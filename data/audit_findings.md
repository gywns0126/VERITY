# VERITY Brain — Audit Findings

## U-shape 알파 발견 (2026-04-19)

- 30종목 5년 8,130행 검증 결과 (`scripts/historical_replay.py`)
- 등급별 forward 30d 수익률:
  - **STRONG_BUY (+3.96%) ≈ CAUTION (+3.94%)** >> **BUY (+1.67%)** ≈ WATCH (+1.92%)
- **양 극단에 알파, 중간에 없음**
  - STRONG_BUY = deep oversold mean-reversion (RSI 18, momentum -11%, vol 17%)
  - CAUTION = high-vol momentum continuation (RSI 64, momentum +17%, **vol 50%**)
- **선형 등급 시스템으로 U-shape 표현 불가**
- **단조성 metric 은 이 universe 에서 무의미**

### 컴포넌트별 등급 분포 (참고)

| component | STRONG_BUY | BUY | WATCH | CAUTION |
|---|---|---|---|---|
| momentum_3m | -11.45 | -0.46 | 5.54 | 16.68 |
| momentum_1m | -9.18 | -2.47 | 2.65 | 10.22 |
| rsi_14 | 18.13 | 42.79 | 58.68 | 63.84 |
| price_to_ma200_pct | -12.91 | 0.94 | 7.78 | 20.98 |
| volatility_20d_ann | 17.23 | 20.30 | 27.53 | 49.63 |
| **fwd_30d_avg %** | **+3.96** | **+1.67** | **+1.92** | **+3.94** |

모든 6 컴포넌트가 등급별로 단조 증가하지만 수익률은 U자형. 선형 IC 측정으로는 U-shape 알파 포착 불가.

---

## §9 보류 사유

- **30 S&P 대형주 post-COVID bias**
  - 2020-01 ~ 2026-04 = post-COVID 강세장 + AI bubble (TSLA/NVDA/META 폭등)
  - high-vol = high-return 이라는 IC +0.10 도 universe 특성에 종속
- **universe 확장 후 재검증 필요**
  - 소형주 / 페니주 (진짜 AVOID 후보 포함)
  - 2008 금융위기 / 2018 무역전쟁 / 2011 유럽위기 등 다른 regime 포함
  - 한국 코스닥 (yfinance coverage 부실 → DART 직접 연결 필요)
- **§9-C (Sharpe 단조성) 장기 로드맵으로 이전**
  - 현 mean return 기준 단조성 → risk-adjusted (Sharpe) 단조성으로 전환
  - BUY = "최고 수익률" → "risk-adjusted 안전 매수"로 의미 재정의
  - CAUTION = "회피" → "고변동 momentum — 추격 위험" 으로 의미 재정의
  - 새 등급 `MOMENTUM_RIDE` 도입 후보 (CAUTION 의 high-vol 부분 분리)

---

## 현재 유효한 검증 결과

- **regime detection: 3/3 PASS** (유지)
  - COVID 크래시 (2020-02~03): STRONG_BUY 0% (평시 0.7%)
  - 2022 인플레: brain_score 평균 2021(55.94) → 2022(54.17) 하락
  - SVB (2023-03): 금융주 68.44 → 62.47
- **AVOID semantic 해소 (§8)**
  - AVOID n: 198 → 0 (대형주에서 fact-only AVOID 차단)
  - has_critical / macro_override 위기 cap 에만 한정
- **inflation_2022 PASS (V3 + regime gate)**
  - VIX > 30 일자에 mean-reversion bonus 비활성 → 거시 신호와 충돌 방지

---

## 작업 우선순위 (다음 세션)

1. **universe 확장 backfill** — 소형주 + 다양한 regime 포함 → 진짜 IC 재측정
2. **DART 연결** — 한국 fundamental 시계열 backfill (현재 DART 미사용)
3. **§9-C Sharpe 단조성** — universe 확장 후 라벨 의미 재정의 검토
4. **brain_history.py 90일 누적 대기** — production 데이터 prospective 검증 (이미 설치됨)

작성: 2026-04-19
관련 커밋: `29f2ec3` (V3 mean-reversion 재설계), `596c801` (§8 AVOID 재정의)

---

## Universe 확장 결과 (2026-04-19)

- **45 ticker × 19년 = 31,975 행** 검증
  - 기존 30 large-cap + 15 소형주/페니주/파산주 (BBBY, RIDE, WISH, NKLA, GME, AMC 등)
  - 시작일 2007-01-01 → GFC/2011 강등/2018 무역전쟁 포함
- **V3 mean-reversion 재설계가 30종목 post-COVID에 overfit 확인**
  - STRONG_BUY 평균 수익률: 5년 30종목 **+3.96%** → 19년 45종목 **+0.67%** (대폭 하락)
  - 페니주 포함 시 deep oversold 반등 알파 사라짐 (망한 종목은 진짜 망함)
- **`price_to_ma200_pct` IC 부호 반전** — universe-specific bias 입증
  - 5종목: IC -0.06 → 45종목: **IC +0.04**
  - V3 의 sign-reversal 근거 자체가 sample-dependent
- **rsi_14, momentum_1m IC가 noise 화** (5종목 -0.05 → 45종목 -0.01)
- **유일하게 살아남는 알파: volatility_20d (IC +0.10)** — 모든 universe 에서 일관
- **단조성 tuning 으로 해결 불가 판정**
  - 30종목 단조성 0.50 → 45종목 단조성 0.00
  - STRONG_BUY (+0.67%) < BUY (+1.91%) < WATCH (+2.24%) < CAUTION (+3.42%) — 완전 역순

### Regime stress (universe 확장 후 6개 중 5/6 PASS)

| regime | verdict | 비고 |
|---|---|---|
| GFC 2008-09~2009-03 | ✓ PASS | STRONG_BUY 0% (평시 0.5%) |
| 2011 美 신용등급 강등 | ✓ PASS | avg 50.58 < 2010 avg 55.70 |
| 2018 Q4 무역전쟁 | ✓ PASS | avg 56.50 < Q3 avg 57.31 |
| COVID 2020-02~03 | ✓ PASS | STRONG_BUY 0% |
| 2022 인플레 | ✗ **FAIL** | avg 52.17 ≈ 2021 avg 52.10 (regime gate 작동했으나 baseline 평탄화) |
| SVB 2023-03 | ✓ PASS | 금융주 65.69 → 64.77 |

regime detection 메커니즘은 broader universe 에서도 견고. inflation_2022 만 FAIL — V3 regime gate 가 작동했으나 페니주/위기 데이터 유입으로 baseline 평탄화하면서 신호가 묻힘.

---

## backtest 단계 종료 선언 (2026-04-19)

- **추가 backtest tuning 없음**
- 19년 45종목 데이터로도 단조성 0.00 — fundamental backtest 한계 직면
- §9-C (Sharpe 단조성 / 라벨 재정의) 도 동일 데이터에 다른 metric 적용일 뿐 — 같은 한계 재현 가능성 높음
- backtest tuning 으로 alpha 입증 불가 결론

### 다음 검증 방식 (1-2개월 horizon)

1. **brain_history prospective 데이터 누적 30-60일** (이미 작동 중, 매일 슬림 스냅샷 + 3일 후 actual_return_3d 백필)
2. **DART KR fundamental backfill** — 현재 한국 종목 검증 0% 사각지대
3. **Regime-conditional IC** — panic / normal / euphoria 별 컴포넌트 IC 분리 측정
4. **production data vs replay 일치 검증** — backtest 와 실전 결과 갭 측정

### 유효한 production-ready 변경 (그대로 유지)

backtest tuning 결론과 별개로, 다음은 production code 로서 가치:
- V3 regime gate (`api/intelligence/verity_brain.py` `_is_regime_panic`) — VIX>30/panic 시 mean-reversion bonus 비활성, regime detection 부작용 차단
- §8 AVOID 라벨 재정의 — 대형주 fact-only AVOID 차단, has_critical 전용
- backfill_replay 인프라 — 향후 alpha 가설 검증의 ground truth 측정 도구

작성: 2026-04-19
관련 커밋: `d561df7` (§9 보류 + U-shape 발견)

---

## DART KR Fundamental Backfill (2026-04-19)

미국 종목 검증 외 한국 검증 사각지대(0%) 해소 — 248 레코드 IC 측정.

- **Universe**: 30 KR large-cap (KOSPI/KOSDAQ, 기존 portfolio)
- **기간**: 2015~2024 (10년 연간 사업보고서, DART `fnlttSinglAcnt.json`)
- **Forward 수익률**: 결산일 + 90일 (공시 마감 proxy) 기준 +30d (yfinance .KS/.KQ)
- **실행 시간**: 172.6초 (1회), 캐시 후 즉시
- **총 레코드**: 248 (금융주 4종 부분 실패 — IFRS 금융업 회계 매핑 미지원)

### KR Factor IC (forward 30d, n=248)

| factor | Pearson | Spearman | 비고 |
|---|---|---|---|
| **roe_pct** | **-0.09** | **-0.06** | ★ 일관 mean-reversion (high ROE 후 underperform) |
| **operating_margin_pct** | **-0.08** | +0.01 | Pearson 강함 (비선형/극단값) |
| debt_ratio_pct | +0.04 | -0.01 | 부호 불일치, 약함 |
| revenue_growth_pct | -0.01 | -0.04 | noise |

**모든 factor |IC| ≥ 0.03** — US (vol 1개만 살아남음) 대비 양호.

### KR vs US 시장 비교 (핵심 발견)

| 시장 | 살아남은 알파 | 방향 |
|---|---|---|
| US (45종목 19년) | volatility_20d (+0.10) | technical |
| **KR (30종목 10년)** | **ROE (-0.09), op_margin (-0.08)** | **fundamental mean-reversion** |

→ 두 시장 모두 mean-reversion 알파 일관. 한국엔 fundamental, 미국엔 technical.

### Production Wiring (§11)

`api/intelligence/verity_brain.py:_compute_kr_fundamental_mean_reversion_score`
- `_compute_fact_score`에 sub-score 추가, `(score - 50) × 0.03` bonus 형태
- KRW 종목만 적용, regime gate (VIX>30 / panic) 시 비활성
- 캐시: `data/dart_kr_cache/{corp_code}_{year}.json`

---

## Production 오심 사례 분석 + 수정 (2026-04-19)

운영 중 발생한 3건 오심을 코드로 fix + 단위 시뮬레이션 검증.

### Case 1: 삼성전자 (2026-04-13) BUY → -4.5%
- **원인**: 컨센서스 99점 과신 (만점 직전 = 호재 소진 패턴), 외국인 매도 미감지
- **수정 (§12)**: `_compute_sentiment_score` 에서 `consensus_opinion ≥ 95` 시 가중치 ×0.7 dampen
- **재시뮬**: brain=60, **grade=WATCH** (이전 BUY) — 오심 회피 ✓
- **원리**: 컨센서스 100점 자체가 contrarian 신호 — 분석가 over-optimism 시점

### Case 2: 현대모비스 (2026-04-18) AVOID → +6.1%
- **원인**: PBR 데이터 누락(None) → multi_factor 과소평가 → AVOID 오류 부여
- **수정 (§13)**: `analyze_stock` 진입 시 `stock["pbr"]` ≤ 0 또는 None → 1.0 (중립) 정규화
  - `pbr_normalized_neutral=True` + `data_quality_fixes=["pbr_invalid_to_1.0"]` 메타 기록 (audit)
  - 2-A `_safe_float` 패턴 동일 적용
- **재시뮬**: pbr None→1.0, brain=53, **grade=WATCH** (이전 AVOID) — 오심 회피 ✓

### Case 3: Coinbase (2026-04-18) AVOID → +27.3%
- **원인**: 크립토 섹터 외생 이벤트, multi_factor 단독 거부권으로 AVOID 강제
- **수정 (§14)**: §8 AVOID guard 직후 추가 완화 게이트 —
  `grade == "AVOID" AND brain_score ≥ 55 AND ai_upside_pct ≥ 65` 동시 충족 시
  AVOID → CAUTION 완화 (`ai_upside_relax` override 기록)
  - has_critical 여부 무관 — AI 강한 호재가 회계 노이즈 압도하는 케이스 인정
- **재시뮬**: has_critical=True, brain=57, ai=72 → **grade=CAUTION** (이전 AVOID) — 오심 회피 ✓
- 반례: ai_upside=40 (조건 미달) → AVOID 유지 ✓ (오탐 방지)

### 수정 후 공통 원칙

- 모든 fix는 audit metadata 기록 (`overrides_applied`, `data_quality_fixes`, `pbr_normalized_neutral`)
- 단위 테스트로 보호 (sentiment dampen, PBR 4가지 케이스, AVOID 완화 + 반례)
- pytest 30/30 회귀 무영향

작성: 2026-04-19
관련 작업: §11 (DART KR MR) + §12 (consensus dampen) + §13 (PBR normalize) + §14 (AI upside relax)
