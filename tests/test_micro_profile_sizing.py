# -*- coding: utf-8 -*-
"""max_per_stock 스케일 불변화 — PREREG_MICRO_PROFILE_2026_08_25 (PM 승인·RULE 7 쿼터 1).

사고 = 절대액 200만이 100만 시드에서 무력화 → 현금×0.9 만 남아 **1종목 50~90% 집중**
(엔진 함수 실측 · 90% 단일 인용은 §6-보정으로 정정된 과장이었다).

🚨 배선 전 검산에서 등록문의 "1,000만 무영향" 도 틀린 것을 발견했다 — 현재 시뮬 총자산이
972.9만이라 20% 비율이 **이미 바인딩**된다(−2.7%). 의도된 스케일 불변으로 수용·기재.
이 테스트는 그 경계들을 고정한다.
"""
from api.vams.engine import _effective_max_per_stock


ABS = 2_000_000


def test_above_10m_absolute_binds():
    """총자산 ≥ 1,000만 — 절대액이 더 작아 현행과 동일."""
    cap, binding = _effective_max_per_stock(ABS, {"total_asset": 12_000_000})
    assert (cap, binding) == (ABS, "max_per_stock_abs")


def test_current_sim_asset_pct_binds_minus_2_7pct():
    """🚨 등록 §2-보정 경계 — 972.9만에서 비율이 바인딩되고 2.7% 축소가 의도된 동작."""
    ta = 9_729_171
    cap, binding = _effective_max_per_stock(ABS, {"total_asset": ta})
    assert binding == "total_asset_pct"
    assert cap == ta * 0.20
    assert 0.026 < 1 - cap / ABS < 0.028


def test_micro_seed_diversifies():
    """100만 시드 — 종목당 20만 = 시드의 20%. 현금×0.9(90만)가 아니라 이게 잡혀야 한다."""
    cap, binding = _effective_max_per_stock(ABS, {"total_asset": 1_000_000})
    assert (cap, binding) == (200_000, "total_asset_pct")
    # execute_buy 의 base = min(cap, cash*0.9) — 시드 전액 현금이어도 20만이 바인딩
    assert min(cap, 1_000_000 * 0.9) == 200_000


def test_missing_or_zero_asset_falls_back_to_absolute():
    """🚨 총자산 결측/0 → 절대액 폴백. 비율×0 으로 사이징이 조용히 죽으면 안 된다."""
    for vams in ({}, {"total_asset": 0}, {"total_asset": None}, {"total_asset": "x"}):
        cap, binding = _effective_max_per_stock(ABS, vams)
        assert (cap, binding) == (ABS, "max_per_stock_abs"), vams


def test_executor_reports_which_cap_bound():
    """sizing_chain 이 abs/pct 어느 쪽이 바인딩했는지 신고하는지 (표시≠집행 계열 가드)."""
    import inspect
    from api.vams import engine
    src = inspect.getsource(engine.execute_buy)
    assert "max_per_stock_binding" in src
    assert "_effective_max_per_stock" in src
