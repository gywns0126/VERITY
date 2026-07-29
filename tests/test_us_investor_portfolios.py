"""거장 인물 축 포트폴리오 빌더 — 공시 사실만, 수익률 랭킹 없음.

2026-07-30 신설 (PM 요청). 기존 us_smart_money_13f 는 종목 축("이 종목을 누가 들고 있나")이라
종목 상세에서만 쓰였다. 본 빌더는 같은 13F 원천을 인물/기관 축으로 뒤집는다.

🚨 이 테스트가 지키는 선 — 13F 는 분기말 보유를 최대 45일 뒤 제출(실측 Berkshire
reportDate 2026-03-31 / filingDate 2026-05-15)하고 롱 미국주식만 담긴다. 따라서 어떤 수치도
'그 사람의 수익률' 이 아니다. 랭킹 기준·caveat·필드명이 그 사실에서 벗어나면 실패시킨다.
"""
import api.builders.us_investor_portfolios_public_builder as B
from api.collectors.sec_13f_collector import MANAGER_PERSON


def _hold(cusip, shares, value):
    return {"cusip": cusip, "shares": shares, "value_usd": value}


def _wire(monkeypatch, curr, prev, report="2026-03-31", filed="2026-05-15"):
    monkeypatch.setattr(B, "ACTIVE_MANAGERS", {"1": "Berkshire Hathaway"})
    monkeypatch.setattr(B, "get_recent_13f_filings", lambda cik, n=2: [
        {"accession_no": "A", "report_date": report, "filed_at": filed},
        {"accession_no": "B", "report_date": "2025-12-31", "filed_at": "2026-02-14"},
    ])
    monkeypatch.setattr(B, "parse_13f_holdings",
                        lambda acc, cik: curr if acc == "A" else prev)
    monkeypatch.setattr(B, "resolve_cusips",
                        lambda cs: {c: f"T{c}" for c in cs if c != "X9"})


def test_investor_axis_shape(monkeypatch):
    _wire(monkeypatch, [_hold("C1", 100, 1000), _hold("C2", 50, 400)],
          [_hold("C1", 80, 700)])
    d = B.build()
    inv = d["investors"][0]
    assert inv["institution"] == "Berkshire Hathaway"
    assert inv["person"] == MANAGER_PERSON["Berkshire Hathaway"]
    assert inv["holdings_count"] == 2
    assert inv["disclosed_value_usd"] == 1400
    assert inv["top_holdings"][0]["ticker"] == "TC1"


def test_report_date_and_filed_at_both_exposed(monkeypatch):
    """보유 기준일 ≠ 제출일 — 둘 다 없으면 신선도 오독."""
    _wire(monkeypatch, [_hold("C1", 100, 1000)], [])
    inv = B.build()["investors"][0]
    assert inv["report_date"] == "2026-03-31"
    assert inv["filed_at"] == "2026-05-15"
    assert inv["prev_report_date"] == "2025-12-31"


def test_change_pct_is_not_labelled_return(monkeypatch):
    """🚨 수익률로 오독될 필드명·라벨 금지."""
    _wire(monkeypatch, [_hold("C1", 100, 1200)], [_hold("C1", 100, 1000)])
    d = B.build()
    inv = d["investors"][0]
    assert inv["disclosed_value_change_pct"] == 20.0
    assert "return" not in inv and "수익률" not in str(list(inv))
    meta = d["_meta"]
    assert "수익률 랭킹 아님" in meta["ranking_basis"]
    assert "수익률이 아니다" in meta["caveat"]
    assert "45일" in meta["caveat"] and "롱 미국주식만" in meta["caveat"]


def test_qoq_change_types(monkeypatch):
    _wire(monkeypatch,
          [_hold("C1", 120, 1200), _hold("C2", 50, 500), _hold("C3", 10, 100)],
          [_hold("C1", 100, 1000), _hold("C2", 80, 800)])
    inv = B.build()["investors"][0]
    by = {h["ticker"]: h["change_type"] for h in inv["top_holdings"]}
    assert by["TC1"] == "INCREASED" and by["TC2"] == "DECREASED" and by["TC3"] == "NEW"
    assert inv["new_count"] == 1 and inv["increased_count"] == 1 and inv["decreased_count"] == 1


def test_unresolved_ticker_counted_not_hidden(monkeypatch):
    """CUSIP 미해석을 침묵시키지 않음 — 건수 노출 + cusip 보존."""
    _wire(monkeypatch, [_hold("C1", 100, 1000), _hold("X9", 10, 100)], [])
    inv = B.build()["investors"][0]
    assert inv["unresolved_ticker_count"] == 1
    unresolved = [h for h in inv["top_holdings"] if h["ticker"] is None]
    assert unresolved and unresolved[0]["cusip"] == "X9"   # 링크아웃 가능하게 보존


def test_concentration_and_weights(monkeypatch):
    _wire(monkeypatch, [_hold("C1", 1, 800), _hold("C2", 1, 200)], [])
    inv = B.build()["investors"][0]
    assert inv["top10_concentration_pct"] == 100.0
    assert inv["top_holdings"][0]["weight_pct"] == 80.0


def test_one_manager_failure_does_not_kill_others(monkeypatch):
    monkeypatch.setattr(B, "ACTIVE_MANAGERS", {"1": "Berkshire Hathaway", "2": "ARK Invest"})

    def _filings(cik, n=2):
        if cik == "2":
            raise RuntimeError("EDGAR 503")
        return [{"accession_no": "A", "report_date": "2026-03-31", "filed_at": "2026-05-15"}]

    monkeypatch.setattr(B, "get_recent_13f_filings", _filings)
    monkeypatch.setattr(B, "parse_13f_holdings", lambda acc, cik: [_hold("C1", 1, 100)])
    monkeypatch.setattr(B, "resolve_cusips", lambda cs: {c: "TC1" for c in cs})
    d = B.build()
    assert len(d["investors"]) == 1
    assert any("ARK Invest" in e for e in d["_meta"]["errors"])


def test_sorted_by_disclosed_value(monkeypatch):
    monkeypatch.setattr(B, "ACTIVE_MANAGERS", {"1": "Berkshire Hathaway", "2": "ARK Invest"})
    monkeypatch.setattr(B, "get_recent_13f_filings", lambda cik, n=2: [
        {"accession_no": cik, "report_date": "2026-03-31", "filed_at": "2026-05-15"}])
    monkeypatch.setattr(B, "parse_13f_holdings",
                        lambda acc, cik: [_hold("C1", 1, 100 if cik == "1" else 900)])
    monkeypatch.setattr(B, "resolve_cusips", lambda cs: {c: "TC1" for c in cs})
    d = B.build()
    assert [i["institution"] for i in d["investors"]] == ["ARK Invest", "Berkshire Hathaway"]
