# VERITY ESTATE — 구현 태스크 계획서

**최초 일자:** 2026-04-26 · **최근 갱신:** 2026-04-30  
**스택:** Framer (React/TS) · Vercel Python 3.12 · Supabase · GitHub Actions

### 진행 현황 요약 (2026-04-30 기준)

| Task | 상태 | 비고 |
|------|------|------|
| 1. 시계열 스파크라인 | ✅ 완료 (4/30) | history → **timeseries** 로 명칭 변경, snapshot → **R-ONE 직접 호출** |
| 2. 마켓 레짐 프리셋 + 자동 전환 | 🟡 부분 | 프리셋 6개 정의 완료, `CURRENT_REGIME` 수동 갱신 중. 자동 detection 은 v1.5 |
| 3. 내러티브 (Anthropic) | ✅ 완료 | `landex_narrative.py` |
| 4. 소프트 페이월 (Pro) | ❌ 미구현 | `MaskedValue.locked` 적용 사례 없음 |
| 5. 주간 다이제스트 (Resend) | ❌ 미구현 | `weekly_digest.yml` 미생성. `digest_publish_readiness.py` 만 존재 (publishing readiness 체크용) |

**4/26 → 4/30 추가 발생 사항** (계획 외)
- LANDEX D 산식 v1.1 → **v1.2**: 윈도우 12주 → 26주, balanced 가중치 D 0.20→0.15 (시점 민감도 보정)
- LANDEX **백테스트 메타-검증** 인프라 (commit `17dc386`) — 5/5 화 첫 cron 결과 예정
- R-ONE env 통합 — `R_ONE_API_KEY`(Vercel) + `REB_API_KEY`(GitHub Actions) 둘 다 fallback

---

## Task 1 — 시계열 스파크라인 (단기 최고 ROI) — ✅ 완료 (2026-04-30, commit `b234853`)

### 실제 구현
- 신규: `vercel-api/api/landex_timeseries.py` (계획 `landex_history.py` 에서 명칭 변경)
- 수정: `vercel-api/vercel.json` — `/api/landex/timeseries` 리라이트, `maxDuration: 15s`
- 수정: `배리티 에스테이트/components/pages/ScoreDetailPanel.tsx` — `TimeSeriesCard` 추가 (인라인 SVG sparkline 2개)
- 신규: `tests/test_landex_timeseries.py` (10건, 전체 54건 통과)

### 계획과의 차이 + 사유
| 계획 (4/26) | 실제 (4/30) | 사유 |
|---|---|---|
| `estate_landex_snapshots` 에서 LANDEX 시계열 | **R-ONE 어댑터 직접 호출** (가격지수 + 미분양) | snapshot 은 점수 한 점만 저장 → 진짜 *시계열 깊이* 는 raw R-ONE. 산식 변경 0 |
| 6개월 스파크라인 + 델타 | **52주(가격지수) + 24개월(미분양)** | R-ONE 가용 lookback 길게 활용 — 사이클 1회분 |
| mock fallback | **fail-closed (503/404)** | 가짜 데이터 sparkline 은 오해 유발 — 메모리 `feedback_ai_fallback_sanitization` 정신 |
| Supabase 응답 정렬 등 테스트 | 핸들러 + lib 함수 10건 (mock R-ONE 응답) | snapshot 의존 제거에 따라 |

### API
- `GET /api/landex/timeseries?gu=강남구&metric=price_index&weeks=52`
- `GET /api/landex/timeseries?gu=강남구&metric=unsold&months=24`
- 응답: `{version, gu, metric, series:[{x,y,date}], as_of, collected_at, source, count}`
- 캐시: `Cache-Control: public, max-age=3600` (R-ONE 갱신 주기 = 주/월)

### 잔여 리스크
- 미분양 시계열 절대값이 25구 대부분 0 → sparkline 의미 적은 구 다수. 추세 변곡 발생 시 가시화 (현재 우선순위 X)
- D 산식 v1.2 + 메타-검증 결과(5/5) 본 후 `metric=accel` (D 가속도 노출) 추가 검토 가능

---

## Task 2 — 마켓 레짐 프리셋 + 자동 전환 — 🟡 부분 완료

### 완료
- ✅ `vercel-api/api/landex/_methodology.py` — `WEIGHT_PRESETS` 6개 정의
  - balanced v1.2 (4/30 갱신: V 0.32 / D 0.15 / S 0.18 / C 0.20 / R 0.15)
  - growth · value · tightening · redevelopment_boom · supply_shock
- ✅ `CURRENT_REGIME` 수동 라벨 — `tightening` since 2026-04 (next review 5/28 신임 총재 첫 금통위)

### 미구현
- ❌ `api/landex/_regime.py` — 자동 `detect_regime()` 함수 (ECOS 기준금리 + estate_alerts 30일 윈도우 집계)
- ❌ `vercel-api/api/landex_regime.py` 엔드포인트 (`GET /api/landex/regime`)

### 메모
- _methodology.py 주석에 "자동 MRS 는 v1.5" 명시 — Task 2 자동 전환은 v1.5 로 미룸이 현재 결정
- 5/5 메타-검증 결과 본 뒤 D 산식 안정성 확인되면 그때 `_regime.py` 검토

### 리스크
- ECOS/알림 실패 시 `balanced` 편향, `estate_alerts` 전역 집계·RLS·service_role 설계

---

## Task 3 — 내러티브 (Anthropic) — ✅ 완료

### 산출물
- ✅ `vercel-api/api/landex_narrative.py` 존재
- ✅ `vercel.json` 에 `/api/landex/narrative` 리라이트 등록 (`maxDuration: 5s`)
- ScoreDetailPanel `fetchDetail` 에서 features/scores 와 병렬 호출 (`Promise.all`) — 실패해도 mock fallback 으로 scores 는 살림

### 리스크
- Vercel 타임아웃(일괄 25구는 GHA/스냅샷 측), JSONB merge race

---

## Task 4 — 소프트 페이월 (Pro) — ❌ 미구현

### 현재
- `components/atomic/MaskedValue.tsx` 존재 (Privacy Mode 마스킹 — L0/L1/L2/L3 sensitivity 기반)
- 그러나 *Pro 등급 게이팅* 적용 사례 없음 (`MaskedValue.locked` prop 미구현)
- `profiles.tier` 컬럼 + JWT 5분 캐시 API 미구현

### 메모
- ESTATE 사이트는 현재 *비공개 테스트* 단계 (memory `feedback_scope`: "검증 전 종목 추천 콘텐츠 금지")
- Pro 페이월은 운영 시작 후 검토 — 우선순위 낮음

### 리스크
- 클라만 제한 시 우회; 진짜 제한은 API 스코프 조정

---

## Task 5 — 주간 다이제스트 (Resend) — ❌ 미구현

### 현재
- ❌ `.github/workflows/weekly_digest.yml` 미생성
- 부분 인프라: `vercel-api/api/digest_publish_readiness.py` (다이제스트 *발행 준비도* 체크용 — 별개)
- `DigestPublishPanel.tsx` (배리티 에스테이트/components/pages) 존재하지만 백엔드 실데이터 wiring 미완 (action_log pending)

### 선결 조건
- ESTATE 운영 누적 N주 데이터 필요 (사이클 비교용)
- `estate_digest_subscribers` 테이블 + RLS + PIPA 수신거부 URL
- Resend 도메인 검증

### 리스크
- GHA 시크릿, Resend 도메인, 스냅샷 전후 비교 결측

---

## 권장 구현 순서 (4/30 갱신)

**완료**
1. ~~Task 1~~ ✅ 시계열 스파크라인 (4/30)
2. ~~Task 3~~ ✅ 내러티브 (이미 박혀있던 자산)
3. ~~Task 2 (프리셋)~~ ✅ WEIGHT_PRESETS 6개 + CURRENT_REGIME 수동

**다음 우선순위**
1. **5/5 LANDEX 메타-검증 cron 첫 결과 확인** (action_log pending) — D 산식 v1.2 안정성 판정
2. ESTATE Brain 로드맵 다음 단계: **단지 drill-down** (memory `project_estate_brain_kickoff` 우선순위 — 백테스트 → 시계열 깊이 ✅ → **단지 drill-down** → ...)
3. (메타-검증 안정 확인 후) Task 2 자동 `detect_regime()` — ECOS + alerts 시그널 융합
4. (운영 누적 N주 후) Task 5 weekly digest

**미루는 것**
- Task 4 (소프트 페이월) — 운영 시작 후 재검토, 현재 *비공개 테스트* 단계
- 자동 MRS — v1.5 (현재 v1.2)

---

## 부록 — 4/26 → 4/30 변경 사항 시간선

| 일자 | 변경 | 커밋 |
|------|------|------|
| 4/29 | R-ONE 어댑터 실측 사양 확정 (CLS_ID 매핑·DTACYCLE_CD `WK`·STATBL_ID T+13자리) | `2ccfbbe` |
| 4/30 | LANDEX D 산식 **v1.1** — 윈도우 12주→26주, cap ±0.5%p→±2.0%p (메타-검증 결과 기반) | (squash) |
| 4/30 | LANDEX **v1.2** — balanced 가중치 D 0.20→0.15 + d_high_volatility 플래그 | `17dc386` |
| 4/30 | drift cry-wolf 완화 + extract grade 위치 + jsonl 정리 | `a0fac4c` |
| 4/30 | **LANDEX timeseries API + sparkline UI** + R-ONE env 통합 | `b234853` |

---

*본 문서는 IDE 계획 응답을 바탕으로 정리한 작업용 요약입니다. 4/30 갱신은 Claude 가 현재 코드 상태 확인 후 정합성 맞춤.*
