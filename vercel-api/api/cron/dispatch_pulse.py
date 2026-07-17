"""
Vercel Cron → GitHub Actions repository_dispatch (시각별 multi-event)

배경: GH Actions schedule trigger 가 high-load 시 silent skip. Vercel Cron (Pro 매분 안정) 으로 우회.

호출: GET /api/cron/dispatch_pulse (매분, Vercel cron `* * * * *`)
시각별 발화 events:
  - price_pulse        — 매 5분 (2026-05-13 매분 → 5분 완화, commit 부피 1/5)
  - daily_realtime     — 매 30분 (5/12 hotfix, ~9m run, brain 분석)
  - macro_collect      — 매 30분 24/7 (2026-07-01, GH schedule silent-skip 회피, daily_realtime 패턴)
  - daily_analysis_quick — 매시 :07 (시간당 1회 quick 분석)
  - reports_v2         — UTC 13:07 매일 (1일 1회 reports)
  - hourly_pulse       — 한국장 4슬롯 + 미장 3슬롯 (DST 자동, 2026-05-12 · 17:00 장후 제거 2026-07-17)

필요 env:
  - GH_DISPATCH_PAT: GitHub PAT (Contents: Read and write)
  - 옵션 CRON_SECRET: Vercel Cron 인증
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
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
    events: list[str] = []
    minute = now_utc.minute
    hour = now_utc.hour
    py_wd = now_utc.weekday()  # 0=Mon..6=Sun
    is_weekday = py_wd <= 4    # Mon-Fri
    is_sun_thu = py_wd in (6, 0, 1, 2, 3)

    # price_pulse — 2026-05-13 매분 → 매 5분 완화 (commit 부피 1/5, 사이트 체감 거의 동일).
    # 2026-05-16 시장 시간 가드 추가 — 토/일/장 마감 발화 차단 (KIS 5분 폭주 사고 후 점검).
    # KR session = 평일 KST 08:30-15:40 (UTC: hour 23 + min >= 30 Sun-Thu, 또는 hour 0-6 Mon-Fri)
    # US session = 평일 ET 09:30-16:00 (UTC: hour 13:30-20:00 Mon-Fri, DST 변동 약간 무시)
    if minute % 5 == 0:
        kr_pre = (hour == 23 and minute >= 30 and is_sun_thu)
        kr_main = ((hour <= 5) or (hour == 6 and minute <= 40)) and is_weekday
        us_main = (
            (hour == 13 and minute >= 30) or
            (14 <= hour <= 19) or
            (hour == 20 and minute == 0)
        ) and is_weekday
        if kr_pre or kr_main or us_main:
            events.append("price_pulse")

    # daily_realtime — 매 30분 (매 5분은 9분 run 과 부적합 + 텔레그램/KIS/AI 호출 연속 발생).
    # price_pulse 가 매분 가격 fresh 담당하므로 daily_realtime 은 분석 갱신 (30분 충분).
    # 5/11→5/12 새벽 11~15 run/hr 폭증 사고 학습.
    if minute % 30 == 0:
        kr_pre = (hour == 23 and is_sun_thu)        # KST 08:xx Sun-Thu
        kr_session = (0 <= hour <= 7 and is_weekday)  # KST 09-16 평일
        us_session = (13 <= hour <= 20 and is_weekday)  # KST 22-익05 평일
        if kr_pre or kr_session or us_session:
            events.append("daily_realtime")

    # macro_collect — 매 30분 24/7 (글로벌 매크로/환율/금리, freshness_sla schedule="always").
    # 2026-07-01: GH schedule '*/30' silent-skip 으로 macro 신선도 8h 갭 → schedule 폐기·dispatch 단일통로
    #   (daily_realtime 패턴). 미장/FX 는 야간(KST)에도 움직이므로 세션 게이트 없이 항상.
    if minute % 30 == 0:
        events.append("macro_collect")
        # crypto_collect — 매 30분 24/7 (크립토 시세·파생, freshness_sla schedule="always", SLA 90분).
        # 2026-07-12: GH schedule '5,35' silent-skip 으로 최대 3~4h 갭 → dispatch 단일통로 이전(macro 패턴).
        events.append("crypto_collect")

    # rss_scout(뉴스속보) / dart_catalyst(공시알림) — 시장시간 P0(SLA 90 / 120분).
    # 2026-07-12: GH schedule silent-skip 실측(뉴스 15분→실제 1~2.75h · 공시 30분→실제 3~4h > SLA)
    #   → Vercel dispatch 30분 이전(crypto/macro 패턴). 원 수집 창 보존:
    #   뉴스 = 평일 UTC 0-23(KR+US·저녁) · 공시 = 평일 UTC 0-9(KR 장중~마감 KST 09-18).
    if minute % 30 == 0 and is_weekday:
        events.append("rss_scout")
        if hour <= 9:
            events.append("dart_catalyst_pulse")

    # daily_analysis quick — 매시 :07, KR 장외 (UTC 8-15 평일) OR 저녁 (UTC 16-22 Sun-Thu)
    if minute == 7:
        if (8 <= hour <= 15 and is_weekday) or (16 <= hour <= 22 and is_sun_thu):
            events.append("daily_analysis_quick")

    # reports_v2 — UTC 13:07 매일
    if hour == 13 and minute == 7:
        events.append("reports_v2")

    # 2026-05-18 — daily_analysis_full + universe_scan Vercel fallback
    # GitHub Actions schedule cron silent miss/delay 회피 (5/16~5/18 universe_scan 3일 silent miss,
    # 5/18 daily_full 16:07 → 20:11 KST 4h delay). Vercel Cron = 신뢰 ↑.
    # daily_analysis_full KR 마감 — UTC 07:07 = KST 16:07 Mon-Fri
    if hour == 7 and minute == 7 and is_weekday:
        events.append("daily_analysis_full")
    # daily_analysis_full US 마감 — UTC 21:30 Tue-Fri = KST 06:30 Wed-Sat
    if hour == 21 and minute == 30 and py_wd in (1, 2, 3, 4):
        events.append("daily_analysis_full")
    # universe_scan KR 마감 직후 — UTC 06:30 = KST 15:30 Mon-Fri
    if hour == 6 and minute == 30 and is_weekday:
        events.append("universe_scan")

    # hourly_pulse — 시간별 정기 시황 (사용자 spam 호소 후속, 2026-05-12)
    # 한국장 4슬롯 (KST 09:30/11:30/14:30/15:30) + 미장 3슬롯 (ET 09:30/11:30/16:00, DST 자동).
    # 매크로 fact-check: project_market_info_density_map (★★★★★ 윈도우 정합).
    if _is_hourly_pulse_slot(now_utc):
        events.append("hourly_pulse")

    return events


def _is_us_dst(now_utc: datetime) -> bool:
    """미국 동부 DST: 3월 둘째 일요일 ~ 11월 첫째 일요일 (UTC 일자 기준 hourly 매처에 충분)."""
    y = now_utc.year
    march1 = datetime(y, 3, 1, tzinfo=timezone.utc)
    second_sun_mar = march1 + timedelta(days=((6 - march1.weekday()) % 7) + 7)
    nov1 = datetime(y, 11, 1, tzinfo=timezone.utc)
    first_sun_nov = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)
    return second_sun_mar <= now_utc < first_sun_nov


def _is_hourly_pulse_slot(now_utc: datetime) -> bool:
    # KST = UTC + 9 (DST 없음)
    kst = now_utc + timedelta(hours=9)
    kst_wd = kst.weekday()  # 0=Mon..6=Sun
    if kst_wd <= 4:  # 평일 한국장 슬롯
        kr_slots = [(9, 30), (11, 30), (14, 30), (15, 30)]  # 17:00 장후 시간외 제거(사용자 "장후 싫다", 2026-07-17)
        if (kst.hour, kst.minute) in kr_slots:
            return True

    # ET = UTC - 4 (DST) or UTC - 5
    et_offset = -4 if _is_us_dst(now_utc) else -5
    et = now_utc + timedelta(hours=et_offset)
    et_wd = et.weekday()
    if et_wd <= 4:  # 평일 미장 슬롯
        us_slots = [(9, 30), (11, 30), (16, 0)]
        if (et.hour, et.minute) in us_slots:
            return True

    return False


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

# deploy: 2026-07-03 — 6/27 이후 vercel-api 미배포 해소 (macro_collect dispatch 사망 + thesis 404 + rights fix 미적용).
# 원인 = push HEAD 가 vercel-api 밖 → ignoreCommand skip (6/27 동일 클래스). HEAD 를 vercel-api 변경으로 올려 배포.
