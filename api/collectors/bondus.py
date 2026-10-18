"""
미국 국채 수익률 곡선·신용 스프레드 (FRED API)
  - Treasury 수익률 곡선 (1M~30Y, 주요 만기)
  - 2s10s / 3m10y 스프레드 (역전 감시)
  - IG / HY 신용 스프레드 (ICE BofA OAS)
기존 fred_macro.py의 _fetch_series 패턴을 재사용.
"""
import math
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from api.config import FRED_API_KEY
from api.utils.macro_provenance import now_iso, observation_meta
from api.utils.macro_runtime import CollectionDeadline, collection_budget, request_timeout, timed_source

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

# 🚨 2026-08-08 정정 — us_ig_oas 가 BAMLC0A4CBBB(= BBB 등급 OAS, IG 최하단 한 칸)를 담고 있었다.
#   공개 컴포넌트 PublicBondRegime 은 이 값을 "투자등급 IG" 로 표기한다 = 라벨과 실제 시리즈 불일치.
#   실측(2026-08-06 관측): 전체 IG 0.78 vs BBB 0.97 — 0.19%p 차이로 늘 BBB 가 더 넓게 나온다.
#   → us_ig_oas 를 전체 IG 지수(BAMLC0A0CM)로 바꿔 라벨과 데이터를 일치시키고, BBB 는 잃지 않도록
#     us_bbb_oas 로 따로 남긴다(추가 사실, 기존 키 제거 0).
#   🚨 임계 무변경 — credit_cycle/risk_appetite 판정은 HY 만 쓰므로(bondanalyzer.analyze_credit_spreads)
#     이 교체로 등급 판정 산식이 바뀌지 않는다. RULE 7 임계 조정 아님(입력 결함 정정).
_CREDIT_SERIES = {
    "us_ig_oas": "BAMLC0A0CM",      # ICE BofA US Corporate Index OAS (전체 투자등급)
    "us_bbb_oas": "BAMLC0A4CBBB",   # ICE BofA BBB US Corporate Index OAS (IG 최하단)
    "us_hy_oas": "BAMLH0A0HYM2",    # ICE BofA US High Yield Index OAS
}


def _fetch_latest(series_id: str, limit: int = 10, retries: int = 3) -> Optional[float]:
    """Preserve the float contract; dated receipts are used by the collector."""
    with collection_budget(25):
        point = _fetch_latest_point(series_id, limit, retries)
    return point["value"] if point else None


def _fetch_latest_point(series_id: str, limit: int = 10, retries: int = 3) -> Optional[Dict[str, Any]]:
    """Retry only within the shared US/parent budget, keeping partial results."""
    if not FRED_API_KEY:
        return None
    for attempt in range(retries):
        try:
            remaining = request_timeout(6)
            r = timed_source("bonds:fred", lambda: requests.get(
                FRED_OBS_URL,
                params={
                    "series_id": series_id,
                    "api_key": FRED_API_KEY,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": limit,
                },
                timeout=(remaining / 3, remaining * 2 / 3),
                allow_redirects=False,
            ))
            if r.status_code != 200:
                if r.status_code not in (429, 500, 502, 503, 504):
                    return None
            else:
                fetched_at = now_iso()
                points = []
                for obs in r.json().get("observations", []):
                    try:
                        value = float(obs.get("value"))
                    except (TypeError, ValueError):
                        continue
                    if not math.isfinite(value):
                        continue
                    metadata = observation_meta("fred", obs.get("date"), fetched_at=fetched_at)
                    if metadata["source_date_status"] == "invalid":
                        continue  # Includes future dates.
                    point = {"value": value, **metadata}
                    if metadata["source_as_of"]:
                        point["as_of"] = metadata["source_as_of"]
                    points.append(point)
                return max(points, key=lambda p: p.get("as_of", "")) if points else None
        except CollectionDeadline:
            return None
        except Exception:
            pass  # Never emit exception bodies, which can contain the API key.
        if attempt < retries - 1:
            try:
                time.sleep(request_timeout(0.6 * (attempt + 1)))
            except CollectionDeadline:
                return None
    return None


def _fetch_series_points(series_id: str, limit: int = 260) -> List[Tuple[str, float]]:
    """FRED 시리즈 관측값 리스트 (최신→과거)."""
    if not FRED_API_KEY:
        return []
    try:
        remaining = request_timeout(6)
        r = requests.get(
            FRED_OBS_URL,
            params={
                "series_id": series_id,
                "api_key": FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": limit,
            },
            timeout=(remaining / 3, remaining * 2 / 3),
            allow_redirects=False,
        )
        if r.status_code != 200:
            return []
        out: List[Tuple[str, float]] = []
        for obs in r.json().get("observations", []):
            raw = obs.get("value")
            if raw in (".", "", None):
                continue
            try:
                value = float(raw)
                metadata = observation_meta("fred", obs.get("date"))
                if math.isfinite(value) and metadata["source_date_status"] == "ok":
                    out.append((metadata["source_as_of"], value))
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
    with collection_budget(25):
        return _collect_us_bonds()


def _collect_us_bonds() -> Dict[str, Any]:
    """
    미국 채권 시장 요약.
    반환: {curve: [...], curve_shape, spread_2y_10y, spread_3m_10y,
           credit_spreads: {us_ig_oas, us_hy_oas, ...}, updated_at}
    """
    result: Dict[str, Any] = {"available": False, "partial": True, "stale": True}

    if not FRED_API_KEY:
        result["error"] = "no_fred_api_key"
        sys.stderr.write("[bond_source] source=us outcome=skipped_no_credentials\n")
        return result

    curve: List[Dict[str, Any]] = []
    for tenor, series_id in _TREASURY_SERIES:
        try:
            request_timeout(1)
        except CollectionDeadline:
            break
        point = _fetch_latest_point(series_id)
        if point is not None:
            entry = {k: v for k, v in point.items() if k != "value"}
            entry.update(tenor=tenor, **{"yield": round(point["value"], 3)})
            curve.append(entry)

    if curve:
        result["curve"] = curve
        result["curve_shape"] = _classify_us_curve_shape(curve)
        result["available"] = True
        as_ofs = [p["as_of"] for p in curve if p.get("as_of")]
        if as_ofs:
            result["curve_as_of"] = max(as_ofs)

        yields_map = {c["tenor"]: c["yield"] for c in curve}
        y2 = yields_map.get("2Y")
        y10 = yields_map.get("10Y")
        y3m = yields_map.get("3M")

        if y2 is not None and y10 is not None:
            result["spread_2y_10y"] = round(y10 - y2, 3)
        if y3m is not None and y10 is not None:
            result["spread_3m_10y"] = round(y10 - y3m, 3)

    credit_points = {}
    for key, series_id in _CREDIT_SERIES.items():
        try:
            request_timeout(1)
        except CollectionDeadline:
            break
        point = _fetch_latest_point(series_id)
        if point is not None:
            credit_points[key] = point
    ig_val = credit_points.get("us_ig_oas", {}).get("value")
    bbb_val = credit_points.get("us_bbb_oas", {}).get("value")
    hy_val = credit_points.get("us_hy_oas", {}).get("value")

    credit: Dict[str, Any] = {}
    if ig_val is not None:
        credit["us_ig_oas"] = round(ig_val, 3)
        credit["us_ig_risk"] = _assess_credit_risk(ig_val, "ig")
    if bbb_val is not None:
        credit["us_bbb_oas"] = round(bbb_val, 3)
    if hy_val is not None:
        credit["us_hy_oas"] = round(hy_val, 3)
        credit["us_hy_risk"] = _assess_credit_risk(hy_val, "hy")

    if credit:
        result["credit_spreads"] = credit
        result["available"] = True
        result["credit_spreads_meta"] = {
            key: {k: v for k, v in point.items() if k != "value"}
            for key, point in credit_points.items()
        }

    result["missing_tenors"] = [t for t, _ in _TREASURY_SERIES
                                if t not in {c["tenor"] for c in curve}]
    result["missing_credit"] = [k for k in _CREDIT_SERIES if k not in credit_points]
    result["partial"] = bool(result["missing_tenors"] or result["missing_credit"])
    result["stale"] = result["partial"] or any(
        point.get("stale") for point in curve + list(credit_points.values()))
    sys.stderr.write(f"[bond_source] source=us outcome={'partial' if result['partial'] else 'complete'} "
                     f"tenors={len(curve)}/11 credit={len(credit_points)}/3\n")

    return result


if __name__ == "__main__":
    import json
    data = get_us_bond_summary()
    print(json.dumps(data, ensure_ascii=False, indent=2))
