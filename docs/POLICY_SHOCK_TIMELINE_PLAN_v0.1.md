# PolicyShockTimeline Plan v0.1

ESTATE Tier 2 / E — 정책 충격 시간축 타임라인 (2026-05-12 박음).

## 1. 책임 분리 (overlap audit)

| 컴포넌트 | lookback | 단위 | 책임 |
|---|---|---|---|
| HeroBriefing | 24h (→72h fallback→LANDEX) | 1건 highlight | "지금 무엇이 일어났나" |
| ChangeFeed | 72h | 리스트 (N=10, 2 카테고리) | "최근 변동 항목" |
| **PolicyShockTimeline** | **30d (~90d)** | **시간축 + magnitude** | "충격이 시간에 따라 어떻게 누적/감쇠하나" |

policy_collector data.go.kr API = 72h 상한. 30/90일 lookback 달성을 위해 archive 누적 인프라 신설.

## 2. 데이터 흐름

```
data.go.kr (정책브리핑 보도자료)
    │ collect_policies(72h, minister_filter=None)
    ▼
policy_keywords.rough_relevance_filter
    │
    ▼
policy_classifier.classify (8 카테고리, stage 0~4, affected_regions)
    │
    ▼
estate_policy_archive_builder
    • jsonl append (id dedup)
    • 90d 초과 prune
    • data/estate_policy_archive.jsonl
    │
    ▼
estate_policy_shock_builder
    • archive read (lookback 30d default)
    • impact_score 산출 (산식 §3)
    • direction 매핑
    • by_day aggregation
    • data/estate_policy_shock.json
    │
    ▼ (publish-data action — staged 파일 추가됨)
gh-pages /data/estate_policy_shock.json
    │
    ▼ (vercel-api read-through)
GET /api/estate/policy-shock
    │
    ▼
estate/components/pages/_shared/PolicyShockTimeline.tsx
```

## 3. impact_score 산식 (자체 신호, v0)

```
impact_score (0~1, magnitude) =
    stage_score   × 0.5
  + cat_weight    × 0.3
  + region_breadth × 0.2

stage_score    = stage / 4
cat_weight     = {regulation:1.0, tax:0.9, loan:0.9, redev:0.8,
                  supply:0.7, rental:0.6, catalyst:0.5, anomaly:0.7}
region_breadth = empty(=전국)|≥4 → 1.0 / 2~3 → 0.7 / 1 → 0.4

direction:
    {regulation, tax, loan, anomaly}      → "negative"
    {catalyst, supply, redev, rental}     → "positive"
    그 외                                  → "neutral"
```

가중치 사유 (코드 주석과 정합):
- **0.5 stage**: 정책 사이클 진행 단계 (발표→입법→시행) 의 직접 지표 → 가장 큰 비중.
- **0.3 category**: 시장 채널 영향 (규제 즉시 가격 충격 vs catalyst 점진).
- **0.2 region**: 전국 vs 국지 구분. stage 에 일부 반영되어 최소 비중.

검증 큐: 90일 archive 누적 후 retract 검토 ([[feedback_spec_iteration_retract_rule]] 정합).

## 4. 운영 정책

- cron: 평일 KST 10:00 (hero_briefing 09:00 + change_feed 09:30 + 30분 시차)
- concurrency group: `estate-policy-shock` (다른 estate 빌더와 분리)
- 빌더는 자기 산출물을 main commit ([[project_gh_pages_disabled]] 정합)
- publish-data action staging 에 `estate_policy_shock.json` + `estate_policy_archive.jsonl` 추가
- maxDuration: 5s (read-through endpoint)
- cache: 300s public

## 5. 컴포넌트 (PolicyShockTimeline.tsx)

위치: `estate/components/pages/_shared/` (도메인 횡단 — home/residential 둘 다)

UI 구성 (밀도 우선):
- HEADER: `POLICY · {N}D` + 갱신시각 + 건수
- FILTERS (in-component selector): 기간 (7/14/30/60/90) + 방향 chip (전체/규제/호재/중립)
- STRIP: 시간축 가로 strip + dot (size = impact, color = direction)
- HOVER DETAIL: 카테고리·stage·impact·제목·출처·지역
- BY_DAY 막대: 일별 max_impact (color = net_direction)
- STATS chip: 규제/호재/중립 카운트 + max/mean impact

디자인 토큰: ESTATE v1.1 패밀리룩 (다크 + #B8864D accent gold, [[feedback_estate_design_familylook]]).

## 6. 알려진 한계 + 다음 단계

- archive 누적 시작점 = 0 일째. 30d 윈도우 full 활용까지 ~30일 누적 필요.
- 단일 region 페널티 0.4 가 과한지 운영 후 재검토.
- 정책 시행 후 시장 반응 (가격/거래량 변화) 와의 정합성 검증 큐잉 (LANDEX 데이터와 cross-link).

## 7. 변경 파일

- `api/builders/estate_policy_archive_builder.py` (new)
- `api/builders/estate_policy_shock_builder.py` (new)
- `vercel-api/api/estate_policy_shock.py` (new)
- `vercel-api/vercel.json` (functions + rewrites 1행씩 추가)
- `estate/components/pages/_shared/PolicyShockTimeline.tsx` (new)
- `.github/workflows/estate_policy_shock.yml` (new)
- `.github/actions/publish-data/action.yml` (staging 목록 2 파일 추가)
- `tests/test_estate_policy_archive_builder.py` (new, 5 tests)
- `tests/test_estate_policy_shock_builder.py` (new, 8 tests)
- `docs/POLICY_SHOCK_TIMELINE_PLAN_v0.1.md` (this)
