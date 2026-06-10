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

    # ── Nison 원전 검증 (2026-06-07, action_queue a76f7dd5) ──
    # 구조 = Nison "Rule of Multiple Techniques"(캔들 + 타 기법 confluence 확인) — 충실.
    # 단, 아래 수치 임계(vol_ratio>1.5 / RSI 40·60 / 가중치 1.5·1.0·cap 4)는 Nison 의
    # *정성* 서술(거래량 support / oversold-overbought confluence)을 자체 수치화한 것 =
    # 원전에 숫자 없음 → 가설(self-op), N 누적 후 검증 대상. RULE 7.
    # 패턴 *기하*(망치 몸통:꼬리 비율 등)는 본 파일 아닌 upstream 에서 탐지.
    # 🚨 DISCONNECT (2026-06-10 발견): 본 함수는 tech.signals 에서 캔들 패턴명을 찾으나
    #    tech.signals producer 는 MA/RSI/MACD/추세뿐 — 캔들 패턴 0건. 진짜 Nison-기하 패턴은
    #    technical.talib_observations.candle_patterns(TA-Lib CDL*, 레퍼런스 구현)에 따로 있고
    #    미연결 → candle_bonus 사실상 항상 0(죽은 결정 경로). 브레인은 캔들 점수 없이 운영된 baseline.
    #    재연결(=죽은 결정입력 활성)은 RULE 7 사전등록 후 N 게이트 통과 + PM 승인:
    #    docs/PREREG_CANDLE_GEOMETRY_ACTIVATION_2026_06_10.md. 그 전까지 현 동작(0) 유지.
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
