# Perplexity 질문 batch — 2026-05-24

> **출처**: 사이트 분석 도구 전수검사 sprint (이번 세션 9 commit 후속). 
> **목적**: 산식 신설 박힌 sprint (E / F / G) 진입 *전*, 사용자 PM 측에서 Perplexity 에 박아 *학술 정합 확인 + RULE 7 사전 등록 input* 확보.
> **활용 패턴**: `feedback_perplexity_collaboration` 정합 — 시스템/코드=Claude, 외부 사실/통계/법규=Perplexity, 애매 시 사용자 핸드오프. 답변 받은 후 `docs/PERPLEXITY_ANSWERS_*.md` 에 박음.

---

## Q1. ETFScreenerPanel — KR ETF Z-Score 적용 학술 사례

**Context**: 
- VERITY 의 ETFScreenerPanel (framer-components/pages/market/ETFScreenerPanel.tsx) = 현재 단순 ETF nav listing. 깊이 부족.
- 메모리 `project_altman_z_korea_standard` 박힘 — KOSPI/KOSDAQ Altman Z″ EM 변형 (3.25 + 6.72X1 + 3.26X2 + 6.72X3 + 1.05X4, 컷 2.6/1.1, 금융 제외).
- 가설: KR ETF (특히 thematic / sector ETF) 의 *holding 종목 Z-Score 가중평균* 을 ETF risk metric 으로 활용.

**질문**:
> 한국 ETF (KOSPI/KOSDAQ 상장 ETF) 에 Altman Z-Score 변형 적용한 *학술 사례* 또는 *실무 사례* 있는가? holding 가중평균 Z″ EM 산식이 ETF 부도 risk / drawdown 예측력에 유의미한가? (Bharath-Shumway 2008 / Beneish M-Score 비교 정합 의무.) 만약 사례 부족 시 ETF risk metric 대체 지표 권고 (downside deviation / Sortino / VaR 등 ETF 적용 사례).

**RULE 7 사전 등록 의무 정보** (답변에 박혀야 할 것):
- 산식 source (학술 논문 / 기관 보고서)
- N (sample size, ETF 수)
- 검증 기간 (몇 년)
- 한국 ETF 특유 (시장 구조 / 운용사 / 추적 오차) 보정 의무
- 신뢰도 (significance level)

---

## Q2. CashFlowRadar — fund_flows + cftc_cot + program_trading cross-validation 학술 사례

**Context**:
- CashFlowRadar = portfolio.fund_flows + crypto_macro + macro 만 사용. 그러나 portfolio 에 cftc_cot + program_trading + kis_market.foreign_institution 도 박혀있음.
- 가설: *외인 net buy* (KIS) + *기관 net buy* (CFTC COT) + *프로그램 매매* (KIS) 3 source 모두 *같은 방향* = *강한 cross verdict* (단일 source 보다 신뢰도 높음).

**질문**:
> 다중 자금 흐름 source (외인 / 기관 / 프로그램 매매 / fund flows) 의 *cross-validation 산식* 학술 사례? 단순 sum vs weighted vs majority vote vs Bayesian 비교 (Granger causality / cointegration 기반). 한국 시장 특유 (외인 = 글로벌 패시브 / 기관 = 연기금 / 프로그램 = 메이저 증권사) 의 source 신뢰도 차이 정합. 합의도 (agreement ratio) 산식 + threshold 권고.

**RULE 7 사전 등록 의무 정보**:
- 산식 source
- N (검증 거래일 수)
- KOSPI / KOSDAQ 각각 검증 결과
- forward return 예측력 (IC / ICIR)
- regime 의존성 (bull / bear / sideway)

---

## Q3. macro_industry_align backend chain — themes_pulse 빌더 방법론

**Context**:
- macro_industry_align.py 박혀있음 (api/intelligence/macro_industry_align.py, mapping.json 박힘 5/20).
- dependency 4 파일 중 1 만 존재: macro_industry_mapping.json (✅) / macro_themes_pulse.json (X) / industry_themes_pulse.json (X) / macro_industry_alignment.json (output, X).
- 메모리 `project_macro_themes_tracker` 박힘 = "IB strategist weekly themes 추출, A 진입 5/20". 빌더 신설 의무.

**질문**:
> *Top-down macro themes* (IB strategist 의 weekly outlook) 자동 추출 방법론? Perplexity Sonar Pro 로 *Goldman Sachs / Morgan Stanley / JPM / BlackRock weekly* 매크로 themes 추출 → 8 매크로 카테고리 (성장 / 인플레 / 금리 / 환율 / 원자재 / 신용 / 지정학 / 정책) × {positive / negative / neutral} × conviction (high/mid/low) 정량화 산식. *Industry themes* (US15 컨콜 keyword 추출) 도 동일 방법론. 비용 효율 + LLM hallucination 보호 패턴.

**RULE 6 정합 의무**: 본 빌더는 *narrative LLM 모듈* 아니라 *데이터 추출 → 정량 dict* 박는 게 정공법 (feedback_no_new_llm_narrative_features 정합).

**구현 cron 의무**:
- macro_themes_pulse 빌더 = 주 1회 (월요일 06:00 KST)
- industry_themes_pulse 빌더 = 주 1회 (화요일 06:00 KST, US 컨콜 직후)
- macro_industry_align runner = 주 1회 (수요일 06:00 KST)
- 결과 attach = main.py 의 portfolio.json 박음

---

## Q4. sector_trends builder 의 정확한 정상 동작 명세

**Context**:
- 메모리 acb2c12c / 193e64c4 fix — sector_trends 1m/3m/6m/1y 가 trail 부족 시 *동일 데이터셋* 반환 결함 검증.
- 진짜 정상 동작 = 각 period 별 *해당 기간 안의 snapshot 만* 사용. period < actual_span_days 시 그 기간 안 snapshot 만 slice.

**질문**:
> 시계열 데이터 (일별 snapshot) 의 *기간별 통계 산출* 표준 방법론? `load_snapshots_range(days)` 가 N 일 전 ~ 어제 일자 모두 load 박는데, *데이터 부족* (예: 49d trail / 90d 요청) 시 caller 가 어떻게 처리해야 정공법? (a) sliding window — *most recent N day*, (b) anchored window — *N day ago to now*, (c) skip + flag insufficient_trail. VERITY 의 sector_trends 시각화 case 정합 권고.

**RULE 7 회피**: 본 질문은 *산식* 변경이 아닌 *동작 명세* 확인. RULE 7 적용 X.

---

## Q5. Brain audit fx_shock σ 산출 — 동적 windows 학술 정합

**Context**:
- verity_brain.detect_macro_override 의 *fx_shock* 게이트 = USD/KRW 의 *90일 σ × 3 = 3σ threshold*.
- 메모리 박힘 — 정상 σ ≈ 0.50%/일 (2010-2024 평균) / 2025-2026 σ ≈ 0.60% (NYU VLAB). fat-tail (excess kurtosis 4-6).
- 현재 fix b8e1b18d — trail 부족 시 "최근 N일 σ" 동적 label. 단 *3σ threshold* 자체는 그대로.

**질문**:
> USD/KRW 일변동률 σ 산출의 *최적 window* 학술 정합? 90일 (이동평균) vs EWMA (RiskMetrics) vs GARCH(1,1) vs realized variance. fat-tail (excess kurtosis 4-6) 시 *3σ threshold* 가 진짜 1차 확률 (정규 0.27%) 적용 가능한가? 한국 외환시장 특유 (2008/2022 stress / NDF 시장 / 한미 금리 spread) 정합. 안정기 σ floor 0.30% 검증 (현 코드 minimum).

**RULE 7 사전 등록 의무**: σ window / threshold 변경 시 PM 승인 + commit.

---

## 답변 후 활용

1. 사용자 PM 측 → Perplexity 박음 (Sonar Pro 권고)
2. 답변 → `docs/PERPLEXITY_ANSWERS_20260524.md` 박음
3. 각 질문 별 *학술 정합 확인* 후 *RULE 7 사전 등록* commit 박음 (예: `pre-register(brain): Q1 Z-Score KR ETF 산식 사전 등록`)
4. 사전 등록 후 *해당 sprint* (E/F/G) 진입 가능

---

## 메모리 정합

- `feedback_perplexity_collaboration` — 외부 사실/통계/법규 = Perplexity 핸드오프
- `feedback_methodology_pre_registration` — 산식 변경 사전 등록 의무
- `feedback_pm_decision_trail_in_commit` — PM 결정 = WHY / DATA / EXPECTED 3요소
- `feedback_threshold_calibration_overfit_guard` — 임계 조정 = 곡선 맞추기 회피
- `feedback_source_attribution_discipline` — 신호/룰/임계 단일 명확 출처 + 자체 신호 명시

## 출처

생성: 2026-05-24 sprint H/I 후 (ce3d1a76 commit 시점)
다음 단계: 사용자 답변 → `docs/PERPLEXITY_ANSWERS_20260524.md` 생성 후 사전 등록 commit
