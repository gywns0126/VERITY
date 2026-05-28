#!/usr/bin/env python3
"""
self_assets_weekly.py — VERITY 자기 자산 5종 강화 weekly trail

WHY: 조건 5-b 보강. 메모 RULE 6 BigBrother 대응 — LLM 못 가지는 자기 자산
누적이 핵심 해자. 매주 자산 항목 ↑/↓/= 박아 정체 detect.

5 항목 (현 wire 박힌 3 + 큐잉 2):
  1. Brain learning N+    — data/metadata/brain_learning.jsonl 신 entry 누적
  2. funnel SHADOW data   — data/wide_scan_log.jsonl 신 entry 누적
  3. cron 자동화 health   — data/metadata/cron_health.jsonl 최근 7일 fail/total
  4. VAMS hit N+          — data/vams/*.json (5/17 reset 후 path 미확정, 큐잉)
  5. Lynch trigger N+     — Lynch classifier output (path 미확정, 큐잉)

산출: data/self_assets_weekly.jsonl 매주 entry append.
ALERT 조건: 항목 N+ 0 (7일간 신 entry 0) — 자산 정체 detect → stderr WARN.

운영: .github/workflows/self_assets_weekly.yml 매주 월 KST 09:00
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = _ROOT / "data" / "self_assets_weekly.jsonl"

KST = timezone(timedelta(hours=9))


def _now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def _count_jsonl_entries_last_n_days(path: Path, days: int = 7) -> Dict[str, Any]:
    """jsonl 파일의 최근 N일 신 entry 수 박음."""
    if not path.exists():
        return {"path": str(path.relative_to(_ROOT)), "n_new": -1,
                "total": 0, "detail": "file missing"}
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    n_new = 0
    total = 0
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                total += 1
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # timestamp 박힌 key 후보 (jsonl 파일별 schema 다름)
                ts = (entry.get("ts_utc") or entry.get("ts_kst") or entry.get("as_of")
                      or entry.get("timestamp") or entry.get("created_at") or entry.get("ts"))
                if not ts:
                    continue
                try:
                    # ISO 8601 parse — Z suffix 또는 +HH:MM offset 양쪽 지원
                    if isinstance(ts, str) and ts.endswith("Z"):
                        ts = ts[:-1] + "+00:00"
                    dt = datetime.fromisoformat(ts)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt >= cutoff:
                        n_new += 1
                except (ValueError, TypeError):
                    continue
    except OSError as e:
        return {"path": str(path.relative_to(_ROOT)), "n_new": -1,
                "total": 0, "detail": f"read fail: {e}"}
    return {"path": str(path.relative_to(_ROOT)), "n_new": n_new, "total": total}


def check_brain_learning() -> Dict[str, Any]:
    r = _count_jsonl_entries_last_n_days(_ROOT / "data" / "metadata" / "brain_learning.jsonl", days=7)
    r["asset"] = "brain_learning"
    r["status"] = "STALE" if r["n_new"] == 0 else ("OK" if r["n_new"] > 0 else "WARN")
    return r


def check_funnel_shadow() -> Dict[str, Any]:
    r = _count_jsonl_entries_last_n_days(_ROOT / "data" / "wide_scan_log.jsonl", days=7)
    r["asset"] = "funnel_shadow"
    r["status"] = "STALE" if r["n_new"] == 0 else ("OK" if r["n_new"] > 0 else "WARN")
    return r


def check_cron_health() -> Dict[str, Any]:
    """cron_health.jsonl 최근 7일 fail/total 비율 박음."""
    path = _ROOT / "data" / "metadata" / "cron_health.jsonl"
    if not path.exists():
        return {"asset": "cron_health", "path": str(path.relative_to(_ROOT)),
                "status": "WARN", "detail": "file missing"}
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    total = 0
    fail = 0
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = (entry.get("ts_utc") or entry.get("ts_kst") or entry.get("as_of")
                      or entry.get("timestamp"))
                if not ts:
                    continue
                try:
                    if isinstance(ts, str) and ts.endswith("Z"):
                        ts = ts[:-1] + "+00:00"
                    dt = datetime.fromisoformat(ts)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt < cutoff:
                        continue
                except (ValueError, TypeError):
                    continue
                total += 1
                # severity / status 박힌 부분 FAIL/WARNING 감지
                sev = (entry.get("severity") or entry.get("status") or "").upper()
                if sev in ("FAIL", "WARNING", "ERROR"):
                    fail += 1
    except OSError as e:
        return {"asset": "cron_health", "status": "WARN", "detail": f"read fail: {e}"}
    fail_rate = round(fail / total * 100, 1) if total > 0 else 0.0
    status = "OK" if fail_rate < 10.0 else ("WARN" if fail_rate < 30.0 else "ALERT")
    return {"asset": "cron_health", "path": str(path.relative_to(_ROOT)),
            "total_7d": total, "fail_7d": fail, "fail_rate_pct": fail_rate, "status": status}


def _previous_snapshot() -> Dict[str, Any]:
    """직전 weekly entry 반환. 첫 실행 시 빈 dict."""
    if not OUTPUT_PATH.exists():
        return {}
    try:
        last_line = ""
        with OUTPUT_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    last_line = line
        return json.loads(last_line) if last_line else {}
    except (json.JSONDecodeError, OSError):
        return {}


def check_vams_hit() -> Dict[str, Any]:
    """VAMS hit trail — portfolio.json 의 vams.simulation_stats.total_trades 누적 + win_rate."""
    portfolio_path = _ROOT / "data" / "portfolio.json"
    if not portfolio_path.exists():
        return {"asset": "vams_hit", "status": "WARN", "detail": "portfolio.json 부재"}
    try:
        with portfolio_path.open("r", encoding="utf-8") as f:
            portfolio = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return {"asset": "vams_hit", "status": "WARN", "detail": f"read fail: {str(e)[:60]}"}

    stats = (portfolio.get("vams") or {}).get("simulation_stats") or {}
    total_trades = stats.get("total_trades", 0)
    win_count = stats.get("win_count", 0)
    win_rate = stats.get("win_rate", 0.0)

    # 직전 weekly entry 의 vams_hit.total_trades 와 비교 = delta
    prev = _previous_snapshot()
    prev_total = 0
    for a in prev.get("assets", []):
        if a.get("asset") == "vams_hit":
            prev_total = a.get("total_trades", 0)
            break

    delta = total_trades - prev_total
    status = "STALE" if delta == 0 else ("OK" if delta > 0 else "WARN")

    return {
        "asset": "vams_hit",
        "path": "data/portfolio.json#vams.simulation_stats",
        "total_trades": total_trades,
        "win_count": win_count,
        "win_rate_pct": win_rate,
        "delta_7d": delta,
        "status": status,
    }


def check_lynch_trigger() -> Dict[str, Any]:
    """Lynch classifier trail — portfolio.json 의 lynch_kr_distribution.total + counts."""
    portfolio_path = _ROOT / "data" / "portfolio.json"
    if not portfolio_path.exists():
        return {"asset": "lynch_trigger", "status": "WARN", "detail": "portfolio.json 부재"}
    try:
        with portfolio_path.open("r", encoding="utf-8") as f:
            portfolio = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return {"asset": "lynch_trigger", "status": "WARN", "detail": f"read fail: {str(e)[:60]}"}

    dist = portfolio.get("lynch_kr_distribution") or {}
    total = dist.get("total", 0)
    counts = dist.get("counts", {})

    # 직전 weekly entry counts 와 비교 = 분류 변화 감지
    prev = _previous_snapshot()
    prev_counts = {}
    for a in prev.get("assets", []):
        if a.get("asset") == "lynch_trigger":
            prev_counts = a.get("counts", {})
            break

    changed = sum(1 for k in counts if counts.get(k) != prev_counts.get(k))
    status = "STALE" if changed == 0 and prev_counts else "OK"
    if total == 0:
        status = "WARN"

    return {
        "asset": "lynch_trigger",
        "path": "data/portfolio.json#lynch_kr_distribution",
        "total": total,
        "counts": counts,
        "categories_changed_7d": changed,
        "status": status,
    }


def main() -> int:
    assets = [
        check_brain_learning(),
        check_funnel_shadow(),
        check_cron_health(),
        check_vams_hit(),
        check_lynch_trigger(),
    ]

    entry = {
        "as_of": _now_kst(),
        "assets": assets,
        "summary": {
            "ok": sum(1 for a in assets if a.get("status") == "OK"),
            "stale": sum(1 for a in assets if a.get("status") == "STALE"),
            "warn": sum(1 for a in assets if a.get("status") == "WARN"),
            "alert": sum(1 for a in assets if a.get("status") == "ALERT"),
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"self_assets_weekly: {entry['summary']}")
    for a in assets:
        # 항목별 metric 표시 (n_new / fail_rate / delta_7d / categories_changed_7d 등)
        metric = (a.get("n_new")
                  or a.get("fail_rate_pct")
                  or a.get("delta_7d")
                  or a.get("categories_changed_7d")
                  or 0)
        print(f"  [{a['status']:5s}] {a['asset']:18s} — metric: {metric} {a.get('detail','')[:60]}")

    stale_count = entry["summary"]["stale"]
    if stale_count > 0:
        print(f"::warning::{stale_count} 자산 STALE — 7일간 신 entry 0", file=sys.stderr)
    return 0 if entry["summary"]["alert"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
