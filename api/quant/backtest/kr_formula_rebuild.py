# -*- coding: utf-8 -*-
"""kr_formula_rebuild — 진입 필터 산식 재구축 검정 (후보 3종 · 파라미터 0).

사전등록 `docs/PREREG_FORMULA_REBUILD_2026_08_12.md` · PM 승인 2026-08-12 "승인. ㄱㄱ".
🚨 관측 산출물만. 점수·집행 입력 0. **실행 1회 소진.** 운영 컷오버는 별도 승인(§7).

후보 = 단면 백분위 순위(0~1)의 **단순 평균** (가중치 0 — 8/8 H4 "가중 근거 없음"):
  C1 (5축) E/P · B/P · DY · OPM(연간) · ROA_ttm
  C2 (7축) C1 + volatility(운영 함수) + F-Score8(8/8 함수)
  C3 (9축) C2 + 비유동성(거래대금↓=고순위) + 고점근접(낙폭↓=고순위)   🚨 부호 표본 내 학습

결측 = 축 제외, 점수 = 가용 축 순위 평균, 가용 < ⌈K/2⌉ 이면 단면 제외 (등록 §2 —
`pbr 결측→3점` 류 기본값 채널 폐지).

🚨 사전 명세 해소 1건 (데이터 관측 전 고정): DY 축의 "무배당 vs 미수집" 구분 —
   `div_src_year` 존재(그해 alotMatter 응답 있음) + `div_yield` None = **실제 무배당 → DY 0.0**.
   `div_src_year` 도 없으면 미수집 = 결측. 무배당을 결측으로 빼면 저배당 순위가 왜곡된다.

채택 규칙(§5, argmax 금지): BH + |NW t|≥3.0(양 호라이즌) + 비용(60d 연환산>+1.2% ·
20d≥0) + 현직 IC 이상(20d +0.0578 / 60d +0.0839) + 진단 무결 → **축수 최소** 후보.
전원 미통과 = 무채택. 진단 4종(§6)은 방향 무관 전부 실행.
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

from api.quant.backtest.kr_fundamental import (  # noqa: E402
    DELIST_PATH, HORIZONS, _calendar, _select_non_overlapping, axis_fscore8,
    exclusion_reason, load_names, load_universe, spearman, t_stat,
)
from api.quant.backtest.kr_price_axes import (  # noqa: E402
    COMMISSION, ENTRY_LAG, SCENARIOS, SELL_TAX, forward_return,
)
from api.quant.backtest.kr_safety_score import (  # noqa: E402
    MIN_VALID, N_QUANTILE, PRIMARY_SCENARIO, bh_fdr, load_ohlcv_duckdb,
    load_panel, nw_lag, nw_t, pit_panel, two_sided_p,
)
from api.quant.backtest.kr_safety_score_full import (  # noqa: E402
    load_op_margin, load_valuation, _pit_pair,
)

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "data")
OUT_PATH = os.path.join(_DATA, "analysis", "prereg_formula_rebuild_20260812.json")

# ── 등록값 (§3·§5·§6) ───────────────────────────────────────────────────────
CANDS: Dict[str, Tuple[str, ...]] = {
    "C1": ("ep", "bp", "dy", "opm", "roa"),
    "C2": ("ep", "bp", "dy", "opm", "roa", "vol", "fs8"),
    "C3": ("ep", "bp", "dy", "opm", "roa", "vol", "fs8", "illiq", "nearhigh"),
}
MIN_AXES = {k: math.ceil(len(v) / 2) for k, v in CANDS.items()}   # 3 / 4 / 5
ADOPT_T = 3.0                    # Harvey-Liu-Zhu — 게이트 재설계 G1
BONF6 = 2.64                     # 참고: α=.05/6 양측
COST60_MIN_PCT = 1.2             # 60d 연환산 스프레드 하한 (%/yr)
COST20_MIN_PCT = 0.0
INCUMBENT_IC = {20: 0.0578, 60: 0.0839}   # #354 safety_full (정본·NW)
SPLIT_BOUNDARY = 20230301        # 반쪽: 2020-01~2023-02 / 2023-03~2026-04
M_TRIALS = 46                    # DSR 벤치마크 — 이 창의 누적 등록 검정 수 (§1-4)


def emax_null_t(m: int = M_TRIALS) -> float:
    """M 회 독립 영가설 시도에서 기대 최대 |t| (Bailey-LdP E[max] 근사, γ=오일러 상수)."""
    from scipy.stats import norm
    g = 0.5772156649
    return float((1 - g) * norm.ppf(1 - 1 / m) + g * norm.ppf(1 - 1 / (m * math.e)))


def pct_rank(pairs: List[Tuple[int, float]], higher_better: bool) -> Dict[int, float]:
    """단면 백분위 순위 (0~1, 동점 평균). pairs = (row_idx, value)."""
    if not pairs:
        return {}
    from scipy.stats import rankdata
    vals = [v for _, v in pairs]
    r = rankdata(vals if higher_better else [-v for v in vals], method="average")
    n = len(vals)
    return {idx: float(rk) / n for (idx, _), rk in zip(pairs, r)}


def run(lake: str, out_path: str = OUT_PATH, limit_rebalances: int = 0) -> Dict[str, Any]:
    t0 = time.time()
    universe = load_universe()
    names = load_names()
    px = load_ohlcv_duckdb(lake)
    panel = load_panel()
    val = load_valuation()
    opm_hist = load_op_margin()
    from api.quant.factors.volatility import (_compute_vols_from_history,
                                              compute_volatility_score)
    try:
        dl = json.load(open(DELIST_PATH, encoding="utf-8")) or {}
        gone = {t for t, v in (dl.get("last_seen") or {}).items()
                if str(v) != str(dl.get("as_of"))}
    except (OSError, json.JSONDecodeError):
        gone = set()

    cal = _calendar({t: {"d": s["d"], "c": s["c"]} for t, s in px.items()})
    rebalances: List[Dict[str, Any]] = []
    cover = {k: 0 for a in CANDS.values() for k in a}
    cover.update({"rows": 0, "panel_absent": 0})

    for as_of, tickers in universe:
        d_int = int(as_of)
        k = bisect.bisect_right(cal, d_int) - 1
        if k < 0 or k + ENTRY_LAG + max(HORIZONS) >= len(cal):
            continue
        signal_day, entry_day = cal[k], cal[k + ENTRY_LAG]
        exits = {h: cal[k + ENTRY_LAG + h] for h in HORIZONS}
        vrow = val.get(d_int) or {}

        # ── 1패스: 원시 축값 ──
        raw: List[Dict[str, Any]] = []
        vols20: List[float] = []
        for t in tickers:
            if exclusion_reason(t, names.get(t)):
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
            hist = close[max(0, i - 251):i + 1]
            lo = max(0, i - 251)
            hi52 = max(close[lo:i + 1])
            drop = ((pxc - hi52) / hi52 * 100.0) if hi52 > 0 else None
            vol_s = s.get("v")
            tv = None
            if vol_s and len(vol_s) > i:
                vv = [close[j] * vol_s[j] for j in range(max(0, i - 19), i + 1)
                      if vol_s[j] is not None and close[j] is not None]
                if vv:
                    tv = sum(vv) / len(vv)

            v = vrow.get(t) or {}
            per_v, pbr_v = v.get("per"), v.get("pbr")
            # DY — 사전 명세: div_src_year 있으면 무배당=0.0, 없으면 결측
            dy = v.get("div_yield")
            if dy is None and v.get("div_src_year") is not None:
                dy = 0.0

            snaps = panel.get(t) or []
            p = pit_panel(snaps, signal_day) if snaps else None
            if p is None:
                cover["panel_absent"] += 1
            roa_ttm = p.get("roa_ttm") if p else None
            fs8 = axis_fscore8(p, snaps) if p else None
            omv = _pit_pair(opm_hist.get(t) or [], signal_day)

            v20, v60 = (None, None)
            if len(hist) >= 20:
                try:
                    v20, v60 = _compute_vols_from_history(hist)
                except Exception:  # noqa: BLE001
                    v20 = v60 = None
            if isinstance(v20, (int, float)) and v20 > 0:
                vols20.append(float(v20))

            raw.append({
                "t": t, "s": s, "i": i,
                "ep": (1.0 / per_v if isinstance(per_v, (int, float)) and per_v > 0 else None),
                "bp": (1.0 / pbr_v if isinstance(pbr_v, (int, float)) and pbr_v > 0 else None),
                "dy": dy, "opm": omv, "roa": roa_ttm,
                "fs8": (float(fs8) if fs8 is not None else None),
                "_v20": v20, "_v60": v60, "_hist": hist,
                "illiq_raw": tv, "nearhigh_raw": drop,
                "_absent": 1 if p is None else 0,
            })
        if len(raw) < MIN_VALID:
            continue

        # ── volatility 운영 함수 (8/8 과 동일 — 단면 중앙값 통계 주입) ──
        med = sorted(vols20)[len(vols20) // 2] if vols20 else None
        ustats = {"median_vol_20d": med} if med else {}
        for r in raw:
            score = None
            try:
                res = compute_volatility_score(
                    {"ticker": r["t"], "price_history": r["_hist"],
                     "volatility_20d": r["_v20"], "volatility_60d": r["_v60"]},
                    universe_stats=ustats) or {}
                sv = res.get("volatility_score")
                score = float(sv) if isinstance(sv, (int, float)) else None
            except Exception:  # noqa: BLE001 — 개별 실패 = 축 결측
                score = None
            r["vol"] = score
            del r["_hist"], r["_v20"], r["_v60"]

        # ── 단면 백분위 순위 (방향 명세 §2) ──
        ranks: Dict[str, Dict[int, float]] = {}
        for ax, hb in (("ep", True), ("bp", True), ("dy", True), ("opm", True),
                       ("roa", True), ("vol", True), ("fs8", True),
                       ("illiq_raw", False), ("nearhigh_raw", True)):
            key = {"illiq_raw": "illiq", "nearhigh_raw": "nearhigh"}.get(ax, ax)
            pairs = [(j, float(r[ax])) for j, r in enumerate(raw) if r.get(ax) is not None]
            ranks[key] = pct_rank(pairs, hb)
            for j, _ in pairs:
                cover[key] += 1
        cover["rows"] += len(raw)

        # ── 후보 점수 + 수익률 ──
        rows: List[Dict[str, Any]] = []
        for j, r in enumerate(raw):
            rec: Dict[str, Any] = {"t": r["t"], "_absent": r["_absent"]}
            full_obs = True
            for cname, axes in CANDS.items():
                have = [ranks[a][j] for a in axes if j in ranks.get(a, {})]
                rec[cname] = (sum(have) / len(have) if len(have) >= MIN_AXES[cname] else None)
                if len(have) < len(axes):
                    full_obs = False
            rec["_full"] = 1 if full_obs else 0
            ok = False
            for h in HORIZONS:
                for scen in SCENARIOS:
                    fr = forward_return(r["s"], entry_day, exits[h],
                                        delisted=(r["t"] in gone),
                                        haircut=(scen == "conservative"))
                    if fr is not None:
                        rec[f"r{h}_{scen}"] = round(fr[0], 6)
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
        "total_observations": sum(len(r["rows"]) for r in rebalances),
        "median_names": (sorted(len(r["rows"]) for r in rebalances)[len(rebalances) // 2]
                         if rebalances else 0),
        "axis_fill_pct": {k: round(cover[k] / cover["rows"] * 100, 1)
                          for k in ("ep", "bp", "dy", "opm", "roa", "vol", "fs8",
                                    "illiq", "nearhigh") if cover["rows"]},
        "panel_absent_pct": (round(cover["panel_absent"] / cover["rows"] * 100, 1)
                             if cover["rows"] else None),
        "elapsed_sec": round(time.time() - t0, 1),
    }
    if not rebalances:
        return {"status": "no_rebalances", "coverage": coverage}

    entry_idx = [r["entry_idx"] for r in rebalances]

    def _ic_series(field: str, h: int, scen: str,
                   row_filter=None) -> Tuple[List[Optional[float]], List[Optional[float]]]:
        ics, sprd = [], []
        for rb in rebalances:
            xs, ys = [], []
            for r in rb["rows"]:
                if row_filter and not row_filter(r):
                    continue
                vx, ret = r.get(field), r.get(f"r{h}_{scen}")
                if vx is None or ret is None:
                    continue
                xs.append(float(vx))
                ys.append(float(ret))
            ics.append(spearman(xs, ys) if len(xs) >= MIN_VALID else None)
            if len(xs) >= N_QUANTILE * 3:
                order = sorted(range(len(xs)), key=lambda q: xs[q])
                kq = max(1, len(order) // N_QUANTILE)
                lo_r = sum(ys[q] for q in order[:kq]) / kq
                hi_r = sum(ys[q] for q in order[-kq:]) / kq
                sprd.append((hi_r - lo_r) - 2 * (2 * COMMISSION + SELL_TAX))
            else:
                sprd.append(None)
        return ics, sprd

    results: Dict[str, Any] = {}
    for cname in CANDS:
        for h in HORIZONS:
            for scen in SCENARIOS:
                key = f"{cname}_{h}d_{scen}"
                ics, sprd = _ic_series(cname, h, scen)
                sel = _select_non_overlapping(entry_idx, h)
                nov_sp = t_stat([sprd[i] for i in sel if sprd[i] is not None])
                results[key] = {
                    "ic_nw": nw_t([x for x in ics if x is not None], nw_lag(h)),
                    "ic_non_overlap": t_stat([ics[i] for i in sel if ics[i] is not None]),
                    "spread_non_overlap": nov_sp,
                    "spread_ann_pct": (round(nov_sp["mean"] * 252 / h * 100, 2)
                                       if nov_sp.get("mean") is not None else None),
                }

    ledger = [f"{c}_{h}d_{PRIMARY_SCENARIO}" for c in CANDS for h in HORIZONS]
    pv = [two_sided_p(results[k]["ic_nw"].get("t"), results[k]["ic_nw"].get("n"))
          for k in ledger]
    for k, p_, okbh in zip(ledger, pv, bh_fdr(pv, q=0.05)):
        results[k]["p_two_sided"] = round(p_, 6) if p_ is not None else None
        results[k]["passes_bh_fdr"] = okbh
        results[k]["in_ledger"] = True
    for k in results:
        results[k].setdefault("in_ledger", False)

    # ── §6 의무 진단 — 방향 무관 전부 ──
    diag: Dict[str, Any] = {}
    # 1. 부재 더미 + 완전관측 부분표본
    ics_d, _ = _ic_series("_absent", 20, PRIMARY_SCENARIO)
    diag["absent_dummy_ic_20d"] = nw_t([x for x in ics_d if x is not None], nw_lag(20))
    for cname in CANDS:
        f20, _ = _ic_series(cname, 20, PRIMARY_SCENARIO, row_filter=lambda r: r["_full"] == 1)
        diag[f"{cname}_full_obs_ic_20d"] = nw_t([x for x in f20 if x is not None], nw_lag(20))
    # 2. 반쪽 부호 일관성
    for cname in CANDS:
        for h in HORIZONS:
            ics, _ = _ic_series(cname, h, PRIMARY_SCENARIO)
            half = {"H1": [], "H2": []}
            for rb, ic in zip(rebalances, ics):
                if ic is None:
                    continue
                half["H1" if int(rb["as_of"]) < SPLIT_BOUNDARY else "H2"].append(ic)
            diag[f"{cname}_{h}d_split"] = {
                hh: {"n": len(v), "mean_ic": (round(st.mean(v), 5) if v else None),
                     "sign_pos": (st.mean(v) > 0 if v else None)}
                for hh, v in half.items()}
    # 3. 분위 단조성 (20d 정본)
    for cname in CANDS:
        acc = [[] for _ in range(N_QUANTILE)]
        for rb in rebalances:
            pair = [(float(r[cname]), float(r[f"r20_{PRIMARY_SCENARIO}"]))
                    for r in rb["rows"]
                    if r.get(cname) is not None and r.get(f"r20_{PRIMARY_SCENARIO}") is not None]
            if len(pair) < MIN_VALID:
                continue
            pair.sort(key=lambda z: z[0])
            kq = len(pair) // N_QUANTILE
            for q in range(N_QUANTILE):
                seg = pair[q * kq:(q + 1) * kq] if q < N_QUANTILE - 1 else pair[q * kq:]
                if seg:
                    acc[q].append(sum(z[1] for z in seg) / len(seg))
        means = [round(sum(a) / len(a) * 100, 3) if a else None for a in acc]
        diag[f"{cname}_quantile_20d_pct"] = means
        diag[f"{cname}_monotone_increasing"] = all(
            means[i] is not None and means[i + 1] is not None and means[i] <= means[i + 1]
            for i in range(N_QUANTILE - 1))
    # 4. DSR 벤치마크
    diag["dsr_benchmark"] = {
        "m_trials_cumulative": M_TRIALS,
        "expected_max_abs_t_under_null": round(emax_null_t(), 3),
        "note": "누적 46회 등록 검정 가정 시 영가설 기대 최대 |t|. 후보 t 가 이를 넘어야 "
                "선택 효과 이상이라 말할 수 있다 (기술 통계 — 채택 조건은 §5의 t≥3.0)",
    }

    # ── §5 채택 규칙 자동 평가 (argmax 금지 — 축수 오름차순) ──
    adoption: Dict[str, Any] = {}
    adopted = None
    for cname in ("C1", "C2", "C3"):
        c20 = results[f"{cname}_20d_{PRIMARY_SCENARIO}"]
        c60 = results[f"{cname}_60d_{PRIMARY_SCENARIO}"]
        split_ok = all(
            diag[f"{cname}_{h}d_split"][hh]["sign_pos"] is True
            for h in HORIZONS for hh in ("H1", "H2"))
        cond = {
            "bh_both": bool(c20.get("passes_bh_fdr") and c60.get("passes_bh_fdr")),
            "t3_both": bool((c20["ic_nw"].get("t") or 0) >= ADOPT_T
                            and (c60["ic_nw"].get("t") or 0) >= ADOPT_T),
            "cost_60d": bool((c60.get("spread_ann_pct") or -9e9) > COST60_MIN_PCT),
            "cost_20d": bool((c20.get("spread_ann_pct") or -9e9) >= COST20_MIN_PCT),
            "beats_incumbent": bool(
                (c20["ic_nw"].get("mean") or 0) >= INCUMBENT_IC[20]
                and (c60["ic_nw"].get("mean") or 0) >= INCUMBENT_IC[60]),
            "split_sign_consistent": split_ok,
            "monotone": bool(diag.get(f"{cname}_monotone_increasing")),
        }
        cond["all_pass"] = all(cond.values())
        adoption[cname] = cond
        if adopted is None and cond["all_pass"]:
            adopted = cname          # 축수 오름차순 순회 = 최소 축 우선
    adoption["adopted"] = adopted
    adoption["rule"] = ("전 조건 통과 후보 중 축수 최소 (C1>C2>C3 우선). "
                        "전원 미통과 = 무채택·현행 유지 (§5)")

    doc = {
        "_meta": {
            "prereg": "docs/PREREG_FORMULA_REBUILD_2026_08_12.md",
            "approved": "PM 2026-08-12 '승인. ㄱㄱ'",
            "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00",
                                         time.localtime(time.time() + 9 * 3600)),
            "tests": len(ledger),
            "judgment": f"NW t → BH-FDR q=.05 · 채택 |t|≥{ADOPT_T} · 참고 Bonferroni {BONF6}",
            "incumbent_ic": INCUMBENT_IC,
            "in_sample_caveat": ("축 선택이 같은 2020-2026 창에서 이뤄졌다(등록 §1). "
                                 "이 통과는 '표본 내 확인 + 문헌 prior' 이상을 주장하지 않는다. "
                                 "진짜 표본외 = 채택 후 G2 동결 전방 모니터."),
            "weights": "동일가중 순위 평균 — 적합 파라미터 0 (8/8 H4)",
        },
        "coverage": coverage,
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
    r = run(a.lake, limit_rebalances=a.limit)
    if r.get("status") == "no_rebalances":
        print("[rebuild] no_rebalances", file=sys.stderr)
        return 1
    c = r["coverage"]
    print(f"\n[rebuild] 리밸런스 {c['rebalances']} · 관측 {c['total_observations']:,} "
          f"· 중앙 {c['median_names']} · {c['elapsed_sec']}s")
    print(f"[rebuild] 축 채움율 {c['axis_fill_pct']} · 패널부재 {c['panel_absent_pct']}%")
    sc = PRIMARY_SCENARIO
    print(f"\n{'후보':5}{'IC20':>8}{'t':>7}{'IC60':>8}{'t':>7}{'스프레드60d(연)':>13}{'BH':>5}{'채택조건':>9}")
    for cn in ("C1", "C2", "C3"):
        a20 = r["results"][f"{cn}_20d_{sc}"]
        a60 = r["results"][f"{cn}_60d_{sc}"]
        ok = r["adoption"][cn]["all_pass"]
        bh = a20.get("passes_bh_fdr") and a60.get("passes_bh_fdr")
        print(f"{cn:5}{(a20['ic_nw'].get('mean') or 0):>8.4f}{(a20['ic_nw'].get('t') or 0):>7.2f}"
              f"{(a60['ic_nw'].get('mean') or 0):>8.4f}{(a60['ic_nw'].get('t') or 0):>7.2f}"
              f"{(a60.get('spread_ann_pct') or 0):>12.1f}%{('통과' if bh else '—'):>5}"
              f"{('전부충족' if ok else '미충족'):>9}")
    print(f"\n채택: {r['adoption']['adopted'] or '무채택 (현행 유지)'}")
    d = r["diagnostics"]
    print(f"부재더미 IC(20d): {d['absent_dummy_ic_20d']}")
    print(f"DSR 벤치: E[max|t|]≈{d['dsr_benchmark']['expected_max_abs_t_under_null']} (M=46)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
