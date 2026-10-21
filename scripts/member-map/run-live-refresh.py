#!/usr/bin/env python3
"""Run bounded public SEC/DART/news discovery; never call AI or publish remotely."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
import json
import math
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from api.collectors.member_map_listing_delta import (
    build_issuer_map, build_kr_universe, collect_sec_delta, collect_dart_delta)
from api.collectors.member_map_live_refresh import (
    FILES, read_state, save_source, state_path, due, apply_result, news_result)
from api.observability.member_map_freshness import POLL_SECONDS, TARGET_SECONDS, instant


def cycle(path, collectors, now):
    previous = read_state(path)
    ready = {source: fn for source, fn in collectors.items() if due(source, previous.get(source, {}), now)}
    def collect(source, fn):
        prior = previous.get(source, {})
        try:
            result = fn(prior.get("feed", {"items": []}), prior.get("cursor"), now)
        except Exception:
            result = {"status": "error", "complete": False, "error": "collection-failed"}
        return source, apply_result(source, prior, result, now)
    # Each source has its own cadence and failure boundary; no AI or full-market
    # annual-document scan occupies these workers.
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(collect, source, fn) for source, fn in ready.items()]
        from concurrent.futures import as_completed
        for future in as_completed(futures):
            source, state = future.result()
            save_source(path, source, state)
    return {source: {key: value.get(key) for key in
                    ("status", "last_attempt_at", "last_success_at", "coverage", "error", "requests")}
            for source, value in read_state(path).items()}


def read_json(path, limit):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("public-input-file")
    return json.loads(path.read_text())


RUNTIME_SOURCES = ("DART",)
RUNTIME_DISABLED_SOURCES = ("SEC", "news")
RECOVERABLE_STORE_CODES = frozenset((
    "refresh-read-timeout", "refresh-read-busy", "refresh-transport-failure",
    "refresh-transport-timeout", "refresh-http-unavailable", "refresh-http-rate-limited",
    "refresh-cache-conflict", "refresh-save-conflict", "refresh-lease-lost",
))
SOURCE_ERROR_CODES = frozenset(("dart-quota-exceeded", "transport_timeout", "transport_failure",
                                "dart_api_failure", "incomplete_page", "page_limit", "record_limit"))


def runtime_event(*, checked_at, attempt, status, last_success_at=None, error_code=None, backoff_seconds=None):
    return {"checked_at": checked_at, "source": "DART", "attempt": attempt,
            "last_success_at": last_success_at, "status": status, "error_code": error_code,
            "backoff_seconds": backoff_seconds, "disabled_sources": list(RUNTIME_DISABLED_SOURCES),
            "ai_calls": 0, "blob_writes": 0, "screen_delivery_verified": False}


def not_due_result(previous, now):
    # Keep the 120-second guard; an early tick waits only the remaining time.
    remaining = POLL_SECONDS["DART"] - (instant(now) - instant(previous["last_attempt_at"])).total_seconds()
    return {"status": "not-due", "requests": 0,
            "last_success_at": previous.get("last_success_at"),
            "retry_after_seconds": max(1, math.ceil(remaining))}


def supabase_cycle(store, catalog, api_key, owner, now=None, *, transport=None):
    """DART 공개 목록만 수집한다. 원자 예약/lease/CAS 이외 원격 쓰기는 없다."""
    from api.collectors.member_map_listing_delta import DART_LIST, ListingError, bounded_transport
    from api.collectors.member_map_refresh_store import RefreshStoreError
    if type(api_key) is not str or not api_key.strip():
        raise RefreshStoreError("refresh-config-rejected")
    now = now or datetime.now(timezone.utc).isoformat()
    universe = build_kr_universe(catalog)
    if not universe:
        raise RefreshStoreError("refresh-catalog-rejected")
    previous = store.read_states().get("DART", {})
    if not due("DART", previous, now):
        return not_due_result(previous, now)
    claim = store.claim("DART", owner)
    # 불명확했던 claim 응답을 재호출해도 같은 예약으로 수집을 반복하지 않는다.
    if claim["status"] != "claimed":
        return {"status": claim["status"], "requests": 0,
                "last_success_at": previous.get("last_success_at"),
                "retry_after_seconds": claim.get("retry_after_seconds")}
    previous = claim["state"]
    if not due("DART", previous, now):
        return not_due_result(previous, now)
    generation, revision = claim["generation"], claim["revision"]
    calls, lease_failed = 0, False
    def guarded_transport(endpoint, **kwargs):
        nonlocal calls, lease_failed
        if endpoint != DART_LIST or calls >= 10:
            raise ListingError("endpoint_rejected")
        try:
            store.renew("DART", owner, generation)
        except RefreshStoreError:
            lease_failed = True
            raise ListingError("transport_failure") from None
        calls += 1
        return (transport or bounded_transport)(endpoint, **kwargs)
    result = collect_dart_delta(universe, previous.get("feed", {"items": []}), previous.get("cursor"),
        now, api_key, transport=guarded_transport, max_pages=10, max_records=1000,
        window_days=2 if previous.get("cursor") is None else 1)
    if lease_failed:
        return {"status": "lease-lost", "requests": calls}
    if result.get("error") == "dart-quota-exceeded":
        # 운영 차단 상태는 오류다. 직전 정상 피드/커서는 그대로 유지한다.
        result = {**result, "status": "error", "complete": False, "records": []}
    state = apply_result("DART", previous, result, now)
    store.renew("DART", owner, generation)
    try:
        saved = store.save("DART", owner, generation, revision, state)
    except RefreshStoreError:
        # 불명확 저장은 데이터 읽기로만 조정한다. 수집기/저장 요청을 재시도하지 않는다.
        try:
            store.read_states()
        except RefreshStoreError:
            pass
        raise
    return {"status": state["status"], "error": state["error"], "requests": calls,
            "revision": saved["revision"], "last_success_at": state.get("last_success_at")}


def run_supabase(catalog, duration_seconds):
    from api.collectors.member_map_refresh_store import RefreshStore, RefreshStoreError, read_public_catalog, safe_error_code
    # 환경값 조회는 명시 실행 이후에만 한다. 로컬 .env fallback은 사용하지 않는다.
    try:
        store = RefreshStore.from_environment(background=True)
        api_key = os.environ.get("DART_API_KEY", "")
        if not api_key.strip():
            raise RefreshStoreError("refresh-config-rejected")
    except Exception as error:
        print(json.dumps(runtime_event(checked_at=datetime.now(timezone.utc).isoformat(), attempt=0,
            status="failed", error_code=safe_error_code(error))), flush=True)
        raise RuntimeError("refresh-unclassified") from None
    owner = str(uuid4())
    deadline = time.monotonic() + duration_seconds
    attempt, failures, last_success_at = 0, 0, None
    while True:
        started = time.monotonic()
        attempt += 1
        try:
            if catalog is None:
                catalog = read_public_catalog()
                # Initial catalog loading is not part of the collection cadence.
                started = time.monotonic()
            result = supabase_cycle(store, catalog, api_key, owner)
        except Exception as error:
            checked_at = datetime.now(timezone.utc).isoformat()
            code = safe_error_code(error)
            if code not in RECOVERABLE_STORE_CODES:
                print(json.dumps(runtime_event(checked_at=checked_at, attempt=attempt,
                    status="failed", last_success_at=last_success_at, error_code=code)), flush=True)
                raise RuntimeError("refresh-unclassified") from None
            failures += 1
            interval = min(300, POLL_SECONDS["DART"] * (2 ** min(failures - 1, 2)))
            event = runtime_event(checked_at=checked_at, attempt=attempt, status="degraded",
                last_success_at=last_success_at, error_code=code, backoff_seconds=interval)
        else:
            checked_at = datetime.now(timezone.utc).isoformat()
            failures = 0
            last_success_at = result.get("last_success_at") or last_success_at
            source_status = result.get("status")
            error_code = result.get("error")
            if type(error_code) is not str or error_code not in SOURCE_ERROR_CODES:
                error_code = "source-error" if source_status in ("error", "partial", "lease-lost") else None
            if source_status not in ("success", "partial", "error", "not-due", "busy",
                    "quota-blocked", "budget-exhausted", "lease-lost", "already-claimed"):
                print(json.dumps(runtime_event(checked_at=checked_at, attempt=attempt,
                    status="failed", last_success_at=last_success_at,
                    error_code="refresh-unexpected-error")), flush=True)
                raise RuntimeError("refresh-unclassified") from None
            event = runtime_event(checked_at=checked_at, attempt=attempt, status=source_status,
                last_success_at=last_success_at, error_code=error_code)
            interval = POLL_SECONDS["DART"]
            retry_after = result.get("retry_after_seconds")
            if source_status == "not-due" and type(retry_after) is int and 0 <= retry_after <= 300:
                # RPC delay is relative to its response, not the previous tick.
                # At least one second prevents zero-delay retries at the boundary.
                interval = max(1, retry_after)
                started = time.monotonic()
        print(json.dumps(event), flush=True)
        if time.monotonic() >= deadline:
            break
        time.sleep(max(0, min(deadline - time.monotonic(), interval - (time.monotonic() - started))))
        if time.monotonic() >= deadline:
            break


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("sqlite", "supabase"), default="sqlite")
    parser.add_argument("--state-db", type=Path)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--sec-index", type=Path)
    parser.add_argument("--sources", nargs="+", choices=tuple(FILES))
    parser.add_argument("--execute-public", action="store_true")
    parser.add_argument("--duration-seconds", type=int, default=0, help="0 = one bounded pass; at most 86400")
    args = parser.parse_args()
    if not 0 <= args.duration_seconds <= 86400:
        parser.error("duration outside bounded range")
    args.sources = args.sources or (["DART"] if args.backend == "supabase" else ["SEC", "DART", "news"])
    if args.backend == "supabase":
        if args.sources != ["DART"] or args.state_db is not None or args.sec_index is not None:
            parser.error("supabase runtime permits DART only; SQLite/SEC options are disabled")
        if not args.execute_public:
            print(json.dumps({"status": "dry-run", "backend": "supabase", "poll_seconds": {"DART": 120},
                "disabled_sources": list(RUNTIME_DISABLED_SOURCES), "dedicated_daily_cap": 8000,
                "shared_remaining": None, "network_requests": 0, "ai_calls": 0, "remote_writes": 0}))
            return
        catalog = read_json(args.catalog, 16 * 1024 * 1024) if args.catalog else None
        run_supabase(catalog, args.duration_seconds)
        return
    if args.state_db is None or args.catalog is None:
        parser.error("sqlite requires --state-db and --catalog")
    catalog = read_json(args.catalog, 16 * 1024 * 1024)
    collectors = {}
    if "SEC" in args.sources:
        if args.sec_index is None:
            parser.error("SEC requires saved official --sec-index")
        issuers = build_issuer_map(catalog, read_json(args.sec_index, 4 * 1024 * 1024))
        collectors["SEC"] = lambda feed, cursor, now: collect_sec_delta(issuers, feed, cursor, now)
    if "DART" in args.sources:
        universe = build_kr_universe(catalog)
        key = os.environ.get("DART_API_KEY", "")
        if args.execute_public and not key:
            # Existing approved key only; do not load/export unrelated secrets.
            from dotenv import dotenv_values
            key = dotenv_values(ROOT / ".env").get("DART_API_KEY") or ""
        collectors["DART"] = lambda feed, cursor, now: collect_dart_delta(
            universe, feed, cursor, now, key, max_pages=10, max_records=1000, window_days=1)
    if "news" in args.sources:
        collectors["news"] = lambda *_: news_result()
    if not args.execute_public:
        print(json.dumps({"status": "dry-run", "poll_seconds": POLL_SECONDS,
                          "delivery_targets_seconds": TARGET_SECONDS, "achieved_sla": False,
                          "network_requests": 0, "ai_calls": 0, "remote_writes": 0}))
        return
    path = state_path(args.state_db)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = state_path(path.with_suffix(".lock"))
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        deadline = time.monotonic() + args.duration_seconds
        previous_summary = None
        while True:
            now = datetime.now(timezone.utc).isoformat()
            result = cycle(path, collectors, now)
            if result != previous_summary:
                print(json.dumps({"checked_at": now, "sources": result, "ai_calls": 0,
                                  "remote_writes": 0, "screen_delivery_verified": False}), flush=True)
                previous_summary = result
            if time.monotonic() >= deadline:
                break
            time.sleep(min(5, max(0, deadline - time.monotonic())))
    finally:
        os.close(fd)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"status": "failed", "error_code": "refresh-unclassified"}), file=sys.stderr)
        raise SystemExit(1)
