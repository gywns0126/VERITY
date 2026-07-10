"""
Thesis 커뮤니티 피드 API — 종목별 공개 관점 + 좋아요 + 신고 (thesis.py 형제, 020 migration).

GET  /api/thesis_feed?ticker=005930          → 종목별 공개 관점 목록 (익명 가능, JWT 있으면 liked/mine 플래그)
GET  /api/thesis_feed?limit=30               → ticker 생략 = 전 종목 최신 글로벌 피드 (커뮤니티 페이지, 2026-07-10)
POST /api/thesis_feed { action, thesis_id, reason? }  → like | unlike | report (로그인 필수)

데이터 경계:
  · 노출 = public_profiles view(id/nickname/avatar 3컬럼) + user_thesis 공개행(RLS ut_select_public).
    email/phone/실명(display_name)/기록가(entry_price) = 비노출.
  · 쓰기 = 전부 사용자 JWT 로 Supabase RLS 통과 (tl_insert 는 공개 thesis 에만 허용).
  · 020 미적용 DB = GET 이 빈 목록 반환 (graceful).

🚨 RULE 7 — 피드 내용 = 이용자 개인 의견. VERITY/AlphaNest 채점·추천 0. RULE 6 — LLM 0.
"""
from http.server import BaseHTTPRequestHandler
import json
import logging
import os
import time
import traceback
from collections import defaultdict
from typing import Optional
from urllib.parse import urlparse, parse_qs

import api.supabase_client as sb

_rate_limit: dict = defaultdict(list)
_RATE_WINDOW = 60
_RATE_MAX = 80

_GLOBAL_CALL_LOG: list = []
_GLOBAL_MAX_PER_HOUR = int(os.environ.get("THESIS_GLOBAL_HOURLY_LIMIT", "10000"))

_logger = logging.getLogger(__name__)
_FEED_LIMIT = 20
_FEED_LIMIT_MAX = 50
_ACTIONS = {"like", "unlike", "report"}


def _global_budget_ok() -> bool:
    now = time.time()
    _GLOBAL_CALL_LOG[:] = [t for t in _GLOBAL_CALL_LOG if now - t < 3600]
    if len(_GLOBAL_CALL_LOG) >= _GLOBAL_MAX_PER_HOUR:
        return False
    _GLOBAL_CALL_LOG.append(now)
    return True


def _safe_err(exc, public_msg: str = "Internal error") -> str:
    _logger.error("thesis_feed error: %s\n%s", exc, traceback.format_exc())
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
    h.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
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
            return _json_response(self, {"items": []})

        qs = parse_qs(urlparse(self.path).query)
        ticker = (qs.get("ticker", [""])[0] or "").strip()
        try:
            limit = max(1, min(_FEED_LIMIT_MAX, int(qs.get("limit", ["0"])[0] or 0))) or _FEED_LIMIT
        except Exception:
            limit = _FEED_LIMIT

        # 익명 조회 가능 — JWT 는 liked/mine 플래그용(검증 실패 = 익명 취급)
        viewer_id = None
        jwt = _extract_jwt(self)
        if jwt:
            viewer_id = sb.verify_jwt(jwt)

        # ticker 지정 = 종목 피드 / 생략 = 전 종목 글로벌 피드 (RLS ut_select_public 은 양쪽 동일 적용)
        filters = {
            "is_public": "eq.true",
            "hidden": "eq.false",
            "select": "id,user_id,ticker,stance,note,created_at,updated_at",
            "order": "created_at.desc",
            "limit": str(limit),
        }
        if ticker:
            filters["ticker"] = f"eq.{ticker}"
        try:
            rows = sb.select("user_thesis", filters)
        except Exception:
            return _json_response(self, {"items": []})  # 020 미적용 DB — 컬럼 부재

        if not rows:
            return _json_response(self, {"items": []})

        ids = ",".join(r["id"] for r in rows if r.get("id"))
        uids = ",".join(sorted({r["user_id"] for r in rows if r.get("user_id")}))

        profiles: dict = {}
        try:
            for p in sb.select("public_profiles", {"id": f"in.({uids})", "select": "id,nickname,avatar"}):
                profiles[p["id"]] = p
        except Exception:
            pass

        like_counts: dict = defaultdict(int)
        liked_ids = set()
        try:
            for lk in sb.select("thesis_likes", {"thesis_id": f"in.({ids})", "select": "thesis_id,user_id"}):
                like_counts[lk["thesis_id"]] += 1
                if viewer_id and lk["user_id"] == viewer_id:
                    liked_ids.add(lk["thesis_id"])
        except Exception:
            pass

        items = []
        for r in rows:
            prof = profiles.get(r.get("user_id"), {})
            items.append({
                "id": r.get("id"),
                "ticker": r.get("ticker") or "",
                "nickname": prof.get("nickname") or "익명",
                "avatar": prof.get("avatar") or "",
                "stance": r.get("stance") or "watch",
                "note": r.get("note") or "",
                "created_at": r.get("created_at") or "",
                "likes": like_counts.get(r.get("id"), 0),
                "liked": r.get("id") in liked_ids,
                "mine": bool(viewer_id and r.get("user_id") == viewer_id),
            })
        _json_response(self, {"items": items})

    def do_POST(self):
        if not _global_budget_ok():
            return _json_response(self, {"error": "서비스 혼잡 - 잠시 후 재시도"}, 429)
        if not _check_rate(_client_ip(self)):
            return _json_response(self, {"error": "요청이 너무 많습니다"}, 429)
        if not sb.is_configured():
            return _json_response(self, {"error": "Supabase 미설정"}, 503)

        jwt = _extract_jwt(self)
        user_id = sb.verify_jwt(jwt) if jwt else None
        if not user_id:
            return _json_response(self, {"error": "Unauthorized"}, 401)

        body = _read_body(self)
        action = str(body.get("action", "")).strip()
        thesis_id = str(body.get("thesis_id", "")).strip()
        if action not in _ACTIONS or not thesis_id:
            return _json_response(self, {"error": "action/thesis_id 필요"}, 400)

        try:
            if action == "like":
                try:
                    sb.insert("thesis_likes", {"thesis_id": thesis_id, "user_id": user_id}, user_jwt=jwt)
                except Exception as e:
                    # 이미 좋아요(PK 충돌 409) = 멱등 ok, 그 외 전파
                    resp = getattr(e, "response", None)
                    if not (resp is not None and resp.status_code == 409):
                        raise
                return _json_response(self, {"ok": True})
            if action == "unlike":
                sb.delete("thesis_likes", {"thesis_id": thesis_id, "user_id": user_id}, user_jwt=jwt)
                return _json_response(self, {"ok": True})
            # report
            reason = str(body.get("reason", "")).strip()[:500]
            sb.insert("thesis_reports", {
                "thesis_id": thesis_id, "reporter_id": user_id, "reason": reason,
            }, user_jwt=jwt)
            _json_response(self, {"ok": True})
        except Exception as e:
            _json_response(self, {"error": _safe_err(e, "처리 실패")}, 500)
