"""
verity_brain._compute_sentiment_score retail group cap 단위 테스트.

2026-05-16 Perplexity 자문 후 design 변경:
  - 13-source hard-wire weight 채택 (post-hoc normalize 폐기)
  - x_sentiment 0.125 + social_sentiment 0.085 = retail 21% (cap 22% 미만)
  - 정상 운영 cap 미발동 (intentional dead)
  - meme trigger (Phase 2 TODO) 시 cap 18% 동적 강화 검증은 별 test

본 test = 정상 운영 (밈 트리거 inactive) 에서 cap 미발동 + components 보존 검증.
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
    Sentinel: x=100, social=100, news=60, 그 외 50 중립.

    13-source hard-wire weight (2026-05-16 Perplexity 자문 후):
      x_sentiment 0.125, social_sentiment 0.085 → retail 합 0.21
      RETAIL_CAP_BASE 0.22 → retail 21% < cap 22% = **정상 운영 cap 미발동**

    2026-06-03: constitution sentiment weights 를 13개 설계값(_default_w)과 동기화 후 actual:
      - score: 62 (이전 63 = constitution 7개가 신규 6개 _default_w 와 혼재해 w_sum=1.26
        이던 출처 이중화 상태값. 단일 출처(w_sum=1.0) 회복으로 1점 미세 변동 — weight
        재배분의 정당한 귀결, retail cap 의도/동작은 불변)
      - retail_cap_applied: False
      - retail_excess_score: 0.0

    의미: 정상 운영 cap intentional dead. meme trigger 시만 cap_meme 18% 동적 강화
    (Phase 2 TODO — 별 test).
    """
    _reset_const_cache()
    stock, portfolio = _make_inputs(news=60, x=100, social=100)
    result = _compute_sentiment_score(stock, portfolio)

    # ── 13-source hard-wire 산식: x=100/social=100 = retail 21% < cap 22% → cap 미발동 ──
    assert result["score"] == 62, (
        f"expected 62 with 13-source single-source weights, got {result['score']} "
        f"(retail_excess={result.get('retail_excess_score')})"
    )

    # ── 정상 운영 cap 미발동 (intentional dead, meme trigger 시만 cap_meme 18% 강화) ──
    assert result["retail_cap_applied"] is False, (
        "정상 운영 시 retail cap 미발동. 발동 시 meme trigger logic 결함 의심."
    )
    assert result["retail_excess_score"] == 0.0

    # ── components 그대로 보존 ──
    assert result["components"]["x_sentiment"] == 100
    assert result["components"]["social_sentiment"] == 100


def test_retail_cap_normal_case_no_effect():
    """모든 소스가 중립(50)일 때는 retail 기여가 cap 미달 → 효과 없음.
    회귀 방지: cap 로직이 정상 케이스를 망가뜨리지 않음."""
    _reset_const_cache()
    stock, portfolio = _make_inputs()  # 모두 50
    result = _compute_sentiment_score(stock, portfolio)

    assert result["score"] == 50, f"neutral expected 50, got {result['score']}"
    assert result["retail_cap_applied"] is False
    assert result["retail_excess_score"] == 0.0
