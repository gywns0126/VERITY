"""
ML 알파 조합기 — 여러 팩터를 최적 비율로 블렌딩

학술 근거:
  - de Prado (2018): Purged K-Fold CV — 금융 시계열에서 미래정보 누수 방지
  - Gu, Kelly & Xiu (2020): ML이 팩터 조합에서 선형 모델을 압도
  - IC 가중(IC-Weighted): 각 팩터의 예측력(IC)에 비례하여 가중치 부여

구현:
  1. IC-Weighted 조합: 가장 단순하지만 강력한 방법
  2. Ridge 회귀 조합: 과적합 방지하며 비선형 관계 포착
  3. Purged K-Fold: 금융 데이터 특화 교차검증
  4. 팩터 선택: IC가 유의미한 팩터만 자동 선별
"""
from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from api.quant.alpha.alpha_scanner import FACTOR_EXTRACTORS, _spearman_rank_corr


def ic_weighted_combine(
    stocks: List[Dict[str, Any]],
    factor_ic_report: Dict[str, Any],
    min_ic: float = 0.03,
) -> List[Dict[str, Any]]:
    """
    IC-Weighted 알파 조합.

    각 팩터 점수를 해당 팩터의 IC에 비례하여 가중합.
    IC가 min_ic 미만인 팩터는 자동 제외.

    Args:
        stocks: 종목 리스트 (팩터 점수 포함)
        factor_ic_report: scan_all_factors() 결과
        min_ic: 최소 IC 임계값

    Returns:
        stocks에 alpha_combined_score 추가된 리스트
    """
    factors_data = factor_ic_report.get("factors", {})

    active_factors: Dict[str, float] = {}
    for name, info in factors_data.items():
        ic = abs(info.get("ic_mean", 0))
        if ic >= min_ic and not info.get("decay_alert", False):
            active_factors[name] = ic

    if not active_factors:
        for stock in stocks:
            stock["alpha_combined"] = {
                "score": stock.get("multi_factor", {}).get("multi_score", 50),
                "method": "fallback",
                "active_factors": [],
            }
        return stocks

    total_ic = sum(active_factors.values())
    weights = {k: v / total_ic for k, v in active_factors.items()}

    for stock in stocks:
        combined = 0.0
        used_factors: List[str] = []

        for factor_name, weight in weights.items():
            extractor = FACTOR_EXTRACTORS.get(factor_name)
            if extractor is None:
                continue

            val = extractor(stock)
            if val is None:
                val = 50

            combined += float(val) * weight
            used_factors.append(factor_name)

        stock["alpha_combined"] = {
            "score": round(max(0, min(100, combined))),
            "method": "ic_weighted",
            "weights": {k: round(v, 4) for k, v in weights.items()},
            "active_factors": used_factors,
        }

    return stocks


def ridge_combine(
    snapshots: List[Dict[str, Any]],
    forward_days: int = 7,
    alpha_reg: float = 1.0,
) -> Dict[str, Any]:
    """
    Ridge 회귀로 최적 팩터 가중치 학습.
    Purged K-Fold로 검증하여 과적합 방지.

    Args:
        snapshots: 날짜순 스냅샷 리스트
        forward_days: 미래 수익률 기간
        alpha_reg: Ridge 정규화 강도

    Returns:
        {
            "weights": {factor: weight},
            "cv_score": float,
            "train_r2": float,
        }
    """
    X_all, y_all, feature_names = _build_training_set(snapshots, forward_days)

    if X_all is None or len(X_all) < 30:
        return {
            "weights": {},
            "cv_score": 0,
            "train_r2": 0,
            "note": "학습 데이터 부족",
        }

    # Purged K-Fold CV
    cv_scores = _purged_kfold_cv(X_all, y_all, alpha_reg, n_folds=5, purge_gap=forward_days)

    # 전체 데이터로 최종 학습
    weights = _ridge_fit(X_all, y_all, alpha_reg)

    y_pred = X_all @ weights
    ss_res = np.sum((y_all - y_pred) ** 2)
    ss_tot = np.sum((y_all - np.mean(y_all)) ** 2)
    train_r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    weight_dict = {}
    for i, name in enumerate(feature_names):
        weight_dict[name] = round(float(weights[i]), 6)

    weight_dict = dict(sorted(weight_dict.items(), key=lambda x: abs(x[1]), reverse=True))

    return {
        "weights": weight_dict,
        "cv_score": round(float(np.mean(cv_scores)), 4) if cv_scores else 0,
        "cv_std": round(float(np.std(cv_scores)), 4) if len(cv_scores) >= 2 else 0,
        "train_r2": round(float(train_r2), 4),
        "n_samples": len(y_all),
        "n_features": len(feature_names),
    }


def _build_training_set(
    snapshots: List[Dict[str, Any]],
    forward_days: int,
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], List[str]]:
    """스냅샷에서 팩터 행렬(X)과 미래 수익률(y)을 구성."""
    factor_names = [
        "multi_factor", "fundamental", "technical", "flow", "sentiment",
        "consensus", "prediction", "timing", "safety_score",
        "momentum", "quality", "volatility", "mean_reversion",
    ]

    X_rows: List[List[float]] = []
    y_rows: List[float] = []

    for i in range(len(snapshots) - 1):
        snap = snapshots[i]
        recs = snap.get("recommendations", [])

        future_snap = None
        for j in range(i + 1, min(i + forward_days + 1, len(snapshots))):
            future_snap = snapshots[j]
        if not future_snap:
            continue

        future_prices: Dict[str, float] = {}
        for r in future_snap.get("recommendations", []):
            t = r.get("ticker", "")
            p = r.get("price")
            if t and p:
                try:
                    future_prices[t] = float(p)
                except (TypeError, ValueError):
                    pass

        for stock in recs:
            ticker = stock.get("ticker", "")
            price = stock.get("price")
            if not ticker or not price or ticker not in future_prices:
                continue

            try:
                price_f = float(price)
                if price_f <= 0:
                    continue
                ret = (future_prices[ticker] - price_f) / price_f * 100
            except (TypeError, ValueError):
                continue

            row = []
            valid = True
            for name in factor_names:
                extractor = FACTOR_EXTRACTORS.get(name)
                if extractor is None:
                    row.append(50.0)
                    continue
                val = extractor(stock)
                if val is None:
                    row.append(50.0)
                else:
                    row.append(float(val))

            X_rows.append(row)
            y_rows.append(ret)

    if len(X_rows) < 20:
        return None, None, factor_names

    X = np.array(X_rows, dtype=float)
    y = np.array(y_rows, dtype=float)

    # Z-정규화
    X_mean = np.mean(X, axis=0)
    X_std = np.std(X, axis=0)
    X_std[X_std == 0] = 1
    X = (X - X_mean) / X_std

    return X, y, factor_names


def _ridge_fit(X: np.ndarray, y: np.ndarray, alpha: float) -> np.ndarray:
    """Ridge 회귀 (closed-form)."""
    n_features = X.shape[1]
    I = np.eye(n_features)
    try:
        w = np.linalg.solve(X.T @ X + alpha * I, X.T @ y)
    except np.linalg.LinAlgError:
        w = np.zeros(n_features)
    return w


def _purged_kfold_cv(
    X: np.ndarray,
    y: np.ndarray,
    alpha: float,
    n_folds: int = 5,
    purge_gap: int = 7,
) -> List[float]:
    """
    Purged K-Fold 교차검증.
    각 fold 경계에서 purge_gap만큼의 관측치를 제거하여 미래정보 누수 방지.
    (de Prado, 2018)
    """
    n = len(y)
    fold_size = n // n_folds
    scores: List[float] = []

    for k in range(n_folds):
        test_start = k * fold_size
        test_end = min((k + 1) * fold_size, n)

        purge_start = max(0, test_start - purge_gap)
        purge_end = min(n, test_end + purge_gap)

        train_mask = np.ones(n, dtype=bool)
        train_mask[purge_start:purge_end] = False

        test_mask = np.zeros(n, dtype=bool)
        test_mask[test_start:test_end] = True

        X_train = X[train_mask]
        y_train = y[train_mask]
        X_test = X[test_mask]
        y_test = y[test_mask]

        if len(y_train) < 10 or len(y_test) < 3:
            continue

        w = _ridge_fit(X_train, y_train, alpha)
        y_pred = X_test @ w

        # Rank IC as metric
        pred_list = y_pred.tolist()
        actual_list = y_test.tolist()
        ic = _spearman_rank_corr(pred_list, actual_list)
        scores.append(ic)

    return scores


def generate_optimal_weights(
    snapshots: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    최적 알파 가중치를 생성하여 Strategy Evolver에 전달할 형태로 반환.
    IC-Weighted와 Ridge 결과를 앙상블.
    """
    if snapshots is None:
        from api.workflows.archiver import load_snapshots_range
        snapshots = load_snapshots_range(60)

    if len(snapshots) < 10:
        return {
            "method": "default",
            "weights": {},
            "note": "데이터 부족 — 기본 가중치 유지",
        }

    ridge_result = ridge_combine(snapshots)

    if ridge_result.get("cv_score", 0) > 0.05:
        return {
            "method": "ridge_purged_cv",
            "weights": ridge_result["weights"],
            "cv_score": ridge_result["cv_score"],
            "train_r2": ridge_result["train_r2"],
            "n_samples": ridge_result["n_samples"],
        }

    return {
        "method": "default",
        "weights": ridge_result.get("weights", {}),
        "cv_score": ridge_result.get("cv_score", 0),
        "note": "CV 점수 미달 — 참고용",
    }
