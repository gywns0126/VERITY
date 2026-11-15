"""Authenticated, read-only candidate for initial public company evidence.

Additive endpoint only. Does not switch the operating mindmap path.
"""
from http.server import BaseHTTPRequestHandler
import json

from api.member_map_state import _identity, _read_json
from api.member_map_analysis import _origin_result, _headers, _encode_result
from api.portfolio_core.portfolio_company_snapshot import _positions, read_company_snapshot


def snapshot_request(request):
    error, headers = _origin_result(request)
    if error:
        return error
    try:
        owner, _token = _identity(request)
    except Exception:
        return 503, headers, {"error": "authentication_unavailable"}
    if not owner:
        return 401, headers, {"error": "authentication_required"}
    body = _read_json(request)
    if type(body) is not dict or set(body) != {"positions"}:
        return 400, headers, {"error": "invalid_request"}
    try:
        _positions(body["positions"])
    except (TypeError, ValueError):
        return 400, headers, {"error": "invalid_positions"}
    try:
        return 200, headers, read_company_snapshot(body["positions"])
    except Exception:
        # No filenames, source bodies, token or selected companies in logs/errors.
        return 503, headers, {"error": "company_snapshot_unavailable"}


class handler(BaseHTTPRequestHandler):
    def send_result(self, result):
        status, headers, body = _encode_result(result)
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        self.send_result(snapshot_request(self))

    def do_OPTIONS(self):
        error, headers = _origin_result(self)
        self.send_result(error or (200, headers, {}))

    def do_GET(self):
        error, headers = _origin_result(self, method_allowed=False)
        self.send_result(error or (405, headers, {"error": "method_not_allowed"}))

    def log_message(self, _format, *_args):
        return
