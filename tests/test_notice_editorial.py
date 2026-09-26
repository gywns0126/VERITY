"""Editorial dates must not rewrite audit time or promote notices implicitly."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from tests.test_site_notice_contract import admin, public, editorial_module, get_public, response


def test_display_date_is_independent_and_partial_edit_preserves_metadata(admin):
    assert admin._notice_payload({"display_date": "2026-09-14", "created_at": "2026-09-14", "updated_at": "2026-09-14"}) == {"display_date": "2026-09-14"}
    assert admin._notice_payload({"title": "changed"}) == {"title": "changed"}
    assert admin._notice_payload({"display_date": ""}) == {"display_date": None}


@pytest.mark.parametrize("payload", [
    {"display_date": "2026-02-30"}, {"display_date": "2026-09-14T00:00:00Z"},
    {"home_visible": "false"}, {"related_tickers": ["AAPL),is_active.eq.false"]},
    {"related_tickers": "AAPL"}, {"related_topics": ["invented"]},
])
def test_invalid_metadata_never_reaches_a_write(admin, monkeypatch, payload):
    post = Mock()
    monkeypatch.setattr(admin.requests, "post", post)
    result = admin.handle_notices(SimpleNamespace(), "POST", {"title": "Notice", **payload})
    assert result["_status"] == 400
    post.assert_not_called()


def test_old_editorial_schema_does_not_break_admin(admin, monkeypatch):
    replies = [response(400, {"code": "42703", "message": "display_date missing"}), response(200, [{"id": "existing"}])]
    monkeypatch.setattr(admin.requests, "get", Mock(side_effect=replies))
    result = admin.handle_notices(SimpleNamespace(path="/api/admin?type=notices"), "GET", {})
    assert result["_status"] == 200
    assert result["_body"]["editorial_ready"] is False
    assert result["_body"]["items"] == [{"id": "existing"}]


def test_public_home_filter_runs_before_limit_and_uses_display_date(public):
    module, sb = public
    sb.select.return_value = [{"id": "notice", "display_date": "2026-09-14", "created_at": "2026-09-22T00:00:00Z", "home_visible": True, "created_by": "private"}]
    result = get_public(module, "/api/notices?placement=home")
    params = sb.select.call_args.args[1]
    assert params["home_visible"] == "eq.true" and params["limit"] == "2"
    assert params["order"].startswith("display_date.desc")
    item = result["body"]["items"][0]
    assert item["created_at"] != item["display_date"] and "created_by" not in item


def test_related_filter_preserves_anon_rls(public):
    module, sb = public
    assert get_public(module, "/api/notices?placement=related&ticker=aapl&topics=13f,report")["status"] == 200
    assert sb.select.call_args.args[1]["or"] == "(related_tickers.cs.{AAPL},related_topics.ov.{13f,report})"
    assert len(sb.select.call_args.args) == 2
    sb.select.reset_mock()
    assert get_public(module, "/api/notices?placement=related&ticker=AAPL%29%2Cis_active.eq.false")["status"] == 400
    sb.select.assert_not_called()
