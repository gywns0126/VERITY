import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 엣지 히트맵 — VERITY 공개 터미널 (AlphaNest). 토스/Finviz 가 못 가진 "우리 사실"로 칠한 시장 한눈 뷰.
 *
 * 🚨 차별점: 색 = 가격%(흔함)가 아니라 우리 고유 사실 — 내부자 순매수(DART) / 외국인 수급(네이버 5일) / 희석 공시 빈도(유증·CB).
 *   "어느 섹터에 내부자·외국인 돈이 도나"를 한눈에. 토스 구조적 불가 영역(Discovery 와 동일 해자, 시각화 표면).
 * 박스 크기 = 시가총액. 섹터 그룹. 클릭 → 종목 리포트(reportPath?q=ticker). 줌(+/−·더블클릭·드래그) = 좌표만 확대(글자 고정).
 *
 * RULE 7: 자체 점수·등급·verdict 0. 색·크기 = 발행된 사실(시총·내부자·수급·공시)만.
 * 🚨 시세 재배포 컴플라이언스(2026-07-02): public_price_snapshot(당일 등락률%) 소비 제거 — 색 지표는 우리 고유 사실(내부자·외국인·희석)만.
 * 데이터 = stock_report_public(시총·섹터) + insider_trades + stock_flow_5d + disclosure_forensics. 전부 Blob, 신규 파이프라인 0.
 * 레이아웃 = squarified treemap(순수 JS, 외부 lib 0). 반응형 ResizeObserver. 테마 = body[data-framer-theme] 추종.
 *   onAccent = 보라(vg) 위 글자색(라이트 흰/다크 짙음).
 * 로딩 = 토스식 스켈레톤(트리맵 모양 회색 패치워크 + shimmer).
 * 🚨 호버 카드 = overflow:hidden 클립 *밖*(외곽 div 자식)에서 렌더 — 하단/모서리 타일서 잘림 방지(2026-06-23 fix). 행 nowrap+말줄임으로 높이 예측.
 * 🚨 타일 호버(2026-06-23) = 효과 0(lift·그림자·외곽선 없음). 마우스 올리면 색만 살짝 진하게(알파 +0.16).
 * 🚨 면책 문구 제거(2026-06-26, PM) — "점수·등급·추천 아님(2027 검증)" 류는 사이트 하단 단일 면책으로 통합. 색=사실·박스=시총 설명은 유지.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", up: "#f04452", down: "#3182f6", amber: "#ff9500",
    vg: "#6c5ce7", vgS: "#f0edff", vt: "#6c5ce7", neutral: "#e9edf1", neutralHover: "#dde2e7", onAccent: "#ffffff", tileInk: "#ffffff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", up: "#f04452", down: "#5b9bff", amber: "#ffb454",
    vg: "#a99bff", vgS: "#241f3a", vt: "#a99bff", neutral: "#222a33", neutralHover: "#2b3440", onAccent: "#0f1318", tileInk: "#ffffff",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

// ── Brandfetch 로고 (토스 핫링킹 제거 2026-07-10) — logo_map(빌드타임 확정) + US 티커 규칙 + 이니셜 폴백 ──
const BF_CID = "1idalDez9T7KlggM8qX"  // 공개 임베드 client id (Logo Link 전용)
const BF_MAP_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/logo_map.json"
let __bfMap: Record<string, string> | null = null
let __bfColors: Record<string, string> = {}
let __bfShapes: Record<string, number> = {}
let __bfStyle: any = { padS: 8, padW: 15, wideRatio: 2.2 }  // 발행 데이터(style)로 조절 — 코드 수정 불요
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
    // 모양 적응 패딩 — 심볼(정사각)은 크게, 워드마크(가로 김)는 여백 확보 (토스식 가시성)
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    const r = __bfShapes[tk] || __bfShapes[tk.replace(/\./g, "-")] || 1
    return (r > (__bfStyle.wideRatio || 2.2) ? (__bfStyle.padW || 15) : (__bfStyle.padS || 8)) + "%"
}
function bfInitialBg(ticker: any): string {
    // 이니셜 타일 — 티커 해시 투톤 그라데이션 (미보유 4.6K 도 디자인 자산화, 종목별 고정색)
    let h = 0; const s = String(ticker || "?")
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360
    return "linear-gradient(135deg, hsl(" + h + ",62%,55%), hsl(" + ((h + 42) % 360) + ",68%,42%))"
}
function bfLogoBg(ticker: any): string {
    // 아이덴티티 색 틴트 타일 (토스식 참조 — 색은 로고 대표색/공식 브랜드색, 자산 복사 아님)
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    const c = __bfColors[tk] || __bfColors[tk.replace(/\./g, "-")]
    // 토스식 넉아웃 (기본): 브랜드색 솔리드 배경 + 로고 흰 실루엣(bfLogoFilter). 조건 미충족 = 솔리드 파스텔.
    // style.mode 노브: "knockout"(기본) | "pastel". mixPct = 파스텔 혼합비(기본 30).
    const p2 = (__bfMap && (__bfMap[tk] || __bfMap[tk.replace(/\./g, "-")])) || ""
    if (c && p2 && p2.indexOf("http") !== 0 && (__bfStyle.mode || "knockout") === "knockout") return c  // 솔리드 브랜드색
    if (!c) return "#ffffff"
    const mix = Number(__bfStyle.mixPct || 30)
    try { if (typeof CSS !== "undefined" && CSS.supports && CSS.supports("color", "color-mix(in srgb, red 50%, white)")) return `color-mix(in srgb, ${c} ${mix}%, #ffffff)` } catch (e2) {}
    return c + (__bfStyle.tintA || "4D")
}
function bfLogoFilter(ticker: any): string {
    // 넉아웃 조건과 동일할 때만 흰 실루엣 (Brandfetch 투명 로고 한정 — 파비콘류는 불투명이라 제외)
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    const c = __bfColors[tk] || __bfColors[tk.replace(/\./g, "-")]
    const p2 = (__bfMap && (__bfMap[tk] || __bfMap[tk.replace(/\./g, "-")])) || ""
    return (c && p2 && p2.indexOf("http") !== 0 && (__bfStyle.mode || "knockout") === "knockout") ? "brightness(0) invert(1)" : "none"
}
function bfLogoSrc(ticker: any, lm: Record<string, string> | null, size: number): string {
    const tk = String(ticker || "").toUpperCase().replace(/-/g, ".")
    const p = (lm && (lm[tk] || lm[tk.replace(/\./g, "-")])) || ""  // 맵 전용 — 미검증 경로 = B 플레이스홀더 위험(2026-07-10)
    if (!p) return ""
    if (p.indexOf("http") === 0) return p  // 폴백 소스(nvstly·공식 파비콘) = 절대 URL 그대로
    return "https://cdn.brandfetch.io/" + p + "?c=" + BF_CID + "&w=" + size * 2 + "&h=" + size * 2
}

const DEFAULT_STOCK = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_report_public.json"
const DEFAULT_INSIDER = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/insider_trades.json"
const DEFAULT_FLOW = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_flow_5d.json"
const DEFAULT_FORENSICS = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/disclosure_forensics.json"
const DEFAULT_REPORT = "/stock"

type MetricKey = "insider" | "flow" | "dilution"
interface Metric {
    key: MetricKey
    tab: string
    diverging: boolean        // true = 양/음(빨강/파랑), false = 단방향(앰버)
    posLabel: string
    negLabel: string
    desc: string
}
const METRICS: Metric[] = [
    { key: "insider", tab: "내부자", diverging: true, posLabel: "순매수", negLabel: "순매도", desc: "내부자 순매수 · DART" },
    { key: "flow", tab: "외국인", diverging: true, posLabel: "순매수", negLabel: "순매도", desc: "외국인 5일 · 네이버" },
    { key: "dilution", tab: "희석공시", diverging: false, posLabel: "유증·CB 多", negLabel: "", desc: "유증·CB 빈도 · DART" },
]

interface Props {
    stockUrl: string
    insiderUrl: string
    flowUrl: string
    forensicsUrl: string
    reportPath: string
    topN: number
    dark: boolean
}

function num(s: any): number | null {
    if (s == null) return null
    const m = String(s).match(/-?[\d,]+\.?\d*/)
    return m ? parseFloat(m[0].replace(/,/g, "")) : null
}
// 시가총액 문자열("16.3조"/"936억") → 억 단위 숫자
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
function sectorOf(s: any): string {
    return (s.peer && s.peer.sector) || (s.overview && s.overview.sector) || "기타"
}
function capLabel(eok: number): string {
    if (!isFinite(eok) || eok <= 0) return "—"
    if (eok >= 10000) return (eok / 10000).toFixed(1) + "조"
    return Math.round(eok).toLocaleString("en-US") + "억"
}
function fmtShares(v: any): string {
    const x = Number(v)
    if (!isFinite(x) || x === 0) return "0"
    const a = Math.abs(x), sign = x > 0 ? "+" : "−"
    if (a >= 1e8) return sign + (a / 1e8).toFixed(1) + "억"
    if (a >= 1e4) return sign + Math.round(a / 1e4).toLocaleString("en-US") + "만"
    return sign + Math.round(a).toLocaleString("en-US")
}
function fmtAge(iso: any): string {
    if (!iso) return ""
    try {
        const mins = Math.max(0, Math.round((Date.now() - new Date(String(iso)).getTime()) / 60000))
        if (mins < 60) return mins + "분 전"
        const hrs = Math.round(mins / 60)
        if (hrs < 24) return hrs + "시간 전"
        return Math.round(hrs / 24) + "일 전"
    } catch (e) {
        return ""
    }
}

/* ── squarified treemap (순수 JS) ── items:[{key,value}] → [{key,x,y,w,h,item}] ── */
function worst(row: any[], side: number, sum: number): number {
    let mx = 0, mn = Infinity
    for (const it of row) { if (it.area > mx) mx = it.area; if (it.area < mn) mn = it.area }
    const s2 = sum * sum, w2 = side * side
    if (s2 === 0 || mn === 0) return Infinity
    return Math.max((w2 * mx) / s2, s2 / (w2 * mn))
}
function squarify(items: any[], X: number, Y: number, W: number, H: number): any[] {
    const out: any[] = []
    if (W <= 0 || H <= 0 || items.length === 0) return out
    const total = items.reduce((a, b) => a + (b.value > 0 ? b.value : 0), 0)
    if (total <= 0) return out
    const scale = (W * H) / total
    const scaled = items.map((it) => ({ ...it, area: Math.max(0.0001, (it.value > 0 ? it.value : 0) * scale) }))
    let x = X, y = Y, w = W, h = H, i = 0
    while (i < scaled.length) {
        const side = Math.min(w, h)
        if (side <= 0) break
        let row = [scaled[i]]
        let rowArea = scaled[i].area
        let j = i + 1
        while (j < scaled.length) {
            const cand = row.concat(scaled[j])
            const candArea = rowArea + scaled[j].area
            if (worst(cand, side, candArea) <= worst(row, side, rowArea)) {
                row = cand; rowArea = candArea; j++
            } else break
        }
        const thick = rowArea / side
        if (w <= h) {
            let cx = x
            for (const it of row) {
                const tw = it.area / thick
                out.push({ key: it.key, x: cx, y: y, w: tw, h: thick, item: it })
                cx += tw
            }
            y += thick; h -= thick
        } else {
            let cy = y
            for (const it of row) {
                const th = it.area / thick
                out.push({ key: it.key, x: x, y: cy, w: thick, h: th, item: it })
                cy += th
            }
            x += thick; w -= thick
        }
        i = j
    }
    return out
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

export default function PublicHeatmap(props: Props) {
    const __lmH = useBfLogoMap()
    const { stockUrl, insiderUrl, flowUrl, forensicsUrl, reportPath, topN, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [stocks, setStocks] = useState<any[]>([])
    const [asOf, setAsOf] = useState<string>("")
    const [insiderMap, setInsiderMap] = useState<Record<string, any>>({})
    const [flowMap, setFlowMap] = useState<Record<string, any[]>>({})
    const [forenMap, setForenMap] = useState<Record<string, any>>({})
    const [metric, setMetric] = useState<MetricKey>("insider")
    const [hover, setHover] = useState<any>(null)
    const [zoom, setZoom] = useState<{ z: number; tx: number; ty: number }>({ z: 1, tx: 0, ty: 0 })
    const dragRef = useRef<{ on: boolean; x: number; y: number; tx: number; ty: number; moved: boolean }>({ on: false, x: 0, y: 0, tx: 0, ty: 0, moved: false })
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!dark : readBodyDark()))

    const C = (onCanvas ? !!dark : themeDark) ? DARK : LIGHT
    const isDark = C === DARK

    /* 테마 추종 */
    useEffect(() => {
        if (onCanvas) return
        const read = () => {
            const t = (typeof document !== "undefined" && document.body) ? document.body.dataset.framerTheme : ""
            setThemeDark(t === "dark")
        }
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    const SAMPLE = useMemo(() => buildSample(), [])

    useEffect(() => {
        if (onCanvas) { setStocks(SAMPLE.stocks); setInsiderMap(SAMPLE.insider); setFlowMap(SAMPLE.flow); setForenMap(SAMPLE.foren); return }
        let alive = true
        const jget = (url: string, ok: (d: any) => void) => {
            if (!url) return
            fetch(url, { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).then((d) => { if (alive && d) ok(d) }).catch(() => {})
        }
        jget(stockUrl, (d) => {
            const a = Array.isArray(d) ? d : d.stocks; if (Array.isArray(a)) setStocks(a)
            const ts = d && d._meta && d._meta.generated_at; if (ts) setAsOf(String(ts))
        })
        jget(insiderUrl, (d) => {
            const a = Array.isArray(d) ? d : d.stocks
            if (!Array.isArray(a)) return
            const m: Record<string, any> = {}; for (const x of a) if (x && x.ticker) m[String(x.ticker)] = x; setInsiderMap(m)
        })
        jget(flowUrl, (d) => { const fm = d.flows || d; if (fm && typeof fm === "object") setFlowMap(fm) })
        jget(forensicsUrl, (d) => {
            const a = Array.isArray(d) ? d : d.stocks
            if (!Array.isArray(a)) return
            const m: Record<string, any> = {}; for (const x of a) if (x && x.ticker) m[String(x.ticker)] = x; setForenMap(m)
        })
        return () => { alive = false }
    }, [stockUrl, insiderUrl, flowUrl, forensicsUrl, onCanvas, SAMPLE])

    const metricsShown = METRICS
    const activeMetric = useMemo(() => METRICS.find((m) => m.key === metric) || METRICS[0], [metric])

    const narrow = w > 0 && w < 560
    const pad = narrow ? 11 : 15
    const cap = Math.max(40, Math.min(260, topN || 160))
    const chartW = Math.max(240, w)
    const chartH = narrow ? 540 : 600

    // 지표값 추출
    const metricVal = (ticker: string): number | null => {
        if (metric === "insider") { const e = insiderMap[ticker]; const v = e && Number(e.net_change); return isFinite(v as number) && v !== 0 ? (v as number) : null }
        if (metric === "flow") { const f = flowMap[ticker]; if (f && f.length) { const v = Number(f[f.length - 1].foreign_net); return isFinite(v) && v !== 0 ? v : null } return null }
        if (metric === "dilution") { const fo = forenMap[ticker]; const v = fo && Number(fo.dilution_count); return isFinite(v as number) && (v as number) > 0 ? (v as number) : null }
        return null
    }

    // 상위 N(시총) → 섹터 그룹 → 트리맵
    const layout = useMemo(() => {
        const uni = stocks
            .map((s) => ({ s, ticker: String(s.ticker || ""), name: s.name || s.ticker, sector: sectorOf(s), cap: parseCap((s.facts || {})["시가총액"]) || 0 }))
            .filter((x) => x.ticker && x.cap > 0)
            .sort((a, b) => b.cap - a.cap)
            .slice(0, cap)
        if (!uni.length) return { tiles: [], sectors: [], scaleCap: 1 }
        // 섹터 묶음
        const bySec: Record<string, any[]> = {}
        for (const x of uni) { (bySec[x.sector] = bySec[x.sector] || []).push(x) }
        const sectorItems = Object.keys(bySec).map((name) => ({ key: name, value: bySec[name].reduce((a, b) => a + b.cap, 0), members: bySec[name] }))
            .sort((a, b) => b.value - a.value)
        const TP = 10
        const secRects = squarify(sectorItems, TP, TP, chartW - TP * 2, chartH - TP * 2)
        const tiles: any[] = []
        const sectors: any[] = []
        for (const sr of secRects) {
            sectors.push({ name: sr.key, x: sr.x, y: sr.y, w: sr.w, h: sr.h })
            const SG = narrow ? 4 : 5
            if (sr.h - SG * 2 < 6 || sr.w - SG * 2 < 6) continue
            const mem = sr.item.members.map((m: any) => ({ key: m.ticker, value: m.cap, m }))
            const leaves = squarify(mem, sr.x + SG, sr.y + SG, sr.w - SG * 2, sr.h - SG * 2)
            for (const lf of leaves) tiles.push({ ...lf, m: lf.item.m, sector: sr.key })
        }
        return { tiles, sectors, scaleCap: 1 }
    }, [stocks, cap, chartW, chartH, narrow])

    // 색 정규화 — 표시 타일들의 |값| 90퍼센타일을 척도 상한으로(이상치 1개가 화면 지배 방지)
    const scaleCap = useMemo(() => {
        const vals: number[] = []
        for (const t of layout.tiles) { const v = metricVal(t.m.ticker); if (v != null) vals.push(Math.abs(v)) }
        if (!vals.length) return 1
        vals.sort((a, b) => a - b)
        const p90 = vals[Math.min(vals.length - 1, Math.floor(vals.length * 0.9))]
        return p90 > 0 ? p90 : (vals[vals.length - 1] || 1)
    }, [layout.tiles, metric, insiderMap, flowMap, forenMap])

    // 색 — 호버 시 알파 +0.16(색만 살짝 진하게). 효과(lift/그림자/외곽선) 0.
    const tileColor = (v: number | null): { bg: string; bgHover: string; strong: boolean; strongHover: boolean } => {
        if (v == null) return { bg: C.neutral, bgHover: C.neutralHover, strong: false, strongHover: false }
        const inten = Math.max(0, Math.min(1, Math.abs(v) / scaleCap))
        const a = 0.16 + inten * 0.76
        const aH = Math.min(1, a + 0.16)
        let base = C.up
        if (activeMetric.diverging) base = v >= 0 ? C.up : C.down
        else base = C.amber
        return { bg: hexA(base, a), bgHover: hexA(base, aH), strong: a >= 0.5, strongHover: aH >= 0.5 }
    }

    const go = (ticker: string) => {
        if (onCanvas || typeof window === "undefined" || !ticker) return
        const p = (reportPath || DEFAULT_REPORT).replace(/\/+$/, "") || "/"
        window.location.href = p + "?q=" + encodeURIComponent(ticker)
    }

    const clampPan = (z: number, tx: number, ty: number) => {
        const minX = Math.min(0, chartW - chartW * z), minY = Math.min(0, chartH - chartH * z)
        return { tx: Math.max(minX, Math.min(0, tx)), ty: Math.max(minY, Math.min(0, ty)) }
    }
    const zoomAt = (factor: number, cx: number, cy: number) => {
        setZoom((st) => {
            const nz = Math.max(1, Math.min(4.5, st.z * factor))
            const px = (cx - st.tx) / st.z, py = (cy - st.ty) / st.z
            const c = clampPan(nz, cx - px * nz, cy - py * nz)
            return { z: nz, tx: c.tx, ty: c.ty }
        })
    }
    const resetZoom = () => setZoom({ z: 1, tx: 0, ty: 0 })

    const wrap: CSSProperties = {
        width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT, padding: pad, boxSizing: "border-box", color: C.ink,
    }
    const tabBtn = (m: Metric): CSSProperties => {
        const active = m.key === metric
        return {
            border: "none", cursor: "pointer", fontFamily: FONT, padding: narrow ? "7px 11px" : "8px 14px",
            borderRadius: 999, fontSize: narrow ? 12 : 13, fontWeight: 800, flexShrink: 0,
            background: active ? C.vg : C.card, color: active ? C.onAccent : C.sub,
            boxShadow: active ? "none" : "0 1px 2px rgba(0,0,0,0.05)",
        }
    }
    const zoomBtnStyle: CSSProperties = { width: 26, height: 26, borderRadius: 7, border: "none", cursor: "pointer", background: C.card, color: C.sub, fontSize: 15, fontWeight: 800, fontFamily: FONT, boxShadow: "0 1px 3px rgba(0,0,0,0.18)", lineHeight: 1, display: "flex", alignItems: "center", justifyContent: "center" }

    // 범례 색 칩
    const legend = () => {
        const steps = activeMetric.diverging
            ? [{ v: -1, l: activeMetric.negLabel }, { v: -0.4, l: "" }, { v: 0, l: "" }, { v: 0.4, l: "" }, { v: 1, l: activeMetric.posLabel }]
            : [{ v: 0.1, l: "적음" }, { v: 0.4, l: "" }, { v: 0.7, l: "" }, { v: 1, l: activeMetric.posLabel }]
        return (
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <span style={{ fontSize: 11, color: C.faint, fontWeight: 700 }}>{activeMetric.desc}</span>
                <div style={{ display: "flex", alignItems: "center", gap: 2 }}>
                    {steps.map((st, i) => {
                        const col = tileColor(st.v === 0 ? null : st.v * scaleCap)
                        return (
                            <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                                <span style={{ width: 16, height: 11, borderRadius: 3, background: st.v === 0 ? C.neutral : col.bg, border: `1px solid ${C.line}` }} />
                                {st.l && <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 700 }}>{st.l}</span>}
                            </span>
                        )
                    })}
                </div>
            </div>
        )
    }

    // 로딩 스켈레톤 — 트리맵 모양 회색 패치워크 + shimmer (토스식)
    const skBase = isDark ? "#222a33" : "#e9edf1"
    const skHi = isDark ? "#2d3742" : "#f3f5f7"
    const SKEL_W = [34, 22, 22, 14, 30, 16, 18, 12, 24, 16, 14, 10, 20, 12, 16, 10, 14, 22, 12, 16]

    // 호버 카드 위치 — 클립 밖 외곽 div 기준(타일 좌표와 동일). 우/좌 플립 + 상/하 클램프(하단 근처면 위로).
    const hoverCardPos = () => {
        const hx = hover.x * zoom.z + zoom.tx, hy = hover.y * zoom.z + zoom.ty, hw = hover.w * zoom.z, hh = hover.h * zoom.z
        const CW = 190, CH = 132, G = 8
        let cl = hx + hw + G
        if (cl + CW > chartW - 6) cl = hx - G - CW
        if (cl < 6) cl = Math.min(Math.max(6, hx + hw / 2 - CW / 2), chartW - CW - 6)
        let ct = hy + hh / 2 - CH / 2
        if (ct + CH > chartH - 6) ct = chartH - CH - 6   // 하단 넘치면 위로 밀기
        if (ct < 6) ct = 6
        return { cl, ct, CW }
    }

    return (
        <div ref={rootRef} style={wrap}>
            {/* 헤더 */}
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 10, flexWrap: "wrap", marginBottom: 8 }}>
                <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: narrow ? 18 : 20, fontWeight: 800, letterSpacing: "-0.5px" }}>엣지 히트맵</div>
                    <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, marginTop: 3 }}>
                        박스=시총 · 색=아래 지표 · 탭→리포트{asOf ? " · 데이터 " + fmtAge(asOf) : ""}
                    </div>
                </div>
            </div>

            {/* 지표 토글 */}
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
                {metricsShown.map((m) => (
                    <button key={m.key} onClick={() => setMetric(m.key)} style={tabBtn(m)}>{m.tab}</button>
                ))}
            </div>

            {/* 범례 */}
            <div style={{ marginBottom: 8 }}>{legend()}</div>

            {/* 트리맵 외곽 (클립 X — 호버 카드가 잘리지 않도록) */}
            <div style={{ position: "relative", width: "100%", height: chartH }}>
                {/* 타일 클립 레이어 (overflow hidden = 줌/팬 타일만 가둠) */}
                <div style={{ position: "absolute", inset: 0, borderRadius: 14, overflow: "hidden", background: C.card, cursor: zoom.z > 1 ? "grab" : "default", touchAction: zoom.z > 1 ? "none" : "auto" }}
                    onMouseLeave={() => { setHover(null); dragRef.current.on = false }}
                    onDoubleClick={(e) => { const r = (e.currentTarget as HTMLElement).getBoundingClientRect(); zoomAt(1.7, e.clientX - r.left, e.clientY - r.top) }}
                    onMouseDown={(e) => { dragRef.current.moved = false; if (zoom.z <= 1) return; dragRef.current = { on: true, x: e.clientX, y: e.clientY, tx: zoom.tx, ty: zoom.ty, moved: false } }}
                    onMouseMove={(e) => { const d = dragRef.current; if (!d.on) return; const dx = e.clientX - d.x, dy = e.clientY - d.y; if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true; const c = clampPan(zoom.z, d.tx + dx, d.ty + dy); setZoom((st) => ({ ...st, tx: c.tx, ty: c.ty })) }}
                    onMouseUp={() => { dragRef.current.on = false }}
                    onTouchStart={(e) => { dragRef.current.moved = false; if (zoom.z <= 1 || !e.touches[0]) return; dragRef.current = { on: true, x: e.touches[0].clientX, y: e.touches[0].clientY, tx: zoom.tx, ty: zoom.ty, moved: false } }}
                    onTouchMove={(e) => { const d = dragRef.current; if (!d.on || !e.touches[0]) return; const dx = e.touches[0].clientX - d.x, dy = e.touches[0].clientY - d.y; if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true; const c = clampPan(zoom.z, d.tx + dx, d.ty + dy); setZoom((st) => ({ ...st, tx: c.tx, ty: c.ty })) }}
                    onTouchEnd={() => { dragRef.current.on = false }}>
                    {layout.tiles.length === 0 ? (
                        <div style={{ position: "absolute", inset: 8, display: "flex", flexWrap: "wrap", gap: 6, alignContent: "flex-start", overflow: "hidden" }}>
                            <style>{`@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                            {SKEL_W.map((wp, i) => (
                                <div key={i} style={{ width: `calc(${wp}% - 6px)`, height: 70 + ((i * 41) % 110), borderRadius: 4, background: skBase, backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`, backgroundSize: "800px 100%", animation: "vsrShimmer 1.4s ease-in-out infinite" }} />
                            ))}
                        </div>
                    ) : (
                        <>
                            {/* 섹터 프레임 (구분 박스) */}
                            {layout.sectors.map((s, i) => {
                                const sx = s.x * zoom.z + zoom.tx, sy = s.y * zoom.z + zoom.ty, sw = s.w * zoom.z, sh = s.h * zoom.z
                                return sw > 8 && sh > 8 ? (
                                    <div key={"sf" + i} style={{ position: "absolute", left: sx + 2, top: sy + 2, width: Math.max(0, sw - 4), height: Math.max(0, sh - 4), border: `1px solid ${isDark ? "rgba(255,255,255,0.15)" : "rgba(0,0,0,0.13)"}`, borderRadius: 8, boxSizing: "border-box", pointerEvents: "none", zIndex: 6 }} />
                                ) : null
                            })}
                            {/* 섹터 라벨 */}
                            {layout.sectors.map((s, i) => {
                                const sx = s.x * zoom.z + zoom.tx, sy = s.y * zoom.z + zoom.ty, sw = s.w * zoom.z, sh = s.h * zoom.z
                                return sw > 50 && sh > 22 ? (
                                    <div key={"sec" + i} style={{ position: "absolute", left: sx + 4, top: sy + 4, maxWidth: sw - 8, fontSize: narrow ? 9.5 : 10.5, fontWeight: 800, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", pointerEvents: "none", letterSpacing: "-0.2px", background: isDark ? "rgba(23,28,35,0.72)" : "rgba(255,255,255,0.78)", padding: "1px 5px", borderRadius: 5, zIndex: 8 }}>{s.name}</div>
                                ) : null
                            })}
                            {/* 타일 */}
                            {layout.tiles.map((t) => {
                                const tx = t.x * zoom.z + zoom.tx, ty = t.y * zoom.z + zoom.ty, tw = t.w * zoom.z, th = t.h * zoom.z
                                const v = metricVal(t.m.ticker)
                                const col = tileColor(v)
                                const big = tw > 44 && th > 28
                                const isHover = !!hover && hover.key === t.key
                                const txt = (isHover ? col.strongHover : col.strong) ? C.tileInk : C.ink
                                return (
                                    <div key={t.key}
                                        onClick={() => { if (!dragRef.current.moved) go(t.m.ticker) }}
                                        onMouseEnter={() => setHover({ ...t, v })}
                                        role="button" tabIndex={0}
                                        style={{
                                            position: "absolute", left: tx, top: ty, width: Math.max(0, tw - 1.5), height: Math.max(0, th - 1.5),
                                            background: isHover ? col.bgHover : col.bg, borderRadius: 3, cursor: "pointer", overflow: "hidden",
                                            display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center",
                                            padding: 2, boxSizing: "border-box", border: `1px solid ${isDark ? "rgba(0,0,0,0.25)" : "rgba(255,255,255,0.35)"}`,
                                            // 호버 = 효과 없이 색만 살짝 진하게(알파 ↑). lift·그림자·외곽선 0.
                                            transition: "background 110ms ease",
                                            zIndex: 1,
                                        }}>
                                        {big && (
                                            <>
                                                {tw > 52 && th > 50 && bfLogoSrc(t.m.ticker, __lmH, 16) ? (<img src={bfLogoSrc(t.m.ticker, __lmH, 16)} alt="" width={16} height={16} onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none" }} style={{ width: 16, height: 16, borderRadius: 5, marginBottom: 2, filter: bfLogoFilter(t.m.ticker), objectFit: "contain", padding: bfLogoPad(t.m.ticker), boxSizing: "border-box", display: "block", background: bfLogoBg(t.m.ticker) }} />) : null}
                                                <span style={{ fontSize: tw > 130 ? 13 : tw > 80 ? 12 : 10.5, fontWeight: 800, color: txt, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: "100%", letterSpacing: "-0.3px", textShadow: col.strong ? "0 1px 2px rgba(0,0,0,0.35)" : "none" }}>{t.m.name}</span>
                                                {th > 42 && <span style={{ fontSize: 10.5, fontWeight: 700, color: txt, opacity: 0.92, marginTop: 1, textShadow: col.strong ? "0 1px 2px rgba(0,0,0,0.3)" : "none" }}>{tileValLabel(metric, v)}</span>}
                                            </>
                                        )}
                                    </div>
                                )
                            })}
                            {/* 줌 컨트롤 */}
                            <div style={{ position: "absolute", top: 8, right: 8, display: "flex", flexDirection: "column", gap: 4, zIndex: 18 }}>
                                <button onMouseDown={(e) => e.stopPropagation()} onClick={() => zoomAt(1.5, chartW / 2, chartH / 2)} style={zoomBtnStyle}>+</button>
                                <button onMouseDown={(e) => e.stopPropagation()} onClick={() => zoomAt(1 / 1.5, chartW / 2, chartH / 2)} style={zoomBtnStyle}>−</button>
                                {zoom.z > 1.01 && <button onMouseDown={(e) => e.stopPropagation()} onClick={resetZoom} style={{ ...zoomBtnStyle, fontSize: 9, height: 18 }}>1:1</button>}
                            </div>
                        </>
                    )}
                </div>

                {/* 호버 카드 — 클립 밖에서 렌더(하단/모서리 타일서 잘림 방지) */}
                {hover && layout.tiles.length > 0 && (() => {
                    const { cl, ct, CW } = hoverCardPos()
                    return (
                        <div style={{
                            position: "absolute", left: cl, top: ct,
                            width: CW, background: C.card, border: `1px solid ${C.line}`, borderRadius: 10,
                            boxShadow: "0 8px 26px rgba(0,0,0,0.22)", padding: "9px 11px", zIndex: 20, pointerEvents: "none", boxSizing: "border-box",
                        }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                {bfLogoSrc(hover.m.ticker, __lmH, 18) ? (<img src={bfLogoSrc(hover.m.ticker, __lmH, 18)} alt="" width={18} height={18} onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none" }} style={{ width: 18, height: 18, borderRadius: 6, flexShrink: 0, filter: bfLogoFilter(hover.m.ticker), objectFit: "contain", padding: bfLogoPad(hover.m.ticker), boxSizing: "border-box", display: "block", background: bfLogoBg(hover.m.ticker) }} />) : null}
                                <span style={{ fontSize: 13, fontWeight: 800, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{hover.m.name}</span>
                                <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, flexShrink: 0 }}>{hover.m.ticker}</span>
                            </div>
                            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginBottom: 5, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{hover.sector} · 시총 {capLabel(hover.m.cap)}</div>
                            {hoverRow("내부자 순매수", insiderFmt(insiderMap[hover.m.ticker]), C)}
                            {hoverRow("외국인 5일", flowFmt(flowMap[hover.m.ticker]), C)}
                            {hoverRow("희석 공시", dilFmt(forenMap[hover.m.ticker]), C)}
                            <div style={{ fontSize: 10, color: C.vg, fontWeight: 800, marginTop: 5 }}>탭 → 전체 리포트 ›</div>
                        </div>
                    )
                })()}
            </div>

            <div style={{ textAlign: "center", fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 10, lineHeight: 1.5 }}>
                색=발행된 사실 · 박스=시가총액
            </div>
        </div>
    )
}

/* ── helpers ── */
function hexA(hex: string, a: number): string {
    const h = hex.replace("#", "")
    const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16)
    return `rgba(${r},${g},${b},${a.toFixed(3)})`
}
function tileValLabel(metric: MetricKey, v: number | null): string {
    if (v == null) return ""
    if (metric === "dilution") return Math.round(v) + "회"
    return fmtSharesShort(v)
}
function fmtSharesShort(v: number): string {
    const a = Math.abs(v), sign = v > 0 ? "+" : "−"
    if (a >= 1e8) return sign + (a / 1e8).toFixed(1) + "억"
    if (a >= 1e4) return sign + Math.round(a / 1e4).toLocaleString("en-US") + "만"
    return sign + Math.round(a).toLocaleString("en-US")
}
function hoverRow(label: string, value: string, C: any) {
    return (
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8, padding: "2px 0", alignItems: "baseline" }}>
            <span style={{ fontSize: 11, color: C.faint, fontWeight: 600, whiteSpace: "nowrap", flexShrink: 0 }}>{label}</span>
            <span style={{ fontSize: 11.5, color: C.ink, fontWeight: 700, fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", textAlign: "right", minWidth: 0 }}>{value}</span>
        </div>
    )
}
function insiderFmt(e: any): string {
    if (!e || e.net_change == null) return "—"
    return fmtSharesShort(Number(e.net_change)) + ` (매수 ${e.buy_n || 0}/매도 ${e.sell_n || 0})`
}
function flowFmt(f: any): string {
    if (!f || !f.length) return "—"
    const v = Number(f[f.length - 1].foreign_net)
    return isFinite(v) ? fmtSharesShort(v) + "주" : "—"
}
function dilFmt(fo: any): string {
    if (!fo) return "—"
    const d = Number(fo.dilution_count)
    return isFinite(d) && d > 0 ? d + "회" : "0"
}
/* ── 캔버스/데모 샘플 ── */
function buildSample() {
    const mk = (ticker: string, name: string, sector: string, cap: string) => ({ ticker, name, market: "KOSPI", facts: { 시가총액: cap }, peer: { sector } })
    const stocks = [
        mk("005930", "삼성전자", "반도체", "425조"), mk("000660", "SK하이닉스", "반도체", "180조"),
        mk("373220", "LG에너지솔루션", "2차전지", "95조"), mk("207940", "삼성바이오로직스", "바이오", "70조"),
        mk("005380", "현대차", "자동차", "52조"), mk("000270", "기아", "자동차", "44조"),
        mk("068270", "셀트리온", "바이오", "40조"), mk("105560", "KB금융", "금융", "38조"),
        mk("055550", "신한지주", "금융", "30조"), mk("247540", "에코프로비엠", "2차전지", "14조"),
        mk("035420", "NAVER", "인터넷", "33조"), mk("035720", "카카오", "인터넷", "20조"),
        mk("012330", "현대모비스", "자동차", "22조"), mk("042700", "한미반도체", "반도체", "11조"),
        mk("034020", "두산에너빌리티", "기계", "13조"), mk("009540", "HD한국조선해양", "조선", "12조"),
    ]
    const insider: Record<string, any> = {
        "005930": { ticker: "005930", net_change: 8590000, buy_n: 3, sell_n: 1 },
        "000660": { ticker: "000660", net_change: -2200000, buy_n: 1, sell_n: 2 },
        "247540": { ticker: "247540", net_change: 540000, buy_n: 2, sell_n: 0 },
        "042700": { ticker: "042700", net_change: 1200000, buy_n: 4, sell_n: 1 },
        "035720": { ticker: "035720", net_change: -880000, buy_n: 0, sell_n: 3 },
        "005380": { ticker: "005380", net_change: 320000, buy_n: 2, sell_n: 1 },
    }
    const flow: Record<string, any[]> = {
        "005930": [{ foreign_net: 230000 }], "000660": [{ foreign_net: 145000 }], "373220": [{ foreign_net: -90000 }],
        "035420": [{ foreign_net: 60000 }], "035720": [{ foreign_net: -40000 }], "068270": [{ foreign_net: 28000 }],
    }
    const foren: Record<string, any> = {
        "247540": { ticker: "247540", dilution_count: 12 }, "034020": { ticker: "034020", dilution_count: 6 },
        "035720": { ticker: "035720", dilution_count: 4 }, "009540": { ticker: "009540", dilution_count: 3 },
    }
    return { stocks, insider, flow, foren }
}

addPropertyControls(PublicHeatmap, {
    stockUrl: { type: ControlType.String, title: "Stock URL", defaultValue: DEFAULT_STOCK },
    insiderUrl: { type: ControlType.String, title: "Insider URL", defaultValue: DEFAULT_INSIDER },
    flowUrl: { type: ControlType.String, title: "Flow URL", defaultValue: DEFAULT_FLOW },
    forensicsUrl: { type: ControlType.String, title: "Forensics URL", defaultValue: DEFAULT_FORENSICS },
    reportPath: { type: ControlType.String, title: "Report Path", defaultValue: DEFAULT_REPORT },
    topN: { type: ControlType.Number, title: "Top N (시총)", defaultValue: 160, min: 40, max: 260, step: 10 },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})