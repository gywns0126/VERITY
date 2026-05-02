# VERITY Decision Log — Master (시간순 통합)

**작성**: 2026-05-03
**범위**: 2026-04-26 ~ 향후 (검증 schedule 포함)
**목적**: 모든 major / sprint-level 결정의 시간순 통합 일지 — *결정 → 결과* causation 추적 baseline (6개월~1년 후 회고용)
**참조 문서**:
- Part A 상세: `docs/DECISION_LOG_RETROSPECTIVE_20260503.md` (4/26 ~ 5/1, T1-01 ~ T1-25, S-01 ~ S-05)
- Part B 상세: `docs/DECISION_LOG_20260502.md` (5/2 오늘, D1~D5 + Audit + 풀스캔)
- 본 문서 = 양 문서 통합 + Part C (향후 schedule) + 양방향 cross-ref index

---

## 시간순 인덱스 (한눈에 보기)

| 일자 | 결정 | Sprint | Tier | 검증 시점 | 상태 |
|---|---|---|---|---|---|
| 2026-04-26 | T1-01 잠금 정책 폐기 + 4 가드 | S-01 | 1 | 운영 영구 | ✅ |
| 2026-04-27 | T1-02 Brain Monitor Phase 1~4 인프라 | S-01 | 1 | 4/30 메타-검수 | ✅ → 결함 3건 |
| 2026-04-27 | T1-03 Reports v2 6단계 인프라 | S-01 | 1 | 즉시 + 게이팅 | ✅ |
| 2026-04-28 | T1-04 Phase A — Brain 룰 이식 | S-01 | 1 | 즉시 + D+30 | ✅ + ⚠️ (P1c) |
| 2026-04-28 | T1-05 Lynch 6분류 한국 임계 | S-01 | 1 | 즉시 + 5/2 P1b | ✅ + ❓ |
| 2026-04-28 | T1-06 Brain 진화 이력 자동 추적 | S-01 | 1 | 4/30 메타-검수 | ✅ → 🔴 결함 1 |
| 2026-04-28 | T1-07 Vercel 인프라 통합 + Pro | S-01 | 1 | 즉시 | ✅ |
| 2026-04-29 | T1-08 마스터 룰 drift audit Phase B | S-02 | 1 | 즉시 + 5/2 audit | ✅ + ⚠️ (Ch.7) |
| 2026-04-30 | T1-09 ESTATE LANDEX V/D/S 실데이터화 | S-03 | 1 | 5/12 첫 cron | ✅ → 대기 |
| 2026-04-30 | T1-10 ESTATE profiles 승인제 | S-03 | 1 | 즉시 | ✅ |
| 2026-04-30 | T1-11 ESTATE estate_action_log | S-03 | 1 | 즉시 + 5/7 점검 | ✅ |
| 2026-04-30 | T1-12 LANDEX D 산식 v1.2 + 메타-검증 | S-03 | 1 | 5/12 mid + 5/26 정식 | 대기 |
| 2026-04-30 | T1-13 Sprint 11 P0 결함 3건 fix | S-04 | 1 | 즉시 + routine | ✅ |
| 2026-04-30 | T1-14 베테랑 due diligence 7결함 평가 수령 | S-04 | 1 | 즉시 + D+90 | ✅ → 1단계 완료 |
| 2026-04-30 | T1-15 결함 1 backtest 무결성 | S-04 | 1 | 즉시 + 5/2 D5 | ✅ |
| 2026-04-30 | T1-16 결함 6 regime leading indicator | S-04 | 1 | 즉시 + 운영 누적 | ✅ |
| 2026-04-30 | T1-17 결함 2 Graham/CANSLIM regime switching | S-04 | 1 | 즉시 + 5/2 P0b | ✅ + ❓ |
| 2026-04-30 | T1-18 결함 3+4 VAMS sizing + factor tilt | S-04 | 1 | 즉시 + Phase 0 | ✅ |
| 2026-04-30 | T1-19 결함 5+7 sentiment env override + daily_actions | S-04 | 1 | 즉시 + 사용자 페이스 | ✅ |
| 2026-04-30 | T1-20 인프라 분리 gh-pages dual-write | S-04 | 1 | HTTP 200 검증 | ✅ |
| 2026-04-30 | T1-21 trade_plan v0_heuristic 레이어 분리 | S-04 | 1 | 즉시 + 운영 누적 | ✅ |
| 2026-05-01 | T1-22 Phase 0 ATR 표준화 (SMA→Wilder EMA) | S-05 | 1 | **5/16 verdict** | 대기 |
| 2026-05-01 | T1-23 Phase 1.1 ATR×2.5 동적 손절 | S-05 | 1 | **5/17 4-cell + D+90** | ✅ → 🔴 풀스캔 v2 |
| 2026-05-01 | T1-24 Phase 1.2 R-multiple 부분 익절 | S-05 | 1 | 즉시 + 운영 누적 | ✅ |
| 2026-05-01 | T1-25 Phase 2-A 5,000 유니버스 인프라 | S-05 | 1 | Phase 0 verdict 후 | ✅ → Day 0 비활성 |
| 2026-05-02 | D1 Stage 3 매도 룰 재설계 | S-06 | 1 | 본인 결정 후 | 보류 |
| 2026-05-02 | D2 ATR 파라미터 출처 정정 + 4-cell 의제 | S-06 | 1 | 5/17 4-cell | ✅ + 풀스캔 보강 |
| 2026-05-02 | D3 ESTATE 백테스트 평가 임계 보강 | S-06 | 1 | **5/12 + 5/26** | ✅ 인프라 / 대기 |
| 2026-05-02 | D4 신호 1·2 출처 단일화 (Mauboussin) | S-06 | 1 | 즉시 | ✅ |
| 2026-05-02 | D5 결정 23 + Bessembinder 자체 검증 | S-06 | 1 | 풀스캔 v2 | ✅ + 🟢 |
| 2026-05-02 | Audit P0/P1 + 풀스캔 v1/v2 | S-06 | 1 | 즉시 + 5/17+ | ✅ → 의제 24건 |
| 2026-05-02 | user_action_queue 시스템 도입 | S-06 | 1 | 즉시 | ✅ |
| 2026-05-02 | staged_updates v1 — Phase 0 누적 자료 강제기 | S-06 | 1 | 5/17 review | 대기 |

---

## Part A: Retrospective (2026-04-26 ~ 2026-05-01)

> **상세**: `docs/DECISION_LOG_RETROSPECTIVE_20260503.md`
> **요약**: 25 Tier 1 결정 / 5 Sprint (S-01~S-05) / 358 commits / 15 신규 메모리

### S-01. Sprint 10 — Brain Monitor + Phase A 룰 이식 + Reports v2 (4/27 ~ 4/28)

T1-01 잠금 폐기 → T1-02 Brain Monitor → T1-03 Reports v2 → T1-04 Phase A 룰 → T1-05 Lynch 6분류 → T1-06 Brain 진화 추적 → T1-07 Vercel 통합

**핵심**: 자가진단 (Brain Monitor) + 외부 출처 룰 이식 (Phase A) + PDF 게이팅 (Reports v2) 3 인프라 동시 구축. Lynch 6분류 한국 캘리브레이션 명시.

### S-02. 마스터 룰 drift audit Phase B (4/29)

T1-08 마스터 룰 drift audit (Lynch Cyclical 5소스 합의 + Q3 매출 CV 폐기 + `feedback_master_rule_drift_audit` 메모리 정책)

**핵심**: T1-05 직후 silent drift 발견 → 향후 룰 추가 시 출처 명시 의무화. 5/2 `feedback_source_attribution_discipline` 의 prequel.

### S-03. ESTATE Implementation Sprint (4/26 ~ 4/30)

T1-09 LANDEX V/D/S 실데이터화 → T1-10 profiles 승인제 → T1-11 estate_action_log → T1-12 LANDEX D v1.2 + 메타-검증

**핵심**: ESTATE Brain 1차 인프라 — R-ONE / VWORLD / 승인제 / 액션 로그 / D 산식 v1.2 + 5 메트릭 사전 인프라. `feedback_estate_density_first` 적용 (VERITY 광범위 패턴 이식 금지).

### S-04. Sprint 11 메타-검수 + 베테랑 due diligence + 인프라 분리 (4/30)

T1-13 Sprint 11 P0 결함 3건 → T1-14 베테랑 7결함 평가 → T1-15~19 7결함 1단계 대응 → T1-20 gh-pages 분리 → T1-21 trade_plan v0_heuristic

**핵심**: 자가진단 → 외부 평가 → 즉시 대응 (16 commits 하루 내). 의사결정 게이트 5/10 → 7/10 추정. 결정 룰 단순 / 로깅 풍부 직교 차원 명시.

### S-05. Phase 0/1.1/1.2/2-A — 매매 룰 표준화 + 유니버스 확장 (5/1)

T1-22 Phase 0 ATR Wilder EMA 마이그레이션 (9 patch) → T1-23 Phase 1.1 ATR×2.5 stop → T1-24 Phase 1.2 R-multiple → T1-25 Phase 2-A 5,000 유니버스

**핵심**: Sprint 11 결함 3 후속 → 본격 마이그레이션. 5/16 Phase 0 verdict 게이트 + 5/17 Phase 1.5.1 또는 rollback. Phase 2-A Day 0 비활성 (Phase 1 우선).

---

## Part B: 2026-05-02 (오늘 결정 + Audit baseline)

> **상세**: `docs/DECISION_LOG_20260502.md`
> **요약**: D1~D5 + Audit (P0/P1) + 풀스캔 v1/v2 = 9건 / 7 메모리 16 변경 / action_queue 24건

### S-06. Audit Sprint — 시스템 출처 무결성 baseline (5/2)

#### [D1] Stage 3 매도 룰 재설계 (보류 — 본인 결정 영역)

**결정**: 보류 + Lynch 1/3 룰 출처 무효 발견 → 대체안 4건 (자체 백테스트 / R-multiple trailing 연장 / percentile-based reduce / Stage 3 룰 보류)
**근거**: Lynch *One Up* (1989) / *Beating the Street* (1993) 원전에 1/3 정량 룰 명시 X
**검증**: 본인 결정 후 (2027 Q1 Bagger Stage Manager 진입 전)
**Cross-ref**: 메모리 `project_multi_bagger_watch` 결정 23 / 선행 T1-08 출처 명시 정책

#### [D2] ATR 파라미터 출처 정정 + 4-cell 백테스트 의제 (P0 격상)

**결정**: ATR(14)×2.5 운영값 유지 + 출처 표현 "월가 표준" → "단기/한국 자체 채택 변형" + LeBeau 원전 ATR(22)×3.0 명시 + 5/17 verdict=ok 후 4-cell 백테스트 P0 격상
**검증 결과**: ✅ D2-1 메모리 정정 / ✅ D2-2 풀스캔 v2 정량 보강 (large stop_loss 75.6% 🔴 = 한국 부적합 강신호)
**Cross-ref**: 선행 T1-23 (Phase 1.1) / 의제 57ac6bd0 (4-cell P0) / d7dea48c (운영 영향) / 0f6dce6a (multiplier 재검토)

#### [D3] ESTATE 백테스트 평가 임계 보강 (silent 측정 → 5/12/26 결정)

**결정**: Mean IC > 0.03 단독 임계 폐기 → 5 메트릭 다중 평가 (Spearman IC / RMSE / Direction / Quintile + Sharpe P1 보류)
**근거**: n=25 신뢰구간 ±0.20, 다중 메트릭 거짓 양성 30% → 8% (4배 감소)
**검증 시점**: 5/5 첫 cron sanity (7f2b51b5) / 5/12 mid (ea3d607b) / 5/26 정식 (41926867)
**Cross-ref**: 선행 T1-12 (LANDEX D v1.2) / 메모리 `project_estate_backtest_methodology`

#### [D4] 신호 1·2 출처 단일화 (Mauboussin)

**결정**: 신호 1 (분기 매출 가속): CANSLIM C 폐기 → Mauboussin & Rappaport *Expectations Investing* (2001) 단일 / 신호 2 (operating leverage): Buffett 1995 + Zweig 폐기 → Mauboussin *More Than You Know* (firm-level) 단일
**검증**: ✅ 즉시 정정 (`project_multi_bagger_watch` line 19, 20)
**Cross-ref**: 선행 T1-08 (출처 명시 정책) / 메모리 `feedback_source_attribution_discipline` 학습 사례

#### [D5] 결정 23 + Bessembinder 자체 검증 (5R 풀스캔 v2)

**결정**: Perplexity 인용 (한국 30년 텐버거 114) 보류 → 자체 풀스캔 검증
**검증 결과**:
- 🟢 결정 23 텐버거 = consistent (가정 114 / 실측 128 / Δ +12.3%)
- 🟢 Bessembinder 한국 패턴 일치 (median -4.36% / skewness 10.89 / top 4% wealth 51.35%)
- ⚠️ Caveat: 한국은 분산형 (top 4% wealth 51% < US 100%) — Concentrated 10 vs 분산 30 결정 10 재검토 의제 (8d762b0a)
**Cross-ref**: 선행 T1-15 (backtest 무결성) / 메모리 `feedback_real_call_over_llm_consensus`

#### [Audit] 시스템 출처 무결성 baseline (Step 1 P0 + Step 2 정정 + Step 3 P1)

**verdict 카운트** (P0+P1 통합, 23 신규 + 6 Skip):

| Verdict | 카운트 | 항목 |
|---|---|---|
| ✅ Skip / 통과 | 8 | D2/D4 정정 6 + Lynch FAST + panic_stages |
| 🟢 보너스 | 2 | 결정 23 / Bessembinder |
| ⚠️ 의제 큐잉 | 3 | Candle / 13F / CYCLICAL Ch.7 |
| 🔴 정정 + 의제 | 3 | 신호 3 / Phase 1.1 / 부채 300% Hard Floor 회귀 |
| ❓ 라벨링 | 9 | Brain 가중치 7:3 / 등급 75-60-45-30 / VCI / GS / VAMS / Lynch 추가 임계 / DGS10 / PEG / VAMS 자본 |

**총 의제 큐잉**: 13건 (Step 2 8 + Step 3 5) → action_queue 누적 24건

**Cross-ref**: 메모리 `feedback_source_attribution_discipline` (audit 메타 원칙) / `project_brain_v5_self_attribution` (P0b/c/d-1/d-2 + P1a/b/c 통합 신규)

#### [Bonus] user_action_queue 시스템 도입 (5/2 morning)

commit: 6a68c30 (10:34 KST)
**결정**: Supabase user_action_queue + scripts/action_queue.py + UserActionQueueCard. "뭐 해야 했지?" 질문 폐지
**Cross-ref**: 선행 T1-11 (estate_action_log) / 메모리 `project_user_action_queue` / `feedback_auto_schedule_action_queue`

#### [Bonus] staged_updates v1 — Phase 0 누적 자료 강제기

commit: 8f8d47c (5/2 00:16 KST)
**결정**: Phase 0 (5/3~5/16) staged_updates v1 — write-time triage + 5/17 review (verdict 의존). 메모리 `project_phase_0_staged_framework`
**Cross-ref**: 선행 T1-22 (Phase 0 마이그레이션) / 5/16 verdict 의제 8c96aef5

---

## Part C: 향후 검증 schedule (Time Machine)

### 즉시 (~1주, 외부 schedule 의존) — 5건

| 우선 | id | 의제 | due | 결정 ID cross-ref |
|---|---|---|---|---|
| 🔴 P1 | 9f48284a | ATR Phase 0 secret 3개 설정 + sanity check | 2026-05-02 (오늘 본인 액션) | T1-22 |
| 🔴 P1 | fe6d1c2d | Gemini 캐시 검증 | 2026-05-03 | T1-11 (action_log) |
| 🔴 P1 | cdad960a | Stage 2 진입 결정 (universe ramp-up 500→1500) | 2026-05-04 | T1-25 |
| 🔴 P1 | 7f2b51b5 | D3 5/5 첫 cron sanity (silent metrics jsonl) | 2026-05-05 | D3 / T1-12 |
| ⚪ P2 | 453e244f | 1주 운영 점검 (Sprint 11 후속) | 2026-05-07 | S-04 |

### 2~3주 내 (5/12 ~ 5/17 verdict 직후) — 4건 — **핵심 게이트 윈도우**

| 우선 | id | 의제 | due | 결정 ID cross-ref |
|---|---|---|---|---|
| ⚪ P2 | ea3d607b | D3 5/12 mid-checkpoint | 2026-05-12 | D3 / T1-12 |
| 🔴 P1 | 8c96aef5 | **ATR Phase 0 5/16 verdict** (자동 cron) | 2026-05-16 | T1-22 |
| 🔴 P1 | 57ac6bd0 | **Phase 1.1 4-cell 백테스트** (verdict=ok 후 P0) | 2026-05-17 | T1-23 / D2 / 풀스캔 v2 🔴 |
| 🔴 P1 | 41926867 | D3 5/26 정식 verdict | 2026-05-26 | D3 / T1-12 |

### 6주 내 (운영 데이터 누적 후) — 4건

| 우선 | id | 의제 | 의존성 | 결정 ID cross-ref |
|---|---|---|---|---|
| 🔴 P1 | d7dea48c | Phase 1.1 운영 영향 사전 검증 (운영 stop hit vs 백테스트 75.6%) | 운영 holding 30+ 누적 | T1-23 / 풀스캔 v2 |
| ✅ → 🔴 | ac9d1dc1 | 부채 300% Hard Floor ↔ sector_aware 면제 검증 (회귀 위험) | **검증 완료 5/2 18:00 KST** | T1-04 / 5/2 P1c — 결과 🔴 (`docs/REGRESSION_RISK_AUDIT_20260502.md`) |
| 🔴 P0 | fa3c2d1e | **sector_thresholds 헬퍼 + Hard Floor 정정 sprint** (ac9d1dc1 후속) | Phase 0 verdict (5/17+) 후 진입 권장. **caveat: sector NULL 51/51 — e8a17b3c 선행** | T1-04 / T1-05 / 운영 코드 변경 |
| 🔴 **P0+** | **e8a17b3c** | **sector 필드 propagation 결함 정정** (fa3c2d1e 선행 의존성) | Phase 0 verdict (5/17+) 후 진입 — 5/2 22:XX 진단 sector NULL 51/51 정량 확정 | T1-04 / `docs/OPS_VERIFICATION_20260502.md` |
| ⚪ **P1** | **b9d4f72a** | **VAMS sector_diversification silent gap 검증** (e8a17b3c 후속) | e8a17b3c 정정 후 D+1 운영 cron | T1-18 결함 4 / `feedback_source_attribution_discipline` 학습 사례 5번째 |
| 🔴 **P0+** | **c5e8f9a2** | **vams.total_value=0 + avg_price=0 silent error 정정** (P0 → P0+ 격상 5/3 00:15) | 자본 진화 path 모든 후속 작업 전제 — 5/17 verdict 후 즉시 진입 | **blocks**: capital_evolution_monitor / Tier 전환 감지 / Holdings 손익 / 자본 진화 후속 |
| ⚪ **P2** | **f3a8c1d4** | **데이터 layer 검증 의무화 — 모든 모듈 spec 의 전제 조건** | 다음 모듈 spec 작성 시 즉시 발효 | `feedback_source_attribution_discipline` 학습 사례 6번째 |
| ⚪ P2 | a760aaff | Brain 가중치 7:3 OOS 백테스트 | brain_weights_cv 누적 4주+ | T1-17 / 5/2 P0b |
| ⚪ P2 | 8d762b0a | Bessembinder 운영 함의 (Concentrated 10 vs 분산 30) | 풀스캔 v2 ✅ | D5 / T1-15 |

### 3개월 보류 / 운영 코드 변경 sprint — 10건

| id | 의제 | 결정 ID cross-ref |
|---|---|---|
| eb0c38e7 | 13F bonus 한국 적용성 (KRX 5%+ 보고) | 5/2 P0d-4 |
| a76f7dd5 | Candle bonus 임계 출처 검증 (Nison 원전) | 5/2 P0d-3 |
| 7916b1f5 | 신호 3 코드 구현 정정 (운영 코드) | T1-08 / 5/2 P0a |
| **fa3c2d1e** | **sector_thresholds 헬퍼 + Hard Floor 정정 (verity_brain.py:1631 / lynch_classifier TURNAROUND 부채)** | T1-04 / 5/2 P1c / ac9d1dc1 검증 / e8a17b3c 선행 |
| **e8a17b3c** | **sector 필드 propagation 정정 (recs sector/category None 51/51)** | T1-04 / fa3c2d1e 선행 / `docs/OPS_VERIFICATION_20260502.md` |
| 0f6dce6a | ATR_STOP_MULTIPLIER 변경 sprint | T1-23 / 4-cell 결과 의존 |
| 22cdd1ec | PEG 3.0 vs Lynch 2.0 보수화 근거 | T1-04 / 5/2 P1c |
| ad4fa2fd | Lynch 임계 (5조/1조/0.8/300%) 산출 근거 | T1-05 / 5/2 P1b |
| d9a64306 | CYCLICAL Lynch Ch.7 챕터 재검증 | T1-05 / T1-08 / 5/2 P0a/P1b |
| 64d145cc | VAMS 프로필 alpha 비교 + 자본 비례 변환 가이드 | 5/2 P1a |
| b02dffe1 | alert_dispatcher warnings_since reset 누락 | T1-02 (trust 4/30~) |
| 9f61f6ac | data_health.jsonl 28h 미작성 | T1-02 (record_health 누락) |

### 분기별 review (3개월 후) — 2026-08-02

- T1-22~T1-25 운영 90일 결과 (Phase 0 verdict / Phase 1.1 stop_hit / Phase 1.2 1R hit / Phase 2-A 진입 여부)
- T1-12 D3 5/26 verdict 결과 + 3개월 누적 IC 추세
- Sprint 11 결함 후속 5건 (look-ahead / timing_signal / OOS / correlation / Markov) 진행도
- "어떤 결정이 alpha 줬나" 회고 (검증 결과 ✅⚠️🔴 갱신)

---

## Cross-Reference Index (양방향)

### 결정 → 후속 결정 (forward)

| 선행 | 후속 |
|---|---|
| T1-01 (잠금 폐기) | T1-02 ~ T1-25 (전제) / 5/2 audit (silent drift 점검 정책) |
| T1-02 (Brain Monitor) | T1-13 (P0 결함 3건) / 의제 b02dffe1 / 9f61f6ac |
| T1-04 (Phase A 룰) | 5/2 P1c (PEG 3.0 / 부채 300%) / 의제 22cdd1ec / ac9d1dc1 |
| T1-05 (Lynch 6분류) | T1-08 (drift audit) / 5/2 P0a/P1b / 의제 ad4fa2fd / d9a64306 |
| T1-06 (Brain 진화 추적) | T1-13 (결함 1 fix) |
| T1-08 (drift audit) | 5/2 audit Step 1/2/3 (`feedback_source_attribution_discipline` prequel) |
| T1-12 (LANDEX D v1.2) | D3 5 메트릭 / 5/12 mid / 5/26 정식 |
| T1-14 (베테랑 평가) | T1-15 ~ T1-21 (1단계 대응) |
| T1-16 (regime leading) | T1-17 (regime_diagnostics 활용) |
| T1-17 (Graham/CANSLIM regime) | 5/2 P0b / 의제 a760aaff |
| T1-18 (VAMS sizing/factor tilt) | T1-22 (Phase 0 ATR 직접 수집) |
| T1-21 (trade_plan v0) | T1-23 (Phase 1.1 stop) / T1-24 (Phase 1.2 exit) |
| T1-22 (Phase 0 ATR) | T1-23 / T1-24 / 의제 9f48284a / 8c96aef5 / 5/2 staged_updates v1 |
| T1-23 (Phase 1.1) | D2 / 풀스캔 v2 🔴 / 의제 57ac6bd0 / d7dea48c / 0f6dce6a |
| T1-25 (Phase 2-A) | 의제 cdad960a (Stage 2 5/4) |
| D2 (ATR 4-cell) | T1-23 (선행) / 풀스캔 v2 / 5/17 4-cell |
| D5 (Bessembinder) | T1-15 (선행 backtest) / 의제 8d762b0a |

### 결정 → 메모리 매핑 (15 신규 / 5/2 추가 2)

| 메모리 | 결정 ID |
|---|---|
| feedback_continuous_evolution | T1-01 |
| project_brain_kb_learning | T1-04 |
| feedback_brain_evolution_admin_sync | T1-06 |
| feedback_perplexity_collaboration | T1-04 |
| feedback_master_rule_drift_audit | T1-08 |
| project_estate_backtest_methodology | T1-12 |
| feedback_metavalidation_decompose | T1-13 |
| project_sprint_11_veteran_response | T1-14 ~ T1-21 |
| project_trade_plan_v0_layer | T1-21 |
| feedback_decision_logging_separation | T1-21 |
| project_atr_phase0_migration | T1-22 |
| project_atr_dynamic_stop | T1-23 / D2 |
| project_r_multiple_exit | T1-24 |
| project_stock_filter_v0_enhancement | T1-25 |
| feedback_auto_schedule_action_queue | T1-25 |
| feedback_source_attribution_discipline | 5/2 audit (T1-08 후속) |
| project_brain_v5_self_attribution | 5/2 audit (P0b/c/d + P1a/b/c) |
| project_phase_0_staged_framework | 5/2 staged_updates v1 |
| project_user_action_queue | 5/2 user_action_queue |

---

## 통계 요약

### 결정 총량 (4/26 ~ 5/2)

| Tier | 카운트 |
|---|---|
| Tier 1 (4/26 ~ 5/1) | 25 |
| Tier 1 (5/2 audit) | 9 (D1~D5 + Audit + user_queue + staged_updates + 풀스캔 v1/v2) |
| **Tier 1 합계** | **34** |
| Tier 2 sprint | 6 (S-01 ~ S-06) |
| Tier 3 commits | 358 (자동 ~200 + feat-class 156) |

### 메모리 총량 (4/26 ~ 5/2)

| 분류 | 카운트 |
|---|---|
| 신규 메모리 (4/26 ~ 5/1) | 15 |
| 신규 메모리 (5/2) | 4 (`feedback_source_attribution_discipline` / `project_brain_v5_self_attribution` / `project_phase_0_staged_framework` / `project_user_action_queue`) |
| **신규 합계** | **19** |
| 5/2 변경 (정정/보강) | 16회 / 7 메모리 |

### action_queue 총량 (5/2 baseline)

| 분류 | 카운트 |
|---|---|
| 즉시 (~1주) | 5 |
| 2~3주 내 (5/12~5/17) | 4 |
| 6주 내 | 4 |
| 3개월 보류 + 운영 코드 변경 | 10 |
| **합계** | **24** (P1 격상 9 + P2 그 외) |

### 검증 상태 분포 (Tier 1, 4/26 ~ 5/2)

| 상태 | 카운트 | 비고 |
|---|---|---|
| ✅ 통과 | 21 | 즉시 검증 통과 + 1단계 완료 |
| ✅ + ⚠️/❓ 부분 | 6 | 즉시 통과 / audit verdict 부분 (T1-04 / T1-05 / T1-08 / T1-17 / T1-23) |
| 🔴 정정 / 회귀 위험 | 1 | T1-23 (풀스캔 v2 75.6%) |
| 대기 (schedule 의존) | 5 | T1-12 / T1-22 / D1 / D3 / staged_updates |
| 보류 (본인 결정) | 1 | D1 |

---

## 유지 관리 정책

| 주기 | 작업 | 시간 비용 |
|---|---|---|
| 매주 일요일 | 그 주 commit log + 메모리 변경 → 본 master 업데이트 + Tier 분류 + cross-ref | ~15분 |
| Major decision 발생 시 | phase/version 변경 / architectural / 외부 출처 채택 / 운영 영향 high → 즉시 추가 | 5~10분 |
| 분기별 1회 (3개월) | "대기 중" entry D+90 hit rate / 운영 결과 반영 / ✅⚠️🔴 갱신 / 회고 | ~1시간 |
| 메모리 변경 시 (자동) | `feedback_source_attribution_discipline` trigger → 메모리 정정 시 본 일지 cross-ref 의무 | 자동 |

**다음 분기별 review**: 2026-08-02

---

## 베테랑 메타 메모

본 일지의 진짜 가치:
1. 6개월 후 운영 결과 검증 시 **causation 추적** (어떤 결정이 어떤 결과 낳았나)
2. 1년 후 시스템 진화 회고 시 **learning rate 측정**
3. 외부 검증 / due diligence 시 **audit trail** 제공
4. PM (사용자) 자기 학습 패턴 자체 분석 도구

함정 회피:
- "결정이 옳았나" 평가 X (감정 / 후견편향)
- 단순 가설 → 검증 결과 매핑만
- 검증 결과는 *데이터가 말함* (운영 hit rate / Sharpe / drawdown)

---

## 변경 추적

| 일자 | 변경 |
|---|---|
| 2026-05-03 | 초기 작성 — Part A (T1-01~T1-25, S-01~S-05) + Part B (5/2 D1~D5 + Audit) + Part C (24건 schedule) + Cross-ref index |
| 2026-05-02 18:00 KST | 의제 ac9d1dc1 검증 완료 → 🔴 (회귀 위험 확정). 신규 의제 fa3c2d1e (sector_thresholds 정정 sprint) 등록. `docs/REGRESSION_RISK_AUDIT_20260502.md` 신규 |
| 2026-05-02 22:30 KST | fa3c2d1e 영향 정량 진단 — KB금융 grade=AVOID + auto_avoid 발현 (회귀 부분 발현 확정). 별개 finding sector NULL 51/51 → 신규 의제 e8a17b3c (P0+ fa3c2d1e 선행). `docs/OPS_VERIFICATION_20260502.md` 신규 |
| 2026-05-02 23:00 KST | e8a17b3c root cause 확정 — KR sector 수집기 미구현 (`api/collectors/kr_sector.py` 신규 + universe_builder/dart_fundamentals sector 부착). 부수 발견: VAMS sector_diversification silent gap (vams/engine.py:421,430 단일 "Unknown" 분류) |
| 2026-05-02 23:55 KST | VAMS 프로필 진단 (Round 2 follow-up) — active=moderate 확정 (config default + portfolio.json 일치). 신규 silent error finding: `vams.total_value=0` + holdings avg_price=0 → 의제 c5e8f9a2 (P0). holdings_utilization_baseline.jsonl + project_capital_evolution_path + DECISION_LOG_20260502 D-Holdings entry 정정 (active=moderate label) |

---

문서 끝. (Master baseline 확정 — 4/26 ~ 5/2 통합 + 향후 schedule)
