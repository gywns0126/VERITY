"""Optional public-only refresh child; independent of the price relay workers."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import sys

_LOGGER = logging.getLogger(__name__)
_STATUS = {"enabled": False, "worker_alive": False}
_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_STATUSES = frozenset(("success", "partial", "error", "not-due", "busy",
    "quota-blocked", "budget-exhausted", "lease-lost", "already-claimed", "degraded", "failed"))
_ERROR_CODES = frozenset(("refresh-read-timeout", "refresh-read-busy", "refresh-transport-failure",
    "refresh-transport-timeout", "refresh-http-unavailable", "refresh-http-rate-limited",
    "refresh-auth-rejected", "refresh-config-rejected", "refresh-catalog-rejected", "refresh-cache-conflict",
    "refresh-state-rejected", "refresh-response-rejected", "refresh-read-rejected", "refresh-lease-lost",
    "refresh-owner-rejected", "refresh-payload-rejected", "refresh-revision-rejected", "refresh-rpc-rejected",
    "refresh-save-conflict", "refresh-source-rejected",
    "refresh-http-failure", "refresh-unexpected-error", "refresh-unclassified",
    "dart-quota-exceeded", "transport_timeout", "transport_failure", "dart_api_failure",
    "incomplete_page", "page_limit", "record_limit", "source-error"))


def _instant(value):
    if type(value) is not str or len(value) > 40 or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:\+00:00|Z)", value):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp.isoformat(timespec="microseconds") if stamp <= datetime.now(timezone.utc) else None


def _accept_event(raw):
    """Child stdout is an untrusted boundary; health has a fixed, small vocabulary."""
    if len(raw) > 2048:
        return
    try:
        event = json.loads(raw)
    except (ValueError, UnicodeError):
        return
    if type(event) is not dict or set(event) != {
            "checked_at", "source", "attempt", "last_success_at", "status", "error_code", "backoff_seconds",
            "disabled_sources", "ai_calls", "blob_writes", "screen_delivery_verified"}:
        return
    checked = _instant(event["checked_at"])
    success = _instant(event["last_success_at"]) if event["last_success_at"] is not None else None
    if (checked is None or event["source"] != "DART" or type(event["attempt"]) is not int
            or not 0 <= event["attempt"] <= 1000000 or (event["attempt"] == 0 and event["status"] != "failed")
            or type(event["status"]) is not str
            or event["status"] not in _SOURCE_STATUSES
            or (event["last_success_at"] is not None and (success is None or success > checked))
            or (event["status"] == "success" and (success is None or event["error_code"] is not None))
            or (event["error_code"] is not None and (type(event["error_code"]) is not str
                or event["error_code"] not in _ERROR_CODES))
            or event["disabled_sources"] != ["SEC", "news"] or type(event["ai_calls"]) is not int
            or event["ai_calls"] != 0 or type(event["blob_writes"]) is not int
            or event["blob_writes"] != 0 or event["screen_delivery_verified"] is not False
            or (event["backoff_seconds"] is not None and
                (type(event["backoff_seconds"]) is not int or not 120 <= event["backoff_seconds"] <= 300))):
        return
    source_status = event["status"]
    _STATUS.update(source="DART", checked_at=checked, attempt=event["attempt"],
                   last_success_at=success or _STATUS.get("last_success_at"), source_status=source_status,
                   status="healthy" if source_status == "success" else "idle" if source_status == "not-due"
                   and success is not None else "failed" if source_status == "failed" else "degraded",
                   error_code=event["error_code"], backoff_seconds=event["backoff_seconds"])
    # Persist only the accepted projection, never arbitrary child output.
    _LOGGER.info("member map refresh %s", json.dumps({
        key: _STATUS[key] for key in ("source", "checked_at", "attempt", "last_success_at",
                                    "source_status", "error_code", "backoff_seconds")
    }, separators=(",", ":")))


async def _read_events(stream):
    try:
        while line := await stream.readline():
            _accept_event(line)
    except (ValueError, asyncio.LimitOverrunError):
        _STATUS.update(status="degraded", error_code="refresh-unclassified")


def status():
    """No credentials, cursors, source bodies or member identifiers in health."""
    snapshot = _STATUS.copy()
    if snapshot.get("worker_alive") and snapshot.get("source_status") in ("success", "not-due"):
        success = snapshot.get("last_success_at")
        if success and (datetime.now(timezone.utc) - datetime.fromisoformat(success)).total_seconds() > 300:
            snapshot.update(status="degraded", error_code="source-stale")
    if snapshot.get("worker_alive") and snapshot.get("source_status") == "starting":
        started = snapshot.get("started_at")
        if started and (datetime.now(timezone.utc) - datetime.fromisoformat(started)).total_seconds() > 300:
            snapshot.update(status="degraded", error_code="source-no-check")
    return snapshot


async def run():
    """Supervise only our child; preserve existing WS and KIS lifecycle."""
    enabled = os.environ.get("MEMBER_MAP_LIVE_REFRESH_ENABLED") == "1"
    _STATUS.clear()
    _STATUS.update(enabled=enabled, worker_alive=False)
    if not enabled:
        return
    # The data worker must not inherit broker, trading or AI credentials.
    child_env = {key: os.environ[key] for key in (
        "PATH", "LANG", "DART_API_KEY", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"
    ) if key in os.environ}
    child_env.update(PYTHONUNBUFFERED="1", PYTHONPATH=str(_ROOT))
    command = (sys.executable, str(_ROOT / "scripts/member-map/run-live-refresh.py"),
               "--backend", "supabase", "--sources", "DART", "--execute-public",
               "--duration-seconds", "86400")
    crashes = 0
    while True:
        process = None
        reader = None
        cancelled = False
        try:
            process = await asyncio.create_subprocess_exec(
                *command, cwd=str(_ROOT), env=child_env, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, limit=4096)
            _STATUS.update(worker_alive=True, status="starting", source_status="starting",
                           started_at=datetime.now(timezone.utc).isoformat())
            if getattr(process, "stdout", None) is not None:
                reader = asyncio.create_task(_read_events(process.stdout))
            code = await process.wait()
            if reader is not None:
                await reader
            _LOGGER.warning("member map refresh child stopped [exit=%s]", code)
        except asyncio.CancelledError:
            cancelled = True
            raise
        except Exception:
            _LOGGER.warning("member map refresh child unavailable [worker-unavailable]")
        finally:
            _STATUS["worker_alive"] = False
            if reader is not None and not reader.done():
                reader.cancel()
                await asyncio.gather(reader, return_exceptions=True)
            if process is not None and process.returncode is None:
                try:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=10)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                except ProcessLookupError:
                    pass
            if cancelled:
                _STATUS.clear()
                _STATUS.update(enabled=True, worker_alive=False)
        if _STATUS.get("source_status") == "failed":
            _STATUS.update(status="failed", backoff_seconds=None,
                           last_exit_at=datetime.now(timezone.utc).isoformat())
            return
        # A running process is not evidence of a successful source check.
        if _STATUS.get("source_status") == "success":
            crashes = 0
        crashes += 1
        delay = min(300, 120 * (2 ** min(crashes - 1, 2)))
        _STATUS.update(source="DART", checked_at=_STATUS.get("checked_at") or datetime.now(timezone.utc).isoformat(),
                       attempt=_STATUS.get("attempt", 0), source_status=_STATUS.get("source_status", "unavailable"),
                       status="degraded", error_code=_STATUS.get("error_code") or "worker-unavailable",
                       backoff_seconds=delay, last_exit_at=datetime.now(timezone.utc).isoformat())
        await asyncio.sleep(delay)
