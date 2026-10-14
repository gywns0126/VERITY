"""universe_candidates — daily_analysis_full 의 STEP 2 fast path 헬퍼.

배경 (2026-05-10): universe_scan_builder 가 별도 cron 으로 적재한
data/universe_candidates.json 의 완료·원천 시각·producer identity를 검사한다.
실패 시 None 반환; main.py는 inline scan 없이 중단한다.

거짓말 트랩 정합 (feedback_data_collection_verification_mandatory):
  - silent skip 절대 금지 — stderr 에 cache hit / stale / miss outcome 명시
  - 신선도 체크 (max_stale_hours default 2)
  - 한 process 1회 로드 + cache (같은 main.py run 안 재호출 X)

메모리 정합:
  - feedback_macro_timestamp_policy: collected_at 메타 보존
  - 실패한 scan attempt는 마지막 정상 파일을 보존하고 소비 시 원 시각으로 검사
"""
from __future__ import annotations

import json
import hashlib
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
_cache_contract = None


def _now_kst() -> datetime:
    return datetime.now(KST)


def snapshot_rejection(snap: Any, max_stale_hours: float, now: datetime,
                       expected_scan_id: str = "") -> str | None:
    """Validate completed producer output before enrichment or analysis."""
    if not isinstance(snap, dict):
        return "snapshot must be an object"
    diag = snap.get("diagnostics") or {}
    if not isinstance(diag, dict):
        return "diagnostics malformed"
    if (snap.get("schema_version") != "v1" or not snap.get("scan_id")
            or not snap.get("completed_at")):
        return "legacy/incomplete snapshot; run upgraded Universe Scan first"
    if diag.get("ok") is not True or diag.get("used_prev_snapshot") or diag.get("kr_starved"):
        return "scan unsuccessful or full previous-snapshot fallback"
    if expected_scan_id and snap["scan_id"] != expected_scan_id:
        return f"producer identity mismatch: expected={expected_scan_id} actual={snap['scan_id']}"
    if (not isinstance(snap.get("candidates"), list) or not snap["candidates"]
            or any(not isinstance(row, dict) or not row.get("ticker") for row in snap["candidates"])):
        return "candidates empty or malformed"
    try:
        times = []
        for key in ("collected_at", "completed_at"):
            ts = datetime.fromisoformat(str(snap[key]))
            times.append(ts if ts.tzinfo else ts.replace(tzinfo=KST))
        source, completed = times
        age_h = (now - source).total_seconds() / 3600
        if source > completed or completed > now or age_h > max_stale_hours:
            return f"invalid/stale scan time: age={age_h:.2f}h limit={max_stale_hours}h"
        # Existing KR splice policy is 96h, independently of the fresh US scan.
        if diag.get("kr_used_prev"):
            sources = snap.get("source_as_of") or {}
            if not isinstance(sources, dict):
                return "market source timestamps malformed"
            origin = sources.get("KR")
            kr_ts = datetime.fromisoformat(str(origin))
            kr_ts = kr_ts if kr_ts.tzinfo else kr_ts.replace(tzinfo=KST)
            if not 0 <= (now - kr_ts).total_seconds() / 3600 <= 96:
                return "KR carried source expired or future"
    except (KeyError, ValueError, TypeError):
        return "source/completion timestamp missing or malformed"
    return None


def load_universe_candidates(
    max_stale_hours: float = DEFAULT_MAX_STALE_HOURS,
    force_reload: bool = False,
) -> Optional[Dict[str, Any]]:
    """snapshot 1회 로드 후 process 캐시. stale 시 None.

    Returns:
      dict {candidates, collected_at, diagnostics} 또는 None.
    """
    global _cache, _loaded, _cache_contract
    expected_scan_id = os.environ.get("UNIVERSE_EXPECTED_SCAN_ID", "")
    contract = (max_stale_hours, expected_scan_id)
    if _loaded and not force_reload and contract == _cache_contract:
        return _cache

    _loaded = True
    _cache = None
    _cache_contract = contract

    if not os.path.isfile(SNAPSHOT_PATH):
        sys.stderr.write(f"[universe_candidates] miss — file 없음 ({SNAPSHOT_PATH})\n")
        return None

    try:
        with open(SNAPSHOT_PATH, "rb") as f:
            body = f.read()
        snap = json.loads(body)
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write(f"[universe_candidates] miss — read 실패: {e}\n")
        return None

    loaded_at = _now_kst()
    rejected = snapshot_rejection(snap, max_stale_hours, loaded_at, expected_scan_id)
    if rejected:
        sys.stderr.write(f"[universe_candidates] rejected — {rejected}\n")
        return None

    collected_at = snap["collected_at"]
    ts = datetime.fromisoformat(collected_at)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=KST)

    age_h = (loaded_at - ts).total_seconds() / 3600.0
    cands = snap["candidates"]

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
    snap["_load_provenance"] = {
        "scan_id": snap["scan_id"],
        "collected_at": collected_at,
        "completed_at": snap["completed_at"],
        "source_as_of": snap.get("source_as_of"),
        "timestamp_basis": snap.get("timestamp_basis"),
        "producer_sha": snap.get("producer_sha"),
        "snapshot_sha256": hashlib.sha256(body).hexdigest(),
        "hash_algorithm": "sha256-exact-file-bytes-before-enrichment",
        "loaded_at": loaded_at.isoformat(timespec="seconds"),
        "snapshot_age_hours": round(age_h, 3),
        "kr_used_prev": bool(diag.get("kr_used_prev")),
        "kr_source_scan_id": snap.get("kr_source_scan_id"),
        "scan_candidate_count": len(cands),
    }
    sys.stderr.write(
        f"[universe_candidates] HIT — age={age_h:.2f}h candidates={len(cands)} "
        f"(KR {diag.get('kr_count', '?')} + US {diag.get('us_count', '?')}) "
        f"collected_at={collected_at}\n"
    )
    _cache = snap
    return snap


def reset_cache() -> None:
    """테스트용."""
    global _cache, _loaded, _cache_contract
    _cache = None
    _loaded = False
    _cache_contract = None
