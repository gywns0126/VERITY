"""
build_comom.py — CoMOM(Lou-Polk 2022) 모멘텀 crowding 월별 시계열 오케스트레이터 (CoMOM 파이프라인 §3).

2026-06-14 신설. 입력 = sharadar_db.py 가 만든 로컬 DuckDB(~/VERITY_data_lake/sharadar.duckdb)
의 SEP/SP500/ACTIONS + Kenneth French FF3(무료). 출력 = derived 테이블 `comom_monthly`
+ parquet(데이터레이크). 🚨 라이선스: 로컬 전용(클라우드/cron 금지) — 로컬 스크립트로만 실행.
🚨 관측/측정 only (RULE 7) — 점수/brain 결정 wire 0. forward IC decay 검증은 §6(후속).

산식 흐름 (Lou-Polk 2022, RFS — comomentum):
  1) 형성월말 t 마다 S&P500 PIT 멤버(survivorship-free) = 유니버스.
  2) 12-1 모멘텀(월별 closeadj, 최근 1M skip) → cross-sectional 십분위 → top=winner / bottom=loser.
  3) winner/loser 종목들의 **주간 FF3 잔차**(trailing 52주) 상호상관 평균 = CoMOM (comomentum.compute_comom).
  4) 월별 CoMOM 시계열 → derived 보존.

🚨 schema gotcha (sharadar_db.py 와 동일 규율):
  - SEP/SP500 = ticker 키. SEP 는 *현재 ticker* 로 엔티티 전체 이력 저장.
    SP500 PIT 멤버십은 *그 시점 ticker* → ACTIONS tickerchange 로 현재 ticker 로 bridge 후 join.
  - closeadj = 배당/분할 조정가(수익률용). survivorship: 상폐 종목도 SEP frozen + SP500 historical 에 잔존.

성능: SEP 는 3GB CSV 뷰(쿼리마다 풀스캔) → S&P500-ever 티커로 필터한 일별가를 *1회* materialize
후 전부 메모리에서 월별/주별 패널 계산. 형성월 루프는 in-memory 슬라이스(빠름).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# repo 루트 import 경로
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from api.quant.alpha.comomentum import compute_comom, WINDOW_WEEKS  # noqa: E402
from api.quant.alpha.ff3_factors import fetch_ff3_weekly            # noqa: E402

logger = logging.getLogger(__name__)

DB_PATH_DEFAULT = os.path.expanduser("~/VERITY_data_lake/sharadar.duckdb")
FF3_CACHE_DEFAULT = os.path.expanduser("~/VERITY_data_lake/ff3_weekly.parquet")
PARQUET_OUT_DEFAULT = os.path.expanduser("~/VERITY_data_lake/comom_monthly.parquet")

MOM_LOOKBACK_M = 12     # 12-1 모멘텀 lookback
MOM_SKIP_M = 1          # 최근 1개월 skip (단기 반전 회피, Jegadeesh-Titman)
DECILE_FRAC = 0.10      # 상/하위 십분위
MIN_UNIVERSE = 30       # 형성월 최소 유효 모멘텀 종목 (십분위 의미 확보)
FWD_HORIZONS_Q = [4, 8] # forward WML 스프레드 측정 분기(1년/2년) — §6 IC decay 검증용


# --------------------------------------------------------------------------- #
# 1. 티커 변경 bridge (historical ticker → 현재 ticker)
# --------------------------------------------------------------------------- #
def build_ticker_bridge(con) -> Dict[str, str]:
    """ACTIONS tickerchange 로 historical→current 매핑. 체인 끝(terminal)까지 resolve.

    Sharadar 관례 검증은 호출부 coverage 리포트로 한다(방향 empirical 확정). 여기선
    tickerchangeto 행: ticker=NEW, contraticker=OLD 가정으로 OLD→NEW edge 구성 후 forward resolve.
    미해결 ticker = 자기 자신 반환(대다수 변경 없음).
    """
    rows = con.execute("""
        SELECT contraticker AS old_t, ticker AS new_t
        FROM ACTIONS
        WHERE action = 'tickerchangeto'
          AND contraticker IS NOT NULL AND ticker IS NOT NULL
          AND contraticker <> ticker
    """).fetchall()
    edge: Dict[str, str] = {}
    for old_t, new_t in rows:
        edge[old_t] = new_t

    def resolve(t: str, _depth: int = 0) -> str:
        seen = set()
        cur = t
        while cur in edge and cur not in seen and _depth < 20:
            seen.add(cur)
            cur = edge[cur]
            _depth += 1
        return cur

    return {old_t: resolve(old_t) for old_t in edge}


# --------------------------------------------------------------------------- #
# 2. S&P500-ever 유니버스 + 가격 패널 materialize
# --------------------------------------------------------------------------- #
def sp500_member_panel(con, bridge: Dict[str, str]) -> pd.DataFrame:
    """SP500 PIT 멤버십(month_end, historical ticker) → bridge 로 current ticker 컬럼 추가."""
    df = con.execute(
        "SELECT month_end, ticker FROM sp500_membership"
    ).fetchdf()
    df["month_end"] = pd.to_datetime(df["month_end"])
    df["cur_ticker"] = df["ticker"].map(lambda t: bridge.get(t, t))
    return df


def materialize_sep_panel(con, tickers: List[str]) -> pd.DataFrame:
    """S&P500-ever current 티커들의 일별 (ticker, date, closeadj) 1회 materialize.

    SEP 뷰 풀스캔 1회로 끝냄. 반환 = pandas DataFrame(메모리 보유).
    """
    # DuckDB 임시 테이블에 티커 리스트 등록 후 semi-join (IN 리스트 길이 한계 회피)
    tdf = pd.DataFrame({"ticker": sorted(set(tickers))})
    con.register("sp_tickers", tdf)
    df = con.execute("""
        SELECT s.ticker, CAST(s.date AS DATE) AS date, s.closeadj
        FROM SEP s
        JOIN sp_tickers t ON s.ticker = t.ticker
        WHERE s.closeadj IS NOT NULL AND s.closeadj > 0
        ORDER BY s.ticker, s.date
    """).fetchdf()
    con.unregister("sp_tickers")
    df["date"] = pd.to_datetime(df["date"])
    return df


def build_price_panels(sep: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """일별 closeadj → (monthly_close: ticker×month_end, weekly_ret: ticker×friday).

    monthly_close = 각 월 마지막 거래일 closeadj (12-1 모멘텀용).
    weekly_ret    = W-FRI 리샘플 last → pct_change (FF3 Friday-dated 정합, comomentum 잔차용).
    """
    s = sep.set_index("date")
    # 월별 마지막값
    monthly = (
        s.groupby("ticker")["closeadj"]
        .resample("ME").last()
        .reset_index()
    )
    monthly_close = monthly.pivot(index="date", columns="ticker", values="closeadj")
    monthly_close.index = monthly_close.index.to_period("M").to_timestamp("M")

    # 주별(금요일) 수익률
    weekly_px = (
        s.groupby("ticker")["closeadj"]
        .resample("W-FRI").last()
    )
    weekly_close = weekly_px.reset_index().pivot(index="date", columns="ticker", values="closeadj")
    # fill_method=None: 휴장 주는 0수익 조작 대신 NaN → 종목별 dropna 에서 제거(잔차 정합)
    weekly_ret = weekly_close.pct_change(fill_method=None)
    return monthly_close, weekly_ret


# --------------------------------------------------------------------------- #
# 3. 형성월별 CoMOM
# --------------------------------------------------------------------------- #
def momentum_12_1(monthly_close: pd.DataFrame, formation: pd.Timestamp) -> pd.Series:
    """형성월말 t 기준 12-1 모멘텀: closeadj(t-skip) / closeadj(t-lookback-skip) - 1.

    skip=1M, lookback=12M → [t-13M, t-1M] 누적수익(최근 1M 제외). 월말 인덱스 정합 필요.
    """
    months = monthly_close.index
    if formation not in months:
        return pd.Series(dtype=float)
    pos = months.get_loc(formation)
    p_recent = pos - MOM_SKIP_M                 # t-1M
    p_old = pos - MOM_SKIP_M - MOM_LOOKBACK_M   # t-13M
    if p_old < 0:
        return pd.Series(dtype=float)
    end = monthly_close.iloc[p_recent]
    start = monthly_close.iloc[p_old]
    mom = (end / start) - 1.0
    return mom.replace([np.inf, -np.inf], np.nan).dropna()


def extreme_deciles(mom: pd.Series, members: set) -> Optional[Dict[str, List[str]]]:
    """유니버스 내 모멘텀 → 상/하위 십분위 {top:[winners], bottom:[losers]}."""
    m = mom[mom.index.isin(members)].dropna()
    if len(m) < MIN_UNIVERSE:
        return None
    n = max(1, int(round(len(m) * DECILE_FRAC)))
    ranked = m.sort_values()
    bottom = list(ranked.index[:n])      # 최저 모멘텀 = loser
    top = list(ranked.index[-n:])        # 최고 모멘텀 = winner
    return {"top": top, "bottom": bottom}


def forward_wml_return(
    monthly_close: pd.DataFrame, formation: pd.Timestamp,
    legs: Dict[str, List[str]], k_quarters: int,
) -> Optional[float]:
    """형성월말 t 의 winner−loser(12-1) 동일가중 스프레드를 forward k분기 보유한 *실현* 수익률.

    Lou-Polk 핵심검정: 높은 CoMOM(t) → 낮은(음) forward 모멘텀 스프레드 (1~2년 후). look-ahead 아님
    (t 시점 십분위 멤버 고정 후 미래 실현가로 평가). 가용 종목 < 5/leg → None.
    """
    months = monthly_close.index
    if formation not in months:
        return None
    pos = months.get_loc(formation)
    tgt = pos + k_quarters * 3
    if tgt >= len(months):
        return None
    p0 = monthly_close.iloc[pos]
    p1 = monthly_close.iloc[tgt]

    def _basket(tks: List[str]) -> Optional[float]:
        r = []
        for t in tks:
            a, b = p0.get(t), p1.get(t)
            if a is not None and b is not None and pd.notna(a) and pd.notna(b) and a > 0:
                r.append(b / a - 1.0)
        return float(np.mean(r)) if len(r) >= 5 else None

    win = _basket(legs.get("top") or [])
    los = _basket(legs.get("bottom") or [])
    if win is None or los is None:
        return None
    return round(win - los, 4)


def comom_for_month(
    formation: pd.Timestamp,
    monthly_close: pd.DataFrame,
    weekly_ret: pd.DataFrame,
    members: set,
    ff3: pd.DataFrame,
    window: int = WINDOW_WEEKS,
) -> Optional[Dict[str, object]]:
    """단일 형성월 CoMOM. 계산 불가(유니버스/십분위 부족) → None."""
    mom = momentum_12_1(monthly_close, formation)
    if mom.empty:
        return None
    legs = extreme_deciles(mom, members)
    if legs is None:
        return None

    # 형성월말까지의 주간수익률만 사용(look-ahead 차단), 종목별 Series 추출
    wk = weekly_ret.loc[weekly_ret.index <= formation]
    if wk.empty:
        return None
    needed = set(legs["top"]) | set(legs["bottom"])
    weekly_returns: Dict[str, pd.Series] = {}
    for t in needed:
        if t in wk.columns:
            s = wk[t].dropna()
            if not s.empty:
                weekly_returns[t] = s

    res = compute_comom(weekly_returns, {"momentum": legs}, ff3, window=window)
    mres = res.get("momentum", {})
    rec = {
        "month_end": formation,
        "comom": mres.get("comom"),
        "comom_winner": mres.get("comom_winner"),
        "comom_loser": mres.get("comom_loser"),
        "n_winner": mres.get("n_winner"),
        "n_loser": mres.get("n_loser"),
        "n_universe": int(len(mom[mom.index.isin(members)].dropna())),
    }
    for k in FWD_HORIZONS_Q:
        rec[f"fwd_wml_{k}q"] = forward_wml_return(monthly_close, formation, legs, k)
    return rec


# --------------------------------------------------------------------------- #
# 4. 오케스트레이터
# --------------------------------------------------------------------------- #
def build(
    db_path: str = DB_PATH_DEFAULT,
    ff3_cache: str = FF3_CACHE_DEFAULT,
    parquet_out: str = PARQUET_OUT_DEFAULT,
    max_months: Optional[int] = None,
    persist: bool = True,
) -> pd.DataFrame:
    """전 구간(또는 최근 max_months) 월별 CoMOM 시계열 빌드 + derived 보존."""
    import duckdb

    con = duckdb.connect(db_path)
    try:
        log = logging.getLogger("build_comom")

        bridge = build_ticker_bridge(con)
        log.info("ticker bridge edges: %d", len(bridge))

        sp = sp500_member_panel(con, bridge)
        sp_curr = sorted(sp["cur_ticker"].dropna().unique().tolist())
        log.info("S&P500-ever current 티커: %d", len(sp_curr))

        sep = materialize_sep_panel(con, sp_curr)
        # bridge 방향 검증(coverage): SP500 멤버 중 SEP 가격이력 매칭 비율
        sep_have = set(sep["ticker"].unique())
        matched = sp["cur_ticker"].isin(sep_have).mean()
        log.info("SP500 멤버-행 SEP closeadj 매칭률: %.3f (낮으면 bridge 방향 의심)", matched)

        monthly_close, weekly_ret = build_price_panels(sep)
        ff3 = fetch_ff3_weekly(cache_path=ff3_cache)
        ff3 = ff3[~ff3.index.duplicated(keep="last")].sort_index()

        # 형성월 = SP500 월말 ∩ 모멘텀 산출 가능(>= 13M 이력) 구간
        formations = sorted(sp["month_end"].unique())
        formations = [pd.Timestamp(f) for f in formations]
        if max_months:
            formations = formations[-max_months:]

        rows = []
        members_by_month = {
            pd.Timestamp(me): set(g["cur_ticker"].dropna())
            for me, g in sp.groupby("month_end")
        }
        for f in formations:
            # monthly_close 인덱스(월말)에 정렬: f 와 같은 달의 월말 timestamp 로 매핑
            f_me = pd.Timestamp(f).to_period("M").to_timestamp("M")
            members = members_by_month.get(pd.Timestamp(f), set())
            if not members:
                continue
            rec = comom_for_month(f_me, monthly_close, weekly_ret, members, ff3)
            if rec is not None and rec.get("comom") is not None:
                rows.append(rec)

        _cols = ["month_end", "comom", "comom_winner", "comom_loser", "n_winner", "n_loser",
                 "n_universe"] + [f"fwd_wml_{k}q" for k in FWD_HORIZONS_Q]
        out = pd.DataFrame(rows).sort_values("month_end").reset_index(drop=True) if rows else pd.DataFrame(columns=_cols)
        log.info("CoMOM 월별 시계열: %d 개월 산출", len(out))

        if persist and not out.empty:
            con.execute("DROP TABLE IF EXISTS comom_monthly")
            con.register("comom_df", out)
            con.execute("CREATE TABLE comom_monthly AS SELECT * FROM comom_df")
            con.unregister("comom_df")
            os.makedirs(os.path.dirname(parquet_out), exist_ok=True)
            out.to_parquet(parquet_out)
            log.info("저장: comom_monthly(DuckDB) + %s", parquet_out)

        return out
    finally:
        con.close()


def _summary(out: pd.DataFrame) -> None:
    if out.empty:
        print("[build_comom] 산출 0행")
        return
    c = out["comom"].astype(float)
    print(f"[build_comom] 월수={len(out)}  기간={out['month_end'].min().date()}~{out['month_end'].max().date()}")
    print(f"  CoMOM  mean={c.mean():.4f}  std={c.std():.4f}  min={c.min():.4f}  max={c.max():.4f}")
    print(f"  n_universe mean={out['n_universe'].mean():.1f}  n_winner mean={out['n_winner'].mean():.1f}")
    print("  최근 6개월:")
    for _, r in out.tail(6).iterrows():
        print(f"    {r['month_end'].date()}  CoMOM={r['comom']}  W={r['comom_winner']} L={r['comom_loser']}  N={r['n_universe']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-path", default=DB_PATH_DEFAULT)
    ap.add_argument("--ff3-cache", default=FF3_CACHE_DEFAULT)
    ap.add_argument("--parquet-out", default=PARQUET_OUT_DEFAULT)
    ap.add_argument("--max-months", type=int, default=None, help="최근 N개월만(스모크 테스트용)")
    ap.add_argument("--no-persist", action="store_true")
    args = ap.parse_args()
    try:
        df = build(
            db_path=args.db_path, ff3_cache=args.ff3_cache, parquet_out=args.parquet_out,
            max_months=args.max_months, persist=not args.no_persist,
        )
        _summary(df)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[build_comom] 실패: {type(e).__name__}: {e}\n")
        raise
