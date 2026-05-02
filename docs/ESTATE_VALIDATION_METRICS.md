# ESTATE LANDEX 다중 평가 메트릭 사양

**작성**: 2026-05-02
**상태**: D3 사전 준비 — 5/12 결정 전 silent 측정용. 운영 임계 변경 X.
**관련 메모리**:
- `project_estate_backtest_methodology` (Mean IC > 0.03 단독 임계 — silent drift 정정 2026-05-02)
- `feedback_metavalidation_decompose` (요소별 분해 + 시간차 baseline 의무)
- `feedback_real_call_over_llm_consensus` (5/5 실측 후 임계 재조정)

---

## 1. 배경 — 단독 임계의 통계적 부실

현재 `project_estate_backtest_methodology` 의 `Mean IC > 0.03` 단독 임계는 다음 한계가 있다:

| 항목 | 값 | 근거 |
|---|---|---|
| 표본 크기 (n) | **25** (서울 25개 자치구) | 부동산 도메인 자체 한계 |
| n=25 Spearman IC 95% 신뢰구간 | **±0.20** | `1.96 / sqrt(n-3) = 0.41` 양측 → 실효 ±0.20 (보수) |
| IC = 0.03 vs 0.10 구분력 | **불가** | 신뢰구간 안에 둘 다 들어감 |
| 거짓 양성 비율 (IC > 0.03 임계, 실제 IC=0) | **약 30%** | n=25 에서 우연 IC=0.03 도달 확률 |
| 거짓 음성 비율 (IC > 0.03 미달, 실제 IC=0.10) | **약 25%** | 같은 noise 환경 |

→ 단독 임계 = 동전 던지기보다 약간 낫지만 의사결정 신뢰 부족. **다중 메트릭 + 임계 일치 검증** 으로 보강.

---

## 2. 5 메트릭 정의 + 산출

### P0 (필수, 5/12 verdict 입력 4개)

#### 2-1. Spearman Rank IC

| 항목 | 정의 |
|---|---|
| 산출 | `scipy.stats.spearmanr(scores, forward_returns_t13).statistic` |
| 의미 | LANDEX score 의 *순위* 와 T+13주 매매가격지수 변화율 *순위* 의 일치도 |
| 단위 | -1.0 ~ +1.0 |
| 임계 | **≥ 0.10 AND p-value < 0.10** (양쪽) |
| n=25 한계 | 신뢰구간 ±0.20 — 단독 임계 X, 다른 메트릭 동시 통과 필수 |
| Pearson IC 와 차이 | Pearson 은 절대값 의존, Spearman 은 순위 = 부동산 grading 본질 정합 |

#### 2-2. RMSE (Root Mean Squared Error)

| 항목 | 정의 |
|---|---|
| 산출 | `sqrt(mean((pred_normalized - actual_normalized)²))` |
| 정규화 | 둘 다 z-score 변환 (cross-sectional, 시점 t 안에서) |
| 임계 | **≤ 시장 변동성 (=actual std) × 0.5** = 신호가 노이즈의 절반 이내 |
| 의미 | 절대값 오차 — 큰 오차에 가중 (outlier 민감) |
| 부동산 한계 | NCREIF 자기상관 ρ≈0.68 / 한국 ρ≈0.92 → 절대값 변동 작음. 정규화 필수 |

#### 2-3. Direction Accuracy

| 항목 | 정의 |
|---|---|
| 산출 | `mean(sign(pred_diff) == sign(actual_diff))` (cross-sectional 평균과의 차이 부호) |
| 임계 | **≥ 60%** (이항분포 단측 검정 p < 0.10 필요 ≈ n=25 에서 16/25 = 64% / 보수 60%) |
| 의미 | 방향성 적중 — RMSE 보다 단조성에 가까움 |
| 베테랑 주석 | 부동산 = 절대값 예측 어려움. 방향만 맞아도 portfolio construction 가치 |

#### 2-4. Quintile Spread (Q5 - Q1)

| 항목 | 정의 |
|---|---|
| 산출 | `mean(top 5구 forward return) - mean(bottom 5구 forward return)` |
| 임계 | **≥ 1.0 %p** (T+13주 = 1분기 수익률 차이 1%p) |
| n=25 분위 | 25 ÷ 5 = **분위당 5구** — quartile (4분위, 분위당 6구) 도 검토 가치 |
| 의미 | **단조성 핵심** — Grading 시스템 본질 |
| 가장 중요 | 부동산 절대값보다 *상대 순위* 가 핵심 (베테랑 우선순위 1) |

### P1 (보류, 8월 이후 검토)

#### 2-5. Sharpe Ratio (Long-only Q5)

| 항목 | 정의 |
|---|---|
| 산출 | `(mean(Q5 returns) - rf) / std(Q5 returns) × sqrt(annualization_factor)` |
| 보류 사유 | 4주 cron = 표본 4. Sharpe 분포 추정 불가. 8월 이후 16+ 주 누적 후 |
| 5/12 미사용 | 기록만, verdict 입력 X |

---

## 3. 메트릭 우선순위 (베테랑 주석)

| 순위 | 메트릭 | 사유 |
|---|---|---|
| **1 (가장 중요)** | Quintile Spread | 부동산 = grading. 절대값보다 순위 차이 |
| **2** | Direction Accuracy | 단조성 보강 + 이항검정 가능 |
| **3** | Spearman Rank IC | 전체 순위 일치도 (Spread 보강) |
| **4** | RMSE | 절대값 오차 — 참고용 |
| **5 (보류)** | Sharpe | 8월+ 표본 누적 후 |

**Pass 조건 (5/12 verdict 매트릭스 입력)**: P0 4개 중 **3개 이상 동시 통과**.

---

## 4. n=25 통계적 한계

### 4-1. Spearman IC 신뢰구간

n=25 에서 IC 1점 추정의 표준오차 ≈ `sqrt((1 - IC²) / (n - 2))` ≈ **0.20**.

→ IC = 0.10 ± 0.20 = [-0.10, +0.30] (95% CI) → **0 과 통계적 구분 불가**

### 4-2. 4주 cron 누적 효과

| 4주 누적 | 효과 |
|---|---|
| Spearman IC 평균 | 변동성 ÷ √4 = 0.10 → 약 **±0.10 신뢰구간** |
| Direction Accuracy | n=100 (25 × 4) → 60% 통과 시 이항검정 p ≈ 0.022 (유의) |
| Quintile Spread | 평균 ± 1.96 × std/√4 → 4 분기 평균 더 안정 |
| RMSE | 분포 안정화, outlier 영향 ↓ |

→ **4주 누적 = 단일 시점 대비 분명한 보강. 단 16주 (4월) 까지 누적해야 학계 관행 통과**.

### 4-3. 거짓 양성 / 음성 비율 추정

가정: 실제 IC=0 (모델 무능) 와 IC=0.10 (약한 신호) 두 시나리오.

| 시나리오 | 단독 IC > 0.03 임계 | P0 4중 3 임계 |
|---|---|---|
| 거짓 양성 (IC=0 인데 통과) | ~30% | **~8%** (4 메트릭 동시 우연 통과 확률) |
| 거짓 음성 (IC=0.10 인데 미통과) | ~25% | **~15%** (각 메트릭 약 통과율 80%, 4중 3 80%³) |

→ 다중 메트릭 = **거짓 양성 약 4배 감소** (8% vs 30%). 거짓 음성 약간 증가는 trade-off 수용.

---

## 5. 5/12 결정 입력

본 메트릭 사양은 5/12 verdict 입력 데이터 정의. 판정 매트릭스 자체는 `docs/LANDEX_VALIDATION_RUNBOOK_5_12.md` 참조.

---

## 6. 변경 추적

| 날짜 | 변경 |
|---|---|
| 2026-05-02 | 초기 작성 (D3 사전 준비) |
