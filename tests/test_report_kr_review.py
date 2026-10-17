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


def test_separate_statements_require_matching_document_scope(monkeypatch):
    fixture = deepcopy(review._registry())
    entry = fixture['084010']
    for doc in entry['documents'].values():
        if doc.get('fs_div') == 'CFS':
            doc['fs_div'] = 'OFS'
    for row in entry['periods']:
        row['fs_div'] = 'OFS'
    monkeypatch.setattr(review, '_registry', lambda: fixture)
    separate = review.reviewed_financials('084010', STOCK, [], NOW)
    assert len(separate) == 7 and all(r['fs_div'] == 'OFS' for r in separate)
    entry['documents']['half_income']['fs_div'] = 'CFS'
    eligible = review.reviewed_entry('084010', STOCK, NOW)
    assert len(eligible['periods']) == 3
    assert all(r['period_kind'] == 'annual' for r in eligible['periods'])
    for row in entry['periods']:
        row['fs_div'] = 'UNKNOWN'
    assert review.reviewed_entry('084010', STOCK, NOW) is None


def test_latest_peer_reviews_preserve_quarter_ytd_scope_and_source():
    now = datetime(2026, 10, 17, tzinfo=KST)
    expected = [('104700', '한국철강', '00687711', 173809519338, -6284385117, -12691130328),
                ('460860', '동국제강', '01765265', 995514578458, 45563446844, 137488041100)]
    for ticker, name, corp, revenue, op, cash in expected:
        rows = review.reviewed_financials(ticker, {'ticker': ticker, 'name': name, 'corp_code': corp}, [], now)
        assert len(rows) == (6 if ticker == '460860' else 4)
        q2, h1 = _by_period(rows, 2026, 'quarter'), _by_period(rows, 2026, 'ytd')
        assert q2['start'] == '2026-04-01' and h1['start'] == '2026-01-01'
        assert q2['revenue'] == revenue and q2['op'] == op
        assert q2['revenue'] - q2['cost_of_sales'] - q2['sga'] == q2['op']
        assert h1['ocf'] == cash and h1['capex'] > 0
        assert q2['ocf'] is q2['capex'] is None
        assert q2['metric_sources']['sga']['fs_div'] == 'OFS'
        assert all(r['fs_div'] == 'OFS' for r in rows)
        assert all('rcpNo=' + r['accession'] in m['source_url'] for r in rows for m in r['metric_sources'].values())
        if ticker == '460860':
            annual = _by_period(rows, 2025, 'annual')
            assert annual['net'] == 8231853074 and annual['sga'] == 214066943596
            assert annual['revenue'] - annual['cost_of_sales'] - annual['sga'] == annual['op']
            assert not any(r['year'] == 2023 for r in rows)  # First seven-month year is not a full annual.


def test_total_net_review_does_not_reuse_noncontrolling_or_parent_amounts():
    now = datetime(2026, 10, 17, tzinfo=KST)
    for ticker, name, expected in [('018880', '한온시스템', {2024: -358595798106, 2025: -197268294891}),
                                    ('331920', '셀레믹스', {2024: 12266469564, 2025: -4036458382})]:
        rows = review.reviewed_financials(ticker, {'ticker': ticker, 'name': name}, [], now)
        assert len(rows) == 2
        for row in rows:
            assert row['net'] == expected[row['year']] and row['fs_div'] == 'CFS'
            assert row['metric_sources']['net']['name'] == '당기순이익(손실)'
            assert row['metric_sources']['net']['sha256']


def test_table_units_are_converted_once_with_raw_cells_preserved(monkeypatch):
    from datetime import date
    for unit, multiplier in [('천원', 1000), ('백만원', 1000000)]:
        fixture = deepcopy(review._registry())
        entry = fixture['018880']
        entry['documents']['annual_income']['unit'] = unit
        for row in entry['periods']:
            for metric in row['metrics'].values():
                metric['value'] = review._amount(metric['raw']) * multiplier
        monkeypatch.setattr(review, '_registry', lambda: fixture)
        row = review.reviewed_financials('018880', {'ticker':'018880','name':'한온시스템'}, [], date(2026,10,17))[0]
        source = row['metric_sources']['net']
        assert row['net'] == review._amount(source['raw_text']) * multiplier
        assert source['reported_unit'] == unit and source['unit_multiplier'] == multiplier
        entry['periods'][0]['metrics']['net']['value'] //= multiplier
        assert len(review.reviewed_entry('018880', {'ticker':'018880','name':'한온시스템'}, date(2026,10,17))['periods']) == 1
        entry['documents']['annual_income']['unit'] = '단위 미확인'
        assert review.reviewed_entry('018880', {'ticker':'018880','name':'한온시스템'}, date(2026,10,17)) is None


def test_large_issuer_losses_and_rewritten_comparatives_use_reported_totals():
    now = datetime(2026, 10, 17, tzinfo=KST)
    cases = [('051910','LG화학',-977063000000,515011000000,1000000),
             ('011170','롯데케미칼',-2476176326250,-1825555752135,1),
             ('097950','CJ제일제당',-416955408000,345925769000,1000),
             ('000070','삼양홀딩스',-298132876106,89491916474,1)]
    for ticker,name,current,prior,multiplier in cases:
        rows=review.reviewed_financials(ticker,{'ticker':ticker,'name':name},[],now)
        assert len(rows)==2
        assert _by_period(rows,2025,'annual')['net']==current
        assert _by_period(rows,2024,'annual')['net']==prior
        assert all(r['metric_sources']['net']['unit_multiplier']==multiplier for r in rows)
        assert all(r['metric_sources']['net']['name'] in ('당기순이익(손실)','당기순손실') for r in rows)


def test_discontinued_results_are_not_operating_profit_or_total_net():
    now = datetime(2026, 10, 17, tzinfo=KST)
    holdings = review.reviewed_financials('005440', {'ticker':'005440','name':'현대지에프홀딩스'}, [], now)
    assert _by_period(holdings,2025,'annual')['op'] == 274073694000
    assert _by_period(holdings,2024,'annual')['op'] == 198099994000
    assert _by_period(holdings,2023,'annual')['op'] == -11033826000
    assert _by_period(holdings,2025,'annual')['net'] == 518661888000
    wia = review.reviewed_financials('011210', {'ticker':'011210','name':'현대위아'}, [], now)
    current = _by_period(wia,2025,'annual')
    assert current['op'] == 204413000000 and current['op'] != -43559000000
    assert current['net'] == 116932000000 and current['net'] != 160491000000
    assert _by_period(wia,2024,'annual')['op'] == 218810000000
    assert current['metric_sources']['net']['name'] == '당기순이익'
    assert current['metric_sources']['op']['unit_multiplier'] == 1000000
