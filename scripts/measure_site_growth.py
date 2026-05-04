#!/usr/bin/env python3
"""measure_site_growth.py — 사이트 성장 measurement 단일 SOT 산출.

feedback_site_growth_is_core 정합 — 핵심 로직 #1 의 측정 layer.

산출 metric (2종):
  - daily_unique_visitors  : 직전 24h Supabase live_visitors distinct session_id
  - profiles_total         : 오늘 시점 Supabase profiles 누적 row count

영속화: data/metadata/site_growth.jsonl (매일 1 entry append, idempotent)
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GROWTH_PATH = os.path.join(REPO_ROOT, "data", "metadata", "site_growth.jsonl")

KST = timezone(timedelta(hours=9))
logger = logging.getLogger(__name__)


def _load_dotenv() -> None:
    env_path = os.path.join(REPO_ROOT, ".env")
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


def _check_env() -> None:
    missing = [k for k, v in [("SUPABASE_URL", SUPABASE_URL), ("SUPABASE_SERVICE_ROLE_KEY", SERVICE_KEY)] if not v]
    if missing:
        sys.exit(f"환경변수 누락: {', '.join(missing)}")


def _headers() -> Dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Prefer": "count=exact",
    }


def _count_with_filter(table: str, filter_query: str = "") -> Optional[int]:
    """Supabase REST count — Content-Range 헤더의 total 추출.

    filter_query 예: "last_seen=gte.2026-05-03T16:00:00Z"
    """
    url = f"{SUPABASE_URL}/rest/v1/{table}?select=*{('&' + filter_query) if filter_query else ''}&limit=0"
    try:
        r = requests.head(url, headers=_headers(), timeout=10)
        if r.status_code >= 400:
            logger.warning("supabase count failed [%s]: %s", r.status_code, r.text[:200])
            return None
        cr = r.headers.get("content-range") or r.headers.get("Content-Range") or ""
        # 형식: "0-0/123" 또는 "*/123"
        if "/" in cr:
            total = cr.rsplit("/", 1)[-1]
            if total.isdigit():
                return int(total)
        return None
    except (requests.RequestException, ValueError) as e:
        logger.warning("supabase count exception: %s", e)
        return None


def _distinct_count_via_select(table: str, distinct_col: str, filter_query: str) -> Optional[int]:
    """distinct count — REST 가 직접 지원 안 해서 페이지네이션 + set(). 24h 단위라 row 수 수만건 이내 가정."""
    url = f"{SUPABASE_URL}/rest/v1/{table}?select={distinct_col}&{filter_query}"
    seen: set = set()
    offset = 0
    page = 1000
    try:
        while True:
            paginated = url + f"&offset={offset}&limit={page}"
            r = requests.get(paginated, headers={**_headers(), "Range": f"{offset}-{offset+page-1}"}, timeout=15)
            if r.status_code >= 400:
                logger.warning("distinct fetch failed [%s]: %s", r.status_code, r.text[:200])
                return None
            rows = r.json() or []
            if not rows:
                break
            for row in rows:
                v = row.get(distinct_col)
                if v is not None:
                    seen.add(v)
            if len(rows) < page:
                break
            offset += page
        return len(seen)
    except (requests.RequestException, ValueError) as e:
        logger.warning("distinct fetch exception: %s", e)
        return None


def _measure() -> Dict[str, Any]:
    now = datetime.now(KST)
    cutoff = (now - timedelta(hours=24)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1) live_visitors 직전 24h distinct session_id
    daily_uv = _distinct_count_via_select(
        "live_visitors", "session_id", f"last_seen=gte.{cutoff}"
    )

    # 2) profiles 누적 row count
    profiles_total = _count_with_filter("profiles")

    return {
        "evaluation_date": now.isoformat(),
        "daily_unique_visitors": daily_uv,
        "profiles_total": profiles_total,
        "window_24h_cutoff_utc": cutoff,
    }


def _append_idempotent(entry: Dict[str, Any]) -> bool:
    """같은 날 중복 호출 시 append 스킵 (idempotent)."""
    today = entry["evaluation_date"][:10]
    if os.path.exists(GROWTH_PATH):
        try:
            with open(GROWTH_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if row.get("evaluation_date", "")[:10] == today:
                        return False  # 이미 오늘 entry 있음
        except OSError:
            pass

    os.makedirs(os.path.dirname(GROWTH_PATH), exist_ok=True)
    with open(GROWTH_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return True


def main() -> int:
    _check_env()
    entry = _measure()
    appended = _append_idempotent(entry)
    print(json.dumps(entry, ensure_ascii=False, indent=2))
    print(f"\n[{'APPENDED' if appended else 'SKIPPED (idempotent)'}] → {GROWTH_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
