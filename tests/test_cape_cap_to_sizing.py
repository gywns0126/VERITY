# -*- coding: utf-8 -*-
"""CAPE 버블 등급 차단 → 사이징 일원화 (2026-08-06).

사전등록 = docs/PREREG_CAPE_BUBBLE_CAP_2026_08_06.md
  PM 승인 "권고대로 ㄱㄱ" — 안 (가) 확정.

사고: 임계 30 이 자체 관측 범위(39.9~42.8) **밖**이라 조건부 규칙이 아니라 상수였다.
발행 스냅샷 87일 중 등급 cap 이 0개인 날 = 0일 → BUY 등급이 구조적으로 영구 0.
게다가 헌법 원문 action 은 "포지션 대폭 축소"(사이징)인데 구현이 등급 차단으로 승격했고,
cape_penalty 로 사이징에 이미 반영 중이라 같은 신호를 두 번 적용했다.

계약: ① cape_bubble 등급 차단 제거 → cape_observation(표시 전용) ② cape_penalty 상한
0.075 → 0.10 (기울기 유지) ③ 총 페널티 cap 0.30 불변 ④ 다른 방패 무변경
⑤ 🚨 개명이 fact.py 위기장 게이트를 죽이지 않는다(발동률 붕괴 금지).
"""
import api.intelligence.verity_brain as VB
from api.intelligence.factors.fact import _PANIC_OVERRIDE_MODES, _is_regime_panic


def _hist(monkeypatch, vals=None):
    # 금리 축을 고정해 CAPE 축만 관측한다
    monkeypatch.setattr(VB, "_yield_hist_cache", list(vals or [4.0] * 100))


def _pf(cape=42.3, cape_pct=99.0):
    return {"macro": {"fred": {"cape": {"value": cape}}},
            "market_horizon": {"cape_percentile": cape_pct}}


# ── 등급 차단 제거 ───────────────────────────────────────────────────

def test_cape_no_longer_caps_grade(monkeypatch):
    """🚨 핵심 계약 — CAPE 고평가 단독으로는 등급이 강등되지 않는다."""
    _hist(monkeypatch)
    ov = VB.detect_macro_override(_pf(cape=42.3))
    assert ov is not None and ov["mode"] == "cape_observation"
    assert "max_grade" not in ov
    assert "cape_bubble" not in str(ov)


def test_cape_silent_below_threshold(monkeypatch):
    """임계(30) 미만이면 관측 표기조차 없다 — 기존 조건 유지."""
    _hist(monkeypatch)
    assert VB.detect_macro_override(_pf(cape=25.0)) is None


def test_cape_observation_does_not_beat_real_cap(monkeypatch):
    """관측은 심각도 0 — 실제 방패가 있으면 primary 를 빼앗지 않는다."""
    _hist(monkeypatch)
    pf = _pf(cape=42.3)
    pf["macro"]["vix"] = {"value": 40}          # 패닉
    ov = VB.detect_macro_override(pf)
    assert ov["mode"] == "panic" and ov["max_grade"] == "WATCH"
    modes = {s["mode"] for s in ov.get("secondary_signals", [])}
    assert "cape_observation" in modes


# ── 사이징 흡수 ──────────────────────────────────────────────────────

def test_cape_penalty_cap_raised_to_10pct(monkeypatch):
    """등급 차단이 하던 방어를 사이징이 흡수 — 상한 0.075 → 0.10."""
    _hist(monkeypatch)
    stock = {"pbr": 1.0, "currency": "KRW"}
    _, meta = VB._compute_macro_multiplier(stock, _pf(cape_pct=100.0))
    assert meta["cape_penalty"] == 0.10


def test_cape_penalty_slope_unchanged(monkeypatch):
    """기울기 무변경 — 90 퍼센타일 시작, 백분위 1당 1.5%p. 상한만 이동했다."""
    _hist(monkeypatch)
    stock = {"pbr": 1.0, "currency": "KRW"}
    for pct, want in [(89.0, 0.0), (90.0, 0.0), (92.0, 0.03), (95.0, 0.075)]:
        _, meta = VB._compute_macro_multiplier(stock, _pf(cape_pct=pct))
        assert meta["cape_penalty"] == want, f"cape_pct={pct}"


def test_cape_penalty_saturates_at_96_7(monkeypatch):
    """(pct-90)/10*0.15 = 0.10 → pct ≈ 96.7 에서 포화. 그 이상은 평평."""
    _hist(monkeypatch)
    stock = {"pbr": 1.0, "currency": "KRW"}
    a = VB._compute_macro_multiplier(stock, _pf(cape_pct=96.7))[1]["cape_penalty"]
    b = VB._compute_macro_multiplier(stock, _pf(cape_pct=100.0))[1]["cape_penalty"]
    assert a == b == 0.10


def test_total_cap_still_030(monkeypatch):
    """등록 §4 — CAPE 상한을 올려도 총 페널티 cap 0.30 은 불변."""
    _hist(monkeypatch, [4.0 + i * 0.01 for i in range(100)])
    pf = _pf(cape_pct=100.0)
    pf["macro"]["usd_krw"] = {"value": 9999}
    pf["macro"]["us_10y"] = {"value": 4.99}
    m, meta = VB._compute_macro_multiplier({"pbr": 99.0, "currency": "KRW"}, pf)
    assert meta["total_penalty"] <= 0.30 and m >= 0.70


# ── 🚨 개명이 죽이는 것들 ────────────────────────────────────────────

def test_panic_gate_knows_new_mode_names():
    """개명된 mode 가 위기장 집합에 등재돼 있어야 한다.

    2026-08-02 에 같은 클래스 사고(panic_stage_1 vs panic_stage1 철자 불일치)로 게이트가
    죽었고, 2026-08-06 개명이 두 번째 재발 경로였다. 실측: 방치 시 89.7% → 28.7%.
    """
    for m in ("cape_observation", "yield_observation"):
        assert m in _PANIC_OVERRIDE_MODES, f"{m} 미등재 — 위기장 게이트가 죽는다"
    for m in ("cape_bubble", "yield_defense"):
        assert m in _PANIC_OVERRIDE_MODES, f"{m} 제거됨 — 과거 발행물 재독 시 매치 상실"


def test_panic_gate_scans_secondary_signals():
    """관측 mode 는 심각도 0 이라 primary 가 되기 어렵다 — secondary 도 봐야 게이트가 산다."""
    ov = {"mode": "credit_complacency", "max_grade": "BUY",
          "secondary_signals": [{"mode": "cape_observation", "max_grade": None}]}
    assert _is_regime_panic(None, ov) is True


def test_panic_gate_still_false_when_calm():
    ov = {"mode": "credit_complacency", "max_grade": "BUY",
          "secondary_signals": [{"mode": "oil_news_reaction", "max_grade": "BUY"}]}
    assert _is_regime_panic({"macro": {"vix": {"value": 15}}}, ov) is False


def test_panic_gate_vix_path_intact():
    assert _is_regime_panic({"macro": {"vix": {"value": 31}}}, None) is True


def test_panic_gate_survives_missing_secondary():
    """secondary_signals 부재·None 요소에도 죽지 않는다."""
    assert _is_regime_panic(None, {"mode": "cape_observation"}) is True
    assert _is_regime_panic(None, {"mode": "x", "secondary_signals": [None]}) is False


# ── 헌법 정합 ────────────────────────────────────────────────────────

def test_constitution_action_is_sizing_not_grade_block():
    """등록 §1(b) — 헌법 원문은 '포지션 축소'(사이징)다. 원문을 바꾸지 않는다."""
    import json
    import os
    # DATA_DIR 은 테스트에서 tmp 로 우회되므로 repo 원본을 직접 읽는다
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(repo, "data", "verity_constitution.json"), encoding="utf-8") as f:
        c = json.load(f)

    def find(o):
        if isinstance(o, dict):
            if "cape_bubble_mode" in o:
                return o["cape_bubble_mode"]
            for v in o.values():
                r = find(v)
                if r:
                    return r
        return None

    mode = find(c)
    assert mode is not None
    assert "포지션" in mode["action"]          # 사이징 지시
    assert "등급" not in mode["action"]        # 등급 차단 지시가 아니다
