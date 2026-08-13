# -*- coding: utf-8 -*-
"""kr_transfer_diagnosis — 단면 IC 가 포트폴리오로 전이되지 않는 원인 분해.

사전등록 `docs/PREREG_TRANSFER_DIAGNOSIS_2026_08_14.md` · PM 승인 2026-08-14 "ㄱㄱ".
🚨 **진단이지 처방이 아니다.** 산식·운영 무변경 (§5). 실행 1회 소진.

표적 = H2 붕괴. 8/13 포트폴리오 백테스트에서 6칸 전부 반쪽 초과수익 부호가 뒤집혔다
(H1 +0.03~+0.80%/월 → H2 −1.80~−2.13%/월). 같은 점수의 단면 IC 는 #355 에서 H2 가
**더 강했다** — 순위력은 커졌는데 포트폴리오 수익이 뒤집힌 이 모순이 표적이다.

원장 3검정 (§3-1 확정 — 상폐는 미래정보라 강등, 거래정지는 플래그 부재로 미측정):
  1. 상위 10 의 20일 평균 거래대금 중앙값(로그)  H2 − H1   방향 (−) 예상 · H-C
  2. 상위 10 의 시가총액 중앙값(로그)            H2 − H1   방향 (−) 예상 · H-A/H-B
  3. 분위 스프레드 − 상위10 초과수익             H2 − H1   방향 (+) 예상 · H-A
판정 = NW t → BH-FDR q=.05 · 참고 Bonferroni 2.39.
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
from api.quant.backtest.kr_price_axes import ENTRY_LAG, forward_return  # noqa: E402
from api.quant.backtest.kr_safety_score import (  # noqa: E402
    MIN_VALID, N_QUANTILE, bh_fdr, load_ohlcv_duckdb, load_panel, nw_lag,
    nw_t, pit_panel, two_sided_p,
)
from api.quant.backtest.kr_safety_score_full import (  # noqa: E402
    _pit_pair, load_op_margin, load_valuation,
)
from api.quant.backtest.kr_formula_rebuild import pct_rank  # noqa: E402

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "data")
OUT_PATH = os.path.join(_DATA, "analysis", "prereg_transfer_diagnosis_20260814.json")

# ── 등록값 (§3·§4) — 코드 상수와 사전 대조 완료 ─────────────────────────────
TOP_N = 10                     # 판정용 고정 (§3)
LADDER_N = (10, 30, 50, 100)   # §4-1 진단
SPLIT_BOUNDARY = 20230301
HORIZON = 20                   # 초과수익 호라이즌 (8/13 N10_H20 정합)
BONF3 = 2.39
ORDER_KRW = 2_000_000          # §4-3 집행 가능성 (max_per_stock)
IMPACT_WARN = 0.05             # 주문/ADV 5%
C3_AXES = ("ep", "bp", "dy", "opm", "roa", "vol", "fs8", "illiq", "nearhigh")


def build_cross_sections(lake: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[int]]:
    """리밸런스별 C3 점수 + 진단 원자료(거래대금·시총·수익률). #355 와 같은 점수 정의."""
    universe, names = load_universe(), load_names()
    px = load_ohlcv_duckdb(lake)
    panel, val, opm_hist = load_panel(), load_valuation(), load_op_margin()
    from api.quant.backtest.kr_fundamental import axis_fscore8
    from api.quant.factors.volatility import (_compute_vols_from_history,
                                              compute_volatility_score)
    cal = _calendar({t: {"d": s["d"], "c": s["c"]} for t, s in px.items()})
    try:
        dl = json.load(open(DELIST_PATH, encoding="utf-8")) or {}
        latest = str(dl.get("as_of"))
        gone = {t for t, v in (dl.get("last_seen") or {}).items() if str(v) != latest}
    except (OSError, json.JSONDecodeError):
        gone = set()

    snaps: List[Dict[str, Any]] = []
    for as_of, tickers in universe:
        d = int(as_of)
        k = bisect.bisect_right(cal, d) - 1
        if k < 0 or k + ENTRY_LAG + HORIZON >= len(cal):
            continue
        sd, ed = cal[k], cal[k + ENTRY_LAG]
        xd = cal[k + ENTRY_LAG + HORIZON]
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
            fr = forward_return(s, ed, xd, delisted=(t in gone), haircut=True)
            raw.append({
                "t": t,
                "ep": (1.0 / per_v if isinstance(per_v, (int, float)) and per_v > 0 else None),
                "bp": (1.0 / pbr_v if isinstance(pbr_v, (int, float)) and pbr_v > 0 else None),
                "dy": dy, "opm": omv, "roa": (p.get("roa_ttm") if p else None),
                "fs8": (float(axis_fscore8(p, panel.get(t) or []))
                        if p and axis_fscore8(p, panel.get(t) or []) is not None else None),
                "_v20": v20, "_v60": v60, "_hist": hist,
                "illiq_raw": tv, "nearhigh_raw": drop,
                "adv": tv,                                 # 20일 평균 거래대금 (진단 원자료)
                "mktcap": (v.get("mktcap") if v.get("mktcap") else None),
                "ret": (fr[0] if fr else None),
                "delisted": 1 if t in gone else 0,
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
            if len(have) >= 5 and r.get("ret") is not None:
                rows.append({**r, "score": sum(have) / len(have),
                             "pct_ep": ranks["ep"].get(j), "pct_bp": ranks["bp"].get(j),
                             "pct_vol": ranks["vol"].get(j),
                             "pct_illiq": ranks["illiq"].get(j)})
        if len(rows) >= MIN_VALID:
            snaps.append({"as_of": d, "rows": rows})
        if len(snaps) % 20 == 0 and snaps:
            print(f"  단면 {len(snaps)} · {as_of}", flush=True)
    return snaps, px, cal


def run(lake: str, out_path: str = OUT_PATH, limit: int = 0) -> Dict[str, Any]:
    t0 = time.time()
    snaps, _px, _cal = build_cross_sections(lake)
    if limit:
        snaps = snaps[:limit]
    if not snaps:
        return {"status": "no_snapshots"}

    def half_of(as_of: int) -> str:
        return "H1" if as_of < SPLIT_BOUNDARY else "H2"

    # ── 리밸런스별 지표 ──
    per_reb: List[Dict[str, Any]] = []
    for sn in snaps:
        rows = sorted(sn["rows"], key=lambda r: -r["score"])
        top = rows[:TOP_N]
        adv = [r["adv"] for r in top if r.get("adv")]
        mc = [r["mktcap"] for r in top if r.get("mktcap")]
        # 분위 스프레드 (Q5 − Q1) vs 상위N 초과수익 — 전 분포 vs 꼬리
        srt = sorted(rows, key=lambda r: r["score"])
        kq = max(1, len(srt) // N_QUANTILE)
        q1 = st.mean(r["ret"] for r in srt[:kq])
        q5 = st.mean(r["ret"] for r in srt[-kq:])
        uni_mean = st.mean(r["ret"] for r in rows)
        topn_ex = st.mean(r["ret"] for r in top) - uni_mean
        per_reb.append({
            "as_of": sn["as_of"], "half": half_of(sn["as_of"]),
            "log_adv": (math.log(st.median(adv)) if adv else None),
            "log_mktcap": (math.log(st.median(mc)) if mc else None),
            "spread_minus_topn": (q5 - q1) - topn_ex,
            "topn_excess": topn_ex, "spread": q5 - q1,
            "delisted_rate": st.mean(r["delisted"] for r in top),
            "n_uni": len(rows),
            "pct_ep": st.mean([r["pct_ep"] for r in top if r.get("pct_ep") is not None] or [0]),
            "pct_bp": st.mean([r["pct_bp"] for r in top if r.get("pct_bp") is not None] or [0]),
            "pct_vol": st.mean([r["pct_vol"] for r in top if r.get("pct_vol") is not None] or [0]),
            "pct_illiq": st.mean([r["pct_illiq"] for r in top if r.get("pct_illiq") is not None] or [0]),
            "impact_over": sum(1 for r in top if r.get("adv") and ORDER_KRW / r["adv"] > IMPACT_WARN),
            "ladder": {n: (st.mean(r["ret"] for r in rows[:n]) - uni_mean)
                       for n in LADDER_N if len(rows) >= n},
        })

    # ── 원장 3검정 (H2 − H1 짝지음 = 두 표본 평균차의 NW t) ──
    def _test(field: str) -> Dict[str, Any]:
        h1 = [r[field] for r in per_reb if r["half"] == "H1" and r.get(field) is not None]
        h2 = [r[field] for r in per_reb if r["half"] == "H2" and r.get(field) is not None]
        if len(h1) < 3 or len(h2) < 3:
            return {"ok": None, "skipped": "표본 부족"}
        # 리밸런스는 시계열이므로 각 반쪽 시계열의 NW 평균·SE 로 차이 검정
        a, b = nw_t(h1, nw_lag(HORIZON)), nw_t(h2, nw_lag(HORIZON))
        sa = (abs(a["mean"] / a["t"]) if a.get("t") else None)
        sb = (abs(b["mean"] / b["t"]) if b.get("t") else None)
        if not sa or not sb:
            return {"ok": None, "skipped": "SE 산출 불가"}
        diff = b["mean"] - a["mean"]
        se = math.sqrt(sa ** 2 + sb ** 2)
        t = diff / se if se > 0 else None
        return {"h1_mean": round(a["mean"], 6), "h2_mean": round(b["mean"], 6),
                "diff": round(diff, 6), "t": (round(t, 4) if t else None),
                "n_h1": len(h1), "n_h2": len(h2)}

    ledger = {"log_adv": "log_adv", "log_mktcap": "log_mktcap",
              "spread_minus_topn": "spread_minus_topn"}
    results = {k: _test(v) for k, v in ledger.items()}
    pv = [two_sided_p(results[k].get("t"),
                      min(results[k].get("n_h1", 0), results[k].get("n_h2", 0)))
          for k in ledger]
    for k, p_, ok in zip(ledger, pv, bh_fdr(pv, q=0.05)):
        results[k]["p_two_sided"] = round(p_, 6) if p_ is not None else None
        results[k]["passes_bh_fdr"] = ok
        results[k]["passes_bonferroni"] = bool(
            results[k].get("t") is not None and abs(results[k]["t"]) >= BONF3)

    # ── §4 진단 ──
    # 🚨 반쪽이 비어도 죽지 않는다 (smoke 가 잡음 — limit 실행/창 변경 시 H2 가 0건).
    #   빈 반쪽은 None 으로 신고한다. 지어내지 않는다.
    def _hmean(field: str, scale: float = 1.0, nd: int = 4) -> Dict[str, Optional[float]]:
        out: Dict[str, Optional[float]] = {}
        for k in ("H1", "H2"):
            v = [r[field] for r in per_reb if r["half"] == k and r.get(field) is not None]
            out[k] = round(st.mean(v) * scale, nd) if v else None
        return out

    diag: Dict[str, Any] = {}
    for n in LADDER_N:
        h = {"H1": [], "H2": []}
        for r in per_reb:
            if n in r["ladder"]:
                h[r["half"]].append(r["ladder"][n])
        diag[f"ladder_N{n}"] = {k: (round(st.mean(v) * 100, 4) if v else None)
                                for k, v in h.items()}
    for f in ("pct_ep", "pct_bp", "pct_vol", "pct_illiq"):
        diag[f"style_{f}"] = _hmean(f)
    diag["impact_over_5pct"] = _hmean("impact_over", nd=2)
    diag["delisted_rate_TOPN"] = _hmean("delisted_rate")
    diag["_delisted_note"] = ("🚨 미래 정보(as_of 기준 상폐 여부) — 판정 근거 아님, "
                              "H-C 정황 증거로만 (등록 §3-1)")
    diag["topn_excess_pct"] = _hmean("topn_excess", 100.0)
    diag["spread_pct"] = _hmean("spread", 100.0)

    doc = {
        "_meta": {
            "prereg": "docs/PREREG_TRANSFER_DIAGNOSIS_2026_08_14.md",
            "approved": "PM 2026-08-14 'ㄱㄱ'",
            "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00",
                                         time.localtime(time.time() + 9 * 3600)),
            "tests": len(ledger), "top_n": TOP_N, "horizon": HORIZON,
            "split_boundary": SPLIT_BOUNDARY,
            "expected_signs": {"log_adv": "-", "log_mktcap": "-",
                               "spread_minus_topn": "+"},
            "scope": "진단이지 처방이 아니다 — 산식·운영 무변경 (§5)",
            "not_measured": ["거래정지(플래그 부재)", "상폐(미래정보 — 기술통계로 강등)"],
        },
        "coverage": {"rebalances": len(per_reb),
                     "window": [per_reb[0]["as_of"], per_reb[-1]["as_of"]],
                     "h1": sum(1 for r in per_reb if r["half"] == "H1"),
                     "h2": sum(1 for r in per_reb if r["half"] == "H2"),
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
        print("[transfer] no_snapshots", file=sys.stderr)
        return 1
    c = r["coverage"]
    print(f"\n[transfer] 리밸런스 {c['rebalances']} (H1 {c['h1']} / H2 {c['h2']}) · {c['elapsed_sec']}s")
    print(f"\n{'검정':22}{'H1':>12}{'H2':>12}{'차이':>11}{'t':>8}{'BH':>6}")
    for k, v in r["results"].items():
        if v.get("t") is None:
            print(f"{k:22} {v.get('skipped')}")
            continue
        print(f"{k:22}{v['h1_mean']:>12.4f}{v['h2_mean']:>12.4f}{v['diff']:>11.4f}"
              f"{v['t']:>8.2f}{('통과' if v.get('passes_bh_fdr') else '—'):>6}")
    d = r["diagnostics"]
    print(f"\n[진단] 상위{TOP_N} 초과수익%: {d['topn_excess_pct']} · 분위스프레드%: {d['spread_pct']}")
    print(f"       N 사다리 초과%: " + " · ".join(
        f"N{n} {d[f'ladder_N{n}']}" for n in LADDER_N if f"ladder_N{n}" in d))
    print(f"       스타일 백분위: EP {d['style_pct_ep']} · BP {d['style_pct_bp']} "
          f"· VOL {d['style_pct_vol']} · ILLIQ {d['style_pct_illiq']}")
    print(f"       주문/ADV>5% 종목수: {d['impact_over_5pct']} · 상폐율(정황) {d['delisted_rate_TOPN']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
