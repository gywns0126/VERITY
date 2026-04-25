"""
GET /api/landex/methodology

LANDEX V/D/S/C/R 방법론 SSOT 반환. 프론트(ESTATE 페이지) + 디버그 도구가 호출.
"""
from http.server import BaseHTTPRequestHandler
import json

from api.landex._methodology import get_methodology_dict


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=3600")  # 1시간 캐시
        self.end_headers()
        body = json.dumps(get_methodology_dict(), ensure_ascii=False).encode("utf-8")
        self.wfile.write(body)
