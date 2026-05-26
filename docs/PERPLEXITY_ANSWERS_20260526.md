# Perplexity 답변 batch — 2026-05-26

> **source**: Perplexity Sonar Pro (사용자 PM 측 박음)
> **date**: 2026-05-26
> **Q file**: `docs/PERPLEXITY_QUESTIONS_20260526.md` (9 Q, P0×2 + P1×2 + P2×5)
> **cost**: 사용자 PM 측 박음 (예상 $0.5~1.5)
> **후속 행동 분류**: ✅ Engineer 자율 박을 거 / ⏳ PM 사전등록 의무 (RULE 7) / 📋 별 sprint 의제

---

## Q1 답 (P0) — 외부 증권사 리포트 양식 표준

### 핵심 답

**한국 6대 증권사 (KB/미래/한투/삼성/NH/신한) 리포트 표준**:
| 구분 | 주요 구성 | Chart/Table/Prose 비중 | 모델 노출 정책 |
|---|---|---|---|
| Daily | 시장 요약 → 섹터 → 종목 이슈 | Chart 30% / Prose 70% | 거의 없음 (방어형) |
| Weekly | 매크로 → 전략 → Top Pick | Table 40% / Chart 30% / Prose 30% | 밸류에이션 배수만 |
| Monthly/Quarterly | 커버 → 매크로 → 섹터 → 종목 → 리스크 → 면책 | Chart 40% / Table 30% / Prose 30% | 목표주가 산식 부분 노출 |

면책 = **후미(마지막 page)** 한국 표준, 모델 = **방어형** (PER 배수·WACC만 공개).

**미국 sell-side (GS/MS/JPM/BofA/Citi)**:
- Initiating Coverage = 30~80p (Summary → Business → Industry → Financials → Valuation → Risk)
- Earnings Preview = 3~8p
- Sector Update = 10~20p
- Strategy Note = 5~15p
- 모델 = **적극형** (DCF/Comps 가정 표 appendix 공개)

**Goldman "Conviction List"** = 고확신 아이디어 별도 운영. report = Investment Thesis → Financial Model → Valuation → Risk → Disclaimer.

### VERITY N<50 권고 (옵션 a/b/c)

| Option | 양식 | 특성 | 권고 |
|---|---|---|---|
| **a (Goldman 압축형)** | Conviction Brief 2p, 핵심 thesis 1문장 + 산식 공개 | 차별화 강함, IP 노출 risk 중간 | 단계적 미래 |
| **b (한국 daily 방어형 변형)** | 현 7장 + "Brain v5 자기 산식 노출" 1장 추가 | RULE 7 정합, N<50 방어 가능 | **✅ 권장** |
| **c (블로그형 hybrid)** | 가설-실험-결과 (Substack형) | LLM 차별화 극대화, IP risk | Phase 2+ |

### 모델 노출 위험 vs 이득

- **위험**: 모델 게이밍 / IP 노출 / N<50 미검증 신뢰도 손상
- **이득**: LLM 무료 tier 차별화 / 학습 trail 누적 / "투명성" 포지셔닝

### ✅ VERITY 후속 action

- **이미 박힘**: 5/26 commit `2d63b2e2` = Option b 정확 정합 (자기 trail 노출 1장 추가, RULE 7 가설 표기). **추가 박을 거 X**.
- 다음 단계 = Option a (Conviction Brief 2p) 의제 큐잉 — Phase 2 진입 trigger.

---

## Q2 답 (P0) — PKM 자기 자산 통합 (Obsidian + Quartz)

### 공개 vault 사례

- **Andy Matuschak** (notes.andymatuschak.org) — Evergreen notes, 백링크, 산식 비공개
- **Maggie Appleton** (maggieappleton.com) — Quartz, 공개/비공개 분리 명확
- **thelulzy/TF-EE-quartz-obsidian-vault** (GitHub) — Quartz + Obsidian 구현 예시
- **국내 퀀트 전용 vault = 사례 없음** → **VERITY 선점 기회** ✓

### 공개 vs 비공개 분리 룰

Quartz `.export-ignore` 로 **비공개 폴더 빌드 제외**.

| 공개 (Quartz publish) | 비공개 (PM 전용) |
|---|---|
| Brain v5 설계 철학/목표 | 실제 임계값 숫자 (75/60/45/25) |
| Lynch 6분류 개념 설명 | 종목별 실제 점수/등급 |
| 산식 논리 구조 | 가중치 (7:3) 정확한 수치 |
| Phase 0 운영 현황 | KIS 토큰 / API key |

### 자동화 pipeline

GitHub Actions + Vercel deploy hook:
1. Obsidian 로컬 편집 → `npx quartz sync` → GitHub push
2. GitHub Actions `deploy.yml` 자동 트리거 → Quartz build → GitHub Pages / Vercel
3. VERITY 메모리 시스템 (`memory/*.md`) 통합 = **별 vault 권장** (직접 mirror = 민감 정보 노출 risk)

### 비용 (총 ~$1/월)

| 항목 | 비용 |
|---|---|
| Quartz hosting (GitHub Pages) | 무료 |
| Obsidian | 무료 (Sync $10/월 = iCloud 대체) |
| Vercel | 무료 |
| 도메인 .com | ~$1/월 |

### 📋 VERITY 후속 action (별 sprint)

- **자기 trail 강화 sprint O path 진입 가능** ([[project_brain_self_trail_strengthening_2026_05_25]])
- 사전 결정 의제 = (1) vault 분리 (공개 = "VERITY methodology vault" / 비공개 = 현 memory 시스템) (2) Quartz publish target = verity-terminal 서브도메인 또는 별도? (3) 메모리 시스템 → 공개 vault export 자동화 룰
- PM 결정 trigger = 사용자 "Obsidian" / "Quartz" / "자기 trail" 발화

---

## Q3 답 (P1) — Brain v5 자기 결정 임계 (N<50) 학술 자문

### 7:3 (fact:sentiment) — Tetlock/Loughran-McDonald 정합

- Tetlock (2007) / Loughran-McDonald (2011) = sentiment 단기 설명력 15~30% 수준
- 한국 KOSPI/KOSDAQ 리테일 ~70% = sentiment 가중치 ↑ 이론 정합. 단 **N<50 미검증 단계 = 7:3 고정이 안전** (overfitting risk)

### 등급 5단계 (75/60/45/25) — Morningstar 5-star 사례 + Kahneman-Tversky 정합

- 학술 표준 = 3단계 (Buy/Hold/Sell) sell-side 다수
- 5단계 = Morningstar 5-star 사례
- **CAUTION 25 비등간격 (10pt gap) = Kahneman-Tversky 손실 회피 이론 정합** ✓

### VCI 비대칭 (+5/-10) — Prospect Theory 정합

- Kahneman-Tversky (1979): 손실 충격 = 이익 약 **2.5배**
- VCI 비대칭 ratio 10/5 = **2.0 → 학술 2.5 근접 정합** ✓
- 한국 리테일 70% 시장 하방 과반응 강함 → 비대칭 설계 적절

### N<50 calibration best practice

| 방법 | 특징 | VERITY 정합 |
|---|---|---|
| Walk-forward | 시계열 OOS | fold 부족 (제한적) |
| Bootstrap | 재표본 신뢰구간 | N=23 최소 활용 |
| **Bayesian prior + posterior** | 사전 지식 보정 | **✅ 가장 권장** |
| Shrinkage estimator | James-Stein | 적용 가능 |

### ⭐ 권고

**현 "이론 고정 + RULE 7 1회 권한" 규율 = Bayesian prior 고정과 동일 논리 = 학술 정합** ✓
- 변경 X. N≥365 또는 IC≥0.05 달성 시까지 임계 동결.
- [[feedback_threshold_calibration_overfit_guard]] / [[project_minimum_n_milestones_2026_05_18]] / [[project_brain_v5_self_attribution]] 정합 입증.

### ✅ VERITY 후속 action

- [[project_brain_v5_self_attribution]] 에 학술 정합 trail 박음 (P0b/c/d-1 외부 자문 reference 추가)
- 코드 변경 X (RULE 7 미적용)

---

## Q4 답 (P1) — Bessembinder 한국 패턴 + 7:3 검증

### Bessembinder (2018) 핵심

- 전체 수익 대부분 = **소수 극단 승자 (fat-tail right skew)**
- 한국 시장 skewness 10.89 = 극단 fat-tail
- 한국 lifetime return 양수 종목 비율 = 미국 (~42%) 보다 낮을 가능성 ↑

### 가중치 권고

- fat-tail 분포 = **fundamental(fact) 가중치 ↑ 정합** (sentiment 단기 노이즈, fat-tail 승자 포착 = fundamental 우월)
- **7:3 = Bessembinder 함의 정합** ✓
- 0.6:0.4 sentiment 상향 = 단기 노이즈 증폭 위험 → 변경 X

### Brain v5 9 factor regime 정합

- Concentrated big-winner 전략 = `moat_quality + canslim_growth + graham_value` 가중치 ↑ 정합
- `commodity_margin + export_trade` = macro regime 필터, fat-tail 승자 선별 보조

### ✅ VERITY 후속 action

- [[project_brain_v5_self_attribution]] 에 Bessembinder 정합 trail 박음
- 가중치 변경 X (RULE 7 미적용)
- [[project_multi_bagger_watch]] 결정 23 검증 보강 §운영 함의 #2 정합 입증

---

## Q5 답 (P2) — commodity_margin wide application 페널티 적절성

### 한국 sector별 commodity 민감도

- **직접 노출** (정유/화학/금속) = commodity 상관 **0.6~0.8**
- **간접** (자동차/항공/의류) = 부분 상관
- **무관** (금융/의료기기/엔터) = **통계 유의 상관 거의 없음**

### 5/26 측정 결과 (JB금융지주)

- commodity_margin primary = CL=F (원유)
- 종목 -15.31% / 원자재 +0.24% → spread_regime "중립"
- 그러나 red_flag 페널티 -5 발동 (이중 페널티)

### ⭐ 진단

**결함 (sector-aware 미적용)** ✓ — JB금융지주 → CL=F 매핑 자체가 부적절.

### 권고

GICS 11 sector 기준 sector-aware white-list:
- **commodity_margin factor 가중치 0 처리 sector**: Financials / Health Care / Communication Services
- **소프트 exception 룰** = `[[feedback_sector_aware_thresholds]]` 패치 정합

### ⏳ VERITY 후속 action (PM 사전등록 의무, RULE 7)

- 메모리 [[project_sector_aware_exemption_2026_05_26]] 신설 박음
- 산식 변경 = RULE 7 PM 1회 권한 사용 의제
- PM 결정 trigger = "Q5 박자" / "sector 면제" 발화

---

## Q6 답 (P2) — SHADOW vs prod gap 진단 학술

### gap 발생 원인 framework

| 원인 | VERITY 해당 여부 |
|---|---|
| Point-in-time bias | 가능성 ↑ (data_snapshot vs live cron) |
| Look-ahead bias | 낮음 (freeze 설계) |
| IC-freeze 효과 | 5/26 일부 관측됨 |
| 시장 변동 | 5/23→5/26 가격 변화 (분리 어려움) |

### Lo (2002) / Bailey-Lopez de Prado (2014) 정합 진단

- **N<50 시점 SHADOW vs prod gap ±1~2 grade = 정상 범위** ✓
- 5/23 SHADOW WATCH 14 → 5/25 prod WATCH 0 → 5/26 prod WATCH 1 = **shrinking 중 = 규율 작동 ✓**

### 1인 운영 sanity check

1. **수기 spot-check** (주 1회, 5종목 무작위) — SHADOW score vs prod score
2. **IC 시계열 rolling 7일 mean** 모니터링
3. **grade 분포 histogram** 주별 비교

### ✅ VERITY 후속 action

- [[project_ic_dead_freeze_2026_05_23]] 에 학술 정합 trail 박음
- 별 sprint 의제 진입 = **불필요** (gap shrinking 중 = 정상)
- 5/27 이후 주 1회 sanity check 3종 routine 박을지 PM 결정 의제

---

## Q7 답 (P2) — Lynch 추가 임계 출처 검증

### 한국 시장 캘리브레이션 결과

| Lynch 분류 | 원전 임계 | 한국 권장 | 근거 |
|---|---|---|---|
| FAST_GROWER 성장 | 20~25% | **≥15%** ✓ | 한국 GDP×3 ≈ 10~11% 상단 마진 |
| FAST_GROWER **시총 ≤ 5조** | 원전 없음 | **자체 설정 명시 필요** ⚠️ | KOSDAQ 중형 기준 |
| STALWART 성장 5~15% | 원전 개략 언급 | 5~15% 유지 ✓ | KOSPI 200 대형주 성장률 |
| ASSET_PLAY PBR ≤ 0.8 | 원전 없음 | **0.8 적정** ✓ | KOSPI 평균 PBR ~0.9~1.1 |
| TURNAROUND 부채 ≤ 300% | 원전 없음 | 300% 유지 + **Altman Z cross-check 권고** | 생존 가능 정의 |

### ✅ VERITY 후속 action (Engineer 자율)

- `api/intelligence/lynch_classifier.py:22-30` 헤더 docstring 보강
- FAST_GROWER 시총 ≤ 5조 = "자체 설정, KOSDAQ 중형 기준" 명시
- TURNAROUND 부채 300% = "Altman Z″ cross-check 권고" 박음
- 값 변경 X (RULE 7 미적용, docstring 만)
- [[project_brain_v5_self_attribution]] P1b 검증 의제 종결

---

## Q8 답 (P2) — 부채 300% Hard Floor + sector_aware 면제 룰

### 한국 금융주 D/E 정상 범위

- 한국 4대 금융지주 D/E = **800~1,400%** 정상
- 은행업 레버리지 구조 전 세계 공통

### 5/26 측정 (JB금융지주)

- 부채 1,084% + 금융주 면제 적용 + FAST_GROWER 분류 = **정합** ✓
- [[project_sector_thresholds_authority_verified_2026_05_13]] 정합 입증

### sector별 면제 룰 권고

| sector | 정상 D/E | 면제 룰 |
|---|---|---|
| **은행/금융지주** | 800~1,400% | Hard Floor 제외 |
| **증권/보험** | 400~900% | ≤600% 완화 |
| **REITs/부동산개발** | 200~500% | 300% → 500% 상향 |
| **항공** | 300~700% | 300% → 500% 상향 |
| **일반 제조업** | ≤200% | 300% 유지 |

### Hard Floor + soft exception 위험

over-exception (면제 남발) 방지 = **GICS 명시 white-list 코드화 권장**.

### ⏳ VERITY 후속 action (PM 사전등록 의무, RULE 7)

- Q5 와 묶음 = [[project_sector_aware_exemption_2026_05_26]] 신설 박음
- 산식 변경 = RULE 7 PM 1회 권한 사용 의제
- PM 결정 trigger = "Q5+Q8 sprint 진입" 발화

---

## Q9 답 (P2) — analyst/dart_fin 회복 path

### source 비교

| Source | 커버리지 | 비용 | 한계 |
|---|---|---|---|
| 네이버 금융 | KOSPI/KOSDAQ 전체 | 무료 | analyst 리포트 구조화 어려움 |
| DART API | 전 상장사 재무 | 무료 (20K/일) | parsing 복잡, corp_code 필요 |
| **pykrx** | KOSPI/KOSDAQ OHLCV + PBR/PER | **무료** | 전일 기준 |
| KRX OpenAPI | 지수/주가 일별 | 무료 | ATR 가능 |
| FnGuide/Wisefn | 기관급 | ₩수백만/월 | budget 초과 |

### ⭐ P0 권고

1. **pykrx 도입** → `quant_volatility` 0/25 복구 (즉시, 무료, `pip install pykrx`)
   - yfinance 한국 종목 커버리지 불안정 교체
   - ATR(14) Wilder EMA 계산 충분
2. **dart_fin 0/25 corp_code 매핑 디버깅**
   - 한도 충분 (25 종목 × 4 재무제표 = 100 call/일 ≪ 20K)
   - 진단 순서: ① corp_code 매핑 → ② API 호출 로그 → ③ parsing 결함

### 월 $25 budget 내 권고

| 우선순위 | 조치 | 비용 |
|---|---|---|
| **P0** | pykrx → quant_volatility 복구 | 무료 |
| **P0** | dart_fin corp_code 디버깅 | 무료 |
| P1 | 네이버 analyst 리포트 title 스크래핑 | 무료 |
| P2 | FnGuide 무료 체험/학생 플랜 탐색 | ~$0 |
| 보류 | Bloomberg/Refinitiv | budget 초과 |

### ✅ VERITY 후속 action (Engineer 자율 P0 박을 수 있음)

- Task #11: pykrx 도입 (의존성 추가 = RULE 4 workflow audit 6축 의무)
- Task #12: dart_fin corp_code 디버깅

---

## 종합 — 후속 action 우선순위 표

| 후속 | Q# | 분류 | 작업 | trigger |
|---|---|---|---|---|
| ✅ 메모리 trail 박음 | Q3/Q4/Q6 | 학술 정합 입증 | [[project_brain_v5_self_attribution]] + [[project_ic_dead_freeze_2026_05_23]] update | 즉시 |
| ✅ Lynch docstring 보강 | Q7 | 출처 명시 | lynch_classifier.py 헤더 4 임계 출처 박음 | 즉시 |
| ✅ pykrx 도입 | Q9 | source 회복 | quant_volatility 0/25 → 복구 | 즉시 |
| ✅ dart_fin 디버깅 | Q9 | source 회복 | corp_code 매핑 검증 | 즉시 |
| ⏳ Q5+Q8 GICS codification | Q5/Q8 | RULE 7 PM 사전등록 | [[project_sector_aware_exemption_2026_05_26]] 신설, PM 결정 대기 | PM 발화 |
| 📋 자기 trail 강화 O path | Q2 | 별 sprint | Obsidian+Quartz 진입, vault 분리 룰 | PM 발화 |
| 📋 Q1 Option a (Conviction 2p) | Q1 | Phase 2 큐 | Option b 이미 박힘, a 는 미래 | Phase 2 |

**학술 정합 입증 사항** (변경 X):
- 7:3 가중치 / 5단계 등급 / VCI 비대칭 = **현 규율 학술 정합 ✓**
- Bessembinder 한국 패턴 → fact 가중치 ↑ 정합 ✓
- SHADOW vs prod gap shrinking = 규율 작동 ✓
- 금융주 부채 1084% + 면제 = 정합 ✓
