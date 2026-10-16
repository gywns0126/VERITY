from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vercel-api' / 'api'))
from report_attribution import monetary_attribution
from report_business import company_explanation
from report_reader import reader_financials


FILING = {'accession': '0000018230-26-000046', 'primary_document': 'cat-20260630.htm', 'report_date': '2026-06-30'}
URL = 'https://www.sec.gov/Archives/edgar/data/18230/000001823026000046/cat-20260630.htm'
# Contiguous public filing paragraph; source and period are retained in the fixture.
QUOTE = ('Total sales and revenues for the second quarter of 2026 were $20.543 billion, an increase of $3.974 billion, or 24 percent, compared with $16.569 billion in the second quarter of 2025. '
         'The increase was primarily due to higher sales volume of $3.1 billion and favorable price realization of $595 million.')


def inputs(quote=QUOTE):
    periods = [dict(year=y, start=f'{y}-04-01', end=f'{y}-06-30', period_kind='quarter', currency='USD', fs_div='ENTITY',
                    accession=FILING['accession'], source_url=URL, revenue=v, op=op)
               for y, v, op in [(2025, 16569000000, 2860000000), (2026, 20543000000, 4295000000)]]
    reader = reader_financials(periods)
    doc = '<div>Item 2. Management’s Discussion</div><p>' + quote + '</p>'
    company = company_explanation(doc, FILING, '18230', reader['current'])
    return reader, company


def test_actual_cat_revenue_contributions_keep_residual_and_metric():
    reader, company = inputs()
    result = monetary_attribution(reader, company)
    group = result['groups'][0]
    assert group['metric'] == 'revenue'
    assert [r['amount'] for r in group['rows']] == [3100000000, 595000000]
    assert group['change'] == 3974000000
    assert group['residual'] == 279000000
    assert group['rounding_bound'] == 50500000
    assert group['quote'] == QUOTE and group['source_url'] == URL
    assert '영업이익' in result['note']


@pytest.mark.parametrize('suffix', [
    'higher sales volume.',
    'higher sales volume of 10 percent.',
    'not higher sales volume of $300 million.',
    'higher sales volume of $300 million to $400 million.',
    'higher sales volume of $300 million and higher sales volume of $200 million.',
    'higher sales volume of $300 million before tax.',
    'higher sales volume of $300 million in the construction segment.',
    'approximately higher sales volume of $300 million.',
])
def test_does_not_promote_qualitative_percentage_range_or_ambiguous_values(suffix):
    r, c = inputs('Total sales and revenues for the second quarter of 2026 increased $3.974 billion. The increase was due to ' + suffix)
    assert monetary_attribution(r, c)['groups'] == []


def test_negative_cost_and_currency_impacts_keep_sign():
    r, c = inputs('Operating profit for the second quarter of 2026 increased. The increase was due to favorable price realization of $300 million, partially offset by higher manufacturing costs of $149 million and unfavorable currency impacts of $5 million.')
    group = monetary_attribution(r, c)['groups'][0]
    assert group['metric'] == 'op'
    assert [x['amount'] for x in group['rows']] == [300000000, -149000000, -5000000]


@pytest.mark.parametrize('change', ['period','accession','currency','financial','prior'])
def test_scope_guards(change):
    r,c=inputs()
    if change=='period': c['period_matches_current']=False
    if change=='accession': c['source']['url']=URL.replace('000001823026000046','000001823026000047')
    if change=='currency': r['current']['currency']=r['prior']['currency']='CAD'
    if change=='prior': r['prior']=None
    assert monetary_attribution(r,c,change=='financial')['groups']==[]


def test_does_not_mutate_shared_inputs():
    r,c=inputs(); before=deepcopy((r,c))
    monetary_attribution(r,c)
    assert (r,c)==before


def test_annual_mda_uses_item7_not_item2_and_stops_at_item8():
    r, _ = inputs()
    current = {**r['current'], 'start': '2026-01-01', 'end': '2026-12-31', 'period_kind': 'annual'}
    filing = {**FILING, 'report_date': '2026-12-31', 'form': '10-K'}
    quote = 'Total sales for the year ended December 31, 2026 increased due to higher sales volume of $300 million.'
    document = '<div>Item 7. Management’s Discussion</div><p>' + quote + '</p><div>Item 8. Financial Statements</div>'
    result = company_explanation(document, filing, '18230', current)
    assert result['excerpts'][0]['quote'] == quote
    assert company_explanation(document.replace('Item 7.', 'Item 2.'), filing, '18230', current)['excerpts'] == []


@pytest.mark.parametrize('quote', [
    'Operating profit for the Construction Industries segment for the second quarter of 2026 increased. The increase was due to higher sales volume of $300 million.',
    'Net sales in North America for the second quarter of 2026 increased. The increase was due to higher sales volume of $300 million.',
    'Total sales and revenues for the second quarter of 2026 increased compared with 2025. In the second quarter of 2025, the decrease was due to lower sales volume of $300 million.',
    'Total sales and revenues for the second quarter of 2026 increased. The increase was not due to higher sales volume of $300 million.',
    'Total sales and revenues for the second quarter of 2026 increased. The prior year increase was due to higher sales volume of $300 million.',
])
def test_causal_sentence_keeps_entity_period_and_negation(quote):
    reader, company = inputs(quote)
    assert company['excerpts'] == []
    assert monetary_attribution(reader, company)['groups'] == []
