"""US 스코어 타당성 — sentiment KR-매크로 편향 보정 검증 (2026-06-23).

sentiment.py 가 전부 KR-매크로 기준이라 US 종목이 KR 시그널로 왜곡되던 결함 fix.
US = market_mood_us 사용 + fx_sentiment/global_index_decoupling/geopolitical 중립화.
[[project_us_financials_sec_edgar]] / [[feedback_us_expansion_settled_no_relitigate]].
"""
from __future__ import annotations

from api.intelligence.factors.sentiment import _compute_sentiment_score

# KR-매크로가 강한 신호를 주는 상황 (USD/KRW 급변·KOSPI 약세·지정학 심각).
_PF = {
    "macro": {
        "market_mood": {"score": 30},        # KR mood 약세
        "market_mood_us": {"score": 70},     # US mood 우호 (별도 빌드)
        "usd_krw": {"change_pct": 2.0},      # 외인 자금 신호 (KR)
    },
    # 2026-07-20 감사: 실 생산자(alert_engine.build_geopolitical_hotspots) 스키마 = sanctioned/china
    # per-ticker 리스트 (events 아님 — 옛 consumer 가 없는 키 읽어 전 종목 50 상수화하던 버그 fix 정합).
    "geopolitical_hotspots": {
        "sanctioned_exposure": [{"ticker": "005930", "name": "테스트", "pct": 12.0}],
        "china_high_exposure": [],
        "country_avg_exposure": [],
        "covered_companies": 1,
    },
    "market_summary": {"kospi": {"change_pct": -3.0}},        # KOSPI 단독 약세
    "nasdaq": {"change_pct": 1.0},
}


def _comp(currency):
    # ticker 005930 = _PF sanctioned_exposure 등재 → KR geopolitical flagged(<50) 검증. US 는 is_us 로 항상 50.
    r = _compute_sentiment_score({"currency": currency, "ticker": "005930", "sentiment": {"score": 50}}, _PF)
    return r.get("components") or {}


def test_us_uses_market_mood_us_not_kr():
    assert _comp("USD")["market_mood"] == 70     # market_mood_us
    assert _comp("KRW")["market_mood"] == 30      # KR market_mood


def test_us_neutralizes_kr_only_macro():
    us = _comp("USD")
    assert us["fx_sentiment"] == 50.0             # USD/KRW 무관 → 중립
    assert us["global_index_decoupling"] == 50.0  # KOSPI 무관 → 중립
    assert us["geopolitical_score"] == 50.0       # KR 지정학 무관 → 중립


def test_kr_unchanged_regression():
    # KR 은 기존대로 KR-매크로 반영 (회귀 가드).
    kr = _comp("KRW")
    assert kr["fx_sentiment"] < 50                # USD/KRW 2% → penalty
    assert kr["global_index_decoupling"] < 50     # KOSPI 약세 gap
    assert kr["geopolitical_score"] < 50          # sanctioned_exposure flagged → 30


def test_us_sentiment_diverges_from_kr():
    # 동일 매크로 환경에서 US 종합 점수가 KR 과 달라야(왜곡 제거 효과).
    us = _compute_sentiment_score({"currency": "USD", "sentiment": {"score": 50}}, _PF)
    kr = _compute_sentiment_score({"currency": "KRW", "sentiment": {"score": 50}}, _PF)
    assert us.get("score") != kr.get("score")
