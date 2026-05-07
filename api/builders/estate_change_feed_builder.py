"""
estate_change_feed_builder.py — ChangeFeed JSON 빌더 (P2 wire)

contract: estate/docs/contract_change_feed.md (v0.2 — 2 카테고리 = regulation + catalyst)

흐름 (hero_briefing 빌더와 동일 인프라 재사용):
    ① collect_policies(72h, minister_filter=None) — 전체 부처
    ② rough_relevance_filter — 부동산 무관 정책 1차 컷
    ③ classify — 8 카테고리(+stage+affected_regions) 산출
    ④ 8 → 2 카테고리 압축 (CATEGORY_MAP)
    ⑤ ChangeFeed schema 로 정렬 + cap (occurred_at DESC, items 상한)
    ⑥ atomic write → estate/data/estate_change_feed.json

8 → 2 카테고리 매핑 (contract v0.2 §1 정합):
    classifier 출력         ChangeFeed v0.2
    ───────────────────    ────────────────
    regulation             regulation   (시장 규제 — 투기지역/조정대상지역/전매/...)
    tax                    regulation   (보유세·공시가격·종부세·양도세 — 규제 성격)
    loan                   regulation   (LTV/DSR/DTI/대출 한도 — 규제 성격)
    catalyst               catalyst     (교통·복합개발·일반 호재)
    supply                 catalyst     (공공주택·분양·공급 — 호재성)
    redev                  catalyst     (재건축·재개발·리모델링 — 호재성)
    rental                 catalyst     (임대주택·청년주택 — 호재성)
    anomaly                (drop)       (v0.2 폐기 — P2 신설 모듈 부담)

severity 매핑 (classifier stage → ChangeFeed severity):
    stage >= 3 → high
    stage == 2 → mid
    stage <= 1 → low

거짓말 트랩:
    T1·T9   fabricate·silent X — 실패 시 items=[] + log
    T2      mock fallback X — 빌더 자체가 실 데이터, 실패 시 items=[]
    T18     anthropic_calls.jsonl 누적 (classifier 가 LLM 호출 시 자동 기록)
    T29     source URL 절대 — collect_policies 가 절대 URL 산출
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from api.analyzers.policy_classifier import classify
from api.analyzers.policy_keywords import rough_relevance_filter
from api.collectors.policy_collector import collect_policies as fetch_policies

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_REPO_ROOT, "data", "estate_change_feed.json")  # hero_briefing 패턴 정합

SCHEMA_VERSION = "1.0"
NAMESPACE = "estate"
DEFAULT_LOOKBACK_HOURS = 72  # contract §2 query default
ITEMS_CAP = 10  # contract §2 N=10 cap (feedback_estate_density_first)
SUMMARY_MAX_LEN = 80  # contract §1 example "(≤80자)"

# 8 → 2 카테고리 매핑 (contract v0.2 §1)
CATEGORY_MAP: Dict[str, Optional[str]] = {
    "regulation": "regulation",
    "tax": "regulation",
    "loan": "regulation",
    "catalyst": "catalyst",
    "supply": "catalyst",
    "redev": "catalyst",
    "rental": "catalyst",
    "anomaly": None,  # v0.2 폐기
}

VALID_OUTPUT_CATEGORIES = ("regulation", "catalyst")


def build(
    now: Optional[datetime] = None,
    lookback_hours: int = DEFAULT_LOOKBACK_HOURS,
    _collect: Optional[Callable] = None,
    _classify: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    ChangeFeed payload dict 반환. 실패 시에도 항상 dict (T1 — items=[] fallback).

    Returns:
        contract_change_feed.md §2 Response schema 준수 dict.
    """
    now = now or datetime.now(timezone.utc)
    collect = _collect or fetch_policies
    classify_fn = _classify or classify

    classified = _collect_and_classify(collect, classify_fn, now, lookback_hours)
    items = _to_feed_items(classified)
    items = sorted(items, key=lambda it: it["occurred_at"], reverse=True)[:ITEMS_CAP]
    counts = {c: 0 for c in VALID_OUTPUT_CATEGORIES}
    for it in items:
        counts[it["category"]] += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "fetched_at": _to_kst_iso(now),
        "namespace": NAMESPACE,
        "scenario": "live",
        "lookback_hours": lookback_hours,
        "items": items,
        "category_counts": counts,
        "total": len(items),
    }


def main() -> int:
    """cron entry — build → write. 빈 items 도 정상 산출 (T1)."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    payload = build()
    _write_json_atomic(OUTPUT_PATH, payload)
    logger.info(
        "main: wrote %s (items=%d regulation=%d catalyst=%d)",
        OUTPUT_PATH, payload["total"],
        payload["category_counts"].get("regulation", 0),
        payload["category_counts"].get("catalyst", 0),
    )
    return 0


# ─────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────

def _collect_and_classify(
    collect: Callable, classify_fn: Callable, now: datetime, lookback_hours: int,
) -> List[Dict[str, Any]]:
    """72h 수집 → prefilter → classify. 단일 item 실패는 skip (T9 — log 만)."""
    try:
        raw = collect(lookback_hours=lookback_hours, minister_filter=None, now=now)
    except Exception as e:
        logger.error("change_feed_builder: collect raised: %s", e)
        return []

    relevant = [p for p in raw if rough_relevance_filter(p)]

    classified: List[Dict[str, Any]] = []
    for p in relevant:
        try:
            cls = classify_fn(p)
        except Exception as e:
            logger.error("change_feed_builder: classify failed id=%s: %s", p.get("id"), e)
            continue
        classified.append({**p, **cls})
    return classified


def _to_feed_items(classified: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """classifier 산출물 → ChangeFeed item 매핑. CATEGORY_MAP None 시 drop."""
    out: List[Dict[str, Any]] = []
    for c in classified:
        src_cat = c.get("category")
        dst_cat = CATEGORY_MAP.get(src_cat)
        if dst_cat is None:
            continue

        occurred_at = c.get("published_at")
        if not occurred_at:
            continue

        out.append({
            "id": _safe_id(c.get("id"), occurred_at, c.get("title")),
            "category": dst_cat,
            "severity": _stage_to_severity(c.get("stage")),
            "region_label": _first_region_or_nationwide(c.get("affected_regions")),
            "title": (c.get("title") or "").strip(),
            "summary": _summarize(c.get("raw_text")),
            "occurred_at": _normalize_iso(occurred_at),
            "source_name": (c.get("source_name") or "").strip(),
            "source_url": (c.get("source_url") or "").strip(),
            "drill_down_url": None,
        })
    return out


def _stage_to_severity(stage: Optional[int]) -> str:
    if stage is None:
        return "low"
    if stage >= 3:
        return "high"
    if stage == 2:
        return "mid"
    return "low"


def _first_region_or_nationwide(regions: Optional[List[str]]) -> str:
    if not regions:
        return "전국"
    return regions[0]


def _summarize(raw_text: Optional[str]) -> str:
    """contract §1 example '(≤80자)' — 80자 컷 + 말줄임표."""
    if not raw_text:
        return ""
    text = raw_text.strip().replace("\n", " ").replace("\r", " ")
    if len(text) <= SUMMARY_MAX_LEN:
        return text
    return text[:SUMMARY_MAX_LEN - 1] + "…"


def _safe_id(item_id: Optional[str], occurred_at: str, title: Optional[str]) -> str:
    """policy_collector 가 NewsItemId 폴백 처리하므로 보통 비지 않음. 보조 폴백."""
    if item_id:
        return f"feed_{item_id}"
    import hashlib
    seed = (occurred_at or "") + "|" + (title or "")
    return f"feed_{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:16]}"


def _normalize_iso(iso: str) -> str:
    """policy_collector 는 UTC ISO 산출. KST ISO 로 변환 (UI 일관성)."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return iso
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return _to_kst_iso(dt)


def _to_kst_iso(dt: datetime) -> str:
    kst = timezone(timedelta(hours=9))
    return dt.astimezone(kst).isoformat(timespec="seconds")


# ─────────────────────────────────────────────────
# Atomic write
# ─────────────────────────────────────────────────

def _write_json_atomic(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


if __name__ == "__main__":
    raise SystemExit(main())
