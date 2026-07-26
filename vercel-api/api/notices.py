"""
공지 · 이벤트 공개 읽기 API (027 migration).

GET /api/notices            → 활성 + 노출 기간 내 공지/이벤트 (pinned 우선 → 최신), 최대 20
GET /api/notices?kind=event → 이벤트만

발행/수정/삭제 = `/api/admin?type=notices` (관리자 인증 + 서비스 role + 감사 로그). 여기는 읽기 전용.

데이터 경계:
  · 노출 = notices RLS(nt_select_public) 통과 행만 — is_active + 기간 내. anon 키로 조회.
  · 027 미적용 DB = 빈 목록 반환 (graceful).
  · CORS = vercel.json 전역 헤더(*) 사용. 인증 헤더를 받지 않는 공개 읽기라 자체 CORS 불요.

🚨 RULE 6 — LLM 0. 관리자가 직접 쓴 문구만 그대로 노출.
"""
from http.server import BaseHTTPRequestHandler
import json
import logging
import os
import time
import traceback
from collections import defaultdict
from urllib.parse import urlparse, parse_qs

import api.supabase_client as sb

_rate_limit: dict = defaultdict(list)
_RATE_WINDOW = 60
_RATE_MAX = 120

_logger = logging.getLogger(__name__)
_LIMIT = 20
_KINDS = ("notice", "event")
# 공지는 자주 바뀌지 않음 — CDN 60초 캐시로 반복 조회 부담 제거(운영 반영 지연 상한도 60초).
_CACHE = "public, max-age=60, s-maxage=60, stale-while-revalidate=300"


def _safe_err(exc, public_msg: str = "Internal error") -> str:
    _logger.error("notices error: %s\n%s", exc, traceback.format_exc())
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


def _json_response(h, data, status=200, cache=_CACHE):
    h.send_response(status)
    h.send_header("Content-Type", "application/json; charset=utf-8")
    h.send_header("Cache-Control", cache)
    h.end_headers()
    h.wfile.write(json.dumps(data, ensure_ascii=False).encode())


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if not _check_rate(_client_ip(self)):
            return _json_response(self, {"error": "요청이 너무 많습니다"}, 429, "no-store")
        if not sb.is_configured():
            return _json_response(self, {"items": []}, 200, "no-store")

        qs = parse_qs(urlparse(self.path).query)
        kind = (qs.get("kind", [""])[0] or "").strip()

        params = {
            "select": "id,kind,title,body,link,pinned,starts_at,ends_at,created_at",
            "order": "pinned.desc,created_at.desc",
            "limit": str(_LIMIT),
        }
        if kind in _KINDS:
            params["kind"] = f"eq.{kind}"

        try:
            rows = sb.select("notices", params)
        except Exception:
            # 027 미적용 DB(테이블 부재) — 배너 없이 정상 렌더
            return _json_response(self, {"items": []}, 200, "no-store")

        items = [{
            "id": r.get("id"),
            "kind": r.get("kind") or "notice",
            "title": r.get("title") or "",
            "body": r.get("body") or "",
            "link": r.get("link") or "",
            "pinned": bool(r.get("pinned")),
            "starts_at": r.get("starts_at") or "",
            "ends_at": r.get("ends_at") or "",
            "created_at": r.get("created_at") or "",
        } for r in (rows or [])]
        _json_response(self, {"items": items})
