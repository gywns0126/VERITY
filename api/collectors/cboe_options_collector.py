"""
CBOE 풋/콜 비율 수집기
panic_stages 트리거 및 vci_bonus 보정 직결

데이터 소스:
  1) CBOE CDN 실시간 SPX 옵션 데이터 (volume 기반 PCR)
  2) yfinance SPY 옵션 체인 (보조/크로스밸리데이션)
  3) 기존 portfolio.json의 history_20d 누적 (매일 append)
"""
from __future__ import annotations
import logging, requests, json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CBOE_CDN = "https://cdn.cboe.com/api/global/delayed_quotes/options"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,*/*;q=0.8",
}

_FALLBACK_KEYS: Dict[str, Any] = {
    "total_pcr_latest": None,
    "total_pcr_avg_20d": None,
    "spx_realtime_pcr": None,
    "pcr_z_score": None,
    "equity_pcr_latest": None,
    "history_20d": [],
}

_PORTFOLIO_PATH = Path(__file__).resolve().parents[2] / "data" / "portfolio.json"


def _pcr_to_signal(pcr: float) -> str:
    if pcr >= 1.3:   return "EXTREME_FEAR"
    elif pcr >= 1.1: return "FEAR"
    elif pcr >= 0.9: return "NEUTRAL"
    elif pcr >= 0.7: return "GREED"
    else:            return "EXTREME_GREED"


def _load_existing_history() -> List[Dict]:
    """기존 portfolio.json에서 history_20d를 읽어 누적 히스토리로 활용."""
    try:
        if _PORTFOLIO_PATH.exists():
            with open(_PORTFOLIO_PATH, "r") as f:
                data = json.load(f)
            return data.get("cboe_pcr", {}).get("history_20d", [])
    except Exception:
        pass
    return []


def get_spx_pcr_from_cdn() -> Dict[str, Any]:
    """CBOE CDN에서 SPX 전체 옵션 볼륨 기반 PCR 계산."""
    try:
        resp = requests.get(
            f"{CBOE_CDN}/_SPX.json", headers=_HEADERS, timeout=15,
        )
        resp.raise_for_status()
        options = resp.json().get("data", {}).get("options", [])
        if not options:
            return {"ok": False, "error": "no SPX options data"}

        put_vol = 0
        call_vol = 0
        for o in options:
            opt_sym = o.get("option", "")
            vol = int(float(o.get("volume", 0) or 0))
            if not opt_sym:
                continue
            if "P" in opt_sym[3:10]:
                put_vol += vol
            else:
                call_vol += vol

        pcr = put_vol / call_vol if call_vol > 0 else 1.0
        return {
            "ok": True,
            "put_call_ratio": round(pcr, 4),
            "put_volume": put_vol,
            "call_volume": call_vol,
            "signal": _pcr_to_signal(pcr),
            "source": "cboe_cdn_spx",
        }
    except Exception as e:
        logger.error("[CBOE] CDN SPX PCR 실패: %s", e)
        return {"ok": False, "error": str(e)}


def get_spy_pcr_from_yfinance() -> Dict[str, Any]:
    """yfinance SPY 옵션 체인에서 PCR 계산 (보조 소스)."""
    try:
        import yfinance as yf
    except ImportError:
        return {"ok": False, "error": "yfinance not installed"}

    try:
        spy = yf.Ticker("SPY")
        exp_dates = spy.options
        if not exp_dates:
            return {"ok": False, "error": "no SPY expiration dates"}

        total_puts = 0
        total_calls = 0
        for exp in exp_dates[:3]:
            chain = spy.option_chain(exp)
            total_puts += chain.puts["volume"].fillna(0).sum()
            total_calls += chain.calls["volume"].fillna(0).sum()

        pcr = total_puts / total_calls if total_calls > 0 else 1.0
        return {
            "ok": True,
            "put_call_ratio": round(pcr, 4),
            "put_volume": int(total_puts),
            "call_volume": int(total_calls),
            "signal": _pcr_to_signal(pcr),
            "source": "yfinance_spy",
        }
    except Exception as e:
        logger.error("[CBOE] yfinance SPY PCR 실패: %s", e)
        return {"ok": False, "error": str(e)}


def get_pcr_composite_signal() -> dict:
    """복합 PCR 시그널: yfinance SPY 우선(일간 볼륨 안정), CDN SPX 보조 + 히스토리 누적."""
    spy = get_spy_pcr_from_yfinance()
    spx = get_spx_pcr_from_cdn()

    primary = spy if spy.get("ok") else spx
    if not primary.get("ok"):
        return {
            "signal": "NEUTRAL",
            "vci_adjustment": 0.0,
            "panic_trigger": False,
            "panic_reason": None,
            **_FALLBACK_KEYS,
        }

    latest_pcr = primary["put_call_ratio"]

    history = _load_existing_history()
    today_str = date.today().isoformat()
    if not history or history[-1].get("date") != today_str:
        history.append({"date": today_str, "pcr": latest_pcr})
    else:
        history[-1]["pcr"] = latest_pcr

    cutoff = (date.today() - timedelta(days=30)).isoformat()
    history = [h for h in history if h.get("date", "") >= cutoff]
    history = sorted(history, key=lambda x: x["date"])
    history_20d = history[-20:]

    values = [h["pcr"] for h in history_20d]
    mean = sum(values) / len(values) if values else latest_pcr
    std = (sum((v - mean)**2 for v in values) / len(values)) ** 0.5 if len(values) > 1 else 0.0
    z_score = (latest_pcr - mean) / std if std > 0 else 0.0

    if latest_pcr >= 1.3:   vci_adj = +6.0
    elif latest_pcr >= 1.1: vci_adj = +3.0
    elif latest_pcr >= 0.9: vci_adj = 0.0
    elif latest_pcr >= 0.7: vci_adj = -2.0
    else:                   vci_adj = -5.0

    panic = latest_pcr >= 1.4 or z_score >= 2.0

    equity_pcr = spy.get("put_call_ratio") if spy.get("ok") else None

    return {
        "total_pcr_latest":    round(latest_pcr, 4),
        "total_pcr_avg_20d":   round(mean, 4),
        "spx_realtime_pcr":    spx.get("put_call_ratio") if spx.get("ok") else None,
        "pcr_z_score":         round(z_score, 3),
        "signal":              _pcr_to_signal(latest_pcr),
        "vci_adjustment":      vci_adj,
        "panic_trigger":       panic,
        "panic_reason":        f"PCR={latest_pcr:.2f}, Z={z_score:.1f}" if panic else None,
        "equity_pcr_latest":   equity_pcr,
        "history_20d":         history_20d,
    }
