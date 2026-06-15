"""
extract_features.py — Sharadar raw → 파생 피처 스토어 (CoMOM 파이프라인 부속, 취소 전 보존).

2026-06-15 신설. 🚨 라이선스: raw verbatim 복사 = 여전히 purge 대상(Core Data). **우리가 *계산*한
파생 피처만 영구 보존 가능**. 본 스크립트 = 라이선스 살아있을 때 survivorship-free·PIT 파생 피처를
계산해 데이터레이크(repo 밖 parquet)에 보존 → raw 는 이후 purge 가능.

🚨 관측/측정 only (RULE 7) — 점수/brain wire 0. 라이선스: 로컬 전용 실행.
DuckDB COPY = CSV→parquet 스트리밍(메모리 안전, 13GB 무리 없음).

산출 (모두 *계산된* 파생, 광역 universe, survivorship-free):
  1) fundamentals_features.parquet — SF1 ART(PIT datekey): F-Score(Piotroski)/Altman-Z/profitability/
     accruals/asset-growth/leverage/current-ratio/ROE/ROA/netmargin/book_equity. YoY=LAG 4분기.
  2) monthly_returns.parquet — SEP 월별 *수익률*(closeadj 원가 아닌 계산된 ret) → 모멘텀/vol 재계산 가능.
  3) insider_quarterly.parquet — SF2 Form4 분기 집계: 매수/매도 주식·건수·순거래액(인사이더 시그널).
  4) inst_crowding_quarterly.parquet — SF3A 분기 기관 breadth(shrholders)/집중도(percentoftotal).

근거: Piotroski(2000) / Altman(1968) / Novy-Marx(2013) / Sloan accruals(1996) / Cooper-Gulen-Schill 자산성장(2008).
"""
from __future__ import annotations

import argparse
import glob
import logging
import os
import sys
from typing import Optional

logger = logging.getLogger(__name__)

RAW_DIR_DEFAULT = os.path.expanduser("~/Desktop/나스닥")
OUT_DIR_DEFAULT = os.path.expanduser("~/VERITY_data_lake/features")


def _csv(raw_dir: str, table: str) -> Optional[str]:
    hits = sorted(glob.glob(os.path.join(raw_dir, f"SHARADAR_{table}_*.csv")))
    return hits[0] if hits else None


def _view(con, raw_dir: str, table: str) -> bool:
    f = _csv(raw_dir, table)
    if not f:
        logger.warning("%s CSV 없음 — skip", table)
        return False
    con.execute(f"CREATE OR REPLACE VIEW {table} AS "
                f"SELECT * FROM read_csv_auto('{f}', header=true, sample_size=-1)")
    return True


def _copy(con, sql: str, out_path: str) -> int:
    con.execute(f"COPY ({sql}) TO '{out_path}' (FORMAT PARQUET)")
    return con.execute(f"SELECT COUNT(*) FROM read_parquet('{out_path}')").fetchone()[0]


# ── 1. SF1 ART → 펀더멘털 파생 피처 (PIT datekey, YoY=LAG 4) ──────────────
SQL_FUNDAMENTALS = """
WITH base AS (
  SELECT ticker, CAST(datekey AS DATE) AS datekey, CAST(calendardate AS DATE) AS calendardate,
    assets, liabilities, equity, netinccmn, ncfo, gp, revenue,
    assetsc, liabilitiesc, retearn, ebit, debt, sharesbas,
    LAG(netinccmn, 4) OVER w / NULLIF(LAG(assets, 4) OVER w, 0) AS roa_4q,
    LAG(debt, 4) OVER w / NULLIF(LAG(assets, 4) OVER w, 0)      AS lev_4q,
    LAG(assetsc, 4) OVER w / NULLIF(LAG(liabilitiesc, 4) OVER w, 0) AS cr_4q,
    LAG(gp, 4) OVER w / NULLIF(LAG(revenue, 4) OVER w, 0)       AS gm_4q,
    LAG(revenue, 4) OVER w / NULLIF(LAG(assets, 4) OVER w, 0)   AS at_4q,
    LAG(assets, 4) OVER w   AS assets_4q,
    LAG(sharesbas, 4) OVER w AS shares_4q
  FROM SF1 WHERE dimension = 'ART' AND assets > 0
  WINDOW w AS (PARTITION BY ticker ORDER BY datekey)
)
SELECT ticker, datekey, calendardate,
  netinccmn / NULLIF(assets, 0)   AS roa,
  netinccmn / NULLIF(equity, 0)   AS roe,
  gp / NULLIF(assets, 0)          AS gpoa,
  netinccmn / NULLIF(revenue, 0)  AS netmargin,
  (netinccmn - ncfo) / NULLIF(assets, 0) AS accruals,
  assets / NULLIF(assets_4q, 0) - 1.0    AS asset_growth,
  debt / NULLIF(assets, 0)        AS leverage,
  assetsc / NULLIF(liabilitiesc, 0) AS current_ratio,
  equity                          AS book_equity,
  1.2 * (assetsc - liabilitiesc) / NULLIF(assets, 0)
   + 1.4 * retearn / NULLIF(assets, 0)
   + 3.3 * ebit / NULLIF(assets, 0)
   + 0.6 * equity / NULLIF(liabilities, 0)
   + 1.0 * revenue / NULLIF(assets, 0) AS altman_z,
  ( CASE WHEN netinccmn / NULLIF(assets, 0) > 0 THEN 1 ELSE 0 END
  + CASE WHEN ncfo > 0 THEN 1 ELSE 0 END
  + CASE WHEN netinccmn / NULLIF(assets, 0) > roa_4q THEN 1 ELSE 0 END
  + CASE WHEN ncfo > netinccmn THEN 1 ELSE 0 END
  + CASE WHEN debt / NULLIF(assets, 0) < lev_4q THEN 1 ELSE 0 END
  + CASE WHEN assetsc / NULLIF(liabilitiesc, 0) > cr_4q THEN 1 ELSE 0 END
  + CASE WHEN sharesbas <= shares_4q THEN 1 ELSE 0 END
  + CASE WHEN gp / NULLIF(revenue, 0) > gm_4q THEN 1 ELSE 0 END
  + CASE WHEN revenue / NULLIF(assets, 0) > at_4q THEN 1 ELSE 0 END
  ) AS piotroski_f
FROM base
"""

# ── 2. SEP → 월별 수익률 (계산된 파생, 원가 미보존) ──────────────────────
SQL_MONTHLY_RET = """
WITH m AS (
  SELECT ticker, date_trunc('month', CAST(date AS DATE)) AS month,
         last(closeadj ORDER BY date) AS px
  FROM SEP WHERE closeadj > 0
  GROUP BY ticker, date_trunc('month', CAST(date AS DATE))
)
SELECT ticker, month,
  px / NULLIF(LAG(px) OVER (PARTITION BY ticker ORDER BY month), 0) - 1.0 AS ret_1m
FROM m
QUALIFY ret_1m IS NOT NULL
"""

# ── 3. SF2 Form4 → 분기 인사이더 집계 ────────────────────────────────────
SQL_INSIDER = """
SELECT ticker, date_trunc('quarter', CAST(transactiondate AS DATE)) AS quarter,
  SUM(CASE WHEN transactioncode = 'P' THEN transactionshares ELSE 0 END) AS buy_shares,
  SUM(CASE WHEN transactioncode = 'S' THEN transactionshares ELSE 0 END) AS sell_shares,
  SUM(CASE WHEN transactioncode = 'P' THEN 1 ELSE 0 END) AS n_buys,
  SUM(CASE WHEN transactioncode = 'S' THEN 1 ELSE 0 END) AS n_sells,
  SUM(transactionvalue) AS net_value
FROM SF2
WHERE transactiondate IS NOT NULL AND transactioncode IS NOT NULL
GROUP BY ticker, date_trunc('quarter', CAST(transactiondate AS DATE))
"""

# ── 4. SF3A → 분기 기관 crowding (breadth/집중도) ────────────────────────
SQL_CROWDING = """
SELECT ticker, CAST(calendardate AS DATE) AS calendardate,
       shrholders, percentoftotal
FROM SF3A WHERE shrholders IS NOT NULL
"""

JOBS = [
    ("SF1", SQL_FUNDAMENTALS, "fundamentals_features.parquet"),
    ("SEP", SQL_MONTHLY_RET, "monthly_returns.parquet"),
    ("SF2", SQL_INSIDER, "insider_quarterly.parquet"),
    ("SF3A", SQL_CROWDING, "inst_crowding_quarterly.parquet"),
]


def extract(raw_dir: str = RAW_DIR_DEFAULT, out_dir: str = OUT_DIR_DEFAULT) -> dict:
    import duckdb
    os.makedirs(out_dir, exist_ok=True)
    con = duckdb.connect()
    out = {}
    try:
        for table, sql, fname in JOBS:
            if not _view(con, raw_dir, table):
                out[fname] = "skip(no csv)"
                continue
            path = os.path.join(out_dir, fname)
            n = _copy(con, sql, path)
            sz = os.path.getsize(path) / 1e6
            out[fname] = {"rows": n, "MB": round(sz, 1)}
            logger.info("✅ %s: %d행 %.1fMB", fname, n, sz)
        return out
    finally:
        con.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", default=RAW_DIR_DEFAULT)
    ap.add_argument("--out-dir", default=OUT_DIR_DEFAULT)
    args = ap.parse_args()
    try:
        res = extract(args.raw_dir, args.out_dir)
        print("[extract_features] 파생 피처 스토어:")
        for k, v in res.items():
            print(f"  {k}: {v}")
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[extract_features] 실패: {type(e).__name__}: {e}\n")
        raise
