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
# 좁힘 (2026-05-28): 헐거운 키워드 ("산식 변경" / "사전등록" / "자기 산식")
# 단독 박지 않음 (메모 cross-ref / 정책 참조 false positive). diff 검증 병행.
_FORMULA_KEYWORDS = [
    "임계 조정", "임계 변경", "임계 재설계",
    "가중치 조정", "가중치 변경",
    "공식 변경", "캘리브레이션",
    "constitution_patch",
    "산식 사전등록", "RULE 7 사전등록", "PM 사전 승인",
    "pre-register",
]

# Negate — 박힌 commit 의 산식 미변경 시그널 (false positive 차단)
_NEGATE_KEYWORDS = [
    "RULE 7 미적용", "RULE 7 비대상", "RULE 7 적용 X",
    "값 변경 0", "산식 수정 X", "노출만", "UI 만",
    "라벨 정정", "label 정정",
]

# 산식 source 파일 glob — diff 검증 (좁힘 ABSOLUTE).
# candidate = 키워드 매칭 AND diff 에 _FORMULA_FILES ≥ 1 박힘.
# 단순 메모/docs/cron yml commit = diff 0 → skip.
_FORMULA_FILES = [
    "data/verity_constitution.json",
    "api/intelligence/factors/",
    "api/intelligence/verity_brain.py",
    "api/intelligence/factor.py",
    "api/intelligence/stress.py",
    "api/intelligence/regime.py",
    "api/intelligence/portfolio.py",
    "api/intelligence/attribution.py",
    "api/analyzers/wide_scan.py",
    "api/vams/engine.py",
    "api/config.py",
]


def _get_changed_files(sha: str) -> List[str]:
    """commit 의 변경 파일 list (path string)."""
    try:
        out = subprocess.check_output(
            ["git", "show", "--name-only", "--pretty=format:", sha],
            cwd=str(_REPO_ROOT), text=True, timeout=10,
        )
        return [line.strip() for line in out.splitlines() if line.strip()]
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return []


def _diff_has_formula_file(sha: str) -> bool:
    """변경 파일 중 _FORMULA_FILES prefix 매칭 ≥ 1."""
    changed = _get_changed_files(sha)
    for f in changed:
        for prefix in _FORMULA_FILES:
            if f == prefix or f.startswith(prefix):
                return True
    return False

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
    """commit message 키워드 매치 AND diff 에 _FORMULA_FILES 박힘.

    2-stage 검증 (2026-05-28 좁힘):
      1. commit message _FORMULA_KEYWORDS 매칭 (좁힘 후)
      2. Negate 박힘 = false (값 변경 0 / UI 만 / RULE 7 비대상 / 라벨 정정)
      3. diff 에 _FORMULA_FILES ≥ 1 박힘 = candidate
         (인프라/docs/cron yml commit = diff 0 → false)
    """
    msg = commit["full_message"]
    msg_lower = msg.lower()
    # Negate 박힘 = candidate 박지 X
    if any(neg.lower() in msg_lower for neg in _NEGATE_KEYWORDS):
        return False
    # 키워드 매칭 0 = skip
    if not any(kw.lower() in msg_lower for kw in _FORMULA_KEYWORDS):
        return False
    # diff 검증 — 산식 source 파일 변경 0 = skip
    return _diff_has_formula_file(commit["sha"])


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


def _audit_sha_list(sha_list: List[str]) -> List[Dict[str, Any]]:
    """SHA list 직접 검증 (PR / push mode). cron 의 _git_log 우회."""
    pending = []
    for sha in sha_list:
        sha = sha.strip()
        if not sha:
            continue
        try:
            msg = subprocess.check_output(
                ["git", "log", "-1", "--pretty=format:%s%n%b", sha],
                cwd=str(_REPO_ROOT), text=True, timeout=10,
            )
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            continue
        parts = msg.split("\n", 1)
        subject = parts[0]
        body = parts[1] if len(parts) > 1 else ""
        commit = {
            "sha": sha,
            "short_sha": sha[:8],
            "date": "",
            "subject": subject,
            "body": body,
            "full_message": subject + "\n" + body,
        }
        if not _is_formula_change_candidate(commit):
            continue
        result = _audit_commit(commit)
        if not result["passed"]:
            pending.append(result)
    return pending


def main() -> int:
    """진입점.

    --mode cron      : 7일 lookback + cockpit_state + ledger (기본, KST 09:15 cron)
    --mode pr-check  : --base ref 와 HEAD 비교 → fail 시 exit 1 (PR pre-merge)
    --mode commit    : --sha 단일 commit 검증 → ::warning:: post-hoc (push trigger)
    """
    import argparse
    p = argparse.ArgumentParser(description="RULE 7 산식 변경 commit audit")
    p.add_argument("--mode", choices=["cron", "pr-check", "commit"], default="cron")
    p.add_argument("--base", default="origin/main", help="pr-check base ref")
    p.add_argument("--sha", default="HEAD", help="commit mode 검증 SHA")
    p.add_argument("--since-days", type=int, default=7, help="cron lookback days")
    args = p.parse_args()

    if args.mode == "cron":
        pending = audit_recent_commits(since_days=args.since_days)
        _update_cockpit_state(pending)
        _append_audit_ledger(pending)
        print(f"  ✓ pre_registration_audit 박힘: 산식 의심 commit {len(pending)}건 (pending)")
        for p_ in pending[:5]:
            print(f"    - {p_['sha']} {p_['date']} {p_['subject']}")
            print(f"      missing: {', '.join(p_['missing'])}")
        return 0

    if args.mode == "pr-check":
        try:
            out = subprocess.check_output(
                ["git", "rev-list", f"{args.base}..HEAD"],
                cwd=str(_REPO_ROOT), text=True, timeout=15,
            )
        except subprocess.SubprocessError as e:
            print(f"::error::git rev-list 실패: {e}", file=sys.stderr)
            return 1
        sha_list = [s.strip() for s in out.splitlines() if s.strip()]
        if not sha_list:
            print("no new commits")
            return 0
        pending = _audit_sha_list(sha_list)
        if not pending:
            print(f"  ✓ {len(sha_list)} commits — RULE 7 정합")
            return 0
        for p_ in pending:
            print(f"::error::RULE 7 violation {p_['sha']}: missing {', '.join(p_['missing'])} — {p_['subject']}")
        return 1

    if args.mode == "commit":
        pending = _audit_sha_list([args.sha])
        if not pending:
            return 0
        for p_ in pending:
            print(f"::warning::RULE 7 post-hoc violation {p_['sha']}: missing {', '.join(p_['missing'])} — {p_['subject']}")
        return 0  # post-hoc = warning only, exit 0 (이미 main 박힘)

    return 0


if __name__ == "__main__":
    sys.exit(main())
