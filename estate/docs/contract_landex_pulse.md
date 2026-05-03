# LandexPulse Contract — 페이지 1 컴포넌트 3/5

**생성일**: 2026-05-03 (P0 명세, 코드 작성 X)
**위치**: `estate/docs/contract_landex_pulse.md` (HeroBriefing/SystemPulse 명세와 동등)
**다음 단계**: P1 Mock (사용자 OK + 컬러 토큰 결정 후)

---

## 결정 사항 (PM 컨펌 완료)

| Q | 결정 |
|---|---|
| Q1 범위 | 25구 overview + 상세 drill-down 통합 (1 컴포넌트) |
| Q2 trigger 분기 | 2분기 — `normal` / `regime_shift` |
| Q3 UI 구조 | META 2 layer (Primary 4셀 + Detail 5셀) |
| Q4 시각화 | **SVG 서울 25구 지도 + 25구 grid 조합** (LandexMapDashboard reuse + 자체 grid) — 정정 2026-05-04 |
| Q5 drill-down | 인라인 expand (클릭 셀 아래 상세) |
| Q6 fetch | mount 1회 + REFRESH, `/api/estate/landex-pulse` |
| Q7 L3 라벨 | "INTERNAL · v1.1 · ENCRYPTED" 통일 (어드민 정체성) |
| Q8 코드 reuse | **부분 reuse — 시각화 영역(LandexMapDashboard SVG 지도)만 reuse, 나머지(META/grid/expand/RANKING)는 자체 구현** — 정정 2026-05-04 |

> **Q4 정정 근거 (2026-05-04)** — 라이브 `LandexMapDashboard.tsx` 에 SVG 서울 25구 지도 컴포넌트 (`atomic/SeoulMap.tsx`) 가 존재. reuse 결과 지도(시각/지리적 직관) + grid(정량/구별 LANDEX) 조합으로 정보량 ↑. 가로 grid only 보다 운영자 인지 풍부.
| Q9 용어 툴팁 | 자체 hover + JSON source (`estate/data/terms.json`) |

---

## 1. 라이브 LANDEX 컴포넌트 실측 reference

### `estate/components/pages/LandexMapDashboard.tsx`

| 항목 | 값 |
|---|---|
| 디자인 토큰 | **v1.0 정본 (Neo Dark Terminal + ESTATE 골드)** — bgPage `#0E0F11`, accent `#B8864D`, **gradeHOT/WARM/NEUT/COOL/AVOID + stage0~4 토큰 보유** |
| Type — `OverlayMode` | `"landex" \| "gei" \| "v" \| "d" \| "s" \| "c" \| "catalyst"` (7) |
| Type — `GradeLabel` | `"HOT" \| "WARM" \| "NEUT" \| "COOL" \| "AVOID"` (5) |
| Type — `StageLevel` | `0 \| 1 \| 2 \| 3 \| 4` (5) |
| Type — `SensitivityLevel` | `"L0" \| "L1" \| "L2" \| "L3"` (4) |
| Interface — `GuData` | `{ name, grade?, stage?, landex?, gei?, ... }` |
| Interface — `FilterState` | `{ minGrade: GradeLabel \| "ALL", ... }` |
| 데이터 흐름 | `fetch /api/landex/scores` → `GuData[]` 변환 (row.tier5 → grade, row.gei_stage → stage) |
| 흡수 컴포넌트 | SeoulMap + FilterPanel + TimeSlider + OverlayToggle + Ranking25Table |
| 등급 임계 | landex ≥80=HOT, ≥65=WARM, ≥50=NEUT, ≥35=COOL, <35=AVOID |
| Stage 임계 | gei ≥80=4, ≥60=3, ≥40=2, ≥20=1, <20=0 |

### `estate/components/pages/ScoreDetailPanel.tsx`

| 항목 | 값 |
|---|---|
| 디자인 토큰 | **v1.0 정본** (LandexMapDashboard 와 동일) |
| Interface — `ScoreSet` | V/D/S/C/R 5축 점수 |
| Interface — `FeatureContrib` | 피처 기여도 (feature/weight/sign) |
| Interface — `SeriesPoint` | 시계열 (x/y/date) |
| Interface — `TimeSeries` | 주간 매매가격지수 / 월간 미분양 등 |
| Interface — `GuDetail` | `{ gu, score, grade, features, strengths, weaknesses, ... }` |
| 데이터 흐름 | 3 endpoint 병렬 — `/api/landex/scores` + `/api/landex/features` + `/api/landex/narrative` |
| 흡수 컴포넌트 | 헤더(구·LANDEX 점수) + ScoreRadar + FeatureContribBar + 강점/약점 |

→ **LandexPulse 는 위 두 컴포넌트의 데이터 모델 + UI 패턴 reference**. 코드 reuse — 시각화 영역만 부분 reuse (`atomic/SeoulMap.tsx` SVG 25구 지도 → LandexPulse 안에 인라인 통합, T31 self-contained). 나머지(META/grid/expand/RANKING)는 자체 구현. schema 1:1 일치 (Q8 정정 2026-05-04).

---

## 2. 데이터 schema — `/api/estate/landex-pulse`

### 응답 schema

```typescript
{
  schema_version: "1.0",
  generated_at: ISO timestamp,
  trigger: {
    type: "normal" | "regime_shift",
    headerTitle: string,    // (서버 미반환 — 클라이언트 TRIGGER_HEADERS 매핑)
    subtitle: string,       // (동일)
    sectionLabel: string,   // (동일)
    // — 또는 클라이언트가 type 만 받아서 매핑 (HeroBriefing/SystemPulse 패턴)
  },
  meta: {
    primary: {
      current_regime: "bull" | "bear" | "neutral",
      top_gainer: { gu_name: string, change_pct: number },
      top_loser:  { gu_name: string, change_pct: number },
      last_shift_at: ISO timestamp | null,
    },
    detail: {
      degraded_count: number,    // 등급 하락 구 수
      gained_count: number,      // 등급 상승 구 수
      gei_s4_count: number,      // GEI Stage 4 구 수
      avg_landex: number,        // 25구 LANDEX 평균 (0~100)
      data_freshness_min: number,// 마지막 cron 분 단위
    },
  },
  gus: [
    {
      gu_name: string,
      landex: number,            // 0~100
      grade: "HOT" | "WARM" | "NEUT" | "COOL" | "AVOID",
      gei: number,
      stage: 0 | 1 | 2 | 3 | 4,  // 라이브 정합 — number (StageLevel 정의)
      v_score: number,
      d_score: number,
      s_score: number,
      c_score: number,
      r_score: number,
      catalyst_score: number,
      // drill-down expand 데이터 (LandexPulse 단일 endpoint 통합 — 라이브 3 endpoint X)
      detail: {
        radar: { v: number, d: number, s: number, c: number, r: number },
        feature_contributions: [
          { feature: string, weight: number, sign: "+" | "-" }
        ],
        timeseries: {
          weekly_price_index: [{ date: string, value: number }],
          monthly_unsold:     [{ date: string, value: number }],
        },
        strengths:  string[],
        weaknesses: string[],
      },
    },
    // ... 25개 구
  ],
}
```

### schema 정합 비교 (라이브 vs LandexPulse)

| 필드 | LandexMapDashboard | ScoreDetailPanel | LandexPulse |
|---|---|---|---|
| `gu_name` | `name` | `gu` | **`gu_name`** (통일) |
| `grade` | `GradeLabel` | `grade` | 동일 (`HOT/WARM/NEUT/COOL/AVOID`) |
| `stage` | `StageLevel` (0~4 number) | — | **number** (라이브 정합) |
| `landex` | `landex?` | `score` | `landex` (필수) |
| `v/d/s/c/r_score` | — | `ScoreSet` | 5축 동일 |
| `feature_contributions` | — | `FeatureContrib[]` | 동일 |
| `timeseries` | (TimeSlider 별개) | `TimeSeries` | 동일 |
| `strengths/weaknesses` | — | `string[]` | 동일 |

→ **LandexMapDashboard overview + ScoreDetailPanel detail 통합**. 라이브 endpoint 3개 (scores/features/narrative) 호출 → LandexPulse 단일 endpoint 통합 (작업량·UX 단순화).

---

## 3. trigger.type 분기 명세

### TRIGGER_HEADERS 매핑

```typescript
type LandexTrigger = "normal" | "regime_shift"

const TRIGGER_HEADERS: Record<LandexTrigger, {
    title: string; subtitle: string; sectionLabel: string
}> = {
    normal: {
        title: "시장 정상",
        subtitle: "regime 안정 — 25구 변화 임계 미만",
        sectionLabel: "REGIME · STABLE",
    },
    regime_shift: {
        title: "시장 regime 변동",
        subtitle: "{N}개 구 등급 변화 — 운영자 검토 필요",
        sectionLabel: "REGIME · SHIFT DETECTED",
    },
}
```

### 분기 결정 로직

```
25구 등급 변화 (HOT↔WARM↔NEUT↔COOL↔AVOID) 구 수 = degraded_count + gained_count
변화 구 수 >= REGIME_SHIFT_THRESHOLD (3)  → trigger = "regime_shift"
그 외                                      → trigger = "normal"
```

**근거 (운영 룰 7번 — cry wolf 방지)**:
- 1~2개 구 변화는 정상 시장 noise → `normal` 유지
- 3개 이상 구 변화 시만 알람 → 운영자 검토 신호

상수: `REGIME_SHIFT_THRESHOLD = 3` (P0 추천. P2 wire 시 조정 영역)

`subtitle` 의 `{N}` = `degraded_count + gained_count` 동적 substitution.

---

## 4. UI 구조 — META 2 layer + 25구 grid + drill-down expand

### 4-1. Header (HeroBriefing 패턴)
- mono `ESTATE · OPERATOR` 라벨
- serif `headerTitle` (regime_shift 시 골드, normal 시 그린)
- sans subtitle
- StatusBar (LIVE indicator + REFRESH 버튼 — SystemPulse 패턴)

### 4-2. SectionDivider — `META`

### 4-3. META Primary 4셀 (170px minmax, 14px font, padding 10·12)

| label | 값 표기 |
|---|---|
| `CURRENT_REGIME` | `BULL · 강세` / `BEAR · 약세` / `NEUTRAL · 중립` (mono enum + 한글 라벨) |
| `TOP_GAINER` | `{gu_name} {+X.X}%` (mono, 그린 톤) |
| `TOP_LOSER` | `{gu_name} {-X.X}%` (mono, 빨강 톤) |
| `LAST_SHIFT` | `formatFreshness` 재사용 (`< 1min` / `Nh ago` / null 시 `—`) |

### 4-4. META Detail 5셀 (140px minmax, 11px font, padding 5·8)

| label | 값 |
|---|---|
| `DEGRADED_COUNT` | `N` (등급 하락) |
| `GAINED_COUNT` | `N` (등급 상승) |
| `GEI_S4_COUNT` | `N` (Stage 4 — warn 톤) |
| `AVG_LANDEX` | `XX.X` (mono) |
| `DATA_FRESHNESS` | `formatFreshness(data_freshness_min)` |

### 4-5. SectionDivider — `VISUALIZATION`

### 4-6. SVG 서울 25구 지도 + 25구 grid (정정 2026-05-04)

**(a) SVG 서울 25구 지도** — `atomic/SeoulMap.tsx` reuse, LandexPulse 안에 인라인 통합 (T31)
- viewBox `0 0 1000 823`, SEOUL_PATHS 25구 (path + centroid) 정합
- 각 구 fill = 등급 색 (HOT/WARM/NEUT/COOL/AVOID), opacity hover/select 동적
- hover/select 시 stroke = `accent` + drop-shadow + 우상단 floating 툴팁 (LANDEX·등급·GEI·Stage)
- 좌하단 범례 (5등급)
- 지도 클릭 = grid 셀 클릭과 **동일 동작** — `setSelectedGu` 공유, inline expand 트리거

**(b) 25구 grid (지도 아래 보조)** — 정량 비교용
```
[강남] [서초] [송파] [강동] [용산] [성동] [광진] [중구] [종로] [서대문]
[은평] [마포] [영등포] [구로] [금천] [동작] [관악] [강서] [양천] [성북]
[동대문] [중랑] [노원] [도봉] [강북]
```
- 한 줄에 5~10구 (가로 wrap, `auto-fill`), 각 셀 = 구 명 + 등급 색
- 셀 디자인: 구 명 (sans) + LANDEX 수치 (mono, 작은 폰트) + 등급 색 배경 (alpha 0.25)
- 셀 클릭 시 **inline expand** — 해당 셀 아래에 상세 펼침 (4-7)
- 지도(시각/지리적 직관) + grid(정량/구별 수치) 조합으로 운영자 인지 풍부

### 4-7. inline expand (클릭한 구의 detail)

선택된 구만 상세 노출 (T43 — 토글 X, 추가 노출. 다른 구는 접혀있는 게 아닌 "선택 안 된" 상태):

- 구 명 + LANDEX 큰 점수 (HOT/WARM 시 골드 강조, 그 외 회색)
- 등급 chip + Stage S{N} chip
- ScoreRadar (V·D·S·C·R 5축, ScoreDetailPanel 패턴)
- FeatureContribBar — 피처 기여도 (라벨 hover 시 `INTERNAL · v1.1 · ENCRYPTED` L3 표기 — Q7)
- 시계열 mini-chart (주간 매매가격지수 + 월간 미분양 inline)
- 강점/약점 list (sans, ScoreDetailPanel 패턴)

### 4-8. SectionDivider — `RANKING`

### 4-9. 25구 랭킹 테이블 (라이브 Ranking25Table 정합)

| # | 구 | LANDEX↓ | 등급 | GEI | Stage | V | D | S | C |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 강남구 | 88.4 | HOT | 78 | S4 | 92 | 85 | 80 | 95 |
| 2 | 서초구 | 84.1 | HOT | ... | ... | ... | ... | ... | ... |

- 정렬: LANDEX 내림차순 default
- 헤더 클릭 시 정렬 토글 (P0 외, P1 검토)
- mono 숫자, sans 라벨

### 4-10. Footer
`ESTATE · INTERNAL · v1.1 · ENCRYPTED` (HeroBriefing/SystemPulse 동일)

---

## 5. 컬러 매핑 — ⚠️ [C]6 트리거 발동

### 토큰 결정 영역

LandexPulse 는 grade* (5톤) + stage* (5톤) **필수 사용**. v1.1 (HeroBriefing/SystemPulse) 는 단순화로 grade*/stage* 부재. 처리 옵션 3:

#### 옵션 A — v1.0 정본 hex 그대로 인라인 (추천)
- LandexMapDashboard 의 hex 그대로 LandexPulse `const C` 에 박음
- v1.1 토큰 정의 자체는 **무수정** ([C]6 미발동)
- 시각 일관성 — 라이브 LandexMapDashboard 색과 100% 일치
- 미래 grade*/stage* 사용 컴포넌트 늘면 v1.2 진화 결정

```typescript
// LandexPulse const C 인라인 (LandexMapDashboard v1.0 hex 정합)
gradeHOT: "#EF4444",   // 빨강 (HOT)
gradeWARM: "#F59E0B",  // 주황 (WARM)
gradeNEUT: "#A8ABB2",  // 회색 (NEUT)
gradeCOOL: "#5BA9FF",  // 파랑 (COOL)
gradeAVOID: "#6B6E76", // 어두운 회색 (AVOID)
stage0: "transparent",
stage1: "#FFD600",     // 노랑 (S1)
stage2: "#F59E0B",     // 주황 (S2)
stage3: "#EF4444",     // 빨강 (S3)
stage4: "#9B59B6",     // 보라 (S4)
```

#### 옵션 B — v1.1 → v1.2 진화 (grade*/stage* 추가) ⚠️ [C]6
- v1.1 토큰 정의에 grade*/stage* 10 토큰 추가 → v1.2 라벨 진화
- HeroBriefing/SystemPulse 도 v1.2 라벨로 정정 (라벨만, hex 무변)
- LandexPulse 는 v1.2 grade*/stage* 토큰 참조
- 미래 호환성 ↑, 단 토큰 정의 변경 = **사전 승인 필수**

#### 옵션 C — v1.0 정본 자체를 다른 컴포넌트가 모두 참조
- 모든 ESTATE 컴포넌트가 LandexMapDashboard 의 v1.0 정본 직접 참조
- Framer self-contained 컨벤션 위반 (T31)
- 폐기

**추천 — 옵션 A**. v1.1 무수정, [C]6 미발동, 시각 일관성 보장.

### 컬러 매핑 (옵션 A 채택 가정)

| 영역 | 토큰 | hex |
|---|---|---|
| 헤더 title (normal) | `C.success` | `#22C55E` |
| 헤더 title (regime_shift) | `C.accent` | `#B8864D` |
| 좌측 띠 (normal) | `C.success` | 그린 |
| 좌측 띠 (regime_shift) | `C.accent` | 골드 |
| TOP_GAINER 값 | `C.success` | 그린 |
| TOP_LOSER 값 | `C.danger` | `#EF4444` |
| GEI_S4_COUNT (warn) | `C.warn` | `#F59E0B` |
| 25구 셀 — HOT | gradeHOT 인라인 | `#EF4444` (alpha 0.7) |
| 25구 셀 — WARM | gradeWARM 인라인 | `#F59E0B` |
| 25구 셀 — NEUT | gradeNEUT 인라인 | `#A8ABB2` |
| 25구 셀 — COOL | gradeCOOL 인라인 | `#5BA9FF` |
| 25구 셀 — AVOID | gradeAVOID 인라인 | `#6B6E76` |
| Stage chip — S4 | stage4 인라인 | `#9B59B6` (보라) |
| 피처 기여도 + | `C.success` | 그린 |
| 피처 기여도 − | `C.danger` | 빨강 |
| 헤더 = serif, META 라벨 = sans uppercase 1.5px, 수치/ID = mono | (폰트 3종 그대로) | |

### 컬러 위계 4단계 (정정 4 정합)

- **L1** (강한 강조): 헤더 title / 25구 셀 등급 색 / 선택된 구의 LANDEX 큰 점수
- **L2** (중간 강조): TOP_GAINER/LOSER, Pill, 피처 기여도 부호
- **L3** (약한 강조): chip (등급/Stage), 시계열 라인, 랭킹 테이블 행
- **L4** (강조 X — `textTertiary`): META 라벨, ESTATE · OPERATOR, Footer

---

## 6. 용어 hover 툴팁 시스템 (Q9)

### 6-1. JSON source 신설 — `estate/data/terms.json`

```json
{
  "GEI_STAGE":      { "label": "GEI Stage",     "category": "internal", "definition": "[P1 Mock]", "stages": {...}, "l3": true },
  "LANDEX":         { "label": "LANDEX",        "category": "metric",   "definition": "[P1 Mock]", "l3": false },
  "V_SCORE":        { "label": "V Score (가치)", ... },
  "D_SCORE":        { "label": "D Score (수요)", ... },
  "S_SCORE":        { "label": "S Score (공급)", ... },
  "C_SCORE":        { "label": "C Score (입지)", ... },
  "R_SCORE":        { "label": "R Score (위험)", ... },
  "CATALYST_SCORE": { "label": "Catalyst Score", ... },
  "REGIME":         { "label": "Regime", "definition": "...", "values": ["bull","bear","neutral"] },
  "GRADE_HOT":      { "label": "HOT 등급", ... },
  "GRADE_WARM":     { "label": "WARM 등급", ... },
  "GRADE_NEUT":     { "label": "NEUT 등급", ... },
  "GRADE_COOL":     { "label": "COOL 등급", ... },
  "GRADE_AVOID":    { "label": "AVOID 등급", ... },
  "TIER10":         { "label": "Tier 10", ... },
  "FEATURE_CONTRIB":{ "label": "피처 기여도", "l3": true },
  "WEEKLY_PRICE_INDEX": { "label": "주간 매매가격지수", ... },
  "MONTHLY_UNSOLD": { "label": "월간 미분양", ... },
  "MoM": { "label": "Month over Month", ... },
  "WoW": { "label": "Week over Week", ... }
}
```

### 6-2. P0 단계 — 키 list 만 정의 (definition 본문 P1 Mock 에서 작성)

19 키:
- 점수 8: LANDEX, V/D/S/C/R_SCORE, CATALYST_SCORE, GEI_STAGE
- 등급 5: GRADE_HOT/WARM/NEUT/COOL/AVOID
- regime/tier 2: REGIME, TIER10
- 분석 2: FEATURE_CONTRIB (l3=true), WEEKLY_PRICE_INDEX, MONTHLY_UNSOLD
- 시간 2: MoM, WoW

### 6-3. UI 패턴 — TermTooltip 컴포넌트

- 위치: `estate/components/shared/TermTooltip.tsx` (신규)
- props: `{ termKey: string, children: React.ReactNode }`
- 용어 표시: `children` 에 점선 underline (`borderBottom: 1px dashed C.textTertiary`) 또는 가는 ? 아이콘
- hover 시 툴팁:
  - 배경 `bgElevated`, border `border`, 그림자 옅게
  - 헤더: serif `term.label` + L3 라벨 (`l3=true` 시 골드 chip)
  - 본문: sans 1~3줄 `term.definition`
  - 추가 정보 (`stages`/`values` dict): sans + mono mix
  - 위치: hover 대상 위/아래 (overflow 처리 — 화면 경계 시 반대편 펼침)
  - 키보드 접근성: focus-within 도 트리거

### 6-4. 적용 범위

- **LandexPulse**: 모든 도메인 용어 wrap (헤더 텍스트, 메타 라벨, 셀 라벨, 피처명 등)
- **HeroBriefing/SystemPulse 소급 적용**: P4 백로그 (LANDEX_CRON / POLICY_CRON / KOREA_KR_WORKER 등)
- **terms.json**: 향후 ESTATE 전체 컴포넌트 공용 — 미래 컴포넌트 추가 시 키만 추가

---

## 7. REFRESH 버튼 + 재진입 (HeroBriefing/SystemPulse 패턴)

| 항목 | 사양 |
|---|---|
| 위치 | StatusBar 우상단 (LIVE 옆) |
| mount 동작 | 자동 1회 fetch (P0 §6 단순화) |
| 클릭 동작 | `/api/estate/landex-pulse?_=Date.now()` 재fetch |
| 1초 피드백 | `REFRESHING…` 표시 + 버튼 disabled |
| 응답 실패 | 마지막 데이터 유지 + `REFRESH FAILED` 톤 다운 (1분 노출) |
| 자동 polling | **X** (운영자 수동 제어) |

---

## 8. 의존성 명세

### 외부 (P1 Mock 단계 신규)
- `vercel-api/api/estate_landex_pulse.py` — `/api/estate/landex-pulse` rewrite
- `?scenario=normal|regime_shift` query 모드 (HeroBriefing/SystemPulse 패턴)
- mock data 2 시나리오 (normal: 변화 1구 / regime_shift: 변화 5+구)

### 내부 신규
- `estate/data/terms.json` — 용어 사전 (P1 Mock 단계 definition 본문 채움)
- `estate/components/shared/TermTooltip.tsx` — hover 툴팁 컴포넌트
- `estate/components/pages/home/LandexPulse.tsx` — 메인 컴포넌트 셸

### 내부 재사용 (HeroBriefing/SystemPulse 패턴)
- `TRIGGER_HEADERS` 매핑 (인라인 상수)
- `formatFreshness` 헬퍼
- `inferTrigger(N >= 3 → regime_shift)` 패턴 (SystemPulse 의 `inferSystemTrigger` 정합)
- META 2 layer (Primary 4 + Detail 5)
- SectionDivider (sans uppercase 1.5px, prefix `//` 제거)
- 컬러 위계 4단계
- 폰트 3종 (serif 헤더, sans 라벨, mono 값)
- REFRESH 버튼
- StatusBar / Footer
- ESTATE_API_BASE 상수 인라인 (`https://project-yw131.vercel.app`)
- Framer 컨벤션 self-contained — 외부 import 0 (TermTooltip 만 estate/components/shared/ 에서 별도 복붙)

### Framer 호환성 — TermTooltip
- LandexPulse 가 TermTooltip 을 self-import 시 Framer 컨벤션 위반 가능 (T31)
- **해결**: TermTooltip 자체도 self-contained Framer 컴포넌트로 작성 + 별도 등록 → LandexPulse 는 일반 React import (Framer 가 같은 프로젝트 내 import 지원)
- 또는 LandexPulse 안에 TermTooltip 인라인 (단순화). **P1 진입 직전 결정**.

---

## 9. 자체 정합 점검

| 항목 | 정합 |
|---|---|
| HeroBriefing 패턴 재사용 8 항목 | ✅ TRIGGER_HEADERS · META 2 layer · SectionDivider · formatFreshness · 컬러 위계 4단계 · 폰트 3종 · REFRESH · StatusBar/Footer |
| 디자인 토큰 v1.1 변경 | **❓ [C]6 트리거 — grade*/stage* 처리 결정 필요** (옵션 A 추천 = v1.1 무수정, hex 인라인) |
| T2 (mock fallback 금지) | ✅ 503 → ErrorView |
| T29 (절대 URL) | ✅ ESTATE_API_BASE 인라인 |
| T31 (Framer self-contained) | ✅ 단 TermTooltip 분리 시 결정 영역 (P1 진입 시 결정) |
| T39 (시각 구분 0.5초) | ✅ 등급 5톤 (HOT 빨강 / WARM 주황 / NEUT 회색 / COOL 파랑 / AVOID 어회) |
| T41 (mono+uppercase 0건) | ✅ 라벨 sans uppercase 1.5px |
| T42 (토큰 변경 X) | 옵션 A 채택 시 ✅ |
| T43 (데이터 누락 X) | ✅ 25구 모두 노출, drill-down expand 는 추가 노출 (토글 아님) |
| 라이브 실측 reference 1:1 | ✅ schema 비교 표 §2 + UI 패턴 §1 |
| 용어 툴팁 키 list 빠짐 없음 | ✅ 19 키 (점수 8 + 등급 5 + regime/tier 2 + 분석 2 + 시간 2) |

---

## 10. P1 Mock 진입 게이트

P0 명세 OK + **컬러 토큰 결정 (옵션 A/B/C)** 이후 P1 Mock 단계 진입:

### P1 작업 list

1. `vercel-api/api/estate_landex_pulse.py` mock endpoint
   - `?scenario=normal` (변화 구 수 < 3) / `?scenario=regime_shift` (변화 구 수 >=3)
   - 25구 mock data + detail 인라인 (radar/features/timeseries/strengths/weaknesses)
2. `vercel.json` rewrite 1건 (`/api/estate/landex-pulse` → `/api/estate_landex_pulse`)
3. `estate/data/terms.json` — 19 용어 definition 본문 작성 (l3 표시 + stages/values dict)
4. `estate/components/pages/home/LandexPulse.tsx` 셸
   - mount fetch + 6 섹션 (Header / META Primary / Detail / 25구 grid / inline expand / 랭킹)
   - 옵션 A grade*/stage* hex 인라인
5. `estate/components/shared/TermTooltip.tsx` — hover 툴팁 (또는 LandexPulse 내부 인라인)
6. Framer 수동 복붙 후 V1 검증 (curl) + V2 검증 (브라우저)

### P1 거짓말 트랩 (예고)
- T2 정합 — mock fallback 텍스트 X (503 시 ErrorView)
- T29 정합 — endpoint base URL 절대 URL
- T31 정합 — Framer self-contained 컨벤션 (TermTooltip 분리 결정)
- T38 정합 — 헤더 라벨 hardcoded X
- T41 정합 — mono+uppercase 0건
- T42 정합 — 디자인 토큰 v1.1 무수정 (옵션 A 채택 시)
- T43 정합 — 25구 누락 X, drill-down expand 토글 X

---

## ⚠️ P1 진입 전 결정 필요 — 2건

### 1. 컬러 토큰 처리 — **옵션 A vs B vs C** ([C]6 트리거)
- 추천: **A** (v1.1 무수정, LandexMapDashboard hex 인라인). [C]6 미발동.
- B 채택 시: v1.2 진화 → HeroBriefing/SystemPulse 헤더 주석 정정 (라벨만, hex 무변).
- C 거부.

### 2. TermTooltip 분리 vs 인라인 — Framer 호환성
- 추천: **P1 진입 시점 결정** (Framer 가 같은 프로젝트 내 .tsx import 지원하면 분리, 아니면 인라인).
- 단순한 시작 = 인라인 (LandexPulse 내부 정의). 향후 ESTATE 다른 컴포넌트 사용 시 분리 검토.

---

**P1 Mock 진입 OK** + 위 2건 결정 떨어지면 즉시 시작.
