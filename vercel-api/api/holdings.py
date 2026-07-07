"""
User Holdings CRUD API — JWT 기반 인증 (watchgroups.py 패턴 복제).

방문자별 보유종목(평단·수량) 저장/조회/수정/삭제. user_holdings 테이블(003 migration,
RLS auth.uid()=user_id). 모든 요청 Authorization: Bearer <supabase_access_token> 필수.
서버가 /auth/v1/user 로 검증한 user_id 만 신뢰 — body user_id 무시(IDOR 방지).

GET    /api/holdings                                          → 본인 보유 목록
POST   /api/holdings { ticker, name?, market?, shares, avg_cost, memo? }  → 추가(있으면 갱신=upsert)
PATCH  /api/holdings { id, shares?, avg_cost?, memo?, name? } → 수정
DELETE /api/holdings { id }                                   → 삭제

🚨 RULE 7 — 저장은 사용자 입력(평단·수량) 사실. 평가손익은 프론트가 현재가 × 수량 단순 계산(사실).
   자체 점수·등급·추천 0. 매수·매도 권유 0.
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

_GLOBAL_CALL_LOG: list = []
_GLOBAL_MAX_PER_HOUR = int(os.environ.get("HOLDINGS_GLOBAL_HOURLY_LIMIT", "10000"))

_logger = logging.getLogger(__name__)


def _global_budget_ok() -> bool:
    now = time.time()
    _GLOBAL_CALL_LOG[:] = [t for t in _GLOBAL_CALL_LOG if now - t < 3600]
    if len(_GLOBAL_CALL_LOG) >= _GLOBAL_MAX_PER_HOUR:
        return False
    _GLOBAL_CALL_LOG.append(now)
    return True


def _safe_err(exc, public_msg: str = "Internal error") -> str:
    _logger.error("holdings error: %s\n%s", exc, traceback.format_exc())
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
    try:
        from api.cors_helper import resolve_origin  # type: ignore
    except Exception:
        resolve_origin = lambda _o: ""  # noqa: E731
    origin = resolve_origin(h.headers.get("Origin") or "")
    if origin:
        h.send_header("Access-Control-Allow-Origin", origin)
        h.send_header("Vary", "Origin")
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
        return auth[7:].strip() or None
    return None


def _authenticate(h) -> Optional[tuple]:
    jwt = _extract_jwt(h)
    if not jwt:
        _json_response(h, {"error": "Unauthorized"}, 401)
        return None
    uid = sb.verify_jwt(jwt)
    if not uid:
        _json_response(h, {"error": "Invalid token"}, 401)
        return None
    return uid, jwt


def _num(v, default=None):
    try:
        x = float(v)
        if x != x or x in (float("inf"), float("-inf")):
            return default
        return x
    except (TypeError, ValueError):
        return default


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
            rows = sb.select("user_holdings", {
                "user_id": f"eq.{user_id}",
                "order": "created_at.asc",
            }, user_jwt=jwt)
            _json_response(self, rows or [])
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
        ticker = str(body.get("ticker", "")).strip()
        if not ticker:
            return _json_response(self, {"error": "ticker 필요"}, 400)
        shares = _num(body.get("shares"), 0)
        avg_cost = _num(body.get("avg_cost"), 0)
        if shares is None or shares < 0 or avg_cost is None or avg_cost < 0:
            return _json_response(self, {"error": "shares·avg_cost 는 0 이상 숫자"}, 400)

        payload = {
            "ticker": ticker,
            "name": str(body.get("name", "")),
            "market": str(body.get("market", "kr")),
            "shares": shares,
            "avg_cost": avg_cost,
            "memo": str(body.get("memo", "")),
        }
        payload["user_id"] = user_id  # 서버 검증 user_id 만 (body user_id 무시 — IDOR 차단)
        try:
            # 원자적 upsert — (user_id, ticker) 충돌 시 갱신, 없으면 삽입.
            # check-then-insert 경쟁(동시 동일 키 → UNIQUE 위반 500) 제거. UNIQUE idx_uh_uniq 정합.
            row = sb.upsert("user_holdings", payload, "user_id,ticker", user_jwt=jwt)
            _json_response(self, row, 200)
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
        hid = str(body.get("id", "")).strip()
        if not hid:
            return _json_response(self, {"error": "id 필요"}, 400)

        updates = {}
        if "name" in body:
            updates["name"] = str(body["name"])
        if "memo" in body:
            updates["memo"] = str(body["memo"])
        if "shares" in body:
            v = _num(body["shares"])
            if v is None or v < 0:
                return _json_response(self, {"error": "shares 는 0 이상 숫자"}, 400)
            updates["shares"] = v
        if "avg_cost" in body:
            v = _num(body["avg_cost"])
            if v is None or v < 0:
                return _json_response(self, {"error": "avg_cost 는 0 이상 숫자"}, 400)
            updates["avg_cost"] = v
        if not updates:
            return _json_response(self, {"error": "변경할 필드 없음"}, 400)

        try:
            rows = sb.update("user_holdings", {"id": hid, "user_id": user_id}, updates, user_jwt=jwt)
            if not rows:
                return _json_response(self, {"error": "권한 없음 또는 항목 없음"}, 403)
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
        hid = str(body.get("id", "")).strip()
        if not hid:
            return _json_response(self, {"error": "id 필요"}, 400)
        try:
            sb.delete("user_holdings", {"id": hid, "user_id": user_id}, user_jwt=jwt)
            _json_response(self, {"ok": True})
        except Exception as e:
            _json_response(self, {"error": _safe_err(e, "DB 삭제 실패")}, 500)
