# -*- coding: utf-8 -*-
"""measurement_audit 검사 G·H·I (2026-08-11 신설).

셋 다 "에러 0 · 값 채워짐 · 실제로는 안 잰 것" 유형을 잡는다. A~F 로는 안 잡혔다.
"""
import json
import os

from api.observability import measurement_audit as MA


def _write(tmp_path, name, doc, monkeypatch):
    monkeypatch.setattr(MA, "DATA_DIR", str(tmp_path))
    with open(os.path.join(tmp_path, name), "w", encoding="utf-8") as f:
        json.dump(doc, f)


def _pf(holdings):
    return {"vams": {"holdings": holdings}}


# ── G. 가드 입력 ────────────────────────────────────────────────────────────
def test_guard_inputs_detects_all_dead(tmp_path, monkeypatch):
    _write(tmp_path, "portfolio.json",
           _pf([{"name": "A", "quantity": 1}, {"name": "B", "quantity": 2}]), monkeypatch)
    r = MA.audit_guard_inputs()
    assert r["ok"] is False
    assert {d["field"] for d in r["dead_guards"]} == {"sector", "beta", "quant_factors"}


def test_guard_inputs_ok_when_filled(tmp_path, monkeypatch):
    h = {"name": "A", "quantity": 1, "sector": "Tech", "beta": 1.1,
         "multi_factor": {"quant_factors": {"momentum": 55}}}
    _write(tmp_path, "portfolio.json", _pf([h]), monkeypatch)
    assert MA.audit_guard_inputs()["ok"] is True


def test_guard_inputs_partial_still_fails(tmp_path, monkeypatch):
    """일부만 채워도 전무한 축이 있으면 FAIL — 가드는 개별로 죽는다."""
    h = {"name": "A", "quantity": 1, "sector": "Tech"}
    _write(tmp_path, "portfolio.json", _pf([h]), monkeypatch)
    r = MA.audit_guard_inputs()
    assert r["ok"] is False
    assert {d["field"] for d in r["dead_guards"]} == {"beta", "quant_factors"}


# ── H. 출구 경로 ────────────────────────────────────────────────────────────
_TARGETS = {"target_1": {"price": 150.0, "exit_pct": 50.0},
            "target_2": {"price": 200.0, "exit_pct": 30.0}}


def test_exit_paths_flags_single_share_winner(tmp_path, monkeypatch):
    h = {"name": "1주승자", "quantity": 1, "return_pct": 29.0, "current_price": 160.0,
         "trailing_active": False, "exit_targets": _TARGETS}
    _write(tmp_path, "portfolio.json", _pf([h]), monkeypatch)
    r = MA.audit_exit_paths()
    assert r["ok"] is False
    assert r["no_profit_exit"][0]["name"] == "1주승자"


def test_exit_paths_ok_when_trailing_active(tmp_path, monkeypatch):
    h = {"name": "1주승자", "quantity": 1, "return_pct": 29.0, "current_price": 210.0,
         "trailing_active": True, "exit_targets": _TARGETS}
    _write(tmp_path, "portfolio.json", _pf([h]), monkeypatch)
    r = MA.audit_exit_paths()
    assert r["ok"] is True
    assert r["ladder_broken"]          # 분할 불가는 잔존 — 따로 센다


def test_exit_paths_ignores_losers(tmp_path, monkeypatch):
    """손실 중이면 기간손절(return<=0)이 출구다 — 확정 경로 부재가 아니다."""
    h = {"name": "1주패자", "quantity": 1, "return_pct": -3.0, "current_price": 90.0,
         "trailing_active": False, "exit_targets": _TARGETS}
    _write(tmp_path, "portfolio.json", _pf([h]), monkeypatch)
    assert MA.audit_exit_paths()["ok"] is True


# ── I. as_of 노후 ───────────────────────────────────────────────────────────
def test_as_of_missing_is_a_defect(tmp_path, monkeypatch):
    """as_of 가 없으면 노후를 구조적으로 확인할 수 없다 = 결함."""
    _write(tmp_path, "bonds.json",
           {"updated_at": "2026-08-11T07:00:00+09:00",
            "kr_corp_spreads": {"grades": {}}, "yield_curves": {"kr": {"curve": []}}},
           monkeypatch)
    r = MA.audit_as_of_staleness()
    assert r["ok"] is False and len(r["missing_as_of"]) == 2


def test_as_of_stale_beyond_limit(tmp_path, monkeypatch):
    _write(tmp_path, "bonds.json",
           {"updated_at": "2026-08-11T07:00:00+09:00",
            "kr_corp_spreads": {"date": "20260727"},
            "yield_curves": {"kr": {"curve_as_of": "20260727"}}}, monkeypatch)
    r = MA.audit_as_of_staleness()
    assert r["ok"] is False
    assert all(x["lag_days"] == 15 for x in r["stale_axes"])


def test_as_of_fresh_passes(tmp_path, monkeypatch):
    _write(tmp_path, "bonds.json",
           {"updated_at": "2026-08-11T07:00:00+09:00",
            "kr_corp_spreads": {"date": "20260810"},
            "yield_curves": {"kr": {"curve_as_of": "20260810"}}}, monkeypatch)
    assert MA.audit_as_of_staleness()["ok"] is True
