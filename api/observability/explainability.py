"""
Brain Score 기여도 분해 — verity_constitution fact_score weights × feature 평균.

목표:
  "오늘 평균 Brain Score 가 65.2 인 이유" — 양수 기여 TOP 5 / 음수 기여 TOP 5.

음수 기여 산정:
  - macro_override 발동: -10 (constitution 가드 효과 추정)
  - red_flags 발생률 × 패널티
  - vci 극단값 (>0.7) 비율
  - 데이터 결측 (dart_health 등)

저장: data/metadata/explainability.jsonl

가드 (spec §6):
  - constitution 미로딩 시 None 반환
  - feature 누락은 0 으로 처리 (제외 X — 기록 가능성 보존)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from api.config import DATA_DIR, now_kst

logger = logging.getLogger(__name__)

_PATH = os.path.join(DATA_DIR, "metadata", "explainability.jsonl")
_CONSTITUTION_PATH = os.path.join(DATA_DIR, "verity_constitution.json")


def _load_weights() -> Dict[str, float]:
    """fact_score weights 로드. 실패 시 빈 dict."""
    try:
        with open(_CONSTITUTION_PATH, "r", encoding="utf-8") as f:
            c = json.load(f)
        return (c.get("fact_score") or {}).get("weights") or {}
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("explainability: constitution load failed: %s", e)
        return {}


def _avg_recommendation_features(recs: List[dict]) -> Dict[str, float]:
    """recommendations 평균값 추출 — fact_score features 와 매핑."""
    if not recs:
        return {}
    out: Dict[str, float] = {}
    # fact_score features → recommendation 키 매핑
    feature_keys = [
        "multi_factor", "consensus_score", "consensus", "prediction",
        "backtest_score", "backtest", "timing_score", "timing",
        "moat_quality", "graham_value", "canslim_growth", "analyst_report",
        "dart_health", "perplexity_risk",
    ]
    for fk in feature_keys:
        vals = [r.get(fk) for r in recs if isinstance(r.get(fk), (int, float))]
        if vals:
            out[fk] = round(sum(vals) / len(vals), 3)

    # brain_score 평균
    bs = [r.get("brain_score") for r in recs if isinstance(r.get("brain_score"), (int, float))]
    if bs:
        out["_avg_brain_score"] = round(sum(bs) / len(bs), 2)

    return out


def _negative_factors(portfolio: dict, recs: List[dict]) -> List[Dict[str, Any]]:
    """음수 기여 요소 추정."""
    negs: List[Dict[str, Any]] = []

    # 1. macro_override 발동
    macro = portfolio.get("macro") or {}
    macro_diag = macro.get("macro_diagnosis")
    # macro_diagnosis 는 dict 또는 list (구조 변동) — dict 만 신뢰
    if not isinstance(macro_diag, dict):
        macro_diag = {}
    if macro_diag.get("override_active") or macro_diag.get("status") == "panic":
        negs.append({
            "feature": "macro_override_active",
            "avg_contribution": -8.0,  # constitution macro_override 의 평균 패널티 추정
            "weight": 0.0,
            "detail": macro_diag.get("status", "active"),
        })

    # 2. red_flags 발생률
    # 위치: top-level r["red_flags"] / r["risk_flags"] (legacy) +
    #       r["verity_brain"]["red_flags"] (현 cron writer 위치 — auto_avoid / downgrade / has_critical).
    # critical (auto_avoid 활성) 은 별도 카운트해서 패널티 분리.
    if recs:
        def _flags(r: dict) -> tuple:
            """returns (is_flagged, is_critical). is_critical = auto_avoid 활성."""
            if r.get("red_flags") or r.get("risk_flags"):
                return True, False  # legacy top-level — critical 정보 없음
            vb = r.get("verity_brain") or {}
            rf = vb.get("red_flags") or {}
            if not isinstance(rf, dict):
                return False, False
            has_critical = bool(rf.get("has_critical"))
            has_auto_avoid = bool(rf.get("auto_avoid"))
            has_downgrade = bool(rf.get("downgrade"))
            return (has_critical or has_auto_avoid or has_downgrade), (has_critical or has_auto_avoid)

        flag_pairs = [_flags(r) for r in recs]
        flagged = sum(1 for f, _ in flag_pairs if f)
        critical = sum(1 for _, c in flag_pairs if c)
        if flagged > 0:
            pct = flagged / len(recs)
            crit_pct = critical / len(recs) if critical else 0
            # critical 비중에 추가 패널티 가중 (1.5x)
            penalty = -6.0 * pct - 3.0 * crit_pct
            negs.append({
                "feature": "red_flags",
                "avg_contribution": round(penalty, 2),
                "weight": pct,
                "detail": f"{flagged}/{len(recs)} 종목 (critical {critical})",
            })

        # 3. VCI 극단값
        extreme = sum(1 for r in recs if isinstance(r.get("vci"), (int, float)) and abs(r["vci"]) > 0.7)
        if extreme > 0:
            pct = extreme / len(recs)
            negs.append({
                "feature": "vci_extreme",
                "avg_contribution": round(-4.0 * pct, 2),
                "weight": pct,
                "detail": f"{extreme} 종목 |VCI|>0.7",
            })

        # 4. dart_health 결측
        missing_dart = sum(1 for r in recs if r.get("dart_health") in (None, 0))
        if missing_dart > 0:
            pct = missing_dart / len(recs)
            negs.append({
                "feature": "dart_health_missing",
                "avg_contribution": round(-3.0 * pct, 2),
                "weight": pct,
                "detail": f"{missing_dart}/{len(recs)} 결측",
            })

    return negs


def _compare_yesterday(today_features: Dict[str, float],
                      today_brain_score: Optional[float]) -> Dict[str, Any]:
    """jsonl 어제 데이터 비교."""
    if not os.path.exists(_PATH) or today_brain_score is None:
        return {}
    try:
        last = None
        today_str = now_kst().strftime("%Y-%m-%d")
        with open(_PATH, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                    if e.get("date") == today_str:
                        continue
                    last = e
                except json.JSONDecodeError:
                    continue
        if not last:
            return {}

        prev_score = last.get("avg_brain_score")
        if prev_score is None:
            return {}

        prev_features = last.get("raw_features") or {}
        score_change = round(today_brain_score - prev_score, 2)

        # 가장 큰 변화 feature
        biggest_key = None
        biggest_delta = 0.0
        for k, v in today_features.items():
            if k.startswith("_"):
                continue
            pv = prev_features.get(k)
            if pv is None:
                continue
            delta = v - pv
            if abs(delta) > abs(biggest_delta):
                biggest_delta = delta
                biggest_key = k

        return {
            "score_change": score_change,
            "biggest_change_feature": biggest_key,
            "biggest_change_value": round(biggest_delta, 4) if biggest_key else 0.0,
            "yesterday_score": prev_score,
        }
    except OSError as e:
        logger.warning("explainability: yesterday compare failed: %s", e)
        return {}


def explain_brain_score(portfolio: Optional[dict]) -> Dict[str, Any]:
    """
    오늘 평균 Brain Score 의 기여도 분해.

    Returns:
      {
        "avg_brain_score": 65.2,
        "positive_contributors": [{"feature", "avg_contribution", "weight"}, ...],
        "negative_contributors": [...],
        "vs_yesterday": {"score_change", "biggest_change_feature", "biggest_change_value"},
        "_meta": {...}
      }
    """
    if not isinstance(portfolio, dict):
        return {"avg_brain_score": None, "positive_contributors": [],
                "negative_contributors": [], "vs_yesterday": {},
                "_meta": {"error": "no_portfolio"}}

    try:
        weights = _load_weights()
        recs = portfolio.get("recommendations") or []
        feat_avg = _avg_recommendation_features(recs)

        avg_brain_score = feat_avg.pop("_avg_brain_score", None)

        # 양수 기여 (weight × value, value 가 0 이상)
        positives: List[Dict[str, Any]] = []
        for feature_key, weight in weights.items():
            # weight key 가 "consensus" 인데 데이터는 "consensus_score" 일 수도
            v = feat_avg.get(feature_key) or feat_avg.get(f"{feature_key}_score")
            if v is None:
                continue
            if v <= 0:
                continue
            contribution = round(v * weight, 2)
            positives.append({
                "feature": feature_key,
                "avg_contribution": contribution,
                "weight": weight,
                "raw_value": v,
            })
        positives.sort(key=lambda x: x["avg_contribution"], reverse=True)

        # 음수 기여
        negatives = _negative_factors(portfolio, recs)
        negatives.sort(key=lambda x: x["avg_contribution"])  # 가장 음수부터

        # 어제 대비
        vs_yesterday = _compare_yesterday(feat_avg, avg_brain_score)

        return {
            "avg_brain_score": avg_brain_score,
            "positive_contributors": positives[:5],
            "negative_contributors": negatives[:5],
            "vs_yesterday": vs_yesterday,
            "_meta": {
                "checked_at": now_kst().isoformat(),
                "weights_loaded": len(weights),
                "features_extracted": len(feat_avg),
                "recs_count": len(recs),
            },
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("explainability: unexpected error: %s", e, exc_info=True)
        return {"avg_brain_score": None, "positive_contributors": [],
                "negative_contributors": [], "vs_yesterday": {},
                "_meta": {"error": str(e)[:200]}}


def persist_explanation(result: Dict[str, Any], today_features: Dict[str, float]) -> str:
    """jsonl 누적."""
    try:
        os.makedirs(os.path.dirname(_PATH), exist_ok=True)
        entry = {
            "date": now_kst().strftime("%Y-%m-%d"),
            "timestamp": now_kst().isoformat(),
            "avg_brain_score": result.get("avg_brain_score"),
            "positive_top": [c["feature"] for c in (result.get("positive_contributors") or [])][:5],
            "negative_top": [c["feature"] for c in (result.get("negative_contributors") or [])][:5],
            "raw_features": today_features,
        }
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return _PATH
    except OSError as e:
        logger.warning("explainability: persist failed: %s", e)
        return ""
