import json
from datetime import datetime

import pytest

from api.utils.dart_period import valid_period_end, verified_period
from api.builders import dart_batch_builder as batch
from api.builders import dart_quarterly_public_builder as public
from scripts.repair_dart_future_periods import repair_rows


CONTEXT = dict(corp_code="01363818", bsns_year="2026", reprt_code="11012",
               fs_div="OFS", receipt="20260514000609", total_assets=100,
               as_of="2026-10-17")


def principal():
    common = {k: v for k, v in CONTEXT.items() if k in {"corp_code", "bsns_year", "reprt_code", "fs_div"}}
    common["rcept_no"] = CONTEXT["receipt"]
    return {"status": "000", "list": [
        {**common, "sj_div": "BS", "account_nm": "자산총계",
         "thstrm_dt": "2026.03.31 현재", "thstrm_amount": "100"},
        {**common, "sj_div": "IS", "account_nm": "매출액",
         "thstrm_dt": "2026.01.01 ~ 2026.03.31", "thstrm_amount": "10"},
    ]}


def test_semiannual_reit_uses_reported_period_not_calendar_offset():
    result = verified_period(principal(), **CONTEXT)
    assert result["period_end"] == "2026-03-31"
    assert result["period_start"] == "2026-01-01"
    assert result["rcept_no"] == CONTEXT["receipt"]


@pytest.mark.parametrize("field,value", [
    ("fs_div", "CFS"), ("receipt", "20261017000001"), ("corp_code", "99999999"),
    ("reprt_code", "11011"), ("bsns_year", "2025"), ("total_assets", 101),
    ("as_of", "2026-03-30"),
])
def test_period_identity_mismatch_rejected(field, value):
    assert verified_period(principal(), **{**CONTEXT, field: value}) == {}


def test_inconsistent_statement_period_rejected():
    data = principal()
    data["list"][1]["thstrm_dt"] = "2026.01.01 ~ 2026.06.30"
    assert not verified_period(data, **CONTEXT)


def test_real_calendar_date_and_leap_year():
    assert valid_period_end("2024-02-29", as_of="2026-10-17")
    assert not valid_period_end("2026-02-29", as_of="2026-10-17")
    assert not valid_period_end("2026-12-31", as_of="2026-10-17")


def test_append_source_period_and_preserve_success_time(tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "OUTPUT_PATH", str(tmp_path / "fundamentals.json"))
    monkeypatch.setattr(batch, "_fiscal_cache", {"330590": "06"})
    fund = {"report_date": "2026", "reprt_code": "11012", "fs_div": "OFS",
            **verified_period(principal(), **CONTEXT), "fetched_at": "2026-05-15T00:00:00+09:00",
            "collection_status": "reused", "revenue": 10}
    assert batch._append_quarterly_snapshots({
        "collected_at": "2026-10-17T00:00:00+09:00", "fundamentals": {"330590": fund}}) == 1
    row = json.loads((tmp_path / "dart_quarterly_snapshots.jsonl").read_text())
    assert row["quarter_end"] == "2026-03-31"
    assert row["fetched_at"] == row["last_successful_at"] == fund["fetched_at"]
    assert row["recorded_at"].startswith("2026-10-17")


@pytest.mark.parametrize("ticker,fund", [
    ("330590", {"report_date": "2026", "reprt_code": "11012"}),
    ("005930", {"report_date": "2026", "reprt_code": "11011"}),
    ("005930", {"report_date": "2025", "collection_status": "reused"}),
])
def test_append_does_not_fabricate_dates_or_success_times(tmp_path, monkeypatch, ticker, fund):
    monkeypatch.setattr(batch, "OUTPUT_PATH", str(tmp_path / "fundamentals.json"))
    monkeypatch.setattr(batch, "_fiscal_cache", {"330590": "06"})
    monkeypatch.setattr(batch, "_now_kst", lambda: datetime(2026, 10, 17, tzinfo=batch.KST))
    assert batch._append_quarterly_snapshots({
        "collected_at": "2026-10-17T00:00:00+09:00", "fundamentals": {ticker: fund}}) == 0


def test_public_gate_rejects_future_and_nonfinite_preserves_leap(tmp_path, monkeypatch):
    path = tmp_path / "rows.jsonl"
    rows = [{"ticker": "T", "quarter_end": q, "roa": 1, "fetched_at": "2026-10-17"}
            for q in ("2024-02-29", "2024-05-31", "2024-08-31", "2024-11-30", "2026-11-30", "2026-02-30")]
    rows[0]["debt_ratio"] = float("nan")
    rows[0]["revenue"] = float("inf")
    path.write_text("".join(json.dumps(x) + "\n" for x in rows))
    monkeypatch.setattr(public, "INPUT_PATH", str(path))
    monkeypatch.setattr(public, "_fiscal_map", {"T": "02"})
    monkeypatch.setattr(public, "_now_kst", lambda: datetime(2026, 10, 17, tzinfo=public.KST))
    result = public.build()
    qs = result["stocks"]["T"]["quarters"]
    assert len(qs) == 4 and qs[0]["q"] == "2024-02-29"
    assert "debt_ratio" not in qs[0] and "revenue" not in qs[0]
    assert result["_meta"]["dropped_invalid_or_future_rows"] == 2
    json.dumps(result, allow_nan=False)


def test_offline_repair_requires_amounts_and_preserves_original():
    proof = {"ticker": "T", "fs_div": "CFS", "reprt_code": "11012",
             "revenue": 10, "operating_profit": 3, "net_income": 2,
             "incorrect_period_end": "2026-12-31", "period_end": "2026-03-31",
             "period_start": "2026-01-01", "period_basis": "source_reported",
             "rcept_no": "20260514000609", "source_url": "https://dart.fss.or.kr/"}
    row = {k: proof[k] for k in ("ticker", "fs_div", "reprt_code", "revenue", "operating_profit", "net_income")}
    row.update(quarter_end="2026-12-31", fetched_at="2026-08-17")
    wrong = {**row, "net_income": 999}
    evidence = {"rows": [proof], "verified_on": "2026-10-17"}
    out, fixed, quarantine = repair_rows([json.dumps(row), json.dumps(wrong)], evidence, "2026-10-17")
    assert len(out) == len(fixed) == len(quarantine) == 1
    assert json.loads(out[0])["quarter_end"] == "2026-03-31"
    assert json.loads(out[0])["fetched_at"] == row["fetched_at"]
    assert fixed[0]["original"] == row and quarantine[0]["original"] == wrong
    assert repair_rows(out, evidence, "2026-10-17")[1:] == ([], [])


def test_failed_record_is_retried():
    from tests.test_dart_batch_builder import TestIsFreshDart
    assert not batch._is_fresh_dart({**TestIsFreshDart.BASE, "collection_status": "retained_after_failure"}, "2025")


def test_partial_batch_failure_preserves_previous_value_and_clock(monkeypatch):
    from api.collectors import dart_fundamentals as collector
    old = {"source": "DART", "report_date": "2024", "revenue": 123,
           "fetched_at": "2025-04-01", "last_successful_at": "2025-04-01"}
    monkeypatch.setattr(batch, "_build_kr_universe_tickers", lambda: ["A", "B"])
    monkeypatch.setattr(batch, "_load_existing", lambda: {"fundamentals": {"A": old}})
    monkeypatch.setattr(collector, "fetch_dart_fundamentals_batch", lambda *a, **kw: {
        "A": {"source": "error"}, "B": {"source": "DART", "revenue": 789}})
    out = batch.build()
    assert out["fundamentals"]["A"] == {**old, "collection_status": "retained_after_failure"}
    assert out["fundamentals"]["B"]["revenue"] == 789
    assert out["diagnostics"]["failed_tickers"] == ["A"]


def test_empty_public_build_blocks_publish_without_overwriting(tmp_path, monkeypatch):
    source, dest = tmp_path / "input.jsonl", tmp_path / "output.json"
    source.write_text("")
    dest.write_text('{"previous": true}')
    monkeypatch.setattr(public, "INPUT_PATH", str(source))
    monkeypatch.setattr(public, "OUTPUT_PATH", str(dest))
    assert public.main() == 1
    assert json.loads(dest.read_text()) == {"previous": True}


def test_invalid_success_time_cannot_mask_older_fetch_time(tmp_path, monkeypatch):
    source = tmp_path / "input.jsonl"
    rows = [{"ticker": "T", "quarter_end": "2026-09-30", "roa": 1,
             "last_successful_at": "invalid", "fetched_at": "2026-08-01"},
            {"ticker": "T", "quarter_end": "2026-06-30", "roa": 1}]
    source.write_text("".join(json.dumps(row) + "\n" for row in rows))
    monkeypatch.setattr(public, "INPUT_PATH", str(source))
    monkeypatch.setattr(public, "_now_kst", lambda: datetime(2026, 10, 17, tzinfo=public.KST))
    assert public.build()["_meta"]["dropped_invalid_or_future_rows"] == 2


def test_noncalendar_collector_binds_period_to_receipt(monkeypatch):
    from api.collectors import dart_fundamentals as collector, dart_corp_code
    monkeypatch.setattr(dart_corp_code, "get_corp_code", lambda _: CONTEXT["corp_code"])
    monkeypatch.setattr(batch, "_fiscal_cache", {"330590": "06"})
    monkeypatch.setattr(collector, "_get_fnltt_all_data", lambda *a, **kw: {
        "status": "000", "list": [{"rcept_no": CONTEXT["receipt"]}],
        "_retrieved_at": "2026-05-15T00:00:00+09:00"})
    monkeypatch.setattr(collector, "_extract_pl_bs_from_dart", lambda *a, **kw: {"total_assets": 100})
    monkeypatch.setattr(collector, "_get_principal_accounts", lambda *a: principal())
    monkeypatch.setattr(collector, "_yf_fallback_for_ticker", lambda _: {})
    # CFS lookup is refused by principal OFS identity; it must not fabricate a date.
    out = collector._fetch_one_dart_fundamentals("330590", "2026", "11012")
    assert out["period_basis"] == "unverified"
    assert out["last_successful_at"] == "2026-05-15T00:00:00+09:00"
    def all_ofs(*a, **kw):
        return {"status": "013"} if kw["fs_div"] == "CFS" else {
            "status": "000", "list": [{"rcept_no": CONTEXT["receipt"]}]}
    monkeypatch.setattr(collector, "_get_fnltt_all_data", all_ofs)
    out = collector._fetch_one_dart_fundamentals("330590", "2026", "11012")
    assert out["period_end"] == "2026-03-31" and out["period_basis"] == "source_reported"
