import json

from api.collectors import nps_holdings as nps


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
    previous = {
        "generated_at": "2026-09-13T10:00:00+09:00",
        "count": 1,
        "as_of_latest": "2026-09-08",
        "holdings": [_row("2026-09-08", 8.02, "DART majorstock live")],
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
        "dart_refresh": {
            "event_tickers": 161,
            "candidate_tickers": 0,
            "updated_tickers": 0,
            "retired_tickers": 0,
            "unresolved_tickers": 0,
            "api_calls": 0,
        },
    }
    before = output.read_text(encoding="utf-8")
    monkeypatch.setattr(nps, "OUTPUT_PATH", str(output))
    monkeypatch.setattr(nps, "build_nps_holdings", lambda: current)

    assert nps.main() == 0
    assert output.read_text(encoding="utf-8") == before
