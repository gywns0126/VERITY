"""
Cross-asset 30일 rolling correlation — Sprint 11 결함 4 후속 (2026-05-01).

5자산: 주식(S&P500), 채권(10Y yield), 금, USD index, 원유.
30일 일별 변화율 (close pct_change) 의 pearson correlation matrix 산출.

진단 신호:
  - "decoupled"     : 모든 |pair corr| < 0.3 — 자산 간 분산 효과 강함 (정상)
  - "all_correlated": 모든 |pair corr| > 0.7 — 위기 모드 (bond 도 risk-on/off 동기화)
  - "normal"        : 그 사이

VAMS 가 corr 한도 강제 (예: 강한 +상관 자산군 누적 비중 제한) 는 다음 단계.
이번 commit 은 데이터 흐름만 — macro["cross_asset_corr"] 부착.

근거: 베테랑 결함 4 — "Correlation 무시 = 사실상 단일 베팅". sector_exposure 한도는
있지만 자산군 correlation 한도 부재. 위기 시 모든 자산이 동기화되면 분산 효과 무력화.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# yfinance ticker 매핑
ASSET_TICKERS: Dict[str, str] = {
    "stock": "^GSPC",   # S&P 500
    "bond_yield": "^TNX",  # 10Y Treasury yield (변동율 = 금리 변화)
    "gold": "GC=F",     # Gold futures
    "usd": "DX-Y.NYB",  # USD Index
    "oil": "CL=F",      # WTI Crude
}

WINDOW_DAYS = 30
DECOUPLED_MAX_ABS = 0.3
ALL_CORRELATED_MIN_ABS = 0.7


def _fetch_returns(ticker: str, days: int = WINDOW_DAYS + 5) -> Optional[List[float]]:
    """yfinance 에서 daily close → pct_change. 결측 제거."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(period=f"{days + 10}d")
        if hist.empty or len(hist) < days:
            return None
        close = hist["Close"].dropna()
        if len(close) < days:
            return None
        rets = close.pct_change().dropna().tail(days).tolist()
        return [float(r) for r in rets] if rets else None
    except Exception as e:  # noqa: BLE001
        logger.warning("cross_asset_corr fetch %s failed: %s", ticker, e)
        return None


def _pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    if not xs or not ys or len(xs) != len(ys) or len(xs) < 5:
        return None
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    denom = (vx * vy) ** 0.5
    if denom <= 0:
        return None
    return round(cov / denom, 3)


def compute_cross_asset_corr(window: int = WINDOW_DAYS) -> Dict[str, Any]:
    """5자산 30일 rolling correlation matrix + 진단 신호.

    yfinance 호출 실패 자산은 skip — 가능한 자산 페어만 산출.
    최소 3개 자산 returns 확보돼야 의미 있는 진단.
    """
    returns: Dict[str, List[float]] = {}
    for name, tk in ASSET_TICKERS.items():
        r = _fetch_returns(tk, window + 5)
        if r and len(r) >= window:
            returns[name] = r[-window:]

    if len(returns) < 3:
        return {
            "available": False,
            "reason": "insufficient_assets",
            "fetched": list(returns.keys()),
            "expected": list(ASSET_TICKERS.keys()),
        }

    # 모든 자산이 동일 길이여야 pairwise corr 의미. 가장 짧은 길이로 정렬.
    min_len = min(len(r) for r in returns.values())
    aligned = {k: v[-min_len:] for k, v in returns.items()}

    pairs: Dict[str, float] = {}
    matrix: Dict[str, Dict[str, float]] = {k: {k: 1.0} for k in aligned}
    asset_names = list(aligned.keys())

    abs_corrs: List[Tuple[str, float]] = []
    for i, a in enumerate(asset_names):
        for b in asset_names[i + 1:]:
            c = _pearson(aligned[a], aligned[b])
            if c is None:
                continue
            key = f"{a}_{b}"
            pairs[key] = c
            matrix[a][b] = c
            matrix[b][a] = c
            abs_corrs.append((key, abs(c)))

    if not pairs:
        return {
            "available": False,
            "reason": "no_valid_pairs",
            "fetched": list(returns.keys()),
        }

    abs_corrs.sort(key=lambda x: -x[1])
    max_pair, max_abs = abs_corrs[0]

    all_below = all(abs_c < DECOUPLED_MAX_ABS for _, abs_c in abs_corrs)
    all_above = all(abs_c > ALL_CORRELATED_MIN_ABS for _, abs_c in abs_corrs)
    if all_below:
        signal = "decoupled"
        interp = "자산 간 분산 효과 강함 (정상 환경)"
    elif all_above:
        signal = "all_correlated"
        interp = "모든 자산 동기화 — 위기 모드 가능성. 분산 효과 무력화"
    else:
        signal = "normal"
        interp = "혼합 — 일부 자산만 강한 상관"

    return {
        "available": True,
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "window_days": window,
        "n_assets": len(aligned),
        "assets": asset_names,
        "pairs": pairs,
        "matrix": matrix,
        "max_abs_pair": {"pair": max_pair, "abs_corr": round(max_abs, 3)},
        "regime_signal": signal,
        "interpretation": interp,
        "thresholds": {
            "decoupled_max_abs": DECOUPLED_MAX_ABS,
            "all_correlated_min_abs": ALL_CORRELATED_MIN_ABS,
        },
    }
