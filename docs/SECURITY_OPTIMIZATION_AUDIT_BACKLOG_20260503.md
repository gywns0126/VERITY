# 보안 + 최적화 Audit 의제 후보 Backlog

**작성**: 2026-05-03 02:00 KST (Round 5 후속 — 의제 후보 목록만)
**실행 시점**: 다음 세션 fresh eye 후 결정 (옵션 A / B / C)
**상태**: **실행 X — 의제 후보 list 만**
**참조**: `docs/SILENT_ERRORS_20260502.md` (silent issue 패턴 학습) / `docs/NEXT_SESSION_FIRST_TASK.md`

---

## 0. 본 backlog 의 목적

5/2 ~ 5/3 새벽 세션에서 silent error 5건 발견 (Phase 1.1 ATR / sector NULL / VAMS sector_div / Hard Floor / vams.total_value=0). *동일 패턴* — 보안 / 최적화 영역에도 silent issue 가능성. 단 *시급도* 는 영역마다 다름.

다음 세션에서 fresh eye 로 *진입 옵션* 결정 (즉시 audit / 정정 sprint 통합 / 보류).

---

## 1. 보안 audit 의제 후보 (총 11건)

### P1 (즉시 검토 권장) — 4건

| # | 의제 | 위험 영역 | 검증 방법 |
|---|---|---|---|
| 1 | Supabase RLS 정책 점검 | estate_alerts / user_action_queue / portfolio_data 테이블 RLS USING 정책 | `feedback_supabase_rls_no_self_subquery` 정합 검증 (재귀 EXISTS 잔존 X) + is_caller_admin 함수 권한 적정성 |
| 2 | API key 환경변수 관리 | .env / GitHub secrets / Vercel env 분포 | `gh secret list` + `vercel env ls` + `.env.example` vs `.env` diff |
| 3 | KIS 실거래 API 권한 격리 | 실거래 활성 여부 + 권한 범위 | `KIS_OPENAPI_BASE_URL` (모의 vs 실거래) + `auto_trader.py` 활성 검증 + 계좌 권한 조회 |
| 4 | DART rate limit 가드 | Phase 2-A 5,000 universe 진입 시 1만/일 한도 임박 | `api/collectors/dart_fundamentals.py` rate limit + `T1-25 Phase 2-A` ramp-up 시 호출 빈도 추정 |

### P2 (정기 점검) — 4건

| # | 의제 | 위험 영역 |
|---|---|---|
| 5 | Telegram bot token 회전 정책 | bot token 노출 시 알림 spoofing |
| 6 | Vercel API endpoint auth 검증 | `vercel-api/api/*.py` 21 함수의 admin token / cors 정책 |
| 7 | GitHub Actions secrets 권한 최소화 | secret 별 사용 workflow 분포 + 최소 권한 원칙 |
| 8 | Framer 컴포넌트 인증 우회 점검 | apiBaseUrl prop 변조 / X-Admin-Token 클라이언트 노출 |

### P3 (보류 가능) — 3건

| # | 의제 | 검증 방법 |
|---|---|---|
| 9 | 라이브러리 취약점 정기 audit | `npm audit` (Framer) + `pip-audit` (Python) |
| 10 | 로그에 민감 정보 leak 점검 | `data/metadata/*.jsonl` + `data/portfolio.json` 의 KIS account / token 등 leak 검증 |
| 11 | gh-pages public 노출 검증 | gh-pages 브랜치의 portfolio.json 에 민감 정보 없는지 확인 |

---

## 2. 최적화 audit 의제 후보 (총 9건)

### P1 (즉시 검토 권장) — 2건

| # | 의제 | 검증 방법 |
|---|---|---|
| 1 | DART rate limit 1만/일 vs Phase 2-A 5,000 종목 (gap 분석) | dart_fundamentals 5,000 호출 / 일 추정 vs 1만 한도 — gap 5,000 (50%) — Phase 2-A Stage 4 (5,000) 진입 시 critical |
| 2 | cron 30분 timeout 실측 (현재 평균 / 최대) | `gh run list --limit 50 --json databaseId,conclusion,createdAt,updatedAt` 분석 → 30분 임계 도달 빈도 |

### P2 (정기 점검) — 4건

| # | 의제 | 검증 방법 |
|---|---|---|
| 3 | 메모리 누수 점검 (cron 매일 누적) | `data/metadata/*.jsonl` size 추세 + portfolio.json size 추세 |
| 4 | KRX OpenAPI rate limit 가드 | `api/collectors/krx_openapi.py` 호출 빈도 + KRX 한도 검증 |
| 5 | portfolio.json 사이즈 추적 (현재 vs 6개월 후 추정) | 현재 ~1.9MB → Phase 2-A 5,000 universe 진입 시 추정 ~5~10MB? |
| 6 | parallel_fetcher 효율 측정 (KR P30 / US P50 vs 실측) | T1-25 Phase 0.5 측정 (P3 50w 21~31x 가속) baseline vs 운영 누적 비교 |

### P3 (보류 가능) — 3건

| # | 의제 | 검증 방법 |
|---|---|---|
| 7 | Vercel cold start 측정 | 21 함수의 cold start 시간 측정 |
| 8 | DB query N+1 점검 | Supabase 쿼리 패턴 분석 |
| 9 | Framer bundle size 점검 | 41 컴포넌트 bundle size + lazy loading 가능성 |

---

## 3. 통합 진입 옵션 (다음 세션 fresh eye 결정)

### 옵션 A: 별도 sprint (1~2일)

- 다음 세션 둘째 작업 (Supabase 등록 + sed replace 후)
- retrospective + Supabase 등록 → 보안 P1 audit + 최적화 P1 audit (~3시간)
- 결과: 보안/최적화 baseline 확정 (5/17 sprint 진입 전)
- 비용: 다음 세션 시간 ↑ / 5/17 sprint 진입 지연

### 옵션 B: 5/17 정정 sprint 통합 (Day 8~10)

- 정정 sprint 내 일부로 진행 (sector / Phase 1.1 sprint 와 같은 시기)
- 결과: 모든 baseline 동시 확정 (시너지)
- 비용: 5/17 sprint 작업량 ↑ (~2시간) / 단일 변수 통제 위반 위험 mid

### 옵션 C: 보류 (P1 만 즉시, P2/P3 는 운영 누적 후)

- P1 항목만 즉시 점검 (보안 4건 + 최적화 2건 = ~30분)
- P2/P3 는 운영 데이터 누적 후 (3개월 ~ 6개월)
- 결과: 시급도 정합 / 비용 최소
- 비용: P2/P3 silent issue 발견 지연

### 베테랑 권장: **옵션 C (P1 즉시 + P2/P3 보류)**

이유:
- 5/17 정정 sprint 가 이미 5건 (hotfix + sector + Phase 1.1 + audit Step 4 + KIS backfill) → 추가 작업 시 단일 변수 통제 위반 위험 ↑
- 보안 P1 4건 + 최적화 P1 2건 = 6건은 *비용 작음 + 위험 큼* (DART rate limit 은 Phase 2-A Stage 4 직전 critical)
- P2/P3 = 운영 누적 후 silent issue 패턴 발현 시 진단 (5/2 audit 모델 정합)

---

## 4. 우선순위 종합 (5/2 audit 후속 정합)

오늘 silent error 5건 발견 패턴 = 보안/최적화에도 *동일 silent issue* 가능성. 단 시급도는 운영 영향 따라 다름:

| 영역 | 시급도 | 운영 영향 |
|---|---|---|
| 운영 데이터 결함 (Error 5) | 🔴 | primary trigger 작동 X = 자본 진화 컨셉 자체 무효 |
| 보안 결함 | 🟡 | 외부 위협 + 사용자 1~3명 (제한적 시장 임팩트) |
| 최적화 결함 | 🟢 | 비용 + 부하 + 사용자 1~3명 (성장 시 critical) |

**최종 우선순위** (다음 세션 결정 baseline):

1. 🔴 **5/17 정정 sprint** (silent error 5건) — 의무
2. 🟡 **보안 P1 audit** (4건, ~30분) — 옵션 C 권장
3. 🟢 **최적화 P1 audit** (2건, ~20분) — 옵션 C 권장
4. ⚪ **보안 P2/P3** (7건) — 운영 누적 후
5. ⚪ **최적화 P2/P3** (7건) — 운영 누적 후

---

## 5. 연관 silent issue 의심 영역 (5/2 audit 패턴 적용)

본 backlog 의 의제 중 *silent issue 패턴 의심* 영역 (다음 audit 시 우선 점검):

| 의제 | silent issue 의심 사유 |
|---|---|
| 보안 P1-1 (Supabase RLS) | `feedback_supabase_rls_no_self_subquery` 정합 검증 부재 — 신규 테이블 (estate_alerts / user_action_queue) 의 RLS 정책 silent gap 가능 |
| 보안 P1-2 (API key 분포) | env 분포 silent drift — `gh secret` vs `.env.example` vs `vercel env` 차이 silent |
| 보안 P1-4 (DART rate limit) | Phase 2-A 진입 후 1만/일 임박 — silent throttle 가능 |
| 최적화 P1-1 (DART rate gap) | 위와 동일 — 같은 root cause |
| 최적화 P1-2 (cron timeout) | 30분 임계 silent 도달 (Actions 자동 fail 시 silent) |

---

## 6. 본 backlog 와 5/17 정정 sprint 의 의존성

| 5/17 정정 sprint | 본 backlog 영향 |
|---|---|
| c5e8f9a2 hotfix | 보안 무관 / 최적화 P3-1 (DB query) 영향 가능 |
| SECTOR_PROPAGATION | 보안 P1-1 (RLS) 일부 영향 (universe builder 권한) / 최적화 P1-1 (DART rate) 직접 영향 |
| PHASE_1_1_RECONSIDERATION | 보안 무관 / 최적화 P2-3 (portfolio.json size) 일부 영향 |
| capital_evolution_monitor | 보안 무관 / 최적화 P3-1 (DB query) 영향 가능 |
| AUDIT_STEP_4_P1_CORRECTION | 무관 (메모리 정정 only) |

→ **SECTOR_PROPAGATION 과 보안 P1-1 + 최적화 P1-1 통합 가능** (옵션 B 의 시너지 영역).

---

## 7. 진입 시 작업 순서 (옵션 C 진입 시 권장)

다음 세션 흐름:

1. **STEP -1** (Supabase UUID 매핑 정정) — `docs/NEXT_SESSION_FIRST_TASK.md`
2. **STEP 0** (큐 + 운영 데이터 확인) — `project_next_session_kickoff` STEP 0
3. **(옵션 C 진입 시)** 보안 P1 4건 + 최적화 P1 2건 audit (~50분)
4. **(P1 결과)** silent issue 발견 시 → 신규 의제 등록 (Supabase) + 5/17 sprint 통합 검토 / 발견 X 시 → P2/P3 보류 확정
5. STEP 1 큐 내 우선순위 작업 진입

---

## 8. 변경 추적

| 일자 | 변경 |
|---|---|
| 2026-05-03 02:00 KST | 초기 작성 — 보안 11건 + 최적화 9건 의제 후보 + 진입 옵션 A/B/C + 베테랑 권장 (옵션 C) |

---

## 9. 학습 사례 cross-ref

본 backlog 작성 자체가 학습 사례 적용:

→ `feedback_source_attribution_discipline` 6번째 학습 사례 ("데이터 layer 결함 → 의사결정 layer 자체 작동 불가") *역방향 적용*: 보안/최적화 결함도 *시스템 작동* 영향 가능 → 운영 누적 전 audit baseline 확보 의무

→ 본 backlog = audit baseline 확정 *후보 목록*. 실행은 다음 세션 fresh eye 후 결정.

---

문서 끝.
