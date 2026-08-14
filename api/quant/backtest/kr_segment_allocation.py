# -*- coding: utf-8 -*-
"""kr_segment_allocation — 세그먼트 배분 검정 (A0/A1/A2).

사전등록 `docs/PREREG_SEGMENT_ALLOCATION_2026_08_14.md` · PM 승인 2026-08-14 "ㄱㄱ".
🚨 관측 산출물만. **실행 1회 소진.** 이 등록으로 운영을 바꾸지 않는다 (§4).

선행 #366 R-3 이 표적을 좁혔다: 점수는 전 세그먼트에서 유효했고(6/6 BH 통과) 시총가중은
점수를 무력화했다(무작위 무차별). 남은 것이 **세그먼트 배분**이다.

🚨 §0 — 이 등록이 곡선 맞추기 최적 지점이다. 세그먼트 수익 표(H1 소형 우세 / H2 대형
   우세)를 이미 봤기 때문이다. 그래서 **적합 파라미터 0** 이 유일한 방어다:
   룩백 창·전환 임계·가중치 등 데이터에서 고르는 수를 하나도 만들지 않는다.
   역변동성(룩백 창 = 파라미터)·레짐 스위칭(전환 임계 = 파라미터)은 등록에서 제외했다.

후보 3 — 배분 하나만 다르고 점수·종목수·비용·창은 전부 동일 (배분 효과 격리):
  A0 현행   세그먼트 무시 · 전 유니버스 상위 12          (기준선)
  A1 중립   대/중/소 1:1:1 고정 · 각 세그먼트 내 상위 4  (세그먼트 베팅을 하지 않는 선택)
  A2 상속   세그먼트 PIT 시총 비중 · 비중 비례 종목수     (지수 배분 상속 · 배분 판단 0)

원장 6검정 = {A1−A0, A2−A0, A1−A2} × {20d, 60d} · 월간 NW t → BH-FDR q=.05 ·
채택 주장 |t| ≥ 3.0 · 참고 Bonferroni 2.64 · **방향 사전 고정 없음**.
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
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

from api.quant.backtest import kr_portfolio as kp  # noqa: E402
from api.quant.backtest.kr_fundamental import (  # noqa: E402
    DELIST_PATH, _calendar, exclusion_reason, load_names, load_universe,
)
from api.quant.backtest.kr_price_axes import ENTRY_LAG  # noqa: E402
from api.quant.backtest.kr_safety_score import (  # noqa: E402
    MIN_VALID, bh_fdr, load_ohlcv_duckdb, load_panel, pit_panel, nw_t, two_sided_p,
)
from api.quant.backtest.kr_safety_score_full import (  # noqa: E402
    _pit_pair, load_op_margin, load_valuation,
)
from api.quant.backtest.kr_formula_rebuild import pct_rank  # noqa: E402
from api.quant.backtest.kr_transfer_diagnosis import C3_AXES  # noqa: E402

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))), "data")
OUT_PATH = os.path.join(_DATA, "analysis", "prereg_segment_allocation_20260814.json")

# ── 등록값 (§1·§2·§3·§4) ────────────────────────────────────────────────────
VARIANTS = ("A0", "A1", "A2")
SEGMENTS = ("large", "mid", "small")
N_HOLD = 12                      # 3의 배수 — 세그먼트 균등 분할 가능 (§1)
GRID_H = (20, 60)
SPLIT_BOUNDARY = 20230301
ADOPT_T = 3.0
BONF6 = 2.64
RANDOM_TRIALS = 20
M_TRIALS = 84                    # DSR 누적 시도 (78 + 본건 6)
ORDER_KRW = 2_000_000
IMPACT_WARN = 0.05


# ── 배분 = 종목수 배정. 전부 파라미터 0 ────────────────────────────────────
def _hamilton(shares: Sequence[float], n: int) -> List[int]:
    """비중 → 정수 종목수 (최대잔여법). 반올림 규칙이지 적합 파라미터가 아니다."""
    raw = [max(0.0, s) * n for s in shares]
    base = [int(math.floor(x)) for x in raw]
    rest = n - sum(base)
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - base[i]), i))
    for i in order[:max(0, rest)]:
        base[i] += 1
    return base


def _top_by_seg(rows: List[Dict[str, Any]], counts: Dict[str, int],
                rng: Optional[random.Random] = None) -> List[str]:
    """세그먼트별 배정 수만큼 선택. rng 가 있으면 점수 대신 무작위 (진단 3용).

    배정분이 세그먼트 종목수를 넘으면 가용분만 — 잔여는 채우지 않는다
    (다른 세그먼트로 흘리면 그 순간 배분이 데이터에 반응하는 규칙이 된다).
    """
    out: List[str] = []
    for seg in SEGMENTS:
        k = counts.get(seg, 0)
        if k <= 0:
            continue
        sub = [r for r in rows if r["seg"] == seg]
        if not sub:
            continue
        if rng is not None:
            out += [r["t"] for r in rng.sample(sub, min(k, len(sub)))]
        else:
            out += [r["t"] for r in sorted(sub, key=lambda z: -z["score"])[:k]]
    return out


def _cap_shares(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    """세그먼트 PIT 시총 비중 (유니버스 전체 기준)."""
    tot = sum(r["mktcap"] for r in rows) or 1.0
    return {seg: sum(r["mktcap"] for r in rows if r["seg"] == seg) / tot
            for seg in SEGMENTS}


def pick_a0(rows: List[Dict[str, Any]], n: int) -> List[str]:
    return [r["t"] for r in sorted(rows, key=lambda z: -z["score"])[:n]]


def pick_a1(rows: List[Dict[str, Any]], n: int) -> List[str]:
    per = n // len(SEGMENTS)
    return _top_by_seg(rows, {seg: per for seg in SEGMENTS})


def a2_counts(rows: List[Dict[str, Any]], n: int) -> Dict[str, int]:
    sh = _cap_shares(rows)
    c = _hamilton([sh[s] for s in SEGMENTS], n)
    return dict(zip(SEGMENTS, c))


def pick_a2(rows: List[Dict[str, Any]], n: int) -> List[str]:
    return _top_by_seg(rows, a2_counts(rows, n))


PICKERS = {"A0": pick_a0, "A1": pick_a1, "A2": pick_a2}


# ── 단면 구축 ───────────────────────────────────────────────────────────────
def build(lake: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[int], set, Dict[str, int]]:
    """리밸런스별 C3 점수 + PIT 시총 + 세그먼트 + 달력 인덱스.

    점수 정의 = #355 재구축 그대로 (재선택·재탐색 0) · 세그먼트 = 시총 3분위(#366 상속).
    🚨 시총 결측 종목은 세그먼트 분할이 불가하므로 제외하고 건수를 신고한다.
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
    drop = {"no_mktcap": 0, "kept": 0}
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
            v = vrow.get(t) or {}
            mc = v.get("mktcap")
            if not mc:
                drop["no_mktcap"] += 1
                continue
            hist = close[max(0, i - 251):i + 1]
            hi52 = max(hist)
            near = ((pxc - hi52) / hi52 * 100) if hi52 > 0 else None
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
            raw.append({
                "t": t, "mktcap": float(mc), "adv": tv,
                "ep": (1.0 / per_v if isinstance(per_v, (int, float)) and per_v > 0 else None),
                "bp": (1.0 / pbr_v if isinstance(pbr_v, (int, float)) and pbr_v > 0 else None),
                "dy": dy, "opm": omv, "roa": (p.get("roa_ttm") if p else None),
                "fs8": (lambda x: float(x) if x is not None else None)(
                    axis_fscore8(p, panel.get(t) or []) if p else None),
                "_v20": v20, "_v60": v60, "_hist": hist,
                "illiq_raw": tv, "nearhigh_raw": near,
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
                rows.append({"t": r["t"], "score": sum(have) / len(have),
                             "mktcap": r["mktcap"], "adv": r["adv"]})
        if len(rows) < MIN_VALID:
            continue
        rows.sort(key=lambda r: r["mktcap"])          # 시총 3분위 (동일 종목수 · PIT)
        n = len(rows)
        for idx, r in enumerate(rows):
            r["seg"] = ("small" if idx < n // 3 else
                        ("mid" if idx < 2 * n // 3 else "large"))
        drop["kept"] += len(rows)
        snaps.append({"as_of": d, "cal_idx": k, "rows": rows})
        if len(snaps) % 20 == 0:
            print(f"  단면 {len(snaps)} · {as_of}", flush=True)
    return snaps, px, cal, gone, drop


# ── 수익 계열 ───────────────────────────────────────────────────────────────
def _reb_slice(snaps: List[Dict[str, Any]], h: int) -> List[Dict[str, Any]]:
    """kp._daily_curve 와 **같은** 리밸런스 추출 규칙 (실비중 집계를 곡선과 맞추기 위함)."""
    if h == 20:
        return list(snaps)
    step = max(1, round(h / 20))
    return [s for i, s in enumerate(snaps) if i % step == 0]


def _monthly(days: Sequence[int], vals: Sequence[float]) -> Dict[int, float]:
    out: Dict[int, float] = {}
    for d, v in zip(days, vals):
        k = d // 100
        out[k] = (1 + out.get(k, 0.0)) * (1 + v) - 1
    return out


def _bench_daily(days: Sequence[int], kospi: Dict[int, float]) -> List[float]:
    out: List[float] = []
    ks = sorted(kospi)
    for i, d in enumerate(days):
        j = bisect.bisect_right(ks, d) - 1
        j0 = bisect.bisect_right(ks, days[i - 1]) - 1 if i else j - 1
        out.append(0.0 if (j <= 0 or j0 < 0 or j == j0)
                   else kospi[ks[j]] / kospi[ks[j0]] - 1.0)
    return out


def _curve(snaps, px, cal, gone, kospi, h: int, picker) -> Dict[str, Any]:
    """일별 마크투마켓 곡선 + 월간 초과수익. 회계·비용은 kp._daily_curve 그대로 재사용."""
    days, rets, meta = kp._daily_curve(snaps, px, cal, N_HOLD, h, gone, picker=picker)
    if not days:
        return {"empty": True}
    b = _bench_daily(days, kospi)
    ex_daily = [r - bb for r, bb in zip(rets, b)]
    return {
        "days": days, "rets": rets, "meta": meta,
        "monthly_excess": _monthly(days, ex_daily),
        "metrics": kp._metrics(rets, days),
        "excess_total_pct": round((math.prod(1 + e for e in ex_daily) - 1) * 100, 2),
    }


def _half(mkey: int) -> str:
    return "H1" if mkey * 100 < SPLIT_BOUNDARY else "H2"


def _split_stats(monthly: Dict[int, float]) -> Dict[str, Any]:
    hv: Dict[str, List[float]] = {"H1": [], "H2": []}
    for k in sorted(monthly):
        hv[_half(k)].append(monthly[k])
    return {k: {"n": len(v), "mean": (round(st.mean(v), 6) if v else None),
                "sign_pos": (st.mean(v) > 0 if v else None)} for k, v in hv.items()}


def _diff_series(a: Dict[int, float], b: Dict[int, float]) -> Tuple[List[float], List[int]]:
    keys = sorted(set(a) & set(b))
    return [a[k] - b[k] for k in keys], keys


def _seg_weights(snaps, h: int, picker) -> Dict[str, Any]:
    """실현 세그먼트 비중 = 리밸런스별 세그먼트 종목수 비율의 평균 (동일가중이므로 = 자본비중)."""
    acc = {seg: [] for seg in SEGMENTS}
    for sn in _reb_slice(snaps, h):
        held = set(picker(sn["rows"], N_HOLD))
        if not held:
            continue
        cnt = {seg: 0 for seg in SEGMENTS}
        for r in sn["rows"]:
            if r["t"] in held:
                cnt[r["seg"]] += 1
        tot = sum(cnt.values()) or 1
        for seg in SEGMENTS:
            acc[seg].append(cnt[seg] / tot)
    return {seg: (round(st.mean(v), 4) if v else None) for seg, v in acc.items()}


def _impact(snaps, h: int, picker) -> Optional[float]:
    """주문 200만원 기준 ADV 5% 초과 종목수 (리밸런스 평균)."""
    over = []
    for sn in _reb_slice(snaps, h):
        held = set(picker(sn["rows"], N_HOLD))
        if not held:
            continue
        c = 0
        for r in sn["rows"]:
            if r["t"] in held and r.get("adv") and ORDER_KRW / r["adv"] > IMPACT_WARN:
                c += 1
        over.append(c)
    return round(st.mean(over), 2) if over else None


def _rand_weights(rng: random.Random) -> List[float]:
    """단체(simplex) 균등 추출 — Dirichlet(1,1,1). 파라미터 없음."""
    e = [-math.log(max(1e-12, rng.random())) for _ in SEGMENTS]
    s = sum(e) or 1.0
    return [x / s for x in e]


def _pct(vals: List[float], q: float) -> float:
    v = sorted(vals)
    return v[min(len(v) - 1, max(0, int(len(v) * q)))]


def run(lake: str, out_path: str = OUT_PATH, limit: int = 0) -> Dict[str, Any]:
    t0 = time.time()
    snaps, px, cal, gone, drop = build(lake)
    if limit:
        snaps = snaps[:limit]
    if not snaps:
        return {"status": "no_snapshots"}
    kospi = kp._load_kospi()

    # ── 후보 3 × 창 2 ──
    curves: Dict[str, Dict[int, Dict[str, Any]]] = {}
    for v in VARIANTS:
        curves[v] = {}
        for h in GRID_H:
            c = _curve(snaps, px, cal, gone, kospi, h, PICKERS[v])
            if c.get("empty"):               # 조용히 넘기면 결손이 판정에 섞인다
                return {"status": "empty_curve", "variant": v, "horizon": h}
            curves[v][h] = c

    descriptive: Dict[str, Any] = {}
    for v in VARIANTS:
        for h in GRID_H:
            c = curves[v][h]
            descriptive[f"{v}_H{h}"] = {
                **c["metrics"], **c["meta"],
                "excess_total_pct": c["excess_total_pct"],
                "excess_monthly_mean_pct": round(
                    st.mean(c["monthly_excess"].values()) * 100, 4),
                "seg_weights": _seg_weights(snaps, h, PICKERS[v]),
                "split_excess": _split_stats(c["monthly_excess"]),
            }

    # ── 원장 6검정 (§2) ──
    ledger = [(a, b, h) for a, b in (("A1", "A0"), ("A2", "A0"), ("A1", "A2"))
              for h in GRID_H]
    results: Dict[str, Any] = {}
    keys: List[str] = []
    for a, b, h in ledger:
        key = f"{a}_minus_{b}_{h}d"
        keys.append(key)
        ser, mk = _diff_series(curves[a][h]["monthly_excess"], curves[b][h]["monthly_excess"])
        lag = 1 if h <= 20 else 3            # 월간 계열 환산 (kp 와 동일)
        hv: Dict[str, List[float]] = {"H1": [], "H2": []}
        for k, x in zip(mk, ser):
            hv[_half(k)].append(x)
        results[key] = {
            "nw": nw_t(ser, lag), "n_months": len(ser),
            "mean_pct": round(st.mean(ser) * 100, 4) if ser else None,
            "split": {k: {"n": len(x), "mean_pct": (round(st.mean(x) * 100, 4) if x else None)}
                      for k, x in hv.items()},
        }
    pv = [two_sided_p(results[k]["nw"].get("t"), results[k]["nw"].get("n")) for k in keys]
    for k, p_, ok in zip(keys, pv, bh_fdr(pv, q=0.05)):
        results[k]["p_two_sided"] = round(p_, 6) if p_ is not None else None
        results[k]["passes_bh_fdr"] = ok
        results[k]["passes_t3"] = bool(results[k]["nw"].get("t") is not None
                                       and abs(results[k]["nw"]["t"]) >= ADOPT_T)

    # ── 의무 진단 4종 (§3) ──
    diag: Dict[str, Any] = {}
    # 1. 반쪽 안정성 — 각 안의 H1/H2 초과수익 (레짐 베팅 차단)
    diag["half_stability"] = {
        f"{v}_H{h}": descriptive[f"{v}_H{h}"]["split_excess"]
        for v in VARIANTS for h in GRID_H}

    # 2. 무작위 배분 벤치 — 배분만 무작위, 종목 선택은 점수 유지
    rand_alloc: Dict[str, Any] = {}
    for h in GRID_H:
        means, calmars = [], []
        for trial in range(RANDOM_TRIALS):
            rng = random.Random(3000 + trial)
            w = _rand_weights(rng)

            def rpick(rows, n, _w=w):
                return _top_by_seg(rows, dict(zip(SEGMENTS, _hamilton(_w, n))))
            c = _curve(snaps, px, cal, gone, kospi, h, rpick)
            if c.get("empty"):
                continue
            means.append(st.mean(c["monthly_excess"].values()))
            if c["metrics"].get("calmar") is not None:
                calmars.append(c["metrics"]["calmar"])
        if means:
            rand_alloc[f"H{h}"] = {
                "trials": len(means),
                "excess_mean_pct": round(st.mean(means) * 100, 4),
                "excess_p2_5_pct": round(_pct(means, 0.025) * 100, 4),
                "excess_p97_5_pct": round(_pct(means, 0.975) * 100, 4),
                "calmar_mean": (round(st.mean(calmars), 3) if calmars else None),
                "calmar_p97_5": (round(_pct(calmars, 0.975), 3) if calmars else None),
                "note": "배분만 무작위 · 종목 선택은 점수 유지. 후보가 95% 상단을 못 넘으면 배분 효과 아님",
            }
    diag["random_allocation_bench"] = rand_alloc

    # 3. 🚨 A2 점수 무력화 검사 — A2 배분 + 무작위 종목 (#366 과 같은 함정 검사)
    a2_null: Dict[str, Any] = {}
    for h in GRID_H:
        means = []
        for trial in range(RANDOM_TRIALS):
            rng = random.Random(4000 + trial)

            def npick(rows, n, _r=rng):
                return _top_by_seg(rows, a2_counts(rows, n), rng=_r)
            c = _curve(snaps, px, cal, gone, kospi, h, npick)
            if not c.get("empty"):
                means.append(st.mean(c["monthly_excess"].values()))
        if means:
            a2m = st.mean(curves["A2"][h]["monthly_excess"].values())
            a2_null[f"H{h}"] = {
                "a2_excess_mean_pct": round(a2m * 100, 4),
                "random_pick_mean_pct": round(st.mean(means) * 100, 4),
                "random_p97_5_pct": round(_pct(means, 0.975) * 100, 4),
                "beats_random_95": bool(a2m > _pct(means, 0.975)),
                "note": "🚨 무작위 종목과 무차별이면 A2 는 지수 배분 추종일 뿐 (§4-6)",
            }
    diag["a2_score_nullification"] = a2_null

    # 4. 집중도·집행
    diag["concentration_impact"] = {
        f"{v}_H{h}": {
            "max_single_weight": round(1.0 / N_HOLD, 4),   # 세 안 모두 동일가중 12종
            "seg_weights": descriptive[f"{v}_H{h}"]["seg_weights"],
            "orders_over_adv5pct": _impact(snaps, h, PICKERS[v]),
        } for v in VARIANTS for h in GRID_H}

    # ── §4 채택 규칙 (계산 전 고정) ──
    adoption: Dict[str, Any] = {}
    passing: List[str] = []
    for cand in ("A1", "A2"):
        for h in GRID_H:
            key = f"{cand}_H{h}"
            tkey = f"{cand}_minus_A0_{h}d"
            r = results[tkey]
            m = descriptive[key]
            m0 = descriptive[f"A0_H{h}"]
            ex_mean = st.mean(curves[cand][h]["monthly_excess"].values())
            rb = rand_alloc.get(f"H{h}") or {}
            cond = {
                "bh": bool(r.get("passes_bh_fdr")),
                "t3": bool(r.get("passes_t3")),
                "calmar_ge_a0": bool((m.get("calmar") if m.get("calmar") is not None else -9)
                                     >= (m0.get("calmar") if m0.get("calmar") is not None else 9)),
                "mdd_not_worse": bool((m.get("mdd") if m.get("mdd") is not None else -9)
                                      >= (m0.get("mdd") if m0.get("mdd") is not None else 9)),
                "split_both_pos": all(
                    m["split_excess"][hh]["sign_pos"] is True for hh in ("H1", "H2")),
                "beats_random_alloc": bool(
                    rb and ex_mean * 100 > (rb.get("excess_p97_5_pct") or 9e9)),
            }
            if cand == "A2":
                cond["a2_not_nullified"] = bool(
                    (a2_null.get(f"H{h}") or {}).get("beats_random_95"))
            cond["all_pass"] = all(cond.values())
            adoption[key] = cond
            if cond["all_pass"]:
                passing.append(key)
    ref = None
    if passing:
        # 복수 충족 → A1 우선 (배분 판단을 하지 않는 쪽 = 더 적은 주장), 그다음 H 최대
        ref = sorted(passing, key=lambda k: (0 if k.startswith("A1") else 1,
                                             -int(k.split("_H")[1])))[0]
    adoption["reference_config"] = ref
    adoption["rule"] = ("전 조건 충족자 중 A1 우선(더 적은 주장) · 그다음 H 최대. "
                        "전원 미충족 = 참조 등록 없음 — '배분으로 해결되지 않음' 으로 기록하고 "
                        "남은 선택지는 중립화(롱숏) 또는 지수 인정 (§4)")

    doc = {
        "_meta": {
            "prereg": "docs/PREREG_SEGMENT_ALLOCATION_2026_08_14.md",
            "approved": "PM 2026-08-14 'ㄱㄱ' (§6 4건)",
            "executed_at": time.strftime("%Y-%m-%dT%H:%M:%S+09:00",
                                         time.localtime(time.time() + 9 * 3600)),
            "tests": len(keys), "adopt_t": ADOPT_T, "bonferroni": BONF6,
            "dsr_m_trials": M_TRIALS,
            "n_hold": N_HOLD, "roundtrip_cost_pct": round(kp.ROUNDTRIP * 100, 3),
            "curve_fit_guard": ("적합 파라미터 0 — 세그먼트 수익 표를 배분 결정에 쓰지 않았다. "
                                "역변동성(룩백 창)·레짐 스위칭(전환 임계)은 등록 제외 (§0·§5)"),
            "direction": "사전 고정 없음 (배분 우열에 대한 사전 근거가 없다)",
            "dependence_note": ("검정 5·6(A1−A2)은 1~4의 선형결합이다 — 6검정은 독립이 아니다. "
                                "BH 는 양의 의존(PRDS) 가정에서 FDR 을 통제하므로 이 구조에서 "
                                "낙관적일 수 있다. 채택 주장은 |t|≥3.0 을 별도로 요구한다"),
            "scope": "이 등록으로 운영을 바꾸지 않는다. 컷오버는 별도 승인 (§4)",
            "not_reproduced": ["손절·트레일링·기간손절", "Kelly/섹터/베타 가드",
                               "배당(가격 수익률만)", "시장충격"],
            "in_sample_caveat": "C3 축 선택이 같은 창(#355 §1) — 선택 편향 상속",
        },
        "coverage": {
            "snapshots": len(snaps),
            "window": [snaps[0]["as_of"], snaps[-1]["as_of"]],
            "median_names": sorted(len(s["rows"]) for s in snaps)[len(snaps) // 2],
            "rows_kept": drop["kept"], "dropped_no_mktcap": drop["no_mktcap"],
            "kospi_days": len(kospi),
            "elapsed_sec": round(time.time() - t0, 1),
        },
        "descriptive": descriptive,
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
    ap.add_argument("--out", default=OUT_PATH)
    a = ap.parse_args()
    r = run(a.lake, out_path=a.out, limit=a.limit)
    if r.get("status") == "no_snapshots":
        print("[seg_alloc] no_snapshots", file=sys.stderr)
        return 1
    c = r["coverage"]
    print(f"\n[seg_alloc] 단면 {c['snapshots']} · 중앙 종목수 {c['median_names']} · "
          f"시총결측 제외 {c['dropped_no_mktcap']} · {c['elapsed_sec']}s")
    print(f"\n{'구성':10}{'CAGR%':>8}{'MDD':>8}{'Calmar':>8}{'Sharpe':>8}{'초과%':>9}"
          f"{'회전':>7}   세그먼트 실비중(대/중/소)")
    for v in VARIANTS:
        for h in GRID_H:
            d = r["descriptive"][f"{v}_H{h}"]
            w = d["seg_weights"]
            print(f"{v}_H{h:<7}{(d.get('cagr_pct') or 0):>8.2f}{(d.get('mdd') or 0):>8.3f}"
                  f"{(d.get('calmar') or 0):>8.2f}{(d.get('sharpe') or 0):>8.2f}"
                  f"{(d.get('excess_total_pct') or 0):>9.1f}"
                  f"{d.get('turnover_per_reb', 0):>7.2f}   "
                  f"{w['large']} / {w['mid']} / {w['small']}")
    print(f"\n{'검정':22}{'평균%':>9}{'t':>8}{'p':>9}{'BH':>6}{'t≥3':>6}   H1 → H2 (%)")
    for k in r["results"]:
        v = r["results"][k]
        s = v["split"]
        print(f"{k:22}{(v.get('mean_pct') or 0):>9.4f}{(v['nw'].get('t') or 0):>8.2f}"
              f"{(v.get('p_two_sided') if v.get('p_two_sided') is not None else float('nan')):>9.4f}"
              f"{('통과' if v.get('passes_bh_fdr') else '—'):>6}"
              f"{('O' if v.get('passes_t3') else '—'):>6}   "
              f"{s['H1']['mean_pct']} → {s['H2']['mean_pct']}")
    d = r["diagnostics"]
    print("\n[진단2] 무작위 배분 벤치:")
    for h in GRID_H:
        b = (d["random_allocation_bench"] or {}).get(f"H{h}") or {}
        print(f"        H{h}: 평균 {b.get('excess_mean_pct')}% · 95% 상단 "
              f"{b.get('excess_p97_5_pct')}% (시행 {b.get('trials')})")
    print("[진단3] A2 점수 무력화 검사:")
    for h in GRID_H:
        b = (d["a2_score_nullification"] or {}).get(f"H{h}") or {}
        print(f"        H{h}: A2 {b.get('a2_excess_mean_pct')}% vs 무작위종목 "
              f"{b.get('random_pick_mean_pct')}% (95% 상단 {b.get('random_p97_5_pct')}%) "
              f"→ 초과 {b.get('beats_random_95')}")
    print("[진단4] 주문/ADV>5% 종목수: " + " · ".join(
        f"{v}_H{h} {d['concentration_impact'][f'{v}_H{h}']['orders_over_adv5pct']}"
        for v in VARIANTS for h in GRID_H))
    print(f"\n참조 구성: {r['adoption']['reference_config'] or '없음 (전원 미충족)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
