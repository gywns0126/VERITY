"""
GET /api/estate/corp-facilities?ticker=069960[&period=2025-FY]

단일 회사의 부동산 시설 목록 + 위치별(구) 집계 + LANDEX 가중평균.
TERMINAL StockDashboard 부동산 탭의 'LANDEX 가중평균' 카드용.

응답 예:
{
  "ticker": "069960",
  "company_name": "(주)현대백화점",
  "period": "2025-FY",
  "facilities": [
    {"location_gu": "강남구", "facility_type": "store", "facility_name": "...",
     "area_sqm": 12345.0, "location_address": "..."},
    ...
  ],
  "by_gu": [
    {"gu": "강남구", "count": 4, "total_area_sqm": 294200.0,
     "landex": 39.7, "tier5": "COOL", "snapshot_month": "2026-04"}
  ],
  "summary": {
    "total_facilities": 31,
    "total_area_sqm": 480000.0,
    "covered_gus": 4,
    "landex_weighted_avg": 52.3,
    "landex_simple_avg": 50.1,
    "missing_landex_gus": ["..."]
  }
}

PostgREST 는 GROUP BY 직접 미지원 — 클라이언트 사이드 집계.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
import logging
import os
import re
from collections import defaultdict
from urllib.parse import parse_qs, urlparse

import requests

_logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"^\d{6}$")
_PERIOD_RE = re.compile(r"^\d{4}-(Q[1-3]|FY)$")


def _supabase_get(path: str, params: list[tuple[str, str]]) -> tuple[list[dict] | None, str | None]:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url:
        return None, "env_SUPABASE_URL_missing"
    if not key:
        return None, "env_SUPABASE_ANON_KEY_missing"
    try:
        r = requests.get(
            f"{url}/rest/v1/{path}",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            params=params,
            timeout=8,
        )
    except Exception as e:
        return None, f"request_exc:{type(e).__name__}"
    if r.status_code != 200:
        body = ""
        try:
            body = r.text[:160]
        except Exception:
            pass
        return None, f"http_{r.status_code}:{body}"
    try:
        return r.json(), None
    except Exception as e:
        return None, f"json_decode:{type(e).__name__}"


def _fetch_facilities(ticker: str, period: str | None) -> tuple[list[dict] | None, str | None]:
    params = [
        ("select", "corp_code,ticker,company_name,facility_type,facility_name,area_sqm,location_gu,location_address,period"),
        ("ticker", f"eq.{ticker}"),
        ("order", "area_sqm.desc.nullslast"),
        ("limit", "500"),
    ]
    if period:
        params.append(("period", f"eq.{period}"))
    return _supabase_get("estate_corp_facilities", params)


def _fetch_landex_for_gus(gus: list[str]) -> tuple[dict[str, dict] | None, str | None]:
    """gu → 최신 month 의 landex 점수·tier 를 반환.

    PostgREST in.() 한글 처리: landex_scores.py 와 동일 패턴 — 각 값을 큰따옴표로 감싸야
    매칭됨 (`in.("강남구","서초구")`). 따옴표 없이 보내면 매칭 실패.
    """
    if not gus:
        return {}, None
    in_clause = ",".join(f'"{g}"' for g in gus)
    params = [
        ("select", "gu,month,landex,tier10,preset"),
        ("gu", f"in.({in_clause})"),
        ("preset", "eq.balanced"),
        ("order", "month.desc"),
        ("limit", "1000"),
    ]
    rows, err = _supabase_get("estate_landex_snapshots", params)
    if rows is None:
        return None, err

    # gu 별 가장 최근 month 의 행만 보관
    latest: dict[str, dict] = {}
    for r in rows:
        g = r.get("gu") or ""
        if not g:
            continue
        if g not in latest or (r.get("month") or "") > (latest[g].get("month") or ""):
            latest[g] = r
    return latest, None


def _tier10_to_tier5(tier10: str | None) -> str | None:
    """S+/S/A+/A/B+/B/C/D/E/F → HOT/WARM/NEUT/COOL/AVOID."""
    if not tier10:
        return None
    t = tier10.upper()
    if t in ("S+", "S"):
        return "HOT"
    if t in ("A+", "A"):
        return "WARM"
    if t in ("B+", "B"):
        return "NEUT"
    if t in ("C", "D"):
        return "COOL"
    return "AVOID"


def _aggregate(facilities: list[dict], landex_by_gu: dict[str, dict]) -> dict:
    by_gu: dict[str, dict] = defaultdict(lambda: {
        "count": 0, "total_area_sqm": 0.0,
    })
    total_area = 0.0
    weighted_sum = 0.0
    weighted_count = 0.0
    landex_sum = 0.0
    landex_n = 0
    missing: set[str] = set()

    for f in facilities:
        g = f.get("location_gu") or ""
        if not g:
            continue
        b = by_gu[g]
        b["count"] += 1
        area = f.get("area_sqm")
        a = 0.0
        if area is not None:
            try:
                a = float(area)
            except (TypeError, ValueError):
                a = 0.0
        b["total_area_sqm"] += a
        total_area += a

    by_gu_out: list[dict] = []
    for g, b in by_gu.items():
        info = landex_by_gu.get(g)
        landex = info.get("landex") if info else None
        tier5 = _tier10_to_tier5(info.get("tier10")) if info else None
        snapshot_month = info.get("month") if info else None
        if landex is None:
            missing.add(g)
        else:
            try:
                lf = float(landex)
                # 가중평균: 면적이 0 이면 단순평균 fallback (count weight 1)
                w = b["total_area_sqm"] if b["total_area_sqm"] > 0 else 1.0
                weighted_sum += lf * w
                weighted_count += w
                landex_sum += lf
                landex_n += 1
            except (TypeError, ValueError):
                missing.add(g)
        by_gu_out.append({
            "gu": g,
            "count": b["count"],
            "total_area_sqm": round(b["total_area_sqm"], 2),
            "landex": round(float(landex), 2) if landex is not None else None,
            "tier5": tier5,
            "snapshot_month": snapshot_month,
        })
    by_gu_out.sort(key=lambda x: (x["total_area_sqm"], x["count"]), reverse=True)

    summary = {
        "total_facilities": len(facilities),
        "total_area_sqm": round(total_area, 2),
        "covered_gus": len(by_gu),
        "landex_weighted_avg": round(weighted_sum / weighted_count, 2) if weighted_count > 0 else None,
        "landex_simple_avg": round(landex_sum / landex_n, 2) if landex_n > 0 else None,
        "missing_landex_gus": sorted(missing),
    }
    return {"by_gu": by_gu_out, "summary": summary}


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        ticker = params.get("ticker", [""])[0].strip()
        period = params.get("period", [""])[0].strip() or None

        if not _TICKER_RE.match(ticker):
            self._err(400, "invalid_ticker", "ticker=6자리 숫자 (예: 069960)")
            return
        if period and not _PERIOD_RE.match(period):
            self._err(400, "invalid_period", "period=YYYY-Q1|Q2|Q3|FY 형식")
            return

        rows, detail = _fetch_facilities(ticker, period)
        if rows is None:
            self._err(503, "supabase_unavailable", f"facilities 조회 실패: {detail}")
            return

        if not rows:
            body = {
                "ticker": ticker,
                "company_name": None,
                "period": period,
                "facilities": [],
                "by_gu": [],
                "summary": {
                    "total_facilities": 0, "total_area_sqm": 0.0, "covered_gus": 0,
                    "landex_weighted_avg": None, "landex_simple_avg": None,
                    "missing_landex_gus": [],
                },
            }
            return self._ok(body)

        # facilities 정리
        company_name = rows[0].get("company_name")
        facilities_clean: list[dict] = []
        unique_gus: set[str] = set()
        for r in rows:
            g = r.get("location_gu") or None
            if g:
                unique_gus.add(g)
            facilities_clean.append({
                "location_gu": g,
                "facility_type": r.get("facility_type"),
                "facility_name": r.get("facility_name"),
                "area_sqm": r.get("area_sqm"),
                "location_address": r.get("location_address"),
            })

        # landex 점수 (병렬이 아닌 단일 query 로 batch fetch)
        landex_by_gu, lerr = _fetch_landex_for_gus(sorted(unique_gus))
        if landex_by_gu is None:
            # landex fetch 실패해도 facility 데이터는 반환
            landex_by_gu = {}

        agg = _aggregate(facilities_clean, landex_by_gu)
        body = {
            "ticker": ticker,
            "company_name": company_name,
            "period": period,
            "facilities": facilities_clean,
            **agg,
        }
        if lerr:
            body["landex_warning"] = lerr
        self._ok(body)

    def _ok(self, body: dict):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))

    def _err(self, status: int, code: str, message: str):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({"error": code, "message": message}).encode("utf-8"))
