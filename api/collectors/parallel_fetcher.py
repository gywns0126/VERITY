"""
병렬 데이터 수집 — Phase 2-A (2026-05-01)

KR (pykrx):
  - WIDE_SCAN_KR_K2_WORKERS = 30 (하드코드, 결정 8 — 환경변수 X)
  - max_workers > 30 → ValueError raise (P50 hung 방지)
  - 첫 호출 30s 초과 → P20 자동 fallback (adaptive degradation)
  - 같은 영업일 OHLCV parquet 캐시 (data/cache/k2_ohlcv/{date}/{ticker}.parquet)
  - fail_rate > 1% → Telegram CRITICAL + 다음 cron 1회 skip 신호

US (yfinance):
  - WIDE_SCAN_US_P3_WORKERS = 50 (P3 측정 권고)
  - 가격: yf.download batch 우선
  - Fundamentals: yf.Ticker.info 단건 ThreadPool

코드 레벨 가드:
  - 모든 future 에 timeout 강제 (pykrx wrapper 의무)
  - fail_rate alert 임계 1%
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

# 결정 8 — KR 하드코드 (환경변수 노출 금지)
WIDE_SCAN_KR_K2_WORKERS = 30

# 결정 9 — US P3 권고
WIDE_SCAN_US_P3_WORKERS = 50

# adaptive degradation 임계
KR_FIRST_CALL_FALLBACK_THRESHOLD_S = 30.0  # 첫 호출 30s 초과 → P20
KR_FAIL_RATE_ALERT_THRESHOLD = 0.01  # 1%

# Per-future timeout (pykrx wrapper 의무 — 결정 16)
KR_PER_TICKER_TIMEOUT_S = 10.0
US_PER_TICKER_TIMEOUT_S = 15.0

# OHLCV 캐시
K2_OHLCV_CACHE_DIR = Path("data/cache/k2_ohlcv")


def _enforce_kr_workers(max_workers: int) -> None:
    """결정 8 — P50 절대 금지 코드 레벨 차단."""
    if max_workers > WIDE_SCAN_KR_K2_WORKERS:
        raise ValueError(
            f"KR pykrx max_workers={max_workers} cannot exceed {WIDE_SCAN_KR_K2_WORKERS} "
            f"(P50 hung risk, KRX 방어 임계 30~50, run 25211054902 실측)"
        )


def _kst_business_day(now: Optional[datetime] = None) -> str:
    """KST 기준 가장 가까운 영업일 (월~금). 휴장일 휴리스틱은 별도 호출자가 처리."""
    if now is None:
        now = datetime.now(ZoneInfo("Asia/Seoul"))
    while now.weekday() >= 5:  # Sat=5, Sun=6
        now -= timedelta(days=1)
    return now.strftime("%Y%m%d")


def _cache_path(ticker: str, bas_dd: str) -> Path:
    """확장자는 .pkl — pandas to_pickle 사용 (pyarrow 의존성 회피).

    영업일 단위로 invalidate 되는 캐시라 pickle 포맷 호환성 우려 없음.
    """
    return K2_OHLCV_CACHE_DIR / bas_dd / f"{ticker}.pkl"


def _read_cache(ticker: str, bas_dd: str):
    p = _cache_path(ticker, bas_dd)
    if not p.exists():
        return None
    try:
        import pandas as pd
        return pd.read_pickle(p)
    except Exception:
        # 캐시 손상 시 graceful degradation
        try:
            p.unlink()
        except Exception:
            pass
        return None


def _write_cache(ticker: str, bas_dd: str, df) -> None:
    try:
        p = _cache_path(ticker, bas_dd)
        p.parent.mkdir(parents=True, exist_ok=True)
        df.to_pickle(p)
    except Exception:
        # 캐시 쓰기 실패는 무시 (운영 데이터 자체는 정상)
        pass


def _kr_fetch_one_ohlcv(ticker: str, start: str, end: str, bas_dd: str):
    """단건 pykrx OHLCV — 캐시 확인 → API 호출 → 캐시 쓰기."""
    cached = _read_cache(ticker, bas_dd)
    if cached is not None and len(cached) > 50:
        return ticker, cached, True  # cache hit
    from pykrx import stock
    df = stock.get_market_ohlcv(start, end, ticker)
    if df is not None and len(df) > 50:
        _write_cache(ticker, bas_dd, df)
        return ticker, df, False
    return ticker, None, False


def fetch_kr_ohlcv_parallel(
    tickers: list[str],
    max_workers: int = WIDE_SCAN_KR_K2_WORKERS,
    period_days: int = 370,
    timeout_per_ticker: float = KR_PER_TICKER_TIMEOUT_S,
    enable_adaptive_fallback: bool = True,
    on_alert: Optional[Callable[[str, dict], None]] = None,
) -> dict:
    """KR pykrx OHLCV 병렬 수집 (P30 권고).

    Args:
        on_alert: (level, payload) 콜백. Telegram 발송 등 외부 처리.

    Returns:
        {
            "data": {ticker: pd.DataFrame},
            "elapsed_s": float,
            "workers_used": int,
            "first_call_ms": int,
            "cache_hit_rate": float,
            "fail_rate": float,
            "fallback_triggered": bool,
            "fail_rate_alert_fired": bool,
        }
    """
    _enforce_kr_workers(max_workers)

    if not tickers:
        return {
            "data": {}, "elapsed_s": 0.0, "workers_used": 0,
            "first_call_ms": 0, "cache_hit_rate": 0.0, "fail_rate": 0.0,
            "fallback_triggered": False, "fail_rate_alert_fired": False,
        }

    end = _kst_business_day()
    today = datetime.strptime(end, "%Y%m%d")
    start = (today - timedelta(days=period_days)).strftime("%Y%m%d")

    # 첫 호출 가드 — 30s 초과 시 P20 fallback
    first_t0 = time.time()
    first_ticker = tickers[0]
    try:
        _, first_df, first_cache_hit = _kr_fetch_one_ohlcv(first_ticker, start, end, end)
    except Exception:
        first_df = None
        first_cache_hit = False
    first_call_ms = int((time.time() - first_t0) * 1000)

    workers_to_use = max_workers
    fallback = False
    if (
        enable_adaptive_fallback
        and first_call_ms / 1000.0 > KR_FIRST_CALL_FALLBACK_THRESHOLD_S
        and max_workers > 20
    ):
        workers_to_use = 20
        fallback = True
        if on_alert:
            on_alert("WARN", {
                "event": "kr_adaptive_fallback",
                "from_workers": max_workers,
                "to_workers": 20,
                "first_call_ms": first_call_ms,
                "reason": "first_call_threshold_exceeded",
            })

    data: dict = {}
    cache_hits = 0
    if first_df is not None and len(first_df) > 50:
        data[first_ticker] = first_df
        if first_cache_hit:
            cache_hits += 1

    remaining = tickers[1:]
    fails: list[str] = []

    pool_t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers_to_use) as ex:
        futures = {
            ex.submit(_kr_fetch_one_ohlcv, t, start, end, end): t
            for t in remaining
        }
        for fu in as_completed(futures, timeout=max(timeout_per_ticker * 4, 60)):
            tk = futures[fu]
            try:
                _, df, hit = fu.result(timeout=timeout_per_ticker)
                if df is not None and len(df) > 50:
                    data[tk] = df
                    if hit:
                        cache_hits += 1
                else:
                    fails.append(tk)
            except (FutTimeout, Exception):
                fails.append(tk)
    pool_elapsed = time.time() - pool_t0

    total_attempts = len(tickers)
    fail_rate = len(fails) / total_attempts if total_attempts else 0.0
    cache_hit_rate = cache_hits / total_attempts if total_attempts else 0.0

    fail_rate_alert = False
    if fail_rate > KR_FAIL_RATE_ALERT_THRESHOLD:
        fail_rate_alert = True
        if on_alert:
            on_alert("CRITICAL", {
                "event": "kr_fail_rate_exceeded",
                "fail_rate": fail_rate,
                "threshold": KR_FAIL_RATE_ALERT_THRESHOLD,
                "fail_count": len(fails),
                "total": total_attempts,
                "fail_sample": fails[:10],
            })

    elapsed_total = (time.time() - first_t0)
    return {
        "data": data,
        "elapsed_s": round(elapsed_total, 2),
        "pool_elapsed_s": round(pool_elapsed, 2),
        "workers_used": workers_to_use,
        "first_call_ms": first_call_ms,
        "cache_hit_rate": round(cache_hit_rate, 4),
        "fail_rate": round(fail_rate, 4),
        "fallback_triggered": fallback,
        "fail_rate_alert_fired": fail_rate_alert,
        "success_count": len(data),
        "fail_count": len(fails),
        "fail_tickers_sample": fails[:10],
    }


def fetch_us_price_batch(
    tickers: list[str],
    period: str = "1y",
) -> dict:
    """US yf.download batch — 가격 데이터.

    Returns: {data: {ticker: DataFrame}, elapsed_s, fail_count, ...}
    """
    if not tickers:
        return {"data": {}, "elapsed_s": 0.0, "success_count": 0, "fail_count": 0, "fail_sample": []}

    import yfinance as yf
    t0 = time.time()
    try:
        df = yf.download(
            tickers=" ".join(tickers),
            period=period,
            group_by="ticker",
            threads=True,
            progress=False,
            auto_adjust=False,
        )
    except Exception as e:
        return {"data": {}, "elapsed_s": round(time.time() - t0, 2), "error": str(e),
                "success_count": 0, "fail_count": len(tickers), "fail_sample": tickers[:10]}

    elapsed = time.time() - t0
    data = {}
    fails = []
    for tk in tickers:
        try:
            sub = df[tk] if len(tickers) > 1 else df
            if sub is not None and len(sub.dropna(how="all")) >= 50:
                data[tk] = sub
            else:
                fails.append(tk)
        except Exception:
            fails.append(tk)
    return {
        "data": data,
        "elapsed_s": round(elapsed, 2),
        "success_count": len(data),
        "fail_count": len(fails),
        "fail_sample": fails[:10],
    }


def fetch_us_fundamentals_parallel(
    tickers: list[str],
    max_workers: int = WIDE_SCAN_US_P3_WORKERS,
    timeout_per_ticker: float = US_PER_TICKER_TIMEOUT_S,
) -> dict:
    """US yf.Ticker.info 병렬 수집 (주 1회 권고)."""
    if not tickers:
        return {"data": {}, "elapsed_s": 0.0, "success_count": 0, "fail_count": 0}

    import yfinance as yf

    def _one(tk: str) -> tuple[str, dict | None]:
        try:
            info = yf.Ticker(tk).info or {}
            return tk, info
        except Exception:
            return tk, None

    t0 = time.time()
    data: dict = {}
    fails: list[str] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_one, t): t for t in tickers}
        for fu in as_completed(futures, timeout=max(timeout_per_ticker * 4, 60)):
            tk = futures[fu]
            try:
                _, info = fu.result(timeout=timeout_per_ticker)
                if info:
                    data[tk] = info
                else:
                    fails.append(tk)
            except (FutTimeout, Exception):
                fails.append(tk)

    elapsed = time.time() - t0
    return {
        "data": data,
        "elapsed_s": round(elapsed, 2),
        "workers_used": max_workers,
        "success_count": len(data),
        "fail_count": len(fails),
        "fail_rate": round(len(fails) / len(tickers), 4) if tickers else 0.0,
        "fail_sample": fails[:10],
    }
