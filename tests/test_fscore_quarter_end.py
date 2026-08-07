# -*- coding: utf-8 -*-
"""F-Score YoY 델타 — quarter_end 오염 수리 (2026-08-07).

사고: 스냅샷의 `quarter_end` 에 **수집일**이 기록된 행이 2,631건 남아 있었다
(2026-05-17 ×1867 등). 그 행이 '최신'으로 뽑히면 YoY 조회(±30일)가 실제 분기말과
44~47일 어긋나 **전부 빗나간다**. 실측: KR 추천 23종 중 22종이 `no_prior`,
전체 39건 중 38건이 `n_delta_computed=0`.

결과: F5/F6/F8/F9 가 델타 대신 **절대 임계 폴백**으로 채점됐다. Piotroski F-Score 는
*개선*(YoY 변화)을 보는 산식인데 *수준*을 보고 있었다 — 9기준 중 4개가 다른 것을 쟀다.

쓰기 쪽은 2026-05-20 에 한 번 고쳤는데(1,867건) 폴백이 남아 계속 오염을 생산했다
(06-07 298 · 07-24 96 · 08-02 90 = 전부 수집일).

계약: ① 진짜 분기말(3·6·9·12월 **말일**)만 유효 ② 쓰기는 산출 불가 시 **기록하지 않는다**
(가짜 날짜 금지) ③ 읽기는 레거시 오염 행을 차단.
"""
import json

import pytest

from api.utils.fscore_delta import (
    compute_fscore_deltas,
    find_yoy_prior,
    is_real_quarter_end,
)


@pytest.mark.parametrize("v,ok", [
    ("2026-03-31", True), ("2026-06-30", True), ("2026-09-30", True), ("2025-12-31", True),
    ("2026-05-17", False),   # 실측 오염 — 수집일 1,867건
    ("2026-06-07", False), ("2026-08-02", False),   # 5/20 수리 후에도 생산된 오염
    ("2026-06-29", False),   # 분기 월이지만 말일 아님
    ("2026-04-30", False),   # 말일이지만 분기 월 아님
    (None, False), ("", False), ("garbage", False),
])
def test_real_quarter_end(v, ok):
    assert is_real_quarter_end(v) is ok


def _snap(qe, **kw):
    d = {"ticker": "000001", "quarter_end": qe, "roa": 5.0, "debt_ratio": 50.0,
         "current_ratio": 1.2, "gross_margin": 30.0, "asset_turnover": 0.9}
    d.update(kw)
    return d


def test_contaminated_row_breaks_yoy_when_included():
    """🚨 사고 재현 — 수집일 행이 '현재'로 뽑히면 1년 전 분기를 못 찾는다."""
    snaps = [_snap("2026-05-17"), _snap("2026-03-31"), _snap("2025-03-31")]
    assert find_yoy_prior("2026-05-17", snaps) is None      # 44~47일 어긋남


def test_yoy_found_with_clean_quarter_ends():
    snaps = [_snap("2026-03-31"), _snap("2025-03-31")]
    p = find_yoy_prior("2026-03-31", snaps)
    assert p is not None and p["quarter_end"] == "2025-03-31"


def test_deltas_computed_when_prior_exists():
    cur = _snap("2026-03-31", roa=8.0, debt_ratio=40.0, current_ratio=1.5,
                gross_margin=35.0, asset_turnover=1.1)
    pri = _snap("2025-03-31")
    d = compute_fscore_deltas(cur, pri)
    assert d["data_source"] == "quarterly_snapshot_yoy"
    assert d["n_delta_computed"] == 5
    assert d["c5_delta_leverage_negative"] is True      # 50 → 40
    assert d["c6_delta_current_ratio_positive"] is True # 1.2 → 1.5
    assert d["c8_delta_gross_margin_positive"] is True  # 30 → 35
    assert d["c9_delta_asset_turnover_positive"] is True


def test_no_prior_returns_all_none():
    d = compute_fscore_deltas(_snap("2026-03-31"), None)
    assert d["data_source"] == "no_prior" and d["n_delta_computed"] == 0


def test_loader_filters_contaminated_rows(tmp_path, monkeypatch):
    """읽기 방어 — 레거시 오염 행이 최신으로 뽑히지 않는다."""
    import api.utils.fscore_delta as FD
    p = tmp_path / "dart_quarterly_snapshots.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in [
        {**_snap("2026-05-17"), "fetched_at": "2026-05-17"},   # 오염
        {**_snap("2026-03-31"), "fetched_at": "2026-05-01"},
        {**_snap("2025-03-31"), "fetched_at": "2025-05-01"},
    ]), encoding="utf-8")
    monkeypatch.setattr(FD, "QUARTERLY_SNAPSHOT_PATH", p)
    snaps = FD.load_quarterly_snapshots("000001")
    ends = [s["quarter_end"] for s in snaps]
    assert "2026-05-17" not in ends
    assert ends[0] == "2026-03-31"
    assert find_yoy_prior(ends[0], snaps) is not None


def test_writer_does_not_fabricate_quarter_end():
    """🚨 쓰기 — 산출 불가 시 수집일을 가짜 분기말로 쓰지 않는다(빈 문자열 → caller skip)."""
    from api.builders.dart_batch_builder import _quarter_end_iso
    assert _quarter_end_iso(None, "11011", "2026-08-07") == ""
    assert _quarter_end_iso("", None, "2026-08-07") == ""
    # 정상 경로는 그대로
    assert _quarter_end_iso("2026-03-31", "11013", "2026-08-07") == "2026-03-31"
    assert _quarter_end_iso("2026", "11011", "2026-08-07").endswith("-12-31")


def test_writer_skips_rows_without_quarter_end():
    import inspect

    from api.builders import dart_batch_builder as B
    src = inspect.getsource(B._append_quarterly_snapshots)
    assert "if not quarter_end:" in src and "continue" in src
