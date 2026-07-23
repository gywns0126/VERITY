#!/usr/bin/env python3
"""publish-data: 공개 발행본 portfolio.json 에서 VERITY 오퍼레이터 크라운주얼(top-level) strip.

VERITY↔AlphaNest 분리 Stage 3 (2026-07-23). 무인증 공개 Blob 의 portfolio.json 이 오퍼레이터 크라운주얼
(vams 자본/포지션·verity_brain·factor_ic·validation·evolution·market_horizon·decision_queue·trade_plan 등)을
top-level 로 그대로 노출 → curl 로 누구나 읽음. AlphaNest 공개(public-probe)는 portfolio.json 에서 뉴스 3키
(headlines/bloomberg_google_headlines/us_headlines)만 읽음(2026-07-23 소비경계 검증, 0 오분류).

원본 data/portfolio.json(오퍼레이터 authed 소스 = private Supabase Storage 로 별도 업로드, 발행 전 단계)은
무변경. _public_dist 발행 복사본에서만 STRIP_KEYS 제거. blocklist 방식 = AlphaNest 미파손(공개 필요 키
전부 잔존, 크라운주얼만 제거).

⚠️ 이 strip 후 공개 blob portfolio.json 은 크라운주얼 없음 → 옛 오퍼레이터 콘솔(공개 blob 직접 읽던 것)은
데이터 소실(의도 — /api/admin?type=portfolio_full authed 로 이전, 콘솔 리디자인 예정). AlphaNest 무영향.
"""
from __future__ import annotations

import json
import sys

# 오퍼레이터 크라운주얼 top-level 키 (RULE 6/7 자기 자산 — 공개 blob 제외). 소비경계 매핑(2026-07-23) PRIVATE 세트.
STRIP_KEYS = {
    # 자본·성과 (VAMS)
    "vams", "vams_profiles", "portfolio_summary", "safe_recommendations",
    # Brain 내부
    "verity_brain", "brain_accuracy", "brain_quality", "brain_evolution_log",
    "dual_model_weights", "brain_weights_cv", "ai_leaderboard",
    # 검증·진화·백테스트
    "validation", "evolution", "strategy_evolution", "postmortem",
    "postmortem_auto_evolve", "backtest_stats", "cross_verification", "verification_report",
    # 자체 산식·신호·판단레이어
    "factor_ic", "value_hunt", "market_horizon", "decision_queue",
    "trade_plan_meta", "trade_plan_evolution_signals", "regime_diagnostics", "stat_arb",
    "lynch_kr_distribution", "atr_migration", "dart_importance_obs", "trend_overlay",
    "sector_rotation_check", "sector_rotation", "event_insights",
    # 오퍼레이터 브리핑·알림 (Brain stance 누출 — "브레인 등급 관망 상한" 등)
    "alerts", "briefing",
    # 우리 분석 출력 (커버리지·데이터소스·감성 IP 누출) + AAII 재배포 라이선스 잔여
    "commodity_impact", "geopolitical_hotspots", "alt_data",
    "us_sentiment", "x_sentiment",
    # 운영·인프라 텔레메트리
    "system_health", "cost_monitor", "observability", "trail_integrity",
    "field_coverage", "price_pulse_meta", "krx_openapi", "daily_actions",
    # 내러티브 리포트 (등급 분포·실현손익 embed)
    "daily_report", "daily_report_us", "weekly_report", "monthly_report",
    "quarterly_report", "semi_report",
    "daily_report_updated", "weekly_report_updated", "monthly_report_updated",
    "quarterly_report_updated", "semi_report_updated",
}


def main(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        # fail-safe: 형식 미인지·로드 실패 시 원본 유지하지 않고 오히려 발행 차단이 안전하나,
        # 공개본이 이미 복사됐으므로 로그 명시 후 skip (원본 크라운주얼 노출 잔존 = 상위 게이트가 감지).
        print(f"sanitize_portfolio_public: 로드 실패({e}) — skip (⚠️ 크라운주얼 잔존 가능)")
        return 0
    if not isinstance(doc, dict):
        print("sanitize_portfolio_public: dict 아님 — skip")
        return 0

    stripped = [k for k in STRIP_KEYS if k in doc]
    for k in stripped:
        doc.pop(k, None)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))

    print(f"sanitize_portfolio_public: 크라운주얼 {len(stripped)}키 strip · 잔존 top키 {len(doc)}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: sanitize_portfolio_public.py <path/to/portfolio.json>")
        sys.exit(1)
    sys.exit(main(sys.argv[1]))
