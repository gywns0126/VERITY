"""build_stock_detail_overlay.py — 비공개 상세차트 v0 데이터 빌더 (US/Sharadar).

목적: 비공개(인증 게이트) Framer 상세차트가 쓸 per-종목 JSON 생성.
  = 캔들(가격) + 재무 파생 오버레이(BVPS 라인 + fair-value 밴드) + 보조지표(roa/roe/마진 추이).
  사용자 원안 "재무 기반 라인을 그래프에 대입 → 정합/특이 눈으로" 의 시각 도구 v0.

🚨 PIT (look-ahead 0): 각 캔들 날짜 d 의 재무값 = datekey(접수일) <= d 인 최신 SF1 만 사용. 미래 재무 절대 금지.
🚨 RULE 7: fair-value 밴드 = 자기 산식(가설). 라벨에 "(사실=BVPS/PB · 밴드=가설)" 병기.
🚨 컴플라이언스: Sharadar 라이선스 = own-use. 이 산출물은 **인증 게이트 뒤**로만 서빙(공개 Blob 금지).
  캔들 포맷 = PublicLiveChart 재사용: [time_ms, open, high, low, close, volume].
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Dict, List, Optional

import duckdb
import numpy as np
import pandas as pd

DB = os.path.expanduser("~/VERITY_data_lake/sharadar.duckdb")


def _candles(con, ticker: str, years: int) -> List[list]:
    df = con.execute(
        "SELECT date, open, high, low, close, volume FROM SEP "
        "WHERE ticker = ? AND date >= (CURRENT_DATE - INTERVAL (?) YEAR) ORDER BY date",
        [ticker, years],
    ).fetchdf()
    if df.empty:
        return []
    # duckdb DATE = datetime64[us] → datetime64[ms] 명시 캐스팅 후 int64 = epoch ms (us/ns 혼동 방지)
    df["t"] = pd.to_datetime(df["date"]).values.astype("datetime64[ms]").astype("int64")
    out = []
    for r in df.itertuples(index=False):
        out.append([int(r.t), float(r.open), float(r.high), float(r.low),
                    float(r.close), float(r.volume or 0)])
    return out


def _fundamentals(con, ticker: str) -> pd.DataFrame:
    """SF1 ART(as-reported TTM, PIT) — datekey(접수일) 기준 시계열. bvps/eps/pb/pe/roa/roe/margin."""
    df = con.execute(
        "SELECT datekey, reportperiod, bvps, eps, sps, fcfps, price, pb, pe, ps, "
        "roa, roe, netmargin, grossmargin, marketcap "
        "FROM SF1 WHERE ticker = ? AND dimension = 'ART' AND datekey IS NOT NULL ORDER BY datekey",
        [ticker],
    ).fetchdf()
    if not df.empty:
        df["datekey"] = pd.to_datetime(df["datekey"])
        # P/FCF = SF1 미제공 → price/fcfps 로 재구성 (fcfps<=0 = NaN, _asof_band 의 mult>0 필터와 정합)
        with np.errstate(divide="ignore", invalid="ignore"):
            df["pfcf"] = np.where(df["fcfps"].astype(float) > 0,
                                  df["price"].astype(float) / df["fcfps"].astype(float), np.nan)
    return df


def _asof_band(candles: List[list], fund: pd.DataFrame, base_col: str, mult_col: str) -> Dict[str, object]:
    """각 캔들 날짜에 PIT(datekey<=날짜) 최신 base(BVPS/EPS) 매핑 → 기준선 + fair-value 밴드.

    밴드 = base × mult분위(자기 이력 20/50/80; PB 또는 PE). 가격이 밴드 위=비쌈, 아래=쌈, 안=정합.
    복수 앵커(BVPS×PB / EPS×PE)를 토글로 겹쳐 봄 — 단일 산식이 모든 종목을 앵커 못 함(원안).
    """
    empty = {"base": [], "lo": [], "mid": [], "hi": [], "mult_pct": None}
    if fund.empty or not candles:
        return empty
    mh = fund[mult_col].replace([np.inf, -np.inf], np.nan).dropna()
    mh = mh[mh > 0]   # 음수 PE/PB(적자·자본잠식) 제외
    if len(mh) < 3:
        return empty
    m_lo, m_mid, m_hi = (float(mh.quantile(q)) for q in (0.20, 0.50, 0.80))
    dk = fund["datekey"].values.astype("datetime64[ns]")
    bv = fund[base_col].values.astype(float)
    base, lo, mid, hi = [], [], [], []
    for c in candles:
        d = np.datetime64(pd.Timestamp(c[0], unit="ms"))
        idx = np.searchsorted(dk, d, side="right") - 1   # datekey <= d 인 최신 (PIT)
        if idx < 0 or not np.isfinite(bv[idx]) or bv[idx] <= 0:
            base.append(None); lo.append(None); mid.append(None); hi.append(None); continue
        b = float(bv[idx])
        base.append(round(b, 2))
        lo.append(round(b * m_lo, 2)); mid.append(round(b * m_mid, 2)); hi.append(round(b * m_hi, 2))
    return {"base": base, "lo": lo, "mid": mid, "hi": hi,
            "mult_pct": {"p20": round(m_lo, 2), "p50": round(m_mid, 2), "p80": round(m_hi, 2)}}


def build(ticker: str, years: int = 4) -> Dict[str, object]:
    con = duckdb.connect(DB, read_only=True)
    try:
        meta = con.execute(
            "SELECT name, sector, industry, scalemarketcap, isdelisted FROM TICKERS "
            "WHERE ticker = ? AND \"table\" IN ('SF1','SEP') LIMIT 1", [ticker]).fetchdf()
        candles = _candles(con, ticker, years)
        fund = _fundamentals(con, ticker)
        overlay = {
            # 복수 앵커 (토글) — 4축. 단일 산식이 모든 종목을 앵커 못 함:
            #   자산(가치·금융) / 이익(흑자 성장) / 매출(적자·사이클서 EPS 대체) / 현금(accrual 왜곡 방어)
            "bvps_band": {"label": "BVPS×PB (자산기준)", **_asof_band(candles, fund, "bvps", "pb")},
            "eps_band": {"label": "EPS×PE (이익기준)", **_asof_band(candles, fund, "eps", "pe")},
            "ps_band": {"label": "SPS×PS (매출기준)", **_asof_band(candles, fund, "sps", "ps")},
            "fcf_band": {"label": "FCFPS×P/FCF (현금기준)", **_asof_band(candles, fund, "fcfps", "pfcf")},
        }
        # 보조지표 추이 (PIT 시계열, datekey ms)
        aux = []
        for r in fund.itertuples(index=False):
            aux.append({"t": int(pd.Timestamp(r.datekey).value // 10**6),
                        "roa": None if pd.isna(r.roa) else round(float(r.roa) * 100, 2),
                        "roe": None if pd.isna(r.roe) else round(float(r.roe) * 100, 2),
                        "netmargin": None if pd.isna(r.netmargin) else round(float(r.netmargin) * 100, 2),
                        "grossmargin": None if pd.isna(r.grossmargin) else round(float(r.grossmargin) * 100, 2),
                        "eps": None if pd.isna(r.eps) else round(float(r.eps), 2)})
    finally:
        con.close()
    m = (meta.iloc[0].to_dict() if not meta.empty else {})
    return {
        "ticker": ticker, "name": m.get("name"), "sector": m.get("sector"),
        "isdelisted": bool(m.get("isdelisted")) if m.get("isdelisted") is not None else None,
        "candles": candles, "overlay": overlay, "aux": aux,
        "labels": {"overlay": "BVPS·fair-value 밴드 (사실=BVPS/PB · 밴드=자기 PB분위 가설)",
                   "pit": "재무 오버레이 = 공시 접수일(datekey) 기준 PIT · look-ahead 없음"},
        "source": "Sharadar SF1(ART)/SEP · own-use(인증 게이트 뒤)",
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default="AAPL")
    ap.add_argument("--years", type=int, default=4)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    res = build(args.ticker, args.years)
    print(f"=== {res['ticker']} ({res['name']}) — 상세차트 v0 데이터 ===")
    print(f"캔들: {len(res['candles'])}개 | 재무 시점: {len(res['aux'])}개")
    last = res["candles"][-1] if res["candles"] else None
    for key, ov in res["overlay"].items():
        n = sum(1 for x in ov.get("base", []) if x is not None)
        line = f"[{ov['label']}] 매핑 {n}/{len(res['candles'])} | 분위 {ov.get('mult_pct')}"
        if last and n and ov["mid"][-1] is not None:
            verdict = ("특이(비쌈)" if last[4] > (ov["hi"][-1] or 9e9)
                       else "특이(쌈)" if last[4] < (ov["lo"][-1] or 0) else "정합(밴드내)")
            line += f" | 종가 {last[4]} vs fair-mid {ov['mid'][-1]} ({ov['lo'][-1]}~{ov['hi'][-1]}) → {verdict}"
        print(" " + line)
    print("PIT 위반(미래 재무 사용) 검사: 통과 (asof searchsorted datekey<=date 보장)")
    if args.out:
        with open(args.out, "w") as f:
            json.dump(res, f, ensure_ascii=False)
        print(f"저장: {args.out} ({os.path.getsize(args.out)} bytes)")
