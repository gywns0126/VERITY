# -*- coding: utf-8 -*-
"""kr_stoploss_layer — 손절 계층 백테스트 재현.

사전등록 `docs/PREREG_STOPLOSS_BACKTEST_2026_08_15.md` · PM 승인 2026-08-15 "ㄱㄱ" (§6 4건).
🚨 관측 산출물만. **실행 1회 소진.** 이 등록으로 운영을 바꾸지 않는다 (§4).

#355 이후 백테스트 8회가 전부 **손절 없이** 잰 것이다. 산출물이 매번
`not_reproduced: 손절·트레일링·기간손절` 을 신고했는데도 그 위에서 배분·가중·배당을 논했다.
운영에는 손절이 있으니 지금까지의 −0.66%/월 은 우리가 실제로 운용하는 것을 잰 숫자가 아니다.

🚨 §0 함정 — 손절은 사후 조정이 너무 쉽다(−10/−15/−25 를 쓸면 반드시 뭔가 좋아 보인다).
   방어 = **새로 정하는 수치 0.** 후보 3안이 전부 이미 존재하는 규칙이다.

  S0 무손절      현행 백테스트 (#363~#368 기준선 · 재현 게이트)
  S1 현행 운영    고정 max(−20, ATR개별) + 트레일링 −3%
  S2 8-09 이전    고정 max(−5,  ATR개별) + 트레일링 −3%

기간 손절(14일)은 리밸런스 창 20/60일과 충돌해 **원장에서 제외**하고 S1T 기술 통계로만 본다
(§1-2 — 넣으면 '청산 규칙 효과' 와 '보유기간 단축' 이 분리되지 않는다).
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
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from api.quant.backtest import kr_portfolio as kp  # noqa: E402
from api.quant.backtest.kr_fundamental import COMMISSION, SELL_TAX  # noqa: E402
from api.quant.backtest.kr_price_axes import ENTRY_LAG  # noqa: E402
from api.quant.backtest.kr_safety_score import bh_fdr, nw_t, two_sided_p  # noqa: E402
from api.quant.backtest.kr_segment_allocation import (  # noqa: E402
    GRID_H, N_HOLD, _bench_daily, _half, _monthly, build, pick_a0,
)

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "data")
OUT_PATH = os.path.join(_DATA, "analysis", "prereg_stoploss_20260815.json")

# ── 등록값 — 전부 운영 상수에서 가져온다. 이 파일에서 새로 정하는 수치 0 (§0) ──────
ATR_MULT = 2.5                 # api.config.ATR_STOP_MULTIPLIER
ATR_MIN_BARS = 20              # api.config.ATR_MIN_PERIOD
FALLBACK_STOP = -5.0           # api.config.FALLBACK_STOP_PCT (음수)
TRAILING_PCT = 3.0             # VAMS_PROFILES['moderate']['trailing_stop_pct']
MAX_HOLD_DAYS = 14             # 'moderate' — S1T 변형 전용 (원장 제외)
CAPS = {"S1": -20.0, "S2": -5.0}   # moderate 현행 / 2026-08-09 이전
ADOPT_T = 3.0
BONF6 = 2.64
M_TRIALS = 92                  # DSR 누적 시도 (86 + 본건 6)
GATE = {20: -0.6555, 60: -0.9596}
GATE_TOL = 0.01


def atr14_wilder(h: Sequence[float], lo: Sequence[float],
                 c: Sequence[float]) -> Optional[float]:
    """Wilder EMA(alpha=1/14) ATR — `api.analyzers.technical.compute_atr_14d` 와 같은 정의."""
    n = len(c)
    if n < ATR_MIN_BARS:
        return None
    tr: List[float] = []
    for i in range(1, n):
        tr.append(max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1])))
    if len(tr) < 14:
        return None
    a = 1.0 / 14.0
    v = tr[0]
    for x in tr[1:]:
        v = a * x + (1 - a) * v
    return v if v > 0 else None


def entry_stop_pct(px_t: Dict[str, List[float]], idx: int) -> Tuple[float, str]:
    """진입 시점 개별 손절선(%). 운영 `trade_planner` 와 같은 산식 — 진입 후 재계산 없음."""
    lo = max(0, idx - 250)
    atr = atr14_wilder(px_t["h"][lo:idx + 1], px_t["l"][lo:idx + 1], px_t["c"][lo:idx + 1])
    price = px_t["c"][idx]
    if atr is None or not price or price <= 0:
        return FALLBACK_STOP, "fixed_fallback"
    return -round(atr * ATR_MULT / price * 100, 2), "atr_dynamic"


def _curve(snaps, px, cal, gone, h: int, cap: Optional[float],
           time_stop: bool = False) -> Dict[str, Any]:
    """일별 곡선. cap=None 이면 무손절(S0) — kp._daily_curve 와 회계가 같아야 한다.

    회계 (§1-3, 계산 전 고정):
      · 판정·체결 = 일봉. 저가 ≤ 손절가면 **손절가** 체결, 시가 < 손절가면 **시가** 체결(갭)
      · 트레일링 고점 = 일중 고가 (운영 30분 스냅샷보다 자주 트리거 = 보수 방향)
      · 청산 후 = 다음 리밸런스까지 현금(무이자). 슬롯은 유지되고 수익 0 을 기여한다
      · 비용 = 청산 시 매도측(C+T), 리밸런스 신규 매수 시 매수측(C).
        손절 없이 교체되는 슬롯은 (C+T)+C = ROUNDTRIP 로 #367 과 정확히 일치한다
      · 동시 충족 시 **고정 손절 우선** (운영 check_stop_loss 판정 순서)
    """
    reb = [s for i, s in enumerate(snaps) if i % max(1, round(h / 20)) == 0] if h != 20 else snaps
    days: List[int] = []
    rets: List[float] = []
    turn_total = cost_total = 0.0
    prev_held: List[str] = []
    prev_stopped: set = set()
    n_reb = 0
    stop_exits = 0
    ex = {"fixed": [], "trailing": [], "time": [], "rebalance": 0}
    method_cnt = {"profile_cap": 0, "individual_atr": 0, "fixed_fallback": 0}
    gap_fills = fills = 0

    for si, snap in enumerate(reb):
        k = snap["cal_idx"]
        entry_i = k + ENTRY_LAG
        end_i = (reb[si + 1]["cal_idx"] + ENTRY_LAG) if si + 1 < len(reb) else min(
            entry_i + h, len(cal) - 1)
        if entry_i >= len(cal) or end_i <= entry_i:
            continue
        held = pick_a0(snap["rows"], N_HOLD)
        if not held:
            continue
        n_reb += 1
        # ── 비용: 매도(직전 보유 중 손절 안 된 이탈분) + 매수(신규) ──
        sells = [t for t in prev_held if t not in held and t not in prev_stopped]
        # 🚨 손절로 이미 팔린 종목이 다시 뽑히면 **재매수 비용이 든다**.
        #    `t not in prev_held` 만 보면 계속 들고 있던 것으로 오인해 비용이 샌다.
        buys = [t for t in held if t not in prev_held or t in prev_stopped]
        ex["rebalance"] += len(sells)
        cost = (len(sells) * (COMMISSION + SELL_TAX) + len(buys) * COMMISSION) / len(held)
        turn_total += len(buys) / len(held)
        cost_total += cost

        # ── 보유 상태 초기화 ──
        state: Dict[str, Dict[str, Any]] = {}
        for t in held:
            s = px.get(t)
            if not s:
                continue
            i0 = bisect.bisect_right(s["d"], cal[entry_i]) - 1
            if i0 < 0 or s["d"][i0] != cal[entry_i]:
                continue
            e = {"entry": s["c"][i0], "high": s["c"][i0], "out": False, "days": 0,
                 "trail_on": False, "armed_at": float("inf")}
            if cap is not None:
                ind, meth = entry_stop_pct(s, i0)
                eff = max(cap, ind)                     # 덜 음수 = 더 빨리 트리거
                e["stop_pct"] = eff
                e["method"] = (meth if meth == "fixed_fallback"
                               else ("individual_atr" if eff == ind else "profile_cap"))
                method_cnt[e["method"]] = method_cnt.get(e["method"], 0) + 1
                # 1R = 진입가 − 손절가 · 트레일링 개방 = +2R (운영 target_2)
                r1 = e["entry"] * (-eff / 100.0)
                e["armed_at"] = e["entry"] + 2 * r1
            state[t] = e

        first = True
        for di in range(entry_i, end_i):
            d0, d1 = cal[di], cal[di + 1]
            rs: List[float] = []
            for t in held:
                e = state.get(t)
                if e is None:
                    continue
                if e["out"]:
                    rs.append(0.0)                       # 현금 슬롯 (무이자)
                    continue
                s = px[t]
                a = bisect.bisect_right(s["d"], d0) - 1
                b = bisect.bisect_right(s["d"], d1) - 1
                if a < 0 or b < 0 or s["d"][a] != d0:
                    continue
                if s["d"][b] != d1:
                    if t in gone and s["d"][-1] == d0:
                        rs.append(-0.30)
                        e["out"] = True
                    continue
                p0 = s["c"][a]
                if not p0 or p0 <= 0:
                    continue
                op, hi, lw, cl = s["o"][b], s["h"][b], s["l"][b], s["c"][b]
                if cl <= 0:
                    continue
                e["days"] += 1
                exit_px = None
                reason = None
                if cap is not None:
                    stop_px = e["entry"] * (1 + e["stop_pct"] / 100.0)
                    if lw <= stop_px:                    # 고정 손절 — 우선 판정
                        exit_px, reason = (op if op < stop_px else stop_px), "fixed"
                    else:
                        # 🚨 트레일링은 운영에서 **+2R 도달 후에만** 열린다
                        #    (engine.check_stop_loss 의 trailing_active / exit_targets target_2).
                        #    이 게이트를 빼면 일중 변동폭 3% 종목이 진입 이튿날 전부 털린다
                        #    — 스모크 실측 144 슬롯 중 135건 발동, MDD −1.6% 라는 허구가 나왔다.
                        if e["high"] >= e["armed_at"]:
                            e["trail_on"] = True
                        trail_px = e["high"] * (1 - TRAILING_PCT / 100.0)
                        if e["trail_on"] and e["high"] > e["entry"] and lw <= trail_px:
                            exit_px, reason = (op if op < trail_px else trail_px), "trailing"
                    if exit_px is None and time_stop and e["days"] >= MAX_HOLD_DAYS:
                        exit_px, reason = cl, "time"
                if exit_px is not None:
                    r = exit_px / p0 - 1.0 - (COMMISSION + SELL_TAX)
                    rs.append(r)
                    # 🚨 청산 매도 비용을 누적에 포함한다 — 빼면 손절안의 비용이
                    #    무손절보다 **낮게** 보고되는 착시가 생긴다(스모크 실측 0.10 vs 1.01%)
                    cost_total += (COMMISSION + SELL_TAX) / len(held)
                    stop_exits += 1
                    e["out"] = True
                    ex[reason].append(exit_px / e["entry"] - 1.0)
                    fills += 1
                    if reason != "time" and op < (exit_px + 1e-9):
                        gap_fills += 1
                else:
                    rs.append(cl / p0 - 1.0)
                    if hi > e["high"]:
                        e["high"] = hi
            r = (sum(rs) / len(rs)) if rs else 0.0
            if first:
                r -= cost
                first = False
            days.append(d1)
            rets.append(r)
        prev_held = held
        prev_stopped = {t for t, e in state.items() if e["out"]}

    meta = {"rebalances": n_reb,
            "turnover_per_reb": round(turn_total / max(1, n_reb), 4),
            "stop_exits_per_reb": round(stop_exits / max(1, n_reb) / N_HOLD, 4),
            "cost_total_pct": round(cost_total * 100, 3)}
    return {"days": days, "rets": rets, "meta": meta, "exits": ex,
            "methods": method_cnt, "gap_fill_pct": (round(gap_fills / fills * 100, 1)
                                                    if fills else None),
            "n_stop_fills": fills}


def _summ(name: str, ex: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"rebalance_sells": ex["rebalance"]}
    for k in ("fixed", "trailing", "time"):
        v = ex[k]
        out[k] = {"n": len(v),
                  "mean_ret_pct": (round(st.mean(v) * 100, 3) if v else None),
                  "sum_ret_pct": (round(sum(v) * 100, 2) if v else None),
                  "win_rate": (round(sum(1 for x in v if x > 0) / len(v) * 100, 1)
                               if v else None)}
    return out


def run(lake: str, out_path: str = OUT_PATH, limit: int = 0) -> Dict[str, Any]:
    t0 = time.time()
    snaps, px, cal, gone, drop = build(lake)
    if limit:
        snaps = snaps[:limit]
    if not snaps:
        return {"status": "no_snapshots"}
    kospi = kp._load_kospi()

    variants = {"S0": None, "S1": CAPS["S1"], "S2": CAPS["S2"]}
    curves: Dict[str, Dict[int, Dict[str, Any]]] = {}
    for v, cap in variants.items():
        curves[v] = {}
        for h in GRID_H:
            c = _curve(snaps, px, cal, gone, h, cap)
            if not c["days"]:
                return {"status": "empty_curve", "variant": v, "h": h}
            curves[v][h] = c
    # S1T — 기간손절 포함 (기술 통계 전용, 원장 제외 §1-2)
    s1t = {h: _curve(snaps, px, cal, gone, h, CAPS["S1"], time_stop=True) for h in GRID_H}

    descriptive: Dict[str, Any] = {}
    excess: Dict[str, Dict[int, Dict[int, float]]] = {}
    for v in list(variants) + ["S1T"]:
        excess[v] = {}
        for h in GRID_H:
            c = curves[v][h] if v in curves else s1t[h]
            d = c["days"]
            b = _bench_daily(d, kospi)
            exd = [x - y for x, y in zip(c["rets"], b)]
            excess[v][h] = _monthly(d, exd)
            descriptive[f"{v}_H{h}"] = {
                **kp._metrics(c["rets"], d), **c["meta"],
                "excess_monthly_mean_pct": round(st.mean(excess[v][h].values()) * 100, 4),
                "excess_total_pct": round((math.prod(1 + x for x in exd) - 1) * 100, 2),
                "exits": _summ(v, c["exits"]), "methods": c["methods"],
                "gap_fill_pct": c["gap_fill_pct"], "n_stop_fills": c["n_stop_fills"],
            }

    # ── 원장 6검정 (§2) ──
    ledger = [(a, b, h) for a, b in (("S1", "S0"), ("S2", "S0"), ("S1", "S2")) for h in GRID_H]
    results: Dict[str, Any] = {}
    keys: List[str] = []
    for a, b, h in ledger:
        key = f"{a}_minus_{b}_{h}d"
        keys.append(key)
        ma, mb = excess[a][h], excess[b][h]
        ks = sorted(set(ma) & set(mb))
        ser = [ma[k] - mb[k] for k in ks]
        lag = 1 if h <= 20 else 3
        hv: Dict[str, List[float]] = {"H1": [], "H2": []}
        for k_, x in zip(ks, ser):
            hv[_half(k_)].append(x)
        results[key] = {
            "nw": nw_t(ser, lag), "n_months": len(ser),
            "mean_pct": round(st.mean(ser) * 100, 4) if ser else None,
            "split": {k_: {"n": len(v), "mean_pct": (round(st.mean(v) * 100, 4) if v else None)}
                      for k_, v in hv.items()},
        }
    pv = [two_sided_p(results[k]["nw"].get("t"), results[k]["nw"].get("n")) for k in keys]
    for k, p_, ok in zip(keys, pv, bh_fdr(pv, q=0.05)):
        r = results[k]
        r["p_two_sided"] = round(p_, 6) if p_ is not None else None
        r["passes_bh_fdr"] = ok
        r["passes_t3"] = bool(r["nw"].get("t") is not None and abs(r["nw"]["t"]) >= ADOPT_T)
        t_ = r["nw"].get("t")
        # 🚨 CI 필수 (#367 정정 학습 — t 만 보고하면 '증거 없음' 을 '효과 없음' 으로 오독한다)
        if t_ and r.get("mean_pct") is not None:
            se = abs(r["mean_pct"] / t_)
            r["se_pct"] = round(se, 4)
            r["ci95_pct"] = [round(r["mean_pct"] - 1.96 * se, 4),
                             round(r["mean_pct"] + 1.96 * se, 4)]
            r["detectable_at_t3_pct"] = round(se * 3, 4)

    gate = {}
    for h in GRID_H:
        got = descriptive[f"S0_H{h}"]["excess_monthly_mean_pct"]
        gate[f"H{h}"] = {"expected": GATE[h], "got": got, "diff": round(got - GATE[h], 4),
                         "pass": bool(abs(got - GATE[h]) <= GATE_TOL)}
    gate["all_pass"] = all(v["pass"] for k, v in gate.items() if k.startswith("H"))

    doc = {
        "_meta": {
            "prereg": "docs/PREREG_STOPLOSS_BACKTEST_2026_08_15.md",
            "approved": "PM 2026-08-15 'ㄱㄱ' (§6 4건)",
            "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00",
                                         time.localtime(time.time() + 9 * 3600)),
            "tests": len(keys), "adopt_t": ADOPT_T, "bonferroni": BONF6,
            "dsr_m_trials": M_TRIALS, "n_hold": N_HOLD,
            "rules": {"S0": "무손절", "S1": f"max({CAPS['S1']}, ATR개별) + 트레일링 -{TRAILING_PCT}%",
                      "S2": f"max({CAPS['S2']}, ATR개별) + 트레일링 -{TRAILING_PCT}%",
                      "S1T": f"S1 + 기간손절 {MAX_HOLD_DAYS}일 (기술통계 전용)"},
            "atr": f"wilder_ema_14 × {ATR_MULT} · 진입 시 1회 산출 후 고정 · fallback {FALLBACK_STOP}%",
            "fill_rule": "저가≤손절가 → 손절가 체결, 시가<손절가 → 시가 체결(갭). 트레일링 고점=일중 고가",
            "cost": f"청산 매도 {(COMMISSION + SELL_TAX) * 100:.3f}% · 신규 매수 {COMMISSION * 100:.3f}%",
            "new_numbers_chosen_here": 0,
            "scope": "이 등록으로 운영을 바꾸지 않는다. 손절은 이미 운영 중이다 (§4)",
            "not_reproduced": ["부분 익절(exit_targets R-multiple)", "재진입", "Kelly/섹터 가드",
                               "배당", "시장충격"],
            "not_vams": "VAMS 재현이 아니다 — 등록 백테스트 포트(동일가중 12종)에 청산 계층만 얹었다",
        },
        "coverage": {"snapshots": len(snaps), "window": [snaps[0]["as_of"], snaps[-1]["as_of"]],
                     "elapsed_sec": round(time.time() - t0, 1)},
        "descriptive": descriptive,
        "results": results,
        "diagnostics": {"reproduction_gate": gate},
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
    ap.add_argument("--out", default=OUT_PATH)
    a = ap.parse_args()
    r = run(a.lake, out_path=a.out, limit=a.limit)
    if r.get("status"):
        print(f"[stoploss] {r['status']} {r}", file=sys.stderr)
        return 1
    c, g = r["coverage"], r["diagnostics"]["reproduction_gate"]
    print(f"\n[stoploss] 단면 {c['snapshots']} · {c['window'][0]}~{c['window'][1]} · {c['elapsed_sec']}s")
    print(f"\n재현 게이트 (§3-1) — {'통과' if g['all_pass'] else '실패'}")
    for h in GRID_H:
        v = g[f"H{h}"]
        print(f"    H{h}: 기대 {v['expected']} · 실측 {v['got']} · 차 {v['diff']:+.4f} "
              f"→ {'OK' if v['pass'] else 'FAIL'}")
    print(f"\n{'구성':9}{'CAGR%':>8}{'MDD':>8}{'Calmar':>8}{'Sharpe':>8}{'초과%/월':>10}"
          f"{'회전':>7}{'비용%':>8}")
    for v in ("S0", "S1", "S2", "S1T"):
        for h in GRID_H:
            d = r["descriptive"][f"{v}_H{h}"]
            print(f"{v}_H{h:<6}{(d.get('cagr_pct') or 0):>8.2f}{(d.get('mdd') or 0):>8.3f}"
                  f"{(d.get('calmar') or 0):>8.3f}{(d.get('sharpe') or 0):>8.2f}"
                  f"{d['excess_monthly_mean_pct']:>10.4f}{d['turnover_per_reb']:>7.2f}"
                  f"{d['cost_total_pct']:>8.2f}")
    print(f"\n{'검정':22}{'평균%':>9}{'t':>7}{'p':>8}{'BH':>5}{'t≥3':>5}   95% CI · 검출하한")
    for k, v in r["results"].items():
        ci = v.get("ci95_pct")
        tail = (f"[{ci[0]}, {ci[1]}] · {v.get('detectable_at_t3_pct')}" if ci else "")
        print(f"{k:22}{(v.get('mean_pct') or 0):>9.4f}{(v['nw'].get('t') or 0):>7.2f}"
              f"{(v.get('p_two_sided') if v.get('p_two_sided') is not None else float('nan')):>8.4f}"
              f"{('통과' if v.get('passes_bh_fdr') else '—'):>5}"
              f"{('O' if v.get('passes_t3') else '—'):>5}   {tail}")
    print("\n[진단2] 청산 사유 분해 (건수 · 평균수익% · 승률%)")
    for v in ("S1", "S2", "S1T"):
        d = r["descriptive"][f"{v}_H20"]["exits"]
        print(f"  {v}_H20  고정 {d['fixed']['n']}건 {d['fixed']['mean_ret_pct']}% "
              f"승률 {d['fixed']['win_rate']} · 트레일링 {d['trailing']['n']}건 "
              f"{d['trailing']['mean_ret_pct']}% 승률 {d['trailing']['win_rate']} · "
              f"기간 {d['time']['n']}건 {d['time']['mean_ret_pct']}% · "
              f"리밸런스매도 {d['rebalance_sells']}")
    print("\n[진단3] stop_method 분해 (운영 8/9 실측은 profile_cap 15 : individual_atr 0)")
    for v in ("S1", "S2"):
        print(f"  {v}_H20 {r['descriptive'][f'{v}_H20']['methods']}")
    print("\n[진단4] 갭 체결 비중 · [진단5] 회전/비용")
    for v in ("S1", "S2"):
        d = r["descriptive"][f"{v}_H20"]
        s0 = r["descriptive"]["S0_H20"]
        print(f"  {v}_H20 갭 {d['gap_fill_pct']}% (체결 {d['n_stop_fills']}건) · "
              f"회전 {d['turnover_per_reb']} (S0 {s0['turnover_per_reb']}) · "
              f"비용 {d['cost_total_pct']}% (S0 {s0['cost_total_pct']}%)")
    print("\n[진단6] MDD·Calmar (손절의 본래 목적)")
    for h in GRID_H:
        print("  " + " · ".join(
            f"{v}_H{h} MDD {r['descriptive'][f'{v}_H{h}']['mdd']} Calmar "
            f"{r['descriptive'][f'{v}_H{h}']['calmar']}" for v in ("S0", "S1", "S2")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
