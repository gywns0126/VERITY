"""Only explicitly reviewed DART HTML may supplement matching KR periods."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "vercel-api" / "api"))
import report_kr_review as review


KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 16, 21, 0, tzinfo=KST)
STOCK = {"ticker": "084010", "name": "대한제강", "corp_code": "00113225"}


def _by_period(rows, year, kind):
    return next(row for row in rows if row["year"] == year and row["period_kind"] == kind)


def test_review_entry_requires_name_ticker_and_supplied_corp_code():
    entry = review.reviewed_entry("084010", STOCK, NOW)
    assert entry and entry["corp_code_match"] == "input_verified"
    assert len(entry["periods"]) == 7
    assert review.reviewed_entry("000000", STOCK, NOW) is None
    assert review.reviewed_entry("084010", {**STOCK, "name": "다른회사"}, NOW) is None
    assert review.reviewed_entry("084010", {**STOCK, "corp_code": "99999999"}, NOW) is None
    assert review.reviewed_entry("084010", {**STOCK, "dart_corp_code": "99999999"}, NOW) is None
    assert review.reviewed_entry("084010", {**STOCK, "financial_evidence": {"corp_code": "99999999"}}, NOW) is None
    assert review.reviewed_entry("084010", {"ticker": "084010", "name": "대한제강"}, NOW)["corp_code_match"] == "registry_only_input_missing"


def test_annual_values_and_sga_components_retain_original_2025_basis():
    rows = review.reviewed_financials("084010", STOCK, [], NOW)
    assert len(rows) == 7
    annual = _by_period(rows, 2025, "annual")
    assert annual["revenue"] == 1247058624052
    assert annual["ocf"] == 39618460129
    assert annual["capex"] == 20703709165
    assert annual["source"].endswith("API 원응답 아님")
    assert annual["metric_sources"]["revenue"]["raw_text"] == "1,247,058,624,052"
    assert annual["metric_sources"]["revenue"]["sha256"]
    assert annual["derived_metrics"]["sga"]["value"] == 73115271001
    assert sum(c["value"] for c in annual["derived_metrics"]["sga"]["components"]) == 73115271001
    assert "sga" not in annual  # Derived source is not a replacement financials operand.
    for year, expected in ((2023, 67071678635), (2024, 66343974431)):
        row = _by_period(rows, year, "annual")
        assert row["derived_metrics"]["sga"]["value"] == expected
        assert sum(c["value"] for c in row["derived_metrics"]["sga"]["components"]) == expected
    entry = review.reviewed_entry("084010", STOCK, NOW)
    assert "1,184,170,129,020" in entry["notes"][0]
    assert "1,247,058,624,052" in entry["notes"][0]
    assert "자동 대체하지 않는다" in entry["notes"][0]


def test_quarter_and_ytd_are_distinct_and_unreported_net_stays_null():
    rows = review.reviewed_financials("084010", STOCK, [], NOW)
    q2 = _by_period(rows, 2026, "quarter")
    h1 = _by_period(rows, 2026, "ytd")
    prior_q2 = _by_period(rows, 2025, "quarter")
    prior_h1 = _by_period(rows, 2025, "ytd")
    assert q2["start"] == "2026-04-01" and "산출" in q2["start_basis"]
    assert prior_q2["start"] == "2025-04-01" and prior_q2["start_basis"]
    assert q2["revenue"] == 387727240066 and q2["op"] == 16292618911
    assert h1["revenue"] == 692069629955 and h1["op"] == 16780631998
    assert h1["net"] == 9033951339 and h1["metric_sources"]["net"]["name"] == "연결 당기순손익"
    assert h1["ocf"] == -6818141298 and h1["capex"] == 5754700573
    assert prior_h1["ocf"] == 48206240793 and prior_h1["capex"] == 11213465993
    assert q2["net"] is q2["ocf"] is q2["capex"] is None
    assert prior_q2["net"] is prior_q2["ocf"] is prior_q2["capex"] is None
    assert prior_h1["net"] is None
    assert q2["metric_sources"]["revenue"]["column"].endswith("3개월")
    assert h1["metric_sources"]["ocf"]["column"] == "제 74 기 반기"


def test_future_review_and_stale_review_fail_closed():
    assert review.reviewed_entry("084010", STOCK, datetime(2026, 10, 15, tzinfo=KST)) is None
    assert review.reviewed_entry("084010", STOCK, datetime(2027, 4, 15, tzinfo=KST)) is None


def test_future_filing_is_not_returned_even_if_review_date_is_current(monkeypatch):
    fixture = deepcopy(review._registry())
    entry = fixture["084010"]
    entry["documents"]["half_income"]["filed"] = "2026-10-17"
    monkeypatch.setattr(review, "_registry", lambda: fixture)
    eligible = review.reviewed_entry("084010", STOCK, NOW)
    assert eligible and len(eligible["periods"]) == 3
    assert all(row["period_kind"] == "annual" for row in eligible["periods"])


def test_newer_or_unknown_same_period_source_is_preserved_without_mutation():
    base = _by_period(review.reviewed_financials("084010", STOCK, [], NOW), 2026, "ytd")
    newer = {**base, "filed": "2026-09-01", "accession": "20260901000001", "ocf": 123}
    unknown = {**base, "filed": "", "ocf": 456}
    for existing in (newer, unknown):
        before = deepcopy(existing)
        result = review.reviewed_financials("084010", STOCK, [existing], NOW)
        assert result[0] == before
        assert existing == before
        assert len([r for r in result if r.get("start") == base["start"] and r.get("end") == base["end"] and r.get("period_kind") == "ytd"]) == 1


def test_older_filing_replaced_and_same_filing_only_fills_missing_metrics():
    old = {"year": 2026, "start": "2026-01-01", "end": "2026-06-30", "period_kind": "ytd",
           "currency": "KRW", "fs_div": "CFS", "filed": "2026-07-01", "accession": "20260701000001", "revenue": 1}
    replaced = _by_period(review.reviewed_financials("084010", STOCK, [old], NOW), 2026, "ytd")
    assert replaced["revenue"] == 692069629955 and replaced["accession"] == "20260814003201"
    same = {**old, "filed": "2026-08-14", "accession": "20260814003201", "revenue": 777, "ocf": None}
    filled = _by_period(review.reviewed_financials("084010", STOCK, [same], NOW), 2026, "ytd")
    assert filled["revenue"] == 777 and filled["ocf"] == -6818141298
    assert "revenue" not in filled["metric_sources"]
    assert filled["metric_sources"]["ocf"]["raw_text"] == "(6,818,141,298)"
    assert old["revenue"] == 1 and same["ocf"] is None
