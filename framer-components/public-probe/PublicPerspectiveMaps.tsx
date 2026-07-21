import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState, type CSSProperties } from "react"
import {
    Factory, Heartbeat, ShieldCheck, UsersThree, Crown, GraduationCap,
    WaveSine, WaveTriangle, WaveSawtooth, TrendUp, HandCoins, TrendDown, CaretDown, Check,
} from "@phosphor-icons/react"

/**
 * 관점 지도 — AlphaNest 탐색. 욕구 · 매출 안정성 · 자사주 3렌즈.
 * 데이터(Blob): perspective_maps.json (분류·집계 사실만).
 *
 * 🚨 재설계(2026-07-12): 비율 지도(C안) — 렌즈 하나 고르면 카테고리가 콘텐츠로 한눈에.
 *   가장 큰 묶음 = 은은한 보라 틴트 히어로, 나머지 = 크기(종목수) 타일. 타일 누르면 그 자리 아래 종목 펼침.
 *   난잡한 3중 선택(분포바+pill줄+정렬토글) 제거. 선택 = 배경색 시프트(외곽선 X, 토스식).
 *   시장(전체/국장/미장)·정렬(규모/이익) = 콤팩트 드롭다운(자리 안 먹음). 아이콘 = Phosphor 라인.
 * 🚨 RULE 7 — 점수·랭킹·추천 0. 분류 기준 공개. 카운트=사실. RULE 6 — LLM narrative 0.
 * 다크모드 자가감지(body[data-framer-theme]). cache-fallback(sessionStorage).
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", violet: "#6c5ce7", violetSoft: "#f0edff", track: "#eef0f3",
    heroBg: "#ece9f8", heroBgSel: "#e0dbf5", tileSel: "#ecedef",
}
const DARK = {
    bg: "#0f1318", card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684",
    line: "#2b2f37", violet: "#a98bff", violetSoft: "#2a2440", track: "#242830",
    heroBg: "#211f2f", heroBgSel: "#292640", tileSel: "#262a33",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DATA_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/perspective_maps.json"
const FLAG = "https://hatscripts.github.io/circle-flags/flags/"
const LIMIT = 15

// 카테고리 key → Phosphor 아이콘 (라인). 히어로=regular · 타일=bold.
const ICON: Record<string, any> = {
    survival: Heartbeat, safety: ShieldCheck, belonging: UsersThree, esteem: Crown, growth: GraduationCap, infra: Factory,
    steady: WaveSine, middle: WaveTriangle, swing: WaveSawtooth,
    steady_buy: TrendUp, some_buy: HandCoins, net_sell: TrendDown,
}

// ── Brandfetch 로고 (logo_map 빌드타임 확정 + 이니셜 폴백) — 타 공개 컴포넌트와 동일 ──
const BF_CID = "1idalDez9T7KlggM8qX"
const BF_MAP_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/logo_map.json"
let __bfMap: Record<string, string> | null = null
let __bfColors: Record<string, string> = {}
let __bfShapes: Record<string, number> = {}
let __bfStyle: any = { padS: 8, padW: 15, wideRatio: 2.2 }
let __bfP: Promise<Record<string, string>> | null = null
function fetchBfMap(): Promise<Record<string, string>> {
    if (__bfMap) return Promise.resolve(__bfMap)
    if (!__bfP) __bfP = fetch(BF_MAP_URL).then((r) => (r.ok ? r.json() : null)).then((d) => { __bfMap = (d && d.logos) || {}; __bfColors = (d && d.colors) || {}; __bfShapes = (d && d.shapes) || {}; __bfStyle = (d && d.style) || __bfStyle; return __bfMap as Record<string, string> }).catch(() => ({} as Record<string, string>))
    return __bfP
}
function useBfLogoMap(): Record<string, string> | null {
    const [m, setM] = useState<Record<string, string> | null>(__bfMap)
    useEffect(() => { let al = true; fetchBfMap().then((mm) => { if (al) setM(mm) }); return () => { al = false } }, [])
    return m
}
function bfLogoPad(ticker: any): string {
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    const r = __bfShapes[tk] || __bfShapes[tk.replace(/\./g, "-")] || 1
    if (r === 0) return "0%"
    return (r > (__bfStyle.wideRatio || 2.2) ? (__bfStyle.padW || 15) : (__bfStyle.padS || 8)) + "%"
}
function bfInitialBg(ticker: any): string {
    let h = 0; const s = String(ticker || "?")
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360
    return "linear-gradient(135deg, hsl(" + h + ",62%,55%), hsl(" + ((h + 42) % 360) + ",68%,42%))"
}
function bfLogoBg(ticker: any): string {
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    const c = __bfColors[tk] || __bfColors[tk.replace(/\./g, "-")]
    const p2 = (__bfMap && (__bfMap[tk] || __bfMap[tk.replace(/\./g, "-")])) || ""
    if (c && p2 && p2.indexOf("http") !== 0 && (__bfStyle.mode || "pastel") === "knockout") return c
    if (!c) return "#ffffff"
    const mix = Number(__bfStyle.mixPct || 30)
    try { if (typeof CSS !== "undefined" && CSS.supports && CSS.supports("color", "color-mix(in srgb, red 50%, white)")) return `color-mix(in srgb, ${c} ${mix}%, #ffffff)` } catch (e2) {}
    return c + (__bfStyle.tintA || "4D")
}
function bfLogoFilter(ticker: any): string {
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    const c = __bfColors[tk] || __bfColors[tk.replace(/\./g, "-")]
    const p2 = (__bfMap && (__bfMap[tk] || __bfMap[tk.replace(/\./g, "-")])) || ""
    return (c && p2 && p2.indexOf("http") !== 0 && (__bfStyle.mode || "pastel") === "knockout") ? "brightness(0) invert(1)" : "none"
}
function bfLogoSrc(ticker: any, lm: Record<string, string> | null, size: number): string {
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    const p = (lm && (lm[tk] || lm[tk.replace(/\./g, "-")])) || ""
    if (!p) return ""
    if (p.indexOf("http") === 0) return p
    return "https://cdn.brandfetch.io/" + p + "?c=" + BF_CID + "&w=" + size * 2 + "&h=" + size * 2
}
function isKR(tk: any): boolean { return /^\d{6}$/.test(String(tk || "")) }

function readBodyDark(): boolean {
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
        if (typeof window !== "undefined" && window.matchMedia) return window.matchMedia("(prefers-color-scheme: dark)").matches
    } catch (e) {}
    return false
}
function fmtAge(iso: any): string {
    if (!iso) return ""
    try {
        const mins = Math.max(0, Math.round((Date.now() - new Date(String(iso)).getTime()) / 60000))
        if (mins < 60) return mins + "분 전"
        const hrs = Math.round(mins / 60)
        if (hrs < 24) return hrs + "시간 전"
        return Math.round(hrs / 24) + "일 전"
    } catch (e) { return "" }
}
function n0(v: any): string { const x = Number(v); return isFinite(x) ? Math.round(x).toLocaleString("en-US") : "—" }
function marginOf(l: any): number | null {
    if (l && l.op_margin != null && isFinite(Number(l.op_margin))) return Number(l.op_margin)
    if (l && l.net_margin != null && isFinite(Number(l.net_margin))) return Number(l.net_margin)
    return null
}
function marginLabel(l: any): string {
    if (l && l.op_margin != null) return "영업 " + l.op_margin + "%"
    if (l && l.net_margin != null) return "순익 " + l.net_margin + "%"
    return ""
}
function metricOf(l: any, sortKey: string): string {
    return sortKey === "profit" ? marginLabel(l) : (l && l.cap_disp ? String(l.cap_disp) : "")
}
function capJo(v: any): string {
    const x = Number(v)
    if (!isFinite(x) || x <= 0) return ""
    return Math.round(x / 1e4).toLocaleString("en-US") + "조"
}
// 카테고리 종목수 (시장 필터 반영) — desire 는 n_kr/n_us, cycle/buyback 은 n + n_kr/n_us
function catCount(c: any, mkt: string): number {
    const kr = Number(c && c.n_kr) || 0, us = Number(c && c.n_us) || 0
    if (mkt === "국장") return kr
    if (mkt === "미장") return us
    const tot = Number(c && c.n)
    return isFinite(tot) && tot > 0 ? tot : kr + us
}
function catLeaders(c: any, mkt: string, sortKey: string): any[] {
    let a = ((c && c.leaders) || []).filter((l: any) => mkt === "전체" || (mkt === "국장" ? l.mkt === "KR" : l.mkt === "US"))
    a = a.slice().sort((x: any, y: any) => sortKey === "profit"
        ? ((marginOf(y) ?? -1e9) - (marginOf(x) ?? -1e9))
        : ((Number(y.cap) || 0) - (Number(x.cap) || 0)))
    return a
}

// 종목 카드 (grid item) — 로고 + 국기 + 이름 + 요약(규모/수익). 로고 실패 시 이니셜.
function StockCard(props: { l: any; C: any; sortKey: string; onGo: (t: string) => void }) {
    const { l, C, sortKey, onGo } = props
    const ticker = String((l && l.ticker) || "")
    const name = (l && l.name) || ""
    const [err, setErr] = useState(false)
    const lm = useBfLogoMap()
    const bfSrc = bfLogoSrc(ticker, lm, 34)
    const kr = isKR(ticker)
    const initial = ((name || "?").trim().charAt(0)) || "?"
    const metric = metricOf(l, sortKey)
    const sector = (l && l.sector) || ""
    return (
        <div onClick={() => onGo(ticker)} role="button" tabIndex={0} title={name + (sector ? " · " + sector : "")}
            style={{ background: C.bg, borderRadius: 12, padding: "11px 6px", boxSizing: "border-box", cursor: "pointer", textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 6, minWidth: 0 }}>
            <div style={{ position: "relative", width: 32, height: 32, flexShrink: 0 }}>
                {!err && bfSrc ? (
                    <img src={bfSrc} alt="" width={32} height={32} loading="lazy" onError={() => setErr(true)}
                        style={{ width: 32, height: 32, borderRadius: 10, filter: bfLogoFilter(ticker), objectFit: "contain", padding: bfLogoPad(ticker), boxSizing: "border-box", display: "block", background: bfLogoBg(ticker) }} />
                ) : (
                    <span style={{ width: 32, height: 32, borderRadius: 10, background: bfInitialBg(ticker), color: "#fff", fontSize: 14, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center" }}>{initial}</span>
                )}
                <img src={FLAG + (kr ? "kr" : "us") + ".svg"} alt="" loading="lazy" decoding="async" width={13} height={13}
                    style={{ position: "absolute", right: -3, bottom: -3, width: 13, height: 13, borderRadius: "50%", border: `1.5px solid ${C.bg}`, background: C.bg, display: "block" }} />
            </div>
            <div style={{ fontSize: 11.5, fontWeight: 700, color: C.ink, lineHeight: 1.25, width: "100%", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{name}</div>
            {metric || sector ? (
                <div style={{ fontSize: 10, fontWeight: 700, color: metric ? C.sub : C.faint, lineHeight: 1.15, width: "100%", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontVariantNumeric: "tabular-nums" }}>{metric || sector}</div>
            ) : null}
        </div>
    )
}

const SAMPLE = {
    _meta: { generated_at: "2026-07-12T13:20:05+09:00" },
    desire: { tiers: [
        { key: "infra", label: "산업 기반", n_kr: 1006, n_us: 900, cap_sum: 840610000, desc: "위 전부를 떠받치는 B2B·부품·장비", leaders: [{ ticker: "005930", name: "삼성전자", mkt: "KR", cap: 5000000, cap_disp: "500조", op_margin: 10.2, sector: "IT" }, { ticker: "NVDA", name: "엔비디아", mkt: "US", cap: 4200000, cap_disp: "$4.2T", net_margin: 55, sector: "반도체" }] },
        { key: "survival", label: "필수·건강", n_kr: 381, n_us: 250, cap_sum: 128520081, desc: "먹고 마시고 아프지 않게 — 유행 안 탐", leaders: [{ ticker: "LLY", name: "일라이릴리", mkt: "US", cap: 982800, cap_disp: "$982.8B", net_margin: 31.7, sector: "제약" }, { ticker: "207940", name: "삼성바이오", mkt: "KR", cap: 658000, cap_disp: "65.8조", op_margin: 3.7, sector: "헬스케어" }] },
        { key: "safety", label: "안전·보장", n_kr: 65, n_us: 231, cap_sum: 119890378, desc: "돈·자산·리스크를 지키는 금융", leaders: [{ ticker: "105560", name: "KB금융", mkt: "KR", cap: 380000, cap_disp: "38조", op_margin: 0, sector: "금융" }] },
        { key: "belonging", label: "관계·연결", n_kr: 93, n_us: 75, cap_sum: 31790000, desc: "사람을 잇는 미디어·통신·플랫폼", leaders: [{ ticker: "035420", name: "NAVER", mkt: "KR", cap: 330000, cap_disp: "33조", op_margin: 15, sector: "인터넷" }] },
        { key: "esteem", label: "프리미엄·품격", n_kr: 43, n_us: 31, cap_sum: 8528711, desc: "과시·품격 소비", leaders: [{ ticker: "005380", name: "현대차", mkt: "KR", cap: 520000, cap_disp: "52조", op_margin: 8, sector: "자동차" }] },
        { key: "growth", label: "성장·교육", n_kr: 10, n_us: 12, cap_sum: 1070171, desc: "배우고 성장하는 수요", leaders: [{ ticker: "NYT", name: "NYT", mkt: "US", cap: 90000, cap_disp: "$9B", net_margin: 12, sector: "미디어" }] },
    ] },
    cycle: { buckets: [
        { key: "steady", label: "매출 꾸준", n: 780, n_kr: 97, n_us: 683, vol_range: [0.1, 7.5], cap_sum: 589411476, desc: "실측 변동성 하위 1/3", leaders: [{ ticker: "AAPL", name: "애플", mkt: "US", cap: 4640000, cap_disp: "$4.64T", net_margin: 27, sector: "IT" }] },
        { key: "middle", label: "중간", n: 780, n_kr: 327, n_us: 453, vol_range: [7.5, 20], cap_sum: 280751212, desc: "변동성 중위 1/3", leaders: [{ ticker: "META", name: "메타", mkt: "US", cap: 1800000, cap_disp: "$1.8T", net_margin: 35, sector: "인터넷" }] },
        { key: "swing", label: "매출 출렁", n: 781, n_kr: 529, n_us: 252, vol_range: [20, 10074], cap_sum: 207723228, desc: "경기·업황에 크게 흔들림", leaders: [{ ticker: "000660", name: "SK하이닉스", mkt: "KR", cap: 1500000, cap_disp: "150조", op_margin: 20.5, sector: "반도체" }] },
    ] },
    buyback: { buckets: [
        { key: "steady_buy", label: "꾸준히 매입", n: 262, n_kr: 262, n_us: 0, cap_sum: 1336875, desc: "취득 공시 2건+ · 취득 > 처분", leaders: [{ ticker: "000270", name: "기아", mkt: "KR", cap: 576000, cap_disp: "57.6조", op_margin: 8, sector: "자동차" }] },
        { key: "net_sell", label: "처분 많음", n: 148, n_kr: 148, n_us: 0, cap_sum: 17019231, desc: "처분 > 취득", leaders: [{ ticker: "005930", name: "삼성전자", mkt: "KR", cap: 5000000, cap_disp: "500조", op_margin: 10.2, sector: "IT" }] },
        { key: "some_buy", label: "가끔 매입", n: 70, n_kr: 70, n_us: 0, cap_sum: 795380, desc: "취득 공시 1건", leaders: [{ ticker: "175330", name: "JB금융지주", mkt: "KR", cap: 30000, cap_disp: "3조", op_margin: 0, sector: "금융" }] },
    ] },
}

export default function PublicPerspectiveMaps(props: { width?: number; dark?: boolean; dataUrl?: string; stockPath?: string }) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (onCanvas ? !!props.dark : readBodyDark()))
    const [data, setData] = useState<any>(onCanvas ? SAMPLE : null)
    const [lens, setLens] = useState<string>("desire")
    const [mkt, setMkt] = useState<string>("전체")
    const [sortKey, setSortKey] = useState<string>("cap")
    const [sel, setSel] = useState<Record<string, string>>({})
    const [ddOpen, setDdOpen] = useState<string>("")
    const [showAll, setShowAll] = useState<boolean>(false)

    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(props.dataUrl || DATA_URL, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (alive && d) { setData(d); try { sessionStorage.setItem("perspective_maps", JSON.stringify(d)) } catch (e) {} } })
            .catch(() => { try { const c = sessionStorage.getItem("perspective_maps"); if (alive && c) setData(JSON.parse(c)) } catch (e) {} })
        return () => { alive = false }
    }, [onCanvas, props.dataUrl])

    useEffect(() => { if (typeof document === "undefined") return; const close = () => setDdOpen(""); document.addEventListener("click", close); return () => document.removeEventListener("click", close) }, [])

    const stockPath = props.stockPath || "/stock"
    const go = (ticker: string) => {
        if (onCanvas || typeof window === "undefined" || !ticker) return
        window.location.href = (stockPath || "/stock").replace(/\/+$/, "") + "?q=" + encodeURIComponent(ticker)
    }

    const wrap: CSSProperties = { width: "100%", background: "transparent", fontFamily: FONT, boxSizing: "border-box", color: C.ink, padding: "0 14px" }

    if (!data) {
        const sk = (w: any, h: number, r = 10): CSSProperties => ({ width: w, height: h, borderRadius: r, background: C.track, animation: "vpmSh 1.4s ease-in-out infinite" })
        return (
            <div style={wrap}>
                <style>{`@keyframes vpmSh{0%,100%{opacity:.55}50%{opacity:1}}`}</style>
                <div style={{ ...sk(120, 20, 6), marginTop: 2 }} />
                <div style={{ display: "flex", gap: 3, marginTop: 12 }}>{[70, 92, 60].map((w, i) => <div key={i} style={sk(w, 36, 10)} />)}</div>
                <div style={{ ...sk("100%", 92, 16), marginTop: 12 }} />
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 9, marginTop: 9 }}>{[0, 1, 2, 3].map((i) => <div key={i} style={sk("100%", 78, 14)} />)}</div>
            </div>
        )
    }

    const meta = data._meta || {}
    const rawCats: any[] = lens === "desire" ? ((data.desire || {}).tiers || [])
        : lens === "cycle" ? ((data.cycle || {}).buckets || [])
            : ((data.buyback || {}).buckets || [])
    // 시장 필터로 종목수 재계산 → 큰 순 정렬 → 비율 지도
    const rows = rawCats.map((c) => ({ c, fc: catCount(c, mkt) })).filter((r) => r.fc > 0).sort((a, b) => b.fc - a.fc)
    const maxFc = Math.max(1, ...rows.map((r) => r.fc))
    const selKey = (sel[lens] && rows.some((r) => r.c.key === sel[lens])) ? sel[lens] : (rows[0] ? rows[0].c.key : "")
    const selRow = rows.find((r) => r.c.key === selKey) || rows[0]
    const hero = rows[0]
    const rest = rows.slice(1)
    const mkTag = mkt !== "전체" ? " · " + mkt : ""

    const lensSub = lens === "desire" ? "인간 욕구 6계층으로 분류 — 탐색 렌즈"
        : lens === "cycle" ? "연간 매출 변동성 3분위 — 안정 ↔ 민감"
            : "자기주식 공시 흐름 — 매입 ↔ 처분"

    const pickCat = (k: string) => { setSel((s) => ({ ...s, [lens]: k })); setShowAll(false) }

    const seg = (v: string, lb: string) => (
        <button key={v} onClick={() => { setLens(v); setShowAll(false) }}
            style={{ flex: 1, border: "none", cursor: "pointer", fontFamily: FONT, padding: "9px 4px", borderRadius: 10, fontSize: 12.5, fontWeight: 800, background: lens === v ? C.card : "transparent", color: lens === v ? C.ink : C.sub, boxShadow: lens === v ? "0 1px 3px rgba(0,0,0,0.06)" : "none" }}>{lb}</button>
    )

    const dd = (key: string, label: string, val: string, opts: { k: string; lb: string }[], set: (k: string) => void) => {
        const on = ddOpen === key
        const cur = opts.find((o) => o.k === val)
        return (
            <div style={{ position: "relative" }} onClick={(e) => e.stopPropagation()}>
                <button onClick={() => setDdOpen(on ? "" : key)}
                    style={{ display: "inline-flex", alignItems: "center", gap: 6, border: "none", background: on ? C.violetSoft : C.card, color: on ? C.violet : C.ink, fontFamily: FONT, fontSize: 12, fontWeight: 700, padding: "8px 11px", borderRadius: 11, cursor: "pointer", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                    <span style={{ color: C.faint, fontWeight: 600 }}>{label}</span>{cur ? cur.lb : val}
                    <CaretDown size={12} weight="bold" color={on ? C.violet : C.faint} style={{ transform: on ? "rotate(180deg)" : "none", transition: "transform .18s" }} />
                </button>
                {on ? (
                    <div style={{ position: "absolute", top: "calc(100% + 5px)", left: 0, zIndex: 30, minWidth: 132, background: C.card, borderRadius: 12, boxShadow: "0 8px 22px rgba(0,0,0,0.18)", padding: 5 }}>
                        {opts.map((o) => {
                            const s = o.k === val
                            return (
                                <button key={o.k} onClick={() => { set(o.k); setDdOpen("") }}
                                    style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%", border: "none", background: s ? C.violetSoft : "transparent", color: s ? C.violet : C.ink, fontFamily: FONT, fontSize: 12.5, fontWeight: 700, padding: "9px 11px", borderRadius: 8, cursor: "pointer", textAlign: "left" }}>
                                    {o.lb}{s ? <Check size={13} weight="bold" color={C.violet} /> : null}
                                </button>
                            )
                        })}
                    </div>
                ) : null}
            </div>
        )
    }

    const catIcon = (key: string, size: number, weight: "regular" | "bold", color: string, style?: CSSProperties) => {
        const Ic = ICON[key]
        return Ic ? <Ic size={size} weight={weight} color={color} style={style} /> : null
    }

    const selLeaders = selRow ? catLeaders(selRow.c, mkt, sortKey) : []
    const shownLeaders = showAll ? selLeaders : selLeaders.slice(0, LIMIT)
    const selCount = selRow ? catCount(selRow.c, mkt) : 0

    return (
        <div style={wrap}>
            <div style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 19, fontWeight: 800, letterSpacing: "-0.4px" }}>관점 지도</div>
                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3, lineHeight: 1.5 }}>
                    같은 시장을 다른 렌즈로 · {lensSub}{meta.generated_at ? " · " + fmtAge(meta.generated_at) + " 갱신" : ""}
                </div>
            </div>

            <div style={{ display: "flex", gap: 3, background: C.track, borderRadius: 13, padding: 3, marginBottom: 12 }}>
                {seg("desire", "욕구")}{seg("cycle", "매출 안정성")}{seg("buyback", "자사주")}
            </div>

            <div style={{ display: "flex", gap: 7, marginBottom: 12 }}>
                {dd("mkt", "시장 ", mkt, [{ k: "전체", lb: "전체" }, { k: "국장", lb: "국장" }, { k: "미장", lb: "미장" }], setMkt)}
                {dd("sort", "정렬 ", sortKey, [{ k: "cap", lb: "규모순" }, { k: "profit", lb: "이익순" }], setSortKey)}
            </div>

            {rows.length === 0 ? (
                <div style={{ background: C.card, borderRadius: 16, padding: "22px 16px", textAlign: "center", color: C.faint, fontSize: 12.5, fontWeight: 600 }}>{mkt}에 해당하는 묶음이 없어요</div>
            ) : (
                <>
                    {hero ? (
                        <div onClick={() => pickCat(hero.c.key)}
                            style={{ position: "relative", overflow: "hidden", borderRadius: 16, padding: 16, marginBottom: 9, cursor: "pointer", background: selKey === hero.c.key ? C.heroBgSel : C.heroBg, transition: "background .15s" }}>
                            <div style={{ position: "absolute", right: 14, top: "50%", transform: "translateY(-50%)", opacity: 0.13 }}>
                                {catIcon(hero.c.key, 82, "regular", C.violet)}
                            </div>
                            <div style={{ fontSize: 16, fontWeight: 800, letterSpacing: "-0.3px" }}>{hero.c.label}</div>
                            <div style={{ fontSize: 27, fontWeight: 800, letterSpacing: "-0.7px", marginTop: 1, color: C.violet, fontVariantNumeric: "tabular-nums" }}>{n0(hero.fc)}<span style={{ fontSize: 13, fontWeight: 700, color: C.faint, marginLeft: 4 }}>종목{mkTag}</span></div>
                            <div style={{ fontSize: 11.5, fontWeight: 600, color: C.sub, marginTop: 3 }}>{hero.c.desc || ""}</div>
                        </div>
                    ) : null}
                    {rest.length ? (
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 9 }}>
                            {rest.map((r) => (
                                <div key={r.c.key} onClick={() => pickCat(r.c.key)}
                                    style={{ borderRadius: 14, background: selKey === r.c.key ? C.tileSel : C.card, boxShadow: "0 1px 3px rgba(0,0,0,0.04)", padding: "13px 14px", cursor: "pointer", display: "flex", flexDirection: "column", gap: 9, transition: "background .15s" }}>
                                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                        <span style={{ width: 28, height: 28, borderRadius: 8, background: C.violetSoft, display: "grid", placeItems: "center", flexShrink: 0 }}>{catIcon(r.c.key, 16, "bold", C.violet)}</span>
                                        <span style={{ fontSize: 13, fontWeight: 800, letterSpacing: "-0.2px", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.c.label}</span>
                                    </div>
                                    <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: "-0.4px", fontVariantNumeric: "tabular-nums" }}>{n0(r.fc)}<span style={{ fontSize: 10, fontWeight: 700, color: C.faint, marginLeft: 3 }}>종목</span></div>
                                    <div style={{ height: 4, borderRadius: 3, background: C.track, overflow: "hidden" }}>
                                        <div style={{ height: "100%", width: Math.round(r.fc / maxFc * 100) + "%", background: C.violet, borderRadius: 3 }} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : null}

                    {selRow ? (
                        <div style={{ marginTop: 14, background: C.card, borderRadius: 16, boxShadow: "0 1px 3px rgba(0,0,0,0.04)", padding: "15px 16px" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                <span style={{ width: 34, height: 34, borderRadius: 10, background: C.violetSoft, display: "grid", placeItems: "center", flexShrink: 0 }}>{catIcon(selRow.c.key, 19, "bold", C.violet)}</span>
                                <div style={{ minWidth: 0 }}>
                                    <div style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-0.3px" }}>{selRow.c.label}</div>
                                    <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 1 }}>정렬 {sortKey === "profit" ? "이익순" : "규모순"}{mkTag}{selRow.c.cap_sum ? " · 규모 " + capJo(selRow.c.cap_sum) : ""}</div>
                                </div>
                                <div style={{ marginLeft: "auto", textAlign: "right", flexShrink: 0 }}>
                                    <div style={{ fontSize: 16, fontWeight: 800, fontVariantNumeric: "tabular-nums" }}>{n0(selCount)}</div>
                                    <div style={{ fontSize: 10, color: C.faint, fontWeight: 700 }}>종목</div>
                                </div>
                            </div>
                            {selRow.c.desc ? <div style={{ fontSize: 12, color: C.sub, fontWeight: 600, marginTop: 9, lineHeight: 1.5 }}>{selRow.c.desc}</div> : null}
                            {shownLeaders.length ? (
                                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(90px, 1fr))", gap: 8, marginTop: 12 }}>
                                    {shownLeaders.map((l: any, i: number) => <StockCard key={(l.ticker || "") + i} l={l} C={C} sortKey={sortKey} onGo={go} />)}
                                </div>
                            ) : (
                                <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, padding: "10px 0" }}>{mkt} 대표 종목 예시 없음</div>
                            )}
                            {selLeaders.length > LIMIT ? (
                                <button onClick={() => setShowAll((v) => !v)}
                                    style={{ width: "100%", marginTop: 10, border: "none", cursor: "pointer", fontFamily: FONT, background: C.bg, color: C.violet, borderRadius: 10, padding: "9px 0", fontSize: 12, fontWeight: 800 }}>
                                    {showAll ? "접기" : `더보기 (${selLeaders.length - LIMIT}개)`}
                                </button>
                            ) : null}
                        </div>
                    ) : null}
                </>
            )}

            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 16, lineHeight: 1.5, textAlign: "center" }}>
                분류 = 탐색용 관점(기준 공개) · 집계 = 공시 사실 · 크기 = 종목수 · 종목은 대표 예시 · 랭킹·점수 아님
            </div>
        </div>
    )
}

addPropertyControls(PublicPerspectiveMaps, {
    width: { type: ControlType.Number, title: "Width", defaultValue: 380 },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
    dataUrl: { type: ControlType.String, title: "Data URL", defaultValue: DATA_URL },
    stockPath: { type: ControlType.String, title: "Stock Path", defaultValue: "/stock" },
})
