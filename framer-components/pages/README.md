# Framer 페이지 매핑 (2026-05-05 v2 — 폴더 정리)

6 페이지 + `_shared` (전 페이지 공유) 구조. 31 활성 컴포넌트.

각 페이지 폴더 = Framer 사이트의 한 페이지에 박을 컴포넌트들.
폴더 = 정리·검색 편의용. Framer manual paste 라 폴더 변경은 사이트 영향 0.

**KR/US 토글 모델**: admin 제외 모든 페이지가 우측 하단 토글로 KR/US 변환.
즉 페이지 6개지만 사실상 12 페이지 분량 (admin 제외 5 × 2).

**v2 변경 (2026-05-05)**:
- `etf-bond/` → `market/` 흡수 (BondDashboard / ETFScreenerPanel)
- `report/` → `portfolio/` 흡수 (VerityReport)
- `global/` → `us/` rename (USDetailHub / USMapEmbed)

---

## 페이지 매핑

| 페이지 | 컴포넌트 | 역할 |
|---|---|---|
| **home** | VerityChat | 진입 시 질문 입력 (Brain on-demand trigger) |
| | AlertHub | 사용자 알림 + briefing |
| **market** | MarketStatus | 시각/장 점등 (KRX/NYSE) |
| | EventCalendar | 이벤트 timeline (earnings/econ/countdown) |
| | MacroHub | KR/US/Crypto/Bond 4 tab macro |
| | CryptoMacroSensor | 코인 sentiment standalone |
| | SectorMap | KR 섹터 rotation |
| | StockHeatmap | KR 종목 시총 가중 heatmap |
| | ETFScreenerPanel | ETF 스크리너 (구 etf-bond 흡수) |
| | BondDashboard | 채권 (구 etf-bond 흡수) |
| **analysis** | StockDashboardV2 | 종목 list + 10 detail tab (메인) |
| | StockDetailPanel | 종목 단독 drill-down |
| | StockSearch | 검색 |
| | ValidationPanel | 검증/백테스트 결과 |
| | VerityBrainPanel | Brain v5 분해 |
| **portfolio** | VAMSProfilePanel | 운영 보유 + 손익 (운영자) |
| | WatchGroupsCard | 관심 그룹 |
| | TaxGuide | 세제 안내 |
| | VerityReport | 리포트 PDF (Brain 학습 input, 구 report 흡수) |
| **us** | USDetailHub | Mag7 + Insider + Analyst tab (구 global) |
| | USMapEmbed | TradingView 미국 맵 (구 global) |
| **admin** | AdminDashboard | 운영자 대시 (잔존 9 카드) |
| | BrainMonitor | Brain Observatory |
| **_shared** | SiteHeader | 상단 1줄 + 더보기 expand |
| | UserActionBell | FAB 52x52 + 빨간 배지 |
| | LiveVisitorPill | footer pill |
| | AuthGate | 로그인 게이트 |
| | AuthPage | 로그인/회원가입 페이지 |
| | LogoutButton | 로그아웃 |
| | MobileApp | 모바일 platform |

---

## 인프라 파일 (framer-components/ 루트)

| 파일 | 역할 |
|---|---|
| `_shared-patterns.ts` | 디자인 토큰 마스터 (Neo Dark Terminal C/G/T/S/R/X/FONT) |
| `_termtooltip-block.ts` | TermTooltip 인라인 블록 마스터 |
| `fetchPortfolioJson.ts` | portfolio.json 공통 fetch helper |
| `netPnlCalc.ts` | 순손익 계산 helper |
| `watchGroupsClient.ts` | watchGroups Supabase 클라이언트 |
| `map-embed-framer-head-snippet.html` | 맵 embed head snippet |

---

## 폐기됨 (Framer 빌드 호환 stub 잔존)

32 컴포넌트 root stub 잔존 (`framer-components/<Name>.tsx`, return null 빈
컴포넌트). Framer 페이지 인스턴스 제거 후 git rm 가능.

cluster: Top bar 4 / Macro 7 / Map 4 / Calendar 3 / Alert 2 / Stock 3 /
US 3 / 기타 5 (TradingPanel / NewsHeadline / TodayActionsCard /
SystemHealthBar / BacktestDashboard) / StockDashboard V1.

---

**관련 문서:**
- `docs/COMPONENT_REVAMP_PLAN_v0.2.md` — 진행 plan
- `docs/DESIGNER_PROMPT_VERITY_v1.md` — v1.1 펜타그램 가이드
- 메모리 `project_pentagram_application` — 펜타그램 적용 reference
- 메모리 `project_stock_dashboard_v2` — V2 풀 재작성 detail
