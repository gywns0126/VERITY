"""
한국은행 ECOS Open API — StatisticSearch
  기준금리: 722Y001 (월 M), 항목 0101000
  국고채 10년: 817Y002 (일 D), 항목 010210000
https://ecos.bok.or.kr/api/
"""
from datetime import timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from api.config import ECOS_API_KEY, now_kst

ECOS_BASE = "https://ecos.bok.or.kr/api/StatisticSearch"
_TIMEOUT = 25


def _normalize_rows(payload: dict) -> List[dict]:
    if not payload or "RESULT" in payload:
        return []
    ss = payload.get("StatisticSearch") or {}
    raw = ss.get("row")
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return [raw]
    return []


def _ecos_get(
    api_key: str,
    stat_code: str,
    cycle: str,
    period_start: str,
    period_end: str,
    item_code: str,
    start_idx: int = 1,
    end_idx: int = 100,
) -> List[dict]:
    """ECOS StatisticSearch JSON — row 리스트(시간 오름차순)."""
    key_seg = quote(api_key, safe="")
    url = (
        f"{ECOS_BASE}/{key_seg}/json/kr/{int(start_idx)}/{int(end_idx)}"
        f"/{stat_code}/{cycle}/{period_start}/{period_end}/{item_code}"
    )
    try:
        r = requests.get(url, timeout=_TIMEOUT)
        if r.status_code != 200:
            return []
        data = r.json()
        if isinstance(data, dict) and data.get("RESULT"):
            return []
        return _normalize_rows(data)
    except Exception:
        return []


def _month_range_months_back(months: int) -> tuple:
    """(시작 YYYYMM, 종료 YYYYMM) KST 기준."""
    end = now_kst().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=30 * months)
    return start.strftime("%Y%m"), end.strftime("%Y%m")


def _day_range_days_back(days: int) -> tuple:
    """(시작 YYYYMMDD, 종료 YYYYMMDD) KST 기준."""
    today = now_kst().date()
    start = today - timedelta(days=days)
    return start.strftime("%Y%m%d"), today.strftime("%Y%m%d")


def get_ecos_macro_block() -> Dict[str, Any]:
    """
    ECOS 한국 기준금리(월)·국고채 10년(일).
    키 없거나 오류 시 available=False.
    """
    out: Dict[str, Any] = {"available": False}
    if not ECOS_API_KEY or not str(ECOS_API_KEY).strip():
        return out

    key = str(ECOS_API_KEY).strip()

    ps, pe = _month_range_months_back(24)
    pr_rows = _ecos_get(key, "722Y001", "M", ps, pe, "0101000", 1, 24)
    if not pr_rows:
        pr_rows = _ecos_get(key, "722Y001", "M", ps, pe, "0101000", 1, 10)
    if pr_rows:
        last = pr_rows[-1]
        try:
            out["korea_policy_rate"] = {
                "value": round(float(last.get("DATA_VALUE", 0)), 3),
                "date": str(last.get("TIME", "")),
                "unit": last.get("UNIT_NAME"),
                "stat_code": "722Y001",
                "source": "ecos",
            }
        except (TypeError, ValueError):
            pass

    ds, de = _day_range_days_back(400)
    y_rows = _ecos_get(key, "817Y002", "D", ds, de, "010210000", 1, 320)
    if not y_rows:
        y_rows = _ecos_get(key, "817Y002", "D", ds, de, "010210000", 1, 10)
    if y_rows:
        last = y_rows[-1]
        try:
            val = round(float(last.get("DATA_VALUE", 0)), 4)
            yoy_pp: Optional[float] = None
            if len(y_rows) >= 200:
                ref = y_rows[max(0, len(y_rows) - 260)]
                yoy_pp = round(val - float(ref.get("DATA_VALUE", 0)), 3)
            d_raw = str(last.get("TIME", ""))
            date_iso = d_raw
            if len(d_raw) == 8 and d_raw.isdigit():
                date_iso = f"{d_raw[:4]}-{d_raw[4:6]}-{d_raw[6:8]}"
            out["korea_gov_10y"] = {
                "value": val,
                "date": date_iso,
                "yoy_pp": yoy_pp,
                "series_id": "ECOS/817Y002/010210000",
                "source_note": "한국은행 ECOS 시장금리(일별) 국고채(10년)",
                "source": "ecos",
            }
        except (TypeError, ValueError):
            pass

    out["available"] = bool(out.get("korea_policy_rate") or out.get("korea_gov_10y"))
    return out


def merge_ecos_into_fred(fred: Dict[str, Any], ecos: Dict[str, Any]) -> None:
    """fred 블록에 ECOS 한국 지표를 덮어쓰기·추가(in-place)."""
    if not fred or not ecos or not ecos.get("available"):
        return

    if ecos.get("korea_gov_10y"):
        g = ecos["korea_gov_10y"]
        fred["korea_gov_10y"] = {
            "value": g.get("value"),
            "date": g.get("date"),
            "yoy_pp": g.get("yoy_pp"),
            "series_id": g.get("series_id"),
            "source_note": g.get("source_note"),
        }

    if ecos.get("korea_policy_rate"):
        fred["korea_policy_rate"] = dict(ecos["korea_policy_rate"])

    fred["available"] = bool(
        fred.get("dgs10")
        or fred.get("core_cpi")
        or fred.get("m2")
        or fred.get("vix_close")
        or fred.get("korea_discount_rate")
        or fred.get("us_recession_smoothed_prob")
        or fred.get("korea_gov_10y")
        or fred.get("korea_policy_rate")
    )
