# Brain v6 Design v0.1

**박힘**: 2026-05-17 새벽. Perplexity Q1-Q6 학계 자문 정합. Phase 2 5 모듈 prereq.

## Brain v5 → v6 진화 요약

### v5 (현재, 2026-04 이후)
- **산식**: `brain_score = fact_score × 0.7 + sentiment_score × 0.3 + bonuses - penalties`
- **fact 14 components** (Perplexity Q1-Q6 batch 후 + equity_brief_verdict):
  - multi_factor / consensus / prediction / backtest / timing / commodity / export / moat
  - graham / canslim / analyst_report / dart_health / perplexity_risk / **equity_brief_verdict**
- **sentiment 13-source hard-wire** (Perplexity 자문, ce36c470):
  - news 0.175 / x 0.125 / mood 0.125 / consensus 0.10 / crypto 0.065 / fear_greed 0.065 / social 0.085
  - + fx 0.050 / commodity 0.040 / GID 0.040 / geo 0.060 / macro 0.050 / horizon 0.020
- **bonuses**: VCI / candle / GS / institutional
- **penalties**: red_flag (max -20)
- **grade 임계**: 75 / 60 / 45 / 25 (STRONG_BUY / BUY / WATCH / CAUTION / AVOID)

### v6 (Phase 2 진입 후, 8월~)

#### 변경 1 — 가중치 재 calibration
- v5: fact 0.7 + sentiment 0.3
- v6: **fact 0.6 + sentiment 0.25 + brief 0.15** (3-axis)
- 이유: Perplexity equity brief 가 institutional 외부 시각. fact (내부 정량) 와 직교 → 별 axis
- 정확한 비중 = 65 거래일 IC/ICIR 측정 후 결정 (Perplexity Q2 자문)

#### 변경 2 — Tier 별 score 산식 차별 (Capital 3-Tier 정합)
- 보수 tier: brain_score 가중 = fact 0.8 + sentiment 0.1 + brief 0.1 (펀더멘털 우선)
- 중간 tier: 표준 (fact 0.6 / sent 0.25 / brief 0.15)
- 공격 tier: fact 0.4 + sentiment 0.3 + brief 0.15 + **catalyst 0.15** (촉매 우선)

#### 변경 3 — Regime-aware threshold
- regime BULL: 75/60/45 (현 v5 유지)
- regime BEAR: 80/65/50 (보수 강화, false BUY 차단)
- regime NEUTRAL: 표준

#### 변경 4 — Ensemble (Strategy Pool 정합)
- 단일 brain_score → **3 strategy pool 의 가중 평균**
- pool 의 각 strategy 가 자체 brain v5/v6 변형 (다른 weight)
- ensemble verdict 가 최종 결정 (project_strategy_pool 정합)

#### 변경 5 — 통계적 게이트 (PSR / DSR / ICIR)
- proposal accept 시 PSR > 0.90 + 절대 margin 0.10 + DSR (K=trial 수) 보정 (Perplexity Q4 자문)
- ICIR < 0.2 → weight floor 30% / ≥ 0.3 → 정상 / ≥ 0.5 → 가중 증가 정당화

## 의존성 체인

```
Phase 1 잔존 (5/17 ~ 8월)
  ↓
65 거래일 IC/ICIR 측정 (8월 말 TG-1 PRODUCTION + Phase 2 Module 1 Factor)
  ↓
v6 변경 1, 2 (가중치 재 calibration + Tier 차별)
  ↓
Phase 2 Module 3 Regime (10월) 
  ↓
v6 변경 3 (Regime-aware threshold)
  ↓
Phase 2 Module 4 Portfolio (11월) + Strategy Pool 활성
  ↓
v6 변경 4 (Ensemble)
  ↓
2027 운영 누적 → v6 검증 → Calmar / MDD 측정
```

## Phase 2 모듈과의 관계

| Phase 2 모듈 | Brain v6 변경 |
|---|---|
| 1 Factor (8월) | 변경 1, 5 (가중치 IC/ICIR 기반 재산출) |
| 2 Stress (9월) | (영향 없음 — stress 는 portfolio level) |
| 3 Regime (10월) | 변경 3 (regime-aware threshold) |
| 4 Portfolio (11월) | 변경 4 (Strategy Pool + ensemble) |
| 5 Attribution (12-1월) | (영향 없음 — attribution 은 분해 분석) |

## 후속 sprint (v6 박을 시점)

- **v6.0 prep** (8월 초): 가중치 변경 1 PR + IC/ICIR 데이터 누적 검증
- **v6.1** (8월 말): Phase 2 Module 1 Factor 결과 반영
- **v6.2** (10월 말): Regime threshold 변경 3 적용
- **v6.3** (11월 말): Strategy Pool ensemble 변경 4 적용
- **v6 검증** (2027 Q1): 6개월 운영 누적 후 v5 vs v6 backtest 비교

## Cross-link

- [[project_brain_v5_self_attribution]] (v5 SSOT)
- [[project_perplexity_q1_q6_batch_2026_05_17]] (Perplexity 학계 자문)
- [[project_perplexity_equity_brief]] (brief 통합)
- [[project_capital_3tier_mode]] (Tier 차별)
- [[project_institutional_5module_roadmap]] (5 모듈 정합)
- `docs/PHASE_2_5_MODULE_ROADMAP_v0.1.md`
- `docs/GOLDEN_GOOSE_VISION_2028_v0.1.md`
- `docs/MASTER_RULE_DRIFT_AUDIT_v0.1.md`
