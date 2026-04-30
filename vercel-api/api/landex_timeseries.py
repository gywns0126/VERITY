"""
GET /api/landex/timeseries?gu=강남구&metric=price_index&weeks=52
GET /api/landex/timeseries?gu=강남구&metric=unsold&months=24

ScoreDetailPanel sparkline 용 — R-ONE 시계열을 그대로 노출.
*산식 변경 0* (V/D/S 계산 그대로) — 메타-검증 cron 결과와 독립.

응답:
{
  "version": "1.0",
  "gu": "강남구",
  "metric": "price_index" | "unsold",
  "series": [
    {"x": "202615", "y": 102.34, "date": "2026-04-13"},
    ...
  ],
  "as_of": "2026-04-13",
  "collected_at": "2026-04-30T20:30:00+09:00",
  "source": "rone_weekly" | "rone_unsold",
  "count": 52
}

캐시:
  - Cache-Control: public, max-age=3600  (R-ONE 갱신 주기 = 주/월 단위 → 1h 충분)
  - REB_API_KEY 미설정 시 503 (mock fallback 안 함 — sparkline 가짜 데이터는 오해 유발)
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
import logging
import re
from urllib.parse import parse_qs, urlparse

from api.landex._sources import rone

_logger = logging.getLogger(__name__)

VERSION = "1.0"

SEOUL_25_GU = [
    "강남구", "서초구", "송파구", "강동구", "마포구",
    "용산구", "성동구", "광진구", "중구", "종로구",
    "서대문구", "은평구", "강서구", "양천구", "영등포구",
    "구로구", "금천구", "관악구", "동작구", "성북구",
    "동대문구", "중랑구", "노원구", "도봉구", "강북구",
]

_GU_RE = re.compile(r"^[가-힣]{2,8}구$")

METRIC_PRICE = "price_index"
METRIC_UNSOLD = "unsold"
ALLOWED_METRICS = (METRIC_PRICE, METRIC_UNSOLD)

# 클라이언트 입력 한도 (R-ONE 호출 비용 + Vercel 10s timeout 보호)
MAX_WEEKS = 156   # ~3년
MAX_MONTHS = 60   # 5년


def _payload_to_series(payload: dict | None, metric: str) -> list[dict]:
    """R-ONE payload → sparkline 표준 포맷 [{x, y, date}, ...]."""
    if not payload:
        return []
    raw = payload.get("series") or []
    if metric == METRIC_PRICE:
        return [
            {"x": s["week"], "y": s["index"], "date": s.get("date")}
            for s in raw if "week" in s and "index" in s
        ]
    # unsold
    return [
        {"x": s["month"], "y": s["unsold"], "date": s.get("date")}
        for s in raw if "month" in s and "unsold" in s
    ]


def fetch_timeseries(gu: str, metric: str, *, weeks: int = 52, months: int = 24) -> dict | None:
    """단일 구의 시계열 fetch + 표준 응답 dict 구성. 키 미설정/실패 시 None."""
    if metric == METRIC_PRICE:
        payload = rone.fetch_weekly_index(gu, weeks=max(1, min(MAX_WEEKS, weeks)))
        if not payload:
            return None
        return {
            "version": VERSION,
            "gu": gu,
            "metric": metric,
            "series": _payload_to_series(payload, metric),
            "as_of": payload.get("as_of"),
            "as_of_period": payload.get("as_of_week"),
            "collected_at": payload.get("collected_at"),
            "source": payload.get("source"),
            "stat_id": payload.get("stat_id"),
        }
    if metric == METRIC_UNSOLD:
        payload = rone.fetch_monthly_unsold(gu, months=max(1, min(MAX_MONTHS, months)))
        if not payload:
            return None
        return {
            "version": VERSION,
            "gu": gu,
            "metric": metric,
            "series": _payload_to_series(payload, metric),
            "as_of": payload.get("as_of"),
            "as_of_period": payload.get("as_of_month"),
            "collected_at": payload.get("collected_at"),
            "source": payload.get("source"),
            "stat_id": payload.get("stat_id"),
        }
    return None


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
        metric = params.get("metric", [METRIC_PRICE])[0].strip().lower()

        # weeks / months — 정수 파싱 실패 시 기본값
        try:
            weeks = int(params.get("weeks", ["52"])[0])
        except (ValueError, TypeError):
            weeks = 52
        try:
            months = int(params.get("months", ["24"])[0])
        except (ValueError, TypeError):
            months = 24

        if not _GU_RE.match(gu) or gu not in SEOUL_25_GU:
            self._err(400, "invalid_gu", "gu=서울 25구 중 하나 필요")
            return
        if metric not in ALLOWED_METRICS:
            self._err(400, "invalid_metric",
                      f"metric ∈ {ALLOWED_METRICS}")
            return

        result = fetch_timeseries(gu, metric, weeks=weeks, months=months)
        if result is None:
            # R-ONE 키 없음 / 네트워크 실패 / 빈 응답 — 가짜 데이터 안 만듦
            self._err(503, "upstream_unavailable",
                      "R-ONE 시계열 일시 조회 불가 — 잠시 후 재시도")
            return
        if not result.get("series"):
            self._err(404, "no_data",
                      f"{gu}/{metric} 시계열 데이터 없음")
            return

        result["count"] = len(result["series"])

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        self.wfile.write(body)

    def _err(self, status: int, code: str, message: str):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(
            {"error": code, "message": message}, ensure_ascii=False
        ).encode("utf-8"))
