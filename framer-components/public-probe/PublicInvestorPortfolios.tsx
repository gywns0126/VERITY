import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState } from "react"

/**
 * 거장의 포트폴리오 — SEC 13F 공시 기반 인물 축 뷰 (공개 probe).
 *
 * 데이터 = data/us_investor_portfolios.json (SEC EDGAR 13F-HR + OpenFIGI CUSIP→ticker).
 * 기존 us_smart_money_13f 는 종목 축("이 종목을 누가 들고 있나")이고, 본 컴포넌트는
 * 인물/기관 축("이 사람이 뭘 들고 있나")이다. 원천 동일.
 *
 * 🚨 RULE 7 = 공시 사실 + 공시 유래 계산값만. 자체 점수·매매신호 0.
 *
 * 🚨🚨 '실시간 수익률 랭킹' 을 만들지 말 것 (이 컴포넌트의 설계 전제):
 *   · 13F 는 분기말 보유를 최대 45일 뒤 제출 — 실측 Berkshire reportDate 2026-03-31 /
 *     filingDate 2026-05-15. 조회 시점엔 이미 수개월 전 스냅샷이다.
 *   · 롱 미국주식만 담긴다(숏·채권·현금·비미국·대부분 파생 제외).
 *   → 랭킹 기준은 공시 총액. 수익률은 '복제'(분기말 포지션을 다음 분기말까지 그대로 보유
 *     가정)만 노출하고 실제 성과가 아님을 화면에 명시한다.
 *
 * 원화 토글 = macro_snapshot.json 의 macro.usd_krw 실시간 조회(PublicMorningBriefing 동일 관례).
 * 실패 시 FX_FALLBACK. 적용 환율·기준시각을 화면에 표기해 환산값의 출처를 감추지 않는다.
 *
 * 다크모드 = body[data-framer-theme] 자가감지 (기존 컴포넌트와 동일 — 손복사 드리프트 금지).
 *
 * 🚨 모바일 = CSS 로만 판정한다 (2026-08-03). JS 측정(narrow)에 기대지 말 것.
 *   Framer 는 컴포넌트 프레임 폭 ≠ 뷰포트라 ResizeObserver 의 rootW 가 Phone(390) 에서도
 *   620 을 넘게 잡힌다 → 데스크톱 분기가 그대로 걸려 2단 유지·좌측 330 고정으로 잘리고 빈다.
 *   레이아웃 접힘 = flex-wrap(브라우저 판단), 그 외 모바일 값 = AN_IPF_CSS 미디어쿼리(700px).
 *   narrow 는 산점도 눈금/라벨 축약 같은 표시 미세조정에만 남겨둔다(틀려도 안 깨지는 것).
 */

const BLOB = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"
const FX_FALLBACK = 1450

// 🚨 AlphaNest 공통 토큰 — 자체 팔레트 금지(2026-07-30 PM 지적).
// PublicCalendar/PublicNPSHoldings 와 동일 값. Framer ColorStyles(/Theme/PageBg·NavBg·MenuHover) 정합.
// 상승=빨강 / 하락=파랑 = 한국 시장 관례. 서양식 green-up 은 이 사이트에서 오독을 만든다.
const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", track: "#eef0f3", hi: "#f6f7f9",
    vt: "#6c5ce7", vtS: "#f0edff",
    up: "#f04452", down: "#3182f6", upS: "#fdecee", downS: "#eaf1fe",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", track: "#222a33", hi: "#1e242c",
    vt: "#a99bff", vtS: "#241f3a",
    up: "#ff6b76", down: "#5a9cff", upS: "#2a1c20", downS: "#1b2740",
}
const FONT =
    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

// 🚨 숫자 = 모노 스택 금지. AlphaNest 공개 컴포넌트 표준은 Pretendard + tabular-nums
// (fontVariantNumeric 사용 21개 파일 / ui-monospace 는 내가 들여온 이 파일 1개뿐이었음 —
//  2026-07-30 PM 지적 "숫자가 프리텐다드가 아닌거 같은데"). 자릿수 정렬은 tabular-nums 로 충분.
const NUM = { fontVariantNumeric: "tabular-nums" as const }

// 🚨 되돌리지 말 것 — 모바일 분기는 CSS 미디어쿼리로만 한다 (2026-08-03 PM 지적 2연속).
//   1차: 좌/우 2단이 Phone 에서 안 접힘 → grid 를 flex-wrap 으로 교체(브라우저가 판단).
//   2차: 접힌 뒤에도 좌측이 maxWidth 330 에 묶여 우측이 빔 → 아래 규칙으로 이전.
//   원인은 둘 다 같다: Framer 는 컴포넌트 프레임 폭 ≠ 실제 뷰포트라 ResizeObserver 로 잰
//   rootW 가 Phone(390) 에서도 620 을 넘게 잡힌다. 즉 JS 측정으로 모바일을 판정할 수 없다.
//   미디어쿼리는 실제 뷰포트를 보므로 프레임 폭과 무관하게 맞는다.
//   경계 700px = flex 줄바꿈 지점(좌 300 + 우 320 + gap 18 = 638) + 루트 여백 여유.
//   ⚠ 인라인 스타일이 클래스를 이기므로 여기 있는 속성은 인라인에 두면 안 된다.
const AN_IPF_CSS = `
.an-ipf-side{flex:1 1 300px;position:sticky;top:12px;max-height:calc(100vh - 24px);margin-bottom:0}
.an-ipf-detail{padding:18px 20px 22px}
.an-ipf-tbl{min-width:460px}
.an-ipf-smstbl{min-width:700px}
.an-ipf-bar{width:100px}
.an-ipf-hdr{align-items:flex-end}
.an-ipf-fxcol{align-items:flex-end}
.an-ipf-fxtoggle{align-self:flex-end}
.an-ipf-fxrate{text-align:right}
@media (max-width:700px){
.an-ipf-side{flex-basis:100%;position:static;max-height:340px;margin-bottom:14px}
.an-ipf-detail{padding:16px 14px 18px}
.an-ipf-tbl{min-width:340px}
.an-ipf-smstbl{min-width:560px}
.an-ipf-bar{width:64px}
.an-ipf-hdr{flex-direction:column;align-items:flex-start}
.an-ipf-fxcol{align-items:flex-start}
.an-ipf-fxtoggle{align-self:flex-start}
.an-ipf-fxrate{text-align:left}
}
`

const KO_CHANGE: Record<string, string> = {
    NEW: "신규",
    INCREASED: "증액",
    DECREASED: "감액",
    HELD: "유지",
}

// 종목 역조회(거장 보유 검색) 캔버스 샘플 — fetch 없는 캔버스 렌더에서 빈 화면 방지
const SM_CANVAS_SAMPLE = {
    _meta: {
        managers: ["Berkshire Hathaway", "Fisher Asset Management", "AQR Capital"],
        count: 1021,
        held_since_window_quarters: 9,
        funds: {
            "Berkshire Hathaway": { report_date: "2026-06-30", filed_at: "2026-08-14" },
            "Fisher Asset Management": { report_date: "2026-06-30", filed_at: "2026-08-12" },
            "AQR Capital": { report_date: "2026-06-30", filed_at: "2026-08-13" },
        },
    },
    stocks: [
        {
            ticker: "GOOGL",
            name: "ALPHABET INC",
            total_value_usd: 48817177284,
            holder_count: 3,
            holders: [
                { fund: "Berkshire Hathaway", shares: 78791167, value_usd: 28157599351, weight_in_fund_pct: 9.41, change_type: "INCREASED", value_change_usd: 12557527438, held_since: "2025-09-30", quarters_held: 4, held_since_floor: false, held_since_qend_price_usd: 254.72, qend_price_usd: 357.37 },
                { fund: "Fisher Asset Management", shares: 39989840, value_usd: 14291169577, weight_in_fund_pct: 4.26, change_type: "HELD", value_change_usd: 0, held_since: "2024-06-30", quarters_held: 9, held_since_floor: true, held_since_qend_price_usd: 182.15, qend_price_usd: 357.37 },
                { fund: "AQR Capital", shares: 18000000, value_usd: 6368408356, weight_in_fund_pct: 0.73, change_type: "NEW", value_change_usd: 6368408356, held_since: "2024-06-30", quarters_held: 9, held_since_floor: true, held_since_qend_price_usd: 182.15, qend_price_usd: 357.37 },
            ],
        },
    ],
}

// 검색 인덱스 캔버스 샘플 — universe_search.json 동일 필드 (name_ko = 한글 검색 축)
const UNI_CANVAS_SAMPLE = {
    stocks: [
        { ticker: "GOOGL", name: "Alphabet Inc.", name_ko: "알파벳", market: "US" },
        { ticker: "AAPL", name: "Apple Inc.", name_ko: "애플", market: "US" },
        { ticker: "NVDA", name: "Nvidia Corporation", name_ko: "엔비디아", market: "US" },
    ],
}

function readBodyDark(): boolean {
    try {
        const _lsPref =
            typeof localStorage !== "undefined"
                ? localStorage.getItem("verity_theme")
                : null
        if (_lsPref === "dark") return true
        if (_lsPref === "light") return false
    } catch (e) {}
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}

const dot = (s?: string | null) => (s || "").replace(/-/g, ".")
// "2024-09-30" → "2024.09" (분기 식별엔 연.월이면 충분 — 말일 표기는 소음)
const ym = (s?: string | null) => (s ? dot(s).slice(0, 7) : "—")

// "언제부터" 표기 — held_since_floor(추적창 상한 도달)면 "이전부터".
// 실제 보유 시작이 추적창(9분기)보다 과거일 수 있다는 뜻 — 단정 표기 금지.
const heldSinceLabel = (h: any): string => {
    if (!h || !h.held_since) return "—"
    return h.held_since_floor ? ym(h.held_since) + " 이전부터" : ym(h.held_since) + "부터"
}

function daysBetween(a?: string | null, b?: string | null): number | null {
    if (!a || !b) return null
    const d = (new Date(b).getTime() - new Date(a).getTime()) / 86400000
    return Number.isFinite(d) ? Math.round(d) : null
}

function fmtMoney(v: number | null | undefined, krw: boolean, fx: number): string {
    if (v == null || !Number.isFinite(v)) return "—"
    if (!krw) {
        if (v >= 1e9) return "$" + (v / 1e9).toFixed(1) + "B"
        if (v >= 1e6) return "$" + (v / 1e6).toFixed(0) + "M"
        return "$" + Math.round(v).toLocaleString()
    }
    const w = v * fx
    if (w >= 1e12) return (w / 1e12).toFixed(1) + "조원"
    if (w >= 1e8) return Math.round(w / 1e8).toLocaleString() + "억원"
    return Math.round(w / 1e4).toLocaleString() + "만원"
}

// 주당 가격 표기 — *_qend_price_usd (분기말 공시 내재가). 🚨 매수 체결가 아님(13F 미공시)
// — 라벨은 "편입 분기가" 류만, '매수가' 단독 표기 금지.
function fmtPrice(v: number | null | undefined, krw: boolean, fx: number): string {
    if (v == null || !Number.isFinite(v)) return "—"
    if (!krw)
        return (
            "$" +
            v.toLocaleString(undefined, {
                minimumFractionDigits: v < 10 ? 2 : 0,
                maximumFractionDigits: 2,
            })
        )
    return Math.round(v * fx).toLocaleString() + "원"
}

const signed = (v: number | null | undefined) =>
    v == null || !Number.isFinite(v) ? "—" : (v > 0 ? "+" : "") + v.toFixed(1) + "%"

// ── 인물 사진 / 종목 로고 (2026-08-01) ──────────────────────────────────────
// 사진 = 위키미디어 자유 라이선스만. 수집기(investor_profiles.py)가 파일별 extmetadata 로
//   라이선스를 확인해 fail-closed 로 걸러 보내므로 여기서는 온 것만 그린다.
//   🚨 CC BY·BY-SA 는 저작자 표시가 의무 → 프로필 카드에 artist/license 를 반드시 함께 노출.
//   🚨 BY-SA 동일조건 변경허락 → 원본을 자르기·리사이즈만 한다. objectFit:"cover" 외에
//      색보정·합성·오버레이 금지(파생물이 되면 같은 라이선스로 배포해야 한다).
//
// 로고 = 토스 CDN. 미국 티커도 서빙된다(2026-08-01 실호출 AAPL/NVDA/MSFT 전부 200).
//   🚨 [[project_logo_toss_lane_2026_07_12]] — 라이브 로고 레인은 **토스**다.
//      Brandfetch/logo_map 으로 갈아타지 말 것(2026-07-12 롤백 사고, PM 격분).
//      404 는 이니셜 폴백 — 기존 종목 리포트와 동일 패턴.
const TOSS_LOGO = (t: string) =>
    `https://static.toss.im/png-icons/securities/icn-sec-fill-${encodeURIComponent(t)}.png`

function initialsOf(s?: string | null): string {
    const w = (s || "")
        .replace(/[^A-Za-z가-힣0-9 ]/g, " ")
        .split(/\s+/)
        .filter(Boolean)
    if (!w.length) return "?"
    if (/[가-힣]/.test(w[0])) return w[0].slice(0, 2)
    return w.slice(0, 2).map((x) => x[0]).join("").toUpperCase()
}

// 원형 아바타 — 사진 있으면 사진, 없거나 로드 실패면 이니셜.
function Avatar({
    src,
    name,
    size,
    C,
}: {
    src?: string | null
    name?: string | null
    size: number
    C: typeof LIGHT
}) {
    // 훅은 조건부 return 위 ([[feedback_framer_hooks_top_level]])
    const [bad, setBad] = useState(false)
    const box = {
        width: size,
        height: size,
        borderRadius: "50%",
        flex: `0 0 ${size}px`,
    } as const
    if (src && !bad) {
        return (
            <img
                src={src}
                alt=""
                loading="lazy"
                onError={() => setBad(true)}
                style={{
                    ...box,
                    objectFit: "cover",
                    display: "block",
                    background: C.hi,
                }}
            />
        )
    }
    return (
        <span
            aria-hidden="true"
            style={{
                ...box,
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                background: C.vtS,
                color: C.vt,
                fontSize: Math.max(10, Math.round(size * 0.36)),
                fontWeight: 750,
                letterSpacing: "-0.02em",
            }}
        >
            {initialsOf(name)}
        </span>
    )
}

// 종목 로고 — 토스 CDN. 404/미해결 티커는 이니셜.
function TickerLogo({ ticker, C }: { ticker?: string | null; C: typeof LIGHT }) {
    const [bad, setBad] = useState(false)
    const S = 22
    const box = {
        width: S,
        height: S,
        borderRadius: 7,
        flex: `0 0 ${S}px`,
    } as const
    if (ticker && !bad) {
        return (
            <img
                src={TOSS_LOGO(ticker)}
                alt=""
                loading="lazy"
                onError={() => setBad(true)}
                style={{
                    ...box,
                    objectFit: "cover",
                    display: "block",
                    background: C.hi,
                }}
            />
        )
    }
    return (
        <span
            aria-hidden="true"
            style={{
                ...box,
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                background: C.hi,
                color: C.faint,
                fontSize: 9.5,
                fontWeight: 750,
            }}
        >
            {(ticker || "").slice(0, 2).toUpperCase() || "—"}
        </span>
    )
}

// 캔버스 미리보기용 최소 표본 — 빈 렌더 금지([[feedback_framer_layout_annotation_required]]).
// 실데이터 형태와 동일한 키만 사용(형태 drift 방지).
const CANVAS_SAMPLE = {
    _meta: { caveat: "", return_caveat: "" },
    investors: [
        {
            cik: "1067983",
            institution: "Berkshire Hathaway",
            person: "워런 버핏",
            report_date: "2026-03-31",
            filed_at: "2026-05-15",
            prev_report_date: "2025-12-31",
            holdings_count: 29,
            disclosed_value_usd: 263095703570,
            disclosed_value_change_pct: -4.04,
            top10_concentration_pct: 90.7,
            new_count: 1,
            increased_count: 4,
            decreased_count: 6,
            unresolved_ticker_count: 0,
            holdings_capped: false,
            disclosed_style: {
                label: "몇 개만 크게",
                detail: "상위 10종목이 대부분입니다",
                badges: [],
                cash_caveat: true,
                replication_vol: 4.0,
            },
            trailing_4q_replication_pct: 11.37,
            quarterly_replication_returns: [
                { to: "2025-06-30", return_pct: 0.32, coverage_pct: 99.6 },
                { to: "2025-09-30", return_pct: 7.07, coverage_pct: 99.9 },
                { to: "2025-12-31", return_pct: 4.58, coverage_pct: 99.3 },
                { to: "2026-03-31", return_pct: -0.86, coverage_pct: 95.7 },
            ],
            // 캔버스에서도 아바타·출처가 보이도록 실데이터와 같은 형태로 채운다(빈 렌더 금지).
            profile: {
                name: "워런 버핏",
                summary: "",
                source: "위키백과",
                source_url: "https://ko.wikipedia.org/wiki/워런_버핏",
                image: {
                    url: "https://upload.wikimedia.org/wikipedia/commons/thumb/5/51/Warren_Buffett_KU_Visit.jpg/330px-Warren_Buffett_KU_Visit.jpg",
                    artist: "Mark Hirschey",
                    license: "CC BY-SA 2.0",
                    license_url: "https://creativecommons.org/licenses/by-sa/2.0",
                },
            },
            top_holdings: [
                {
                    ticker: "AAPL",
                    cusip: "037833100",
                    weight_pct: 21.99,
                    value_usd: 57843260493,
                    shares: 227917808,
                    change_type: "HELD",
                },
                {
                    ticker: "AXP",
                    cusip: "025816109",
                    weight_pct: 17.43,
                    value_usd: 45859204536,
                    shares: 151610700,
                    change_type: "HELD",
                },
            ],
        },
    ],
}

// 분기 복제 수익률 선형 차트 (PM 2026-07-30 "막대 말고 선형").
//
// 🚨 preserveAspectRatio="none" 금지 — 2026-07-30 PM 지적 "그래프가 좌우로 늘려져 있음".
//   고정 viewBox(560×132)를 width=100% 로 늘리면 선뿐 아니라 **텍스트·원까지 가로로 잡아당겨진다**
//   (끝점이 타원, 라벨이 늘어짐). 기존 Spark(40×24)는 텍스트가 없어 왜곡이 안 보였을 뿐 같은 문제.
//   → ResizeObserver 로 컨테이너 실폭을 재고 **실제 픽셀 좌표**로 그린다. 스케일 왜곡 0.
//
// 🚨 0 기준선 필수. 수익률은 부호가 의미이고, 0선 없는 선형은 등락을 감춘다.
//   끝점만 강조(현재 분기) — 나머지 점은 작게 두어 선의 흐름이 읽히게.
function ReturnLine({ rs, C }: { rs: any[]; C: typeof LIGHT }) {
    const [w, setW] = useState(560)
    const hostRef = useRef<HTMLDivElement | null>(null)

    useEffect(() => {
        const el = hostRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => {
            const cw = entries[0]?.contentRect?.width
            if (cw && cw > 0) setW(Math.round(cw))
        })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    const H = 138
    const PAD_T = 18
    const PAD_B = 28
    const PAD_L = 14
    // 🚨 우측 여백 = 끝점 값 라벨 자리. 2026-07-30 PM 지적 "숫자 위치 수정" —
    //   라벨을 끝점 '위'에 두면 선이 그 점으로 들어오면서 글자와 겹친다(하강 구간에서 특히).
    //   점 오른쪽으로 빼고 그만큼 플롯 폭을 줄여 충돌 자체를 없앤다.
    const PAD_R = 56
    const vals = rs.map((q) => Number(q.return_pct) || 0)

    const lo = Math.min(0, ...vals)
    const hi = Math.max(0, ...vals)
    const rng = hi - lo || 1
    const innerW = Math.max(120, w - PAD_L - PAD_R)
    const x = (i: number) =>
        vals.length < 2 ? PAD_L : (i / (vals.length - 1)) * innerW + PAD_L
    const y = (v: number) => PAD_T + (1 - (v - lo) / rng) * (H - PAD_T - PAD_B)

    const pts = vals.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`)
    const zeroY = y(0)
    const area =
        pts.join(" ") +
        ` ${x(vals.length - 1).toFixed(1)},${zeroY.toFixed(1)} ${x(0).toFixed(1)},${zeroY.toFixed(1)}`
    const last = vals[vals.length - 1]
    const stroke = last >= 0 ? C.up : C.down
    const gid = "rl-" + stroke.replace(/[^a-z0-9]/gi, "")

    return (
        <div ref={hostRef} style={{ width: "100%" }}>
            {vals.length < 2 ? null : (
                <svg
                    width={w}
                    height={H}
                    viewBox={`0 0 ${w} ${H}`}
                    style={{ display: "block" }}
                    role="img"
                    aria-label="분기별 복제 수익률 추이"
                >
                    <defs>
                        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor={stroke} stopOpacity={0.16} />
                            <stop offset="100%" stopColor={stroke} stopOpacity={0} />
                        </linearGradient>
                    </defs>
                    {/* 0 기준선 */}
                    <line
                        x1={PAD_L}
                        y1={zeroY}
                        x2={w - PAD_R + 8}
                        y2={zeroY}
                        stroke={C.line}
                        strokeWidth={1}
                        strokeDasharray="3 3"
                    />
                    <polygon points={area} fill={`url(#${gid})`} />
                    <polyline
                        points={pts.join(" ")}
                        fill="none"
                        stroke={stroke}
                        strokeWidth={2}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                    />
                    {vals.map((v, i) => {
                        const isLast = i === vals.length - 1
                        return (
                            <g key={rs[i].to}>
                                <circle
                                    cx={x(i)}
                                    cy={y(v)}
                                    r={isLast ? 4 : 2.6}
                                    fill={isLast ? stroke : C.card}
                                    stroke={stroke}
                                    strokeWidth={isLast ? 0 : 1.6}
                                />
                                <title>{`${dot(rs[i].to)} · ${signed(v)} · 커버리지 ${rs[i].coverage_pct}%`}</title>
                            </g>
                        )
                    })}
                    {/* 끝점 값만 라벨 — 전 구간 라벨은 선을 가린다.
                        🚨 SVG text 는 fontFamily 를 명시해야 Pretendard 가 적용된다. */}
                    <text
                        x={x(vals.length - 1) + 9}
                        y={y(last) + 4}
                        textAnchor="start"
                        fill={stroke}
                        fontFamily={FONT}
                        fontSize={11.5}
                        fontWeight={750}
                    >
                        {signed(last)}
                    </text>
                    {vals.map((v, i) =>
                        i === 0 || i === vals.length - 1 ? (
                            <text
                                key={"x" + rs[i].to}
                                x={x(i)}
                                y={H - 9}
                                textAnchor={i === 0 ? "start" : "middle"}
                                fill={C.faint}
                                fontFamily={FONT}
                                fontSize={10.5}
                            >
                                {dot(rs[i].to).slice(2, 7)}
                            </text>
                        ) : null
                    )}
                </svg>
            )}
        </div>
    )
}

// 스타일 지도 — 집중도 × 복제 변동성 2축 산점도 (PM 2026-08-01).
//
// 🚨 왜 육각형(레이더)이 아니라 2축인가:
//   쓸 수 있는 축을 전부 재보니 독립인 건 둘뿐이었다. 실측 상관 —
//     집중도 ↔ 종목수 **-0.90** (사실상 같은 축) / 집중도 ↔ 변동성 +0.07 (독립)
//     변동성 ↔ 복제수익 +0.37 / 종목수 ↔ 변동성 -0.17
//   나머지 후보(종목수·신규수)는 holdings 상한 300 에 걸려 왜곡되고, 분기 총액변동은
//   주가 등락이 섞여 성향과 무관하다. 6축을 채우면 4개가 가짜 축이 된다.
//   레이더는 면적이 값의 제곱으로 커지고 축 순서가 모양을 바꿔, 가짜 축이 섞이면
//   특히 해롭다. 그래서 정직하게 2축만 그린다. 육각형 요청이 다시 오면 이 주석부터 볼 것.
//
// 🚨 분면에 이름을 붙이지 않는다("공격형" 등). 13F 는 현금·채권·숏이 빠져 성향 판정의
//   근거가 못 된다(버핏 집중도 90.7% = 16인 중 4위). 위치는 사실, 해석은 독자 몫.
function StyleMap({
    list,
    sel,
    onPick,
    C,
}: {
    list: any[]
    sel: number
    onPick: (i: number) => void
    C: typeof LIGHT
}) {
    const [w, setW] = useState(560)
    const hostRef = useRef<HTMLDivElement | null>(null)

    useEffect(() => {
        const el = hostRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((e) => {
            const cw = e[0]?.contentRect?.width
            if (cw && cw > 0) setW(Math.round(cw))
        })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    // 🚨 좁은 화면 판정 = 이 차트 자기 실폭. 부모의 rootW(=Framer 프레임 폭)는 못 믿는다.
    //   여기 w 는 자기 컨테이너를 재므로 Phone 에서 실제로 줄어드는 것이 확인된 값이다.
    const narrow = w < 560

    const pts = list
        .map((v, i) => ({
            i,
            name: v.person || v.institution,
            x: Number(v.top10_concentration_pct),
            y: Number(v.disclosed_style?.replication_vol),
        }))
        .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y))

    // 🚨 ReturnLine 과 같은 이유로 실픽셀 좌표를 쓴다 — viewBox 를 늘리면 텍스트까지 왜곡된다.
    const H = narrow ? 230 : 300
    const PAD = narrow
        ? { t: 14, r: 12, b: 32, l: 34 }
        : { t: 16, r: 18, b: 34, l: 44 }
    if (pts.length < 3) return null
    const xs = pts.map((p) => p.x)
    const ys = pts.map((p) => p.y)
    const x0 = 0
    const x1 = 100
    const y0 = 0
    const y1 = Math.max(...ys) * 1.15 || 1
    const innerW = Math.max(140, w - PAD.l - PAD.r)
    const innerH = H - PAD.t - PAD.b
    const px = (v: number) => PAD.l + ((v - x0) / (x1 - x0)) * innerW
    const py = (v: number) => PAD.t + (1 - (v - y0) / (y1 - y0)) * innerH

    return (
        <div ref={hostRef} style={{ width: "100%" }}>
            <svg
                width={w}
                height={H}
                viewBox={`0 0 ${w} ${H}`}
                style={{ display: "block" }}
                role="img"
                aria-label="집중도와 분기 기복으로 본 운용사 분포"
            >
                {(narrow ? [0, 50, 100] : [0, 25, 50, 75, 100]).map((g) => (
                    <g key={g}>
                        <line
                            x1={px(g)}
                            y1={PAD.t}
                            x2={px(g)}
                            y2={PAD.t + innerH}
                            stroke={C.line}
                            strokeWidth={1}
                            strokeDasharray="2 4"
                        />
                        <text
                            x={px(g)}
                            y={H - 16}
                            textAnchor="middle"
                            fill={C.faint}
                            fontFamily={FONT}
                            fontSize={10.5}
                            fontWeight={550}
                        >
                            {g}%
                        </text>
                    </g>
                ))}
                <text
                    x={PAD.l + innerW / 2}
                    y={H - 3}
                    textAnchor="middle"
                    fill={C.faint}
                    fontFamily={FONT}
                    fontSize={11}
                    fontWeight={600}
                >
                    상위 10종목 비중 — 오른쪽일수록 몇 개에 몰아서
                </text>
                <text
                    x={12}
                    y={PAD.t + innerH / 2}
                    textAnchor="middle"
                    fill={C.faint}
                    fontFamily={FONT}
                    fontSize={11}
                    fontWeight={600}
                    transform={`rotate(-90 12 ${PAD.t + innerH / 2})`}
                >
                    {narrow ? "분기 기복 ↑" : "분기 기복 — 위일수록 출렁임"}
                </text>
                {/* 🚨 선택 점을 마지막에 그린다. SVG 는 문서 순서대로 덮으므로 그냥 map 하면
                    뒤 인덱스 점들이 선택 점의 이름표를 가린다(2026-08-01 PM 스크린샷 — "켄 피셔"
                    라벨이 다른 점 뒤로 들어감). z-index 는 SVG 에 안 먹으니 순서로 해결한다. */}
                {pts
                    .filter((p) => p.i !== sel)
                    .map((p) => (
                        <g
                            key={p.i}
                            onClick={() => onPick(p.i)}
                            style={{ cursor: "pointer" }}
                        >
                            <circle
                                cx={px(p.x)}
                                cy={py(p.y)}
                                r={5}
                                fill={C.card}
                                stroke={C.faint}
                                strokeWidth={1.6}
                            />
                            <title>{`${p.name} · 집중도 ${p.x.toFixed(0)}% · 기복 ${p.y.toFixed(1)}`}</title>
                        </g>
                    ))}
                {pts
                    .filter((p) => p.i === sel)
                    .map((p) => {
                        // 🚨 이름표를 SVG 안으로 밀어 넣는다 — 되돌리지 말 것 (2026-08-09 PM 스크린샷).
                        //   textAnchor="middle" 이라 점이 좌·우 끝에 있으면 이름의 절반이
                        //   SVG 경계 밖으로 나가 잘린다("빌 애크먼" = 집중도 최상단 → 오른쪽 끝).
                        //   SVG 는 뷰박스 밖을 그리지 않으므로 앵커 x 를 안쪽으로 당겨야 한다.
                        //   한글 12.5px·750 기준 글자폭 ≈ 12.4px → 반폭 = 글자수 × 6.2.
                        //   +4 = 후광 stroke(3.5) 절반과 여백. 이름표는 잘리느니 조금 어긋나는 게 낫다.
                        const halfW = Math.max(20, p.name.length * 6.2 + 4)
                        const lx = Math.min(
                            Math.max(px(p.x), halfW),
                            Math.max(halfW, w - halfW)
                        )
                        // 위쪽 끝 점은 이름표가 뷰박스 위로 나가므로 점 아래로 내린다.
                        const ly =
                            py(p.y) - 14 < 12 ? py(p.y) + 22 : py(p.y) - 14
                        return (
                        <g key={p.i} style={{ cursor: "pointer" }}>
                            {/* 이름표 자리를 비우는 후광 — 점이 촘촘한 구간에서도 읽히게.
                                paintOrder="stroke" 로 외곽선을 글자 뒤에 깐다. */}
                            <text
                                x={lx}
                                y={ly}
                                textAnchor="middle"
                                fill={C.vt}
                                stroke={C.card}
                                strokeWidth={3.5}
                                paintOrder="stroke"
                                strokeLinejoin="round"
                                fontFamily={FONT}
                                fontSize={12.5}
                                fontWeight={750}
                            >
                                {p.name}
                            </text>
                            <circle
                                cx={px(p.x)}
                                cy={py(p.y)}
                                r={9}
                                fill={C.card}
                            />
                            <circle
                                cx={px(p.x)}
                                cy={py(p.y)}
                                r={7}
                                fill={C.vt}
                            />
                            <title>{`${p.name} · 집중도 ${p.x.toFixed(0)}% · 기복 ${p.y.toFixed(1)}`}</title>
                        </g>
                        )
                    })}
            </svg>
        </div>
    )
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicInvestorPortfolios(props: {
    dataUrl?: string
    macroUrl?: string
    searchUrl?: string
    universeUrl?: string
    dark?: boolean
    topN?: number
    stockPath?: string
}) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    // 종목 클릭 → 리포트 페이지 (/stock?q=티커 — AlphaNestFeed·PublicETFFlow 와 동일 규약)
    const stockPath = (props.stockPath || "/stock").replace(/\/+$/, "")
    const goStock = (tk?: string | null) => {
        if (!tk || onCanvas) return
        try {
            window.location.href = stockPath + "?q=" + encodeURIComponent(tk)
        } catch (e) {}
    }
    // 모바일 대응 — 루트 실폭 측정 (PublicCalendar 등 형제 컴포넌트와 동일 관례).
    // 좌 330px + 우 1fr 2단이라 620 미만에서는 두 열이 다 뭉개진다 → 세로 스택으로 전환.
    const rootRef = useRef<HTMLDivElement | null>(null)
    const [rootW, setRootW] = useState(0)
    const [themeDark, setThemeDark] = useState<boolean>(() =>
        onCanvas ? !!props.dark : readBodyDark()
    )
    // 🚨 훅은 전부 조건부 return 위 ([[feedback_framer_hooks_top_level]] — 2026-07-07 실사고)
    const [data, setData] = useState<any>(onCanvas ? CANVAS_SAMPLE : null)
    const [sel, setSel] = useState(0)
    const [krw, setKrw] = useState(false)
    const [fx, setFx] = useState<{ rate: number; asOf: string | null }>({
        rate: FX_FALLBACK,
        asOf: null,
    })
    // 종목 역조회 (거장 보유 검색) — us_smart_money_13f.json (종목 축, 같은 13F 원천)
    const [sm, setSm] = useState<any>(onCanvas ? SM_CANVAS_SAMPLE : null)
    // 🚨 검색 인덱스 = universe_search.json (사이트 전 검색창 공통 소스 — 한글명 name_ko 포함).
    //   13F name(SEC 영문 issuer)만으로 매칭하면 "애플" 이 안 나온다(PM 8/24 격분 사고).
    const [uni, setUni] = useState<any>(onCanvas ? UNI_CANVAS_SAMPLE : null)
    const [smQ, setSmQ] = useState("")
    const [smTicker, setSmTicker] = useState<string | null>(null)

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (
            typeof MutationObserver === "undefined" ||
            typeof document === "undefined" ||
            !document.body
        )
            return
        const obs = new MutationObserver(read)
        obs.observe(document.body, {
            attributes: true,
            attributeFilter: ["data-framer-theme"],
        })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(props.dataUrl || BLOB + "/us_investor_portfolios.json")
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (alive && d && Array.isArray(d.investors)) setData(d)
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [onCanvas, props.dataUrl])

    // 실시간 환율 — macro_snapshot.macro.usd_krw (PublicMorningBriefing 과 동일 소스)
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(props.macroUrl || BLOB + "/macro_snapshot.json")
            .then((r) => (r.ok ? r.json() : null))
            .then((m) => {
                const u = m && m.macro && m.macro.usd_krw
                const v = u && Number(u.value)
                if (alive && v && Number.isFinite(v) && v > 0)
                    setFx({ rate: v, asOf: u.as_of || m.collected_at || null })
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [onCanvas, props.macroUrl])

    // 종목 축 데이터 — 검색창을 처음 쓸 때가 아니라 마운트 시 로드 (400KB 급, 입력 지연 방지)
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(props.searchUrl || BLOB + "/us_smart_money_13f.json")
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (alive && d && Array.isArray(d.stocks)) setSm(d)
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [onCanvas, props.searchUrl])

    // 검색 인덱스 — universe_search.json (HoldingsTab 등 전 검색창과 동일 소스·동일 필드)
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(props.universeUrl || BLOB + "/universe_search.json")
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (alive && d && Array.isArray(d.stocks)) setUni(d)
            })
            .catch(() => {})
        return () => {
            alive = false
        }
    }, [onCanvas, props.universeUrl])

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((e) => {
            for (const x of e) setRootW(x.contentRect.width)
        })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    const narrow = rootW > 0 && rootW < 620
    const C = themeDark ? DARK : LIGHT
    const list: any[] = useMemo(
        () => (data && Array.isArray(data.investors) ? data.investors : []),
        [data]
    )
    const cur = list[Math.min(sel, Math.max(list.length - 1, 0))] || null
    const topN = Math.max(3, props.topN ?? 25)

    // ── 종목 역조회 (검색) ──────────────────────────────────────────────────
    const smStocks: any[] = useMemo(
        () => (sm && Array.isArray(sm.stocks) ? sm.stocks : []),
        [sm]
    )
    const smMeta = (sm && sm._meta) || {}
    const smFunds: Record<string, any> = smMeta.funds || {}
    const smQraw = smQ.trim()
    const smQn = smQraw.toLowerCase()
    const smByTicker: Record<string, any> = useMemo(() => {
        const m: Record<string, any> = {}
        for (const s of smStocks) m[String(s.ticker)] = s
        return m
    }, [smStocks])
    // 검색 대상 = universe_search 의 미국 전 종목 (검수 2026-08-24: US 5,324 · 거장 보유
    // 1,021 전수 매칭 100% · 한글명 989/1,021). 거장 미보유 종목도 탐색은 되고,
    // 선택하면 "보유 없음" + 리포트 이동을 준다 — 검색이 막다른 골목이 되지 않게.
    const searchRows: any[] = useMemo(() => {
        const rows: any[] = uni && Array.isArray(uni.stocks) ? uni.stocks : []
        const us = rows.filter(
            (r: any) => String(r.market || "").toLowerCase() === "us"
        )
        if (!us.length)
            // universe 미로딩/실패 폴백 — 거장 보유분만이라도 검색되게 (영문명 한정)
            return smStocks.map((s: any) => ({
                ticker: s.ticker,
                name: s.name,
                name_ko: "",
                holder_count: s.holder_count || 0,
            }))
        const rows2 = us.map((r: any) => ({
            ticker: r.ticker,
            name: r.name || r.ticker,
            name_ko: r.name_ko || "",
            holder_count: (smByTicker[r.ticker] || {}).holder_count || 0,
        }))
        // 🚨 합집합 — 거장 보유인데 universe 밖인 종목(해외 ADR 등, 2026-08-25 실측 TSM
        //   8펀드 보유가 universe_search US 에 없음)을 뒤에 붙인다. 안 붙이면 데이터가
        //   있어도 검색이 "보유 없음" 거짓을 만든다. 이름 = 13F issuer 영문(한글명 없음).
        const usSet = new Set(rows2.map((r: any) => r.ticker))
        for (const s of smStocks) {
            if (!usSet.has(s.ticker))
                rows2.push({
                    ticker: s.ticker,
                    name: s.name,
                    name_ko: "",
                    holder_count: s.holder_count || 0,
                })
        }
        return rows2
    }, [uni, smStocks, smByTicker])
    // 🚨 매칭 = 사이트 공통 검색창 규약(PublicHoldingsTab 원형과 동일):
    //   ticker/영문명 = 소문자 substring · 한글명 = raw substring(한글은 대소문자 없음).
    //   랭킹 = 정확 > 접두 > 포함, 동순위는 거장 보유 많은 쪽 먼저. 상위 8.
    //   전방일치 전용·영문명 단독 매칭으로 되돌리지 말 것(8/24 "애플" 미검색 사고).
    const smSuggests: any[] = useMemo(() => {
        if (!smQn) return []
        const rk = (x: any) => {
            const t = String(x.ticker || "").toLowerCase()
            const n = String(x.name || "").toLowerCase()
            const k = String(x.name_ko || "")
            return t === smQn
                ? 0
                : n === smQn || k === smQraw
                  ? 1
                  : t.indexOf(smQn) === 0
                    ? 2
                    : n.indexOf(smQn) === 0 || (k && k.indexOf(smQraw) === 0)
                      ? 3
                      : 4
        }
        return searchRows
            .filter(
                (x: any) =>
                    String(x.ticker || "").toLowerCase().includes(smQn) ||
                    String(x.name || "").toLowerCase().includes(smQn) ||
                    String(x.name_ko || "").includes(smQraw)
            )
            .sort(
                (a: any, b: any) =>
                    rk(a) - rk(b) || (b.holder_count || 0) - (a.holder_count || 0)
            )
            .slice(0, 8)
    }, [searchRows, smQn, smQraw])
    // 선택 종목 — smSel = 검색 인덱스 행(이름용), smCur = 거장 보유 데이터(없으면 미보유)
    const smSel: any = useMemo(
        () => searchRows.find((s) => s.ticker === smTicker) || null,
        [searchRows, smTicker]
    )
    const smCur: any = smTicker ? smByTicker[smTicker] || null : null
    // 미커버 안내 — 입력이 있는데 제안 0 + 선택 0 (분모를 함께 말한다)
    const smNoHit = !!smQn && smSuggests.length === 0 && !smTicker
    // 한글명 조인 (universe) — top10 행 표기용
    const uniKoMap: Record<string, string> = useMemo(() => {
        const m: Record<string, string> = {}
        for (const r of searchRows) if (r.name_ko) m[r.ticker] = r.name_ko
        return m
    }, [searchRows])
    // ── 이번 분기 거장 순매수 TOP 10 (검색 대기 화면 기본 노출, PM 승인 8/25) ──
    // 🚨 기준 = 펀드 수 (신규 + 증액 − 감액). value_change_usd 로 랭킹하지 말 것 —
    //   그 필드는 주가 등락 + 실제 매매가 섞여 있어(13F 메모리 필드 규약) "순매수" 라벨과
    //   어긋난다. change_type 은 주식수 delta 기준이라 순수 매매 행동 = 라벨 정직.
    //   '수익률' 라벨 절대 금지(트랙 고정 규율)와 같은 뿌리.
    const smTop10: any[] = useMemo(() => {
        const scored = smStocks
            .map((s: any) => {
                let nw = 0,
                    inc = 0,
                    dec = 0
                for (const h of s.holders || []) {
                    if (h.change_type === "NEW") nw++
                    else if (h.change_type === "INCREASED") inc++
                    else if (h.change_type === "DECREASED") dec++
                }
                return { ...s, _nw: nw, _inc: inc, _dec: dec, _net: nw + inc - dec }
            })
            .filter((s: any) => s._net > 0)
        scored.sort(
            (a: any, b: any) =>
                b._net - a._net ||
                b._nw + b._inc - (a._nw + a._inc) ||
                b.total_value_usd - a.total_value_usd
        )
        return scored.slice(0, 10)
    }, [smStocks])
    // 펀드명 클릭 → 좌측 인물 목록의 해당 운용사로 점프 (두 축이 같은 16개 명단)
    const jumpToFund = (fund: string) => {
        const i = list.findIndex(
            (v: any) =>
                String(v.institution || "").toUpperCase() === String(fund || "").toUpperCase()
        )
        if (i >= 0) setSel(i)
    }

    const money = (v: any) => fmtMoney(v, krw, fx.rate)
    const tone = (v: any) =>
        v == null ? C.faint : v > 0 ? C.up : v < 0 ? C.down : C.sub

    if (!list.length) {
        return (
            <div
                style={{
                    background: C.bg,
                    color: C.faint,
                    padding: 28,
                    borderRadius: 16,
                    fontFamily: FONT,
                    fontSize: 14,
                }}
            >
                거장 포트폴리오를 불러오는 중입니다.
            </div>
        )
    }

    const lagDays = daysBetween(cur?.report_date, cur?.filed_at)
    const rs: any[] = Array.isArray(cur?.quarterly_replication_returns)
        ? cur.quarterly_replication_returns
        : []

    const chipBg = (t: string) =>
        t === "NEW"
            ? C.vtS
            : t === "INCREASED"
              ? C.upS
              : t === "DECREASED"
                ? C.downS
                : C.hi
    const chipFg = (t: string) =>
        t === "NEW"
            ? C.vt
            : t === "INCREASED"
              ? C.up
              : t === "DECREASED"
                ? C.down
                : C.faint

    return (
        <div
            ref={rootRef}
            style={{
                width: "100%",
                // 🚨 모바일 잘림 방지 — 자식이 넘쳐도 루트가 커지지 않게(2026-08-03 PM 지적).
                //   maxWidth 100% + overflowX 클립이 없으면 표(minWidth)가 페이지를 넓혀 잘린다.
                maxWidth: "100%",
                // 🚨 `hidden` 이 아니라 `clip` 이어야 한다 — 되돌리지 말 것 (2026-08-09 PM 지적).
                //   overflow-x:hidden 은 반대축을 auto 로 계산해 이 루트를 **스크롤 컨테이너**로
                //   만든다. 그러면 자식의 position:sticky 가 뷰포트가 아니라 이 루트를 기준으로
                //   붙어서, 좌측 운용사 목록 고정(2026-07-30 PM)이 조용히 죽는다.
                //   `clip` 은 잘라내되 스크롤 컨테이너를 만들지 않아 둘 다 성립한다.
                overflowX: "clip",
                boxSizing: "border-box",
                // 🚨 배경 transparent — 자체 팔레트로 칠하면 테마 판정 타이밍에 흰 판이 깔린다
                //   (2026-08-01 리포트와 동일 사유). Framer 프레임의 ColorStyle 이 비쳐 보이게 둔다.
                background: "transparent",
                color: C.ink,
                fontFamily: FONT,
                fontSize: 15,
                fontWeight: 500,
                lineHeight: 1.6,
                padding: "4px 0 8px",
            }}
        >
            {/* 🚨 2026-08-03 모바일 분기 = CSS 미디어쿼리. JS 측정(narrow)에 기대지 말 것.
                Framer 는 컴포넌트 프레임 폭이 실제 뷰포트와 달라 rootW 가 크게 잡힌다.
                그러면 Phone 에서도 데스크톱 값(좌측 maxWidth 330 / sticky)이 적용돼
                줄바꿈 후에도 목록이 330 에 묶여 우측이 비고, 목록이 화면을 잠식한다(PM 지적).
                아래 규칙은 인라인 스타일로 덮이므로 해당 속성을 인라인에서 지웠다 — 되돌리지 말 것. */}
            <style>{AN_IPF_CSS}</style>

            {/* 헤더 + 통화 토글 */}
            {/* 🚨 2026-08-24 PM "버튼이 우측으로 쏠림" — 되돌리지 말 것.
                원인 = `flexWrap:wrap`. 좁은 폭에서 우측 열이 **자기 줄로 접히면서**
                내용 폭(= 환율 문구 폭)으로 줄고, 그 안의 `align-items:flex-end` 가
                토글을 문구 오른쪽 끝으로 밀었다. 그래서 좌·우 어디에도 안 맞는
                어중간한 위치가 됐다(= 쏠림). 8/09 3연속 수정은 **데스크톱 우측 여백**
                건이라 이건 다른 원인이다 — 그 수정들을 되돌린 것이 아니다.
                해법 = ① `nowrap` 으로 "접혔는데 우측정렬" 상태 자체를 없애고
                       ② 700px 이하에서만 세로 스택 + 좌측정렬(미디어쿼리).
                🚨 align-items / flex-direction = AN_IPF_CSS. 인라인 금지
                   (인라인이 미디어쿼리를 덮는다 — 이 파일의 기존 규약). */}
            <div
                className="an-ipf-hdr"
                style={{
                    display: "flex",
                    flexWrap: "nowrap",
                    gap: 14,
                    justifyContent: "space-between",
                    marginBottom: 18,
                }}
            >
                <div>
                    <div
                        style={{
                            // 🚨 라이브(Framer)에서 PM 이 직접 줄인 값 — repo 로 역동기(2026-08-24).
                            //   repo 는 24/800 이었고 라이브가 20/700 이었다. 통짜 복붙으로
                            //   덮었으면 이 변경이 조용히 사라진다(RULE 11 3소스 동기화).
                            fontSize: 20,
                            fontWeight: 700,
                            letterSpacing: "-0.022em",
                            color: C.ink,
                        }}
                    >
                        거장의 포트폴리오
                    </div>
                    <div style={{ color: C.faint, fontSize: 13.5, marginTop: 5 }}>
                        미국 증권거래위원회(SEC) 13F 공시로 확인되는 {list.length}개 운용사의 보유 종목
                    </div>
                </div>
                {/* 🚨 우측 열 = 세로 스택 + 오른쪽 정렬. 되돌리지 말 것 (2026-08-09 PM 스크린샷).
                    환율 문구를 상시 노출로 바꾸자(같은 날) 이 열의 폭이 문구 길이로 넓어졌고,
                    토글 컨테이너가 블록 레벨 flex 라 그 폭까지 늘어나 KRW 오른쪽에 빈 공간이 생겼다.
                    alignItems:flex-end 로 토글을 내용 폭으로 줄이고 문구와 오른쪽을 맞춘다. */}
                <div
                    className="an-ipf-fxcol"
                    style={{
                        display: "flex",
                        flexDirection: "column",
                        // align-items = AN_IPF_CSS (미디어쿼리). 인라인 금지.
                    }}
                >
                    <div
                        className="an-ipf-fxtoggle"
                        style={{
                            // 🚨 되돌리지 말 것 (2026-08-09 PM, 3번째 수정).
                            //   `display:flex` + 자식 `width:62` 로는 우측 여백이 안 잡혔다.
                            //   inline-grid + gridAutoColumns:1fr = 두 칸이 **가장 넓은 글자 기준
                            //   같은 폭**으로 잡히고(전환해도 안 흔들림), 컨테이너는 내용 폭에서 멈춘다.
                            //   width:fit-content + align-self 로 부모가 늘려도 안 늘어나게 이중으로 건다.
                            //   🚨 align-self 는 AN_IPF_CSS 로 옮겼다(2026-08-24) — 이중 방어는
                            //   그대로이고, 좁은 폭에서만 flex-start 로 뒤집기 위해서다. 인라인 금지.
                            display: "inline-grid",
                            gridAutoFlow: "column",
                            gridAutoColumns: "1fr",
                            width: "fit-content",
                            background: C.hi,
                            borderRadius: 999,
                            padding: 3,
                            gap: 2,
                        }}
                    >
                        {[
                            { k: false, t: "USD" },
                            { k: true, t: "KRW" },
                        ].map((o) => (
                            <button
                                key={o.t}
                                type="button"
                                onClick={() => setKrw(o.k)}
                                aria-pressed={krw === o.k}
                                style={{
                                    border: 0,
                                    cursor: "pointer",
                                    font: "inherit",
                                    fontSize: 13,
                                    fontWeight: 650,
                                    // 폭 균등은 부모 grid(1fr 2칸)가 담당한다 — 여기서 고정폭을
                                    // 주면 내용보다 넓어져 우측이 빈다(2026-08-09 실패한 1차 수정).
                                    padding: "6px 14px",
                                    textAlign: "center",
                                    whiteSpace: "nowrap",
                                    borderRadius: 999,
                                    background: krw === o.k ? C.card : "transparent",
                                    color: krw === o.k ? C.vt : C.faint,
                                }}
                            >
                                {o.t}
                            </button>
                        ))}
                    </div>
                    {/* 🚨 환율 문구는 통화와 무관하게 항상 띄운다 — 되돌리지 말 것 (2026-08-09 PM).
                        KRW 일 때만 그리면 전환할 때마다 이 줄이 생겼다 사라져 아래가 밀린다.
                        USD 로 보고 있어도 "무슨 환율로 환산되는지" 를 먼저 아는 편이 낫다. */}
                    <div
                        className="an-ipf-fxrate"
                        style={{
                            fontSize: 11.5,
                            color: C.faint,
                            marginTop: 5,
                            // text-align = AN_IPF_CSS (미디어쿼리). 인라인 금지.
                        }}
                    >
                        1달러 = {fx.rate.toLocaleString()}원
                        {fx.asOf ? " · " + dot(fx.asOf.slice(0, 10)) + " 기준" : " · 근사값"}
                    </div>
                </div>
            </div>

            {/* 신선도 = 각주가 아니라 상단 1급 정보 */}
            <div
                style={{
                    background: C.card,
                    borderRadius: 16,
                    padding: "16px 18px",
                    marginBottom: 18,
                }}
            >
                <div style={{ fontSize: 14, fontWeight: 750, letterSpacing: "-0.01em", color: C.ink }}>
                    지금 보는 건 실시간이 아니라 {dot(cur?.report_date)} 시점의 보유입니다.
                </div>
                <div style={{ color: C.sub, fontSize: 13, marginTop: 5 }}>
                    13F는 분기말 보유를 최대 45일 뒤에 제출합니다. 공시에는 미국 상장주식 매수
                    포지션만 담기고 공매도·채권·현금·해외자산은 빠집니다.
                </div>
                <div
                    style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 7,
                        marginTop: 10,
                        background: C.hi,
                        borderRadius: 999,
                        padding: "5px 12px",
                        fontSize: 12.5,
                        color: C.sub,
                    }}
                >
                    <span
                        style={{
                            width: 6,
                            height: 6,
                            borderRadius: "50%",
                            background: C.vt,
                        }}
                    />
                    보유 기준일 {dot(cur?.report_date)} · 제출일 {dot(cur?.filed_at)}
                    {lagDays != null ? ` — 공시까지 ${lagDays}일` : ""}
                </div>
            </div>

            {/* 스타일 지도 — 16명을 한 화면에 놓고 비교. 점을 누르면 아래 상세가 바뀐다
                ([[feedback_in_component_interactivity]] — 컴포넌트 안에서 상호작용 완결). */}
            <div
                style={{
                    background: C.card,
                    borderRadius: 16,
                    padding: "16px 18px 10px",
                    marginBottom: 18,
                }}
            >
                <div style={{ fontSize: 14, fontWeight: 750, letterSpacing: "-0.01em", color: C.ink }}>
                    한눈에 보는 스타일
                </div>
                <div
                    style={{
                        color: C.faint,
                        fontSize: 12.5,
                        margin: "4px 0 6px",
                        lineHeight: 1.55,
                    }}
                >
                    점을 누르면 아래에서 자세히 볼 수 있습니다. 오른쪽일수록 소수 종목에
                    몰아서 담았고, 위일수록 분기마다 성과가 출렁였습니다.
                </div>
                <StyleMap list={list} sel={sel} onPick={setSel} C={C} />
                <div
                    style={{
                        fontSize: 11.5,
                        color: C.faint,
                        lineHeight: 1.55,
                        paddingBottom: 6,
                    }}
                >
                    위치는 공시 숫자를 그대로 옮긴 것이며 좋고 나쁨을 뜻하지 않습니다.
                    현금·채권·공매도는 이 공시에 없어 반영되지 않습니다.
                </div>
            </div>

            {/* ── 종목 역조회 — "이 종목, 누가 얼마나 언제부터 들고 있나" ──────────
                🚨 검색창 디자인·방식 = 사이트 공통 규약 그대로 (PM 2026-08-24 "다른
                컴포넌트랑 다르다" 지적 후 정렬). 원형 = PublicNPSHoldings(돋보기 SVG +
                회색 필드 radius 12 + × 클리어, 보더/아웃라인 0) + PublicHoldingsTab
                (결과 = 입력 아래 인라인 목록 · 로고+이름/티커 2줄 · 상위 8 · 선택 시
                입력 초기화). 오버레이 드롭다운으로 되돌리지 말 것. */}
            <div
                style={{
                    background: C.card,
                    borderRadius: 16,
                    padding: "14px 15px",
                    marginBottom: 18,
                }}
            >
                <div style={{ position: "relative" }}>
                    <svg
                        width="14"
                        height="14"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke={C.faint}
                        strokeWidth="2.4"
                        strokeLinecap="round"
                        style={{
                            position: "absolute",
                            left: 13,
                            top: "50%",
                            transform: "translateY(-50%)",
                            pointerEvents: "none",
                        }}
                    >
                        <circle cx="11" cy="11" r="7" />
                        <line x1="21" y1="21" x2="16.65" y2="16.65" />
                    </svg>
                    <input
                        type="text"
                        value={smQ}
                        onChange={(e) => {
                            setSmQ(e.target.value)
                            setSmTicker(null)
                        }}
                        onKeyDown={(e) => {
                            if (e.key === "Enter" && smSuggests.length > 0) {
                                setSmTicker(smSuggests[0].ticker)
                                setSmQ("")
                            }
                        }}
                        placeholder="종목명·코드 검색 — 어떤 거장이 들고 있는지"
                        aria-label="거장 보유 종목 검색"
                        style={{
                            width: "100%",
                            boxSizing: "border-box",
                            border: "none",
                            background: C.bg,
                            color: C.ink,
                            borderRadius: 12,
                            padding: "11px 32px 11px 36px",
                            fontSize: 13,
                            fontFamily: FONT,
                            outline: "none",
                            WebkitAppearance: "none",
                        }}
                    />
                    {smQ && (
                        <span
                            role="button"
                            tabIndex={0}
                            onClick={() => {
                                setSmQ("")
                                setSmTicker(null)
                            }}
                            style={{
                                position: "absolute",
                                right: 10,
                                top: "50%",
                                transform: "translateY(-50%)",
                                color: C.faint,
                                fontSize: 14,
                                fontWeight: 700,
                                cursor: "pointer",
                                lineHeight: 1,
                            }}
                        >
                            ×
                        </span>
                    )}
                </div>

                {smSuggests.length > 0 && !smCur && (
                    <div
                        style={{
                            marginTop: 8,
                            display: "flex",
                            flexDirection: "column",
                            gap: 2,
                        }}
                    >
                        {smSuggests.map((s: any) => (
                            <div
                                key={s.ticker}
                                onClick={() => {
                                    setSmTicker(s.ticker)
                                    setSmQ("")
                                }}
                                onKeyDown={(ev: any) => {
                                    if (ev.key === "Enter") {
                                        setSmTicker(s.ticker)
                                        setSmQ("")
                                    }
                                }}
                                role="option"
                                tabIndex={0}
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 10,
                                    padding: "8px 6px",
                                    borderRadius: 10,
                                    cursor: "pointer",
                                }}
                            >
                                <TickerLogo ticker={s.ticker} C={C} />
                                <div style={{ minWidth: 0, flex: 1 }}>
                                    <div
                                        style={{
                                            fontSize: 13.5,
                                            fontWeight: 700,
                                            color: C.ink,
                                            whiteSpace: "nowrap",
                                            overflow: "hidden",
                                            textOverflow: "ellipsis",
                                        }}
                                    >
                                        {s.name_ko ||
                                            (s.name && s.name !== s.ticker
                                                ? s.name
                                                : s.ticker)}
                                    </div>
                                    <div
                                        style={{
                                            fontSize: 11,
                                            color: C.faint,
                                            fontWeight: 600,
                                        }}
                                    >
                                        {s.ticker} · US
                                    </div>
                                </div>
                                <span
                                    style={{
                                        fontSize: 11,
                                        fontWeight: 700,
                                        color:
                                            s.holder_count > 0 ? C.vt : C.faint,
                                        flexShrink: 0,
                                        paddingRight: 4,
                                        ...NUM,
                                    }}
                                >
                                    {s.holder_count > 0
                                        ? `거장 ${s.holder_count}개 펀드`
                                        : "거장 보유 없음"}
                                </span>
                            </div>
                        ))}
                    </div>
                )}

                {smNoHit && (
                    <div
                        style={{
                            padding: "16px 0 8px",
                            textAlign: "center",
                            color: C.faint,
                            fontSize: 13,
                            fontWeight: 600,
                        }}
                    >
                        "{smQraw}" 검색 결과 없음 — 미국 상장{" "}
                        {searchRows.length.toLocaleString()}종목 기준 (한국 종목은 13F
                        공시 대상이 아니에요)
                    </div>
                )}

                {smTicker && (
                    <div style={{ marginTop: 12 }}>
                        <div
                            style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 10,
                                flexWrap: "wrap",
                            }}
                        >
                            <TickerLogo ticker={smTicker} C={C} />
                            <div style={{ minWidth: 0, flex: 1 }}>
                                <div style={{ fontSize: 15.5, fontWeight: 750 }}>
                                    {(smSel && smSel.name_ko) || smTicker}
                                    <span
                                        style={{
                                            marginLeft: 8,
                                            fontSize: 12.5,
                                            fontWeight: 550,
                                            color: C.faint,
                                        }}
                                    >
                                        {smSel && smSel.name_ko
                                            ? smTicker
                                            : (smSel && smSel.name) ||
                                              (smCur && smCur.name) ||
                                              ""}
                                    </span>
                                </div>
                                <div
                                    style={{
                                        marginTop: 2,
                                        fontSize: 12.5,
                                        color: C.sub,
                                        ...NUM,
                                    }}
                                >
                                    {smCur
                                        ? `거장 ${smCur.holder_count}개 펀드 보유 · 합산 ${fmtMoney(smCur.total_value_usd, krw, fx.rate)}`
                                        : `거장 ${(smMeta.managers || []).length || 16}개 운용사 보유 없음`}
                                </div>
                            </div>
                            <button
                                onClick={() => goStock(smTicker)}
                                style={{
                                    border: "none",
                                    outline: "none",
                                    cursor: "pointer",
                                    background: C.vtS,
                                    color: C.vt,
                                    borderRadius: 999,
                                    padding: "7px 13px",
                                    fontSize: 12.5,
                                    fontWeight: 700,
                                    fontFamily: FONT,
                                    whiteSpace: "nowrap",
                                }}
                            >
                                종목 리포트 →
                            </button>
                            <button
                                onClick={() => {
                                    setSmTicker(null)
                                    setSmQ("")
                                }}
                                aria-label="검색 결과 닫기"
                                style={{
                                    border: "none",
                                    outline: "none",
                                    cursor: "pointer",
                                    background: C.hi,
                                    color: C.sub,
                                    borderRadius: 999,
                                    padding: "7px 12px",
                                    fontSize: 12.5,
                                    fontWeight: 650,
                                    fontFamily: FONT,
                                }}
                            >
                                ✕
                            </button>
                        </div>

                        {!smCur && (
                            <div
                                style={{
                                    marginTop: 10,
                                    padding: "12px 0 4px",
                                    fontSize: 12.5,
                                    color: C.sub,
                                    lineHeight: 1.6,
                                }}
                            >
                                추적 중인 집중형 {(smMeta.managers || []).length || 16}개
                                운용사의 최근 13F 공시에는 이 종목이 없어요. 인덱스펀드
                                보유는 집계하지 않아요(신호 희석). 종목 자체 분석은 위
                                "종목 리포트" 에서 볼 수 있어요.
                            </div>
                        )}
                        {smCur && (
                        <>
                        <div style={{ overflowX: "auto", marginTop: 10 }}>
                            <table
                                className="an-ipf-smstbl"
                                style={{ width: "100%", borderCollapse: "collapse" }}
                            >
                                <thead>
                                    <tr>
                                        {["운용사", "평가액", "펀드 내 비중", "주식수", "보유 시작", "편입 분기가", "기준일", "분기 변화"].map(
                                            (h, i) => (
                                                <th
                                                    key={h}
                                                    style={{
                                                        fontSize: 11.5,
                                                        fontWeight: 650,
                                                        letterSpacing: "0.07em",
                                                        color: C.faint,
                                                        textAlign: i === 0 ? "left" : "right",
                                                        padding: "8px 9px",
                                                        whiteSpace: "nowrap",
                                                    }}
                                                >
                                                    {h}
                                                </th>
                                            )
                                        )}
                                    </tr>
                                </thead>
                                <tbody>
                                    {(smCur.holders || []).map((h: any) => (
                                        <tr key={h.fund}>
                                            <td
                                                onClick={() => jumpToFund(h.fund)}
                                                onKeyDown={(ev: any) => {
                                                    if (ev.key === "Enter") jumpToFund(h.fund)
                                                }}
                                                tabIndex={0}
                                                role="button"
                                                title="아래 목록에서 이 운용사 포트폴리오 보기"
                                                style={{
                                                    padding: "9px 9px",
                                                    fontSize: 13.5,
                                                    fontWeight: 650,
                                                    borderTop: `1px solid ${C.line}`,
                                                    whiteSpace: "nowrap",
                                                    cursor: "pointer",
                                                }}
                                            >
                                                {h.fund}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "9px 9px",
                                                    ...NUM,
                                                    fontSize: 13.5,
                                                    textAlign: "right",
                                                    borderTop: `1px solid ${C.line}`,
                                                    whiteSpace: "nowrap",
                                                }}
                                            >
                                                {fmtMoney(h.value_usd, krw, fx.rate)}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "9px 9px",
                                                    ...NUM,
                                                    fontSize: 13.5,
                                                    textAlign: "right",
                                                    borderTop: `1px solid ${C.line}`,
                                                }}
                                            >
                                                {h.weight_in_fund_pct == null
                                                    ? "—"
                                                    : h.weight_in_fund_pct.toFixed(2) + "%"}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "9px 9px",
                                                    ...NUM,
                                                    fontSize: 13.5,
                                                    textAlign: "right",
                                                    borderTop: `1px solid ${C.line}`,
                                                    whiteSpace: "nowrap",
                                                }}
                                            >
                                                {Math.round(h.shares || 0).toLocaleString()}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "9px 9px",
                                                    ...NUM,
                                                    fontSize: 13,
                                                    textAlign: "right",
                                                    borderTop: `1px solid ${C.line}`,
                                                    whiteSpace: "nowrap",
                                                    color: C.sub,
                                                }}
                                            >
                                                {heldSinceLabel(h)}
                                                {h.quarters_held > 0 && (
                                                    <span style={{ color: C.faint }}>
                                                        {" "}
                                                        ({h.quarters_held}분기
                                                        {h.held_since_floor ? "+" : ""})
                                                    </span>
                                                )}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "9px 9px",
                                                    ...NUM,
                                                    fontSize: 13,
                                                    textAlign: "right",
                                                    borderTop: `1px solid ${C.line}`,
                                                    whiteSpace: "nowrap",
                                                    color: C.sub,
                                                }}
                                            >
                                                {fmtPrice(
                                                    h.held_since_qend_price_usd,
                                                    krw,
                                                    fx.rate
                                                )}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "9px 9px",
                                                    ...NUM,
                                                    fontSize: 12.5,
                                                    textAlign: "right",
                                                    borderTop: `1px solid ${C.line}`,
                                                    whiteSpace: "nowrap",
                                                    color: C.faint,
                                                }}
                                            >
                                                {ym((smFunds[h.fund] || {}).report_date)}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "9px 9px",
                                                    textAlign: "right",
                                                    borderTop: `1px solid ${C.line}`,
                                                }}
                                            >
                                                <span
                                                    style={{
                                                        display: "inline-block",
                                                        padding: "2.5px 9px",
                                                        borderRadius: 999,
                                                        fontSize: 11.5,
                                                        fontWeight: 650,
                                                        background: chipBg(h.change_type),
                                                        color: chipFg(h.change_type),
                                                    }}
                                                >
                                                    {KO_CHANGE[h.change_type] || h.change_type}
                                                </span>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        <div style={{ marginTop: 8, fontSize: 12, color: C.faint, lineHeight: 1.55 }}>
                            "보유 시작"은 최근 {smMeta.held_since_window_quarters || 9}개 분기
                            공시로 역추적한 연속 보유 시작이며, "이전부터"는 추적 범위 이전부터
                            보유 중이라는 뜻이에요. 13F 는 분기말 보유를 최대 45일 뒤에
                            제출하므로 현재 보유와 다를 수 있어요. "편입 분기가"는 그
                            분기말 공시 평가액÷주식수(내재가)로, 실제 매수 체결가가
                            아니에요 — 13F 는 체결가를 공시하지 않아요.
                        </div>
                        </>
                        )}
                    </div>
                )}

                {/* 검색 대기 화면 — 이번 분기 거장 순매수 TOP 10 (탐색 진입점) */}
                {!smQn && !smTicker && smTop10.length > 0 && (
                    <div style={{ marginTop: 12 }}>
                        <div
                            style={{
                                display: "flex",
                                alignItems: "baseline",
                                gap: 8,
                                flexWrap: "wrap",
                            }}
                        >
                            <span style={{ fontSize: 13.5, fontWeight: 750 }}>
                                이번 분기 거장 순매수 TOP 10
                            </span>
                            <span style={{ fontSize: 11.5, color: C.faint }}>
                                신규+증액−감액 펀드 수 기준 · 13F 분기 공시
                            </span>
                        </div>
                        <div
                            style={{
                                marginTop: 6,
                                display: "flex",
                                flexDirection: "column",
                                gap: 2,
                            }}
                        >
                            {smTop10.map((s: any, i: number) => (
                                <div
                                    key={s.ticker}
                                    onClick={() => setSmTicker(s.ticker)}
                                    onKeyDown={(ev: any) => {
                                        if (ev.key === "Enter")
                                            setSmTicker(s.ticker)
                                    }}
                                    role="button"
                                    tabIndex={0}
                                    style={{
                                        display: "flex",
                                        alignItems: "center",
                                        gap: 10,
                                        padding: "8px 6px",
                                        borderRadius: 10,
                                        cursor: "pointer",
                                    }}
                                >
                                    <span
                                        style={{
                                            width: 18,
                                            flexShrink: 0,
                                            fontSize: 12,
                                            fontWeight: 700,
                                            color: i < 3 ? C.vt : C.faint,
                                            textAlign: "center",
                                            ...NUM,
                                        }}
                                    >
                                        {i + 1}
                                    </span>
                                    <TickerLogo ticker={s.ticker} C={C} />
                                    <div style={{ minWidth: 0, flex: 1 }}>
                                        <div
                                            style={{
                                                fontSize: 13.5,
                                                fontWeight: 700,
                                                color: C.ink,
                                                whiteSpace: "nowrap",
                                                overflow: "hidden",
                                                textOverflow: "ellipsis",
                                            }}
                                        >
                                            {uniKoMap[s.ticker] ||
                                                (s.name && s.name !== s.ticker
                                                    ? s.name
                                                    : s.ticker)}
                                        </div>
                                        <div
                                            style={{
                                                fontSize: 11,
                                                color: C.faint,
                                                fontWeight: 600,
                                            }}
                                        >
                                            {s.ticker} · 보유 {s.holder_count}개 펀드
                                        </div>
                                    </div>
                                    <div
                                        style={{
                                            flexShrink: 0,
                                            textAlign: "right",
                                            paddingRight: 4,
                                        }}
                                    >
                                        <div
                                            style={{
                                                fontSize: 12.5,
                                                fontWeight: 750,
                                                color: C.up,
                                                ...NUM,
                                            }}
                                        >
                                            순매수 +{s._net}
                                        </div>
                                        <div
                                            style={{
                                                fontSize: 10.5,
                                                color: C.faint,
                                                fontWeight: 600,
                                                ...NUM,
                                            }}
                                        >
                                            신규 {s._nw} · 증액 {s._inc} · 감액{" "}
                                            {s._dec}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>

            <div
                style={{
                    // 🚨 2026-08-03 grid→flex-wrap. JS 측정(narrow)에 기대지 말 것.
                    //   Framer 는 컴포넌트 프레임 폭이 뷰포트와 다를 수 있어 rootW 가 620 을 넘게 잡히고,
                    //   그러면 Phone(390) 에서도 2단이 유지돼 우측 카드가 잘린다(PM 스크린샷 2026-08-03).
                    //   flex-wrap 은 "둘이 안 들어가면 접는다" 를 브라우저가 판단하므로 측정이 필요 없다.
                    //   좌 300 + 우 320 + gap 18 = 638 미만이면 자동 줄바꿈 → 세로 스택.
                    display: "flex",
                    flexWrap: "wrap",
                    gap: 18,
                    alignItems: "flex-start",
                }}
            >
                {/* 좌: 운용사 목록 — 스크롤 시 제자리 고정(PM 2026-07-30).
                    부모 grid 가 alignItems:"start" 여야 sticky 가 먹는다(stretch 면 트랙 높이만큼
                    늘어나 붙을 자리가 없음). 최대 높이를 뷰포트에 묶어 목록이 화면을 넘지 않게. */}
                <div
                    className="an-ipf-side"
                    style={{
                        background: C.card,
                        borderRadius: 16,
                        overflow: "hidden",
                        // flex / sticky / maxHeight / marginBottom = AN_IPF_CSS. 인라인 금지
                        // (인라인이 클래스를 이겨 미디어쿼리가 안 먹는다).
                        // maxWidth 상한도 두지 말 것 — 줄바꿈된 모바일에서 그 폭에 묶여
                        // 우측이 빈다(2026-08-03 PM 지적).
                        minWidth: 0,
                        display: "flex",
                        flexDirection: "column",
                    }}
                >
                    <div
                        style={{
                            padding: "14px 16px 10px",
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "baseline",
                        }}
                    >
                        <span
                            style={{
                                fontSize: 11.5,
                                fontWeight: 750,
                                letterSpacing: "0.09em",
                                color: C.faint,
                            }}
                        >
                            운용사
                        </span>
                        <span style={{ fontSize: 12, color: C.faint }}>공시 총액순</span>
                    </div>
                    <div style={{ overflowY: "auto", flex: 1, minHeight: 0 }}>
                        {list.map((v, i) => {
                            const on = i === sel
                            return (
                                <button
                                    key={v.cik}
                                    type="button"
                                    onClick={() => setSel(i)}
                                    style={{
                                        width: "100%",
                                        textAlign: "left",
                                        border: 0,
                                        cursor: "pointer",
                                        font: "inherit",
                                        color: C.ink,
                                        background: on ? C.vtS : "transparent",
                                        padding: "11px 16px",
                                        display: "grid",
                                        gridTemplateColumns:
                                            "20px 30px minmax(0,1fr) auto",
                                        gap: 10,
                                        alignItems: "center",
                                    }}
                                >
                                    <span
                                        style={{
                                            ...NUM,
                                            fontSize: 12,
                                            textAlign: "right",
                                            color: on ? C.vt : C.faint,
                                            fontWeight: on ? 750 : 500,
                                        }}
                                    >
                                        {i + 1}
                                    </span>
                                    <Avatar
                                        src={v.profile?.image?.url}
                                        name={v.person || v.institution}
                                        size={30}
                                        C={C}
                                    />
                                    <span style={{ minWidth: 0 }}>
                                        <span
                                            style={{
                                                display: "block",
                                                fontSize: 14,
                                                fontWeight: 650,
                                                color: C.ink,
                                                whiteSpace: "nowrap",
                                                overflow: "hidden",
                                                textOverflow: "ellipsis",
                                            }}
                                        >
                                            {v.person || v.institution}
                                        </span>
                                        <span
                                            style={{
                                                display: "block",
                                                fontSize: 11.5,
                                                color: C.faint,
                                                whiteSpace: "nowrap",
                                                overflow: "hidden",
                                                textOverflow: "ellipsis",
                                            }}
                                        >
                                            {v.institution}
                                        </span>
                                        <span
                                            style={{
                                                display: "block",
                                                height: 3,
                                                borderRadius: 2,
                                                background: C.hi,
                                                marginTop: 5,
                                                overflow: "hidden",
                                            }}
                                        >
                                            <span
                                                style={{
                                                    display: "block",
                                                    height: "100%",
                                                    width: `${v.top10_concentration_pct || 0}%`,
                                                    background: C.vt,
                                                    borderRadius: 2,
                                                }}
                                            />
                                        </span>
                                    </span>
                                    <span style={{ textAlign: "right" }}>
                                        <span
                                            style={{
                                                display: "block",
                                                ...NUM,
                                                fontSize: 13,
                                                fontWeight: 650,
                                            }}
                                        >
                                            {money(v.disclosed_value_usd)}
                                        </span>
                                        <span
                                            style={{
                                                display: "block",
                                                ...NUM,
                                                fontSize: 11,
                                                color: C.faint,
                                            }}
                                        >
                                            {v.holdings_count}
                                            {v.holdings_capped ? "+" : ""}종목
                                        </span>
                                    </span>
                                </button>
                            )
                        })}
                    </div>
                </div>

                {/* 우: 상세 */}
                <div
                    className="an-ipf-detail"
                    style={{
                        background: C.card,
                        borderRadius: 16,
                        // padding = AN_IPF_CSS (미디어쿼리). 인라인 금지.
                        // 남는 공간 전부 차지(999) — 좌측이 기본 300 을 채우고 나머지가 여기로.
                        // basis 320 = 이 값 아래로는 좌측과 나란히 설 수 없다는 선언 → 자동 줄바꿈 유발.
                        flex: "999 1 320px",
                        minWidth: 0,
                    }}
                >
                    <div
                        style={{
                            display: "flex",
                            flexWrap: "wrap",
                            gap: "10px 16px",
                            justifyContent: "space-between",
                            alignItems: "flex-start",
                        }}
                    >
                        <div
                            style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 12,
                                minWidth: 0,
                            }}
                        >
                            <Avatar
                                src={cur.profile?.image?.url}
                                name={cur.person || cur.institution}
                                size={52}
                                C={C}
                            />
                            <div style={{ minWidth: 0 }}>
                                <div
                                    style={{
                                        fontSize: 20,
                                        fontWeight: 800,
                                        letterSpacing: "-0.02em",
                                        color: C.ink,
                                    }}
                                >
                                    {cur.person || cur.institution}
                                </div>
                                <div
                                    style={{
                                        color: C.faint,
                                        fontSize: 12.5,
                                        marginTop: 3,
                                    }}
                                >
                                    {cur.institution} · CIK {cur.cik}
                                </div>
                                {/* 공시에 보이는 방식 — 성향 판정이 아니다.
                                    13F 는 현금·채권·숏이 빠지므로 성향의 근거가 못 된다
                                    (버핏 집중도 90.7% = 16인 중 4위. 판정하면 '공격적'이 됨). */}
                                {cur.disclosed_style?.label ? (
                                    <div
                                        style={{
                                            display: "flex",
                                            flexWrap: "wrap",
                                            alignItems: "center",
                                            gap: 6,
                                            marginTop: 8,
                                        }}
                                    >
                                        <span
                                            style={{
                                                background: C.vtS,
                                                color: C.vt,
                                                borderRadius: 999,
                                                padding: "4px 11px",
                                                fontSize: 12.5,
                                                fontWeight: 750,
                                            }}
                                        >
                                            {cur.disclosed_style.label}
                                        </span>
                                        {(cur.disclosed_style.badges || []).map(
                                            (b: string) => (
                                                <span
                                                    key={b}
                                                    style={{
                                                        background: C.hi,
                                                        color: C.sub,
                                                        borderRadius: 999,
                                                        padding: "4px 10px",
                                                        fontSize: 12,
                                                        fontWeight: 650,
                                                    }}
                                                >
                                                    {b}
                                                </span>
                                            )
                                        )}
                                    </div>
                                ) : null}
                                {/* 🚨 집중도가 높은 인물에만 — 13F 사각지대 고지.
                                    이 줄이 없으면 "버핏 = 몰빵형" 오독이 난다. 지우지 말 것. */}
                                {cur.disclosed_style?.cash_caveat ? (
                                    <div
                                        style={{
                                            fontSize: 12,
                                            color: C.faint,
                                            marginTop: 6,
                                            fontWeight: 600,
                                        }}
                                    >
                                        현금·채권은 이 공시에 나오지 않습니다. 주식만 놓고 본
                                        모습입니다.
                                    </div>
                                ) : null}
                            </div>
                        </div>
                        <div
                            style={{
                                background: C.hi,
                                borderRadius: 12,
                                padding: "8px 12px",
                                fontSize: 12,
                                color: C.sub,
                                textAlign: "right",
                            }}
                        >
                            <span
                                style={{
                                    display: "block",
                                    ...NUM,
                                    fontSize: 13,
                                    color: C.ink,
                                }}
                            >
                                {dot(cur.report_date)}
                            </span>
                            기준 보유 · {dot(cur.filed_at)} 제출
                        </div>
                    </div>

                    {cur.profile && cur.profile.summary ? (
                        <div
                            style={{
                                marginTop: 14,
                                background: C.hi,
                                borderRadius: 13,
                                padding: "12px 14px",
                                fontSize: 13,
                                color: C.sub,
                                lineHeight: 1.68,
                            }}
                        >
                            {cur.profile.summary_ko || cur.profile.summary}
                            {cur.profile.source_url ? (
                                <div style={{ marginTop: 7 }}>
                                    <a
                                        href={cur.profile.source_url}
                                        target="_blank"
                                        rel="noopener"
                                        style={{
                                            color: C.vt,
                                            textDecoration: "none",
                                            fontSize: 12,
                                        }}
                                    >
                                        위키백과 · {cur.profile.name}
                                        {cur.profile.summary_ko ? " · 자동 번역" : ""}
                                    </a>
                                </div>
                            ) : null}
                            {/* 🚨 사진 저작자 표시 = CC BY·BY-SA 의무 사항. 지우지 말 것.
                                표기 없이 쓰면 라이선스 위반이다. */}
                            {cur.profile.image ? (
                                <div
                                    style={{
                                        marginTop: 4,
                                        fontSize: 11.5,
                                        color: C.faint,
                                    }}
                                >
                                    사진{" "}
                                    {cur.profile.image.artist
                                        ? cur.profile.image.artist + " · "
                                        : ""}
                                    {cur.profile.image.license_url ? (
                                        <a
                                            href={cur.profile.image.license_url}
                                            target="_blank"
                                            rel="noopener"
                                            style={{
                                                color: C.faint,
                                                textDecoration: "underline",
                                            }}
                                        >
                                            {cur.profile.image.license}
                                        </a>
                                    ) : (
                                        cur.profile.image.license
                                    )}
                                </div>
                            ) : null}
                        </div>
                    ) : null}

                    {/* 요약 지표 */}
                    <div
                        style={{
                            display: "grid",
                            gridTemplateColumns: `repeat(auto-fit,minmax(${narrow ? 104 : 120}px,1fr))`,
                            gap: 8,
                            marginTop: 15,
                        }}
                    >
                        {[
                            { l: "공시 총액", v: money(cur.disclosed_value_usd) },
                            {
                                l: "보유 종목",
                                // 🚨 holdings_count 는 빌더 상한(TOP_HOLDINGS_PER_FUND)에 걸린다.
                                //   상한이면 실제는 더 많다 — "300종목"으로 단정하면 거짓이 된다.
                                v:
                                    String(cur.holdings_count) +
                                    (cur.holdings_capped ? "+" : ""),
                                sub: cur.holdings_capped
                                    ? "상위 " + cur.holdings_count + "종목 기준"
                                    : undefined,
                            },
                            {
                                l: "상위 10종목 비중",
                                v: (cur.top10_concentration_pct ?? "—") + "%",
                            },
                            {
                                l: "최근 4분기 복제",
                                v: signed(cur.trailing_4q_replication_pct),
                                c: tone(cur.trailing_4q_replication_pct),
                                sub: "실제 성과 아님",
                            },
                            {
                                l: "분기 중 움직임",
                                v: `${cur.new_count}·${cur.increased_count}·${cur.decreased_count}`,
                                sub: "신규·증액·감액",
                            },
                        ].map((s) => (
                            <div
                                key={s.l}
                                style={{
                                    background: C.hi,
                                    borderRadius: 12,
                                    padding: "10px 12px",
                                }}
                            >
                                <span
                                    style={{ display: "block", fontSize: 11.5, color: C.faint }}
                                >
                                    {s.l}
                                </span>
                                <span
                                    style={{
                                        display: "block",
                                        ...NUM,
                                        fontSize: 16.5,
                                        fontWeight: 750,
                                        marginTop: 3,
                                        color: (s as any).c || C.ink,
                                    }}
                                >
                                    {s.v}
                                </span>
                                {(s as any).sub ? (
                                    <span
                                        style={{ display: "block", fontSize: 11.5, color: C.faint }}
                                    >
                                        {(s as any).sub}
                                    </span>
                                ) : null}
                            </div>
                        ))}
                    </div>

                    {/* 분기 복제 수익률 그래프 */}
                    {rs.length ? (
                        <div
                            style={{
                                marginTop: 16,
                                background: C.hi,
                                borderRadius: 13,
                                padding: "14px 16px 12px",
                            }}
                        >
                            <div style={{ fontSize: 12.5, fontWeight: 700 }}>
                                분기별 공시 롱 북 복제 수익률
                            </div>
                            <div
                                style={{
                                    fontSize: 11.5,
                                    color: C.faint,
                                    margin: "3px 0 10px",
                                    lineHeight: 1.55,
                                }}
                            >
                                각 분기말 공시 포지션을 다음 분기말까지 그대로
                                보유했다고 가정한 계산값입니다. 분기 중 매매가
                                반영되지 않아 실제 운용 성과와 다릅니다.
                            </div>
                            <ReturnLine rs={rs} C={C} />
                        </div>
                    ) : null}

                    <div
                        style={{
                            marginTop: 12,
                            fontSize: 12.5,
                            color: C.faint,
                            lineHeight: 1.6,
                        }}
                    >
                        직전 공시({dot(cur.prev_report_date) || "—"}) 대비 공시 총액 변동{" "}
                        {signed(cur.disclosed_value_change_pct)} — 주가 등락과 실제 매매가 함께
                        반영된 값이라 수익률이 아닙니다.
                    </div>
                    {cur.unresolved_ticker_count ? (
                        <div style={{ marginTop: 8, fontSize: 12.5, color: C.faint }}>
                            티커로 변환되지 않은 보유 {cur.unresolved_ticker_count}건은 CUSIP으로
                            표시됩니다.
                        </div>
                    ) : null}

                    {/* 보유 종목 */}
                    <div
                        style={{
                            width: "100%",
                            maxWidth: "100%",
                            minWidth: 0,
                            overflowX: "auto",
                            WebkitOverflowScrolling: "touch",
                            marginTop: 12,
                        }}
                    >
                        <table
                            className="an-ipf-tbl"
                            style={{
                                width: "100%",
                                borderCollapse: "collapse",
                                // minWidth = AN_IPF_CSS (미디어쿼리). 좁은 화면 340 / 넓은 화면 460.
                                // 넘치면 바깥 컨테이너 안에서만 가로 스크롤. 인라인 금지.
                            }}
                        >
                            <thead>
                                <tr>
                                    {["종목", "비중", "평가액", "주식수", "분기 변동"].map(
                                        (h, i) => (
                                            <th
                                                key={h}
                                                style={{
                                                    fontSize: 11,
                                                    fontWeight: 650,
                                                    letterSpacing: "0.07em",
                                                    color: C.faint,
                                                    textAlign: i === 0 ? "left" : "right",
                                                    padding: "8px 9px",
                                                }}
                                            >
                                                {h}
                                            </th>
                                        )
                                    )}
                                </tr>
                            </thead>
                            <tbody>
                                {(cur.top_holdings || []).slice(0, topN).map((h: any) => (
                                    <tr
                                        key={h.cusip}
                                        onClick={() => goStock(h.ticker)}
                                        onKeyDown={(ev: any) => {
                                            if (ev.key === "Enter") goStock(h.ticker)
                                        }}
                                        tabIndex={h.ticker ? 0 : -1}
                                        role={h.ticker ? "link" : undefined}
                                        style={{
                                            cursor: h.ticker ? "pointer" : "default",
                                        }}
                                    >
                                        <td
                                            style={{
                                                padding: "9px 9px",
                                                fontSize: 13.5,
                                                borderTop: `1px solid ${C.line}`,
                                                // 🚨 라이브 정합 — #213 이 650→600 일괄 변경 시
                                                // 이 삼항만 놓쳤고 라이브에는 600 이 반영돼
                                                // 있었다. repo 를 라이브에 맞춘다(RULE 11).
                                                fontWeight: h.ticker ? 650 : 550,
                                                color: h.ticker ? C.ink : C.faint,
                                            }}
                                        >
                                            <span
                                                style={{
                                                    display: "flex",
                                                    alignItems: "center",
                                                    gap: 8,
                                                    minWidth: 0,
                                                }}
                                            >
                                                <TickerLogo ticker={h.ticker} C={C} />
                                                <span
                                                    style={{
                                                        overflow: "hidden",
                                                        textOverflow: "ellipsis",
                                                        whiteSpace: "nowrap",
                                                    }}
                                                >
                                                    {h.ticker || h.cusip}
                                                </span>
                                            </span>
                                        </td>
                                        <td
                                            style={{
                                                padding: "9px 9px",
                                                fontSize: 13.5,
                                                textAlign: "right",
                                                borderTop: `1px solid ${C.line}`,
                                            }}
                                        >
                                            {h.weight_pct == null
                                                ? "—"
                                                : h.weight_pct.toFixed(2) + "%"}
                                            <span
                                                className="an-ipf-bar"
                                                style={{
                                                    display: "block",
                                                    height: 3,
                                                    // width = AN_IPF_CSS. 고정 100 은 좁은 화면에서
                                                    // 이 열의 하한이 되어 표를 넓힌다. 인라인 금지.
                                                    marginLeft: "auto",
                                                    marginTop: 4,
                                                    borderRadius: 2,
                                                    background: C.hi,
                                                    overflow: "hidden",
                                                }}
                                            >
                                                <span
                                                    style={{
                                                        display: "block",
                                                        height: "100%",
                                                        width: `${Math.min(100, (h.weight_pct || 0) * 3)}%`,
                                                        background: C.vt,
                                                    }}
                                                />
                                            </span>
                                        </td>
                                        <td
                                            style={{
                                                padding: "9px 9px",
                                                ...NUM,
                                                fontSize: 13.5,
                                                textAlign: "right",
                                                borderTop: `1px solid ${C.line}`,
                                            }}
                                        >
                                            {money(h.value_usd)}
                                        </td>
                                        <td
                                            style={{
                                                padding: "9px 9px",
                                                ...NUM,
                                                fontSize: 13.5,
                                                textAlign: "right",
                                                borderTop: `1px solid ${C.line}`,
                                            }}
                                        >
                                            {Math.round(h.shares || 0).toLocaleString()}
                                        </td>
                                        <td
                                            style={{
                                                padding: "9px 9px",
                                                textAlign: "right",
                                                borderTop: `1px solid ${C.line}`,
                                            }}
                                        >
                                            <span
                                                style={{
                                                    display: "inline-block",
                                                    padding: "2.5px 9px",
                                                    borderRadius: 999,
                                                    fontSize: 11.5,
                                                    fontWeight: 650,
                                                    background: chipBg(h.change_type),
                                                    color: chipFg(h.change_type),
                                                }}
                                            >
                                                {KO_CHANGE[h.change_type] || h.change_type}
                                            </span>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <div style={{ marginTop: 10, fontSize: 12.5, color: C.faint }}>
                        평가액 상위 {Math.min(topN, (cur.top_holdings || []).length)}종목입니다.
                    </div>
                </div>
            </div>

            <div
                style={{
                    marginTop: 18,
                    fontSize: 12,
                    color: C.faint,
                    lineHeight: 1.65,
                }}
            >
                출처 — SEC EDGAR 13F-HR. 티커는 OpenFIGI로 CUSIP을 변환했으며 변환되지 않은
                항목은 CUSIP으로 표시합니다. 인물 소개와 사진은 위키미디어에서 가져왔으며
                자유 라이선스로 확인된 것만 실었습니다. 저작자와 라이선스는 각 카드에 표기했습니다.
                종목 로고는 토스 제공입니다.
                운용사명 옆 인물은 대표 연관 인물이며 현재 운용 주체와 다를 수 있습니다.
            </div>
        </div>
    )
}

addPropertyControls(PublicInvestorPortfolios, {
    dark: {
        type: ControlType.Boolean,
        title: "Dark (canvas)",
        defaultValue: false,
    },
    dataUrl: {
        type: ControlType.String,
        title: "데이터 URL",
        defaultValue: BLOB + "/us_investor_portfolios.json",
    },
    macroUrl: {
        type: ControlType.String,
        title: "환율 URL",
        defaultValue: BLOB + "/macro_snapshot.json",
    },
    searchUrl: {
        type: ControlType.String,
        title: "종목 검색 데이터 URL",
        defaultValue: BLOB + "/us_smart_money_13f.json",
    },
    universeUrl: {
        type: ControlType.String,
        title: "검색 인덱스 URL (한글명)",
        defaultValue: BLOB + "/universe_search.json",
    },
    topN: {
        type: ControlType.Number,
        title: "표시 종목 수",
        defaultValue: 25,
        min: 3,
        max: 50,
        step: 1,
    },
    stockPath: {
        type: ControlType.String,
        title: "종목 페이지 경로",
        defaultValue: "/stock",
    },
})
