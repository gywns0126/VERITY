"""
VERITY 차트/호가/체결 API — Railway 프록시.
GET /api/chart?ticker=005930
GET /api/chart?ticker=005930&type=minute

KIS 토큰 발급은 Railway 서버에서만 수행.
Vercel은 프록시만 담당하여 토큰 중복 발급을 방지한다.

보안:
  - ticker는 6자리 숫자만 허용 (정규식 검증, path traversal 방지)
  - type은 화이트리스트로 제한
  - 에러 메시지에 예외 원문 노출 금지
"""
from http.server import BaseHTTPRequestHandler
import json
import logging
import os
import re
import traceback
from urllib.parse import parse_qs, urlparse

import requests

_logger = logging.getLogger(__name__)

_RAILWAY_URL = (
    os.environ.get("RAILWAY_URL", "https://verity-production-1e44.up.railway.app")
    .strip().strip('"').rstrip("/")
)

_TICKER_RE = re.compile(r"^[0-9]{6}$")
_ALLOWED_TYPES = frozenset({"all", "minute", "daily", "tick", "quote"})


def _safe_err(exc, public_msg: str = "chart fetch failed") -> str:
    _logger.error("chart api error: %s\n%s", exc, traceback.format_exc())
    return public_msg


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        ticker = (params.get("ticker", [""])[0] or params.get("t", [""])[0]).strip()
        qtype = params.get("type", ["all"])[0].strip().lower()

        if qtype not in _ALLOWED_TYPES:
            qtype = "all"

        # 6자리 미만 숫자면 좌측 0 패딩, 그 외는 규격 위반으로 거부.
        if ticker.isdigit() and len(ticker) < 6:
            ticker = ticker.zfill(6)

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=30, stale-while-revalidate=60")
        self.end_headers()

        if not _TICKER_RE.match(ticker):
            self.wfile.write(json.dumps(
                {"error": "invalid ticker (6-digit KR code only)"},
                ensure_ascii=False,
            ).encode())
            return

        if ticker == "000000":
            self.wfile.write(json.dumps(
                {"error": "ticker 파라미터 필요"},
                ensure_ascii=False,
            ).encode())
            return

        try:
            r = requests.get(
                f"{_RAILWAY_URL}/chart/{ticker}",
                params={"type": qtype},
                timeout=12,
            )
            self.wfile.write(r.content)
        except Exception as e:
            self.wfile.write(json.dumps(
                {"error": _safe_err(e, "chart fetch failed")},
                ensure_ascii=False,
            ).encode())
