# -*- coding: utf-8 -*-
"""fx_hedge_regime — 사전등록 §2 규칙의 단위 검증 (등록값 1391/1509/30%)."""
import copy

from api.vams.fx_hedge_regime import BAND_HI, BAND_LO, TARGET_RATIO, run


def _pf(cash=1_000_000, reserve_krw=2_800_000, usd_stock=1_400_000, krw_stock=4_500_000):
    holdings = []
    if usd_stock:
        holdings.append({"ticker": "NEM", "currency": "USD",
                         "current_price": usd_stock, "quantity": 1})
    if krw_stock:
        holdings.append({"ticker": "005930", "currency": "KRW",
                         "current_price": krw_stock, "quantity": 1})
    reserve = None
    if reserve_krw:
        reserve = {"usd_value": reserve_krw / 1450.0, "krw_invested": 3_000_000.0,
                   "current_krw": float(reserve_krw),
                   "pnl_krw": reserve_krw - 3_000_000.0, "ticker": "455030",
                   "name": "KODEX 미국달러SOFR금리액티브(합성)"}
    total = cash + reserve_krw + usd_stock + krw_stock
    return {"vams": {"cash": float(cash), "holdings": holdings,
                     "fx_hedge_reserve": reserve, "total_asset": float(total)}}


def test_initial_cut_to_cap_in_deadband():
    """데드밴드 + 초기 상태 ON → 최초 1회 상한 축소 (등록 §3)."""
    pf = _pf()
    r = run(pf, fx=1415.30)
    assert r["status"] == "adjusted" and r["state"] == "ON"
    v = pf["vams"]
    total = v["total_asset"]  # 조정 전 총자산 기준 목표
    expect_target = max(0.0, TARGET_RATIO * 9_700_000 - 1_400_000)
    assert abs(r["op"]["target"] - expect_target) < 2
    # 총자산 불변 (현금 ↔ 리저브 이동만)
    new_total = v["cash"] + (v["fx_hedge_reserve"] or {}).get("current_krw", 0) \
        + sum(h["current_price"] * h["quantity"] for h in v["holdings"])
    assert abs(new_total - total) < 2


def test_deadband_holds_after_initial():
    pf = _pf()
    run(pf, fx=1415.30)
    r2 = run(pf, fx=1420.0)          # 데드밴드 재평가 — 트리거 없음
    assert r2["status"] == "hold"


def test_off_liquidates_fully():
    pf = _pf()
    run(pf, fx=1415.30)
    r = run(pf, fx=BAND_LO - 1)      # 1390 → OFF
    assert r["state"] == "OFF" and r["op"]["target"] == 0
    assert pf["vams"]["fx_hedge_reserve"] is None
    assert pf["vams"]["fx_hedge_reserve_closed"]["realized_pnl_cum"] is not None


def test_on_reenters_bounded_by_cash():
    pf = _pf()
    run(pf, fx=1415.30)
    run(pf, fx=BAND_LO - 1)          # 전량 청산
    cash_before = pf["vams"]["cash"]
    r = run(pf, fx=BAND_HI + 1)      # ON 복귀 → 목표 재충전 (현금 한도 내)
    assert r["state"] == "ON"
    assert pf["vams"]["cash"] >= 0
    moved = r["op"].get("moved", 0)
    assert moved <= cash_before + 1
    # 재진입 종목은 청산 기록에서 승계 — 다른 상품으로 갈아타지 않는다
    assert pf["vams"]["fx_hedge_reserve"]["ticker"] == "455030"


def test_usd_holdings_change_triggers_recompute():
    pf = _pf()
    run(pf, fx=1415.30)
    pf["vams"]["holdings"] = [h for h in pf["vams"]["holdings"]
                              if h["currency"] != "USD"]   # USD 전량 청산
    r = run(pf, fx=1415.30)
    assert r["status"] in ("adjusted", "evaluated")
    assert "usd_holdings_change" in r["op"]["triggers"]
    # USD 주식이 빠지면 목표가 커진다 (0.30×총자산 전액)
    assert r["op"]["target"] > 0


def test_idempotent_no_action_when_at_target():
    pf = _pf()
    run(pf, fx=1415.30)
    st = copy.deepcopy(pf["vams"]["fx_hedge_regime"]["last"])
    r = run(pf, fx=1415.30)
    assert r["status"] == "hold"
    assert pf["vams"]["fx_hedge_regime"]["last"]["usd_set"] == st["usd_set"]
