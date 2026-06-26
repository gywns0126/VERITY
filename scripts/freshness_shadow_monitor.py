#!/usr/bin/env python3
"""신선도 SLA 매니페스트 데이터주도 모니터 — SHADOW 모드 (관측-only, 알람 없음).

data/freshness_sla.json 의 각 스트림을 schedule-aware 로 검사 → 나이 vs max_age 위반 여부를
data/metadata/freshness_observations.jsonl 에 1 run 1 record append. **텔레그램·severity 무관여.**

목적 = 매시간 CI 에서 실 데이터로 모니터 동작을 관측 → false-alarm 0 확인 후 알람 flip(별도 단계).
shadow 이므로 ts 추출 불완전(NO_TS)이어도 무해 — 오히려 어느 스트림이 안 잡히는지 드러냄(커버리지 진단).

ts 추출 = per-stream `ts_field`(매니페스트, 옵션) 우선 → 없으면 fallback 체인 →
list/jsonl 은 마지막 요소/라인. schedule 게이팅 = weekday(주말 skip)/market_hours(장중만).
commit-age 미사용(cron_health 체크아웃 shallow). owner=local 은 heartbeat 가 별도 커버 → skip.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime, time, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.config import DATA_DIR, now_kst  # noqa: E402

KST = timezone(timedelta(hours=9))
MANIFEST = os.path.join(DATA_DIR, "freshness_sla.json")
OBS_PATH = os.path.join(DATA_DIR, "metadata", "freshness_observations.jsonl")

TS_FALLBACK = ["collected_at", "generated_at", "updated_at", "as_of", "last_checked_at"]
TS_FALLBACK_NESTED = [("_meta", "generated_at"), ("_meta", "collected_at")]
# list/jsonl 요소에서 ts 찾을 후보 필드
ITEM_TS = ["date", "collected_at", "created_at", "ts", "ts_utc", "published", "pub_date", "as_of"]


def _extract_ts(obj, ts_field: str | None):
    """dict/list 에서 ISO ts 문자열 추출. ts_field 우선(dotted) → fallback."""
    if ts_field:
        cur = obj
        for k in ts_field.split("."):
            if isinstance(cur, dict):
                cur = cur.get(k)
            else:
                cur = None
                break
        if isinstance(cur, str):
            return cur
    if isinstance(obj, dict):
        for k in TS_FALLBACK:
            if isinstance(obj.get(k), str):
                return obj[k]
        for a, b in TS_FALLBACK_NESTED:
            m = obj.get(a)
            if isinstance(m, dict) and isinstance(m.get(b), str):
                return m[b]
    if isinstance(obj, list) and obj:
        last = obj[-1]
        if isinstance(last, dict):
            for k in ITEM_TS:
                if isinstance(last.get(k), str):
                    return last[k]
    return None


def _load_any(path: str):
    """json 또는 jsonl(마지막 라인) 로드."""
    try:
        if path.endswith(".jsonl"):
            last = None
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        last = line
            return json.loads(last) if last else None
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _age_minutes(iso: str) -> float | None:
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=KST)
    return (now_kst() - t.astimezone(KST)).total_seconds() / 60


def _schedule_active(schedule: str, now: datetime) -> bool:
    """이 스트림을 지금 검사해야 하나(자연 정체 구간 skip)."""
    wd = now.weekday()  # 0=월 ~ 6=일
    if schedule == "market_hours":
        return wd < 5 and time(9, 0) <= now.timetz().replace(tzinfo=None) <= time(15, 40)
    if schedule == "weekday":
        return wd < 5
    return True  # always / weekly / monthly


def build_observations() -> dict:
    now = now_kst()
    m = _load_any(MANIFEST) or {}
    rows = []
    for s in m.get("streams", []):
        if s.get("owner") == "local":
            continue  # heartbeat 가 별도 커버
        f = s.get("file", "")
        sched = s.get("schedule", "always")
        if "*" in f:  # glob v0 skip
            rows.append({"id": s["id"], "status": "skip_glob"})
            continue
        if not _schedule_active(sched, now):
            rows.append({"id": s["id"], "status": "skip_schedule", "schedule": sched})
            continue
        path = os.path.join(DATA_DIR, f)
        if not os.path.exists(path):
            rows.append({"id": s["id"], "status": "missing"})
            continue
        obj = _load_any(path)
        ts = _extract_ts(obj, s.get("ts_field"))
        if not ts:
            rows.append({"id": s["id"], "status": "no_ts"})
            continue
        age_m = _age_minutes(ts)
        if age_m is None:
            rows.append({"id": s["id"], "status": "bad_ts", "ts": ts})
            continue
        maxm = s.get("max_age_minutes")
        would_alarm = bool(maxm and age_m > maxm)
        rows.append({
            "id": s["id"], "status": "checked", "schedule": sched,
            "age_min": round(age_m, 1), "max_age_min": maxm,
            "would_alarm": would_alarm, "criticality": s.get("criticality"),
        })
    alarms = [r["id"] for r in rows if r.get("would_alarm")]
    return {
        "observed_at": now.isoformat(),
        "mode": "shadow",
        "checked": sum(1 for r in rows if r["status"] == "checked"),
        "would_alarm_ids": alarms,
        "rows": rows,
    }


def main() -> int:
    obs = build_observations()
    os.makedirs(os.path.dirname(OBS_PATH), exist_ok=True)
    with open(OBS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(obs, ensure_ascii=False) + "\n")
    print(f"[freshness-shadow] checked={obs['checked']} "
          f"would_alarm={obs['would_alarm_ids'] or '없음'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
