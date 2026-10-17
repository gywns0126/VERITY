"""cockpit_aggregate — reducer integration test.

회귀 가드:
- 11 ledger fixture mock → cockpit_state 박힘 정합.
- 결손 ledger 도 silent skip 없이 진행 ([[feedback_data_collection_verification_mandatory]] 정합).
- severity 룰 정합.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest


def _ts_kst(hours_ago: float = 1.0) -> str:
    """현재 시각 기준 N 시간 전 KST iso 박음. fixture 자연 stale 차단용
    (2026-05-29 회귀 가드 — 5/27 hard-coded timestamp 가 24h cutoff 초과로 silent 깨짐)."""
    kst = timezone(timedelta(hours=9))
    return (datetime.now(kst) - timedelta(hours=hours_ago)).isoformat(timespec="seconds")


@pytest.fixture
def mock_ledger_dir(tmp_path, monkeypatch):
    """모든 11 ledger를 mock data 박은 tmp 디렉토리.

    cockpit_aggregate 의 DATA_DIR / METADATA_DIR 박음.
    """
    data_dir = tmp_path / "data"
    metadata_dir = data_dir / "metadata"
    metadata_dir.mkdir(parents=True)

    # cron_health.jsonl (마지막 entry 박음)
    (metadata_dir / "cron_health.jsonl").write_text(
        json.dumps({
            "ts_kst": "2026-05-27T12:00:00+09:00",
            "kis_lock_commits_24h": 1,
            "fred_age_h": 1.5,
            "macro_age_h": 2.0,
            "severity": "GREEN",
            "dispatch_chain_summary": {"total": 100, "ok": 95},
        }) + "\n",
        encoding="utf-8",
    )

    # data_health.jsonl
    (metadata_dir / "data_health.jsonl").write_text(
        json.dumps({
            "timestamp": "2026-05-27T12:00:00",
            "core_sources_ok": True,
            "overall_status": "ok",
        }) + "\n",
        encoding="utf-8",
    )
    (metadata_dir / "data_health.json").write_text(
        json.dumps({
            "_meta": {"generated_at": _ts_kst(0.5)},
            "status": "green",
            "reasons": [],
            "publish_verify": {
                "generated_at": "2026-05-27T12:05:00+09:00",
                "ok": True,
                "failed": 0,
            },
        }),
        encoding="utf-8",
    )

    # data_pipeline_health.json
    (metadata_dir / "data_pipeline_health.json").write_text(
        json.dumps({
            "collected_at": "2026-05-27T12:00:00",
            "overall_status": "ok",
            "summary": {},
        }),
        encoding="utf-8",
    )

    # fred_health.jsonl (3 entry, 1 fail)
    (metadata_dir / "fred_health.jsonl").write_text(
        "\n".join([
            json.dumps({"ts_utc": "2026-05-27T03:00:00+00:00", "series_id": "DGS10", "status": "ok"}),
            json.dumps({"ts_utc": "2026-05-27T03:01:00+00:00", "series_id": "M2", "status": "ok"}),
            json.dumps({"ts_utc": "2026-05-27T03:02:00+00:00", "series_id": "CPI", "status": "fail"}),
        ]) + "\n",
        encoding="utf-8",
    )

    # runtime_load_log.jsonl
    (metadata_dir / "runtime_load_log.jsonl").write_text(
        json.dumps({
            "mode": "quick",
            "ramp_up_stage": 0,
            "dart_failure_rate": 0.0,
            "rate_limit_violations": 0,
            "kr_first_call_duration_ms": 500,
        }) + "\n",
        encoding="utf-8",
    )

    # operator_deadman_log.jsonl
    (metadata_dir / "operator_deadman_log.jsonl").write_text(
        json.dumps({
            "ts": "2026-05-27T12:00:00",
            "days_git": 0.5,
            "days_telegram": 1.0,
            "days_uaq": 2.0,
            "trigger": "ok",
            "maintenance": False,
            "warn_days": 7,
        }) + "\n",
        encoding="utf-8",
    )

    # alert_state.json
    (metadata_dir / "alert_state.json").write_text(
        json.dumps({
            "last_push_at": "2026-05-27T11:30:00",
            "last_topics": ["KIS", "FRED"],
        }),
        encoding="utf-8",
    )

    # brain_audit.jsonl
    (metadata_dir / "brain_audit.jsonl").write_text(
        json.dumps({
            "ts_kst": "2026-05-27T12:00:00+09:00",
            "brain_score": 55,
            "grade": "WATCH",
            "n_total": 25,
        }) + "\n",
        encoding="utf-8",
    )

    # telegram_volume.jsonl — 동적 timestamp (24h 안)
    (data_dir / "telegram_volume.jsonl").write_text(
        "\n".join([
            json.dumps({"ts_kst": _ts_kst(2.0), "outcome": "sent", "fingerprint": "a"}),
            json.dumps({"ts_kst": _ts_kst(1.5), "outcome": "dedupe_skip", "fingerprint": "a"}),
        ]) + "\n",
        encoding="utf-8",
    )

    # system_health_snapshot.json
    (data_dir / "system_health_snapshot.json").write_text(
        json.dumps({
            "updated_at": "2026-05-27T12:00:00",
            "system_health": {"overall": "ok"},
        }),
        encoding="utf-8",
    )

    # portfolio.json (vams.reset_meta + validation)
    (data_dir / "portfolio.json").write_text(
        json.dumps({
            "vams": {
                "reset_meta": {"reset_at": "2026-05-17T14:12:07+09:00"},
                # n_validation_days 권위 소스 = validation_report.window.days (2026-06-11 fix)
                "validation_report": {"window": {"days": 30}},
            },
            "validation": {
                "target_days": 90,
                "sample_total": 30,
            },
        }),
        encoding="utf-8",
    )

    # cockpit_aggregate 모듈의 path constants 박음
    import scripts.cockpit_aggregate as agg
    monkeypatch.setattr(agg, "DATA_DIR", data_dir)
    monkeypatch.setattr(agg, "METADATA_DIR", metadata_dir)
    monkeypatch.setattr(agg, "COCKPIT_PATH", metadata_dir / "cockpit_state.json")

    return data_dir, metadata_dir


def test_build_cockpit_state_with_full_ledgers(mock_ledger_dir):
    """모든 11 ledger 박은 mock → cockpit_state 정상 박힘."""
    from scripts.cockpit_aggregate import build_cockpit_state
    state = build_cockpit_state()

    assert state["schema_version"] == 1
    assert state["severity"] == "GREEN"
    assert state["severity_reasons"] == []
    assert state["n_verification_days"] == 30
    assert state["n_milestones"]["to_50"] == 20  # 50 - 30
    # 🚨 2026-08-18 — 종전은 to_252 == 222 를 고정했다. to_252/to_365 는 폐기된 표본수
    #    게이트(VALIDATION_METHODOLOGY §7-1)를 향한 잔여일수라 산출에서 제거했다.
    #    테스트가 죽은 전제를 붙잡고 있으면 코드를 고칠 수 없다 — 부재를 검증한다.
    assert "to_252" not in state["n_milestones"], "폐기 마일스톤이 되살아났다"
    assert "to_365" not in state["n_milestones"], "폐기 마일스톤이 되살아났다"
    assert state["n_milestones"]["to_100"] == 70  # 100 - 30
    assert state["operator_deadman"]["trigger"] == "ok"
    assert state["alert_volume_24h"]["sent"] == 1
    assert state["alert_volume_24h"]["dedupe_skip"] == 1
    # _inputs_snapshot 박힘 (silent skip 차단)
    assert state["_inputs_snapshot"]["validation_sample"] == 30
    assert state["_inputs_snapshot"]["vams_days_since_reset"] is not None
    assert state["_inputs_snapshot"]["delivery_status"] == "green"
    assert state["_inputs_snapshot"]["publish_verify_ok"] is True


def test_build_cockpit_state_surfaces_delivery_red(mock_ledger_dir):
    _data_dir, metadata_dir = mock_ledger_dir
    (metadata_dir / "data_health.json").write_text(
        json.dumps({
            "status": "red",
            "reasons": ["배달 검증 실패 1건"],
            "publish_verify": {"ok": False, "failed": 1},
        }),
        encoding="utf-8",
    )

    from scripts.cockpit_aggregate import build_cockpit_state
    state = build_cockpit_state()
    assert state["severity"] == "RED"
    assert state["severity_reasons"] == ["data delivery RED: 배달 검증 실패 1건"]
    assert state["_inputs_snapshot"]["publish_verify_failed"] == 1


def test_build_cockpit_state_with_missing_ledgers(tmp_path, monkeypatch):
    """결손 ledger 박혀있어도 silent skip 없이 GREEN 박힘."""
    data_dir = tmp_path / "data"
    metadata_dir = data_dir / "metadata"
    metadata_dir.mkdir(parents=True)
    # 어떤 ledger 도 박지 않음

    import scripts.cockpit_aggregate as agg
    monkeypatch.setattr(agg, "DATA_DIR", data_dir)
    monkeypatch.setattr(agg, "METADATA_DIR", metadata_dir)
    monkeypatch.setattr(agg, "COCKPIT_PATH", metadata_dir / "cockpit_state.json")

    from scripts.cockpit_aggregate import build_cockpit_state
    state = build_cockpit_state()

    # 결손 aggregate 는 stale/결손 health evidence 로 YELLOW 처리한다.
    assert state["severity"] == "YELLOW"
    assert any("data delivery AMBER" in reason for reason in state["severity_reasons"])
    # N=0 (validation 결손) → to_50 = 50
    assert state["n_verification_days"] == 0
    assert state["n_milestones"]["to_50"] == 50
    # 2026-05-29 defensive — telegram_volume.jsonl 결손이어도 0-default shape 박힘
    # (downstream KeyError 가드).
    assert state["alert_volume_24h"] == {
        "sent": 0, "dedupe_skip": 0, "quiet_skip": 0, "fp_repeat_max": 0,
    }


@pytest.mark.parametrize("aggregate_text", [None, "{", json.dumps({"status": "green", "reasons": []})])
def test_missing_unreadable_or_incomplete_data_health_is_yellow(
    mock_ledger_dir, monkeypatch, aggregate_text
):
    _data_dir, metadata_dir = mock_ledger_dir
    path = metadata_dir / "data_health.json"
    if aggregate_text is None:
        path.unlink()
    else:
        path.write_text(aggregate_text, encoding="utf-8")

    from scripts.cockpit_aggregate import build_cockpit_state
    state = build_cockpit_state()
    assert state["severity"] == "YELLOW"
    assert any("data delivery AMBER" in reason for reason in state["severity_reasons"])


def test_old_data_health_build_timestamp_is_yellow(mock_ledger_dir, monkeypatch):
    _data_dir, metadata_dir = mock_ledger_dir
    now = datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("scripts.cockpit_aggregate._now_utc", lambda: now)
    (metadata_dir / "data_health.json").write_text(
        json.dumps({
            "_meta": {"generated_at": (now - timedelta(hours=3, seconds=1)).isoformat()},
            "generated_at": now.isoformat(),  # _meta is authoritative over the legacy field.
            "status": "green",
            "reasons": [],
            "publish_verify": {"ok": True, "failed": 0},
        }), encoding="utf-8",
    )

    from scripts.cockpit_aggregate import build_cockpit_state
    state = build_cockpit_state()
    assert state["severity"] == "YELLOW"
    assert "data_health aggregate stale" in state["severity_reasons"][0]
    assert state["_inputs_snapshot"]["delivery_generated_at"] == (now - timedelta(hours=3, seconds=1)).isoformat()


@pytest.mark.parametrize("candidate", [17, ["2026-10-18T00:00:00+00:00"]])
def test_non_string_data_health_timestamp_is_yellow_without_crashing(
    mock_ledger_dir, monkeypatch, candidate
):
    _data_dir, metadata_dir = mock_ledger_dir
    now = datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("scripts.cockpit_aggregate._now_utc", lambda: now)
    (metadata_dir / "data_health.json").write_text(
        json.dumps({
            "_meta": {"generated_at": candidate},
            "status": "green",
            "reasons": [],
            "publish_verify": {"ok": True, "failed": 0},
        }), encoding="utf-8",
    )

    from scripts.cockpit_aggregate import build_cockpit_state
    state = build_cockpit_state()
    assert state["severity"] == "YELLOW"
    assert "data_health aggregate generated_at missing or invalid" in state["severity_reasons"][-1]


def test_invalid_authoritative_meta_timestamp_does_not_fall_back_to_legacy(
    mock_ledger_dir, monkeypatch
):
    _data_dir, metadata_dir = mock_ledger_dir
    now = datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("scripts.cockpit_aggregate._now_utc", lambda: now)
    legacy_generated_at = now.isoformat()
    (metadata_dir / "data_health.json").write_text(
        json.dumps({
            "_meta": {"generated_at": "not-a-timestamp"},
            "generated_at": legacy_generated_at,
            "status": "green",
            "reasons": [],
            "publish_verify": {"ok": True, "failed": 0},
        }), encoding="utf-8",
    )

    from scripts.cockpit_aggregate import build_cockpit_state
    state = build_cockpit_state()
    assert state["severity"] == "YELLOW"
    assert "data_health aggregate generated_at missing or invalid" in state["severity_reasons"][-1]
    assert state["_inputs_snapshot"]["delivery_generated_at"] == "not-a-timestamp"


def test_publish_verify_timestamp_cannot_substitute_for_aggregate_timestamp(
    mock_ledger_dir, monkeypatch
):
    _data_dir, metadata_dir = mock_ledger_dir
    now = datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("scripts.cockpit_aggregate._now_utc", lambda: now)
    (metadata_dir / "data_health.json").write_text(
        json.dumps({
            "status": "green",
            "reasons": [],
            "publish_verify": {
                "generated_at": now.isoformat(),
                "ok": True,
                "failed": 0,
            },
        }), encoding="utf-8",
    )

    from scripts.cockpit_aggregate import build_cockpit_state
    state = build_cockpit_state()
    assert state["severity"] == "YELLOW"
    assert "data_health aggregate generated_at missing or invalid" in state["severity_reasons"][-1]
    assert state["_inputs_snapshot"]["delivery_generated_at"] is None


@pytest.mark.parametrize("meta", [[], {}, None])
def test_malformed_meta_cannot_use_legacy_clock(mock_ledger_dir, meta):
    _data_dir, metadata_dir = mock_ledger_dir
    (metadata_dir / "data_health.json").write_text(json.dumps({
        "_meta": meta, "generated_at": _ts_kst(0.1), "status": "green", "reasons": [],
        "publish_verify": {"ok": True, "failed": 0},
    }))
    from scripts.cockpit_aggregate import build_cockpit_state
    assert build_cockpit_state()["severity"] == "YELLOW"


def test_future_data_health_build_timestamp_over_five_minutes_is_yellow(
    mock_ledger_dir, monkeypatch
):
    _data_dir, metadata_dir = mock_ledger_dir
    now = datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("scripts.cockpit_aggregate._now_utc", lambda: now)
    generated_at = (now + timedelta(minutes=5, seconds=1)).isoformat()
    (metadata_dir / "data_health.json").write_text(
        json.dumps({
            "_meta": {"generated_at": generated_at},
            "status": "green",
            "reasons": [],
            "publish_verify": {"ok": True, "failed": 0},
        }), encoding="utf-8",
    )

    from scripts.cockpit_aggregate import build_cockpit_state
    state = build_cockpit_state()
    assert state["severity"] == "YELLOW"
    assert "data_health aggregate generated_at is in the future (>5m)" in state["severity_reasons"][-1]


def test_legacy_top_level_generated_at_remains_supported(mock_ledger_dir, monkeypatch):
    _data_dir, metadata_dir = mock_ledger_dir
    now = datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc)
    generated_at = (now - timedelta(hours=1)).isoformat()
    monkeypatch.setattr("scripts.cockpit_aggregate._now_utc", lambda: now)
    (metadata_dir / "data_health.json").write_text(
        json.dumps({
            "generated_at": generated_at,
            "status": "green",
            "reasons": [],
            "publish_verify": {"ok": True, "failed": 0},
        }), encoding="utf-8",
    )

    from scripts.cockpit_aggregate import build_cockpit_state
    state = build_cockpit_state()
    assert state["severity"] == "GREEN"
    assert state["_inputs_snapshot"]["delivery_generated_at"] == generated_at


def test_actual_data_health_builder_amber_reaches_consumer_as_yellow(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    metadata_dir = data_dir / "metadata"
    metadata_dir.mkdir(parents=True)

    import api.builders.data_health_builder as health_builder
    import scripts.cockpit_aggregate as agg

    monkeypatch.setattr(health_builder, "_META", str(metadata_dir))
    monkeypatch.setattr(health_builder, "_DATA", str(data_dir))
    monkeypatch.setattr(agg, "DATA_DIR", data_dir)
    monkeypatch.setattr(agg, "METADATA_DIR", metadata_dir)
    monkeypatch.setattr(agg, "COCKPIT_PATH", metadata_dir / "cockpit_state.json")

    aggregate = health_builder.build()
    assert aggregate["status"] == "amber"
    (metadata_dir / "data_health.json").write_text(
        json.dumps(aggregate), encoding="utf-8",
    )

    state = agg.build_cockpit_state()
    assert state["severity"] == "YELLOW"
    assert state["_inputs_snapshot"]["delivery_status"] == "amber"
    assert any(reason.startswith("data delivery AMBER:") for reason in state["severity_reasons"])


def test_stale_data_health_does_not_downgrade_existing_red(mock_ledger_dir, monkeypatch):
    _data_dir, metadata_dir = mock_ledger_dir
    now = datetime(2026, 10, 18, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("scripts.cockpit_aggregate._now_utc", lambda: now)
    (metadata_dir / "data_health.json").write_text(
        json.dumps({
            "_meta": {"generated_at": (now - timedelta(hours=4)).isoformat()},
            "status": "red",
            "reasons": ["기존 전달 검증 실패"],
            "publish_verify": {"ok": False, "failed": 1},
        }), encoding="utf-8",
    )

    from scripts.cockpit_aggregate import build_cockpit_state
    state = build_cockpit_state()
    assert state["severity"] == "RED"
    assert state["severity_reasons"] == ["data delivery RED: 기존 전달 검증 실패"]


def test_alert_volume_24h_empty_shape_when_only_stale_entries(tmp_path, monkeypatch):
    """telegram_volume.jsonl 에 24h 윈도우 밖 entry 만 있어도 0-default shape 박힘."""
    data_dir = tmp_path / "data"
    metadata_dir = data_dir / "metadata"
    metadata_dir.mkdir(parents=True)
    # 48h 전 entry — cutoff 초과
    (data_dir / "telegram_volume.jsonl").write_text(
        json.dumps({"ts_kst": _ts_kst(48.0), "outcome": "sent", "fingerprint": "a"}) + "\n",
        encoding="utf-8",
    )

    import scripts.cockpit_aggregate as agg
    monkeypatch.setattr(agg, "DATA_DIR", data_dir)
    monkeypatch.setattr(agg, "METADATA_DIR", metadata_dir)
    monkeypatch.setattr(agg, "COCKPIT_PATH", metadata_dir / "cockpit_state.json")

    from scripts.cockpit_aggregate import build_cockpit_state
    state = build_cockpit_state()
    assert state["alert_volume_24h"]["sent"] == 0
    assert state["alert_volume_24h"]["dedupe_skip"] == 0


def test_red_severity_when_kis_lock_spike(mock_ledger_dir):
    """KIS lock 3건 박힘 → RED."""
    data_dir, metadata_dir = mock_ledger_dir
    # cron_health.jsonl 의 kis_lock_commits_24h = 3 으로 박음
    (metadata_dir / "cron_health.jsonl").write_text(
        json.dumps({
            "ts_kst": "2026-05-27T12:00:00+09:00",
            "kis_lock_commits_24h": 3,
            "fred_age_h": 1.0,
            "severity": "RED",
        }) + "\n",
        encoding="utf-8",
    )

    from scripts.cockpit_aggregate import build_cockpit_state
    state = build_cockpit_state()
    assert state["severity"] == "RED"
    assert any("KIS" in r for r in state["severity_reasons"])


def test_yellow_when_fred_stale(mock_ledger_dir):
    """fred_age_h > 6 → YELLOW."""
    data_dir, metadata_dir = mock_ledger_dir
    (metadata_dir / "cron_health.jsonl").write_text(
        json.dumps({
            "ts_kst": "2026-05-27T12:00:00+09:00",
            "kis_lock_commits_24h": 0,
            "fred_age_h": 10.5,  # stale
            "severity": "YELLOW",
        }) + "\n",
        encoding="utf-8",
    )

    from scripts.cockpit_aggregate import build_cockpit_state
    state = build_cockpit_state()
    assert state["severity"] == "YELLOW"
    assert any("FRED" in r for r in state["severity_reasons"])
