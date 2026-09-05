from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "vercel-api" / "api" / "support.py"
MIGRATION = ROOT / "supabase" / "migrations" / "037_community_support.sql"
COMMUNITY = ROOT / "framer-components" / "public-probe" / "PublicCommunityPage.tsx"
ADMIN = ROOT / "framer-components" / "pages" / "admin" / "NoticeAdminCard.tsx"


def _load_support():
    fake = types.ModuleType("api.supabase_client")
    fake.is_configured = lambda: True
    fake.verify_jwt = lambda _token: "user-1"
    fake.select = lambda *_args, **_kwargs: []
    fake.insert = lambda _table, data, **_kwargs: {"id": "s1", **data}
    fake.delete = lambda *_args, **_kwargs: None
    api_pkg = sys.modules.setdefault("api", types.ModuleType("api"))
    setattr(api_pkg, "supabase_client", fake)
    sys.modules["api.supabase_client"] = fake
    spec = importlib.util.spec_from_file_location("community_support_api", API)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_new_payload_forces_feedback_private_and_ignores_admin_fields():
    support = _load_support()
    payload, error = support._new_payload(
        "user-1",
        {
            "kind": "feedback",
            "title": "기능 의견",
            "body": "이 기능이 필요해요",
            "publish_consent": True,
            "status": "answered",
            "answer": "client answer",
            "hidden": True,
            "user_id": "other-user",
        },
    )
    assert error is None
    assert payload == {
        "user_id": "user-1",
        "kind": "feedback",
        "title": "기능 의견",
        "body": "이 기능이 필요해요",
        "publish_consent": False,
        "status": "open",
    }


def test_public_item_has_no_identity_or_admin_fields():
    support = _load_support()
    item = support._public_item(
        {
            "id": "s1",
            "user_id": "secret-user",
            "title": "질문",
            "body": "내용",
            "answer": "답변",
            "answered_at": "2026-09-05T00:00:00Z",
            "created_at": "2026-09-04T00:00:00Z",
            "hidden": False,
        }
    )
    assert set(item) == {"id", "title", "body", "answer", "answered_at", "created_at"}


def test_migration_enforces_private_feedback_and_answered_public_rls():
    sql = MIGRATION.read_text()
    assert "community_support_feedback_private" in sql
    assert "kind = 'question' OR publish_consent = false" in sql
    assert "cs_select_public_answered" in sql
    assert "status = 'answered'" in sql
    assert "UPDATE 정책 없음" in sql
    assert "DROP POLICY" not in sql
    assert "DROP TRIGGER" not in sql


def test_framer_surfaces_declare_three_main_tabs_and_both_support_consumers():
    community = COMMUNITY.read_text()
    admin = ADMIN.read_text()
    assert '"커뮤니티"' in community
    assert '"공지·Q&A"' in community
    assert '"내 관점"' in community
    assert "/api/support" in community
    assert "/api/thesis" in community
    assert "/api/support?admin=1" in admin
