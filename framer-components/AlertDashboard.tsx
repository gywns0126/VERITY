import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

interface Props {
    dataUrl: string
    maxAlerts: number
}

type AlertLevel = "CRITICAL" | "WARNING" | "INFO"
type FilterType = "all" | AlertLevel

const LEVEL_META: Record<AlertLevel, { color: string; bg: string; icon: string; label: string }> = {
    CRITICAL: { color: "#FF4D4D", bg: "#FF4D4D15", icon: "🚨", label: "긴급" },
    WARNING: { color: "#FFD600", bg: "#FFD60015", icon: "⚠️", label: "주의" },
    INFO: { color: "#60A5FA", bg: "#60A5FA15", icon: "ℹ️", label: "참고" },
}

export default function AlertDashboard(props: Props) {
    const { dataUrl, maxAlerts } = props
    const [data, setData] = useState<any>(null)
    const [filter, setFilter] = useState<FilterType>("all")

    useEffect(() => {
        if (!dataUrl) return
        fetch(dataUrl)
            .then((r) => r.text())
            .then((t) =>
                JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null"))
            )
            .then(setData)
            .catch(console.error)
    }, [dataUrl])

    const alerts: any[] = (data?.alerts || []).slice(0, maxAlerts)
    const filtered = filter === "all" ? alerts : alerts.filter((a: any) => a.level === filter)

    const counts = { CRITICAL: 0, WARNING: 0, INFO: 0 }
    alerts.forEach((a: any) => {
        if (a.level in counts) counts[a.level as AlertLevel]++
    })

    return (
        <div style={container}>
            <div style={headerRow}>
                <span style={titleStyle}>알림 센터</span>
                <span style={{ color: "#555", fontSize: 10 }}>{alerts.length}건</span>
            </div>

            <div style={filterRow}>
                <FilterChip label="전체" active={filter === "all"} count={alerts.length} onClick={() => setFilter("all")} color="#fff" />
                <FilterChip label="긴급" active={filter === "CRITICAL"} count={counts.CRITICAL} onClick={() => setFilter("CRITICAL")} color="#FF4D4D" />
                <FilterChip label="주의" active={filter === "WARNING"} count={counts.WARNING} onClick={() => setFilter("WARNING")} color="#FFD600" />
                <FilterChip label="참고" active={filter === "INFO"} count={counts.INFO} onClick={() => setFilter("INFO")} color="#60A5FA" />
            </div>

            <div style={listWrap}>
                {filtered.length === 0 && (
                    <div style={{ color: "#555", fontSize: 12, textAlign: "center", padding: 30 }}>
                        {alerts.length === 0 ? "알림이 없습니다." : "해당 레벨의 알림이 없습니다."}
                    </div>
                )}
                {filtered.map((a: any, i: number) => {
                    const meta = LEVEL_META[a.level as AlertLevel] || LEVEL_META.INFO
                    return (
                        <div key={i} style={{ ...alertCard, borderLeft: `3px solid ${meta.color}`, background: meta.bg }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <span style={{ fontSize: 11, fontWeight: 700, color: meta.color }}>
                                    {meta.icon} {meta.label}
                                </span>
                                {a.category && (
                                    <span style={categoryBadge}>{a.category}</span>
                                )}
                            </div>
                            <div style={{ color: "#ddd", fontSize: 12, lineHeight: 1.5, marginTop: 4 }}>
                                {a.message}
                            </div>
                            {a.action && (
                                <div style={{ color: "#888", fontSize: 10, marginTop: 4, lineHeight: 1.4 }}>
                                    → {a.action}
                                </div>
                            )}
                        </div>
                    )
                })}
            </div>
        </div>
    )
}

function FilterChip({ label, active, count, onClick, color }: {
    label: string; active: boolean; count: number; onClick: () => void; color: string
}) {
    return (
        <span
            onClick={onClick}
            style={{
                padding: "4px 10px",
                borderRadius: 20,
                fontSize: 11,
                fontWeight: 600,
                cursor: "pointer",
                border: active ? `1px solid ${color}` : "1px solid #333",
                background: active ? `${color}15` : "transparent",
                color: active ? color : "#666",
                fontFamily: "'Inter', 'Pretendard', sans-serif",
            }}
        >
            {label} {count > 0 ? count : ""}
        </span>
    )
}

const DATA_URL = "https://kim-hyojun.github.io/stock-analysis/data/portfolio.json"

AlertDashboard.defaultProps = {
    dataUrl: DATA_URL,
    maxAlerts: 15,
}

addPropertyControls(AlertDashboard, {
    dataUrl: {
        type: ControlType.String,
        title: "데이터 URL",
        defaultValue: DATA_URL,
    },
    maxAlerts: {
        type: ControlType.Number,
        title: "최대 알림 수",
        defaultValue: 15,
        min: 5,
        max: 30,
        step: 1,
    },
})

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"

const container: React.CSSProperties = {
    width: "100%",
    background: "#111",
    border: "1px solid #222",
    borderRadius: 16,
    padding: 16,
    fontFamily: font,
    boxSizing: "border-box",
    display: "flex",
    flexDirection: "column",
    gap: 12,
}

const headerRow: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
}

const titleStyle: React.CSSProperties = {
    color: "#fff",
    fontSize: 14,
    fontWeight: 700,
    fontFamily: font,
}

const filterRow: React.CSSProperties = {
    display: "flex",
    gap: 6,
    flexWrap: "wrap",
}

const listWrap: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 8,
}

const alertCard: React.CSSProperties = {
    padding: "10px 12px",
    borderRadius: 10,
    display: "flex",
    flexDirection: "column",
    gap: 2,
}

const categoryBadge: React.CSSProperties = {
    fontSize: 9,
    color: "#555",
    background: "#1a1a1a",
    padding: "2px 6px",
    borderRadius: 4,
    fontFamily: font,
}
