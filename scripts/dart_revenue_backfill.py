# -*- coding: utf-8 -*-
"""dart_revenue_backfill — 기존 분기 스냅샷에 **매출만** 소급 적재. PM 승인 2026-08-19.

## 왜

`revenue_acceleration` 의 2Q 연속가속 보강이 watch 448/448 전량 미작동이었다.
원인은 신호가 아니라 **입력**: 수집기가 매출을 파싱해 `asset_turnover = rev/ta` 까지
쓰고도 스냅샷에 안 실었다(2026-08-19 수리, `dart_batch_builder`). 수리는 **신규 수집분**
부터 적용되므로, 과거 147,703행은 여전히 매출이 없다 → 커버리지 0%.

이 스크립트가 그 과거분을 메운다. **새 데이터를 캐는 게 아니라 버려진 필드를 되받는다.**

## 대상 — 전부가 아니라 판정에 필요한 만큼만 (RULE 13: 열거 먼저)

보강은 `quarterly_revenue` 3점이면 판정한다(성장률 2개 → 가속 비교 1회).
조립 규약(`api/utils/quarterly_revenue`)은 **같은 reprt_code 를 연도만 바꿔** 뽑으므로,
티커마다 "가장 최근 분기 × 최근 3개 회계연도" 만 있으면 된다.

    실측 (data/dart_quarterly_snapshots.jsonl 기준)
      티커 2,804 · 재조회 그룹 31개 · **총 7,664 단위**
      최신분기 분포 = 11012(반기) 1,428 · 11013(1Q) 921 · 11011(연간) 421 · 11014(3Q) 34
      최대 그룹 = (11012, 2026) 1,398종목
      완료 시 3점 확보 = **2,340 티커 (83.5%)**

## 쿼터 ([[project_dart_api_2026_constraints]] DART 20,000/일)

7,664 단위 = 쿼터의 38.3%. 🚨 단 `fetch_dart_fundamentals_batch` 는 CFS 실패 시 OFS
재시도가 있어 **실 호출은 단위 수보다 많다**. 그래서 기본 상한을 두고(`--max-units`)
청크마다 진도를 저장해 여러 run 으로 나눌 수 있게 한다.

🚨 RULE 4 — 진도 파일 `data/.dart_revenue_backfill_progress.json` 은 **어느 워크플로에도
등록돼 있지 않다.** 이 스크립트는 **수동 실행 전용**이며 산출·진도 모두 수동 커밋한다.
cron 승격 시 해당 yml 의 `git add` 에 두 경로를 명시하는 것이 선행 조건이다.
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

SNAP = os.path.join(_ROOT, "data", "dart_quarterly_snapshots.jsonl")
PROGRESS = os.path.join(_ROOT, "data", ".dart_revenue_backfill_progress.json")
YEARS_PER_TICKER = 3          # 조립 MIN_POINTS 와 동일 — 더 캐지 않는다
CHUNK = 120                   # dart_quarterly_backfill_builder 와 동일 청크 크기


def plan() -> List[Tuple[str, int, List[str]]]:
    """→ [(reprt_code, fiscal_year, [ticker...])] — 재조회 그룹.

    스냅샷에 **이미 존재하는** (티커, 분기, 연도) 만 대상으로 한다. 없는 기간을 새로 캐면
    그건 다른 작업(gap backfill)이고 쿼터 성격도 다르다.
    """
    grid: Dict[Tuple[str, str], Dict[int, str]] = collections.defaultdict(dict)
    have_rev: set = set()
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
        if isinstance(r.get("revenue"), (int, float)) and r["revenue"] > 0:
            have_rev.add((str(tk), str(rc), fy))

    best: Dict[str, Tuple[str, str]] = {}
    for (tk, rc), ys in grid.items():
        latest = max(ys.values())
        if tk not in best or latest > best[tk][0]:
            best[tk] = (latest, rc)

    groups: Dict[Tuple[str, int], List[str]] = collections.defaultdict(list)
    for tk, (_lq, rc) in best.items():
        for fy in sorted(grid[(tk, rc)], reverse=True)[:YEARS_PER_TICKER]:
            if (tk, rc, fy) in have_rev:
                continue          # 이미 매출 보유 = 재조회 불필요 (재개 시 자연 축소)
            groups[(rc, fy)].append(tk)
    # 큰 그룹부터 — 중단되어도 커버리지가 빨리 오른다
    return [(rc, fy, sorted(tks)) for (rc, fy), tks in
            sorted(groups.items(), key=lambda x: -len(x[1]))]


def _load_progress() -> Dict[str, Any]:
    if os.path.exists(PROGRESS):
        try:
            with open(PROGRESS, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    return {"done_keys": [], "units_done": 0, "appended_total": 0}


def _save_progress(p: Dict[str, Any]) -> None:
    tmp = PROGRESS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PROGRESS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-units", type=int, default=8000,
                    help="이번 run 에서 처리할 최대 (티커×기간) 단위. DART 쿼터 보호.")
    ap.add_argument("--dry-run", action="store_true", help="계획만 출력, 호출 0")
    ap.add_argument("--sleep", type=float, default=0.0, help="청크 간 대기(초)")
    a = ap.parse_args()

    groups = plan()
    total = sum(len(t) for _rc, _fy, t in groups)
    print(f"[rev_backfill] 그룹 {len(groups)} · 잔여 단위 {total:,} "
          f"(DART 일 쿼터 20,000 의 {total/200:.1f}%)")
    for rc, fy, tks in groups[:8]:
        print(f"    reprt={rc} year={fy}  {len(tks):,}종목")
    if len(groups) > 8:
        print(f"    … 외 {len(groups)-8}그룹")
    if a.dry_run:
        print("[rev_backfill] dry-run — 호출 0")
        return 0
    if not total:
        print("[rev_backfill] 잔여 0 — 이미 완료")
        return 0

    from api.builders.dart_batch_builder import _append_quarterly_snapshots
    from api.collectors.dart_fundamentals import fetch_dart_fundamentals_batch

    p = _load_progress()
    done = set(tuple(k) if isinstance(k, list) else k for k in p.get("done_keys") or [])
    units = 0
    t0 = time.time()
    for rc, fy, tks in groups:
        if f"{rc}:{fy}" in done:
            continue
        for i in range(0, len(tks), CHUNK):
            if units >= a.max_units:
                print(f"[rev_backfill] --max-units {a.max_units} 도달 — 중단(재개 가능)")
                _save_progress(p)
                return 0
            chunk = tks[i:i + CHUNK]
            funds = fetch_dart_fundamentals_batch(
                chunk, max_workers=6, bsns_year=str(fy), reprt_code=rc) or {}
            # 정식 DART 분만 — yfinance fallback 은 분기 시계열에 부적합(기존 백필과 동일 규약)
            dart_funds = {tk: f for tk, f in funds.items()
                          if str(f.get("source", "")).startswith("DART")
                          and (f.get("total_assets") or 0) > 0}
            with_rev = sum(1 for f in dart_funds.values()
                           if isinstance(f.get("revenue"), (int, float)) and f["revenue"] > 0)
            appended = _append_quarterly_snapshots({
                "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
                "fundamentals": dart_funds,
            }) if dart_funds else 0
            units += len(chunk)
            p["units_done"] = int(p.get("units_done", 0)) + len(chunk)
            p["appended_total"] = int(p.get("appended_total", 0)) + appended
            print(f"[rev_backfill] {rc}/{fy} {i+len(chunk)}/{len(tks)} "
                  f"· DART정식 {len(dart_funds)} · 매출보유 {with_rev} · append {appended} "
                  f"· 누적단위 {units:,} · {time.time()-t0:.0f}s", flush=True)
            _save_progress(p)
            if a.sleep:
                time.sleep(a.sleep)
        done.add(f"{rc}:{fy}")
        p["done_keys"] = sorted(done)
        _save_progress(p)

    print(f"[rev_backfill] 완료 — 단위 {units:,} · append {p.get('appended_total', 0):,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
