"""universe_candidates — daily_analysis_full 의 STEP 2 fast path 헬퍼.

배경 (2026-05-10): universe_scan_builder 가 별도 cron 으로 적재한
data/universe_candidates.json 을 읽고, stale 시 None 반환 (caller inline fallback).

거짓말 트랩 정합 (feedback_data_collection_verification_mandatory):
  - silent skip 절대 금지 — stderr 에 cache hit / stale / miss outcome 명시
  - 신선도 체크 (max_stale_hours default 2)
  - 한 process 1회 로드 + cache (같은 main.py run 안 재호출 X)

메모리 정합:
  - feedback_macro_timestamp_policy: collected_at 메타 보존
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
SNAPSHOT_PATH = os.path.join(_REPO_ROOT, "data", "universe_candidates.json")

DEFAULT_MAX_STALE_HOURS = 2

_cache: Optional[Dict[str, Any]] = None
_loaded = False


def _now_kst() -> datetime:
    return datetime.now(KST)


def load_universe_candidates(
    max_stale_hours: float = DEFAULT_MAX_STALE_HOURS,
    force_reload: bool = False,
) -> Optional[Dict[str, Any]]:
    """snapshot 1회 로드 후 process 캐시. stale 시 None.

    Returns:
      dict {candidates, collected_at, diagnostics} 또는 None.
    """
    global _cache, _loaded
    if _loaded and not force_reload:
        return _cache

    _loaded = True
    _cache = None

    if not os.path.isfile(SNAPSHOT_PATH):
        sys.stderr.write(f"[universe_candidates] miss — file 없음 ({SNAPSHOT_PATH})\n")
        return None

    try:
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            snap = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write(f"[universe_candidates] miss — read 실패: {e}\n")
        return None

    collected_at = snap.get("collected_at")
    if not collected_at:
        sys.stderr.write("[universe_candidates] miss — collected_at 누락\n")
        return None

    try:
        ts = datetime.fromisoformat(collected_at)
    except ValueError:
        sys.stderr.write(f"[universe_candidates] miss — collected_at 파싱 실패: {collected_at}\n")
        return None

    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=KST)

    age_h = (_now_kst() - ts).total_seconds() / 3600.0
    if age_h > max_stale_hours:
        sys.stderr.write(
            f"[universe_candidates] stale — age={age_h:.2f}h > {max_stale_hours}h "
            f"collected_at={collected_at} (fallback inline filter pipeline)\n"
        )
        return None

    cands = snap.get("candidates") or []
    if not cands:
        sys.stderr.write(
            f"[universe_candidates] miss — candidates 0건 collected_at={collected_at}\n"
        )
        return None

    diag = snap.get("diagnostics", {})
    sys.stderr.write(
        f"[universe_candidates] HIT — age={age_h:.2f}h candidates={len(cands)} "
        f"(KR {diag.get('kr_count', '?')} + US {diag.get('us_count', '?')}) "
        f"collected_at={collected_at}\n"
    )
    _cache = snap
    return snap


def reset_cache() -> None:
    """테스트용."""
    global _cache, _loaded
    _cache = None
    _loaded = False
