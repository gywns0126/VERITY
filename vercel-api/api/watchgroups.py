"""
Watch Groups CRUD API.

GET    /api/watchgroups?user_id=xxx                    → 그룹 + 아이템 목록
POST   /api/watchgroups  { user_id, name, color, icon } → 그룹 생성
PATCH  /api/watchgroups  { id, name?, color?, icon?, sort_order? } → 그룹 수정
DELETE /api/watchgroups  { id }                         → 그룹 삭제

POST   /api/watchgroups  { action:"add_item", group_id, ticker, name, market, memo }
DELETE /api/watchgroups  { action:"remove_item", item_id }
"""
from http.server import BaseHTTPRequestHandler
import json
import time
from collections import defaultdict
from urllib.parse import parse_qs, urlparse

import api.supabase_client as sb

_rate_limit: dict = defaultdict(list)
_RATE_WINDOW = 60
_RATE_MAX = 80


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
    h.send_header("Access-Control-Allow-Headers", "Content-Type")


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
    return json.loads(raw.decode("utf-8"))


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        _cors_headers(self)
        self.end_headers()

    def do_GET(self):
        if not _check_rate(_client_ip(self)):
            return _json_response(self, {"error": "요청이 너무 많습니다"}, 429)
        if not sb.is_configured():
            return _json_response(self, [])

        params = parse_qs(urlparse(self.path).query)
        user_id = params.get("user_id", [""])[0].strip()
        if not user_id:
            return _json_response(self, {"error": "user_id 필요"}, 400)

        try:
            groups = sb.select("watch_groups", {
                "user_id": f"eq.{user_id}",
                "order": "sort_order.asc,created_at.asc",
            }, user_id=user_id)
            group_ids = [g["id"] for g in groups]
            items = []
            if group_ids:
                items = sb.select("watch_group_items", {
                    "group_id": f"in.({','.join(group_ids)})",
                    "order": "sort_order.asc,created_at.asc",
                }, user_id=user_id)

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
            _json_response(self, {"error": str(e)[:200]}, 500)

    def do_POST(self):
        if not _check_rate(_client_ip(self)):
            return _json_response(self, {"error": "요청이 너무 많습니다"}, 429)
        if not sb.is_configured():
            return _json_response(self, {"error": "Supabase 미설정"}, 503)

        body = _read_body(self)
        action = body.get("action", "create_group")
        user_id = body.get("user_id", "").strip()

        try:
            if action == "add_item":
                group_id = body.get("group_id", "").strip()
                ticker = body.get("ticker", "").strip()
                if not user_id or not group_id or not ticker:
                    return _json_response(self, {"error": "user_id, group_id, ticker 필요"}, 400)
                owner = sb.select(
                    "watch_groups",
                    {"id": f"eq.{group_id}", "user_id": f"eq.{user_id}", "select": "id", "limit": "1"},
                    user_id=user_id,
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
                }, user_id=user_id)
                return _json_response(self, row, 201)

            if not user_id:
                return _json_response(self, {"error": "user_id 필요"}, 400)

            row = sb.insert("watch_groups", {
                "user_id": user_id,
                "name": body.get("name", "관심종목"),
                "color": body.get("color", "#B5FF19"),
                "icon": body.get("icon", "⭐"),
                "sort_order": body.get("sort_order", 0),
            }, user_id=user_id)
            _json_response(self, row, 201)
        except Exception as e:
            _json_response(self, {"error": str(e)[:200]}, 500)

    def do_PATCH(self):
        if not _check_rate(_client_ip(self)):
            return _json_response(self, {"error": "요청이 너무 많습니다"}, 429)
        if not sb.is_configured():
            return _json_response(self, {"error": "Supabase 미설정"}, 503)

        body = _read_body(self)
        user_id = body.get("user_id", "").strip()
        gid = body.get("id", "").strip()
        if not user_id or not gid:
            return _json_response(self, {"error": "user_id, id 필요"}, 400)

        updates = {}
        for key in ("name", "color", "icon", "sort_order"):
            if key in body:
                updates[key] = body[key]

        if not updates:
            return _json_response(self, {"error": "변경할 필드 없음"}, 400)

        try:
            rows = sb.update("watch_groups", {"id": gid, "user_id": user_id}, updates, user_id=user_id)
            if not rows:
                return _json_response(self, {"error": "권한 없음 또는 그룹 없음"}, 403)
            _json_response(self, rows[0] if rows else {})
        except Exception as e:
            _json_response(self, {"error": str(e)[:200]}, 500)

    def do_DELETE(self):
        if not _check_rate(_client_ip(self)):
            return _json_response(self, {"error": "요청이 너무 많습니다"}, 429)
        if not sb.is_configured():
            return _json_response(self, {"error": "Supabase 미설정"}, 503)

        body = _read_body(self)
        action = body.get("action", "delete_group")
        user_id = body.get("user_id", "").strip()
        if not user_id:
            return _json_response(self, {"error": "user_id 필요"}, 400)

        try:
            if action == "remove_item":
                item_id = body.get("item_id", "").strip()
                if not item_id:
                    return _json_response(self, {"error": "item_id 필요"}, 400)
                items = sb.select(
                    "watch_group_items",
                    {"id": f"eq.{item_id}", "select": "id,group_id", "limit": "1"},
                    user_id=user_id,
                )
                if not items:
                    return _json_response(self, {"error": "아이템 없음"}, 404)
                owner = sb.select(
                    "watch_groups",
                    {"id": f"eq.{items[0]['group_id']}", "user_id": f"eq.{user_id}", "select": "id", "limit": "1"},
                    user_id=user_id,
                )
                if not owner:
                    return _json_response(self, {"error": "권한 없음"}, 403)
                sb.delete("watch_group_items", {"id": item_id}, user_id=user_id)
                return _json_response(self, {"ok": True})

            gid = body.get("id", "").strip()
            if not gid:
                return _json_response(self, {"error": "id 필요"}, 400)
            sb.delete("watch_groups", {"id": gid, "user_id": user_id}, user_id=user_id)
            _json_response(self, {"ok": True})
        except Exception as e:
            _json_response(self, {"error": str(e)[:200]}, 500)
