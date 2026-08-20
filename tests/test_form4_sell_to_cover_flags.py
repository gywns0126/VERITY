"""Form 4 부가 사실 — sell_to_cover(3신호) · plan_10b51 (2026-08-21).

배경 실측 (2026-08-20 MRNA):
    조인이 CEO Bancel 을 "급등 13일 전 499,246주 매도"(code S) 로 보여줬는데,
    원문은 8/10 만료 옵션 **강제 행사의 sell-to-cover** 였고 보유는 **순증 +252,469** 였다.
    Form 4 에 sell-to-cover 전용 코드가 없어 재량 매도와 둘 다 `S` 로 찍힌다.

설계 근거 (퍼플렉시티 2026-08-21, PM 수신):
    벤더 실무는 ① M+S 시간적 결합 ② 각주 텍스트 ③ 보유 순증 **셋을 병행**하며
    단일 업계 표준은 없다(Bloomberg·FactSet 로직 비공개). → **3신호 중 ≥2** 를 채택.

🚨 이 파일이 지키는 두 경계
    1. `_parse_form4` 의 P/S 합산 규칙 **불변** — SPCX 머스크 "8억주 매도" 수정분 보호.
       플래그는 별도 순수 함수라 판정에 관여하지 않는다.
    2. Cohen–Malloy–Pomorski 의 routine/opportunistic 과 **섞지 않는다** —
       그쪽은 캘린더 패턴만 보는 별개 축이다.
"""
from __future__ import annotations

from api.builders import us_insider_trades_public_builder as b


def _doc(txns: str, footnotes: str = "", aff: str = "") -> str:
    return f"""<?xml version="1.0"?>
<ownershipDocument>
  <issuer><issuerTradingSymbol>ACME</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Doe Jane</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>0</isDirector><isOfficer>1</isOfficer>
      <isTenPercentOwner>0</isTenPercentOwner><officerTitle>CEO</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  {aff}
  <nonDerivativeTable>{txns}</nonDerivativeTable>
  {footnotes}
</ownershipDocument>"""


def _tx(code: str, date: str, shares: float, ad: str) -> str:
    return f"""<nonDerivativeTransaction>
      <transactionDate><value>{date}</value></transactionDate>
      <transactionCoding><transactionCode>{code}</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>{shares}</value></transactionShares>
        <transactionAcquiredDisposedCode><value>{ad}</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </nonDerivativeTransaction>"""


# MRNA 형태 — M 751,715 취득 / S 499,246 처분 / 각주 "solely to cover..." / 10b5-1
MRNA_SHAPED = _doc(
    _tx("M", "2026-08-05", 499246, "A")
    + _tx("S", "2026-08-05", 499246, "D")
    + _tx("M", "2026-08-06", 252469, "A"),
    footnotes="<footnote id=\"F1\">The reported transactions were effected pursuant to a "
              "Rule 10b5-1 trading plan adopted on May 4, 2026. The Reporting Person "
              "exercised in full two stock option awards that were scheduled to expire. "
              "the Reporting Person sold 499,246 shares acquired upon exercise solely to "
              "cover the exercise price, applicable withholding taxes, and related "
              "transaction costs, and retained all remaining shares.</footnote>",
    aff="<aff10b5One>1</aff10b5One>",
)

# 진짜 재량 매도 — S 단독, 각주 없음, 순감소
DISCRETIONARY = _doc(_tx("S", "2026-05-30", 2000, "D"))


def test_mrna_shaped_fires_all_three_signals():
    f = b._form4_flags(MRNA_SHAPED)
    assert f["sell_to_cover"] is True
    assert set(f["stc_signals"].split("+")) == {"pairing", "footnote", "net_increase"}
    assert f["plan_10b51"] is True
    assert f["plan_adopted"] == "May 4, 2026"


def test_discretionary_sale_is_not_flagged():
    """🚨 이게 뒤집히면 진짜 매도를 sell-to-cover 로 덮어버린다."""
    f = b._form4_flags(DISCRETIONARY)
    assert f.get("sell_to_cover") is False
    assert f["stc_signals"] == "none"


def test_single_signal_is_not_enough():
    """각주만 있고 M 도 없고 순감소면 1신호 — ≥2 규칙에 걸려 False."""
    only_footnote = _doc(
        _tx("S", "2026-05-30", 2000, "D"),
        footnotes="<footnote id=\"F1\">shares sold to cover tax withholding</footnote>",
    )
    f = b._form4_flags(only_footnote)
    assert f["stc_signals"] == "footnote"
    assert f["sell_to_cover"] is False


def test_pairing_plus_net_increase_without_footnote():
    """각주가 비어도 M+S 결합 + 순증이면 2신호 → 채택."""
    f = b._form4_flags(
        _doc(_tx("M", "2026-08-05", 1000, "A") + _tx("S", "2026-08-05", 400, "D"))
    )
    assert set(f["stc_signals"].split("+")) == {"pairing", "net_increase"}
    assert f["sell_to_cover"] is True


def test_distant_m_does_not_pair():
    """M 이 한 달 전이면 결합 신호가 아니다 — 우연한 동시 발생 방지."""
    f = b._form4_flags(
        _doc(_tx("M", "2026-07-01", 1000, "A") + _tx("S", "2026-08-05", 1200, "D"))
    )
    assert "pairing" not in f["stc_signals"]


def test_no_sale_yields_no_stc_verdict():
    """매수만 있으면 판별 대상이 아니다 — 억지 판정하지 않는다."""
    f = b._form4_flags(_doc(_tx("P", "2026-06-10", 1000, "A")))
    assert "sell_to_cover" not in f
    assert "stc_signals" not in f


def test_plan_checkbox_false_is_reported():
    f = b._form4_flags(_doc(_tx("S", "2026-05-30", 100, "D"),
                            aff="<aff10b5One>0</aff10b5One>"))
    assert f["plan_10b51"] is False
    assert "plan_adopted" not in f


def test_malformed_xml_returns_empty_not_crash():
    assert b._form4_flags("<not-xml") == {}


# ── 경계 보호 ────────────────────────────────────────────────
def test_parse_form4_signature_and_ps_rule_unchanged():
    """🚨 P/S 합산 규칙과 5-튜플 시그니처는 불변이어야 한다(SPCX 수정분 보호)."""
    parsed = b._parse_form4(MRNA_SHAPED)
    assert isinstance(parsed, tuple) and len(parsed) == 5
    person, position, net, code, last_date = parsed
    # M(취득) 은 합산에서 제외되고 S 만 잡힌다 — 이게 SPCX 수정의 핵심이다
    assert net == -499246.0
    assert code == "S"


def test_flags_do_not_alter_net_or_code():
    """플래그는 사실을 더할 뿐 판정을 바꾸지 않는다."""
    before = b._parse_form4(MRNA_SHAPED)
    b._form4_flags(MRNA_SHAPED)
    assert b._parse_form4(MRNA_SHAPED) == before


def test_source_keeps_cmp_axis_separate():
    """CMP routine/opportunistic 을 이 함수에 섞지 않았는지 — 경계 문서화 유지."""
    import inspect
    src = inspect.getsource(b)
    assert "routine" not in b._form4_flags.__doc__.lower()
    assert "Cohen" in src, "CMP 와 섞지 말라는 경계 주석이 사라졌다"
