"""Public report consumes normalized metrics, never fabricated peer figures."""
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vercel-api' / 'api'))
from report_evidence import build_report, analysis_prompt


def stock(ticker, currency='KRW', end='2026-06-30'):
    url = 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814000123'
    row = dict(year=2026, start='2026-04-01', end=end, period_kind='quarter',
               currency=currency, fs_div='CFS', source_url=url, filed='2026-08-14',
               revenue=100, op=10, net=8, metric_sources={})
    for key in ('revenue', 'op', 'net'):
        row['metric_sources'][key] = dict(name=key, start=row['start'], end=end,
                                         currency=currency, source_url=url)
    return dict(ticker=ticker, name='합성 검수 ' + ticker, gics_ko='검수 업종',
                financial_evidence={'periods': [row]})


def test_arbitrary_issuers_use_same_pipeline_and_prompt_contract():
    stocks = [stock('123456'), stock('234567'), stock('345678', 'USD')]
    docs = {'stock_report_public.json': {'stocks': stocks}}
    report = build_report('123456', lambda n: docs.get(n, {}), datetime(2026, 10, 17, tzinfo=timezone.utc))
    comparison = report['peer_comparison']
    assert comparison['qualified'] == 1 and comparison['held'] == 1
    qualified = comparison['rows'][0]
    assert qualified['metrics']['op_margin']['value'] == 10
    assert qualified['accounting_standard_comparability'] == 'basis_unknown'
    assert not qualified['ranking_allowed']
    sections = {s['id']: s for s in report['sections']}
    assert sections['R4N']['total'] == 2  # target plus aligned peer, not currency-mismatched peer
    assert sections['R4H']['total'] == 2
    assert report['attribution']['status'] == 'unavailable'
    prompt = analysis_prompt(report)
    assert 'peer_comparison' in prompt and 'attribution' in prompt
    assert '미설명 잔여분' in prompt


def test_reviewed_peer_quarters_are_used_without_erasing_scope_difference():
    stocks = [{'ticker': '084010', 'name': '대한제강'},
              {'ticker': '104700', 'name': '한국철강', 'gics_ko': '철강'},
              {'ticker': '460860', 'name': '동국제강', 'gics_ko': '철강'}]
    docs = {'stock_report_public.json': {'stocks': stocks}}
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    fetch = lambda n: docs.get(n, {})
    daehan = build_report('084010', fetch, now)
    assert daehan['peer_comparison']['qualified'] == 0
    for row in daehan['peer_comparison']['rows']:
        assert 'fs_div_mismatch' in row['reasons']
        assert 'missing_financial_evidence' not in row['reasons']
        assert 'no_sourced_income' not in row['reasons']
        assert 'kr_review_applied' not in row['reasons']
        assert row['enrichment'] == 'kr_review_applied'
        assert any(p['start'] == '2026-04-01' and p['end'] == '2026-06-30' for p in row['available_periods'])
    section = next(s for s in daehan['sections'] if s['id'] == 'R4H')
    for row in section['rows']:
        assert '2026-04-01' in row[3]['text'] and '별도' in row[3]['text']
        assert 'rcpNo=2026081400' in row[3]['url']
    korean = build_report('104700', fetch, now)
    assert korean['reader']['current']['end'] == '2026-06-30'
    assert korean['reader']['current']['fs_div'] == 'OFS'
    assert korean['peer_comparison']['qualified'] == 1
    peer = korean['peer_comparison']['rows'][0]
    assert peer['ticker'] == '460860' and peer['metrics']['net']['value'] == 11645015990
    assert not peer['ranking_allowed']


def test_held_exact_period_keeps_source_but_future_or_stale_period_does_not():
    target, peer = stock('123456'), stock('234567')
    target['financial_evidence']['periods'][0]['accounting_standard'] = 'K-IFRS'
    period = peer['financial_evidence']['periods'][0]
    period['accounting_standard'] = 'US-GAAP'
    docs = {'stock_report_public.json': {'stocks': [target, peer]}}
    fetch = lambda n: docs.get(n, {})
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    result = build_report('123456', fetch, now)
    assert 'accounting_standard_mismatch' in result['peer_comparison']['rows'][0]['reasons']
    last = lambda r: next(s for s in r['sections'] if s['id'] == 'R4H')['rows'][0][3]
    assert last(result)['url'] == period['source_url']
    period['filed'] = '2027-01-01'
    assert last(build_report('123456', fetch, now)) == '기간·원문 미연결'
    period['filed'] = '2026-08-14'
    assert last(build_report('123456', fetch, datetime(2027, 10, 17, tzinfo=timezone.utc))) == '기간·원문 미연결'
