import { addPropertyControls, ControlType } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * EventCalendar — VERITY 통합 이벤트 캘린더
 *
 * 통합 출처:
 *   - USEarningsCalendar.tsx (258줄) — 미장 종목 실적 발표 + 이전 surprise
 *   - USEconCalendar.tsx (218줄) — 미장 거시 경제 이벤트 (FOMC/CPI/NFP 등)
 *
 * 분리 유지:
 *   - MarketCountdown.tsx — "시장 시간 시계" (Calendar 아님, 별도 처리)
 *
 * 모던 심플 6원칙:
 *   1. No card-in-card — 외곽 1개 + 섹션 spacing
 *   2. Flat hierarchy — H1 + cap uppercase 라벨
 *   3. Mono numerics — D-day / 가격 / surprise %
 *   4. Expand on tap — 평소 4건, 더보기 펼침
 *   5. Color discipline — severity = warn/danger/textTertiary 토큰만
 *   6. Hover tooltip — PEAD/SUE/FOMC/CPI/NFP 등 macro 용어
 *
 * Filter chip: 전체 / 실적 / 거시 / TODAY only
 * 섹션: TODAY / UPCOMING (1~14d) / RECENT (-3~-1d)
 *
 * 데이터: portfolio.json
 *   - recommendations[].earnings.next_earnings (실적 일정)
 *   - recommendations[].earnings_surprises (이전 surprise)
 *   - global_events (거시 이벤트 — name/severity/d_day/impact/action)
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
    accent: "0 0 8px rgba(181,255,25,0.35)",
    accentSoft: "0 0 4px rgba(181,255,25,0.20)",
    success: "0 0 6px rgba(34,197,94,0.30)",
    danger: "0 0 6px rgba(239,68,68,0.30)",
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


/* ──────────────────────────────────────────────────────────────
 * ◆ TERMS START ◆ (data/verity_terms.json 발췌)
 * ────────────────────────────────────────────────────────────── */
interface Term {
    label: string
    category?: "metric" | "grade" | "signal" | "concept" | "data_source" | "internal" | "time"
    definition: string
    l3?: boolean
}
const TERMS: Record<string, Term> = {
    PEAD: {
        label: "PEAD (실적 발표 후 드리프트)",
        category: "concept",
        definition: "Post-Earnings-Announcement Drift. 긍정 surprise 후 14d~60d 평균 이상 수익률. Bernard & Thomas (1989) 60일 누적 약 4.2% L/S 스프레드 검증. 60년 robust anomaly.",
    },
    SUE: {
        label: "SUE (표준화 실적 surprise)",
        category: "metric",
        definition: "Standardized Unexpected Earnings. (actual EPS - 기대 EPS) / std(historical surprises). 분위 5등분으로 PEAD score 산출.",
    },
    FOMC: {
        label: "FOMC",
        category: "concept",
        definition: "Federal Open Market Committee — 미 연준 통화정책 결정 회의. 연 8회. 금리 결정·점도표(dot plot)·QE/QT 발표. 발표 직후 시장 변동성 급증.",
    },
    CPI: {
        label: "CPI (소비자물가지수)",
        category: "concept",
        definition: "Consumer Price Index — 미국 소비자 물가 변동률. 매월 BLS 발표. 인플레이션 1차 지표. headline + core 둘 다 시장 영향.",
    },
    PCE: {
        label: "PCE (개인소비지출 물가)",
        category: "concept",
        definition: "Personal Consumption Expenditures Price Index — 연준이 선호하는 인플레이션 지표. core PCE 가 정책 판단 1순위.",
    },
    NFP: {
        label: "NFP (비농업 고용)",
        category: "concept",
        definition: "Nonfarm Payrolls — 매월 첫째 금요일 BLS 발표 비농업 부문 고용 변화. 미국 노동시장 1차 지표.",
    },
    ISM_PMI: {
        label: "ISM PMI",
        category: "concept",
        definition: "Institute for Supply Management PMI. 제조업/서비스. 50 기준 (확장/위축). 경기 선행 지표.",
    },
    GDP: {
        label: "GDP",
        category: "concept",
        definition: "Gross Domestic Product. 미국은 분기별 BEA 발표 (advance/second/final 3차 revision). 경제 성장률 종합 지표.",
    },
}
/* ◆ TERMS END ◆ */


/* ──────────────────────────────────────────────────────────────
 * ◆ TERMTOOLTIP START ◆
 * ────────────────────────────────────────────────────────────── */
function TermTooltip({ termKey, children }: { termKey: string; children: React.ReactNode }) {
    const [show, setShow] = useState(false)
    const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
    const anchorRef = useRef<HTMLSpanElement>(null)
    const term = TERMS[termKey]
    if (!term) return <>{children}</>
    const TIP_W = 320
    const TIP_H = 160
    const handleEnter = () => {
        const el = anchorRef.current
        if (!el || typeof window === "undefined") { setShow(true); return }
        const rect = el.getBoundingClientRect()
        const vw = window.innerWidth
        const vh = window.innerHeight
        const margin = 8
        let left = rect.left
        if (left + TIP_W + margin > vw) left = Math.max(margin, rect.right - TIP_W)
        let top = rect.bottom + 6
        if (top + TIP_H + margin > vh) top = Math.max(margin, rect.top - TIP_H - 6)
        setPos({ top, left })
        setShow(true)
    }
    const handleLeave = () => { setShow(false); setPos(null) }
    return (
        <span
            ref={anchorRef}
            onMouseEnter={handleEnter}
            onMouseLeave={handleLeave}
            onFocus={handleEnter}
            onBlur={handleLeave}
            tabIndex={0}
            style={{
                position: "relative", display: "inline-block",
                borderBottom: `1px dotted ${C.textTertiary}`,
                cursor: "help", outline: "none",
            }}
        >
            {children}
            {show && pos && (
                <div style={{
                    position: "fixed", top: pos.top, left: pos.left,
                    width: TIP_W, zIndex: 100,
                    padding: "10px 12px", borderRadius: R.md,
                    background: C.bgElevated, border: `1px solid ${C.borderStrong}`,
                    boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                    fontFamily: FONT, fontSize: 12, lineHeight: 1.5,
                    whiteSpace: "normal", pointerEvents: "none",
                }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                        <span style={{ color: C.textPrimary, fontWeight: T.w_bold, fontSize: 13 }}>{term.label}</span>
                        {term.l3 && (
                            <span style={{
                                color: C.accent, fontSize: 9,
                                letterSpacing: "1.5px", fontWeight: T.w_black, textTransform: "uppercase",
                                padding: "1px 6px", borderRadius: R.pill,
                                border: `1px solid ${C.accent}60`,
                            }}>L3</span>
                        )}
                    </div>
                    <div style={{ color: C.textSecondary }}>{term.definition}</div>
                </div>
            )}
        </span>
    )
}
/* ◆ TERMTOOLTIP END ◆ */


/* ─────────── Portfolio fetch ─────────── */
const PORTFOLIO_FETCH_TIMEOUT_MS = 15_000

function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}
function fetchJson(url: string, signal?: AbortSignal): Promise<any> {
    const ac = new AbortController()
    if (signal) {
        if (signal.aborted) ac.abort()
        else signal.addEventListener("abort", () => ac.abort(), { once: true })
    }
    const timer = setTimeout(() => ac.abort(), PORTFOLIO_FETCH_TIMEOUT_MS)
    return fetch(bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal: ac.signal })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((t) => JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
        .finally(() => clearTimeout(timer))
}


/* ─────────── 통합 이벤트 모델 ─────────── */
type EventType = "earnings" | "econ"

interface UnifiedEvent {
    type: EventType
    date: string                    // YYYY-MM-DD
    dDay: number                    // 0=오늘, 양수=미래, 음수=과거
    name: string                    // 종목명 또는 이벤트명
    ticker?: string                 // earnings only
    price?: number                  // earnings only
    severity?: "high" | "medium" | "low"  // econ only
    surprise_pct?: number           // earnings: 이전 surprise %
    impact?: string                 // econ only
    action?: string                 // econ only
    impactAreas?: string[]          // econ only
    /** macro 용어 키 (TermTooltip 활성용) */
    termKey?: string
}


/* ─────────── 미장 keyword + macro term 매핑 ─────────── */
const US_KEYWORDS = [
    "FOMC", "CPI", "GDP", "PCE", "PPI", "NFP",
    "고용", "비농업", "Nonfarm", "Fed", "금리결정",
    "ISM", "PMI", "Michigan", "소비자심리", "소비자신뢰", "Conference Board",
    "실업", "Jobless", "주간 실업", "잭슨홀",
    "소비자물가", "소매판매", "Retail", "주택착공", "Housing", "주택판매",
    "삼중마녀", "Quad Witching",
]

function detectTermKey(name: string): string | undefined {
    const n = name.toUpperCase()
    if (n.includes("FOMC") || n.includes("FED") || n.includes("금리결정")) return "FOMC"
    if (n.includes("CPI") || n.includes("소비자물가")) return "CPI"
    if (n.includes("PCE")) return "PCE"
    if (n.includes("NFP") || n.includes("NONFARM") || n.includes("비농업")) return "NFP"
    if (n.includes("ISM") || n.includes("PMI")) return "ISM_PMI"
    if (n.includes("GDP")) return "GDP"
    return undefined
}

function isUSEvent(ev: any): boolean {
    const name = (ev.name || "").toLowerCase()
    return US_KEYWORDS.some((kw) => name.includes(kw.toLowerCase())) || ev.country === "미국"
}

function isUSStock(r: any): boolean {
    return r.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(r.market || "")
}


/* ─────────── 일자 → D-day ─────────── */
function calcDDay(dateStr: string): number {
    if (!dateStr) return 999
    const target = new Date(dateStr + "T00:00:00")
    if (isNaN(target.getTime())) return 999
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    return Math.round((target.getTime() - today.getTime()) / 86400000)
}


/* ─────────── D-day 표시 ─────────── */
function dDayText(d: number): string {
    if (d === 0) return "TODAY"
    if (d > 0) return `D-${d}`
    return `D+${Math.abs(d)}`
}
function dDayColor(d: number): string {
    if (d === 0) return C.danger
    if (d > 0 && d <= 2) return C.warn
    return C.textTertiary
}


/* ─────────── Severity 색 ─────────── */
function severityColor(s?: "high" | "medium" | "low"): { bg: string; fg: string; label: string } {
    switch (s) {
        case "high":   return { bg: `${C.danger}1F`, fg: C.danger, label: "HIGH" }
        case "medium": return { bg: `${C.warn}1F`,   fg: C.warn,   label: "MED" }
        default:       return { bg: `${C.textTertiary}1F`, fg: C.textTertiary, label: "LOW" }
    }
}


/* ═══════════════════════════ 메인 ═══════════════════════════ */

type FilterMode = "all" | "earnings" | "econ" | "today"

interface Props {
    dataUrl: string
}

export default function EventCalendar(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [filter, setFilter] = useState<FilterMode>("all")
    const [showAll, setShowAll] = useState(false)

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal).then((d) => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    /* 통합 timeline 산출 */
    const events = useMemo<UnifiedEvent[]>(() => {
        if (!data) return []
        const all: UnifiedEvent[] = []

        /* earnings: recommendations[].earnings.next_earnings */
        const recs: any[] = data.recommendations || []
        for (const r of recs) {
            if (!isUSStock(r)) continue
            const ne = r.earnings?.next_earnings
            if (!ne) continue
            const dDay = calcDDay(ne)
            if (dDay < -3 || dDay > 14) continue
            const prevSurprise = r.earnings_surprises?.[0]?.surprise_pct
            all.push({
                type: "earnings",
                date: ne,
                dDay,
                name: r.name || r.ticker || "—",
                ticker: r.ticker,
                price: r.price,
                surprise_pct: prevSurprise,
            })
        }

        /* econ: global_events */
        const gevents: any[] = data.global_events || []
        for (const ev of gevents) {
            if (!isUSEvent(ev)) continue
            const dDay = ev.d_day ?? calcDDay(ev.date)
            if (dDay < -3 || dDay > 14) continue
            all.push({
                type: "econ",
                date: ev.date,
                dDay,
                name: ev.name || "—",
                severity: ev.severity,
                impact: ev.impact,
                action: ev.action,
                impactAreas: ev.impact_area,
                termKey: detectTermKey(ev.name || ""),
            })
        }

        /* sort: dDay 오름차순 (TODAY 먼저, UPCOMING, RECENT 마지막) */
        all.sort((a, b) => {
            const aOrder = a.dDay === 0 ? 0 : a.dDay > 0 ? 1 : 2
            const bOrder = b.dDay === 0 ? 0 : b.dDay > 0 ? 1 : 2
            if (aOrder !== bOrder) return aOrder - bOrder
            return Math.abs(a.dDay) - Math.abs(b.dDay)
        })
        return all
    }, [data])

    /* filter 적용 */
    const filtered = useMemo(() => {
        return events.filter((ev) => {
            if (filter === "all") return true
            if (filter === "today") return ev.dDay === 0
            if (filter === "earnings") return ev.type === "earnings"
            if (filter === "econ") return ev.type === "econ"
            return true
        })
    }, [events, filter])

    const todayCount = events.filter((e) => e.dDay === 0).length
    const upcomingCount = events.filter((e) => e.dDay > 0).length
    const recentCount = events.filter((e) => e.dDay < 0).length

    /* 섹션 분리 */
    const todayEvents = filtered.filter((e) => e.dDay === 0)
    const upcomingEvents = filtered.filter((e) => e.dDay > 0)
    const recentEvents = filtered.filter((e) => e.dDay < 0)

    const DEFAULT_VISIBLE = 4

    /* 로딩 */
    if (!data) {
        return (
            <div style={shell}>
                <div style={loadingBox}>
                    <span style={{ color: C.textTertiary, fontSize: T.body }}>이벤트 로딩 중…</span>
                </div>
            </div>
        )
    }

    return (
        <div style={shell}>
            {/* Header */}
            <div style={headerRow}>
                <div style={headerLeft}>
                    <span style={titleStyle}>Event Calendar</span>
                    <span style={metaStyle}>향후 14일 · 오늘 {todayCount}건</span>
                </div>
                <div style={headerRight}>
                    <FilterChip label="전체" active={filter === "all"} onClick={() => setFilter("all")} count={events.length} />
                    <FilterChip label="실적" active={filter === "earnings"} onClick={() => setFilter("earnings")} count={events.filter(e => e.type === "earnings").length} />
                    <FilterChip label="거시" active={filter === "econ"} onClick={() => setFilter("econ")} count={events.filter(e => e.type === "econ").length} />
                    <FilterChip label="오늘" active={filter === "today"} onClick={() => setFilter("today")} count={todayCount} />
                </div>
            </div>

            <div style={hr} />

            {/* TODAY */}
            {todayEvents.length > 0 && (
                <Section label="TODAY" accent={C.danger}>
                    {todayEvents.map((ev, i) => <EventRow key={`t-${i}`} event={ev} />)}
                </Section>
            )}

            {/* UPCOMING */}
            {upcomingEvents.length > 0 && (
                <Section label="UPCOMING" accent={C.warn}>
                    {(showAll ? upcomingEvents : upcomingEvents.slice(0, DEFAULT_VISIBLE)).map((ev, i) => (
                        <EventRow key={`u-${i}`} event={ev} />
                    ))}
                    {upcomingEvents.length > DEFAULT_VISIBLE && (
                        <button onClick={() => setShowAll((v) => !v)} style={moreBtn}>
                            {showAll ? "▾ 접기" : `▸ 더보기 (+${upcomingEvents.length - DEFAULT_VISIBLE})`}
                        </button>
                    )}
                </Section>
            )}

            {/* RECENT */}
            {recentEvents.length > 0 && (
                <Section label="RECENT" accent={C.textTertiary}>
                    {recentEvents.map((ev, i) => <EventRow key={`r-${i}`} event={ev} />)}
                </Section>
            )}

            {filtered.length === 0 && (
                <div style={emptyBox}>
                    <span style={{ color: C.textTertiary, fontSize: T.body }}>해당 조건에 표시할 이벤트 없음</span>
                </div>
            )}
        </div>
    )
}


/* ─────────── 서브 컴포넌트 ─────────── */

function FilterChip({ label, active, onClick, count }: {
    label: string; active: boolean; onClick: () => void; count: number
}) {
    return (
        <button
            onClick={onClick}
            style={{
                background: active ? C.accentSoft : "transparent",
                border: `1px solid ${active ? C.accent : C.border}`,
                color: active ? C.accent : C.textSecondary,
                padding: `${S.xs}px ${S.md}px`,
                borderRadius: R.pill,
                fontSize: T.cap,
                fontWeight: T.w_semi,
                fontFamily: FONT,
                letterSpacing: "0.05em",
                cursor: "pointer",
                transition: X.base,
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
            }}
        >
            <span>{label}</span>
            <span style={{ ...MONO, fontSize: T.cap, color: active ? C.accent : C.textTertiary }}>{count}</span>
        </button>
    )
}

function Section({ label, accent, children }: { label: string; accent: string; children: React.ReactNode }) {
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.sm, padding: `${S.md}px 0` }}>
            <div style={{ display: "flex", alignItems: "center", gap: S.sm }}>
                <span style={{ width: 4, height: 4, borderRadius: "50%", background: accent, boxShadow: `0 0 6px ${accent}80` }} />
                <span style={{
                    color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med,
                    letterSpacing: "0.08em", textTransform: "uppercase",
                }}>
                    {label}
                </span>
            </div>
            <div style={{ display: "flex", flexDirection: "column" }}>{children}</div>
        </div>
    )
}

function EventRow({ event }: { event: UnifiedEvent }) {
    const sev = severityColor(event.severity)
    return (
        <div style={rowStyle}>
            {/* D-day badge */}
            <div style={dDayBlock}>
                <span style={{ ...MONO, color: dDayColor(event.dDay), fontSize: T.body, fontWeight: T.w_bold }}>
                    {dDayText(event.dDay)}
                </span>
                <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap }}>
                    {event.date?.slice(5)}
                </span>
            </div>

            {/* main content */}
            <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 4 }}>
                {/* type + severity + name */}
                <div style={{ display: "flex", alignItems: "center", gap: S.sm, flexWrap: "wrap" }}>
                    {event.type === "earnings" ? (
                        <span style={typeBadge}>EARNINGS</span>
                    ) : (
                        <span style={{ ...typeBadge, background: sev.bg, color: sev.fg, borderColor: sev.fg + "40" }}>
                            {sev.label}
                        </span>
                    )}
                    {event.termKey ? (
                        <TermTooltip termKey={event.termKey}>
                            <span style={nameStyle}>{event.name}</span>
                        </TermTooltip>
                    ) : (
                        <span style={nameStyle}>{event.name}</span>
                    )}
                    {event.ticker && (
                        <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap }}>{event.ticker}</span>
                    )}
                </div>

                {/* econ: impact */}
                {event.type === "econ" && event.impact && (
                    <div style={{ color: C.textSecondary, fontSize: T.cap, lineHeight: T.lh_normal }}>
                        {event.impact}
                    </div>
                )}

                {/* econ: action */}
                {event.type === "econ" && event.action && (
                    <div style={actionBox}>
                        <span style={{ color: C.accent, fontSize: T.cap, fontWeight: T.w_semi }}>권고 </span>
                        <span style={{ color: C.textPrimary, fontSize: T.cap }}>{event.action}</span>
                    </div>
                )}

                {/* econ: impact areas */}
                {event.type === "econ" && event.impactAreas && event.impactAreas.length > 0 && (
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {event.impactAreas.map((area, i) => (
                            <span key={i} style={impactAreaChip}>{area}</span>
                        ))}
                    </div>
                )}

                {/* earnings: prev surprise */}
                {event.type === "earnings" && event.surprise_pct != null && (
                    <div style={{ display: "flex", alignItems: "center", gap: S.sm }}>
                        <span style={{ color: C.textTertiary, fontSize: T.cap }}>이전 </span>
                        <TermTooltip termKey="SUE">
                            <span style={{
                                ...MONO,
                                color: event.surprise_pct >= 0 ? C.success : C.danger,
                                fontSize: T.cap,
                                fontWeight: T.w_semi,
                            }}>
                                {event.surprise_pct >= 0 ? "+" : ""}{event.surprise_pct.toFixed(1)}%
                            </span>
                        </TermTooltip>
                    </div>
                )}
            </div>

            {/* earnings: price (right) */}
            {event.type === "earnings" && event.price != null && (
                <div style={{ flexShrink: 0, ...MONO, color: C.textSecondary, fontSize: T.cap }}>
                    ${event.price.toFixed(2)}
                </div>
            )}
        </div>
    )
}


/* ─────────── 스타일 ─────────── */

const shell: CSSProperties = {
    width: "100%", boxSizing: "border-box",
    fontFamily: FONT, color: C.textPrimary,
    background: C.bgPage,
    border: `1px solid ${C.border}`,
    borderRadius: 16,
    padding: S.xxl,
    display: "flex", flexDirection: "column",
}

const headerRow: CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    gap: S.md, flexWrap: "wrap",
}

const headerLeft: CSSProperties = {
    display: "flex", flexDirection: "column", gap: 2,
}

const headerRight: CSSProperties = {
    display: "flex", gap: S.sm, flexWrap: "wrap",
}

const titleStyle: CSSProperties = {
    fontSize: T.h2, fontWeight: T.w_bold, color: C.textPrimary,
    letterSpacing: "-0.5px", lineHeight: 1.2,
}

const metaStyle: CSSProperties = {
    fontSize: T.cap, color: C.textTertiary, fontWeight: T.w_med,
}

const hr: CSSProperties = {
    height: 1, background: C.border, margin: `${S.md}px 0 0`,
}

const rowStyle: CSSProperties = {
    display: "flex", gap: S.md, alignItems: "flex-start",
    padding: `${S.md}px 0`,
    borderBottom: `1px solid ${C.border}`,
}

const dDayBlock: CSSProperties = {
    display: "flex", flexDirection: "column", alignItems: "center",
    minWidth: 56, flexShrink: 0,
}

const typeBadge: CSSProperties = {
    background: C.bgElevated,
    color: C.textSecondary,
    fontSize: 9,
    fontWeight: T.w_bold,
    letterSpacing: "0.1em",
    padding: "2px 6px",
    borderRadius: R.sm,
    border: `1px solid ${C.border}`,
    fontFamily: FONT,
}

const nameStyle: CSSProperties = {
    color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi,
}

const actionBox: CSSProperties = {
    background: C.accentSoft,
    borderLeft: `2px solid ${C.accent}80`,
    padding: `${S.xs}px ${S.sm}px`,
    borderRadius: R.sm,
    fontFamily: FONT,
}

const impactAreaChip: CSSProperties = {
    background: C.bgElevated,
    color: C.textSecondary,
    fontSize: 9,
    fontWeight: T.w_semi,
    letterSpacing: "0.05em",
    padding: "2px 6px",
    borderRadius: R.sm,
    fontFamily: FONT,
}

const moreBtn: CSSProperties = {
    background: "transparent",
    border: `1px solid ${C.border}`,
    color: C.textSecondary,
    padding: `${S.xs}px ${S.md}px`,
    borderRadius: R.md,
    fontSize: T.cap,
    fontWeight: T.w_semi,
    fontFamily: FONT,
    cursor: "pointer",
    marginTop: S.sm,
    alignSelf: "center",
    transition: X.base,
}

const loadingBox: CSSProperties = {
    minHeight: 200,
    display: "flex", alignItems: "center", justifyContent: "center",
}

const emptyBox: CSSProperties = {
    padding: `${S.xxl}px 0`,
    textAlign: "center",
}


/* ─────────── Framer Property Controls ─────────── */

EventCalendar.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
}

addPropertyControls(EventCalendar, {
    dataUrl: {
        type: ControlType.String,
        title: "Portfolio URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
    },
})
