"""
팩터 IC(Information Coefficient) 스캐너 — 알파 유효성 측정

학술 근거:
  - Grinold & Kahn (1999): IC = corr(팩터 노출, 미래 수익률)
    — 팩터의 예측력을 측정하는 가장 기본적인 지표
  - IC > 0.05: 약한 예측력, IC > 0.10: 유의미, IC > 0.15: 강한 예측력
  - ICIR (IC / std(IC)): IC의 안정성 — ICIR > 0.5면 실전 사용 가능

구현:
  1. 스냅샷 아카이브에서 팩터 값과 N일 후 실제 수익률 추출
  2. Rank IC (스피어만 상관) 계산
  3. 롤링 IC로 팩터 유효기간(수명) 추적
  4. 팩터 붕괴(Decay) 감지 → Strategy Evolver에 경고
"""
from __future__ import annotations

import json
import os
import statistics
from typing import Any, Dict, List


from api.config import DATA_DIR, now_kst


IC_CACHE_PATH = os.path.join(DATA_DIR, "factor_ic_history.json")

FACTOR_EXTRACTORS = {
    "multi_factor": lambda s: s.get("multi_factor", {}).get("multi_score"),
    "momentum": lambda s: s.get("multi_factor", {}).get("quant_factors", {}).get("momentum"),
    "quality": lambda s: s.get("multi_factor", {}).get("quant_factors", {}).get("quality"),
    "volatility": lambda s: s.get("multi_factor", {}).get("quant_factors", {}).get("volatility"),
    "mean_reversion": lambda s: s.get("multi_factor", {}).get("quant_factors", {}).get("mean_reversion"),
    "fundamental": lambda s: s.get("multi_factor", {}).get("factor_breakdown", {}).get("fundamental"),
    "technical": lambda s: s.get("multi_factor", {}).get("factor_breakdown", {}).get("technical"),
    "flow": lambda s: s.get("multi_factor", {}).get("factor_breakdown", {}).get("flow"),
    "sentiment": lambda s: s.get("multi_factor", {}).get("factor_breakdown", {}).get("sentiment"),
    "consensus": lambda s: s.get("consensus", {}).get("consensus_score"),
    "prediction": lambda s: s.get("prediction", {}).get("up_probability"),
    "timing": lambda s: s.get("timing", {}).get("timing_score"),
    "brain_score": lambda s: s.get("verity_brain", {}).get("brain_score"),
    "safety_score": lambda s: s.get("safety_score"),
}


def _spearman_rank_corr(x: List[float], y: List[float]) -> float:
    """스피어만 순위 상관계수 (scipy 없이 구현)."""
    n = len(x)
    if n < 5:
        return 0.0

    def _rank(arr):
        sorted_idx = sorted(range(len(arr)), key=lambda i: arr[i])
        ranks = [0.0] * len(arr)
        for rank, idx in enumerate(sorted_idx):
            ranks[idx] = rank + 1
        return ranks

    rx = _rank(x)
    ry = _rank(y)

    d_sq = sum((rx[i] - ry[i]) ** 2 for i in range(n))
    rho = 1 - (6 * d_sq) / (n * (n**2 - 1))
    return round(rho, 6)


def compute_factor_ic(
    snapshots: List[Dict[str, Any]],
    factor_name: str,
    forward_days: int = 7,
) -> Dict[str, Any]:
    """
    스냅샷 아카이브에서 특정 팩터의 IC(Information Coefficient) 계산.

    Args:
        snapshots: 날짜순 정렬된 스냅샷 리스트
        factor_name: FACTOR_EXTRACTORS 키
        forward_days: 미래 수익률 측정 기간 (영업일)

    Returns:
        {
            "factor": str,
            "ic_mean": float,
            "ic_std": float,
            "icir": float,
            "ic_series": [...],
            "is_significant": bool,
            "decay_alert": bool,
        }
    """
    if factor_name not in FACTOR_EXTRACTORS:
        return {"factor": factor_name, "error": f"알 수 없는 팩터: {factor_name}"}

    extractor = FACTOR_EXTRACTORS[factor_name]
    ic_series: List[float] = []

    for i in range(len(snapshots) - 1):
        snap = snapshots[i]
        recs = snap.get("recommendations", [])
        if len(recs) < 5:
            continue

        future_snap = None
        for j in range(i + 1, min(i + forward_days + 1, len(snapshots))):
            future_snap = snapshots[j]
        if not future_snap:
            continue

        future_prices: Dict[str, float] = {}
        for r in future_snap.get("recommendations", []):
            t = r.get("ticker", "")
            p = r.get("price")
            if t and p:
                try:
                    future_prices[t] = float(p)
                except (TypeError, ValueError):
                    pass

        factor_vals: List[float] = []
        returns: List[float] = []

        for stock in recs:
            ticker = stock.get("ticker", "")
            price = stock.get("price")
            fv = extractor(stock)

            if fv is None or price is None or ticker not in future_prices:
                continue

            try:
                price_f = float(price)
                fp = future_prices[ticker]
                if price_f <= 0:
                    continue
                ret = (fp - price_f) / price_f * 100
                factor_vals.append(float(fv))
                returns.append(ret)
            except (TypeError, ValueError):
                continue

        if len(factor_vals) >= 5:
            ic = _spearman_rank_corr(factor_vals, returns)
            ic_series.append(ic)

    if not ic_series:
        return {
            "factor": factor_name,
            "ic_mean": 0,
            "ic_std": 0,
            "icir": 0,
            "ic_series": [],
            "is_significant": False,
            "decay_alert": False,
            "note": "IC 계산 불가 (데이터 부족)",
        }

    ic_mean = statistics.mean(ic_series)
    ic_std = statistics.stdev(ic_series) if len(ic_series) >= 3 else 0
    icir = ic_mean / ic_std if ic_std > 1e-6 else 0

    # 최근 5개 IC vs 전체: 붕괴 감지
    decay_alert = False
    if len(ic_series) >= 10:
        recent_mean = statistics.mean(ic_series[-5:])
        overall_mean = statistics.mean(ic_series)
        if overall_mean > 0.03 and recent_mean < 0.01:
            decay_alert = True
        elif overall_mean > 0.05 and recent_mean < overall_mean * 0.3:
            decay_alert = True

    return {
        "factor": factor_name,
        "ic_mean": round(ic_mean, 5),
        "ic_std": round(ic_std, 5),
        "icir": round(icir, 3),
        "ic_series": [round(v, 5) for v in ic_series[-30:]],
        "is_significant": abs(ic_mean) > 0.05 and abs(icir) > 0.4,
        "decay_alert": decay_alert,
        "sample_count": len(ic_series),
    }


def scan_all_factors(
    forward_days: int = 7,
) -> Dict[str, Any]:
    """
    모든 팩터의 IC를 스캔하여 유효성 리포트 생성.
    """
    from api.workflows.archiver import load_snapshots_range

    snapshots = load_snapshots_range(60)
    if len(snapshots) < 5:
        return {
            "status": "insufficient_data",
            "snapshot_count": len(snapshots),
            "factors": {},
        }

    results: Dict[str, Dict[str, Any]] = {}
    significant: List[str] = []
    decaying: List[str] = []

    for factor_name in FACTOR_EXTRACTORS:
        ic_result = compute_factor_ic(snapshots, factor_name, forward_days)
        results[factor_name] = ic_result

        if ic_result.get("is_significant"):
            significant.append(factor_name)
        if ic_result.get("decay_alert"):
            decaying.append(factor_name)

    ranking = sorted(
        results.items(),
        key=lambda x: abs(x[1].get("icir", 0)),
        reverse=True,
    )

    return {
        "status": "ok",
        "snapshot_count": len(snapshots),
        "forward_days": forward_days,
        "factors": results,
        "ranking": [{"factor": k, "icir": v.get("icir", 0)} for k, v in ranking],
        "significant_factors": significant,
        "decaying_factors": decaying,
        "scanned_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }


def scan_all_factors_multi_window(
    windows: List[int] | None = None,
) -> Dict[str, Any]:
    """7/14/30일 윈도우별 IC를 스캔하고 히스토리에 저장."""
    if windows is None:
        windows = [7, 14, 30]

    from api.workflows.archiver import load_snapshots_range

    snapshots = load_snapshots_range(90)
    if len(snapshots) < 5:
        return {
            "status": "insufficient_data",
            "snapshot_count": len(snapshots),
            "windows": {},
        }

    all_results: Dict[int, Dict[str, Any]] = {}
    for w in windows:
        result = scan_all_factors(forward_days=w)
        all_results[w] = result
        if result.get("status") == "ok":
            save_ic_snapshot(result)

    return {
        "status": "ok",
        "snapshot_count": len(snapshots),
        "windows": {str(w): r for w, r in all_results.items()},
        "scanned_at": now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
    }


def compute_monthly_rollup(days: int = 30) -> Dict[str, Any]:
    """factor_ic_history.json에서 최근 N일 구간의 팩터별 평균 ICIR 롤업."""
    history: List[Dict[str, Any]] = []
    try:
        with open(IC_CACHE_PATH, "r", encoding="utf-8") as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

    if not history:
        return {}

    cutoff = now_kst() - __import__("datetime").timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%dT")

    recent = [h for h in history if (h.get("date") or "") >= cutoff_str]
    if not recent:
        return {}

    agg: Dict[str, List[float]] = {}
    for entry in recent:
        for fname, fdata in entry.get("factors", {}).items():
            icir = fdata.get("icir")
            if icir is not None:
                agg.setdefault(fname, []).append(float(icir))

    by_factor = []
    for fname, vals in agg.items():
        avg_icir = round(sum(vals) / len(vals), 3) if vals else 0
        by_factor.append({
            "factor": fname,
            "avg_icir": avg_icir,
            "obs_days": len(vals),
        })

    by_factor.sort(key=lambda x: abs(x["avg_icir"]), reverse=True)

    return {
        "period_label": f"최근 {days}일",
        "window_days": days,
        "obs_entries": len(recent),
        "by_factor": by_factor,
        "top_factors": [f["factor"] for f in by_factor[:5]],
    }


def save_ic_snapshot(scan_result: Dict[str, Any]):
    """IC 스캔 결과를 히스토리에 누적 저장 (동일 날짜+윈도우 중복 방지)."""
    history: List[Dict[str, Any]] = []
    try:
        with open(IC_CACHE_PATH, "r", encoding="utf-8") as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    raw_date = scan_result.get("scanned_at", now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00"))
    date_key = raw_date[:10]  # yyyy-mm-dd
    fwd = scan_result.get("forward_days", 7)

    entry = {
        "date": raw_date,
        "date_key": date_key,
        "forward_days": fwd,
        "factors": {},
    }
    for name, data in scan_result.get("factors", {}).items():
        entry["factors"][name] = {
            "ic_mean": data.get("ic_mean", 0),
            "icir": data.get("icir", 0),
            "significant": data.get("is_significant", False),
            "decay": data.get("decay_alert", False),
            "sample_count": data.get("sample_count", 0),
        }

    history = [
        h for h in history
        if not (h.get("date_key", h.get("date", "")[:10]) == date_key
                and h.get("forward_days", 7) == fwd)
    ]
    history.append(entry)
    history = history[-180:]

    with open(IC_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
