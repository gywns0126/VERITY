#!/usr/bin/env python3
"""H1-ext — 외부 장기 데이터로 macro 승수를 재구성해 타이밍 예측력을 검정한다.

## 왜 이게 가능한가

자체 원장은 83일이고 자기상관 0.878 이라 유효 표본이 5.4 다(§11, 착수 불가 판정).
그런데 **승수는 입력의 결정론적 함수**다 —
`multiplier = 1 − min(0.30, valuation + currency + cape + yield)`.
시장 수준 축 3개(cape·currency·yield)의 **과거 입력을 구하면 승수를 재구성**할 수 있고,
그러면 표본이 83일이 아니라 수십 년이 된다.

🚨 이건 스누핑이 아니다. 룰의 파라미터는 이미 사전 고정돼 있고(커밋 485cb5dfe,
`tests/test_percentile_window_spec_lock.py` 로 잠금), **고정된 룰을 긴 역사에 적용해
보는 것은 검증이지 튜닝이 아니다.** 창을 바꿔가며 좋은 걸 고르면 그때 스누핑이 된다.

## 외부 소스 (전부 실호출 확인 2026-08-19)

| 계열 | 소스 | 범위 | 확인 |
|---|---|---|---|
| Shiller CAPE (월) | multpl.com by-month | **1871-02 ~ 2026-08** (1,867행) | ✅ |
| 미국 10년물 (일) | FRED `DGS10` | 1962-01-02 ~ (16,860행) | ✅ |
| 원/달러 (월) | FRED `EXKOUS` | 1981-04 ~ (544행) | ✅ |
| 한국 주가지수 (월) | FRED `SPASTT01KRM661N` (OECD) | 1981-01 ~ (546행) | ✅ |

실효 검정 구간 = 원/달러·KOSPI 가 시작하는 **1981년부터**.

## 🚨 핵심 설계 — 룩어헤드 두 버전을 **둘 다** 낸다

우리 구현의 `cape_percentile` 은 **1881~2024 전 기간 정적 테이블**이다. 그걸 1985년에
적용하면 그 시점에 알 수 없던 분포를 쓰는 것이라 **룩어헤드**다.

  · **(A) 현행 구현 그대로** — 정적 테이블. 실제 코드와 일치하나 과거 적용 시 룩어헤드
  · **(B) 확장창(point-in-time)** — 각 시점까지의 데이터만으로 백분위 산출. 룩어헤드 없음

Q5 답변은 "실시간 vs 사후 백분위 성과 차이를 직접 계량한 학술 연구는 거의 없다
(증거 불충분)" 고 했다. **우리가 직접 재면 된다.** 두 결과의 차이가 그 답이다.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import requests

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

CACHE = os.path.join(_ROOT, "data", "metadata", "macro_external_longrun.json")
FRED = "https://api.stlouisfed.org/fred/series/observations"
MULTPL = "https://www.multpl.com/shiller-pe/table/by-month"

# 🚨 룰 상수 — verity_brain 과 **동일해야 한다**. 여기서 임의로 바꾸면 검정이 무의미하다.
CAPE_MAX_PENALTY = 0.10          # _CAPE_MAX_PENALTY
CAPE_START_PCT = 90.0
YIELD_MAX_PENALTY = 0.10
YIELD_START_PCT = 90.0           # _yield_penalty 와 정합 (아래에서 실제 함수 재사용)
CURRENCY_START = 1450.0
CURRENCY_BAND = 300.0
CURRENCY_MAX_PENALTY = 0.075
TOTAL_CAP = 0.30
YIELD_WINDOW = 252               # _YIELD_PCT_WINDOW


def _fred(series_id: str, key: str) -> List[Tuple[str, float]]:
    r = requests.get(FRED, params={"series_id": series_id, "api_key": key,
                                   "file_type": "json", "observation_start": "1960-01-01"},
                     timeout=40)
    r.raise_for_status()
    out = []
    for o in r.json().get("observations", []):
        try:
            out.append((o["date"], float(o["value"])))
        except (ValueError, KeyError):
            continue
    return out


def _cape() -> List[Tuple[str, float]]:
    r = requests.get(MULTPL, timeout=40, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    t = html.unescape(r.text).replace(" ", " ")
    rows = re.findall(r"<td>([A-Z][a-z]{2}\s+\d{1,2},\s*\d{4})</td>\s*<td>\s*([\d.]+)\s*</td>", t)
    out = []
    for ds, v in rows:
        try:
            d = datetime.strptime(ds, "%b %d, %Y").date()
            out.append((d.strftime("%Y-%m-%d"), float(v)))
        except ValueError:
            continue
    return sorted(out)


def fetch_all(force: bool = False) -> Dict[str, List]:
    if os.path.exists(CACHE) and not force:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    from api.config import FRED_API_KEY
    data = {
        "cape": _cape(),
        "dgs10": _fred("DGS10", FRED_API_KEY),
        "usdkrw": _fred("EXKOUS", FRED_API_KEY),
        "kospi": _fred("SPASTT01KRM661N", FRED_API_KEY),
        "_meta": {"fetched": date.today().isoformat(),
                  "sources": {"cape": MULTPL, "fred": "DGS10/EXKOUS/SPASTT01KRM661N"}},
    }
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


# ── 페널티 (verity_brain 룰과 동일하게 재현) ──────────────────────────────
def cape_pen_static(cape: float) -> float:
    """(A) 현행 구현 — 정적 테이블로 백분위 → 페널티."""
    from api.intelligence.market_horizon import cape_percentile
    pct = cape_percentile(cape)
    if pct is None or pct < CAPE_START_PCT:
        return 0.0
    return max(0.0, min(CAPE_MAX_PENALTY, (pct - 90) / 10 * 0.15))


def _pct_expanding(hist: List[float], cur: float) -> float:
    return sum(1 for v in hist if v <= cur) / len(hist) * 100 if hist else 50.0


def cape_pen_pit(hist: List[float], cape: float) -> float:
    """(B) 확장창 — 그 시점까지의 분포만 사용(룩어헤드 없음)."""
    pct = _pct_expanding(hist, cape)
    if pct < CAPE_START_PCT:
        return 0.0
    return max(0.0, min(CAPE_MAX_PENALTY, (pct - 90) / 10 * 0.15))


def yield_pen(pct: Optional[float]) -> float:
    if pct is None or pct < YIELD_START_PCT:
        return 0.0
    return max(0.0, min(YIELD_MAX_PENALTY, (pct - 90) / 10 * 0.15))


def currency_pen(usdkrw: float) -> float:
    if usdkrw < CURRENCY_START:
        return 0.0
    return max(0.0, min(CURRENCY_MAX_PENALTY,
                        (usdkrw - CURRENCY_START) / CURRENCY_BAND * CURRENCY_MAX_PENALTY))


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean(); rb -= rb.mean()
    d = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / d) if d else float("nan")


def main() -> int:
    force = "--refresh" in sys.argv
    d = fetch_all(force)
    cape = [(x[0], x[1]) for x in d["cape"]]
    dgs = [(x[0], x[1]) for x in d["dgs10"]]
    fx = {x[0][:7]: x[1] for x in d["usdkrw"]}
    ks = {x[0][:7]: x[1] for x in d["kospi"]}

    print("═" * 70)
    print("H1-ext — 외부 장기 데이터로 macro 승수 재구성 · 타이밍 예측력 검정")
    print("═" * 70)
    print(f"CAPE {len(cape)}행 {cape[0][0]}~{cape[-1][0]} · DGS10 {len(dgs)}행 "
          f"· 원/달러 {len(fx)}월 · 한국지수 {len(ks)}월")

    # 월말 기준 10년물 백분위 (롤링 252 거래일 — 구현과 동일한 창)
    dgs_dates = [x[0] for x in dgs]
    dgs_vals = [x[1] for x in dgs]
    y_pct_by_month: Dict[str, float] = {}
    for i in range(len(dgs)):
        mo = dgs_dates[i][:7]
        lo = max(0, i - YIELD_WINDOW + 1)
        win = dgs_vals[lo:i + 1]
        if len(win) >= 60:
            y_pct_by_month[mo] = sum(1 for v in win if v <= dgs_vals[i]) / len(win) * 100

    cape_hist: List[float] = []
    months, mult_a, mult_b = [], [], []
    for ds, cv in cape:
        mo = ds[:7]
        cape_hist.append(cv)
        if mo not in fx or mo not in ks or mo not in y_pct_by_month:
            continue
        yp = yield_pen(y_pct_by_month[mo])
        cp = currency_pen(fx[mo])
        a = 1.0 - min(TOTAL_CAP, cape_pen_static(cv) + cp + yp)
        b = 1.0 - min(TOTAL_CAP, cape_pen_pit(cape_hist[:-1], cv) + cp + yp)
        months.append(mo); mult_a.append(a); mult_b.append(b)

    if len(months) < 60:
        print(f"🚨 겹치는 월 {len(months)} — 검정 불가")
        return 0

    print(f"\n검정 구간 **{months[0]} ~ {months[-1]} · {len(months)}개월**"
          f" ({(len(months)/12):.1f}년) — 자체 원장 83일 대비 {len(months)/83*30:.0f}배")

    idx = {m: i for i, m in enumerate(months)}
    kv = np.array([ks[m] for m in months])

    for H in (12, 24):
        fwd = np.full(len(months), np.nan)
        for i in range(len(months) - H):
            if kv[i] > 0:
                fwd[i] = kv[i + H] / kv[i] - 1.0
        ok = ~np.isnan(fwd)
        print(f"\n── forward {H}개월 (관측 {int(ok.sum())}) ──")
        for label, mult in (("(A) 현행 정적 테이블 [룩어헤드 有]", np.array(mult_a)),
                            ("(B) 확장창 point-in-time [룩어헤드 無]", np.array(mult_b))):
            m, f = mult[ok], fwd[ok]
            if np.unique(m).size < 3:
                print(f"  {label}: 승수 고유값 {np.unique(m).size} — 산출 불가")
                continue
            ic = spearman(m, f)
            n_ind = max(1, int(ok.sum()) // H)      # 중첩 보정 = 비중첩 창 수
            se = np.sqrt((1 - ic ** 2) / max(n_ind - 2, 1))
            print(f"  {label}")
            print(f"    승수 범위 {m.min():.3f}~{m.max():.3f} · 고유 {np.unique(m).size}개"
                  f" · <1.0 비율 {(m<1).mean()*100:.0f}%")
            print(f"    IC(승수, forward) = {ic:+.4f}  "
                  f"· 비중첩 창 {n_ind} · SE≈{se:.4f} · |t|≈{abs(ic/se):.2f}")
            print(f"    🚨 검출하한 |IC| ≥ {2*se:.4f}")
            print(f"    기대 부호 = **양(+)** (승수가 낮았던 국면의 forward 가 낮아야 함)")
    print("\n※ (A)와 (B)의 차이가 곧 Q5(d) '실시간 vs 사후 백분위' 의 자체 실측치다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
