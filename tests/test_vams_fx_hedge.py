"""β USD ETF FX 헷지 reserve 단위 테스트 (2026-05-18 PM 결정, 5/22 실행).

검증:
  - enter_fx_hedge: cash→reserve, USD 원금 = krw/usdkrw, 진입 시 total 불변
  - recalculate_total: USDKRW MtM (환손익), reserve 가 total_asset 에 가산
  - holdings 외 별도 필드 → Brain auto-sell(run_vams_cycle 매도 루프) 구조적 제외
  - 중복 진입 거부 / cash 초과 거부
  - _consume_pending_fx_hedge: sentinel 1회 소비 + 삭제
"""
from __future__ import annotations

import json
import os

from api.vams import engine as e


def _pf(cash=10_000_000, usdkrw=1507.98):
    return {
        "vams": {"cash": cash, "holdings": [], "total_asset": cash},
        "macro": {"usd_krw": {"value": usdkrw}},
    }


def test_enter_moves_cash_to_reserve():
    p = _pf()
    r = e.enter_fx_hedge(p, krw_amount=3_000_000, usdkrw=1507.98,
                         ticker="455030", name="KODEX USD SOFR", reason="β")
    assert r["ok"] is True
    assert abs(p["vams"]["cash"] - 7_000_000) < 0.01
    res = p["vams"]["fx_hedge_reserve"]
    assert res["ticker"] == "455030"
    assert abs(res["usd_value"] - 3_000_000 / 1507.98) < 1e-6


def test_total_unchanged_at_entry():
    p = _pf()
    e.enter_fx_hedge(p, krw_amount=3_000_000, usdkrw=1507.98,
                     ticker="455030", name="x", reason="β")
    e.recalculate_total(p)
    assert abs(p["vams"]["total_asset"] - 10_000_000) < 0.01


def test_mtm_on_krw_weakness():
    p = _pf()
    e.enter_fx_hedge(p, krw_amount=3_000_000, usdkrw=1500.0,
                     ticker="455030", name="x", reason="β")
    p["macro"]["usd_krw"]["value"] = 1650.0  # KRW 10% 약세
    e.recalculate_total(p)
    res = p["vams"]["fx_hedge_reserve"]
    assert res["pnl_krw"] > 0
    assert abs(res["return_pct"] - 10.0) < 0.1  # +10% FX 이익
    # total = cash 7M + reserve MtM 3.3M
    assert abs(p["vams"]["total_asset"] - (7_000_000 + 3_300_000)) < 1.0


def test_reserve_excluded_from_auto_sell_loop():
    # reserve 는 holdings 가 아니므로 매도 루프(holdings 순회)가 못 건드림.
    p = _pf()
    e.enter_fx_hedge(p, krw_amount=3_000_000, usdkrw=1507.98,
                     ticker="455030", name="x", reason="β")
    assert p["vams"]["holdings"] == []  # reserve 는 holdings 외
    assert "455030" not in [h.get("ticker") for h in p["vams"]["holdings"]]


def test_duplicate_and_overspend_rejected():
    p = _pf()
    e.enter_fx_hedge(p, krw_amount=3_000_000, usdkrw=1507.98, ticker="455030", name="x", reason="β")
    dup = e.enter_fx_hedge(p, krw_amount=1_000_000, usdkrw=1507.98, ticker="455030", name="x", reason="β")
    assert dup["ok"] is False
    p2 = _pf(cash=1_000_000)
    over = e.enter_fx_hedge(p2, krw_amount=3_000_000, usdkrw=1507.98, ticker="455030", name="x", reason="β")
    assert over["ok"] is False


def test_consume_pending_sentinel(tmp_path, monkeypatch):
    sentinel = tmp_path / "pending_fx_hedge.json"
    monkeypatch.setattr(e, "_PENDING_FX_HEDGE_PATH", str(sentinel))
    sentinel.write_text(json.dumps({
        "krw_amount": 3_000_000, "ticker": "455030", "name": "KODEX USD SOFR", "reason": "β",
    }))
    # 1차 소비: 진입 + sentinel 보존 (persist 확정 전 = idempotent 핵심)
    p = _pf()
    e._consume_pending_fx_hedge(p)
    assert p["vams"].get("fx_hedge_reserve") is not None
    assert os.path.exists(sentinel)  # 보존 — persist 안 한 run 이 소비해도 유실 X
    assert abs(p["vams"]["cash"] - 7_000_000) < 0.01

    # 2차 소비 (reserve 이미 존재 = 영속 완료 가정): sentinel 정리 + 이중 진입 X
    e._consume_pending_fx_hedge(p)
    assert not os.path.exists(sentinel)  # job done → 정리
    assert p["vams"]["fx_hedge_reserve"]["ticker"] == "455030"
    assert abs(p["vams"]["cash"] - 7_000_000) < 0.01  # 이중 차감 X


def test_consume_idempotent_non_persisting_run(tmp_path, monkeypatch):
    """비-영속 run 이 소비(진입 but 미저장)해도 sentinel 유지 → 다음 run 재진입."""
    sentinel = tmp_path / "pending_fx_hedge.json"
    monkeypatch.setattr(e, "_PENDING_FX_HEDGE_PATH", str(sentinel))
    spec = {"krw_amount": 3_000_000, "ticker": "455030", "name": "x", "reason": "β"}
    sentinel.write_text(json.dumps(spec))

    # run A (비-영속): 진입하지만 portfolio 버려짐 (저장 안 함)
    pA = _pf()
    e._consume_pending_fx_hedge(pA)
    assert pA["vams"]["fx_hedge_reserve"] is not None
    assert os.path.exists(sentinel)  # 보존 — pA 는 버려질 것

    # run B (영속): fresh load (reserve 없음) → 재진입 → 저장된다고 가정
    pB = _pf()
    e._consume_pending_fx_hedge(pB)
    assert pB["vams"]["fx_hedge_reserve"]["ticker"] == "455030"
    assert os.path.exists(sentinel)  # 아직 보존 (pB persist 후 다음 run 이 정리)
