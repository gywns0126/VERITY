# -*- coding: utf-8 -*-
"""dart_delisted_backfill — 상장 소멸 종목 분기 재무 백필 (생존 편향의 마지막 조각).

🚨 **왜 필요한가 — 가격만 채워선 생존 편향이 안 풀린다.**
PR #312(PIT 유니버스) + #314(소멸 종목 가격 415/415) 로 "그 시점 실제 상장 목록"과
"사라진 종목의 가격"은 확보했다. 그런데 실측(2026-08-08):

    생존 종목 2,793 → 분기 펀더멘털 보유 1,914 (68.5%)
    사라진 종목  415 → 분기 펀더멘털 보유    3 ( 0.7%)   ← 여기

`dart_quarterly_snapshots` 를 채우는 백필 빌더가 **현 상장 유니버스**를 순회하기 때문이다.
그래서 망한 회사는 점수가 아예 안 매겨지고, 백테스트 단면에서 통째로 빠진다. 가격을
아무리 채워도 **점수가 없으면 그 종목은 표본에 못 들어온다** — 생존 편향이 가격층에서
펀더멘털층으로 옮겨갔을 뿐이다.

결과적으로 "F-Score 낮은 종목이 못 간다" 를 검정할 때 **실제로 상장폐지된 최악의 사례들이
저점수 분위에서 빠진다**. 어떤 팩터든 실제보다 순해 보이고, 그 숫자를 믿고 실전에 가면
정확히 그 차이만큼 잃는다.

**되는 이유**: DART 는 상장폐지 이후에도 과거 공시를 보유한다. 실호출 표본 20종 중
14종(70%)이 소멸 직전 2개 연도 재무에 응답했다.

작업량: 261종목 × 상장기간 연도 × 4분기 = 5,040 단위 (CFS→OFS fallback 포함 최대 ~10,080콜).
DART 일 한도 20,000 내 1일 완주 가능 ([[project_dart_api_2026_constraints]]).

스키마: `dart_batch_builder._append_quarterly_snapshots` 재사용 — 기존 jsonl 과 **동일 스키마**.
       별 파일을 만들지 않는다(소비자 분기 방지).
🚨 RULE 4: 산출 = `data/dart_quarterly_snapshots.jsonl` + 진행 파일. 워크플로 git add 정합 의무.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from api.config import DATA_DIR
    _DATA = DATA_DIR
except Exception:  # 단독 실행 폴백
    _DATA = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")

DELIST_PATH = os.path.join(_DATA, "kr_delisting.json")
PROGRESS_PATH = os.path.join(_DATA, ".dart_delisted_backfill_progress.json")

REPRT_CODES = ("11011", "11014", "11012", "11013")   # 연간 · 3Q · 반기 · 1Q
MIN_YEAR = 2019          # 백테스트 구간 2020~ 이므로 YoY 위해 2019 부터
_WORKERS = 8


def _targets() -> List[Tuple[str, int, int]]:
    """[(ticker, 시작연도, 종료연도)] — 소멸 종목 중 펀더멘털 미보유분만.

    제외(우선주/스팩/리츠/ETF)는 백테스트 모듈의 사전 고정 규칙을 그대로 쓴다 —
    두 곳에서 따로 정의하면 유니버스가 어긋난다.
    """
    from api.quant.backtest.kr_fundamental import (
        exclusion_reason, load_fundamentals, load_names,
    )
    try:
        with open(DELIST_PATH, encoding="utf-8") as f:
            dl = json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return []
    latest = str(dl.get("as_of"))
    first_seen = dl.get("first_seen") or {}
    last_seen = dl.get("last_seen") or {}
    names = load_names()
    have = load_fundamentals()
    out: List[Tuple[str, int, int]] = []
    for t, last in last_seen.items():
        if str(last) == latest:
            continue                                  # 아직 상장 중
        if exclusion_reason(t, names.get(t)):
            continue
        if t in have:
            continue                                  # 이미 시계열 보유
        try:
            y0 = max(MIN_YEAR, int(str(first_seen.get(t, last))[:4]) - 1)
            y1 = int(str(last)[:4])
        except (TypeError, ValueError):
            continue
        if y1 >= y0:
            out.append((t, y0, y1))
    return sorted(out)


def _load_progress() -> Dict[str, Any]:
    try:
        with open(PROGRESS_PATH, encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_progress(p: Dict[str, Any]) -> None:
    tmp = PROGRESS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=1)
    os.replace(tmp, PROGRESS_PATH)


def collect(max_units: int = 6000, workers: int = _WORKERS) -> Dict[str, Any]:
    """(연도, reprt_code) 단위로 순회하며 소멸 종목 재무를 백필한다.

    멱등: 완료한 (year, reprt) 키를 진행 파일에 남겨 재실행 시 건너뛴다.
    🚨 응답 0건은 **실패가 아니다** — 그 시점에 이미 폐지돼 제출 자체가 없을 수 있다.
       0건을 실패로 세면 재시도 루프에 갇힌다. 사실만 기록한다.
    """
    from api.builders.dart_batch_builder import _append_quarterly_snapshots
    from api.collectors.dart_fundamentals import fetch_dart_fundamentals_batch

    targets = _targets()
    if not targets:
        return {"status": "no_targets"}
    prog = _load_progress()
    done: Set[str] = set(prog.get("done_keys") or [])

    years = sorted({y for _, y0, y1 in targets for y in range(y0, y1 + 1)})
    units = 0
    appended_total = 0
    per_key: List[Dict[str, Any]] = []
    t0 = time.time()

    for year in years:
        alive = [t for t, y0, y1 in targets if y0 <= year <= y1]
        if not alive:
            continue
        for reprt in REPRT_CODES:
            key = f"{year}:{reprt}"
            if key in done:
                continue
            if units + len(alive) > max_units:
                _save_progress({"done_keys": sorted(done), "targets": len(targets),
                                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00",
                                                            time.localtime(time.time() + 9 * 3600))})
                return {"status": "paused_quota", "units": units,
                        "appended": appended_total, "per_key": per_key,
                        "elapsed_sec": round(time.time() - t0, 1)}
            funds = fetch_dart_fundamentals_batch(
                alive, max_workers=workers, bsns_year=str(year), reprt_code=reprt)
            got = {t: v for t, v in (funds or {}).items()
                   if v and any(v.get(k) is not None for k in
                                ("roa", "debt_ratio", "current_ratio",
                                 "gross_margin", "asset_turnover"))}
            n_app = 0
            if got:
                for v in got.values():
                    v.setdefault("reprt_code", reprt)
                n_app = _append_quarterly_snapshots({
                    "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00",
                                                  time.localtime(time.time() + 9 * 3600)),
                    "fundamentals": got,
                })
            units += len(alive)
            appended_total += n_app
            done.add(key)
            per_key.append({"key": key, "tried": len(alive),
                            "with_data": len(got), "appended": n_app})
            sys.stderr.write(f"[dart_delisted_backfill] {key} 시도 {len(alive)} · "
                             f"데이터 {len(got)} · append {n_app}\n")
            sys.stderr.flush()

    _save_progress({"done_keys": sorted(done), "targets": len(targets),
                    "completed": True,
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00",
                                                time.localtime(time.time() + 9 * 3600))})
    return {"status": "ok", "units": units, "appended": appended_total,
            "targets": len(targets), "per_key": per_key,
            "elapsed_sec": round(time.time() - t0, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-units", type=int, default=6000)
    ap.add_argument("--workers", type=int, default=_WORKERS)
    ap.add_argument("--plan-only", action="store_true")
    a = ap.parse_args()
    if a.plan_only:
        tg = _targets()
        units = sum((y1 - y0 + 1) * len(REPRT_CODES) for _, y0, y1 in tg)
        print(f"[dart_delisted_backfill] 대상 {len(tg)}종목 · 단위 {units:,}")
        return 0
    r = collect(a.max_units, a.workers)
    if r.get("status") == "no_targets":
        print("[dart_delisted_backfill] 대상 없음 (kr_universe_pit 먼저 실행)", file=sys.stderr)
        return 0
    print(f"[dart_delisted_backfill] {r['status']} · 단위 {r['units']:,} · "
          f"append {r['appended']:,} · {r['elapsed_sec']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
