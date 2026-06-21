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
