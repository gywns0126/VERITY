"""13F 보유 파싱 — 직접 주식만. 옵션·전환사채 혼입 차단.

2026-07-30 실사고. 파서가 putCall 태그만 걸러서 두 종류가 새어들었고, CUSIP 단위 합산 과정에서
주식·옵션·전환사채가 한 덩어리가 되어 보유량·평가액이 붕괴했다.

실측 원본 (Tudor CIK 923093, 2025-09-30 / 파일 분포 SH 3,273 · PRN 45):
    00971T101 SH  value 3,219,800  shares 42,500     Akamai / Equity Option
    00971T101 PRN value 71,437,900 shares 73,703,000 Akamai / Convertible Bond
  합산 shares=73,745,500 → 내재가 $0.97 (실제 주가 ~$87).
  그 결과 복제 수익률이 단일 분기 +425.56% 로 폭주(정상 분기 -5~+9%),
  4분기 누적이 +475.9% 로 표시됐다. 수정 후 해당 분기 -2.13% / 누적 +8.97%.
  대조군 Berkshire·Gates 는 수정 전후 완전 동일(회귀 0).

🚨 sshPrnamtType 은 SH(주식)만 유효. PRN 의 sshPrnamt 는 주식수가 아니라 **채권 원금**이다.
🚨 putCall 태그 없이 titleOfClass 에만 'Equity Option' 을 쓰는 filer 가 있다(Tudor).
"""
import xml.etree.ElementTree as ET

import api.collectors.sec_13f_collector as C


def _xml(rows):
    body = "".join(
        f"<infoTable><nameOfIssuer>{r.get('n','X')}</nameOfIssuer>"
        f"<titleOfClass>{r.get('cls','Equity')}</titleOfClass>"
        f"<cusip>{r['cusip']}</cusip><value>{r['v']}</value>"
        f"<shrsOrPrnAmt><sshPrnamt>{r['s']}</sshPrnamt>"
        f"<sshPrnamtType>{r.get('t','SH')}</sshPrnamtType></shrsOrPrnAmt>"
        + (f"<putCall>{r['pc']}</putCall>" if r.get("pc") else "")
        + "</infoTable>"
        for r in rows)
    return f"<informationTable>{body}</informationTable>"


def _parse(monkeypatch, rows):
    monkeypatch.setattr(C, "_find_infotable_url", lambda cik, acc: "http://x/t.xml")

    class _R:
        status_code = 200
        text = _xml(rows)

    monkeypatch.setattr(C.requests, "get", lambda *a, **k: _R())
    return C.parse_13f_holdings("acc", "923093")


def test_convertible_bond_excluded(monkeypatch):
    """PRN = 채권 원금. 주식수로 합산하면 내재가가 붕괴한다(Akamai 실사고 재현)."""
    out = _parse(monkeypatch, [
        {"cusip": "00971T101", "v": 3_700_000, "s": 42_500, "cls": "Equity"},
        {"cusip": "00971T101", "v": 71_437_900, "s": 73_703_000, "t": "PRN",
         "cls": "Convertible Bond"},
    ])
    assert len(out) == 1
    r = out[0]
    assert r["shares"] == 42_500
    assert 80 <= r["value_usd"] / r["shares"] <= 95      # 실제 주가대(≈$87)


def test_equity_option_excluded_without_putcall(monkeypatch):
    """putCall 태그가 없어도 titleOfClass 로 옵션을 거른다(Tudor 표기)."""
    out = _parse(monkeypatch, [
        {"cusip": "M2682V108", "v": 113_132_471, "s": 234_156, "cls": "Equity"},
        {"cusip": "M2682V108", "v": 4_444_980, "s": 9_200, "cls": "Equity Option"},
    ])
    assert len(out) == 1 and out[0]["shares"] == 234_156


def test_putcall_still_excluded(monkeypatch):
    """기존 putCall 필터 회귀 0."""
    out = _parse(monkeypatch, [
        {"cusip": "AAA", "v": 1000, "s": 10, "cls": "Equity"},
        {"cusip": "AAA", "v": 9999, "s": 999, "cls": "Equity", "pc": "Put"},
    ])
    assert out[0]["shares"] == 10


def test_warrant_and_note_excluded(monkeypatch):
    out = _parse(monkeypatch, [
        {"cusip": "BBB", "v": 500, "s": 5, "cls": "Common Stock"},
        {"cusip": "BBB", "v": 700, "s": 70, "cls": "Warrant"},
        {"cusip": "BBB", "v": 800, "s": 80, "cls": "Senior Note"},
    ])
    assert out[0]["shares"] == 5


def test_plain_equity_untouched(monkeypatch):
    """정상 주식 보유는 그대로 — 대조군 회귀 0."""
    out = _parse(monkeypatch, [
        {"cusip": "037833100", "v": 57_843_260_493, "s": 227_917_808, "cls": "COM"},
    ])
    assert len(out) == 1 and out[0]["value_usd"] == 57_843_260_493


def test_missing_prnamt_type_treated_as_shares(monkeypatch):
    """sshPrnamtType 미기재 filer 는 주식으로 취급(과도한 배제 방지)."""
    rows = [{"cusip": "CCC", "v": 1000, "s": 10, "cls": "Equity"}]
    xml = _xml(rows).replace("<sshPrnamtType>SH</sshPrnamtType>", "")
    monkeypatch.setattr(C, "_find_infotable_url", lambda cik, acc: "u")

    class _R:
        status_code = 200
        text = xml

    monkeypatch.setattr(C.requests, "get", lambda *a, **k: _R())
    out = C.parse_13f_holdings("a", "1")
    assert len(out) == 1 and out[0]["shares"] == 10
