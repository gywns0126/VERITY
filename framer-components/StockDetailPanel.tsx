import { addPropertyControls, ControlType } from "framer"
import React, { Component, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import type { CSSProperties, ReactNode } from "react"

class PanelErrorBoundary extends Component<{ children: ReactNode }> {
    state = { error: null as string | null }
    static getDerivedStateFromError(e: Error) { return { error: e.message || "렌더 오류" } }
    render() {
        if (this.state.error) return (
            <div style={{ width: "100%", height: "100%", minHeight: 120, background: "#000", borderRadius: 20, border: "1px solid #222", display: "flex", flexDirection: "column" as const, alignItems: "center", justifyContent: "center", gap: 12, padding: 24, fontFamily: "'Inter', sans-serif" }}>
                <div style={{ color: "#F04452", fontSize: 14, fontWeight: 700 }}>컴포넌트 오류</div>
                <div style={{ color: "#8B95A1", fontSize: 11, textAlign: "center" as const, maxWidth: 280 }}>{this.state.error}</div>
                <button onClick={() => this.setState({ error: null })} style={{ padding: "8px 20px", borderRadius: 10, border: "1px solid #333", background: "#111", color: "#fff", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>다시 시도</button>
            </div>
        )
        return this.props.children
    }
}

const _font = "'Inter', 'Pretendard', -apple-system, sans-serif"
const UP = "#F04452"
const DOWN = "#3182F6"
const BG = "#000"
const CARD = "#111"
const BORDER = "#222"
const MUTED = "#8B95A1"
const ACCENT = "#B5FF19"

const FETCH_OPTS: RequestInit = { mode: "cors", credentials: "omit" }

function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

function fetchJson(url: string): Promise<any> {
    return fetch(bustUrl(url), { cache: "no-store", ...FETCH_OPTS })
        .then((r) => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            const ct = r.headers.get("content-type") || ""
            if (!ct.includes("json") && !ct.includes("text")) throw new Error("non-json response")
            return r.text()
        })
        .then((t) => {
            if (!t || !t.trim()) return null
            return JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null"))
        })
}

function normalizeApiBase(raw: string): string {
    let s = (raw || "").trim().replace(/\/+$/, "")
    if (!s) return ""
    if (!/^https?:\/\//i.test(s)) s = `https://${s.replace(/^\/+/, "")}`
    return s.replace(/\/+$/, "")
}

function fmtKRW(n: number): string {
    if (!Number.isFinite(n)) return "—"
    return `${Math.round(n).toLocaleString("ko-KR")}원`
}

function fmtNum(n: number): string {
    if (!Number.isFinite(n)) return "—"
    return Math.round(n).toLocaleString("ko-KR")
}

function fmtUSD(n: number): string {
    if (!Number.isFinite(n)) return "—"
    return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function fmtVol(n: number): string {
    if (!Number.isFinite(n) || n <= 0) return "—"
    if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`
    if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`
    return String(n)
}

// ── 차트 컴포넌트 ──

interface CandleData { o: number; h: number; l: number; c: number; up: boolean; vol?: number }

function fmtAxisPrice(n: number): string {
    if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`
    if (n >= 1e4) return `${(n / 1e4).toFixed(n >= 1e5 ? 0 : 1)}만`
    if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`
    return String(Math.round(n))
}

function LineChart({ data, color, width, height, volumes }: { data: number[]; color: string; width: number; height: number; volumes?: number[] }) {
    const w = Math.max(120, width), h = Math.max(80, height)
    if (!data || data.length < 2) return <div style={{ width: "100%", height: h, color: MUTED, fontSize: 12, display: "flex", alignItems: "center", justifyContent: "center" }}>차트 데이터 없음</div>

    const volH = volumes?.length ? h * 0.18 : 0
    const chartH = h - volH
    const padT = 12, padB = 20, padR = 52, padL = 4
    const usableW = w - padL - padR
    const usableH = chartH - padT - padB

    const mn = Math.min(...data), mx = Math.max(...data), rng = mx - mn || 1
    const xOf = (i: number) => padL + (i / (data.length - 1)) * usableW
    const yOf = (v: number) => padT + (1 - (v - mn) / rng) * usableH

    const pts = data.map((v, i) => `${xOf(i)},${yOf(v)}`).join(" ")
    const fillPts = `${xOf(0)},${padT + usableH} ${pts} ${xOf(data.length - 1)},${padT + usableH}`

    const gridCount = 4
    const gridLines: { y: number; label: string }[] = []
    for (let g = 0; g <= gridCount; g++) {
        const val = mn + (rng * g) / gridCount
        gridLines.push({ y: yOf(val), label: fmtAxisPrice(val) })
    }

    const maxVol = volumes?.length ? Math.max(...volumes, 1) : 1

    return (
        <svg width="100%" height="100%" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="xMidYMid meet" style={{ display: "block" }}>
            <defs>
                <linearGradient id="lineFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={color} stopOpacity={0.25} />
                    <stop offset="100%" stopColor={color} stopOpacity={0.02} />
                </linearGradient>
            </defs>
            {gridLines.map((g, i) => (
                <g key={i}>
                    <line x1={padL} y1={g.y} x2={w - padR + 4} y2={g.y} stroke="#1A1A1A" strokeWidth={1} />
                    <text x={w - padR + 8} y={g.y + 3.5} fill={MUTED} fontSize={9} fontFamily={_font}>{g.label}</text>
                </g>
            ))}
            <polygon points={fillPts} fill="url(#lineFill)" />
            <polyline points={pts} fill="none" stroke={color} strokeWidth={1.8} strokeLinejoin="round" strokeLinecap="round" />
            {data.length <= 60 && data.map((v, i) => (
                <circle key={i} cx={xOf(i)} cy={yOf(v)} r={data.length <= 20 ? 2.5 : 1.5} fill={color} />
            ))}
            {volumes && volumes.length > 0 && (
                <g>
                    <line x1={padL} y1={chartH} x2={w - padR + 4} y2={chartH} stroke="#1A1A1A" strokeWidth={1} />
                    {volumes.map((vol, i) => {
                        const barW = Math.max(1, usableW / volumes.length * 0.7)
                        const barH = (vol / maxVol) * (volH - 4)
                        const x = padL + (i / (volumes.length - 1)) * usableW - barW / 2
                        const clr = i > 0 && data[i] >= data[i - 1] ? UP : DOWN
                        return <rect key={i} x={x} y={h - barH - 2} width={barW} height={barH} fill={clr} opacity={0.5} rx={0.5} />
                    })}
                </g>
            )}
        </svg>
    )
}

function CandleChart({ candles, width, height }: { candles: CandleData[]; width: number; height: number }) {
    const w = Math.max(120, width), h = Math.max(80, height)
    if (!candles || candles.length < 2) return <div style={{ width: "100%", height: h, color: MUTED, fontSize: 12, display: "flex", alignItems: "center", justifyContent: "center" }}>차트 데이터 없음</div>

    const hasVol = candles.some(c => (c.vol || 0) > 0)
    const volH = hasVol ? h * 0.18 : 0
    const chartH = h - volH
    const padT = 12, padB = 8, padR = 52, padL = 4
    const usableW = w - padL - padR
    const usableH = chartH - padT - padB

    const mn = Math.min(...candles.map(c => c.l)), mx = Math.max(...candles.map(c => c.h)), rng = mx - mn || 1
    const step = usableW / candles.length
    const gap = Math.max(1, step * 0.15)
    const bodyW = Math.max(1.5, step - gap)
    const xC = (i: number) => padL + i * step + step / 2
    const yOf = (v: number) => padT + (1 - (v - mn) / rng) * usableH

    const gridCount = 4
    const gridLines: { y: number; label: string }[] = []
    for (let g = 0; g <= gridCount; g++) {
        const val = mn + (rng * g) / gridCount
        gridLines.push({ y: yOf(val), label: fmtAxisPrice(val) })
    }

    const ma5 = candles.length >= 5 ? candles.map((_, i, arr) => {
        if (i < 4) return null
        const sum = arr.slice(i - 4, i + 1).reduce((s, c) => s + c.c, 0)
        return { x: xC(i), y: yOf(sum / 5) }
    }).filter(Boolean) as { x: number; y: number }[] : []

    const ma20 = candles.length >= 20 ? candles.map((_, i, arr) => {
        if (i < 19) return null
        const sum = arr.slice(i - 19, i + 1).reduce((s, c) => s + c.c, 0)
        return { x: xC(i), y: yOf(sum / 20) }
    }).filter(Boolean) as { x: number; y: number }[] : []

    const maxVol = hasVol ? Math.max(...candles.map(c => c.vol || 0), 1) : 1

    return (
        <svg width="100%" height="100%" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="xMidYMid meet" style={{ display: "block" }}>
            {gridLines.map((g, i) => (
                <g key={i}>
                    <line x1={padL} y1={g.y} x2={w - padR + 4} y2={g.y} stroke="#1A1A1A" strokeWidth={1} />
                    <text x={w - padR + 8} y={g.y + 3.5} fill={MUTED} fontSize={9} fontFamily={_font}>{g.label}</text>
                </g>
            ))}
            {candles.map((c, i) => {
                const x = xC(i), yH = yOf(c.h), yL = yOf(c.l), yO = yOf(c.o), yClose = yOf(c.c)
                const bT = Math.min(yO, yClose), bB = Math.max(yO, yClose), bH = Math.max(1, bB - bT)
                const clr = c.up ? UP : DOWN
                return (
                    <g key={i}>
                        <line x1={x} y1={yH} x2={x} y2={yL} stroke={clr} strokeWidth={1} />
                        <rect x={x - bodyW / 2} y={bT} width={bodyW} height={bH} fill={clr} opacity={0.95} rx={0.5} />
                    </g>
                )
            })}
            {ma5.length > 1 && (
                <polyline points={ma5.map(p => `${p.x},${p.y}`).join(" ")} fill="none" stroke="#FFD600" strokeWidth={1} strokeOpacity={0.7} />
            )}
            {ma20.length > 1 && (
                <polyline points={ma20.map(p => `${p.x},${p.y}`).join(" ")} fill="none" stroke="#00D4FF" strokeWidth={1} strokeOpacity={0.6} />
            )}
            {hasVol && (
                <g>
                    <line x1={padL} y1={chartH} x2={w - padR + 4} y2={chartH} stroke="#1A1A1A" strokeWidth={1} />
                    {candles.map((c, i) => {
                        const vol = c.vol || 0
                        const barH = (vol / maxVol) * (volH - 4)
                        const x = xC(i) - bodyW / 2
                        return <rect key={i} x={x} y={h - barH - 2} width={bodyW} height={barH} fill={c.up ? UP : DOWN} opacity={0.4} rx={0.5} />
                    })}
                </g>
            )}
        </svg>
    )
}

interface OrderRow { price: number; ask_vol: number | null; bid_vol: number | null; pct_label: string; highlight?: boolean }

type TabId = "chart" | "order" | "trade"

// ── 메인 Props ──

const DEFAULT_API = "https://vercel-api-alpha-umber.vercel.app"
const DEFAULT_PORTFOLIO = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"
const DEFAULT_RELAY = "https://verity-production-1e44.up.railway.app"

interface Props {
    apiBase: string
    portfolioUrl: string
    realtimeServerUrl: string
    market: "kr" | "us"
}

function StockDetailPanelInner(props: Props) {
    const api = normalizeApiBase(props.apiBase) || normalizeApiBase(DEFAULT_API)
    const portfolioUrl = (props.portfolioUrl || "").trim() || DEFAULT_PORTFOLIO
    const relayUrl = normalizeApiBase(props.realtimeServerUrl) || normalizeApiBase(DEFAULT_RELAY)
    const market: "kr" | "us" = props.market || "kr"
    const isUS = market === "us"

    // ── 검색 상태 ──
    const [query, setQuery] = useState("")
    const [suggestions, setSuggestions] = useState<any[]>([])
    const [selectedStock, setSelectedStock] = useState<{ ticker: string; name: string; market: string } | null>(null)
    const [searchLoading, setSearchLoading] = useState(false)
    const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
    const marketRef = useRef(market)
    marketRef.current = market

    // ── 데이터 상태 ──
    const [portfolio, setPortfolio] = useState<any>(null)
    const [tab, setTab] = useState<TabId>("chart")
    const [tfPick, setTfPick] = useState<"실시간" | "1주" | "1달" | "3달" | "1년">("실시간")

    // ── KIS 직접 조회 데이터 ──
    const [kisData, setKisData] = useState<any>(null)
    const [kisLoading, setKisLoading] = useState(false)

    // ── SSE 실시간 ──
    const [sseConnected, setSseConnected] = useState(false)
    const [liveOrderbook, setLiveOrderbook] = useState<any>(null)
    const [liveTrades, setLiveTrades] = useState<any[]>([])
    const [liveStrength, setLiveStrength] = useState(0)
    const [liveCandles, setLiveCandles] = useState<CandleData[]>([])

    // ── 차트 사이즈 ──
    const chartBoxRef = useRef<HTMLDivElement | null>(null)
    const [chartBox, setChartBox] = useState({ w: 600, h: 300 })

    // ── 주문 상태 ──
    const [orderSide, setOrderSide] = useState<"buy" | "sell">("buy")
    const [orderQty, setOrderQty] = useState("")
    const [orderPrice, setOrderPrice] = useState("")
    const [orderType, setOrderType] = useState<"00" | "01">("01")
    const [orderSubmitting, setOrderSubmitting] = useState(false)
    const [orderResult, setOrderResult] = useState<{ success: boolean; message: string } | null>(null)
    const [showConfirm, setShowConfirm] = useState(false)

    // ── 포트폴리오 로드 ──
    useEffect(() => {
        const u = portfolioUrl.trim()
        if (!u) return
        fetchJson(u).then(setPortfolio).catch(console.error)
        const iv = setInterval(() => fetchJson(u).then(setPortfolio).catch(console.error), 5 * 60_000)
        return () => clearInterval(iv)
    }, [portfolioUrl])

    // ── 검색 ──
    const handleSearch = useCallback((q: string) => {
        setQuery(q)
        if (!q.trim()) { setSuggestions([]); return }
        if (searchTimer.current) clearTimeout(searchTimer.current)
        searchTimer.current = setTimeout(() => {
            const mkt = marketRef.current === "us" ? "us" : "kr"
            fetch(`${api}/api/search?q=${encodeURIComponent(q.trim())}&limit=8&market=${mkt}`, FETCH_OPTS)
                .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
                .then(items => { if (Array.isArray(items)) setSuggestions(items) })
                .catch(() => setSuggestions([]))
        }, 200)
    }, [api])

    const selectStock = useCallback((ticker: string, name: string, mkt: string) => {
        setSelectedStock({ ticker, name, market: mkt })
        setQuery(name)
        setSuggestions([])
        setTab("chart")
        setTfPick("실시간")
        setOrderResult(null)
        setLiveOrderbook(null)
        setLiveTrades([])
        setLiveCandles([])
    }, [])

    // ── 종목 선택 시 KIS API로 데이터 즉시 조회 ──
    useEffect(() => {
        if (!selectedStock || isUS) return
        const ticker = selectedStock.ticker.replace(/\D/g, "").padStart(6, "0")
        if (!ticker || ticker === "000000") return

        setKisLoading(true)
        setKisData(null)
        fetchJson(`${api}/api/chart?ticker=${ticker}&type=all`)
            .then(data => {
                if (data && !data.error) {
                    setKisData(data)
                    if (data.orderbook && !liveOrderbook) setLiveOrderbook(data.orderbook)
                    if (Array.isArray(data.trades) && data.trades.length > 0 && liveTrades.length === 0) setLiveTrades(data.trades)
                }
            })
            .catch(() => {})
            .finally(() => setKisLoading(false))
    }, [selectedStock, api, isUS])

    // ── KIS 스냅샷에서 데이터 추출 (portfolio.json 폴백) ──
    const kisSnap = useMemo(() => {
        if (!selectedStock || !portfolio?.kis_snapshots) return null
        const t6 = selectedStock.ticker.replace(/\D/g, "").padStart(6, "0")
        return portfolio.kis_snapshots[t6] || null
    }, [selectedStock, portfolio])

    const currentPrice = useMemo(() => {
        if (liveTrades.length > 0) {
            const p = Number(liveTrades[0]?.price)
            if (Number.isFinite(p) && p > 0) return p
        }
        if (kisData?.price?.price) return Number(kisData.price.price)
        if (kisSnap?.price?.price) return Number(kisSnap.price.price)
        const rec = portfolio?.recommendations?.find((r: any) => {
            const t = String(r?.ticker || "").replace(/\D/g, "").padStart(6, "0")
            const st = selectedStock?.ticker.replace(/\D/g, "").padStart(6, "0")
            return t === st
        })
        if (rec?.price) return Number(rec.price)
        return 0
    }, [liveTrades, kisData, kisSnap, portfolio, selectedStock])

    const prevClose = useMemo(() => {
        if (kisData?.price?.prev_close) return Number(kisData.price.prev_close)
        if (kisSnap?.price) return Number(kisSnap.price.prev_close || kisSnap.price.price * 0.99) || 0
        return 0
    }, [kisData, kisSnap])

    const changePct = prevClose > 0 ? ((currentPrice - prevClose) / prevClose * 100) : 0
    const changeAmt = prevClose > 0 ? (currentPrice - prevClose) : 0
    const dirColor = changePct >= 0 ? UP : DOWN

    // ── 차트 데이터 ──
    const chartLine = useMemo((): number[] => {
        // KIS API 일봉 우선
        if (kisData?.daily && Array.isArray(kisData.daily) && kisData.daily.length > 1) {
            return kisData.daily.map((c: any) => c.close || 0).filter((v: number) => v > 0)
        }
        if (kisSnap?.chart && Array.isArray(kisSnap.chart)) {
            return kisSnap.chart.map((c: any) => c.close || 0).filter((v: number) => v > 0)
        }
        const rec = portfolio?.recommendations?.find((r: any) => {
            const t = String(r?.ticker || "").replace(/\D/g, "").padStart(6, "0")
            const st = selectedStock?.ticker.replace(/\D/g, "").padStart(6, "0")
            return t === st
        })
        if (rec?.sparkline?.length > 1) return rec.sparkline.map(Number).filter((v: number) => v > 0)
        return []
    }, [kisData, kisSnap, portfolio, selectedStock])

    const chartCandles = useMemo((): CandleData[] => {
        // KIS API 일봉 OHLCV 우선
        if (kisData?.daily && Array.isArray(kisData.daily) && kisData.daily.length > 1) {
            return kisData.daily.map((c: any) => ({
                o: c.open || 0, h: c.high || 0, l: c.low || 0, c: c.close || 0,
                up: (c.close || 0) >= (c.open || 0),
                vol: c.volume || 0,
            })).filter((c: CandleData) => c.h > 0)
        }
        if (kisSnap?.chart && Array.isArray(kisSnap.chart) && kisSnap.chart.length > 1) {
            return kisSnap.chart.map((c: any) => ({
                o: c.open || 0, h: c.high || 0, l: c.low || 0, c: c.close || 0,
                up: (c.close || 0) >= (c.open || 0),
                vol: c.volume || c.vol || 0,
            })).filter((c: CandleData) => c.h > 0)
        }
        if (chartLine.length >= 2) {
            const tail = chartLine.slice(-Math.min(90, chartLine.length))
            return tail.slice(1).map((c, i) => {
                const o = tail[i]
                const spread = Math.abs(c - o) * 0.15 || o * 0.003
                return { o, h: Math.max(o, c) + spread, l: Math.min(o, c) - spread, c, up: c >= o, vol: 0 }
            })
        }
        return []
    }, [kisData, kisSnap, chartLine])

    // KIS API 분봉 → CandleData 변환
    const kisMinuteCandles = useMemo((): CandleData[] => {
        if (!kisData?.minute || !Array.isArray(kisData.minute)) return []
        return kisData.minute.map((c: any) => ({
            o: c.open || 0, h: c.high || 0, l: c.low || 0, c: c.close || 0,
            up: (c.close || 0) >= (c.open || 0),
            vol: c.volume || 0,
        })).filter((c: CandleData) => c.h > 0)
    }, [kisData])

    const _findRec = useCallback(() => {
        return portfolio?.recommendations?.find((r: any) => {
            const t = String(r?.ticker || "").replace(/\D/g, "").padStart(6, "0")
            const st = selectedStock?.ticker.replace(/\D/g, "").padStart(6, "0")
            return t === st
        })
    }, [portfolio, selectedStock])

    const chartData = useMemo(() => {
        if (tfPick === "실시간") {
            if (liveCandles.length >= 2) return liveCandles.map(c => c.c)
            if (kisMinuteCandles.length >= 2) return kisMinuteCandles.map(c => c.c)
            return chartLine.length >= 2 ? chartLine : []
        }
        const rec = _findRec()
        const weekly: number[] = rec?.sparkline_weekly || []
        switch (tfPick) {
            case "1주": return chartLine
            case "1달": return chartLine.length > 20 ? chartLine.slice(-20) : chartLine
            case "3달": return weekly.length > 13 ? weekly.slice(-65) : (chartLine.length > 1 ? chartLine : weekly)
            case "1년": return weekly.length > 1 ? weekly : chartLine
            default: return chartLine
        }
    }, [tfPick, chartLine, _findRec, liveCandles, kisMinuteCandles])

    const chartVolumes = useMemo((): number[] => {
        if (kisData?.daily && Array.isArray(kisData.daily)) {
            return kisData.daily.map((c: any) => c.volume || 0)
        }
        if (kisSnap?.chart && Array.isArray(kisSnap.chart)) {
            return kisSnap.chart.map((c: any) => c.volume || c.vol || 0)
        }
        return []
    }, [kisData, kisSnap])

    const finalCandles = useMemo(() => {
        const base = chartCandles.filter(c => c.h > 0 && c.l > 0)

        const appendRtCandle = (arr: CandleData[]) => {
            if (!sseConnected || liveTrades.length < 4 || arr.length === 0) return arr
            const last = arr[arr.length - 1]
            const rtp = liveTrades.map(t => Number(t?.price)).filter(p => Number.isFinite(p) && p > 0)
            if (rtp.length === 0) return arr
            return [...arr, { o: last.c, h: Math.max(last.c, ...rtp), l: Math.min(last.c, ...rtp), c: rtp[0], up: rtp[0] >= last.c, vol: 0 }]
        }

        switch (tfPick) {
            case "실시간":
                if (liveCandles.length >= 2) return liveCandles
                if (kisMinuteCandles.length >= 2) return kisMinuteCandles
                return base.length >= 2 ? base.slice(-5) : []
            case "1주":
                return appendRtCandle(base.slice(-5))
            case "1달":
                return appendRtCandle(base.slice(-22))
            default:
                return []
        }
    }, [chartCandles, liveTrades, sseConnected, tfPick, liveCandles, kisMinuteCandles])

    // 호가 합성용 호가단위 계산
    const _getTickSize = useCallback((price: number): number => {
        if (price >= 500000) return 1000
        if (price >= 100000) return 500
        if (price >= 50000) return 100
        if (price >= 10000) return 50
        if (price >= 5000) return 10
        if (price >= 1000) return 5
        return 1
    }, [])

    // ── 호가 데이터 (실시간 → KIS API → 종가 기반 합성) ──
    const orderbookRows = useMemo((): OrderRow[] => {
        const rows: OrderRow[] = []
        const cp = currentPrice
        if (cp <= 0) return rows

        const ob = liveOrderbook
        if (ob && (ob.asks?.length > 0 || ob.bids?.length > 0)) {
            const asks = (ob.asks || []).slice(-5)
            const bids = (ob.bids || []).slice(0, 5)
            for (const r of asks) {
                const pct = cp > 0 ? (((r.price - cp) / cp) * 100).toFixed(2) : "0.00"
                rows.push({ price: r.price, ask_vol: r.volume, bid_vol: null, pct_label: `+${pct}%` })
            }
            rows.push({ price: cp, ask_vol: null, bid_vol: null, pct_label: "0.0%", highlight: true })
            for (const r of bids) {
                const pct = cp > 0 ? (((r.price - cp) / cp) * 100).toFixed(2) : "0.00"
                rows.push({ price: r.price, ask_vol: null, bid_vol: r.volume, pct_label: `${pct}%` })
            }
        } else {
            // 실시간/API 호가 없으면 현재가 기반으로 합성 호가 생성
            const tick = _getTickSize(cp)
            for (let i = 5; i >= 1; i--) {
                const p = cp + tick * i
                const pct = ((p - cp) / cp * 100).toFixed(2)
                const vol = Math.round(1000 + Math.random() * 4000)
                rows.push({ price: p, ask_vol: vol, bid_vol: null, pct_label: `+${pct}%` })
            }
            rows.push({ price: cp, ask_vol: null, bid_vol: null, pct_label: "0.0%", highlight: true })
            for (let i = 1; i <= 5; i++) {
                const p = cp - tick * i
                const pct = ((p - cp) / cp * 100).toFixed(2)
                const vol = Math.round(1000 + Math.random() * 4000)
                rows.push({ price: p, ask_vol: null, bid_vol: vol, pct_label: `${pct}%` })
            }
        }
        return rows
    }, [liveOrderbook, currentPrice])

    // ── 체결 합성 (일봉 데이터 기반) ──
    const syntheticTrades = useMemo(() => {
        if (liveTrades.length > 0) return null
        const cp = currentPrice
        if (cp <= 0) return null
        const daily = kisData?.daily
        if (!Array.isArray(daily) || daily.length < 2) return null

        const recent = daily.slice(-5)
        const trades: any[] = []
        for (const d of recent) {
            const c = d.close || 0, o = d.open || 0, h = d.high || 0, l = d.low || 0, v = d.volume || 0
            if (c <= 0) continue
            const side = c >= o ? "buy" : "sell"
            const change = prevClose > 0 ? c - prevClose : 0
            const pct = prevClose > 0 ? ((c - prevClose) / prevClose * 100) : 0
            const date = d.date || ""
            const dateFmt = date.length >= 8 ? `${date.slice(4, 6)}/${date.slice(6, 8)}` : date
            trades.push({ time: dateFmt, price: c, change: Math.round(change), change_pct: Math.round(pct * 100) / 100, volume: v, side })
            if (h > c) trades.push({ time: dateFmt, price: h, change: 0, change_pct: 0, volume: Math.round(v * 0.15), side: "buy" })
            if (l < c && l > 0) trades.push({ time: dateFmt, price: l, change: 0, change_pct: 0, volume: Math.round(v * 0.1), side: "sell" })
        }
        return trades.slice(0, 20)
    }, [liveTrades, currentPrice, kisData, prevClose])

    // ── Railway SSE 연결 (토픽 기반, 분봉 수신) ──
    useEffect(() => {
        if (!relayUrl || !selectedStock || isUS) return
        const ticker = selectedStock.ticker.replace(/\D/g, "").padStart(6, "0")
        if (!ticker || ticker === "000000") return

        setSseConnected(false)
        setLiveOrderbook(null)
        setLiveTrades([])
        setLiveStrength(0)
        setLiveCandles([])

        let es: EventSource | null = null
        let errCount = 0
        try {
            es = new EventSource(`${relayUrl}/stream/${ticker}`)
            es.onopen = () => { setSseConnected(true); errCount = 0 }
            es.onerror = () => {
                errCount++
                setSseConnected(false)
                if (errCount > 5 && es) { es.close(); es = null }
            }

            es.addEventListener("snapshot", (e: MessageEvent) => {
                try {
                    const d = JSON.parse(e.data)
                    if (d.orderbook) setLiveOrderbook(d.orderbook)
                    if (Array.isArray(d.trades) && d.trades.length > 0) setLiveTrades(d.trades)
                    const str = Number(d?.strength_pct)
                    if (Number.isFinite(str) && str > 0) setLiveStrength(str)
                } catch {}
            })

            es.addEventListener("candles", (e: MessageEvent) => {
                try {
                    const arr = JSON.parse(e.data)
                    if (Array.isArray(arr) && arr.length > 0) {
                        setLiveCandles(arr.map((c: any) => ({
                            o: c.o, h: c.h, l: c.l, c: c.c,
                            up: c.c >= c.o,
                            vol: c.vol || 0,
                        })))
                    }
                } catch {}
            })

            es.addEventListener("candle", (e: MessageEvent) => {
                try {
                    const c = JSON.parse(e.data)
                    if (c.o && c.h && c.l && c.c) {
                        setLiveCandles(prev => {
                            const nd: CandleData = { o: c.o, h: c.h, l: c.l, c: c.c, up: c.c >= c.o, vol: c.vol || 0 }
                            return [...prev, nd].slice(-240)
                        })
                    }
                } catch {}
            })

            es.addEventListener("orderbook", (e: MessageEvent) => {
                try {
                    const ob = JSON.parse(e.data)
                    setLiveOrderbook(ob)
                } catch {}
            })

            es.addEventListener("trade", (e: MessageEvent) => {
                try {
                    const t = JSON.parse(e.data)
                    setLiveTrades(prev => [{ ...t, ticker }, ...prev].slice(0, 30))
                    const str = Number(t?.strength_pct)
                    if (Number.isFinite(str) && str > 0) setLiveStrength(str)
                    // 실시간 틱으로 마지막 캔들 업데이트
                    const price = Number(t.price)
                    const vol = Number(t.volume) || 0
                    if (Number.isFinite(price) && price > 0) {
                        setLiveCandles(prev => {
                            if (prev.length === 0) return prev
                            const last = { ...prev[prev.length - 1] }
                            last.h = Math.max(last.h, price)
                            last.l = Math.min(last.l, price)
                            last.c = price
                            last.up = price >= last.o
                            last.vol = (last.vol || 0) + vol
                            return [...prev.slice(0, -1), last]
                        })
                    }
                } catch {}
            })
        } catch {}

        return () => { if (es) { es.close(); setSseConnected(false) } }
    }, [relayUrl, selectedStock, isUS])

    // ── 차트 리사이즈 ──
    useLayoutEffect(() => {
        const el = chartBoxRef.current
        if (!el) return
        const measure = () => {
            const r = el.getBoundingClientRect()
            setChartBox({ w: Math.max(64, Math.floor(r.width)), h: Math.max(64, Math.floor(r.height)) })
        }
        measure()
        if (typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver(() => measure())
        ro.observe(el)
        return () => ro.disconnect()
    }, [tab, selectedStock])

    // ── 주문 실행 ──
    const submitOrder = useCallback(() => {
        if (!selectedStock || orderSubmitting) return
        const qty = parseInt(orderQty, 10)
        if (!qty || qty <= 0) { setOrderResult({ success: false, message: "수량을 입력하세요" }); return }
        const price = orderType === "01" ? 0 : parseInt(orderPrice, 10) || 0
        if (orderType === "00" && price <= 0) { setOrderResult({ success: false, message: "가격을 입력하세요" }); return }

        setOrderSubmitting(true)
        setOrderResult(null)

        fetch(`${api}/api/order`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                ticker: selectedStock.ticker,
                side: orderSide,
                qty,
                price,
                order_type: orderType,
                market,
            }),
            ...FETCH_OPTS,
        })
            .then(r => r.json())
            .then(data => {
                setOrderResult({ success: data.success, message: data.message || (data.success ? "주문 접수 완료" : "주문 실패") })
                setShowConfirm(false)
            })
            .catch(e => {
                setOrderResult({ success: false, message: String(e?.message || "네트워크 오류") })
                setShowConfirm(false)
            })
            .finally(() => setOrderSubmitting(false))
    }, [selectedStock, orderSide, orderQty, orderPrice, orderType, orderSubmitting, api, market])

    const candleCount = liveCandles.length || kisMinuteCandles.length
    const realtimeLabel = sseConnected ? (candleCount > 0 ? `실시간 · ${candleCount}봉` : "실시간") : (kisData ? "KIS 조회" : (relayUrl ? "연결 중..." : "정적"))
    const realtimeColor = sseConnected ? "#22C55E" : (kisData ? "#60A5FA" : "#F59E0B")

    const tabs: { id: TabId; label: string }[] = [
        { id: "chart", label: "차트" },
        { id: "order", label: "호가/체결" },
        { id: "trade", label: "주문" },
    ]

    return (
        <div style={wrapStyle}>
            {/* ── 검색 바 ── */}
            <div style={searchBarStyle}>
                <svg width={16} height={16} viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0 }}>
                    <circle cx={11} cy={11} r={7} stroke="#555" strokeWidth={2} /><path d="M16 16L20 20" stroke="#555" strokeWidth={2} strokeLinecap="round" />
                </svg>
                <input
                    type="text"
                    value={query}
                    onChange={e => handleSearch(e.target.value)}
                    onKeyDown={e => { if (e.key === "Escape") { setQuery(""); setSuggestions([]) } }}
                    placeholder={isUS ? "종목명 또는 티커 (예: AAPL, 테슬라)..." : "종목명 또는 코드 검색 (예: 삼성전자, 005930)..."}
                    style={searchInputStyle}
                />
                {query && (
                    <button onClick={() => { setQuery(""); setSuggestions([]) }} style={{ background: "none", border: "none", color: "#555", cursor: "pointer", fontSize: 16, padding: 0 }}>✕</button>
                )}
            </div>

            {/* ── 검색 결과 드롭다운 ── */}
            {suggestions.length > 0 && (
                <div style={suggestionsStyle}>
                    {suggestions.map((sg: any) => (
                        <div key={sg.ticker} onClick={() => selectStock(sg.ticker, sg.name, sg.market || market)}
                            style={suggestionItemStyle}
                            onMouseEnter={e => (e.currentTarget.style.background = "#1A1A1A")}
                            onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
                            <span style={{ color: "#fff", fontSize: 13, fontWeight: 600 }}>{sg.name}</span>
                            <span style={{ color: "#555", fontSize: 10, marginLeft: 6 }}>{sg.ticker}</span>
                            <span style={{ color: "#444", fontSize: 10, marginLeft: "auto" }}>{sg.market}</span>
                        </div>
                    ))}
                </div>
            )}

            {!selectedStock ? (
                <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: MUTED, fontSize: 14, padding: 40, textAlign: "center" as const }}>
                    종목을 검색하여 선택하세요
                </div>
            ) : (
                <>
                    {/* ── 종목 헤더 ── */}
                    <div style={headerStyle}>
                        <div style={{ minWidth: 0, flex: 1 }}>
                            <div style={{ color: "#fff", fontSize: "clamp(15px, 3.8vw, 22px)", fontWeight: 800, lineHeight: 1.2 }}>{selectedStock.name}</div>
                            <div style={{ color: MUTED, fontSize: 12, marginTop: 4 }}>
                                {selectedStock.ticker}
                                <span style={{ marginLeft: 8, fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 999, border: `1px solid ${realtimeColor}`, color: realtimeColor }}>{kisLoading ? "로딩..." : realtimeLabel}</span>
                            </div>
                        </div>
                        <div style={{ textAlign: "right" as const, flexShrink: 0 }}>
                            <div style={{ color: "#fff", fontSize: "clamp(17px, 5.2vw, 32px)", fontWeight: 800, lineHeight: 1.15 }}>
                                {isUS ? fmtUSD(currentPrice) : fmtKRW(currentPrice)}
                            </div>
                            {prevClose > 0 && (
                                <div style={{ color: dirColor, fontSize: "clamp(11px, 2.8vw, 15px)", fontWeight: 700, marginTop: 4 }}>
                                    {changePct >= 0 ? "+" : ""}{isUS ? fmtUSD(changeAmt).replace("$", "") : fmtNum(changeAmt)}
                                    {" "}({changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%)
                                </div>
                            )}
                        </div>
                    </div>

                    {/* ── 탭 ── */}
                    <div style={tabRowStyle}>
                        {tabs.map(t => (
                            <button key={t.id} type="button" onClick={() => setTab(t.id)}
                                style={{ ...tabBtnStyle, color: tab === t.id ? "#fff" : MUTED, borderBottom: tab === t.id ? "2px solid #fff" : "2px solid transparent" }}>
                                {t.label}
                            </button>
                        ))}
                    </div>

                    {/* ── 본문 ── */}
                    <div style={bodyStyle}>
                        {/* ── 차트 탭 ── */}
                        {tab === "chart" && (
                            <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, width: "100%" }}>
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10, flexShrink: 0, gap: 8, flexWrap: "wrap" as const }}>
                                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                        <span style={{ color: ACCENT, fontSize: 12, fontWeight: 700 }}>차트</span>
                                        {tfPick === "실시간" && sseConnected && (
                                            <span style={{ fontSize: 9, color: "#22C55E", fontWeight: 700, padding: "2px 6px", borderRadius: 4, background: "rgba(34,197,94,0.15)", animation: "pulse 2s infinite" }}>● LIVE</span>
                                        )}
                                    </div>
                                    <div style={{ display: "flex", gap: 4 }}>
                                        {(["실시간", "1주", "1달", "3달", "1년"] as const).map(tf => (
                                            <button key={tf} type="button" onClick={() => setTfPick(tf)}
                                                style={{ border: "none", borderRadius: 8, padding: "6px 10px", fontSize: 11, fontWeight: 600, cursor: "pointer", fontFamily: _font, background: tfPick === tf ? "#2A2A2A" : "transparent", color: tfPick === tf ? (tf === "실시간" ? "#22C55E" : "#fff") : MUTED }}>
                                                {tf === "실시간" ? "1분" : tf}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                                <div ref={chartBoxRef} style={{ flex: 1, minHeight: 200, width: "100%", position: "relative" as const }}>
                                    {(tfPick === "실시간" || tfPick === "1주" || tfPick === "1달") && finalCandles.length >= 2
                                        ? <CandleChart candles={finalCandles} width={chartBox.w} height={chartBox.h} />
                                        : <LineChart data={chartData} color={dirColor} width={chartBox.w} height={chartBox.h} volumes={chartVolumes.length === chartData.length ? chartVolumes : undefined} />}
                                </div>
                                {(chartData.length >= 2 || finalCandles.length >= 2) && (() => {
                                    const useCandles = (tfPick === "실시간" || tfPick === "1주" || tfPick === "1달") && finalCandles.length >= 2
                                    const hi = useCandles ? Math.max(...finalCandles.map(c => c.h)) : Math.max(...chartData)
                                    const lo = useCandles ? Math.min(...finalCandles.map(c => c.l)) : Math.min(...chartData)
                                    return (
                                        <div style={{ marginTop: 8, display: "flex", gap: 16, flexShrink: 0, alignItems: "center", flexWrap: "wrap" as const }}>
                                            <span style={{ color: UP, fontSize: 11, fontWeight: 600 }}>H {isUS ? fmtUSD(hi) : fmtKRW(hi)}</span>
                                            <span style={{ color: DOWN, fontSize: 11, fontWeight: 600 }}>L {isUS ? fmtUSD(lo) : fmtKRW(lo)}</span>
                                            {tfPick === "실시간" && (liveCandles.length > 0 || kisMinuteCandles.length > 0) && (
                                                <span style={{ color: liveCandles.length > 0 ? "#22C55E" : "#60A5FA", fontSize: 10, fontWeight: 600, marginLeft: "auto" }}>
                                                    {liveCandles.length > 0 ? `LIVE 1분봉 · ${liveCandles.length}개` : `분봉 · ${kisMinuteCandles.length}개`}
                                                </span>
                                            )}
                                            {(tfPick === "1주" || tfPick === "1달") && finalCandles.length >= 5 && (
                                                <>
                                                    <span style={{ color: "#FFD600", fontSize: 10, fontWeight: 600 }}>— MA5</span>
                                                    {finalCandles.length >= 20 && <span style={{ color: "#00D4FF", fontSize: 10, fontWeight: 600 }}>— MA20</span>}
                                                </>
                                            )}
                                        </div>
                                    )
                                })()}
                            </div>
                        )}

                        {/* ── 호가/체결 탭 ── */}
                        {tab === "order" && (
                            <div style={{ width: "100%", minWidth: 0 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 10 }}>
                                    {sseConnected ? (
                                        <>
                                            <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#22C55E", boxShadow: "0 0 6px #22C55E" }} />
                                            <span style={{ color: "#22C55E", fontSize: 10, fontWeight: 600 }}>실시간</span>
                                        </>
                                    ) : (
                                        <>
                                            <div style={{ width: 6, height: 6, borderRadius: "50%", background: liveOrderbook ? "#60A5FA" : "#F59E0B" }} />
                                            <span style={{ color: liveOrderbook ? "#60A5FA" : "#F59E0B", fontSize: 10, fontWeight: 600 }}>
                                                {liveOrderbook ? "KIS 조회" : "종가 기준"}
                                            </span>
                                        </>
                                    )}
                                    {liveStrength > 0 && (
                                        <span style={{ fontSize: 11, fontWeight: 800, color: liveStrength >= 100 ? UP : DOWN, background: liveStrength >= 100 ? "rgba(240,68,82,0.15)" : "rgba(49,130,246,0.15)", padding: "3px 8px", borderRadius: 6, marginLeft: "auto" }}>
                                            체결강도 {liveStrength}%
                                        </span>
                                    )}
                                </div>

                                <div style={{ color: ACCENT, fontSize: 11, fontWeight: 700, marginBottom: 10 }}>호가</div>
                                {orderbookRows.length > 0 && (
                                    <div style={{ marginBottom: 16 }}>
                                        {orderbookRows.map((row, i) => {
                                            const isAsk = row.ask_vol != null && row.ask_vol > 0
                                            const isBid = row.bid_vol != null && row.bid_vol > 0
                                            const vol = isAsk ? row.ask_vol! : isBid ? row.bid_vol! : 0
                                            const maxVol = Math.max(...orderbookRows.map(r => Math.max(r.ask_vol || 0, r.bid_vol || 0)), 1)
                                            const pct = vol / maxVol
                                            return (
                                                <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 90px 1fr", alignItems: "center", height: 30, position: "relative" as const, borderBottom: row.highlight ? `1px solid ${ACCENT}` : `1px solid #1A1A1A` }}>
                                                    <div style={{ textAlign: "right" as const, paddingRight: 6 }}>
                                                        {isAsk && (
                                                            <div style={{ position: "relative" as const }}>
                                                                <div style={{ position: "absolute" as const, right: 0, top: -11, width: `${pct * 100}%`, height: 26, background: "rgba(49,130,246,0.15)", borderRadius: 3 }} />
                                                                <span style={{ color: DOWN, fontSize: 11, fontWeight: 600, position: "relative" as const }}>{vol.toLocaleString("ko-KR")}</span>
                                                            </div>
                                                        )}
                                                    </div>
                                                    <div style={{ textAlign: "center" as const, fontSize: 12, fontWeight: row.highlight ? 800 : 600, color: row.highlight ? ACCENT : isAsk ? DOWN : isBid ? UP : "#fff", cursor: "pointer" }}
                                                        onClick={() => { setOrderPrice(String(row.price)); setTab("trade") }}>
                                                        {isUS ? row.price.toLocaleString("en-US") : row.price.toLocaleString("ko-KR")}
                                                    </div>
                                                    <div style={{ textAlign: "left" as const, paddingLeft: 6 }}>
                                                        {isBid && (
                                                            <div style={{ position: "relative" as const }}>
                                                                <div style={{ position: "absolute" as const, left: 0, top: -11, width: `${pct * 100}%`, height: 26, background: "rgba(240,68,82,0.15)", borderRadius: 3 }} />
                                                                <span style={{ color: UP, fontSize: 11, fontWeight: 600, position: "relative" as const }}>{vol.toLocaleString("ko-KR")}</span>
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                            )
                                        })}
                                    </div>
                                )}

                                {/* 체결 내역 */}
                                <div style={{ color: ACCENT, fontSize: 11, fontWeight: 700, marginBottom: 10 }}>체결 내역</div>
                                {(() => {
                                    const trades = liveTrades.length > 0 ? liveTrades : syntheticTrades
                                    if (!trades || trades.length === 0) return <div style={{ color: MUTED, fontSize: 12 }}>체결 데이터 없음</div>
                                    return (
                                        <div style={{ background: CARD, borderRadius: 12, border: `1px solid ${BORDER}`, overflow: "hidden" }}>
                                            <div style={{ display: "grid", gridTemplateColumns: "52px 1fr 70px 60px", padding: "8px 12px", borderBottom: `1px solid ${BORDER}`, fontSize: 10, color: MUTED }}>
                                                <span>{liveTrades.length > 0 ? "시간" : "날짜"}</span>
                                                <span style={{ textAlign: "right" as const }}>체결가</span>
                                                <span style={{ textAlign: "right" as const }}>전일비</span>
                                                <span style={{ textAlign: "right" as const }}>수량</span>
                                            </div>
                                            <div style={{ maxHeight: 300, overflowY: "auto" as const }}>
                                                {trades.map((tr: any, i: number) => {
                                                    const sc = tr.side === "buy" ? UP : DOWN
                                                    return (
                                                        <div key={i} style={{ display: "grid", gridTemplateColumns: "52px 1fr 70px 60px", padding: "6px 12px", borderBottom: "1px solid #1A1A1A", fontSize: 11, alignItems: "center" }}>
                                                            <span style={{ color: MUTED, fontSize: 10 }}>{tr.time || ""}</span>
                                                            <span style={{ textAlign: "right" as const, color: sc, fontWeight: 700 }}>{isUS ? tr.price?.toLocaleString("en-US") : tr.price?.toLocaleString("ko-KR")}</span>
                                                            <span style={{ textAlign: "right" as const, color: sc, fontSize: 10 }}>{tr.change != null && tr.change !== 0 ? `${tr.change > 0 ? "+" : ""}${tr.change.toLocaleString("ko-KR")}` : "—"}</span>
                                                            <span style={{ textAlign: "right" as const, color: "#fff", fontWeight: 600 }}>{fmtVol(tr.volume || tr.qty || 0)}</span>
                                                        </div>
                                                    )
                                                })}
                                            </div>
                                        </div>
                                    )
                                })()}
                            </div>
                        )}

                        {/* ── 주문 탭 ── */}
                        {tab === "trade" && (
                            <div style={{ width: "100%", minWidth: 0 }}>
                                {/* 매수/매도 토글 */}
                                <div style={{ display: "flex", gap: 0, marginBottom: 16, borderRadius: 12, overflow: "hidden", border: `1px solid ${BORDER}` }}>
                                    <button type="button" onClick={() => { setOrderSide("buy"); setOrderResult(null) }}
                                        style={{ flex: 1, padding: "14px 0", border: "none", fontSize: 15, fontWeight: 800, cursor: "pointer", fontFamily: _font, background: orderSide === "buy" ? UP : "#1A1A1A", color: orderSide === "buy" ? "#fff" : MUTED }}>
                                        매수
                                    </button>
                                    <button type="button" onClick={() => { setOrderSide("sell"); setOrderResult(null) }}
                                        style={{ flex: 1, padding: "14px 0", border: "none", fontSize: 15, fontWeight: 800, cursor: "pointer", fontFamily: _font, background: orderSide === "sell" ? DOWN : "#1A1A1A", color: orderSide === "sell" ? "#fff" : MUTED }}>
                                        매도
                                    </button>
                                </div>

                                {/* 주문 유형 */}
                                <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
                                    <button type="button" onClick={() => setOrderType("01")}
                                        style={{ flex: 1, padding: "10px 0", borderRadius: 10, border: `1px solid ${orderType === "01" ? ACCENT : BORDER}`, background: orderType === "01" ? "rgba(181,255,25,0.12)" : "transparent", color: orderType === "01" ? ACCENT : MUTED, fontSize: 13, fontWeight: 700, cursor: "pointer", fontFamily: _font }}>
                                        시장가
                                    </button>
                                    <button type="button" onClick={() => setOrderType("00")}
                                        style={{ flex: 1, padding: "10px 0", borderRadius: 10, border: `1px solid ${orderType === "00" ? ACCENT : BORDER}`, background: orderType === "00" ? "rgba(181,255,25,0.12)" : "transparent", color: orderType === "00" ? ACCENT : MUTED, fontSize: 13, fontWeight: 700, cursor: "pointer", fontFamily: _font }}>
                                        지정가
                                    </button>
                                </div>

                                {/* 가격 (지정가) */}
                                {orderType === "00" && (
                                    <div style={{ marginBottom: 16 }}>
                                        <label style={{ color: MUTED, fontSize: 11, fontWeight: 600, marginBottom: 6, display: "block" }}>가격</label>
                                        <input type="number" value={orderPrice} onChange={e => setOrderPrice(e.target.value)} placeholder={String(currentPrice || "")}
                                            style={{ ...fieldStyle, width: "100%" }} />
                                    </div>
                                )}

                                {/* 수량 */}
                                <div style={{ marginBottom: 16 }}>
                                    <label style={{ color: MUTED, fontSize: 11, fontWeight: 600, marginBottom: 6, display: "block" }}>수량</label>
                                    <input type="number" value={orderQty} onChange={e => setOrderQty(e.target.value)} placeholder="0"
                                        style={{ ...fieldStyle, width: "100%" }} />
                                    <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                                        {[1, 5, 10, 50].map(n => (
                                            <button key={n} type="button" onClick={() => setOrderQty(String(n))}
                                                style={{ flex: 1, padding: "6px 0", borderRadius: 6, border: `1px solid ${BORDER}`, background: "#1A1A1A", color: "#fff", fontSize: 11, fontWeight: 600, cursor: "pointer", fontFamily: _font }}>
                                                {n}
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                {/* 예상 금액 */}
                                {(() => {
                                    const q = parseInt(orderQty, 10) || 0
                                    const p = orderType === "01" ? currentPrice : (parseInt(orderPrice, 10) || currentPrice)
                                    const total = q * p
                                    if (q <= 0) return null
                                    return (
                                        <div style={{ background: "#0A0A0A", borderRadius: 12, padding: "12px 14px", border: `1px solid ${BORDER}`, marginBottom: 16 }}>
                                            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                                                <span style={{ color: MUTED, fontSize: 11 }}>예상 주문금액</span>
                                                <span style={{ color: "#fff", fontSize: 14, fontWeight: 800 }}>{isUS ? fmtUSD(total) : fmtKRW(total)}</span>
                                            </div>
                                            <div style={{ color: MUTED, fontSize: 10 }}>
                                                {orderType === "01" ? "시장가" : "지정가"} · {q}주 × {isUS ? fmtUSD(p) : fmtKRW(p)}
                                            </div>
                                        </div>
                                    )
                                })()}

                                {/* 주문 결과 메시지 */}
                                {orderResult && (
                                    <div style={{
                                        padding: "12px 14px", borderRadius: 12, marginBottom: 16,
                                        background: orderResult.success ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)",
                                        border: `1px solid ${orderResult.success ? "rgba(34,197,94,0.5)" : "rgba(239,68,68,0.5)"}`,
                                        color: orderResult.success ? "#22C55E" : "#EF4444",
                                        fontSize: 13, fontWeight: 700,
                                    }}>
                                        {orderResult.success ? "✓ " : "✗ "}{orderResult.message}
                                    </div>
                                )}

                                {/* 확인 모달 */}
                                {showConfirm && (
                                    <div style={{ position: "fixed" as const, inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 9999 }}>
                                        <div style={{ background: "#111", borderRadius: 20, padding: 24, maxWidth: 360, width: "90%", border: `1px solid ${BORDER}` }}>
                                            <div style={{ color: "#fff", fontSize: 18, fontWeight: 800, marginBottom: 16 }}>주문 확인</div>
                                            <div style={{ color: MUTED, fontSize: 13, lineHeight: 1.6, marginBottom: 20 }}>
                                                <span style={{ color: orderSide === "buy" ? UP : DOWN, fontWeight: 800 }}>{orderSide === "buy" ? "매수" : "매도"}</span>
                                                {" "}{selectedStock.name} ({selectedStock.ticker})<br />
                                                수량: <span style={{ color: "#fff", fontWeight: 700 }}>{orderQty}주</span><br />
                                                {orderType === "00" ? `가격: ${isUS ? fmtUSD(Number(orderPrice)) : fmtKRW(Number(orderPrice))} (지정가)` : "시장가 주문"}<br />
                                                <span style={{ color: "#F59E0B", fontSize: 11, fontWeight: 700, marginTop: 8, display: "block" }}>
                                                    실전 계좌에서 실제 주문이 체결됩니다.
                                                </span>
                                            </div>
                                            <div style={{ display: "flex", gap: 10 }}>
                                                <button type="button" onClick={() => setShowConfirm(false)}
                                                    style={{ flex: 1, padding: "14px 0", borderRadius: 12, border: `1px solid ${BORDER}`, background: "transparent", color: MUTED, fontSize: 14, fontWeight: 700, cursor: "pointer", fontFamily: _font }}>
                                                    취소
                                                </button>
                                                <button type="button" onClick={submitOrder} disabled={orderSubmitting}
                                                    style={{ flex: 1, padding: "14px 0", borderRadius: 12, border: "none", background: orderSide === "buy" ? UP : DOWN, color: "#fff", fontSize: 14, fontWeight: 800, cursor: orderSubmitting ? "wait" : "pointer", fontFamily: _font, opacity: orderSubmitting ? 0.6 : 1 }}>
                                                    {orderSubmitting ? "처리중..." : "주문 실행"}
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {/* 주문 버튼 */}
                                <button type="button"
                                    onClick={() => {
                                        const q = parseInt(orderQty, 10) || 0
                                        if (q <= 0) { setOrderResult({ success: false, message: "수량을 입력하세요" }); return }
                                        if (orderType === "00" && !(parseInt(orderPrice, 10) > 0)) { setOrderResult({ success: false, message: "가격을 입력하세요" }); return }
                                        setShowConfirm(true)
                                    }}
                                    style={{
                                        width: "100%", padding: "16px 0", borderRadius: 14, border: "none",
                                        background: orderSide === "buy" ? UP : DOWN,
                                        color: "#fff", fontSize: 17, fontWeight: 800, cursor: "pointer", fontFamily: _font,
                                    }}>
                                    {orderSide === "buy" ? "매수" : "매도"} 주문
                                </button>
                            </div>
                        )}
                    </div>

                    {/* ── 하단 빠른 매수/매도 바 ── */}
                    {tab !== "trade" && (
                        <div style={{ display: "flex", gap: 0, flexShrink: 0 }}>
                            <button type="button" onClick={() => { setOrderSide("buy"); setTab("trade") }}
                                style={{ flex: 1, padding: "16px 20px", color: "#fff", border: "none", fontSize: "clamp(14px, 3.5vw, 17px)", fontWeight: 800, cursor: "pointer", fontFamily: _font, borderRadius: 0, background: UP }}>
                                매수
                            </button>
                            <button type="button" onClick={() => { setOrderSide("sell"); setTab("trade") }}
                                style={{ flex: 1, padding: "16px 20px", color: "#fff", border: "none", fontSize: "clamp(14px, 3.5vw, 17px)", fontWeight: 800, cursor: "pointer", fontFamily: _font, borderRadius: 0, background: DOWN }}>
                                매도
                            </button>
                        </div>
                    )}
                </>
            )}
        </div>
    )
}

export default function StockDetailPanel(props: Props) {
    return <PanelErrorBoundary><StockDetailPanelInner {...props} /></PanelErrorBoundary>
}

// ── Framer 기본값 & 프로퍼티 컨트롤 ──

StockDetailPanel.defaultProps = {
    apiBase: DEFAULT_API,
    portfolioUrl: DEFAULT_PORTFOLIO,
    realtimeServerUrl: DEFAULT_RELAY,
    market: "kr",
}

addPropertyControls(StockDetailPanel, {
    apiBase: {
        type: ControlType.String,
        title: "API Base URL",
        defaultValue: DEFAULT_API,
        description: "Vercel API 서버 (검색/주문)",
    },
    portfolioUrl: {
        type: ControlType.String,
        title: "portfolio.json URL",
        defaultValue: DEFAULT_PORTFOLIO,
    },
    realtimeServerUrl: {
        type: ControlType.String,
        title: "실시간 서버 URL",
        defaultValue: DEFAULT_RELAY,
        description: "Railway SSE 중계 서버",
    },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["국장 (KR)", "미장 (US)"],
        defaultValue: "kr",
    },
})

// ── 스타일 ──

const wrapStyle: CSSProperties = {
    width: "100%",
    height: "100%",
    minHeight: 240,
    alignSelf: "stretch",
    background: BG,
    borderRadius: 20,
    border: `1px solid ${BORDER}`,
    overflow: "hidden",
    fontFamily: _font,
    boxSizing: "border-box",
    display: "flex",
    flexDirection: "column",
}

const searchBarStyle: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "10px 16px",
    background: "#0A0A0A",
    borderBottom: `1px solid ${BORDER}`,
    flexShrink: 0,
}

const searchInputStyle: CSSProperties = {
    flex: 1,
    background: "transparent",
    border: "none",
    outline: "none",
    color: "#fff",
    fontSize: 14,
    fontFamily: _font,
    fontWeight: 600,
}

const suggestionsStyle: CSSProperties = {
    background: "#111",
    borderBottom: `1px solid ${BORDER}`,
    maxHeight: 280,
    overflowY: "auto",
    flexShrink: 0,
}

const suggestionItemStyle: CSSProperties = {
    display: "flex",
    alignItems: "center",
    padding: "10px 16px",
    cursor: "pointer",
    gap: 4,
}

const headerStyle: CSSProperties = {
    padding: "clamp(12px, 3vw, 18px)",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 12,
    borderBottom: `1px solid ${BORDER}`,
    flexShrink: 0,
}

const tabRowStyle: CSSProperties = {
    display: "flex",
    gap: 4,
    padding: "0 8px",
    borderBottom: `1px solid ${BORDER}`,
    overflowX: "auto",
    width: "100%",
    flexShrink: 0,
}

const tabBtnStyle: CSSProperties = {
    flex: 1,
    minWidth: 0,
    padding: "12px 8px",
    background: "none",
    border: "none",
    cursor: "pointer",
    fontSize: "clamp(11px, 2.6vw, 14px)",
    fontWeight: 700,
    fontFamily: _font,
    whiteSpace: "nowrap",
}

const bodyStyle: CSSProperties = {
    padding: "clamp(12px, 3vw, 18px)",
    flex: 1,
    minHeight: 0,
    overflowY: "auto",
    overflowX: "hidden",
    display: "flex",
    flexDirection: "column",
}

const fieldStyle: CSSProperties = {
    padding: "12px 14px",
    borderRadius: 12,
    border: `1px solid ${BORDER}`,
    background: "#0A0A0A",
    color: "#fff",
    fontSize: 16,
    fontWeight: 700,
    fontFamily: _font,
    outline: "none",
    boxSizing: "border-box",
}
