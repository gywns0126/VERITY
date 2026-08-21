#!/usr/bin/env python3
"""L2 — 희석군 내 내부자 방향 (사전등록 H2). 🚨 관측 전용 · 산식 변경 0 · 발행 안 함.

🚨 **등록서 §2 의 L2 T 추정이 틀렸다.** [2024-08, 2025-09] 14개월로 적었는데,
근거였던 "elestock 약 2년 창" 의 실측 거래 시작이 **2024-06-28** 이라 룩백 1년을 빼면
T ≥ 2025-06-28 이다. 가격은 등록대로 **pkl 단독**(2025-12-30 종료)이므로:

    3개월 지평 → T ∈ [2025-07, 2025-09]  = **3개 횡단면**
    6개월 지평 → 🚨 **공집합**

등록 규칙(§3-E-1 "불일치 시 한 소스만")을 지키면 이게 결과다. 규칙을 완화하지 않는다.

🚨 **결과 동반 문장 (등록 §3-E-7 의무)**: 이 비교는 **상장 유지 종목 한정**이다.
희석 후 상폐한 최악 사례가 빠져 있으므로 **내부자 매도의 해악이 과소평가된다.**
"""
from __future__ import annotations

import glob
import json
import os
import re
import statistics
import sys
from datetime import date, timedelta

import numpy.core as _np_core

sys.modules.setdefault("numpy._core", _np_core)
for _s in ("numeric", "multiarray", "umath", "numerictypes", "_multiarray_umath", "overrides"):
    try:
        sys.modules[f"numpy._core.{_s}"] = __import__(f"numpy.core.{_s}", fromlist=[_s])
    except Exception:
        pass
import pickle  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA = os.path.join(_ROOT, "data")
OUT = os.path.join(DATA, "metadata", "dilution_insider_l2.json")
_KD = re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일")


def kdate(v):
    m = _KD.match(str(v or ""))
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def num(v):
    s = str(v or "").replace(",", "").strip()
    if s in ("", "-", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def cohen_d(a, b):
    if len(a) < 2 or len(b) < 2:
        return None
    va, vb, n1, n2 = statistics.pvariance(a), statistics.pvariance(b), len(a), len(b)
    sp = ((n1 * va + n2 * vb) / (n1 + n2)) ** 0.5
    return None if sp == 0 else (statistics.mean(a) - statistics.mean(b)) / sp


def main() -> int:
    det = json.load(open(os.path.join(DATA, "dart_cb_bw_detail.json"), encoding="utf-8"))["by_ticker"]
    ins = {str(r["ticker"]): r for r in
           json.load(open(os.path.join(DATA, "insider_trades.json"), encoding="utf-8"))["stocks"]}

    px = {}
    for p in glob.glob(os.path.join(DATA, "cache", "5r_analysis_ohlcv", "*.pkl")):
        tk = os.path.basename(p).split("_")[0]
        try:
            df = pickle.load(open(p, "rb"))
            px[tk] = {d.date(): float(c) for d, c in zip(df.index, df["close"]) if c == c}
        except Exception:
            continue

    def at(ser, t, back=10):
        ds = [d for d in ser if d <= t]
        if not ds:
            return None
        last = max(ds)
        return ser[last] if (t - last).days <= back else None

    Ts = [date(2025, 7, 1), date(2025, 8, 1), date(2025, 9, 1)]
    rows = []
    for t in Ts:
        for tk, v in det.items():
            if tk not in px or tk not in ins:
                continue
            live = [x for x in v["instruments"]
                    if (b := kdate(x.get("x_bgd"))) and (e := kdate(x.get("x_edd"))) and b <= t <= e]
            ov = sum(num(x.get("x_pct")) or 0 for x in live)
            if ov <= 0:
                continue                       # 🚨 L2 = 희석군 **안에서만** 비교(등록 H2)
            lo = t - timedelta(days=365)
            net = sum((tr.get("change") or 0) for tr in (ins[tk].get("trades") or [])
                      if tr.get("date") and lo < date(*map(int, tr["date"].split("-"))) <= t)
            p0 = at(px[tk], t)
            if not p0 or p0 <= 0:
                continue
            y, m = (t.year, t.month + 3)
            y, m = (y + (m - 1) // 12, (m - 1) % 12 + 1)
            p1 = at(px[tk], date(y, m, 1))
            if not p1 or p1 <= 0:
                continue
            rows.append({"t": t.isoformat(), "tk": tk, "ov": ov, "net": net, "m3": p1 / p0 - 1})

    # 월 고정효과(§5-5)
    by_t = {}
    for r in rows:
        by_t.setdefault(r["t"], []).append(r["m3"])
    mu = {k: statistics.mean(v) for k, v in by_t.items() if v}
    for r in rows:
        r["m3_ex"] = r["m3"] - mu[r["t"]]

    buy = [r for r in rows if r["net"] > 0]
    sell = [r for r in rows if r["net"] < 0]
    flat = [r for r in rows if r["net"] == 0]
    res = {"_meta": {
        "prereg": "PREREG_DILUTION_INSIDER_CROSS_2026_08_21.md H2 / L2",
        "T": [t.isoformat() for t in Ts],
        "registered_T_was_wrong": ("등록서 §2 는 14개월로 적었으나 실측 거래 시작 2024-06-28 "
                                   "+ 룩백 1년 + pkl 종료 2025-12-30 → 3개월. 6개월 지평은 공집합"),
        "mandatory_caveat": ("🚨 상장 유지 종목 한정. 희석 후 상폐한 최악 사례가 빠져 "
                             "내부자 매도의 해악이 과소평가된다"),
        "detect_floor_d": 0.37, "brain_input": False, "publish": False,
        "n_obs": len(rows), "n_ticker": len({r["tk"] for r in rows}),
        "n_buy": len(buy), "n_sell": len(sell), "n_flat": len(flat),
        "m6": "🚨 공집합 — 미시행",
    }, "H2": {}}
    for key in ("m3", "m3_ex"):
        d = cohen_d([r[key] for r in buy], [r[key] for r in sell])
        res["H2"][key] = {
            "mean_buy": round(statistics.mean([r[key] for r in buy]), 5) if buy else None,
            "mean_sell": round(statistics.mean([r[key] for r in sell]), 5) if sell else None,
            "cohen_d": round(d, 4) if d is not None else None,
            "detectable": (abs(d) >= 0.37) if d is not None else None,
        }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"[L2] 관측 {len(rows)} · 종목 {res['_meta']['n_ticker']} "
          f"· 순매수 {len(buy)} / 순매도 {len(sell)} / 무변동 {len(flat)}")
    for k, v in res["H2"].items():
        d = v["cohen_d"]
        print(f"  [{k:<6}] 매수 {v['mean_buy']} vs 매도 {v['mean_sell']} · d={d} "
              f"→ {'검출됨' if (d and abs(d) >= 0.37) else '🚨 검출 불가'}")
    print(f"[L2] 기록 → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
