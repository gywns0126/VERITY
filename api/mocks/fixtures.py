"""
하드코딩 mock fixture — trace가 없을 때 사용되는 최소 구조 fallback.
각 키의 반환값은 실제 함수 반환 스키마와 동일.
"""
from __future__ import annotations

FIXTURES: dict = {
    # ── Gemini ──────────────────────────────────────────────
    "gemini.stock_analysis": {
        "company_tagline": "[MOCK] 분석 스킵",
        "ai_verdict": "[MOCK] dev 모드 — 실제 AI 호출 안 함",
        "recommendation": "WATCH",
        "risk_flags": [],
        "confidence": 0,
        "gold_insight": "[MOCK]",
        "silver_insight": "[MOCK]",
        "detected_risk_keywords": [],
        "model_used": "mock",
    },
    "gemini.daily_report": {
        "market_summary": "[MOCK] dev 모드 — 리포트 미생성",
        "market_analysis": "[MOCK]",
        "strategy": "[MOCK]",
        "risk_watch": "[MOCK]",
        "hot_theme": "[MOCK]",
        "tomorrow_outlook": "[MOCK]",
        "model_used": "mock",
    },
    "gemini.periodic_report": {
        "title": "[MOCK] 정기 리포트",
        "executive_summary": "[MOCK]",
        "performance_review": "[MOCK]",
        "sector_analysis": "[MOCK]",
        "macro_outlook": "[MOCK]",
        "brain_review": "[MOCK]",
        "meta_insight": "[MOCK]",
        "strategy": "[MOCK]",
        "risk_watch": "[MOCK]",
        "_period": "unknown",
        "_period_label": "mock",
        "_raw_stats": {},
        "model_used": "mock",
    },
    "gemini.batch_analysis": [],
    "gemini.reanalyze_pro": {},

    # ── Claude ──────────────────────────────────────────────
    "claude.deep": {
        "claude_verdict": "[MOCK] dev 모드 — Claude 미호출",
        "agrees_with_gemini": True,
        "override_recommendation": None,
        "confidence_adjustment": 0,
        "hidden_risks": [],
        "hidden_opportunities": [],
        "vci_analysis": "[MOCK]",
        "conviction_note": "[MOCK]",
        "_error": "mock",
    },
    "claude.batch_deep": {},
    "claude.light": {
        "quick_verdict": "[MOCK]",
        "alert_change": False,
        "new_recommendation": None,
        "confidence_delta": 0,
        "watch_note": "[MOCK]",
    },
    "claude.batch_light": {},
    "claude.emergency": {
        "cause_guess": "[MOCK]",
        "action": "[MOCK]",
        "hold_or_exit": "HOLD",
        "urgency_1_5": 1,
        "reasoning": "[MOCK]",
    },
    "claude.verify_tail_risk": {
        "severity_1_10": 1,
        "category": "irrelevant",
        "agrees_with_gemini": True,
        "summary_ko": "[MOCK] dev 모드",
        "reasoning": "[MOCK]",
    },
    "claude.morning_strategy": {
        "scenario": "[MOCK]",
        "watch_points": [],
        "risk_note": "[MOCK]",
        "top_pick_comment": "[MOCK]",
    },
    "claude.brain_drift": {
        "drift_cause": "[MOCK]",
        "significance": "low",
        "action_hint": "[MOCK]",
        "alert_worthy": False,
    },

    # ── Claude (intelligence) ──────────────────────────────
    "claude.postmortem": {
        "status": "clean",
        "message": "[MOCK] dev 모드 — 포스트모텀 미실행",
        "failures": [],
        "generated_at": "",
    },
    "claude.strategy_evolution": {
        "status": "skipped",
        "reason": "[MOCK] dev 모드",
    },

    # ── Perplexity ─────────────────────────────────────────
    "perplexity.sonar": {
        "content": "[MOCK] dev 모드 — Perplexity 미호출",
        "citations": [],
        "model": "mock",
        "usage": {},
    },
    "perplexity.macro_event": {
        "event": "[MOCK]",
        "impact_summary": "[MOCK]",
        "severity": "LOW",
        "kr_impact": "",
        "us_impact": "",
        "citations": [],
    },
    "perplexity.earnings": {
        "ticker": "MOCK",
        "earnings_summary": "[MOCK]",
        "beat_miss": "UNKNOWN",
        "guidance": "",
        "citations": [],
    },
    "perplexity.stock_risk": {
        "ticker": "MOCK",
        "external_risks": "[MOCK]",
        "risk_level": "LOW",
        "issues": [],
        "citations": [],
    },
    "perplexity.quarterly_research": {
        "status": "mock",
        "quarter": "MOCK",
        "summary": "[MOCK]",
        "citations_count": 0,
        "token_cost_usd": 0,
    },

    # ── Gemini (parsers) ───────────────────────────────────
    "gemini.facilities_parse": {"error": "mock_mode"},
    "gemini.properties_parse": {"error": "mock_mode"},
    "gemini.hscode_mapper": {},
    "gemini.commodity_narrator": {},
    "gemini.commodity_sector_map": {},

    # ── Gemini (chat) ──────────────────────────────────────
    "gemini.chat": "[MOCK] dev 모드 — AI 비서 응답 대체",

    # ── Gemini (tail risk) ─────────────────────────────────
    "gemini.tail_risk": None,

    # ── Finnhub ────────────────────────────────────────────
    "finnhub.analyst_consensus": {
        "buy": 0, "hold": 0, "sell": 0, "strongBuy": 0, "strongSell": 0,
        "target_high": 0, "target_low": 0, "target_mean": 0, "target_median": 0,
        "upside_pct": 0,
    },
    "finnhub.earnings_surprises": [],
    "finnhub.insider_sentiment": {
        "mspr": 0, "net_shares": 0, "positive_count": 0, "negative_count": 0,
    },
    "finnhub.institutional_ownership": {"total_holders": 0, "change_pct": 0},
    "finnhub.peer_companies": [],
    "finnhub.basic_financials": {},
    "finnhub.company_news": [],

    # ── Polygon ────────────────────────────────────────────
    "polygon.options_flow": {},
    "polygon.short_interest": {},
    "polygon.pre_after_market": {},

    # ── NewsAPI ────────────────────────────────────────────
    "newsapi.us_stock_news": [],
    "newsapi.market_news": [],
}
