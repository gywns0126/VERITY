# -*- coding: utf-8 -*-
"""팩터 하위신호 단면 z-score 부착 (PREREG_FACTOR_V2 §5-1, 2026-08-17).

문헌 = 순위 → z-score → 단순평균 (Asness-Frazzini-Pedersen 2019 QMJ).
구간화는 표준이 아니며 **경계 선택 자체가 은닉 자유도**다.

🚨 이 단계는 **부착만** 한다 — 점수를 바꾸지 않는다. 그래서 전환 전에 결함이 드러났고,
   실제로 실데이터에서 2건을 잡았다(아래 회귀).
"""
from __future__ import annotations

import statistics as S

from api.analyzers.stock_filter import _ZSPEC, _Z_MIN_SAMPLE, attach_factor_zscores


def _pool(vals, field="per", currency="KRW", **extra):
    return [{"currency": currency, field: v, **extra} for v in vals]


def test_direction_lower_is_better_for_valuation():
    """🚨 PER 은 낮을수록 z 가 높아야 한다 — 방향은 신호의 성질이므로 부착 시점에 정규화."""
    pool = _pool([3.0, 6.0, 10.0, 20.0, 40.0, 60.0])
    attach_factor_zscores(pool)
    zs = [p["factor_z"]["per"] for p in pool]
    assert zs == sorted(zs, reverse=True), f"PER 방향 뒤집힘: {zs}"


def test_direction_higher_is_better_for_roe():
    pool = _pool([1.0, 5.0, 9.0, 14.0, 22.0, 30.0], field="roe")
    attach_factor_zscores(pool)
    zs = [p["factor_z"]["roe"] for p in pool]
    assert zs == sorted(zs), f"ROE 방향 뒤집힘: {zs}"


def test_zero_ratio_is_unmeasured_not_cheapest():
    """🚨 핵심 회귀: PER 0(실적 없음)을 '가장 싸다'로 읽지 않는다.

    실측 2026-08-17 — KR 20종목 중 per==0 이 3건인데 방향(-1)을 그대로 적용하니
    그 3건이 **최고 저평가(z +1.40)** 로 매겨졌다. `or 50` falsy 결함과 같은 클래스.
    """
    pool = _pool([0, 0, 5.0, 8.0, 12.0, 20.0, 30.0])
    attach_factor_zscores(pool)
    zeros = [p for p in pool if p["per"] == 0]
    assert all("per" not in (p.get("factor_z") or {}) for p in zeros), \
        "0 인 PER 이 순위에 들어갔다 — 미측정이어야 한다"
    assert all("per" in p["factor_z"] for p in pool if p["per"] > 0)


def test_constant_field_is_not_attached():
    """🚨 상수 축은 부착하지 않는다.

    실측 — KR 20종목의 `pbr` 이 **전부 1.0** 이었다(US 는 33/36 정상). 임계 배점에서는
    전 종목이 같은 점수를 받아 안 보이던 결함인데 z 로 바꾸면 σ=0 이라 드러난다.
    변별 정보가 0 이면 '있는 척' 하지 말고 미측정으로 남긴다.
    """
    pool = _pool([1.0] * 8, field="pbr")
    attach_factor_zscores(pool)
    assert all("pbr" not in (p.get("factor_z") or {}) for p in pool)


def test_markets_are_separated():
    """🚨 KR/US 를 섞으면 통화·시장 구조가 오염된다 (beta 부분 채움 실측: KR +16.8 vs US +0.0)."""
    pool = _pool([3.0, 6.0, 10.0, 20.0, 40.0]) + _pool([100.0, 200.0, 300.0, 400.0, 500.0],
                                                       currency="USD")
    attach_factor_zscores(pool)
    kr = [p["factor_z"]["per"] for p in pool if p["currency"] != "USD"]
    us = [p["factor_z"]["per"] for p in pool if p["currency"] == "USD"]
    # 각 시장 안에서 독립적으로 표준화 — 양쪽 다 최고/최저가 존재해야 한다
    assert max(kr) > 0 > min(kr) and max(us) > 0 > min(us)
    assert abs(S.mean(kr)) < 0.3 and abs(S.mean(us)) < 0.3


def test_small_sample_is_skipped():
    """표본 부족은 키를 만들지 않는다 — `attach_safety_percentile` 과 같은 하한."""
    pool = _pool([3.0, 6.0])
    attach_factor_zscores(pool)
    assert all("per" not in (p.get("factor_z") or {}) for p in pool)
    assert _Z_MIN_SAMPLE >= 5


def test_missing_is_excluded_not_neutralized():
    """🚨 결측에 중립 0 을 넣지 않는다 — '못 잼' 이 '평균' 으로 둔갑한다."""
    pool = _pool([3.0, 6.0, 10.0, 20.0, 40.0]) + [{"currency": "KRW"}] * 2
    attach_factor_zscores(pool)
    missing = [p for p in pool if "per" not in p]
    assert all("per" not in (p.get("factor_z") or {}) for p in missing)


def test_spec_has_explicit_direction_for_every_field():
    """방향 미정 필드가 섞이면 부호가 조용히 뒤집힌다."""
    assert _ZSPEC and all(v in (+1, -1) for v in _ZSPEC.values())


def test_does_not_mutate_scores():
    """🚨 이 단계는 부착만 한다 — 기존 점수 필드를 건드리면 안 된다."""
    pool = _pool([3.0, 6.0, 10.0, 20.0, 40.0], brain_score=70, safety_score=55)
    attach_factor_zscores(pool)
    assert all(p["brain_score"] == 70 and p["safety_score"] == 55 for p in pool)
