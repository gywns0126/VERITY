"""
GET /api/estate/corp-by-region?gu=강남구[&period=2025-FY][&limit=20]

서울 25구 중 1개 구의 부동산 보유 법인 ranking — ESTATE 고유 가치.
estate_corp_facilities 에서 location_gu 필터링 후 회사별 집계.

응답 예:
{
  "gu": "강남구",
  "period": "2025-FY",
  "ranking": [
    {
      "corp_code": "00126380",
      "ticker": "005930",
      "company_name": "삼성전자",
      "facilities": 4,
      "total_area_sqm": 294200.00,
      "facility_types": ["HQ", "store"]
    }
  ]
}

주의: PostgREST 는 GROUP BY 직접 지원 안 함. 클라이언트 사이드 집계.
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

SEOUL_25_GU = {
    "강남구", "강동구", "강북구", "강서구", "관악구", "광진구", "구로구",
    "금천구", "노원구", "도봉구", "동대문구", "동작구", "마포구", "서대문구",
    "서초구", "성동구", "성북구", "송파구", "양천구", "영등포구", "용산구",
    "은평구", "종로구", "중랑구", "중구",
}

_PERIOD_RE = re.compile(r"^\d{4}-(Q[1-3]|FY)$")


def _fetch(gu: str, period: str | None) -> list[dict] | None:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not key:
        return None

    params = [
        ("select", "corp_code,ticker,company_name,facility_type,facility_name,area_sqm,location_address"),
        ("location_gu", f"eq.{gu}"),
        ("order", "area_sqm.desc.nullslast"),
        ("limit", "1000"),
    ]
    if period:
        params.append(("period", f"eq.{period}"))

    try:
        r = requests.get(
            f"{url}/rest/v1/estate_corp_facilities",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            params=params,
            timeout=8,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        _logger.warning("corp_by_region fetch 실패 gu=%s: %s", gu, e)
        return None


def _aggregate(rows: list[dict], limit: int) -> list[dict]:
    bucket: dict[str, dict] = defaultdict(lambda: {
        "corp_code": "", "ticker": None, "company_name": "",
        "facilities": 0, "total_area_sqm": 0.0,
        "facility_types": set(),
    })
    for r in rows:
        cc = r.get("corp_code") or ""
        if not cc:
            continue
        b = bucket[cc]
        b["corp_code"] = cc
        b["ticker"] = r.get("ticker") or b["ticker"]
        b["company_name"] = r.get("company_name") or b["company_name"]
        b["facilities"] += 1
        area = r.get("area_sqm")
        if area is not None:
            try:
                b["total_area_sqm"] += float(area)
            except (TypeError, ValueError):
                pass
        ft = r.get("facility_type")
        if ft:
            b["facility_types"].add(ft)

    out = []
    for b in bucket.values():
        out.append({
            "corp_code": b["corp_code"],
            "ticker": b["ticker"],
            "company_name": b["company_name"],
            "facilities": b["facilities"],
            "total_area_sqm": round(b["total_area_sqm"], 2),
            "facility_types": sorted(b["facility_types"]),
        })
    out.sort(key=lambda x: x["total_area_sqm"], reverse=True)
    return out[:limit]


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        gu = params.get("gu", [""])[0].strip()
        period = params.get("period", [""])[0].strip() or None
        limit_s = params.get("limit", ["20"])[0].strip() or "20"

        if not gu or gu not in SEOUL_25_GU:
            self._err(400, "invalid_gu",
                      "gu=서울 25구 중 하나 (예: 강남구)")
            return
        if period and not _PERIOD_RE.match(period):
            self._err(400, "invalid_period", "period=YYYY-Q1|Q2|Q3|FY 형식")
            return
        try:
            limit = max(1, min(100, int(limit_s)))
        except ValueError:
            limit = 20

        rows = _fetch(gu, period)
        if rows is None:
            self._err(503, "supabase_unavailable", "DB 조회 실패")
            return

        ranking = _aggregate(rows, limit)
        body = {
            "gu": gu,
            "period": period,
            "ranking": ranking,
            "total_companies": len(ranking),
        }
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
