# -*- coding: utf-8 -*-
"""us_chart_history — 미국 전체 유니버스 일봉 이력 레이크 (KR `kr_chart_history` 대응).

**왜 필요한가**: 2026-08-08 백테스트로 최종 점수의 39%(technical 17 · momentum 10 ·
volatility 6 · mean_reversion 6)가 전부 가격 파생이라는 것과, 그 중 통과한 축이
volatility 하나뿐이라는 것을 KR 에서 확인했다. **미장에서는 같은 검정을 못 했다** —
일봉 이력이 없었기 때문이다.

기존 `us_chart_daily` 는 공분산용으로 추천 종목 250봉만 담는다(상한 60). 백테스트·
변동성 분석·레버리지 상품 끌림 계산에는 **전 유니버스 × 전 기간**이 필요하다.

**소스 = yfinance.** 2026-08-08 실호출 검증 결과 무료로 이력을 주는 곳이 여기뿐이었다:
    Polygon 무료  → 과거 403 · 분당 2콜에서 429
    FMP 무료      → 403 (legacy endpoint 폐지)
    Alpha Vantage → DAILY_ADJUSTED 프리미엄 전환
    Finnhub 무료  → /stock/candle 403
    Stooq         → HTML 차단
    yfinance      → TSLA 4,052봉(2010~) · TSLL 1,003봉 ✅ (운영 `analyze_technical` 이 이미 사용)

🚨 **레포에 커밋하지 않는다.** 5,000종목 × ~1,600봉이면 KR 레이크(161MB)와 같은 규모다.
   `data/us_chart_history/` 는 .gitignore 대상이며, 발행이 필요하면 KR 과 동일하게
   Vercel Blob 으로 올린다(`fsc_daily_prices.run_history` 선례).

🚨 **수정주가(auto_adjust=True)** 로 받는다. 미수정 가격이 섞이면 분할일에 가짜 폭락이
   생겨 변동성·모멘텀이 통째로 오염된다.

멱등·재개: 이미 받은 티커는 건너뛴다. 중단돼도 다음 run 이 이어받는다
   (2026-08-08 소멸 종목 백필에서 중단 1회로 진도가 날아간 학습 — 파일 존재 자체가 체크포인트).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Set

try:
    from api.config import DATA_DIR
    _DATA = DATA_DIR
except Exception:  # 단독 실행 폴백
    _DATA = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")

OUT_DIR = os.path.join(_DATA, "us_chart_history")
META_PATH = os.path.join(_DATA, "us_chart_history_meta.json")
UNIVERSE_PATHS = (
    os.path.join(_DATA, "us_universe_combined.json"),
    os.path.join(_DATA, "us_universe_sp1500.json"),
)

WORKERS = 8            # Yahoo 유량 — 과하면 429. 실측 8병렬 안정
PERIOD = "max"         # 전 기간 (상장 이후)
MIN_BARS = 60          # 이보다 짧으면 저장하지 않는다(신규 상장·데이터 불량)


def load_universe(limit: int = 0) -> List[str]:
    """미국 티커 목록. us_universe_combined 우선, 없으면 sp1500.

    🚨 티커 정규화: yfinance 는 BRK.B 를 BRK-B 로 쓴다. 점을 하이픈으로 바꾼다.
    """
    tickers: List[str] = []
    seen: Set[str] = set()
    for p in UNIVERSE_PATHS:
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        cand: List[Any] = []
        if isinstance(doc, dict):
            for k in ("tickers", "stocks", "universe", "data"):
                v = doc.get(k)
                if isinstance(v, list):
                    cand = v
                    break
                if isinstance(v, dict):
                    cand = list(v.keys())
                    break
            if not cand:
                cand = [k for k in doc if not str(k).startswith("_")]
        elif isinstance(doc, list):
            cand = doc
        for c in cand:
            t = c if isinstance(c, str) else (c or {}).get("ticker") or (c or {}).get("symbol")
            t = str(t or "").strip().upper()
            if not t or len(t) > 6 or t in seen:
                continue
            if not all(ch.isalnum() or ch in ".-" for ch in t):
                continue
            seen.add(t)
            tickers.append(t)
        if tickers:
            break
    tickers.sort()
    return tickers[:limit] if limit else tickers


def _yf_symbol(t: str) -> str:
    return t.replace(".", "-")


def fetch_one(ticker: str) -> Optional[Dict[str, Any]]:
    """단일 종목 전 기간 일봉 → {t, n, c:[[yyyymmdd,o,h,l,c,v], ...]}. 실패면 None."""
    try:
        from api.collectors.yfinance_safe import yf_ticker
        hist = yf_ticker(_yf_symbol(ticker)).history(period=PERIOD, auto_adjust=True)
    except Exception:  # noqa: BLE001 — 개별 실패는 caller 가 집계
        return None
    if hist is None or len(hist) < MIN_BARS:
        return None
    rows: List[List[float]] = []
    for ts, r in hist.iterrows():
        try:
            c = float(r["Close"])
            if c <= 0:
                continue
            rows.append([int(ts.strftime("%Y%m%d")), float(r["Open"]), float(r["High"]),
                         float(r["Low"]), c, float(r["Volume"] or 0)])
        except (TypeError, ValueError, KeyError):
            continue
    if len(rows) < MIN_BARS:
        return None
    rows.sort(key=lambda x: x[0])
    return {"t": ticker, "n": ticker, "c": rows}


def _have() -> Set[str]:
    """이미 받은 티커 — 파일 존재 자체가 체크포인트(중단 내성)."""
    if not os.path.isdir(OUT_DIR):
        return set()
    return {os.path.splitext(f)[0] for f in os.listdir(OUT_DIR) if f.endswith(".json")}


def collect(limit: int = 0, refresh: bool = False, universe_limit: int = 0) -> Dict[str, Any]:
    universe = load_universe(universe_limit)
    if not universe:
        return {"status": "no_universe", "hint": "data/us_universe_combined.json 확인"}
    os.makedirs(OUT_DIR, exist_ok=True)
    have = set() if refresh else _have()
    todo = [t for t in universe if t not in have]
    if limit:
        todo = todo[:limit]

    ok, failed = 0, []
    t0 = time.time()

    def _one(t: str) -> bool:
        r = fetch_one(t)
        if not r:
            return False
        tmp = os.path.join(OUT_DIR, f"{t}.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, os.path.join(OUT_DIR, f"{t}.json"))
        return True

    if todo:
        with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for i, (t, good) in enumerate(zip(todo, ex.map(_one, todo)), 1):
                if good:
                    ok += 1
                else:
                    failed.append(t)
                if i % 200 == 0:
                    print(f"[us_chart_history] {i}/{len(todo)} · ok {ok} · "
                          f"{time.time() - t0:.0f}s", file=sys.stderr, flush=True)

    total = _have()
    meta = {
        "as_of": time.strftime("%Y-%m-%dT%H:%M:%S+09:00", time.localtime(time.time() + 9 * 3600)),
        "universe": len(universe), "have": len(total),
        "fetched_now": ok, "failed_now": len(failed), "failed_sample": failed[:30],
        "source": "yfinance period=max auto_adjust=True",
        "note": ("레포 비커밋 — 5,000종목 규모라 Blob/외부 저장 대상. "
                 "🚨 실패는 상장폐지·티커변경·야후 미수록 혼재이며 사유를 단정하지 않는다."),
    }
    tmp = META_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    os.replace(tmp, META_PATH)
    return {"status": "ok", **{k: meta[k] for k in ("universe", "have", "fetched_now", "failed_now")},
            "elapsed_sec": round(time.time() - t0, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="이번 run 최대 종목 (0=전체)")
    ap.add_argument("--universe-limit", type=int, default=0)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--plan-only", action="store_true")
    a = ap.parse_args()
    if a.plan_only:
        u = load_universe(a.universe_limit)
        print(f"[us_chart_history] 유니버스 {len(u):,} · 보유 {len(_have()):,} · "
              f"잔여 {len([t for t in u if t not in _have()]):,}")
        return 0
    r = collect(a.limit, a.refresh, a.universe_limit)
    if r.get("status") != "ok":
        print(f"[us_chart_history] {r.get('status')} — {r.get('hint','')}", file=sys.stderr)
        return 1
    print(f"[us_chart_history] 보유 {r['have']:,}/{r['universe']:,} · "
          f"신규 {r['fetched_now']:,} · 실패 {r['failed_now']} · {r['elapsed_sec']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
