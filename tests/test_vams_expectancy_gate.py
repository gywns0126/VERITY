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
