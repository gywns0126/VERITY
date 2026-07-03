"""market_flow frgn 파서 회귀 가드.

2026-07-04 사고: 구 class="num" 파서가 네이버 frgn 개편 후 매치 0 → 전 종목 flow 0/중립
silent 반환 (브레인 flow 신호 死). 파서가 다시 0행이 되면 여기서 잡는다.
fixture = 실 frgn 데이터 행 구조 (class="tah" 셀, 2026-07-04 실호출 캡처 축약).
"""
from api.collectors.market_flow import _parse_flow_table

_ROW = """
<tr>
<td class="tah p10 gray03">{date}</td>
<td class="tah p11">{close}</td>
<td class="tah p11">1,000</td>
<td class="tah p11"><span>+1.00%</span></td>
<td class="tah p11">31,498,600</td>
<td class="tah p11">{inst}</td>
<td class="tah p11">{fgn}</td>
<td class="tah p11">2,732,503,622</td>
<td class="tah p11">46.74%</td>
</tr>
"""

_HTML = "<table>" + _ROW.format(date="2026.07.03", close="309,500", inst="+4,369,649", fgn="-1,365,575") \
    + _ROW.format(date="2026.07.02", close="286,000", inst="-2,166,435", fgn="-5,007,053") + "</table>"


def test_parse_flow_table_extracts_rows_newest_first():
    rows = _parse_flow_table(_HTML)
    assert len(rows) == 2
    assert rows[0] == {"foreign": -1365575, "inst": 4369649, "ratio": 46.74}
    assert rows[1]["foreign"] == -5007053 and rows[1]["inst"] == -2166435


def test_parse_flow_table_empty_on_structure_change():
    # 구조 붕괴(=구 사고 재현) 시 조용히 0행 — 소비부 폴백/중립 경로 유지 확인용
    assert _parse_flow_table('<td class="num">123</td>') == []
