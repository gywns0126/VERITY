"""
VERITY 차트/호가/체결 API — Railway 프록시.
GET /api/chart?ticker=005930
GET /api/chart?ticker=005930&type=minute

KIS 토큰 발급은 Railway 서버에서만 수행.
Vercel은 프록시만 담당하여 토큰 중복 발급을 방지한다.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import requests
from urllib.parse import parse_qs, urlparse

_RAILWAY_URL = (
    os.environ.get("RAILWAY_URL", "https://verity-production-1e44.up.railway.app")
    .strip().strip('"').rstrip("/")
)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        ticker = (params.get("ticker", [""])[0] or params.get("t", [""])[0]).strip().zfill(6)
        qtype = params.get("type", ["all"])[0].strip().lower()

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=30, stale-while-revalidate=60")
        self.end_headers()

        if not ticker or ticker == "000000":
            self.wfile.write(json.dumps({"error": "ticker 파라미터 필요"}, ensure_ascii=False).encode())
            return

        try:
            r = requests.get(
                f"{_RAILWAY_URL}/chart/{ticker}",
                params={"type": qtype},
                timeout=12,
            )
            self.wfile.write(r.content)
        except Exception as e:
            self.wfile.write(json.dumps({"error": str(e)[:200]}, ensure_ascii=False).encode())
