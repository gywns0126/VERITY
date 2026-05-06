# ChangeFeed Contract — Page 1 컴포넌트 4/5 — P0

**생성일**: 2026-05-06
**위치**: `estate/docs/contract_change_feed.md`
**전제**: P3-4 closure 95% (`project_estate_p3_4_pending` 정합) — 정책 데이터 흐름 정상 (data.go.kr 정공법, commit `0beb222`)
**다음 단계**: P1 Mock — endpoint 응답 mock + 컴포넌트 셸 (사용자 OK 후 진입)

---

## 0. 목적 — wireframe-home.md §"좌 알림 칼럼" 의 *Page 1 적용*

> "매일 아침 어제 이후 뭐가 바뀌었나를 30초에 파악"

기존 wireframe (3칼럼 데스크톱 1440 — 좌 알림 280px) 를 Page 1 단일 컴포넌트로 정공법 채택. 4 카테고리 broadcast feed.

---

## 1. 4 카테고리 (wireframe-home.md §알림 카테고리 정합)

| 색 | 카테고리 ID | 라벨 (한국어) | 트리거 |
|---|---|---|---|
| 🔴 danger | `gei` | GEI 경보 | Stage 전환 (1→2, 2→3), 40 돌파 |
| 🟡 warn | `catalyst` | 호재 업데이트 | 교통·재개발 단계 배수 변화 (정책 collector + LANDEX feature) |
| 🟣 accent | `regulation` | 규제 변화 | 투기지역·전매·대출·세제 (data.go.kr 정책뉴스/보도자료 from policy_collector) |
| 🔵 info | `anomaly` | 이상거래 | 실거래 통계적 이상치 (동 단위 YoY 단일건) |

**카테고리 ID 정합**: 기존 `vercel-api/api/estate_alerts.py` 의 `VALID_CATEGORIES = {"gei", "catalyst", "regulation", "anomaly"}` 1:1.

---

## 2. 인프라 표준 v1.1 — endpoint

**신규**: `GET /api/estate/change-feed`

namespace: `/api/estate/*` (부동산 고유) — `contract_system_pulse.md` §0 정합.

| 차이 (vs estate_alerts) | 이유 |
|---|---|
| **anonymous** (auth X) | Page 1 home = 로그인 전 진입점. broadcast feed |
| **read-only** | 사용자별 read/hide 상태 X (anonymous) |
| **N=10 cap** | density-first (memory `feedback_estate_density_first`) — 미확인 10건+ 만 스크롤 |

### Query parameters (P1 Mock)

```
GET /api/estate/change-feed?categories=gei,catalyst,regulation,anomaly&hours=72
```

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `categories` | (전체) | comma-sep. 빈 값은 4 카테고리 모두 |
| `hours` | 72 | lookback 시간. wireframe = "3일까지 표시 후 아카이브" 정합 |
| `scenario` | `live` | P1 Mock 시 `healthy`/`empty`/`error` 시나리오 toggle |

### Response schema

```json
{
  "schema_version": "1.0",
  "fetched_at": "2026-05-06T22:00:00+09:00",
  "namespace": "estate",
  "scenario": "live",
  "items": [
    {
      "id": "alert_xxxxxxxx",
      "category": "regulation",
      "severity": "high",
      "region_label": "서울 강남구",
      "title": "재건축 안전진단 기준 완화",
      "summary": "국토교통부, 안전진단 D등급도 재건축 가능... (≤80자)",
      "occurred_at": "2026-05-06T15:30:00+09:00",
      "source_name": "국토교통부",
      "source_url": "https://www.korea.kr/briefing/...",
      "drill_down_url": null
    }
  ],
  "category_counts": {
    "gei": 0,
    "catalyst": 2,
    "regulation": 5,
    "anomaly": 1
  },
  "total": 8
}
```

### items 정렬

`occurred_at DESC`. severity 무관 (시간 기반 — wireframe "어제 이후").

### 실패 정책 (T1·T9 정합)

- 실패 시 `items: []` + `total: 0` + log error. fabricate X
- `scenario=error` 시 명시 mock error: `{"error": "...", "items": []}`

---

## 3. 데이터 출처 (P2 wire 단계에서 실연결, P1 Mock 은 hard-code)

| 카테고리 | 출처 (P2) |
|---|---|
| `regulation` | `policy_collector.collect_policies()` (data.go.kr 정공법) — `MinisterCode` 기반 부처 라벨 + Title/raw_text |
| `catalyst` | `policy_collector.collect_policies(minister_filter=None)` 중 `policy_keywords.rough_relevance_filter()` + `policy_classifier.classify()` 의 catalyst 분류 |
| `gei` | `landex_features.fetch()` 의 GEI Stage 전환 detection (별도 detector — P2 신설) |
| `anomaly` | 실거래 통계 이상치 (P2 별도 모듈) |

**P1 Mock**: 4 카테고리 hard-code 응답 (각 시나리오별 1~3건). live wire 는 P2.

---

## 4. UI 명세 (estate/components/pages/home/ChangeFeed.tsx)

### 위치

Page 1 home, **LandexPulse 다음 / EstateActionLog 위**. 단일 컬럼 max-width 800.

### 헤더

```
변동 피드            [전체 24]   [3일]
[GEI 0] [호재 2] [규제 5] [이상 1]    ← 카테고리 chip filter
```

- 좌측: 컴포넌트 라벨 (스타일은 SystemPulse 헤더 정합)
- 우측: 총 개수 + lookback 표시 (`hours=72` → "3일")
- 카테고리 chip: 클릭 시 filter (URL state X — 컴포넌트 local state)

### 항목 카드 (wireframe-home.md §항목 구조 정합)

```
[● 색]  [지역명]                    [상대시간]
        [Title]
        [Summary 한 줄]
        [출처 부처명]
```

- `●` 색 = 카테고리별 (danger/warn/accent/info)
- `상대시간` = "10분 전", "2시간 전", "어제 17:00" (occurred_at 기반)
- 클릭 → `source_url` 새 탭 open. drill_down_url 있으면 우선
- 호버 효과 = ESTATE 패밀리룩 (HeroBriefing accentSoft wash)

### 빈 상태

`scenario=empty` 또는 items 0 시:
```
지난 3일간 새 변동 없음
```

### 에러 상태

`scenario=error` 시:
```
[!] 변동 피드 일시 불가  [재시도]
```

### 토큰

ESTATE design tokens v1.1 정합 (HeroBriefing/SystemPulse/LandexPulse 와 동일 import). 직접 hex 박지 말고 C/R 만 사용.

---

## 5. P1 Mock 범위

| 항목 | 내용 |
|---|---|
| `vercel-api/api/estate_change_feed.py` | mock 응답 (`live`/`empty`/`error` 시나리오) |
| `vercel.json` rewrite | `/api/estate/change-feed` → `/api/estate_change_feed` |
| `estate/components/pages/home/ChangeFeed.tsx` | UI 셸 + fetch + 카테고리 chip filter |
| Framer prop: `apiUrl` | default `${ESTATE_API_BASE}/api/estate/change-feed` |
| Framer prop: `defaultScenario` | enum `live`/`empty`/`error` (개발 toggle) |

**P1 통과 조건**: 3 시나리오 (`live`/`empty`/`error`) 모두 의도대로 렌더 + 카테고리 chip filter 동작 + 모바일 반응형 (max-width < 600 시 단일 컬럼).

P1 통과 후 P2 wire (실데이터 연결) 진입.

---

## 6. 거짓말 트랩 (T-Code) 컴플라이언스 가드

- T1  fabricate 금지 — items 빈 배열 fallback. mock 응답도 `scenario` 필드로 출처 명시
- T9  silent 실패 X — fetch 실패 시 명시 에러 상태 + console.error
- T11 URL 가정 X — `source_url` 응답 필드 사용 (hardcoded korea.kr 직접 링크 금지)
- T18 카운트 정합 — `category_counts` 합 = `total`
- T29 source URL 절대 URL 의무 — production domain only
- T38 헤더 라벨 hardcoded 금지 — 카테고리 라벨도 응답에서 (P2 시 i18n 가능성)

---

## 7. 폐기/유지

| 항목 | 결정 |
|---|---|
| 기존 `estate_alerts.py` (auth 필수) | **유지** — 사용자별 read/hide 가 다른 페이지(Signals 탭)에서 필요 |
| `change-feed` (anonymous) | **신설** — Page 1 broadcast 전용 |
| Categories 4종 | **고정** — wireframe + estate_alerts schema 정합 |

---

## 8. References

- `estate/docs/wireframe-home.md` §"좌 알림 칼럼" (4 카테고리 원전)
- `vercel-api/api/estate_alerts.py` (categories 정합 출처)
- `estate/docs/contract_system_pulse.md` (endpoint namespace 표준 v1.1)
- `estate/docs/contract_p3_4_policy_data_source.md` (정책 데이터 흐름)
- memory `project_estate_p3_4_pending` (단계 8 진입 전제)
- memory `feedback_estate_density_first` (N=10 cap 결정)
