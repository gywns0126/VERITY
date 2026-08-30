"""누적형 관리자 목록이 전체를 한 번에 렌더링하지 않는 계약."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADMIN_API = ROOT / "vercel-api" / "api" / "admin.py"
ADMIN_UI = ROOT / "framer-components" / "pages" / "admin"


def test_audit_api_returns_total_and_accepts_offset() -> None:
    source = ADMIN_API.read_text(encoding="utf-8")
    start = source.index("def handle_audit_log(")
    end = source.index("\n\n_NOTICE_KINDS", start)
    body = source[start:end]
    assert 'params.get("offset"' in body
    assert '"Prefer": "count=exact"' in body
    assert '"total": total' in body


def test_member_and_audit_ui_are_bounded_to_twenty_rows() -> None:
    for name in ("MemberAdminCard.tsx", "AuditLogCard.tsx"):
        source = (ADMIN_UI / name).read_text(encoding="utf-8")
        assert "const PAGE_SIZE = 20" in source, name
        assert "offset=${" in source, name
        assert "표시 {rangeStart" in source, name
        assert "전체 {totalCount" in source, name
