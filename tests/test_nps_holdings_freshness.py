import json
from pathlib import Path

from api.collectors import nps_holdings as nps


ROOT = Path(__file__).resolve().parents[1]


def _row(date, pct, src, ticker="005930", name="삼성전자"):
    return {
        "ticker": ticker,
        "name": name,
        "pct": pct,
        "qty_change": None,
        "date": date,
        "src": src,
    }


def test_merge_latest_keeps_newer_dart_over_quarter_csv():
    merged = {}
    nps._merge_latest(
        merged,
        "005930",
        _row("2026-09-08", 8.02, "DART majorstock live"),
    )
    nps._merge_latest(
        merged,
        "005930",
        _row("2026-03-30", 7.1, "data.go.kr #15106890 (분기 확정 CSV)"),
    )

    assert merged["005930"]["date"] == "2026-09-08"
    assert merged["005930"]["pct"] == 8.02


def test_merge_latest_prefers_dart_when_dates_match():
    merged = {}
    nps._merge_latest(
        merged,
        "005930",
        _row("2026-03-31", 7.1, "data.go.kr #15106890 (분기 확정 CSV)"),
    )
    nps._merge_latest(
        merged,
        "005930",
        _row("2026-03-31", 7.4, "DART majorstock live"),
    )

    assert merged["005930"]["pct"] == 7.4
    assert merged["005930"]["src"] == "DART majorstock live"


def test_latest_nps_record_joins_majorstock_and_elestock():
    latest = nps._latest_nps_from_payloads(
        [
            {
                "repror": "국민연금공단",
                "stkrt": "7.20",
                "stkqy_irds": "-100",
                "rcept_dt": "2026-07-01",
            }
        ],
        [
            {
                "repror": "국민연금공단",
                "sp_stock_lmp_rate": "8.02",
                "sp_stock_lmp_irds_cnt": "1,862,656",
                "rcept_dt": "2026-09-08",
            }
        ],
    )

    assert latest == {
        "pct": 8.02,
        "qty_change": 1862656.0,
        "date": "2026-09-08",
        "src": "DART elestock live",
    }


def test_dart_api_key_accepts_environment_fallback(monkeypatch):
    monkeypatch.setattr("api.config.DART_API_KEY", "")
    monkeypatch.setenv("DART_API_KEY", "env-key")

    assert nps._dart_api_key() == "env-key"


def test_data_go_fallback_uses_latest_verified_quarter(monkeypatch):
    import requests

    monkeypatch.delenv("NPS_DATA_GO_KR_URL", raising=False)
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("offline")))

    assert nps._resolve_latest_url().endswith("uddi:5536983c-fa78-46c7-bef1-b602ec951fcf")


def test_catalyst_input_missing_is_not_treated_as_empty_success(monkeypatch, tmp_path):
    monkeypatch.setattr(nps, "CATALYST_PATH", str(tmp_path / "missing.jsonl"))

    events, audit = nps._nps_catalyst_events()

    assert events == {}
    assert audit["event_source_ok"] is False
    assert audit["event_source_rows"] == 0
    assert audit["event_source_error"] == "FileNotFoundError"


def test_build_uses_latest_date_instead_of_source_order(monkeypatch):
    monkeypatch.setattr(
        nps,
        "_from_data_go_kr",
        lambda _names: {"005930": _row("2026-03-30", 7.1, "data.go.kr #15106890")},
    )
    monkeypatch.setattr(
        nps,
        "_from_major_csv",
        lambda _names: {
            "005930": _row(
                "2026-03-30", 7.2, "data.go.kr #15106890 (분기 확정 CSV)"
            )
        },
    )
    monkeypatch.setattr(nps, "_from_previous_live", lambda: {})
    monkeypatch.setattr(
        nps,
        "_from_dart_existing",
        lambda _names: {"005930": _row("2026-07-01", 7.8, "DART majorstock")},
    )
    audit = {
        "event_tickers": 1,
        "candidate_tickers": 1,
        "updated_tickers": 1,
        "retired_tickers": 0,
        "unresolved_tickers": 0,
        "api_calls": 2,
    }
    monkeypatch.setattr(
        nps,
        "_from_dart_live",
        lambda _names, _baseline: (
            {"005930": _row("2026-09-08", 8.02, "DART majorstock live")},
            set(),
            audit,
        ),
    )
    monkeypatch.setattr(nps, "_from_full_list", lambda _names: [])
    monkeypatch.setattr(nps, "_from_full_overseas", lambda: [])
    monkeypatch.setattr(nps, "_asset_mix", lambda: [])

    out = nps.build_nps_holdings()

    assert out["count"] == 1
    assert out["holdings"][0]["date"] == "2026-09-08"
    assert out["holdings"][0]["pct"] == 8.02
    assert out["as_of_latest"] == "2026-09-08"
    assert out["dart_refresh"] == audit


def test_main_does_not_rewrite_timestamp_only_change(monkeypatch, tmp_path):
    output = tmp_path / "nps_holdings.json"
    heartbeat = tmp_path / "nps_holdings_heartbeat.json"
    current_audit = {
        "event_source_ok": True,
        "event_source_rows": 1200,
        "event_source_invalid_rows": 0,
        "event_source_latest": "20260913",
        "event_tickers": 161,
        "candidate_tickers": 0,
        "updated_tickers": 0,
        "retired_tickers": 0,
        "unresolved_tickers": 0,
        "api_calls": 0,
    }
    previous = {
        "generated_at": "2026-09-13T10:00:00+09:00",
        "count": 1,
        "as_of_latest": "2026-09-08",
        "holdings": [_row("2026-09-08", 8.02, "DART majorstock live")],
        "dart_check": current_audit,
        "dart_refresh": {
            "event_tickers": 161,
            "candidate_tickers": 152,
            "updated_tickers": 152,
            "retired_tickers": 0,
            "unresolved_tickers": 0,
            "api_calls": 304,
        },
    }
    output.write_text(json.dumps(previous, ensure_ascii=False), encoding="utf-8")
    current = {
        **previous,
        "generated_at": "2026-09-13T11:00:00+09:00",
        "dart_refresh": current_audit,
    }
    before = output.read_text(encoding="utf-8")
    monkeypatch.setattr(nps, "OUTPUT_PATH", str(output))
    monkeypatch.setattr(nps, "HEARTBEAT_PATH", str(heartbeat))
    monkeypatch.setattr(nps, "build_nps_holdings", lambda: current)

    assert nps.main() == 0
    assert output.read_text(encoding="utf-8") == before
    assert json.loads(heartbeat.read_text(encoding="utf-8"))["status"] == "ok"


def test_main_fail_closed_preserves_previous_output(monkeypatch, tmp_path):
    output = tmp_path / "nps_holdings.json"
    heartbeat = tmp_path / "nps_holdings_heartbeat.json"
    previous = {"generated_at": "2026-09-13T10:00:00+09:00", "count": 232}
    output.write_text(json.dumps(previous, ensure_ascii=False), encoding="utf-8")
    audit = {
        "event_source_ok": True,
        "event_source_rows": 1200,
        "event_source_invalid_rows": 0,
        "event_tickers": 161,
        "candidate_tickers": 1,
        "unresolved_tickers": 1,
    }
    notices = []
    monkeypatch.setattr(nps, "OUTPUT_PATH", str(output))
    monkeypatch.setattr(nps, "HEARTBEAT_PATH", str(heartbeat))
    monkeypatch.setattr(nps, "build_nps_holdings", lambda: {"count": 231, "dart_refresh": audit})
    monkeypatch.setattr(nps, "_notify_failure", lambda reason, details: notices.append((reason, details)) or True)

    assert nps.main() == 2
    assert json.loads(output.read_text(encoding="utf-8")) == previous
    assert not heartbeat.exists()
    assert len(notices) == 1


def test_workflow_escalates_nps_failure_after_safe_publish():
    workflow = (ROOT / ".github/workflows/daily_analysis_full.yml").read_text(encoding="utf-8")

    assert "id: nps_holdings" in workflow
    assert "TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}" in workflow
    assert "TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}" in workflow
    assert "steps.nps_holdings.outcome == 'failure'" in workflow
    assert workflow.index("Publish hot data to VERITY-data") < workflow.index("국민연금 보유 신선도 실패 확정")


def test_sla_tracks_success_heartbeat_as_p0():
    manifest = json.loads((ROOT / "data/freshness_sla.json").read_text(encoding="utf-8"))
    stream = next(item for item in manifest["streams"] if item["id"] == "nps_holdings")

    assert stream["file"] == "metadata/nps_holdings_heartbeat.json"
    assert stream["ts_field"] == "last_run_at"
    assert stream["criticality"] == "P0"
