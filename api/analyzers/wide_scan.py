"""
wide_scan v0_heuristic — Phase 2-B Coarse Filter (5,000 → 1,000)

설계 근거 (Perplexity 7답 종합 + 메모리 통합, 2026-05-10):
- Q1: 7차원 = Liquidity(게이트키퍼) / Value / Profitability / Growth / Safety / Payout / Momentum (AQR QMJ + Carhart 정합)
- Q2: sector_thresholds 의무 (한국 PBR 1.1 vs S&P500 5.3 — 미국 임계값 사용 시 90% false BUY)
- Q3: F-Score ≥ 7 + Altman Z ≥ 1.81 (제조업) 강력 게이트 — step (c)
- Q4: 22% cut (5,000 → 1,000) 학계/실무 표준 중앙값
- Q5: DART lag 평균 38일(대) / 43일(중소) — 마감 ±2주 delta pull (후행)
- Q6: 한국 경기민감재(조선·화학·철강) = 3Y CAGR + Mid-cycle Normalized + GICS Z-score (단년 데이터 한계 명시)
- Q7: 한국 시장 = WIDE_SCAN_PRODUCTION_MIN_DAYS 거래일 shadow run 의무 + State Machine
       (2026-05-22 PM 승인 65→90, config.WIDE_SCAN_PRODUCTION_MIN_DAYS)

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

from api.config import WIDE_SCAN_MODE, WIDE_SCAN_PRODUCTION_MIN_DAYS
from api.analyzers.sector_thresholds import (
    resolve_sector_bucket,
    get_per_thresholds,
    get_pbr_thresholds,
)

WIDE_SCAN_LOG_PATH = Path("data/wide_scan_log.jsonl")


def production_gate_status(log_path: Optional[Path] = None) -> dict:
    """SHADOW→PRODUCTION 전환 게이트 상태 — 누적 거래일 vs 최소선.

    wide_scan_log.jsonl 의 distinct date(ts) 수 = SHADOW 운영 거래일.
    PRODUCTION/CANARY 적용 wire 시 이 ready 를 선결 조건으로 검사 (조기 flip 방어).

    Returns:
        {days_accumulated, min_required, ready, gate_basis}
    주의: ready=True 는 N **개수** 충족일 뿐. flip 시 N **품질**(IC 부호/단조성) 별도 확인 의무
          (config WIDE_SCAN_PRODUCTION_MIN_DAYS caveat).
    """
    path = log_path or WIDE_SCAN_LOG_PATH
    days: set[str] = set()
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        ts = json.loads(line).get("ts")
                    except json.JSONDecodeError:
                        continue
                    if ts:
                        days.add(str(ts)[:10])  # YYYY-MM-DD
        except OSError:
            pass
    n = len(days)
    return {
        "days_accumulated": n,
        "min_required": WIDE_SCAN_PRODUCTION_MIN_DAYS,
        "ready": n >= WIDE_SCAN_PRODUCTION_MIN_DAYS,
        "gate_basis": "Lopez de Prado MinTRL 하단 + STRATEGY_MIN_OOS_DAYS 일관성 (PM 2026-05-22)",
    }
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
    """Q3: ROE + GP/A (Gross Margin proxy) + operating_margin.

    Magic Formula 한국개선 (KAIS 2023): ROIC 대신 GP/A 권장. yfinance grossMargins
    가용 시 GP/A 1차 proxy 로 활용 (실제 GP/A = gross_profit/total_assets, 더 정밀
    하려면 DART pre-attach 후 step e).

    GP/A 가용: 3 metric 평균. 미가용: ROE + OPM 평균 (legacy).
    """
    roe = float(stock.get("roe") or 0)
    opm = float(stock.get("operating_margin") or 0)
    # ROE: 0 = 0점, 15 = 100점
    roe_score = _clamp(roe / 15.0 * 100, 0, 100)
    # 영업마진: 0 = 0점, 15 = 100점
    opm_score = _clamp(opm / 15.0 * 100, 0, 100)

    # GP/A proxy (Magic Formula 한국개선) — gross_margins 가용 시
    gm = stock.get("gross_margins")
    if gm is not None:
        # 매출총이익률: 10% = 0점, 50% = 100점
        gm_score = _clamp((float(gm) - 10) / 40 * 100, 0, 100)
        return (roe_score + opm_score + gm_score) / 3.0
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


# ── F-Score / Altman Z 강력 게이트 (step c — 구조 prep, 데이터 통합은 step e) ─────────
# 현재 wide_scan 호출 시점 (main.py STEP 2.05) 의 stock dict 에는:
#   ROE / debt_ratio / current_ratio / operating_margin / revenue_growth / market_cap 만 가용
# DART (main.py:2712) 는 30 candidates 에만 attach — wide_scan call 시점엔 미존재
# yfinance info 의 freeCashflow / grossMargins / totalAssets 등은 get_stock_data 가 미추출
#
# 따라서 F-Score 9 항목 / Altman Z 5 비율 → 현재 stock dict 에서 1-2개만 계산 가능
# step (c) 는 구조 prep — 항목별 True/False/None + missing_fields 리스트 반환
# 실 데이터 통합 = step (e) (stock_data.py 확장 + DART pre-attach)

def _piotroski_f_score(stock: dict) -> dict:
    """Q3: F-Score 9 항목 explicit dict 반환.

    Profitability (4): ROA>0, CFO>0, ΔROA>0, CFO>NI (accruals 양수)
    Leverage/Liquidity (3): Δleverage<0, Δcurrent_ratio>0, no new shares
    Operating Efficiency (2): Δgross_margin>0, Δasset_turnover>0

    Returns:
        {
          "score": Optional[int],          # 0-9, missing 시 None (전체 무효)
          "available_n": int,              # 9 중 계산된 항목 수
          "criteria": {c1~c9: bool|None}, # None=missing
          "missing_fields": [list of str],
          "data_source": "stock_dict_v0",  # step e 에서 "dart_pre_attach" 로 전환
        }

    한국 KOSPI 1995~2016 백테스트: F-Score 9점 연 21.38% (Perplexity Q3, 가장 강력).
    F-Score ≥ 7 binary gate 가 메인 활용법.
    """
    # 가용 필드: ROE, ROA, CFO (operating_cashflow), EPS — 단년 + fscore_deltas (시계열 Δ wire, 2026-05-20)
    roa = stock.get("roa")
    cfo = stock.get("operating_cashflow")
    eps = stock.get("eps")
    shares = stock.get("shares_outstanding")
    # net_income proxy = eps × shares (없으면 None)
    ni = (eps * shares) if (eps and shares) else None

    # 시계열 Δ wire (2026-05-20) — wide_scan contract (stock mutate 금지) 정합 위해 직접 호출
    deltas: dict = {}
    try:
        from api.utils.fscore_delta import (
            load_quarterly_snapshots, find_quarter_offset_prior,
            compute_fscore_deltas_with_cycle_guard, is_cyclical_for_fscore,
        )
        ticker = stock.get("ticker", "")
        snapshots = load_quarterly_snapshots(ticker) if ticker else []
        if snapshots:
            current = snapshots[0]
            current_qend = current.get("quarter_end", "")
            prior_4q = find_quarter_offset_prior(current_qend, snapshots[1:], quarters_back=4)
            is_cyc = is_cyclical_for_fscore(stock)
            prior_8q = find_quarter_offset_prior(current_qend, snapshots[1:], quarters_back=8) if is_cyc else None
            deltas = compute_fscore_deltas_with_cycle_guard(current, prior_4q, prior_8q, is_cyclical=is_cyc)
    except Exception:
        pass
    delta_roa = deltas.get("delta_roa")

    criteria: dict = {
        "c1_roa_positive": (float(roa) > 0) if roa is not None else None,
        "c2_cfo_positive": (float(cfo) > 0) if cfo is not None else None,
        "c3_delta_roa_positive": (delta_roa > 0) if delta_roa is not None else None,
        "c4_cfo_gt_ni": (cfo > ni) if (cfo is not None and ni is not None) else None,
        "c5_delta_leverage_negative": deltas.get("c5_delta_leverage_negative"),
        "c6_delta_current_ratio_positive": deltas.get("c6_delta_current_ratio_positive"),
        "c7_no_new_shares": None,                                   # shares 시계열 누적 후 (별 sprint)
        "c8_delta_gross_margin_positive": deltas.get("c8_delta_gross_margin_positive"),
        "c9_delta_asset_turnover_positive": deltas.get("c9_delta_asset_turnover_positive"),
    }
    missing_fields = []
    if deltas.get("data_source") in ("no_snapshots", "no_prior"):
        missing_fields.append("quarterly_snapshots_yoy")
    if criteria["c7_no_new_shares"] is None:
        missing_fields.append("shares_outstanding_history")

    available = [v for v in criteria.values() if v is not None]
    available_n = len(available)
    # available_n ≥ 3 (current/Δ 모두 부재라도 c1+c2+c4 는 가능) 일 때 부분 score 박음
    score = sum(1 for v in available if v is True) if available_n >= 3 else None

    return {
        "score": score,
        "available_n": available_n,
        "criteria": criteria,
        "missing_fields": missing_fields,
        "data_source": "stock_dict_v0+fscore_delta",
        "cycle_guard": deltas.get("cycle_guard"),
    }


def _altman_z_score(stock: dict) -> dict:
    """Q3: Altman Z 5 비율 explicit dict 반환. 제조업 한정 (부도 제거 binary cutoff).

    원본 Z (1968 미국 제조업):
    Z = 1.2*A + 1.4*B + 3.3*C + 0.6*D + 1.0*E
      A = working capital / total assets
      B = retained earnings / total assets
      C = EBIT / total assets
      D = market cap / total liabilities
      E = sales / total assets

    한국 시장 조정 (Perplexity Q1-3, 2026-05-17 학계 자문):
    - 원본 Z ≥ 1.81 안전 cutoff 는 한국에 부적합 (한국 제조업 D/E 100~150% vs 미국 60~80%).
    - 한국 KOSPI 제조업: Z ≥ 2.3 (상향)
    - KOSDAQ 성장주 / 비제조업: Altman Z'' 신흥시장 모델 사용
        Z″_EM = 3.25 + 6.56*X1 + 3.26*X2 + 6.72*X3 + 1.05*X4 (Altman/Hartzell/Peck 1995)
          X1 = Working Capital / Total Assets (계수 6.56)
          X2 = Retained Earnings / Total Assets
          X3 = EBIT / Total Assets (계수 6.72)
          X4 = Market Cap / Total Liabilities (상장사 변형, Perplexity Q-fin-2)
        컷: Safe ≥ 2.6 / Grey 1.1~2.6 / Distress < 1.1
        (2026-05-20 drift 정정 — 5/14 메모리 + 5/19 commit 28e99a19 X1 6.72 wrong.
         학술 원전 = X1 6.56. wallstreetprep / stocktitan / 다중 출처 정합.)
    - 금융업 (KSIC 64~66): applicable=False (Z 모델 적용 불가)
    - 대기업 계열사 (재벌): Z ≥ 1.5 완화 (계열사 지원으로 부도 적음)

    Returns:
        {
          "z_value": Optional[float],
          "z_safe_threshold": float,     # 한국 조정 cutoff (2.3 / 4.5 / 1.5)
          "model_variant": str,          # "korean_kospi" / "emerging_market_zpp" / "chaebol_relaxed"
          "applicable": bool,
          "sector_bucket": str,
          "ratios": {A~E: float|None},
          "missing_fields": [list of str],
          "data_source": "stock_dict_v0",
        }

    Perplexity Q1-3 ref: docs/MASTER_RULE_DRIFT_AUDIT_v0.1.md.
    """
    bucket = resolve_sector_bucket(stock)
    applicable = (bucket == "제조")

    # Perplexity Q1-3 — 한국 조정 cutoff 결정
    # 1. 금융업 (KSIC 64~66) = applicable False 유지
    # 2. KOSDAQ 성장주 = Z'' 신흥시장 모델 (4.5 cutoff)
    # 3. KOSPI 제조업 = Z (2.3 cutoff, 상향)
    # 4. 대기업 계열사 (재벌) = Z (1.5 완화). 식별 정보 부재시 일반 KOSPI 룰 적용
    market = str(stock.get("market", "")).upper()
    if not applicable:
        model_variant = "not_applicable"
        z_safe_threshold = 0.0
    elif market in ("KOSDAQ",):
        model_variant = "emerging_market_zpp"
        z_safe_threshold = 2.6  # Z″ EM safe cut (Perplexity Q-fin-1 2026-05-19)
    else:  # KOSPI 일반 제조업
        model_variant = "korean_kospi"
        z_safe_threshold = 2.3  # 한국 제조업 학술 정합 (koreascience 2015 JAKO201535257998954)

    # 현재 stock dict 에서 가능한 ratio 만 계산 — 거의 다 None (시계열 Δ 누적 sprint 후 보강)
    market_cap = float(stock.get("market_cap") or 0)
    debt_ratio_pct = stock.get("debt_ratio")  # liabilities/equity %
    # debt_ratio % 로 D (MC/TL) 추정 불가 (TL 절대값 미가용). 미보강.

    ratios: dict = {
        "A_working_capital_over_assets": None,
        "B_retained_earnings_over_assets": None,
        "C_ebit_over_assets": None,
        "D_market_cap_over_liabilities": None,
        "E_sales_over_assets": None,
    }
    missing_fields = [
        "working_capital", "retained_earnings", "ebit",
        "total_assets", "total_liabilities_absolute", "sales",
    ]

    return {
        "z_value": None,            # ratio 1+ 결손 → 전체 None (DART 데이터 통합 sprint 후 보강)
        "z_safe_threshold": z_safe_threshold,  # Perplexity Q1-3 한국 조정
        "model_variant": model_variant,
        "applicable": applicable,
        "sector_bucket": bucket,
        "ratios": ratios,
        "missing_fields": missing_fields,
        "data_source": "stock_dict_v0",
    }


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
    fscore_available_n = 0     # F-Score 9 항목 중 1+ 항목이 계산된 종목 수
    fscore_full_n = 0           # F-Score 7+ 항목 계산되어 score 값 박힌 종목 수
    altman_applicable_n = 0     # 제조업 (Altman Z 적용 가능) 종목 수
    altman_z_full_n = 0         # Z value 계산된 종목 수
    for s in stocks:
        composite, breakdown = _score_stock(s)
        scored.append((composite, s.get("ticker", "?"), breakdown))
        for k, v in breakdown.items():
            dim_sum[k] += v
        # step (c) 게이트 prep — 데이터 가용성 stats 만 누적, decision 영향 0
        f_eval = _piotroski_f_score(s)
        if f_eval["available_n"] > 0:
            fscore_available_n += 1
        if f_eval["score"] is not None:
            fscore_full_n += 1
        z_eval = _altman_z_score(s)
        if z_eval["applicable"]:
            altman_applicable_n += 1
        if z_eval["z_value"] is not None:
            altman_z_full_n += 1

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
        "step": "c_gate_prep",
        "input_n": input_n,
        "target_n": target_n,
        "passed_n": len(passed),
        "cut_score": round(cut_score, 2),
        "dim_weights": DIM_WEIGHTS,
        "dim_avg": dim_avg,
        "top10_tickers": [t for _, t, _ in passed[:10]],
        "top10_scores": [round(s, 2) for s, _, _ in passed[:10]],
        # step (c) 게이트 데이터 가용성 — silent skip 차단 (memory feedback_data_collection_verification_mandatory)
        "gate_stats": {
            "fscore_available_n": fscore_available_n,
            "fscore_full_n": fscore_full_n,
            "altman_applicable_n": altman_applicable_n,
            "altman_z_full_n": altman_z_full_n,
            "data_source": "stock_dict_v0",
        },
        "note": "step_c — 게이트 구조 prep. 실 데이터 통합은 step e (stock_data 확장 + DART pre-attach).",
    }
    logged = _append_jsonl(entry)

    # ── funnel sprint Step 2/3/4 cascading (2026-05-17) ──
    # SHADOW 모드만 — PRODUCTION 진입 (8월 말 TG-1) 까지 decision 영향 0.
    # 결과는 wide_scan_log.jsonl step 별 entry 적재. top_tickers 는 step 1 결과 그대로 반환.
    stocks_map = {s.get("ticker", "?"): s for s in stocks}
    try:
        passed_300, step_d_entry = _step_d_precision_filter(passed, target_n=300)
        step_d_entry.update({"ts": now_iso, "label": LABEL, "mode": WIDE_SCAN_MODE,
                             "top10_tickers": [t for _, t, _ in passed_300[:10]]})
        _append_jsonl(step_d_entry)

        passed_100, step_e_entry = _step_e_brain_quick(passed_300, target_n=100)
        step_e_entry.update({"ts": now_iso, "label": LABEL, "mode": WIDE_SCAN_MODE,
                             "top10_tickers": [t for _, t, _ in passed_100[:10]]})
        _append_jsonl(step_e_entry)

        passed_25, step_f_entry = _step_f_sector_diversified(
            passed_100, stocks_map, target_kr=10, target_us=15
        )
        step_f_entry.update({"ts": now_iso, "label": LABEL, "mode": WIDE_SCAN_MODE,
                             "final_tickers": [t for _, t, _ in passed_25]})
        _append_jsonl(step_f_entry)
    except Exception as e:
        import sys
        print(f"[wide_scan] funnel cascading 실패: {type(e).__name__}: {e}",
              file=sys.stderr, flush=True)

    return {
        "mode": WIDE_SCAN_MODE, "label": LABEL,
        "input_n": input_n, "target_n": target_n,
        "passed_n": len(passed),
        "logged": logged, "skipped": False,
        "top_tickers": [t for _, t, _ in passed],
        "cut_score": cut_score,
    }


# ── funnel sprint Step 2/3/4 (2026-05-17): SHADOW path cascading ─────────────
# project_funnel_5stage_sprint plan. SHADOW 모드만 — PRODUCTION 진입 (8월 말 TG-1) 까지
# decision 영향 0. cascading 결과는 wide_scan_log.jsonl 의 step 별 entry 로 적재.
# WIDE_SCAN_PRODUCTION_MIN_DAYS(90) 거래일 SHADOW 누적 후 PRODUCTION 진입 시 즉시 사용 가능.

def _step_d_precision_filter(passed_1k: List[Tuple[float, str, dict]],
                             target_n: int = 300) -> Tuple[List[Tuple[float, str, dict]], dict]:
    """Step 2 (1,000 → 300) 정밀 펀더멘털 필터.

    진짜 게이트 = F-Score ≥ 7 + Altman Z ≥ 1.81. 그러나 F-Score 시계열 Δ 데이터 부재로
    현재 게이트 활성 불가 → fallback = composite top 30% (단순 score cut).
    시계열 누적 sprint (별도 큐) 통과 후 게이트 자동 활성 검토.
    """
    n = len(passed_1k)
    target = min(target_n, n)
    out = passed_1k[:target]  # 이미 composite 내림차순
    return out, {
        "step": "d_precision_fallback",
        "input_n": n,
        "target_n": target,
        "passed_n": len(out),
        "mode_active": "composite_topN",  # 시계열 누적 후 "fscore_z_gate" 로 전환
        "note": "Step 2 fallback — F-Score 시계열 Δ 데이터 누적 후 진짜 게이트 활성 검토",
    }


def _step_e_brain_quick(passed_300: List[Tuple[float, str, dict]],
                        target_n: int = 100) -> Tuple[List[Tuple[float, str, dict]], dict]:
    """Step 3 (300 → 100) Brain v5 quick path.

    fact 0.7 * fact_score + sentiment 0.3 * sentiment_score quick 산식.
    SHADOW 모드라 portfolio 호출 X — stock dict 의 기존 fact/sentiment 컴포넌트 활용.
    완전 호출 (verity_brain._compute_fact/_sentiment) 은 운영 부담 — 단순 proxy 사용.
    """
    rescored = []
    for composite, ticker, breakdown in passed_300:
        # proxy: stock dict 에서 fact/sentiment 신호 발견 가능한 dim avg 활용
        # value + profitability + safety = fact proxy. momentum + payout = sentiment proxy.
        fact_proxy = (
            breakdown.get("value", 50) * 0.35
            + breakdown.get("profitability", 50) * 0.35
            + breakdown.get("safety", 50) * 0.30
        )
        sent_proxy = (
            breakdown.get("momentum", 50) * 0.60
            + breakdown.get("payout", 50) * 0.40
        )
        brain_quick = round(fact_proxy * 0.7 + sent_proxy * 0.3, 2)
        rescored.append((brain_quick, ticker, {**breakdown, "_brain_quick": brain_quick}))

    rescored.sort(key=lambda t: t[0], reverse=True)
    target = min(target_n, len(rescored))
    out = rescored[:target]
    return out, {
        "step": "e_brain_quick",
        "input_n": len(passed_300),
        "target_n": target,
        "passed_n": len(out),
        "weights": {"fact": 0.7, "sentiment": 0.3},
        "fact_proxy_dims": {"value": 0.35, "profitability": 0.35, "safety": 0.30},
        "sentiment_proxy_dims": {"momentum": 0.60, "payout": 0.40},
        "note": "proxy 산식 — verity_brain 정식 호출은 SHADOW 운영 부담. brain_quick top N.",
    }


def _step_f_sector_diversified(passed_100: List[Tuple[float, str, dict]],
                               stocks_map: dict,
                               target_kr: int = 10,
                               target_us: int = 15) -> Tuple[List[Tuple[float, str, dict]], dict]:
    """Step 4 (100 → 25) Sector Diversified.

    sector 별 분류 + 각 sector max N 종목 = 분산. KR 10 + US 15 = 25.
    KR / US sector 분포 별도 추적.
    stocks_map: {ticker: stock_dict} — sector / market 정보 lookup.
    """
    kr_pool, us_pool = [], []
    for entry in passed_100:
        _, ticker, _ = entry
        s = stocks_map.get(ticker, {})
        market = str(s.get("market", "")).upper()
        if market in ("US", "NASDAQ", "NYSE", "NYS"):
            us_pool.append((entry, s.get("sector", "unknown")))
        else:
            kr_pool.append((entry, s.get("sector", "unknown")))

    def _sector_diversify(pool: List[Tuple[Tuple, str]], target: int) -> List[Tuple]:
        """sector 별 max ceil(target / n_sectors) 종목, 부족하면 score 순 채움."""
        if not pool:
            return []
        sectors_present = {sec for _, sec in pool}
        max_per_sector = max(1, target // max(len(sectors_present), 1))
        sector_count: Dict[str, int] = {}
        primary, leftover = [], []
        for entry, sec in pool:
            if sector_count.get(sec, 0) < max_per_sector:
                primary.append(entry)
                sector_count[sec] = sector_count.get(sec, 0) + 1
            else:
                leftover.append(entry)
        # 부족하면 leftover 채움
        while len(primary) < target and leftover:
            primary.append(leftover.pop(0))
        return primary[:target]

    kr_selected = _sector_diversify(kr_pool, target_kr)
    us_selected = _sector_diversify(us_pool, target_us)
    out = kr_selected + us_selected

    kr_sectors = {}
    us_sectors = {}
    for entry in kr_selected:
        sec = stocks_map.get(entry[1], {}).get("sector", "unknown")
        kr_sectors[sec] = kr_sectors.get(sec, 0) + 1
    for entry in us_selected:
        sec = stocks_map.get(entry[1], {}).get("sector", "unknown")
        us_sectors[sec] = us_sectors.get(sec, 0) + 1

    return out, {
        "step": "f_sector_diversified",
        "input_n": len(passed_100),
        "target_n": target_kr + target_us,
        "passed_n": len(out),
        "kr_n": len(kr_selected),
        "us_n": len(us_selected),
        "kr_sector_distribution": kr_sectors,
        "us_sector_distribution": us_sectors,
        "note": "sector field 부재 종목 = 'unknown' bucket. stock_data Step 1 (sector fetch) 통과 후 활성 ↑",
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
