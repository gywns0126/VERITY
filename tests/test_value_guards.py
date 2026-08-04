# -*- coding: utf-8 -*-
"""신호 필터 F2(사이클 업종 가드)·F3(이익의 질 게이트) — PREREG_SIGNAL_FILTERS_2026_08_04.

핵심 계약: 결측 ≠ 발동 (데이터 부족·무키·비사이클 = 가드 비활성/미발동) /
F2 = graham 가치 가점 무효 / F3 = 50% / 감점·재무건전성 가점 불변.
사례 회귀: 동우팜형(F2 사이클 피크) · 제이엠티형(F3 영업외 비중).
"""
import api.intelligence.value_guards as vg
from api.intelligence.factors.graham import _compute_graham_score


# 동우팜형 피크 시계열 — 2024 영업적자 → 2025 급증 (5년 중앙값 40 × 2 < 당해 300)
PEAK_OP = {"2025": 300.0, "2024": -50.0, "2023": 40.0, "2022": 30.0, "2021": 60.0}
FLAT_NET = {"2025": 250.0, "2024": -40.0, "2023": 35.0, "2022": 25.0, "2021": 50.0}


def _prime(monkeypatch, tmp_path, corp="00000001", ticker="088910",
           induty="10121", op=None, net=None):
    monkeypatch.setattr(vg, "CACHE_PATH", str(tmp_path / "vg_cache.json"))
    monkeypatch.setattr(vg, "RAW_CACHE_DIR", str(tmp_path / "raw"))
    monkeypatch.setattr(vg, "DART_API_KEY", "")  # 네트워크 차단 — fetch 경로 봉인
    monkeypatch.setattr(vg, "_mapping", {ticker: corp})
    monkeypatch.setattr(vg, "_cache", {corp: {
        "induty": induty, "op_income": dict(op or {}), "net_income": dict(net or {})}})


def test_f2_cycle_peak_triggers(monkeypatch, tmp_path):
    # 동우팜 사례형: 축산/식료품(KSIC 10) ∧ 직전 3년 적자 ∧ 당해 > 5년 중앙값×2
    _prime(monkeypatch, tmp_path, op=PEAK_OP, net=FLAT_NET)
    g = vg.evaluate_value_guards({"ticker": "088910"})
    assert g["active"] and g["cycle_peak_guard"] is True
    assert g["detail_f2"]["year"] == 2025


def test_f2_noncycle_sector_never_triggers(monkeypatch, tmp_path):
    # 같은 숫자라도 비사이클 업종(KSIC 58 출판)이면 미발동 — 목록 LOCKED
    _prime(monkeypatch, tmp_path, induty="58211", op=PEAK_OP, net=FLAT_NET)
    g = vg.evaluate_value_guards({"ticker": "088910"})
    assert g["cycle_peak_guard"] is False


def test_f2_insufficient_years_no_trigger(monkeypatch, tmp_path):
    # 5년 중앙값 요건 — 4개년뿐이면 미발동 (결측 ≠ 발동)
    op4 = {k: v for k, v in PEAK_OP.items() if k != "2021"}
    _prime(monkeypatch, tmp_path, op=op4, net=FLAT_NET)
    g = vg.evaluate_value_guards({"ticker": "088910"})
    assert g["cycle_peak_guard"] is False


def test_f2_no_prior_deficit_no_trigger(monkeypatch, tmp_path):
    # 직전 3년 적자 없음 → 급증만으론 미발동
    op = dict(PEAK_OP, **{"2024": 20.0})
    _prime(monkeypatch, tmp_path, op=op, net=FLAT_NET)
    g = vg.evaluate_value_guards({"ticker": "088910"})
    assert g["cycle_peak_guard"] is False


def test_f3_nonop_ratio_triggers(monkeypatch, tmp_path):
    # 제이엠티 사례형: 순이익 100 중 영업 55 → 영업외 45% > 30%
    _prime(monkeypatch, tmp_path, ticker="094970", induty="26429",
           op={"2025": 55.0, "2024": 50.0}, net={"2025": 100.0, "2024": 90.0})
    g = vg.evaluate_value_guards({"ticker": "094970"})
    assert g["earnings_quality"] is True
    assert g["detail_f3"]["leg"] == "nonop_ratio"


def test_f3_negative_net_income_skipped(monkeypatch, tmp_path):
    # 순이익 ≤ 0 = 저PER 가점 자체가 없음 → 게이트 불필요 (미발동)
    _prime(monkeypatch, tmp_path, op={"2025": 10.0}, net={"2025": -5.0})
    g = vg.evaluate_value_guards({"ticker": "088910"})
    assert g["earnings_quality"] is False


def test_f3_fcf_leg_triggers_when_extracted(monkeypatch, tmp_path):
    # 영업외 정상(5%) but FCF/순이익 0.3 < 0.5 → FCF 다리 발동
    _prime(monkeypatch, tmp_path, op={"2025": 95.0}, net={"2025": 100.0})
    stock = {"ticker": "088910", "dart_financials": {"cashflow": {
        "operating": 120.0, "investing": -90.0, "financing": 0, "free_cashflow": 30.0}}}
    g = vg.evaluate_value_guards(stock)
    assert g["earnings_quality"] is True
    assert g["detail_f3"]["leg"] == "fcf_ni"


def test_f3_fcf_leg_skipped_when_unextracted(monkeypatch, tmp_path):
    # cashflow 전부 0 = 미추출 마커 → FCF 다리 skip (결측 ≠ 발동)
    _prime(monkeypatch, tmp_path, op={"2025": 95.0}, net={"2025": 100.0})
    stock = {"ticker": "088910", "dart_financials": {"cashflow": {
        "operating": 0, "investing": 0, "financing": 0, "free_cashflow": 0}}}
    g = vg.evaluate_value_guards(stock)
    assert g["earnings_quality"] is False


def test_us_stock_not_evaluated(monkeypatch, tmp_path):
    _prime(monkeypatch, tmp_path)
    assert vg.evaluate_value_guards({"ticker": "AAPL", "currency": "USD"}) is None


def test_no_corp_mapping_inactive(monkeypatch, tmp_path):
    _prime(monkeypatch, tmp_path)
    g = vg.evaluate_value_guards({"ticker": "999999"})
    assert g["active"] is False and not g["cycle_peak_guard"]


# ── graham 통합 — 가점 스케일 (F2=0 / F3=0.5 / 무가드=1.0) ────────────────────

def _value_stock(**extra):
    # PER 2 · PBR 0.5 → 저PER +12, 복합(1.0≤22.5) +10. PEG 입력 없음. 재무건전성 중립대.
    s = {"ticker": "088910", "kis_financial_ratio": {
        "source": "kis", "per": 2.0, "pbr": 0.5, "debt_ratio": 120, "roe": 10, "current_ratio": 150}}
    s.update(extra)
    return s


def test_graham_f2_zeroes_value_bonus():
    base = _compute_graham_score(_value_stock())
    gated = _compute_graham_score(_value_stock(value_guards={"cycle_peak_guard": True}))
    assert base - gated == 22  # +12(저PER) +10(복합) 전액 무효


def test_graham_f3_halves_value_bonus():
    base = _compute_graham_score(_value_stock())
    gated = _compute_graham_score(_value_stock(value_guards={"earnings_quality": True}))
    assert base - gated == 11  # 22 × 0.5


def test_graham_penalties_unchanged_under_guard():
    # 고PER 감점(-8)은 가드와 무관 — 가점만 스케일
    hi = {"ticker": "088910", "kis_financial_ratio": {
        "source": "kis", "per": 40.0, "pbr": 3.0, "debt_ratio": 120, "roe": 10, "current_ratio": 150}}
    assert _compute_graham_score(dict(hi)) == _compute_graham_score(
        dict(hi, value_guards={"cycle_peak_guard": True}))
