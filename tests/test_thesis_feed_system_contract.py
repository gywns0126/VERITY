import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "vercel-api" / "api" / "thesis_feed.py"


def _load_feed():
    fake = types.ModuleType("api.supabase_client")
    fake.is_configured = lambda: True
    fake.verify_jwt = lambda _token: None
    fake.select = lambda *_args, **_kwargs: []
    api_pkg = sys.modules.setdefault("api", types.ModuleType("api"))
    setattr(api_pkg, "supabase_client", fake)
    sys.modules["api.supabase_client"] = fake
    spec = importlib.util.spec_from_file_location("thesis_feed_system_contract", API)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_system_item_has_explicit_identity_and_source_clock():
    feed = _load_feed()
    row = {
        "id": "s1",
        "user_id": None,
        "ticker": "005930",
        "stance": "watch",
        "note": "[알파콘솔 시스템 · 공개 관찰 기록]\n확인한 사실",
        "created_at": "2026-09-22T12:00:00Z",
        "author_kind": "system",
        "system_label": "알파콘솔 시스템",
        "data_as_of": "2026-09-22T00:00:00Z",
        "published_at": "2026-09-22T12:00:00Z",
        "source_url": "https://dart.fss.or.kr/example",
        "source_title": "분기보고서",
        "content_version": 1,
    }
    item = feed._public_feed_item(row, {}, "viewer-1", {}, set())
    assert item["nickname"] == "알파네스트 관찰 노트"
    assert item["note"].startswith("[알파네스트 관찰 노트]")
    assert "알파콘솔 시스템" not in item["note"]
    assert item["author_kind"] == "system"
    assert item["system_generated"] is True
    assert item["mine"] is False
    assert item["data_as_of"] == "2026-09-22T00:00:00Z"
    assert item["source_url"].startswith("https://dart.fss.or.kr/")


def test_legacy_user_item_keeps_profile_identity():
    feed = _load_feed()
    row = {"id": "u1", "user_id": "viewer-1", "ticker": "AAPL", "stance": "bull", "note": "내 관점"}
    item = feed._public_feed_item(row, {"viewer-1": {"nickname": "사용자", "avatar": "a.png"}}, "viewer-1", {"u1": 2}, {"u1"})
    assert item["nickname"] == "사용자"
    assert item["author_kind"] == "user"
    assert item["system_generated"] is False
    assert item["mine"] is True
    assert item["likes"] == 2
    assert item["liked"] is True
