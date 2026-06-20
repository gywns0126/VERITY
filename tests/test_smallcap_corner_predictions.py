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
from scripts import score_smallcap_corner as SC


@pytest.fixture
def corner_stocks():
    return [
        {"ticker": "035460", "name": "기산텔레콤", "market": "KQ", "mktcap_eok": 800, "close": 5000,
         "financials": {"debt_ratio": 9.0, "roa": 5.0, "gross_margin": 30.0, "net_income": 120, "quarter_end": "2025-12-31"},
         "has_forensic_depth": True},
        {"ticker": "232830", "name": "아이티센피엔에스", "market": "KQ", "mktcap_eok": 348, "close": 2105,
         "financials": {"debt_ratio": 681.15, "roa": None, "gross_margin": 7.31, "net_income": 0, "quarter_end": "2025-12-31"},
         "has_forensic_depth": False},
        {"ticker": "000000", "name": "테스트소형", "market": "KS", "mktcap_eok": 1500, "close": 12000,
         "financials": {"debt_ratio": 50.0, "roa": 8.0, "gross_margin": 40.0, "net_income": 300, "quarter_end": "2025-12-31"},
         "has_forensic_depth": False},
    ]


def _load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def test_structure_n_times_three_horizons(tmp_path, corner_stocks):
    p = str(tmp_path / "sc.jsonl")
    rows = PL.generate_smallcap_predictions(corner_stocks, path=p)
    written = _load(p)
    # 3 종목 × 3 horizon = 9 (brain 결손 skip 없을 시). 반환 == 파일 기록.
    assert len(rows) == len(written) == 9
    assert all(r["target_type"] == "stock" for r in written)
    assert all(r["source"] == "smallcap_corner.v0" for r in written)
    assert all(r["spec_version"] == "smallcap.v0" for r in written)
    assert {r["horizon"] for r in written} == {"short", "mid", "long"}


def test_forced_direction_consistency(tmp_path, corner_stocks):
    """강제 매핑: direction 은 항상 grade 에서 유도 (코너 전용 자유 flip 0)."""
    p = str(tmp_path / "sc.jsonl")
    PL.generate_smallcap_predictions(corner_stocks, path=p)
    for r in _load(p):
        grade = str(r["signals"]["grade"]).upper()
        assert r["direction"] == PL._GRADE_DIRECTION.get(grade, "neutral")


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


def test_low_confidence_reflects_coverage_gate(tmp_path, corner_stocks):
    """low_confidence = (data_coverage < 0.40). 얕은 데이터 정직 표기."""
    p = str(tmp_path / "sc.jsonl")
    PL.generate_smallcap_predictions(corner_stocks, path=p)
    for r in _load(p):
        cov = r["signals"]["data_coverage"]
        assert r["low_confidence"] is (cov < PL._SMALLCAP_COVERAGE_GATE)


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


# ── 채점 subgroup 집계 (prediction_scoring stat 헬퍼 재사용) ──

def _scored_entry(ticker, horizon, pred_score, realized, direction="up", low_conf=False, neglected=False):
    return {
        "target_type": "stock", "target": ticker, "horizon": horizon,
        "direction": direction, "pred_score": pred_score, "confidence": 0.7,
        "low_confidence": low_conf,
        "signals": {"neglected_quality": neglected, "source": "smallcap_corner.v0"},
        "scored": True, "realized_return": realized, "hit": None, "ic_contrib": pred_score,
    }


def test_in_subgroup_logic():
    e_hi = _scored_entry("A", "mid", 60, 5.0, low_conf=False, neglected=True)
    e_lo = _scored_entry("B", "mid", 40, -2.0, low_conf=True, neglected=False)
    assert SC._in_subgroup(e_hi, "all") and SC._in_subgroup(e_lo, "all")
    assert SC._in_subgroup(e_hi, "high_conf") and not SC._in_subgroup(e_lo, "high_conf")
    assert SC._in_subgroup(e_hi, "neglected_quality") and not SC._in_subgroup(e_lo, "neglected_quality")


def test_aggregate_subgroup_counts():
    """3 부분군 × horizon 집계 — n 카운트 + survivorship 플래그."""
    entries = [
        _scored_entry("A", "mid", 70, 6.0, low_conf=False, neglected=True),
        _scored_entry("B", "mid", 55, 1.0, low_conf=False, neglected=False),
        _scored_entry("C", "mid", 30, -3.0, low_conf=True, neglected=False),
    ]
    recs = SC._aggregate(entries)
    by_key = {(r["subgroup"], r["horizon"]): r for r in recs}
    assert by_key[("all", "mid")]["n"] == 3
    assert by_key[("high_conf", "mid")]["n"] == 2          # A,B (low_conf C 제외)
    assert by_key[("neglected_quality", "mid")]["n"] == 1  # A
    assert all(r["survivorship_unadjusted"] is True for r in recs)
    assert all(r["spec_version"] == "smallcap.v0" for r in recs)


def test_score_smallcap_empty_trail(tmp_path):
    res = SC.score_smallcap(trail_path=str(tmp_path / "none.jsonl"),
                            ic_history_path=str(tmp_path / "ic.jsonl"))
    assert res["scored"] == 0
