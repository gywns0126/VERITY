"""
crosscheck_13f.py — CoMOM 의 *해석* 교차검증: 13F 기관 crowding (CoMOM 파이프라인 §4).

2026-06-14 신설. CoMOM = 팩터 십분위 내 잔차 상호상관(=차익거래 자본 집중의 *간접* 추정).
이게 실제 기관 crowding 을 반영하는지 = 독립 13F 데이터(SF3A)로 교차검증:
  - shrholders = 13F 보유 기관 수(ownership breadth, Lou-Polk crowding proxy)
  - percentoftotal = 기관 보유 집중도
형성분기 momentum winner(crowded leg) 의 평균 breadth/concentration 을 CoMOM(t) 과 상관.
가설: 높은 CoMOM ↔ winner leg 의 높은 기관 breadth/집중 = CoMOM 이 crowding 을 포착한다는 독립 증거.

🚨 SF3A = 분기 2013-06~ (shrholders_null 0). → CoMOM momentum 와 겹치는 ~51분기만.
🚨 관측/측정 only (RULE 7). 라이선스: 로컬 전용. build_comom 함수 재사용(중복 0).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from build_comom import (  # noqa: E402  — 동일 파이프라인 함수 재사용(중복 회피)
    DB_PATH_DEFAULT, build_ticker_bridge, sp500_member_panel, materialize_sep_panel,
    build_price_panels, momentum_12_1, extreme_deciles, _semi_join_scan,
)

logger = logging.getLogger(__name__)
COMOM_PARQUET = os.path.expanduser("~/VERITY_data_lake/comom_factor_monthly.parquet")
OUT_PARQUET = os.path.expanduser("~/VERITY_data_lake/comom_13f_crosscheck.parquet")


def materialize_sf3a(con, tickers: List[str]) -> pd.DataFrame:
    """SP500-ever SF3A (ticker, calendardate, shrholders, percentoftotal). 분기 2013~."""
    df = _semi_join_scan(con, tickers, """
        SELECT a.ticker, CAST(a.calendardate AS DATE) AS calendardate,
               a.shrholders, a.percentoftotal
        FROM SF3A a JOIN sp_tickers t ON a.ticker = t.ticker
        WHERE a.shrholders IS NOT NULL
        ORDER BY a.ticker, a.calendardate
    """)
    df["calendardate"] = pd.to_datetime(df["calendardate"])
    return df


def _asof_panel(sf3a: pd.DataFrame, col: str, month_index: pd.DatetimeIndex) -> pd.DataFrame:
    """SF3A col → calendardate forward-fill 월말 패널 (look-ahead 차단)."""
    piv = sf3a.pivot_table(index="calendardate", columns="ticker", values=col, aggfunc="last")
    full = piv.index.union(month_index)
    return piv.reindex(full).sort_index().ffill().reindex(month_index)


def _leg_mean(panel: pd.DataFrame, formation: pd.Timestamp, tickers: List[str]) -> Optional[float]:
    if formation not in panel.index:
        return None
    row = panel.loc[formation]
    vals = [row.get(t) for t in tickers if t in row.index and pd.notna(row.get(t))]
    return float(np.mean(vals)) if len(vals) >= 5 else None


def _corr(x: pd.Series, y: pd.Series, method: str) -> Optional[float]:
    d = pd.concat([x, y], axis=1).dropna()
    if len(d) < 8:
        return None
    return round(float(d.corr(method=method).iloc[0, 1]), 4)


def crosscheck(db_path: str = DB_PATH_DEFAULT, comom_parquet: str = COMOM_PARQUET,
               persist: bool = True) -> Dict[str, object]:
    import duckdb

    con = duckdb.connect(db_path)
    try:
        bridge = build_ticker_bridge(con)
        sp = sp500_member_panel(con, bridge)
        sp_curr = sorted(sp["cur_ticker"].dropna().unique().tolist())
        sep = materialize_sep_panel(con, sp_curr)
        monthly_close, _ = build_price_panels(sep)
        sf3a = materialize_sf3a(con, sp_curr)
        logger.info("SF3A 행 %d, %s~%s", len(sf3a),
                    sf3a["calendardate"].min().date(), sf3a["calendardate"].max().date())

        breadth = _asof_panel(sf3a, "shrholders", monthly_close.index)
        conc = _asof_panel(sf3a, "percentoftotal", monthly_close.index)

        members_by_q = {pd.Timestamp(me): set(g["cur_ticker"].dropna()) for me, g in sp.groupby("month_end")}
        rows = []
        for f in sorted(sp["month_end"].unique()):
            f_me = pd.Timestamp(f).to_period("M").to_timestamp("M")
            members = members_by_q.get(pd.Timestamp(f), set())
            if not members:
                continue
            mom = momentum_12_1(monthly_close, f_me)
            legs = extreme_deciles(mom, members)
            if legs is None:
                continue
            rows.append({
                "month_end": f_me,
                "win_breadth": _leg_mean(breadth, f_me, legs["top"]),
                "los_breadth": _leg_mean(breadth, f_me, legs["bottom"]),
                "win_conc": _leg_mean(conc, f_me, legs["top"]),
                "los_conc": _leg_mean(conc, f_me, legs["bottom"]),
            })
        panel = pd.DataFrame(rows)

        # CoMOM momentum 슬라이스 병합
        cm = pd.read_parquet(comom_parquet)
        cm = cm[cm.get("factor", "momentum") == "momentum"][["month_end", "comom"]].copy()
        cm["month_end"] = pd.to_datetime(cm["month_end"])
        panel["month_end"] = pd.to_datetime(panel["month_end"])
        merged = panel.merge(cm, on="month_end", how="inner").dropna(subset=["comom"])
        merged["breadth_spread"] = merged["win_breadth"] - merged["los_breadth"]

        # 13F 가용(=breadth 존재) 구간만 = 실제 상관 N (SF3A 2013~ 제약)
        have_13f = merged.dropna(subset=["win_breadth"])
        out = {
            "n_overlap": int(len(have_13f)),
            "period": (str(have_13f["month_end"].min().date()), str(have_13f["month_end"].max().date())) if len(have_13f) else None,
            "corr": {},
        }
        for tgt in ["win_breadth", "win_conc", "breadth_spread"]:
            out["corr"][tgt] = {
                "spearman": _corr(merged["comom"], merged[tgt], "spearman"),
                "pearson": _corr(merged["comom"], merged[tgt], "pearson"),
            }

        if persist and len(merged):
            con.execute("DROP TABLE IF EXISTS comom_13f_crosscheck")
            con.register("cc_df", merged)
            con.execute("CREATE TABLE comom_13f_crosscheck AS SELECT * FROM cc_df")
            con.unregister("cc_df")
            os.makedirs(os.path.dirname(OUT_PARQUET), exist_ok=True)
            merged.to_parquet(OUT_PARQUET)
        return out
    finally:
        con.close()


def _print(res: Dict[str, object]) -> None:
    print(f"[crosscheck_13f] CoMOM ↔ 13F 기관 crowding 교차검증 (관측 only)")
    print(f"  겹침 N={res['n_overlap']}분기  기간={res['period']}  (SF3A 2013~ 제약)")
    print("  가설: 높은 CoMOM ↔ winner(crowded) leg 높은 기관 breadth/집중 → +상관 = CoMOM 이 crowding 포착 증거.\n")
    labels = {"win_breadth": "winner 기관수(breadth)", "win_conc": "winner 집중도(percentoftotal)",
              "breadth_spread": "breadth 스프레드(win−los)"}
    for tgt, c in res["corr"].items():
        print(f"  CoMOM vs {labels.get(tgt, tgt)}: Spearman={c['spearman']}  Pearson={c['pearson']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-path", default=DB_PATH_DEFAULT)
    ap.add_argument("--comom-parquet", default=COMOM_PARQUET)
    ap.add_argument("--no-persist", action="store_true")
    args = ap.parse_args()
    try:
        _print(crosscheck(args.db_path, args.comom_parquet, persist=not args.no_persist))
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[crosscheck_13f] 실패: {type(e).__name__}: {e}\n")
        raise
