"""us_filing_probe — SEC 직조회 회귀 테스트 (네트워크 0).

2026-08-12 신설. SWMR(Swarmer) 조회에서 만든 모듈이고, **구축 중에 실제로 낸 버그 2종**을
고정하는 것이 이 파일의 목적이다.

  ① 신선도 오염 — 회사가 회계 태그를 갈아타면 옛 태그의 **마지막 값**이 최신으로 둔갑한다.
     RCAT 실측: 현금을 `CashAndCashEquivalentsAtCarryingValue` 로 조회하니 2021-07-31 값이
     나왔고(그 뒤로는 `CashCashEquivalentsRestrictedCash...` 사용), 그 5년 전 잔고로
     런웨이를 계산해 "0.8분기" 라는 거짓 경보가 만들어졌다. 초록불 + 그럴듯한 값이라
     사람 눈으로는 안 걸린다 ([[feedback_api_row_limit_truncation_stale_value]]).
  ② 경보 잡음 — 오래 상장된 회사의 옛 424B4·소진된 ATM 까지 올리면 경보가 무의미해진다.
     RCAT 2021-06-14 락업, ONDS 2022-03-22 유동성 라인이 실제로 올라왔다.

세 번째 축은 CLI import 경로다 — `ticker_facts` 는 스크립트 직접 실행 시 최상위 모듈로
로드되므로 `api.intelligence.*` 절대 import 만 두면 **CLI 에서만 섹션이 조용히 빠진다**.
그 배선은 `test_ticker_facts_wiring` 이 지킨다.
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.intelligence import us_filing_probe as P  # noqa: E402


def _facts(tags):
    """companyfacts 최소 골격. tags = {(ns, tag, unit): [rec, ...]}"""
    out = {"facts": {"us-gaap": {}, "dei": {}}}
    for (ns, tag, unit), recs in tags.items():
        out["facts"].setdefault(ns, {})[tag] = {"units": {unit: recs}}
    return out


# ── ① 신선도 오염 ──────────────────────────────────────────────────────────

def test_stale_tag_is_rejected():
    """옛 태그의 마지막 값은 채택되지 않는다 — RCAT 현금 2021년 사고 고정."""
    f = _facts({
        ("us-gaap", "NetIncomeLoss", "USD"): [{"end": "2026-06-30", "val": -1000}],
        ("us-gaap", "CashAndCashEquivalentsAtCarryingValue", "USD"): [
            {"end": "2021-07-31", "val": 66_118_581},   # 5년 전 = 태그 교체 전 마지막 값
        ],
    })
    anchor = P._anchor_end(f)
    assert anchor == "2026-06-30"
    stale = P._latest(f, "us-gaap", "CashAndCashEquivalentsAtCarryingValue", "USD")
    assert stale["val"] == 66_118_581          # 원본 조회는 값을 준다
    assert P._fresh(stale, anchor) is None      # 신선도 게이트가 막는다


def test_fresh_first_prefers_current_tag():
    """태그를 갈아탄 회사는 신선한 대체 태그를 골라야 한다."""
    f = _facts({
        ("us-gaap", "NetIncomeLoss", "USD"): [{"end": "2026-06-30", "val": -1}],
        ("us-gaap", "CashAndCashEquivalentsAtCarryingValue", "USD"): [
            {"end": "2021-07-31", "val": 66_118_581}],
        ("us-gaap", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "USD"): [
            {"end": "2026-06-30", "val": 325_553_000}],
    })
    got = P._fresh_first(f, P._CASH_TAGS, "USD", P._anchor_end(f))
    assert got is not None and got["val"] == 325_553_000


def test_runway_requires_matching_period_end():
    """현금과 영업현금흐름의 기간말이 어긋나면 런웨이를 내지 않는다."""
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=90)).isoformat()
    f = _facts({
        ("us-gaap", "NetIncomeLoss", "USD"): [{"end": end, "val": -1}],
        ("us-gaap", "CashAndCashEquivalentsAtCarryingValue", "USD"): [
            {"end": end, "val": 10_000_000}],
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivities", "USD"): [
            {"end": end, "start": start, "val": -2_000_000}],
    })
    fin = (P._alerts_block("0000000001", [], f) or {}).get("재무 요약 (XBRL)") or {}
    assert "런웨이(단순)" in fin and "5.0분기" in fin["런웨이(단순)"]

    # 기간말 불일치 → 산출 금지
    f2 = _facts({
        ("us-gaap", "NetIncomeLoss", "USD"): [{"end": end, "val": -1}],
        ("us-gaap", "CashAndCashEquivalentsAtCarryingValue", "USD"): [
            {"end": end, "val": 10_000_000}],
        ("us-gaap", "NetCashProvidedByUsedInOperatingActivities", "USD"): [
            {"end": (date.today() - timedelta(days=95)).isoformat(),
             "start": (date.today() - timedelta(days=185)).isoformat(), "val": -2_000_000}],
    })
    fin2 = (P._alerts_block("0000000001", [], f2) or {}).get("재무 요약 (XBRL)") or {}
    assert "런웨이(단순)" not in fin2
    assert "기간말 불일치" in (fin2.get("런웨이") or "")


# ── ② 경보 잡음 ────────────────────────────────────────────────────────────

def _row(d, form, items="", acc="0001-00-000001", doc="x.htm"):
    return {"filingDate": d, "form": form, "accessionNumber": acc,
            "primaryDocument": doc, "items": items, "reportDate": ""}


def test_old_ipo_emits_no_lockup_alert(monkeypatch):
    """상장 500일 초과 종목의 옛 424B4 로 락업 경보를 내지 않는다 — RCAT 2021 사고."""
    monkeypatch.setattr(P, "_doc_text", lambda *a, **k: None)
    rows = [_row("2021-04-30", "424B4")]
    al = P._alerts_block("0000000001", rows, None) or {}
    assert "락업 만기(추정)" not in al and "상장" not in al


def test_recent_ipo_emits_lockup_alert(monkeypatch):
    """상장 1년 미만이면 락업 만기를 낸다. 본문에 일수가 있으면 그걸 우선한다."""
    monkeypatch.setattr(P, "_doc_text",
                        lambda *a, **k: "for a period of 180 days from the date of this prospectus")
    ipo = (date.today() - timedelta(days=150)).isoformat()
    al = P._alerts_block("0000000001", [_row(ipo, "424B4")], None) or {}
    assert "424B4 본문 파싱" in al["락업 만기(추정)"]
    expected = (date.fromisoformat(ipo) + timedelta(days=180)).isoformat()
    assert expected in al["락업 만기(추정)"]


def test_old_equity_line_is_not_alerted(monkeypatch):
    """400일 넘은 자금조달 라인은 경보 대상이 아니다 — ONDS 2022 사고."""
    monkeypatch.setattr(P, "_doc_text", lambda *a, **k: "common stock purchase agreement")
    rows = [_row("2022-03-22", "8-K", items="1.01"), _row("2022-03-22", "424B5")]
    al = P._alerts_block("0000000001", rows, None) or {}
    assert "자금조달 라인(ATM·유동성 라인)" not in al


def test_recent_equity_line_is_detected(monkeypatch):
    """8-K item 1.01 + 근접 등록서류 + 본문 문구 = 유동성 라인 탐지."""
    monkeypatch.setattr(
        P, "_doc_text",
        lambda *a, **k: ("the Company entered into a Common Stock Purchase Agreement ... "
                         "the right to sell up to 3,000,000 shares of its common stock"))
    d0 = (date.today() - timedelta(days=40)).isoformat()
    d1 = (date.today() - timedelta(days=35)).isoformat()
    rows = [_row(d0, "8-K", items="1.01,9.01"), _row(d0, "S-1"), _row(d1, "424B3")]
    al = P._alerts_block("0000000001", rows, None) or {}
    hits = al.get("자금조달 라인(ATM·유동성 라인)") or []
    assert hits and "3,000,000주" in hits[0]


def test_plain_8k_without_registration_is_not_alerted(monkeypatch):
    """등록서류가 따라붙지 않는 단순 계약 8-K 는 희석 경보가 아니다 (오탐 방지)."""
    monkeypatch.setattr(P, "_doc_text", lambda *a, **k: "common stock purchase agreement")
    d0 = (date.today() - timedelta(days=40)).isoformat()
    al = P._alerts_block("0000000001", [_row(d0, "8-K", items="1.01")], None) or {}
    assert "자금조달 라인(ATM·유동성 라인)" not in al


# ── 완전희석 사다리 ────────────────────────────────────────────────────────

def test_diluted_ladder_and_market_cap():
    """발행주식만으로 시총을 계산하던 결손의 고정 — SWMR 실측값 사용."""
    f = _facts({
        ("us-gaap", "CommonStockSharesOutstanding", "shares"): [
            {"end": "2026-03-31", "val": 10_798_722}],
        ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding", "shares"): [
            {"end": "2026-03-31", "val": 16_064_920}],
        ("us-gaap",
         "AntidilutiveSecuritiesExcludedFromComputationOfEarningsPerShareAmount", "shares"): [
            {"end": "2026-03-31", "val": 5_810_144}],
    })
    cap = P._capital_block(f)
    assert cap["_basic"] == 10_798_722
    assert cap["_diluted_max"] == 21_875_064
    lad = P.market_cap_ladder(cap, 39.47)
    assert lad == ["발행주식 기준: $426M", "완전희석 기준: $863M"]
    # 요점 = 두 값이 2배 넘게 벌어진다는 것. 하나만 쓰면 판단이 뒤집힌다.
    assert cap["_diluted_max"] / cap["_basic"] > 2.0


def test_market_cap_ladder_needs_a_real_price():
    """가격이 없으면 시총을 만들지 않는다 — 지어낸 가격 금지 규율."""
    assert P.market_cap_ladder({"_basic": 100, "_diluted_max": 200}, 0) is None
    assert P.market_cap_ladder(None, 10.0) is None


# ── 공시 이력 ──────────────────────────────────────────────────────────────

def test_filings_include_more_than_8k():
    """10-Q/10-K/S-1/424B* 가 조인에 들어와야 한다 — 8-K 전용 결손의 직접 수정."""
    assert {"10-Q", "10-K", "S-1", "424B3", "424B4", "DEF 14A"} <= set(P.FORMS_OF_INTEREST)
    d = date.today().isoformat()
    rows = [_row(d, "10-Q"), _row(d, "424B4"), _row(d, "8-K", items="2.02"),
            _row(d, "NT 10-Q")]
    blk = P._filings_block("0000000001", rows)
    forms = {x["폼"] for x in blk["공시"]}
    assert {"10-Q", "424B4", "8-K"} <= forms
    assert "NT 10-Q" not in forms          # 관심 폼 밖은 제외
    assert "2.02 실적 발표" in [x.get("항목") for x in blk["공시"] if x["폼"] == "8-K"][0]


def test_truncation_is_reported():
    """상한으로 자를 때 '미표시 N' 을 신고한다 — 렌더 단계 조용한 누락 방지."""
    d = date.today().isoformat()
    rows = [_row(d, "8-K", items="8.01", acc=f"0001-00-{i:06d}") for i in range(P.MAX_FILINGS + 7)]
    blk = P._filings_block("0000000001", rows)
    assert blk["건수"] == P.MAX_FILINGS + 7
    assert len(blk["공시"]) == P.MAX_FILINGS
    assert blk["미표시"] == 7


def test_zero_filings_is_asserted_not_guessed():
    """0건은 '확정' 이다 — 추정으로 흐리지 않는다 (DART 직조회와 같은 규율)."""
    blk = P._filings_block("0000000001", [_row("2000-01-01", "8-K")])
    assert blk["건수"] == 0
    assert "확정" in blk["확정"]


def test_kr_ticker_is_not_probed():
    """KR 6자리는 이 모듈 대상이 아니다 (KIS·DART 가 담당)."""
    assert P._cik("005930") is None
    assert P.probe("005930") is None


# ── ③ CLI import 배선 ──────────────────────────────────────────────────────

def test_ticker_facts_wiring():
    """ticker_facts 가 상대·절대 양쪽 import 로 probe 를 잡아야 한다.

    절대 import 하나만 두었을 때 `python api/intelligence/operator_ask.py` 경로에서
    ticker_facts 가 최상위 모듈로 로드돼 섹션이 통째로 빠졌다(2026-08-12 실측).
    """
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "api", "intelligence", "ticker_facts.py")
    with open(src, encoding="utf-8") as fh:
        code = fh.read()
    assert "from . import us_filing_probe" in code
    assert "import us_filing_probe" in code
    assert "SEC 공시·자본구조" in code


def test_sync_script_carries_the_module():
    """Vercel 복제본 목록에 등재돼야 한다 — 누락 시 사이트에서만 조용히 실패한다."""
    sh = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "scripts", "sync_operator_ask.sh")
    with open(sh, encoding="utf-8") as fh:
        assert "us_filing_probe.py" in fh.read()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
