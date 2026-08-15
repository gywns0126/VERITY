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

# 파생만(옵션) — 비파생 0 → NO_MARKET_TX (방향 신호 약함).
FORM4_DERIV_ONLY = """<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner><reportingOwnerId><rptOwnerName>X Y</rptOwnerName></reportingOwnerId></reportingOwner>
  <derivativeTable><derivativeTransaction>
    <transactionCoding><transactionCode>M</transactionCode></transactionCoding>
  </derivativeTransaction></derivativeTable>
</ownershipDocument>"""

# 🚨 머스크 SPCX 2026-06-15 실제 구조의 축약 — 전환(C) 3.16억 + 인수대가 취득(A) 5.11억
#    + 실제 시장매도(S) 11,390. 옛 구현은 이걸 전부 합산해 net +801,923,260 을 만들고,
#    codes 에 S 가 섞였다는 이유로 대표코드를 "S" 로 찍어 "머스크가 8억주를 팔았다" 가 됐다.
FORM4_MUSK_SHAPED = """<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Musk Elon</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector><isOfficer>1</isOfficer>
      <officerTitle>CEO, CTO &amp; Chairman</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-02-02</value></transactionDate>
      <transactionCoding><transactionCode>A</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>511289725</value></transactionShares>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-06-15</value></transactionDate>
      <transactionCoding><transactionCode>C</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>282614850</value></transactionShares>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-04-02</value></transactionDate>
      <transactionCoding><transactionCode>G</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>480</value></transactionShares>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-04-02</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>11390</value></transactionShares>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""

# 부여·세금원천만 — 정상 파싱이지만 매매 신호 0. None(파싱 실패)과 구분돼야 한다.
FORM4_GRANT_ONLY = """<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner><reportingOwnerId><rptOwnerName>Grantee A</rptOwnerName></reportingOwnerId></reportingOwner>
  <nonDerivativeTable><nonDerivativeTransaction>
    <transactionDate><value>2026-06-17</value></transactionDate>
    <transactionCoding><transactionCode>F</transactionCode></transactionCoding>
    <transactionAmounts>
      <transactionShares><value>2617</value></transactionShares>
      <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
    </transactionAmounts>
  </nonDerivativeTransaction></nonDerivativeTable>
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


def test_parse_derivative_only_is_no_market_tx():
    """비파생 0 — 정상 파싱이므로 '파싱 실패(None)' 와 구분한다."""
    assert b._parse_form4(FORM4_DERIV_ONLY) is b.NO_MARKET_TX


def test_parse_malformed_returns_none():
    assert b._parse_form4("<not-xml") is None


def test_conversions_and_grants_are_not_trades():
    """🚨 전환(C)·부여(A)·증여(G)를 매매로 합산하지 않는다 — SPCX 2026-08-15 사고.

    옛 구현은 비파생 거래를 코드 무관하게 전부 합산해 머스크 Form 4 하나에서
    net_change +801,923,260 을 만들었고, codes 에 S 가 하나 섞였다는 이유로
    대표코드를 "S"(매도) 로 찍었다. 결과 = "머스크가 8억주를 팔았다".
    sell_n 0 인데 code S 라는 자기모순이 이미 신호였다.
    실제 시장 거래는 11,390주 매도 하나뿐이다.
    """
    person, position, net, code, last_date = b._parse_form4(FORM4_MUSK_SHAPED)
    assert person == "Musk Elon"
    assert net == -11390.0        # P/S 만 합산 (A 511M · C 283M · G 480 은 제외)
    assert code == "S"            # 순액 부호에서 끌어온다
    assert last_date == "2026-06-15"


def test_representative_code_follows_net_sign():
    """대표코드는 codes 목록이 아니라 순액 부호를 따른다 (순매수인데 'S' 금지)."""
    xml = FORM4_MUSK_SHAPED.replace(
        "<transactionShares><value>11390</value></transactionShares>\n"
        "        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>",
        "<transactionShares><value>11390</value></transactionShares>\n"
        "        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>")
    _, _, net, code, _ = b._parse_form4(xml)
    assert net == 11390.0 and code == "P"


def test_issuer_symbol_is_extracted_for_attribution_check():
    """🚨 Form 4 의 발행사를 뽑아 귀속을 대조한다 — VWAV→SVRE 오귀속 차단.

    EDGAR 는 Form 4 를 발행사 CIK 와 보고자 CIK **양쪽에** 색인한다. 이 빌더는
    티커→CIK→submissions 로 수집하므로, 어떤 회사가 **남의 내부자로서** 낸 공시까지
    자기 종목 거래로 끌어온다. 실측: VWAV(발행주식 2,538만주) 엔트리에 "35.4억주 매수(P)"
    가 실려 net +244억주가 나왔고, 원문 발행사는 SVRE(SaverOne)였다. 발행주식의 140배가
    공개 '내부자 순매수' 탭 1위에 있었다. 코드가 진짜 P 라서 매매 필터로는 안 걸린다 —
    **귀속 대조가 유일한 방어다.**
    """
    other = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0001894693</issuerCik>
    <issuerName>SaverOne 2014 Ltd.</issuerName>
    <issuerTradingSymbol>SVRE</issuerTradingSymbol>
  </issuer>
  <reportingOwner><reportingOwnerId><rptOwnerName>VisionWave Holdings, Inc.</rptOwnerName></reportingOwnerId></reportingOwner>
  <nonDerivativeTable><nonDerivativeTransaction>
    <transactionDate><value>2026-03-30</value></transactionDate>
    <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
    <transactionAmounts>
      <transactionShares><value>3545596800</value></transactionShares>
      <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
    </transactionAmounts>
  </nonDerivativeTransaction></nonDerivativeTable>
</ownershipDocument>"""
    cik, sym = b._form4_issuer(other)
    assert (cik, sym) == ("1894693", "SVRE")
    # 매매 파싱 자체는 성공한다 — 그래서 귀속 대조 없이는 절대 안 걸린다.
    assert b._parse_form4(other)[2] == 3545596800.0
    assert b._form4_issuer("<not xml") == ("", "")


def test_grant_only_is_no_market_tx_not_parse_failure():
    """부여·세금원천만 있는 Form 4 는 '매매 없음' 이지 '파싱 실패' 가 아니다.

    둘을 뭉치면 main() 의 carry-forward 분기가 옛 엔트리를 영구 보존한다 —
    파서를 고쳐도 산출물이 안 바뀌는 경로다.
    """
    assert b._parse_form4(FORM4_GRANT_ONLY) is b.NO_MARKET_TX
    assert b._parse_form4(FORM4_GRANT_ONLY) is not None


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
