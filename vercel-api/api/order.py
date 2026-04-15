"""
VERITY 주문 API — Railway 프록시.
POST /api/order → Railway /api/order (주문)
GET  /api/order → Railway /api/order (잔고)

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
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        """잔고 조회 프록시."""
        qs = parse_qs(urlparse(self.path).query)
        market = (qs.get("market", ["kr"])[0]).lower()
        try:
            r = requests.get(
                f"{_RAILWAY_URL}/api/order",
                params={"market": market},
                timeout=12,
            )
            self._json(r.status_code, r.json())
        except Exception as e:
            self._json(502, {"error": str(e)[:200]})

    def do_POST(self):
        """주문 프록시."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length > 0 else b"{}"
            r = requests.post(
                f"{_RAILWAY_URL}/api/order",
                data=body,
                headers={"Content-Type": "application/json"},
                timeout=12,
            )
            self._json(r.status_code, r.json())
        except Exception as e:
            self._json(502, {"success": False, "message": str(e)[:200]})

    def _json(self, code: int, data: dict):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)
