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


@pytest.mark.parametrize("query", ["view=queue", "view=unknown&ticker=MSFT"])
def test_queue_auth_first(monkeypatch, query):
    monkeypatch.setattr(api, "_authorize", lambda headers: (False, "unauthorized"))
    download = Mock(side_effect=AssertionError("must not read storage"))
    monkeypatch.setattr(api, "_download", download)
    request = Request("/api/analysis_review?" + query)
    api.handler.do_GET(request)
    assert request.status == 401
    assert request.response_headers["Cache-Control"] == "no-store"
    download.assert_not_called()


@pytest.mark.parametrize("query", ["view=", "view=other", "view=queue&view=queue",
                                    "view=queue&ticker=MSFT", "view=queue&ticker=",
                                    "view=queue&limit=1"])
def test_invalid_queue_query_never_downloads(authenticated, monkeypatch, query):
    download = Mock()
    monkeypatch.setattr(api, "_download", download)
    request = Request("/api/analysis_review?" + query)
    api.handler.do_GET(request)
    assert request.status == 400
    assert request.body == {"error": "invalid_view"}
    assert request.response_headers["Cache-Control"] == "no-store"
    download.assert_not_called()


@pytest.mark.parametrize("missing", [True, False])
def test_queue_empty_and_missing_storage(authenticated, monkeypatch, missing):
    data = None if missing else dict(bundle(), items={})
    monkeypatch.setattr(api, "_download", lambda: data)
    request = Request("/api/analysis_review?view=queue")
    api.handler.do_GET(request)
    assert request.status == 200
    assert request.body == {
        "schema": "analysis-review-queue-v1",
        "generated_at": None if missing else data["generated_at"],
        "total": 0, "counts": {"awaiting_review": 0, "review_expired": 0, "reviewed": 0},
        "items": [], "orders_authorized": False, "monitoring_active": False,
    }
    assert request.response_headers["Cache-Control"] == "no-store"


def test_queue_order_counts_allowlist_and_single_clock(monkeypatch):
    data = bundle()
    template = data["items"].pop("MSFT")
    for ticker in ("Z", "PENDING_B", "OLD", "PENDING_A", "LIVE"):
        # Tickers use only the same canonical alphabet as the ticker endpoint.
        ticker = ticker.replace("_", "-")
        row = deepcopy(template)
        row.update(ticker=ticker, name=ticker, raw_account="secret")
        row["review"]["facts"] = {"account": "secret"}
        if ticker.startswith("PENDING"):
            row.update(state="awaiting_review", review=None)
        elif ticker in ("Z", "OLD"):
            row["review"]["valid_until"] = NOW.isoformat()
        else:
            row["state"] = "review_expired"  # Persisted state is not trusted.
        if ticker == "OLD":
            row["prepared_at"] = "2026-10-05T10:30:00Z"
        data["items"][ticker] = row
    before = deepcopy(data)
    clock = Mock()
    clock.now.return_value = NOW
    clock.fromisoformat = datetime.fromisoformat
    monkeypatch.setattr(api, "datetime", clock)
    result = api.project_queue(data)
    clock.now.assert_called_once_with(timezone.utc)
    assert [s["ticker"] for s in result["items"]] == ["OLD", "Z", "PENDING-A", "PENDING-B", "LIVE"]
    assert result["total"] == 5
    assert result["counts"] == {"awaiting_review": 2, "review_expired": 2, "reviewed": 1}
    keys = {"ticker", "name", "state", "prepared_at", "reviewed_at", "valid_until", "verdict", "confidence"}
    assert all(set(row) == keys for row in result["items"])
    assert all(result["items"][2][key] is None for key in ("reviewed_at", "valid_until", "verdict", "confidence"))
    assert "secret" not in json.dumps(result)
    assert data == before


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(schema="bad"),
    lambda d: d.update(generated_at="bad"),
    lambda d: d.update(items=[]),
    lambda d: d["items"].update(BAD={}),
    lambda d: d["items"].update({"../secret": deepcopy(d["items"]["MSFT"])}),
    lambda d: d["items"]["MSFT"].update(ticker="AAPL"),
    lambda d: d["items"]["MSFT"]["review"].update(valid_until="bad"),
    lambda d: d["items"]["MSFT"]["sources"].update(total=9),
])
def test_queue_any_malformed_row_fails_whole_response(authenticated, monkeypatch, mutation):
    data = bundle()
    mutation(data)
    monkeypatch.setattr(api, "_download", lambda: data)
    request = Request("/api/analysis_review?view=queue")
    api.handler.do_GET(request)
    assert request.status == 503
    assert request.body == {"error": "analysis_review_unavailable"}
    assert request.response_headers["Cache-Control"] == "no-store"


def test_queue_transport_failure_is_not_empty_queue(authenticated, monkeypatch):
    monkeypatch.setattr(api, "_download", Mock(side_effect=api.requests.Timeout()))
    request = Request("/api/analysis_review?view=queue")
    api.handler.do_GET(request)
    assert request.status == 503
    assert request.response_headers["Cache-Control"] == "no-store"


def test_queue_handler_uses_one_download_and_runtime_expiry(authenticated, monkeypatch):
    data = bundle()
    download = Mock(return_value=data)
    monkeypatch.setattr(api, "_download", download)
    clock = Mock()
    clock.now.return_value = datetime(2026, 10, 8, tzinfo=timezone.utc)
    clock.fromisoformat = datetime.fromisoformat
    monkeypatch.setattr(api, "datetime", clock)
    request = Request("/api/analysis_review?view=queue")
    api.handler.do_GET(request)
    assert request.status == 200
    assert request.body["items"][0]["state"] == "review_expired"
    assert request.body["counts"]["review_expired"] == request.body["total"] == 1
    assert request.body["schema"] == "analysis-review-queue-v1"
    assert request.response_headers["Cache-Control"] == "no-store"
    download.assert_called_once_with()
    clock.now.assert_called_once_with(timezone.utc)
