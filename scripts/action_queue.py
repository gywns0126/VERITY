#!/usr/bin/env python3
"""
queue.py — user_action_queue CLI (Claude Code 측 헬퍼)

Supabase user_action_queue 테이블에 작업 추가/조회/마감 처리.
서비스 롤 키로 RLS 우회 (service_role 은 is_caller_admin() = TRUE).

사용 예:
  python scripts/queue.py list
  python scripts/queue.py list --status pending --category framer_paste
  python scripts/queue.py add "TradingPanel TimingSignal paste" \
      --category framer_paste --priority p1 \
      --commit f6d3eed --component framer-components/TradingPanel.tsx
  python scripts/queue.py done <uuid> --note "paste 완료"
  python scripts/queue.py skip <uuid>

환경변수 (.env 자동 로드):
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

import requests

# ── .env 자동 로드 (python-dotenv 없이) ─────────────────────────────────
def _load_dotenv() -> None:
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


_load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
TABLE = "user_action_queue"


def _check_env() -> None:
    missing = [k for k, v in [("SUPABASE_URL", SUPABASE_URL), ("SUPABASE_SERVICE_ROLE_KEY", SERVICE_KEY)] if not v]
    if missing:
        sys.exit(f"환경변수 누락: {', '.join(missing)} (.env 확인)")


def _headers() -> Dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _rest(path: str = "") -> str:
    return f"{SUPABASE_URL}/rest/v1/{TABLE}{path}"


# ── 명령어 구현 ──────────────────────────────────────────────────────────

def cmd_list(args: argparse.Namespace) -> int:
    _check_env()
    params: Dict[str, str] = {
        "select": "id,title,category,priority,status,commit_hash,component_path,due_at,created_at,completed_at",
        "order": "priority.asc,created_at.desc",
        "limit": str(args.limit),
    }
    if args.status:
        params["status"] = f"eq.{args.status}"
    if args.category:
        params["category"] = f"eq.{args.category}"
    if args.priority:
        params["priority"] = f"eq.{args.priority}"
    r = requests.get(_rest(), headers=_headers(), params=params, timeout=10)
    r.raise_for_status()
    rows: List[Dict[str, Any]] = r.json()
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("(빈 결과)")
        return 0
    for row in rows:
        due = row.get("due_at")
        due_str = f" 📅{due[:10]}" if due else ""
        commit = row.get("commit_hash") or ""
        commit_str = f" [{commit[:7]}]" if commit else ""
        print(
            f"[{row['priority']}] {row['status']:8s} {row['category']:18s} "
            f"{row['title']}{commit_str}{due_str}"
        )
        print(f"        id={row['id']} component={row.get('component_path') or '-'}")
    print(f"\n총 {len(rows)} 건")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    _check_env()
    payload: Dict[str, Any] = {
        "title": args.title,
        "category": args.category,
        "priority": args.priority,
    }
    if args.detail:
        payload["detail"] = args.detail
    if args.commit:
        payload["commit_hash"] = args.commit
    if args.component:
        payload["component_path"] = args.component
    if args.snippet:
        payload["code_snippet"] = args.snippet
    if args.due:
        payload["due_at"] = args.due
    r = requests.post(_rest(), headers=_headers(), json=payload, timeout=10)
    if r.status_code >= 400:
        sys.exit(f"insert 실패 [{r.status_code}]: {r.text[:300]}")
    rows = r.json()
    row = rows[0] if isinstance(rows, list) and rows else rows
    print(f"✓ 추가됨 id={row.get('id')}")
    print(f"  {row.get('priority')} {row.get('category')} — {row.get('title')}")
    return 0


def _resolve_id(prefix: str) -> str:
    """8자 이상 prefix 입력 시 전체 UUID 매칭 (편의).
    PostgREST 의 UUID 컬럼은 like 연산자 미지원 → 전체 fetch + 클라이언트 필터.
    """
    if "-" in prefix and len(prefix) >= 32:
        return prefix
    # 전체 가져와서 prefix 매칭 (행 수 적어서 OK)
    params = {"select": "id"}
    r = requests.get(_rest(), headers=_headers(), params=params, timeout=10)
    r.raise_for_status()
    rows = [row for row in r.json() if str(row.get("id", "")).startswith(prefix)]
    if len(rows) == 0:
        sys.exit(f"id prefix '{prefix}' 매칭 없음")
    if len(rows) > 1:
        sys.exit(f"id prefix '{prefix}' 다중 매칭 ({len(rows)}건) — 더 길게 입력")
    return rows[0]["id"]


def _update_status(target_id: str, status: str, note: Optional[str]) -> int:
    from datetime import datetime, timezone
    payload: Dict[str, Any] = {
        "status": status,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    if note:
        payload["user_notes"] = note
    params = {"id": f"eq.{target_id}"}
    r = requests.patch(_rest(), headers=_headers(), params=params, json=payload, timeout=10)
    if r.status_code >= 400:
        sys.exit(f"update 실패 [{r.status_code}]: {r.text[:300]}")
    rows = r.json()
    if not rows:
        sys.exit(f"id {target_id} 없음")
    row = rows[0]
    print(f"✓ {status} — {row.get('title')}")
    return 0


def cmd_done(args: argparse.Namespace) -> int:
    _check_env()
    return _update_status(_resolve_id(args.id), "done", args.note)


def cmd_skip(args: argparse.Namespace) -> int:
    _check_env()
    return _update_status(_resolve_id(args.id), "skipped", args.note)


def cmd_show(args: argparse.Namespace) -> int:
    _check_env()
    target_id = _resolve_id(args.id)
    params = {"id": f"eq.{target_id}", "select": "*"}
    r = requests.get(_rest(), headers=_headers(), params=params, timeout=10)
    r.raise_for_status()
    rows = r.json()
    if not rows:
        sys.exit(f"id {target_id} 없음")
    print(json.dumps(rows[0], ensure_ascii=False, indent=2))
    return 0


# ── reconcile: pending 태스크의 효과 검출 → 자동 done ───────────────────
#
# Framer paste 는 컴포넌트 자체 heartbeat 로 자동 종결되므로 여기서 X.
# supabase_migration 처럼 PostgREST 로 효과 검출 가능한 항목만 처리.

def _probe_table(name: str) -> bool:
    r = requests.head(
        f"{SUPABASE_URL}/rest/v1/{name}",
        headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}"},
        timeout=8,
    )
    return r.status_code in (200, 206)


def _probe_rpc(name: str) -> bool:
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/rpc/{name}",
        headers={
            "apikey": SERVICE_KEY,
            "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type": "application/json",
        },
        json={},
        timeout=8,
    )
    if r.status_code == 404:
        return False
    body = r.text
    if "PGRST202" in body or "Could not find the function" in body:
        return False
    return True


def _detect_008() -> bool:
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers={"apikey": SERVICE_KEY, "Authorization": f"Bearer {SERVICE_KEY}"},
        params={"select": "is_admin", "limit": "1"},
        timeout=8,
    )
    return r.status_code == 200


def _detect_009() -> bool:
    return _probe_table("user_action_queue") and _probe_rpc("action_queue_complete")


def _detect_010() -> bool:
    return _probe_rpc("action_queue_heartbeat")


# 새 마이그 추가 시 여기 갱신
DETECTORS = [
    ("008", _detect_008),
    ("009", _detect_009),
    ("010", _detect_010),
]


def cmd_reconcile(args: argparse.Namespace) -> int:
    _check_env()
    params = {
        "select": "id,title,component_path,status",
        "status": "eq.pending",
        "category": "eq.supabase_migration",
        "limit": "100",
    }
    r = requests.get(_rest(), headers=_headers(), params=params, timeout=10)
    r.raise_for_status()
    rows: List[Dict[str, Any]] = r.json()
    if not rows:
        print("pending supabase_migration 없음")
        return 0

    closed = 0
    for row in rows:
        title = row.get("title", "") or ""
        path = row.get("component_path", "") or ""
        haystack = f"{title} {path}"
        matched = None
        for tag, fn in DETECTORS:
            if tag in haystack:
                matched = (tag, fn)
                break
        if not matched:
            print(f"  ? {title} — 검출기 없음 (skip)")
            continue
        tag, fn = matched
        try:
            present = fn()
        except Exception as e:
            print(f"  ! {title} — 검출 에러: {e}")
            continue
        if present:
            if args.dry_run:
                print(f"  ✓ {title} — 효과 검출 ({tag}) [--dry-run]")
            else:
                _update_status(row["id"], "done", f"[auto] reconcile detected {tag}")
                closed += 1
        else:
            print(f"  · {title} — 미검출 ({tag})")

    if not args.dry_run:
        print(f"\n자동 종결: {closed} 건")
    return 0


# ── argparse ────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(prog="queue", description="user_action_queue CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="큐 조회 (default: pending)")
    p_list.add_argument("--status", default="pending",
                        choices=["pending", "in_progress", "done", "skipped", "all"])
    p_list.add_argument("--category", default=None,
                        choices=["framer_paste", "supabase_migration", "verification", "monitoring", "misc"])
    p_list.add_argument("--priority", default=None, choices=["p0", "p1", "p2"])
    p_list.add_argument("--limit", type=int, default=50)
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_add = sub.add_parser("add", help="새 작업 추가")
    p_add.add_argument("title")
    p_add.add_argument("--category", required=True,
                       choices=["framer_paste", "supabase_migration", "verification", "monitoring", "misc"])
    p_add.add_argument("--priority", default="p2", choices=["p0", "p1", "p2"])
    p_add.add_argument("--detail", default=None)
    p_add.add_argument("--commit", default=None, help="commit hash")
    p_add.add_argument("--component", default=None, help="예: framer-components/X.tsx")
    p_add.add_argument("--snippet", default=None, help="paste 용 raw URL or 코드")
    p_add.add_argument("--due", default=None, help="ISO timestamptz")
    p_add.set_defaults(func=cmd_add)

    p_done = sub.add_parser("done", help="작업 완료 처리")
    p_done.add_argument("id", help="UUID 또는 8자 이상 prefix")
    p_done.add_argument("--note", default=None)
    p_done.set_defaults(func=cmd_done)

    p_skip = sub.add_parser("skip", help="작업 스킵 처리")
    p_skip.add_argument("id")
    p_skip.add_argument("--note", default=None)
    p_skip.set_defaults(func=cmd_skip)

    p_show = sub.add_parser("show", help="단건 상세")
    p_show.add_argument("id")
    p_show.set_defaults(func=cmd_show)

    p_rec = sub.add_parser("reconcile", help="pending supabase_migration 의 효과 검출 → 자동 done")
    p_rec.add_argument("--dry-run", action="store_true", help="검출만 하고 done 처리 안 함")
    p_rec.set_defaults(func=cmd_reconcile)

    # status 'all' 처리
    args = p.parse_args()
    if args.cmd == "list" and args.status == "all":
        args.status = None
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
