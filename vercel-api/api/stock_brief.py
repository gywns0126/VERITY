"""
GET /api/verity/stock-brief?ticker=005930  — 온디맨드 AI 브리핑 (무료 v0, 자판기 전신)

파이프라인: 캐시(Supabase Storage) → miss 시 발행 JSON grounding 조립 → Gemini flash-lite → 캐시 저장.
  grounding (Blob, publish-data 발행 — 전부 이미 공개된 사실):
    KR = stock_report_public + dart_quarterly_public + insider_trades + disclosure_forensics
    US = us_stock_report_public(+smallcap) + us_quarterly_public + us_insider_trades

RULE 6 = LLM 은 조립만 — 제공 grounding 밖 숫자/가격/전망 생성 금지 (프롬프트 강제).
RULE 7 = 사실+관측 라벨, 점수/등급/추천 0. disclaimer 필드 고정.
비용 가드 = ①같은 종목·같은 날 = 캐시 1회 생성 ②일일 신규 생성 캡(BRIEF_DAILY_CAP, 기본 50)
  ③Gemini flash-lite (Claude 월예산 무접촉). 캐시/캡 store = verity-reports 버킷 briefs/ (신규 테이블/버킷 0).

거짓말 트랩:
  grounding 핵심(stock_report entry) 없음 → 404 (리포트 미보유 종목 — 생성 안 함, 창작 차단)
  Gemini 키 없음/실패 → 503 (결정론 위장 생성 없음)
  캡 초과 → 429 + retry_after_hint
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import requests
from google import genai

_logger = logging.getLogger(__name__)

SOURCE_BASE = (os.environ.get("US_FORENSICS_SOURCE_BASE") or "https://rte5guenhonw9fzn.public.blob.vercel-storage.com").strip().rstrip("/")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite").strip() or "gemini-2.5-flash-lite"

BUCKET = "verity-reports"           # reports.py 와 동일 버킷 재사용 (신규 버킷 생성 불요)
BRIEF_PREFIX = "briefs"             # briefs/{YYYY-MM-DD}/{TICKER}.json
DAILY_CAP = int(os.environ.get("BRIEF_DAILY_CAP", "50") or "50")
FETCH_TIMEOUT = 6
KST = timezone(timedelta(hours=9))

_TICKER_KR = re.compile(r"^\d{6}$")
_TICKER_US = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

KR_SOURCES = {
    "report": "stock_report_public.json",
    "quarterly": "dart_quarterly_public.json",
    "insider": "insider_trades.json",
    "forensics": "disclosure_forensics.json",
}
US_SOURCES = {
    "report": "us_stock_report_public.json",
    "report_smallcap": "us_stock_report_us_smallcap.json",
    "quarterly": "us_quarterly_public.json",
    "insider": "us_insider_trades.json",
}

DISCLAIMER = "공개 데이터(DART·SEC·네이버·금융위) 사실 기반 자동 생성 · 점수·등급·종목 추천 아님 · 투자 판단과 책임은 본인에게 있습니다"

PROMPT_RULES = """너는 아래 [데이터]만 사용해 한국어 종목 브리핑을 쓴다. 절대 규칙:
1. [데이터]에 없는 숫자·가격·날짜·사실을 만들지 마라. 목표가·매수/매도 의견·수익률 전망 금지.
2. 각 섹션 끝에 근거 출처를 괄호로 표기하라. 예: (출처: DART 분기재무)
3. 데이터가 비어 있는 섹션은 "확인된 데이터 없음"이라고 쓰고 넘어가라. 추정으로 채우지 마라.
4. 형식: 아래 5개 섹션 제목을 정확히 사용, 섹션당 2~4문장, 전체 700자 이내.
## 한눈에
## 재무 흐름
## 수급·내부자
## 공시·리스크
## 지켜볼 것"""


def _date_key() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _storage_headers() -> dict:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }


def _cache_path(ticker: str) -> str:
    return f"{BRIEF_PREFIX}/{_date_key()}/{ticker}.json"


def _cache_get(ticker: str):
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return None
    try:
        r = requests.get(
            f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{_cache_path(ticker)}",
            headers=_storage_headers(), timeout=FETCH_TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()
    except (requests.RequestException, ValueError):
        pass
    return None


def _cache_put(ticker: str, payload: dict) -> None:
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return
    try:
        requests.post(
            f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{_cache_path(ticker)}",
            headers={**_storage_headers(), "Content-Type": "application/json", "x-upsert": "true"},
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=FETCH_TIMEOUT,
        )
    except requests.RequestException as e:
        _logger.warning("brief cache put 실패 (생성 결과는 반환): %s", e)


def _today_count() -> int:
    """오늘 신규 생성 수 — 캡 판정. store 불통 시 캡 초과 취급(비용 안전 방향)."""
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return DAILY_CAP
    try:
        r = requests.post(
            f"{SUPABASE_URL}/storage/v1/object/list/{BUCKET}",
            headers={**_storage_headers(), "Content-Type": "application/json"},
            json={"prefix": f"{BRIEF_PREFIX}/{_date_key()}/", "limit": 1000},
            timeout=FETCH_TIMEOUT,
        )
        if r.status_code != 200:
            return DAILY_CAP
        return len(r.json() or [])
    except (requests.RequestException, ValueError):
        return DAILY_CAP


def _fetch_source(key: str, fname: str):
    try:
        r = requests.get(f"{SOURCE_BASE}/{fname}?_={int(time.time())}", timeout=FETCH_TIMEOUT)
        if r.status_code != 200:
            return key, None
        return key, r.json()
    except (requests.RequestException, ValueError):
        return key, None


def _entry_for(doc, ticker: str):
    if not doc:
        return None
    for s in (doc.get("stocks") or []):
        if str(s.get("ticker") or "").upper() == ticker:
            return s
    return None


def _slim(obj, max_chars: int) -> str:
    """grounding 항목을 프롬프트 예산 안으로 — 직렬화 후 하드 컷 (LLM 에 raw JSON 그대로)."""
    if obj is None:
        return "없음"
    s = json.dumps(obj, ensure_ascii=False, default=str)
    return s[:max_chars]


def _build_grounding(ticker: str) -> tuple:
    """(grounding_text, name, sources_used) — report entry 없으면 (None, None, [])."""
    is_kr = bool(_TICKER_KR.match(ticker))
    sources = KR_SOURCES if is_kr else US_SOURCES
    with ThreadPoolExecutor(max_workers=len(sources)) as ex:
        results = dict(ex.map(lambda kv: _fetch_source(kv[0], kv[1]), sources.items()))

    report = _entry_for(results.get("report"), ticker)
    if report is None and not is_kr:
        report = _entry_for(results.get("report_smallcap"), ticker)
    if report is None:
        return None, None, []

    name = report.get("name_ko") or report.get("name") or ticker
    used = ["stock_report(DART·네이버·SEC 집계)"]

    # 분기추이 — 최근 8개 항목만 (프롬프트 예산)
    q_entry = None
    q_doc = results.get("quarterly")
    if q_doc:
        stocks = q_doc.get("stocks")
        raw = stocks.get(ticker) if isinstance(stocks, dict) else _entry_for(q_doc, ticker)
        if raw:
            q_entry = raw
            if isinstance(raw, dict) and isinstance(raw.get("quarters"), list):
                q_entry = {**raw, "quarters": raw["quarters"][-8:]}
            used.append("분기재무(DART·SEC)")

    ins_entry = _entry_for(results.get("insider"), ticker)
    if ins_entry and isinstance(ins_entry.get("trades"), list):
        ins_entry = {**ins_entry, "trades": ins_entry["trades"][:10]}
    if ins_entry:
        used.append("내부자거래(DART·SEC Form4)")

    forn_entry = _entry_for(results.get("forensics"), ticker) if is_kr else None
    if forn_entry:
        used.append("공시포렌식(DART)")

    grounding = "\n".join([
        f"[종목] {name} ({ticker})",
        f"[리포트 사실] {_slim(report, 4000)}",
        f"[분기 재무] {_slim(q_entry, 2500)}",
        f"[내부자 거래] {_slim(ins_entry, 1500)}",
        f"[공시 이벤트] {_slim(forn_entry, 1200)}",
    ])
    return grounding, name, used


def _generate(grounding: str):
    client = genai.Client(api_key=GEMINI_API_KEY)
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=f"[데이터]\n{grounding}",
        config={"system_instruction": PROMPT_RULES, "temperature": 0.2, "max_output_tokens": 1400},
    )
    return (resp.text or "").strip()


class handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        try:
            qs = parse_qs(urlparse(self.path).query)
            ticker = (qs.get("ticker", [""])[0] or "").strip().upper()
            if not (_TICKER_KR.match(ticker) or _TICKER_US.match(ticker)):
                return self._send(400, {"error": "invalid_ticker"})

            cached = _cache_get(ticker)
            if cached:
                cached["cached"] = True
                return self._send(200, cached)

            if not GEMINI_API_KEY:
                return self._send(503, {"error": "not_configured"})

            if _today_count() >= DAILY_CAP:
                return self._send(429, {
                    "error": "daily_cap",
                    "message": "오늘 신규 브리핑 생성량이 가득 찼어요. 내일 다시 시도해 주세요 — 이미 생성된 종목은 계속 볼 수 있어요.",
                })

            grounding, name, used = _build_grounding(ticker)
            if grounding is None:
                return self._send(404, {"error": "no_report_data", "message": "아직 정밀 리포트 데이터가 없는 종목이에요."})

            try:
                brief = _generate(grounding)
            except Exception as e:
                _logger.error("gemini 생성 실패: %s", type(e).__name__)
                return self._send(503, {"error": "llm_unavailable", "message": "브리핑 생성이 잠시 불안정해요. 잠시 후 다시 시도해 주세요."})
            if not brief:
                return self._send(503, {"error": "llm_empty"})

            payload = {
                "ticker": ticker,
                "name": name,
                "date_key": _date_key(),
                "generated_at": datetime.now(KST).isoformat(),
                "brief": brief,
                "sources": used,
                "disclaimer": DISCLAIMER,
                "cached": False,
            }
            _cache_put(ticker, payload)
            return self._send(200, payload)
        except Exception:
            _logger.exception("stock_brief 처리 실패")
            return self._send(500, {"error": "internal"})
