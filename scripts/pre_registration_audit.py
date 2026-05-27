#!/usr/bin/env python3
"""pre_registration_audit — 산식 변경 commit 의 PM=approved + WHY/DATA/EXPECTED audit.

PM=approved 2026-05-23 (plan §Phase 1-c).
WHY: [[feedback_pm_decision_trail_in_commit]] WHY/DATA/EXPECTED 3요소 의무 +
     CLAUDE.md RULE 7 자기 산식 임계 조정 1회만 PM 사전 승인 의무.
     산식 변경 commit 박음 → 4요소 미박힘 = silent drift → cockpit_state.YELLOW.
DATA: git log --since=7d --grep 산식 변경 키워드 후보 commit → message 4요소 정합 검증.
EXPECTED: 매일 KST 09:00 (operator_deadman 직후 chain) 실행 → 미박힌 commit list
          → cockpit_state.pre_registration_pending 박음 → severity rule YELLOW.

source: [[project_win_condition_decision]] option 2 + [[feedback_methodology_pre_registration]].
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

_REPO_ROOT = Path(__file__).resolve().parents[1]
COCKPIT_PATH = _REPO_ROOT / "data" / "metadata" / "cockpit_state.json"
AUDIT_LEDGER = _REPO_ROOT / "data" / "metadata" / "pre_registration_audit.jsonl"

# 산식 변경 의심 키워드 (commit message subject 또는 body)
# RULE 7 정합 — 자기 산식 임계 조정 1회 권한 사용 시그널만 박음.
# 'grade' / 'weight' 단독 박지 않음 (UI / refactor commit 박힌 부분 false positive).
_FORMULA_KEYWORDS = [
    "사전등록",
    "자기 산식", "임계 조정", "가중치 조정",
    "산식 변경", "공식 변경", "캘리브레이션",
    "constitution_patch",
]

# Negate — 박힌 commit 의 산식 미변경 시그널 (false positive 차단)
_NEGATE_KEYWORDS = [
    "RULE 7 미적용", "RULE 7 비대상", "RULE 7 적용 X",
    "값 변경 0", "산식 수정 X", "노출만", "UI 만",
]

# 4요소 정규식 — 부분 매치 (대소문자 무시)
_PM_APPROVED_RE = re.compile(r"PM[=\s]*approved", re.IGNORECASE)
_WHY_RE = re.compile(r"WHY[:\s]", re.IGNORECASE)
_DATA_RE = re.compile(r"DATA[:\s]", re.IGNORECASE)
_EXPECTED_RE = re.compile(r"EXPECTED[:\s]", re.IGNORECASE)


def _git_log(since_days: int = 7) -> List[Dict[str, Any]]:
    """git log --since=Nd 후보 commit list 박음.

    Returns: [{sha, date, subject, body}, ...] 최신순.
    """
    fmt = "%H\x1f%ad\x1f%s\x1f%b\x1e"  # SHA / date / subject / body / record-sep
    try:
        out = subprocess.check_output(
            ["git", "log", f"--since={since_days}.days",
             "--date=short", f"--pretty=format:{fmt}"],
            cwd=str(_REPO_ROOT), text=True, timeout=30,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
        print(f"  ✗ git log 실패: {e}", file=sys.stderr)
        return []

    commits = []
    for record in out.split("\x1e"):
        record = record.strip("\n").strip()
        if not record:
            continue
        parts = record.split("\x1f", 3)
        if len(parts) < 3:
            continue
        sha = parts[0]
        date = parts[1]
        subject = parts[2]
        body = parts[3] if len(parts) > 3 else ""
        commits.append({
            "sha": sha,
            "short_sha": sha[:8],
            "date": date,
            "subject": subject,
            "body": body,
            "full_message": subject + "\n" + body,
        })
    return commits


def _is_formula_change_candidate(commit: Dict[str, Any]) -> bool:
    """commit message 박힌 부분 산식 변경 의심 키워드 매치.

    Negate 키워드 박힘 시 false positive 차단 (값 변경 0 / UI 만 / RULE 7 비대상).
    """
    msg = commit["full_message"]
    msg_lower = msg.lower()
    # Negate 박힘 = candidate 박지 X
    if any(neg.lower() in msg_lower for neg in _NEGATE_KEYWORDS):
        return False
    return any(kw.lower() in msg_lower for kw in _FORMULA_KEYWORDS)


def _audit_commit(commit: Dict[str, Any]) -> Dict[str, Any]:
    """4요소 정합 검증 박음.

    Returns: {
        sha, date, subject,
        is_candidate: bool,
        has_pm: bool, has_why: bool, has_data: bool, has_expected: bool,
        missing: [str],  # 미박힌 요소 list
        passed: bool,    # 4요소 모두 박힘
    }
    """
    msg = commit["full_message"]
    has_pm = bool(_PM_APPROVED_RE.search(msg))
    has_why = bool(_WHY_RE.search(msg))
    has_data = bool(_DATA_RE.search(msg))
    has_expected = bool(_EXPECTED_RE.search(msg))

    missing = []
    if not has_pm:
        missing.append("PM=approved")
    if not has_why:
        missing.append("WHY")
    if not has_data:
        missing.append("DATA")
    if not has_expected:
        missing.append("EXPECTED")

    return {
        "sha": commit["short_sha"],
        "date": commit["date"],
        "subject": commit["subject"][:80],
        "is_candidate": True,
        "has_pm": has_pm,
        "has_why": has_why,
        "has_data": has_data,
        "has_expected": has_expected,
        "missing": missing,
        "passed": len(missing) == 0,
    }


def audit_recent_commits(since_days: int = 7) -> List[Dict[str, Any]]:
    """7일 내 산식 변경 의심 commit audit.

    Returns: missing 박힌 commit list (pending). passed=True 박은 commit 박지 않음.
    """
    commits = _git_log(since_days=since_days)
    pending = []
    for c in commits:
        if not _is_formula_change_candidate(c):
            continue
        result = _audit_commit(c)
        if not result["passed"]:
            pending.append(result)
    return pending


def _update_cockpit_state(pending: List[Dict[str, Any]]) -> None:
    """cockpit_state.json 의 pre_registration_pending field 박음.

    cockpit_state.json 부재 시 skip (cockpit_aggregate 가 먼저 박혀야 함).
    """
    if not COCKPIT_PATH.exists():
        print(f"  ⚠ cockpit_state.json 부재 — skip", file=sys.stderr)
        return
    try:
        with COCKPIT_PATH.open("r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ✗ cockpit_state.json read 실패: {e}", file=sys.stderr)
        return

    state["pre_registration_pending"] = pending

    try:
        with COCKPIT_PATH.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"  ✗ cockpit_state.json write 실패: {e}", file=sys.stderr)


def _append_audit_ledger(pending: List[Dict[str, Any]]) -> None:
    """pre_registration_audit.jsonl 박음 — 시계열 trail."""
    AUDIT_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "pending_count": len(pending),
        "pending": pending,
    }
    try:
        with AUDIT_LEDGER.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"  ✗ audit ledger write 실패: {e}", file=sys.stderr)


def main() -> int:
    """daily 진입점 (KST 09:00 cron)."""
    pending = audit_recent_commits(since_days=7)
    _update_cockpit_state(pending)
    _append_audit_ledger(pending)

    print(f"  ✓ pre_registration_audit 박힘: 산식 의심 commit {len(pending)}건 (pending)")
    for p in pending[:5]:
        print(f"    - {p['sha']} {p['date']} {p['subject']}")
        print(f"      missing: {', '.join(p['missing'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
