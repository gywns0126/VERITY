"""
XGBoost 1주 상승 확률 예측기 (Sprint 4)
- 종목별 과거 1년 데이터로 피처 생성
- RSI/MACD/볼린저/거래량/MA배열 등 15개 피처
- 5일 후 수익률 > 0% 를 타겟으로 학습
- 학습 데이터가 부족하면 fallback으로 규칙 기반 확률 반환
"""
import numpy as np
import pandas as pd
import yfinance as yf
from typing import Dict, Optional

try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except Exception:
    # ImportError, XGBoostError(libomp 미설치 등) — 파이프라인은 rule_based 폴백으로 계속
    HAS_XGB = False
    XGBClassifier = None  # type: ignore


def _compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """OHLCV 데이터프레임에서 예측 피처 생성"""
    close = df["Close"]
    volume = df["Volume"]

    feat = pd.DataFrame(index=df.index)

    feat["rsi14"] = _rsi(close, 14)
    feat["rsi7"] = _rsi(close, 7)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    feat["macd_hist"] = macd - signal

    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    feat["ma5_ratio"] = close / ma5 - 1
    feat["ma20_ratio"] = close / ma20 - 1
    feat["ma_alignment"] = ((close > ma20) & (ma20 > ma60)).astype(int)

    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_range = bb_upper - bb_lower
    feat["bb_position"] = np.where(bb_range > 0, (close - bb_lower) / bb_range, 0.5)

    vol_ma20 = volume.rolling(20).mean()
    feat["vol_ratio"] = volume / vol_ma20.replace(0, 1)

    feat["return_1d"] = close.pct_change(1)
    feat["return_5d"] = close.pct_change(5)
    feat["volatility_20d"] = close.pct_change().rolling(20).std()

    high_20d = close.rolling(20).max()
    feat["drawdown_20d"] = (close - high_20d) / high_20d

    feat["volume_price_trend"] = (volume * close.pct_change()).rolling(5).sum()

    return feat


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _build_dataset(ticker_yf: str, period: str = "2y", forward_days: int = 5):
    """
    학습 데이터셋 구축
    - 피처: 기술적 지표 15개
    - 타겟: forward_days 후 수익률 > 0 (이진 분류)
    """
    try:
        t = yf.Ticker(ticker_yf)
        df = t.history(period=period)
        if df.empty or len(df) < 120:
            return None, None, None
    except Exception:
        return None, None, None

    df = df.dropna(subset=["Close"])
    features = _compute_features(df)

    future_return = df["Close"].pct_change(forward_days).shift(-forward_days)
    target = (future_return > 0).astype(int)

    combined = features.copy()
    combined["target"] = target
    combined = combined.dropna()

    if len(combined) < 60:
        return None, None, None

    X = combined.drop("target", axis=1)
    y = combined["target"]

    return X, y, features


def predict_stock(ticker_yf: str, current_features: Optional[Dict] = None) -> Dict:
    """
    XGBoost로 1주 후 상승 확률 예측
    반환: up_probability, confidence, model_accuracy, feature_importance
    """
    if not HAS_XGB:
        return _fallback_prediction(current_features)

    X, y, all_features = _build_dataset(ticker_yf)
    if X is None:
        return _fallback_prediction(current_features)

    split = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train, y_test = y.iloc[:split], y.iloc[split:]

    model = XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        use_label_encoder=False,
        eval_metric="logloss",
        verbosity=0,
    )

    try:
        model.fit(X_train, y_train)
    except Exception:
        return _fallback_prediction(current_features)

    accuracy = float(model.score(X_test, y_test))

    last_features = all_features.dropna().iloc[-1:]
    if last_features.empty:
        return _fallback_prediction(current_features)

    try:
        proba = model.predict_proba(last_features)[0]
        up_prob = float(proba[1]) if len(proba) > 1 else 0.5
    except Exception:
        up_prob = 0.5

    importances = {}
    if hasattr(model, "feature_importances_"):
        for fname, imp in zip(X.columns, model.feature_importances_):
            importances[fname] = round(float(imp), 4)
        importances = dict(sorted(importances.items(), key=lambda x: -x[1])[:5])

    confidence_level = "high" if accuracy >= 0.6 else "medium" if accuracy >= 0.52 else "low"

    return {
        "up_probability": round(up_prob * 100, 1),
        "model_accuracy": round(accuracy * 100, 1),
        "confidence_level": confidence_level,
        "top_features": importances,
        "method": "xgboost",
        "train_samples": split,
        "test_samples": len(X) - split,
    }


def _fallback_prediction(features: Optional[Dict] = None) -> Dict:
    """XGBoost 사용 불가 시 규칙 기반 예측"""
    if not features:
        return {
            "up_probability": 50.0,
            "model_accuracy": 0,
            "confidence_level": "none",
            "top_features": {},
            "method": "fallback",
            "train_samples": 0,
            "test_samples": 0,
        }

    score = 50.0
    tech = features.get("technical", {})
    mf = features.get("multi_factor", {})

    rsi = tech.get("rsi", 50)
    if rsi <= 30:
        score += 12
    elif rsi <= 40:
        score += 6
    elif rsi >= 70:
        score -= 10

    if tech.get("macd_hist", 0) > 0:
        score += 5
    else:
        score -= 3

    ms = mf.get("multi_score", 50)
    score += (ms - 50) * 0.3

    score = max(5, min(95, score))

    return {
        "up_probability": round(score, 1),
        "model_accuracy": 0,
        "confidence_level": "rule_based",
        "top_features": {},
        "method": "rule_based",
        "train_samples": 0,
        "test_samples": 0,
    }
