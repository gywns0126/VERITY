#!/usr/bin/env python3
"""로컬 맥 하트비트 — 로컬 레이크 의존 잡의 생존 신호를 data/local_lake_health.json 으로 발행.

목적 (신선도 거버넌스 Tier 1 — 로컬 맥 SPOF 가시화):
  event_study / kr_flow / 가격레이크 등은 `~/VERITY_data_lake/*.duckdb` 의존 → CI(GitHub Actions)가
  못 닿음. 이 맥이 꺼지면 그 산출물이 무알람 동결. CI 는 맥 생존을 직접 못 봄.
  → 이 맥에서 도는 잡이 주기적으로 heartbeat_at + 로컬 아티팩트 나이를 발행 → CI cron_health 가
    heartbeat_at 나이로 "로컬 맥 N일 정지(SPOF)" 알람 가능.

발행 경로: 로컬 상태 파일 → gh contents API → main/data/local_lake_health.json.
일간 launchd는 레이크에 설치한 독립 사본을 실행하며 공유 작업트리를 변경하지 않는다.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def now_kst():
    return datetime.now(timezone(timedelta(hours=9)))

LAKE = os.path.expanduser("~/VERITY_data_lake")
OUT = os.environ.get("VERITY_HEARTBEAT_OUTPUT", os.path.join(DATA_DIR, "local_lake_health.json"))
EVENT_STUDY_PATH = os.environ.get("VERITY_EVENT_STUDY_PATH", os.path.join(DATA_DIR, "event_study.json"))

REPO = "gywns0126/VERITY"
REMOTE_PATH = "data/local_lake_health.json"  # CI cron_health 가 체크아웃 로컬파일로 읽음

# (name, 경로, kind) — kind=mtime: 파일 수정시각 / kind=json:<field>: JSON 내부 타임스탬프
# 🚨 2026-08-09 — `us_prices.duckdb` 를 추적에서 뺐다. 갱신 스케줄이 없어 43일 멈춰 있던
#   레이크이고, US 가격 정본은 이제 CI 산출 `us_chart_history`(월 1회) 로 옮겼다. 폴백으로만
#   남은 파일을 계속 stale 로 세면 "고칠 수 없는 빨간불" 만 남는다. 대신 그 자리에 새 정본의
#   로컬 캐시(us_event_study.json)를 넣어 **전달 경로가 살아 있는지**를 본다.
TRACKED = [
    ("kr_prices_lake",     os.path.join(LAKE, "kr_prices.duckdb"),                          "mtime"),
    ("kr_flow_parquet",    os.path.join(LAKE, "kr_flow_observations.parquet"),             "mtime"),
    ("prediction_trail",   os.path.join(LAKE, "smallcap_corner_prediction_trail.jsonl"),  "mtime"),
    ("us_event_study",     os.path.join(LAKE, "us_event_study.json"),
     "json:_meta.generated_at"),
    ("event_study",        EVENT_STUDY_PATH,  "json:_meta.generated_at"),
]

# 아티팩트별 stale 임계(시간). 로컬 잡 자연 cadence 기준 — 초과 시 status=stale.
STALE_H = {
    "kr_prices_lake": 24 * 9,
    "kr_flow_parquet": 24 * 10,
    "prediction_trail": 24 * 10,
    "us_event_study": 24 * 45,   # 소스가 월 1회(매월 2일) — 한 회차 건너뛰어도 여유
    "event_study": 24 * 10,
}


def _mtime_iso(path: str) -> str | None:
    try:
        ts = os.path.getmtime(path)
    except OSError:
        return None
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, timezone.utc).astimezone(now_kst().tzinfo).isoformat()


def _json_field(path: str, dotted: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    cur = d
    for k in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur if isinstance(cur, str) else None


def _age_hours(iso: str | None) -> float | None:
    if not iso:
        return None
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    now = now_kst()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=now.tzinfo)
    return round((now - dt).total_seconds() / 3600, 1)


def build() -> dict:
    now = now_kst()
    arts = []
    for name, path, kind in TRACKED:
        last = _mtime_iso(path) if kind == "mtime" else _json_field(path, kind.split(":", 1)[1])
        age = _age_hours(last)
        thr = STALE_H.get(name)
        if last is None:
            status = "missing"
        elif thr is not None and age is not None and age > thr:
            status = "stale"
        else:
            status = "fresh"
        arts.append({"name": name, "last_updated": last, "age_hours": age,
                     "stale_threshold_hours": thr, "status": status})
    return {
        "heartbeat_at": now.isoformat(),
        "host": os.uname().nodename,
        "_meta": {
            "purpose": "로컬 맥 SPOF 가시화. CI cron_health 가 heartbeat_at 나이로 맥 정지 알람.",
            "note": "로컬 레이크(.duckdb) 의존 산출물 생존 신호. heartbeat_at stale = 맥 꺼짐 의심.",
        },
        "artifacts": arts,
    }


def _publish_to_main() -> bool:
    """gh api contents PUT 로 main 직접 발행 (클론·dirty-tree rebase 회피, gh repo scope).
    CI cron_health 가 체크아웃 로컬파일로 읽어 heartbeat_at 나이 = 맥 SPOF 판정."""
    # launchd 는 homebrew PATH 가 없을 수 있음 — 2026-07-04 plist PATH 축소로 gh
    # FileNotFoundError 가 4주 침묵 실패(하트비트 30일 stale P0). which + 절대경로 폴백.
    gh = shutil.which("gh") or next(
        (p for p in ("/opt/homebrew/bin/gh", "/usr/local/bin/gh") if os.path.exists(p)), None)
    if not gh:
        print("[heartbeat] main 발행 실패: gh 미발견 — launchd PATH 에 homebrew 경로 필요")
        return False
    with open(OUT, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()
    endpoint = f"repos/{REPO}/contents/{REMOTE_PATH}"
    for attempt in range(3):
        try:
            current = subprocess.run(
                [gh, "api", endpoint + "?ref=main", "--jq", ".sha"],
                capture_output=True, text=True, timeout=30,
            )
            sha = current.stdout.strip()
            if current.returncode or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
                raise RuntimeError("main 파일 SHA 조회 실패")
            args = [gh, "api", "--method", "PUT", endpoint,
                    "-f", "message=chore(heartbeat): 로컬 맥 생존 신호 갱신 [skip ci]",
                    "-f", "branch=main", "-f", f"content={content_b64}", "-f", f"sha={sha}"]
            result = subprocess.run(args, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                print("[heartbeat] main 발행 완료 (gh api contents)")
                return True
            raise RuntimeError("main 파일 발행 실패")
        except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
            print(f"[heartbeat] 발행 시도 {attempt + 1}/3 실패: {exc}")
        if attempt < 2:
            time.sleep(2 * (attempt + 1))
    return False


def main() -> int:
    health = build()
    os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(health, f, ensure_ascii=False, indent=2)
    os.replace(tmp, OUT)
    bad = [a["name"] for a in health["artifacts"] if a["status"] != "fresh"]
    print(f"[heartbeat] {OUT} — {len(health['artifacts'])} 아티팩트, "
          f"stale/missing={bad or '없음'}")
    if "--publish" in sys.argv and not _publish_to_main():
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
