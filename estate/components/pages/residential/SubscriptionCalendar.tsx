import { addPropertyControls, ControlType } from "framer"
import React, { useState, useEffect, useMemo, useCallback } from "react"

/* ◆ ESTATE DESIGN TOKENS v1.1 (다크 + 골드 — 패밀리룩) ◆ */
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
const ESTATE_SUBSCRIPTION_CALENDAR_URL = `${ESTATE_API_BASE}/api/estate/subscription-calendar`

/* ──────────────────────────────────────────────────────────────
 * SubscriptionCalendar — ESTATE Tier 2 / D
 *
 * 청약홈 분양정보 (한국부동산원 15098547) → 5종 event 분해 → 시간축 캘린더.
 * 이벤트: recruit(모집공고) / application(접수) / announcement(발표) /
 *         contract(계약) / move_in(입주예정).
 * PolicyShock 와 직교: 정책=과거 충격 누적, 분양=미래 공급 충격 예정표.
 * ────────────────────────────────────────────────────────────── */

type EventType = "recruit" | "application" | "announcement" | "contract" | "move_in"

interface CalendarEvent {
    id: string
    house_manage_no: string
    pblanc_no: string
    house_nm: string
    address: string
    region: string
    event_type: EventType
    date_start: string
    date_end: string | null
    total_supply: number | null
    speclt_rdn_earth: boolean
    business_entity: string
    rent_secd_nm: string | null
    source_url: string
}

interface CalendarPayload {
    schema_version?: string
    fetched_at: string
    namespace: string
    scenario?: "live" | "empty" | "error"
    window: { past_days: number; future_days: number }
    total_subscriptions: number
    events: CalendarEvent[]
    by_month: Record<string, {
        count: number
        by_event_type: Partial<Record<EventType, number>>
        regions: Record<string, number>
        total_supply: number
    }>
    by_region: Record<string, number>
    upcoming_high_impact: CalendarEvent[]
    error?: string
}

const EVENT_META: Record<EventType, { label: string; color: string }> = {
    recruit: { label: "모집공고", color: C.warn },
    application: { label: "청약접수", color: C.accent },
    announcement: { label: "발표", color: C.info },
    contract: { label: "계약", color: C.textSecondary },
    move_in: { label: "입주예정", color: C.success },
}

const WINDOW_OPTIONS: { label: string; past: number; future: number }[] = [
    { label: "이번 달", past: 0, future: 30 },
    { label: "3개월", past: 30, future: 90 },
    { label: "6개월", past: 60, future: 180 },
    { label: "1년", past: 90, future: 365 },
]

interface Props {
    apiUrlOverride?: string
}

export default function SubscriptionCalendar(props: Props) {
    const sourceBase = (props.apiUrlOverride && props.apiUrlOverride.trim()) || ESTATE_SUBSCRIPTION_CALENDAR_URL

    const [windowIdx, setWindowIdx] = useState<number>(1)
    const [eventTypes, setEventTypes] = useState<Set<EventType>>(new Set())
    const [selectedRegion, setSelectedRegion] = useState<string>("")
    const [payload, setPayload] = useState<CalendarPayload | null>(null)
    const [loading, setLoading] = useState<boolean>(true)
    const [error, setError] = useState<string | null>(null)

    const win = WINDOW_OPTIONS[windowIdx]

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        setError(null)
        const url = new URL(sourceBase)
        url.searchParams.set("past_days", String(win.past))
        url.searchParams.set("future_days", String(win.future))
        if (eventTypes.size > 0) url.searchParams.set("event_types", Array.from(eventTypes).join(","))
        if (selectedRegion) url.searchParams.set("regions", selectedRegion)

        fetch(url.toString(), { cache: "no-store" })
            .then(async (r) => {
                if (!r.ok) throw new Error(`upstream ${r.status}`)
                return (await r.json()) as CalendarPayload
            })
            .then((data) => {
                if (cancelled) return
                setPayload(data)
                setLoading(false)
            })
            .catch((e) => {
                if (cancelled) return
                setError(String(e?.message || e))
                setPayload(null)
                setLoading(false)
            })

        return () => { cancelled = true }
    }, [sourceBase, win.past, win.future, eventTypes, selectedRegion])

    const events = payload?.events || []
    const byMonth = payload?.by_month || {}
    const upcoming = payload?.upcoming_high_impact || []
    const regionList = useMemo(
        () => Object.keys(payload?.by_region || {}).sort((a, b) =>
            (payload!.by_region[b] || 0) - (payload!.by_region[a] || 0)),
        [payload],
    )

    const monthKeys = useMemo(() => Object.keys(byMonth).sort(), [byMonth])
    const maxMonthCount = useMemo(() => {
        let m = 0
        for (const k of monthKeys) {
            const c = byMonth[k]?.count || 0
            if (c > m) m = c
        }
        return m || 1
    }, [byMonth, monthKeys])

    const toggleEventType = useCallback((t: EventType) => {
        setEventTypes((prev) => {
            const next = new Set(prev)
            if (next.has(t)) next.delete(t)
            else next.add(t)
            return next
        })
    }, [])

    return (
        <div
            style={{
                width: "100%",
                background: C.bgCard,
                borderRadius: R.lg,
                padding: 16,
                fontFamily: FONT,
                color: C.textPrimary,
                boxSizing: "border-box",
                border: `1px solid ${C.borderStrong}`,
            }}
        >
            {/* HEADER */}
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 4 }}>
                <span style={{ fontSize: 11, letterSpacing: 1.2, color: C.accent, fontFamily: FONT_MONO }}>
                    SUBSCRIPTION · {win.label}
                </span>
                <span style={{ fontSize: 11, color: C.textTertiary }}>
                    {payload?.fetched_at ? `갱신 ${payload.fetched_at.slice(5, 16).replace("T", " ")}` : ""}
                </span>
            </div>
            <div style={{ fontSize: 16, fontWeight: 600, color: C.textPrimary, marginBottom: 12 }}>
                분양 캘린더
                <span style={{ fontSize: 12, fontWeight: 400, color: C.textSecondary, marginLeft: 8 }}>
                    {loading ? "—" : `${events.length}개 일정 / 공고 ${payload?.total_subscriptions ?? "—"}건`}
                </span>
            </div>

            {/* FILTERS — in-component selector */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
                <SelectorPill
                    label="기간"
                    value={String(windowIdx)}
                    options={WINDOW_OPTIONS.map((o, i) => ({ value: String(i), label: o.label }))}
                    onChange={(v) => setWindowIdx(parseInt(v, 10))}
                />
                {regionList.length > 0 && (
                    <SelectorPill
                        label="지역"
                        value={selectedRegion}
                        options={[{ value: "", label: "전체" }, ...regionList.map((r) => ({ value: r, label: r }))]}
                        onChange={setSelectedRegion}
                    />
                )}
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                    {(Object.keys(EVENT_META) as EventType[]).map((t) => {
                        const active = eventTypes.has(t)
                        const meta = EVENT_META[t]
                        return (
                            <button
                                key={t}
                                onClick={() => toggleEventType(t)}
                                style={{
                                    background: active ? meta.color + "26" : "transparent",
                                    color: active ? meta.color : C.textSecondary,
                                    border: `1px solid ${active ? meta.color : C.borderStrong}`,
                                    borderRadius: R.pill,
                                    padding: "4px 10px",
                                    fontSize: 11,
                                    fontFamily: FONT,
                                    cursor: "pointer",
                                    transition: "all 200ms ease",
                                }}
                            >
                                {meta.label}
                            </button>
                        )
                    })}
                </div>
            </div>

            {/* STATE */}
            {loading && <Skeleton height={140} />}
            {!loading && error && (
                <div style={{ padding: 24, textAlign: "center", color: C.textTertiary, fontSize: 12 }}>
                    분양 캘린더 일시 불가
                </div>
            )}
            {!loading && !error && events.length === 0 && (
                <div style={{ padding: 24, textAlign: "center", color: C.textTertiary, fontSize: 12 }}>
                    선택한 윈도우에 일정 없음
                </div>
            )}

            {!loading && !error && events.length > 0 && (
                <>
                    {/* MONTH STRIP */}
                    {monthKeys.length > 0 && (
                        <div style={{ marginBottom: 12 }}>
                            <div style={{ fontSize: 10, color: C.textTertiary, marginBottom: 4, fontFamily: FONT_MONO }}>
                                MONTHLY · COUNT
                            </div>
                            <div
                                style={{
                                    display: "grid",
                                    gridTemplateColumns: `repeat(${monthKeys.length}, 1fr)`,
                                    gap: 4,
                                    background: C.bgElevated,
                                    borderRadius: R.sm,
                                    padding: 8,
                                }}
                            >
                                {monthKeys.map((k) => {
                                    const m = byMonth[k]
                                    const heightPct = (m.count / maxMonthCount) * 100
                                    return (
                                        <div
                                            key={k}
                                            style={{
                                                display: "flex",
                                                flexDirection: "column",
                                                alignItems: "stretch",
                                                gap: 2,
                                            }}
                                        >
                                            <div
                                                title={`${k}: ${m.count}건 (공급 ${m.total_supply})`}
                                                style={{
                                                    height: 36,
                                                    display: "flex",
                                                    flexDirection: "column-reverse",
                                                }}
                                            >
                                                <div
                                                    style={{
                                                        background: C.accent,
                                                        opacity: 0.7,
                                                        height: `${heightPct}%`,
                                                        borderRadius: 2,
                                                    }}
                                                />
                                            </div>
                                            <div
                                                style={{
                                                    fontSize: 9,
                                                    color: C.textTertiary,
                                                    textAlign: "center",
                                                    fontFamily: FONT_MONO,
                                                }}
                                            >
                                                {k.slice(5)}
                                            </div>
                                        </div>
                                    )
                                })}
                            </div>
                        </div>
                    )}

                    {/* HIGH IMPACT (향후 30d + ≥1000세대 recruit) */}
                    {upcoming.length > 0 && (
                        <div style={{ marginBottom: 12 }}>
                            <div style={{ fontSize: 10, color: C.accent, marginBottom: 4, fontFamily: FONT_MONO }}>
                                HIGH IMPACT · 30D · ≥1000세대
                            </div>
                            {upcoming.slice(0, 3).map((e) => (
                                <a
                                    key={e.id}
                                    href={e.source_url || "#"}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    style={{
                                        display: "block",
                                        background: C.bgInput,
                                        border: `1px solid ${C.borderStrong}`,
                                        borderRadius: R.md,
                                        padding: "8px 12px",
                                        marginBottom: 4,
                                        textDecoration: "none",
                                        color: C.textPrimary,
                                        fontSize: 12,
                                    }}
                                >
                                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                                        <span style={{ fontWeight: 500 }}>{e.house_nm}</span>
                                        <span style={{ fontFamily: FONT_MONO, color: C.accentBright }}>
                                            {e.total_supply?.toLocaleString()}세대
                                        </span>
                                    </div>
                                    <div style={{ fontSize: 10, color: C.textTertiary }}>
                                        {e.region} · 공고 {e.date_start}
                                        {e.speclt_rdn_earth && (
                                            <span style={{ color: C.danger, marginLeft: 6 }}>· 투기과열</span>
                                        )}
                                    </div>
                                </a>
                            ))}
                        </div>
                    )}

                    {/* EVENT LIST */}
                    <div style={{ maxHeight: 320, overflowY: "auto" }}>
                        {events.slice(0, 50).map((e) => {
                            const meta = EVENT_META[e.event_type]
                            return (
                                <a
                                    key={e.id}
                                    href={e.source_url || "#"}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    style={{
                                        display: "block",
                                        padding: "8px 0",
                                        borderBottom: `1px solid ${C.borderStrong}`,
                                        textDecoration: "none",
                                        color: C.textPrimary,
                                    }}
                                >
                                    <div style={{ display: "flex", alignItems: "baseline", gap: 8, fontSize: 12 }}>
                                        <span
                                            style={{
                                                fontFamily: FONT_MONO,
                                                fontSize: 10,
                                                color: C.textTertiary,
                                                minWidth: 70,
                                            }}
                                        >
                                            {e.date_start.slice(5)}
                                            {e.date_end && e.date_end !== e.date_start ? `~${e.date_end.slice(5)}` : ""}
                                        </span>
                                        <span
                                            style={{
                                                fontSize: 10,
                                                color: meta.color,
                                                fontWeight: 600,
                                                fontFamily: FONT_MONO,
                                                minWidth: 56,
                                            }}
                                        >
                                            {meta.label}
                                        </span>
                                        <span style={{ flex: 1, color: C.textPrimary }}>{e.house_nm}</span>
                                        <span style={{ fontSize: 10, color: C.textTertiary, fontFamily: FONT_MONO }}>
                                            {e.region}
                                        </span>
                                    </div>
                                </a>
                            )
                        })}
                    </div>
                </>
            )}
        </div>
    )
}

function SelectorPill({
    label, value, options, onChange,
}: {
    label: string
    value: string
    options: { value: string; label: string }[]
    onChange: (v: string) => void
}) {
    return (
        <label
            style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                background: C.bgElevated,
                border: `1px solid ${C.borderStrong}`,
                borderRadius: R.pill,
                padding: "3px 10px",
                fontSize: 11,
                color: C.textSecondary,
            }}
        >
            <span style={{ color: C.textTertiary }}>{label}</span>
            <select
                value={value}
                onChange={(e) => onChange(e.target.value)}
                style={{
                    background: "transparent",
                    border: "none",
                    color: C.accentBright,
                    fontFamily: FONT,
                    fontSize: 11,
                    cursor: "pointer",
                    outline: "none",
                }}
            >
                {options.map((o) => (
                    <option key={o.value} value={o.value} style={{ background: C.bgCard, color: C.textPrimary }}>
                        {o.label}
                    </option>
                ))}
            </select>
        </label>
    )
}

function Skeleton({ height }: { height: number }) {
    return (
        <div
            style={{
                height,
                background: C.bgElevated,
                borderRadius: R.md,
                opacity: 0.5,
            }}
        />
    )
}

addPropertyControls(SubscriptionCalendar, {
    apiUrlOverride: {
        type: ControlType.String,
        title: "API URL (override)",
        defaultValue: "",
        placeholder: ESTATE_SUBSCRIPTION_CALENDAR_URL,
    },
})
