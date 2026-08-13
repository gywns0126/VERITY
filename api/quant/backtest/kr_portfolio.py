# -*- coding: utf-8 -*-
"""kr_portfolio — 포트폴리오 백테스트 (win condition 직접 측정).

사전등록 `docs/PREREG_PORTFOLIO_BACKTEST_2026_08_13.md` · PM 승인 2026-08-13 "승인. ㄱㄱ".
🚨 관측 산출물만. **실행 1회 소진.** 참조 구성 등록일 뿐 운영 무변경(§3).

우리는 목표 지표를 한 번도 잰 적이 없다 — 등록 win condition 은 **Calmar 1.0+ / MDD <20%**
인데 8/8~8/12 검정 6회가 전부 단면 IC 였다. 이 러너가 그것을 직접 잰다.

격자 6칸 = 보유 N ∈ {5,10,20} × 리밸런스 H ∈ {20d,60d} · 동일가중 고정 · C3 점수 그대로.
🚨 **일별 마크투마켓.** 리밸런스 빈도로 MDD 를 재면 구간 내 저점을 못 봐 과소평가된다 —
win condition 이 MDD 기준이므로 그 과소평가가 판정을 뒤집는다.

미재현(§1-2): 손절·트레일링·기간손절 · Kelly/섹터/베타 가드 · 배당 · 시장충격.
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
    DELIST_PATH, _calendar, exclusion_reason, load_names, load_universe,
)
from api.quant.backtest.kr_price_axes import COMMISSION, ENTRY_LAG, SELL_TAX  # noqa: E402
from api.quant.backtest.kr_safety_score import (  # noqa: E402
    MIN_VALID, bh_fdr, load_ohlcv_duckdb, load_panel, nw_lag, nw_t, pit_panel,
    two_sided_p,
)
from api.quant.backtest.kr_safety_score_full import (  # noqa: E402
    _pit_pair, load_op_margin, load_valuation,
)
from api.quant.backtest.kr_formula_rebuild import pct_rank  # noqa: E402

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "data")
OUT_PATH = os.path.join(_DATA, "analysis", "prereg_portfolio_20260813.json")
KOSPI_PATH = os.path.join(_DATA, "metadata", "kospi_daily.jsonl")

# ── 등록값 (§1·§3) ──────────────────────────────────────────────────────────
GRID_N = (5, 10, 20)
GRID_H = (20, 60)
ROUNDTRIP = 2 * COMMISSION + SELL_TAX      # 0.230%
ADOPT_T = 3.0
CALMAR_MIN = 1.0
MDD_MIN = -0.20
SPLIT_BOUNDARY = 20230301
CURRENT_N, CURRENT_H = 7, 14               # §4-2 현행 규칙 참조점 (격자 밖)
RANDOM_TRIALS = 20                          # §4-4 무작위 벤치
M_TRIALS = 66                               # DSR 누적 시도 (§1-2)
C3_AXES = ("ep", "bp", "dy", "opm", "roa", "vol", "fs8", "illiq", "nearhigh")


def _load_kospi() -> Dict[int, float]:
    out: Dict[int, float] = {}
    try:
        with open(KOSPI_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    r = json.loads(line)
                    out[int(r["d"])] = float(r["close"])
    except OSError:
        pass
    return out


def build_scores(lake: str) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, List[float]]],
                                     List[int]]:
    """리밸런스별 C3 점수 단면 + 가격 레이크 + 시장 달력.

    점수 산출은 #355 재구축과 **같은 정의**를 쓴다 (재선택·재탐색 0).
    """
    universe, names = load_universe(), load_names()
    px = load_ohlcv_duckdb(lake)
    panel, val, opm_hist = load_panel(), load_valuation(), load_op_margin()
    from api.quant.factors.volatility import (_compute_vols_from_history,
                                              compute_volatility_score)
    from api.quant.backtest.kr_fundamental import axis_fscore8
    cal = _calendar({t: {"d": s["d"], "c": s["c"]} for t, s in px.items()})

    snaps: List[Dict[str, Any]] = []
    for as_of, tickers in universe:
        d = int(as_of)
        k = bisect.bisect_right(cal, d) - 1
        if k < 0 or k + ENTRY_LAG >= len(cal):
            continue
        sd = cal[k]
        vrow = val.get(d) or {}
        raw, vols20 = [], []
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
            hist = close[max(0, i - 251):i + 1]
            hi52 = max(hist)
            drop = ((pxc - hi52) / hi52 * 100) if hi52 > 0 else None
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
            per_v, pbr_v = v.get("per"), v.get("pbr")
            dy = v.get("div_yield")
            if dy is None and v.get("div_src_year") is not None:
                dy = 0.0
            v20, v60 = (None, None)
            if len(hist) >= 20:
                try:
                    v20, v60 = _compute_vols_from_history(hist)
                except Exception:  # noqa: BLE001
                    v20 = v60 = None
            if isinstance(v20, (int, float)) and v20 > 0:
                vols20.append(float(v20))
            raw.append({
                "t": t, "i": i,
                "ep": (1.0 / per_v if isinstance(per_v, (int, float)) and per_v > 0 else None),
                "bp": (1.0 / pbr_v if isinstance(pbr_v, (int, float)) and pbr_v > 0 else None),
                "dy": dy, "opm": omv,
                "roa": (p.get("roa_ttm") if p else None),
                "fs8": (lambda x: float(x) if x is not None else None)(
                    axis_fscore8(p, panel.get(t) or []) if p else None),
                "_v20": v20, "_v60": v60, "_hist": hist,
                "illiq_raw": tv, "nearhigh_raw": drop,
            })
        if len(raw) < MIN_VALID:
            continue
        med = sorted(vols20)[len(vols20) // 2] if vols20 else None
        ustats = {"median_vol_20d": med} if med else {}
        for r in raw:
            try:
                res = compute_volatility_score(
                    {"ticker": r["t"], "price_history": r["_hist"],
                     "volatility_20d": r["_v20"], "volatility_60d": r["_v60"]},
                    universe_stats=ustats) or {}
                sv = res.get("volatility_score")
                r["vol"] = float(sv) if isinstance(sv, (int, float)) else None
            except Exception:  # noqa: BLE001
                r["vol"] = None
            del r["_hist"], r["_v20"], r["_v60"]
        ranks: Dict[str, Dict[int, float]] = {}
        for ax, hb in (("ep", True), ("bp", True), ("dy", True), ("opm", True),
                       ("roa", True), ("vol", True), ("fs8", True),
                       ("illiq_raw", False), ("nearhigh_raw", True)):
            key = {"illiq_raw": "illiq", "nearhigh_raw": "nearhigh"}.get(ax, ax)
            ranks[key] = pct_rank(
                [(j, float(r[ax])) for j, r in enumerate(raw) if r.get(ax) is not None], hb)
        scored = []
        for j, r in enumerate(raw):
            have = [ranks[a][j] for a in C3_AXES if j in ranks.get(a, {})]
            if len(have) >= 5:
                scored.append({"t": r["t"], "score": sum(have) / len(have)})
        if len(scored) >= MIN_VALID:
            snaps.append({"as_of": d, "cal_idx": k, "rows": scored})
        if len(snaps) % 20 == 0:
            print(f"  점수 {len(snaps)} 단면 · {as_of}", flush=True)
    return snaps, px, cal


def _daily_curve(snaps: List[Dict[str, Any]], px: Dict[str, Dict[str, List[float]]],
                 cal: List[int], n_hold: int, h: int, gone: set,
                 picker=None) -> Tuple[List[int], List[float], Dict[str, Any]]:
    """일별 자산곡선. picker(rows, n) → 보유 티커 (기본 = C3 상위 n).

    회계: 리밸런스 시 교체분만 비용 과금 · 진입 T+1 종가 · 상폐 haircut 0.70 ·
    유효 <n 이면 가용분만 + 잔여 현금(무이자).
    """
    if picker is None:
        def picker(rows, n):
            return [r["t"] for r in sorted(rows, key=lambda z: -z["score"])[:n]]

    reb = [s for idx, s in enumerate(snaps) if idx % max(1, round(h / 20)) == 0] \
        if h != 20 else snaps
    days: List[int] = []
    rets: List[float] = []
    turn_total = 0.0
    cost_total = 0.0
    prev_held: List[str] = []
    n_reb = 0

    for si, snap in enumerate(reb):
        k = snap["cal_idx"]
        entry_i = k + ENTRY_LAG
        end_i = (reb[si + 1]["cal_idx"] + ENTRY_LAG) if si + 1 < len(reb) else min(
            entry_i + h, len(cal) - 1)
        if entry_i >= len(cal) or end_i <= entry_i:
            continue
        held = picker(snap["rows"], n_hold)
        if not held:
            continue
        n_reb += 1
        # 회전 비용 — 교체분만 (유지 종목 비과금)
        turn = len(set(held) - set(prev_held)) / max(1, len(held))
        cost = turn * ROUNDTRIP
        turn_total += turn
        cost_total += cost
        prev_held = held
        # 일별 동일가중 수익률
        first = True
        for di in range(entry_i, end_i):
            d0, d1 = cal[di], cal[di + 1]
            rs = []
            for t in held:
                s = px.get(t)
                if not s:
                    continue
                a = bisect.bisect_right(s["d"], d0) - 1
                b = bisect.bisect_right(s["d"], d1) - 1
                if a < 0 or b < 0 or s["d"][a] != d0:
                    continue
                if s["d"][b] != d1:
                    # 상폐/거래정지 — 마지막 관측 후 haircut 1회 적용하고 이후 제외
                    if t in gone and s["d"][-1] == d0:
                        rs.append(-0.30)
                    continue
                p0, p1 = s["c"][a], s["c"][b]
                if p0 and p0 > 0 and p1 and p1 > 0:
                    rs.append(p1 / p0 - 1.0)
            r = (sum(rs) / len(rs)) if rs else 0.0
            if first:
                r -= cost                        # 진입일에 회전비용 반영
                first = False
            days.append(d1)
            rets.append(r)
    meta = {"rebalances": n_reb,
            "turnover_per_reb": round(turn_total / max(1, n_reb), 4),
            "cost_total_pct": round(cost_total * 100, 3)}
    return days, rets, meta


def _metrics(rets: List[float], days: List[int]) -> Dict[str, Any]:
    import numpy as np

    from api.quant.risk_metrics import (annualized_sharpe, calmar_ratio,
                                        max_drawdown, sortino_ratio)
    a = np.asarray(rets, dtype=float)
    if len(a) < 30:
        return {"n_days": len(a)}
    eq = float(np.prod(1 + a))
    yrs = len(a) / 252.0
    return {
        "n_days": len(a),
        "total_return_pct": round((eq - 1) * 100, 2),
        "cagr_pct": round((eq ** (1 / yrs) - 1) * 100, 2) if yrs > 0 else None,
        "mdd": round(max_drawdown(a), 4),
        "calmar": round(calmar_ratio(a, 252), 3),
        "sharpe": round(annualized_sharpe(a), 3),
        "sortino": round(sortino_ratio(a), 3),
        "ann_vol_pct": round(float(np.std(a, ddof=1)) * math.sqrt(252) * 100, 2),
    }


def run(lake: str, out_path: str = OUT_PATH, limit: int = 0) -> Dict[str, Any]:
    t0 = time.time()
    snaps, px, cal = build_scores(lake)
    if limit:
        snaps = snaps[:limit]
    if not snaps:
        return {"status": "no_snapshots"}
    dl = json.load(open(DELIST_PATH, encoding="utf-8")) or {}
    gone = {t for t, v in (dl.get("last_seen") or {}).items()
            if str(v) != str(dl.get("as_of"))}
    kospi = _load_kospi()

    def bench_series(days: List[int]) -> List[float]:
        out = []
        ks = sorted(kospi)
        for i, d in enumerate(days):
            j = bisect.bisect_right(ks, d) - 1
            j0 = bisect.bisect_right(ks, days[i - 1]) - 1 if i else j - 1
            if j <= 0 or j0 < 0 or j == j0:
                out.append(0.0)
            else:
                out.append(kospi[ks[j]] / kospi[ks[j0]] - 1.0)
        return out

    results: Dict[str, Any] = {}
    ledger = []
    for n in GRID_N:
        for h in GRID_H:
            key = f"N{n}_H{h}"
            ledger.append(key)
            days, rets, meta = _daily_curve(snaps, px, cal, n, h, gone)
            b = bench_series(days)
            ex = [r - bb for r, bb in zip(rets, b)]
            # 월간 집계로 NW t (일별 초과수익은 자기상관·과대 t 위험)
            monthly: Dict[int, float] = {}
            for d, e in zip(days, ex):
                monthly.setdefault(d // 100, 0.0)
                monthly[d // 100] = (1 + monthly[d // 100]) * (1 + e) - 1
            mser = [monthly[k] for k in sorted(monthly)]
            half = {"H1": [], "H2": []}
            for k in sorted(monthly):
                half["H1" if k * 100 < SPLIT_BOUNDARY else "H2"].append(monthly[k])
            results[key] = {
                "metrics": _metrics(rets, days),
                "bench_metrics": _metrics(b, days),
                "excess_nw": nw_t(mser, 1 if h <= 20 else 3),
                "excess_total_pct": round((math.prod(1 + e for e in ex) - 1) * 100, 2),
                "split": {kk: {"n": len(v), "mean": (round(st.mean(v), 5) if v else None),
                               "sign_pos": (st.mean(v) > 0 if v else None)}
                          for kk, v in half.items()},
                **meta,
            }

    pv = [two_sided_p(results[k]["excess_nw"].get("t"), results[k]["excess_nw"].get("n"))
          for k in ledger]
    for k, p_, ok in zip(ledger, pv, bh_fdr(pv, q=0.05)):
        results[k]["p_two_sided"] = round(p_, 6) if p_ is not None else None
        results[k]["passes_bh_fdr"] = ok

    # ── §4 진단 ──
    diag: Dict[str, Any] = {}
    # 1. 비용 민감도 (N10_H60 대표 — 원장 밖 기술 통계)
    for mult, lab in ((0.0, "cost_0"), (1.0, "cost_base"), (2.0, "cost_2x")):
        global ROUNDTRIP
        keep = ROUNDTRIP
        ROUNDTRIP = keep * mult
        d_, r_, _ = _daily_curve(snaps, px, cal, 10, 60, gone)
        diag[lab] = _metrics(r_, d_)
        ROUNDTRIP = keep
    # 2. 현행 규칙 참조점 (격자 밖)
    d_, r_, m_ = _daily_curve(snaps, px, cal, CURRENT_N, CURRENT_H, gone)
    diag["current_rule_N7_H14"] = {**_metrics(r_, d_), **m_}
    # 3. KOSPI 매수보유
    if kospi:
        ks = sorted(kospi)
        kd = [d for d in ks if snaps[0]["as_of"] <= d <= snaps[-1]["as_of"]]
        kr_ = [kospi[kd[i]] / kospi[kd[i - 1]] - 1 for i in range(1, len(kd))]
        diag["kospi_buy_hold"] = _metrics(kr_, kd[1:])
    # 4. 무작위 N종목 벤치 (시드 고정 · §4-4)
    import random
    for n in GRID_N:
        cal_r = []
        for trial in range(RANDOM_TRIALS):
            rng = random.Random(1000 + trial)

            def rpick(rows, k, _rng=rng):
                return [r["t"] for r in _rng.sample(rows, min(k, len(rows)))]
            d_, r_, _ = _daily_curve(snaps, px, cal, n, 60, gone, picker=rpick)
            m = _metrics(r_, d_)
            if m.get("calmar") is not None:
                cal_r.append(m["calmar"])
        if cal_r:
            cal_r.sort()
            diag[f"random_N{n}_H60"] = {
                "trials": len(cal_r), "calmar_mean": round(st.mean(cal_r), 3),
                "calmar_p2_5": cal_r[int(len(cal_r) * 0.025)],
                "calmar_p97_5": cal_r[min(len(cal_r) - 1, int(len(cal_r) * 0.975))]}

    # ── §3 채택 (참조 구성 등록) ──
    adoption: Dict[str, Any] = {}
    passing = []
    for k in ledger:
        r = results[k]
        m = r["metrics"]
        cond = {
            "bh": bool(r.get("passes_bh_fdr")),
            "t3": bool((r["excess_nw"].get("t") or 0) >= ADOPT_T),
            "calmar_1": bool((m.get("calmar") or -9) >= CALMAR_MIN),
            "mdd_20": bool((m.get("mdd") or -9) >= MDD_MIN),
            "split_both": all(r["split"][hh]["sign_pos"] is True for hh in ("H1", "H2")),
            "beats_bench": bool((r.get("excess_total_pct") or -9e9) > 0),
        }
        cond["all_pass"] = all(cond.values())
        adoption[k] = cond
        if cond["all_pass"]:
            passing.append(k)
    # N 최소 · H 최대 우선 (보수적)
    ref = None
    if passing:
        ref = sorted(passing, key=lambda k: (int(k.split("_")[0][1:]),
                                             -int(k.split("_H")[1])))[0]
    adoption["reference_config"] = ref
    adoption["rule"] = ("전 조건 충족자 중 N 최소·H 최대 (보수적). 최고 Calmar 선택 금지. "
                        "전원 미충족 = 참조 등록 없음 — 등록 §3 이 가장 가능성 높다고 명시")

    doc = {
        "_meta": {
            "prereg": "docs/PREREG_PORTFOLIO_BACKTEST_2026_08_13.md",
            "approved": "PM 2026-08-13 '승인. ㄱㄱ'",
            "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00",
                                         time.localtime(time.time() + 9 * 3600)),
            "grid": {"N": list(GRID_N), "H": list(GRID_H)},
            "roundtrip_cost_pct": round(ROUNDTRIP * 100, 3),
            "win_condition": {"calmar_min": CALMAR_MIN, "mdd_min": MDD_MIN},
            "not_reproduced": ["손절·트레일링·기간손절", "Kelly/섹터/베타 가드",
                               "배당(가격 수익률만)", "시장충격"],
            "in_sample_caveat": "C3 축 선택이 같은 창(#355 §1) — 선택 편향 상속",
            "dsr_m_trials": M_TRIALS,
            "scope": "참조 구성 등록일 뿐 운영 무변경 (§3)",
        },
        "coverage": {"snapshots": len(snaps),
                     "window": [snaps[0]["as_of"], snaps[-1]["as_of"]],
                     "kospi_days": len(kospi),
                     "elapsed_sec": round(time.time() - t0, 1)},
        "results": results,
        "diagnostics": diag,
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
    r = run(a.lake, limit=a.limit)
    if r.get("status") == "no_snapshots":
        print("[portfolio] no_snapshots", file=sys.stderr)
        return 1
    c = r["coverage"]
    print(f"\n[portfolio] 단면 {c['snapshots']} · KOSPI {c['kospi_days']}일 · {c['elapsed_sec']}s")
    print(f"\n{'구성':10}{'CAGR%':>8}{'MDD':>8}{'Calmar':>8}{'Sharpe':>8}"
          f"{'초과%':>9}{'t':>7}{'회전':>7}{'채택':>7}")
    for k in [f"N{n}_H{h}" for n in GRID_N for h in GRID_H]:
        v = r["results"][k]
        m = v["metrics"]
        ok = "충족" if r["adoption"][k]["all_pass"] else "—"
        print(f"{k:10}{(m.get('cagr_pct') or 0):>8.2f}{(m.get('mdd') or 0):>8.3f}"
              f"{(m.get('calmar') or 0):>8.2f}{(m.get('sharpe') or 0):>8.2f}"
              f"{(v.get('excess_total_pct') or 0):>9.1f}{(v['excess_nw'].get('t') or 0):>7.2f}"
              f"{v.get('turnover_per_reb', 0):>7.2f}{ok:>7}")
    d = r["diagnostics"]
    print(f"\n[진단] KOSPI 매수보유: {d.get('kospi_buy_hold')}")
    print(f"       현행규칙 N7_H14: {d.get('current_rule_N7_H14')}")
    for n in GRID_N:
        print(f"       무작위 N{n}_H60: {d.get(f'random_N{n}_H60')}")
    print(f"       비용 0/1x/2x Calmar: {d.get('cost_0',{}).get('calmar')} / "
          f"{d.get('cost_base',{}).get('calmar')} / {d.get('cost_2x',{}).get('calmar')}")
    print(f"\n참조 구성: {r['adoption']['reference_config'] or '없음 (전원 미충족 — 현행 유지)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
