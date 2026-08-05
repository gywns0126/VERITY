# -*- coding: utf-8 -*-
"""금리 방패 재설계 — 등급 차단 → 사이징 + 백분위 임계 (2026-08-06).

사전등록 = docs/PREREG_YIELD_SHIELD_REDESIGN_2026_08_06.md
  PM 승인 "권고대로 ㄱㄱ" — 안 (가) 확정.

사고: 절대 임계 4.5% 가 실측 분포 중앙값 4.48% 에 놓여 판별력이 최소였고(AUC→0.5),
등급 차단이라 매수 신호가 원천 소멸해 검증 표본까지 봉쇄됐다(aligned BUY 0건).

계약: ① 등급 차단(max_grade) 제거 — 신호 생존 ② 금리 압력은 사이징 배율로만 반영
③ 백분위 기반(상위 20% 하향 시작 · 10% 하한) — 분포 중앙 문제 정의상 해소
④ 표본 <60 이면 페널티 0 + stderr 경고(조용한 실패 금지) ⑤ 총 페널티 cap 0.30 불변.
"""
import api.intelligence.verity_brain as VB


def _hist(monkeypatch, vals):
    monkeypatch.setattr(VB, "_yield_hist_cache", list(vals))


# ── 백분위 산출 ──────────────────────────────────────────────────────

def test_percentile_basic(monkeypatch):
    _hist(monkeypatch, [4.0 + i * 0.01 for i in range(100)])   # 4.00~4.99
    assert VB._yield_percentile(4.50) == 51.0
    assert VB._yield_percentile(4.98) == 99.0


def test_percentile_none_when_sample_too_small(monkeypatch, capsys):
    """표본 부족 = 판정 보류. 🚨 조용히 0 을 반환하지 않고 stderr 로 드러낸다."""
    _hist(monkeypatch, [4.5] * 10)
    assert VB._yield_percentile(4.5) is None
    assert "표본 부족" in capsys.readouterr().err


def test_percentile_none_for_missing_input(monkeypatch):
    _hist(monkeypatch, [4.0 + i * 0.01 for i in range(100)])
    assert VB._yield_percentile(None) is None


# ── 페널티 곡선 ──────────────────────────────────────────────────────

def test_penalty_zero_below_start_threshold(monkeypatch):
    """상위 20% 밖(=80 퍼센타일 미만)은 페널티 0 — 노이즈 대역에 반응하지 않는다."""
    _hist(monkeypatch, [4.0 + i * 0.01 for i in range(100)])
    pen, pct = VB._yield_penalty(4.50)      # ~51 퍼센타일
    assert pen == 0.0 and pct == 51.0


def test_penalty_ramps_between_80_and_90(monkeypatch):
    _hist(monkeypatch, [4.0 + i * 0.01 for i in range(100)])
    p80, _ = VB._yield_penalty(4.79)        # 80 퍼센타일 = 시작점
    p85, _ = VB._yield_penalty(4.84)        # 중간
    p90, _ = VB._yield_penalty(4.89)        # 90 = 하한 도달
    assert p80 == 0.0
    assert 0 < p85 < VB._YIELD_MAX_PENALTY
    assert p90 == VB._YIELD_MAX_PENALTY


def test_penalty_capped_at_extreme(monkeypatch):
    """극단 금리에서도 상한 초과 금지 — 사이징은 완만하게(이진 차단 아님)."""
    _hist(monkeypatch, [4.0 + i * 0.01 for i in range(100)])
    pen, _ = VB._yield_penalty(99.0)
    assert pen == VB._YIELD_MAX_PENALTY


def test_penalty_zero_when_sample_insufficient(monkeypatch):
    _hist(monkeypatch, [4.9] * 10)
    assert VB._yield_penalty(4.9)[0] == 0.0


# ── 배율 합류 ────────────────────────────────────────────────────────

def _pf(y10):
    return {"macro": {"us_10y": {"value": y10}}, "market_horizon": {"cape_percentile": 50.0}}


def test_multiplier_includes_yield_penalty(monkeypatch):
    _hist(monkeypatch, [4.0 + i * 0.01 for i in range(100)])
    stock = {"pbr": 1.0, "currency": "KRW"}
    lo, meta_lo = VB._compute_macro_multiplier(stock, _pf(4.50))   # 51 퍼센타일
    hi, meta_hi = VB._compute_macro_multiplier(stock, _pf(4.95))   # 96 퍼센타일
    assert meta_lo["yield_penalty"] == 0.0
    assert meta_hi["yield_penalty"] == VB._YIELD_MAX_PENALTY
    assert hi < lo                                   # 고금리일수록 배율 축소


def test_multiplier_respects_total_cap(monkeypatch):
    """금리 축을 더해도 총 페널티 cap 0.30 은 불변 (등록 §4)."""
    _hist(monkeypatch, [4.0 + i * 0.01 for i in range(100)])
    stock = {"pbr": 99.0, "currency": "KRW"}          # 밸류 페널티 최대
    pf = _pf(4.99)
    pf["macro"]["usd_krw"] = {"value": 9999}          # 환율 페널티 최대
    pf["market_horizon"]["cape_percentile"] = 100.0   # CAPE 최대
    m, meta = VB._compute_macro_multiplier(stock, pf)
    assert meta["total_penalty"] <= 0.30
    assert m >= 0.70


def test_meta_exposes_percentile_for_reproducibility(monkeypatch):
    """등록 §4 — 백분위를 관측 필드로 동시 기록(재현 가능성)."""
    _hist(monkeypatch, [4.0 + i * 0.01 for i in range(100)])
    _, meta = VB._compute_macro_multiplier({"pbr": 1.0, "currency": "KRW"}, _pf(4.95))
    assert meta["inputs"]["us_10y"] == 4.95
    assert meta["inputs"]["us_10y_percentile"] == 96.0
    assert "PREREG_YIELD_SHIELD_REDESIGN" in meta["rule_reference"]


# ── 등급 차단 제거 ───────────────────────────────────────────────────

def test_yield_rule_no_longer_caps_grade(monkeypatch):
    """🚨 핵심 계약 — 고금리 단독으로는 등급이 강등되지 않는다(관측만 남는다)."""
    _hist(monkeypatch, [4.0 + i * 0.01 for i in range(100)])
    ov = VB.detect_macro_override({"macro": {"us_10y": {"value": 4.95}}})
    assert ov is not None and ov["mode"] == "yield_observation"
    assert "max_grade" not in ov                       # 등급 상한 없음 = 강등 없음
    assert "yield_defense" not in str(ov)


def test_yield_rule_silent_below_threshold(monkeypatch):
    _hist(monkeypatch, [4.0 + i * 0.01 for i in range(100)])
    assert VB.detect_macro_override({"macro": {"us_10y": {"value": 3.0}}}) is None


def test_other_shields_still_cap_grade(monkeypatch):
    """등록 §4 — VIX 패닉 등 다른 방패는 범위 밖. 등급 차단이 그대로 살아 있어야 한다."""
    _hist(monkeypatch, [4.0 + i * 0.01 for i in range(100)])
    ov = VB.detect_macro_override({"macro": {"vix": {"value": 40}, "us_10y": {"value": 4.95}}})
    assert ov["max_grade"] == "WATCH"                  # 패닉이 primary
    modes = {s["mode"] for s in ov.get("secondary_signals", [])} | {ov["mode"]}
    assert "yield_observation" in modes                # 금리는 관측으로 병기
