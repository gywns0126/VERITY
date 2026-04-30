import { useState, useEffect, useRef, useCallback } from "react"
import { addPropertyControls, ControlType } from "framer"

/* ── fetchPortfolioJson (Framer 단일 파일 제약으로 인라인) ── */
function bustPortfolioUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

const PORTFOLIO_FETCH_TIMEOUT_MS = 15_000

function _withTimeout<T>(p: Promise<T>, ms: number, ac: AbortController): Promise<T> {
    const timer = setTimeout(() => ac.abort(), ms)
    return p.finally(() => clearTimeout(timer))
}

function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    const ac = new AbortController()
    if (signal) {
        if (signal.aborted) ac.abort()
        else signal.addEventListener("abort", () => ac.abort(), { once: true })
    }
    return _withTimeout(
        fetch(bustPortfolioUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal: ac.signal })
            .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
            .then((t) => JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null"))),
        PORTFOLIO_FETCH_TIMEOUT_MS,
        ac,
    )
}

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆ (Neo Dark Terminal — _shared-patterns.ts 마스터)
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    strongBuy: "#22C55E", buy: "#B5FF19", watch: "#FFD600", caution: "#F59E0B", avoid: "#EF4444",
    up: "#F04452", down: "#3182F6",
    info: "#5BA9FF", success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const G = {
    accent: "0 0 8px rgba(181,255,25,0.35)",
    accentSoft: "0 0 4px rgba(181,255,25,0.20)",
    accentStrong: "0 0 12px rgba(181,255,25,0.50)",
    danger: "0 0 6px rgba(239,68,68,0.30)",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_tight: 1.3, lh_normal: 1.5, lh_loose: 1.7,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease", slow: "240ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/* ── Crypto 모드 ── */
interface CoinData {
    id: string
    symbol: string
    name: string
    price: number
    change24h: number
}

/** 업비트 KRW 마켓 — 공개 GET /v1/ticker, 인증 불필요 · CORS 허용 */
const COINS = [
    { id: "bitcoin", market: "KRW-BTC", symbol: "BTC", name: "비트코인", role: "시장 대장주" },
    { id: "ethereum", market: "KRW-ETH", symbol: "ETH", name: "이더리움", role: "생태계 기준" },
    { id: "solana", market: "KRW-SOL", symbol: "SOL", name: "솔라나", role: "기술적 흐름" },
    { id: "ripple", market: "KRW-XRP", symbol: "XRP", name: "리플", role: "제도권 뉴스" },
    { id: "dogecoin", market: "KRW-DOGE", symbol: "DOGE", name: "도지코인", role: "탐욕 지수" },
] as const

interface UpbitTickerRow {
    market: string
    trade_price: number
    signed_change_rate: number
}

const UPBIT_TICKER_URL = `https://api.upbit.com/v1/ticker?markets=${COINS.map((c) => c.market).join(",")}`

/* ── SmartMoney 모드 ── */
interface FlowItem {
    name: string
    ticker: string
    signal: string
    score: number
    type: "foreign" | "institution" | "both"
}

/* ── 공통 Props ── */
interface Props {
    mode: "crypto" | "smartmoney"
    speed: number
    refreshInterval: number
    dataUrl: string
}

/* ── 공통 스크롤 훅 ── */
function useScrollingOffset(
    hasItems: boolean,
    speed: number,
    contentRef: React.RefObject<HTMLDivElement | null>,
    paused: boolean,
) {
    const [offset, setOffset] = useState(0)

    useEffect(() => {
        if (!hasItems || paused) return
        const interval = setInterval(() => {
            setOffset((prev) => {
                const contentWidth = contentRef.current?.scrollWidth || 1000
                const next = prev - 1
                if (Math.abs(next) > contentWidth / 2) return 0
                return next
            })
        }, 40 / (speed || 1))
        return () => clearInterval(interval)
    }, [hasItems, speed, contentRef, paused])

    return offset
}

/* ── 포맷 유틸 (업비트 KRW) ── */
const formatKrw = (price: number): string => {
    if (!Number.isFinite(price)) return "—"
    const opts: Intl.NumberFormatOptions =
        price >= 1000
            ? { maximumFractionDigits: 0 }
            : { maximumFractionDigits: 6, minimumFractionDigits: 0 }
    return `₩${price.toLocaleString("ko-KR", opts)}`
}

const formatChange = (change: number): string => {
    const sign = change >= 0 ? "+" : ""
    return `${sign}${change.toFixed(2)}%`
}

/* ── 메인 컴포넌트 ── */
export default function ScrollingTicker(props: Props) {
    const { mode, speed, refreshInterval, dataUrl } = props
    const containerRef = useRef<HTMLDivElement>(null)
    const contentRef = useRef<HTMLDivElement>(null)

    const [coins, setCoins] = useState<CoinData[]>([])
    const [flowItems, setFlowItems] = useState<FlowItem[]>([])
    const [error, setError] = useState(false)
    const [lastUpdated, setLastUpdated] = useState("")
    const [scrollPaused, setScrollPaused] = useState(false)

    const hasItems = mode === "crypto" ? coins.length > 0 : flowItems.length > 0
    const offset = useScrollingOffset(hasItems, speed, contentRef, scrollPaused)
    const scrollHoverProps = {
        onMouseEnter: () => setScrollPaused(true),
        onMouseLeave: () => setScrollPaused(false),
    } as const

    /* ── Crypto fetch (업비트 공개 API) ── */
    const fetchCrypto = useCallback(() => {
        fetch(UPBIT_TICKER_URL)
            .then((r) => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`)
                return r.json()
            })
            .then((data: unknown) => {
                if (!Array.isArray(data)) throw new Error("invalid payload")
                const byMarket = new Map(
                    (data as UpbitTickerRow[]).map((row) => [row.market, row]),
                )
                const results: CoinData[] = COINS.map((c) => {
                    const row = byMarket.get(c.market)
                    const rate = row?.signed_change_rate
                    return {
                        id: c.id,
                        symbol: c.symbol,
                        name: c.name,
                        price: row?.trade_price ?? 0,
                        change24h: typeof rate === "number" ? rate * 100 : 0,
                    }
                })
                if (results.every((x) => x.price === 0)) throw new Error("empty tickers")
                setCoins(results)
                setError(false)
                const now = new Date()
                setLastUpdated(
                    `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`,
                )
            })
            .catch(() => setError(true))
    }, [])

    /* ── SmartMoney fetch ── */
    const fetchSmartMoney = useCallback(() => {
        if (!dataUrl) return
        fetchPortfolioJson(dataUrl)
            .then((data) => {
                const recs: any[] = data?.recommendations || []
                const items: FlowItem[] = []

                for (const stock of recs) {
                    const flow = stock.flow || {}
                    const timing = stock.timing || {}
                    const pred = stock.prediction || {}
                    const fs = flow.flow_score || 50
                    const signals: string[] = flow.flow_signals || []
                    const ts = timing.timing_score || 50
                    const up = pred.up_probability || 50

                    const isForeign = signals.some((s: string) =>
                        s.includes("외국인"),
                    )
                    const isInst = signals.some((s: string) =>
                        s.includes("기관"),
                    )
                    const type =
                        isForeign && isInst
                            ? "both"
                            : isForeign
                              ? "foreign"
                              : isInst
                                ? "institution"
                                : "both"

                    let mainSignal = ""
                    if (signals.length > 0) {
                        mainSignal = signals[0]
                    } else if (timing.label && timing.label !== "관망") {
                        mainSignal = `${timing.label} ${ts}점`
                    } else if (up > 55) {
                        mainSignal = `AI↑${up}%`
                    } else {
                        mainSignal = `종합 ${stock.multi_factor?.multi_score || fs}점`
                    }

                    const compositeScore = fs * 0.3 + ts * 0.4 + up * 0.3

                    items.push({
                        name: stock.name,
                        ticker: stock.ticker,
                        signal: mainSignal,
                        score: Math.round(compositeScore),
                        type,
                    })
                }

                items.sort((a, b) => b.score - a.score)
                setFlowItems(items.slice(0, 15))
            })
            .catch(() => {})
    }, [dataUrl])

    useEffect(() => {
        if (mode === "crypto") {
            fetchCrypto()
            const iv = setInterval(fetchCrypto, (refreshInterval || 60) * 1000)
            return () => clearInterval(iv)
        }
        fetchSmartMoney()
        const iv = setInterval(fetchSmartMoney, 15 * 60 * 1000)
        return () => clearInterval(iv)
    }, [mode, fetchCrypto, fetchSmartMoney, refreshInterval])

    /* ── 로딩 / 에러 ── */
    if (!hasItems) {
        const isCrypto = mode === "crypto"
        return (
            <div style={styles.container}>
                <div style={styles.labelWrap}>
                    <span style={styles.labelIcon}>
                        {isCrypto ? "₿" : "⚡"}
                    </span>
                    <span style={styles.label}>
                        {isCrypto ? "업비트" : "SMART MONEY"}
                    </span>
                </div>
                <span
                    style={{ color: C.textTertiary, fontSize: 12, fontFamily: FONT }}
                >
                    {isCrypto
                        ? error
                            ? "API 연결 실패 — 재시도 중..."
                            : "시세 로딩 중..."
                        : "수급 데이터 대기 중..."}
                </span>
                {isCrypto && <span style={styles.blinkDot} />}
            </div>
        )
    }

    /* ── Crypto 렌더 ── */
    if (mode === "crypto") {
        const doubled = [...coins, ...coins]
        const avgChange =
            coins.reduce((s, c) => s + c.change24h, 0) / coins.length
        const marketMood =
            avgChange >= 3
                ? "EXTREME GREED"
                : avgChange >= 1
                  ? "GREED"
                  : avgChange >= -1
                    ? "NEUTRAL"
                    : avgChange >= -3
                      ? "FEAR"
                      : "EXTREME FEAR"
        const moodColor =
            avgChange >= 1 ? "#B5FF19" : avgChange >= -1 ? "#888" : "#FF4D4D"

        return (
            <div
                style={styles.container}
                ref={containerRef}
                {...scrollHoverProps}
            >
                <div style={styles.labelWrap}>
                    <span style={styles.labelIcon}>₿</span>
                    <span style={styles.label}>업비트 BIG5</span>
                </div>

                <div style={styles.moodBadge}>
                    <span
                        style={{ ...styles.moodDot, background: moodColor }}
                    />
                    <span
                        style={{ ...styles.moodText, color: moodColor }}
                    >
                        {marketMood}
                    </span>
                </div>

                <div style={styles.separator} />

                <div style={styles.trackWrap}>
                    <div
                        ref={contentRef}
                        style={{
                            ...styles.track,
                            transform: `translateX(${offset}px)`,
                        }}
                    >
                        {doubled.map((coin, i) => {
                            const isUp = coin.change24h >= 0
                            const changeColor = isUp ? "#B5FF19" : "#FF4D4D"
                            const bgGlow = isUp
                                ? "rgba(181,255,25,0.04)"
                                : "rgba(255,77,77,0.04)"
                            const meta = COINS.find((c) => c.id === coin.id)

                            return (
                                <div
                                    key={`${coin.id}-${i}`}
                                    style={{
                                        ...styles.coinItem,
                                        background: bgGlow,
                                    }}
                                >
                                    <span style={styles.coinSymbol}>
                                        {coin.symbol}
                                    </span>
                                    <span style={styles.coinPrice}>
                                        {formatKrw(coin.price)}
                                    </span>
                                    <span
                                        style={{
                                            ...styles.coinChange,
                                            color: changeColor,
                                            background: isUp
                                                ? "rgba(181,255,25,0.1)"
                                                : "rgba(255,77,77,0.1)",
                                            border: `1px solid ${isUp ? "rgba(181,255,25,0.2)" : "rgba(255,77,77,0.2)"}`,
                                        }}
                                    >
                                        {isUp ? "▲" : "▼"}{" "}
                                        {formatChange(coin.change24h)}
                                    </span>
                                    <span style={styles.coinRole}>
                                        {meta?.role}
                                    </span>
                                    <span style={styles.divider}>│</span>
                                </div>
                            )
                        })}
                    </div>
                </div>

                <div style={styles.timeWrap}>
                    <span style={styles.timeText}>{lastUpdated}</span>
                </div>

                <style>{`@keyframes cryptoBlink { 0%,100%{opacity:1} 50%{opacity:.3} }`}</style>
            </div>
        )
    }

    /* ── SmartMoney 렌더 ── */
    const doubled = [...flowItems, ...flowItems]

    return (
        <div
            style={styles.container}
            ref={containerRef}
            {...scrollHoverProps}
        >
            <span style={styles.label}>SMART MONEY</span>
            <div style={styles.trackWrap}>
                <div
                    ref={contentRef}
                    style={{
                        ...styles.track,
                        transform: `translateX(${offset}px)`,
                    }}
                >
                    {doubled.map((item, i) => {
                        const typeIcon =
                            item.type === "foreign"
                                ? "🏦"
                                : item.type === "institution"
                                  ? "🏢"
                                  : "⚡"
                        const scoreColor =
                            item.score >= 60
                                ? "#B5FF19"
                                : item.score >= 50
                                  ? "#22C55E"
                                  : "#888"

                        return (
                            <div
                                key={`${item.ticker}-${i}`}
                                style={styles.flowItem}
                            >
                                <span style={{ fontSize: 12 }}>
                                    {typeIcon}
                                </span>
                                <span style={styles.itemName}>
                                    {item.name}
                                </span>
                                <span
                                    style={{
                                        ...styles.itemSignal,
                                        color: scoreColor,
                                    }}
                                >
                                    {item.signal}
                                </span>
                                <span style={styles.flowDivider}>·</span>
                            </div>
                        )
                    })}
                </div>
            </div>
        </div>
    )
}

ScrollingTicker.defaultProps = {
    mode: "crypto",
    speed: 1,
    refreshInterval: 60,
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
}

addPropertyControls(ScrollingTicker, {
    mode: {
        type: ControlType.Enum,
        title: "모드",
        options: ["crypto", "smartmoney"],
        optionTitles: ["암호화폐", "스마트머니"],
        defaultValue: "crypto",
    },
    speed: {
        type: ControlType.Number,
        title: "스크롤 속도",
        defaultValue: 1,
        min: 0.5,
        max: 3,
        step: 0.5,
    },
    refreshInterval: {
        type: ControlType.Number,
        title: "갱신 주기(초)",
        defaultValue: 60,
        min: 30,
        max: 300,
        step: 10,
        hidden: (props: any) => props.mode !== "crypto",
    },
    dataUrl: {
        type: ControlType.String,
        title: "Data URL",
        defaultValue:
            "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
        hidden: (props: any) => props.mode !== "smartmoney",
    },
})

const styles: Record<string, React.CSSProperties> = {
    container: {
        width: "100%",
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "8px 16px",
        background: "#000",
        fontFamily: FONT_MONO,
        borderTop: "1px solid #111",
        borderBottom: "1px solid #111",
        overflow: "hidden",
        boxSizing: "border-box",
    },
    labelWrap: {
        display: "flex",
        alignItems: "center",
        gap: 6,
        flexShrink: 0,
    },
    labelIcon: {
        color: "#F7931A",
        fontSize: 14,
        fontWeight: 900,
    },
    label: {
        color: C.textDisabled,
        fontSize: 12,
        fontWeight: 800,
        letterSpacing: "0.12em",
        whiteSpace: "nowrap" as const,
        flexShrink: 0,
    },
    moodBadge: {
        display: "flex",
        alignItems: "center",
        gap: 4,
        flexShrink: 0,
        padding: "2px 8px",
        background: C.bgPage,
        border: `1px solid ${C.border}`,
        borderRadius: 6,
    },
    moodDot: {
        width: 6,
        height: 6,
        borderRadius: 3,
        animation: "cryptoBlink 2s ease-in-out infinite",
    },
    moodText: {
        fontSize: 8,
        fontWeight: 800,
        letterSpacing: "0.08em",
        whiteSpace: "nowrap" as const,
    },
    separator: {
        width: 1,
        height: 20,
        background: C.bgElevated,
        flexShrink: 0,
    },
    trackWrap: {
        flex: 1,
        overflow: "hidden",
        position: "relative" as const,
    },
    track: {
        display: "flex",
        alignItems: "center",
        gap: 0,
        whiteSpace: "nowrap" as const,
        transition: "none",
    },
    coinItem: {
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        padding: "3px 10px",
        borderRadius: 6,
        flexShrink: 0,
        marginRight: 2,
    },
    coinSymbol: {
        color: C.textPrimary,
        fontSize: 12,
        fontWeight: 800,
        letterSpacing: "0.04em",
    },
    coinPrice: { color: C.textPrimary, fontSize: 12, fontWeight: 600 },
    coinChange: {
        fontSize: 12,
        fontWeight: 700,
        padding: "1px 6px",
        borderRadius: 3,
        whiteSpace: "nowrap" as const,
    },
    coinRole: {
        color: C.textDisabled,
        fontSize: 12,
        fontWeight: 500,
        whiteSpace: "nowrap" as const,
    },
    divider: { color: "#1A1A1A", fontSize: 12, padding: "0 4px" },
    timeWrap: {
        flexShrink: 0,
        display: "flex",
        alignItems: "center",
        gap: 4,
    },
    timeText: {
        color: C.textDisabled,
        fontSize: 12,
        fontWeight: 600,
        fontVariantNumeric: "tabular-nums",
        whiteSpace: "nowrap" as const,
    },
    blinkDot: {
        width: 6,
        height: 6,
        borderRadius: 3,
        background: "#B5FF19",
        animation: "cryptoBlink 1.5s ease-in-out infinite",
        flexShrink: 0,
    },
    flowItem: {
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "0 6px",
        flexShrink: 0,
    },
    itemName: { color: C.textSecondary, fontSize: 12, fontWeight: 600 },
    itemSignal: { fontSize: 12, fontWeight: 500 },
    flowDivider: { color: "#222", fontSize: 12, padding: "0 4px" },
}
