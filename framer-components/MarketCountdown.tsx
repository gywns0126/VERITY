/**
 * ⚠️ DEPRECATED (2026-05-05 Plan v0.1 §3 [Calendar] 폐기 결정)
 *
 * EventCalendar timeline + filter chip (countdown) 으로 흡수. (MarketStatus 는 별도 살림)
 *
 * Framer 페이지에서 인스턴스 제거. 추후 일괄 cleanup commit 시 git rm.
 *
 * ────────────────────────────────────────────────────────────
 */
import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState, useCallback } from "react"

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


const KR_HOLIDAYS_2026: { date: string; name: string }[] = [
    { date: "2026-01-01", name: "신정" },
    { date: "2026-01-16", name: "설날 연휴" },
    { date: "2026-01-17", name: "설날" },
    { date: "2026-01-18", name: "설날 연휴" },
    { date: "2026-01-19", name: "대체공휴일" },
    { date: "2026-03-01", name: "삼일절" },
    { date: "2026-03-02", name: "대체공휴일" },
    { date: "2026-05-05", name: "어린이날" },
    { date: "2026-05-24", name: "석가탄신일" },
    { date: "2026-05-25", name: "대체공휴일" },
    { date: "2026-06-06", name: "현충일" },
    { date: "2026-08-15", name: "광복절" },
    { date: "2026-09-24", name: "추석 연휴" },
    { date: "2026-09-25", name: "추석" },
    { date: "2026-09-26", name: "추석 연휴" },
    { date: "2026-10-03", name: "개천절" },
    { date: "2026-10-09", name: "한글날" },
    { date: "2026-12-25", name: "성탄절" },
]

const US_HOLIDAYS_2026: { date: string; name: string }[] = [
    { date: "2026-01-01", name: "New Year's Day" },
    { date: "2026-01-19", name: "MLK Day" },
    { date: "2026-02-16", name: "Presidents' Day" },
    { date: "2026-04-03", name: "Good Friday" },
    { date: "2026-05-25", name: "Memorial Day" },
    { date: "2026-06-19", name: "Juneteenth" },
    { date: "2026-07-03", name: "Independence Day (observed)" },
    { date: "2026-09-07", name: "Labor Day" },
    { date: "2026-11-26", name: "Thanksgiving" },
    { date: "2026-12-25", name: "Christmas" },
]

type MarketState = "pre" | "open" | "post"

interface MarketInfo {
    label: string
    state: MarketState
    stateLabel: string
    remaining: string
    nextOpen: string | null
    dDay: number | null
    nextHoliday: { name: string; date: string; dDay: number } | null
    color: string
}

function toDateStr(d: Date): string {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

function getTimeInZone(tz: string): Date {
    const s = new Date().toLocaleString("en-US", { timeZone: tz })
    return new Date(s)
}

function isWeekend(d: Date): boolean {
    return d.getDay() === 0 || d.getDay() === 6
}

function isHoliday(d: Date, holidays: { date: string }[]): boolean {
    const ds = toDateStr(d)
    return holidays.some((h) => h.date === ds)
}

function formatCountdown(ms: number): string {
    if (ms <= 0) return "00:00:00"
    const totalSec = Math.floor(ms / 1000)
    const h = Math.floor(totalSec / 3600)
    const m = Math.floor((totalSec % 3600) / 60)
    const s = totalSec % 60
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
}

function getNextTradingDay(d: Date, holidays: { date: string }[]): Date {
    const next = new Date(d)
    next.setDate(next.getDate() + 1)
    while (isWeekend(next) || isHoliday(next, holidays)) {
        next.setDate(next.getDate() + 1)
    }
    return next
}

function getNextHoliday(now: Date, holidays: { date: string; name: string }[]): { name: string; date: string; dDay: number } | null {
    const todayStr = toDateStr(now)
    for (const h of holidays) {
        if (h.date >= todayStr) {
            const hDate = new Date(h.date + "T00:00:00")
            const diff = Math.ceil((hDate.getTime() - new Date(todayStr + "T00:00:00").getTime()) / 86400000)
            return { name: h.name, date: h.date, dDay: diff }
        }
    }
    return null
}

function diffDays(from: Date, to: Date): number {
    const a = new Date(toDateStr(from) + "T00:00:00")
    const b = new Date(toDateStr(to) + "T00:00:00")
    return Math.ceil((b.getTime() - a.getTime()) / 86400000)
}

function computeMarket(
    label: string,
    tz: string,
    openH: number,
    openM: number,
    closeH: number,
    closeM: number,
    holidays: { date: string; name: string }[],
): MarketInfo {
    const now = getTimeInZone(tz)
    const h = now.getHours()
    const m = now.getMinutes()
    const s = now.getSeconds()
    const nowMs = (h * 3600 + m * 60 + s) * 1000
    const openMs = (openH * 3600 + openM * 60) * 1000
    const closeMs = (closeH * 3600 + closeM * 60) * 1000

    const isClosed = isWeekend(now) || isHoliday(now, holidays)
    const nextHoliday = getNextHoliday(now, holidays)

    if (isClosed) {
        const nextDay = getNextTradingDay(now, holidays)
        const dd = diffDays(now, nextDay)
        const dayLabel = nextDay.toLocaleDateString("ko-KR", { month: "long", day: "numeric", weekday: "short" })
        return {
            label,
            state: "post",
            stateLabel: "휴장",
            remaining: "—",
            nextOpen: dayLabel,
            dDay: dd,
            nextHoliday,
            color: C.textTertiary,
        }
    }

    if (nowMs < openMs) {
        const remaining = openMs - nowMs
        return {
            label,
            state: "pre",
            stateLabel: "장 전",
            remaining: formatCountdown(remaining),
            nextOpen: null,
            dDay: null,
            nextHoliday,
            color: "#EAB308",
        }
    }

    if (nowMs < closeMs) {
        const remaining = closeMs - nowMs
        return {
            label,
            state: "open",
            stateLabel: "거래 중",
            remaining: formatCountdown(remaining),
            nextOpen: null,
            dDay: null,
            nextHoliday,
            color: "#22C55E",
        }
    }

    const nextDay = getNextTradingDay(now, holidays)
    const dd = diffDays(now, nextDay)
    const dayLabel = nextDay.toLocaleDateString("ko-KR", { month: "long", day: "numeric", weekday: "short" })
    return {
        label,
        state: "post",
        stateLabel: "장 마감",
        remaining: "—",
        nextOpen: dayLabel,
        dDay: dd,
        nextHoliday,
        color: C.textTertiary,
    }
}

interface Props {
    showHoliday: boolean
}

export default function MarketCountdown(props: Props) {
    const { showHoliday } = props
    const [tick, setTick] = useState(0)

    useEffect(() => {
        const id = setInterval(() => setTick((t) => t + 1), 1000)
        return () => clearInterval(id)
    }, [])

    const kr = computeMarket("KRX 한국", "Asia/Seoul", 9, 0, 15, 30, KR_HOLIDAYS_2026)
    const us = computeMarket("NYSE 미국", "America/New_York", 9, 30, 16, 0, US_HOLIDAYS_2026)

    const stateIcon = (s: MarketState) => s === "open" ? "●" : s === "pre" ? "◐" : "○"

    return (
        <div style={container}>
            {[kr, us].map((mk) => (
                <div key={mk.label} style={marketCard}>
                    <div style={cardTop}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span style={{ ...dot, color: mk.color }}>{stateIcon(mk.state)}</span>
                            <span style={marketLabel}>{mk.label}</span>
                        </div>
                        <span style={{ ...stateBadge, background: mk.color + "18", color: mk.color, borderColor: mk.color + "40" }}>
                            {mk.stateLabel}
                        </span>
                    </div>

                    {mk.state === "open" && (
                        <div style={countdownRow}>
                            <span style={countdownLabel}>마감까지</span>
                            <span style={{ ...countdownValue, color: mk.color }}>{mk.remaining}</span>
                        </div>
                    )}

                    {mk.state === "pre" && (
                        <div style={countdownRow}>
                            <span style={countdownLabel}>개장까지</span>
                            <span style={{ ...countdownValue, color: mk.color }}>{mk.remaining}</span>
                        </div>
                    )}

                    {mk.state === "post" && mk.nextOpen && (
                        <div style={countdownRow}>
                            <span style={countdownLabel}>다음 개장</span>
                            <span style={nextOpenText}>{mk.nextOpen}</span>
                            {mk.dDay != null && (
                                <span style={dDayBadge}>D-{mk.dDay}</span>
                            )}
                        </div>
                    )}

                    {showHoliday && mk.nextHoliday && (
                        <div style={holidayRow}>
                            <span style={holidayText}>
                                다음 휴장: {mk.nextHoliday.name}
                            </span>
                            <span style={holidayDDay}>
                                D{mk.nextHoliday.dDay === 0 ? "-Day" : `-${mk.nextHoliday.dDay}`}
                            </span>
                        </div>
                    )}
                </div>
            ))}
        </div>
    )
}

MarketCountdown.defaultProps = {
    showHoliday: true,
}

addPropertyControls(MarketCountdown, {
    showHoliday: {
        type: ControlType.Boolean,
        title: "휴장일 표시",
        defaultValue: true,
    },
})

const font = FONT

const container: React.CSSProperties = {
    width: "100%",
    display: "flex",
    gap: 12,
    padding: "10px 16px",
    background: "#000",
    fontFamily: font,
}

const marketCard: React.CSSProperties = {
    flex: 1,
    background: C.bgElevated,
    borderRadius: 12,
    border: `1px solid ${C.border}`,
    padding: "12px 16px",
    display: "flex",
    flexDirection: "column",
    gap: 8,
}

const cardTop: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
}

const dot: React.CSSProperties = {
    fontSize: 12,
}

const marketLabel: React.CSSProperties = {
    color: C.textPrimary,
    fontSize: 13,
    fontWeight: 700,
    fontFamily: font,
}

const stateBadge: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 700,
    padding: "3px 8px",
    borderRadius: 6,
    border: "1px solid",
    fontFamily: font,
}

const countdownRow: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 8,
}

const countdownLabel: React.CSSProperties = {
    color: C.textTertiary,
    fontSize: 12,
    fontWeight: 500,
    fontFamily: font,
}

const countdownValue: React.CSSProperties = {
    fontSize: 20,
    fontWeight: 900,
    fontFamily: "'Inter', monospace",
    letterSpacing: "-0.02em",
}

const nextOpenText: React.CSSProperties = {
    color: C.textSecondary,
    fontSize: 13,
    fontWeight: 600,
    fontFamily: font,
}

const dDayBadge: React.CSSProperties = {
    color: "#EAB308",
    fontSize: 12,
    fontWeight: 800,
    background: "rgba(234,179,8,0.1)",
    padding: "2px 8px",
    borderRadius: 6,
    fontFamily: font,
}

const holidayRow: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    borderTop: `1px solid ${C.border}`,
    paddingTop: 6,
}

const holidayText: React.CSSProperties = {
    color: C.textTertiary,
    fontSize: 12,
    fontFamily: font,
}

const holidayDDay: React.CSSProperties = {
    color: "#F97316",
    fontSize: 12,
    fontWeight: 700,
    fontFamily: font,
}
