"""Reuse the existing auth fixture; no member-state or real network access."""
import importlib.util
import sys
from unittest.mock import Mock, call
import pytest

_fixture_path = __import__('pathlib').Path(__file__).with_name('test_member_map_analysis.py')
_spec = importlib.util.spec_from_file_location('company_snapshot_endpoint_fixture', _fixture_path)
_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture)
modules, _request, API_DIR = _fixture.modules, _fixture._request, _fixture.API_DIR


@pytest.fixture
def candidate(modules, monkeypatch):
    _, sb = modules
    spec = importlib.util.spec_from_file_location("api.member_map_company_snapshot", API_DIR / "member_map_company_snapshot.py")
    endpoint = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, endpoint)
    spec.loader.exec_module(endpoint)
    endpoint.read_company_snapshot = Mock(return_value={"schema": "alphaconsole-portfolio-v1", "companies": []})
    return endpoint, sb


@pytest.mark.parametrize("token", [None, "bad-token"])
def test_authentication_precedes_any_public_read(candidate, token):
    endpoint, sb = candidate
    status, headers, body = endpoint.snapshot_request(_request(token, {"positions": [{"market": "KR", "ticker": "001111"}]}))
    assert status == 401
    endpoint.read_company_snapshot.assert_not_called()
    sb.select.assert_not_called()


@pytest.mark.parametrize("positions", [[], [{"market": "KR", "ticker": "001111", "memo": "private"}],
    [{"market": "US", "ticker": "../private"}], [{"market": "KR", "ticker": "001111"}] * 31])
def test_identifier_only_validation_before_any_source_read(candidate, positions):
    endpoint, sb = candidate
    status, _, _ = endpoint.snapshot_request(_request("jwt-a", {"positions": positions}))
    assert status == 400
    endpoint.read_company_snapshot.assert_not_called()
    sb.select.assert_not_called()


def test_only_validated_identifiers_reach_public_reader_and_response_is_private(candidate):
    endpoint, sb = candidate
    positions = [{"market": "KR", "ticker": "001111"}]
    for token in ("jwt-a", "jwt-b"):
        status, headers, body = endpoint.snapshot_request(_request(token, {"positions": positions}))
        assert status == 200
        assert headers["Cache-Control"].startswith("private, no-store")
        assert headers["Vercel-CDN-Cache-Control"] == "no-store"
    assert endpoint.read_company_snapshot.call_args_list == [call(positions), call(positions)]
    sb.select.assert_not_called()


def test_corrupt_snapshot_fails_closed_without_raw_exception(candidate):
    endpoint, sb = candidate
    endpoint.read_company_snapshot.side_effect = ValueError("secret-like input must not leak")
    status, _, body = endpoint.snapshot_request(_request("jwt-a", {"positions": [{"market": "KR", "ticker": "001111"}]}))
    assert status == 503 and body == {"error": "company_snapshot_unavailable"}
    sb.select.assert_not_called()


def test_disallowed_origin_never_authenticates_or_fetches(candidate):
    endpoint, sb = candidate
    status, _, body = endpoint.snapshot_request(_request("jwt-a", {"positions": []}, origin="https://evil.test"))
    assert status == 403
    sb.verify_jwt.assert_not_called()
    endpoint.read_company_snapshot.assert_not_called()


def test_full_claims_are_opt_in_prepared_public_rows_and_default_bytes_unchanged(modules, monkeypatch):
    endpoint, sb = modules
    documents = _fixture._documents()
    documents["stock_report_public.json"] = {"stocks": {"005930": {"facts": [
        {"metric": "revenue", "value": 123, "unit": "KRW", "as_of": "2025", "source": "DART"}]}}}
    monkeypatch.setattr(endpoint, "fetch_public_sources", Mock(return_value=_fixture._bundle(documents)))
    positions = [{"market": "KR", "ticker": "005930"}]
    ordinary = endpoint.analyze_request(_request("jwt-a", {"positions": positions}))
    request = _request("jwt-a", {"positions": positions})
    request.path = "/api/member_map_analysis?core_claims=1"
    status, headers, actual = endpoint.analyze_request(request)
    claims = actual["_meta"].pop("core_claims")
    assert status == ordinary[0] == 200
    assert claims["status"] == "ready" and len(claims["companies"]["KR:005930"]) == 1
    assert endpoint._encode_result((status, headers, actual))[2] == endpoint._encode_result(ordinary)[2]
    sb.select.assert_not_called()
