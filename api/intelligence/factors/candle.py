"""Candle psychology score — Nison Rule of Multiple Techniques.

원본: api/intelligence/verity_brain.py:417-482 (분해 전).
"""
from __future__ import annotations

from typing import Any, Dict

from api.intelligence.factors._common import _safe_float


def _compute_candle_psychology_score(stock: Dict[str, Any]) -> float:
    """Nison Rule of Multiple Techniques: 캔들 패턴 + 확인 조건 → 보너스 점수.
    timing 팩터 보정에 사용. -10 ~ +10 범위의 보너스를 반환."""
    tech = stock.get("technical") or {}
    signals = tech.get("signals") or []
    vol_ratio = _safe_float(tech.get("vol_ratio"), 1.0)

    candle_base = 0
    bullish_count = 0
    bearish_count = 0

    bullish_patterns = [
        "망치", "hammer", "관통", "piercing", "아침별", "morning_star",
        "삼병정", "three_white", "상승장악", "bullish_engulf",
        "모닝", "상승잉태", "역전된망치", "inverted_hammer"
    ]
    bearish_patterns = [
        "교수형", "hanging", "흑운", "dark_cloud", "저녁별", "evening_star",
        "까마귀", "three_black", "하락장악", "bearish_engulf",
        "유성", "shooting_star", "하락잉태", "이브닝"
    ]

    for sig in signals:
        sig_lower = sig.lower() if isinstance(sig, str) else ""
        for bp in bullish_patterns:
            if bp in sig_lower:
                bullish_count += 1
                break
        for bp in bearish_patterns:
            if bp in sig_lower:
                bearish_count += 1
                break

    if bullish_count > bearish_count:
        candle_base = min(bullish_count * 1.5, 4)
    elif bearish_count > bullish_count:
        candle_base = max(bearish_count * -1.5, -4)

    if candle_base == 0:
        return 0.0

    # Nison 확인 조건: 거래량 동반 확인
    volume_bonus = 0
    if abs(candle_base) > 0 and vol_ratio > 1.5:
        volume_bonus = 1.5 if candle_base > 0 else -1.5

    # RSI 방향 일치 확인
    rsi = _safe_float(tech.get("rsi"))
    rsi_bonus = 0
    if rsi is not None:
        if candle_base > 0 and rsi < 40:
            rsi_bonus = 1.5
        elif candle_base < 0 and rsi > 60:
            rsi_bonus = -1.5

    # MACD 방향 일치 확인
    macd_hist = _safe_float(tech.get("macd_hist"))
    macd_bonus = 0
    if macd_hist is not None:
        if candle_base > 0 and macd_hist > 0:
            macd_bonus = 1.0
        elif candle_base < 0 and macd_hist < 0:
            macd_bonus = -1.0

    total = candle_base + volume_bonus + rsi_bonus + macd_bonus
    return max(-10.0, min(10.0, round(total, 1)))
