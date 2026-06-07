"""VAMS expectancy_r AND-gate (88b40aa2, 2026-05-16 Perplexity 승인 구현)."""
from api.vams.validation import _trade_stats


def _hist(wins, win_amt, losses, loss_amt):
    return ([{"type": "SELL", "pnl": win_amt, "date": "2026-06-01"}] * wins
            + [{"type": "SELL", "pnl": -loss_amt, "date": "2026-06-01"}] * losses)


def test_expectancy_r_formula():
    # win_rate 0.6, pl_ratio 2.0 → E[R] = 0.6×2 − 0.4 = 0.8
    t = _trade_stats(_hist(6, 200, 4, 100))
    assert t["expectancy_r"] == 0.8


def test_high_winrate_low_pl_below_1_2R():
    # 55% + pl 1.5 (현 win/pl 게이트 최소) → E[R] = 0.55×1.5 − 0.45 = 0.375 < 1.2 (게이트 강함)
    t = _trade_stats(_hist(55, 150, 45, 100))
    assert t["expectancy_r"] == round(0.55 * 1.5 - 0.45, 3)
    assert t["expectancy_r"] < 1.2


def test_expectancy_none_when_no_loss():
    assert _trade_stats(_hist(5, 100, 0, 0))["expectancy_r"] is None
    assert _trade_stats([])["expectancy_r"] is None


def test_sqn_computation():
    """SQN = mean(R)/σ(R) × √min(N,100). 6×+2R, 4×-1R → E=0.8, σ≈1.469, SQN≈1.72."""
    t = _trade_stats(_hist(6, 200, 4, 100))
    assert t["sqn"] == 1.721
    # 표본<2 또는 무손실 → None
    assert _trade_stats(_hist(1, 100, 1, 100))["sqn"] is not None  # 2건이면 계산
    assert _trade_stats([])["sqn"] is None


def test_recalibrated_thresholds_2026_06_07():
    """1.2R→0.25R 재보정(Perplexity) — 0.375R(55%+1.5pl)가 이제 통과대(>0.25)."""
    from api.config import VAMS_MIN_EXPECTANCY_R, VAMS_MIN_SQN
    assert VAMS_MIN_EXPECTANCY_R == 0.25
    assert VAMS_MIN_SQN == 1.7
    t = _trade_stats(_hist(55, 150, 45, 100))
    assert t["expectancy_r"] >= VAMS_MIN_EXPECTANCY_R  # 0.375 ≥ 0.25 통과
