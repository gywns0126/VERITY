"""
VERITY Chat Hybrid — 진단 엔드포인트

GET /api/chat_diag

내일 배포 후 hybrid 경로가 제대로 활성화됐는지 원격 확인용.
silent fallback (import 실패 → legacy) 상태를 한 번의 요청으로 진단.

반환:
  {
    "ok": true,
    "hybrid": {
      "enabled_flag": true,              // CHAT_HYBRID_ENABLED env
      "module_loaded": true,             // orchestrator import 성공?
      "import_error": null,              // 실패시 에러
    },
    "env_keys_present": {                // boolean — 값은 노출하지 않음
      "ANTHROPIC_API_KEY": true,
      "PERPLEXITY_API_KEY": true,
      ...
    },
    "runtime": {                         // Vercel 번들 디버깅용
      "python_version": "3.9.x",
      "cwd": "...",
      "chat_hybrid_on_sys_path": true,
    },
    "cache_stats": {...},                // hybrid 로드됐을 때만
    "rate_limit_status": {...},
    "cost_counters": {...}
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
    "ANTHROPIC_API_KEY",
    "PERPLEXITY_API_KEY",
    "GEMINI_API_KEY",
    "KIS_APP_KEY",
    "KIS_APP_SECRET",
    "KIS_ACCOUNT_NO",
    "FINNHUB_API_KEY",
    "POLYGON_API_KEY",
    "RAILWAY_SHARED_SECRET",
    "ORDER_ALLOWED_ORIGINS",
    "CHAT_HYBRID_PER_MIN_CAP",
    "CHAT_HYBRID_DAILY_CAP",
    "CHAT_HYBRID_SYNTH_MODEL",
    "CHAT_HYBRID_GROUNDING_MODEL",
    "CHAT_HYBRID_CLASSIFIER_MODEL",
)


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
    # chat.py 와 동일한 완화된 매칭 규칙
    enabled = (
        os.environ.get("CHAT_HYBRID_ENABLED", "").strip().lower()
        in ("true", "1", "yes", "on")
    )
    result = {
        "enabled_flag": enabled,
        "module_loaded": False,
        "import_error": None,
    }
    try:
        from api.chat_hybrid import orchestrator, cache, rate_limit  # type: ignore
        from api.chat_hybrid.search import perplexity_client, gemini_grounding  # type: ignore
        from api.chat_hybrid.response_synthesizer import get_session_stats as synth_stats  # type: ignore

        result["module_loaded"] = True
        result["cache_stats"] = cache.stats()
        result["rate_limit_global"] = rate_limit.get_status("__global__")
        result["cost_counters"] = {
            "perplexity": perplexity_client.get_session_stats(),
            "grounding": gemini_grounding.get_session_stats(),
            "claude_synth": synth_stats(),
        }
    except Exception as e:
        result["import_error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return result


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
