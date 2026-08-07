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
import math
import logging
import os
import re
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
# Railway 측에서 X-Service-Auth 헤더를 검증. 미설정 시 모든 주문 요청 503.
_RAILWAY_SHARED_SECRET = (os.environ.get("RAILWAY_SHARED_SECRET") or "").strip().strip('"')

_CORS_HEADERS = ("Content-Type", "Authorization")

# ORDER_ALLOWED_ORIGINS — 쉼표 구분 허용 Origin 목록.
# 2026-04-23: 와일드카드 폴백 제거. 미설정이면 CORS 헤더 자체를 안 붙여 브라우저가
# 크로스오리진 요청을 차단. '*' 를 값에 넣어도 명시적으로 제거 (wildcard 금지).
_raw_origins = (os.environ.get("ORDER_ALLOWED_ORIGINS", "") or "")
# 자사 오퍼레이터 오리진 기본 허용 (2026-08-04 "Load failed" 사고 — env 미등재로 신 도메인
# 전면 차단됐음). 특정 오리진 명시 = 2026-04-23 wildcard 금지 결정 유지. env 는 합집합.
_DEFAULT_ORIGINS = ("https://alphanest-psi.vercel.app",)
_ALLOWED_ORIGINS = frozenset(
    o for o in (s.strip() for s in _raw_origins.split(","))
    if o and o != "*"
) | frozenset(_DEFAULT_ORIGINS)
_WILDCARD_IN_ENV = any(s.strip() == "*" for s in _raw_origins.split(","))

# 모듈 로드 시 설정 상태 로그 (Vercel 빌드 로그에 남음)
if not _RAILWAY_SHARED_SECRET:
    _logger.critical(
        "RAILWAY_SHARED_SECRET 미설정 — /api/order 는 503 반환 (fail-closed)"
    )
if not _ALLOWED_ORIGINS:
    _logger.critical(
        "ORDER_ALLOWED_ORIGINS 미설정 — 모든 CORS 요청 차단"
    )
if _WILDCARD_IN_ENV:
    _logger.warning(
        "ORDER_ALLOWED_ORIGINS 에 '*' 포함됨 — 무시. 명시 origin 만 사용 가능"
    )


def _resolve_origin(request_origin: str) -> str:
    """허용 origin 에 정확 일치하는 경우에만 그대로 반환. 이외는 빈 문자열.
    빈 문자열이면 호출자가 CORS 헤더를 붙이지 않는다 → 브라우저 차단."""
    request_origin = (request_origin or "").strip()
    if not _ALLOWED_ORIGINS:
        return ""
    return request_origin if request_origin in _ALLOWED_ORIGINS else ""

# ── 주문 검증 파라미터 ────────────────────────────────────────
_ALLOWED_SIDES = frozenset({"BUY", "SELL", "01", "02"})
_ALLOWED_ORDER_TYPES = frozenset({"00", "01"})  # 지정가 / 시장가
_ALLOWED_MARKETS = frozenset({"kr", "us"})
# 계좌 라우팅 슬러그 형식 — Supabase 029 의 CHECK 제약과 동일. 서버 env 키를 조립하는
# 값이라 DB 가드가 뚫려도 여기서 한 번 더 끊는다(이중 방어).
_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]{0,15}$")

_MAX_QTY = int(os.environ.get("ORDER_MAX_QTY", "10000"))
_MAX_PRICE_KRW = int(os.environ.get("ORDER_MAX_PRICE_KRW", "100000000"))
_MAX_ORDER_VALUE_KRW_DEFAULT = int(os.environ.get("ORDER_MAX_VALUE_KRW", "10000000"))
# US 주문 안전 상한 (2026-08-04 결함 fix) — 달러 주문에 원화 상한을 적용하던 통화 혼합 제거.
# KRW 1천만원 ≈ USD 7천 수준을 보수적으로 잡음(환율 무관 고정 상한, 필요 시 env 조정).
_MAX_PRICE_USD = float(os.environ.get("ORDER_MAX_PRICE_USD", "100000"))
_MAX_ORDER_VALUE_USD_DEFAULT = float(os.environ.get("ORDER_MAX_VALUE_USD", "7000"))
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
        """profiles 테이블에서 사용자별 주문 권한/한도/계좌 라우팅 조회. 실패 시 기본값.

        🚨 broker_slug 는 기본값을 두지 않는다(None). 회원이 2명 이상인 순간
        기본값 = "조회에 실패하면 남의 계좌로 주문" 이 되기 때문이다. 없으면 거절.
        """
        defaults = {
            "order_enabled": False,
            "max_order_krw": _MAX_ORDER_VALUE_KRW_DEFAULT,
            "daily_order_count_limit": _DAILY_COUNT_LIMIT_DEFAULT,
            "broker_slug": None,
        }
        try:
            rows = sb.select(
                "profiles",
                {
                    "id": f"eq.{user_id}",
                    "select": "order_enabled,max_order_krw,daily_order_count_limit,broker_slug",
                    "limit": "1",
                },
                user_jwt=jwt,
            )
            if not rows:
                return defaults
            row = rows[0]
            slug = (row.get("broker_slug") or "").strip()
            return {
                "order_enabled": bool(row.get("order_enabled")),
                "max_order_krw": int(row.get("max_order_krw") or defaults["max_order_krw"]),
                "daily_order_count_limit": int(
                    row.get("daily_order_count_limit") or defaults["daily_order_count_limit"]
                ),
                "broker_slug": slug if _SLUG_RE.match(slug) else None,
            }
        except Exception as e:
            _logger.warning("order limits lookup failed: %s", e)
            return defaults

    def _authorized_user(self) -> Optional[dict]:
        """Supabase access_token 검증 + 주문 권한 확인. 실패 시 401/403/503 응답."""
        # 0) 서비스 설정 게이트 — secret 미설정이면 Railway 에 요청 자체를 보내지 않는다.
        #    Railway 도 fail-closed 지만 Vercel 에서 조기 차단해 불필요한 아웃바운드 차단.
        if not _RAILWAY_SHARED_SECRET:
            self._json(503, {
                "error": "Service unavailable",
                "detail": "RAILWAY_SHARED_SECRET 미설정",
            })
            return None

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
        # 🚨 계좌 라우팅 미지정 = 거절. 조용히 기본 계좌로 보내면 남의 실계좌로 체결된다.
        if not limits.get("broker_slug"):
            self._json(403, {
                "error": "Broker account not linked",
                "detail": "profiles.broker_slug 미지정 — 서버에서 계좌 연결 후 이용 가능",
            })
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
        # 실계좌 라우팅 — 값의 출처는 service_role 전용 컬럼(029). 클라이언트 입력이 아니다.
        out["X-Verity-Broker"] = user["limits"]["broker_slug"]
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

        # 🚨 2026-08-04 결함 fix — US 소수 가격 지원:
        #   옛 코드는 price 를 무조건 int() → US 지정가 $133.54 가 133 으로 절삭(잘못된 가격 주문)
        #   또는 문자열 "133.54" 에서 ValueError 거부. KR 은 정수 호가라 int 강제 유지.
        try:
            qty = int(body.get("qty", 0))
            price = float(body.get("price", 0) or 0)
        except (TypeError, ValueError):
            return False, "qty/price must be numeric", None

        # 🚨 유한성·부호 가드 (2026-08-04 적대적 테스트로 발견 — 실자금 경로).
        #   NaN 은 모든 비교가 False 라 아래 상한 검사를 전부 통과한다(nan 가격이 KIS 로 전송).
        #   Inf/NaN 은 KR 분기의 int() 에서 ValueError/OverflowError → 미처리 500 (옛 int() 강제
        #   코드는 try 안이라 400 이었음 = float 전환이 만든 회귀). 여기서 선차단.
        if not math.isfinite(price):
            return False, "price must be a finite number", None
        if price < 0:
            return False, "price must not be negative", None

        if market == "kr":
            if price != int(price):
                return False, "KR price must be integer (호가 단위)", None
            price = int(price)
        else:
            price = round(price, 2)   # US = 소수 2자리(센트)

        if qty <= 0 or qty > _MAX_QTY:
            return False, f"qty out of range (1~{_MAX_QTY})", None

        # 통화별 상한 — 달러 주문에 원화 상한을 쓰던 통화 혼합 제거
        is_kr = market == "kr"
        max_price = _MAX_PRICE_KRW if is_kr else _MAX_PRICE_USD
        cur = "KRW" if is_kr else "USD"
        if order_type == "00":
            if price <= 0 or price > max_price:
                return False, f"price out of range for limit order ({cur})", None
        # 시장가는 price=0 허용

        order_value = qty * max(price, 1)
        max_per_order = (
            float(limits.get("max_order_krw", _MAX_ORDER_VALUE_KRW_DEFAULT)) if is_kr
            else float(limits.get("max_order_usd", _MAX_ORDER_VALUE_USD_DEFAULT))
        )
        if order_value > max_per_order:
            return False, f"order value exceeds per-order limit ({max_per_order:,.0f} {cur})", None

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
