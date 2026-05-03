# SystemPulse Contract — 페이지 1 컴포넌트 2/5

**생성일**: 2026-05-03 (P0 명세, 코드 작성 X)
**위치 결정**: `estate/docs/contract_system_pulse.md` (사용자 명령서 "동등 위치" 옵션 — ESTATE docs 영역)
**다음 단계**: P1 Mock (사용자 OK 후 진입)

---

## 0. 인프라 표준 v1.1 — endpoint 네임스페이스 룰 (이번 신설)

| 네임스페이스 | 범위 |
|---|---|
| `/api/system/*` | ESTATE/VERITY 공용 자원 (Vercel/Supabase/Claude API) |
| `/api/estate/*` | 부동산 고유 자원 (LANDEX/정책/korea.kr) |
| `/api/verity/*` | 주식 고유 자원 (KIS) |

**원칙**: 각 endpoint 단일 책임. 컴포넌트는 필요 endpoint 조합 호출.

---

## 1. 자원 분류 — 모니터 대상 (SystemPulse 셀 6개)

### `/api/system/health` (공용 — 신규 endpoint)

| 자원 ID | 메트릭 | healthy 조건 | degraded 조건 |
|---|---|---|---|
| `vercel_functions` | last_invocation + error_rate | last < 5min ago AND error_rate < 5% | last >= 5min ago OR error_rate >= 5% |
| `supabase` | rls_check + conn_ok | 둘 다 true | 1개 이상 false |
| `claude_api` | quota_usage_pct | < 80% | >= 80% (또는 미측정 시 **unknown** — degraded 와 별도 톤) |

### `/api/estate/health` (ESTATE 고유 — 신규 endpoint)

| 자원 ID | 메트릭 | healthy 조건 | degraded 조건 |
|---|---|---|---|
| `landex_cron` | last_success_at | < 24h ago | >= 24h ago OR last run failed |
| `policy_cron` | last_success_at | < 24h ago | >= 24h ago OR last run failed |
| `korea_kr_worker` | last_fetch_at + error_rate | (P3-4 미해결 — 항상 **blocked** 별도 톤) | — |

**note**: `korea_kr_worker` 는 P3-4 (Railway 우회) 완료 전까지 healthy 불가. `blocked` 별도 톤으로 표시 — degraded 와 분리해서 "P3-4 미해결" 운영자에 인지.

### Resource 응답 schema (공통)

```json
{
  "schema_version": "1.0",
  "fetched_at": "2026-05-03T12:34:56+09:00",
  "namespace": "system" | "estate",
  "resources": [
    {
      "id": "vercel_functions",
      "label_ko": "Vercel Functions",
      "status": "healthy" | "degraded" | "blocked" | "unknown",
      "metric": {
        "last_invocation_at": "2026-05-03T12:33:00+09:00",
        "error_rate_pct": 1.2
      },
      "note": null | "P3-4 우회 인프라 미구축"
    },
    ...
  ]
}
```

컴포넌트가 두 endpoint 응답의 `resources` 배열을 합쳐 6셀 렌더 + trigger 분기 결정.

---

## 2. trigger 분기 명세

### TRIGGER_HEADERS 매핑 (HeroBriefing 패턴 재사용)

```typescript
type SystemPulseTrigger = "healthy" | "degraded"

const TRIGGER_HEADERS: Record<SystemPulseTrigger, {
    title: string; subtitle: string; sectionLabel: string
}> = {
    healthy: {
        title: "시스템 정상",
        subtitle: "전 시스템 모니터 통과",
        sectionLabel: "STATUS · ALL GREEN",
    },
    degraded: {
        title: "시스템 점검 필요",
        subtitle: "1개 이상 자원 임계 도달",
        sectionLabel: "STATUS · ATTENTION",
    },
}
```

### 분기 결정 로직

```
모든 resources.status === "healthy"             → trigger = "healthy"
모든 resources.status ∈ {"healthy", "unknown"}  → trigger = "healthy" (unknown 은 정보 부족, degraded 아님)
1개 이상 resources.status ∈ {"degraded", "blocked"} → trigger = "degraded"
```

`unknown` 은 trigger 영향 X — 셀 톤만 별도 (확장 안내).

---

## 3. UI 구조 — META 2 layer (HeroBriefing 1:1 재사용)

### Primary 4셀 (170px minmax, 14px font, padding 10·12 — 운영자 0.5초)

| # | label | 값 |
|---|---|---|
| 1 | OVERALL_STATUS | `ALL GREEN` (healthy) / `N DEGRADED` (degraded 자원 수) / `N BLOCKED` (P3-4 미해결 시 N=1+) |
| 2 | LAST_FETCHED | fetch timestamp (`< 1min` / `Nmin ago` / `Nh ago` / `Nd ago` — formatFreshness 헬퍼 재사용) |
| 3 | SOURCE | `system+estate` (호출한 endpoint 조합 식별자) |
| 4 | SESSION_ID | 현재 로그인 세션 ID 첫 8자 (운영자 식별 — `data.user.id.slice(0, 8)`) |

### Detail 6셀 (140px minmax, 11px font, padding 5·8 — 디버깅 시)

각 자원 1셀:

| # | label | 값 표기 |
|---|---|---|
| 1 | VERCEL | `OK` (healthy 시) / `DEGRADED` / `UNKNOWN` |
| 2 | SUPABASE | 동일 |
| 3 | CLAUDE_API | `OK` / `DEGRADED` / `UNKNOWN` |
| 4 | LANDEX_CRON | `OK` (last_success 표기 sub) / `DEGRADED` |
| 5 | POLICY_CRON | 동일 |
| 6 | KOREA_KR | `BLOCKED · P3-4` (현재) — 별도 라벨 |

**T43 정합**: 모두 노출. 토글·hide 금지.
**T40 정합**: grid `auto-fill, minmax(140px, 1fr)` 자동 정렬.

---

## 4. 디자인 토큰 v1.1 컬러 매핑

| status | 토큰 | hex | 의미 |
|---|---|---|---|
| `healthy` | `C.success` | `#22C55E` | 그린 (live 톤, 신호 OK) |
| `degraded` | `C.accent` | `#B8864D` | 골드 (운영자 주의 — VERITY 본체 빨강 X, ESTATE 정체성 정합) |
| `blocked` | `C.textSecondary` | `#A8A299` | 회색 + 별도 `BLOCKED · P3-4` 라벨 (degraded 와 시각 분리) |
| `unknown` | `C.textTertiary` | `#6B665E` | 더 옅은 회색 (정보 부족, 운영자 비-action) |

### 폰트 (정정 3 v1.1 정합)

| 영역 | 폰트 |
|---|---|
| 헤더 title (`시스템 정상` / `시스템 점검 필요`) | `FONT_SERIF` (Noto Serif KR) |
| 서브타이틀 / Detail 셀 status 라벨 | `FONT` (sans Pretendard) |
| 섹션 라벨 (`STATUS · ALL GREEN`) | `FONT` + uppercase + letterSpacing 1.5px |
| META 라벨 (Primary/Detail label) | `FONT` + uppercase + letterSpacing 1.5px |
| timestamp / SESSION_ID / 자원 id | `FONT_MONO` (SF Mono) |

### 컬러 위계 4단계 (정정 4 정합)

- **L1 강한 강조**: `OVERALL_STATUS` 값 (healthy 시 success 큰 폰트, degraded 시 accent 큰 폰트)
- **L2 중간 강조**: 자원 셀 status (각 셀의 ok/degraded 톤)
- **L3 약한 강조**: 셀 sub-text (last_success_at 등 — `textSecondary`)
- **L4 강조 X**: META 라벨, ESTATE · OPERATOR, Footer (`textTertiary`)

---

## 5. REFRESH 버튼 + 6. 재진입 명세

### REFRESH 버튼

| 항목 | 사양 |
|---|---|
| 위치 | StatusBar 우상단 (LIVE indicator 옆) |
| 클릭 동작 | `/api/system/health` + `/api/estate/health` 동시 fetch (Promise.all) → 응답 도착 시 UI 갱신 |
| 클릭 직후 피드백 | 1초간 `REFRESHING…` 표시 + 버튼 disabled |
| 응답 실패 시 | 마지막 fetch 데이터 유지 + 우상단 `REFRESH FAILED` 톤 다운 텍스트 (1분간 노출 후 자동 사라짐) |
| 키보드 접근성 | Enter/Space 키 작동 (button semantic 유지) |

### 재진입 동작 (작업 6 단순화)

- 컴포넌트 **mount 시점마다 자동 fetch** (= "로그인 1회 fetch" + "재진입 시 fetch" 통합)
- ESTATE 다른 페이지 → SystemPulse 재진입 = 새 mount = 새 fetch
- 자동 polling **X** (운영자 수동 제어 — REFRESH 버튼)
- 단 fetch 실패 시 mock 폴백 **X** (T2 정합 — endpoint 503 시 ErrorView 회색 점선 박스 + reason 표시)

---

## 7. 의존성 list

### 외부 (P1 Mock 단계에서 mock data 반환할 endpoint 신규 2건)

- `vercel-api/api/system_health.py` (신규)
  - `/api/system/health` rewrite 라우트
  - mock 모드: `?mock=true` query 시 정해진 mock JSON 반환
- `vercel-api/api/estate_health.py` (신규)
  - `/api/estate/health` rewrite 라우트
  - 동일 mock 모드

### 내부 (재사용)

- HeroBriefing.tsx 의 패턴:
  - `TRIGGER_HEADERS` 매핑 (인라인 상수)
  - `inferTriggerType` 패턴 (단 SystemPulse 는 resources status 합산 기반)
  - `formatFreshness` 헬퍼 (last_fetched 표기)
  - META 2 layer (Primary 4 + Detail N) 셀 스타일 (`primaryCellStyle` / `detailCellStyle`)
  - SectionDivider 폰트 (sans uppercase + 1.5px)
  - 컬러 위계 4단계
- 디자인 토큰 v1.1 (다크 + 골드 emphasis) — **변경 X**
- ESTATE_API_BASE 상수 인라인 (`https://project-yw131.vercel.app`)
- Framer 컨벤션 self-contained — 외부 import 0

### Schema·Endpoint 정합 검증 (P1 진입 직전 의무)

- `/api/system/health` mock 응답 schema = 위 §1 Resource 응답 schema
- `/api/estate/health` mock 응답 schema = 동일
- 두 응답 합쳐 6셀 렌더 — `id` 충돌 없음 (system 3 + estate 3)

---

## 8. P1 Mock 진입 게이트

P0 명세 OK 떨어지면 P1 Mock 단계 진입:

1. `vercel-api/api/system_health.py` + `vercel-api/api/estate_health.py` mock JSON 반환 endpoint 작성
2. `vercel.json` rewrite 2건 추가 (`/api/system/health`, `/api/estate/health`)
3. `estate/components/pages/home/SystemPulse.tsx` 컴포넌트 셸 작성 — Mock JSON fetch + 6셀 렌더
4. mock JSON 데이터: 의도적으로 **healthy 시나리오 1건 + degraded 시나리오 1건** 둘 다 만들어서 trigger 분기 검증 (`?scenario=healthy|degraded` query)
5. Framer 수동 복붙 후 사용자 V6 검증

P1 거짓말 트랩 (예고):
- T2 정합 — mock fallback 텍스트 X (503 시 ErrorView)
- T29 정합 — endpoint base URL 절대 URL (`ESTATE_API_BASE`)
- T31 정합 — Framer self-contained 컨벤션
- T38 정합 — 헤더 라벨 hardcoded X (`TRIGGER_HEADERS` 동적)

---

## 명세 정합 자체 점검

| 항목 | 정합 |
|---|---|
| HeroBriefing 패턴 재사용 | ✅ TRIGGER_HEADERS · META 2 layer · 컬러 위계 4단계 · formatFreshness · SectionDivider |
| 디자인 토큰 v1.1 그대로 | ✅ 변경 0 |
| T2 (mock fallback 금지) 정신 | ✅ 503 시 ErrorView, mock 폴백 X |
| T39 (시각 구분 0.5초) 정신 | ✅ healthy 그린 / degraded 골드 / blocked 회색 — 임계 색 분리 |
| T43 (데이터 누락 X) | ✅ 6 자원 모두 노출, 토글·hide 금지 |
| 세션 단순화 | ✅ mount = fetch + REFRESH 수동, polling X |

---

**P1 Mock 진입 OK 떨어지면 즉시 시작.**
