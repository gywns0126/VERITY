"""POST /api/content_mcp — closed until private access is configured."""
from http.server import BaseHTTPRequestHandler
import json
import logging

from content_mcp import MAX_BODY, ServiceError, process_request


class handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Do not log URLs, request bodies, or bearer credentials.
        return

    def _handle(self):
        try:
            if self.headers.get("Transfer-Encoding"):
                raise ServiceError(400, "unsupported_transfer_encoding")
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) > 1:
                raise ServiceError(400, "invalid_content_length")
            try:
                length = int(lengths[0]) if lengths else 0
            except ValueError:
                raise ServiceError(400, "invalid_content_length") from None
            if not 0 <= length <= MAX_BODY:
                raise ServiceError(413, "request_too_large")
            status, payload = process_request(self.command, dict(self.headers), self.rfile.read(length))
        except ServiceError as exc:
            status, payload = exc.status, {"error": exc.code}
        except Exception:
            logging.error("content_mcp internal failure")
            status, payload = 500, {"error": "internal_error"}
        raw = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        if status == 405:
            self.send_header("Allow", "POST")
        if status == 401:
            from content_oauth import config
            self.send_header("WWW-Authenticate", 'Bearer resource_metadata="' + config()["metadata"] + '", scope="content:read"')
        if status == 429:
            self.send_header("Retry-After", "60")
        self.end_headers()
        self.wfile.write(raw)

    do_POST = _handle
    do_GET = _handle
    do_DELETE = _handle
    do_OPTIONS = _handle
