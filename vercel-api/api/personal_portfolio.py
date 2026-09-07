"""Read the authenticated user's saved operator review. No writes or orders."""
from http.server import BaseHTTPRequestHandler
import json
import os
import re
import time
import requests

try:
    import api.supabase_client as sb
except ModuleNotFoundError:
    import supabase_client as sb


def load_personal_portfolio(token):
    if not token:
        return 401, {"error": "authentication_required"}
    uid = sb.verify_jwt(token)
    if not uid or not re.fullmatch(r"[0-9a-fA-F-]{36}", uid):
        return 401, {"error": "authentication_required"}
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    bucket = os.environ.get("OPERATOR_BUCKET", "verity-reports")
    if not key or not base:
        return 503, {"error": "private_storage_unavailable"}
    path = f"_operator/personal/{uid}/latest.json"
    try:
        response = requests.get(f"{base}/storage/v1/object/{bucket}/{path}",
            headers={"apikey": key, "Authorization": "Bearer " + key},
            params={"cacheNonce": str(time.time_ns())}, timeout=8)
        if response.status_code == 404:
            return 404, {"error": "personal_review_not_published"}
        if response.status_code == 400 and response.json().get("code") == "NoSuchKey":
            return 404, {"error": "personal_review_not_published"}
        if response.status_code != 200:
            return 502, {"error": "private_storage_read_failed"}
        if len(response.content) > 200_000:
            return 502, {"error": "invalid_personal_review"}
        data = response.json()
        if data.get("schema") != "personal-portfolio-view-v1" or data.get("owner_id") != uid:
            return 502, {"error": "invalid_personal_review"}
        return 200, data
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return 502, {"error": "private_storage_read_failed"}


class handler(BaseHTTPRequestHandler):
    def respond(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "private, no-store, max-age=0")
        self.send_header("Vary", "Authorization, Origin")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        # Bearer-only read endpoint; no cookies or credentialed CORS.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def do_OPTIONS(self):
        self.respond(200, {})

    def do_GET(self):
        auth = self.headers.get("Authorization", "")
        token = auth[7:].strip() if auth.startswith("Bearer ") else ""
        self.respond(*load_personal_portfolio(token))

    def do_POST(self):
        self.respond(405, {"error": "read_only_endpoint"})
