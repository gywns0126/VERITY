#!/usr/bin/env python3
"""
backfill_price_lake.py — 로컬 가격레이크(kr_prices.duckdb) 코너 미커버 종목 백필.

2026-06-20 신설. 소형주 코너 1,120 중 레이크 미커버(~535)를 pykrx OHLCV 로 채워 enrichment 커버리지 확대
([[project_alpha_nest_smallcap_track]] §10). 레이크 = 로컬 자산(repo 밖, ~/VERITY_data_lake).

idempotent: 이미 ohlcv 에 있는 ticker = skip. graceful: 종목별 fetch 실패 = skip + 로그(전체 막지 않음).
ingest_log 동시 기록. 1 ticker = pykrx 1 HTTP call(date-range), ~535 call.

usage: python3 scripts/kr/backfill_price_lake.py [--start 2010-01-01] [--limit N] [--corner PATH]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from api.config import now_kst

LAKE_PATH = os.path.expanduser("~/VERITY_data_lake/kr_prices.duckdb")
_MARKET_MAP = {"KQ": "KOSDAQ", "KS": "KOSPI", "KOSDAQ": "KOSDAQ", "KOSPI": "KOSPI"}


def _load_corner(path: str):
    import json
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("stocks") or []


def _fetch_ohlcv(ticker: str, start: str, end: str):
    """pykrx 일봉 OHLCV → list[tuple] (date, o,h,l,c,vol,value). 실패 시 None."""
    from pykrx import stock as pk
    df = pk.get_market_ohlcv_by_date(start.replace("-", ""), end.replace("-", ""), ticker)
    if df is None or df.empty:
        return None
    rows = []
    for idx, r in df.iterrows():
        d = idx.date() if hasattr(idx, "date") else idx
        rows.append((
            d,
            int(r.get("시가", 0) or 0), int(r.get("고가", 0) or 0),
            int(r.get("저가", 0) or 0), int(r.get("종가", 0) or 0),
            int(r.get("거래량", 0) or 0), int(r.get("거래대금", 0) or 0),
        ))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2010-01-01", help="백필 시작일 (기본 2010-01-01)")
    ap.add_argument("--limit", type=int, default=None, help="처리 종목 수 제한 (테스트용)")
    ap.add_argument("--corner", default=None, help="코너 json 경로")
    ap.add_argument("--sleep", type=float, default=0.4, help="pykrx call 간 sleep(초)")
    args = ap.parse_args()

    import duckdb
    from api.config import DATA_DIR
    corner_path = args.corner or os.path.join(DATA_DIR, "smallcap_corner.json")
    if not os.path.exists(LAKE_PATH):
        sys.stderr.write(f"[backfill] 레이크 부재: {LAKE_PATH} — abort\n")
        return 1

    stocks = _load_corner(corner_path)
    con = duckdb.connect(LAKE_PATH, read_only=False)
    have = {r[0] for r in con.execute("SELECT DISTINCT ticker FROM ohlcv").fetchall()}
    missing = [s for s in stocks if s.get("ticker") and str(s["ticker"]) not in have]
    if args.limit:
        missing = missing[: args.limit]
    end = now_kst().strftime("%Y-%m-%d")
    print(f"[backfill] 코너 {len(stocks)} | 레이크 보유 {len(have)} | 미커버 {len(missing)} 처리 (start={args.start})")

    ok = skipped = failed = total_rows = 0
    for i, s in enumerate(missing, 1):
        tic = str(s["ticker"])
        name = s.get("name") or ""
        market = _MARKET_MAP.get(str(s.get("market", "")).upper(), "KOSDAQ")
        try:
            rows = _fetch_ohlcv(tic, args.start, end)
        except Exception as e:  # noqa: BLE001 — 종목 fetch 실패 = skip(전체 막지 않음)
            failed += 1
            sys.stderr.write(f"[backfill] {tic} {name} fetch 실패: {type(e).__name__}: {e}\n")
            time.sleep(args.sleep)
            continue
        if not rows:
            skipped += 1
            time.sleep(args.sleep)
            continue
        ingested_at = now_kst().replace(tzinfo=None)
        # ohlcv PK=(ticker,date) → OR IGNORE 로 중복 무시(idempotent 재실행). ingest_log PK=(ticker) →
        # ON CONFLICT UPDATE(빈 적재 로그 rows=0 갱신). 종목별 원자(ohlcv+log 정합).
        con.execute("BEGIN")
        con.executemany(
            "INSERT OR IGNORE INTO ohlcv (ticker,name,market,date,open,high,low,close,volume,value) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(tic, name, market, d, o, h, l, c, v, val) for (d, o, h, l, c, v, val) in rows],
        )
        con.execute(
            "INSERT INTO ingest_log (ticker,name,market,rows,ingested_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT (ticker) DO UPDATE SET name=excluded.name, market=excluded.market, "
            "rows=excluded.rows, ingested_at=excluded.ingested_at",
            [tic, name, market, len(rows), ingested_at],
        )
        con.execute("COMMIT")
        ok += 1
        total_rows += len(rows)
        if i % 25 == 0 or i == len(missing):
            print(f"[backfill] {i}/{len(missing)} — ok={ok} skip={skipped} fail={failed} rows={total_rows}")
        time.sleep(args.sleep)

    con.close()
    print(f"[backfill] 완료 — ok={ok} skip(빈값)={skipped} fail={failed} total_rows={total_rows}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
