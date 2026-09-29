"""Read-only content contract: real authored snapshot + offline HTTP/MCP adapters."""
import importlib.util
import io
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vercel-api"))
import content_site as site
import content_mcp as mcp
from content_public import PublicSourceError


def test_snapshot_inventory_and_full_detail():
    doc = json.loads((ROOT / "vercel-api/education_content.json").read_text())
    assert len(doc["lessons"]) == 8 and len(doc["guides"]) == 16
    for source in ("lessons", "guides"):
        listing = site.load_site({"source": source, "limit": 20})
        assert listing["total_available"] == len(doc[source])
        assert listing["publication_status"] == "editor_saved_snapshot"
        assert listing["content_revision"] == doc["content_revision"]
        for row in doc[source]:
            detail = site.load_site({"source": source, "id": row["id"]})["items"][0]
            assert all(detail[key] == value for key, value in row.items())
            assert len(detail["steps"]) == 3
            if source == "guides":
                assert detail["tutorial"] == doc["tutorials"][row["id"]]
            else:
                assert detail["sources"] and detail["limit"]
    assert site.load_site({"source": "guides"})["next_offset"] == 10
    assert len(site.load_site({"source": "guides", "offset": 10})["items"]) == 6
    assert site.load_site({"source": "lessons", "id": "unknown"})["items"] == []


@pytest.mark.parametrize("args", [
    {}, {"source": "admin"}, {"source": "lessons", "url": "https://evil.test"},
    {"source": "lessons", "limit": True}, {"source": "guides", "offset": -1},
    {"source": "lessons", "limit": 21}, {"source": "lessons", "id": "../secret"},
    {"source": "guides", "id": "home", "offset": 0}, {"source": "notices", "id": "bad"},
])
def test_reject_before_fetch(args):
    fetch = Mock()
    with pytest.raises(ValueError):
        site.load_site(args, notice_fn=fetch)
    fetch.assert_not_called()


def test_notices_public_whitelist_and_expiry():
    now = datetime(2026, 9, 29, tzinfo=timezone.utc)
    base = {"id": "00000000-0000-0000-0000-000000000001", "title": "공지", "body": "원문", "created_by": "private", "email": "private"}
    rows = [base, {**base, "is_active": False}, {**base, "ends_at": now.isoformat()},
            {**base, "starts_at": "2026-10-01T00:00:00Z"}, {**base, "ends_at": "invalid"}]
    fetch = Mock(return_value={"items": rows})
    result = site.load_site({"source": "notices"}, notice_fn=fetch, now=now)
    assert len(result["items"]) == 1
    assert "created_by" not in result["items"][0] and "email" not in result["items"][0]
    assert result["items"][0]["body"] == "원문"
    fetch.assert_called_once_with(None)


@pytest.mark.parametrize("payload", [{"items": [], "error": "failed"}, {"items": [], "migration_required": "pending"}, {}])
def test_source_failure_is_not_empty_success(payload):
    with pytest.raises(PublicSourceError):
        site.load_site({"source": "notices"}, notice_fn=lambda _: payload)


def http(path, method="do_GET"):
    spec = importlib.util.spec_from_file_location("education_http", ROOT / "vercel-api/api/education.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    handler = module.handler.__new__(module.handler)
    handler.path = path
    handler.wfile = io.BytesIO()
    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock()
    getattr(handler, method)()
    return handler.send_response.call_args.args[0], json.loads(handler.wfile.getvalue())


def test_public_http_reads_and_rejects_writes():
    assert http("/api/education")[1]["total_available"] == 8
    assert http("/api/education?source=guides&id=home")[1]["items"][0]["tutorial"]
    for method in ("do_POST", "do_PUT", "do_PATCH", "do_DELETE"):
        assert http("/api/education", method)[0] == 405


@pytest.mark.parametrize("query", ["source=notices", "id=home&id=home", "limit=", "source=guides&limit=99", "url=https://evil.test", "offset=-1", "source="])
def test_bad_http_queries(query):
    assert http("/api/education?" + query)[0] == 400


def test_mcp_auth_before_new_content_and_error_handling():
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "get_alphanest_content", "arguments": {"source": "lessons", "id": "basics"}}}).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    read = Mock()
    with pytest.raises(mcp.ServiceError):
        mcp.process_request("POST", headers, body, authorize_fn=Mock(side_effect=mcp.ServiceError(401, "denied")), site_fn=read)
    read.assert_not_called()
    status, response = mcp.process_request("POST", headers, body, authorize_fn=lambda _: None)
    assert status == 200 and response["result"]["structuredContent"]["items"][0]["id"] == "basics"
    _, response = mcp.process_request("POST", headers, body, authorize_fn=lambda _: None,
                                      site_fn=Mock(side_effect=PublicSourceError("failed")))
    assert response["result"]["isError"] is True


def test_global_cors_covers_readonly_endpoint():
    config = json.loads((ROOT / "vercel-api/vercel.json").read_text())
    import re
    rule = next(row for row in config["headers"] if re.fullmatch(row["source"], "/api/education"))
    assert {row["key"]: row["value"] for row in rule["headers"]}["Access-Control-Allow-Origin"] == "*"
