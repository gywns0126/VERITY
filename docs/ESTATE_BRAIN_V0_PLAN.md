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
