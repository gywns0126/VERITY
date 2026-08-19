#!/usr/bin/env python3
"""금리 축 형태 비교 F0/F1/F2 — 사전등록 `PREREG_YIELD_AXIS_FORM_2026_08_19.md` 실행.

🚨 이 스크립트는 등록문의 판정 규칙을 **그대로** 구현한다. 등록 후 규칙을 바꾸면
스누핑이 되므로, 임계(z≥1 · CPI 3%)와 판정표는 여기서 하드코딩하고 변경 금지다.

후보 (전부 yield_penalty ∈ [0, 0.10], 상한·기울기 동일 — 형태만 교체)
  F0 수준 백분위(현행) · F1 충격 z-score · F2 충격 × 인플레 레짐

🚨 목표는 **우열을 가리는 것이 아니다**(등록문 §1). 검출하한이 이미 |IC| ≥ 0.30(12M)로
측정돼 있어 통계적 우열 판정은 거의 확실히 불가능하다. 목표는
① 문헌 형태가 부호라도 맞는지 ② 현행이 뚜렷이 나쁜지 ③ 못 잰다는 사실의 기록.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional, Tuple

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from scripts.macro_h1_external_reconstruction import (  # noqa: E402
    CAPE_MAX_PENALTY, TOTAL_CAP, YIELD_MAX_PENALTY, YIELD_WINDOW,
    cape_pen_pit, currency_pen, fetch_all, spearman,
)

# ── 등록문 §2 에 고정된 임계 — 변경 금지 ──────────────────────────────────
SHOCK_Z_START = 1.0        # F1: z < 1 이면 페널티 0
SHOCK_Z_BAND = 2.0         # z=3 에서 상한 도달
SHOCK_LOOKBACK_M = 120     # 충격 z 의 롤링 창(개월)
SHOCK_HORIZON_M = 12       # 금리 '변화' 의 기간(개월)
CPI_REGIME_PCT = 3.0       # F2: CPI YoY < 3% 일 때만 금리 충격을 노출축소 신호로 인정
HORIZONS = (12, 24)
N_COMPARISONS = 6          # 3형태 × 2지평 — 등록문 §3


def yield_pen_level(pct: Optional[float]) -> float:
    """F0 — 현행. 롤링 252거래일 수준 백분위."""
    if pct is None or pct < 90.0:
        return 0.0
    return max(0.0, min(YIELD_MAX_PENALTY, (pct - 90) / 10 * 0.15))


def yield_pen_shock(z: Optional[float]) -> float:
    """F1 — 12개월 금리 변화의 z-score(롤링 120개월)."""
    if z is None or z < SHOCK_Z_START:
        return 0.0
    return max(0.0, min(YIELD_MAX_PENALTY,
                        (z - SHOCK_Z_START) / SHOCK_Z_BAND * YIELD_MAX_PENALTY))


def yield_pen_shock_regime(z: Optional[float], cpi_yoy: Optional[float]) -> float:
    """F2 — F1 × 인플레 레짐(이진). 고인플레면 금리 충격 신호를 끈다."""
    if cpi_yoy is None or cpi_yoy >= CPI_REGIME_PCT:
        return 0.0
    return yield_pen_shock(z)


def build_monthly(d: Dict) -> Dict[str, Dict[str, float]]:
    """월별 입력 패널 — {YYYY-MM: {cape, usdkrw, kospi, y_pct, y_z, cpi_yoy}}"""
    out: Dict[str, Dict[str, float]] = {}

    for ds, v in d["cape"]:
        out.setdefault(ds[:7], {})["cape"] = v
    for ds, v in d["usdkrw"]:
        out.setdefault(ds[:7], {})["usdkrw"] = v
    for ds, v in d["kospi"]:
        out.setdefault(ds[:7], {})["kospi"] = v

    # 10년물: 월말값 + 롤링 252거래일 수준 백분위
    dates = [x[0] for x in d["dgs10"]]
    vals = [x[1] for x in d["dgs10"]]
    last_by_month: Dict[str, float] = {}
    for i, ds in enumerate(dates):
        mo = ds[:7]
        last_by_month[mo] = vals[i]
        lo = max(0, i - YIELD_WINDOW + 1)
        win = vals[lo:i + 1]
        if len(win) >= 60:
            out.setdefault(mo, {})["y_pct"] = sum(1 for v in win if v <= vals[i]) / len(win) * 100

    # 충격 z: 12개월 금리 변화의 롤링 120개월 z-score
    months = sorted(last_by_month)
    chg: Dict[str, float] = {}
    for i in range(SHOCK_HORIZON_M, len(months)):
        chg[months[i]] = last_by_month[months[i]] - last_by_month[months[i - SHOCK_HORIZON_M]]
    cm = sorted(chg)
    for i in range(len(cm)):
        lo = max(0, i - SHOCK_LOOKBACK_M + 1)
        win = [chg[m] for m in cm[lo:i + 1]]
        if len(win) >= 60:
            mu, sd = float(np.mean(win)), float(np.std(win, ddof=1))
            if sd > 0:
                out.setdefault(cm[i], {})["y_z"] = (chg[cm[i]] - mu) / sd

    # CPI YoY
    cpi = {x[0][:7]: x[1] for x in d.get("cpi", [])}
    cs = sorted(cpi)
    for i in range(12, len(cs)):
        prev = cpi[cs[i - 12]]
        if prev:
            out.setdefault(cs[i], {})["cpi_yoy"] = (cpi[cs[i]] / prev - 1) * 100
    return out


def main() -> int:
    d = fetch_all(False)
    if "cpi" not in d:
        from api.config import FRED_API_KEY
        from scripts.macro_h1_external_reconstruction import _fred, CACHE
        import json
        d["cpi"] = _fred("CPIAUCSL", FRED_API_KEY)
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        print("[fetch] CPIAUCSL 추가 캐시")

    panel = build_monthly(d)
    need = ("cape", "usdkrw", "kospi", "y_pct", "y_z", "cpi_yoy")
    months = sorted(m for m, v in panel.items() if all(k in v for k in need))

    print("═" * 72)
    print("금리 축 형태 비교 F0/F1/F2 — PREREG_YIELD_AXIS_FORM_2026_08_19 실행")
    print("═" * 72)
    print(f"공통 표본 **{months[0]} ~ {months[-1]} · {len(months)}개월** "
          f"({len(months)/12:.1f}년)")
    print("🚨 등록문 §1 — 목표는 우열 판정이 **아니다**. 검출하한이 이미 |IC|≥0.30(12M)로")
    print("   측정돼 있어 통계적 우열은 거의 확실히 불가능하다.")

    # cape·currency 는 세 형태 공통 (변수 하나만 이동)
    cape_hist: List[float] = []
    base: List[float] = []
    pens: Dict[str, List[float]] = {"F0": [], "F1": [], "F2": []}
    for m in sorted(panel):
        if "cape" in panel[m]:
            cape_hist.append(panel[m]["cape"])
        if m not in months:
            continue
        v = panel[m]
        base.append(cape_pen_pit(cape_hist[:-1], v["cape"]) + currency_pen(v["usdkrw"]))
        pens["F0"].append(yield_pen_level(v["y_pct"]))
        pens["F1"].append(yield_pen_shock(v["y_z"]))
        pens["F2"].append(yield_pen_shock_regime(v["y_z"], v["cpi_yoy"]))

    b = np.array(base)
    ks = np.array([panel[m]["kospi"] for m in months])
    mults = {k: 1.0 - np.minimum(TOTAL_CAP, b + np.array(v)) for k, v in pens.items()}

    print("\n── 형태별 페널티 발동 상황 (표본 전체) ──")
    for k in ("F0", "F1", "F2"):
        p = np.array(pens[k])
        print(f"  {k}  >0 비율 {(p>0).mean()*100:>5.1f}% · 상한도달 {(p>=0.0999).mean()*100:>4.1f}%"
              f" · 고유값 {np.unique(np.round(p,5)).size:>3}  |  승수 범위 "
              f"{mults[k].min():.3f}~{mults[k].max():.3f}")

    print(f"\n🚨 다중비교 {N_COMPARISONS}회 — 명목 유의로 승자를 고르지 않는다(등록문 §3)")
    results = {}
    for H in HORIZONS:
        fwd = np.full(len(months), np.nan)
        for i in range(len(months) - H):
            if ks[i] > 0:
                fwd[i] = ks[i + H] / ks[i] - 1.0
        ok = ~np.isnan(fwd)
        n_ind = max(1, int(ok.sum()) // H)
        print(f"\n── forward {H}개월 · 관측 {int(ok.sum())} · 비중첩 창 {n_ind} ──")
        for k in ("F0", "F1", "F2"):
            m = mults[k][ok]
            if np.unique(m).size < 3:
                print(f"  {k}: 승수 고유값 {np.unique(m).size} — 산출 불가")
                results[(k, H)] = None
                continue
            ic = spearman(m, fwd[ok])
            se = np.sqrt((1 - ic ** 2) / max(n_ind - 2, 1))
            floor = 2 * se
            results[(k, H)] = (ic, se, floor)
            mark = "○" if abs(ic) >= floor else "×"
            print(f"  {k}  IC {ic:+.4f} · SE {se:.4f} · |t| {abs(ic/se):.2f} "
                  f"· 하한 {floor:.4f}  [{mark} {'하한 초과' if mark=='○' else '검출 미달'}]"
                  f" · 부호 {'기대(+)' if ic > 0 else '🚨 반대(−)'}")

    # ── 등록문 §3 판정표 그대로 ──────────────────────────────────────────
    print("\n" + "═" * 72)
    print("판정 (등록문 §3 규칙 — 사후 변경 없음)")
    print("═" * 72)
    valid = {k: v for k, v in results.items() if v}
    over = [k for k, v in valid.items() if abs(v[0]) >= v[2]]
    if not over:
        print("→ **판정 보류.** 모든 형태가 검출하한 미달이다. 형태 우열을 말하지 않는다.")
        print("   아래는 서술 보고이며 **순위로 읽으면 안 된다**:")
        for H in HORIZONS:
            row = [(k, valid[(k, H)][0]) for k in ("F0", "F1", "F2") if (k, H) in valid]
            print(f"     {H}M  " + " · ".join(f"{k} {ic:+.4f}" for k, ic in row))
        neg = [k for k, v in valid.items() if v[0] < 0]
        if neg:
            print(f"   🚨 부호가 기대와 반대인 셀: {sorted(neg)} — 관측 기록(제거 근거 아님)")
        else:
            print("   부호는 전 셀에서 기대 방향(+)이다.")
    else:
        print(f"→ 하한 초과 셀 {sorted(over)} — 등록문상 **후보 등록**이며 즉시 배선하지 않는다.")
        print("   재현·강건성 확인을 별도 등록으로 진행할 것.")
    print("\n🚨 등록문 §4 — 결과와 무관하게 **이번 실행으로 산식을 바꾸지 않는다.**")
    print("   또한 형태를 바꿔도 금리 축은 전 종목 공통값이라 **횡단면 기여는 여전히 0**이다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
