"""Concise reading order and follow-up baselines from the existing dossier.

Company quotations are evidence, not independent causal verification. No model
calls, predictions or undocumented substitution of missing financial values.
"""
if __package__:
    from .report_context import _number, format_money
    from .report_reader import period_label
else:
    from report_context import _number, format_money
    from report_reader import period_label


def reading_guide(reader, company, events, issues, is_financial=False):
    current, prior, cash = (reader.get(k) for k in ('current', 'prior', 'cash'))
    visuals = reader.get('visuals', {})
    insights, charts = visuals.get('insights', {}), visuals.get('charts', {})
    sources = [r for r in (prior, current) if r]
    income = insights.get('income')
    evidence = ' · '.join(f'{r[0]} {r[2]} ({r[3]})' for r in reader['rows'] if r[2] != '—')
    headline = {'label': '이번에 달라진 점',
                'title': income['title'] if income else '같은 기준의 최근 실적부터 확인합니다',
                'detail': evidence if current else '기간·통화·보고 범위·원문이 연결된 손익 자료가 부족합니다.',
                'sources': sources}
    # Counter-evidence is bounded to actual observations; absence is not safety.
    annual = insights.get('annual', {})
    cash_insight = insights.get('cash', {})
    if annual.get('title') == '연간 흐름과 최근 실적의 방향이 달라졌습니다':
        counter = {'title': annual['title'], 'detail': annual['evidence'],
                   'sources': charts.get('annual', {}).get('sources', [])[-2:] + sources}
    elif cash_insight and cash and _number(cash.get('net')) is not None and cash['net'] > 0 and cash['ocf'] < cash['net']:
        counter = {'title': cash_insight['title'], 'detail': cash_insight['evidence'], 'sources': [cash]}
    else:
        counter = {'title': '변화가 이어지는지는 아직 확인이 필요합니다',
                   'detail': '수신된 실적 한 번으로 장기 추세를 확정하지 않습니다. 사업 원인과 다음 같은 기간의 실적을 함께 확인하세요.', 'sources': sources[-1:]}
    counter['label'] = '함께 봐야 할 점'

    newer = next((n for n in reader['observations'] if '본문 수치에서 제외' in n), '')
    if newer:
        gap = newer
    elif not current:
        gap = '원문·기간·통화·연결/별도를 갖춘 손익 자료가 없어 최근 실적 비교를 보류했습니다.'
    elif not prior:
        gap = '동일 기준의 전년 동기 자료가 없어 실적 증감률을 계산하지 않았습니다.'
    elif not cash:
        gap = '기간과 원문이 연결된 현금흐름이 없어 이익과 현금을 대조하지 못했습니다.'
    elif current and cash['end'] < current['end']:
        gap = f"현금흐름은 {cash['end']}까지로, 손익의 {current['end']}보다 이전 자료입니다."
    elif not is_financial and _number(cash.get('capex')) is None:
        gap = '같은 기간의 유형자산 취득 지출이 없어 투자 지출 차감 후 현금흐름을 계산하지 않았습니다.'
    elif not company['excerpts']:
        gap = '현재 실적 기간에 대응하는 회사의 원인 설명 문단을 확보하지 못했습니다.'
    else:
        missing = [r['label'] for r in company['topics'] if not r['refs']]
        gap = ('회사 설명에서 ' + '·'.join(missing) + ' 항목은 발췌되지 않았습니다. 영향이 없다는 뜻은 아닙니다.') if missing else '회사 설명은 경영진의 설명입니다. 항목별 기여 금액과 일회성 여부는 원문 대조가 필요합니다.'
    unresolved = {'label': '아직 확인할 빈칸', 'title': '해석의 범위를 제한하는 자료', 'detail': gap, 'sources': []}

    checklist = []
    if current:
        for key, label in [('revenue', '매출 흐름'), ('op', '영업수익성')]:
            value = _number(current.get(key))
            if value is None:
                continue
            baseline = format_money(value, current['currency'])
            if not is_financial and key == 'op' and _number(current.get('revenue')) and current['revenue'] > 0:
                baseline += f" · 영업이익률 {value / current['revenue'] * 100:.1f}%"
            checklist.append({'item': label, 'state': period_label(current) + '\n' + baseline,
                              'next': '다음 공시도 같은 기간 길이의 전년 동기와 비교. ' + ('매출 증감 방향 확인.' if key == 'revenue' else '영업이익과 이익률의 방향을 함께 확인.'),
                              'source': {'text': '현재 근거', 'url': current['source_url']}})
    checklist.append({'item': '현금흐름',
        'state': (period_label(cash) + '\n영업현금 ' + format_money(cash['ocf'], cash['currency'])) if cash else '기간·원문을 갖춘 현금흐름 미확보',
        'next': ('같은 기간의 현금흐름표를 확인. 금융업의 대출·조달 구조를 함께 읽으며 일반 기업식 FCF로 평가하지 않음.' if is_financial else '같은 기간·공시의 순이익, 영업현금흐름, 유형자산 취득 지출을 대조. 누락 항목부터 확인.'),
        'source': {'text': '현재 근거', 'url': cash['source_url']} if cash else '미확보'})
    checklist.append({'item': '변화의 원인',
        'state': f"현재 실적과 기간이 맞는 회사 설명 {len(company['excerpts'])}개 문단. " + ' / '.join(r['label'] + (' 연결' if r['refs'] else ' 미확보') for r in company['topics']),
        'next': '가격·물량·구성·비용 설명과 항목별 기여 금액을 원문에서 확인. 반복 가능한 변화와 일회성 항목 구분.',
        'source': company['source'] or '미확보'})
    if events:
        event = events[0]
        checklist.append({'item': '최근 공시', 'state': event[0] + ' · ' + event[1],
                          'next': '계약·자금·사업 조건과 정정 여부를 본문에서 확인한 뒤 실적과 연결.', 'source': event[3]})
    valuation = next((i for i in issues if i['refs'] == 'R3 · R4'), None)
    if valuation:
        checklist.append({'item': '가격 비교의 기준', 'state': valuation['observation'],
                          'next': '이익 기준기간·주가 기준일·업종 표본이 일치하는지 먼저 확인. 불일치하면 배수 비교 보류.', 'source': '부록 R3 · R4'})
    return {'version': 'report-reading-v1', 'cards': [headline, counter, unresolved], 'checklist': checklist,
            'company': company}
