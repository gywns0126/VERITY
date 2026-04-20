import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"

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


function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    return `${u}${u.includes("?") ? "&" : "?"}_=${Date.now()}`
}

const _FETCH: RequestInit = { cache: "no-store", mode: "cors", credentials: "omit" }

function fetchJson(url: string, signal?: AbortSignal): Promise<any> {
    return fetch(bustUrl(url), { ..._FETCH, signal })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((t) => JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
}

const DATA_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"
const F = "'Inter', 'Pretendard', -apple-system, sans-serif"

interface Props { dataUrl: string }

const US_KEYWORDS = [
    "FOMC", "CPI", "GDP", "PCE", "PPI", "NFP",
    "고용", "비농업", "Nonfarm", "Fed", "금리결정",
    "ISM", "PMI", "Michigan", "소비자심리", "소비자신뢰", "Conference Board",
    "실업", "Jobless", "주간 실업", "잭슨홀",
    "소비자물가", "소매판매", "Retail", "주택착공", "Housing", "주택판매",
    "삼중마녀", "Quad Witching",
]
const SEVERITY_COLORS: Record<string, { bg: string; text: string; label: string }> = {
    high: { bg: "rgba(239,68,68,0.15)", text: "#EF4444", label: "HIGH" },
    medium: { bg: "rgba(245,158,11,0.15)", text: "#F59E0B", label: "MED" },
    low: { bg: "rgba(100,100,100,0.1)", text: "#888", label: "LOW" },
}

function dDayText(d: number): string {
    if (d === 0) return "TODAY"
    if (d === 1) return "D-1"
    if (d < 0) return `D+${Math.abs(d)}`
    return `D-${d}`
}

function dDayColor(d: number): string {
    if (d === 0) return "#EF4444"
    if (d <= 2) return "#F59E0B"
    return "#666"
}

export default function USEconCalendar(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    const allEvents: any[] = data?.global_events || []
    const usEvents = allEvents.filter((ev) => {
        const name = (ev.name || "").toLowerCase()
        const isUS = US_KEYWORDS.some((kw) => name.includes(kw.toLowerCase())) || ev.country === "미국"
        const dDay = ev.d_day ?? 99
        return isUS && dDay >= -3 && dDay <= 14
    })

    const todayEvents = usEvents.filter((e) => e.d_day === 0)
    const upcomingEvents = usEvents.filter((e) => (e.d_day || 0) > 0)
    const pastEvents = usEvents.filter((e) => (e.d_day || 0) < 0)

    if (!data) {
        return (
            <div style={{ ...card, minHeight: 140, alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: C.textTertiary, fontSize: 13, fontFamily: F }}>경제 캘린더 로딩 중...</span>
            </div>
        )
    }

    return (
        <div style={card}>
            <div style={header}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 16, fontWeight: 800, color: C.textPrimary, fontFamily: F }}>🏛️ US Economic Calendar</span>
                    {todayEvents.length > 0 && (
                        <span style={{ ...liveBadge }}>LIVE {todayEvents.length}</span>
                    )}
                </div>
                <span style={{ color: C.textTertiary, fontSize: 12, fontFamily: F }}>향후 14일</span>
            </div>

            <div style={{ padding: "0 14px 14px", maxHeight: 480, overflowY: "auto" }}>
                {todayEvents.length > 0 && (
                    <EventSection label="🔴 TODAY" events={todayEvents} />
                )}
                {upcomingEvents.length > 0 && (
                    <EventSection label="📅 UPCOMING" events={upcomingEvents} />
                )}
                {pastEvents.length > 0 && (
                    <EventSection label="✅ RECENT" events={pastEvents} />
                )}
                {usEvents.length === 0 && (
                    <div style={{ padding: 30, textAlign: "center" }}>
                        <span style={{ color: C.textTertiary, fontSize: 13, fontFamily: F }}>향후 14일간 주요 미국 경제 이벤트 없음</span>
                    </div>
                )}
            </div>
        </div>
    )
}

function EventSection({ label, events }: { label: string; events: any[] }) {
    return (
        <div style={{ marginTop: 10 }}>
            <div style={{ color: C.textSecondary, fontSize: 12, fontWeight: 700, letterSpacing: 1, marginBottom: 6, fontFamily: F }}>{label}</div>
            {events.map((ev, i) => {
                const sev = SEVERITY_COLORS[ev.severity] || SEVERITY_COLORS.low
                const dDay = ev.d_day ?? 0
                const impactAreas: string[] = ev.impact_area || []
                return (
                    <div key={i} style={row}>
                        <div style={{ display: "flex", alignItems: "flex-start", gap: 10, flex: 1, minWidth: 0 }}>
                            <div style={{ textAlign: "center", flexShrink: 0, minWidth: 44 }}>
                                <div style={{ color: dDayColor(dDay), fontSize: 13, fontWeight: 800, fontFamily: F }}>{dDayText(dDay)}</div>
                                <div style={{ color: C.textTertiary, fontSize: 8, fontFamily: F }}>{ev.date?.slice(5) || ""}</div>
                            </div>
                            <div style={{ minWidth: 0, flex: 1 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                                    <span style={{
                                        background: sev.bg, color: sev.text, fontSize: 7, fontWeight: 800,
                                        padding: "2px 5px", borderRadius: 3, fontFamily: F,
                                    }}>{sev.label}</span>
                                    <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: F }}>{ev.name}</span>
                                </div>
                                {ev.impact && (
                                    <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: F, lineHeight: 1.4, marginBottom: 4 }}>{ev.impact}</div>
                                )}
                                {ev.action && (
                                    <div style={{
                                        color: "#B5FF19", fontSize: 12, fontFamily: F, lineHeight: 1.4,
                                        background: "rgba(181,255,25,0.05)", padding: "4px 6px", borderRadius: 6,
                                        borderLeft: "2px solid #B5FF1940",
                                    }}>💡 {ev.action}</div>
                                )}
                                {impactAreas.length > 0 && (
                                    <div style={{ display: "flex", gap: 4, marginTop: 4, flexWrap: "wrap" }}>
                                        {impactAreas.map((area, j) => (
                                            <span key={j} style={{
                                                background: C.bgElevated, color: C.textSecondary, fontSize: 8, fontWeight: 600,
                                                padding: "2px 6px", borderRadius: 3, fontFamily: F,
                                            }}>{area}</span>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                )
            })}
        </div>
    )
}

USEconCalendar.defaultProps = { dataUrl: DATA_URL }
addPropertyControls(USEconCalendar, {
    dataUrl: { type: ControlType.String, title: "JSON URL", defaultValue: DATA_URL },
})

const card: React.CSSProperties = {
    width: "100%", background: C.bgPage, borderRadius: 16,
    border: `1px solid ${C.border}`, overflow: "hidden",
    display: "flex", flexDirection: "column", fontFamily: F,
}
const header: React.CSSProperties = {
    padding: "14px 16px", borderBottom: `1px solid ${C.border}`,
    display: "flex", justifyContent: "space-between", alignItems: "center",
}
const liveBadge: React.CSSProperties = {
    background: "rgba(239,68,68,0.2)", color: "#EF4444", fontSize: 12, fontWeight: 800,
    padding: "3px 8px", borderRadius: 6, fontFamily: F,
    animation: "pulse 2s ease-in-out infinite",
}
const row: React.CSSProperties = {
    padding: "10px 0", borderBottom: `1px solid ${C.border}`,
}
