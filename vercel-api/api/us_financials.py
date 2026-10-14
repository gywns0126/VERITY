"""
GET /api/verity/us-financials                 — US15 표준화 재무 summary (전체)
GET /api/verity/us-financials?ticker=MSFT     — 단일 ticker 전체 snapshot (8Q+5Y 시계열+파생)

데이터 source = data/us_financials/ (SEC EDGAR XBRL, us_financials_builder 월 1회 cron).
read-through: raw.githubusercontent main (gh-pages 아님 — us_financials 는 main 커밋).
project_us_financials_sec_edgar 정합. v0.3 sector calibration 반영 (pretax_margin / fcf_na_reason).

거짓말 트랩:
    fetch fail → 503 + status="source_unavailable" (가짜 데이터 X).
    ticker 없으면 404 (universe 외).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler
from threading import Lock
from urllib.parse import parse_qs, urlparse

import requests

_logger = logging.getLogger(__name__)

SOURCE_BASE_ENV = "US_FINANCIALS_SOURCE_BASE"
# 2026-05-26 VERITY private 전환 sweep — e916ea7b 누락 보완. Vercel Blob 으로 cutover.
# raw.githubusercontent.com/gywns0126/VERITY/main/... 은 private 404 → 503.
# base=rte5guenhonw9fzn ([[project_repo_visibility_plan]]).
SOURCE_BASE_FALLBACK = (
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_financials"
)

TIMEOUT_SEC = 4          # vercel.json maxDuration=5 안전 마진
CACHE_MAX_AGE = 3600     # 1시간 — us_financials 는 월 1회 갱신 (분기 보고서)
SOURCE_CACHE_TTL = 300
CDN_MAX_AGE = 300
SOURCE_CACHE_LIMIT = 64
_SOURCE_CACHE = OrderedDict()
_CACHE_LOCK = Lock()
# Fixed-size stripes bound synchronization memory for arbitrary valid tickers.
_SOURCE_LOCKS = tuple(Lock() for _ in range(16))

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def _source_base() -> str:
    return (os.environ.get(SOURCE_BASE_ENV) or SOURCE_BASE_FALLBACK).strip().rstrip("/")


def _fetch_json(rel_path: str):
    """Stable public Blob URL; success-only bounded read-through cache."""
    url = f"{_source_base()}/{rel_path}"
    with _SOURCE_LOCKS[hash(url) % len(_SOURCE_LOCKS)]:
        with _CACHE_LOCK:
            hit = _SOURCE_CACHE.get(url)
            if hit:
                _SOURCE_CACHE.move_to_end(url)
                if time.monotonic() < hit[0]:
                    return hit[1], 200
        try:
            r = requests.get(url, timeout=TIMEOUT_SEC, headers=hit[2] if hit else {})
            if r.status_code == 304 and hit:
                payload, validators = hit[1], hit[2]
            elif r.status_code == 404:
                return None, 404
            elif r.status_code == 200:
                payload = r.json()
                if not isinstance(payload, dict):
                    raise ValueError("source JSON must be an object")
                validators = {request_key: r.headers[response_key]
                              for response_key, request_key in
                              (("ETag", "If-None-Match"), ("Last-Modified", "If-Modified-Since"))
                              if r.headers.get(response_key)}
            else:
                return None, 503
        except (requests.RequestException, ValueError) as e:
            _logger.error("us_financials: source fetch/parse failed %s: %s", rel_path, e)
            return None, 503
        with _CACHE_LOCK:
            _SOURCE_CACHE[url] = (time.monotonic() + SOURCE_CACHE_TTL, payload, validators)
            _SOURCE_CACHE.move_to_end(url)
            while len(_SOURCE_CACHE) > SOURCE_CACHE_LIMIT:
                _SOURCE_CACHE.popitem(last=False)
        return payload, 200


class handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send(self, code: int, payload: dict, cache: bool = False):
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if cache and code == 200:
            self.send_header("Cache-Control", f"public, max-age={CACHE_MAX_AGE}, s-maxage={CDN_MAX_AGE}")
        else:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        ticker = (params.get("ticker", [""])[0] or "").strip().upper()

        if ticker:
            if not _TICKER_RE.match(ticker):
                self._send(400, {"status": "invalid_ticker", "ticker": ticker})
                return
            payload, code = _fetch_json(f"{ticker}.json")
            if code == 404:
                self._send(404, {"status": "not_found", "ticker": ticker,
                                 "note": "US Financials universe 외 또는 미수집"})
                return
            if payload is None:
                self._send(503, {"status": "source_unavailable", "ticker": ticker})
                return
            self._send(200, payload, cache=True)
            return

        # ticker 미지정 → universe summary
        payload, code = _fetch_json("_summary.json")
        if payload is None:
            self._send(503, {"status": "source_unavailable",
                             "note": "us_financials/_summary.json fetch 실패"})
            return
        self._send(200, payload, cache=True)
