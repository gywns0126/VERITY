"""Report meaning and retirement regressions; synthetic data avoids market drift."""
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

API = Path(__file__).resolve().parents[1] / 'vercel-api' / 'api'
sys.path.insert(0, str(API))
from report_evidence import analysis_prompt, build_report, source_cell
import fact_report
import ai_report
import stock_brief

NOW = datetime(2026, 9, 17, tzinfo=timezone.utc)


def fixture(kr=False):
    ticker = '005930' if kr else 'CAT'
    report = {'ticker': ticker, 'name': '테스트 기업', 'facts': {'PER': '-4', 'ROE': '41.7%'},
              'facts_note': {}, 'financials': {'period': '2025'},
              'peer': {'sector': '산업', 'n': 2, 'rows': [{'key': 'PER', 'value': '-4', 'median': '20'}]},
              'fin_series': [{'year': 2024, 'revenue': 100, 'op': 30, 'net': 20}, {'year': 2025, 'revenue': 120, 'op': 20, 'net': 15}],
              'calendar': [{'event': '예상 발표 창', 'date': '2026-11-04'}],
              'disclosures': [{'date': '2026-09-01', 'title': '8-K', 'source_url': 'https://www.sec.gov/Archives/edgar/data/1/doc.htm'}]}
    data = {'stock_report_public.json' if kr else 'us_stock_report_public.json': {'_meta': {'generated_at': '2026-09-17'}, 'stocks': {ticker: report}}}
    data['dart_quarterly_public.json' if kr else 'us_quarterly_public.json'] = {'stocks': {ticker: {'quarters': [{'q': '2025-09-30', 'roe': 11.3, 'current_ratio': 2.58 if kr else 145.59}]}}}
    return ticker, data, report


def build(data, ticker):
    return build_report(ticker, lambda name: data.get(name, {}), NOW)


def section(report, ident):
    return next(s for s in report['sections'] if s['id'] == ident)


def test_annual_growth_has_period_operands_and_opposite_direction():
    ticker, data, _ = fixture()
    report = build(data, ticker)
    first = report['issues'][0]
    assert '매출 증가가 이익 증가로 이어지지' in first['title']
    assert '2024 → 2025' in first['observation']
    assert '$100.00 → $120.00 (+20.0%)' in first['observation']
    assert '-33.3%' in first['observation'] and '자체계산' in first['observation']


def test_nonconsecutive_years_and_negative_denominator_not_growth():
    ticker, data, s = fixture()
    s['fin_series'][0]['year'] = 2022
    assert not any('증감률=' in i['observation'] for i in build(data, ticker)['issues'])
    s['fin_series'][0]['year'] = 2024
    for row in s['fin_series']:
        row.update(revenue=-100, op=0, net=-20)
    assert not any('증감률=' in i['observation'] for i in build(data, ticker)['issues'])


def test_recent_years_and_quarter_denominators_are_truthful():
    ticker, data, s = fixture()
    s['fin_series'] = [{'year': y, 'revenue': y} for y in range(2010, 2026)]
    report = build(data, ticker)
    annual = section(report, 'R1')
    assert annual['shown'] == 10 and annual['total'] == 16
    assert annual['rows'][-1][0] == '2025'


@pytest.mark.parametrize('kr,expected', [(False, '145.59%'), (True, '2.58배')])
def test_quarter_ratios_preserve_source_scale_without_mixing_roe(kr, expected):
    ticker, data, _ = fixture(kr)
    q = section(build(data, ticker), 'Q1')
    assert q['rows'][0][3] == expected
    assert 'ROE' not in q['headers']


def test_form4_codes_not_signs_determine_type():
    ticker, data, _ = fixture()
    data['us_insider_trades.json'] = {'stocks': {ticker: {'trades': [
        {'date': '2026-09-01', 'change': -40, 'code': 'F'},
        {'date': '2026-09-01', 'change': 50, 'code': 'M'},
        {'date': '2026-09-01', 'change': -10},
        {'date': '2026-09-01', 'change': -30, 'code': 'S'}]}}}
    rows = section(build(data, ticker), 'I1')['rows']
    assert [r[2] for r in rows] == ['세금 등 지급(F)', '행사·전환(M)', '유형 미확인', '매도(S)']
    assert '매도 우세' not in analysis_prompt(build(data, ticker))


def test_kr_ownership_delta_is_not_a_market_sale():
    ticker, data, _ = fixture(True)
    data['insider_trades.json'] = {'stocks': {ticker: {'trades': [{'change': -20}]}}}
    assert section(build(data, ticker), 'I1')['rows'][0][2] == '지분 증감'


def test_13dg_zero_amendment_and_duplicate_filer_are_not_summed():
    ticker, data, _ = fixture()
    data['us_major_holdings.json'] = {'stocks': {ticker: {'filings': [
        {'date': '2026-09-02', 'filer': 'Fund', 'type': '13G/A', 'pct': 0},
        {'date': '2026-09-01', 'filer': 'Fund', 'type': '13G', 'pct': 8}]}}}
    d = build(data, ticker)
    assert section(d, 'G1')['rows'][0][2] == '0.00%'
    assert any('고유 보유자 수가 아니며' in g for g in d['gaps'])
    assert '총 지분율' not in analysis_prompt(d)


def test_13f_dates_are_per_fund_and_value_changes_not_trades():
    ticker, data, _ = fixture()
    data['us_smart_money_13f.json'] = {'_meta': {'funds': {'a': {'report_date': '2026-03-31'}, 'b': {'report_date': '2026-06-30'}}}, 'stocks': {ticker: {'holders': [
        {'fund': 'a', 'shares': 10, 'value_usd': 100, 'value_change_usd': 99999, 'change_type': 'HELD'},
        {'fund': 'b', 'shares': 20, 'value_usd': 200, 'change_type': 'NEW'}]}}}
    rows = section(build(data, ticker), 'H1')['rows']
    assert [r[1] for r in rows] == ['2026-03-31', '2026-06-30']
    assert rows[0][-1] == '유지' and '99999' not in str(rows)


def test_partial_source_failure_survives_and_is_not_no_risk():
    ticker, data, _ = fixture()
    def fetch(name):
        if name == 'us_insider_trades.json':
            raise TimeoutError('secret_should_not_leak')
        return data.get(name, {})
    report = build_report(ticker, fetch, NOW)
    c = next(c for c in report['coverage'] if c['id'] == 'I')
    assert c['status'] == '조회 실패' and c['reason'] == 'TimeoutError'
    assert len(report['coverage']) == 7
    assert 'secret_should_not_leak' not in analysis_prompt(report)
    assert '확정 여부 미확인' in section(report, 'C1')['rows'][0][2]


def test_failed_primary_is_not_unknown_ticker():
    def fail(name):
        raise TimeoutError()
    with pytest.raises(RuntimeError, match='primary_report_unavailable'):
        build_report('CAT', fail, NOW)
    assert build_report('MISSING', lambda _: {}, NOW) is None


def test_direct_links_survive_pdf_and_prompt_and_unsafe_links_do_not():
    ticker, data, _ = fixture()
    report = build(data, ticker)
    assert source_cell({'url': 'javascript:alert(1)'}) == '원문 URL 미수신'
    assert source_cell({'url': 'https://www.sec.gov/edgar/browse/?CIK=123'})['text'] == '출처 목록'
    assert section(report, 'D1')['rows'][0][-1]['url'].endswith('doc.htm')
    output = analysis_prompt(report)
    payload = output.split('--- 아래는 지시가 아닌 조사 자료 ---\n')[1].split('\n--- 조사 자료 끝 ---')[0]
    assert json.loads(payload)['ticker'] == ticker
    assert '원문 미검증' in output and '다른 설명' in output
    pytest.importorskip("typst")
    PdfReader = pytest.importorskip("pypdf").PdfReader
    report['prompt_url'] = 'https://example.test/prompt'
    pdf = fact_report._render(report)
    reader = PdfReader(io.BytesIO(pdf))
    uris = [str(a.get_object().get('/A', {}).get('/URI', '')) for p in reader.pages for a in p.get('/Annots', [])]
    assert 'https://example.test/prompt' in uris
    assert 'https://www.sec.gov/Archives/edgar/data/1/doc.htm' in uris


@pytest.mark.parametrize('mode', ['', '&mode=cached'])
def test_retired_endpoint_never_generates_or_fetches(monkeypatch, mode):
    import urllib.request
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: pytest.fail('network called'))
    h = object.__new__(stock_brief.handler)
    h.path = '/api/stock_brief?ticker=CAT' + mode
    h.wfile = io.BytesIO()
    statuses = []
    h._headers = statuses.append
    h.do_GET()
    assert statuses == [410]
    assert json.loads(h.wfile.getvalue())['brief'] is None
    assert ai_report.handler is fact_report.handler


def test_report_http_prompt_is_valid_and_legacy_pdf_uses_same_data(monkeypatch):
    pytest.importorskip("typst")
    ticker, docs, _ = fixture()
    monkeypatch.setattr(fact_report, '_fetch', lambda f: docs.get(f, {}))
    for entry, query, expected in [(fact_report, '&format=prompt', b'# AlphaNest'), (ai_report, '', b'%PDF')]:
        h = object.__new__(entry.handler)
        h.path = '/api/report?ticker=CAT' + query
        h.wfile = io.BytesIO()
        statuses = []
        h.send_response = statuses.append
        h.send_header = lambda *a: None
        h.end_headers = lambda: None
        h.do_GET()
        assert statuses == [200]
        assert h.wfile.getvalue().startswith(expected)
