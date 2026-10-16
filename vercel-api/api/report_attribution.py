"""Bounded monetary attributions from already period/issuer-checked quotations.

These are company explanations, not independently established causal effects.
Do not interpret total profit changes, percentages, or segment numbers as drivers.
"""
import re
from decimal import Decimal

if __package__:
    from .report_context import _number
    from .report_reader import comparable, period_label
else:
    from report_context import _number
    from report_reader import comparable, period_label


_DRIVER = re.compile(
    r'\b(?P<direction>unfavorable|favorable|higher|lower|increased|decreased)\s+'
    r'(?P<driver>price realization|sales volume|shipment volumes?|product mix|sales mix|'
    r'manufacturing costs?|production costs?|operating costs?|currency impacts?|'
    r'foreign currency (?:translation|exchange))\s+of\s+'
    r'\$(?P<amount>\d[\d,]*(?:\.\d+)?)\s+(?P<scale>billion|million)\b', re.I)
_NAMES = {'price': '가격', 'sales volume': '판매량', 'shipment': '출하량',
          'product mix': '제품 구성', 'sales mix': '제품 구성', 'manufacturing': '제조원가',
          'production': '생산비용', 'operating': '운영비용', 'currency': '환율',
          'foreign currency': '환율'}
_METRICS = {'매출': 'revenue', '영업손익': 'op', '영업이익': 'op', '순이익': 'net'}


def _extract(quote):
    cause = re.search(r'\b(?:due to|driven by|reflect(?:s|ed|ing)?|result(?:ed|ing) from)\b', quote, re.I)
    if not cause:
        return []
    if re.search(r'\b(?:not|never|unrelated|rather than)\s*$', quote[:cause.start()], re.I):
        return []
    if re.search(r'\b(segment|division|regional|region|North America|South America|Latin America|Europe|Asia|EMEA|APAC)\b', quote, re.I):
        return []
    body = quote[cause.end():]
    # No segment, outlook, hypothetical, adjusted or tax-basis mixtures.
    if re.search(r'\b(segment|division|adjusted|pretax|after.tax|before.tax|expect|forecast|would|could|will|excluding)\b', body, re.I):
        return []
    rows = []
    for match in _DRIVER.finditer(body):
        direction, driver = match['direction'].lower(), match['driver'].lower()
        before = body[max(0, match.start()-24):match.start()].lower()
        after = body[match.end():match.end()+20].lower()
        if re.search(r'\b(not|without|approximately|about)\s*$', before) or re.match(r'\s*(?:to\b|[-–])', after):
            continue
        raw = match['amount'].replace(',', '')
        scale = Decimal(10**9 if match['scale'].lower() == 'billion' else 10**6)
        value = Decimal(raw) * scale
        cost = 'cost' in driver
        positive = direction == 'favorable' or (direction in ('higher', 'increased') and not cost) or (direction in ('lower', 'decreased') and cost)
        sign = 1 if positive else -1
        precision = scale * Decimal(10) ** Decimal(Decimal(raw).as_tuple().exponent)
        label = next(name for stem, name in _NAMES.items() if driver.startswith(stem))
        rows.append({'label': label, 'driver': driver, 'amount': int(value) * sign,
                     'reported_amount': '$' + match['amount'] + ' ' + match['scale'].lower(),
                     'quote_span': match[0], 'rounding_step': int(precision),
                     'kind': 'company_reported_contribution'})
    # Repeated labels can represent a subtotal or offset: do not double count.
    names = [r['label'] for r in rows]
    return [] if len(set(names)) != len(names) else rows


def monetary_attribution(reader, company, is_financial=False):
    current, prior = reader.get('current'), reader.get('prior')
    result = {'status': 'unavailable', 'basis': None, 'groups': [],
              'note': '원인별 금액을 명시한 같은 기간의 회사 설명이 없습니다. 미확보는 영향 0이 아닙니다.',
              'classification': 'company_reported_not_independently_verified'}
    if not current or not prior or not comparable(prior, current):
        result['note'] = '같은 기간 길이·통화·보고 범위의 전년 동기 수치가 없어 원인 금액과 증감을 대조하지 않았습니다.'
        return result
    result['basis'] = {'current': current, 'prior': prior, 'label': period_label(current)}
    if is_financial:
        result['note'] = '금융업은 산업기업식 가격·물량·제조비용 분류를 적용하지 않습니다.'
        return result
    if company.get('period_matches_current') is False:
        result['note'] = '회사 설명은 다른 기간의 누적 설명입니다. 현재 단일 분기 원인별 금액으로 전용하지 않았습니다.'
        return result
    source = (company.get('source') or {}).get('url', '')
    accession = str(current.get('accession') or '').replace('-', '')
    if not accession or accession not in source or not source.startswith('https://www.sec.gov/Archives/edgar/data/'):
        return result
    period = current['start'] + ' ~ ' + current['end']
    for excerpt in company.get('excerpts', []):
        metric = _METRICS.get(excerpt.get('metric'))
        if excerpt.get('period') != period or not metric or current['currency'] != 'USD':
            continue  # $ without an explicit USD basis is ambiguous.
        old, new = _number(prior.get(metric)), _number(current.get(metric))
        quote = excerpt.get('quote', '')
        if old is None or new is None or not isinstance(quote, str):
            continue
        rows = _extract(quote)
        if not rows:
            continue
        delta = new - old
        subtotal = sum(r['amount'] for r in rows)
        residual = delta - subtotal
        result['groups'].append({'metric': metric, 'metric_label': excerpt['metric'],
            'prior': old, 'current': new, 'change': delta, 'currency': current['currency'],
            'rows': rows, 'subtotal': subtotal, 'residual': residual,
            'rounding_bound': sum(r['rounding_step'] / 2 for r in rows),
            'source_url': source, 'quote': quote, 'ref': excerpt.get('id'),
            'residual_label': '미설명 잔여분 · 반올림 및 다른 요인 포함 가능'})
    if result['groups']:
        result.update(status='partial', note='회사 원문의 명시적 금액만 연결했습니다. 회사 설명이며 독립 인과 검증이 아닙니다. 원문 반올림 단위를 보존하고 잔여분은 가격·물량·비용에 임의 배분하지 않습니다. 매출 기여액을 영업이익 기여액으로 옮기지 않습니다.')
    return result
