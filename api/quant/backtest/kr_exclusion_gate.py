# -*- coding: utf-8 -*-
"""kr_exclusion_gate — 배제 게이트 동일강도 교체 검정 (짝지은 비교 · 파라미터 0).

사전등록 `docs/PREREG_EXCLUSION_GATE_ADOPTION_2026_08_12.md` · PM 승인 2026-08-12 "ㄱㄱ.".
🚨 관측 산출물만. **실행 1회 소진.** 재구축 6검정(소진)의 재실행이 아니다 — 새 소원장.

각 리밸런스 t (공통 단면 = 후보 점수 산출 가능 종목):
  r_t        = 현직 배제율 (safety_full < 55 — 운영 결측 기본값 그대로)
  현직 잔존   = safety_full ≥ 55
  후보 잔존   = 후보 백분위 상위 · **현직 잔존과 같은 인원수** (강도 상속 — 임계 발명 0)
  D_t(h)     = mean ret_h(후보 잔존) − mean ret_h(현직 잔존)      가설 D > 0

원장 6검정 = D(C1/C2/C3) × 20/60d · NW t → BH-FDR q=.05 · 채택 조건(§3-2):
  t≥3.0 양 호라이즌 + 승자 보존(전방 60d 상위 10% 보존율 ≥ 현직) + 반쪽 부호 +
  완전관측 부호 → 충족자 중 **축수 최소** (C1>C2>C3). 전원 미통과 = 무채택.
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
    DELIST_PATH, HORIZONS, _calendar, _select_non_overlapping, axis_fscore8,
    exclusion_reason, load_names, load_universe, t_stat,
)
from api.quant.backtest.kr_price_axes import (  # noqa: E402
    ENTRY_LAG, SCENARIOS, forward_return,
)
from api.quant.backtest.kr_safety_score import (  # noqa: E402
    MIN_VALID, PRIMARY_SCENARIO, bh_fdr, load_ohlcv_duckdb, load_panel,
    nw_lag, nw_t, pit_panel, pts_debt, pts_drop, pts_op_margin, pts_roe,
    pts_trading_value, two_sided_p,
)
from api.quant.backtest.kr_safety_score_full import (  # noqa: E402
    _pit_pair, load_op_margin, load_valuation, pts_div, pts_pbr, pts_per,
)
from api.quant.backtest.kr_formula_rebuild import (  # noqa: E402
    CANDS, MIN_AXES, pct_rank,
)

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "data")
OUT_PATH = os.path.join(_DATA, "analysis", "prereg_exclusion_gate_20260812.json")

MIN_SAFETY = 55                  # 현직 게이트 — 운영값 그대로 (강도 상속의 기준)
ADOPT_T = 3.0
BONF6 = 2.64
SPLIT_BOUNDARY = 20230301
WINNER_TOP_PCT = 0.10            # 승자 = 전방 60d conservative 상위 10% (§3-2-2)


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

    for as_of, tickers in universe:
        d_int = int(as_of)
        k = bisect.bisect_right(cal, d_int) - 1
        if k < 0 or k + ENTRY_LAG + max(HORIZONS) >= len(cal):
            continue
        signal_day, entry_day = cal[k], cal[k + ENTRY_LAG]
        exits = {h: cal[k + ENTRY_LAG + h] for h in HORIZONS}
        vrow = val.get(d_int) or {}

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
            hi52 = max(hist)
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
            dy = v.get("div_yield")
            if dy is None and v.get("div_src_year") is not None:
                dy = 0.0
            snaps = panel.get(t) or []
            p = pit_panel(snaps, signal_day) if snaps else None
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

            # 현직 safety_full — 운영 결측 기본값 그대로 (재구축과 동일 재현)
            incumbent = (pts_per(per_v) + pts_pbr(pbr_v) + pts_div(v.get("div_yield"))
                         + (pts_drop(drop) or 0) + (pts_trading_value(tv) or 0)
                         + (pts_debt(p.get("debt_ratio") if p else None) or 0)
                         + (pts_op_margin(omv) or 0) + (pts_roe(roa_ttm) or 0))

            raw.append({
                "t": t, "s": s, "incumbent": incumbent,
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
            except Exception:  # noqa: BLE001
                score = None
            r["vol"] = score
            del r["_hist"], r["_v20"], r["_v60"]

        ranks: Dict[str, Dict[int, float]] = {}
        for ax, hb in (("ep", True), ("bp", True), ("dy", True), ("opm", True),
                       ("roa", True), ("vol", True), ("fs8", True),
                       ("illiq_raw", False), ("nearhigh_raw", True)):
            key = {"illiq_raw": "illiq", "nearhigh_raw": "nearhigh"}.get(ax, ax)
            ranks[key] = pct_rank(
                [(j, float(r[ax])) for j, r in enumerate(raw) if r.get(ax) is not None], hb)

        rows: List[Dict[str, Any]] = []
        for j, r in enumerate(raw):
            rec: Dict[str, Any] = {"t": r["t"], "incumbent": r["incumbent"],
                                   "_absent": r["_absent"]}
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

    if not rebalances:
        return {"status": "no_rebalances"}
    entry_idx = [r["entry_idx"] for r in rebalances]

    # ── 짝지은 D 시계열 + 승자 보존 + 부재 구성 ──
    def _paired(cname: str, h: int, scen: str,
                row_filter=None) -> Tuple[List[Optional[float]], List[Dict[str, Any]]]:
        ds: List[Optional[float]] = []
        meta: List[Dict[str, Any]] = []
        rk = f"r{h}_{scen}"
        for rb in rebalances:
            common = [r for r in rb["rows"]
                      if r.get(cname) is not None and r.get(rk) is not None
                      and (row_filter is None or row_filter(r))]
            if len(common) < MIN_VALID:
                ds.append(None)
                meta.append({})
                continue
            inc_kept = [r for r in common if r["incumbent"] >= MIN_SAFETY]
            n_keep = len(inc_kept)
            if n_keep < 20 or n_keep >= len(common):
                ds.append(None)
                meta.append({})
                continue
            cand_sorted = sorted(common, key=lambda r: -float(r[cname]))
            cand_kept = cand_sorted[:n_keep]
            m_c = st.mean(float(r[rk]) for r in cand_kept)
            m_i = st.mean(float(r[rk]) for r in inc_kept)
            ds.append(m_c - m_i)
            # 승자 보존 (전방 60d conservative 상위 10% — §3-2-2, 정본 h 무관 공통 정의)
            wk = "r60_conservative"
            winners = sorted((r for r in common if r.get(wk) is not None),
                             key=lambda r: -float(r[wk]))
            winners = winners[:max(1, int(len(winners) * WINNER_TOP_PCT))]
            wset = {id(r) for r in winners}
            keep_c = {id(r) for r in cand_kept}
            keep_i = {id(r) for r in inc_kept}
            meta.append({
                "n_common": len(common), "n_keep": n_keep,
                "excl_rate": round(1 - n_keep / len(common), 4),
                "win_ret_cand": (sum(1 for w in wset if w in keep_c) / len(wset)),
                "win_ret_inc": (sum(1 for w in wset if w in keep_i) / len(wset)),
                "absent_excl_cand": (st.mean([r["_absent"] for r in cand_sorted[n_keep:]])
                                     if len(cand_sorted) > n_keep else None),
                "absent_excl_inc": (st.mean([r["_absent"] for r in common
                                             if r["incumbent"] < MIN_SAFETY]) or 0.0),
            })
        return ds, meta

    results: Dict[str, Any] = {}
    diag: Dict[str, Any] = {}
    for cname in CANDS:
        for h in HORIZONS:
            for scen in SCENARIOS:
                key = f"{cname}_{h}d_{scen}"
                ds, meta = _paired(cname, h, scen)
                sel = _select_non_overlapping(entry_idx, h)
                results[key] = {
                    "d_nw": nw_t([x for x in ds if x is not None], nw_lag(h)),
                    "d_non_overlap": t_stat([ds[i] for i in sel if ds[i] is not None]),
                    "d_mean_pct": (round(st.mean([x for x in ds if x is not None]) * 100, 4)
                                   if any(x is not None for x in ds) else None),
                }
                if scen == PRIMARY_SCENARIO:
                    # 반쪽 부호
                    half = {"H1": [], "H2": []}
                    for rb, x in zip(rebalances, ds):
                        if x is not None:
                            half["H1" if int(rb["as_of"]) < SPLIT_BOUNDARY else "H2"].append(x)
                    results[key]["split"] = {
                        hh: {"n": len(v), "mean": (round(st.mean(v), 6) if v else None),
                             "sign_pos": (st.mean(v) > 0 if v else None)}
                        for hh, v in half.items()}
                    if h == 60:
                        wr_c = [m["win_ret_cand"] for m in meta if m.get("win_ret_cand") is not None]
                        wr_i = [m["win_ret_inc"] for m in meta if m.get("win_ret_inc") is not None]
                        diag[f"{cname}_winner_retention"] = {
                            "cand": round(st.mean(wr_c), 4), "inc": round(st.mean(wr_i), 4),
                            "cand_ge_inc": st.mean(wr_c) >= st.mean(wr_i)}
                        diag[f"{cname}_absent_in_excluded"] = {
                            "cand": round(st.mean([m["absent_excl_cand"] for m in meta
                                                   if m.get("absent_excl_cand") is not None]), 4),
                            "inc": round(st.mean([m["absent_excl_inc"] for m in meta
                                                  if m.get("absent_excl_inc") is not None]), 4)}
                        diag["excl_rate_mean"] = round(
                            st.mean([m["excl_rate"] for m in meta if m.get("excl_rate")]), 4)
        # 완전관측 부분표본 부호 (양 호라이즌)
        for h in HORIZONS:
            ds_f, _ = _paired(cname, h, PRIMARY_SCENARIO, row_filter=lambda r: r["_full"] == 1)
            vals = [x for x in ds_f if x is not None]
            diag[f"{cname}_full_obs_{h}d"] = {
                "n": len(vals), "mean": (round(st.mean(vals), 6) if vals else None),
                "sign_pos": (st.mean(vals) > 0 if vals else None)}

    ledger = [f"{c}_{h}d_{PRIMARY_SCENARIO}" for c in CANDS for h in HORIZONS]
    pv = [two_sided_p(results[k]["d_nw"].get("t"), results[k]["d_nw"].get("n")) for k in ledger]
    for k, p_, okbh in zip(ledger, pv, bh_fdr(pv, q=0.05)):
        results[k]["p_two_sided"] = round(p_, 6) if p_ is not None else None
        results[k]["passes_bh_fdr"] = okbh

    adoption: Dict[str, Any] = {}
    adopted = None
    for cname in ("C1", "C2", "C3"):
        c20 = results[f"{cname}_20d_{PRIMARY_SCENARIO}"]
        c60 = results[f"{cname}_60d_{PRIMARY_SCENARIO}"]
        cond = {
            "bh_both": bool(c20.get("passes_bh_fdr") and c60.get("passes_bh_fdr")),
            "t3_both": bool((c20["d_nw"].get("t") or 0) >= ADOPT_T
                            and (c60["d_nw"].get("t") or 0) >= ADOPT_T),
            "winner_retention": bool(diag[f"{cname}_winner_retention"]["cand_ge_inc"]),
            "split_sign": all(results[f"{cname}_{h}d_{PRIMARY_SCENARIO}"]["split"][hh]["sign_pos"]
                              is True for h in HORIZONS for hh in ("H1", "H2")),
            "full_obs_sign": all(diag[f"{cname}_full_obs_{h}d"]["sign_pos"] is True
                                 for h in HORIZONS),
        }
        cond["all_pass"] = all(cond.values())
        adoption[cname] = cond
        if adopted is None and cond["all_pass"]:
            adopted = cname
    adoption["adopted"] = adopted
    adoption["rule"] = "전 조건 충족자 중 축수 최소 (C1>C2>C3). 전원 미통과 = 무채택 (§3-2)"

    doc = {
        "_meta": {
            "prereg": "docs/PREREG_EXCLUSION_GATE_ADOPTION_2026_08_12.md",
            "approved": "PM 2026-08-12 'ㄱㄱ.'",
            "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00",
                                         time.localtime(time.time() + 9 * 3600)),
            "design": "동일강도 짝지은 교체 — r_t 를 현직(min_safety 55)에서 상속, 같은 인원수",
            "tests": len(ledger),
            "judgment": f"NW t → BH-FDR q=.05 · 채택 |t|≥{ADOPT_T} 양 호라이즌 · 참고 Bonf {BONF6}",
        },
        "coverage": {
            "rebalances": len(rebalances),
            "window": [rebalances[0]["as_of"], rebalances[-1]["as_of"]],
            "elapsed_sec": round(time.time() - t0, 1),
        },
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
        print("[excl_gate] no_rebalances", file=sys.stderr)
        return 1
    c = r["coverage"]
    d = r["diagnostics"]
    print(f"\n[excl_gate] 리밸런스 {c['rebalances']} · 평균 배제율 {d.get('excl_rate_mean')}"
          f" · {c['elapsed_sec']}s")
    sc = PRIMARY_SCENARIO
    print(f"\n{'후보':5}{'D20(%)':>9}{'t':>7}{'D60(%)':>9}{'t':>7}{'승자보존 후보/현직':>16}{'채택조건':>9}")
    for cn in ("C1", "C2", "C3"):
        a20 = r["results"][f"{cn}_20d_{sc}"]
        a60 = r["results"][f"{cn}_60d_{sc}"]
        w = d[f"{cn}_winner_retention"]
        ok = r["adoption"][cn]["all_pass"]
        print(f"{cn:5}{(a20.get('d_mean_pct') or 0):>9.3f}{(a20['d_nw'].get('t') or 0):>7.2f}"
              f"{(a60.get('d_mean_pct') or 0):>9.3f}{(a60['d_nw'].get('t') or 0):>7.2f}"
              f"{w['cand']:>9.3f}/{w['inc']:.3f}{('전부충족' if ok else '미충족'):>9}")
    print(f"\n채택: {r['adoption']['adopted'] or '무채택 (현행 유지)'}")
    for cn in ("C1", "C2", "C3"):
        fails = [k for k, v in r["adoption"][cn].items() if v is False and k != "all_pass"]
        if fails:
            print(f"  {cn} 실패 조건: {fails}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
