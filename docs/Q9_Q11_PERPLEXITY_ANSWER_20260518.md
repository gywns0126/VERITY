# Q9 + Q11 답변 — Grade 임계 / Minimum N (Perplexity, 2026-05-18)

**Source**: Perplexity Sonar Pro (사용자 paste, 2026-05-18). 학술 reference 정교 (Bailey-Lopez de Prado / Harvey 2016 / Reschenhofer 2022 / Grinold-Kahn / AQR / NIH 2024).

---

## Q9 — Grade Threshold Calibration

### 결정적 fact
1. **임계 60→50 하향 = 곡선 맞추기 (금지)**. max=49 = "산식 재검토 신호이지, 임계 하향의 근거가 아니다".
2. **N<50** = absolute threshold (이론 고정), walk-forward 불가. **N≥50** = 1회 walk-forward 임계 재검토 가능.
3. **AQR 표준 = quintile** (top 20%), 단 정확 임계 비공개.
4. **Asymmetric hysteresis** (진입 55 > 유지 45) = Reschenhofer 2022 실증 Sharpe 우위.
5. **1회 권한 = 학술 정합** (Secretary Problem 1/e + Harvey 2016 |t|>3.0 + PBO/CSCV).

### Absolute vs Percentile vs Z-score
| 방식 | 정공법 조건 | brain_score 적용 |
|---|---|---|
| Absolute | 점수 의미 calibrated (F-Score 0~9) + 우주 안정 | N=25엔 분포 변동 = 위험 (단 이론 고정 시 유일 옵션) |
| Percentile | 우주 ≥50~100 + ranking 자체 목적 | N=25엔 top decile = 2.5개 = 정수 문제 |
| Z-score | 정규 안정 + 역사 σ 신뢰 | N=25엔 σ 추정 오차 큼 = 불안정 |

→ **N=25 권장**: Absolute 유지 + 이론 고정 (곡선 맞추기 금지) + asymmetric hysteresis band

### Sample Size별 검증 가능성
| N | 검증법 | 임계 최적화 |
|---|---|---|
| **25** | 없음 (이론 only) | ❌ 검정력 0 |
| **50** | Walk-forward (OOS 15~20) | ⚠️ 1개 임계만 |
| **100** | Walk-forward + 5-fold CV | ✓ 2~3 파라미터 |
| **250+** | CSCV | ✓ PSR/DSR 신뢰 |

### N=25 brain_score 직접 권고
- 임계 60→50 = **데이터에 맞춘 곡선 맞추기, 산식 설계 문제를 임계로 가리는 조치** (Perplexity 직접 인용)
- **선행 조치**: max=49 원인 진단 — 어떤 component 가 상위 점수 도달 막는지 분리 분석
- N→50 확장 후: 1회 walk-forward 기반 임계 재검토 (사전 문서화 필수, pre-registration)
- **Asymmetric hysteresis 채택**: 진입 55 > 유지 45 분리 (Reschenhofer 2022)
- PSR 모니터링: T≥100 도달 시점부터 PSR 계산 시작

---

## Q11 — Minimum N for IC / PSR / DSR

### 결정적 fact
1. **N=14 hit rate 50% Wilson 95% CI = [27%, 73%]** = 동전 던지기와 통계적 구분 X (사용자 진단 valid)
2. **IC 유의 (p<0.05)**: IC=0.05 → N≥1000+, IC=0.10 → N≈500, IC=0.15 → N≈365
3. **PSR minimum N≥252 (1년 daily)** + skew/kurtosis 안정 (3rd moment N≥100, 4th N≥250)
4. **DSR MinBTL = 684 거래일 (2.7년) for I=1**, I=100 시 2,735일 (10.9년)
5. **Live trail >> Backtest** 통계적 가중치 (Lopez de Prado)
6. **CPCV (Combinatorial Purged CV)** 백테스트 표준 (Bailey 2017 SSRN 2917044)

### IC 유의성 milestone
| N | IC=0.05 | IC=0.10 | IC=0.15 |
|---|---|---|---|
| 14 | p=0.87 ✗ | p=0.73 ✗ | p=0.61 ✗ |
| 30 | p=0.79 ✗ | p=0.60 ✗ | p=0.43 ✗ |
| 100 | p=0.62 ✗ | p=0.32 ✗ | p=0.14 ✗ |
| 252 | p=0.43 ✗ | p=0.11 ✗ | **p=0.017 ✓** |
| 365 | p=0.34 ✗ | △p=0.056 | p=0.004 ✓ |
| 504 | p=0.26 ✗ | **p=0.025 ✓** | p=0.001 ✓ |

### PSR 적용 minimum N
- T<100: skew/kurtosis 극단값 지배 = PSR 의미 없음
- T=252 (연간 SR=1.0): PSR≈0.95 도달
- **실용 minimum: T≥252 + N_trials≥30 (Lopez de Prado Ch.14)**

### DSR MinBTL
| 전략 시도 횟수 I | MinBTL (거래일) | MinBTL (년) |
|---|---|---|
| 1 | 684 | 2.7년 |
| 2 | 971 | 3.9년 |
| 10 | 1,676 | 6.7년 |
| 20 | 1,991 | 7.9년 |
| 50 | 2,412 | 9.6년 |
| 100 | 2,735 | 10.9년 |

→ **"백테스트 최소 5~10년 필요"** 경험칙의 수리적 근거 (Bailey et al. 2014)

### N=14 Binomial CI 진단 (사용자 진단 valid 확인)
| N | 95% CI hit rate=50% | half-width |
|---|---|---|
| **14** | [0.268, 0.732] | **±23.2%p** (동전 구분 X) |
| 30 | [0.332, 0.668] | ±16.8%p (노이즈) |
| 100 | [0.404, 0.596] | ±9.6%p |
| 365 | [0.449, 0.551] | ±5.1%p |

= **CI 좁히기 O(1/√N)**. N=14→56→224→896 = ±12→6→3%p

---

## VERITY 운영 적용 (Engineer 분석)

### 현재 상태 (N=14 거래일)
- 운영 풀 N=25 종목 / 거래일 14
- hit rate 50% = CI [27%, 73%] = **통계 무의미**
- IC (factor_ic_history.json) 7d/14d/30d window 적용

### Tier 2 결정 의제 (Q7/Q9/Q11 답 종합)
| 옵션 | 답 정합 | 결정 |
|---|---|---|
| **C** DEAD factor disable | ✓ Q7 best practice (Disable = 학술 표준) | **YES** (multi_factor / timing 즉시 disable, prediction / consensus 별 sprint) |
| **D** bonus 임계 완화 | ✗ Q9 곡선 맞추기 risk | **보류** |
| **E** grade 60→50 하향 | ✗ Q9 "산식 설계 문제를 임계로 가리는 조치" | **NO** |
| **대안** 산식 재설계 | ✓ Q9 권고 + Q7 IC-IR weighting | **다음 sprint 정공법** |

### 산식 재설계 의제 (Q9 답 정합)
**max=49 root cause = Tier 1 fix 미완 + 산식 자체 한계**:
1. **5 component 100% fallback 50** (Tier 1 fix 일부 박힘):
   - commodity_margin (A6 v2 회복 ✓ 단 scale fix 0623355b 후 trigger 의무)
   - dart_business_analysis (A1 v2 박힘, staging mock = prod mode 의무)
   - perplexity_risk (A7 회복 ✓ 10/25)
   - quant_volatility (A5 회복 ✓ 25/25)
   - analyst_report_summary (A2 KIRS 매칭 0/10)
2. **DEAD 4 factor anti-signal 30%** (Q7 답 disable 의무):
   - multi_factor / prediction / timing / consensus
3. **Bonus pipeline 모두 0/25 trigger** (산식 자체 결함):
   - vci / candle / gs / inst — fact_score≥60 trigger 임계 도달 불가
4. **IC-IR weighting 전환** (Q7 답 best practice, Brain v6 큐잉):
   - 개별 disable rule 없이 자동 처리

### Timeline (Q11 답 정합)
| N | 시점 | milestone | 적용 |
|---|---|---|---|
| 14 | 현재 | 통계 무의미 | 산식 정상화 (Tier 1 fix) |
| 30 | ~6월 중순 | binomial ±17%p (여전 노이즈) | walk-forward 1회 권한 사용 검토 |
| 100 | ~9월 중순 | binomial ±10%p (약 신호) | IC 부분 유의 |
| 252 | ~2027 Q1 | PSR≈0.95 도달 가능 | IC 유의 (IC=0.15+) |
| 365 | ~2027 Q2 | IC=0.10 → p=0.056 (경계) | PSR/DSR 적용 |
| 504 | ~2027 Q4 | IC=0.10 → p=0.025 ✓ | DSR MinBTL 도래 |
| 684 | ~2028 Q2 | DSR MinBTL (I=1) | DSR 적용 가능 |

---

## Engineer 다음 sprint 추천 (Q7/Q9/Q11 답 종합)

### 즉시 (이번 sprint)
1. **multi_factor / timing disable (w=0)** — Q7 답 정공법, 단일 변수 통제
   - factor_decay.py:271 `_STATUS_MULT` DEAD 0.3 → 0.0 변경 (DEAD only)
   - sanity: brain_score 분포 변화 측정 (trigger 후)
2. **commodity scale fix trigger** — commit `0623355b` 효과 측정 (이번 schedule cron `26029877029` 완료 후)
3. **메모리 박음**: feedback_threshold_calibration_overfit_guard (Q9 patterns)
4. **메모리 박음**: project_minimum_n_milestones_2026_05_18 (Q11 N milestone)

### 다음 sprint (1주)
1. **prediction / consensus flip audit** — Q7 답 ICIR 절대값 확인 + 경제적 논리 검증
2. **A2 KIRS 매칭 개선** — 운영 풀 N=25 매칭 0/10 ticker 알고리즘
3. **Asymmetric hysteresis 박음** — 진입 55 > 유지 45 (Reschenhofer 2022)
4. **6.5 unhashable type 정확 fix** — silent fail trace 확보 후

### Brain v6 (2027 Q1 큐잉)
1. **IC-IR weighting 전환** — Q7 답 best practice, 개별 disable rule 폐기
2. **CPCV (Combinatorial Purged CV)** 백테스트 정합 — Bailey 2017
3. **walk-forward + embargo** 적용 — N≥50 도래 시
4. **alphalens-reloaded** 통합 (project_oss_audit_2026_05_17 정합)

---

## Cross-link

- `docs/Q7_DEAD_FACTOR_PERPLEXITY_ANSWER_20260518.md`
- `docs/TIER2_PM_DECISION_QUEUE_20260518.md` (Q7+Q9+Q11 답 반영 갱신 의무)
- `docs/BRAIN_SCORE_AUDIT_20260518.md` §6 root cause
- `[[project_brain_v5_self_attribution]]` (7:3 가중치 + 임계 75-60-45-30)
- `[[project_brain_v6_design_2026_05_17]]` (IC-IR weighting 전환 의제)
- `[[feedback_perplexity_collaboration]]` (외부 자문 정합)
- `[[feedback_no_premature_completion_claims]]` (시간 + 검증 frame 정합)

## 참고 출처 (사용자 paste, 학술 reference)
- Bailey & Lopez de Prado, "The Deflated Sharpe Ratio" (2014)
- Bailey et al., "Probability of Backtest Overfitting" (CSCV, 2014)
- Reschenhofer (2022), "Combining Factors"
- Harvey et al. (2016), "… and the Cross-Section of Expected Returns"
- Grinold & Kahn (1999), Active Portfolio Management
- López de Prado (2018), Advances in Financial Machine Learning Ch.14
- NIH (2024), 소표본 CV 분석 (nested 10-fold CV)
- AQR "Hold the Dip" (2025), "Can Machines Build Better Stock Portfolios?" (2024)

---

**End of Q9 + Q11 답 정리. Tier 2 결정 의제 확정 (C YES / D 보류 / E NO + 산식 재설계 정공법).**
