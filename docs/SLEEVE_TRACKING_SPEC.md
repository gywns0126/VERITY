# SLEEVE TRACKING SPEC v0.1

작성: 2026-05-12
근거: `터미널 보충 학습 자료. /터미널 학습 자료 5.md` (Perplexity Q3 — Multi-market sleeve 추적 실무 표준)
연관: `UNIVERSE_FUNNEL_REFORM_PLAN_v0.3.md` (Stage 5 베타 테스트 구역)

## 1. 목적

Tier 1 VERITY 의 KR sleeve (6 종목) 와 US sleeve (2 종목, 베타 테스트 구역) 를 **독립 sub-strategy** 로 추적. AQR / Two Sigma 멀티스트래트 표준 정합. Brinson-Fachler 계층 attribution 적용.

## 2. Sleeve 단위 산출 지표

### 2.1 Sleeve-level Sharpe (로컬 통화)

```
Sharpe_KR = (r̄_KR_KRW - r_f,KR) / σ_KR
Sharpe_US = (r̄_US_USD - r_f,US) / σ_US
```

| 시장 | 무위험 (r_f) | 연율화 인자 | 비고 |
|---|---|---|---|
| KR | KOFR 또는 CD 91일물 | √248-252 | KRX 거래일수 정확 산정 |
| US | SOFR | √252 | 정합 |

**중요**: 로컬 통화 기준 — 환차익은 별 attribution 항목. USD 환산 후 통합 Sharpe 는 portfolio-level 별도.

AQR 장기 글로벌 주식 Sharpe baseline = 0.3. 지역·breadth 차이 고려 조정.

### 2.2 Sleeve-level Information Ratio

```
IR_KR = α_KR / TE_KR
IR_US = α_US / TE_US
```

| 시장 | 벤치마크 (1차) | 벤치마크 (스마트베타) |
|---|---|---|
| KR | KOSPI 200 | KRX 300 또는 KRX/S&P Korea Quality |
| US | S&P 500 | Russell 1000 또는 MSCI USA Quality |

TE 산출:
- **Ex-ante TE**: 팩터 모델 기반 예측치 (Barra/AXIOMA 또는 자체)
- **Ex-post TE**: 실현 표준편차 (alpha 시계열)

둘 다 별도 기록. KG 제로인 표준 = 연율 TE 최근 1년 기간.

### 2.3 Sleeve-level Maximum Drawdown

```
MDD_KR = max((Peak_t - Trough_t) / Peak_t)
```

- **Calendar MDD**: 연간/분기 기준 (보고용)
- **Rolling MDD**: 12개월 rolling window (sleeve 간 비교용)

Two Sigma 정합 — sleeve 독립 손실 한도 관리.

### 2.4 추가 Sleeve 지표

- Hit rate (월별 +/- 비율)
- Capture ratio (up-capture / down-capture vs 벤치마크)
- Information Coefficient (IC) 및 IC-IR (월별 z-score)
- Turnover (분기 회전율)
- Implementation Shortfall (코스닥 소형주 특히)

## 3. Brinson-Fachler 계층 Attribution

### 3.1 3-Level 분해

| Level | 분해 항목 | 산식 |
|---|---|---|
| **L1: 시장 배분** | KR vs US 비중 결정 | (w_KR^P - w_KR^B) × (R_KR^B - R^B) |
| **L2: Sleeve 내 팩터 배분** | 밸류/모멘텀/퀄리티 비중 | 시장별 반복 |
| **L3: 종목 선택** | 팩터 내 개별 기여 | w_i^P × (R_i - R_factor^B) |

Interaction term = (w_i^P - w_i^B)(R_i^P - R_i^B) → 실무 표준 = **L3 (선택 효과) 에 흡수**.

### 3.2 Singer-Karnosky 다중통화 Attribution

KR sleeve USD 환산 시 환 alpha 와 로컬 주식 alpha 분리:

```
R_KR_USD = R_KR_KRW + ΔFX_KRW/USD + cross-term

L1' 환 효과 분리 = ΔFX 단독 기여
L1 시장 배분 = KR sleeve 로컬 수익률 기여 (FX 중립)
```

학계 표준 (journal.r-project 인용). Tier 1 단계에서 portfolio-level 통합 시 필수.

## 4. Sleeve 간 상관관계 모니터링

### 4.1 잔차 상관관계 (Residual Correlation)

KOSPI 가 글로벌 risk-on/off 에 민감 → KR/US sleeve 시장 베타 상관 ↑ 가능. **단순 수익률 상관이 아닌 *잔차* (벤치마크 차감 후 alpha 시계열 상관) 사용**.

```
ρ_residual = corr(α_KR, α_US)   (월별, rolling 12m)
```

### 4.2 임계값

| ρ_residual | 의미 | 대응 |
|---|---|---|
| < 0.2 | AQR baseline 가정 정합 — 진정한 독립 sleeve | 정상 |
| 0.2 ~ 0.4 | 분산 효과 부분 유지 | 모니터링 |
| **≥ 0.4** | **실질적 분산 효과 소멸 (실무 임계)** | risk budget 재조정, US sleeve 축소 검토 |

월별 산출 + AdminDashboard 표시 의무.

## 5. KR Sleeve 특수 보정

### 5.1 거래일수 비동기

KR 거래일 248-252일 / US 252일. 연율화 sqrt factor:
- KR: sqrt(250) 통상 사용 (정밀하면 해당 연도 실제 거래일)
- US: sqrt(252)

### 5.2 T+2 결제 (실질 D+1 매매)

신호 → 실행 시차 US 보다 유리. 단 KOSDAQ 소형주 시장충격 비용 ↑ → Implementation Shortfall 별도 attribution.

### 5.3 환노출 처리

- KR sleeve 본질 KRW 자산. USD 환산 시 ΔFX 항 발생
- portfolio 통합 측정 = USD 기준 (글로벌 표준)
- Sleeve 평가 = KRW 로컬 기준 (alpha 순도 유지)

## 6. 베타 테스트 구역 운영 룰 (Tier 1 US sleeve)

`UNIVERSE_FUNNEL_REFORM_PLAN_v0.2 §6.2` 의 "베타 테스트 구역" 운영 정의:

- US sleeve 2 종목 = **학습 모드**. 데이터 누적 후 Tier 2 진입 시 확대
- 진입 hurdle: KR Brain v5 score + 5%p (단순 룰, 정밀 산식은 COST_MODEL_SPEC Part II)
- **독립 jsonl**: `data/sleeve_tracking/kr_sleeve.jsonl` + `us_sleeve.jsonl`
- Sharpe / IR / MDD / Hit rate 모두 분리 추적
- 청산 hurdle: US 22% 세금 복리 잠식 회피 — KR 보다 strict
- 잔차 상관 0.4 초과 시 US 축소 검토

### 6.1 운영 데이터 수집 (5/17 sprint 진입 시점)

```
data/sleeve_tracking/
├── kr_sleeve.jsonl       # KR 6 종목 daily metrics
├── us_sleeve.jsonl       # US 2 종목 daily metrics
├── attribution.jsonl     # Brinson-Fachler L1-L3 분해
└── residual_corr.jsonl   # 잔차 상관 월별 (12m rolling)
```

### 6.2 AdminDashboard 표시 (간단)

- Sleeve 별 Sharpe / IR (월별 갱신)
- 잔차 상관 게이지 (0~1, 0.4 노란선, 0.6 빨간선)
- Brinson-Fachler L1-L3 막대 (분기 또는 월)

## 7. 구현 액션 (5/17 sprint)

```
api/portfolio/sleeve_tracker.py (신규)
  + compute_sleeve_sharpe(sleeve_returns, r_f)
  + compute_sleeve_ir(alpha_series, te_method='ex_post')
  + compute_sleeve_mdd(equity_curve, mode='rolling_12m')
  + brinson_fachler_attribution(p_returns, b_returns, p_weights, b_weights)
  + residual_correlation(alpha_kr, alpha_us, rolling=12)
  + singer_karnosky_fx_decompose(kr_returns_krw, fx_series)

api/vams/engine.py
  → 매매 시 sleeve 라벨링 (kr_stock / us_stock)
  → jsonl append (kr_sleeve.jsonl / us_sleeve.jsonl)

framer-components/admin/SleeveTrackingPanel.tsx (신규)
  → 두 sleeve Sharpe·IR·MDD 카드
  → 잔차 상관 게이지
  → Brinson-Fachler 분해 막대

api/scheduling/sleeve_metrics_cron.yml
  → 월 1회 attribution 산출 + jsonl append
```

## 8. 검증 트랙 (65 거래일 PRODUCTION 게이트)

- Sleeve Sharpe 각 ≥ 0.3 (AQR baseline) 목표
- 잔차 상관 < 0.4 유지 확인 (실패 시 US 축소)
- Brinson-Fachler L1 (시장 배분) 효과가 노이즈 수준 (±50bps/년) — 그 이상이면 sleeve split 재설계
- L3 (종목 선택) 이 KR-bias 의 alpha 원천인지 확인 (KR 종목 선택 > US 종목 선택)

## 9. v0.3 통합 정합

이 spec 의 §6 베타 구역 운영 룰 = `UNIVERSE_FUNNEL_REFORM_PLAN_v0.3.md §6.2` 와 정합 유지. 변경 시 양쪽 동시 갱신.

## 10. 메모리 정합

- `feedback_simple_front_monster_back` — Backend (이 spec) 정교 / Frontend (AdminDashboard) 심플
- `feedback_baseline_must_be_segment_scoped` — Sleeve별 baseline 명시 (KR baseline ≠ US baseline)
- `feedback_source_attribution_discipline` — Singer-Karnosky / Brinson-Fachler 학계 출처 명시
- `reference_learning_materials_folder` — 학습자료 5.md 백링크
