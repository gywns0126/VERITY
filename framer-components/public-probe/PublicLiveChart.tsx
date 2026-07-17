import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 일봉 차트 v2 — VERITY 공개 터미널. 자체 SVG 캔들 (외부 라이브러리 0 · 외부 위젯 0).
 *
 * 🚨 시세 재배포 컴플라이언스 (2026-07-04 v2):
 *   · KRX/KIS raw 재배포 불가 → 자체 차트 중단(7/2) → TradingView 위젯 시도 → KRX 임베드 표시 제한 확인(7/4 실증).
 *   · v2 source = 금융위원회_주식시세정보 공공데이터 (data.go.kr/data/15094808) —
 *     "이용허락범위 제한 없음" + 무료 (portal 원문 확인). 재배포 합법 → 자체 차트 부활.
 *   · T+1 전일 종가까지 — 당일/실시간 없음. 라벨 정직 표기 의무. 실시간 = 네이버 link-out.
 *   상세 = docs/MIGRATION_KRX_QUOTE_REDISTRIBUTION_2026_07.md.
 *
 * 데이터 = Blob /kr_chart_daily/chunk_XX.json (청크 = parseInt(code,36)%40 — collector 와 동일 산식).
 *   종목당 최근 250거래일 [basDt,시,고,저,종,거래량] 오름차순. 평일 14:23 KST cron 갱신.
 * 정보량 = 캔들+거래량+MA(5/20/60)+52주 고저선+전일比 헤더+크로스헤어 카드(시고저종·거래량·등락률).
 * 편의성 = 기간탭(1M/3M/6M/1Y/전체)+터치 대응+종목연동(prop→URL ?q=→localStorage, verity-ticker-change·popstate).
 * 전체(MAX) 탭 = /kr_chart_history/{code}.json lazy fetch(2020~, 월간 cron) + 최근 청크 병합 → 320봉 초과 시 주봉 자동 전환.
 * KR 색 = 상승 빨강 / 하락 파랑. 테마 = body[data-framer-theme]. 캔버스 = 데모 봉. 로딩 = shimmer 스켈레톤.
 */

interface Props {
    ticker: string
    chartBase: string
    height: number
    dark: boolean
    showVolume: boolean
}
const DEFAULT_BASE = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"
const N_CHUNKS = 40
const LIGHT = { bg: "#ffffff", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#e5e8eb", grid: "#eef1f4", up: "#f04452", down: "#3182f6", vg: "#6c5ce7", ma5: "#f2a33c", ma20: "#0ca678", ma60: "#8b6cf0", hi52: "#f04452", lo52: "#3182f6", tipBd: "#e5e8eb" }
const DARK = { bg: "#171c23", card: "#1e242c", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#252b34", grid: "#1e242c", up: "#f04452", down: "#5b9bff", vg: "#a99bff", ma5: "#ffb454", ma20: "#34e08a", ma60: "#a99bff", hi52: "#ff6b76", lo52: "#5b9bff", tipBd: "#2d343d" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif"
const WK = ["일", "월", "화", "수", "목", "금", "토"]
const RANGES = [
    { key: "1M", days: 22 },
    { key: "3M", days: 66 },
    { key: "6M", days: 132 },
    { key: "1Y", days: 250 },
    { key: "전체", days: 0 },   // MAX — 히스토리 lazy fetch + 주봉 자동 전환
]

function isMobileWidth(): boolean {
    if (typeof window === "undefined") return false
    return window.innerWidth > 0 && window.innerWidth < 560
}
// 증권사(네이버)가 서빙 = 재배포 아님. 실시간·무료·합법 딥링크.
function naverUrl(tk: string): string {
    if (!/^\d{6}$/.test(tk)) return "https://finance.naver.com/"
    return isMobileWidth()
        ? "https://m.stock.naver.com/domestic/stock/" + tk + "/total"
        : "https://finance.naver.com/item/main.naver?code=" + tk
}
function mmdd(bas: number): string {
    const s = String(bas)
    return s.length === 8 ? s.slice(4, 6) + "." + s.slice(6, 8) : s
}
function dateDot(bas: number): string {
    const s = String(bas)
    if (s.length !== 8) return s
    const wd = WK[new Date(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8)).getDay()]
    return `${s.slice(0, 4)}.${s.slice(4, 6)}.${s.slice(6, 8)}(${wd})`
}
function won(v: any): string { const x = Number(v); return isFinite(x) && x > 0 ? Math.round(x).toLocaleString("en-US") + "원" : "—" }
function fmtVol(v: any): string {
    const x = Number(v)
    if (!isFinite(x) || x <= 0) return "—"
    if (x >= 1e8) return (x / 1e8).toFixed(2) + "억"
    if (x >= 1e4) return Math.round(x / 1e4).toLocaleString("en-US") + "만"
    return Math.round(x).toLocaleString("en-US")
}
// collector(_chunk_idx)와 동일 — base36 (코드 'K' 포함 우선주 변형 대응). 양측 검증 완료.
function chunkOf(code: string): string {
    const n = parseInt(code, 36) % N_CHUNKS
    return String(n).padStart(2, "0")
}
function sma(closes: number[], period: number): (number | null)[] {
    const out: (number | null)[] = []
    let sum = 0
    for (let i = 0; i < closes.length; i++) {
        sum += closes[i]
        if (i >= period) sum -= closes[i - period]
        out.push(i >= period - 1 ? sum / period : null)
    }
    return out
}
// 일봉 → 주봉 (주 키 = 월요일). [주 마지막날, 첫 시가, max 고, min 저, 마지막 종가, 합 거래량]
function toWeekly(cs: number[][]): number[][] {
    const out: number[][] = []
    let cur: number[] | null = null
    let curKey = ""
    for (const c of cs) {
        const str = String(c[0])
        if (str.length !== 8) continue
        const dt = new Date(+str.slice(0, 4), +str.slice(4, 6) - 1, +str.slice(6, 8))
        const day = (dt.getDay() + 6) % 7
        const mon = new Date(dt.getFullYear(), dt.getMonth(), dt.getDate() - day)
        const key = String(mon.getFullYear() * 10000 + (mon.getMonth() + 1) * 100 + mon.getDate())
        if (key !== curKey) {
            if (cur) out.push(cur)
            cur = [c[0], c[1], c[2], c[3], c[4], c[5]]
            curKey = key
        } else if (cur) {
            cur[0] = c[0]
            cur[2] = Math.max(cur[2], c[2])
            cur[3] = Math.min(cur[3], c[3])
            cur[4] = c[4]
            cur[5] += c[5]
        }
    }
    if (cur) out.push(cur)
    return out
}
// 히스토리(월간 stale 가능) + 최근 청크(fresh) 병합 — 같은 날은 최근 청크 우선
function mergeHist(hist: number[][] | null, recent: number[][]): number[][] {
    if (!hist || !hist.length) return recent
    const m: Record<number, number[]> = {}
    for (const c of hist) m[c[0]] = c
    for (const c of recent) m[c[0]] = c
    return Object.keys(m).map((k) => m[+k]).sort((a, b) => a[0] - b[0])
}

function demoCandles(): number[][] {
    const demo: number[][] = []
    let p = 70000
    for (let i = 0; i < 60; i++) {
        const o = p, c = Math.round(p * (1 + (((i * 7) % 11) - 5) / 100))
        demo.push([20260400 + (i % 28) + 1, o, Math.round(Math.max(o, c) * 1.01), Math.round(Math.min(o, c) * 0.99), c, 1000000 + i * 9000])
        p = c
    }
    return demo
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicLiveChart(props: Props) {
    const { ticker, chartBase, height, dark, showVolume } = props
    const base = (chartBase || DEFAULT_BASE).replace(/\/+$/, "")
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const Hprop = height || 480

    const wrapRef = useRef<HTMLDivElement>(null)
    const svgRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [h, setH] = useState(0)
    const [full, setFull] = useState<number[][]>(() => (RenderTarget.current() === RenderTarget.canvas ? demoCandles() : []))
    const [name, setName] = useState("")
    const [range, setRange] = useState("3M")
    const [hoverIdx, setHoverIdx] = useState<number | null>(null)
    const [noData, setNoData] = useState(false)
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!dark : (typeof document !== "undefined" && !!document.body && document.body.dataset.framerTheme === "dark")))

    const isDark = onCanvas ? !!dark : themeDark
    const C = isDark ? DARK : LIGHT

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

    // 종목 = prop → URL ?q= → localStorage(StockReport 기록). 이벤트·popstate 수신해 리로드 없이 추종.
    // 유효 코드 아니면 빈 상태 (기본 종목 fallback 금지 — 엉뚱 그래프 방지). 'K' 포함 우선주 변형 허용.
    const resolveTk = (): string => {
        let t = String(ticker || "").trim().toUpperCase()
        if (!t && typeof window !== "undefined") {
            t = (new URLSearchParams(window.location.search).get("q") || "").trim().toUpperCase()
            if (!t) { try { t = (window.localStorage.getItem("verity_last_ticker") || "").trim().toUpperCase() } catch (e) { t = "" } }
        }
        return /^[0-9]{5}[0-9A-Z]$/.test(t) ? t : ""
    }
    const [tk, setTk] = useState<string>(resolveTk)
    useEffect(() => {
        if (onCanvas) return
        const reread = () => setTk(resolveTk())
        reread()
        window.addEventListener("verity-ticker-change", reread)
        window.addEventListener("popstate", reread)
        return () => { window.removeEventListener("verity-ticker-change", reread); window.removeEventListener("popstate", reread) }
    }, [ticker, onCanvas])

    useEffect(() => {
        const el = wrapRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) { setW(e.contentRect.width); setH(e.contentRect.height) } })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    /* 데이터 — Blob 청크 fetch (sessionStorage 캐시, cache-fallback). 종목 미포함 = 정직한 빈 상태. */
    useEffect(() => {
        if (onCanvas) { setFull(demoCandles()); setName("미리보기"); return }
        setFull([]); setNoData(false); setName(""); setHoverIdx(null)
        if (!tk) return
        let alive = true
        const url = base + "/kr_chart_daily/chunk_" + chunkOf(tk) + ".json"
        const cacheKey = "krchart_" + chunkOf(tk)
        const apply = (doc: any): boolean => {
            const ent = doc && doc.stocks && doc.stocks[tk]
            if (ent && Array.isArray(ent.c) && ent.c.length > 1) {
                if (alive) { setFull(ent.c); setName(ent.n || tk) }
                return true
            }
            return false
        }
        fetch(url, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((doc) => {
                if (!alive) return
                if (doc) {
                    try { sessionStorage.setItem(cacheKey, JSON.stringify(doc)) } catch (e) {}
                    if (!apply(doc)) setNoData(true)   // 청크 수신 OK · 종목 없음 = 진짜 없음
                } else {
                    try { const c = sessionStorage.getItem(cacheKey); if (!(c && apply(JSON.parse(c)))) setNoData(true) } catch (e) { setNoData(true) }
                }
            })
            .catch(() => {
                try { const c = sessionStorage.getItem(cacheKey); if (!(c && apply(JSON.parse(c)))) { /* 네트워크 오류 = 스켈레톤 유지 */ } } catch (e) {}
            })
        return () => { alive = false }
    }, [tk, base, onCanvas])

    /* 전체(MAX) 탭 — 히스토리 lazy fetch (탭 선택 시에만 1회). [] = 미보유(최근 청크만으로 표시). */
    const [histFull, setHistFull] = useState<number[][] | null>(null)
    useEffect(() => { setHistFull(null) }, [tk])
    useEffect(() => {
        if (onCanvas || range !== "전체" || !tk || histFull) return
        let alive = true
        fetch(base + "/kr_chart_history/" + tk + ".json", { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (alive) setHistFull(d && Array.isArray(d.c) && d.c.length > 1 ? d.c : []) })
            .catch(() => { if (alive) setHistFull([]) })
        return () => { alive = false }
    }, [range, tk, base, onCanvas, histFull])

    /* 파생 — 52주(전체 250d) 고저 + MA 는 full 기준 계산 후 range 슬라이스 (경계 왜곡 방지) */
    const view = useMemo(() => {
        if (!full || full.length < 2) return null
        const hi52 = Math.max(...full.map((c) => c[2]))
        const lo52 = Math.min(...full.map((c) => c[3]))
        if (range === "전체") {
            const merged = mergeHist(histFull, full)
            const isWeekly = merged.length > 320
            const candles = isWeekly ? toWeekly(merged) : merged
            const none: (number | null)[] = []
            // MAX = 주봉·수년 스팬 — MA(일봉 산식)·52주선 비표시 (오독 방지)
            return { candles, ma5: none, ma20: none, ma60: none, hi52, lo52, prevClose: null, isMax: true, isWeekly }
        }
        const closesAll = full.map((c) => c[4])
        const ma5All = sma(closesAll, 5), ma20All = sma(closesAll, 20), ma60All = sma(closesAll, 60)
        const days = (RANGES.find((r) => r.key === range) || RANGES[1]).days
        const start = Math.max(0, full.length - days)
        return {
            candles: full.slice(start),
            ma5: ma5All.slice(start), ma20: ma20All.slice(start), ma60: ma60All.slice(start),
            hi52, lo52,
            prevClose: start > 0 ? full[start - 1][4] : null,
            isMax: false, isWeekly: false,
        }
    }, [full, range, histFull])

    /* 좌표 — 프레임 실측 높이 안을 꽉 채움 (헤더/탭/축/푸터 크롬 ≈ 118px 제외) */
    const cv = useMemo(() => {
        if (!view) return null
        const candles = view.candles
        const his = candles.map((c) => c[2]), los = candles.map((c) => c[3])
        // 52주 고저선은 시야 밖일 수 있음 — 가격축은 현 range + (근접 시) 52주선 포함
        let pmin = Math.min(...los), pmax = Math.max(...his)
        if (!view.isMax) {
            const prng0 = (pmax - pmin) || 1
            if (view.hi52 <= pmax + prng0 * 0.25) pmax = Math.max(pmax, view.hi52)
            if (view.lo52 >= pmin - prng0 * 0.25) pmin = Math.min(pmin, view.lo52)
        }
        const prng = (pmax - pmin) || 1
        const W = Math.max(240, (w || 800) - 4)
        const chartH = h > 200 ? Math.max(180, h - 118) : Hprop - 118
        const Hv = showVolume !== false ? Math.round(chartH * 0.16) : 0
        const gap = Hv ? 8 : 0
        const padT = 10, padB = 4
        const Hp = chartH - Hv - gap
        const n = candles.length
        const xAt = (i: number) => (n === 1 ? W / 2 : (i / (n - 1)) * W)
        const yP = (v: number) => padT + (Hp - padT - padB) - ((v - pmin) / prng) * (Hp - padT - padB)
        const vols = candles.map((c) => c[5])
        const vmax = Math.max(1, ...vols)
        const cw = Math.max(1.2, (W / n) * 0.62)
        const items = candles.map((c, i) => {
            const upDay = c[4] >= c[1]
            const bh = Hv ? (c[5] / vmax) * (Hv - 2) : 0
            return { x: xAt(i), oy: yP(c[1]), cy: yP(c[4]), hy: yP(c[2]), ly: yP(c[3]), upDay, volTop: Hp + gap + (Hv - bh), volH: Math.max(0.5, bh) }
        })
        const tickIdx = [0, Math.round((n - 1) / 3), Math.round((2 * (n - 1)) / 3), n - 1]
        const maPath = (arr: (number | null)[]): string => {
            let dstr = "", pen = false
            for (let i = 0; i < arr.length; i++) {
                const v = arr[i]
                if (v == null) { pen = false; continue }
                dstr += (pen ? "L" : "M") + xAt(i).toFixed(1) + "," + yP(v).toFixed(1)
                pen = true
            }
            return dstr
        }
        return { W, H: chartH, Hp, Hv, gap, pmin, pmax, xAt, yP, items, cw, n, tickIdx, p5: maPath(view.ma5), p20: maPath(view.ma20), p60: maPath(view.ma60) }
    }, [view, w, h, Hprop, showVolume])

    const setHoverFromX = (clientX: number) => {
        if (!cv || !svgRef.current) return
        const rect = svgRef.current.getBoundingClientRect()
        if (rect.width <= 0) return
        let rel = (clientX - rect.left) / rect.width
        rel = Math.max(0, Math.min(1, rel))
        setHoverIdx(Math.round(rel * (cv.n - 1)))
    }

    const candles = view ? view.candles : []
    const last = candles.length ? candles[candles.length - 1] : null
    const prevOfLast = candles.length > 1 ? candles[candles.length - 2][4] : (view && view.prevClose) || null
    const lastChg = last && prevOfLast ? ((last[4] - prevOfLast) / prevOfLast) * 100 : null

    const hov = hoverIdx != null && cv && hoverIdx >= 0 && hoverIdx < cv.n ? candles[hoverIdx] : null
    const hovX = hov && cv ? cv.xAt(hoverIdx as number) : 0
    const hovChg = (() => {
        if (!hov || hoverIdx == null) return null
        const pc = (hoverIdx as number) > 0 ? candles[(hoverIdx as number) - 1][4] : (view && view.prevClose)
        if (!pc || pc <= 0) return null
        return ((hov[4] - pc) / pc) * 100
    })()
    const cardLeftPct = cv ? (hovX / cv.W) * 100 : 0
    const cardFlip = cv ? hoverIdx != null && (hoverIdx as number) > cv.n * 0.5 : false

    const wrap: CSSProperties = {
        width: "100%", height: "100%", minHeight: Math.max(260, Hprop), position: "relative",
        background: C.bg, borderRadius: 16, overflow: "hidden", boxSizing: "border-box",
        fontFamily: FONT, padding: "10px 4px 4px", display: "flex", flexDirection: "column",
    }
    const tipRow = (label: string, value: any, color?: string) => (
        <div style={{ display: "flex", justifyContent: "space-between", gap: 10, padding: "2px 0" }}>
            <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 500 }}>{label}</span>
            <span style={{ fontSize: 11.5, color: color || C.ink, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{value}</span>
        </div>
    )
    const maChip = (label: string, color: string) => (
        <span style={{ display: "inline-flex", alignItems: "center", gap: 3, fontSize: 10, fontWeight: 600, color: C.faint }}>
            <span style={{ width: 10, height: 2, background: color, display: "inline-block", borderRadius: 1 }} />{label}
        </span>
    )
    const rangeTab = (r: { key: string }) => (
        <button key={r.key} onClick={() => { setRange(r.key); setHoverIdx(null) }} style={{
            border: "none", cursor: "pointer", fontFamily: FONT, padding: "4px 10px", borderRadius: 8,
            fontSize: 11.5, fontWeight: 700, background: range === r.key ? (isDark ? "#252b34" : "#f2f4f6") : "transparent",
            color: range === r.key ? C.ink : C.faint,
        }}>{r.key}</button>
    )

    const renderEmpty = () => (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 7, padding: "0 18px", textAlign: "center" }}>
            {/* Phosphor chart-line (regular) — 자작 점선 아이콘의 끊김 인상 교체 (PM 2026-07-07) */}
            <svg width="30" height="30" viewBox="0 0 256 256" style={{ opacity: 0.5 }}>
                <path d="M232,208a8,8,0,0,1-8,8H32a8,8,0,0,1-8-8V48a8,8,0,0,1,16,0v94.37L90.73,98a8,8,0,0,1,10.07-.38l58.81,44.11L218.73,90a8,8,0,1,1,10.54,12l-64,56a8,8,0,0,1-10.07.38L96.39,114.29,40,163.63V200H224A8,8,0,0,1,232,208Z" fill={C.faint} />
            </svg>
            <span style={{ fontSize: 13, fontWeight: 700, color: C.sub }}>{tk ? "표시할 시세 정보가 없습니다" : "표시할 종목이 없습니다"}</span>
            <span style={{ fontSize: 11, fontWeight: 500, color: C.faint, lineHeight: 1.5 }}>{tk ? "이 종목은 차트로 표시할 일봉 데이터가 없어요" : "종목을 선택하면 차트가 표시돼요"}</span>
        </div>
    )
    const renderSkeleton = () => {
        const skBase = isDark ? "#222a33" : "#e9edf1"
        const skHi = isDark ? "#2d3742" : "#f3f5f7"
        const sh: CSSProperties = {
            background: skBase, backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`,
            backgroundSize: "800px 100%", animation: "plcShimmer 1.4s ease-in-out infinite",
        }
        const n = 40
        return (
            <div style={{ flex: 1, padding: "8px 10px 0", display: "flex", flexDirection: "column" }}>
                <style>{`@keyframes plcShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={{ flex: 1, display: "flex", alignItems: "flex-end", gap: 3 }}>
                    {Array.from({ length: n }).map((_, i) => {
                        const bh = 26 + ((i * 41 + 17) % 64)
                        return <div key={i} style={{ flex: 1, height: bh + "%", borderRadius: 3, ...sh }} />
                    })}
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 10, marginBottom: 6 }}>
                    {Array.from({ length: 4 }).map((_, i) => <div key={i} style={{ width: 38, height: 9, borderRadius: 4, ...sh }} />)}
                </div>
            </div>
        )
    }

    return (
        <div ref={wrapRef} style={wrap}>
            {/* 헤더 — 전일 종가·등락 + 52주 + 기간탭 (정직: T+1 전일까지) */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 10px 6px", flexWrap: "wrap" }}>
                {last && (
                    <>
                        <span style={{ fontSize: 17, fontWeight: 800, color: C.ink, letterSpacing: -0.3 }}>{won(last[4])}</span>
                        {lastChg != null && (
                            <span style={{ fontSize: 12.5, fontWeight: 700, color: lastChg > 0 ? C.up : lastChg < 0 ? C.down : C.faint }}>
                                {(lastChg > 0 ? "▲ +" : lastChg < 0 ? "▼ " : "") + lastChg.toFixed(2) + "%"}
                            </span>
                        )}
                        <span style={{ fontSize: 10.5, fontWeight: 700, color: C.faint, background: C.grid, padding: "1px 6px", borderRadius: 5 }}>전일 종가 · {dateDot(last[0])}</span>
                        {view && view.isWeekly && <span style={{ fontSize: 10, fontWeight: 700, color: C.vg }}>주봉</span>}
                        {view && (
                            <span style={{ fontSize: 10.5, fontWeight: 600, color: C.faint }}>
                                52주 <span style={{ color: C.hi52 }}>{Number(view.hi52).toLocaleString()}</span> / <span style={{ color: C.lo52 }}>{Number(view.lo52).toLocaleString()}</span>
                            </span>
                        )}
                    </>
                )}
                <span style={{ marginLeft: "auto", display: "inline-flex", gap: 2 }}>{RANGES.map(rangeTab)}</span>
            </div>

            {cv && view ? (
                <>
                    <div ref={svgRef} style={{ position: "relative", width: "100%", touchAction: "pan-y" }}
                        onMouseMove={(e) => setHoverFromX(e.clientX)}
                        onMouseLeave={() => setHoverIdx(null)}
                        onTouchStart={(e) => { if (e.touches[0]) setHoverFromX(e.touches[0].clientX) }}
                        onTouchMove={(e) => { if (e.touches[0]) setHoverFromX(e.touches[0].clientX) }}>
                        <svg viewBox={`0 0 ${cv.W} ${cv.H}`} width="100%" height={cv.H} preserveAspectRatio="none" style={{ display: "block" }}>
                            <line x1={0} y1={cv.yP(cv.pmax)} x2={cv.W} y2={cv.yP(cv.pmax)} stroke={C.grid} strokeWidth={1} />
                            <line x1={0} y1={cv.yP((cv.pmax + cv.pmin) / 2)} x2={cv.W} y2={cv.yP((cv.pmax + cv.pmin) / 2)} stroke={C.grid} strokeWidth={1} />
                            <line x1={0} y1={cv.yP(cv.pmin)} x2={cv.W} y2={cv.yP(cv.pmin)} stroke={C.grid} strokeWidth={1} />
                            {/* 52주 고저 점선 (가격축 범위 안 + MAX 아님) */}
                            {!view.isMax && view.hi52 <= cv.pmax && view.hi52 >= cv.pmin && (
                                <line x1={0} y1={cv.yP(view.hi52)} x2={cv.W} y2={cv.yP(view.hi52)} stroke={C.hi52} strokeWidth={1} strokeOpacity={0.5} strokeDasharray="4 4" vectorEffect="non-scaling-stroke" />
                            )}
                            {!view.isMax && view.lo52 <= cv.pmax && view.lo52 >= cv.pmin && (
                                <line x1={0} y1={cv.yP(view.lo52)} x2={cv.W} y2={cv.yP(view.lo52)} stroke={C.lo52} strokeWidth={1} strokeOpacity={0.5} strokeDasharray="4 4" vectorEffect="non-scaling-stroke" />
                            )}
                            {/* 캔들 + 거래량 */}
                            {cv.items.map((cd: any, i: number) => {
                                const col = cd.upDay ? C.up : C.down
                                const bodyTop = Math.min(cd.oy, cd.cy)
                                const bodyH = Math.max(0.8, Math.abs(cd.oy - cd.cy))
                                return (
                                    <g key={i}>
                                        {cv.Hv > 0 && <rect x={cd.x - cv.cw / 2} y={cd.volTop} width={cv.cw} height={cd.volH} fill={col} fillOpacity={0.35} />}
                                        <line x1={cd.x} y1={cd.hy} x2={cd.x} y2={cd.ly} stroke={col} strokeWidth={1} vectorEffect="non-scaling-stroke" />
                                        <rect x={cd.x - cv.cw / 2} y={bodyTop} width={Math.max(1, cv.cw)} height={bodyH} fill={col} />
                                    </g>
                                )
                            })}
                            {/* 이동평균선 5/20/60 */}
                            {cv.p60 && <path d={cv.p60} fill="none" stroke={C.ma60} strokeWidth={1.2} strokeOpacity={0.9} vectorEffect="non-scaling-stroke" />}
                            {cv.p20 && <path d={cv.p20} fill="none" stroke={C.ma20} strokeWidth={1.2} strokeOpacity={0.9} vectorEffect="non-scaling-stroke" />}
                            {cv.p5 && <path d={cv.p5} fill="none" stroke={C.ma5} strokeWidth={1.2} strokeOpacity={0.9} vectorEffect="non-scaling-stroke" />}
                            {hov && (
                                <>
                                    <line x1={hovX} y1={0} x2={hovX} y2={cv.H} stroke={C.faint} strokeWidth={1} strokeOpacity={0.45} vectorEffect="non-scaling-stroke" />
                                    <circle cx={hovX} cy={cv.yP(hov[4])} r={4} fill={hov[4] >= hov[1] ? C.up : C.down} stroke={C.bg} strokeWidth={1.5} />
                                </>
                            )}
                        </svg>
                        <span style={{ position: "absolute", top: 2, right: 4, fontSize: 10, fontWeight: 600, color: C.faint, background: C.bg, padding: "0 3px", borderRadius: 4 }}>{Number(cv.pmax).toLocaleString()}</span>
                        <span style={{ position: "absolute", top: (cv.Hp - 14) + "px", right: 4, fontSize: 10, fontWeight: 600, color: C.faint, background: C.bg, padding: "0 3px", borderRadius: 4 }}>{Number(cv.pmin).toLocaleString()}</span>

                        {/* 크로스헤어 플로팅 카드 (토스풍 컴팩트) */}
                        {hov && (
                            <div style={{
                                position: "absolute", top: 2, left: cardLeftPct + "%",
                                transform: cardFlip ? "translateX(calc(-100% - 8px))" : "translateX(8px)",
                                background: C.card, border: `1px solid ${C.tipBd}`, borderRadius: 10,
                                boxShadow: "0 8px 24px rgba(0,0,0,0.14)", padding: "7px 9px", minWidth: 122,
                                zIndex: 30, pointerEvents: "none",
                            }}>
                                <div style={{ fontSize: 12, fontWeight: 600, color: C.ink, marginBottom: 4, letterSpacing: "-0.2px" }}>{dateDot(hov[0])}</div>
                                {tipRow("시가", won(hov[1]))}
                                {tipRow("종가", won(hov[4]))}
                                {tipRow("최고", won(hov[2]), C.up)}
                                {tipRow("최저", won(hov[3]), C.down)}
                                {tipRow("거래량", fmtVol(hov[5]))}
                                {hovChg != null && tipRow("등락률", (hovChg > 0 ? "+" : "") + hovChg.toFixed(2) + "%", hovChg > 0 ? C.up : hovChg < 0 ? C.down : C.faint)}
                            </div>
                        )}
                    </div>
                    {/* 날짜축 */}
                    <div style={{ position: "relative", height: 14, margin: "2px 2px 0" }}>
                        {cv.tickIdx.map((ti: number, i: number) => {
                            const lp = (cv.xAt(ti) / cv.W) * 100
                            const tf = i === 0 ? "translateX(0)" : i === cv.tickIdx.length - 1 ? "translateX(-100%)" : "translateX(-50%)"
                            return <span key={i} style={{ position: "absolute", left: lp + "%", transform: tf, fontSize: 10, fontWeight: 500, color: C.faint, whiteSpace: "nowrap" }}>{candles[ti] ? mmdd(candles[ti][0]) : ""}</span>
                        })}
                    </div>
                    {/* 푸터 — MA 범례 + 정직 라벨 + 네이버 실시간 */}
                    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "5px 10px 4px", flexWrap: "wrap" }}>
                        {!view.isMax && <>{maChip("MA5", C.ma5)}{maChip("MA20", C.ma20)}{maChip("MA60", C.ma60)}</>}
                        <span style={{ fontSize: 10, color: C.faint, fontWeight: 500 }}>
                            {view.isMax ? (view.isWeekly ? "주봉 · 전체 기간 (2020~)" : "일봉 · 전체 기간") : "일봉"} · 전일까지 · 금융위 공공데이터 (T+1)
                        </span>
                        {tk && (
                            <a href={naverUrl(tk)} target="_blank" rel="noopener noreferrer"
                                style={{ marginLeft: "auto", fontSize: 11, fontWeight: 800, color: C.vg, textDecoration: "none" }}>
                                실시간 호가·차트 · 네이버 ↗
                            </a>
                        )}
                    </div>
                </>
            ) : noData || (!tk && !onCanvas) ? (
                renderEmpty()
            ) : (
                renderSkeleton()
            )}
        </div>
    )
}

addPropertyControls(PublicLiveChart, {
    ticker: { type: ControlType.String, title: "Ticker", defaultValue: "" },
    chartBase: { type: ControlType.String, title: "Chart Base", defaultValue: DEFAULT_BASE },
    height: { type: ControlType.Number, title: "Height(fallback)", defaultValue: 480, min: 220, max: 800, step: 10 },
    showVolume: { type: ControlType.Boolean, title: "Volume", defaultValue: true, enabledTitle: "On", disabledTitle: "Off" },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})
