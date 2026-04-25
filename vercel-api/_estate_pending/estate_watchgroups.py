"""
Estate Watch Groups CRUD — JWT 기반 인증.

테이블: estate_groups, estate_group_members (migration 004 참조).

Authorization: Bearer <supabase_access_token> 필수.
서버는 Supabase /auth/v1/user 로 토큰 검증하고 검증된 user_id 만 신뢰.

GET    /api/estate/watchgroups                              → 본인 그룹+멤버 목록
POST   /api/estate/watchgroups  { name, color? }            → 그룹 생성
PATCH  /api/estate/watchgroups  { id, name?, color?, sort_order? } → 그룹 수정
DELETE /api/estate/watchgroups  { id }                      → 그룹 삭제

POST   /api/estate/watchgroups  { action:"add_member", group_id, gu, memo? }
DELETE /api/estate/watchgroups  { action:"remove_member", member_id }
"""
from http.server import BaseHTTPRequestHandler
import json
import logging
import os
import re
import time
import traceback
from collections import defaultdict
from typing import Optional
from urllib.parse import parse_qs, urlparse

import requests

import api.supabase_client as sb
from api.cors_helper import resolve_origin

_logger = logging.getLogger(__name__)

# 25구 검증 — 다른 지역은 거부
SEOUL_25 = frozenset([
    "강남구", "서초구", "송파구", "강동구", "마포구",
    "용산구", "성동구", "광진구", "중구", "종로구",
    "서대문구", "은평구", "강서구", "양천구", "영등포구",
    "구로구", "금천구", "관악구", "동작구", "성북구",
    "동대문구", "중랑구", "노원구", "도봉구", "강북구",
])

_rate_limit: dict = defaultdict(list)
_RATE_WINDOW = 60
_RATE_MAX = 80


def _safe_err(exc, public_msg: str = "Internal error") -> str:
    _logger.error("estate_watchgroups: %s\n%s", exc, traceback.format_exc())
    return public_msg


def _client_ip(h) -> str:
    xfwd = h.headers.get("x-forwarded-for", "")
    if xfwd:
        return xfwd.split(",")[0].strip()
    return (h.client_address[0] if h.client_address else "unknown") or "unknown"


def _rate_ok(ip: str) -> bool:
    now = time.time()
    bucket = _rate_limit[ip]
    bucket[:] = [t for t in bucket if now - t < _RATE_WINDOW]
    if len(bucket) >= _RATE_MAX:
        return False
    bucket.append(now)
    return True


def _verify_jwt(auth_header: str) -> Optional[str]:
    """Supabase /auth/v1/user 로 토큰 검증 → user_id 반환. 실패 시 None."""
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:].strip()
    if not token or len(token) > 4096:
        return None
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    anon = os.environ.get("SUPABASE_ANON_KEY", "")
    if not base or not anon:
        return None
    try:
        r = requests.get(
            f"{base}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": anon},
            timeout=5,
        )
        if r.status_code != 200:
            return None
        return r.json().get("id")
    except Exception as e:
        _logger.warning("jwt verify failed: %s", e)
        return None


class handler(BaseHTTPRequestHandler):
    def _set_cors(self):
        origin = resolve_origin(self.headers.get("Origin", ""))
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors()
        self.end_headers()

    def _json(self, status: int, payload: dict):
        self.send_response(status)
        self._set_cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def _err(self, status: int, code: str, message: str):
        self._json(status, {"error": code, "message": message})

    def _auth_or_reject(self) -> Optional[str]:
        ip = _client_ip(self)
        if not _rate_ok(ip):
            self._err(429, "rate_limit", "Too many requests")
            return None
        user_id = _verify_jwt(self.headers.get("Authorization", ""))
        if not user_id:
            self._err(401, "unauthorized", "Valid Supabase access token required")
            return None
        return user_id

    def _read_body(self) -> Optional[dict]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 65536:
                return None
            raw = self.rfile.read(length)
            return json.loads(raw)
        except Exception:
            return None

    # ──────────────────────────────────────────────────────────
    # GET — 그룹 + 멤버 조회
    # ──────────────────────────────────────────────────────────
    def do_GET(self):
        user_id = self._auth_or_reject()
        if not user_id:
            return
        token = self.headers.get("Authorization", "")[7:]
        try:
            groups = sb.select("estate_groups", {
                "user_id": f"eq.{user_id}",
                "select": "id,name,color,sort_order,created_at,updated_at",
                "order": "sort_order.asc,created_at.asc",
            }, user_jwt=token) or []

            group_ids = [g["id"] for g in groups]
            members = []
            if group_ids:
                members = sb.select("estate_group_members", {
                    "group_id": f"in.({','.join(group_ids)})",
                    "select": "id,group_id,gu,memo,sort_order,created_at",
                    "order": "sort_order.asc,created_at.asc",
                }, user_jwt=token) or []

            members_by_group = defaultdict(list)
            for m in members:
                members_by_group[m["group_id"]].append(m)
            for g in groups:
                g["members"] = members_by_group.get(g["id"], [])

            self._json(200, {"groups": groups})
        except Exception as e:
            self._err(500, "fetch_failed", _safe_err(e))

    # ──────────────────────────────────────────────────────────
    # POST — 그룹 생성 OR 멤버 추가 (action 분기)
    # ──────────────────────────────────────────────────────────
    def do_POST(self):
        user_id = self._auth_or_reject()
        if not user_id:
            return
        token = self.headers.get("Authorization", "")[7:]
        body = self._read_body()
        if body is None:
            self._err(400, "invalid_body", "JSON body required")
            return
        action = body.get("action")
        try:
            if action == "add_member":
                group_id = body.get("group_id")
                gu = (body.get("gu") or "").strip()
                memo = (body.get("memo") or "").strip()[:200]
                if not group_id or gu not in SEOUL_25:
                    self._err(400, "invalid_input", "group_id + gu(서울 25구) 필수")
                    return
                # 소유권 확인
                owner = sb.select("estate_groups", {
                    "id": f"eq.{group_id}", "user_id": f"eq.{user_id}",
                    "select": "id", "limit": "1",
                }, user_jwt=token)
                if not owner:
                    self._err(403, "not_owner", "Group not owned by user")
                    return
                row = sb.insert("estate_group_members", {
                    "group_id": group_id, "gu": gu, "memo": memo,
                }, user_jwt=token)
                self._json(200, {"member": row})
                return

            # 기본: 그룹 생성
            name = (body.get("name") or "관심지역").strip()[:60]
            color = (body.get("color") or "#B8864D").strip()
            if not re.match(r"^#[0-9A-Fa-f]{6}$", color):
                color = "#B8864D"
            row = sb.insert("estate_groups", {
                "user_id": user_id, "name": name, "color": color,
            }, user_jwt=token)
            self._json(200, {"group": row})
        except Exception as e:
            self._err(500, "insert_failed", _safe_err(e))

    # ──────────────────────────────────────────────────────────
    # PATCH — 그룹 수정
    # ──────────────────────────────────────────────────────────
    def do_PATCH(self):
        user_id = self._auth_or_reject()
        if not user_id:
            return
        token = self.headers.get("Authorization", "")[7:]
        body = self._read_body()
        if body is None or not body.get("id"):
            self._err(400, "invalid_body", "id required")
            return
        patch = {}
        if "name" in body:
            patch["name"] = (body["name"] or "").strip()[:60] or "관심지역"
        if "color" in body:
            color = (body["color"] or "").strip()
            if re.match(r"^#[0-9A-Fa-f]{6}$", color):
                patch["color"] = color
        if "sort_order" in body and isinstance(body["sort_order"], int):
            patch["sort_order"] = body["sort_order"]
        patch["updated_at"] = "now()"
        try:
            row = sb.update("estate_groups", {
                "id": f"eq.{body['id']}", "user_id": f"eq.{user_id}",
            }, patch, user_jwt=token)
            self._json(200, {"group": row})
        except Exception as e:
            self._err(500, "update_failed", _safe_err(e))

    # ──────────────────────────────────────────────────────────
    # DELETE — 그룹 OR 멤버 삭제
    # ──────────────────────────────────────────────────────────
    def do_DELETE(self):
        user_id = self._auth_or_reject()
        if not user_id:
            return
        token = self.headers.get("Authorization", "")[7:]
        body = self._read_body() or {}
        action = body.get("action")
        try:
            if action == "remove_member":
                member_id = body.get("member_id")
                if not member_id:
                    self._err(400, "invalid_body", "member_id required")
                    return
                # 멤버 조회 → 소유권 확인 → 삭제
                m_rows = sb.select("estate_group_members", {
                    "id": f"eq.{member_id}", "select": "id,group_id", "limit": "1",
                }, user_jwt=token)
                if not m_rows:
                    self._err(404, "not_found", "Member not found")
                    return
                owner = sb.select("estate_groups", {
                    "id": f"eq.{m_rows[0]['group_id']}", "user_id": f"eq.{user_id}",
                    "select": "id", "limit": "1",
                }, user_jwt=token)
                if not owner:
                    self._err(403, "not_owner", "Member not owned by user")
                    return
                sb.delete("estate_group_members", {"id": f"eq.{member_id}"}, user_jwt=token)
                self._json(200, {"ok": True})
                return

            # 기본: 그룹 삭제
            group_id = body.get("id")
            if not group_id:
                self._err(400, "invalid_body", "id required")
                return
            sb.delete("estate_groups", {
                "id": f"eq.{group_id}", "user_id": f"eq.{user_id}",
            }, user_jwt=token)
            self._json(200, {"ok": True})
        except Exception as e:
            self._err(500, "delete_failed", _safe_err(e))
