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
import select
import signal
import sys
import tempfile
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict
from api.utils.macro_runtime import collection_budget

logger = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_REPO_ROOT, "data", "macro_snapshot.json")

KST = timezone(timedelta(hours=9))


def _now_kst() -> datetime:
    return datetime.now(KST)


def _safe_call(fn: Callable[[], Any], name: str, timeout_s: int) -> tuple[Any, str | None]:
    """Isolate one collector on the POSIX cron runner, including its threads.

    Executor.shutdown(wait=False) still joins live workers at interpreter exit.
    A disposable child exits directly after writing its JSON result; a timeout
    terminates its process group before we continue to the next collector.
    """
    outcome: str | None = None
    result: Any = None
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="macro-collector-") as temp:
            path = os.path.join(temp, "result.json")
            sys.stdout.flush()
            sys.stderr.flush()
            ready_read, ready_write = os.pipe()
            try:
                pid = os.fork()
            except BaseException:
                os.close(ready_read)
                os.close(ready_write)
                raise
            if pid == 0:
                try:
                    os.close(ready_read)
                    os.setsid()
                    try:
                        with collection_budget(max(0, timeout_s - 2)):
                            payload = {"result": fn(), "error": None}
                    except Exception as error:
                        payload = {"result": None, "error": f"exception:{type(error).__name__}"}
                    with open(path, "w", encoding="utf-8") as output:
                        json.dump(payload, output, ensure_ascii=False)
                    sys.stdout.flush()
                    sys.stderr.flush()
                    os.write(ready_write, b"1")
                finally:
                    # Do not wait on stalled library/executor threads at exit.
                    os._exit(0)
            os.close(ready_write)
            try:
                deadline = started + timeout_s
                readable, _, _ = select.select(
                    [ready_read], [], [], max(0, deadline - time.monotonic())
                )
                if not readable:
                    outcome = f"timeout_{timeout_s}s"
                elif os.path.isfile(path):
                    with open(path, encoding="utf-8") as output:
                        payload = json.load(output)
                    result, outcome = payload["result"], payload["error"]
                else:
                    outcome = "worker_exited_without_result"
            finally:
                # Keep the child PID reserved until group cleanup is complete;
                # reaping first could allow its numeric process-group ID reuse.
                os.close(ready_read)
                try:
                    os.killpg(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    # macOS reports EPERM for an already-exited group leader;
                    # the owned PID is still signalled and reaped below.
                    pass
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                os.waitpid(pid, 0)
        if result is None:
            outcome = outcome or "returned_none"
    except Exception as e:
        outcome = f"exception:{type(e).__name__}"
    finally:
        ok = result is not None and outcome is None
        sys.stderr.write(
            f"[macro_collect] collector={name} ok={ok} outcome={outcome or 'success'} "
            f"elapsed_ms={round((time.monotonic() - started) * 1000)} isolation=process\n"
        )
    return (result, outcome)


def _load_existing() -> Dict[str, Any]:
    """직전 snapshot — 이번 run 전체 fail 시 이전 데이터 유지 fallback."""
    if not os.path.isfile(OUTPUT_PATH):
        return {}
    try:
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
            return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _is_observation(value: Any) -> bool:
    return isinstance(value, dict) and any(
        key in value for key in ("source", "source_as_of", "as_of", "value", "pct",
                                 "index", "billions_usd", "trillions_usd", "yoy_pct")
    )


def _mark_reused(value: Any) -> Any:
    """Copy fallback data without advancing any observation/fetch/success clock."""
    if isinstance(value, list):
        return [_mark_reused(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: _mark_reused(item) for key, item in value.items()}
    if _is_observation(value):
        result.update(stale=True, reused=True)
    return result


def _preserve_partial_macro(current: dict, previous: dict, prefix: str = "") -> list[str]:
    """Restore failed/missing source rows, including native FRED/ECOS fields.

    Only these two source containers are descended into; successful empty lists
    and unrelated narrative/diagnostic structures keep their existing behavior.
    """
    reused = []
    for key in dict.fromkeys([*current, *previous]):
        path = f"{prefix}.{key}" if prefix else key
        row, old = current.get(key), previous.get(key)
        if not prefix and key in ("fred", "ecos"):
            if isinstance(old, dict):
                if not isinstance(row, dict):
                    row = current[key] = {}
                reused.extend(_preserve_partial_macro(row, old, path))
                if any(_is_observation(value) for value in row.values()):
                    row["available"] = True
            continue
        source_downgrade = (
            path == "fred.korea_gov_10y" and isinstance(old, dict) and isinstance(row, dict)
            and old.get("source") == "ecos" and row.get("source") == "fred")
        if _is_observation(old) and (source_downgrade or row is None or isinstance(row, dict) and row.get("status") == "fail"):
            if old.get("status") != "fail":
                current[key] = _mark_reused(old)
                reused.append(path)
    return sorted(reused)


def _has_stale_macro_row(macro: dict) -> bool:
    rows = list(macro.values())
    for key in ("fred", "ecos"):
        if isinstance(macro.get(key), dict):
            if macro[key].get("available") is False:
                return True
            rows.extend(macro[key].values())
    return any(_is_observation(row) and (row.get("stale") or row.get("status") == "fail")
               for row in rows)


def build() -> Dict[str, Any]:
    """3 collector 호출 → snapshot dict 반환. caller 가 OUTPUT_PATH atomic write."""
    from api.collectors.macro_data import get_macro_indicators
    from api.collectors.yieldcurve import get_full_yield_curve_data
    from api.collectors.global_events import collect_global_events

    now = _now_kst()
    prev = _load_existing()
    errors: list[str] = []
    started = time.time()

    macro, macro_err = _safe_call(get_macro_indicators, "macro", timeout_s=60)
    if macro_err:
        errors.append(f"macro: {macro_err}")

    bonds, bonds_err = _safe_call(
        lambda: get_full_yield_curve_data(prev_bonds=prev.get("bonds")), "bonds", timeout_s=60)
    if bonds_err:
        errors.append(f"bonds: {bonds_err}")

    events, events_err = _safe_call(collect_global_events, "global_events", timeout_s=45)
    if events_err:
        errors.append(f"global_events: {events_err}")

    elapsed = round(time.time() - started, 2)

    # Collection attempts are not successful refreshes. Legacy collected_at remains
    # the build clock; collector_meta and each quote carry their own provenance.
    stamp = _now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    final = {}
    collector_meta = {}
    used_prev = []
    for name, result, error in (("macro", macro, macro_err), ("bonds", bonds, bonds_err),
                                ("global_events", events, events_err)):
        # An empty event list is a valid successful collection, not a cache miss.
        ok = result is not None and not error and (bool(result) or name == "global_events")
        previous = prev.get(name)
        reused = not ok and previous is not None
        if reused:
            used_prev.append(name)
        final[name] = deepcopy(result) if ok else _mark_reused(previous)
        old_meta = (prev.get("collector_meta") or {}).get(name) or {}
        collector_meta[name] = {
            "last_attempted_at": stamp,
            "fetched_at": stamp if ok else old_meta.get("fetched_at"),
            "last_successful_at": stamp if ok else old_meta.get("last_successful_at"),
            "stale": not ok,
            "reused": reused,
        }
        if name == "bonds" and ok and isinstance(result, dict) and result.get("stale"):
            collector_meta[name]["stale"] = True
            collector_meta[name]["last_successful_at"] = old_meta.get("last_successful_at")

    # A collector can return a partial dict with failed quotes. Preserve only the
    # failed quote's previous payload; do not relabel it as newly collected.
    reused_fields = []
    if macro and not macro_err and isinstance(final["macro"], dict):
        previous_macro = prev.get("macro") or {}
        reused_fields = _preserve_partial_macro(final["macro"], previous_macro)
        collector_meta["macro"]["stale"] = bool(reused_fields) or _has_stale_macro_row(final["macro"])
        if collector_meta["macro"]["stale"]:
            old_meta = (prev.get("collector_meta") or {}).get("macro") or {}
            collector_meta["macro"]["last_successful_at"] = old_meta.get("last_successful_at")
            collector_meta["macro"]["reused"] = bool(reused_fields)

    diagnostics = {
        "macro_ok": not collector_meta["macro"]["stale"],
        "bonds_ok": bool(bonds) and not bonds_err and not collector_meta["bonds"]["stale"],
        "events_ok": events is not None and not events_err,
        "errors": errors,
        "used_prev_snapshot": used_prev,
        "reused_macro_fields": reused_fields,
        "elapsed_s": elapsed,
    }

    return {
        "collected_at": now.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "macro": final["macro"] or {},
        "bonds": final["bonds"] or {},
        "global_events": final["global_events"] or [],
        "collector_meta": collector_meta,
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
    started = time.monotonic()
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

    sys.stderr.write(f"[macro_collect] run_complete elapsed_ms={round((time.monotonic()-started)*1000)}\n")

    # 모든 collector 가 fail 시 exit code 1 (cron 알람)
    if not (diag.get("macro_ok") or diag.get("bonds_ok") or diag.get("events_ok")):
        sys.stderr.write("[macro_collect] FATAL — 3 collector all fail\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
