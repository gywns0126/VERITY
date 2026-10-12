# Focused subset of existing local contract regressions; no saved raw fixture required.
from copy import deepcopy

import pytest

from api.intelligence.portfolio_contract_facts import (
    MAIN, attach_contract_facts, parse_contract_facts, validate_contract_fact,
)


RECEIPT = "20260930800867"
DCM = "11597650"
ISSUER = "KR:028050"
NAME = "삼성E&A"
TITLE = "단일판매ㆍ공급계약체결"
FILED = "2026-09-30"
OBSERVED = "2026-10-03T12:42:06Z"
VIEWER = ("https://dart.fss.or.kr/report/viewer.do?rcpNo=" + RECEIPT
          + "&dcmNo=" + DCM + "&eleId=0&offset=0&length=0&dtd=HTML")



def _body(*, correction=True, issuer=NAME, duplicate_name=False, financial_rows="",
          counterparty_financial_rows=""):
    correction_tables = ""
    if correction:
        correction_tables = """
        <table><tr><td>정정일자</td><td>2026-09-29</td></tr>
        <tr><td>2. 정정관련 공시서류제출일</td><td>2026-07-01</td></tr>
        <tr><td>3. 정정사유</td><td>유보기한 정정</td></tr></table>
        <table><tr><td>정정항목</td><td>정정전</td><td>정정후</td></tr>
        <tr><td>8. 공시 유보 관련 사항 - 3. 유보기한</td><td>2026-09-30</td><td>2026-11-30</td></tr></table>
        """
    repeated = f"<tr><td>- 체결계약명</td><td>다른 계약</td></tr>" if duplicate_name else ""
    title_day = FILED.replace("-", ".")
    return f"""<html><head><title>{issuer}/{TITLE}/({title_day}){TITLE}</title></head>
    <body><div class="xforms">{correction_tables}<table>
    <tr><td>1. 판매ㆍ공급계약 구분</td><td>용역제공</td></tr>
    <tr><td>- 체결계약명</td><td>-</td></tr>{repeated}
    {financial_rows}<tr><td>3. 계약상대</td><td>글로벌 발주처</td></tr>{counterparty_financial_rows}
    <tr><td>5. 계약기간</td><td>시작일</td><td>2030-01-01</td></tr>
    <tr><td>종료일</td><td>2050-12-31</td></tr>
    <tr><td>7. 계약(수주)일자</td><td>2026-06-30</td></tr>
    </table><script><table><tr><td>3. 계약상대</td><td>가짜</td></tr></table></script>
    </div></body></html>""".encode("euc-kr")


def _parse(raw=None, **changes):
    args = {
        "receipt_no": RECEIPT,
        "issuer_id": ISSUER,
        "issuer_name": NAME,
        "filed_on": FILED,
        "main_url": MAIN + RECEIPT,
        "viewer_url": VIEWER,
        "observed_at": OBSERVED,
    }
    args.update(changes)
    return parse_contract_facts(_body() if raw is None else raw, **args)


def test_extracts_optional_literal_financial_terms_before_counterparty_boundary():
    rows = """<tr><td>2. 계약내역</td><td>계약금액(원)</td><td>657,448,735,562</td></tr>
    <tr><td>최근매출액(원)</td><td>8,318,442,435,057</td></tr>
    <tr><td>매출액 대비(%)</td><td>7.90</td></tr>"""
    result = _parse(_body(financial_rows=rows))
    assert result["contract"]["financial_terms"] == {
        "amount": {"label": "계약금액(원)", "value": "657,448,735,562"},
        "recent_revenue": {"label": "최근매출액(원)", "value": "8,318,442,435,057"},
        "revenue_ratio": {"label": "매출액 대비(%)", "value": "7.90"},
    }
    assert validate_contract_fact(result)["contract"]["financial_terms"] == result["contract"]["financial_terms"]


def test_financial_terms_omit_unavailable_values_and_preserve_dash_verbatim():
    rows = '<tr><td>2. 계약내역</td><td>계약금액(원)</td><td>-</td></tr>'
    result = _parse(_body(financial_rows=rows,
                          counterparty_financial_rows='<tr><td>최근 매출액(원)</td><td>999,999</td></tr>'))
    assert result["contract"]["financial_terms"] == {
        "amount": {"label": "계약금액(원)", "value": "-"},
    }


def _basis_fact(note):
    rows = '<tr><td>2. 계약내역</td><td>최근매출액(원)</td><td>1,000</td></tr>'
    raw = _body(financial_rows=rows).decode('euc-kr').replace(
        '</table><script>', '<tr><td>10. 기타 투자판단에 참고할 사항</td></tr>'
        f'<tr><td>{note}</td></tr></table><script>')
    return _parse(raw.encode('euc-kr'))


@pytest.mark.parametrize('scope,expected', [('연결', 'consolidated'), ('별도', 'separate'), ('개별', 'separate')])
def test_revenue_basis_is_explicit_quote_bound_and_optional_for_legacy(scope, expected):
    note = f'상기2. 계약내역 중 최근매출액은 2025년도 {scope}재무제표 기준임.'
    fact = _basis_fact(note)
    assert fact['contract']['revenue_basis'] == {'year': 2025, 'scope': expected, 'quote': note}
    assert validate_contract_fact(fact) == fact
    old = deepcopy(fact)
    old['contract'].pop('revenue_basis'); old['contract'].pop('financial_notes')
    assert validate_contract_fact(old) == old
    doc = _document()
    assert attach_contract_facts({'contract_facts': [fact]}, [doc], _catalog())['accepted'] == 1
    assert doc['contract_facts']['contract'] == fact['contract']


@pytest.mark.parametrize('note', [
    '최근 사업년도 2025년 연결재무제표 기준 매출액(1.1조원)대비는 26.1%입니다.',
    '계약상대방의 최근매출액은 2025년도 연결재무제표 기준임.',
    '상기2. 계약내역 중 최근매출액은 2025년도 연결재무제표 기준이 아닙니다.',
    '상기2. 계약내역 중 최근매출액은 2027년도 연결재무제표 기준임.',
    '상기2. 계약내역 중 최근매출액은 2025년도 연결재무제표 기준임. '
    '최근매출액은 2024년도 별도재무제표 기준임.',
    '상기2. 계약내역 중 최근매출액은 2025년도 연결재무제표 기준임. 최근매출액은 미확인입니다.',
])
def test_ambiguous_other_party_future_or_reference_denominators_are_not_inferred(note):
    fact = _basis_fact(note)
    assert 'revenue_basis' not in fact['contract']
    assert fact['contract']['financial_notes']['value'] == note
    assert validate_contract_fact(fact) == fact


@pytest.mark.parametrize('mutation', ['year', 'scope', 'quote', 'extra', 'no-denominator', 'notes'])
def test_revenue_basis_validator_rejects_forged_or_unbound_fields(mutation):
    fact = _basis_fact('최근매출액은 2025년도 별도재무제표 기준임.')
    basis = fact['contract']['revenue_basis']
    if mutation == 'year': basis['year'] = 2024
    elif mutation == 'scope': basis['scope'] = 'consolidated'
    elif mutation == 'quote': basis['quote'] = '원문에 없는 근거'
    elif mutation == 'extra': basis['grade'] = 'high'
    elif mutation == 'notes': fact['contract']['financial_notes']['value'] = '다른 원문.'
    else: fact['contract']['financial_terms'].pop('recent_revenue')
    with pytest.raises(ValueError):
        validate_contract_fact(fact)


def test_financial_terms_omit_ambiguous_amount_aliases():
    rows = """<tr><td>2. 계약내역</td><td>계약금액 총액(원)</td><td>100</td></tr>
    <tr><td>계약금액(원)</td><td>100</td></tr>"""
    result = _parse(_body(financial_rows=rows))
    assert "financial_terms" not in result["contract"]


@pytest.mark.parametrize("rows", [
    '<tr><td>표시항목</td><td>계약금액(원)</td><td>100</td></tr>',
    '<tr><td>2. 계약내역</td><td>계약금액(원)</td><td>100</td><td>100</td></tr>',
    '<tr><td>2. 계약내역</td><td>설명</td></tr><tr><td>계약금액(원)</td><td>금액</td><td>100</td></tr>',
])
def test_financial_terms_omit_missing_or_unsupported_contract_section_rows(rows):
    result = _parse(_body(financial_rows=rows))
    assert "financial_terms" not in result["contract"]


@pytest.mark.parametrize("key,label", [
    ("amount", "확정 계약금액"),
    ("recent_revenue", "- 최근 매출액(원)"),
    ("revenue_ratio", "매출액 대비 (원)"),
])
def test_financial_terms_validator_rejects_labels_outside_exact_whitelist(key, label):
    fact = _parse()
    fact["contract"]["financial_terms"] = {key: {"label": label, "value": "12"}}
    with pytest.raises(ValueError):
        validate_contract_fact(fact)


def _document(**changes):
    value = {
        "id": "DART:" + RECEIPT, "title": "[기재정정]" + TITLE,
        "url": MAIN + RECEIPT, "as_of": FILED, "kind": "disclosure",
        "source": "DART", "company_ids": [ISSUER],
    }
    value.update(changes)
    return value


def _catalog():
    return [{"id": ISSUER, "name": NAME}]
