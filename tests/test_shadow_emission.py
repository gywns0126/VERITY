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


def test_shadow_defaults_to_separate_trail(monkeypatch):
    """P0 fix (물리 분리): shadow 는 path 미지정 시 SHADOW_PATH(별도 파일)로 기록 →
    프로덕션 trail 무오염. prediction_scoring 이 섀도우를 절대 pool 못 함 (spec §1/§5)."""
    assert PT.SHADOW_PATH != PT._PATH  # 별도 경로
    prod_tmp = tempfile.mktemp(suffix=".jsonl")
    shadow_tmp = tempfile.mktemp(suffix=".shadow.jsonl")
    monkeypatch.setattr(PT, "_PATH", prod_tmp)
    monkeypatch.setattr(PT, "SHADOW_PATH", shadow_tmp)

    # 프로덕션 로깅 (default → _PATH)
    PT.log_prediction(target_type="stock", target="005930", horizon="short",
                      direction="up", pred_score=80.0, confidence=0.6, signals={})
    # 섀도우 로깅 (path 미지정 → SHADOW_PATH)
    PL.generate_shadow_predictions([{"ticker": "005930", "score": 85.0}])

    prod_rows = [json.loads(l) for l in open(prod_tmp, encoding="utf-8") if l.strip()]
    shadow_rows = [json.loads(l) for l in open(shadow_tmp, encoding="utf-8") if l.strip()]
    # 프로덕션 trail = production 1건만, shadow 0건 (오염 0)
    assert len(prod_rows) == 1 and all(r["source"] == "production" for r in prod_rows)
    # 섀도우 trail = shadow 만
    assert len(shadow_rows) == len(PL._HORIZONS)
    assert all(r["source"] == "shadow_funnel.v0" for r in shadow_rows)


def test_shadow_explicit_path_override():
    """path 명시 시 그 경로 사용 (테스트 격리 보장)."""
    tmp = tempfile.mktemp(suffix=".jsonl")
    out = PL.generate_shadow_predictions([{"ticker": "005930", "score": 85.0}], path=tmp)
    rows = [json.loads(l) for l in open(tmp, encoding="utf-8") if l.strip()]
    assert len(rows) == len(out) == len(PL._HORIZONS)
