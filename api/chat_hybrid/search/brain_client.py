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
    # 기본값: VERITY-data repo (옵션 B, 2026-05-17 박힘).
    # env PORTFOLIO_URL 로 재정의 권장 (CDN 5분 캐시 회피하려면 jsdelivr 등 선택).
    return os.environ.get(
        "PORTFOLIO_URL",
        "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/portfolio.json",
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


# ── price_pulse: 5분-fresh KIS 시세 overlay (2026-06-03) ──
# portfolio.json 가격은 분석 cron(~하루 1회) 기준 → 챗이 옛 가격을 인용.
# price_pulse.json 의 KIS 5분-fresh 가격을 유니버스 종목에 덧씌운다.
# ※ 이미 수집된 파일 read 일 뿐 KIS 직접 호출 아님 → RULE 1 무관. 실패 시 fail-open.
def _price_pulse_url() -> str:
    return os.environ.get(
        "PRICE_PULSE_URL",
        "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/price_pulse.json",
    )


_pulse_cache: Dict[str, Any] = {"data": None, "ts": 0.0}


def _load_price_pulse() -> Dict[str, Any]:
    """price_pulse.json 로드 (로컬 우선, URL 폴백). 실패 시 {}."""
    now = time.time()
    if _pulse_cache["data"] is not None and now - _pulse_cache["ts"] < _URL_CACHE_TTL:
        return _pulse_cache["data"]

    data: Dict[str, Any] = {}
    pp = _portfolio_path()
    local = os.path.join(os.path.dirname(pp), "price_pulse.json") if pp else ""
    if local and os.path.isfile(local):
        try:
            with open(local, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}
    if not data:
        try:
            import urllib.request
            req = urllib.request.Request(
                _price_pulse_url(), headers={"User-Agent": "VERITY-Chat-Hybrid/1.0"}
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
                txt = resp.read().decode("utf-8")
                txt = txt.replace("NaN", "null").replace("Infinity", "null").replace("-Infinity", "null")
                data = json.loads(txt)
        except Exception as e:
            logger.warning("price_pulse 로드 실패: %s", e)
            data = {}

    _pulse_cache["data"] = data
    _pulse_cache["ts"] = now
    return data


def _pulse_price_map(pulse: Dict[str, Any]) -> Dict[str, float]:
    """price_pulse → {TICKER(upper): price(float)} 맵."""
    p = pulse.get("prices") if isinstance(pulse, dict) else None
    if not isinstance(p, dict):
        return {}
    out: Dict[str, float] = {}
    for k, v in p.items():
        try:
            out[str(k).strip().upper()] = float(v)
        except (TypeError, ValueError):
            continue
    return out


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


def _format_ticker_block(s: Dict[str, Any], fresh_prices: Optional[Dict[str, float]] = None) -> str:
    """단일 종목 요약 블록. fresh_prices(price_pulse) 있으면 KIS 5분-fresh 가격 우선."""
    name = s.get("name", "?")
    ticker = s.get("ticker", "?")
    rec = s.get("recommendation", "?")
    brain = s.get("verity_brain", {}).get("brain_score", s.get("brain_score", "?"))
    grade = s.get("verity_brain", {}).get("grade", "?")
    price = s.get("current_price") or s.get("price") or "?"
    price_src = ""
    if fresh_prices:
        fp = fresh_prices.get(str(ticker).strip().upper())
        if fp:
            price = f"{int(fp):,}" if float(fp).is_integer() else fp
            price_src = " (KIS 실시간)"
    multi = (s.get("multi_factor") or {}).get("multi_score", "?")
    timing = (s.get("timing") or {}).get("timing_score", "?")

    lines = [
        f"[{name} {ticker}]",
        f"  판정: {rec} · 등급: {grade} · Brain: {brain}",
        f"  현재가: {price}{price_src} · 멀티팩터: {multi} · 타이밍: {timing}",
    ]

    # 등급 근거 — fact/심리/VCI 분해 (왜 이 등급인지, 답 깊이의 핵심)
    vb = s.get("verity_brain", {}) or {}
    _fs = vb.get("fact_score")
    _ss = vb.get("sentiment_score")
    fact = _fs.get("score") if isinstance(_fs, dict) else _fs
    senti = _ss.get("score") if isinstance(_ss, dict) else _ss
    vci_d = vb.get("vci") if isinstance(vb.get("vci"), dict) else {}
    conf = vb.get("grade_confidence")
    basis: List[str] = []
    if fact is not None:
        basis.append(f"fact {fact}")
    if senti is not None:
        basis.append(f"심리 {senti}")
    if vci_d.get("vci") is not None:
        basis.append(f"VCI {vci_d.get('vci')}({vci_d.get('signal', '')})")
    if conf:
        basis.append(f"확신 {conf}")
    if basis:
        lines.append("  등급 근거: " + " · ".join(basis))
        if vci_d.get("label"):
            lines.append(f"    └ {vci_d['label']}")

    # 팩터 기여 — 무엇이 등급을 끌어올렸나/눌렀나
    fc = (s.get("multi_factor") or {}).get("factor_contribution")
    if isinstance(fc, dict):
        nums = [(k, v) for k, v in fc.items() if isinstance(v, (int, float))]
        if nums:
            nums.sort(key=lambda kv: kv[1], reverse=True)
            top = " · ".join(f"↑{k} {v:.1f}" for k, v in nums[:3])
            low_k, low_v = nums[-1]
            lines.append(f"  팩터 기여: {top} / ↓{low_k} {low_v:.1f}")

    # 타이밍 판정 이유
    reasons = (s.get("timing") or {}).get("reasons")
    if isinstance(reasons, list) and reasons:
        lines.append("  타이밍 이유: " + "; ".join(str(r)[:50] for r in reasons[:2]))

    # Lynch 분류 (한국형)
    lynch = s.get("lynch_kr")
    if isinstance(lynch, dict) and lynch.get("label"):
        summ = lynch.get("summary", "")
        lines.append(f"  Lynch: {lynch['label']}" + (f" — {summ}" if summ else ""))

    # 심리 근거 헤드라인 (있을 때만)
    heads = (s.get("sentiment") or {}).get("top_headlines")
    if isinstance(heads, list) and heads:
        lines.append("  심리 근거: " + "; ".join(str(h)[:60] for h in heads[:2]))

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


def _format_user_watchlist(
    user_watchlist: Optional[List[Dict[str, Any]]],
    pf: Optional[Dict[str, Any]],
    fresh_prices: Optional[Dict[str, float]] = None,
) -> List[str]:
    """사용자 개인 관심종목(localStorage 기반) 컨텍스트 블록.

    - 항상 전체 ticker 리스트를 노출 (챗이 "관심종목 알려줘" 류 질문 답할 수 있게)
    - portfolio.json 에 있는 종목은 _format_ticker_block 으로 풍부 데이터 첨부
    - 무한 컨텍스트 방지: ticker 최대 50개, 풍부 블록 최대 5개
    """
    if not user_watchlist:
        return []

    # 입력 정규화: { ticker, name, market } 만 추출, 최대 50개
    cleaned: List[Dict[str, str]] = []
    seen = set()
    for it in user_watchlist[:50]:
        if not isinstance(it, dict):
            continue
        t = str(it.get("ticker") or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        cleaned.append({
            "ticker": t,
            "name": str(it.get("name") or "").strip() or t,
            "market": str(it.get("market") or "").strip(),
        })
    if not cleaned:
        return []

    parts = ["\n[사용자 관심종목]"]
    summary = ", ".join(f"{c['name']}({c['ticker']})" for c in cleaned[:50])
    parts.append(f"  사용자가 추적 중인 종목 {len(cleaned)}개: {summary}")

    # portfolio.json 에 있는 종목 — 풍부 블록 (최대 5개)
    if pf is not None:
        tickers = [c["ticker"] for c in cleaned]
        rich = _find_stocks_by_ticker(pf, tickers)
        if rich:
            parts.append("\n[관심종목 상세 — Brain 데이터 매칭분]")
            for s in rich[:5]:
                parts.append(_format_ticker_block(s, fresh_prices))
    return parts


def fetch_brain_context(
    query: str,
    intent: Optional[Dict[str, Any]] = None,
    session_id: str = "anonymous",
    user_watchlist: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Brain 컨텍스트 구성 (포트폴리오 요약 + 관련 종목 상세 + 사용자 관심종목).

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

    # price_pulse — 5분-fresh KIS 시세 overlay (자체 60s 캐시). 실패 시 빈 맵 = 무영향.
    pulse = _load_price_pulse()
    fresh_prices = _pulse_price_map(pulse)
    pulse_ts = pulse.get("updated_at") if isinstance(pulse, dict) else None
    if fresh_prices and pulse_ts:
        parts.append(f"[실시간 시세 갱신] {pulse_ts} (KIS, 유니버스 {len(fresh_prices)}종목)")

    # 사용자 개인 관심종목 — portfolio.json 캐시 hit 시에도 풍부 데이터 위해 재로드
    if user_watchlist:
        if pf is None:
            pf = _load_portfolio()
        watchlist_parts = _format_user_watchlist(user_watchlist, pf, fresh_prices)
        if watchlist_parts:
            parts.extend(watchlist_parts)
            for it in user_watchlist[:50]:
                if isinstance(it, dict) and it.get("ticker"):
                    matched_tickers.append(str(it["ticker"]))

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
                parts.append(_format_ticker_block(s, fresh_prices))
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
