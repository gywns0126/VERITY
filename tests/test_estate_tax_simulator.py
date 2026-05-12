"""
test_estate_tax_simulator.py — 한국 부동산 세제 시뮬레이터 산식 검증.

핵심:
    1) 취득세 구간 (6억/9억 경계)
    2) 재산세 누진세
    3) 종부세 12억 공제 + 누진
    4) 양도세 1주택 12억 이하 비과세
    5) 단기 양도 (1년 미만 70%, 1~2년 60%)
    6) 장기보유특별공제 누적
    7) invalid input → ValueError
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EP = ROOT / "vercel-api" / "api" / "estate_tax_simulator.py"

spec = importlib.util.spec_from_file_location("estate_tax_sim", str(EP))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


# ── 취득세 ──

def test_acquisition_tax_6억_이하():
    """5억 매수 → 1.1% = 550만원."""
    tax, meta = mod.calc_acquisition_tax(500_000_000)
    assert tax == 5_500_000
    assert meta["rate"] == 0.011


def test_acquisition_tax_6_to_9억():
    """8억 매수 → 2.0% = 1600만원."""
    tax, meta = mod.calc_acquisition_tax(800_000_000)
    assert tax == 16_000_000
    assert meta["rate"] == 0.020


def test_acquisition_tax_9억_초과():
    """10억 매수 → 3.3% = 3300만원."""
    tax, meta = mod.calc_acquisition_tax(1_000_000_000)
    assert tax == 33_000_000
    assert meta["rate"] == 0.033


# ── 재산세 ──

def test_property_tax_low_value():
    """공시가격 1억 → 과표 6000만 → 0.1% = 6만원."""
    tax, meta = mod.calc_property_tax(100_000_000)
    assert tax == 60_000
    assert meta["taxable_base"] == 60_000_000


def test_property_tax_high_value():
    """공시가격 10억 → 과표 6억 → 0.4% × 6억 − 63만 = 177만원."""
    tax, meta = mod.calc_property_tax(1_000_000_000)
    assert tax == 1_770_000  # 6억 × 0.4% - 63만 = 240만 - 63만


# ── 종부세 ──

def test_comprehensive_tax_below_12억_zero():
    """1주택 + 공시가격 10억 → 종부세 0 (12억 공제)."""
    tax, meta = mod.calc_comprehensive_tax(1_000_000_000)
    assert tax == 0
    assert meta["taxable_base"] == 0


def test_comprehensive_tax_above_12억():
    """1주택 + 공시가격 15억 → 초과 3억 × 60% = 1.8억 → 0.5% = 90만원."""
    tax, meta = mod.calc_comprehensive_tax(1_500_000_000)
    assert tax == 900_000
    assert meta["taxable_base"] == 180_000_000


# ── 양도세 ──

def test_capital_gains_exempt_under_12억_1house():
    """매도가 10억 + 보유 5년 + 거주 5년 → 비과세 (1세대 1주택)."""
    tax, meta = mod.calc_capital_gains_tax(
        purchase_price=700_000_000,
        sale_price=1_000_000_000,
        holding_years=5,
        residence_years=5,
    )
    assert tax == 0
    assert meta["status"] == "exempt_1house_under_12억"


def test_capital_gains_short_term_under_1y():
    """1년 미만 매도 → 70% 세율."""
    tax, meta = mod.calc_capital_gains_tax(
        purchase_price=500_000_000,
        sale_price=600_000_000,
        holding_years=0,
        residence_years=0,
    )
    # gain = 100_000_000, 70% = 70_000_000
    assert tax == 70_000_000
    assert meta["status"] == "short_term_under_1y"


def test_capital_gains_short_term_1_to_2y():
    """1~2년 매도 → 60% 세율."""
    tax, meta = mod.calc_capital_gains_tax(
        purchase_price=500_000_000,
        sale_price=600_000_000,
        holding_years=1,
        residence_years=1,
    )
    assert tax == 60_000_000
    assert meta["status"] == "short_term_1_to_2y"


def test_capital_gains_long_term_with_deduction():
    """5년 보유/거주 + 12억 초과 → 장기보유특별공제 40% + 누진세."""
    tax, meta = mod.calc_capital_gains_tax(
        purchase_price=1_000_000_000,
        sale_price=1_500_000_000,
        holding_years=5,
        residence_years=5,
    )
    # 12억 초과 1주택 — taxable_ratio = (15-12)/15 = 0.2
    # gain = 5억, taxable_gain = 5억 × 0.2 = 1억
    # 장기보유공제 = (5×4%)×2 = 40%
    # after_deduction = 1억 × 0.6 = 6000만 → 24% bracket (5000만 초과 8800만 이하)
    # tax = 6000만×24%−576만 = 1440만−576만 = 864만원
    assert meta["status"] == "long_term"
    assert meta["long_term_deduction_rate"] == pytest.approx(0.40)
    assert meta["taxable_gain"] == 100_000_000
    assert tax == 8_640_000


def test_capital_gains_no_sale_returns_zero():
    """매도가 0 → 양도세 0."""
    tax, meta = mod.calc_capital_gains_tax(500_000_000, 0, 5, 5)
    assert tax == 0
    assert meta["status"] == "no_sale"


def test_capital_gains_loss_returns_zero():
    """매도가 < 매수가 → 양도세 0."""
    tax, meta = mod.calc_capital_gains_tax(500_000_000, 400_000_000, 5, 5)
    assert tax == 0
    assert meta["status"] == "no_gain"


# ── 통합 simulate() ──

def test_simulate_full_flow():
    """8억 매수 + 5년 후 12억 매도 + 1주택. 모든 세금 합산."""
    result = mod.simulate({
        "purchase_price": 800_000_000,
        "appraised_value": 700_000_000,
        "holding_years": 5,
        "residence_years": 5,
        "sale_price": 1_200_000_000,
    })
    assert result["acquisition_tax"] == 16_000_000  # 2.0%
    assert result["annual_property_tax"] > 0
    assert result["annual_comprehensive_tax"] == 0  # 7억 공시 < 12억
    assert result["capital_gains_tax"] == 0  # 정확히 12억 = 비과세
    assert result["total_burden"] >= result["acquisition_tax"]
    assert result["track"].startswith("1세대 1주택")


def test_simulate_invalid_purchase_price():
    with pytest.raises(ValueError, match="purchase_price"):
        mod.simulate({"purchase_price": 0})


def test_simulate_residence_exceeds_holding():
    with pytest.raises(ValueError, match="residence_years"):
        mod.simulate({
            "purchase_price": 500_000_000,
            "holding_years": 2,
            "residence_years": 3,
        })


def test_simulate_appraised_fallback_70pct():
    """공시가격 미제공 → purchase_price × 0.7 fallback."""
    result = mod.simulate({
        "purchase_price": 1_000_000_000,
        "holding_years": 5,
        "residence_years": 5,
    })
    assert result["input"]["appraised_value"] == 700_000_000
