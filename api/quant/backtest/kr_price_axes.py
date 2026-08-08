# -*- coding: utf-8 -*-
"""kr_price_axes — KR 가격 파생 4축 백테스트.

사전등록 `docs/PREREG_BACKTEST_KR_PRICE_AXES.md` (PM 승인 안 가, 2026-08-08).
🚨 관측 산출물만 만든다. 점수·집행 입력 0.

**왜 이 축들인가**: 앞선 v1.1 백테스트가 검정한 것은 최종 점수 가중 **4.8%**
(quality 8% 중 F-Score·GP/A)였다. 반면 여기 4축은 **39%** 다 —
technical 17 · momentum 10 · volatility 6 · mean_reversion 6 (BASE_WEIGHTS).
전부 OHLCV 파생이라 DART·공시·감성 같은 결측 문제가 없고, 재료는 이미 디스크에 있다.

**운영 함수를 그대로 부른다.** 산식을 새로 쓰지 않는다 — 직접 구현하면 그건 운영
산식 검정이 아니라 다른 산식 검정이다. technical 은 `analyze_technical` 이 함수 안에서
yfinance 를 호출해 과거 재현이 불가능했으므로 `analyze_technical_from_ohlcv` 로
**이동만** 분리했다(`tests/test_technical_extraction.py` 가 origin/main 원본과 대조 고정).

🚨 **진입은 T+1 종가다** (v1.1 은 T 종가였다). 가격 파생 신호는 T 종가로 계산하므로
   그 종가에 사는 것은 불가능하다. T 신호 → T+1 종가 진입, 지평도 T+1 부터 센다.
   이 한 줄이 없으면 결과 전체가 거래 불가능한 숫자가 된다.

🚨 **bid-ask bounce 는 완화될 뿐 제거되지 않는다.** 과매도 신호는 종가가 매수호가에
   체결된 종목과 상관되고, 종가→종가 수익률은 그 기계적 반등을 신호로 오인한다.
   T+1 진입이 1거래일을 건너뛰지만 잔존한다 — mean_reversion 결과에 유보가 따라붙는다.

🚨 **단면 모집단이 운영과 다르다.** 여기서는 PIT 전체 유니버스(약 1,400종목)에서
   순위를 내지만 운영은 후보 25종목 안에서 낸다. 팩터 유효성 검정이지 배선 재현이 아니다.
"""
from __future__ import annotations

import argparse
import bisect
import glob
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from api.quant.backtest.kr_fundamental import (   # v1.1 과 같은 방법론 부품 재사용
    DELIST_HAIRCUT,
    DELIST_PATH,
    MIN_NAMES,
    N_QUANTILE,
    SELL_TAX,
    COMMISSION,
    _DATA,
    _calendar,
    _select_non_overlapping,
    exclusion_reason,
    load_names,
    load_universe,
    spearman,
    t_stat,
)

OUT_PATH = os.path.join(_DATA, "backtest_kr_price_axes.json")
TRAIL_PATH = os.path.join(_DATA, "backtest_kr_price_axes_trail.jsonl")
DELIST_CHUNKS = os.path.join(_DATA, "kr_chart_delisted", "chunk_*.json")

# ── 사전등록 고정 상수 (실행 중 변경 금지) ─────────────────────────────────
AXES: Tuple[str, ...] = ("technical", "momentum", "volatility", "mean_reversion")
HORIZONS: Tuple[int, ...] = (20, 60)
SCENARIOS: Tuple[str, ...] = ("optimistic", "conservative")
ENTRY_LAG = 1                  # 🚨 T 신호 → T+1 종가 진입
LOOKBACK = 252                 # technical 이 보는 창 (운영 period="1y")
MOM_OFFSETS = {"price_1m": 21, "price_3m": 63, "price_6m": 126, "price_12m": 252}
BONFERRONI_T = 2.73            # 4축 × 2지평 = 8검정, α=0.05/8. 🚨 낮추지 않는다


# ══════════════════════════════════════════════════════════════════════════
# 로딩
# ══════════════════════════════════════════════════════════════════════════
def load_ohlcv(lake_dir: str) -> Dict[str, Dict[str, List[float]]]:
    """{ticker: {d,o,h,l,c,v}} — 현 상장(레이크) + 소멸(청크). 봉 수 많은 쪽 채택."""
    px: Dict[str, Dict[str, List[float]]] = {}

    def _absorb(t: str, candles: Sequence[Sequence]) -> None:
        if not candles or len(candles) < 20:
            return
        prev = px.get(t)
        if prev and len(prev["d"]) >= len(candles):
            return
        d, o, h, lo, c, v = [], [], [], [], [], []
        for row in candles:
            try:
                dd, oo, hh, ll, cc, vv = (int(row[0]), float(row[1]), float(row[2]),
                                          float(row[3]), float(row[4]), float(row[5]))
            except (TypeError, ValueError, IndexError):
                continue
            if cc <= 0:
                continue
            d.append(dd)
            # 🚨 시가/고가/저가가 0 인 행이 있다(FSC 일부 종목). 종가로 대체한다 —
            #    0 을 그대로 두면 ATR·볼린저가 폭주한다. 결측 ≠ 0.
            o.append(oo if oo > 0 else cc)
            h.append(hh if hh > 0 else cc)
            lo.append(ll if ll > 0 else cc)
            c.append(cc)
            v.append(vv if vv >= 0 else 0.0)
        if len(d) >= 20:
            px[t] = {"d": d, "o": o, "h": h, "l": lo, "c": c, "v": v}

    for p in glob.glob(os.path.join(lake_dir, "*.json")):
        t = os.path.splitext(os.path.basename(p))[0]
        if len(t) != 6 or not t.isdigit():
            continue
        try:
            with open(p, encoding="utf-8") as f:
                _absorb(t, (json.load(f) or {}).get("c") or [])
        except (OSError, json.JSONDecodeError):
            continue

    for p in sorted(glob.glob(DELIST_CHUNKS)):
        try:
            with open(p, encoding="utf-8") as f:
                for t, ent in ((json.load(f) or {}).get("stocks") or {}).items():
                    _absorb(str(t), (ent or {}).get("c") or [])
        except (OSError, json.JSONDecodeError):
            continue
    return px


# ══════════════════════════════════════════════════════════════════════════
# 시점별 stock dict 구성 — 운영 함수가 읽는 필드를 그대로 채운다
# ══════════════════════════════════════════════════════════════════════════
def build_stock(t: str, s: Dict[str, List[float]], i: int) -> Optional[Dict[str, Any]]:
    """신호 시점 i(그 종목 자기 인덱스)까지의 정보만으로 stock dict 구성.

    🚨 i 이후를 절대 참조하지 않는다 — look-ahead 차단의 전부다.
    """
    if i < 19:
        return None                       # 최소 20봉 (technical 요구)
    import pandas as pd
    from api.analyzers.technical import analyze_technical_from_ohlcv

    lo = max(0, i - LOOKBACK + 1)
    close = pd.Series(s["c"][lo:i + 1], dtype=float)
    high = pd.Series(s["h"][lo:i + 1], dtype=float)
    low = pd.Series(s["l"][lo:i + 1], dtype=float)
    vol = pd.Series(s["v"][lo:i + 1], dtype=float)

    tech = analyze_technical_from_ohlcv(close, high, low, vol, ticker=t)
    price = float(s["c"][i])
    hist = s["c"][lo:i + 1]

    stock: Dict[str, Any] = {
        "ticker": t, "price": price,
        "technical": tech, "price_history": hist,
        "high_52w": max(hist), "low_52w": min(hist),
    }
    for key, back in MOM_OFFSETS.items():
        j = i - back
        stock[key] = float(s["c"][j]) if j >= 0 else None
    return stock


def score_axes(stock: Dict[str, Any], universe: List[Dict[str, Any]],
               universe_stats: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """4축 점수 — 운영 함수를 그대로 호출한다."""
    from api.quant.factors.mean_reversion import compute_mean_reversion_score
    from api.quant.factors.momentum import compute_momentum_score
    from api.quant.factors.volatility import compute_volatility_score

    out: Dict[str, Optional[float]] = {}
    tech = stock.get("technical") or {}
    ts = tech.get("technical_score")
    out["technical"] = float(ts) if isinstance(ts, (int, float)) else None
    for axis, fn, kw in (
        ("momentum", compute_momentum_score, {"universe": universe}),
        ("volatility", compute_volatility_score, {"universe_stats": universe_stats}),
        ("mean_reversion", compute_mean_reversion_score, {}),
    ):
        try:
            r = fn(stock, **kw) or {}
            v = r.get(f"{axis}_score")
            out[axis] = float(v) if isinstance(v, (int, float)) else None
        except Exception:  # noqa: BLE001 — 개별 종목 실패는 관측 제외로 처리
            out[axis] = None
    return out


def _universe_stats(stocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """volatility 가 읽는 단면 통계. 🚨 PIT 전체 기준 — 운영(후보 25종목)과 다르다."""
    from api.quant.factors.volatility import _compute_vols_from_history
    vols = []
    for s in stocks:
        h = s.get("price_history") or []
        if len(h) >= 20:
            v20, _ = _compute_vols_from_history(h)
            if isinstance(v20, (int, float)) and v20 > 0:
                vols.append(v20)
    if not vols:
        return {}
    vols.sort()
    return {"median_vol_20d": vols[len(vols) // 2]}


# ══════════════════════════════════════════════════════════════════════════
# 수익률 — T+1 진입
# ══════════════════════════════════════════════════════════════════════════
def forward_return(s: Dict[str, List[float]], entry_day: int, exit_day: int,
                   delisted: bool, haircut: bool) -> Optional[Tuple[float, str]]:
    """(수익률, 처리모드). entry_day = T+1. 산출 불가면 None."""
    d = s["d"]
    ei = bisect.bisect_right(d, entry_day) - 1
    if ei < 0 or d[ei] != entry_day:
        return None                        # T+1 에 거래가 없으면 진입 불가 — 버린다
    e_px = s["c"][ei]
    if d[-1] >= exit_day:
        xi = bisect.bisect_right(d, exit_day) - 1
        if xi < 0:
            return None
        return (s["c"][xi] / e_px - 1.0, "normal")
    if not delisted:
        return None                        # 단순 데이터 공백 — 결측 ≠ 실패
    return (s["c"][-1] * (DELIST_HAIRCUT if haircut else 1.0) / e_px - 1.0, "delisted")


# ══════════════════════════════════════════════════════════════════════════
# 실행
# ══════════════════════════════════════════════════════════════════════════
def run(lake_dir: str, out_path: str = OUT_PATH, trail_path: str = TRAIL_PATH,
        limit_rebalances: int = 0) -> Dict[str, Any]:
    t0 = time.time()
    universe = load_universe()
    names = load_names()
    px = load_ohlcv(lake_dir)
    try:
        with open(DELIST_PATH, encoding="utf-8") as f:
            dl = json.load(f) or {}
        latest = str(dl.get("as_of"))
        gone = {t for t, v in (dl.get("last_seen") or {}).items() if str(v) != latest}
    except (OSError, json.JSONDecodeError):
        gone = set()
    if not universe or not px:
        return {"status": "missing_input",
                "have": {"universe": len(universe), "prices": len(px)}}

    cal = _calendar({t: {"d": s["d"], "c": s["c"]} for t, s in px.items()})
    rebalances: List[Dict[str, Any]] = []
    trail: List[Dict[str, Any]] = []
    excl_tally: Dict[str, int] = {}

    for as_of, tickers in universe:
        k = bisect.bisect_right(cal, int(as_of)) - 1
        if k < 0:
            continue
        signal_day = cal[k]
        if k + ENTRY_LAG + max(HORIZONS) >= len(cal):
            continue
        entry_day = cal[k + ENTRY_LAG]                    # 🚨 T+1 종가 진입
        exits = {h: cal[k + ENTRY_LAG + h] for h in HORIZONS}

        stocks: List[Dict[str, Any]] = []
        for t in tickers:
            why = exclusion_reason(t, names.get(t))
            if why:
                excl_tally[why] = excl_tally.get(why, 0) + 1
                continue
            s = px.get(t)
            if not s:
                continue
            i = bisect.bisect_right(s["d"], signal_day) - 1
            if i < 0 or s["d"][i] != signal_day:
                continue                                   # 그날 거래 없음 = 신호 없음
            st = build_stock(t, s, i)
            if st:
                stocks.append(st)
        if len(stocks) < MIN_NAMES:
            continue

        ustats = _universe_stats(stocks)
        rows: List[Dict[str, Any]] = []
        for st in stocks:
            sc = score_axes(st, stocks, ustats)
            if all(v is None for v in sc.values()):
                continue
            s = px[st["ticker"]]
            rec: Dict[str, Any] = {"t": st["ticker"], **sc}
            ok = False
            for h in HORIZONS:
                for scen in SCENARIOS:
                    r = forward_return(s, entry_day, exits[h],
                                       delisted=(st["ticker"] in gone),
                                       haircut=(scen == "conservative"))
                    if r is not None:
                        rec[f"r{h}_{scen}"] = round(r[0], 6)
                        rec[f"m{h}"] = r[1]
                        ok = True
            if ok:
                rows.append(rec)
        if len(rows) < MIN_NAMES:
            continue
        rebalances.append({"as_of": as_of, "entry_idx": k + ENTRY_LAG, "rows": rows})
        trail.append({"as_of": as_of, "signal_day": signal_day, "entry_day": entry_day,
                      "n_scored": len(rows), "n_universe": len(tickers),
                      "n_delisted_exit": sum(1 for r in rows if any(
                          r.get(f"m{h}") == "delisted" for h in HORIZONS))})
        print(f"  [{len(rebalances)}] {as_of} 신호 {signal_day} → 진입 {entry_day} · "
              f"{len(rows)}종목 · {time.time() - t0:.0f}s", flush=True)
        if limit_rebalances and len(rebalances) >= limit_rebalances:
            break

    coverage = {
        "rebalances": len(rebalances),
        "window": ([rebalances[0]["as_of"], rebalances[-1]["as_of"]] if rebalances else None),
        "excluded": excl_tally,
        "median_names": (sorted(len(r["rows"]) for r in rebalances)[len(rebalances) // 2]
                         if rebalances else 0),
        "total_observations": sum(len(r["rows"]) for r in rebalances),
        "delisted_exits": sum(t["n_delisted_exit"] for t in trail),
        "elapsed_sec": round(time.time() - t0, 1),
    }
    if not rebalances:
        return {"status": "no_rebalances", "coverage": coverage}

    entry_idx = [r["entry_idx"] for r in rebalances]
    results: Dict[str, Any] = {}
    spreads: Dict[str, List[Optional[float]]] = {}
    ic_series: Dict[str, List[Optional[float]]] = {}

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
                    ics.append(spearman(xs, ys) if len(xs) >= MIN_NAMES else None)
                    if len(xs) >= N_QUANTILE * 3:
                        order = sorted(range(len(xs)), key=lambda i: xs[i])
                        kq = max(1, len(order) // N_QUANTILE)
                        lo_r = sum(ys[i] for i in order[:kq]) / kq
                        hi_r = sum(ys[i] for i in order[-kq:]) / kq
                        sprd.append((hi_r - lo_r) - 2 * (2 * COMMISSION + SELL_TAX))
                    else:
                        sprd.append(None)
                spreads[key] = sprd
                if scen == "optimistic" and h == 20:
                    ic_series[axis] = ics
                sel = _select_non_overlapping(entry_idx, h)
                results[key] = {
                    "ic_naive": t_stat([v for v in ics if v is not None]),
                    "ic_non_overlap": t_stat([ics[i] for i in sel if ics[i] is not None]),
                    "spread_naive": t_stat([v for v in sprd if v is not None]),
                    "spread_non_overlap": t_stat([sprd[i] for i in sel if sprd[i] is not None]),
                    "passes_bonferroni_ic": bool(
                        (lambda o: o["t"] is not None and abs(o["t"]) >= BONFERRONI_T)(
                            t_stat([ics[i] for i in sel if ics[i] is not None]))),
                }

    # ── H3: 축 간 IC 상관 6쌍 (비겹침 20일) ────────────────────────────────
    sel20 = _select_non_overlapping(entry_idx, 20)
    h3: Dict[str, Any] = {}
    for a in range(len(AXES)):
        for b in range(a + 1, len(AXES)):
            xa, xb = AXES[a], AXES[b]
            pair = [(ic_series[xa][i], ic_series[xb][i]) for i in sel20]
            pair = [(x, y) for x, y in pair if x is not None and y is not None]
            c = spearman([x for x, _ in pair], [y for _, y in pair]) if len(pair) >= 3 else None
            h3[f"{xa}~{xb}"] = {"corr": (round(c, 4) if c is not None else None),
                                "n": len(pair),
                                "pass": (c is not None and abs(c) < 0.7)}

    # ── H4: 가격 4축 vs 펀더멘털 2축 평균 IC 대조 ──────────────────────────
    price_mean = {a: results[f"{a}_20d_optimistic"]["ic_non_overlap"].get("mean")
                  for a in AXES}
    vals = [v for v in price_mean.values() if v is not None]
    h4: Dict[str, Any] = {"price_axes_mean_ic": price_mean,
                          "price_axes_avg": (round(sum(vals) / len(vals), 6) if vals else None),
                          "fundamental_ref": {"fscore8": 0.030941, "gpa": 0.009005},
                          "fundamental_avg": round((0.030941 + 0.009005) / 2, 6)}
    if h4["price_axes_avg"] is not None:
        h4["h4_holds"] = h4["price_axes_avg"] > h4["fundamental_avg"]

    pbo: Dict[str, Any] = {"status": "skipped"}
    try:
        import numpy as np
        from api.quant.alpha.pbo import cscv_pbo
        keys = sorted(spreads)
        rowsel = [i for i in range(len(rebalances))
                  if all(spreads[k][i] is not None for k in keys)]
        if len(rowsel) >= 16 and len(keys) >= 2:
            pbo = cscv_pbo(np.array([[spreads[k][i] for k in keys] for i in rowsel],
                                    dtype=float), n_partitions=16)
            pbo["trials"] = keys
            pbo["T"] = len(rowsel)
        else:
            pbo = {"status": "insufficient", "T": len(rowsel), "N": len(keys)}
    except Exception as e:  # noqa: BLE001
        pbo = {"status": "error", "detail": f"{type(e).__name__}: {str(e)[:120]}"}

    doc = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00",
                                      time.localtime(time.time() + 9 * 3600)),
        "prereg": "docs/PREREG_BACKTEST_KR_PRICE_AXES.md (PM 승인 안 가)",
        "axes_weight_base": {"technical": 0.17, "momentum": 0.10,
                             "volatility": 0.06, "mean_reversion": 0.06},
        "method": {
            "entry": "T+1 종가 (신호는 T 종가 산출 — T 종가 매수는 불가능)",
            "horizons": list(HORIZONS), "bonferroni_t": BONFERRONI_T,
            "judgment": "비겹침 표본만. 임계는 8검정 기준이며 낮추지 않는다",
            "universe": "kr_universe_pit 월말 · 우선주/스팩/리츠/ETF 제외",
            "delist_haircut": DELIST_HAIRCUT,
            "cost_roundtrip": 2 * COMMISSION + SELL_TAX,
        },
        "caveats": {
            "bid_ask_bounce": ("mean_reversion 은 종가가 매수호가에 체결된 종목과 상관된다. "
                               "T+1 진입으로 완화되나 제거되지 않음 — 단독 채택 금지"),
            "cross_section_mismatch": ("단면 모집단 = PIT 전체(약 1,400종목). "
                                       "운영은 후보 25종목 — 통과해도 1:1 전이 아님"),
            "not_strategy": "팩터 신호 검정이며 진입·청산·사이징을 포함한 전략 검증이 아님",
        },
        "coverage": coverage, "results": results,
        "h3_axis_independence": h3, "h4_vs_fundamental": h4, "pbo": pbo,
        "note": "🚨 관측 산출물. 점수·집행 입력 0.",
    }
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    os.replace(tmp, out_path)
    with open(trail_path, "w", encoding="utf-8") as f:
        for t in trail:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    return doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lake", required=True)
    ap.add_argument("--limit-rebalances", type=int, default=0, help="0 = 전체")
    a = ap.parse_args()
    r = run(a.lake, limit_rebalances=a.limit_rebalances)
    if r.get("status") in ("missing_input", "no_rebalances"):
        print(f"[kr_price_axes] {r.get('status')}", file=sys.stderr)
        return 1
    c = r["coverage"]
    print(f"[kr_price_axes] 리밸런스 {c['rebalances']} · 관측 {c['total_observations']:,} · "
          f"중앙 종목수 {c['median_names']} · 상폐청산 {c['delisted_exits']} · {c['elapsed_sec']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
