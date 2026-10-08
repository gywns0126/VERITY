from __future__ import annotations

import importlib.util
from datetime import date
import io
from pathlib import Path
import subprocess
import sys
import urllib.error
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "member-map" / "capture-annual-customer-tables.py"


def _module():
    spec = importlib.util.spec_from_file_location("capture_annual_customer_tables_tested", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_entrypoint_resolves_repo_imports_before_cli_dispatch(tmp_path):
    result = subprocess.run([sys.executable, str(SCRIPT), "--help"], cwd=tmp_path,
                            capture_output=True, text=True, timeout=10, check=False)

    assert result.returncode == 0
    assert "--fetch-public" in result.stdout
    assert "ModuleNotFoundError" not in result.stderr


def _inputs(*, receipt="20260331000001", name="Example Holdings Co.",
            report="사업보고서 (2025.12)", year="2025", filed="20260331",
            corp="00123456", row_name=None, ticker="123456"):
    company = {"id": "KR:" + ticker, "ticker": ticker, "market": "KR", "name": name}
    row = {"corp_code": corp, "rcept_no": receipt, "rcept_dt": filed,
           "bsns_year": year, "report_nm": report, "name": name if row_name is None else row_name}
    return ({"rows": {ticker: row}}, {ticker: corp},
            {"tickerIndex": {"KR:" + ticker: {"issuer": company}},
             "annual_customer_tables": []})


def test_selector_uses_parser_month_end_and_exact_catalog_identity():
    module = _module()
    overview, mapping, evidence = _inputs()

    selected, summary = module.select_candidates(
        overview, mapping, evidence, today=date(2026, 10, 8))

    assert [row["receipt_no"] for row in selected] == ["20260331000001"]
    assert summary["counts"]["valid_annual_metadata"] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"report": "사업보고서 (2025.13)"},
        {"receipt": 20260331000001},
        {"row_name": "Example Holdings Company"},
        {"filed": "20251230", "receipt": "20251230000001"},
        {"year": 2025},
    ],
)
def test_invalid_candidate_is_rejected_without_aborting_other_rows(changes):
    module = _module()
    bad = _inputs(**changes)
    good = _inputs(receipt="20260331000002", ticker="654321", corp="00654321")
    overview = {"rows": {**bad[0]["rows"], **good[0]["rows"]}}
    mapping = {**bad[1], **good[1]}
    evidence = {"tickerIndex": {**bad[2]["tickerIndex"], **good[2]["tickerIndex"]},
                "annual_customer_tables": []}

    selected, summary = module.select_candidates(
        overview, mapping, evidence, today=date(2026, 10, 8))

    assert [row["receipt_no"] for row in selected] == ["20260331000002"]
    assert summary["counts"]["rejected"] == 1
    assert summary["counts"]["valid_annual_metadata"] == 1


def test_wrong_exact_corp_binding_is_rejected():
    module = _module()
    overview, mapping, evidence = _inputs(corp="00999999")
    mapping["123456"] = "00123456"

    selected, summary = module.select_candidates(
        overview, mapping, evidence, today=date(2026, 10, 8))

    assert selected == []
    assert summary["rejection_reasons"] == {"corp-code-not-exact": 1}


def test_selector_can_bind_from_overview_and_catalog_without_mapping_file():
    module = _module()
    overview, _mapping, evidence = _inputs()

    selected, summary = module.select_candidates(
        overview, None, evidence, today=date(2026, 10, 8))

    assert [row["corp_code"] for row in selected] == ["00123456"]
    assert summary["counts"]["valid_annual_metadata"] == 1


def test_two_receipt_failures_skip_candidate_and_select_next_receipt():
    module = _module()
    first = _inputs(receipt="20260331000001", ticker="123456", corp="00123456")
    second = _inputs(receipt="20260331000002", ticker="654321", corp="00654321")
    overview = {"rows": {**first[0]["rows"], **second[0]["rows"]}}
    mapping = {**first[1], **second[1]}
    evidence = {"tickerIndex": {**first[2]["tickerIndex"], **second[2]["tickerIndex"]},
                "annual_customer_tables": []}
    ledger = {"schema": module._ATTEMPT_SCHEMA, "receipts": {
        "20260331000001": {"failures": 2, "reason": "parse-rejected"}}}

    selected, summary = module.select_candidates(
        overview, mapping, evidence, limit=1, today=date(2026, 10, 8),
        attempt_ledger=ledger)

    assert [row["receipt_no"] for row in selected] == ["20260331000002"]
    assert summary["skipped_after_failures"] == 1


def test_new_receipt_is_not_blocked_by_prior_receipt_failures():
    module = _module()
    overview, mapping, evidence = _inputs(receipt="20260801000001", filed="20260801")
    ledger = {"schema": module._ATTEMPT_SCHEMA, "receipts": {
        "20260331000001": {"failures": 2, "reason": "parse-rejected"}}}

    selected, _summary = module.select_candidates(
        overview, mapping, evidence, today=date(2026, 10, 8), attempt_ledger=ledger)

    assert [row["receipt_no"] for row in selected] == ["20260801000001"]


@pytest.mark.parametrize("outcome", ["access-stop", "rate-limit"])
def test_access_or_rate_limit_does_not_increment_receipt_failures(outcome):
    module = _module()
    original = {"schema": module._ATTEMPT_SCHEMA, "receipts": {
        "20260331000001": {"failures": 1, "reason": "source-fetch-failed"}}}
    before = {"schema": original["schema"], "receipts": dict(original["receipts"])}

    module._update_attempt_ledger(original, "20260331000001", outcome)

    assert original == before


def test_attempt_ledger_atomic_write_preserves_concurrent_change(tmp_path):
    module = _module()
    ledger = {"schema": module._ATTEMPT_SCHEMA, "receipts": {
        "20260331000001": {"failures": 1, "reason": "parse-rejected"}}}

    module._write_attempt_ledger_atomic(tmp_path, None, ledger)
    loaded, raw = module._read_attempt_ledger(tmp_path)
    assert loaded == ledger
    assert raw is not None

    with pytest.raises(ValueError, match="changed-during-run"):
        module._write_attempt_ledger_atomic(tmp_path, None, {"schema": module._ATTEMPT_SCHEMA,
                                                               "receipts": {}})
    assert module._read_attempt_ledger(tmp_path)[0] == ledger


class _Response:
    status = 200

    def __init__(self, body, url="https://opendart.fss.or.kr/api/document.xml"):
        self.body = body
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, size=-1):
        return self.body[:size]

    def geturl(self):
        return self.url


class _Opener:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        return self.response


def _zip_bytes():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("20260331000001.xml", "<ROOT/>")
    return output.getvalue()


def test_annual_capture_selects_only_receipt_named_xml_member():
    from api.intelligence.portfolio_annual_customer_tables import capture_annual_customer_tables

    receipt = "20260331000001"
    xml = ('<DOCUMENT><COMPANY-NAME AREGCIK="00123456">Example Holdings Co.</COMPANY-NAME>'
           '<DOCUMENT-NAME ACODE="11011">사업보고서</DOCUMENT-NAME>'
           '<TU AUNIT="periodFrom" AUNITVALUE="20250101"></TU>'
           '<TU AUNIT="periodTo" AUNITVALUE="20251231"></TU>'
           '<table><tr><td>body</td></tr></table></DOCUMENT>').encode("utf-8")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("unrelated.xml", xml.replace(b"00123456", b"00999999"))
        archive.writestr(receipt + ".xml", xml)

    result = capture_annual_customer_tables(
        output.getvalue(), receipt_no=receipt, issuer_id="KR:123456",
        issuer_name="Example Holdings Co.", corp_code="00123456", filed_on="2026-03-31",
        fiscal_year="2025", report_name="사업보고서 (2025.12)",
        expected_member=receipt + ".xml")

    assert result["archive_member"] == receipt + ".xml"


def test_annual_capture_does_not_guess_between_xml_members():
    from api.intelligence.portfolio_annual_customer_tables import capture_annual_customer_tables

    receipt = "20260331000001"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("first.xml", "<DOCUMENT/>")
        archive.writestr(receipt + ".xml", "<DOCUMENT/>")

    with pytest.raises(ValueError, match="archive-source-member-ambiguous"):
        capture_annual_customer_tables(
            output.getvalue(), receipt_no=receipt, issuer_id="KR:123456",
            issuer_name="Example Holdings Co.", corp_code="00123456", filed_on="2026-03-31",
            fiscal_year="2025", report_name="사업보고서 (2025.12)")


def test_fetch_is_bounded_single_request_and_xml_quota_stops():
    module = _module()
    receipt = "20260331000001"
    opener = _Opener(_Response(_zip_bytes()))

    assert module._fetch_archive(receipt, "test-key-never-logged", opener) == _zip_bytes()
    assert len(opener.calls) == 1
    request, timeout = opener.calls[0]
    assert request.full_url.startswith("https://opendart.fss.or.kr/api/document.xml?")
    assert timeout == 20

    quota = _Opener(_Response(b"<result><status>020</status><message>limited</message></result>"))
    with pytest.raises(module.SourceAccessStop):
        module._fetch_archive(receipt, "test-key-never-logged", quota)
    assert len(quota.calls) == 1


@pytest.mark.parametrize("status_code", ["010", "011", "012", "021"])
@pytest.mark.parametrize("format", ["json", "xml"])
def test_auth_and_access_statuses_stop_without_becoming_receipt_failures(status_code, format):
    module = _module()
    receipt = "20260331000001"
    if format == "json":
        body = ("{\"status\":\"" + status_code + "\",\"message\":\"limited\"}").encode()
    else:
        body = ("<result><status>" + status_code + "</status><message>limited</message></result>").encode()
    opener = _Opener(_Response(body))

    with pytest.raises(module.SourceAccessStop, match="dart-status-" + status_code):
        module._fetch_archive(receipt, "test-key-never-logged", opener)

    assert len(opener.calls) == 1


def test_fetch_rejects_redirected_endpoint_and_invalid_receipt():
    module = _module()
    opener = _Opener(_Response(_zip_bytes(), "https://example.invalid/api/document.xml"))
    with pytest.raises(ValueError, match="unexpected-source-endpoint"):
        module._fetch_archive("20260331000001", "test-key", opener)
    assert len(opener.calls) == 1

    never_called = _Opener(_Response(_zip_bytes()))
    with pytest.raises(ValueError, match="invalid-receipt"):
        module._fetch_archive(20260331000001, "test-key", never_called)
    assert never_called.calls == []


def test_missing_api_key_stops_before_loading_capture_helper(tmp_path, monkeypatch):
    module = _module()
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    output_dir = tmp_path / "output"
    monkeypatch.delenv("DART_API_KEY", raising=False)
    monkeypatch.setattr(module, "_load_capture_module",
                        lambda: pytest.fail("helper must not load before key validation"))

    with pytest.raises(SystemExit, match="DART_API_KEY is required"):
        module.main(["--source-dir", str(source_dir), "--output-dir", str(output_dir),
                     "--fetch-public"])

    assert not output_dir.exists()


def test_archive_cache_rejects_symlinks_and_accepts_exact_receipt_name(tmp_path):
    module = _module()
    receipt = "20260331000001"
    archive_path = tmp_path / (receipt + ".zip")
    archive_path.write_bytes(_zip_bytes())
    assert module._archive_path(tmp_path, receipt) == archive_path
    assert module._read_archive(archive_path) == _zip_bytes()

    only_symlink_dir = tmp_path / "symlink-only"
    only_symlink_dir.mkdir()
    linked = only_symlink_dir / ("dart-document-" + receipt + ".zip")
    linked.symlink_to(archive_path)
    with pytest.raises(ValueError, match="invalid-archive-cache-file"):
        module._archive_path(only_symlink_dir, receipt)
