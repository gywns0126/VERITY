"""ic_validity — degenerate IC 관측 격리 단일 predicate 테스트 (D9 step 1).

2026-06-14 신설. factor_ic_history.json 의 sample_count==0 → icir 폭주(100.0 등)
degenerate placeholder 를 IC 통계에서 일관 격리하는지 검증.
"""
import pytest

from api.quant.alpha.ic_validity import (
    is_valid_ic_obs,
    has_valid_icir,
    valid_factor_obs,
    filter_valid_series,
    ICIR_SANE_MAX,
)


def test_legacy_flag_rejected():
    assert is_valid_ic_obs({"ic_mean": -0.025, "icir": -0.3, "sample_count": 0, "legacy": True}) is False


def test_sample_count_zero_rejected():
    # 무플래그 sample_count==0 (81건) 도 탈락
    assert is_valid_ic_obs({"ic_mean": -0.025, "icir": 52.928, "sample_count": 0}) is False


def test_icir_blowup_rejected():
    # std≈0 degenerate (icir 폭주) — sample_count 가 살아있어도 icir 폭주는 탈락
    assert is_valid_ic_obs({"ic_mean": 0.01, "icir": 100.0, "sample_count": 3}) is False
    assert is_valid_ic_obs({"ic_mean": 0.01, "icir": -31.089, "sample_count": 2}) is False


def test_real_obs_passes():
    # 실데이터 예 (2026-04-16): momentum sc=3 icir=-0.239, volatility sc=3 icir=1.952
    assert is_valid_ic_obs({"ic_mean": -0.0615, "icir": -0.239, "sample_count": 3}) is True
    assert is_valid_ic_obs({"ic_mean": 0.123, "icir": 1.952, "sample_count": 3}) is True
    # 최신 (sc=52)
    assert is_valid_ic_obs({"ic_mean": -0.02, "icir": -0.19, "sample_count": 52}) is True


def test_missing_or_nonfinite():
    assert is_valid_ic_obs(None) is False
    # sample_count 부재 + sane icir = 통과 (fail-safe: 명시 degenerate 만 거부)
    assert is_valid_ic_obs({"ic_mean": 0.01, "icir": 0.4}) is True
    # 단 sample_count 부재라도 icir 폭주는 2차 가드로 탈락
    assert is_valid_ic_obs({"ic_mean": 0.01, "icir": 100.0}) is False
    assert is_valid_ic_obs({"ic_mean": float("nan"), "sample_count": 5}) is False
    assert is_valid_ic_obs({"ic_mean": 0.01, "icir": float("inf"), "sample_count": 5}) is False


def test_icir_at_boundary():
    # |icir| == ICIR_SANE_MAX 은 탈락(>=), 미만은 통과
    assert is_valid_ic_obs({"ic_mean": 0.01, "icir": ICIR_SANE_MAX, "sample_count": 5}) is False
    assert is_valid_ic_obs({"ic_mean": 0.01, "icir": ICIR_SANE_MAX - 0.01, "sample_count": 5}) is True


def test_has_valid_icir_needs_two_periods():
    # ic_mean 은 유효(sc>=1)하나 icir 평균엔 sc>=2 필요
    assert is_valid_ic_obs({"ic_mean": 0.05, "icir": None, "sample_count": 1}) is True
    assert has_valid_icir({"ic_mean": 0.05, "icir": 0.5, "sample_count": 1}) is False
    assert has_valid_icir({"ic_mean": 0.05, "icir": 0.5, "sample_count": 2}) is True
    # sample_count 부재 + sane icir = icir 평균에 허용 (부재는 미상)
    assert has_valid_icir({"ic_mean": 0.05, "icir": 0.5}) is True


def test_valid_factor_obs_filters_entry():
    entry = {"factors": {
        "good": {"ic_mean": 0.1, "icir": 1.5, "sample_count": 10},
        "legacy": {"ic_mean": 0.0, "icir": 100.0, "sample_count": 0, "legacy": True},
        "zero": {"ic_mean": 0.0, "icir": 52.9, "sample_count": 0},
    }}
    out = valid_factor_obs(entry)
    assert set(out.keys()) == {"good"}


def test_filter_valid_series_drops_degenerate():
    history = [
        {"factors": {"momentum": {"ic_mean": 0.0, "icir": 52.9, "sample_count": 0}}},  # degenerate
        {"factors": {"momentum": {"ic_mean": -0.06, "icir": -0.24, "sample_count": 3}}},  # real
    ]
    series = filter_valid_series(history, "momentum")
    assert len(series) == 1
    assert series[0]["sample_count"] == 3
