"""
CBOE 풋/콜 비율 수집기
panic_stages 트리거 및 vci_bonus 보정 직결
"""
from __future__ import annotations
import logging, requests
from datetime import datetime, date, timedelta

logger = logging.getLogger(__name__)

CBOE_TOTAL_PC_URL  = "https://www.cboe.com/publish/scheduledtask/mktdata/datahouse/totalpc.csv"
CBOE_EQUITY_PC_URL = "https://www.cboe.com/publish/scheduledtask/mktdata/datahouse/equitypc.csv"
CBOE_CDN           = "https://cdn.cboe.com/api/global/delayed_quotes/options"

def _pcr_to_signal(pcr: float) -> str:
    if pcr >= 1.3:   return "EXTREME_FEAR"
    elif pcr >= 1.1: return "FEAR"
    elif pcr >= 0.9: return "NEUTRAL"
    elif pcr >= 0.7: return "GREED"
    else:            return "EXTREME_GREED"

def get_historical_pcr(days: int = 20, pcr_type: str = "total") -> list[dict]:
    url = CBOE_TOTAL_PC_URL if pcr_type == "total" else CBOE_EQUITY_PC_URL
    try:
        lines = requests.get(url, timeout=15).text.strip().split("\n")
        data_lines = [l for l in lines if l.strip() and not l.upper().startswith("DATE")]
        results, cutoff = [], date.today() - timedelta(days=days)
        for line in data_lines[-(days * 2):]:
            parts = line.strip().split(",")
            if len(parts) < 3: continue
            try:
                dt  = datetime.strptime(parts[0].strip(), "%m/%d/%Y").date()
                pcr = float(parts[2].strip())
                if dt >= cutoff:
                    results.append({"date": dt.isoformat(), "pcr": pcr})
            except (ValueError, IndexError):
                continue
        return sorted(results, key=lambda x: x["date"])
    except Exception as e:
        logger.error(f"[CBOE] 히스토리 조회 실패: {e}")
        return []

def get_realtime_pcr(symbol: str = "_SPX") -> dict:
    try:
        data    = requests.get(f"{CBOE_CDN}/{symbol}.json", timeout=10).json().get("data", {})
        options = data.get("options", [])
        put_vol  = sum(int(o.get("put_volume",0) or 0) for o in options)
        call_vol = sum(int(o.get("call_volume",0) or 0) for o in options)
        pcr = put_vol / call_vol if call_vol > 0 else 1.0
        return {"symbol": symbol, "put_call_ratio": round(pcr, 4),
                "put_volume": put_vol, "call_volume": call_vol,
                "signal": _pcr_to_signal(pcr)}
    except Exception as e:
        logger.error(f"[CBOE] 실시간 PCR 실패: {e}")
        return {"symbol": symbol, "put_call_ratio": None}

def get_pcr_composite_signal() -> dict:
    history = get_historical_pcr(days=20)
    if not history:
        return {"signal": "NEUTRAL", "vci_adjustment": 0.0,
                "panic_trigger": False, "panic_reason": None}

    latest  = history[-1]["pcr"]
    values  = [h["pcr"] for h in history]
    mean    = sum(values) / len(values)
    std     = (sum((v - mean)**2 for v in values) / len(values)) ** 0.5
    z_score = (latest - mean) / std if std > 0 else 0.0

    if latest >= 1.3:   vci_adj = +6.0
    elif latest >= 1.1: vci_adj = +3.0
    elif latest >= 0.9: vci_adj = 0.0
    elif latest >= 0.7: vci_adj = -2.0
    else:               vci_adj = -5.0

    panic = latest >= 1.4 or z_score >= 2.0

    spx = get_realtime_pcr("_SPX")
    equity = get_historical_pcr(days=5, pcr_type="equity")

    return {
        "total_pcr_latest":    round(latest, 4),
        "total_pcr_avg_20d":   round(mean, 4),
        "spx_realtime_pcr":    spx.get("put_call_ratio"),
        "pcr_z_score":         round(z_score, 3),
        "signal":              _pcr_to_signal(latest),
        "vci_adjustment":      vci_adj,
        "panic_trigger":       panic,
        "panic_reason":        f"PCR={latest:.2f}, Z={z_score:.1f}" if panic else None,
        "equity_pcr_latest":   equity[-1]["pcr"] if equity else None,
        "history_20d":         history,
    }
