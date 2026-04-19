"""
CFTC Commitments of Traders (COT) 리포트 수집기

매주 금요일 공개, 화요일 기준 데이터 (3일 래그).
Disaggregated / Traders in Financial Futures (TFF) 리포트 수집.

핵심: Managed Money 순 롱/숏 변화 추적 → 기관 방향 전환 시그널.
cot_reports 패키지 사용 또는 CFTC PRE 직접 CSV 파싱.
"""
from __future__ import annotations

import logging
import traceback
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 30
# brower-like UA 추가 — Socrata가 Verity-Terminal/1.0 같은 스크립트 UA를 일부 IP에서 throttle
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
_INSTRUMENT_RETRIES = 2  # 빈 응답 시 재시도 횟수 (총 3회 시도)
_RETRY_BACKOFF_S = 1.5

_CFTC_PRE_BASE = "https://publicreporting.cftc.gov"

# report_type: "tff" → Traders in Financial Futures (gpe5-46if)
#              "disaggregated" → Disaggregated Futures (72hh-3qpy)
_DEFAULT_INSTRUMENTS = {
    "SP500":          {"market_name": "E-MINI S&P 500",  "cftc_code": "13874A", "report_type": "tff"},
    "NASDAQ":         {"market_name": "NASDAQ-100",      "cftc_code": "209742", "report_type": "tff"},
    "CRUDE_OIL":      {"market_name": "CRUDE OIL",       "cftc_code": "067651", "report_type": "disaggregated"},
    "GOLD":           {"market_name": "GOLD",            "cftc_code": "088691", "report_type": "disaggregated"},
    "US_TREASURY_10Y":{"market_name": "10-YEAR",         "cftc_code": "043602", "report_type": "tff"},
    "VIX":            {"market_name": "VIX FUTURES",     "cftc_code": "1170E1", "report_type": "tff"},
}

_SOCRATA_ENDPOINTS = {
    "tff":           f"{_CFTC_PRE_BASE}/resource/gpe5-46if.json",
    "disaggregated": f"{_CFTC_PRE_BASE}/resource/72hh-3qpy.json",
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


def _classify_net_position(net_long: float, prev_net_long: Optional[float] = None) -> str:
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


def _extract_tff_row(row: Any, key: str, market_name: str) -> Dict[str, Any]:
    """TFF 리포트 행에서 포지션 데이터 추출."""
    lev_long = _safe_int(row.get("Lev_Money_Positions_Long_All", 0))
    lev_short = _safe_int(row.get("Lev_Money_Positions_Short_All", 0))
    asset_long = _safe_int(row.get("Asset_Mgr_Positions_Long_All", 0))
    asset_short = _safe_int(row.get("Asset_Mgr_Positions_Short_All", 0))

    net_managed = (asset_long + lev_long) - (asset_short + lev_short)

    chg_long = (_safe_int(row.get("Change_Asset_Mgr_Long_All", 0))
                + _safe_int(row.get("Change_Lev_Money_Long_All", 0)))
    chg_short = (_safe_int(row.get("Change_Asset_Mgr_Short_All", 0))
                 + _safe_int(row.get("Change_Lev_Money_Short_All", 0)))
    change_1w = chg_long - chg_short

    prev_net = net_managed - change_1w if change_1w != 0 else None
    signal = _classify_net_position(net_managed, prev_net)

    return {
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


def _extract_disagg_row(row: Any, key: str, market_name: str) -> Dict[str, Any]:
    """Disaggregated 리포트 행에서 포지션 데이터 추출 (M_Money = Managed Money)."""
    mm_long = _safe_int(row.get("M_Money_Positions_Long_All", 0))
    mm_short = _safe_int(row.get("M_Money_Positions_Short_All", 0))

    net_managed = mm_long - mm_short

    chg_long = _safe_int(row.get("Change_M_Money_Long_All", 0))
    chg_short = _safe_int(row.get("Change_M_Money_Short_All", 0))
    change_1w = chg_long - chg_short

    prev_net = net_managed - change_1w if change_1w != 0 else None
    signal = _classify_net_position(net_managed, prev_net)

    return {
        "ok": True,
        "market_name": market_name,
        "net_managed_money": net_managed,
        "asset_mgr_long": mm_long,
        "asset_mgr_short": mm_short,
        "lev_money_long": 0,
        "lev_money_short": 0,
        "change_1w": change_1w,
        "signal": signal,
    }


def _try_cot_reports_package(instruments: Dict[str, Dict]) -> Dict[str, Any]:
    """cot_reports 패키지로 수집 시도 — TFF + Disaggregated 병합."""
    try:
        import cot_reports as cot
        import pandas as pd
    except ImportError:
        logger.debug("cot_reports 패키지 미설치, CFTC API 폴백")
        return {"ok": False}

    try:
        tff_df = None
        disagg_df = None

        need_tff = any(
            m.get("report_type", "tff") == "tff" for m in instruments.values()
        )
        need_disagg = any(
            m.get("report_type") == "disaggregated" for m in instruments.values()
        )

        if need_tff:
            try:
                tff_df = cot.cot_report(report_type="traders_in_financial_futures")
                if tff_df is not None and hasattr(tff_df, "empty") and tff_df.empty:
                    tff_df = None
            except Exception as e:
                logger.warning("TFF 리포트 수집 실패: %s", e)

        if need_disagg:
            try:
                disagg_df = cot.cot_report(report_type="disaggregated_fut")
                if disagg_df is not None and hasattr(disagg_df, "empty") and disagg_df.empty:
                    disagg_df = None
            except Exception as e:
                logger.warning("Disaggregated 리포트 수집 실패: %s", e)

        if tff_df is None and disagg_df is None:
            return {"ok": False, "error": "both TFF and disaggregated reports empty"}

        report_date = ""
        date_col = "As of Date in Form YYYY-MM-DD"
        for df in (tff_df, disagg_df):
            if df is not None and date_col in df.columns:
                report_date = str(df[date_col].iloc[0])
                break

        inst_results = {}
        for key, meta in instruments.items():
            market_name = meta["market_name"]
            rtype = meta.get("report_type", "tff")

            df = tff_df if rtype == "tff" else disagg_df
            if df is None:
                inst_results[key] = {"ok": False, "error": f"no {rtype} dataframe"}
                continue

            name_col = "Market and Exchange Names"
            if name_col not in df.columns:
                inst_results[key] = {"ok": False, "error": "column not found"}
                continue

            matches = df[df[name_col].str.contains(market_name, case=False, na=False)]
            if matches.empty:
                inst_results[key] = {"ok": False, "error": f"no data for {market_name}"}
                continue

            row = matches.iloc[0]

            if rtype == "tff":
                inst_results[key] = _extract_tff_row(row, key, market_name)
            else:
                inst_results[key] = _extract_disagg_row(row, key, market_name)

        result = {
            "ok": any(v.get("ok") for v in inst_results.values()),
            "report_date": report_date,
            "instruments": inst_results,
            "summary": _compute_summary(inst_results),
            "source": "cot_reports_package",
        }
        return result

    except Exception as e:
        logger.warning("cot_reports 패키지 오류: %s\n%s", e, traceback.format_exc())
        return {"ok": False, "error": str(e)}


def _try_cftc_api(instruments: Dict[str, Dict]) -> Dict[str, Any]:
    """CFTC Public Reporting Environment 직접 호출 (Socrata JSON).

    금융선물 → TFF 엔드포인트(gpe5-46if), 상품 → Disaggregated(72hh-3qpy).
    """
    inst_results = {}
    report_date = ""

    for key, meta in instruments.items():
        cftc_code = meta.get("cftc_code", "")
        if not cftc_code:
            inst_results[key] = {"ok": False, "error": "no cftc_code"}
            continue

        rtype = meta.get("report_type", "tff")
        endpoint = _SOCRATA_ENDPOINTS.get(rtype, _SOCRATA_ENDPOINTS["tff"])

        try:
            params = {
                "cftc_contract_market_code": cftc_code,
                "$order": "report_date_as_yyyy_mm_dd DESC",
                "$limit": 2,
            }
            # 빈 응답/rate-limit 시 백오프 재시도 (datacenter IP intermittent block 대응)
            rows = None
            attempt_err = None
            import time
            for attempt in range(_INSTRUMENT_RETRIES + 1):
                try:
                    r = requests.get(endpoint, params=params, headers=_HEADERS, timeout=_TIMEOUT)
                    r.raise_for_status()
                    rows = r.json()
                    if isinstance(rows, list) and len(rows) > 0:
                        break  # 성공
                    # 빈 list 또는 dict error → 재시도
                    attempt_err = "empty list" if isinstance(rows, list) else f"non-list ({type(rows).__name__})"
                    if attempt < _INSTRUMENT_RETRIES:
                        time.sleep(_RETRY_BACKOFF_S * (attempt + 1))
                except requests.RequestException as re:
                    attempt_err = str(re)[:80]
                    if attempt < _INSTRUMENT_RETRIES:
                        time.sleep(_RETRY_BACKOFF_S * (attempt + 1))
                        continue
                    raise
            if rows is None:
                inst_results[key] = {"ok": False, "error": f"no response after {_INSTRUMENT_RETRIES + 1} attempts: {attempt_err}"}
                continue

            # 응답 형태 강건성 검증 (rate-limit/error JSON 시 dict 반환되어
            # 기존 코드는 통과 후 모든 _col() = None → _safe_int() = 0 → ok=true 0값 버그)
            if isinstance(rows, dict):
                # Socrata error: {"error": True, "message": "Throttled"} 등
                err_msg = rows.get("message") or str(rows)
                inst_results[key] = {"ok": False, "error": f"socrata error: {err_msg[:100]}"}
                continue
            if not isinstance(rows, list) or len(rows) == 0:
                inst_results[key] = {"ok": False, "error": "no data"}
                continue

            latest = rows[0]
            if not isinstance(latest, dict):
                inst_results[key] = {"ok": False, "error": f"unexpected row shape: {type(latest).__name__}"}
                continue
            # 핵심 키 부재 = error response 가 list로 wrap 된 경우
            if "report_date_as_yyyy_mm_dd" not in latest:
                inst_results[key] = {"ok": False, "error": "row missing date — likely error response"}
                continue

            prev = rows[1] if len(rows) > 1 and isinstance(rows[1], dict) else None

            if not report_date:
                report_date = latest.get("report_date_as_yyyy_mm_dd", "")

            if rtype == "tff":
                asset_long = _safe_int(_col(latest, "asset_mgr_positions_long"))
                asset_short = _safe_int(_col(latest, "asset_mgr_positions_short"))
                lev_long = _safe_int(_col(latest, "lev_money_positions_long"))
                lev_short = _safe_int(_col(latest, "lev_money_positions_short"))
                # 모든 핵심 컬럼이 0 = 컬럼 부재 (None → 0 변환). 정상 데이터면 매우 희박.
                if asset_long == 0 and asset_short == 0 and lev_long == 0 and lev_short == 0:
                    inst_results[key] = {"ok": False,
                        "error": "all positions zero — likely missing columns in response"}
                    continue
                net_managed = (asset_long + lev_long) - (asset_short + lev_short)

                chg_al = _safe_int(_col(latest, "change_in_asset_mgr_long"))
                chg_as = _safe_int(_col(latest, "change_in_asset_mgr_short"))
                chg_ll = _safe_int(_col(latest, "change_in_lev_money_long"))
                chg_ls = _safe_int(_col(latest, "change_in_lev_money_short"))
                change_1w = (chg_al + chg_ll) - (chg_as + chg_ls)

                prev_net = net_managed - change_1w if change_1w != 0 else None
                if prev_net is None and prev:
                    p_al = _safe_int(_col(prev, "asset_mgr_positions_long"))
                    p_as = _safe_int(_col(prev, "asset_mgr_positions_short"))
                    p_ll = _safe_int(_col(prev, "lev_money_positions_long"))
                    p_ls = _safe_int(_col(prev, "lev_money_positions_short"))
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
            else:
                mm_long = _safe_int(_col(latest, "m_money_positions_long"))
                mm_short = _safe_int(_col(latest, "m_money_positions_short"))
                if mm_long == 0 and mm_short == 0:
                    inst_results[key] = {"ok": False,
                        "error": "all m_money positions zero — likely missing columns in response"}
                    continue
                net_managed = mm_long - mm_short

                chg_ml = _safe_int(_col(latest, "change_in_m_money_long"))
                chg_ms = _safe_int(_col(latest, "change_in_m_money_short"))
                change_1w = chg_ml - chg_ms

                prev_net = net_managed - change_1w if change_1w != 0 else None
                if prev_net is None and prev:
                    p_ml = _safe_int(_col(prev, "m_money_positions_long"))
                    p_ms = _safe_int(_col(prev, "m_money_positions_short"))
                    prev_net = p_ml - p_ms
                    change_1w = net_managed - prev_net

                signal = _classify_net_position(net_managed, prev_net)
                inst_results[key] = {
                    "ok": True,
                    "market_name": meta["market_name"],
                    "net_managed_money": net_managed,
                    "asset_mgr_long": mm_long,
                    "asset_mgr_short": mm_short,
                    "lev_money_long": 0,
                    "lev_money_short": 0,
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


def _col(row: Dict, base_name: str) -> Any:
    """Socrata 컬럼명 변형 대응: base_name, base_name_all 순으로 조회."""
    val = row.get(base_name)
    if val is not None:
        return val
    return row.get(f"{base_name}_all", 0)


def _safe_int(val) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return 0
