#!/usr/bin/env python3
"""업비트 호가 슬리피지 이력 → 분위수 요약. 2026-08-16 신설.

TIDE 백테스트가 쓸 **비용 모델 상수**를 여기서 뽑는다. 평균이 아니라 분위수를 내는
이유는 청산이 하필 최악 구간에서 일어나기 때문이다 — p50 으로 백테스트하면 낙관 편향된다.

사용:
    python3 scripts/analyze_orderbook_slippage.py
    python3 scripts/analyze_orderbook_slippage.py --size 500000 --market KRW-BTC

🚨 표본이 얇으면(<30) 분위수를 내지 않고 그 사실을 신고한다. N=3 짜리 p95 는
   숫자만 그럴듯하고 의미가 없다.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from typing import Any, Dict, List

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(_ROOT, "data", "upbit_orderbook_slippage.jsonl")
MIN_N = 30      # 이 미만이면 분위수 산출 거부


def _pct(sorted_vals: List[float], q: float) -> float:
    """선형보간 없는 보수적 분위수 — 표본이 얇을 때 과대 매끄러움을 피한다."""
    if not sorted_vals:
        return float("nan")
    i = min(len(sorted_vals) - 1, int(round(q * (len(sorted_vals) - 1))))
    return sorted_vals[i]


def load(path: str) -> List[Dict[str, Any]]:
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        continue      # 깨진 줄은 건너뛰되 전체를 버리지 않는다
    except OSError:
        pass
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=None, help="특정 주문금액만")
    ap.add_argument("--market", default=None, help="특정 마켓만")
    a = ap.parse_args()

    rows = load(PATH)
    if not rows:
        print(f"이력 없음 — {PATH}")
        print("수집기는 crypto_collect 워크플로에 배선돼 있다. 첫 실행 후 다시 볼 것.")
        return 0

    ts = sorted(r.get("ts", "") for r in rows if r.get("ts"))
    print(f"# 업비트 호가 슬리피지 — 표본 {len(rows)}행")
    print(f"  기간 {ts[0][:16]} ~ {ts[-1][:16]}")
    print()

    # 스프레드 (우리 크기에서 실제 지배 비용)
    by_mkt = defaultdict(list)
    for r in rows:
        if a.market and r.get("market") != a.market:
            continue
        if r.get("spread_bps") is not None:
            by_mkt[r["market"]].append(float(r["spread_bps"]))
    print("## 스프레드 (bp) — 왕복 비용의 주 성분")
    for m, v in sorted(by_mkt.items()):
        v.sort()
        if len(v) < MIN_N:
            print(f"  {m:9} N={len(v)} — 🚨 표본 부족(<{MIN_N}), 분위수 미산출. 최소 {v[0]:.2f} / 최대 {v[-1]:.2f}")
        else:
            print(f"  {m:9} N={len(v)}  p50 {_pct(v,.50):6.2f}  p75 {_pct(v,.75):6.2f}  "
                  f"p95 {_pct(v,.95):6.2f}  최대 {v[-1]:6.2f}")
    print()

    # 체결충격 (금액별)
    sizes = [a.size] if a.size else None
    agg: Dict[tuple, List[float]] = defaultdict(list)
    unfilled: Dict[tuple, int] = defaultdict(int)
    for r in rows:
        if a.market and r.get("market") != a.market:
            continue
        for side in ("buy", "sell"):
            for q, d in (r.get(side) or {}).items():
                if sizes and int(q) not in sizes:
                    continue
                if d.get("slip_pct") is not None:
                    agg[(r["market"], int(q), side)].append(float(d["slip_pct"]))
                if not d.get("filled", True):
                    unfilled[(r["market"], int(q), side)] += 1

    print("## 체결충격 (%) — 최우선 호가 대비. 양수 = 불리")
    print(f"{'마켓':10}{'금액':>12}{'방향':>6}{'N':>6}{'p50':>9}{'p75':>9}{'p95':>9}{'최대':>9}  미체결")
    for (m, q, side), v in sorted(agg.items()):
        v.sort()
        uf = unfilled.get((m, q, side), 0)
        flag = f"  🚨 {uf}건" if uf else ""
        if len(v) < MIN_N:
            print(f"{m:10}{q:>12,}{side:>6}{len(v):>6}    표본 부족(<{MIN_N}) · 최대 {v[-1]:.4f}%{flag}")
        else:
            print(f"{m:10}{q:>12,}{side:>6}{len(v):>6}{_pct(v,.50):>9.4f}{_pct(v,.75):>9.4f}"
                  f"{_pct(v,.95):>9.4f}{v[-1]:>9.4f}{flag}")
    print()
    print("## 백테스트 비용 상수 제안")
    print("  편도 = 수수료 + 스프레드/2 + 체결충격(p75~p95)")
    print("  현재 TIDE 백테스트: fee_rate 0.001(=0.1%) · 슬리피지 0")
    print("  라이브 config:      FEE_RATE 0.0005(=0.05%)")
    print("  🚨 둘이 다르다. 어느 쪽으로 통일할지 정하고 백테스트를 재실행해야 비교가 성립한다.")
    if len(rows) < MIN_N * 2:
        print()
        print(f"  🚨 총 표본 {len(rows)}행 — 상수 확정 전 최소 2주 수집 권장(급락일 포함 필요).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
