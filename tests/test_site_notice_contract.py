"""Site-wide notices: opt-in, migration compatibility and no auth expansion."""
import importlib.util
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace, ModuleType
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def editorial_module(monkeypatch):
    # Tests load handlers outside Vercel's api package; keep the deployed import contract.
    monkeypatch.setitem(sys.modules, "api.notice_editorial", load("notice_editorial_test", "vercel-api/api/notice_editorial.py"))


@pytest.fixture
def admin(monkeypatch):
    module = load("notice_admin_test", "vercel-api/api/admin.py")
    monkeypatch.setattr(module, "_svc_ready", lambda: True)
    monkeypatch.setattr(module, "_caller_identity", lambda _: {"id": "verified-admin"})
    monkeypatch.setattr(module, "headers_to_dict", lambda _: {})
    monkeypatch.setattr(module, "_audit", Mock())
    return module


def response(status, body):
    return SimpleNamespace(status_code=status, text=json.dumps(body), json=lambda: body)


def test_pin_does_not_promote_and_partial_update_preserves_fields(admin):
    assert admin._notice_payload({"pinned": True}) == {"pinned": True}
    assert admin._notice_payload({"site_wide": True, "created_by": "attacker"}) == {"site_wide": True}


@pytest.mark.parametrize("value", ["false", "true", 0, 1, None, [], {}])
def test_sitewide_requires_boolean(admin, value):
    with pytest.raises(ValueError):
        admin._notice_payload({"site_wide": value})


@pytest.mark.parametrize("link", ["javascript:alert(1)", "//evil.test", "/\\evil.test", "http://evil.test", "https://u:p@evil.test", "https://a.test/\nx", "x" * 501])
def test_reject_unsafe_links(admin, link):
    with pytest.raises(ValueError):
        admin._notice_payload({"link": link})


@pytest.mark.parametrize("link", ["", "/lab", "/community?tab=support", "https://example.com/news?a=1"])
def test_allow_links(admin, link):
    assert admin._notice_payload({"link": link})["link"] == link


def test_ready_even_with_no_notices(admin, monkeypatch):
    monkeypatch.setattr(admin.requests, "get", Mock(return_value=response(200, [])))
    result = admin.handle_notices(SimpleNamespace(path="/api/admin?type=notices"), "GET", {})
    assert result["_body"]["site_wide_ready"] is True


def test_old_schema_keeps_manager_available(admin, monkeypatch):
    calls = []
    def get(*args, **kwargs):
        calls.append(dict(kwargs["params"]))
        return response(400, {"code": "42703", "message": "site_wide missing"}) if len(calls) == 1 else response(200, [{"id": "old"}])
    monkeypatch.setattr(admin.requests, "get", get)
    result = admin.handle_notices(SimpleNamespace(path="/api/admin?type=notices"), "GET", {})
    assert result["_status"] == 200
    assert result["_body"]["items"] == [{"id": "old"}]
    assert result["_body"]["site_wide_ready"] is False
    assert "site_wide" not in calls[1]["select"]


def test_bad_payload_never_writes(admin, monkeypatch):
    post = Mock()
    monkeypatch.setattr(admin.requests, "post", post)
    result = admin.handle_notices(SimpleNamespace(), "POST", {"title": "test", "site_wide": "false"})
    assert result["_status"] == 400
    post.assert_not_called()


def test_create_stores_opt_in_and_verified_actor(admin, monkeypatch):
    post = Mock(return_value=response(201, [{"id": "new", "site_wide": True}]))
    monkeypatch.setattr(admin.requests, "post", post)
    result = admin.handle_notices(SimpleNamespace(), "POST", {"title": "Notice", "site_wide": True, "created_by": "forged"})
    assert result["_status"] == 201
    assert post.call_args.kwargs["json"]["created_by"] == "verified-admin"
    assert post.call_args.kwargs["json"]["site_wide"] is True


@pytest.fixture
def public(monkeypatch):
    sb = ModuleType("api.supabase_client")
    sb.is_configured = lambda: True
    sb.select = Mock(return_value=[])
    import api
    monkeypatch.setitem(sys.modules, "api.supabase_client", sb)
    monkeypatch.setattr(api, "supabase_client", sb, raising=False)
    return load("notice_public_test", "vercel-api/api/notices.py"), sb


def get_public(module, path):
    result = {}
    h = SimpleNamespace(path=path, headers={}, client_address=("127.0.0.1", 1), wfile=io.BytesIO())
    h.send_response = lambda status: result.update(status=status)
    h.send_header = lambda k, v: result.update({k: v})
    h.end_headers = lambda: None
    module.handler.do_GET(h)
    result["body"] = json.loads(h.wfile.getvalue())
    return result


def test_public_site_filter_precedes_limit_and_output_is_whitelisted(public):
    module, sb = public
    sb.select.return_value = [{"id": "n", "site_wide": True, "created_by": "private", "extra_secret": "hidden"}]
    result = get_public(module, "/api/notices?placement=site")
    params = sb.select.call_args.args[1]
    assert params["site_wide"] == "eq.true" and params["limit"] == "20"
    assert len(sb.select.call_args.args) == 2  # No user JWT/service-role argument.
    assert result["body"]["items"][0]["site_wide"] is True
    assert "private" not in json.dumps(result["body"])
    assert "extra_secret" not in json.dumps(result["body"])


def test_normal_archive_keeps_sitewide_rows(public):
    module, sb = public
    sb.select.return_value = [{"id": "n", "site_wide": True}, {"id": "old", "pinned": True}]
    result = get_public(module, "/api/notices")
    assert "site_wide" not in sb.select.call_args.args[1]
    assert [n["site_wide"] for n in result["body"]["items"]] == [True, False]


def test_direct_notice_lookup_retains_rls(public):
    module, sb = public
    notice_id = "00000000-0000-0000-0000-000000000001"
    assert get_public(module, "/api/notices?id=" + notice_id)["status"] == 200
    assert sb.select.call_args.args[1]["id"] == "eq." + notice_id
    assert len(sb.select.call_args.args) == 2


def test_invalid_notice_id_never_queries(public):
    module, sb = public
    assert get_public(module, "/api/notices?id=malformed")["status"] == 400
    sb.select.assert_not_called()


def test_public_network_error_not_misreported_as_empty_success(public):
    module, sb = public
    sb.select.side_effect = TimeoutError("fixture timeout")
    result = get_public(module, "/api/notices?placement=site")
    assert result["status"] == 503 and result["Cache-Control"] == "no-store"


def test_missing_sitewide_schema_fails_closed(public):
    module, sb = public
    exc = RuntimeError("fixture old schema")
    exc.response = SimpleNamespace(text='{"code":"42703","message":"site_wide missing"}')
    sb.select.side_effect = exc
    result = get_public(module, "/api/notices?placement=site")
    assert result["body"]["items"] == []
    assert result["body"]["migration_required"] == "038_notice_sitewide"


def test_migration_is_additive_and_no_promotion():
    sql = (ROOT / "supabase/migrations/038_notice_sitewide.sql").read_text()
    assert "DEFAULT false" in sql
    for statement in ("DROP ", "DELETE ", "UPDATE public.notices", "DISABLE ROW LEVEL"):
        assert statement not in sql.upper() if statement.isupper() else statement not in sql


def test_notice_artwork_payload_is_restricted_to_the_public_bucket(admin):
    prefix = admin._notice_image_prefix()
    assert admin._notice_payload({"thumbnail_theme": "report", "thumbnail_url": ""}) == {"thumbnail_theme": "report", "thumbnail_url": ""}
    for payload in [{"thumbnail_theme": "invented"}, {"thumbnail_theme": None}, {"thumbnail_url": "https://evil.test/a.png"}, {"thumbnail_url": "data:image/svg+xml,<svg/>"}, {"thumbnail_url": prefix + "../private.png"}]:
        with pytest.raises(ValueError):
            admin._notice_payload(payload)
    url = prefix + "a" * 64 + ".png"
    assert admin._notice_payload({"thumbnail_url": url})["thumbnail_url"] == url


def test_pre_artwork_schema_preserves_existing_notice_manager(admin, monkeypatch):
    replies = [response(400, {"code": "42703", "message": "thumbnail_theme missing"}), response(200, [{"id": "old"}])]
    monkeypatch.setattr(admin.requests, "get", Mock(side_effect=replies))
    result = admin.handle_notices(SimpleNamespace(path="/api/admin?type=notices"), "GET", {})
    assert result["_status"] == 200
    assert result["_body"]["artwork_ready"] is False
    assert result["_body"]["site_wide_ready"] is True
    assert result["_body"]["items"][0]["id"] == "old"


def sample_png(width=1, height=1):
    import struct, zlib
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\xff")) + chunk(b"IEND", b"")


def test_upload_rejects_invalid_images_without_storage_write(admin, monkeypatch):
    import base64
    post = Mock(); monkeypatch.setattr(admin.requests, "post", post)
    for raw in [b"<svg onload=\"evil()\"/>", sample_png()[:-1], sample_png() + b"extra", sample_png(1201), b"x" * 262145]:
        result = admin.handle_notices(SimpleNamespace(), "POST", {"action": "upload_thumbnail", "image_base64": base64.b64encode(raw).decode()})
        assert result["_status"] == 400
    post.assert_not_called()


def test_upload_uses_fixed_public_artwork_bucket_and_bounded_png(admin, monkeypatch):
    import base64, hashlib
    png = sample_png()
    post = Mock(return_value=response(200, {})); monkeypatch.setattr(admin.requests, "post", post)
    result = admin.handle_notices(SimpleNamespace(), "POST", {"action": "upload_thumbnail", "image_base64": base64.b64encode(png).decode(), "bucket": "private", "path": "bad"})
    assert result["_body"]["url"] == admin._notice_image_prefix() + hashlib.sha256(png).hexdigest() + ".png"
    assert "/notice-images/" in post.call_args.args[0]
    assert post.call_args.kwargs["headers"]["Content-Type"] == "image/png"
    assert post.call_args.kwargs["data"] == png


def test_public_artwork_passes_through_without_admin_fields(public):
    module, sb = public
    sb.select.return_value = [{"id": "n", "thumbnail_theme": "report", "thumbnail_url": "https://example.test/image.png", "created_by": "private"}]
    item = get_public(module, "/api/notices")["body"]["items"][0]
    assert item["thumbnail_theme"] == "report"
    assert item["thumbnail_url"].endswith("image.png")
    assert "created_by" not in item
