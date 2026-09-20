"""Readable direction must preserve loss transitions and absent comparisons."""
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vercel-api' / 'api'))
from report_reader import change_display, reader_financials


def period(year, **overrides):
    row = dict(year=year, start=f'{year}-01-01', end=f'{year}-12-31', period_kind='annual',
               currency='USD', fs_div='ENTITY', source_url=f'https://www.sec.gov/Archives/{year}.htm',
               revenue=100, op=20, net=15)
    return {**row, **overrides}


@pytest.mark.parametrize('old,new,profit,direction,label', [
    (100, 124, False, 'up', '+24.0%'), (100, 80, False, 'down', '−20.0%'),
    (0, 0, False, 'flat', '변동 없음'), (None, 0, False, 'unknown', '비교 불가'),
    (0, 5, True, 'up', '0 기준'), (-10, 5, True, 'up', '흑자 전환'),
    (10, -5, True, 'down', '적자 전환'), (-10, -5, True, 'up', '손실 축소'),
    (-5, -10, True, 'down', '손실 확대'), (100, 100.001, False, 'up', '<0.1%'),
    (100, 99.999, False, 'down', '<0.1%'),
])
def test_change_direction_and_exceptions(old, new, profit, direction, label):
    d = change_display(old, new, profit)
    assert d['direction'] == direction and label in d['label']


def test_mismatched_currency_never_produces_direction():
    d = reader_financials([period(2024), period(2025, currency='CAD')])
    assert all(m['change'] == {'direction': 'unknown', 'label': '비교 불가'} for m in d['metrics'])


def test_pdf_arrows_financial_transition_and_chart_takeaway():
    pytest.importorskip('typst')
    from pypdf import PdfReader
    from fact_report import _render
    from report_evidence import build_report
    stock = {'ticker': 'CAT', 'financial_evidence': {'periods': [period(2024, op=-5), period(2025, revenue=124, op=10)]}}
    d = build_report('CAT', lambda n: {'stocks': {'CAT': stock}} if n == 'us_stock_report_public.json' else {})
    pdf = PdfReader(io.BytesIO(_render(d)))
    text = '\n'.join(p.extract_text() for p in pdf.pages)
    assert '↑' in text and '+24.0%' in text and '흑자 전환' in text
    assert d['reader']['visuals']['charts']['bridge']['takeaway'] in text
