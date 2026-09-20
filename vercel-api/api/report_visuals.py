"""Charts and bounded interpretations from the reader's period-validated facts.

No forecasting, scores, model calls or inferred business causes. SVG is generated
only for the PDF; the own-AI export retains compact numerical chart evidence.
"""
from html import escape

if __package__:
    from .report_context import _number, format_money
else:
    from report_context import _number, format_money

ACCENT = '#6c5ce7'
BLUE = '#4384d8'
INK = '#191f28'
SUB = '#657084'
GREY = '#a9afbc'


def _source(row):
    return {k: row.get(k, '') for k in ('start', 'end', 'period_kind', 'currency', 'fs_div', 'source_url')}


def _margin(row):
    revenue, op = _number(row.get('revenue')), _number(row.get('op'))
    return op / revenue * 100 if revenue is not None and revenue > 0 and op is not None else None


def _income_reading(prior, current):
    values = [_number(r.get(k)) for r in (prior, current) for k in ('revenue', 'op')]
    if any(v is None for v in values):
        return None
    r0, o0, r1, o1 = values
    if r0 <= 0 or r1 <= 0:
        return None
    m0, m1 = o0 / r0 * 100, o1 / r1 * 100
    dr, do = r1 - r0, o1 - o0
    if dr > 0 and do < 0:
        title = '매출 증가가 영업이익 증가로 이어지지 않았습니다'
        meaning = '매출은 늘었지만 영업이익은 줄었습니다. 더 큰 매출 규모에도 수익성이 낮아진 점이 이번 실적의 확인 과제입니다.'
    elif o0 == 0 and o1 > 0:
        title = '손익분기에서 영업이익이 발생했습니다'
        meaning = '전년 동기 영업손익은 0이고 이번 기간에는 양수입니다. 전기 분모가 0이므로 증가율을 계산하지 않습니다.'
    elif o0 < 0 < o1:
        title = '영업손익이 흑자로 전환됐습니다'
        meaning = '전년 동기의 영업손실에서 이번 기간에는 영업이익이 발생했습니다. 손익 전환의 규모와 반복 가능성을 나누어 살펴볼 필요가 있습니다.'
    elif o1 < 0 <= o0:
        title = '영업손익이 적자로 전환됐습니다'
        meaning = '전년 동기와 달리 이번 기간에는 영업손실이 발생했습니다. 사업부별 손익과 일회성 비용부터 확인해야 합니다.'
    elif o0 < 0 and o1 < 0:
        title = '영업손실이 줄었습니다' if do > 0 else '영업손실이 늘었습니다' if do < 0 else '영업손실 규모가 같습니다'
        meaning = '두 기간 모두 영업손실 상태입니다. 손실 규모의 변화와 흑자 전환 여부는 구분해서 읽어야 합니다.'
    elif dr > 0 and m1 > m0:
        title = '매출 성장에 수익성 개선이 동반됐습니다'
        meaning = '매출이 늘면서 매출에서 영업이익으로 남는 비율도 높아졌습니다. 이번 기간에는 외형과 수익성이 함께 개선됐습니다.'
    elif dr < 0 and do > 0:
        title = '매출 감소에도 영업이익은 늘었습니다'
        meaning = '매출 규모는 줄었지만 영업이익은 늘었습니다. 제품 구성·비용·일회성 항목 중 어느 부분이 변화를 설명하는지 확인할 필요가 있습니다.'
    elif dr < 0 and do < 0:
        title = '매출과 영업이익이 함께 줄었습니다'
        meaning = '외형과 영업이익이 모두 감소했습니다. 이익률까지 낮아졌는지 함께 보면 매출 감소와 수익성 변화의 방향을 구분할 수 있습니다.'
    else:
        title = '매출 규모와 수익성을 함께 읽어야 합니다'
        meaning = '매출과 영업이익의 변화를 함께 비교했습니다. 매출이 늘었다는 사실만으로 영업이익률 개선까지 뜻하지는 않습니다.'
    return {'title': title, 'meaning': meaning,
            'evidence': f'영업이익률 {m0:.1f}% → {m1:.1f}% ({m1-m0:+.1f}%p). 영업이익 ÷ 매출 × 100 자체계산.',
            'limit': '가격·판매량·제품 구성·비용의 기여도는 이 수치만으로 확정할 수 없습니다.',
            'next': '다음 실적도 전년 동기와 비교해 이익률과 사업부별 손익의 변화가 이어지는지 확인하세요.'}


def build_visuals(reader, is_financial, comparable):
    """Use the same validated rows as the PDF tables; never fill missing values."""
    current, prior, cash = (reader.get(k) for k in ('current', 'prior', 'cash'))
    charts, insights = {}, {}
    if current and prior and comparable(prior, current) and not is_financial:
        reading = _income_reading(prior, current)
        if reading:
            insights['income'] = reading
            charts['margin'] = {'kind': 'bars', 'title': '같은 분기의 영업이익률' if current['period_kind'] == 'quarter' else '같은 기간의 영업이익률',
                'unit': '%', 'rows': [{'label': '전년 동기', 'value': _margin(prior), 'display': f'{_margin(prior):.1f}%', 'color': GREY},
                                     {'label': '이번 기간', 'value': _margin(current), 'display': f'{_margin(current):.1f}%', 'color': ACCENT}],
                'sources': [_source(prior), _source(current)], 'note': '0을 기준으로 표시 · 영업이익 ÷ 매출 × 100 자체계산'}

    if 'margin' in charts:
        r0, r1, o0, o1 = [float(v) for v in (prior['revenue'], current['revenue'], prior['op'], current['op'])]
        revenue_effect = (r1-r0) * o0/r0
        margin_effect = o1-o0-revenue_effect
        charts['bridge'] = {'kind': 'waterfall', 'title': '영업이익이 달라진 구조', 'unit': current['currency'],
            'rows': [{'label': '전년 동기', 'from': 0, 'to': o0, 'value': o0, 'color': GREY},
                     {'label': '매출 규모 변화 몫', 'from': o0, 'to': o0+revenue_effect, 'value': revenue_effect, 'color': ACCENT},
                     {'label': '이익률 변화 몫', 'from': o0+revenue_effect, 'to': o1, 'value': margin_effect, 'color': BLUE},
                     {'label': '이번 기간', 'from': 0, 'to': o1, 'value': o1, 'color': INK}],
            'sources': [_source(prior), _source(current)],
            'note': '회계적 분해: 전기 이익률을 유지한 매출 변화 몫 + 이익률 변화 몫. 가격·물량·비용의 실제 기여액을 뜻하지 않습니다.',
            'formula': '전기 영업이익 + (당기 매출−전기 매출)×전기 이익률 + 당기 매출×(당기−전기 이익률) = 당기 영업이익'}
        for row in charts['bridge']['rows']:
            row['display'] = format_money(row['value'], current['currency'])

    # Consecutive fiscal years only, within the latest income's currency/scope.
    annual = [r for r in reader.get('periods', []) if r['period_kind'] == 'annual' and current
              and all(r[k] == current[k] for k in ('currency', 'fs_div'))
              and _number(r.get('revenue')) is not None]
    annual.sort(key=lambda r: (r['end'], r['start']))
    cohort = annual[-1:]
    for row in reversed(annual[:-1]):
        if len(cohort) == 3:
            break
        if not comparable(row, cohort[0]):
            break
        cohort.insert(0, row)
    if len(cohort) >= 2:
        net_panel = is_financial or all(_number(r.get('op')) is None for r in cohort)
        metrics = [('revenue', '보고 매출' if is_financial else '매출', ACCENT),
                   ('net', '순이익', BLUE) if net_panel else ('op', '영업이익', BLUE)]
        panels = []
        for key, label, color in metrics:
            panels.append({'title': label, 'style': 'line' if key == 'revenue' else 'bars', 'rows': [{'label': r['end'][:4], 'value': _number(r.get(key)),
                'display': format_money(r.get(key), r['currency']), 'color': color} for r in cohort]})
        charts['annual'] = {'kind': 'annual', 'title': '최근 연간 실적 흐름', 'unit': cohort[-1]['currency'],
                            'panels': panels, 'sources': [_source(r) for r in cohort],
                            'note': f'기준이 일치하는 연속 {len(cohort)}개 연도 · 높이는 각 지표 안에서 비교 · 빈 값은 미수신'}
        if not is_financial:
            reading = _income_reading(cohort[-2], cohort[-1])
            if reading:
                if current['period_kind'] != 'annual' and current['start'] > cohort[-1]['end'] and prior:
                    annual_m = [_margin(r) for r in cohort[-2:]]
                    latest_m = [_margin(r) for r in (prior, current)]
                    if all(v is not None for v in annual_m + latest_m):
                        ad, qd = annual_m[1] - annual_m[0], latest_m[1] - latest_m[0]
                        if ad < 0 < qd or ad > 0 > qd:
                            reading = {'title': '연간 흐름과 최근 실적의 방향이 달라졌습니다',
                                'meaning': f"최근 연간 비교({cohort[-2]['end'][:4]} → {cohort[-1]['end'][:4]})에서는 이익률이 {'낮아졌지만' if ad < 0 else '높아졌지만'}, 최신 기간의 전년 동기 비교에서는 {'높아졌습니다' if qd > 0 else '낮아졌습니다'}. 최신 기간과 연간 실적은 별도로 비교했습니다.",
                                'evidence': f'연간 이익률 변화 {ad:+.1f}%p · 최신 기간의 전년 동기 변화 {qd:+.1f}%p.',
                                'limit': '기간이 다른 두 금액을 직접 비교한 결과가 아니며, 한 번의 방향 변화로 장기 추세 전환을 확정할 수 없습니다.',
                                'next': '다음 실적에서도 같은 방향의 이익률 변화가 이어지는지 확인하세요.'}
                insights['annual'] = reading
    if cash and not is_financial:
        ocf, net, capex = [_number(cash.get(k)) for k in ('ocf', 'net', 'capex')]
        if ocf is not None:
            rows = [{'label': '순이익', 'value': net, 'color': GREY},
                    {'label': '영업현금흐름', 'value': ocf, 'color': ACCENT}]
            if capex is not None and capex >= 0:
                rows += [{'label': '유형자산 취득 지출', 'value': capex, 'color': GREY},
                         {'label': '취득 지출 차감 후', 'value': ocf-capex, 'color': BLUE}]
            for row in rows:
                row['display'] = format_money(row['value'], cash['currency'])
            charts['cash'] = {'kind': 'bars', 'title': '같은 기간의 이익과 현금', 'unit': cash['currency'],
                'rows': rows, 'sources': [_source(cash)],
                'note': '각 막대는 개별 금액으로 서로 합산하지 않습니다. 취득 지출은 지출 규모를 양수로 표시합니다.'}
            if net is not None:
                if net > 0 and ocf < 0:
                    title, meaning = '이익이 났지만 영업활동에서는 현금이 유출됐습니다', '손익과 현금흐름의 방향이 다릅니다. 매출채권·재고·매입채무 등 운전자본과 비현금 조정 항목을 먼저 확인해야 합니다.'
                elif net > 0 and ocf < net:
                    title, meaning = '영업현금 유입이 순이익보다 작습니다', '보고된 순이익보다 영업활동에서 유입된 현금이 적습니다. 차이의 원인이 운전자본인지 비현금 손익인지 확인해야 합니다.'
                elif net > 0:
                    title, meaning = '영업현금 유입이 순이익 이상입니다', '같은 기간에 영업현금 유입이 순이익 규모를 웃돌거나 같습니다. 현금 유입은 확인되지만 자산·부채 변동과 비현금 비용의 영향도 함께 포함됩니다.'
                else:
                    title, meaning = '손익과 현금흐름을 금액으로 비교합니다', '순이익이 0 이하이므로 현금 전환율은 계산하지 않았습니다. 영업현금흐름이 발생한 경로는 현금흐름표의 조정 항목에서 확인해야 합니다.'
                insights['cash'] = {'title': title, 'meaning': meaning,
                    'evidence': f"동일 기간 순이익 {format_money(net, cash['currency'])} · 영업현금흐름 {format_money(ocf, cash['currency'])}.",
                    'limit': '이 차이만으로 이익의 질을 확정하지 않습니다. 유형자산 취득 지출 차감액은 회사가 정의한 FCF와 다를 수 있습니다.',
                    'next': '다음 실적도 같은 기간의 손익·현금흐름으로 맞추고, 운전자본이 현금흐름 변화에 미친 영향을 확인하세요.'}
    # Read the observation before the graph, while preserving source and limits below.
    for key, chart in charts.items():
        insight = insights.get({'margin': 'income', 'annual': 'annual', 'cash': 'cash'}.get(key, ''))
        chart['takeaway'] = insight['title'] if insight else (
            '매출 규모와 이익률 변화가 영업이익 차이를 나눠 설명합니다 · 회계적 분해'
            if key == 'bridge' else '같은 기준의 연도별 금액을 비교합니다'
            if key == 'annual' else '수신된 현금 금액만 표시합니다 · 미수신은 0이 아닙니다')
    return {'version': 'report-visuals-v2', 'charts': charts, 'insights': insights}


def _text(x, y, text, size=12, color=SUB, anchor='start', weight=600):
    return f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}">{escape(str(text))}</text>'


def _axis(values):
    values = [v for v in values if v is not None]
    lo, hi = min([0.0] + values), max([0.0] + values)
    if lo == hi:
        hi = 1.0
    return lo, hi


def chart_svg(chart):
    """Inline vector drawing with zero baselines; no network or external assets."""
    if chart['kind'] == 'waterfall':
        height, body = 206, []
        rows = chart['rows']
        lo, hi = _axis([r[k] for r in rows for k in ('from', 'to')])
        y = lambda v: 160 - (v-lo)/(hi-lo)*113
        zero = y(0)
        body.append(f'<line x1="12" x2="608" y1="{zero:.2f}" y2="{zero:.2f}" stroke="#a9afbc"/>')
        for i, row in enumerate(rows):
            x = 28 + i*151
            y0, y1 = y(row['from']), y(row['to'])
            body.append(f'<rect x="{x}" y="{min(y0,y1):.2f}" width="102" height="{abs(y1-y0):.2f}" rx="3" fill="{row["color"]}"/>')
            if i < len(rows)-1:
                body.append(f'<line x1="{x+102}" x2="{x+151}" y1="{y1:.2f}" y2="{y1:.2f}" stroke="#a9afbc" stroke-dasharray="3 3"/>')
            body.append(_text(x+51, min(y0,y1)-7, row['display'], 12, INK, 'middle', 700))
            body.append(_text(x+51, 180, row['label'], 11, SUB, 'middle'))
        body.append(_text(12, 202, '0 기준 · ' + chart['unit'], 10))
    elif chart['kind'] == 'annual':
        height, body = 215, []
        for index, panel in enumerate(chart['panels']):
            x0, width, top, bottom = 18 + index * 310, 280, 45, 168
            rows = panel['rows']
            lo, hi = _axis([r['value'] for r in rows])
            y = lambda v: bottom - (v-lo) / (hi-lo) * (bottom-top)
            zero = y(0)
            body.append(_text(x0, 20, panel['title'], 14, INK, weight=800))
            body.append(f'<line x1="{x0}" x2="{x0+width}" y1="{zero:.2f}" y2="{zero:.2f}" stroke="#a9afbc"/>')
            body.append(_text(x0, 207, '0 기준 · ' + chart['unit'], 10))
            step = width / len(rows)
            previous = None
            for i, r in enumerate(rows):
                x = x0 + (i + 0.5) * step
                if r['value'] is None:
                    body.append(_text(x, 113, '미수신', 11, anchor='middle'))
                    previous = None
                else:
                    value_y = y(r['value'])
                    h = abs(zero-value_y)
                    if panel.get('style') == 'line':
                        if previous is not None:
                            body.append(f'<line x1="{previous[0]:.2f}" y1="{previous[1]:.2f}" x2="{x:.2f}" y2="{value_y:.2f}" stroke="{r["color"]}" stroke-width="3"/>')
                        body.append(f'<circle cx="{x:.2f}" cy="{value_y:.2f}" r="{5 if i == len(rows)-1 else 3}" fill="{r["color"] if i == len(rows)-1 else GREY}"/>')
                        previous = (x, value_y)
                    else:
                        body.append(f'<rect x="{x-22:.2f}" y="{min(zero,value_y):.2f}" width="44" height="{h:.2f}" rx="3" fill="{r["color"] if i == len(rows)-1 else GREY}"/>')
                    # Negative labels sit above zero, away from the fiscal-year labels.
                    label_y = value_y - 7 if r['value'] >= 0 else zero - 7
                    body.append(_text(x, label_y, r['display'], 12 if i == len(rows)-1 else 11, INK if i == len(rows)-1 else SUB, 'middle', 800 if i == len(rows)-1 else 600))
                body.append(_text(x, 189, r['label'], 12, anchor='middle'))
    else:
        rows = chart['rows']
        height, body = 42 + 36 * len(rows), []
        left, right = 156, 478
        lo, hi = _axis([r['value'] for r in rows])
        x = lambda v: left + (v-lo)/(hi-lo)*(right-left)
        zero = x(0)
        for i, r in enumerate(rows):
            y = 12 + i * 36
            body.append(_text(8, y+16, r['label'], 12, INK))
            body.append(f'<rect x="{left}" y="{y}" width="{right-left}" height="24" rx="3" fill="#f3f4f7"/>')
            if r['value'] is not None:
                xv = x(r['value'])
                body.append(f'<rect x="{min(zero,xv):.2f}" y="{y}" width="{abs(xv-zero):.2f}" height="24" rx="3" fill="{r["color"]}"/>')
            body.append(_text(610, y+16, r['display'] if r['value'] is not None else '미수신', 12, INK, 'end', 700))
        body.append(f'<line x1="{zero:.2f}" x2="{zero:.2f}" y1="8" y2="{height-30}" stroke="#657084"/>')
        body.append(_text(zero, height-12, '0', 10, anchor='middle'))
        body.append(_text(610, height-12, '단위 ' + chart['unit'], 10, anchor='end'))
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="620" height="{height}" viewBox="0 0 620 {height}"><g font-family="Pretendard, sans-serif">' + ''.join(body) + '</g></svg>'
