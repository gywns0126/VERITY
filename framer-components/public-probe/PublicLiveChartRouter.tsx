import { addPropertyControls, ControlType, RenderTarget } from "framer"
import {
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react"
const DEFAULT_DATA_BASE =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"
const WORLD_BANK_URL =
    "https://www.worldbank.org/en/research/commodity-markets"
const FONT =
    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

interface Props {
    ticker?: string
    previewTicker?: string
    chartBase?: string
    height?: number
    usChartHeight?: number
    showVolume?: boolean
    dark?: boolean
    [key: string]: any
}

type Commodity = {
    name: string
    symbol: string
    exchange: string
    macroKey: string
    unit: string
}

type ChartPoint = {
    label: string
    value: number
}

type RangeKey = "1M" | "3M" | "6M" | "1Y"

const COMMODITIES: Record<string, Commodity> = {
    CMD_GOLD: {
        name: "금",
        symbol: "GC=F",
        exchange: "COMEX",
        macroKey: "gold",
        unit: "USD/트로이온스",
    },
    CMD_SILVER: {
        name: "은",
        symbol: "SI=F",
        exchange: "COMEX",
        macroKey: "silver",
        unit: "USD/트로이온스",
    },
    CMD_COPPER: {
        name: "구리",
        symbol: "HG=F",
        exchange: "COMEX",
        macroKey: "copper",
        unit: "USD/파운드",
    },
    CMD_WTI: {
        name: "WTI 원유",
        symbol: "CL=F",
        exchange: "NYMEX",
        macroKey: "wti_oil",
        unit: "USD/배럴",
    },
    CMD_BRENT: {
        name: "브렌트유",
        symbol: "BZ=F",
        exchange: "ICE",
        macroKey: "brent",
        unit: "USD/배럴",
    },
    CMD_NATGAS: {
        name: "천연가스",
        symbol: "NG=F",
        exchange: "NYMEX",
        macroKey: "natural_gas",
        unit: "USD/MMBtu",
    },
    CMD_CORN: {
        name: "옥수수",
        symbol: "ZC=F",
        exchange: "CBOT",
        macroKey: "corn",
        unit: "USD/부셸",
    },
    CMD_WHEAT: {
        name: "밀",
        symbol: "ZW=F",
        exchange: "CBOT",
        macroKey: "wheat",
        unit: "USD/부셸",
    },
    CMD_SOYBEAN: {
        name: "대두",
        symbol: "ZS=F",
        exchange: "CBOT",
        macroKey: "soybean",
        unit: "USD/부셸",
    },
    CMD_COFFEE: {
        name: "커피",
        symbol: "KC=F",
        exchange: "ICE US",
        macroKey: "coffee",
        unit: "USD/파운드",
    },
    CMD_SUGAR: {
        name: "설탕",
        symbol: "SB=F",
        exchange: "ICE US",
        macroKey: "sugar",
        unit: "USD/파운드",
    },
    CMD_COTTON: {
        name: "면화",
        symbol: "CT=F",
        exchange: "ICE US",
        macroKey: "cotton",
        unit: "USD/파운드",
    },
}

function readTicker(fallback = ""): string {
    if (typeof window === "undefined") return fallback.trim().toUpperCase()
    const query = (
        new URLSearchParams(window.location.search).get("q") || ""
    )
        .trim()
        .toUpperCase()
    if (query) return query
    try {
        return (
            window.localStorage.getItem("verity_last_ticker") || fallback
        )
            .trim()
            .toUpperCase()
    } catch {
        return fallback.trim().toUpperCase()
    }
}

function dataUrl(value?: string): string {
    const base = String(value || DEFAULT_DATA_BASE).replace(/\/+$/, "")
    return base.endsWith(".json") ? base : base + "/macro_snapshot.json"
}

function numeric(value: unknown): number | null {
    if (value === null || value === undefined || value === "") return null
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
}

function formatValue(value: number): string {
    return value.toLocaleString("ko-KR", {
        maximumFractionDigits: value >= 100 ? 1 : value >= 10 ? 2 : 3,
    })
}

function formatAsOf(value: unknown): string {
    if (!value) return "기준시각 확인 중"
    const date = new Date(String(value))
    if (Number.isNaN(date.getTime())) return String(value)
    return (
        date.toLocaleString("ko-KR", {
            timeZone: "Asia/Seoul",
            month: "numeric",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        }) + " KST"
    )
}

function buildDailyPoints(values: unknown[]): ChartPoint[] {
    return values
        .map(numeric)
        .filter((value): value is number => value !== null)
        .map((value, index, rows) => ({
            value,
            label:
                index === 0
                    ? "1개월 전"
                    : index === rows.length - 1
                      ? "최근"
                      : "",
        }))
}

function buildHistoryPoints(history: unknown[]): ChartPoint[] {
    return history
        .map((row: any) => ({
            label: String(row?.date || ""),
            value: numeric(row?.close),
        }))
        .filter(
            (row): row is ChartPoint =>
                Boolean(row.label) && row.value !== null
        )
}

function shortDate(value: string, fallback: string): string {
    const matched = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/)
    return matched ? matched[2] + "." + matched[3] : fallback
}

function buildMonthlyPoints(history: unknown[]): ChartPoint[] {
    return history
        .map((row: any) => ({
            label: String(row?.period || ""),
            value: numeric(row?.value),
        }))
        .filter(
            (row): row is ChartPoint =>
                Boolean(row.label) && row.value !== null
        )
}

function OwnChart({
    points,
    color,
    dark,
    gradientId,
    width,
    height,
}: {
    points: ChartPoint[]
    color: string
    dark: boolean
    gradientId: string
    width: number
    height: number
}) {
    const wrapRef = useRef<HTMLDivElement | null>(null)
    const [hoverIndex, setHoverIndex] = useState<number | null>(null)
    const left = 0
    const right = width
    const top = 10
    const bottom = height - 4
    const values = points.map((point) => point.value)
    const rawMin = Math.min(...values)
    const rawMax = Math.max(...values)
    const span = Math.max(rawMax - rawMin, Math.abs(rawMax) * 0.02, 1)
    const min = rawMin - span * 0.08
    const max = rawMax + span * 0.08
    const coordinates = points.map((point, index) => {
        const x =
            left +
            (index / Math.max(points.length - 1, 1)) * (right - left)
        const y = bottom - ((point.value - min) / (max - min)) * (bottom - top)
        return { ...point, x, y }
    })
    const line = coordinates
        .map(
            (point, index) =>
                (index === 0 ? "M " : "L ") +
                point.x.toFixed(2) +
                " " +
                point.y.toFixed(2)
        )
        .join(" ")
    const area =
        line +
        " L " +
        right +
        " " +
        bottom +
        " L " +
        left +
        " " +
        bottom +
        " Z"
    const latest = coordinates[coordinates.length - 1]
    const highest = coordinates.reduce((best, point) =>
        point.value > best.value ? point : best
    )
    const lowest = coordinates.reduce((best, point) =>
        point.value < best.value ? point : best
    )
    const grid = dark ? "#2b323c" : "#eef1f4"
    const label = dark ? "#828d9b" : "#8b95a1"
    const hovered = hoverIndex === null ? null : coordinates[hoverIndex]
    const hoveredPrior =
        hoverIndex !== null && hoverIndex > 0
            ? coordinates[hoverIndex - 1].value
            : null
    const hoveredChange =
        hovered && hoveredPrior !== null && hoveredPrior !== 0
            ? ((hovered.value - hoveredPrior) / Math.abs(hoveredPrior)) * 100
            : null
    const setHoverFromX = (clientX: number) => {
        const rect = wrapRef.current?.getBoundingClientRect()
        if (!rect || rect.width <= 0) return
        const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
        setHoverIndex(Math.round(ratio * Math.max(points.length - 1, 0)))
    }

    return (
        <div
            ref={wrapRef}
            style={{ position: "relative", width: "100%", touchAction: "pan-y" }}
            onMouseMove={(event) => setHoverFromX(event.clientX)}
            onMouseLeave={() => setHoverIndex(null)}
            onTouchStart={(event) => {
                if (event.touches[0]) setHoverFromX(event.touches[0].clientX)
            }}
            onTouchMove={(event) => {
                if (event.touches[0]) setHoverFromX(event.touches[0].clientX)
            }}
        >
            <svg
                viewBox={"0 0 " + width + " " + height}
                width="100%"
                height={height}
                role="img"
                aria-label="원자재 가격 추세"
                preserveAspectRatio="none"
                style={{ display: "block" }}
            >
                <defs>
                    <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
                        <stop offset="0%" stopColor={color} stopOpacity="0.2" />
                        <stop offset="100%" stopColor={color} stopOpacity="0.02" />
                    </linearGradient>
                </defs>
                {[0, 0.5, 1].map((ratio) => {
                    const y = top + (bottom - top) * ratio
                    return <line key={ratio} x1={left} x2={right} y1={y} y2={y} stroke={grid} strokeWidth="1" vectorEffect="non-scaling-stroke" />
                })}
                <path d={area} fill={"url(#" + gradientId + ")"} />
                <path d={line} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
                {[
                    { name: "최고", point: highest },
                    { name: "최저", point: lowest },
                ].map(({ name, point }) => (
                    <circle
                        key={name}
                        cx={point.x}
                        cy={point.y}
                        r="3.5"
                        fill={dark ? "#171c23" : "#ffffff"}
                        stroke={color}
                        strokeWidth="1.5"
                        vectorEffect="non-scaling-stroke"
                        aria-label={name + " " + formatValue(point.value)}
                    />
                ))}
                <circle cx={latest.x} cy={latest.y} r="4" fill={color} stroke={dark ? "#171c23" : "#ffffff"} strokeWidth="2" vectorEffect="non-scaling-stroke" />
                {hovered ? <>
                    <line x1={hovered.x} y1={0} x2={hovered.x} y2={height} stroke={label} strokeWidth="1" strokeOpacity="0.45" vectorEffect="non-scaling-stroke" />
                    <circle cx={hovered.x} cy={hovered.y} r="4" fill={color} stroke={dark ? "#171c23" : "#ffffff"} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
                </> : null}
            </svg>
            <span style={{ position: "absolute", top: 2, right: 4, fontSize: 10, fontWeight: 600, color: label, background: dark ? "#171c23" : "#ffffff", padding: "0 3px", borderRadius: 4 }}>{formatValue(max)}</span>
            <span style={{ position: "absolute", top: Math.max(4, height - 18), right: 4, fontSize: 10, fontWeight: 600, color: label, background: dark ? "#171c23" : "#ffffff", padding: "0 3px", borderRadius: 4 }}>{formatValue(min)}</span>
            {hovered ? <div style={{ position: "absolute", top: 2, left: (hovered.x / width) * 100 + "%", transform: hovered.x > width * 0.5 ? "translateX(calc(-100% - 8px))" : "translateX(8px)", minWidth: 118, border: "1px solid " + grid, borderRadius: 10, background: dark ? "#1e242c" : "#ffffff", boxShadow: "0 8px 24px rgba(0,0,0,0.14)", padding: "7px 9px", pointerEvents: "none", zIndex: 30 }}>
                <div style={{ color: dark ? "#e3e7ec" : "#191f28", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>{hovered.label}</div>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 10, color: label, fontSize: 10.5 }}><span>종가</span><b style={{ color: dark ? "#e3e7ec" : "#191f28", fontSize: 11.5 }}>{formatValue(hovered.value)}</b></div>
                {hoveredChange !== null ? <div style={{ display: "flex", justifyContent: "space-between", gap: 10, color: label, fontSize: 10.5, marginTop: 3 }}><span>등락률</span><b style={{ color, fontSize: 11.5 }}>{(hoveredChange > 0 ? "+" : "") + hoveredChange.toFixed(2) + "%"}</b></div> : null}
            </div> : null}
        </div>
    )
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicLiveChartRouter(props: Props) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const fallback = String(
        props.ticker || (onCanvas ? props.previewTicker || "" : "")
    )
    const [ticker, setTicker] = useState(() => readTicker(fallback))
    const [dark, setDark] = useState(Boolean(props.dark))
    const [payload, setPayload] = useState<any>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState(false)
    const [range, setRange] = useState<RangeKey>("1M")
    const wrapRef = useRef<HTMLDivElement | null>(null)
    const [width, setWidth] = useState(0)

    useEffect(() => {
        if (onCanvas) return
        const sync = () => setTicker(readTicker(String(props.ticker || "")))
        sync()
        window.addEventListener("popstate", sync)
        window.addEventListener("verity-ticker-change", sync)
        return () => {
            window.removeEventListener("popstate", sync)
            window.removeEventListener("verity-ticker-change", sync)
        }
    }, [props.ticker, onCanvas])

    useEffect(() => {
        if (typeof document === "undefined") return
        const sync = () =>
            setDark(
                document.body.getAttribute("data-framer-theme") === "dark" ||
                    Boolean(props.dark)
            )
        sync()
        const observer = new MutationObserver(sync)
        observer.observe(document.body, {
            attributes: true,
            attributeFilter: ["data-framer-theme"],
        })
        return () => observer.disconnect()
    }, [props.dark])

    useEffect(() => {
        let alive = true
        setLoading(true)
        setError(false)
        fetch(dataUrl(props.chartBase))
            .then((response) => {
                if (!response.ok) throw new Error("macro snapshot unavailable")
                return response.json()
            })
            .then((data) => {
                if (!alive) return
                setPayload(data)
                setLoading(false)
            })
            .catch(() => {
                if (!alive) return
                setError(true)
                setLoading(false)
            })
        return () => {
            alive = false
        }
    }, [props.chartBase])

    useEffect(() => {
        const element = wrapRef.current
        if (!element || typeof ResizeObserver === "undefined") return
        const observer = new ResizeObserver((entries) => {
            for (const entry of entries) setWidth(entry.contentRect.width)
        })
        observer.observe(element)
        return () => observer.disconnect()
    }, [])

    const commodity = COMMODITIES[ticker]
    const data = useMemo(() => {
        if (!commodity || !payload) return null
        const quote = payload?.macro?.[commodity.macroKey] || null
        const benchmark =
            payload?.commodity_benchmarks?.items?.[ticker] || null
        const daily = buildDailyPoints(
            Array.isArray(quote?.sparkline) ? quote.sparkline : []
        )
        const historyDaily = buildHistoryPoints(
            Array.isArray(quote?.history_daily) ? quote.history_daily : []
        )
        const monthly = buildMonthlyPoints(
            Array.isArray(benchmark?.history) ? benchmark.history : []
        )
        return { quote, benchmark, daily, historyDaily, monthly }
    }, [commodity, payload, ticker])

    if (!commodity) return null

    const Hprop = Math.max(
        300,
        Number(props.height || props.usChartHeight || 480)
    )
    const ink = dark ? "#e3e7ec" : "#191f28"
    const sub = dark ? "#9aa4b1" : "#4e5968"
    const faint = dark ? "#828d9b" : "#8b95a1"
    const card = dark ? "#171c23" : "#ffffff"
    const field = dark ? "#222831" : "#f2f4f6"
    const hasHistory = Boolean(data && data.historyDaily.length >= 2)
    const hasDaily = Boolean(data && data.daily.length >= 2)
    const allPoints = hasHistory
        ? data?.historyDaily || []
        : hasDaily
          ? data?.daily || []
          : data?.monthly || []
    const rangeSize: Record<RangeKey, number> = {
        "1M": 22,
        "3M": 66,
        "6M": 132,
        "1Y": 260,
    }
    const rangeMinimum: Record<RangeKey, number> = {
        "1M": 2,
        "3M": 45,
        "6M": 90,
        "1Y": 180,
    }
    const rangeEnabled = (key: RangeKey) =>
        allPoints.length >= rangeMinimum[key]
    const nextUnavailableRange = (["3M", "6M", "1Y"] as RangeKey[]).find(
        (key) => !rangeEnabled(key)
    )
    const activeRange: RangeKey = rangeEnabled(range) ? range : "1M"
    const selectedPoints = allPoints.slice(-rangeSize[activeRange])
    const points = selectedPoints
    const sourceIsDaily = hasHistory || hasDaily
    const current =
        numeric(data?.quote?.value) ??
        points[points.length - 1]?.value ??
        numeric(data?.benchmark?.latest?.value) ??
        null
    const change =
        numeric(data?.quote?.change_pct) ??
        numeric(data?.benchmark?.change_pct)
    const color =
        change === null || change === 0
            ? dark
                ? "#9aa4b1"
                : "#6b7684"
            : change > 0
              ? dark
                  ? "#f05b67"
                  : "#f04452"
              : dark
                ? "#5b9bff"
                : "#3182f6"
    const seriesHigh = points.length
        ? Math.max(...points.map((point) => point.value))
        : null
    const seriesLow = points.length
        ? Math.min(...points.map((point) => point.value))
        : null
    const seriesStart = points[0]?.value ?? null
    const seriesAverage = points.length
        ? points.reduce((sum, point) => sum + point.value, 0) / points.length
        : null
    const periodChange =
        seriesStart !== null && current !== null && seriesStart !== 0
            ? ((current - seriesStart) / Math.abs(seriesStart)) * 100
            : null
    const dailyReturns = points.slice(1).map((point, index) => {
        const prior = points[index].value
        return prior === 0 ? 0 : point.value / prior - 1
    })
    let rollingPeak = points[0]?.value ?? null
    let maxDrawdown = 0
    points.forEach((point) => {
        rollingPeak =
            rollingPeak === null ? point.value : Math.max(rollingPeak, point.value)
        if (rollingPeak) {
            maxDrawdown = Math.min(
                maxDrawdown,
                ((point.value - rollingPeak) / rollingPeak) * 100
            )
        }
    })
    const positiveRatio = dailyReturns.length
        ? (dailyReturns.filter((value) => value > 0).length /
              dailyReturns.length) *
          100
        : null
    const averageReturn = dailyReturns.length
        ? dailyReturns.reduce((sum, value) => sum + value, 0) /
          dailyReturns.length
        : 0
    const annualizedVolatility = dailyReturns.length
        ? Math.sqrt(
              dailyReturns.reduce(
                  (sum, value) => sum + Math.pow(value - averageReturn, 2),
                  0
              ) / dailyReturns.length
          ) *
          Math.sqrt(252) *
          100
        : null
    const distanceFromHigh =
        seriesHigh !== null && current !== null && seriesHigh !== 0
            ? ((current - seriesHigh) / seriesHigh) * 100
            : null
    const source = sourceIsDaily
        ? String(data?.quote?.source || "단기 시세")
        : "World Bank Pink Sheet"
    const asOf = sourceIsDaily
        ? formatAsOf(data?.quote?.as_of || payload?.collected_at)
        : String(data?.benchmark?.latest?.period || "최신월 확인 중")
    const unit = sourceIsDaily
        ? commodity.unit
        : String(data?.benchmark?.unit || "USD 기준")
    const gradientId = "commodity-area-" + ticker.toLowerCase()
    const ready = points.length >= 2 && current !== null
    const chartWidth = Math.max(240, (width || 800) - 4)
    const proposedChartHeight = Math.min(
        Math.max(190, Math.round(chartWidth / 1.75)),
        Math.max(220, Hprop - 118)
    )
    const chartHeight = Number.isFinite(proposedChartHeight) ? proposedChartHeight : 320
    const tickIndexes = points.length
        ? [0, Math.round((points.length - 1) / 3), Math.round((2 * (points.length - 1)) / 3), points.length - 1]
        : []
    const high52 = numeric(data?.quote?.high_52w)
    const low52 = numeric(data?.quote?.low_52w)

    return (
        <div
            ref={wrapRef}
            style={{
                width: "100%",
                height: "100%",
                minHeight: Hprop,
                position: "relative",
                background: card,
                borderRadius: 16,
                boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
                overflow: "hidden",
                padding: "10px 4px 4px",
                boxSizing: "border-box",
                fontFamily: FONT,
                color: ink,
                display: "flex",
                flexDirection: "column",
            }}
        >
            <div
                style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "0 10px 6px",
                    flexWrap: "wrap",
                }}
            >
                {current !== null ? <>
                    <span style={{ fontSize: 17, fontWeight: 800, color: ink, letterSpacing: "-0.3px" }}>{formatValue(current)}</span>
                    {change !== null ? <span style={{ color, fontSize: 12.5, fontWeight: 700 }}>{(change > 0 ? "+" : "") + change.toFixed(2) + "%"}</span> : null}
                    <span style={{ color: faint, background: field, padding: "1px 6px", borderRadius: 5, fontSize: 10.5, fontWeight: 700 }}>선물 종가 · {asOf}</span>
                    {high52 !== null && low52 !== null ? <span style={{ color: faint, fontSize: 10.5, fontWeight: 600 }}>52주 <span style={{ color: dark ? "#ff6b76" : "#f04452" }}>{formatValue(high52)}</span> / <span style={{ color: dark ? "#5b9bff" : "#3182f6" }}>{formatValue(low52)}</span></span> : null}
                </> : <span style={{ color: faint, fontSize: 12, fontWeight: 700 }}>데이터 연결 중</span>}
                <span style={{ marginLeft: "auto", display: "inline-flex", gap: 2 }}>
                        {(
                            [
                                ["1M", "1M"],
                                ["3M", "3M"],
                                ["6M", "6M"],
                                ["1Y", "1Y"],
                            ] as const
                        ).map(([key, label]) => {
                            const enabled = rangeEnabled(key)
                            return (
                            <button
                                key={key}
                                type="button"
                                disabled={!enabled}
                                onClick={() => enabled && setRange(key)}
                                aria-pressed={activeRange === key}
                                style={{
                                    border: 0,
                                    borderRadius: 8,
                                    padding: "4px 10px",
                                    background:
                                        activeRange === key ? field : "transparent",
                                    color:
                                        activeRange === key
                                            ? ink
                                            : enabled
                                              ? faint
                                              : dark
                                                ? "#505a67"
                                                : "#b0b8c1",
                                    boxShadow: "none",
                                    fontFamily: FONT,
                                    fontSize: 11.5,
                                    fontWeight: 700,
                                    cursor: enabled ? "pointer" : "default",
                                }}
                            >
                                {label}
                            </button>
                            )
                        })}
                </span>
            </div>

            <div style={{ width: "100%", height: chartHeight }}>
                    {loading ? (
                        <div
                            style={{
                                height: "100%",
                                borderRadius: 12,
                                background: field,
                                display: "grid",
                                placeItems: "center",
                                color: faint,
                                fontSize: 12,
                                fontWeight: 700,
                            }}
                        >
                            가격 흐름을 불러오고 있어요
                        </div>
                    ) : error || !ready ? (
                        <div
                            style={{
                                height: "100%",
                                borderRadius: 12,
                                background: field,
                                display: "grid",
                                placeItems: "center",
                                color: sub,
                                fontSize: 12,
                                fontWeight: 700,
                                textAlign: "center",
                                lineHeight: 1.6,
                                padding: 20,
                                boxSizing: "border-box",
                            }}
                        >
                            원자재 기준선을 준비하고 있어요.
                            <br />
                            다음 수집 뒤 자동으로 표시됩니다.
                        </div>
                    ) : (
                        <OwnChart
                            points={points}
                            color={color}
                            dark={dark}
                            gradientId={gradientId}
                            width={chartWidth}
                            height={chartHeight}
                        />
                    )}
            </div>

            {ready ? <div style={{ position: "relative", height: 14, margin: "2px 2px 0" }}>
                {tickIndexes.map((index, tickIndex) => {
                    const left = points.length > 1 ? (index / (points.length - 1)) * 100 : 0
                    const transform = tickIndex === 0 ? "translateX(0)" : tickIndex === tickIndexes.length - 1 ? "translateX(-100%)" : "translateX(-50%)"
                    return <span key={tickIndex} style={{ position: "absolute", left: left + "%", transform, color: faint, fontSize: 10, fontWeight: 500, whiteSpace: "nowrap" }}>{shortDate(points[index]?.label || "", "")}</span>
                })}
            </div> : null}

                {nextUnavailableRange ? (
                    <div
                        style={{
                            margin: "5px 10px 0",
                            borderRadius: 10,
                            background: field,
                            padding: "8px 10px",
                            color: faint,
                            fontSize: 10.5,
                            lineHeight: 1.5,
                            fontWeight: 650,
                        }}
                    >
                        현재 {allPoints.length.toLocaleString("ko-KR")}개 관측 · {nextUnavailableRange} 버튼은 {rangeMinimum[nextUnavailableRange]}개부터 사용할 수 있어요.
                    </div>
                ) : null}

                {ready ? (
                    <div
                        style={{
                            display: "flex",
                            gap: 18,
                            marginTop: 4,
                            padding: "5px 10px 4px",
                            overflowX: "auto",
                            scrollbarWidth: "none",
                            flexShrink: 0,
                        }}
                    >
                        {[
                            ["기간 최고종가", seriesHigh],
                            ["기간 최저종가", seriesLow],
                            ["기간 수익률", periodChange],
                            ["고점 대비", distanceFromHigh],
                            ["최대 낙폭", maxDrawdown],
                            ["연환산 변동성", annualizedVolatility],
                            ["상승 관측 비중", positiveRatio],
                            ["평균 종가", seriesAverage],
                            ["관측 수", points.length],
                        ].map(([label, value]) => (
                            <div
                                key={String(label)}
                                style={{
                                    minWidth: 78,
                                    padding: "2px 0",
                                    flex: "0 0 auto",
                                }}
                            >
                                <div
                                    style={{
                                        color: faint,
                                        fontSize: 9.5,
                                        fontWeight: 600,
                                    }}
                                >
                                    {label}
                                </div>
                                <div
                                    style={{
                                        marginTop: 2,
                                        color: ink,
                                        fontSize: 11.5,
                                        fontWeight: 600,
                                    }}
                                >
                                    {typeof value === "number"
                                        ? label === "관측 수"
                                            ? value + "개"
                                            : [
                                                    "기간 수익률",
                                                    "고점 대비",
                                                    "최대 낙폭",
                                                    "연환산 변동성",
                                                    "상승 관측 비중",
                                                ].includes(String(label))
                                              ? (value > 0 ? "+" : "") +
                                                value.toFixed(2) +
                                                "%"
                                              : formatValue(value)
                                        : "—"}
                                </div>
                            </div>
                        ))}
                    </div>
                ) : null}

                <div
                    style={{
                        marginTop: "auto",
                        padding: "5px 10px 4px",
                        color: faint,
                        fontSize: 10,
                        lineHeight: 1.55,
                        fontWeight: 500,
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        flexWrap: "wrap",
                    }}
                >
                    <span>{commodity.name} · {commodity.symbol} · {commodity.exchange}</span>
                    <span>{sourceIsDaily ? "선물 연속물" : "세계은행 월평균"} · {unit}</span>
                    <span>{source} · {asOf} · {points.length}개 관측</span>
                    {!sourceIsDaily ? (
                            <a
                                href={WORLD_BANK_URL}
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{
                                    color: dark ? "#8eb8ff" : "#3182f6",
                                    textDecoration: "none",
                                    fontWeight: 700,
                                }}
                            >
                                원문
                            </a>
                    ) : null}
                </div>
        </div>
    )
}

addPropertyControls(PublicLiveChartRouter, {
    ticker: { type: ControlType.String, title: "Ticker", defaultValue: "" },
    previewTicker: {
        type: ControlType.String,
        title: "Preview",
        defaultValue: "CMD_GOLD",
    },
    chartBase: {
        type: ControlType.String,
        title: "Data Base",
        defaultValue: DEFAULT_DATA_BASE,
    },
    height: {
        type: ControlType.Number,
        title: "Height",
        defaultValue: 480,
        min: 220,
        max: 900,
        step: 10,
    },
    usChartHeight: {
        type: ControlType.Number,
        title: "Commodity",
        defaultValue: 400,
        min: 260,
        max: 900,
        step: 10,
    },
    showVolume: {
        type: ControlType.Boolean,
        title: "Volume",
        defaultValue: true,
    },
    dark: {
        type: ControlType.Boolean,
        title: "Dark",
        defaultValue: false,
    },
})
