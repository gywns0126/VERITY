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
import urllib.parse

GH_REPO = os.environ.get("GH_DISPATCH_REPO", "gywns0126/VERITY")
GH_PAT = os.environ.get("GH_DISPATCH_PAT", "")
CRON_SECRET = os.environ.get("CRON_SECRET", "")

# Quick과 같은 GitHub concurrency group(`verity-data-write`)의 실제 workflow 파일.
# tests/test_dispatch_mode_payload.py가 워크플로 전체를 열거해 이 집합의 drift를 차단한다.
DATA_WRITE_WORKFLOWS = {
    "bond_etf_analysis.yml",
    "broker_guide.yml",
    "daily_analysis.yml",
    "daily_analysis_full.yml",
    "export_trade_daily.yml",
    "kis_token_refresh.yml",
    "reports_v2_cron.yml",
}


def _dispatch(event_type: str, payload: dict | None = None) -> tuple[int, str]:
    """🚨 2026-08-20 — `client_payload` 추가. 종전에는 event_type 만 보냈다.

    그래서 `daily_analysis_full` 워크플로의 모드 분기(`github.event.schedule` 문자열 매칭)가
    **dispatch 경로에서 항상 빈 문자열**을 받아 `else → mode=full` 로 흘렀다.
    KST 06:30(UTC 21:30) 슬롯은 `full_us`(미장 전체) 여야 하는데 매번 `full`(상위 10개)로
    돌아, 미장 수집이 49종목 중 10개로 잘리고 있었다 — 실측 2026-08-20 06:30 run
    `[5.71] 미장 데이터 수집 — 상위 10개`. Finnhub 커버가 29/49 로 보이던 원인이다.

    워크플로 주석이 이미 경고했던 함정이다(*"cron 문자열 매칭이라 … else 로 흘러간다"*).
    dispatch 는 schedule 이 아니므로 그 매칭이 **구조적으로** 성립하지 않는다.
    """
    if not GH_PAT:
        return 500, "GH_DISPATCH_PAT not set"
    url = f"https://api.github.com/repos/{GH_REPO}/dispatches"
    _body: dict = {"event_type": event_type}
    if payload:
        _body["client_payload"] = payload
    body = json.dumps(_body).encode("utf-8")
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
    # 🚨 2026-08-22 — `== 0` 에서 `< 5` 로 넓혔다. **자기 계측 실험이다.**
    #   Vercel cron 은 0,5,7,10,… 에만 예약돼 있어 **1~4 분에는 예약 자체가 없다**.
    #   따라서 이 창이 새로 잡는 것은 오직 **:00 예약분이 늦게 실행된 경우**뿐이다.
    #   즉 이 한 줄이 가설을 가른다:
    #     실행 밀림이 원인 → 1~4 분에 run 이 생기고 정시 발화율이 오른다
    #     호출 자체가 결손  → 아무 변화 없다 (되돌린다)
    #   🚨 보정 슬롯(5/35)과 겹치지 않는다(`< 5` 이므로). 겹쳐도 `_ran_recently` 가 막는다.
    #   🚨 종전에 내가 "창 확대는 효과 0" 이라 단정했는데 그 근거가 **순환**이었다 —
    #      발화한 run 의 분 분포로 발화 못 한 호출을 추론했다. 그래서 실험으로 되돌린다.
    if minute % 30 < 5:
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
    # daily_analysis_full KR 마감 — UTC 07:50 = KST 16:50 Mon-Fri
    # 🚨 2026-08-07 — 07:07 → 07:50 이동 (.github/workflows/daily_analysis_full.yml 과 쌍).
    #   universe_scan(06:30 시작, 실측 49~66분)이 같은 concurrency 그룹을 점유하는 동안
    #   daily_full 이 대기로 들어가고, 제3 워크플로 도착 시 밀려나 취소된다.
    #   실측 08-07: universe_scan 06:30→07:24 · daily_full 07:07 대기 · Export Trade
    #   07:16 도착 → daily_full 취소 = 당일 장 마감 분석 누락.
    #   이 매핑을 안 옮기면 Vercel fallback 이 옛 시각으로 쏴 충돌이 재현된다.
    if hour == 7 and minute == 50 and is_weekday:
        events.append("daily_analysis_full")
    # daily_analysis_full US 마감 — UTC 21:30 Tue-Fri = KST 06:30 Wed-Sat
    # 🚨 2026-08-20 — 이 슬롯은 **full_us**(미장 전체)다. dispatch 는 `github.event.schedule`
    #   이 비어 워크플로가 모드를 못 가리므로 payload 로 명시한다. 안 실으면 else 로 흘러
    #   `full`(미장 상위 10개)이 되고, 미장 마감 분석이 통째로 얕아진다.
    if hour == 21 and minute == 30 and py_wd in (1, 2, 3, 4):
        events.append(("daily_analysis_full", {"mode": "full_us"}))
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


# ── 보정 슬롯 (2026-08-20 신설) ────────────────────────────────────────────
# 🚨 실측: 30분 수집기가 하루 27~36회만 돈다(기대 48). 워크플로 실패는 **0건** —
#   전부 success 다. 즉 고장난 것은 수집기가 아니라 **dispatch 호출 자체가 안 온 것**이다.
#   macro_collect 와 crypto_collect 의 일별 횟수가 거의 같다(28/28·32/32·21/21)는 점이
#   근거다. 둘은 같은 호출에서 나가므로, 함께 빠졌다면 빠진 것은 호출 하나다.
#
# 🚨 "매칭 창을 넓히자"(`minute % 30 <= 2`)는 **효과가 없다** — 늦게 오는 게 아니라
#   안 오는 것이다. 발화한 run 의 분(minute) 분포가 30분:55 · 00분:41 로 촘촘하고
#   31/01분은 4건뿐이라 지터 가설이 서지 않는다. 그래서 창이 아니라 **재시도**다.
#
# 정규 슬롯(0/30분) 5분 뒤에 한 번 더 기회를 준다. 단 무조건 쏘지 않는다 —
# 정규 슬롯이 이미 돌았으면 건너뛴다. 정상일 때 추가 런 0, 누락일 때만 메운다.
_BACKUP_SLOTS: dict[int, list[tuple[str, str]]] = {
    5: [("macro_collect", "macro_collect.yml"), ("crypto_collect", "crypto_collect.yml")],
    35: [("macro_collect", "macro_collect.yml"), ("crypto_collect", "crypto_collect.yml")],
}
# 정규↔보정 간격 5분 + 여유. 정규 슬롯 간격이 30분이라 20분이면 앞 슬롯만 본다.
_BACKUP_WINDOW_MIN = 20


def _resolve_backup_events(now_utc: datetime) -> list[tuple[str, str]]:
    """보정 슬롯 후보 — (event_type, workflow_file). 순수 함수(I/O 0).

    `_resolve_events` 를 건드리지 않는다. 그쪽은 미장 `full_us` 경로가 지나가는
    자리이고 단위 테스트가 직접 호출하므로, 네트워크가 필요한 판단을 섞지 않는다.
    """
    out = list(_BACKUP_SLOTS.get(now_utc.minute, []))
    # KSD 일일 수집 — GH 05:47 cron 누락을 05:55, 06:15 두 번 확인한다.
    # 최근 run 이 있으면 handler 의 _ran_recently 가 건너뛰므로 정상일 추가 실행은 0이다.
    if (now_utc.hour, now_utc.minute) in ((5, 55), (6, 15)):
        out.append(("dividend_ksd", "dividend_ksd.yml"))
    return out


def _ran_recently(workflow_file: str, minutes: int, now_utc: datetime) -> bool:
    """해당 워크플로가 최근 `minutes` 분 안에 만들어진 run 을 갖는가.

    🚨 판단 실패(토큰 없음·API 오류·형식 이상) = **False** 를 돌려준다. 즉 fail-open 이라
    한 번 더 쏜다. 이 슬롯의 목적이 누락 보정이므로, 모를 때는 메우는 쪽이 맞다.
    중복 발화의 대가는 수집 런 1회(timeout 5분·멱등)뿐이고, 반대 방향의 대가는
    신선도 갭이다.
    """
    if not GH_PAT:
        return False
    url = (f"https://api.github.com/repos/{GH_REPO}/actions/workflows/"
           f"{urllib.parse.quote(workflow_file)}/runs?per_page=1")
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {GH_PAT}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "verity-vercel-dispatch/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            runs = (json.loads(resp.read().decode("utf-8")) or {}).get("workflow_runs") or []
        if not runs:
            return False
        created = str(runs[0].get("created_at") or "")
        if created.endswith("Z"):
            created = created[:-1] + "+00:00"
        age_min = (now_utc - datetime.fromisoformat(created)).total_seconds() / 60
        return 0 <= age_min <= minutes
    except Exception:
        return False


def _data_write_group_busy(now_utc: datetime, max_age_minutes: int = 360) -> bool:
    """공용 데이터 쓰기 그룹에 최근 미완료 run이 있으면 True.

    GitHub concurrency는 그룹당 대기 run을 하나만 유지한다. Full이 공용 쓰기 잠금을 오래
    점유할 때 Quick을 대기열에 넣으면 뒤늦게 온 Bond/ETF 등이 그 Quick을 교체 취소한다.
    그래서 그룹이 바쁠 때는 Quick을 만들지 않고 다음 시간에 다시 확인한다. 조회 실패도
    True로 처리한다. 6시간보다 오래된 비정상 run은 영구 차단을 막기 위해 제외한다.
    """
    if not GH_PAT:
        return True
    url = f"https://api.github.com/repos/{GH_REPO}/actions/runs?per_page=100"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {GH_PAT}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "verity-vercel-dispatch/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            runs = (json.loads(resp.read().decode("utf-8")) or {}).get("workflow_runs") or []
        for run in runs:
            if str(run.get("status") or "") == "completed":
                continue
            workflow_file = str(run.get("path") or "").rsplit("/", 1)[-1]
            if workflow_file not in DATA_WRITE_WORKFLOWS:
                continue
            created = str(run.get("created_at") or "")
            if created.endswith("Z"):
                created = created[:-1] + "+00:00"
            try:
                age_min = (now_utc - datetime.fromisoformat(created)).total_seconds() / 60
            except (TypeError, ValueError):
                return True
            if 0 <= age_min <= max_age_minutes:
                return True
        return False
    except Exception:
        return True


def _split_event(evt) -> tuple[str, dict | None]:
    """`_resolve_events` 항목을 (event_type, payload) 로 가른다.

    🚨 2026-08-20 — 항목은 문자열이거나 (event_type, payload) 튜플이다. 튜플을 그대로
    `_dispatch` 에 넘기면 event_type 이 리스트로 직렬화돼 GitHub 이 422 를 낸다.

    핸들러 안에 있던 2줄을 함수로 뺐다. 이유 = **이 경로는 아직 한 번도 실행된 적이 없다**.
    페이로드를 싣는 슬롯은 UTC 21:30 화~금 하나뿐이라, 8/20 수정 이후 첫 발화가
    8/21 06:30 KST 다. 그때 처음 도는 코드를 테스트가 못 만지는 상태로 두지 않는다
    (기존 테스트 4건은 전부 **소스 문자열 grep** 이라 이 분기가 지워져도 통과한다).
    """
    if isinstance(evt, tuple):
        return evt[0], evt[1]
    return evt, None


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
        for raw_evt in events:
            evt, _payload = _split_event(raw_evt)
            if evt == "daily_analysis_quick" and _data_write_group_busy(now_utc):
                results.append({"event": evt, "payload": _payload, "status": 200,
                                "detail": "busy-skip: verity-data-write 점유 중, 다음 시간 재확인"})
                continue
            status, detail = _dispatch(evt, _payload)
            results.append({"event": evt, "payload": _payload,
                            "status": status, "detail": detail})

        # 보정 슬롯 — 정규 슬롯이 이미 돌았으면 건너뛴다(추가 런 0).
        # 🚨 건너뛴 것도 결과에 남긴다. 조용히 지나가면 보정이 작동하는지 영영 모른다
        #    (건수 0 + 성공 종료 = 결손 은폐. 이 저장소가 반복해서 당한 형태다).
        for evt, wf_file in _resolve_backup_events(now_utc):
            if _ran_recently(wf_file, _BACKUP_WINDOW_MIN, now_utc):
                results.append({"event": evt, "payload": None, "status": 200,
                                "detail": f"backup-skip: 정규 슬롯 {_BACKUP_WINDOW_MIN}분 내 발화 확인"})
                continue
            status, detail = _dispatch(evt, None)
            results.append({"event": evt, "payload": None, "status": status,
                            "detail": f"backup-fire: {detail}"})

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
