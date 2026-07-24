"""2026-07-24 2차 산식 감사 Class B — MSPR 스케일 정규화 + funding 정본 상수.

MSPR: Finnhub 정본 = -100~100 정규화(Perplexity 실호출 grounding). 우리 collector 가 월별 mspr 를
합산해 ±450 부풀림 → ±5 임계가 근중립값까지 오판정. collector 평균화(-100~100 복원) + 임계 -5→-40
(정본 스케일 명확 순매도). #155 suspend 해제. funding_overheat 0.05→CRYPTO_FUNDING_OVERHEAT(0.06).
"""
from __future__ import annotations

from api.intelligence.factors.red_flags import _detect_red_flags


def _dg(mspr):
    return _detect_red_flags({"currency": "USD", "insider_sentiment": {"mspr": mspr}}, {"macro": {}})["downgrade"]


def test_mspr_fires_on_clear_net_selling():
    # 정규화 -60(명확 순매도, Cisco -75/Qualcomm -60 류) → 감점 발동
    assert any("MSPR" in x for x in _dg(-60))


def test_mspr_near_neutral_not_penalized():
    # 근중립(-5, 옛 -5.0 임계가 오감점하던 값)은 -40 미달 → 감점 없어야
    assert not any("MSPR" in x for x in _dg(-5))
    assert not any("MSPR" in x for x in _dg(-30))  # -30 도 임계 미달(보수)


def test_mspr_threshold_on_normalized_scale():
    from api.config import US_INSIDER_MSPR_PENALTY
    assert US_INSIDER_MSPR_PENALTY == -40.0  # -100~100 정본 스케일 임계


def test_funding_uses_canonical_constant():
    from api.config import CRYPTO_FUNDING_OVERHEAT
    assert CRYPTO_FUNDING_OVERHEAT == 0.06
