"""
test_smallcap_corner_predictions.py — KR 소형주 코너 forward 예측 생성+채점 단위 검증.

사전등록 spec (docs/PREREG_SMALLCAP_CORNER_TRAIL_2026_06_20.md) 정합:
analyze_all 별도 호출 → forward 예측 / 강제 매핑(direction = _GRADE_DIRECTION[grade]) /
entry_price 동결(PIT) / neglected_quality 부분군 태그 / low_confidence = data_coverage 게이트 /
별 trail(SMALLCAP_PATH, 메인 무오염) / 관측 only. + 채점 subgroup 집계(prediction_scoring 헬퍼 재사용).
"""
import json

import pytest

from api.intelligence import prediction_layer as PL
from api.metadata import prediction_trail as PT
from api.builders import smallcap_corner_enrich as EN
from scripts import score_smallcap_corner as SC


def _enriched(ticker, name, market, mktcap, close, fin, mf_score, neglected_ok=True):
    """enrich_quant_factors 통과 후 형태(enriched=True + multi_factor)를 시뮬레이트."""
    return {
        "ticker": ticker, "name": name, "market": market, "mktcap_eok": mktcap, "close": close,
        "financials": fin, "has_forensic_depth": False,
        "enriched": True, "price_points": 250,
        "multi_factor": {"multi_score": mf_score, "grade": "관망"},
        "quant_factors": {"momentum_score": mf_score, "quality_score": 50,
                          "volatility_score": 50, "mean_reversion_score": 50},
    }


@pytest.fixture
def corner_stocks():
    # enrich 후 형태 — multi_score 분산(35/55/70)으로 brain_score 분산 유도.
    return [
        _enriched("035460", "기산텔레콤", "KQ", 800, 5000,
                  {"debt_ratio": 9.0, "roa": 5.0, "gross_margin": 30.0, "net_income": 120}, 70),
        _enriched("232830", "아이티센피엔에스", "KQ", 348, 2105,
                  {"debt_ratio": 681.15, "roa": None, "gross_margin": 7.31, "net_income": 0}, 35),
        _enriched("000000", "테스트소형", "KS", 1500, 12000,
                  {"debt_ratio": 50.0, "roa": 8.0, "gross_margin": 40.0, "net_income": 300}, 55),
    ]


def _load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def test_structure_factor_times_horizon(tmp_path, corner_stocks):
    p = str(tmp_path / "sc.jsonl")
    rows = PL.generate_smallcap_predictions(corner_stocks, path=p)
    written = _load(p)
    # 3 종목 × 4 팩터 × 3 horizon = 36. 반환 == 파일 기록.
    assert len(rows) == len(written) == 36
    assert all(r["target_type"] == "stock" for r in written)
    assert {r["signals"]["factor"] for r in written} == {"momentum", "quality", "vol", "mr"}
    assert all(r["source"] == f"smallcap_corner.{r['signals']['factor']}.v0" for r in written)
    assert all(r["spec_version"] == "smallcap.v0" for r in written)
    assert {r["horizon"] for r in written} == {"short", "mid", "long"}


def test_face_value_direction(tmp_path, corner_stocks):
    """강제 매핑: direction = face-value(score>50 up / <50 down / ==50 neutral). 자유 flip 0."""
    p = str(tmp_path / "sc.jsonl")
    PL.generate_smallcap_predictions(corner_stocks, path=p)
    for r in _load(p):
        sc = r["signals"]["factor_score"]
        expected = "up" if sc > 50 else "down" if sc < 50 else "neutral"
        assert r["direction"] == expected
        assert r["pred_score"] == sc
        assert r["confidence"] == 0.5


def test_entry_price_frozen_pit(tmp_path, corner_stocks):
    """entry_price = scan 시점 종가 동결 (signals)."""
    p = str(tmp_path / "sc.jsonl")
    PL.generate_smallcap_predictions(corner_stocks, path=p)
    by_t = {s["ticker"]: s["close"] for s in corner_stocks}
    for r in _load(p):
        assert r["signals"]["entry_price"] == by_t[r["target"]]


def test_neglected_quality_subgroup_tag(tmp_path, corner_stocks):
    """방치 우량 멤버십 = signals 동결 (멤버만 True)."""
    p = str(tmp_path / "sc.jsonl")
    PL.generate_smallcap_predictions(corner_stocks, neglected_tickers=["035460"], path=p)
    for r in _load(p):
        expected = r["target"] == "035460"
        assert r["signals"]["neglected_quality"] is expected


def test_separate_trail_no_main_contamination(tmp_path, corner_stocks):
    """기본 path = SMALLCAP_PATH (메인 trail 과 별 파일). 무오염."""
    assert PT.SMALLCAP_PATH != PT._PATH
    assert PT.SMALLCAP_PATH.endswith("smallcap_corner_prediction_trail.jsonl")
    # ic_history 도 메인과 별 sink
    from api.intelligence.prediction_scoring import IC_HISTORY_PATH as MAIN_IC
    assert SC.IC_HISTORY_PATH != MAIN_IC


def test_empty_input_graceful():
    assert PL.generate_smallcap_predictions([]) == []
    assert PL.generate_smallcap_predictions(None) == []


def test_non_enriched_skipped(tmp_path):
    """enriched=False(가격레이크 부재) 종목 = degenerate → trail 제외 (spec §10)."""
    raw = [{"ticker": "111111", "name": "미enrich", "market": "KQ", "close": 1000,
            "financials": {"debt_ratio": 30.0, "roa": 5.0, "gross_margin": 20.0}}]  # enriched 키 부재
    assert PL.generate_smallcap_predictions(raw, path=str(tmp_path / "x.jsonl")) == []


def test_rows_carry_factor_and_price_points(tmp_path, corner_stocks):
    p = str(tmp_path / "sc.jsonl")
    PL.generate_smallcap_predictions(corner_stocks, path=p)
    rows = _load(p)
    assert rows and all(r["signals"].get("factor") in {"momentum", "quality", "vol", "mr"} for r in rows)
    assert all(r["signals"].get("price_points") is not None for r in rows)


# ── Phase 1 enrichment (smallcap_corner_enrich) ──

def test_enrich_no_lake_graceful():
    """lake 부재 시 전 종목 enriched=False (graceful, CI 안전)."""
    stocks = [{"ticker": "035460", "name": "기산", "close": 5000,
               "financials": {"roa": 5.0, "debt_ratio": 9.0, "gross_margin": 30.0}}]
    out = EN.enrich_quant_factors(stocks, lake_path="/nonexistent/lake.duckdb")
    assert len(out) == 1
    assert out[0]["enriched"] is False
    assert out[0]["multi_factor"]["multi_score"] is not None  # 팩터 계산은 진행(중립)


def test_enrich_one_disperses_with_history():
    """가격 히스토리 충분 시 enriched=True + multi_factor 계산 (분산 lever 검증)."""
    import math
    # 우상향 추세 + 저변동 종가 252점 (모멘텀 양호 예상)
    closes_up = [1000 * (1 + 0.001 * i) for i in range(252)]
    s = {"ticker": "AAA", "name": "상승주", "close": closes_up[-1],
         "financials": {"roa": 10.0, "debt_ratio": 20.0, "gross_margin": 45.0}}
    out = EN._enrich_one(s, closes_up)
    assert out["enriched"] is True
    assert out["price_points"] == 252
    assert isinstance(out["multi_factor"]["multi_score"], int)
    assert out["quant_factors"]["momentum_score"] is not None


def test_enrich_one_short_history_not_enriched():
    """가격 점수 부족(<60) = enriched=False."""
    s = {"ticker": "BBB", "name": "신규", "close": 1000, "financials": {"roa": 5.0}}
    out = EN._enrich_one(s, [1000.0] * 30)  # 30점 < _MIN_HISTORY
    assert out["enriched"] is False


# ── 채점 subgroup 집계 (prediction_scoring stat 헬퍼 재사용) ──

def _scored_entry(ticker, horizon, pred_score, realized, factor="momentum", direction="up", neglected=False):
    return {
        "target_type": "stock", "target": ticker, "horizon": horizon,
        "direction": direction, "pred_score": pred_score, "confidence": 0.5,
        "source": f"smallcap_corner.{factor}.v0",
        "signals": {"factor": factor, "neglected_quality": neglected},
        "scored": True, "realized_return": realized, "hit": None, "ic_contrib": pred_score,
    }


def test_in_subgroup_logic():
    e_neg = _scored_entry("A", "mid", 60, 5.0, neglected=True)
    e_oth = _scored_entry("B", "mid", 40, -2.0, neglected=False)
    assert SC._in_subgroup(e_neg, "all") and SC._in_subgroup(e_oth, "all")
    assert SC._in_subgroup(e_neg, "neglected_quality") and not SC._in_subgroup(e_oth, "neglected_quality")
    assert SC._SUBGROUPS == ("all", "neglected_quality")  # high_conf 제거 (§11)


def test_aggregate_factor_subgroup_counts():
    """(factor, subgroup, horizon) 집계 — 팩터별 독립 + n 카운트 + survivorship 플래그."""
    entries = [
        _scored_entry("A", "mid", 70, 6.0, factor="momentum", neglected=True),
        _scored_entry("B", "mid", 55, 1.0, factor="momentum", neglected=False),
        _scored_entry("A", "mid", 30, 6.0, factor="quality", neglected=True),
    ]
    recs = SC._aggregate(entries)
    by_key = {(r["factor"], r["subgroup"], r["horizon"]): r for r in recs}
    assert by_key[("momentum", "all", "mid")]["n"] == 2           # A,B
    assert by_key[("momentum", "neglected_quality", "mid")]["n"] == 1  # A
    assert by_key[("quality", "all", "mid")]["n"] == 1            # 팩터 분리
    assert all(r["survivorship_unadjusted"] is True for r in recs)
    assert all(r["spec_version"] == "smallcap.v0" for r in recs)


def test_score_smallcap_empty_trail(tmp_path):
    res = SC.score_smallcap(trail_path=str(tmp_path / "none.jsonl"),
                            ic_history_path=str(tmp_path / "ic.jsonl"))
    assert res["scored"] == 0
