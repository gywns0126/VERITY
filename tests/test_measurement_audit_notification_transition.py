import json

import scripts.push_measurement_audit_telegram as push


def test_previous_failing_skips_current_trail_row(tmp_path, monkeypatch):
    monkeypatch.setattr(push, "DATA_DIR", str(tmp_path))
    meta = tmp_path / "metadata"
    meta.mkdir()
    rows = [
        {"as_of": "2026-08-27T18:00:00+09:00", "status": "FAIL",
         "failing": ["ledger_integrity"]},
        {"as_of": "2026-08-28T18:00:00+09:00", "status": "FAIL",
         "failing": ["ledger_integrity"]},
    ]
    (meta / "measurement_audit_trail.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
    )
    assert push._previous_failing(rows[-1]["as_of"]) == ["ledger_integrity"]
