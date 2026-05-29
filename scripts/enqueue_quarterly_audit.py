#!/usr/bin/env python3
"""enqueue_quarterly_audit — 분기 정밀 audit reminder 자동 등록.

PM goal "100억 책임자 mindset" 5/29 sprint 후속. 분기 1회 [[project_full_audit_2026_05_29]]
9 단계 audit 재실행 의무 — UserActionBell 표시 → 사용자 인지 path 확보.

작동:
- 분기 cron (`0 0 1 1,4,7,10 *` = UTC 분기 첫째 날 = KST 09:00) trigger
- Supabase user_action_queue 에 verification p1 entry 등록
- due_at = 분기 첫째 날 09:00 KST + 14일 (관찰 window)
- 중복 check: title prefix 매칭 pending entry 있으면 skip (멱등)

환경변수 (action_queue.py 동일):
  SUPABASE_URL
  SUPABASE_SERVICE_ROLE_KEY

사용:
  python3 scripts/enqueue_quarterly_audit.py        # 정합 cron 호출
  python3 scripts/enqueue_quarterly_audit.py --dry  # dry-run, insert X

[[feedback_auto_schedule_action_queue]] 정합 — 채팅 안내 휘발 차단.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

# ── .env 자동 로드 ───────────────────────────────────────
def _load_dotenv() -> None:
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
    )
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
KST = timezone(timedelta(hours=9))

TITLE_PREFIX = "분기 정밀 audit 재실행"
DETAIL = (
    "100억 책임자 mindset 9 단계 audit 재실행 — 디렉토리/의존성/workflow/test/"
    "의심패턴/산식/RULE/TIDE/보고서. P0/P1/P2 분류 + source-of-truth drift 측정. "
    "[[project_full_audit_2026_05_29]] 정합. trigger = 채팅 '분기 audit' 또는 '100억 책임자'."
)


def _headers() -> dict:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _check_env() -> None:
    if not SUPABASE_URL or not SERVICE_KEY:
        sys.exit("ERROR: SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY 환경변수 필요.")


def _quarter_due_at() -> str:
    """현 분기 첫째 날 + 14일 + 09:00 KST. cron 실행 시점 정합."""
    now = datetime.now(KST)
    quarter_month = ((now.month - 1) // 3) * 3 + 1
    quarter_start = now.replace(
        month=quarter_month, day=1, hour=9, minute=0, second=0, microsecond=0
    )
    due = quarter_start + timedelta(days=14)
    return due.isoformat()


def _pending_exists() -> bool:
    """현 pending entry 중 TITLE_PREFIX 매칭 = True (중복 차단)."""
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}"
    params = {
        "select": "id,title,status",
        "status": "eq.pending",
        "title": f"ilike.{TITLE_PREFIX}%",
    }
    try:
        r = requests.get(url, headers=_headers(), params=params, timeout=10)
        if r.status_code >= 400:
            print(f"  ! pending check fail [{r.status_code}]: {r.text[:200]}", file=sys.stderr)
            return False
        rows = r.json()
        return len(rows) > 0 if isinstance(rows, list) else False
    except requests.RequestException as e:
        print(f"  ! pending check exception: {e}", file=sys.stderr)
        return False


def enqueue(dry: bool = False) -> int:
    _check_env()
    if _pending_exists():
        print(f"✓ skip — pending '{TITLE_PREFIX}' entry 이미 존재 (멱등)")
        return 0
    due_at = _quarter_due_at()
    title = f"{TITLE_PREFIX} (100억 책임자 9 단계)"
    payload = {
        "title": title,
        "category": "verification",
        "priority": "p1",
        "actor": "user",
        "detail": DETAIL,
        "due_at": due_at,
    }
    if dry:
        print(f"DRY-RUN payload: {payload}")
        return 0
    url = f"{SUPABASE_URL}/rest/v1/{TABLE}"
    r = requests.post(url, headers=_headers(), json=payload, timeout=10)
    if r.status_code >= 400 and "actor" in payload and "PGRST204" in r.text:
        payload.pop("actor", None)
        r = requests.post(url, headers=_headers(), json=payload, timeout=10)
    if r.status_code >= 400:
        print(f"ERROR insert [{r.status_code}]: {r.text[:300]}", file=sys.stderr)
        return 1
    rows = r.json()
    row = rows[0] if isinstance(rows, list) and rows else rows
    print(f"✓ 등록 id={row.get('id')} due={due_at}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="분기 정밀 audit reminder 자동 등록")
    p.add_argument("--dry", action="store_true", help="dry-run, insert X")
    args = p.parse_args()
    return enqueue(dry=args.dry)


if __name__ == "__main__":
    sys.exit(main())
