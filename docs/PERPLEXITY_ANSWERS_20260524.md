# Perplexity 답변 정리 — 2026-05-24

> **출처**: `docs/PERPLEXITY_QUESTIONS_20260524.md` 의 Q2 (cash cross) + Q5 (USD/KRW σ) 답변.
> **활용**: RULE 7 사전 등록 input. 답변 기반 산식 박기 *전* 백테스트 / 검증 의무 표기.
> **사용자 응답 status**: Q2 / Q5 답변 박힘. Q1 (KR ETF Z-Score) / Q3 (themes pulse) / Q4 (sector_trends 명세) = 답변 대기.

---

## Q2 — 자금 흐름 cross-validation (F sprint input)

### 핵심 결론
- **단순 합산 < 가중평균 < Bayesian aggregation** 정합도 순.
- **한국 시장 특유**: 외인 · 기관 · 프로그램 매매의 정보비대칭 + 역할 차이 → *source weighting 의무*.
- 합의도 (agreement ratio) + 강도 (weighted score) **결합 산식** 이 majority vote / weighted score 단독보다 우월.

### 산식 4 유형
| 유형 | 산식 | 특성 |
|---|---|---|
| 단순 합산 | `S_t = Σ z_i,t` | z-score 표준화 후 합. baseline |
| 가중평균 | `S_t = Σ w_i × z_i,t`, `Σ w_i = 1` | IC / t-stat / hit rate / turnover 효율 기반 weight |
| Majority vote | `S_t = sign(Σ sign(z_i,t))` | 방향성 합의 강, 크기 정보 손실 |
| Bayesian aggregation | `P(r_{t+h}>0 \| x_{1:t}) ∝ P(r_{t+h}>0) × Π P(x_i,t \| r_{t+h})^w_i` | 신호별 likelihood 결합. expert judgement 또는 다중 source 결합 *가장 자연* |

### 실무 권고 순서
1. **Granger causality** 로 *선행 정보 있는 source 만 남김* → predictive filtering
2. **Cointegration** = 장기 균형 검증용 (filtering 후 보조)
3. **IC 기반 weight** 결정 (순서: 예측력 검증 → 가중치 결정 분리)

→ *예측력 검증 + 가중치 결정 분리 구조* 가 가장 안전.

### 한국 시장 source 신뢰도 (Perplexity 정리)
| source | 역할 | weight 권고 |
|---|---|---|
| 외인 net buy | KOSPI 대형주 / 지수 방향성 직접 반응 | 가장 큼 |
| 기관 net buy | 연기금 = 정보성 높음, 금융투자/보험 = 분리 의무 | 중간 (분리 후) |
| 프로그램 매매 | 차익 거래 성격 → 단기 변동성 확대와 함께 해석 | 방향성 X, **regime filter / vol 보정 변수** |
| CFTC COT | 미국 자산 / 글로벌 risk-on/off 간접 | 보조 신호만 |
| ETF flows | 국내 ETF = 단기 **역추세** 성격 관찰 (한국 연구) | *반전 / 과열 지표* (추세 신호 X) |

기본 weight 출발점: **`w_foreign > w_institution > w_program`**.  
기관은 *연기금 / 금융투자 / 보험* 분리가 문헌 친화적.

### Agreement ratio + 강도 결합 산식 (**핵심 권고**)

```
AR_t = (1/N_t) × Σ 1(sign(s_1j) = sign(s_2j) = sign(s_3j))

S_t = AR_t × Σ w_i × z_i,t
```

| threshold | 의미 |
|---|---|
| AR ≥ 0.67 | 1차 유효 |
| AR ≥ 0.80 | 강한 합의 |

### 예측력 검증 (IC / ICIR / Decay)

```
IC_h = corr(S_t, r_{t+h})
ICIR = mean(IC_h) / std(IC_h)
Decay(h) = IC_h / IC_1
```

**horizon 별 일반 경향**:
- forward 5d = 가장 강함
- forward 20d = 절반 수준
- forward 60d = regime 의존 (확인용)

### Regime 의존성
| regime | 우월 source / 산식 |
|---|---|
| Bull | 외인 신호 + ETF flow |
| Bear | 기관 / 연기금 + 프로그램 매매 위험회피 신호 |
| Sideway | 합의도 + majority vote 효율 ↑ |
| Crisis | **Bayesian aggregation** 가장 안정. 단순 sum = 과적합 |

→ **고정 모델 X. 레짐별 weight set 분리** 정공법.

### 검증 표본 요구 (VERITY 백테스트 의무)
- 최소 2~5년, 권장 5~10년
- KOSPI / KOSDAQ 분리
- forward 5d / 20d / 60d
- bull / bear / sideway 레짐 분리
- z-score 표준화 + lagged signal
- 성과 = IC / hit rate / turnover-adjusted IR / decay curve

### **VERITY 의 현재 trail (49d) 으로는 N 부족** — 실제 산식 박기 *전*:
1. KRX / 예탁결제원 / CFTC / ETF flow 원자료 백테스트
2. KOSPI / KOSDAQ × 5d/20d/60d × 4 regime 의 IC 표 산출
3. weight + AR threshold 사전 등록 commit
4. F sprint (CashFlowRadar cross verdict) 진입

---

## Q5 — USD/KRW σ 동적 windows (b8e1b18d 후속)

### 최종 판정 (Perplexity)
| 용도 | 판정 |
|---|---|
| 정규분포 기준 이벤트 필터 | **P (통과)** |
| 실제 FX tail risk 캡처 | **F (불합격)** |

### 산식 4 유형 비교
| 유형 | 특성 |
|---|---|
| **EWMA (λ=0.94, RiskMetrics)** | 최근 데이터 가중치 큼. 단순 이동평균보다 추정오차 작거나 비슷 |
| **GARCH(1,1)** | 평균회귀 반영. 충격 후 서서히 안정되는 시계열 정합. 레짐 전환 잘 설명 |
| Realized variance (intraday) | 가장 우월. intraday 데이터 있을 시 우선 |
| 90일 rolling std | fallback / 장기 기준선 only |

### 권고 산식 (계층 구조)
```
σ_basic   = EWMA(λ=0.94)              ← 기본
σ_corr    = GARCH(1,1)                ← 보정
σ_realized = realized_variance        ← intraday 있을 시 우선
σ_fallback = 90d rolling std          ← floor / ceiling 참고만

σ_final = max(σ_floor, min(σ_EWMA, σ_GARCH))    ← 보수적 결합
```

### Fat-tail 보정
- USD/KRW excess kurtosis = 4-6 (fat-tail 강함)
- 정규분포 ±3σ = 0.27% **이론**, 실제 빈도 **1% 내외 또는 더 큼**
- 3σ 단독 = 희귀 이벤트로 사용 가능, but "거의 안 일어남" 해석 *틀림*

### **Quantile threshold 병행** (핵심 권고)
| quantile | 의미 |
|---|---|
| 1% | 강한 경보 |
| 5% | 주의 |
| 95% | 상단 압력 탐지 |
| 99% | 극단 스트레스 |

대칭 σ + 분위수 기준 *동시 사용*. 환율 = 하방/상방 비대칭 의무.

### 0.30% floor 판정
- **P (보수적 operational floor 로 합리)**
- 하지만 학술적 최적값 일반화 근거 *약함*
- **soft floor 권고** (hard floor X)

### 49일 부족 case (현재 VERITY 시점)
정공법 4 단계:
1. 49일 rolling std 우선 계산
2. EWMA 로 최근 49일 보강
3. 장기 priors + GARCH shrinkage 가능 시
4. 90일 수준 = floor / ceiling 만 참고

→ 실무 권고: `σ_final = max(σ_floor, min(σ_EWMA, σ_GARCH))`

### 한국 FX 시장 특유
- 2008 금융위기 / 2022 금리충격 = σ 점프 큼
- BIS / 국내 연구 = 구조적 취약성 / 대외자산 환리스크 / NDF-현물 연계 지적
- σ = 단순 통계 X, **조건부 지표** (한미 금리 spread / 달러 유동성 / NDF 프리미엄 동반)

→ 90일 = *장기 평균 기준선*, 일일 판단 = EWMA / GARCH 이중 구조.

---

## VERITY 적용 단계 (사전 등록 input)

### F sprint (CashFlowRadar cross verdict) — 진입 *전 의무*

| 단계 | 작업 | 의무 |
|---|---|---|
| 1 | KRX / 예탁결제원 / CFTC / ETF flow 원자료 fetch | backend 신설 |
| 2 | KOSPI / KOSDAQ × 5d/20d/60d × 4 regime IC 백테스트 | 산식 검증 (Q2 답변에 수치 없음, 직접 산출) |
| 3 | weight + AR threshold 사전 등록 commit | RULE 7 |
| 4 | CashFlowRadar UI = `S_t = AR × Σ w_i × z_i,t` 노출 | frontend |
| 5 | Brain 산식 통합 (선택) — fact_score 보너스 + sentiment cross | 별도 PM 결정 |

**현재 단계**: 1 (원자료 fetch) 도 미박힘. 큰 sprint. *별도 의제 큐잉*.

### σ sprint (USD/KRW σ EWMA 보강) — 진입 가능 단계

| 단계 | 작업 | 의무 |
|---|---|---|
| 1 | EWMA(λ=0.94) σ 산식 박음 (factors/_common 또는 verity_brain) | 산식 신설 = RULE 7 사전 등록 |
| 2 | GARCH(1,1) 보정 — `arch` 라이브러리 의존성 | backend (requirements.txt) |
| 3 | quantile threshold (1/5/95/99%) 박음 (3σ 와 병행) | 산식 추가 = RULE 7 |
| 4 | 49일 trail case fallback 로직 박음 — `max(σ_floor, min(σ_EWMA, σ_GARCH))` | 이미 검증 (Perplexity 정합) |
| 5 | verity_brain fx_shock msg 동적 method 명시 — "EWMA σ" / "GARCH σ" / "90일 σ" | b8e1b18d 후속 |

**현재 단계**: 1 (EWMA 산식) 박을 수 있음. RULE 7 사전 등록 commit 후 진입.

---

## RULE 7 사전 등록 (메모리 정합)

`feedback_methodology_pre_registration` + `project_brain_v5_self_attribution` 정합 — 자기 산식 변경 = 1회만, PM 승인 의무, commit 에 WHY/DATA/EXPECTED 박음.

### 사전 등록 commit 박을 산식 (Q5 기반)

```
산식 이름: USD/KRW σ 동적 추정 (EWMA + Quantile)
산식:
   σ_EWMA(t) = sqrt(λ × σ²(t-1) + (1-λ) × r²(t))
   λ = 0.94 (RiskMetrics 표준)
   
   σ_GARCH(1,1)(t) = ω + α × r²(t-1) + β × σ²(t-1)
   (arch 라이브러리, MLE fit)
   
   σ_final = max(σ_floor, min(σ_EWMA, σ_GARCH))
   σ_floor = 0.30% (soft floor, 보수적 operational)
   
   threshold 4 단계:
   - 3σ_final (이벤트 필터)
   - Q1 (강한 경보)
   - Q5 (주의)
   - Q95/Q99 (상단/극단 스트레스)
   
WHY: USD/KRW excess kurtosis 4-6 (fat-tail), 90d rolling std 단독 = 
     정규분포 가정 ±3σ 0.27% 이론과 실제 빈도 1%+ mismatch.
     RiskMetrics EWMA + GARCH(1,1) 학술 정합 (Perplexity Q5 정리).

DATA: 검증 의무 — USD/KRW 일별 5~10년 (FRED DEXKOUS), 
      2008 / 2022 stress event 분리 검증.
      VERITY 현재 trail = 49d → 백테스트 input 부족 → 시점:
        * EWMA 산식 박음 + verity_brain msg 동적 method 박음 (즉시 가능)
        * GARCH 추가 = 백테스트 후 (별도 sprint)

EXPECTED: 49d 시점 EWMA σ ≈ 0.40~0.60% 추정 (현재 fix b8e1b18d 의 
         sigma_dyn 동일 path), msg label = "EWMA σ" 명시. 
         3σ threshold + Q1/Q5/Q95/Q99 병행 → 사용자 PM 보수적 해석.
         자연 회복 시 (180d+) GARCH 보정 자동 활성.
```

---

## 다음 commit 후보

### Pre-register commits (RULE 7)
1. `pre-register(brain): USD/KRW σ EWMA 산식 사전 등록 — Q5 정합` (Q5)
2. `pre-register(brain): 자금 흐름 cross-validation 산식 사전 등록 — Q2 정합` (Q2) → 단 백테스트 *전* 까지는 *틀만* 박음

### Implementation commits (사전 등록 후)
1. EWMA σ 산식 박음 + verity_brain msg method 명시 (Q5 산식 1 단계)
2. CashFlowRadar AR × Σ w_i × z_i,t UI 박음 (Q2 산식 1 단계, 백테스트 의무 명시 caption)

---

## 출처

- 답변 출처: Perplexity Sonar Pro (사용자 박음 2026-05-24)
- 답변 핵심 인용: nber.org / sites.stat.columbia.edu / koreascience.kr / s-space.snu.ac.kr / sciencedirect / chosun / aeaweb / eia.feaa.ugal / joongang.co / kcmi.re / kif.re / kbam.co
- 다음 단계: 사전 등록 commit + EWMA / Cross verdict sprint 진입

## 메모리 정합

- `feedback_perplexity_collaboration` — 외부 사실/통계/법규 = Perplexity 핸드오프 (적용 완료)
- `feedback_methodology_pre_registration` — 산식 변경 사전 등록 의무
- `feedback_pm_decision_trail_in_commit` — PM 결정 commit = WHY/DATA/EXPECTED 3요소
- `feedback_source_attribution_discipline` — 신호/룰/임계 단일 명확 출처 + 자체 신호 명시
- `feedback_no_premature_completion_claims` — Q2 / Q5 사전 등록 = *틀만*, 산식 박을 단계는 백테스트 후
