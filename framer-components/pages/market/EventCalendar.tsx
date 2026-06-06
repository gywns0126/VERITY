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
    bgPage: "#0a0a0a", bgCard: "#141414", bgElevated: "#1a1a1a", bgInput: "transparent",
    border: "rgba(255,255,255,0.06)", borderStrong: "rgba(255,255,255,0.10)", borderHover: "#7fffa0",
    textPrimary: "#ffffff", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#7fffa0", accentSoft: "rgba(127, 255, 160,0.12)",
    success: "#22C55E", warn: "#F59E0B", danger: "#EF4444", info: "#5BA9FF",
}
const G = {
    accent: "0 0 8px rgba(127, 255, 160,0.35)",
    accentSoft: "0 0 4px rgba(127, 255, 160,0.20)",
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
                
                cursor: "help", outline: "none",
            }}
        >
            {children}
            {show && pos && (
                <div style={{
                    position: "fixed", top: pos.top, left: pos.left,
                    width: TIP_W, zIndex: 100,
                    padding: "10px 12px", borderRadius: R.md,
                    background: C.bgElevated,
                    border: `1px solid ${C.border}`,
                    fontFamily: FONT, fontSize: 12, lineHeight: 1.5,
                    whiteSpace: "normal", pointerEvents: "none",
                }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                        <span style={{ color: C.textPrimary, fontWeight: T.w_bold, fontSize: 13 }}>{term.label}</span>
                        {term.l3 && (
                            <span style={{
                                color: C.accent, fontSize: 9,
                                letterSpacing: 1.5, fontWeight: T.w_black, textTransform: "uppercase",
                                padding: "1px 6px", borderRadius: R.sm,
                                
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

// ── last-good 캐시 fallback (2026-06-06 표준 스니펫, self-contained) ──
const CACHE_KEY = "verity_cache_eventcal"
function loadCache(key: string): { data: any; ts: number } | null {
    try {
        const raw = localStorage.getItem(key)
        if (!raw) return null
        const obj = JSON.parse(raw)
        return obj && obj.ts ? obj : null
    } catch (e) {
        return null
    }
}
function saveCache(key: string, data: any) {
    try {
        localStorage.setItem(key, JSON.stringify({ data: data, ts: Date.now() }))
    } catch (e) {
        // quota 등 저장 실패 무시
    }
}
function cacheAge(ts: number): string {
    const m = Math.round((Date.now() - ts) / 60000)
    if (m < 1) return "방금 전"
    if (m < 60) return `${m}분 전`
    const h = Math.round(m / 60)
    return h < 24 ? `${h}시간 전` : `${Math.round(h / 24)}일 전`
}


/* ─────────── 통합 이벤트 모델 ─────────── */
type EventType = "earnings" | "econ" | "dart"

interface UnifiedEvent {
    type: EventType
    date: string                    // YYYY-MM-DD
    dDay: number                    // 0=오늘, 양수=미래, 음수=과거
    name: string                    // 종목명 또는 이벤트명
    ticker?: string                 // earnings / dart
    price?: number                  // earnings only
    severity?: "high" | "medium" | "low"  // econ only
    surprise_pct?: number           // earnings: 이전 surprise %
    impact?: string                 // econ only
    action?: string                 // econ only
    impactAreas?: string[]          // econ only
    /** macro 용어 키 (TermTooltip 활성용) */
    termKey?: string
    /** dart_catalyst_alerts.events 직결 (자체 5-tier 산식, 2026-05-23 PM 사전등록 RULE 7) */
    severityNum?: number            // dart only: 1~5
    pblntfLabel?: string            // dart only: "지분공시" / "발행공시" / "주요사항보고"
    reportNm?: string               // dart only: 보고서명
    isCorrection?: boolean          // dart only: 정정공시 여부 (restatement risk)
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

/** mode 별 종목 노출 분기 (KR/US 토글 모델 호환) */
function matchMarketStock(r: any, mode: "us" | "kr" | "all"): boolean {
    const us = isUSStock(r)
    if (mode === "us") return us
    if (mode === "kr") return !us
    return true
}

/** mode 별 거시 이벤트 노출 분기 */
function matchMarketEvent(ev: any, mode: "us" | "kr" | "all"): boolean {
    const us = isUSEvent(ev)
    if (mode === "us") return us
    if (mode === "kr") return !us
    return true
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
        case "high":   return { bg: `${C.bgElevated}`, fg: C.danger, label: "HIGH" }
        case "medium": return { bg: `${C.bgElevated}`,   fg: C.warn,   label: "MED" }
        default:       return { bg: `${C.bgElevated}`, fg: C.textTertiary, label: "LOW" }
    }
}


/* ═══════════════════════════ 메인 ═══════════════════════════ */

type FilterMode = "all" | "earnings" | "econ" | "dart" | "today"

interface Props {
    dataUrl: string
    market?: "us" | "kr" | "all"
}

export default function EventCalendar(props: Props) {
    const { dataUrl, market = "us" } = props
    const [data, setData] = useState<any>(null)
    const [cacheTs, setCacheTs] = useState<number | null>(null)
    const [filter, setFilter] = useState<FilterMode>("all")
    const [showAll, setShowAll] = useState(false)

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal)
            .then((d) => { if (!ac.signal.aborted) { saveCache(CACHE_KEY, d); setData(d); setCacheTs(null) } })
            .catch(() => { const c = loadCache(CACHE_KEY); if (c) { setData(c.data); setCacheTs(c.ts) } })
        return () => ac.abort()
    }, [dataUrl])

    /* 통합 timeline 산출 */
    const events = useMemo<UnifiedEvent[]>(() => {
        if (!data) return []
        const all: UnifiedEvent[] = []

        /* earnings: recommendations[].earnings.next_earnings */
        const recs: any[] = data.recommendations || []
        for (const r of recs) {
            if (!matchMarketStock(r, market)) continue
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
            if (!matchMarketEvent(ev, market)) continue
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

        /* dart: dart_catalyst_alerts.events (KR 한정, 자체 5-tier 산식 직결) */
        if (market !== "us") {
            const dca: any[] = data.dart_catalyst_alerts?.events || []
            for (const e of dca) {
                const rd = String(e.rcept_dt || "")
                // rcept_dt = "20260521" → "2026-05-21"
                const date = rd.length === 8
                    ? `${rd.slice(0, 4)}-${rd.slice(4, 6)}-${rd.slice(6, 8)}`
                    : ""
                if (!date) continue
                const dDay = calcDDay(date)
                if (dDay < -7 || dDay > 14) continue
                all.push({
                    type: "dart",
                    date,
                    dDay,
                    name: e.name || e.ticker || "—",
                    ticker: e.ticker,
                    severityNum: typeof e.severity === "number" ? e.severity : undefined,
                    pblntfLabel: e.pblntf_label,
                    reportNm: e.report_nm,
                    isCorrection: e.is_correction === true,
                })
            }
        }

        /* sort: dDay 오름차순 (TODAY 먼저, UPCOMING, RECENT 마지막) */
        all.sort((a, b) => {
            const aOrder = a.dDay === 0 ? 0 : a.dDay > 0 ? 1 : 2
            const bOrder = b.dDay === 0 ? 0 : b.dDay > 0 ? 1 : 2
            if (aOrder !== bOrder) return aOrder - bOrder
            return Math.abs(a.dDay) - Math.abs(b.dDay)
        })
        return all
    }, [data, market])

    /* filter 적용 */
    const filtered = useMemo(() => {
        return events.filter((ev) => {
            if (filter === "all") return true
            if (filter === "today") return ev.dDay === 0
            if (filter === "earnings") return ev.type === "earnings"
            if (filter === "econ") return ev.type === "econ"
            if (filter === "dart") return ev.type === "dart"
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
            {cacheTs != null && (
                <div style={{ fontSize: 11, color: "#F59E0B", fontFamily: FONT, marginBottom: 6 }}>
                    ⚠ 오프라인 · {cacheAge(cacheTs)} 데이터
                </div>
            )}
            {/* Header */}
            <div style={headerRow}>
                <div style={headerLeft}>
                    <span style={titleStyle}>Event Calendar</span>
                    <span style={metaStyle}>
                        향후 14일 · 오늘 {todayCount}건
                        {events.some((e) => e.type === "dart") && " · DART 5-tier 자체 산식 (가설)"}
                    </span>
                </div>
                <div style={headerRight}>
                    <FilterChip label="전체" active={filter === "all"} onClick={() => setFilter("all")} count={events.length} />
                    <FilterChip label="실적" active={filter === "earnings"} onClick={() => setFilter("earnings")} count={events.filter(e => e.type === "earnings").length} />
                    <FilterChip label="거시" active={filter === "econ"} onClick={() => setFilter("econ")} count={events.filter(e => e.type === "econ").length} />
                    {events.some((e) => e.type === "dart") && (
                        <FilterChip label="공시" active={filter === "dart"} onClick={() => setFilter("dart")} count={events.filter(e => e.type === "dart").length} />
                    )}
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
            style={{ border: "none",
                background: "transparent",
                
                color: active ? C.textPrimary : C.textTertiary,
                padding: `${S.xs}px ${S.md}px`,
                borderRadius: R.sm,
                fontSize: T.cap,
                fontWeight: active ? T.w_bold : T.w_semi,
                fontFamily: FONT,
                letterSpacing: 0.5,
                textTransform: "uppercase",
                cursor: "pointer",
                transition: "color 180ms ease, border-color 180ms ease",
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
                <span style={{ width: 4, height: 4, borderRadius: "50%", background: accent, boxShadow: `0 0 6px ${accent}` }} />
                <span style={{
                    color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med,
                    letterSpacing: 1, textTransform: "uppercase",
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
    // dart severity 5-tier 색 매핑 (2026-05-23 backend PM 사전등록, RULE 7)
    const dartSev = (() => {
        const n = event.severityNum
        if (n === 5) return { fg: C.danger, label: "LV5" }
        if (n === 4) return { fg: C.danger, label: "LV4" }
        if (n === 3) return { fg: C.warn, label: "LV3" }
        if (n === 2) return { fg: C.textSecondary, label: "LV2" }
        if (n === 1) return { fg: C.textTertiary, label: "LV1" }
        return { fg: C.textTertiary, label: "LV?" }
    })()
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
                    ) : event.type === "dart" ? (
                        <span style={{ ...typeBadge, background: C.bgElevated, color: dartSev.fg, borderColor: dartSev.fg + "40" }}>
                            {dartSev.label}
                        </span>
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

                {/* dart: pblntf_label + report_nm + correction flag */}
                {event.type === "dart" && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: S.sm, flexWrap: "wrap" }}>
                            {event.pblntfLabel && (
                                <span style={impactAreaChip}>{event.pblntfLabel}</span>
                            )}
                            {event.isCorrection && (
                                <span style={{
                                    background: `${C.danger}1A`,
                                    color: C.danger,
                                    fontSize: T.cap,
                                    fontWeight: T.w_bold,
                                    padding: `2px ${S.sm}px`,
                                    borderRadius: R.sm,
                                    letterSpacing: 0.5,
                                }}>정정공시</span>
                            )}
                        </div>
                        {event.reportNm && (
                            <div style={{ color: C.textSecondary, fontSize: T.cap, lineHeight: T.lh_normal }}>
                                {event.reportNm.length > 40 ? event.reportNm.slice(0, 38) + "…" : event.reportNm}
                            </div>
                        )}
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

    borderRadius: 8,
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
    letterSpacing: -0.5, lineHeight: 1.2,
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
    
}

const dDayBlock: CSSProperties = {
    display: "flex", flexDirection: "column", alignItems: "center",
    minWidth: 56, flexShrink: 0,
}

const typeBadge: CSSProperties = {
    background: "transparent",
    color: C.textSecondary,
    fontSize: 9,
    fontWeight: T.w_bold,
    letterSpacing: 1,
    padding: "2px 6px",
    borderRadius: R.sm,
    
    fontFamily: FONT,
}

const nameStyle: CSSProperties = {
    color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi,
}

const actionBox: CSSProperties = {
    background: "transparent",
    
    padding: `${S.xs}px ${S.sm}px`,
    borderRadius: R.sm,
    fontFamily: FONT,
}

const impactAreaChip: CSSProperties = {
    background: "transparent",
    color: C.textSecondary,
    fontSize: 9,
    fontWeight: T.w_semi,
    letterSpacing: 0.5,
    padding: "2px 6px",
    borderRadius: R.sm,
    fontFamily: FONT,
}

const moreBtn: CSSProperties = {
    border: "none",
    background: "transparent",
    
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
    dataUrl: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/portfolio.json",
    market: "us",
}

addPropertyControls(EventCalendar, {
    dataUrl: {
        type: ControlType.String,
        title: "Portfolio URL",
        defaultValue: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/portfolio.json",
    },
    market: {
        type: ControlType.Enum,
        title: "시장",
        options: ["us", "kr", "all"],
        optionTitles: ["미장 (US)", "국장 (KR)", "전체"],
        defaultValue: "us",
    },
})
