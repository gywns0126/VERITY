"""
User Trades CRUD API — 사용자 본인 매매 거래 이력 + 실현손익(이동평균).

holdings.py 패턴 복제(JWT 인증·레이트리밋·IDOR 차단). user_trades 테이블(022 migration,
RLS auth.uid()=user_id). 모든 요청 Authorization: Bearer <supabase_access_token> 필수.
서버가 /auth/v1/user 로 검증한 user_id 만 신뢰 — body user_id 무시(IDOR 방지).

GET    /api/trades                                                    → 본인 거래 이력 + 실현손익 요약
POST   /api/trades { ticker, name?, market?, side, shares, price, traded_at?, memo? }  → 거래 1건 추가(append)
PATCH  /api/trades { id, side?, shares?, price?, traded_at?, memo?, name? }            → 거래 수정
DELETE /api/trades { id }                                             → 거래 삭제

🚨 RULE 7 — 저장은 사용자 입력(체결가·수량·매매구분) 사실. 실현손익은 이동평균 단순 차감(사실 계산).
   자체 점수·등급·추천 0. 매수·매도 권유 0.
🚨 법률 — 실현손익 기반(미실현 아님), 본인 비공개(RLS). '상위 X%' 배지·백분위·공개 없음.
   price = 사용자 입력 체결가(시세 재배포 아님).
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
from api.nest_validation import read_body, number, asset, select_all

_rate_limit: dict = defaultdict(list)
_RATE_WINDOW = 60
_RATE_MAX = 80

_GLOBAL_CALL_LOG: list = []
_GLOBAL_MAX_PER_HOUR = int(os.environ.get("TRADES_GLOBAL_HOURLY_LIMIT", "10000"))

_logger = logging.getLogger(__name__)


def _global_budget_ok() -> bool:
    now = time.time()
    _GLOBAL_CALL_LOG[:] = [t for t in _GLOBAL_CALL_LOG if now - t < 3600]
    if len(_GLOBAL_CALL_LOG) >= _GLOBAL_MAX_PER_HOUR:
        return False
    _GLOBAL_CALL_LOG.append(now)
    return True


def _safe_err(exc, public_msg: str = "Internal error") -> str:
    _logger.error("trades error: %s\n%s", exc, traceback.format_exc())
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
    h.send_header("Cache-Control", "private, no-store")
    _cors_headers(h)
    h.end_headers()
    h.wfile.write(json.dumps(data, ensure_ascii=False).encode())


def _read_body(h) -> dict:
    return read_body(h)


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
    return number(v, default)


def _valid_date(s: str) -> bool:
    """YYYY-MM-DD 형식 + 실제 날짜 검증. Postgres DATE 파싱 500 사전 차단."""
    try:
        import datetime as _dt
        if len(str(s)) != 10 or str(s)[4] != "-" or str(s)[7] != "-":
            return False
        _dt.date.fromisoformat(str(s))
        return True
    except (ValueError, TypeError):
        return False


def _compute_summary(trades: list) -> dict:
    """종목별 시간순 이동평균으로 실현손익 계산 (사실 계산, RULE 7).

    매수: 수량·원가 누적 → 평단 = 누적원가 / 누적수량.
    매도: 실현손익 += (매도가 − 평단) × 매도수량, 잔량·원가 비례 차감.
    보유 초과 매도(공매/입력오류): 초과분은 평단 미상 → 실현 미반영(허수 이익 방지).
    """
    def _key(t):
        return (str(t.get("traded_at") or ""), str(t.get("created_at") or ""))

    by_ticker: dict = defaultdict(list)
    for t in trades:
        by_ticker[t.get("ticker")].append(t)

    rows = []
    total_realized = 0.0
    unmatched_sell = 0.0
    for ticker, ts in by_ticker.items():
        ts_sorted = sorted(ts, key=_key)
        qty = 0.0          # 보유 잔량
        cost = 0.0         # 잔량의 원가 총액
        realized = 0.0
        name = ""
        market = "kr"
        for t in ts_sorted:
            name = t.get("name") or name
            market = t.get("market") or market
            shares = _num(t.get("shares"), 0) or 0.0
            price = _num(t.get("price"), 0) or 0.0
            if shares <= 0:
                continue
            if t.get("side") == "buy":
                qty += shares
                cost += shares * price
            else:  # sell
                unmatched_sell += max(0.0, shares - qty)
                if qty <= 0:
                    continue  # 보유 없이 매도 = 평단 미상, 실현 미반영
                avg = cost / qty if qty else 0.0
                sold = min(shares, qty)
                realized += (price - avg) * sold
                qty -= sold
                cost = avg * qty  # 잔량 원가 = 평단 × 잔량 (초과 매도분은 무시)
        avg_open = (cost / qty) if qty > 0 else 0.0
        rows.append({
            "ticker": ticker,
            "name": name,
            "market": market,
            "realized_pnl": round(realized, 2),
            "open_shares": round(qty, 6),
            "open_avg_cost": round(avg_open, 4),
        })
        total_realized += realized

    rows.sort(key=lambda r: r["realized_pnl"], reverse=True)
    totals = {currency: round(sum(r["realized_pnl"] for r in rows if ("USD" if r["market"] == "us" else "KRW") == currency), 2)
              for currency in ("KRW", "USD")}
    mixed = len({r["market"] for r in rows}) > 1
    return {"by_ticker": rows, "total_realized_pnl": None if mixed else round(total_realized, 2),
            "realized_by_currency": totals, "unmatched_sell_shares": round(unmatched_sell, 6)}


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
            return _json_response(self, {"error": "Supabase 미설정"}, 503)

        auth = _authenticate(self)
        if not auth:
            return
        user_id, jwt = auth
        try:
            rows = select_all(sb.select, "user_trades", {
                "user_id": f"eq.{user_id}",
                }, jwt)
            rows.sort(key=lambda r: (r.get("traded_at") or "", r.get("created_at") or "", r["id"]))
            _json_response(self, {"trades": rows, "summary": _compute_summary(rows)})
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
        resolved = asset(body)
        if not resolved:
            return _json_response(self, {"error": "국내·미국 주식/ETF 종목코드를 확인해 주세요. 직접 원자재는 지원하지 않습니다."}, 400)
        ticker, market = resolved
        side = str(body.get("side", "")).strip().lower()
        if side not in ("buy", "sell"):
            return _json_response(self, {"error": "side 는 buy 또는 sell"}, 400)
        shares = _num(body.get("shares"))
        price = _num(body.get("price"))
        if shares is None or shares <= 0:
            return _json_response(self, {"error": "shares 는 0 초과 숫자"}, 400)
        if price is None or price <= 0:
            return _json_response(self, {"error": "price 는 0 초과 숫자"}, 400)

        payload = {
            "ticker": ticker,
            "name": str(body.get("name", "")),
            "market": market,
            "side": side,
            "shares": shares,
            "price": price,
            "memo": str(body.get("memo", "")),
        }
        traded_at = str(body.get("traded_at", "")).strip()
        if traded_at:
            if not _valid_date(traded_at):
                return _json_response(self, {"error": "traded_at 는 YYYY-MM-DD"}, 400)
            payload["traded_at"] = traded_at
        payload["user_id"] = user_id  # 서버 검증 user_id 만 (body user_id 무시 — IDOR 차단)
        request_id = body.get("request_id")
        if request_id:
            try:
                from uuid import UUID
                payload["id"] = str(UUID(str(request_id)))
            except (ValueError, TypeError):
                return _json_response(self, {"error": "request_id 형식 오류"}, 400)
        try:
            # The existing UUID primary key deduplicates retries without a migration.
            if request_id:
                previous = sb.select("user_trades", {"id": "eq." + payload["id"], "user_id": "eq." + user_id, "limit": "1"}, user_jwt=jwt)
                if previous:
                    if all(previous[0].get(k) == v for k, v in payload.items()):
                        return _json_response(self, previous[0])
                    return _json_response(self, {"error": "이미 저장된 요청입니다. 목록을 확인하고 수정해 주세요."}, 409)
            row = sb.insert("user_trades", payload, user_jwt=jwt)
            _json_response(self, row, 200)
        except Exception as e:
            if request_id and getattr(getattr(e, "response", None), "status_code", None) == 409:
                return _json_response(self, {"error": "같은 요청이 처리 중이거나 이미 저장됐어요. 목록을 확인해 주세요."}, 409)
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
        tid = str(body.get("id", "")).strip()
        if not tid:
            return _json_response(self, {"error": "id 필요"}, 400)

        updates = {}
        if "name" in body:
            updates["name"] = str(body["name"])
        if "memo" in body:
            updates["memo"] = str(body["memo"])
        if "side" in body:
            s = str(body["side"]).strip().lower()
            if s not in ("buy", "sell"):
                return _json_response(self, {"error": "side 는 buy 또는 sell"}, 400)
            updates["side"] = s
        if "shares" in body:
            v = _num(body["shares"])
            if v is None or v <= 0:
                return _json_response(self, {"error": "shares 는 0 초과 숫자"}, 400)
            updates["shares"] = v
        if "price" in body:
            v = _num(body["price"])
            if v is None or v <= 0:
                return _json_response(self, {"error": "price 는 0 초과 숫자"}, 400)
            updates["price"] = v
        if "traded_at" in body:
            ta = str(body["traded_at"]).strip()
            if not _valid_date(ta):
                return _json_response(self, {"error": "traded_at 는 YYYY-MM-DD"}, 400)
            updates["traded_at"] = ta
        if not updates:
            return _json_response(self, {"error": "변경할 필드 없음"}, 400)

        try:
            rows = sb.update("user_trades", {"id": tid, "user_id": user_id}, updates, user_jwt=jwt)
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
        tid = str(body.get("id", "")).strip()
        if not tid:
            return _json_response(self, {"error": "id 필요"}, 400)
        try:
            sb.delete("user_trades", {"id": tid, "user_id": user_id}, user_jwt=jwt)
            _json_response(self, {"ok": True})
        except Exception as e:
            _json_response(self, {"error": _safe_err(e, "DB 삭제 실패")}, 500)
