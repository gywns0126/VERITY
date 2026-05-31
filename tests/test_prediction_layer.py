"""
test_prediction_layer.py — Prediction Layer v0 생성+로깅 단위 검증.

사전등록 spec (docs/prediction_layer_spec_v0_2026_06_01.md) 정합:
forward-only / horizon 3 / grade→방향 매핑 / 단기섹터 low_confidence / schema.
"""
import json
import os

import pytest

from api.intelligence import prediction_layer as PL
from api.metadata import prediction_trail as PT


@pytest.fixture
def recs():
    return [
        {"ticker": "114090", "sector": "Consumer Cyclical",
         "verity_brain": {"brain_score": 52, "grade": "CAUTION", "grade_confidence": "firm", "vci": 18}},
        {"ticker": "175330", "sector": "Financial",
         "verity_brain": {"brain_score": 56, "grade": "WATCH", "grade_confidence": "firm"}},
        {"ticker": "000660", "sector": "Technology",
         "verity_brain": {"brain_score": 40, "grade": "AVOID", "grade_confidence": "tentative"}},
        {"ticker": "BADREC", "sector": "X", "verity_brain": {}},  # 결손 → skip
    ]


@pytest.fixture
def macro():
    return {"sectors": [
        {"sector": "Financials", "score": 0.13, "raw_score": 0.52, "tier": "FAVORED", "contribution_count": 4},
        {"sector": "Energy", "score": -0.10, "raw_score": -0.4, "tier": "DISFAVORED", "contribution_count": 3},
        {"sector": "Health", "score": 0.0, "raw_score": 0.0, "tier": "NEUTRAL", "contribution_count": 1},
    ]}


def _load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def test_stock_predictions_count_and_skip(tmp_path, recs):
    p = str(tmp_path / "t.jsonl")
    PL.generate_stock_predictions(recs, path=p)
    rows = _load(p)
    # 3 valid recs × 3 horizons = 9 (BADREC 결손 skip)
    assert len(rows) == 9
    assert {r["target"] for r in rows} == {"114090", "175330", "000660"}


def test_grade_direction_mapping(tmp_path, recs):
    p = str(tmp_path / "t.jsonl")
    PL.generate_stock_predictions(recs, path=p)
    rows = _load(p)
    by_t = {r["target"]: r["direction"] for r in rows}
    assert by_t["114090"] == "neutral"  # CAUTION
    assert by_t["175330"] == "up"       # WATCH
    assert by_t["000660"] == "down"     # AVOID


def test_forward_only(tmp_path, recs, macro):
    p = str(tmp_path / "t.jsonl")
    PL.run_prediction_layer(recs, macro, path=p)
    rows = _load(p)
    assert rows and all(r["created_at"][:10] < r["eval_date"] for r in rows)


def test_horizons_and_eval_dates(tmp_path, recs):
    p = str(tmp_path / "t.jsonl")
    PL.generate_stock_predictions(recs[:1], path=p)
    rows = _load(p)
    assert {r["horizon"] for r in rows} == {"short", "mid", "long"}
    # eval_date 단 < 중 < 장
    by_h = {r["horizon"]: r["eval_date"] for r in rows}
    assert by_h["short"] < by_h["mid"] < by_h["long"]


def test_sector_low_confidence_short_only(tmp_path, macro):
    p = str(tmp_path / "t.jsonl")
    PL.generate_sector_predictions(macro, path=p)
    rows = _load(p)
    short = [r for r in rows if r["horizon"] == "short"]
    nonshort = [r for r in rows if r["horizon"] != "short"]
    assert short and all(r["low_confidence"] for r in short)        # 단기 섹터 = low_conf (PPL Q4)
    assert nonshort and not any(r["low_confidence"] for r in nonshort)


def test_sector_direction_by_tier(tmp_path, macro):
    p = str(tmp_path / "t.jsonl")
    PL.generate_sector_predictions(macro, path=p)
    rows = _load(p)
    by_t = {r["target"]: r["direction"] for r in rows}
    assert by_t["Financials"] == "up"     # FAVORED, score>0.05
    assert by_t["Energy"] == "down"       # DISFAVORED
    assert by_t["Health"] == "neutral"    # NEUTRAL


def test_schema_and_unscored(tmp_path, recs, macro):
    p = str(tmp_path / "t.jsonl")
    PL.run_prediction_layer(recs, macro, path=p)
    for r in _load(p):
        assert r["scored"] is False
        assert r["realized_return"] is None and r["hit"] is None and r["ic_contrib"] is None
        assert set(("pred_id", "created_at", "target_type", "horizon", "pred_score", "confidence", "signals")) <= set(r)


def test_invalid_horizon_raises(tmp_path):
    with pytest.raises(ValueError):
        PT.log_prediction("stock", "X", "weekly", "up", 1.0, 0.5, {}, path=str(tmp_path / "t.jsonl"))


def test_graceful_empty(tmp_path):
    p = str(tmp_path / "t.jsonl")
    out = PL.run_prediction_layer([], {}, path=p)
    assert out["total"] == 0
    assert not os.path.exists(p)  # 빈 입력 = 파일 미생성
