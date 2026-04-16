"""
Perplexity 실시간 웹 리서치 — 매크로 이벤트·실적·종목 리스크

quarterly_research.py가 분기 1회 딥리서치라면, 이 모듈은
파이프라인 실행 중 즉각 호출되는 실시간 리서치를 담당한다.

활용처:
  1) 매크로 이벤트 해석 — FOMC/CPI 등 고영향 이벤트 발생 시
  2) 실적 발표 직후 요약 — 어닝콜 핵심 + 시장 반응
  3) 종목 외부 리스크 탐지 — 소송/규제/스캔들 비정형 위험
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from api.clients.perplexity_client import call_perplexity
from api.config import PERPLEXITY_API_KEY, DATA_DIR, now_kst

_CONSTITUTION_PATH = Path(DATA_DIR) / "verity_constitution.json"

# ─── 시스템 프롬프트 (constitution 기반 동적 생성) ───────────────


def _load_constitution_block() -> Dict[str, Any]:
    """verity_constitution.json에서 Perplexity용 프롬프트 조각 로드."""
    try:
        with open(_CONSTITUTION_PATH, "r", encoding="utf-8") as f:
            const = json.load(f)
        si = const.get("gemini_system_instruction", {})
        return {
            "tone": si.get("tone", ""),
            "principles": si.get("principles", []),
            "analysis_protocol": si.get("analysis_protocol", []),
            "forecast_horizons": si.get("forecast_horizons", []),
        }
    except Exception:
        return {"tone": "", "principles": [], "analysis_protocol": [], "forecast_horizons": []}


def _build_principles_block() -> str:
    """톤+원칙만 압축 (매크로/실적용 — 가벼운 주입)."""
    cb = _load_constitution_block()
    lines = []
    if cb["tone"]:
        lines.append(f"[Tone] {cb['tone']}")
    if cb["principles"]:
        lines.append("[Core Principles]")
        lines.extend(f"- {p}" for p in cb["principles"])
    return "\n".join(lines)


def _build_full_protocol_block() -> str:
    """톤+원칙+분석 프로토콜+전망 시간대 전체 (종목 분석용)."""
    cb = _load_constitution_block()
    lines = []
    if cb["tone"]:
        lines.append(f"[Tone] {cb['tone']}")
    if cb["principles"]:
        lines.append("[Core Principles]")
        lines.extend(f"- {p}" for p in cb["principles"])
    if cb["analysis_protocol"]:
        lines.append("[Analysis Protocol — cover as many items as data allows]")
        lines.extend(f"- {a}" for a in cb["analysis_protocol"])
    if cb["forecast_horizons"]:
        lines.append("[Required Forecast Horizons]")
        lines.extend(f"- {h}" for h in cb["forecast_horizons"])
    return "\n".join(lines)


_BASE_MACRO_SYSTEM = (
    "You are a senior macro strategist at a top asset manager. "
    "Provide concise, data-driven analysis with specific numbers and sources. "
    "Focus on actionable implications for equity portfolios in Korea and the US. "
    "Answer in English. Keep it under 400 words."
)

_BASE_EARNINGS_SYSTEM = (
    "You are a sell-side equity research analyst. "
    "Summarize earnings results concisely with hard numbers. "
    "Focus on beat/miss, guidance changes, and market reaction. "
    "Answer in English. Keep it under 300 words."
)

_BASE_RISK_SYSTEM = (
    "You are a compliance and risk analyst at a hedge fund. "
    "Report only confirmed, sourced facts — no speculation. "
    "If no material risks exist, clearly state that. "
    "Answer in English. Keep it under 300 words."
)


def _get_macro_system() -> str:
    return f"{_BASE_MACRO_SYSTEM}\n\n{_build_principles_block()}"


def _get_earnings_system() -> str:
    return f"{_BASE_EARNINGS_SYSTEM}\n\n{_build_principles_block()}"


def _get_risk_system() -> str:
    return f"{_BASE_RISK_SYSTEM}\n\n{_build_full_protocol_block()}"


# ═══════════════════════════════════════════════════════════════
# 1) 매크로 이벤트 실시간 해석
# ═══════════════════════════════════════════════════════════════

def research_macro_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """단일 매크로 이벤트에 대한 Perplexity 실시간 리서치.

    Args:
        event: global_events 배열의 원소
               (name, date, severity, impact_area, ...)

    Returns:
        {"event": str, "impact_summary": str, "severity": str,
         "kr_impact": str, "us_impact": str, "citations": list}
        실패 시 {"event": str, "error": str}
    """
    name = event.get("name", "Unknown Event")
    date = event.get("date", "unknown")

    query = (
        f'"{name}" just occurred or is imminent ({date}).\n'
        "What is the expected impact on:\n"
        "1. US equity market (S&P 500, Nasdaq) — direction and magnitude\n"
        "2. Korea equity market (KOSPI, KOSDAQ) — direction and magnitude\n"
        "3. USD/KRW exchange rate\n"
        "4. Bond yields (US 10Y, Korea 10Y)\n\n"
        "Rate overall market impact severity as one of: CRITICAL / HIGH / MODERATE / LOW.\n"
        "Start your answer with the severity rating on its own line.\n"
        "Cite specific analyst or institution views from the last 48 hours."
    )

    result = call_perplexity(query, system_prompt=_get_macro_system(), max_tokens=1500)
    if "error" in result:
        return {"event": name, "error": result["error"]}

    content = result.get("content", "")
    severity = _extract_severity(content)
    kr_impact, us_impact = _split_market_impacts(content)

    return {
        "event": name,
        "date": date,
        "impact_summary": content,
        "severity": severity,
        "kr_impact": kr_impact,
        "us_impact": us_impact,
        "citations": result.get("citations", []),
    }


def research_macro_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """임박 고영향 이벤트 목록을 일괄 리서치."""
    if not PERPLEXITY_API_KEY:
        return []
    results = []
    for ev in events[:3]:
        print(f"  [Perplexity] 매크로 이벤트 리서치: {ev.get('name', '?')}")
        results.append(research_macro_event(ev))
    return results


# ═══════════════════════════════════════════════════════════════
# 2) 실적 발표 직후 요약
# ═══════════════════════════════════════════════════════════════

def research_earnings(stock: Dict[str, Any]) -> Dict[str, Any]:
    """실적 발표 직후 종목 어닝 리서치.

    Args:
        stock: 후보 종목 dict (name, ticker, ticker_yf, earnings, ...)

    Returns:
        {"ticker": str, "earnings_summary": str, "beat_miss": str,
         "guidance": str, "citations": list}
    """
    name = stock.get("name", stock.get("ticker", "?"))
    ticker = stock.get("ticker_yf") or stock.get("ticker", "?")
    now = now_kst()
    quarter = f"{now.year}Q{(now.month - 1) // 3 + 1}"

    query = (
        f'"{name}" ({ticker}) earnings report for {quarter}.\n'
        "Summarize in 200 words:\n"
        "1. Revenue & EPS vs consensus (beat / miss / inline) — cite numbers\n"
        "2. Key guidance changes for next quarter\n"
        "3. Management commentary highlights\n"
        "4. After-hours / next-day stock price reaction\n"
        "5. Analyst upgrades or downgrades within 24 hours\n\n"
        "Start your answer with one word: BEAT, MISS, or INLINE."
    )

    result = call_perplexity(query, system_prompt=_get_earnings_system(), max_tokens=1200)
    if "error" in result:
        return {"ticker": ticker, "error": result["error"]}

    content = result.get("content", "")
    beat_miss = _extract_beat_miss(content)
    guidance = _extract_section(content, "guidance")

    return {
        "ticker": ticker,
        "earnings_summary": content,
        "beat_miss": beat_miss,
        "guidance": guidance,
        "citations": result.get("citations", []),
    }


def is_earnings_imminent(stock: Dict[str, Any]) -> bool:
    """실적 발표일이 D-0 ~ D+1 범위인지 판별."""
    ed = stock.get("earnings", {}).get("next_earnings")
    if not ed:
        return False
    try:
        earn_date = datetime.strptime(str(ed)[:10], "%Y-%m-%d")
        now = datetime.now()
        delta = (earn_date - now).days
        return -1 <= delta <= 1
    except (ValueError, TypeError):
        return False


# ═══════════════════════════════════════════════════════════════
# 3) 종목 외부 리스크 탐지
# ═══════════════════════════════════════════════════════════════

def research_stock_risk(stock: Dict[str, Any]) -> Dict[str, Any]:
    """종목의 비정형 외부 리스크 웹 스캔.

    Args:
        stock: 후보 종목 dict (name, ticker, ...)

    Returns:
        {"ticker": str, "external_risks": str, "risk_level": str,
         "issues": list[str], "citations": list}
    """
    name = stock.get("name", stock.get("ticker", "?"))
    ticker = stock.get("ticker_yf") or stock.get("ticker", "?")

    query = (
        f'"{name}" ({ticker}) — scan for non-financial risks in the last 30 days:\n'
        "1. Pending lawsuits or regulatory actions\n"
        "2. Executive changes or corporate governance issues\n"
        "3. Product recalls, safety incidents\n"
        "4. Sanctions, trade restrictions, export controls\n"
        "5. ESG controversies or activist campaigns\n\n"
        "Rate overall external risk: HIGH / MODERATE / LOW.\n"
        "Start your answer with the risk rating on its own line.\n"
        'Only report confirmed facts with sources. If nothing significant found, say "No material external risks found."'
    )

    result = call_perplexity(query, system_prompt=_get_risk_system(), max_tokens=1200)
    if "error" in result:
        return {"ticker": ticker, "error": result["error"]}

    content = result.get("content", "")
    risk_level = _extract_risk_level(content)
    issues = _extract_issues(content)

    return {
        "ticker": ticker,
        "external_risks": content,
        "risk_level": risk_level,
        "issues": issues,
        "citations": result.get("citations", []),
    }


# ═══════════════════════════════════════════════════════════════
# 내부 헬퍼
# ═══════════════════════════════════════════════════════════════

def _extract_severity(text: str) -> str:
    """응답 텍스트에서 CRITICAL/HIGH/MODERATE/LOW 추출."""
    upper = text.upper()[:200]
    for level in ("CRITICAL", "HIGH", "MODERATE", "LOW"):
        if level in upper:
            return level
    return "MODERATE"


def _extract_beat_miss(text: str) -> str:
    """응답 첫 줄에서 BEAT/MISS/INLINE 추출."""
    first_line = text.strip().split("\n")[0].upper()
    for tag in ("BEAT", "MISS", "INLINE"):
        if tag in first_line:
            return tag
    return "UNKNOWN"


def _extract_risk_level(text: str) -> str:
    """응답에서 HIGH/MODERATE/LOW 리스크 등급 추출."""
    upper = text.upper()[:200]
    for level in ("HIGH", "MODERATE", "LOW"):
        if level in upper:
            return level
    return "LOW"


def _extract_section(text: str, keyword: str) -> str:
    """텍스트에서 특정 키워드가 포함된 문장 추출."""
    for line in text.split("\n"):
        if keyword.lower() in line.lower():
            return line.strip()
    return ""


def _extract_issues(text: str) -> List[str]:
    """번호 매긴 이슈 항목들을 리스트로 추출."""
    issues = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and stripped[0].isdigit() and "." in stripped[:3]:
            issues.append(stripped)
    if not issues and "no material" in text.lower():
        return []
    return issues


def _split_market_impacts(text: str) -> tuple:
    """응답에서 KR/US 영향 요약을 분리 추출."""
    kr_impact = ""
    us_impact = ""
    for line in text.split("\n"):
        lower = line.lower()
        if "korea" in lower or "kospi" in lower or "kosdaq" in lower:
            kr_impact = line.strip()
        elif "us " in lower or "s&p" in lower or "nasdaq" in lower:
            if not us_impact:
                us_impact = line.strip()
    return kr_impact, us_impact
