"""2026-07-24 US SEC 재무 확장 — Altman/graham US 결측 해소.

sec_edgar get_financial_facts 에 Assets/유동자산·부채/이익잉여금 추가(XBRL 실 SEC 검증) → US Altman
(X1 운전자본/총자산·X2 이익잉여금)·graham 유동비율(200%) 활성화. quality/graham 이 sec_financials fallback.
"""
from __future__ import annotations

from api.quant.factors.quality import compute_altman_z
from api.intelligence.factors.graham import _compute_graham_score


def _us(**sf):
    return {"currency": "USD", "market": "NASDAQ", "market_cap": 100e9,
            "sec_financials": {"total_assets": 200e9, "working_capital": 20e9,
                               "retained_earnings": 50e9, "operating_income": 15e9,
                               "total_debt": 40e9, **sf}}


def test_altman_us_activates_from_sec_financials():
    # 옛: top-level total_assets None → bail(unknown). 이제 sec_financials fallback → 계산.
    res = compute_altman_z(_us())
    assert res.get("zone") != "unknown"
    assert res.get("z_score") is not None


def test_altman_us_bail_when_no_sec_financials():
    # sec_financials 도 없으면 여전히 데이터부족(정상 — 없는 데이터 억지 계산 금지)
    res = compute_altman_z({"currency": "USD", "market": "NASDAQ"})
    assert res.get("zone") == "unknown"


def test_graham_us_current_ratio_active():
    # 유동비율 criterion: 250%(>200 → +5) > 89%(<100 → -5)
    hi = _compute_graham_score({"currency": "USD", "per": 15, "sec_financials": {"current_ratio": 250, "roe": 0.2, "debt_ratio": 50}})
    lo = _compute_graham_score({"currency": "USD", "per": 15, "sec_financials": {"current_ratio": 89, "roe": 0.2, "debt_ratio": 50}})
    assert hi > lo  # 유동비율 축이 US 에서 활성 (옛 항상 0 → dead)
