"""매매밴드 tier 스케일러 + 분기 재분배 단위테스트 (PREREG_TRADING_BANDS Part A/B, PM 승인 2026-08-02)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.portfolio.band_scaler import band_profile, scaled_entry_zone, scaled_stop_pct  # noqa: E402
from api.portfolio.rebalance import quarterly_rebalance  # noqa: E402


def test_tier_boundaries_and_mults():
    """승인 tier: S<1천만 ×1.4 / M<1억 ×1.0 / L<10억 ×0.8 / XL ×1.2 (U자)."""
    assert band_profile(5_000_000)["tier"] == "S"
    assert band_profile(5_000_000)["band_mult"] == 1.4
    assert band_profile(10_000_000)["tier"] == "M"          # 경계=상위 tier
    assert band_profile(50_000_000)["band_mult"] == 1.0
    assert band_profile(500_000_000)["band_mult"] == 0.8
    assert band_profile(5_000_000_000)["tier"] == "XL"
    assert band_profile(5_000_000_000)["band_mult"] == 1.2
    assert band_profile(5_000_000_000)["slice_required"] is True


def test_invalid_total_falls_back_neutral():
    for bad in (0, -1, None, "x"):
        p = band_profile(bad)  # type: ignore[arg-type]
        assert p["tier"] == "M" and p["band_mult"] == 1.0 and p["fallback"] is True


def test_scaled_stop_widens_for_small_accounts():
    """ATR base -6% · S=×1.4 → -8.4% (넓게) / L=×0.8 → -4.8% (좁게). 항상 음수."""
    assert abs(scaled_stop_pct(-6.0, 5_000_000) - (-8.4)) < 1e-9
    assert abs(scaled_stop_pct(6.0, 500_000_000) - (-4.8)) < 1e-9


def test_entry_zone_scales_width_high_anchored():
    lo, hi = scaled_entry_zone(90.0, 100.0, 5_000_000)   # 폭 10 → ×1.4 = 14
    assert hi == 100.0 and abs(lo - 86.0) < 1e-9
    lo2, hi2 = scaled_entry_zone(90.0, 100.0, 500_000_000)  # ×0.8 = 8
    assert hi2 == 100.0 and abs(lo2 - 92.0) < 1e-9
    assert scaled_entry_zone(100.0, 90.0, 1_000_000) == (100.0, 90.0)  # 비정상=원값


def test_rebalance_drift_gate_no_trade_inside_band():
    """M tier 밴드 ±20%: 목표 10% 보유 11%(rel +10%) = 밴드 내 → 액션 0."""
    out = quarterly_rebalance({"A": 0.11}, {"A": 0.10}, 50_000_000)
    assert out["actions"] == [] and out["skipped_in_band"] == 1


def test_rebalance_leland_partial_to_edge_not_target():
    """M tier(5천만, ±20%): 목표 10% 보유 16%(rel +60%) → edge 12%까지만 매도 (목표 복귀 아님)."""
    out = quarterly_rebalance({"A": 0.16}, {"A": 0.10}, 50_000_000)
    a = out["actions"][0]
    assert a["side"] == "sell"
    assert abs(a["to_w"] - 0.12) < 1e-9          # 밴드 edge
    assert a["amount_krw"] == round(0.04 * 50_000_000)
    assert a["cost_krw"] == round(a["amount_krw"] * 0.00215)  # 매도세+수수료


def test_tier_boundary_exactly_1e8_is_L():
    """경계 정합: 정확히 1억 = L(±12%, ×0.8) — Part A 표 '1억~10억'."""
    assert band_profile(100_000_000)["tier"] == "L"
    out = quarterly_rebalance({"A": 0.16}, {"A": 0.10}, 100_000_000)
    assert abs(out["actions"][0]["to_w"] - 0.112) < 1e-9


def test_rebalance_min_trade_gate_flag():
    """S tier 최소 30만: 소액 드리프트는 gated=True 표기(실행 보류)."""
    out = quarterly_rebalance({"A": 0.20}, {"A": 0.10}, 3_000_000)
    a = out["actions"][0]
    assert a["gated"] is (a["amount_krw"] < 300_000)


def test_rebalance_untargeted_holding_goes_to_review():
    """목표 없는 보유 = 자동 청산 산출 금지, review 로만."""
    out = quarterly_rebalance({"A": 0.10, "B": 0.05}, {"A": 0.10}, 50_000_000)
    assert out["review"] == ["B"]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if fails else 0)
