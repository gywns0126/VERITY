"""
estate_policy_archive_builder.py — 정책 누적 archive (PolicyShockTimeline 데이터 백본)

배경:
    policy_collector 의 data.go.kr API 는 startDate/endDate 3일 제약 (72h limit).
    HeroBriefing (1건) · ChangeFeed (72h N=10) 는 짧은 lookback 으로 충분하지만
    PolicyShockTimeline 은 30~90일 시간축 시각화가 책임이라 누적 archive 가 필수.

흐름:
    ① collect_policies(72h, minister_filter=None) — ChangeFeed builder 와 동일 수집
    ② rough_relevance_filter — 부동산 무관 필터
    ③ classify — 8 카테고리(+stage+affected_regions)
    ④ jsonl read (기존) → id 셋 구성 → 신규만 append
    ⑤ 90일 초과 항목 prune (timeline 최대 lookback 90d 정합)

출력 schema (jsonl, 한 줄 = 한 정책):
    id               policy_collector NewsItemId 또는 hash
    title            제목
    source_name      MinisterCode (부처명)
    source_url       원문 URL (T29 절대)
    published_at     KST ISO (UI 일관 — ChangeFeed 정합)
    category         classifier 산출 8 카테고리
    stage            0~4
    affected_regions list[str]
    archived_at      KST ISO (이 archive 에 기록된 시점)

거짓말 트랩:
    T1·T9   fabricate·silent X — 실패 시 archive 무수정 + log
    T2      mock X — 빌더 자체가 실 데이터
    T18     anthropic_calls.jsonl 누적 (classifier 가 LLM 호출 시 자동)
    T29     source_url 절대
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from api.analyzers.policy_classifier import classify
from api.analyzers.policy_keywords import rough_relevance_filter
from api.collectors.policy_collector import collect_policies as fetch_policies

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_REPO_ROOT, "data", "estate_policy_archive.jsonl")

KST = timezone(timedelta(hours=9))

DEFAULT_LOOKBACK_HOURS = 72       # API 상한
PRUNE_DAYS = 90                   # timeline 최대 lookback (Shock builder 와 정합)


def build(
    now: Optional[datetime] = None,
    archive_path: Optional[str] = None,
    _collect: Optional[Callable] = None,
    _classify: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    72h 정책 신규분 archive append + 90d 초과 prune. write 는 main 에서.

    Returns:
        {appended: int, total_after: int, pruned: int, scanned: int}
    """
    now = now or datetime.now(timezone.utc)
    path = archive_path or OUTPUT_PATH
    collect = _collect or fetch_policies
    classify_fn = _classify or classify

    existing = _read_archive(path)
    existing_ids = {row["id"] for row in existing if "id" in row}

    try:
        raw = collect(lookback_hours=DEFAULT_LOOKBACK_HOURS, minister_filter=None, now=now)
    except Exception as e:
        logger.error("policy_archive: collect raised: %s — archive 무수정", e)
        return {"appended": 0, "total_after": len(existing), "pruned": 0, "scanned": 0}

    scanned = len(raw)
    relevant = [p for p in raw if rough_relevance_filter(p)]

    new_rows: List[Dict[str, Any]] = []
    archived_at = now.astimezone(KST).isoformat(timespec="seconds")

    for p in relevant:
        pid = p.get("id")
        if not pid or pid in existing_ids:
            continue
        try:
            cls = classify_fn(p)
        except Exception as e:
            logger.error("policy_archive: classify failed id=%s: %s", pid, e)
            continue
        row = {
            "id": pid,
            "title": (p.get("title") or "").strip(),
            "source_name": (p.get("source_name") or "").strip(),
            "source_url": (p.get("source_url") or "").strip(),
            "published_at": _normalize_kst_iso(p.get("published_at")),
            "category": cls.get("category"),
            "stage": cls.get("stage"),
            "affected_regions": cls.get("affected_regions") or [],
            "archived_at": archived_at,
        }
        new_rows.append(row)
        existing_ids.add(pid)

    merged = existing + new_rows
    cutoff = now - timedelta(days=PRUNE_DAYS)
    pruned_rows, dropped = _prune_old(merged, cutoff)

    _write_jsonl_atomic(path, pruned_rows)

    return {
        "appended": len(new_rows),
        "pruned": dropped,
        "total_after": len(pruned_rows),
        "scanned": scanned,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    stats = build()
    logger.info(
        "main: archive %s (scanned=%d appended=%d pruned=%d total=%d)",
        OUTPUT_PATH, stats["scanned"], stats["appended"],
        stats["pruned"], stats["total_after"],
    )
    return 0


def _read_archive(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
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
                    logger.error("policy_archive: skip malformed line: %s", e)
    except OSError as e:
        logger.error("policy_archive: read failed: %s", e)
        return []
    return rows


def _prune_old(rows: List[Dict[str, Any]], cutoff_utc: datetime) -> tuple[List[Dict[str, Any]], int]:
    kept: List[Dict[str, Any]] = []
    dropped = 0
    for r in rows:
        pa = r.get("published_at")
        try:
            dt = datetime.fromisoformat((pa or "").replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            kept.append(r)
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt.astimezone(timezone.utc) < cutoff_utc:
            dropped += 1
            continue
        kept.append(r)
    return kept, dropped


def _normalize_kst_iso(iso: Optional[str]) -> Optional[str]:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return iso
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST).isoformat(timespec="seconds")


def _write_jsonl_atomic(path: str, rows: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


if __name__ == "__main__":
    raise SystemExit(main())
