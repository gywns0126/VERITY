# VERITY 컴포넌트 정리 + 모던 심플 재디자인 Plan v0.1

**작성:** 2026-05-04
**대상:** Frontend (Framer code components, ESTATE 제외)
**전제:** 인프라 (verity_terms.json + TermTooltip block) 박힌 후 cluster 1개씩 진입
**다음 정정:** v0.2 — cluster 1개 끝날 때마다 plan 업데이트

---

## 1. 핵심 원칙 (3가지)

### 1-1. 이건희-반도체 원칙
**Frontend = 심플 (결정자 시선) / Backend = 월가 상위 0.00000001% 미친 트레이딩 괴물급 (실행자 정교함).**

이건희가 반도체 만드는 법 모르지만 삼성이 반도체로 떴듯이, 결정자(사용자)는 결과만 받고 실행자(Brain)가 monstrously 정교하게 작동.

→ 메모리 `feedback_simple_front_monster_back` 마스터 정의.

**금지:**
- "단순화" 요청 = frontend만. Backend 단순화 X (alpha 죽음)
- "정교화" 요청 = backend만. Frontend 노이즈 추가 X (사용자 인지 부하)

### 1-2. "굳이?" 테스트
각 데이터/컴포넌트마다:
- **사용자가 이 정보로 액션을 취할 수 있는가?**
- **No** → 폐기 또는 [더보기] expand 안으로
- **Yes** → 유지 + 모던 심플 적용

사용자는 **초보**. 월가 단말기 정보 밀도는 Brain 정직함 표시지 사용자 부담 X.

### 1-3. Framer 모던 심플 톤 (Linear / Vercel / Stripe / Framer.com 톤)

기존 Neo Dark Terminal 토큰 (`_shared-patterns.ts`) 그대로 + 다음 강화:

| 원칙 | 적용 |
|---|---|
| No card-in-card | 외곽 1개, 내부는 spacing(S.xxl=24)으로 섹션 분리 |
| Flat hierarchy | H1 1개 + cap(12) uppercase 라벨 + content |
| Mono numerics | 숫자/티커/시각/단위 SF Mono + tabular-nums |
| Expand on tap | 평소 깔끔, 깊이는 사용자 요청 시 펼침 |
| Color discipline | accent glow는 active/CTA만, 자체 색 토큰으로 정정 |
| Padding 일관 | S.xl(20) 카드 / S.xxl(24) 외곽 / 1px hr separator |
| Hover tooltip | 전문 용어 `borderBottom: 1px dotted` + `<TermTooltip>` |
| No emoji | 🏦🏢⚡▲▼ 폐기 (단, FAB/Bell 등 의도된 마이크로 포인트는 OK) |

### 1-4. 시스템 관리 측면 예외

BrainMonitor / AdminDashboard / SystemHealthBar / VAMSProfilePanel / BacktestDashboard 등 **운영자 전용**은 정보 밀도 유지. 단순화 X. 사용자 노출 X.

---

## 2. 인프라 (모든 cluster 진입 전 박혀야 함)

### 2-1. `data/verity_terms.json`
- VERITY 도메인 용어 사전 마스터 (40+ 용어)
- l3=true 는 외부 공유 금지 내부 자산 (Brain 자체 산출/임계값)
- 카테고리: metric / grade / signal / concept / data_source / internal / time

### 2-2. `framer-components/_termtooltip-block.ts`
- TermTooltip 인라인 블록 마스터 (참조용)
- ESTATE LandexPulse 검증된 패턴 그대로 (320px 박스, viewport edge-aware)
- 각 컴포넌트는 본 마스터에서 ◆MARKER◆ 사이 블록 인라인 복붙

### 2-3. `_shared-patterns.ts` (기존 그대로)
- 디자인 토큰 마스터 — 변경 없음
- TermTooltip 블록 추가는 본 plan v0.2 cycle에 통합 검토

---

## 3. 53 → 27 Cluster Verdict

| # | Cluster | 현재 | After | Δ | 핵심 결정 |
|---|---|---|---|---|---|
| 1 | **Top bar** | 5 | 2 | -3 | SiteHeader (MarketBar+WorldClock 통합 1줄+더보기) + UserActionBell. ScrollingTicker 폐기, LiveVisitors 강등 |
| 2 | **Macro/Sentiment** | 8 | 1 | -7 | MacroHub (tab: KR/US/Crypto/Bond). 초보가 macro 8개 봐서 액션? Brain이 fact_score 흡수 |
| 3 | **Map/Heatmap** | 5 | 1 | -4 | MarketMap (region toggle KR/US/Global + view toggle heatmap/sector) |
| 4 | **Calendar** | 3 | 1 | -2 | EventCalendar (filter: earnings/econ/countdown) |
| 5 | **Validation/Backtest** | 2 | 1 | -1 | 사용자 ValidationPanel 유지. BacktestDashboard → AdminDashboard 흡수 (admin 깊이) |
| 6 | **Alert** | 2 | 1 | -1 | AlertHub (briefing은 view) |
| 7 | **Stock** | 6 | 3 | -3 | StockDashboard / StockDetailPanel / StockSearch. PennyScout/SafePicks → Dashboard preset, CompareCard → Detail sub |
| 8 | **US prefix 잔여** | 3 | 1 | -2 | USDetailHub (Mag7 + Insider + Analyst). USCapitalFlow/Earnings/Econ/Sector/Map은 #2/3/4에 흡수 |
| 9 | **Brain** | 4 | 4 | 0 | 역할 다름 (Monitor admin / Panel·Chat·Report 사용자). Navigation 톤만 통일 |
| 10 | **Bond/ETF** | 3 | 3 | 0 | 자산 다름. 디자인만 모던 심플 적용 |
| 11 | **Trading** | 1 | 0 | -1 | TradingPanel → AdminDashboard 흡수 (운영자 자기 주문 = admin) |
| 12 | **Tax** | 1 | 1 | 0 | TaxGuide (사용자 가이드, 모던 심플 적용) |
| 13 | **News** | 1 | 0 | -1 | NewsHeadline → SiteHeader 더보기 흡수 또는 폐기 |
| 14 | **Today/Bell** | 2 | 1 | -1 | UserActionBell이 TodayActionsCard 흡수 (이미 진행 — 메모리 `project_user_action_queue` 2026-05-04 단일화 반영) |
| 15 | **Admin/System** | 2 | 1 | -1 | AdminDashboard가 SystemHealthBar 흡수 |
| 16 | **Auth** | 3 | 3 | 0 | AuthGate / AuthPage / LogoutButton 표준 분리 |
| 17 | **Mobile** | 1 | 1 | 0 | MobileApp 별도 platform |
| 18 | **VAMS/Watch** | 2 | 2 | 0 | VAMSProfilePanel (운영) + WatchGroupsCard (사용자) |

**총: 53 → 27 (-26).** 약 49% 압축.

---

## 4. 진입 순서 (위험 낮은 순)

| 순 | Step | 컴포넌트 | 위험 | 추정 기간 |
|---|---|---|---|---|
| 0 | 인프라 | verity_terms.json + TermTooltip block | — | ✅ 완료 (2026-05-04) |
| 1 | SiteHeader | Top bar 5 → 2 | 낮음 (장식 영역 위주) | 0.5~1일 |
| 2 | EventCalendar | Calendar 3 → 1 | 낮음 (단순 timeline) | 1일 |
| 3 | AlertHub | Alert 2 → 1 | 중간 (action 영향 가능) | 1일 |
| 4 | MarketMap | Map 5 → 1 | 낮음 (시각화 only) | 1~2일 |
| 5 | ValidationPanel 톤 강화 | 1 → 1 (모던 심플 reference 강화) | 낮음 | 0.5일 |
| 6 | Stock cluster | Stock 6 → 3 | 중간 (drill-down 깊이) | 2~3일 |
| 7 | USDetailHub | US 3 → 1 | 중간 (Mag7/Insider/Analyst 통합) | 1~2일 |
| 8 | MacroHub | Macro 8 → 1 | **높음** (가장 많은 컴포넌트, 사용 깊음) | 2~3일 |
| 9 | 흡수 작업 | Trading→Admin / News→SiteHeader / SystemHealth→Admin | 중간 | 1~2일 |

**총 예상 기간: 10~17일.** 각 step 끝날 때마다 너 republish 1회 + 1~2일 관찰 (사용자 행동 데이터 연속성 확보).

---

## 5. 각 Cluster 상세

### 5-1. SiteHeader (Step 1)

**입력:**
- ScrollingTicker.tsx (640줄) — **폐기**. crypto는 CryptoMacroSensor로 흡수, smartmoney는 StockDashboard로 흡수
- MarketBar.tsx (548줄) — 통합
- WorldClockRow.tsx (462줄) — 통합 (4도시 → 2도시)
- LiveVisitors.tsx (1015줄) — **footer 강등** 또는 admin only

**출력:** `framer-components/SiteHeader.tsx`

**디자인 (1줄, expand on tap):**
```
[● 장 열림]  KOSPI 2,520 +0.5%  │  S&P 5,180 +0.8%  │  서울 14:23  │  [▸ 더보기]
```
- ● 장 열림/닫힘 — KRX + NYSE 이중 점등
- KOSPI + S&P 2개만 (NDX/KOSDAQ/USD/VIX/Gold/Silver는 [더보기] 안)
- 서울 시각 1개 (뉴욕은 ● 점등이 같은 정보)
- [▸ 더보기] expand: O₂ 게이지 + 6개 지수 + 원자재 + freshness

**TermTooltip 적용 후보:** O₂ score, VIX, MARKET_MOOD

### 5-2. EventCalendar (Step 2)

**입력:** MarketCountdown / USEarningsCalendar / USEconCalendar
**출력:** `framer-components/EventCalendar.tsx`
**디자인:** 단일 timeline + filter chip (earnings/econ/countdown)
**TermTooltip 후보:** PEAD (earnings 이벤트에)

### 5-3. AlertHub (Step 3)

**입력:** AlertBriefing / AlertDashboard
**출력:** `framer-components/AlertHub.tsx`
**디자인:** 알림 list + briefing은 카드 1개 view (탭하면 expand)

### 5-4. MarketMap (Step 4)

**입력:** GlobalMapEmbed / USMapEmbed / KRXHeatmap / USSectorMap / SectorHeat
**출력:** `framer-components/MarketMap.tsx`
**디자인:** Region toggle (KR / US / Global) + View toggle (heatmap / sector)
**TermTooltip 후보:** 섹터 명, 지역 명

### 5-5. ValidationPanel 톤 강화 (Step 5)

**입력:** ValidationPanel (이미 모던 심플 reference)
**작업:** TermTooltip 적용 (VAMS, IC, ICIR, MDD, alpha, sharpe, win rate, 손익비)
**디자인:** 6원칙 그대로, 용어 부분만 dotted underline + tooltip

### 5-6. Stock cluster (Step 6)

**입력:**
- StockDashboard (3095줄) — 메인 list, **유지 + filter preset 추가** (PennyScout / SafePicks 흡수)
- StockDetailPanel — 개별 drill-down, **유지 + sub view 추가** (CompareCard 흡수)
- StockSearch — 검색, **유지**
- PennyScout — Dashboard filter preset로 흡수
- SafePicks — Dashboard filter preset로 흡수
- CompareCard — DetailPanel sub view로 흡수

**TermTooltip 후보:** fact_score, brain_score, 13 sub-score 전체, 5 grade

### 5-7. USDetailHub (Step 7)

**입력:** USMag7Tracker / USInsiderFeed / USAnalystView
**출력:** `framer-components/USDetailHub.tsx` 또는 StockDashboard의 view로 흡수
**디자인:** Tab (Mag7 / Insider / Analyst)

### 5-8. MacroHub (Step 8, 가장 위험)

**입력 (8개):**
- MacroPanel
- MacroSentimentPanel
- SentimentPanel
- YieldCurvePanel
- CryptoMacroSensor (ScrollingTicker crypto 흡수까지)
- CapitalFlowRadar
- USCapitalFlowRadar
- GlobalMarketsPanel

**출력:** `framer-components/MacroHub.tsx`
**디자인:** Tab 4개 (KR / US / Crypto / Bond) + 각 tab 안에 macro chips + sentiment + yield curve sub-view
**TermTooltip 후보:** regime, market_mood, VIX, yield curve, foreign flow, institution flow

### 5-9. 흡수 작업 (Step 9)

| 폐기/흡수 | 대상 |
|---|---|
| TradingPanel → AdminDashboard | 운영자 자기 주문 영역 |
| NewsHeadline → SiteHeader 더보기 또는 폐기 | 약한 액션 가치 |
| SystemHealthBar → AdminDashboard | 같은 admin 영역 |
| BacktestDashboard → AdminDashboard | admin 깊이 영역 |

---

## 6. 모던 심플 적용 체크리스트 (각 컴포넌트 republish 전)

- [ ] 디자인 토큰 블록 (◆ DESIGN TOKENS START/END ◆) 인라인 박힘
- [ ] 자체 색 (#FF4D4D, #F7931A, #FFD700 등) 토큰으로 정정
- [ ] 카드-인-카드 폐기 (외곽 1개, 내부는 spacing)
- [ ] 숫자/티커/시각 mono + tabular-nums
- [ ] Emoji 폐기 (예외: FAB/Bell/checkmark 등 의도된 마이크로 포인트)
- [ ] 전문 용어에 `<TermTooltip termKey="...">` + dotted underline 적용
- [ ] Padding S.xl(20) / S.xxl(24) 일관
- [ ] hr separator 1px (`background: C.border`)
- [ ] accent glow 는 active/CTA만 사용
- [ ] Property control 단순화 (16개+ over-engineered 정리)
- [ ] [더보기] expand-on-tap 패턴 적용 (정보 깊이)

---

## 7. 중지 정책

각 step에서 막힘 발생 시:
1. 그 cluster에서 즉시 멈춤
2. 다음 step 미진입
3. 막힘 원인 분석 (메모리 `feedback_decision_logging_separation`)
4. 정정 후 재개

**막힘 트리거:**
- republish 후 사용자 행동 데이터에 회복 불가 단절
- TermTooltip 위치 깨짐 (viewport edge 처리)
- 통합 후 데이터 fetch 실패
- Framer property control 복잡도 폭발

---

## 8. 백엔드 트랙 무관 보장

본 plan은 **frontend only.** Backend 트랙은 직교 운영:

| Backend 트랙 | 이번 plan 영향 |
|---|---|
| ATR Phase 0 verdict (5/16) | **무관** |
| Earnings Layer Sprint (5/16~) | **무관** |
| fact_score v2 가중치 재산출 (10월 말~) | **무관** |
| Brain v5 IC 자동 조정 | **무관** |
| 모든 sub-score 깊이 작업 | **무관** |

Backend는 계속 괴물화. Frontend만 단순화. 이건희-반도체 원칙 그대로.

---

## 9. 버전 관리

| 버전 | 시점 | 내용 |
|---|---|---|
| **v0.1** | **2026-05-04** | **초안 + 인프라 박음** |
| v0.2 | Step 1 (SiteHeader) 완료 후 | 실측 보강 + Step 2 detail 추가 |
| v0.3+ | 각 step 완료 시 | 진행 누적 |

**GitHub commit prefix:** `[verity-revamp]` (cluster 작업) / `[verity-revamp-infra]` (terms/tooltip 인프라)

---

**END OF v0.1**

다음 step: SiteHeader (Top bar 5 → 2). 위험 가장 낮은 cluster부터 시작.
