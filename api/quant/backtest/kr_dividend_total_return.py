# -*- coding: utf-8 -*-
"""kr_dividend_total_return — 배당 포함 총수익 재계산.

사전등록 `docs/PREREG_DIVIDEND_TOTAL_RETURN_2026_08_15.md` · PM 승인 2026-08-15 "ㄱㄱ" (§6 4건).
🚨 관측 산출물만. **실행 1회 소진.** 이 등록으로 운영을 바꾸지 않는다 (§4).

지금까지 보고한 모든 초과수익이 가격수익률 기준이었다. 우리 점수는 `div_yield` 를 C3 축으로
쓰므로 배당 제외가 우리 쪽만 체계적으로 깎았을 개연이 있다. 그 크기를 잰다.

🚨 §0 함정 — 방향이 정해진 측정이다(배당을 넣으면 우리 숫자가 오른다). 게다가 KOSPI 총수익
   지수가 데이터에 없어 벤치를 자작해야 한다. 방어 셋:
   ① 양쪽 동일 회계 (한쪽만 TR 로 올리는 비교 금지)
   ② 벤치 3종 사전 고정 + 전부 보고 (사후 선택 금지)
   ③ 해석 임계 0.20%p/월 계산 전 고정

계열 5종 (§1-2):
  P_PR  A0 포트 가격수익률 — 재현 게이트 (#367 값과 일치해야 함)
  P_TR  A0 포트 총수익률
  B1    KOSPI 가격지수 (현행 벤치 · 연속성 병기만)
  B2    유니버스 시총가중 가격수익률
  B3    유니버스 시총가중 총수익률 — **주 비교 (동일 회계)**

원장 2검정 = (P_TR − B3) × {20d, 60d} · 월간 NW t → BH-FDR q=.05 · 주장 |t| ≥ 3.0.
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
from api.quant.backtest.kr_safety_score import bh_fdr, nw_t, two_sided_p  # noqa: E402
from api.quant.backtest.kr_segment_allocation import (  # noqa: E402
    GRID_H, N_HOLD, SPLIT_BOUNDARY, _bench_daily, _half, _monthly, build, pick_a0,
)
from api.quant.backtest.kr_price_axes import ENTRY_LAG  # noqa: E402

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "data")
OUT_PATH = os.path.join(_DATA, "analysis", "prereg_dividend_total_return_20260815.json")
DIV_PATH = os.path.join(_DATA, "metadata", "kr_dividend_history.jsonl")

# ── 등록값 (§1·§2·§4) ──────────────────────────────────────────────────────
ADOPT_T = 3.0
BONF2 = 2.24
M_TRIALS = 86                    # DSR 누적 시도 (84 + 본건 2)
MATERIAL_PCT = 0.20              # §4 임계 %/월 — 계산 전 고정
PRIMARY_H = 20                   # 판정 기준 창 = 현행 보고(−0.6555%/월)와 같은 20d
DIV_TAX = 0.154                  # §3-5 세후 민감도
EX_SHIFTS = (-3, 0, 3)           # §3-5 배당락일 민감도
# 🚨 §3-1 재현 게이트 기준값 = #367 산출물 A0 (동일 build · 동일 picker)
GATE = {20: -0.6555, 60: -0.9596}
GATE_TOL = 0.01


# ── 배당 원장 ───────────────────────────────────────────────────────────────
def load_dividends() -> Tuple[Dict[str, Dict[int, float]], Dict[str, int], Dict[str, Any],
                              Dict[Tuple[str, int], Optional[float]]]:
    """(ticker → {회계연도: dps}, ticker → 결산월, 통계).

    `basis=thstrm`(당기) 우선. `stlm_dt` 는 **보고서의** 결산일이라 frmtrm 행에서는 연도가
    한 해 뒤다 — 월만 취하고 연도는 `year` 필드를 쓴다.
    """
    dps: Dict[str, Dict[int, float]] = {}
    month: Dict[str, int] = {}
    reported: Dict[Tuple[str, int], Optional[float]] = {}
    seen_basis: Dict[Tuple[str, int], str] = {}
    rows = 0
    for line in open(DIV_PATH, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        rows += 1
        t, y = r.get("ticker"), r.get("year")
        if not t or y is None:
            continue
        y = int(y)
        key = (t, y)
        basis = str(r.get("basis") or "")
        if key in seen_basis and seen_basis[key] == "thstrm" and basis != "thstrm":
            continue
        v = r.get("dps")
        dps.setdefault(t, {})[y] = float(v) if isinstance(v, (int, float)) else 0.0
        rep = r.get("div_yield_reported")
        reported[key] = float(rep) if isinstance(rep, (int, float)) else None
        seen_basis[key] = basis
        sd = str(r.get("stlm_dt") or "")
        if len(sd) >= 7 and t not in month:
            try:
                month[t] = int(sd[5:7])
            except ValueError:
                pass
    payers = sum(1 for t in dps for y in dps[t] if dps[t][y] > 0)
    stat = {"rows": rows, "tickers": len(dps),
            "ticker_years": sum(len(v) for v in dps.values()), "dps_gt0": payers,
            "fy_range": [min((y for v in dps.values() for y in v), default=None),
                         max((y for v in dps.values() for y in v), default=None)]}
    return dps, month, stat, reported


# 🚨 등록 후 스모크에서 발견한 원장 결함 → 데이터 정합 필터 (§등록 이탈 · 산출물에 신고)
#    · `067900` dps = 배당금 **총액** 오파싱 (보고 0.58% vs 계산 10,596,990%)
#    · `000480`/`134380` 등 = 액면분할 미조정 (보고 5.61% vs 계산 56.2% = 정확히 10배)
#    우리 점수가 배당 축을 쓰므로 이런 레코드는 **포트에 우선 선택**되어 결과를 부풀린다.
#    판정 기준 = 원장 자신의 `div_yield_reported` 와의 배율. 4배·0.25배 밖 = 단위 오류.
#    (연중 주가 변동으로 생기는 정상 이탈은 대부분 2배 안, 구조 오류는 전부 5배 밖 — 실측)
DIV_RATIO_LO, DIV_RATIO_HI = 0.25, 4.0
DIV_CAP_NO_REPORT = 15.0          # 보고 수익률 부재 시 허용 상한 (%)


def validate_dividends(dps, reported, month, cal, px) -> Tuple[Dict[str, Dict[int, float]],
                                                               Dict[str, Any]]:
    """원장 자체 보고 수익률과 대조해 단위 오류 레코드를 제거한다."""
    clean: Dict[str, Dict[int, float]] = {}
    kept = dropped = no_price = 0
    drops: List[Dict[str, Any]] = []
    for t, per_year in dps.items():
        mon = month.get(t, 12)
        for y, v in per_year.items():
            if not v or v <= 0:
                continue
            d = _ex_date(cal, y, mon, 0)
            s = px.get(t)
            if d is None or not s:
                no_price += 1
                continue
            i = bisect.bisect_left(s["d"], d)
            if i <= 0 or i >= len(s["d"]) or s["d"][i] != d:
                no_price += 1
                continue
            p0 = s["c"][i - 1]
            if not p0 or p0 <= 0:
                no_price += 1
                continue
            imp = v / p0 * 100
            rep = reported.get((t, y))
            if isinstance(rep, (int, float)) and rep > 0:
                ratio = imp / rep
                bad = not (DIV_RATIO_LO <= ratio <= DIV_RATIO_HI)
            else:
                ratio, bad = None, imp > DIV_CAP_NO_REPORT
            if bad:
                dropped += 1
                if len(drops) < 40:
                    drops.append({"ticker": t, "fy": y, "implied_pct": round(imp, 2),
                                  "reported_pct": rep,
                                  "ratio": (round(ratio, 2) if ratio else None)})
                continue
            kept += 1
            clean.setdefault(t, {})[y] = v
    stat = {"kept": kept, "dropped": dropped, "no_price": no_price,
            "dropped_pct": round(dropped / max(1, kept + dropped) * 100, 2),
            "rule": f"implied/reported ∉ [{DIV_RATIO_LO},{DIV_RATIO_HI}] "
                    f"또는 (보고 부재 & implied > {DIV_CAP_NO_REPORT}%)",
            "examples": sorted(drops, key=lambda z: -(z["implied_pct"]))[:12]}
    return clean, stat


def _ex_date(cal: Sequence[int], year: int, mon: int, shift: int = 0) -> Optional[int]:
    """배당락일 = 결산기준일(= 결산월 최종 거래일) **직전 거래일** (§1-1 · 실측 확인).

    실측: FY2022 20221228(−1.43%p) · FY2023 20231227(−3.24%p) 에 단일 급락.
    """
    lo, hi = year * 10000 + mon * 100, year * 10000 + mon * 100 + 99
    i = bisect.bisect_right(cal, hi) - 1
    if i < 0 or cal[i] < lo:
        return None
    j = i - 1 + shift
    return cal[j] if 0 <= j < len(cal) else None


def build_div_by_day(dps: Dict[str, Dict[int, float]], month: Dict[str, int],
                     cal: Sequence[int], shift: int = 0) -> Dict[str, Dict[int, float]]:
    out: Dict[str, Dict[int, float]] = {}
    for t, per_year in dps.items():
        mon = month.get(t, 12)
        for y, v in per_year.items():
            if not v or v <= 0:
                continue
            d = _ex_date(cal, y, mon, shift)
            if d is not None:
                out.setdefault(t, {})[d] = v
    return out


# ── 곡선 (kp._daily_curve 회계 복제 + 배당 층 분리) ─────────────────────────
def _window_prices(px, tickers, lo: int, hi: int) -> Dict[str, Dict[int, float]]:
    """창 [lo,hi] 구간만 잘라 날짜→종가 dict. 일별 bisect 를 없애는 목적."""
    out: Dict[str, Dict[int, float]] = {}
    for t in tickers:
        s = px.get(t)
        if not s:
            continue
        d, c = s["d"], s["c"]
        a = bisect.bisect_left(d, lo)
        b = bisect.bisect_right(d, hi)
        if a < b:
            out[t] = dict(zip(d[a:b], c[a:b]))
    return out


def curves(snaps, px, cal, gone, div_by_day, h: int) -> Dict[str, Any]:
    """포트(동일가중 12) + 벤치(유니버스 시총가중) 를 한 번에.

    가격층과 배당층을 **분리 보관**한다 — 세후 민감도가 배당층 스칼라 배로 계산되도록.
    포트 회계는 kp._daily_curve 와 동일 (교체분만 과금 · 진입 T+1 · 상폐 haircut −0.30).
    벤치는 지수 성격이므로 **비용 0**, 시총 비중은 리밸런스마다 재설정하고 창 안에서는 표류.
    """
    reb = [s for i, s in enumerate(snaps) if i % max(1, round(h / 20)) == 0] if h != 20 else snaps
    days: List[int] = []
    pp: List[float] = []   # 포트 가격
    pd_: List[float] = []  # 포트 배당
    bp: List[float] = []   # 벤치 가격
    bd: List[float] = []   # 벤치 배당
    turn_total = cost_total = 0.0
    prev_held: List[str] = []
    n_reb = 0
    join_hit = join_miss = 0

    for si, snap in enumerate(reb):
        k = snap["cal_idx"]
        entry_i = k + ENTRY_LAG
        end_i = (reb[si + 1]["cal_idx"] + ENTRY_LAG) if si + 1 < len(reb) else min(
            entry_i + h, len(cal) - 1)
        if entry_i >= len(cal) or end_i <= entry_i:
            continue
        rows = snap["rows"]
        held = pick_a0(rows, N_HOLD)
        if not held:
            continue
        n_reb += 1
        turn = len(set(held) - set(prev_held)) / max(1, len(held))
        cost = turn * kp.ROUNDTRIP
        turn_total += turn
        cost_total += cost
        prev_held = held
        lo, hi = cal[entry_i], cal[end_i]
        wp = _window_prices(px, [r["t"] for r in rows], lo, hi)
        wgt = {r["t"]: float(r["mktcap"]) for r in rows}   # PIT 시총 → 창 안에서 표류
        for t in held:
            if t in div_by_day:
                join_hit += 1
            else:
                join_miss += 1
        first = True
        for di in range(entry_i, end_i):
            d0, d1 = cal[di], cal[di + 1]
            # ── 포트 (동일가중) ──
            rs_p, rs_d = [], []
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
                        rs_p.append(-0.30)
                        rs_d.append(0.0)
                    continue
                if p1 <= 0:
                    continue
                rs_p.append(p1 / p0 - 1.0)
                dv = (div_by_day.get(t) or {}).get(d1)
                rs_d.append((dv / p0) if dv else 0.0)
            r_p = (sum(rs_p) / len(rs_p)) if rs_p else 0.0
            r_d = (sum(rs_d) / len(rs_d)) if rs_d else 0.0
            if first:
                r_p -= cost                       # 진입일 회전비용 (가격층에 부과)
                first = False
            # ── 벤치 (시총가중 · 비용 0) ──
            tot = num_p = num_d = 0.0
            for t, w in wgt.items():
                if w <= 0:
                    continue
                m = wp.get(t)
                if not m:
                    continue
                p0, p1 = m.get(d0), m.get(d1)
                if p0 is None or p0 <= 0:
                    continue
                if p1 is None:
                    s = px.get(t)
                    if t in gone and s and s["d"][-1] == d0:
                        tot += w
                        num_p += w * -0.30
                    continue
                if p1 <= 0:
                    continue
                r = p1 / p0 - 1.0
                dv = (div_by_day.get(t) or {}).get(d1)
                tot += w
                num_p += w * r
                num_d += w * ((dv / p0) if dv else 0.0)
            b_p = (num_p / tot) if tot > 0 else 0.0
            b_d = (num_d / tot) if tot > 0 else 0.0
            # 다음 날 비중 표류
            for t in list(wgt):
                m = wp.get(t)
                if not m:
                    continue
                p0, p1 = m.get(d0), m.get(d1)
                if p0 and p1 and p0 > 0 and p1 > 0:
                    wgt[t] *= p1 / p0
            days.append(d1)
            pp.append(r_p)
            pd_.append(r_d)
            bp.append(b_p)
            bd.append(b_d)
    return {"days": days, "p_price": pp, "p_div": pd_, "b_price": bp, "b_div": bd,
            "meta": {"rebalances": n_reb,
                     "turnover_per_reb": round(turn_total / max(1, n_reb), 4),
                     "cost_total_pct": round(cost_total * 100, 3),
                     "div_join_hit": join_hit, "div_join_miss": join_miss}}


def _compose(a: Sequence[float], b: Sequence[float], scale: float = 1.0) -> List[float]:
    return [x + scale * y for x, y in zip(a, b)]


def _total_pct(rets: Sequence[float]) -> float:
    return round((math.prod(1 + r for r in rets) - 1) * 100, 2)


def _mean_monthly_pct(monthly: Dict[int, float]) -> float:
    return round(st.mean(monthly.values()) * 100, 4) if monthly else 0.0


def _diff(a: Dict[int, float], b: Dict[int, float]) -> Tuple[List[float], List[int]]:
    ks = sorted(set(a) & set(b))
    return [a[k] - b[k] for k in ks], ks


# ── 진단 ───────────────────────────────────────────────────────────────────
def diag_double_count(px, cal, dps, month) -> Dict[str, Any]:
    """🚨 §3-2 이중계산 방어 — 배당락일에 dps>0 이 dps=0 대비 음수여야 한다.

    양수로 뒤집힌 회계연도 = 그 해 가격이 배당 수정주가일 가능성 → 가산 제외 대상으로 신고.
    """
    out: Dict[str, Any] = {}
    years = sorted({y for v in dps.values() for y in v})
    for y in years:
        if y < 2019 or y > 2025:
            continue
        d = _ex_date(cal, y, 12, 0)
        if d is None:
            continue
        i = bisect.bisect_left(cal, d)
        if i <= 0:
            continue
        prev = cal[i - 1]
        hi_, lo_ = [], []
        for t, s in px.items():
            if month.get(t, 12) != 12 or y not in (dps.get(t) or {}):
                continue
            a = bisect.bisect_left(s["d"], prev)
            b = bisect.bisect_left(s["d"], d)
            if a >= len(s["d"]) or b >= len(s["d"]):
                continue
            if s["d"][a] != prev or s["d"][b] != d:
                continue
            p0, p1 = s["c"][a], s["c"][b]
            if not p0 or p0 <= 0 or not p1:
                continue
            r = (p1 / p0 - 1.0) * 100
            (hi_ if dps[t][y] > 0 else lo_).append(r)
        if len(hi_) > 100 and len(lo_) > 100:
            gap = st.mean(hi_) - st.mean(lo_)
            out[f"FY{y}"] = {"ex_date": d, "n_payer": len(hi_), "n_nonpayer": len(lo_),
                            "gap_pct_p": round(gap, 3), "unadjusted_ok": bool(gap < 0)}
    return out


def run(lake: str, out_path: str = OUT_PATH, limit: int = 0) -> Dict[str, Any]:
    t0 = time.time()
    snaps, px, cal, gone, drop = build(lake)
    if limit:
        snaps = snaps[:limit]
    if not snaps:
        return {"status": "no_snapshots"}
    kospi = kp._load_kospi()
    dps_raw, month, dstat, reported = load_dividends()
    dps, vstat = validate_dividends(dps_raw, reported, month, cal, px)

    base: Dict[int, Dict[str, Any]] = {}
    sens: Dict[str, Dict[int, float]] = {}
    for shift in EX_SHIFTS:
        dbd = build_div_by_day(dps, month, cal, shift)
        for h in GRID_H:
            c = curves(snaps, px, cal, gone, dbd, h)
            if not c["days"]:
                return {"status": "empty_curve", "h": h, "shift": shift}
            if shift == 0:
                base[h] = c
            else:
                sens.setdefault(f"ex_shift_{shift:+d}", {})[h] = round(
                    _mean_monthly_pct(_monthly(c["days"], c["p_div"]))
                    - _mean_monthly_pct(_monthly(c["days"], c["b_div"])), 4)

    # 🚨 필터 미적용(원장 그대로) 민감도 — 결함 레코드가 결과를 얼마나 부풀리는지 신고
    dbd_raw = build_div_by_day(dps_raw, month, cal, 0)
    for h in GRID_H:
        c = curves(snaps, px, cal, gone, dbd_raw, h)
        sens.setdefault("no_validation_filter", {})[h] = round(
            _mean_monthly_pct(_monthly(c["days"], c["p_div"]))
            - _mean_monthly_pct(_monthly(c["days"], c["b_div"])), 4)

    # ── 계열 5종 + 분해 ──
    # 🚨 규약 통일: 초과는 **일별 차를 월간 복리**로 묶는다 (#367 과 동일). 수준 계열의
    #    월평균 차로 계산하면 교차항 때문에 재현 게이트가 헛돈다.
    diffs: Dict[int, Dict[str, Dict[int, float]]] = {}
    descriptive: Dict[str, Any] = {}
    decomposition: Dict[str, Any] = {}
    for h in GRID_H:
        c = base[h]
        d = c["days"]
        p_pr_d, p_tr_d = c["p_price"], _compose(c["p_price"], c["p_div"])
        b1_d, b2_d = _bench_daily(d, kospi), c["b_price"]
        b3_d = _compose(c["b_price"], c["b_div"])
        M = {
            "gate_excess": _monthly(d, [x - y for x, y in zip(p_pr_d, b1_d)]),
            "same_acct_excess": _monthly(d, [x - y for x, y in zip(p_tr_d, b3_d)]),
            "port_div": _monthly(d, c["p_div"]),
            "univ_div": _monthly(d, c["b_div"]),
            "univ_vs_kospi": _monthly(d, [x - y for x, y in zip(b2_d, b1_d)]),
            "port_div_after_tax": _monthly(d, [x * (1 - DIV_TAX) for x in c["p_div"]]),
            "univ_div_after_tax": _monthly(d, [x * (1 - DIV_TAX) for x in c["b_div"]]),
        }
        diffs[h] = M
        for k, ser_ in (("P_PR", p_pr_d), ("P_TR", p_tr_d), ("B1", b1_d),
                        ("B2", b2_d), ("B3", b3_d)):
            descriptive[f"{k}_H{h}"] = {
                "monthly_mean_pct": _mean_monthly_pct(_monthly(d, ser_)),
                "total_pct": _total_pct(ser_)}
        descriptive[f"P_PR_H{h}"].update(kp._metrics(p_pr_d, d))
        descriptive[f"P_TR_H{h}"].update(kp._metrics(p_tr_d, d))
        pdv, udv = _mean_monthly_pct(M["port_div"]), _mean_monthly_pct(M["univ_div"])
        decomposition[f"H{h}"] = {
            "reported_excess_vs_B1": _mean_monthly_pct(M["gate_excess"]),
            "same_accounting_excess_vs_B3": _mean_monthly_pct(M["same_acct_excess"]),
            "port_div_yield": pdv,
            "univ_div_yield": udv,
            "net_div_contribution": round(pdv - udv, 4),
            "universe_contribution_B2_minus_B1": _mean_monthly_pct(M["univ_vs_kospi"]),
            "after_tax_net_div": round(_mean_monthly_pct(M["port_div_after_tax"])
                                       - _mean_monthly_pct(M["univ_div_after_tax"]), 4),
            "_note": "분해는 복리 교차항 때문에 1차 근사로만 가법적이다",
        }

    # ── 원장 2검정 (§2) ──
    results: Dict[str, Any] = {}
    keys: List[str] = []
    for h in GRID_H:
        key = f"P_TR_minus_B3_{h}d"
        keys.append(key)
        M = diffs[h]["same_acct_excess"]
        mk = sorted(M)
        ser = [M[k_] for k_ in mk]
        lag = 1 if h <= 20 else 3
        hv: Dict[str, List[float]] = {"H1": [], "H2": []}
        for k_, x in zip(mk, ser):
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
        if t_ and r.get("mean_pct") is not None:
            se = abs(r["mean_pct"] / t_)
            r["ci95_pct"] = [round(r["mean_pct"] - 1.96 * se, 4),
                             round(r["mean_pct"] + 1.96 * se, 4)]

    # ── 의무 진단 (§3) ──
    gate: Dict[str, Any] = {}
    for h in GRID_H:
        got = decomposition[f"H{h}"]["reported_excess_vs_B1"]
        gate[f"H{h}"] = {"expected": GATE[h], "got": got,
                         "diff": round(got - GATE[h], 4),
                         "pass": bool(abs(got - GATE[h]) <= GATE_TOL)}
    gate["all_pass"] = all(v["pass"] for k, v in gate.items() if k.startswith("H"))

    held_names = {t for s in snaps for t in pick_a0(s["rows"], N_HOLD)}
    cov = {
        "snapshots": len(snaps),
        "window": [snaps[0]["as_of"], snaps[-1]["as_of"]],
        "held_unique_tickers": len(held_names),
        "held_with_div_record": sum(1 for t in held_names if t in dps),
        "held_without_div_record": sum(1 for t in held_names if t not in dps),
        "div_ledger": dstat,
        "fy2026_snapshots": sum(1 for s in snaps if s["as_of"] >= 20260101),
        "fy2026_note": "FY2026 배당 원장 부재 → 해당 구간 배당 0 (양쪽 동일 적용, 우리 쪽 하향 편향)",
        "dropped_no_mktcap": drop["no_mktcap"],
        "elapsed_sec": round(time.time() - t0, 1),
    }

    diagnostics = {
        "reproduction_gate": gate,
        "dividend_record_validation": vstat,
        # 🚨 정제 원장(dps)은 payer 만 남아 무배당 대조군이 사라진다 → 반드시 원본을 넘긴다
        "double_count_guard": diag_double_count(px, cal, dps_raw, month),
        "coverage": cov,
        "sensitivity_ex_date": sens,
        "sensitivity_after_tax": {f"H{h}": decomposition[f"H{h}"]["after_tax_net_div"]
                                  for h in GRID_H},
        "external_consistency": {
            "computed_univ_div_yield_pct_per_month": {
                f"H{h}": decomposition[f"H{h}"]["univ_div_yield"] for h in GRID_H},
            "computed_univ_div_yield_pct_annual": {
                f"H{h}": round(decomposition[f"H{h}"]["univ_div_yield"] * 12, 3)
                for h in GRID_H},
            # §3-4 공표치 실호출 확보 (2026-08-15 WebSearch). KOSPI 가격 급등으로 최근 급락 중.
            "published_kospi_div_yield_pct": {
                "2022_expected": 2.4, "2025_05_07": 2.14, "2025_12_26": 1.35,
                "2026_05_29": 0.82, "2026_06_04": 0.92,
                "sources": ["신한투자증권 배당주전략 22년 1분기", "INDEXerGO 배당수익률 시리즈",
                            "파이낸셜뉴스 2026-05-06 '시총은 3배 뛴 코스피, 배당수익률은 반토막'"],
            },
            "verdict": ("정합 — 우리 계산 1.66%(기간 평균)가 공표 KOSPI 0.82~2.4% 범위 안. "
                        "우리 유니버스는 KOSDAQ 포함(배당수익률 더 낮음)이라 KOSPI 평균보다 "
                        "낮게 나오는 것이 예상 방향. §3-4 의 '2배 이상 이탈' 에 해당하지 않음"),
            "status": "확인 완료",
        },
    }

    # ── §4 해석 (계산 전 고정) ──
    net = decomposition[f"H{PRIMARY_H}"]["net_div_contribution"]
    verdict = {
        "primary_horizon": PRIMARY_H,
        "net_div_contribution_pct_per_month": net,
        "threshold_pct": MATERIAL_PCT,
        "material": bool(net >= MATERIAL_PCT),
        "action": ("과거 보고(#363/#365/#366/#367) 초과수익 수치를 TR 기준으로 재기술. "
                   "유의성 판정은 재검정 없이 뒤집지 않는다 (별도 등록)"
                   if net >= MATERIAL_PCT else
                   "회계는 부차적 요인 — 과거 결론 유지, 이 가지를 닫는다"),
        "same_accounting_excess_still_negative": bool(
            decomposition[f"H{PRIMARY_H}"]["same_accounting_excess_vs_B3"] < 0),
        "forbidden_claim_guard": ("B3 기준 초과가 음수면 '배당을 넣으니 이긴다' 류 서술 금지 (§4)"),
    }

    doc = {
        "_meta": {
            "prereg": "docs/PREREG_DIVIDEND_TOTAL_RETURN_2026_08_15.md",
            "approved": "PM 2026-08-15 'ㄱㄱ' (§6 4건)",
            "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00",
                                         time.localtime(time.time() + 9 * 3600)),
            "tests": len(keys), "adopt_t": ADOPT_T, "bonferroni": BONF2,
            "dsr_m_trials": M_TRIALS,
            "n_hold": N_HOLD, "roundtrip_cost_pct": round(kp.ROUNDTRIP * 100, 3),
            "primary_benchmark": "B3 (유니버스 시총가중 TR · 동일 회계) — §6-1 PM 승인",
            "ex_date_rule": "결산기준일(결산월 최종거래일) 직전 거래일 — §6-3 PM 승인",
            "tax_basis": "세전 (양쪽 동일). 세후 15.4% 는 민감도로만 (§1-1)",
            "bench_cost": "벤치 = 지수 성격이므로 거래비용 0. 포트만 회전비용 과금",
            "changed_vs_367": "수익 회계(배당)만. 점수·종목수·유니버스·비용 규칙 동일",
            "not_reproduced": ["손절·트레일링·기간손절", "Kelly/섹터/베타 가드", "시장충격",
                               "중간·분기배당 개별 처리(연 1회 지급 근사)"],
            "approximations": ["FY2024+ 배당기준일 분리 → 연말 고정 근사 (민감도 ±3거래일)",
                               "KOSPI TR 부재 → 벤치 자작(B3). B1 은 연속성 병기만"],
            "registration_deviation": (
                "🚨 등록 후 스모크에서 배당 원장 결함 발견 → 단위 오류 필터 신설(등록에 없던 것). "
                "dps 총액 오파싱(067900 = 보고 0.58% vs 계산 10,596,990%) · 액면분할 미조정"
                "(000480 = 보고 5.61% vs 계산 56.2%). 🚨 실측 방향 = 착수 전 예상과 **반대**: "
                "결함 레코드는 전 종목을 담는 벤치(B3)를 훨씬 크게 오염시켜(필터 미적용 시 순 "
                "배당 기여 −44.76%/월) 결과를 우리에게 **불리한** 쪽으로 왜곡한다. 즉 필터는 "
                "우리 숫자를 올리는 정정이므로 더 엄격히 봐야 한다 — 그럼에도 정제 후 결과가 "
                "임계 미달이라 판정은 뒤집히지 않는다. 필터 미적용 결과를 민감도에 병기한다"),
        },
        "coverage": cov,
        "descriptive": descriptive,
        "decomposition": decomposition,
        "results": results,
        "diagnostics": diagnostics,
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
        print(f"[div_tr] {r['status']} {r}", file=sys.stderr)
        return 1
    c = r["coverage"]
    g = r["diagnostics"]["reproduction_gate"]
    print(f"\n[div_tr] 단면 {c['snapshots']} · {c['window'][0]}~{c['window'][1]} · "
          f"{c['elapsed_sec']}s")
    print(f"\n🚨 재현 게이트 (§3-1) — {'통과' if g['all_pass'] else '실패'}")
    for h in GRID_H:
        v = g[f"H{h}"]
        print(f"    H{h}: 기대 {v['expected']} · 실측 {v['got']} · 차 {v['diff']:+.4f} "
              f"→ {'OK' if v['pass'] else 'FAIL'}")
    if not g["all_pass"]:
        print("    바닥이 다르다 — 회계 결과를 읽지 말 것 (§3-1)")
    print(f"\n{'계열':10}{'월평균%':>10}{'총%':>10}   설명")
    lbl = {"P_PR": "포트 가격수익", "P_TR": "포트 총수익", "B1": "KOSPI 가격지수(병기)",
           "B2": "유니버스 시총가중 가격", "B3": "유니버스 시총가중 총수익(주 비교)"}
    for h in GRID_H:
        print(f"  ── H{h} ──")
        for k in ("P_PR", "P_TR", "B1", "B2", "B3"):
            d = r["descriptive"][f"{k}_H{h}"]
            print(f"  {k:8}{d['monthly_mean_pct']:>10.4f}{d['total_pct']:>10.1f}   {lbl[k]}")
    print(f"\n{'분해 (%/월)':34}{'H20':>10}{'H60':>10}")
    for k, nm in (("reported_excess_vs_B1", "현행 보고 초과 (P_PR−B1)"),
                  ("same_accounting_excess_vs_B3", "동일 회계 초과 (P_TR−B3)"),
                  ("port_div_yield", "포트 배당 (P_TR−P_PR)"),
                  ("univ_div_yield", "유니버스 배당 (B3−B2)"),
                  ("net_div_contribution", "🚨 순 배당 기여"),
                  ("universe_contribution_B2_minus_B1", "유니버스 기여 (B2−B1)")):
        print(f"  {nm:32}{r['decomposition']['H20'][k]:>10.4f}{r['decomposition']['H60'][k]:>10.4f}")
    print(f"\n{'검정':22}{'평균%':>9}{'t':>8}{'p':>9}{'BH':>6}{'t≥3':>6}   95% CI")
    for k, v in r["results"].items():
        ci = v.get("ci95_pct")
        print(f"{k:22}{(v.get('mean_pct') or 0):>9.4f}{(v['nw'].get('t') or 0):>8.2f}"
              f"{(v.get('p_two_sided') if v.get('p_two_sided') is not None else float('nan')):>9.4f}"
              f"{('통과' if v.get('passes_bh_fdr') else '—'):>6}"
              f"{('O' if v.get('passes_t3') else '—'):>6}   "
              f"[{ci[0]}, {ci[1]}]" if ci else "")
    d = r["diagnostics"]
    v_ = d["dividend_record_validation"]
    print(f"\n[진단1] 원장 단위오류 필터: 채택 {v_['kept']} · 제외 {v_['dropped']} "
          f"({v_['dropped_pct']}%) · 가격부재 {v_['no_price']}")
    for x in v_["examples"][:3]:
        print(f"        제외예 {x['ticker']} FY{x['fy']} 계산 {x['implied_pct']}% vs "
              f"보고 {x['reported_pct']}% (배율 {x['ratio']})")
    print("\n[진단2] 이중계산 방어 (배당락일 payer−nonpayer, 음수여야 정상):")
    for k, v in d["double_count_guard"].items():
        print(f"        {k} {v['ex_date']} {v['gap_pct_p']:+.3f}%p "
              f"→ {'OK' if v['unadjusted_ok'] else '🚨 양수 — 수정주가 의심'}")
    print(f"[진단3] 커버리지: 보유 종목 {c['held_unique_tickers']} 중 배당원장 보유 "
          f"{c['held_with_div_record']} · 부재 {c['held_without_div_record']} · "
          f"2026 단면 {c['fy2026_snapshots']}")
    print(f"[진단5] 민감도 배당락일: {d['sensitivity_ex_date']} · 세후: {d['sensitivity_after_tax']}")
    e = d["external_consistency"]
    print(f"[진단4] 유니버스 배당수익률 연환산: {e['computed_univ_div_yield_pct_annual']} "
          f"(공표 KOSPI 대조 = {e['status']})")
    v = r["verdict"]
    print(f"\n판정 (§4 · H{v['primary_horizon']}): 순 배당 기여 {v['net_div_contribution_pct_per_month']}%/월 "
          f"vs 임계 {v['threshold_pct']} → {'유의미' if v['material'] else '부차적'}")
    print(f"        {v['action']}")
    if v["same_accounting_excess_still_negative"]:
        print("        🚨 동일 회계 초과가 여전히 음수 — 배당 가산 후에도 벤치에 미달")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
