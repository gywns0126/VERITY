"""
FRED API — 공식 거시 시계열
  미국: DGS10, CPILFESL, M2SL, VIXCLS, RECPROUSM156N
  한국(ECOS 대체): IRLTLT01KRA156N(국채10Y·OECD), INTDSRKRM193N(할인율·IMF)
https://fred.stlouisfed.org/docs/api/fred/
"""
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

from api.config import FRED_API_KEY

FRED_OBS_URL = "https://api.stlouisfed.org/fred/series/observations"


def _parse_observations(payload: dict) -> List[Tuple[str, float]]:
    out: List[Tuple[str, float]] = []
    for obs in payload.get("observations", []) or []:
        raw = obs.get("value")
        if raw in (".", "", None):
            continue
        try:
            out.append((str(obs.get("date", "")), float(raw)))
        except (TypeError, ValueError):
            continue
    return out


def _value_minus_approx_12m_prior(points: List[Tuple[str, float]]) -> Optional[float]:
    """최신값 − 약 12개월 전(±2M) 관측. 없으면 직전 관측 대비."""
    if len(points) < 2:
        return None
    d0_s, v0 = points[0]
    try:
        d0 = datetime.strptime(d0_s[:10], "%Y-%m-%d")
    except ValueError:
        return round(v0 - points[1][1], 4)
    best_v: Optional[float] = None
    best_dm = 99
    for d_s, v in points[1:]:
        try:
            d = datetime.strptime(d_s[:10], "%Y-%m-%d")
        except ValueError:
            continue
        dm = abs((d0.year - d.year) * 12 + (d0.month - d.month))
        if 10 <= dm <= 14 and dm < best_dm:
            best_v = v
            best_dm = dm
    if best_v is not None:
        return round(v0 - best_v, 4)
    return round(v0 - points[1][1], 4)


def _fetch_series(series_id: str, limit: int) -> List[Tuple[str, float]]:
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
                "limit": int(limit),
            },
            timeout=20,
        )
        if r.status_code != 200:
            return []
        return _parse_observations(r.json())
    except Exception:
        return []


def get_fred_macro_block() -> Dict[str, Any]:
    """
    미국: DGS10·근원CPI·M2(기존), VIX 종가, 스무딩 리세션 확률.
    한국: OECD 10Y 국채, IMF 할인율(ECOS 미가입 시 방어용 대체).
    API 키 없거나 오류 시 부분/빈 블록.
    """
    if not FRED_API_KEY:
        return {"available": False, "error": "no_api_key"}

    out: Dict[str, Any] = {"available": False}

    vix_c = _fetch_series("VIXCLS", 20)
    if len(vix_c) >= 1:
        vd, vv = vix_c[0]
        v_ch5: Optional[float] = None
        if len(vix_c) >= 6:
            v_ch5 = round(vv - vix_c[5][1], 3)
        out["vix_close"] = {
            "value": round(vv, 2),
            "date": vd,
            "change_5d": v_ch5,
            "series_id": "VIXCLS",
        }

    dgs = _fetch_series("DGS10", 20)
    if len(dgs) >= 1:
        latest_d, latest_v = dgs[0]
        ch5: Optional[float] = None
        if len(dgs) >= 6:
            ch5 = round(latest_v - dgs[5][1], 4)
        out["dgs10"] = {
            "value": round(latest_v, 3),
            "date": latest_d,
            "change_5d_pp": ch5,
        }

    cpi = _fetch_series("CPILFESL", 16)
    if len(cpi) >= 13:
        cur_d, cur_v = cpi[0]
        _, yago_v = cpi[12]
        if yago_v and yago_v > 0:
            yoy = round((cur_v / yago_v - 1) * 100, 2)
            out["core_cpi"] = {
                "index": round(cur_v, 2),
                "date": cur_d,
                "yoy_pct": yoy,
            }

    m2 = _fetch_series("M2SL", 60)
    if len(m2) >= 53:
        cur_d, cur_v = m2[0]
        _, yago_v = m2[52]
        if yago_v and yago_v > 0:
            yoy = round((cur_v / yago_v - 1) * 100, 2)
            out["m2"] = {
                "billions_usd": round(cur_v, 1),
                "date": cur_d,
                "yoy_pct": yoy,
            }

    kr10 = _fetch_series("IRLTLT01KRA156N", 36)
    if len(kr10) >= 1:
        kd, kv = kr10[0]
        yoy_pp = _value_minus_approx_12m_prior(kr10)
        out["korea_gov_10y"] = {
            "value": round(kv, 3),
            "date": kd,
            "yoy_pp": yoy_pp,
            "series_id": "IRLTLT01KRA156N",
            "source_note": "OECD Main Economic Indicators (빈도·시차 ECOS와 다를 수 있음)",
        }

    krd = _fetch_series("INTDSRKRM193N", 24)
    if len(krd) >= 1:
        dd, dv = krd[0]
        d_yoy: Optional[float] = None
        if len(krd) >= 13:
            d_yoy = round(dv - krd[12][1], 4)
        out["korea_discount_rate"] = {
            "value": round(dv, 3),
            "date": dd,
            "yoy_pp": d_yoy,
            "series_id": "INTDSRKRM193N",
            "source_note": "IMF IFS (BOK 기준금리와 시차·정의 다를 수 있음)",
        }

    rec = _fetch_series("RECPROUSM156N", 8)
    if len(rec) >= 1:
        rd, rv = rec[0]
        mom: Optional[float] = None
        if len(rec) >= 2:
            mom = round(rv - rec[1][1], 3)
        out["us_recession_smoothed_prob"] = {
            "pct": round(rv, 2),
            "date": rd,
            "mom_change_pp": mom,
            "series_id": "RECPROUSM156N",
            "source_note": "Smoothed U.S. recession probability (monthly model)",
        }

    out["available"] = bool(
        out.get("dgs10")
        or out.get("core_cpi")
        or out.get("m2")
        or out.get("vix_close")
        or out.get("korea_gov_10y")
        or out.get("korea_discount_rate")
        or out.get("us_recession_smoothed_prob")
    )
    return out
