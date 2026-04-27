"""
admin/* 공통 — portfolio.json fetch + JWT 인증 + 관리자 게이트.

엔드포인트 5종 (brain_health / data_health / drift / trust / explain) 이
공유. Vercel Serverless 콜드 스타트 최소화 위해 모듈 레벨 캐시 (60초).
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

import requests

_logger = logging.getLogger(__name__)

PORTFOLIO_URL = os.environ.get(
    "PORTFOLIO_RAW_URL",
    "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
ADMIN_BYPASS_TOKEN = os.environ.get("ADMIN_BYPASS_TOKEN", "")  # 본인 접근용 단일 토큰

_PORTFOLIO_CACHE: Dict[str, Any] = {"data": None, "fetched_at": 0}
_PORTFOLIO_TTL = 60  # 초


def fetch_portfolio() -> Optional[dict]:
    """GitHub raw URL 에서 portfolio.json fetch — 60초 모듈 캐시."""
    now = time.time()
    if _PORTFOLIO_CACHE["data"] and (now - _PORTFOLIO_CACHE["fetched_at"] < _PORTFOLIO_TTL):
        return _PORTFOLIO_CACHE["data"]
    try:
        r = requests.get(PORTFOLIO_URL, timeout=10)
        r.raise_for_status()
        data = r.json()
        _PORTFOLIO_CACHE["data"] = data
        _PORTFOLIO_CACHE["fetched_at"] = now
        return data
    except (requests.RequestException, ValueError) as e:
        _logger.warning("portfolio fetch failed: %s", e)
        return _PORTFOLIO_CACHE["data"]  # 캐시 stale 반환


def get_observability(portfolio: Optional[dict]) -> Dict[str, Any]:
    """portfolio.observability 슬림 요약 추출. 없으면 빈 dict."""
    if not isinstance(portfolio, dict):
        return {}
    obs = portfolio.get("observability")
    if not isinstance(obs, dict):
        return {}
    return obs


def is_admin_token(token: str) -> bool:
    """ADMIN_BYPASS_TOKEN 단순 비교. 본인 단독 운영 — JWT 인증 대안."""
    return bool(ADMIN_BYPASS_TOKEN and token and token == ADMIN_BYPASS_TOKEN)


def verify_admin_jwt(jwt: str) -> bool:
    """Supabase JWT 검증 + profiles.is_admin = true 체크."""
    if not jwt or not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return False
    try:
        r = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {jwt}"},
            timeout=5,
        )
        if r.status_code != 200:
            return False
        user_id = r.json().get("id")
        if not user_id:
            return False
        # profiles.is_admin
        p = requests.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            params={"id": f"eq.{user_id}", "select": "is_admin"},
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {jwt}"},
            timeout=5,
        )
        if p.status_code != 200:
            return False
        rows = p.json()
        return bool(rows and rows[0].get("is_admin") is True)
    except (requests.RequestException, ValueError) as e:
        _logger.warning("admin verify failed: %s", e)
        return False


def authorize(headers_dict: Dict[str, str]) -> Tuple[bool, str]:
    """
    헤더에서 인증 추출 + 검증.

    우선순위:
      1. X-Admin-Token: ADMIN_BYPASS_TOKEN 일치 → ok
      2. Authorization: Bearer <jwt> → Supabase 검증 + is_admin=true → ok

    Returns: (is_authorized, reason)
    """
    bypass = headers_dict.get("x-admin-token") or headers_dict.get("X-Admin-Token")
    if bypass and is_admin_token(bypass):
        return True, "bypass_token"

    auth = headers_dict.get("authorization") or headers_dict.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        jwt = auth.split(" ", 1)[1].strip()
        if verify_admin_jwt(jwt):
            return True, "supabase_admin"

    if not ADMIN_BYPASS_TOKEN and not SUPABASE_URL:
        return False, "no_auth_configured"
    return False, "unauthorized"


def write_response(handler, status: int, body: dict, cache: str = "no-store") -> None:
    """공통 응답 헬퍼. CORS 포함."""
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", cache)
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Token")
    handler.end_headers()
    handler.wfile.write(payload)


def write_options(handler) -> None:
    handler.send_response(200)
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Token")
    handler.end_headers()


def headers_to_dict(handler) -> Dict[str, str]:
    """BaseHTTPRequestHandler.headers 를 dict 로."""
    out: Dict[str, str] = {}
    for k, v in handler.headers.items():
        out[k.lower()] = v
    return out
