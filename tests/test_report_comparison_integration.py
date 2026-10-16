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
