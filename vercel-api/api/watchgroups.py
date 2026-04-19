"""
Watch Groups CRUD API — JWT 기반 인증.

모든 요청은 Authorization: Bearer <supabase_access_token> 헤더 필수.
서버는 Supabase /auth/v1/user로 토큰을 검증하고 검증된 user_id만 신뢰한다.
body/query의 user_id는 무시된다(IDOR 방지).

GET    /api/watchgroups                                 → 본인 그룹 + 아이템 목록
POST   /api/watchgroups  { name, color, icon }           → 그룹 생성
PATCH  /api/watchgroups  { id, name?, color?, icon?, sort_order? } → 그룹 수정
DELETE /api/watchgroups  { id }                          → 그룹 삭제

POST   /api/watchgroups  { action:"add_item", group_id, ticker, name, market, memo }
DELETE /api/watchgroups  { action:"remove_item", item_id }
"""
from http.server import BaseHTTPRequestHandler
import json
import logging
import os
import time
import traceback
from collections import defaultdict
from typing import Optional
from urllib.parse import parse_qs, urlparse

import api.supabase_client as sb

_rate_limit: dict = defaultdict(list)
_RATE_WINDOW = 60
_RATE_MAX = 80

# 서버리스 인스턴스 분산을 고려한 전역 시간당 상한 (악성 루프 1차 방어).
# 인스턴스별 캡이라 완벽하지 않지만 단일 인스턴스의 폭주를 차단한다.
_GLOBAL_CALL_LOG: list = []
_GLOBAL_MAX_PER_HOUR = int(os.environ.get("WATCHGROUPS_GLOBAL_HOURLY_LIMIT", "10000"))


def _global_budget_ok() -> bool:
    now = time.time()
    _GLOBAL_CALL_LOG[:] = [t for t in _GLOBAL_CALL_LOG if now - t < 3600]
    if len(_GLOBAL_CALL_LOG) >= _GLOBAL_MAX_PER_HOUR:
        return False
    _GLOBAL_CALL_LOG.append(now)
    return True

_logger = logging.getLogger(__name__)


def _safe_err(exc, public_msg: str = "Internal error") -> str:
    _logger.error("watchgroups error: %s\n%s", exc, traceback.format_exc())
    return public_msg


def _client_ip(h) -> str:
    xfwd = h.headers.get("x-forwarded-for", "")
    if xfwd:
        return xfwd.split(",")[0].strip()
    return (h.client_address[0] if h.client_address else "unknown") or "unknown"


def _check_rate(ip: str) -> bool:
    now = time.time()
    _rate_limit[ip] = [t for t in _rate_limit[ip] if now - t < _RATE_WINDOW]
    if len(_rate_limit[ip]) >= _RATE_MAX:
        return False
    _rate_limit[ip].append(now)
    return True


def _cors_headers(h):
    h.send_header("Access-Control-Allow-Origin", "*")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")


def _json_response(h, data, status=200):
    h.send_response(status)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    _cors_headers(h)
    h.end_headers()
    h.wfile.write(json.dumps(data, ensure_ascii=False).encode())


def _read_body(h) -> dict:
    length = int(h.headers.get("Content-Length", 0) or 0)
    if length == 0:
        return {}
    raw = h.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def _extract_jwt(h) -> Optional[str]:
    auth = (h.headers.get("Authorization") or "").strip()
    if auth.startswith("Bearer "):
        tok = auth[7:].strip()
        return tok or None
    return None


def _authenticate(h) -> Optional[tuple]:
    """요청을 검증하고 (user_id, jwt) 튜플을 반환. 실패 시 401 응답 후 None."""
    jwt = _extract_jwt(h)
    if not jwt:
        _json_response(h, {"error": "Unauthorized"}, 401)
        return None
    uid = sb.verify_jwt(jwt)
    if not uid:
        _json_response(h, {"error": "Invalid token"}, 401)
        return None
    return uid, jwt


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        _cors_headers(self)
        self.end_headers()

    def do_GET(self):
        if not _global_budget_ok():
            return _json_response(self, {"error": "서비스 혼잡 - 잠시 후 재시도"}, 429)
        if not _check_rate(_client_ip(self)):
            return _json_response(self, {"error": "요청이 너무 많습니다"}, 429)
        if not sb.is_configured():
            return _json_response(self, [])

        auth = _authenticate(self)
        if not auth:
            return
        user_id, jwt = auth

        try:
            # RLS가 auth.uid()로 자동 필터 — 명시적 user_id eq 불필요하지만
            # 2차 방어선 겸 order/limit 지정
            groups = sb.select("watch_groups", {
                "user_id": f"eq.{user_id}",
                "order": "sort_order.asc,created_at.asc",
            }, user_jwt=jwt)
            group_ids = [g["id"] for g in groups]
            items = []
            if group_ids:
                items = sb.select("watch_group_items", {
                    "group_id": f"in.({','.join(group_ids)})",
                    "order": "sort_order.asc,created_at.asc",
                }, user_jwt=jwt)

            items_by_group = {}
            for it in items:
                gid = it["group_id"]
                items_by_group.setdefault(gid, []).append(it)

            result = []
            for g in groups:
                g["items"] = items_by_group.get(g["id"], [])
                result.append(g)

            _json_response(self, result)
        except Exception as e:
            _json_response(self, {"error": _safe_err(e, "DB 조회 실패")}, 500)

    def do_POST(self):
        if not _global_budget_ok():
            return _json_response(self, {"error": "서비스 혼잡 - 잠시 후 재시도"}, 429)
        if not _check_rate(_client_ip(self)):
            return _json_response(self, {"error": "요청이 너무 많습니다"}, 429)
        if not sb.is_configured():
            return _json_response(self, {"error": "Supabase 미설정"}, 503)

        auth = _authenticate(self)
        if not auth:
            return
        user_id, jwt = auth

        body = _read_body(self)
        action = body.get("action", "create_group")

        try:
            if action == "add_item":
                group_id = str(body.get("group_id", "")).strip()
                ticker = str(body.get("ticker", "")).strip()
                if not group_id or not ticker:
                    return _json_response(self, {"error": "group_id, ticker 필요"}, 400)
                # 소유 그룹 확인 (RLS가 막아주지만 명시적 검증으로 403 반환)
                owner = sb.select(
                    "watch_groups",
                    {"id": f"eq.{group_id}", "user_id": f"eq.{user_id}", "select": "id", "limit": "1"},
                    user_jwt=jwt,
                )
                if not owner:
                    return _json_response(self, {"error": "권한 없음 또는 그룹 없음"}, 403)
                row = sb.insert("watch_group_items", {
                    "group_id": group_id,
                    "ticker": ticker,
                    "name": body.get("name", ""),
                    "market": body.get("market", "kr"),
                    "memo": body.get("memo", ""),
                    "sort_order": body.get("sort_order", 0),
                }, user_jwt=jwt)
                return _json_response(self, row, 201)

            row = sb.insert("watch_groups", {
                "user_id": user_id,  # 서버가 검증한 user_id만 사용
                "name": body.get("name", "관심종목"),
                "color": body.get("color", "#B5FF19"),
                "icon": body.get("icon", "⭐"),
                "sort_order": body.get("sort_order", 0),
            }, user_jwt=jwt)
            _json_response(self, row, 201)
        except Exception as e:
            _json_response(self, {"error": _safe_err(e, "DB 쓰기 실패")}, 500)

    def do_PATCH(self):
        if not _global_budget_ok():
            return _json_response(self, {"error": "서비스 혼잡 - 잠시 후 재시도"}, 429)
        if not _check_rate(_client_ip(self)):
            return _json_response(self, {"error": "요청이 너무 많습니다"}, 429)
        if not sb.is_configured():
            return _json_response(self, {"error": "Supabase 미설정"}, 503)

        auth = _authenticate(self)
        if not auth:
            return
        user_id, jwt = auth

        body = _read_body(self)
        gid = str(body.get("id", "")).strip()
        if not gid:
            return _json_response(self, {"error": "id 필요"}, 400)

        updates = {}
        for key in ("name", "color", "icon", "sort_order"):
            if key in body:
                updates[key] = body[key]

        if not updates:
            return _json_response(self, {"error": "변경할 필드 없음"}, 400)

        try:
            rows = sb.update(
                "watch_groups",
                {"id": gid, "user_id": user_id},
                updates,
                user_jwt=jwt,
            )
            if not rows:
                return _json_response(self, {"error": "권한 없음 또는 그룹 없음"}, 403)
            _json_response(self, rows[0] if rows else {})
        except Exception as e:
            _json_response(self, {"error": _safe_err(e, "DB 업데이트 실패")}, 500)

    def do_DELETE(self):
        if not _global_budget_ok():
            return _json_response(self, {"error": "서비스 혼잡 - 잠시 후 재시도"}, 429)
        if not _check_rate(_client_ip(self)):
            return _json_response(self, {"error": "요청이 너무 많습니다"}, 429)
        if not sb.is_configured():
            return _json_response(self, {"error": "Supabase 미설정"}, 503)

        auth = _authenticate(self)
        if not auth:
            return
        user_id, jwt = auth

        body = _read_body(self)
        action = body.get("action", "delete_group")

        try:
            if action == "remove_item":
                item_id = str(body.get("item_id", "")).strip()
                if not item_id:
                    return _json_response(self, {"error": "item_id 필요"}, 400)
                items = sb.select(
                    "watch_group_items",
                    {"id": f"eq.{item_id}", "select": "id,group_id", "limit": "1"},
                    user_jwt=jwt,
                )
                if not items:
                    return _json_response(self, {"error": "아이템 없음"}, 404)
                owner = sb.select(
                    "watch_groups",
                    {"id": f"eq.{items[0]['group_id']}", "user_id": f"eq.{user_id}", "select": "id", "limit": "1"},
                    user_jwt=jwt,
                )
                if not owner:
                    return _json_response(self, {"error": "권한 없음"}, 403)
                sb.delete("watch_group_items", {"id": item_id}, user_jwt=jwt)
                return _json_response(self, {"ok": True})

            gid = str(body.get("id", "")).strip()
            if not gid:
                return _json_response(self, {"error": "id 필요"}, 400)
            sb.delete("watch_groups", {"id": gid, "user_id": user_id}, user_jwt=jwt)
            _json_response(self, {"ok": True})
        except Exception as e:
            _json_response(self, {"error": _safe_err(e, "DB 삭제 실패")}, 500)
