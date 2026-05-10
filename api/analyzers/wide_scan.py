"""
wide_scan v0_heuristic — Phase 2-B Coarse Filter (5,000 → 1,000)

설계 근거 (Perplexity 7답 종합 + 메모리 통합, 2026-05-10):
- Q1: 7차원 = Liquidity(게이트키퍼) / Value / Profitability / Growth / Safety / Payout / Momentum (AQR QMJ + Carhart 정합)
- Q2: sector_thresholds 의무 (한국 PBR 1.1 vs S&P500 5.3 — 미국 임계값 사용 시 90% false BUY)
- Q3: F-Score ≥ 7 + Altman Z ≥ 1.81 (제조업) 강력 게이트
- Q4: 22% cut (5,000 → 1,000) 학계/실무 표준 중앙값
- Q5: DART lag 평균 38일(대) / 43일(중소) — 마감 ±2주 delta pull 필요 (후행)
- Q6: 한국 경기민감재(조선·화학·철강) = 3Y CAGR + Mid-cycle Normalized + GICS Z-score
- Q7: 한국 시장 = 65 거래일(1분기) shadow run 의무 + State Machine

Step (a) 스코프 (2026-05-10):
- 모듈 인프라 + jsonl 로깅 + 7차원 stub 만 박음
- 7차원 실제 계산 = step (b)
- F-Score / Altman Z = step (c)
- State Machine (CANARY/PRODUCTION 전환) = step (d)

shadow mode = decision 영향 0. portfolio.json 출력은 production stock_filter 결과 그대로.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from api.config import WIDE_SCAN_MODE

WIDE_SCAN_LOG_PATH = Path("data/wide_scan_log.jsonl")
WIDE_SCAN_TARGET_RATIO = 0.22  # Q4: 5,000 → 1,000 (22%)
LABEL = "v0_heuristic"          # 메모리 원칙 2


# ── 7차원 스코어 stub (step b 에서 실제 계산 박음) ────────────────────
def _score_liquidity(stock: dict) -> float:
    """Q1: 게이트키퍼 차원 (factor X). 시총 + 거래대금 기반.
    step (b) 에서 sector_thresholds 적용. 현재는 placeholder.
    """
    return 0.0


def _score_value(stock: dict, sector: str) -> float:
    """Q2: PER/PBR/PCR sector_thresholds 적용 의무. 미국 임계값 사용 절대 금지."""
    return 0.0


def _score_profitability(stock: dict) -> float:
    """Q3: ROE + GP/A + 영업마진. Magic Formula 한국개선 (KAIS 2023, ROIC → GP/A)."""
    return 0.0


def _score_growth(stock: dict, sector: str) -> float:
    """Q6: 3Y CAGR + Mid-cycle Normalized + GICS Z-score.
    경기민감재 (조선/화학/철강): EPS sign change 2분기 = Growth 무효 → Profitability 대체.
    """
    return 0.0


def _score_safety(stock: dict) -> float:
    """Q1 QMJ Safety: 부채비율 + 베타 + Vol + Earnings Variability (MSCI Quality 정합).
    Solvency 흡수 (독립 차원 X — 학계 표준).
    """
    return 0.0


def _score_payout(stock: dict) -> float:
    """Q1 QMJ Payout 신규 차원: 배당수익률 + 자사주매입 수익률."""
    return 0.0


def _score_momentum(stock: dict) -> float:
    """Q3: 12-1M skip price momentum (Carhart 표준)."""
    return 0.0


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


# ── 메인 진입점 ──────────────────────────────────────────────────────
def run_wide_scan_shadow(stocks: List[dict], *, run_at_iso: Optional[str] = None) -> dict:
    """Phase 2-B Coarse Filter shadow 실행 — decision 영향 0.

    Args:
        stocks: get_all_stock_data 결과 리스트 (5,000 universe 통과 종목)
        run_at_iso: 명시적 timestamp (테스트용). None 이면 KST 현재.

    Returns:
        {
          "mode": WIDE_SCAN_MODE,
          "label": "v0_heuristic",
          "input_n": int,
          "target_n": int,        # input_n × 22%
          "passed_n": int,        # step (a) 는 항상 0 (스코어 미구현)
          "logged": bool,         # jsonl 적재 성공 여부
          "skipped": bool,        # DISABLED 모드면 True
        }

    Step (a) 동작: input_n / target_n 만 jsonl 1줄 적재 후 빈 결과 반환.
    decision 영향 0 보장 — 호출자는 결과 무시하고 production filter 결과 사용.
    """
    if WIDE_SCAN_MODE == "DISABLED":
        return {
            "mode": "DISABLED", "label": LABEL,
            "input_n": len(stocks), "target_n": 0, "passed_n": 0,
            "logged": False, "skipped": True,
        }

    now_iso = run_at_iso or datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    input_n = len(stocks)
    target_n = int(input_n * WIDE_SCAN_TARGET_RATIO)

    # Step (a) — 7차원 스코어 미구현. 단순 카운트만 적재.
    # step (b) 에서 stocks 순회하며 7차원 score 계산 + 상위 22% 선출 + ticker 별 jsonl 1줄/종목.
    entry = {
        "ts": now_iso,
        "label": LABEL,
        "mode": WIDE_SCAN_MODE,
        "step": "a_infra",
        "input_n": input_n,
        "target_n": target_n,
        "passed_n": 0,
        "note": "step_a_skeleton — 7차원 스코어 미구현, jsonl 적재만 검증",
    }

    logged = _append_jsonl(entry)
    return {
        "mode": WIDE_SCAN_MODE, "label": LABEL,
        "input_n": input_n, "target_n": target_n, "passed_n": 0,
        "logged": logged, "skipped": False,
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
