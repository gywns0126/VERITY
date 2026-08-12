# -*- coding: utf-8 -*-
"""게이트 컷오버 (PREREG_GATE_STRENGTH_REDESIGN §4 · PR #357 채택 B)."""
from api.analyzers.stock_filter import attach_safety_percentile
from api.config import GATE_BOTTOM_PCT


def _pool(scores, currency="KRW"):
    return [{"ticker": f"T{i}", "safety_score": sc, "currency": currency}
            for i, sc in enumerate(scores)]


def test_percentile_attached_per_market():
    kr = _pool([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    us = _pool([5, 15, 25, 35, 45], currency="USD")
    attach_safety_percentile(kr + us)
    assert kr[0]["safety_pct"] == 0.1 and kr[-1]["safety_pct"] == 1.0
    # US 는 자기 시장 단면에서 백분위 (KR 과 섞이지 않는다)
    assert us[-1]["safety_pct"] == 1.0


def test_bottom_cut_semantics():
    pool = _pool(list(range(1, 101)))
    attach_safety_percentile(pool)
    passed = [s for s in pool if s["safety_pct"] >= GATE_BOTTOM_PCT]
    assert 78 <= len(passed) <= 82          # 하위 20% 컷 ≈ 80% 잔존


def test_small_sample_reports_none():
    """표본 <5 = 게이트 판정 불가 — 백분위를 지어내지 않는다."""
    pool = _pool([50, 60, 70])
    attach_safety_percentile(pool)
    assert all(s["safety_pct"] is None for s in pool)


def test_ties_share_percentile():
    pool = _pool([50, 50, 50, 50, 50, 50])
    attach_safety_percentile(pool)
    assert len({s["safety_pct"] for s in pool}) == 1


def test_vams_buy_sort_is_brain_not_safety():
    """정렬 키 교체 — safety 내림차순 코드가 매수 경로에 남아 있으면 안 된다."""
    import inspect

    from api.vams import engine
    src = inspect.getsource(engine)
    assert 'buy_candidates.sort(key=lambda s: s.get("safety_score", 0), reverse=True)' not in src
    assert "_brain_key" in src
