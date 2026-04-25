"""
Supabase REST 클라이언트 (httpx-free, requests 기반).

환경변수:
  SUPABASE_URL      - 프로젝트 URL (예: https://xxxx.supabase.co)
  SUPABASE_ANON_KEY - anon/public API 키

인증 모델:
  사용자 JWT(access_token)가 있으면 user_jwt로 호출 → Supabase RLS가
  auth.uid()로 본인 행만 반환. 없으면 anon key로 폴백(공개 테이블 전용).
"""
import os
from typing import Any, Dict, List, Optional
import requests

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")


def _headers(user_jwt: Optional[str] = None) -> Dict[str, str]:
    h = {
        "apikey": SUPABASE_ANON_KEY,
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    h["Authorization"] = f"Bearer {user_jwt}" if user_jwt else f"Bearer {SUPABASE_ANON_KEY}"
    return h


def _rest(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


def is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY)


def verify_jwt(jwt: str) -> Optional[str]:
    """Supabase /auth/v1/user로 토큰을 검증하고 user_id(sub) 반환. 실패 시 None.

    반드시 서버 측에서 호출하여 클라이언트가 주장하는 user_id 대신
    Supabase가 검증한 UID만 신뢰한다.
    """
    if not jwt or not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None
    try:
        r = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {jwt}",
            },
            timeout=5,
        )
        if r.status_code != 200:
            return None
        return r.json().get("id")
    except Exception:
        return None


def select(table: str, params: Dict[str, str], user_jwt: Optional[str] = None) -> List[Dict[str, Any]]:
    r = requests.get(_rest(table), headers=_headers(user_jwt), params=params, timeout=8)
    r.raise_for_status()
    return r.json()


def insert(table: str, data: Dict[str, Any], user_jwt: Optional[str] = None) -> Dict[str, Any]:
    r = requests.post(_rest(table), headers=_headers(user_jwt), json=data, timeout=8)
    r.raise_for_status()
    rows = r.json()
    return rows[0] if isinstance(rows, list) and rows else rows


def update(
    table: str,
    match: Dict[str, str],
    data: Dict[str, Any],
    user_jwt: Optional[str] = None,
) -> List[Dict[str, Any]]:
    params = {f"{k}": f"eq.{v}" for k, v in match.items()}
    r = requests.patch(_rest(table), headers=_headers(user_jwt), params=params, json=data, timeout=8)
    r.raise_for_status()
    return r.json()


def delete(table: str, match: Dict[str, str], user_jwt: Optional[str] = None) -> None:
    params = {f"{k}": f"eq.{v}" for k, v in match.items()}
    r = requests.delete(_rest(table), headers=_headers(user_jwt), params=params, timeout=8)
    r.raise_for_status()
