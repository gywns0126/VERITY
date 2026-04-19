"""
verity_brain._compute_sentiment_score retail group cap 단위 테스트.

Brain Audit §1-C 수정 검증:
  x_sentiment(X/Twitter) + social_sentiment(reddit+naver+stocktwits) 합산 기여가
  전체 sentiment_score 의 20%(=20점) 를 초과할 수 없다.
"""
from __future__ import annotations

import api.intelligence.verity_brain as vb
from api.intelligence.verity_brain import _compute_sentiment_score


def _reset_const_cache():
    """전역 constitution 캐시 초기화 (다른 테스트 간섭 방지)."""
    vb._constitution_cache = None


def _make_inputs(*, news=50, x=50, mood=50, consensus=None, crypto=50, mfg=50, social=50):
    """각 소스별 sentinel 값으로 stock+portfolio dict 구성.
    constitution.json 기본 가중치(news 0.25, x 0.18, mood 0.18, consensus 0.12,
    crypto 0.08, mfg 0.10, social 0.09 — 합 1.0) 가정."""
    stock = {
        "sentiment": {"score": news},
        "social_sentiment": {"score": social},
    }
    if consensus is not None:
        stock["consensus"] = {"investment_opinion_numeric": consensus}
    portfolio = {
        "x_sentiment": {"score": x},
        "macro": {"market_mood": {"score": mood}},
        "crypto_macro": {"available": True, "composite": {"score": crypto}},
        "market_fear_greed": {"ok": True, "value": mfg},
    }
    return stock, portfolio


def test_retail_cap_meme_stock_pump():
    """
    Sentinel: x=100, social=100, 그 외 모든 소스 50 중립.

    [Before — cap 부재 가정] retail_raw = 100*0.18 + 100*0.09 = 27 (>20)
        총점 = 60*0.25 + 100*0.18 + 50*0.18 + 50*0.12 + 50*0.08 + 50*0.10 + 100*0.09
             = 15 + 18 + 9 + 6 + 4 + 5 + 9 = 66

    [After — RETAIL_CAP=0.20 적용] retail 기여 27 → 20 으로 제한 (excess 7 차감)
        총점 = 66 - 7 = 59

    의미: 밈 종목 4소스 동시 펌프 시 sentiment_score 가 +7 점만큼 덜 부풀려짐.
    """
    _reset_const_cache()
    stock, portfolio = _make_inputs(news=60, x=100, social=100)
    result = _compute_sentiment_score(stock, portfolio)

    # ── 핵심 단언: 캡 적용 후 점수 ──
    assert result["score"] == 59, (
        f"expected 59 after cap, got {result['score']} "
        f"(retail_excess={result.get('retail_excess_score')})"
    )

    # ── 캡 발동 메타 단언 ──
    assert result["retail_cap_applied"] is True
    assert result["retail_excess_score"] == 7.0, (
        f"expected excess 7.0, got {result['retail_excess_score']}"
    )

    # ── components 그대로 보존 (cap은 합산에만 영향, 개별 값은 유지) ──
    assert result["components"]["x_sentiment"] == 100
    assert result["components"]["social_sentiment"] == 100

    # ── 비교 reference: cap 부재 시 기댓값 (베이스라인 — 변경 전/후 대조) ──
    _NO_CAP_BASELINE = 66
    delta = _NO_CAP_BASELINE - result["score"]
    assert delta == 7, f"cap effect (before-after) should be 7 points, got {delta}"


def test_retail_cap_normal_case_no_effect():
    """모든 소스가 중립(50)일 때는 retail 기여가 cap 미달 → 효과 없음.
    회귀 방지: cap 로직이 정상 케이스를 망가뜨리지 않음."""
    _reset_const_cache()
    stock, portfolio = _make_inputs()  # 모두 50
    result = _compute_sentiment_score(stock, portfolio)

    assert result["score"] == 50, f"neutral expected 50, got {result['score']}"
    assert result["retail_cap_applied"] is False
    assert result["retail_excess_score"] == 0.0
