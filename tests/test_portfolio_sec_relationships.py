"""Independent adversarial checks. All names/HTML are synthetic, not SEC quotes.

Only this test file is owned by the reviewer. HTTP is forbidden; CLI transport
is replaced with explicit bytes. Failing assertions describe required behavior,
not accepted production behavior, and are deliberately not marked xfail.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sys
import urllib.request

import pytest

from api.intelligence import portfolio_sec_relationships as sec
from api.intelligence.portfolio_evidence import _validate_artifact

# Clean release checkouts contain the deployed mirror, not the local source engine.
if importlib.util.find_spec("api.intelligence.portfolio_engine") is not None:
    engine = importlib.import_module("api.intelligence.portfolio_engine")
else:
    engine = importlib.import_module("vercel-api.api.portfolio_core.portfolio_engine")

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "capture_sec_test", ROOT / "scripts/member-map/capture-sec-relationships.py")
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


def metadata(**changes):
    return {"issuer_id": "US:AAA", "issuer_name": "Alpha Corporation", "cik": "0000000001",
            "accession": "0000000001-26-000001", "filed_date": "2026-02-01",
            "period_end": "2025-12-31", "form": "10-K", "primary_document": "annual.htm",
            "url": "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/annual.htm", **changes}


def capture(paragraphs=None, **changes):
    return {**metadata(), "schema": "sec-annual-excerpts-v1", "document_sha256": "a" * 64,
            "paragraphs": ["Our customers include Beta Corporation."] if paragraphs is None else paragraphs,
            **changes}


def companies():
    return [{"id": "US:" + ticker, "ticker": ticker, "market": "US", "name": name,
             "facts": [], "documents": []} for ticker, name in (
                 ("AAA", "Alpha Corporation"), ("BBB", "Beta Corporation"),
                 ("CCC", "Gamma Corporation"), ("ZZZ", "Unrelated Corporation"))]


def html(body="<p>Our customers include Beta Corporation.</p>", **facts):
    fields = {"EntityCentralIndexKey": "0000000001", "DocumentPeriodEndDate": "2025-12-31",
              "DocumentType": "10-K", **facts}
    return ("<html><body>" + "".join(
        f'<ix:nonNumeric name="dei:{key}">{value}</ix:nonNumeric>'
        for key, value in fields.items()) + body + "</body></html>").encode()


def artifact(captures=()):
    value = {
        "schemaVersion": 1, "generatedAt": "2026-02-02T00:00:00Z",
        "scope": {"mode": "published-automatic-evidence-catalog",
                  "runtimeFreshness": "not-automatically-reverified",
                  "note": "Generated from declared received source snapshots; source timestamps are reported separately and are not automatically reverified."},
        "artifactTimestamps": {}, "sourceDateCoverage": {},
        "inputs": {name: {"bytes": 0, "sha256": "0" * 64}
                   for name in ("universe", "chainSnippets", "groupStructure")},
        "identityCatalog": {"identities": 0, "textMatchMarkets": ["KR", "KONEX", "US"]},
        "denominators": {key: 0 for key in (
            "issuersInput", "issuersIndexed", "documentsInput", "documentsAccepted", "excerptsInput",
            "excerptsAccepted", "excerptsRejected", "relationsInput", "relationsAccepted", "relationsRejected")},
        "rejectionReasons": {}, "tickerIndex": {}, "sources": {}, "events": {},
        "relations": {}, "corrections": [], "sec_filing_excerpts": list(captures),
    }
    return value


@pytest.fixture(autouse=True)
def no_http(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("HTTP is forbidden in independent SEC review")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(urllib.request.OpenerDirector, "open", forbidden)
    engine._reset_projection_cache_for_tests()
    yield
    engine._reset_projection_cache_for_tests()


@pytest.mark.parametrize("role", ["customers", "suppliers"])
def test_valid_capture_role_quote_hash_and_historical_scope(role):
    quote = f"Our {role} include Beta Corporation."
    raw = html(f"<p>{quote}</p>")
    row = sec.capture_sec_html(raw, metadata())
    assert row["document_sha256"] == hashlib.sha256(raw).hexdigest()
    index = sec.index_sec_relationships([row], companies())
    relation, = index["relations"]
    assert relation["evidence"]["quote"] == quote
    assert relation["evidence"]["role"] == role[:-1]
    assert relation["source"]["as_of"] == "2026-02-01"
    assert relation["source"]["period_end"] == "2025-12-31"
    assert relation["snapshot_scope"] == "reported-filing-period-not-current"


@pytest.mark.parametrize("facts", [
    {"EntityCentralIndexKey": "0000000002"}, {"DocumentPeriodEndDate": "2024-12-31"},
    {"DocumentType": "10-Q"}, {"DocumentType": "10-K/A"},
])
def test_inline_xbrl_binding_rejects_mismatch(facts):
    with pytest.raises(ValueError):
        sec.capture_sec_html(html(**facts), metadata())


@pytest.mark.parametrize("transform,text,period,error", [
    ("ixt:date-monthname-day-year-en", "October 31 , 2025", "2025-10-31", None),
    ("ixt:date-monthname-day-year-en", "October 31 , 2025", "2025-09-30", "sec-html-period"),
    ("ixt:unsupported-date", "October 31 , 2025", "2025-10-31", "sec-html-period"),
    (None, "October 31 , 2025", "2025-10-31", "sec-html-period"),
    ("ixt:date-monthname-day-year-en", "February 30 , 2025", "2025-02-28", "sec-html-date-transform"),
])
def test_declared_inline_date_transform_binding(transform, text, period, error):
    # Synthetic filing: reproduce the reported formatting, not an official quote.
    attribute = f' format="{transform}"' if transform is not None else ""
    raw = html().replace(
        b'<ix:nonNumeric name="dei:DocumentPeriodEndDate">2025-12-31</ix:nonNumeric>',
        f'<ix:nonNumeric name="dei:DocumentPeriodEndDate"{attribute}>{text}</ix:nonNumeric>'.encode())
    meta = metadata(filed_date="2025-12-22", period_end=period,
                    accession="0000000001-25-000001",
                    url="https://www.sec.gov/Archives/edgar/data/1/000000000125000001/annual.htm")
    if error:
        with pytest.raises(ValueError, match=f"^{error}$"):
            sec.capture_sec_html(raw, meta)
    else:
        row = sec.capture_sec_html(raw, meta)
        assert row["period_end"] == "2025-10-31"
        assert row["filed_date"] == "2025-12-22"
        assert row["document_sha256"] == hashlib.sha256(raw).hexdigest()
        relation, = sec.index_sec_relationships([row], companies())["relations"]
        assert relation["source"]["period_end"] == "2025-10-31"


def test_conflicting_duplicate_inline_fact_rejected():
    body = '<ix:nonNumeric name="dei:EntityCentralIndexKey">0000000002</ix:nonNumeric>'
    with pytest.raises(ValueError, match="sec-html-issuer"):
        sec.capture_sec_html(html(body), metadata())


@pytest.mark.parametrize("body", [
    "<table><tr><td>Our customers include</td><td>Beta Corporation.</td></tr></table>",
    "<table><tr><td><p>Our customers include Beta Corporation.</p></td></tr></table>",
])
def test_tables_never_become_prose_relationships(body):
    row = sec.capture_sec_html(html(body), metadata())
    assert row["paragraphs"] == []
    assert sec.index_sec_relationships([row], companies())["relations"] == []


def test_nohit_is_valid_source_but_no_relationship():
    row = sec.capture_sec_html(html("<p>We manufacture components.</p>"), metadata())
    index = sec.index_sec_relationships([row], companies())
    assert index["coverage"]["issuer_bound"] == 1
    assert index["relations"] == []


@pytest.mark.parametrize("mode", ["unknown", "mixed-unknown", "ambiguous", "issuer-mismatch", "self"])
def test_names_must_bind_uniquely(mode):
    catalog = companies()
    row = capture()
    if mode == "unknown":
        row["paragraphs"] = ["Our customers include Unknown Corporation."]
    elif mode == "mixed-unknown":
        row["paragraphs"] = ["Our customers include Beta Corporation and Unknown Corporation."]
    elif mode == "ambiguous":
        catalog.append({"id": "US:DDD", "name": "Beta Inc."})
    elif mode == "issuer-mismatch":
        row["issuer_name"] = "Gamma Corporation"
    else:
        row["paragraphs"] = ["Our customers include Alpha Corporation."]
    assert sec.index_sec_relationships([row], catalog)["relations"] == []


@pytest.mark.parametrize("quote", [
    "Our customers do not include Beta Corporation.",
    "Our potential customers include Beta Corporation.",
    "Rival Corporation's customers include Beta Corporation.",
    "Our customers may include Beta Corporation.",
    "Our former customers include Beta Corporation.",
    "Our customers include Beta Corporation and Gamma Corporation, subject to regulatory approval.",
    "Our suppliers include Beta Corporation, unless negotiations fail.",
    "Our customers include Beta Corporation, according to Rival Corporation.",
])
def test_negation_other_subject_and_qualified_roles_are_not_accepted(quote):
    assert sec.index_sec_relationships([capture([quote])], companies())["relations"] == []


@pytest.mark.parametrize("tag", ["blockquote", "q"])
def test_other_company_quoted_paragraph_does_not_become_issuer_role(tag):
    body = (f'<{tag}><p>Rival Corporation states:</p>'
            f'<p>Our customers include Beta Corporation.</p></{tag}>')
    row = sec.capture_sec_html(html(body), metadata())
    assert sec.index_sec_relationships([row], companies())["relations"] == []


def foundry_quote(second="Gamma Corporation"):
    # Synthetic names in the full grammar observed at NVDA capture paragraphs[16].
    return ("We utilize foundries, such as Beta Corporation, or BETA, and "
            f"{second}, or GAMMA, to produce our semiconductor wafers.")


@pytest.mark.parametrize("second,expected", [
    ("Gamma Corporation", {"US:BBB", "US:CCC"}),
    ("Unknown Corporation", {"US:BBB"}),
])
def test_foundry_explicit_names_preserve_supplier_period_and_full_quote(second, expected):
    quote = ("We have expanded our supplier relationships. " + foundry_quote(second)
             + " We purchase memory from other suppliers.")
    row = sec.capture_sec_html(html(f"<p>{quote}</p>"), metadata())
    index = sec.index_sec_relationships([row], companies())
    assert {r["participants"][1]["id"] for r in index["relations"]} == expected
    for relation in index["relations"]:
        assert relation["participants"][0]["id"] == "US:AAA"
        assert relation["participants"][1]["role"] == "reported_supplier"
        assert relation["evidence"]["quote"] == quote
        assert relation["evidence"]["paragraph_sha256"] == hashlib.sha256(quote.encode()).hexdigest()
        assert relation["source"]["period_end"] == "2025-12-31"
        assert relation["source"]["as_of"] == "2026-02-01"
        assert relation["snapshot_scope"] == "reported-filing-period-not-current"
    if second == "Unknown Corporation":
        assert index["coverage"]["rejection_reasons"]["party-not-uniquely-bound"] == 1


@pytest.mark.parametrize("tag", ["blockquote", "q"])
def test_foundry_quoted_html_is_not_issuer_evidence(tag):
    raw = html(f"<{tag}><p>{foundry_quote()}</p></{tag}>")
    row = sec.capture_sec_html(raw, metadata())
    assert row["paragraphs"] == []
    assert sec.index_sec_relationships([row], companies())["relations"] == []


@pytest.mark.parametrize("quote", [
    '"' + foundry_quote() + '"',
    "If demand grows. " + foundry_quote(),
    foundry_quote() + " This arrangement is subject to regulatory approval.",
    foundry_quote() + " This arrangement applies only provided that regulatory approval is obtained.",
    foundry_quote().replace("We utilize", "Rival Corporation utilizes"),
    foundry_quote().replace("We utilize", "We do not utilize"),
    "Foundries such as Beta Corporation and Gamma Corporation produce semiconductor wafers.",
    "Our suppliers include Beta Corporation and unknown foundries.",
])
def test_foundry_conditional_quoted_and_generic_boundaries(quote):
    assert sec.index_sec_relationships([capture([quote])], companies())["relations"] == []


@pytest.mark.parametrize("changes", [
    {"filed_date": "2099-02-01"}, {"filed_date": "2026-02-30"},
    {"period_end": "2026-03-01"}, {"url": "https://example.com/annual.htm"},
    {"url": metadata()["url"] + "?secret=x"}, {"primary_document": "../annual.htm"},
    {"primary_document": "/annual.htm"}, {"document_sha256": "x" * 64},
])
def test_capture_date_url_and_path_contract(changes):
    with pytest.raises(ValueError):
        sec.validate_sec_capture(capture(**changes))


def test_all_us_catalog_offset_is_not_portfolio_window():
    rows = [{"ticker": f"T{i:03}", "market": "US"} for i in range(65)]
    rows += [{"ticker": "000001", "market": "KR"}, rows[0]]
    selected, total = cli.select_catalog({"stocks": rows}, offset=40, limit=20)
    assert selected == [f"T{i:03}" for i in range(40, 60)] and total == 65


def test_engine_attaches_only_selected_sec_relationships():
    docs = {"universe_search.json": {"stocks": companies()},
            "member_map_auto_evidence.json": artifact([capture()])}
    _validate_artifact(docs["member_map_auto_evidence.json"])
    result = engine.analyze_portfolio([{"ticker": "BBB", "market": "US"}], docs)
    relation, = result["automatic_evidence"]["relationships"]
    assert relation["participants"][0]["id"] == "US:AAA"
    assert result["_meta"]["external_model_calls"] == 0
    unrelated = engine.analyze_portfolio([{"ticker": "ZZZ", "market": "US"}], docs)
    assert unrelated["automatic_evidence"]["relationships"] == []


@pytest.mark.parametrize("bad_captures", [None, {}, [{}], [capture(), {}]])
def test_malformed_capture_cannot_break_unrelated_portfolio(bad_captures):
    docs = {"universe_search.json": {"stocks": companies()},
            "member_map_auto_evidence.json": artifact()}
    positions = [{"ticker": "ZZZ", "market": "US"}]
    baseline = engine.analyze_portfolio(positions, docs)
    docs["member_map_auto_evidence.json"]["sec_filing_excerpts"] = bad_captures
    before = deepcopy(docs)
    result = engine.analyze_portfolio(positions, docs, public_bundle_revision="a" * 64)
    assert result["companies"][0]["id"] == "US:ZZZ"
    for field in ("companies", "documents", "prices"):
        assert result[field] == baseline[field]
    assert result["automatic_evidence"] is None
    assert result["coverage"]["evidence"]["status"] == "rejected"
    assert engine.analyze_portfolio(positions, docs, public_bundle_revision="a" * 64) == result
    assert docs == before


def submission():
    return {"cik": 1, "tickers": ["AAA"], "name": "Alpha Corporation", "filings": {"recent": {
        "form": ["10-K"], "filingDate": ["2026-02-01"], "reportDate": ["2025-12-31"],
        "accessionNumber": ["0000000001-26-000001"], "primaryDocument": ["annual.htm"]}}}


@pytest.mark.parametrize("change", ["wrong-cik", "wrong-ticker", "amendment"])
def test_script_metadata_identity_and_amendment(change):
    doc = submission()
    if change == "wrong-cik":
        doc["cik"] = 2
    elif change == "wrong-ticker":
        doc["tickers"] = ["BBB"]
    else:
        amended = {"form": "10-K/A", "filingDate": "2026-02-02", "reportDate": "2025-12-31",
                   "accessionNumber": "0000000001-26-000002", "primaryDocument": "amended.htm"}
        for key, value in amended.items():
            doc["filings"]["recent"][key].append(value)
    error = "sec-amendment-needs-review" if change == "amendment" else "sec-submission-identity"
    with pytest.raises(ValueError, match=f"^{error}$"):
        cli.latest_metadata("AAA", "0000000001", doc)


def run_cli(tmp_path, monkeypatch, capsys, *, mode):
    source = tmp_path / "source"
    source.mkdir()
    baseline = artifact([capture([])] if mode == "cached" else [])
    for name, value in (("member_map_auto_evidence.json", baseline),
                        ("universe_search.json", {"stocks": companies()[:1]})):
        (source / name).write_text(json.dumps(value), encoding="utf-8")
    original = (source / "member_map_auto_evidence.json").read_bytes()
    out = tmp_path / "capture"
    calls = []
    def fake_get(url, maximum=0):
        calls.append(url)
        if url == cli.TICKER_URL:
            return json.dumps({"0": {"ticker": "AAA", "cik_str": 1}}).encode()
        if "submissions" in url:
            doc = submission()
            if mode == "ragged":
                doc["filings"]["recent"]["reportDate"] = []
            return json.dumps(doc).encode()
        return html("<p>We manufacture components.</p>")
    monkeypatch.setattr(cli, "get_public", fake_get)
    argv = ["capture-sec-relationships.py", "--source-dir", str(source), "--output-dir", str(out)]
    if mode != "dry":
        argv.append("--fetch-public")
    monkeypatch.setattr(sys, "argv", argv)
    code = cli.main()
    summary = json.loads(capsys.readouterr().out)
    assert (source / "member_map_auto_evidence.json").read_bytes() == original
    assert summary["model_calls"] == 0 and summary["published"] is False
    return code, summary, calls, out


@pytest.mark.parametrize("mode,requests", [("dry", 0), ("cached", 2), ("nohit", 3)])
def test_cli_dry_cached_nohit_no_model_or_implicit_apply(tmp_path, monkeypatch, capsys, mode, requests):
    code, summary, calls, out = run_cli(tmp_path, monkeypatch, capsys, mode=mode)
    assert code == 0 and len(calls) == requests
    assert summary["public_gets"] == requests
    if mode == "dry":
        assert not out.exists()
    elif mode == "cached":
        assert summary["cached"] == 1 and summary["captured"] == 0
    else:
        value = json.loads((out / "member_map_auto_evidence.json").read_text())
        assert summary["captured"] == 1
        assert sec.index_sec_relationships(value["sec_filing_excerpts"], companies())["relations"] == []


def test_ragged_submission_is_rejected_without_cli_crash(tmp_path, monkeypatch, capsys):
    code, summary, calls, out = run_cli(tmp_path, monkeypatch, capsys, mode="ragged")
    assert code == 0 and summary["captured"] == 0
    assert summary["rows"][0]["status"] == "sec-submission-shape"
    assert len(calls) == 2 and (out / "manifest.json").is_file()


def test_cli_source_symlink_is_rejected(tmp_path, monkeypatch):
    target = tmp_path / "real.json"
    target.write_text(json.dumps(artifact()), encoding="utf-8")
    (tmp_path / "member_map_auto_evidence.json").symlink_to(target)
    monkeypatch.setattr(sys, "argv", ["capture-sec-relationships.py", "--source-dir", str(tmp_path),
                                     "--output-dir", str(tmp_path / "out")])
    with pytest.raises((ValueError, OSError)):
        cli.main()
