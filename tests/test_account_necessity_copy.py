"""계정 안내가 판촉 문구가 아니라 기록 보존 계약을 설명하는지 검증한다."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "framer-components" / "public-probe"


def test_menu_explains_storage_requirement() -> None:
    source = (PUBLIC / "PublicMenuAccount.tsx").read_text(encoding="utf-8")
    assert "로그인하고 기록 보관" in source
    assert "기기 간 동기화" in source
    assert "무료로" not in source


def test_menu_preserves_account_shape_until_auth_is_ready() -> None:
    source = (PUBLIC / "PublicMenuAccount.tsx").read_text(encoding="utf-8")
    assert "const [authReady, setAuthReady]" in source
    assert 'typeof window !== "undefined" && !!loadSession()' in source
    assert "setAuthReady(true)" in source
    assert "if (!authReady)" in source
    assert 'visibility: "hidden"' not in source
    assert 'background: hexA(sub, 0.13)' in source


def test_auth_explains_public_and_account_boundaries() -> None:
    source = (PUBLIC / "PublicAuth.tsx").read_text(encoding="utf-8")
    assert "개인 투자 기록을 보관하려면 계정이 필요합니다" in source
    assert "시장 정보와 종목 리포트는 로그인 없이 볼 수 있습니다" in source
    assert "계정 만들기" in source


def test_thesis_copy_explains_identity_and_persistence() -> None:
    source = (PUBLIC / "PublicThesisNote.tsx").read_text(encoding="utf-8")
    assert "작성자 식별과 수정 이력 보존" in source
    assert "현재 기기에 임시 저장됩니다" in source
    assert "기록을 보존하고 다른 기기에서 불러오려면 로그인이 필요합니다" in source


def test_visit_rpc_uses_named_conflict_constraint() -> None:
    source = (ROOT / "supabase" / "migrations" / "034_fix_site_visit_rpc.sql").read_text(encoding="utf-8")
    assert "on conflict on constraint site_visit_days_pkey" in source.lower()
    assert "grant execute on function public.record_site_visit(text) to anon, authenticated" in source.lower()
