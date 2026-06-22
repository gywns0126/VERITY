"""us_analyst_consensus — 컨센서스 파싱 검증 (네트워크 없음).

[[project_us_financials_sec_edgar]] (b) us_flow 컨센서스. yfinance 실호출은
[[feedback_real_call_over_llm_consensus]] 스모크 검증(AMZN 63명 upside 28.1%).
"""
from __future__ import annotations

from api.builders import us_analyst_consensus_public_builder as b


def test_build_consensus_full():
    info = {
        "numberOfAnalystOpinions": 42, "targetMeanPrice": 314.0, "recommendationKey": "buy",
        "recommendationMean": 1.98, "targetHighPrice": 400.0, "targetLowPrice": 215.0,
        "currentPrice": 298.0,
    }
    c = b._build_consensus("AAPL", info, {"strongBuy": 6, "buy": 23, "hold": 15})
    assert c["rec_key"] == "buy" and c["num_analysts"] == 42
    assert c["target_mean"] == 314.0
    assert c["upside_pct"] == round((314.0 - 298.0) / 298.0 * 100, 1)  # 5.4
    assert c["counts"]["buy"] == 23


def test_build_consensus_no_coverage_returns_none():
    # 애널리스트 커버리지 전무 → None (소형주 등).
    assert b._build_consensus("XYZ", {"currentPrice": 10.0}, {}) is None


def test_build_consensus_upside_none_without_price():
    info = {"numberOfAnalystOpinions": 5, "targetMeanPrice": 50.0, "recommendationKey": "hold"}
    c = b._build_consensus("AAA", info, {})
    assert c is not None
    assert c["upside_pct"] is None   # current_price 부재 → upside 계산 불가


def test_extract_counts_handles_none():
    assert b._extract_counts(None) == {}


def test_rec_mean_is_yfinance_scale_not_our_score():
    # rec_mean = yfinance 1~5 척도 그대로 (RULE 7 — 우리 자체 산식 아님).
    info = {"recommendationMean": 2.5, "numberOfAnalystOpinions": 3, "recommendationKey": "hold"}
    c = b._build_consensus("Z", info, {})
    assert c["rec_mean"] == 2.5
