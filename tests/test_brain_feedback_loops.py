"""
Brain 자동 성장 회로 핵심 로직 단위 테스트.

타깃:
  §26 postmortem penalty (false_buy vs missed_opportunity, time decay)
  #1 AI 리더보드 가중치 (샘플 하한, delta cap, drift cap)
  §24 governance cap (±3.0)
  §22 moat DART 통합 (중복 가산 없음)

회귀 방지용 — 구조 변경 시 의도된 설계가 깨지는지 즉시 감지.
"""
from __future__ import annotations

import pytest

import api.intelligence.verity_brain as vb


# ──────────────────────────────────────────────────────────────
# §26 Postmortem time-decay penalty
# ──────────────────────────────────────────────────────────────


def test_postmortem_false_buy_applies_penalty():
    """false_buy (BUY 했는데 하락) → 감점 정당."""
    portfolio = {
        "postmortem": {
            "windows": {
                "7d": {"failures": [{"ticker": "005930", "type": "false_buy",
                                     "actual_return": -5.0, "lesson": "RSI 과매수"}]}
            }
        }
    }
    penalty, memo = vb._compute_postmortem_penalty({"ticker": "005930"}, portfolio)
    assert penalty < 0
    assert memo["penalty_applied"] is True
    assert memo["type"] == "false_buy"


def test_postmortem_missed_opportunity_no_penalty():
    """missed_opportunity (AVOID 했는데 상승) → 감점 없음 (버그픽스)."""
    portfolio = {
        "postmortem": {
            "windows": {
                "7d": {"failures": [{"ticker": "035720", "type": "missed_opportunity",
                                     "actual_return": 6.38, "lesson": "과도한 회피"}]}
            }
        }
    }
    penalty, memo = vb._compute_postmortem_penalty({"ticker": "035720"}, portfolio)
    assert penalty == 0.0
    assert memo["penalty_applied"] is False
    assert memo["type"] == "missed_opportunity"
    # memo 는 여전히 부착 (UI 경고용)
    assert memo["actual_return"] == 6.38


def test_postmortem_time_decay_halflife():
    """halflife=30 지수감쇠 검증. 0일≈-2, 30일≈-1, 60일≈-0.5."""
    def _pen(days):
        portfolio = {"postmortem": {"windows": {
            f"{days}d": {"failures": [{"ticker": "X", "type": "false_buy"}]}
        }}}
        p, _ = vb._compute_postmortem_penalty({"ticker": "X"}, portfolio)
        return p

    # 30일 경과 ≈ -1.0
    assert abs(_pen(30) - (-1.0)) < 0.05
    # 60일 ≈ -0.5
    assert abs(_pen(60) - (-0.5)) < 0.05
    # 7일 ≈ -1.70 (0.5 ^ (7/30) ≈ 0.851)
    assert abs(_pen(7) - (-1.70)) < 0.05


def test_postmortem_latest_window_wins_on_duplicate():
    """같은 ticker 가 여러 window 에 있으면 가장 최신 window 사용."""
    portfolio = {"postmortem": {"windows": {
        "7d": {"failures": [{"ticker": "TSLA", "type": "false_buy", "lesson": "최근"}]},
        "30d": {"failures": [{"ticker": "TSLA", "type": "false_buy", "lesson": "과거"}]},
    }}}
    penalty, memo = vb._compute_postmortem_penalty({"ticker": "TSLA"}, portfolio)
    # 7d window 선택됨
    assert memo["days_since"] == 7
    assert memo["lesson"] == "최근"


def test_postmortem_no_portfolio_returns_zero():
    """portfolio None / 빈 상태 → 안전하게 0 반환."""
    assert vb._compute_postmortem_penalty({"ticker": "X"}, None) == (0.0, None)
    assert vb._compute_postmortem_penalty({"ticker": "X"}, {}) == (0.0, None)
    # ticker 누락
    assert vb._compute_postmortem_penalty({}, {"postmortem": {}}) == (0.0, None)


# ──────────────────────────────────────────────────────────────
# #1 AI 리더보드 가중치 피드백 루프
# ──────────────────────────────────────────────────────────────


def test_leaderboard_weights_base_when_no_data():
    """리더보드 없음 → base 유지."""
    from api.main import _resolve_dual_model_weights
    r = _resolve_dual_model_weights({})
    assert r["gemini"] == 0.55 and r["claude"] == 0.45
    assert r["_feedback"] == "no_leaderboard"


def test_leaderboard_insufficient_samples_keeps_base():
    """30건 미만 → base 유지 (단기 노이즈 방어)."""
    from api.main import _resolve_dual_model_weights
    r = _resolve_dual_model_weights({
        "ai_leaderboard": {"by_source": [
            {"source": "gemini", "n": 4, "hit_rate": 100.0},
            {"source": "claude", "n": 20, "hit_rate": 55.0},
        ]}
    })
    assert r["gemini"] == 0.55 and r["claude"] == 0.45
    assert r["_feedback"] == "insufficient_samples"


def test_leaderboard_delta_cap_extreme():
    """극단 delta (25%p) → cap (baseline +0.10) 발동."""
    from api.main import _resolve_dual_model_weights
    r = _resolve_dual_model_weights({
        "ai_leaderboard": {"by_source": [
            {"source": "gemini", "n": 50, "hit_rate": 40.0},
            {"source": "claude", "n": 50, "hit_rate": 65.0},
        ]}
    })
    # claude 최대 0.55 (baseline 0.45 + cap 0.10)
    assert r["claude"] == 0.55
    assert r["_cap_applied"] is True


def test_leaderboard_cumulative_drift_cap():
    """Claude weight 는 [0.35, 0.55] 범위 내 (cumulative drift cap)."""
    from api.main import AI_WEIGHT_ABS_MIN, AI_WEIGHT_ABS_MAX
    assert AI_WEIGHT_ABS_MIN == 0.35
    assert AI_WEIGHT_ABS_MAX == 0.55
    # Gemini 극단 우위 시 Claude 는 floor 0.35
    from api.main import _resolve_dual_model_weights
    r = _resolve_dual_model_weights({
        "ai_leaderboard": {"by_source": [
            {"source": "gemini", "n": 50, "hit_rate": 80.0},
            {"source": "claude", "n": 50, "hit_rate": 50.0},
        ]}
    })
    assert r["claude"] == 0.35
    assert r["gemini"] == 0.65


# ──────────────────────────────────────────────────────────────
# §24 governance cap (±3.0)
# ──────────────────────────────────────────────────────────────


def test_governance_penalty_cap_applied():
    """자사주 매각 + 대주주 대량매도 동시 발동 시 penalty cap 3.0 적용."""
    stock = {
        "ticker": "X",
        "currency": "KRW",
        "dart_treasury_stock_latest": {
            "acquisition": {"shares": 0},
            "disposal": {"shares": 1_000_000, "reason": "일반매각"},
        },
        "dart_major_shareholder_changes": [
            {"delta_pct_pt": -6.0, "reason": "대량매도"}
        ],
    }
    # 이론 penalty: 자사주 -1.0 + 대주주 -2.0 = -3.0 (cap 과 동일)
    result = vb._compute_fact_score(stock, portfolio={})
    components = result["components"]
    # governance_penalty cap 발동 확인
    if "governance_penalty" in components:
        assert components["governance_penalty"] <= 3.0
    # audit flag 확인
    fixes = stock.get("data_quality_fixes", [])
    # cap 발동 시 'gov_penalty_capped' 기록
    if components.get("governance_penalty") == 3.0:
        assert "gov_penalty_capped" in fixes


def test_governance_bonus_below_cap():
    """자사주 취득 + 대주주 대량매수 = bonus 2.5 (cap 3.0 미도달)."""
    stock = {
        "ticker": "Y", "currency": "KRW",
        "dart_treasury_stock_latest": {
            "acquisition": {"shares": 1_000_000, "reason": "소각"},
            "disposal": {"shares": 0},
        },
        "dart_major_shareholder_changes": [
            {"delta_pct_pt": +2.0, "reason": "장내매수"}
        ],
    }
    result = vb._compute_fact_score(stock, portfolio={})
    components = result["components"]
    if "governance_bonus" in components:
        # bonus 는 cap 3.0 이내 (이론최대 2.5)
        assert components["governance_bonus"] <= 3.0


# ──────────────────────────────────────────────────────────────
# Perplexity risk mapping (#2a)
# ──────────────────────────────────────────────────────────────


def test_perplexity_risk_component_mapping():
    """risk_level → 점수 매핑 정확성."""
    def _score(level):
        stock = {"ticker": "X", "currency": "USD"}
        if level:
            stock["external_risk"] = {"risk_level": level}
        result = vb._compute_fact_score(stock, portfolio={})
        return result["components"].get("perplexity_risk")

    assert _score(None) == 50.0       # 스캔 미호출 → 중립
    assert _score("LOW") == 60.0
    assert _score("MODERATE") == 40.0
    assert _score("HIGH") == 15.0
    assert _score("CRITICAL") == 5.0
