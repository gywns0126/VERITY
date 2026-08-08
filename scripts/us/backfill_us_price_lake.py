#!/usr/bin/env python3
"""
backfill_us_price_lake.py — 로컬 US 가격레이크(us_prices.duckdb) 구축 (AlphaNest 미장 강화).

2026-06-25 신설 (PM 결정). KR 가격레이크(kr_prices.duckdb)의 US 대응 — US 이벤트스터디(과거 공시 패턴)
+ 모멘텀/변동성 팩터 잠금해제. 레이크 = 로컬 자산(repo 밖, ~/VERITY_data_lake). 소스 = yfinance(무료·키 0).

KR(pykrx, 원화 정수) 과 달리 US 는 float 가격 → ohlcv 가격 컬럼 DOUBLE. 분할/배당 조정 종가(auto_adjust=True)
로 저장 — 미장 잦은 분할(예: NVDA) 의 forward-return 왜곡 방지. value = close*volume(달러 거래대금 근사).

idempotent: 이미 ohlcv 에 있는 ticker = skip(resume). graceful: 종목별 fetch 실패 = skip + 로그.

🚨 2026-08-08 --update 추가 — 이 스크립트에는 증분 경로가 없었다. "이미 있는 ticker = skip" 이라
  한 번 백필한 뒤로는 **날짜가 영영 늘지 않는다**. 실측: 레이크 최종일 2026-06-26 = 43일 정체인데
  event_study_builder / excursion_trail 은 그 위에서 계속 돌고 있었다(측정이 조용히 과거에 고정).
  KR 레이크(kr_prices.duckdb 8/06)와 달리 US 만 갱신 스케줄이 없던 것이 원인이다.
  --update = 보유 ticker 는 max(date) 다음날부터 증분, 미보유 ticker 는 기존대로 전 기간 백필.

usage: python3 scripts/us/backfill_us_price_lake.py [--start 2010-01-01] [--limit N] [--universe PATH]
       python3 scripts/us/backfill_us_price_lake.py --update   # 증분(스케줄러용)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from api.config import DATA_DIR, now_kst

LAKE_PATH = os.path.expanduser("~/VERITY_data_lake/us_prices.duckdb")
DEFAULT_UNIVERSE = os.path.join(DATA_DIR, "us_stock_report_public.json")

_DDL_OHLCV = (
    "CREATE TABLE IF NOT EXISTS ohlcv ("
    "ticker VARCHAR, name VARCHAR, market VARCHAR, date DATE, "
    "open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume BIGINT, value DOUBLE, "
    "PRIMARY KEY (ticker, date))"
)
_DDL_LOG = (
    "CREATE TABLE IF NOT EXISTS ingest_log ("
    "ticker VARCHAR PRIMARY KEY, name VARCHAR, market VARCHAR, rows INTEGER, ingested_at TIMESTAMP)"
)


def _load_universe(path: str):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    stocks = d if isinstance(d, list) else (d.get("stocks") or [])
    out = []
    for s in stocks:
        tk = str(s.get("ticker") or "").strip().upper()
        if tk:
            out.append((tk, s.get("name") or tk))
    return out


def _fetch_ohlcv(ticker: str, start: str):
    """yfinance 일봉 OHLCV(분할/배당 조정) → list[tuple] (date,o,h,l,c,vol,value). 실패/빈값 None."""
    import yfinance as yf
    df = yf.Ticker(ticker).history(start=start, auto_adjust=True, raise_errors=False)
    if df is None or df.empty:
        return None
    rows = []
    for idx, r in df.iterrows():
        d = idx.date() if hasattr(idx, "date") else idx
        try:
            o, h, lo, c = float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"])
            vol = int(r["Volume"] or 0)
        except (KeyError, ValueError, TypeError):
            continue
        if c <= 0:
            continue
        rows.append((d, round(o, 4), round(h, 4), round(lo, 4), round(c, 4), vol, round(c * vol, 2)))
    return rows or None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2010-01-01", help="백필 시작일 (기본 2010-01-01)")
    ap.add_argument("--limit", type=int, default=None, help="처리 종목 수 제한 (테스트용)")
    ap.add_argument("--universe", default=None, help="US 유니버스 json 경로 (기본 us_stock_report_public.json)")
    ap.add_argument("--sleep", type=float, default=0.25, help="yfinance call 간 sleep(초)")
    ap.add_argument("--update", action="store_true",
                    help="보유 ticker 를 max(date) 다음날부터 증분 갱신(+미보유는 전 기간 백필)")
    args = ap.parse_args()

    import duckdb
    from datetime import timedelta as _td

    universe = _load_universe(args.universe or DEFAULT_UNIVERSE)
    os.makedirs(os.path.dirname(LAKE_PATH), exist_ok=True)
    con = duckdb.connect(LAKE_PATH, read_only=False)
    con.execute(_DDL_OHLCV)
    con.execute(_DDL_LOG)
    have = {r[0] for r in con.execute("SELECT DISTINCT ticker FROM ohlcv").fetchall()}

    # worklist = [(ticker, name, start)] — 미보유는 전 기간, 보유는 증분(--update 일 때만).
    work: list = [(t, n, args.start) for (t, n) in universe if t not in have]
    if args.update:
        last_by_tk = {
            r[0]: r[1]
            for r in con.execute("SELECT ticker, max(date) FROM ohlcv GROUP BY ticker").fetchall()
        }
        today = now_kst().date()
        stale = []
        for (t, n) in universe:
            last = last_by_tk.get(t)
            if last is None:
                continue                       # 미보유 = 위 work 에 이미 있음
            if (today - last).days < 1:
                continue                       # 이미 최신
            stale.append((t, n, (last + _td(days=1)).strftime("%Y-%m-%d")))
        work = stale + work                    # 증분 먼저 — 부분 실행돼도 최신성부터 회복
        print(f"[us-lake] --update 증분 대상 {len(stale)}종 (레이크 보유 {len(have)})")
    if args.limit:
        work = work[: args.limit]
    print(f"[us-lake] 유니버스 {len(universe)} | 레이크 보유 {len(have)} | 처리 {len(work)}종")

    ok = skipped = failed = total_rows = 0
    for i, (tic, name, start) in enumerate(work, 1):
        try:
            rows = _fetch_ohlcv(tic, start)
        except Exception as e:  # noqa: BLE001 — 종목 fetch 실패 = skip(전체 막지 않음)
            failed += 1
            sys.stderr.write(f"[us-lake] {tic} {name} fetch 실패: {type(e).__name__}: {str(e)[:80]}\n")
            time.sleep(args.sleep)
            continue
        if not rows:
            skipped += 1
            time.sleep(args.sleep)
            continue
        ingested_at = now_kst().replace(tzinfo=None)
        con.execute("BEGIN")
        con.executemany(
            "INSERT OR IGNORE INTO ohlcv (ticker,name,market,date,open,high,low,close,volume,value) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(tic, name, "US", d, o, h, lo, c, v, val) for (d, o, h, lo, c, v, val) in rows],
        )
        con.execute(
            "INSERT INTO ingest_log (ticker,name,market,rows,ingested_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT (ticker) DO UPDATE SET name=excluded.name, market=excluded.market, "
            "rows=excluded.rows, ingested_at=excluded.ingested_at",
            [tic, name, "US", len(rows), ingested_at],
        )
        con.execute("COMMIT")
        ok += 1
        total_rows += len(rows)
        if i % 50 == 0 or i == len(work):
            print(f"[us-lake] {i}/{len(work)} — ok={ok} skip={skipped} fail={failed} rows={total_rows}")
        time.sleep(args.sleep)

    con.close()
    print(f"[us-lake] 완료 — ok={ok} skip(빈값)={skipped} fail={failed} total_rows={total_rows} -> {LAKE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
