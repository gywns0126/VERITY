"""
User Thesis CRUD API — JWT 기반 인증 (holdings.py/watchgroups.py 패턴 복제).

사용자 본인 매매 논지(관점/메모/기록가) 저장/조회/삭제. user_thesis 테이블(018 migration,
RLS auth.uid()=user_id). 모든 요청 Authorization: Bearer <supabase_access_token> 필수.
서버가 /auth/v1/user 로 검증한 user_id 만 신뢰 — body user_id 무시(IDOR 방지). 키 = (user_id, ticker).

GET    /api/thesis                                          → 본인 전 thesis
POST   /api/thesis { ticker, market?, stance, note?, entry_price? }  → upsert(있으면 갱신)
DELETE /api/thesis { ticker }                              → 삭제

🚨 RULE 7 — 사용자 자기 저널(관점/메모/기록 시 가격). VERITY 채점·점수·추천 0. RULE 6 — LLM 0.
"""
from http.server import BaseHTTPRequestHandler
import json
import logging
import os
import time
import traceback
from collections import defaultdict
from typing import Optional

import api.supabase_client as sb

_rate_limit: dict = defaultdict(list)
_RATE_WINDOW = 60
_RATE_MAX = 80

_GLOBAL_CALL_LOG: list = []
_GLOBAL_MAX_PER_HOUR = int(os.environ.get("THESIS_GLOBAL_HOURLY_LIMIT", "10000"))

_logger = logging.getLogger(__name__)
_STANCES = {"bull", "watch", "bear"}


def _global_budget_ok() -> bool:
    now = time.time()
    _GLOBAL_CALL_LOG[:] = [t for t in _GLOBAL_CALL_LOG if now - t < 3600]
    if len(_GLOBAL_CALL_LOG) >= _GLOBAL_MAX_PER_HOUR:
        return False
    _GLOBAL_CALL_LOG.append(now)
    return True


def _safe_err(exc, public_msg: str = "Internal error") -> str:
    _logger.error("thesis error: %s\n%s", exc, traceback.format_exc())
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
    h.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
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
            rows = sb.select("user_thesis", {
                "user_id": f"eq.{user_id}",
                "order": "created_at.desc",
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
        stance = str(body.get("stance", "watch")).strip()
        if stance not in _STANCES:
            stance = "watch"

        payload = {
            "ticker": ticker,
            "market": str(body.get("market", "kr")),
            "stance": stance,
            "note": str(body.get("note", "")),
            "entry_price": _num(body.get("entry_price")),  # None 허용(기록 시 가격 미저장)
        }
        # 커뮤니티 공개 토글(020) — 키가 온 요청만 반영. 공개 전환 = 별명 필수(피드 표시명).
        # 별명 없으면 거부 대신 비공개로 저장 + 플래그 반환 (메모 유실 방지).
        is_public = None
        nickname_required = False
        if "is_public" in body:
            is_public = bool(body.get("is_public"))
            if is_public:
                try:
                    prof = sb.select("public_profiles", {
                        "id": f"eq.{user_id}", "select": "id", "limit": "1",
                    })
                    if not prof:
                        is_public = False
                        nickname_required = True
                except Exception:
                    pass  # 020 미적용 DB — view 부재. 아래 폴백에서 is_public 자체가 제거됨
            payload["is_public"] = is_public

        def _write(p):
            # upsert — 동일 (user_id, ticker) 있으면 갱신, 없으면 삽입
            existing = sb.select("user_thesis", {
                "user_id": f"eq.{user_id}", "ticker": f"eq.{ticker}",
                "select": "id", "limit": "1",
            }, user_jwt=jwt)
            if existing:
                rows = sb.update("user_thesis", {"id": existing[0]["id"], "user_id": user_id},
                                 p, user_jwt=jwt)
                return (rows[0] if rows else {}), 200
            row = sb.insert("user_thesis", {**p, "user_id": user_id}, user_jwt=jwt)  # 서버 검증 user_id 만
            return row, 201

        try:
            data, status = _write(payload)
            if nickname_required and isinstance(data, dict):
                data["nickname_required"] = True
            _json_response(self, data, status)
        except Exception as e:
            # 020 미적용 DB(is_public 컬럼 부재) 폴백 — 저널 저장은 무회귀
            if is_public is not None:
                try:
                    data, status = _write({k: v for k, v in payload.items() if k != "is_public"})
                    return _json_response(self, data, status)
                except Exception as e2:
                    return _json_response(self, {"error": _safe_err(e2, "DB 쓰기 실패")}, 500)
            _json_response(self, {"error": _safe_err(e, "DB 쓰기 실패")}, 500)

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
        ticker = str(body.get("ticker", "")).strip()
        if not ticker:
            return _json_response(self, {"error": "ticker 필요"}, 400)
        try:
            sb.delete("user_thesis", {"user_id": user_id, "ticker": ticker}, user_jwt=jwt)
            _json_response(self, {"ok": True})
        except Exception as e:
            _json_response(self, {"error": _safe_err(e, "DB 삭제 실패")}, 500)
