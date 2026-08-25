"""us_smart_money_13f — QoQ change_type + CUSIP 캐시 파싱 검증 (네트워크 없음).

[[project_us_financials_sec_edgar]] (b) 13F 완전판. OpenFIGI/SEC 실호출은
[[feedback_real_call_over_llm_consensus]] 스모크 검증(037833100→AAPL 등).
"""
from __future__ import annotations

import json

from api.builders import us_smart_money_13f_public_builder as b


def _h(cusip, shares, value):
    return {"cusip": cusip, "issuer": cusip, "shares": shares, "value_usd": value}


def test_holdings_change_new_inc_dec_held():
    prev = [_h("A", 100, 1000), _h("B", 200, 2000), _h("C", 300, 3000)]
    curr = [_h("A", 150, 1500),   # INCREASED
            _h("B", 200, 2000),   # HELD (shares 동일)
            _h("C", 250, 2500),   # DECREASED
            _h("D", 400, 4000)]   # NEW
    out = {h["cusip"]: h for h in b._holdings_with_change(curr, prev)}
    assert out["A"]["change_type"] == "INCREASED" and out["A"]["value_change_usd"] == 500
    assert out["B"]["change_type"] == "HELD"
    assert out["C"]["change_type"] == "DECREASED" and out["C"]["value_change_usd"] == -500
    assert out["D"]["change_type"] == "NEW" and out["D"]["value_change_usd"] == 4000


def test_holdings_change_skips_no_cusip():
    out = b._holdings_with_change([_h("", 10, 100), _h("X", 5, 50)], [])
    assert [h["cusip"] for h in out] == ["X"]   # 빈 CUSIP 제외


def test_active_managers_exclude_index_funds():
    names = set(b.ACTIVE_MANAGERS.values())
    assert "Berkshire Hathaway" in names
    # 인덱스펀드 제외 (신호 희석·비용 회피)
    assert "Vanguard Group" not in names
    assert "BlackRock" not in names
    assert "State Street" not in names


def test_cusip_cache_roundtrip(tmp_path, monkeypatch):
    from api.collectors import cusip_resolver as cr
    p = tmp_path / "cusip.json"
    monkeypatch.setattr(cr, "CACHE_PATH", str(p))
    cr._save_cache({"037833100": "AAPL", "BADCUSIP0": None})
    cache = cr.load_cache()
    assert cache["037833100"] == "AAPL"
    assert cache["BADCUSIP0"] is None      # 영구 미스도 캐시(재조회 방지)


# ── held_since (연속 보유 시작) — 2026-08-24 검색창 축 ─────────────────────────

_QS = [  # 오래된 → 최근 (빌더 계약과 동일 방향) — 값 = 분기말 내재가(None = 산출 불가)
    ("2024-06-30", {"A": 10.0, "B": 20.0}),
    ("2024-09-30", {"A": 11.0, "B": 21.0, "C": None}),
    ("2024-12-31", {"A": 12.0, "C": 31.0}),          # B 청산
    ("2025-03-31", {"A": 13.0, "B": 23.0, "C": 33.0}),  # B 재매수
]


def test_held_since_consecutive_full_window_is_floor():
    since, q, floor, px = b._held_since(_QS, "A")
    assert since == "2024-06-30" and q == 4 and floor is True   # 창 상한 도달
    assert px == 10.0                     # 편입(최고령 연속) 분기말 내재가


def test_held_since_gap_resets_to_rebuy_quarter():
    # B 는 2024-12-31 에 끊겼다 — "언제부터 계속 보유" = 재매수 분기(2025-03-31)만.
    since, q, floor, px = b._held_since(_QS, "B")
    assert since == "2025-03-31" and q == 1 and floor is False
    assert px == 23.0                     # 재매수 분기말 가격 (2024 가격 아님)


def test_held_since_partial_window_not_floor():
    since, q, floor, px = b._held_since(_QS, "C")
    assert since == "2024-09-30" and q == 3 and floor is False
    assert px is None                     # 편입 분기 내재가 산출 불가 → None (가짜 0 금지)


def test_held_since_absent_and_empty():
    assert b._held_since(_QS, "ZZZ") == (None, 0, False, None)
    assert b._held_since([], "A") == (None, 0, False, None)


# ── 필터 재정의 (2026-08-25, PM 승인: sp1500 게이트 → ETF 제외만) ──────────────

def test_norm_us_ticker_class_share_formats():
    assert b._norm_us_ticker("BRK/B") == "BRK-B"   # Gates 재단 실측 누락 케이스
    assert b._norm_us_ticker("brk.b") == "BRK-B"
    assert b._norm_us_ticker(" TSM ") == "TSM"
    assert b._norm_us_ticker(None) == ""


def test_load_etf_set_contains_index_etfs():
    s = b._load_etf_set()
    # 인물축 상위25 실측에서 걸러져야 하는 ETF 들 (SPY·IVV·IEF)
    assert {"SPY", "IVV", "IEF"} <= s
    # 개별주는 ETF 집합에 없어야 한다
    assert "TSM" not in s and "BRK-B" not in s
