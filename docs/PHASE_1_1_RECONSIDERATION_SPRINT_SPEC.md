# Phase 1.1 Reconsideration Sprint 명세 (의제 57ac6bd0 + d7dea48c + 0f6dce6a)

**작성**: 2026-05-03 01:15 KST (Round 4 작업 8)
**의제 id**: 57ac6bd0 (P0 4-cell 백테스트) + d7dea48c (P1 운영 영향 사전 검증) + 0f6dce6a (multiplier 재검토)
**예상 시간**: ~4시간 (3 step + 의사결정)
**참조**: `docs/SOURCE_AUDIT_20260502.md` §5 (Phase 1.1 v2 verdict 🔴) / `docs/SILENT_ERRORS_20260502.md` Error 1 / 메모리 `project_atr_dynamic_stop`

---

## 0. Sprint 목표

Phase 1.1 ATR×2.5 한국 시장 부적합 정량 검증 (5/2 풀스캔 v2 large stop_loss 75.6%) → 4-cell 백테스트 + 운영 holding 실측 → ATR multiplier 재선택 + 운영 코드 변경.

---

## 1. 진입 조건 (선행 의존성)

### 1-1. 의무 (선행 의제)

| 우선 | 의제 | 이유 |
|---|---|---|
| **1** | Phase 0 verdict (5/17) 통과 | Wilder EMA baseline 보호 (단일 변수 통제) |
| **2** | **c5e8f9a2 hotfix sprint 완료** | 운영 holding 실측 데이터 정확도 (avg_price=0 → return_pct 부정확 → stop_hit 비율 측정 부정확) |

### 1-2. 병행 가능 (독립)

- 작업 7 (SECTOR_PROPAGATION_SPRINT) — 동시 진행 가능 (독립)
- 단 Step 3 (sector 차등 분석 보강) 은 작업 7 Step 4 완료 후 가능

### 1-3. 미정정 시 영향

c5e8f9a2 미정정 상태에서 Step 2 (운영 실측 vs 백테스트) 진입 시:
- holdings avg_price=0 → return_pct 부정확
- stop_hit 비율 측정 부정확
- 4-cell 백테스트와 비교 의미 X

→ **c5e8f9a2 완료 의무**.

---

## 2. 작업 단계 (순차)

### Step 1 — 4-cell 백테스트 실행 (90분)

**파일**:
- `scripts/atr_4cell_backtest.py` (신규)
- 결과: `data/analysis/atr_4cell_backtest_20260517.json`

**4 cell**:
| cell | ATR period | multiplier | 출처 |
|---|---|---|---|
| **현재** | 14 | 2.5 | 본 시스템 (T1-23) |
| 후보 1 | 14 | 3.0 | LeBeau period 보존, multiplier 보수 |
| 후보 2 | 22 | 2.5 | LeBeau period 채택, multiplier 본 시스템 |
| **LeBeau 원전** | 22 | 3.0 | Chuck LeBeau *Computer Analysis of Futures Market* |

**universe**: 5/2 v2 universe 그대로 (1,791 종목, hard_floor 적용)

**메트릭** (시총 tier 별 분해):
| 메트릭 | 산출식 |
|---|---|
| stop_loss_rate | 1년 윈도우 stop hit / 전체 entry |
| 5R hit rate | 5R 도달 / 전체 entry |
| max_excursion (R-multiple cap=50) | mean / p90 |
| avg days to 5R hit | (도달 시) 평균 일수 |
| profit factor | 총 이익 / 총 손실 |
| Sharpe ratio (per cell) | 위험 조정 수익 |

**sector 차등 분해** (작업 7 Step 4 완료 시):
- 금융 / IT / 바이오 / 화학 / 자동차 등 sector 별 stop_loss_rate
- sector 별 최적 multiplier 차등 가능성 검토

**산출**: 4 cell × 6 메트릭 × 3 시총 tier (large/mid/small) = 72 cells 결과 표.

### Step 2 — 운영 holding 실측 비교 (60분)

**입력**: c5e8f9a2 hotfix 후 정확한 holdings avg_price + return_pct.

**작업**:
- 지난 1개월 (4/2~5/1) holding 의 stop_hit 비율 측정
- 백테스트 75.6% (large tier) 와 비교
- 격차 분석:
  - **격차 < 10%p**: 백테스트와 운영 정합 ✅ → 4-cell 결과 신뢰
  - **격차 10~30%p**: 부분 격차 ⚠️ → 추가 진단 (운영 universe vs 백테스트 universe 차이?)
  - **격차 > 30%p**: 격차 큼 🔴 → 운영-백테스트 정합성 의제 (별도 sprint)

**산출**: `data/analysis/operational_stop_hit_vs_backtest_20260517.json`

### Step 3 — ATR multiplier 선택 + 운영 코드 변경 (90분)

**의사결정 매트릭스** (4 cell + 실측 종합):

| 결과 시나리오 | 액션 |
|---|---|
| LeBeau 원전 (22×3.0) large stop < 60% + Sharpe ↑ | **multiplier 변경** → ATR_PERIOD=22, ATR_STOP_MULTIPLIER=3.0 |
| 후보 2 (22×2.5) 우수 | period 만 변경 → ATR_PERIOD=22 |
| 후보 1 (14×3.0) 우수 | multiplier 만 변경 → ATR_STOP_MULTIPLIER=3.0 |
| 모두 격차 작음 (5%p 이내) | 현재 유지 + sector 차등 도입 검토 |
| 모두 60%+ | **Phase 1.1 룰 자체 재설계** (별도 sprint) — ATR 외 다른 stop loss 산식 검토 |

**운영 코드 변경**:
- `api/config.py:ATR_STOP_MULTIPLIER` 또는 `ATR_PERIOD` 변경 (선택된 cell 기준)
- 기존 holding 의 stop_loss_method = "atr_dynamic" 영속화 (T1-22 P-03 정합) → 변경 영향 X
- 신규 entry 부터 새 multiplier 적용
- 단위 테스트 추가 (`tests/test_atr_stop_new_multiplier.py`)

**rollback 조건** (변경 후 모니터링):
- 새 multiplier 적용 후 평균 손실 -12% 악화 (3주 모니터링)
- 5R hit rate < 30% (multiplier 너무 큰 신호)
- ATR 산출 실패율 > 30%

---

## 3. 검증 매트릭스

### 3-1. Step 1 (4-cell 백테스트 산출)

- [ ] 4 cell × 1,791 종목 백테스트 실행 완료
- [ ] 시총 tier 별 분해 결과 산출 (3 tier × 6 메트릭)
- [ ] sector 차등 분석 (작업 7 Step 4 후 가능)
- [ ] 결과 jsonl 영구 보존

### 3-2. Step 2 (운영 실측 비교)

- [ ] 운영 holding 1개월 stop_hit 비율 산출
- [ ] 백테스트 vs 실측 격차 분석
- [ ] 격차 verdict (< 10%p 정합 / 10-30%p 진단 / > 30%p 별도 sprint)

### 3-3. Step 3 (multiplier 변경 후)

- [ ] 4-cell 결과 large tier stop_loss < 60% 인 cell 존재 검증
- [ ] 운영 holding 실측 vs 백테스트 ±10%p 이내 (변경 후)
- [ ] 새 multiplier 적용 후 D+30 stop_hit 비율 안정 (백테스트 ±5%p)
- [ ] D+90 운영 결과 alpha 비교 (변경 전 vs 후)

---

## 4. 4-cell 백테스트 sector 차등 분해 (보강 — 작업 7 Step 4 후 가능)

**기존 4 cell** (ATR period × multiplier) 외에 sector 별 분해:

| sector | 4 cell stop_loss_rate | 최적 multiplier (sector 별) |
|---|---|---|
| 금융 (FINANCIAL_SECTORS) | 산출 후 | 보수 (낮은 변동성 — 작은 multiplier 가능) |
| IT / 반도체 | 산출 후 | 표준 (변동성 중) |
| 바이오 / 제약 | 산출 후 | 큰 multiplier (변동성 ↑) |
| 화학 / 정유 | 산출 후 | 표준 |
| 건설 / 항공 | 산출 후 | 큰 multiplier (cyclical 변동성) |

**sector 별 최적 multiplier 차등 가능성**:
- 단일 multiplier 한계 발견 시 → sector × multiplier 매트릭스 도입 의제
- 별도 sprint (Phase 1.1.5 — sector-aware ATR stop)

→ 작업 7 + 8 동시 진행 시 자동 통합. sector 데이터 정합성 의무.

---

## 5. 롤백 조건

- 새 multiplier 적용 후 평균 손실 -12% 악화 (3주 모니터링)
- 5R hit rate < 30% (multiplier 너무 큰 신호)
- ATR 산출 실패율 > 30%
- 운영 cron 실패 (다음 portfolio.json 생성 X)

**롤백 절차**:
1. `git revert <multiplier-change-commit>`
2. 기존 holding 영향 X (atr_method_at_entry 영속화)
3. 별도 진단 의제 등록 (예: `0f6dce6a-fail` — Step 3 multiplier 선택 재검토)

---

## 6. 운영 영향

**예상 (긍정)**:
- stop_loss 75% → < 60% 목표 (whipsaw 손절 감소)
- 평균 보유 기간 ↑ (early exit 감소)
- 5R hit rate 안정 (multiplier 너무 작지 않은 한)

**위험**:
- multiplier ↑ 시 1R distance ↑ → entry 당 risk 증가 (sizing 영향)
- 큰 multiplier 시 stop hit 늦어 → 손실 폭 ↑ (개별 종목)

**완화**:
- VAMS sizing (T1-18) volatility_adj 와 함께 작동 (큰 multiplier ↔ 작은 size)
- 백테스트 + 실측 검증 후 PM confirm 게이트
- D+30 / D+90 운영 결과 모니터링

---

## 7. 후속 의제 진입

| 후속 의제 | 의존성 해제 |
|---|---|
| Phase 1.1.5 (sector-aware ATR stop) | sector 별 최적 multiplier 차등 발견 시 |
| Phase 1.5.1 (백테스트 검증) | Phase 1.1 multiplier 안정 후 |
| Phase 2-A Stage 2 진입 (cdad960a) | Phase 1.1 안정 + 운영 검증 후 |
| capital_evolution_monitor Trigger 1 정상 작동 | c5e8f9a2 + Phase 1.1 안정 후 |

---

## 8. 학습 사례 cross-ref

본 sprint = `feedback_real_call_over_llm_consensus` + `feedback_source_attribution_discipline` 정합:

- "월가 표준" 표현 silent drift (5/2 D2-1 정정) → 4-cell 백테스트 정량 검증 → multiplier 재선택
- *외부 출처 인용 vs 자체 캘리브레이션* 명확 분리 의무 — 본 sprint 결과로 "단기/한국 자체 채택 변형" 를 *정량 baseline* 으로 격상

→ `feedback_source_attribution_discipline` 학습 사례 7번째 후보 (sprint 완료 후 추가 검토 — 작업 7 sprint 와 둘 중 먼저 완료 시점 학습).

---

## 9. 변경 추적

| 일자 | 변경 |
|---|---|
| 2026-05-03 01:15 KST | 초기 작성 — 3 step + 4 cell × 6 메트릭 × 3 tier 매트릭스 + sector 차등 분해 + 의사결정 매트릭스 + 검증 |

---

문서 끝.
