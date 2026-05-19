"""
GET /api/estate/corp-disposals?ticker=035420[&months=12]

ESTATE corp Signal 3 — 회사 부동산·유형자산 양도/처분 공시 list (DART 주요사항보고서).
Last deploy marker: 2026-05-20 00:05 KST — DART_API_KEY production env baking redeploy.

데이터 흐름:
  ticker → Supabase estate_corp_holdings.corp_code → DART list.json + 키워드 필터.
  ticker 가 holdings 에 없으면 404 (corp snapshot 미수집).

키워드 필터:
  부동산 토큰 {유형자산, 토지, 부동산, 건물, 본사, 지점, 사업장} ∩
  처분 토큰 {양도, 처분, 매각, 매도}
  exclude: 자기주식 (주식 처분 제외)

응답:
{
  "ticker": "035420", "corp_code": "00266961", "company_name": "NAVER",
  "period_months": 12,
  "disposals": [
    {"rcept_dt": "20251015", "report_nm": "주요사항보고서(유형자산 양도결정)", "rcept_no": "..."}
  ],
  "total_count": 1
}
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import re
from urllib.parse import parse_qs, urlparse

import requests

_logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"^\d{6}$")

_PROP_TOKENS = ("유형자산", "토지", "부동산", "건물", "본사", "지점", "사업장")
_DISPOSAL_TOKENS = ("양도", "처분", "매각", "매도")
_EXCLUDE_TOKENS = ("자기주식", "주식양도", "주식 양도")

KST = timezone(timedelta(hours=9))


def _is_property_disposal(report_nm: str) -> bool:
    if not report_nm:
        return False
    if any(x in report_nm for x in _EXCLUDE_TOKENS):
        return False
    has_prop = any(t in report_nm for t in _PROP_TOKENS)
    has_disp = any(t in report_nm for t in _DISPOSAL_TOKENS)
    return has_prop and has_disp


def _lookup_corp_code(ticker: str) -> tuple[dict | None, str | None]:
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
            params={
                "select": "corp_code,ticker,company_name",
                "ticker": f"eq.{ticker}",
                "order": "period.desc",
                "limit": "1",
            },
            timeout=5,
        )
    except Exception as e:
        return None, f"request_exc:{type(e).__name__}"
    if r.status_code != 200:
        return None, f"http_{r.status_code}"
    try:
        rows = r.json()
    except Exception as e:
        return None, f"json_decode:{type(e).__name__}"
    if not rows:
        return None, "ticker_not_in_holdings"
    return rows[0], None


def _fetch_disclosures(corp_code: str, months: int) -> tuple[list[dict] | None, str | None]:
    key = os.environ.get("DART_API_KEY", "")
    if not key:
        return None, "env_DART_API_KEY_missing"
    today = datetime.now(KST).date()
    bgn = (today - timedelta(days=months * 31)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    try:
        r = requests.get(
            "https://opendart.fss.or.kr/api/list.json",
            params={
                "crtfc_key": key,
                "corp_code": corp_code,
                "bgn_de": bgn,
                "end_de": end,
                "page_count": "100",
                "sort": "date",
                "sort_mth": "desc",
            },
            timeout=8,
        )
    except Exception as e:
        return None, f"request_exc:{type(e).__name__}"
    if r.status_code != 200:
        return None, f"http_{r.status_code}"
    try:
        d = r.json()
    except Exception as e:
        return None, f"json_decode:{type(e).__name__}"
    status = d.get("status")
    if status == "013":
        return [], None  # 조회 데이터 없음 — 정상 빈 리스트
    if status not in ("000", None):
        return None, f"dart_status_{status}"
    return d.get("list", []), None


def _filter_disposals(rows: list[dict]) -> list[dict]:
    out = []
    for d in rows:
        nm = d.get("report_nm", "")
        if not _is_property_disposal(nm):
            continue
        out.append({
            "rcept_dt": d.get("rcept_dt", ""),
            "report_nm": nm,
            "rcept_no": d.get("rcept_no", ""),
            "flr_nm": d.get("flr_nm", ""),
        })
    return out


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
        months_s = params.get("months", ["12"])[0].strip() or "12"

        if not ticker or not _TICKER_RE.match(ticker):
            self._err(400, "invalid_ticker", "ticker=6자리 숫자(KRX) 필수")
            return
        try:
            months = max(1, min(24, int(months_s)))
        except ValueError:
            months = 12

        meta, detail = _lookup_corp_code(ticker)
        if meta is None:
            if detail == "ticker_not_in_holdings":
                self._err(404, "no_corp_data", f"ticker={ticker} corp snapshot 미수집")
            else:
                self._err(503, "supabase_unavailable", f"DB 조회 실패: {detail}")
            return

        disclosures, detail = _fetch_disclosures(meta["corp_code"], months)
        if disclosures is None:
            self._err(503, "dart_unavailable", f"DART 조회 실패: {detail}")
            return

        disposals = _filter_disposals(disclosures)
        body = {
            "ticker": meta.get("ticker"),
            "corp_code": meta.get("corp_code"),
            "company_name": meta.get("company_name"),
            "period_months": months,
            "disposals": disposals,
            "total_count": len(disposals),
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
