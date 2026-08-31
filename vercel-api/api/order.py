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
import hashlib
import math
import logging
import os
import re
import time
import traceback
from datetime import datetime, timedelta, timezone
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
_SUPABASE_SERVICE_ROLE_KEY = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
_OPERATOR_BUCKET = os.environ.get("OPERATOR_BUCKET", "verity-reports")

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
_ORDER_POLICY_MODE = os.environ.get("ORDER_POLICY_MODE", "advised").strip().lower()
_ORDER_PRICE_BAND_PCT = float(os.environ.get("ORDER_PRICE_BAND_PCT", "0.05"))
_MICRO_SEED_MAX_KRW = int(os.environ.get("ORDER_MICRO_SEED_MAX_KRW", "2000000"))
_MICRO_MAX_NAME_PCT = float(os.environ.get("ORDER_MICRO_MAX_NAME_PCT", "0.25"))
_MICRO_MAX_TOTAL_PCT = float(os.environ.get("ORDER_MICRO_MAX_TOTAL_PCT", "0.60"))
_MICRO_MAX_HOLDINGS = int(os.environ.get("ORDER_MICRO_MAX_HOLDINGS", "8"))
_MICRO_MIN_ORDER_KRW = int(os.environ.get("ORDER_MICRO_MIN_ORDER_KRW", "20000"))
_STANDARD_MAX_NAME_PCT = float(os.environ.get("ORDER_STANDARD_MAX_NAME_PCT", "0.15"))
_STANDARD_MAX_TOTAL_PCT = float(os.environ.get("ORDER_STANDARD_MAX_TOTAL_PCT", "0.60"))
_ALLOW_MEMORY_FALLBACK = os.environ.get("ORDER_ALLOW_MEMORY_FALLBACK", "0") == "1"

# 인메모리 중복 방지 (서버리스 한계로 인스턴스별 상태 — 완전 중복 차단은 아님).
# 실 배포에는 Upstash/Redis 권장.
_ORDER_DEDUPE: dict = {}
_ORDER_DEDUPE_TTL = 30
_DAILY_ORDER_COUNT: dict = {}


def _to_float(value, default: float = 0.0) -> float:
    try:
        parsed = float(str(value or "0").replace(",", ""))
        return parsed if math.isfinite(parsed) else default
    except (TypeError, ValueError):
        return default


def _parse_kst_iso(value) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _is_buy(side: str) -> bool:
    return side in ("BUY", "02")


def _kr_market_open(now: Optional[datetime] = None) -> bool:
    kst = timezone(timedelta(hours=9))
    current = (now or datetime.now(kst)).astimezone(kst)
    if current.weekday() >= 5:
        return False
    minute = current.hour * 60 + current.minute
    return 9 * 60 <= minute <= 15 * 60 + 30


def _download_moderation() -> Optional[dict]:
    if not (sb.SUPABASE_URL and _SUPABASE_SERVICE_ROLE_KEY):
        return None
    try:
        response = requests.get(
            f"{sb.SUPABASE_URL}/storage/v1/object/{_OPERATOR_BUCKET}/_operator/moderation_portfolio.json",
            headers={
                "apikey": _SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {_SUPABASE_SERVICE_ROLE_KEY}",
            },
            timeout=8,
        )
        if response.status_code == 200:
            payload = response.json()
            return payload if isinstance(payload, dict) else None
        _logger.warning("moderation policy fetch status=%s", response.status_code)
    except (requests.RequestException, ValueError) as exc:
        _logger.warning("moderation policy fetch failed: %s", exc)
    return None


def _balance_policy_view(balance: dict, ticker: str) -> dict:
    rows = balance.get("output1") if isinstance(balance, dict) else None
    rows = rows if isinstance(rows, list) else []
    current_qty = 0
    current_name_value = 0.0
    invested_value = 0.0
    holding_count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        qty = int(_to_float(row.get("hldg_qty") or row.get("ovrs_cblc_qty")))
        if qty <= 0:
            continue
        holding_count += 1
        code = str(row.get("pdno") or row.get("ovrs_pdno") or "").strip()
        price = _to_float(
            row.get("prpr") or row.get("now_pric2") or row.get("ovrs_now_pric1")
        )
        value = _to_float(
            row.get("evlu_amt") or row.get("ovrs_stck_evlu_amt") or qty * price
        )
        invested_value += max(value, 0.0)
        if code == ticker:
            current_qty += qty
            current_name_value += max(value, 0.0)

    summary = balance.get("output2") if isinstance(balance, dict) else None
    if isinstance(summary, list):
        summary = summary[0] if summary else {}
    summary = summary if isinstance(summary, dict) else {}
    cash = _to_float(summary.get("dnca_tot_amt") or summary.get("frcr_dncl_amt_2"))
    total_asset = _to_float(summary.get("tot_evlu_amt") or summary.get("tot_asst_amt"))
    return {
        "cash": cash,
        "total_asset": total_asset,
        "current_qty": current_qty,
        "current_name_value": current_name_value,
        "invested_value": invested_value,
        "holding_count": holding_count,
    }


def _evaluate_order_policy(
    normalized: dict,
    limits: dict,
    balance: dict,
    quote: dict,
    moderation: Optional[dict] = None,
    override_reason: str = "",
    market_open: Optional[bool] = None,
) -> Tuple[bool, str, dict]:
    """Evaluate the execution contract using fresh quote and account state."""
    mode = _ORDER_POLICY_MODE if _ORDER_POLICY_MODE in {"manual", "advised", "enforced"} else "advised"
    if normalized["market"] != "kr":
        return False, "US order policy is not enabled", {}
    if not (_kr_market_open() if market_open is None else market_open):
        return False, "KR market is closed", {}
    if mode == "manual" and not override_reason.strip():
        return False, "manual mode requires override_reason", {}

    live_price = _to_float(quote.get("price"))
    if live_price <= 0:
        return False, "live price unavailable", {}
    order_type = normalized["order_type"]
    requested_price = _to_float(normalized["price"])
    execution_price = live_price if order_type == "01" else requested_price
    if execution_price <= 0:
        return False, "execution price unavailable", {}
    if order_type == "00":
        gap = abs(requested_price / live_price - 1.0)
        if gap > _ORDER_PRICE_BAND_PCT:
            return False, "limit price exceeds live-price band", {}
        upper = _to_float(quote.get("upper_limit"))
        lower = _to_float(quote.get("lower_limit"))
        if upper > 0 and requested_price > upper:
            return False, "limit price exceeds exchange upper limit", {}
        if lower > 0 and requested_price < lower:
            return False, "limit price is below exchange lower limit", {}

    view = _balance_policy_view(balance, normalized["ticker"])
    seed = _to_float(limits.get("seed_krw"))
    capital_base = seed if seed > 0 else view["total_asset"]
    if capital_base <= 0:
        return False, "capital base unavailable", {}

    is_micro = capital_base <= _MICRO_SEED_MAX_KRW
    max_name_pct = _MICRO_MAX_NAME_PCT if is_micro else _STANDARD_MAX_NAME_PCT
    max_total_pct = _MICRO_MAX_TOTAL_PCT if is_micro else _STANDARD_MAX_TOTAL_PCT
    order_value = normalized["qty"] * execution_price
    buying = _is_buy(normalized["side"])
    signed_value = order_value if buying else -order_value
    post_name_value = max(0.0, view["current_name_value"] + signed_value)
    post_total_value = max(0.0, view["invested_value"] + signed_value)

    if buying:
        if order_value > view["cash"]:
            return False, "insufficient cash", {}
        if is_micro and order_value < _MICRO_MIN_ORDER_KRW:
            return False, "order is below micro-profile minimum", {}
        if view["current_qty"] == 0 and is_micro and view["holding_count"] >= _MICRO_MAX_HOLDINGS:
            return False, "micro-profile holding count exceeded", {}
        if post_name_value / capital_base > max_name_pct + 1e-9:
            return False, "post-trade single-name exposure exceeded", {}
        if post_total_value / capital_base > max_total_pct + 1e-9:
            return False, "post-trade total exposure exceeded", {}
    elif normalized["qty"] > view["current_qty"]:
        return False, "sell quantity exceeds live holdings", {}

    target_weight = None
    moderation_fresh = False
    moderation_version = None
    if isinstance(moderation, dict) and moderation.get("status") == "ok":
        target_weight = _to_float((moderation.get("weights") or {}).get(normalized["ticker"]), -1.0)
        moderation_version = moderation.get("method") or moderation.get("version")
        generated = _parse_kst_iso(moderation.get("generated_at"))
        moderation_fresh = bool(
            generated and 0 <= (datetime.now(timezone.utc) - generated.astimezone(timezone.utc)).total_seconds() <= 36 * 3600
        )
    if mode == "enforced":
        if not moderation_fresh:
            return False, "current moderation target unavailable", {}
        if target_weight is None or target_weight <= 0:
            return False, "ticker is not in the enforced target portfolio", {}
        if post_name_value / capital_base > target_weight + 1e-9:
            return False, "order exceeds enforced target weight", {}

    snapshot = {
        "mode": mode,
        "capital_profile": "micro" if is_micro else "standard",
        "capital_base_krw": round(capital_base),
        "live_price": live_price,
        "price_band_pct": _ORDER_PRICE_BAND_PCT,
        "current_qty": view["current_qty"],
        "post_name_pct": round(post_name_value / capital_base, 6),
        "post_total_pct": round(post_total_value / capital_base, 6),
        "max_name_pct": max_name_pct,
        "max_total_pct": max_total_pct,
        "target_weight": target_weight if target_weight is not None and target_weight >= 0 else None,
        "target_current": moderation_fresh,
        "target_version": moderation_version,
        "override_reason": override_reason.strip()[:300] or None,
        "executor": {
            "is_executor": True,
            "executor": "vercel-api.api.order._evaluate_order_policy",
            "owner": "server_order_policy",
        },
    }
    return True, "", snapshot


def _shared_reserve(
    user: dict,
    normalized: dict,
    policy_snapshot: Optional[dict] = None,
) -> Optional[Tuple[bool, str]]:
    """Supabase RPC로 인스턴스 공용 주문 슬롯을 원자적으로 예약한다.

    기본은 내구성 원장이 없으면 주문을 거절한다. 서버리스 인스턴스별
    인메모리 폴백은 명시적인 전환기 플래그가 있을 때만 허용한다.
    """
    if not (sb.SUPABASE_URL and sb.SUPABASE_ANON_KEY):
        if _ALLOW_MEMORY_FALLBACK:
            return None
        return False, "order safety ledger unavailable"
    canonical = json.dumps(
        {
            "ticker": normalized["ticker"],
            "side": normalized["side"],
            "qty": normalized["qty"],
            "price": normalized["price"],
            "order_type": normalized["order_type"],
            "market": normalized["market"],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    order_hash = hashlib.sha256(canonical).hexdigest()
    daily_limit = int(user["limits"].get("daily_order_count_limit", _DAILY_COUNT_LIMIT_DEFAULT))
    try:
        r = requests.post(
            f"{sb.SUPABASE_URL}/rest/v1/rpc/reserve_order_slot",
            headers={
                "apikey": sb.SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {user['jwt']}",
                "Content-Type": "application/json",
            },
            json={
                "p_order_hash": order_hash,
                "p_daily_limit": daily_limit,
                "p_policy_mode": (policy_snapshot or {}).get("mode", "unknown"),
                "p_policy_snapshot": policy_snapshot or {},
                "p_override_reason": (policy_snapshot or {}).get("override_reason"),
            },
            timeout=8,
        )
        if r.status_code in (404, 405) or (r.status_code == 400 and "PGRST202" in r.text):
            _logger.error("reserve_order_slot policy RPC unavailable — refusing order")
            if _ALLOW_MEMORY_FALLBACK:
                return None
            return False, "order safety ledger migration required"
        if r.status_code != 200:
            _logger.error("reserve_order_slot failed: status=%s body=%s", r.status_code, r.text[:200])
            return False, "order safety ledger unavailable"
        payload = r.json()
        if payload.get("ok") is True:
            return True, ""
        reason = payload.get("reason")
        if reason == "duplicate":
            return False, "duplicate order within 30s"
        if reason == "daily_limit":
            return False, "daily order count exceeded"
        return False, "order safety ledger rejected request"
    except (requests.RequestException, ValueError) as e:
        _logger.error("reserve_order_slot error: %s", e)
        return False, "order safety ledger unavailable"


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
            "seed_krw": None,
        }
        try:
            rows = sb.select(
                "profiles",
                {
                    "id": f"eq.{user_id}",
                    "select": "order_enabled,max_order_krw,daily_order_count_limit,broker_slug,seed_krw",
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
                "seed_krw": int(row["seed_krw"]) if _to_float(row.get("seed_krw")) > 0 else None,
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

    def _fetch_policy_inputs(
        self,
        user: dict,
        normalized: dict,
    ) -> Tuple[Optional[dict], Optional[dict], str]:
        """Fetch account state and a timestamped quote immediately before reservation."""
        if normalized["market"] != "kr":
            return None, None, "US order policy is not enabled"
        try:
            headers = self._proxy_headers(user)
            balance_response = requests.get(
                f"{_RAILWAY_URL}/api/order",
                params={"market": "kr"},
                headers=headers,
                timeout=12,
            )
            if balance_response.status_code != 200:
                return None, None, "live balance unavailable"
            balance = balance_response.json()
            if not isinstance(balance, dict) or balance.get("error"):
                return None, None, "live balance unavailable"

            quote_response = requests.get(
                f"{_RAILWAY_URL}/quotes",
                params={"tickers": normalized["ticker"]},
                headers=headers,
                timeout=8,
            )
            if quote_response.status_code != 200:
                return None, None, "live quote unavailable"
            quote_payload = quote_response.json()
            quote = (quote_payload.get("quotes") or {}).get(normalized["ticker"])
            quote_asof = _parse_kst_iso(quote_payload.get("asof"))
            if not isinstance(quote, dict) or quote_asof is None:
                return None, None, "live quote unavailable"
            age = (datetime.now(timezone.utc) - quote_asof.astimezone(timezone.utc)).total_seconds()
            if age < -30 or age > 120:
                return None, None, "live quote is stale"
            return balance, quote, ""
        except (requests.RequestException, ValueError, TypeError) as exc:
            _logger.error("order policy input fetch failed: %s", exc)
            return None, None, "order policy inputs unavailable"

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
        side = {"01": "SELL", "02": "BUY"}.get(side, side)
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

        override_reason = str(body.get("override_reason", "")).strip()[:300]
        balance, quote, input_error = self._fetch_policy_inputs(user, normalized)
        if balance is None or quote is None:
            self._json(503, {"error": input_error or "order policy inputs unavailable"})
            return
        policy_ok, policy_error, policy_snapshot = _evaluate_order_policy(
            normalized,
            user["limits"],
            balance,
            quote,
            moderation=_download_moderation(),
            override_reason=override_reason,
        )
        if not policy_ok:
            self._json(409, {"error": policy_error})
            return

        shared = _shared_reserve(user, normalized, policy_snapshot)
        if shared is not None:
            reserved, reserve_error = shared
            if not reserved:
                self._json(429 if "duplicate" in reserve_error or "daily" in reserve_error else 503,
                           {"error": reserve_error})
                return
        else:
            # 마이그레이션 전환기 한정 폴백. 032 적용 뒤에는 RPC가 항상 이 경로보다 우선한다.
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
            upstream_order = {**normalized, "side": normalized["side"].lower()}
            r = requests.post(
                f"{_RAILWAY_URL}/api/order",
                json=upstream_order,
                headers=self._proxy_headers(user),
                timeout=12,
            )
            try:
                payload = r.json()
            except Exception:
                payload = {"success": False, "message": "upstream returned non-JSON"}
            if isinstance(payload, dict):
                payload["order_policy"] = policy_snapshot
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
