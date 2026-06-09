"""macro_snapshot — daily_analysis_full 의 fast path 헬퍼.

배경 (2026-05-10): macro_collect_builder 가 별도 cron 으로 적재한
data/macro_snapshot.json 을 읽고, stale 시 None 반환 (caller inline fetch fallback).

거짓말 트랩 정합 (feedback_data_collection_verification_mandatory):
  - silent skip 절대 금지 — stderr 에 cache hit / stale / miss outcome 명시
  - 신선도 체크 (max_stale_minutes default 30)
  - 한 process 1회 로드 (lru_cache) — 같은 main.py run 안에서 재호출 X

메모리 정합:
  - feedback_macro_timestamp_policy: collected_at 메타 보존 (caller 가 portfolio 에 넣어야)
  - feedback_continuous_evolution 4 가드 — 롤백 path = inline fetch fallback 보존
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SNAPSHOT_PATH = os.path.join(_REPO_ROOT, "data", "macro_snapshot.json")

DEFAULT_MAX_STALE_MIN = 30

_cache: Optional[Dict[str, Any]] = None
_loaded = False


def _now_kst() -> datetime:
    return datetime.now(KST)


def load_macro_snapshot(
    max_stale_minutes: int = DEFAULT_MAX_STALE_MIN,
    force_reload: bool = False,
) -> Optional[Dict[str, Any]]:
    """snapshot 1회 로드 후 process 캐시. stale 시 None.

    Returns:
      dict {macro, bonds, global_events, collected_at, diagnostics} 또는 None.
    """
    global _cache, _loaded
    if _loaded and not force_reload:
        return _cache

    _loaded = True
    _cache = None

    if not os.path.isfile(SNAPSHOT_PATH):
        sys.stderr.write(f"[macro_snapshot] miss — file 없음 ({SNAPSHOT_PATH})\n")
        return None

    try:
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            snap = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write(f"[macro_snapshot] miss — read 실패: {e}\n")
        return None

    collected_at = snap.get("collected_at")
    if not collected_at:
        sys.stderr.write("[macro_snapshot] miss — collected_at 누락\n")
        return None

    try:
        # ISO with tz "+09:00" parse
        ts = datetime.fromisoformat(collected_at)
    except ValueError:
        sys.stderr.write(f"[macro_snapshot] miss — collected_at 파싱 실패: {collected_at}\n")
        return None

    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=KST)

    age_min = (_now_kst() - ts).total_seconds() / 60.0
    if age_min > max_stale_minutes:
        sys.stderr.write(
            f"[macro_snapshot] stale — age={age_min:.1f}min > {max_stale_minutes}min "
            f"collected_at={collected_at} (fallback inline fetch)\n"
        )
        return None

    sys.stderr.write(
        f"[macro_snapshot] HIT — age={age_min:.1f}min collected_at={collected_at}\n"
    )
    _cache = snap
    return snap


def reset_cache() -> None:
    """테스트용."""
    global _cache, _loaded
    _cache = None
    _loaded = False
