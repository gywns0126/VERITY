# Framer 수동 복붙 큐 (PM 전용 · SoT)

MCP 로 라이브 반영이 위험한(>60KB, write-loss) 공개 컴포넌트. **repo 파일 = 정합 최신본** — 통째로 라이브 Framer 코드파일에 복붙.

> Claude 세션/에이전트는 Framer 공개 컴포넌트 작업 진입 시 **이 파일을 먼저 읽고** 중복/롤백 회피 (RULE 11).

최종 갱신: 2026-08-18

---

## 🚨 지금 복붙 필요 — 공개 유리박스에서 폐기된 게이트 제거 (PM 지시 2026-08-18)

**공개 알파네스트가 폐기된 목표치를 지금 이 순간 노출 중이다.** PM 결정
"공개용 사이트 검증 창도 수정 및 폐기 절차".

| repo 파일 | 라이브 코드파일 | 반영 내용 | 상태 |
|---|---|---|---|
| `public-probe/PublicGlassboxTab.tsx` | PublicGlassboxTab | 표본 목표·진행률 제거, 사실만 표기 | ✅ **복붙 완료 2026-08-19 (PM 확인 "정상 뜨네")** |
| ~~`pages/admin/BrainMonitor.tsx`~~ | — | 🚫 **복붙 불요 — 폐기된 컴포넌트** (PM 지적 2026-08-19) |

> 🚨 **1차 복붙은 문법 파손으로 실패했다** (2026-08-19). 툴팁 문자열 안에 큰따옴표를 넣어
> `Expected ',', got '몇' (58:325)` 로 라이브 화면이 에러를 띄웠다. 원인은 검사 부재 —
> 파이썬은 편집마다 `ast.parse` 로 막았는데 tsx 는 아무것도 없었고, 회귀 2,431건이 전부
> 통과한 채로 깨진 파일이 나갔다. 이후 `tests/test_tsx_syntax.py` 가 전수 파싱한다.
> **이 큐에 올리기 전 `npx --no-install esbuild <파일> --outfile=/dev/null` 통과 필수.**
>
> 🚨 **BrainMonitor 를 큐에 올린 것도 내 잘못이다** (2026-08-19 PM 지적 "폐기한지 오래인데?").
> `framer_track_index` 가 이미 적어뒀다 — *`pages/admin/` 중 AdminDashboard·**BrainMonitor**·
> OperatorCockpitCard·SystemMapCard·CapitalEvolutionPath = 구 배리티 소유, **operator-web
> 이관 완료(8/12)** → 라이브 unpublish 후 삭제 가능.* 살아있는 쪽은
> `operator-web/app/components/BrainMonitorPanel.tsx` 이고 그건 8/18 에 이미 처리됐다(624f056a1).
>
> **원인 = `framer_track_index` 를 읽지 않았다.** RULE 11 이 "작업 진입 시 이 파일을 먼저
> 읽고 중복/롤백 회피" 라고 지목한 그 파일이다. `252` grep 에 걸렸다는 이유만으로 살아있는
> 컴포넌트로 취급했다 — **grep 히트는 생존 증거가 아니다.**
> 🚨 큐에 올리기 전 확인 2종: ① esbuild 파싱 ② `framer_track_index` 의 생존/폐기 구분.

### 왜 급한가 — 지금 화면이 틀린 값을 그린다

백엔드는 2026-08-18 에 `validation_summary.json` 의 `gate` 를 **`null`** 로 바꿨다
(표본수 IC 게이트 폐기 정합, PM 결정 2026-08-15). 라이브 blob 실측으로 확인했다.

그런데 컴포넌트 폴백이 `Number(gate.target_n) || 252` 였다. 즉 지금 공개 페이지는

```
N_eff = 0 / 252 · 진척 0.0%
```

를 그린다 — **폐기된 목표를 0% 진행률로 되살린 상태**다. 종전(진척 57.6%)보다 나쁘다.

### 무엇이 바뀌었나

- `MILESTONES` 에서 `N=252 IC 게이트` 제거. **30·100·684 는 유지** (§5 가 유지로 명시).
  684 는 라벨을 "DSR 참조 (목표 아님)" 로 바꿨다.
- 진행률 바·"게이트 도달 ✓" 배지·"다음 관문까지 X%" 전부 제거 → **N_eff 사실 표기**만.
- `interface Gate` 에서 `target_n` · `progress_pct` 삭제 — 타입에 남겨두면 다음 편집자가
  "채워야 할 값" 으로 오해해 폴백을 되살린다.
- 하단 안내문을 정직하게 교체 — "목표 표본까지 몇 %" 를 왜 없앴는지 페이지 자체가 설명한다.
- SAMPLE 상수의 `진척 57.6% / 21.0%` 문자열도 함께 정리 (캔버스 프리뷰가 옛 화면을 보여주지 않게).

### 🚨 되돌리지 말 것

컴포넌트 상단에 가드 주석을 넣었다. 폐기 사유가 **정확히 이 UI 형태**였다 —
검정력을 따지지 않고 표본만 요구하면 출력이 언제나 "더 모아라" 가 된다.
백엔드가 `gate: null` 을 보내므로, 여기서 목표치를 폴백으로 되살리면 폐기가 무효가 된다.

### 미확인 (RULE 11 3소스 중 1개 미검)

🚨 **라이브 Framer 를 읽지 못했다** (MCP 미연결). repo 미러 = `origin/main` 과 일치는 확인했으나,
라이브가 그 사이 따로 편집됐다면 이 복붙이 그것을 덮는다. **붙이기 전에 라이브 코드파일을 먼저 열어
`gate.target_n` / `progress_pct` 참조가 이 파일과 같은 위치인지 눈으로 확인**할 것.
다르면 붙이지 말고 알려주면 3-way 로 다시 맞춘다.

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
