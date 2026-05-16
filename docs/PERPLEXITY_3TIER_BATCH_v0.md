# Perplexity Batch Query — VAMS 3-Tier 모드 검증

**용도**: 사용자가 Perplexity Pro (Sonar Pro 권장) 에 batch query 1회 호출.
**대상 결정**: [[project_capital_3tier_mode]] — 보수 60% / 중간 30% / 공격 10% 3-Tier hybrid 설계의 학계/실무 검증.
**시점**: 5/17 이후 진입 전 (ATR Phase 0 verdict 후).

## Context 전달용 prefix (Perplexity 답 quality ↑)

```
나는 1인 한국 개인 PM이다. 한국 KOSPI/KOSDAQ + 미장 NYSE/NASDAQ 종목을 자체
시스템(VERITY)으로 운영한다. 현 상황:
- 시드 ~1000만원 시뮬 단계 (실제 시드는 전역 후 ~13개월 후 본격 투입)
- 베타 38일차, 단일 PM, 자동화 + 룰 기반 (Brain v5 점수 + ATR 손절 + R-multiple 익절)
- 한국 세제: 주식 매매차익 비과세 (대주주 50억 이상 제외), 1년 미만 단타 33% (해외주식)
- 목표: 2028 황금알 거위 (Calmar 1.0+, MDD 20% 미만, All-weather)

설계 중: VAMS 자본을 3-Tier 로 분할 — 보수 60% / 중간 30% / 공격 10%.
시그널 (Brain verdict / Filter funnel 결과) 은 공유하되, Tier 별로 자본 분배 +
포지션 룰 차별 (포지션 크기 / ATR 손절 multiplier / R-multiple 익절 단계 / 종목 수 등).

다음 6개 질문에 답하라. 각 답에 학계/실무 출처 (CFA / Markowitz / Kelly /
Yale Endowment / Bridgewater / Korean academic 등) 명시. 한국 시장 적용 시
조정 사항 별도 명시.
```

---

## Q1 — 자본 분배 비율 (60/30/10) 학계 검증

> 1인 PM 이 시드를 "보수/중간/공격" 3 bucket 으로 분할할 때, 학계/실무 권위
> 분배 비율은? 60/30/10 이 표준인가, 아니면 50/30/20 또는 70/20/10 등 다른
> 비율이 더 typical 한가?
>
> 검토 frameworks:
> - Yale Endowment Model 의 자산 클래스 분배
> - Markowitz Mean-Variance + Sharpe maximization
> - Kelly Criterion (full Kelly vs fractional Kelly)
> - Risk Parity (각 bucket 의 risk contribution 균등)
> - All-weather 4-quadrant 분배
>
> 한국 개인 1인 PM (시드 1000만원~1억 range) 에 가장 적합한 비율 권고 +
> 그 이유 + 한국 시장 특수성 (KOSPI 변동성 / 한국 세제 / 한국 채권 yield).

---

## Q2 — Tier 별 룰 차별 (포지션 size / 손절 / 익절 / 종목 수)

> 같은 시그널을 보수/중간/공격 Tier 가 어떻게 다르게 운영해야 하는가?
> 학계/실무 권위 룰:
>
> (a) **포지션 크기** — 각 Tier 내 단일 종목 max %  (보수 5%? 공격 15%?)
> (b) **ATR 손절 multiplier** — 보수 = ATR×3.5 (널널)? 공격 = ATR×1.5 (타이트)?
> (c) **R-multiple 익절 단계** — 보수 = 50/30/20 (조기 익절 + 트레일링)?
>      공격 = 30/30/40 (트레일링 비중 ↑, 멀티배거 노리기)?
> (d) **종목 수** — 보수 = 15-20 종목 분산? 공격 = 5-8 집중?
> (e) **거래 빈도** — 보수 = buy-and-hold (회전율 < 0.5/yr)?
>      공격 = active rotation (회전율 2-3/yr)?
> (f) **종목 선정 필터** — 보수 = Quality (ROE/F-Score/Altman Z)?
>      공격 = Growth/Momentum (EPS 가속 / 52w high breakout)?
>
> 각 항목에 학계 권위 (e.g., Carhart 4-factor / Fama-French / O'Shaughnessy
> What Works on Wall Street / O'Neil CANSLIM / Lynch / Buffett) 매핑.
> 한국 시장 적용 시 조정 사항 명시.

---

## Q3 — Hybrid 구조 (시그널 공유 + 자본/룰 차별) 실무 사례

> "동일 시그널 source + Tier 별 자본/룰 차별" 구조의 실무 운영 사례:
> - 헤지펀드 multi-strategy fund 사례 (Bridgewater All Weather + Pure Alpha?)
> - 자산운용사 sleeve 구조 (BlackRock / Vanguard)
> - 개인 PM / family office 사례
> - 학계 논문 (multi-bucket allocation, modular portfolio construction)
>
> 시그널 공유 + 룰 차별 vs 시그널 자체도 Tier 별 차별의 trade-off.
> 시그널 quality 검증 단계 (1인 베타 38일차 + 운영 데이터 누적 중) 에서
> 어느 구조가 더 robust 한가?

---

## Q4 — Tier 간 자본 재배분 trigger (회귀 / 조정 규칙)

> 시간이 지나면서 Tier 비율 60/30/10 이 시장 변동에 따라 drift 한다.
> 재배분 trigger 학계/실무 권위:
>
> (a) **시간 기반** — 분기 1회 rebalance (가장 흔함)? 월 1회? 연 1회?
> (b) **편차 기반** — 목표 비율 ±5% drift 시? ±10%?
> (c) **regime 기반** — VIX > 30 시 공격 → 보수 자동 이동?
>      [[project_market_horizon]] euphoria verdict 시 공격 축소?
> (d) **Drawdown 기반** — 공격 Tier MDD > 30% 시 일시 중단?
>
> Yale Endowment / Bridgewater 의 rebalance 룰 + 한국 개인 적용 시
> 거래 비용 (수수료 + 세금 33% 단타 회피) 고려한 권고 빈도.

---

## Q5 — 시드 사이즈별 3-Tier 의미 (1000만원 / 1억 / 10억)

> 3-Tier 의 효용은 시드 사이즈에 따라 다르다:
>
> (a) **시드 1000만원**: 60/30/10 = 600/300/100만원. 100만원 공격 Tier
>     에서 5 종목 분산 시 종목당 20만원 — 의미 있는 entry? 거래 비용 비율?
>     이 사이즈에서 3-Tier 가 정말 ROI 가 있는가? 아니면 단일 Tier 가 나은가?
> (b) **시드 1억**: 60/30/10 = 6000/3000/1000. 적정 entry size?
> (c) **시드 10억**: 60/30/10 = 6/3/1억. 헤지펀드 small-cap 임팩트?
>
> "3-Tier 의 운영 break-even 시드 사이즈" 학계 / 실무 권위 추정.
> 한국 개인 (수수료 0.015% 평균 + 양도세 면제 - 대주주 50억 제외) 기준.

---

## Q6 — Tier 별 평가 지표 차별 (Sharpe / Sortino / Calmar / 절대수익)

> 보수/중간/공격 Tier 의 평가 지표는 같아야 하는가, 달라야 하는가?
> 학계 권고:
>
> (a) **보수 Tier**: Sortino (downside-only) + max DD + 채권 대비 alpha?
> (b) **중간 Tier**: Sharpe + 시장 alpha + IR (information ratio)?
> (c) **공격 Tier**: 절대수익 + Calmar + 멀티배거 hit rate?
>
> 또는 통일된 지표 (Sharpe / Calmar) 로 Tier 비교가 더 합리적?
> 1인 PM 의 KPI dashboard 권위 frameworks (CFA Performance Attribution /
> GIPS / Bridgewater 의 internal scoring 등).
> 한국 시장 적용 시 무위험수익률 base (한국 국고채 10y) + 벤치마크
> (KOSPI200 / KOSDAQ150) 권고.

---

## 답 받은 후 처리 (사용자 액션)

1. Perplexity 답 받으면 `docs/PERPLEXITY_3TIER_ANSWERS_<날짜>.md` 에 저장
2. 답 6개를 [[project_capital_3tier_mode]] 메모리에 cross-link
3. 사용자 PM 결정:
   - 비율 60/30/10 유지 또는 조정 (Q1 답)
   - Tier 별 룰 차별 산식 박음 (Q2 답)
   - rebalance 룰 결정 (Q4 답)
   - 평가 지표 박음 (Q6 답)
4. 결정 commit 시 [[feedback_pm_decision_trail_in_commit]] 정합:
   `WHY: Perplexity 권위 (출처 인용) + 한국 시장 조정 / DATA: Q1-Q6 답 ref / EXPECTED: ...`

## 비용
- Perplexity Sonar Pro 1 batch = ~$0.10 (6 query bundled)
- ROI: 3-Tier 운영 잘못 박힐 시 → 1인 PM 운영 6개월~1년 시간 낭비 위험. $0.10 검증 가치 압도적
