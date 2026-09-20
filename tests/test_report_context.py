"""Regression cases for period/currency truthfulness and non-causal explanations."""
import json
import math
import sys
from pathlib import Path

import pytest

API = Path(__file__).resolve().parents[1] / 'vercel-api' / 'api'
sys.path.insert(0, str(API))
from report_context import compare_annual, format_money
from report_evidence import build_report, analysis_prompt


def annual():
    return [dict(year=y, revenue=r, op=o, net=n, currency='USD', fs_div='CFS',
                 start=f'{y}-01-01', end=f'{y}-12-31', period_kind='annual',
                 source_url=f'https://www.sec.gov/Archives/example-{y}.htm')
            for y, r, o, n in [(2024, 100, 30, 20), (2025, 120, 20, 15)]]


def dossier(rows=None, kr=False, extra=None, stock_extra=None):
    ticker = '005930' if kr else 'CAT'
    row = {'ticker': ticker, 'fin_series': rows if rows is not None else annual(),
           'financials': {'period': '2025'}, 'business': '기계'}
    row.update(stock_extra or {})
    docs = {'stock_report_public.json' if kr else 'us_stock_report_public.json': {'stocks': {ticker: row}}}
    docs.update(extra or {})
    return build_report(ticker, lambda name: docs.get(name, {}))


def test_foreign_currency_not_relabeled_as_dollars_in_pdf_input_or_prompt():
    rows = annual()
    for r in rows:
        r['currency'] = 'JPY'
    report = dossier(rows, stock_extra={'financials': {'period': '2025', 'currency': 'JPY'}})
    assert report['comparison']['currency'] == 'JPY'
    assert 'JPY 100.00' in analysis_prompt(report)
    assert '$100.00' not in analysis_prompt(report)
    r1 = next(s for s in report['sections'] if s['id'] == 'R1')
    assert all(r[1].startswith('JPY ') for r in r1['rows'])
    assert '보고 통화 필드' in analysis_prompt(report)


@pytest.mark.parametrize('key,value,reason', [
    ('currency', 'CAD', '보고 통화'), ('fs_div', 'OFS', '연결·별도'),
    ('period_kind', 'reported_quarter', '다른 기간'), ('year', 2024, '중복'),
])
def test_incompatible_basis_never_produces_growth_or_bridge(key, value, reason):
    rows = annual()
    for r in rows:
        r.update(currency='USD', fs_div='CFS')
    rows[1][key] = value
    report = dossier(rows)
    c = report['comparison']
    assert not c['usable'] and c['bridge'] is None and not c['changes']
    assert reason in c['reason']
    assert not any(s['id'] == 'R5' for s in report['sections'])
    assert report['summary'][1]['title'] == '최근 실적 비교는 보류합니다'


@pytest.mark.parametrize('end', ['2025-03-31', 'invalid', '2024-12-31'])
def test_partial_overlapping_or_invalid_dates_do_not_pass_as_annual(end):
    rows = annual()
    rows[0].update(start='2024-01-01', end='2024-12-31')
    rows[1].update(start='2025-01-01', end=end)
    assert not compare_annual(rows, {}, False)['usable']


def test_bridge_reconciles_and_is_not_claimed_as_price_or_volume_cause():
    c = compare_annual(annual(), {}, False)
    b = c['bridge']
    assert math.isclose(b['revenue_effect'], 6)
    assert math.isclose(b['margin_effect'], -16)
    assert math.isclose(b['revenue_effect'] + b['margin_effect'], -10)
    assert math.isclose(b['operating_change'], -10)
    d = dossier()
    text = analysis_prompt(d)
    assert '인과관계를 증명하지' in text
    assert '연결 연간 비교' in text
    assert d['annual_basis'][0]['scope'] == '연결'
    assert d['annual_basis'][0]['source_url'].startswith('https://www.sec.gov/')


def test_zero_or_negative_revenue_does_not_create_margin_bridge():
    for v in [0, -10, None]:
        rows = annual()
        rows[0]['revenue'] = v
        assert compare_annual(rows, {}, False)['bridge'] is None


def test_business_quote_retains_source_date_and_no_donor_company_fallback():
    quote = '당사는 반도체를 생산하고 판매합니다. ' * 15
    rec = {'text': quote, 'fiscal_year': '2025', 'filed_at': '20260310', 'report': '사업보고서',
           'url': 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260310002820', 'truncated': True}
    docs = {'kr_business_overview_public.json': {'rows': {'005930': rec, '000660': {'text': '다른 기업'}}}}
    d = dossier(kr=True, extra=docs)
    profile = d['business_profile']
    assert profile['available'] and profile['text'] == quote.strip()
    assert profile['filed_at'] == '20260310'
    assert profile['source']['url'] == rec['url']
    assert len(profile['summary']) <= 222
    assert len(d['summary']) == 3 and '다른 기업' not in analysis_prompt(d)
    assert next(c for c in d['coverage'] if c['id']=='B')['status'] == '수신'
    assert len(d['coverage']) == 11


@pytest.mark.parametrize('url', ['', 'javascript:alert(1)', 'https://dart.fss.or.kr/'])
def test_uncited_business_text_is_not_promoted_to_source_quote(url):
    rec = {'text': '회사 설명', 'url': url}
    d = dossier(kr=True, extra={'kr_business_overview_public.json': {'rows': {'005930': rec}}})
    assert not d['business_profile']['available']
    assert '제품·사업부 설명 원문' in d['summary'][0]['observation']


def test_metric_calculation_provenance_and_row_source_survive_export():
    rows = annual()
    rows[-1].update(fs_div='CFS', currency='KRW', source_url='https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260310002820')
    calc = '시가총액 100 ÷ 순이익 10 (2025년 연간 · 연결 · 시총 2026-09-18)'
    d = dossier(rows, kr=True, stock_extra={'facts': {'PER': '10'}, 'facts_note': {'PER': '자체계산'}, 'facts_calc': {'PER': calc}})
    r3 = next(s for s in d['sections'] if s['id']=='R3')
    assert calc in r3['rows'][0][2]
    assert d['annual_basis'][-1]['source_url'] == rows[-1]['source_url']
    assert '2026-09-18' in analysis_prompt(d)


def test_product_paragraph_precedes_organization_boilerplate_without_rewriting():
    intro = '당사는 해외 생산 판매법인 10개로 구성됩니다.'
    products = '사업별로 보면 반도체와 디스플레이 제품을 생산합니다.'
    d = dossier(kr=True, extra={'kr_business_overview_public.json': {'rows': {'005930': {
        'text': intro + '\n\n' + products, 'url': 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260310002820'
    }}}})
    assert d['summary'][0]['observation'] == products
    assert intro in d['business_profile']['text']


def test_finite_currency_formatting_does_not_accept_bools_or_html():
    assert format_money(float('nan')) == '—'
    assert format_money(True) == '—'
    assert '통화 미상' in format_money(12, '<JPY>')
    assert format_money(1_000_000, 'CAD') == 'CAD 1.00M'
