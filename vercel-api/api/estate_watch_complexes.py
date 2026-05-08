"""
Estate User Watch Complexes CRUD — 사용자 단지 watchlist (V0_WATCHLIST 동적 등록).

테이블: estate_user_watch_complexes (migration 014).
estate_brain_builder 가 V0_WATCHLIST + 모든 사용자 등록 단지 union → unique complex 별 brain 산출.

Authorization: Bearer <supabase_access_token> 필수.
서버는 Supabase /auth/v1/user 로 토큰 검증하고 user_id 만 신뢰.

GET    /api/estate/watch-complexes                                 → 본인 등록 단지 목록
POST   /api/estate/watch-complexes  { gu, dong, apt, build_year,
                                       project_type?, redev_stage?,
                                       months_in_stage?, valuation_pending?,
                                       subscription_announced?, memo? }   → 등록
PATCH  /api/estate/watch-complexes  { id, ... }                    → 수정
DELETE /api/estate/watch-complexes  { id }                         → 삭제
"""
from http.server import BaseHTTPRequestHandler
import json
import logging
import re
import time
import traceback
from collections import defaultdict
from typing import Optional

import api.supabase_client as sb
from api.cors_helper import resolve_origin

_logger = logging.getLogger(__name__)

SEOUL_25 = frozenset([
    "강남구", "서초구", "송파구", "강동구", "마포구",
    "용산구", "성동구", "광진구", "중구", "종로구",
    "서대문구", "은평구", "강서구", "양천구", "영등포구",
    "구로구", "금천구", "관악구", "동작구", "성북구",
    "동대문구", "중랑구", "노원구", "도봉구", "강북구",
])

VALID_REDEV_STAGES = frozenset([
    "district_designation", "union_setup", "business_plan",
    "management_plan", "relocation", "completion",
])

VALID_PROJECT_TYPES = frozenset(["reconstruction", "redevelopment"])

_rate_limit: dict = defaultdict(list)
_RATE_WINDOW = 60
_RATE_MAX = 80

# clustering.normalize_apt_name 와 같은 정규식 패턴 (코드 중복 방지 위해 inline import 시도)
_RE_PARENS = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_RE_NUMBER_UNIT = re.compile(r"\d+\s*(단지|차|동|블록|블럭)")
_RE_SPECIAL = re.compile(r"[\-·~,/_\.]+")
_RE_WHITESPACE = re.compile(r"\s+")


def _normalize_apt_name(name: Optional[str]) -> str:
    """clustering.normalize_apt_name 정합 — endpoint 자체에 inline (cross-import 회피)."""
    if not name:
        return ""
    s = name.strip()
    s = _RE_PARENS.sub("", s)
    s = _RE_NUMBER_UNIT.sub("", s)
    s = _RE_SPECIAL.sub("", s)
    s = _RE_WHITESPACE.sub("", s)
    return s.strip()


def _safe_err(exc, public_msg: str = "Internal error") -> str:
    _logger.error("estate_watch_complexes: %s\n%s", exc, traceback.format_exc())
    return public_msg


def _client_ip(h) -> str:
    fwd = h.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return getattr(h, "client_address", ("unknown",))[0]


def _rate_ok(ip: str) -> bool:
    now = time.time()
    bucket = _rate_limit[ip]
    bucket[:] = [t for t in bucket if t > now - _RATE_WINDOW]
    if len(bucket) >= _RATE_MAX:
        return False
    bucket.append(now)
    return True


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
        token = self.headers.get("Authorization", "")
        if not token.startswith("Bearer "):
            self._err(401, "unauthorized", "Bearer token required")
            return None
        user_id = sb.verify_jwt(token[7:].strip())
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
    # GET — 본인 등록 단지 목록
    # ──────────────────────────────────────────────────────────
    def do_GET(self):
        user_id = self._auth_or_reject()
        if not user_id:
            return
        token = self.headers.get("Authorization", "")[7:]
        try:
            rows = sb.select("estate_user_watch_complexes", {
                "user_id": f"eq.{user_id}",
                "select": "id,gu,dong,apt,apt_normalized,build_year,project_type,"
                          "redev_stage,months_in_stage,valuation_pending,"
                          "subscription_announced,memo,created_at,updated_at",
                "order": "created_at.desc",
            }, user_jwt=token) or []
            self._json(200, {"complexes": rows, "total": len(rows)})
        except Exception as e:
            self._err(500, "fetch_failed", _safe_err(e))

    # ──────────────────────────────────────────────────────────
    # POST — 등록
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

        # 검증
        gu = (body.get("gu") or "").strip()
        if gu not in SEOUL_25:
            self._err(400, "invalid_gu", f"gu must be one of 서울 25구")
            return
        dong = (body.get("dong") or "").strip()
        if not dong or len(dong) > 50:
            self._err(400, "invalid_dong", "dong required, max 50 chars")
            return
        apt = (body.get("apt") or "").strip()
        if not apt or len(apt) > 100:
            self._err(400, "invalid_apt", "apt required, max 100 chars")
            return
        try:
            build_year = int(body.get("build_year") or 0)
        except (TypeError, ValueError):
            build_year = 0
        if build_year and not (1950 <= build_year <= 2050):
            self._err(400, "invalid_build_year", "build_year out of range")
            return

        project_type = body.get("project_type")
        if project_type and project_type not in VALID_PROJECT_TYPES:
            self._err(400, "invalid_project_type", f"must be one of {sorted(VALID_PROJECT_TYPES)}")
            return
        redev_stage = body.get("redev_stage")
        if redev_stage and redev_stage not in VALID_REDEV_STAGES:
            self._err(400, "invalid_redev_stage", f"must be one of {sorted(VALID_REDEV_STAGES)}")
            return

        try:
            months_in_stage = max(0, int(body.get("months_in_stage") or 0))
        except (TypeError, ValueError):
            months_in_stage = 0

        memo = (body.get("memo") or "").strip()[:500]

        data = {
            "user_id": user_id,
            "gu": gu, "dong": dong,
            "apt": apt, "apt_normalized": _normalize_apt_name(apt),
            "build_year": build_year,
            "project_type": project_type,
            "redev_stage": redev_stage,
            "months_in_stage": months_in_stage,
            "valuation_pending": bool(body.get("valuation_pending", False)),
            "subscription_announced": bool(body.get("subscription_announced", False)),
            "memo": memo,
        }

        try:
            row = sb.insert("estate_user_watch_complexes", data, user_jwt=token)
            self._json(201, {"complex": row})
        except Exception as e:
            # uniq violation = 23505 (Postgres) — Supabase REST 가 409 로 매핑하기도 함
            msg = str(e).lower()
            if "duplicate" in msg or "23505" in msg:
                self._err(409, "duplicate", "이미 등록된 단지")
                return
            self._err(500, "insert_failed", _safe_err(e))

    # ──────────────────────────────────────────────────────────
    # PATCH — 수정
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
        complex_id = body["id"]
        update_data: dict = {}
        for field in ("memo", "project_type", "redev_stage", "months_in_stage",
                      "valuation_pending", "subscription_announced"):
            if field in body:
                update_data[field] = body[field]
        if "project_type" in update_data and update_data["project_type"] not in (None, *VALID_PROJECT_TYPES):
            self._err(400, "invalid_project_type", "")
            return
        if "redev_stage" in update_data and update_data["redev_stage"] not in (None, *VALID_REDEV_STAGES):
            self._err(400, "invalid_redev_stage", "")
            return
        if not update_data:
            self._err(400, "nothing_to_update", "")
            return
        try:
            rows = sb.update(
                "estate_user_watch_complexes",
                {"id": complex_id, "user_id": user_id},
                update_data, user_jwt=token,
            )
            if not rows:
                self._err(404, "not_found", "")
                return
            self._json(200, {"complex": rows[0]})
        except Exception as e:
            self._err(500, "update_failed", _safe_err(e))

    # ──────────────────────────────────────────────────────────
    # DELETE — 삭제
    # ──────────────────────────────────────────────────────────
    def do_DELETE(self):
        user_id = self._auth_or_reject()
        if not user_id:
            return
        token = self.headers.get("Authorization", "")[7:]
        body = self._read_body()
        if body is None or not body.get("id"):
            self._err(400, "invalid_body", "id required")
            return
        try:
            sb.delete(
                "estate_user_watch_complexes",
                {"id": body["id"], "user_id": user_id},
                user_jwt=token,
            )
            self._json(200, {"ok": True})
        except Exception as e:
            self._err(500, "delete_failed", _safe_err(e))
