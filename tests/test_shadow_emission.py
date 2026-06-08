"""섀도우 funnel emission 테스트 — Shadow Funnel Scoring Spec v0 증분 2.

2026-06-08. log_prediction source 분리 + generate_shadow_predictions 검증.
"""
import json
import tempfile

import pytest

from api.metadata import prediction_trail as PT
from api.intelligence import prediction_layer as PL


def test_log_prediction_source_separates_pred_id():
    tmp = tempfile.mktemp(suffix=".jsonl")
    prod = PT.log_prediction(target_type="stock", target="005930", horizon="short",
                             direction="up", pred_score=80.0, confidence=0.6, signals={}, path=tmp)
    shad = PT.log_prediction(target_type="stock", target="005930", horizon="short",
                             direction="up", pred_score=85.0, confidence=0.5, signals={},
                             spec_version="shadow.v0", source="shadow_funnel.v0", path=tmp)
    # 같은 ticker/horizon/일자라도 source 다르면 pred_id 충돌 없어야 (채점 rewrite 매칭 보호)
    assert prod["pred_id"] != shad["pred_id"]
    assert prod["source"] == "production"
    assert shad["source"] == "shadow_funnel.v0"
    assert shad["pred_id"].endswith("-shadow_funnel")


def test_log_prediction_backward_compat_no_source():
    # source 미지정 = 기존 동작 (pred_id suffix 없음, source=production)
    tmp = tempfile.mktemp(suffix=".jsonl")
    e = PT.log_prediction(target_type="stock", target="000660", horizon="mid",
                          direction="up", pred_score=70.0, confidence=0.5, signals={}, path=tmp)
    assert e["pred_id"] == f"{e['created_at'][:10].replace('-','')}-000660-mid"
    assert e["source"] == "production"


def test_generate_shadow_predictions_basic():
    tmp = tempfile.mktemp(suffix=".jsonl")
    picks = [
        {"ticker": "005930", "score": 85.6, "entry_price": 71000, "currency": "KRW", "name": "삼성전자"},
        {"ticker": "000660", "score": 80.1, "entry_price": 190000, "currency": "KRW", "name": "SK하이닉스"},
    ]
    out = PL.generate_shadow_predictions(picks, path=tmp)
    assert len(out) == 2 * len(PL._HORIZONS)  # ticker × horizon
    assert all(r["source"] == "shadow_funnel.v0" for r in out)
    assert all(r["spec_version"] == "shadow.v0" for r in out)
    # entry_price 동결 (PIT §3) — signals 에 보존
    assert out[0]["signals"]["entry_price"] == 71000
    assert out[0]["pred_score"] == 85.6


def test_generate_shadow_predictions_graceful_skip():
    tmp = tempfile.mktemp(suffix=".jsonl")
    picks = [
        {"ticker": "005930", "score": 85.6},
        {"ticker": "BAD", "score": None},   # 점수 결손 → skip
        {"score": 50.0},                     # ticker 결손 → skip
    ]
    out = PL.generate_shadow_predictions(picks, path=tmp)
    assert len(out) == 1 * len(PL._HORIZONS)  # 유효 1건만


def test_generate_shadow_predictions_direction_threshold():
    tmp = tempfile.mktemp(suffix=".jsonl")
    out = PL.generate_shadow_predictions(
        [{"ticker": "X", "score": 49.0}], path=tmp
    )
    assert all(r["direction"] == "neutral" for r in out)  # <50 = neutral
    out2 = PL.generate_shadow_predictions(
        [{"ticker": "Y", "score": 60.0}], path=tmp
    )
    assert all(r["direction"] == "up" for r in out2)  # >=50 = up


def test_shadow_records_distinct_from_production_in_same_trail():
    """같은 trail 파일에 production + shadow 공존, source 로 분리 가능."""
    tmp = tempfile.mktemp(suffix=".jsonl")
    PT.log_prediction(target_type="stock", target="005930", horizon="short",
                      direction="up", pred_score=80.0, confidence=0.6, signals={}, path=tmp)
    PL.generate_shadow_predictions([{"ticker": "005930", "score": 85.0}], path=tmp)
    rows = [json.loads(l) for l in open(tmp, encoding="utf-8") if l.strip()]
    by_source = {}
    for r in rows:
        by_source.setdefault(r["source"], 0)
        by_source[r["source"]] += 1
    assert by_source["production"] == 1
    assert by_source["shadow_funnel.v0"] == len(PL._HORIZONS)
