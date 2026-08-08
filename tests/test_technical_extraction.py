# -*- coding: utf-8 -*-
"""analyze_technical 순수함수 분리 — 동작 보존 회귀 고정.

사전등록 `docs/PREREG_BACKTEST_KR_PRICE_AXES.md` §1.1 은 이 분리를 **이동만**으로
제한한다. 수식이 한 줄이라도 바뀌면 백테스트가 운영 산식이 아닌 다른 산식을
검정하게 되고, 그 결과는 쓸 수 없다.

그래서 이 테스트는 **분리 전 원본을 origin/main 에서 직접 꺼내** 같은 OHLCV 에
대해 산출을 대조한다. "내가 안 바꿨다" 는 주장 대신 기계 대조로 고정한다.
"""
from __future__ import annotations

import os
import subprocess
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")

from api.analyzers.technical import analyze_technical_from_ohlcv  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KEYS = ("price", "ma5", "ma20", "ma60", "ma120", "rsi", "macd", "macd_signal",
         "macd_hist", "bb_upper", "bb_lower", "bb_position", "vol_ratio",
         "atr_14d", "atr_14d_pct", "return_5d_pct", "technical_score")


def _synthetic(n: int = 300, seed: int = 7):
    """결정론적 OHLCV — RNG 시드 고정 (재현 가능해야 대조가 의미 있다)."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0005, 0.018, n)
    close = 50000 * np.exp(np.cumsum(steps))
    high = close * (1 + np.abs(rng.normal(0, 0.008, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.008, n)))
    vol = rng.integers(50_000, 900_000, n).astype(float)
    idx = pd.date_range("2024-01-01", periods=n, freq="D")
    return (pd.Series(close, index=idx), pd.Series(high, index=idx),
            pd.Series(low, index=idx), pd.Series(vol, index=idx))


def _baseline_module():
    """origin/main 의 분리 전 technical.py 를 메모리에 적재.

    파일을 디스크에 쓰지 않는다 — 테스트가 워킹트리를 오염시키면 안 된다.
    """
    try:
        src = subprocess.run(
            ["git", "-C", _REPO, "show", "origin/main:api/analyzers/technical.py"],
            capture_output=True, text=True, timeout=30, check=True).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        pytest.skip("origin/main 조회 불가 (오프라인/얕은 클론)")
    if "def analyze_technical_from_ohlcv" in src:
        pytest.skip("origin/main 이 이미 분리본 — 대조 대상 아님")
    mod = types.ModuleType("_technical_baseline")
    mod.__file__ = os.path.join(_REPO, "api/analyzers/technical.py")
    sys.modules["_technical_baseline"] = mod
    exec(compile(src, mod.__file__, "exec"), mod.__dict__)
    return mod


def _baseline_call(mod, close, high, low, volume):
    """분리 전 analyze_technical 을 yfinance 대신 준비된 OHLCV 로 구동.

    원본은 함수 안에서 yf_ticker 를 부르므로, 그 모듈을 가짜로 끼워 같은
    데이터가 흘러 들어가게 한다. 산식 경로는 그대로 지난다.
    """
    hist = pd.DataFrame({"Close": close, "High": high, "Low": low, "Volume": volume})

    fake = types.ModuleType("api.collectors.yfinance_safe")
    fake.yf_ticker = lambda _t: types.SimpleNamespace(history=lambda **_k: hist)
    saved = sys.modules.get("api.collectors.yfinance_safe")
    sys.modules["api.collectors.yfinance_safe"] = fake
    try:
        return mod.analyze_technical("005930.KS")
    finally:
        if saved is not None:
            sys.modules["api.collectors.yfinance_safe"] = saved
        else:
            sys.modules.pop("api.collectors.yfinance_safe", None)


@pytest.mark.parametrize("seed", [7, 21, 99])
def test_extraction_preserves_every_output(seed):
    """🚨 분리 전후 산출이 전 필드 동일해야 한다. 하나라도 다르면 검정 중단 사유다."""
    close, high, low, volume = _synthetic(seed=seed)
    got = analyze_technical_from_ohlcv(close, high, low, volume, ticker="005930.KS")
    want = _baseline_call(_baseline_module(), close, high, low, volume)

    for k in _KEYS:
        a, b = got.get(k), want.get(k)
        if a is None or b is None:
            assert a == b, f"{k}: 분리 {a} vs 원본 {b}"
        else:
            assert a == pytest.approx(b, rel=1e-12, abs=1e-12), \
                f"{k}: 분리 {a} vs 원본 {b}"


def test_extraction_preserves_signals():
    close, high, low, volume = _synthetic(seed=7)
    got = analyze_technical_from_ohlcv(close, high, low, volume, ticker="005930.KS")
    want = _baseline_call(_baseline_module(), close, high, low, volume)
    assert got.get("signals") == want.get("signals")


def test_short_series_returns_empty_like_original():
    """5봉 미만 = 산출 불가. 원본과 같은 빈 결과를 줘야 한다."""
    close, high, low, volume = _synthetic(n=4)
    got = analyze_technical_from_ohlcv(close, high, low, volume)
    assert got["technical_score"] == 50 and got["price"] == 0


def test_wrapper_still_takes_ticker_and_does_io():
    """운영 진입점 시그니처가 그대로여야 한다 — 호출처 24곳이 이걸 부른다."""
    import inspect
    from api.analyzers.technical import analyze_technical
    sig = inspect.signature(analyze_technical)
    assert list(sig.parameters) == ["ticker_yf"]
    assert "yf_ticker" in inspect.getsource(analyze_technical)


def test_pure_function_does_no_io():
    """순수 함수 본문에 네트워크·파일 진입점이 없어야 한다.

    (ATR 마이그레이션 로깅은 헬퍼 안에 있고 환경변수 게이트로 꺼져 있다 —
     여기서는 순수 함수가 **직접** I/O 를 부르지 않는지만 고정한다.)
    """
    import inspect
    src = inspect.getsource(analyze_technical_from_ohlcv)
    for bad in ("yf_ticker", "t.history", "urlopen", "requests.", "open("):
        assert bad not in src, f"순수 함수에 I/O 잔존: {bad}"
