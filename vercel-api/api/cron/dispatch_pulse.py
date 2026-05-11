"""
Vercel Cron → GitHub Actions repository_dispatch trigger

배경: GH Actions 의 1분 cron 이 high-load 시 silent skip (확정 결함).
       Vercel Cron (Pro 플랜 1분 안정) → 본 endpoint → GitHub API repository_dispatch
       → price_pulse.yml workflow_run trigger. schedule 의존 0.

필요 env (Vercel project settings):
  - GH_DISPATCH_PAT: GitHub PAT (Contents: Read and write)
  - 옵션 CRON_SECRET: Vercel Cron 인증 (있으면 검증)

호출:
  GET /api/cron/dispatch_pulse
  → POST https://api.github.com/repos/gywns0126/VERITY/dispatches
  → { "event_type": "price_pulse" }

Vercel cron 등록은 vercel.json crons.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler

import urllib.request
import urllib.error

GH_REPO = os.environ.get("GH_DISPATCH_REPO", "gywns0126/VERITY")
GH_PAT = os.environ.get("GH_DISPATCH_PAT", "")
CRON_SECRET = os.environ.get("CRON_SECRET", "")


def _dispatch(event_type: str) -> tuple[int, str]:
    if not GH_PAT:
        return 500, "GH_DISPATCH_PAT not set"
    url = f"https://api.github.com/repos/{GH_REPO}/dispatches"
    body = json.dumps({"event_type": event_type}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {GH_PAT}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "verity-vercel-dispatch/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status, "dispatched"
    except urllib.error.HTTPError as e:
        return e.code, f"http {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}"
    except Exception as e:
        return 500, f"error: {e}"


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Vercel Cron 은 자동으로 Authorization: Bearer <CRON_SECRET> 헤더 송신
        # CRON_SECRET 미설정 시 가드 X (rate limit 만 의존)
        if CRON_SECRET:
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {CRON_SECRET}":
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"unauthorized"}')
                return

        status, detail = _dispatch("price_pulse")
        out = {"status": status, "detail": detail, "repo": GH_REPO, "event": "price_pulse"}
        self.send_response(200 if 200 <= status < 300 else 502)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(out).encode("utf-8"))
