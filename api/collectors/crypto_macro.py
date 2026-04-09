"""
크립토 매크로 센서 — 주식 분석 보조 지표
공개 API만 사용 (키 불필요).

5대 지표:
  1. BTC Fear & Greed Index  (Alternative.me)
  2. 바이낸스 펀딩비           (Binance Futures)
  3. 김치 프리미엄             (업비트 vs 바이낸스)
  4. BTC-나스닥 상관계수       (바이낸스 BTC + yfinance NQ)
  5. 스테이블코인 시총         (CoinGecko 무인증)
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

import requests

from api.config import (
    CRYPTO_FUNDING_OVERHEAT,
    CRYPTO_FUNDING_UNDERHEAT,
    CRYPTO_KIMCHI_PREMIUM_WARN,
    CRYPTO_FNG_EXTREME_GREED,
    CRYPTO_FNG_EXTREME_FEAR,
)

_TIMEOUT = 8
_HEADERS = {"User-Agent": "Verity-Terminal/1.0"}


def collect_crypto_macro() -> Dict[str, Any]:
    """5대 크립토 매크로 센서 수집. 개별 실패는 fallback."""
    result: Dict[str, Any] = {"available": False}

    fng = _fetch_fear_and_greed()
    result["fear_and_greed"] = fng

    funding = _fetch_funding_rate()
    result["funding_rate"] = funding

    kimchi = _fetch_kimchi_premium()
    result["kimchi_premium"] = kimchi

    correlation = _fetch_btc_nasdaq_correlation()
    result["btc_nasdaq_corr"] = correlation

    stablecoin = _fetch_stablecoin_mcap()
    result["stablecoin_mcap"] = stablecoin

    ok_count = sum(
        1 for v in [fng, funding, kimchi, correlation, stablecoin]
        if v.get("ok")
    )
    # Framer는 이 플래그로만 UI를 열고 닫음 — 1개라도 성공하면 표시(부분 데이터)
    result["available"] = ok_count >= 1
    result["ok_count"] = ok_count
    result["total"] = 5
    result["composite"] = _compute_composite(result)

    return result


def _fetch_fear_and_greed() -> Dict[str, Any]:
    """Alternative.me Fear & Greed Index."""
    try:
        r = requests.get(
            "https://api.alternative.me/fng/?limit=2&format=json",
            headers=_HEADERS, timeout=_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            return {"ok": False, "error": "empty"}

        today = data[0]
        yesterday = data[1] if len(data) > 1 else None

        value = int(today["value"])
        label = today.get("value_classification", "")
        prev_value = int(yesterday["value"]) if yesterday else None
        change = (value - prev_value) if prev_value is not None else None

        signal = "neutral"
        if value >= CRYPTO_FNG_EXTREME_GREED:
            signal = "extreme_greed"
        elif value >= 60:
            signal = "greed"
        elif value <= CRYPTO_FNG_EXTREME_FEAR:
            signal = "extreme_fear"
        elif value <= 40:
            signal = "fear"

        return {
            "ok": True,
            "value": value,
            "label": label,
            "prev_value": prev_value,
            "change": change,
            "signal": signal,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def _fetch_funding_rate() -> Dict[str, Any]:
    """바이낸스 BTC/USDT 무기한 선물 펀딩비."""
    try:
        r = requests.get(
            "https://fapi.binance.com/fapi/v1/fundingRate",
            params={"symbol": "BTCUSDT", "limit": 3},
            headers=_HEADERS, timeout=_TIMEOUT,
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return {"ok": False, "error": "empty"}

        latest = rows[-1]
        rate = float(latest["fundingRate"])
        rate_pct = round(rate * 100, 4)

        signal = "neutral"
        if rate_pct >= CRYPTO_FUNDING_OVERHEAT:
            signal = "long_overheat"
        elif rate_pct <= CRYPTO_FUNDING_UNDERHEAT:
            signal = "short_overheat"

        prev_rate = float(rows[-2]["fundingRate"]) * 100 if len(rows) >= 2 else None

        return {
            "ok": True,
            "rate": rate,
            "rate_pct": rate_pct,
            "prev_rate_pct": round(prev_rate, 4) if prev_rate is not None else None,
            "signal": signal,
            "timestamp": latest.get("fundingTime"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def _fetch_kimchi_premium() -> Dict[str, Any]:
    """업비트 BTC 원화가 vs 바이낸스 BTC USDT가 → 김프(%)."""
    try:
        upbit_r = requests.get(
            "https://api.upbit.com/v1/ticker?markets=KRW-BTC",
            headers=_HEADERS, timeout=_TIMEOUT,
        )
        upbit_r.raise_for_status()
        upbit_price = float(upbit_r.json()[0]["trade_price"])

        binance_r = requests.get(
            "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
            headers=_HEADERS, timeout=_TIMEOUT,
        )
        binance_r.raise_for_status()
        binance_usd = float(binance_r.json()["price"])

        fx_r = requests.get(
            "https://api.binance.com/api/v3/ticker/price?symbol=USDTKRW",
            headers=_HEADERS, timeout=_TIMEOUT,
        )
        if fx_r.status_code == 200:
            usdt_krw = float(fx_r.json()["price"])
        else:
            usdt_krw = _fallback_usd_krw()

        if not usdt_krw or usdt_krw <= 0:
            usdt_krw = _fallback_usd_krw()

        binance_krw = binance_usd * usdt_krw
        premium_pct = round((upbit_price - binance_krw) / binance_krw * 100, 2) if binance_krw > 0 else 0

        signal = "normal"
        if premium_pct >= CRYPTO_KIMCHI_PREMIUM_WARN:
            signal = "overheated"
        elif premium_pct >= 3.0:
            signal = "elevated"
        elif premium_pct <= -1.0:
            signal = "discount"

        return {
            "ok": True,
            "premium_pct": premium_pct,
            "upbit_krw": upbit_price,
            "binance_usd": binance_usd,
            "usdt_krw": usdt_krw,
            "signal": signal,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def _fallback_usd_krw() -> float:
    """환율 폴백 — 기존 매크로 데이터에서 가져오거나 yfinance."""
    try:
        import yfinance as yf
        t = yf.Ticker("KRW=X")
        hist = t.history(period="1d")
        if len(hist) >= 1:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return 1380.0


def _fetch_btc_nasdaq_correlation() -> Dict[str, Any]:
    """최근 30일 BTC-나스닥 상관계수. 바이낸스 일봉 + yfinance NQ."""
    try:
        now_ms = int(time.time() * 1000)
        start_ms = now_ms - 45 * 24 * 60 * 60 * 1000

        r = requests.get(
            "https://api.binance.com/api/v3/klines",
            params={
                "symbol": "BTCUSDT",
                "interval": "1d",
                "startTime": start_ms,
                "endTime": now_ms,
                "limit": 45,
            },
            headers=_HEADERS, timeout=_TIMEOUT,
        )
        r.raise_for_status()
        klines = r.json()
        if len(klines) < 15:
            return {"ok": False, "error": "insufficient_btc_data"}

        btc_closes = [float(k[4]) for k in klines]
        btc_returns = [
            (btc_closes[i] - btc_closes[i - 1]) / btc_closes[i - 1]
            for i in range(1, len(btc_closes))
        ]

        import yfinance as yf
        nq = yf.Ticker("^IXIC")
        hist = nq.history(period="2mo")
        if len(hist) < 15:
            return {"ok": False, "error": "insufficient_nq_data"}

        nq_closes = [float(v) for v in hist["Close"].tolist()]
        nq_returns = [
            (nq_closes[i] - nq_closes[i - 1]) / nq_closes[i - 1]
            for i in range(1, len(nq_closes))
        ]

        min_len = min(len(btc_returns), len(nq_returns), 30)
        btc_r = btc_returns[-min_len:]
        nq_r = nq_returns[-min_len:]

        corr = _pearson(btc_r, nq_r)

        signal = "decoupled"
        if corr >= 0.7:
            signal = "strongly_coupled"
        elif corr >= 0.4:
            signal = "moderately_coupled"
        elif corr <= -0.3:
            signal = "inversely_correlated"

        return {
            "ok": True,
            "correlation": round(corr, 3),
            "period_days": min_len,
            "signal": signal,
            "btc_last_price": btc_closes[-1],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def _pearson(x: list, y: list) -> float:
    """피어슨 상관계수 (numpy 없이)."""
    n = len(x)
    if n < 5:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    sx = (sum((xi - mx) ** 2 for xi in x) / n) ** 0.5
    sy = (sum((yi - my) ** 2 for yi in y) / n) ** 0.5
    if sx == 0 or sy == 0:
        return 0.0
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / n
    return cov / (sx * sy)


def _fetch_stablecoin_mcap() -> Dict[str, Any]:
    """CoinGecko 무인증 — USDT + USDC 시총 합산."""
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": "tether,usd-coin",
                "vs_currencies": "usd",
                "include_market_cap": "true",
                "include_24hr_change": "true",
            },
            headers=_HEADERS, timeout=_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()

        usdt = data.get("tether", {})
        usdc = data.get("usd-coin", {})

        usdt_mcap = usdt.get("usd_market_cap", 0)
        usdc_mcap = usdc.get("usd_market_cap", 0)
        total_mcap = usdt_mcap + usdc_mcap
        total_mcap_b = round(total_mcap / 1e9, 1)

        return {
            "ok": True,
            "total_mcap_usd": total_mcap,
            "total_mcap_b": total_mcap_b,
            "usdt_mcap_b": round(usdt_mcap / 1e9, 1),
            "usdc_mcap_b": round(usdc_mcap / 1e9, 1),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def _compute_composite(data: Dict[str, Any]) -> Dict[str, Any]:
    """5개 센서를 종합한 크립토 매크로 온도 (0~100).
    50=중립, 높을수록 위험자산 과열, 낮을수록 공포/기회.
    """
    score = 50.0
    signals = []

    fng = data.get("fear_and_greed", {})
    if fng.get("ok"):
        v = fng["value"]
        score += (v - 50) * 0.3
        if fng["signal"] == "extreme_greed":
            signals.append("크립토 극단적 탐욕")
        elif fng["signal"] == "extreme_fear":
            signals.append("크립토 극단적 공포")

    funding = data.get("funding_rate", {})
    if funding.get("ok"):
        rp = funding["rate_pct"]
        if rp >= CRYPTO_FUNDING_OVERHEAT:
            score += 12
            signals.append(f"펀딩비 과열 {rp:+.4f}%")
        elif rp >= 0.03:
            score += 5
        elif rp <= CRYPTO_FUNDING_UNDERHEAT:
            score -= 12
            signals.append(f"펀딩비 음수 {rp:+.4f}%")
        elif rp <= -0.01:
            score -= 5

    kimchi = data.get("kimchi_premium", {})
    if kimchi.get("ok"):
        kp = kimchi["premium_pct"]
        if kp >= CRYPTO_KIMCHI_PREMIUM_WARN:
            score += 10
            signals.append(f"김프 {kp:+.1f}% 과열")
        elif kp >= 3.0:
            score += 5
        elif kp <= -1.0:
            score -= 5

    corr = data.get("btc_nasdaq_corr", {})
    if corr.get("ok"):
        c = corr["correlation"]
        if c >= 0.7:
            signals.append(f"BTC-NQ 강결합 {c:.2f}")
        elif c <= -0.3:
            signals.append(f"BTC-NQ 역상관 {c:.2f}")

    score = max(0, min(100, round(score)))

    if score >= 75:
        label = "과열"
        risk_level = "high"
    elif score >= 60:
        label = "낙관"
        risk_level = "elevated"
    elif score >= 40:
        label = "중립"
        risk_level = "normal"
    elif score >= 25:
        label = "비관"
        risk_level = "low"
    else:
        label = "공포"
        risk_level = "opportunity"

    return {
        "score": score,
        "label": label,
        "risk_level": risk_level,
        "signals": signals,
    }
