#!/usr/bin/env python3
"""VAMS reset 5/17 — archive current state + fresh 1000만원 시작.

근거: project_vams_reset_2026_05_17 memory.
실행: 5/17 KST 09:00 직전. ATR Phase 0 verdict + W2/W3 wiring + funnel reform sprint 진입 timing 정합.

Default = --dry-run (실제 변경 X, 계획만 출력).
--execute 명시 시에만 실제 archive + reset.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
PORTFOLIO_PATH = REPO_ROOT / "data" / "portfolio.json"
ARCHIVE_DIR = REPO_ROOT / "data" / "vams" / "archive_pre_5_17"
KST = ZoneInfo("Asia/Seoul")

FRESH_CAPITAL = 10_000_000  # 1000만원


def fresh_vams_state(now_kst: str) -> dict:
    """5/17 시작 fresh VAMS subtree."""
    return {
        "total_asset": FRESH_CAPITAL,
        "cash": FRESH_CAPITAL,
        "holdings": [],
        "total_return_pct": 0.0,
        "total_realized_pnl": 0,
        "simulation_stats": {
            "total_trades": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate": 0.0,
            "realized_pnl": 0,
            "peak_asset": FRESH_CAPITAL,
            "max_drawdown_pct": 0.0,
            "best_trade": None,
            "worst_trade": None,
            "updated_at": now_kst,
        },
        "active_profile": "moderate",
        "adjusted_performance": {
            "adjusted_total_asset": FRESH_CAPITAL,
            "adjusted_return_pct": 0.0,
            "raw_return_pct": 0.0,
            "gap_pp": 0.0,
            "deductions": {},
            "assumptions": {},
            "computed_at": now_kst,
        },
        "validation_report": {},
        "reset_meta": {
            "reset_at": now_kst,
            "reason": "Phase 0 verdict + W2/W3 wiring + funnel reform sprint 진입",
            "previous_state_archived_to": str(ARCHIVE_DIR.relative_to(REPO_ROOT)),
            "fresh_capital_krw": FRESH_CAPITAL,
        },
    }


def summarize_current(portfolio: dict) -> dict:
    vams = portfolio.get("vams", {})
    return {
        "total_asset": vams.get("total_asset"),
        "cash": vams.get("cash"),
        "holdings_count": len(vams.get("holdings", []) or []),
        "holdings_tickers": [h.get("ticker") for h in (vams.get("holdings", []) or [])],
        "total_return_pct": vams.get("total_return_pct"),
        "total_realized_pnl": vams.get("total_realized_pnl"),
        "simulation_total_trades": vams.get("simulation_stats", {}).get("total_trades"),
        "active_profile": vams.get("active_profile"),
    }


def run(dry_run: bool) -> int:
    if not PORTFOLIO_PATH.exists():
        print(f"FATAL: {PORTFOLIO_PATH} not found", file=sys.stderr)
        return 1

    with PORTFOLIO_PATH.open("r", encoding="utf-8") as f:
        portfolio = json.load(f)

    now_kst = datetime.now(KST).isoformat()
    current = summarize_current(portfolio)

    print("=" * 60)
    print(f"VAMS RESET 5/17 — {'DRY-RUN' if dry_run else 'EXECUTE'}")
    print(f"now (KST): {now_kst}")
    print("=" * 60)
    print()
    print("[CURRENT STATE]")
    for k, v in current.items():
        print(f"  {k}: {v}")
    print()
    print("[ARCHIVE TARGET]")
    print(f"  dir: {ARCHIVE_DIR}")
    print(f"  files:")
    print(f"    - portfolio_vams_snapshot.json (vams subtree + vams_profiles)")
    print(f"    - portfolio_full_snapshot.json (full portfolio.json copy)")
    print(f"    - reset_log.json (when/why/fresh state)")
    print()
    print("[FRESH STATE AFTER RESET]")
    fresh = fresh_vams_state(now_kst)
    print(f"  total_asset: {fresh['total_asset']:,}")
    print(f"  cash: {fresh['cash']:,}")
    print(f"  holdings: []")
    print(f"  total_trades: 0")
    print(f"  active_profile: {fresh['active_profile']} (preserved)")
    print(f"  reset_meta.reset_at: {fresh['reset_meta']['reset_at']}")
    print()

    if dry_run:
        print("[DRY-RUN COMPLETE — no changes made]")
        print("To execute on 5/17: python scripts/vams_reset_5_17.py --execute")
        return 0

    # --execute path
    print("[EXECUTING ARCHIVE]")
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. vams subtree + vams_profiles
    vams_snapshot = {
        "vams": portfolio.get("vams", {}),
        "vams_profiles": portfolio.get("vams_profiles", {}),
        "snapshot_at": now_kst,
    }
    snapshot_path = ARCHIVE_DIR / "portfolio_vams_snapshot.json"
    with snapshot_path.open("w", encoding="utf-8") as f:
        json.dump(vams_snapshot, f, ensure_ascii=False, indent=2)
    print(f"  ✓ {snapshot_path.relative_to(REPO_ROOT)} ({snapshot_path.stat().st_size:,} bytes)")

    # 2. full portfolio.json backup
    full_backup = ARCHIVE_DIR / "portfolio_full_snapshot.json"
    shutil.copy2(PORTFOLIO_PATH, full_backup)
    print(f"  ✓ {full_backup.relative_to(REPO_ROOT)} ({full_backup.stat().st_size:,} bytes)")

    # 3. reset log
    reset_log = {
        "reset_at": now_kst,
        "previous_state": current,
        "fresh_capital_krw": FRESH_CAPITAL,
        "reason": "5/17 sprint 진입 (ATR Phase 0 verdict + W2/W3 wiring + funnel reform A+B+C min)",
        "archive_files": [str(snapshot_path.name), str(full_backup.name)],
    }
    log_path = ARCHIVE_DIR / "reset_log.json"
    with log_path.open("w", encoding="utf-8") as f:
        json.dump(reset_log, f, ensure_ascii=False, indent=2)
    print(f"  ✓ {log_path.relative_to(REPO_ROOT)}")

    print()
    print("[EXECUTING RESET]")
    portfolio["vams"] = fresh_vams_state(now_kst)
    # vams_profiles 은 보존 (config). 다른 키도 보존.

    with PORTFOLIO_PATH.open("w", encoding="utf-8") as f:
        json.dump(portfolio, f, ensure_ascii=False, indent=2)
    print(f"  ✓ portfolio.json vams subtree reset (cash={FRESH_CAPITAL:,})")

    print()
    print("[RESET COMPLETE]")
    print(f"  archive: {ARCHIVE_DIR.relative_to(REPO_ROOT)}")
    print(f"  next: 5/17 sprint Day 1 (Phase A — brain F+G + ATR W2/W3 + Stage 0 + Stage 1)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--execute", action="store_true",
                    help="실제 archive + reset 실행. 미지정 시 dry-run (변경 X).")
    args = ap.parse_args()
    sys.exit(run(dry_run=not args.execute))


if __name__ == "__main__":
    main()
