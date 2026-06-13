"""
test_ml_shadow_predictions.py — ML(XGB up_probability) shadow 예측 생성+로깅 단위 검증.

사전등록 spec (docs/ml_shadow_prediction_spec_v0_2026_06_13.md) 정합:
genuine ensemble 만 / 방향 50경계 / confidence=P(방향적중) / pred_score=up_prob /
source=xgb_ml.v0 / forward-only / 별도 trail(ML_PATH) / 관측 only.
"""
import json
import os

import pytest

from api.intelligence import prediction_layer as PL
from api.metadata import prediction_trail as PT


@pytest.fixture
def recs():
    return [
        {"ticker": "AAA", "prediction": {
            "up_probability": 80.6, "method": "ensemble_5m_3arch", "model_accuracy": 58.0,
            "confidence_level": "high", "prediction_std": 5.0, "conformal_width_pct": 30.0,
            "train_samples": 200, "top_features": {"rsi": 0.3}}},
        {"ticker": "BBB", "prediction": {"up_probability": 30.0, "method": "ensemble_5m_3arch"}},  # down
        {"ticker": "CCC", "prediction": {"up_probability": 50.0, "method": "ensemble_5m_3arch"}},  # neutral
        {"ticker": "FALL", "prediction": {"up_probability": 50.0, "method": "fallback"}},   # skip(비-ensemble)
        {"ticker": "RULE", "prediction": {"up_probability": 62.0, "method": "rule_based"}}, # skip(휴리스틱)
        {"ticker": "ERR", "prediction": {"up_probability": 50, "method": "error"}},         # skip
        {"ticker": "NOPRED"},                                                               # skip(예측 결손)
    ]


def _load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def test_ensemble_only_and_count(tmp_path, recs):
    p = str(tmp_path / "ml.jsonl")
    PL.generate_ml_predictions(recs, path=p)
    rows = _load(p)
    # genuine ensemble 3건(AAA/BBB/CCC) × 3 horizon = 9. fallback/rule_based/error/결손 skip.
    assert len(rows) == 9
    assert {r["target"] for r in rows} == {"AAA", "BBB", "CCC"}


def test_direction_50_boundary(tmp_path, recs):
    p = str(tmp_path / "ml.jsonl")
    PL.generate_ml_predictions(recs, path=p)
    by_t = {r["target"]: r["direction"] for r in _load(p)}
    assert by_t["AAA"] == "up"        # up_prob 80.6 > 50
    assert by_t["BBB"] == "down"      # 30 < 50
    assert by_t["CCC"] == "neutral"   # == 50


def test_confidence_is_prob_of_called_direction(tmp_path, recs):
    """Brier 입력 = P(예측 방향 적중). up→up_prob/100, down→1-up_prob/100, neutral→0.5."""
    p = str(tmp_path / "ml.jsonl")
    PL.generate_ml_predictions(recs, path=p)
    by_t = {r["target"]: r["confidence"] for r in _load(p)}
    assert by_t["AAA"] == 0.806       # 80.6/100
    assert by_t["BBB"] == 0.70        # 1 - 30/100
    assert by_t["CCC"] == 0.5


def test_pred_score_is_up_probability(tmp_path, recs):
    p = str(tmp_path / "ml.jsonl")
    PL.generate_ml_predictions(recs, path=p)
    by_t = {r["target"]: r["pred_score"] for r in _load(p)}
    assert by_t["AAA"] == 80.6
    assert by_t["BBB"] == 30.0


def test_source_tag_and_spec_version(tmp_path, recs):
    p = str(tmp_path / "ml.jsonl")
    PL.generate_ml_predictions(recs, path=p)
    rows = _load(p)
    assert all(r["source"] == "xgb_ml.v0" for r in rows)
    assert all(r["spec_version"] == "ml.v0" for r in rows)
    # pred_id 가 source suffix 로 프로덕션과 충돌 회피
    assert all(r["pred_id"].endswith("-xgb_ml") for r in rows)


def test_horizons_and_forward_only(tmp_path, recs):
    p = str(tmp_path / "ml.jsonl")
    PL.generate_ml_predictions(recs[:1], path=p)
    rows = _load(p)
    assert {r["horizon"] for r in rows} == {"short", "mid", "long"}
    assert all(r["created_at"][:10] < r["eval_date"] for r in rows)


def test_signals_and_unscored_schema(tmp_path, recs):
    p = str(tmp_path / "ml.jsonl")
    PL.generate_ml_predictions(recs[:1], path=p)
    for r in _load(p):
        assert r["target_type"] == "stock"
        assert r["scored"] is False
        assert r["realized_return"] is None and r["hit"] is None and r["ic_contrib"] is None
        assert r["signals"]["up_probability"] == 80.6
        assert r["signals"]["method"] == "ensemble_5m_3arch"
        assert r["signals"]["source"] == "xgb_ml.v0"


def test_scorer_schema_compat(recs, tmp_path):
    """동일 source-agnostic scorer(prediction_scoring) 가 읽을 필드 모두 존재 = 재사용 가능."""
    p = str(tmp_path / "ml.jsonl")
    PL.generate_ml_predictions(recs, path=p)
    needed = {"target_type", "target", "horizon", "direction", "pred_score",
              "confidence", "eval_date", "created_at", "scored"}
    for r in _load(p):
        assert needed <= set(r)


def test_graceful_empty(tmp_path):
    p = str(tmp_path / "ml.jsonl")
    out = PL.generate_ml_predictions([], path=p)
    assert out == []
    assert not os.path.exists(p)  # 빈 입력 = 파일 미생성


def test_all_nonensemble_skipped(tmp_path):
    p = str(tmp_path / "ml.jsonl")
    out = PL.generate_ml_predictions(
        [{"ticker": "X", "prediction": {"up_probability": 70, "method": "fallback"}}], path=p
    )
    assert out == []
    assert not os.path.exists(p)
