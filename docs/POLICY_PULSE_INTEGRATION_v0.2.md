# PolicyPulse Integration v0.2

3 → 1 정책 컴포넌트 통합 (2026-05-12 박음).

## 1. 사용자 결정

> "지금까지 총 4개 컴포넌트가 나왔는데, 이거 합칠 수 있는건 합쳐."

4 = HeroBriefing / ChangeFeed / PolicyShockTimeline / SubscriptionCalendar.

## 2. Audit 결과 (feedback_component_overlap_audit 정합)

| 컴포넌트 | 데이터 소스 | 도메인 | 시간 깊이 | 책임 |
|---|---|---|---|---|
| HeroBriefing | data.go.kr 1371000 (정책) | 정책 | 24h(→72h→LANDEX) | highlight 1건 |
| ChangeFeed | data.go.kr 1371000 (정책) | 정책 | 72h | N=10 리스트 |
| PolicyShockTimeline | data.go.kr 1371000 (정책) | 정책 | 30~90d | 시간축 + impact |
| SubscriptionCalendar | data.go.kr 15098547 (분양) | 분양 | -30d ~ +365d | 5 event 캘린더 |

- 정책 3 = 같은 데이터 소스 + 같은 도메인. 시간 깊이만 다름 → **통합 가능**.
- 분양 1 = 다른 데이터 소스 + 다른 도메인 → **분리 유지**.

**결과**: 4 → 2 (PolicyPulse + SubscriptionCalendar).

## 3. 통합 컴포넌트: PolicyPulse

위치: `estate/components/pages/_shared/PolicyPulse.tsx`

```
┌──────────────────────────────────────────────────┐
│ POLICY PULSE · 갱신 {time}                       │
│ 정책 통합 모니터  24h 1건 · 30d 누적 · 72h 변동  │
├──────────────────────────────────────────────────┤
│ HIGHLIGHT · 24H                                  │
│ ┌──────────────────────────────────────────────┐│
│ │ [출처] · 발표시각                            ││
│ │ 정책 제목                                    ││
│ │ "AI 한줄평"                                  ││
│ └──────────────────────────────────────────────┘│
├──────────────────────────────────────────────────┤
│ SHOCK · 30D    [기간▾][전체/규제/호재/중립]      │
│ ━●━━●━●━━━●━━●━━━━━●━━●━━━●━━(strip)            │
│ HOVER detail (카테고리·stage·impact·제목)        │
│ ▁▃█▆▂▁ (by_day max impact 막대)                  │
│ [규제 N][호재 N][중립 N][max X.XX][mean X.XX]    │
├──────────────────────────────────────────────────┤
│ RECENT · 72H    [전체/규제/호재]                 │
│ ● 규제  공시가격 인상 발표              · 서울  │
│ ● 호재  3기 신도시 추가 지정            · 경기  │
│ ● 규제  대출 한도 축소 검토             · 전국  │
│ ● 호재  GTX-B 노선 확정                · 인천  │
│ ● 규제  보유세 강화 시행령              · 전국  │
└──────────────────────────────────────────────────┘
```

## 4. Backend 분리 보존 (feedback_simple_front_monster_back 정합)

3 endpoint / 3 builder / 3 cron 그대로 유지:
- `/api/estate/hero-briefing` ← `estate_hero_briefing_builder` (cron 09:00)
- `/api/estate/change-feed` ← `estate_change_feed_builder` (cron 09:30)
- `/api/estate/policy-shock` ← `estate_policy_shock_builder` (cron 10:00) + `estate_policy_archive_builder`

PolicyPulse 는 3 endpoint **병렬 fetch** (Promise.all). 각 cache 300s 라 동시 부하 ↓.
한 부분 실패해도 다른 섹션 정상 노출 ([[feedback_data_collection_verification_mandatory]] 정합 —
명시 로그 + Placeholder 카드).

**monster back / simple front**:
- backend = 3 endpoint, 정밀 분리 (각자 책임)
- frontend = 1 컴포넌트, 통합 화면 (사용자 단순)

## 5. 삭제 파일

- ~~`estate/components/pages/home/HeroBriefing.tsx`~~ → PolicyPulse 가 흡수
- ~~`estate/components/pages/home/ChangeFeed.tsx`~~ → PolicyPulse 가 흡수
- ~~`estate/components/pages/_shared/PolicyShockTimeline.tsx`~~ → PolicyPulse 가 흡수

빌더·endpoint·테스트·plan 문서 (HERO/CHANGEFEED/POLICY_SHOCK_TIMELINE_PLAN_v0.1.md) 는 모두 유지.

## 6. 사용자 액션 (Framer 페이지 교체)

`user_action_queue` 박힘:
- 기존 HeroBriefing / ChangeFeed / PolicyShockTimeline 사용하던 Framer 페이지에서
  `PolicyPulse` 로 swap. estate/components/pages/_shared/PolicyPulse.tsx 코드 paste.

## 7. 변경 파일

신규:
- `estate/components/pages/_shared/PolicyPulse.tsx` (new)
- `docs/POLICY_PULSE_INTEGRATION_v0.2.md` (this)

삭제:
- `estate/components/pages/home/HeroBriefing.tsx`
- `estate/components/pages/home/ChangeFeed.tsx`
- `estate/components/pages/_shared/PolicyShockTimeline.tsx`

backend / builder / endpoint / 테스트 = 변경 없음.

## 8. 다음 단계

- Framer 페이지 swap 액션 완료 후 실사이트 검증
- 운영 누적 후 PolicyPulse 내부 cap (CHANGE_LIST_CAP=5) / 윈도우 기본값 retract 검토
- SubscriptionCalendar 와의 cross-link 가능성 큐잉 (시간축 통합 MarketPulse 후순위, E/D 운영 검증 후)
