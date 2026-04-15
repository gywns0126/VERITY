"""
CNN Fear & Greed Index — 주식시장 심리 종합 지수 (0~100)

7개 하위 지표:
  1. S&P 500 모멘텀 (vs 125일 이동평균)
  2. 신고가/신저가 비율
  3. 주가 강도 (McClellan Volume Summation)
  4. 풋/콜 옵션 비율
  5. 정크본드 스프레드
  6. 시장 변동성 (VIX)
  7. 안전자산 수요 (주식 vs 채권 수익률)

공식 API 없음. 비공식 CNN 엔드포인트 + fear_and_greed 패키지 이중 구조.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

import requests

from api.config import MARKET_FNG_EXTREME_GREED, MARKET_FNG_EXTREME_FEAR

logger = logging.getLogger(__name__)

_TIMEOUT = 10
_HEADERS = {"User-Agent": "Verity-Terminal/1.0"}

_CNN_API = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"

_LABEL_MAP = {
    "extreme fear": "극도공포",
    "fear": "공포",
    "neutral": "중립",
    "greed": "탐욕",
    "extreme greed": "극도탐욕",
}


def collect_market_fear_greed() -> Dict[str, Any]:
    """CNN Fear & Greed Index 수집. 패키지 → CNN API 순 폴백."""
    result = _try_package()
    if result.get("ok"):
        return result

    result = _try_cnn_api()
    if result.get("ok"):
        return result

    return {"ok": False, "error": "all methods failed", "value": None}


def _classify(value: int) -> str:
    if value <= 24:
        return "extreme_fear"
    if value <= 44:
        return "fear"
    if value <= 55:
        return "neutral"
    if value <= 75:
        return "greed"
    return "extreme_greed"


def _signal(value: int) -> str:
    if value >= MARKET_FNG_EXTREME_GREED:
        return "extreme_greed"
    if value >= 60:
        return "greed"
    if value <= MARKET_FNG_EXTREME_FEAR:
        return "extreme_fear"
    if value <= 40:
        return "fear"
    return "neutral"


def _build_result(
    value: int,
    description: str,
    previous_close: float = None,
    one_week_ago: float = None,
    one_month_ago: float = None,
    one_year_ago: float = None,
    sub_indicators: Dict[str, Any] = None,
    source: str = "",
) -> Dict[str, Any]:
    change_1d = round(value - previous_close, 1) if previous_close is not None else None
    change_1w = round(value - one_week_ago, 1) if one_week_ago is not None else None

    return {
        "ok": True,
        "value": value,
        "description": description,
        "description_kr": _LABEL_MAP.get(description.lower(), description),
        "classification": _classify(value),
        "signal": _signal(value),
        "previous_close": previous_close,
        "one_week_ago": one_week_ago,
        "one_month_ago": one_month_ago,
        "one_year_ago": one_year_ago,
        "change_1d": change_1d,
        "change_1w": change_1w,
        "sub_indicators": sub_indicators or {},
        "source": source,
    }


def _try_package() -> Dict[str, Any]:
    """fear_and_greed 패키지로 수집 시도."""
    try:
        import fear_and_greed
        data = fear_and_greed.get()
        value = int(data.value)
        desc = str(data.description).lower().strip()

        return _build_result(
            value=value,
            description=desc,
            previous_close=getattr(data, "previous_close", None),
            one_week_ago=getattr(data, "one_week_ago", None),
            one_month_ago=getattr(data, "one_month_ago", None),
            one_year_ago=getattr(data, "one_year_ago", None),
            source="fear_and_greed_package",
        )
    except ImportError:
        logger.debug("fear_and_greed 패키지 미설치, CNN API 폴백")
        return {"ok": False}
    except Exception as e:
        logger.warning("fear_and_greed 패키지 오류: %s", e)
        return {"ok": False}


def _try_cnn_api() -> Dict[str, Any]:
    """CNN 비공식 API 직접 호출."""
    try:
        r = requests.get(_CNN_API, headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        data = r.json()

        fg = data.get("fear_and_greed") or {}
        score = fg.get("score")
        if score is None:
            return {"ok": False, "error": "no score in response"}

        value = int(round(float(score)))
        rating = (fg.get("rating") or "").lower().strip()

        prev = fg.get("previous_close", None)
        w1 = fg.get("previous_1_week", None)
        m1 = fg.get("previous_1_month", None)
        y1 = fg.get("previous_1_year", None)

        sub = {}
        for key in (
            "stock_price_strength",
            "stock_price_breadth",
            "stock_price_momentum",
            "put_call_options",
            "market_volatility_vix",
            "junk_bond_demand",
            "safe_haven_demand",
        ):
            indicator = data.get(key)
            if indicator and isinstance(indicator, dict):
                sub[key] = {
                    "score": indicator.get("score"),
                    "rating": indicator.get("rating"),
                }

        return _build_result(
            value=value,
            description=rating,
            previous_close=float(prev) if prev is not None else None,
            one_week_ago=float(w1) if w1 is not None else None,
            one_month_ago=float(m1) if m1 is not None else None,
            one_year_ago=float(y1) if y1 is not None else None,
            sub_indicators=sub,
            source="cnn_api",
        )
    except Exception as e:
        logger.warning("CNN Fear & Greed API 오류: %s", e)
        return {"ok": False, "error": str(e)}
