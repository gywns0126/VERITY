"""Projection tests use temporary private artifacts, never the live journal."""
from datetime import timedelta
import pytest
from tests.test_analysis_harness import packet, reviewed, NOW
from api.intelligence import analysis_harness as h, analysis_console as c


def test_projection_excludes_raw_facts_and_rechecks_expiry(tmp_path):
    p = packet()
    h.save_packet(p, tmp_path)
    journal = tmp_path / "journal"
    h.finalize(p["packet_id"], reviewed(p), runtime=tmp_path, journal_path=journal,
               now=NOW + timedelta(hours=1))
    result = c.build(runtime=tmp_path, journal_path=journal, now=NOW + timedelta(days=2))
    item = result["items"]["005930"]
    assert item["state"] == "review_expired"
    assert item["review"]["verdict"] == "관심"
    assert "facts" not in item and "sections" not in item
    assert result["orders_authorized"] is False
    assert result["monitoring_active"] is False


def test_new_pending_packet_supersedes_older_review(tmp_path):
    p = packet()
    h.save_packet(p, tmp_path)
    journal = tmp_path / "journal"
    h.finalize(p["packet_id"], reviewed(p), runtime=tmp_path, journal_path=journal,
               now=NOW + timedelta(hours=1))
    newer = h.build_packet(p["facts"], now=NOW + timedelta(hours=2))
    h.save_packet(newer, tmp_path)
    item = c.build(runtime=tmp_path, journal_path=journal, now=NOW + timedelta(hours=3))["items"]["005930"]
    assert item["packet_id"] == newer["packet_id"]
    assert item["state"] == "awaiting_review"
    assert item["review"] is None


def test_corrupt_packet_does_not_produce_valid_projection(tmp_path):
    p = packet()
    path = h.save_packet(p, tmp_path)
    path.write_text('{}')
    with pytest.raises(ValueError):
        c.build(runtime=tmp_path, journal_path=tmp_path / "journal")
