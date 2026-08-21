# Framer 수동 복붙 큐 (PM 전용 · SoT)

MCP 로 라이브 반영이 위험한(>60KB, write-loss) 공개 컴포넌트. **repo 파일 = 정합 최신본** — 통째로 라이브 Framer 코드파일에 복붙.

> Claude 세션/에이전트는 Framer 공개 컴포넌트 작업 진입 시 **이 파일을 먼저 읽고** 중복/롤백 회피 (RULE 11).

최종 갱신: 2026-08-21

---

## 🟠 대기 (2026-08-22) — 둥지 별 마크 통일 + 배지 한 줄 고정

**PM 지적 2건** (스크린샷)
1. 보유종목 추가 UI 가 **보라 배경 + 문자 `★`** 였다 → *"리포트에서 쓰는것처럼 노랑색
   모서리가 둥근 별"*. 같은 사이트에서 같은 뜻의 마크가 두 형태였다.
2. 배지가 **세로로 쌓여 행 높이가 늘었다**(국민연금 1 + 공시 2 + `+1` = 4줄)
   → *"스택 높이 변화 없이도 표시되게끔"*.

**수정**
- `StarMark` 신설 — `PublicStockReport` 헤더 별과 **동일 path** + 소프트골드 `#f6b93b`
  + `strokeLinejoin="round"`. 🚨 문자 `★` 로 되돌리지 말 것(폰트마다 모양·굵기가 달라짐)
- 버튼 배경 `C.vgS`(연보라) → `transparent`, 안내 문구의 `★` 도 같은 마크로
- `NestBadges` = `flexWrap:"wrap"` + `marginTop` **제거** → `inline-flex` + `overflow:hidden`.
  공시는 1건만 표시하고 나머지는 `+N`, 제목 전문은 `title` 툴팁
- 배지를 담는 서브라인(`티커 · N주 · 비중 N%`)에 `whiteSpace:"nowrap"` 고정 —
  이게 없으면 긴 공시 제목에서 여전히 줄바꿈된다

가드 = `test_star_mark_consistency.py` 4건(리포트와 **path 동일** 검사 포함) +
`test_badges_do_not_grow_row_height`. 🚨 두 테스트 모두 1차에 **내 경고 주석이 위반으로
잡히는** 오탐이 났다 — 주석 제거 후 검사하도록 고쳤다(같은 형태를 두 번 겪었다).

| repo 파일 | 라이브 코드파일 | 반영 내용 | 상태 |
|---|---|---|---|
| `public-probe/PublicHoldingsTab.tsx` | PublicHoldingsTab (`S2WFHHW`) | 골드 SVG 별 통일 + 배지 인라인 1줄 고정 | 🟠 **복붙 대기** |

---


## ✅ 완료 (2026-08-22 PM 복붙 · MCP 라이브 검증) — 시장 브리핑 "내 보유 종목 소식"

**PM 요청**: 보유 종목 소식이 **브리핑에도** 보여야 한다(둥지 배지만으로는 부족).
**절충안 채택** — 전용 섹션을 넣되 **겹침 0이면 섹션 자체를 렌더하지 않는다**.
전용 섹션을 처음에 반대했던 이유가 "겹침 0인 날 빈 섹션이 뜬다" 였고, 이 조건이 그 반대를 보장한다.

**변경 3점** (라이브 base, 국소):
1. 상태 2개 `nestIdx` / `npsMap`
2. fetch 훅 1개 — `nest_briefing_index.json` + `nps_holdings.json`
3. 파생값 `myNews`(보유 ∩ 색인) + 섹션 렌더 — `!isDemo && myNews.length > 0` 일 때만

**인증·보유목록은 기존 `/api/holdings` 재사용** (① 내 자산 섹션이 이미 호출).
새 수집·파이프라인·LLM 0. RULE 6 안전 · RULE 7(공시 제목 원문 + 지분율, 점수·추천 0).

**실데이터 검증**
| 케이스 | 섹션 |
|---|---|
| VAMS 보유 11 | **O · 6종목** (삼성E&A nps 7.31%+공시 1 · DVN 공시 1 · NAVER/파마리서치/LG/기아 nps만) |
| 실제 회원 보유(005930) | **O · 1종목** (국민연금 7.26% + 공시 2건) |
| 겹침 0 (미보유 티커) | **X** ← 정상 |
| 보유 0 (비로그인) | **X** ← 정상 |

✅ **RULE 11 3-way diff 완료** — 라이브(1,372줄) vs repo **공백 제외 완전 동일**,
`repo == origin/main`. 라이브 전용 편집 없음 = 덮어쓸 위험 없음.
🚨 MCP 가 4연속 타임아웃 나서 PM 재연결 후 진행했다. 미연결 상태로 미러를 base 삼지 않았다.

| repo 파일 | 라이브 코드파일 | 반영 내용 | 상태 |
|---|---|---|---|
| `public-probe/PublicMorningBriefing.tsx` | PublicMorningBriefing (`AUFKK5X`) | 상태 2 + fetch 훅 + `myNews` 섹션(겹침 0시 미렌더) | ✅ **복붙 완료 2026-08-22** — 마커 8/8 확인, 라이브 vs repo 공백 제외 동일 |

---


## ✅ 완료 (2026-08-22 PM 복붙 · MCP 라이브 검증) — 둥지 보유종목 공시 + 국민연금 배지

**PM 요청**: *"각 회원이 둥지에 보유한 종목이 수파베이스로 저장되니, 그 종목들에 대한
긴급 뉴스 등이 요약으로 나오는 데일리 브리핑이 필요"* + *"국민연금이 보유하고 있는지"*.

**검증 결과 — 종전엔 둘 다 없었다**: `daily_briefing.json` 에 회원 키 0, 빌더에
`user/holding/supabase` grep **0건**(전역 단일 발행). `PublicHoldingsTab` 에
`nps|국민연금` grep **0건**.

**설계 — 회원별 서버 발행이 아니다.** 회원 수만큼 만들면 blob 캐시가 깨지고 비용이
회원 수에 비례한다. **전역 색인 1개**를 캐시로 내리고 브라우저가 `/api/holdings` 로
받은 본인 티커만 고른다. 이 컴포넌트는 **이미 그 API 를 호출**하고 있어 배선이 있다.

**신규 산출물** `data/nest_briefing_index.json` (빌더 `nest_briefing_index_builder.py`)
— KR 388 + US 412 = **800 티커 · 178KB**. 최근 3일 · 종목당 3건.
기존 피드를 직접 안 쓰는 이유 = 크기(US 4.1MB + KR 862KB 는 브라우저가 못 받음).

**실측 커버리지**: VAMS 보유 11종목 중 **7개**, 대형주 10 가정 **10/10** 에 배지 표시.
국민연금 1,071 티커가 공시 799 보다 넓게 걸린다.

🚨 **국민연금은 5% 이상 대량보유 공시가 원천** — 색인에 없다 = **"미보유"가 아니라 "5% 미만"**.
그래서 없으면 **아무것도 표시하지 않는다**. "국민연금 미보유" 라고 쓰면 거짓이 된다.
색인 로드 전(null)에도 안 그린다 — 없음을 단정하지 않기 위해서다.

RULE 6 = LLM 0(결정론적 조회) · RULE 7 = 공시 제목 원문 그대로 + 지분율, 점수·추천 0.
🚨 **뉴스는 v1 미포함** — `news_flash.json` 200건이 티커 연결 **0/200**, 종목별 헤드라인은
분석 풀 한정이라 임의 보유종목을 못 덮는다. 넣으려면 뉴스↔종목 매핑이 선행(별건).

✅ **RULE 11 3-way diff 완료** — 라이브(4,169줄)를 base 로 편집했다. 라이브 vs repo 실질
차이는 프레이머 포매터의 **괄호 1개**뿐(`(onCanvas ? …)` → `onCanvas ? …`, 의미 동일).
`repo == origin/main`. 라이브 전용 편집 없음 = 덮어쓸 위험 없음.

| repo 파일 | 라이브 코드파일 | 반영 내용 | 상태 |
|---|---|---|---|
| `public-probe/PublicHoldingsTab.tsx` | PublicHoldingsTab (`S2WFHHW`) | 상태 2 + fetch 훅 1 + `NestBadges` 컴포넌트 | ✅ **복붙 완료 2026-08-22** — 마커 7/7 확인. 라이브 차이는 포매터 후행쉼표 1개뿐 |

---


## ✅ 완료 (2026-08-22 PM 복붙 · 라이브 검증) — 투자 캘린더 빈 화면 수정

**증상**: PM 신고 "투자 캘린더 작동 안 됨". 실측 = **2026-08-01 부터 3주간 빈 그리드**.
**원인 2겹** (둘 다 `PublicCalendar.tsx`):
1. 초기 월이 `{ y: 2026, m: 6 }`(**7월**) **하드코딩** — 도입 `430172692`(7/12, 최초 구현).
   그날은 7월이 현재라 맞았고, 8/1 부터 조용히 틀렸다. **2026-07 이벤트 = 0건**(전수 확인).
2. 바로 위 fetch 의 *"데이터 있는 가장 가까운 달로 초기 이동"* **주석만 있고 구현이 비어 있었다**
   = 안전망 부재. 1번을 덮어줬어야 할 코드가 없어 그대로 화면에 나왔다.

**수정**: 초기 월 = 오늘 기준 계산 · fetch 후 최근접 데이터 보유 월 자동 이동(`jumpedRef` 1회).
**검증**: esbuild 파싱 0 · tsx 게이트 통과 · 실데이터 시뮬레이션
(오늘 2026-08 → 유지 161건 / 7월 → 8월 이동 / 10월 → 9월 / 2025-11 → 2025-12).
**정상 배제**: blob `HTTP 200 · 351KB · 18:03 생성` · CORS `*` — 데이터·발행은 무결.

🚨 **복붙 전 RULE 11 의무** — 이 건은 **Framer MCP 미연결 상태에서 만든 수정**이라
라이브 3-way diff 를 **못 했다**. repo 미러 최신 커밋이 7/24 라 라이브가 더 신선할 수 있다.
붙여넣기 전 라이브 `PublicCalendar` 를 열어 **7/23 이벤트 리스트 높이 매칭(calH/ResizeObserver)**
가 살아 있는지 확인할 것 — 그게 라이브 전용 편집이라 롤백된 전례가 있다.
통짜 교체가 불안하면 **아래 2훅만 수동 적용**해도 된다(둘 다 국소):
`const [cur, setCur] = useState(...)` 블록 · fetch `.then()` 안 `if (!jumpedRef.current)` 블록.

| repo 파일 | 라이브 코드파일 | 반영 내용 | 상태 |
|---|---|---|---|
| `public-probe/PublicCalendar.tsx` | PublicCalendar (`dwTN2Ws`) | 초기월 하드코딩 제거 + 최근접 월 자동이동 구현 | ✅ **복붙 완료 2026-08-22** — MCP readCodeFile 로 라이브 검증(초기월 `new Date()` · `jumpedRef` · 가드 주석 전부 반영) |

---


## 🟡 대기 (2026-08-21) — 기업 리포트·자료 다크모드 CSS 전환

PM 지시 "기업 리포트·자료 컴포넌트 css로 바꿔서 다크모드 연동".

| repo 파일 | 라이브 코드파일 | 반영 내용 | 상태 |
|---|---|---|---|
| `public-probe/PublicCompanyReports.tsx` | PublicCompanyReports (`qqqztxj`) | JS 다크 감지 제거 → CSS 변수 `--an-cr-*` 구동 | 🟡 **복붙 대기** |

RULE 11 3-way 확인 완료 — 라이브 고유 마커 9종(`__anHyd`·`anReadDark`·`791d29f7e`·
`verityAssetKind`·`verity_theme`·`data-an-theme`·네이버/EDGAR URL 3종)이 repo 미러에
**전부 있고** repo 미러 = `origin/main`. 즉 **stale 미러로 라이브를 덮는 상황이 아니다.**

바뀐 것: `__anHyd`/`anReadDark`/`readBodyDark` + 테마 MutationObserver 삭제 →
모듈 최상단 `AN_PALETTE`(`body` / `body[data-framer-theme="dark"]`) + `C` = `var(--an-cr-*)`.
`data-verity-asset-kind` 옵저버(ETF 숨김)는 **테마와 무관하므로 유지**했다.

🚨 함정 2개를 미리 막았다:
- `<style>{AN_PALETTE}</style>` 를 **반환 분기 2곳 모두**에 넣었다. 조기 반환(종목 미선택)에서
  빠뜨리면 그 화면만 색이 죽는다.
- SVG 화살표의 `stroke={C.vt}` → `style={{ stroke: C.vt }}`. 프레젠테이션 attribute 에서는
  CSS 변수가 해석되지 않아 선이 사라진다.

검증 = esbuild 통과 · JS 다크 감지 코드 0(주석만 잔존) · `C.<key>` 7종 전부 LIGHT/DARK 에 존재 ·
LIGHT↔DARK 키 불일치 0 · `tests/test_tsx_syntax.py` 전수 통과.

🚨 **아래 규율의 "dark 판정 = html-first `readBodyDark`" 는 아직 전환 안 된 컴포넌트용이다.**
CSS 변수로 전환한 컴포넌트는 JS 가 테마를 읽지 않는 것이 정답이라, 이 항목은 위반이 아니다
([[project_theme_branch_divergence_2026_07_31]] codemod 1~5).

---

## ✅ 완료 (2026-08-19 PM 확인) — 공개 유리박스 폐기 게이트 제거

**공개 알파네스트가 폐기된 목표치를 지금 이 순간 노출 중이다.** PM 결정
"공개용 사이트 검증 창도 수정 및 폐기 절차".

| repo 파일 | 라이브 코드파일 | 반영 내용 | 상태 |
|---|---|---|---|
| `public-probe/PublicGlassboxTab.tsx` | PublicGlassboxTab | 표본 목표·진행률 제거 + 🚨 로드 판정 `gate`→`signals` 정정 | ✅ **복붙 완료 2026-08-19** (총 3회 — 게이트 제거 · 문법 파손 정정 · 로드 판정 정정) |
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

## ✅ 완료 (2026-08-19 PM 확인) — 공개 blob CDN 우회 제거 · 15파일 21개소

PM 지시 2026-08-19 "고쳐. 내가 복붙할게". 파일 = `public-probe/` 아래 그대로, 이미 수정 반영됨.

### 왜 — 같은 사고가 7/20 에 이미 있었다

메모리 원문: *2026-07-20 Vercel 청구 급증(Fast Origin Transfer 62GB=$16.91, Blob 18GB).
방문자 아님. 범인 = `pages/*` 33개 컴포넌트가 공개 blob 을 캐시버스터+no-store 로 fetch.*

그때 `pages/*` 는 고쳤는데 **`public-probe/`(공개 알파네스트)는 그대로 남았다.**
실측(8/19) — 공개 blob fetch **23개소가 `cache:"no-store"`**. CDN 은 정상 작동 중이었다
(`x-vercel-cache: HIT · age 1954 · s-maxage=300`) — **컴포넌트가 그걸 우회하고 있었다.**
`portfolio.json` 이 891KB 라, 탭을 열 때마다 origin 에서 통째로 재다운로드된다.

### 무엇이 바뀌었나 — `{ cache: "no-store" }` 인자만 제거

```
- fetch(validationUrl, { cache: "no-store" })
+ fetch(validationUrl)
```

로직·URL·에러 처리 전부 그대로다. **CDN 이 30초(s-maxage=300) 캐시하므로 신선도 손실은
최악 30초**이고, 원본 데이터는 그보다 훨씬 느리게 갱신된다.

| 파일 | 개소 | | 파일 | 개소 |
|---|---:|---|---|---:|
| `PublicHoldingsTab.tsx` | 3 | | `PublicEntranceMap.tsx` | 1 |
| `PublicMarketTab.tsx` | 3 | | `PublicEventHistory.tsx` | 1 |
| `PublicMorningBriefing.tsx` | 2 | | `PublicFreshnessBoard.tsx` | 1 |
| `PublicNPSHoldings.tsx` | 2 | | `PublicGlassboxTab.tsx` | 1 |
| `CryptoDilutionForensics.tsx` | 1 | | `PublicPerspectiveMaps.tsx` | 1 |
| `CryptoNews.tsx` | 1 | | ~~`PublicQuarterlyTrend.tsx`~~ | 폐기 |
| `PublicBondRegime.tsx` | 1 | | `PublicWatchlist.tsx` | 1 |
| `PublicCompanyReports.tsx` | 1 | | ~~`PublicDailyBriefing.tsx`~~ | 폐기 |
| `PublicETFFlow.tsx` | 1 | | | |

> 🚨 **2026-08-19 정정 — 2파일은 PM 이 폐기 결정하고 삭제했다.** 큐에서 제외한다.
> `PublicDailyBriefing.tsx`(1개소) · `PublicQuarterlyTrend.tsx`(1개소) → **복붙 대상 15파일 21개소.**
>
> 🚨 **`framer_track_index` 에는 이 둘의 폐기 기재가 없었다.** 오히려 `public-probe/` 전체가
> "삭제 절대 금지" 로 적혀 있어, 그 파일만 봤다면 반대로 판단했을 것이다. 즉 이번 건은
> 색인 미독이 아니라 **색인에 없던 PM 결정**이다(어제 BrainMonitor 오등록과 다른 경우).
>
> **수집·발행은 유지한다** — 두 산출물을 다른 컴포넌트가 계속 읽는다:
> `daily_briefing.json` → `PublicMorningBriefing.tsx` · `dart_quarterly_public.json` → `PublicStockReport.tsx`.
> 컴포넌트가 죽었다고 빌더를 끄면 살아있는 화면이 빈다.

🚨 `PublicGlassboxTab.tsx` 는 **어제 게이트 제거분과 합쳐진 최신본**이다. 어제 것을 이미
붙였어도 이 파일은 **다시 붙여야** 한다.

### 🚨 건드리지 않은 것 (일부러)

`no-store` 가 남은 곳은 전부 **blob 이 아니다** — 고치면 오히려 깨진다:
- 자체 API 라우트(`/api/verity/*`, `/api/thesis*`, `/api/holdings` 등) = 동적 응답, 인증 포함
- 외부 거래소 API(바이낸스·업비트) = 우리 비용 아님
- Supabase(`/rest/v1/`) = 인증 쿼리
- `PublicDisclosureFeed.tsx:477` = `DEFAULT_API` 가 blob 이 아니라 우리 API 서버

### 검증

전 72개 `public-probe/*.tsx` esbuild 파싱 **파손 0**. `git diff` = 23개소 모두
`, { cache: "no-store" }` 인자 제거만(로직 변경 0).

---

## 🟡 라이브 반영 여부 미확인 — dark mode html-first fix

🚨 **2026-08-19 정정 — repo 파일은 셋 다 이미 html-first 다.** PM 지적("파일 업데이트 안됐던데")으로
실측했다. 세 파일 모두 `html[data-an-theme]` → `body[data-framer-theme]` → `verity_theme` 순서이고
`body-first 금지 — 되돌리지 말 것` 가드 주석까지 들어 있다.

즉 **이 항목은 "파일을 고쳐야 한다" 가 아니라 "라이브에 붙었는지 모른다" 였다.** 큐가
7/23 이후 갱신되지 않아 ⏳ 로 남아 있었을 뿐이다.

| repo 파일 | 라이브 코드파일 (id) | repo 상태 | 최종 수정 | 라이브 반영 |
|---|---|---|---|---|
| `public-probe/PublicStockReport.tsx` | PublicStockReport (`wQArrWb`, 400KB) | ✅ html-first 적용됨 | 08-09 | ❓ 미확인 |
| `public-probe/PublicHoldingsTab.tsx` | PublicHoldingsTab (`S2WFHHW`, 191KB) | ✅ html-first + CSS 변수 | **08-19**(오늘 CDN 수정 포함) | ❓ 미확인 |
| `public-probe/PublicAuth.tsx` | PublicAuth (`k5Rb6uP`, 27KB) | ✅ html-first 적용됨 | 07-23 | ❓ 미확인 |

**판단 근거** — 새로고침 시 "부분 라이트" 가 **안 나오면** 라이브에 이미 반영된 것이다.
나오면 그 파일만 붙이면 된다. 🚨 `PublicHoldingsTab` 은 오늘 CDN 우회 제거분이 들어갔으므로
**어느 쪽이든 붙여야 한다**(이미 15파일 큐에서 붙였다면 완료).

🚨 **교훈 — 큐 항목은 "파일 상태" 가 아니라 "라이브 반영 여부" 를 추적한다.**
파일이 이미 고쳐졌는데 ⏳ 로 남아 있으면 다음 세션이 없는 일을 하려 든다.
닫을 때 repo 상태와 라이브 상태를 **따로** 적는다.

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
