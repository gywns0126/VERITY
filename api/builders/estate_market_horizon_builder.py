"""
estate_market_horizon_builder.py — ESTATE 5축 종합 verdict synthesizer

EstateMarketHorizon.tsx (market/ 폴더) 의 데이터 source.
ESTATE 의 진짜 "MarketHorizon" 짝 (VERITY MarketHorizon V2.1 과 동급 역할).

5축 입력:
  1. 거시(macro)   = /api/estate/macro-bridge   weight 0.20
  2. 사이클(cycle) = /api/estate/horizon         weight 0.25
  3. 정책(policy)  = /api/estate/policy-narrative weight 0.15
  4. 지역(region)  = /api/landex/scores          weight 0.15
  5. 섹터(sector)  = /api/estate/sector-pulse    weight 0.25

종합 산식:
  - 각 axis verdict → score (+1/-1/0)
  - weighted_avg = Σ(weight × score) / Σ(weight where available)
  - ≥ +0.4 → BULLISH / ≤ -0.4 → BEARISH / mixed_count≥2 → MIXED / else NEUTRAL

거짓말 트랩:
  T1·T9 silent fabricate X — axis 실패 시 verdict="UNAVAILABLE" 명시
  T2    mock fallback X — 5축 모두 실패 시 build 자체 None 반환
  T4    임의 상수 X — 가중치 + 임계 모두 명시 박음
  T29   분모 가용 weight 합으로 정규화 (missing axis 무시)

Memory: feedback_brain_synthesizer_role / feedback_brain_evolution_admin_sync /
        project_estate_brain_kickoff / project_market_horizon (VERITY 짝)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import statistics
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
KST = timezone(timedelta(hours=9))
OUTPUT_PATH = REPO_ROOT / "data" / "estate_market_horizon.json"

ESTATE_API_BASE_DEFAULT = "https://project-yw131.vercel.app"
TIMEOUT_SEC = 15

_logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# 5축 spec — weight + endpoint + verdict 추출 함수
# ─────────────────────────────────────────────────────────────────────

# 가중치 — T4 정합 (임의 상수 X, 산식 박음).
# 사이클 + 섹터 = 시장 폭 (각 0.25)
# 거시 = long-term (0.20)
# 정책 + 지역 = 단기 충격 / micro (각 0.15)
# 합 = 1.00
WEIGHTS = {
    "macro": 0.20,
    "cycle": 0.25,
    "policy": 0.15,
    "region": 0.15,
    "sector": 0.25,
}

# verdict → score 매핑
VERDICT_SCORE = {
    "BULLISH": 1,
    "NEUTRAL": 0,
    "BEARISH": -1,
    "MIXED": 0,  # mixed 는 score 0 + mixed_count 가산
    "UNAVAILABLE": None,  # weighted avg 분모 제외
}

# 종합 verdict 임계
OVERALL_BULLISH_THRESHOLD = 0.4
OVERALL_BEARISH_THRESHOLD = -0.4

# LANDEX scores 평균 → verdict 산식 (자체 신호 v0)
LANDEX_MEAN_BULLISH = 65
LANDEX_MEAN_BEARISH = 45
LANDEX_STDEV_MIXED = 12  # 25구 점수 분산 12 이상 = MIXED 시그널

# Cycle stage → verdict 매핑 (EstateHorizon V0 산식 정합)
CYCLE_STAGE_TO_VERDICT = {
    "recovery": "BULLISH",
    "expansion": "BULLISH",
    "peak": "MIXED",  # 꼭대기 — 양가 신호
    "contraction": "BEARISH",
    "depression": "BEARISH",
}


def _get_base() -> str:
    return (os.environ.get("ESTATE_API_BASE", "") or ESTATE_API_BASE_DEFAULT).strip().rstrip("/")


def _fetch_endpoint(path: str) -> Optional[Dict[str, Any]]:
    """endpoint 호출 + JSON 파싱. 실패 시 None."""
    base = _get_base()
    url = f"{base}{path}"
    try:
        r = requests.get(url, timeout=TIMEOUT_SEC)
        if r.status_code != 200:
            _logger.warning("endpoint %s returned %d", path, r.status_code)
            return None
        return r.json()
    except (requests.RequestException, ValueError, json.JSONDecodeError) as e:
        _logger.warning("endpoint %s fetch failed: %s", path, e)
        return None


# ─────────────────────────────────────────────────────────────────────
# 5축 verdict 추출
# ─────────────────────────────────────────────────────────────────────

def _axis_macro() -> Dict[str, Any]:
    """거시 axis — macro-bridge verdict 필드 우선. 부재 시 NEUTRAL."""
    out: Dict[str, Any] = {"name": "거시", "weight": WEIGHTS["macro"], "verdict": "UNAVAILABLE"}
    payload = _fetch_endpoint("/api/estate/macro-bridge")
    if not payload:
        out["_error"] = "endpoint unavailable"
        return out

    # macro-bridge schema — verdict 또는 overall_verdict 필드 우선
    verdict = (
        payload.get("verdict")
        or payload.get("overall_verdict")
        or (payload.get("narrative") or {}).get("verdict")
    )
    if verdict in VERDICT_SCORE:
        out["verdict"] = verdict
    else:
        # verdict 필드 부재 — NEUTRAL fallback (graceful, T1 정합: 사유 명시)
        out["verdict"] = "NEUTRAL"
        out["_fallback_reason"] = "verdict 필드 부재, NEUTRAL"

    out["as_of"] = payload.get("generated_at") or payload.get("as_of") or ""
    # 핵심 지표만 raw 노출
    if isinstance(payload.get("indicators"), list):
        out["raw_indicators"] = [
            {
                "name": ind.get("name") or ind.get("label"),
                "value": ind.get("value") or ind.get("latest"),
            }
            for ind in payload["indicators"][:4]
        ]
    return out


def _axis_cycle() -> Dict[str, Any]:
    """사이클 axis — EstateHorizon stage → verdict 매핑."""
    out: Dict[str, Any] = {"name": "사이클", "weight": WEIGHTS["cycle"], "verdict": "UNAVAILABLE"}
    payload = _fetch_endpoint("/api/estate/horizon")
    if not payload:
        out["_error"] = "endpoint unavailable"
        return out

    stage = (
        payload.get("cycle_stage")
        or payload.get("stage")
        or (payload.get("classification") or {}).get("stage")
    )
    if stage in CYCLE_STAGE_TO_VERDICT:
        out["verdict"] = CYCLE_STAGE_TO_VERDICT[stage]
        out["stage"] = stage
    else:
        out["verdict"] = "NEUTRAL"
        out["_fallback_reason"] = f"stage 미인식: {stage}"

    out["as_of"] = payload.get("generated_at") or payload.get("as_of") or ""
    return out


def _axis_policy() -> Dict[str, Any]:
    """정책 axis — PolicyPulse weekly verdict."""
    out: Dict[str, Any] = {"name": "정책", "weight": WEIGHTS["policy"], "verdict": "UNAVAILABLE"}
    payload = _fetch_endpoint("/api/estate/policy-narrative")
    if not payload:
        out["_error"] = "endpoint unavailable (첫 cron 전 가능, 월요일 KST 06:30)"
        return out

    verdict = payload.get("verdict")
    if verdict in VERDICT_SCORE:
        out["verdict"] = verdict
    else:
        out["verdict"] = "NEUTRAL"
        out["_fallback_reason"] = "verdict 필드 부재"

    out["as_of"] = payload.get("generated_at", "")
    if payload.get("market_overview"):
        out["overview"] = payload["market_overview"][:200]
    return out


def _axis_region() -> Dict[str, Any]:
    """지역 axis — LANDEX scores 25구 평균 + 분산 → verdict 룰 (자체 신호 v0)."""
    out: Dict[str, Any] = {"name": "지역", "weight": WEIGHTS["region"], "verdict": "UNAVAILABLE"}
    payload = _fetch_endpoint("/api/landex/scores")
    if not payload or not isinstance(payload.get("data"), list):
        out["_error"] = "endpoint unavailable or no data"
        return out

    scores = []
    for row in payload["data"]:
        v = row.get("landex")
        if isinstance(v, (int, float)):
            scores.append(float(v))

    if not scores:
        out["_error"] = "LANDEX 점수 0건"
        return out

    mean_val = round(statistics.mean(scores), 2)
    stdev_val = round(statistics.stdev(scores), 2) if len(scores) >= 2 else 0

    if stdev_val >= LANDEX_STDEV_MIXED and mean_val < LANDEX_MEAN_BULLISH:
        verdict = "MIXED"  # 분산 크고 평균 강세 아님 = 지역 차별화
    elif mean_val >= LANDEX_MEAN_BULLISH:
        verdict = "BULLISH"
    elif mean_val <= LANDEX_MEAN_BEARISH:
        verdict = "BEARISH"
    else:
        verdict = "NEUTRAL"

    out["verdict"] = verdict
    out["mean_landex"] = mean_val
    out["stdev_landex"] = stdev_val
    out["n_gu"] = len(scores)
    out["as_of"] = payload.get("month") or payload.get("generated_at") or ""
    return out


def _axis_sector() -> Dict[str, Any]:
    """섹터 axis — SectorPulse overall_verdict."""
    out: Dict[str, Any] = {"name": "섹터", "weight": WEIGHTS["sector"], "verdict": "UNAVAILABLE"}
    payload = _fetch_endpoint("/api/estate/sector-pulse")
    if not payload:
        out["_error"] = "endpoint unavailable (첫 cron 전 가능, 월요일 KST 07:00)"
        return out

    verdict = payload.get("overall_verdict")
    if verdict in VERDICT_SCORE:
        out["verdict"] = verdict
    else:
        out["verdict"] = "NEUTRAL"
        out["_fallback_reason"] = f"overall_verdict 미인식: {verdict}"

    out["as_of"] = payload.get("generated_at", "")
    # 섹터별 verdict 카운트
    if isinstance(payload.get("sectors"), list):
        sector_verdicts = []
        for s in payload["sectors"]:
            v = s.get("verdict")
            if v and v != "UNAVAILABLE":
                sector_verdicts.append({"name": s.get("name"), "verdict": v})
        out["sectors_breakdown"] = sector_verdicts
    return out


# ─────────────────────────────────────────────────────────────────────
# 종합 verdict
# ─────────────────────────────────────────────────────────────────────

def _compute_overall(axes: List[Dict[str, Any]]) -> Tuple[str, float, str]:
    """5축 weighted average → 종합 verdict + rationale."""
    weighted_sum = 0.0
    weight_total = 0.0
    mixed_count = 0
    parts = []

    for ax in axes:
        v = ax.get("verdict")
        w = ax.get("weight", 0)
        score = VERDICT_SCORE.get(v)
        if score is None:
            # UNAVAILABLE — 분모 제외
            parts.append(f"{ax['name']} 데이터부재")
            continue
        weighted_sum += w * score
        weight_total += w
        if v == "MIXED":
            mixed_count += 1
        parts.append(f"{ax['name']} {v}")

    if weight_total == 0:
        return "UNAVAILABLE", 0.0, "5축 모두 데이터부재"

    weighted_avg = round(weighted_sum / weight_total, 3)

    if weighted_avg >= OVERALL_BULLISH_THRESHOLD:
        overall = "BULLISH"
    elif weighted_avg <= OVERALL_BEARISH_THRESHOLD:
        overall = "BEARISH"
    elif mixed_count >= 2:
        overall = "MIXED"
    else:
        overall = "NEUTRAL"

    rationale = " · ".join(parts) + f" (가중평균 {weighted_avg:+.2f})"
    return overall, weighted_avg, rationale


def _build_narrative(overall: str, weighted_avg: float, axes: List[Dict[str, Any]]) -> str:
    """rule-based 한 줄 요약 (T2 — LLM 호출 X)."""
    bullish = [ax["name"] for ax in axes if ax.get("verdict") == "BULLISH"]
    bearish = [ax["name"] for ax in axes if ax.get("verdict") == "BEARISH"]
    mixed = [ax["name"] for ax in axes if ax.get("verdict") == "MIXED"]

    if overall == "BULLISH":
        base = f"{'·'.join(bullish)} 강세 주도"
        if bearish:
            base += f", {'·'.join(bearish)} 약세 부분 상쇄"
        return base + f". 종합 강세 (가중평균 {weighted_avg:+.2f})."
    if overall == "BEARISH":
        base = f"{'·'.join(bearish)} 약세 주도"
        if bullish:
            base += f", {'·'.join(bullish)} 강세 부분 상쇄"
        return base + f". 종합 약세 (가중평균 {weighted_avg:+.2f})."
    if overall == "MIXED":
        return f"강세({'·'.join(bullish) or '없음'}) ↔ 약세({'·'.join(bearish) or '없음'}) 혼조. MIXED 신호 {len(mixed)}건."
    if overall == "UNAVAILABLE":
        return "5축 모두 데이터 부재. 다음 cron 재시도."
    return f"신호 균형 (가중평균 {weighted_avg:+.2f}). 명확한 방향 부재."


def build() -> Optional[Dict[str, Any]]:
    print("[market_horizon] 5축 페치 중…", file=sys.stderr)
    axes = [
        ("macro", _axis_macro),
        ("cycle", _axis_cycle),
        ("policy", _axis_policy),
        ("region", _axis_region),
        ("sector", _axis_sector),
    ]
    results = []
    axes_dict = {}
    for key, fn in axes:
        res = fn()
        res["key"] = key
        results.append(res)
        axes_dict[key] = res
        print(f"  ▶ {key}: {res['verdict']}", file=sys.stderr)

    overall, weighted_avg, rationale = _compute_overall(results)
    if overall == "UNAVAILABLE":
        _logger.error("market_horizon: 5축 모두 부재 — JSON 안 씀")
        return None

    narrative = _build_narrative(overall, weighted_avg, results)

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "verdict": overall,
        "weighted_score": weighted_avg,
        "rationale": rationale,
        "narrative": narrative,
        "axes": axes_dict,
        "thresholds": {
            "bullish": OVERALL_BULLISH_THRESHOLD,
            "bearish": OVERALL_BEARISH_THRESHOLD,
            "weights": WEIGHTS,
        },
    }


def _write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    result = build()
    if result is None:
        print("[market_horizon] build 실패 — 이전 JSON 유지", file=sys.stderr)
        return 1
    _write_json_atomic(OUTPUT_PATH, result)
    valid = sum(1 for ax in result["axes"].values() if ax.get("verdict") != "UNAVAILABLE")
    print(
        f"[market_horizon] 완료 verdict={result['verdict']} score={result['weighted_score']} valid={valid}/5",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
