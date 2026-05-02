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
