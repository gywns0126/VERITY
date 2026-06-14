"""
build_comom.py — CoMOM(Lou-Polk 2022) 팩터 crowding 분기 시계열 오케스트레이터 (CoMOM 파이프라인 §3 + §2 팩터일반화).

2026-06-14 신설(§3 모멘텀), 2026-06-14 확장(§2 co-value/co-quality 일반화).
입력 = sharadar_db.py 가 만든 로컬 DuckDB(SEP/SP500/ACTIONS/DAILY/SF1) + Kenneth French FF3(무료).
출력 = derived 테이블 `comom_factor_monthly`(long: factor 별 row) + parquet(데이터레이크).
🚨 라이선스: 로컬 전용(클라우드/cron 금지). 🚨 관측/측정 only (RULE 7) — 점수/brain 결정 wire 0.

CoMOM 일반화 (Lou-Polk 의 comomentum 을 임의 팩터로):
  형성분기말 t 마다 S&P500 PIT 멤버(survivorship-free) → 팩터점수 cross-sectional 십분위(top/bottom)
  → 그 종목들의 주간 FF3 잔차(trailing 52주) 상호상관 평균 = CoMOM. 높을수록 동일 팩터에 차익거래 집중.
  팩터: momentum(12-1) / value(B/M=1/pb) / quality(gross profitability=gp/assets, Novy-Marx 2013).

🚨 팩터별 부호 이질성 (Perplexity 자문, validate 가 측정): momentum=positive-feedback(crowding→이후 수익 하락,
  음의 forward) / value=negative-feedback(차익거래가 가격을 적정가로 → 오히려 +상관 가능) → 방향 가정 0.

🚨 schema gotcha(실측 2026-06-14):
  - SEP/SP500/DAILY = ticker 키(permaticker 없음). SEP=현재ticker로 엔티티 전체이력 →
    SP500 historical ticker 를 ACTIONS tickerchangeto bridge(매칭률 0.998 확정) 로 현재ticker 매핑 후 join.
  - SF1 사전계산 비율컬럼(roe/pb 등)=100% null → 원시필드(gp/assets/netinccmn/equity)서 자체파생.
  - SF1 = datekey(공시일=PIT 가용일) 기준 forward-fill. dimension='ART'(as-reported TTM). look-ahead 차단.
  - DAILY pb<=0(음수자본 7.8%)=value 부적격 제외. closeadj=배당/분할 조정가(수익률용, 글리치 0).

성능: SEP(3GB)/DAILY(2.3GB)/SF1(2.2GB) = CSV 뷰(쿼리마다 풀스캔) → SP500-ever 티커 필터로 *각 1회*
materialize 후 전부 메모리 패널화. 형성분기 루프는 in-memory 슬라이스.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Callable, Dict, List, Optional, Tuple

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
PARQUET_OUT_DEFAULT = os.path.expanduser("~/VERITY_data_lake/comom_factor_monthly.parquet")

MOM_LOOKBACK_M = 12     # 12-1 모멘텀 lookback
MOM_SKIP_M = 1          # 최근 1개월 skip (단기 반전 회피, Jegadeesh-Titman)
DECILE_FRAC = 0.10      # 상/하위 십분위
MIN_UNIVERSE = 30       # 형성분기 최소 유효 팩터점수 종목 (십분위 의미 확보)
FWD_HORIZONS_Q = [4, 8] # forward 팩터 스프레드 측정 분기(1년/2년) — §6 decay 검증용
FACTORS = ["momentum", "value", "quality"]


# --------------------------------------------------------------------------- #
# 1. 티커 변경 bridge (historical ticker → 현재 ticker)
# --------------------------------------------------------------------------- #
def build_ticker_bridge(con) -> Dict[str, str]:
    """ACTIONS tickerchange 로 historical→current 매핑. 체인 끝(terminal)까지 resolve.

    tickerchangeto 행: ticker=NEW, contraticker=OLD (방향=SEP 매칭률 0.998 로 확정). 미해결=자기자신.
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

    def resolve(t: str) -> str:
        seen = set()
        cur = t
        depth = 0
        while cur in edge and cur not in seen and depth < 20:
            seen.add(cur)
            cur = edge[cur]
            depth += 1
        return cur

    return {old_t: resolve(old_t) for old_t in edge}


# --------------------------------------------------------------------------- #
# 2. S&P500-ever 유니버스 + 원천 패널 materialize (각 뷰 풀스캔 1회)
# --------------------------------------------------------------------------- #
def sp500_member_panel(con, bridge: Dict[str, str]) -> pd.DataFrame:
    """SP500 PIT 멤버십(month_end, historical ticker) → bridge 로 current ticker 컬럼 추가."""
    df = con.execute("SELECT month_end, ticker FROM sp500_membership").fetchdf()
    df["month_end"] = pd.to_datetime(df["month_end"])
    df["cur_ticker"] = df["ticker"].map(lambda t: bridge.get(t, t))
    return df


def _semi_join_scan(con, tickers: List[str], sql: str) -> pd.DataFrame:
    """sp_tickers 임시 등록 후 semi-join 스캔 (IN 리스트 길이 한계 회피)."""
    tdf = pd.DataFrame({"ticker": sorted(set(tickers))})
    con.register("sp_tickers", tdf)
    try:
        return con.execute(sql).fetchdf()
    finally:
        con.unregister("sp_tickers")


def materialize_sep_panel(con, tickers: List[str]) -> pd.DataFrame:
    """SP500-ever 일별 (ticker, date, closeadj) 1회 materialize (가격, 글리치 closeadj>0)."""
    df = _semi_join_scan(con, tickers, """
        SELECT s.ticker, CAST(s.date AS DATE) AS date, s.closeadj
        FROM SEP s JOIN sp_tickers t ON s.ticker = t.ticker
        WHERE s.closeadj IS NOT NULL AND s.closeadj > 0
        ORDER BY s.ticker, s.date
    """)
    df["date"] = pd.to_datetime(df["date"])
    return df


def materialize_daily_pb(con, tickers: List[str]) -> pd.DataFrame:
    """SP500-ever 일별 (ticker, date, pb) — value(B/M=1/pb)용. pb>0(음수자본 제외)."""
    df = _semi_join_scan(con, tickers, """
        SELECT d.ticker, CAST(d.date AS DATE) AS date, d.pb
        FROM DAILY d JOIN sp_tickers t ON d.ticker = t.ticker
        WHERE d.pb IS NOT NULL AND d.pb > 0
        ORDER BY d.ticker, d.date
    """)
    df["date"] = pd.to_datetime(df["date"])
    return df


def materialize_sf1_quality(con, tickers: List[str]) -> pd.DataFrame:
    """SP500-ever SF1 ART (ticker, datekey, gp, assets) — quality(gp/assets)용. PIT=datekey.

    dimension='ART'(as-reported TTM). 사전계산 비율 null 이라 원시필드서 파생. assets>0, gp not null.
    """
    df = _semi_join_scan(con, tickers, """
        SELECT s.ticker, CAST(s.datekey AS DATE) AS datekey, s.gp, s.assets
        FROM SF1 s JOIN sp_tickers t ON s.ticker = t.ticker
        WHERE s.dimension = 'ART' AND s.gp IS NOT NULL AND s.assets IS NOT NULL AND s.assets > 0
        ORDER BY s.ticker, s.datekey
    """)
    df["datekey"] = pd.to_datetime(df["datekey"])
    df["gpoa"] = df["gp"] / df["assets"]   # gross profitability (Novy-Marx 2013)
    return df


# --------------------------------------------------------------------------- #
# 3. 패널 (월말 인덱스 정합)
# --------------------------------------------------------------------------- #
def build_price_panels(sep: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """일별 closeadj → (monthly_close: 월말×ticker, weekly_ret: 금요일×ticker)."""
    s = sep.set_index("date")
    monthly = s.groupby("ticker")["closeadj"].resample("ME").last().reset_index()
    monthly_close = monthly.pivot(index="date", columns="ticker", values="closeadj")
    monthly_close.index = monthly_close.index.to_period("M").to_timestamp("M")

    weekly_px = s.groupby("ticker")["closeadj"].resample("W-FRI").last()
    weekly_close = weekly_px.reset_index().pivot(index="date", columns="ticker", values="closeadj")
    # fill_method=None: 휴장 주는 0수익 조작 대신 NaN → 종목별 dropna 에서 제거(잔차 정합)
    weekly_ret = weekly_close.pct_change(fill_method=None)
    return monthly_close, weekly_ret


def build_value_panel(daily_pb: pd.DataFrame, month_index: pd.DatetimeIndex) -> pd.DataFrame:
    """일별 pb → 월말 B/M(=1/pb) 패널 (월말×ticker), monthly_close 인덱스 정합."""
    s = daily_pb.set_index("date")
    monthly_pb = s.groupby("ticker")["pb"].resample("ME").last().reset_index()
    pb_panel = monthly_pb.pivot(index="date", columns="ticker", values="pb")
    pb_panel.index = pb_panel.index.to_period("M").to_timestamp("M")
    bm = 1.0 / pb_panel.where(pb_panel > 0)
    return bm.reindex(month_index)


def build_quality_panel(sf1: pd.DataFrame, month_index: pd.DatetimeIndex) -> pd.DataFrame:
    """SF1 ART gpoa → datekey 기준 월말 forward-fill 패널 (look-ahead 차단). 월말×ticker."""
    piv = sf1.pivot_table(index="datekey", columns="ticker", values="gpoa", aggfunc="last")
    full = piv.index.union(month_index)
    return piv.reindex(full).sort_index().ffill().reindex(month_index)


# --------------------------------------------------------------------------- #
# 4. 팩터 점수 / 십분위 / forward 스프레드
# --------------------------------------------------------------------------- #
def momentum_12_1(monthly_close: pd.DataFrame, formation: pd.Timestamp) -> pd.Series:
    """12-1 모멘텀: closeadj(t-1M) / closeadj(t-13M) - 1 (최근 1M skip)."""
    months = monthly_close.index
    if formation not in months:
        return pd.Series(dtype=float)
    pos = months.get_loc(formation)
    p_recent = pos - MOM_SKIP_M
    p_old = pos - MOM_SKIP_M - MOM_LOOKBACK_M
    if p_old < 0:
        return pd.Series(dtype=float)
    mom = (monthly_close.iloc[p_recent] / monthly_close.iloc[p_old]) - 1.0
    return mom.replace([np.inf, -np.inf], np.nan).dropna()


def factor_score(factor: str, formation: pd.Timestamp, panels: Dict[str, pd.DataFrame]) -> pd.Series:
    """팩터별 형성분기말 cross-sectional 점수 (높을수록 top leg). dropna."""
    if factor == "momentum":
        return momentum_12_1(panels["monthly_close"], formation)
    panel = panels.get({"value": "value", "quality": "quality"}[factor])
    if panel is None or formation not in panel.index:
        return pd.Series(dtype=float)
    return panel.loc[formation].dropna()


def extreme_deciles(score: pd.Series, members: set) -> Optional[Dict[str, List[str]]]:
    """유니버스 내 점수 → 상/하위 십분위 {top:[고점수], bottom:[저점수]}."""
    m = score[score.index.isin(members)].dropna()
    if len(m) < MIN_UNIVERSE:
        return None
    n = max(1, int(round(len(m) * DECILE_FRAC)))
    ranked = m.sort_values()
    return {"top": list(ranked.index[-n:]), "bottom": list(ranked.index[:n])}


def forward_spread_return(
    monthly_close: pd.DataFrame, formation: pd.Timestamp,
    legs: Dict[str, List[str]], k_quarters: int,
) -> Optional[float]:
    """top−bottom 동일가중 스프레드를 forward k분기 보유한 *실현* 수익률 (look-ahead 아님)."""
    months = monthly_close.index
    if formation not in months:
        return None
    pos = months.get_loc(formation)
    tgt = pos + k_quarters * 3
    if tgt >= len(months):
        return None
    p0, p1 = monthly_close.iloc[pos], monthly_close.iloc[tgt]

    def _basket(tks: List[str]) -> Optional[float]:
        r = []
        for t in tks:
            a, b = p0.get(t), p1.get(t)
            if a is not None and b is not None and pd.notna(a) and pd.notna(b) and a > 0:
                r.append(b / a - 1.0)
        return float(np.mean(r)) if len(r) >= 5 else None

    top, bot = _basket(legs.get("top") or []), _basket(legs.get("bottom") or [])
    if top is None or bot is None:
        return None
    return round(top - bot, 4)


def comom_for_factor(
    factor: str, formation: pd.Timestamp, score: pd.Series,
    panels: Dict[str, pd.DataFrame], members: set, ff3: pd.DataFrame,
    window: int = WINDOW_WEEKS,
) -> Optional[Dict[str, object]]:
    """단일 (factor, 형성분기) CoMOM + forward 스프레드. 계산 불가 → None."""
    if score.empty:
        return None
    legs = extreme_deciles(score, members)
    if legs is None:
        return None

    weekly_ret = panels["weekly_ret"]
    wk = weekly_ret.loc[weekly_ret.index <= formation]   # look-ahead 차단
    if wk.empty:
        return None
    needed = set(legs["top"]) | set(legs["bottom"])
    weekly_returns: Dict[str, pd.Series] = {}
    for t in needed:
        if t in wk.columns:
            s = wk[t].dropna()
            if not s.empty:
                weekly_returns[t] = s

    res = compute_comom(weekly_returns, {factor: legs}, ff3, window=window)
    fr = res.get(factor, {})
    rec = {
        "month_end": formation,
        "factor": factor,
        "comom": fr.get("comom"),
        "comom_top": fr.get("comom_winner"),       # top leg(고점수) = compute_comom 'winner' 위치
        "comom_bottom": fr.get("comom_loser"),     # bottom leg(저점수)
        "n_top": fr.get("n_winner"),
        "n_bottom": fr.get("n_loser"),
        "n_universe": int(len(score[score.index.isin(members)].dropna())),
    }
    for k in FWD_HORIZONS_Q:
        rec[f"fwd_spread_{k}q"] = forward_spread_return(panels["monthly_close"], formation, legs, k)
    return rec


# --------------------------------------------------------------------------- #
# 5. 오케스트레이터
# --------------------------------------------------------------------------- #
def build(
    db_path: str = DB_PATH_DEFAULT,
    ff3_cache: str = FF3_CACHE_DEFAULT,
    parquet_out: str = PARQUET_OUT_DEFAULT,
    factors: Optional[List[str]] = None,
    max_quarters: Optional[int] = None,
    persist: bool = True,
) -> pd.DataFrame:
    """전 구간(또는 최근 max_quarters) 팩터별 CoMOM 분기 시계열 빌드 + derived 보존."""
    import duckdb

    factors = factors or FACTORS
    con = duckdb.connect(db_path)
    try:
        log = logging.getLogger("build_comom")

        bridge = build_ticker_bridge(con)
        sp = sp500_member_panel(con, bridge)
        sp_curr = sorted(sp["cur_ticker"].dropna().unique().tolist())
        log.info("S&P500-ever current 티커: %d (bridge edges %d)", len(sp_curr), len(bridge))

        sep = materialize_sep_panel(con, sp_curr)
        matched = sp["cur_ticker"].isin(set(sep["ticker"].unique())).mean()
        log.info("SP500 멤버-행 SEP closeadj 매칭률: %.3f (bridge 방향 검증)", matched)
        monthly_close, weekly_ret = build_price_panels(sep)
        panels: Dict[str, pd.DataFrame] = {"monthly_close": monthly_close, "weekly_ret": weekly_ret}

        if "value" in factors:
            panels["value"] = build_value_panel(materialize_daily_pb(con, sp_curr), monthly_close.index)
            log.info("value(B/M) 패널: %d 분기 × %d 티커", *panels["value"].shape)
        if "quality" in factors:
            panels["quality"] = build_quality_panel(materialize_sf1_quality(con, sp_curr), monthly_close.index)
            log.info("quality(gp/assets) 패널: %d 분기 × %d 티커", *panels["quality"].shape)

        ff3 = fetch_ff3_weekly(cache_path=ff3_cache)
        ff3 = ff3[~ff3.index.duplicated(keep="last")].sort_index()

        formations = [pd.Timestamp(f) for f in sorted(sp["month_end"].unique())]
        if max_quarters:
            formations = formations[-max_quarters:]
        members_by_q = {pd.Timestamp(me): set(g["cur_ticker"].dropna()) for me, g in sp.groupby("month_end")}

        rows = []
        for f in formations:
            f_me = pd.Timestamp(f).to_period("M").to_timestamp("M")
            members = members_by_q.get(pd.Timestamp(f), set())
            if not members:
                continue
            for factor in factors:
                score = factor_score(factor, f_me, panels)
                rec = comom_for_factor(factor, f_me, score, panels, members, ff3)
                if rec is not None and rec.get("comom") is not None:
                    rows.append(rec)

        _cols = ["month_end", "factor", "comom", "comom_top", "comom_bottom", "n_top", "n_bottom",
                 "n_universe"] + [f"fwd_spread_{k}q" for k in FWD_HORIZONS_Q]
        out = (pd.DataFrame(rows).sort_values(["factor", "month_end"]).reset_index(drop=True)
               if rows else pd.DataFrame(columns=_cols))
        for fac in factors:
            log.info("  %s: %d 분기", fac, int((out["factor"] == fac).sum()) if not out.empty else 0)

        if persist and not out.empty:
            con.execute("DROP TABLE IF EXISTS comom_factor_monthly")
            con.execute("DROP TABLE IF EXISTS comom_monthly")  # §3 momentum-only SoT 폐기(long 으로 통합)
            con.register("comom_df", out)
            con.execute("CREATE TABLE comom_factor_monthly AS SELECT * FROM comom_df")
            con.unregister("comom_df")
            os.makedirs(os.path.dirname(parquet_out), exist_ok=True)
            out.to_parquet(parquet_out)
            old_parquet = os.path.join(os.path.dirname(parquet_out), "comom_monthly.parquet")
            if os.path.exists(old_parquet):
                os.remove(old_parquet)  # 폐기된 momentum-only 산출 정리
            log.info("저장: comom_factor_monthly(DuckDB) + %s", parquet_out)

        return out
    finally:
        con.close()


def _summary(out: pd.DataFrame) -> None:
    if out.empty:
        print("[build_comom] 산출 0행")
        return
    print(f"[build_comom] 총 {len(out)}행 (long, factor×분기)")
    for fac, g in out.groupby("factor"):
        c = g["comom"].astype(float)
        print(f"=== {fac} ({len(g)}분기 {g['month_end'].min().date()}~{g['month_end'].max().date()}) ===")
        print(f"  CoMOM mean={c.mean():.4f} std={c.std():.4f} min={c.min():.4f} max={c.max():.4f}"
              f"  n_universe~{g['n_universe'].mean():.0f}")
        for _, r in g.tail(3).iterrows():
            print(f"    {r['month_end'].date()}  CoMOM={r['comom']}  top={r['comom_top']} bot={r['comom_bottom']}  N={r['n_universe']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-path", default=DB_PATH_DEFAULT)
    ap.add_argument("--ff3-cache", default=FF3_CACHE_DEFAULT)
    ap.add_argument("--parquet-out", default=PARQUET_OUT_DEFAULT)
    ap.add_argument("--factors", nargs="*", default=None, help=f"기본 {FACTORS}")
    ap.add_argument("--max-quarters", type=int, default=None, help="최근 N분기만(스모크)")
    ap.add_argument("--no-persist", action="store_true")
    args = ap.parse_args()
    try:
        df = build(
            db_path=args.db_path, ff3_cache=args.ff3_cache, parquet_out=args.parquet_out,
            factors=args.factors, max_quarters=args.max_quarters, persist=not args.no_persist,
        )
        _summary(df)
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(f"[build_comom] 실패: {type(e).__name__}: {e}\n")
        raise
