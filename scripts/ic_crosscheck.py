"""ic_crosscheck — self IC 엔진 ↔ alphalens 교차검증 (D9 step 2).

목적 (2026-06-14): 우리가 자체 산출하는 IC(api/quant/alpha/ic_backtest.cross_sectional_ic +
api/intelligence/ic_stats.newey_west_tstat)가 표준 라이브러리(alphalens-reloaded)와 **같은
값을 내는지** 대조한다. 둘이 수렴하면 자체 IC 파이프라인을 신뢰할 수 있고(N=252 게이트
전 사전 신뢰 확보), 발산하면 자체 산식에 구현 버그가 있다는 뜻이다.

설계 원칙 (필수흡수 검증 캐비엇 정합):
  · alphalens = **cross-check 전용**. zipline/vectorbt 신규 의존성 도입 금지.
  · **on-demand 스크립트** — cron 미배선(cron CI 에 alphalens 무거운 의존성 안 들임).
    alphalens 는 requirements.txt 아닌 requirements-research.txt (별도). 미설치 시 graceful.
  · **source-of-truth = self ic_stats Newey-West**. alphalens 는 대조 레퍼런스일 뿐,
    어떤 결정도 alphalens 의 naive p-value 로 내리지 않는다(중첩수익 p-value 낙관 편향).
  · 순환 정당화 차단 — 이 도구는 "다른 미검증 자체 알파를 정당화하는 자"가 아니라
    "자체 IC 산식이 표준과 일치함을 확인하는 자"다. 결정론적 팩터(가격기반 모멘텀)로
    검증하므로 brain 점수에 의존하지 않는다.

실행: python scripts/ic_crosscheck.py [--factor momentum] [--horizon 5] [--tickers 200]
출력: 콘솔 + data/metadata/ic_crosscheck.jsonl (source 태그 + divergence).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LAKE_PATH = os.path.expanduser("~/VERITY_data_lake/kr_prices.duckdb")
OUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "metadata", "ic_crosscheck.jsonl",
)

# self IC ↔ alphalens 수렴 허용오차 (엔지니어링 tolerance, 자의 — trial_log 대상).
# 두 엔진 모두 Spearman rank IC라 동률처리·결측 차이만큼만 벌어져야 함.
DIVERGENCE_TOL = 0.02


def _load_panel(n_tickers: int, lookback_days: int) -> pd.DataFrame:
    """가격레이크 → close 가격 wide DataFrame (index=date, columns=ticker).

    유동성 상위 n_tickers (최근 평균 거래대금) 만 — 횡단면 IC 안정 + 속도.
    """
    import duckdb

    con = duckdb.connect(LAKE_PATH, read_only=True)
    cutoff = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    # 유동성 상위 종목 선정
    top = con.execute(
        """
        SELECT ticker FROM ohlcv WHERE date >= ?
        GROUP BY ticker
        HAVING COUNT(*) > 200
        ORDER BY AVG(value) DESC LIMIT ?
        """,
        [cutoff, n_tickers],
    ).fetchall()
    tickers = [t[0] for t in top]
    if not tickers:
        con.close()
        raise RuntimeError("가격레이크에서 종목 0 — lookback/경로 확인")
    ph = ",".join(["?"] * len(tickers))
    rows = con.execute(
        f"SELECT date, ticker, close FROM ohlcv WHERE date >= ? AND ticker IN ({ph}) ORDER BY date",
        [cutoff] + tickers,
    ).fetchdf()
    con.close()
    panel = rows.pivot(index="date", columns="ticker", values="close").astype(float)
    panel.index = pd.to_datetime(panel.index)
    return panel


def _compute_factor(close: pd.DataFrame, factor: str, lookback: int) -> pd.DataFrame:
    """결정론적 가격기반 팩터 (date×ticker)."""
    if factor == "momentum":
        return close.pct_change(lookback)          # N일 모멘텀
    if factor == "reversal":
        return -close.pct_change(lookback)         # 단기 역전
    raise ValueError(f"미지원 factor: {factor}")


def _self_ic_series(factor: pd.DataFrame, close: pd.DataFrame, horizon: int) -> list:
    """self cross_sectional_ic 로 일별 횡단면 IC 시계열."""
    from api.quant.alpha.ic_backtest import cross_sectional_ic

    fwd = close.pct_change(horizon).shift(-horizon)   # t 에서 본 h일 forward return
    ics = []
    for dt in factor.index:
        if dt not in fwd.index:
            continue
        ic = cross_sectional_ic(factor.loc[dt], fwd.loc[dt])
        if ic is not None:
            ics.append(ic)
    return ics


def _alphalens_mean_ic(factor: pd.DataFrame, close: pd.DataFrame, horizon: int):
    """alphalens 표준 IC (동일 팩터/가격). 미설치/실패 시 None."""
    try:
        from alphalens.utils import get_clean_factor_and_forward_returns
        from alphalens.performance import factor_information_coefficient
    except ImportError:
        return None, "alphalens 미설치 (pip install -r requirements-research.txt)"
    try:
        # alphalens factor = MultiIndex (date, asset) Series
        fac_stacked = factor.stack()
        fac_stacked.index = fac_stacked.index.set_names(["date", "asset"])
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fd = get_clean_factor_and_forward_returns(
                fac_stacked, close, periods=(horizon,), quantiles=5, max_loss=0.5,
            )
            ic = factor_information_coefficient(fd)
        col = f"{horizon}D"
        if col not in ic.columns:
            col = ic.columns[0]
        return float(ic[col].mean()), None
    except Exception as e:  # noqa: BLE001
        return None, f"alphalens 산출 실패: {str(e)[:100]}"


def run(factor: str = "momentum", horizon: int = 5, n_tickers: int = 200,
        lookback_days: int = 730, factor_lookback: int = 20) -> dict:
    from api.intelligence.ic_stats import newey_west_tstat

    close = _load_panel(n_tickers, lookback_days)
    fac = _compute_factor(close, factor, factor_lookback)

    self_ics = _self_ic_series(fac, close, horizon)
    nw = newey_west_tstat(self_ics, horizon_days=horizon)
    self_mean = nw.get("mean_ic")

    al_mean, al_err = _alphalens_mean_ic(fac, close, horizon)

    divergence = None
    verdict = "SELF_ONLY"
    if al_mean is not None and self_mean is not None:
        divergence = abs(self_mean - al_mean)
        verdict = "CONVERGE" if divergence < DIVERGENCE_TOL else "DIVERGE"

    return {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "factor": factor,
        "factor_lookback": factor_lookback,
        "horizon": horizon,
        "n_tickers": n_tickers,
        "panel_dates": int(len(close)),
        "self_ic_mean": round(self_mean, 5) if self_mean is not None else None,
        "self_nw_tstat": round(nw["nw_tstat"], 4) if nw.get("nw_tstat") is not None else None,
        "self_n_periods": nw.get("T"),
        "alphalens_ic_mean": round(al_mean, 5) if al_mean is not None else None,
        "alphalens_error": al_err,
        "divergence": round(divergence, 5) if divergence is not None else None,
        "tolerance": DIVERGENCE_TOL,
        "verdict": verdict,
        "source_of_truth": "self ic_stats newey_west (alphalens=대조 only)",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--factor", default="momentum", choices=["momentum", "reversal"])
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--tickers", type=int, default=200)
    ap.add_argument("--lookback-days", type=int, default=730)
    ap.add_argument("--factor-lookback", type=int, default=20)
    ap.add_argument("--no-log", action="store_true")
    a = ap.parse_args()

    r = run(a.factor, a.horizon, a.tickers, a.lookback_days, a.factor_lookback)

    print(f"[ic_crosscheck] factor={r['factor']}({r['factor_lookback']}d) "
          f"horizon={r['horizon']}d tickers={r['n_tickers']} dates={r['panel_dates']}")
    print(f"  self    IC mean = {r['self_ic_mean']}  (NW t={r['self_nw_tstat']}, N={r['self_n_periods']})")
    print(f"  alphalens IC mean = {r['alphalens_ic_mean']}  {r['alphalens_error'] or ''}")
    print(f"  divergence = {r['divergence']} (tol {r['tolerance']}) → {r['verdict']}")

    if not a.no_log:
        try:
            os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
            with open(OUT_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"  → {OUT_PATH}")
        except Exception as e:  # noqa: BLE001
            print(f"  로그 실패(무시): {e}")

    # DIVERGE = self 산식과 표준 불일치 = 조사 필요 (exit 1). 단 alphalens 부재는 정상(0).
    return 1 if r["verdict"] == "DIVERGE" else 0


if __name__ == "__main__":
    sys.exit(main())
