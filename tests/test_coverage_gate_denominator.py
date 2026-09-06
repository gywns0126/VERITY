# -*- coding: utf-8 -*-
"""커버리지 게이트 — 분모 증가와 분자 붕괴를 구분한다.

🚨 2026-08-12 실사고. 미장 유니버스가 SEC 벌크로 1,505 → 5,148(3.4배)이 되자
   us.field.facts.PER 86.3%→44.1% · us.companion.us_quarterly 99.5%→30.4% 로 찍혀
   publish 가 차단됐다. 그런데 종목 단위로 대조하니 **데이터 손실이 0** 이었다:
     PER 채움 1,299 → 2,265 · PBR 1,428 → 3,710 · 재무 1,499 → 4,243
     기존 1,505 종목 중 PER/PBR/재무를 잃은 종목 = 0
   커버리지가 개선됐는데 게이트가 붕괴로 읽었다. 게이트가 **비율만** 봤기 때문이다.

   🚨 완화하되 원래 목적은 보존해야 한다 — 이 게이트는 2026-07-11
   us_quarterly 1,494 → 10종 실사고로 도입됐다. 그건 절대 건수가 붕괴한 경우이므로
   "건수 유지·증가면 통과" 규칙으로도 그대로 잡힌다. 아래가 그 계약이다.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.builders import coverage_report_builder as cb  # noqa: E402


def _report(us_total: int, per_filled: int, quarterly: int) -> dict:
    return {
        "kr_total": 0, "fields": {}, "companions": {},
        "us_total": us_total,
        "us_fields": {"facts.PER": {"filled": per_filled,
                                    "pct": round(per_filled / us_total * 100, 1)}},
        "us_companions": {"us_quarterly": {"count": quarterly,
                                           "pct_of_us": round(quarterly / us_total * 100, 1)}},
        "us_smallcap_fields": {},
    }


def test_flat_counts_mirrors_flat_pcts_keys():
    r = _report(1000, 800, 900)
    pcts, counts = cb._flat_pcts(r), cb._flat_counts(r)
    assert set(pcts) == set(counts), "두 평탄화의 키 체계가 어긋나면 대조가 불가능하다"
    assert counts["us.field.facts.PER"] == 800
    assert counts["us.companion.us_quarterly"] == 900


def test_denominator_growth_keeps_counts_so_not_a_collapse():
    """실사고 재현 — 유니버스 3.4배, 건수는 증가."""
    old = _report(1505, 1299, 1498)
    new = _report(5148, 2265, 1530)

    op, np_ = cb._flat_pcts(old), cb._flat_pcts(new)
    on, nn = cb._flat_counts(old), cb._flat_counts(new)

    for k in ("us.field.facts.PER", "us.companion.us_quarterly"):
        assert op[k] - np_[k] > cb.CORE_FAIL_PP, "비율 낙폭은 옛 기준으로 FAIL 조건이다"
        assert nn[k] >= on[k], "그러나 절대 건수는 유지·증가 — 차단 대상이 아니다"


def test_real_collapse_still_blocked():
    """🚨 2026-07-11 형태(us_quarterly 1,494 → 10종)는 여전히 잡혀야 한다."""
    old = _report(1505, 1299, 1494)
    new = _report(1505, 1299, 10)

    op, np_ = cb._flat_pcts(old), cb._flat_pcts(new)
    on, nn = cb._flat_counts(old), cb._flat_counts(new)

    k = "us.companion.us_quarterly"
    assert op[k] - np_[k] > cb.CORE_FAIL_PP
    assert nn[k] < on[k], "건수가 붕괴했으므로 완화 규칙이 적용되지 않는다 = 차단 유지"


def test_partial_shrink_still_blocked():
    """건수가 조금이라도 줄면 완화하지 않는다 — 경계는 '유지·증가' 다."""
    old = _report(1505, 1299, 1498)
    new = _report(5148, 1298, 1497)   # 유니버스는 늘었지만 건수는 1 감소
    on, nn = cb._flat_counts(old), cb._flat_counts(new)
    for k in ("us.field.facts.PER", "us.companion.us_quarterly"):
        assert not (nn[k] >= on[k]), "1건이라도 줄면 완화 조건 불성립"


# ── 발행 최소선 (PM 2026-08-12 "데이터 없이는 좀 그렇잖아") ──────────────────

def test_empty_shell_excluded_from_publish():
    """핵심축 4종이 전부 빈 행은 발행하지 않는다. 수집은 전량 유지한다."""
    from api.builders import us_stock_report_public_builder as ub
    import inspect
    src = inspect.getsource(ub.main)
    assert "_core_axes" in src, "발행 최소선 필터가 사라지면 빈 껍데기 662종목이 다시 나간다"
    assert "핵심축 0" in src or "빈 껍데기" in src


def test_partial_financial_cache_cannot_replace_richer_compact_history():
    from api.builders import us_stock_report_public_builder as ub

    cached = [{"year": y} for y in (2021, 2022, 2023, 2024, 2025)]
    partial = [{"year": y} for y in (2024, 2025)]
    cached_fin = {"period": "2025", "groups": [{"title": "annual"}]}

    fs, fin = ub._prefer_richer_annual_pack(partial, None, cached, cached_fin)
    assert fs == cached
    assert fin == cached_fin


def test_equal_or_longer_fresh_history_wins():
    from api.builders import us_stock_report_public_builder as ub

    cached = [{"year": 2023}, {"year": 2024}]
    fresh = [{"year": 2023}, {"year": 2024}, {"year": 2025}]
    fresh_fin = {"period": "2025"}

    fs, fin = ub._prefer_richer_annual_pack(fresh, fresh_fin, cached, {"period": "2024"})
    assert fs == fresh
    assert fin == fresh_fin


def test_existing_public_report_is_available_as_regeneration_floor(tmp_path):
    from api.builders import us_stock_report_public_builder as ub

    path = tmp_path / "us_stock_report_public.json"
    path.write_text(json.dumps({"stocks": [{
        "ticker": "AAPL",
        "fin_series": [{"year": 2024}, {"year": 2025}],
        "financials": {"period": "2025"},
    }]}), encoding="utf-8")

    got = ub._load_existing_public_annual_packs(str(path))
    assert got["AAPL"]["fs"] == [{"year": 2024}, {"year": 2025}]
    assert got["AAPL"]["fin"] == {"period": "2025"}
