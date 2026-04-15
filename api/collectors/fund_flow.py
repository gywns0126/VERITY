"""
ICI 펀드 플로우 + ETF 자금 유출입 (EPFR 무료 프록시)

EPFR 유료 구독 대신:
  1. ETF 거래량·가격 변동으로 자금 유출입 추정 (yfinance)
  2. 주요 ETF AUM 변화로 로테이션 시그널 산출

추적 ETF:
  - SPY (S&P500), QQQ (나스닥), IWM (소형주)
  - TLT (장기국채), HYG (하이일드), LQD (투자등급)
  - GLD (금), USO (원유)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_EQUITY_ETFS = ["SPY", "QQQ", "IWM", "DIA", "VTI"]
_BOND_ETFS = ["TLT", "IEF", "HYG", "LQD", "BND"]
_SAFE_HAVEN_ETFS = ["GLD", "SHV", "TIP"]
_COMMODITY_ETFS = ["USO", "GLD", "SLV"]

_ALL_ETFS = list(dict.fromkeys(
    _EQUITY_ETFS + _BOND_ETFS + _SAFE_HAVEN_ETFS + _COMMODITY_ETFS
))


def collect_fund_flows(
    etf_tickers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """ETF 기반 자금 유출입 추정 + 로테이션 시그널."""
    tickers = etf_tickers or _ALL_ETFS

    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance 미설치")
        return {"ok": False, "error": "yfinance not installed"}

    etf_flows = {}
    equity_score = 0
    bond_score = 0
    safe_score = 0

    for ticker in tickers:
        try:
            etf = yf.Ticker(ticker)
            hist = etf.history(period="1mo")
            if hist is None or hist.empty or len(hist) < 5:
                etf_flows[ticker] = {"ok": False, "error": "insufficient data"}
                continue

            close = hist["Close"]
            volume = hist["Volume"]

            recent_5d_vol = volume.iloc[-5:].mean()
            prev_5d_vol = volume.iloc[-10:-5].mean() if len(volume) >= 10 else recent_5d_vol

            vol_change_pct = ((recent_5d_vol - prev_5d_vol) / prev_5d_vol * 100
                              if prev_5d_vol > 0 else 0)

            price_1w = ((close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] * 100
                        if len(close) >= 5 else 0)
            price_1m = ((close.iloc[-1] - close.iloc[0]) / close.iloc[0] * 100
                        if len(close) >= 2 else 0)

            money_flow_1w = price_1w * (recent_5d_vol / 1e6)

            if price_1w > 0 and vol_change_pct > 10:
                flow_signal = "strong_inflow"
            elif price_1w > 0:
                flow_signal = "inflow"
            elif price_1w < 0 and vol_change_pct > 10:
                flow_signal = "strong_outflow"
            elif price_1w < 0:
                flow_signal = "outflow"
            else:
                flow_signal = "neutral"

            etf_flows[ticker] = {
                "ok": True,
                "price_1w_pct": round(price_1w, 2),
                "price_1m_pct": round(price_1m, 2),
                "avg_volume_5d": int(recent_5d_vol),
                "volume_change_pct": round(vol_change_pct, 1),
                "money_flow_1w": round(money_flow_1w, 1),
                "flow_signal": flow_signal,
                "last_close": round(float(close.iloc[-1]), 2),
            }

            if ticker in _EQUITY_ETFS:
                equity_score += money_flow_1w
            elif ticker in _BOND_ETFS:
                bond_score += money_flow_1w
            if ticker in _SAFE_HAVEN_ETFS:
                safe_score += money_flow_1w

        except Exception as e:
            logger.warning("ETF flow failed for %s: %s", ticker, e)
            etf_flows[ticker] = {"ok": False, "error": str(e)}

    ok_count = sum(1 for v in etf_flows.values() if v.get("ok"))
    if ok_count == 0:
        return {"ok": False, "etf_flows": etf_flows, "error": "no etf data"}

    rotation_signal = _compute_rotation(equity_score, bond_score, safe_score)

    return {
        "ok": True,
        "etf_flows": etf_flows,
        "equity_flow_score": round(equity_score, 1),
        "bond_flow_score": round(bond_score, 1),
        "safe_haven_flow_score": round(safe_score, 1),
        "rotation_signal": rotation_signal["signal"],
        "rotation_detail": rotation_signal,
        "etf_count": ok_count,
    }


def _compute_rotation(
    equity: float, bond: float, safe: float,
) -> Dict[str, Any]:
    """주식/채권/안전자산 자금 흐름 기반 로테이션 시그널."""
    total = abs(equity) + abs(bond) + abs(safe)
    if total == 0:
        return {"signal": "neutral", "confidence": 0, "detail": "insufficient data"}

    if equity > 0 and equity > bond and equity > safe:
        signal = "risk_on"
        conf = min(100, int(equity / total * 100))
        detail = "주식 유입 우위 — 위험 선호 환경"
    elif safe > 0 and safe > equity and bond > 0:
        signal = "risk_off"
        conf = min(100, int((safe + bond) / total * 50))
        detail = "안전자산·채권 유입 — 위험 회피 환경"
    elif bond > 0 and bond > equity:
        signal = "defensive"
        conf = min(100, int(bond / total * 100))
        detail = "채권 유입 우위 — 방어적 포지셔닝"
    elif equity < 0 and bond < 0:
        signal = "cash_flight"
        conf = min(100, int(abs(equity + bond) / total * 100))
        detail = "주식·채권 동반 유출 — 현금 선호"
    else:
        signal = "neutral"
        conf = 20
        detail = "뚜렷한 자금 흐름 방향 없음"

    return {
        "signal": signal,
        "confidence": conf,
        "detail": detail,
        "equity_score": round(equity, 1),
        "bond_score": round(bond, 1),
        "safe_score": round(safe, 1),
    }
