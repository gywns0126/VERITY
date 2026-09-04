import { addPropertyControls, ControlType, RenderTarget } from "framer"
import {
    useEffect,
    useMemo,
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

type RangeKey = "1W" | "1M"

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
}: {
    points: ChartPoint[]
    color: string
    dark: boolean
    gradientId: string
}) {
    const width = 800
    const height = 270
    const left = 18
    const right = 782
    const top = 22
    const bottom = 220
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
    const firstLabel = points[0]?.label || ""
    const lastLabel = points[points.length - 1]?.label || ""

    return (
        <svg
            viewBox={"0 0 " + width + " " + height}
            width="100%"
            height="100%"
            role="img"
            aria-label="원자재 가격 추세"
            preserveAspectRatio="none"
            style={{ display: "block", overflow: "visible" }}
        >
            <defs>
                <linearGradient
                    id={gradientId}
                    x1="0"
                    x2="0"
                    y1="0"
                    y2="1"
                >
                    <stop offset="0%" stopColor={color} stopOpacity="0.24" />
                    <stop offset="100%" stopColor={color} stopOpacity="0.02" />
                </linearGradient>
            </defs>
            {[0, 0.5, 1].map((ratio) => {
                const y = top + (bottom - top) * ratio
                return (
                    <line
                        key={ratio}
                        x1={left}
                        x2={right}
                        y1={y}
                        y2={y}
                        stroke={grid}
                        strokeWidth="1"
                        vectorEffect="non-scaling-stroke"
                    />
                )
            })}
            <path d={area} fill={"url(#" + gradientId + ")"} />
            <path
                d={line}
                fill="none"
                stroke={color}
                strokeWidth="3"
                strokeLinecap="round"
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
            />
            {[{ point: highest, name: "최고" }, { point: lowest, name: "최저" }].map(
                ({ point, name }) => (
                    <g key={name}>
                        <circle
                            cx={point.x}
                            cy={point.y}
                            r="4"
                            fill={dark ? "#171c23" : "#ffffff"}
                            stroke={color}
                            strokeWidth="2"
                            vectorEffect="non-scaling-stroke"
                        />
                        <text
                            x={point.x}
                            y={
                                name === "최고"
                                    ? Math.max(13, point.y - 10)
                                    : Math.min(bottom + 19, point.y + 18)
                            }
                            fill={label}
                            fontSize="11"
                            fontWeight="750"
                            fontFamily={FONT}
                            textAnchor={
                                point.x > width * 0.72
                                    ? "end"
                                    : point.x < width * 0.28
                                      ? "start"
                                      : "middle"
                            }
                        >
                            {name + " " + formatValue(point.value)}
                        </text>
                    </g>
                )
            )}
            <circle
                cx={latest.x}
                cy={latest.y}
                r="5"
                fill={color}
                stroke={dark ? "#171c23" : "#ffffff"}
                strokeWidth="3"
                vectorEffect="non-scaling-stroke"
            />
            <text
                x={left}
                y="252"
                fill={label}
                fontSize="13"
                fontWeight="700"
                fontFamily={FONT}
            >
                {firstLabel}
            </text>
            <text
                x={right}
                y="252"
                fill={label}
                fontSize="13"
                fontWeight="700"
                fontFamily={FONT}
                textAnchor="end"
            >
                {lastLabel}
            </text>
        </svg>
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

    const commodity = COMMODITIES[ticker]
    const data = useMemo(() => {
        if (!commodity || !payload) return null
        const quote = payload?.macro?.[commodity.macroKey] || null
        const benchmark =
            payload?.commodity_benchmarks?.items?.[ticker] || null
        const daily = buildDailyPoints(
            Array.isArray(quote?.sparkline) ? quote.sparkline : []
        )
        const monthly = buildMonthlyPoints(
            Array.isArray(benchmark?.history) ? benchmark.history : []
        )
        return { quote, benchmark, daily, monthly }
    }, [commodity, payload, ticker])

    if (!commodity) return null

    const height = Math.max(
        300,
        Number(props.usChartHeight || props.height || 480)
    )
    const ink = dark ? "#e3e7ec" : "#191f28"
    const sub = dark ? "#9aa4b1" : "#4e5968"
    const faint = dark ? "#828d9b" : "#8b95a1"
    const card = dark ? "#171c23" : "#ffffff"
    const field = dark ? "#222831" : "#f2f4f6"
    const shadow = dark
        ? "0 10px 34px rgba(0,0,0,.22)"
        : "0 10px 34px rgba(0,0,0,.055)"
    const hasDaily = Boolean(data && data.daily.length >= 2)
    const allPoints = hasDaily ? data?.daily || [] : data?.monthly || []
    const activeRange: RangeKey = range
    const points =
        activeRange === "1W" && allPoints.length > 5
            ? allPoints.slice(-5)
            : allPoints
    const sourceIsDaily = hasDaily
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

    return (
        <div
            style={{
                width: "100%",
                height: "100%",
                minHeight: 0,
                padding: "0 10px 4px",
                boxSizing: "border-box",
                fontFamily: FONT,
                color: ink,
            }}
        >
            <section
                style={{
                    width: "100%",
                    minHeight: height,
                    boxSizing: "border-box",
                    borderRadius: 20,
                    background: card,
                    boxShadow: shadow,
                    padding: "18px clamp(16px, 2.4vw, 24px) 14px",
                    display: "flex",
                    flexDirection: "column",
                }}
            >
                <div
                    style={{
                        display: "flex",
                        alignItems: "flex-start",
                        justifyContent: "space-between",
                        gap: 16,
                        flexWrap: "wrap",
                    }}
                >
                    <div>
                        <div
                            style={{
                                color: dark ? "#8eb8ff" : "#3182f6",
                                fontSize: 11.5,
                                fontWeight: 850,
                            }}
                        >
                            AlphaNest 원자재 차트
                        </div>
                        <div
                            style={{
                                marginTop: 5,
                                fontSize: 21,
                                fontWeight: 900,
                                letterSpacing: "-0.5px",
                            }}
                        >
                            {commodity.name}
                        </div>
                        <div
                            style={{
                                marginTop: 4,
                                color: faint,
                                fontSize: 11.5,
                                fontWeight: 700,
                            }}
                        >
                            {commodity.symbol} · {commodity.exchange}
                        </div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                        {current !== null ? (
                            <>
                                <div
                                    style={{
                                        fontSize: 24,
                                        fontWeight: 900,
                                        letterSpacing: "-0.4px",
                                    }}
                                >
                                    {formatValue(current)}
                                </div>
                                <div
                                    style={{
                                        marginTop: 3,
                                        color,
                                        fontSize: 12.5,
                                        fontWeight: 850,
                                    }}
                                >
                                    {change !== null
                                        ? (change > 0 ? "+" : "") +
                                          change.toFixed(2) +
                                          "%"
                                        : "변동률 확인 중"}
                                </div>
                            </>
                        ) : (
                            <div
                                style={{
                                    color: faint,
                                    fontSize: 12,
                                    fontWeight: 750,
                                }}
                            >
                                데이터 연결 중
                            </div>
                        )}
                    </div>
                </div>

                <div
                    style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: 12,
                        marginTop: 16,
                        flexWrap: "wrap",
                    }}
                >
                    <div
                        style={{
                            display: "flex",
                            gap: 4,
                            padding: 4,
                            borderRadius: 999,
                            background: field,
                        }}
                    >
                        {(
                            [
                                ["1W", "1주", allPoints.length >= 5],
                                ["1M", "1개월", allPoints.length >= 2],
                            ] as const
                        ).map(([key, label, enabled]) => (
                            <button
                                key={key}
                                type="button"
                                disabled={!enabled}
                                onClick={() => enabled && setRange(key)}
                                aria-pressed={activeRange === key}
                                style={{
                                    border: 0,
                                    borderRadius: 999,
                                    padding: "7px 12px",
                                    background:
                                        activeRange === key ? card : "transparent",
                                    color:
                                        activeRange === key
                                            ? ink
                                            : enabled
                                              ? faint
                                              : dark
                                                ? "#505a67"
                                                : "#b0b8c1",
                                    boxShadow:
                                        activeRange === key
                                            ? "0 2px 8px rgba(0,0,0,.07)"
                                            : "none",
                                    fontFamily: FONT,
                                    fontSize: 11.5,
                                    fontWeight: 800,
                                    cursor: enabled ? "pointer" : "default",
                                }}
                            >
                                {label}
                            </button>
                        ))}
                    </div>
                    <div
                        style={{
                            color: faint,
                            fontSize: 10.5,
                            fontWeight: 650,
                        }}
                    >
                        {sourceIsDaily ? "선물 연속물" : "세계은행 월평균"} ·{" "}
                        {unit}
                    </div>
                </div>

                <div
                    style={{
                        height: Math.max(210, height - 214),
                        minHeight: 210,
                        marginTop: 8,
                    }}
                >
                    {loading ? (
                        <div
                            style={{
                                height: "100%",
                                borderRadius: 16,
                                background: field,
                                display: "grid",
                                placeItems: "center",
                                color: faint,
                                fontSize: 12,
                                fontWeight: 750,
                            }}
                        >
                            가격 흐름을 불러오고 있어요
                        </div>
                    ) : error || !ready ? (
                        <div
                            style={{
                                height: "100%",
                                borderRadius: 16,
                                background: field,
                                display: "grid",
                                placeItems: "center",
                                color: sub,
                                fontSize: 12,
                                fontWeight: 750,
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
                        />
                    )}
                </div>

                {ready ? (
                    <div
                        style={{
                            display: "grid",
                            gridTemplateColumns:
                                "repeat(3, minmax(0, 1fr))",
                            gap: 8,
                            marginTop: 6,
                        }}
                    >
                        {[
                            ["기간 최고가", seriesHigh],
                            ["기간 최저가", seriesLow],
                            ["시작가", seriesStart],
                            ["현재가", current],
                            ["기간 변동률", periodChange],
                            ["평균가", seriesAverage],
                            ["관측 수", points.length],
                        ].map(([label, value]) => (
                            <div
                                key={String(label)}
                                style={{
                                    borderRadius: 14,
                                    background: field,
                                    padding: "10px 11px",
                                }}
                            >
                                <div
                                    style={{
                                        color: faint,
                                        fontSize: 9.5,
                                        fontWeight: 750,
                                    }}
                                >
                                    {label}
                                </div>
                                <div
                                    style={{
                                        marginTop: 3,
                                        color: sub,
                                        fontSize: 11.5,
                                        fontWeight: 850,
                                    }}
                                >
                                    {typeof value === "number"
                                        ? label === "관측 수"
                                            ? value + "개"
                                            : label === "기간 변동률"
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
                        marginTop: 12,
                        color: faint,
                        fontSize: 10.5,
                        lineHeight: 1.55,
                        fontWeight: 600,
                    }}
                >
                    {sourceIsDaily
                        ? "1주·1개월 흐름은 선물 연속물 기준이며 거래소·서비스별로 지연될 수 있어요."
                        : "가용한 월평균 기준선으로 표시하며 선물 현재가와 같은 값이 아니에요."}
                    <span> · {source} · {asOf}</span>
                    {!sourceIsDaily ? (
                        <>
                            {" · "}
                            <a
                                href={WORLD_BANK_URL}
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{
                                    color: dark ? "#8eb8ff" : "#3182f6",
                                    textDecoration: "none",
                                    fontWeight: 750,
                                }}
                            >
                                원문
                            </a>
                        </>
                    ) : null}
                </div>
            </section>
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
