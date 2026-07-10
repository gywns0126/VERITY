"""
GET /api/verity/us-forensics?ticker=MSFT  — 단일 ticker 美 forensics 통합 (4 소스 집계)

집계 소스 (Blob, publish-data 발행):
  insider     = us_insider_trades.json    (SEC Form4 내부자)
  holdings    = us_major_holdings.json     (SEC 13D/13G 5%+ 대량보유)
  smart_money = us_smart_money_13f.json    (집중형 13F 스마트머니)
  (consensus 섹션 = 2026-07-10 제거 — yfinance 목표가·투자의견은 Benzinga/S&P 실권리,
   재배포 blocker. 표시 = 출처 링크아웃 대체, 숫자 부활 = 유료 티어 Polygon×Benzinga 정식 라이선스.)

[[project_us_financials_sec_edgar]] (b). 프런트(PublicStockReport 등)가 per-ticker 1콜로 소비.
4 소스 병렬 fetch(maxDuration 5s 내). RULE 7 = 공시/외부 사실만(우리 자체 점수 0).

거짓말 트랩:
  소스 fetch 실패 → 해당 섹션 null + sources[k].status="unavailable" (가짜 X).
  ticker 가 소스에 없음 → 섹션 null (유효 공백 — 그 종목에 해당 공시 없음, 에러 아님).
  4 소스 전부 실패 → 503.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import requests

_logger = logging.getLogger(__name__)

SOURCE_BASE_ENV = "US_FORENSICS_SOURCE_BASE"
SOURCE_BASE_FALLBACK = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"

SOURCES = {
    "insider": "us_insider_trades.json",
    "holdings": "us_major_holdings.json",
    "smart_money": "us_smart_money_13f.json",
}

TIMEOUT_SEC = 4          # vercel.json maxDuration=5 안전 마진 (병렬이라 벽시계 ≈ 1 fetch)
CACHE_MAX_AGE = 3600     # 1시간 — 소스는 일/주 단위 갱신

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def _source_base() -> str:
    return (os.environ.get(SOURCE_BASE_ENV) or SOURCE_BASE_FALLBACK).strip().rstrip("/")


def _fetch_one(key: str, fname: str, ticker: str):
    """단일 소스 fetch → (key, entry|None, meta, status). entry = ticker 매칭 stock 또는 None."""
    url = f"{_source_base()}/{fname}?_={int(time.time())}"
    try:
        r = requests.get(url, timeout=TIMEOUT_SEC)
        if r.status_code != 200:
            return key, None, None, "unavailable"
        doc = r.json()
    except (requests.RequestException, ValueError, json.JSONDecodeError) as e:
        _logger.error("us_forensics: %s fetch/parse 실패: %s", fname, e)
        return key, None, None, "unavailable"
    entry = None
    for s in (doc.get("stocks") or []):
        if str(s.get("ticker") or "").upper() == ticker:
            entry = s
            break
    meta = doc.get("_meta") or {}
    return key, entry, {"generated_at": meta.get("generated_at"), "source": meta.get("source")}, "ok"


class handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send(self, code: int, payload: dict, cache: bool = False):
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if cache:
            self.send_header("Cache-Control", f"public, max-age={CACHE_MAX_AGE}")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        ticker = (params.get("ticker", [""])[0] or "").strip().upper()
        if not ticker:
            self._send(400, {"status": "ticker_required",
                             "note": "GET /api/verity/us-forensics?ticker=MSFT"})
            return
        if not _TICKER_RE.match(ticker):
            self._send(400, {"status": "invalid_ticker", "ticker": ticker})
            return

        with ThreadPoolExecutor(max_workers=len(SOURCES)) as ex:
            results = list(ex.map(lambda kv: _fetch_one(kv[0], kv[1], ticker), SOURCES.items()))

        sections: dict = {}
        sources: dict = {}
        ok_n = 0
        for key, entry, meta, status in results:
            sections[key] = entry          # None = 그 종목에 해당 공시 없음(유효 공백)
            sources[key] = {"status": status, **(meta or {})}
            if status == "ok":
                ok_n += 1

        if ok_n == 0:
            self._send(503, {"status": "source_unavailable", "ticker": ticker,
                             "sources": sources})
            return

        self._send(200, {
            "status": "ok",
            "ticker": ticker,
            "sections": sections,          # insider / holdings / smart_money
            "sources": sources,            # 소스별 status + generated_at (신선도 투명)
        }, cache=True)

# redeploy-bump 2026-07-10 — dd5066df7 이 봇커밋 87개에 묻혀 ignoreCommand 창(50) 밖 = deploy skip 재발(3차). fresh HEAD 재트리거.
