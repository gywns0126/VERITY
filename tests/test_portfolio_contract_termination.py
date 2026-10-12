# Focused subset of existing local contract regressions; no saved raw fixture required.
from copy import deepcopy

import pytest

from api.intelligence.portfolio_contract_facts import MAIN
from api.intelligence.portfolio_contract_termination import (
    parse_contract_termination, validate_contract_termination,
)


RECEIPT = "20260929800628"
ISSUER = "KR:069260"
NAME = "TKG휴켐스"
SOURCE_NAME = "티케이지휴켐스"
FILED = "2026-09-29"
OBSERVED = "2026-10-03T17:39:02.431157+00:00"
VIEWER = ("https://dart.fss.or.kr/report/viewer.do?rcpNo=" + RECEIPT
          + "&dcmNo=11594687&eleId=0&offset=0&length=0&dtd=HTML")



def _body(*, issuer=SOURCE_NAME, title="단일판매ㆍ공급계약 해지",
          links=None, anchor="1. 판매ㆍ공급계약 해지 구분"):
    links = links or [
        ("2024-06-28 단일판매ㆍ공급계약체결",
         "/dsaf001/main.do?rcpNo=20240628800179"),
        ("2015-04-28 단일판매ㆍ공급계약체결",
         "/dsaf001/main.do?rcpNo=20150428800537"),
    ]
    anchors = " ".join(f'<a href="{href}">{text}</a>' for text, href in links)
    return f"""<html><head><title>{issuer}/{title}/(2026.09.29){title}</title></head>
    <body><div class="xforms"><table>
    <tr><td>{anchor}</td><td>상품공급</td></tr>
    <tr><td>- 해지계약명</td><td>DNT매매 계약</td></tr>
    <tr><td>3. 계약상대</td><td>OCI 주식회사</td></tr>
    <tr><td>4. 계약기간</td><td>시작일</td><td>2014-08-18</td></tr>
    <tr><td>종료일</td><td>2027-03-28</td></tr>
    <tr><td>5. 해지 주요사유</td><td>계약상대방의 TDI사업종료에 따른 공급계약 해지</td></tr>
    <tr><td>6. 해지일자</td><td>2026-09-29</td></tr>
    <tr><td>8. 기타 투자판단과 관련한 중요사항</td><td>해지일자는 공문 수령일이며 효력은 6개월 이후 발효됩니다.</td></tr>
    <tr><td>관련공시</td><td>{anchors}</td></tr>
    </table></div></body></html>""".encode("euc-kr")


def _parse(raw=None, **changes):
    args = {"receipt_no": RECEIPT, "issuer_id": ISSUER, "issuer_name": NAME,
            "expected_source_issuer_name": SOURCE_NAME, "filed_on": FILED,
            "main_url": MAIN + RECEIPT, "viewer_url": VIEWER,
            "observed_at": OBSERVED}
    args.update(changes)
    return parse_contract_termination(_body() if raw is None else raw, **args)


def _dated_body(note):
    return _body().decode('euc-kr').replace(
        '해지일자는 공문 수령일이며 효력은 6개월 이후 발효됩니다.', note).encode('euc-kr')


def test_explicit_future_effect_is_not_current_termination_and_legacy_is_unchanged():
    result = _parse(_dated_body('해지통보일 (2026.09.29)로부터 해지발효일 (2027.03.28)까지 공급합니다.'))
    assert result['termination']['date']['value'] == '2026-09-29'
    assert result['termination']['notice_on']['date'] == '2026-09-29'
    assert result['termination']['effective_on']['date'] == '2027-03-28'
    assert result['current_contract_status'] == 'not-inferred'
    assert validate_contract_termination(result) == result
    for key in ('notice_on', 'effective_on'):
        result['termination'].pop(key)
    assert validate_contract_termination(result) == result
    # A period end and relative "six months" alone never become an effect date.
    legacy = _parse()
    assert 'notice_on' not in legacy['termination'] and 'effective_on' not in legacy['termination']


@pytest.mark.parametrize('note', [
    '해지통보일 (2026.09.30)로부터 해지발효일 (2027.03.28)까지 공급합니다.',
    '해지통보일 (2027.09.29)로부터 해지발효일 (2028.03.28)까지 공급합니다.',
    '해지통보일 (2026.09.29) 및 해지통보일 (2026.09.28)입니다.',
    '해지통보일 (2026.13.29)로부터 해지발효일 (2027.03.28)까지 공급합니다.',
    '자회사 해지통보일 (2026.09.29)로부터 해지발효일 (2027.03.28)까지 공급합니다.',
])
def test_notice_mismatch_ambiguity_and_wrong_scope_do_not_promote_dates(note):
    result = _parse(_dated_body(note))
    assert 'notice_on' not in result['termination'] and 'effective_on' not in result['termination']
    assert result['current_contract_status'] == 'not-inferred'


@pytest.mark.parametrize('effect', [
    '해지발효일 (2026.03.28)', '해지발효일 (2027.02.30)',
    '해지발효일 (2027.03.28) 및 해지발효일 (2027.04.28)',
    '해지발효일 (2027.03.28)이 아닙니다', '효력은 6개월 이후',
])
def test_ambiguous_invalid_negative_and_relative_effect_is_omitted(effect):
    result = _parse(_dated_body('해지통보일 (2026.09.29)입니다. ' + effect + '.'))
    assert result['termination']['notice_on']['date'] == '2026-09-29'
    assert 'effective_on' not in result['termination']


@pytest.mark.parametrize('key,label,day', [
    ('notice_on', '해지통보일', '2026.09.29'),
    ('effective_on', '해지발효일', '2027.03.28'),
])
@pytest.mark.parametrize('negative', [
    '아닌 다른 날짜입니다', '아니다', '아님', '아닐 수 있습니다',
    '아니라 다른 날짜입니다', '아닙니다',
])
def test_negated_date_forms_are_omitted_and_cannot_be_reinjected(key, label, day, negative):
    note = '해지통보일 (2026.09.29)입니다. 해지발효일 (2027.03.28)입니다.'
    original = f'{label} ({day})입니다'
    negated = f'{label} ({day})이 {negative}'
    changed_note = note.replace(original, negated)
    result = _parse(_dated_body(changed_note))
    assert key not in result['termination']
    assert 'effective_on' not in result['termination']
    if key == 'effective_on':
        assert result['termination']['notice_on']['date'] == FILED
    assert result['termination']['other_matters']['value'] == changed_note
    assert result['termination']['date']['value'] == FILED
    assert result['current_contract_status'] == 'not-inferred'
    assert validate_contract_termination(result) == result
    # Matching the altered quote to the note must not restore a negated date.
    injected = _parse(_dated_body(note))
    injected['termination']['other_matters']['value'] = changed_note
    injected['termination'][key]['quote'] = injected['termination'][key]['quote'].replace(original, negated)
    with pytest.raises(ValueError):
        validate_contract_termination(injected)


def test_validator_rejects_status_promotion_and_changed_proof():
    fact = _parse()
    for path, value in [
        (("current_contract_status",), "terminated"),
        (("proves",), "termination"),
        (("source", "content_sha256"), "z" * 64),
    ]:
        changed = deepcopy(fact)
        target = changed
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        with pytest.raises(ValueError):
            validate_contract_termination(changed)
