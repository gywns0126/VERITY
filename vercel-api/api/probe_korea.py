"""
[temp-probe] P3-4 prereq 측정 1 — Vercel egress 에서 korea.kr 차단 여부 확인.

ESTATE-P2-001 Railway 우회 P0 Contract 진입 전 1회용 probe.
GitHub Actions runner (Azure egress) 는 ConnectionResetError(104) 확인됨.
이 probe 는 Vercel egress (AWS/GCP) 도 동일 차단인지 결정.

작업 완료 즉시 revert 의무 — [C]2 예외 1회 승인 (2026-05-04 user 승인, 갱신).
파일명 _probe_korea.py → probe_korea.py 갱신 (Vercel underscore convention 충돌).
임시 표식: [temp-probe] commit prefix 단독 운용.
"""
from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler

import requests

TARGET_URL = "https://www.korea.kr/rss/dept_molit.xml"
PRODUCTION_UA = "VERITY-ESTATE/1.0 (+https://github.com/gywns0126/VERITY)"


def _probe(user_agent: str, timeout: int = 10) -> dict:
    started = time.time()
    try:
        resp = requests.get(
            TARGET_URL,
            headers={"User-Agent": user_agent},
            timeout=timeout,
            allow_redirects=False,
        )
        elapsed_ms = int((time.time() - started) * 1000)
        return {
            "outcome": "response",
            "status": resp.status_code,
            "elapsed_ms": elapsed_ms,
            "body_first_500": resp.text[:500],
            "body_byte_length": len(resp.content),
            "headers": dict(resp.headers),
            "tls_handshake": "ok",
            "error": None,
        }
    except requests.exceptions.SSLError as e:
        return {"outcome": "tls_error", "error": str(e), "elapsed_ms": int((time.time() - started) * 1000)}
    except requests.exceptions.ConnectionError as e:
        return {"outcome": "connection_error", "error": str(e), "elapsed_ms": int((time.time() - started) * 1000)}
    except requests.exceptions.Timeout as e:
        return {"outcome": "timeout", "error": str(e), "elapsed_ms": int((time.time() - started) * 1000)}
    except Exception as e:
        return {"outcome": "unknown_error", "error_type": type(e).__name__, "error": str(e), "elapsed_ms": int((time.time() - started) * 1000)}


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        result_production_ua = _probe(PRODUCTION_UA)
        result_browser_ua = _probe("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        payload = {
            "purpose": "P3-4 prereq Vercel egress probe",
            "target_url": TARGET_URL,
            "results": {
                "production_ua": result_production_ua,
                "browser_ua": result_browser_ua,
            },
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
