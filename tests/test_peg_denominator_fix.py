"""2026-07-24 2차 산식 감사 Class B(돈 우선) — PEG Hard Floor 분모 revenue→EPS 정정.

PEG = P/E ÷ EPS 성장(정의). 옛 코드가 죽은 consensus.eps_growth_* → revenue_growth(매출성장)로
붕괴 → US 전 종목 PEG 를 매출성장으로 오산 → 잘못된 auto_avoid(좋은 종목 강제 거부 = 기회손실).
실측: US PEG auto_avoid 10→2 (8개 잘못된 AVOID 해제). 실 소스 eps_quarterly_growth 사용.
"""
from __future__ import annotations

from api.intelligence.factors.red_flags import _detect_red_flags


def _aa(stock):
    return _detect_red_flags(stock, {"macro": {}})["auto_avoid"]


def test_peg_uses_eps_not_revenue():
    # Cisco 케이스: revenue 12%(old PEG 37/12=3.1→AVOID) but EPS 35%(PEG 1.05 정상) → PEG AVOID 없어야
    s = {"currency": "USD", "per": 37.26, "revenue_growth": 12.0, "eps_quarterly_growth": 35.4}
    assert not any("PEG" in x for x in _aa(s))


def test_peg_fires_on_real_expensive():
    # 진짜 PEG-expensive: PER 40 · EPS 성장 5% → PEG 8 > 3 → auto_avoid 정상 발동
    s = {"currency": "USD", "per": 40.0, "eps_quarterly_growth": 5.0}
    assert any("PEG" in x for x in _aa(s))


def test_peg_ignores_revenue_growth_when_no_eps():
    # revenue_growth 만 있고 eps 없음 → PEG 미평가(revenue 로 PEG 안 만듦, fail-closed) → AVOID 없어야
    s = {"currency": "USD", "per": 70.0, "revenue_growth": 7.0}  # old: 70/7=10>3 이면 AVOID 였음
    assert not any("PEG" in x for x in _aa(s))


def test_peg_skips_negative_eps_growth():
    # 음성장 = PEG 무의미 → skip (guard _eps>0). PEG 로 강제 AVOID 안 함(다른 신호가 담당).
    s = {"currency": "USD", "per": 30.0, "eps_quarterly_growth": -50.0}
    assert not any("PEG" in x for x in _aa(s))
