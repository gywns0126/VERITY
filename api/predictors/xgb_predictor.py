"""
앙상블 예측기 V2 — 3-Architecture Ensemble + Conformal Prediction

아키텍처:
  GBDT ×3 (XGBoost / LightGBM / CatBoost)
  + Neural Net (sklearn MLP)
  + Linear (Logistic Regression)

핵심 개선:
  1. Walk-forward validation — 시계열 정합 정확도 계측 (미래 정보 누출 방지)
  2. Split Conformal Prediction — distribution-free coverage guarantee
  3. WF 정확도 가중 소프트 보팅 — 고성능 모델에 자동 편중
  4. 데이터 분할: Train 70% → Calibration 15% → Test 15%
"""
import numpy as np
import pandas as pd
import yfinance as yf
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── GBDT models (optional) ──
try:
    from xgboost import XGBClassifier
    _HAS_XGB = True
except Exception:
    _HAS_XGB = False
    XGBClassifier = None  # type: ignore

try:
    from lightgbm import LGBMClassifier
    _HAS_LGBM = True
except Exception:
    _HAS_LGBM = False
    LGBMClassifier = None  # type: ignore

try:
    from catboost import CatBoostClassifier
    _HAS_CAT = True
except Exception:
    _HAS_CAT = False
    CatBoostClassifier = None  # type: ignore

# ── sklearn models (Neural Net + Linear) ──
try:
    from sklearn.neural_network import MLPClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    _HAS_SKLEARN = True
except Exception:
    _HAS_SKLEARN = False

# ── 상수 ──
_WF_MIN_TRAIN = 120
_WF_STEP = 50
_CONFORMAL_ALPHA = 0.10   # coverage = 90%
_TRAIN_RATIO = 0.70
_CAL_RATIO = 0.15


# ═══════════════════════════════════════════════════════════
#  피처 엔지니어링
# ═══════════════════════════════════════════════════════════

def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _compute_features(df: pd.DataFrame) -> pd.DataFrame:
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


def _build_dataset(
    ticker_yf: str, period: str = "2y", forward_days: int = 5,
) -> Tuple[Optional[pd.DataFrame], Optional[pd.Series], Optional[pd.DataFrame]]:
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


# ═══════════════════════════════════════════════════════════
#  모델 팩토리 (3-Architecture)
# ═══════════════════════════════════════════════════════════

def _model_factories() -> List[Tuple[str, str, Callable]]:
    """(이름, 아키텍처, 팩토리) 리스트 — 각 호출마다 fresh 인스턴스 생성용."""
    factories: List[Tuple[str, str, Callable]] = []

    if _HAS_XGB:
        factories.append(("xgboost", "gbdt", lambda: XGBClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, colsample_bytree=0.8,
            use_label_encoder=False, eval_metric="logloss", verbosity=0,
        )))
    if _HAS_LGBM:
        factories.append(("lightgbm", "gbdt", lambda: LGBMClassifier(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            subsample=0.8, colsample_bytree=0.8, verbose=-1,
        )))
    if _HAS_CAT:
        factories.append(("catboost", "gbdt", lambda: CatBoostClassifier(
            iterations=100, depth=4, learning_rate=0.1,
            subsample=0.8, verbose=0, allow_writing_files=False,
        )))
    if _HAS_SKLEARN:
        factories.append(("mlp", "neural_net", lambda: Pipeline([
            ("scaler", StandardScaler()),
            ("model", MLPClassifier(
                hidden_layer_sizes=(64, 32), max_iter=200,
                early_stopping=True, validation_fraction=0.15,
                random_state=42,
            )),
        ])))
        factories.append(("logistic", "linear", lambda: Pipeline([
            ("scaler", StandardScaler()),
            ("model", LogisticRegression(max_iter=500, C=1.0, random_state=42)),
        ])))

    return factories


# ═══════════════════════════════════════════════════════════
#  Walk-Forward Validation
# ═══════════════════════════════════════════════════════════

def _walk_forward_accuracy(
    factory: Callable,
    X: pd.DataFrame,
    y: pd.Series,
    min_train: int = _WF_MIN_TRAIN,
    step: int = _WF_STEP,
) -> Tuple[float, int]:
    """Expanding-window walk-forward. 각 fold마다 fresh 모델을 생성해 학습/평가."""
    n = len(X)
    accs: List[float] = []

    for fold_end in range(min_train, n - step, step):
        test_end = min(fold_end + step, n)
        try:
            model = factory()
            model.fit(X.iloc[:fold_end], y.iloc[:fold_end])
            acc = float(model.score(X.iloc[fold_end:test_end], y.iloc[fold_end:test_end]))
            accs.append(acc)
        except Exception:
            continue

    if not accs:
        return 0.0, 0
    return float(np.mean(accs)), len(accs)


# ═══════════════════════════════════════════════════════════
#  Split Conformal Prediction
# ═══════════════════════════════════════════════════════════

def _conformal_calibrate(
    trained_models: List[Tuple[str, Any, float]],
    X_cal: pd.DataFrame,
    y_cal: pd.Series,
) -> np.ndarray:
    """캘리브레이션 셋에서 비순응도(nonconformity) 점수 계산.

    Score_i = 1 - P_ensemble(true_class_i | x_i)
    """
    if len(X_cal) == 0:
        return np.array([0.5])

    weighted_proba = np.zeros((len(X_cal), 2))
    total_w = 0.0
    for _name, model, weight in trained_models:
        try:
            p = model.predict_proba(X_cal)
            if p.shape[1] < 2:
                continue
            weighted_proba += p * weight
            total_w += weight
        except Exception:
            continue

    if total_w <= 0:
        return np.array([0.5])
    weighted_proba /= total_w

    scores = np.array([
        1.0 - weighted_proba[i, int(y_cal.iloc[i])]
        for i in range(len(y_cal))
    ])
    return np.sort(scores)


def _conformal_predict(
    trained_models: List[Tuple[str, Any, float]],
    X_new: pd.DataFrame,
    cal_scores: np.ndarray,
    alpha: float = _CONFORMAL_ALPHA,
) -> Tuple[float, float, float, List[int], float]:
    """Split Conformal Prediction — coverage guarantee = 1 - alpha.

    Returns: (up_prob, ci_lower, ci_upper, prediction_set, q_hat)
    """
    n = len(cal_scores)
    q_level = min(np.ceil((n + 1) * (1 - alpha)) / n, 1.0)
    q_hat = float(np.quantile(cal_scores, q_level))

    weighted_proba = np.zeros(2)
    total_w = 0.0
    for _name, model, weight in trained_models:
        try:
            p = model.predict_proba(X_new)[0]
            if len(p) < 2:
                continue
            weighted_proba += p * weight
            total_w += weight
        except Exception:
            continue

    if total_w <= 0:
        return 0.5, 0.0, 1.0, [0, 1], 0.5
    weighted_proba /= total_w

    up_prob = float(weighted_proba[1])

    prediction_set = [c for c in range(2) if 1 - weighted_proba[c] <= q_hat]

    ci_lower = max(0.0, up_prob - q_hat)
    ci_upper = min(1.0, up_prob + q_hat)

    return up_prob, ci_lower, ci_upper, prediction_set, q_hat


# ═══════════════════════════════════════════════════════════
#  메인 예측 함수
# ═══════════════════════════════════════════════════════════

def predict_stock(ticker_yf: str, current_features: Optional[Dict] = None) -> Dict:
    """
    다중 아키텍처 앙상블 + Conformal Prediction 으로 5일 후 상승 확률 예측.

    Walk-forward validation → Split Conformal → Weighted Ensemble.
    반환 dict은 기존 필드 + conformal 필드 모두 포함 (하위 호환).
    """
    factories = _model_factories()
    if not factories:
        return _fallback_prediction(current_features)

    X, y, all_features = _build_dataset(ticker_yf)
    if X is None:
        return _fallback_prediction(current_features)

    last_features = all_features.dropna().iloc[-1:]
    if last_features.empty:
        return _fallback_prediction(current_features)

    # ── 시계열 정합 분할: Train 70% | Cal 15% | Test 15% ──
    n = len(X)
    train_end = int(n * _TRAIN_RATIO)
    cal_end = int(n * (_TRAIN_RATIO + _CAL_RATIO))

    if train_end < 60 or (cal_end - train_end) < 10:
        return _fallback_prediction(current_features)

    X_train = X.iloc[:train_end]
    y_train = y.iloc[:train_end]
    X_cal = X.iloc[train_end:cal_end]
    y_cal = y.iloc[train_end:cal_end]
    X_test = X.iloc[cal_end:]
    y_test = y.iloc[cal_end:]

    # ── 1. Walk-forward + 모델 학습 ──
    trained_models: List[Tuple[str, Any, float]] = []
    individual: Dict[str, Dict] = {}
    all_importances: Dict[str, float] = {}

    for name, arch, factory in factories:
        wf_acc, n_folds = _walk_forward_accuracy(factory, X, y)

        try:
            model = factory()
            model.fit(X_train, y_train)
            val_acc = float(model.score(X_test, y_test)) if len(X_test) > 0 else wf_acc

            weight = max(wf_acc, 0.01) if n_folds > 0 else max(val_acc, 0.01)
            trained_models.append((name, model, weight))

            individual[name] = {
                "architecture": arch,
                "wf_accuracy": round(wf_acc * 100, 1),
                "val_accuracy": round(val_acc * 100, 1),
                "wf_folds": n_folds,
                "weight": round(weight, 4),
            }

            if hasattr(model, "feature_importances_"):
                for fname, imp in zip(X.columns, model.feature_importances_):
                    all_importances[fname] = all_importances.get(fname, 0) + float(imp)
        except Exception:
            continue

    if not trained_models:
        return _fallback_prediction(current_features)

    # ── 2. Conformal Calibration ──
    cal_scores = _conformal_calibrate(trained_models, X_cal, y_cal)

    # ── 3. Conformal Prediction ──
    up_prob, ci_lower, ci_upper, pred_set, q_hat = _conformal_predict(
        trained_models, last_features, cal_scores,
    )

    # ── 4. 개별 모델 예측값 (모델 간 분산 계산용) ──
    raw_probs: List[float] = []
    for _name, model, _ in trained_models:
        try:
            p = model.predict_proba(last_features)[0]
            raw_probs.append(float(p[1]) if len(p) > 1 else 0.5)
        except Exception:
            continue

    std_prob = float(np.std(raw_probs, ddof=1)) if len(raw_probs) >= 2 else 0.0

    # ── 5. 피처 중요도 (GBDT 모델 기준) ──
    n_gbdt = sum(
        1 for nm, _, _ in trained_models
        if individual.get(nm, {}).get("architecture") == "gbdt"
    )
    top_features: Dict[str, float] = {}
    if all_importances and n_gbdt > 0:
        normed = {k: v / n_gbdt for k, v in all_importances.items()}
        top_features = dict(sorted(normed.items(), key=lambda x: -x[1])[:5])
        top_features = {k: round(v, 4) for k, v in top_features.items()}

    # ── 6. 종합 신뢰도 ──
    wf_accs = [w for _, _, w in trained_models]
    mean_wf_acc = float(np.mean(wf_accs))
    conformal_width = ci_upper - ci_lower

    if mean_wf_acc >= 0.58 and conformal_width < 0.35:
        confidence_level = "high"
    elif mean_wf_acc >= 0.52 or conformal_width < 0.50:
        confidence_level = "medium"
    else:
        confidence_level = "low"

    architectures = sorted({
        individual[nm]["architecture"]
        for nm, _, _ in trained_models if nm in individual
    })
    n_models = len(trained_models)
    method = f"ensemble_{n_models}m_{len(architectures)}arch"
    max_folds = max((individual[nm].get("wf_folds", 0) for nm in individual), default=0)

    result: Dict[str, Any] = {
        "up_probability": round(up_prob * 100, 1),
        "prediction_std": round(std_prob * 100, 1),
        "confidence_interval": [round(ci_lower * 100, 1), round(ci_upper * 100, 1)],
        "conformal_coverage": round((1 - _CONFORMAL_ALPHA) * 100),
        "conformal_q_hat": round(q_hat, 4),
        "conformal_width_pct": round(conformal_width * 100, 1),
        "prediction_set": pred_set,
        "model_accuracy": round(mean_wf_acc * 100, 1),
        "individual_models": individual,
        "confidence_level": confidence_level,
        "top_features": top_features,
        "method": method,
        "architectures": architectures,
        "walk_forward_folds": max_folds,
        "train_samples": train_end,
        "calibration_samples": cal_end - train_end,
        "test_samples": n - cal_end,
    }

    try:
        from api.tracing import get_tracer
        feat_row = last_features.iloc[0].to_dict() if not last_features.empty else {}
        get_tracer().log_prediction(ticker_yf, {
            "feature_vector": {
                k: round(float(v), 6) if isinstance(v, float) else v
                for k, v in feat_row.items()
            },
            "all_importances": (
                {k: round(v, 4) for k, v in all_importances.items()}
                if all_importances else {}
            ),
        }, result)
    except Exception:
        pass

    return result


# ═══════════════════════════════════════════════════════════
#  폴백 (데이터/모델 없을 때 규칙 기반)
# ═══════════════════════════════════════════════════════════

def _fallback_prediction(features: Optional[Dict] = None) -> Dict:
    base: Dict[str, Any] = {
        "up_probability": 50.0,
        "prediction_std": 0.0,
        "confidence_interval": [50.0, 50.0],
        "conformal_coverage": 0,
        "conformal_q_hat": 0,
        "conformal_width_pct": 0,
        "prediction_set": [0, 1],
        "model_accuracy": 0,
        "individual_models": {},
        "confidence_level": "none",
        "top_features": {},
        "method": "fallback",
        "architectures": [],
        "walk_forward_folds": 0,
        "train_samples": 0,
        "calibration_samples": 0,
        "test_samples": 0,
    }

    if not features:
        return base

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

    base["up_probability"] = round(score, 1)
    base["confidence_interval"] = [round(score, 1), round(score, 1)]
    base["confidence_level"] = "rule_based"
    base["method"] = "rule_based"
    return base
