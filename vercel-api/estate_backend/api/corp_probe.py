"""
GET /api/_corp_probe

진단 전용 — PostgREST OpenAPI 스펙 조회해 'estate_*' 테이블이
인식되는지 확인. PGRST125 원인 확정용. 사용 후 삭제.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
import os
import requests


def _probe() -> dict:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    out: dict = {"url_present": bool(url), "key_present": bool(key)}
    if not url or not key:
        return out

    try:
        r = requests.get(
            f"{url}/rest/v1/",
            headers={"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/openapi+json"},
            timeout=8,
        )
        out["openapi_status"] = r.status_code
        if r.status_code == 200:
            try:
                spec = r.json()
                paths = list((spec.get("paths") or {}).keys())
                out["estate_paths"] = sorted(p for p in paths if "estate" in p)
                out["all_paths_sample"] = sorted(paths)[:30]
                out["total_paths"] = len(paths)
            except Exception as e:
                out["openapi_parse"] = f"err:{type(e).__name__}"
        else:
            out["openapi_body"] = r.text[:300]
    except Exception as e:
        out["openapi_exc"] = f"{type(e).__name__}:{e}"

    # 직접 표적 테이블 호출
    for tbl in ("estate_market_reports", "estate_corp_holdings", "estate_corp_facilities"):
        try:
            r = requests.get(
                f"{url}/rest/v1/{tbl}",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
                params={"select": "*", "limit": "1"},
                timeout=6,
            )
            out[tbl] = {"status": r.status_code, "body": (r.text or "")[:200]}
        except Exception as e:
            out[tbl] = {"exc": f"{type(e).__name__}:{e}"}

    return out


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = _probe()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8"))
