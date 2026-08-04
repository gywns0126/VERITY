# -*- coding: utf-8 -*-
"""풀 회전 v0 판정 — PREREG_POOL_ROTATION_2026_08_04 (보고서만, 집행 없음).

핵심 계약: 결측 ≠ 발동 (증거 일수 임계 미달 = 퇴출 없음) / R1 보유 = 퇴출 면제 /
R5 제안 캡 5 / KR 하한 미달 시 진입 후보 = KR 만 / 스트릭 = 풀 이탈 시 단절.
"""
import importlib.util
import os
import sys

_spec = importlib.util.spec_from_file_location(
    "pool_rotation_report",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "scripts", "pool_rotation_report.py"))
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)


def _day(date, finals, polluted=None, tv=None):
    snap = {}
    for tk, fin in finals.items():
        snap[tk] = {"final": fin, "name": f"종목{tk}",
                    "trading_value": (tv or {}).get(tk, 5_000_000_000),
                    "polluted": bool((polluted or {}).get(tk))}
    return (date, snap)


def test_streak_counts_consecutive_from_latest():
    days = [_day("d1", {"A": "AVOID"}), _day("d2", {"A": "WATCH"}), _day("d3", {"A": "AVOID"}),
            _day("d4", {"A": "AVOID"})]
    st = pr.compute_streaks(days)
    assert st["A"]["avoid_streak"] == 2  # d4·d3 연속, d2 에서 단절


def test_streak_breaks_on_pool_absence():
    days = [_day("d1", {"A": "AVOID"}), _day("d2", {}), _day("d3", {"A": "AVOID"})]
    st = pr.compute_streaks(days)
    assert st["A"]["avoid_streak"] == 1  # d2 풀 이탈 → 단절


def test_no_exit_below_evidence_threshold():
    # AVOID 3일 연속 — 임계 20 미달 → 퇴출 0 (결측 ≠ 발동)
    days = [_day(f"d{i}", {"A": "AVOID", "B": "WATCH"}) for i in range(3)]
    pool = [{"ticker": "A", "sector": "IT"}, {"ticker": "B", "sector": "IT"}]
    rep = pr.build_report(pool, days, {}, {}, [], [], {})
    assert rep["exits"] == []
    assert rep["evidence_days"] == 3


def test_exit_fires_at_threshold_but_held_exempt():
    days = [_day(f"d{i:02d}", {"A": "AVOID", "H": "AVOID"}) for i in range(pr.AVOID_EXIT_DAYS)]
    pool = [{"ticker": "A", "sector": "IT"}, {"ticker": "H", "sector": "IT"}]
    portfolio = {"vams": {"holdings": [{"ticker": "H"}]}}
    rep = pr.build_report(pool, days, portfolio, {}, [], [], {})
    assert [e["ticker"] for e in rep["exits"]] == ["A"]  # H = R1 보유 예외
    assert any(w["ticker"] == "H" and "R1" in w.get("note", "") for w in rep["watch_streaks"])


def test_pollution_exit_at_10_days():
    days = [_day(f"d{i:02d}", {"P": "WATCH"}, polluted={"P": True})
            for i in range(pr.POLLUTION_EXIT_DAYS)]
    pool = [{"ticker": "P", "sector": "IT"}]
    rep = pr.build_report(pool, days, {}, {}, [], [], {})
    assert rep["exits"] and "R2b" in rep["exits"][0]["reason"]


def test_kr_weighted_entries_when_below_floor():
    # KR 1종뿐 (하한 20 미달) → 진입 후보는 KR 만, US 후보 제외
    days = [_day("d1", {"111111": "WATCH"})]
    pool = [{"ticker": "111111", "sector": "IT"}]
    universe = [
        {"ticker": "222222", "name": "KR후보", "trading_value": 2_000_000_000},
        {"ticker": "AAPL", "name": "US후보", "trading_value": 9e9},
    ]
    rep = pr.build_report(pool, days, {}, {}, universe, [], {"222222": "00111111"})
    assert [e["ticker"] for e in rep["entries"]] == ["222222"]
    assert rep["pool"]["kr_deficit"] == pr.KR_FLOOR - 1


def test_entry_gate_blocks_no_mapping_low_liquidity_pollution():
    days = [_day("d1", {"111111": "WATCH"})]
    pool = [{"ticker": "111111", "sector": "IT"}]
    universe = [
        {"ticker": "333333", "name": "무재무", "trading_value": 2e9},              # 매핑 없음
        {"ticker": "444444", "name": "저유동", "trading_value": 5e8},              # 10억 미만
        {"ticker": "555555", "name": "666666.KS,0P123", "trading_value": 2e9},   # name 오염
        {"ticker": "666666", "name": "정상", "trading_value": 2e9},
    ]
    mapping = {"444444": "c", "555555": "c", "666666": "c"}
    rep = pr.build_report(pool, days, {}, {}, universe, [], mapping)
    assert [e["ticker"] for e in rep["entries"]] == ["666666"]


def test_entries_capped_at_weekly_swap_cap():
    days = [_day("d1", {"111111": "WATCH"})]
    pool = [{"ticker": "111111", "sector": "IT"}]
    universe = [{"ticker": f"7{i:05d}", "name": f"후보{i}", "trading_value": 2e9}
                for i in range(10)]
    mapping = {f"7{i:05d}": "c" for i in range(10)}
    rep = pr.build_report(pool, days, {}, {}, universe, [], mapping)
    assert len(rep["entries"]) == pr.WEEKLY_SWAP_CAP


def test_r1_out_of_pool_holdings_surfaced():
    days = [_day("d1", {"111111": "WATCH"})]
    pool = [{"ticker": "111111", "sector": "IT"}]
    portfolio = {"vams": {"holdings": [{"ticker": "204610"}, {"ticker": "111111"}]}}
    paper = {"positions": {"999999": {}}}
    rep = pr.build_report(pool, days, portfolio, paper, [], [], {})
    assert rep["r1_held_out_of_pool"] == ["204610", "999999"]


def test_sector_over_cap_flagged():
    days = [_day("d1", {t: "WATCH" for t in ("A", "B", "C", "D")})]
    pool = [{"ticker": t, "sector": "IT"} for t in ("A", "B", "C")] + [{"ticker": "D", "sector": "Fin"}]
    rep = pr.build_report(pool, days, {}, {}, [], [], {})
    assert "IT" in rep["pool"]["sector_over_cap"]  # 75% > 25%
