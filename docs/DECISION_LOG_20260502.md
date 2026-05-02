# 결정 일지 — 2026-05-02

오늘 메인 의사결정 + 근거 + 검증 시점 + 검증 결과. bootstrap founder 의 검증 단계 baseline 확정 작업.

---

## [D1] Stage 3 매도 룰 재설계 (보류 — 사용자 결정 영역)

**결정**: 보류. Lynch 1/3 룰 출처 무효 발견 → 대체안 4건 제시 (자체 백테스트 / R-multiple trailing 연장 / percentile-based reduce / Stage 3 룰 보류).
**근거**: Lynch *One Up* (1989) / *Beating the Street* (1993) 원전에 1/3 정량 룰 명시 X. "+10~15%p 알파" 백테스트 출처 부재 (Claude × Perplexity 일치).
**검증 시점**: 사용자 본인 결정 후 (2027 Q1 Bagger Stage Manager 진입 전)
**검증 결과**: 보류 — 본인 결정 대기. 메모리 `project_multi_bagger_watch` 결정 23 Stage 3 줄 = "출처 미검증 — 본인 결정 영역" 라벨링 완료

---

## [D2] ATR 파라미터 출처 정정 + 4-cell 백테스트 의제

**결정**:
1. ATR(14)×2.5 운영값 유지 (Phase 0 마이그레이션 baseline 보호)
2. 출처 표현 "월가 표준" → "단기/한국 자체 채택 변형" + LeBeau 원전 ATR(22)×3.0 명시
3. 5/17 verdict=ok 후 4-cell 비교 백테스트 의제 큐잉 (P0 격상)

**근거**: LeBeau Chandelier Exit 원전 (Computer Analysis of Futures Market) = ATR(22)×3.0. 본 시스템 (14)×2.5 = 변형. Phase 0 (5/3~5/16) Wilder EMA 마이그레이션 검증 baseline 흔들지 않기 위해 즉시 변경 X.

**검증 시점**:
- 1차: 메모리 정정 (즉시) — ✅ 완료
- 2차: 5/17 Phase 0 verdict 후 4-cell 백테스트 — 대기

**검증 결과**:
- ✅ D2-1 출처 표현 정정 완료 (project_atr_dynamic_stop)
- ✅ **D2-2 풀스캔 v2 정량 보강** (Phase 1.3 v2 2차 정정 — large stop_loss 75.6% 🔴 = ATR×2.5 한국 시장 부적합 강한 신호)
- 대기: 4-cell 백테스트 (의제 57ac6bd0, due 2026-05-17)

---

## [D3] ESTATE 백테스트 평가 임계 보강 (silent 측정 → 5/12/26 결정)

**결정**: Mean IC > 0.03 단독 임계 폐기 → 5 메트릭 다중 평가 (Spearman IC / RMSE / Direction / Quintile + Sharpe P1 보류). silent 측정 인프라 사전 구축 → 5/26 정식 verdict 후 운영 전환.

**근거**: n=25 (서울 25구) 신뢰구간 ±0.20 = IC 0.03 vs 0.10 구분 불가. 단독 임계 = 동전 던지기보다 약간 낫지만 의사결정 신뢰 부족. 다중 메트릭 = 거짓 양성 30% → 8% (4배 감소).

**검증 시점**:
- silent 측정 인프라: 즉시 (2026-05-02) — ✅ 완료
- 5/5 첫 cron sanity (jsonl row 1 확인): 의제 7f2b51b5
- 5/12 mid-checkpoint: 의제 ea3d607b
- 5/26 정식 verdict: 의제 41926867

**검증 결과**:
- ✅ `docs/ESTATE_VALIDATION_METRICS.md` (5 메트릭 정의 + n=25 한계)
- ✅ `scripts/landex_meta_validation.py` silent 측정 추가 (운영 verdict 미터치)
- ✅ `docs/LANDEX_VALIDATION_RUNBOOK_5_12.md` (일정 정정 5/12 mid + 5/26 정식 / §3 인터페이스 계약)
- ✅ 단위 테스트 5/5 + mock dry-run 통과
- 대기: 5/5 / 5/12 / 5/26 cron 결과

---

## [D4] 신호 1·2 출처 단일화 (Mauboussin)

**결정**:
- 신호 1 (분기 매출 가속): CANSLIM C 폐기 → **Mauboussin & Rappaport, *Expectations Investing* (2001)** 단일
- 신호 2 (operating leverage): Buffett 1995 + Zweig 둘 다 폐기 → **Mauboussin, *More Than You Know* (firm-level)** 단일

**근거**:
- CANSLIM C 원전 = EPS 25%+ YoY 가속 (이익) — 매출 가속과 정의 다름
- Buffett 1995 letter = GEICO 인수 / Capital Cities 매각 / float — operating leverage 결정 단락 부재
- Zweig = macro level operating leverage — firm-level 신호와 부적합

**검증 시점**: 즉시 (메모리 정정 완료)
**검증 결과**: ✅ 5/2 정정 완료 (project_multi_bagger_watch line 19, 20)

---

## [D5] 결정 23 + Bessembinder 자체 검증 (5R 풀스캔 v2)

**결정**:
1. Perplexity 인용 (한국 30년 텐버거 114개) 보류 → 자체 풀스캔 검증
2. analyze_5r_sample_feasibility.py 에 D5 메트릭 추가 (decision_23_verification + bessembinder_check)
3. 풀스캔 v2 (hard_floor + R-cap=50) 로 자체 baseline 확립

**근거**:
- 외부 LLM 출처 검증 불가 (Bessembinder 2018 = 미국 분포)
- Lynch 1/3 / 결정 23 / CANSLIM C / Buffett 1995 모두 Perplexity 인용 무효 — *자체 백테스트 우선* 원칙 (`feedback_real_call_over_llm_consensus` 와 정합)

**검증 시점**: 풀스캔 v2 (당일 ~17:00 KST)

**검증 결과**:
- ✅ **결정 23 텐버거 = consistent** (가정 114 / 실측 128 / Δ +12.3%)
  - 단 Caveat: 연평균 normalize 시 30년 가정 (3.8/년) vs 10년 실측 (12.8/년) = 3.4배 차이. 황금기 편향 가능
- ✅ **Bessembinder 한국 패턴 일치** (median -4.36% / skewness 10.89 / top 4% wealth share 51.35%)
  - 한국 특이성: 미국 100% 대비 분산형 — Concentrated big-winner 전략 (결정 10 high conviction 10) 재검토 의제 (8d762b0a)

---

## [Audit] 시스템 출처 무결성 baseline (Step 1 P0 + Step 2 정정 + Step 3 P1)

**결정**: D2/D4 외 silent drift 잔여 발굴. P0 (4영역) → P1 (3영역) 풀 audit + 메타 원칙 정립.

**근거**: 단발 정정 (D2/D4) 만으로 silent drift 누적 차단 부족. 시스템 전반에 *자체 결정인데 명시 X* 영역 다수 의심 (Brain v5 가중치 / 등급 임계 / VAMS 프로필 / Macro override).

**검증 시점**: 즉시 (당일)

**검증 결과**:
- ✅ Step 1 P0 audit 완료 (P0a/b/c/d 4영역, 14 항목)
- ✅ 풀스캔 v2 결과 자동 보강 (Phase 1.1 verdict 🔴)
- ✅ Step 2 메모리 정정 6건 + 의제 8건 등록
- ✅ Step 3 P1 audit 완료 (VAMS / Lynch 추가 / Macro override, 9 항목)
- ✅ Step 3 메모리 정정 보강 + 의제 5건 추가

**P0 + P1 통합 verdict 카운트** (총 23 신규 audit + 6 Skip 확인):

| Verdict | 카운트 |
|---|---|
| ✅ Skip / 통과 | 6 + 2 = **8** |
| 🟢 보너스 검증 | **2** (결정 23 / Bessembinder) |
| ⚠️ 의제 큐잉 | **3** |
| 🔴 정정 + 의제 | **3** (신호 3 / Phase 1.1 / 부채 300% Hard Floor 회귀 위험) |
| ❓ 라벨링 | **9** |

**총 의제 큐잉**: 13건 (Step 2 8건 + Step 3 5건). action_queue 총 **24건**

---

## [D-자본] 자본 규모별 시스템 진화 path 컨셉 채택

**결정**: VERITY = 자본 규모 함수형 진화 시스템 정체성 확정. 6 tier (1천만~100억+) × 7축 (종목수/universe/시총/보유기간/데이터/검증/거버넌스) + 3종 trigger (자본임계 primary / 시장임팩트 secondary / 활용도 cap tertiary)

**근거**:
- 시장에 비슷한 사례 없음 (3 구조적 이유): (1) 시장 인센티브 misalign — 단일 product 화 X / (2) Target 시장 power law — 100억+ PM 0.1% 미만 / (3) 자본 진화 = PM 진화 동시 발생 — 외부 시스템화 어색
- 부분 매칭 사례 4건 (Bridgewater Pure Alpha / Wealthfront / 한국 PB / Robo-advisor 일반) 모두 *교집합 영역* 만 채움
- 모든 기술 결정 (Brain Score / Phase 1.3 / VAMS / e8a17b3c / fa3c2d1e) 의 *메타 맥락* = "현재 tier 적합한가? 다른 tier 진화 시 회귀 위험?"

**검증 시점**:
- 자본 1억 도달 시 첫 evolution sprint (Tier 1 → 2 transition checklist 발동)
- 매주 cron capital_tier monitor (Round 3 명세 진입 후)
- 분기별 review 시 tier 정합성 점검

**검증 결과**: 대기 중 — 5/2 baseline = Tier 1 (자본 1,000만 가정). holdings 활용도 28.6% (under-utilized). 자본 1억 도달 시까지 trigger 발현 0건 정상

**영향 범위**: 시스템 비전 자체 (메타 원칙) — 모든 기술 결정의 자문 기준

**Cross-ref**:
- 신규 메모리 `project_capital_evolution_path` (시스템 메모리)
- T1-23 Phase 1.1 ATR×2.5: Tier 1 한국 시장 부적합 가능 → 정정 sprint (silent error 4건과 통합)
- T1-25 Phase 2-A 5,000 universe: Tier 2 진입 인프라 (Tier 1 Day 0 비활성 정합)
- e8a17b3c sector 수집: Tier 1~6 모두 필수 (silent error 2건)

---

## [D-Sector] sector propagation silent error 4건 발견 + 5/17 후 정정 sprint

**결정**: 5/17 Phase 0 verdict 통과 후 silent error 4건 정정 sprint 진입 (단일 변수 통제, 결정 21 정합). 진입 순서: 4-cell 백테스트 (57ac6bd0) → e8a17b3c (root cause) → fa3c2d1e (Hard Floor sector 분기) → b9d4f72a (VAMS 분산 한도 검증)

**근거**:
- 운영 영향 부분적 (확정 발현 1건 KB금융 AVOID + 잠재 ~40 금융주) + Phase 0 baseline 보호 의무 (5/3~5/16 A/B 비교)
- silent error 4건 의존성 그래프 (`docs/SILENT_ERRORS_20260502.md`):
  - Error 2 (sector NULL) → Error 3 (VAMS 분산 무효) + Error 4 (Hard Floor silent)
  - Error 1 (ATR×2.5) + Error 3 → 분산 안 된 portfolio + tight stop = 변동성 폭증 누적
  - Error 4 → KB금융 AVOID 부분 발현 (5/2 22:30 진단 확정)
- 정정 sprint 우선순위 매트릭스 (1~4) 확정

**검증 시점**:
- e8a17b3c 정정 후 D+1: recs sector 51/51 → 100% non-null 목표
- fa3c2d1e 정정 후 D+1: KB금융 AVOID 해제 + 금융주 추천 0 → 5~10건 예상
- b9d4f72a 측정: holdings sector "Unknown" 100% → 다양화 검증
- 4-cell 백테스트: large stop_loss < 60% 인 cell 존재 검증

**검증 결과**: 대기 중 — 5/17 후 sprint 진입 의제 4건 (57ac6bd0 / e8a17b3c / fa3c2d1e / b9d4f72a) action_queue 등록 완료

**영향 범위**: VAMS / Brain / 추천 분류 / Hard Floor / sector 분산 한도 / multi_factor consumer 7곳

**Cross-ref**:
- `docs/SILENT_ERRORS_20260502.md` (4 silent error + 의존성 + 시나리오)
- `docs/OPS_VERIFICATION_20260502.md` (3차 진단 + root cause)
- `docs/REGRESSION_RISK_AUDIT_20260502.md` (의제 ac9d1dc1 검증 결과 🔴)
- 의제 e8a17b3c / fa3c2d1e / b9d4f72a / 57ac6bd0 / d7dea48c / 0f6dce6a
- 메모리 `feedback_source_attribution_discipline` (학습 사례 5번째)

---

## [D-Holdings] Holdings under-utilization 28.6% (2/7 moderate) baseline + total_value=0 silent error

**결정**: 5/2 시점 holdings 활용도 28.6% (2/7 moderate 프로필 기준) baseline 기록 — 시스템 활용도 측정 baseline 확보. `data/analysis/holdings_utilization_baseline.jsonl` 신규 (1줄, 5/2 baseline). **별도 신규 silent error finding**: vams.total_value=0 + holdings avg_price=0 → 의제 c5e8f9a2 등록

**근거**:
- Round 1 작업 2 진단 + Round 2 follow-up VAMS 프로필 진단 (5/2 23:55) — active profile = **moderate** (config default + portfolio.json `active_profile=moderate` 일치, env 미설정)
- moderate max_picks=7 기준 utilization 28.6% (2/7) — *active=safe 가정 시 2/3=66.7% 정상 범위 즉시 진입*
- Tier 1 정상 활용도 50~80% 대비 *under-utilized* — 자본 cap 미달 (Tier 1 자본 흡수 초기 정상)
- 시스템 활용도 = 자본 진화 trigger 의 *보조 신호* (Trigger 3 — tertiary): 90%+ 지속 4주 시 tier 전환 신호
- **신규 silent error**: `vams.total_value=0` + holdings avg_price=0 → Trigger 1 (자본 임계 도달) primary 신호 측정 자체 불가 — 의제 c5e8f9a2 등록 (capital_evolution_monitor 명세 진입 전 정정 의무)

**검증 시점**:
- e8a17b3c 정정 후 D+1: sector 다양화 후 활용도 변화 측정
- 5/17 정정 sprint 후 30일: 추천 sector 분산 + holdings 진입 비율 비교
- 운영 30일 후: 활용도 추세 (under-utilized 지속 vs 정상 범위 진입)
- 매주 cron 자동화 (Round 3 capital_evolution_monitor 명세 — 별도 의제)

**검증 결과**: 대기 중 — 5/2 baseline (28.6%) 기록 완료

**영향 범위**: 시스템 활용도 측정 (자본 진화 trigger 보조 신호 — Trigger 3)

**Cross-ref**:
- 신규 메모리 `project_capital_evolution_path` (Trigger 3 spec)
- `data/analysis/holdings_utilization_baseline.jsonl` (시계열 추적용)
- D-자본 (Tier 1 baseline 정합) / Round 3 capital_evolution_monitor 명세 (자동화 의제)

---

## [풀스캔 진행] Phase 1.3 표본 가능성 검증 (v1 → v2)

**결정**: hard_floor 적용 v2 재실행 (v1 페니/우선주 noise dominated false positive)

**근거**:
- v1 결과: 5R unique 98.9% / max_excursion 60M+ (페니 ATR≈0 → R분모 폭주)
- 운영 시스템 (`build_extended_universe`) 는 hard_floor 기본 적용 — 분석도 동일해야 정합 (`feedback_source_attribution_discipline` 학습 사례 보강)

**검증 시점**: 당일 풀스캔 v2 (~30분, ~16:46 KST)

**검증 결과**:
- ✅ 5R unique **94.5%** (1,693 / 1,791 처리)
- ✅ max_excursion mean 7.90 (cap=50 작동, outlier 130건 audit jsonl)
- ✅ Phase 1.1 large tier stop_loss **75.6%** → 🔴 verdict
- ✅ D5 결정 23 = consistent (128 vs 가정 114)
- ✅ D5 Bessembinder 한국 패턴 일치
- 파일: `data/analysis/5r_feasibility_full_v2_20260502.json`
- v1 결과 archive: `data/analysis/_archive/v1_pre_hard_floor/`

---

## 통합 평가

**총 의사결정**: D1~D5 + Audit (P0/P1) + 풀스캔 v1/v2 = **9건**

**오늘 작업 평가**: bootstrap founder 의 *검증 단계 baseline 확정* 완료
- 시스템 전반 silent drift 발굴 + 자체 결정 라벨링
- 5/16 Phase 0 verdict + 5/17 4-cell 백테스트 + 5/26 ESTATE 다중 메트릭 verdict 의 *입력 데이터 + 인프라* 모두 사전 구축
- 메타 원칙 (`feedback_source_attribution_discipline`) 정립 — 향후 silent drift 재발 차단

**다음 세션 진입 권고**:
1. 5/2 본인 액션: ATR Phase 0 secret 3개 설정 (의제 9f48284a, P1, due 오늘)
2. 5/3~5/7 자동 진행 모니터링 (action_queue 5건)
3. 5/16~5/17 핵심 게이트 직전 점검
4. 6주 내 회귀 위험 정리: 부채 300% Hard Floor ↔ sector_aware (의제 ac9d1dc1)
5. 운영 데이터 누적 후: Phase 1.1 운영 영향 사전 검증 (큐 3, 의제 d7dea48c)

**관련 문서**:
- `docs/SOURCE_AUDIT_20260502.md` — P0/P1 audit 풀
- `docs/ACTION_QUEUE_PRIORITIZATION_20260502.md` — 24건 우선순위 매트릭스
- `docs/MEMORY_CHANGE_LOG_20260502.md` — 7 메모리 16 변경
- `docs/ESTATE_VALIDATION_METRICS.md` — D3 5 메트릭 사양
- `docs/LANDEX_VALIDATION_RUNBOOK_5_12.md` — D3 5/12/26 RUNBOOK
