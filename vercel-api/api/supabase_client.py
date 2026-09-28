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


class AuthServiceUnavailable(Exception):
    """Authentication dependency failed; never authorize on this outcome."""


def verify_jwt(jwt: str, *, strict: bool = False) -> Optional[str]:
    """Supabase /auth/v1/user로 토큰을 검증하고 user_id(sub) 반환. 실패 시 None.

    반드시 서버 측에서 호출하여 클라이언트가 주장하는 user_id 대신
    Supabase가 검증한 UID만 신뢰한다. strict=True는 의존성/설정/응답 오류를
    AuthServiceUnavailable로 구분하며, 실제 토큰 거절은 계속 None을 반환한다.
    """
    if not jwt:
        return None
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        if strict:
            raise AuthServiceUnavailable
        return None
    try:
        r = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {jwt}",
            },
            timeout=5,
            allow_redirects=not strict,
        )
        if r.status_code != 200:
            if strict and r.status_code not in (400, 401, 403):
                raise AuthServiceUnavailable
            return None
        uid = r.json().get("id")
        if strict and (not isinstance(uid, str) or not uid.strip()):
            raise AuthServiceUnavailable
        return uid
    except Exception:
        if strict:
            # Raw exceptions/upstream bodies can contain credentials or user data.
            raise AuthServiceUnavailable from None
        return None


def select(
    table: str,
    params: Dict[str, str],
    user_jwt: Optional[str] = None,
    *,
    strict: bool = False,
) -> List[Dict[str, Any]]:
    """Read rows; strict auth reads require HTTP 200, preserving 401/403 denials."""
    if strict and not is_configured():
        raise AuthServiceUnavailable
    r = requests.get(
        _rest(table), headers=_headers(user_jwt), params=params, timeout=8,
        allow_redirects=not strict,
    )
    if strict and r.status_code not in (200, 401, 403):
        raise AuthServiceUnavailable
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
