"""
GET /api/verity/us-forensics?ticker=MSFT  — 단일 ticker 美 forensics 통합 (6 소스 집계)

집계 소스 (Blob, publish-data 발행):
  insider     = us_insider_trades.json    (SEC Form4 내부자)
  holdings    = us_major_holdings.json     (SEC 13D/13G 5%+ 대량보유)
  smart_money = us_smart_money_13f.json    (집중형 13F 스마트머니)
  short_interest = us_short_interest.json  (거래소 공매도 잔고)
  form144     = us_form144.json             (제한주식·지배증권 매도 예정 신고)
  (consensus 섹션 = 2026-07-10 제거 — yfinance 목표가·투자의견은 Benzinga/S&P 실권리,
   재배포 blocker. 표시 = 출처 링크아웃 대체, 숫자 부활 = 유료 티어 Polygon×Benzinga 정식 라이선스.)

[[project_us_financials_sec_edgar]] (b). 프런트(PublicStockReport 등)가 per-ticker 1콜로 소비.
6 소스 병렬 fetch(maxDuration 5s 내). RULE 7 = 공시/외부 사실만(우리 자체 점수 0).

거짓말 트랩:
  소스 fetch 실패 → 해당 섹션 null + sources[k].status="unavailable" (가짜 X).
  ticker 가 이벤트형 소스에 없음 → "공시 없음"으로 단정하지 않고 no_record_in_snapshot.
  8-K는 전 유니버스 상태 행으로 recent_8k / no_recent_8k / unknown을 구분한다.
  6 소스 전부 실패 → 503.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler
from threading import Lock
from urllib.parse import parse_qs, urlparse

import requests

_logger = logging.getLogger(__name__)

SOURCE_BASE_ENV = "US_FORENSICS_SOURCE_BASE"
SOURCE_BASE_FALLBACK = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"

# 🚫 "consensus": us_analyst_consensus.json 재추가 금지 (PM 확정 2026-07-10).
#    컨센서스 = 발행 제외 (Benzinga/S&P 실권리). 세션 간 재추가 핑퐁 2회 — 이 결정 변경 = PM 재승인 필수.
SOURCES = {
    "insider": "us_insider_trades.json",
    "holdings": "us_major_holdings.json",
    "smart_money": "us_smart_money_13f.json",
    "short_interest": "us_short_interest.json",
    "disclosure_forensics": "us_disclosure_forensics.json",
    "form144": "us_form144.json",
}

TIMEOUT_SEC = 4          # vercel.json maxDuration=5 안전 마진 (병렬이라 벽시계 ≈ 1 fetch)
CACHE_MAX_AGE = 3600     # 1시간 — 소스는 일/주 단위 갱신
SOURCE_CACHE_TTL = 300  # Shared snapshot reuse; retain original generated_at.
CDN_MAX_AGE = 300
_SOURCE_CACHE = {}  # Fixed six filenames; independent of visitor ticker count.
_SOURCE_LOCKS = {fname: Lock() for fname in SOURCES.values()}

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def _source_base() -> str:
    return (os.environ.get(SOURCE_BASE_ENV) or SOURCE_BASE_FALLBACK).strip().rstrip("/")


def _load_source(fname: str):
    url = f"{_source_base()}/{fname}"
    # A second ticker must not download the same whole snapshot concurrently.
    with _SOURCE_LOCKS[fname]:
        hit = _SOURCE_CACHE.get(fname)
        if hit and hit[0] != url:
            hit = None
        if hit and time.monotonic() < hit[1]:
            return hit[2]
        try:
            r = requests.get(url, timeout=TIMEOUT_SEC, headers=hit[3] if hit else {})
            if r.status_code == 304 and hit:
                doc, validators = hit[2], hit[3]
            elif r.status_code == 200:
                doc = r.json()
                if not isinstance(doc, dict):
                    raise ValueError("source JSON must be an object")
                stocks, meta = doc.get("stocks") or [], doc.get("_meta") or {}
                if not isinstance(stocks, list) or any(not isinstance(row, dict) for row in stocks) or not isinstance(meta, dict):
                    raise ValueError("source snapshot shape is invalid")
                validators = {request_key: r.headers[response_key]
                              for response_key, request_key in
                              (("ETag", "If-None-Match"), ("Last-Modified", "If-Modified-Since"))
                              if r.headers.get(response_key)}
            else:
                return None
            _SOURCE_CACHE[fname] = (url, time.monotonic() + SOURCE_CACHE_TTL, doc, validators)
            return doc
        except (requests.RequestException, ValueError) as e:
            _logger.error("us_forensics: %s fetch/parse 실패: %s", fname, e)
            return None


def _fetch_one(key: str, fname: str, ticker: str):
    """단일 소스 fetch → (key, entry|None, meta, status). entry = ticker 매칭 stock 또는 None."""
    doc = _load_source(fname)
    if doc is None:
        return key, None, None, "unavailable"
    entry = None
    for s in (doc.get("stocks") or []):
        if str(s.get("ticker") or "").upper() == ticker:
            entry = s
            break
    meta = doc.get("_meta") or {}
    public_meta_keys = (
        "generated_at",
        "source",
        "universe_n",
        "processed_n",
        "unprocessed_n",
        "event_present_n",
        "no_recent_8k_n",
        "recent_window_days",
        "deep_window_days",
    )
    public_meta = {name: meta.get(name) for name in public_meta_keys if name in meta}
    return key, entry, public_meta, "ok"


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
        present_n = 0
        for key, entry, meta, status in results:
            sections[key] = entry
            if status != "ok":
                data_state = "source_unavailable"
            elif entry is None:
                data_state = "not_in_snapshot"
            elif key == "disclosure_forensics":
                data_state = entry.get("event_state") or "unknown"
            else:
                data_state = "record_present"
            sources[key] = {"status": status, "data_state": data_state, **(meta or {})}
            if status == "ok":
                ok_n += 1
            if entry is not None:
                present_n += 1

        if ok_n == 0:
            self._send(503, {"status": "source_unavailable", "ticker": ticker,
                             "sources": sources})
            return

        self._send(200, {
            "status": "ok",
            "ticker": ticker,
            "sections": sections,          # insider / holdings / smart_money / short_interest / disclosure_forensics / form144
            "sources": sources,            # 소스별 status + generated_at (신선도 투명)
            "coverage": {
                "source_connected_n": ok_n,
                "source_total_n": len(SOURCES),
                "record_present_n": present_n,
            },
        }, cache=ok_n == len(SOURCES))

# redeploy-bump 2026-07-10 — dd5066df7 이 봇커밋 87개에 묻혀 ignoreCommand 창(50) 밖 = deploy skip 재발(3차). fresh HEAD 재트리거.
