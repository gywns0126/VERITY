#!/usr/bin/env python3
"""로컬 맥 하트비트 — 로컬 레이크 의존 잡의 생존 신호를 data/local_lake_health.json 으로 발행.

목적 (신선도 거버넌스 Tier 1 — 로컬 맥 SPOF 가시화):
  event_study / kr_flow / 가격레이크 등은 `~/VERITY_data_lake/*.duckdb` 의존 → CI(GitHub Actions)가
  못 닿음. 이 맥이 꺼지면 그 산출물이 무알람 동결. CI 는 맥 생존을 직접 못 봄.
  → 이 맥에서 도는 잡이 주기적으로 heartbeat_at + 로컬 아티팩트 나이를 발행 → CI cron_health 가
    heartbeat_at 나이로 "로컬 맥 N일 정지(SPOF)" 알람 가능.

발행 경로: data/local_lake_health.json → (호출 잡이 commit+push) → VERITY-data + publish list.
호출: backup_irreplaceable.sh(launchd 주1) 동승. 더 잦은 비트는 v1(Blob 직발행) 후보.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.config import DATA_DIR, now_kst  # noqa: E402

LAKE = os.path.expanduser("~/VERITY_data_lake")
OUT = os.path.join(DATA_DIR, "local_lake_health.json")

# (name, 경로, kind) — kind=mtime: 파일 수정시각 / kind=json:<field>: JSON 내부 타임스탬프
TRACKED = [
    ("kr_prices_lake",     os.path.join(LAKE, "kr_prices.duckdb"),                          "mtime"),
    ("us_prices_lake",     os.path.join(LAKE, "us_prices.duckdb"),                          "mtime"),
    ("kr_flow_parquet",    os.path.join(LAKE, "kr_flow_observations.parquet"),             "mtime"),
    ("prediction_trail",   os.path.join(LAKE, "smallcap_corner_prediction_trail.jsonl"),  "mtime"),
    ("event_study",        os.path.join(DATA_DIR, "event_study.json"),  "json:_meta.generated_at"),
]

# 아티팩트별 stale 임계(시간). 로컬 잡 자연 cadence 기준 — 초과 시 status=stale.
STALE_H = {
    "kr_prices_lake": 24 * 9,
    "us_prices_lake": 24 * 14,
    "kr_flow_parquet": 24 * 10,
    "prediction_trail": 24 * 10,
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


def main() -> int:
    health = build()
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(health, f, ensure_ascii=False, indent=2)
    os.replace(tmp, OUT)
    bad = [a["name"] for a in health["artifacts"] if a["status"] != "fresh"]
    print(f"[heartbeat] {OUT} — {len(health['artifacts'])} 아티팩트, "
          f"stale/missing={bad or '없음'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
