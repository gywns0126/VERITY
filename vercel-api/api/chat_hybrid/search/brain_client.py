"""
VERITY Chat Hybrid — Brain 컨텍스트 빌더

기존 api/intelligence/chat_engine.py 의 _load_portfolio_context / _build_stock_context
를 재사용하되, 다음 차이:
  1. 티커 타겟팅 — classifier 가 추출한 related_tickers 를 우선 주입
  2. 캐시 계층 연동 (tier=brain, TTL 1분)
  3. 반환 형식 통일 (text + citations=[])

외부 호출 0 — 로컬 파일만.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from api.chat_hybrid import cache

logger = logging.getLogger(__name__)


def _portfolio_path() -> str:
    try:
        from api.config import PORTFOLIO_PATH
        return PORTFOLIO_PATH
    except ImportError:
        return ""


def _portfolio_url() -> str:
    # 기본값: 현재 repo 의 raw.githubusercontent URL.
    # 과거 기본값(kim-hyojun.github.io/stock-analysis) 은 404 — 프로젝트 이전 후 미수정.
    # env PORTFOLIO_URL 로 재정의 권장 (CDN 5분 캐시 회피하려면 jsdelivr 등 선택).
    return os.environ.get(
        "PORTFOLIO_URL",
        "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
    )


_url_cache: Dict[str, Any] = {"data": None, "ts": 0.0}
_URL_CACHE_TTL = 60.0  # 1분 — cache.py brain tier 과 동일


def _load_from_url() -> Dict[str, Any]:
    now = time.time()
    if _url_cache["data"] and now - _url_cache["ts"] < _URL_CACHE_TTL:
        return _url_cache["data"]
    try:
        import urllib.request
        req = urllib.request.Request(
            _portfolio_url(), headers={"User-Agent": "VERITY-Chat-Hybrid/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            txt = resp.read().decode("utf-8")
            txt = txt.replace("NaN", "null").replace("Infinity", "null").replace("-Infinity", "null")
            data = json.loads(txt)
            _url_cache["data"] = data
            _url_cache["ts"] = now
            return data
    except Exception as e:
        logger.warning("portfolio URL 로드 실패: %s", e)
        return {}


def _load_portfolio() -> Dict[str, Any]:
    """로컬 파일 우선 (서버/Railway), 없으면 URL 폴백 (Vercel serverless)."""
    path = _portfolio_path()
    if path:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
    return _load_from_url()


def _format_portfolio_summary(pf: Dict[str, Any]) -> List[str]:
    """시장 전반 요약 — 모든 질문에 공통 주입."""
    parts: List[str] = []
    updated = pf.get("updated_at", "?")
    parts.append(f"[데이터 갱신] {updated}")

    macro = pf.get("macro", {})
    mood = macro.get("market_mood", {})
    parts.append(
        f"[시장무드] {mood.get('score', '?')}점 ({mood.get('label', '—')})"
    )
    vix = (macro.get("vix") or {}).get("value")
    if vix is not None:
        parts.append(f"[VIX] {vix}")
    usd = (macro.get("usd_krw") or {}).get("value")
    if usd is not None:
        parts.append(f"[USD/KRW] {usd}")

    brain = pf.get("verity_brain", {}).get("market_brain", {})
    if brain.get("avg_brain_score") is not None:
        parts.append(f"[시장 평균 Brain] {brain['avg_brain_score']}점")

    return parts


def _format_ticker_block(s: Dict[str, Any]) -> str:
    """단일 종목 요약 블록."""
    name = s.get("name", "?")
    ticker = s.get("ticker", "?")
    rec = s.get("recommendation", "?")
    brain = s.get("verity_brain", {}).get("brain_score", s.get("brain_score", "?"))
    grade = s.get("verity_brain", {}).get("grade", "?")
    price = s.get("current_price") or s.get("price") or "?"
    multi = (s.get("multi_factor") or {}).get("multi_score", "?")
    timing = (s.get("timing") or {}).get("timing_score", "?")

    lines = [
        f"[{name} {ticker}]",
        f"  판정: {rec} · 등급: {grade} · Brain: {brain}",
        f"  현재가: {price} · 멀티팩터: {multi} · 타이밍: {timing}",
    ]
    # 리스크/postmortem memo
    rf = s.get("verity_brain", {}).get("red_flags", {})
    if rf.get("has_critical") or rf.get("auto_avoid"):
        flags = rf.get("auto_avoid", []) or rf.get("downgrade", [])
        if flags:
            lines.append(f"  ⚠ 리스크: {', '.join(str(x)[:50] for x in flags[:3])}")
    pm = s.get("postmortem_memo")
    if pm and pm.get("lesson"):
        lines.append(f"  📝 최근 오심 메모: {pm['lesson'][:80]}")

    # Analyst + DART (Phase 3/4 필드)
    ar = s.get("analyst_report_summary") or {}
    if ar.get("report_count", 0) > 0:
        sent = ar.get("analyst_sentiment_score", "?")
        cnt = ar.get("report_count", 0)
        lines.append(f"  📊 증권사 리포트: {cnt}건 · 센티먼트 {sent}")
    dh = (s.get("dart_business_analysis") or {}).get("business_health_score")
    if dh is not None:
        lines.append(f"  🏢 DART 건전성: {dh}/100")

    return "\n".join(lines)


def _find_stocks_by_ticker(pf: Dict[str, Any], tickers: List[str]) -> List[Dict]:
    if not tickers:
        return []
    recs = pf.get("recommendations", []) or []
    holdings = (pf.get("vams") or {}).get("holdings", []) or pf.get("holdings", []) or []
    targets = {t.upper() for t in tickers if t}
    matched = []
    seen = set()
    for s in recs + holdings:
        t = str(s.get("ticker", "")).upper()
        name = str(s.get("name", "")).upper()
        if not t or t in seen:
            continue
        if t in targets or name in targets:
            matched.append(s)
            seen.add(t)
    return matched


def _find_stocks_by_name(pf: Dict[str, Any], query: str) -> List[Dict]:
    """질문 텍스트에 종목명이 포함된 경우 매칭 (ticker 추출 실패 backup)."""
    recs = pf.get("recommendations", []) or []
    q_compact = query.replace(" ", "")
    matched = []
    seen = set()
    for s in recs:
        t = str(s.get("ticker", "")).upper()
        name = str(s.get("name", ""))
        if not t or t in seen or not name:
            continue
        if name in query or name.replace(" ", "") in q_compact:
            matched.append(s)
            seen.add(t)
            if len(matched) >= 5:
                break
    return matched


def fetch_brain_context(
    query: str,
    intent: Optional[Dict[str, Any]] = None,
    session_id: str = "anonymous",
) -> Dict[str, Any]:
    """Brain 컨텍스트 구성 (포트폴리오 요약 + 관련 종목 상세).

    Returns: {
        "ok": True,
        "text": str (Claude system prompt 에 주입),
        "citations": [],
        "matched_tickers": [str],
        "latency_ms": int,
    }
    """
    t0 = time.time()
    intent = intent or {}
    related_tickers = intent.get("related_tickers") or []

    # 캐시: 포트폴리오 요약은 1분 TTL (session 무관)
    cached = cache.get("brain", "portfolio_summary_v1")
    if cached is None:
        pf = _load_portfolio()
        cached = _format_portfolio_summary(pf)
        cache.set_value("brain", "portfolio_summary_v1", cached)
    else:
        pf = None  # 지역 변수 — 아래에서 필요 시 재로드

    parts: List[str] = list(cached)
    matched_tickers: List[str] = []

    # 관련 종목 주입
    if related_tickers or True:  # name 기반 fallback 위해 항상 시도
        if pf is None:
            pf = _load_portfolio()

        stocks = _find_stocks_by_ticker(pf, related_tickers)
        if not stocks:
            stocks = _find_stocks_by_name(pf, query)

        if stocks:
            parts.append("\n[관련 종목]")
            for s in stocks[:5]:
                parts.append(_format_ticker_block(s))
                matched_tickers.append(str(s.get("ticker", "")))

    # 알림 (portfolio_only 질문 특히 유용)
    if pf is None:
        pf = _load_portfolio()
    alerts = pf.get("alerts", [])
    if alerts and intent.get("intent_type") in ("portfolio_only", "hybrid"):
        parts.append("\n[최근 알림]")
        for a in alerts[:5]:
            msg = a.get("text") or a.get("message") or "?"
            parts.append(f"  • {str(msg)[:120]}")

    text = "\n".join(parts) if parts else "포트폴리오 데이터 없음."

    return {
        "ok": True,
        "text": text,
        "citations": [],
        "matched_tickers": matched_tickers,
        "latency_ms": int((time.time() - t0) * 1000),
    }
