#!/usr/bin/env python3
"""
VERITY Chat Hybrid — 월 비용 시뮬레이터

단위 비용 (측정치 기반):
  분류기 (Gemini flash-lite): ~$0.0001/call
  Perplexity sonar:           $0.002-0.009/call  (평균 $0.005)
  Perplexity sonar-pro:       ~$0.02/call
  Gemini Grounding:           $0.003/call
  Claude Sonnet 합성:         $0.01-0.02/call (평균 $0.012)
  Brain (로컬):               $0

트래픽 가정 (조정 가능):
  일일 활성 사용자: 10 (본인 + 내부 테스터)
  사용자당 일일 질문: 5
  intent 분포: 30% portfolio_only + 30% hybrid + 30% external_only + 10% greeting
  hybrid 중: 70% simple sonar, 10% complex sonar-pro
  external_only 중: 50% grounding 만, 50% perplexity+grounding

캐시 효과:
  classifier: 10분 TTL → 예상 hit_rate 40% (반복 질문)
  perplexity: 3분 TTL → 예상 hit_rate 15%
  grounding:  3분 TTL → 예상 hit_rate 20% (FOMC 등 고정 fact)

목표 cap: 월 $30 — 이 아래로 유지.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class CostModel:
    # per-call USD
    classifier: float = 0.0001
    perplexity_simple: float = 0.005
    perplexity_complex: float = 0.02
    grounding: float = 0.003
    synth: float = 0.012

    # cache hit rate (0-1)
    classifier_hit: float = 0.40
    perplexity_hit: float = 0.15
    grounding_hit: float = 0.20


@dataclass
class TrafficMix:
    daily_users: int = 10
    q_per_user_day: int = 5
    # intent 분포 합은 1.0
    portfolio_only: float = 0.30
    hybrid: float = 0.30
    external_only: float = 0.30
    greeting: float = 0.10
    # hybrid 안의 Perplexity 분포
    p_complex_ratio: float = 0.10  # sonar-pro 비율 (10%)
    # external_only 안의 Perplexity 병행 비율
    ext_with_p: float = 0.50


@dataclass
class Estimate:
    total_qs: int
    per_stage: Dict[str, float] = field(default_factory=dict)

    @property
    def total(self) -> float:
        return round(sum(self.per_stage.values()), 4)

    def display(self, period: str, tm: TrafficMix):
        print(f"\n=== {period} 추정 (DAU {tm.daily_users} × {tm.q_per_user_day} 질문) ===")
        print(f"  총 질문수:          {self.total_qs:,}")
        for stage, cost in self.per_stage.items():
            print(f"  {stage:<20} ${cost:>8.4f}")
        print(f"  {'─'*30}")
        print(f"  합계:               ${self.total:>8.4f}")


def estimate(days: int, tm: TrafficMix, cm: CostModel) -> Estimate:
    total_q = int(tm.daily_users * tm.q_per_user_day * days)

    # 분류기: 항상 호출 (greeting 은 규칙 기반 분기)
    non_greeting = total_q * (1 - tm.greeting)
    classifier_calls = non_greeting * (1 - cm.classifier_hit)

    # 합성(Claude): 모든 응답 (greeting 포함)
    synth_calls = total_q

    # Perplexity: hybrid 70% (simple) + hybrid 10% (complex) + external_only×ext_with_p
    hybrid_qs = total_q * tm.hybrid
    external_qs = total_q * tm.external_only
    p_simple = (hybrid_qs * (1 - tm.p_complex_ratio)) + (external_qs * tm.ext_with_p * (1 - tm.p_complex_ratio))
    p_complex = (hybrid_qs + external_qs * tm.ext_with_p) * tm.p_complex_ratio
    p_simple *= (1 - cm.perplexity_hit)
    p_complex *= (1 - cm.perplexity_hit)

    # Grounding: external_only 100% + hybrid 30% (factual 혼합)
    g_calls = external_qs * 1.0 + hybrid_qs * 0.30
    g_calls *= (1 - cm.grounding_hit)

    est = Estimate(total_qs=total_q)
    est.per_stage["classifier"] = round(classifier_calls * cm.classifier, 4)
    est.per_stage["perplexity_simple"] = round(p_simple * cm.perplexity_simple, 4)
    est.per_stage["perplexity_complex"] = round(p_complex * cm.perplexity_complex, 4)
    est.per_stage["grounding"] = round(g_calls * cm.grounding, 4)
    est.per_stage["synth_claude"] = round(synth_calls * cm.synth, 4)
    return est


def scenario_table(label: str, tm: TrafficMix, cm: CostModel, cap: float = 30.0):
    e_day = estimate(1, tm, cm)
    e_mon = estimate(30, tm, cm)
    print(f"\n╔══ {label} ══════════════════════════════════════════════")
    e_day.display("일일", tm)
    e_mon.display("월간 (30일)", tm)
    ratio = e_mon.total / cap * 100
    status = "✓ OK" if e_mon.total <= cap else "✗ CAP 초과"
    print(f"\n  월 비용 / ${cap} cap: {ratio:.1f}% [{status}]")
    print("╚══════════════════════════════════════════════════════════")
    return e_mon.total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=10, help="일일 활성 사용자")
    ap.add_argument("--qpd", type=int, default=5, help="사용자당 일일 질문")
    ap.add_argument("--cap", type=float, default=30.0, help="월 cap ($)")
    ap.add_argument("--json", action="store_true", help="JSON 출력")
    args = ap.parse_args()

    cm = CostModel()
    base = TrafficMix(daily_users=args.users, q_per_user_day=args.qpd)

    if args.json:
        e_mon = estimate(30, base, cm)
        print(json.dumps({
            "monthly_total_usd": e_mon.total,
            "breakdown": e_mon.per_stage,
            "cap": args.cap,
            "ratio_pct": round(e_mon.total / args.cap * 100, 1),
            "within_cap": e_mon.total <= args.cap,
        }, indent=2))
        return

    print(f"VERITY Chat Hybrid 비용 시뮬레이션")
    print(f"캐시 히트율: classifier {cm.classifier_hit*100:.0f}% · perplexity {cm.perplexity_hit*100:.0f}% · grounding {cm.grounding_hit*100:.0f}%")

    # 시나리오 3종: 예상 / 낙관 / 비관
    scenario_table("예상 (설정값)", base, cm, args.cap)

    # 낙관: 캐시 40% 더 잘 맞음
    cm_opt = CostModel(
        classifier_hit=0.55, perplexity_hit=0.30, grounding_hit=0.35,
    )
    scenario_table("낙관 (캐시 높음)", base, cm_opt, args.cap)

    # 비관: 사용자 2배 + 캐시 낮음
    tm_bad = TrafficMix(
        daily_users=args.users * 2, q_per_user_day=args.qpd,
    )
    cm_bad = CostModel(
        classifier_hit=0.10, perplexity_hit=0.05, grounding_hit=0.05,
    )
    total_bad = scenario_table("비관 (사용자 2배 · 캐시 낮음)", tm_bad, cm_bad, args.cap)

    print(f"\n경계: 비관 시나리오에서 ${total_bad:.2f} — cap ${args.cap} 내인지 반드시 모니터링.")
    print("실시간 cap: CHAT_HYBRID_DAILY_CAP (글로벌 일일 호출 수) 로 강제.")


if __name__ == "__main__":
    main()
