"""
신규 딜 품질 (막스 5번째 사이클 신호) — V2.3 검증.
"""
from __future__ import annotations

import pytest


def test_classify_speculative_extreme():
    """광기 — z >= +1.5 (둘 다 매우 높음)"""
    from api.intelligence.market_horizon import classify_new_listing_quality
    out = classify_new_listing_quality(
        recent_listings_count=50,
        avg_first_day_return_pct=80.0,
        baseline_listings_count=20,
        baseline_first_day_return_pct=20.0,
        baseline_listings_sigma=10.0,
        baseline_return_sigma=15.0,
    )
    assert out["verdict"] == "speculative_extreme"
    assert out["value"] >= 1.5


def test_classify_normal():
    """정상 — z 작음"""
    from api.intelligence.market_horizon import classify_new_listing_quality
    out = classify_new_listing_quality(
        recent_listings_count=20,
        avg_first_day_return_pct=18.0,
        baseline_listings_count=20,
        baseline_first_day_return_pct=20.0,
        baseline_listings_sigma=10.0,
        baseline_return_sigma=15.0,
    )
    assert out["verdict"] == "normal"


def test_classify_starved():
    """기근 — z <= -1.5 (둘 다 매우 낮음, contrarian 매수 신호)"""
    from api.intelligence.market_horizon import classify_new_listing_quality
    out = classify_new_listing_quality(
        recent_listings_count=2,
        avg_first_day_return_pct=-20.0,
        baseline_listings_count=20,
        baseline_first_day_return_pct=20.0,
        baseline_listings_sigma=10.0,
        baseline_return_sigma=15.0,
    )
    assert out["verdict"] == "starved"
    assert out["value"] < -1.5


def test_classify_count_only_when_return_missing():
    from api.intelligence.market_horizon import classify_new_listing_quality
    out = classify_new_listing_quality(
        recent_listings_count=50,
        avg_first_day_return_pct=None,
        baseline_listings_count=20,
        baseline_first_day_return_pct=None,
        baseline_listings_sigma=10.0,
    )
    assert out["z_count"] == 3.0
    assert out["z_return"] is None
    assert out["verdict"] == "speculative_extreme"


def test_classify_returns_none_when_no_input():
    from api.intelligence.market_horizon import classify_new_listing_quality
    out = classify_new_listing_quality(
        recent_listings_count=None,
        avg_first_day_return_pct=None,
        baseline_listings_count=None,
        baseline_first_day_return_pct=None,
    )
    assert out["verdict"] is None


def test_build_signals_includes_new_listing_quality():
    """build_signals 에 new_listing_quality 합류 검증."""
    from api.intelligence.market_horizon import build_signals, classify_new_listing_quality
    nlq = classify_new_listing_quality(
        recent_listings_count=50, avg_first_day_return_pct=80.0,
        baseline_listings_count=20, baseline_first_day_return_pct=20.0,
        baseline_listings_sigma=10.0, baseline_return_sigma=15.0,
    )
    sigs = build_signals(
        spread_3m_10y=0.5, cape=30, cape_pctile=85, pmi=51, hy_oas=3.5, vix=18,
        new_listing_quality=nlq,
    )
    nl_sig = next((s for s in sigs if s["name"] == "new_listing_quality"), None)
    assert nl_sig is not None
    assert nl_sig["direction"] == "warn"  # speculative_extreme = warn
    assert "Howard Marks" in nl_sig["note"]
    assert "z_count" in nl_sig["note"]


def test_build_signals_starved_is_ok_direction():
    """starved 는 contrarian 매수 신호 → ok direction"""
    from api.intelligence.market_horizon import build_signals, classify_new_listing_quality
    nlq = classify_new_listing_quality(
        recent_listings_count=2, avg_first_day_return_pct=-20.0,
        baseline_listings_count=20, baseline_first_day_return_pct=20.0,
        baseline_listings_sigma=10.0, baseline_return_sigma=15.0,
    )
    sigs = build_signals(
        spread_3m_10y=0.5, cape=30, cape_pctile=85, pmi=51, hy_oas=3.5, vix=18,
        new_listing_quality=nlq,
    )
    nl_sig = next((s for s in sigs if s["name"] == "new_listing_quality"), None)
    assert nl_sig["direction"] == "ok"


def test_build_signals_no_nlq_skips_signal():
    """new_listing_quality verdict=None 이면 signal 추가 안 됨."""
    from api.intelligence.market_horizon import build_signals
    sigs = build_signals(
        spread_3m_10y=0.5, cape=30, cape_pctile=85, pmi=51, hy_oas=3.5, vix=18,
        new_listing_quality={"verdict": None},
    )
    nl_sig = next((s for s in sigs if s["name"] == "new_listing_quality"), None)
    assert nl_sig is None


def test_compute_market_horizon_extracts_new_listings_from_portfolio():
    """compute_market_horizon 가 portfolio.new_listings 를 정확히 추출하는지."""
    from api.intelligence.market_horizon import compute_market_horizon
    portfolio = {
        "new_listings": {
            "recent_3m_count": 50,
            "recent_3m_avg_first_day_pct": 80.0,
            "baseline_5y_count": 20,
            "baseline_5y_first_day_pct": 20.0,
            "baseline_count_sigma": 10.0,
            "baseline_return_sigma": 15.0,
        },
    }
    out = compute_market_horizon(portfolio)
    nl_sig = next((s for s in out["signals"] if s["name"] == "new_listing_quality"), None)
    assert nl_sig is not None
    assert nl_sig["direction"] == "warn"
    assert nl_sig["value"] >= 1.5
