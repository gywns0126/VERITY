"""
Estate Alerts — 알림 피드 조회 + 마킹.

GET    /api/estate/alerts?since=ISO&category=gei,catalyst&severity=high,mid
POST   /api/estate/alerts  { action:"mark_read", alert_id }
POST   /api/estate/alerts  { action:"mark_hidden", alert_id }
POST   /api/estate/alerts  { action:"mark_all_read" }

알림 자체는 service_role 또는 백엔드 워커가 estate_alerts 에 INSERT 하고,
사용자는 SELECT + mark 만 가능 (RLS 로 격리).
"""
from http.server import BaseHTTPRequestHandler
import json
import logging
import os
from collections import defaultdict
from urllib.parse import parse_qs, urlparse

import requests

import api.supabase_client as sb
from api.cors_helper import resolve_origin

_logger = logging.getLogger(__name__)

VALID_CATEGORIES = frozenset(["gei", "catalyst", "regulation", "anomaly"])
VALID_SEVERITIES = frozenset(["high", "mid", "low"])


def _verify_jwt(auth_header: str):
    if not auth_header.startswith("Bearer "):
        return None
    return sb.verify_jwt(auth_header[7:])


class handler(BaseHTTPRequestHandler):
    def _set_cors(self):
        origin = resolve_origin(self.headers.get("Origin", ""))
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(200); self._set_cors(); self.end_headers()

    def _json(self, status, payload):
        self.send_response(status); self._set_cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def _err(self, status, code, message):
        self._json(status, {"error": code, "message": message})

    def _auth(self):
        user_id = _verify_jwt(self.headers.get("Authorization", ""))
        if not user_id:
            self._err(401, "unauthorized", "Valid Supabase access token required")
            return None, None
        return user_id, self.headers.get("Authorization", "")[7:]

    # ── GET ────────────────────────────────────────────────
    def do_GET(self):
        user_id, token = self._auth()
        if not user_id:
            return
        params = parse_qs(urlparse(self.path).query)
        since = params.get("since", [""])[0].strip()
        cat_csv = params.get("category", [""])[0].strip()
        sev_csv = params.get("severity", [""])[0].strip()

        q = {"select": "id,user_id,category,severity,title,body,gu,source_url,occurred_at",
             "order": "occurred_at.desc",
             "limit": "200"}
        if since:
            q["occurred_at"] = f"gte.{since}"
        if cat_csv:
            cats = [c for c in cat_csv.split(",") if c in VALID_CATEGORIES]
            if cats:
                q["category"] = f"in.({','.join(cats)})"
        if sev_csv:
            sevs = [s for s in sev_csv.split(",") if s in VALID_SEVERITIES]
            if sevs:
                q["severity"] = f"in.({','.join(sevs)})"

        try:
            alerts = sb.select("estate_alerts", q, user_jwt=token) or []
            alert_ids = [a["id"] for a in alerts]
            marks = []
            if alert_ids:
                marks = sb.select("estate_alert_marks", {
                    "user_id": f"eq.{user_id}",
                    "alert_id": f"in.({','.join(alert_ids)})",
                    "select": "alert_id,status,marked_at",
                }, user_jwt=token) or []
            mark_map = {m["alert_id"]: m for m in marks}
            # status 결합: marked 있으면 그 status, 없으면 'new'
            for a in alerts:
                m = mark_map.get(a["id"])
                a["status"] = m["status"] if m else "new"
            self._json(200, {"alerts": alerts})
        except Exception as e:
            _logger.error("alerts fetch failed: %s", e)
            self._err(500, "fetch_failed", "alerts fetch failed")

    # ── POST (마킹) ─────────────────────────────────────────
    def do_POST(self):
        user_id, token = self._auth()
        if not user_id:
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length)) if length else {}
        except Exception:
            self._err(400, "invalid_body", "JSON body required")
            return
        action = body.get("action")

        try:
            if action == "mark_all_read":
                # 신규 알림 전체를 read 로 upsert
                fresh = sb.select("estate_alerts", {
                    "select": "id", "limit": "200", "order": "occurred_at.desc",
                }, user_jwt=token) or []
                for a in fresh:
                    sb.insert("estate_alert_marks", {
                        "user_id": user_id, "alert_id": a["id"], "status": "read",
                    }, user_jwt=token)
                self._json(200, {"ok": True, "marked": len(fresh)})
                return

            alert_id = body.get("alert_id")
            if not alert_id:
                self._err(400, "invalid_body", "alert_id required")
                return
            status = "hidden" if action == "mark_hidden" else "read"
            sb.insert("estate_alert_marks", {
                "user_id": user_id, "alert_id": alert_id, "status": status,
            }, user_jwt=token)
            self._json(200, {"ok": True, "status": status})
        except Exception as e:
            _logger.error("mark failed: %s", e)
            self._err(500, "mark_failed", "alert mark failed")
