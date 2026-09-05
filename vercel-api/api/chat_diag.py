"""
VERITY Chat — 진단 엔드포인트

GET /api/chat_diag

구형 Hybrid가 다시 활성화되지 않았는지와 현재 환경·CORS 상태를 확인한다.

반환:
  {
    "ok": true,
    "hybrid": {
      "retired": true,
      "configured_flag": true,           // 과거 env 잔존 여부
      "effective_enabled": false,
    },
    "env_keys_present": {                // boolean — 값은 노출하지 않음
      "PERPLEXITY_API_KEY": true,
      ...
    },
    "runtime": {                         // Vercel 번들 디버깅용
      "python_version": "3.9.x",
      "cwd": "...",
      "chat_hybrid_on_sys_path": true,
    },
  }

보안:
  - 값이 아니라 존재 여부 boolean 만 노출 → secret leak 없음
  - 인증 없음 (정보 민감도 낮음)
  - GET 전용, 쓰기 작업 없음
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler


# chat.py 와 동일한 sys.path 조작 — 실패해도 진단 가능하도록
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


_TRACKED_ENV_KEYS = (
    "CHAT_HYBRID_ENABLED",
    "PERPLEXITY_API_KEY",
    "GEMINI_API_KEY",
    # KIS_APP_KEY / KIS_APP_SECRET / KIS_ACCOUNT_NO 제거 (2026-05-13).
    # Vercel endpoint 에서 KIS 호출 0건 (GH Actions 전용). 죽은 env 등록 정리.
    "FINNHUB_API_KEY",
    "POLYGON_API_KEY",
    "RAILWAY_SHARED_SECRET",
    "ORDER_ALLOWED_ORIGINS",
    "API_ALLOWED_ORIGINS",
    "CHAT_HYBRID_PER_MIN_CAP",
    "CHAT_HYBRID_DAILY_CAP",
    "CHAT_HYBRID_GROUNDING_MODEL",
    "CHAT_HYBRID_CLASSIFIER_MODEL",
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
)


def _cors_diag() -> dict:
    """cors_helper 가 정상 import 되고 ALLOWED_ORIGINS 가 채워졌는지 + 공개 사이트 origin 매칭되는지."""
    out = {
        "import_path_tried": "api.cors_helper",
        "import_ok": False,
        "import_error": None,
        "allowed_origins_count": 0,
        "test_match_public_site": False,
    }
    try:
        from api.cors_helper import resolve_origin, ALLOWED_ORIGINS  # type: ignore
        out["import_ok"] = True
        out["allowed_origins_count"] = len(ALLOWED_ORIGINS)
        # 실제 매칭 — 값이 무엇인지는 노출하지 않고 boolean 만.
        # 🚨 2026-08-12: 프로브 심볼을 구 프레이머 배리티 → 살아있는 공개 사이트로 교체.
        #   구 오리진으로 재면 은퇴한 표면의 허용 여부를 검사하게 된다.
        public_site = "https://www.alphanest.kr"
        out["test_match_public_site"] = bool(resolve_origin(public_site))
    except Exception as e:
        out["import_error"] = f"{type(e).__name__}: {str(e)[:200]}"
        # fallback: 직접 env 길이만 — 값 노출 안 함
        try:
            v = os.environ.get("API_ALLOWED_ORIGINS", "")
            out["env_raw_length"] = len(v)
        except Exception:
            pass
    return out


def _env_presence() -> dict:
    out = {}
    for k in _TRACKED_ENV_KEYS:
        v = os.environ.get(k, "")
        # 값 자체는 노출하지 않되, 비어있음/있음 + 길이만
        if v:
            out[k] = {"present": True, "length": len(v)}
        else:
            out[k] = {"present": False}
    # CHAT_HYBRID_ENABLED 은 값도 노출 (boolean flag 이라 민감도 0)
    out["CHAT_HYBRID_ENABLED"] = {
        "present": bool(os.environ.get("CHAT_HYBRID_ENABLED")),
        "value": os.environ.get("CHAT_HYBRID_ENABLED", "").strip().lower(),
    }
    return out


def _runtime_info() -> dict:
    hybrid_path = os.path.join(_PROJECT_ROOT, "api", "chat_hybrid")
    return {
        "python_version": sys.version.split()[0],
        "cwd": os.getcwd(),
        "project_root": _PROJECT_ROOT,
        "chat_hybrid_path_exists": os.path.isdir(hybrid_path),
        "chat_hybrid_orchestrator_exists": os.path.isfile(
            os.path.join(hybrid_path, "orchestrator.py")
        ),
        "sys_path_first_5": sys.path[:5],
    }


def _try_hybrid_load() -> dict:
    configured = (
        os.environ.get("CHAT_HYBRID_ENABLED", "").strip().lower()
        in ("true", "1", "yes", "on")
    )
    return {
        "retired": True,
        "configured_flag": configured,
        "effective_enabled": False,
        "note": "과거 설정값과 무관하게 외부 다중 모델 합성은 실행되지 않음",
    }


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        try:
            body = {
                "ok": True,
                "hybrid": _try_hybrid_load(),
                "env_keys_present": _env_presence(),
                "runtime": _runtime_info(),
                "cors": _cors_diag(),
            }
            code = 200
        except Exception as e:
            body = {
                "ok": False,
                "error": f"{type(e).__name__}: {str(e)[:200]}",
                "trace": traceback.format_exc()[:500],
            }
            code = 500

        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8"))

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
