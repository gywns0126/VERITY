import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 종목 발견(Discovery) — VERITY 공개 터미널 (AlphaNest). 토스 "주식 골라보기"식 좌측 탭 + 정렬표/리스트 + 로고·국기.
 * 되돌리지 말 것: 선택 조건은 조회 순서·0건 결과로 바꾸지 않는다. 실패·미수신과 0건을 구분한다.
 * 되돌리지 말 것: 우측 상세는 내용 높이(Fit)를 유지하며 sticky로 표시한다. 내부 세로 스크롤과 화면 높이 제한을 복원하지 않는다. 바깥 배경은 페이지 바탕을 드러낸다.
 * 조건 설명은 기존 판정·정렬과 일치시킨다. 낮은 배수를 저평가·우량 판정으로 바꾸지 않으며, 표시 이유는 수신 자료만 사용한다.
 * 수급 전환은 같은 종목의 최근 두 관측값만 비교한다. 결손·과거 수신을 신규 편입으로 취급하지 않는다.
 * 수익률 배지는 당시 구성·동일비중·수정주가의 완전한 비교만 사용한다. 결손/만료/시장 혼합이면 순위를 숨긴다.
 *
 * 🚨 헌법 가드 (RULE 7 / held-2027 / feedback_scope):
 *  - 모든 리스트·표 = 발행된 사실(stock_report_public + insider_trades + stock_flow_5d + disclosure_forensics) 위 결정론적 규칙. 자체 점수 0 (RULE 6 통과).
 *  - 네이밍 = 필터 사실 그대로. held/추천아님 면책 = 하단 푸터 유지(상단 헤더는 사이트 네비와 중복이라 제거 2026-06-21).
 *  - 애널리스트 컬럼 영구 제외.
 *
 * 🚨 차별 컬럼/스크리너 = 토스 구조적 불가: 내부자(DART)/외국인 수급 + 지배구조(공정위 의결권 지분) + 공시 이력(DART 유증·CB 누적 빈도). edge 플래그=로직용, 탭 강조 안 함(PM "튀어").
 * 🚨 결정 동선 링킹(2026-06-21): URL `?sector=X`·`?screen=Y` 딥링크 수용 → 리포트/결정패널서 "동종업계 더보기" 등으로 필터된 채 진입.
 * 레이아웃 = 페이지 분할 + 넓은 화면(≥980)만 master-detail(표 좌 + 클릭 종목 우측 패널). 그 외 = 행 클릭 시 reportPath?q=ticker.
 * 🚨 모바일(narrow<620): 표는 카드 리스트 강제(8컬럼 가로스크롤 회피) + 표/리스트 토글 숨김. 상단 탭 바 = sticky + 하단 그림자(카드가 밑으로 미끄러지는 토스식 경계).
 * 🚨 sticky: 탭 = wrap(자연흐름) → 뷰포트 기준 top=navTop(네브바 회피). 우측 상세 = top 16px, Fit 높이, 내부 세로 스크롤 없음. 표헤더 = overflowX:auto 표카드가 스크롤 컨테이너라 top=0.
 *   좌측 탭 = 흰박스 없이 회색 배경에 직접(활성만 흰 알약). 모바일 탭바 = full-bleed(좌우 -pad) + 상하 여백 균형 + 프로스트 글래스(반투명 0.7 + backdrop blur, 스크롤 콘텐츠가 뿌옇게 밑으로 사라짐, PM "탭만" 유지).
 * 🚨 TABLE_MIN ≥ 컬럼 최소폭 합(≈776) — 작으면 선택행 배경이 마지막 컬럼서 끊김.
 */

interface Props {
    stockUrl: string
    usStockUrl: string
    usSmallcapUrl?: string
    insiderUrl: string
    usInsiderUrl?: string
    flowUrl: string
    forensicsUrl: string
    performanceUrl?: string
    apiBase: string
    reportPath: string
    dark: boolean
    perList: number
    topOffset: number
}
const DEFAULT_URL =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_report_public.json"
const DEFAULT_INSIDER =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/insider_trades.json"
const DEFAULT_US_INSIDER =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_insider_trades.json"
const DEFAULT_FLOW =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_flow_5d.json"
const DEFAULT_FORENSICS =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/disclosure_forensics.json"
const DEFAULT_API = "https://project-yw131.vercel.app"
const DEFAULT_REPORT = "/stock"
// 데이터 신선도 — ISO → 상대시각(다른 public 컴포넌트와 동일 패턴).
function fmtAge(iso: any): string {
    if (!iso) return ""
    try {
        const mins = Math.max(
            0,
            Math.round((Date.now() - new Date(String(iso)).getTime()) / 60000)
        )
        if (mins < 60) return mins + "분 전"
        const hrs = Math.round(mins / 60)
        if (hrs < 24) return hrs + "시간 전"
        return Math.round(hrs / 24) + "일 전"
    } catch {
        return ""
    }
}

// ── Brandfetch 로고 (토스 핫링킹 제거 2026-07-10) — logo_map(빌드타임 확정) + US 티커 규칙 + 이니셜 폴백 ──
const BF_CID = "1idalDez9T7KlggM8qX" // 공개 임베드 client id (Logo Link 전용)
const BF_MAP_URL =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/logo_map.json"
let __bfMap: Record<string, string> | null = null
let __bfColors: Record<string, string> = {}
let __bfShapes: Record<string, number> = {}
let __bfStyle: any = { padS: 8, padW: 15, wideRatio: 2.2 } // 발행 데이터(style)로 조절 — 코드 수정 불요
let __bfP: Promise<Record<string, string>> | null = null
function fetchBfMap(): Promise<Record<string, string>> {
    if (__bfMap) return Promise.resolve(__bfMap)
    if (!__bfP)
        __bfP = fetch(BF_MAP_URL)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                __bfMap = (d && d.logos) || {}
                __bfColors = (d && d.colors) || {}
                __bfShapes = (d && d.shapes) || {}
                __bfStyle = (d && d.style) || __bfStyle
                return __bfMap as Record<string, string>
            })
            .catch(() => ({}) as Record<string, string>)
    return __bfP
}
function useBfLogoMap(): Record<string, string> | null {
    const [m, setM] = useState<Record<string, string> | null>(__bfMap)
    useEffect(() => {
        let al = true
        fetchBfMap().then((mm) => {
            if (al) setM(mm)
        })
        return () => {
            al = false
        }
    }, [])
    return m
}
function bfLogoPad(ticker: any): string {
    // 모양 적응 패딩 — 심볼(정사각)은 크게, 워드마크(가로 김)는 여백 확보 (토스식 가시성)
    const tk = String(ticker || "")
        .toUpperCase()
        .replace(/-/g, ".")
    const r = __bfShapes[tk] || __bfShapes[tk.replace(/\./g, "-")] || 1
    if (r === 0) return "0%" // 큐레이션 풀블리드 아이콘(자체 배경 포함) = 타일 꽉 채움
    return (
        (r > (__bfStyle.wideRatio || 2.2)
            ? __bfStyle.padW || 15
            : __bfStyle.padS || 8) + "%"
    )
}
function bfInitialBg(ticker: any): string {
    // 이니셜 타일 — 티커 해시 투톤 그라데이션 (미보유 4.6K 도 디자인 자산화, 종목별 고정색)
    let h = 0
    const s = String(ticker || "?")
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360
    return (
        "linear-gradient(135deg, hsl(" +
        h +
        ",62%,55%), hsl(" +
        ((h + 42) % 360) +
        ",68%,42%))"
    )
}
function bfLogoBg(ticker: any): string {
    // 아이덴티티 색 틴트 타일 (토스식 참조 — 색은 로고 대표색/공식 브랜드색, 자산 복사 아님)
    const tk = String(ticker || "")
        .toUpperCase()
        .replace(/-/g, ".")
    const c = __bfColors[tk] || __bfColors[tk.replace(/\./g, "-")]
    // 토스식 넉아웃 (기본): 브랜드색 솔리드 배경 + 로고 흰 실루엣(bfLogoFilter). 조건 미충족 = 솔리드 파스텔.
    // style.mode 노브: "knockout"(기본) | "pastel". mixPct = 파스텔 혼합비(기본 30).
    const p2 =
        (__bfMap && (__bfMap[tk] || __bfMap[tk.replace(/\./g, "-")])) || ""
    if (
        c &&
        p2 &&
        p2.indexOf("http") !== 0 &&
        (__bfStyle.mode || "pastel") === "knockout"
    )
        return c // 솔리드 브랜드색
    if (!c) return "#ffffff"
    const mix = Number(__bfStyle.mixPct || 30)
    try {
        if (
            typeof CSS !== "undefined" &&
            CSS.supports &&
            CSS.supports("color", "color-mix(in srgb, red 50%, white)")
        )
            return `color-mix(in srgb, ${c} ${mix}%, #ffffff)`
    } catch (e2) {}
    return c + (__bfStyle.tintA || "4D")
}
function bfLogoFilter(ticker: any): string {
    // 넉아웃 조건과 동일할 때만 흰 실루엣 (Brandfetch 투명 로고 한정 — 파비콘류는 불투명이라 제외)
    const tk = String(ticker || "")
        .toUpperCase()
        .replace(/-/g, ".")
    const c = __bfColors[tk] || __bfColors[tk.replace(/\./g, "-")]
    const p2 =
        (__bfMap && (__bfMap[tk] || __bfMap[tk.replace(/\./g, "-")])) || ""
    return c &&
        p2 &&
        p2.indexOf("http") !== 0 &&
        (__bfStyle.mode || "pastel") === "knockout"
        ? "brightness(0) invert(1)"
        : "none"
}
function bfLogoSrc(
    ticker: any,
    lm: Record<string, string> | null,
    size: number
): string {
    const tk = String(ticker || "")
        .toUpperCase()
        .replace(/-/g, ".")
    if (!tk) return ""
    // 로고 = 토스 종목 CDN (PM 결정: 완전 공개[런칭] 전까지 토스 사용, 2026-07-12). 404/차단 시 onError → 이니셜 폴백.
    return (
        "https://static.toss.im/png-icons/securities/icn-sec-fill-" +
        tk +
        ".png"
    )
}
const FLAG_BASE = "https://hatscripts.github.io/circle-flags/flags/"

// 🚨 2026-07-24 테마 = 자체 내장 CSS 변수(--an-dsc-*) 구동. JS 다크 감지 전면 제거 + 헤드 CSS 의존 제거.
//   <style>{AN_PALETTE} 정적 HTML 정합. chevron data-URI = var 불가라 고정 gray(#8b95a1). 되돌리지 말 것.
const LIGHT = {
    bg: "#f8f9fb",
    card: "#ffffff",
    ink: "#191f28",
    sub: "#4e5968",
    faint: "#8b95a1",
    line: "#e5e8eb",
    up: "#f04452",
    down: "#3182f6",
    vg: "#0ca678",
    vgS: "#e7faf0",
    vt: "#6c5ce7",
    vtS: "#f0edff",
    glass: "rgba(248,249,251,0.7)",
    skBase: "#e9edf1",
    skHi: "#f3f5f7",
    shadowStrong: "rgba(0,0,0,0.14)",
}
const DARK = {
    bg: "#1d242c",
    card: "#171c23",
    ink: "#e3e7ec",
    sub: "#9aa4b1",
    faint: "#828d9b",
    line: "#252b34",
    up: "#f04452",
    down: "#5b9bff",
    vg: "#34e08a",
    vgS: "#0f241c",
    vt: "#a99bff",
    vtS: "#241f3a",
    glass: "rgba(29,36,44,0.7)",
    skBase: "#222a33",
    skHi: "#2d3742",
    shadowStrong: "rgba(0,0,0,0.5)",
}

// 🎨 팔레트 자체 내장 — LIGHT/DARK 를 CSS 변수(--an-dsc-*)로 발행. 정적 HTML 정합. 되돌리지 말 것.
const _ANP = "dsc"
const AN_PALETTE =
    "body{" +
    Object.keys(LIGHT)
        .map((k) => "--an-" + _ANP + "-" + k + ":" + (LIGHT as any)[k])
        .join(";") +
    "}" +
    'body[data-framer-theme="dark"]{' +
    Object.keys(DARK)
        .map((k) => "--an-" + _ANP + "-" + k + ":" + (DARK as any)[k])
        .join(";") +
    "}"
const C: Record<string, string> = {}
for (const _k of Object.keys(LIGHT)) C[_k] = "var(--an-" + _ANP + "-" + _k + ")"
const FONT =
    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const KR_MK = ["KOSPI", "KOSDAQ", "KONEX"]
const PANEL_FACTS = [
    "시가총액",
    "PER",
    "PBR",
    "ROE",
    "부채비율",
    "D/E",
    "영업이익률",
    "순이익률",
    "Altman-Z",
] // 부채비율=국장 / D/E=미장(키 상이, null 아닌 쪽만 노출). 배당수익률·EPS=양쪽 0% 소스부재라 제거
const DILUTIVE = ["유상증자", "전환사채(CB)", "신주인수권부사채(BW)"]

function num(s: any): number | null {
    if (s == null) return null
    const m = String(s).match(/-?[\d,]+\.?\d*/)
    return m ? parseFloat(m[0].replace(/,/g, "")) : null
}
function parseCap(s: any): number | null {
    if (s == null) return null
    const str = String(s)
    let v = 0
    const jo = str.match(/([\d.]+)\s*조/)
    if (jo) v += parseFloat(jo[1]) * 10000
    const eok = str.match(/([\d.]+)\s*억/)
    if (eok) v += parseFloat(eok[1])
    return v > 0 ? v : null
}
function fmtShares(v: any): string {
    const x = Number(v)
    if (!isFinite(x) || x === 0) return "0"
    const a = Math.abs(x)
    const sign = x > 0 ? "+" : "−"
    if (a >= 1e8) return sign + (a / 1e8).toFixed(1) + "억주"
    if (a >= 1e4)
        return sign + Math.round(a / 1e4).toLocaleString("en-US") + "만주"
    return sign + Math.round(a).toLocaleString("en-US") + "주"
}
function mmdd(s: any): string {
    const x = String(s || "").replace(/-/g, "")
    if (/^\d{8}$/.test(x)) return x.slice(4, 6) + "." + x.slice(6, 8)
    if (/^\d{4}-\d{2}-\d{2}/.test(String(s || "")))
        return String(s).slice(5, 10).replace("-", ".")
    return String(s || "")
}
function dilCount(f: any): number {
    if (!f || !f.counts) return 0
    let n = 0
    for (const k of DILUTIVE) n += Number(f.counts[k]) || 0
    return n
}
function pvs(s: any, key: string): string | null {
    const rows = (s.peer && s.peer.rows) || []
    for (const r of rows) if (r.key === key) return r.vs || null
    return null
}
function sectorOf(s: any): string {
    // KR=peer/overview 섹터. US=business(SIC 업종, 깨끗한 섹터 없음) fallback.
    return (
        (s.peer && s.peer.sector) ||
        (s.overview && s.overview.sector) ||
        (!/^\d{6}$/.test(String(s.ticker || "")) ? s.business || "" : "") ||
        ""
    )
}
function flagCode(market: any): string {
    const m = String(market || "").toUpperCase()
    if (
        KR_MK.indexOf(m) >= 0 ||
        m.indexOf("KOS") >= 0 ||
        m.indexOf("KONEX") >= 0
    )
        return "kr"
    if (
        m.indexOf("NAS") >= 0 ||
        m.indexOf("NYSE") >= 0 ||
        m.indexOf("AMEX") >= 0 ||
        m.indexOf("US") >= 0
    )
        return "us"
    return "kr"
}

function Logo(props: {
    ticker: string
    name: string
    market: string
    C: any
    size?: number
}) {
    const { ticker, name, market, C } = props
    const size = props.size || 32
    const [err, setErr] = useState(false)
    const lm = useBfLogoMap()
    const bfSrc = bfLogoSrc(ticker, lm, size)
    const ch =
        String(name || "?")
            .trim()
            .charAt(0) || "?"
    const code = flagCode(market)
    const fsize = Math.round(size * 0.46)
    return (
        <div
            style={{
                position: "relative",
                width: size,
                height: size,
                flexShrink: 0,
            }}
        >
            {!err && bfSrc ? (
                <img
                    src={bfSrc}
                    alt=""
                    loading="lazy"
                    decoding="async"
                    width={size}
                    height={size}
                    onError={() => setErr(true)}
                    style={{
                        width: size,
                        height: size,
                        borderRadius: Math.round(size * 0.32),
                        objectFit: "cover",
                        display: "block",
                        background: "transparent",
                    }}
                />
            ) : (
                <div
                    style={{
                        width: size,
                        height: size,
                        borderRadius: Math.round(size * 0.32),
                        background: bfInitialBg(ticker),
                        color: "#ffffff",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: Math.round(size * 0.42),
                        fontWeight: 800,
                    }}
                >
                    {ch}
                </div>
            )}
            {code && (
                <img
                    src={FLAG_BASE + code + ".svg"}
                    alt=""
                    loading="lazy"
                    decoding="async"
                    width={fsize}
                    height={fsize}
                    style={{
                        position: "absolute",
                        right: -3,
                        bottom: -3,
                        width: fsize,
                        height: fsize,
                        borderRadius: "50%",
                        border: `1.5px solid ${C.card}`,
                        background: C.card,
                        display: "block",
                        boxShadow: "0 1px 2px rgba(0,0,0,0.18)",
                    }}
                />
            )}
        </div>
    )
}

interface Ctx {
    insiderMap: Record<string, any>
    flowMap: Record<string, any[]>
    forensicsMap: Record<string, any>
}
interface Screen {
    id: string
    group: "전체" | "수급·자본변동" | "가치·수익성" | "재무·자산가치"
    tab: string
    title: string
    rule: string
    note: string
    order: string
    peerKeys?: string[]
    edge?: boolean
    pred: (s: any, ctx: Ctx) => boolean
    chips: string[]
    sortBy: (s: any, ctx: Ctx) => number
}
const SCREENS: Screen[] = [
    {
        id: "all",
        group: "전체",
        tab: "전체",
        title: "전체 종목",
        rule: "현재 수신한 종목 리포트 안에서 정렬·필터로 탐색",
        note: "거래소 전체 상장종목을 빠짐없이 조회한 목록은 아니에요. 필요한 지표가 없는 종목은 추가 조건에서 제외될 수 있어요.",
        order: "시가총액 큰 순",
        pred: () => true,
        chips: ["PBR", "PER", "ROE"],
        sortBy: (s) => -(parseCap((s.facts || {})["시가총액"]) ?? -1),
    },
    {
        id: "insider_buy",
        group: "수급·자본변동",
        tab: "내부자 순매수",
        edge: true,
        title: "내부자(임원·주요주주)가 순매수한 회사",
        rule: "국내 DART·미국 SEC Form 4 · 내부자 순증감 > 0",
        note: "수집된 내부자 순증감 합계예요. 거래 사유·수집 기간을 원문에서 확인해야 하며, 회사 전망을 판정한 결과는 아니에요.",
        order: "내부자 순증감 주식 수 큰 순",
        pred: (s, ctx) => {
            const e = ctx.insiderMap[s.ticker]
            return !!(e && Number(e.net_change) > 0)
        },
        chips: ["PBR", "ROE"],
        sortBy: (s, ctx) =>
            -Number((ctx.insiderMap[s.ticker] || {}).net_change || 0),
    },
    {
        id: "insider_dom",
        group: "수급·자본변동",
        tab: "내부자 매수우세",
        edge: true,
        title: "내부자 매수 건수가 매도보다 많은 회사",
        rule: "국내 DART·미국 SEC Form 4 · 매수 건수 > 매도 건수",
        note: "건수 차이로 거른 목록이에요. 거래 금액·주식 수의 크기나 매수 이유는 별도로 확인해야 해요.",
        order: "매수·매도 건수 차이 큰 순",
        pred: (s, ctx) => {
            const e = ctx.insiderMap[s.ticker]
            return !!(e && Number(e.buy_n) > Number(e.sell_n))
        },
        chips: ["PBR", "ROE"],
        sortBy: (s, ctx) => {
            const e = ctx.insiderMap[s.ticker] || {}
            return -((Number(e.buy_n) || 0) - (Number(e.sell_n) || 0))
        },
    },
    {
        id: "foreign_buy",
        group: "수급·자본변동",
        tab: "외국인 순매수",
        edge: true,
        title: "외국인이 최근 순매수한 회사",
        rule: "네이버 수급 · 수신 자료의 마지막 거래일 외국인 순매매 > 0",
        note: "오늘이나 장중 거래를 뜻하지 않아요. 종목별 마지막 거래일과 순매수 규모를 함께 확인해주세요.",
        order: "외국인 순매매 주식 수 큰 순",
        pred: (s, ctx) => {
            const f = ctx.flowMap[s.ticker]
            return !!(f && f.length && Number(f[f.length - 1].foreign_net) > 0)
        },
        chips: ["PBR", "ROE"],
        sortBy: (s, ctx) => {
            const f = ctx.flowMap[s.ticker]
            return f && f.length ? -Number(f[f.length - 1].foreign_net || 0) : 0
        },
    },
    {
        id: "dilution_hist",
        group: "수급·자본변동",
        tab: "유증·CB 이력",
        edge: true,
        title: "유상증자·전환사채·BW 발행 이력이 있는 회사",
        rule: "DART 공시 — 자본조달성 발행(유증/CB/BW) 1건 이상 (사실 빈도)",
        note: "수집된 공시 이력의 건수예요. 발표와 실제 발행·전환은 다를 수 있고, 건수만으로 희석 규모를 판단하지 않아요.",
        order: "수집된 유증·CB·BW 공시 건수 큰 순",
        pred: (s, ctx) => dilCount(ctx.forensicsMap[s.ticker]) > 0,
        chips: ["PBR", "PER"],
        sortBy: (s, ctx) => -dilCount(ctx.forensicsMap[s.ticker]),
    },
    {
        id: "value_quality_strict",
        group: "가치·수익성",
        tab: "세 지표 비교",
        title: "업종보다 PBR·PER은 낮고 ROE는 높은 회사",
        rule: "PBR·PER < 업종 중앙값 + ROE > 업종 중앙값",
        note: "세 비교 조건을 동시에 적용해요. 낮은 배수와 높은 ROE만으로 저평가·우량 여부가 확정되지는 않아요.",
        order: "PBR 낮은 순",
        peerKeys: ["PBR", "PER", "ROE"],
        pred: (s) =>
            pvs(s, "PBR") === "below" &&
            pvs(s, "PER") === "below" &&
            pvs(s, "ROE") === "above",
        chips: ["PBR", "PER", "ROE"],
        sortBy: (s) => num((s.facts || {}).PBR) ?? 99,
    },
    {
        id: "value_quality",
        group: "가치·수익성",
        tab: "PBR·ROE 비교",
        title: "업종보다 PBR은 낮고 ROE는 높은 회사",
        rule: "PBR < 업종 중앙값 + ROE > 업종 중앙값",
        note: "장부가 대비 가격과 자기자본이익률을 함께 비교해요. 사업 전망·일회성 이익·부채는 별도로 확인해주세요.",
        order: "PBR 낮은 순",
        peerKeys: ["PBR", "ROE"],
        pred: (s) => pvs(s, "PBR") === "below" && pvs(s, "ROE") === "above",
        chips: ["PBR", "ROE", "부채비율"],
        sortBy: (s) => num((s.facts || {}).PBR) ?? 99,
    },
    {
        id: "per_cheap",
        group: "가치·수익성",
        tab: "낮은 PER",
        title: "PER이 업종 중앙값보다 낮은 회사",
        rule: "PER < 업종 중앙값",
        note: "이익 대비 가격 배수가 낮다는 조건이에요. 이익의 기준 기간과 일회성 요인을 확인해야 해요.",
        order: "PER 낮은 순",
        peerKeys: ["PER"],
        pred: (s) => pvs(s, "PER") === "below",
        chips: ["PER", "ROE", "시가총액"],
        sortBy: (s) => num((s.facts || {}).PER) ?? 999,
    },
    {
        id: "roe_top",
        group: "가치·수익성",
        tab: "높은 ROE",
        title: "ROE가 업종 중앙값보다 높은 회사",
        rule: "ROE > 업종 중앙값",
        note: "ROE는 자기자본 대비 이익 비율이에요. 평균이 아닌 중앙값과 비교하며, 높은 값이 수익 지속성을 보장하지는 않아요.",
        order: "ROE 높은 순",
        peerKeys: ["ROE"],
        pred: (s) => pvs(s, "ROE") === "above",
        chips: ["ROE", "PBR", "부채비율"],
        sortBy: (s) => -(num((s.facts || {}).ROE) ?? -1),
    },
    {
        id: "low_debt",
        group: "재무·자산가치",
        tab: "낮은 부채비율",
        title: "부채비율이 업종 중앙값보다 낮은 회사",
        rule: "부채비율 < 업종 중앙값",
        note: "부채비율 비교값이 있는 종목만 포함돼요. 미국 D/E를 이 조건에 대신 넣거나, 낮은 부채비율을 재무 안전 판정으로 해석하지 않아요.",
        order: "부채비율 낮은 순",
        peerKeys: ["부채비율"],
        pred: (s) => pvs(s, "부채비율") === "below",
        chips: ["부채비율", "ROE", "PBR"],
        sortBy: (s) => num((s.facts || {})["부채비율"]) ?? 999,
    },
    {
        id: "below_book",
        group: "재무·자산가치",
        tab: "PBR 1 미만",
        title: "수신한 PBR이 1 미만인 회사",
        rule: "PBR < 1.0",
        note: "장부가 대비 가격 비율을 보는 조건이에요. 0·음수 여부와 자본 상태를 먼저 확인해야 하며, 자산가치나 저평가를 확정하지 않아요.",
        order: "PBR 낮은 순",
        pred: (s) => (num((s.facts || {}).PBR) ?? 9) < 1.0,
        chips: ["PBR", "ROE", "배당수익률"],
        sortBy: (s) => num((s.facts || {}).PBR) ?? 99,
    },
]


// Explain the existing predicate; never reclassify or fill absent values with zero.
function discoveryDisplayValue(v: any): string {
    return typeof v === "number" && Number.isFinite(v) ? String(v) : typeof v === "string" && v.trim() ? v.trim() : "미제공"
}
type DiscoveryFlowChange = { kind: "entered" | "continuing" | "older" | "unknown" | "not_buy"; text: string }
function discoveryFlowDate(value: any): string {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return ""
    const parsed = new Date(value + "T00:00:00Z")
    return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value ? value : ""
}
function discoveryFlowValue(value: any): number | null {
    if (typeof value !== "number" && (typeof value !== "string" || !/^[+-]?(?:\d+\.?\d*|\.\d+)$/.test(value.trim()))) return null
    const number = Number(value)
    return Number.isFinite(number) ? number : null
}
function discoveryFlowChange(rows: any, asOf: string): DiscoveryFlowChange {
    const unknown: DiscoveryFlowChange = { kind: "unknown", text: "비교 불가 · 최근 두 관측일의 수급값이 필요해요." }
    if (!Array.isArray(rows) || !rows.length) return unknown
    const last = rows[rows.length - 1], previous = rows[rows.length - 2]
    const lastDate = discoveryFlowDate(last?.date), previousDate = discoveryFlowDate(previous?.date)
    if (!lastDate || !asOf || lastDate > asOf) return unknown
    if (lastDate < asOf) return { kind: "older", text: `과거 수신 · ${lastDate} 자료 (최신 수신일 ${asOf}과 다름)` }
    const current = discoveryFlowValue(last?.foreign_net), before = discoveryFlowValue(previous?.foreign_net)
    // Never skip a missing penultimate value to compare against an older observation.
    if (!previousDate || previousDate >= lastDate || current === null || before === null) return unknown
    const values = `${previousDate} ${before.toLocaleString("ko-KR")}주 → ${lastDate} ${current.toLocaleString("ko-KR")}주`
    if (current <= 0) return { kind: "not_buy", text: `현재 순매수 조건 아님 · ${values}` }
    return { kind: before <= 0 ? "entered" : "continuing", text: `${before <= 0 ? "순매수 전환" : "순매수 지속"} · ${values}` }
}
function discoveryFlowHistory(flowMap: Record<string, any[]>) {
    let asOf = ""
    for (const rows of Object.values(flowMap)) {
        const date = Array.isArray(rows) ? discoveryFlowDate(rows[rows.length - 1]?.date) : ""
        if (date > asOf) asOf = date
    }
    const byTicker: Record<string, DiscoveryFlowChange> = {}
    for (const [ticker, rows] of Object.entries(flowMap)) byTicker[ticker] = discoveryFlowChange(rows, asOf)
    return { asOf, byTicker }
}
function discoveryFlowCoverage(stocks: any[], byTicker: Record<string, DiscoveryFlowChange>) {
    const counts = { total: stocks.length, comparable: 0, entered: 0, older: 0, unknown: 0 }
    for (const stock of stocks) {
        const kind = byTicker[stock.ticker]?.kind
        if (kind === "entered" || kind === "continuing") counts.comparable++
        if (kind === "entered") counts.entered++
        else if (kind === "older") counts.older++
        else if (kind !== "continuing") counts.unknown++
    }
    return counts
}
function discoveryReason(sc: Screen, s: any, ctx: Ctx): string {
    if (sc.peerKeys) return sc.peerKeys.map((key) => {
        const row = (s.peer?.rows || []).find((r: any) => r.key === key)
        const direction = row?.vs === "below" ? "낮음" : row?.vs === "above" ? "높음" : row?.vs === "equal" ? "같음" : "비교 미제공"
        return key + " " + discoveryDisplayValue(row?.value) + " / 업종 중앙값 " + discoveryDisplayValue(row?.median) + " (" + direction + ")"
    }).join(" · ")
    const ins = ctx.insiderMap[s.ticker]
    if (sc.id === "insider_buy") return "수집된 내부자 순증감 " + discoveryDisplayValue(ins?.net_change) + "주"
    if (sc.id === "insider_dom") return "수집된 매수 " + discoveryDisplayValue(ins?.buy_n) + "건 / 매도 " + discoveryDisplayValue(ins?.sell_n) + "건"
    if (sc.id === "foreign_buy") { const rows = ctx.flowMap[s.ticker] || [], row = rows[rows.length - 1]; return "거래일 " + discoveryDisplayValue(row?.date) + " · 외국인 순매매 " + discoveryDisplayValue(row?.foreign_net) + "주" }
    if (sc.id === "dilution_hist") return ctx.forensicsMap[s.ticker]?.counts ? "수집된 유증·CB·BW 공시 " + dilCount(ctx.forensicsMap[s.ticker]) + "건" : "공시 이력 미제공"
    if (sc.id === "below_book") return "PBR " + discoveryDisplayValue(s.facts?.PBR) + " · 적용 조건 1 미만"
    return "현재 수신한 종목 리포트에 포함돼 있어요."
}

const COLS: {
    key: string
    label: string
    align: string
    w: number
    sort: boolean
}[] = [
    { key: "rank", label: "#", align: "right", w: 30, sort: false },
    { key: "name", label: "종목", align: "left", w: 0, sort: true },
    { key: "cap", label: "시총", align: "right", w: 92, sort: true },
    { key: "PER", label: "PER", align: "right", w: 58, sort: true },
    { key: "PBR", label: "PBR", align: "right", w: 58, sort: true },
    { key: "ROE", label: "ROE", align: "right", w: 64, sort: true },
    { key: "insider", label: "내부자", align: "right", w: 100, sort: true },
    { key: "sector", label: "섹터", align: "left", w: 96, sort: true },
]
const TABLE_MIN = 780
const RANGE_METRICS = ["PER", "PBR", "ROE", "부채비율", "D/E"] // D/E=미장 부채 필터(부채비율은 국장만). 배당수익률=소스부재 제거

function metricNum(s: any, key: string): number | null {
    const f = s.facts || {}
    if (key === "cap") return parseCap(f["시가총액"])
    return num(f[key])
}

type DiscoveryKind = "stocks" | "flows" | "performance"
const EMPTY_DISCOVERY_DOCS: any[] = []
const EMPTY_DISCOVERY_FLOWS: Record<string, any[]> = {}
// Public artifacts only. Revalidation never replaces a successful document with a failed response.
const discoveryPublicDocs = new Map<string, any>()
const discoveryPublicDetails = new Map<string, any>()
function discoveryListUrl(url: string | undefined, filename: string): string | undefined {
    if (!url) return url
    return url.replace(/(?:stock_report_public|us_stock_report_public|us_stock_report_us_smallcap)\.json(?=\?|#|$)/, filename)
}
function validDiscoveryDoc(d: any, kind: DiscoveryKind): boolean {
    if (kind === "performance") return d?._meta?.schema === "discovery-performance-v1" && Array.isArray(d.windows)
    if (kind === "stocks") return Array.isArray(d) || !!(d && Array.isArray(d.stocks))
    const rows = d && (d.flows || d)
    return !!rows && typeof rows === "object" && !Array.isArray(rows) &&
        Object.entries(rows).every(([k, v]) => k === "_meta" ||
            (Array.isArray(v) && v.every(row => row && typeof row === "object" && !Array.isArray(row))))
}
async function loadDiscoverySources(urls: string[], kind: DiscoveryKind, signal: AbortSignal) {
    return Promise.all(urls.map(async (url) => {
        try {
            const r = await fetch(url, { signal })
            if (!r.ok) return null
            const d = await r.json()
            return validDiscoveryDoc(d, kind) ? d : null
        } catch { return null }
    }))
}
function useDiscoverySources(urls: (string | undefined)[], kind: DiscoveryKind, retry: number) {
    const key = JSON.stringify([...new Set(urls.filter((u): u is string => !!u))])
    const [state, setState] = useState<{ key: string; docs: any[]; failed: number; settled: boolean } | null>(null)
    useEffect(() => {
        let alive = true
        const controller = new AbortController()
        const timer = setTimeout(() => controller.abort(), 15000)
        const selected = JSON.parse(key) as string[]
        setState(previous => {
            if (previous?.key === key) return previous
            return {
                key, docs: selected.map(url => discoveryPublicDocs.get(kind + ":" + url) || null), failed: 0,
                settled: selected.some(url => discoveryPublicDocs.has(kind + ":" + url)) || !selected.length,
            }
        })
        loadDiscoverySources(selected, kind, controller.signal).then((fresh) => {
            clearTimeout(timer)
            if (!alive) return
            const docs = fresh.map((doc, index) => {
                const cacheKey = kind + ":" + selected[index]
                if (doc) discoveryPublicDocs.set(cacheKey, doc)
                return doc || discoveryPublicDocs.get(cacheKey) || null
            })
            setState({ key, docs, failed: fresh.filter(doc => !doc).length, settled: true })
        })
        return () => { alive = false; clearTimeout(timer); controller.abort() }
    }, [key, kind, retry])
    const requested = (JSON.parse(key) as string[]).length
    const current = state?.key === key ? state : null
    const docs = current?.docs || EMPTY_DISCOVERY_DOCS
    const loading = !!requested && !current?.settled
    const received = docs.filter(Boolean).length
    return { loading, docs, requested, received, failed: current?.failed || 0 }
}
function discoveryRows(docs: any[]): any[] {
    const seen = new Set<string>()
    return docs.flatMap((d) => Array.isArray(d) ? d : d?.stocks || []).filter((s) => {
        const ticker = s && typeof s.ticker === "string" ? s.ticker.trim() : ""
        if (!ticker || seen.has(ticker)) return false
        seen.add(ticker)
        return true
    })
}
function discoveryRangeError(metric: string, min: string, max: string): string {
    if (!metric) return ""
    const lo = min.trim() === "" ? null : Number(min)
    const hi = max.trim() === "" ? null : Number(max)
    if ((lo !== null && !Number.isFinite(lo)) || (hi !== null && !Number.isFinite(hi)))
        return "지표 범위에는 유한한 숫자를 입력해주세요."
    return lo !== null && hi !== null && lo > hi ? "최솟값은 최댓값보다 클 수 없어요." : ""
}

const DISCOVERY_HISTORY_KEY = "__alphaNestDiscoveryV1"
type DiscoveryHistorySnapshot = {
    version: 1
    screen: string
    performancePeriod: number
    view: string
    sortKey: string
    sortDir: number
    sector: string
    market: string
    rangeMetric: string
    rangeMin: string
    rangeMax: string
    selected: string
    onlyFlowEntries: boolean
    scrollY: number
}
function discoveryHistoryText(value: unknown, max: number): string {
    return typeof value === "string" ? value.slice(0, max) : ""
}
function readDiscoveryHistorySnapshot(): DiscoveryHistorySnapshot | null {
    if (typeof window === "undefined") return null
    try {
        const raw = window.history.state?.[DISCOVERY_HISTORY_KEY]
        if (!raw || raw.version !== 1) return null
        return {
            version: 1,
            screen: SCREENS.some((screen) => screen.id === raw.screen) ? raw.screen : "all",
            performancePeriod: [1, 3, 6].includes(raw.performancePeriod) ? raw.performancePeriod : 3,
            view: raw.view === "list" ? "list" : "table",
            sortKey: COLS.some((column) => column.key === raw.sortKey) ? raw.sortKey : "cap",
            sortDir: raw.sortDir === 1 ? 1 : -1,
            sector: discoveryHistoryText(raw.sector, 120),
            market: ["all", "kr", "us"].includes(raw.market) ? raw.market : "all",
            rangeMetric: RANGE_METRICS.includes(raw.rangeMetric) ? raw.rangeMetric : "",
            rangeMin: discoveryHistoryText(raw.rangeMin, 40),
            rangeMax: discoveryHistoryText(raw.rangeMax, 40),
            selected: discoveryHistoryText(raw.selected, 24),
            onlyFlowEntries: raw.onlyFlowEntries === true,
            scrollY: Number.isFinite(raw.scrollY) ? Math.max(0, Math.min(raw.scrollY, 10000000)) : 0,
        }
    } catch {
        return null
    }
}

// Backend summaries are rechecked here; a stale or incomplete document cannot award a badge.
function discoveryPerformance(doc: any, market: string, period: number, filtered: boolean, now = Date.now()) {
    const unavailable = (message: string) => ({ message, winners: [] as string[], window: null as any })
    if (market === "all") return unavailable("국장·미장을 선택하면 같은 시장 안에서 비교해요.")
    if (filtered) return unavailable("수익률 비교는 추가 필터를 해제한 시장 전체 조건 기준이에요.")
    const meta = doc?._meta
    if (!meta || meta.schema !== "discovery-performance-v1" || !Array.isArray(doc.windows)) return unavailable("당시 구성과 가격 자료를 확인한 뒤 수익률을 표시해요.")
    const expires = Date.parse(meta.valid_until), generated = Date.parse(meta.generated_at)
    if (!Number.isFinite(expires) || !Number.isFinite(generated) || generated > now || expires <= now || expires - generated > 86400000 || now - generated > 86400000) return unavailable("수익률 자료 갱신이 필요해요. 이전 순위는 표시하지 않아요.")
    if (meta.weighting !== "equal-weight-buy-and-hold" || meta.basis !== "split-and-dividend-adjusted-close" || meta.currency !== "market-local" || meta.costs !== "excluded") return unavailable("수익률 계산 기준을 확인 중이에요.")
    const found = doc.windows.filter((v: any) => v?.market === market && v?.period === period)
    if (found.length !== 1) return unavailable("선택한 기간의 비교 자료가 없어요.")
    const w = found[0]
    if (!discoveryFlowDate(w.start) || !discoveryFlowDate(w.end) || ![1, 3, 6].includes(period)) return unavailable("수익률 기준일을 확인 중이에요.")
    const anchor = new Date(w.end + "T00:00:00Z"), day = anchor.getUTCDate()
    anchor.setUTCDate(1); anchor.setUTCMonth(anchor.getUTCMonth() - period)
    anchor.setUTCDate(Math.min(day, new Date(Date.UTC(anchor.getUTCFullYear(), anchor.getUTCMonth() + 1, 0)).getUTCDate()))
    const anchorGap = (anchor.getTime() - Date.parse(w.start)) / 86400000
    if (anchorGap < 0 || anchorGap > 7 || Date.parse(w.end) > now || now - Date.parse(w.end) > 8 * 86400000) return unavailable("선택한 기간과 수익률 기준일이 일치하지 않아요.")
    const ids = SCREENS.filter(s => s.id !== "all" && (market === "kr" || !["foreign_buy", "dilution_hist", "low_debt"].includes(s.id))).map(s => s.id)
    const validRow = (row: any) => row && Number.isInteger(row.total) && row.total >= 0 && row.priced === row.total && row.unknown === 0 && row.missing_count === 0 && Array.isArray(row.source_errors) && !row.source_errors.length && (row.status === "empty" ? row.total === 0 && row.return_pct === null : row.status === "ready" && row.total > 0 && typeof row.return_pct === "number" && Number.isFinite(row.return_pct) && row.return_pct >= -100)
    if (w.status !== "ready" || !discoveryFlowDate(w.start) || !discoveryFlowDate(w.end) || w.start >= w.end ||
        !Array.isArray(w.categories) || w.categories.length !== ids.length || w.categories.some((c: any) => !c || typeof c !== "object") || new Set(w.categories.map((c: any) => c.id)).size !== ids.length ||
        !w.categories.every((c: any) => ids.includes(c.id) && validRow(c)) || !validRow(w.benchmark) || w.benchmark.status !== "ready") return unavailable("구성·가격에 결손 또는 미확인 항목이 있어 순위를 표시하지 않아요.")
    const ranked = w.categories.filter((c: any) => c.status === "ready")
    if (ranked.length < 2) return unavailable("비교 가능한 조건이 충분하지 않아요.")
    const max = Math.max(...ranked.map((c: any) => c.return_pct))
    const winners = ranked.filter((c: any) => Math.abs(c.return_pct - max) < 1e-8).map((c: any) => c.id)
    if (!Array.isArray(w.winners) || winners.length !== w.winners.length || !w.winners.every((id: any) => winners.includes(id)) || new Set(w.winners).size !== winners.length) return unavailable("수익률 순위 정합성을 확인 중이에요.")
    return { message: `${w.start} ~ ${w.end} · ${market === "kr" ? "원화" : "달러"} 기준 · 비교 ${ranked.length}/${ids.length}개 조건`, winners, window: w }
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicDiscovery(props: Props) {
    const {
        stockUrl,
        usStockUrl,
        usSmallcapUrl,
        insiderUrl,
        usInsiderUrl,
        flowUrl,
        forensicsUrl,
        performanceUrl,
        apiBase,
        reportPath,
        dark,
        perList,
        topOffset,
    } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const cap = Math.max(10, Math.min(120, perList || 40))
    const base = (apiBase || DEFAULT_API).replace(/\/+$/, "")
    const navTop = Math.max(0, Number(topOffset) || 60) // 사용자 고정 네브바 높이 — 탭 sticky top 에만(전체 패딩 X, PM "탭만")

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [retry, setRetry] = useState(0)
    const reports = useDiscoverySources([
        discoveryListUrl(stockUrl, "stock_report_list_public.json"),
        discoveryListUrl(usStockUrl, "us_stock_report_list_public.json"),
        discoveryListUrl(usSmallcapUrl, "us_smallcap_report_list_public.json"),
    ], "stocks", retry)
    const insiders = useDiscoverySources([insiderUrl, usInsiderUrl], "stocks", retry)
    const flows = useDiscoverySources([flowUrl], "flows", retry)
    const forensics = useDiscoverySources([forensicsUrl], "stocks", retry)
    const performance = useDiscoverySources([performanceUrl], "performance", retry)
    const [performancePeriod, setPerformancePeriod] = useState(3)
    const [performanceNow, setPerformanceNow] = useState(() => Date.now())
    const performanceExpiry = performance.docs[0]?._meta?.valid_until
    useEffect(() => {
        const expires = Date.parse(performanceExpiry)
        setPerformanceNow(Date.now())
        if (!Number.isFinite(expires) || expires <= Date.now()) return
        const timer = setTimeout(() => setPerformanceNow(Date.now()), Math.min(expires - Date.now() + 1, 86400001))
        return () => clearTimeout(timer)
    }, [performanceExpiry])
    const list = useMemo(() => discoveryRows(reports.docs), [reports.docs])
    const genAt = stockUrl && reports.docs[0]?._meta?.generated_at || ""
    const insiderMap = useMemo<Record<string, any>>(() => Object.fromEntries(discoveryRows(insiders.docs).map(s => [s.ticker, s])), [insiders.docs])
    const flowMap: Record<string, any[]> = flows.docs[0]?.flows || flows.docs[0] || EMPTY_DISCOVERY_FLOWS
    const flowHistory = useMemo(() => discoveryFlowHistory(flowMap), [flowMap])
    const forensicsMap = useMemo<Record<string, any>>(() => Object.fromEntries(discoveryRows(forensics.docs).map(s => [s.ticker, s])), [forensics.docs])
    const [tab, setTab] = useState(0)
    const [view, setView] = useState<string>("table")
    const [sortKey, setSortKey] = useState<string>("cap")
    const [sortDir, setSortDir] = useState<number>(-1)
    const [sector, setSector] = useState<string>("")
    const [mkt, setMkt] = useState<string>("all") // 전체/국장(kr)/미장(us) 토글
    const [rMetric, setRMetric] = useState<string>("")
    const [rMin, setRMin] = useState<string>("")
    const [rMax, setRMax] = useState<string>("")
    const [selected, setSelected] = useState<string>("")
    const [onlyFlowEntries, setOnlyFlowEntries] = useState(false)
    const [restoreScroll, setRestoreScroll] = useState<number | null>(null)
    const performanceView = discoveryPerformance(performance.docs[0], mkt, performancePeriod,
        !!(sector || rMetric && (rMin.trim() || rMax.trim()) || SCREENS[tab]?.id === "foreign_buy" && onlyFlowEntries), Math.max(performanceNow, Date.now()))

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => {
            for (const e of entries) {
                const box = Array.isArray(e.borderBoxSize) ? e.borderBoxSize[0] : e.borderBoxSize as any
                const width = box?.inlineSize ?? el.getBoundingClientRect().width
                if (Number.isFinite(width) && width > 0) setW(width)
            }
        })
        try { ro.observe(el, { box: "border-box" }) } catch { ro.observe(el) }
        return () => ro.disconnect()
    }, [])

    // URL 딥링크와 이 히스토리 엔트리의 발견 상태를 1회 복원한다.
    useEffect(() => {
        if (onCanvas || typeof window === "undefined") return
        try {
            const restored = readDiscoveryHistorySnapshot()
            if (restored) {
                setPerformancePeriod(restored.performancePeriod)
                setTab(Math.max(0, SCREENS.findIndex((screen) => screen.id === restored.screen)))
                setView(restored.view)
                setSortKey(restored.sortKey)
                setSortDir(restored.sortDir)
                setSector(restored.sector)
                setMkt(restored.market)
                setRMetric(restored.rangeMetric)
                setRMin(restored.rangeMin)
                setRMax(restored.rangeMax)
                setSelected(restored.selected)
                setOnlyFlowEntries(restored.onlyFlowEntries)
                setRestoreScroll(restored.scrollY)
            }
            const sp = new URLSearchParams(window.location.search)
            const sec = sp.get("sector")
            if (sec) setSector(sec)
            const scr = sp.get("screen")
            if (scr) {
                const i = SCREENS.findIndex((sc) => sc.id === scr)
                if (i >= 0) setTab(i)
            }
        } catch {
            /* ignore */
        }
    }, [onCanvas])

    const narrow = w > 0 && w < 620
    const wide = w >= 980 // master-detail 패널 표시 임계
    const pad = narrow ? 12 : 18
    const ctx = useMemo<Ctx>(
        () => ({ insiderMap, flowMap, forensicsMap }),
        [insiderMap, flowMap, forensicsMap]
    )
    const insiderNet = (s: any): number | null => {
        const e = insiderMap[s.ticker]
        if (!e || e.net_change == null) return null
        const n = Number(e.net_change)
        return isFinite(n) ? n : null
    }

    const counts = useMemo(() => {
        if (!list.length) return SCREENS.map(() => 0)
        return SCREENS.map((sc) => list.filter((s) => sc.pred(s, ctx)).length)
    }, [list, ctx])
    // A zero count or delayed source never changes the user's selected condition.
    const visibleTabs = SCREENS.map((_, i) => i)

    const sectors = useMemo(() => {
        const set: Record<string, number> = {}
        for (const s of list) {
            const sec = sectorOf(s)
            if (sec) set[sec] = (set[sec] || 0) + 1
        }
        return Object.keys(set).sort((a, b) => set[b] - set[a])
    }, [list])

    const sc = SCREENS[tab] || SCREENS[0]
    const sourceFor = (id: string) => id.startsWith("insider_") ? insiders : id === "foreign_buy" ? flows : id === "dilution_hist" ? forensics : reports
    const activeSource = sourceFor(sc.id)
    const pendingResult = reports.loading || activeSource.loading
    const unavailableResult = !pendingResult && (!reports.received || !activeSource.received)
    const sourceIssues = [
        ["종목 리포트", reports], ["내부자 자료", insiders],
        ["외국인 수급", flows], ["공시 이력", forensics],
    ] as const
    useEffect(() => {
        if (onCanvas || pendingResult || w <= 0 || restoreScroll === null) return
        let secondFrame = 0
        const firstFrame = requestAnimationFrame(() => {
            secondFrame = requestAnimationFrame(() => {
                window.scrollTo(0, restoreScroll)
                setRestoreScroll(null)
            })
        })
        return () => {
            cancelAnimationFrame(firstFrame)
            if (secondFrame) cancelAnimationFrame(secondFrame)
        }
    }, [onCanvas, pendingResult, restoreScroll, w])
    const rangeError = discoveryRangeError(rMetric, rMin, rMax)
    const rMinN = rMin.trim() === "" ? null : Number(rMin)
    const rMaxN = rMax.trim() === "" ? null : Number(rMax)
    const useTable = view === "table" && !narrow // 모바일=카드 강제(8컬럼 가로스크롤 회피)
    const sortDescription = useTable ? `${COLS.find(c => c.key === sortKey)?.label || sortKey} ${sortDir < 0 ? "내림차순" : "오름차순"}` : sc.order

    const sel = useMemo(() => {
        if (!list.length || rangeError || pendingResult || unavailableResult) return { total: 0, items: [] as any[], flowCoverage: null as ReturnType<typeof discoveryFlowCoverage> | null }
        let hits = list.filter((s) => sc.pred(s, ctx))
        if (mkt !== "all")
            hits = hits.filter(
                (s) =>
                    !/^\d{6}$/.test(String(s.ticker || "")) === (mkt === "us")
            )
        if (sector) hits = hits.filter((s) => sectorOf(s) === sector)
        if (rMetric && (rMinN != null || rMaxN != null)) {
            hits = hits.filter((s) => {
                const v = metricNum(s, rMetric)
                if (v == null) return false
                if (rMinN != null && v < rMinN) return false
                if (rMaxN != null && v > rMaxN) return false
                return true
            })
        }
        const flowCoverage = sc.id === "foreign_buy" ? discoveryFlowCoverage(hits, flowHistory.byTicker) : null
        if (sc.id === "foreign_buy" && onlyFlowEntries) hits = hits.filter(s => flowHistory.byTicker[s.ticker]?.kind === "entered")
        const arr = hits.slice()
        const cmpNull = (va: number | null, vb: number | null) => {
            if (va == null && vb == null) return 0
            if (va == null) return 1
            if (vb == null) return -1
            return (va - vb) * sortDir
        }
        if (useTable) {
            if (sortKey === "name") {
                arr.sort(
                    (a, b) =>
                        String(a.name || "").localeCompare(
                            String(b.name || "")
                        ) * sortDir
                )
            } else if (sortKey === "sector") {
                arr.sort(
                    (a, b) => sectorOf(a).localeCompare(sectorOf(b)) * sortDir
                )
            } else if (sortKey === "insider") {
                arr.sort((a, b) => cmpNull(insiderNet(a), insiderNet(b)))
            } else {
                arr.sort((a, b) =>
                    cmpNull(metricNum(a, sortKey), metricNum(b, sortKey))
                )
            }
        } else {
            arr.sort((a, b) => sc.sortBy(a, ctx) - sc.sortBy(b, ctx))
        }
        return { total: hits.length, items: arr.slice(0, cap), flowCoverage }
    }, [
        list,
        sc,
        ctx,
        mkt,
        sector,
        rMetric,
        rMinN,
        rMaxN,
        rangeError,
        pendingResult,
        unavailableResult,
        flowHistory,
        onlyFlowEntries,
        useTable,
        sortKey,
        sortDir,
        cap,
    ])

    // 넓은 화면: 선택 종목 자동 유지(없거나 목록 밖이면 최상단). 좁은 화면: 패널 없음.
    useEffect(() => {
        if (!wide || !sel.items.length) return
        const inList = sel.items.some((s) => s.ticker === selected)
        if (!inList) setSelected(sel.items[0].ticker)
    }, [wide, sel.items, selected])

    const selStock = useMemo(
        () => sel.items.find((s) => s.ticker === selected) || null,
        [sel.items, selected]
    )
    const detailKey = wide && selStock ? base + ":" + String(selStock.ticker).toUpperCase() : ""
    const [detailRetry, setDetailRetry] = useState(0)
    const [detailState, setDetailState] = useState<{ key: string; report: any; failed: boolean } | null>(null)
    const selectedReport = detailKey && detailState?.key === detailKey ? detailState.report : null
    useEffect(() => {
        if (onCanvas || !detailKey || !selStock) return
        const ticker = String(selStock.ticker).toUpperCase()
        let alive = true
        const controller = new AbortController()
        setDetailState({ key: detailKey, report: discoveryPublicDetails.get(detailKey) || null, failed: false })
        fetch(base + "/api/stock_slice?ticker=" + encodeURIComponent(ticker) + (/^\d{6}$/.test(ticker) ? "&overview=1" : ""), { signal: controller.signal })
            .then(response => response.ok ? response.json() : null)
            .then(data => {
                if (!alive) return
                const report = data?.status === "ok" && data.report?.ticker?.toUpperCase() === ticker ? data.report : null
                if (report) discoveryPublicDetails.set(detailKey, report)
                setDetailState({ key: detailKey, report: report || discoveryPublicDetails.get(detailKey) || null, failed: !report })
            })
            .catch(() => {
                if (alive) setDetailState({ key: detailKey, report: discoveryPublicDetails.get(detailKey) || null, failed: true })
            })
        return () => { alive = false; controller.abort() }
    }, [onCanvas, detailKey, detailRetry])

    // 선택 종목 실시간가(/api/stock) = 2026-07-03 컴플라이언스로 제거 — 시세는 리포트(네이버 link-out/TV 위젯)에서

    const go = (ticker: string) => {
        if (onCanvas || typeof window === "undefined" || !ticker) return
        const p = (reportPath || DEFAULT_REPORT).replace(/\/+$/, "") || "/"
        try {
            const currentHistoryState = window.history.state
            const historyBase = currentHistoryState && typeof currentHistoryState === "object" ? currentHistoryState : {}
            const snapshot: DiscoveryHistorySnapshot = {
                version: 1,
                screen: sc.id,
                performancePeriod,
                view,
                sortKey,
                sortDir,
                sector,
                market: mkt,
                rangeMetric: rMetric,
                rangeMin: rMin,
                rangeMax: rMax,
                selected,
                onlyFlowEntries,
                scrollY: Math.max(0, window.scrollY || 0),
            }
            // 이 발견 페이지의 현재 히스토리 엔트리에만 저장해 새 방문에 이전 조건이 섞이지 않게 한다.
            window.history.replaceState({ ...historyBase, [DISCOVERY_HISTORY_KEY]: snapshot }, "", window.location.href)
        } catch {
            /* 탐색 상태 저장 실패가 리포트 이동을 막지 않게 한다. */
        }
        window.location.href = p + "?q=" + encodeURIComponent(ticker)
    }
    const onRow = (ticker: string) => {
        if (wide) setSelected(ticker)
        else go(ticker)
    }
    const onSort = (key: string) => {
        if (sortKey === key) {
            setSortDir((d) => -d)
            return
        }
        setSortKey(key)
        setSortDir(key === "name" || key === "sector" ? 1 : -1)
    }
    const resetFilters = () => {
        setMkt("all")
        setSector("")
        setRMetric("")
        setRMin("")
        setRMax("")
        setOnlyFlowEntries(false)
    }

    const wrap: CSSProperties = {
        width: "100%",
        minHeight: "100%",
        background: "transparent",
        fontFamily: FONT,
        padding: `8px ${pad}px ${pad}px`,
        boxSizing: "border-box",
        color: C.ink,
        // 🚨 스태킹 격리 — 내부 sticky(zIndex)가 페이지 fixed 네브바 위로 그려지는 사고 원천 차단 (2026-07-08, /discover nav zIndex 부재 사고. 페이지 nav zIndex 10 + 여기 격리 이중 방어).
        position: "relative",
        zIndex: 0,
        isolation: "isolate",
    }
    const chipFor = (s: any, key: string) => {
        const v = (s.facts || {})[key]
        if (v == null) return null
        const vs = pvs(s, key)
        const arrow = vs === "above" ? " ↑" : vs === "below" ? " ↓" : ""
        const col = vs === "above" ? C.vg : vs === "below" ? C.down : C.faint
        return (
            <span
                key={key}
                style={{
                    fontSize: 11,
                    fontWeight: 600,
                    color: C.sub,
                    background: C.bg,
                    borderRadius: 7,
                    padding: "3px 8px",
                    whiteSpace: "nowrap",
                }}
            >
                <span style={{ color: C.faint }}>{key} </span>
                <span style={{ color: C.ink }}>{v}</span>
                {arrow && (
                    <span style={{ color: col, fontWeight: 700 }}>{arrow}</span>
                )}
            </span>
        )
    }
    const edgeChips = (s: any) => {
        const out: any[] = []
        const nv = insiderNet(s)
        if (nv)
            out.push(
                <span
                    key="ins"
                    style={{
                        fontSize: 11,
                        fontWeight: 700,
                        color: nv > 0 ? C.up : C.down,
                        background: C.bg,
                        borderRadius: 7,
                        padding: "3px 8px",
                        whiteSpace: "nowrap",
                    }}
                >
                    내부자 {fmtShares(nv)}
                </span>
            )
        const f = flowMap[s.ticker]
        if (f && f.length) {
            const fn = Number(f[f.length - 1].foreign_net)
            if (fn)
                out.push(
                    <span
                        key="for"
                        style={{
                            fontSize: 11,
                            fontWeight: 700,
                            color: fn > 0 ? C.up : C.down,
                            background: C.bg,
                            borderRadius: 7,
                            padding: "3px 8px",
                            whiteSpace: "nowrap",
                        }}
                    >
                        외국인 {fmtShares(fn)}
                    </span>
                )
        }
        const dc = dilCount(forensicsMap[s.ticker])
        if (dc > 0)
            out.push(
                <span
                    key="dil"
                    style={{
                        fontSize: 11,
                        fontWeight: 700,
                        color: C.sub,
                        background: C.bg,
                        borderRadius: 7,
                        padding: "3px 8px",
                        whiteSpace: "nowrap",
                    }}
                >
                    유증·CB {dc}회
                </span>
            )
        return out
    }
    // 커스텀 chevron (OS 기본 화살표 제거 — appearance none). 색 = 테마 faint.
    // data URI 전체 encodeURIComponent — 공백/따옴표 raw 상태면 Safari·Framer 퍼블리시에서 파싱 실패 → placeholder 텍스처 노출 (다크에서만 도드라짐).
    const chevronUrl = `url("data:image/svg+xml,${encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 6' width='10' height='6'><path d='M1 1l4 4 4-4' stroke='#8b95a1' stroke-width='1.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/></svg>`)}")`
    const selStyle: CSSProperties = {
        border: "none",
        borderRadius: 9,
        padding: "7px 28px 7px 11px",
        minHeight: "var(--an-dsc-control-height, 36px)",
        lineHeight: 1.25,
        boxSizing: "border-box",
        fontSize: 12,
        fontFamily: FONT,
        fontWeight: 700,
        backgroundColor: C.card,
        color: C.ink,
        outline: "none",
        cursor: "pointer",
        appearance: "none",
        WebkitAppearance: "none",
        MozAppearance: "none",
        backgroundImage: chevronUrl,
        backgroundRepeat: "no-repeat",
        backgroundPosition: "right 10px center",
        backgroundSize: "10px 6px",
    }
    const numStyle: CSSProperties = {
        width: 58,
        border: `1px solid ${C.line}`,
        borderRadius: 9,
        padding: "7px 8px",
        minHeight: "var(--an-dsc-control-height, 36px)",
        lineHeight: 1.25,
        fontSize: 12,
        fontFamily: FONT,
        fontWeight: 700,
        background: C.card,
        color: C.ink,
        outline: "none",
        boxSizing: "border-box",
    }

    // 로딩 스켈레톤 — 탭/헤더/툴바/결과 전 영역 일관 적용 (list 적재 전 빈 영역 방지). 토스식 shimmer.
    const loading = reports.loading
    const skBase = C.skBase
    const skHi = C.skHi
    const skBlock = (bw: any, bh: number, br = 6): CSSProperties => ({
        width: bw,
        height: bh,
        borderRadius: br,
        background: skBase,
        backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`,
        backgroundSize: "800px 100%",
        animation: "vsrShimmer 1.4s ease-in-out infinite",
        flexShrink: 0,
    })

    const tabButton = (i: number) => {
        const active = i === tab
        const best = performanceView.winners.includes(SCREENS[i].id)
        const badge = best ? <span style={{ display: narrow ? "inline-block" : "block", marginTop: narrow ? 0 : 3, marginLeft: narrow ? 6 : 0, fontSize: 10.5, fontWeight: 700, color: C.vt }}>{performancePeriod}개월 {performanceView.winners.length > 1 ? "공동 " : ""}1위</span> : null
        if (narrow) {
            return (
                <button
                    key={SCREENS[i].id}
                    aria-pressed={active}
                    onClick={() => setTab(i)}
                    style={{
                        flexShrink: 0,
                        border: "none",
                        cursor: "pointer",
                        fontFamily: FONT,
                        padding: "8px 12px",
                        minHeight: "var(--an-dsc-control-height, 36px)",
                        lineHeight: 1.25,
                        boxSizing: "border-box",
                        borderRadius: 999,
                        fontSize: 12.5,
                        fontWeight: 700,
                        background: active ? C.card : "transparent",
                        color: active ? C.ink : C.sub,
                        boxShadow: active
                            ? "0 1px 2px rgba(0,0,0,0.06)"
                            : "none",
                    }}
                >
                    {SCREENS[i].tab}
                    {badge}
                    <span
                        style={{
                            marginLeft: 6,
                            fontWeight: 700,
                            color: C.faint,
                        }}
                    >
                        {reports.loading || sourceFor(SCREENS[i].id).loading ? "…" : !reports.received || !sourceFor(SCREENS[i].id).received ? "—" : counts[i]}
                    </span>
                </button>
            )
        }
        return (
            <button
                key={SCREENS[i].id}
                aria-pressed={active}
                onClick={() => setTab(i)}
                style={{
                    width: "100%",
                    border: "none",
                    cursor: "pointer",
                    fontFamily: FONT,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 8,
                    padding: "7px 12px",
                    minHeight: "var(--an-dsc-control-height, 36px)",
                    lineHeight: 1.25,
                    boxSizing: "border-box",
                    borderRadius: 10,
                    fontSize: 13.5,
                    fontWeight: 700,
                    textAlign: "left",
                    background: active ? C.card : "transparent",
                    color: active ? C.ink : C.sub,
                    boxShadow: active ? "0 1px 2px rgba(0,0,0,0.06)" : "none",
                }}
            >
                <span style={{ whiteSpace: "nowrap" }}>{SCREENS[i].tab}{badge}</span>
                <span
                    style={{
                        flexShrink: 0,
                        fontWeight: 700,
                        fontSize: 12,
                        color: C.faint,
                    }}
                >
                    {reports.loading || sourceFor(SCREENS[i].id).loading ? "…" : !reports.received || !sourceFor(SCREENS[i].id).received ? "—" : counts[i]}
                </span>
            </button>
        )
    }

    const cellText = (s: any, key: string) => {
        const f = s.facts || {}
        if (key === "cap") return f["시가총액"] || "—"
        if (key === "sector") return sectorOf(s) || "—"
        return f[key] != null ? f[key] : "—"
    }
    const colStyle = (col: any, extra?: CSSProperties): CSSProperties => ({
        width: col.w || undefined,
        minWidth: col.w === 0 ? 148 : col.w,
        flex: col.w === 0 ? 1 : ("none" as any),
        textAlign: col.align,
        whiteSpace: "nowrap",
        overflow: "hidden",
        textOverflow: "ellipsis",
        ...extra,
    })

    // 우측 상세 패널(데스크탑) — 선택한 한 종목의 공개 슬라이스만 로드.
    const detailPanel = () => {
        if (!selStock) return null
        if (!selectedReport) return (
            <div role="status" style={{ flexShrink: 0, width: 340, background: C.card, borderRadius: 16, padding: 16, boxSizing: "border-box", color: C.sub, fontSize: 12.5, fontWeight: 600 }}>
                {detailState?.key === detailKey && detailState.failed ? "종목 상세 자료를 확인하지 못했어요." : "종목 상세 자료를 불러오는 중이에요."}
                {detailState?.key === detailKey && detailState.failed && <button onClick={() => setDetailRetry(n => n + 1)} style={{ ...selStyle, marginTop: 8, display: "block" }}>상세 다시 불러오기</button>}
            </div>
        )
        const s = selectedReport
        const facts = s.facts || {}
        const ins = insiderMap[s.ticker]
        const flow = flowMap[s.ticker] || []
        const flast = flow.length ? flow[flow.length - 1] : null
        const peerRows = (s.peer && s.peer.rows) || []
        const own = s.ownership || null
        const foren = forensicsMap[s.ticker] || null
        const kv = (k: string, v: any, color?: string) => (
            <div
                key={k}
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    padding: "6px 0",
                    fontSize: 12.5,
                }}
            >
                <span style={{ color: C.sub, fontWeight: 600 }}>{k}</span>
                <span
                    style={{
                        fontWeight: 700,
                        color: color || C.ink,
                        fontVariantNumeric: "tabular-nums",
                    }}
                >
                    {v}
                </span>
            </div>
        )
        const sub = (t: string) => (
            <div
                style={{
                    fontSize: 11.5,
                    fontWeight: 800,
                    color: C.faint,
                    marginTop: 14,
                    marginBottom: 2,
                }}
            >
                {t}
            </div>
        )
        return (
            <div
                style={{
                    flexShrink: 0,
                    width: 340,
                    height: "fit-content",
                    position: "sticky",
                    top: 16,
                    background: C.card,
                    borderRadius: 16,
                    padding: 16,
                    boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
                    boxSizing: "border-box",
                }}
            >
                <div
                    style={{
                        display: "flex",
                        alignItems: "flex-start",
                        gap: 11,
                    }}
                >
                    <Logo
                        ticker={s.ticker}
                        name={s.name}
                        market={s.market}
                        C={C}
                        size={40}
                    />
                    <div style={{ flex: 1, minWidth: 0 }}>
                        <div
                            style={{
                                fontSize: 17,
                                fontWeight: 800,
                                color: C.ink,
                                letterSpacing: "-0.3px",
                                whiteSpace: "nowrap",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                            }}
                        >
                            {s.name}
                        </div>
                        <div
                            style={{
                                fontSize: 11.5,
                                color: C.faint,
                                fontWeight: 600,
                            }}
                        >
                            {s.ticker} · {s.market}
                        </div>
                    </div>
                    <button
                        onClick={() => setSelected("")}
                        style={{
                            border: "none",
                            background: "transparent",
                            cursor: "pointer",
                            fontSize: 16,
                            color: C.faint,
                            fontWeight: 700,
                            padding: 0,
                            lineHeight: 1,
                        }}
                    >
                        ×
                    </button>
                </div>
                {s.business && (
                    <div
                        style={{
                            fontSize: 12,
                            color: C.sub,
                            fontWeight: 600,
                            marginTop: 6,
                            lineHeight: 1.45,
                        }}
                    >
                        {s.business}
                    </div>
                )}

                <div style={{ marginTop: 6 }}>
                    {sub("기본 지표")}
                    {PANEL_FACTS.filter((k) => facts[k] != null).map((k) =>
                        kv(k, facts[k])
                    )}
                </div>

                {peerRows.length > 0 && (
                    <div>
                        {sub("동종업계 비교 (업종 중앙값)")}
                        {peerRows.map((r: any, i: number) =>
                            kv(
                                r.key,
                                <span>
                                    {r.value}{" "}
                                    <span
                                        style={{
                                            color: C.faint,
                                            fontWeight: 600,
                                        }}
                                    >
                                        vs {r.median}
                                    </span>{" "}
                                    <span style={{ color: C.vt }}>
                                        {r.vs === "above"
                                            ? "↑"
                                            : r.vs === "below"
                                              ? "↓"
                                              : "="}
                                    </span>
                                </span>
                            )
                        )}
                    </div>
                )}

                {ins && Number(ins.total) > 0 && (
                    <div>
                        {sub(
                            /^\d{6}$/.test(String(s.ticker || ""))
                                ? "내부자 거래 (DART)"
                                : "내부자 거래 (SEC Form 4)"
                        )}
                        {kv(
                            "순증감",
                            fmtShares(ins.net_change),
                            Number(ins.net_change) >= 0 ? C.up : C.down
                        )}
                        {kv("매수 / 매도", `${ins.buy_n}건 / ${ins.sell_n}건`)}
                        {(ins.trades || [])
                            .slice(0, 2)
                            .map((t: any, i: number) => (
                                <div
                                    key={i}
                                    style={{
                                        display: "flex",
                                        justifyContent: "space-between",
                                        fontSize: 11.5,
                                        padding: "4px 0",
                                        color: C.sub,
                                        fontWeight: 600,
                                    }}
                                >
                                    <span>
                                        {mmdd(t.date)} {t.person}
                                        {t.position ? ` · ${t.position}` : ""}
                                    </span>
                                    <span
                                        style={{
                                            color:
                                                Number(t.change) >= 0
                                                    ? C.up
                                                    : C.down,
                                            fontWeight: 700,
                                        }}
                                    >
                                        {fmtShares(t.change)}
                                    </span>
                                </div>
                            ))}
                    </div>
                )}

                {flast &&
                (Number(flast.foreign_net) || Number(flast.inst_net)) ? (
                    <div>
                        {sub("외국인·기관 수급 (최근)")}
                        {kv(
                            "외국인 순매매",
                            fmtShares(flast.foreign_net),
                            Number(flast.foreign_net) >= 0 ? C.up : C.down
                        )}
                        {kv(
                            "기관 순매매",
                            fmtShares(flast.inst_net),
                            Number(flast.inst_net) >= 0 ? C.up : C.down
                        )}
                    </div>
                ) : null}

                {own && (
                    <div>
                        {sub("지배구조 · 공정위 (의결권 지분)")}
                        {own.group && kv("기업집단", own.group, C.vt)}
                        {own.family_pct != null &&
                            kv(
                                "총수일가 지배지분",
                                own.family_pct + "%",
                                own.family_pct > 0 ? C.ink : C.faint
                            )}
                        {(own.shareholders || [])
                            .slice(0, 3)
                            .map((sh: any, i: number) => (
                                <div
                                    key={i}
                                    style={{
                                        display: "flex",
                                        justifyContent: "space-between",
                                        fontSize: 11.5,
                                        padding: "4px 0",
                                        color: C.sub,
                                        fontWeight: 600,
                                    }}
                                >
                                    <span
                                        style={{
                                            whiteSpace: "nowrap",
                                            overflow: "hidden",
                                            textOverflow: "ellipsis",
                                            maxWidth: "66%",
                                        }}
                                    >
                                        {sh.type}
                                        {sh.name && sh.name !== sh.type
                                            ? ` · ${sh.name}`
                                            : ""}
                                    </span>
                                    <span
                                        style={{
                                            color: C.ink,
                                            fontWeight: 700,
                                        }}
                                    >
                                        {sh.pct}%
                                    </span>
                                </div>
                            ))}
                        <details className="an-dsc-help" style={{ marginTop: 12, fontSize: 12, fontWeight: 600, color: C.sub, background: C.card, borderRadius: 14 }}>
                            <summary className="an-dsc-help-summary">
                                <span className="an-dsc-help-title">지분 요약 · 보는 법</span>
                            </summary>
                            <div className="an-dsc-help-body">
                                <p style={{ margin: 0 }}>이 주주 목록은 받은 자료 중 최대 3개만 보여주는 요약이에요. 표시된 지분을 더해 전체 주주 구성이나 남은 지분을 계산하지 않아요. 총수일가 지배지분은 개별 주주 항목과 별도로 읽어요.</p>
                            </div>
                        </details>
                        {own.cross_check &&
                            own.cross_check.status &&
                            kv(
                                "DART↔공정위 교차",
                                own.cross_check.status === "match"
                                    ? "일치"
                                    : own.cross_check.status === "approx"
                                      ? "근사"
                                      : "차이",
                                own.cross_check.status === "match"
                                    ? C.vg
                                    : C.faint
                            )}
                        {own.sub_count
                            ? kv("계열사", own.sub_count + "곳")
                            : null}
                    </div>
                )}

                {foren &&
                    foren.counts &&
                    Object.keys(foren.counts).length > 0 && (
                        <div>
                            {sub("공시 이력 · DART (이벤트 누적 빈도)")}
                            {Object.entries(foren.counts)
                                .sort(
                                    (a: any, b: any) =>
                                        Number(b[1]) - Number(a[1])
                                )
                                .slice(0, 5)
                                .map(([k, v]: any) =>
                                    kv(
                                        k,
                                        v + "회",
                                        DILUTIVE.indexOf(k) >= 0 ? C.ink : C.sub
                                    )
                                )}
                            {(foren.events || [])
                                .slice(0, 2)
                                .map((e: any, i: number) => (
                                    <div
                                        key={i}
                                        style={{
                                            display: "flex",
                                            justifyContent: "space-between",
                                            fontSize: 11.5,
                                            padding: "4px 0",
                                            color: C.sub,
                                            fontWeight: 600,
                                        }}
                                    >
                                        <span
                                            style={{
                                                whiteSpace: "nowrap",
                                                overflow: "hidden",
                                                textOverflow: "ellipsis",
                                                maxWidth: "72%",
                                            }}
                                        >
                                            {mmdd(e.date)} {e.category}
                                        </span>
                                        {e.source_url && (
                                            <a
                                                href={e.source_url}
                                                target="_blank"
                                                rel="noreferrer"
                                                onClick={(ev) =>
                                                    ev.stopPropagation()
                                                }
                                                style={{
                                                    color: C.vt,
                                                    fontWeight: 700,
                                                    textDecoration: "none",
                                                    flexShrink: 0,
                                                }}
                                            >
                                                원문
                                            </a>
                                        )}
                                    </div>
                                ))}
                        </div>
                    )}

                {/* 애널리스트 컨센서스(목표주가·투자의견) 인라인 노출 제거 — 2026-07-10 컴플라이언스:
                    증권사 컨센서스 재배포(이중 IP: 네이버 ToS + 증권사 리서치 저작물) 소지.
                    PublicStockReport 의 출처 link-out 패턴과 정합 — 상세는 전체 리포트에서 출처 연결. */}

                <button
                    onClick={() => go(s.ticker)}
                    style={{
                        width: "100%",
                        marginTop: 16,
                        border: "none",
                        cursor: "pointer",
                        fontFamily: FONT,
                        padding: "11px 0",
                        borderRadius: 11,
                        fontSize: 13,
                        fontWeight: 800,
                        background: "#6c5ce7",
                        color: "#fff",
                    }}
                >
                    전체 리포트 보기 →
                </button>
                <div
                    style={{
                        fontSize: 10.5,
                        color: C.faint,
                        fontWeight: 600,
                        marginTop: 8,
                        lineHeight: 1.5,
                        textAlign: "center",
                    }}
                >
                    사실만 · 차트·심화는 전체 리포트
                </div>
            </div>
        )
    }

    return (
        <div ref={rootRef} style={wrap}>
            <style>{AN_PALETTE}</style>
            <style>{`
/* Compact disclosure surfaces — AlphaNest Design v1; keep native details and existing type weights. */
.an-dsc-help{min-width:0;padding:8px;box-sizing:border-box;--help-hover:#f1f3f5;--help-focus:#e9edf2;--help-sub:#6b7684}
body[data-framer-theme="dark"] .an-dsc-help{--help-hover:#252c35;--help-focus:#303945;--help-sub:#9aa4b1}
.an-dsc-help>summary{position:relative;list-style:none;cursor:pointer;display:flex;align-items:center;gap:8px;min-height:44px;box-sizing:border-box;padding:10px 40px 10px 12px!important;border:0;border-radius:12px;background:var(--an-dsc-card);color:var(--an-dsc-ink);font-weight:700;line-height:1.4;text-decoration:none!important;transition:background-color .16s ease}
.an-dsc-help>summary::marker{content:""}
.an-dsc-help>summary::-webkit-details-marker{display:none}
.an-dsc-help>summary::after{content:"";position:absolute;inset-inline-end:16px;top:50%;width:6px;height:6px;background:none;-webkit-mask:none;mask:none;border:solid currentColor;border-width:0 1.5px 1.5px 0;transform:translateY(-50%) rotate(-45deg);pointer-events:none}
.an-dsc-help[open]>summary::after{transform:translateY(-70%) rotate(45deg)}
@media(hover:hover){.an-dsc-help>summary:not(:focus-visible):hover{background:var(--help-hover);filter:none}}
.an-dsc-help>summary:focus-visible{background:var(--help-focus);outline:none!important;box-shadow:none!important}
.an-dsc-help-title{flex:1;min-width:0}
.an-dsc-help-body{padding:12px 12px 8px;line-height:1.65;color:var(--help-sub)}
.an-dsc-help-grid{display:grid;grid-template-columns:minmax(0,1fr);gap:8px;margin:0}
.an-dsc-help-grid>div{min-width:0}
.an-dsc-help dt{display:inline;font-weight:700;margin-right:8px}
.an-dsc-help dd{display:inline;margin:0;overflow-wrap:anywhere}
.an-dsc-help-note{margin:8px 0 0;overflow-wrap:anywhere}
.an-dsc-help-note>strong{margin-right:8px}
.an-dsc-performance-rows{display:grid;gap:8px;margin-top:12px}
.an-dsc-performance-row{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:4px 16px}
.an-dsc-performance-row>span{min-width:0;overflow-wrap:anywhere}
@media(prefers-reduced-motion:reduce){.an-dsc-help>summary{transition:none}}
@media(max-width:600px),(pointer:coarse){body{--an-dsc-control-height:44px;--an-dsc-segment-height:44px}}
`}</style>
            <style>{`@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
            <div
                style={{
                    display: "flex",
                    flexDirection: narrow ? "column" : "row",
                    gap: narrow ? 12 : 20,
                    alignItems: "flex-start",
                }}
            >
                {/* 탭 — 흰박스 없이 회색 배경에 직접, 활성만 흰 알약 */}
                {narrow ? (
                    <div
                        style={{
                            display: "flex",
                            gap: 7,
                            overflowX: "auto",
                            padding: `10px ${pad}px`,
                            width: `calc(100% + ${pad * 2}px)`,
                            boxSizing: "border-box",
                            marginLeft: -pad,
                            position: "sticky",
                            top: navTop,
                            background: C.glass,
                            backdropFilter: "saturate(1.4) blur(14px)",
                            WebkitBackdropFilter: "saturate(1.4) blur(14px)",
                            zIndex: 5,
                            scrollbarWidth: "none",
                            boxShadow: `0 8px 8px -7px ${C.shadowStrong}`,
                        }}
                    >
                        {loading
                            ? Array.from({ length: 4 }).map((_, i) => (
                                  <div
                                      key={i}
                                      style={skBlock(
                                          i === 0 ? 76 : 60,
                                          33,
                                          999
                                      )}
                                  />
                              ))
                            : visibleTabs.map((i) => tabButton(i))}
                    </div>
                ) : (
                    <div
                        style={{
                            flexShrink: 0,
                            width: 188,
                            position: "sticky",
                            top: navTop,
                            display: "flex",
                            flexDirection: "column",
                            gap: 2,
                        }}
                    >
                        {loading
                            ? Array.from({ length: 5 }).map((_, i) => (
                                  <div
                                      key={i}
                                      style={{
                                          ...skBlock("100%", 40, 10),
                                          marginBottom: 2,
                                      }}
                                  />
                              ))
                            : visibleTabs.map((i, position) => {
                                  const group = SCREENS[i].group
                                  const previousGroup =
                                      position > 0
                                          ? SCREENS[visibleTabs[position - 1]].group
                                          : null
                                  return (
                                      <div key={SCREENS[i].id} style={{ display: "contents" }}>
                                          {group !== "전체" &&
                                              (position === 0 || group !== previousGroup) && (
                                              <div
                                                  data-discovery-group={group}
                                                  style={{
                                                      padding:
                                                          position === 0
                                                              ? "2px 12px 5px"
                                                              : "12px 12px 5px",
                                                      color: C.faint,
                                                      fontSize: 11,
                                                      fontWeight: 700,
                                                      lineHeight: 1.4,
                                                  }}
                                              >
                                                  {group}
                                              </div>
                                          )}
                                          {tabButton(i)}
                                      </div>
                                  )
                              })}
                    </div>
                )}

                {/* 콘텐츠 */}
                <div
                    style={{
                        flex: 1,
                        minWidth: 0,
                        width: narrow ? "100%" : "auto",
                    }}
                >
                    {loading ? (
                        <div style={{ padding: "0 2px 10px" }}>
                            <div style={skBlock(168, 16, 7)} />
                            <div
                                style={{ ...skBlock(232, 11, 6), marginTop: 7 }}
                            />
                        </div>
                    ) : (
                        <div style={{ padding: "0 2px 10px" }}>
                            <h1
                                style={{ margin: 0,
                                    fontSize: 15.5,
                                    fontWeight: 700,
                                    color: C.ink,
                                    letterSpacing: "-0.3px",
                                }}
                            >
                                {sc.title}
                                {sector ? ` · ${sector}` : ""}
                            </h1>
                            <div
                                style={{
                                    fontSize: 11.5,
                                    color: C.faint,
                                    fontWeight: 600,
                                    marginTop: 3,
                                }}
                            >
                                {sc.rule} · {rangeError ? "입력 확인 필요" : pendingResult ? "자료 확인 중" : unavailableResult ? "결과 확인 불가" : `확인된 자료에서 ${sel.total}종목`}
                                {sel.total > sel.items.length
                                    ? ` (${sel.items.length}개 표시)`
                                    : ""}
                                {genAt ? ` · 국내 리포트 ${fmtAge(genAt)} 생성` : ""}
                            </div>
                            <details key={sc.id} className="an-dsc-help" style={{ marginTop: 12, fontSize: 12, fontWeight: 600, color: C.sub, background: C.card, borderRadius: 14 }}>
                                <summary className="an-dsc-help-summary">
                                    <span className="an-dsc-help-title">조건·자료 범위</span>
                                </summary>
                                <div className="an-dsc-help-body">
                                    <dl className="an-dsc-help-grid">
                                        <div><dt style={{ color: C.ink }}>조건의 의미</dt><dd>{sc.note}</dd></div>
                                        <div><dt style={{ color: C.ink }}>탐색 범위</dt><dd>현재 받은 리포트 <strong style={{ fontWeight: 800, color: C.ink }}>{list.length}종목</strong>{" · "}시장·업종·지표 필터 적용 전 기준이에요.</dd></div>
                                        {sc.peerKeys && <div><dt style={{ color: C.ink }}>업종 비교 기준</dt><dd>업종 중앙값은 비교 집단을 크기순으로 놓았을 때 가운데 값이에요. 표시값은 반올림될 수 있고, 종목별 원자료는 전체 리포트에서 확인할 수 있어요.</dd></div>}
                                    </dl>
                                    <p className="an-dsc-help-note"><strong style={{ fontWeight: 700, color: C.ink }}>자료를 읽을 때</strong>{" "}종목·자료별 기준 기간은 다를 수 있어요. 필요한 자료가 없으면 결과에서 빠질 수 있으며, 미표시가 반대 조건을 뜻하지 않아요.</p>
                                </div>
                            </details>
                            <div style={{ marginTop: 10, fontSize: 11.5, color: C.sub, fontWeight: 600, lineHeight: 1.6 }}><strong style={{ fontWeight: 700 }}>정렬 기준</strong> · {sortDescription}<span style={{ display: "block", marginTop: 2 }}>투자 추천 순위가 아니에요.</span></div>
                            <div style={{ marginTop: 10, fontSize: 11.5, color: C.sub, fontWeight: 600, lineHeight: 1.6 }}>
                                <label style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 700, flexWrap: "wrap" }}>
                                    조건별 과거 수익률
                                    <select aria-label="수익률 비교 기간" value={performancePeriod} onChange={event => setPerformancePeriod(Number(event.target.value))} style={selStyle}>
                                        {[1, 3, 6].map(months => <option key={months} value={months}>최근 {months}개월</option>)}
                                    </select>
                                </label>
                                <div role="status">{performance.loading && performanceUrl ? "수익률 자료 확인 중이에요." : performanceView.message}</div>
                                {!!performanceUrl && !performance.loading && performance.failed > 0 && <button onClick={() => setRetry(n => n + 1)} style={{ ...selStyle, marginTop: 4, backgroundImage: "none", color: C.vt }}>수익률 자료 다시 확인</button>}
                                {performanceView.window && <details className="an-dsc-help" style={{ marginTop: 10, background: C.card, borderRadius: 14 }}>
                                    <summary style={{ color: C.ink }}>계산 기준·자료 범위</summary>
                                    <div className="an-dsc-help-body">
                                        <p style={{ margin: 0 }}>시작 당시 종목을 같은 비중으로 유지한 가상 수익률이에요. 분할·배당 조정 가격, 시장별 통화 기준이며 비용·세금·환율 효과는 제외해요.</p>
                                        <div className="an-dsc-performance-rows">
                                            <div className="an-dsc-performance-row" style={{ fontWeight: 700, color: C.ink }}><span>전체 비교군 {performanceView.window.benchmark.priced}/{performanceView.window.benchmark.total}종목</span><span>수익률 {performanceView.window.benchmark.return_pct.toFixed(2)}%</span></div>
                                            {performanceView.window.categories.map((row: any) => <div className="an-dsc-performance-row" key={row.id}><span>{SCREENS.find(s => s.id === row.id)?.tab} · 가격 확인 {row.priced}/{row.total}종목</span><span style={{ fontWeight: 700 }}>{row.return_pct === null ? "구성 종목 없음" : `${row.return_pct.toFixed(2)}%`}</span></div>)}
                                        </div>
                                        <p className="an-dsc-help-note">관측 가설 · T={Math.round((Date.parse(performanceView.window.end) - Date.parse(performanceView.window.start)) / 86400000)}일 · 독립 관측 N=미산정. 과거 성과이며 예측력 검증 결과가 아니에요. 조건 간 종목은 중복될 수 있어요.</p>
                                    </div>
                                </details>}
                            </div>
                            {sc.id === "foreign_buy" && sel.flowCoverage && (
                                <div style={{ marginTop: 10, padding: 12, borderRadius: 12, background: C.card, color: C.sub, fontSize: 11.5, fontWeight: 600, lineHeight: 1.65 }}>
                                    <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontWeight: 700, color: C.ink }}>
                                        <input type="checkbox" checked={onlyFlowEntries} onChange={event => setOnlyFlowEntries(event.target.checked)} style={{ accentColor: C.vt, flexShrink: 0 }} />
                                        최신 수신일 순매수 전환만 보기
                                    </label>
                                    <div>수신 최신 거래일 {flowHistory.asOf || "미제공"} · 순매수 {sel.flowCoverage.total}종목 중 비교 가능 {sel.flowCoverage.comparable}종목 · 전환 {sel.flowCoverage.entered}종목</div>
                                    <div>과거 수신 {sel.flowCoverage.older}종목 · 비교 불가 {sel.flowCoverage.unknown}종목 · 현재 시장·업종·지표 필터 기준, 표시 개수 제한 전</div>
                                    <div>같은 종목의 이전 관측값이 0 이하이고 마지막 값이 양수일 때만 전환으로 표시해요. 오늘·연속 거래일·매수 추천을 뜻하지 않아요.</div>
                                </div>
                            )}
                        </div>
                    )}

                    {sourceIssues.some(([, source]) => !source.loading && (source.failed > 0 || !source.requested)) && (
                        <div role="status" style={{ fontSize: 12, fontWeight: 600, color: C.sub, background: C.card, borderRadius: 12, padding: 12, marginBottom: 10, lineHeight: 1.6 }}>
                            {sourceIssues.filter(([, source]) => !source.loading && (source.failed > 0 || !source.requested)).map(([label, source]) =>
                                <div key={label}>{label}: {source.requested ? `${source.requested}개 소스 중 ${source.requested - source.failed}개 확인 · 일부 자료를 불러오지 못했어요.` : "연결된 소스가 없어요."}</div>
                            )}
                            <div>미수신 자료는 조건 미충족으로 판단하지 않아요.</div>
                            <button onClick={() => setRetry(n => n + 1)} style={{ ...selStyle, marginTop: 6, backgroundImage: "none", color: C.vt }}>자료 다시 불러오기</button>
                        </div>
                    )}
                    {/* 도구막대 */}
                    {loading ? (
                        <div
                            style={{
                                display: "flex",
                                gap: 7,
                                flexWrap: "wrap",
                                alignItems: "center",
                                marginBottom: 10,
                            }}
                        >
                            {!narrow && <div style={skBlock(92, 34, 10)} />}
                            <div style={skBlock(104, 34, 9)} />
                            <div style={skBlock(104, 34, 9)} />
                        </div>
                    ) : (
                        <div
                            style={{
                                display: "flex",
                                gap: 7,
                                flexWrap: "wrap",
                                alignItems: "center",
                                marginBottom: 10,
                            }}
                        >
                            {!narrow && (
                                <div
                                    style={{
                                        display: "flex",
                                        gap: 3,
                                        background: C.card,
                                        borderRadius: 10,
                                        padding: 3,
                                        boxShadow: "0 1px 2px rgba(0,0,0,0.04)",
                                    }}
                                >
                                    {[
                                        ["table", "표"],
                                        ["list", "리스트"],
                                    ].map(([v, lb]) => (
                                        <button
                                            key={v}
                                            onClick={() => setView(v)}
                                            style={{
                                                border: "none",
                                                cursor: "pointer",
                                                fontFamily: FONT,
                                                padding: "6px 12px",
                                                minHeight: "var(--an-dsc-segment-height, 32px)",
                                                lineHeight: 1.25,
                                                boxSizing: "border-box",
                                                borderRadius: 8,
                                                fontSize: 12,
                                                fontWeight: 700,
                                                background:
                                                    view === v
                                                        ? C.bg
                                                        : "transparent",
                                                color:
                                                    view === v ? C.ink : C.sub,
                                            }}
                                        >
                                            {lb}
                                        </button>
                                    ))}
                                </div>
                            )}
                            <div
                                style={{
                                    display: "flex",
                                    gap: 2,
                                    background: C.line,
                                    borderRadius: 9,
                                    padding: 2,
                                    flexShrink: 0,
                                }}
                            >
                                {(
                                    [
                                        ["all", "전체"],
                                        ["kr", "국장"],
                                        ["us", "미장"],
                                    ] as [string, string][]
                                ).map(([m, lbl]) => (
                                    <button
                                        key={m}
                                        onClick={() => setMkt(m)}
                                        style={{
                                            border: "none",
                                            cursor: "pointer",
                                            padding: "6px 10px",
                                            minHeight: "var(--an-dsc-segment-height, 32px)",
                                            lineHeight: 1.25,
                                            boxSizing: "border-box",
                                            borderRadius: 7,
                                            fontSize: 12,
                                            fontWeight: 800,
                                            fontFamily: "inherit",
                                            whiteSpace: "nowrap",
                                            background:
                                                mkt === m
                                                    ? C.card
                                                    : "transparent",
                                            color: mkt === m ? C.vt : C.sub,
                                        }}
                                    >
                                        {lbl}
                                    </button>
                                ))}
                            </div>
                            <select
                                aria-label="업종 필터"
                                value={sector}
                                onChange={(e) => setSector(e.target.value)}
                                style={{
                                    ...selStyle,
                                    maxWidth: 150,
                                    textOverflow: "ellipsis",
                                }}
                            >
                                <option value="">섹터 전체</option>
                                {sectors.map((sec) => (
                                    <option key={sec} value={sec}>
                                        {sec}
                                    </option>
                                ))}
                            </select>
                            <select
                                aria-label="지표 범위"
                                value={rMetric}
                                onChange={(e) => setRMetric(e.target.value)}
                                style={selStyle}
                            >
                                <option value="">지표 범위…</option>
                                {RANGE_METRICS.map((m) => (
                                    <option key={m} value={m}>
                                        {m}
                                    </option>
                                ))}
                            </select>
                            {rMetric && (
                                <>
                                    <input
                                        aria-label="지표 최솟값"
                                        aria-invalid={!!rangeError}
                                        value={rMin}
                                        onChange={(e) =>
                                            setRMin(e.target.value)
                                        }
                                        placeholder="최소"
                                        inputMode="decimal"
                                        style={numStyle}
                                    />
                                    <span
                                        style={{
                                            fontSize: 12,
                                            color: C.faint,
                                            fontWeight: 700,
                                        }}
                                    >
                                        ~
                                    </span>
                                    <input
                                        aria-label="지표 최댓값"
                                        aria-invalid={!!rangeError}
                                        value={rMax}
                                        onChange={(e) =>
                                            setRMax(e.target.value)
                                        }
                                        placeholder="최대"
                                        inputMode="decimal"
                                        style={numStyle}
                                    />
                                </>
                            )}
                            {(sector || rMetric || mkt !== "all" || (sc.id === "foreign_buy" && onlyFlowEntries)) && (
                                <button
                                    onClick={resetFilters}
                                    style={{
                                        border: "none",
                                        cursor: "pointer",
                                        fontFamily: FONT,
                                        padding: "7px 11px",
                                        minHeight: "var(--an-dsc-control-height, 36px)",
                                        lineHeight: 1.25,
                                        boxSizing: "border-box",
                                        borderRadius: 9,
                                        fontSize: 12,
                                        fontWeight: 700,
                                        background: C.bg,
                                        color: C.sub,
                                    }}
                                >
                                    초기화
                                </button>
                            )}
                        </div>
                    )}

                    {/* 표/리스트 + (넓은 화면) 우측 상세 패널 */}
                    <div
                        style={{
                            display: "flex",
                            gap: 16,
                            alignItems: "flex-start",
                        }}
                    >
                        <div style={{ flex: 1, minWidth: 0 }}>
                            {pendingResult ? (
                                <div
                                    style={{
                                        background: C.card,
                                        borderRadius: 16,
                                        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                                        overflow: "hidden",
                                    }}
                                >
                                    {Array.from({ length: 9 }).map((_, i) => (
                                        <div
                                            key={i}
                                            style={{
                                                display: "flex",
                                                alignItems: "center",
                                                gap: 14,
                                                padding: "12px 16px",
                                                borderTop:
                                                    i === 0
                                                        ? "none"
                                                        : `1px solid ${C.line}`,
                                            }}
                                        >
                                            <div style={skBlock(20, 20, 6)} />
                                            <div
                                                style={{ flex: 1, minWidth: 0 }}
                                            >
                                                <div
                                                    style={skBlock(
                                                        i % 3 === 0
                                                            ? "52%"
                                                            : "38%",
                                                        13
                                                    )}
                                                />
                                            </div>
                                            {!narrow && (
                                                <div style={skBlock(64, 13)} />
                                            )}
                                            {!narrow && (
                                                <div style={skBlock(54, 13)} />
                                            )}
                                            <div style={skBlock(46, 13)} />
                                        </div>
                                    ))}
                                </div>
                            ) : !sel.items.length ? (
                                <div role="status" style={{ background: C.card, borderRadius: 16, padding: 24, color: C.sub, fontSize: 13, fontWeight: 600, lineHeight: 1.7 }}>
                                    {rangeError || (unavailableResult ? "자료를 확인하지 못해 이 조건의 결과를 보여드릴 수 없어요. 위의 다시 불러오기를 이용해주세요." : !list.length ? "현재 수신된 종목 자료가 비어 있어요." : "현재 확인된 자료에서 선택한 조건에 맞는 종목이 없어요. 조건을 바꾸거나 필터를 초기화해 주세요.")}
                                </div>
                            ) : useTable ? (
                                <div
                                    style={{
                                        background: C.card,
                                        borderRadius: 16,
                                        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                                        overflowX: "auto",
                                    }}
                                >
                                    <div style={{ minWidth: TABLE_MIN }}>
                                        <div
                                            style={{
                                                display: "flex",
                                                alignItems: "center",
                                                gap: 14,
                                                padding: "0px 16px",
                                                borderBottom: `1px solid ${C.line}`,
                                                position: "sticky",
                                                top: 0,
                                                background: C.card,
                                                zIndex: 2,
                                            }}
                                        >
                                            {COLS.map((col) => {
                                                const activeSort =
                                                    sortKey === col.key
                                                const label =
                                                    col.label +
                                                    (activeSort
                                                        ? sortDir < 0
                                                            ? " ↓"
                                                            : " ↑"
                                                        : "")
                                                if (!col.sort) {
                                                    return (
                                                        <div
                                                            key={col.key}
                                                            style={colStyle(
                                                                col,
                                                                {
                                                                    fontSize: 11.5,
                                                                    fontWeight: 700,
                                                                    color: C.faint,
                                                                }
                                                            )}
                                                        >
                                                            {col.label}
                                                        </div>
                                                    )
                                                }
                                                return (
                                                    <button
                                                        key={col.key}
                                                        onClick={() =>
                                                            onSort(col.key)
                                                        }
                                                        style={{
                                                            border: "none",
                                                            cursor: "pointer",
                                                            fontFamily: FONT,
                                                            background:
                                                                "transparent",
                                                            padding: "6px 0",
                                                            minHeight: "var(--an-dsc-control-height, 36px)",
                                                            lineHeight: 1.25,
                                                            boxSizing: "border-box",
                                                            fontSize: 11.5,
                                                            fontWeight: 700,
                                                            color: activeSort
                                                                ? C.vg
                                                                : C.faint,
                                                            ...colStyle(col),
                                                        }}
                                                    >
                                                        {label}
                                                    </button>
                                                )
                                            })}
                                        </div>
                                        {sel.items.map((s, idx) => {
                                            const isSel =
                                                wide && s.ticker === selected
                                            return (
                                                <div
                                                    key={s.ticker}
                                                    role="button"
                                                    tabIndex={0}
                                                    onClick={() =>
                                                        onRow(s.ticker)
                                                    }
                                                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRow(s.ticker) } }}
                                                    style={{
                                                        display: "flex",
                                                        alignItems: "center",
                                                        gap: 14,
                                                        padding: "10px 16px",
                                                        borderTop:
                                                            idx === 0
                                                                ? "none"
                                                                : `1px solid ${C.line}`,
                                                        cursor: "pointer",
                                                        fontVariantNumeric:
                                                            "tabular-nums",
                                                        background: isSel
                                                            ? C.bg
                                                            : "transparent",
                                                    }}
                                                >
                                                    {COLS.map((col) => {
                                                        if (
                                                            col.key === "rank"
                                                        ) {
                                                            return (
                                                                <div
                                                                    key="rank"
                                                                    style={colStyle(
                                                                        col,
                                                                        {
                                                                            fontSize: 12,
                                                                            fontWeight: 700,
                                                                            color: C.faint,
                                                                        }
                                                                    )}
                                                                >
                                                                    {idx + 1}
                                                                </div>
                                                            )
                                                        }
                                                        if (
                                                            col.key === "name"
                                                        ) {
                                                            return (
                                                                <div
                                                                    key="name"
                                                                    style={{
                                                                        flex: 1,
                                                                        minWidth: 148,
                                                                        display:
                                                                            "flex",
                                                                        alignItems:
                                                                            "center",
                                                                        gap: 10,
                                                                    }}
                                                                >
                                                                    <Logo
                                                                        ticker={
                                                                            s.ticker
                                                                        }
                                                                        name={
                                                                            s.name
                                                                        }
                                                                        market={
                                                                            s.market
                                                                        }
                                                                        C={C}
                                                                        size={
                                                                            30
                                                                        }
                                                                    />
                                                                    <div
                                                                        style={{
                                                                            minWidth: 0,
                                                                        }}
                                                                    >
                                                                        <div
                                                                            style={{
                                                                                fontSize: 13.5,
                                                                                fontWeight: 700,
                                                                                color: C.ink,
                                                                                whiteSpace:
                                                                                    "nowrap",
                                                                                overflow:
                                                                                    "hidden",
                                                                                textOverflow:
                                                                                    "ellipsis",
                                                                            }}
                                                                        >
                                                                            {
                                                                                s.name
                                                                            }
                                                                        </div>
                                                                        <div
                                                                            style={{
                                                                                fontSize: 10.5,
                                                                                color: C.faint,
                                                                                fontWeight: 600,
                                                                            }}
                                                                        >
                                                                            {
                                                                                s.ticker
                                                                            }{" "}
                                                                            ·{" "}
                                                                            {
                                                                                s.market
                                                                            }
                                                                        </div>
                                                                        {sc.id === "foreign_buy" && <div style={{ marginTop: 3, fontSize: 10.5, fontWeight: 600, color: C.sub, lineHeight: 1.5, overflowWrap: "anywhere" }}>
                                                                            {flowHistory.byTicker[s.ticker]?.text || "비교 불가 · 수급 자료 미제공"}
                                                                        </div>}
                                                                    </div>
                                                                </div>
                                                            )
                                                        }
                                                        if (
                                                            col.key ===
                                                            "insider"
                                                        ) {
                                                            const nv =
                                                                insiderNet(s)
                                                            return (
                                                                <div
                                                                    key="insider"
                                                                    style={colStyle(
                                                                        col,
                                                                        {
                                                                            fontSize: 12.5,
                                                                            fontWeight:
                                                                                sortKey ===
                                                                                "insider"
                                                                                    ? 800
                                                                                    : 700,
                                                                            color:
                                                                                nv ==
                                                                                null
                                                                                    ? C.faint
                                                                                    : nv >
                                                                                        0
                                                                                      ? C.up
                                                                                      : nv <
                                                                                          0
                                                                                        ? C.down
                                                                                        : C.faint,
                                                                        }
                                                                    )}
                                                                >
                                                                    {nv == null
                                                                        ? "—"
                                                                        : fmtShares(
                                                                              nv
                                                                          )}
                                                                </div>
                                                            )
                                                        }
                                                        const v = cellText(
                                                            s,
                                                            col.key
                                                        )
                                                        const isSorted =
                                                            sortKey === col.key
                                                        return (
                                                            <div
                                                                key={col.key}
                                                                style={colStyle(
                                                                    col,
                                                                    {
                                                                        fontSize: 12.5,
                                                                        fontWeight:
                                                                            isSorted
                                                                                ? 800
                                                                                : 600,
                                                                        color:
                                                                            v ===
                                                                            "—"
                                                                                ? C.faint
                                                                                : col.key ===
                                                                                    "sector"
                                                                                  ? C.sub
                                                                                  : C.ink,
                                                                    }
                                                                )}
                                                            >
                                                                {v}
                                                            </div>
                                                        )
                                                    })}
                                                </div>
                                            )
                                        })}
                                        {sel.total > sel.items.length && (
                                            <div
                                                style={{
                                                    textAlign: "center",
                                                    padding: "12px 0",
                                                    fontSize: 12,
                                                    color: C.faint,
                                                    fontWeight: 600,
                                                    borderTop: `1px solid ${C.line}`,
                                                }}
                                            >
                                                결과 {sel.total}종목 중{" "}
                                                {sel.items.length} 표시 ·
                                                필터·정렬로 좁히기
                                            </div>
                                        )}
                                    </div>
                                </div>
                            ) : (
                                <div
                                    style={{
                                        background: C.card,
                                        borderRadius: 16,
                                        padding: "4px 6px",
                                        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                                    }}
                                >
                                    {sel.items.map((s, idx) => {
                                        const ec = edgeChips(s)
                                        const isSel =
                                            wide && s.ticker === selected
                                        return (
                                            <div
                                                key={s.ticker}
                                                role="button"
                                                tabIndex={0}
                                                onClick={() => onRow(s.ticker)}
                                                onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRow(s.ticker) } }}
                                                style={{
                                                    display: "flex",
                                                    alignItems: "center",
                                                    gap: 12,
                                                    padding: "11px 10px",
                                                    borderTop:
                                                        idx === 0
                                                            ? "none"
                                                            : `1px solid ${C.line}`,
                                                    cursor: "pointer",
                                                    borderRadius: 10,
                                                    background: isSel
                                                        ? C.bg
                                                        : "transparent",
                                                }}
                                            >
                                                <Logo
                                                    ticker={s.ticker}
                                                    name={s.name}
                                                    market={s.market}
                                                    C={C}
                                                />
                                                <div
                                                    style={{
                                                        flex: 1,
                                                        minWidth: 0,
                                                    }}
                                                >
                                                    <div
                                                        style={{
                                                            display: "flex",
                                                            alignItems:
                                                                "baseline",
                                                            gap: 7,
                                                        }}
                                                    >
                                                        <span
                                                            style={{
                                                                fontSize: 14.5,
                                                                fontWeight: 700,
                                                                color: C.ink,
                                                                whiteSpace:
                                                                    "nowrap",
                                                                overflow:
                                                                    "hidden",
                                                                textOverflow:
                                                                    "ellipsis",
                                                                maxWidth: "62%",
                                                            }}
                                                        >
                                                            {s.name}
                                                        </span>
                                                        <span
                                                            style={{
                                                                flexShrink: 0,
                                                                fontSize: 11,
                                                                color: C.faint,
                                                                fontWeight: 600,
                                                            }}
                                                        >
                                                            {s.ticker} ·{" "}
                                                            {s.market}
                                                        </span>
                                                    </div>
                                                    {s.business && (
                                                        <div
                                                            style={{
                                                                fontSize: 11.5,
                                                                color: C.sub,
                                                                fontWeight: 600,
                                                                marginTop: 1,
                                                                whiteSpace:
                                                                    "nowrap",
                                                                overflow:
                                                                    "hidden",
                                                                textOverflow:
                                                                    "ellipsis",
                                                            }}
                                                        >
                                                            {s.business}
                                                        </div>
                                                    )}
                                                    <div
                                                        style={{
                                                            display: "flex",
                                                            gap: 5,
                                                            flexWrap: "wrap",
                                                            marginTop: 6,
                                                        }}
                                                    >
                                                        {sc.id !== "all" && <div style={{ width: "100%", fontSize: 11.5, fontWeight: 600, color: C.sub, lineHeight: 1.5, overflowWrap: "anywhere" }}>
                                                            표시 이유: {discoveryReason(sc, s, ctx)}
                                                        </div>}
                                                        {sc.id === "foreign_buy" && <div style={{ width: "100%", fontSize: 11.5, fontWeight: 600, color: C.sub, lineHeight: 1.5, overflowWrap: "anywhere" }}>
                                                            {flowHistory.byTicker[s.ticker]?.text || "비교 불가 · 수급 자료 미제공"}
                                                        </div>}
                                                        {sc.chips.map((k) =>
                                                            chipFor(s, k)
                                                        )}
                                                        {ec}
                                                    </div>
                                                </div>
                                                <span
                                                    style={{
                                                        flexShrink: 0,
                                                        fontSize: 16,
                                                        color: C.faint,
                                                        fontWeight: 600,
                                                    }}
                                                >
                                                    ›
                                                </span>
                                            </div>
                                        )
                                    })}
                                    {sel.total > sel.items.length && (
                                        <div
                                            style={{
                                                textAlign: "center",
                                                padding: "12px 0 8px",
                                                fontSize: 12,
                                                color: C.faint,
                                                fontWeight: 600,
                                                borderTop: `1px solid ${C.line}`,
                                            }}
                                        >
                                            결과 {sel.total}종목 중{" "}
                                            {sel.items.length} 표시 · 필터로
                                            좁히기
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                        {wide && loading && (
                            <div
                                style={{
                                    flexShrink: 0,
                                    width: 340,
                                    background: C.card,
                                    borderRadius: 16,
                                    padding: 16,
                                    boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
                                    boxSizing: "border-box",
                                }}
                            >
                                <div
                                    style={{
                                        display: "flex",
                                        alignItems: "center",
                                        gap: 11,
                                    }}
                                >
                                    <div style={skBlock(40, 40, 12)} />
                                    <div style={{ flex: 1 }}>
                                        <div style={skBlock("70%", 15, 7)} />
                                        <div
                                            style={{
                                                ...skBlock("44%", 11, 6),
                                                marginTop: 6,
                                            }}
                                        />
                                    </div>
                                </div>
                                <div
                                    style={{
                                        ...skBlock("52%", 21, 8),
                                        marginTop: 12,
                                    }}
                                />
                                {Array.from({ length: 6 }).map((_, i) => (
                                    <div
                                        key={i}
                                        style={{
                                            display: "flex",
                                            justifyContent: "space-between",
                                            padding: "7px 0",
                                        }}
                                    >
                                        <div style={skBlock(72, 12, 6)} />
                                        <div style={skBlock(52, 12, 6)} />
                                    </div>
                                ))}
                            </div>
                        )}
                        {wide && selected && detailPanel()}
                    </div>
                </div>
            </div>

            <div
                style={{
                    textAlign: "center",
                    fontSize: 11.5,
                    color: C.sub,
                    fontWeight: 600,
                    marginTop: 20,
                    lineHeight: 1.55,
                }}
            >
                직접 조건검색으로 짜기 어려운 사실 기반 스크린 — 내부자·외국인
                수급·지배구조·공시이력
            </div>
            <div
                style={{
                    textAlign: "center",
                    fontSize: 11,
                    color: C.faint,
                    fontWeight: 600,
                    marginTop: 6,
                    lineHeight: 1.5,
                }}
            >
                시총·PER·PBR·ROE = KRX·DART·SEC · 내부자=DART(국장)·SEC
                Form4(미장) · 외국인 수급=네이버 · 지배구조=공정위 ·
                공시이력=DART · 사실 정렬·필터일 뿐
            </div>
        </div>
    )
}

addPropertyControls(PublicDiscovery, {
    stockUrl: {
        type: ControlType.String,
        title: "Stock URL",
        defaultValue: DEFAULT_URL,
    },
    usStockUrl: {
        type: ControlType.String,
        title: "US Stock URL",
        defaultValue:
            "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_stock_report_public.json",
    },
    usSmallcapUrl: {
        type: ControlType.String,
        title: "US Smallcap URL",
        defaultValue:
            "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_stock_report_us_smallcap.json",
    },
    insiderUrl: {
        type: ControlType.String,
        title: "Insider URL",
        defaultValue: DEFAULT_INSIDER,
    },
    usInsiderUrl: {
        type: ControlType.String,
        title: "US Insider URL",
        defaultValue: DEFAULT_US_INSIDER,
    },
    flowUrl: {
        type: ControlType.String,
        title: "Flow URL",
        defaultValue: DEFAULT_FLOW,
    },
    forensicsUrl: {
        type: ControlType.String,
        title: "Forensics URL",
        defaultValue: DEFAULT_FORENSICS,
    },
    performanceUrl: {
        type: ControlType.String,
        title: "수익률 검증 자료",
        defaultValue: "",
        description: "검증·공개 권한 확인을 마친 discovery-performance-v1 집계 URL만 연결합니다. 비어 있으면 순위가 표시되지 않습니다.",
    },
    apiBase: {
        type: ControlType.String,
        title: "API Base",
        defaultValue: DEFAULT_API,
    },
    reportPath: {
        type: ControlType.String,
        title: "Report Path",
        defaultValue: DEFAULT_REPORT,
    },
    perList: {
        type: ControlType.Number,
        title: "Rows",
        defaultValue: 40,
        min: 10,
        max: 120,
        step: 10,
    },
    topOffset: {
        type: ControlType.Number,
        title: "Top Offset (navbar)",
        defaultValue: 60,
        min: 0,
        max: 200,
        step: 4,
    },
    dark: {
        type: ControlType.Boolean,
        title: "Dark",
        defaultValue: false,
        enabledTitle: "On",
        disabledTitle: "Off",
    },
})
