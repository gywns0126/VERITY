"""stock_slice — 종목 1개 상세 번들 (로딩 극단 경량화, 2026-07-08).

문제: /stock 페이지가 전 종목 맵(리포트 4.66MB + US 4.55MB + 내부자 3.2MB + 포렌식 2.6MB
      + 분기·대차·수급 …≈16MB)을 통째로 받아 1종목만 표시 → 브라우저 다운로드+파싱 병목.
해결: 이 엔드포인트가 발행 JSON을 서버에서 티커로 슬라이스해 ~12KB 단일 번들 반환.
      · 모듈 캐시(TTL 30분) — 웜 인스턴스는 재다운로드 없이 메모리에서 슬라이스.
      · 응답 CDN 캐시(s-maxage) — 같은 종목 반복 조회는 엣지에서 즉시, 함수 미실행.

GET /api/stock_slice?ticker=005930  (KR=6자리 → 국내 소스, 그 외 → 美 리포트만; 美 forensics 는 별도 엔드포인트)
🚨 RULE 7 — 원본 발행 사실 그대로 슬라이스만. 가공·점수 없음.
"""
from http.server import BaseHTTPRequestHandler
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlparse

import requests

_logger = logging.getLogger(__name__)

BASE = (os.environ.get("STOCK_SLICE_SOURCE_BASE")
        or "https://rte5guenhonw9fzn.public.blob.vercel-storage.com").strip().rstrip("/")
TIMEOUT = 8
TTL = 1800  # 모듈 캐시 30분 (발행 데이터 = 일 단위 갱신)

# section → 발행 파일. 국내 소스.
KR_SOURCES = {
    "report": "stock_report_public.json",
    "flow": "stock_flow_5d.json",
    "forensics": "disclosure_forensics.json",
    "insider": "insider_trades.json",
    "warn": "market_warnings.json",
    "lending": "securities_lending.json",
    "supply": "supply_demand.json",
    "employment": "nps_employment.json",
}
# 美 = 리포트 슬라이스만 (내부자·13F·컨센서스는 /api/verity/us-forensics 가 이미 per-ticker).
US_SOURCES = {
    "report": "us_stock_report_public.json",
    "report_smallcap": "us_stock_report_us_smallcap.json",
}

_TICKER_RE = re.compile(r"^[A-Za-z0-9.\-]{1,12}$")
_CACHE = {}  # fname -> (epoch, doc)


def _load(fname):
    now = time.time()
    hit = _CACHE.get(fname)
    if hit and (now - hit[0]) < TTL:
        return hit[1]
    try:
        r = requests.get(f"{BASE}/{fname}", timeout=TIMEOUT)
        if r.status_code == 200:
            doc = r.json()
            _CACHE[fname] = (now, doc)
            return doc
    except (requests.RequestException, ValueError, json.JSONDecodeError) as e:
        _logger.error("stock_slice: %s load 실패: %s", fname, e)
    return hit[1] if hit else None  # stale fallback


def _slice(doc, ticker):
    """다양한 발행 스키마에서 ticker 엔트리 추출.
    {stocks:[...]}(리포트·내부자·포렌식·대차) / {stocks:{tk:{}}}(수급·고용)
    / {flows|warnings|top-level: {tk: val}}(수급flow·경보)."""
    if isinstance(doc, list):
        for s in doc:
            if isinstance(s, dict) and str(s.get("ticker") or "").upper() == ticker:
                return s
        return None
    if not isinstance(doc, dict):
        return None
    stocks = doc.get("stocks")
    if isinstance(stocks, dict):
        return stocks.get(ticker) or stocks.get(ticker.upper()) or stocks.get(ticker.lower())
    if isinstance(stocks, list):
        for s in stocks:
            if isinstance(s, dict) and str(s.get("ticker") or "").upper() == ticker:
                return s
        return None
    m = doc.get("flows") or doc.get("warnings") or doc
    if isinstance(m, dict):
        return m.get(ticker) or m.get(ticker.upper())
    return None


def _meta_field(doc, key):
    meta = (doc or {}).get("_meta") if isinstance(doc, dict) else None
    return (meta or {}).get(key)


class handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send(self, code, payload, cache=False):
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if cache:
            # 브라우저 5분 · CDN 30분 · 갱신 중 stale 24h 서빙 (함수 재실행 최소)
            self.send_header("Cache-Control", "public, max-age=300, s-maxage=1800, stale-while-revalidate=86400")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        raw = (params.get("ticker", [""])[0] or "").strip()
        if not raw or not _TICKER_RE.match(raw):
            self._send(400, {"status": "ticker_required", "note": "GET /api/stock_slice?ticker=005930"})
            return
        ticker = raw.upper()
        is_kr = bool(re.match(r"^[0-9]{6}$", ticker))

        if is_kr:
            srcs = KR_SOURCES
        else:
            srcs = US_SOURCES
        docs = {}
        with ThreadPoolExecutor(max_workers=len(srcs)) as ex:
            for k, doc in zip(srcs.keys(), ex.map(lambda f: _load(f), srcs.values())):
                docs[k] = doc

        out = {"status": "ok", "ticker": ticker, "market": "KR" if is_kr else "US"}

        if is_kr:
            report = _slice(docs.get("report"), ticker)
            out["report"] = report
            out["report_as_of"] = _meta_field(docs.get("report"), "generated_at")
            out["flow"] = _slice(docs.get("flow"), ticker)
            out["forensics"] = _slice(docs.get("forensics"), ticker)
            out["insider"] = _slice(docs.get("insider"), ticker)
            out["warn"] = _slice(docs.get("warn"), ticker)
            out["lending"] = _slice(docs.get("lending"), ticker)
            out["lend_as_of"] = _meta_field(docs.get("lending"), "as_of")
            out["supply"] = _slice(docs.get("supply"), ticker)
            out["employment"] = _slice(docs.get("employment"), ticker)
        else:
            report = _slice(docs.get("report"), ticker) or _slice(docs.get("report_smallcap"), ticker)
            out["report"] = report
            out["report_as_of"] = _meta_field(docs.get("report"), "generated_at")

        # report None = 리포트 미보유 종목(유효 공백) — 200 유지, 컴포넌트가 stub 안내.
        self._send(200, out, cache=True)
