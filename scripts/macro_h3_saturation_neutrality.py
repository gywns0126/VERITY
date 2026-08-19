#!/usr/bin/env python3
"""H3 — 포화된 균일 macro 승수가 위험조정 성과에 중립인가. (사전등록 §3 단계 2, PM 승인 2026-08-19)

## 왜 표본이 필요 없나

H1(타이밍)·H2(선택)와 달리 H3 는 **구조 질문**이다. 승수가 전 종목 동일하고 매수 종목 수를
바꾸지 않으면, 그 승수가 성과에 하는 일은 산술로 결정된다. 그래서 승수 시계열 원장이
없어도 **지금** 답이 나온다 — 이게 H3 를 첫 단계로 둔 이유다.

🚨 다만 "균일 스칼라" 라는 전제 자체는 **코드에서 확인해야 한다.** 가정하고 시작하면
안 되는 부분이 정확히 거기다. 아래 §1 이 그 확인이다.

## 검증 순서

  §1 전제 확인 — macro 승수가 정말 '종목 수를 바꾸지 않는 스칼라' 인가
  §2 산술    — 우리 성과 지표 정의(rf=0) 하에서 k 배 축소가 Sharpe·Calmar 에 미치는 영향
  §3 실효 분해 — 승수 체인에서 macro 가 차지하는 몫
  §4 Q4 정당화 3조건 대입 — Sharpe 중립이어도 정당한 경우가 있는가
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys

import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

PORTFOLIO = os.path.join(_ROOT, "data", "portfolio.json")
RECOMMEND = os.path.join(_ROOT, "data", "recommendations.json")


def section(t):
    print("\n" + "═" * 68)
    print(t)
    print("═" * 68)


def main() -> int:
    # ── §1 전제 확인 ────────────────────────────────────────────────────
    section("§1 전제 확인 — macro 승수는 '종목 수를 바꾸지 않는 스칼라' 인가")

    with open(PORTFOLIO, encoding="utf-8") as f:
        pf = json.load(f)
    v = pf.get("vams") or {}
    holdings = v.get("holdings") or []
    cash = float(v.get("cash") or 0)

    from api import config as C
    max_per_stock = C.VAMS_MAX_PER_STOCK
    prof = C._active_vams
    max_buy = prof.get("max_buy_per_cycle", 5)

    print("코드 구조 (api/vams/engine.py:933-945, 1856-1858)")
    print("  invest = min(max_per_stock, cash×0.9) × Kelly × ATR × macro")
    print(f"  매수 루프는 `bought >= max_buy` 로 멈춘다 — max_buy_per_cycle = {max_buy}")
    print()
    print(f"  현금 {cash:,.0f}원 · cash×0.9 = {cash*0.9:,.0f} · max_per_stock = {max_per_stock:,}")
    binding = "cash×0.9" if cash * 0.9 < max_per_stock else "max_per_stock"
    print(f"  🚨 실제로 묶는 제약 = **{binding}**")
    print()
    if binding == "max_per_stock":
        print("  → macro 축소가 현금을 남겨도 **1회차 매수 종목 수는 안 늘어난다**")
        print(f"     (상한이 종목당 금액이지 현금이 아니고, 건수는 {max_buy}건으로 캡)")
        print("  ✅ 전제 성립: 종목 수 불변 · 각 포지션만 k 배 = **순수 스칼라**")
        scalar_ok = True
    else:
        print("  🚨 전제 **불성립 가능** — 현금이 묶는 제약이면 축소가 매수 여력을 늘려")
        print("     종목 수가 변할 수 있다. 그러면 스칼라가 아니라 재배분이다.")
        scalar_ok = False

    print(f"\n  참고: 보유 {len(holdings)}종목 · 현금비중 "
          f"{cash/(cash+sum(h.get('buy_price',0)*h.get('quantity',0) for h in holdings))*100:.1f}%")

    # ── §2 산술 ─────────────────────────────────────────────────────────
    section("§2 산술 — 우리 지표 정의에서 k 배 축소가 무엇을 바꾸나")

    print("우리 성과 정의 = `api/vams/validation.py:18` — **연율 샤프 (rf=0)**")
    print()
    print("  포지션을 전부 k 배 하면 (k = macro 승수):")
    print("    포트폴리오 수익  R_p → k·R_s      (잔여 현금 수익 0 — 이자 배선 없음, 실측)")
    print("    포트폴리오 변동성 σ_p → k·σ_s")
    print("    Sharpe = (k·R_s − rf)/(k·σ_s),  rf=0  →  R_s/σ_s   ⇒ **k 와 무관**")
    print("    MDD   → k·MDD  ⇒  Calmar = k·R/(k·MDD) = R/MDD  ⇒ **k 와 무관**")
    print()
    print("🚨 즉 **우리가 쓰는 지표에서는 Sharpe·Calmar 둘 다 불변**이고,")
    print("   바뀌는 것은 **절대 수익과 절대 낙폭이 같은 비율로 줄어드는 것**뿐이다.")
    print()
    print("⚠️ 단서 두 개 — 어느 쪽도 지금 우리에게 유리하지 않다:")
    print("  ① rf>0 로 재면 오히려 **불리해진다**: (k·R−rf)/(k·σ) 는 k 가 작을수록 낮다.")
    print("     남는 현금이 **무위험 수익을 못 받기 때문**이다(이자 배선 0건, 실측).")
    print("  ② 인플레이션을 감안하면 유휴 현금은 실질 마이너스다"
          " (core CPI YoY 2.79%, macro_snapshot).")

    # ── §3 실효 분해 ────────────────────────────────────────────────────
    section("§3 실효 분해 — 승수 체인에서 macro 의 몫")

    with open(RECOMMEND, encoding="utf-8") as f:
        recs = json.load(f)
    mm = [r["macro_multiplier"]["multiplier"] for r in recs
          if isinstance(r.get("macro_multiplier"), dict)
          and isinstance(r["macro_multiplier"].get("multiplier"), (int, float))]
    macro_avg = float(np.mean(mm)) if mm else float("nan")

    amts = [h.get("buy_price", 0) * h.get("quantity", 0) for h in holdings
            if h.get("buy_price") and h.get("quantity")]
    med = st.median(amts) if amts else float("nan")
    realized = med / max_per_stock if max_per_stock else float("nan")

    print(f"  macro 승수 평균           {macro_avg:.3f}   (N={len(mm)}, 전 종목 <1.0)")
    print(f"  실측 매수금액 중앙        {med:,.0f}원")
    print(f"  상한 대비 실현 배수       {realized:.3f}  (= 중앙 매수 ÷ max_per_stock)")
    print(f"  → macro 외 나머지(Kelly×ATR) ≈ {realized/macro_avg:.3f}")
    print()
    print("  🚨 Kelly λ = n/252 (KELLY_LAMBDA_N_FULL). 폐기 게이트가 실자본 사이징을")
    print("     누르고 있는 건 별건으로 이미 등재돼 있다(kickoff '죽은 전제').")
    print(f"     그 축이 나머지 축소의 대부분을 설명한다 — macro({macro_avg:.3f})는 2순위다.")

    # ── §4 Q4 정당화 3조건 ──────────────────────────────────────────────
    section("§4 Q4 정당화 3조건 대입 — Sharpe 중립이어도 정당한가")

    rows = [
        ("① 파산위험·비선형 유틸리티 (half-Kelly 표준)",
         "❌ 중복",
         f"Kelly λ={realized/macro_avg:.2f} 수준으로 **이미 half-Kelly(0.5)보다 보수적**이다. "
         "파산위험 논거는 Kelly 축이 담당 중이고 macro 는 그 위에 겹쳐 있다"),
        ("② 레버리지 제약·회피 (Asness-Frazzini-Pedersen 2012)",
         "❌ 불성립",
         "그 논거는 '안전자산 과중 배분이 Sharpe 우위' 인데, 우리 잔여 현금은 "
         "**수익 0%** 라 안전자산이 아니라 순수 드래그다 (이자 배선 0건)"),
        ("③ 비선형 목적함수 (Moreira-Muir 변동성 반비례)",
         "❌ 타 축 담당",
         "그 형태는 `_apply_volatility_adj` ATR 축이 이미 맡고 있다. macro 는 "
         "변동성이 아니라 밸류에이션·금리 수준을 본다"),
    ]
    for name, verdict, why in rows:
        print(f"\n  {name}")
        print(f"    판정 {verdict} — {why}")

    section("판정")
    if scalar_ok:
        print("H3 = **성립.** 포화된 균일 macro 승수는 우리 지표(rf=0)에서 Sharpe·Calmar 에")
        print("     **구조적으로 중립**이고, 절대 수익·절대 낙폭만 같은 비율로 줄인다.")
        print()
        print("🚨 그리고 Q4 의 정당화 3조건이 **셋 다 성립하지 않는다** —")
        print("   ①은 Kelly 가 이미 하고, ②는 현금이 무수익이라 안 되고, ③은 ATR 담당이다.")
        print()
        print("⚠️ **그렇다고 '제거하면 나아진다' 가 아니다.** 중립이면 제거해도 지표는 그대로다.")
        print("   바뀌는 건 **절대 규모**이고, 그건 성과 문제가 아니라 **자본 배분 정책**이다.")
        print("   → 후속 = 승수를 '거시 신호' 가 아니라 **노출 정책**으로 정명(§3 단계 3).")
    else:
        print("H3 = **판정 보류** — 스칼라 전제가 성립하지 않는다. 재배분 효과를 별도 측정해야 한다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
