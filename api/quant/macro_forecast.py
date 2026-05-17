"""
macro_forecast — statsforecast (Nixtla) wrapper. macro 시계열 단기 forecast.

audit (general-purpose agent, 2026-05-17) 결과:
- statsforecast: AutoARIMA/AutoETS/MSTL — numpy/numba 의존만, 가벼움 (pmdarima 100x)
- 자체 산식 X (표준 통계 모델, Brain 보조 input)
- 도입 가치: macro_snapshot 4지표 1~5일 forecast → EstateMacroBridge narrative input

RULE 7 정합:
- 출처 명시 의무 — "(가설 / statsforecast AutoARIMA, N=관측일수)"
- Brain v5 의 자기 산식 input X (보조 신호만, override X)

wiring: 현재 dead code. macro_snapshot 호출자 wire = 후속 sprint.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional, Literal
import warnings

try:
    import pandas as pd
    import numpy as np
    from statsforecast import StatsForecast
    from statsforecast.models import AutoARIMA, AutoETS, Naive
    _SF_AVAILABLE = True
except ImportError:
    _SF_AVAILABLE = False


MODEL_REGISTRY = {
    "auto_arima": lambda: AutoARIMA(season_length=1, max_p=5, max_q=5),
    "auto_ets": lambda: AutoETS(season_length=1, model="ZZN"),  # ZZN = non-seasonal
    "naive": lambda: Naive(),
}


def forecast_series(
    series_id: str,
    values: list[float],
    dates: Optional[list[str]] = None,
    horizon: int = 5,
    model: Literal["auto_arima", "auto_ets", "naive"] = "auto_arima",
    level: Optional[list[int]] = None,
) -> dict:
    """단일 시계열 → horizon 일 forecast.

    Args:
        series_id: 시계열 식별자 (예: "DGS10", "VIX", "USD_KRW")
        values: 과거 시계열 값 list (시간순, 최소 10개 권장)
        dates: ISO date 문자열 list (생략 시 days 역산)
        horizon: 예측 일수 (default 5)
        model: "auto_arima" (정확), "auto_ets" (빠름), "naive" (baseline)
        level: confidence interval levels (예: [80, 95])

    Returns:
        {
            "available": bool,
            "series_id": str,
            "model": str,
            "n_observations": int,
            "horizon": int,
            "forecast": [{"ds": "YYYY-MM-DD", "y": float, "lo_95": float|None, "hi_95": float|None}, ...],
            "note": str,
        }
    """
    if not _SF_AVAILABLE:
        return {"available": False, "series_id": series_id, "note": "statsforecast 미설치"}

    if not values or len(values) < 5:
        return {
            "available": True,
            "series_id": series_id,
            "model": model,
            "n_observations": len(values or []),
            "horizon": horizon,
            "forecast": [],
            "note": f"데이터 부족 (N={len(values or [])}) — 최소 5건 필요. 통계 무의미.",
        }

    # ds 생성 (없으면 오늘부터 역산)
    if dates is None:
        today = datetime.now().date()
        dates = [(today - timedelta(days=len(values) - 1 - i)).strftime("%Y-%m-%d") for i in range(len(values))]

    # statsforecast DataFrame 형식: [unique_id, ds, y]
    df = pd.DataFrame({
        "unique_id": [series_id] * len(values),
        "ds": pd.to_datetime(dates),
        "y": values,
    })

    model_obj = MODEL_REGISTRY.get(model, MODEL_REGISTRY["auto_arima"])()
    sf = StatsForecast(models=[model_obj], freq="D", n_jobs=1)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sf.fit(df)
            fcst_df = sf.predict(h=horizon, level=level or [])
    except Exception as e:
        return {
            "available": True,
            "series_id": series_id,
            "model": model,
            "n_observations": len(values),
            "horizon": horizon,
            "forecast": [],
            "note": f"forecast 실패: {e}",
        }

    # statsforecast 출력 컬럼명 = model class name (예: "AutoARIMA")
    model_col = [c for c in fcst_df.columns if c not in ("unique_id", "ds")][0].split("-")[0]

    out = []
    for _, row in fcst_df.iterrows():
        rec = {"ds": row["ds"].strftime("%Y-%m-%d"), "y": float(row[model_col])}
        if level:
            for lv in level:
                lo_col = f"{model_col}-lo-{lv}"
                hi_col = f"{model_col}-hi-{lv}"
                if lo_col in fcst_df.columns:
                    rec[f"lo_{lv}"] = float(row[lo_col])
                if hi_col in fcst_df.columns:
                    rec[f"hi_{lv}"] = float(row[hi_col])
        out.append(rec)

    n_label = f"N={len(values)}일"
    if len(values) < 30:
        confidence = f"(가설 / {model}, {n_label} — 통계 무의미)"
    elif len(values) < 100:
        confidence = f"(가설 / {model}, {n_label} — 예비 결과)"
    else:
        confidence = f"(가설 / {model}, {n_label})"

    return {
        "available": True,
        "series_id": series_id,
        "model": model,
        "n_observations": len(values),
        "horizon": horizon,
        "forecast": out,
        "note": confidence,
    }


def forecast_macro_snapshot(macro_snapshot: dict, horizon: int = 5,
                              series_keys: Optional[list[str]] = None) -> dict:
    """macro_snapshot.json 의 여러 시계열 일괄 forecast.

    Args:
        macro_snapshot: {series_id: {"history": [...], "dates": [...]}}
        horizon: 예측 일수
        series_keys: 특정 series 만 (None = 모두)

    Returns:
        {series_id: forecast_result}
    """
    if not _SF_AVAILABLE:
        return {"_available": False, "_note": "statsforecast 미설치"}

    results = {}
    keys = series_keys or list(macro_snapshot.keys())
    for sid in keys:
        entry = macro_snapshot.get(sid, {})
        history = entry.get("history") or entry.get("values") or []
        dates = entry.get("dates")
        if not history:
            continue
        results[sid] = forecast_series(sid, history, dates, horizon=horizon)
    results["_available"] = True
    return results
