import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useState, type CSSProperties } from "react"

/**
 * 결정 요약 (검색 통합) — VERITY 공개 터미널. 종목 검색 + 결정 scaffold 를 한 컴포넌트로 통합.
 *
 * 🚨 통합 이유(2026-06-23) = 검색·패널이 한 컴포넌트면 선택이 *내부 state* 라 ?q/localStorage 동기화 싸움이 사라짐.
 *   선택 → 내부 state 즉시 갱신(리로드 없음) + localStorage `verity_last_ticker` + ?q(replaceState) 기록(리포트 토글 유지)
 *   + "verity-ticker-change" 이벤트 발사 → 같은 페이지 PublicThesisNote(내 관점)가 리로드 없이 따라옴.
 * 검색창 디자인 = PublicStockReport 본문 검색과 동일(토스식 borderless 채움 · 돋보기 · 클리어 × · 드롭다운).
 *
 * 🚨 목표 = 사용자가 *자기* 매매 결정을 내리도록 사실을 결정 축으로 재구성 (결정-support, 결정-making 아님).
 * 🚨 RULE 7 = 사실 재배열 + 교과서적 일반 방향만. 자체 점수·가중·종합·추천 0. "가중·종합·판단은 본인" 면책 의무.
 * 🚨 RULE 6 = LLM 내러티브 0 (전부 결정론적 규칙 + 발행 사실). 산식/엔진 비노출(공개 희석 VERITY).
 * 데이터(5 발행 피드) = stock_report_public(facts/peer/ownership·검색 universe) + insider_trades + disclosure_forensics + stock_flow_5d + market_warnings.
 * 🚨 결정 동선 링킹 = "관련 탐색" → /discover?sector=·?screen= 딥링크. 강세=빨강/약세=파랑(KR 관례).
 */

const LIGHT = { bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#e5e8eb", up: "#f04452", down: "#3182f6", vg: "#0ca678", vgS: "#e7faf0", vt: "#6c5ce7", vtS: "#f0edff", amber: "#ff9500", amberS: "#fff4e0", redS: "#fdecee", upS: "#fdecee", downS: "#eaf1fe" }
const DARK = { bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#252b34", up: "#f04452", down: "#5b9bff", vg: "#34e08a", vgS: "#11281d", vt: "#a99bff", vtS: "#241f3a", amber: "#ffb340", amberS: "#2a2113", redS: "#2a1518", upS: "#2a1a1d", downS: "#17263c" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const KR_MK = ["KOSPI", "KOSDAQ", "KONEX"]

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
    if (!p) return ""
    if (p.indexOf("http") === 0) return p  // 폴백 소스(nvstly·공식 파비콘) = 절대 URL 그대로
    return "https://cdn.brandfetch.io/" + p + "?c=" + BF_CID + "&w=" + size * 2 + "&h=" + size * 2
}
const FLAG_BASE = "https://hatscripts.github.io/circle-flags/flags/"
const LAST_TK_KEY = "verity_last_ticker"
const TK_EVENT = "verity-ticker-change"

const DEF_STOCK = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_report_public.json"
const DEF_INSIDER = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/insider_trades.json"
const DEF_FORENSICS = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/disclosure_forensics.json"
const DEF_FLOW = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_flow_5d.json"
const DEF_WARN = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/market_warnings.json"
const DEF_UNIVERSE = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/universe_search.json"
const DEF_API = "https://project-yw131.vercel.app"

const VALUE_KEYS = ["PER", "PBR"]
const QUALITY_KEYS = ["ROE", "영업이익률"]
const LOWER_BETTER = ["PER", "PBR", "부채비율"]
const DILUTIVE = ["유상증자", "전환사채(CB)", "신주인수권부사채(BW)"]

interface Props {
    ticker: string
    stockUrl: string
    usStockUrl: string
    usSmallcapUrl?: string
    insiderUrl: string
    forensicsUrl: string
    flowUrl: string
    warnUrl: string
    reportPath: string
    discoverPath: string
    dark: boolean
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
function flagCode(market: any): string {
    const m = String(market || "").toUpperCase()
    if (KR_MK.indexOf(m) >= 0 || m.indexOf("KOS") >= 0 || m.indexOf("KONEX") >= 0) return "kr"
    if (m.indexOf("NAS") >= 0 || m.indexOf("NYSE") >= 0 || m.indexOf("AMEX") >= 0 || m.indexOf("US") >= 0) return "us"
    return "kr"
}
function Logo(props: { ticker: string; name: string; market: string; C: any; size?: number }) {
    const { ticker, name, market, C } = props
    const size = props.size || 38
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
                    style={{ width: size, height: size, borderRadius: 11, objectFit: "contain", padding: "13%", boxSizing: "border-box", display: "block", background: bfLogoBg(ticker)}} />
            ) : (
                <div style={{ width: size, height: size, borderRadius: 11, background: C.vtS, color: C.vt, display: "flex", alignItems: "center", justifyContent: "center", fontSize: Math.round(size * 0.42), fontWeight: 800 }}>{ch}</div>
            )}
            {code && (
                <img src={FLAG_BASE + code + ".svg"} alt="" width={fsize} height={fsize}
                    style={{ position: "absolute", right: -3, bottom: -3, width: fsize, height: fsize, borderRadius: "50%", border: `1.5px solid ${C.card}`, background: C.card, display: "block" }} />
            )}
        </div>
    )
}

function DirArrow(props: { up: boolean; C: any }) {
    const { up, C } = props
    const col = up ? C.up : C.down
    const bg = up ? C.upS : C.downS
    return (
        <span style={{ flexShrink: 0, display: "inline-flex", alignItems: "center", justifyContent: "center", width: 18, height: 18, borderRadius: 5, background: bg }} aria-hidden="true">
            <svg width={10} height={10} viewBox="0 0 12 12" fill="none" stroke={col} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                {up ? (<><line x1="6" y1="10" x2="6" y2="2.6" /><polyline points="2.8,5.6 6,2.4 9.2,5.6" /></>)
                    : (<><line x1="6" y1="2" x2="6" y2="9.4" /><polyline points="2.8,6.4 6,9.6 9.2,6.4" /></>)}
            </svg>
        </span>
    )
}

const DEMO = {
    name: "DL이앤씨", ticker: "375500", market: "KOSPI", business: "건설·플랜트 EPC",
    facts: { PER: "8.3", PBR: "0.6", ROE: "9.7%", 부채비율: "20%", 시가총액: "3.1조" },
    peer: { sector: "건설", rows: [{ key: "PER", value: "8.3", median: "18.6", vs: "below" }, { key: "PBR", value: "0.6", median: "1.4", vs: "below" }, { key: "ROE", value: "9.7%", median: "7%", vs: "above" }, { key: "부채비율", value: "84%", median: "87%", vs: "below" }, { key: "영업이익률", value: "5.2%", median: "3.2%", vs: "above" }] },
    consensus: { target_price: "122,588원", opinion: "매수" },
}
const DEMO_INS = { net_change: 15816598, buy_n: 9, sell_n: 3, total: 12 }
const DEMO_FOR = { counts: { 무상증자: 1, 자기주식취득: 9, "전환사채(CB)": 2, 유상증자: 1 } }
const DEMO_FLOW = [{ foreign_net: 151302, inst_net: 16724 }]

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
export default function PublicDecisionPanel(props: Props) {
    const { ticker, stockUrl, usStockUrl, usSmallcapUrl, insiderUrl, forensicsUrl, flowUrl, warnUrl, reportPath, discoverPath, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    // 테마 추종 — 사이트 다크모드(body[data-framer-theme]) 따라감. 캔버스는 dark prop 정적.
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!dark : readBodyDark()))
    useEffect(() => {
        if (onCanvas) return
        const read = () => { const t = (typeof document !== "undefined" && document.body) ? document.body.dataset.framerTheme : ""; setThemeDark(t === "dark") }
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])
    const isDark = onCanvas ? !!dark : themeDark
    const C = isDark ? DARK : LIGHT

    const [w, setW] = useState(0)
    const [stock, setStock] = useState<any>(null)
    const [ins, setIns] = useState<any>(null)
    const [foren, setForen] = useState<any>(null)
    const [flow, setFlow] = useState<any[]>([])
    const [warned, setWarned] = useState<boolean>(false)
    const rootRef = useState<HTMLDivElement | null>(null)

    // 검색(통합 TickerPicker) — universe + 내부 선택 state
    const [universe, setUniverse] = useState<any[]>([])
    const [query, setQuery] = useState("")
    const [focused, setFocused] = useState(false)
    const [selTk, setSelTk] = useState<string>(() => {
        if (ticker && ticker.trim()) return ticker.trim()
        if (typeof window !== "undefined") {
            try {
                const q = (new URLSearchParams(window.location.search).get("q") || "").trim()
                if (q) return q
                return (window.localStorage.getItem(LAST_TK_KEY) || "").trim()
            } catch { return "" }
        }
        return ""
    })
    const tk = selTk

    // 검색 universe = 경량 인덱스(universe_search.json ~621KB) — 전 종목 리포트(9.2MB) 로드 제거. 2026-07-08.
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(DEF_UNIVERSE, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null))
            .then((d) => { const a = d && (Array.isArray(d) ? d : d.stocks); if (alive && Array.isArray(a) && a.length) setUniverse(a) })
            .catch(() => {})
        return () => { alive = false }
    }, [onCanvas])

    // ?q= 가 종목명(비 티커)일 때 → 티커로 해석. universe 로드 후 1회 (딥링크 보존, StockReport 와 동일).
    useEffect(() => {
        if (onCanvas || !universe.length) return
        const t = String(tk || "").trim()
        if (!t || universe.some((x) => String(x.ticker).toUpperCase() === t.toUpperCase())) return
        const low = t.toLowerCase()
        const hit = universe.find((x) => String(x.name || "").toLowerCase() === low || String((x as any).name_ko || "") === t)
            || universe.find((x) => String(x.name || "").toLowerCase().includes(low) || String((x as any).name_ko || "").includes(t))
        if (hit) setSelTk(String(hit.ticker))
    }, [universe, tk, onCanvas])

    const matches = useMemo(() => {
        const qq = query.trim().toLowerCase(); if (!qq) return []
        const rk = (x: any) => {
            const t = String(x.ticker || "").toLowerCase(), n = String(x.name || "").toLowerCase(), k = String(x.name_ko || "").toLowerCase()
            return t === qq ? 0 : (n === qq || k === qq) ? 1 : t.indexOf(qq) === 0 ? 2 : (n.indexOf(qq) === 0 || (k && k.indexOf(qq) === 0)) ? 3 : 4
        }
        return universe.filter((x) => String(x.name || "").toLowerCase().includes(qq) || String(x.ticker || "").toLowerCase().includes(qq) || String((x as any).name_ko || "").includes(qq)).sort((a: any, b: any) => rk(a) - rk(b)).slice(0, 10)
    }, [query, universe])

    // 선택 = 내부 state 즉시 갱신 + localStorage·?q 기록 + 이벤트(ThesisNote 추종)
    const pick = (t: string) => {
        const v = String(t || "").trim()
        if (!v) return
        setSelTk(v)
        setQuery("")
        setFocused(false)
        if (onCanvas || typeof window === "undefined") return
        try {
            window.localStorage.setItem(LAST_TK_KEY, v)
            window.history.replaceState(null, "", window.location.pathname + "?q=" + encodeURIComponent(v) + window.location.hash)
            window.dispatchEvent(new Event(TK_EVENT))
        } catch { /* private/quota */ }
    }

    useEffect(() => {
        const el = rootRef[0]
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [rootRef[0]])

    // 종목 상세 = 슬라이스 API 1콜(~11KB) — 전 종목 맵 5개(≈11MB) 로드 대체. 2026-07-08.
    useEffect(() => {
        if (onCanvas || !tk) return
        let alive = true
        const t = String(tk).toUpperCase()
        setStock(null); setIns(null); setForen(null); setFlow([]); setWarned(false)
        fetch(DEF_API + "/api/stock_slice?ticker=" + encodeURIComponent(t))
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive || !d || d.status !== "ok") return
                if (d.report) setStock(d.report)
                setIns(d.insider || null)
                setForen(d.forensics || null)
                setFlow(Array.isArray(d.flow) ? d.flow : [])
                setWarned(!!d.warn)
            })
            .catch(() => {})
        return () => { alive = false }
    }, [tk, onCanvas])

    const s = onCanvas ? DEMO : stock
    const insD = onCanvas ? DEMO_INS : ins
    const forD = onCanvas ? DEMO_FOR : foren
    const flowD = onCanvas ? DEMO_FLOW : flow

    const narrow = w > 0 && w < 620
    const pad = narrow ? 16 : 22

    const model = useMemo(() => {
        if (!s) return null
        const facts = s.facts || {}
        const rows = (s.peer && s.peer.rows) || []
        const rowBy = (k: string) => rows.find((r: any) => r.key === k) || null
        const insNet = insD && insD.net_change != null ? Number(insD.net_change) : null
        const flast = (flowD && flowD.length) ? flowD[flowD.length - 1] : null
        const foreignNet = flast && flast.foreign_net != null ? Number(flast.foreign_net) : null
        const instNet = flast && flast.inst_net != null ? Number(flast.inst_net) : null
        const dil = (() => { const c = (forD && forD.counts) || {}; let n = 0; for (const k of DILUTIVE) n += Number(c[k]) || 0; return n })()

        const risk: { sev: string; text: string }[] = []
        if (warned) risk.push({ sev: "심각", text: "시장경보 — KRX 공식 지정(투자주의/관리 등)" })
        if (dil > 0) risk.push({ sev: "주의", text: `자본조달성 공시 ${dil}회 (유증·CB·BW 누적, 희석 부담)` })
        const debtRow = rowBy("부채비율")
        if (debtRow && debtRow.vs === "above") risk.push({ sev: "주의", text: `부채비율 ${debtRow.value} · 업종 ${debtRow.median} 이상` })

        const bull: string[] = [], bear: string[] = []
        for (const r of rows) {
            const lb = LOWER_BETTER.indexOf(r.key) >= 0
            const good = lb ? r.vs === "below" : r.vs === "above"
            const bad = lb ? r.vs === "above" : r.vs === "below"
            if (good) bull.push(`${r.key} ${r.value} · 업종 ${r.median} ${lb ? "이하" : "이상"}`)
            else if (bad) bear.push(`${r.key} ${r.value} · 업종 ${r.median} ${lb ? "이상" : "이하"}`)
        }
        if (insNet != null && insNet > 0) bull.push(`내부자 순매수 ${fmtShares(insNet)} (DART)`)
        else if (insNet != null && insNet < 0) bear.push(`내부자 순매도 ${fmtShares(insNet)} (DART)`)
        if (foreignNet != null && foreignNet > 0) bull.push(`외국인 순매수 ${fmtShares(foreignNet)} (최근)`)
        else if (foreignNet != null && foreignNet < 0) bear.push(`외국인 순매도 ${fmtShares(foreignNet)} (최근)`)
        if (instNet != null && instNet > 0) bull.push(`기관 순매수 ${fmtShares(instNet)} (최근)`)
        else if (instNet != null && instNet < 0) bear.push(`기관 순매도 ${fmtShares(instNet)} (최근)`)
        if (dil > 0) bear.push(`유증·CB 이력 ${dil}회 (공급 부담)`)
        if (warned) bear.push("시장경보 지정 (KRX)")

        const valRows = VALUE_KEYS.map(rowBy).filter(Boolean)
        const qualRows = QUALITY_KEYS.map(rowBy).filter(Boolean)
        const discN = (() => { const c = (forD && forD.counts) || {}; return Object.values(c).reduce((a: number, b: any) => a + (Number(b) || 0), 0) })()
        const sector = (s.peer && s.peer.sector) || (s.overview && s.overview.sector) || ""
        return { facts, rows, insNet, foreignNet, instNet, dil, risk, bull, bear, valRows, qualRows, discN, sector }
    }, [s, insD, forD, flowD, warned])

    const wrap: CSSProperties = { width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT, padding: pad, boxSizing: "border-box", color: C.ink }
    const setRef = (el: HTMLDivElement | null) => { if (el && rootRef[0] !== el) rootRef[1](el) }

    // 검색창 — 리포트 본문 검색과 동일(토스식 borderless 채움 · 돋보기 · 클리어 × · 드롭다운)
    const inputStyle: CSSProperties = {
        width: "100%", boxSizing: "border-box", border: "none",
        background: C.card, color: C.ink, borderRadius: 12,
        padding: "12px 34px 12px 38px", fontSize: 13.5, fontFamily: FONT, outline: "none",
        WebkitAppearance: "none",
    }
    const searchBar = (
        <div style={{ position: "relative", marginBottom: 18 }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke={C.faint} strokeWidth="2.4" strokeLinecap="round"
                style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}>
                <circle cx="11" cy="11" r="7" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input style={inputStyle} placeholder={`종목 검색 (이름·코드)${universe.length ? ` · 전 종목 ${universe.length}개` : ""}`}
                value={query} onChange={(e) => setQuery(e.target.value)}
                onFocus={() => setFocused(true)} onBlur={() => setTimeout(() => setFocused(false), 150)} />
            {query && (
                <span role="button" tabIndex={0} onMouseDown={(e) => { e.preventDefault(); setQuery("") }}
                    style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)", color: C.faint, fontSize: 15, fontWeight: 700, cursor: "pointer", lineHeight: 1 }}>×</span>
            )}
            {focused && matches.length > 0 && (
                <div style={{ position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 60, background: C.card, borderRadius: 12, boxShadow: "0 10px 30px rgba(0,0,0,0.14)", padding: 6, maxHeight: 320, overflowY: "auto" }}>
                    {matches.map((m) => (
                        <div key={m.ticker} onMouseDown={() => pick(m.ticker)}
                            style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderRadius: 9, cursor: "pointer" }}>
                            <Logo ticker={m.ticker} name={m.name} market={m.market} C={C} size={22} />
                            <span style={{ fontSize: 13.5, fontWeight: 700, color: C.ink }}>{m.name}</span>
                            {m.name_ko && <span style={{ fontSize: 12, color: C.sub, fontWeight: 600 }}>{m.name_ko}</span>}
                            <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginLeft: "auto" }}>{m.ticker} · {m.market}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )

    if (!tk && !onCanvas) {
        return <div ref={setRef} style={wrap}>{searchBar}<div style={{ padding: "28px 18px", textAlign: "center", color: C.faint, fontSize: 13, fontWeight: 600 }}>종목을 검색·선택하면 결정 요약이 나와요.</div></div>
    }
    if (!s || !model) {
        // 토스식 스켈레톤 — 결정 패널 레이아웃(헤더 + 4축 + 강세약세) 모사 + shimmer. 텍스트 "불러오는 중" 대체.
        const skBase = isDark ? "#222a33" : "#e9edf1"
        const skHi = isDark ? "#2d3742" : "#f3f5f7"
        const shim: CSSProperties = { background: skBase, backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`, backgroundSize: "800px 100%", animation: "vsrShimmer 1.4s ease-in-out infinite", borderRadius: 7 }
        const bar = (bw: number | string, bh: number, mt = 0): CSSProperties => ({ ...shim, width: bw, height: bh, marginTop: mt })
        const skCard = () => (
            <div style={{ background: C.card, borderRadius: 14, padding: "15px 17px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                <div style={bar(64, 12)} />
                <div style={bar("82%", 12, 9)} />
                <div style={bar("62%", 12, 7)} />
            </div>
        )
        return (
            <div ref={setRef} style={wrap}>
                {searchBar}
                <style>{`@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                {/* 헤더 스켈레톤 */}
                <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18, paddingLeft: narrow ? 14 : 17 }}>
                    <div style={{ ...shim, width: narrow ? 34 : 40, height: narrow ? 34 : 40, borderRadius: 11 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={bar(132, 17)} />
                        <div style={bar(190, 11, 6)} />
                    </div>
                </div>
                {/* 결정 4축 스켈레톤 */}
                <div style={{ display: "grid", gridTemplateColumns: narrow ? "1fr" : "1fr 1fr", gap: 12 }}>
                    {skCard()}{skCard()}{skCard()}{skCard()}
                </div>
                {/* 강세 ↔ 약세 스켈레톤 */}
                <div style={{ display: "grid", gridTemplateColumns: narrow ? "1fr" : "1fr 1fr", gap: 12, marginTop: 18 }}>
                    {skCard()}{skCard()}
                </div>
            </div>
        )
    }

    const vsArrow = (vs: string) => vs === "above" ? "↑" : vs === "below" ? "↓" : "="
    const vsColor = (key: string, vs: string) => {
        const lb = LOWER_BETTER.indexOf(key) >= 0
        const good = lb ? vs === "below" : vs === "above"
        const bad = lb ? vs === "above" : vs === "below"
        return good ? C.up : bad ? C.down : C.faint
    }
    const sevStyle = (sev: string) => sev === "심각" ? { fg: C.up, bg: C.redS } : sev === "주의" ? { fg: C.amber, bg: C.amberS } : { fg: C.sub, bg: C.bg }
    const goDiscover = (qs: string) => {
        if (onCanvas || typeof window === "undefined") return
        const p = (discoverPath || "/discover").replace(/\/+$/, "") || "/discover"
        window.location.href = p + "?" + qs
    }

    const axisCard = (title: string, sub: string, body: any) => (
        <div style={{ background: C.card, borderRadius: 14, padding: "15px 17px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                <span style={{ fontSize: 13.5, fontWeight: 800, color: C.ink, letterSpacing: "-0.2px" }}>{title}</span>
                <span style={{ fontSize: 10.5, fontWeight: 600, color: C.faint }}>{sub}</span>
            </div>
            <div style={{ marginTop: 8 }}>{body}</div>
        </div>
    )
    const factLine = (r: any) => (
        <div key={r.key} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "4px 0", fontSize: 12.5 }}>
            <span style={{ color: C.sub, fontWeight: 600 }}>{r.key}</span>
            <span style={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                <span style={{ color: C.ink }}>{r.value}</span>
                <span style={{ color: C.faint, fontWeight: 600 }}> · 업종 {r.median} </span>
                <span style={{ color: vsColor(r.key, r.vs), fontWeight: 800 }}>{vsArrow(r.vs)}</span>
            </span>
        </div>
    )
    const flowLine = (label: string, v: number) => (
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, fontWeight: 700 }}>
            <span style={{ color: C.sub, fontWeight: 600 }}>{label}</span>
            <span style={{ color: v > 0 ? C.up : C.down }}>{v > 0 ? "순매수" : "순매도"} {fmtShares(v)}</span>
        </div>
    )
    const linkChip = (label: string, qs: string) => (
        <button key={qs} onClick={() => goDiscover(qs)}
            style={{ border: "none", cursor: "pointer", fontFamily: FONT, background: C.card, color: C.vt, borderRadius: 999, padding: "8px 14px", fontSize: 12, fontWeight: 700, whiteSpace: "nowrap" }}>{label} →</button>
    )

    const m = model
    const noSignal = (m.insNet == null || m.insNet === 0) && (m.foreignNet == null || m.foreignNet === 0) && (m.instNet == null || m.instNet === 0) && m.discN === 0
    const relLinks: any[] = []
    if (m.sector) relLinks.push(linkChip(`동종업계 ${m.sector}`, "sector=" + encodeURIComponent(m.sector)))
    if (m.insNet != null && m.insNet > 0) relLinks.push(linkChip("내부자 순매수 종목", "screen=insider_buy"))
    if (m.foreignNet != null && m.foreignNet > 0) relLinks.push(linkChip("외국인 순매수 종목", "screen=foreign_buy"))
    if (m.dil > 0) relLinks.push(linkChip("유증·CB 이력 종목", "screen=dilution_hist"))

    return (
        <div ref={setRef} style={wrap}>
            {searchBar}

            {/* 헤더 — 리포트와 동일 좌측 인셋(paddingLeft) + 여백 */}
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 18, paddingLeft: narrow ? 14 : 17 }}>
                <Logo ticker={s.ticker} name={s.name} market={s.market} C={C} size={narrow ? 34 : 40} />
                <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 7, flexWrap: "wrap" }}>
                        <span style={{ fontSize: narrow ? 17 : 19, fontWeight: 800, color: C.ink, letterSpacing: "-0.4px" }}>{s.name}</span>
                        <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{s.ticker} · {s.market}</span>
                    </div>
                    <div style={{ fontSize: 11.5, fontWeight: 800, color: C.vt, marginTop: 1 }}>결정 요약 <span style={{ color: C.faint, fontWeight: 600 }}>· 사실을 결정 축으로 · 판단은 본인</span></div>
                </div>
            </div>

            {/* 결정 4축 */}
            <div style={{ display: "grid", gridTemplateColumns: narrow ? "1fr" : "1fr 1fr", gap: 12 }}>
                {axisCard("싼가?", "밸류에이션 · 업종 대비", (
                    m.valRows.length ? m.valRows.map(factLine) : <span style={{ fontSize: 12, color: C.faint, fontWeight: 600 }}>업종 비교 데이터 부족</span>
                ))}
                {axisCard("잘 버나?", "자본효율 · 업종 대비", (
                    m.qualRows.length ? m.qualRows.map(factLine) : <span style={{ fontSize: 12, color: C.faint, fontWeight: 600 }}>업종 비교 데이터 부족</span>
                ))}
                {axisCard("위험한가?", "통합 리스크 점검", (
                    m.risk.length === 0
                        ? <span style={{ fontSize: 12.5, color: C.vg, fontWeight: 700 }}>현재 발행 데이터 기준 표면화된 리스크 플래그 없음</span>
                        : <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                            {m.risk.map((rk, i) => {
                                const st = sevStyle(rk.sev)
                                return (
                                    <div key={i} style={{ display: "flex", gap: 7, alignItems: "flex-start" }}>
                                        <span style={{ flexShrink: 0, fontSize: 10, fontWeight: 800, color: st.fg, background: st.bg, borderRadius: 6, padding: "2px 7px" }}>{rk.sev}</span>
                                        <span style={{ fontSize: 11.5, color: C.sub, fontWeight: 600, lineHeight: 1.4 }}>{rk.text}</span>
                                    </div>
                                )
                            })}
                        </div>
                ))}
                {axisCard("특이한가?", "수급·내부자·공시 신호", (
                    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                        {m.insNet != null && m.insNet !== 0 && flowLine("내부자 (DART)", m.insNet)}
                        {m.foreignNet != null && m.foreignNet !== 0 && flowLine("외국인 (최근)", m.foreignNet)}
                        {m.instNet != null && m.instNet !== 0 && flowLine("기관 (최근)", m.instNet)}
                        {m.discN > 0 && (
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5 }}>
                                <span style={{ color: C.sub, fontWeight: 600 }}>공시 이력 (DART)</span>
                                <span style={{ color: C.ink, fontWeight: 700 }}>누적 {m.discN}건</span>
                            </div>
                        )}
                        {noSignal && <span style={{ fontSize: 12, color: C.faint, fontWeight: 600 }}>특이 수급·신호 없음</span>}
                    </div>
                ))}
            </div>

            {/* 강세 ↔ 약세 긴장 */}
            <div style={{ marginTop: 18 }}>
                <div style={{ fontSize: 12, fontWeight: 800, color: C.faint, padding: "0 2px 8px" }}>강세 ↔ 약세 요인 <span style={{ fontWeight: 600 }}>· 사실이 어느 방향으로 충돌하는지</span></div>
                <div style={{ display: "grid", gridTemplateColumns: narrow ? "1fr" : "1fr 1fr", gap: 12 }}>
                    <div style={{ background: C.card, borderRadius: 14, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 7 }}>
                            <DirArrow up={true} C={C} />
                            <span style={{ fontSize: 12.5, fontWeight: 800, color: C.up }}>강세 요인 <span style={{ color: C.faint, fontWeight: 600, fontSize: 10.5 }}>(일반)</span></span>
                        </div>
                        {m.bull.length ? m.bull.map((t, i) => (
                            <div key={i} style={{ display: "flex", gap: 7, padding: "4px 0", fontSize: 12, color: C.sub, fontWeight: 600, lineHeight: 1.4 }}><span style={{ color: C.up }}>+</span>{t}</div>
                        )) : <span style={{ fontSize: 12, color: C.faint, fontWeight: 600 }}>—</span>}
                    </div>
                    <div style={{ background: C.card, borderRadius: 14, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 7 }}>
                            <DirArrow up={false} C={C} />
                            <span style={{ fontSize: 12.5, fontWeight: 800, color: C.down }}>약세 요인 <span style={{ color: C.faint, fontWeight: 600, fontSize: 10.5 }}>(일반)</span></span>
                        </div>
                        {m.bear.length ? m.bear.map((t, i) => (
                            <div key={i} style={{ display: "flex", gap: 7, padding: "4px 0", fontSize: 12, color: C.sub, fontWeight: 600, lineHeight: 1.4 }}><span style={{ color: C.down }}>−</span>{t}</div>
                        )) : <span style={{ fontSize: 12, color: C.faint, fontWeight: 600 }}>표면화된 약세 사실 없음</span>}
                    </div>
                </div>
            </div>

            {/* 관련 탐색 */}
            {relLinks.length > 0 && (
                <div style={{ marginTop: 18 }}>
                    <div style={{ fontSize: 12, fontWeight: 800, color: C.faint, padding: "0 2px 8px" }}>관련 탐색 <span style={{ fontWeight: 600 }}>· 비슷한 종목으로</span></div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 7 }}>{relLinks}</div>
                </div>
            )}

            <div style={{ textAlign: "center", fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 18, lineHeight: 1.55 }}>
                방향(↑↓/강세·약세)은 <b>교과서적 일반론</b>(저PER=상대적 저렴 등)일 뿐 · 상세 근거는 아래 전체 리포트
            </div>
        </div>
    )
}

addPropertyControls(PublicDecisionPanel, {
    ticker: { type: ControlType.String, title: "Ticker (빈칸=URL ?q=)", defaultValue: "" },
    stockUrl: { type: ControlType.String, title: "Stock URL", defaultValue: DEF_STOCK },
    usStockUrl: { type: ControlType.String, title: "US Stock URL", defaultValue: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_stock_report_public.json" },
    usSmallcapUrl: { type: ControlType.String, title: "US Smallcap URL", defaultValue: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_stock_report_us_smallcap.json" },
    insiderUrl: { type: ControlType.String, title: "Insider URL", defaultValue: DEF_INSIDER },
    forensicsUrl: { type: ControlType.String, title: "Forensics URL", defaultValue: DEF_FORENSICS },
    flowUrl: { type: ControlType.String, title: "Flow URL", defaultValue: DEF_FLOW },
    warnUrl: { type: ControlType.String, title: "Warnings URL", defaultValue: DEF_WARN },
    reportPath: { type: ControlType.String, title: "Report Path", defaultValue: "/stock" },
    discoverPath: { type: ControlType.String, title: "Discover Path", defaultValue: "/discover" },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})
