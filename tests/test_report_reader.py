import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vercel-api' / 'api'))
from report_context import compare_annual
from report_reader import reader_financials
from report_business import filing_business


def period(year=2025, **kwargs):
    return dict(year=year, start=f'{year}-01-01', end=f'{year}-12-31', period_kind='annual',
                currency='CAD', fs_div='CFS', source_url='https://www.sec.gov/Archives/example.htm',
                filed=f'{year+1}-02-01', revenue=100, op=20, net=15, **kwargs)


def test_missing_scope_source_dates_withholds_annual_growth():
    for key in ('fs_div', 'source_url', 'start', 'end', 'currency'):
        rows = [period(2024), period(2025)]
        for row in rows:
            row.pop(key)
        assert not compare_annual(rows, {}, False)['usable']


def test_mixed_quarter_and_ytd_never_compare_or_join_cash():
    ytd = period(2025, ocf=50, capex=10)
    ytd.update(end='2025-06-30', period_kind='ytd')
    quarter = period(2026)
    quarter.update(start='2026-04-01', end='2026-06-30', period_kind='quarter')
    r = reader_financials([ytd, quarter])
    assert r['current'] == quarter and r['prior'] is None
    assert r['cash'] == ytd and r['cash_rows'][-1][1] == 'CAD 40.00'
    assert any('이전 자료' in s for s in r['cash_notes'])


def test_missing_capex_not_zero_and_financial_fcf_not_applicable():
    row = period(ocf=60)
    r = reader_financials([row])
    assert len(r['cash_rows']) == 3
    assert any('누락을 0' in s for s in r['cash_notes'])
    row['capex'] = 0
    assert reader_financials([row])['cash_rows'][-1][1] == 'CAD 60.00'
    r = reader_financials([row], is_financial=True)
    assert len(r['cash_rows']) == 3 and any('금융업' in s for s in r['cash_notes'])


def test_zero_negative_and_unknown_income_do_not_invent_ratios():
    a, b = period(2024), period(2025)
    a.update(revenue=0, op=-20, net=None)
    r = reader_financials([a, b])
    assert [row[-1] for row in r['rows']] == ['미산출'] * 3


def test_sec_business_is_contiguous_quote_not_segment_allocation():
    f = {'accession': '0000018230-26-000046', 'primary_document': 'cat.htm', 'form': '10-Q',
         'filing_date': '2026-08-05', 'report_date': '2026-06-30'}
    quote = 'We have four reportable segments. This business description explains the equipment and financial services provided to customers.'
    r = filing_business('<ix:header>secret</ix:header><div>Description of segments</div><p>'+quote+'</p>', f, '18230')
    assert quote in r['text'] and 'secret' not in r['text']
    assert r['truncated'] and r['filed_at'] == '2026-08-05'
    assert r['url'].endswith('/cat.htm')
    assert filing_business('<div>no matching business section</div>', f, '18230') == {}
