"""
test_estate_policy_archive_builder.py — archive append/dedup/prune 검증.

DI 로 collector·classifier 주입 (실 호출 X). 핵심 동작:
    1) 신규 정책 append
    2) 기존 id dedup (재append X)
    3) 90d 초과 prune
    4) classify 실패 시 row skip + 다른 정책 유지
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from api.builders import estate_policy_archive_builder as builder


NOW = datetime(2026, 5, 12, 1, 0, 0, tzinfo=timezone.utc)


def _policy(pid: str, h: int, **kw) -> dict:
    pub = NOW - timedelta(hours=h)
    return {
        "id": pid,
        "title": kw.get("title", f"정책 {pid}"),
        "source_name": kw.get("source_name", "국토교통부"),
        "source_url": kw.get("source_url", f"https://example.gov.kr/{pid}"),
        "published_at": pub.isoformat(),
        "raw_text": kw.get("raw_text", "공시가격 인상"),
    }


def _classifier_ok(p):
    return {"category": "regulation", "stage": 3, "affected_regions": ["서울"]}


def test_archive_append_new_policies(tmp_path):
    archive = tmp_path / "archive.jsonl"

    def collect(**kwargs):
        return [_policy("A", 2), _policy("B", 5)]

    stats = builder.build(
        now=NOW,
        archive_path=str(archive),
        _collect=collect,
        _classify=_classifier_ok,
    )

    assert stats["appended"] == 2
    assert stats["total_after"] == 2
    assert stats["pruned"] == 0

    lines = archive.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    ids = {json.loads(ln)["id"] for ln in lines}
    assert ids == {"A", "B"}


def test_archive_dedup_existing_id(tmp_path):
    archive = tmp_path / "archive.jsonl"
    archive.write_text(
        json.dumps({
            "id": "A", "title": "기존",
            "source_name": "국토부", "source_url": "https://x",
            "published_at": (NOW - timedelta(hours=10)).isoformat(),
            "category": "regulation", "stage": 2, "affected_regions": [],
            "archived_at": (NOW - timedelta(days=1)).isoformat(),
        }) + "\n",
        encoding="utf-8",
    )

    def collect(**kwargs):
        return [_policy("A", 2), _policy("B", 3)]

    stats = builder.build(
        now=NOW,
        archive_path=str(archive),
        _collect=collect,
        _classify=_classifier_ok,
    )

    assert stats["appended"] == 1
    assert stats["total_after"] == 2
    lines = archive.read_text(encoding="utf-8").strip().split("\n")
    ids = {json.loads(ln)["id"] for ln in lines}
    assert ids == {"A", "B"}


def test_archive_prune_old(tmp_path):
    archive = tmp_path / "archive.jsonl"
    old_pub = (NOW - timedelta(days=95)).isoformat()
    fresh_pub = (NOW - timedelta(days=10)).isoformat()
    archive.write_text(
        json.dumps({
            "id": "OLD", "title": "옛 정책",
            "source_name": "국토부", "source_url": "https://x/old",
            "published_at": old_pub,
            "category": "regulation", "stage": 1, "affected_regions": [],
            "archived_at": old_pub,
        }) + "\n" +
        json.dumps({
            "id": "FRESH", "title": "최근",
            "source_name": "국토부", "source_url": "https://x/fresh",
            "published_at": fresh_pub,
            "category": "supply", "stage": 2, "affected_regions": ["부산"],
            "archived_at": fresh_pub,
        }) + "\n",
        encoding="utf-8",
    )

    def collect(**kwargs):
        return []

    stats = builder.build(
        now=NOW,
        archive_path=str(archive),
        _collect=collect,
        _classify=_classifier_ok,
    )

    assert stats["pruned"] == 1
    assert stats["total_after"] == 1
    lines = archive.read_text(encoding="utf-8").strip().split("\n")
    ids = {json.loads(ln)["id"] for ln in lines}
    assert ids == {"FRESH"}


def test_archive_classify_failure_skips_row(tmp_path):
    archive = tmp_path / "archive.jsonl"

    def collect(**kwargs):
        return [_policy("A", 1), _policy("B", 2)]

    def classify_fail_on_A(p):
        if p["id"] == "A":
            raise RuntimeError("classify boom")
        return {"category": "supply", "stage": 1, "affected_regions": []}

    stats = builder.build(
        now=NOW,
        archive_path=str(archive),
        _collect=collect,
        _classify=classify_fail_on_A,
    )

    assert stats["appended"] == 1
    lines = archive.read_text(encoding="utf-8").strip().split("\n")
    ids = {json.loads(ln)["id"] for ln in lines}
    assert ids == {"B"}


def test_archive_collect_failure_preserves_existing(tmp_path):
    archive = tmp_path / "archive.jsonl"
    archive.write_text(
        json.dumps({
            "id": "X", "title": "보존",
            "source_name": "국토부", "source_url": "https://x/X",
            "published_at": (NOW - timedelta(hours=5)).isoformat(),
            "category": "supply", "stage": 2, "affected_regions": [],
            "archived_at": (NOW - timedelta(days=1)).isoformat(),
        }) + "\n",
        encoding="utf-8",
    )

    def collect(**kwargs):
        raise RuntimeError("network boom")

    stats = builder.build(
        now=NOW,
        archive_path=str(archive),
        _collect=collect,
        _classify=_classifier_ok,
    )

    assert stats["appended"] == 0
    assert stats["total_after"] == 1
    assert "X" in archive.read_text(encoding="utf-8")
