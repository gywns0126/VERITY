"""
test_estate_policy_shock_builder.py — shock 빌더 산식·집계 검증.

핵심:
    1) impact_score = stage×0.5 + cat_weight×0.3 + region_breadth×0.2 산식
    2) direction 매핑 (regulation→negative, supply→positive, anomaly→negative 등)
    3) by_day aggregation (count, max_impact, net_direction_score)
    4) lookback 윈도우 필터
    5) archive 부재 → items=[] (T1)
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from api.builders import estate_policy_shock_builder as builder


NOW = datetime(2026, 5, 12, 1, 0, 0, tzinfo=timezone.utc)


def _row(pid, cat, stage, regions, h_ago):
    pub = NOW - timedelta(hours=h_ago)
    return {
        "id": pid,
        "title": f"정책 {pid}",
        "source_name": "국토교통부",
        "source_url": f"https://x/{pid}",
        "published_at": pub.isoformat(),
        "category": cat,
        "stage": stage,
        "affected_regions": regions,
        "archived_at": pub.isoformat(),
    }


def _write(path, rows):
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def test_impact_score_formula_regulation_stage3_one_region(tmp_path):
    """stage=3, regulation, 1 region → 0.75×0.5 + 1.0×0.3 + 0.4×0.2 = 0.755"""
    archive = tmp_path / "a.jsonl"
    _write(archive, [_row("A", "regulation", 3, ["서울"], 5)])

    payload = builder.build(now=NOW, archive_path=str(archive))
    assert len(payload["items"]) == 1
    assert payload["items"][0]["impact_score"] == pytest.approx(0.755, abs=0.001)
    assert payload["items"][0]["direction"] == "negative"


def test_impact_score_supply_stage1_three_regions(tmp_path):
    """stage=1, supply(0.7), 3 regions(0.7) → 0.25×0.5 + 0.7×0.3 + 0.7×0.2 = 0.475"""
    archive = tmp_path / "a.jsonl"
    _write(archive, [_row("B", "supply", 1, ["서울", "부산", "대구"], 24)])

    payload = builder.build(now=NOW, archive_path=str(archive))
    assert payload["items"][0]["impact_score"] == pytest.approx(0.475, abs=0.001)
    assert payload["items"][0]["direction"] == "positive"


def test_impact_score_anomaly_empty_regions(tmp_path):
    """stage=2, anomaly(0.7), 0 regions(=전국, 1.0) → 0.5×0.5 + 0.7×0.3 + 1.0×0.2 = 0.66"""
    archive = tmp_path / "a.jsonl"
    _write(archive, [_row("C", "anomaly", 2, [], 1)])

    payload = builder.build(now=NOW, archive_path=str(archive))
    assert payload["items"][0]["impact_score"] == pytest.approx(0.66, abs=0.001)
    assert payload["items"][0]["direction"] == "negative"


def test_direction_mapping(tmp_path):
    archive = tmp_path / "a.jsonl"
    _write(archive, [
        _row("R", "regulation", 1, [], 1),
        _row("T", "tax", 1, [], 2),
        _row("L", "loan", 1, [], 3),
        _row("C", "catalyst", 1, [], 4),
        _row("S", "supply", 1, [], 5),
        _row("D", "redev", 1, [], 6),
        _row("E", "rental", 1, [], 7),
    ])

    payload = builder.build(now=NOW, archive_path=str(archive))
    dirs = {it["id"]: it["direction"] for it in payload["items"]}
    assert dirs == {
        "R": "negative", "T": "negative", "L": "negative",
        "C": "positive", "S": "positive", "D": "positive", "E": "positive",
    }


def test_by_day_aggregation(tmp_path):
    archive = tmp_path / "a.jsonl"
    day_a = NOW - timedelta(days=3)
    day_b = NOW - timedelta(days=1)
    _write(archive, [
        {**_row("A1", "regulation", 4, [], 0), "published_at": day_a.isoformat()},
        {**_row("A2", "tax", 2, ["서울"], 0), "published_at": day_a.isoformat()},
        {**_row("B1", "supply", 3, [], 0), "published_at": day_b.isoformat()},
    ])

    payload = builder.build(now=NOW, archive_path=str(archive))
    day_a_key = day_a.isoformat()[:10]
    day_b_key = day_b.isoformat()[:10]

    assert payload["by_day"][day_a_key]["count"] == 2
    assert payload["by_day"][day_b_key]["count"] == 1
    # day_a: 둘 다 negative, 막대 색 검정
    assert payload["by_day"][day_a_key]["net_direction_score"] < 0
    # day_b: supply = positive
    assert payload["by_day"][day_b_key]["net_direction_score"] > 0


def test_lookback_filter(tmp_path):
    archive = tmp_path / "a.jsonl"
    _write(archive, [
        _row("RECENT", "regulation", 2, [], 24 * 3),     # 3d ago
        _row("FAR",    "regulation", 2, [], 24 * 50),    # 50d ago
    ])

    payload_7d = builder.build(now=NOW, archive_path=str(archive), lookback_days=7)
    assert {it["id"] for it in payload_7d["items"]} == {"RECENT"}

    payload_90d = builder.build(now=NOW, archive_path=str(archive), lookback_days=90)
    assert {it["id"] for it in payload_90d["items"]} == {"RECENT", "FAR"}


def test_missing_archive_returns_empty(tmp_path):
    payload = builder.build(now=NOW, archive_path=str(tmp_path / "missing.jsonl"))
    assert payload["items"] == []
    assert payload["total"] == 0
    assert payload["stats"]["max_impact"] == 0.0


def test_stats_aggregation(tmp_path):
    archive = tmp_path / "a.jsonl"
    _write(archive, [
        _row("R1", "regulation", 4, ["서울"], 10),
        _row("R2", "tax", 2, [], 20),
        _row("S1", "supply", 3, ["부산", "대구", "광주", "인천"], 30),
    ])

    payload = builder.build(now=NOW, archive_path=str(archive))
    stats = payload["stats"]

    assert stats["by_direction"]["negative"] == 2
    assert stats["by_direction"]["positive"] == 1
    assert stats["by_category"]["regulation"] == 1
    assert stats["by_category"]["supply"] == 1
    assert stats["max_impact"] > 0
    assert 0 < stats["mean_impact"] <= stats["max_impact"]
