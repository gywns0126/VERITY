# -*- coding: utf-8 -*-
"""kr_segment_ic — 세그먼트별 조건부 IC + 가중 방식 검정.

사전등록 `docs/PREREG_SEGMENT_IC_2026_08_14.md` · PM 승인 2026-08-14 "ㄱㄱ".
🚨 진단이며 산식·운영 무변경 (§4). 실행 1회 소진.

문제 재정의(§0): 대형주는 **이미 유니버스 안에 있다**(삼성전자 1,534조 · SK하이닉스
1,255조 포함, mktcap 채움율 100%). 표적은 유니버스가 아니라 **동일가중**이다 —
1,534조와 500억을 같은 0.05% 로 취급해 KOSPI 가 받은 대형주 상승(+171.8%)을 희석했다.

원장 8검정:
  1~6  C3 IC — 시총 3분위(대/중/소) 내 · 20/60일 · 방향 (+)
  7·8  시총가중 상위10 − 동일가중 상위10 초과수익 · 20/60일 · 부호 없음(양방향 관심)
판정 = NW t → BH-FDR q=.05 · 채택 주장 |t|≥3.0 · 참고 Bonferroni 2.73.

🚨 §4 차단 조항: 시총가중이 이겨도 **진단 3(무작위와 무차별)** 이면 채택 불가 —
   지수 추종을 자체 산식으로 위장하는 것이다.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import random
import statistics as st
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from api.quant.backtest.kr_fundamental import (  # noqa: E402
    DELIST_PATH, _calendar, exclusion_reason, load_names, load_universe, spearman,
)
from api.quant.backtest.kr_price_axes import ENTRY_LAG, forward_return  # noqa: E402
from api.quant.backtest.kr_safety_score import (  # noqa: E402
    MIN_VALID, bh_fdr, load_ohlcv_duckdb, load_panel, nw_lag, nw_t, pit_panel,
    two_sided_p,
)
from api.quant.backtest.kr_safety_score_full import (  # noqa: E402
    _pit_pair, load_op_margin, load_valuation,
)
from api.quant.backtest.kr_formula_rebuild import pct_rank  # noqa: E402
from api.quant.backtest.kr_transfer_diagnosis import C3_AXES  # noqa: E402

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "data")
OUT_PATH = os.path.join(_DATA, "analysis", "prereg_segment_ic_20260814.json")

# ── 등록값 (§2·§3) ──────────────────────────────────────────────────────────
HORIZONS = (20, 60)
SEGMENTS = ("large", "mid", "small")     # 시총 3분위 (동일 종목수)
TOP_N = 10
SPLIT_BOUNDARY = 20230301
ADOPT_T = 3.0
BONF8 = 2.73
RANDOM_TRIALS = 20
CONC_WARN = 0.60                          # §3-2 상위3 합 60% = 개별주 베팅
ORDER_KRW = 2_000_000
IMPACT_WARN = 0.05


def build(lake: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """리밸런스별 C3 점수 + 시총 + **20/60일 수익률 둘 다**.

    🚨 kr_transfer_diagnosis.build_cross_sections 는 20일만 산출한다(착수 전 확인).
       등록이 20/60 둘 다이므로 여기서 자체 산출한다 — 재사용 불가 확인 후 결정.
    """
    universe, names = load_universe(), load_names()
    px = load_ohlcv_duckdb(lake)
    panel, val, opm_hist = load_panel(), load_valuation(), load_op_margin()
    from api.quant.backtest.kr_fundamental import axis_fscore8
    from api.quant.factors.volatility import (_compute_vols_from_history,
                                              compute_volatility_score)
    cal = _calendar({t: {"d": s["d"], "c": s["c"]} for t, s in px.items()})
    dl = json.load(open(DELIST_PATH, encoding="utf-8")) or {}
    gone = {t for t, v in (dl.get("last_seen") or {}).items()
            if str(v) != str(dl.get("as_of"))}

    snaps: List[Dict[str, Any]] = []
    for as_of, tickers in universe:
        d = int(as_of)
        k = bisect.bisect_right(cal, d) - 1
        if k < 0 or k + ENTRY_LAG + max(HORIZONS) >= len(cal):
            continue
        sd, ed = cal[k], cal[k + ENTRY_LAG]
        ex = {h: cal[k + ENTRY_LAG + h] for h in HORIZONS}
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
            v = vrow.get(t) or {}
            mc = v.get("mktcap")
            if not mc:
                continue                     # 세그먼트 분할 불가 종목은 제외 (건수 신고)
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
            rets: Dict[int, Optional[float]] = {}
            for h in HORIZONS:
                fr = forward_return(s, ed, ex[h], delisted=(t in gone), haircut=True)
                rets[h] = fr[0] if fr else None
            raw.append({
                "t": t, "mktcap": float(mc), "adv": tv, "rets": rets,
                "ep": (1.0 / per_v if isinstance(per_v, (int, float)) and per_v > 0 else None),
                "bp": (1.0 / pbr_v if isinstance(pbr_v, (int, float)) and pbr_v > 0 else None),
                "dy": dy, "opm": omv, "roa": (p.get("roa_ttm") if p else None),
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
        rows = []
        for j, r in enumerate(raw):
            have = [ranks[a][j] for a in C3_AXES if j in ranks.get(a, {})]
            if len(have) >= 5:
                rows.append({**r, "score": sum(have) / len(have)})
        if len(rows) < MIN_VALID:
            continue
        # 시총 3분위 (동일 종목수 · PIT 시총)
        rows.sort(key=lambda r: r["mktcap"])
        n = len(rows)
        for idx, r in enumerate(rows):
            r["seg"] = ("small" if idx < n // 3 else
                        ("mid" if idx < 2 * n // 3 else "large"))
        snaps.append({"as_of": d, "rows": rows})
        if len(snaps) % 20 == 0:
            print(f"  단면 {len(snaps)} · {as_of}", flush=True)
    return snaps, px


def run(lake: str, out_path: str = OUT_PATH, limit: int = 0) -> Dict[str, Any]:
    t0 = time.time()
    snaps, _px = build(lake)
    if limit:
        snaps = snaps[:limit]
    if not snaps:
        return {"status": "no_snapshots"}

    def half(d: int) -> str:
        return "H1" if d < SPLIT_BOUNDARY else "H2"

    # ── 검정 1~6: 세그먼트 내 IC ──
    results: Dict[str, Any] = {}
    ledger: List[str] = []
    for seg in SEGMENTS:
        for h in HORIZONS:
            key = f"ic_{seg}_{h}d"
            ledger.append(key)
            ics = []
            for sn in snaps:
                sub = [r for r in sn["rows"]
                       if r["seg"] == seg and r["rets"].get(h) is not None]
                if len(sub) < MIN_VALID:
                    ics.append(None)
                    continue
                ics.append(spearman([r["score"] for r in sub],
                                    [r["rets"][h] for r in sub]))
            vals = [x for x in ics if x is not None]
            results[key] = {"nw": nw_t(vals, nw_lag(h)), "n": len(vals)}
            hv = {"H1": [], "H2": []}
            for sn, ic in zip(snaps, ics):
                if ic is not None:
                    hv[half(sn["as_of"])].append(ic)
            results[key]["split"] = {
                k: {"n": len(v), "mean": (round(st.mean(v), 5) if v else None)}
                for k, v in hv.items()}

    # ── 검정 7·8: 시총가중 상위10 − 동일가중 상위10 ──
    def topn_ret(rows: List[Dict[str, Any]], h: int, weight: str,
                 picker=None) -> Optional[float]:
        cand = [r for r in rows if r["rets"].get(h) is not None]
        if len(cand) < TOP_N:
            return None
        sel = (picker(cand) if picker
               else sorted(cand, key=lambda r: -r["score"])[:TOP_N])
        if weight == "equal":
            return st.mean(r["rets"][h] for r in sel)
        tot = sum(r["mktcap"] for r in sel)
        if tot <= 0:
            return None
        return sum(r["rets"][h] * r["mktcap"] / tot for r in sel)

    for h in HORIZONS:
        key = f"capw_minus_ew_{h}d"
        ledger.append(key)
        diffs, hv = [], {"H1": [], "H2": []}
        for sn in snaps:
            cw = topn_ret(sn["rows"], h, "cap")
            ew = topn_ret(sn["rows"], h, "equal")
            if cw is None or ew is None:
                continue
            diffs.append(cw - ew)
            hv[half(sn["as_of"])].append(cw - ew)
        results[key] = {"nw": nw_t(diffs, nw_lag(h)), "n": len(diffs),
                        "split": {k: {"n": len(v),
                                      "mean": (round(st.mean(v), 5) if v else None)}
                                  for k, v in hv.items()}}

    pv = [two_sided_p(results[k]["nw"].get("t"), results[k]["nw"].get("n"))
          for k in ledger]
    for k, p_, ok in zip(ledger, pv, bh_fdr(pv, q=0.05)):
        results[k]["p_two_sided"] = round(p_, 6) if p_ is not None else None
        results[k]["passes_bh_fdr"] = ok
        results[k]["passes_t3"] = bool(
            results[k]["nw"].get("t") is not None
            and abs(results[k]["nw"]["t"]) >= ADOPT_T)

    # ── §3 진단 4종 ──
    diag: Dict[str, Any] = {}
    # 1. 세그먼트별 수익 기준선
    for seg in SEGMENTS:
        hv = {"H1": [], "H2": []}
        for sn in snaps:
            sub = [r for r in sn["rows"]
                   if r["seg"] == seg and r["rets"].get(20) is not None]
            if len(sub) >= MIN_VALID:
                hv[half(sn["as_of"])].append(st.mean(r["rets"][20] for r in sub))
        diag[f"seg_return_{seg}_20d_pct"] = {
            k: (round(st.mean(v) * 100, 4) if v else None) for k, v in hv.items()}
    # 2. 집중도 (시총가중 상위10)
    mx, top3 = [], []
    for sn in snaps:
        cand = [r for r in sn["rows"] if r["rets"].get(20) is not None]
        if len(cand) < TOP_N:
            continue
        sel = sorted(cand, key=lambda r: -r["score"])[:TOP_N]
        tot = sum(r["mktcap"] for r in sel)
        if tot <= 0:
            continue
        w = sorted((r["mktcap"] / tot for r in sel), reverse=True)
        mx.append(w[0])
        top3.append(sum(w[:3]))
    diag["capw_concentration"] = {
        "max_single_mean": (round(st.mean(mx), 4) if mx else None),
        "top3_sum_mean": (round(st.mean(top3), 4) if top3 else None),
        "over_60pct_rebalances": sum(1 for x in top3 if x > CONC_WARN),
        "note": f"상위3 합 > {CONC_WARN:.0%} = 사실상 개별주 베팅 (§3-2)"}
    # 3. 🚨 점수 기여 소멸 검사 — 시총가중 상위10 vs 시총가중 무작위10
    rnd_means = []
    for trial in range(RANDOM_TRIALS):
        rng = random.Random(2000 + trial)
        vals = []
        for sn in snaps:
            cand = [r for r in sn["rows"] if r["rets"].get(20) is not None]
            if len(cand) < TOP_N:
                continue
            v = topn_ret(sn["rows"], 20, "cap",
                         picker=lambda c, _r=rng: _r.sample(c, TOP_N))
            if v is not None:
                vals.append(v)
        if vals:
            rnd_means.append(st.mean(vals))
    score_vals = [topn_ret(sn["rows"], 20, "cap") for sn in snaps]
    score_vals = [v for v in score_vals if v is not None]
    if rnd_means and score_vals:
        rnd_means.sort()
        sm = st.mean(score_vals)
        diag["score_contribution_capw_20d"] = {
            "score_mean_pct": round(sm * 100, 4),
            "random_mean_pct": round(st.mean(rnd_means) * 100, 4),
            "random_p2_5_pct": round(rnd_means[int(len(rnd_means) * 0.025)] * 100, 4),
            "random_p97_5_pct": round(
                rnd_means[min(len(rnd_means) - 1, int(len(rnd_means) * 0.975))] * 100, 4),
            "beats_random_95": bool(
                sm > rnd_means[min(len(rnd_means) - 1, int(len(rnd_means) * 0.975))]),
            "note": "🚨 무작위 95% 상단을 못 넘으면 시총가중이 점수를 무력화한 것 (§4)"}
    # 4. 집행 가능성
    for w in ("equal", "cap"):
        over = []
        for sn in snaps:
            cand = [r for r in sn["rows"] if r["rets"].get(20) is not None and r.get("adv")]
            if len(cand) < TOP_N:
                continue
            sel = sorted(cand, key=lambda r: -r["score"])[:TOP_N]
            tot = sum(r["mktcap"] for r in sel) if w == "cap" else None
            c = 0
            for r in sel:
                amt = (ORDER_KRW * TOP_N * (r["mktcap"] / tot)) if w == "cap" else ORDER_KRW
                if r["adv"] and amt / r["adv"] > IMPACT_WARN:
                    c += 1
            over.append(c)
        diag[f"impact_over_{w}"] = round(st.mean(over), 2) if over else None

    doc = {
        "_meta": {
            "prereg": "docs/PREREG_SEGMENT_IC_2026_08_14.md",
            "approved": "PM 2026-08-14 'ㄱㄱ'",
            "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00",
                                         time.localtime(time.time() + 9 * 3600)),
            "tests": len(ledger), "adopt_t": ADOPT_T, "bonferroni": BONF8,
            "problem_restated": ("대형주는 이미 유니버스 안에 있다(삼성 1,534조·하이닉스 "
                                 "1,255조). 표적은 유니버스가 아니라 동일가중이다 (§0)"),
            "blocker": ("시총가중이 이겨도 진단 3(무작위와 무차별)이면 채택 불가 — "
                        "지수 추종을 자체 산식으로 위장하는 것 (§4)"),
            "scope": "진단이며 산식·운영 무변경",
        },
        "coverage": {"snapshots": len(snaps),
                     "window": [snaps[0]["as_of"], snaps[-1]["as_of"]],
                     "median_names": sorted(len(s["rows"]) for s in snaps)[len(snaps) // 2],
                     "elapsed_sec": round(time.time() - t0, 1)},
        "results": results,
        "diagnostics": diag,
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
        print("[segment] no_snapshots", file=sys.stderr)
        return 1
    c = r["coverage"]
    print(f"\n[segment] 단면 {c['snapshots']} · 중앙 종목수 {c['median_names']} · {c['elapsed_sec']}s")
    print(f"\n{'검정':22}{'IC/Δ':>10}{'t':>8}{'p':>9}{'BH':>6}{'t≥3':>6}   H1 → H2")
    for k in r["results"]:
        v = r["results"][k]
        s = v["split"]
        print(f"{k:22}{(v['nw'].get('mean') or 0):>10.4f}{(v['nw'].get('t') or 0):>8.2f}"
              f"{(v.get('p_two_sided') if v.get('p_two_sided') is not None else float('nan')):>9.4f}"
              f"{('통과' if v.get('passes_bh_fdr') else '—'):>6}"
              f"{('O' if v.get('passes_t3') else '—'):>6}   "
              f"{s['H1']['mean']} → {s['H2']['mean']}")
    d = r["diagnostics"]
    print(f"\n[진단] 세그먼트 수익(20d,%): " + " · ".join(
        f"{s} {d[f'seg_return_{s}_20d_pct']}" for s in SEGMENTS))
    print(f"       시총가중 집중도: 최대단일 {d['capw_concentration']['max_single_mean']} "
          f"· 상위3합 {d['capw_concentration']['top3_sum_mean']} "
          f"· 60%초과 {d['capw_concentration']['over_60pct_rebalances']}/{c['snapshots']} 리밸")
    sc = d.get("score_contribution_capw_20d") or {}
    print(f"       🚨 점수 기여: 시총가중 점수 {sc.get('score_mean_pct')}% vs "
          f"무작위 {sc.get('random_mean_pct')}% (95% {sc.get('random_p2_5_pct')}~"
          f"{sc.get('random_p97_5_pct')}) → 무작위 초과 {sc.get('beats_random_95')}")
    print(f"       주문/ADV>5% 종목수: 동일가중 {d.get('impact_over_equal')} "
          f"· 시총가중 {d.get('impact_over_cap')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
