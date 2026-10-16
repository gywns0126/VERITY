"""Dated issuer reviews must not become an evergreen or wrong-period narrative."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vercel-api' / 'api'))
from report_business import reviewed_kr_business
from report_kr_review import reviewed_financials
from report_reader import reader_financials
from report_evidence import build_report

NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)
STOCK = {'ticker': '084010', 'name': '대한제강', 'corp_code': '00113225',
         'financials': {'period': '2025'}, 'peer': {'sector': '철강', 'n': 164,
         'rows': [{'key': 'PER', 'value': '8', 'median': '12'}]}}


def reader():
    return reader_financials(reviewed_financials('084010', STOCK, [], NOW))


def test_half_year_cause_is_not_quarter_cause():
    entry = reviewed_kr_business('084010', STOCK, reader(), NOW)
    assert entry['company']['period_matches_current'] is False
    assert '반기 누적' in entry['company']['basis_label']
    assert '2분기' in entry['company']['note']
    assert len(entry['peers']) == 2
    assert entry['company']['topics'][0]['refs'] == []


def test_identity_expiry_and_newer_period_do_not_reuse_old_cause():
    assert reviewed_kr_business('084010', {**STOCK, 'name': '다른회사'}, reader(), NOW) is None
    assert reviewed_kr_business('084010', {**STOCK, 'corp_code': '00000000'}, reader(), NOW) is None
    assert reviewed_kr_business('084010', STOCK, reader(), datetime(2027, 5, 1)) is None
    assert reviewed_kr_business('084010', STOCK, reader(), datetime(2026, 10, 15)) is None
    newer = deepcopy(reader())
    newer['current']['end'] = '2026-09-30'
    assert reviewed_kr_business('084010', STOCK, newer, NOW) is None
    corrected = deepcopy(reader())
    for row in corrected['periods']:
        row['accession'] = '20260901000001'
    assert reviewed_kr_business('084010', STOCK, corrected, NOW) is None


def test_public_dossier_integrates_latest_income_cash_peers_and_review_notes():
    data = {'stock_report_public.json': {'stocks': {'084010': STOCK}}}
    report = build_report('084010', lambda name: data.get(name, {}), NOW)
    assert report['reader']['current']['start'] == '2026-04-01'
    assert report['reader']['current']['revenue'] == 387727240066
    assert report['reader']['current']['net'] is None
    assert report['reader']['cash']['start'] == '2026-01-01'
    assert report['reader']['cash']['ocf'] == -6818141298
    assert report['business_profile']['available']
    sections = {r['id']: r for r in report['sections']}
    assert len(sections['R4']['rows']) == 2
    assert '한국철강' in sections['R4']['rows'][0][0]
    assert '164개' in sections['R4G']['note']
    assert '직접 비교기업의 중앙값이 아닙니다' in sections['R4G']['note']
    assert len(sections['R2S']['rows']) == 3
    assert '1,184,170,129,020' in sections['RF']['note']
    assert any('단일 분기의 원인으로 전용하지 않음' in r['state'] for r in report['reading']['checklist'])
    assert not any(r['refs'] == 'R3 · R4' for r in report['issues'])


def test_legacy_cash_summary_does_not_mark_new_verified_cash_unusable():
    s = deepcopy(STOCK)
    s['financials']['groups'] = [{'title': '현금흐름표', 'rows': [{'k': '영업활동', 'v': '396억'}]}]
    data = {'stock_report_public.json': {'stocks': {'084010': s}}}
    report = build_report('084010', lambda name: data.get(name, {}), NOW)
    rows = next(r['rows'] for r in report['sections'] if r['id'] == 'DQ1')
    assert rows[0][0] == '결산 요약 영업현금흐름' and '보류' in rows[0][2]
    assert rows[1][0] == '본문 영업현금흐름' and '비교 가능' in rows[1][2]
