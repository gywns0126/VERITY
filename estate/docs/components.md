# Components & Design Tokens v0.1

> VERITY ESTATE 컴포넌트 라이브러리.
> Framer 구현 전 공통 요소·토큰 스펙 고정.
> **VERITY TERMINAL과 80% 공유** — 포인트 컬러만 분리.

---

## 1. 설계 원칙

1. **Atomic → Composite → Layout** 3계층.
2. **디자인 토큰을 먼저 정의**하고 컴포넌트는 토큰 참조만 한다. 직접 hex 값 금지.
3. **Privacy Mode를 컴포넌트 1급 속성으로** 취급. 모든 민감 컴포넌트는 `sensitivity` prop(`L1/L2/L3`)을 받는다.
4. **VERITY TERMINAL 공유 가능 여부를** 모든 컴포넌트에 명시. 공유는 기본값, ESTATE 전용은 예외 처리.
5. **Framer Auto-layout 친화적**으로 설계. 모든 컴포넌트는 stretchable width / fixed height 기본.

---

## 2. 디자인 토큰

### 2.1 Color

**브랜드·배경** (TERMINAL과 공유):
```
--bg-primary       #0A0B0D     # 어두운 배경 (dark mode 기본)
--bg-secondary     #13151A     # 카드·패널
--bg-tertiary      #1C1F26     # 호버·선택 상태
--border-default   #2A2E38
--border-strong    #3A3F4A
--text-primary     #E8EAED
--text-secondary   #9AA0A6
--text-tertiary    #5F6368
--text-disabled    #3C4043
```

**악센트** (제품별 분리):
```
# VERITY TERMINAL (참고용)
--accent-terminal  #C4FF5A     # 형광 라임

# VERITY ESTATE
--accent-estate    #B8864D     # bronze/darkened amber
--accent-estate-hover  #D4A063
--accent-estate-muted  #4A3520
```

> 이전 논의: 쨍한 골드는 한국 부동산 브랜드(푸르지오·자이 프리미엄)가 이미 사용. **bronze(darkened amber)**로 VERITY 톤(절제·신뢰) 유지.

**LANDEX 등급 색상** (5등급):
```
--grade-hot      #E74C3C   # 레드
--grade-warm     #E67E22   # 오렌지
--grade-neutral  #95A5A6   # 중립 그레이
--grade-cool     #3498DB   # 블루
--grade-avoid    #5D6D7E   # 다크 그레이
```

**GEI Stage 색상** (5단계):
```
--stage-0   transparent          # 정상 (오버레이 없음)
--stage-1   #F1C40F  (alpha 0.3) # 초기 (yellow)
--stage-2   #E67E22  (alpha 0.5) # 가속 (orange) ⚠
--stage-3   #E74C3C  (alpha 0.6) # 정점 (red)
--stage-4   #9B59B6  (alpha 0.7) # 쇠락 (purple)
```

**Alert Category 색상**:
```
--cat-gei         #E74C3C   # 🔴 GEI 경보
--cat-catalyst    #F39C12   # 🟡 호재
--cat-regulation  #9B59B6   # 🟣 규제
--cat-anomaly     #3498DB   # 🔵 이상거래
```

**Status 색상** (수익·손실·중립):
```
--status-positive  #2ECC71
--status-neutral   #95A5A6
--status-negative  #E74C3C
```

### 2.2 Typography

**Font Family** (TERMINAL 공유):
```
--font-display  "Pretendard", system-ui
--font-body     "Pretendard", system-ui
--font-mono     "JetBrains Mono", "D2Coding", monospace
```

**Scale** (8단계):
```
--text-xs    11px / 16px
--text-sm    13px / 20px
--text-base  14px / 22px   # 기본
--text-md    16px / 24px
--text-lg    20px / 28px
--text-xl    24px / 32px
--text-2xl   32px / 40px
--text-3xl   44px / 52px   # Hero
```

**Weight**:
```
--weight-regular  400
--weight-medium   500
--weight-semibold 600
--weight-bold     700
```

### 2.3 Spacing

```
--space-1   4px
--space-2   8px
--space-3   12px
--space-4   16px
--space-5   24px
--space-6   32px
--space-8   48px
--space-10  64px
```

### 2.4 Radius & Elevation

```
--radius-sm   4px
--radius-md   8px
--radius-lg   12px
--radius-xl   16px

--shadow-sm   0 1px 2px rgba(0,0,0,0.2)
--shadow-md   0 4px 8px rgba(0,0,0,0.3)
--shadow-lg   0 8px 24px rgba(0,0,0,0.4)
```

### 2.5 Motion

```
--easing-standard   cubic-bezier(0.4, 0, 0.2, 1)
--duration-fast     120ms
--duration-base     200ms
--duration-slow     320ms
```

---

## 3. Atomic 컴포넌트

### 3.1 LabelPill

LANDEX 등급·GEI Stage 표시용 알약.

```
Props:
  variant: 'grade' | 'stage'
  value:   'HOT' | 'WARM' | 'NEUT' | 'COOL' | 'AVOID'     # variant='grade'
         | 'Stage0' | 'Stage1' | 'Stage2' | 'Stage3' | 'Stage4'  # variant='stage'
  size:    'sm' | 'md' | 'lg'
  sensitivity: 'L0' | 'L1'   # 이 컴포넌트는 기본 L0 (공개 OK)
```

**시각 스펙**:
- 배경: `var(--grade-*)` 또는 `var(--stage-*)` 10% alpha
- 텍스트: 해당 색 100% 또는 white
- 패딩: `sm=2/6px · md=4/10px · lg=6/12px`
- 라디우스: `--radius-sm`

**VERITY TERMINAL 공유**: ✅ 공유. TERMINAL에서는 다른 enum 사용(예: 종목 등급).

### 3.2 Badge

카테고리·severity·상태 표시.

```
Props:
  variant: 'category' | 'severity' | 'status'
  value:   string
  icon:    optional
  size:    'sm' | 'md'
```

**variant별 색상**: category는 `--cat-*`, status는 `--status-*`.

**공유**: ✅ TERMINAL과 enum만 교체.

### 3.3 MaskedValue ⭐ 핵심

민감 수치·구명을 마스킹 처리. Privacy Mode와 연동.

```
Props:
  value:        number | string
  sensitivity:  'L1' | 'L2' | 'L3'   # 필수
  format:       'currency' | 'percent' | 'number' | 'text'
  unmaskOnHover:    boolean  (default: false)
  unmaskDuration:   number   (default: 0, 30초 권장 시 30000)
```

**동작**:
- 기본 상태 + Privacy Mode OFF → **노출** (단 sensitivity=L3는 기본 마스킹 ON)
- Privacy Mode ON → 전부 마스킹
- 마스킹 스타일: 숫자 `●●.●`, 문자 `●●●`

**스타일**:
- 마스킹 시 폰트 색 `--text-tertiary`
- 클릭 가능하면 커서 `pointer` + 미묘한 외곽선

**공유**: ✅ 완전 공유. TERMINAL VAMS에서도 동일 사용.

### 3.4 TrendArrow

방향성 표시 (↗ ↘ ↔).

```
Props:
  direction: 'up' | 'down' | 'flat'
  magnitude: optional (수치 표기)
  interpretation: 'positive' | 'negative' | 'neutral' | 'context'
```

**핵심 주의**: `direction`과 `interpretation`은 별개. 금리 상승은 direction=up이지만 interpretation=negative (부동산 관점).

**공유**: ✅.

### 3.5 Stoplight

🟢 🟡 🔴 3색 인디케이터 (VAMS 포지션용).

```
Props:
  state: 'green' | 'yellow' | 'red'
  size: 'sm' | 'md'
```

**공유**: ✅.

### 3.6 ScoreRadar

5축 레이더 차트 (V/D/S/C/R).

```
Props:
  scores:       { V, D, S, C, R: number }   # 0~100 (R은 감점이므로 −10~0)
  size:         number (정사각)
  showLabels:   boolean
  sensitivity:  'L2' | 'L3'   # 수치 표시 시 L2/L3
```

**Privacy Mode ON**: 축 이름만, 폴리곤 자체는 숨김.

**공유**: ⚠️ 부분 공유. TERMINAL은 다른 5축(가치·성장·수익·리스크·모멘텀 등) — 렌더러 재사용, 축 라벨 교체.

### 3.7 FeatureContribBar

피처별 기여도 막대.

```
Props:
  items: [{ label, value, direction }]
  max:   number
  sensitivity: 'L3'   # 이 컴포넌트는 전부 L3
```

**주의**: 가중치 역산 리스크. Privacy Mode ON이면 전체 컴포넌트 숨김(렌더 안 함).

**공유**: ✅.

---

## 4. Composite 컴포넌트

### 4.1 AlertCard

Signals·Home AlertDashboard에서 사용.

```
Props:
  timestamp:   ISO string
  category:    'gei' | 'catalyst' | 'regulation' | 'anomaly'
  gu:          string
  summary:     string            # 한 줄
  delta:       string            # 변화량 설명
  severity:    'high' | 'mid' | 'low'
  status:      'new' | 'read' | 'hidden'
  actions:     ['detail', 'hide']
```

**구성 요소**: Badge(category) + LabelPill(severity) + 텍스트 + Action 버튼

**변형**:
- `compact` (Home 사이드바용) — 3줄
- `full` (Signals 피드용) — 5줄 + delta 상세

**공유**: ⚠️ 부분 — TERMINAL alert와 구조는 동일, enum 다름.

### 4.2 PositionCard

VAMS 포지션 리스트.

```
Props:
  state:        Stoplight state
  gu:           MaskedValue
  property:     MaskedValue (optional)
  roi:          MaskedValue (L3)
  days:         number (보유일수, L0)
```

**기본 마스킹 ON** (이 컴포넌트 한정).

**공유**: ✅ 완전 공유.

### 4.3 KeyIndicatorCard

Macro 페이지 4대 지표 카드.

```
Props:
  label:       string
  value:       string (단위 포함)
  trend:       TrendArrow props
  onClick:     function
  sensitivity: 'L0'   # 공공 데이터
```

**공유**: ⚠️ TERMINAL은 VIX·DXY 등 다른 매크로.

### 4.4 WatchGroupCard

Home·Region에서 사용.

```
Props:
  name:     string
  gus:      string[]
  tally:    { HOT, WARM, NEUT, COOL, AVOID: number }
  expanded: boolean
```

**스타일**: 기본 접힘(▸), 클릭 시 펼침 — 개별 구 목록 + 등급 뱃지.

**공유**: ⚠️ TERMINAL도 WatchGroup 있지만 종목 리스트. 구조 재사용, enum 교체.

### 4.5 ReportCard

Digest 리포트 라이브러리.

```
Props:
  title:       string
  generatedAt: ISO string
  period:      'weekly' | 'monthly' | 'quarterly'
  status:      'new' | 'published' | 'draft' | 'archived'
  actions:     ['open', 'duplicate', 'publishDraft']
```

**공유**: ✅.

### 4.6 DilutionCheckPanel

Digest 공개 발행 탭 우측 패널. `dilution-rules.md § 5.2` 구현체.

```
Props:
  checks: [
    { id, label, passed: boolean, reason?: string }  × 6
  ]
  overallPass: boolean
```

**시각**:
- 통과: 체크 아이콘 + `--status-positive`
- 실패: X 아이콘 + `--status-negative` + reason 표시
- 전체 통과 시 `[발행 예약]` 버튼 활성화

**공유**: ❌ ESTATE 전용 (dilution 개념은 공유되지만 check 항목 구체).

---

## 5. Specialized 위젯

### 5.1 SeoulMap

25구 폴리곤 SVG.

```
Props:
  overlay:    'landex' | 'gei' | 'v' | 'd' | 's' | 'c' | 'catalyst'
  selectedGu: string | null
  catalystMarkers:  CatalystMarker[]
  size:       'mini' | 'full'
  interactive: boolean
  timeSnapshot: ISO date  (time slider 연동)
  sensitivity: 'L2'        # 색상 오버레이가 L2 위험
```

**데이터 소스**: `/data/seoul-25gu.geojson` (정적 파일)

**mini vs full**:
- mini: 라벨·범례 없음. Home 우측 패널용 (~360×280)
- full: 줌·패닝·호버 툴팁. Region 페이지 메인

**공유**: ❌ ESTATE 전용.

### 5.2 TimeSlider

월간 스냅샷 재생 슬라이더.

```
Props:
  range:      { from, to: ISO date }
  current:    ISO date
  events:     Event[]    # 타임라인 이벤트 마커
  onChange:   (date) => void
  autoPlay:   boolean
  speed:      '1M/s' | '3M/s' | '6M/s'
```

**공유**: ⚠️ TERMINAL에 유사한 historical replay 있을 수 있음 — 구현체 공유.

### 5.3 OverlayToggle

지도 오버레이 전환 라디오.

```
Props:
  options:  ['landex', 'gei', 'v', 'd', 's', 'c', 'catalyst']
  value:    string
  onChange: (value) => void
```

**공유**: ❌ ESTATE 전용.

### 5.4 FilterPanel

Region·Signals 공통 좌측 필터.

```
Props:
  sections: [
    { type: 'radio' | 'checkbox' | 'range' | 'search',
      label, options, value }
  ]
  onChange: (state) => void
  onReset:  () => void
  urlSync:  boolean   # 필터 상태를 query string과 동기화
```

**공유**: ✅.

### 5.5 Ranking25Table

Region 하단 25구 랭킹 테이블.

```
Props:
  columns:    ColumnSpec[]
  data:       RowData[]
  sortBy:     string
  sortDir:    'asc' | 'desc'
  onRowClick: (gu) => void
  sensitivity: 'L2'   # 수치 컬럼 L2
  actions:    ['exportCSV', 'saveSnapshot']
```

**Privacy Mode ON**: 수치 컬럼 전부 `—`. CSV 내보내기 비활성.

**공유**: ❌ ESTATE 전용 (TERMINAL은 종목 테이블 별도).

---

## 6. Layout 컴포넌트

### 6.1 TopNav

```
Props:
  logo:        'VERITY ESTATE' | 'VERITY TERMINAL'
  tabs:        Tab[]
  activeTab:   string
  searchHandler: () => void   # ⌘K
  notifications: number
  privacyMode:   boolean
  onTogglePrivacy: () => void
```

**높이 고정**: 56px. 좌측 로고, 중앙 탭, 우측 ⌘K + 🔔 + ⚙ + User + **Privacy Mode 토글**.

**공유**: ✅ 구조 공유 (`logo` prop만 교체).

### 6.2 TabNav (페이지 내 서브탭)

Digest·Settings 등에서 사용.

```
Props:
  tabs:       { id, label, icon?, badge? }[]
  activeTab:  string
  onChange:   (id) => void
```

**공유**: ✅.

### 6.3 ThreeColumnLayout

Home·Signals·Region·VAMS에서 사용.

```
Props:
  left:       { width, content, collapsible }
  center:     { content }
  right:      { width, content, collapsible }
  breakpoint: 1280 | 1440    # 기본 1440
```

**반응형**: < 1280px에서 `right` 숨김 or Drawer 전환.

**공유**: ✅.

### 6.4 Drawer

Signals 룰 편집·알림 상세 등에서 사용.

```
Props:
  side:       'left' | 'right'
  width:      number
  open:       boolean
  onClose:    () => void
  children:   ReactNode
```

**모션**: `--duration-base`, `--easing-standard`.

**공유**: ✅.

### 6.5 Modal

신규 포지션·설정 변경 등.

```
Props:
  open:     boolean
  onClose:  () => void
  title:    string
  size:     'sm' | 'md' | 'lg'
  actions:  { primary, secondary }
```

**공유**: ✅.

---

## 7. 글로벌 기능

### 7.1 PrivacyModeProvider

전역 Context Provider. 모든 `sensitivity!='L0'` 컴포넌트가 구독.

```
Context:
  privacyMode: boolean
  togglePrivacy: () => void
  maskLevel: 'L0' | 'L1' | 'L2' | 'L3'
```

**키보드 단축키**: `⌘⇧P` — 어디서든 Privacy Mode 토글.

**화면 공유 감지** (v0.2): 브라우저 API로 screen sharing 시작 감지 → 자동 Privacy Mode ON.

### 7.2 DilutionFilter

공개 발행 전 6항목 검증. Digest 페이지 우측 패널에서 시각화되지만, 함수 자체는 전역.

```
Function:
  dilutionCheck(draft: PublicDraft): CheckResult[6]
  - 원점수·수치 스캔
  - combination guard
  - 지역 4주 간격 체크
  - VAMS 참조 스캔
  - 가중치 누출 스캔
  - 임계치 누출 스캔
```

**공유**: ❌ ESTATE 전용.

---

## 8. VERITY TERMINAL 공유 요약

80% 공유 원칙에 대한 구체 집계:

| 카테고리 | 컴포넌트 수 | 완전 공유 | 부분 공유(enum 교체) | ESTATE 전용 |
|---|---|---|---|---|
| Atomic | 7 | 5 | 2 | 0 |
| Composite | 6 | 2 | 3 | 1 |
| Specialized | 5 | 1 | 1 | 3 |
| Layout | 5 | 5 | 0 | 0 |
| Global | 2 | 0 | 0 | 2 |
| **합계** | **25** | **13 (52%)** | **6 (24%)** | **6 (24%)** |

**약 76% 재사용** (완전+부분 공유). 목표 80% 근접. ESTATE 전용 6개는 대부분 지도·희석 관련 — 부동산 도메인 본질.

---

## 9. Framer 파일 구조 (제안)

```
verity-estate.framer/
├── Tokens/
│   ├── Colors
│   ├── Typography
│   ├── Spacing
│   └── Radius
├── Atomic/
│   ├── LabelPill
│   ├── Badge
│   ├── MaskedValue
│   ├── TrendArrow
│   ├── Stoplight
│   ├── ScoreRadar
│   └── FeatureContribBar
├── Composite/
│   ├── AlertCard
│   ├── PositionCard
│   ├── KeyIndicatorCard
│   ├── WatchGroupCard
│   ├── ReportCard
│   └── DilutionCheckPanel
├── Specialized/
│   ├── SeoulMap
│   ├── TimeSlider
│   ├── OverlayToggle
│   ├── FilterPanel
│   └── Ranking25Table
├── Layout/
│   ├── TopNav
│   ├── TabNav
│   ├── ThreeColumnLayout
│   ├── Drawer
│   └── Modal
└── Pages/
    ├── Home
    ├── Region
    ├── Signals
    ├── VAMS
    ├── Macro
    └── Digest
```

---

## 10. 구현 순서 (Framer 착수)

1. **Tokens 먼저** (1~2시간) — 색·타이포·스페이싱 Variables로 등록
2. **Atomic 7개** (반나절) — 모든 페이지가 의존
3. **Layout 5개** (반나절) — TopNav·ThreeColumnLayout·Drawer·Modal·TabNav
4. **Specialized 5개** (1~2일) — SeoulMap이 가장 오래 걸림 (SVG 폴리곤)
5. **Composite 6개** (하루) — Atomic 조합
6. **Pages 6개** (2~3일) — Home 먼저, 나머지 병렬

**총 예상**: 6~8일 (혼자 작업 기준).

---

## 11. 남은 결정 사항

- [ ] 악센트 컬러 **bronze 최종 hex 확정** (`#B8864D`는 가설)
- [ ] Pretendard vs 다른 한글 폰트 — TERMINAL 기준 따를 것
- [ ] dark mode 기본 확정? light mode 지원할지
- [ ] SeoulMap GeoJSON 출처 확정 (국토부 행정구역 SHP → GeoJSON 변환)
- [ ] 화면 공유 감지 API (Screen Capture API는 "공유 당하는" 감지 아님 — 실제 구현 방식 조사)
- [ ] ScoreRadar vs 막대형 — A/B 결정 (wireframe-region.md § 6 항목과 연동)

---

## 12. 변경 이력

| 버전 | 날짜 | 변경 |
|---|---|---|
| v0.1 | 2026-04-23 | 초안. 25 컴포넌트. 토큰 5종(Color·Type·Space·Radius·Motion). VERITY TERMINAL 공유율 76%. MaskedValue·PrivacyModeProvider를 1급 시설로 승격. Framer 파일 구조·구현 순서 제안. |
