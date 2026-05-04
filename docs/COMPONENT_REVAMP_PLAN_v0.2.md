# VERITY 컴포넌트 정리 + 모던 심플 재디자인 Plan v0.2

**작성:** 2026-05-04 (v0.1) / **update 2026-05-05 (v0.2 마무리)**
**대상:** Frontend (Framer code components, ESTATE 제외)

---

## 진행 결과 요약 (v0.1 9 step 모두 완료, 2026-05-05)

| Step | 완료 | 컴포넌트 | 비고 |
|---|---|---|---|
| 0 | ✅ | verity_terms.json + TermTooltip block | infra |
| 1 | ✅ | SiteHeader (Top bar 5→2) + LiveVisitorPill split | |
| 2 | ✅ | EventCalendar (Calendar 3→1) + MarketStatus 별도 | |
| 3 | ✅ | AlertHub (Alert 2→1) | |
| 4 | ✅ | MarketMap (Map 5→3) | StockHeatmap·SectorMap 별도 폐기 |
| 5 | ✅ | ValidationPanel TermTooltip 적용 | |
| 6 | ✅ | Stock cluster + **StockDashboard V2 풀 재작성** (Step A 정공법 16 turn) | 78 sub-component, Technical tab 통째 retract |
| 7 | ✅ | USDetailHub (US 3→1) | |
| 8 | ✅ | MacroHub (Macro 8→2) + CryptoMacroSensor standalone 유지 | |
| 9 | ✅ | 흡수 작업 + DEPRECATED sweep 33건 | 단순 폐기 결정 (Admin 흡수 거부) |

---

## v0.1 verdict 와 실제 결정 차이 (사용자 결정 반영)

| 항목 | v0.1 verdict | v0.2 실제 결정 | 사유 |
|---|---|---|---|
| BacktestDashboard | Admin 흡수 | **단순 폐기** | ValidationPanel 충분, admin 흡수 거부 |
| TradingPanel | Admin 흡수 | **단순 폐기** | 1인 사용자 검증 단계 불필요 |
| NewsHeadline | SiteHeader 흡수 또는 폐기 | **단순 폐기** | StockDashboardV2 NewsSection 흡수 |
| SystemHealthBar | Admin 흡수 | **단순 폐기** (Step 9 commit `a35a18c`) | admin 운영 영역 단순 정리 |
| CryptoMacroSensor | MacroHub 흡수 | **standalone 유지** | 사용자 운영 인정 (좌측 치우침 fix 2026-05-05 commit `61951ce`) |
| MarketStatus | (verdict 외) | **별도 살림** | EventCalendar 와 다른 layer (commit `bf920c2` "디자인 혁명") |

**원칙 변경**: "Admin 흡수" 가능성은 v0.1 에서 가벼웠음. v0.2 실제 운영 시 admin 영역도 6 카드 retract (Step 9 정정 commit `a35a18c`). 1인 운영자는 정리+압축이 흡수+승계보다 가치 큼.

---

## DEPRECATED 컴포넌트 33건 (2026-05-05 sweep)

| # | Cluster | 컴포넌트 |
|---|---|---|
| 1-4 | Top bar | ScrollingTicker / MarketBar / WorldClockRow / LiveVisitors |
| 5-11 | Macro | MacroPanel / MacroSentimentPanel / SentimentPanel / YieldCurvePanel / CapitalFlowRadar / USCapitalFlowRadar / GlobalMarketsPanel |
| 12-18 | Map | GlobalMapEmbed / USMapEmbed / KRXHeatmap / USSectorMap / SectorHeat / StockHeatmap / SectorMap |
| 19-21 | Calendar | MarketCountdown / USEarningsCalendar / USEconCalendar |
| 22-23 | Alert | AlertBriefing / AlertDashboard |
| 24-26 | Stock | PennyScout / SafePicks / CompareCard |
| 27-29 | US | USAnalystView / USInsiderFeed / USMag7Tracker |
| 30 | Trading | TradingPanel |
| 31 | News | NewsHeadline |
| 32 | Today/Bell | TodayActionsCard |
| 33 | Admin/System | SystemHealthBar / BacktestDashboard |

각 컴포넌트 line 1 에 `⚠️ DEPRECATED (2026-05-05 Plan v0.1 §3 [Cluster] 폐기 결정)` 헤더 박힘. cluster 별 폐기 사유 + 흡수처 + Framer 인스턴스 제거 안내.

---

## 잔존 활성 컴포넌트

| Cluster | 컴포넌트 | 비고 |
|---|---|---|
| Top bar | SiteHeader / UserActionBell / LiveVisitorPill | |
| Macro | MacroHub / CryptoMacroSensor | standalone 2건 |
| Map | MarketMap | |
| Calendar | EventCalendar / MarketStatus | |
| Validation | ValidationPanel | |
| Alert | AlertHub | |
| Stock | StockDashboardV2 / StockDetailPanel / StockSearch | StockDashboard V1 swap 후 폐기 예정 |
| US | USDetailHub | |
| Brain | BrainMonitor / VerityBrainPanel / VerityChat / VerityReport | 역할 다름, 모두 살림 |
| Bond/ETF | BondDashboard / ETFDashboard / ETFScreenerPanel | |
| Tax | TaxGuide | |
| Admin | AdminDashboard (7 카드 잔존, 6 카드 retract) | |
| Auth | AuthGate / AuthPage / LogoutButton | |
| Mobile | MobileApp | |
| VAMS/Watch | VAMSProfilePanel / WatchGroupsCard | |

**총 활성: 28 (V1 swap 후 27)** → v0.1 verdict (27) 거의 도달.

---

## v0.2 후속 흡수 4건 (2026-05-05 사용자 재결정)

이전 verdict 변경 6건 중 4건 다시 흡수로 정정:

| # | 흡수 | commit |
|---|---|---|
| **B1** | BacktestDashboard → AdminDashboard.CardBacktestSummary (period 7d/14d/30d 탭 + 적중률/평균수익/샤프) | `37ec7f0` |
| **B2** | TradingPanel → AdminDashboard.CardMyHoldings (vams.holdings top 5 + 총자산/현금/수익률) | `37ec7f0` |
| **B3** | PennyScout/SafePicks → StockDashboardV2 filter preset chip 2개 ("저가주" / "안전") | `8c7c624` |
| **B4** | NewsHeadline → SiteHeader expand panel 안 시장 뉴스 row 5건 | `5c1097d` |
| **B5** | CompareCard → DetailPanel sub view | **거부** (이미 DEPRECATED 유지, AlertHub 교체 권고로 대체) |

소스 컴포넌트 4건은 DEPRECATED 헤더 유지 (Framer standalone 인스턴스 제거).

---

## 사용자 액션 큐 (Framer republish)

1. StockDashboardV2 swap (action queue id `a39faa21`) + B3 preset chip 포함
2. CryptoMacroSensor 좌측 치우침 fix (action queue id `76a6fa89`)
3. AdminDashboard republish — B1+B2 흡수 (action queue id `e0ec15d6`)
4. SiteHeader republish — B4 흡수 (action queue id `ea43cd13`)
5. DEPRECATED 33 컴포넌트 Framer 페이지 인스턴스 제거 (점진)

---

## 다음 단계

- 1~2주 운영 후 V1 → `_legacy.tsx` rename, 일괄 cleanup commit (git rm 33건)
- 강화/보완 발견 시 단일 fix cycle (mass redesign 거부, 메모리 `project_component_pruning_pending` deprecated → 본 plan v0.2 으로 대체)

---

**END OF v0.2**
