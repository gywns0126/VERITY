import json

from api.builders.report_kr_evidence import (
    EVIDENCE_SCHEMA_VERSION,
    load_financial_evidence,
    load_previous_financial_evidence,
    periods_from_rows,
    reconcile_financial_evidence,
)


def row(name, amount, *, ticker="005930", scope="CFS", rcept="20250814003156",
        code="11012", dates="2025.01.01 ~ 2025.06.30", add=None, account_id=None):
    return {
        "stock_code": ticker, "rcept_no": rcept, "reprt_code": code,
        "fs_div": scope, "currency": "KRW", "sj_div": "IS",
        "account_nm": name, "account_id": account_id,
        "thstrm_amount": str(amount), "thstrm_add_amount": None if add is None else str(add),
        "thstrm_dt": dates,
    }


def test_half_year_uses_ytd_amount_and_keeps_metadata():
    periods = periods_from_rows([
        row("매출액", 74, add=153), row("영업이익", 4, add=11),
        row("당기순이익(손실)", 5, add=13),
    ])["005930"]
    assert len(periods) == 1
    p = periods[0]
    assert (p["period_kind"], p["start"], p["end"]) == ("ytd", "2025-01-01", "2025-06-30")
    assert (p["revenue"], p["op"], p["net"]) == (153, 11, 13)
    assert p["fs_div"] == "CFS" and p["currency"] == "KRW"
    assert p["accession"] == p["rcept_no"] == "20250814003156"
    assert p["filed"] == "2025-08-14"
    assert p["metric_sources"]["revenue"]["name"] == "매출액"


def test_missing_ytd_and_missing_identity_are_not_promoted():
    missing_add = row("매출액", 74, add=None)
    missing_currency = row("영업이익", 4, add=11)
    missing_currency["currency"] = ""
    assert periods_from_rows([missing_add, missing_currency]) == {}


def test_zero_is_a_reported_value_not_missing():
    annual_zero = row("영업이익", 0, code="11011", dates="2024.01.01 ~ 2024.12.31",
                      rcept="20250311001085")
    period = periods_from_rows([annual_zero])["005930"][0]
    assert period["op"] == 0
    assert period["metric_sources"]["op"]["name"] == "영업이익"


def test_conflicting_duplicate_withholds_only_that_metric():
    rows = [
        row("매출액", 100, add=200), row("매출액", 101, add=201),
        row("영업이익", 10, add=20),
    ]
    p = periods_from_rows(rows)["005930"][0]
    assert p["revenue"] is None
    assert "revenue" not in p["metric_sources"]
    assert p["op"] == 20


def test_scope_and_accession_are_not_mixed_and_cfs_is_preferred():
    rows = [
        row("매출액", 1, add=10, scope="OFS", rcept="20250814000001"),
        row("영업이익", 2, add=20, scope="OFS", rcept="20250814000001"),
        row("매출액", 3, add=30, scope="CFS", rcept="20250814000002"),
        row("영업이익", 4, add=40, scope="CFS", rcept="20250814000002"),
    ]
    p = periods_from_rows(rows)["005930"][0]
    assert p["fs_div"] == "CFS"
    assert p["rcept_no"] == "20250814000002"
    assert (p["revenue"], p["op"]) == (30, 40)


def test_financial_company_does_not_invent_revenue():
    rows = [
        row("순이자손익", 100, ticker="105560", code="11011",
            dates="2025.01.01 ~ 2025.12.31", add=None),
        row("영업이익(손실)", 80, ticker="105560", code="11011",
            dates="2025.01.01 ~ 2025.12.31", add=None),
        row("당기순이익(손실)", 60, ticker="105560", code="11011",
            dates="2025.01.01 ~ 2025.12.31", add=None),
    ]
    p = periods_from_rows(rows)["105560"][0]
    assert p["revenue"] is None
    assert (p["op"], p["net"]) == (80, 60)


def test_cache_loader_is_graceful_and_reports_denominator(tmp_path):
    annual = [
        row("매출액", 100, code="11011", dates="2024.01.01 ~ 2024.12.31",
            rcept="20250311001085"),
        row("영업이익", 10, code="11011", dates="2024.01.01 ~ 2024.12.31",
            rcept="20250311001085"),
    ]
    (tmp_path / "one.json").write_text(json.dumps({"status": "000", "list": annual}), encoding="utf-8")
    (tmp_path / "empty.json").write_text(json.dumps({"status": "013", "list": []}), encoding="utf-8")
    (tmp_path / "error_with_rows.json").write_text(
        json.dumps({"status": "020", "list": annual}), encoding="utf-8"
    )
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    evidence, stats = load_financial_evidence(str(tmp_path), {"005930"})
    assert evidence["005930"]["schema_version"] == EVIDENCE_SCHEMA_VERSION
    assert evidence["005930"]["periods"][0]["revenue"] == 100
    assert stats == {"cache_files": 4, "parsed_files": 3, "nonempty_files": 1,
                     "tickers": 1, "attached": 1}
    assert load_financial_evidence(str(tmp_path / "missing"))[0] == {}


def test_previous_evidence_survives_missing_cache_and_invalid_shape_is_rejected(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    evidence, _stats = load_financial_evidence(str(source))
    assert evidence == {}

    valid_financial = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "source": "DART 단일회사 주요계정",
        "periods": [{
            "year": 2024, "start": "2024-01-01", "end": "2024-12-31",
            "period_kind": "annual", "currency": "KRW", "fs_div": "CFS",
            "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20250311001085",
            "filed": "2025-03-11", "accession": "20250311001085", "rcept_no": "20250311001085",
            "revenue": 100, "op": None, "net": None, "ocf": None, "capex": None,
            "metric_sources": {"revenue": {
                "account_id": None, "name": "매출액", "start": "2024-01-01", "end": "2024-12-31",
                "currency": "KRW", "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20250311001085",
            }},
        }],
    }
    snapshot = {"stocks": [
        {"ticker": "005930", "financial_evidence": valid_financial},
        {"ticker": "000660", "financial_evidence": {"periods": valid_financial["periods"]}},
    ]}
    path = tmp_path / "stock_report_public.json"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    financial = load_previous_financial_evidence(str(path))
    assert financial == {"005930": valid_financial}
    selected, preserved = reconcile_financial_evidence({"005930", "000660"}, {}, financial)
    assert selected == {"005930": valid_financial}
    assert preserved == 1

    newer = json.loads(json.dumps(valid_financial))
    newer_period = json.loads(json.dumps(valid_financial["periods"][0]))
    newer_period.update({
        "year": 2025, "start": "2025-01-01", "end": "2025-12-31",
        "filed": "2026-03-10", "accession": "20260310002820", "rcept_no": "20260310002820",
        "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260310002820",
    })
    newer_period["metric_sources"]["revenue"].update({
        "start": "2025-01-01", "end": "2025-12-31",
        "source_url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260310002820",
    })
    newer["periods"] = [newer_period]
    selected, preserved = reconcile_financial_evidence({"005930"}, {"005930": newer}, financial)
    assert [p["year"] for p in selected["005930"]["periods"]] == [2024, 2025]
    assert preserved == 0
