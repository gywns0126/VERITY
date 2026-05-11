"""
Vercel Cron → GitHub Actions repository_dispatch (시각별 multi-event)

배경: GH Actions schedule trigger 가 high-load 시 silent skip. Vercel Cron (Pro 매분 안정) 으로 우회.

호출: GET /api/cron/dispatch_pulse (매분, Vercel cron `* * * * *`)
시각별 발화 events:
  - price_pulse        — 매분 (지수+보유+추천 가격, ~30s run)
  - daily_realtime     — 매 5분 (UTC minute % 5 == 0, ~9m run, brain 분석)
  - daily_analysis_quick — 매시 :07 (시간당 1회 quick 분석)
  - reports_v2         — UTC 13:07 매일 (1일 1회 reports)

필요 env:
  - GH_DISPATCH_PAT: GitHub PAT (Contents: Read and write)
  - 옵션 CRON_SECRET: Vercel Cron 인증
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
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


def _resolve_events(now_utc: datetime) -> list[str]:
    """현재 UTC 시각 기반 발화 event_type 목록 결정.

    Python weekday: 0=Mon..6=Sun. Cron weekday: 0=Sun..6=Sat.
    """
    events = ["price_pulse"]  # 매분 항상 (지수+보유+추천 ~30s)
    minute = now_utc.minute
    hour = now_utc.hour
    py_wd = now_utc.weekday()  # 0=Mon..6=Sun
    is_weekday = py_wd <= 4    # Mon-Fri
    is_sun_thu = py_wd in (6, 0, 1, 2, 3)

    # daily_realtime — 매 5분, KR 장중 (UTC 23 + 0-7 평일) OR 미장 (UTC 13-20 평일)
    if minute % 5 == 0:
        kr_pre = (hour == 23 and is_sun_thu)        # KST 08:xx (UTC 23 = KR 다음날) Sun-Thu
        kr_session = (0 <= hour <= 7 and is_weekday)  # KST 09-16 평일
        us_session = (13 <= hour <= 20 and is_weekday)  # KST 22-익05 평일
        if kr_pre or kr_session or us_session:
            events.append("daily_realtime")

    # daily_analysis quick — 매시 :07, KR 장외 (UTC 8-15 평일) OR 저녁 (UTC 16-22 Sun-Thu)
    if minute == 7:
        if (8 <= hour <= 15 and is_weekday) or (16 <= hour <= 22 and is_sun_thu):
            events.append("daily_analysis_quick")

    # reports_v2 — UTC 13:07 매일
    if hour == 13 and minute == 7:
        events.append("reports_v2")

    return events


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Vercel Cron 은 자동으로 Authorization: Bearer <CRON_SECRET> 헤더 송신
        if CRON_SECRET:
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {CRON_SECRET}":
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":"unauthorized"}')
                return

        now_utc = datetime.now(timezone.utc)
        events = _resolve_events(now_utc)
        results = []
        for evt in events:
            status, detail = _dispatch(evt)
            results.append({"event": evt, "status": status, "detail": detail})

        all_ok = all(200 <= r["status"] < 300 for r in results)
        out = {
            "now_utc": now_utc.isoformat(),
            "repo": GH_REPO,
            "events": results,
        }
        self.send_response(200 if all_ok else 502)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(out).encode("utf-8"))
