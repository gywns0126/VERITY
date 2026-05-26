# Perplexity 질문 batch — 2026-05-26

> **출처**: 5/26 리포트 빈약 audit sprint + IC-freeze SHADOW verify 종결 후 PM 측 외부 자문 의제 정리. 사용자 발화 "다른 의제는 필요하면 퍼플렉시티 질문 준비" + "있으면 다 정리해와. 내가 답 받아오게" trigger.
> **목적**: (1) 사용자 명시 발화 trigger 의제 (외부 양식 / PKM 통합) 외부 자문 + (2) Brain v5 자기 결정 임계 (N<50 시점) 학술 정합 검증 + (3) sprint 큐 잔존 의제 외부 자문.
> **활용 패턴**: `feedback_perplexity_collaboration` 정합 — 시스템/코드=Claude, 외부 사실/통계/법규=Perplexity, 애매 시 사용자 핸드오프. 답변 받은 후 `docs/PERPLEXITY_ANSWERS_20260526.md` 에 박음.
> **예상 비용**: Perplexity Sonar Pro 학술 reference 깊은 답 ~$0.05~0.15/query × 9 = **~$0.5~1.5 batch**. 사용자 부담 우선 P0 (Q1+Q2) 만 박아도 의제 진입 가능.

---

## 우선순위 표 (사용자 batch 박을 때 선별 참고)

| Priority | Q# | 의제 | trigger |
|---|---|---|---|
| **P0** | Q1 | 외부 증권사 리포트 양식 표준 | 사용자 5/26 발화 직접 |
| **P0** | Q2 | PKM 자기 자산 통합 best practice (Obsidian + Quartz) | 자기 trail 강화 sprint R 종결 trigger 충족 |
| **P1** | Q3 | Brain v5 자기 결정 임계 (N<50) 학술 자문 | 5/25 P1 진단 / 365일 trail 도달 전 자문 trail 누적 |
| **P1** | Q4 | Bessembinder 한국 패턴 + 7:3 가중치 검증 | [[project_brain_v5_self_attribution]] 검증 의제 큐잉 |
| **P2** | Q5 | commodity_margin wide application 페널티 적절성 | P1 후속 ① 5/25 큐 |
| **P2** | Q6 | SHADOW vs prod gap 진단 학술 | P1 후속 ② 5/25 큐, 5/26 측정 결과 보강 |
| **P2** | Q7 | Lynch 추가 임계 출처 (FAST_GROWER 외) | [[project_brain_v5_self_attribution]] P1b 검증 의제 |
| **P2** | Q8 | 부채 300% Hard Floor + sector_aware 면제 룰 정합성 | [[project_brain_v5_self_attribution]] P1c 회귀 위험 의제 |
| **P2** | Q9 | analyst/dart_fin 회복 path (네이버 커버리지 한계) | 5/26 리포트 빈약 audit 1축 (데이터 결손) 후속 |

---

## Q1. 외부 증권사 리포트 양식 표준 (P0, 사용자 직접 발화)

**Context**:
- VERITY 가 자동 생성하는 리포트 8종 (daily/weekly/monthly/quarterly/semi/annual × admin/public) 의 양식이 "빈약" 진단 (사용자 5/25 발화 "실패 이건"). 5/26 sprint 에서 자기 trail 노출 강화 commit `2d63b2e2` 박았으나 외부 표준과 정합성 미검증.
- VERITY 현 양식 = COVER 30초 브리핑 + 매크로 + 이벤트 캘린더 + Brain 종합 판단 + 종목 판단 (BUY/보유/회피) + 섹터 동향 + VAMS 현황 + AI 이견 검토 (총 7장 chapter).
- VERITY 1인 운영, 미검증 N<50 단계, 자기 trail 강화 (Brain v5 가중치 7:3 / 5단계 등급 임계 / VCI / Lynch 6분류 / VAMS / KIS 1일 1토큰 / IC-DEAD freeze / Phase 0 누적 23일 / macro_mult 0.85) 노출 박힘.

**질문**:
> 1. 한국 증권사 (KB증권 / 미래에셋증권 / 한국투자증권 / 삼성증권 / NH투자증권 / 신한투자증권) 의 daily 시황 + weekly 시황 + monthly 시황 + quarterly outlook 리포트 *양식 표준* 비교. 목차 구성 / chart vs table vs prose 비중 (%) / 면책 위치 / 자기 산식·모델 노출 정책 (방어형 vs 적극형) 정밀 비교.
> 2. 미국 sell-side firm (Goldman Sachs / Morgan Stanley / JPMorgan / BofA / Citi) 의 institutional research brief *양식 표준* — initiating coverage / earnings preview / sector update / strategy note 각각의 chapter 구조 + 모델 디스클로저 정책.
> 3. VERITY 같은 1인 운영 미검증 N<50 단계의 양식 권장 = 어느 firm style mimicry 가 정합? (자기 산식 노출 강화 + Brain v5 trail 박음 + 가설 표기 의무 — CLAUDE.md RULE 7 정합)
> 4. 자기 모델 / 산식 / 임계 노출 강화 시 *위험* (모델 게이밍 / IP 노출 / 신뢰도 손상) vs *이득* (차별점 강조 / LLM 무료 tier 와 차별화 / 학습 trail 축적) 학술/실무 균형 권고.

**RULE 7 사전 등록 의무 정보** (답변에 박혀야 할 것):
- 각 firm 양식 source (실 PDF / 공식 publication)
- chapter 비중 정량 (page 비례)
- N (몇 개 리포트 sample 분석)
- 한국 vs 미국 firm 차이 정합
- 1인 운영 미검증 단계 권고 양식 (단일 답 X, 옵션 a/b/c 비교)

---

## Q2. PKM 자기 자산 통합 best practice (Obsidian + Quartz) (P0, R 종결 trigger 충족)

**Context**:
- [[project_brain_self_trail_strengthening_2026_05_25]] PM 명시 5/25, 자기 trail 강화 sprint = (V) 메모리 graph 시각화 / (B) Brain v6 design / **(O) PKM 외부 도구 자기 보존 통합** 3 path 중 **(O) 선택 박힘**.
- VERITY 자기 자산 (Brain v5 가중치 7:3 / 등급 임계 75-60-45-25 / VCI / Lynch / VAMS / KIS 1일 1토큰 / IC-DEAD freeze / Phase 0 누적 N / 산식 commit trail) 을 PKM (Obsidian + Quartz embed publish) 으로 통합 노출 의도.
- 사용자 5/26 데모 확인 후 vault content 결정 대기. CLAUDE.md RULE 6 정합 (LLM 못 가지는 자기 차별점 = 자기 운영 trail / 자기 산식 / 자기 universe).

**질문**:
> 1. Obsidian + Quartz embed publish 조합으로 *trading system / quant operator 자기 자산* 통합 노출 사례 — 학술 / 실무 / GitHub 공개 vault 사례 (e.g. Andy Matuschak / Maggie Appleton / Quantitative finance researchers). 백링크 + dataview + graph view 활용 패턴.
> 2. *공개 vault* (Quartz publish, PM 사이트 노출) vs *비공개 vault* (PM 본인 의사결정 지원, Brain 학습 input) 분리 룰. 자기 산식 / 임계 / 운영 trail 어디까지 공개 vs 비공개 권장? (Q1 #4 모델 게이밍 risk 와 정합)
> 3. **VERITY-style "1인 헤지펀드 미만 + 콘텐츠 기관급" 포지셔닝 ([[project_positioning_top_retail]])** 에서 PKM 노출 강도 권장 — Phase 1 (개미 중 최강) vs Phase 2 (1인 운용 사실상 기관급) 단계별.
> 4. Obsidian → Quartz publish pipeline 의 *update 자동화* (cron / GitHub Actions / Vercel deploy hook) best practice. VERITY 의 메모리 시스템 (`~/.claude/projects/.../memory/*.md`) 과의 통합 path — 직접 mirror vs 별 vault vs 양방향 sync.

**RULE 7 사전 등록 의무 정보**:
- 사례 vault URL (실 공개 vault, 최소 3개)
- 학술 reference (PKM + finance/quant 도메인)
- 노출 강도 분류 (1-5 scale) vs operator 단계 매핑
- 한국 / 영어 vault 사용자 차이 정합
- 비용 (Quartz hosting / Obsidian sync / 도메인) 예상

---

## Q3. Brain v5 자기 결정 임계 (N<50) 학술 자문 (P1)

**Context**:
- [[project_brain_v5_self_attribution]] 정리 — Brain v5 의 자체 결정 임계·가중치 P0b/c/d-1/d-2/e/f + P1a/b/c. SOURCE_AUDIT_20260502 결과 = 학계/펀드 직접 인용 X (영감 출처만, 비율·임계는 자체).
- 운영 N = Phase 0 누적 14일 (5/2~5/16) + VAMS reset 5/17 후 9일 = total ~23일. **N<50 산식 자유 tweak 금지 규율** ([[feedback_threshold_calibration_overfit_guard]]) 박힘. 365일 trail 도달 ~2027-05.
- 자체 결정 임계 list:
  - P0b: fact 0.70 / sentiment 0.30 가중치 (7:3)
  - P0c: 등급 75 / 60 / 45 / 25 (5단계 등간격 15점, CAUTION만 25)
  - P0d-1: VCI 임계 25 / 15 / -15 / -25 + 비대칭 보너스 +5 / -10
  - P0e: red_flag 이중 페널티 (점수 -5 × downgrade_count + grade 1~2단계 강등)
  - P0f: quadrant_unfavored (점수 -5 + grade -1단계)

**질문**:
> 1. fact 0.70 / sentiment 0.30 비율 (7:3) — 한국 시장 / global 시장 *학술 표준 사례*. fundamental + sentiment 결합 모델 (예: Tetlock 2007 / Loughran-McDonald 2011 / Heston-Sinha 2017) 의 비율 분포. 한국 KOSPI/KOSDAQ 특유 retail 비중 (~70%) 정합 가중치 권고.
> 2. 등급 임계 5단계 등간격 (75/60/45/25/0) — 학술 best practice (3단계 vs 4단계 vs 5단계). VERITY 의 CAUTION 25 (10점 gap) 만 비등간격 = 보수성 강화 의도 (Perplexity MED-A 권고, commit `ba7e5a2b`). 적정성 검증.
> 3. VCI 비대칭 보너스 +5 / -10 (positive 약함 vs negative 강함) — Cohen 역발상 영감, 임계는 자체. *손실 회피 학술* (Kahneman-Tversky prospect theory) + 비대칭 design 학술 근거. 한국 시장 retail behavior 정합.
> 4. red_flag 이중 페널티 (점수 -5 + grade -1단계 동시 적용) — 5/25 진단 결과 25/25 종목 100% downgrade_count ≥ 1 발동 = 이중 페널티 universal application. 이중 페널티 design 학술 사례 (Bayesian downweight vs hard floor vs cascade).
> 5. **N<50 시점 calibration 학술 best practice** — walk-forward / bootstrap / Bayesian prior + posterior update / shrinkage estimator. VERITY 의 "이론 고정 + RULE 7 1회 권한" 규율 정합 권고.

**RULE 7 사전 등록 의무 정보**:
- 학술 reference (논문 / book / pension fund whitepaper)
- N (사례 sample size)
- 한국 / 미국 / 유럽 시장 차이 정합
- VERITY 1인 운영 + N<50 단계 권장 임계 (변경 권고 X / 변경 권고 시 1회 권한)
- 변경 시 trigger (운영 N≥365 vs IC≥0.05 vs ICIR≥0.3)

---

## Q4. Bessembinder 한국 패턴 + 7:3 가중치 검증 (P1)

**Context**:
- [[project_brain_v5_self_attribution]] P0b 검증 의제 큐잉 박힘. Bessembinder (2018) "Do Stocks Outperform Treasury Bills?" + 한국 시장 skewness 10.89 = fat-tail 보상 구조.
- 한국 = lifetime stock return 1.5% 만 양 (positive skew 극단). VERITY 의 fact 0.7 (fundamental) / sentiment 0.3 비율이 fat-tail 보상 구조 적합한지 학술 검증 필요.
- [[project_multi_bagger_watch]] 결정 23 검증 보강 §운영 함의 #2 정합.

**질문**:
> 1. Bessembinder 한국 패턴 (skewness 10.89, lifetime return 1.5% 종목만 양) 의 *운영 함의* — 가중치 / 종목 선별 / 포지션 사이징 권고. Concentrated big-winner 전략 vs 분산 전략.
> 2. fact 0.7 (fundamental) / sentiment 0.3 가중치 — fat-tail skewed 분포에서 적합성. 다른 비율 (0.6:0.4 / 0.8:0.2 / 0.85:0.15) 비교 학술 (OOS hit_rate / avg_return / Sortino).
> 3. 한국 시장 *Bessembinder-Asness* 결합 권고 — momentum + value + quality 비중. VERITY 의 Brain v5 9 factor (multi_factor / consensus / prediction / timing / commodity_margin / export_trade / moat_quality / graham_value / canslim_growth) regime 정합.

**RULE 7 사전 등록 의무 정보**:
- Bessembinder 2018 + 한국 후속 연구 (있을 경우)
- N (Korea Stock Exchange 1985~2026 trail)
- 가중치 비교 OOS 결과 (IC / IR / hit rate)
- 한국 / 미국 패턴 차이
- VERITY 의 [[feedback_seed_size_conservatism]] 정합 권고

---

## Q5. commodity_margin wide application 페널티 적절성 (P2)

**Context**:
- 5/25 P1 후속 ① 큐 — NG=F / LIT / CL=F 등 원자재 급변 시 의료기기 / 엔터 / 금융주 → -5 페널티 + grade 강등 wide application 사례 관찰.
- 진단 의제 = 의도된 가드 vs 결함 (sector 무관 페널티) 판정.
- 5/26 측정 결과 = JB금융지주 (175330) Lynch=Fast Grower, commodity_margin primary=CL=F (상관 None), 종목 -15.31% / 원자재 +0.24% → spread_regime="중립", but red_flag 페널티 -5 발동.

**질문**:
> 1. 한국 시장 sector 별 원자재 민감도 학술 — *직접 노출* (정유 / 석탄 / 금속) vs *간접 노출* (자동차 / 항공 / 의류). 의료기기 / 엔터 / 금융주 의 원자재 민감도 학술 근거.
> 2. commodity 급변 → 비관련 sector 페널티 적용 = *over-correction* 학술 사례. KOSPI / KOSDAQ regime별 (bull / bear / sideway) 원자재 영향 비대칭.
> 3. VERITY 의 commodity_margin primary 자동 선택 (Financial Services → CL=F) 의 적절성. sector-aware mapping ([[feedback_sector_aware_thresholds]] 정합) 의무 권고.

**RULE 7 사전 등록 의무 정보**:
- 학술 reference (sector-commodity sensitivity papers)
- 한국 sector 분류 (GICS 11 / WICS) 별 commodity exposure 표
- 의료기기 / 엔터 / 금융주 commodity 민감도 정량
- VERITY 의 commodity_margin 룰 권고 변경 path

---

## Q6. SHADOW vs prod gap 진단 학술 (P2)

**Context**:
- 5/23 SHADOW = BUY 1 / WATCH 14 (214150@60 BUY 예측), 5/25 prod = BUY 0 / WATCH 0, 5/26 prod = BUY 0 / WATCH 1 (214150 WATCH 진입).
- gap 좁아졌으나 잔존. SHADOW (predict, paper) vs prod (live, real data) 측정 path 차이 진단 필요.
- IC-freeze SHADOW 측정 결과 = brain max +6 / WATCH +1 → 자동 drift 제거 효과 일부 관측, 시장 변동 + IC-freeze 둘 다 영향 분리 어려움.

**질문**:
> 1. *동일 universe / 동일 산식인데 SHADOW (predict, freeze 후 dry-run) vs prod (live, fresh data) grade 분포 gap* 발생 원인 학술 framework. Out-of-sample vs in-sample / point-in-time bias / look-ahead bias / data snooping bias 진단 분류.
> 2. factor IC live vs backtest mismatch 진단 학술 (Lo 2002 / Bailey-Lopez de Prado 2014 / Harvey-Liu 2014). 1인 운영 N<50 시점 권장 진단 framework.
> 3. VERITY 의 5/23 SHADOW (PR #52 / IC-freeze 사전등록 기준) vs 5/26 prod (실제 머지 후 cron) gap = 정상 / 결함 판정 기준. gap 좁아지는 속도 normal 분포.

**RULE 7 사전 등록 의무 정보**:
- 학술 reference (SHADOW vs live mismatch papers)
- 진단 framework step-by-step
- 1인 운영 권장 sanity check (cost-effective)
- VERITY 의 측정 path (SHADOW = data_snapshot 기반, prod = live cron) 정합 검증

---

## Q7. Lynch 추가 임계 출처 (FAST_GROWER 외) (P2)

**Context**:
- [[project_brain_v5_self_attribution]] P1b — FAST_GROWER 15% 임계 = 헤더 docstring 출처 박힘 (Lynch 원전 20~25% / 한국 GDP × 3 ≈ 10~11% 캘리브). 정합.
- 다른 임계 출처 미박힘:
  - FAST_GROWER 시총 ≤ 5조 — 출처 X
  - STALWART 매출 5~15% / 시총 ≥ 1조 — 출처 X
  - ASSET_PLAY PBR ≤ 0.8 — "한국 저PBR 구조 반영" 만
  - TURNAROUND 부채 ≤ 300% — "생존 가능" 만

**질문**:
> 1. Lynch *One Up on Wall Street* 6분류 임계의 한국 시장 캘리브레이션 학술 사례. 시총 / PBR / 부채비율 한국 특유 분포 baseline.
> 2. STALWART 매출 5~15% / 시총 ≥ 1조 — 한국 시장 적정성 (KOSPI 200 + KOSDAQ 150 universe 정합).
> 3. ASSET_PLAY PBR ≤ 0.8 — 한국 저PBR 구조 (KOSPI 평균 PBR ~ 0.9~1.1) 정합. 더 보수적 임계 (PBR ≤ 0.6) vs 현 0.8 비교.
> 4. TURNAROUND 부채 300% — *생존 가능* 정의 학술. Altman Z-Score / Beneish M-Score 와의 cross-check 권고.

**RULE 7 사전 등록 의무 정보**:
- Lynch 원전 + 한국 후속 연구
- 시총 / PBR / 부채 한국 특유 분포 정량 (sample size)
- 임계 변경 권고 (변경 X / 권고 시 정량)

---

## Q8. 부채 300% Hard Floor + sector_aware 면제 룰 정합성 (P2)

**Context**:
- [[project_brain_v5_self_attribution]] P1c **🔴 회귀 위험** — 부채 300% Hard Floor (verity_brain.py:1631-1667) + sector_aware 면제 룰 (한국은행 + 4대 금융지주 1176% 정합, [[project_sector_thresholds_authority_verified_2026_05_13]]).
- 5/26 측정 결과 = JB금융지주 (175330) 부채비율 1084.16% but 금융주 면제 적용 (red_flag 미발동, Lynch=Fast Grower 분류). 그러나 [[project_sprint_11_veteran_response]] 베테랑 진단 시 sector_aware 패치 무력화 위험 보고.

**질문**:
> 1. 한국 금융주 (은행 / 증권 / 보험) D/E 정상 범위 학술 - 한국은행 + 4대 금융지주 1176% 정합성. global 금융주 D/E 비교 (미국 / 유럽 / 일본).
> 2. 부채 300% Hard Floor + 금융주 면제 룰 정합성 학술 - hard floor + soft exception design 의 위험 (over-exception vs under-exception).
> 3. VERITY 의 1.084% 부채 비율 + FAST_GROWER 분류 + red_flag 미발동 = 정합 / 결함 판정. JB금융지주 같은 한국 금융 지주사 universe 권장 처리.
> 4. 금융주 외 sector (REITs / 부동산개발 / 항공) 의 high D/E 정상 범위 + 면제 룰 권고.

**RULE 7 사전 등록 의무 정보**:
- 학술 reference (sector-specific debt ratio papers)
- 한국 금융주 / REITs / 항공 D/E 정상 범위 정량
- Hard Floor + exception design 학술 사례
- VERITY 의 sector_aware 룰 변경 권고

---

## Q9. analyst/dart_fin 회복 path (네이버 커버리지 한계) (P2)

**Context**:
- 5/26 portfolio.json 25 종목 적재율 = **analyst_report 0/25 + dart_fin 0/25 + quant_volatility 0/25**. 외부 보조 source 빈약.
- 메모리 5/20 결정 = "네이버 커버리지 한계, 튜닝 불가" (analyst_report). 그러나 데이터 결손 = 리포트 빈약 1축 (5/26 audit). 외부 source 회복 path 검토 필요.
- VERITY budget = Claude $20/월 + Perplexity ~$2.4/월 (US15 brief) + DART 20K/일 무료 + KIS 무료 (1일 1토큰).

**질문**:
> 1. 한국 25 종목 universe analyst_report 커버리지 한계 source 비교 - 네이버 finance (현 source) vs FnGuide (paid) vs Wisefn (paid) vs DataGuide (paid) vs Bloomberg (paid) vs Refinitiv (paid). 각 source coverage % + 한국 KOSPI 200 / KOSDAQ 150 사용량.
> 2. dart_financials 결손 root cause - DART API spec (20K/일, corp_code 월1회, [[project_dart_api_2026_constraints]]) 한계 내 25 종목 매일 fetch 가능한가? 결손 0/25 = 호출 부재 / 호출 실패 / parsing 결함 진단 framework.
> 3. quant_volatility (0/25) - yfinance 한국 종목 OHLCV 데이터 한계 vs pykrx vs KRX OpenAPI. ATR (14) Wilder EMA 계산 source 권고.
> 4. VERITY 1인 운영 monthly budget ~$25 내 회복 가능 path - 무료 source 회복 우선 vs paid source 부분 도입 (cost-benefit).

**RULE 7 사전 등록 의무 정보**:
- 각 paid source 한국 25 종목 커버리지 % 정량
- 무료 source 회복 path (네이버 / DART / pykrx / KRX OpenAPI / FRED) 한계
- 비용 비교 표 ($/월, 25 종목 가정)
- VERITY 권고 path (현 source 유지 / paid 도입 우선순위)

---

## 답변 형식 (사용자가 Perplexity 결과 박을 때)

각 Q 답변 = 별 file `docs/PERPLEXITY_ANSWERS_20260526.md` 박음. 구조:

```markdown
## Q{N} 답변

**source**: Perplexity Sonar Pro / GPT-5 / Claude Opus / 기타
**cost**: $X.XX
**date**: 2026-MM-DD

### 핵심 답 (3-5 bullet)
- ...

### 학술 reference
- ...

### RULE 7 사전 등록 입력 (코드 변경 시)
- ...

### VERITY 권고 (변경 / 유지 / 추가 자문 필요)
- ...
```

답변 받은 후 다음 세션 catch 키워드 = "Q{N} 답 박았어" → VERITY 측 변경 / 메모리 update / 코드 commit trail.
