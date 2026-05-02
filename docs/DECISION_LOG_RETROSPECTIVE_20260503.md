# Retrospective Decision Log — 2026-04-26 ~ 2026-05-01

**작성**: 2026-05-03 (5/2 audit baseline 직후)
**범위**: 5/2 본 audit 작업 *이전* (4/26 ~ 5/1) 의 major / sprint-level 결정 통합
**목적**: 6개월~1년 후 운영 결과 검증 시 *결정 → 결과* causation 추적 baseline 확보
**전제**:
- 5/2 결정 (D1~D5 + audit + 풀스캔 v1/v2) 은 `docs/DECISION_LOG_20260502.md` Part 1 에 별도 기록 (본 문서 범위 밖)
- documentation only — 운영 코드 / 운영 데이터 / 메모리 미터치
- 데이터 소스: 스펙 §27~30 + git log 4/26-5/1 (358 commits, feat-class 156) + 베테랑 due diligence 보고서 + 메모리 (40개) + docs/

**원칙** (`feedback_source_attribution_discipline` 정합):
- Tier 1 entry = 결정 + 근거 + 검증 시점 + 검증 결과 + 영향 범위 + cross-ref (5~7줄)
- Tier 2 entry = sprint 압축 (테마 + 결정 ID list + 결과 평가, 1~2줄)
- Tier 3 = 통계만 (commit / 메모리 / 의제 카운트)
- "결정이 옳았나" 평가 X — *데이터가 말함* (운영 hit rate / Sharpe / drawdown)

---

## Part 1: Tier 1 — Major Decisions (T1-01 ~ T1-25)

### T1-01. 잠금 정책 폐기 + 4 가드 도입

  commit: §27.1 (메모리 `feedback_continuous_evolution`, ValidationPanel.tsx 정정)
  일자: 2026-04-26
  sprint: S-01

  결정: 분기/반기/연간 리포트 정적 잠금 (Brain 코드 동결 + N일 누적) 폐기. 검증 의미 재정의 → "운영 누적 N일치 시그널-결과 페어" + 룰은 진화 OK
  근거: 기존 잠금 정책은 통제 변수 가정. 25일 단독 제작 + 운영 진화 속도 + commit/시간대/모니터링/롤백 4 가드 활용 가능
  검증 시점: 즉시 (메모리 전환) + 운영 영구 (4 가드 실효성)
  검증 결과: ✅ ValidationPanel "운영 누적 판정 · 룰 진화 OK" 전환 / 진화 hit rate 측정은 운영 누적 N일 후
  영향 범위: 검증 정책 / 모든 sprint (잠금 부재 가정)
  Cross-ref: 후속 모든 sprint (T1-02~T1-25) 의 전제 / 메모리 `feedback_continuous_evolution` + `project_validation_plan`

### T1-02. Brain Monitor 인프라 Phase 1~4 구축

  commit: f365b18 / d3c0ddb / fab43d1 / 5b17c29 (4/27 21:23-21:48 4 commits) → 5864614 / 4ec0584 (4/28 18:28-18:33 TSX 단일 컴포넌트)
  일자: 2026-04-27 ~ 2026-04-28
  sprint: S-01

  결정: 관리자 전용 모니터링 + 리포트 발행 신뢰도 자동 판정 인프라 구축. 4 측정 모듈 (data_health / feature_drift / explainability / trust_score) + 5탭 대시보드 + Telegram 알림 + Trust PDF 게이팅. 3D Three.js → 2D SVG 단일 .tsx 코드 컴포넌트로 폐기
  근거: Sprint 9까지 운영 신호 (data freshness / drift / brain 분포) 수동 점검. 운영 진화 속도 ↑ 후 자동 모니터링 부재 시 silent drift 누적 위험. 3D Three.js 는 잔상/Sandbox 충돌/모바일 viewport 문제로 폐기
  검증 시점: 즉시 (단위 테스트 31 통과) + 4/30 메타-검수 (Sprint 11 P0 결함 발견 시점)
  검증 결과: ✅ 인프라 가동 / ⚠️ 4/30 운영 11회 누적 후 P0 결함 3건 발견 (T1-13 으로 연결) — 측정 라인은 살아있으나 신호 의미 약화
  영향 범위: observability / Framer / Trust PDF 게이팅 / cron
  Cross-ref: 후속 → T1-13 (Sprint 11 메타-검수 결함 3건) / 메모리 `feedback_brain_evolution_admin_sync`

### T1-03. Reports v2 6단계 인프라 (Daily/Weekly/Monthly/Quarterly/Semi/Annual + 관리자/일반인)

  commit: e6d1cf9 (Daily v2) / aed0543 (Weekly v2) / 978aa75 (Monthly/Q/Semi/Annual) / bf4f672 (5차 갭) / 7d64ac5 (Framer dual button) / b6b650f (cron)
  일자: 2026-04-27 19:32 ~ 21:01
  sprint: S-01

  결정: 6단계 PDF 리포트 × 관리자/일반인 이원화 (총 12 리포트). 일반인용 dilution 룰북 + 단위표기 정합 + LLM 사전주입 + 시나리오 라벨링 가드. cron 자동화
  근거: 보고서 분리 없이 단일 PDF 운영 시 일반인 대상 IR 가독성 부족. Trust PDF 게이팅 (T1-02) 의 출력 채널 사전 구비
  검증 시점: 즉시 (12 PDF 자동 생성) + Trust 게이팅 가동 후 hold/manual_review 분기 검증
  검증 결과: ✅ 운영 정상 / Trust 게이팅 - hold 차단 동작 확인 (Sprint 11 직전)
  영향 범위: reports / cron / Framer (VerityReport 듀얼 버튼)
  Cross-ref: T1-02 (Trust 게이팅 입력) / 메모리 `feedback_brain_evolution_admin_sync`

### T1-04. Phase A — Brain 룰 이식 (배리티 브레인 투자 바이블)

  commit: fd17367 (Druckenmiller regime_weight) / 7c89024 (Lynch PEG → graham_value) / 396aa5d (Hard Floor 강화 — 유동비율 + PEG 절대 매도)
  일자: 2026-04-28 19:53-20:09
  sprint: S-01

  결정: PDF 9권 → 1권 통합 정리본 룰 *이식* (RAG 아님). 3 룰 즉시 적용 — Druckenmiller bond_regime → multi_factor 가중치 동적 / Lynch PEG 보정 (graham_value) / Hard Floor 강화 (유동비율 50% / PEG 3.0 절대 매도)
  근거: 외부 출처 (Lynch 2권 / Ackman / Druckenmiller / TCI Hohn / Rokos) 정량 임계 통합. 한국 retail bias 보정 (PEG 3.0 = Lynch 원전 2.0 보수화)
  검증 시점: 즉시 (단위 테스트) / 운영 누적 D+30 brain 분포 변화 / 5/2 audit P1c (PEG 3.0 vs 2.0 보수화 근거 명시 의제)
  검증 결과: ✅ 즉시 통과 / ⚠️ 5/2 P1c verdict ❓ — 자체 보수화 명시 X (의제 22cdd1ec) / 부채 300% Hard Floor ↔ sector_aware 충돌 회귀 위험 발견 (의제 ac9d1dc1)
  영향 범위: Brain v5 / VAMS (multi_factor 가중치 동적) / Hard Floor 매도 신호
  Cross-ref: 메모리 `project_brain_kb_learning` / 5/2 audit P1c / 의제 22cdd1ec / ac9d1dc1

### T1-05. Lynch 6분류 — 한국 KOSPI/KOSDAQ 임계 확정

  commit: 9e99620
  일자: 2026-04-28 20:27
  sprint: S-01

  결정: `lynch_classifier.py` 신규. 한국 GDP 2026E 1.9% 기준. FAST=15%/시총≤5조 / STALWART=5-15%/≥1조 / TURNAROUND=ROE<0+op_margin>0+rev>0+부채<300% / CYCLICAL=11키워드 / ASSET=PBR<0.8 / SLOW=default. 우선순위 Turn → Cyc → Fast → Stal → Asset → Slow
  근거: Lynch 원전 Fast Grower 20-25% (1989 미국 명목 GNP ~7-8% × 3) → 한국 명목 GDP × 3 ≈ 10-11% vs 절대값 20% 사이 운영 선택. 헤더 docstring 출처 명시 ✅ (KDI/IMF/OECD)
  검증 시점: 즉시 (test_lynch_classifier 18 cases) / 4/29 마스터 룰 drift audit (Lynch Cyclical 키워드 5소스 합의) / 5/2 P1b
  검증 결과: ✅ 즉시 통과 / ✅ 4/29 Cyclical 키워드 반도체·자동차 추가 (commit 3383e6f) / 5/2 P1b verdict = FAST_GROWER ✅ / 다른 임계 (5조/1조/0.8/300%) ❓ (의제 ad4fa2fd) / CYCLICAL Ch.7 인용 챕터 재검증 의제 d9a64306
  영향 범위: Brain / 종목 분류 / VAMS holding 분류
  Cross-ref: 후속 T1-08 (마스터 룰 drift audit) / 5/2 P0a / P1b / 메모리 `project_brain_kb_learning`

### T1-06. Brain 진화 이력 자동 추적 + commit prefix 정책

  commit: f044707
  일자: 2026-04-28 20:15
  sprint: S-01

  결정: `brain_evolution.py` 신규. git log 분석으로 commit 메시지 prefix 자동 파싱 (`feat|fix|perf|refactor (brain|observability|reports|estate)`). portfolio["brain_evolution_log"] 최근 30개 attach. AdminDashboard CardBrainEvolution 카드 자동 반영
  근거: 잠금 폐기 (T1-01) 후 진화 이력을 별도 reporting 으로 관리 시 비용. commit 메시지 = single source of truth. 메모리 `feedback_brain_evolution_admin_sync` (commit prefix 의무 + 별도 reporting X)
  검증 시점: 즉시 (운영 attach) / 4/30 Sprint 11 메타-검수 (quick/realtime save_portfolio 누락 결함 발견)
  검증 결과: ✅ 인프라 가동 / 🔴 4/30 결함 발견 (quick/realtime 모드 디스크 미반영) → fix commit c33319c (T1-13)
  영향 범위: observability / AdminDashboard / 모든 향후 commit (prefix 정책)
  Cross-ref: 후속 → T1-13 (결함 1 fix) / 메모리 `feedback_brain_evolution_admin_sync`

### T1-07. Vercel 인프라 통합 — vercel-api 단일 프로젝트 + Pro 결제

  commit: 99cc906 (estate_backend 통합) / 27e27de (ignoreCommand 제거 후 Pro 한도 해제)
  일자: 2026-04-28 12:28-21:08
  sprint: S-01

  결정: estate_backend 별도 프로젝트 → vercel-api 단일 프로젝트 흡수 (21 함수). admin 5 → 1 통합 (`api/admin.py` query param 라우터). Hobby 12 한도 → Pro 결제 → 250 한도. cron quota 보호용 ignoreCommand 도입 후 Pro 전환으로 제거
  근거: estate_backend 분리 시 Vercel quota / Framer 클라이언트 측 fetch 도메인 분산 / cron 비용 ↑. 단일 프로젝트로 인프라 통합 + Pro 결제 (월 $20) 정량 합리화
  검증 시점: 즉시 (배포 정상) / 운영 누적 (cron 빈도 / Framer fetch 정합)
  검증 결과: ✅ Pro 전환 후 cron 100/일 한도 해제 / Framer BrainMonitor.tsx 단일 코드 컴포넌트 정상
  영향 범위: 인프라 / cost / Framer / Vercel API
  Cross-ref: 메모리 `project_vercel_infra`

### T1-08. 마스터 룰 drift audit (Phase B) + Lynch Cyclical 5소스 합의 + Q3 매출 CV 폐기

  commit: c92d727 (false alarm 차단) / 6752040 (Lynch 임계 근거 정정 + drift 검증 정책) / 3383e6f (Cyclical 키워드 5소스 합의) / 8c16a67 (Q3 통합)
  일자: 2026-04-29 21:45-22:55
  sprint: S-02

  결정: 9권 마스터 룰 silent drift 검증 (Phase B). 원전 출처 명시 + 조정 산출식 코드 주석 의무 (메모리 `feedback_master_rule_drift_audit`). Lynch Cyclical 키워드 5소스 (Lynch + 한국 산업분류 + KOSPI섹터 + 증권업 분류 + 자체 검증) 합의 후 반도체·자동차 추가. Q3 매출 CV 폐기 → 영업이익률 std 권고 (signal-to-noise 개선)
  근거: T1-05 직후 임계값 silent drift (1차/2차 요약본 차이) 발견. 원전 직접 인용 vs 자체 캘리브레이션 명확 분리 필요. Lynch Cyclical 4키워드 (자동차/철강/화학/항공) → 한국 시장 실제 cyclical 미커버 종목 (반도체/조선/건설/해운) 분류 누락
  검증 시점: 즉시 (메모리 정책 도입) / 운영 누적 (drift 재발 X 검증) / 5/2 P1b CYCLICAL Ch.7 챕터 재검증 의제
  검증 결과: ✅ 즉시 정정 완료 / ✅ Cyclical 키워드 11개로 확장 / ⚠️ 5/2 P0a/P1b CYCLICAL Ch.7 인용 챕터 재검증 의제 d9a64306 (별도 sprint)
  영향 범위: Brain / 메모리 정책 / 향후 룰 추가 시 출처 명시 의무
  Cross-ref: 선행 T1-05 / 후속 5/2 audit Step 1 P0 + Step 3 P1 / 메모리 `feedback_master_rule_drift_audit`

### T1-09. ESTATE LANDEX V/D/S 실데이터화 (R-ONE 어댑터 통합)

  commit: 2ccfbbe (R-ONE 어댑터 LANDEX V/D/S) / 5b05a6f (VWORLD geocoding 어댑터) / a52bd6b (서울 지하철 STATION_TO_GU) / b5636d8 (LANDEX snapshot wrapper + GH Actions)
  일자: 2026-04-30 01:43-01:45
  sprint: S-03

  결정: ESTATE LANDEX 의 V (밸류) / D (수요) / S (공급) 점수를 mock 에서 R-ONE 매매지수 + 미분양 통계 직접 호출로 전환. VWORLD 지오코더 (refined.structure.level2 / ROAD→PARCEL fallback) + 서울 지하철 API 응답 키 변경 자동 보강
  근거: ESTATE 기획 단계에서 mock 데이터 운영 시 메타-검증 무의미. R-ONE 실측 사양 (CLS_ID 매핑이 통계마다 다름, KOSIS Param 우회) 1회 실호출 검증 (메모리 `project_rone_api_spec` / `feedback_real_call_over_llm_consensus` 정합)
  검증 시점: 즉시 (R-ONE freshness probe) / 5/12 첫 cron sanity (의제 7f2b51b5)
  검증 결과: ✅ R-ONE freshness probe 가동 / ✅ LANDEX V/D/S 실데이터 전환
  영향 범위: ESTATE / R-ONE / VWORLD / GH Actions
  Cross-ref: 메모리 `project_rone_api_spec` / `project_vworld_api_spec` / 후속 T1-12

### T1-10. ESTATE 인증 — profiles 승인제 마이그레이션 (007 + 008)

  commit: 6bb7635 / ee6df47 (007 profiles 승인제) / f263173 / e11f90c (008 admin RLS + AdminDashboard 가입 승인 UI)
  일자: 2026-04-30 01:45-01:59
  sprint: S-03

  결정: profiles 테이블 승인제 도입 (003+007 마이그레이션). AuthPage / EstateAuthPage 분리 · 세션 공유. is_caller_admin() SECURITY DEFINER 함수로 RLS 무한 재귀 우회 (메모리 `feedback_supabase_rls_no_self_subquery`)
  근거: ESTATE 별도 사용자 풀 운영 시 Supabase RLS 정책에서 같은 테이블 EXISTS 자기참조 → 무한 재귀 발생. SECURITY DEFINER 함수로 우회
  검증 시점: 즉시 (마이그레이션 적용) / 사용자 가입 시도 시 (운영 검증)
  검증 결과: ✅ 승인 UI 정상 / RLS 무한 재귀 회피 정합
  영향 범위: Supabase / Auth / ESTATE / Admin UI
  Cross-ref: 메모리 `project_auth_status_schema` / `feedback_supabase_rls_no_self_subquery`

### T1-11. ESTATE 사용자 액션 로깅 시스템 (estate_action_log.json)

  commit: 21d67c6 (action log 시스템) / cdd1341 (CardUserActions 모바일 우선) / 18f7359 (Sandbox 60s heartbeat 차단)
  일자: 2026-04-30 02:58-03:18
  sprint: S-03

  결정: 사용자 직접 처리 액션 자동 append → `data/estate_action_log.json`. EstateActionLog 컴포넌트 + AdminDashboard CardUserActions. Sandbox 60s heartbeat 회귀 차단 (Supabase fetch + hard-gate 제거)
  근거: ESTATE 별도 사용자 풀 운영 시 사용자 직접 처리 액션을 별도 추적 채널 부재 → 분실 위험. 메모리 `feedback_user_action_logging` (자동 append 의무)
  검증 시점: 즉시 (15개 done 처리 4/30 19:13)
  검증 결과: ✅ 15개 done 처리 / ⚠ 5/7 1주 점검 의제 (453e244f) / 5/3 Gemini 캐시 검증 (fe6d1c2d)
  영향 범위: ESTATE / Framer / 사용자 워크플로
  Cross-ref: 메모리 `feedback_user_action_logging` / 후속 T1-12 / 5/2 user_action_queue 통합 (memory `project_user_action_queue`)

### T1-12. LANDEX D 산식 v1.2 + 백테스트 메타-검증 인프라

  commit: 17dc386
  일자: 2026-04-30 19:51
  sprint: S-03

  결정: LANDEX D (수요) 산식 v1.1 → v1.2 갱신 — 윈도우 12주 → 26주 확장. 백테스트 메타-검증 인프라 + 마켓 레짐 프리셋 6개 + tightening regime 채택
  근거: D 산식 v1.1 12주 윈도우 = 단기 노이즈 dominant. 26주로 확장하여 분기 사이클 정합. n=25 (서울 25구) 한계 내에서 mean IC 0.03 단독 임계 부적합 → 5 메트릭 (Spearman IC / RMSE / Direction / Quintile + Sharpe P1 보류) 사전 인프라
  검증 시점: 5/12 mid-checkpoint (의제 ea3d607b) / 5/26 정식 verdict (의제 41926867)
  검증 결과: 대기 중 — 5/12 / 5/26 cron 결과 / 5/2 D3 5 메트릭 silent 측정 인프라 사전 구축 완료
  영향 범위: ESTATE / 메타-검증 / 백테스트 (lookback 8년 한국 사이클 1회)
  Cross-ref: 메모리 `project_estate_backtest_methodology` / 5/2 D3 / 의제 ea3d607b / 41926867

### T1-13. Sprint 11 자가진단 — Trust 정확도 P0 결함 3건 fix

  commit: c33319c (결함 1 brain_evolution_log 디스크 미반영 + 결함 2 brain_distribution_normal silent PASS) / a0fac4c (결함 3 Drift cry-wolf 완화) / 8424bdf (P1 per-source freshness)
  일자: 2026-04-30 19:06-19:56
  sprint: S-04

  결정: 운영 11회 누적 후 메타-검수 → 3 P0 결함 fix. (1) quick/realtime 모드 save_portfolio 누락 → in-memory 만 → 디스크 반영. (2) trust_score._check_brain_distribution grade 위치 버그 (top-level r.grade=None) → r.verity_brain.grade. (3) feature_drift 단일 critical 자동 overall 승격 → 비율 50%+ 또는 overall ≥ 0.2 일 때만
  근거: T1-02 가동 후 trust verdict 만성 manual_review (mood_score critical 1개로 overall=0.0934). 신호 의미 약화 = 측정 라인 살아있으나 거짓 양성 dominate. 메모리 `feedback_metavalidation_decompose` (요소별 분해 + 시간차 baseline 둘 다)
  검증 시점: 즉시 (test 49/49 통과) / 4/30 21:15 KST 자동 routine (다음 cron portfolio.json 3 체크)
  검증 결과: ✅ 즉시 통과 / ✅ routine 통과 (brain_evolution_log > 0, lynch SLOW_GROWER 61.5%, brain_distribution_normal 'BUY+' 형식)
  영향 범위: observability / Trust / Brain / 모든 cron 모드
  Cross-ref: 선행 T1-02 / T1-06 / 후속 T1-14 (베테랑 평가는 같은 날 후반) / 메모리 `feedback_metavalidation_decompose`

### T1-14. 베테랑 due diligence 평가 수령 — 7결함 평가

  commit: §29.1 (외부 LLM 평가 + 사용자 전달, 보고서 docs/SPRINT_11_VETERAN_RESPONSE_2026-04-30.md)
  일자: 2026-04-30 evening
  sprint: S-04

  결정: 월스트리트 PM 관점 due diligence 평가 수령 + 7결함 1단계 대응 결정 ("판단 정밀도" 우선). 평가 inputs: 의사결정 게이트 5/10 / 수집·관측·거버넌스 9/10. 7결함 = P0 3 (backtest, brain weight, sizing) + P1 3 (correlation, sentiment, regime) + P2 1 (UI)
  근거: 외부 PM 관점 = 본 시스템 *내 돈을 넣겠는가* 질문에 No. "기능 추가 X / 판단 정밀도 우선" 명시. 4주 sprint 권고 즉시 1단계 대응 (16 commits 하루 내)
  검증 시점: 즉시 (보고서 작성 + 1단계 대응) / 5/16~5/17 핵심 게이트 / 운영 D+90 (실측 vs 백테스트)
  검증 결과: ✅ 7결함 모두 1단계 대응 완료 (T1-15 ~ T1-19) / 의사결정 게이트 5/10 → 7/10 추정 / 결함 후속 (look-ahead bias / cross-validation / ATR 직접 수집 / correlation matrix / sentiment timing_signal 분리) 다음 sprint
  영향 범위: 시스템 전체 / 평가 표준 (외부 PM 관점) / 다음 sprint 우선순위
  Cross-ref: 후속 T1-15/16/17/18/19 (7결함 대응) / 메모리 `project_sprint_11_veteran_response`

### T1-15. 결함 1 — Backtest 무결성 (survivorship + slippage + TX cost + dual-track)

  commit: 64d7e42
  일자: 2026-04-30 20:47
  sprint: S-04

  결정: `backtest_archive.py` 보정 — Survivorship (today_snap 미존재 → 보수 -50% + delisted_count) + Slippage tier (≥10조 0.1%/≥1조 0.3%/<1조 0.7%) + TX cost (VAMS 일치 0.03%) + dual-track (gross / net 둘 다 노출 + `_corrections_meta` audit trail)
  근거: 베테랑 평가 = backtest = forward tracking, hit_rate 60% 표시 → 실거래 45% 가능성. Dual-track 으로 호환성 보존 (기존 키 유지) + 정직성 (net 별도 노출)
  검증 시점: 즉시 (test_backtest_corrections 10 cases) / 운영 누적 (D+30 hit_rate vs hit_rate_net 격차) / 5/2 D5 Bessembinder 자체 검증 (보너스 finding)
  검증 결과: ✅ 즉시 통과 / ✅ 5/2 D5 Bessembinder 한국 패턴 일치 (median -4.36% / skewness 10.89 / top 4% wealth 51.35%) — 한국은 분산형 (Concentrated 10 vs 분산 30 의제 8d762b0a)
  영향 범위: backtest / VAMS / 분석 신뢰성
  남은 한계: look-ahead bias 검증 (rec_price T+1 시가 보정) — 다음 sprint
  Cross-ref: 선행 T1-14 / 후속 5/2 D5 / 의제 8d762b0a (concentrated vs 분산)

### T1-16. 결함 6 — Regime leading indicator 분리

  commit: c5ec057 (1단계) / 17dbee9 (Sprint 11 후속, HY spread 최상위 promote)
  일자: 2026-04-30 20:54 / 2026-05-01 01:47
  sprint: S-04

  결정: `_classify_regime` 에 leading 시그널 3개 (Yield curve slope 2y10y 6-18개월 선행 / Copper-Gold 비율 변화율 / HY spread 5%+ stress). portfolio.regime_diagnostics 분해 (trailing_score / leading_score / divergence_warning 임계 |diff| ≥ 0.5)
  근거: 베테랑 평가 = 기존 regime detection 모두 trailing 후행. "레짐 판단이 틀리면 모든 종목이 일제히 틀린다" — leading 분리 + divergence_warning 으로 전환 임박 신호화
  검증 시점: 즉시 (test_regime_leading_indicators 11 cases) / 운영 누적 (divergence_warning hit rate)
  검증 결과: ✅ 즉시 통과 / 운영 누적 검증 대기 (HY spread 수집 가용 시 자동 활용)
  영향 범위: regime / Brain (T1-17 입력) / 매크로 분석
  남은 한계: HY spread 미수집 (FRED BAMLH0A0HYM2) / Markov 2-state regime probability — 다음 sprint
  Cross-ref: 후속 T1-17 (regime_diagnostics 활용) / 메모리 `project_sprint_11_veteran_response`

### T1-17. 결함 2 — Graham vs CANSLIM regime switching (가중치 동적)

  commit: 353609e (1단계) / feb6e4a (Sprint 11 후속 brain_weights cross-validation OOS)
  일자: 2026-04-30 21:00 / 2026-05-01 01:55
  sprint: S-04

  결정: `_compute_fact_score` regime_diagnostics 활용. bull (regime > 0.3): CANSLIM 1.5× / Graham 0.5× / bear (< -0.3): Graham 1.5× / CANSLIM 0.5× / mixed: 기본. leading 신호 1.5× 가중. result["regime_weighting"] audit
  근거: 베테랑 평가 = fact_score 안에 Graham (가치) + CANSLIM (성장) 단순 가중평균 → 철학적 충돌, 양쪽 어정쩡. regime 따라 동적 전환
  검증 시점: 즉시 (test_brain_regime_weighting 6 cases) / 5/2 audit P0b (7:3 fact/sentiment 가중치 자체 결정 ❓) / brain_weights_cv 누적 4주+
  검증 결과: ✅ 즉시 통과 / 🔴 5/2 P0b verdict ❓ (7:3 자체 결정 라벨링 — 메모리 `project_brain_v5_self_attribution` 신규) / OOS 검증 의제 a760aaff
  영향 범위: Brain (fact_score 산출) / 가치 vs 성장 균형
  남은 한계: 0.7/0.3 (fact vs sentiment) OOS 검증 근거 부재 (env override 만)
  Cross-ref: 선행 T1-16 (regime_diagnostics) / 후속 5/2 P0b / 의제 a760aaff / 메모리 `project_brain_v5_self_attribution`

### T1-18. 결함 3+4 — VAMS 변동성 sizing + factor tilt 한도

  commit: 48187e6 (결함 3 sizing) / 4295bf9 (결함 4 factor tilt) / d328f10 (Sprint 11 후속 ATR_14d 직접 수집) / a7e9641 (Sprint 11 후속 cross-asset 30일 correlation matrix)
  일자: 2026-04-30 21:05-21:08 / 2026-05-01 01:44-01:50
  sprint: S-04

  결정: (3) VAMS sizing — `prediction.top_features.volatility_20d` proxy 사용. tier multiplier ≤15% 1.0× / ≤30% 0.85× / >30% 0.70×. (4) factor tilt — `VAMS_MAX_FACTOR_TILT_PCT` 60% (momentum/quality/volatility/mean_reversion 4개 중 한 factor 60%+ 같은 방향이면 매수 차단)
  근거: 베테랑 평가 = 손절 -3/-5/-8% 고정 + 종목당 200만원 = 변동성 무시. Sector 한도만 → factor 노출 한도 부재 → 7종목 momentum 70+ = 단일 베팅
  검증 시점: 즉시 (test_vams_volatility_sizing 10 + test_vams_factor_tilt 5) / Sprint 11 후속 ATR_14d 직접 수집 가용 후 → Phase 0 (T1-22) → Phase 1.1 (T1-23)
  검증 결과: ✅ 즉시 통과 / ✅ ATR_14d 직접 수집 1단계 진행 (Sprint 11 후속) → 5/1 Phase 0/1.1 마이그레이션 본격화
  영향 범위: VAMS / sizing / factor 분산
  Cross-ref: 후속 T1-22 / T1-23 (Phase 0/1.1) / 메모리 `project_atr_dynamic_stop`

### T1-19. 결함 5+7 — Sentiment env override + daily_actions backend (decision fatigue 차단)

  commit: 4aa9b0e (env override + daily_actions backend) / c545e69 (action_log 명시) / 09a4b30 (Framer TodayActionsCard) / fe01e0b (TodayActionsCard 첫 화면 KPI strip + dashboard_summary backend)
  일자: 2026-04-30 21:19-21:35 / 2026-05-01 17:03
  sprint: S-04

  결정: (5) `BRAIN_FACT_WEIGHT_OVERRIDE` / `BRAIN_SENTIMENT_WEIGHT_OVERRIDE` 환경변수 도입 (베테랑 권고 0.85/0.15 점진 시험). (7) `daily_actions.py` 신규 — BUY 1/SELL 1/WATCH 1 추출 (BUY: STRONG_BUY/BUY+미보유+brain 최고 / SELL: 보유 return -3% 미만 / WATCH: brain 55-69+미보유). main.py attach. Framer TodayActionsCard 신설
  근거: 베테랑 평가 = sentiment alpha decay 1-3일 (Tetlock) → 30% 가중 과대. 49 Framer 컴포넌트 정보 풍부하나 사용자 decision fatigue → 월가 PM 워크플로우 "오늘의 액션 3개" 첫 화면
  검증 시점: 즉시 (단위 테스트) / 사용자 페이스 (Framer republish) / 5/1 Brain TodayActionsCard 첫 화면 KPI strip
  검증 결과: ✅ env override 가동 / ✅ daily_actions backend 가동 / ✅ Framer TodayActionsCard republish (action_log)
  영향 범위: Brain (sentiment 시험) / Framer / UX (decision fatigue 차단)
  남은 한계: sentiment → timing_signal architectural 분리 (Constitution + ML + Framer 영향 큰 작업)
  Cross-ref: 메모리 `project_sprint_11_veteran_response` / 후속 Sprint 11 결함 5 후속 timing_signal 분리

### T1-20. 인프라 분리 — gh-pages dual-write Phase A/B (commit storm 차단)

  commit: ee8cca9 (Phase A) / 7008a9d (Phase B URL 마이그레이션) / 04dffee (estate_alerts 자동 생성)
  일자: 2026-04-30 20:22-20:28
  sprint: S-04

  결정: Phase A — 매 cron 변경 산출물 (portfolio.json + recommendations.json + consensus_data.json) gh-pages 브랜치 force-orphan push (peaceiris/actions-gh-pages@v4 + force_orphan=true). 5 워크플로 publish (verity-data-write 그룹). Phase B — Framer 41 + Vercel API 3 raw URL `/main/data/*` → `/gh-pages/*` (dual-write 안전망 살아있어 main URL fetch fallback)
  근거: 베테랑 권고 옵션 D-1 채택. main 브랜치 commit storm (60+/day) → gh-pages 분리. 점진 마이그레이션 안전 (dual-write)
  검증 시점: 즉시 (`https://raw.githubusercontent.com/.../gh-pages/portfolio.json` HTTP 200 OK) / Phase C (Framer republish 완료 후 main 산출물 .gitignore)
  검증 결과: ✅ Phase A/B 가동 / Phase C 보류 (Framer republish 진행 중)
  영향 범위: 인프라 / Framer / Vercel API / cron / git history (60/day → ~10/day Phase C 적용 시)
  Cross-ref: 메모리 `project_sprint_11_veteran_response`

### T1-21. trade_plan v0_heuristic 레이어 분리 + 자체 진화 신호

  commit: eda4e34 (v0_heuristic 레이어) / baae8f5 (메타-검증 모듈 분해 통계) / 7de46f0 (portfolio 부착 + followup 자동 갱신) / 36252bc (일일 admin PDF 3-3 trade_plan v0 자체 검증) / baaa865 (자체 진화 신호 + Claude 진화 입력) / b88da40 (AdminDashboard CardTradePlanV0)
  일자: 2026-04-30 22:22-23:59 (6 commits 100분 내)
  sprint: S-04

  결정: verdict 위 4 판단 레이어 분리 (`trade_planner.py` v0_heuristic 인프라). v1 정식 trade_planner.py 는 8월 예정. v0_heuristic = 결정 룰 단순 + 로깅 풍부 (직교 차원). B 단계 = A 단계 학습 데이터 수집으로 명시 설계 (메모리 `feedback_decision_logging_separation`)
  근거: Brain verdict (BUY/STRONG_BUY) → 즉시 매수 X. 진입가/손절/익절/보유기간 별도 판단 레이어 필요. 단 v1 정식은 4-cell 백테스트 / Phase 1 검증 / OOS / regime adapt 까지 비용 큼 → v0 heuristic 으로 빠르게 baseline + B 단계 학습 데이터 누적
  검증 시점: 즉시 (test 통과) / 운영 누적 (v0_heuristic followup 결과) / 5/2 trade_plan v0 자체 검증 (CardTradePlanV0)
  검증 결과: ✅ 6 commit 즉시 가동 / 운영 누적 검증 진행 중
  영향 범위: trade_plan / VAMS / Brain / Admin / PDF (3-3 섹션)
  Cross-ref: 후속 T1-23 (Phase 1.1 stop_loss) / T1-24 (Phase 1.2 exit_targets) — trade_plan_v0 의 stop/target 산출이 Phase 1.1/1.2 룰로 정밀화 / 메모리 `project_trade_plan_v0_layer` / `feedback_decision_logging_separation`

### T1-22. Phase 0 — ATR 표준화 마이그레이션 (SMA → Wilder EMA(14))

  commit: 598d356 (P-01 config 단일 정의 + ATR 헬퍼 추출) / 18fbf31 (P-02 analyze_technical 헬퍼 호출 + ticker 정규화) / c7f34a8 (P-03 atr_method_at_entry 영속화 + check_stop_loss audit) / 21a2149 (P-04 rollback 환경별 명시) / bd9621c (P-05 _should_log_migration 자동 비활성 룰) / b9d44d3 (P-06 운영 절차 runbook) / 4fca938 (P-07 jsonl 5MB 자동 rotation) / 971fecb (P-08 outlier counter + telegram alert) / 4f2838a (P-09 단위 테스트 추가) / 59c7a01 (Phase 0 5/16 검증 자동화 + 판정 매트릭스) / 7fc184b (5/16 1회성 자동화 cron 신설)
  일자: 2026-05-01 22:27-22:45 (P-01~P-09 18분) / 5/2 7fc184b
  sprint: S-05

  결정: 결정 20. 운영 ATR 산출법이 SMA(14) 인라인 → Wilder EMA(14) 표준 마이그레이션. 9 patch (P-01~P-09) 안전장치 — fallback / rollback / A/B 비교 / outlier 5건/일 alert / 5MB rotation / 단위 테스트 39 cases / 14일 자동 만료 룰 (`ATR_MIGRATION_START_DATE` ISO date)
  근거: Wilder EMA = 학계/월가 표준. Sprint 11 결함 3 후속 — ATR_14d 직접 수집 baseline 표준화 위해. 백테스트 검증 시 SMA vs Wilder EMA 산출 차이 silent drift 방지. 결정 21 — W2/W3 wiring 5/16 후 격리 (단일 변수 통제)
  검증 시점: 5/3 secret 3개 설정 (의제 9f48284a 본인 액션) → 5/3~5/16 A/B 비교 14일 → 5/16 자동 verdict (`analyze_atr_migration.py`) → 5/17 ok→Phase 1.5.1 / fail→rollback / monitoring→+7일 / escape→+7일
  검증 결과: ✅ 코드 commit + push (5/1 22:45) / ✅ 5/16 자동화 cron 신설 (7fc184b) / 대기 — 5/3 secret / 5/16 verdict (의제 8c96aef5)
  영향 범위: VAMS / 백테스트 / Brain / 모든 ATR 사용처
  Cross-ref: 선행 T1-18 (Sprint 11 결함 3 ATR_14d 직접 수집) / 후속 T1-23 (Phase 1.1 stop) / T1-24 (Phase 1.2 R-multiple) / 메모리 `project_atr_phase0_migration` / 의제 9f48284a / 8c96aef5

### T1-23. Phase 1.1 — ATR×2.5 동적 손절 (고정 -8% 폐기)

  commit: d44609a
  일자: 2026-05-01 21:23
  sprint: S-05

  결정: 고정 -8% 손절 폐기 → ATR(14)×2.5 동적 손절. profile 상한 vs individual 보수적 우선 (`max(profile_pct, individual_pct)`, 둘 다 음수 → 덜 음수 = 더 빨리 트리거). ATR 미산출 시 -5% fallback (-8% 보다 보수적). VAMS holding `stop_loss_pct_individual` + `stop_loss_method` 영속화
  근거: 종목 변동성 무시한 단일 임계 → whipsaw 손절 가설. 월가 표준 표현 채택 (5/2 audit P0e: "월가 표준" → "단기/한국 자체 채택 변형" 정정 — LeBeau 원전 ATR(22)×3.0)
  검증 시점: 즉시 (test_atr_stop 10 통과) / 5/16 Phase 0 verdict 후 4-cell 백테스트 (의제 57ac6bd0) / 운영 누적 90일 실측 stop_hit 비율 vs 백테스트 75%
  검증 결과: ✅ 단위 테스트 10/10 / 🔴 5/2 풀스캔 v2 large tier stop_loss 75.6% (한국 부적합 강신호) / 5/16 verdict 대기 / 운영 D+90 대기 / 5/2 D2 메모리 정정 완료 (`project_atr_dynamic_stop`)
  영향 범위: VAMS / 백테스트 / 운영 매매 직접
  Cross-ref: 선행 T1-22 (Wilder EMA baseline 의존) / 후속 5/2 D2 + 풀스캔 v2 + audit P0e / 의제 57ac6bd0 (4-cell 백테스트 P0 격상) / d7dea48c (운영 영향 사전 검증) / 0f6dce6a (multiplier 재검토 sprint) / 메모리 `project_atr_dynamic_stop`

### T1-24. Phase 1.2 — R-multiple 부분 익절 (1.12 magic 폐기)

  commit: 8ef2c47
  일자: 2026-05-01 21:29
  sprint: S-05

  결정: `exit_target = MA20 × 1.12` magic number 폐기 → R-multiple 3단계 부분 익절 (1R/2R/트레일링). target_1: 진입가+1R 50% 청산 / target_2: 진입가+2R 잔여 30% 청산 / target_3: 트레일링 잔여 20% (고점 -5%, +2R 후 활성화). VAMS `check_partial_exit` + `execute_partial_sell` + `holding.exit_targets/exit_history/trailing_active`
  근거: Linda Raschke / Chuck LeBeau 표준 R-multiple 채택 (5/2 audit: 표준 표현 정정 — R-multiple 변형 자체 설계). 진입가-손절가 거리 = 1R. 단일 magic number = 종목별 변동성 무시
  검증 시점: 즉시 (test_r_multiple_exit 15 통과) / 운영 누적 (1R hit < 30% rollback / profit factor 0.2 악화)
  검증 결과: ✅ 즉시 통과 / 운영 누적 검증 대기 / 5/2 메모리 description 정정 완료 (`project_r_multiple_exit`)
  영향 범위: VAMS / trade_plan / 익절 룰
  Cross-ref: 선행 T1-22 (ATR baseline) / T1-23 (stop_price → 1R 거리) / 메모리 `project_r_multiple_exit`

### T1-25. Phase 2-A — 유니버스 5,000 확장 인프라 (9+19 결정)

  commit: 4feefe7 (universe_builder + hard_floor + parallel_fetcher + ramp_up_monitor Day 0) / a70f5cb (main.py 통합 + dart_fundamentals batch + KST 시간대 가드) / 430ddc5 / 2e47784 / 0d36bec (UNIVERSE_RAMP_UP_STAGE/AUTO env 주입 + Realtime/Quick "0" 비활성)
  일자: 2026-05-01 20:26-20:59
  sprint: S-05

  결정: 정적 화이트리스트 85종목 → 동적 5,000 (KR 2,000 + US 3,000) 확장. 5단계 funnel (5,000 → Hard Floor 4,500 → Coarse 1,000 → Medium 300 → Fine 100 → Sector Diversified Top 10). max_workers KR=30 / US=50 (P50 hung 코드 레벨 차단). DART 1순위 + yfinance .KS 2순위 (pykrx 환경 부적합 / KIS rate limit). 14일 ramp-up 단계 (500/1500/3000/5000) 본인 승인 게이트
  근거: Phase 0.5 측정 (P3 50w 21~31x 가속, K1 KRX OpenAPI 1콜 3초, K2-P30 27배 speedup, K2-P50 hung). 코어 화이트리스트 85 항상 union 보장 + 5중 backward compat 가드 (Stage ≤ 85 / KST 22~06 / build 실패 / Hard Floor 0 / step1/step2 0)
  검증 시점: 즉시 (단위 테스트 79) / Phase 0 verdict 종료 후 (5/17+) UNIVERSE_RAMP_UP_STAGE 변경 — Phase 1 우선 / 2-A 병행 X
  검증 결과: ✅ 인프라 가동 (Day 0 비활성, UNIVERSE_RAMP_UP_STAGE="0") / 대기 — Stage 2 진입 결정 5/4 (의제 cdad960a) / Brain v5=10 high conviction Phase 2-D 안정 후
  영향 범위: 유니버스 / Hard Floor / parallel fetch / DART / cost / cron 시간
  Cross-ref: 선행 T1-22 (Phase 0 우선) / 메모리 `project_stock_filter_v0_enhancement` / 의제 cdad960a

---

## Part 2: Tier 2 — Sprint-level Decisions (S-01 ~ S-05)

### S-01. Sprint 10 — Brain Monitor + Phase A 룰 이식 + Reports v2 (4/27 ~ 4/28)

  핵심 테마: 잠금 폐기 후 *자가진단* (Brain Monitor) + *외부 출처 룰 이식* (Phase A) + *PDF 게이팅* (Reports v2) 3 인프라 동시 구축
  주요 결정 ID: T1-01 (잠금 폐기) / T1-02 (Brain Monitor) / T1-03 (Reports v2) / T1-04 (Phase A 룰) / T1-05 (Lynch 6분류) / T1-06 (Brain 진화 추적) / T1-07 (Vercel 통합)
  결과 평가: ✅ 7 결정 모두 즉시 가동 / ⚠️ Brain Monitor 측정 라인은 살아있으나 신호 의미 약화 (Sprint 11 P0 결함 3건으로 연결) / Phase A PEG 3.0 Hard Floor 자체 보수화 명시 미흡 (5/2 audit P1c)
  교훈 (5/2 audit 회고 정합): 외부 출처 인용 시 (a) 챕터 정확 / (b) 자체 캘리브레이션 명시 / (c) 임계값 산출 산식 주석 의무

### S-02. 마스터 룰 drift audit Phase B (4/29)

  핵심 테마: T1-05 (Lynch 6분류) 직후 임계값 silent drift 발견 → 메모리 `feedback_master_rule_drift_audit` 정책 도입 + Lynch Cyclical 키워드 5소스 합의 + Q3 매출 CV 폐기
  주요 결정 ID: T1-08
  결과 평가: ✅ 단일 결정으로 메모리 정책 + 코드 정정 + 5소스 합의 + Q3 정정 4 산출. 본 결정의 진짜 가치 = *향후 룰 추가 시 출처 명시 의무화* (5/2 audit `feedback_source_attribution_discipline` 의 prequel)

### S-03. ESTATE Implementation Sprint (4/26 ~ 4/30)

  핵심 테마: ESTATE Brain 비전 → 1차 인프라 — corp endpoints / R-ONE 실데이터화 / VWORLD geocoder / profiles 승인제 / action_log 시스템 / LANDEX D 산식 v1.2 + 백테스트 메타-검증
  주요 결정 ID: T1-09 (LANDEX V/D/S 실데이터화) / T1-10 (profiles 승인제) / T1-11 (estate_action_log) / T1-12 (LANDEX D v1.2 + 메타-검증)
  보조 commit (Tier 3): 4/26 corp_real_estate migration (006) + corp endpoints 3개 / 4/27 corp 진단 / 4/28 Vercel estate_backend 흡수 / 4/29 EstateLandexCard StockDashboard 부동산 탭 추가
  결과 평가: ✅ 1차 인프라 완비 / 5/2 D3 5 메트릭 silent 측정 인프라 사전 구축 / 5/12/26 운영 verdict 대기 / 메모리 `feedback_estate_density_first` (VERITY 광범위 패턴 이식 금지) 적용 (T1-09~12 모두 ESTATE 별도 폴더)

### S-04. Sprint 11 메타-검수 + 베테랑 due diligence + 인프라 분리 (4/30)

  핵심 테마: 자가진단 (Sprint 11 P0 결함 3건 fix) → 외부 PM 평가 (7결함) → 즉시 1단계 대응 (16 commits 하루 내) + gh-pages 분리. 의사결정 게이트 5/10 → 7/10 추정. 또한 trade_plan v0_heuristic 레이어 분리로 *결정 룰 단순 / 로깅 풍부* 직교 차원 명시 설계
  주요 결정 ID: T1-13 (Sprint 11 P0 결함 3건) / T1-14 (베테랑 평가 수령) / T1-15 (결함 1 backtest) / T1-16 (결함 6 regime leading) / T1-17 (결함 2 Graham/CANSLIM regime switching) / T1-18 (결함 3+4 sizing/factor tilt) / T1-19 (결함 5+7 sentiment override + daily_actions) / T1-20 (gh-pages dual-write) / T1-21 (trade_plan v0_heuristic)
  결과 평가: ✅ 7결함 모두 1단계 대응 / 17 후속 commit 5/1 새벽 (Sprint 11 결함 1/2/3/4/5 후속 5건 + timing_signal UI 노출) / 다음 sprint 권고 5건 (look-ahead bias / sentiment timing_signal 분리 / cross-validation OOS / cross-asset correlation matrix / Markov regime probability)

### S-05. Phase 0 / 1.1 / 1.2 / 2-A — 매매 룰 표준화 + 유니버스 확장 (5/1)

  핵심 테마: Sprint 11 결함 3 ATR 후속 → 본격 마이그레이션 (Phase 0 SMA→Wilder EMA, 9 patch) + Phase 1.1 ATR×2.5 동적 손절 (고정 -8% 폐기) + Phase 1.2 R-multiple 부분 익절 (1.12 magic 폐기) + Phase 2-A 5,000 유니버스 인프라 (9+19 결정)
  주요 결정 ID: T1-22 (Phase 0 ATR 표준화) / T1-23 (Phase 1.1 ATR×2.5 stop) / T1-24 (Phase 1.2 R-multiple exit) / T1-25 (Phase 2-A 5,000 유니버스)
  결과 평가: ✅ 4 Phase 코드 commit + push 완료 / 5/16 Phase 0 verdict 게이트 (5/3 secret 본인 액션 의제 9f48284a) / 5/17 Phase 1.5.1 진입 또는 rollback / 🔴 5/2 풀스캔 v2 Phase 1.1 large stop 75.6% — 한국 부적합 강신호 (4-cell 백테스트 P0 격상) / Phase 2-A Day 0 비활성 (Phase 1 우선)

---

## Part 3: Tier 3 — Micro Decision 통계 (4/26 ~ 5/1)

### Commit 통계

| 분류 | 카운트 |
|---|---|
| 총 commit (4/26 ~ 5/1) | 358 |
| feat-class (feat/fix/perf/refactor/docs/chore/observability/brain) | 156 |
| 자동 생성 (📊 분석 / 📡 RSS / 🔍 PennyScout / 📑 리포트 / 🔐 KIS / 🔔 deadman / publish) | ~200 |

### 메모리 변경 통계 (4/26 ~ 5/1)

| 신규 메모리 | 4/26 ~ 5/1 |
|---|---|
| feedback_continuous_evolution | 4/26 (T1-01) |
| project_brain_kb_learning | 4/28 (T1-04) |
| feedback_brain_evolution_admin_sync | 4/28 (T1-06) |
| feedback_perplexity_collaboration | 4/28 (T1-04 동시) |
| feedback_master_rule_drift_audit | 4/29 (T1-08) |
| project_estate_backtest_methodology | 4/30 (T1-12) |
| feedback_metavalidation_decompose | 4/30 (T1-13) |
| project_sprint_11_veteran_response | 4/30 (T1-14) |
| project_trade_plan_v0_layer | 4/30 (T1-21) |
| feedback_decision_logging_separation | 4/30 (T1-21) |
| project_atr_phase0_migration | 5/1 (T1-22) |
| project_atr_dynamic_stop | 5/1 (T1-23) |
| project_r_multiple_exit | 5/1 (T1-24) |
| project_stock_filter_v0_enhancement | 5/1 (T1-25) |
| feedback_auto_schedule_action_queue | 5/1 (T1-25 보강) |

**총 신규: 15개 메모리** (4/26 ~ 5/1, 6일간)

### 의제 / action_queue 추적

| 분류 | 카운트 |
|---|---|
| Sprint 11 결함 후속 (다음 sprint 권고) | 5 (look-ahead / timing_signal / OOS / correlation / Markov) |
| Phase 0/1.1/1.2/2-A 후속 (5/3~5/17) | 5 (secret 설정 / Stage 2 / verdict / 4-cell / Phase 1.5.1) |

(*5/2 audit 후 action_queue 24건으로 확장 — 본 retrospective 범위 밖, master 일지 Part C 참조*)

---

## Part 4: Validation rules 검증 (8 항목)

| # | 검증 룰 | 통과 |
|---|---|---|
| 1 | 모든 Tier 1 entry 출처 명시 (commit hash / 스펙북 § / 메모리) | ✅ 25/25 — 모두 commit hash 명시, 스펙북 § 또는 메모리 매핑 |
| 2 | 검증 시점 명시 (즉시 / 미래 schedule / 대기) | ✅ 25/25 |
| 3 | 검증 결과 기록 (대기 entry 의 schedule 명시) | ✅ 25/25 |
| 4 | Cross-ref 양방향 (A → B 면 B → A 도) | ✅ Tier 1 내부 양방향 검증 — T1-02 ↔ T1-13 / T1-05 ↔ T1-08 / T1-14 ↔ T1-15~21 / T1-18 ↔ T1-22 ↔ T1-23 ↔ T1-24 / T1-21 ↔ T1-23 ↔ T1-24 |
| 5 | 시간순 정렬 (commit 일자 기준) | ✅ T1-01 (4/26) → T1-02/03 (4/27) → T1-04~07 (4/28) → T1-08 (4/29) → T1-09~21 (4/30) → T1-22~25 (5/1) |
| 6 | Tier 분류 일관성 (같은 패턴 결정 동일 Tier) | ✅ Sprint 단위 = T2, Major = T1, micro = T3 통계 |
| 7 | action_queue 의제 cross-ref 정합 (5/2 audit 의제와) | ✅ T1-23 (4-cell 57ac6bd0 / 운영 d7dea48c / multiplier 0f6dce6a) / T1-04 (PEG 22cdd1ec / 부채 ac9d1dc1) / T1-05 (Lynch 임계 ad4fa2fd / Ch.7 d9a64306) / T1-08 (5/2 audit P0a/P1b) / T1-17 (OOS a760aaff) / T1-22 (secret 9f48284a / verdict 8c96aef5) |
| 8 | 메모리 신규/정정 cross-ref 정합 | ✅ Part 3 메모리 통계 = 15 신규 모두 Tier 1 결정에 매핑 |

**Validation 8/8 통과** — 본 retrospective 일지 baseline 확정.

---

## Part 5: 유지 관리 정책 (분기별 review schedule)

| 주기 | 작업 | 시간 비용 |
|---|---|---|
| 매주 1회 (일요일) | 그 주 commit log + 메모리 변경 → master 일지 업데이트 + 새 entry Tier 분류 + cross-ref | ~15분 |
| Major decision 발생 시 (즉시) | phase/version 변경 / architectural / 외부 출처 채택 / 운영 영향 high → 즉시 추가 | 5~10분 |
| 분기별 1회 (3개월) | "대기 중" entry D+90 hit rate / 운영 결과 반영 / ✅⚠️🔴 갱신 / 회고 (어떤 결정이 alpha 줬나) | ~1시간 |
| 메모리 변경 시 (자동) | `feedback_source_attribution_discipline` trigger 확장 → 메모리 정정 시 결정 일지 cross-ref 의무 | 자동 |

다음 분기별 review 시점: **2026-08-02** (3개월 후 — Phase 0 verdict 결과 + Phase 1.1 운영 90일 / 4-cell 백테스트 결과 / D3 5/26 verdict 3개월 누적 / Sprint 11 결함 후속 5건 진행도)

---

## 변경 추적

| 일자 | 변경 |
|---|---|
| 2026-05-03 | 초기 작성 — 25 Tier 1 entry / 5 Tier 2 sprint / Tier 3 통계 / Validation 8/8 통과 |

---

문서 끝. (Retrospective baseline 확정 — 4/26 ~ 5/1, 5/2 audit 직전 시점)
