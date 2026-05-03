"""
VERITY 리포트 PDF 서빙 — Supabase Storage signed URL 발급.

배경 (2026-05-03):
  기존 Framer 컴포넌트는 raw.githubusercontent.com 의 PDF 파일을
  새창으로 직접 열었으나, data/.gitignore 가 PDF 를 잡아 GitHub 에
  업로드된 적 자체가 없어 항상 404. 또한 admin 리포트는 검증 전
  추천 데이터를 포함하므로 public URL 노출 자체가 정책 위반
  (feedback_scope: 시스템 트랙 비공개).

  → cron 이 PDF 생성 후 Supabase Storage private bucket
    `verity-reports` 에 업로드. 이 함수가 JWT/admin 검증 후
    short-lived signed URL 을 발급한다.

엔드포인트:
  GET /api/reports?period=daily&type=admin
    → admin: Bearer JWT 필수 + profiles.is_admin=TRUE
    → public: Bearer JWT 필수 (일반 로그인 사용자)
    → 응답: 200 {url, filename, expires_in} | 401 | 403 | 404 | 500
    → 프론트가 응답 받은 url 로 window.open. signed URL 자체가 시간제한이라
      쿼리에 노출되어도 안전.

period: daily | weekly | monthly | quarterly | semi | annual
type:   admin  | public

파일명 규약: verity_<period>_<type>.pdf (cron 의 latest alias)
"""
from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler
from typing import Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests

_logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

BUCKET = "verity-reports"

VALID_PERIODS = {"daily", "weekly", "monthly", "quarterly", "semi", "annual"}
VALID_TYPES = {"admin", "public"}

# admin 은 5분 (민감), public 은 1시간
SIGNED_URL_TTL = {"admin": 300, "public": 3600}


def _cors_headers(h):
    try:
        from api.cors_helper import resolve_origin  # type: ignore
    except Exception:
        resolve_origin = lambda _o: ""  # noqa: E731
    origin = resolve_origin(h.headers.get("Origin") or "")
    if origin:
        h.send_header("Access-Control-Allow-Origin", origin)
        h.send_header("Vary", "Origin")
    h.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")


def _json(h, status: int, body: dict):
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    h.send_response(status)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Cache-Control", "no-store")
    _cors_headers(h)
    h.end_headers()
    h.wfile.write(payload)


def _extract_jwt(h) -> Optional[str]:
    auth = (h.headers.get("Authorization") or "").strip()
    if auth.startswith("Bearer "):
        tok = auth[7:].strip()
        return tok or None
    return None


def _verify_user(jwt: str) -> Optional[str]:
    """JWT 검증 → user_id 반환. 실패 시 None."""
    if not jwt or not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None
    try:
        r = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {jwt}"},
            timeout=5,
        )
        if r.status_code != 200:
            return None
        return r.json().get("id")
    except (requests.RequestException, ValueError) as e:
        _logger.warning("user verify failed: %s", e)
        return None


def _is_admin(jwt: str, user_id: str) -> bool:
    """profiles.is_admin 조회. RLS 가 본인 row 만 허용하는데 admin 본인 조회라 OK."""
    try:
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            params={"id": f"eq.{user_id}", "select": "is_admin"},
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {jwt}"},
            timeout=5,
        )
        if r.status_code != 200:
            return False
        rows = r.json()
        return bool(rows and rows[0].get("is_admin") is True)
    except (requests.RequestException, ValueError) as e:
        _logger.warning("admin check failed: %s", e)
        return False


def _create_signed_url(filename: str, ttl_seconds: int) -> Tuple[Optional[str], Optional[int]]:
    """Supabase Storage signed URL 발급. service_role 키 필요.

    반환: (url, http_status). url 이 None 이면 status 로 분기.
    """
    if not SUPABASE_SERVICE_ROLE_KEY:
        _logger.error("SUPABASE_SERVICE_ROLE_KEY 미설정 — signed URL 발급 불가")
        return None, 500
    try:
        r = requests.post(
            f"{SUPABASE_URL}/storage/v1/object/sign/{BUCKET}/{filename}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
            },
            json={"expiresIn": ttl_seconds},
            timeout=8,
        )
        if r.status_code == 400 or r.status_code == 404:
            return None, 404
        if r.status_code != 200:
            _logger.warning("sign URL failed: status=%s body=%s", r.status_code, r.text[:200])
            return None, 500
        signed_path = r.json().get("signedURL") or r.json().get("signedUrl")
        if not signed_path:
            return None, 500
        # signedURL 은 보통 /storage/v1/object/sign/... 형식의 path
        if signed_path.startswith("http"):
            return signed_path, 200
        return f"{SUPABASE_URL}{signed_path}", 200
    except (requests.RequestException, ValueError) as e:
        _logger.error("signed URL error: %s", e)
        return None, 500


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        _cors_headers(self)
        self.end_headers()

    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            period = (qs.get("period", [""])[0] or "").strip().lower()
            kind = (qs.get("type", [""])[0] or "").strip().lower()

            if period not in VALID_PERIODS:
                _json(self, 400, {"error": "invalid period",
                                   "valid": sorted(VALID_PERIODS)})
                return
            if kind not in VALID_TYPES:
                _json(self, 400, {"error": "invalid type",
                                   "valid": sorted(VALID_TYPES)})
                return

            jwt = _extract_jwt(self)
            if not jwt:
                _json(self, 401, {"error": "Unauthorized — Bearer token required"})
                return
            user_id = _verify_user(jwt)
            if not user_id:
                _json(self, 401, {"error": "Invalid token"})
                return

            if kind == "admin" and not _is_admin(jwt, user_id):
                _json(self, 403, {"error": "Admin only"})
                return

            filename = f"verity_{period}_{kind}.pdf"
            ttl = SIGNED_URL_TTL[kind]
            url, status = _create_signed_url(filename, ttl)
            if status == 404:
                _json(self, 404, {
                    "error": "report_not_found",
                    "message": "리포트가 아직 생성되지 않았습니다",
                    "filename": filename,
                })
                return
            if not url:
                _json(self, 500, {"error": "signed_url_failed"})
                return

            _json(self, 200, {
                "url": url,
                "filename": filename,
                "expires_in": ttl,
                "period": period,
                "type": kind,
            })
        except Exception as e:
            _logger.exception("reports handler error")
            _json(self, 500, {"error": "internal"})
