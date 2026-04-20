import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState, type CSSProperties } from "react"

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


const CITIES = [
    { key: "seoul", label: "서울", tz: "Asia/Seoul" },
    { key: "ny", label: "뉴욕", tz: "America/New_York" },
    { key: "london", label: "런던", tz: "Europe/London" },
    { key: "hk", label: "홍콩", tz: "Asia/Hong_Kong" },
] as const

interface Props {
    showSeconds: boolean
    fontSizeTime: number
    fontSizeDate: number
    fontSizeCity: number
    cityContentGap: number
    timeDateGap: number
    layout: "row" | "stack"
    viewportFixed: boolean
    fixedZIndex: number
    fixedTop: number
    fixedRight: number
    fixedBottom: number
    fixedLeft: number
    paddingTop: number
    paddingRight: number
    paddingBottom: number
    paddingLeft: number
}

function formatTimeAndDate(now: Date, tz: string, showSeconds: boolean): { time: string; date: string } {
    const dateOpts: Intl.DateTimeFormatOptions = {
        timeZone: tz,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        weekday: "short",
    }
    const timeOpts: Intl.DateTimeFormatOptions = {
        timeZone: tz,
        hour: "2-digit",
        minute: "2-digit",
        ...(showSeconds ? { second: "2-digit" } : {}),
        hour12: false,
    }
    const dParts = new Intl.DateTimeFormat("ko-KR", dateOpts).formatToParts(now)
    const tParts = new Intl.DateTimeFormat("ko-KR", timeOpts).formatToParts(now)
    const pick = (parts: Intl.DateTimeFormatPart[], type: string) =>
        parts.find((p) => p.type === type)?.value ?? ""
    const y = pick(dParts, "year")
    const m = pick(dParts, "month")
    const day = pick(dParts, "day")
    const wd = pick(dParts, "weekday")
    const h = pick(tParts, "hour")
    const min = pick(tParts, "minute")
    const sec = showSeconds ? pick(tParts, "second") : ""
    const time = showSeconds ? `${h}:${min}:${sec}` : `${h}:${min}`
    const date = `${y}.${m}.${day} ${wd}`
    return { time, date }
}

function insetStyle(top: number, right: number, bottom: number, left: number): CSSProperties {
    const s: CSSProperties = {}
    if (top >= 0) s.top = top
    if (right >= 0) s.right = right
    if (bottom >= 0) s.bottom = bottom
    if (left >= 0) s.left = left
    return s
}

function CityBlock(props: {
    label: string
    tz: string
    now: Date
    showSeconds: boolean
    fontSizeTime: number
    fontSizeDate: number
    fontSizeCity: number
    cityContentGap: number
    timeDateGap: number
    layout: "row" | "stack"
    isFirst: boolean
}) {
    const {
        label,
        tz,
        now,
        showSeconds,
        fontSizeTime,
        fontSizeDate,
        fontSizeCity,
        cityContentGap,
        timeDateGap,
        layout,
        isFirst,
    } = props
    const { time, date } = formatTimeAndDate(now, tz, showSeconds)

    const cityStyle: CSSProperties = {
        fontSize: Math.max(8, fontSizeCity),
        fontWeight: 700,
        color: "#B5FF19",
        flexShrink: 0,
        letterSpacing: "-0.02em",
        lineHeight: 1.2,
    }
    const timeStyle: CSSProperties = {
        fontSize: Math.max(8, fontSizeTime),
        fontWeight: 600,
        color: C.textPrimary,
        fontVariantNumeric: "tabular-nums",
        letterSpacing: "-0.03em",
        lineHeight: 1.2,
    }
    const dateStyle: CSSProperties = {
        fontSize: Math.max(8, fontSizeDate),
        fontWeight: 500,
        color: C.textSecondary,
        fontVariantNumeric: "tabular-nums",
        letterSpacing: "-0.03em",
        lineHeight: 1.2,
        overflow: "hidden",
        textOverflow: "ellipsis",
        minWidth: 0,
    }

    if (layout === "stack") {
        return (
            <div
                style={{
                    flex: "1 1 0",
                    minWidth: 0,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "flex-start",
                    paddingLeft: isFirst ? 0 : 10,
                    borderLeft: isFirst ? "none" : "1px solid #222",
                    overflow: "hidden",
                }}
            >
                <span style={{ ...cityStyle, marginBottom: cityContentGap }}>{label}</span>
                <span style={{ ...timeStyle, marginBottom: timeDateGap }}>{time}</span>
                <span style={dateStyle}>{date}</span>
            </div>
        )
    }

    return (
        <div
            style={{
                flex: "1 1 0",
                minWidth: 0,
                display: "flex",
                flexDirection: "row",
                alignItems: "baseline",
                gap: cityContentGap,
                paddingLeft: isFirst ? 0 : 10,
                borderLeft: isFirst ? "none" : "1px solid #222",
                overflow: "hidden",
            }}
        >
            <span style={cityStyle}>{label}</span>
            <div
                style={{
                    display: "flex",
                    flexDirection: "row",
                    alignItems: "baseline",
                    gap: timeDateGap,
                    minWidth: 0,
                    flex: 1,
                    overflow: "hidden",
                }}
            >
                <span style={{ ...timeStyle, flexShrink: 0 }}>{time}</span>
                <span style={dateStyle}>{date}</span>
            </div>
        </div>
    )
}

export default function WorldClockRow(props: Props) {
    const {
        showSeconds,
        fontSizeTime,
        fontSizeDate,
        fontSizeCity,
        cityContentGap,
        timeDateGap,
        layout,
        viewportFixed,
        fixedZIndex,
        fixedTop,
        fixedRight,
        fixedBottom,
        fixedLeft,
        paddingTop,
        paddingRight,
        paddingBottom,
        paddingLeft,
    } = props
    const [tick, setTick] = useState(0)

    useEffect(() => {
        const id = setInterval(() => setTick((n) => n + 1), 1000)
        return () => clearInterval(id)
    }, [])

    const now = new Date()
    void tick

    const pad = `${paddingTop}px ${paddingRight}px ${paddingBottom}px ${paddingLeft}px`

    const cardStyle: CSSProperties = {
        display: "flex",
        flexDirection: "row",
        alignItems: layout === "stack" ? "flex-start" : "center",
        justifyContent: "space-between",
        gap: 8,
        width: "100%",
        boxSizing: "border-box",
        padding: pad,
        borderRadius: 12,
        background: C.bgElevated,
        border: `1px solid ${C.border}`,
        fontFamily: FONT,
        overflow: "hidden",
    }

    const inner = (
        <div style={cardStyle}>
            {CITIES.map((c, i) => (
                <CityBlock
                    key={c.key}
                    label={c.label}
                    tz={c.tz}
                    now={now}
                    showSeconds={showSeconds}
                    fontSizeTime={fontSizeTime}
                    fontSizeDate={fontSizeDate}
                    fontSizeCity={fontSizeCity}
                    cityContentGap={cityContentGap}
                    timeDateGap={timeDateGap}
                    layout={layout}
                    isFirst={i === 0}
                />
            ))}
        </div>
    )

    if (!viewportFixed) return inner

    const fixedShell: CSSProperties = {
        position: "fixed",
        zIndex: fixedZIndex,
        boxSizing: "border-box",
        ...insetStyle(fixedTop, fixedRight, fixedBottom, fixedLeft),
    }
    const hasL = fixedLeft >= 0
    const hasR = fixedRight >= 0
    if (hasL && hasR) {
        /* left+right 로 가로 폭 자동 */
    } else if (hasL && !hasR) {
        fixedShell.width = `calc(100vw - ${fixedLeft}px)`
    } else if (!hasL && hasR) {
        fixedShell.left = 0
    } else {
        fixedShell.left = 0
        fixedShell.right = 0
    }

    return <div style={fixedShell}>{inner}</div>
}

WorldClockRow.defaultProps = {
    showSeconds: true,
    fontSizeTime: 12,
    fontSizeDate: 10,
    fontSizeCity: 10,
    cityContentGap: 12,
    timeDateGap: 6,
    layout: "stack",
    viewportFixed: false,
    fixedZIndex: 1000,
    fixedTop: -1,
    fixedRight: -1,
    fixedBottom: -1,
    fixedLeft: -1,
    paddingTop: 8,
    paddingRight: 10,
    paddingBottom: 8,
    paddingLeft: 10,
}

addPropertyControls(WorldClockRow, {
    showSeconds: {
        type: ControlType.Boolean,
        title: "초 표시",
        defaultValue: true,
    },
    fontSizeTime: {
        type: ControlType.Number,
        title: "시간 글자 크기",
        defaultValue: 12,
        min: 8,
        max: 20,
        step: 1,
    },
    fontSizeDate: {
        type: ControlType.Number,
        title: "날짜 글자 크기",
        defaultValue: 10,
        min: 7,
        max: 18,
        step: 1,
    },
    fontSizeCity: {
        type: ControlType.Number,
        title: "도시 글자 크기",
        defaultValue: 10,
        min: 8,
        max: 18,
        step: 1,
    },
    cityContentGap: {
        type: ControlType.Number,
        title: "도시↔시간 갭(px)",
        defaultValue: 12,
        min: 0,
        max: 32,
        step: 1,
    },
    timeDateGap: {
        type: ControlType.Number,
        title: "시간↔날짜 갭(px)",
        defaultValue: 6,
        min: 0,
        max: 24,
        step: 1,
    },
    layout: {
        type: ControlType.Enum,
        title: "배치",
        options: ["row", "stack"],
        optionTitles: ["한 줄(도시·시간·날짜)", "수직(도시 위·시간·날짜)"],
        defaultValue: "stack",
    },
    viewportFixed: {
        type: ControlType.Boolean,
        title: "뷰포트 고정",
        defaultValue: false,
        description: "position:fixed",
    },
    fixedZIndex: {
        type: ControlType.Number,
        title: "고정 z-index",
        defaultValue: 1000,
        min: 0,
        max: 99999,
        step: 1,
        hidden: (p) => !p.viewportFixed,
    },
    fixedTop: {
        type: ControlType.Number,
        title: "고정 top(px, -1=미사용)",
        defaultValue: -1,
        min: -1,
        max: 400,
        step: 1,
        hidden: (p) => !p.viewportFixed,
    },
    fixedRight: {
        type: ControlType.Number,
        title: "고정 right(px, -1=미사용)",
        defaultValue: -1,
        min: -1,
        max: 400,
        step: 1,
        hidden: (p) => !p.viewportFixed,
    },
    fixedBottom: {
        type: ControlType.Number,
        title: "고정 bottom(px, -1=미사용)",
        defaultValue: -1,
        min: -1,
        max: 400,
        step: 1,
        hidden: (p) => !p.viewportFixed,
    },
    fixedLeft: {
        type: ControlType.Number,
        title: "고정 left(px, -1=미사용)",
        defaultValue: -1,
        min: -1,
        max: 400,
        step: 1,
        hidden: (p) => !p.viewportFixed,
    },
    paddingTop: {
        type: ControlType.Number,
        title: "패딩 상",
        defaultValue: 8,
        min: 0,
        max: 48,
        step: 1,
    },
    paddingRight: {
        type: ControlType.Number,
        title: "패딩 우",
        defaultValue: 10,
        min: 0,
        max: 48,
        step: 1,
    },
    paddingBottom: {
        type: ControlType.Number,
        title: "패딩 하",
        defaultValue: 8,
        min: 0,
        max: 48,
        step: 1,
    },
    paddingLeft: {
        type: ControlType.Number,
        title: "패딩 좌",
        defaultValue: 10,
        min: 0,
        max: 48,
        step: 1,
    },
})
