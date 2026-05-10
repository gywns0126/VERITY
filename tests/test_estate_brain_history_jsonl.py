"""estate_brain_builder.history.jsonl append 정합 검증.

C 단계 시계열 깊이 — 매 cron 마다 jsonl 1 row append. 누적 검증 (feedback_data_collection_verification_mandatory).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.builders import estate_brain_builder as bld


def _mock_payload(generated_at: str = "2026-05-10T10:00:00+09:00") -> dict:
    """compute_estate_brain 출력 mock — gu_aggregates / complexes / macro / diagnostics."""
    return {
        "schema_version": "v0",
        "generated_at": generated_at,
        "macro": {
            "mortgage_rate_pct": 4.85,
            "jeonse_to_sale_ratio_pct": 53.2,
            "unsold_houses_yoy_pct": 12.4,
            "treasury_10y_pct": 3.18,
            "extra_field_should_be_dropped": "noise",
        },
        "horizon": {"signal": "neutral"},
        "gu_aggregates": {
            "강남구": {
                "valuation": {"weighted_score": 65.2, "extreme_signals_count": 2},
                "cycle_analog": {"current_phase": "Rate-Shock Rebound"},
            },
            "서초구": {
                "valuation": {"weighted_score": 70.1, "extreme_signals_count": 3},
                "cycle_analog": {"current_phase": "Rate-Shock Rebound"},
            },
        },
        "complexes": [
            {"valuation": {"weighted_score": 55.0}},
            {"valuation": {"weighted_score": 80.0}},
            {"valuation": {"weighted_score": 60.0}},
        ],
        "diagnostics": {"rone_jeonse_available": True, "kosis_available": False},
        "model_meta": {"version": "v0.2"},
    }


def test_compact_history_row_drops_macro_noise(tmp_path: Path):
    row = bld._compact_history_row(_mock_payload())
    # 화이트리스트 macro 키만 통과
    assert row["macro"] == {
        "mortgage_rate_pct": 4.85,
        "jeonse_to_sale_ratio_pct": 53.2,
        "unsold_houses_yoy_pct": 12.4,
        "treasury_10y_pct": 3.18,
    }
    assert "extra_field_should_be_dropped" not in row["macro"]


def test_compact_history_row_extracts_gu_scores_signals_phase():
    row = bld._compact_history_row(_mock_payload())
    assert row["gu_scores"] == {"강남구": 65.2, "서초구": 70.1}
    assert row["gu_signals"] == {"강남구": 2, "서초구": 3}
    assert row["gu_phase"] == {"강남구": "Rate-Shock Rebound", "서초구": "Rate-Shock Rebound"}


def test_compact_history_row_complex_summary():
    row = bld._compact_history_row(_mock_payload())
    cs = row["complex_summary"]
    assert cs["n"] == 3
    assert cs["mean"] == 65.0  # (55+80+60)/3
    assert cs["min"] == 55.0
    assert cs["max"] == 80.0


def test_compact_history_row_handles_empty_complexes():
    p = _mock_payload()
    p["complexes"] = []
    row = bld._compact_history_row(p)
    assert row["complex_summary"]["n"] == 0
    assert row["complex_summary"]["mean"] is None


def test_append_history_jsonl_creates_and_appends(tmp_path: Path):
    """첫 호출 = 파일 생성 + 1 row. 두 번째 = 2 row. (cron 누적 시뮬)."""
    jsonl = tmp_path / "estate_brain_history.jsonl"

    ok1 = bld._append_history_jsonl(_mock_payload("2026-05-10T10:00:00+09:00"), path=str(jsonl))
    ok2 = bld._append_history_jsonl(_mock_payload("2026-05-11T10:00:00+09:00"), path=str(jsonl))

    assert ok1 and ok2
    lines = jsonl.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    rows = [json.loads(l) for l in lines]
    assert rows[0]["generated_at"] == "2026-05-10T10:00:00+09:00"
    assert rows[1]["generated_at"] == "2026-05-11T10:00:00+09:00"
    assert all(r["schema_version"] == bld.HISTORY_SCHEMA_VERSION for r in rows)


def test_append_history_jsonl_logs_logged_state_to_stderr(tmp_path: Path, capsys):
    """feedback_data_collection_verification_mandatory — stderr 에 logged=True/False 명시."""
    jsonl = tmp_path / "estate_brain_history.jsonl"
    bld._append_history_jsonl(_mock_payload(), path=str(jsonl))
    captured = capsys.readouterr()
    assert "logged=True" in captured.err
    assert "estate_brain history" in captured.err


def test_append_history_jsonl_failure_logs_logged_false(tmp_path: Path, capsys, monkeypatch):
    """write 실패 시 logged=False 명시 — silent skip 방지."""
    bad_path = "/no_such_dir/this_should_fail/estate_brain_history.jsonl"
    monkeypatch.setattr("os.makedirs", lambda *a, **kw: None)  # mkdir 통과해도
    # open 시 실패하도록
    ok = bld._append_history_jsonl(_mock_payload(), path=bad_path)
    captured = capsys.readouterr()
    assert ok is False
    assert "logged=False" in captured.err
