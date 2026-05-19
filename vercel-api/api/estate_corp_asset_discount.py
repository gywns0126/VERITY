"""
GET /api/estate/corp-asset-discount
    [?min_ratio=30]           — 부동산/총자산 비율 ≥ N% (default 20)
    [&revaluation=true|false] — 재평가 발생 종목만 (default 무관)
    [&period=2025-FY]         — 보고기간 (default 최신)
    [&limit=50]               — 결과 행 수 (default 50, max 200)

자산주 watchlist — 부동산 비중 높은 회사 + (옵션) 재평가 트리거.
estate_corp_holdings 단일 테이블 조회.

응답 예:
{
  "filters": {"min_ratio": 30, "revaluation_only": true, "period": "2025-FY"},
  "watchlist": [
    {
      "ticker": "...", "company_name": "...",
      "total_property_krw": ...,
      "property_to_asset_pct": 39.12,
      "revaluation_flag": true,
      "revaluation_amount_krw": ...,
      "hidden_value_krw": <fair-book>
    }
  ]
}
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler
import json
import logging
import os
import re
from urllib.parse import parse_qs, urlparse

import requests

_logger = logging.getLogger(__name__)

_PERIOD_RE = re.compile(r"^\d{4}-(Q[1-3]|FY)$")

_FIELDS = ",".join([
    "corp_code", "ticker", "company_name", "period",
    "total_property_krw", "property_to_asset_pct",
    "investment_property_krw",
    "revaluation_flag", "revaluation_amount_krw",
    "book_value_total_krw", "fair_value_total_krw",
])


def _resolve_latest_period() -> tuple[str | None, str | None]:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url:
        return None, "env_SUPABASE_URL_missing"
    if not key:
        return None, "env_SUPABASE_ANON_KEY_missing"
    try:
        r = requests.get(
            f"{url}/rest/v1/estate_corp_holdings",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            params={"select": "period", "order": "period.desc", "limit": "1"},
            timeout=5,
        )
    except Exception as e:
        return None, f"request_exc:{type(e).__name__}"
    if r.status_code != 200:
        return None, f"http_{r.status_code}:{(r.text or '')[:120]}"
    rows = r.json()
    return (rows[0]["period"] if rows else None), None


def _fetch(period: str, min_ratio: float, revaluation_only: bool,
           limit: int) -> tuple[list[dict] | None, str | None]:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url:
        return None, "env_SUPABASE_URL_missing"
    if not key:
        return None, "env_SUPABASE_ANON_KEY_missing"

    params = [
        ("select", _FIELDS),
        ("period", f"eq.{period}"),
        ("property_to_asset_pct", f"gte.{min_ratio}"),
        ("order", "property_to_asset_pct.desc.nullslast"),
        ("limit", str(limit)),
    ]
    if revaluation_only:
        params.append(("revaluation_flag", "eq.true"))

    try:
        r = requests.get(
            f"{url}/rest/v1/estate_corp_holdings",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            params=params,
            timeout=8,
        )
    except Exception as e:
        return None, f"request_exc:{type(e).__name__}"
    if r.status_code != 200:
        return None, f"http_{r.status_code}:{(r.text or '')[:160]}"
    try:
        return r.json(), None
    except Exception as e:
        return None, f"json_decode:{type(e).__name__}"


def _enrich(rows: list[dict]) -> list[dict]:
    """hidden_value_krw = fair - book (둘 다 있는 경우만)."""
    for r in rows:
        fv = r.get("fair_value_total_krw")
        bv = r.get("book_value_total_krw")
        if fv is not None and bv is not None:
            r["hidden_value_krw"] = fv - bv
        else:
            r["hidden_value_krw"] = None
    return rows


_COMMERCIAL_KEYS = ("office", "retail_mid_large")


def _build_commercial_market(payload: dict) -> dict | None:
    """sector_pulse payload → commercial cross-link dict. 분리 testable."""
    if not isinstance(payload, dict) or not isinstance(payload.get("sectors"), list):
        return None
    out = {"verdict": None, "sectors": [], "generated_at": payload.get("generated_at")}
    bearish = bullish = unavailable = 0
    for s in payload["sectors"]:
        if not isinstance(s, dict) or s.get("key") not in _COMMERCIAL_KEYS:
            continue
        out["sectors"].append({
            "key": s.get("key"),
            "name": s.get("name"),
            "verdict": s.get("verdict"),
            "yoy_change_pct": s.get("yoy_change_pct"),
            "yield_pct": s.get("yield_pct"),
        })
        v = s.get("verdict")
        if v == "BEARISH":
            bearish += 1
        elif v == "BULLISH":
            bullish += 1
        elif v == "UNAVAILABLE":
            unavailable += 1
    if not out["sectors"]:
        return None
    # commercial-pulse 와 동일 보수 합성: 모두 UNAVAILABLE → UNAVAILABLE,
    # any BEARISH → BEARISH, 모두 BULLISH → BULLISH, else NEUTRAL
    if all(x["verdict"] == "UNAVAILABLE" for x in out["sectors"]):
        out["verdict"] = "UNAVAILABLE"
    elif bearish > 0:
        out["verdict"] = "BEARISH"
    elif bullish == len(out["sectors"]):
        out["verdict"] = "BULLISH"
    else:
        out["verdict"] = "NEUTRAL"
    return out


def _fetch_commercial_market() -> dict | None:
    """sector_pulse.json 에서 commercial-only 추출. 실패 시 None (필드 omit, endpoint 차단 X).

    cross-link 의도: 자산주 watchlist 회사 (상업 부동산 보유) × 상업 시장 동향.
    실패해도 watchlist 응답은 정상 제공.
    """
    url = (os.environ.get("ESTATE_SECTOR_PULSE_SOURCE_URL", "") or "").strip()
    if not url:
        return None
    try:
        r = requests.get(url, timeout=3)
    except Exception:
        return None
    if r.status_code != 200:
        return None
    try:
        payload = r.json()
    except Exception:
        return None
    return _build_commercial_market(payload)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        min_ratio_s = params.get("min_ratio", ["20"])[0].strip() or "20"
        revaluation_s = params.get("revaluation", [""])[0].strip().lower()
        period = params.get("period", [""])[0].strip()
        limit_s = params.get("limit", ["50"])[0].strip() or "50"

        try:
            min_ratio = max(0.0, min(100.0, float(min_ratio_s)))
        except ValueError:
            self._err(400, "invalid_min_ratio", "min_ratio=0~100 float")
            return
        revaluation_only = revaluation_s in ("true", "1", "yes")
        if period and not _PERIOD_RE.match(period):
            self._err(400, "invalid_period", "period=YYYY-Q1|Q2|Q3|FY 형식")
            return
        try:
            limit = max(1, min(200, int(limit_s)))
        except ValueError:
            limit = 50

        if not period:
            period, p_detail = _resolve_latest_period()
            if not period:
                self._err(503, "no_data",
                          f"데이터 없음 또는 DB 조회 실패: {p_detail}")
                return

        rows, detail = _fetch(period, min_ratio, revaluation_only, limit)
        if rows is None:
            self._err(503, "supabase_unavailable", f"DB 조회 실패: {detail}")
            return

        rows = _enrich(rows)
        body = {
            "filters": {
                "min_ratio": min_ratio,
                "revaluation_only": revaluation_only,
                "period": period,
                "limit": limit,
            },
            "watchlist": rows,
            "total_matches": len(rows),
        }
        commercial = _fetch_commercial_market()
        if commercial is not None:
            body["commercial_market"] = commercial
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
