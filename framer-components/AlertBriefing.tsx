import { useState, useEffect } from "react"
import { addPropertyControls, ControlType } from "framer"

interface Props {
    dataUrl: string
}

const TONE_STYLES: Record<string, { bg: string; border: string; icon: string; label: string }> = {
    urgent: { bg: "rgba(239,68,68,0.08)", border: "#EF4444", icon: "🔴", label: "긴급" },
    cautious: { bg: "rgba(234,179,8,0.08)", border: "#EAB308", icon: "🟡", label: "주의" },
    defensive: { bg: "rgba(234,179,8,0.06)", border: "#F59E0B", icon: "🛡️", label: "방어" },
    positive: { bg: "rgba(34,197,94,0.06)", border: "#22C55E", icon: "🟢", label: "양호" },
    neutral: { bg: "rgba(136,136,136,0.06)", border: "#555", icon: "⚪", label: "중립" },
}

const LEVEL_STYLES: Record<string, { bg: string; color: string; label: string }> = {
    CRITICAL: { bg: "rgba(239,68,68,0.15)", color: "#EF4444", label: "긴급" },
    WARNING: { bg: "rgba(234,179,8,0.15)", color: "#EAB308", label: "주의" },
    INFO: { bg: "rgba(96,165,250,0.12)", color: "#60A5FA", label: "참고" },
}

const CAT_LABELS: Record<string, string> = {
    macro: "매크로",
    holding: "보유종목",
    earnings: "실적",
    opportunity: "기회",
    news: "뉴스",
    event: "이벤트",
    strategy: "전략",
}

export default function AlertBriefing(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [expanded, setExpanded] = useState(false)
    const [tab, setTab] = useState<"alerts" | "events">("alerts")

    useEffect(() => {
        if (!dataUrl) return
        fetch(dataUrl)
            .then((r) => r.text())
            .then((txt) => {
                const clean = txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")
                setData(JSON.parse(clean))
            })
            .catch(() => {})
    }, [dataUrl])

    if (!data) {
        return (
            <div style={styles.container}>
                <div style={styles.loading}>VERITY 브리핑 준비 중...</div>
            </div>
        )
    }

    const briefing = data.briefing || {}
    const events = data.global_events || []
    const tone = TONE_STYLES[briefing.tone] || TONE_STYLES.neutral
    const alerts: any[] = briefing.alerts || []
    const actions: string[] = briefing.action_items || []
    const counts = briefing.alert_counts || {}
    const updatedAt = data.updated_at || ""

    const upcomingEvents = events.filter((e: any) => (e.d_day ?? 99) <= 7)

    return (
        <div style={styles.container}>
            {/* 비서의 한마디 — 최상단 헤드라인 */}
            <div
                style={{
                    ...styles.headlineBanner,
                    background: tone.bg,
                    borderLeft: `3px solid ${tone.border}`,
                }}
                onClick={() => setExpanded(!expanded)}
            >
                <div style={styles.headlineRow}>
                    <span style={{ fontSize: 18 }}>{tone.icon}</span>
                    <div style={styles.headlineText}>
                        <div style={styles.headlineLabel}>
                            VERITY · {tone.label}
                        </div>
                        <div style={styles.headlineMessage}>
                            {briefing.headline || "분석 대기 중"}
                        </div>
                    </div>
                    <div style={styles.expandArrow}>{expanded ? "▲" : "▼"}</div>
                </div>

                {/* 요약 배지 */}
                <div style={styles.badgeRow}>
                    {counts.critical > 0 && (
                        <span style={{ ...styles.badge, background: LEVEL_STYLES.CRITICAL.bg, color: LEVEL_STYLES.CRITICAL.color }}>
                            긴급 {counts.critical}
                        </span>
                    )}
                    {counts.warning > 0 && (
                        <span style={{ ...styles.badge, background: LEVEL_STYLES.WARNING.bg, color: LEVEL_STYLES.WARNING.color }}>
                            주의 {counts.warning}
                        </span>
                    )}
                    {counts.info > 0 && (
                        <span style={{ ...styles.badge, background: LEVEL_STYLES.INFO.bg, color: LEVEL_STYLES.INFO.color }}>
                            참고 {counts.info}
                        </span>
                    )}
                    {upcomingEvents.length > 0 && (
                        <span style={{ ...styles.badge, background: "rgba(168,85,247,0.12)", color: "#A855F7" }}>
                            이벤트 {upcomingEvents.length}
                        </span>
                    )}
                    <span style={styles.time}>
                        {updatedAt ? new Date(updatedAt).toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : ""}
                    </span>
                </div>

                {/* 지금 해야 할 것 */}
                {actions.length > 0 && (
                    <div style={styles.actionBox}>
                        <div style={styles.actionTitle}>지금 해야 할 것</div>
                        {actions.map((a, i) => (
                            <div key={i} style={styles.actionItem}>→ {a}</div>
                        ))}
                    </div>
                )}
            </div>

            {/* 펼침 영역: 상세 알림 + 이벤트 */}
            {expanded && (
                <div style={styles.expandedArea}>
                    {/* 탭 전환 */}
                    <div style={styles.tabRow}>
                        <button
                            style={tab === "alerts" ? styles.tabActive : styles.tab}
                            onClick={() => setTab("alerts")}
                        >
                            경고 ({alerts.length})
                        </button>
                        <button
                            style={tab === "events" ? styles.tabActive : styles.tab}
                            onClick={() => setTab("events")}
                        >
                            이벤트 ({upcomingEvents.length})
                        </button>
                    </div>

                    {tab === "alerts" && (
                        <div style={styles.alertList}>
                            {alerts.length === 0 && (
                                <div style={styles.emptyText}>활성 경고 없음 ✅</div>
                            )}
                            {alerts.map((a: any, i: number) => {
                                const lvl = LEVEL_STYLES[a.level] || LEVEL_STYLES.INFO
                                const cat = CAT_LABELS[a.category] || a.category
                                return (
                                    <div key={i} style={{ ...styles.alertCard, borderLeft: `3px solid ${lvl.color}` }}>
                                        <div style={styles.alertHeader}>
                                            <span style={{ ...styles.alertBadge, background: lvl.bg, color: lvl.color }}>
                                                {lvl.label}
                                            </span>
                                            <span style={styles.alertCat}>{cat}</span>
                                        </div>
                                        <div style={styles.alertMsg}>{a.message}</div>
                                        {a.action && (
                                            <div style={styles.alertAction}>→ {a.action}</div>
                                        )}
                                    </div>
                                )
                            })}
                        </div>
                    )}

                    {tab === "events" && (
                        <div style={styles.alertList}>
                            {upcomingEvents.length === 0 && (
                                <div style={styles.emptyText}>7일 내 주요 이벤트 없음</div>
                            )}
                            {upcomingEvents.map((e: any, i: number) => {
                                const sev = e.severity === "high" ? LEVEL_STYLES.CRITICAL : e.severity === "medium" ? LEVEL_STYLES.WARNING : LEVEL_STYLES.INFO
                                return (
                                    <div key={i} style={{ ...styles.alertCard, borderLeft: `3px solid ${sev.color}` }}>
                                        <div style={styles.alertHeader}>
                                            <span style={{ ...styles.alertBadge, background: sev.bg, color: sev.color }}>
                                                D-{e.d_day ?? "?"}
                                            </span>
                                            <span style={styles.alertCat}>
                                                {e.date ? new Date(e.date).toLocaleDateString("ko-KR", { month: "short", day: "numeric" }) : ""}
                                            </span>
                                        </div>
                                        <div style={styles.alertMsg}>{e.name}</div>
                                        <div style={styles.eventImpact}>{e.impact}</div>
                                        {e.action && (
                                            <div style={styles.alertAction}>→ {e.action}</div>
                                        )}
                                        {e.impact_area && (
                                            <div style={styles.impactTags}>
                                                {e.impact_area.map((tag: string, j: number) => (
                                                    <span key={j} style={styles.impactTag}>{tag}</span>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )
                            })}
                        </div>
                    )}

                    {/* 포트폴리오 상태 한줄 */}
                    {briefing.portfolio_status && (
                        <div style={styles.portfolioStatus}>{briefing.portfolio_status}</div>
                    )}
                </div>
            )}
        </div>
    )
}

addPropertyControls(AlertBriefing, {
    dataUrl: {
        type: ControlType.String,
        title: "Data URL",
        defaultValue:
            "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    },
})

const styles: Record<string, React.CSSProperties> = {
    container: {
        width: "100%",
        fontFamily: "'Inter', 'Pretendard', -apple-system, sans-serif",
    },
    loading: {
        padding: "16px 20px",
        color: "#666",
        fontSize: 13,
        background: "rgba(255,255,255,0.02)",
        borderRadius: 12,
        border: "1px solid rgba(255,255,255,0.06)",
    },
    headlineBanner: {
        padding: "16px 20px",
        borderRadius: 12,
        cursor: "pointer",
        transition: "all 0.2s",
    },
    headlineRow: {
        display: "flex",
        alignItems: "flex-start",
        gap: 12,
    },
    headlineText: {
        flex: 1,
    },
    headlineLabel: {
        fontSize: 11,
        color: "#888",
        fontWeight: 600,
        letterSpacing: "0.05em",
        textTransform: "uppercase" as const,
        marginBottom: 4,
    },
    headlineMessage: {
        fontSize: 15,
        fontWeight: 600,
        color: "#fff",
        lineHeight: "1.5",
    },
    expandArrow: {
        color: "#666",
        fontSize: 11,
        marginTop: 4,
    },
    badgeRow: {
        display: "flex",
        gap: 6,
        marginTop: 10,
        flexWrap: "wrap" as const,
        alignItems: "center",
    },
    badge: {
        padding: "3px 8px",
        borderRadius: 6,
        fontSize: 11,
        fontWeight: 600,
    },
    time: {
        fontSize: 10,
        color: "#555",
        marginLeft: "auto",
    },
    actionBox: {
        marginTop: 12,
        padding: "10px 12px",
        background: "rgba(255,255,255,0.03)",
        borderRadius: 8,
        border: "1px solid rgba(255,255,255,0.06)",
    },
    actionTitle: {
        fontSize: 11,
        fontWeight: 700,
        color: "#FFD700",
        marginBottom: 6,
        letterSpacing: "0.03em",
    },
    actionItem: {
        fontSize: 13,
        color: "#ccc",
        lineHeight: "1.6",
    },
    expandedArea: {
        marginTop: 8,
        borderRadius: 12,
        background: "rgba(255,255,255,0.02)",
        border: "1px solid rgba(255,255,255,0.06)",
        overflow: "hidden",
    },
    tabRow: {
        display: "flex",
        borderBottom: "1px solid rgba(255,255,255,0.06)",
    },
    tab: {
        flex: 1,
        padding: "10px",
        background: "none",
        border: "none",
        color: "#666",
        fontSize: 12,
        fontWeight: 600,
        cursor: "pointer",
    },
    tabActive: {
        flex: 1,
        padding: "10px",
        background: "none",
        border: "none",
        borderBottom: "2px solid #fff",
        color: "#fff",
        fontSize: 12,
        fontWeight: 600,
        cursor: "pointer",
    },
    alertList: {
        padding: "8px 12px",
        display: "flex",
        flexDirection: "column" as const,
        gap: 8,
    },
    emptyText: {
        textAlign: "center" as const,
        color: "#666",
        fontSize: 13,
        padding: "20px 0",
    },
    alertCard: {
        padding: "10px 12px",
        borderRadius: 8,
        background: "rgba(255,255,255,0.02)",
    },
    alertHeader: {
        display: "flex",
        alignItems: "center",
        gap: 8,
        marginBottom: 4,
    },
    alertBadge: {
        padding: "2px 6px",
        borderRadius: 4,
        fontSize: 10,
        fontWeight: 700,
    },
    alertCat: {
        fontSize: 10,
        color: "#666",
    },
    alertMsg: {
        fontSize: 13,
        color: "#ddd",
        lineHeight: "1.5",
    },
    alertAction: {
        fontSize: 12,
        color: "#FFD700",
        marginTop: 4,
    },
    eventImpact: {
        fontSize: 12,
        color: "#999",
        marginTop: 4,
        lineHeight: "1.4",
    },
    impactTags: {
        display: "flex",
        gap: 4,
        marginTop: 6,
    },
    impactTag: {
        padding: "2px 6px",
        borderRadius: 4,
        background: "rgba(168,85,247,0.1)",
        color: "#A855F7",
        fontSize: 10,
        fontWeight: 600,
    },
    portfolioStatus: {
        padding: "8px 12px",
        borderTop: "1px solid rgba(255,255,255,0.06)",
        fontSize: 11,
        color: "#666",
        textAlign: "center" as const,
    },
}
