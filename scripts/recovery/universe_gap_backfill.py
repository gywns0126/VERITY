#!/usr/bin/env python3
"""Recover the Sep 8-11 persistence gap without inventing historical observations.

Read: immutable pre/post incident stock_history snapshots + eight Actions logs.
Write: isolated data/research sidecar, NEVER stock_history or live candidates.
Prices are provider history retrieved now, not the lost intraday snapshots.
No KIS, scoring, orders, current fundamentals, or production workflow dispatch.
"""
from __future__ import annotations

import argparse
import ast
import concurrent.futures
import fcntl
import hashlib
import json
import math
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = "gywns0126/VERITY"
ROOT = Path(__file__).resolve().parents[2]
START, END = "2026-09-08", "2026-09-12"  # end exclusive
DAYS = [f"2026-09-{day:02}" for day in range(8, 12)]
ANCHOR = "9129a576367d81db4cf14c30be8701b62c00d787"
SOURCES = ["data/stock_history/2026-Q3.part-01.jsonl", "data/stock_history/2026-Q3.jsonl"]
RUN_IDS = [34194925279, 34221733442, 34319337010, 34347125538,
           34445467380, 34472694702, 34570183855, 34595320574]
DEFAULT_OUTPUT = ROOT / "data/research/universe_gap_20260908_20260911"
PRICE_FIELDS = set("record_kind is_backfilled eligible_for_observation_trail key ticker market currency date open high low close volume adj_close provider_bar_timestamp exchange_timezone retrieved_at source source_url price_basis".split())
_LOG_LINE = re.compile(r"\t(\d{4}-\d\d-\d\dT[\d:.]+Z) (.*)$")
_PATTERNS = {
    "snapshot_append": re.compile(r"\[quarterly_history\] appended n=(\d+) skipped=(\d+) → 2026-Q3\.jsonl$"),
    "coarse_filter": re.compile(r"\[Phase 2-B wide_scan (SHADOW|PRODUCTION)\] input=(\d+) target=(\d+) passed=(\d+) logged=(True|False)$"),
    "candidate_diff": re.compile(r"\[cand_diff\] ok · 편입 (\d+) · 이탈 (\d+) · 유지 (\d+) / (\d+)$"),
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def gh(*args: str) -> str:
    return subprocess.check_output(["gh", *args], cwd=ROOT, text=True, timeout=120)


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parse_log(text: str) -> dict:
    """Persist ONLY whitelisted observations; logs may contain unrelated secrets."""
    events = {kind: [] for kind in _PATTERNS}
    rejected_pushes = 0
    for line in text.splitlines():
        match = _LOG_LINE.search(line)
        if not match:
            continue
        timestamp, message = match.groups()
        for kind, pattern in _PATTERNS.items():
            event = pattern.fullmatch(message)
            if event:
                events[kind].append({"logged_at": timestamp, "message": message,
                                     "values": list(event.groups())})
        if "remote: error: File data/stock_history/2026-Q3.jsonl" in message:
            rejected_pushes += 1
    if any(len(values) != 1 for values in events.values()) or rejected_pushes == 0:
        raise ValueError("Missing/ambiguous observed events or persistence failure")
    appended, skipped = map(int, events["snapshot_append"][0]["values"])
    mode, count, target, passed, logged = events["coarse_filter"][0]["values"]
    added, removed, kept, total = map(int, events["candidate_diff"][0]["values"])
    if appended != int(count) or added + kept != total or logged != "True":
        raise ValueError("Inconsistent recorded counts")
    return {"record_kind": "log_recovered_observation", "not_full_snapshot": True,
            "reported_unsaved_rows": appended, "skipped_rows": skipped,
            "coarse": {"mode": mode, "input": int(count), "target": int(target), "passed": int(passed)},
            "candidate_diff": {"added": added, "removed": removed, "kept": kept, "total": total,
                               "baseline": "last_persisted_previous_snapshot_not_previous_failed_run"},
            "rejected_pushes": rejected_pushes,
            "evidence": [event for values in events.values() for event in values]}


def recover_run(run_id: int) -> dict:
    meta = json.loads(gh("api", f"repos/{REPO}/actions/runs/{run_id}"))
    if meta["path"] != ".github/workflows/universe_scan.yml" or not START <= meta["created_at"][:10] < END:
        raise ValueError(f"Unexpected run {run_id}")
    result = parse_log(gh("run", "view", str(run_id), "--repo", REPO, "--log"))
    artifacts = json.loads(gh("api", f"repos/{REPO}/actions/runs/{run_id}/artifacts"))
    result.update({"run_id": run_id, "source_url": meta["html_url"],
                   "head_sha": meta["head_sha"], "created_at": meta["created_at"],
                   "workflow_conclusion": meta["conclusion"], "retrieved_at": now(),
                   "artifact_count": artifacts["total_count"]})
    return result


def build_targets(history_root: Path) -> tuple[list, list]:
    """Boundary union is an explicit proxy, NOT the unknown failed-run membership."""
    roster: dict[str, dict] = {}
    sources = []
    for rel in SOURCES:
        path = history_root / rel
        before = sha256(path)
        rows, used = 0, 0
        with path.open(encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                rows += 1
                day = str(row.get("ts", ""))[:10]
                if day not in {"2026-09-07", "2026-09-12"}:
                    continue
                used += 1
                ticker, market = str(row["ticker"]), str(row["market"])
                currency = str(row.get("currency", ""))
                is_kr = market in {"KOSPI", "KOSDAQ"}
                symbol = ticker + (".KS" if market == "KOSPI" else ".KQ") if is_kr else ticker.replace(".", "-")
                key = ("KR:" if is_kr else "US:") + ticker
                if key not in roster:
                    roster[key] = {"key": key, "ticker": ticker, "market": market,
                                   "currency": currency, "provider_symbol": symbol,
                                   "anchor_observed_days": [], "anchor_last_observed_at": row["ts"]}
                entry = roster[key]
                if entry["provider_symbol"] != symbol or entry["currency"] != currency:
                    raise ValueError(f"Ambiguous boundary symbol/currency {key}")
                if day not in entry["anchor_observed_days"]:
                    entry["anchor_observed_days"].append(day)
                entry["anchor_last_observed_at"] = max(entry["anchor_last_observed_at"], row["ts"])
        if sha256(path) != before:
            raise ValueError(f"Concurrent source modification: {rel}")
        sources.append({"path": rel, "sha256": before, "rows": rows, "selected_rows": used})
    return sorted(roster.values(), key=lambda r: r["key"]), sources


def chart_url(symbol: str) -> str:
    period = [int(datetime.fromisoformat(day).replace(tzinfo=timezone.utc).timestamp()) for day in (START, END)]
    params = urllib.parse.urlencode({"period1": period[0], "period2": period[1], "interval": "1d", "events": "div,splits"})
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol, safe='')}?{params}"


def finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def naver_url(ticker: str) -> str:
    if not re.fullmatch(r"\d{6}", ticker):
        raise ValueError("Naver fallback requires a KR instrument code")
    return f"https://api.finance.naver.com/siseJson.naver?symbol={ticker}&requestType=1&startTime=20260908&endTime=20260911&timeframe=day"


def parse_naver(data: list, target: dict, retrieved_at: str) -> list:
    if not target["key"].startswith("KR:") or target["currency"] != "KRW":
        raise ValueError("Naver fallback only covers KR shares")
    if not data or data[0][:6] != ["날짜", "시가", "고가", "저가", "종가", "거래량"]:
        raise ValueError("Unexpected Naver daily columns")
    out, seen = [], set()
    for record in data[1:]:
        if len(record) < 6 or not re.fullmatch(r"\d{8}", str(record[0])):
            raise ValueError("Invalid Naver record")
        raw_day = str(record[0])
        day = f"{raw_day[:4]}-{raw_day[4:6]}-{raw_day[6:]}"
        if day not in DAYS:
            continue
        if day in seen:
            raise ValueError("Duplicate Naver date")
        seen.add(day)
        values = dict(zip(("open", "high", "low", "close", "volume"), record[1:6]))
        if not all(finite(v) for v in values.values()):
            continue
        o, h, low, c, v = values.values()
        if min(o, h, low, c) <= 0 or v < 0 or int(v) != v or not low <= min(o, c) <= max(o, c) <= h:
            continue
        out.append({"record_kind": "historical_price_backfill", "is_backfilled": True,
                    "eligible_for_observation_trail": False, "key": target["key"],
                    "ticker": target["ticker"], "market": target["market"], "currency": "KRW",
                    "date": day, **values, "adj_close": None,
                    "provider_bar_timestamp": None, "exchange_timezone": "Asia/Seoul",
                    "retrieved_at": retrieved_at, "source": "Naver Finance daily",
                    "source_url": naver_url(target["ticker"]),
                    "price_basis": "provider_quote_as_returned_not_original_scan_price"})
    return out


def parse_chart(payload: dict, target: dict, retrieved_at: str) -> tuple[list, list]:
    chart = payload.get("chart") or {}
    result = chart.get("result") or []
    if chart.get("error") or len(result) != 1:
        raise ValueError("provider_error_or_empty_result")
    data = result[0]
    meta = data.get("meta") or {}
    if meta.get("symbol", "").upper() != target["provider_symbol"].upper():
        raise ValueError("provider_symbol_mismatch")
    if meta.get("currency") != target["currency"]:
        raise ValueError("provider_currency_mismatch")
    tz = ZoneInfo(meta["exchangeTimezoneName"])
    indicators = data.get("indicators") or {}
    quotes = indicators.get("quote") or []
    if len(quotes) != 1:
        raise ValueError("missing_quote")
    times = data.get("timestamp") or []
    quote = quotes[0]
    if any(len(quote.get(k) or []) != len(times) for k in ("open", "high", "low", "close", "volume")):
        raise ValueError("quote_length_mismatch")
    adj = (indicators.get("adjclose") or [{}])[0].get("adjclose") or []
    out, issues, seen = [], [], set()
    for i, stamp in enumerate(times):
        date = datetime.fromtimestamp(stamp, tz).date().isoformat()
        if date not in DAYS:
            continue
        if date in seen:
            raise ValueError("duplicate_trading_date")
        seen.add(date)
        values = {k: quote[k][i] for k in ("open", "high", "low", "close", "volume")}
        if not all(finite(v) for v in values.values()):
            issues.append({"date": date, "reason": "missing_or_nonfinite_ohlcv"})
            continue
        o, h, low, c, v = (values[k] for k in ("open", "high", "low", "close", "volume"))
        if min(o, h, low, c) <= 0 or v < 0 or int(v) != v or not low <= min(o, c) <= max(o, c) <= h:
            issues.append({"date": date, "reason": "invalid_ohlcv"})
            continue
        adjusted = adj[i] if i < len(adj) and finite(adj[i]) and adj[i] > 0 else None
        out.append({"record_kind": "historical_price_backfill", "is_backfilled": True,
                    "eligible_for_observation_trail": False, "key": target["key"],
                    "ticker": target["ticker"], "market": target["market"], "currency": meta["currency"],
                    "date": date, **values, "adj_close": adjusted,
                    "provider_bar_timestamp": stamp, "exchange_timezone": meta["exchangeTimezoneName"],
                    "retrieved_at": retrieved_at, "source": "Yahoo Finance chart",
                    "source_url": chart_url(target["provider_symbol"]),
                    "price_basis": "provider_quote_as_returned_not_original_scan_price"})
    return out, issues


class RateLimiter:
    def __init__(self, interval: float = 0.3):
        self.interval, self.next = interval, 0.0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            delay = max(0.0, self.next - time.monotonic())
            self.next = max(self.next, time.monotonic()) + self.interval
        if delay:
            time.sleep(delay)


def naver_fallback(target: dict, limiter: RateLimiter, existing: list) -> tuple[list, str | None]:
    if not target["key"].startswith("KR:"):
        return existing, None
    try:
        limiter.wait()
        req = urllib.request.Request(naver_url(target["ticker"]), headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.naver.com/"})
        with urllib.request.urlopen(req, timeout=25) as response:
            data = ast.literal_eval(response.read().decode("utf-8-sig").strip())
        known = {r["date"] for r in existing}
        extra = [r for r in parse_naver(data, target, now()) if r["date"] not in known]
        return existing + extra, None
    except (OSError, ValueError, SyntaxError, IndexError, TypeError) as exc:
        return existing, "naver_" + type(exc).__name__


def fetch_target(target: dict, limiter: RateLimiter) -> tuple[list, dict]:
    error = "not_attempted"
    for attempt in range(3):
        limiter.wait()
        try:
            req = urllib.request.Request(chart_url(target["provider_symbol"]), headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as response:
                payload = json.load(response)
            rows, issues = parse_chart(payload, target, now())
            missing = sorted(set(DAYS) - {r["date"] for r in rows})
            fallback_error = None
            if missing:
                rows, fallback_error = naver_fallback(target, limiter, rows)
                missing = sorted(set(DAYS) - {r["date"] for r in rows})
            return rows, {"key": target["key"], "attempted": True, "rows": len(rows),
                          "missing_dates": missing, "issues": issues,
                          "fallback_error": fallback_error,
                          "error": "provider_missing_dates" if missing else None}
        except urllib.error.HTTPError as exc:
            error = f"HTTP_{exc.code}"
            if exc.code not in {429, 500, 502, 503, 504}:
                break
        except (OSError, ValueError, KeyError, TypeError) as exc:
            error = type(exc).__name__ + ":" + str(exc)[:120]
        if attempt < 2:
            time.sleep(2 ** (attempt + 1))
    rows, fallback_error = naver_fallback(target, limiter, [])
    missing = sorted(set(DAYS) - {r["date"] for r in rows})
    return rows, {"key": target["key"], "attempted": True, "rows": len(rows),
                  "missing_dates": missing, "issues": [], "fallback_error": fallback_error,
                  "primary_error": error, "error": error if missing else None}


def read_prices(path: Path) -> list:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    keys = [(r["key"], r["date"]) for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate saved price keys")
    if any(r.get("record_kind") != "historical_price_backfill" or r.get("eligible_for_observation_trail") is not False for r in rows):
        raise ValueError("Wrong sidecar record type")
    return rows


def write_prices(path: Path, rows: list) -> None:
    temp = path.with_suffix(".jsonl.tmp")
    with temp.open("w", encoding="utf-8") as f:
        for row in sorted(rows, key=lambda r: (r["key"], r["date"])):
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


def price_coverage(targets: list, rows: list, attempts: dict) -> dict:
    dates: dict[str, set] = {}
    for row in rows:
        dates.setdefault(row["key"], set()).add(row["date"])
    unresolved = []
    for target in targets:
        key = target["key"]
        missing = sorted(set(DAYS) - dates.get(key, set()))
        if missing:
            unresolved.append({"key": key, "missing_dates": missing,
                               **{k: v for k, v in attempts.get(key, {}).items() if k in {"error", "issues"}}})
    return {"target_tickers": len(targets), "attempted_tickers": len(attempts),
            "complete_tickers": len(targets) - len(unresolved), "tickers_with_prices": len(dates),
            "expected_ticker_days": len(targets) * len(DAYS), "recovered_ticker_days": len(rows),
            "missing_ticker_days": sum(len(x["missing_dates"]) for x in unresolved),
            "by_date": dict(sorted(Counter(r["date"] for r in rows).items())),
            "by_source": dict(sorted(Counter(r["source"] for r in rows).items())),
            "unresolved": unresolved, "retrieved_at": now()}


def validate_saved_prices(rows: list, targets: list) -> None:
    """A damaged resume file must not inflate coverage or become a fake snapshot."""
    by_key = {r["key"]: r for r in targets}
    for row in rows:
        if set(row) != PRICE_FIELDS:
            raise ValueError("Saved price has unexpected/missing fields")
        target = by_key.get(row.get("key"))
        if target is None or row.get("date") not in DAYS:
            raise ValueError("Saved price outside roster/date scope")
        if any(row.get(k) != target[k] for k in ("ticker", "currency", "market")):
            raise ValueError("Saved price identity mismatch")
        if row.get("is_backfilled") is not True or any(k in row for k in ("ts", "price", "per", "roe")):
            raise ValueError("Saved price masquerades as an observed snapshot")
        is_naver = row["source"] == "Naver Finance daily"
        expected_url = naver_url(target["ticker"]) if is_naver else chart_url(target["provider_symbol"])
        if row["source"] not in {"Naver Finance daily", "Yahoo Finance chart"} or row["source_url"] != expected_url:
            raise ValueError("Saved price provenance mismatch")
        retrieved = datetime.fromisoformat(row["retrieved_at"].replace("Z", "+00:00"))
        if retrieved.tzinfo is None or retrieved.date().isoformat() < END:
            raise ValueError("Invalid recovery retrieval timestamp")
        if is_naver:
            if not target["key"].startswith("KR:") or row["provider_bar_timestamp"] is not None or row["exchange_timezone"] != "Asia/Seoul":
                raise ValueError("Invalid Naver provenance")
        else:
            day = datetime.fromtimestamp(row["provider_bar_timestamp"], ZoneInfo(row["exchange_timezone"])).date().isoformat()
            if day != row["date"]:
                raise ValueError("Provider timestamp/date mismatch")
        if row["adj_close"] is not None and (not finite(row["adj_close"]) or row["adj_close"] <= 0):
            raise ValueError("Invalid saved adjusted close")
        values = [row.get(k) for k in ("open", "high", "low", "close", "volume")]
        if not all(finite(v) for v in values):
            raise ValueError("Saved price contains missing/nonfinite values")
        o, h, low, close, volume = values
        if min(o, h, low, close) <= 0 or volume < 0 or int(volume) != volume or not low <= min(o, close) <= max(o, close) <= h:
            raise ValueError("Saved price has invalid OHLCV")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--history-root", type=Path, default=ROOT)
    parser.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    parser.add_argument("--limit", type=int, help="Smoke test only; denominator remains full roster")
    parser.add_argument("--retry-missing", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    # Avoid accidental ingestion by the actual-snapshot consumer's *.jsonl glob.
    if "research" not in output.parts or output.name != DEFAULT_OUTPUT.name:
        parser.error("Output must be a data/research/universe_gap_20260908_20260911 sidecar")
    args.history_root = args.history_root.resolve()
    for rel in SOURCES:
        # Do not derive the roster from moving HEAD or a shared dirty file.
        blob = subprocess.check_output(["git", "show", f"{ANCHOR}:{rel}"], cwd=ROOT)
        if hashlib.sha256(blob).hexdigest() != sha256(args.history_root / rel):
            raise ValueError(f"Source differs from immutable incident anchor: {rel}")
    targets, sources = build_targets(args.history_root)
    output.mkdir(parents=True, exist_ok=True)
    # Keep the descriptor alive until the entire command exits. A second runner
    # must not overwrite the first runner's atomic checkpoints.
    output_lock = (output / ".recovery.lock").open("a")
    try:
        fcntl.flock(output_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise ValueError("Another recovery writer already holds this output")
    atomic_json(output / "targets.json", {"basis": "union_of_observed_boundary_rosters_NOT_failed_run_roster",
                                         "anchor_commit": ANCHOR, "count": len(targets), "targets": targets})
    evidence_path = output / "run_evidence.json"
    if evidence_path.exists():
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if sorted(x["run_id"] for x in evidence) != sorted(RUN_IDS):
            raise ValueError("Wrong saved run evidence")
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            evidence = list(executor.map(recover_run, RUN_IDS))
        atomic_json(evidence_path, evidence)
    prices_path = output / "prices_daily.jsonl"
    rows = read_prices(prices_path)
    validate_saved_prices(rows, targets)
    existing = {(r["key"], r["date"]): r for r in rows}
    attempts_path = output / "attempts.json"
    attempts = json.loads(attempts_path.read_text()) if attempts_path.exists() else {}
    pending = [t for t in targets if any((t["key"], d) not in existing for d in DAYS)
               and (args.retry_missing or t["key"] not in attempts)]
    if args.limit is not None:
        pending = pending[:max(0, args.limit)]
    manifest = {"schema": "universe-gap-recovery-v1", "status": "running", "gap_start": START,
                "recovery_tool_sha256": sha256(Path(__file__)),
                "gap_end_exclusive": END, "generated_at": now(), "anchor_commit": ANCHOR,
                "source_files": sources, "runs_recovered": len(evidence), "runs_expected": len(RUN_IDS),
                "reported_unsaved_snapshot_rows": sum(r["reported_unsaved_rows"] for r in evidence),
                "original_missing_snapshot_rows_restored": 0,
                "original_snapshot_status": "unrecoverable_from_checked_logs_and_artifacts",
                "price_roster_basis": "boundary_union_proxy_not_exact_failed_run_membership",
                "not_restored": ["full_failed_run_fundamentals", "ownership_snapshots", "full_candidate_lists", "intraday_scan_prices"],
                "production_consumers_changed": False, "observation_trail_eligible": False,
                "price_sources": ["Yahoo Finance chart", "Naver Finance daily (KR missing bars only)"],
                "price_basis": "provider_OHLCV_as_returned_adjustments_may_be_revised_after_event",
                "usage": "historical research only; never count as originally observed samples"}
    atomic_json(output / "manifest.json", manifest)

    def checkpoint():
        write_prices(prices_path, list(existing.values()))
        atomic_json(attempts_path, attempts)
        coverage = price_coverage(targets, list(existing.values()), attempts)
        atomic_json(output / "coverage.json", coverage)
        return coverage

    limiter = RateLimiter()
    print(f"run evidence {len(evidence)}/{len(RUN_IDS)}, targets {len(targets)}, queued {len(pending)}", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(fetch_target, t, limiter): t for t in pending}
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            new_rows, report = future.result()
            for row in new_rows:
                existing.setdefault((row["key"], row["date"]), row)
            attempts[report["key"]] = report
            if i % 50 == 0 or i == len(pending):
                coverage = checkpoint()
                print(f"attempted {coverage['attempted_tickers']}/{len(targets)}; complete {coverage['complete_tickers']}; bars {len(existing)}", flush=True)
    coverage = checkpoint()
    if any(sha256(args.history_root / s["path"]) != s["sha256"] for s in sources):
        raise ValueError("Source changed during recovery")
    manifest.update({"status": "partial_original_recovery",
                     "price_backfill_status": "complete" if coverage["missing_ticker_days"] == 0 else "partial",
                     "finished_at": now(), "coverage": {k: v for k, v in coverage.items() if k != "unresolved"},
                     "files_sha256": {name: sha256(output / name) for name in
                                      ("targets.json", "run_evidence.json", "prices_daily.jsonl", "attempts.json", "coverage.json")}})
    atomic_json(output / "manifest.json", manifest)
    print(json.dumps({"status": manifest["status"], **manifest["coverage"]}, ensure_ascii=False), flush=True)
    return 0 if coverage["missing_ticker_days"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
