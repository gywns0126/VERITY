"""Synthetic responses and this checkout only; no key/config/network access."""
import ast
import copy
import importlib.util
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("structure_test_core", ROOT / "api/collectors/company_structure_refresh.py")
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _isolate_data_dir(monkeypatch):
    # Override the root fixture: it imports trading modules and credentials.
    import socket
    original_get = core.os.environ.get

    def guarded_get(key, *args):
        if key == "DART_API_KEY":
            pytest.fail("synthetic test read a credential")
        return original_get(key, *args)

    monkeypatch.setattr(core.os.environ, "get", guarded_get)
    monkeypatch.setattr(socket.socket, "connect", lambda *args: pytest.fail("real network attempted"))
    yield


@pytest.fixture
def helpers():
    return SimpleNamespace(ROOT=ROOT, BoundedSession=core.BoundedSession,
                           _attach_source_rows=core._attach_source_rows)


def document(tmp_path, n=3):
    (tmp_path / "data").mkdir(exist_ok=True)
    listed = {f"{i:06d}": {"name": f"Issuer {i}", "market": "KS"} for i in range(1, n + 1)}
    (tmp_path / "data/kr_listed.json").write_text(json.dumps(listed))
    (tmp_path / "data/mapping.json").write_text(json.dumps({key: key.zfill(8) for key in listed}))
    return core.build_document(tmp_path, now=NOW)


def scout_with(helpers, responses):
    """Use the real parser functions without importing config or stock data."""
    tree = ast.parse((helpers.ROOT / "api/collectors/DartScout.py").read_text())
    names = {"fetch_major_shareholders", "fetch_subsidiary_investments", "_parse_int", "_parse_float"}
    namespace = {"ANNUAL_REPORT": "11011", "re": re, "time": time}
    exec(compile("from __future__ import annotations", "annotations", "exec"), namespace)
    functions = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
    exec(compile(ast.unparse(functions), "existing_dart_parsers", "exec", flags=0x1000000), namespace)
    scout = SimpleNamespace(_SESSION=object())
    pending = iter(responses)
    physical = []

    def physical_get(url, **kwargs):
        physical.append((url, kwargs))
        result = next(pending)
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(status_code=result if isinstance(result, int) else 200,
                               payload=result)

    real_session = helpers.BoundedSession

    class Session(real_session):
        def __init__(self, limit):
            super().__init__(limit)
            self._session.get = physical_get

    def call(endpoint, params):
        response = scout._SESSION.get("https://opendart.fss.or.kr/api/" + endpoint, params=params)
        if response.status_code != 200:
            raise ValueError("http-error")
        return response.payload

    scout._call = call
    for name in names & {"fetch_major_shareholders", "fetch_subsidiary_investments"}:
        parsed_function = namespace[name]

        def fetch(corp, year, function=parsed_function):
            namespace["_call"] = scout._call
            return function(corp, year)

        setattr(scout, name, fetch)
    return scout, SimpleNamespace(BoundedSession=Session, _attach_source_rows=helpers._attach_source_rows), physical


def refresh(doc, tmp_path, helpers, responses, **kwargs):
    scout, capture, physical = scout_with(helpers, responses)
    original = scout._SESSION, scout._call
    saved = []
    # Exercise the production default helper path; replace only its transport.
    with patch.object(core._CaptureHelpers, "BoundedSession", capture.BoundedSession):
        result, summary = core.refresh(doc, source_dir=tmp_path, fetch_public=True, now=NOW,
                                      scout=scout,
                                      checkpoint=lambda value: saved.append(copy.deepcopy(value)), **kwargs)
    assert (scout._SESSION, scout._call) == original
    assert summary["requests"] == len(physical)
    assert all(not kw["allow_redirects"] for _, kw in physical)
    assert all(kw["params"]["bsns_year"] == core.expected_period(NOW)["year"]
               and kw["params"]["reprt_code"] == core.expected_period(NOW)["reportCode"]
               for _, kw in physical)
    return result, summary, saved


def test_dry_plan_no_imports_requests_or_identity_selfheal(tmp_path, monkeypatch):
    doc = document(tmp_path)
    listed = core.read_json(tmp_path / "data/kr_listed.json")
    listed.update({"0068Y0": {"name": "Mixed code", "market": "KQ"},
                   "0017J0": {"name": "Unmapped mixed code", "market": "KQ"}})
    core.atomic_json(tmp_path / "data/kr_listed.json", listed)
    mapping = core.read_json(tmp_path / "data/mapping.json")
    mapping["0068Y0"] = "01933981"
    core.atomic_json(tmp_path / "data/mapping.json", mapping)
    doc = core.build_document(tmp_path / "data", now=NOW)
    monkeypatch.setattr(core, "BoundedSession", lambda _: pytest.fail("dry opened live session"))
    doc["issuers"]["KR:000003"]["corp_code"] = None
    result, summary = core.refresh(doc, source_dir=tmp_path, now=NOW)
    assert summary["requests"] == summary["attempted"] == 0
    assert summary["requested"] == 5 and summary["selected"] == 3 and summary["unmapped"] == 2
    assert "KR:0068Y0" in summary["lists"]["selected"]
    assert summary["unmappedReasons"]["KR:0017J0"] == "missing-corp-code"
    assert result["issuers"]["KR:000001"]["endpoints"]["hyslrSttus"]["attemptStatus"] == "not-attempted"


def test_selection_missing_then_oldest_and_seven_day_ttl(tmp_path):
    doc = document(tmp_path, 4)
    for index, age in ((2, 20), (3, 8), (4, 6)):
        for block in doc["issuers"][f"KR:{index:06d}"]["endpoints"].values():
            block.update(status="013", lastSuccessAt=(NOW - timedelta(days=age)).isoformat())
    selected, unmapped, fresh, deferred = core.select_issuers(doc, 2, NOW)
    assert selected == ["KR:000001", "KR:000002"]
    assert fresh == ["KR:000004"] and deferred == ["KR:000003"] and not unmapped
    for year, month, day, expected_year, report in ((2026, 10, 22, "2026", "11012"),
            (2026, 11, 30, "2026", "11014"), (2027, 1, 1, "2026", "11014"),
            (2027, 3, 15, "2026", "11014"), (2027, 4, 1, "2026", "11011"),
            (2027, 6, 1, "2027", "11013")):
        assert core.expected_period(datetime(year, month, day, tzinfo=timezone.utc)) == {"year": expected_year, "reportCode": report}


def test_hard_issuer_limit_and_validation(tmp_path):
    doc = document(tmp_path, 305)
    assert len(core.select_issuers(doc, now=NOW)[0]) == 300
    for limit in (-1, 301, True):
        with pytest.raises(ValueError):
            core.select_issuers(doc, limit, NOW)
    doc["requestBudget"] = {"day": "2026-10-21", "requests": 601}
    with pytest.raises(ValueError):
        core.refresh(doc, source_dir=tmp_path, now=NOW)


def test_fair_due_selection_rotates_300_errors_before_stale_and_preserves_clocks(tmp_path):
    doc = document(tmp_path, 602)
    for index in range(1, 301):
        # One failed endpoint already makes the issuer attempted, not unvisited.
        doc["issuers"][f"KR:{index:06d}"]["endpoints"]["hyslrSttus"].update(
            attemptStatus="error", attemptedAt=NOW.isoformat())
    later = NOW + timedelta(days=1)
    before = copy.deepcopy(doc)
    selected = core.select_issuers(doc, 300, later)[0]
    assert selected == [f"KR:{index:06d}" for index in range(301, 601)]
    assert doc == before  # Selection never rewrites source/check/attempt clocks.
    for key in selected:
        for block in doc["issuers"][key]["endpoints"].values():
            block.update(attemptStatus="error", attemptedAt=later.isoformat())
    next_batch = core.select_issuers(doc, 300, later + timedelta(days=1))[0]
    assert next_batch[:2] == ["KR:000601", "KR:000602"]
    assert next_batch[2:] == [f"KR:{index:06d}" for index in range(1, 299)]

    mixed = document(tmp_path, 3)
    for index, age, status in ((1, 1, "error"), (2, 20, "000"), (3, 10, "error")):
        for block in mixed["issuers"][f"KR:{index:06d}"]["endpoints"].values():
            stamp = (NOW - timedelta(days=age)).isoformat()
            block.update(status=status, attemptedAt=stamp)
            if status == "000":
                block.update(lastSuccessAt=stamp, checkedAt=stamp)
    assert core.select_issuers(mixed, 3, NOW)[0] == ["KR:000002", "KR:000003", "KR:000001"]
    for block in mixed["issuers"]["KR:000002"]["endpoints"].values():
        block["checkedAt"] = (NOW - timedelta(days=1)).isoformat()
    for block in mixed["issuers"]["KR:000003"]["endpoints"].values():
        block.update(status="000", checkedAt=(NOW + timedelta(days=1)).isoformat())
    before = copy.deepcopy(mixed)
    selected, _, fresh, _ = core.select_issuers(mixed, 3, NOW)
    assert selected == ["KR:000003", "KR:000001"] and fresh == ["KR:000002"]
    assert mixed == before  # Future checks remain due, never promoted as fresh.


def test_same_response_rows_and_provenance(tmp_path, helpers):
    doc = document(tmp_path, 1)
    raw = {"nm": "Owner Inc", "corp_code": "00000001", "rcept_no": "20260301000001", "stlm_dt": "2025-12-31", "trmend_posesn_stock_qota_rt": "51.00"}
    people = [{**raw, "nm": name} for name in ("홍길동", "Owner Trust Inc", "개인 투자조합 LLC")]
    inv = {"inv_prm": " Affiliate Ltd ", "corp_code": "00000001", "rcept_no": "20260301000001", "stlm_dt": "2025.12.31", "trmend_blce_qota_rt": "30.00", "trmend_blce_qy": "1,234"}
    result, summary, saved = refresh(doc, tmp_path, helpers, [{"status": "000", "list": [raw] + people}, {"status": "000", "list": [inv]}])
    assert summary["success"] == 2 and summary["error"] == 0
    endpoint = result["issuers"]["KR:000001"]["endpoints"]["hyslrSttus"]
    assert endpoint["rows"][0]["sourceRow"]["fields"]["stlm_dt"] == raw["stlm_dt"]
    assert endpoint["rows"][0]["provenance"]["rcept_no"] == raw["rcept_no"]
    assert endpoint["rows"][0]["provenance"]["stlm_dt"] == raw["stlm_dt"]
    assert endpoint["rows"][0]["provenance"]["bsns_year"] == "2026"
    assert endpoint["rows"][0]["provenance"]["reprt_code"] == "11012"
    assert endpoint["reportPeriod"] == {"year": "2026", "reportCode": "11012"}
    assert endpoint["sourcePeriodStatus"] == "source-period-mismatch"
    investment = result["issuers"]["KR:000001"]["endpoints"]["otrCprInvstmntSttus"]["rows"][0]
    assert investment["sourceRow"]["fields"]["trmend_blce_qy"] == "1,234"
    assert investment["end_balance_qty"] == 1234 and investment["quantityStatus"] == "source-quantity-verified"
    assert endpoint["raw_row_count"] == 4 and endpoint["corporate_row_count"] == 1
    assert endpoint["omitted_non_corporate_count"] == 3
    assert "rawResponse" not in json.dumps(result)
    for value in (result, saved):
        assert all(person["nm"] not in json.dumps(value, ensure_ascii=False) for person in people)
    assert saved[0]["requestBudget"]["requests"] == 1
    assert saved[0]["issuers"]["KR:000001"]["endpoints"]["hyslrSttus"]["rows"] == []


def test_failure_retains_previous_rows_status_and_dates(tmp_path, helpers):
    doc = document(tmp_path, 1)
    old_stamp = (NOW - timedelta(days=20)).isoformat()
    issuer = doc["issuers"]["KR:000001"]
    issuer["collectedAt"] = old_stamp
    for endpoint, block in issuer["endpoints"].items():
        name_key = "nm" if endpoint == "hyslrSttus" else "inv_corp_name"
        raw_name = "nm" if endpoint == "hyslrSttus" else "inv_prm"
        block.update(status="000", rows=[{name_key: "Retained Corp", "provenance": {"rcept_no": "20250301000001"}, "sourceRow": {"fields": {raw_name: "Retained Corp", "rcept_no": "20250301000001", "stlm_dt": "2024.12.31"}}}],
                     rawResponse={"status": "000", "list": [{"rcept_no": "20250301000001"}]},
                     lastSuccessAt=old_stamp, checkedAt=old_stamp)
    safe_previous = core.sanitize_document(doc)
    result, summary, saved = refresh(doc, tmp_path, helpers, [{"status": "100"}, {"status": "013", "list": []}])
    block = result["issuers"]["KR:000001"]["endpoints"]["hyslrSttus"]
    assert block["status"] == "000" and block["rows"] == safe_previous["issuers"]["KR:000001"]["endpoints"]["hyslrSttus"]["rows"]
    assert block["lastSuccessAt"] == block["checkedAt"] == old_stamp
    assert "rawResponse" not in json.dumps(saved)
    assert block["attemptStatus"] == "100"
    assert result["issuers"]["KR:000001"]["collectedAt"] == old_stamp
    assert summary["error"] == summary["empty"] == summary["retained"] == 1
    retained, attempt, _ = refresh(doc, tmp_path, helpers, [{"status": "013", "list": []}] * 2)
    retained_block = retained["issuers"]["KR:000001"]["endpoints"]["hyslrSttus"]
    assert retained_block["lastSuccessAt"] == old_stamp and retained_block["rows"] == block["rows"]
    assert retained_block["attemptStatus"] == "013" and retained_block["status"] == "000"
    assert retained_block["attemptPeriod"] == {"year": "2026", "reportCode": "11012"}
    assert attempt["retained"] == 1


def test_013_distinct_from_failure_and_not_attempted(tmp_path, helpers):
    result, summary, _ = refresh(document(tmp_path, 2), tmp_path, helpers, [{"status": "013", "list": []}] * 2, limit=1)
    assert summary["empty"] == 2 and summary["success"] == summary["error"] == 0
    assert result["issuers"]["KR:000001"]["endpoints"]["hyslrSttus"]["status"] == "013"
    assert result["issuers"]["KR:000002"]["endpoints"]["hyslrSttus"]["attemptedAt"] is None
    assert core.select_issuers(result, now=NOW)[0] == ["KR:000002"]
    result, summary, saved = refresh(document(tmp_path, 1), tmp_path, helpers,
                                    [{"status": "000", "list": [{"nm": "김개인"}]}, {"status": "013", "list": []}])
    block = result["issuers"]["KR:000001"]["endpoints"]["hyslrSttus"]
    assert block["status"] == "000" and block["rows"] == []
    assert block["sourceResult"] == "no-qualifying-corporate-rows" and block["lastSuccessAt"] == NOW.isoformat()
    assert block["raw_row_count"] == block["omitted_non_corporate_count"] == 1
    assert "김개인" not in json.dumps(saved, ensure_ascii=False)


def test_immediate_global_stop_for_dart_and_http(tmp_path, helpers):
    for failure in ({"status": "020"}, 401, 403, 429):
        result, summary, _ = refresh(document(tmp_path), tmp_path, helpers, [failure])
        assert summary["requests"] == summary["error"] == 1
        assert summary["stopReason"] in ("020", "HTTP401", "HTTP403", "HTTP429")
        assert summary["sourceError"] == summary["exitCode"] == 1
        assert result["issuers"]["KR:000001"]["endpoints"]["otrCprInvstmntSttus"]["attemptStatus"] == "not-attempted"
        assert summary["deferred"] == 2


def test_daily_budget_persists_across_runs_and_resets_kst(tmp_path, helpers, monkeypatch):
    doc = document(tmp_path, 2)
    doc["requestBudget"] = {"day": "2026-10-21", "requests": 599}
    result, summary, _ = refresh(doc, tmp_path, helpers, [{"status": "013", "list": []}])
    assert summary["requests"] == 1 and summary["dailyRequestsAfter"] == 600
    assert summary["sourceError"] == summary["exitCode"] == 0 and summary["budgetDeferred"] == 2
    _, repeated, _ = refresh(result, tmp_path, helpers, [])
    assert repeated["requests"] == 0 and repeated["stopReason"] == "daily-request-budget"
    assert repeated["sourceError"] == repeated["exitCode"] == 0
    store = tmp_path / "budget-store.json"
    core.atomic_json(store, result)
    cli_spec = importlib.util.spec_from_file_location("kr_budget_cli", ROOT / "scripts/member-map/refresh-company-structure.py")
    cli = importlib.util.module_from_spec(cli_spec)
    cli_spec.loader.exec_module(cli)
    monkeypatch.setattr(cli, "datetime", SimpleNamespace(now=lambda _: NOW))
    assert cli.run(cli.parse_args(["--source-dir", str(tmp_path), "--store", str(store), "--fetch-public"])) == 0
    assert core.read_json(store)["summary"]["stopReason"] == "daily-request-budget"
    result["requestBudget"]["day"] = "2026-10-20"
    _, next_day, _ = refresh(result, tmp_path, helpers, [{"status": "013", "list": []}] * 4)
    assert next_day["dailyRequestsBefore"] == 0 and next_day["requests"] == 4
    assert next_day["guardedBudget"]["valid"]
    # A complete synthetic day exercises both hard ceilings physically.
    scout, capture, physical = scout_with(helpers, [{"status": "013", "list": []}] * 600)
    _, ceiling = core.refresh(document(tmp_path, 305), source_dir=tmp_path,
                              fetch_public=True, now=NOW, helpers=capture, scout=scout,
                              checkpoint=lambda _: None)
    assert ceiling["attempted"] == 300 and ceiling["requests"] == len(physical) == 600
    assert ceiling["deferred"] == 5


def test_timeout_and_parser_mismatch_no_retries_or_freshness(tmp_path, helpers):
    import requests
    for response in (requests.ConnectionError("secret-url"), {"status": "000", "list": [{"nm": "Other", "corp_code": "99999999"}]}):
        result, summary, _ = refresh(document(tmp_path, 1), tmp_path, helpers, [response, {"status": "013", "list": []}])
        assert summary["requests"] == 2 and summary["error"] == 1
        assert summary["exitCode"] == summary["sourceError"] == 1 and summary["stopReason"] == "source-error"
        block = result["issuers"]["KR:000001"]["endpoints"]["hyslrSttus"]
        assert block["status"] == "error" and "lastSuccessAt" not in block
        assert block["attemptStatus"] == "error"
    bounded = core.BoundedSession(1)
    try:
        assert bounded._session.get_adapter("https://").max_retries.total == 0
        bounded._session.get = lambda *args, **kwargs: object()
        bounded.get("https://example.invalid")
        with pytest.raises(core.RequestBudgetExceeded):
            bounded.get("https://example.invalid")
        assert bounded.count == 1
    finally:
        bounded.close()
    response = {"list": [{"nm": "Owner", "rcept_no": "20260301000001"}]}
    for parsed in ([], [{"nm": "Wrong order"}]):
        with pytest.raises(ValueError):
            core._attach_source_rows("hyslrSttus.json", parsed, response, "00000001")


def test_seed_merge_atomic_store_and_explicit_cli_store(tmp_path):
    doc = document(tmp_path, 1)
    stamp = (NOW - timedelta(days=10)).isoformat()
    seed = {"schema": "alphaconsole-dart-structured-provenance-source-v1", "issuers": [{
        "ticker": "000001", "name": "old", "corp_code": "00000001", "collected_at": stamp,
        "endpoints": {key: {"status": "013", "rows": []} for key in core.ENDPOINTS}}]}
    seeded = core.build_document(tmp_path, seed=seed, now=NOW)
    private_row = {"nm": "김개인", "sourceRow": {"index": 0, "fields": {"nm": "김개인"}}}
    seed["issuers"][0]["endpoints"]["hyslrSttus"].update(status="000", rows=[private_row], rawResponse={"list": [{"nm": "김개인"}]}, metadata={"signature": "김개인"})
    seeded = core.build_document(tmp_path, seed=seed, now=NOW)
    assert "김개인" not in json.dumps(seeded, ensure_ascii=False)
    store = tmp_path / "sources.json"
    core.atomic_json(store, seeded)
    assert core.read_json(store) == seeded
    merged = core.build_document(tmp_path, existing=doc, seed=seed, now=NOW)
    assert merged["issuers"]["KR:000001"]["collectedAt"] is None
    cli_spec = importlib.util.spec_from_file_location("structure_cli", ROOT / "scripts/member-map/refresh-company-structure.py")
    cli = importlib.util.module_from_spec(cli_spec)
    cli_spec.loader.exec_module(cli)
    with pytest.raises(SystemExit):
        cli.parse_args([])
    before = store.read_bytes()
    assert cli.run(cli.parse_args(["--store", str(store), "--source-dir", str(tmp_path)])) == 0
    assert store.read_bytes() == before and not store.with_name(store.name + ".lock").exists()
