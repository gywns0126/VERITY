# ESTATE Brain V0 Plan (2026-05-08)

**Source**: 사용자 Perplexity 호출 결과 (한국 부동산 단지 valuation factor + 폭락 사이클 analog).
메모리 정합:
- `project_estate_brain_kickoff` — 우선순위 백테스트 → 시계열 → drill-down
- `feedback_estate_density_first` — 단지 단위 밀도 (광범위 패턴 이식 X)
- `feedback_master_rule_drift_audit` — 원전 출처 명시 + 조정 산식 주석 의무
- `feedback_perplexity_collaboration` — 외부 사실/통계/법규 = Perplexity (이 plan 의 source 정합)

## 단지 단위 Valuation — 4 Layer

| Layer | 지표 | 산식 | 가중치 (실무 REF) | 역할 |
|---|---|---|---|---|
| **L4** | 인근 실거래 비교 | 동일 생활권 (학군·역세권 500m) 3-5 단지 헤도닉 보정 | **40-50%** | Primary Anchor |
| **L2** | 전세가율 | P_전세 / P_매매 × 100 | **25-30%** | 내재가치 하방 지지선 |
| **L3** | Cap Rate | NOI / P_매매 × 100 (전세는 전월세 전환율 5.0-5.5% 적용) | **15-20%** | 수익성 상한 체크 |
| **L1** | PIR | P_매매 / 권역 중위 연소득 | **10-15%** | 거시 Sanity Check |

## 고평가 4중 신호 (동시 발현 시 신뢰도 가장 높음)

1. **PIR > 권역 10yr 이동평균 + 1σ**
2. **전세가율 < 50%** (서울 기준, 거품 영역)
3. **Cap Rate < 국고채 10년물 - 100bp** (역전 = 채권 대비 부동산 비매력)
4. **인근 실거래 vs KB시세 괴리 > 10%**

## Layer 별 정상 밴드

**PIR**:
- 전국 평균 ~8-10x
- 서울 아파트 15-25x
- 추세 이탈 폭 (현재 - 10yr 이동평균) 이 절대 수준보다 신뢰

**전세가율** (서울 10yr 평균 ~60%):
- ≥70%: 매매 저평가 / 갭투자 과열 동시
- 55-70%: 균형
- <50%: 매매 거품 (2009 35-40% 박힘)

**Cap Rate** (서울 아파트 1.0-1.8%, 2019 FIG):
- DCR × LTV × MC 조합 산식 병행 (감정평가)

**실거래 비교**:
- 시간 보정: ≤6개월
- 공간 보정: 동일 생활권 500m 반경 3-5 단지
- 헤도닉 변수: 면적/층/브랜드/주차/세대수/조망/남향

## ESTATE 사이클 Historical Analog (3 패턴)

VERITY MarketHorizon V2 의 nearest-N analog matching 과 같은 구조 — *부동산 전용*:

| 패턴 | 사이클 | 트리거 | 하락폭 (서울) | 회복 형태 | 회복 소요 |
|---|---|---|---|---|---|
| **Shock-Recovery** | 1997 IMF | 환율·금리 25% | -18.2% (전국 -15.1%) | V자 | 4년 2개월 |
| **Debt-Deflation Drag** | 2008 GFC | 가계부채+공급과잉 | -12% (강남3구 -10%) | U/L자 | 9년+ (서울 16-17년) |
| **Rate-Shock Rebound** | 2022 금리인상 | 0.5→3.5% | -20% (외곽 -30%+) | W자 (핵심지 선행) | 3-6년 (진행 중) |

**공통 패턴**:
- 핵심지 (강남3구·마용성) 가 *먼저 저점 → 먼저 회복*
- 비핵심지 (수도권 외곽) 가 *후하락 → 후회복*
- 즉 *전국 단일 지수* 적용 = 위험. *권역 분리* 필수

## ESTATE Brain V0 산출 schema

```json
"estate_brain": {
  "version": "v0",
  "as_of": "2026-05-08T...",
  "complex_id": "...",  // 단지 식별자
  "valuation": {
    "primary_anchor_pct": 80,  // L4 인근 실거래 비교 = 적정가 대비 %
    "layers": {
      "L1_pir":           { "value": 22.5, "10yr_ma": 18.3, "z_score": 1.4, "verdict": "high" },
      "L2_jeonse_ratio":  { "value": 48.2, "verdict": "low" },         // <50% = 거품 신호
      "L3_cap_rate":      { "value": 1.6, "treasury_10y": 3.2, "verdict": "compressed" },
      "L4_neighbor_gap":  { "kb_price": 12.5e8, "actual": 11.0e8, "gap_pct": -12 }
    },
    "weighted_score": 65,  // 4 layer 가중평균 (40/25/15/10 → 정규화)
    "extreme_signals_count": 2  // 고평가 4중 신호 중 N개 발현
  },
  "cycle_analog": {
    "current_phase": "Rate-Shock Rebound",  // Shock-Recovery / Debt-Deflation Drag / Rate-Shock Rebound
    "phase_progress": "recovery_phase_2",     // 단계 (예: 저점 / 초기회복 / 본격회복)
    "nearest_historical": [
      { "name": "2022 금리인상", "distance": 0.18, "recovery_after_pct": "+15% in 24M" },
      { "name": "2008 GFC", "distance": 0.45 }
    ]
  },
  "regional_split": {
    "core": "강남3구·마용성",  // 핵심지 별도 산출
    "non_core": "수도권 외곽"
  },
  "model_meta": {
    "factor_weights": "REF Perplexity 2026-05-08 (한국 실무 가중치)",
    "analog_source": "KB부동산·한국부동산원 1997/2008/2022",
    "version": "v0_hardcoded"
  }
}
```

## 데이터 source (이미 박힌 인프라 우선)

**박힘**:
- R-ONE 매매지수 + 미분양 (`api/collectors/r_one.py`, 메모리 `project_rone_api_spec`)
- VWORLD 지오코더 (`project_vworld_api_spec`)
- KOSIS Param 우회 (메모리 박힘)

**추가 필요**:
- 단지 단위 KB시세 (KB부동산 공개 API 또는 scrape)
- 단지 단위 실거래 (국토부 실거래가 공개데이터)
- 권역 중위소득 (KOSIS)
- 전세가율 (한국부동산원)
- Cap rate 산정용 임대료 (단지 단위 부재 시 권역 평균)

## V0 박는 작업 (진입 시점 — 다른 세션 결정)

1. `api/intelligence/estate_brain.py` 신규 — 4 layer 산식 + 가중평균
2. 데이터 collectors 보강:
   - KB시세 collector (단지 단위)
   - 실거래가 collector
   - 권역 중위소득 (KOSIS)
3. `data/estate_portfolio.json` 의 단지별 estate_brain 박음
4. Frontend EstateBrainPanel (또는 기존 Landex 컴포넌트 흡수) — 4 layer + 4중 신호 + analog

## V1 (운영 후)

- 동적 analog matching (KB·한국부동산원 시계열 fetch + 권역 분리)
- 헤도닉 회귀계수 자체 학습 (단지 단위)
- 단지 별 *진입 가능성 grade* (VERITY brain v5 의 grade 패턴)

## V2 (5/17 후 게이트)

- ESTATE Mode (보수/중간/공격) — VERITY capital_3tier_mode 와 직교
- ESTATE 단지 별 *예상 holding period* (1997 V자 / 2008 U자 / 2022 W자 분류 기반)

## 메모리 정합 검증

- ✅ `feedback_estate_density_first` — VERITY 이식 X. 단지 단위 *밀도* (4 layer factor + 1 단지)
- ✅ `feedback_master_rule_drift_audit` — 원전 출처 (Perplexity 2026-05-08) + 산식 주석
- ✅ `feedback_real_call_over_llm_consensus` — Perplexity 답변은 *시장 사실/법규* 영역 (LLM 합의 X, *외부 source*)
- ⚠️ 4 layer 가중치 (40/25/15/10) = REF 실무 평균. 단일 표준 X — V1 백테스트 후 자체 calibration 의무

## 운영 검증

- V0 박은 후 1-2개월: 4 layer 산출 정확도 측정
- 3-6개월: 고평가 4중 신호 vs 실제 가격 변동 hit rate 측정
- 12개월: analog matching 정확도 (Rate-Shock Rebound 진행 단계 예측 vs 실제)

---

# V0.2 — Perplexity 추가 source (2026-05-08)

사용자 추가 Perplexity 호출 3건. plan 즉시 업그레이드.

## 데이터 source 정밀화 (질문 1)

**계층형 데이터 스택 — 무료/유료 분기**:

| Layer | source | 비용 | 단지 단위 |
|---|---|---|---|
| 실거래가 backbone | 국토부 RTMS API (`getRTMSDataSvcAptTrade`) | 무료 (1k-10k/일) | ✓ 단지명·면적·금액·층 |
| 가격지수 overlay | 한국부동산원 Open API | 무료 | ✗ 권역만 |
| 시세 reference | KB데이터허브 | 무료 (UI) / 기관 유료 (API) | △ 웹 조회만 |
| 단지 geocoding | VWORLD (이미 박힘) | 무료 | ✓ |
| 전월세 | RTMS `getRTMSDataSvcAptRent` | 무료 | ✓ |

**V0 권장 stack** (메모리 `feedback_real_call_over_llm_consensus` 정합 — 무료 + 자체 검증):
1. 실거래가 = RTMS API (자동 cron)
2. 시세 정합 = KB데이터허브 (수동 spot-check, V1 대량 자동화 시 직방 RED B2B 또는 자이랜드 AVM)
3. 지수 = 부동산원 Open API
4. 단지 좌표 = VWORLD

**한계**:
- RTMS = 단지명 *문자열* 만 (고유 ID X) → 동일 단지 중복 표기. *clustering 필요*
- 신고 lag ~30일

## Macro lead time (질문 2) — 운영 cycle_analog 산식 직결

| 신호 | 매매가 lead time | 신뢰도 | 방향 | source |
|---|---|---|---|---|
| 전세가격 상승 | **1-3개월** | ★★★★★ | + | 시차상관 / VAR |
| 전세가율 80%+ | 단기 +, **24M 후 −** | ★★★★ | 양날 | 패널 |
| 착공 실적 ↓ | **26-30개월** | ★★★★ | + (공급↓) | 교차상관 |
| 미분양 증가 | **3-6개월** | ★★★★ | − | Granger |
| 인허가 | **32개월** (신뢰성 약화) | ★★★ | + | CERIK |
| 호가 지수 | **1개월** | ★★★★ | + | 시차상관 |
| SNS 감성 | **2개월** | ★★★ | + | VAR+Granger |
| **금리 인상** | **3개월 시작 / 5-6개월 피크 / 12-18개월 지속** | ★★ (비선형) | − (시기별 역전) | TVP-VAR (KRIHS) |

**핵심 함의**:
- 단기 (1-3M) momentum = 전세가격 변화율 + 호가 + 거래량
- 중기 (3-12M) 추세 = 전세가율 80% 분기 + 미분양 누적
- 장기 (12M+) 구조 = 착공실적 → 입주 시차 (26-32개월)
- 금리 = *단독 시그널 X*. 전세가율과 교호작용
- **forward return horizon 26주 (6개월) 최적** — 전세 선행 1-3개월 + 가격 반응 2-3개월

**고평가 4중 신호 추가 신호** (V0 plan 의 4중 + lead time):
- 미분양 누적 변화율 +30% (3-6M lead) → 하락 강 신호
- 전세가율 < 50% + 24M 후 역전세 위험 = 중장기 침체

## 재건축/재개발 6단계 stage 분류 (질문 3)

**6단계 enum**:
1. `district_designation` — 정비구역 지정 (초기 기대)
2. `union_setup` — 조합설립 인가 (**재건축 최대 상승** 구간)
3. `business_plan` — 사업시행 인가 (분담금 변동성↑)
4. `management_plan` — 관리처분 인가 (**재개발 최대 상승**, P값 명시화)
5. `relocation` — 이주·철거 (주변 전세가 +5M 내 급등)
6. `completion` — 준공·입주 (신축 프리미엄)

**평균 소요 기간** (전국 118 사업장 국토부 데이터):
- 정비구역 지정 → 조합설립: 27.9개월
- 조합설립 → 사업시행: 31.3개월
- 사업시행 → 관리처분: 20.9개월
- 관리처분 → 이주: 6-12개월
- 이주 → 준공: 24-36개월
- **전체 평균 10년 (서울시 처리기한제 2025.7~ 13년 단축 목표)**

**가격 영향 패턴** (재건축 vs 재개발):

| 단계 | 재건축 | 재개발 |
|---|---|---|
| 1 정비구역 | 🟡 완만 | 🟡 완만 |
| 2 조합설립 | 🔴 **최대 상승** (기대 선반영) | 🟡 완만 상승 |
| 3 사업시행 | 🟡 (이미 반영) | 🟠 상승 지속 |
| 4 관리처분 | 🟡 일시 조정 가능 | 🔴 **최대 상승** (P값) |
| 5 이주·철거 | 🟡 입주권 완만 | 🟡 입주권 완만 |
| 6 준공·입주 | 🟠 신축 프리미엄 | 🟠 신축 프리미엄 |

**진입 최적 시점**:
- 재건축 = **정비구역 지정 ~ 조합설립인가 직전** (기대 선반영 직전)
- 재개발 = **사업시행 인가 전후** (관리처분까지 최대 상승 구간 진입)

**관리처분인가 monitoring 핵심**:
- 종전자산평가 결과 발표 시점 — 감정가 > 기대치 → 프리미엄 ↑ / 감정가 < 기대치 → 프리미엄 급락 + 매도 폭탄
- 일반분양 공고 → 분양권 프리미엄 vs 입주권 프리미엄 역전 가능

**이주 시점 시그널**:
- 이주 시작 → 5개월 내 주변 반경 전세가 급등 (실증 확인)
- → 해당 권역 매매가 상승 예측 선행지표

## ESTATE Brain V0 schema 보강

```json
"estate_brain": {
  "version": "v0.2",
  "complex_id": "...",
  "valuation": { /* 4 layer 그대로 */ },
  "cycle_analog": {
    "current_phase": "Rate-Shock Rebound",
    "phase_progress": "recovery_phase_2",
    "lead_time_signals": {
      "jeonse_3m_lead":     { "value": "+1.5%", "verdict": "moderate_up" },
      "jeonse_ratio_24m":   { "value": 65, "verdict": "balanced" },
      "construction_starts_lead": { "value": "-12% YoY", "lead_months": 28, "verdict": "supply_tight_in_2y" },
      "unsold_units_lead":  { "value": "+18% YoY", "lead_months": 4, "verdict": "negative_pressure" },
      "rate_lead":          { "lead_months": 6, "rate_change": "-0.5pp", "verdict": "supportive" }
    },
    "forward_return_horizon_weeks": 26
  },
  "redevelopment_stage": {
    "stage": "management_plan",  // 6단계 enum
    "stage_label_ko": "관리처분 인가",
    "months_to_next_stage_estimated": 8,
    "price_phase": "max_uplift_redevelopment",  // peak / mid / pre / post
    "monitoring": {
      "valuation_announcement_pending": true,  // 종전자산평가 발표 대기
      "general_subscription_announced": false
    }
  }
}
```

## 운영 우선순위 (다른 세션 결정)

**즉시 박을 것**:
1. RTMS API collector (`api/collectors/molit_rtms.py`)
2. 단지명 clustering 로직 (RTMS 의 문자열 → 단지 ID 매핑)
3. estate_brain.py 의 lead_time_signals 산출 (전세 / 미분양 / 착공 / 금리 5신호)
4. redevelopment_stage 분류 (정비구역 + 조합설립 데이터 source 별도 — *국토부 도시정비 정보몽땅* 등)

**V1 (운영 6-12개월 후)**:
- 자체 VAR/Granger 분석 — 한국 시계열 (KB / 부동산원 / 한은 / 국토부) 으로 lead time 정밀 calibration
- 직방 RED 또는 자이랜드 AVM B2B 계약 (KB시세 정합)
- 단지별 stage 자동 progression tracking
