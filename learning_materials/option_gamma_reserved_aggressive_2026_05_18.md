# Option γ Reserved — 학계 권고 전체 추종 (공격적 운용)

- 생성: 2026-05-18 02:35 KST
- 트리거 사유: 5/18 PM 결정 시점 = 시드 1000만 (VAMS reset 0거래일) → γ 거절, β 채택
- **거절 = 영구 X**. trigger 조건 충족 시 재평가 + 박음
- 출처: Perplexity A1-A4 batch (learning_materials/perplexity_caution_answers_2026_05_18.md)

---

## γ 상세 spec

### 자산 배분 (시드 1000만 가정 → 자본 increase 시 동일 비율 scale)

| 자산군 | 비중 | 종목 후보 |
|---|---|---|
| KRW 현금 / MMF | 40-50% | KODEX 단기채권 / KODEX 종합채권 |
| USD 자산 | 30% | KODEX 미국달러SOFR(444460) + ACE 미국30년국채(H)(453850) 5:5 |
| **글로벌 주식 ETF** | **20-30%** | TIGER 미국S&P500 / KODEX 미국나스닥100 / TIGER MSCI ACWI |

**β 대비 추가 진입** = 글로벌 주식 ETF 20-30% (β = USD 자산만, 주식 0).

### 학계 근거

| Framework | γ 정합 |
|---|---|
| **Markowitz MPT** | CAPE 99%ile ERP 1.6-2.0% 압축 환경 권고 = ETF 기반 60/40~80/20. γ = 50-60% risk asset → MPT 권고 상단 |
| **Kelly (Full)** | f* = ERP/σ² = 20-35% 주식 (현 CAPE 환경 자동 도출). γ = Full Kelly 영역 |
| **Merton** | 실용 Guardrail Floor 20% / Ceiling 40%. γ 글로벌 ETF 20-30% = Floor 정합 |
| **Behavioral** | DCA 3-6회 분할, 100% 현금 = 기회비용 함정. γ = Mental Accounting "점진 트랜치 40-50%" |

---

## γ trigger 조건 (재평가 발동)

다음 중 **하나 이상** 충족 시 PM γ 재평가 의무 (action_queue 자동 등록 후속 큐잉 — 자동 monitor 미구현 단계 manual):

### A. 자본 trigger ([[project_capital_evolution_path]] 정합)

- **시드 ≥ 5,000만** (Tier 2 진입 가능 baseline) — 거래비용 비선형 잠식 완화, 1-2 트랜치 → 3-5 트랜치 가능
- 또는 **시드 ≥ 1억** (Tier 3) — γ 분할 매수 5회+ 가능

### B. 시스템 성숙도 trigger

- **N ≥ 365 거래일** (1년 trail, IC/ICIR ≥ 0.3 게이트 통과 — [[project_validation_plan]])
- **Phase 2 진입** ([[project_institutional_5module_roadmap]] Module 1-3 완료 = Factor IC + Stress + Regime)
- **VAMS hit rate ≥ 55%** (Phase 0 14일 50% baseline 상회 + N≥100)

### C. macro regime trigger

- **CAPE percentile < 75%ile** + **USDKRW < 1350** (정상 환경 복귀) — 학계 권고 default region
- OR **value spread 극단 확대** (Asness HML Devil α 305-378bp 영역) — 저밸류 진입 알파 극대화 (B1 답)

### D. PM 결단 trigger (예외)

- 사용자가 명시적으로 "공격 운용 전환" 발화 — 시드 X / 시스템 성숙도 X 무관 즉시 발동
- 예: 자본금 외부 유입 (보너스/세금 환급 등) 으로 시드 일시 증가
- 의무: 사용자 발화 + commit message PM 승인 기록 ([[feedback_pm_decision_trail_in_commit]])

---

## γ 진입 시 실행 sequence

1. **trigger 확인** (위 A-D 중 어느 조건 충족)
2. PM 승인 commit + 메모리 trail (옛 β → γ 전환 trail)
3. **점진 진입** (1주에 1 트랜치, 3-5회 분할)
   - Week 1: KRW 현금 50% → USD ETF 30% + 글로벌 주식 ETF 10% (β 부분 + 글로벌 시작)
   - Week 2-3: 글로벌 ETF 10% → 20-30% (분할 추가)
   - 일괄 진입 = 학계 비권장 (Statman 1995 DCA Regret Aversion)
4. macro_multiplier 임계 재calibrate ([[feedback_no_premature_completion_claims]] 정합 — 1주 검증 후)
5. 1개월 후 PM 재평가 (γ 유지 / β 회귀 / 추가 공격)

---

## γ 예상 효과 (학계 추정)

| Metric | β (현재 채택) | γ (reserved) |
|---|---|---|
| Sharpe (예상) | 0.4-0.6 | 0.5-0.8 |
| Max DD (예상) | -5~-10% | -15~-25% (CAPE 99%ile 환경 + 헷지 일부) |
| 기회비용 | 중간 (현금 70-80%) | 낮음 (현금 40-50%) |
| 시스템 부담 | 낮음 (USD ETF 1-2 트랜치) | 중간 (3-5 트랜치 + 글로벌 ETF rebalance) |

---

## 관련 자산

- [[project_capital_evolution_path]] — Tier 진화 trigger 정합
- [[project_validation_plan]] — N≥365 + IC/ICIR 게이트
- [[project_institutional_5module_roadmap]] — Phase 2 모듈 진행
- [[feedback_seed_size_conservatism]] — 시드 작을수록 보수 (γ 현 거절 근거)
- [[project_pm_decision_cash_hold_2026_05_18]] — 5/18 β 채택 결정 (γ 보류 trail)
- learning_materials/perplexity_caution_answers_2026_05_18.md — A1-A4 + B1-B2 자문 본문

---

## 갱신 history

- 2026-05-18 02:35 KST — γ spec 박힘 (5/18 PM 결정 후 reserve)
