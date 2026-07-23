"""GET /api/ai_report?ticker= — AI 해석 리포트 PDF (Typst 조판, 다운로드 파일).

팩트 리포트(서버 조판)와 동일 파이프라인 + 맨 앞 'AI 해석' 서술 장.
  · 팩트 본문 = fact_report._build_data (공시·수집 사실 · LLM 0 · 점수 0)
  · AI 해석 장 = stock_brief 캐시/생성 브리핑 (기존 무료 v0 grounding 조립 재사용 —
    신규 LLM 서사 기능 아님 = RULE 6. 화면에 이미 노출되던 브리핑을 서버에서 조판만.)

브라우저 window.print(화면 캡쳐) 대체 (PM 2026-07-23) — 팩트 리포트와 동일하게 진짜 PDF 파일.
RULE 7 = AI 해석은 사실 위 관측 라벨 · 점수·등급·추천 0. footer disclaimer 고정.

sibling import 패턴은 이 코드베이스 표준 (stock_detail→api.stock, holdings→api.supabase_client 등).
"""
from __future__ import annotations

import json
import re
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler

from api.fact_report import KST, _TICKER_KR, _TICKER_US, _build_data, _render
from api.stock_brief import (
    DAILY_CAP,
    GEMINI_API_KEY,
    _build_grounding,
    _cache_get,
    _cache_put,
    _date_key,
    _generate,
    _today_count,
)

_AI_DISCLAIMER = (
    "AI 해석 = 공개 데이터(DART·SEC·네이버·금융위) 기반 자동 생성 서술 · "
    "팩트 섹션은 공시·수집 사실 · 점수·등급·추천 아님 · 판단과 책임은 본인 · AlphaNest AI 해석 리포트"
)


def _parse_brief(brief: str):
    """'## 제목\\n본문' 마크다운 → [{h, body}]. 본문 개행·중복공백은 단일 공백(Typst 문단 정리)."""
    out = []
    for chunk in re.split(r"(?m)^##\s+", brief or ""):
        chunk = chunk.strip()
        if not chunk:
            continue
        head, _, body = chunk.partition("\n")
        head = head.strip()
        body = re.sub(r"\s+", " ", body).strip()
        if head:
            out.append({"h": head, "body": body or "확인된 데이터 없음"})
    return out


def _get_brief(ticker: str):
    """(payload, err_code, err_json) — 캐시 우선, miss 시 키·캡 가드 후 생성(stock_brief 로직 재사용).

    프론트가 먼저 /api/verity/stock-brief 로 생성·캐시를 데운 뒤 이 엔드포인트를 열면 캐시 히트(생성 0).
    캐시 불통 등으로 miss 여도 여기서 1회 생성 폴백(캡·키 가드는 동일 적용)."""
    cached = _cache_get(ticker)
    if cached and cached.get("brief"):
        return cached, None, None
    if not GEMINI_API_KEY:
        return None, 503, {"error": "not_configured"}
    if _today_count() >= DAILY_CAP:
        return None, 429, {"error": "daily_cap",
                           "message": "오늘 신규 브리핑 생성량이 가득 찼어요. 내일 다시 시도해 주세요 — 이미 생성된 종목은 계속 볼 수 있어요."}
    grounding, name, used = _build_grounding(ticker)
    if grounding is None:
        return None, 404, {"error": "no_report_data", "message": "아직 정밀 리포트 데이터가 없는 종목이에요."}
    try:
        brief = _generate(grounding)
    except Exception:  # noqa: BLE001
        return None, 503, {"error": "llm_unavailable", "message": "브리핑 생성이 잠시 불안정해요. 잠시 후 다시 시도해 주세요."}
    if not brief:
        return None, 503, {"error": "llm_empty"}
    payload = {
        "ticker": ticker, "name": name, "date_key": _date_key(),
        "generated_at": datetime.now(KST).isoformat(),
        "brief": brief, "sources": used, "cached": False,
    }
    _cache_put(ticker, payload)
    return payload, None, None


class handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _err(self, code: int, obj: dict):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
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
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            ticker = (qs.get("ticker", [""])[0] or "").strip().upper()
            if not (_TICKER_KR.match(ticker) or _TICKER_US.match(ticker)):
                return self._err(400, {"error": "invalid_ticker"})

            # 팩트 본문 (공시·수집 사실 — 리포트 미보유 종목이면 404, 창작 차단)
            data = _build_data(ticker)
            if not data:
                return self._err(404, {"error": "unknown_ticker",
                                       "message": "아직 정밀 리포트 데이터가 없는 종목이에요."})

            # AI 해석 장 (캐시/생성 브리핑)
            brief_payload, ec, ej = _get_brief(ticker)
            if brief_payload is None:
                return self._err(ec, ej)

            ai_sections = _parse_brief(brief_payload.get("brief") or "")
            if ai_sections:
                data["ai"] = {
                    "sections": ai_sections,
                    "sources": [str(x) for x in (brief_payload.get("sources") or [])],
                }
            data["report_label"] = "AI 해석 리포트"
            data["disclaimer"] = _AI_DISCLAIMER

            pdf = _render(data)
            fname = f"AlphaNest_AIReport_{ticker}_{datetime.now(KST).strftime('%Y%m%d')}.pdf"
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Disposition", f'inline; filename="{fname}"')
            self.send_header("Content-Length", str(len(pdf)))
            self.send_header("Cache-Control", "public, max-age=600")
            self.end_headers()
            self.wfile.write(pdf)
        except Exception as e:  # noqa: BLE001
            self._err(500, {"error": type(e).__name__})
