"""오퍼레이터 온디맨드 종합 엔드포인트 — 알파네스트 발행 사실 조인 + 3종 LLM.

소비자 = 오퍼레이터 사이트(https://alphanest-psi.vercel.app) 의 3종 LLM 패널.
  기존 패널은 **추천 상위 종목만 주 1회 사전계산**이라 임의 종목 즉시 조회가 불가했다.
  이 엔드포인트가 그 제약을 푼다.

  GET /api/operator_ask?ticker=094970                 → 사실 조인만 (LLM 0 · 비용 0 · ~10s)
  GET /api/operator_ask?ticker=094970&q=<질문>&llm=1   → 3종 LLM 종합 (~90s)

🚨 인증 = admin.py 와 동일 규약(X-Admin-Token 또는 Bearer JWT + profiles.is_admin).
   공개 노출 절대 금지 — 종목 상담·분석·추천이 포함된다(PM 2026-08-03, 유사투자자문 회피).
   authorize() 통과분만 도달하므로 응답 본문에 판단이 들어가도 된다.

🚨 코어(operator_core/) 는 복제본이다. 수정은 SSOT = api/intelligence/{ticker_facts,operator_ask}.py
   에서 하고 scripts/sync_operator_ask.sh 로 동기화할 것.
"""

from http.server import BaseHTTPRequestHandler
import json
import logging
import os
import sys
import traceback
from typing import Any, Dict, Tuple
from urllib.parse import parse_qs, urlparse

import requests

_logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
ADMIN_BYPASS_TOKEN = os.environ.get("ADMIN_BYPASS_TOKEN", "")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ── 인증 (admin.py 규약 동일) ────────────────────────────────────────────────
def _headers_to_dict(handler) -> Dict[str, str]:
    return {k.lower(): v for k, v in handler.headers.items()}


def _verify_admin_jwt(jwt: str) -> bool:
    if not jwt or not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return False
    try:
        r = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {jwt}"},
            timeout=5,
        )
        if r.status_code != 200:
            return False
        uid = r.json().get("id")
        if not uid:
            return False
        p = requests.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            params={"id": f"eq.{uid}", "select": "is_admin"},
            headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {jwt}"},
            timeout=5,
        )
        if p.status_code != 200:
            return False
        rows = p.json()
        return bool(rows and rows[0].get("is_admin") is True)
    except (requests.RequestException, ValueError) as e:
        _logger.warning("operator_ask admin verify failed: %s", e)
        return False


def _authorize(h: Dict[str, str]) -> Tuple[bool, str]:
    bypass = h.get("x-admin-token")
    if bypass and ADMIN_BYPASS_TOKEN and bypass == ADMIN_BYPASS_TOKEN:
        return True, "bypass_token"
    auth = h.get("authorization") or ""
    if auth.lower().startswith("bearer ") and _verify_admin_jwt(auth.split(" ", 1)[1].strip()):
        return True, "supabase_admin"
    return False, "unauthorized"


def _write(handler, status: int, body: Dict[str, Any]) -> None:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Token")
    handler.end_headers()
    handler.wfile.write(payload)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Token")
        self.end_headers()

    def do_GET(self):
        ok, reason = _authorize(_headers_to_dict(self))
        if not ok:
            return _write(self, 401, {"error": "unauthorized", "reason": reason})

        qs = parse_qs(urlparse(self.path).query)
        query = (qs.get("ticker", [""])[0] or qs.get("q_ticker", [""])[0]).strip()
        question = (qs.get("q", [""])[0] or "").strip()
        want_llm = (qs.get("llm", ["0"])[0] or "0") in ("1", "true", "yes")
        if not query:
            return _write(self, 400, {"error": "ticker 필요"})

        try:
            from operator_core import operator_ask as core  # noqa: PLC0415
        except Exception as e:  # noqa: BLE001
            _logger.error("operator core import 실패: %s\n%s", e, traceback.format_exc())
            return _write(self, 500, {"error": "core_import_failed"})

        try:
            out = core.ask(query, question, facts_only=not want_llm)
        except Exception as e:  # noqa: BLE001
            _logger.error("operator_ask 실패: %s\n%s", e, traceback.format_exc())
            return _write(self, 500, {"error": "ask_failed"})

        facts = out.get("facts") or {}
        body: Dict[str, Any] = {
            "ticker": facts.get("ticker"),
            "name": facts.get("name"),
            "sections": facts.get("sections") or [],
            "missing": facts.get("missing") or [],
            "collected_at": (facts.get("_meta") or {}).get("collected_at"),
            "facts_text": out.get("facts_text"),
        }
        if want_llm:
            syn = out.get("synthesis") or {}
            body["synthesis"] = {
                "text": syn.get("text"),
                "refused": bool(syn.get("refused")),
                "category": syn.get("category"),
                "usage": syn.get("usage"),
            }
            pplx = out.get("perplexity") or {}
            body["external"] = {"text": pplx.get("text"), "citations": pplx.get("citations")}
            body["budget"] = out.get("_budget")
            body["budget_blocked"] = out.get("budget_blocked")
            body["cached"] = bool(out.get("_cached"))
        _write(self, 200, body)
