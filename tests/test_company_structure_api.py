import hashlib
import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "company_structure_api_under_test", ROOT / "vercel-api/api/company_structure.py")
api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(api)

ISSUER = "KR:005930"
PAYLOAD = {"schema": api.PAYLOAD_SCHEMA,
           "observedAt": "2026-10-21T00:00:00Z",
           "companies": [{"id": ISSUER, "name": "Samsung Electronics", "ticker": "005930", "market": "KR"},
                         {"id": "KR:000660", "name": "SK hynix", "ticker": "000660", "market": "KR"}],
           "relations": [{"id": ISSUER + "|major-shareholder|KR:000660", "from": ISSUER,
                          "to": "KR:000660", "type": "major-shareholder", "label": "Major shareholder",
                          "asOf": "2026-06-30", "observedAt": "2026-10-21T00:00:00Z",
                          "status": "source-dated", "ownershipPct": None,
                          "directOwnership": "unspecified", "source_kind": "sec-exhibit-21",
                          "evidence": [{"title": "SEC filing",
                                        "url": "https://www.sec.gov/Archives/edgar/data/88000/000119312526104113/hkhc-ex21.htm",
                                        "asOf": "2026-07-02"}]}],
           "coverage": {"status": "source-checked", "sourceChecked": True,
                        "asOfMeaning": "Settlement period, not collection date",
                        "endpoints": {"hyslrSttus": {"status": "000"}}}}


def _bytes(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _manifest(entry=None):
    issuers = {ISSUER: {"ticker": "005930", "market": "KR", "name": "Samsung Electronics",
                        "status": "not-attempted"}}
    if entry:
        issuers[ISSUER].update(entry)
    return {"schema": api.INDEX_SCHEMA, "generatedAt": "2026-10-21T10:00:00Z",
            "coverage": {"KR": {"total": 1, "checked": 0},
                         "US": {"total": 0, "pending": 0}, "excluded": {"index": 5}},
            "issuers": issuers}


def _setup():
    api._MANIFEST_CACHE = None
    api._PAYLOAD_CACHE.clear()


def test_serves_hash_verified_payload_and_preserves_endpoint_coverage():
    _setup()
    raw = _bytes(PAYLOAD)
    digest = hashlib.sha256(raw).hexdigest()
    manifest = _bytes(_manifest({"status": "source-checked", "sha256": digest, "bytes": len(raw)}))
    seen = []

    def read(url, limit):
        seen.append((url, limit))
        return manifest if url == api.INDEX_URL else raw

    with patch.object(api, "_read_public_bytes", side_effect=read):
        status, body = api._dispatch("/api/company_structure?market=KR&ticker=005930")
    assert status == 200
    assert body["schema"] == api.PAYLOAD_SCHEMA
    assert body["relations"] == PAYLOAD["relations"]
    assert body["relations"][0]["directOwnership"] == "unspecified"
    assert body["relations"][0]["source_kind"] == "sec-exhibit-21"
    assert body["coverage"]["endpoints"] == PAYLOAD["coverage"]["endpoints"]
    assert body["coverage"]["asOfMeaning"] == PAYLOAD["coverage"]["asOfMeaning"]
    assert body["coverage"]["sourceStatus"] == "source-checked"
    assert body["coverage"]["requestedIssuer"] == ISSUER
    assert body["coverage"]["indexGeneratedAt"] == "2026-10-21T10:00:00Z"
    assert body["coverage"]["universeDenominator"] == {"total": 1, "byMarket": {"KR": 1, "US": 0}}
    assert body["coverage"]["manifestCoverage"] == _manifest()["coverage"]
    assert seen == [(api.INDEX_URL, api.INDEX_MAX_BYTES),
                    (api.PUBLIC_BASE + "company-structure/" + digest + ".json", api.PAYLOAD_MAX_BYTES)]


def test_registered_not_attempted_ticker_returns_catalogue_empty_shell():
    _setup()
    manifest = _bytes(_manifest({"status": "not-attempted"}))
    with patch.object(api, "_read_public_bytes", return_value=manifest) as read:
        status, body = api._dispatch("/api/company_structure?market=KR&ticker=005930")
    assert status == 200
    assert body["companies"] == [{"id": ISSUER, "name": "Samsung Electronics",
                                  "ticker": "005930", "market": "KR"}]
    assert body["relations"] == []
    assert body["coverage"]["sourceStatus"] == "not-attempted"
    assert body["coverage"]["status"] == "not-attempted"
    assert read.call_count == 1


def test_registered_legacy_only_without_payload_keeps_its_source_status():
    _setup()
    manifest = _bytes(_manifest({"status": "legacy-only"}))
    with patch.object(api, "_read_public_bytes", return_value=manifest):
        status, body = api._dispatch("/api/company_structure?market=KR&ticker=005930")
    assert status == 200 and body["relations"] == []
    assert body["coverage"]["status"] == body["coverage"]["sourceStatus"] == "legacy-only"


def test_unregistered_ticker_is_404():
    _setup()
    with patch.object(api, "_read_public_bytes", return_value=_bytes(_manifest())):
        status, body = api._dispatch("/api/company_structure?market=KR&ticker=000001")
    assert status == 404 and body["error"] == "issuer-not-found"


@pytest.mark.parametrize("path", [
    "/api/company_structure?market=KR&market=US&ticker=005930",
    "/api/company_structure?market=KR&ticker=005930&extra=1",
    "/api/company_structure?market=kr&ticker=005930",
    "/api/company_structure?market=KR&ticker=12345",
    "/api/company_structure?market=US&ticker=lower",
    "/api/company_structure/extra?market=KR&ticker=005930",
    "https://evil.example/api/company_structure?market=KR&ticker=005930",
])
def test_invalid_query_and_path_are_rejected_without_fetch(path):
    with patch.object(api, "_read_public_bytes", side_effect=AssertionError("must not fetch")):
        status, body = api._dispatch(path)
    assert status == 400 and body["error"] == "invalid-request"


def test_hash_or_byte_count_mismatch_returns_503():
    _setup()
    raw = _bytes(PAYLOAD)
    entry = {"status": "source-checked", "sha256": "0" * 64, "bytes": len(raw)}
    manifest = _bytes(_manifest(entry))
    with patch.object(api, "_read_public_bytes", side_effect=[manifest, raw]):
        status, body = api._dispatch("/api/company_structure?market=KR&ticker=005930")
    assert status == 503 and body["error"] == "company-structure-unavailable"


def test_payload_url_is_derived_from_validated_digest_only():
    _setup()
    raw = _bytes(PAYLOAD)
    digest = hashlib.sha256(raw).hexdigest()
    doc = _manifest({"status": "source-checked", "sha256": digest, "bytes": len(raw),
                     "url": "https://evil.example/x"})
    calls = []

    def read(url, _limit):
        calls.append(url)
        return _bytes(doc) if url == api.INDEX_URL else raw

    with patch.object(api, "_read_public_bytes", side_effect=read):
        status, _ = api._dispatch("/api/company_structure?market=KR&ticker=005930")
    assert status == 200
    assert calls == [api.INDEX_URL, api.PUBLIC_BASE + "company-structure/" + digest + ".json"]


def test_unallowlisted_evidence_url_fails_closed():
    _setup()
    malicious = json.loads(_bytes(PAYLOAD))
    malicious["relations"][0]["evidence"][0]["url"] = "https://attacker.example/fake"
    raw = _bytes(malicious)
    digest = hashlib.sha256(raw).hexdigest()
    manifest = _bytes(_manifest({"status": "source-checked", "sha256": digest, "bytes": len(raw)}))
    with patch.object(api, "_read_public_bytes", side_effect=[manifest, raw]):
        status, body = api._dispatch("/api/company_structure?market=KR&ticker=005930")
    assert status == 503 and body["error"] == "company-structure-unavailable"


@pytest.mark.parametrize("location", ["top", "coverage", "relation"])
def test_unallowlisted_source_url_fields_are_rejected(location):
    _setup()
    doc = json.loads(_bytes(PAYLOAD))
    if location == "top":
        doc["sourceURL"] = "https://attacker.example/x"
    elif location == "coverage":
        doc["coverage"]["sourceURL"] = "https://attacker.example/x"
    else:
        doc["relations"][0]["sourceURL"] = "https://attacker.example/x"
    raw = _bytes(doc)
    digest = hashlib.sha256(raw).hexdigest()
    manifest = _bytes(_manifest({"status": "source-checked", "sha256": digest, "bytes": len(raw)}))
    with patch.object(api, "_read_public_bytes", side_effect=[manifest, raw]):
        status, body = api._dispatch("/api/company_structure?market=KR&ticker=005930")
    assert status == 503 and body["error"] == "company-structure-unavailable"


def test_warm_payload_cache_rechecks_requested_issuer_binding():
    _setup()
    raw = _bytes(PAYLOAD)
    digest = hashlib.sha256(raw).hexdigest()
    second = "KR:000001"
    doc = _manifest({"status": "source-checked", "sha256": digest, "bytes": len(raw)})
    doc["coverage"]["KR"]["total"] = 2
    doc["issuers"][second] = {"ticker": "000001", "market": "KR", "name": "Other issuer",
                              "status": "source-checked", "sha256": digest, "bytes": len(raw)}
    manifest = _bytes(doc)
    with patch.object(api, "_read_public_bytes", side_effect=[manifest, raw]):
        assert api._dispatch("/api/company_structure?market=KR&ticker=005930")[0] == 200
        status, body = api._dispatch("/api/company_structure?market=KR&ticker=000001")
    assert status == 503 and body["error"] == "company-structure-unavailable"


def test_us_shared_payload_contains_and_serves_all_cik_aliases_from_cache():
    _setup()
    ids = ["US:ABC", "US:ABCD"]
    us_payload = {"schema": api.PAYLOAD_SCHEMA,
                  "companies": [{"id": item, "name": item, "ticker": item[3:], "market": "US"} for item in ids],
                  "relations": [],
                  "coverage": {"status": "source-checked", "securityIds": ids}}
    raw = _bytes(us_payload)
    digest = hashlib.sha256(raw).hexdigest()
    entry = {"market": "US", "name": "Issuer", "status": "source-checked",
             "sha256": digest, "bytes": len(raw)}
    index = {"schema": api.INDEX_SCHEMA, "generatedAt": "2026-10-21T10:00:00Z",
             "coverage": {"KR": {"total": 0}, "US": {"total": 2}},
             "issuers": {ids[0]: {**entry, "ticker": "ABC"}, ids[1]: {**entry, "ticker": "ABCD"}}}

    def read(url, _limit):
        return _bytes(index) if url == api.INDEX_URL else raw

    with patch.object(api, "_read_public_bytes", side_effect=read) as fetch:
        assert api._dispatch("/api/company_structure?market=US&ticker=ABC")[0] == 200
        status, body = api._dispatch("/api/company_structure?market=US&ticker=ABCD")
    assert status == 200 and body["coverage"]["requestedIssuer"] == "US:ABCD"
    assert [row["id"] for row in body["companies"]] == ids
    assert fetch.call_count == 2


def test_us_payload_must_match_manifest_alias_group_exactly():
    _setup()
    raw_doc = {"schema": api.PAYLOAD_SCHEMA,
               "companies": [{"id": "US:ABC", "name": "ABC", "ticker": "ABC", "market": "US"}],
               "relations": [], "coverage": {"status": "source-checked", "securityIds": ["US:ABC"]}}
    raw = _bytes(raw_doc)
    digest = hashlib.sha256(raw).hexdigest()
    entries = {key: {"ticker": key[3:], "market": "US", "name": key,
                     "status": "source-checked", "sha256": digest, "bytes": len(raw)}
               for key in ("US:ABC", "US:ABCD")}
    index = {"schema": api.INDEX_SCHEMA, "generatedAt": "2026-10-21T10:00:00Z",
             "coverage": {"KR": {"total": 0}, "US": {"total": 2}}, "issuers": entries}
    with patch.object(api, "_read_public_bytes", side_effect=[_bytes(index), raw]):
        status, body = api._dispatch("/api/company_structure?market=US&ticker=ABC")
    assert status == 503 and body["error"] == "company-structure-unavailable"


def test_served_documents_are_copies_not_mutations_of_process_cache():
    _setup()
    raw = _bytes(PAYLOAD)
    digest = hashlib.sha256(raw).hexdigest()
    manifest = _bytes(_manifest({"status": "source-checked", "sha256": digest, "bytes": len(raw)}))
    with patch.object(api, "_read_public_bytes", side_effect=[manifest, raw]):
        first_status, first = api._dispatch("/api/company_structure?market=KR&ticker=005930")
    first["companies"][0]["name"] = "mutated"
    first["coverage"]["manifestCoverage"]["KR"]["total"] = 999
    second_status, second = api._dispatch("/api/company_structure?market=KR&ticker=005930")
    assert first_status == second_status == 200
    assert second["companies"][0]["name"] == "Samsung Electronics"
    assert second["coverage"]["manifestCoverage"]["KR"]["total"] == 1


def test_unknown_manifest_source_status_is_not_promoted_to_normal():
    _setup()
    raw = _bytes(_manifest({"status": "success"}))
    with patch.object(api, "_read_public_bytes", return_value=raw):
        status, body = api._dispatch("/api/company_structure?market=KR&ticker=005930")
    assert status == 503 and body["error"] == "company-structure-unavailable"


@pytest.mark.parametrize("raw", [
    b'{"schema":"alphanest-company-structure-index-v1","schema":"x"}',
    b'{"schema":"alphanest-company-structure-index-v1","value":NaN}',
])
def test_duplicate_keys_and_nonfinite_numbers_fail_closed(raw):
    _setup()
    with patch.object(api, "_read_public_bytes", return_value=raw):
        status, body = api._dispatch("/api/company_structure?market=KR&ticker=005930")
    assert status == 503 and body["error"] == "company-structure-unavailable"


@pytest.mark.parametrize("raw", [
    b'{"schema":"alphanest-company-structure-v1","schema":"x"}',
    b'{"schema":"alphanest-company-structure-v1","value":NaN}',
])
def test_payload_duplicate_keys_and_nonfinite_numbers_fail_closed(raw):
    _setup()
    digest = hashlib.sha256(raw).hexdigest()
    manifest = _bytes(_manifest({"status": "source-checked", "sha256": digest, "bytes": len(raw)}))
    with patch.object(api, "_read_public_bytes", side_effect=[manifest, raw]):
        status, body = api._dispatch("/api/company_structure?market=KR&ticker=005930")
    assert status == 503 and body["error"] == "company-structure-unavailable"


def test_expired_manifest_failure_does_not_promote_retained_data_as_current():
    _setup()
    manifest = _bytes(_manifest({"status": "not-attempted"}))
    with patch.object(api, "_read_public_bytes", return_value=manifest):
        assert api._dispatch("/api/company_structure?market=KR&ticker=005930")[0] == 200
    retained = api._MANIFEST_CACHE[1]
    api._MANIFEST_CACHE = (0.0, retained)
    with patch.object(api, "_read_public_bytes", side_effect=OSError("offline")):
        status, body = api._dispatch("/api/company_structure?market=KR&ticker=005930")
    assert status == 503 and body["error"] == "company-structure-unavailable"
    assert api._MANIFEST_CACHE is not None


def test_post_is_not_supported():
    request = object.__new__(api.handler)
    request.wfile = io.BytesIO()
    sent = []
    request.send_response = lambda status: sent.append(("status", status))
    request.send_header = lambda key, value: sent.append((key, value))
    request.end_headers = lambda: None
    request.do_POST()
    assert ("status", 405) in sent
    assert ("Allow", "GET") in sent
