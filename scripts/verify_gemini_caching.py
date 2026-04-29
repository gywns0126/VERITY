#!/usr/bin/env python3
"""Gemini 컨텍스트 캐싱 적용 후 검증 스크립트.

사용:
  # 구조적 점검만 (API 호출 없음, 무료)
  python3 scripts/verify_gemini_caching.py --dry-run

  # 실제 호출 1회 (1종목 분석, ~₩5 미만)
  python3 scripts/verify_gemini_caching.py

  # 캐시 히트 확인용 2회 호출 (~₩10)
  python3 scripts/verify_gemini_caching.py --twice

체크 항목:
  1. system_instruction 크기 ≥ 1024 토큰 (Flash 캐시 최소 통과)
  2. caches.create() 성공 여부
  3. 두 번째 호출 시 cached_content_token_count > 0 (캐시 적중)
  4. 출력 JSON 의 필수 키 존재 (recommendation/ai_verdict/risk_flags 등)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _make_fixture_stock() -> dict:
    """캐싱 검증용 최소 종목 fixture. 실제 main.py 흐름과 호환되는 키 셋."""
    return {
        "ticker": "005930",
        "name": "삼성전자",
        "market": "KOSPI",
        "price": 78500,
        "market_cap": 468_000_000_000_000,
        "trading_value": 850_000_000_000,
        "per": 14.2, "pbr": 1.3, "div_yield": 1.8,
        "drop_from_high_pct": -8.4,
        "debt_ratio": 25.3, "operating_margin": 18.4, "roe": 9.2,
        "technical": {
            "rsi": 52, "macd_hist": 0.3, "bb_position": 55,
            "vol_ratio": 1.1, "trend_strength": 0.6,
            "price_change_pct": 0.8, "signals": ["RSI 중립"],
        },
        "sentiment": {"score": 58, "headline_count": 12, "detail": []},
        "flow": {"foreign_net": 1_200_000, "institution_net": -450_000,
                 "foreign_5d_sum": 5_300_000, "institution_5d_sum": -2_100_000},
        "multi_factor": {"multi_score": 72, "grade": "BUY",
                        "factor_contribution": {"value": 18, "growth": 22, "momentum": 16, "quality": 16},
                        "regime": "neutral"},
        "prediction": {"up_probability": 58, "method": "XGBoost"},
        "backtest": {"win_rate": 62, "sharpe_ratio": 1.4, "total_trades": 30},
        "verity_brain": {"brain_score": 71, "grade": "BUY"},
    }


def check_sys_instr_size() -> bool:
    from api.analyzers.gemini_analyst import _load_system_instruction
    si = _load_system_instruction()
    rough_tokens = len(si) // 2.5  # 한국어 평균
    print(f"  system_instruction: {len(si)} chars, ~{rough_tokens:.0f} tokens")
    if rough_tokens >= 1024:
        print(f"  \033[92m✓ Flash 캐시 최소(1024) 통과\033[0m")
        return True
    print(f"  \033[93m⚠ 1024 미만 — 캐시 생성 거부될 수 있음\033[0m")
    return False


def run_live_call(twice: bool = False) -> None:
    if not os.environ.get("GEMINI_API_KEY"):
        print("\033[91mGEMINI_API_KEY 미설정 — 라이브 호출 불가\033[0m")
        sys.exit(2)

    from api.analyzers.gemini_analyst import init_gemini, analyze_stock
    from api.utils.gemini_cache import cache_stats

    client = init_gemini()
    stock = _make_fixture_stock()

    print("\n[1차 호출] (캐시 생성 시도)")
    r1 = analyze_stock(client, stock)
    _print_result("1차", r1)
    print(f"  cache_stats: {cache_stats()}")

    if twice:
        print("\n[2차 호출] (캐시 히트 기대)")
        r2 = analyze_stock(client, stock)
        _print_result("2차", r2)
        print(f"  cache_stats: {cache_stats()}")
        print("\n2차 응답에 cached_content_token_count 확인은 tracer 로그 또는 "
              "response.usage_metadata 직접 확인. 이 스크립트는 analyze_stock "
              "결과만 받으므로 raw 응답은 보지 않음.")


def _print_result(label: str, result: dict) -> None:
    required = ["company_tagline", "ai_verdict", "recommendation", "risk_flags",
                "confidence", "gold_insight", "silver_insight"]
    missing = [k for k in required if k not in result]
    print(f"  {label} 결과 키: {sorted(result.keys())}")
    if missing:
        print(f"  \033[91m✗ 누락 키: {missing}\033[0m")
    else:
        print(f"  \033[92m✓ 필수 키 모두 존재\033[0m")
    print(f"  recommendation: {result.get('recommendation')}")
    print(f"  ai_verdict: {(result.get('ai_verdict') or '')[:80]}")
    print(f"  gold_insight: {(result.get('gold_insight') or '')[:80]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="API 호출 없이 구조 점검만")
    ap.add_argument("--twice", action="store_true", help="2회 호출로 캐시 적중 확인")
    args = ap.parse_args()

    print("[STEP 1] system_instruction 크기 점검")
    ok = check_sys_instr_size()

    if args.dry_run:
        print("\n[dry-run] API 호출 생략. 라이브 검증은 인자 없이 재실행하세요.")
        return 0 if ok else 1

    print("\n[STEP 2] 라이브 호출 + 출력 키 검증")
    run_live_call(twice=args.twice)
    return 0


if __name__ == "__main__":
    sys.exit(main())
