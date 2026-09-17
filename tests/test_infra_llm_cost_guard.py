import json
from datetime import datetime

from scripts import infra_status_monitor as monitor


def _write(tmp_path, entries):
    path = tmp_path / "data" / "metadata" / "llm_cost.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries),
        encoding="utf-8",
    )


def test_recent_google_ai_call_is_an_alert(tmp_path, monkeypatch):
    today = datetime.now(monitor.KST).date().isoformat()
    _write(tmp_path, [{
        "date": today,
        "provider": "google",
        "call_type": "daily_report",
        "cost_usd": 0.001,
    }])
    monkeypatch.setattr(monitor, "ROOT", tmp_path)

    result = monitor.check_llm_budget()

    assert result["status"] == "ALERT"
    assert "Google AI 최근 호출 1건" in result["detail"]
    assert "daily_report:1" in result["detail"]


def test_non_google_cost_below_budget_stays_ok(tmp_path, monkeypatch):
    today = datetime.now(monitor.KST).date().isoformat()
    _write(tmp_path, [{
        "date": today,
        "provider": "anthropic",
        "call_type": "operator",
        "cost_usd": 1.25,
    }])
    monkeypatch.setattr(monitor, "ROOT", tmp_path)

    result = monitor.check_llm_budget()

    assert result["status"] == "OK"
    assert "Google AI 최근 호출" not in result["detail"]
