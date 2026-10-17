"""Legacy received values must not disappear or become verified operands."""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'vercel-api' / 'api'))
from report_integrity import cash_receipt, financial_display, valuation_display
from report_evidence import build_report


def test_zero_sga_with_conflicting_display_totals_is_flagged_not_replaced():
    fin = {'groups': [{'title': '손익계산서', 'rows': [
        {'k': '매출총이익', 'v': '702억'}, {'k': '영업이익', 'v': '−29억'},
        {'k': '판매비와관리비', 'v': '0'}]}]}
    before = copy.deepcopy(fin)
    result, warnings = financial_display(fin)
    row = result['groups'][0]['rows'][-1]
    assert row['status'] == 'inconsistent' and row['received_value'] == '0'
    assert '확인 필요' in row['v'] and '731' not in row['v']
    assert warnings and fin == before
    fin['groups'][0]['rows'][1]['v'] = '702억'
    result, warnings = financial_display(fin)
    row = result['groups'][0]['rows'][-1]
    assert row['status'] == 'unverified_zero' and row['received_value'] == '0'
    assert '확인 필요' in row['v'] and warnings


def test_legacy_zero_sga_without_status_or_other_totals_is_not_verified():
    for zero in ('0', '0원', '0억', 0, 0.0):
        fin = {'groups': [{'title': '손익계산서', 'rows': [{'k': '판매비와관리비', 'v': zero}]}]}
        before = copy.deepcopy(fin)
        result, warnings = financial_display(fin)
        row = result['groups'][0]['rows'][0]
        assert row['status'] == 'unverified_zero' and row['received_value'] == zero
        assert '확인 필요' in row['v'] and warnings and fin == before
    for value in ('2억', '—', None):
        fin = {'groups': [{'title': '손익계산서', 'rows': [{'k': '판매비와관리비', 'v': value}]}]}
        result, warnings = financial_display(fin)
        assert result == fin and not warnings


def test_cash_summary_is_received_without_becoming_an_arithmetic_input():
    fin = {'period': '2025', 'groups': [{'title': '현금흐름표', 'rows': [{'k': '영업활동', 'v': '396억'}]}]}
    state = cash_receipt(fin, {'cash': None})
    assert state['received'] and state['received_value'] == '396억'
    assert not state['analysis_usable'] and not state['calculation_ready']
    assert not state['primary_value_verified'] and '396억' in state['note']
    assert not cash_receipt({}, {'cash': None})['received']


def test_estimate_value_and_original_formula_are_both_preserved():
    original = {'PBR': '0.4', 'BPS': '27,066원', 'PER': '25'}
    calculations = {k: '총자산 ÷ (1 + 부채비율 / 100)' for k in ('PBR', 'BPS')}
    values, calc, warnings = valuation_display(original, {}, calculations)
    assert values['PBR'] == '추정 0.4' and values['PER'] == '25'
    assert '지배기업 소유주지분' in calc['PBR'] and '자기주식' in calc['BPS']
    assert original['PBR'] == '0.4' and len(warnings) == 2
    assert valuation_display({'PBR': '1'}, {}, {'PBR': '직접 자기자본 기준'})[0]['PBR'] == '1'


def test_generic_calculated_per_keeps_received_number_but_holds_comparison():
    cases = (
        ('064550', '120.2', '시가총액 2052억 ÷ 순이익 17억 (2025년 연간 · 시총 2026-10-16 기준)'),
        ('000370', '2.6', '시가총액 7646억 ÷ 순이익 2923억 (2025년 연간 · 시총 2026-10-16 기준)'),
        ('005880', '3.8', '시가총액 6600억 ÷ 순이익 1733억 (2025년 연간 · 시총 2026-10-16 기준)'),
    )
    for ticker, received, formula in cases:
        facts, notes, calculations = {'PER': received}, {'PER': '자체계산'}, {'PER': formula}
        before = copy.deepcopy((facts, notes, calculations))
        values, descriptions, warnings = valuation_display(facts, notes, calculations)
        assert values['PER'] == '비교 보류 · 수집값 ' + received, ticker
        assert descriptions['PER'].startswith(formula), ticker
        assert '귀속 기준' in descriptions['PER'] and '보통주 EPS 정합 미검수' in descriptions['PER']
        assert '총당기순이익' not in descriptions['PER']
        assert len(warnings) == 1 and '비교를 보류' in warnings[0]
        assert (facts, notes, calculations) == before


def test_per_without_generic_calculated_formula_is_not_auto_qualified():
    for note, formula in (
        ('외부 수신', ''),
        ('자체계산', '주가 20,000원 ÷ 지배주주 EPS 1,000원'),
        ('자체계산', '시가총액 100억 ÷ 지배주주 순이익 10억 (2025년 연간)'),
        ('자체계산', '시가총액 100억 ÷ 순이익 10억 (보통주 EPS 원문 검수)'),
        ('외부 수신', '시가총액 100억 ÷ 순이익 10억 (2025년 연간)'),
    ):
        values, descriptions, warnings = valuation_display({'PER': '10'}, {'PER': note}, {'PER': formula})
        assert values['PER'] == '10' and descriptions['PER'] == formula and not warnings


def test_r4_reference_uses_qualified_per_from_r3_without_peer_recalculation():
    stock = {'ticker': '084010', 'name': 'fixture', 'facts': {'PER': '10'},
             'facts_note': {'PER': '자체계산'},
             'facts_calc': {'PER': '시가총액 100억 ÷ 순이익 10억 (2025년 연간)'},
             'peer': {'sector': 'fixture', 'rows': [{'key': 'PER', 'value': '10', 'median': '12'}]}}
    report = build_report('084010', lambda name: {'stocks': [stock]} if name == 'stock_report_public.json' else {})
    r3 = next(section for section in report['sections'] if section['id'] == 'R3')
    r4 = next(section for section in report['sections'] if section['id'] == 'R4')
    assert next(row for row in r3['rows'] if row[0] == 'PER')[1] == '비교 보류 · 수집값 10'
    assert next(row for row in r4['rows'] if row[0] == 'PER')[1:] == ['비교 보류 · 수집값 10', '12']
    assert stock['facts']['PER'] == '10' and stock['peer']['rows'][0]['value'] == '10'


def test_older_cash_period_does_not_validate_latest_display_summary():
    fin = {'period': '2025', 'currency': 'KRW', 'fs_div': 'CFS',
           'groups': [{'title': '현금흐름표', 'rows': [{'k': '영업활동', 'v': '396억'}]}]}
    cash = {'year': 2022, 'start': '2022-01-01', 'end': '2022-12-31',
            'period_kind': 'annual', 'currency': 'KRW', 'fs_div': 'CFS',
            'source_url': 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20230331003410',
            'ocf': 396e8, 'net': 100e8}
    state = cash_receipt(fin, {'cash': cash})
    assert not state['analysis_usable'] and not state['source_linked']
    assert '2022-01-01~2022-12-31' in state['note']
    cash.update(year=2025, start='2025-01-01', end='2025-12-31')
    assert cash_receipt(fin, {'cash': cash})['summary_linked']
    cash['ocf'] = 39618460129
    assert cash_receipt(fin, {'cash': cash})['summary_linked']
    assert not cash_receipt({**fin, 'fs_div': 'OFS'}, {'cash': cash})['summary_linked']
    cash['ocf'] = 100e8
    assert not cash_receipt(fin, {'cash': cash})['summary_linked']
    state = cash_receipt({}, {'cash': cash})
    assert state['reported_period'] == '2025-12-31' and state['analysis_usable']
    assert '요약값 미수신' in state['status']


def test_dossier_keeps_unlinked_annuals_cash_and_exact_missing_fields():
    period = {'year': 2025, 'start': '2025-01-01', 'end': '2025-12-31', 'currency': 'KRW',
              'fs_div': 'CFS', 'period_kind': 'annual', 'source_url': 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260318000780',
              'revenue': 100, 'op': -2, 'net': 3}
    stock = {'ticker': '084010', 'financial_evidence': {'periods': [period]},
             'fin_series': [{'year': 2023, 'revenue': 140}, {'year': 2024, 'revenue': 120}, period],
             'calendar': [{'event': '제출 예상', 'basis': '과거 제출 패턴'}],
             'financials': {'period': '2025', 'groups': [{'title': '현금흐름표', 'rows': [{'k': '영업활동', 'v': '396억'}]}]}}
    docs = {'stock_report_public.json': {'stocks': [stock]},
            'dart_quarterly_public.json': {'stocks': {'084010': {'quarters': [{'q': '2026-06-30', 'revenue': 60}]}}},
            'kr_earnings_pattern.json': {'patterns': {'084010': [{'filed': '2026-05-15', 'form': '정기보고서'}]}}}
    report = build_report('084010', lambda name: docs.get(name, {}))
    pending = next(s for s in report['sections'] if s['id'] == 'R1U')
    assert [r[0] for r in pending['rows']] == ['2023', '2024']
    assert all(r[-1] == 'KRW 피드 기본값' for r in pending['rows'])
    assert isinstance(report['annual_basis'], list) and report['annual_basis'][0]['year'] == 2025
    assert report['reader']['current'] == period and report['reader']['prior'] is None
    assert report['reader']['cash'] is None and '396억' in report['reader']['cash_notes'][0]
    assert '단일 분기·누적 구분' in report['reader']['observations'][-1]
    assert next(c for c in report['coverage'] if c['id'] == 'E')['published'] == '최신 제출 2026-05-15'
    assert next(c for c in report['reading']['checklist'] if c['item'] == '현금흐름')['state'] == '요약값 수신 · 분석 연결 미완료'
