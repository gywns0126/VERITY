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

DEFAULT_MAX_STALE_HOURS = 26  # 어제 cache 까지 허용 (universe_scan 1회 결함 흡수)
_DART_MAX_STALE_DAYS = 8

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

    # 🚨 2026-09-02 — snapshot fast path 에도 DART 를 다시 주입한다.
    # universe_scan 이 KR 수집 실패분을 직전 snapshot 으로 대체하면(kr_used_prev=True),
    # scan 내부의 pre-attach 분모는 0/0 이다. daily_analysis 는 그 snapshot 을 그대로
    # 채점해 DART 원천에 있던 재무 8키가 recommendations 에서 전부 사라졌다
    # (key_coverage 기준 10→18). JSON 로드 뒤 멱등 보강하면 정상 snapshot 은 유지하고,
    # 이월 KR 후보만 복구한다. 실패해도 후보 로드는 유지하되 결과를 자기신고한다.
    try:
        from api.utils.dart_pre_attach import attach_dart_to_stocks

        dart_result = attach_dart_to_stocks(
            cands,
            max_stale_days=_DART_MAX_STALE_DAYS,
        )
        snap["_load_enrichment"] = {"dart": dart_result}
        sys.stderr.write(
            "[universe_candidates] DART reload enrichment — "
            f"attached={dart_result.get('attached_n', 0)}/"
            f"{dart_result.get('kr_total_n', 0)} "
            f"cache_hit={dart_result.get('cache_hit', False)}\n"
        )
    except Exception as e:  # noqa: BLE001 — DART 보강 실패가 후보 로드를 죽이지 않는다
        snap["_load_enrichment"] = {
            "dart": {"cache_hit": False, "error": f"{type(e).__name__}: {e}"[:160]}
        }
        sys.stderr.write(
            f"[universe_candidates] DART reload enrichment 실패: {type(e).__name__}: {e}\n"
        )

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
