"""us_insider_trades_public_builder — Form4 파싱/회전 검증 (네트워크 없음).

[[project_us_financials_sec_edgar]] (b) US Form4 내부자. SEC 실호출은
[[feedback_real_call_over_llm_consensus]] 로 스모크 검증함 (여기선 파싱 계약만).
"""
from __future__ import annotations

import json

from api.builders import us_insider_trades_public_builder as b


# SEC Form4 ownershipDocument 재현 — 비파생 매수(P/A) 2건 + 매도(S/D) 1건.
FORM4_BUY = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer><issuerTradingSymbol>ACME</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Doe Jane</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>0</isDirector><isOfficer>1</isOfficer>
      <isTenPercentOwner>0</isTenPercentOwner><officerTitle>Chief Executive Officer</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-06-10</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-06-12</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>500</value></transactionShares>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""

FORM4_SELL = """<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Roe Richard</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector><isOfficer>0</isOfficer><isTenPercentOwner>0</isTenPercentOwner>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-05-30</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>2000</value></transactionShares>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""

# 파생만(옵션) — 비파생 0 → None (방향 신호 약함).
FORM4_DERIV_ONLY = """<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner><reportingOwnerId><rptOwnerName>X Y</rptOwnerName></reportingOwnerId></reportingOwner>
  <derivativeTable><derivativeTransaction>
    <transactionCoding><transactionCode>M</transactionCode></transactionCoding>
  </derivativeTransaction></derivativeTable>
</ownershipDocument>"""


def test_parse_buy_officer():
    person, position, net, code, last_date = b._parse_form4(FORM4_BUY)
    assert person == "Doe Jane"
    assert position == "Chief Executive Officer"   # isOfficer + officerTitle
    assert net == 1500.0                            # +1000 +500 (A 취득)
    assert code == "P"                              # 공개매수
    assert last_date == "2026-06-12"                # 최신 거래일


def test_parse_sell_director():
    person, position, net, code, last_date = b._parse_form4(FORM4_SELL)
    assert person == "Roe Richard"
    assert position == "Director"                   # isDirector
    assert net == -2000.0                           # 처분(D)
    assert code == "S"


def test_parse_derivative_only_returns_none():
    assert b._parse_form4(FORM4_DERIV_ONLY) is None  # 비파생 0


def test_parse_malformed_returns_none():
    assert b._parse_form4("<not-xml") is None


def test_ordered_universe_priority_first(tmp_path, monkeypatch):
    # rec 우선풀(portfolio US)이 항상 앞 + 나머지 회전.
    uni = tmp_path / "uni.json"
    uni.write_text(json.dumps({"tickers": ["AAA", "MSFT", "BBB", "CCC"]}), encoding="utf-8")
    pf = tmp_path / "pf.json"
    pf.write_text(json.dumps({"recommendations": [{"ticker": "MSFT", "currency": "USD"}]}), encoding="utf-8")
    # _universe() 는 COMBINED_PATH(소형주 5,313 확장, 2026-07-09) 를 SP1500_PATH 보다 먼저 읽음 →
    # mock 유니버스가 무시돼 실 5,313종목 누출되던 회귀. COMBINED_PATH 도 mock 으로 지정.
    monkeypatch.setattr(b, "COMBINED_PATH", str(uni))
    monkeypatch.setattr(b, "SP1500_PATH", str(uni))
    monkeypatch.setattr(b, "PORTFOLIO_PATH", str(pf))
    order = b._ordered_universe()
    assert order[0] == "MSFT"          # 우선풀 먼저
    assert set(order) == {"AAA", "MSFT", "BBB", "CCC"}  # 전 종목 포함
