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
    → 최신 (latest alias) PDF signed URL 발급
    → 응답: 200 {url, filename, expires_in, period, type}

  GET /api/reports?period=daily&type=admin&date=2026-04-27
    → 특정 일자 archive PDF signed URL 발급
    → 응답: 200 {url, filename, expires_in, period, type, date}

  GET /api/reports?period=daily&type=admin&action=list
    → 해당 (period, type) archive 목록 (signed URL 없음, 가벼움)
    → 응답: 200 {items: [{date, filename}, ...], period, type}

공통:
  - admin: Bearer JWT 필수 + profiles.is_admin=TRUE
  - public: Bearer JWT 필수 (일반 로그인 사용자)
  - 401 (no/invalid token) | 403 (admin only) | 404 (PDF 없음) | 500

period: daily | weekly | monthly | quarterly | semi | annual
type:   admin  | public

스토리지 경로:
  - latest alias  : verity_<period>_<type>.pdf  (bucket 루트)
  - dated archive : archive/<period>/<type>/<YYYY-MM-DD>.pdf
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

# YYYY-MM-DD 검증 (path traversal/주입 방지)
import re as _re
_DATE_RE = _re.compile(r"^\d{4}-\d{2}-\d{2}$")


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


def _create_signed_url(object_path: str, ttl_seconds: int) -> Tuple[Optional[str], Optional[int]]:
    """Supabase Storage signed URL 발급. service_role 키 필요.

    object_path 는 bucket 내부 경로 (예: 'verity_daily_admin.pdf' 또는
    'archive/daily/admin/2026-04-27.pdf').

    반환: (url, http_status). url 이 None 이면 status 로 분기.
    """
    if not SUPABASE_SERVICE_ROLE_KEY:
        _logger.error("SUPABASE_SERVICE_ROLE_KEY 미설정 — signed URL 발급 불가")
        return None, 500
    try:
        r = requests.post(
            f"{SUPABASE_URL}/storage/v1/object/sign/{BUCKET}/{object_path}",
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
        if signed_path.startswith("http"):
            return signed_path, 200
        return f"{SUPABASE_URL}{signed_path}", 200
    except (requests.RequestException, ValueError) as e:
        _logger.error("signed URL error: %s", e)
        return None, 500


def _list_archive(period: str, kind: str) -> Tuple[Optional[list], Optional[int]]:
    """archive/<period>/<kind>/ 하위 PDF 목록 → [{date, filename}].

    Supabase Storage list API: POST /storage/v1/object/list/<bucket>
    body: {"prefix": "archive/<period>/<kind>/", "limit": 1000, "sortBy": {"column": "name", "order": "desc"}}
    반환 row 의 'name' 은 prefix 기준 상대 경로 (예: '2026-04-27.pdf').
    """
    if not SUPABASE_SERVICE_ROLE_KEY:
        return None, 500
    prefix = f"archive/{period}/{kind}/"
    try:
        r = requests.post(
            f"{SUPABASE_URL}/storage/v1/object/list/{BUCKET}",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "prefix": prefix,
                "limit": 1000,
                "offset": 0,
                "sortBy": {"column": "name", "order": "desc"},
            },
            timeout=8,
        )
        if r.status_code != 200:
            _logger.warning("list failed: status=%s body=%s", r.status_code, r.text[:200])
            return None, 500
        rows = r.json() if r.text else []
        items = []
        for row in rows:
            name = row.get("name") or ""
            # YYYY-MM-DD.pdf 만 수용
            if not name.endswith(".pdf") or len(name) != 14:
                continue
            date_str = name[:-4]
            items.append({"date": date_str, "filename": name})
        return items, 200
    except (requests.RequestException, ValueError) as e:
        _logger.error("list error: %s", e)
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
            action = (qs.get("action", [""])[0] or "").strip().lower()
            date = (qs.get("date", [""])[0] or "").strip()

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

            # ── action=list: archive 목록 반환 ─────────────────
            if action == "list":
                items, status = _list_archive(period, kind)
                if items is None:
                    _json(self, 500, {"error": "list_failed"})
                    return
                _json(self, 200, {
                    "items": items,
                    "period": period,
                    "type": kind,
                })
                return

            # ── date 지정: archive 단일 PDF signed URL ─────────
            if date:
                if not _DATE_RE.match(date):
                    _json(self, 400, {"error": "invalid date (YYYY-MM-DD 필수)"})
                    return
                object_path = f"archive/{period}/{kind}/{date}.pdf"
                ttl = SIGNED_URL_TTL[kind]
                url, status = _create_signed_url(object_path, ttl)
                if status == 404:
                    _json(self, 404, {
                        "error": "report_not_found",
                        "message": f"{date} 자 리포트가 없습니다",
                        "filename": object_path,
                    })
                    return
                if not url:
                    _json(self, 500, {"error": "signed_url_failed"})
                    return
                _json(self, 200, {
                    "url": url,
                    "filename": object_path,
                    "expires_in": ttl,
                    "period": period,
                    "type": kind,
                    "date": date,
                })
                return

            # ── 기본: latest alias signed URL ─────────────────
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
