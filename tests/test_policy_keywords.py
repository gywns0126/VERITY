"""
test_policy_keywords.py — Step 2 prefilter + 키워드 사전 검증

T16: KEYWORDS fabricate 금지 — fixture 12건 + 표준 용어 출처 매칭.
"""
from api.analyzers.policy_keywords import (
    CATEGORY_KEYWORDS,
    KEYWORDS,
    keyword_matches,
    rough_relevance_filter,
)


def _p(title: str = "", raw_text: str = "") -> dict:
    return {
        "id": "t",
        "title": title,
        "source_url": "https://www.korea.kr/news/x",
        "source_name": "국토교통부",
        "published_at": "2026-05-01T00:00:00+00:00",
        "raw_text": raw_text,
    }


# ── 부동산 매칭 (fixture 12건) ─────────────────────

def test_filter_matches_apartment_pubprice():
    """fixture #1: 2026년 공동주택 공시가격 — tax 매칭."""
    p = _p(title="2026년 공동주택 공시가격(안) 공개")
    assert rough_relevance_filter(p) is True
    m = keyword_matches(p)
    assert "공시가격" in m["tax"]


def test_filter_matches_public_housing_supply():
    """fixture #2,3: 공공주택 분양 / 도심 공공주택 — supply 매칭."""
    p = _p(title="상반기 수도권 공공주택 분양 일정")
    assert rough_relevance_filter(p) is True
    m = keyword_matches(p)
    assert "공공주택" in m["supply"]
    assert "분양" in m["supply"]


def test_filter_matches_jeonse_fraud():
    """fixture #7: 전세사기특별법 — rental 매칭."""
    p = _p(title="전세사기특별법 개정")
    m = keyword_matches(p)
    assert "전세사기" in m["rental"]


def test_filter_matches_irregular_transaction():
    """fixture #6: 서울·경기 주택 이상거래 — anomaly + catalyst 동시 매칭."""
    p = _p(title="서울 강남구 주택 이상거래 단속")
    m = keyword_matches(p)
    assert "이상거래" in m["anomaly"]
    assert "주택" in m["catalyst"]


# ── 비-부동산 (fixture 38건 부분) ─────────────────────

def test_filter_excludes_satellite_launch():
    """fixture: 차세대중형위성 발사 — 매칭 X."""
    p = _p(title="차세대중형위성 2호 5월 발사 예정")
    assert rough_relevance_filter(p) is False


def test_filter_excludes_railway_announcement():
    """fixture: 부전~마산 복선전철 — 매칭 X (철도)."""
    p = _p(title="부전~마산 복선전철 사업의 조속한 개통")
    assert rough_relevance_filter(p) is False


def test_filter_excludes_minister_briefing():
    """fixture: [장관동정] 청년정책 — 매칭 X (일반 동정)."""
    p = _p(title="[장관동정] 김윤덕 장관 청년정책")
    assert rough_relevance_filter(p) is False


def test_filter_excludes_traffic_card():
    """fixture: 모두의카드 대중교통 환급 — 매칭 X (교통/카드)."""
    p = _p(title="모두의카드 대중교통 환급")
    assert rough_relevance_filter(p) is False


# ── 경계 케이스 ─────────────────────

def test_keywords_sorted_long_first():
    """길이 내림차순 정렬: '전세사기' 가 '전세' 보다 앞에 위치 → 매칭 충돌 회피."""
    assert KEYWORDS.index("전세사기") < KEYWORDS.index("전세")


def test_category_dict_covers_all_8_categories():
    """8 카테고리 모두 키워드 ≥1개."""
    expected = {
        "regulation", "supply", "tax", "loan",
        "redev", "rental", "anomaly", "catalyst",
    }
    assert set(CATEGORY_KEYWORDS.keys()) == expected
    for cat, kws in CATEGORY_KEYWORDS.items():
        assert len(kws) >= 1, f"{cat} 카테고리에 키워드 0개"


def test_filter_returns_false_on_empty_policy():
    """빈 정책 dict — 매칭 X."""
    assert rough_relevance_filter(_p()) is False
    assert rough_relevance_filter({"title": None, "raw_text": None}) is False
