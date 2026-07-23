"""2026-07-24 2차 산식 감사 Class A — fail-open + dead 컴포넌트 fix 검증.

키스톤: 결측 데이터가 '중립' 아닌 '강신호'로 붕괴(fail-open) + 소비자-생산자 계약 드리프트로
컴포넌트 영구 dead. origin/main 감사 + 실데이터 검증 후 fix.
- CANSLIM C: 미존재 consensus.eps_growth_* → 실 소스 eps_quarterly_growth(%)
- CANSLIM N: signals 어휘 미매칭(dead) → drop_from_high_pct 직접
- CANSLIM L: drop 결측 default 0(=신고가) → 부당 +8 차단
- Graham: 결측 PBR sentinel(1.0)이 복합기준 +10 부당획득 → sentinel skip
- feature_drift: brain_score/vci top-level 오독(항상 None) → verity_brain 중첩 정정(게이트 복구)
"""
from __future__ import annotations

from api.intelligence.factors.canslim import _compute_canslim_score
from api.intelligence.factors.graham import _compute_graham_score
from api.observability.feature_drift import extract_features


# ── CANSLIM C: 실 소스로 발화 (옛날 dead) ──

def test_canslim_c_fires_on_eps_quarterly_growth():
    high = _compute_canslim_score({"currency": "USD", "eps_quarterly_growth": 50})
    none_g = _compute_canslim_score({"currency": "USD"})
    assert high > none_g  # C 발화 → 점수 상승
    assert high >= 64  # 50 base + 15 (>=50 성장)


def test_canslim_c_ignores_dead_consensus_field():
    # 옛 미존재 필드(consensus.eps_growth_*)는 이제 무시 — eps_quarterly_growth 만 소스.
    via_dead = _compute_canslim_score({"currency": "USD", "consensus": {"eps_growth_qoq_pct": 99}})
    assert via_dead == 50.0  # dead 필드로는 C 미발화


def test_canslim_c_negative_growth_penalized():
    low = _compute_canslim_score({"currency": "USD", "eps_quarterly_growth": -30})
    assert low < 50.0  # 음성장 감점


# ── CANSLIM L: fail-open 차단 (drop 결측 → 부당 +8 없음) ──

def test_canslim_l_no_bonus_when_drop_missing():
    missing = _compute_canslim_score({"currency": "USD"})
    assert missing == 50.0  # drop 결측 → L 미발화 (옛날 default 0 → +8 이었음)


def test_canslim_l_fires_on_real_near_high():
    near = _compute_canslim_score({"currency": "USD", "drop_from_high_pct": -2})
    assert near > 50.0  # 실제 신고가 근접 → L(+8)


# ── CANSLIM N: drop_from_high 직접 (옛 키워드 매칭 dead) ──

def test_canslim_n_fires_near_high():
    # drop 3% 이내 = 신고가권 → N(+5). (L 과 합산되나 N 기여 검증 = 3% 경계 안팎 비교)
    inside = _compute_canslim_score({"currency": "USD", "drop_from_high_pct": -2})   # L+8, N+5
    edge = _compute_canslim_score({"currency": "USD", "drop_from_high_pct": -10})    # L+3, N 0
    assert inside > edge  # 신고가권이 더 높음 (N 발화 기여)


# ── Graham: sentinel PBR 복합기준 skip ──

def test_graham_sentinel_pbr_skips_composite():
    real = _compute_graham_score({"per": 10, "pbr": 1.5})            # 복합 +10
    sentinel = _compute_graham_score({"per": 10, "pbr": 1.0, "pbr_normalized_neutral": True})
    assert real - sentinel == 10  # sentinel 은 복합 +10 미획득


def test_graham_real_low_pbr_still_gets_composite():
    # 진짜 낮은 PBR (normalized_neutral 아님) 은 복합기준 정상 획득.
    real = _compute_graham_score({"per": 10, "pbr": 1.5})
    no_composite = _compute_graham_score({"per": 10, "pbr": 6.0})  # pb_pe=60>50 → -8
    assert real > no_composite


# ── feature_drift: 중첩 추출 복구 (게이트 무력화 fix) ──

def _pf():
    return {"recommendations": [
        {"per": 10, "pbr": 1, "roe": 0.1, "debt_ratio": 50,
         "verity_brain": {"brain_score": 60, "grade": "BUY", "vci": {"vci": 20}}},
        {"per": 12, "pbr": 2, "roe": 0.2, "debt_ratio": 40,
         "verity_brain": {"brain_score": 40, "grade": "AVOID", "vci": {"vci": 10}}},
    ]}


def test_drift_avg_brain_score_from_nested():
    f = extract_features(_pf())
    assert f.get("avg_brain_score") == 50.0  # (60+40)/2 — 옛날 top-level 오독으로 None 이었음


def test_drift_vci_avg_from_nested():
    f = extract_features(_pf())
    assert f.get("vci_avg") == 15.0  # (20+10)/2 — 옛날 미존재 소스로 None 이었음


def test_drift_gate_signals_no_longer_all_none():
    # 게이트 무력화 회귀 가드: 3 핵심 신호(brain/grade/vci) 전부 산출돼야.
    f = extract_features(_pf())
    assert f.get("avg_brain_score") is not None
    assert f.get("vci_avg") is not None
    assert f.get("grade_distribution_buy_pct") is not None
