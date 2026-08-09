# -*- coding: utf-8 -*-
"""kr_safety_score — 필터 Step 3 안심점수 **부분** 검정.

사전등록 `docs/PREREG_BACKTEST_SAFETY_SCORE_2026_08_09.md` (PM 승인 2026-08-09).
🚨 관측 산출물만 만든다. 점수·집행 입력 0.

**왜**: PM 발화 "5000→25 필터링을 솔직히 못 믿겠음". `calculate_safety_score` 는
가중치가 아니라 **유니버스 진입 자격**을 정한다 — 여기서 떨어지면 채점 대상조차 아니다.
`VAMS_PROFILES["moderate"]["min_safety"]=55` 로 매수 자격에도 직접 쓰인다. 그런데
이 배점(PER 5~15→20점 · PBR≤1.0→15점 · 낙폭≤−30%→15점 …)은 **검정된 적이 없다.**

🚨 **100점 중 53점만 재현된다.** PER 20 · PBR 15 · 배당 12 는 PIT 소스가 없다
(주식수/BPS/배당 시계열 부재 — 8/8 이 Graham 을 폐기한 그 이유와 동일).
**결론을 safety_score 전체로 확대하지 말 것.**

그럼에도 지금 하는 이유 = 가장 의심되는 **낙폭 배점(15점)** 이 재현 가능한 쪽에 있다.
낙폭 −30% 에 15점은 mean reversion 베팅인데, 8/8 에서 그 축은 **불통과**(t 1.54/0.81)였다.

**운영 배점을 그대로 쓴다.** 구간 배점(15/10/5)을 연속값으로 바꾸지 않는다 — 바꾸면
운영 산식 검정이 아니라 다른 산식 검정이 된다(kr_price_axes 의 "운영 함수를 그대로" 정합).

🚨 **진입은 T+1 종가** · PIT 펀더멘털 지연 분기 +45일 / 사업 +90일.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from api.quant.backtest.kr_fundamental import (   # 8/8 과 같은 방법론 부품 재사용
    DELIST_PATH, HORIZONS, _calendar, _select_non_overlapping,
    exclusion_reason, load_names, load_universe, spearman, t_stat,
)
from api.quant.backtest.kr_price_axes import (
    COMMISSION, ENTRY_LAG, MIN_NAMES, SCENARIOS, SELL_TAX,
    forward_return, load_ohlcv,
)

# 🚨 사전등록 §4 는 **5분위**를 등록했다(10분위 금지 — GP/A 절단 artifact 전례).
#   kr_price_axes 기본값은 10 이므로 import 하지 않고 여기서 고정한다.
N_QUANTILE = 5

# 🚨 사전등록 §4 "리밸런스별 유효 종목 < 100 이면 그 시점 제외".
#   kr_price_axes 의 MIN_NAMES 는 30 이라 등록값보다 느슨하다 — 등록값을 따른다.
MIN_VALID = 100

# 🚨 정본 시나리오. 사전등록 §3 원장은 **12검정**(6축×2호라이즌)인데 코드는 시나리오
#   2개를 함께 계산한다 → 그대로 두면 24검정이 되어 원장을 위반한다.
#   §4 가 `DELIST_HAIRCUT 0.70` 을 등록값으로 고정했으므로 **haircut 적용 = conservative**
#   가 정본이다. optimistic 은 민감도 참고로만 싣고 판정에 쓰지 않는다.
PRIMARY_SCENARIO = "conservative"

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "data")
OUT_PATH = os.path.join(_DATA, "analysis", "prereg_safety_score_20260809.json")
PANEL_PATH = os.path.join(_DATA, "metadata", "kr_fundamental_panel.jsonl")

# 사전등록 §3 검정 원장 — 6축 × 2호라이즌 = 12검정. 사후 추가 금지.
AXES: Tuple[str, ...] = ("safety_partial", "drop", "trading_value", "debt", "op_margin", "roe")
BONFERRONI_T = 2.87            # α=.05 / 12검정 양측
# 사전등록 §0 — 재현 불가 배점(합 47). 산출물에 명시해 결론 확대를 막는다.
UNREPRODUCIBLE = {"per": 20, "pbr": 15, "div_yield": 12}
REPRODUCIBLE_TOTAL = 53

# PIT 공시 지연 (법정 제출기한). 사전등록 §4.
LAG_QUARTER_DAYS = 45
LAG_ANNUAL_DAYS = 90


# ── 운영 배점 그대로 (api/analyzers/stock_filter.calculate_safety_score 발췌) ──
def pts_drop(drop_pct: Optional[float]) -> Optional[int]:
    if drop_pct is None:
        return None
    if drop_pct <= -30:
        return 15
    if drop_pct <= -20:
        return 10
    if drop_pct <= -10:
        return 5
    return 0


def pts_trading_value(tv: Optional[float]) -> Optional[int]:
    """KR 기준. 운영은 US 를 따로 두나 이 검정은 KR-only 다."""
    if tv is None:
        return None
    if tv >= 50_000_000_000:
        return 12
    if tv >= 10_000_000_000:
        return 8
    if tv >= 1_000_000_000:
        return 4
    return 0


def pts_debt(debt: Optional[float]) -> Optional[int]:
    if debt is None:
        return None
    if 0 < debt <= 30:
        return 10
    if 30 < debt <= 60:
        return 6
    if debt == 0:
        return 3
    return 0


def pts_op_margin(m: Optional[float]) -> Optional[int]:
    if m is None:
        return None
    if m >= 15:
        return 10
    if m >= 8:
        return 6
    if m >= 3:
        return 3
    return 0


def pts_roe(r: Optional[float]) -> Optional[int]:
    if r is None:
        return None
    if r >= 15:
        return 6
    if r >= 8:
        return 4
    if r >= 3:
        return 2
    return 0


def nw_lag(horizon_days: int, rebalance_days: int = 21) -> int:
    """사전등록 §3 "Newey-West(lag=호라이즌)" 의 **단위 환산**.

    🚨 등록문은 lag 을 '호라이즌' 이라 썼지만 호라이즌은 **거래일**(20/60)이고
       IC 시계열은 **월간 리밸런스**다. lag=20 을 75개 월간 관측에 걸면 과적합돼
       NW 추정이 무너진다. 겹치는 기간 수로 환산한다 — 20일≈1개월→lag 0,
       60일≈3개월→lag 2. 데이터를 보기 **전에** 고정했다.
    """
    return max(0, -(-horizon_days // rebalance_days) - 1)


def nw_t(vals: Sequence[float], lag: int) -> Dict[str, Any]:
    """평균의 Newey-West t. 사전등록 §3 의 등록 판정통계량."""
    n = len(vals)
    if n < 3:
        return {"n": n, "mean": (round(sum(vals) / n, 6) if n else None), "t": None, "lag": lag}
    m = sum(vals) / n
    dev = [v - m for v in vals]
    g0 = sum(d * d for d in dev) / n
    S = g0
    for k in range(1, min(lag, n - 1) + 1):
        gk = sum(dev[i] * dev[i - k] for i in range(k, n)) / n
        S += 2 * (1 - k / (lag + 1)) * gk
    if S <= 0:                     # 절단 후 음수 분산 — 판정 불가로 신고한다
        return {"n": n, "mean": round(m, 6), "t": None, "lag": lag,
                "note": "NW 분산 ≤ 0 (Bartlett 절단) — 판정 불가"}
    se = math.sqrt(S / n)
    return {"n": n, "mean": round(m, 6), "t": round(m / se, 4), "lag": lag,
            "positive_rate": round(sum(1 for v in vals if v > 0) / n, 4)}


def bh_fdr(pvals: Sequence[Optional[float]], q: float = 0.05) -> List[Optional[bool]]:
    """Benjamini-Hochberg. 사전등록 §3 의 **1차 판정**. Bonferroni 는 참고치다."""
    idx = [i for i, v in enumerate(pvals) if v is not None]
    if not idx:
        return [None] * len(pvals)
    order = sorted(idx, key=lambda i: pvals[i])          # type: ignore[index,arg-type]
    m = len(order)
    cut = -1
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= q * rank / m:                      # type: ignore[operator]
            cut = rank
    out: List[Optional[bool]] = [None] * len(pvals)
    for i in idx:
        out[i] = False
    for rank, i in enumerate(order, start=1):
        if rank <= cut:
            out[i] = True
    return out


def two_sided_p(t: Optional[float], n: Optional[int]) -> Optional[float]:
    """t → 양측 p. df=n−1. n 이 작을 때 정규근사는 과신이므로 t 분포를 쓴다."""
    if t is None or not n or n < 2:
        return None
    from scipy import stats
    return float(2 * stats.t.sf(abs(float(t)), df=n - 1))


def _yyyymmdd_plus(day: int, n: int) -> int:
    from datetime import date, timedelta
    d = date(day // 10000, (day // 100) % 100, day % 100) + timedelta(days=n)
    return d.year * 10000 + d.month * 100 + d.day


def load_panel() -> Dict[str, List[Dict[str, Any]]]:
    """측정정화 패널 → {ticker: [{as_of_int, debt_ratio, roa, ...}]} (관측일 = 분기말+지연)."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    try:
        f = open(PANEL_PATH, encoding="utf-8")
    except OSError:
        return out
    with f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            qe = str(r.get("quarter_end") or "")
            if len(qe) != 10:
                continue
            q = int(qe[:4] + qe[5:7] + qe[8:10])
            # 🚨 quarter_end 는 회계 기준일이지 공개일이 아니다. 법정 제출기한만큼 늦춘다.
            lag = LAG_ANNUAL_DAYS if qe[5:7] == "12" else LAG_QUARTER_DAYS
            r["_as_of"] = _yyyymmdd_plus(q, lag)
            out.setdefault(str(r.get("ticker") or ""), []).append(r)
    for v in out.values():
        v.sort(key=lambda x: x["_as_of"])
    return out


def pit_panel(snaps: List[Dict[str, Any]], day: int) -> Optional[Dict[str, Any]]:
    """day 시점에 **공개돼 있던** 최신 분기. look-ahead 0."""
    i = bisect.bisect_right([s["_as_of"] for s in snaps], day) - 1
    return snaps[i] if i >= 0 else None


def build_row(t: str, s: Dict[str, List[float]], i: int,
              panel: Dict[str, List[Dict[str, Any]]], day: int) -> Optional[Dict[str, Any]]:
    """한 종목의 재현 가능 배점. 산출 불가 항목은 None (0점 대체 금지 — 사전등록 §4)."""
    close = s["c"]
    if i < 20:
        return None
    px = close[i]
    if not px or px <= 0:
        return None
    # 52주 고점 대비 — 운영과 같은 정의(고점 대비 하락률, 음수)
    lo = max(0, i - 251)
    hi = max(close[lo:i + 1])
    drop = ((px - hi) / hi * 100.0) if hi > 0 else None
    # 거래대금 — 20일 평균 (일별 단일값은 노이즈)
    tv = None
    vol = s.get("v")
    if vol and len(vol) > i:
        vals = [close[j] * vol[j] for j in range(max(0, i - 19), i + 1)
                if vol[j] is not None and close[j] is not None]
        if vals:
            tv = sum(vals) / len(vals)

    snaps = panel.get(t) or []
    p = pit_panel(snaps, day) if snaps else None
    debt = p.get("debt_ratio") if p else None
    roa = p.get("roa") if p else None
    gm = p.get("gross_margin") if p else None

    d_pts, tv_pts = pts_drop(drop), pts_trading_value(tv)
    de_pts, om_pts = pts_debt(debt), pts_op_margin(gm)
    roe_pts = pts_roe(roa)     # 🚨 근사 — 패널에 ROE 가 없어 ROA 로 대체. 산출물에 명시.

    parts = [d_pts, tv_pts, de_pts, om_pts, roe_pts]
    if all(v is None for v in parts):
        return None
    return {
        "t": t,
        "drop": d_pts, "trading_value": tv_pts, "debt": de_pts,
        "op_margin": om_pts, "roe": roe_pts,
        # 합산은 산출 가능한 항목만 — 결측을 0으로 채우면 결측이 저점수로 둔갑한다
        "safety_partial": (sum(v for v in parts if v is not None)
                           if sum(v is not None for v in parts) >= 3 else None),
    }


def load_ohlcv_duckdb(db_path: str) -> Dict[str, Dict[str, List[float]]]:
    """kr_prices.duckdb → load_ohlcv 와 같은 구조. 파일 레이크가 없을 때 쓴다.

    🚨 이 레이크는 종목별로 갱신이 멈춘 곳이 있다(2026-08-09 실측: 2,521종 중
       1,263 만 08-06 까지, 1,239 는 06-11~06-12 에서 정지 — us_prices 와 같은 증분 결함).
       그래서 뒤쪽 리밸런스는 유니버스가 줄어든다. **감추지 않고 coverage 에 신고한다.**
    """
    import duckdb
    con = duckdb.connect(db_path, read_only=True)
    try:
        rows = con.execute(
            "SELECT ticker, date, open, high, low, close, volume FROM ohlcv "
            "WHERE date >= DATE '2018-01-01' ORDER BY ticker, date").fetchall()
    finally:
        con.close()
    px: Dict[str, Dict[str, List[float]]] = {}
    for t, d, o, h, lo, c, v in rows:
        if c is None or float(c) <= 0:
            continue
        dd = d.year * 10000 + d.month * 100 + d.day
        s = px.setdefault(str(t), {"d": [], "o": [], "h": [], "l": [], "c": [], "v": []})
        cc = float(c)
        s["d"].append(dd)
        s["o"].append(float(o) if o and float(o) > 0 else cc)
        s["h"].append(float(h) if h and float(h) > 0 else cc)
        s["l"].append(float(lo) if lo and float(lo) > 0 else cc)
        s["c"].append(cc)
        s["v"].append(float(v) if v and float(v) >= 0 else 0.0)
    return {t: s for t, s in px.items() if len(s["d"]) >= 20}


def run(lake_dir: str, out_path: str = OUT_PATH, limit_rebalances: int = 0) -> Dict[str, Any]:
    t0 = time.time()
    universe = load_universe()
    names = load_names()
    px = (load_ohlcv_duckdb(lake_dir) if lake_dir.endswith(".duckdb")
          else load_ohlcv(lake_dir))
    panel = load_panel()
    try:
        with open(DELIST_PATH, encoding="utf-8") as f:
            dl = json.load(f) or {}
        latest = str(dl.get("as_of"))
        gone = {t for t, v in (dl.get("last_seen") or {}).items() if str(v) != latest}
    except (OSError, json.JSONDecodeError):
        gone = set()
    if not universe or not px or not panel:
        return {"status": "missing_input",
                "have": {"universe": len(universe), "prices": len(px), "panel": len(panel)}}

    cal = _calendar({t: {"d": s["d"], "c": s["c"]} for t, s in px.items()})
    rebalances: List[Dict[str, Any]] = []
    excl: Dict[str, int] = {}

    for as_of, tickers in universe:
        k = bisect.bisect_right(cal, int(as_of)) - 1
        if k < 0 or k + ENTRY_LAG + max(HORIZONS) >= len(cal):
            continue
        signal_day = cal[k]
        entry_day = cal[k + ENTRY_LAG]
        exits = {h: cal[k + ENTRY_LAG + h] for h in HORIZONS}

        rows: List[Dict[str, Any]] = []
        for t in tickers:
            why = exclusion_reason(t, names.get(t))
            if why:
                excl[why] = excl.get(why, 0) + 1
                continue
            s = px.get(t)
            if not s:
                continue
            i = bisect.bisect_right(s["d"], signal_day) - 1
            if i < 0 or s["d"][i] != signal_day:
                continue
            rec = build_row(t, s, i, panel, signal_day)
            if not rec:
                continue
            ok = False
            for h in HORIZONS:
                for scen in SCENARIOS:
                    r = forward_return(s, entry_day, exits[h],
                                       delisted=(t in gone),
                                       haircut=(scen == "conservative"))
                    if r is not None:
                        rec[f"r{h}_{scen}"] = round(r[0], 6)
                        ok = True
            if ok:
                rows.append(rec)
        if len(rows) < MIN_VALID:      # 사전등록 §4 등록값 100 (import 기본 30 아님)
            continue
        rebalances.append({"as_of": as_of, "entry_idx": k + ENTRY_LAG, "rows": rows})
        print(f"  [{len(rebalances)}] {as_of} → 진입 {entry_day} · {len(rows)}종목 "
              f"· {time.time() - t0:.0f}s", flush=True)
        if limit_rebalances and len(rebalances) >= limit_rebalances:
            break

    coverage = {
        "rebalances": len(rebalances),
        "window": ([rebalances[0]["as_of"], rebalances[-1]["as_of"]] if rebalances else None),
        "excluded": excl,
        "total_observations": sum(len(r["rows"]) for r in rebalances),
        "median_names": (sorted(len(r["rows"]) for r in rebalances)[len(rebalances) // 2]
                         if rebalances else 0),
        "elapsed_sec": round(time.time() - t0, 1),
    }
    if not rebalances:
        return {"status": "no_rebalances", "coverage": coverage}

    entry_idx = [r["entry_idx"] for r in rebalances]
    results: Dict[str, Any] = {}
    spreads: Dict[str, List[Optional[float]]] = {}

    for axis in AXES:
        for h in HORIZONS:
            for scen in SCENARIOS:
                key = f"{axis}_{h}d_{scen}"
                ics: List[Optional[float]] = []
                sprd: List[Optional[float]] = []
                for rb in rebalances:
                    xs, ys = [], []
                    for r in rb["rows"]:
                        v, ret = r.get(axis), r.get(f"r{h}_{scen}")
                        if v is None or ret is None:
                            continue
                        xs.append(float(v))
                        ys.append(float(ret))
                    ics.append(spearman(xs, ys) if len(xs) >= MIN_VALID else None)
                    if len(xs) >= N_QUANTILE * 3:
                        order = sorted(range(len(xs)), key=lambda i: xs[i])
                        kq = max(1, len(order) // N_QUANTILE)
                        lo_r = sum(ys[i] for i in order[:kq]) / kq
                        hi_r = sum(ys[i] for i in order[-kq:]) / kq
                        sprd.append((hi_r - lo_r) - 2 * (2 * COMMISSION + SELL_TAX))
                    else:
                        sprd.append(None)
                spreads[key] = sprd
                sel = _select_non_overlapping(entry_idx, h)
                nov = t_stat([ics[i] for i in sel if ics[i] is not None])
                nw = nw_t([v for v in ics if v is not None], nw_lag(h))
                results[key] = {
                    "ic_nw": nw,                     # 🚨 사전등록 §3 등록 판정통계량
                    "ic_naive": t_stat([v for v in ics if v is not None]),
                    "ic_non_overlap": nov,
                    "spread_naive": t_stat([v for v in sprd if v is not None]),
                    "spread_non_overlap": t_stat([sprd[i] for i in sel if sprd[i] is not None]),
                    "passes_bonferroni_ic": bool(
                        nov.get("t") is not None and abs(nov["t"]) >= BONFERRONI_T),
                }

    # ── 사전등록 §3 1차 판정: BH-FDR q=0.05, **정본 12검정에만** 적용 ──
    ledger = [f"{a}_{h}d_{PRIMARY_SCENARIO}" for a in AXES for h in HORIZONS]
    pv = [two_sided_p(results[k]["ic_nw"].get("t"), results[k]["ic_nw"].get("n"))
          for k in ledger]
    bh = bh_fdr(pv, q=0.05)
    for k, p_, ok in zip(ledger, pv, bh):
        results[k]["p_two_sided"] = (round(p_, 6) if p_ is not None else None)
        results[k]["passes_bh_fdr"] = ok
        results[k]["in_ledger"] = True
    for k in results:
        results[k].setdefault("in_ledger", False)   # 민감도(optimistic) = 판정 제외

    pbo: Dict[str, Any] = {"status": "skipped"}
    try:
        import numpy as np
        from api.quant.alpha.pbo import cscv_pbo
        keys = sorted(spreads)
        rowsel = [i for i in range(len(rebalances))
                  if all(spreads[k][i] is not None for k in keys)]
        if len(rowsel) >= 16 and len(keys) >= 2:
            pbo = cscv_pbo(np.array([[spreads[k][i] for k in keys] for i in rowsel],
                                    dtype=float))
    except Exception as e:  # noqa: BLE001
        pbo = {"status": "error", "detail": f"{type(e).__name__}: {e}"}

    doc = {
        "_meta": {
            "prereg": "docs/PREREG_BACKTEST_SAFETY_SCORE_2026_08_09.md",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00", time.localtime(time.time() + 9 * 3600)),
            "market": "KR-only",
            "entry": "T 신호 → T+1 종가",
            "pit_lag_days": {"quarter": LAG_QUARTER_DAYS, "annual": LAG_ANNUAL_DAYS},
            "tests": len(AXES) * len(HORIZONS),
            "primary_scenario": PRIMARY_SCENARIO,
            "scenario_note": ("사전등록 §3 원장 = 12검정. 코드가 시나리오 2개를 계산하므로 "
                              "§4 등록값 DELIST_HAIRCUT 0.70 이 적용되는 conservative 를 "
                              "정본으로 선언한다. optimistic 은 민감도이며 판정에 쓰지 않는다."),
            "judgment": ("1차 = 사전등록 §3 대로 Newey-West t → BH-FDR q=0.05. "
                         "비겹침 표본 t(8/8 방식)는 robustness 로 병기하며, "
                         "둘이 엇갈리면 골라잡지 않고 엇갈림을 그대로 보고한다."),
            "nw_lag_conversion": ("§3 'lag=호라이즌' 은 거래일 단위 표기다. IC 시계열이 "
                                  "월간이라 겹침 기간 수로 환산했다(20일→0, 60일→2). "
                                  "데이터 관측 전 고정."),
            "min_valid_names": MIN_VALID,
            "n_quantile": N_QUANTILE,
            "bonferroni_t": BONFERRONI_T,
            "min_detectable_ic": 0.041,
            "reproducible_points": REPRODUCIBLE_TOTAL,
            "unreproducible_points": UNREPRODUCIBLE,
            "roe_note": "패널에 ROE 부재 → ROA 로 근사. 운영 ROE 배점과 다를 수 있다.",
            "scope_warning": ("safety_score 100점 중 53점만 재현했다. "
                              "결론을 전체 점수로 확대하지 말 것(사전등록 §0)."),
        },
        "coverage": coverage,
        "results": results,
        "pbo": pbo,
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.replace(tmp, out_path)
    return doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lake", default=os.path.expanduser("~/VERITY_data_lake/kr_chart_history"))
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    r = run(a.lake, limit_rebalances=a.limit)
    if r.get("status") in ("missing_input", "no_rebalances"):
        print(f"[safety_score] {r['status']} — {json.dumps(r, ensure_ascii=False)[:300]}",
              file=sys.stderr)
        return 1
    c = r["coverage"]
    print(f"\n[safety_score] 리밸런스 {c['rebalances']} · 관측 {c['total_observations']:,} "
          f"· 중앙 종목수 {c['median_names']} · {c['elapsed_sec']}s")
    print(f"[safety_score] 재현 {REPRODUCIBLE_TOTAL}/100점 (PER 20·PBR 15·배당 12 불가)")
    sc = PRIMARY_SCENARIO
    print(f"[safety_score] 정본 시나리오 = {sc} (상폐 haircut 0.70 적용) · 판정 = BH-FDR q=.05")
    print(f"\n{'축':16}{'IC(20d)':>9}{'t':>7}{'p':>8}{'IC(60d)':>9}{'t':>7}{'p':>8}  BH")
    for axis in AXES:
        k20, k60 = f"{axis}_20d_{sc}", f"{axis}_60d_{sc}"
        a, b = r["results"][k20], r["results"][k60]
        r20, r60 = a["ic_nw"], b["ic_nw"]
        flags = [a.get("passes_bh_fdr"), b.get("passes_bh_fdr")]
        p = "통과" if any(f is True for f in flags) else "불통과"
        print(f"{axis:16}{(r20.get('mean') or 0):>9.4f}{(r20.get('t') or 0):>7.2f}"
              f"{(a.get('p_two_sided') if a.get('p_two_sided') is not None else float('nan')):>8.3f}"
              f"{(r60.get('mean') or 0):>9.4f}{(r60.get('t') or 0):>7.2f}"
              f"{(b.get('p_two_sided') if b.get('p_two_sided') is not None else float('nan')):>8.3f}  {p}")
    print(f"\nPBO: {r['pbo'].get('pbo', r['pbo'].get('status'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
