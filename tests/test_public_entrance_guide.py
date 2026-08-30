"""홈 리서치 길잡이의 공개 계약을 보호한다.

길잡이는 투자성향이나 종목을 추천하지 않고, 기존 데이터 페이지를 읽는 순서만
안내한다. 첫 방문 이후에는 축소 상태를 브라우저에 기억해 재방문을 방해하지 않는다.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "framer-components" / "public-probe" / "PublicEntranceMap.tsx"


def _source() -> str:
    return COMPONENT.read_text(encoding="utf-8")


def test_guide_keeps_five_question_routes_and_existing_data_map():
    src = _source()
    for text in (
        "특정 종목을 알아보고 싶어요",
        "오늘 시장을 이해하고 싶어요",
        "좋은 기업인지 확인하고 싶어요",
        "내 포트폴리오 위험을 점검하고 싶어요",
        "공시와 기업 변화를 확인하고 싶어요",
        "전체 데이터 지도",
    ):
        assert text in src


def test_guide_collapses_for_returning_visitors_without_login_profile():
    src = _source()
    assert 'localStorage.getItem("an_research_guide_seen")' in src
    assert 'localStorage.setItem("an_research_guide_seen", "1")' in src
    assert "supabase" not in src.lower()


def test_guide_routes_to_research_pages_instead_of_scoring_users():
    src = _source()
    for path in ("/stock", "/market", "/nest", "/disclosure", "/glassbox"):
        assert path in src
    for forbidden in ("공격형", "안정형", "위험등급", "추천 종목"):
        assert forbidden not in src
