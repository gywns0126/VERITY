"""
Supabase REST 클라이언트 (httpx-free, requests 기반).

환경변수:
  SUPABASE_URL      - 프로젝트 URL (예: https://xxxx.supabase.co)
  SUPABASE_ANON_KEY - anon/public API 키
"""
import os
from typing import Any, Dict, List, Optional
import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")


def _headers(user_id: Optional[str] = None) -> Dict[str, str]:
    h = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    if user_id:
        h["x-user-id"] = user_id
    return h


def _rest(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


def is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY)


def select(table: str, params: Dict[str, str], user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    r = requests.get(_rest(table), headers=_headers(user_id), params=params, timeout=8)
    r.raise_for_status()
    return r.json()


def insert(table: str, data: Dict[str, Any], user_id: Optional[str] = None) -> Dict[str, Any]:
    r = requests.post(_rest(table), headers=_headers(user_id), json=data, timeout=8)
    r.raise_for_status()
    rows = r.json()
    return rows[0] if isinstance(rows, list) and rows else rows


def update(
    table: str,
    match: Dict[str, str],
    data: Dict[str, Any],
    user_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    params = {f"{k}": f"eq.{v}" for k, v in match.items()}
    r = requests.patch(_rest(table), headers=_headers(user_id), params=params, json=data, timeout=8)
    r.raise_for_status()
    return r.json()


def delete(table: str, match: Dict[str, str], user_id: Optional[str] = None) -> None:
    params = {f"{k}": f"eq.{v}" for k, v in match.items()}
    r = requests.delete(_rest(table), headers=_headers(user_id), params=params, timeout=8)
    r.raise_for_status()
