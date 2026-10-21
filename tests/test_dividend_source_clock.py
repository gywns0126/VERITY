import json
from datetime import datetime, timedelta, timezone

from api import config
from api.collectors import DartScout, dart_corp_code, dividend_kr
from scripts import freshness_producer_evidence as evidence
from scripts import kr_company_facts_backfill as backfill


KST = timezone(timedelta(hours=9))
CHECKED = datetime(2026, 10, 21, 6, 15, tzinfo=KST)


def test_dart_report_date_and_successful_query_clock_are_separate(monkeypatch):
    monkeypatch.setattr(config, "DART_API_KEY", "fixture")
    monkeypatch.setattr(dividend_kr, "now_kst", lambda: CHECKED)
    monkeypatch.setattr(dart_corp_code, "get_corp_code", lambda ticker: "00126380")
    monkeypatch.setattr(DartScout, "_call", lambda endpoint, params: {
        "status": "000",
        "list": [{"se": "주당 현금배당금(원)", "thstrm": "1,500",
                  "frmtrm": "1,000", "rcept_no": "20260319001234"}],
    })

    result = dividend_kr.fetch_tier1_dart_annual_result("005930", 2025)

    assert result["outcome"] == "record"
    assert result["source_as_of"] == "2026-03-19"
    assert result["source_checked_at"] == CHECKED.isoformat()
    assert result["record"]["source_as_of"] == "2026-03-19"
    assert result["record"]["source_checked_at"] == CHECKED.isoformat()


def test_non_success_dart_status_never_becomes_no_dividend(monkeypatch):
    monkeypatch.setattr(config, "DART_API_KEY", "fixture")
    monkeypatch.setattr(dart_corp_code, "get_corp_code", lambda ticker: "00126380")
    monkeypatch.setattr(DartScout, "_call", lambda endpoint, params: {
        "status": "020", "message": "quota",
    })

    result = dividend_kr.fetch_tier1_dart_annual_result("005930", 2025)

    assert result == {"outcome": "failed", "source_status": "020"}
    assert "source_checked_at" not in result


def test_dart_exception_log_does_not_expose_exception_message(monkeypatch, capsys):
    monkeypatch.setattr(config, "DART_API_KEY", "fixture")
    monkeypatch.setattr(dart_corp_code, "get_corp_code", lambda ticker: "00126380")
    monkeypatch.setattr(
        DartScout,
        "_call",
        lambda endpoint, params: (_ for _ in ()).throw(
            RuntimeError("https://example.invalid?crtfc_key=secret")
        ),
    )

    result = dividend_kr.fetch_tier1_dart_annual_result("005930", 2025)

    output = capsys.readouterr().out
    assert result == {"outcome": "failed", "reason": "RuntimeError"}
    assert "RuntimeError" in output
    assert "secret" not in output
    assert "crtfc_key" not in output


def test_dart_013_is_a_successful_no_data_query_with_no_source_report_date(monkeypatch):
    monkeypatch.setattr(config, "DART_API_KEY", "fixture")
    monkeypatch.setattr(dividend_kr, "now_kst", lambda: CHECKED)
    monkeypatch.setattr(dart_corp_code, "get_corp_code", lambda ticker: "00126380")
    monkeypatch.setattr(DartScout, "_call", lambda endpoint, params: {
        "status": "013", "list": [],
    })

    result = dividend_kr.fetch_tier1_dart_annual_result("005930", 2025)

    assert result == {"outcome": "no_data", "source_status": "013",
                      "source_checked_at": CHECKED.isoformat(), "source_as_of": None}


def test_failed_sweep_preserves_existing_ledger(monkeypatch, tmp_path):
    path = tmp_path / "dividends_kr.json"
    monkeypatch.setattr(dividend_kr, "_DIVIDENDS_DB_PATH", str(path))
    original = {"005930": [{"ex_date": "2025-12-30", "updated_at": "2026-08-01T00:00:00+09:00"}]}
    dividend_kr.save_dividends_db(original)
    monkeypatch.setattr(dividend_kr, "fetch_tier1_dart_annual_result",
                        lambda ticker, year: {"outcome": "failed", "reason": "timeout"})
    monkeypatch.setattr(dividend_kr, "fetch_tier0_pykrx",
                        lambda *args: (_ for _ in ()).throw(AssertionError("no fallback")))

    result = dividend_kr.sweep_annual_plans_detailed(["005930"], 2025)

    assert result["005930"]["artifact_status"] == "preserved"
    assert json.loads(path.read_text()) == original


def test_malformed_or_empty_success_response_is_not_a_success(monkeypatch):
    monkeypatch.setattr(config, "DART_API_KEY", "fixture")
    monkeypatch.setattr(dart_corp_code, "get_corp_code", lambda ticker: "00126380")
    for response in (None, {"status": "000", "list": []},
                     {"status": "000", "list": [{}]},
                     {"status": "000", "list": ["bad"]}):
        monkeypatch.setattr(DartScout, "_call", lambda endpoint, params, value=response: value)
        result = dividend_kr.fetch_tier1_dart_annual_result("005930", 2025)
        assert result["outcome"] == "failed"
        assert "source_checked_at" not in result


def test_success_response_requires_cash_row_and_parseable_amount_contract(monkeypatch):
    monkeypatch.setattr(config, "DART_API_KEY", "fixture")
    monkeypatch.setattr(dividend_kr, "now_kst", lambda: CHECKED)
    monkeypatch.setattr(dart_corp_code, "get_corp_code", lambda ticker: "00126380")

    for rows, reason in (
        ([{"se": "주당액면가액(원)", "thstrm": "500", "frmtrm": "500"}],
         "missing_cash_dividend_rows"),
        ([{"se": "주당 현금배당금(원)", "thstrm": "malformed", "frmtrm": "-"}],
         "invalid_cash_dividend_amount"),
        ([{"se": "주당 현금배당금(원)"}],
         "invalid_cash_dividend_amount"),
    ):
        monkeypatch.setattr(DartScout, "_call", lambda endpoint, params, value=rows: {
            "status": "000", "list": value,
        })
        result = dividend_kr.fetch_tier1_dart_annual_result("005930", 2025)
        assert result["outcome"] == "failed"
        assert result["reason"] == reason
        assert "source_checked_at" not in result


def test_explicit_zero_or_dash_cash_values_are_definitive_no_cash(monkeypatch):
    monkeypatch.setattr(config, "DART_API_KEY", "fixture")
    monkeypatch.setattr(dividend_kr, "now_kst", lambda: CHECKED)
    monkeypatch.setattr(dart_corp_code, "get_corp_code", lambda ticker: "00126380")
    monkeypatch.setattr(DartScout, "_call", lambda endpoint, params: {
        "status": "000",
        "list": [{"se": "주당 현금배당금(원)", "thstrm": "0", "frmtrm": "-",
                  "rcept_no": "20260319001234"}],
    })

    result = dividend_kr.fetch_tier1_dart_annual_result("005930", 2025)

    assert result == {
        "outcome": "no_cash_dividend", "source_status": "000",
        "source_checked_at": CHECKED.isoformat(), "source_as_of": "2026-03-19",
    }


def test_invalid_receipt_date_is_not_source_as_of(monkeypatch):
    monkeypatch.setattr(config, "DART_API_KEY", "fixture")
    monkeypatch.setattr(dividend_kr, "now_kst", lambda: CHECKED)
    monkeypatch.setattr(dart_corp_code, "get_corp_code", lambda ticker: "00126380")
    monkeypatch.setattr(DartScout, "_call", lambda endpoint, params: {
        "status": "000",
        "list": [{"se": "주당 현금배당금(원)", "thstrm": "1,500",
                  "rcept_no": "20261340001234"}],
    })

    result = dividend_kr.fetch_tier1_dart_annual_result("005930", 2025)

    assert result["outcome"] == "record"
    assert result["source_as_of"] is None


def test_receipt_hash_is_computed_after_quarantine(monkeypatch, tmp_path):
    ledger = tmp_path / "dividends_kr.json"
    receipt = tmp_path / "metadata/dividends_kr_source_receipt.json"
    ledger.write_text(json.dumps({
        "005930": [{"ex_date": "2025-12-30", "updated_at": "2026-01-01T00:00:00+09:00"}],
    }))
    monkeypatch.setattr(backfill, "DIVIDENDS_PATH", str(ledger))
    monkeypatch.setattr(backfill, "DIVIDENDS_RECEIPT_PATH", str(receipt))
    monkeypatch.setattr(dividend_kr, "_DIVIDENDS_DB_PATH", str(ledger))
    monkeypatch.setattr(dividend_kr, "sweep_annual_plans_detailed", lambda tickers, year: {
        "005930": {"outcome": "record", "source_status": "000",
                   "source_checked_at": "2026-10-21T06:15:01+09:00",
                   "source_as_of": "2026-03-19", "artifact_status": "skip"},
    })

    def quarantine():
        data = json.loads(ledger.read_text())
        data["005930"][0]["implausible"] = True
        ledger.write_text(json.dumps(data))
        return 1

    monkeypatch.setattr(backfill, "quarantine_implausible_dividends", quarantine)
    clocks = iter(["2026-10-21T06:14:59+09:00", "2026-10-21T06:15:00+09:00",
                   "2026-10-21T06:15:02+09:00"])
    monkeypatch.setattr(backfill, "_now_iso", lambda: next(clocks))

    backfill.run_dividends([("005930", "삼성전자")], "2025", 0, False, 1)

    assert json.loads(ledger.read_text())["005930"][0]["implausible"] is True
    assert evidence.collection_receipt("dividends_kr", ledger)["status"] == "bound_query_complete"


def test_bounded_rotation_receipt_preserves_last_success_after_failure(monkeypatch, tmp_path):
    ledger = tmp_path / "dividends_kr.json"
    receipt = tmp_path / "metadata/dividends_kr_source_receipt.json"
    rows = {
        "000001": [{"ex_date": "2025-12-30", "updated_at": "2026-01-01T00:00:00+09:00"}],
        "000002": [{"ex_date": "2025-12-30", "updated_at": "2026-02-01T00:00:00+09:00"}],
        "000003": [{"ex_date": "2025-12-30", "updated_at": "2026-03-01T00:00:00+09:00"}],
    }
    ledger.write_text(json.dumps(rows))
    monkeypatch.setattr(backfill, "DIVIDENDS_PATH", str(ledger))
    monkeypatch.setattr(backfill, "DIVIDENDS_RECEIPT_PATH", str(receipt))
    monkeypatch.setattr(dividend_kr, "_DIVIDENDS_DB_PATH", str(ledger))
    monkeypatch.setattr(backfill, "quarantine_implausible_dividends", lambda: 0)
    selected = []

    def complete(tickers, year):
        selected.append(list(tickers))
        return {ticker: {"outcome": "record", "source_status": "000",
                         "source_checked_at": "2026-10-21T06:15:01+09:00",
                         "source_as_of": "2026-03-19", "artifact_status": "skip"}
                for ticker in tickers}

    monkeypatch.setattr(dividend_kr, "sweep_annual_plans_detailed", complete)
    clocks = iter(["2026-10-21T06:14:59+09:00", "2026-10-21T06:15:00+09:00",
                   "2026-10-21T06:15:02+09:00"])
    monkeypatch.setattr(backfill, "_now_iso", lambda: next(clocks))
    univ = [(ticker, ticker) for ticker in rows]

    first = backfill.run_dividends(univ, "2025", 0, False, 2)

    assert selected == [["000001", "000002"]]
    assert first["progressed"] == 2 and first["scope_total"] == 3
    first_receipt = json.loads(receipt.read_text())
    assert first_receipt["successful_checked_at"] == "2026-10-21T06:15:02+09:00"
    assert first_receipt["all_records_revalidated"] is False
    proof = evidence.collection_receipt("dividends_kr", ledger)
    assert proof["status"] == "bound_query_complete"
    assert proof["scope_counts"] == {
        "selected": 2, "attempted": 2, "successful": 2, "total": 3,
        "rotation_checked": 2,
    }

    def failed(tickers, year):
        selected.append(list(tickers))
        return {ticker: {"outcome": "failed", "reason": "timeout",
                         "artifact_status": "fail"} for ticker in tickers}

    monkeypatch.setattr(dividend_kr, "sweep_annual_plans_detailed", failed)
    clocks = iter(["2026-10-22T00:20:00+09:00", "2026-10-22T00:20:02+09:00"])
    monkeypatch.setattr(backfill, "_now_iso", lambda: next(clocks))

    second = backfill.run_dividends(univ, "2025", 0, False, 2)

    assert selected[-1] == ["000003"]
    assert second["progressed"] == 0 and second["failed"] == 1
    second_receipt = json.loads(receipt.read_text())
    assert second_receipt["outcome"] == "partial_failure"
    assert second_receipt["successful_checked_at"] == first_receipt["successful_checked_at"]
    assert second_receipt["rotation"]["checked_tickers"] == ["000001", "000002"]
    assert all(isinstance(value, list) for value in json.loads(ledger.read_text()).values())
    assert evidence.collection_receipt("dividends_kr", ledger)["status"] == "bound_query_incomplete"
