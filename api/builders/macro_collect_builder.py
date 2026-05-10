"""macro_collect_builder — 외부 매크로/채권/글로벌이벤트 collector 별도 cron 분리.

배경 (2026-05-10):
  - daily_analysis_full.yml 1 job 안에 13+ collector + universe filter (5000) +
    brain layer 17 가 모두 묶여있어 GHA runner 한계 압력.
  - 5/10 13:11 KST workflow_dispatch run 에서 매크로/채권/글로벌이벤트 3종 동시 timeout
    (45/45/30s) 발생. universe 5000 stage 진입 첫 run.
  - 3종 모두 외부 API 의존이라 universe size 와 직교 — 별도 cron 으로 격리.

배치:
  - cron: */15 * * * * (15분 마다)
  - 산출: data/macro_snapshot.json + collected_at 메타
  - daily_analysis_full 은 snapshot 읽기 fast path + stale 30분+ 시 inline fetch fallback.

거짓말 트랩 정합 (feedback_data_collection_verification_mandatory):
  - try/finally + logged=True stderr 표식
  - silent skip 절대 금지 — collector fail 시 errors[] 박고 partial snapshot 유지
  - 직전 snapshot 보존 (이번 run 전체 fail 시 file 덮어쓰기 X)

메모리 정합:
  - feedback_macro_timestamp_policy: collected_at + 각 collector source/as_of 메타 의무
  - project_atr_phase0_migration 결정 21: ATR/W2/W3 와 직교 변수 (인프라 분할)
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_REPO_ROOT, "data", "macro_snapshot.json")

KST = timezone(timedelta(hours=9))


def _now_kst() -> datetime:
    return datetime.now(KST)


def _safe_call(fn: Callable[[], Any], name: str, timeout_s: int) -> tuple[Any, str | None]:
    """ThreadPoolExecutor + timeout. fail 시 (None, reason) 반환.

    silent skip 방지 — stderr 에 outcome 명시.
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(fn)
    outcome: str | None = None
    result: Any = None
    try:
        result = future.result(timeout=timeout_s)
        if result is None:
            outcome = "returned_none"
    except FutTimeout:
        outcome = f"timeout_{timeout_s}s"
    except Exception as e:
        outcome = f"exception:{type(e).__name__}:{str(e)[:120]}"
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
        ok = result is not None and outcome is None
        sys.stderr.write(
            f"[macro_collect] collector={name} ok={ok} outcome={outcome or 'success'}\n"
        )
    return (result, outcome)


def _load_existing() -> Dict[str, Any]:
    """직전 snapshot — 이번 run 전체 fail 시 이전 데이터 유지 fallback."""
    if not os.path.isfile(OUTPUT_PATH):
        return {}
    try:
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def build() -> Dict[str, Any]:
    """3 collector 호출 → snapshot dict 반환. caller 가 OUTPUT_PATH atomic write."""
    from api.collectors.macro_data import get_macro_indicators
    from api.collectors.yieldcurve import get_full_yield_curve_data
    from api.collectors.global_events import collect_global_events

    now = _now_kst()
    errors: list[str] = []
    started = time.time()

    macro, macro_err = _safe_call(get_macro_indicators, "macro", timeout_s=60)
    if macro_err:
        errors.append(f"macro: {macro_err}")

    bonds, bonds_err = _safe_call(get_full_yield_curve_data, "bonds", timeout_s=60)
    if bonds_err:
        errors.append(f"bonds: {bonds_err}")

    events, events_err = _safe_call(collect_global_events, "global_events", timeout_s=45)
    if events_err:
        errors.append(f"global_events: {events_err}")

    elapsed = round(time.time() - started, 2)

    # 직전 snapshot — 이번 run 의 partial fail 시 누락 collector 만 prev 사용
    prev = _load_existing()
    prev_macro = prev.get("macro") if isinstance(prev, dict) else None
    prev_bonds = prev.get("bonds") if isinstance(prev, dict) else None
    prev_events = prev.get("global_events") if isinstance(prev, dict) else None

    final_macro = macro if macro else prev_macro
    final_bonds = bonds if bonds else prev_bonds
    final_events = events if events else prev_events

    used_prev = []
    if not macro and prev_macro is not None:
        used_prev.append("macro")
    if not bonds and prev_bonds is not None:
        used_prev.append("bonds")
    if not events and prev_events is not None:
        used_prev.append("global_events")

    diagnostics = {
        "macro_ok": macro is not None and not macro_err,
        "bonds_ok": bonds is not None and not bonds_err,
        "events_ok": events is not None and not events_err,
        "errors": errors,
        "used_prev_snapshot": used_prev,
        "elapsed_s": elapsed,
    }

    return {
        "collected_at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "macro": final_macro or {},
        "bonds": final_bonds or {},
        "global_events": final_events or [],
        "diagnostics": diagnostics,
        "schema_version": "v0",
    }


def _atomic_write(path: str, data: Dict[str, Any]) -> None:
    """tmp file → rename. 부분 쓰기 race 방지."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def main() -> int:
    snapshot = build()
    _atomic_write(OUTPUT_PATH, snapshot)
    diag = snapshot.get("diagnostics", {})
    sys.stderr.write(
        f"[macro_collect] snapshot 적재 OK at={snapshot.get('collected_at')} "
        f"macro={diag.get('macro_ok')} bonds={diag.get('bonds_ok')} events={diag.get('events_ok')} "
        f"used_prev={diag.get('used_prev_snapshot')} elapsed={diag.get('elapsed_s')}s\n"
    )
    # 편승 — data_pipeline_health 갱신 (별도 cron 추가 X)
    try:
        from api.observability.data_pipeline_health import write_data_pipeline_health
        write_data_pipeline_health()
    except Exception as _e:
        sys.stderr.write(f"[macro_collect] data_pipeline_health 갱신 실패(무시): {_e}\n")

    # 모든 collector 가 fail 시 exit code 1 (cron 알람)
    if not (diag.get("macro_ok") or diag.get("bonds_ok") or diag.get("events_ok")):
        sys.stderr.write("[macro_collect] FATAL — 3 collector all fail\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
