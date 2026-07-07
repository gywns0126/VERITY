"""factor_batch.py — 재무 산식 배치 탐색 오케스트레이터 (관측 전용).

사전등록(동결): docs/PREREG_FORMULA_DISCOVERY_2026_07_06.md
  · horizon=12m · 유니버스=US Mid/Large/Mega(소형 제외) · 컷오프=flag0 + |ICIR|≥0.3 + DSR≥0.95
  · 1차=관측 전용(reject 없음) · 성격=레일 캘리브레이션(알파 발굴 아님, held-2027)

🚨 RULE 7: 산식/컷오프 튜닝 금지. 실행 후 산식 목록 변경 = 새 사전등록. 생존분 = *가설 후보*(라이브 아님).
🚨 신규 코드는 이 오케스트레이터뿐 — 검증 수학(gauntlet 10체크·CSCV PBO·DSR)은 전부 기존 자산 재사용.

동작: 동결 산식 K개 → 각각 [PIT 패널 → gauntlet 10체크 → spread Sharpe → DSR(n_trials=K)] → 리더보드.
  DSR n_trials=K = "K개 시도 중 최고가 우연일 확률" 다중검정 보정. K 고정이 곡선맞추기 차단 핵심.

주의(정직): 11필드 decile 방법론에선 z-score/rank = 단조변환 → 동일 분위 → 무의미. 순서를 바꾸는
  변환만 사용(level / YoY Δ / 선언 z-합성). '수백'은 필드 상호작용·가격데이터 필요(후속 스코프).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.validation.factor_gauntlet import (  # noqa: E402
    FUND, forward_returns, fundamental_signal, run_gauntlet, _load_size_delisted,
)
from api.quant.alpha.psr import compute_deflated_sharpe_ratio  # noqa: E402

# ── 동결 산식 집합 (§3, 실행 후 변경 = 새 사전등록) ──
BASE_FIELDS = ["roa", "roe", "gpoa", "netmargin", "accruals", "asset_growth",
               "leverage", "current_ratio", "book_equity", "altman_z", "piotroski_f"]
LOWER_BETTER = {"accruals", "asset_growth", "leverage"}   # 방향 사전지정 = 부호 반전
# 선언 조합 (z-합성, 사후 추가 금지). 값 = (필드, 방향부호) 리스트
COMPOSITES: Dict[str, List[tuple]] = {
    "quality_z": [("gpoa", 1), ("roa", 1), ("netmargin", 1)],
    "safety_z": [("altman_z", 1), ("current_ratio", 1), ("leverage", -1)],
    "conservative_z": [("accruals", -1), ("asset_growth", -1), ("leverage", -1)],
    "qmj_z": [("gpoa", 1), ("piotroski_f", 1), ("accruals", -1)],   # quality-minus-junk 근사
}
# 대형/중형 유니버스 (소형 제외 = 거래가능성 필터, §4-②)
UNIVERSE_SIZES_PREFIX = ("4", "5", "6")   # 4-Mid / 5-Large / 6-Mega


def _sign(field: str) -> int:
    return -1 if field in LOWER_BETTER else 1


def _level_panel(field: str) -> pd.DataFrame:
    """fundamental_signal(field) + 방향부호. (ticker, formation_date, value)."""
    p = fundamental_signal(field)
    p["value"] = p["value"] * _sign(field)
    return p


def _yoy_panel(field: str) -> pd.DataFrame:
    """전년 동형성일 대비 Δ (순서를 바꾸는 변환). 방향부호 적용."""
    p = fundamental_signal(field).copy()
    p["year"] = p["formation_date"].dt.year
    prev = p[["ticker", "year", "value"]].copy()
    prev["year"] = prev["year"] + 1
    prev = prev.rename(columns={"value": "prev"})
    m = p.merge(prev, on=["ticker", "year"], how="inner")
    m["value"] = (m["value"] - m["prev"]) * _sign(field)
    return m[["ticker", "formation_date", "value"]].dropna(subset=["value"])


def _composite_panel(spec: List[tuple]) -> pd.DataFrame:
    """형성일별 각 성분 횡단면 z(부호적용) 합. z-score = 합성에서만 유효(순서 바꿈)."""
    cols = list({f for f, _ in spec})
    ff = pd.read_parquet(FUND, columns=["ticker", "datekey"] + cols)
    ff["datekey"] = pd.to_datetime(ff["datekey"])
    rows = []
    for yr in range(1999, 2026):
        f = pd.Timestamp(f"{yr}-06-30")
        cur = ff[(ff["datekey"] <= f) & (ff["datekey"] >= f - pd.DateOffset(months=18))]
        cur = cur.sort_values("datekey").groupby("ticker").tail(1)
        if cur.empty:
            continue
        z = pd.DataFrame({"ticker": cur["ticker"].values})
        z["value"] = 0.0
        ok = np.zeros(len(cur), dtype=bool)
        acc = np.zeros(len(cur), dtype=float)
        cnt = np.zeros(len(cur), dtype=float)
        for fld, sgn in spec:
            v = cur[fld].astype(float).values
            mu, sd = np.nanmean(v), np.nanstd(v)
            if not np.isfinite(sd) or sd == 0:
                continue
            zz = (v - mu) / sd * sgn
            good = np.isfinite(zz)
            acc[good] += zz[good]
            cnt[good] += 1
        valid = cnt > 0
        z["value"] = np.where(valid, acc, np.nan)
        z = z[valid]
        z["formation_date"] = pd.Timestamp(f"{yr}-06-01")
        rows.append(z[["ticker", "formation_date", "value"]])
    return pd.concat(rows, ignore_index=True).dropna(subset=["value"]) if rows else pd.DataFrame()


def _spread_series(panel: pd.DataFrame) -> List[float]:
    """형성일별 top-bottom 십분위 fwd 스프레드 시계열 (Sharpe/DSR 입력). gauntlet decile 로직 동일."""
    fwd = forward_returns(12, clip=5.0)
    bp = panel.merge(fwd.rename(columns={"month": "formation_date"}),
                     on=["ticker", "formation_date"], how="inner")
    out = []
    for _f, g in bp.groupby("formation_date"):
        g = g.dropna(subset=["value", "fwd"])
        if g["value"].nunique() < 10 or len(g) < 30:
            continue
        d = pd.qcut(g["value"].rank(method="first"), 10, labels=False)
        out.append(float(g.loc[d == 9, "fwd"].mean() - g.loc[d == 0, "fwd"].mean()))
    return out


def _icir(panel: pd.DataFrame) -> Optional[float]:
    """형성일별 rank IC(Spearman: value vs fwd) → ICIR = mean/std."""
    fwd = forward_returns(12, clip=5.0)
    bp = panel.merge(fwd.rename(columns={"month": "formation_date"}),
                     on=["ticker", "formation_date"], how="inner")
    ics = []
    for _f, g in bp.groupby("formation_date"):
        g = g.dropna(subset=["value", "fwd"])
        if len(g) < 30 or g["value"].nunique() < 10:
            continue
        ics.append(float(g["value"].rank().corr(g["fwd"].rank())))
    ics = [x for x in ics if x is not None and np.isfinite(x)]
    if len(ics) < 3:
        return None
    sd = float(np.std(ics, ddof=1))
    return round(float(np.mean(ics)) / sd, 3) if sd > 0 else None


def _one(name: str, panel: pd.DataFrame, K: int, size_labels, delisted) -> Dict[str, object]:
    series = _spread_series(panel)
    T = len(series)
    sharpe = dsr = None
    if T >= 4:
        arr = np.array(series, dtype=float)
        sd = float(arr.std(ddof=1))
        if sd > 0:
            sharpe = round(float(arr.mean()) / sd, 3)   # 연간관측 → 연 Sharpe(√252 불필요)
            d = compute_deflated_sharpe_ratio(sharpe, T=T, n_trials=K, returns=series)
            dsr = d.get("psr") if isinstance(d, dict) else None   # DSR = benchmark 보정된 PSR
    icir = _icir(panel)
    g = run_gauntlet(panel, horizon_m=12, size_labels=size_labels, delisted=delisted)
    flags = g.get("flags", [])
    critical = [f for f in flags if f in ("placebo_leak", "survivorship", "regime_dependent")]
    base = g["checks"]["1_base"]
    survivor = (len(critical) == 0 and icir is not None and abs(icir) >= 0.3
                and dsr is not None and dsr >= 0.95)
    return {
        "formula": name, "n_periods": T, "spread": base.get("spread"), "t": base.get("t"),
        "icir": icir, "spread_sharpe": sharpe, "dsr": round(dsr, 3) if dsr is not None else None,
        "flags": flags, "critical_flags": critical, "survivor": survivor,
    }


def run_batch() -> Dict[str, object]:
    size_labels, delisted = _load_size_delisted()
    # 유니버스 = Mid/Large/Mega (소형 제외)
    keep = size_labels[size_labels["size"].astype(str).str.strip().str[0].isin(UNIVERSE_SIZES_PREFIX)]
    uni = set(keep["ticker"])

    def _restrict(p: pd.DataFrame) -> pd.DataFrame:
        return p[p["ticker"].isin(uni)]

    # 동결 산식 목록 빌드 (K 고정)
    formulas: List[tuple] = []
    for fld in BASE_FIELDS:
        formulas.append((f"{fld}", _restrict(_level_panel(fld))))
        formulas.append((f"{fld}_yoy", _restrict(_yoy_panel(fld))))
    for cname, spec in COMPOSITES.items():
        formulas.append((cname, _restrict(_composite_panel(spec))))
    K = len(formulas)

    rows = []
    for name, panel in formulas:
        try:
            rows.append(_one(name, panel, K, size_labels, delisted))
        except Exception as e:  # noqa: BLE001
            rows.append({"formula": name, "error": f"{type(e).__name__}: {e}"})

    ranked = sorted([r for r in rows if "error" not in r],
                    key=lambda r: (r["dsr"] is not None, r["dsr"] or -9), reverse=True)
    survivors = [r for r in ranked if r.get("survivor")]
    return {
        "prereg": "docs/PREREG_FORMULA_DISCOVERY_2026_07_06.md",
        "universe": "US Mid/Large/Mega", "horizon_m": 12, "K_trials": K,
        "cutoff": "critical_flag=0 & |ICIR|>=0.3 & DSR>=0.95",
        "n_survivors": len(survivors), "leaderboard": ranked,
        "errors": [r for r in rows if "error" in r],
        "note": "관측 전용 · 생존분=가설 후보(라이브 아님, held-2027) · DSR n_trials=K 다중검정 보정",
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="", help="결과 JSON 저장 경로(옵션)")
    args = ap.parse_args()
    res = run_batch()
    print(f"\n===== FORMULA BATCH (US Mid/Large/Mega · h=12m · K={res['K_trials']}) =====")
    print(f"컷오프: {res['cutoff']}")
    print(f"생존: {res['n_survivors']}/{res['K_trials']}\n")
    hdr = f"{'formula':<18} {'T':>3} {'spread':>8} {'t':>6} {'ICIR':>6} {'Sharpe':>7} {'DSR':>6}  flags"
    print(hdr); print("-" * len(hdr))
    for r in res["leaderboard"]:
        mark = "★" if r.get("survivor") else " "
        print(f"{mark}{r['formula']:<17} {r['n_periods']:>3} "
              f"{(r['spread'] if r['spread'] is not None else 0):>8.4f} "
              f"{(r['t'] if r['t'] is not None else 0):>6.2f} "
              f"{(r['icir'] if r['icir'] is not None else 0):>6.2f} "
              f"{(r['spread_sharpe'] if r['spread_sharpe'] is not None else 0):>7.2f} "
              f"{(r['dsr'] if r['dsr'] is not None else 0):>6.2f}  {','.join(r['flags']) or '-'}")
    if res["errors"]:
        print(f"\n오류 {len(res['errors'])}: " + ", ".join(f"{e['formula']}({e['error']})" for e in res["errors"]))
    if args.out:
        with open(args.out, "w") as f:
            json.dump(res, f, ensure_ascii=False, indent=1, default=str)
        print(f"\n저장: {args.out}")
