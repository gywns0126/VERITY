"""
wide_scan v0_heuristic — Phase 2-B Coarse Filter (5,000 → 1,000)

설계 근거 (Perplexity 7답 종합 + 메모리 통합, 2026-05-10):
- Q1: 7차원 = Liquidity(게이트키퍼) / Value / Profitability / Growth / Safety / Payout / Momentum (AQR QMJ + Carhart 정합)
- Q2: sector_thresholds 의무 (한국 PBR 1.1 vs S&P500 5.3 — 미국 임계값 사용 시 90% false BUY)
- Q3: F-Score ≥ 7 + Altman Z ≥ 1.81 (제조업) 강력 게이트 — step (c)
- Q4: 22% cut (5,000 → 1,000) 학계/실무 표준 중앙값
- Q5: DART lag 평균 38일(대) / 43일(중소) — 마감 ±2주 delta pull (후행)
- Q6: 한국 경기민감재(조선·화학·철강) = 3Y CAGR + Mid-cycle Normalized + GICS Z-score (단년 데이터 한계 명시)
- Q7: 한국 시장 = 65 거래일(1분기) shadow run 의무 + State Machine

Step 진척:
- (a) 인프라 (jsonl + state machine 진입점) ✓
- (b1) sector_thresholds 모듈 ✓
- (b2) 7차원 absolute scoring + 22% cut + run-level jsonl 적재 ← 현재
- (c) F-Score / Altman Z 강력 게이트
- (d) cross-sectional Z-score + ticker-level jsonl + CANARY/PRODUCTION 전환

shadow mode = decision 영향 0. portfolio.json 출력은 production stock_filter 결과 그대로.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from api.config import WIDE_SCAN_MODE
from api.analyzers.sector_thresholds import (
    resolve_sector_bucket,
    get_per_thresholds,
    get_pbr_thresholds,
)

WIDE_SCAN_LOG_PATH = Path("data/wide_scan_log.jsonl")
WIDE_SCAN_TARGET_RATIO = 0.22  # Q4: 5,000 → 1,000 (22%)
LABEL = "v0_heuristic"          # 메모리 원칙 2

# 7차원 가중치 (Q1 답 — AQR QMJ 4차원 + Value/Momentum/Liquidity 분산)
DIM_WEIGHTS = {
    "liquidity":     0.10,
    "value":         0.20,
    "profitability": 0.20,
    "growth":        0.10,  # 단년 데이터 한계 → 가중치 낮게. step (c) 에서 3Y CAGR 추가 후 상향
    "safety":        0.15,
    "payout":        0.10,
    "momentum":      0.15,
}
assert abs(sum(DIM_WEIGHTS.values()) - 1.0) < 1e-9, "DIM_WEIGHTS 합 1.0 위반"

# 경기민감재 — Q6: YoY 단년 데이터 신뢰도 낮은 GICS bucket
_CYCLICAL_COMPANY_TYPES = {
    "조선", "화학", "철강", "산업재", "광업", "건설", "자동차", "에너지", "석유", "가스",
}


# ── 헬퍼 함수 ────────────────────────────────────────────────────────
def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _is_us(stock: dict) -> bool:
    return (stock.get("currency") or "").upper() == "USD"


def _is_cyclical(stock: dict) -> bool:
    """Q6: 한국 경기민감재 (조선/화학/철강) 판정. YoY 단년 Growth 신뢰도 낮음."""
    return (stock.get("company_type") or "") in _CYCLICAL_COMPANY_TYPES


# ── 7차원 absolute scoring (step b2 — v0_heuristic) ──────────────────
def _score_liquidity(stock: dict) -> float:
    """Q1: 게이트키퍼 차원 (factor X). trading_value + market_cap log scale.

    한국 50B 원 / 미국 $500M 이 100점 기준 (Phase 0.5 결정 6 정합).
    Hard Floor 통과 종목만 들어오므로 실측 분포 좁아 단순 log scale 충분.
    """
    tv = float(stock.get("trading_value") or 0)
    mc = float(stock.get("market_cap") or 0)
    if tv <= 0 and mc <= 0:
        return 0.0
    if _is_us(stock):
        # 거래대금 score (log scale, $1M~$500M)
        tv_score = _clamp(math.log10(max(tv, 1)) - 6.0, 0, 2.7) / 2.7 * 100  # 1e6=0, 5e8=100
        mc_score = _clamp(math.log10(max(mc, 1)) - 8.0, 0, 4.0) / 4.0 * 100  # 1e8=0, 1e12=100
    else:
        # KR: 1B 원 = 0점, 50B 원 = 100점
        tv_score = _clamp(math.log10(max(tv, 1)) - 9.0, 0, 1.7) / 1.7 * 100
        mc_score = _clamp(math.log10(max(mc, 1)) - 10.0, 0, 4.0) / 4.0 * 100
    return (tv_score + mc_score) / 2.0


def _score_value(stock: dict, bucket: str) -> float:
    """Q2: PER/PBR sector_thresholds 적용 의무. 미국 임계값 사용 금지.

    PER ≤ Q1 = 100점 / Q2 = 50점 / Q3 = 20점 / Q3 초과 = 0점.
    PER ≤ 0 (적자) = 50점 (모름 — turnaround 가능성 보존). 메모리 결정 8 미발동.
    PBR 도 동일 방식. 두 점수 평균.
    """
    per = float(stock.get("per") or 0)
    pbr = float(stock.get("pbr") or 0)
    per_th = get_per_thresholds(bucket)
    pbr_th = get_pbr_thresholds(bucket)

    def _score_metric(value: float, th: dict) -> float:
        if value <= 0:
            return 50.0  # 적자/미보고 — 모름 처리
        if value <= th["Q1"]:
            return 100.0
        if value <= th["Q2"]:
            return 75.0
        if value <= th["Q3"]:
            return 40.0
        return _clamp(40.0 - (value - th["Q3"]) / th["Q3"] * 30, 0, 40)  # Q3 초과 점진 하락

    return (_score_metric(per, per_th) + _score_metric(pbr, pbr_th)) / 2.0


def _score_profitability(stock: dict) -> float:
    """Q3: ROE + operating_margin (GP/A 미가용 — yfinance 단계 미수집).

    Magic Formula 한국개선 (KAIS 2023): ROIC 대신 GP/A 권장이지만 단계적 도입.
    현재 ROE + OPM 평균. step (c) 에서 GP/A 보강 검토.
    """
    roe = float(stock.get("roe") or 0)
    opm = float(stock.get("operating_margin") or 0)
    # ROE: 0 = 0점, 15 = 100점
    roe_score = _clamp(roe / 15.0 * 100, 0, 100)
    # 영업마진: 0 = 0점, 15 = 100점
    opm_score = _clamp(opm / 15.0 * 100, 0, 100)
    return (roe_score + opm_score) / 2.0


def _score_growth(stock: dict, bucket: str) -> float:
    """Q6: revenue_growth (단년 YoY) 만 가용 — 한계 명시.

    단년 데이터 = cyclical noise 위험. 경기민감재는 페널티 30% 적용.
    step (c) 에서 3Y CAGR + Mid-cycle Normalized 보강 후 가중치 0.10 → 0.15 상향.
    """
    rg = float(stock.get("revenue_growth") or 0)
    # -10% = 0점, +30% = 100점
    base = _clamp((rg + 10) / 40 * 100, 0, 100)
    if _is_cyclical(stock):
        base *= 0.7  # Q6 페널티 — YoY 신뢰도 낮음
    return base


def _score_safety(stock: dict) -> float:
    """Q1 QMJ Safety: debt_ratio (sector-aware) + current_ratio.

    금융업 (bucket=금융) 은 debt_ratio 점수 무효화 (50점 = 모름).
    현재 Beta / Volatility / Earnings Variability 미가용 — step (c) 보강.
    """
    debt = float(stock.get("debt_ratio") or 0)
    cr = float(stock.get("current_ratio") or 0)
    bucket = resolve_sector_bucket(stock)

    if bucket == "금융":
        debt_score = 50.0  # 금융업은 자체 부채구조 — 일반 임계값 미적용
    else:
        # 30 = 100점, 200 = 0점
        if debt <= 0:
            debt_score = 50.0
        else:
            debt_score = _clamp(100 - (debt - 30) / 1.7, 0, 100)
    # 유동비율: 1.0 = 0점, 2.0 = 100점
    if cr <= 0:
        cr_score = 50.0
    else:
        cr_score = _clamp((cr - 1.0) / 1.0 * 100, 0, 100)
    return (debt_score + cr_score) / 2.0


def _score_payout(stock: dict) -> float:
    """Q1 QMJ Payout 신규 차원: 배당수익률.

    자사주매입 (buyback yield) 미가용 — yfinance 단계 미수집. step (c) DART 통합.
    """
    dy = float(stock.get("div_yield") or 0)
    # 0% = 0점, 5% = 100점
    return _clamp(dy / 5.0 * 100, 0, 100)


def _score_momentum(stock: dict) -> float:
    """Q3: 12-1M skip momentum (Carhart 표준).

    sparkline_weekly (52pt) 가용 시 [-52:-4] vs [-4:] 비교 = 12-1M skip.
    fallback: drop_from_high_pct 사용 (52w 고점 대비 — momentum proxy).
    """
    weekly = stock.get("sparkline_weekly") or []
    if isinstance(weekly, list) and len(weekly) >= 52:
        try:
            past = float(weekly[-52])  # 12개월 전
            recent = float(weekly[-4])  # 1개월 전 (skip)
            if past > 0:
                ret_12_1 = (recent - past) / past * 100
                # -30% = 0점, +30% = 100점
                return _clamp((ret_12_1 + 30) / 60 * 100, 0, 100)
        except (TypeError, ValueError, IndexError):
            pass
    # Fallback: drop_from_high_pct
    drop = float(stock.get("drop_from_high_pct") or 0)
    # 0% (52w 고점 도달) = 100점, -50% = 0점
    return _clamp(100 + drop * 2, 0, 100)


# ── F-Score / Altman Z 강력 게이트 stub (step c) ─────────────────────
def _piotroski_f_score(stock: dict) -> Optional[int]:
    """Q3: F-Score ≥ 7 단독 강력 (한국 KOSPI 1995~2016 9점 연 21.38%).
    Profitability(4) + Leverage/Liquidity(3) + Operating Efficiency(2) = 9 항목.
    step (c) 에서 실제 계산. 현재 None 반환 (게이트 미적용).
    """
    return None


def _altman_z_score(stock: dict, sector: str) -> Optional[float]:
    """Q3: Altman Z ≥ 1.81 binary 컷오프 (제조업 한정, 부도 제거 전용).
    비제조업 (금융/지주/서비스): 부채비율 대체 (Q3 주의).
    """
    return None


# ── 합산 + Cut ───────────────────────────────────────────────────────
def _score_stock(stock: dict) -> Tuple[float, dict]:
    """단일 종목 7차원 점수 + 가중 합산. (composite_score, dim_breakdown) 반환."""
    bucket = resolve_sector_bucket(stock)
    breakdown = {
        "liquidity":     _score_liquidity(stock),
        "value":         _score_value(stock, bucket),
        "profitability": _score_profitability(stock),
        "growth":        _score_growth(stock, bucket),
        "safety":        _score_safety(stock),
        "payout":        _score_payout(stock),
        "momentum":      _score_momentum(stock),
    }
    composite = sum(breakdown[k] * DIM_WEIGHTS[k] for k in DIM_WEIGHTS)
    return composite, breakdown


# ── 메인 진입점 ──────────────────────────────────────────────────────
def run_wide_scan_shadow(stocks: List[dict], *, run_at_iso: Optional[str] = None) -> dict:
    """Phase 2-B Coarse Filter shadow 실행 — decision 영향 0.

    Args:
        stocks: get_all_stock_data 결과 리스트 (5,000 universe 통과 종목)
        run_at_iso: 명시적 timestamp (테스트용). None 이면 KST 현재.

    Returns:
        {
          "mode": WIDE_SCAN_MODE, "label": "v0_heuristic",
          "input_n": int, "target_n": int, "passed_n": int,
          "logged": bool, "skipped": bool,
          "top_tickers": list[str],   # 통과 종목 ticker (composite 내림차순)
          "cut_score": float,         # 22% cut 임계값
        }

    Step (b2) 동작: 7차원 absolute scoring → composite 합산 → 상위 22% 선출.
    decision 영향 0 보장 — 호출자는 결과 무시하고 production filter 결과 사용.
    """
    if WIDE_SCAN_MODE == "DISABLED":
        return {
            "mode": "DISABLED", "label": LABEL,
            "input_n": len(stocks), "target_n": 0, "passed_n": 0,
            "logged": False, "skipped": True,
            "top_tickers": [], "cut_score": 0.0,
        }

    now_iso = run_at_iso or datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    input_n = len(stocks)
    target_n = int(input_n * WIDE_SCAN_TARGET_RATIO)

    # 7차원 스코어 + composite (decision 영향 0 — 입력 stocks mutate 금지)
    scored: List[Tuple[float, str, dict]] = []
    dim_sum = {k: 0.0 for k in DIM_WEIGHTS}
    for s in stocks:
        composite, breakdown = _score_stock(s)
        scored.append((composite, s.get("ticker", "?"), breakdown))
        for k, v in breakdown.items():
            dim_sum[k] += v

    # 22% cut — 합산 score 내림차순 상위 target_n
    scored.sort(key=lambda t: t[0], reverse=True)
    passed = scored[:target_n] if target_n > 0 else []
    cut_score = passed[-1][0] if passed else 0.0

    # run-level jsonl 1줄 적재 (ticker-level 라인은 step d 에서 추가)
    dim_avg = {k: round(dim_sum[k] / max(input_n, 1), 2) for k in DIM_WEIGHTS}
    entry = {
        "ts": now_iso,
        "label": LABEL,
        "mode": WIDE_SCAN_MODE,
        "step": "b2_scoring",
        "input_n": input_n,
        "target_n": target_n,
        "passed_n": len(passed),
        "cut_score": round(cut_score, 2),
        "dim_weights": DIM_WEIGHTS,
        "dim_avg": dim_avg,
        "top10_tickers": [t for _, t, _ in passed[:10]],
        "top10_scores": [round(s, 2) for s, _, _ in passed[:10]],
        "note": "step_b2 — absolute scoring v0. cross-sectional Z-score 는 step d.",
    }
    logged = _append_jsonl(entry)

    return {
        "mode": WIDE_SCAN_MODE, "label": LABEL,
        "input_n": input_n, "target_n": target_n,
        "passed_n": len(passed),
        "logged": logged, "skipped": False,
        "top_tickers": [t for _, t, _ in passed],
        "cut_score": cut_score,
    }


def _append_jsonl(entry: dict) -> bool:
    """data/wide_scan_log.jsonl 1줄 append. silent 실패 (main 흐름 무중단).

    메모리 feedback_data_collection_verification_mandatory 정합:
    try/finally + logged 명시 stderr + 누적 검증 N run 의무.
    """
    try:
        WIDE_SCAN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(WIDE_SCAN_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        import sys
        print(
            f"[wide_scan] jsonl 적재 실패 — {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        return False
