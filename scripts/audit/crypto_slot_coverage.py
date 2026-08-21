#!/usr/bin/env python3
"""30분 수집기 슬롯 커버리지 — 보정 슬롯 N=2 판정용 (2026-08-21 신설).

## 왜 스크립트인가

이 측정을 손으로 하다 **2026-08-20 에 없는 결함을 만들 뻔했다** — `gh run list -L 100` 이
100건에서 잘린 것을 "하루 18회(기대 48)" 로 읽었다. 분모를 절단당한 채 결론을 냈다.
판단을 사람에게 맡기지 않고 아래 세 함정을 코드가 막는다:

  🚨 ① 절단 자가탐지 — 가져온 가장 오래된 run 이 창 시작보다 **나중**이면 절단이다.
        그 경우 숫자를 내놓지 않고 **중단**한다(부분 데이터로 판정 금지).
  🚨 ② 부분일 처리 — 오늘을 볼 때 48 과 비교하지 않는다. **경과한 슬롯 수**와 비교한다.
  🚨 ③ 경계일 배제 — 보정 슬롯 배포는 **UTC 2026-08-20 15:19Z** 다. 그날은 전후가 섞이므로
        기본 판정 대상에서 뺀다(`--include-boundary` 로만 포함).
  🚨 ④ **정규/보정 귀속을 시각만으로 단정하지 않는다.** 배포 **전날**(8/20)에도 :05/:35 발화가
        9건 있었다 — 정규 슬롯의 지연 발화가 그 창에 들어온다. 그래서 이 스크립트는
        "보정" 이라 단정하지 않고 **`:05/:35 발화 수`를 배포 전 baseline 과 대조**한다.

## 판정

슬롯 = 매시 :00 · :30 (UTC). 정규 발화는 ±2분, 보정 발화는 +4~8분 안에 잡는다.
커버리지 = (정규 도달 + 보정이 메운 것) ÷ 경과 슬롯.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

# 🚨 UTC 다. 커밋은 KST 2026-08-21 00:11 이지만 그건 **UTC 2026-08-20 15:11** 이고
#   verity-api 배포 성공이 **UTC 2026-08-20 15:19:09** 이다.
#   처음에 KST 날짜를 그대로 써서 하루를 틀렸고, 그 탓에 경계일 가드가 엉뚱한 날을 막았다.
#   실측 대조로 잡았다 — :05/:35 발화가 08-09~08-19 매일 0 · 08-20 **9** · 08-21 **18**.
DEPLOY = datetime(2026, 8, 20, 15, 19, 9, tzinfo=timezone.utc)   # 보정 슬롯 배포(UTC)


def runs(wf: str, limit: int) -> list[datetime]:
    r = subprocess.run(["gh", "run", "list", "--workflow", wf, "-L", str(limit),
                        "--json", "createdAt"], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"gh 실패: {r.stderr[:200]}")
    return sorted(datetime.strptime(x["createdAt"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                  for x in json.loads(r.stdout or "[]"))


def baseline(wf: str, ts: list[datetime]) -> int | None:
    """배포 **이전** 날짜들의 :05/:35 발화 수 중앙값. 귀속 판단의 대조군."""
    from statistics import median
    per: dict = {}
    for t in ts:
        if t >= DEPLOY:
            continue
        per.setdefault(t.date(), 0)
        if t.minute in (5, 6, 7, 35, 36, 37):
            per[t.date()] += 1
    vals = [v for d, v in per.items() if d < DEPLOY.date()]   # 경계일 제외
    return int(median(vals)) if len(vals) >= 3 else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="UTC 기준 YYYY-MM-DD. 미지정 = 어제(UTC)")
    ap.add_argument("--workflows", default="crypto_collect.yml,macro_collect.yml")
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--include-boundary", action="store_true",
                    help="배포 경계일(2026-08-21)도 판정 대상에 포함")
    a = ap.parse_args()

    now = datetime.now(timezone.utc)
    day = (datetime.strptime(a.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
           if a.date else (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0))
    day = day.replace(hour=0, minute=0, second=0, microsecond=0)
    end = day + timedelta(days=1)

    if day.date() == DEPLOY.date() and not a.include_boundary:
        print(f"🚨 {day:%Y-%m-%d} 은 보정 슬롯 **배포 경계일**({DEPLOY:%H:%M}Z)이다 — 전후가 섞인다.")
        print("   판정 대상이 아니다. 다음 날을 보거나 --include-boundary 를 쓸 것.")
        return 2

    slots = [day + timedelta(minutes=30 * i) for i in range(48)]
    elapsed = [s for s in slots if s + timedelta(minutes=10) <= now]   # 보정 여유까지 지난 슬롯만
    if not elapsed:
        print(f"🚨 {day:%Y-%m-%d} 에 아직 경과한 슬롯이 없다.")
        return 2

    print(f"판정일 {day:%Y-%m-%d} (UTC) · 슬롯 48 중 경과 {len(elapsed)}"
          + ("  🚨 부분일 — 48 과 비교하지 않는다" if len(elapsed) < 48 else ""))
    bad = False
    for wf in [w.strip() for w in a.workflows.split(",") if w.strip()]:
        ts = runs(wf, a.limit)
        if not ts:
            print(f"  {wf}: run 0건"); bad = True; continue
        # 🚨 ① 절단 자가탐지
        if ts[0] > day:
            print(f"  🚨 {wf}: 절단 의심 — 가장 오래된 run {ts[0]:%m-%d %H:%M}Z 가 창 시작 "
                  f"{day:%m-%d %H:%M}Z 보다 나중이다. --limit 를 키울 것(현재 {a.limit}).")
            print("     🚨 부분 데이터로 판정하지 않는다 — 2026-08-20 에 이 오독으로 없는 결함을 만들 뻔했다.")
            bad = True
            continue
        reg = late = miss = 0
        missed_slots = []
        for s in elapsed:
            if any(abs((t - s).total_seconds()) <= 120 for t in ts):
                reg += 1
            elif any(240 <= (t - s).total_seconds() <= 480 for t in ts):
                late += 1          # 🚨 "보정" 이라 단정하지 않는다 — ④ 참조
            else:
                miss += 1
                missed_slots.append(f"{s:%H:%M}")
        cov = (reg + late) / len(elapsed) * 100
        base = baseline(wf, ts)
        print(f"  {wf:<20} 정시 {reg:>2} · +4~8분 {late:>2} · 미도달 {miss:>2} "
              f"→ 커버리지 {cov:.1f}%  (정시만 {reg/len(elapsed)*100:.1f}%)")
        print(f"    🚨 +4~8분 {late}건 — 배포 전 baseline 중앙 {base}건. "
              f"{'증가 = 보정 작동 정황' if base is not None and late > base else '증가 없음 = 보정 귀속 근거 부족'}")
        if missed_slots:
            print(f"    미도달 슬롯: {', '.join(missed_slots[:12])}"
                  + (" …" if len(missed_slots) > 12 else ""))
        if cov < 90:
            bad = True
    print("\n판정: " + ("🚨 커버리지 미달 또는 측정 불가 — 위 사유 확인" if bad
                        else "✅ 보정 슬롯이 정규 결손을 메우고 있다"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
