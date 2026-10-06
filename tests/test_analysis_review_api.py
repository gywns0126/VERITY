"""Private analysis read path: auth first, strict projection, no public fallback."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
from io import BytesIO
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("analysis_review_endpoint", ROOT / "vercel-api/api/analysis_review.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
NOW = datetime(2026, 10, 6, 0, tzinfo=timezone.utc)


def bundle():
    return {"schema": api.SCHEMA, "generated_at": "2026-10-05T12:00:00Z", "items": {"MSFT": {
        "ticker": "MSFT", "name": "Microsoft", "packet_id": "a" * 64,
        "facts_at": "2026-10-05T10:00:00Z", "prepared_at": "2026-10-05T11:00:00Z",
        "state": "reviewed", "section_total": 1,
        "sources": {"total": 1, "counts": {"in_bundle": 1},
                    "entries": [{"source": "sec", "group": "additional_section", "state": "in_bundle"}],
                    "scope": "representation, not fetch coverage", "limitations": []},
        "review": {"record_id": "analysis:" + "a" * 64, "verdict": "보류", "confidence": "low",
                   "reviewed_at": "2026-10-05T12:00:00Z", "valid_until": "2026-10-07T12:00:00Z",
                   "reasoning_brief": "Needs more evidence", "counterevidence": "Growth improved",
                   "change_conditions": ["Review filing"], "limitations": "No price confirmation",
                   "unresolved": ["price"],
                   "coverage": {"section_total": 1, "reviewed": 1, "not_used": 0,
                                "primary_supported_basis": 1, "basis_total": 1, "unresolved": True,
                                "verification": "reviewer_attestation_not_machine_proof"},
                   "evidence": [{"section_id": "s1", "claim": "revenue", "value": "100",
                                 "source_as_of": "2026-09-30", "excerpt": "Revenue 100",
                                 "url": "https://www.sec.gov/example", "source_kind": "primary",
                                 "status": "confirmed", "checked_at": "2026-10-05T11:30:00Z"}]}}}}


class Request:
    def __init__(self, path="/api/analysis_review?ticker=MSFT", headers=None):
        self.path, self.headers = path, headers or {}
        self.wfile, self.response_headers = BytesIO(), {}

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        self.response_headers[key] = value

    def end_headers(self):
        pass

    @property
    def body(self):
        return json.loads(self.wfile.getvalue())


@pytest.fixture
def authenticated(monkeypatch):
    monkeypatch.setattr(api, "_authorize", lambda headers: (True, "test"))


def test_auth_denies_before_private_download(monkeypatch):
    monkeypatch.setattr(api, "_authorize", lambda headers: (False, "unauthorized"))
    download = Mock(side_effect=AssertionError("must not read storage"))
    monkeypatch.setattr(api, "_download", download)
    request = Request()
    api.handler.do_GET(request)
    assert request.status == 401
    assert request.response_headers["Cache-Control"] == "no-store"
    download.assert_not_called()


@pytest.mark.parametrize("query", ["", "ticker=", "ticker=../secret", "ticker=A&ticker=B", "ticker=" + "A" * 21,
                                    "ticker=%20MSFT", "ticker=MSFT%0A", "ticker=한글"])
def test_invalid_ticker_never_downloads(authenticated, monkeypatch, query):
    download = Mock()
    monkeypatch.setattr(api, "_download", download)
    request = Request("/api/analysis_review?" + query)
    api.handler.do_GET(request)
    assert request.status == 400
    assert request.response_headers["Cache-Control"] == "no-store"
    download.assert_not_called()


def test_missing_storage_or_ticker_means_not_reviewed(authenticated, monkeypatch):
    for data in (None, dict(bundle(), items={})):
        monkeypatch.setattr(api, "_download", lambda: data)
        request = Request()
        api.handler.do_GET(request)
        assert request.status == 200
        assert request.body["state"] == "not_reviewed"
        assert request.body["orders_authorized"] is False
        assert request.response_headers["Cache-Control"] == "no-store"


def test_pending_is_not_older_review():
    data = bundle()
    data["items"]["MSFT"].update(state="awaiting_review", review=None)
    result = api.project(data, "MSFT", now=NOW)
    assert result["state"] == "awaiting_review" and result["review"] is None


def test_expiry_recomputed_at_request_time():
    data = bundle()
    assert api.project(data, "MSFT", now=NOW)["state"] == "reviewed"
    result = api.project(data, "MSFT", now=datetime(2026, 10, 8, tzinfo=timezone.utc))
    assert result["state"] == result["review"]["state"] == "review_expired"
    # A stale export state is not authoritative either.
    data["items"]["MSFT"]["state"] = "review_expired"
    assert api.project(data, "MSFT", now=NOW)["state"] == "reviewed"


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(schema="wrong"),
    lambda d: d["items"]["MSFT"].update(ticker="AAPL"),
    lambda d: d["items"]["MSFT"].update(review=None),
    lambda d: d["items"]["MSFT"]["review"].update(record_id="analysis:" + "b" * 64),
    lambda d: d["items"]["MSFT"]["review"].update(valid_until="bad"),
    lambda d: d["items"]["MSFT"]["review"].update(valid_until="2026-10-04T12:00:00Z"),
    lambda d: d["items"]["MSFT"]["sources"].update(total=2),
    lambda d: d["items"]["MSFT"]["review"]["coverage"].update(reviewed=2),
    lambda d: d["items"]["MSFT"]["review"]["evidence"][0].update(url="javascript:alert(1)"),
])
def test_malformed_projection_fails_closed(authenticated, monkeypatch, mutation):
    data = bundle()
    mutation(data)
    monkeypatch.setattr(api, "_download", lambda: data)
    request = Request()
    api.handler.do_GET(request)
    assert request.status == 503
    assert request.body == {"error": "analysis_review_unavailable"}
    assert request.response_headers["Cache-Control"] == "no-store"


def test_only_allowlisted_fields_returned():
    data = bundle()
    row = data["items"]["MSFT"]
    row["facts"] = {"account": "secret"}
    row["review"]["raw_account"] = "secret"
    row["sources"]["entries"][0]["raw"] = "secret"
    row["review"]["evidence"][0]["raw"] = "secret"
    result = api.project(data, "MSFT", now=NOW)
    assert "secret" not in json.dumps(result)


def test_storage_404_and_errors_no_public_fallback(monkeypatch):
    monkeypatch.setattr(api, "SUPABASE_URL", "https://private.example")
    monkeypatch.setattr(api, "SUPABASE_SERVICE_ROLE_KEY", "test-only")
    response = Mock(status_code=404, content=b"")
    get = Mock(return_value=response)
    monkeypatch.setattr(api.requests, "get", get)
    assert api._download() is None
    assert get.call_args.args == ("https://private.example/storage/v1/object/verity-reports/_operator/analysis_reviews.json",)
    assert get.call_args.kwargs["allow_redirects"] is False
    for status in (400, 401, 403, 302, 500):
        response.status_code = status
        with pytest.raises(ValueError):
            api._download()
    assert get.call_count == 6


def test_transport_failure_is_503(authenticated, monkeypatch):
    monkeypatch.setattr(api, "_download", Mock(side_effect=api.requests.Timeout()))
    request = Request()
    api.handler.do_GET(request)
    assert request.status == 503
    assert request.response_headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("value", [None, [], "not a projection"])
def test_storage_null_is_not_treated_as_missing(monkeypatch, value):
    monkeypatch.setattr(api, "SUPABASE_URL", "https://private.example")
    monkeypatch.setattr(api, "SUPABASE_SERVICE_ROLE_KEY", "test-only")
    response = Mock(status_code=200, content=b"null")
    response.json.return_value = value
    monkeypatch.setattr(api.requests, "get", Mock(return_value=response))
    with pytest.raises(ValueError):
        api._download()


def test_success_normalizes_case_and_does_not_mutate(authenticated, monkeypatch):
    data = bundle()
    before = deepcopy(data)
    monkeypatch.setattr(api, "_download", lambda: data)
    request = Request("/api/analysis_review?ticker=msft")
    api.handler.do_GET(request)
    assert request.status == 200 and request.body["ticker"] == "MSFT"
    assert request.response_headers["Cache-Control"] == "no-store"
    assert data == before
