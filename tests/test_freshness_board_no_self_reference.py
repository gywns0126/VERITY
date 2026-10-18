import json
from datetime import datetime, timedelta, timezone

import pytest

from api.builders import data_health_builder, freshness_board_builder


def test_board_excludes_its_own_previous_output(tmp_path, monkeypatch):
    manifest = tmp_path / "freshness_sla.json"
    manifest.write_text(json.dumps({"streams": [
        {"id": "freshness_board", "file": "freshness_board.json", "criticality": "P2",
         "schedule": "always", "max_age_minutes": 240}
    ]}), encoding="utf-8")
    monkeypatch.setattr(freshness_board_builder, "MANIFEST", str(manifest))

    board = freshness_board_builder.build_board()

    assert board["streams"] == []
    assert board["summary"]["stale"] == 0


@pytest.mark.parametrize("payload,reason", [
    (None, "missing"), ("not JSON", "unreadable"),
    ('[{"published_at":"2026-10-15T10:01:09+09:00"}]', "no_ts"),
    ('{"005930":[{"updated_at":"2026-08-10T18:14:40+09:00"}]}', "no_ts"),
    ('{"generated_at":"not-a-date"}', "bad_ts"),
])
def test_unmeasured_stream_has_id_and_reason_even_on_weekend(tmp_path, monkeypatch, payload, reason):
    manifest = tmp_path / "freshness_sla.json"
    manifest.write_text(json.dumps({"streams": [{
        "id": "input", "file": "input.json", "criticality": "P2",
        "schedule": "weekday", "max_age_minutes": 90,
    }]}))
    if payload is not None:
        (tmp_path / "input.json").write_text(payload)
    monkeypatch.setattr(freshness_board_builder, "MANIFEST", str(manifest))
    monkeypatch.setattr(freshness_board_builder, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(freshness_board_builder, "now_kst", lambda:
                        datetime(2026, 10, 18, 17, tzinfo=timezone(timedelta(hours=9))))
    board = freshness_board_builder.build_board()
    assert board["_skipped_count"] == 1
    assert board["_skipped"] == [{"id": "input", "reason": reason}]
    assert board["streams"] == []


def test_health_preserves_unmeasured_ids_and_stale_source_clock(tmp_path, monkeypatch):
    board = {
        "_meta": {"generated_at": "2026-10-18T17:12:38.107326+09:00"},
        "_skipped_count": 2,
        "_skipped": [{"id": "news_flash", "reason": "no_ts"},
                     {"id": "dividends_kr", "reason": "no_ts"}],
        "_producer_evidence": {"news_flash": {
            "status": "pipeline_completed", "completed_at": "2026-10-16T23:31:59Z",
            "clock_kind": "producer_step_completion", "asset_binding": "unverified",
            "source_freshness_verified": False,
        }},
        "streams": [{"id": "logo_map", "criticality": "P2", "status": "stale",
                     "last_ts": "2026-07-10T21:28:23.192812+09:00",
                     "age_eff_min": 143744.2, "max_age_min": 129600}],
    }
    (tmp_path / "freshness_board.json").write_text(json.dumps(board))
    monkeypatch.setattr(data_health_builder, "_DATA", str(tmp_path))
    section = data_health_builder._freshness_section()
    assert section["skipped_count"] == 2
    assert section["unmeasured_streams"] == board["_skipped"]
    assert section["producer_evidence"] == board["_producer_evidence"]
    assert section["stale_other"] == ["logo_map"]
    assert section["stale_other_details"] == [{
        "id": "logo_map", "last_ts": "2026-07-10T21:28:23.192812+09:00",
        "age_eff_min": 143744.2, "max_age_min": 129600,
    }]
