"""
국내 채권 수익률·스프레드 수집 (pykrx + ECOS)
  - 국고채 수익률 곡선 (1Y~30Y)
  - 회사채 신용등급별 스프레드 (AA-/A+/BBB+)
  - 한국은행 ECOS 보조 (국고채 3Y 기준)
"""
from datetime import timedelta
from typing import Any, Dict, List, Optional

from api.config import ECOS_API_KEY, now_kst

_KR_GOV_BOND_TENORS = {
    "1Y": "국고채권(01년)",
    "2Y": "국고채권(02년)",
    "3Y": "국고채권(03년)",
    "5Y": "국고채권(05년)",
    "10Y": "국고채권(10년)",
    "20Y": "국고채권(20년)",
    "30Y": "국고채권(30년)",
}

_CORP_GRADES = ("AA-", "A+", "BBB+")

_ECOS_BOND_ITEMS = {
    "gov_1y":  ("817Y002", "010200000"),
    "gov_2y":  ("817Y002", "010200001"),
    "gov_3y":  ("817Y002", "010210000"),
    "gov_5y":  ("817Y002", "010200002"),
    "gov_10y": ("817Y002", "010210000"),
    "gov_20y": ("817Y002", "010220000"),
    "gov_30y": ("817Y002", "010230000"),
    "corp_aa_minus": ("817Y002", "010300003"),
    "corp_a_plus":   ("817Y002", "010300006"),
    "corp_bbb_plus": ("817Y002", "010300009"),
}


def _pykrx_bond_yields() -> Dict[str, Any]:
    """pykrx에서 국고채 수익률 곡선 수집 시도."""
    try:
        from pykrx import bond
    except ImportError:
        return {}

    today = now_kst().date()
    start = today - timedelta(days=14)
    from_s = start.strftime("%Y%m%d")
    to_s = today.strftime("%Y%m%d")

    curve: List[Dict[str, Any]] = []
    for tenor, name in _KR_GOV_BOND_TENORS.items():
        try:
            df = bond.get_otc_treasury_yields(from_s, to_s, name)
            if df is None or df.empty:
                continue
            col = "수익률" if "수익률" in df.columns else (df.columns[0] if len(df.columns) > 0 else None)
            if col is None:
                continue
            vals = df[col].dropna()
            if vals.empty:
                continue
            last_yield = float(vals.iloc[-1])
            curve.append({"tenor": tenor, "yield": round(last_yield, 3)})
        except Exception:
            continue

    return {"curve": curve} if curve else {}


def _ecos_fetch_series(stat_code: str, item_code: str, days: int = 30) -> Optional[float]:
    """ECOS에서 단일 시계열의 최신값."""
    if not ECOS_API_KEY:
        return None
    try:
        import requests
        from urllib.parse import quote

        today = now_kst().date()
        start = today - timedelta(days=days)
        key_seg = quote(str(ECOS_API_KEY).strip(), safe="")
        url = (
            f"https://ecos.bok.or.kr/api/StatisticSearch/{key_seg}/json/kr/1/10"
            f"/{stat_code}/D/{start.strftime('%Y%m%d')}/{today.strftime('%Y%m%d')}/{item_code}"
        )
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            return None
        data = r.json()
        ss = data.get("StatisticSearch") or {}
        rows = ss.get("row")
        if not rows:
            return None
        if isinstance(rows, dict):
            rows = [rows]
        last = rows[-1]
        return round(float(last.get("DATA_VALUE", 0)), 4)
    except Exception:
        return None


def _ecos_yield_curve() -> Dict[str, Any]:
    """ECOS에서 국고채 수익률 곡선 + 회사채 스프레드 수집."""
    if not ECOS_API_KEY:
        return {}

    tenor_map = {
        "1Y":  ("817Y002", "010200000"),
        "3Y":  ("817Y002", "010210000"),
        "5Y":  ("817Y002", "010200002"),
        "10Y": ("817Y002", "010210001"),
        "20Y": ("817Y002", "010220000"),
        "30Y": ("817Y002", "010230000"),
    }

    curve: List[Dict[str, Any]] = []
    for tenor, (stat, item) in tenor_map.items():
        val = _ecos_fetch_series(stat, item, days=30)
        if val is not None:
            curve.append({"tenor": tenor, "yield": val})

    gov_3y = next((c["yield"] for c in curve if c["tenor"] == "3Y"), None)

    corp_grade_map = {
        "AA-":  ("817Y002", "010300003"),
        "A+":   ("817Y002", "010300006"),
        "BBB+": ("817Y002", "010300009"),
    }

    grades: Dict[str, Dict[str, Any]] = {}
    for grade, (stat, item) in corp_grade_map.items():
        val = _ecos_fetch_series(stat, item, days=30)
        if val is not None:
            entry: Dict[str, Any] = {"yield": val}
            if gov_3y is not None:
                entry["spread_vs_3y"] = round(val - gov_3y, 3)
            grades[grade] = entry

    result: Dict[str, Any] = {}
    if curve:
        result["curve"] = curve
    if grades:
        result["grades"] = grades
    return result


def _classify_curve_shape(curve: List[Dict[str, Any]]) -> str:
    """수익률 곡선 형태 판별."""
    if len(curve) < 3:
        return "insufficient_data"

    yields = [c["yield"] for c in curve]
    short = yields[0]
    long = yields[-1]
    mid = yields[len(yields) // 2]

    if long > short + 0.3:
        return "normal"
    elif short > long + 0.3:
        return "inverted"
    elif mid > short and mid > long:
        return "humped"
    else:
        return "flat"


def get_bond_market_summary() -> Dict[str, Any]:
    """
    국내 채권 시장 요약.
    반환: {curve: [...], curve_shape, kr_corp_spreads: {grades: ...}, updated_at}
    """
    ts = now_kst().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    date_str = now_kst().strftime("%Y%m%d")

    result: Dict[str, Any] = {
        "available": False,
        "updated_at": ts,
    }

    pykrx_data = _pykrx_bond_yields()
    ecos_data = _ecos_yield_curve()

    curve = pykrx_data.get("curve") or ecos_data.get("curve") or []

    if curve:
        result["curve"] = curve
        result["curve_shape"] = _classify_curve_shape(curve)
        result["available"] = True

    grades = ecos_data.get("grades")
    if grades:
        result["kr_corp_spreads"] = {
            "date": date_str,
            "grades": grades,
        }

    return result


if __name__ == "__main__":
    import json
    data = get_bond_market_summary()
    print(json.dumps(data, ensure_ascii=False, indent=2))
