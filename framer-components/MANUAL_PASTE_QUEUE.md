# Framer 수동 복붙 큐 (PM 전용 · SoT)

MCP 로 라이브 반영이 위험한(대용량 truncation·write-loss) 공개 컴포넌트 목록.
아래 **repo 파일 = 정합 최신본**(라이브 미러 + 픽스 반영 완료). repo 파일 내용을 라이브 Framer 코드파일에 **통째로 복붙**하면 됨.

> Claude 세션/에이전트는 Framer 공개 컴포넌트 작업 진입 시 **이 파일을 먼저 읽고** 중복 작업·롤백을 피할 것 (RULE 11 3소스 동기화 정합).

최종 갱신: 2026-07-23

---

## 전체 복붙 필요 (repo → 라이브)

| repo 파일 | 라이브 코드파일 (id) | 사유 | 반영 내용 | 상태 |
|---|---|---|---|---|
| `public-probe/PublicStockReport.tsx` | PublicStockReport (`wQArrWb`, 391KB) | >60KB MCP write-loss | 보유종목 별 = 연회색 채움(외곽선 제거). 라이브 대비 diff = 별 fill/stroke **2줄만**(라이브 read→패치→repo write, byte-동일 검증) | ⏳ 복붙 대기 |
| `public-probe/SmallcapScreenerAll.tsx` | SmallcapScreenerAll (`bqbqGIU`, ~30KB) | 인라인 truncation 위험 | `readBodyDark` html-first(새로고침 '부분 라이트' fix) | ⏳ 복붙 대기 |
| `public-probe/PublicPerspectiveMaps.tsx` | PublicPerspectiveMaps (`uFqZdln`, home/, 58KB) | >50KB truncation | `readBodyDark` html-first(새로고침 '부분 라이트' fix) | ⏳ 복붙 대기 |

## 라이브 이미 반영됨 (MCP push 완료 · 복붙 불요)

- **PublicTickerSync** (`G9Q8pUl`) — 콜드 랜딩 = 거래대금 1위(hot_stock) 디폴트 + `verity-ticker-change` 디스패치. 리포트·결정·라이브차트·관점기록·AI PDF 공유 종목. typecheck clean.
- 라이브→repo 전체 미러 sweep(~60 컴포넌트) 완료 — admin 콘솔·_shared 포함, repo == 라이브.

---

## 규율

- **복붙 전**: 라이브가 그 사이 수정됐는지 확인(3소스 동기 RULE 11). 어긋나면 라이브 우선 재reconcile 후 repo 갱신.
- **복붙 후**: 위 표 상태를 ✅ 로 갱신 + 날짜 기록.
- **repo 파일 상단 "되돌리지 말 것" 가드 주석 삭제 금지** (dark html-first·별 채움 등).
