# -*- coding: utf-8 -*-
"""kr_market_neutral — 시장 노출 제거(중립화) 검정.

사전등록 `docs/PREREG_MARKET_NEUTRAL_2026_08_15.md` · PM 승인 2026-08-15 "ㄱㄱ" (§6 4건).
🚨 관측 산출물만. **실행 1회 소진.** 이 등록으로 운영을 바꾸지 않는다 (§4).

오늘 검증에서 4개 등록의 지표가 잘못 놓여 있었음이 드러났다 —
`−0.6555%/월 = 알파 +0.71 − 베타갭 1.28`. 베타 0.19 포트를 베타 1.0 지수와 raw 로 견줬다.

🚨 §0 — **결과를 미리 아는 등록이다.** 알파 t 1.51(S0)/2.05(S1) 로 임계 3.0 미달이고
   잔차 반쪽이 부호를 뒤집는다(S0 +0.635→−0.589 · S1 +0.876→−0.812).
   그래서 §4 채택 조건 ③(H1·H2 양쪽 양수)을 결정적 조건으로 두고 완화하지 않는다.

🚨 공매도 제도 실측이 설계를 결정했다 — 개별종목 숏 자유 구간이 **1,604일 중 337일(21.0%)**.
   그래서 주 후보는 **지수 헤지(L1)** 이고 종목 롱숏(L2)은 반사실로 강등한다.

  L0 롱온리     #370 의 S0 그대로 (재현 게이트)
  L1 지수 헤지  L0 + 인버스 ETF · 헤지비율 = PIT 트레일링 베타(창 = 격자 h)
  L2 종목 롱숏  상위12 롱 50% / 하위12 숏 50% (자본 100% 기준 통일)
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
OUT_PATH = os.path.join(_DATA, "analysis", "prereg_market_neutral_20260815.json")

# ── 등록값 (§1·§2·§4) — 새로 정하는 수치 0 ────────────────────────────────
INVERSE_FEE_ANNUAL = 0.0064        # KODEX 인버스 운용보수 0.64%/년
BORROW_RATES = (0.025, 0.040, 0.055)   # §3-5 대주 수수료 민감도 3점 (연) · 🚨 공표치 미확인
BORROW_PRIMARY = 0.040
SIDE_W = 0.5                       # L2 롱/숏 각 50% — 자본 100% 기준을 L0/L1 과 통일
ADOPT_T = 3.0
BONF6 = 2.64
M_TRIALS = 98                      # DSR 누적 시도 (92 + 본건 6)
RESID_BETA_MAX = 0.2               # §3-3 헤지 작동 확인 임계
GATE = {20: -0.5982, 60: -0.9166}  # 🚨 #370 실측 (#369 가드로 이동한 기준선 · §6-3 승인)
GATE_TOL = 0.01

# 🚨 공매도 제도 구간 (실호출 확인 2026-08-15)
SHORT_FREE = ((20200204, 20200315), (20250331, 20261231))
SHORT_PARTIAL = ((20210503, 20231105),)     # K200/KQ150 만 — 구성종목 데이터 부재로 근사


def _regime(d: int) -> str:
    for a, b in SHORT_FREE:
        if a <= d <= b:
            return "free"
    for a, b in SHORT_PARTIAL:
        if a <= d <= b:
            return "partial"
    return "banned"


def pick_bottom(rows: List[Dict[str, Any]], n: int) -> List[str]:
    return [r["t"] for r in sorted(rows, key=lambda z: z["score"])[:n]]


def _win(px, tickers, lo: int, hi: int) -> Dict[str, Dict[int, float]]:
    out: Dict[str, Dict[int, float]] = {}
    for t in tickers:
        s = px.get(t)
        if not s:
            continue
        a = bisect.bisect_left(s["d"], lo)
        b = bisect.bisect_right(s["d"], hi)
        if a < b:
            out[t] = dict(zip(s["d"][a:b], s["c"][a:b]))
    return out


def _side_ret(held, wp, px, gone, d0: int, d1: int) -> Optional[float]:
    """동일가중 한 쪽의 일간 수익. kp._daily_curve 와 같은 회계."""
    rs: List[float] = []
    for t in held:
        m = wp.get(t)
        if not m:
            continue
        p0, p1 = m.get(d0), m.get(d1)
        if p0 is None or p0 <= 0:
            continue
        if p1 is None:
            s = px.get(t)
            if t in gone and s and s["d"][-1] == d0:
                rs.append(-0.30)
            continue
        if p1 <= 0:
            continue
        rs.append(p1 / p0 - 1.0)
    return (sum(rs) / len(rs)) if rs else None


def _beta_pit(days: Sequence[int], rets: Sequence[float], bench: Dict[int, float],
              h: int) -> Optional[float]:
    """진입 시점까지의 실현 수익으로만 추정한 트레일링 베타 (미래 정보 0).

    추정 창 = 그 격자의 리밸런스 창 h — **새 파라미터를 만들지 않기 위해** 격자값을 재사용한다.
    """
    if len(rets) < h:
        return None
    y = list(rets[-h:])
    xs = list(days[-h:])
    ks = sorted(bench)
    x: List[float] = []
    for i, d in enumerate(xs):
        j = bisect.bisect_right(ks, d) - 1
        j0 = bisect.bisect_right(ks, xs[i - 1]) - 1 if i else j - 1
        x.append(0.0 if (j <= 0 or j0 < 0 or j == j0) else bench[ks[j]] / bench[ks[j0]] - 1.0)
    mx, my = st.mean(x), st.mean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    if sxx <= 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / sxx


def curves(snaps, px, cal, gone, kospi, h: int,
           borrow: float = BORROW_PRIMARY) -> Dict[str, Any]:
    """L0/L1/L2 를 한 번에. L0 는 kp._daily_curve(=#370 S0) 와 회계가 같아야 한다."""
    reb = [s for i, s in enumerate(snaps) if i % max(1, round(h / 20)) == 0] if h != 20 else snaps
    days: List[int] = []
    l0: List[float] = []
    l1: List[float] = []
    l2: List[float] = []
    hedge_w: List[float] = []
    turn = cost = 0.0
    prev_l: List[str] = []
    prev_s: List[str] = []
    n_reb = 0
    fee_d = INVERSE_FEE_ANNUAL / 252.0
    borrow_d = borrow / 252.0
    ks = sorted(kospi)

    for si, snap in enumerate(reb):
        k = snap["cal_idx"]
        e = k + ENTRY_LAG
        end = (reb[si + 1]["cal_idx"] + ENTRY_LAG) if si + 1 < len(reb) else min(
            e + h, len(cal) - 1)
        if e >= len(cal) or end <= e:
            continue
        longs = pick_a0(snap["rows"], N_HOLD)
        shorts = pick_bottom(snap["rows"], N_HOLD)
        if not longs:
            continue
        n_reb += 1
        c_l = len(set(longs) - set(prev_l)) / len(longs) * (2 * COMMISSION + SELL_TAX)
        c_s = (len(set(shorts) - set(prev_s)) / max(1, len(shorts))
               * (2 * COMMISSION + SELL_TAX)) * SIDE_W
        turn += len(set(longs) - set(prev_l)) / len(longs)
        cost += c_l
        prev_l, prev_s = longs, shorts
        # 🚨 PIT 베타 — 진입 전까지의 실현 수익만 사용. 첫 창은 추정 불가 → 헤지 0
        beta = _beta_pit(days, l0, kospi, h)
        # 🚨 클램프 [0, 1.5] — 등록 후 추가한 가드다. 음수 헤지(시장 매수)와 1.5x 초과
        #    레버리지를 배제하는 경계이며 산출물 _meta 에 신고한다.
        beta = 0.0 if beta is None else max(0.0, min(1.5, beta))
        # 헤지 리밸런싱 비용 — ETF 는 증권거래세 면제이므로 수수료만
        c_h = abs(beta - (hedge_w[-1] if hedge_w else 0.0)) * COMMISSION
        hedge_w.append(beta)
        lo_d, hi_d = cal[e], cal[end]
        wp = _win(px, [r["t"] for r in snap["rows"]], lo_d, hi_d)
        first = True
        for di in range(e, end):
            d0, d1 = cal[di], cal[di + 1]
            rl = _side_ret(longs, wp, px, gone, d0, d1)
            rs_ = _side_ret(shorts, wp, px, gone, d0, d1)
            if rl is None:
                continue
            j = bisect.bisect_right(ks, d1) - 1
            j0 = bisect.bisect_right(ks, d0) - 1
            rm = 0.0 if (j <= 0 or j0 < 0 or j == j0) else kospi[ks[j]] / kospi[ks[j0]] - 1.0
            a0 = rl - (c_l if first else 0.0)
            # L1 = 롱 + 베타만큼 인버스 ETF (일간 −1×시장 − 보수)
            a1 = a0 + beta * (-rm - fee_d) - (c_h if first else 0.0)
            # L2 = 롱 50% − 숏 50% − 대주 수수료
            a2 = (SIDE_W * a0 - SIDE_W * ((rs_ if rs_ is not None else rm) + borrow_d)
                  - (c_s if first else 0.0))
            first = False
            days.append(d1)
            l0.append(a0)
            l1.append(a1)
            l2.append(a2)
    return {"days": days, "L0": l0, "L1": l1, "L2": l2,
            "meta": {"rebalances": n_reb, "turnover_per_reb": round(turn / max(1, n_reb), 4),
                     "cost_total_pct": round(cost * 100, 3),
                     "hedge_beta_mean": round(st.mean(hedge_w), 4) if hedge_w else None,
                     "hedge_beta_min": round(min(hedge_w), 4) if hedge_w else None,
                     "hedge_beta_max": round(max(hedge_w), 4) if hedge_w else None}}


def _realized_beta(days, rets, kospi) -> Optional[float]:
    b = _bench_daily(days, kospi)
    mx, my = st.mean(b), st.mean(rets)
    sxx = sum((a - mx) ** 2 for a in b)
    if sxx <= 0:
        return None
    return round(sum((a - mx) * (c - my) for a, c in zip(b, rets)) / sxx, 4)


def _test(m: Dict[int, float], lag: int) -> Dict[str, Any]:
    kk = sorted(m)
    ser = [m[x] for x in kk]
    hv: Dict[str, List[float]] = {"H1": [], "H2": []}
    for x, v in zip(kk, ser):
        hv[_half(x)].append(v)
    r: Dict[str, Any] = {
        "nw": nw_t(ser, lag), "n_months": len(ser),
        "mean_pct": round(st.mean(ser) * 100, 4) if ser else None,
        "split": {a: {"n": len(v), "mean_pct": (round(st.mean(v) * 100, 4) if v else None),
                      "positive": (st.mean(v) > 0 if v else None)} for a, v in hv.items()},
    }
    t = r["nw"].get("t")
    if t and r["mean_pct"] is not None:
        se = abs(r["mean_pct"] / t)
        r["se_pct"] = round(se, 4)
        r["ci95_pct"] = [round(r["mean_pct"] - 1.96 * se, 4), round(r["mean_pct"] + 1.96 * se, 4)]
        r["detectable_at_t3_pct"] = round(se * 3, 4)
    return r


def run(lake: str, out_path: str = OUT_PATH, limit: int = 0) -> Dict[str, Any]:
    t0 = time.time()
    snaps, px, cal, gone, drop = build(lake)
    if limit:
        snaps = snaps[:limit]
    if not snaps:
        return {"status": "no_snapshots"}
    kospi = kp._load_kospi()

    base: Dict[int, Dict[str, Any]] = {}
    for h in GRID_H:
        c = curves(snaps, px, cal, gone, kospi, h)
        if not c["days"]:
            return {"status": "empty_curve", "h": h}
        base[h] = c

    descriptive: Dict[str, Any] = {}
    monthly: Dict[int, Dict[str, Dict[int, float]]] = {}
    for h in GRID_H:
        c = base[h]
        d = c["days"]
        monthly[h] = {k: _monthly(d, c[k]) for k in ("L0", "L1", "L2")}
        bench = _bench_daily(d, kospi)
        monthly[h]["excess_L0"] = _monthly(d, [x - y for x, y in zip(c["L0"], bench)])
        for k in ("L0", "L1", "L2"):
            descriptive[f"{k}_H{h}"] = {
                **kp._metrics(c[k], d), **c["meta"],
                "monthly_mean_pct": round(st.mean(monthly[h][k].values()) * 100, 4),
                "total_pct": round((math.prod(1 + x for x in c[k]) - 1) * 100, 2),
                "realized_beta": _realized_beta(d, c[k], kospi),
            }

    # ── 원장 6검정 (§2) ──
    results: Dict[str, Any] = {}
    keys: List[str] = []
    for h in GRID_H:
        lag = 1 if h <= 20 else 3
        for nm, m in (("L1_vs_zero", monthly[h]["L1"]), ("L2_vs_zero", monthly[h]["L2"])):
            key = f"{nm}_{h}d"
            keys.append(key)
            results[key] = _test(m, lag)
        key = f"L2_minus_L1_{h}d"
        keys.append(key)
        a, b = monthly[h]["L2"], monthly[h]["L1"]
        kk = sorted(set(a) & set(b))
        results[key] = _test({x: a[x] - b[x] for x in kk}, lag)
    pv = [two_sided_p(results[k]["nw"].get("t"), results[k]["nw"].get("n")) for k in keys]
    for k, p_, ok in zip(keys, pv, bh_fdr(pv, q=0.05)):
        results[k]["p_two_sided"] = round(p_, 6) if p_ is not None else None
        results[k]["passes_bh_fdr"] = ok
        results[k]["passes_t3"] = bool(results[k]["nw"].get("t") is not None
                                       and abs(results[k]["nw"]["t"]) >= ADOPT_T)

    # ── 진단 (§3) ──
    gate = {}
    for h in GRID_H:
        got = round(st.mean(monthly[h]["excess_L0"].values()) * 100, 4)
        gate[f"H{h}"] = {"expected": GATE[h], "got": got, "diff": round(got - GATE[h], 4),
                         "pass": bool(abs(got - GATE[h]) <= GATE_TOL)}
    gate["all_pass"] = all(v["pass"] for k, v in gate.items() if k.startswith("H"))

    # §3-4 공매도 제도 구간 분해 — L2 의 유일한 실행 가능 증거
    regime: Dict[str, Any] = {}
    for h in GRID_H:
        c = base[h]
        buckets: Dict[str, List[float]] = {"free": [], "partial": [], "banned": []}
        bd: Dict[str, List[int]] = {"free": [], "partial": [], "banned": []}
        for d, v in zip(c["days"], c["L2"]):
            g = _regime(d)
            buckets[g].append(v)
            bd[g].append(d)
        regime[f"H{h}"] = {
            g: {"days": len(v),
                "share_pct": round(len(v) / len(c["days"]) * 100, 1),
                "monthly_mean_pct": (round(st.mean(_monthly(bd[g], v).values()) * 100, 4)
                                     if v else None),
                "total_pct": round((math.prod(1 + x for x in v) - 1) * 100, 2) if v else None}
            for g, v in buckets.items()}

    # §3-5 대주 수수료 민감도
    sens: Dict[str, Any] = {}
    for r in BORROW_RATES:
        if abs(r - BORROW_PRIMARY) < 1e-9:
            sens[f"borrow_{r * 100:.1f}pct"] = {
                f"H{h}": descriptive[f"L2_H{h}"]["monthly_mean_pct"] for h in GRID_H}
            continue
        row = {}
        for h in GRID_H:
            c = curves(snaps, px, cal, gone, kospi, h, borrow=r)
            row[f"H{h}"] = round(st.mean(_monthly(c["days"], c["L2"]).values()) * 100, 4)
        sens[f"borrow_{r * 100:.1f}pct"] = row

    # §3-6 인버스 ETF 근사 오차 — 일간 복리 드래그
    drag = {}
    for h in GRID_H:
        d = base[h]["days"]
        b = _bench_daily(d, kospi)
        inv = math.prod(1 - x for x in b) - 1          # 일간 −1배 복리
        direct = -(math.prod(1 + x for x in b) - 1)    # 단순 부호 반전
        drag[f"H{h}"] = {"daily_inverse_total_pct": round(inv * 100, 2),
                         "naive_negated_total_pct": round(direct * 100, 2),
                         "compounding_drag_pct_p": round((inv - direct) * 100, 2)}

    verdict: Dict[str, Any] = {}
    for h in GRID_H:
        r = results[f"L1_vs_zero_{h}d"]
        rb = descriptive[f"L1_H{h}"]["realized_beta"]
        cond = {
            "bh": bool(r.get("passes_bh_fdr")),
            "t3": bool(r.get("passes_t3")),
            "both_halves_positive": bool(r["split"]["H1"]["positive"]
                                         and r["split"]["H2"]["positive"]),
            "residual_beta_ok": bool(rb is not None and abs(rb) <= RESID_BETA_MAX),
        }
        cond["all_pass"] = all(cond.values())
        verdict[f"L1_H{h}"] = cond
    verdict["adopted"] = [k for k, v in verdict.items()
                          if isinstance(v, dict) and v.get("all_pass")]
    verdict["rule"] = ("전원 미충족 = '시장 노출 제거로는 해결되지 않는다' 기록. "
                       "남는 것은 산식 조정이 아니라 N 축적(2027-05 게이트) (§4)")

    doc = {
        "_meta": {
            "prereg": "docs/PREREG_MARKET_NEUTRAL_2026_08_15.md",
            "approved": "PM 2026-08-15 'ㄱㄱ' (§6 4건)",
            "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00",
                                         time.localtime(time.time() + 9 * 3600)),
            "tests": len(keys), "adopt_t": ADOPT_T, "bonferroni": BONF6,
            "dsr_m_trials": M_TRIALS, "n_hold": N_HOLD,
            "candidates": {
                "L0": "롱온리 (#370 S0)",
                "L1": f"L0 + 인버스 ETF · 헤지비율=PIT 트레일링 베타(창 h) · 보수 {INVERSE_FEE_ANNUAL*100}%/년",
                "L2": f"상위{N_HOLD} 롱 {SIDE_W*100:.0f}% / 하위{N_HOLD} 숏 {SIDE_W*100:.0f}% (자본 100% 통일)"},
            "known_before_run": ("알파 t 1.51(S0)/2.05(S1) 로 임계 미달 · 잔차 반쪽 부호 뒤집힘. "
                                 "§4-③ 반쪽 요건을 완화하지 않는다"),
            "short_regime": "개별종목 숏 자유 구간 21.0% — L2 는 반사실, free 하위표본만 참조",
            "hedge_beta_clamp": "[0, 1.5] — 등록 후 추가한 가드(음수 헤지·과잉 레버리지 배제)",
            "borrow_rate_unverified": "🚨 개인 대주 수수료 공표치 미확보 — 3점 민감도로 대체",
            "approximations": ["인버스 ETF = 일간 −1×KOSPI (실제는 KOSPI200 선물 추종, 추적오차 있음)",
                               "partial 구간은 K200/KQ150 구성종목 부재로 제약 미적용",
                               "숏 상폐 = 롱 haircut(−30%)의 부호 반전이라 +30% 로 계상 — 실제 −100%(=숏 +100%)보다 과소, 숏에 보수적"],
            "scope": "이 등록으로 운영을 바꾸지 않는다 (§4)",
        },
        "coverage": {"snapshots": len(snaps),
                     "window": [snaps[0]["as_of"], snaps[-1]["as_of"]],
                     "elapsed_sec": round(time.time() - t0, 1)},
        "descriptive": descriptive,
        "results": results,
        "diagnostics": {"reproduction_gate": gate, "short_regime_split": regime,
                        "borrow_sensitivity": sens, "inverse_etf_drag": drag},
        "verdict": verdict,
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
        print(f"[mn] {r['status']} {r}", file=sys.stderr)
        return 1
    c, g = r["coverage"], r["diagnostics"]["reproduction_gate"]
    print(f"\n[mn] 단면 {c['snapshots']} · {c['window'][0]}~{c['window'][1]} · {c['elapsed_sec']}s")
    print(f"\n재현 게이트 — {'통과' if g['all_pass'] else '실패'}")
    for h in GRID_H:
        v = g[f"H{h}"]
        print(f"    H{h}: 기대 {v['expected']} · 실측 {v['got']} · 차 {v['diff']:+.4f} "
              f"→ {'OK' if v['pass'] else 'FAIL'}")
    print(f"\n{'구성':9}{'CAGR%':>8}{'MDD':>8}{'Calmar':>8}{'Sharpe':>8}{'월평균%':>9}"
          f"{'실현베타':>9}")
    for k in ("L0", "L1", "L2"):
        for h in GRID_H:
            d = r["descriptive"][f"{k}_H{h}"]
            print(f"{k}_H{h:<6}{(d.get('cagr_pct') or 0):>8.2f}{(d.get('mdd') or 0):>8.3f}"
                  f"{(d.get('calmar') or 0):>8.3f}{(d.get('sharpe') or 0):>8.2f}"
                  f"{d['monthly_mean_pct']:>9.4f}{(d.get('realized_beta') or 0):>9.3f}")
    m = r["descriptive"]["L1_H20"]
    print(f"\n헤지 베타(PIT): 평균 {m['hedge_beta_mean']} · 범위 {m['hedge_beta_min']}~{m['hedge_beta_max']}")
    print(f"\n{'검정':22}{'평균%':>9}{'t':>7}{'p':>8}{'BH':>5}{'t≥3':>5}   H1→H2 · CI")
    for k, v in r["results"].items():
        s = v["split"]
        ci = v.get("ci95_pct")
        print(f"{k:22}{(v.get('mean_pct') or 0):>9.4f}{(v['nw'].get('t') or 0):>7.2f}"
              f"{(v.get('p_two_sided') if v.get('p_two_sided') is not None else float('nan')):>8.4f}"
              f"{('통과' if v.get('passes_bh_fdr') else '—'):>5}"
              f"{('O' if v.get('passes_t3') else '—'):>5}   "
              f"{s['H1']['mean_pct']}→{s['H2']['mean_pct']}"
              + (f" · [{ci[0]}, {ci[1]}]" if ci else ""))
    d = r["diagnostics"]
    print("\n[진단4] 🚨 공매도 제도 구간별 L2 (free 만이 실행 가능 증거)")
    for h in GRID_H:
        for gname, v in d["short_regime_split"][f"H{h}"].items():
            print(f"  H{h} {gname:8} {v['share_pct']:>5}% · 월평균 {v['monthly_mean_pct']} · 총 {v['total_pct']}%")
    print(f"\n[진단5] 대주 수수료 민감도: {d['borrow_sensitivity']}")
    print(f"[진단6] 인버스 복리 드래그: {d['inverse_etf_drag']}")
    print("\n[§4 판정]")
    for k, v in r["verdict"].items():
        if isinstance(v, dict):
            print(f"  {k}: {v}")
    print(f"  채택: {r['verdict']['adopted'] or '없음'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
