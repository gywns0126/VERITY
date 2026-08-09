# -*- coding: utf-8 -*-
"""사전등록 §6 의무 진단 — "BH 통과 + 방향 반대" 시 분위 절단 artifact 여부.

🚨 새 가설 검정이 아니다. §6 이 명시적으로 요구한 진단이며, 추정 결과(이미 확정)는
   건드리지 않는다. 산출물도 별도 파일이다.
"""
import bisect, json, os, sys
sys.path.insert(0, ".")
from api.quant.backtest.kr_safety_score import (
    AXES, DELIST_PATH, ENTRY_LAG, HORIZONS, MIN_VALID, N_QUANTILE, PRIMARY_SCENARIO,
    _calendar, build_row, exclusion_reason, forward_return, load_names,
    load_ohlcv_duckdb, load_panel, load_universe,
)

px = load_ohlcv_duckdb(os.path.expanduser("~/VERITY_data_lake/kr_prices.duckdb"))
panel, universe, names = load_panel(), load_universe(), load_names()
try:
    dl = json.load(open(DELIST_PATH, encoding="utf-8")) or {}
    gone = {t for t, v in (dl.get("last_seen") or {}).items() if str(v) != str(dl.get("as_of"))}
except Exception:
    gone = set()

cal = _calendar({t: {"d": s["d"], "c": s["c"]} for t, s in px.items()})
rebs = []
for as_of, tickers in universe:
    k = bisect.bisect_right(cal, int(as_of)) - 1
    if k < 0 or k + ENTRY_LAG + max(HORIZONS) >= len(cal):
        continue
    rows = []
    for t in tickers:
        if exclusion_reason(t, names.get(t)):
            continue
        s = px.get(t)
        if not s:
            continue
        i = bisect.bisect_right(s["d"], cal[k]) - 1
        if i < 0 or s["d"][i] != cal[k]:
            continue
        rec = build_row(t, s, i, panel, cal[k])
        if not rec:
            continue
        ok = False
        for h in HORIZONS:
            r = forward_return(s, cal[k + ENTRY_LAG], cal[k + ENTRY_LAG + h],
                               delisted=(t in gone), haircut=(PRIMARY_SCENARIO == "conservative"))
            if r is not None:
                rec[f"r{h}"] = r[0]; ok = True
        if ok:
            rows.append(rec)
    if len(rows) >= MIN_VALID:
        rebs.append(rows)

out = {"_note": "사전등록 §6 의무 진단. 추정 결과 재산출 아님.",
       "rebalances": len(rebs), "n_quantile": N_QUANTILE, "scenario": PRIMARY_SCENARIO,
       "axes": {}}
for axis in AXES:
    vals_all = [r[axis] for rows in rebs for r in rows if r.get(axis) is not None]
    distinct = sorted(set(vals_all))
    # 값별 점유율 — 동점이 많으면 분위 경계가 동점 안에서 임의로 잘린다
    share = {str(v): round(sum(1 for x in vals_all if x == v) / len(vals_all), 4)
             for v in distinct} if len(distinct) <= 24 else "연속(24 초과)"
    prof = {}
    for h in HORIZONS:
        # 리밸런스별 5분위 평균 → 시점 평균 (단면 내 분위, 시계열 평균)
        acc = [[] for _ in range(N_QUANTILE)]
        for rows in rebs:
            pair = [(r[axis], r[f"r{h}"]) for r in rows
                    if r.get(axis) is not None and r.get(f"r{h}") is not None]
            if len(pair) < MIN_VALID:
                continue
            pair.sort(key=lambda p: p[0])
            kq = len(pair) // N_QUANTILE
            for q in range(N_QUANTILE):
                seg = pair[q * kq:(q + 1) * kq] if q < N_QUANTILE - 1 else pair[q * kq:]
                if seg:
                    acc[q].append(sum(p[1] for p in seg) / len(seg))
        means = [round(sum(a) / len(a) * 100, 3) if a else None for a in acc]
        # 분위별 점수 범위 — 동점 절단이면 인접 분위 범위가 겹친다
        rng = [[] for _ in range(N_QUANTILE)]
        for rows in rebs:
            v = sorted(r[axis] for r in rows if r.get(axis) is not None)
            if len(v) < MIN_VALID:
                continue
            kq = len(v) // N_QUANTILE
            for q in range(N_QUANTILE):
                seg = v[q * kq:(q + 1) * kq] if q < N_QUANTILE - 1 else v[q * kq:]
                if seg:
                    rng[q].append((seg[0], seg[-1]))
        span = [[min(x[0] for x in r), max(x[1] for x in r)] if r else None for r in rng]
        ok_mono = all(means[i] is not None and means[i + 1] is not None
                      and means[i] >= means[i + 1] for i in range(N_QUANTILE - 1))
        out["axes"][f"{axis}_{h}d"] = {
            "quantile_mean_ret_pct": means,          # Q1(낮은 점수) → Q5(높은 점수)
            "quantile_score_span": span,
            "monotone_decreasing": ok_mono,
            "extreme_only": (means[0] is not None and means[-1] is not None
                             and abs(means[0] - means[-1]) > 0
                             and abs(means[1] - means[-2]) / max(abs(means[0] - means[-1]), 1e-9) < 0.25),
        }
    out["axes"][axis + "_values"] = {"distinct": distinct if len(distinct) <= 24 else len(distinct),
                                     "share": share, "n": len(vals_all)}
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), "data", "analysis",
    "prereg_safety_score_20260809_diagnosis.json")
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("리밸런스", len(rebs))
for axis in ("safety_partial", "drop", "trading_value", "debt", "op_margin", "roe"):
    v = out["axes"][axis + "_values"]
    print(f"\n== {axis} · 고유값 {v['distinct'] if isinstance(v['distinct'],int) else v['distinct']}")
    if isinstance(v["share"], dict):
        print("   점유율", {k: f"{x:.1%}" for k, x in list(v["share"].items())})
    for h in HORIZONS:
        d = out["axes"][f"{axis}_{h}d"]
        print(f"   {h}d Q1→Q5 수익률%: {d['quantile_mean_ret_pct']}  단조↓={d['monotone_decreasing']}  극단만={d['extreme_only']}")
        print(f"        분위 점수범위: {d['quantile_score_span']}")
