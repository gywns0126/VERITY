"""ic_stats 단위 테스트 — Shadow Funnel Scoring Spec v0 산식 검증.

2026-06-08. 합성 데이터로 알려진 성질 검증 (known-answer + 부호/단조 sanity).
"""
import math

import numpy as np
import pytest

from api.intelligence import ic_stats as IC


# ── rank_ic ──────────────────────────────────────────────────────────


def test_rank_ic_perfect_positive():
    scores = [1, 2, 3, 4, 5]
    rets = [0.1, 0.2, 0.3, 0.4, 0.5]
    ic, p = IC.rank_ic(scores, rets, method="kendall")
    assert ic == pytest.approx(1.0)
    ic_s, _ = IC.rank_ic(scores, rets, method="spearman")
    assert ic_s == pytest.approx(1.0)


def test_rank_ic_perfect_negative():
    scores = [1, 2, 3, 4, 5]
    rets = [0.5, 0.4, 0.3, 0.2, 0.1]
    ic, _ = IC.rank_ic(scores, rets, method="spearman")
    assert ic == pytest.approx(-1.0)


def test_rank_ic_degenerate_returns_none():
    # 분산 0 (모두 동일) → None
    assert IC.rank_ic([1, 1, 1, 1], [0.1, 0.2, 0.3, 0.4])[0] is None
    # 표본 < 3 → None
    assert IC.rank_ic([1, 2], [0.1, 0.2])[0] is None


def test_rank_ic_handles_nan():
    scores = [1, 2, 3, 4, float("nan")]
    rets = [0.1, 0.2, 0.3, 0.4, 0.9]
    ic, _ = IC.rank_ic(scores, rets, method="spearman")
    assert ic == pytest.approx(1.0)  # nan 쌍 제거 후 완전 단조


# ── bootstrap CI ─────────────────────────────────────────────────────


def test_bootstrap_ci_reproducible_and_bounds():
    rng = np.random.default_rng(1)
    scores = rng.normal(size=40)
    rets = scores * 0.5 + rng.normal(size=40) * 0.5  # 양의 관계
    m1, lo1, hi1 = IC.bootstrap_ic_ci(scores, rets, seed=42)
    m2, lo2, hi2 = IC.bootstrap_ic_ci(scores, rets, seed=42)
    assert (m1, lo1, hi1) == (m2, lo2, hi2)  # seed 고정 = 재현
    assert lo1 <= m1 <= hi1
    assert m1 > 0  # 양의 관계


# ── Newey-West ───────────────────────────────────────────────────────


def test_auto_maxlags_rule():
    # max(h-1, ceil(0.75 T^(1/3)))
    assert IC._auto_maxlags(T=27, horizon_days=5) == max(4, math.ceil(0.75 * 3))  # =4
    assert IC._auto_maxlags(T=1000, horizon_days=5) == math.ceil(0.75 * 1000 ** (1 / 3))


def test_newey_west_positive_mean_iid():
    # iid 양의 평균 IC 시계열 → t-stat 양수
    rng = np.random.default_rng(2)
    ics = 0.08 + rng.normal(0, 0.05, size=300)
    res = IC.newey_west_tstat(ics, horizon_days=5)
    assert res["mean_ic"] == pytest.approx(0.08, abs=0.02)
    assert res["nw_tstat"] > 2.0
    assert res["maxlags"] >= 4


def test_newey_west_widens_se_under_autocorr():
    # 양의 자기상관 시리즈 → NW SE 가 단순 SE 보다 커야 (t 작아짐)
    rng = np.random.default_rng(3)
    T = 400
    e = rng.normal(0, 0.05, size=T)
    x = np.empty(T)
    x[0] = 0.08 + e[0]
    for i in range(1, T):
        x[i] = 0.08 + 0.6 * (x[i - 1] - 0.08) + e[i]  # AR(1) ρ=0.6
    nw = IC.newey_west_tstat(x, horizon_days=10)
    simple_se = x.std(ddof=1) / math.sqrt(T)
    assert nw["nw_se"] > simple_se  # 자기상관 반영 → SE 확대


def test_newey_west_too_short():
    assert IC.newey_west_tstat([0.1], horizon_days=5)["nw_tstat"] is None


# ── effective N / cross-correction ───────────────────────────────────


def test_effective_n_independent_equals_n():
    C = np.eye(5)
    assert IC.effective_n_from_corr(C) == pytest.approx(5.0)
    assert IC.cross_correction_multiplier(C) == pytest.approx(1.0)


def test_effective_n_high_corr_shrinks():
    N = 10
    C = np.full((N, N), 0.8)
    np.fill_diagonal(C, 1.0)
    n_eff = IC.effective_n_from_corr(C)
    assert n_eff < N  # 상관 높으면 유효 N 감소
    assert n_eff == pytest.approx(N / (1 + (N - 1) * 0.8))
    assert IC.cross_correction_multiplier(C) > 1.0  # SE 확대


def test_cross_correction_negative_corr_clamped():
    N = 5
    C = np.full((N, N), -0.1)
    np.fill_diagonal(C, 1.0)
    # 음상관 과보정 방지 → 승수 >= 1
    assert IC.cross_correction_multiplier(C) >= 1.0


# ── 풀 스택 ──────────────────────────────────────────────────────────


def test_corrected_summary_cross_reduces_tstat():
    rng = np.random.default_rng(4)
    ics = 0.08 + rng.normal(0, 0.05, size=300)
    # 상관 높은 수익률 행렬 → cross_mult > 1 → final_tstat < nw_tstat
    R = rng.normal(size=(300, 8)) + rng.normal(size=(300, 1))  # 공통요인 = 양의 횡단상관
    out = IC.corrected_ic_summary(ics, horizon_days=5, return_matrix=R)
    assert out["cross_mult"] > 1.0
    assert out["final_tstat"] < out["nw_tstat"]
    assert out["n_eff"] < 8


def test_corrected_summary_no_matrix_passthrough():
    rng = np.random.default_rng(5)
    ics = 0.08 + rng.normal(0, 0.05, size=200)
    out = IC.corrected_ic_summary(ics, horizon_days=5, return_matrix=None)
    assert out["final_tstat"] == out["nw_tstat"]
    assert out["cross_mult"] == 1.0


# ── paired 비교 ──────────────────────────────────────────────────────


def test_paired_ic_test_a_better():
    rng = np.random.default_rng(6)
    base = rng.normal(0.03, 0.04, size=60)
    a = base + 0.04  # shadow 가 일관되게 우위
    b = base
    res = IC.paired_ic_test(a, b)
    assert res["median_diff"] > 0
    assert res["a_better"] is True


def test_paired_ic_test_insufficient():
    res = IC.paired_ic_test([0.1, 0.2], [0.05, 0.1])
    assert res["a_better"] is None
    assert "표본 부족" in res["note"]
