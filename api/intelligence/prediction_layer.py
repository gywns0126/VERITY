"""
prediction_layer.py — VERITY Prediction Layer v0 생성기.

2026-06-01 신설. 사전등록 spec (docs/prediction_layer_spec_v0_2026_06_01.md) 정합.
descriptive(핫 섹터/종목) → predictive 전환. 자기 신호(Brain grade + macro_industry_alignment)의
forward 투영 (RULE 6 — LLM 예측 wrap 금지). 매 daily run 당 cross-section 1벌 생성
(IC 표준, factor_ic_history 정합) → prediction_trail.jsonl 로깅. 채점은 별도 cron.

대상 × horizon = (섹터 로테이션 + 종목 forward) × (단 short / 중 mid / 장 long).
모든 산출 = "예측 추적 중 (가설)" — actionable 아님 (N gate 통과 전, spec §4/§5).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from api.metadata import prediction_trail as PT

_HORIZONS = ("short", "mid", "long")

# Brain grade → forward 방향 (grade 자체가 암묵적 forward 판단)
_GRADE_DIRECTION = {"BUY": "up", "WATCH": "up", "CAUTION": "neutral", "AVOID": "down"}
# grade_confidence label → 수치 (Brier 채점 입력)
_CONF_MAP = {"firm": 0.7, "tentative": 0.45, "weak": 0.35}


def _conf_num(grade_confidence: Any) -> float:
    if isinstance(grade_confidence, (int, float)):
        return max(0.0, min(1.0, float(grade_confidence)))
    return _CONF_MAP.get(str(grade_confidence).lower(), 0.5)


def generate_stock_predictions(
    recommendations: List[Dict[str, Any]], path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """종목 forward — 각 추천의 Brain grade/score 를 horizon 3개로 투영."""
    out: List[Dict[str, Any]] = []
    for rec in recommendations or []:
        vb = rec.get("verity_brain") or {}
        grade = vb.get("grade")
        score = vb.get("brain_score")
        ticker = rec.get("ticker")
        if not ticker or grade is None or score is None:
            continue  # 데이터 결손 = skip (graceful)
        direction = _GRADE_DIRECTION.get(str(grade).upper(), "neutral")
        conf = _conf_num(vb.get("grade_confidence"))
        signals = {
            "brain_score": score,
            "grade": grade,
            "sector": rec.get("sector"),
            "vci": vb.get("vci"),
            "source": "verity_brain.v5",
        }
        for h in _HORIZONS:
            out.append(
                PT.log_prediction(
                    target_type="stock", target=str(ticker), horizon=h,
                    direction=direction, pred_score=float(score), confidence=conf,
                    signals=signals, path=path,
                )
            )
    return out


# 섀도우 funnel 예측 source 태그 (Shadow Funnel Scoring Spec v0). production 과 분리 집계.
_SHADOW_SOURCE = "shadow_funnel.v0"


def generate_shadow_predictions(
    picks: List[Dict[str, Any]], path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """섀도우 funnel e_brain_quick 100-name → forward 예측 (Shadow Funnel Scoring Spec v0).

    picks = [{"ticker","score","entry_price","currency","name"}, ...] (wide_scan persist).
    source="shadow_funnel.v0" 분리 태그 → 프로덕션 IC 와 별도 집계/비교 (§5).
    pred_score = funnel 합성점수 (cross-section rank-IC 입력). entry_price 는 signals 에 동결 (PIT, §3).

    물리 분리: path 미지정 시 PT.SHADOW_PATH(별도 trail) 에 기록 — 프로덕션 scorer 가
    섀도우를 pool 하지 못하게 함 (§1 무오염, prediction_scoring.py 무변경). 채점은 증분 3 섀도우 scorer.
    """
    path = path or PT.SHADOW_PATH
    out: List[Dict[str, Any]] = []
    for p in picks or []:
        ticker = p.get("ticker")
        score = p.get("score")
        if not ticker or score is None:
            continue  # 결손 = skip (graceful)
        direction = "up" if float(score) >= 50.0 else "neutral"
        signals = {
            "funnel_score": score,
            "entry_price": p.get("entry_price"),  # scan 시점 동결 (pykrx backward-adjust drift 회피)
            "currency": p.get("currency"),
            "name": p.get("name"),
            "stage": "e_brain_quick",
            "source": _SHADOW_SOURCE,
        }
        for h in _HORIZONS:
            out.append(
                PT.log_prediction(
                    target_type="stock", target=str(ticker), horizon=h,
                    direction=direction, pred_score=float(score), confidence=0.5,
                    signals=signals, spec_version="shadow.v0", source=_SHADOW_SOURCE,
                    path=path,
                )
            )
    return out


def generate_sector_predictions(
    macro_alignment: Dict[str, Any], path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """섹터 로테이션 — macro_industry_alignment score 로 rank → 방향 투영.

    PPL Q4: 단기(short) 섹터 로테이션은 단기 반전으로 학술지지 낮음 → low_confidence 플래그.
    """
    out: List[Dict[str, Any]] = []
    sectors = (macro_alignment or {}).get("sectors") or []
    if not sectors:
        return out
    # score desc 정렬 → rank
    ranked = sorted(sectors, key=lambda s: s.get("score", 0.0), reverse=True)
    for rank, s in enumerate(ranked, start=1):
        name = s.get("sector")
        sc = s.get("score")
        if not name or sc is None:
            continue
        tier = str(s.get("tier", "")).upper()
        if tier == "FAVORED" or sc > 0.05:
            direction = "up"
        elif tier == "DISFAVORED" or sc < -0.05:
            direction = "down"
        else:
            direction = "neutral"
        signals = {
            "align_score": sc, "raw_score": s.get("raw_score"),
            "tier": s.get("tier"), "contribution_count": s.get("contribution_count"),
            "source": "macro_industry_alignment.v0.1",
        }
        for h in _HORIZONS:
            out.append(
                PT.log_prediction(
                    target_type="sector", target=str(name), horizon=h,
                    direction=direction, pred_score=float(sc), confidence=0.5,
                    signals=signals, rank=rank,
                    low_confidence=(h == "short"),  # 단기 섹터 = 학술지지 낮음 (PPL Q4)
                    path=path,
                )
            )
    return out


def run_prediction_layer(
    recommendations: List[Dict[str, Any]],
    macro_alignment: Optional[Dict[str, Any]] = None,
    path: Optional[str] = None,
) -> Dict[str, int]:
    """daily 파이프라인 hook 진입점. cross-section 1벌 생성+로깅. 결손 시 graceful 부분 생성."""
    stock = generate_stock_predictions(recommendations, path=path)
    sector = generate_sector_predictions(macro_alignment or {}, path=path)
    return {
        "stock_predictions": len(stock),
        "sector_predictions": len(sector),
        "total": len(stock) + len(sector),
    }
