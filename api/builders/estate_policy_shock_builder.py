"""
estate_policy_shock_builder.py — PolicyShockTimeline 데이터 빌더

archive (estate_policy_archive.jsonl) 를 N일 lookback 으로 read → impact_score 산출 →
시간축 시각화용 JSON 산출. ChangeFeed (72h 리스트) / HeroBriefing (1건 highlight) 와는
직교 책임. lookback 깊이 + 충격 magnitude + 부호(방향) 가 차별점.

산식 (impact_score, direction) — 자체 신호 (feedback_source_attribution_discipline):
    impact_score (0~1, magnitude) =
        stage_score   × 0.5
        + cat_weight  × 0.3
        + region_breadth × 0.2

    stage_score = stage / 4              # 0~4 → 0~1 단순 정규화
    cat_weight  = CATEGORY_WEIGHT[cat]   # 카테고리별 시장 영향력 (자체 추정, v0)
    region_breadth =
        1.0  if regions empty (=전국) or len ≥ 4
        0.7  if 2~3 regions
        0.4  if 1 region

    direction:
        regulation, tax, loan, anomaly → "negative"
        catalyst, supply, redev, rental → "positive"
        그 외 → "neutral"

    가중치 (0.5/0.3/0.2) 사유:
        stage 가 정책 사이클 진행 (발표→입법→시행) 의 직접 지표 → 가장 큰 비중.
        category 는 시장 채널 영향 (규제는 즉시 가격 충격, catalyst 는 점진) → 차순위.
        region breadth 는 전국 vs 국지 구분 → 최소 비중 (이미 stage 에 일부 반영).
        v0 자체 신호 — 운영 누적 후 retract 검토 (spec_iteration_retract_rule 정합).

출력 schema (v1.0):
    schema_version  : "1.0"
    fetched_at      : KST ISO
    namespace       : "estate"
    lookback_days   : int
    items           : list — 각 archive row + impact_score + direction
    by_day          : dict — YYYY-MM-DD: {count, max_impact, net_direction_score}
    stats           : dict — by_category, by_direction, max_impact, mean_impact
    total           : int

거짓말 트랩:
    T1·T9  fabricate·silent X — archive 없으면 items=[] + log
    T2     mock X — archive 가 실 데이터 백본
    T4     confidence/score 임의 상수 X — 위 산식 명시
    T29    source_url 절대 (archive 가 절대)
"""
from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARCHIVE_PATH = os.path.join(_REPO_ROOT, "data", "estate_policy_archive.jsonl")
OUTPUT_PATH = os.path.join(_REPO_ROOT, "data", "estate_policy_shock.json")

KST = timezone(timedelta(hours=9))

SCHEMA_VERSION = "1.0"
NAMESPACE = "estate"
DEFAULT_LOOKBACK_DAYS = 30
LOOKBACK_DAYS_MAX = 90  # archive prune 과 정합

# 카테고리별 시장 영향력 가중치 — 자체 신호 (v0, retract 검토 90일 후)
CATEGORY_WEIGHT: Dict[str, float] = {
    "regulation": 1.0,
    "tax": 0.9,
    "loan": 0.9,
    "redev": 0.8,
    "supply": 0.7,
    "rental": 0.6,
    "catalyst": 0.5,
    "anomaly": 0.7,
}

NEGATIVE_CATEGORIES = {"regulation", "tax", "loan", "anomaly"}
POSITIVE_CATEGORIES = {"catalyst", "supply", "redev", "rental"}


def build(
    now: Optional[datetime] = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    archive_path: Optional[str] = None,
) -> Dict[str, Any]:
    """archive 읽어 timeline payload 산출. write 는 main 에서."""
    now = now or datetime.now(timezone.utc)
    path = archive_path or ARCHIVE_PATH
    lookback_days = max(1, min(lookback_days, LOOKBACK_DAYS_MAX))

    rows = _read_archive(path)
    cutoff_utc = now - timedelta(days=lookback_days)
    rows = [r for r in rows if _in_window(r, cutoff_utc)]

    items: List[Dict[str, Any]] = []
    by_day: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"count": 0, "max_impact": 0.0, "net_direction_score": 0.0})
    cat_counts: Dict[str, int] = defaultdict(int)
    dir_counts: Dict[str, int] = {"negative": 0, "positive": 0, "neutral": 0}
    impact_sum = 0.0
    max_impact = 0.0

    for r in rows:
        impact = _impact_score(r)
        direction = _direction(r.get("category"))
        item = {
            "id": r.get("id"),
            "title": r.get("title"),
            "source_name": r.get("source_name"),
            "source_url": r.get("source_url"),
            "published_at": r.get("published_at"),
            "category": r.get("category"),
            "stage": r.get("stage"),
            "affected_regions": r.get("affected_regions") or [],
            "impact_score": round(impact, 4),
            "direction": direction,
        }
        items.append(item)

        day = (r.get("published_at") or "")[:10]
        if day:
            cell = by_day[day]
            cell["count"] += 1
            if impact > cell["max_impact"]:
                cell["max_impact"] = round(impact, 4)
            sign = 1 if direction == "positive" else (-1 if direction == "negative" else 0)
            cell["net_direction_score"] = round(cell["net_direction_score"] + impact * sign, 4)

        if r.get("category"):
            cat_counts[r["category"]] += 1
        dir_counts[direction] += 1
        impact_sum += impact
        if impact > max_impact:
            max_impact = impact

    items.sort(key=lambda it: it.get("published_at") or "", reverse=True)
    mean_impact = (impact_sum / len(items)) if items else 0.0

    return {
        "schema_version": SCHEMA_VERSION,
        "fetched_at": now.astimezone(KST).isoformat(timespec="seconds"),
        "namespace": NAMESPACE,
        "lookback_days": lookback_days,
        "items": items,
        "by_day": dict(by_day),
        "stats": {
            "by_category": dict(cat_counts),
            "by_direction": dir_counts,
            "max_impact": round(max_impact, 4),
            "mean_impact": round(mean_impact, 4),
        },
        "total": len(items),
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    payload = build()
    _write_json_atomic(OUTPUT_PATH, payload)
    logger.info(
        "main: wrote %s (lookback=%dd items=%d max_impact=%.3f)",
        OUTPUT_PATH, payload["lookback_days"], payload["total"],
        payload["stats"]["max_impact"],
    )
    return 0


def _impact_score(row: Dict[str, Any]) -> float:
    """impact_score = stage×0.5 + cat_weight×0.3 + region_breadth×0.2. 산식 사유는 모듈 docstring."""
    stage = row.get("stage")
    stage_score = (float(stage) / 4.0) if isinstance(stage, (int, float)) else 0.0
    stage_score = max(0.0, min(1.0, stage_score))

    cat = row.get("category") or ""
    cat_weight = CATEGORY_WEIGHT.get(cat, 0.5)

    regions = row.get("affected_regions") or []
    n = len(regions)
    if n == 0:
        region_breadth = 1.0  # empty = 전국 가정 (classifier 가 명시 안 함)
    elif n >= 4:
        region_breadth = 1.0
    elif n >= 2:
        region_breadth = 0.7
    else:
        region_breadth = 0.4

    return stage_score * 0.5 + cat_weight * 0.3 + region_breadth * 0.2


def _direction(category: Optional[str]) -> str:
    if category in NEGATIVE_CATEGORIES:
        return "negative"
    if category in POSITIVE_CATEGORIES:
        return "positive"
    return "neutral"


def _read_archive(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        logger.info("policy_shock: archive missing at %s — items=[]", path)
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rows.append(json.loads(ln))
                except json.JSONDecodeError as e:
                    logger.error("policy_shock: skip malformed line: %s", e)
    except OSError as e:
        logger.error("policy_shock: read failed: %s", e)
        return []
    return rows


def _in_window(row: Dict[str, Any], cutoff_utc: datetime) -> bool:
    pa = row.get("published_at")
    if not pa:
        return False
    try:
        dt = datetime.fromisoformat(pa.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc) >= cutoff_utc


def _write_json_atomic(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


if __name__ == "__main__":
    raise SystemExit(main())
