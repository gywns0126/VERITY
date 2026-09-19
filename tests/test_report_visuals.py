"""Financial chart safety: comparable periods, missing data and negative values."""
import io
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vercel-api' / 'api'))
from report_reader import reader_financials
from report_visuals import chart_svg


def period(year, **overrides):
    row = dict(year=year, start=f'{year}-01-01', end=f'{year}-12-31', period_kind='annual',
               currency='USD', fs_div='ENTITY', source_url=f'https://www.sec.gov/Archives/{year}.htm',
               revenue=100, op=20, net=15)
    row.update(overrides)
    return row


def visuals(rows, financial=False):
    return reader_financials(rows, financial)['visuals']


def test_graphs_exclude_missing_period_provenance_and_currency_mismatch():
    for key in ('start', 'end', 'currency', 'fs_div', 'source_url'):
        rows = [period(2024), period(2025)]
        for row in rows:
            del row[key]
        assert visuals(rows)['charts'] == {}
    assert visuals([period(2024), period(2025, currency='CAD')])['charts'] == {}
    assert visuals([period(2024), period(2025, fs_div='OFS')])['charts'] == {}


def test_annual_gap_is_not_connected_or_described_as_a_trend():
    v = visuals([period(2022), period(2024), period(2025)])
    assert [s['end'] for s in v['charts']['annual']['sources']] == ['2024-12-31', '2025-12-31']
    assert 'annual' not in visuals([period(2023), period(2025)])['charts']


def test_quarter_profit_is_not_compared_with_ytd_cash():
    cash = period(2026, end='2026-06-30', period_kind='ytd', net=40, ocf=35, capex=5)
    quarter = period(2026, start='2026-04-01', end='2026-06-30', period_kind='quarter', net=999)
    v = visuals([cash, quarter])
    assert v['charts']['cash']['rows'][0]['value'] == 40
    assert '$40.00' in v['insights']['cash']['evidence'] and '999' not in v['insights']['cash']['evidence']
    assert v['charts']['cash']['sources'][0]['period_kind'] == 'ytd'


def test_missing_is_not_zero_and_capex_absence_prevents_residual():
    v = visuals([period(2025, net=None, ocf=30, capex=None)])
    c = v['charts']['cash']
    assert c['rows'][0]['value'] is None
    assert len(c['rows']) == 2
    assert '미수신' in chart_svg(c)
    assert 'cash' not in v['insights']
    assert len(visuals([period(2025, ocf=30, capex=0)])['charts']['cash']['rows']) == 4


def test_bank_has_no_industrial_margin_or_cash_quality_interpretation():
    v = visuals([period(2024, ocf=10, capex=2), period(2025, ocf=40, capex=4)], True)
    assert set(v['charts']) == {'annual'}
    assert v['charts']['annual']['panels'][1]['title'] == '순이익'
    assert v['insights'] == {}


@pytest.mark.parametrize('old,new,title', [
    (-10, 5, '흑자로 전환'), (5, -10, '적자로 전환'), (-10, -5, '손실이 줄'),
    (-5, -10, '손실이 늘'),
])
def test_negative_profit_uses_profit_loss_language(old, new, title):
    v = visuals([period(2024, op=old), period(2025, op=new)])
    assert title in v['insights']['income']['title']
    for chart in v['charts'].values():
        svg = chart_svg(chart)
        root = ET.fromstring(svg)
        assert 'NaN' not in svg and 'Infinity' not in svg
        for rect in root.iter('{http://www.w3.org/2000/svg}rect'):
            assert float(rect.attrib['height']) >= 0 and float(rect.attrib['width']) >= 0


def test_revenue_up_profit_down_is_not_described_as_quality_growth():
    v = visuals([period(2024), period(2025, revenue=120, op=15)])
    assert '이어지지 않았습니다' in v['insights']['income']['title']
    assert '원인' not in v['insights']['income']['meaning'] or '확인' in v['insights']['income']['meaning']


def test_recent_quarter_and_annual_direction_are_compared_separately():
    rows = [period(2024), period(2025, op=15),
            period(2025, start='2025-04-01', end='2025-06-30', period_kind='quarter', op=10),
            period(2026, start='2026-04-01', end='2026-06-30', period_kind='quarter', op=20)]
    v = visuals(rows)
    assert '방향이 달라졌습니다' in v['insights']['annual']['title']
    assert '-5.0%p' in v['insights']['annual']['evidence']
    assert '+10.0%p' in v['insights']['annual']['evidence']
    assert '장기 추세 전환을 확정할 수 없습니다' in v['insights']['annual']['limit']


def test_all_zero_and_extreme_values_render_finite_zero_based_bars():
    for value in (0, -1e18, 1e18):
        v = visuals([period(2024, op=value), period(2025, op=value, ocf=value, capex=0)])
        for chart in v['charts'].values():
            ET.fromstring(chart_svg(chart))
            assert 'nan' not in chart_svg(chart).lower()


def test_svg_text_is_escaped_and_export_keeps_numbers_not_markup():
    v = visuals([period(2024), period(2025)])
    c = v['charts']['annual']
    c['panels'][0]['rows'][0]['label'] = '<script>&'
    svg = chart_svg(c)
    ET.fromstring(svg)
    assert '&lt;script&gt;&amp;' in svg
    assert '<svg' not in json.dumps(v)


def test_pdf_has_chart_labels_and_interpretation_with_clickable_sources():
    pytest.importorskip('typst')
    from pypdf import PdfReader
    import fact_report
    from report_evidence import build_report, analysis_prompt
    rows = [period(2024), period(2025, revenue=120, op=30, ocf=25, capex=5)]
    stock = {'ticker': 'CAT', 'name': '검증 기업', 'financial_evidence': {'periods': rows}}
    d = build_report('CAT', lambda name: {'stocks': {'CAT': stock}} if name == 'us_stock_report_public.json' else {})
    pdf = PdfReader(io.BytesIO(fact_report._render(d)))
    text = '\n'.join(p.extract_text() for p in pdf.pages)
    assert '최근 연간 실적 흐름' in text and '영업현금 유입이 순이익 이상' in text
    assert '매출 성장에 수익성 개선' in text
    links = [str(a.get_object().get('/A', {}).get('/URI', '')) for p in pdf.pages for a in p.get('/Annots', [])]
    assert rows[-1]['source_url'] in links
    assert '<svg' not in analysis_prompt(d)
    assert 'chart_images' not in d


def test_missing_operating_profit_uses_explicit_net_panel_without_substitution():
    v = visuals([period(2024, op=None, net=10), period(2025, op=None, net=12)])
    assert v['charts']['annual']['panels'][1]['title'] == '순이익'
    assert [r['value'] for r in v['charts']['annual']['panels'][1]['rows']] == [10, 12]
    assert 'margin' not in v['charts'] and 'income' not in v['insights']
