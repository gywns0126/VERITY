# Framer 수동 복붙 큐 (PM 전용 · SoT)

MCP 로 라이브 반영이 위험한(>60KB, write-loss) 공개 컴포넌트. **repo 파일 = 정합 최신본** — 통째로 라이브 Framer 코드파일에 복붙.

> Claude 세션/에이전트는 Framer 공개 컴포넌트 작업 진입 시 **이 파일을 먼저 읽고** 중복/롤백 회피 (RULE 11).

최종 갱신: 2026-08-24

---

## 🟠 대기 (2026-08-25) — 거장 순매수 TOP 10 (검색 대기 화면, PM 승인)

**대상** = `PublicInvestorPortfolios.tsx` (`Ayy74xh`) · **repo 통짜 재복붙** (직전 ✅ 완료본 위 추가만).
내용 = 검색창 비어 있을 때 카드 안에 "이번 분기 거장 순매수 TOP 10" 노출, 행 클릭 = 보유 표.
🚨 **랭킹 기준 = 펀드 수(신규+증액−감액)** — `value_change_usd` 는 주가 등락이 섞여
"순매수" 라벨 불가(13F 필드 규약), `change_type` 은 주식수 delta = 순수 매매 행동.
'수익률' 라벨 금지 규율과 같은 뿌리 — 평가액 랭킹으로 되돌리지 말 것.
실데이터 실측 = 1위 비자 +7(증액7) · SPCX 신규5 · 알파벳 +5(증액7·감액4).

**+ 8/25 2건째(같은 복붙에 포함) — "편입 분기가" 열.** PM "매수가도 표시할 수 있나" →
🚨 **13F 는 매수 체결가 미공시** — 표시 가능한 정직한 값 = 연속 보유 시작 분기말 내재가
(평가액÷주식수, `held_since_qend_price_usd`). 라벨 = "편입 분기가" · **'매수가' 단독 표기
금지**(빌더·컴포넌트 주석 고정). 실측 = Berkshire AAPL $210.62(2024-06-28 종가와 일치) ·
GOOGL $243.10. 🚨 **데이터 선행 조건** = `us_smart_money_13f` 워크플로 재실행 후 blob 착지
(그 전 복붙 시 해당 열 "—" — 깨지지 않음).
**+ 8/25 3건째(같은 복붙에 포함) — 검색 인덱스 합집합.** PM 승인 "ㄱㄱ" (13F 필터 정비).
13F 종목 축이 sp1500 게이트 → **ETF 만 제외**로 재정의되면서(TSM 8펀드가 "보유 없음"
거짓 표면), universe_search 에 없는 거장 보유(해외 ADR)도 검색되게 **universe ∪ 13F
합집합**으로 확장. 한글명 없는 종목은 영문 issuer 로 검색됨(한계 명시).

**+ 8/25 4건째(같은 복붙에 포함) — ETF 포함·분리 설계.** PM "ETF 는 필수지" →
보유 사실 표면(검색·보유 표) = **ETF 포함**(`is_etf` 뱃지 "티커 · ETF") /
**순매수 TOP10 랭킹·콘솔 강제편입 = 개별주만**(ETF 매수 ≠ 개별 종목 확신 — 신호 희석).
"보유 없음" 문구도 정정(인덱스 **운용사** 제외라는 뜻으로 — ETF 보유 집계와 구분).

검증 마커 = `순매수 TOP 10` · `신규+증액−감액` · `편입 분기가` · `합집합` · `ETF · ` (문자열 grep).

---

## ✅ 완료 (2026-08-25 PM 복붙 · 발행 번들 실측) — 거장 페이지: 종목 클릭→리포트 + 보유 검색

✅ **반영 실측 (전언 아님, 8/25).** `/master` 페이지 번들 11개 grep — `an-ipf-smstbl` ·
`종목명·코드 검색` · `거장 보유 없음` · `보유 시작` 각 1개 번들 + `universe_search.json`
3개 번들(타 검색창 공용이라 3 = 정상) = **5/5 착지**. PM 확인 "잘작동함".
잔여 = 데이터 쪽 N=2 (9/1 정기 cron, held_since 채움 유지 확인)만.

**대상** = `PublicInvestorPortfolios.tsx` (`Ayy74xh`) · **repo 파일 통째로 복붙.**
base = 8/24 역동기 완료본(아래 "통화 토글" 완료 항목의 정량 대조 4/4) 위에 추가만 얹음 —
PM 이 그 복붙 이후 라이브를 또 손댔다면 통짜 전에 알릴 것.
(PM 결정 8/24: 별도 컴포넌트 대신 **기존 컴포넌트 안에 통합** — `PublicSmartMoneySearch.tsx`
신규안은 repo 에서 삭제, 캔버스 신규 배치 불필요.)

내용 2가지:
1. **종목 클릭 → 리포트** — 보유 종목 행 클릭 시 `/stock?q=티커` 이동
   (AlphaNestFeed·PublicETFFlow 와 동일 규약, 캔버스에서는 이동 안 함)
2. **종목 역조회 검색창** — 헤더 아래 삽입. 티커/회사명 검색 → 해당 종목을
   **누가(16개 운용사) · 얼마나(평가액·펀드 내 비중·주식수) · 언제부터(연속 보유 시작,
   9분기 역추적, "이전부터"=창 상한) · 분기 변화** 표. 펀드명 클릭 = 아래 인물 목록으로 점프.
   기준일(report_date) 열 + 45일 지연·롱온리 caveat (13F 메모리 계약). 환율 토글 공유.

🚨 8/24 2차 — 검색창을 **사이트 공통 규약으로 정렬**(PM "왜 거장만 다르냐" 지적):
디자인 = NPSHoldings 원형(돋보기 SVG·회색 필드 radius 12·13px·× 클리어·보더 0),
방식 = HoldingsTab 원형(substring+정확>접두>포함 랭킹·상위 8·**입력 아래 인라인 목록**,
오버레이 드롭다운 아님·로고+이름/티커 2줄·선택 시 입력 초기화). 되돌리지 말 것.

🚨 8/24 3차 — **"애플" 미검색 사고 fix.** 13F name = SEC 영문 issuer 라 한글 검색 전멸이었다.
검색 인덱스를 **universe_search.json**(전 검색창 공통 소스, name_ko 포함)으로 교체 —
US 5,324종목 전체 탐색 + 거장 보유 1,021 표시(전수 조인 100% 검수). 미보유 종목 선택 =
"거장 보유 없음" + 종목 리포트 이동(막다른 골목 금지). 실데이터 검증 = 애플→AAPL(8펀드) ·
엔비디아→NVDA · 테슬라→TSLA · 삼성전자→0건(KR 제외 안내). 한글 매칭 = raw substring.

검증 마커(발행 번들 grep, 지역 변수명 금지 — 문자열/클래스만):
`an-ipf-smstbl` · `"?q="` · `보유 시작` · `이전부터` · `종목 검색 데이터 URL` ·
`종목명·코드 검색` · `검색 인덱스 URL (한글명)` · `거장 보유 없음`

🚨 **데이터 선행 조건 = 이미 충족** — 8/24 빌더 확장분(`held_since` 등)이 N=1 run 으로
blob 재발행 완료(2,269/2,269 채움 실측). 복붙 즉시 정상 표시.

---

## ✅ 완료 (2026-08-24 PM 복붙 · 발행 번들 실측) — 거장 통화 토글 우측 쏠림

PM 스크린샷: 설명 문구·환율 문구는 왼쪽에 붙어 있는데 **USD/KRW 토글만 어중간하게 오른쪽**.

**원인 = `flexWrap:"wrap"`.** 좁은 폭에서 우측 열이 자기 줄로 접히면, 그 열의 폭이
`justify-content:space-between` 아래 홀로 남아 **내용 폭(= 환율 문구 폭)** 으로 줄어든다.
그 안의 `align-items:flex-end` 가 토글(문구보다 좁다)을 **문구 오른쪽 끝**으로 민다.
결과 = 좌·우 어디에도 안 맞는 위치. 🚨 8/09 의 3연속 수정은 **데스크톱 우측 여백** 건이라
원인이 다르다 — 그 수정들을 되돌린 것이 아니다(inline-grid·fit-content 그대로).

**해법** = ① `nowrap` 으로 "접혔는데 우측정렬" 상태 자체를 없앤다(좁아지면 왼쪽 글이 대신
줄바꿈) ② 700px 이하에서만 세로 스택 + 좌측정렬. 정렬은 전부 `AN_IPF_CSS` 미디어쿼리로
옮겼다 — 인라인이 미디어쿼리를 덮기 때문이고, 이 파일의 기존 규약이다.

🚨 **라이브 드리프트 실측(RULE 11)** — 라이브/repo 정량 3단 = 문자 +3,805 · **공백제거 +19** ·
**식별자 ±0**. 분류 결과 대부분 프리티어 노이즈(후행 쉼표·`{""}`)였고, **실 변경 1건**이
라이브에만 있었다 = 제목 `fontSize 24→20 · fontWeight 800→700`(PM 이 라이브에서 직접 줄인 값).
repo 로 **역동기 완료**. 즉 지금 repo = 라이브 + 이번 수정 → **통짜 복붙 가능**.

**대상** = `PublicInvestorPortfolios.tsx` (`Ayy74xh`) · repo 파일 통째로.


✅ **반영 실측 (전언 아님).** 발행 사이트 HTML 에서 `framerusercontent.com/sites/2QiUuP9OY5me9trZ46mVcJ/*.mjs`
번들 19개를 받아 마커 grep:

| 번들 | 마커 | 결과 |
|---|---|---|
| `ytmlOwIjqrPV…DPgtZSwA.mjs` (33,299 B) | `an-ipf-hdr` `an-ipf-fxcol` `an-ipf-fxtoggle` `an-ipf-fxrate` | **4/4 존재** (대조군 `an-ipf-side` 도 존재) |
| 〃 | `flex-direction:column;align-items:flex-start` | 1건 = 미디어쿼리 블록 착지 |
| 〃 | `fontSize:20` | 2건 — 🚨 PM 이 라이브에서 줄인 제목값 **보존 확인**(역동기가 맞았다) |
| `iRg0Vtg83bJ7…bGfBcuZv.mjs` (60,334 B) | `repeat(7, minmax(0, 1fr))` | 2건(스켈레톤+본 그리드) · 구버전 `repeat(7,1fr)` **0건** |
| 〃 | `padding:0` / `minWidth:0` | 셀 버튼 착지 확인 |

🚨 `jumpedRef` 같은 **지역 변수명은 0건이 정상** — 미니파이로 이름이 바뀐다. 클래스명·문자열
리터럴만 마커로 쓸 것.

---

## ✅ 완료 (2026-08-24 PM 복붙 · 발행 번들 실측) — 투자 캘린더 Sun 열 잘림

PM: "폭이 좁아지면 삐져나옴. 380px 까진 괜찮은데 아이폰 미니는 비율이 살짝 깨져 보임."

**원인 = `gridTemplateColumns: "repeat(7,1fr)"`.** CSS 에서 `1fr` 은 `minmax(auto,1fr)` 이라
열이 **내용 최소폭 아래로 못 줄어든다**. 셀 최소폭 = 점 3개(5×3) + 간격(3×2) + `+11`(≈15px)
+ **버튼 UA 기본 padding(≈12px)** ≈ 51px. × 7 + 그리드 간격 12 + 카드·래퍼 좌우 56
≈ **425px**. 그 아래에서는 그리드가 카드보다 넓어져 7번째 열(Sun)이 밖으로 밀려 잘린다.

**해법 3줄** = `minmax(0, 1fr)`(최소폭 바닥 해제) + 셀 버튼 `padding: 0`(UA 여백 84px 회수)
+ `minWidth: 0`(그리드 자식 축소 허용). 셋은 한 쌍이다 — `minmax(0,·)` 만 넣으면 내용이
셀 밖으로 넘치고, `padding:0` 만 넣으면 최소폭 바닥이 그대로다.
🚨 위 px 는 **코드에서 계산한 값이지 브라우저 실측이 아니다.** 다만 고침 자체는 이 숫자에
의존하지 않는다 — 최소폭 바닥을 없애는 것이라 어떤 폭에서도 7열이 들어간다.
잔여 한계 = 셀이 ~37px 아래로 내려가면(뷰포트 ≈325px 미만) 점·카운터가 셀을 넘친다.

🚨 **이 파일은 정량 드리프트 미확인이다.** 라이브 응답이 파일로 안 떨어져 3단 대조를 못 했고,
마커 대조(8/21 가드·`jumpedRef`·`LIST_CAP`·`calH`·`data-an-theme` 등 10종)만 일치 확인했다.
**통짜 복붙 금지 — 아래 3곳 라인 교체만.** 라이브는 프리티어로 펼쳐져 있어 repo(압축형)와
줄 모양이 다르다.

**대상** = `PublicCalendar.tsx` (`dwTN2Ws`) · 변경 3곳:
1. 스켈레톤 그리드 `gridTemplateColumns: "repeat(7,1fr)",` → `"repeat(7, minmax(0, 1fr))",`
   (바로 아래 줄이 `gap: 8,` 인 쪽)
2. 본 그리드 같은 줄 → 같은 값 (바로 아래 줄이 `gap: narrow ? 2 : 4,` 인 쪽)
3. 날짜 셀 `<button>` style 의 `border: "none",` 다음 줄에 `padding: 0,` 과 `minWidth: 0,` 추가


✅ **반영 실측 (전언 아님).** 발행 사이트 HTML 에서 `framerusercontent.com/sites/2QiUuP9OY5me9trZ46mVcJ/*.mjs`
번들 19개를 받아 마커 grep:

| 번들 | 마커 | 결과 |
|---|---|---|
| `ytmlOwIjqrPV…DPgtZSwA.mjs` (33,299 B) | `an-ipf-hdr` `an-ipf-fxcol` `an-ipf-fxtoggle` `an-ipf-fxrate` | **4/4 존재** (대조군 `an-ipf-side` 도 존재) |
| 〃 | `flex-direction:column;align-items:flex-start` | 1건 = 미디어쿼리 블록 착지 |
| 〃 | `fontSize:20` | 2건 — 🚨 PM 이 라이브에서 줄인 제목값 **보존 확인**(역동기가 맞았다) |
| `iRg0Vtg83bJ7…bGfBcuZv.mjs` (60,334 B) | `repeat(7, minmax(0, 1fr))` | 2건(스켈레톤+본 그리드) · 구버전 `repeat(7,1fr)` **0건** |
| 〃 | `padding:0` / `minWidth:0` | 셀 버튼 착지 확인 |

🚨 `jumpedRef` 같은 **지역 변수명은 0건이 정상** — 미니파이로 이름이 바뀐다. 클래스명·문자열
리터럴만 마커로 쓸 것.

---

## 🔴 대기 (2026-08-23) — 로그인 카드가 "처리 중…" 에서 영구히 멈춘다

PM 신고 스크린샷: `/login` 카드가 **처리 중…** 인 채 이메일·비밀번호 칸은 **비어 있다**.

🚨 **재현하지 못했다.** Chrome 확장 미연결이라 라이브 페이지를 못 열었고, DB 조회는 분류기가
막았다. 아래는 **코드에서 확정되는 결함**이고 신고 상태와 정합하나, **원인 확정은 아니다.**

✅ **PM 확인(8/23) = "구글로 로그인은 끝났는데 돌아오니 저 상태".** 구글 경로 확정.
✅ **복붙 후 재관측 = "10초쯤 멈췄다가 메시지 · 주소창이 잠깐 바뀌었다가 돌아왔다".**
🚨 **이 조합이 원인을 좁힌다** — 10초 타이머가 발화했다는 건 **그 페이지의 JS 문맥이 살아
있었다**는 뜻이다. 즉 브라우저가 구글로 **떠났다가 되돌아온 게 아니라, 이동이 시작됐다
중단되고 원래 문서가 그대로 남았다.** (떠났다 돌아왔으면 새 로드로 타이머가 사라지거나,
bfcache 복원이면 `pageshow(persisted)` 가 먼저 해제한다 — 둘 다 메시지가 안 뜬다.)
남은 후보 = **accounts.google.com 으로의 이동을 확장/네트워크가 취소**하는 축.

✅ **라이브 반영 검증 방식 = 발행 번들 실측(추론 아님).** MCP 쓰기는 하지 않았다 —
`updateCodeFile` 미호출, 라이브에는 읽기만. 반영 주체는 **PM 복붙**이다. 확인은 발행 사이트가
실제로 받는 번들
`framerusercontent.com/sites/2QiUuP9OY5me9trZ46mVcJ/Zpt_YHB0KN…`(24,158 B)을 받아
마커 3종(`이동하지 못했습니다` · `서버 응답이 없습니다` · `pageshow`) **전부 존재**로 했다.
🚨 종전 기재 "신 문구 발현으로 확인" 은 **추론**이었다 — 같은 결론이지만 근거가 달랐다.

✅ **브라우저 실측(8/23, PM Chrome 연동 후) = 전 구간 정상 통과.** `/login` 에서 구글 버튼
1회 클릭 → Supabase `/authorize` → 구글(계정 선택 화면 없이 즉시 통과) → `/auth/v1/callback`
→ `https://www.alphanest.kr/login#access_token=…` → `consumeHash` → `afterLoginPath=/me`
이동까지 **끊김 없이 완료**, `/me` 에 로그인 상태로 착지(관리자).
🚨 **이로써 Redirect URLs 축은 해소된다** — callback 이 `alphanest.kr/login` 을 받아 그리로
되돌려줬다는 것이 곧 허용목록 등재의 증거다. 종전 "허용목록 의심" 은 **기각**.
🚨 **동시에 원래 증상은 재현되지 않았다.** 따라서 "고쳤다" 고 말할 수 없다 — 이번 수정은
막다른 골목(재시도 불가)을 없앤 것이고, 중단의 원인은 **미규명**이다. 재발 시 확보할 것 =
주소창 URL 전문 + 콘솔 에러 + 다른 브라우저/시크릿 재현 여부.

**Supabase 축 실측(GET 2회, 부작용 0)** — `/auth/v1/authorize` 는 정상이다: 302 →
`accounts.google.com`, `client_id=684365722039-…`, `redirect_uri=…/auth/v1/callback`,
`redirect_to=https://www.alphanest.kr/login` 동봉. 🚨 **단 이것으로 Redirect URLs 허용목록을
증명하지 못한다** — 대조군 `redirect_to=https://example.com/x` 도 **같은 302** 를 받는다.
검증은 `/authorize` 가 아니라 `/callback` 단계에서 일어난다. **허용목록 축은 미검증 존치.**
🚨 **그러면 이 수정은 화면 고착만 푼다 — 로그인 자체는 여전히 안 될 수 있다.** 복귀가
로그인된 상태로 착지하지 않았다는 뜻이므로 **Supabase Auth → URL Configuration** 축이 남는다:
`redirectUrl=""` 이라 복귀 주소는 `currentBack()` = `https://www.alphanest.kr/login` 이고,
이 주소(또는 와일드카드)가 **Redirect URLs 에 없으면 Supabase 가 Site URL(VERITY)로 튕긴다**
(컴포넌트 상단 주석의 수동 선행 항목). PM 확인 = 구글 인증 직후 **주소창 도메인** 과
해시가 `#access_token=` 인지 `#error=` 인지.

**확정 결함 = `busy` 를 되돌릴 경로가 없다.** `googleLogin` 은 `setBusy(true)` 후
`window.location.href` 만 세우고 **`finally` 가 없다.** 이동이 일어나지 않으면 busy 가 영구
true 이고, 두 버튼 다 `disabled={busy}` 라 **새로고침 말고는 재시도할 방법이 없다.**
🚨 **입력칸이 비어 있는 것이 이 경로를 가리킨다** — 이메일 제출은 빈 입력을 `setBusy` 전에
반려하므로 "빈 칸 + 처리 중" 조합이 나올 수 없다.

가장 그럴듯한 촉발 = **bfcache**. 구글로 이탈했다가 **뒤로가기**로 돌아오면 브라우저가 React
상태를 통째로 복원해 `busy=true` 가 살아 돌아온다. 되돌아온 이유는 별도 축이다 — Supabase
Auth → URL Configuration 의 **Redirect URLs 에 AlphaNest 도메인이 없으면** 구글 복귀가
Site URL(VERITY)로 튄다(코드 상단 주석의 수동 선행 항목). **PM 확인 필요.**

**조치 5** ① `timedFetch` 신설 15s — 타임아웃 없는 `await fetch` 는 `submit` 의 `finally`
자체에 도달하지 못한다 ② `supaFetch` 경유 ③ `ensureProfile` 경유 — 🚨 **토큰 발급 성공
'후' 에 await 되는 지점**이라 여기서 멈추면 `saveSession` 전에 고착된다 ④ `consumeHash` 의
`/auth/v1/user` 경유 ⑤ `pageshow(persisted)` + `focus` 에서 busy 해제 · 이동 미발생 시
10초 후 해제 + 사유 표시. 🚨 `focus` 해제는 **구글 이탈 시도(`navPendingRef`)에만** 건다 —
무조건 풀면 이메일 제출 중에 busy 가 풀려 **이중 제출**이 난다.

검증 = esbuild 종료코드 0 · RULE 9 0건. 🚨 **런타임 미검증**(재현 못 함) — 정적 통과는
안전이 아니다([[feedback_green_check_is_not_safety]]).

**드리프트 대조 — 선언·마커 단위까지만 했다.** 라이브 read 는 전문을 했으나 결과가 파일로
떨어지지 않아 **바이트 3단 대조는 못 했다.** 대신 미러의 선언 28개(SESSION_KEY … readBodyDark
+ addPropertyControls)와 주석 날짜 마커 3개(2026-07-13·07-20·07-23)를 라이브 전문과 대조해
**라이브 전용 구성물 0** 을 확인했다. 라이브는 prettier 포맷만 다르다.

🚨 **반영은 PM 복붙으로 한다(권장 정정).** `updateCodeFile` 은 **전체 내용 교체**라 내가 700줄을
다시 써 보내야 하고, 한 줄만 흘려도 **공개 사이트 로그인 경로**가 통째로 죽는다. repo 파일을
그대로 복사하면 바이트가 정의상 정확하다. 종전 "MCP 직접 반영 권장" 은 이 제약을 빠뜨린 판단이다.

| repo 파일 | 라이브 코드파일 | 반영 내용 | 상태 |
|---|---|---|---|
| `public-probe/PublicAuth.tsx` | PublicAuth (`k5Rb6uP`) | busy 고착 해제 5건 | ✅ **복붙 완료·발행 번들 실측**(PM 8/23) · 증상 미재현 |

---

## 🟠 대기 (2026-08-23) — 시장 브리핑 미로그인 CTA 문구 (1줄)

PM 지시: 브리핑 카드 "내 자산" CTA 의 **"바로 봐요" → "바로 볼 수 있어요"**.

🚨 **63KB 통짜 복붙 불필요 — 라이브 에디터에서 그 1줄만 고친다.** 라이브에 다른 세션·PM
편집이 들어와 있으면 통짜가 그걸 덮는다.

라이브 `PublicMorningBriefing` (`AUFKK5X`) 에서 `바로 봐요` 로 검색(파일 내 1건) 후 교체:

```
전:  로그인하면 보유종목 증감을 여기서 바로 봐요
후:  로그인하면 보유종목 증감을 여기서 바로 볼 수 있어요
```

RULE 11 ② 정량 대조(교체 직전 실측) = 라이브 vs repo 미러 **문자 63,862 / 공백제거 25,619 /
식별자 558종 전부 일치, 차 0**. 드리프트 없는 상태에서의 1줄 변경이다.

동일 문구가 `PublicCompanyReports.tsx:316` ("원문으로 바로 봐요.") 에도 있으나 **다른
컴포넌트라 이번 지시 범위 밖** — 손대지 않았다.

| repo 파일 | 라이브 코드파일 | 반영 내용 | 상태 |
|---|---|---|---|
| `public-probe/PublicMorningBriefing.tsx` | PublicMorningBriefing (`AUFKK5X`) | CTA 문구 1줄 (838행) | 🟠 **1줄 수정 대기** |

---

## 🟠 대기 (2026-08-23) — 미장 심화 카드에 Form 144 섹션 추가

`PublicStockDetailUS` 는 PM 이 이미 라이브 생성·배치 완료(`bNt5ZZI`, `/stock` 리포트 바로
아래 `ssEgfz7ly`). **그 뒤에 Form 144 섹션이 추가돼 repo 가 앞선 상태다.**

🚨 **착수하며 발견한 결함 — 집계 절단이 조용했다.**
`notices` 길이 분포가 1건 494 · 2건 336 · 3건 238 로 줄다가 **12건에서 504 로 튄다** =
`PER_TICKER_CAP = 12` 의 절단면. 그런데 `notice_count`·`total_value_usd` 가 12건 기준인데
잘렸다는 표시가 없어 화면이 **"AMZN 12건 · $41억" 을 전량으로 읽는다**(2,463 중 **504종목 =
20.5%** 해당). 빌더에 `notices_in_window`·`truncated` 자기신고를 추가했고, 화면은
`12건+` 로 표기한다. 🚨 `merged = prev + fresh` 라 **이전 스냅샷엔 새 필드가 없어**
소비처가 `truncated || notice_count >= 12` 폴백으로 판정한다.

🚨 **화면에서 가장 중요한 줄** = "팔겠다고 미리 낸 신고이고 체결이 아닙니다. 신고 후 실제로
팔지 않는 경우도 흔하고, 보수로 받은 주식의 세금 납부용 매도도 여기에 들어갑니다."
Form 4 의 sell-to-cover 교훈이 이 폼에도 그대로 걸린다
([[feedback_form4_sell_to_cover_not_discretionary_sale]]). 이 문구 제거 금지.

**같이 들어간 것** = 발행 allowlist 에 `us_form144.json` 등재(`.github/actions/publish-data`).
🔔 **blob 발행은 다음 정기 run 후** — 붙여넣어도 Form 144 섹션만 그때까지 안 보인다(정상,
데이터 없으면 섹션이 스스로 숨는다). 나머지 3섹션(공매도·5%+대량보유·8-K)은 즉시 보인다.

검증: esbuild 종료코드 0 · 대외 금지문자열 0 · RULE 9 0 · 절단 표기 실데이터 대조
(AMZN·FANG·DOCN `12건+` / OMER `4건`).

| repo 파일 | 라이브 코드파일 | 반영 내용 | 상태 |
|---|---|---|---|
| `public-probe/PublicStockDetailUS.tsx` | PublicStockDetailUS (`bNt5ZZI`) | Form 144 섹션 추가 + 절단 표기 | 🟠 **복붙 대기** |

---

## 🟠 대기 (2026-08-22) — 세금 탭 전제 명시 (계산 무변경)

**검증 결과 계산은 정확하다** — 손계산 대조 통과(US 1,000만 → (1,000만−250만)×22% = 165만 ·
4억 → 3억×22%+9,750만×27.5% = 9,281만 · 손실 시 과세표준 0 · KR 거래세 0.2% · KR 양도세 0).

🚨 **그런데 전제가 화면에 없었다.** `usGainSum` 은 보유 **전 종목 손익의 단순 합**이라
전량 매도 가정이다. 실제 해외 양도세는 그 해에 **실현한 것만** 통산하므로,
일부만 팔면 미실현 손실이 차감되지 않아 **실제 세금이 더 크다** — 화면이 낙관 쪽으로 치우친다.

**조치 = 계산 무변경, 전제 명시 3곳**
- 헤더 `매도 가정` → **`전량 매도` 가정**
- 하단 설명에 손익통산 전제 추가("일부만 팔면 손실 종목이 차감되지 않아 실제 세금은 더 클 수 있어요")
- 코드 주석에 검증 결과와 이유 고정

가드 = `test_tax_tab_states_full_liquidation_assumption` + `test_us_tax_math_is_progressive_with_deduction`
(문구 제거 시 FAIL 확인). 상수 동기 가드 8건은 `7fb95642c` 에서 이미 시행.

| repo 파일 | 라이브 코드파일 | 반영 내용 | 상태 |
|---|---|---|---|
| `public-probe/PublicHoldingsTab.tsx` | PublicHoldingsTab (`S2WFHHW`) | 세금 탭 전량 매도 전제 명시(계산 무변경) | 🟠 **복붙 대기** |

---

## 🟠 대기 (2026-08-23) — 히트맵 줌 버튼이 관심종목 카드를 뚫는다

PM 신고(스크린샷): **엣지 히트맵의 확대·축소 버튼이 관심종목 패널 위에 그려진다.**

**원인 = z-index 값이 아니라 스택 문맥 부재.** 트리맵 외곽 `<div ref={chartRef}>` 이
`position:"relative"` 만 갖고 있어 **스택 문맥을 만들지 않는다.** CSS 규칙상
`position:relative` 는 `z-index`(auto 아닌 값)와 **함께** 있어야 문맥이 생긴다.
그래서 내부 `zIndex:18`(줌 컨트롤) · `zIndex:20`(호버카드)이 히트맵 안에 갇히지 않고
**프레이머 페이지 루트 문맥까지 올라가** 다른 레이어와 직접 경쟁했다.
`PublicWatchlist.tsx` 는 `zIndex`·`position` 이 **0건**이라(배치는 프레이머가 함) 밀린다.

**조치 = `isolation:"isolate"` 한 줄.** 히트맵 내부 상하 순서는 그대로고, 서브트리 전체가
하나의 문맥으로 접혀 바깥과 경쟁하지 않는다. 컴포넌트 상단에 "되돌리지 말 것" 가드 주석 고정.

🚨 **70KB 통짜 복붙 불필요.** 라이브에 다른 세션 편집이 있을 수 있는데(이번엔 Framer MCP
미연결이라 라이브 3-way read 를 못 했다) 통짜로 덮으면 그걸 날린다. 라이브 코드파일에서
`ref={chartRef}` 를 찾아 style 객체에 `isolation: "isolate",` **한 줄만** 추가할 것.

✅ **라이브 MCP 로 원인·충분성 둘 다 확정(2026-08-23).** `/market`(`M_VSjMD_c`) 레이어 실측:

| 레이어 | position | z-index | DOM |
|---|---|---|---|
| `PublicHeatmap` `hI9oYak1m` | 흐름(정적) | auto | 앞 |
| └ 줌 컨트롤 | absolute | **18** | — |
| `관심종목` `YNXzXV6G7` (`Yt2y4c4dK`) | **fixed** | **auto** | 뒤(마지막 자식) |

CSS 도색 순서상 **양수 z-index 는 `z-index:auto` 인 positioned 요소 전부보다 위**다 —
DOM 순서와 무관하다. 관심종목이 마지막 자식인데도 밀린 이유가 이것이고, 값을 올리는
대응(관심종목에 z-index 부여)은 **대증요법**이다. 문맥을 가두면 히트맵 전체가 `auto` 로
참여해 DOM 순서대로 관심종목이 위에 온다. **레이어 재정렬·z 값 부여 모두 불필요.**

🔎 3-way: 라이브 코드파일(`m5rK79f`)을 읽어 repo 미러와 대조 — 포맷만 다르고 내용 동일,
**드리프트 0**. 라이브 zIndex 5개(1·6·8·18·20) 전부 `ref={chartRef}` 하위라 한 곳만 막으면 된다.

| repo 파일 | 라이브 코드파일 | 반영 내용 | 상태 |
|---|---|---|---|
| `public-probe/PublicHeatmap.tsx` | PublicHeatmap (`m5rK79f`) | **파일 전체 교체** — 팔레트판 복원 + isolation | ✅ **완료(2026-08-23, PM 복붙 · MCP 정량 검증)** |

### ✅ 해소 — 1줄 지시였는데 통짜로 들어가 라이브가 되돌아갔다 (2026-08-23, 같은 날 복구)

**repo 미러가 stale 이었다.** main 의 히트맵은 `readBodyDark()`+MutationObserver **JS 다크 감지**
계열이고, 라이브는 2026-07-24 개편으로 **CSS 변수(`--an-hm-*`, `AN_PALETTE`)** 계열이었다.
그 상태로 repo 전문이 붙어 들어가 라이브가 JS 감지판으로 회귀 → **히트맵만 라이트로 남는
"부분 라이트"**(PM 스크린샷). 라이브 파일 헤더의 *"되돌리지 말 것"* 을 정확히 되돌렸다.

🚨 **원인은 내(세션) 보고다.** "라이브 = repo 동일, 드리프트 0" 이라고 했는데 zIndex 5개만
눈으로 맞춰본 것이었다. 문자 수만 셌어도 **43K vs 68K** 로 즉시 드러났다.

**복원본 = `b13d0f5fd`(팔레트판) + isolation + 가드주석 = 43,106자.** 근거:
- 저빈도 문자열 **22/22** 일치 · 구조 마커 **17/17** 일치 (붙여넣기 직전 라이브 read 와 대조)
- 기능 손실 0 — 공백 제거 시 main 과의 차이는 **+3,746자뿐**이고 전부 `readBodyDark`·
  `isDark`·`MutationObserver` 뭉치다. squarify·zoom·touch·hover·샘플·컨트롤 전부 동일
- esbuild 구문 검사 통과

✅ **복구 확인(PM: "다크모드 잘됨") + MCP 정량 검증.** 눈대중 대신 3단 대조를 돌렸다:
문자 수 63,119(라이브) vs 43,106(repo) → **공백 제거 시 26,001 vs 25,938, 차 63자**
→ `difflib` 로 구간을 찍으니 **전부 프리티어 정규화**(후행 쉼표 추가·세미콜론 제거·괄호 정리·
JSX `{""}`). 식별자 개수 11종 전수 일치(`AN_PALETTE` 3·`readBodyDark` 0·`isolation` 1).
**의미 차이 0.**

🚨 이 3단 대조가 CLAUDE.md RULE 11 ② 에 의무로 등재됐다 — 눈대중 판정 금지.

---

## ✅ 완료 (2026-08-22 PM 복붙 · MCP 라이브 검증) — 둥지 별·배지·평단 3건

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

🚨 **같이 들어간 P0 — 평단이 조용히 0 으로 저장되던 것.** PM 실사고: *"하이닉스 10주를
2,000,000원에 샀다고 올렸는데 자동으로 1,690,000원으로 되더라"*. 값이 바뀐 게 아니라
**입력이 버려졌다** — `Number("2,000,000")`=NaN → `|| 0` → **0 저장**, 서버도
`float()` ValueError → `default 0`, 검증이 `>= 0` 이라 **에러 없이 통과**.
`avg_cost=0` 이면 평가 화면이 현재가로 대체 표시해 1,690,000(= 000660 현재가)으로 보였다.
🚨 **DB 실측 = 삼성전자·SK하이닉스 둘 다 `avg_cost 0.0`** (삼성전자는 7/27부터).
수정 = 프론트 `parseNum`(쉼표·₩·$·원 제거) + 실패 시 **오류 문구 + 저장 차단**,
서버 `_num` 정규화 + **0 거부(400)**. 가드 = `tests/test_holdings_numeric_input.py` 12건.
🚨 **기존 2건은 값을 복구할 수 없다**(원래 얼마였는지 서버가 모른다) — PM 이 직접 재입력해야 한다.

| `public-probe/PublicHoldingsTab.tsx` | PublicHoldingsTab (`S2WFHHW`) | 골드 SVG 별 통일 + 배지 인라인 1줄 + **평단 파싱(쉼표) 수정·저장 차단** | ✅ **복붙 완료 2026-08-22** — 마커 13/13, 라이브 vs repo 공백 제외 동일. 🚨 검증 시 문자열 매칭이 프레이머 포매터 줄바꿈/공백(`size={ 17 }`)에 3번 빗나갔다 — **평탄화 후 대조**할 것 |

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

---

## ✅ 완료 (2026-08-25) — PublicStockDetailKR 기관·사업장 영구 미표시 (MCP surgical · RULE ④ 예외 절차)

**결함**: `d.stocks[tk]` 가 배열(1,789)을 티커 문자열로 인덱싱 → 항상 undefined →
기관 26·사업장 29종목 파트가 라이브에서 영구 미표시. forensics 쪽은 dict 라 정상 —
**두 발행물의 stocks 형태가 다르다**(report=배열 / forensics=dict).

**절차**: 라이브 read → 🚨 **repo 미러가 또 stale 시대판**(라이브=팔레트 `--an-sdk-*` /
repo=구 JS 감지판) — 장문 프로브 7종 중 `_ANP "sdk"` 불일치로 검출, 히트맵(8/23)과 두 번째.
→ 라이브 전사(비테마 본문 = HEAD 와 diff 75줄 전량 테마 전환분으로 분류 = 전사 정합 증명)
→ 수정 블록 삽입 → updateCodeFile(typecheck 0) → 재read 로 수정 블록·버전 해시 갱신 확인.
repo 미러 = 라이브판으로 교체 완료(시대판 정합 회복).

🚨 **미러 stale 2건째 = 계급 문제.** public-probe 74파일 전수의 시대판 감사(라이브 vs 미러
팔레트 마커 대조)가 필요하다 — 별도 세션 의제.
