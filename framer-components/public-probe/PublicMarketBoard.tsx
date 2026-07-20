import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 글로벌 시세 보드 — AlphaNest 공개. 소스별 컴플라이언스(2026-07-16, KR 소스 2026-07-17 yfinance, 2026-07-19 복원).
 *
 * 🚨 시세 컴플라이언스 — 소스·성격별:
 *   · 크립토 = Binance 무인증 공개(브라우저 직접) → 실시간 값. USD.
 *   · KR 지수 = yfinance 전일 종가 '숫자'(=사실, 저작권 대상 아님. macro_snapshot). data_date 라벨. 실시간은 네이버 딥링크.
 *   · US·글로벌 지수·환율·원자재 = 전일 종가 레벨 '숫자'(=사실). 값 표기 + 실시간은 네이버 딥링크.
 *   · 금리 = FRED → 전일 종가.
 *   🚨 KIS price_pulse(실시간 KR지수 재배포=위법) · 업비트(재배포금지) 전면 제거. 되돌리지 말 것.
 *   ⚠️ 금지선 = 실시간 피드 재배포(코스콤/거래소/KIS). 전일 종가 숫자 표기는 사실이라 허용. 장중 접근=네이버 딥링크.
 * 🚨 이 disk 미러 = 라이브(MCP)와 동기 유지 의무 — 2026-07-19 사고: disk 구버전(price_pulse)이 라이브 컴플라이언트판을 덮음(붙여넣기/싱크).
 * 🚨 외곽선 금지 — 분리=채움색만. 🚨 RULE 7 사실만. KR 색 = 상승 빨강 / 하락 파랑. 다크모드 = body[data-framer-theme] 추종.
 */

const LIGHT = { bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#6b7684", faint: "#8b95a1", line: "#eef1f4", up: "#f04452", down: "#3182f6", flat: "#8b95a1", cPos: "#0ca678", cNeg: "#6c5ce7", chipBg: "#f2f4f6", live: "#0ca678", vg: "#6c5ce7" }
const DARK = { bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#252b34", up: "#f04452", down: "#5b9bff", flat: "#828d9b", cPos: "#34e08a", cNeg: "#a99bff", chipBg: "#0f1318", live: "#34e08a", vg: "#a99bff" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

const DEFAULT_MACRO = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/macro_snapshot.json"
const DEFAULT_EXPO = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/commodity_exposure.json"
const DEFAULT_REPORT = "/stock"

const BINANCE_REST = "https://data-api.binance.vision/api/v3/ticker/24hr"
const BINANCE_KLINE = "https://data-api.binance.vision/api/v3/klines"
const BINANCE_WS = "wss://data-stream.binance.vision/stream?streams="
const CRYPTO_SYMS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "DOGEUSDT"]

// 실시간 접근 = 네이버 딥링크(증권사 서빙 = 재배포 아님).
const NAVER_URL: Record<string, string> = {
    kospi: "https://m.stock.naver.com/domestic/index/KOSPI/total",
    kosdaq: "https://m.stock.naver.com/domestic/index/KOSDAQ/total",
    sp500: "https://m.stock.naver.com/worldstock/index/.INX/total",
    nasdaq: "https://m.stock.naver.com/worldstock/index/.IXIC/total",
    dow: "https://m.stock.naver.com/worldstock/index/.DJI/total",
    sox: "https://m.stock.naver.com/worldstock/index/.SOX/total",
    nikkei: "https://m.stock.naver.com/worldstock/index/.N225/total",
    dax: "https://m.stock.naver.com/worldstock/index/.GDAXI/total",
    vix: "https://m.stock.naver.com/worldstock/index/.VIX/total",
    usdkrw: "https://finance.naver.com/marketindex/",
    gold: "https://finance.naver.com/marketindex/",
    silver: "https://finance.naver.com/marketindex/",
    copper: "https://finance.naver.com/marketindex/",
    wti_oil: "https://finance.naver.com/marketindex/",
}

interface Props {
    macroUrl: string
    commodityUrl: string
    reportPath: string
    dark: boolean
    refreshSec: number
}

// src: binance / macro(전일 종가 값). mkey=macro 키(다를 때). spark=macro sparkline 키.
const GROUPS: { title: string; items: { key: string; name: string; src: "binance" | "macro"; spark?: string; mkey?: string; bsym?: string; dec?: number; unit?: string; pre?: string }[] }[] = [
    {
        title: "국내 지수", items: [
            { key: "kospi", name: "코스피", src: "macro", spark: "kospi", dec: 2 },
            { key: "kosdaq", name: "코스닥", src: "macro", spark: "kosdaq", dec: 2 },
        ],
    },
    {
        title: "해외 지수", items: [
            { key: "sp500", name: "S&P 500", src: "macro", spark: "sp500", dec: 2 },
            { key: "nasdaq", name: "나스닥", src: "macro", spark: "nasdaq", dec: 2 },
            { key: "dow", name: "다우존스", src: "macro", mkey: "dji", spark: "dji", dec: 2 },
            { key: "sox", name: "필라델피아 반도체", src: "macro", spark: "sox", dec: 2 },
            { key: "nikkei", name: "니케이225", src: "macro", spark: "nikkei", dec: 2 },
            { key: "dax", name: "독일 DAX", src: "macro", spark: "dax", dec: 2 },
        ],
    },
    {
        title: "변동성·환율·금리", items: [
            { key: "vix", name: "VIX 공포지수", src: "macro", spark: "vix", dec: 2 },
            { key: "usdkrw", name: "달러 환율", src: "macro", mkey: "usd_krw", spark: "usd_krw", dec: 2, unit: "원" },
            { key: "us_10y", name: "미국 10년물", src: "macro", spark: "us_10y", dec: 3, unit: "%" },
            { key: "us_2y", name: "미국 2년물", src: "macro", spark: "us_2y", dec: 3, unit: "%" },
        ],
    },
    {
        title: "원자재", items: [
            { key: "gold", name: "금", src: "macro", spark: "gold", dec: 2 },
            { key: "silver", name: "은", src: "macro", spark: "silver", dec: 2 },
            { key: "copper", name: "구리", src: "macro", spark: "copper", dec: 3 },
            { key: "wti_oil", name: "WTI 유가", src: "macro", spark: "wti_oil", dec: 2 },
        ],
    },
    {
        title: "크립토", items: [
            { key: "btc", name: "비트코인", src: "binance", bsym: "BTCUSDT", pre: "$" },
            { key: "eth", name: "이더리움", src: "binance", bsym: "ETHUSDT", pre: "$" },
            { key: "xrp", name: "리플 XRP", src: "binance", bsym: "XRPUSDT", pre: "$" },
            { key: "sol", name: "솔라나", src: "binance", bsym: "SOLUSDT", pre: "$" },
            { key: "doge", name: "도지코인", src: "binance", bsym: "DOGEUSDT", pre: "$" },
        ],
    },
]

function fmtNum(v: any, dec: number): string {
    const x = Number(v)
    if (!isFinite(x)) return "—"
    return x.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec })
}
function cryptoDec(v: number): number { return !isFinite(v) ? 2 : v >= 1000 ? 0 : v >= 1 ? 2 : 4 }
// data_date(YYYYMMDD) → "M/D 종가" 라벨. 없으면 제네릭 "전일 종가"로 폴백.
function fmtCloseLabel(yyyymmdd: any): string {
    const s = String(yyyymmdd || "")
    if (s.length !== 8) return "전일 종가"
    const m = Number(s.slice(4, 6)), d = Number(s.slice(6, 8))
    if (!m || !d) return "전일 종가"
    return `${m}/${d} 종가`
}

function Spark({ data, color, w, h }: { data: number[]; color: string; w: number; h: number }) {
    if (!data || data.length < 2) return null
    const min = Math.min(...data), max = Math.max(...data), rng = (max - min) || 1
    const pad = 2
    const pts = data.map((v, i) => `${((i / (data.length - 1)) * w).toFixed(1)},${(h - pad - ((v - min) / rng) * (h - pad * 2)).toFixed(1)}`)
    const line = pts.join(" ")
    const area = `${line} ${w.toFixed(1)},${h} 0,${h}`
    const gid = "vmb-" + color.replace(/[^a-z0-9]/gi, "")
    return (
        <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: "block", flexShrink: 0 }}>
            <defs>
                <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={color} stopOpacity={0.22} />
                    <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
            </defs>
            <polygon points={area} fill={`url(#${gid})`} stroke="none" />
            <polyline points={line} fill="none" stroke={color} strokeWidth={1.4} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
        </svg>
    )
}

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

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
// 🎨 페이지 이동 다크 번쩍임 제거(2026-07-20): 첫 마운트만 라이트(SSG/첫방문 매칭·stuck 방지) → 이후 마운트는 실제 테마 즉시.
let __anHyd = false
function anReadDark(): boolean {
    if (typeof document === "undefined") return false
    if (!__anHyd) {
        __anHyd = true
        return false
    }
    const h = document.documentElement ? document.documentElement.dataset.anTheme : null
    if (h === "dark") return true
    if (h === "light") return false
    return !!(document.body && document.body.dataset.framerTheme === "dark")
}


export default function PublicMarketBoard(props: Props) {
    const { macroUrl, commodityUrl, reportPath, dark, refreshSec } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!dark : anReadDark()))
    const C = (onCanvas ? !!dark : themeDark) ? DARK : LIGHT

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [macro, setMacro] = useState<any>(null)
    const [macroLoaded, setMacroLoaded] = useState(false)
    const [expo, setExpo] = useState<any>(null)
    const [openCommodity, setOpenCommodity] = useState<string>("")

    const [cryptoRows, setCryptoRows] = useState<Record<string, { price: number; chg: number }>>({})
    const [cryptoSpark, setCryptoSpark] = useState<Record<string, number[]>>({})
    const [cryptoLive, setCryptoLive] = useState(false)

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

    useEffect(() => {
        if (onCanvas) return
        let alive = true
        const load = () => {
            fetch(macroUrl).then((r) => (r.ok ? r.json() : null)).then((d) => { if (alive && d) { setMacro(d); setMacroLoaded(true) } }).catch(() => {})
        }
        load()
        const sec = Math.max(60, refreshSec || 300)
        const t = setInterval(load, sec * 1000)
        return () => { alive = false; clearInterval(t) }
    }, [macroUrl, refreshSec, onCanvas])

    useEffect(() => {
        if (onCanvas) return
        let alive = true
        const syms = encodeURIComponent(JSON.stringify(CRYPTO_SYMS))
        fetch(`${BINANCE_REST}?symbols=${syms}`, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((arr) => {
                if (!alive || !Array.isArray(arr)) return
                const next: Record<string, { price: number; chg: number }> = {}
                arr.forEach((t: any) => { next[t.symbol] = { price: Number(t.lastPrice), chg: Number(t.priceChangePercent) } })
                setCryptoRows((prev) => ({ ...prev, ...next }))
            })
            .catch(() => {})
        return () => { alive = false }
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas) return
        let alive = true
        CRYPTO_SYMS.forEach((sym) => {
            fetch(`${BINANCE_KLINE}?symbol=${sym}&interval=1d&limit=30`, { cache: "no-store" })
                .then((r) => (r.ok ? r.json() : null))
                .then((k) => {
                    if (!alive || !Array.isArray(k)) return
                    const closes = k.map((row: any) => Number(row[4])).filter((x: number) => isFinite(x))
                    if (closes.length >= 2) setCryptoSpark((prev) => ({ ...prev, [sym]: closes }))
                })
                .catch(() => {})
        })
        return () => { alive = false }
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas || typeof WebSocket === "undefined") return
        let ws: WebSocket | null = null
        let retry: any = null
        let tries = 0
        let disposed = false
        const connect = () => {
            if (disposed) return
            const streams = CRYPTO_SYMS.map((s) => s.toLowerCase() + "@ticker").join("/")
            try {
                ws = new WebSocket(BINANCE_WS + streams)
                ws.onopen = () => { setCryptoLive(true); tries = 0 }
                ws.onclose = () => { setCryptoLive(false); if (!disposed) schedule() }
                ws.onerror = () => { try { ws && ws.close() } catch (e) {} }
                ws.onmessage = (ev) => {
                    try {
                        const m = JSON.parse(ev.data)
                        const d = m && m.data
                        if (!d || !d.s) return
                        setCryptoRows((prev) => ({ ...prev, [d.s]: { price: Number(d.c), chg: Number(d.P) } }))
                    } catch (e) {}
                }
            } catch (e) { schedule() }
        }
        const schedule = () => { if (disposed || tries >= 8) return; const delay = Math.min(15000, 1000 * Math.pow(2, tries)); tries++; retry = setTimeout(connect, delay) }
        connect()
        return () => { disposed = true; clearTimeout(retry); if (ws) { try { ws.onclose = null; ws.close() } catch (e) {} } }
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas || !commodityUrl) return
        let alive = true
        fetch(commodityUrl).then((r) => (r.ok ? r.json() : null))
            .then((d) => { const c = d && (d.commodities || d); if (alive && c && typeof c === "object") setExpo(c) }).catch(() => {})
        return () => { alive = false }
    }, [commodityUrl, onCanvas])

    const M = useMemo(() => (macro && (macro.macro || macro)) || null, [macro])
    const expoData = useMemo(() => {
        if (onCanvas) return { wti_oil: { label: "WTI 원유", note: "정유·항공·석유화학 — 원유 가격에 원가·매출 연관.", count: 68, stocks: [{ ticker: "051910", name: "LG화학", industry: "Specialty Chemicals" }, { ticker: "096770", name: "SK이노베이션", industry: "Oil & Gas Refining & Marketing" }] }, copper: { label: "구리", note: "비철금속·금속가공.", count: 17, stocks: [{ ticker: "010130", name: "고려아연", industry: "Other Industrial Metals & Mining" }] } }
        return expo
    }, [expo, onCanvas])

    const go = (ticker: string) => {
        if (onCanvas || typeof window === "undefined" || !ticker) return
        const p = (reportPath || DEFAULT_REPORT).replace(/\/+$/, "") || "/"
        window.location.href = p + "?q=" + encodeURIComponent(ticker)
    }

    const rows = useMemo(() => {
        const seed = (base: number, n: number, drift: number) => Array.from({ length: n }, (_, i) => base * (1 + Math.sin(i / 3) * 0.01 + (i / n) * drift))
        return GROUPS.map((g) => ({
            title: g.title,
            items: g.items.map((it) => {
                if (onCanvas) {
                    const demo: Record<string, [number, number]> = { kospi: [6820.6, -6.37], kosdaq: [791.84, -4.53], sp500: [7572.03, 1.08], nasdaq: [26259.91, 1.9], dow: [52568.99, 0.14], sox: [12717.2, 1.2], nikkei: [42180.0, 0.4], dax: [24992.32, -0.2], vix: [16.17, 2.31], usdkrw: [1531.5, 0.53], us_10y: [4.62, 0.0], us_2y: [3.84, 0.0], gold: [4070.8, -0.5], silver: [52.1, 0.8], copper: [4.62, 0.3], wti_oil: [80.09, -1.1], btc: [64286, 2.32], eth: [1878, 5.55], xrp: [2.41, 0.58], sol: [77.36, 1.6], doge: [0.3821, -1.04] }
                    const [v, cp] = demo[it.key] || [100, 0]
                    const dec = it.src === "binance" ? cryptoDec(v) : (it.dec ?? 2)
                    return { ...it, value: v, change_pct: cp, spark: seed(v, 24, cp / 100), dec, dataDate: "", hasVal: true, pending: false }
                }
                if (it.src === "binance") {
                    const cr = it.bsym ? cryptoRows[it.bsym] : undefined
                    const sp = it.bsym ? cryptoSpark[it.bsym] : undefined
                    const value = cr ? cr.price : undefined
                    const hasVal = value != null && isFinite(Number(value)) && Number(value) > 0
                    return { ...it, value, change_pct: cr ? cr.chg : undefined, spark: sp && sp.length >= 2 ? sp : null, dec: hasVal ? cryptoDec(Number(value)) : 2, dataDate: "", hasVal, pending: !hasVal && !cryptoLive }
                }
                // macro (전일 종가 값) — KR 지수 포함(yfinance). data_date = 실 종가 봉 날짜.
                const node = M ? M[it.mkey || it.key] : undefined
                const value = node && node.value
                const change_pct = node && (node.change_pct != null ? node.change_pct : node.change_percent)
                const sn = it.spark ? (M ? M[it.spark] : undefined) : undefined
                const arr = sn && Array.isArray(sn.sparkline) ? sn.sparkline.map((x: any) => Number(x)).filter((x: number) => isFinite(x)) : null
                const hasVal = value != null && isFinite(Number(value)) && Number(value) !== 0
                return { ...it, value, change_pct, dataDate: node && node.data_date, spark: arr && arr.length >= 2 ? arr : null, hasVal, pending: !hasVal && !macroLoaded }
            }).filter((it: any) => it.hasVal || it.pending),
        })).filter((g) => g.items.length > 0)
    }, [M, onCanvas, macroLoaded, cryptoRows, cryptoSpark, cryptoLive])

    const cols = w <= 0 ? 4 : w < 440 ? 2 : w < 700 ? 3 : w < 1000 ? 4 : 5
    const narrow = w > 0 && w < 560
    const pad = narrow ? 11 : 15

    const wrap: CSSProperties = {
        width: "100%", minHeight: "100%", overflowX: "hidden",
        background: C.bg, fontFamily: FONT, padding: `0 ${pad}px`, boxSizing: "border-box", color: C.ink,
    }

    const naverLink = (key: string) => {
        const u = NAVER_URL[key]
        if (!u) return null
        return (
            <a href={u} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}
                style={{ display: "inline-flex", alignItems: "center", gap: 2, fontSize: 9, fontWeight: 700, color: C.vg, textDecoration: "none", whiteSpace: "nowrap" }}>
                네이버 ↗
            </a>
        )
    }

    const card = (it: any) => {
        const cp = Number(it.change_pct)
        const col = !isFinite(cp) ? C.flat : cp > 0 ? C.up : cp < 0 ? C.down : C.flat
        const sign = isFinite(cp) && cp > 0 ? "+" : ""
        const live = it.src === "binance"
        const expoHit = it.src === "macro" && expoData && expoData[it.key] && Number(expoData[it.key].count) > 0
        const open = openCommodity === it.key
        const onClick = expoHit ? () => setOpenCommodity(open ? "" : it.key) : undefined
        return (
            <div key={it.key} onClick={onClick}
                style={{ background: open ? C.chipBg : C.card, borderRadius: 11, padding: "8px 10px", boxShadow: open ? "inset 0 1px 3px rgba(0,0,0,0.12)" : "0 1px 2px rgba(0,0,0,0.04)", display: "flex", alignItems: "center", gap: 9, minWidth: 0, cursor: expoHit ? "pointer" : "default" }}>
                {it.spark && <Spark data={it.spark} color={col} w={40} h={24} />}
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: C.sub, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {it.name}{expoHit && <span style={{ marginLeft: 4, fontSize: 9.5, fontWeight: 700, color: C.cPos }}>·{expoData[it.key].count}</span>}
                    </div>
                    <div style={{ fontSize: 15, fontWeight: 800, color: C.ink, letterSpacing: "-0.3px", marginTop: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{it.pre || ""}{fmtNum(it.value, it.dec ?? 2)}{it.unit || ""}</div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 0, minWidth: 0, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 11, fontWeight: 800, color: col, whiteSpace: "nowrap" }}>{isFinite(cp) ? `${sign}${cp.toFixed(2)}%` : "—"}</span>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}>
                            {live && <span style={{ width: 5, height: 5, borderRadius: "50%", background: C.live }} />}
                            <span style={{ fontSize: 9, fontWeight: 700, color: live ? C.live : C.faint, whiteSpace: "nowrap" }}>{live ? "실시간" : fmtCloseLabel(it.dataDate)}</span>
                        </span>
                        {!live && naverLink(it.key)}
                    </div>
                </div>
                {expoHit && <span style={{ flexShrink: 0, fontSize: 12, color: open ? C.cPos : C.faint, fontWeight: 700 }}>{open ? "−" : "›"}</span>}
            </div>
        )
    }

    const exposurePanel = () => {
        const e = expoData && openCommodity ? expoData[openCommodity] : null
        if (!e) return null
        const stocks = e.stocks || []
        return (
            <div style={{ background: C.card, borderRadius: 11, padding: "10px 12px", boxShadow: "0 1px 2px rgba(0,0,0,0.04)", marginTop: 8, marginBottom: 2 }}>
                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                    <span style={{ fontSize: 12.5, fontWeight: 800, color: C.ink }}>{e.label} — KR 노출 <span style={{ color: C.cPos }}>{e.count}</span></span>
                    <span onClick={() => setOpenCommodity("")} style={{ cursor: "pointer", fontSize: 13, color: C.faint, fontWeight: 700 }}>×</span>
                </div>
                <div style={{ fontSize: 10.5, color: C.sub, fontWeight: 600, marginTop: 2, lineHeight: 1.45 }}>{e.note}</div>
                {stocks.length === 0 ? (
                    <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 700, padding: "8px 0 2px" }}>KR 상장 노출 종목 없음 (제한적)</div>
                ) : (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                        {stocks.map((s: any) => (
                            <span key={s.ticker} onClick={() => go(s.ticker)} role="button" tabIndex={0}
                                style={{ display: "inline-flex", alignItems: "baseline", gap: 5, background: C.chipBg, borderRadius: 8, padding: "5px 9px", cursor: "pointer" }}>
                                <span style={{ fontSize: 12, fontWeight: 700, color: C.ink }}>{s.name}</span>
                                <span style={{ fontSize: 9.5, fontWeight: 600, color: C.faint }}>{s.industry}</span>
                            </span>
                        ))}
                    </div>
                )}
                <div style={{ fontSize: 9.5, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.45 }}>산업 멤버십 사실 · 시총순 · 누르면 리포트</div>
            </div>
        )
    }

    const isDark = onCanvas ? !!dark : themeDark
    const skBase = isDark ? "#222a33" : "#e9edf1"
    const skHi = isDark ? "#2d3742" : "#f3f5f7"
    const skBlock = (bw: number | string, bh: number, mt?: number): CSSProperties => ({
        width: bw, height: bh, marginTop: mt, borderRadius: 5, background: skBase,
        backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`,
        backgroundSize: "800px 100%", animation: "vsrShimmer 1.4s ease-in-out infinite",
    })
    const skTile = (key: string) => (
        <div key={key} style={{ background: C.card, borderRadius: 11, padding: "8px 10px", boxShadow: "0 1px 2px rgba(0,0,0,0.04)", display: "flex", alignItems: "center", gap: 9, minWidth: 0 }}>
            <div style={skBlock(40, 24)} />
            <div style={{ flex: 1, minWidth: 0 }}>
                <div style={skBlock("60%", 11)} />
                <div style={skBlock("80%", 15, 4)} />
                <div style={skBlock("40%", 11, 4)} />
            </div>
        </div>
    )
    const skeleton = () => {
        const skGroups: number[] = [2, 6, 4]
        let n = 0
        return (
            <div>
                {skGroups.map((cnt, gi) => (
                    <div key={gi} style={{ marginBottom: 12 }}>
                        <div style={skBlock(54, 11)} />
                        <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gap: 8, marginTop: 5 }}>
                            {Array.from({ length: cnt }).map((_, i) => (<div key={n++}>{skTile("s" + n)}</div>))}
                        </div>
                    </div>
                ))}
            </div>
        )
    }

    return (
        <div ref={rootRef} style={wrap}>
            <style>{`@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8, marginBottom: 10 }}>
                <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.4px" }}>글로벌 시세</span>
                <span style={{ fontSize: 10.5, fontWeight: 600, color: C.faint }}>크립토 실시간 · 나머지 전일 종가 + 네이버 실시간 링크</span>
            </div>

            {rows.length === 0 ? (
                skeleton()
            ) : (
                rows.map((g) => (
                    <div key={g.title} style={{ marginBottom: 12 }}>
                        <div style={{ fontSize: 11, fontWeight: 800, color: C.faint, padding: "0 2px 5px" }}>
                            {g.title}{g.title === "원자재" ? <span style={{ marginLeft: 6, fontWeight: 600, color: C.cPos }}>· 누르면 KR 노출 종목</span> : ""}
                        </div>
                        <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gap: 8 }}>
                            {g.items.map((it: any) => it.pending ? skTile("sk:" + it.key) : card(it))}
                        </div>
                        {g.title === "원자재" && exposurePanel()}
                    </div>
                ))
            )}

            <div style={{ fontSize: 10, color: C.faint, fontWeight: 600, marginTop: 2, lineHeight: 1.5 }}>
                크립토 = Binance 실시간 · 지수 레벨 = 전일 종가 '숫자'(사실) · 실시간은 네이버 딥링크 · 상승 빨강/하락 파랑
            </div>
        </div>
    )
}

addPropertyControls(PublicMarketBoard, {
    macroUrl: { type: ControlType.String, title: "Macro URL", defaultValue: DEFAULT_MACRO },
    commodityUrl: { type: ControlType.String, title: "Commodity URL", defaultValue: DEFAULT_EXPO },
    reportPath: { type: ControlType.String, title: "Report Path", defaultValue: DEFAULT_REPORT },
    refreshSec: { type: ControlType.Number, title: "Refresh(s)", defaultValue: 300, min: 60, max: 600, step: 30 },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})
