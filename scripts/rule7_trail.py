#!/usr/bin/env python3
"""
rule7_trail.py — RULE 7 retroactive trail CLI

data/metadata/rule7_retroactive_trail.jsonl 편집 헬퍼. jsonl vim 직접 편집
부담 ↓. pre_registration_audit.py 의 cross-ref 와 같은 schema.

사용 예:
  python scripts/rule7_trail.py list
  python scripts/rule7_trail.py list --status pending
  python scripts/rule7_trail.py show bc81a43e
  python scripts/rule7_trail.py approve bc81a43e \\
      --why "Q5 sector 면제 (Financial/Healthcare/Comm Services) — Perplexity 자문 정합" \\
      --data "commodity_margin neutral 50 적용, 운영 commit 0건" \\
      --expected "false positive 0건 + true positive sector 별 정합"
  python scripts/rule7_trail.py reject 5a5258ae \\
      --reason "ATR Phase 1.5.1 = 인프라 블로커 해소, 산식 변경 아님 (재분류)"
  python scripts/rule7_trail.py add <full_sha> [--note "..."]

schema (각 line, jsonl):
  sha / date / subject / missing
  pm_decision: null | "approved" | "rejected" | "pending"
  pm_why / pm_data / pm_expected: str | null
  pm_approved_at: ISO timestamp KST | null
  pm_rejected_reason: str | null
  added_at: ISO timestamp KST
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
TRAIL_PATH = _REPO_ROOT / "data" / "metadata" / "rule7_retroactive_trail.jsonl"
KST = timezone(timedelta(hours=9))


def _now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def _load_entries() -> List[Dict[str, Any]]:
    if not TRAIL_PATH.exists():
        return []
    entries = []
    with TRAIL_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"::warning::jsonl 손상 line skip: {e}", file=sys.stderr)
    return entries


def _save_entries(entries: List[Dict[str, Any]]) -> None:
    TRAIL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TRAIL_PATH.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _resolve_sha(prefix: str, entries: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """prefix 매칭 entry 반환. 다중 매칭 시 None + error."""
    matches = [e for e in entries if e.get("sha", "").startswith(prefix)]
    if not matches:
        return None
    if len(matches) > 1:
        sys.exit(f"::error::sha prefix '{prefix}' 다중 매칭 ({len(matches)}건). 더 길게 박으세요.")
    return matches[0]


def _status_of(entry: Dict[str, Any]) -> str:
    d = entry.get("pm_decision")
    if d == "approved":
        return "approved"
    if d == "rejected":
        return "rejected"
    return "pending"


# ── commands ────────────────────────────────────────────────────────────

def cmd_list(args: argparse.Namespace) -> int:
    entries = _load_entries()
    if args.status and args.status != "all":
        entries = [e for e in entries if _status_of(e) == args.status]
    if not entries:
        print("(빈 결과)")
        return 0
    for e in entries:
        status = _status_of(e)
        status_tag = {"approved": "✓", "rejected": "✗", "pending": "·"}.get(status, "?")
        missing = ", ".join(e.get("missing", [])) or "-"
        print(f"  {status_tag} [{status:8s}] {e['sha'][:8]} {e.get('date','')} {e['subject'][:70]}")
        print(f"    missing: {missing}")
    print(f"\n총 {len(entries)} 건")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    entries = _load_entries()
    e = _resolve_sha(args.sha, entries)
    if not e:
        sys.exit(f"::error::sha '{args.sha}' 미발견")
    print(json.dumps(e, ensure_ascii=False, indent=2))
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    entries = _load_entries()
    e = _resolve_sha(args.sha, entries)
    if not e:
        sys.exit(f"::error::sha '{args.sha}' 미발견. add 먼저 박으세요.")
    e["pm_decision"] = "approved"
    e["pm_why"] = args.why
    e["pm_data"] = args.data
    e["pm_expected"] = args.expected
    e["pm_approved_at"] = _now_kst()
    _save_entries(entries)
    print(f"  ✓ approved — {e['sha'][:8]} {e['subject'][:60]}")
    return 0


def cmd_reject(args: argparse.Namespace) -> int:
    entries = _load_entries()
    e = _resolve_sha(args.sha, entries)
    if not e:
        sys.exit(f"::error::sha '{args.sha}' 미발견")
    e["pm_decision"] = "rejected"
    e["pm_rejected_reason"] = args.reason
    e["pm_approved_at"] = _now_kst()  # 결정 박힌 시각 박음 (approved/rejected 동일 컬럼)
    _save_entries(entries)
    print(f"  ✗ rejected — {e['sha'][:8]} {e['subject'][:60]}")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    entries = _load_entries()
    if any(e.get("sha", "").startswith(args.sha[:8]) for e in entries):
        sys.exit(f"::error::sha '{args.sha[:8]}' 이미 박혀있음. approve/reject/show 사용.")
    # git 에서 full SHA / date / subject 박음
    try:
        out = subprocess.check_output(
            ["git", "log", "-1", "--pretty=format:%H|%cs|%s", args.sha],
            cwd=str(_REPO_ROOT), text=True, timeout=10,
        )
    except subprocess.SubprocessError as e:
        sys.exit(f"::error::git log 실패: {e}")
    full_sha, date, subject = out.split("|", 2)
    entry = {
        "sha": full_sha,
        "date": date,
        "subject": subject,
        "missing": args.missing or ["PM=approved"],
        "pm_decision": None,
        "pm_why": None,
        "pm_data": None,
        "pm_expected": None,
        "pm_approved_at": None,
        "added_at": _now_kst(),
    }
    if args.note:
        entry["note"] = args.note
    entries.append(entry)
    _save_entries(entries)
    print(f"  + added — {full_sha[:8]} {subject[:60]}")
    return 0


# ── argparse ────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(prog="rule7_trail", description="RULE 7 retroactive trail CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="entry 조회")
    p_list.add_argument("--status", default="all",
                        choices=["all", "pending", "approved", "rejected"])
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="단건 상세")
    p_show.add_argument("sha", help="SHA prefix (8자 이상)")
    p_show.set_defaults(func=cmd_show)

    p_approve = sub.add_parser("approve", help="PM=approved + WHY/DATA/EXPECTED 박음")
    p_approve.add_argument("sha", help="SHA prefix")
    p_approve.add_argument("--why", required=True, help="결정 이유 (정책/원전/근거)")
    p_approve.add_argument("--data", required=True, help="데이터 / 검증 / 영향 범위")
    p_approve.add_argument("--expected", required=True, help="기대 효과 / 메트릭 / 게이트")
    p_approve.set_defaults(func=cmd_approve)

    p_reject = sub.add_parser("reject", help="PM=rejected 박음 (재분류 / 산식 변경 아님)")
    p_reject.add_argument("sha", help="SHA prefix")
    p_reject.add_argument("--reason", required=True, help="거부 사유")
    p_reject.set_defaults(func=cmd_reject)

    p_add = sub.add_parser("add", help="신 entry 추가 (cron 미박힌 commit 직접 박을 때)")
    p_add.add_argument("sha", help="git SHA (full 또는 prefix)")
    p_add.add_argument("--missing", nargs="*", default=None,
                       help="기본 ['PM=approved']")
    p_add.add_argument("--note", default=None, help="메모")
    p_add.set_defaults(func=cmd_add)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
