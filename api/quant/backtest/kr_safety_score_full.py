# -*- coding: utf-8 -*-
"""kr_safety_score_full — 안심점수 **전체 100점** 사전등록 검정.

사전등록 `docs/PREREG_BACKTEST_SAFETY_SCORE_FULL_2026_08_10.md` (PM 승인 2026-08-11 "둘 다 승인").
🚨 관측 산출물만. 점수·집행 입력 0. **실행 1회 소진.**

## 8/9(53점 부분)과 다른 것

1. **100점 전부 재현** — PER 20 · PBR 15 · 배당 12 를 `kr_valuation_panel`(PIT 시총·지배주주
   EPS·DPS)로 복원. 8/9 의 오염 2축 정정: 영업이익률 = `dart_kr_fin_history` **연간 실측**
   (매출총이익률 대입 폐기) · ROE = `roa_ttm`(기간 혼재 roa 폐기).
2. **결측 = 운영 기본값 그대로** (§4-1, 8/9 의 "제외" 와 반대). 운영 `calculate_safety_score`
   는 `stock.get("per", 0)` 이라 결측 = 0 = 0점이고, **`pbr == 0 → 3점`** 이라 PBR 결측이
   3점을 받는다. 검정 대상이 실제로 돌아가는 시스템이므로 그대로 재현한다.
   대가(재무 부재 종목이 저점수로 둔갑) = §6-1 진단 2(부재 더미 IC)로 처리.
3. **재검정 안 함**: drop·trading_value·debt 단독 축 — 8/9 에 오염 없이 측정 완료.
   단 safety_full 합산의 **입력**으로는 당연히 들어간다.

## 재현하지 않는 것 (§4-2 — 산출물에 명시)

- `_turnaround` −10점 (lynch_classifier 의존, PIT 불가)
- 미국 시장 분기 (KR-only)
- 영업이익률은 **연간만** (분기 PIT 소스 없음. 12월 결산 가정 +90일 지연)

판정 = 등록 §3: 12검정 (safety_full·per·pbr·div·op_margin·roe × 20/60d) ·
conservative 정본 · NW t(lag 0/2) → BH-FDR q=.05 · 참고 Bonferroni |t|≥2.87 · PBO 병기.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import sys
import time
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from api.quant.backtest.kr_fundamental import (  # noqa: E402 — 8/8 부품 재사용
    DELIST_PATH, HORIZONS, _calendar, _select_non_overlapping,
    exclusion_reason, load_names, load_universe, spearman, t_stat,
)
from api.quant.backtest.kr_price_axes import (  # noqa: E402
    COMMISSION, ENTRY_LAG, SCENARIOS, SELL_TAX, forward_return,
)
from api.quant.backtest.kr_safety_score import (  # noqa: E402 — 8/9 부품 재사용
    BONFERRONI_T, LAG_ANNUAL_DAYS, MIN_VALID, N_QUANTILE, PRIMARY_SCENARIO,
    bh_fdr, load_ohlcv_duckdb, load_panel, nw_lag, nw_t, pit_panel, pts_debt,
    pts_drop, pts_op_margin, pts_roe, pts_trading_value, two_sided_p,
)

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "data")
OUT_PATH = os.path.join(_DATA, "analysis", "prereg_safety_score_full_20260810.json")
VAL_PATH = os.path.join(_DATA, "metadata", "kr_valuation_panel.jsonl")
FIN_HIST_PATH = os.path.join(_DATA, "dart_kr_fin_history.json")

AXES: Tuple[str, ...] = ("safety_full", "per", "pbr", "div", "op_margin", "roe")


# ── 운영 배점 그대로 (stock_filter.calculate_safety_score 발췌 — 결측=0 의미 포함) ──
def pts_per(per: Optional[float]) -> int:
    p = per or 0
    if 5 <= p <= 15:
        return 20
    if 15 < p <= 25:
        return 12
    if 0 < p <= 50:
        return 5
    return 0


def pts_pbr(pbr: Optional[float]) -> int:
    """🚨 운영의 `elif pbr == 0: score += 3` — **결측이 3점을 받는다.** 그대로 재현."""
    b = pbr or 0
    if 0 < b <= 1.0:
        return 15
    if 1.0 < b <= 1.5:
        return 10
    if 1.5 < b <= 3.0:
        return 5
    if b == 0:
        return 3
    return 0


def pts_div(dy: Optional[float]) -> int:
    d = dy or 0
    if d >= 3:
        return 12
    if d >= 1:
        return 7
    return 0


def _plus(day: int, n: int) -> int:
    d = date(day // 10000, (day // 100) % 100, day % 100) + timedelta(days=n)
    return d.year * 10000 + d.month * 100 + d.day


def load_valuation() -> Dict[int, Dict[str, Dict[str, Any]]]:
    """kr_valuation_panel — {월말 req: {ticker: row}}. per/pbr/div_yield + PIT 처리 완료본."""
    out: Dict[int, Dict[str, Dict[str, Any]]] = {}
    with open(VAL_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            out.setdefault(int(r["d"] if "req" not in r else r["req"]), {})[str(r["t"])] = r
    return out


def load_op_margin() -> Dict[str, List[Tuple[int, float]]]:
    """연간 영업이익률 — dart_kr_fin_history (15,108행 · 1,715종목 · 2015~).

    🚨 8/9 오염 정정의 핵심: 매출총이익률이 아니라 **영업이익률**이다.
    PIT = 사업연도 말 +90일 (12월 결산 가정 — 산출물에 명시). 연간만 있다(§4-3)."""
    try:
        rows = json.load(open(FIN_HIST_PATH, encoding="utf-8")).get("rows") or []
    except (OSError, json.JSONDecodeError):
        return {}
    out: Dict[str, List[Tuple[int, float]]] = {}
    for r in rows:
        f = r.get("fundamentals") or {}
        rev, op = f.get("revenue"), f.get("operating_profit")
        if not rev or rev <= 0 or op is None:
            continue
        y = int(r.get("fiscal_year") or 0)
        if y < 2015:
            continue
        as_of = _plus(y * 10000 + 1231, LAG_ANNUAL_DAYS)
        out.setdefault(str(r.get("ticker")), []).append((as_of, op / rev * 100.0))
    for v in out.values():
        v.sort()
    return out


def _pit_pair(series: List[Tuple[int, float]], day: int) -> Optional[float]:
    i = bisect.bisect_right(series, (day, float("inf"))) - 1
    return series[i][1] if i >= 0 else None


def run(lake: str, out_path: str = OUT_PATH, limit_rebalances: int = 0) -> Dict[str, Any]:
    t0 = time.time()
    universe = load_universe()
    names = load_names()
    px = load_ohlcv_duckdb(lake) if lake.endswith(".duckdb") else None
    panel = load_panel()               # 분기 패널 (debt_ratio · roa_ttm — PIT lag 내장)
    val = load_valuation()             # 밸류에이션 (per·pbr·div — PIT 처리 완료)
    opm = load_op_margin()             # 연간 영업이익률
    try:
        dl = json.load(open(DELIST_PATH, encoding="utf-8")) or {}
        gone = {t for t, v in (dl.get("last_seen") or {}).items() if str(v) != str(dl.get("as_of"))}
    except (OSError, json.JSONDecodeError):
        gone = set()
    if not universe or not px or not val:
        return {"status": "missing_input",
                "have": {"universe": len(universe), "prices": len(px or {}),
                         "valuation_dates": len(val), "op_margin_tickers": len(opm)}}

    cal = _calendar({t: {"d": s["d"], "c": s["c"]} for t, s in px.items()})
    rebalances: List[Dict[str, Any]] = []
    excl: Dict[str, int] = {}
    fill = {k: 0 for k in ("per", "pbr", "div", "op_margin", "roe", "debt", "fin_absent")}
    n_rows_total = 0

    for as_of, tickers in universe:
        d_int = int(as_of)
        k = bisect.bisect_right(cal, d_int) - 1
        if k < 0 or k + ENTRY_LAG + max(HORIZONS) >= len(cal):
            continue
        signal_day = cal[k]
        entry_day = cal[k + ENTRY_LAG]
        exits = {h: cal[k + ENTRY_LAG + h] for h in HORIZONS}
        vrow_by_t = val.get(d_int) or {}

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
            if i < 0 or s["d"][i] != signal_day or i < 20:
                continue
            close = s["c"]
            pxc = close[i]
            if not pxc or pxc <= 0:
                continue

            # ── 가격 파생 2종 (8/9 과 동일 정의) ──
            lo = max(0, i - 251)
            hi = max(close[lo:i + 1])
            drop = ((pxc - hi) / hi * 100.0) if hi > 0 else None
            tv = None
            vol = s.get("v")
            if vol and len(vol) > i:
                vals = [close[j] * vol[j] for j in range(max(0, i - 19), i + 1)
                        if vol[j] is not None and close[j] is not None]
                if vals:
                    tv = sum(vals) / len(vals)

            # ── 재무 PIT (분기 패널 — 8/9 과 동일 pit) ──
            snaps = panel.get(t) or []
            p = pit_panel(snaps, signal_day) if snaps else None
            debt = p.get("debt_ratio") if p else None
            roa_ttm = p.get("roa_ttm") if p else None
            if p is None:
                fill["fin_absent"] += 1

            # ── 밸류에이션 (월말 조인) + 연간 영업이익률 ──
            v = vrow_by_t.get(t) or {}
            per_v, pbr_v, div_v = v.get("per"), v.get("pbr"), v.get("div_yield")
            om_v = _pit_pair(opm.get(t) or [], signal_day)

            for key, x in (("per", per_v), ("pbr", pbr_v), ("div", div_v),
                           ("op_margin", om_v), ("roe", roa_ttm), ("debt", debt)):
                if x is not None:
                    fill[key] += 1
            n_rows_total += 1

            # ── 배점 — 결측 = 운영 기본값 (None→0, pbr 결측→3점) ──
            c_per, c_pbr, c_div = pts_per(per_v), pts_pbr(pbr_v), pts_div(div_v)
            c_drop = pts_drop(drop) or 0
            c_tv = pts_trading_value(tv) or 0
            c_debt = pts_debt(debt) or 0
            c_om = pts_op_margin(om_v) or 0
            c_roe = pts_roe(roa_ttm) or 0

            rec: Dict[str, Any] = {
                "t": t,
                "per": c_per, "pbr": c_pbr, "div": c_div,
                "op_margin": c_om, "roe": c_roe,
                "safety_full": c_per + c_pbr + c_div + c_drop + c_tv + c_debt + c_om + c_roe,
                # §6-1 진단용 — 정정 53점(가격·재무축만) + 재무 부재 더미
                "_s53c": c_drop + c_tv + c_debt + c_om + c_roe,
                "_absent": 1 if p is None else 0,
            }
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
        if len(rows) < MIN_VALID:
            continue
        rebalances.append({"as_of": as_of, "entry_idx": k + ENTRY_LAG, "rows": rows})
        print(f"  [{len(rebalances)}] {as_of} · {len(rows)}종목 · {time.time() - t0:.0f}s",
              flush=True)
        if limit_rebalances and len(rebalances) >= limit_rebalances:
            break

    coverage = {
        "rebalances": len(rebalances),
        "window": ([rebalances[0]["as_of"], rebalances[-1]["as_of"]] if rebalances else None),
        "excluded": excl,
        "total_observations": sum(len(r["rows"]) for r in rebalances),
        "median_names": (sorted(len(r["rows"]) for r in rebalances)[len(rebalances) // 2]
                         if rebalances else 0),
        "fill_rate_pct": {k: round(vv / n_rows_total * 100, 1) if n_rows_total else 0.0
                          for k, vv in fill.items()},
        "elapsed_sec": round(time.time() - t0, 1),
    }
    if not rebalances:
        return {"status": "no_rebalances", "coverage": coverage}

    entry_idx = [r["entry_idx"] for r in rebalances]
    results: Dict[str, Any] = {}
    spreads: Dict[str, List[Optional[float]]] = {}

    def _series(axis: str, h: int, scen: str) -> Tuple[List[Optional[float]], List[Optional[float]]]:
        ics: List[Optional[float]] = []
        sprd: List[Optional[float]] = []
        for rb in rebalances:
            xs, ys = [], []
            for r in rb["rows"]:
                vx, ret = r.get(axis), r.get(f"r{h}_{scen}")
                if vx is None or ret is None:
                    continue
                xs.append(float(vx))
                ys.append(float(ret))
            ics.append(spearman(xs, ys) if len(xs) >= MIN_VALID else None)
            if len(xs) >= N_QUANTILE * 3:
                order = sorted(range(len(xs)), key=lambda idx: xs[idx])
                kq = max(1, len(order) // N_QUANTILE)
                lo_r = sum(ys[idx] for idx in order[:kq]) / kq
                hi_r = sum(ys[idx] for idx in order[-kq:]) / kq
                sprd.append((hi_r - lo_r) - 2 * (2 * COMMISSION + SELL_TAX))
            else:
                sprd.append(None)
        return ics, sprd

    for axis in AXES:
        for h in HORIZONS:
            for scen in SCENARIOS:
                key = f"{axis}_{h}d_{scen}"
                ics, sprd = _series(axis, h, scen)
                spreads[key] = sprd
                sel = _select_non_overlapping(entry_idx, h)
                nov = t_stat([ics[i] for i in sel if ics[i] is not None])
                nw = nw_t([x for x in ics if x is not None], nw_lag(h))
                results[key] = {
                    "ic_nw": nw,
                    "ic_naive": t_stat([x for x in ics if x is not None]),
                    "ic_non_overlap": nov,
                    "spread_non_overlap": t_stat([sprd[i] for i in sel if sprd[i] is not None]),
                    "passes_bonferroni_ic": bool(
                        nw.get("t") is not None and abs(nw["t"]) >= BONFERRONI_T),
                }

    # ── 판정: 정본 12검정에만 BH-FDR (등록 §3) ──
    ledger = [f"{a}_{h}d_{PRIMARY_SCENARIO}" for a in AXES for h in HORIZONS]
    pv = [two_sided_p(results[k]["ic_nw"].get("t"), results[k]["ic_nw"].get("n"))
          for k in ledger]
    for k, p_, okbh in zip(ledger, pv, bh_fdr(pv, q=0.05)):
        results[k]["p_two_sided"] = (round(p_, 6) if p_ is not None else None)
        results[k]["passes_bh_fdr"] = okbh
        results[k]["in_ledger"] = True
    for k in results:
        results[k].setdefault("in_ledger", False)

    # ── §6-1 진단 (BH 통과 + 방향 반대 시 의무 — 등록 방향은 전부 양(+)) ──
    inverse_pass = [k for k in ledger
                    if results[k].get("passes_bh_fdr")
                    and (results[k]["ic_nw"].get("mean") or 0) < 0]
    diagnostics: Dict[str, Any] = {"triggered_by": inverse_pass}
    if inverse_pass:
        # 진단 2 — 데이터 부재 교락: 완전관측 부분표본 IC + 부재 더미 자체의 IC
        for label, cond in (("full_obs_only", lambda r: r["_absent"] == 0),
                            ("absent_dummy", None)):
            ics = []
            for rb in rebalances:
                if label == "absent_dummy":
                    xs = [float(r["_absent"]) for r in rb["rows"]
                          if r.get(f"r20_{PRIMARY_SCENARIO}") is not None]
                    ys = [float(r[f"r20_{PRIMARY_SCENARIO}"]) for r in rb["rows"]
                          if r.get(f"r20_{PRIMARY_SCENARIO}") is not None]
                else:
                    sub = [r for r in rb["rows"] if cond(r)
                           and r.get(f"r20_{PRIMARY_SCENARIO}") is not None]
                    xs = [float(r["safety_full"]) for r in sub]
                    ys = [float(r[f"r20_{PRIMARY_SCENARIO}"]) for r in sub]
                ics.append(spearman(xs, ys) if len(xs) >= MIN_VALID else None)
            diagnostics[label] = nw_t([x for x in ics if x is not None], nw_lag(20))
        # 진단 3 — 가치 47점 기여 분해 (기술 통계만 — p 주장 금지, 등록 §6-1)
        ics_53 = []
        for rb in rebalances:
            xs = [float(r["_s53c"]) for r in rb["rows"]
                  if r.get(f"r20_{PRIMARY_SCENARIO}") is not None]
            ys = [float(r[f"r20_{PRIMARY_SCENARIO}"]) for r in rb["rows"]
                  if r.get(f"r20_{PRIMARY_SCENARIO}") is not None]
            ics_53.append(spearman(xs, ys) if len(xs) >= MIN_VALID else None)
        diagnostics["s53_corrected_descriptive"] = {
            "mean_ic": (round(sum(x for x in ics_53 if x is not None)
                              / max(1, sum(1 for x in ics_53 if x is not None)), 6)),
            "note": "기술 통계만 — 원장 밖이라 p 값을 주장하지 않는다(등록 §6-1-3)",
        }
        # 진단 1 — 분위 단조성 (safety_full, 정본 20d)
        acc = [[] for _ in range(N_QUANTILE)]
        for rb in rebalances:
            pair = [(float(r["safety_full"]), float(r[f"r20_{PRIMARY_SCENARIO}"]))
                    for r in rb["rows"] if r.get(f"r20_{PRIMARY_SCENARIO}") is not None]
            if len(pair) < MIN_VALID:
                continue
            pair.sort(key=lambda z: z[0])
            kq = len(pair) // N_QUANTILE
            for q in range(N_QUANTILE):
                seg = pair[q * kq:(q + 1) * kq] if q < N_QUANTILE - 1 else pair[q * kq:]
                if seg:
                    acc[q].append(sum(z[1] for z in seg) / len(seg))
        means = [round(sum(a) / len(a) * 100, 3) if a else None for a in acc]
        diagnostics["quantile_means_20d_pct"] = means
        diagnostics["monotone_decreasing"] = all(
            means[i] is not None and means[i + 1] is not None and means[i] >= means[i + 1]
            for i in range(N_QUANTILE - 1))

    pbo: Dict[str, Any] = {"status": "skipped"}
    try:
        import numpy as np

        from api.quant.alpha.pbo import cscv_pbo
        keys = sorted(k for k in spreads if k.endswith(PRIMARY_SCENARIO))
        rowsel = [i for i in range(len(rebalances))
                  if all(spreads[k][i] is not None for k in keys)]
        if len(rowsel) >= 16 and len(keys) >= 2:
            pbo = cscv_pbo(np.array([[spreads[k][i] for k in keys] for i in rowsel],
                                    dtype=float))
    except Exception as e:  # noqa: BLE001
        pbo = {"status": "error", "detail": f"{type(e).__name__}: {e}"}

    doc = {
        "_meta": {
            "prereg": "docs/PREREG_BACKTEST_SAFETY_SCORE_FULL_2026_08_10.md",
            "approved": "PM 2026-08-11 '둘 다 승인'",
            "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00",
                                         time.localtime(time.time() + 9 * 3600)),
            "market": "KR-only",
            "tests": len(AXES) * len(HORIZONS),
            "primary_scenario": PRIMARY_SCENARIO,
            "judgment": "NW t(lag 0/2) → BH-FDR q=.05 · 참고 Bonferroni |t|≥2.87 · 비겹침 병기",
            "min_detectable_ic": {"single": 0.031, "bonferroni12": 0.041},
            "missing_semantics": ("운영 기본값 그대로 — 결측 PER/배당=0점, 결측 PBR=3점 "
                                  "(calculate_safety_score 원 동작. 등록 §4-1)"),
            "not_reproduced": ["_turnaround −10점 (lynch 의존)",
                               "영업이익률 분기 (연간만 · 12월 결산 +90일 가정)",
                               "US 분기 trading_value 임계 (KR-only)"],
            "corrected_from_0809": ["op_margin: 매출총이익률 대입 폐기 → 연간 영업이익률 실측",
                                     "roe: 기간 혼재 roa 폐기 → roa_ttm"],
            "scope_warning": "관측 산출물. 점수·집행 입력 0. 이 실행으로 배점을 바꾸지 않는다(§6-2).",
        },
        "coverage": coverage,
        "results": results,
        "diagnostics": diagnostics,
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
    ap.add_argument("--lake", default=os.path.expanduser("~/VERITY_data_lake/kr_prices.duckdb"))
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    r = run(a.lake, limit_rebalances=a.limit)
    if r.get("status") in ("missing_input", "no_rebalances"):
        print(f"[safety_full] {r['status']} — {json.dumps(r, ensure_ascii=False)[:300]}",
              file=sys.stderr)
        return 1
    c = r["coverage"]
    print(f"\n[safety_full] 리밸런스 {c['rebalances']} · 관측 {c['total_observations']:,} "
          f"· 중앙 {c['median_names']} · {c['elapsed_sec']}s")
    print(f"[safety_full] 채움율 {c['fill_rate_pct']}")
    sc = PRIMARY_SCENARIO
    print(f"\n{'축':13}{'IC(20d)':>9}{'t':>7}{'p':>8}{'IC(60d)':>9}{'t':>7}{'p':>8}  BH")
    for axis in AXES:
        a20, a60 = r["results"][f"{axis}_20d_{sc}"], r["results"][f"{axis}_60d_{sc}"]
        n20, n60 = a20["ic_nw"], a60["ic_nw"]
        flag = "통과" if (a20.get("passes_bh_fdr") or a60.get("passes_bh_fdr")) else "—"
        print(f"{axis:13}{(n20.get('mean') or 0):>9.4f}{(n20.get('t') or 0):>7.2f}"
              f"{(a20.get('p_two_sided') if a20.get('p_two_sided') is not None else float('nan')):>8.3f}"
              f"{(n60.get('mean') or 0):>9.4f}{(n60.get('t') or 0):>7.2f}"
              f"{(a60.get('p_two_sided') if a60.get('p_two_sided') is not None else float('nan')):>8.3f}  {flag}")
    if r["diagnostics"].get("triggered_by"):
        d = r["diagnostics"]
        print(f"\n[진단] 역방향 BH 통과: {d['triggered_by']}")
        print(f"  완전관측 부분표본 IC: {d.get('full_obs_only')}")
        print(f"  재무 부재 더미 IC:   {d.get('absent_dummy')}")
        print(f"  분위 Q1→Q5(20d,%):  {d.get('quantile_means_20d_pct')} 단조↓={d.get('monotone_decreasing')}")
    print(f"\nPBO: {r['pbo'].get('pbo', r['pbo'].get('status'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
