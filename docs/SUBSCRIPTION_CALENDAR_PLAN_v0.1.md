# SubscriptionCalendar Plan v0.1

ESTATE Tier 2 / D — 분양 캘린더 (2026-05-12 박음).

## 1. 책임 분리 (overlap audit)

| 컴포넌트 | 시간 | 데이터 | 책임 |
|---|---|---|---|
| HeroBriefing | 24h | 정책 1건 | "지금 무엇이 일어났나" |
| ChangeFeed | 72h | 정책 N=10 | "최근 변동 항목" |
| PolicyShockTimeline | 30~90d 과거 | 정책 누적 + impact_score | "과거 정책 충격이 어떻게 누적되나" |
| **SubscriptionCalendar** | **30d 과거 ~ 365d 미래** | **청약공고 + 5종 event** | **"미래 공급 충격이 언제 일어나는가"** |

PolicyShock 와 직교 페어:
- PolicyShock = 과거 정책 충격 누적 (시그널 누적)
- SubscriptionCalendar = 미래 공급 충격 예정 (시그널 선행)
- 둘 다 LANDEX 가격 변동 분석 input

## 2. 데이터 흐름

```
data.go.kr 15098547 (한국부동산원 청약홈 분양정보)
  endpoint: api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail
  인증: env PUBLIC_DATA_API_KEY (policy_collector v2 와 동일 키)
    │
    ▼
api/collectors/subscription_collector.py
  • cond[RCRIT_PBLANC_DE::GTE] 윈도우 필터
  • perPage 500 paging
  • T1/T9 정합 (실패 시 [] + log)
    │
    ▼
api/builders/estate_subscription_calendar_builder.py
  row 1건 → 5종 event 분해:
    recruit       RCRIT_PBLANC_DE
    application   RCEPT_BGNDE ~ RCEPT_ENDDE
    announcement  PRZWNER_PRESNATN_DE
    contract      CNTRCT_CNCLS_BGNDE ~ CNTRCT_CNCLS_ENDDE
    move_in       MVN_PREARNGE_YM (YYYYMM → 그 달 1일)
  + by_month / by_region 집계
  + upcoming_high_impact (향후 30d + recruit + ≥1000세대)
    │
    ▼ (publish-data action staging — 파일 목록 추가됨)
gh-pages /data/estate_subscription_calendar.json
    │
    ▼ (vercel-api read-through)
GET /api/estate/subscription-calendar
    │
    ▼
estate/components/pages/_shared/SubscriptionCalendar.tsx
```

## 3. 5종 event 분해 사유

캘린더 시각화는 "오늘 무엇이 일어나는가" 가 핵심. 한 분양이 모집~입주까지
1~2년 늘어지므로 row-as-event (단일 dot) 으론 의미 부족.

5 dot 분해 = 시간축 위 사용자 의사결정 게이트와 정합:

| event | 의사결정 게이트 |
|---|---|
| recruit (모집공고) | "지금 공고 났는가" (입찰 의향 형성) |
| application (청약접수) | "지금 접수 받는가" (구매 결정 시간 압축) |
| announcement (당첨자발표) | "당첨/탈락 결과 언제" (소유권 분기) |
| contract (계약체결) | "계약 데드라인" (현금 흐름 trigger) |
| move_in (입주예정) | "공급 충격 시점" (LANDEX 가격 reaction 시작점) |

magnitude / 가중치 v0 박지 않음 — 단순 timeline. PolicyShock 처럼 산식 박기 전에
운영 데이터 누적 후 결정 ([[feedback_estate_density_first]] 정합).

## 4. high-impact 임계 (자체 v0)

```
upcoming_high_impact 진입 조건:
    event_type == "recruit"
    AND today ≤ date_start ≤ today + 30d
    AND TOT_SUPLY_HSHLDCO ≥ 1000
```

사유: 1000세대 = LANDEX 자치구 가격 변동에 통계적 영향 가능한 규모 (자체 추정, v0).
운영 누적 후 임계 retract 검토 ([[feedback_spec_iteration_retract_rule]] 정합).

## 5. 운영 정책

- cron: 평일 KST 10:30 (hero 09:00 / change_feed 09:30 / policy_shock 10:00 다음 +30분 시차)
- concurrency group: `estate-subscription-calendar`
- 빌더는 자기 산출물을 main commit ([[project_gh_pages_disabled]] 정합)
- publish-data action staging 에 `estate_subscription_calendar.json` 추가
- maxDuration: 5s (read-through endpoint)
- cache: 300s public

## 6. 입력 게이트 (활용신청 필수)

`PUBLIC_DATA_API_KEY` 는 이미 등록되어 있음 (policy_collector v2 사용 중).
그러나 동일 키로도 **서비스별 활용신청 필요**. data.go.kr 15098547 활용신청은
user 액션 (user_action_queue 큐잉됨).

미신청 상태에서 cron 발화 시:
- collector → 503 또는 인증 오류
- 명시 로그 + events=[] 반환 ([[feedback_data_collection_verification_mandatory]] silent skip X)
- 컴포넌트는 "선택한 윈도우에 일정 없음" 표기

활용신청 후 다음 cron (또는 workflow_dispatch) 발화 = 데이터 수집 시작.

## 7. 컴포넌트 (SubscriptionCalendar.tsx)

위치: `estate/components/pages/_shared/`. PolicyShockTimeline 과 같은 _shared.

UI 구성 (밀도 우선):
- HEADER: `SUBSCRIPTION · {window_label}` + 갱신시각 + 일정/공고 카운트
- FILTERS (in-component selector):
  - 기간 (이번 달 / 3개월 / 6개월 / 1년)
  - 지역 셀렉트 (by_region 기준 정렬)
  - 이벤트 종류 chip (5종 토글)
- MONTH STRIP: 월별 막대 (height = count, color = accent gold)
- HIGH IMPACT 카드: 향후 30d + ≥1000세대 recruit 상위 3건. 투기과열지구 빨강 표시
- EVENT LIST: 날짜 + 종류 + 단지명 + 지역. 50건 cap (밀도 + 가독성)

디자인 토큰: ESTATE v1.1 패밀리룩 ([[feedback_estate_design_familylook]] 정합).

## 8. 변경 파일 (v0.1)

- `api/collectors/subscription_collector.py` (new)
- `api/builders/estate_subscription_calendar_builder.py` (new)
- `vercel-api/api/estate_subscription_calendar.py` (new)
- `vercel-api/vercel.json` (functions + rewrites 1행씩 추가)
- `estate/components/pages/_shared/SubscriptionCalendar.tsx` (new)
- `.github/workflows/estate_subscription_calendar.yml` (new)
- `.github/actions/publish-data/action.yml` (staging 목록에 1 파일 추가)
- `tests/test_subscription_collector.py` (new, 5 tests)
- `tests/test_estate_subscription_calendar_builder.py` (new, 9 tests)
- `docs/SUBSCRIPTION_CALENDAR_PLAN_v0.1.md` (this)

## 9. 다음 단계 (큐잉)

- **user_action**: data.go.kr 15098547 활용신청 (user_action_queue 박힘)
- env `ESTATE_SUBSCRIPTION_CALENDAR_SOURCE_URL` Vercel 등록 (gh-pages JSON URL)
- 첫 cron 발화 후 응답 schema 실측 검증 ([[feedback_real_call_over_llm_consensus]])
- 응답에 누락 컬럼 있으면 builder 정합 보강
- 30d 운영 후: high-impact 임계 1000세대 retract 검토
- v1 큐잉: 청약경쟁률 API (15098905) 연동 — recruit event 에 경쟁률 metadata 추가
