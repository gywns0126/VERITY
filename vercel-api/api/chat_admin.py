"""관리자 전용 챗 — 미발행 내부 자산까지 컨텍스트에 넣는 경로.

POST /api/chat_admin  { question, session_id?, recent_turns? }
  → NDJSON: {"type":"status"|"meta"|"delta"|"end"|"error"} 줄 단위

🚨 왜 공개 /api/chat 과 분리했나 (PM 2026-07-30 "나 혼자 볼거고 배포 안할거니까"):
  공개 챗은 인증 게이트가 없다(IP 레이트리밋만). 거기에 내부 데이터를 물리면 그 순간
  아무 방문자에게나 재배포가 된다. 그래서 **경로 자체를 나눈다** —
  공개 경로는 internal=False 기본값 그대로 두고, 이 파일만 검증 통과 후 internal=True 를 켠다.
  한 엔드포인트에 플래그로 얹지 않은 이유 = 플래그 실수 한 번이 곧 유출이기 때문.

인증: Bearer JWT → Supabase /auth/v1/user → profiles.is_admin=true. 또는 X-Admin-Token(우회키).
  admin.py 와 같은 판정을 쓴다(SSOT 재사용, 판정 로직 이중화 금지).
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler

_logger = logging.getLogger(__name__)

# admin.py 의 authorize() 를 그대로 재사용 — 인증 판정을 두 벌로 두지 않는다.
try:
    from api.admin import authorize as _authorize
except Exception:  # noqa: BLE001 — 임포트 실패 시 아래에서 503
    _authorize = None

_MAX_Q = 2000  # 관리자 경로는 공개(500자)보다 넉넉히 — 긴 분석 요청 허용
_RATE_WINDOW = 60
_RATE_MAX = 30
_rate: dict = defaultdict(list)


def _rate_ok(key: str) -> bool:
    now = time.time()
    _rate[key] = [t for t in _rate[key] if now - t < _RATE_WINDOW]
    if len(_rate[key]) >= _RATE_MAX:
        return False
    _rate[key].append(now)
    return True


def _headers_dict(h) -> dict:
    try:
        return {k.lower(): v for k, v in h.items()}
    except Exception:  # noqa: BLE001
        return {}


class handler(BaseHTTPRequestHandler):
    def _cors(self):
        origin = self.headers.get("Origin") or "*"
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Vary", "Origin")

    def _json(self, data: dict, code: int = 200):
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _line(self, obj: dict):
        self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        try:
            self.wfile.flush()
        except Exception:  # noqa: BLE001 — 클라이언트 조기 종료
            pass

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Token")
        self.end_headers()

    def do_GET(self):
        # 헬스 — 게이트가 살아 있는지만 알린다(내용 노출 0).
        hd = _headers_dict(self.headers)
        allowed = bool(_authorize and _authorize(hd)[0])
        self._json({"ok": True, "authorized": allowed, "internal": allowed})

    def do_POST(self):
        if _authorize is None:
            return self._json({"error": "인증 모듈 로드 실패"}, 503)

        hd = _headers_dict(self.headers)
        allowed, how = _authorize(hd)
        if not allowed:
            # 존재 자체를 숨기지 않되(관리자 UI 가 상태를 읽어야 함) 내용은 주지 않는다.
            return self._json({"error": "관리자 인증이 필요합니다"}, 403)

        if not _rate_ok(how or "admin"):
            return self._json({"error": "요청이 너무 많습니다"}, 429)

        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n).decode("utf-8")) if n else {}
        except (ValueError, UnicodeDecodeError):
            return self._json({"error": "본문 파싱 실패"}, 400)

        q = str(body.get("question") or "").strip()
        if not q:
            return self._json({"error": "question 이 필요합니다"}, 400)
        if len(q) > _MAX_Q:
            return self._json({"error": f"질문이 너무 깁니다 ({_MAX_Q}자 이내)"}, 400)

        sid = str(body.get("session_id") or "admin")
        turns = body.get("recent_turns") if isinstance(body.get("recent_turns"), list) else None

        try:
            from api.chat_hybrid import orchestrator as orc
        except Exception as e:  # noqa: BLE001
            _logger.exception("chat_hybrid 로드 실패")
            return self._json({"error": f"챗 엔진 로드 실패: {type(e).__name__}"}, 503)

        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        try:
            for ev in orc.run_hybrid(
                query=q,
                session_id=sid,
                recent_turns=turns,
                internal=True,  # 🚨 이 한 줄이 내부 자산 접근. 공개 경로에는 절대 넣지 말 것.
            ):
                if ev.get("type") == "rate_limit":
                    self._line({"type": "error", "message": ev.get("reason", "요청 한도 초과")})
                else:
                    self._line(ev)
        except Exception as e:  # noqa: BLE001 — 스트림 도중 실패는 이벤트로 알린다
            _logger.exception("admin chat 스트림 실패")
            self._line({"type": "error", "message": f"{type(e).__name__}: {str(e)[:160]}"})

    def log_message(self, *args):  # 서버리스 로그 소음 억제
        return
