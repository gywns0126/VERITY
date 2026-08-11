# -*- coding: utf-8 -*-
"""dart_quarterly_gap_backfill — 분기 재무 백필이 **시도조차 안 한** 종목을 메운다.

2026-08-11 신설. PM 지시 "전부 다 채워".

## 진단 (고치기 전에 셌다)

`data/.dart_quarterly_backfill_progress.json` 의 `universe` 는 **1,533종목**이었다
(`universe_builder.build_extended_universe("KR", target_size=…, apply_hard_floor=True)` 산출).
백테스트 유니버스(우선주·스팩·리츠·ETF 제외)는 **2,899종목**이다.

```
백테스트 유니버스 2,899 · 패널 보유 2,100 · 결손 799
  결손 중 기존 백필 universe 에 있던 것 = 4  ← 즉 **시도조차 안 했다**
  결손 중 corp_code 보유 794 / 미보유 5
```

실호출 표본 40건(2023 사업보고서): **29건 채워짐(72%)** · 11건 `status 013`(공시 없음).
→ 채울 수 있는 종목 추정 **약 575 / 794**. 나머지는 DART 에 정기공시가 없다.

## 설계 — 기존 백필 기계를 그대로 쓴다

`dart_quarterly_backfill_builder` 는 이미 paced·resumable·청크마다 진도 저장이다.
새로 짜지 않고 **진도 파일과 universe 만 갈아끼운다**:

- 진도 파일 = `data/.dart_quarterly_gap_backfill_progress.json` (**별 파일**)
  🚨 기존 진도(`done=true`, 62,853 단위 완료)를 건드리면 완료 상태가 날아간다.
- universe = 결손 794종목
- 산출은 **같은** `dart_quarterly_snapshots.jsonl` 에 append (스키마 단일 출처 유지)

## 쿼터 ([[project_dart_api_2026_constraints]] DART 20,000/일)

794종목 × 기간수. `DART_BACKFILL_YEARS=7`(2019~2025) 기준 약 31기간 = **~24,600 단위**.
CFS 실패 시 OFS 재시도가 있어 실 콜은 그보다 많다. **하루에 안 끝난다** —
`--max-units` 로 일일 상한을 두고 여러 날에 나눠 재개한다.

🚨 RULE 4 — 신규 진도 파일 `data/.dart_quarterly_gap_backfill_progress.json` 은
   **어느 워크플로에도 등록돼 있지 않다.** `dart_quarterly_backfill.yml:78` 은 특정 경로
   (`git add data/.dart_quarterly_backfill_progress.json data/dart_quarterly_snapshots.jsonl`)
   만 add 하므로 broad add 로 자동 포함되지 **않는다**.
   → 이 스크립트는 **수동 실행 전용**이며 진도 파일은 수동 커밋한다.
   cron 으로 승격할 때는 그 yml 의 `git add` 에 이 경로를 추가하는 것이 선행 조건이다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import List, Set

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

GAP_PROGRESS = os.path.join(_ROOT, "data", ".dart_quarterly_gap_backfill_progress.json")
PANEL = os.path.join(_ROOT, "data", "metadata", "kr_fundamental_panel.jsonl")
MAPPING = os.path.join(_ROOT, "data", "mapping.json")


def missing_tickers() -> List[str]:
    """백테스트 유니버스(제외 필터 적용) − 패널 보유. corp_code 있는 것만."""
    from api.quant.backtest.kr_fundamental import (exclusion_reason, load_names,
                                                   load_universe)
    names = load_names()
    uni: Set[str] = set()
    for _, tks in load_universe():
        for t in tks:
            if not exclusion_reason(t, names.get(t)):
                uni.add(t)
    have: Set[str] = set()
    try:
        with open(PANEL, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        have.add(json.loads(line)["ticker"])
                    except (json.JSONDecodeError, KeyError):
                        pass
    except OSError:
        pass
    mapping = json.load(open(MAPPING, encoding="utf-8"))
    return sorted(t for t in (uni - have)
                  if isinstance(mapping.get(t), str) and len(mapping[t]) == 8)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-units", type=int, default=16000,
                    help="이 실행에서 처리할 최대 종목·기간 단위 (DART 일 한도 보호)")
    ap.add_argument("--years", type=int, default=7, help="백필 연수 (7 = 2019~2025)")
    a = ap.parse_args()

    os.environ["DART_BACKFILL_YEARS"] = str(a.years)
    os.environ.setdefault("DART_BACKFILL_CHUNK", "120")

    import api.builders.dart_quarterly_backfill_builder as B

    tks = missing_tickers()
    if not tks:
        print("[gap_backfill] 결손 0 — 할 일 없음")
        return 0

    # 🚨 진도 파일·universe 만 갈아끼운다. 기존 완료 진도는 손대지 않는다.
    B.PROGRESS_PATH = GAP_PROGRESS
    B._build_universe = lambda: tks                       # noqa: SLF001
    # run 당 상한을 우리가 관리한다(1회 dispatch = 하루치)
    B.RUN_UNIT_CAP = a.max_units
    B.RUN_DEADLINE_S = 10 ** 9

    print(f"[gap_backfill] 결손 {len(tks):,}종목 · 연수 {a.years} · 이번 실행 상한 {a.max_units:,}단위",
          flush=True)
    t0 = time.time()
    rc = B.main()
    try:
        p = json.load(open(GAP_PROGRESS, encoding="utf-8"))
        print(f"[gap_backfill] 진도 {p.get('units_done'):,}/{p.get('units_total'):,} "
              f"· done={p.get('done')} · {time.time() - t0:.0f}s")
        if not p.get("done"):
            print("[gap_backfill] 미완 — 내일 같은 명령으로 재개(진도 보존)", file=sys.stderr)
    except OSError:
        pass
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
