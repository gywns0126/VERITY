"""
VERITY 주문 API — Railway 프록시 (Supabase JWT 인증 기반).

POST /api/order → Railway /api/order (주문)
GET  /api/order → Railway /api/order (잔고)

인증:
  - Authorization: Bearer <supabase_access_token> 헤더 필수.
  - 서버는 Supabase /auth/v1/user로 토큰을 검증하고 profiles.order_enabled=true
    인 사용자만 허용한다. 클라이언트에 공유 비밀을 노출하지 않는다.
  - Railway에는 환경변수 RAILWAY_SHARED_SECRET을 별도로 두고 서버 간 신뢰만 부여
    (Vercel→Railway 구간). 클라이언트는 이 값을 볼 수 없다.

주문 검증:
  - 입력 필드 화이트리스트 + 수량/가격 상한 검증
  - 30초 내 동일 주문 중복 차단
  - 사용자별 일일 주문 횟수 상한
"""
from http.server import BaseHTTPRequestHandler
import json
import logging
import os
import time
import traceback
from datetime import datetime, timezone
from typing import Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests

import api.supabase_client as sb

_logger = logging.getLogger(__name__)

_RAILWAY_URL = (
    os.environ.get("RAILWAY_URL", "https://verity-production-1e44.up.railway.app")
    .strip().strip('"').rstrip("/")
)

# Vercel ↔ Railway 서버 간 공유 비밀 (클라이언트 미노출).
# Railway 측에서 X-Service-Auth 헤더를 검증하도록 설정한다.
_RAILWAY_SHARED_SECRET = (os.environ.get("RAILWAY_SHARED_SECRET") or "").strip()

_CORS_HEADERS = ("Content-Type", "Authorization")

# 환경변수 ORDER_ALLOWED_ORIGINS: 쉼표 구분 허용 Origin 목록 (예: "https://verity.ai,https://kim-hyojun.github.io")
# 비어 있으면 폴백: 프레이머 프리뷰 허용을 위해 * (단 CRIT-5에서 access_token 요구하므로 실질적 위험은 낮음)
_ALLOWED_ORIGINS = frozenset(
    o.strip() for o in (os.environ.get("ORDER_ALLOWED_ORIGINS", "") or "").split(",")
    if o.strip()
)


def _resolve_origin(request_origin: str) -> str:
    request_origin = (request_origin or "").strip()
    if not _ALLOWED_ORIGINS:
        # 허용 목록 미설정 시 와일드카드로 폴백 (운영 환경에서는 반드시 ORDER_ALLOWED_ORIGINS 설정 권고)
        return "*"
    return request_origin if request_origin in _ALLOWED_ORIGINS else ""

# ── 주문 검증 파라미터 ────────────────────────────────────────
_ALLOWED_SIDES = frozenset({"BUY", "SELL", "01", "02"})
_ALLOWED_ORDER_TYPES = frozenset({"00", "01"})  # 지정가 / 시장가
_ALLOWED_MARKETS = frozenset({"kr", "us"})
_MAX_QTY = int(os.environ.get("ORDER_MAX_QTY", "10000"))
_MAX_PRICE_KRW = int(os.environ.get("ORDER_MAX_PRICE_KRW", "100000000"))
_MAX_ORDER_VALUE_KRW_DEFAULT = int(os.environ.get("ORDER_MAX_VALUE_KRW", "10000000"))
_DAILY_COUNT_LIMIT_DEFAULT = int(os.environ.get("ORDER_DAILY_COUNT_LIMIT", "50"))

# 인메모리 중복 방지 (서버리스 한계로 인스턴스별 상태 — 완전 중복 차단은 아님).
# 실 배포에는 Upstash/Redis 권장.
_ORDER_DEDUPE: dict = {}
_ORDER_DEDUPE_TTL = 30
_DAILY_ORDER_COUNT: dict = {}


def _safe_err(exc, public_msg: str = "Internal error") -> str:
    _logger.error("order api error: %s\n%s", exc, traceback.format_exc())
    return public_msg


def _prune_dedupe(now: float) -> None:
    if len(_ORDER_DEDUPE) <= 1000:
        return
    cutoff = now - _ORDER_DEDUPE_TTL
    for k, t in list(_ORDER_DEDUPE.items()):
        if t < cutoff:
            _ORDER_DEDUPE.pop(k, None)


class handler(BaseHTTPRequestHandler):
    def _order_limits_for(self, user_id: str, jwt: str) -> dict:
        """profiles 테이블에서 사용자별 주문 권한/한도 조회. 실패 시 기본값."""
        defaults = {
            "order_enabled": False,
            "max_order_krw": _MAX_ORDER_VALUE_KRW_DEFAULT,
            "daily_order_count_limit": _DAILY_COUNT_LIMIT_DEFAULT,
        }
        try:
            rows = sb.select(
                "profiles",
                {
                    "id": f"eq.{user_id}",
                    "select": "order_enabled,max_order_krw,daily_order_count_limit",
                    "limit": "1",
                },
                user_jwt=jwt,
            )
            if not rows:
                return defaults
            row = rows[0]
            return {
                "order_enabled": bool(row.get("order_enabled")),
                "max_order_krw": int(row.get("max_order_krw") or defaults["max_order_krw"]),
                "daily_order_count_limit": int(
                    row.get("daily_order_count_limit") or defaults["daily_order_count_limit"]
                ),
            }
        except Exception as e:
            _logger.warning("order limits lookup failed: %s", e)
            return defaults

    def _authorized_user(self) -> Optional[dict]:
        """Supabase access_token 검증 + 주문 권한 확인. 실패 시 401/403 응답."""
        auth = (self.headers.get("Authorization") or "").strip()
        if not auth.startswith("Bearer "):
            self._json(401, {"error": "Unauthorized"})
            return None
        jwt = auth[7:].strip()
        if not jwt:
            self._json(401, {"error": "Unauthorized"})
            return None
        uid = sb.verify_jwt(jwt)
        if not uid:
            self._json(401, {"error": "Invalid token"})
            return None
        limits = self._order_limits_for(uid, jwt)
        if not limits.get("order_enabled"):
            self._json(403, {"error": "Order not permitted for this account"})
            return None
        return {"user_id": uid, "jwt": jwt, "limits": limits}

    def _proxy_headers(self, user: dict) -> dict:
        """Railway에 전달할 헤더. 클라이언트의 Authorization은 전달하지 않는다."""
        out = {"Content-Type": "application/json"}
        # 서버 간 공유 비밀 (Railway가 검증)
        if _RAILWAY_SHARED_SECRET:
            out["X-Service-Auth"] = _RAILWAY_SHARED_SECRET
        # Railway가 사용자별 로깅/권한을 하도록 검증된 UID를 헤더로 전달
        out["X-Verity-User-Id"] = user["user_id"]
        return out

    def _validate_order(self, body: dict, limits: dict) -> Tuple[bool, str, Optional[dict]]:
        if not isinstance(body, dict):
            return False, "invalid body", None
        ticker = str(body.get("ticker", "")).strip()
        side = str(body.get("side", "")).strip().upper()
        order_type = str(body.get("order_type", "")).strip()
        market = str(body.get("market", "kr")).strip().lower()

        if not ticker or not ticker.isalnum() or len(ticker) > 10:
            return False, "invalid ticker", None
        if side not in _ALLOWED_SIDES:
            return False, "invalid side (BUY/SELL/01/02)", None
        if order_type not in _ALLOWED_ORDER_TYPES:
            return False, "invalid order_type (00=limit, 01=market)", None
        if market not in _ALLOWED_MARKETS:
            return False, "invalid market (kr/us)", None

        try:
            qty = int(body.get("qty", 0))
            price = int(body.get("price", 0))
        except (TypeError, ValueError):
            return False, "qty/price must be integer", None

        if qty <= 0 or qty > _MAX_QTY:
            return False, f"qty out of range (1~{_MAX_QTY})", None
        if order_type == "00":
            if price <= 0 or price > _MAX_PRICE_KRW:
                return False, "price out of range for limit order", None
        # 시장가는 price=0 허용

        order_value = qty * max(price, 1)
        max_per_order = int(limits.get("max_order_krw", _MAX_ORDER_VALUE_KRW_DEFAULT))
        if order_value > max_per_order:
            return False, f"order value exceeds per-order limit ({max_per_order:,} KRW)", None

        normalized = {
            "ticker": ticker,
            "side": side,
            "qty": qty,
            "price": price,
            "order_type": order_type,
            "market": market,
        }
        return True, "", normalized

    # ── HTTP ─────────────────────────────────────────────
    def _write_cors(self):
        origin = _resolve_origin(self.headers.get("Origin") or "")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            if origin != "*":
                self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", ", ".join(_CORS_HEADERS))

    def do_OPTIONS(self):
        self.send_response(204)
        self._write_cors()
        self.end_headers()

    def do_GET(self):
        """잔고 조회 프록시."""
        user = self._authorized_user()
        if not user:
            return
        qs = parse_qs(urlparse(self.path).query)
        market_raw = (qs.get("market", ["kr"])[0]).strip().lower()
        market = market_raw if market_raw in _ALLOWED_MARKETS else "kr"
        try:
            r = requests.get(
                f"{_RAILWAY_URL}/api/order",
                params={"market": market},
                headers=self._proxy_headers(user),
                timeout=12,
            )
            try:
                payload = r.json()
            except Exception:
                payload = {"error": "upstream returned non-JSON"}
            self._json(r.status_code, payload)
        except Exception as e:
            self._json(502, {"error": _safe_err(e, "프록시 호출 실패")})

    def do_POST(self):
        """주문 프록시."""
        user = self._authorized_user()
        if not user:
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            body = json.loads(raw.decode("utf-8"))
        except Exception:
            self._json(400, {"error": "invalid JSON body"})
            return

        ok, msg, normalized = self._validate_order(body, user["limits"])
        if not ok or normalized is None:
            self._json(400, {"error": msg})
            return

        now = time.time()
        dedupe_key = (
            f"{user['user_id']}:{normalized['ticker']}:{normalized['side']}:"
            f"{normalized['qty']}:{normalized['price']}:{normalized['order_type']}"
        )
        last = _ORDER_DEDUPE.get(dedupe_key, 0)
        if now - last < _ORDER_DEDUPE_TTL:
            self._json(429, {"error": "duplicate order within 30s"})
            return
        _ORDER_DEDUPE[dedupe_key] = now
        _prune_dedupe(now)

        day_key = f"{user['user_id']}:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        cnt = _DAILY_ORDER_COUNT.get(day_key, 0)
        daily_limit = int(user["limits"].get("daily_order_count_limit", _DAILY_COUNT_LIMIT_DEFAULT))
        if cnt >= daily_limit:
            self._json(429, {"error": "daily order count exceeded"})
            return
        _DAILY_ORDER_COUNT[day_key] = cnt + 1

        try:
            r = requests.post(
                f"{_RAILWAY_URL}/api/order",
                json=normalized,
                headers=self._proxy_headers(user),
                timeout=12,
            )
            try:
                payload = r.json()
            except Exception:
                payload = {"success": False, "message": "upstream returned non-JSON"}
            self._json(r.status_code, payload)
        except Exception as e:
            self._json(502, {"success": False, "message": _safe_err(e, "프록시 호출 실패")})

    def _json(self, code: int, data: dict):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._write_cors()
        self.end_headers()
        self.wfile.write(body)
