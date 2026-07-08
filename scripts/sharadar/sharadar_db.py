"""
sharadar_db.py — Sharadar 로컬 번들 DuckDB 스테이징 + 유니버스 빌더 (CoMOM 파이프라인 §1-2).

2026-06-14 신설. 🚨 라이선스 규율: 로컬 전용(클라우드 금지) — raw CSV는 ~/Desktop/나스닥 에서만
read, staging DuckDB + derived 는 repo 밖(~/VERITY_data_lake) 보존. raw 는 derived 산출 후 purge 대상.
본 파일은 *코드*(데이터 아님) 라 repo 추적. 데이터는 절대 repo 진입 금지.

DuckDB read_csv_auto = 스트리밍 스캔(13GB 메모리 로드 0). 뷰만 등록, derived 테이블만 영속.

gotcha(인벤토리 도출): ticker 직접 join 금지 → permaticker(불변키). category=보통주 필터.
SP500 PIT 멤버십 = action='historical' 월말 스냅샷(1998-03~) 직접 사용. survivorship-free.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from typing import Dict, Optional

RAW_DIR_DEFAULT = os.path.expanduser("~/Desktop/나스닥")
DB_PATH_DEFAULT = os.path.expanduser("~/VERITY_data_lake/sharadar.duckdb")

# 등록할 테이블 (table_name → 파일 glob prefix)
TABLES = ["SF1", "SEP", "DAILY", "SF3A", "SF3B", "SF2", "SP500", "TICKERS", "ACTIONS", "METRICS", "EVENTS"]


def _find_csv(raw_dir: str, table: str) -> Optional[str]:
    hits = glob.glob(os.path.join(raw_dir, f"SHARADAR_{table}_*.csv"))
    # 최신 mtime 선택 — 구 번들이 남아있어도 최신 다운로드 사용.
    # (구: sorted[0]=알파벳/해시순 임의 → 새 번들 추가 시 old 를 silent 선택하는 stale 버그)
    return max(hits, key=os.path.getmtime) if hits else None


def connect(raw_dir: str = RAW_DIR_DEFAULT, db_path: str = DB_PATH_DEFAULT):
    """DuckDB 연결 + 로컬 Sharadar CSV 를 뷰로 등록(스트리밍, 메모리 로드 0)."""
    import duckdb

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    con = duckdb.connect(db_path)
    registered = {}
    for t in TABLES:
        f = _find_csv(raw_dir, t)
        if not f:
            continue
        # read_csv_auto: 헤더/타입 자동, 따옴표 콤마 안전. 뷰 = 매 쿼리 스트리밍 스캔.
        con.execute(
            f"CREATE OR REPLACE VIEW {t} AS "
            f"SELECT * FROM read_csv_auto('{f}', header=true, sample_size=-1)"
        )
        registered[t] = f
    return con, registered


def build_common_stock_universe(con) -> int:
    """보통주 마스터 (derived 테이블 universe_common). TICKERS table='SF1'·category=보통주·permaticker dedup.

    category 보통주 = 'Domestic Common Stock'/'ADR Common Stock'/'Canadian Common Stock' 계열.
    permaticker = 불변 join 키 (ticker 재활용 회피).
    """
    con.execute("""
        CREATE OR REPLACE TABLE universe_common AS
        SELECT permaticker, ticker, name, exchange, isdelisted,
               category, sector, famaindustry, siccode,
               firstpricedate, lastpricedate
        FROM (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY permaticker ORDER BY lastpricedate DESC NULLS LAST) rn
            FROM TICKERS
            WHERE "table" IN ('SF1', 'SEP')
              AND category LIKE '%Common Stock%'
        ) WHERE rn = 1
    """)
    return con.execute("SELECT COUNT(*) FROM universe_common").fetchone()[0]


def build_sp500_membership(con) -> int:
    """SP500 월말 PIT 멤버십 (derived 테이블 sp500_membership). action='historical' 스냅샷(1998-03~).

    각 (date, ticker) = 그 월말의 S&P500 구성종목. survivorship-free(상폐/피인수 종목도 그 시점엔 멤버).
    """
    con.execute("""
        CREATE OR REPLACE TABLE sp500_membership AS
        SELECT CAST(date AS DATE) AS month_end, ticker
        FROM SP500
        WHERE action = 'historical'
    """)
    return con.execute("SELECT COUNT(*) FROM sp500_membership").fetchone()[0]


def smoke(raw_dir: str = RAW_DIR_DEFAULT, db_path: str = DB_PATH_DEFAULT) -> Dict[str, object]:
    """스테이징 + 유니버스 빌드 + survivorship/PIT 검증 리포트."""
    con, reg = connect(raw_dir, db_path)
    out: Dict[str, object] = {"registered_tables": list(reg.keys())}

    # 행수(스트리밍 카운트)
    out["sep_rows"] = con.execute("SELECT COUNT(*) FROM SEP").fetchone()[0]
    out["sf1_rows"] = con.execute("SELECT COUNT(*) FROM SF1").fetchone()[0]

    out["universe_common_n"] = build_common_stock_universe(con)
    # survivorship 검증: 유니버스에 상폐 종목 포함?
    delisted = con.execute("SELECT COUNT(*) FROM universe_common WHERE isdelisted='Y'").fetchone()[0]
    active = con.execute("SELECT COUNT(*) FROM universe_common WHERE isdelisted='N'").fetchone()[0]
    out["universe_delisted"] = delisted
    out["universe_active"] = active
    out["survivorship_free"] = delisted > 0

    out["sp500_membership_rows"] = build_sp500_membership(con)
    # PIT 샘플: 특정 월말 S&P500 멤버 수 (정상이면 ~500)
    sample = con.execute("""
        SELECT month_end, COUNT(*) n FROM sp500_membership
        GROUP BY month_end ORDER BY month_end DESC LIMIT 3
    """).fetchall()
    out["sp500_recent_monthends"] = [(str(d), n) for d, n in sample]
    # 그 멤버 중 현재 상폐된 종목 존재? (survivorship-free PIT 증거)
    out["sp500_includes_delisted"] = con.execute("""
        SELECT COUNT(DISTINCT m.ticker) FROM sp500_membership m
        JOIN universe_common u ON m.ticker = u.ticker
        WHERE u.isdelisted = 'Y'
    """).fetchone()[0]
    con.close()
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default=RAW_DIR_DEFAULT)
    ap.add_argument("--db-path", default=DB_PATH_DEFAULT)
    args = ap.parse_args()
    try:
        r = smoke(args.raw_dir, args.db_path)
        print("[sharadar_db] 스테이징/유니버스 smoke:")
        for k, v in r.items():
            print(f"  {k}: {v}")
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[sharadar_db] 실패: {type(e).__name__}: {e}\n")
        raise
