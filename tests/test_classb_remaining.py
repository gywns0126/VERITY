"""2026-07-24 2차 산식 감사 Class B 잔여 — MSPR 감점 suspend + funding 정본 상수.

- insider MSPR downgrade: 임계 -5.0 이 실 스케일(±450) 불일치 → US 절반 오감점 → grounding 전 suspend.
- vci funding_overheat: 하드코딩 0.05 → 정본 CRYPTO_FUNDING_OVERHEAT(0.06).
"""
from __future__ import annotations

from api.intelligence.factors.red_flags import _detect_red_flags


def test_mspr_downgrade_suspended():
    # 극단 매도(mspr -450)도 감점 없어야 (임계 미캘리 → grounding 전 suspend, fail-closed).
    dg = _detect_red_flags({"currency": "USD", "insider_sentiment": {"mspr": -450}}, {"macro": {}})["downgrade"]
    assert not any("MSPR" in x for x in dg)


def test_mspr_near_neutral_not_penalized():
    # 근중립(-5.21, 옛 임계가 오감점하던 값)도 감점 없어야.
    dg = _detect_red_flags({"currency": "USD", "insider_sentiment": {"mspr": -5.21}}, {"macro": {}})["downgrade"]
    assert not any("MSPR" in x for x in dg)


def test_funding_uses_canonical_constant():
    from api.config import CRYPTO_FUNDING_OVERHEAT
    assert CRYPTO_FUNDING_OVERHEAT == 0.06  # vci.py 가 하드코딩 0.05 대신 이 상수 사용
