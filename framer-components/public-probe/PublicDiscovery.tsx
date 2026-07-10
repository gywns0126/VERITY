import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 종목 발견(Discovery) — VERITY 공개 터미널 (AlphaNest). 토스 "주식 골라보기"식 좌측 탭 + 정렬표/리스트 + 로고·국기.
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
 * 🚨 sticky: 탭/패널 = wrap(자연흐름) → 뷰포트 기준 top=navTop(네브바 회피). 표헤더 = overflowX:auto 표카드가 스크롤 컨테이너라 top=0.
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
    apiBase: string
    reportPath: string
    dark: boolean
    perList: number
    topOffset: number
}
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_report_public.json"
const DEFAULT_INSIDER = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/insider_trades.json"
const DEFAULT_US_INSIDER = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_insider_trades.json"
const DEFAULT_FLOW = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_flow_5d.json"
const DEFAULT_FORENSICS = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/disclosure_forensics.json"
const DEFAULT_API = "https://project-yw131.vercel.app"
const DEFAULT_REPORT = "/stock"
// 데이터 신선도 — ISO → 상대시각(다른 public 컴포넌트와 동일 패턴).
function fmtAge(iso: any): string {
    if (!iso) return ""
    try {
        const mins = Math.max(0, Math.round((Date.now() - new Date(String(iso)).getTime()) / 60000))
        if (mins < 60) return mins + "분 전"
        const hrs = Math.round(mins / 60)
        if (hrs < 24) return hrs + "시간 전"
        return Math.round(hrs / 24) + "일 전"
    } catch {
        return ""
    }
}

// ── Brandfetch 로고 (토스 핫링킹 제거 2026-07-10) — logo_map(빌드타임 확정) + US 티커 규칙 + 이니셜 폴백 ──
const BF_CID = "1idalDez9T7KlggM8qX"  // 공개 임베드 client id (Logo Link 전용)
const BF_MAP_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/logo_map.json"
let __bfMap: Record<string, string> | null = null
let __bfColors: Record<string, string> = {}
let __bfP: Promise<Record<string, string>> | null = null
function fetchBfMap(): Promise<Record<string, string>> {
    if (__bfMap) return Promise.resolve(__bfMap)
    if (!__bfP) __bfP = fetch(BF_MAP_URL).then((r) => (r.ok ? r.json() : null)).then((d) => { __bfMap = (d && d.logos) || {}; __bfColors = (d && d.colors) || {}; return __bfMap as Record<string, string> }).catch(() => ({} as Record<string, string>))
    return __bfP
}
function useBfLogoMap(): Record<string, string> | null {
    const [m, setM] = useState<Record<string, string> | null>(__bfMap)
    useEffect(() => { let al = true; fetchBfMap().then((mm) => { if (al) setM(mm) }); return () => { al = false } }, [])
    return m
}
function bfLogoBg(ticker: any): string {
    // 아이덴티티 색 틴트 타일 (토스식 참조 — 색은 로고 대표색/공식 브랜드색, 자산 복사 아님)
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    const c = __bfColors[tk] || __bfColors[tk.replace(/\./g, "-")]
    return c ? c + "26" : "#ffffff"  // 15% 알파 틴트, 무채색/미보유 = 흰 타일
}
function bfLogoSrc(ticker: any, lm: Record<string, string> | null, size: number): string {
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    const p = (lm && (lm[tk] || lm[tk.replace(/\./g, "-")])) || ""  // 맵 전용 — 미검증 경로 = B 플레이스홀더 위험(2026-07-10)
    return p ? "https://cdn.brandfetch.io/" + p + "?c=" + BF_CID + "&w=" + size * 2 + "&h=" + size * 2 : ""
}
const FLAG_BASE = "https://hatscripts.github.io/circle-flags/flags/"

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", up: "#f04452", down: "#3182f6", vg: "#0ca678", vgS: "#e7faf0", vt: "#6c5ce7", vtS: "#f0edff", glass: "rgba(242,244,246,0.7)",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", up: "#f04452", down: "#5b9bff", vg: "#34e08a", vgS: "#0f241c", vt: "#a99bff", vtS: "#241f3a", glass: "rgba(15,19,24,0.7)",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const KR_MK = ["KOSPI", "KOSDAQ", "KONEX"]
const PANEL_FACTS = ["시가총액", "PER", "PBR", "ROE", "부채비율", "D/E", "영업이익률", "순이익률", "Altman-Z"]   // 부채비율=국장 / D/E=미장(키 상이, null 아닌 쪽만 노출). 배당수익률·EPS=양쪽 0% 소스부재라 제거
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
    if (a >= 1e4) return sign + Math.round(a / 1e4).toLocaleString("en-US") + "만주"
    return sign + Math.round(a).toLocaleString("en-US") + "주"
}
function mmdd(s: any): string {
    const x = String(s || "").replace(/-/g, "")
    if (/^\d{8}$/.test(x)) return x.slice(4, 6) + "." + x.slice(6, 8)
    if (/^\d{4}-\d{2}-\d{2}/.test(String(s || ""))) return String(s).slice(5, 10).replace("-", ".")
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
    return (s.peer && s.peer.sector) || (s.overview && s.overview.sector) ||
        (!/^\d{6}$/.test(String(s.ticker || "")) ? (s.business || "") : "") || ""
}
function flagCode(market: any): string {
    const m = String(market || "").toUpperCase()
    if (KR_MK.indexOf(m) >= 0 || m.indexOf("KOS") >= 0 || m.indexOf("KONEX") >= 0) return "kr"
    if (m.indexOf("NAS") >= 0 || m.indexOf("NYSE") >= 0 || m.indexOf("AMEX") >= 0 || m.indexOf("US") >= 0) return "us"
    return "kr"
}

function Logo(props: { ticker: string; name: string; market: string; C: any; size?: number }) {
    const { ticker, name, market, C } = props
    const size = props.size || 32
    const [err, setErr] = useState(false)
    const lm = useBfLogoMap()
    const bfSrc = bfLogoSrc(ticker, lm, size)
    const ch = (String(name || "?").trim().charAt(0)) || "?"
    const code = flagCode(market)
    const fsize = Math.round(size * 0.46)
    return (
        <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
            {!err && bfSrc ? (
                <img src={bfSrc} alt="" width={size} height={size}
                    onError={() => setErr(true)}
                    style={{ width: size, height: size, borderRadius: 10, objectFit: "contain", padding: "13%", boxSizing: "border-box", display: "block", background: bfLogoBg(ticker)}} />
            ) : (
                <div style={{ width: size, height: size, borderRadius: 10, background: C.vtS, color: C.vt, display: "flex", alignItems: "center", justifyContent: "center", fontSize: Math.round(size * 0.42), fontWeight: 800 }}>{ch}</div>
            )}
            {code && (
                <img src={FLAG_BASE + code + ".svg"} alt="" width={fsize} height={fsize}
                    style={{ position: "absolute", right: -3, bottom: -3, width: fsize, height: fsize, borderRadius: "50%", border: `1.5px solid ${C.card}`, background: C.card, display: "block", boxShadow: "0 1px 2px rgba(0,0,0,0.18)" }} />
            )}
        </div>
    )
}

interface Ctx { insiderMap: Record<string, any>; flowMap: Record<string, any[]>; forensicsMap: Record<string, any> }
interface Screen {
    id: string
    tab: string
    title: string
    rule: string
    edge?: boolean
    pred: (s: any, ctx: Ctx) => boolean
    chips: string[]
    sortBy: (s: any, ctx: Ctx) => number
}
const SCREENS: Screen[] = [
    {
        id: "all", tab: "전체", title: "전체 종목", rule: "전 종목 — 정렬·필터로 탐색",
        pred: () => true, chips: ["PBR", "PER", "ROE"],
        sortBy: (s) => -(parseCap((s.facts || {})["시가총액"]) ?? -1),
    },
    {
        id: "insider_buy", tab: "내부자 순매수", edge: true,
        title: "내부자(임원·주요주주)가 순매수한 회사",
        rule: "DART 내부자 순증감 > 0",
        pred: (s, ctx) => { const e = ctx.insiderMap[s.ticker]; return !!(e && Number(e.net_change) > 0) },
        chips: ["PBR", "ROE"],
        sortBy: (s, ctx) => -Number((ctx.insiderMap[s.ticker] || {}).net_change || 0),
    },
    {
        id: "insider_dom", tab: "내부자 매수우세", edge: true,
        title: "내부자 매수 건수가 매도보다 많은 회사",
        rule: "DART 내부자 매수 건수 > 매도 건수",
        pred: (s, ctx) => { const e = ctx.insiderMap[s.ticker]; return !!(e && Number(e.buy_n) > Number(e.sell_n)) },
        chips: ["PBR", "ROE"],
        sortBy: (s, ctx) => { const e = ctx.insiderMap[s.ticker] || {}; return -((Number(e.buy_n) || 0) - (Number(e.sell_n) || 0)) },
    },
    {
        id: "foreign_buy", tab: "외국인 순매수", edge: true,
        title: "외국인이 최근 순매수한 회사",
        rule: "네이버 수급 · 최근일 외국인 순매매 > 0",
        pred: (s, ctx) => { const f = ctx.flowMap[s.ticker]; return !!(f && f.length && Number(f[f.length - 1].foreign_net) > 0) },
        chips: ["PBR", "ROE"],
        sortBy: (s, ctx) => { const f = ctx.flowMap[s.ticker]; return f && f.length ? -Number(f[f.length - 1].foreign_net || 0) : 0 },
    },
    {
        id: "dilution_hist", tab: "유증·CB 이력", edge: true,
        title: "유상증자·전환사채·BW 발행 이력이 있는 회사",
        rule: "DART 공시 — 자본조달성 발행(유증/CB/BW) 1건 이상 (사실 빈도)",
        pred: (s, ctx) => dilCount(ctx.forensicsMap[s.ticker]) > 0,
        chips: ["PBR", "PER"],
        sortBy: (s, ctx) => -dilCount(ctx.forensicsMap[s.ticker]),
    },
    {
        id: "value_quality_strict", tab: "저평가+우량",
        title: "업종보다 싸고, 더 잘 버는 회사",
        rule: "PBR·PER 업종 중앙값 이하 + ROE 업종 중앙값 이상",
        pred: (s) => pvs(s, "PBR") === "below" && pvs(s, "PER") === "below" && pvs(s, "ROE") === "above",
        chips: ["PBR", "PER", "ROE"],
        sortBy: (s) => num((s.facts || {}).PBR) ?? 99,
    },
    {
        id: "value_quality", tab: "싸고 잘 버는",
        title: "업종 대비 저평가인데 자본효율은 높은 회사",
        rule: "PBR 업종 중앙값 이하 + ROE 업종 중앙값 이상",
        pred: (s) => pvs(s, "PBR") === "below" && pvs(s, "ROE") === "above",
        chips: ["PBR", "ROE", "부채비율"],
        sortBy: (s) => num((s.facts || {}).PBR) ?? 99,
    },
    {
        id: "per_cheap", tab: "PER 저평가",
        title: "이익 대비 업종보다 싸게 거래되는 회사",
        rule: "PER 업종 중앙값 이하",
        pred: (s) => pvs(s, "PER") === "below",
        chips: ["PER", "ROE", "시가총액"],
        sortBy: (s) => num((s.facts || {}).PER) ?? 999,
    },
    {
        id: "roe_top", tab: "자본효율 상위",
        title: "업종 평균보다 자본효율이 높은 회사",
        rule: "ROE 업종 중앙값 이상",
        pred: (s) => pvs(s, "ROE") === "above",
        chips: ["ROE", "PBR", "부채비율"],
        sortBy: (s) => -(num((s.facts || {}).ROE) ?? -1),
    },
    {
        id: "low_debt", tab: "가벼운 빚",
        title: "빚 부담이 업종보다 가벼운 회사",
        rule: "부채비율 업종 중앙값 이하",
        pred: (s) => pvs(s, "부채비율") === "below",
        chips: ["부채비율", "ROE", "PBR"],
        sortBy: (s) => num((s.facts || {})["부채비율"]) ?? 999,
    },
    {
        id: "below_book", tab: "장부가 밑",
        title: "장부가보다 싸게 거래되는 회사",
        rule: "PBR 1.0 미만 (자산 대비 저평가)",
        pred: (s) => (num((s.facts || {}).PBR) ?? 9) < 1.0,
        chips: ["PBR", "ROE", "배당수익률"],
        sortBy: (s) => num((s.facts || {}).PBR) ?? 99,
    },
]

const COLS: { key: string; label: string; align: string; w: number; sort: boolean }[] = [
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
const RANGE_METRICS = ["PER", "PBR", "ROE", "부채비율", "D/E"]   // D/E=미장 부채 필터(부채비율은 국장만). 배당수익률=소스부재 제거

function metricNum(s: any, key: string): number | null {
    const f = s.facts || {}
    if (key === "cap") return parseCap(f["시가총액"])
    return num(f[key])
}

function readBodyDark(): boolean {
    // 첫 페인트 flash 방지 — body 속성 미설정(마운트 직후) 시 토글 저장 선호(localStorage) → OS 순 폴백.
    // PublicThemeToggle 이 verity_theme 로 저장 + body[data-framer-theme] 설정 = 동일 소스라 첫 페인트부터 정합.
    try {
        if (typeof document !== "undefined" && document.body) {
            const a = document.body.dataset.framerTheme
            if (a === "dark") return true
            if (a === "light") return false
        }
        if (typeof localStorage !== "undefined") {
            const s = localStorage.getItem("verity_theme")
            if (s === "dark") return true
            if (s === "light") return false
        }
        if (typeof window !== "undefined" && window.matchMedia) {
            return window.matchMedia("(prefers-color-scheme: dark)").matches
        }
    } catch (e) {}
    return false
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicDiscovery(props: Props) {
    const { stockUrl, usStockUrl, usSmallcapUrl, insiderUrl, usInsiderUrl, flowUrl, forensicsUrl, apiBase, reportPath, dark, perList, topOffset } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    /* 테마 추종: body[data-framer-theme] 읽기 + 변경 감지 (캔버스는 dark prop 정적) */
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!dark : readBodyDark()))
    useEffect(() => {
        if (onCanvas) return
        const read = () => {
            const t =
                typeof document !== "undefined" && document.body
                    ? document.body.dataset.framerTheme
                    : ""
            setThemeDark(t === "dark")
        }
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

    const isDark = onCanvas ? !!dark : themeDark
    const C = isDark ? DARK : LIGHT
    const cap = Math.max(10, Math.min(120, perList || 40))
    const base = (apiBase || DEFAULT_API).replace(/\/+$/, "")
    const navTop = Math.max(0, Number(topOffset) || 60)   // 사용자 고정 네브바 높이 — 탭/패널 sticky top 에만(전체 패딩 X, PM "탭만")

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [list, setList] = useState<any[]>([])
    const [genAt, setGenAt] = useState<string>("")
    const [insiderMap, setInsiderMap] = useState<Record<string, any>>({})
    const [flowMap, setFlowMap] = useState<Record<string, any[]>>({})
    const [forensicsMap, setForensicsMap] = useState<Record<string, any>>({})
    const [tab, setTab] = useState(0)
    const [view, setView] = useState<string>("table")
    const [sortKey, setSortKey] = useState<string>("cap")
    const [sortDir, setSortDir] = useState<number>(-1)
    const [sector, setSector] = useState<string>("")
    const [mkt, setMkt] = useState<string>("all")   // 전체/국장(kr)/미장(us) 토글
    const [rMetric, setRMetric] = useState<string>("")
    const [rMin, setRMin] = useState<string>("")
    const [rMax, setRMax] = useState<string>("")
    const [selected, setSelected] = useState<string>("")

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    // URL 딥링크 — ?sector=X(섹터 필터) / ?screen=Y(탭 선택) 자동 적용 (결정 동선 링킹). 1회.
    useEffect(() => {
        if (onCanvas || typeof window === "undefined") return
        try {
            const sp = new URLSearchParams(window.location.search)
            const sec = sp.get("sector")
            if (sec) setSector(sec)
            const scr = sp.get("screen")
            if (scr) { const i = SCREENS.findIndex((sc) => sc.id === scr); if (i >= 0) setTab(i) }
        } catch { /* ignore */ }
    }, [onCanvas])

    useEffect(() => {
        if (!stockUrl) return
        let alive = true
        const urls: string[] = [stockUrl, usStockUrl, usSmallcapUrl].filter((u): u is string => Boolean(u))
        Promise.all(urls.map((u) => fetch(u, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).catch(() => null)))
            .then((docs) => {
                if (!alive) return
                const arr: any[] = []
                for (const d of docs) { const a = d && (Array.isArray(d) ? d : d.stocks); if (Array.isArray(a)) arr.push(...(a as any[])) }
                // ticker dedup (smallcap 트랙 ∩ sp600 중복 — 먼저 등장 우선)
                const seen = new Set<string>()
                const deduped = arr.filter((s: any) => { const tk2 = String(s.ticker || ""); if (!tk2 || seen.has(tk2)) return false; seen.add(tk2); return true })
                if (deduped.length) setList(deduped)
                setGenAt(docs[0] && docs[0]._meta && docs[0]._meta.generated_at ? docs[0]._meta.generated_at : "")
            })
        return () => { alive = false }
    }, [stockUrl, usStockUrl, usSmallcapUrl])

    useEffect(() => {
        if (!insiderUrl) return
        let alive = true
        // KR(insider_trades, DART) + US(us_insider_trades, SEC Form4) 병합 — schema 동일, 티커 숫자/비숫자라 충돌 0.
        const urls: string[] = [insiderUrl, usInsiderUrl].filter((u): u is string => Boolean(u))
        Promise.all(urls.map((u) => fetch(u, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).catch(() => null)))
            .then((docs) => {
                if (!alive) return
                const m: Record<string, any> = {}
                for (const d of docs) {
                    const arr = d && (Array.isArray(d) ? d : d.stocks)
                    if (Array.isArray(arr)) for (const x of arr) { if (x && x.ticker) m[String(x.ticker)] = x }
                }
                setInsiderMap(m)
            })
        return () => { alive = false }
    }, [insiderUrl, usInsiderUrl])

    useEffect(() => {
        if (!flowUrl) return
        let alive = true
        fetch(flowUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { const fm = d && (d.flows || d); if (alive && fm && typeof fm === "object") setFlowMap(fm) })
            .catch(() => {})
        return () => { alive = false }
    }, [flowUrl])

    useEffect(() => {
        if (!forensicsUrl) return
        let alive = true
        fetch(forensicsUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const arr = d && (Array.isArray(d) ? d : d.stocks)
                if (!alive || !Array.isArray(arr)) return
                const m: Record<string, any> = {}
                for (const x of arr) { if (x && x.ticker) m[String(x.ticker)] = x }
                setForensicsMap(m)
            })
            .catch(() => {})
        return () => { alive = false }
    }, [forensicsUrl])

    const narrow = w > 0 && w < 620
    const wide = w >= 980          // master-detail 패널 표시 임계
    const pad = narrow ? 12 : 18
    const ctx = useMemo<Ctx>(() => ({ insiderMap, flowMap, forensicsMap }), [insiderMap, flowMap, forensicsMap])
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
    const visibleTabs = useMemo(() => SCREENS.map((sc, i) => i).filter((i) => counts[i] > 0), [counts])

    useEffect(() => {
        if (visibleTabs.length && visibleTabs.indexOf(tab) < 0) setTab(visibleTabs[0])
    }, [visibleTabs, tab])

    const sectors = useMemo(() => {
        const set: Record<string, number> = {}
        for (const s of list) { const sec = sectorOf(s); if (sec) set[sec] = (set[sec] || 0) + 1 }
        return Object.keys(set).sort((a, b) => set[b] - set[a])
    }, [list])

    const sc = SCREENS[tab] || SCREENS[0]
    const rMinN = rMin.trim() === "" ? null : Number(rMin)
    const rMaxN = rMax.trim() === "" ? null : Number(rMax)
    const useTable = view === "table" && !narrow   // 모바일=카드 강제(8컬럼 가로스크롤 회피)

    const sel = useMemo(() => {
        if (!list.length) return { total: 0, items: [] as any[] }
        let hits = list.filter((s) => sc.pred(s, ctx))
        if (mkt !== "all") hits = hits.filter((s) => (!/^\d{6}$/.test(String(s.ticker || ""))) === (mkt === "us"))
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
        const arr = hits.slice()
        const cmpNull = (va: number | null, vb: number | null) => {
            if (va == null && vb == null) return 0
            if (va == null) return 1
            if (vb == null) return -1
            return (va - vb) * sortDir
        }
        if (useTable) {
            if (sortKey === "name") {
                arr.sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")) * sortDir)
            } else if (sortKey === "sector") {
                arr.sort((a, b) => sectorOf(a).localeCompare(sectorOf(b)) * sortDir)
            } else if (sortKey === "insider") {
                arr.sort((a, b) => cmpNull(insiderNet(a), insiderNet(b)))
            } else {
                arr.sort((a, b) => cmpNull(metricNum(a, sortKey), metricNum(b, sortKey)))
            }
        } else {
            arr.sort((a, b) => sc.sortBy(a, ctx) - sc.sortBy(b, ctx))
        }
        return { total: hits.length, items: arr.slice(0, cap) }
    }, [list, sc, ctx, mkt, sector, rMetric, rMinN, rMaxN, useTable, sortKey, sortDir, cap])

    // 넓은 화면: 선택 종목 자동 유지(없거나 목록 밖이면 최상단). 좁은 화면: 패널 없음.
    useEffect(() => {
        if (!wide || !sel.items.length) return
        const inList = sel.items.some((s) => s.ticker === selected)
        if (!inList) setSelected(sel.items[0].ticker)
    }, [wide, sel.items, selected])

    const selStock = useMemo(() => list.find((s) => s.ticker === selected) || null, [list, selected])

    // 선택 종목 실시간가(/api/stock) = 2026-07-03 컴플라이언스로 제거 — 시세는 리포트(네이버 link-out/TV 위젯)에서

    const go = (ticker: string) => {
        if (onCanvas || typeof window === "undefined" || !ticker) return
        const p = (reportPath || DEFAULT_REPORT).replace(/\/+$/, "") || "/"
        window.location.href = p + "?q=" + encodeURIComponent(ticker)
    }
    const onRow = (ticker: string) => { if (wide) setSelected(ticker); else go(ticker) }
    const onSort = (key: string) => {
        if (sortKey === key) { setSortDir((d) => -d); return }
        setSortKey(key)
        setSortDir(key === "name" || key === "sector" ? 1 : -1)
    }
    const resetFilters = () => { setMkt("all"); setSector(""); setRMetric(""); setRMin(""); setRMax("") }

    const wrap: CSSProperties = {
        width: "100%", minHeight: "100%",
        background: C.bg, fontFamily: FONT, padding: pad, boxSizing: "border-box", color: C.ink,
        // 🚨 스태킹 격리 — 내부 sticky(zIndex)가 페이지 fixed 네브바 위로 그려지는 사고 원천 차단 (2026-07-08, /discover nav zIndex 부재 사고. 페이지 nav zIndex 10 + 여기 격리 이중 방어).
        position: "relative", zIndex: 0, isolation: "isolate",
    }
    const chipFor = (s: any, key: string) => {
        const v = (s.facts || {})[key]
        if (v == null) return null
        const vs = pvs(s, key)
        const arrow = vs === "above" ? " ↑" : vs === "below" ? " ↓" : ""
        const col = vs === "above" ? C.vg : vs === "below" ? C.down : C.faint
        return (
            <span key={key} style={{ fontSize: 11, fontWeight: 600, color: C.sub, background: C.bg, borderRadius: 7, padding: "3px 8px", whiteSpace: "nowrap" }}>
                <span style={{ color: C.faint }}>{key} </span>
                <span style={{ color: C.ink }}>{v}</span>
                {arrow && <span style={{ color: col, fontWeight: 700 }}>{arrow}</span>}
            </span>
        )
    }
    const edgeChips = (s: any) => {
        const out: any[] = []
        const nv = insiderNet(s)
        if (nv) out.push(
            <span key="ins" style={{ fontSize: 11, fontWeight: 700, color: nv > 0 ? C.up : C.down, background: C.bg, borderRadius: 7, padding: "3px 8px", whiteSpace: "nowrap" }}>내부자 {fmtShares(nv)}</span>
        )
        const f = flowMap[s.ticker]
        if (f && f.length) {
            const fn = Number(f[f.length - 1].foreign_net)
            if (fn) out.push(
                <span key="for" style={{ fontSize: 11, fontWeight: 700, color: fn > 0 ? C.up : C.down, background: C.bg, borderRadius: 7, padding: "3px 8px", whiteSpace: "nowrap" }}>외국인 {fmtShares(fn)}</span>
            )
        }
        const dc = dilCount(forensicsMap[s.ticker])
        if (dc > 0) out.push(
            <span key="dil" style={{ fontSize: 11, fontWeight: 700, color: C.sub, background: C.bg, borderRadius: 7, padding: "3px 8px", whiteSpace: "nowrap" }}>유증·CB {dc}회</span>
        )
        return out
    }
    // 커스텀 chevron (OS 기본 화살표 제거 — appearance none). 색 = 테마 faint.
    // data URI 전체 encodeURIComponent — 공백/따옴표 raw 상태면 Safari·Framer 퍼블리시에서 파싱 실패 → placeholder 텍스처 노출 (다크에서만 도드라짐).
    const chevronUrl = `url("data:image/svg+xml,${encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 6' width='10' height='6'><path d='M1 1l4 4 4-4' stroke='${C.faint}' stroke-width='1.6' fill='none' stroke-linecap='round' stroke-linejoin='round'/></svg>`)}")`
    const selStyle: CSSProperties = {
        border: "none", borderRadius: 9, padding: "7px 28px 7px 11px", fontSize: 12, fontFamily: FONT,
        fontWeight: 700, backgroundColor: C.card, color: C.ink, outline: "none", cursor: "pointer",
        appearance: "none", WebkitAppearance: "none", MozAppearance: "none",
        backgroundImage: chevronUrl, backgroundRepeat: "no-repeat", backgroundPosition: "right 10px center", backgroundSize: "10px 6px",
    }
    const numStyle: CSSProperties = {
        width: 58, border: `1px solid ${C.line}`, borderRadius: 9, padding: "7px 8px", fontSize: 12,
        fontFamily: FONT, fontWeight: 700, background: C.card, color: C.ink, outline: "none", boxSizing: "border-box",
    }

    // 로딩 스켈레톤 — 탭/헤더/툴바/결과 전 영역 일관 적용 (list 적재 전 빈 영역 방지). 토스식 shimmer.
    const loading = list.length === 0
    const skBase = isDark ? "#222a33" : "#e9edf1"
    const skHi = isDark ? "#2d3742" : "#f3f5f7"
    const skBlock = (bw: any, bh: number, br = 6): CSSProperties => ({
        width: bw, height: bh, borderRadius: br, background: skBase,
        backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`,
        backgroundSize: "800px 100%", animation: "vsrShimmer 1.4s ease-in-out infinite", flexShrink: 0,
    })

    const tabButton = (i: number) => {
        const active = i === tab
        if (narrow) {
            return (
                <button key={SCREENS[i].id} onClick={() => setTab(i)}
                    style={{
                        flexShrink: 0, border: "none", cursor: "pointer", fontFamily: FONT,
                        padding: "8px 13px", borderRadius: 999, fontSize: 12.5, fontWeight: 700,
                        background: active ? C.card : "transparent", color: active ? C.ink : C.sub,
                        boxShadow: active ? "0 1px 2px rgba(0,0,0,0.06)" : "none",
                    }}>
                    {SCREENS[i].tab}
                    <span style={{ marginLeft: 6, fontWeight: 700, color: C.faint }}>{counts[i]}</span>
                </button>
            )
        }
        return (
            <button key={SCREENS[i].id} onClick={() => setTab(i)}
                style={{
                    width: "100%", border: "none", cursor: "pointer", fontFamily: FONT,
                    display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8,
                    padding: "10px 13px", borderRadius: 10, fontSize: 13.5, fontWeight: 700, textAlign: "left",
                    background: active ? C.card : "transparent", color: active ? C.ink : C.sub,
                    boxShadow: active ? "0 1px 2px rgba(0,0,0,0.06)" : "none",
                }}>
                <span style={{ whiteSpace: "nowrap" }}>{SCREENS[i].tab}</span>
                <span style={{ flexShrink: 0, fontWeight: 700, fontSize: 12, color: C.faint }}>{counts[i]}</span>
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
        width: col.w || undefined, minWidth: col.w === 0 ? 148 : col.w, flex: col.w === 0 ? 1 : "none" as any,
        textAlign: col.align, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", ...extra,
    })

    // 우측 상세 패널(데스크탑) — 이미 로드된 사실 + 실시간가 + 전체 리포트 CTA.
    const detailPanel = () => {
        const s = selStock
        if (!s) return null
        const facts = s.facts || {}
        const ins = insiderMap[s.ticker]
        const flow = flowMap[s.ticker] || []
        const flast = flow.length ? flow[flow.length - 1] : null
        const peerRows = (s.peer && s.peer.rows) || []
        const own = s.ownership || null
        const foren = forensicsMap[s.ticker] || null
        const kv = (k: string, v: any, color?: string) => (
            <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", fontSize: 12.5 }}>
                <span style={{ color: C.sub, fontWeight: 600 }}>{k}</span>
                <span style={{ fontWeight: 700, color: color || C.ink, fontVariantNumeric: "tabular-nums" }}>{v}</span>
            </div>
        )
        const sub = (t: string) => <div style={{ fontSize: 11.5, fontWeight: 800, color: C.faint, marginTop: 14, marginBottom: 2 }}>{t}</div>
        return (
            <div style={{ flexShrink: 0, width: 340, position: "sticky", top: navTop, maxHeight: `calc(100vh - ${navTop + 24}px)`, overflowY: "auto", background: C.card, borderRadius: 16, padding: 16, boxShadow: "0 1px 3px rgba(0,0,0,0.05)", boxSizing: "border-box" }}>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 11 }}>
                    <Logo ticker={s.ticker} name={s.name} market={s.market} C={C} size={40} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 17, fontWeight: 800, color: C.ink, letterSpacing: "-0.3px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.name}</div>
                        <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{s.ticker} · {s.market}</div>
                    </div>
                    <button onClick={() => setSelected("")} style={{ border: "none", background: "transparent", cursor: "pointer", fontSize: 16, color: C.faint, fontWeight: 700, padding: 0, lineHeight: 1 }}>×</button>
                </div>
                {s.business && <div style={{ fontSize: 12, color: C.sub, fontWeight: 600, marginTop: 6, lineHeight: 1.45 }}>{s.business}</div>}

                <div style={{ marginTop: 6 }}>
                    {sub("기본 지표")}
                    {PANEL_FACTS.filter((k) => facts[k] != null).map((k) => kv(k, facts[k]))}
                </div>

                {peerRows.length > 0 && (
                    <div>
                        {sub("동종업계 비교 (업종 중앙값)")}
                        {peerRows.map((r: any, i: number) => kv(
                            r.key,
                            <span>{r.value} <span style={{ color: C.faint, fontWeight: 600 }}>vs {r.median}</span> <span style={{ color: C.vt }}>{r.vs === "above" ? "↑" : r.vs === "below" ? "↓" : "="}</span></span>
                        ))}
                    </div>
                )}

                {ins && (Number(ins.total) > 0) && (
                    <div>
                        {sub(/^\d{6}$/.test(String(s.ticker || "")) ? "내부자 거래 (DART)" : "내부자 거래 (SEC Form 4)")}
                        {kv("순증감", fmtShares(ins.net_change), Number(ins.net_change) >= 0 ? C.up : C.down)}
                        {kv("매수 / 매도", `${ins.buy_n}건 / ${ins.sell_n}건`)}
                        {(ins.trades || []).slice(0, 2).map((t: any, i: number) => (
                            <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, padding: "4px 0", color: C.sub, fontWeight: 600 }}>
                                <span>{mmdd(t.date)} {t.person}{t.position ? ` · ${t.position}` : ""}</span>
                                <span style={{ color: Number(t.change) >= 0 ? C.up : C.down, fontWeight: 700 }}>{fmtShares(t.change)}</span>
                            </div>
                        ))}
                    </div>
                )}

                {flast && (Number(flast.foreign_net) || Number(flast.inst_net)) ? (
                    <div>
                        {sub("외국인·기관 수급 (최근)")}
                        {kv("외국인 순매매", fmtShares(flast.foreign_net), Number(flast.foreign_net) >= 0 ? C.up : C.down)}
                        {kv("기관 순매매", fmtShares(flast.inst_net), Number(flast.inst_net) >= 0 ? C.up : C.down)}
                    </div>
                ) : null}

                {own && (
                    <div>
                        {sub("지배구조 · 공정위 (의결권 지분)")}
                        {own.group && kv("기업집단", own.group, C.vt)}
                        {own.family_pct != null && kv("총수일가 지배지분", own.family_pct + "%", own.family_pct > 0 ? C.ink : C.faint)}
                        {(own.shareholders || []).slice(0, 3).map((sh: any, i: number) => (
                            <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, padding: "4px 0", color: C.sub, fontWeight: 600 }}>
                                <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "66%" }}>{sh.type}{sh.name && sh.name !== sh.type ? ` · ${sh.name}` : ""}</span>
                                <span style={{ color: C.ink, fontWeight: 700 }}>{sh.pct}%</span>
                            </div>
                        ))}
                        {own.cross_check && own.cross_check.status && kv("DART↔공정위 교차", own.cross_check.status === "match" ? "일치" : own.cross_check.status === "approx" ? "근사" : "차이", own.cross_check.status === "match" ? C.vg : C.faint)}
                        {own.sub_count ? kv("계열사", own.sub_count + "곳") : null}
                    </div>
                )}

                {foren && foren.counts && Object.keys(foren.counts).length > 0 && (
                    <div>
                        {sub("공시 이력 · DART (이벤트 누적 빈도)")}
                        {Object.entries(foren.counts).sort((a: any, b: any) => Number(b[1]) - Number(a[1])).slice(0, 5).map(([k, v]: any) => kv(k, v + "회", DILUTIVE.indexOf(k) >= 0 ? C.ink : C.sub))}
                        {(foren.events || []).slice(0, 2).map((e: any, i: number) => (
                            <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, padding: "4px 0", color: C.sub, fontWeight: 600 }}>
                                <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "72%" }}>{mmdd(e.date)} {e.category}</span>
                                {e.source_url && <a href={e.source_url} target="_blank" rel="noreferrer" onClick={(ev) => ev.stopPropagation()} style={{ color: C.vt, fontWeight: 700, textDecoration: "none", flexShrink: 0 }}>원문</a>}
                            </div>
                        ))}
                    </div>
                )}

                {/* 애널리스트 컨센서스(목표주가·투자의견) 인라인 노출 제거 — 2026-07-10 컴플라이언스:
                    증권사 컨센서스 재배포(이중 IP: 네이버 ToS + 증권사 리서치 저작물) 소지.
                    PublicStockReport 의 출처 link-out 패턴과 정합 — 상세는 전체 리포트에서 출처 연결. */}

                <button onClick={() => go(s.ticker)} style={{ width: "100%", marginTop: 16, border: "none", cursor: "pointer", fontFamily: FONT, padding: "11px 0", borderRadius: 11, fontSize: 13, fontWeight: 800, background: C.vt, color: "#fff" }}>전체 리포트 보기 →</button>
                <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.5, textAlign: "center" }}>사실만 · 차트·심화는 전체 리포트</div>
            </div>
        )
    }

    return (
        <div ref={rootRef} style={wrap}>
            <style>{`@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
            <div style={{ display: "flex", flexDirection: narrow ? "column" : "row", gap: narrow ? 12 : 20, alignItems: "flex-start" }}>
                {/* 탭 — 흰박스 없이 회색 배경에 직접, 활성만 흰 알약 */}
                {narrow ? (
                    <div style={{ display: "flex", gap: 7, overflowX: "auto", padding: `10px ${pad}px`, width: `calc(100% + ${pad * 2}px)`, marginLeft: -pad, position: "sticky", top: navTop, background: C.glass, backdropFilter: "saturate(1.4) blur(14px)", WebkitBackdropFilter: "saturate(1.4) blur(14px)", zIndex: 5, scrollbarWidth: "none", boxShadow: `0 8px 8px -7px ${isDark ? "rgba(0,0,0,0.5)" : "rgba(0,0,0,0.14)"}` }}>
                        {loading
                            ? Array.from({ length: 4 }).map((_, i) => <div key={i} style={skBlock(i === 0 ? 76 : 60, 33, 999)} />)
                            : visibleTabs.map((i) => tabButton(i))}
                    </div>
                ) : (
                    <div style={{ flexShrink: 0, width: 188, position: "sticky", top: navTop, display: "flex", flexDirection: "column", gap: 2 }}>
                        {loading
                            ? Array.from({ length: 5 }).map((_, i) => <div key={i} style={{ ...skBlock("100%", 40, 10), marginBottom: 2 }} />)
                            : visibleTabs.map((i) => tabButton(i))}
                    </div>
                )}

                {/* 콘텐츠 */}
                <div style={{ flex: 1, minWidth: 0, width: narrow ? "100%" : "auto" }}>
                    {loading ? (
                        <div style={{ padding: "0 2px 10px" }}>
                            <div style={skBlock(168, 16, 7)} />
                            <div style={{ ...skBlock(232, 11, 6), marginTop: 7 }} />
                        </div>
                    ) : (
                        <div style={{ padding: "0 2px 10px" }}>
                            <div style={{ fontSize: 15.5, fontWeight: 700, color: C.ink, letterSpacing: "-0.3px" }}>{sc.title}{sector ? ` · ${sector}` : ""}</div>
                            <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3 }}>{sc.rule} · 결과 {sel.total}종목{sel.total > sel.items.length ? ` (상위 ${sel.items.length})` : ""}{genAt ? ` · ${fmtAge(genAt)} 갱신` : ""}</div>
                        </div>
                    )}

                    {/* 도구막대 */}
                    {loading ? (
                        <div style={{ display: "flex", gap: 7, flexWrap: "wrap", alignItems: "center", marginBottom: 10 }}>
                            {!narrow && <div style={skBlock(92, 34, 10)} />}
                            <div style={skBlock(104, 34, 9)} />
                            <div style={skBlock(104, 34, 9)} />
                        </div>
                    ) : (
                        <div style={{ display: "flex", gap: 7, flexWrap: "wrap", alignItems: "center", marginBottom: 10 }}>
                            {!narrow && (
                                <div style={{ display: "flex", gap: 3, background: C.card, borderRadius: 10, padding: 3, boxShadow: "0 1px 2px rgba(0,0,0,0.04)" }}>
                                    {[["table", "표"], ["list", "리스트"]].map(([v, lb]) => (
                                        <button key={v} onClick={() => setView(v)}
                                            style={{ border: "none", cursor: "pointer", fontFamily: FONT, padding: "6px 12px", borderRadius: 8, fontSize: 12, fontWeight: 700, background: view === v ? C.bg : "transparent", color: view === v ? C.ink : C.sub }}>{lb}</button>
                                    ))}
                                </div>
                            )}
                            <div style={{ display: "flex", gap: 2, background: C.line, borderRadius: 9, padding: 2, flexShrink: 0 }}>
                                {([["all", "전체"], ["kr", "국장"], ["us", "미장"]] as [string, string][]).map(([m, lbl]) => (
                                    <button key={m} onClick={() => setMkt(m)}
                                        style={{ border: "none", cursor: "pointer", padding: "5px 10px", borderRadius: 7, fontSize: 12, fontWeight: 800, fontFamily: "inherit", whiteSpace: "nowrap", background: mkt === m ? C.card : "transparent", color: mkt === m ? C.vt : C.sub }}>
                                        {lbl}
                                    </button>
                                ))}
                            </div>
                            <select value={sector} onChange={(e) => setSector(e.target.value)} style={{ ...selStyle, maxWidth: 150, textOverflow: "ellipsis" }}>
                                <option value="">섹터 전체</option>
                                {sectors.map((sec) => (<option key={sec} value={sec}>{sec}</option>))}
                            </select>
                            <select value={rMetric} onChange={(e) => setRMetric(e.target.value)} style={selStyle}>
                                <option value="">지표 범위…</option>
                                {RANGE_METRICS.map((m) => (<option key={m} value={m}>{m}</option>))}
                            </select>
                            {rMetric && (
                                <>
                                    <input value={rMin} onChange={(e) => setRMin(e.target.value)} placeholder="최소" inputMode="decimal" style={numStyle} />
                                    <span style={{ fontSize: 12, color: C.faint, fontWeight: 700 }}>~</span>
                                    <input value={rMax} onChange={(e) => setRMax(e.target.value)} placeholder="최대" inputMode="decimal" style={numStyle} />
                                </>
                            )}
                            {(sector || rMetric) && (
                                <button onClick={resetFilters} style={{ border: "none", cursor: "pointer", fontFamily: FONT, padding: "7px 11px", borderRadius: 9, fontSize: 12, fontWeight: 700, background: C.bg, color: C.sub }}>초기화</button>
                            )}
                        </div>
                    )}

                    {/* 표/리스트 + (넓은 화면) 우측 상세 패널 */}
                    <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                            {loading ? (
                                <div style={{ background: C.card, borderRadius: 16, boxShadow: "0 1px 3px rgba(0,0,0,0.04)", overflow: "hidden" }}>
                                    {Array.from({ length: 9 }).map((_, i) => (
                                        <div key={i} style={{ display: "flex", alignItems: "center", gap: 14, padding: "12px 16px", borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                                            <div style={skBlock(20, 20, 6)} />
                                            <div style={{ flex: 1, minWidth: 0 }}><div style={skBlock(i % 3 === 0 ? "52%" : "38%", 13)} /></div>
                                            {!narrow && <div style={skBlock(64, 13)} />}
                                            {!narrow && <div style={skBlock(54, 13)} />}
                                            <div style={skBlock(46, 13)} />
                                        </div>
                                    ))}
                                </div>
                            ) : useTable ? (
                                <div style={{ background: C.card, borderRadius: 16, boxShadow: "0 1px 3px rgba(0,0,0,0.04)", overflowX: "auto" }}>
                                    <div style={{ minWidth: TABLE_MIN }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "11px 16px", borderBottom: `1px solid ${C.line}`, position: "sticky", top: 0, background: C.card, zIndex: 2 }}>
                                            {COLS.map((col) => {
                                                const activeSort = sortKey === col.key
                                                const label = col.label + (activeSort ? (sortDir < 0 ? " ↓" : " ↑") : "")
                                                if (!col.sort) {
                                                    return <div key={col.key} style={colStyle(col, { fontSize: 11.5, fontWeight: 700, color: C.faint })}>{col.label}</div>
                                                }
                                                return (
                                                    <button key={col.key} onClick={() => onSort(col.key)}
                                                        style={{ border: "none", cursor: "pointer", fontFamily: FONT, background: "transparent", padding: 0,
                                                            fontSize: 11.5, fontWeight: 700, color: activeSort ? C.vg : C.faint, ...colStyle(col) }}>{label}</button>
                                                )
                                            })}
                                        </div>
                                        {sel.items.map((s, idx) => {
                                            const isSel = wide && s.ticker === selected
                                            return (
                                                <div key={s.ticker} role="button" tabIndex={0} onClick={() => onRow(s.ticker)}
                                                    style={{ display: "flex", alignItems: "center", gap: 14, padding: "10px 16px", borderTop: idx === 0 ? "none" : `1px solid ${C.line}`, cursor: "pointer", fontVariantNumeric: "tabular-nums", background: isSel ? C.bg : "transparent" }}>
                                                    {COLS.map((col) => {
                                                        if (col.key === "rank") {
                                                            return <div key="rank" style={colStyle(col, { fontSize: 12, fontWeight: 700, color: C.faint })}>{idx + 1}</div>
                                                        }
                                                        if (col.key === "name") {
                                                            return (
                                                                <div key="name" style={{ flex: 1, minWidth: 148, display: "flex", alignItems: "center", gap: 10 }}>
                                                                    <Logo ticker={s.ticker} name={s.name} market={s.market} C={C} size={30} />
                                                                    <div style={{ minWidth: 0 }}>
                                                                        <div style={{ fontSize: 13.5, fontWeight: 700, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.name}</div>
                                                                        <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600 }}>{s.ticker} · {s.market}</div>
                                                                    </div>
                                                                </div>
                                                            )
                                                        }
                                                        if (col.key === "insider") {
                                                            const nv = insiderNet(s)
                                                            return (
                                                                <div key="insider" style={colStyle(col, { fontSize: 12.5, fontWeight: sortKey === "insider" ? 800 : 700, color: nv == null ? C.faint : (nv > 0 ? C.up : nv < 0 ? C.down : C.faint) })}>
                                                                    {nv == null ? "—" : fmtShares(nv)}
                                                                </div>
                                                            )
                                                        }
                                                        const v = cellText(s, col.key)
                                                        const isSorted = sortKey === col.key
                                                        return (
                                                            <div key={col.key} style={colStyle(col, { fontSize: 12.5, fontWeight: isSorted ? 800 : 600, color: v === "—" ? C.faint : (col.key === "sector" ? C.sub : C.ink) })}>{v}</div>
                                                        )
                                                    })}
                                                </div>
                                            )
                                        })}
                                        {sel.total > sel.items.length && (
                                            <div style={{ textAlign: "center", padding: "12px 0", fontSize: 12, color: C.faint, fontWeight: 600, borderTop: `1px solid ${C.line}` }}>
                                                결과 {sel.total}종목 중 상위 {sel.items.length} 표시 · 필터·정렬로 좁히기
                                            </div>
                                        )}
                                    </div>
                                </div>
                            ) : (
                                <div style={{ background: C.card, borderRadius: 16, padding: "4px 6px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                                    {sel.items.map((s, idx) => {
                                        const ec = edgeChips(s)
                                        const isSel = wide && s.ticker === selected
                                        return (
                                            <div key={s.ticker} role="button" tabIndex={0} onClick={() => onRow(s.ticker)}
                                                style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 10px", borderTop: idx === 0 ? "none" : `1px solid ${C.line}`, cursor: "pointer", borderRadius: 10, background: isSel ? C.bg : "transparent" }}>
                                                <Logo ticker={s.ticker} name={s.name} market={s.market} C={C} />
                                                <div style={{ flex: 1, minWidth: 0 }}>
                                                    <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
                                                        <span style={{ fontSize: 14.5, fontWeight: 700, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "62%" }}>{s.name}</span>
                                                        <span style={{ flexShrink: 0, fontSize: 11, color: C.faint, fontWeight: 600 }}>{s.ticker} · {s.market}</span>
                                                    </div>
                                                    {s.business && <div style={{ fontSize: 11.5, color: C.sub, fontWeight: 600, marginTop: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{s.business}</div>}
                                                    <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginTop: 6 }}>
                                                        {sc.chips.map((k) => chipFor(s, k))}
                                                        {ec}
                                                    </div>
                                                </div>
                                                <span style={{ flexShrink: 0, fontSize: 16, color: C.faint, fontWeight: 600 }}>›</span>
                                            </div>
                                        )
                                    })}
                                    {sel.total > sel.items.length && (
                                        <div style={{ textAlign: "center", padding: "12px 0 8px", fontSize: 12, color: C.faint, fontWeight: 600, borderTop: `1px solid ${C.line}` }}>
                                            결과 {sel.total}종목 중 상위 {sel.items.length} 표시 · 필터로 좁히기
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                        {wide && loading && (
                            <div style={{ flexShrink: 0, width: 340, background: C.card, borderRadius: 16, padding: 16, boxShadow: "0 1px 3px rgba(0,0,0,0.05)", boxSizing: "border-box" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
                                    <div style={skBlock(40, 40, 12)} />
                                    <div style={{ flex: 1 }}><div style={skBlock("70%", 15, 7)} /><div style={{ ...skBlock("44%", 11, 6), marginTop: 6 }} /></div>
                                </div>
                                <div style={{ ...skBlock("52%", 21, 8), marginTop: 12 }} />
                                {Array.from({ length: 6 }).map((_, i) => (
                                    <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "7px 0" }}>
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

            <div style={{ textAlign: "center", fontSize: 11.5, color: C.sub, fontWeight: 600, marginTop: 20, lineHeight: 1.55 }}>
                직접 조건검색으로 짜기 어려운 사실 기반 스크린 — 내부자·외국인 수급·지배구조·공시이력
            </div>
            <div style={{ textAlign: "center", fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 6, lineHeight: 1.5 }}>
                시총·PER·PBR·ROE = KRX·DART·SEC · 내부자=DART(국장)·SEC Form4(미장) · 외국인 수급=네이버 · 지배구조=공정위 · 공시이력=DART · 사실 정렬·필터일 뿐
            </div>
        </div>
    )
}

addPropertyControls(PublicDiscovery, {
    stockUrl: { type: ControlType.String, title: "Stock URL", defaultValue: DEFAULT_URL },
    usStockUrl: { type: ControlType.String, title: "US Stock URL", defaultValue: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_stock_report_public.json" },
    usSmallcapUrl: { type: ControlType.String, title: "US Smallcap URL", defaultValue: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_stock_report_us_smallcap.json" },
    insiderUrl: { type: ControlType.String, title: "Insider URL", defaultValue: DEFAULT_INSIDER },
    usInsiderUrl: { type: ControlType.String, title: "US Insider URL", defaultValue: DEFAULT_US_INSIDER },
    flowUrl: { type: ControlType.String, title: "Flow URL", defaultValue: DEFAULT_FLOW },
    forensicsUrl: { type: ControlType.String, title: "Forensics URL", defaultValue: DEFAULT_FORENSICS },
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    reportPath: { type: ControlType.String, title: "Report Path", defaultValue: DEFAULT_REPORT },
    perList: { type: ControlType.Number, title: "Rows", defaultValue: 40, min: 10, max: 120, step: 10 },
    topOffset: { type: ControlType.Number, title: "Top Offset (navbar)", defaultValue: 60, min: 0, max: 200, step: 4 },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})
