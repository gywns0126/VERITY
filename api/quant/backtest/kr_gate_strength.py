# -*- coding: utf-8 -*-
"""kr_gate_strength — 게이트 강도 재설계 검정 (풀 품질 · 격납비).

사전등록 `docs/PREREG_GATE_STRENGTH_REDESIGN_2026_08_12.md` · PM 승인 2026-08-12 "ㄱㄱ".
🚨 관측 산출물만. **실행 1회 소진.**

세 풀 (공통 단면 = C1 산출 가능 + 수익률 존재):
  A = 현행  safety_full ≥ 55            (~19% 잔존 — 실측 상위 선별기)
  B = 강도만 incumbent 백분위 > 하위 20%
  C = 강도+점수  C1 백분위 > 하위 20%

핵심 지표 = 격납비 (풀 크기 보정 — 크기 다른 풀의 유일한 공정 비교):
  승자격납비 = P(미래 상위 10% 승자 ∈ 풀) ÷ 잔존율     >1 = 무작위보다 승자 접근 좋음
  패자격납비 = P(미래 하위 10% 패자 ∈ 풀) ÷ 잔존율     <1 = 안전 기능 작동

원장 4검정 = 승자격납비 (B−A, C−A) × 승자정의(20d/60d 상위 10%) · NW t → BH q=.05.
채택(§3): B = 검정1·2 BH+t≥3 + 풀평균 비열등(t>−2) + 패자격납비<1 + 반쪽부호 + 완전관측부호.
C = 동일 5조건 + B 를 승자·패자 격납비 점추정 완승 시만. B 미충족 = 전원 무채택.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import statistics as st
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from api.quant.backtest.kr_fundamental import (  # noqa: E402
    DELIST_PATH, HORIZONS, _calendar, exclusion_reason, load_names,
    load_universe,
)
from api.quant.backtest.kr_price_axes import ENTRY_LAG, forward_return  # noqa: E402
from api.quant.backtest.kr_safety_score import (  # noqa: E402
    MIN_VALID, bh_fdr, load_ohlcv_duckdb, load_panel, nw_lag, nw_t,
    pit_panel, pts_debt, pts_drop, pts_op_margin, pts_roe, pts_trading_value,
    two_sided_p,
)
from api.quant.backtest.kr_safety_score_full import (  # noqa: E402
    _pit_pair, load_op_margin, load_valuation, pts_div, pts_pbr, pts_per,
)
from api.quant.backtest.kr_formula_rebuild import pct_rank  # noqa: E402

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "data")
OUT_PATH = os.path.join(_DATA, "analysis", "prereg_gate_strength_20260812.json")

MIN_SAFETY = 55
BOTTOM_CUT = 0.20            # §5 — 단일 등록. 스캔 금지 (측정된 신호 경계 Q1 상속)
ADOPT_T = 3.0
NONINF_T = -2.0
BONF4 = 2.50
SPLIT_BOUNDARY = 20230301
DECILE = 0.10


def _c1_axes(v: Dict[str, Any], p: Optional[Dict[str, Any]],
             omv: Optional[float]) -> Dict[str, Optional[float]]:
    per_v, pbr_v = v.get("per"), v.get("pbr")
    dy = v.get("div_yield")
    if dy is None and v.get("div_src_year") is not None:
        dy = 0.0
    return {
        "ep": (1.0 / per_v if isinstance(per_v, (int, float)) and per_v > 0 else None),
        "bp": (1.0 / pbr_v if isinstance(pbr_v, (int, float)) and pbr_v > 0 else None),
        "dy": dy, "opm": omv,
        "roa": (p.get("roa_ttm") if p else None),
    }


def run(lake: str, out_path: str = OUT_PATH, limit_rebalances: int = 0) -> Dict[str, Any]:
    t0 = time.time()
    universe = load_universe()
    names = load_names()
    px = load_ohlcv_duckdb(lake)
    panel = load_panel()
    val = load_valuation()
    opm_hist = load_op_margin()
    dl = json.load(open(DELIST_PATH, encoding="utf-8")) or {}
    gone = {t for t, v in (dl.get("last_seen") or {}).items()
            if str(v) != str(dl.get("as_of"))}
    cal = _calendar({t: {"d": s["d"], "c": s["c"]} for t, s in px.items()})

    # 리밸런스별: {h: {"wr": {A,B,C}, "lr": {...}, "pm": {...}, "keep": {...}, "full_wr": {...}}}
    series: List[Dict[str, Any]] = []
    for as_of, tickers in universe:
        d = int(as_of)
        k = bisect.bisect_right(cal, d) - 1
        if k < 0 or k + ENTRY_LAG + max(HORIZONS) >= len(cal):
            continue
        sd, ed = cal[k], cal[k + ENTRY_LAG]
        ex = {h: cal[k + ENTRY_LAG + h] for h in HORIZONS}
        vrow = val.get(d) or {}
        rows = []
        for t in tickers:
            if exclusion_reason(t, names.get(t)):
                continue
            s = px.get(t)
            if not s:
                continue
            i = bisect.bisect_right(s["d"], sd) - 1
            if i < 20 or s["d"][i] != sd:
                continue
            close = s["c"]
            pxc = close[i]
            if not pxc or pxc <= 0:
                continue
            lo = max(0, i - 251)
            hi = max(close[lo:i + 1])
            drop = ((pxc - hi) / hi * 100) if hi > 0 else None
            vv = s.get("v")
            tv = None
            if vv and len(vv) > i:
                a = [close[j] * vv[j] for j in range(max(0, i - 19), i + 1)
                     if vv[j] is not None]
                if a:
                    tv = sum(a) / len(a)
            v = vrow.get(t) or {}
            p = pit_panel(panel.get(t) or [], sd)
            omv = _pit_pair(opm_hist.get(t) or [], sd)
            inc = (pts_per(v.get("per")) + pts_pbr(v.get("pbr")) + pts_div(v.get("div_yield"))
                   + (pts_drop(drop) or 0) + (pts_trading_value(tv) or 0)
                   + (pts_debt(p.get("debt_ratio") if p else None) or 0)
                   + (pts_op_margin(omv) or 0)
                   + (pts_roe(p.get("roa_ttm") if p else None) or 0))
            ax = _c1_axes(v, p, omv)
            r = {"inc": float(inc), "ax": ax,
                 "_full": all(x is not None for x in ax.values())}
            ok = False
            for h in HORIZONS:
                fr = forward_return(s, ed, ex[h], delisted=(t in gone), haircut=True)
                if fr is not None:
                    r[f"r{h}"] = fr[0]
                    ok = True
            if ok:
                rows.append(r)
        if len(rows) < MIN_VALID:
            continue

        # C1 백분위
        for axk in ("ep", "bp", "dy", "opm", "roa"):
            pr = pct_rank([(j, float(rows[j]["ax"][axk])) for j in range(len(rows))
                           if rows[j]["ax"][axk] is not None], True)
            for j, rk in pr.items():
                rows[j].setdefault("rks", []).append(rk)
        for r in rows:
            rks = r.get("rks") or []
            r["c1"] = sum(rks) / len(rks) if len(rks) >= 3 else None
        common0 = [r for r in rows if r["c1"] is not None]
        if len(common0) < MIN_VALID:
            continue
        inc_pr = pct_rank([(j, common0[j]["inc"]) for j in range(len(common0))], True)
        for j, rk in inc_pr.items():
            common0[j]["inc_pr"] = rk
        # 🚨 smoke 가 잡은 결함 정정: c1 합성값(순위평균)은 꼬리가 압축돼 값 0.20 컷이면
        #   잔존율 0.92 가 된다. 등록문은 "백분위 > 하위 20%" — 합성점수를 **다시 백분위화**
        #   해서 자른다 (B 의 inc_pr 과 대칭).
        c1_pr = pct_rank([(j, common0[j]["c1"]) for j in range(len(common0))], True)
        for j, rk in c1_pr.items():
            common0[j]["c1_pr"] = rk

        rec: Dict[str, Any] = {"as_of": as_of}
        for h in HORIZONS:
            rk_ = f"r{h}"
            common = [r for r in common0 if r.get(rk_) is not None]
            if len(common) < MIN_VALID:
                continue
            pools = {
                "A": [r for r in common if r["inc"] >= MIN_SAFETY],
                "B": [r for r in common if r["inc_pr"] > BOTTOM_CUT],
                "C": [r for r in common if r["c1_pr"] > BOTTOM_CUT],
            }
            if any(len(p_) < 20 or len(p_) >= len(common) for p_ in pools.values()):
                continue
            n = len(common)
            ordered = sorted(common, key=lambda r: r[rk_])
            n_dec = max(1, int(n * DECILE))
            losers = set(map(id, ordered[:n_dec]))
            winners = set(map(id, ordered[-n_dec:]))
            hrec: Dict[str, Any] = {}
            for name, p_ in pools.items():
                keep = len(p_) / n
                pid = set(map(id, p_))
                wr = (sum(1 for w in winners if w in pid) / len(winners)) / keep
                lr = (sum(1 for l_ in losers if l_ in pid) / len(losers)) / keep
                hrec[name] = {"keep": keep, "wr": wr, "lr": lr,
                              "pm": st.mean(r[rk_] for r in p_)}
            # 완전관측 부분표본 승자격납비 (§3-5)
            fcommon = [r for r in common if r["_full"]]
            if len(fcommon) >= MIN_VALID:
                fn = len(fcommon)
                ford = sorted(fcommon, key=lambda r: r[rk_])
                fwin = set(map(id, ford[-max(1, int(fn * DECILE)):]))
                for name, p_ in pools.items():
                    fp = [r for r in p_ if r["_full"]]
                    if fp and fwin:
                        keep = len(fp) / fn
                        pid = set(map(id, fp))
                        hrec[name]["full_wr"] = (
                            (sum(1 for w in fwin if w in pid) / len(fwin)) / keep
                            if keep > 0 else None)
            rec[str(h)] = hrec
        if len(rec) > 1:
            series.append(rec)
        if limit_rebalances and len(series) >= limit_rebalances:
            break
        if len(series) % 20 == 0:
            print(f"  [{len(series)}] {as_of} · {time.time() - t0:.0f}s", flush=True)

    if not series:
        return {"status": "no_rebalances"}

    def _diff(metric: str, x: str, y: str, h: int) -> List[float]:
        out = []
        for rec in series:
            hr = rec.get(str(h))
            if hr and metric in hr.get(x, {}) and metric in hr.get(y, {}):
                a, b = hr[x].get(metric), hr[y].get(metric)
                if a is not None and b is not None:
                    out.append(a - b)
        return out

    results: Dict[str, Any] = {}
    ledger_keys = []
    for cmpname, pool in (("B_minus_A", "B"), ("C_minus_A", "C")):
        for h in HORIZONS:
            key = f"wr_{cmpname}_{h}d"
            ledger_keys.append(key)
            dsr = _diff("wr", pool, "A", h)
            results[key] = {"nw": nw_t(dsr, nw_lag(h)), "n": len(dsr)}
            # 반쪽
            half = {"H1": [], "H2": []}
            for rec in series:
                hr = rec.get(str(h))
                if hr and "wr" in hr.get(pool, {}) and "wr" in hr.get("A", {}):
                    half["H1" if int(rec["as_of"]) < SPLIT_BOUNDARY else "H2"].append(
                        hr[pool]["wr"] - hr["A"]["wr"])
            results[key]["split"] = {k: {"n": len(v),
                                         "mean": (round(st.mean(v), 4) if v else None),
                                         "sign_pos": (st.mean(v) > 0 if v else None)}
                                     for k, v in half.items()}
            fd = _diff("full_wr", pool, "A", h)
            results[key]["full_obs"] = {"n": len(fd),
                                        "mean": (round(st.mean(fd), 4) if fd else None),
                                        "sign_pos": (st.mean(fd) > 0 if fd else None)}
    pv = [two_sided_p(results[k]["nw"].get("t"), results[k]["nw"].get("n"))
          for k in ledger_keys]
    for k, p_, okbh in zip(ledger_keys, pv, bh_fdr(pv, q=0.05)):
        results[k]["p_two_sided"] = round(p_, 6) if p_ is not None else None
        results[k]["passes_bh_fdr"] = okbh

    guards: Dict[str, Any] = {}
    for pool in ("B", "C"):
        for h in HORIZONS:
            guards[f"pm_{pool}_minus_A_{h}d"] = nw_t(_diff("pm", pool, "A", h), nw_lag(h))
    levels: Dict[str, Any] = {}
    for pool in ("A", "B", "C"):
        for h in HORIZONS:
            for m in ("wr", "lr", "keep", "pm"):
                vals = [rec[str(h)][pool][m] for rec in series
                        if str(h) in rec and m in rec[str(h)].get(pool, {})]
                levels[f"{pool}_{m}_{h}d"] = round(st.mean(vals), 4) if vals else None

    def _passes(pool: str) -> Dict[str, Any]:
        cmpname = f"{pool}_minus_A"
        c = {
            "bh_both": all(results[f"wr_{cmpname}_{h}d"]["passes_bh_fdr"] for h in HORIZONS),
            "t3_both": all((results[f"wr_{cmpname}_{h}d"]["nw"].get("t") or 0) >= ADOPT_T
                           for h in HORIZONS),
            "pool_mean_noninf": all(
                (guards[f"pm_{pool}_minus_A_{h}d"].get("t") or -9e9) > NONINF_T
                for h in HORIZONS),
            "loser_ratio_lt1": all((levels[f"{pool}_lr_{h}d"] or 9e9) < 1.0 for h in HORIZONS),
            "split_sign": all(results[f"wr_{cmpname}_{h}d"]["split"][hh]["sign_pos"] is True
                              for h in HORIZONS for hh in ("H1", "H2")),
            "full_obs_sign": all(results[f"wr_{cmpname}_{h}d"]["full_obs"]["sign_pos"] is True
                                 for h in HORIZONS),
        }
        c["all_pass"] = all(c.values())
        return c

    adoption = {"B": _passes("B"), "C": _passes("C")}
    c_beats_b = all(
        (levels[f"C_wr_{h}d"] or 0) > (levels[f"B_wr_{h}d"] or 0)
        and (levels[f"C_lr_{h}d"] or 9e9) < (levels[f"B_lr_{h}d"] or 0)
        for h in HORIZONS)
    adoption["c_beats_b_point"] = c_beats_b
    adopted = None
    if adoption["B"]["all_pass"]:
        adopted = "C" if (adoption["C"]["all_pass"] and c_beats_b) else "B"
    adoption["adopted"] = adopted
    adoption["rule"] = ("B 채택 조건 충족 필수. C 는 동일 조건 + 격납비 점추정 완승 시만. "
                        "B 미충족 = 전원 무채택 (§3)")

    doc = {
        "_meta": {
            "prereg": "docs/PREREG_GATE_STRENGTH_REDESIGN_2026_08_12.md",
            "approved": "PM 2026-08-12 'ㄱㄱ'",
            "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00",
                                         time.localtime(time.time() + 9 * 3600)),
            "tests": len(ledger_keys),
            "bottom_cut": BOTTOM_CUT,
            "judgment": f"격납비 짝지은 차 NW→BH · 채택 t≥{ADOPT_T} · 비열등 t>{NONINF_T} "
                        f"· 참고 Bonf {BONF4}",
        },
        "coverage": {"rebalances": len(series),
                     "window": [series[0]["as_of"], series[-1]["as_of"]],
                     "elapsed_sec": round(time.time() - t0, 1)},
        "levels": levels,
        "results": results,
        "guards": {k: v for k, v in guards.items()},
        "adoption": adoption,
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
    if r.get("status") == "no_rebalances":
        print("[gate_strength] no_rebalances", file=sys.stderr)
        return 1
    L = r["levels"]
    print(f"\n[gate_strength] 리밸런스 {r['coverage']['rebalances']} "
          f"· {r['coverage']['elapsed_sec']}s · 하위컷 {r['_meta']['bottom_cut']:.0%}")
    print(f"\n{'풀':4}{'잔존율':>8}{'승자격납비 20d/60d':>20}{'패자격납비 20d/60d':>20}{'풀평균20d(%)':>12}")
    for p_ in ("A", "B", "C"):
        print(f"{p_:4}{L[f'{p_}_keep_20d']:>8.3f}"
              f"{L[f'{p_}_wr_20d']:>10.3f}/{L[f'{p_}_wr_60d']:.3f}"
              f"{L[f'{p_}_lr_20d']:>10.3f}/{L[f'{p_}_lr_60d']:.3f}"
              f"{L[f'{p_}_pm_20d']*100:>11.3f}")
    print()
    for k in ("wr_B_minus_A_20d", "wr_B_minus_A_60d", "wr_C_minus_A_20d", "wr_C_minus_A_60d"):
        v = r["results"][k]
        print(f"  {k:22} Δ {v['nw'].get('mean'):+.4f} · t {v['nw'].get('t'):+.2f} "
              f"· p {v.get('p_two_sided')} · BH {'통과' if v.get('passes_bh_fdr') else '—'}")
    print(f"\n채택: {r['adoption']['adopted'] or '무채택 (현행 유지)'}")
    for p_ in ("B", "C"):
        fails = [k for k, v in r["adoption"][p_].items() if v is False and k != "all_pass"]
        if fails:
            print(f"  {p_} 실패 조건: {fails}")
    print(f"  C 가 B 완승(점추정): {r['adoption']['c_beats_b_point']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
