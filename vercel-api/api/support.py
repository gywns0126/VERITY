"""AlphaNest 커뮤니티 질문·피드백 API.

GET  /api/support                         공개 동의 + 답변 완료 Q&A
GET  /api/support?mine=1                  로그인 사용자의 질문·피드백
GET  /api/support?admin=1                 관리자 전체 접수함
POST /api/support                         질문·피드백 접수
POST /api/support?admin=1                 관리자 답변·상태·숨김 변경
DELETE /api/support {id}                  본인의 미답변 접수 삭제

공개 범위는 DB RLS와 응답 필드 허용목록으로 이중 제한한다. 이메일·전화·user_id는
공개 응답에 포함하지 않는다. 관리자 변경은 service_role을 사용하고 감사 로그를 남긴다.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
import json
import logging
import os
import time
import traceback
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests

try:
    import api.supabase_client as sb
except ModuleNotFoundError:  # direct module tests
    import supabase_client as sb


_logger = logging.getLogger(__name__)
_rate_limit: Dict[str, list] = defaultdict(list)
_RATE_WINDOW = 60
_RATE_MAX = 60
_KINDS = {"question", "feedback"}
_STATUSES = {"open", "answered", "closed"}
_PUBLIC_LIMIT = 50
_MINE_LIMIT = 100
_ADMIN_LIMIT = 200

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def _cors(h) -> None:
    try:
        from api.cors_helper import resolve_origin
        origin = resolve_origin(h.headers.get("Origin") or "")
    except Exception:
        origin = ""
    if origin:
        h.send_header("Access-Control-Allow-Origin", origin)
        h.send_header("Vary", "Origin")
    h.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
    h.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")


def _json(h, data: Any, status: int = 200) -> None:
    h.send_response(status)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Cache-Control", "no-store")
    _cors(h)
    h.end_headers()
    h.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))


def _body(h) -> dict:
    try:
        size = int(h.headers.get("Content-Length", 0) or 0)
        if size <= 0 or size > 16_384:
            return {}
        return json.loads(h.rfile.read(size).decode("utf-8") or "{}")
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _jwt(h) -> str:
    auth = (h.headers.get("Authorization") or "").strip()
    return auth[7:].strip() if auth.startswith("Bearer ") else ""


def _rate_ok(h) -> bool:
    ip = (h.headers.get("x-forwarded-for") or "").split(",")[0].strip() or "unknown"
    now = time.time()
    _rate_limit[ip] = [t for t in _rate_limit[ip] if now - t < _RATE_WINDOW]
    if len(_rate_limit[ip]) >= _RATE_MAX:
        return False
    _rate_limit[ip].append(now)
    return True


def _truthy(value: Any) -> bool:
    return value is True or str(value).lower() in {"1", "true", "yes"}


def _clean_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _new_payload(user_id: str, data: dict) -> Tuple[Optional[dict], Optional[str]]:
    kind = _clean_text(data.get("kind"), 20)
    title = _clean_text(data.get("title"), 120)
    body = _clean_text(data.get("body"), 2000)
    if kind not in _KINDS:
        return None, "종류를 확인해주세요"
    if not title:
        return None, "제목을 입력해주세요"
    if not body:
        return None, "내용을 입력해주세요"
    consent = bool(_truthy(data.get("publish_consent"))) if kind == "question" else False
    return {
        "user_id": user_id,
        "kind": kind,
        "title": title,
        "body": body,
        "publish_consent": consent,
        "status": "open",
    }, None


def _public_item(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "title": row.get("title") or "",
        "body": row.get("body") or "",
        "answer": row.get("answer") or "",
        "answered_at": row.get("answered_at") or "",
        "created_at": row.get("created_at") or "",
    }


def _mine_item(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "kind": row.get("kind") or "question",
        "title": row.get("title") or "",
        "body": row.get("body") or "",
        "publish_consent": bool(row.get("publish_consent")),
        "status": row.get("status") or "open",
        "answer": row.get("answer") or "",
        "answered_at": row.get("answered_at") or "",
        "created_at": row.get("created_at") or "",
    }


def _service_headers(extra: Optional[dict] = None) -> dict:
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def _service_ready() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def _admin_identity(token: str) -> Optional[dict]:
    if not token or not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return None
    try:
        user_res = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"},
            timeout=5,
        )
        if user_res.status_code != 200:
            return None
        user = user_res.json()
        user_id = user.get("id")
        if not user_id:
            return None
        profile_res = requests.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"},
            params={"id": f"eq.{user_id}", "select": "is_admin"},
            timeout=5,
        )
        profiles = profile_res.json() if profile_res.status_code == 200 else []
        if not profiles or profiles[0].get("is_admin") is not True:
            return None
        return {"id": user_id, "email": user.get("email")}
    except (requests.RequestException, ValueError):
        return None


def _audit(actor: dict, action: str, target_id: str, detail: Optional[dict] = None) -> None:
    if not _service_ready():
        return
    try:
        requests.post(
            f"{SUPABASE_URL}/rest/v1/admin_audit_log",
            headers=_service_headers({"Prefer": "return=minimal"}),
            json={
                "actor_id": actor.get("id"),
                "actor_email": actor.get("email"),
                "action": action,
                "target_type": "community_support",
                "target_id": target_id,
                "detail": detail or {},
            },
            timeout=6,
        )
    except requests.RequestException as exc:
        _logger.warning("support audit failed: %s", exc)


def _admin_list(status_filter: str) -> list:
    params = {
        "select": "id,user_id,kind,title,body,publish_consent,status,answer,answered_at,hidden,created_at,updated_at",
        "order": "created_at.desc",
        "limit": str(_ADMIN_LIMIT),
    }
    if status_filter in _STATUSES:
        params["status"] = f"eq.{status_filter}"
    response = requests.get(
        f"{SUPABASE_URL}/rest/v1/community_support",
        headers=_service_headers(),
        params=params,
        timeout=8,
    )
    response.raise_for_status()
    rows = response.json()
    user_ids = sorted({str(row.get("user_id")) for row in rows if row.get("user_id")})
    profiles: Dict[str, dict] = {}
    if user_ids:
        p_res = requests.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            headers=_service_headers(),
            params={"id": f"in.({','.join(user_ids)})", "select": "id,nickname,display_name"},
            timeout=8,
        )
        if p_res.status_code == 200:
            profiles = {str(p.get("id")): p for p in p_res.json()}
    for row in rows:
        profile = profiles.get(str(row.get("user_id")), {})
        row["author"] = profile.get("nickname") or profile.get("display_name") or "회원"
        row.pop("user_id", None)
    return rows


def _admin_update(actor: dict, data: dict) -> Tuple[Optional[dict], Optional[str]]:
    support_id = _clean_text(data.get("id"), 64)
    action = _clean_text(data.get("action"), 20)
    if not support_id:
        return None, "id 필요"
    patch: Dict[str, Any] = {}
    if action == "answer":
        answer = _clean_text(data.get("answer"), 3000)
        if not answer:
            return None, "답변을 입력해주세요"
        patch = {
            "answer": answer,
            "status": "answered",
            "answered_by": actor.get("id"),
            "answered_at": datetime.now(timezone.utc).isoformat(),
        }
    elif action == "close":
        patch = {"status": "closed"}
    elif action == "reopen":
        patch = {"status": "open", "answer": None, "answered_by": None, "answered_at": None}
    elif action in {"hide", "unhide"}:
        patch = {"hidden": action == "hide"}
    else:
        return None, "작업을 확인해주세요"
    response = requests.patch(
        f"{SUPABASE_URL}/rest/v1/community_support",
        headers=_service_headers({"Prefer": "return=representation"}),
        params={"id": f"eq.{support_id}"},
        json=patch,
        timeout=8,
    )
    response.raise_for_status()
    rows = response.json()
    _audit(actor, f"support_{action}", support_id, {"fields": sorted(patch.keys())})
    return (rows[0] if isinstance(rows, list) and rows else {"id": support_id, **patch}), None


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        _cors(self)
        self.end_headers()

    def do_GET(self):
        if not _rate_ok(self):
            return _json(self, {"error": "요청이 너무 많습니다"}, 429)
        if not sb.is_configured():
            return _json(self, {"items": []})
        query = parse_qs(urlparse(self.path).query)
        token = _jwt(self)
        admin_view = _truthy(query.get("admin", [""])[0])
        mine = _truthy(query.get("mine", [""])[0])
        if admin_view:
            actor = _admin_identity(token)
            if not actor:
                return _json(self, {"error": "Unauthorized"}, 401)
            if not _service_ready():
                return _json(self, {"error": "service_role_unconfigured"}, 503)
            try:
                status_filter = _clean_text(query.get("status", [""])[0], 20)
                return _json(self, {"items": _admin_list(status_filter)})
            except requests.HTTPError as exc:
                if getattr(exc.response, "status_code", 0) in {400, 404}:
                    return _json(self, {"items": [], "migration_required": "037_community_support"})
                _logger.error("support admin GET HTTP: %s", exc)
                return _json(self, {"error": "접수함을 불러오지 못했어요"}, 500)
            except Exception as exc:
                _logger.error("support admin GET: %s\n%s", exc, traceback.format_exc())
                return _json(self, {"error": "접수함을 불러오지 못했어요"}, 500)

        user_id = sb.verify_jwt(token) if token else None
        if mine and not user_id:
            return _json(self, {"error": "Unauthorized"}, 401)
        params = {
            "select": "id,kind,title,body,publish_consent,status,answer,answered_at,created_at",
            "order": "answered_at.desc.nullslast,created_at.desc",
            "limit": str(_MINE_LIMIT if mine else _PUBLIC_LIMIT),
        }
        if mine:
            params["user_id"] = f"eq.{user_id}"
        else:
            params.update({
                "kind": "eq.question",
                "publish_consent": "eq.true",
                "status": "eq.answered",
                "hidden": "eq.false",
            })
        try:
            rows = sb.select("community_support", params, user_jwt=token or None)
            items = [_mine_item(row) for row in rows or []] if mine else [_public_item(row) for row in rows or []]
            return _json(self, {"items": items})
        except Exception as exc:
            _logger.error("support GET: %s\n%s", exc, traceback.format_exc())
            return _json(self, {"items": [], "migration_required": "037_community_support"})

    def do_POST(self):
        if not _rate_ok(self):
            return _json(self, {"error": "요청이 너무 많습니다"}, 429)
        token = _jwt(self)
        query = parse_qs(urlparse(self.path).query)
        admin_view = _truthy(query.get("admin", [""])[0])
        data = _body(self)
        if admin_view:
            actor = _admin_identity(token)
            if not actor:
                return _json(self, {"error": "Unauthorized"}, 401)
            if not _service_ready():
                return _json(self, {"error": "service_role_unconfigured"}, 503)
            try:
                row, error = _admin_update(actor, data)
                return _json(self, {"error": error}, 400) if error else _json(self, row or {})
            except Exception as exc:
                _logger.error("support admin POST: %s\n%s", exc, traceback.format_exc())
                return _json(self, {"error": "답변을 저장하지 못했어요"}, 500)

        user_id = sb.verify_jwt(token) if token else None
        if not user_id:
            return _json(self, {"error": "Unauthorized"}, 401)
        payload, error = _new_payload(user_id, data)
        if error:
            return _json(self, {"error": error}, 400)
        try:
            row = sb.insert("community_support", payload or {}, user_jwt=token)
            return _json(self, _mine_item(row), 201)
        except Exception as exc:
            _logger.error("support POST: %s\n%s", exc, traceback.format_exc())
            return _json(self, {"error": "접수하지 못했어요"}, 500)

    def do_DELETE(self):
        if not _rate_ok(self):
            return _json(self, {"error": "요청이 너무 많습니다"}, 429)
        token = _jwt(self)
        user_id = sb.verify_jwt(token) if token else None
        if not user_id:
            return _json(self, {"error": "Unauthorized"}, 401)
        support_id = _clean_text(_body(self).get("id"), 64)
        if not support_id:
            return _json(self, {"error": "id 필요"}, 400)
        try:
            sb.delete("community_support", {"id": support_id, "user_id": user_id, "status": "open"}, user_jwt=token)
            return _json(self, {"ok": True})
        except Exception as exc:
            _logger.error("support DELETE: %s", exc)
            return _json(self, {"error": "삭제하지 못했어요"}, 500)
