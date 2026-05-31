#!/usr/bin/env python3
"""
arena_asset_stats.py — ARENA Pre-Sprint 0 B축: 자산 historical 통계 측정

WHY: ARENA Sprint 1 시뮬 엔진의 GBM 파라미터 (μ, σ) + 성과 baseline + 자산 간
corr 행렬을 실 historical 로 측정해 A축 spec (docs/arena_spec_v0_2026_05_30.md)
의 GBM / Sharpe 산식에 공급한다. 사전 등록 path — 측정값 = historical estimate
(가설, N=n_days). site 노출 X (본인 only).

A축 refinement 정합:
  #1 성과 메트릭 = api/quant/risk_metrics.py (empyrical-reloaded) 직접 재사용.
     자체 재구현 금지 — divergence 0 ([[feedback_component_overlap_audit]]).
  #2 연율화 인자 자산 카테고리 분기 — 전통자산(ETF) 252 / 코인 365.

GBM 파라미터 (A축 §1.2 Itô 보정 정합):
  log return r = ln(S_t / S_{t-1})
  σ_ann      = std(r) · √periods
  μ_log_ann  = mean(r) · periods            # 로그가격 drift
  μ_gbm      = μ_log_ann + σ_ann² / 2       # SDE drift coefficient (Itô 역보정)

R_f = 0 세전 통일 ([[feedback_rf_pretax_consistency]], empyrical default rf=0).
MDD = 음수 magnitude (risk_metrics 정합, [[feedback_mdd_magnitude_display]] — UI 노출 시 양수 변환).

산출: data/arena/asset_stats_b_axis_<YYYYMMDD>.json + 콘솔 표
실행:
  python scripts/arena_asset_stats.py              # 5년 lookback
  python scripts/arena_asset_stats.py --years 3
  python scripts/arena_asset_stats.py --check      # 네트워크 X, import·설정 검증만

데이터 source: yfinance 일원 (KR ETF .KS / 미장 ETF / 레버리지·인버스 / 코인).
  pykrx fallback = KR ETF Yahoo 결측 시 (requirements 등록됨, 현 미사용 — 6/1 측정
  중 KR .KS 결측 발견 시 add).

옵션(Sprint 1.5) = 기초자산 파생이라 historical fetch 불필요 (Black-Scholes spec, A축 §5).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

KST = timezone(timedelta(hours=9))
OUTPUT_DIR = _ROOT / "data" / "arena"

# ── Sprint 1 코어 자산 (ticker, label, category, periods, multiplier, underlying) ──
#    periods    = 연율화 인자 (refinement #2): 전통자산 252 거래일 / 코인 24·7 = 365
#                 (Perplexity 2026-05-31 확인: 252/365 혼용 시 Sharpe √(365/252)≈1.20배 왜곡)
#    multiplier = 기초지수 일일 배수 (Perplexity 2026-05-31 검증). 1.0 = 비레버리지
#    underlying = 레버리지 ETF 의 1배 기초 proxy (감쇠 공식 β(β−1)/2·σ² 계산용). None = 자체
#
#    레버리지 ETF 모델링 결정 (Perplexity 2026-05-31, Avellaneda-Zhang 2010 / Balter et al. 2025 /
#    SEC DERA 2019): sim 엔진은 ① 기초지수 GBM → 일일 N배 복리 가 학술 표준. ETF 자체 σ 직접
#    GBM = 감쇠(beta slippage) 이중계상. 본 B축은 ETF 자체 σ/μ 도 측정(ground truth) 하되,
#    sim 경로 생성은 underlying 에서 파생. C축 KS test 가 측정 ETF μ vs (β·underlying − decay) 정합 검증.
ASSETS = [
    # ticker        label                          category       periods  mult  underlying
    ("069500.KS", "KODEX 200",                      "kr_etf",       252,  1.0,  None),
    ("229200.KS", "KODEX 코스닥150",                 "kr_etf",       252,  1.0,  None),
    ("SPY",       "SPDR S&P 500",                    "us_etf",       252,  1.0,  None),
    ("QQQ",       "Invesco QQQ",                     "us_etf",       252,  1.0,  None),
    ("122630.KS", "KODEX 레버리지 (2x KOSPI200)",     "kr_leverage",  252,  2.0,  "KODEX 200"),
    ("114800.KS", "KODEX 인버스 (-1x F-KOSPI200)",    "kr_inverse",   252, -1.0,  "KODEX 200"),
    ("TQQQ",      "ProShares UltraPro QQQ (3x)",     "us_leverage",  252,  3.0,  "Invesco QQQ"),
    ("SQQQ",      "ProShares UltraPro Short QQQ (-3x)", "us_inverse", 252, -3.0,  "Invesco QQQ"),
    ("BTC-USD",   "Bitcoin",                         "coin",         365,  1.0,  None),
    ("ETH-USD",   "Ethereum",                        "coin",         365,  1.0,  None),
]

# Sprint 1 sim 거래비용 모델 (왕복, Perplexity 2026-05-31). 측정 X — sim 엔진 입력 상수.
#   KR ETF 증권거래세 0% (면제) / 국내주식형 ETF 매매차익 0%. 개별주(Sprint 1.5)는 2026-01-01 거래세 0.20%.
ROUND_TRIP_COST = {
    "kr_etf":      0.0008,   # 수수료 ~0.03% + 슬리피지 ~0.05%, 거래세 0
    "kr_leverage": 0.0010,
    "kr_inverse":  0.0010,
    "us_etf":      0.0010,   # KR 증권사 수수료 + 스프레드
    "us_leverage": 0.0020,   # TQQQ ~0.15~0.23%
    "us_inverse":  0.0020,
    "coin":        0.0012,   # 업비트 taker 0.05%×2 + 슬리피지
}


def _now_kst() -> datetime:
    return datetime.now(KST)


def _r(x, nd: int = 4):
    return round(float(x), nd) if x is not None and not (isinstance(x, float) and math.isnan(x)) else None


def fetch_close(ticker: str, years: float):
    """yfinance adjusted close (auto_adjust) 시계열. 결측·multiindex 정규화."""
    import yfinance as yf

    end = _now_kst()
    start = end - timedelta(days=int(years * 365.25) + 7)
    df = yf.download(
        ticker,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )
    if df is None or len(df) == 0:
        raise ValueError("no data returned")
    close = df["Close"]
    # yfinance 신버전 = MultiIndex 컬럼 (Close, TICKER) 가능 → 1열로 축소
    if hasattr(close, "columns"):
        close = close.iloc[:, 0]
    close = close.dropna()
    if len(close) < 30:
        raise ValueError(f"insufficient history ({len(close)} rows)")
    return close


def compute_stats(close, periods: int) -> dict:
    """GBM 파라미터 + risk_metrics 재사용 성과 지표 + skew/kurtosis (C축 prep)."""
    import numpy as np

    from api.quant.risk_metrics import compute_risk_metrics

    log_ret = np.log(close / close.shift(1)).dropna()
    simple_ret = close.pct_change().dropna()

    sigma_ann = float(log_ret.std(ddof=1) * math.sqrt(periods))
    mu_log_ann = float(log_ret.mean() * periods)
    mu_gbm = mu_log_ann + 0.5 * sigma_ann ** 2  # Itô 역보정 (A축 §1.2)

    rm = compute_risk_metrics(simple_ret.to_numpy(), risk_free=0.0, periods=periods)
    if not rm.get("available"):
        raise RuntimeError("empyrical 미설치 — compute_risk_metrics unavailable")

    return {
        "n_days": int(len(log_ret)),
        "start": str(close.index[0].date()),
        "end": str(close.index[-1].date()),
        "periods_annualization": periods,
        # GBM 공급 파라미터
        "mu_gbm_annual": _r(mu_gbm, 6),
        "mu_log_annual": _r(mu_log_ann, 6),
        "sigma_annual": _r(sigma_ann, 6),
        # 성과 baseline (risk_metrics.py 재사용)
        "sharpe": _r(rm.get("sharpe")),
        "sortino": _r(rm.get("sortino")),
        "calmar": _r(rm.get("calmar")),
        "max_drawdown": _r(rm.get("max_drawdown")),  # 음수 magnitude
        # C축 (KS test / fat-tail) prep
        "skew": _r(float(log_ret.skew())),
        "excess_kurtosis": _r(float(log_ret.kurtosis())),
    }, log_ret


def run_check() -> int:
    """네트워크 없이 import·설정만 검증 (6/1 실행 전 사전 확인)."""
    ok = True
    print("=== ARENA B축 스크립트 --check ===")
    for mod in ("yfinance", "numpy", "pandas"):
        try:
            __import__(mod)
            print(f"  [OK] import {mod}")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"  [FAIL] import {mod}: {e}", file=sys.stderr)
    try:
        from api.quant.risk_metrics import compute_risk_metrics  # noqa: F401
        import empyrical  # noqa: F401
        print("  [OK] api.quant.risk_metrics + empyrical")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"  [FAIL] risk_metrics/empyrical: {e}", file=sys.stderr)
    print(f"\n자산 universe ({len(ASSETS)}개):")
    for ticker, label, cat, periods, mult, under in ASSETS:
        u = f" ← {under}" if under else ""
        print(f"  {ticker:11s} {label:36s} [{cat:12s}] periods={periods} {mult:+.0f}x{u}")
    print(f"\n출력 경로: {OUTPUT_DIR}/asset_stats_b_axis_<YYYYMMDD>.json")
    print("결과:", "READY" if ok else "의존성 결함 — requirements 설치 필요")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="ARENA B축 자산 historical 통계 측정")
    ap.add_argument("--years", type=float, default=5.0, help="lookback (기본 5년)")
    ap.add_argument("--output", default=None, help="출력 경로 override")
    ap.add_argument("--check", action="store_true", help="네트워크 X, import·설정 검증만")
    args = ap.parse_args()

    if args.check:
        return run_check()

    import pandas as pd

    results: dict = {}
    ret_series: dict = {}
    failures: list = []

    for ticker, label, category, periods, mult, under in ASSETS:
        try:
            close = fetch_close(ticker, args.years)
            stats, log_ret = compute_stats(close, periods)
            stats["ticker"] = ticker
            stats["category"] = category
            stats["multiplier"] = mult
            stats["underlying"] = under
            stats["round_trip_cost"] = ROUND_TRIP_COST.get(category)
            results[label] = stats
            ret_series[label] = log_ret
            print(
                f"[OK]   {label:34s} N={stats['n_days']:<5d} "
                f"μ_gbm={stats['mu_gbm_annual']:+.3f} σ={stats['sigma_annual']:.3f} "
                f"Sharpe={stats['sharpe']} MDD={stats['max_drawdown']}"
            )
        except Exception as e:  # noqa: BLE001
            failures.append({"ticker": ticker, "label": label, "error": str(e)})
            print(f"[FAIL] {label}: {e}", file=sys.stderr)

    # 레버리지 ETF 변동성 감쇠 (Perplexity 2026-05-31, β(β−1)/2·σ² + GBM 파생 정합 검증)
    #   expected_decay  = underlying σ 기반 이론 감쇠 (연)
    #   gbm_implied_mu  = β·μ_underlying − decay  (sim ① 방식 예측)
    #   measured_vs_implied = 측정 ETF μ_gbm − gbm_implied_mu  (C축 KS test prep, |오차| 클수록 GBM 가정 이탈)
    for label, st in results.items():
        beta = st.get("multiplier")
        under = st.get("underlying")
        if beta is None or abs(beta) == 1.0 or not under or under not in results:
            continue
        u = results[under]
        sig_u = u.get("sigma_annual")
        mu_u = u.get("mu_gbm_annual")
        if sig_u is None or mu_u is None:
            continue
        decay = beta * (beta - 1.0) / 2.0 * sig_u ** 2
        implied_mu = beta * mu_u - decay
        st["expected_decay_annual"] = _r(decay, 5)
        st["gbm_implied_mu"] = _r(implied_mu, 5)
        st["measured_vs_implied"] = _r((st.get("mu_gbm_annual") or 0) - implied_mu, 5)

    # corr 행렬 (log return, 공통 거래일 inner-join — 코인/ETF 캘린더 mismatch 정규화)
    correlation: dict = {}
    if len(ret_series) >= 2:
        cdf = pd.DataFrame(ret_series).dropna()
        correlation = json.loads(cdf.corr().round(3).to_json())
        correlation["_n_common_days"] = int(len(cdf))

    payload = {
        "collected_at": _now_kst().isoformat(),
        "source": "yfinance",
        "lookback_years": args.years,
        "axis": "B (asset historical stats)",
        "spec_ref": "docs/arena_spec_v0_2026_05_30.md",
        "note": (
            "측정값 = historical estimate (가설, N=n_days). site 노출 X (본인 only). "
            "MDD = 음수 magnitude. 연율화 = category 분기 (ETF 252 / 코인 365). "
            "레버리지 ETF: ETF 자체 σ/μ 측정 + 이론 감쇠 병기 — sim 경로는 underlying GBM 파생 (Perplexity 2026-05-31)."
        ),
        "round_trip_cost_model": ROUND_TRIP_COST,
        "assets": results,
        "correlation_log_returns": correlation,
        "failures": failures,
    }

    out = Path(args.output) if args.output else OUTPUT_DIR / f"asset_stats_b_axis_{_now_kst():%Y%m%d}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n측정 완료: {len(results)}/{len(ASSETS)} 성공, {len(failures)} 실패")
    print(f"산출: {out}")
    if failures:
        print(f"실패 목록: {[f['ticker'] for f in failures]}", file=sys.stderr)

    # 전부 실패 = 데이터 source 결함 → exit 1 (cron/audit detect)
    return 1 if not results else 0


if __name__ == "__main__":
    raise SystemExit(main())
