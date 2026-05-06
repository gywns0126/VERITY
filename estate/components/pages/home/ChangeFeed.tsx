import { addPropertyControls, ControlType } from "framer"
import React, { useState, useEffect, useCallback, useMemo } from "react"

/* ──────────────────────────────────────────────────────────────
 * ◆ ESTATE DESIGN TOKENS v1.1 ◆ (다크 + 골드 emphasis — 패밀리룩)
 * HeroBriefing/SystemPulse/LandexPulse 와 동일 토큰. 직접 hex 박지 말고 C/R 만.
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0A0908",
    bgCard: "#0F0D0A",
    bgElevated: "#16130E",
    bgInput: "#1F1B14",
    border: "transparent",
    borderStrong: "#3A3024",
    textPrimary: "#F2EFE9",
    textSecondary: "#A8A299",
    textTertiary: "#6B665E",
    textDisabled: "#4A453E",
    accent: "#B8864D",
    accentBright: "#D4A26B",
    accentSoft: "rgba(184,134,77,0.15)",
    success: "#22C55E",
    warn: "#F59E0B",
    danger: "#EF4444",
    info: "#5BA9FF",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
/* ◆ TOKENS END ◆ */

const ESTATE_API_BASE = "https://project-yw131.vercel.app"
const ESTATE_CHANGE_FEED_URL = `${ESTATE_API_BASE}/api/estate/change-feed`

/*
 * ESTATE ChangeFeed — Page 1 컴포넌트 4/5 (P1 Mock)
 *
 * contract_change_feed.md (v0.2 — 2 카테고리 축소: regulation + catalyst)
 * - mount 시 /api/estate/change-feed 단일 호출 (anonymous, auth X)
 * - 카테고리 chip filter (local state)
 * - 항목 클릭 → source_url 새 탭
 * - 3 시나리오 (live/empty/error) 모두 의도된 렌더
 * - HeroBriefing/SystemPulse 패밀리룩 정합
 */

type Category = "regulation" | "catalyst"
type Severity = "high" | "mid" | "low"

interface FeedItem {
    id: string
    category: Category
    severity: Severity
    region_label: string
    title: string
    summary: string
    occurred_at: string
    source_name: string
    source_url: string
    drill_down_url?: string | null
}

interface FeedResponse {
    schema_version?: string
    fetched_at: string
    namespace: string
    scenario: "live" | "empty" | "error"
    lookback_hours: number
    items: FeedItem[]
    category_counts: Partial<Record<Category, number>>
    total: number
    error?: string
}

const CATEGORY_META: Record<Category, { label: string; color: string }> = {
    regulation: { label: "규제", color: C.accent },
    catalyst: { label: "호재", color: C.warn },
}

const SEVERITY_META: Record<Severity, { color: string }> = {
    high: { color: C.danger },
    mid: { color: C.warn },
    low: { color: C.textTertiary },
}

function formatRelative(iso: string, now: number): string {
    if (!iso) return "—"
    try {
        const t = new Date(iso).getTime()
        if (isNaN(t)) return "—"
        const minutesAgo = Math.floor((now - t) / 60000)
        if (minutesAgo < 1) return "방금 전"
        if (minutesAgo < 60) return `${minutesAgo}분 전`
        if (minutesAgo < 1440) return `${Math.floor(minutesAgo / 60)}시간 전`
        return `${Math.floor(minutesAgo / 1440)}일 전`
    } catch {
        return "—"
    }
}

interface Props {
    apiUrl: string
    defaultScenario: "live" | "empty" | "error"
    lookbackHours: number
}

function ChangeFeed(props: Props) {
    const { apiUrl, defaultScenario, lookbackHours } = props
    const [data, setData] = useState<FeedResponse | null>(null)
    const [loading, setLoading] = useState(true)
    const [fetchError, setFetchError] = useState<string | null>(null)
    const [activeFilter, setActiveFilter] = useState<Category | null>(null)
    const [now, setNow] = useState<number>(() => Date.now())

    const fetchFeed = useCallback(async () => {
        setLoading(true)
        setFetchError(null)
        try {
            const url = new URL(apiUrl)
            url.searchParams.set("scenario", defaultScenario)
            url.searchParams.set("hours", String(lookbackHours))
            const res = await fetch(url.toString(), { cache: "no-store" })
            if (!res.ok) {
                throw new Error(`HTTP ${res.status}`)
            }
            const json: FeedResponse = await res.json()
            setData(json)
            setNow(Date.now())
        } catch (e: any) {
            // T9 — silent 실패 X
            // eslint-disable-next-line no-console
            console.error("[ChangeFeed] fetch failed:", e)
            setFetchError(e?.message || "fetch failed")
        } finally {
            setLoading(false)
        }
    }, [apiUrl, defaultScenario, lookbackHours])

    useEffect(() => {
        fetchFeed()
    }, [fetchFeed])

    const filteredItems = useMemo(() => {
        if (!data) return []
        if (!activeFilter) return data.items
        return data.items.filter((it) => it.category === activeFilter)
    }, [data, activeFilter])

    return (
        <div style={containerStyle}>
            <Header
                total={data?.total ?? 0}
                lookbackHours={data?.lookback_hours ?? lookbackHours}
                counts={data?.category_counts ?? {}}
                activeFilter={activeFilter}
                onSelectFilter={setActiveFilter}
                onRefresh={fetchFeed}
                loading={loading}
            />
            <Body
                loading={loading}
                fetchError={fetchError}
                data={data}
                items={filteredItems}
                now={now}
            />
        </div>
    )
}

/* ──────────────────────────── Header ──────────────────────────── */

function Header(props: {
    total: number
    lookbackHours: number
    counts: Partial<Record<Category, number>>
    activeFilter: Category | null
    onSelectFilter: (c: Category | null) => void
    onRefresh: () => void
    loading: boolean
}) {
    const { total, lookbackHours, counts, activeFilter, onSelectFilter, onRefresh, loading } = props
    const lookbackLabel = lookbackHours >= 24
        ? `${Math.floor(lookbackHours / 24)}일`
        : `${lookbackHours}시간`

    return (
        <div style={headerStyle}>
            <div style={headerRowStyle}>
                <div style={headerLeftStyle}>
                    <span style={titleStyle}>변동 피드</span>
                    <span style={countBadgeStyle}>전체 {total}</span>
                    <span style={lookbackBadgeStyle}>{lookbackLabel}</span>
                </div>
                <button
                    type="button"
                    onClick={onRefresh}
                    disabled={loading}
                    style={refreshBtnStyle}
                    aria-label="Refresh"
                >
                    {loading ? "..." : "↻"}
                </button>
            </div>
            <div style={chipRowStyle}>
                <ChipButton
                    label="전체"
                    count={total}
                    active={activeFilter === null}
                    color={C.textSecondary}
                    onClick={() => onSelectFilter(null)}
                />
                {(Object.keys(CATEGORY_META) as Category[]).map((cat) => (
                    <ChipButton
                        key={cat}
                        label={CATEGORY_META[cat].label}
                        count={counts[cat] ?? 0}
                        active={activeFilter === cat}
                        color={CATEGORY_META[cat].color}
                        onClick={() => onSelectFilter(cat)}
                    />
                ))}
            </div>
        </div>
    )
}

function ChipButton(props: {
    label: string
    count: number
    active: boolean
    color: string
    onClick: () => void
}) {
    const { label, count, active, color, onClick } = props
    return (
        <button
            type="button"
            onClick={onClick}
            style={{
                ...chipBtnStyle,
                color: active ? C.textPrimary : C.textTertiary,
                borderColor: active ? color : C.border,
                background: active ? `${color}1F` : "transparent",
            }}
        >
            <span style={{ ...chipDotStyle, background: color }} />
            {label} {count}
        </button>
    )
}

/* ──────────────────────────── Body ──────────────────────────── */

function Body(props: {
    loading: boolean
    fetchError: string | null
    data: FeedResponse | null
    items: FeedItem[]
    now: number
}) {
    const { loading, fetchError, data, items, now } = props

    if (loading && !data) {
        return <SkeletonList />
    }

    // T9 — fetch 자체 실패 (네트워크/HTTP) 명시
    if (fetchError) {
        return <ErrorView message={`변동 피드 일시 불가 — ${fetchError}`} />
    }

    // T1 — scenario=error 응답
    if (data?.scenario === "error") {
        return <ErrorView message={data.error || "변동 피드 일시 불가"} />
    }

    if (!items.length) {
        return <EmptyView lookbackHours={data?.lookback_hours ?? 72} />
    }

    return (
        <div style={listStyle}>
            {items.map((it) => (
                <FeedItemCard key={it.id} item={it} now={now} />
            ))}
        </div>
    )
}

function FeedItemCard(props: { item: FeedItem; now: number }) {
    const { item, now } = props
    const cat = CATEGORY_META[item.category] ?? { label: "", color: C.textTertiary }
    const sev = SEVERITY_META[item.severity] ?? { color: C.textTertiary }
    const onClick = () => {
        const url = item.drill_down_url || item.source_url
        if (url) window.open(url, "_blank", "noopener")
    }

    return (
        <button type="button" onClick={onClick} style={itemCardStyle}>
            <div style={itemHeaderStyle}>
                <span style={{ ...itemDotStyle, background: cat.color }} />
                <span style={itemRegionStyle}>{item.region_label}</span>
                <span style={{ ...itemCategoryChipStyle, color: cat.color, borderColor: cat.color }}>
                    {cat.label}
                </span>
                <span style={{ flex: 1 }} />
                <span style={itemTimeStyle}>{formatRelative(item.occurred_at, now)}</span>
            </div>
            <div style={itemTitleStyle}>{item.title}</div>
            {item.summary && <div style={itemSummaryStyle}>{item.summary}</div>}
            <div style={itemFooterStyle}>
                <span style={{ ...itemSeverityDotStyle, background: sev.color }} />
                <span style={itemSourceStyle}>{item.source_name}</span>
            </div>
        </button>
    )
}

function SkeletonList() {
    return (
        <div style={listStyle}>
            {[0, 1, 2].map((i) => (
                <div key={i} style={{ ...itemCardStyle, cursor: "default", pointerEvents: "none" }}>
                    <div style={{ ...skelLineStyle, width: "40%", height: 12 }} />
                    <div style={{ ...skelLineStyle, width: "85%", height: 16, marginTop: 8 }} />
                    <div style={{ ...skelLineStyle, width: "65%", height: 12, marginTop: 6 }} />
                </div>
            ))}
        </div>
    )
}

function EmptyView(props: { lookbackHours: number }) {
    const lookbackLabel = props.lookbackHours >= 24
        ? `지난 ${Math.floor(props.lookbackHours / 24)}일간`
        : `지난 ${props.lookbackHours}시간 동안`
    return (
        <div style={emptyStyle}>{lookbackLabel} 새 변동 없음</div>
    )
}

function ErrorView(props: { message: string }) {
    return (
        <div style={errorStyle}>
            <span style={{ color: C.danger, fontWeight: 600 }}>!</span>
            <span style={{ marginLeft: 8 }}>{props.message}</span>
        </div>
    )
}

/* ──────────────────────────── Styles ──────────────────────────── */

const containerStyle: React.CSSProperties = {
    width: "100%",
    background: C.bgCard,
    borderRadius: R.lg,
    border: `1px solid ${C.border}`,
    padding: 18,
    fontFamily: FONT,
    color: C.textPrimary,
    boxSizing: "border-box",
}

const headerStyle: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 12,
    marginBottom: 14,
    paddingBottom: 12,
    borderBottom: `1px solid ${C.border}`,
}

const headerRowStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
}

const headerLeftStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "baseline",
    gap: 10,
    flexWrap: "wrap",
}

const titleStyle: React.CSSProperties = {
    fontSize: 16,
    fontWeight: 700,
    color: C.textPrimary,
    letterSpacing: "0.01em",
}

const countBadgeStyle: React.CSSProperties = {
    fontSize: 12,
    color: C.textSecondary,
    fontFamily: FONT_MONO,
}

const lookbackBadgeStyle: React.CSSProperties = {
    fontSize: 11,
    color: C.textTertiary,
    fontFamily: FONT_MONO,
    padding: "2px 6px",
    borderRadius: R.sm,
    border: `1px solid ${C.border}`,
}

const refreshBtnStyle: React.CSSProperties = {
    fontFamily: FONT_MONO,
    fontSize: 14,
    color: C.textSecondary,
    background: "transparent",
    border: `1px solid ${C.border}`,
    borderRadius: R.sm,
    padding: "4px 10px",
    cursor: "pointer",
}

const chipRowStyle: React.CSSProperties = {
    display: "flex",
    flexWrap: "wrap",
    gap: 6,
}

const chipBtnStyle: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    fontFamily: FONT,
    fontSize: 12,
    fontWeight: 600,
    padding: "5px 10px",
    borderRadius: R.pill,
    border: `1px solid ${C.border}`,
    cursor: "pointer",
    transition: "all 180ms ease",
}

const chipDotStyle: React.CSSProperties = {
    width: 6,
    height: 6,
    borderRadius: "50%",
    display: "inline-block",
}

const listStyle: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 8,
}

const itemCardStyle: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 4,
    background: C.bgElevated,
    borderRadius: R.md,
    border: `1px solid ${C.border}`,
    padding: "12px 14px",
    cursor: "pointer",
    textAlign: "left",
    fontFamily: FONT,
    color: C.textPrimary,
    transition: "background 180ms ease",
}

const itemHeaderStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 8,
    fontSize: 11,
}

const itemDotStyle: React.CSSProperties = {
    width: 6,
    height: 6,
    borderRadius: "50%",
    display: "inline-block",
}

const itemRegionStyle: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 600,
    color: C.textSecondary,
}

const itemCategoryChipStyle: React.CSSProperties = {
    fontSize: 10,
    fontWeight: 700,
    padding: "1px 6px",
    borderRadius: R.sm,
    border: `1px solid ${C.border}`,
    letterSpacing: "0.05em",
}

const itemTimeStyle: React.CSSProperties = {
    fontSize: 11,
    color: C.textTertiary,
    fontFamily: FONT_MONO,
}

const itemTitleStyle: React.CSSProperties = {
    fontSize: 14,
    fontWeight: 700,
    color: C.textPrimary,
    marginTop: 4,
    lineHeight: 1.4,
}

const itemSummaryStyle: React.CSSProperties = {
    fontSize: 12,
    color: C.textSecondary,
    lineHeight: 1.5,
    marginTop: 2,
}

const itemFooterStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 6,
    marginTop: 6,
    fontSize: 11,
    color: C.textTertiary,
}

const itemSeverityDotStyle: React.CSSProperties = {
    width: 5,
    height: 5,
    borderRadius: "50%",
    display: "inline-block",
}

const itemSourceStyle: React.CSSProperties = {
    fontSize: 11,
    color: C.textTertiary,
    fontFamily: FONT_MONO,
}

const skelLineStyle: React.CSSProperties = {
    background: `linear-gradient(90deg, ${C.bgElevated} 25%, ${C.bgInput} 50%, ${C.bgElevated} 75%)`,
    backgroundSize: "200% 100%",
    animation: "estateSkel 1.4s linear infinite",
    borderRadius: R.sm,
}

const emptyStyle: React.CSSProperties = {
    padding: "32px 12px",
    textAlign: "center",
    color: C.textTertiary,
    fontSize: 13,
    fontFamily: FONT,
}

const errorStyle: React.CSSProperties = {
    padding: "16px 12px",
    color: C.textSecondary,
    fontSize: 13,
    background: C.bgElevated,
    borderRadius: R.md,
    border: `1px solid ${C.border}`,
    display: "flex",
    alignItems: "center",
}

/* skeleton keyframes (Framer 환경 정합) */
if (typeof document !== "undefined" && !document.getElementById("estate-skel-kf")) {
    const s = document.createElement("style")
    s.id = "estate-skel-kf"
    s.textContent = `@keyframes estateSkel { 0%{background-position:200% 0} 100%{background-position:-200% 0} }`
    document.head.appendChild(s)
}

/* ──────────────────────────── Framer ──────────────────────────── */

ChangeFeed.defaultProps = {
    apiUrl: ESTATE_CHANGE_FEED_URL,
    defaultScenario: "live",
    lookbackHours: 72,
}

addPropertyControls(ChangeFeed, {
    apiUrl: {
        type: ControlType.String,
        title: "API URL",
        defaultValue: ESTATE_CHANGE_FEED_URL,
        description: "/api/estate/change-feed endpoint",
    },
    defaultScenario: {
        type: ControlType.Enum,
        title: "Scenario (P1 Mock)",
        defaultValue: "live",
        options: ["live", "empty", "error"],
        optionTitles: ["Live", "Empty", "Error"],
        description: "P1 Mock 검증용 — endpoint 가 ?scenario= 따라 분기",
    },
    lookbackHours: {
        type: ControlType.Number,
        title: "Lookback (hours)",
        defaultValue: 72,
        min: 1,
        max: 168,
        step: 1,
        description: "기본 72h (3일). 1~168 가드.",
    },
})

export default ChangeFeed
