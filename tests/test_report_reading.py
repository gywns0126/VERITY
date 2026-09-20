"""Reader additions must retain identity, periods, counter-evidence and omissions."""
from datetime import datetime
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vercel-api' / 'api'))
from report_business import company_explanation, reviewed_overview
from report_reader import reader_financials
from report_reading import reading_guide
from report_visuals import chart_svg

FILING = {'accession': '0000018230-26-000046', 'primary_document': 'cat.htm', 'report_date': '2026-06-30'}
QUOTE = ('Total sales and revenues for the second quarter of 2026 increased 10 percent compared with the second quarter of 2025. '
         'The increase was due to higher sales volume, partially offset by unfavorable price realization.')


def period(year=2026, **kw):
    return dict(year=year, start=f'{year}-04-01', end=f'{year}-06-30', period_kind='quarter', currency='USD',
                fs_div='ENTITY', source_url='https://www.sec.gov/Archives/edgar/data/18230/000001823026000046/cat.htm',
                accession=FILING['accession'], revenue=120, op=30, net=20, **kw)


def document(*paragraphs):
    return '<div>Item 2. Management’s Discussion and Analysis of Financial Condition and Results of Operations</div>' + ''.join('<p>'+p+'</p>' for p in paragraphs)


def test_company_quote_is_current_complete_and_keeps_offset():
    data = company_explanation(document(QUOTE), FILING, '18230', period())
    assert data['excerpts'][0]['quote'] == QUOTE
    assert data['excerpts'][0]['period'] == '2026-04-01 ~ 2026-06-30'
    assert data['topics'][0]['refs'] == ['M1']
    assert data['topics'][2]['refs'] == []
    assert data['source']['url'].endswith('/cat.htm')


@pytest.mark.parametrize('quote', [
    QUOTE.replace('second quarter of 2026', 'six months ended June 30, 2026'),
    QUOTE.replace('second quarter of 2026', 'second quarter of 2025'),
    QUOTE.replace('increased 10 percent', 'will increase 10 percent'),
    QUOTE.replace('Total sales and revenues', 'Construction Industries sales'),
    QUOTE.replace('for the second quarter of 2026 ', ''),
])
def test_no_ytd_old_forecast_segment_or_undated_cause(quote):
    assert not company_explanation(document(quote), FILING, '18230', period())['excerpts']


def test_cause_needs_actual_mda_and_same_filing():
    assert not company_explanation('<p>'+QUOTE+'</p>', FILING, '18230', period())['excerpts']
    row = period(); row['accession'] = 'different'
    assert not company_explanation(document(QUOTE), FILING, '18230', row)['excerpts']
    row = period(); row['end'] = '2026-09-30'
    assert not company_explanation(document(QUOTE), FILING, '18230', row)['excerpts']
    assert not company_explanation(document('Item 3. Risk Factors', QUOTE), FILING, '18230', period())['excerpts']


def test_reviewed_business_requires_entity_and_review_age():
    today = datetime(2026, 9, 20)
    assert reviewed_overview('CAT', '0000018230', today)['rows']
    assert reviewed_overview('CAT', '49938', today) is None
    assert reviewed_overview('IMO', '', today) is None
    assert reviewed_overview('CAT', '18230', datetime(2027, 9, 20)) is None
    assert reviewed_overview('CAT', '18230', datetime(2026, 9, 19)) is None


def test_summary_prioritizes_newer_unusable_feed_and_checklist_has_baseline():
    reader = reader_financials([period(2025), period(2026, ocf=25)])
    reader['observations'].append('분기 피드 2026-09-30은 근거 부족으로 본문 수치에서 제외했습니다.')
    company = company_explanation(None, {}, '', reader['current'])
    r = reading_guide(reader, company, [], [])
    assert len(r['cards']) == 3
    assert '2026-09-30' in r['cards'][2]['detail']
    assert '2026-04-01' in r['checklist'][0]['state']
    assert '전년 동기' in r['checklist'][0]['next']
    assert '미확보' in r['checklist'][3]['state']
    assert '0' not in r['cards'][2]['title']


def test_positive_income_does_not_hide_negative_cash():
    reader = reader_financials([period(2025), period(2026, ocf=-10)])
    r = reading_guide(reader, company_explanation(None, {}, '', reader['current']), [], [])
    assert '현금이 유출' in r['cards'][1]['title']
    assert r['cards'][1]['sources'][0]['ocf'] == -10


@pytest.mark.parametrize('old_op,new_op', [(20,30),(30,10),(-20,10),(-20,-30),(0,0)])
def test_waterfall_reconciles_and_negative_rectangles_are_valid(old_op,new_op):
    a,b = period(2025), period(2026)
    a.update(revenue=100, op=old_op); b.update(op=new_op)
    reader = reader_financials([a,b])
    chart = reader['visuals']['charts']['bridge']; rows = chart['rows']
    assert rows[0]['value'] + rows[1]['value'] + rows[2]['value'] == pytest.approx(rows[3]['value'])
    for l,r in zip(rows[:2],rows[1:3]):
        assert l['to'] == r['from']
    root = ET.fromstring(chart_svg(chart))
    assert all(float(r.attrib['height']) >= 0 for r in root.iter('{http://www.w3.org/2000/svg}rect'))
    assert '<svg' not in json.dumps(reader)
    assert '실제 기여액을 뜻하지' in chart['note']
    assert 'bridge' not in reader_financials([a,b], is_financial=True)['visuals']['charts']


def test_financial_checklist_does_not_treat_missing_capex_as_industrial_gap():
    reader = reader_financials([period(2025), period(2026, ocf=25)], is_financial=True)
    r = reading_guide(reader, company_explanation(None, {}, '', reader['current']), [], [], True)
    assert '취득 지출' not in r['cards'][2]['detail']
    assert '금융업' in r['checklist'][2]['next']
    assert '영업이익률' not in r['checklist'][1]['state']
