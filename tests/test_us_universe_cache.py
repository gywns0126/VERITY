"""US 유니버스 캐시 → universe_builder 로더 검증 (네트워크 없음).

[[project_us_financials_sec_edgar]] 국장 parity — US 유니버스 ~150 static → sp1500 1500.
yfinance 실수집(build_us_universe_cache)은 [[feedback_real_call_over_llm_consensus]] 스모크 검증.
"""
from __future__ import annotations

import json

from api.collectors import universe_builder as ub


def test_static_cache_reads_provided_cache(tmp_path):
    # universe_us.json 캐시 존재 시 그대로 사용 (1순위).
    p = tmp_path / "universe_us.json"
    entries = [{"ticker": "AAPL", "name": "AAPL", "market": "US", "currency": "USD",
                "market_cap": 4_000_000_000_000, "avg_trading_value_30d": 14_000_000_000,
                "is_core": True, "is_managed": False, "is_suspended": False, "tier": "core", "source": "sp1500_yf"}]
    p.write_text(json.dumps(entries), encoding="utf-8")
    out = ub._load_us_static_cache(cache_path=p)
    assert len(out) == 1 and out[0]["ticker"] == "AAPL"
    assert out[0]["source"] == "sp1500_yf"


def test_static_cache_falls_to_sp1500(tmp_path):
    # 캐시 부재 → sp1500 1차 fallback (실 us_universe_sp1500.json 사용, 1500+ 엔트리).
    out = ub._load_us_static_cache(cache_path=tmp_path / "absent.json")
    assert len(out) > 500                       # sp1500 = 1500 (static ~150 아님)
    assert all(e["currency"] == "USD" for e in out[:50])
    assert any(e["source"] == "sp1500" for e in out)


def test_sp1500_universe_entry_shape():
    out = ub._load_sp1500_universe()
    assert len(out) > 500
    e = out[0]
    for k in ("ticker", "name", "market", "currency", "market_cap",
              "avg_trading_value_30d", "is_core", "tier", "source"):
        assert k in e
    assert e["market"] == "US" and e["currency"] == "USD"


def test_build_us_universe_caps_target():
    # build_us_universe(300) = 코어 + 상위, target 안에서 (국장 parity us_target=stage×0.6).
    uni = ub.build_us_universe(300)
    assert 0 < len(uni) <= 300 + 90            # 300 + 코어 여유
    assert all(e["currency"] == "USD" for e in uni)
