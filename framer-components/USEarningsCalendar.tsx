import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"

function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

const _FETCH: RequestInit = { cache: "no-store", mode: "cors", credentials: "omit" }

function fetchJson(url: string): Promise<any> {
    return fetch(bustUrl(url), _FETCH)
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((t) => JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
}

const DATA_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"
const F = "'Inter', 'Pretendard', -apple-system, sans-serif"

interface Props { dataUrl: string }

export default function USEarningsCalendar(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [showAllUpcoming, setShowAllUpcoming] = useState(false)
    const [showAllSurprises, setShowAllSurprises] = useState(false)

    useEffect(() => {
        if (!dataUrl) return
        fetchJson(dataUrl).then(setData).catch(console.error)
    }, [dataUrl])

    const allRecs: any[] = data?.recommendations || []
    const usRecs = allRecs.filter((r) => r.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(r.market || ""))

    const withEarnings = usRecs
        .filter((r) => r.earnings?.next_earnings || (Array.isArray(r.earnings_surprises) && r.earnings_surprises.length > 0))
        .sort((a, b) => {
            const da = a.earnings?.next_earnings || "9999"
            const db = b.earnings?.next_earnings || "9999"
            return da.localeCompare(db)
        })

    const upcoming = withEarnings.filter((r) => r.earnings?.next_earnings)
    const withSurprises = usRecs.filter((r) => Array.isArray(r.earnings_surprises) && r.earnings_surprises.length > 0)
    const UPCOMING_DEFAULT_COUNT = 4
    const SURPRISE_DEFAULT_COUNT = 4
    const upcomingToRender = showAllUpcoming ? upcoming : upcoming.slice(0, UPCOMING_DEFAULT_COUNT)
    const surprisesToRender = showAllSurprises ? withSurprises.slice(0, 10) : withSurprises.slice(0, SURPRISE_DEFAULT_COUNT)

    const avgSurprise = (() => {
        let sum = 0, cnt = 0
        withSurprises.forEach((r) => {
            const latest = r.earnings_surprises[0]
            if (latest?.surprise_pct != null) { sum += latest.surprise_pct; cnt++ }
        })
        return cnt > 0 ? (sum / cnt) : null
    })()

    if (!data) {
        return (
            <div style={{ ...card, minHeight: 160, alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: "#666", fontSize: 13, fontFamily: F }}>실적 캘린더 로딩 중...</span>
            </div>
        )
    }

    return (
        <div style={card}>
            <div style={header}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 16, fontWeight: 800, color: "#fff", fontFamily: F }}>📅 Earnings Calendar</span>
                    <span style={badge}>{upcoming.length}건 예정</span>
                </div>
                {avgSurprise !== null && (
                    <span style={{ color: avgSurprise >= 0 ? "#22C55E" : "#EF4444", fontSize: 11, fontWeight: 700, fontFamily: F }}>
                        평균 서프라이즈 {avgSurprise >= 0 ? "+" : ""}{avgSurprise.toFixed(1)}%
                    </span>
                )}
            </div>

            {upcoming.length > 0 && (
                <div style={section}>
                    <span style={sectionLabel}>다가오는 실적 발표</span>
                    {upcomingToRender.map((r, i) => {
                        const prevSurprise = r.earnings_surprises?.[0]
                        return (
                            <div key={i} style={row}>
                                <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 0 }}>
                                    <span style={dateChip}>{r.earnings.next_earnings}</span>
                                    <div style={{ minWidth: 0 }}>
                                        <span style={{ color: "#fff", fontSize: 13, fontWeight: 700, fontFamily: F, display: "block" }}>{r.name}</span>
                                        <span style={{ color: "#555", fontSize: 10, fontFamily: F }}>{r.ticker}</span>
                                    </div>
                                </div>
                                <div style={{ textAlign: "right", flexShrink: 0 }}>
                                    <span style={{ color: "#888", fontSize: 11, fontFamily: F, display: "block" }}>
                                        ${r.price?.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </span>
                                    {prevSurprise && (
                                        <span style={{ color: prevSurprise.surprise_pct >= 0 ? "#22C55E" : "#EF4444", fontSize: 10, fontWeight: 700, fontFamily: F }}>
                                            이전 {prevSurprise.surprise_pct >= 0 ? "+" : ""}{prevSurprise.surprise_pct}%
                                        </span>
                                    )}
                                </div>
                            </div>
                        )
                    })}
                    {upcoming.length > UPCOMING_DEFAULT_COUNT && (
                        <button
                            onClick={() => setShowAllUpcoming((v) => !v)}
                            style={toggleButton}
                        >
                            {showAllUpcoming ? "접기" : `더보기 (+${upcoming.length - UPCOMING_DEFAULT_COUNT})`}
                        </button>
                    )}
                </div>
            )}

            {withSurprises.length > 0 && (
                <div style={section}>
                    <span style={sectionLabel}>최근 실적 서프라이즈</span>
                    {surprisesToRender.map((r, i) => {
                        const surprises: any[] = r.earnings_surprises || []
                        return (
                            <div key={i} style={{ ...row, flexDirection: "column", gap: 6 }}>
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                    <div>
                                        <span style={{ color: "#fff", fontSize: 12, fontWeight: 700, fontFamily: F }}>{r.name}</span>
                                        <span style={{ color: "#555", fontSize: 10, marginLeft: 6 }}>{r.ticker}</span>
                                    </div>
                                    <span style={{ color: "#888", fontSize: 11, fontFamily: F }}>
                                        ${r.price?.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </span>
                                </div>
                                <div style={{ display: "flex", gap: 4 }}>
                                    {surprises.slice(0, 4).map((s, j) => {
                                        const sp = s.surprise_pct || 0
                                        const color = sp > 0 ? "#22C55E" : sp < 0 ? "#EF4444" : "#666"
                                        const bg = sp > 0 ? "rgba(34,197,94,0.1)" : sp < 0 ? "rgba(239,68,68,0.1)" : "rgba(100,100,100,0.1)"
                                        return (
                                            <div key={j} style={{ flex: 1, padding: "6px 4px", background: bg, borderRadius: 6, textAlign: "center" }}>
                                                <div style={{ color: "#888", fontSize: 8, fontFamily: F }}>{s.period || `Q${4 - j}`}</div>
                                                <div style={{ color, fontSize: 12, fontWeight: 800, fontFamily: F }}>{sp > 0 ? "+" : ""}{sp}%</div>
                                                {s.actual != null && (
                                                    <div style={{ color: "#555", fontSize: 8, fontFamily: F }}>
                                                        ${s.actual} / ${s.estimate}
                                                    </div>
                                                )}
                                            </div>
                                        )
                                    })}
                                </div>
                            </div>
                        )
                    })}
                    {withSurprises.length > SURPRISE_DEFAULT_COUNT && (
                        <button
                            onClick={() => setShowAllSurprises((v) => !v)}
                            style={toggleButton}
                        >
                            {showAllSurprises ? "접기" : `더보기 (+${withSurprises.length - SURPRISE_DEFAULT_COUNT})`}
                        </button>
                    )}
                </div>
            )}

            {upcoming.length === 0 && withSurprises.length === 0 && (
                <div style={{ padding: 30, textAlign: "center" }}>
                    <span style={{ color: "#555", fontSize: 13, fontFamily: F }}>미장 실적 데이터 없음</span>
                </div>
            )}
        </div>
    )
}

USEarningsCalendar.defaultProps = { dataUrl: DATA_URL }
addPropertyControls(USEarningsCalendar, {
    dataUrl: { type: ControlType.String, title: "JSON URL", defaultValue: DATA_URL },
})

const card: React.CSSProperties = {
    width: "100%", background: "#0A0A0A", borderRadius: 16,
    border: "1px solid #222", overflow: "hidden",
    display: "flex", flexDirection: "column", fontFamily: F,
}
const header: React.CSSProperties = {
    padding: "14px 16px", borderBottom: "1px solid #222",
    display: "flex", justifyContent: "space-between", alignItems: "center",
}
const badge: React.CSSProperties = {
    background: "#1A2A00", color: "#B5FF19", fontSize: 10,
    fontWeight: 700, padding: "3px 8px", borderRadius: 4, fontFamily: F,
}
const section: React.CSSProperties = { padding: "10px 16px" }
const sectionLabel: React.CSSProperties = {
    color: "#666", fontSize: 10, fontWeight: 600, letterSpacing: 1,
    textTransform: "uppercase" as const, display: "block", marginBottom: 8, fontFamily: F,
}
const row: React.CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "10px 0", borderBottom: "1px solid #1A1A1A",
}
const dateChip: React.CSSProperties = {
    background: "#1A1A2E", color: "#A78BFA", fontSize: 10, fontWeight: 700,
    padding: "4px 8px", borderRadius: 6, fontFamily: F, whiteSpace: "nowrap",
}
const toggleButton: React.CSSProperties = {
    marginTop: 8,
    display: "block",
    marginLeft: "auto",
    marginRight: "auto",
    padding: "8px 10px",
    borderRadius: 8,
    border: "1px solid #2A2A2A",
    background: "#111",
    color: "#B5FF19",
    fontSize: 11,
    fontWeight: 700,
    fontFamily: F,
    cursor: "pointer",
}
