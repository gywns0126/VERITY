"""
Historical Backfill Replay — VERITY Brain 의 과거 검증.

목적
----
brain_score 메커니즘을 historical 가격 데이터로 재구성하여
"60일 데이터 누적 대기" 없이 즉시 컴포넌트별 IC 측정.
brain_history.py 가 prospectively 채울 시간을 backfill 로 단축.

스코프 한계 (정직한 고지)
------------------------
- 가격: yfinance (KR + US, 무료, 키 불필요)
- 펀더멘털: DART API (한국, OPTIONAL) — DART_API_KEY 없으면 자동 스킵.
            * 본 replay 는 DART 없이도 동작 — 펀더멘털 컴포넌트는 'unavailable' 처리.
- 센티먼트: 시계열 뉴스/X/소셜 데이터 historical 재현 불가 → 50 중립으로 고정.
            따라서 본 replay 는 'sentiment-neutralized fact-only validation'.
            full brain_score 의 30%(sentiment) 는 noise. 70%(fact) 의 IC 만 측정.
- 컨센서스/예측 (LSTM)/AI verdict: 과거 시점 모델 스냅샷 부재 → 평균값으로 대체.

따라서 본 replay 가 검증하는 것은:
    * 가격 기반 technical / momentum 팩터의 forward 30d 수익률 IC
    * grade 분포의 regime 적합성 (COVID 크래시에 STRONG_BUY 가 폭증하지 않는가?)
    * 컴포넌트별 alpha 기여도 — IC < 0.03 이면 noise → 제거 후보 표시

본 replay 가 검증하지 못하는 것은:
    * 센티먼트 컴포넌트 (news/x/social) — 데이터 부재
    * 펀더멘털 cross-section IC (DART 미연결 시) — 펀더멘털 정적값 사용
    * VCI bonus / red_flag / overrides — 단순화된 grade 산출만 수행

사용
----
  python scripts/historical_replay.py                    # 기본: smoke (5종목 × 1년)
  python scripts/historical_replay.py --smoke            # 명시적 smoke
  python scripts/historical_replay.py --full             # 풀 (30종목 × 2020~현재)
  python scripts/historical_replay.py --tickers AAPL,MSFT --start 2022-01-01

결과
----
  data/backfill_replay_result.json   — replay 데이터 + grade 분포 + regime 결과
  data/component_ic_result.json      — 컴포넌트별 Spearman/Pearson IC + 제거 후보
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

# ─── 상수 ───────────────────────────────────────────────────

DEFAULT_SMOKE_TICKERS = ["AAPL", "MSFT", "JPM", "XOM", "BAC"]  # US large cap, long history

# survivorship bias 완화 — 망한 종목/페니주 포함 universe
DEFAULT_FULL_TICKERS = [
    # US 대형주 30 (post-COVID/AI 강세 — 모멘텀 알파 측정)
    "AAPL", "MSFT", "JPM", "XOM", "BAC", "NVDA", "AMZN", "META", "WMT", "BRK-B",
    "GS", "MS", "PFE", "JNJ", "CVX", "NEE", "AMT", "PLD", "MCO", "COST",
    "HD", "LOW", "MCD", "SBUX", "NKE", "TSLA", "DIS", "NFLX", "V", "MA",
    # 소형주/페니주/파산주 15 (진짜 AVOID 후보 — survivorship 보정)
    # 일부는 BK/delisting (BBBY 2023, RIDE 2023, WISH 2024, PRTY 2023, EXPR 2024)
    # yfinance 는 delisting 직전까지 historical 반환
    "GME", "AMC", "BBBY", "RIDE", "NKLA", "SPCE", "WISH", "CLOV",
    "RKT", "UWMC", "PRTY", "EXPR", "TLRY", "SNDL", "ACB",
]

DEFAULT_START_FULL = "2007-01-01"  # 2008 GFC 포함
DEFAULT_START_SMOKE = "2023-01-01"
EVAL_FREQ_DAYS = 5      # eval date 간격 (5 영업일 = 주 1회)
FORWARD_HOLD = 30       # 후속 수익률 평가 기간 (영업일)

# Regime stress test 정의 (universe 확장 후 6개)
REGIMES = {
    "gfc_2008": {
        "start": "2008-09-01", "end": "2009-03-31",
        "description": "GFC (Lehman → 바닥) — STRONG_BUY 비율 평시 절반 미만이어야 PASS",
        "metric": "strong_buy_pct_vs_baseline",
    },
    "us_credit_downgrade_2011": {
        "start": "2011-08-01", "end": "2011-10-31",
        "description": "S&P 美 신용등급 강등 — 평균 brain_score 가 2010 대비 하락해야 PASS",
        "metric": "avg_brain_score_vs_2010",
    },
    "trade_war_2018": {
        "start": "2018-10-01", "end": "2018-12-31",
        "description": "Q4 2018 무역전쟁 급락 — 평균 brain_score 가 Q3 2018 대비 하락해야 PASS",
        "metric": "avg_brain_score_vs_q3_2018",
    },
    "covid_crash": {
        "start": "2020-02-20", "end": "2020-03-23",
        "description": "COVID 시장 크래시 — STRONG_BUY 가 평시 대비 절반 미만이어야 PASS",
        "metric": "strong_buy_pct_vs_baseline",
    },
    "inflation_2022": {
        "start": "2022-01-01", "end": "2022-12-31",
        "description": "2022 인플레 급등기 — 평균 brain_score 가 2021 대비 하락해야 PASS",
        "metric": "avg_brain_score_vs_2021",
    },
    "svb_collapse": {
        "start": "2023-03-06", "end": "2023-03-15",
        "description": "SVB 파산 — 금융주(BAC,JPM) brain_score 5일 윈도우 비교",
        "metric": "financial_sector_score_drop",
        "tickers": ["BAC", "JPM"],
    },
}

# Grade 임계 (verity_brain.py 와 동일).
# Brain Audit §8: AVOID 는 has_critical / macro panic 에만 발동 (verity_brain §8 참조).
# replay 는 red_flags 미모델 → AVOID 는 발동 불가 → CAUTION 최하위 등급으로 대체.
_GRADE_THRESHOLDS = [("STRONG_BUY", 75), ("BUY", 60), ("WATCH", 45),
                     ("CAUTION", 0)]

# Component IC 노이즈 임계
IC_NOISE_THRESHOLD = 0.03


# ─── 데이터 수집 ─────────────────────────────────────────────


def fetch_price_history(ticker: str, start: str, end: str,
                        max_retries: int = 2) -> Optional[pd.DataFrame]:
    """yfinance 로 일봉 OHLCV. 재시도 포함."""
    for attempt in range(max_retries):
        try:
            t = yf.Ticker(ticker)
            df = t.history(start=start, end=end, auto_adjust=True)
            if df.empty or len(df) < 30:
                return None
            df.index = pd.to_datetime(df.index).tz_localize(None)
            return df
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"  [WARN] {ticker} fetch failed: {e}", file=sys.stderr)
                return None
            time.sleep(1.0)
    return None


# ─── 컴포넌트 산출 ─────────────────────────────────────────


def compute_factors_at(df: pd.DataFrame, eval_idx: int) -> Optional[Dict[str, float]]:
    """eval_idx (날짜 정수 인덱스) 시점의 6개 fact-only 컴포넌트.

    모두 가격으로부터 계산 — historical 재현 가능.
    Returns: dict 또는 None (데이터 부족 시).
    """
    if eval_idx < 200:  # 200일 MA 위해 최소 데이터
        return None
    close = df["Close"]
    cur = float(close.iloc[eval_idx])

    # 1. momentum_3m: 60 영업일 전 대비
    if eval_idx >= 60:
        m3 = (cur / float(close.iloc[eval_idx - 60]) - 1) * 100
    else:
        return None

    # 2. momentum_1m: 20 영업일 전 대비
    m1 = (cur / float(close.iloc[eval_idx - 20]) - 1) * 100

    # 3. RSI(14)
    delta = close.iloc[eval_idx - 14:eval_idx + 1].diff().dropna()
    gain = delta.where(delta > 0, 0).mean()
    loss = -delta.where(delta < 0, 0).mean()
    if loss == 0:
        rsi = 100.0
    else:
        rs = gain / loss
        rsi = 100 - 100 / (1 + rs)

    # 4. price_to_ma200 (gap %)
    ma200 = float(close.iloc[eval_idx - 200:eval_idx + 1].mean())
    px_to_ma = (cur / ma200 - 1) * 100 if ma200 > 0 else 0.0

    # 5. volatility_20d (annualized %)
    rets = close.iloc[eval_idx - 20:eval_idx + 1].pct_change().dropna()
    vol = float(rets.std() * np.sqrt(252) * 100) if len(rets) > 1 else 0.0

    # 6. volume_ratio_20d (현재 거래량 / 20일 평균)
    vol_avg = float(df["Volume"].iloc[eval_idx - 20:eval_idx].mean())
    cur_vol = float(df["Volume"].iloc[eval_idx])
    vol_ratio = cur_vol / vol_avg if vol_avg > 0 else 1.0

    return {
        "momentum_3m": float(m3),
        "momentum_1m": float(m1),
        "rsi_14": float(rsi),
        "price_to_ma200_pct": float(px_to_ma),
        "volatility_20d_ann": float(vol),
        "volume_ratio_20d": float(vol_ratio),
    }


def factors_to_brain_score(factors: Dict[str, float],
                           regime_panic: bool = False) -> Tuple[float, str]:
    """6개 컴포넌트 → 단순화된 brain_score (sentiment=50 중립).

    v2 (Backfill IC validated, 2020~현재 1355행 검증 후 재설계)
    -------------------------------------------------------------
    측정된 IC (forward 30d 수익률 상관):
      rsi_14:              -0.05  → mean-reversion (높을수록 감점)
      price_to_ma200_pct:  -0.06  → mean-reversion (위로 멀수록 감점)
      momentum_1m:         -0.03  → mean-reversion (강할수록 감점)
      volatility_20d_ann:  +0.11  → low-vol premium (낮을수록 가산)
      momentum_3m:         +0.025 → noise → 가중치 0
      volume_ratio_20d:    +0.022 → noise → 가중치 0

    가중치 (|IC| 비례 정규화, sum=1.0):
      vol_20d 0.44, ma200 0.24, rsi 0.20, mom_1m 0.12

    regime_panic=True (VIX>30):
      mean-reversion 비활성 → fact=50 중립 사용.
      이유: 위기장에서 가격 ↓ → MA gap 음수 → 점수 ↑ 가 거시 신호와 충돌.
    """
    def _clip(x): return max(0.0, min(100.0, x))

    if regime_panic:
        # 위기장: technical mean-reversion 비활성 → 중립 fact_score
        fact_score = 50.0
    else:
        rsi = factors["rsi_14"]
        s_rsi = _clip(100 - rsi)
        px = factors["price_to_ma200_pct"]
        s_px = _clip(50 - px * 1.67)
        m1 = factors["momentum_1m"]
        s_m1 = _clip(50 - m1 * 5)
        vol = factors["volatility_20d_ann"]
        s_vol = _clip(100 - max(0, vol - 20) * 2.5)
        # noise (m3, vr) 가중치 0 — 미사용

        fact_score = (s_vol * 0.44 + s_px * 0.24 + s_rsi * 0.20 + s_m1 * 0.12)

    sent_score = 50.0  # 중립 가정 (historical 재현 불가)
    brain_score = fact_score * 0.7 + sent_score * 0.3

    return float(brain_score), _score_to_grade(brain_score)


def _score_to_grade(score: float) -> str:
    for g, thr in _GRADE_THRESHOLDS:
        if score >= thr:
            return g
    return "CAUTION"  # Brain Audit §8: AVOID 미발동 (red_flags 미모델)


# ─── 단일 종목 replay ──────────────────────────────────────


VIX_PANIC_THRESHOLD = 30.0


def fetch_vix_series(start: str, end: str) -> Optional[pd.Series]:
    """^VIX 일별 종가 (regime gate 용)."""
    df = fetch_price_history("^VIX", start, end)
    if df is None:
        return None
    return df["Close"].astype(float)


def _vix_at(vix_series: Optional[pd.Series], date_ts) -> float:
    """date_ts (Timestamp) 의 VIX. 시리즈 부재 시 0 (panic 미발동)."""
    if vix_series is None:
        return 0.0
    try:
        # 정확히 일치하는 날짜가 없을 수 있음 — asof 사용 (직전 영업일 값)
        v = vix_series.asof(date_ts)
        return float(v) if pd.notna(v) else 0.0
    except Exception:
        return 0.0


def replay_ticker(ticker: str, start: str, end: str,
                  vix_series: Optional[pd.Series] = None) -> List[Dict[str, Any]]:
    """ticker 의 날짜별 (factors, brain_score, forward_30d_return) 시계열.

    vix_series 가 제공되면 VIX>30 일자에 regime_panic=True 로 mean-reversion 비활성.
    """
    df = fetch_price_history(ticker, start, end)
    if df is None:
        return []

    out: List[Dict[str, Any]] = []
    n = len(df)
    for i in range(200, n - FORWARD_HOLD, EVAL_FREQ_DAYS):
        factors = compute_factors_at(df, i)
        if factors is None:
            continue
        date_ts = df.index[i]
        vix_val = _vix_at(vix_series, date_ts)
        regime_panic = vix_val > VIX_PANIC_THRESHOLD
        score, grade = factors_to_brain_score(factors, regime_panic=regime_panic)
        cur_p = float(df["Close"].iloc[i])
        fut_p = float(df["Close"].iloc[i + FORWARD_HOLD])
        fwd_ret = (fut_p - cur_p) / cur_p * 100 if cur_p > 0 else None
        out.append({
            "ticker": ticker,
            "date": date_ts.strftime("%Y-%m-%d"),
            "factors": factors,
            "vix": round(vix_val, 2),
            "regime_panic": regime_panic,
            "brain_score": round(score, 2),
            "grade": grade,
            "price": round(cur_p, 4),
            "forward_30d_price": round(fut_p, 4),
            "forward_30d_return_pct": round(fwd_ret, 3) if fwd_ret is not None else None,
        })
    return out


# ─── Component IC 측정 ────────────────────────────────────


def compute_component_ic(replay_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """각 컴포넌트별 forward 30d 수익률과의 Spearman + Pearson IC."""
    # DataFrame 변환
    rows = []
    for r in replay_data:
        if r["forward_30d_return_pct"] is None:
            continue
        row = {"forward_ret": r["forward_30d_return_pct"]}
        row.update(r["factors"])
        rows.append(row)
    if len(rows) < 30:
        return {"status": "insufficient_data", "n": len(rows)}

    df = pd.DataFrame(rows)
    component_cols = [c for c in df.columns if c != "forward_ret"]

    ic_results = {}
    for col in component_cols:
        x = df[col].astype(float)
        y = df["forward_ret"].astype(float)
        # Pearson
        try:
            pearson = float(x.corr(y, method="pearson"))
        except Exception:
            pearson = None
        # Spearman (robust to outliers)
        try:
            spearman = float(x.corr(y, method="spearman"))
        except Exception:
            spearman = None
        is_noise = (
            (pearson is None or abs(pearson) < IC_NOISE_THRESHOLD) and
            (spearman is None or abs(spearman) < IC_NOISE_THRESHOLD)
        )
        ic_results[col] = {
            "pearson_ic": round(pearson, 4) if pearson is not None else None,
            "spearman_ic": round(spearman, 4) if spearman is not None else None,
            "n": len(df),
            "is_noise_candidate": is_noise,
        }
    return {
        "status": "ok",
        "n": len(df),
        "components": ic_results,
        "noise_candidates": [c for c, v in ic_results.items() if v["is_noise_candidate"]],
        "noise_threshold": IC_NOISE_THRESHOLD,
    }


# ─── Regime stress tests ───────────────────────────────────


def _filter_by_date_range(data: List[Dict[str, Any]], start: str, end: str,
                          tickers: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    out = []
    for r in data:
        if not (start <= r["date"] <= end):
            continue
        if tickers and r["ticker"] not in tickers:
            continue
        out.append(r)
    return out


def _grade_distribution(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    if not rows:
        return {}
    from collections import Counter
    c = Counter(r["grade"] for r in rows)
    n = len(rows)
    return {g: round(c.get(g, 0) / n * 100, 1) for g in
            ["STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID"]}


def _strong_buy_pct_test(replay_data, regime_key, results, baseline_dist):
    """STRONG_BUY 비율이 평시 절반 미만인지 (panic 인식 검증)."""
    r = REGIMES[regime_key]
    rows = _filter_by_date_range(replay_data, r["start"], r["end"])
    dist = _grade_distribution(rows)
    sb = dist.get("STRONG_BUY", 0)
    base_sb = baseline_dist.get("STRONG_BUY", 0)
    pass_ = sb < (base_sb / 2) if base_sb > 0 else sb < 5
    results[regime_key] = {
        "description": r["description"],
        "n": len(rows),
        "grade_distribution_pct": dist,
        "regime_strong_buy_pct": sb,
        "baseline_strong_buy_pct": base_sb,
        "verdict": "PASS" if pass_ else ("INSUFFICIENT_DATA" if len(rows) < 10 else "FAIL"),
    }


def _avg_score_vs_period_test(replay_data, regime_key, ref_start, ref_end,
                               ref_label, results):
    """regime 평균 brain_score 가 ref 기간보다 낮은지."""
    r = REGIMES[regime_key]
    rows_regime = _filter_by_date_range(replay_data, r["start"], r["end"])
    rows_ref = _filter_by_date_range(replay_data, ref_start, ref_end)
    avg_regime = float(np.mean([x["brain_score"] for x in rows_regime])) if rows_regime else None
    avg_ref = float(np.mean([x["brain_score"] for x in rows_ref])) if rows_ref else None
    if avg_regime is not None and avg_ref is not None:
        pass_ = avg_regime < avg_ref
        verdict = "PASS" if pass_ else "FAIL"
    else:
        verdict = "INSUFFICIENT_DATA"
    results[regime_key] = {
        "description": r["description"],
        "ref_label": ref_label,
        "n_regime": len(rows_regime),
        "n_ref": len(rows_ref),
        "avg_brain_score_regime": round(avg_regime, 2) if avg_regime is not None else None,
        "avg_brain_score_ref": round(avg_ref, 2) if avg_ref is not None else None,
        "verdict": verdict,
    }


def regime_stress_test(replay_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """6개 regime 이진 검증 (GFC 2008 / 2011 강등 / 2018 무역 / COVID / 2022 / SVB)."""
    results: Dict[str, Any] = {}

    baseline_rows = replay_data
    baseline_dist = _grade_distribution(baseline_rows)
    baseline_avg_score = float(np.mean([r["brain_score"] for r in baseline_rows])) if baseline_rows else 0
    results["_baseline"] = {
        "n": len(baseline_rows),
        "avg_brain_score": round(baseline_avg_score, 2),
        "grade_distribution_pct": baseline_dist,
    }

    # 1. GFC 2008-09~2009-03: STRONG_BUY 평시 절반 미만
    _strong_buy_pct_test(replay_data, "gfc_2008", results, baseline_dist)

    # 2. 2011 美 신용등급 강등: 2011-08~10 평균 < 2010 평균
    _avg_score_vs_period_test(replay_data, "us_credit_downgrade_2011",
                               "2010-01-01", "2010-12-31", "2010", results)

    # 3. 2018 Q4 무역전쟁: Q4 평균 < Q3 평균
    _avg_score_vs_period_test(replay_data, "trade_war_2018",
                               "2018-07-01", "2018-09-30", "Q3 2018", results)

    # 4. COVID: STRONG_BUY 평시 절반 미만
    _strong_buy_pct_test(replay_data, "covid_crash", results, baseline_dist)

    # 5. 2022 인플레: 2022 평균 < 2021 평균
    _avg_score_vs_period_test(replay_data, "inflation_2022",
                               "2021-01-01", "2021-12-31", "2021", results)

    # 6. SVB: 금융주 5일 윈도우 비교
    svb = REGIMES["svb_collapse"]
    svb_tickers = svb["tickers"]
    pre_svb = _filter_by_date_range(replay_data, "2023-02-27", "2023-03-08", svb_tickers)
    post_svb = _filter_by_date_range(replay_data, "2023-03-13", "2023-03-22", svb_tickers)
    pre_avg = float(np.mean([r["brain_score"] for r in pre_svb])) if pre_svb else None
    post_avg = float(np.mean([r["brain_score"] for r in post_svb])) if post_svb else None
    if pre_avg is not None and post_avg is not None:
        svb_pass = post_avg < pre_avg
        svb_verdict = "PASS" if svb_pass else "FAIL"
    else:
        svb_verdict = "INSUFFICIENT_DATA"
    results["svb_collapse"] = {
        "description": svb["description"],
        "tickers": svb_tickers,
        "n_pre": len(pre_svb),
        "n_post": len(post_svb),
        "avg_brain_score_pre": round(pre_avg, 2) if pre_avg is not None else None,
        "avg_brain_score_post": round(post_avg, 2) if post_avg is not None else None,
        "verdict": svb_verdict,
    }

    return results


# ─── Forward return by grade ──────────────────────────────


def grade_return_summary(replay_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """등급별 forward 30d 수익률 통계."""
    by_grade: Dict[str, List[float]] = {g: [] for g in
                                         ["STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID"]}
    for r in replay_data:
        if r["forward_30d_return_pct"] is None:
            continue
        by_grade[r["grade"]].append(r["forward_30d_return_pct"])

    out = {}
    for g, rets in by_grade.items():
        if rets:
            out[g] = {
                "n": len(rets),
                "avg_return_pct": round(float(np.mean(rets)), 3),
                "median_return_pct": round(float(np.median(rets)), 3),
                "win_rate_pct": round(sum(1 for r in rets if r > 0) / len(rets) * 100, 1),
                "std_pct": round(float(np.std(rets)), 3),
            }
        else:
            out[g] = {"n": 0}
    # 단조성 점검
    avgs = [(g, out[g]["avg_return_pct"]) for g in
            ["STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID"]
            if out[g].get("n", 0) > 0]
    correct = sum(1 for i in range(len(avgs) - 1) if avgs[i][1] >= avgs[i + 1][1])
    pairs = max(1, len(avgs) - 1)
    monotonicity = round(correct / pairs, 3)
    return {"by_grade": out, "monotonicity_score": monotonicity}


# ─── 메인 ─────────────────────────────────────────────────


def grade_component_breakdown(replay_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """등급별 fact_score 컴포넌트 평균/표준편차 비교 (§9 진단).

    가설: 등급 간 차이를 만드는 컴포넌트가 무엇인지 파악.
    BUY 가 CAUTION 보다 수익률 낮은 원인 = 어느 컴포넌트가 잘못된 방향으로 작동하나?
    """
    component_keys = ["momentum_3m", "momentum_1m", "rsi_14",
                      "price_to_ma200_pct", "volatility_20d_ann", "volume_ratio_20d"]
    grades_present = ["STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID"]

    by_grade: Dict[str, Dict[str, List[float]]] = {
        g: {c: [] for c in component_keys} for g in grades_present
    }
    fwd_by_grade: Dict[str, List[float]] = {g: [] for g in grades_present}

    for r in replay_data:
        g = r["grade"]
        f = r.get("factors") or {}
        for c in component_keys:
            v = f.get(c)
            if v is not None:
                by_grade[g][c].append(float(v))
        fr = r.get("forward_30d_return_pct")
        if fr is not None:
            fwd_by_grade[g].append(fr)

    out: Dict[str, Any] = {"by_grade": {}}
    for g in grades_present:
        comp_stats = {}
        for c in component_keys:
            vals = by_grade[g][c]
            if vals:
                comp_stats[c] = {
                    "mean": round(float(np.mean(vals)), 3),
                    "std": round(float(np.std(vals)), 3),
                    "n": len(vals),
                }
            else:
                comp_stats[c] = {"mean": None, "std": None, "n": 0}
        fwd = fwd_by_grade[g]
        out["by_grade"][g] = {
            "components": comp_stats,
            "n": len(fwd),
            "fwd_avg": round(float(np.mean(fwd)), 3) if fwd else None,
        }

    return out


def print_component_breakdown(breakdown: Dict[str, Any]) -> None:
    grades = ["STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID"]
    components = ["momentum_3m", "momentum_1m", "rsi_14",
                  "price_to_ma200_pct", "volatility_20d_ann", "volume_ratio_20d"]
    print(f"{'component':<22} " + " ".join(f"{g:>11}" for g in grades))
    print("-" * 92)
    for c in components:
        row = f"{c:<22} "
        for g in grades:
            v = breakdown["by_grade"][g]["components"].get(c, {}).get("mean")
            row += f" {v:>10.2f}" if v is not None else f"        -   "
        print(row)
    print("-" * 92)
    n_row = f"{'n':<22} "
    fwd_row = f"{'fwd_30d_avg %':<22} "
    for g in grades:
        info = breakdown["by_grade"][g]
        n_row += f" {info['n']:>10d}"
        fwd_row += f" {info['fwd_avg']:>+10.3f}" if info["fwd_avg"] is not None else "         -"
    print(n_row)
    print(fwd_row)


def main():
    parser = argparse.ArgumentParser(description="VERITY Brain historical backfill replay")
    parser.add_argument("--smoke", action="store_true", help="5 종목 × 1년 (smoke test)")
    parser.add_argument("--full", action="store_true", help="30 종목 × 2020~현재 (전체)")
    parser.add_argument("--tickers", type=str, help="콤마 구분 ticker (수동 지정)")
    parser.add_argument("--start", type=str, help="시작 날짜 YYYY-MM-DD")
    parser.add_argument("--end", type=str, default=None, help="종료 날짜 (default: today)")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="결과 저장 디렉터리 (default: data/)")
    parser.add_argument("--component-breakdown", action="store_true",
                        help="§9 진단: 등급별 fact_score 컴포넌트 분포 출력")
    args = parser.parse_args()

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
        start = args.start or DEFAULT_START_SMOKE
    elif args.full:
        tickers = DEFAULT_FULL_TICKERS
        start = args.start or DEFAULT_START_FULL
    else:  # smoke 기본
        tickers = DEFAULT_SMOKE_TICKERS
        start = args.start or DEFAULT_START_SMOKE

    end = args.end or datetime.now().strftime("%Y-%m-%d")
    out_dir = args.output_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

    print(f"=" * 72)
    print(f"VERITY Historical Backfill Replay")
    print(f"=" * 72)
    print(f"기간: {start} → {end}")
    print(f"종목: {len(tickers)}개  ({', '.join(tickers[:5])}{'...' if len(tickers) > 5 else ''})")
    print(f"eval freq: {EVAL_FREQ_DAYS}d, forward hold: {FORWARD_HOLD}d")
    print()
    print(f"⚠ 검증 한계 — sentiment=50 중립 고정, DART 미연결, ML 모델 미사용")
    print(f"  → fact-only / technical-only IC validation 임을 명심")
    print()

    # VIX series (regime gate 용) — 한 번만 fetch
    print(f"  VIX fetch (regime gate 용, panic 임계 {VIX_PANIC_THRESHOLD}) ...", end=" ", flush=True)
    vix_series = fetch_vix_series(start, end)
    if vix_series is not None:
        n_panic = int((vix_series > VIX_PANIC_THRESHOLD).sum())
        print(f"OK ({len(vix_series)} 일, panic {n_panic} 일)")
    else:
        print(f"SKIP (regime gate 비활성)")
    print()

    # 종목별 replay
    all_data: List[Dict[str, Any]] = []
    for i, tkr in enumerate(tickers, 1):
        print(f"  [{i}/{len(tickers)}] {tkr} ...", end=" ", flush=True)
        rows = replay_ticker(tkr, start, end, vix_series=vix_series)
        if rows:
            print(f"OK ({len(rows)} 일자)")
            all_data.extend(rows)
        else:
            print(f"SKIP (데이터 부족)")

    if not all_data:
        print("\n❌ 사용 가능한 데이터 없음 — 종료.")
        return 1

    print(f"\n총 replay 행: {len(all_data)} (종목 {len(tickers)} × 평균 {len(all_data) // len(tickers)} 일자)")

    # IC 측정
    print("\n" + "=" * 72)
    print("Component IC (forward 30d 수익률 상관)")
    print("=" * 72)
    ic = compute_component_ic(all_data)
    if ic.get("status") == "ok":
        for comp, v in ic["components"].items():
            ps = ("%+0.4f" % v["pearson_ic"]) if v["pearson_ic"] is not None else "  ?  "
            sp = ("%+0.4f" % v["spearman_ic"]) if v["spearman_ic"] is not None else "  ?  "
            mark = " ⚠NOISE" if v["is_noise_candidate"] else ""
            print(f"  {comp:<25} pearson={ps}  spearman={sp}{mark}")
        nc = ic["noise_candidates"]
        if nc:
            print(f"\n  제거 후보 (|IC| < {IC_NOISE_THRESHOLD}): {', '.join(nc)}")
        else:
            print(f"\n  ✓ 모든 컴포넌트가 |IC| >= {IC_NOISE_THRESHOLD}")
    else:
        print(f"  insufficient_data (n={ic.get('n', 0)})")

    # Grade 단조성
    print("\n" + "=" * 72)
    print("등급별 forward 30d 수익률")
    print("=" * 72)
    gr = grade_return_summary(all_data)
    for g in ["STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID"]:
        v = gr["by_grade"][g]
        if v.get("n", 0):
            print(f"  {g:<12} n={v['n']:<5d} avg={v['avg_return_pct']:+7.3f}%  "
                  f"median={v['median_return_pct']:+7.3f}%  win={v['win_rate_pct']:5.1f}%")
        else:
            print(f"  {g:<12} n=0  (no samples)")
    print(f"\n  단조성 점수: {gr['monotonicity_score']:.2f} "
          f"(1.0=완벽, 0.5=무작위)")

    # Regime stress test
    print("\n" + "=" * 72)
    print("Regime Stress Test")
    print("=" * 72)
    regime = regime_stress_test(all_data)
    for k, v in regime.items():
        if k.startswith("_"):
            continue
        verdict = v.get("verdict", "?")
        mark = "✓" if verdict == "PASS" else ("✗" if verdict == "FAIL" else "?")
        print(f"  {mark} [{verdict}] {k}: {v['description']}")
        # STRONG_BUY 비율 테스트 (gfc, covid)
        if "regime_strong_buy_pct" in v:
            print(f"      regime STRONG_BUY%: {v['regime_strong_buy_pct']:.1f}% "
                  f"(평시 {v['baseline_strong_buy_pct']:.1f}% / n={v['n']})")
        # 평균 score 비교 테스트 (2011 강등, 2018 무역, 2022 인플레)
        elif "avg_brain_score_regime" in v:
            ar = v.get("avg_brain_score_regime")
            af = v.get("avg_brain_score_ref")
            if ar is not None and af is not None:
                print(f"      regime avg={ar:.2f} / ref({v['ref_label']}) avg={af:.2f}  "
                      f"(n_r={v['n_regime']}, n_f={v['n_ref']})")
            else:
                print(f"      데이터 부족 (n_r={v['n_regime']}, n_f={v['n_ref']})")
        # SVB
        elif k == "svb_collapse":
            pre = v.get("avg_brain_score_pre")
            post = v.get("avg_brain_score_post")
            if pre is not None and post is not None:
                print(f"      SVB 전 avg={pre:.2f} → 후 avg={post:.2f}  "
                      f"(n_pre={v['n_pre']}, n_post={v['n_post']})")
            else:
                print(f"      데이터 부족 (n_pre={v['n_pre']}, n_post={v['n_post']})")

    # § 9 진단: 등급별 컴포넌트 분포 (--component-breakdown 시)
    if args.component_breakdown:
        print("\n" + "=" * 92)
        print("§9 — 등급별 fact_score 컴포넌트 분포 (BUY vs CAUTION 역전 진단)")
        print("=" * 92)
        breakdown = grade_component_breakdown(all_data)
        print_component_breakdown(breakdown)
    else:
        breakdown = None

    # 저장
    backfill_path = os.path.join(out_dir, "backfill_replay_result.json")
    ic_path = os.path.join(out_dir, "component_ic_result.json")

    backfill_payload = {
        "generated_at": datetime.now().isoformat(),
        "config": {"tickers": tickers, "start": start, "end": end,
                   "eval_freq_days": EVAL_FREQ_DAYS, "forward_hold_days": FORWARD_HOLD},
        "n_replay_rows": len(all_data),
        "grade_return_summary": gr,
        "regime_stress_test": regime,
        "component_breakdown": breakdown,
        "limitations": [
            "sentiment=50 중립 고정 (historical 뉴스 재현 불가)",
            "DART 펀더멘털 미연결 — technical/momentum 컴포넌트만",
            "LSTM/AI 예측 미적용 — 모델 스냅샷 부재",
            "VCI bonus / red_flag / overrides 단순화 (full pipeline 의 70% 만 검증)",
        ],
    }
    # 가벼운 저장 (full replay row 는 별도 필요 시)
    with open(backfill_path, "w", encoding="utf-8") as f:
        json.dump(backfill_payload, f, ensure_ascii=False, indent=2, default=str)

    with open(ic_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "config": backfill_payload["config"],
            **ic,
        }, f, ensure_ascii=False, indent=2, default=str)

    print()
    print(f"=" * 72)
    print(f"저장 완료:")
    print(f"  {backfill_path}")
    print(f"  {ic_path}")

    # 종합 verdict
    pass_count = sum(1 for k, v in regime.items()
                     if not k.startswith("_") and v.get("verdict") == "PASS")
    total = sum(1 for k, v in regime.items()
                if not k.startswith("_") and v.get("verdict") in ("PASS", "FAIL"))
    print(f"\n종합 — Regime: {pass_count}/{total} PASS, "
          f"단조성 {gr['monotonicity_score']:.2f}, "
          f"노이즈 컴포넌트 {len(ic.get('noise_candidates', []))}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
