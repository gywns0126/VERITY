"""
GET /api/landex/health

ESTATE 외부 API 키 + Supabase 연결 상태 확인.
실제 호출 없이 환경변수 존재 여부만 보고 — 키 노출 없음.

응답:
{
  "configured": {
    "publicdata":    true,
    "ecos":          true,
    "seoul_data":    true,
    "seoul_subway":  true,
    "kosis":         true
  },
  "supabase": { "configured": true, "url_present": true },
  "ready": true,
  "missing": []
}
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
import os


def _is_set(name: str) -> bool:
    v = os.environ.get(name, "")
    return bool(v and v.strip())


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        keys = {
            "publicdata":   _is_set("PUBLICDATA_API_KEY"),
            "ecos":         _is_set("ECOS_API_KEY"),
            "seoul_data":   _is_set("SEOUL_DATA_API_KEY"),
            "seoul_subway": _is_set("SEOUL_SUBWAY_API_KEY"),
            "kosis":        _is_set("KOSIS_API_KEY"),
        }
        supabase = {
            "configured": _is_set("SUPABASE_URL") and _is_set("SUPABASE_ANON_KEY"),
            "url_present": _is_set("SUPABASE_URL"),
        }
        missing = [k for k, v in keys.items() if not v]
        ready = len(missing) == 0 and supabase["configured"]

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        body = json.dumps({
            "configured": keys,
            "supabase": supabase,
            "ready": ready,
            "missing": missing,
        }, ensure_ascii=False).encode("utf-8")
        self.wfile.write(body)
