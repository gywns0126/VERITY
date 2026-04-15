"""
미국 국채 수익률 곡선·신용 스프레드 (FRED API)
  - Treasury 수익률 곡선 (1M~30Y, 주요 만기)
  - 2s10s / 3m10y 스프레드 (역전 감시)
  - IG / HY 신용 스프레드 (ICE BofA OAS)
기존 fred_macro.py의 _fetch_series 패턴을 재사용.
"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

from api.config import FRED_API_KEY

FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"

_TREASURY_SERIES = [
    ("1M",  "DGS1MO"),
    ("3M",  "DGS3MO"),
    ("6M",  "DGS6MO"),
    ("1Y",  "DGS1"),
    ("2Y",  "DGS2"),
    ("3Y",  "DGS3"),
    ("5Y",  "DGS5"),
    ("7Y",  "DGS7"),
    ("10Y", "DGS10"),
    ("20Y", "DGS20"),
    ("30Y", "DGS30"),
]

_CREDIT_SERIES = {
    "us_ig_oas": "BAMLC0A4CBBB",
    "us_hy_oas": "BAMLH0A0HYM2",
}


def _fetch_latest(series_id: str, limit: int = 5) -> Optional[float]:
    """FRED 시리즈 최신 관측값 1개."""
    if not FRED_API_KEY:
        return None
    try:
        r = requests.get(
            FRED_OBS_URL,
            params={
                "series_id": series_id,
                "api_key": FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": limit,
            },
            timeout=20,
        )
        if r.status_code != 200:
            return None
        for obs in r.json().get("observations", []):
            raw = obs.get("value")
            if raw in (".", "", None):
                continue
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
    except Exception:
        pass
    return None


def _fetch_series_points(series_id: str, limit: int = 260) -> List[Tuple[str, float]]:
    """FRED 시리즈 관측값 리스트 (최신→과거)."""
    if not FRED_API_KEY:
        return []
    try:
        r = requests.get(
            FRED_OBS_URL,
            params={
                "series_id": series_id,
                "api_key": FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": limit,
            },
            timeout=20,
        )
        if r.status_code != 200:
            return []
        out: List[Tuple[str, float]] = []
        for obs in r.json().get("observations", []):
            raw = obs.get("value")
            if raw in (".", "", None):
                continue
            try:
                out.append((str(obs.get("date", "")), float(raw)))
            except (TypeError, ValueError):
                continue
        return out
    except Exception:
        return []


def _classify_us_curve_shape(curve: List[Dict[str, Any]]) -> str:
    """미국 수익률 곡선 형태 판별."""
    if len(curve) < 4:
        return "insufficient_data"

    yields_map = {c["tenor"]: c["yield"] for c in curve}
    short = yields_map.get("3M") or yields_map.get("1M")
    mid = yields_map.get("2Y") or yields_map.get("5Y")
    long = yields_map.get("10Y") or yields_map.get("30Y")

    if short is None or long is None:
        return "insufficient_data"

    spread = long - short
    if spread > 0.5:
        return "normal"
    elif spread < -0.3:
        return "inverted"
    elif mid is not None and mid > short and mid > long:
        return "humped"
    else:
        return "flat"


def _assess_credit_risk(oas: float, category: str) -> str:
    """OAS 수준에 따른 리스크 등급."""
    if category == "hy":
        if oas < 3.0:
            return "LOW"
        elif oas < 5.0:
            return "MODERATE"
        elif oas < 7.0:
            return "HIGH"
        else:
            return "EXTREME"
    else:  # ig
        if oas < 1.0:
            return "LOW"
        elif oas < 1.5:
            return "MODERATE"
        elif oas < 2.5:
            return "HIGH"
        else:
            return "EXTREME"


def get_us_bond_summary() -> Dict[str, Any]:
    """
    미국 채권 시장 요약.
    반환: {curve: [...], curve_shape, spread_2y_10y, spread_3m_10y,
           credit_spreads: {us_ig_oas, us_hy_oas, ...}, updated_at}
    """
    result: Dict[str, Any] = {"available": False}

    if not FRED_API_KEY:
        result["error"] = "no_fred_api_key"
        return result

    curve: List[Dict[str, Any]] = []
    for tenor, series_id in _TREASURY_SERIES:
        val = _fetch_latest(series_id)
        if val is not None:
            curve.append({"tenor": tenor, "yield": round(val, 3)})

    if curve:
        result["curve"] = curve
        result["curve_shape"] = _classify_us_curve_shape(curve)
        result["available"] = True

        yields_map = {c["tenor"]: c["yield"] for c in curve}
        y2 = yields_map.get("2Y")
        y10 = yields_map.get("10Y")
        y3m = yields_map.get("3M")

        if y2 is not None and y10 is not None:
            result["spread_2y_10y"] = round(y10 - y2, 3)
        if y3m is not None and y10 is not None:
            result["spread_3m_10y"] = round(y10 - y3m, 3)

    ig_val = _fetch_latest(_CREDIT_SERIES["us_ig_oas"])
    hy_val = _fetch_latest(_CREDIT_SERIES["us_hy_oas"])

    credit: Dict[str, Any] = {}
    if ig_val is not None:
        credit["us_ig_oas"] = round(ig_val, 3)
        credit["us_ig_risk"] = _assess_credit_risk(ig_val, "ig")
    if hy_val is not None:
        credit["us_hy_oas"] = round(hy_val, 3)
        credit["us_hy_risk"] = _assess_credit_risk(hy_val, "hy")

    if credit:
        result["credit_spreads"] = credit
        result["available"] = True

    return result


if __name__ == "__main__":
    import json
    data = get_us_bond_summary()
    print(json.dumps(data, ensure_ascii=False, indent=2))
