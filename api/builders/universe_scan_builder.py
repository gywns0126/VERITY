"""universe_scan_builder — universe scan + stock_filter 별도 cron 분리.

배경 (2026-05-10):
  daily_analysis_full 의 STEP 2 (run_filter_pipeline_with_ramp_up) 가 universe 5000
  ticker 처리 = 35분 (cooler/retry 누적). 그 후 STEP 3-12 (60 candidate × 12 외부 API
  step) = 75분. 합 110분 → watchdog 도달 SIGTERM. macro_collect 패턴 확장 = universe
  scan + filter 도 별도 cron 분리. daily_analysis 는 적재된 candidate jsonl 만 읽음.

배치:
  - cron: 평일 KST 15:30 (UTC 06:30). KR 시장 마감 (15:30) 직후 = 당일 종가 반영.
  - 산출: data/universe_candidates.json (collected_at + candidates + diagnostics)
  - daily_analysis_full STEP 2 = snapshot 읽기 fast path + max_stale 2h fallback.

거짓말 트랩 정합 (feedback_data_collection_verification_mandatory):
  - try/finally + logged stderr 표식
  - silent skip 절대 금지 — fail 시 errors[] 박고 최종 exit code 분리
  - 직전 snapshot 보존 (이번 run candidates 0건이면 file 덮어쓰기 X)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_REPO_ROOT, "data", "universe_candidates.json")

KST = timezone(timedelta(hours=9))


def _now_kst() -> datetime:
    return datetime.now(KST)


def _load_existing() -> Dict[str, Any]:
    """직전 snapshot — 이번 run 의 candidates 0건 일 때 fallback."""
    if not os.path.isfile(OUTPUT_PATH):
        return {}
    try:
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def build() -> Dict[str, Any]:
    """run_filter_pipeline_with_ramp_up 호출 → snapshot dict.

    실패 시에도 항상 dict 반환 (T1 — diagnostics 에 source 명시).
    """
    from api.analyzers.stock_filter import run_filter_pipeline_with_ramp_up

    now = _now_kst()
    started = time.time()
    candidates: List[Dict[str, Any]] = []
    error: str | None = None

    try:
        candidates = run_filter_pipeline_with_ramp_up(market_scope="all") or []
    except BaseException as e:
        error = f"{type(e).__name__}: {str(e)[:200]}"
        sys.stderr.write(f"[universe_scan] FAIL: {error}\n")

    elapsed = round(time.time() - started, 2)

    # 0건 fallback — 직전 snapshot 보존 (commit 안 해도 되도록 caller 가 판단)
    prev = _load_existing()
    used_prev = False
    if not candidates and isinstance(prev.get("candidates"), list) and prev["candidates"]:
        candidates = prev["candidates"]
        used_prev = True
        sys.stderr.write(
            f"[universe_scan] used_prev=True (이번 run 0건, 직전 snapshot {len(candidates)}건)\n"
        )

    kr_count = sum(1 for c in candidates if c.get("currency") != "USD")
    us_count = sum(1 for c in candidates if c.get("currency") == "USD")

    # US 유니버스 소스 de-silence — 캐시 부재 시 fallback(S&P100+core) 명시.
    # universe_us.json gitignored + 생성기 없음 → 상시 fallback. silent degradation 아닌 의식 상태.
    _us_cache = os.path.join(_REPO_ROOT, "data", "cache", "universe_us.json")
    us_universe_source = "cache" if os.path.exists(_us_cache) else "static_fallback"

    diagnostics = {
        "ok": error is None and bool(candidates),
        "candidates_count": len(candidates),
        "kr_count": kr_count,
        "us_count": us_count,
        "us_universe_source": us_universe_source,  # "static_fallback" = US ~S&P100 (KR-first interim)
        "ramp_up_stage": int(os.environ.get("UNIVERSE_RAMP_UP_STAGE", "0") or 0),
        "ramp_up_note": "5000 = cap(상한), 목표 아님 — 실 유니버스 = 품질 floor 통과 전체",
        "elapsed_s": elapsed,
        "used_prev_snapshot": used_prev,
        "error": error,
    }

    return {
        "collected_at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "candidates": candidates,
        "diagnostics": diagnostics,
        "schema_version": "v0",
    }


def _atomic_write(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    os.replace(tmp, path)


def main() -> int:
    snapshot = build()
    _atomic_write(OUTPUT_PATH, snapshot)
    diag = snapshot.get("diagnostics", {})
    sys.stderr.write(
        f"[universe_scan] snapshot OK at={snapshot.get('collected_at')} "
        f"candidates={diag.get('candidates_count')} (KR {diag.get('kr_count')} + US {diag.get('us_count')}) "
        f"stage={diag.get('ramp_up_stage')} elapsed={diag.get('elapsed_s')}s "
        f"used_prev={diag.get('used_prev_snapshot')}\n"
    )

    # 편승 — data_pipeline_health 갱신 (별도 cron 추가 X)
    try:
        from api.observability.data_pipeline_health import write_data_pipeline_health
        write_data_pipeline_health()
    except Exception as _e:
        sys.stderr.write(f"[universe_scan] data_pipeline_health 갱신 실패(무시): {_e}\n")

    if not diag.get("ok"):
        sys.stderr.write(f"[universe_scan] FATAL — error={diag.get('error')}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
