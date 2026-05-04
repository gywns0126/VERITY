import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState, type CSSProperties } from "react"

/**
 * MarketStatus — VERITY 시장 상태 (혁명 디자인 v1)
 *
 * 출처: MarketCountdown.tsx (404줄) modernize + 책임 명확화.
 *
 * 정보 영역:
 *   - 시장 상태 (거래 중 / 장 전 / 장 마감 / 휴장)
 *   - 카운트다운 (마감까지 / 개장까지) — 거래일
 *   - D-day (다음 개장 / 휴장 시) — 비거래일
 *   - 세션 진행 progress bar (거래 중일 때) — 초보 직관 신호
 *   - 다음 휴장 D-N
 *
 * 분리 이유 (SiteHeader 와 별도):
 *   SiteHeader = 시장 가격·상태 *지금*
 *   MarketStatus = 시간 흐름·휴장 *예측*
 *
 * 모던 심플 6원칙:
 *   1. No card-in-card — 외곽 1개 + 좌우 split + 중앙 divider
 *   2. Flat hierarchy — cap 라벨 + hero 카운트다운 + sub
 *   3. Mono numerics — 카운트다운 / D-day / progress %
 *   4. Hero countdown — 28pt mono (Bloomberg 단말기 정밀감)
 *   5. Color discipline — 토큰만 (success/warn/danger/textTertiary)
 *   6. Emoji 0 / 자체 색 0
 *
 * feedback_no_hardcode_position 적용:
 *   - position:fixed / 위치 px / zIndex 미사용
 *   - inline 렌더링, 위치는 Framer 에서 직접 배치
 */

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    success: "#22C55E", warn: "#F59E0B", danger: "#EF4444", info: "#5BA9FF",
}
const G = {
    success: "0 0 6px rgba(34,197,94,0.35)",
    warn: "0 0 6px rgba(245,158,11,0.35)",
    accent: "0 0 8px rgba(181,255,25,0.35)",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_normal: 1.5,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/* ─────────── Holidays (2026 — 2027 추가 별도 작업) ─────────── */
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
    { date: "2026-07-03", name: "Independence Day (obs)" },
    { date: "2026-09-07", name: "Labor Day" },
    { date: "2026-11-26", name: "Thanksgiving" },
    { date: "2026-12-25", name: "Christmas" },
]


/* ─────────── Time helpers ─────────── */
type MarketState = "pre" | "open" | "post" | "closed"

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
    return holidays.some((h) => h.date === toDateStr(d))
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
            const today = new Date(todayStr + "T00:00:00")
            const diff = Math.ceil((hDate.getTime() - today.getTime()) / 86400000)
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

function formatCountdown(ms: number): string {
    if (ms <= 0) return "00:00:00"
    const totalSec = Math.floor(ms / 1000)
    const h = Math.floor(totalSec / 3600)
    const m = Math.floor((totalSec % 3600) / 60)
    const s = totalSec % 60
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
}

function formatNextOpen(d: Date): string {
    return d.toLocaleDateString("ko-KR", { month: "numeric", day: "numeric", weekday: "short" })
}


/* ─────────── Market info compute ─────────── */
interface MarketInfo {
    region: string
    state: MarketState
    stateLabel: string
    /** 거래 중: "마감까지" / 장 전: "개장까지" / 그 외: null */
    countdownLabel: string | null
    /** HH:MM:SS 형식, 비거래일은 null */
    countdownText: string | null
    /** 세션 진행 % (거래 중일 때만 0~100) */
    sessionProgress: number | null
    /** 비거래일: 다음 개장 일자 + D-N */
    nextOpenLabel: string | null
    nextOpenDDay: number | null
    /** 다음 휴장 (항상 표시) */
    nextHoliday: { name: string; date: string; dDay: number } | null
    /** 점등 색 */
    statusColor: string
    statusGlow: string
}

function computeMarket(
    region: string,
    tz: string,
    openH: number, openM: number,
    closeH: number, closeM: number,
    holidays: { date: string; name: string }[],
): MarketInfo {
    const now = getTimeInZone(tz)
    const h = now.getHours()
    const m = now.getMinutes()
    const s = now.getSeconds()
    const nowMs = (h * 3600 + m * 60 + s) * 1000
    const openMs = (openH * 3600 + openM * 60) * 1000
    const closeMs = (closeH * 3600 + closeM * 60) * 1000
    const sessionMs = closeMs - openMs

    const closed = isWeekend(now) || isHoliday(now, holidays)
    const nextHoliday = getNextHoliday(now, holidays)

    /* 휴장 (주말/공휴일) */
    if (closed) {
        const nextDay = getNextTradingDay(now, holidays)
        const dd = diffDays(now, nextDay)
        return {
            region,
            state: "closed",
            stateLabel: "휴장",
            countdownLabel: null,
            countdownText: null,
            sessionProgress: null,
            nextOpenLabel: formatNextOpen(nextDay),
            nextOpenDDay: dd,
            nextHoliday,
            statusColor: C.textTertiary,
            statusGlow: "none",
        }
    }

    /* 장 전 (pre-market) */
    if (nowMs < openMs) {
        return {
            region,
            state: "pre",
            stateLabel: "장 전",
            countdownLabel: "개장까지",
            countdownText: formatCountdown(openMs - nowMs),
            sessionProgress: null,
            nextOpenLabel: null,
            nextOpenDDay: null,
            nextHoliday,
            statusColor: C.warn,
            statusGlow: G.warn,
        }
    }

    /* 거래 중 */
    if (nowMs < closeMs) {
        const elapsed = nowMs - openMs
        const progressPct = Math.max(0, Math.min(100, (elapsed / sessionMs) * 100))
        return {
            region,
            state: "open",
            stateLabel: "거래 중",
            countdownLabel: "마감까지",
            countdownText: formatCountdown(closeMs - nowMs),
            sessionProgress: progressPct,
            nextOpenLabel: null,
            nextOpenDDay: null,
            nextHoliday,
            statusColor: C.success,
            statusGlow: G.success,
        }
    }

    /* 장 마감 (post-market, 평일) */
    const nextDay = getNextTradingDay(now, holidays)
    const dd = diffDays(now, nextDay)
    return {
        region,
        state: "post",
        stateLabel: "장 마감",
        countdownLabel: null,
        countdownText: null,
        sessionProgress: null,
        nextOpenLabel: formatNextOpen(nextDay),
        nextOpenDDay: dd,
        nextHoliday,
        statusColor: C.textTertiary,
        statusGlow: "none",
    }
}


/* ═══════════════════════════ 메인 ═══════════════════════════ */

interface Props {
    showHoliday: boolean
}

export default function MarketStatus(props: Props) {
    const { showHoliday } = props
    const [, setTick] = useState(0)

    /* 1초 tick (거래 중일 때 카운트다운 + progress 갱신) */
    useEffect(() => {
        const id = setInterval(() => setTick((n) => n + 1), 1000)
        return () => clearInterval(id)
    }, [])

    const kr = computeMarket("KOREA", "Asia/Seoul", 9, 0, 15, 30, KR_HOLIDAYS_2026)
    const us = computeMarket("USA", "America/New_York", 9, 30, 16, 0, US_HOLIDAYS_2026)

    return (
        <div style={shell}>
            <div style={grid}>
                <MarketColumn info={kr} />
                <div style={vDivider} />
                <MarketColumn info={us} />
            </div>

            {showHoliday && (kr.nextHoliday || us.nextHoliday) && (
                <>
                    <div style={hDivider} />
                    <div style={holidayRow}>
                        <HolidayBlock region="KOREA" holiday={kr.nextHoliday} />
                        <HolidayBlock region="USA" holiday={us.nextHoliday} />
                    </div>
                </>
            )}
        </div>
    )
}


/* ─────────── 시장 컬럼 ─────────── */
function MarketColumn({ info }: { info: MarketInfo }) {
    return (
        <div style={column}>
            {/* Region cap label */}
            <span style={regionLabel}>{info.region}</span>

            {/* Status row */}
            <div style={statusRow}>
                <span
                    style={{
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        background: info.statusColor,
                        boxShadow: info.statusGlow,
                    }}
                />
                <span style={{ ...stateText, color: info.statusColor }}>{info.stateLabel}</span>
            </div>

            {/* Hero — countdown 또는 D-day */}
            {info.countdownText && (
                <div style={heroBlock}>
                    <span style={{ ...heroValue, ...MONO, color: info.statusColor }}>
                        {info.countdownText}
                    </span>
                    {info.countdownLabel && (
                        <span style={heroLabel}>{info.countdownLabel}</span>
                    )}
                </div>
            )}

            {info.nextOpenLabel && info.nextOpenDDay != null && (
                <div style={heroBlock}>
                    <span style={{ ...heroValue, ...MONO, color: C.textPrimary }}>
                        D-{info.nextOpenDDay}
                    </span>
                    <span style={heroLabel}>다음 개장 {info.nextOpenLabel}</span>
                </div>
            )}

            {/* Session progress bar (거래 중일 때만) */}
            {info.sessionProgress != null && (
                <div style={progressWrap}>
                    <div style={progressTrack}>
                        <div
                            style={{
                                ...progressFill,
                                width: `${info.sessionProgress}%`,
                                background: C.success,
                                boxShadow: `0 0 4px ${C.success}80`,
                            }}
                        />
                    </div>
                    <span style={{ ...progressText, ...MONO }}>
                        {info.sessionProgress.toFixed(0)}% 진행
                    </span>
                </div>
            )}
        </div>
    )
}


/* ─────────── 휴장 row ─────────── */
function HolidayBlock({
    region,
    holiday,
}: {
    region: string
    holiday: { name: string; date: string; dDay: number } | null
}) {
    if (!holiday) {
        return (
            <div style={holidayCol}>
                <span style={holidayCapLabel}>{region} 휴장</span>
                <span style={{ color: C.textTertiary, fontSize: T.body }}>없음</span>
            </div>
        )
    }
    const ddColor = holiday.dDay <= 1 ? C.warn : holiday.dDay <= 7 ? C.info : C.textTertiary
    return (
        <div style={holidayCol}>
            <span style={holidayCapLabel}>{region} 다음 휴장</span>
            <div style={{ display: "flex", alignItems: "baseline", gap: S.sm, flexWrap: "wrap" }}>
                <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap }}>
                    {holiday.date.slice(5).replace("-", "/")}
                </span>
                <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi }}>
                    {holiday.name}
                </span>
                <span
                    style={{
                        ...MONO,
                        color: ddColor,
                        fontSize: T.cap,
                        fontWeight: T.w_bold,
                        padding: "2px 6px",
                        borderRadius: R.sm,
                        background: `${ddColor}1A`,
                    }}
                >
                    {holiday.dDay === 0 ? "TODAY" : `D-${holiday.dDay}`}
                </span>
            </div>
        </div>
    )
}


/* ─────────── 스타일 ─────────── */

const shell: CSSProperties = {
    width: "100%",
    boxSizing: "border-box",
    fontFamily: FONT,
    color: C.textPrimary,
    background: C.bgPage,
    border: `1px solid ${C.border}`,
    borderRadius: R.lg,
    padding: S.xxl,
    display: "flex",
    flexDirection: "column",
    gap: S.lg,
}

const grid: CSSProperties = {
    display: "grid",
    gridTemplateColumns: "1fr auto 1fr",
    alignItems: "stretch",
    gap: S.xxl,
}

const column: CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: S.md,
    minWidth: 0,
}

const vDivider: CSSProperties = {
    width: 1,
    background: C.border,
    alignSelf: "stretch",
}

const regionLabel: CSSProperties = {
    color: C.textTertiary,
    fontSize: T.cap,
    fontWeight: T.w_med,
    letterSpacing: "0.12em",
    textTransform: "uppercase",
}

const statusRow: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: S.sm,
}

const stateText: CSSProperties = {
    fontSize: T.body,
    fontWeight: T.w_semi,
    letterSpacing: "0.02em",
}

const heroBlock: CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 2,
    marginTop: S.sm,
}

const heroValue: CSSProperties = {
    fontSize: T.h1,
    fontWeight: T.w_bold,
    letterSpacing: "-0.02em",
    lineHeight: 1.1,
}

const heroLabel: CSSProperties = {
    color: C.textTertiary,
    fontSize: T.cap,
    fontWeight: T.w_med,
    letterSpacing: "0.05em",
    marginTop: 2,
}

const progressWrap: CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 4,
    marginTop: S.sm,
}

const progressTrack: CSSProperties = {
    width: "100%",
    height: 3,
    background: C.bgElevated,
    borderRadius: 2,
    overflow: "hidden",
}

const progressFill: CSSProperties = {
    height: "100%",
    borderRadius: 2,
    transition: "width 0.6s ease",
}

const progressText: CSSProperties = {
    color: C.textTertiary,
    fontSize: T.cap,
    fontWeight: T.w_med,
    letterSpacing: "0.02em",
}

const hDivider: CSSProperties = {
    height: 1,
    background: C.border,
    margin: 0,
}

const holidayRow: CSSProperties = {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: S.xxl,
}

const holidayCol: CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: S.xs,
    minWidth: 0,
}

const holidayCapLabel: CSSProperties = {
    color: C.textTertiary,
    fontSize: T.cap,
    fontWeight: T.w_med,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
}


/* ─────────── Framer Property Controls ─────────── */

MarketStatus.defaultProps = {
    showHoliday: true,
}

addPropertyControls(MarketStatus, {
    showHoliday: {
        type: ControlType.Boolean,
        title: "휴장일 표시",
        defaultValue: true,
    },
})
