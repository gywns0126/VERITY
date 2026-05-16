# Perplexity Batch Query — VAMS 3-Tier 모드 검증 (v1)

**용도**: 사용자가 Perplexity Pro (Sonar Pro 권장, Reasoning 또는 Deep Research 모드면 더 좋음) 에 batch query 1회 호출.
**대상 결정**: [[project_capital_3tier_mode]] — 보수 60% / 중간 30% / 공격 10% 3-Tier hybrid 설계의 학계/실무 검증.
**시점**: 5/17 이후 진입 전 (ATR Phase 0 verdict 후).
**버전**: v1 (2026-05-17, 사용자 "무지 짧은디" 피드백 후 깊이 + 반증 + 한국 정밀 + 산출 format 보강).

---

## 0. Context Prefix (Perplexity 답 quality 우선용 — 반드시 첨부)

```
나는 한국 1인 개인 PM (직업군인, 전역일 2027-06-30 = ~13개월 후, 그 이후 풀타임 PM 전환).
운영 시스템 = VERITY (KOSPI/KOSDAQ + NYSE/NASDAQ 종목, 자체 룰 기반 Brain v5).

현 단계 (2026-05-17 기준):
- 시드 ~1000만원 시뮬 (VAMS). 실 시드 = 전역 후 ~13개월 후 본격 투입
- 베타 운영 ~38일차, 단일 PM, 자동화 (KIS API 직결 + ATR 동적 손절 + R-multiple 부분 익절 + Brain v5 점수 funnel)
- 한국 세제: 국내 주식 매매차익 비과세 (대주주 50억 이상 제외), 해외주식 1년 미만 33% / 1년 이상 22% (지방세 별도), 금투세 폐지 확정 (2025-01), 손실 이월공제 불가
- 운영 trail: 모든 PM 결정 commit 에 WHY/DATA/EXPECTED 명시 (PM 진화 trail 자산화 중)
- 목표: 2028 황금알 거위 (Calmar 1.0+, MDD 20% 미만, All-weather + Anti-fragile + Anti-FOMO)
- 다음 단계 (전역 후): 외부 자본 / 자문 / fund 진입 가능성

설계 진행 중: VAMS 자본을 3-Tier 분할 — 보수 60% / 중간 30% / 공격 10%.
시그널 (Brain verdict / Filter funnel 결과) 공유 + Tier 별 자본 분배 + 포지션 룰 차별
(포지션 크기 / ATR 손절 multiplier / R-multiple 익절 단계 / 종목 수 / 회전율 / 종목 선정 필터).

다음 10개 질문에 답하라. 답 quality 우선 (token 사용량 신경 X, Deep Research 권장).

**답 산출 형식 의무**:
1. 각 답에 학계/실무 출처 명시 (저자 / 연도 / 책 또는 논문 제목 / 페이지 가능 시).
   허용 source: CFA Institute, Markowitz, Sharpe, Kelly, Yale Endowment (David Swensen),
   Bridgewater (Ray Dalio), AQR (Cliff Asness), Renaissance, O'Shaughnessy, William O'Neil,
   Lynch, Buffett/Munger letters, Damodaran, Korean academic (KAIST / SNU 경영 / 자본시장연구원).
2. 구체 수치 권고 박음 (비율, multiplier, %, count). "상황 따라 다름" 같은 회피 답 금지.
3. **한국 시장 적용 시 조정 사항** 별도 박스 (KOSPI 변동성, 한국 세제, 한국 국고채 yield).
4. **반증 case** 별도 박스 (이 권고가 잘못된 경우 / edge case / blow-up scenario).
5. 표 형식 권장 (행/열 명확).
```

---

## Q1 — 자본 분배 비율 (60/30/10) 학계 권위 검증

> 1인 PM 이 시드를 "보수/중간/공격" 3 bucket 으로 분할할 때 학계/실무 표준 비율?
>
> 검토 frameworks (각각 비율 권고 + 산식 근거):
> - **Yale Endowment Model** (Swensen 2009 "Pioneering Portfolio Management"): asset class별 분배 어떻게?
> - **Markowitz Mean-Variance + Sharpe maximization**: efficient frontier 위 3 bucket 매핑?
> - **Kelly Criterion** (Full Kelly vs Fractional Kelly = 1/2 Kelly / 1/4 Kelly): 공격 Tier 사이즈 산식?
> - **Risk Parity** (Bridgewater All Weather): 각 bucket 의 risk contribution 균등?
> - **All-weather 4-quadrant** (성장/인플레이션/디플레이션/스태그플레이션): 4가 아닌 3 Tier 매핑 가능?
> - **Permanent Portfolio** (Harry Browne): 25% × 4 vs 3 Tier 변환?
> - **Coffeehouse Portfolio** / **Lazy Portfolio** (Bogle 추종): 단순화 비율?
>
> **요구 산출**:
> (a) 위 7 frameworks 각각의 권고 비율 표 (보수 % / 중간 % / 공격 %).
> (b) 한국 개인 1인 PM (시드 1000만원~1억 range, 전역 후 ~13개월) 에 가장 적합한 비율 + 그 이유.
> (c) 60/30/10 vs 50/30/20 vs 70/20/10 vs 80/15/5 vs 40/40/20 비교표 — 어떤 가정에서 어떤 게 최적?
> (d) **반증**: 이 비율이 자살행위인 경우 (시장 regime / 시드 사이즈 / PM 경력 / 심리) edge case.

---

## Q2 — Tier 별 룰 차별 산식 (구체 수치)

> 같은 시그널을 보수/중간/공격 Tier 가 어떻게 다르게 운영해야 하는가?
> 항목별 구체 수치 권고:
>
> (a) **포지션 크기** (단일 종목 max % of Tier):
>     - 보수: 5%? 8%? 10%?  (Kelly fractional 적용 산식)
>     - 중간: 10%? 12%?
>     - 공격: 15%? 20%? 25%?
>     - 한국 시장 적용 시 small-cap 거래량 고려 추가 cap?
>
> (b) **ATR 손절 multiplier** (현 VERITY = ATR(14)×2.5 단일):
>     - 보수: ATR×3.0~3.5 (널널, 흔들림 견딤)?
>     - 중간: ATR×2.5 (현 기준)?
>     - 공격: ATR×1.5~2.0 (타이트, 빠른 손절)?
>     - 학계 권위: Van Tharp "Trade Your Way" / Mark Douglas / Wilder ATR 원전 권고?
>
> (c) **R-multiple 익절 단계** (현 VERITY = 50/30/20 = 1R/2R/트레일링):
>     - 보수: 60/30/10 (조기 익절 ↑, 트레일링 ↓)?
>     - 중간: 50/30/20 (현 기준)?
>     - 공격: 30/30/40 (트레일링 ↑, 멀티배거 노리기)?
>     - 학계: Van Tharp / Schabacker / 한국 멀티배거 실증?
>
> (d) **종목 수** (Tier 내 분산 수):
>     - 보수: 15-20 (분산)?
>     - 중간: 10-12?
>     - 공격: 5-8 (집중)?
>     - 학계: Markowitz 분산 효과 marginal benefit / Statman 1987 "How Many Stocks Make a Diversified Portfolio?"
>
> (e) **회전율** (yr 기준):
>     - 보수: <0.5 (buy-and-hold)?
>     - 중간: 1.0~1.5?
>     - 공격: 2.0~3.0 (active rotation)?
>     - 한국 세제 (해외 1년 미만 33%) 가 회전율에 미치는 영향?
>
> (f) **종목 선정 필터** (signal source):
>     - 보수: Quality (Piotroski F-Score 8+ / Altman Z > 3 / ROE > 15% / 부채비율 < 100%)?
>     - 중간: Value+Quality (Fama-French value + Quality combo)?
>     - 공격: Growth/Momentum (CANSLIM / EPS 가속 / 52w high breakout / Jegadeesh-Titman momentum)?
>     - 한국 시장 적용 (KOSPI/KOSDAQ 구분, 금융주 sector_aware 제외)?
>
> **요구 산출**: 위 6 항목 × 3 Tier = 18 cell 표. 각 cell 에 구체 수치 + 학계 source + 한국 조정 + 반증.

---

## Q3 — Hybrid 구조 (시그널 공유 + 자본/룰 차별) 실무 사례 + 학계

> "동일 시그널 source + Tier 별 자본/룰 차별" 구조의 실무 / 학계 검증:
>
> (a) **실무 사례** (3개 이상, 구체 fund 이름 + 운영 방식):
>     - Bridgewater Pure Alpha vs All Weather (시그널 공유?)
>     - AQR multi-strategy (style sleeve 구조)
>     - 헤지펀드 multi-strategy umbrella 일반
>     - 자산운용사 sleeve / sub-portfolio
>     - 한국 운용사 사례 (한투/미래에셋/KB 자산운용 multi-asset)
>     - Family office 1인 PM 사례 (Norway Sovereign Wealth Fund / Yale Endowment 내부 구조)
>
> (b) **학계 논문** (저자, 연도, 결론):
>     - Modular portfolio construction 논문
>     - Multi-bucket allocation 효율성 vs 단일 portfolio
>     - 시그널 공유 + 룰 차별 vs 시그널 자체 차별의 trade-off
>
> (c) **시그널 quality 검증 단계 (1인 베타 38일차 + 운영 누적 중) 에서 어느 구조가 robust?**
>     - 시그널 검증 부족 단계에서 Tier 차별이 noise 증폭 시키나, 분산 효과 살리나?
>     - "단일 Tier 로 검증 누적 후 3-Tier 분할" 점진 전환 vs "처음부터 3-Tier" 직진의 효과 비교.
>
> (d) **반증**: 3-Tier hybrid 가 실패한 실제 사례 (펀드 close, drawdown, blow-up)?

---

## Q4 — Tier 간 자본 재배분 trigger (구체 룰)

> 시간이 지나면서 Tier 비율 60/30/10 이 시장 변동에 drift. 재배분 trigger:
>
> (a) **시간 기반**: 분기/월/연 1회? 가장 흔한 cadence + 학계 권위?
> (b) **편차 기반**: 목표 비율 ±5% / ±10% / ±20% drift 시 rebalance? Markowitz / Yale 룰?
> (c) **Regime 기반** (가장 정교):
>     - VIX > 30 → 공격 → 보수 자동 이동? VIX 임계 학계 권위?
>     - [[project_market_horizon]] 의 euphoria/recession verdict 시?
>     - 금리 인상 cycle / 인플레이션 regime / yield curve 역전?
>     - 학계: Risk On / Risk Off regime detection 논문 (Lasse Pedersen, AQR)
> (d) **Drawdown 기반**: 공격 Tier MDD > 20% / 30% / 50% 시 일시 중단? Calmar threshold?
> (e) **시그널 quality 기반**: Brain v5 verdict hit rate 가 ↓ 시 보수 ramp-up?
>
> **요구 산출**:
> - 5 trigger 종류 × 한국 개인 적용 권고표 (frequency / threshold / unwind 룰).
> - 거래 비용 (수수료 0.015% + 양도세) 고려한 ROI break-even.
> - **반증**: rebalance 자체가 alpha 죽이는 경우 (overtrading) edge case + Yale / Bridgewater 의 rebalance 지연 사례.

---

## Q5 — 시드 사이즈별 3-Tier 의미 (break-even 분석)

> 3-Tier 의 효용은 시드 사이즈 함수. 한국 개인 적용 시 구체 분석:
>
> (a) **시드 1000만원** (현 VAMS 시뮬):
>     - 60/30/10 = 600/300/100. 공격 Tier 100만원에서 5 종목 분산 시 종목당 20만원.
>     - 한국 KOSPI 종목 평균 가격 + 1주 entry 가능성? (삼성전자 7만원 = 3주 / 카카오 5만원 = 4주)
>     - 거래 수수료 (0.015%) + 슬리피지 비율 100만원 entry 에서 의미 있나?
>     - 결론: 이 사이즈에서 3-Tier 가 ROI 있는가, 단일 Tier 가 나은가?
> (b) **시드 1억** (전역 후 1차 본격):
>     - 60/30/10 = 6000/3000/1000만원. 적정 entry size?
>     - 분산 효과 / 거래 비용 / 한국 small-cap 임팩트?
> (c) **시드 10억** (성장 후):
>     - 60/30/10 = 6/3/1억. 헤지펀드 small-cap 시장 임팩트 risk?
>     - 한국 시장 (KOSPI200 + KOSDAQ150 vs 그 외) liquidity gradient?
>
> **요구 산출**:
> - "3-Tier 운영 break-even 시드" 구체 수치 + 산식 (Kelly / 거래 비용 ratio).
> - 사이즈별 권고 Tier 수 (1000만 = 1 Tier? 1억 = 2 Tier? 10억 = 3 Tier? 100억 = 5 Tier?).
> - 학계 권위 (institutional vs individual portfolio sizing).
> - **반증**: 단일 Tier 가 우월한 시드 / 시장 / 시기 case.

---

## Q6 — Tier 별 평가 지표 차별 (KPI dashboard)

> 보수/중간/공격 Tier 의 평가 지표 같아야 vs 달라야:
>
> (a) **각 Tier 의 핵심 KPI** (학계 권위):
>     - 보수: Sortino (downside-only) / max DD / 채권 대비 alpha / Treynor ratio?
>     - 중간: Sharpe / 시장 alpha / IR (information ratio)?
>     - 공격: 절대수익 / Calmar / 멀티배거 hit rate / Omega ratio?
> (b) **공통 메타 KPI**:
>     - 전체 portfolio Sharpe / Calmar / MDD / 회전율
>     - GIPS / CFA Performance Attribution 표준
> (c) **한국 시장 base / benchmark**:
>     - 무위험수익률: 한국 국고채 10y (현 ~3.5%)?
>     - 보수 벤치마크: KOSPI200 / 코덱스 200 / 채권 50:50?
>     - 중간 벤치마크: KOSPI total return?
>     - 공격 벤치마크: KOSDAQ150 / Russell 2000 / 코스닥 small-cap?
> (d) **Reporting cadence**:
>     - 월간 / 분기 / 연간 attribution + factor exposure?
>
> **요구 산출**:
> - 3 Tier × 5-7 KPI 표 + 한국 base/벤치마크 매핑 + 권고 reporting 빈도.
> - **반증**: 잘못된 KPI 사용 시 의사결정 왜곡 case (예: 공격 Tier 에 Sharpe 적용 = 멀티배거 단리 무시).

---

## Q7 — 1인 PM 의 blow-up risk 패턴 (공격 Tier 특히)

> 1인 PM 이 공격 Tier 에서 흔히 망하는 패턴 (실증 / 학계 / 행동재무학):
>
> (a) **포지션 sizing 실패**: Kelly Full 박는 사고 (Niederhoffer 1997 사례 등)
> (b) **수렴 실패 (FOMO / revenge trade)**: Damodaran 행동재무 사례
> (c) **레버리지 함정**: 한국 신용/미국 margin 사용 시 blow-up
> (d) **drawdown 처리 실패**: -30% 시 double-down 충동
> (e) **시그널 overfitting**: 1인 PM 이 자체 시그널 검증 부족 + 운영 → blow-up
> (f) **regime shift 못 잡음**: 2008 / 2020 / 2022 사례
> (g) **세제 함정**: 한국 1년 미만 33% 무시 거래
>
> **요구 산출**: 7 패턴 × 실제 사례 (이름 / 펀드 / 연도) + 1인 PM 방어 룰.

---

## Q8 — 한국 세제 정밀 반영이 Tier 분배에 미치는 영향

> 한국 개인 PM 세제:
> - 국내 주식: 매매차익 비과세 (대주주 50억 제외)
> - 해외 주식: 1년 미만 33%, 1년 이상 22% (지방세 별도)
> - 배당: 15.4% 원천징수
> - 금투세: 폐지 확정 (2025-01)
> - 손실 이월공제: 불가
>
> (a) 3 Tier 의 KR/US 종목 비중이 세제로 인해 어떻게 조정되어야?
>     - 보수 Tier = KR 위주 (비과세) + 1년 hold 미장?
>     - 공격 Tier = KR 단타 (비과세) + 미장 회피?
> (b) 1년 미만 33% 가 R-multiple 익절 단계에 미치는 영향:
>     - 1R 익절 (+1R = +5% 가정) - 33% = +3.35% 실수익 → 의미 있나?
>     - 트레일링 (+5R+ 가능) 후 1년 hold 22% 가 ROI 우월?
> (c) 손실 이월공제 불가 = 손절 후 익절 합산 시 세금 폭탄.
>     공격 Tier 회전율 ↑ → 세금 누적. 방어 룰?
> (d) 대주주 50억 anchor: 시드 50억 도달 시 Tier 재설계?
>
> **요구 산출**: KR/US 비중 권고표 × 3 Tier + 세후 수익률 모델 + 학계/실무 권위.

---

## Q9 — 시뮬 (VAMS) → 실거래 전환 protocol

> 1인 PM 이 시뮬레이션 (paper trading) 에서 검증 통과 후 실거래 전환 시 protocol:
>
> (a) **검증 기간 권고**:
>     - 시뮬 운영 N일 누적 시그널-결과 페어 (학계 표본 N 권위)?
>     - VERITY 현 38일 + 향후 65 거래일 게이트 (8월 말) 적절?
> (b) **소액 → 본격 ramp-up 단계** (학계 권위):
>     - 시드 1% → 10% → 30% → 100% 점진?
>     - 각 단계 검증 기준 (Sharpe / MDD / hit rate)?
> (c) **paper 와 실거래의 격차** (slippage / 심리 / 실행):
>     - 학계 추정: paper alpha 대비 실거래 alpha 평균 -20~-50%?
>     - 1인 PM 자동화 (KIS API) 가 격차 줄이나?
> (d) **3-Tier 단계별 도입**:
>     - 보수 Tier 먼저 실거래 → 6개월 검증 후 중간 → 그 후 공격?
>     - 또는 3 Tier 동시 소액 시작?
>
> **요구 산출**: 시뮬→실거래 전환 timeline 표 + 단계별 검증 KPI + 한국 1인 PM 사례.

---

## Q10 — 메타: 이 3-Tier 설계의 critical flaw 5건

> 위 설계 전체 (60/30/10 + 시그널 공유 + Tier 룰 차별 + 한국 세제 + 시드 1000만원~1억 range) 의 critical flaw 5건:
>
> (a) 가장 큰 blind spot?
> (b) 1년 후 retrospective 시 가장 후회할 결정?
> (c) 학계/실무 권위에서 이 설계가 부정될 가능성?
> (d) 1인 PM 베타 38일차의 약점이 3-Tier 에서 증폭되는 부분?
> (e) 한국 시장 특수성 (소수 종목 dominance / regulatory cycle / 산업구조) 미반영 부분?
>
> 솔직한 반대 의견 + 대안 권고. "Yes-Man" 답 거부.

---

## 답 받은 후 처리 (사용자 액션)

1. Perplexity 답 받으면 `docs/PERPLEXITY_3TIER_ANSWERS_<날짜>.md` 에 저장 (raw 그대로)
2. 답 10개를 [[project_capital_3tier_mode]] 메모리에 cross-link
3. **Critical flaw Q10 답 = 우선 처리** (설계 자체 회귀 필요할 수도)
4. 사용자 PM 결정:
   - 비율 (Q1) — 60/30/10 유지 vs 조정
   - Tier 별 룰 (Q2 18 cell 표) — 박음
   - 재배분 룰 (Q4) — 결정
   - 시드 break-even (Q5) — 단일 Tier vs 3-Tier 결정
   - KPI dashboard (Q6) — 박음
   - 한국 세제 정합 (Q8) — KR/US 비중 결정
   - 실거래 protocol (Q9) — timeline 박음
5. 결정 commit 시 [[feedback_pm_decision_trail_in_commit]] 정합 (WHY=Perplexity 권위 출처 / DATA=Q1-Q10 답 ref / EXPECTED=...)

## 비용
- Perplexity Sonar Pro 1 batch (Deep Research 모드) = ~$0.20-0.40
- ROI: 3-Tier 잘못 박힐 시 → 1인 PM 운영 6개월~1년 시간 낭비 + 시드 손실 risk. 검증 비용 압도적
- Q10 critical flaw 답 1개만으로도 $0.40 가치 충분 (설계 자체 회귀 가능)
