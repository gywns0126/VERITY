# -*- coding: utf-8 -*-
"""dart_latest_pl_backfill — **각 티커의 최신 분기 1개**에 손익 3종 소급. 2026-08-22 신설.

## 왜 신설인가 (기존 도구를 왜 못 쓰나)

`dart_revenue_backfill`(8/19)은 **매출 결손만** 대상으로 한다(`have_rev` 필터).
그 결과 지금 revenue 는 최신 분기 81.6% 까지 올라왔는데 **operating_profit 은 0.0%** 다
— 스냅샷에 그 필드를 싣기 시작한 게 오늘(8/22)이라 과거 행에는 아예 없다.
게다가 그 도구는 그룹 단위 `done_keys` 로 재개를 관리해서, 이미 완료 표시된 그룹은
매출이 차면 다시 건드리지 않는다. 즉 **영업이익은 영영 안 채워진다.**

🚨 **왜 영업이익이 따로 중요한가.** net_income 은 이미 87.4% 있는데 그것만으로는
본업을 못 본다 — 021820(세원정공) 연간 순이익 488억은 지분법 230 + 금융수익 135 가
섞인 값이고, 같은 기간 영업이익은 170억, **최근 분기는 −6.7억 적자**다.
순이익만 보면 "PER 2 초저평가" 로 읽히고 적자 전환이 안 보인다.

## 대상 — 최신 분기 1개만 (RULE 13: 열거 먼저)

전 기간 소급은 155,228행 = 8일치 쿼터다. 적자 전환 감지에 필요한 것은 **최신 분기**이고,
과거 분기는 정기 배치가 알아서 쌓는다(실측: 8/19 수리 후 3일에 7,525행, 신규분 100% 충족).
그래서 티커마다 **가장 최근 (reprt_code, fiscal_year) 하나**만 재조회한다.

    실측 2026-08-22 — 티커 2,806 · 최신 분기 손익 보유율
      revenue 81.6% · net_income 87.4% · **operating_profit 0.0%**

## 쿼터

티커 1개당 1단위. 2,806 단위 ≈ 일 20,000 의 14%.
`--max-units` 로 상한을 두고 `data/.dart_latest_pl_progress.json` 에 진도를 남겨 재개한다.

🚨 RULE 4 — 진도 파일은 어느 워크플로에도 등록돼 있지 않다. **수동 실행 전용**이며
산출·진도 모두 수동 커밋한다. cron 승격 시 해당 yml 의 `git add` 에 두 경로 명시가 선행이다.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from api.builders.dart_batch_builder import _append_quarterly_snapshots  # noqa: E402
from api.collectors.dart_fundamentals import fetch_dart_fundamentals_batch  # noqa: E402

SNAP = os.path.join(_ROOT, "data", "dart_quarterly_snapshots.jsonl")
PROGRESS = os.path.join(_ROOT, "data", ".dart_latest_pl_progress.json")
CHUNK = 40


def plan() -> List[Tuple[str, int, List[str]]]:
    """→ [(reprt_code, fiscal_year, [ticker...])] — 각 티커의 **최신 분기 1개**.

    🚨 operating_profit 이 이미 있는 (티커, rc, fy) 는 제외한다 — 재개 시 자연 축소.
    """
    grid: Dict[Tuple[str, str], Dict[int, str]] = collections.defaultdict(dict)
    have_op: set = set()
    for line in open(SNAP, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        tk, rc = r.get("ticker"), r.get("reprt_code")
        qe = str(r.get("quarter_end") or "")
        if not tk or not rc or len(qe) < 4 or not qe[:4].isdigit():
            continue
        fy = int(qe[:4])
        grid[(str(tk), str(rc))][fy] = qe
        if isinstance(r.get("operating_profit"), (int, float)):
            have_op.add((str(tk), str(rc), fy))

    best: Dict[str, Tuple[str, str, int]] = {}
    for (tk, rc), ys in grid.items():
        fy = max(ys)
        latest = ys[fy]
        if tk not in best or latest > best[tk][0]:
            best[tk] = (latest, rc, fy)

    groups: Dict[Tuple[str, int], List[str]] = collections.defaultdict(list)
    for tk, (_lq, rc, fy) in best.items():
        if (tk, rc, fy) in have_op:
            continue
        groups[(rc, fy)].append(tk)
    return [(rc, fy, sorted(tks)) for (rc, fy), tks in
            sorted(groups.items(), key=lambda x: -len(x[1]))]


def _load() -> Dict[str, Any]:
    if os.path.exists(PROGRESS):
        try:
            with open(PROGRESS, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    return {"done_keys": [], "units_done": 0, "appended_total": 0}


def _save(p: Dict[str, Any]) -> None:
    tmp = PROGRESS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PROGRESS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-units", type=int, default=3000, help="이번 run 최대 (티커) 단위")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.0)
    a = ap.parse_args()

    groups = plan()
    total = sum(len(t) for _rc, _fy, t in groups)
    print(f"[latest_pl] 그룹 {len(groups)} · 잔여 {total:,}단위 "
          f"(DART 일 20,000 의 {total/200:.1f}%)")
    for rc, fy, tks in groups[:6]:
        print(f"    reprt={rc} year={fy}  {len(tks):,}종목")
    if a.dry_run:
        print("[latest_pl] dry-run — 호출 0")
        return 0
    if not total:
        print("[latest_pl] 잔여 0 — 완료")
        return 0

    p = _load()
    done = set(p.get("done_keys") or [])
    units = 0
    t0 = time.time()
    for rc, fy, tks in groups:
        if f"{rc}:{fy}" in done:
            continue
        for i in range(0, len(tks), CHUNK):
            if units >= a.max_units:
                print(f"[latest_pl] --max-units {a.max_units} 도달 — 중단(재개 가능)")
                _save(p)
                return 0
            chunk = tks[i:i + CHUNK]
            funds = fetch_dart_fundamentals_batch(
                chunk, max_workers=6, bsns_year=str(fy), reprt_code=rc) or {}
            # 🚨 정식 DART 분만 — yfinance fallback 은 분기 시계열에 부적합(기존 백필 규약 동일)
            dart_funds = {tk: f for tk, f in funds.items()
                          if str(f.get("source", "")).startswith("DART")
                          and (f.get("total_assets") or 0) > 0}
            with_op = sum(1 for f in dart_funds.values()
                          if isinstance(f.get("operating_profit"), (int, float)))
            appended = _append_quarterly_snapshots({
                "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
                "fundamentals": dart_funds,
            }) if dart_funds else 0
            units += len(chunk)
            p["units_done"] = int(p.get("units_done", 0)) + len(chunk)
            p["appended_total"] = int(p.get("appended_total", 0)) + appended
            print(f"[latest_pl] {rc}/{fy} {i+len(chunk)}/{len(tks)} · DART정식 {len(dart_funds)}"
                  f" · 영업이익보유 {with_op} · append {appended}"
                  f" · 누적 {units:,} · {time.time()-t0:.0f}s", flush=True)
            _save(p)
            if a.sleep:
                time.sleep(a.sleep)
        done.add(f"{rc}:{fy}")
        p["done_keys"] = sorted(done)
        _save(p)
    print(f"[latest_pl] 완료 — 단위 {units:,} · append 누적 {p.get('appended_total')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
