"""
CFTC Commitments of Traders (COT) 리포트 수집기

매주 금요일 공개, 화요일 기준 데이터 (3일 래그).
Disaggregated / Traders in Financial Futures (TFF) 리포트 수집.

핵심: Managed Money 순 롱/숏 변화 추적 → 기관 방향 전환 시그널.
cot_reports 패키지 사용 또는 CFTC PRE 직접 CSV 파싱.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 30
_HEADERS = {"User-Agent": "Verity-Terminal/1.0"}

_CFTC_PRE_BASE = "https://publicreporting.cftc.gov"

_DEFAULT_INSTRUMENTS = {
    "SP500": {"market_name": "E-MINI S&P 500", "cftc_code": "13874A"},
    "NASDAQ": {"market_name": "NASDAQ-100", "cftc_code": "20974A"},
    "CRUDE_OIL": {"market_name": "CRUDE OIL", "cftc_code": "067651"},
    "GOLD": {"market_name": "GOLD", "cftc_code": "088691"},
    "US_TREASURY_10Y": {"market_name": "10-YEAR", "cftc_code": "043602"},
    "VIX": {"market_name": "VIX FUTURES", "cftc_code": "1170E1"},
}


def collect_cot_report(
    instruments: Optional[Dict[str, Dict]] = None,
) -> Dict[str, Any]:
    """CFTC COT 리포트 수집 (cot_reports 패키지 → 직접 API 순 폴백)."""
    instr = instruments or _DEFAULT_INSTRUMENTS

    result = _try_cot_reports_package(instr)
    if result.get("ok"):
        return result

    result = _try_cftc_api(instr)
    if result.get("ok"):
        return result

    return {
        "ok": False,
        "instruments": {},
        "summary": {"overall_signal": "unavailable", "conviction_level": 0},
        "error": "all methods failed",
    }


def _classify_net_position(net_long: float, prev_net_long: float = None) -> str:
    """순 롱 포지션 기반 시그널."""
    if prev_net_long is not None:
        change = net_long - prev_net_long
        if abs(change) > abs(prev_net_long) * 0.20 and prev_net_long != 0:
            return "strong_bullish" if change > 0 else "strong_bearish"
    if net_long > 0:
        return "bullish"
    if net_long < 0:
        return "bearish"
    return "neutral"


def _compute_summary(instruments: Dict[str, Dict]) -> Dict[str, Any]:
    """전체 기관 포지셔닝 요약."""
    bullish = 0
    bearish = 0
    total = 0

    for key, data in instruments.items():
        if not data.get("ok"):
            continue
        total += 1
        sig = data.get("signal", "neutral")
        if "bullish" in sig:
            bullish += 1
        elif "bearish" in sig:
            bearish += 1

    if total == 0:
        return {"overall_signal": "unavailable", "conviction_level": 0}

    ratio = (bullish - bearish) / total
    if ratio >= 0.4:
        signal = "bullish"
    elif ratio <= -0.4:
        signal = "bearish"
    else:
        signal = "neutral"

    conviction = round(abs(ratio) * 100)
    return {
        "overall_signal": signal,
        "conviction_level": conviction,
        "bullish_count": bullish,
        "bearish_count": bearish,
        "total_instruments": total,
    }


def _try_cot_reports_package(instruments: Dict[str, Dict]) -> Dict[str, Any]:
    """cot_reports 패키지로 수집 시도."""
    try:
        import cot_reports as cot
        import pandas as pd
    except ImportError:
        logger.debug("cot_reports 패키지 미설치, CFTC API 폴백")
        return {"ok": False}

    try:
        df = cot.cot_report(report_type="traders_in_financial_futures")
        if df is None or (hasattr(df, 'empty') and df.empty):
            return {"ok": False, "error": "empty TFF report"}

        report_date = ""
        if "As of Date in Form YYYY-MM-DD" in df.columns:
            report_date = str(df["As of Date in Form YYYY-MM-DD"].iloc[0])

        inst_results = {}
        for key, meta in instruments.items():
            market_name = meta["market_name"]
            matches = df[df["Market and Exchange Names"].str.contains(market_name, case=False, na=False)]
            if matches.empty:
                inst_results[key] = {"ok": False, "error": f"no data for {market_name}"}
                continue

            row = matches.iloc[0]

            lev_long = _safe_int(row.get("Lev_Money_Positions_Long_All", 0))
            lev_short = _safe_int(row.get("Lev_Money_Positions_Short_All", 0))
            asset_long = _safe_int(row.get("Asset_Mgr_Positions_Long_All", 0))
            asset_short = _safe_int(row.get("Asset_Mgr_Positions_Short_All", 0))

            net_managed = (asset_long + lev_long) - (asset_short + lev_short)

            chg_long = _safe_int(row.get("Change_Asset_Mgr_Long_All", 0)) + _safe_int(row.get("Change_Lev_Money_Long_All", 0))
            chg_short = _safe_int(row.get("Change_Asset_Mgr_Short_All", 0)) + _safe_int(row.get("Change_Lev_Money_Short_All", 0))
            change_1w = chg_long - chg_short

            prev_net = net_managed - change_1w if change_1w != 0 else None
            signal = _classify_net_position(net_managed, prev_net)

            inst_results[key] = {
                "ok": True,
                "market_name": market_name,
                "net_managed_money": net_managed,
                "asset_mgr_long": asset_long,
                "asset_mgr_short": asset_short,
                "lev_money_long": lev_long,
                "lev_money_short": lev_short,
                "change_1w": change_1w,
                "signal": signal,
            }

        result = {
            "ok": any(v.get("ok") for v in inst_results.values()),
            "report_date": report_date,
            "instruments": inst_results,
            "summary": _compute_summary(inst_results),
            "source": "cot_reports_package",
        }
        return result

    except Exception as e:
        logger.warning("cot_reports 패키지 오류: %s", e)
        return {"ok": False, "error": str(e)}


def _try_cftc_api(instruments: Dict[str, Dict]) -> Dict[str, Any]:
    """CFTC Public Reporting Environment 직접 호출 (Socrata JSON)."""
    tff_endpoint = f"{_CFTC_PRE_BASE}/resource/gpe5-46if.json"

    inst_results = {}
    report_date = ""

    for key, meta in instruments.items():
        cftc_code = meta.get("cftc_code", "")
        if not cftc_code:
            inst_results[key] = {"ok": False, "error": "no cftc_code"}
            continue

        try:
            params = {
                "cftc_contract_market_code": cftc_code,
                "$order": "report_date_as_yyyy_mm_dd DESC",
                "$limit": 2,
            }
            r = requests.get(tff_endpoint, params=params, headers=_HEADERS, timeout=_TIMEOUT)
            r.raise_for_status()
            rows = r.json()

            if not rows:
                inst_results[key] = {"ok": False, "error": "no data"}
                continue

            latest = rows[0]
            prev = rows[1] if len(rows) > 1 else None

            if not report_date:
                report_date = latest.get("report_date_as_yyyy_mm_dd", "")

            asset_long = _safe_int(latest.get("asset_mgr_positions_long_all", 0))
            asset_short = _safe_int(latest.get("asset_mgr_positions_short_all", 0))
            lev_long = _safe_int(latest.get("lev_money_positions_long_all", 0))
            lev_short = _safe_int(latest.get("lev_money_positions_short_all", 0))

            net_managed = (asset_long + lev_long) - (asset_short + lev_short)

            prev_net = None
            change_1w = None
            if prev:
                p_al = _safe_int(prev.get("asset_mgr_positions_long_all", 0))
                p_as = _safe_int(prev.get("asset_mgr_positions_short_all", 0))
                p_ll = _safe_int(prev.get("lev_money_positions_long_all", 0))
                p_ls = _safe_int(prev.get("lev_money_positions_short_all", 0))
                prev_net = (p_al + p_ll) - (p_as + p_ls)
                change_1w = net_managed - prev_net

            signal = _classify_net_position(net_managed, prev_net)

            inst_results[key] = {
                "ok": True,
                "market_name": meta["market_name"],
                "net_managed_money": net_managed,
                "asset_mgr_long": asset_long,
                "asset_mgr_short": asset_short,
                "lev_money_long": lev_long,
                "lev_money_short": lev_short,
                "change_1w": change_1w,
                "signal": signal,
            }

        except Exception as e:
            logger.warning("CFTC API failed for %s: %s", key, e)
            inst_results[key] = {"ok": False, "error": str(e)}

    return {
        "ok": any(v.get("ok") for v in inst_results.values()),
        "report_date": report_date,
        "instruments": inst_results,
        "summary": _compute_summary(inst_results),
        "source": "cftc_api",
    }


def _safe_int(val) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return 0
