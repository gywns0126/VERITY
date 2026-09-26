"""Narrow OAuth HTTP adapter. Do not log queries, cookies, codes or tokens."""
from http.server import BaseHTTPRequestHandler
import json

from content_mcp import ServiceError
from content_oauth import process


class handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _handle(self):
        extra = {}
        try:
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get("Transfer-Encoding") or len(lengths) > 1:
                raise ServiceError(400, "invalid_request")
            try:
                length = int(lengths[0]) if lengths else 0
            except ValueError:
                raise ServiceError(400, "invalid_request") from None
            if not 0 <= length <= 16384:
                raise ServiceError(413, "request_too_large")
            status, payload, extra = process(self.command, self.path, dict(self.headers), self.rfile.read(length))
        except ServiceError as exc:
            status, payload = exc.status, {"error": exc.code}
        except Exception:
            status, payload = 500, {"error": "internal_error"}
        is_html = isinstance(payload, str)
        raw = (payload if is_html else json.dumps(payload, ensure_ascii=False)).encode()
        self.send_response(status)
        self.send_header("Content-Type", ("text/html" if is_html else "application/json") + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        # Keep a non-null Origin on the same-origin consent POST, without
        # disclosing the authorization query to the cross-origin callback.
        self.send_header("Referrer-Policy", "strict-origin")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self' https://chatgpt.com/connector_platform_oauth_redirect; frame-ancestors 'none'; base-uri 'none'")
        self.send_header("Content-Length", str(len(raw)))
        for key, value in extra.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    do_GET = _handle
    do_POST = _handle
    do_OPTIONS = _handle
    do_DELETE = _handle
