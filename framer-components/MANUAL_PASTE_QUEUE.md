# Framer 수동 복붙 큐 (PM 전용 · SoT)

MCP 로 라이브 반영이 위험한(>60KB, write-loss) 공개 컴포넌트. **repo 파일 = 정합 최신본** — 통째로 라이브 Framer 코드파일에 복붙.

> Claude 세션/에이전트는 Framer 공개 컴포넌트 작업 진입 시 **이 파일을 먼저 읽고** 중복/롤백 회피 (RULE 11).

최종 갱신: 2026-07-23

---

## ⏳ 지금 복붙 필요 — dark mode html-first fix (새로고침 '부분 라이트' 근본 fix)

body-first `readBodyDark` → html-first 로 정정. body-first 는 Framer 정적 export 의 light body 에 단락돼 새로고침 시 라이트로 stuck. >60KB 라 MCP push 불가.

| repo 파일 | 라이브 코드파일 (id) | 반영 내용 | 상태 |
|---|---|---|---|
| `public-probe/PublicStockReport.tsx` | PublicStockReport (`wQArrWb`, 400KB) | readBodyDark html-first (+ 이전 별 채움 픽스 포함) | ⏳ 복붙 |
| `public-probe/PublicHoldingsTab.tsx` | PublicHoldingsTab (`S2WFHHW`, 191KB) | readBodyDark html-first | ⏳ 복붙 |
| `public-probe/PublicAuth.tsx` | PublicAuth (`k5Rb6uP`, 27KB) | readBodyDark html-first | ⏳ 복붙 |

## ✅ 라이브 이미 반영됨 (MCP push + byte-verify 완료 · 복붙 불요)

- **PublicThemeToggle** (`W_KF9F5`) — body-리셋 자가치유(로그아웃 복귀 fix)
- **PublicSessionTag** (`qcBvPxE`) — html-first
- **PublicThesisFeed** (`WaAJVHx`) — html-first (init + 폴백 effect)
- **PublicTickerSync** (`G9Q8pUl`) — 거래대금 1위 hot_stock 디폴트 + 이벤트 디스패치
- 라이브→repo 전체 미러 sweep(~60) 완료

## 📌 참고 — 이미 복붙 완료된 과거 항목
- PublicStockReport 별 연회색 채움 · SmallcapScreenerAll · PublicPerspectiveMaps (dark html-first) — 완료

---

## 규율
- **복붙 전**: 라이브가 그 사이 수정됐는지 확인(RULE 11). 어긋나면 라이브 우선 재reconcile.
- **복붙 후**: 위 표 상태를 ✅ 로 갱신.
- **repo 상단 "되돌리지 말 것" 가드 주석 삭제 금지** (dark html-first·별 채움 등).
- **dark 판정 = html-first `readBodyDark`** (html[data-an-theme] → body[data-framer-theme] → verity_theme). body-first 금지.
