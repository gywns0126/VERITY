"""
Black Swan ledger + periodic_report 통합 unit 테스트.

검증:
1. _append_black_swan_ledger 가 JSONL append + 500 회전
2. load_black_swan_ledger(hours=N) cutoff 동작
3. periodic_report.generate_periodic_analysis("daily") 결과 black_swan_events 키 존재
"""
from __future__ import annotations

import json
import os
from datetime import timedelta

import pytest

from api.config import KST, now_kst


@pytest.fixture
def isolated_ledger(tmp_path, monkeypatch):
    """tail_risk_digest 모듈의 _LEDGER_PATH 를 tmp 로 교체."""
    ledger_path = str(tmp_path / "data" / "black_swan_ledger.jsonl")
    os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
    import api.intelligence.tail_risk_digest as trd
    monkeypatch.setattr(trd, "_LEDGER_PATH", ledger_path)
    return ledger_path


def test_append_and_load_round_trip(isolated_ledger):
    from api.intelligence.tail_risk_digest import (
        _append_black_swan_ledger,
        load_black_swan_ledger,
    )

    entry = {
        "ts_kst": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "severity": 7,
        "category": "war",
        "summary_ko": "test summary",
        "portfolio_angle": "",
        "primary_title": "Headline",
        "link": "",
        "cycle_stage": "late_bull",
        "is_realtime": False,
        "telegram_sent": False,
        "dedupe_key": "abc123",
    }
    assert _append_black_swan_ledger(entry) is True
    assert os.path.isfile(isolated_ledger)

    loaded = load_black_swan_ledger()
    assert len(loaded) == 1
    assert loaded[0]["dedupe_key"] == "abc123"
    assert loaded[0]["severity"] == 7


def test_load_with_hours_cutoff(isolated_ledger):
    from api.intelligence.tail_risk_digest import (
        _append_black_swan_ledger,
        load_black_swan_ledger,
    )

    old_ts = (now_kst() - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%S+09:00")
    new_ts = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")

    _append_black_swan_ledger({
        "ts_kst": old_ts, "severity": 5, "category": "geopolitics",
        "summary_ko": "old", "dedupe_key": "old1",
    })
    _append_black_swan_ledger({
        "ts_kst": new_ts, "severity": 6, "category": "war",
        "summary_ko": "new", "dedupe_key": "new1",
    })

    # 24h 컷 — old 빠져야 함
    recent = load_black_swan_ledger(hours=24)
    assert len(recent) == 1
    assert recent[0]["dedupe_key"] == "new1"

    # 전체 로드 — 둘 다
    all_events = load_black_swan_ledger()
    assert len(all_events) == 2


def test_ledger_rotation_caps_at_max(isolated_ledger, monkeypatch):
    import api.intelligence.tail_risk_digest as trd
    monkeypatch.setattr(trd, "_LEDGER_MAX", 5)  # 빠른 검증용 cap

    base_ts = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    for i in range(10):
        trd._append_black_swan_ledger({
            "ts_kst": base_ts, "severity": 5, "category": "war",
            "summary_ko": f"e{i}", "dedupe_key": f"k{i}",
        })

    loaded = trd.load_black_swan_ledger()
    assert len(loaded) == 5
    # 최신 5개만 남음 (k5 ~ k9)
    keys = [e["dedupe_key"] for e in loaded]
    assert keys == ["k5", "k6", "k7", "k8", "k9"]


def test_periodic_report_has_black_swan_section(isolated_ledger, monkeypatch, tmp_path):
    """daily report 결과에 black_swan_events 키 존재 + ledger 데이터 반영."""
    from api.intelligence.tail_risk_digest import _append_black_swan_ledger
    import api.intelligence.periodic_report as pr

    # 가짜 snapshot 1개 (load_snapshots_range 가 빈 list 반환하지 않게)
    fake_snap = {
        "_date": now_kst().strftime("%Y-%m-%d"),
        "sectors": [],
        "recommendations": [],
        "macro": {},
        "headlines": [],
        "vams": {},
    }
    monkeypatch.setattr(pr, "load_snapshots_range", lambda days: [fake_snap])

    # 직전 24h 안에 1건
    _append_black_swan_ledger({
        "ts_kst": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "severity": 9,
        "category": "war",
        "summary_ko": "주요 무력 충돌",
        "portfolio_angle": "",
        "primary_title": "Major conflict",
        "link": "",
        "cycle_stage": "euphoria",
        "is_realtime": False,
        "telegram_sent": True,
        "dedupe_key": "war-001",
    })

    result = pr.generate_periodic_analysis("daily")
    assert "black_swan_events" in result
    bs = result["black_swan_events"]
    assert bs["available"] is True
    assert bs["count"] == 1
    assert bs["severity_dist"]["high_8plus"] == 1
    assert bs["severity_dist"]["mid_5to7"] == 0
    assert bs["telegram_sent_count"] == 1
    assert bs["category_dist"]["war"] == 1
    assert len(bs["top_events"]) == 1
    assert bs["top_events"][0]["severity"] == 9


def test_periodic_report_empty_ledger(isolated_ledger, monkeypatch):
    """ledger 없을 때도 black_swan_events 키 정상 반환."""
    import api.intelligence.periodic_report as pr

    fake_snap = {
        "_date": now_kst().strftime("%Y-%m-%d"),
        "sectors": [], "recommendations": [], "macro": {},
        "headlines": [], "vams": {},
    }
    monkeypatch.setattr(pr, "load_snapshots_range", lambda days: [fake_snap])

    result = pr.generate_periodic_analysis("daily")
    assert "black_swan_events" in result
    bs = result["black_swan_events"]
    assert bs["available"] is False
    assert bs["count"] == 0
