"""talib_observations — TA-Lib 지표/캔들 observation-only 계측 (2026-06-09 착수).

목적: 자체 RSI/MACD/ATR(technical.py) vs TA-Lib 표준 구현의 divergence 를 노출 +
TA-Lib geometry 기반 캔들패턴을 별도 필드로 부착. **점수에 미반영** (RULE 7 정합 —
established 외부 도구 prior 사용은 정당하나, 검증 trail 중간 점수 불연속 회피 위해
observation-only 로 먼저 쌓고 clean 경계서 flip 결정).

연관: [[project_oss_adoption_scorecard_2026_06_09]] (TA-Lib adopt, BSD 라이선스).
divergence 가 크면 = 자체 구현 버그 후보 (예: quality.py F2/F4 류). N 누적 후
'표준화 flip' 사전등록 대상.

guarded import — talib 미설치 환경(로컬 일부/CI 빌드 전)에서도 파이프라인 무중단.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

try:
    import talib  # type: ignore
    _TALIB_AVAILABLE = True
except Exception:  # ImportError 또는 C lib 부재
    _TALIB_AVAILABLE = False

# VERITY candle.py 가 추적하는 패턴군 ↔ TA-Lib geometry 함수 매핑 (관측 표준화).
_CDL_FUNCS = (
    ("hammer", "CDLHAMMER"),
    ("inverted_hammer", "CDLINVERTEDHAMMER"),
    ("engulfing", "CDLENGULFING"),
    ("morning_star", "CDLMORNINGSTAR"),
    ("evening_star", "CDLEVENINGSTAR"),
    ("shooting_star", "CDLSHOOTINGSTAR"),
    ("hanging_man", "CDLHANGINGMAN"),
    ("piercing", "CDLPIERCING"),
    ("dark_cloud", "CDLDARKCLOUDCOVER"),
    ("three_white_soldiers", "CDL3WHITESOLDIERS"),
    ("three_black_crows", "CDL3BLACKCROWS"),
    ("harami", "CDLHARAMI"),
    ("doji", "CDLDOJI"),
)


def _fin(v: Any) -> Optional[float]:
    """nan/inf → None, 아니면 float."""
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def compute_talib_observations(
    hist: Any,
    self_rsi: Optional[float] = None,
    self_macd_hist: Optional[float] = None,
    self_atr: Optional[float] = None,
) -> Dict[str, Any]:
    """TA-Lib 관측 dict 반환. hist = yfinance history DataFrame (OHLCV).

    🚨 observation-only: 어떤 호출처도 이 반환값을 점수/등급에 반영하지 않음.
    """
    if not _TALIB_AVAILABLE:
        return {"available": False, "reason": "talib_not_installed"}
    try:
        cols = ["Open", "High", "Low", "Close"]
        if not all(c in getattr(hist, "columns", []) for c in cols):
            return {"available": True, "error": "missing_ohlc_columns"}
        df = hist[cols].dropna()
        n = len(df)
        if n < 35:  # MACD(12,26,9) 최소 유효 구간
            return {"available": True, "insufficient_history": True, "n": n}

        o = df["Open"].to_numpy(dtype="float64")
        h = df["High"].to_numpy(dtype="float64")
        l = df["Low"].to_numpy(dtype="float64")
        c = df["Close"].to_numpy(dtype="float64")

        rsi_t = _fin(talib.RSI(c, timeperiod=14)[-1])
        _macd, _sig, _mhist = talib.MACD(c)
        macd_hist_t = _fin(_mhist[-1])
        atr_t = _fin(talib.ATR(h, l, c, timeperiod=14)[-1])
        _u, _m, _lo = talib.BBANDS(c, timeperiod=20)
        bb_u, bb_lo = _fin(_u[-1]), _fin(_lo[-1])
        price = _fin(c[-1])
        bb_position = None
        if bb_u is not None and bb_lo is not None and price is not None and bb_u > bb_lo:
            bb_position = round((price - bb_lo) / (bb_u - bb_lo) * 100, 1)
        _k, _d = talib.STOCH(h, l, c)
        stoch_k = _fin(_k[-1])

        # 캔들패턴 (마지막 봉): talib +100 강세 / -100 약세 / 0 없음
        patterns: Dict[str, int] = {}
        for label, fn_name in _CDL_FUNCS:
            fn = getattr(talib, fn_name, None)
            if fn is None:
                continue
            try:
                v = int(fn(o, h, l, c)[-1])
            except Exception:
                continue
            if v != 0:
                patterns[label] = v

        # 자체 구현 대비 divergence (버그 표면화)
        divergence: Dict[str, float] = {}
        if rsi_t is not None and self_rsi is not None:
            divergence["rsi_abs"] = round(abs(rsi_t - float(self_rsi)), 2)
        if macd_hist_t is not None and self_macd_hist is not None:
            divergence["macd_hist_abs"] = round(abs(macd_hist_t - float(self_macd_hist)), 4)
        if atr_t is not None and self_atr:
            divergence["atr_pct"] = round(abs(atr_t - float(self_atr)) / float(self_atr) * 100, 2)

        return {
            "available": True,
            "n": n,
            "rsi": rsi_t,
            "macd_hist": macd_hist_t,
            "atr": atr_t,
            "bb_position": bb_position,
            "stoch_k": stoch_k,
            "candle_patterns": patterns,
            "divergence_vs_self": divergence,
            "talib_version": getattr(talib, "__version__", "?"),
        }
    except Exception as e:  # noqa: BLE001
        return {"available": True, "error": str(e)[:160]}
