import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"
import { fetchPortfolioJson } from "./fetchPortfolioJson"

interface Props {
    dataUrl: string
}

export default function SectorHeat(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [expanded, setExpanded] = useState<string | null>(null)
    const [view, setView] = useState<"hot" | "cold" | "all" | "rotation">("hot")

    useEffect(() => {
        if (!dataUrl) return
        fetchPortfolioJson(dataUrl).then(setData).catch(console.error)
    }, [dataUrl])

    const font = "'Pretendard', -apple-system, sans-serif"
    const sectors: any[] = data?.sectors || []
    const rotation: any = data?.sector_rotation || {}

    const filtered = (() => {
        if (view === "hot") return sectors.filter((s) => s.change_pct > 0).slice(0, 10)
        if (view === "cold") return [...sectors].sort((a, b) => a.change_pct - b.change_pct).filter((s) => s.change_pct < 0).slice(0, 10)
        return sectors.slice(0, 20)
    })()

    const heatColor = (heat: string) => {
        if (heat === "hot") return "#22C55E"
        if (heat === "warm") return "#86EFAC"
        if (heat === "cool") return "#FCA5A5"
        if (heat === "cold") return "#EF4444"
        return "#888"
    }

    const heatBg = (heat: string) => {
        if (heat === "hot") return "rgba(34,197,94,0.12)"
        if (heat === "warm") return "rgba(134,239,172,0.08)"
        if (heat === "cool") return "rgba(252,165,165,0.08)"
        if (heat === "cold") return "rgba(239,68,68,0.12)"
        return "rgba(136,136,136,0.06)"
    }

    const barWidth = (pct: number) => {
        const maxPct = Math.max(...sectors.map((s) => Math.abs(s.change_pct || 0)), 3)
        return `${Math.min(Math.abs(pct) / maxPct * 100, 100)}%`
    }

    const chgColor = (v: number) => v > 0 ? "#22C55E" : v < 0 ? "#EF4444" : "#888"

    if (!data) {
        return (
            <div style={{ ...card, minHeight: 160, alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: "#999", fontSize: 14, fontFamily: font }}>섹터 로딩 중...</span>
            </div>
        )
    }

    const hotCount = sectors.filter((s) => s.change_pct > 0).length
    const coldCount = sectors.filter((s) => s.change_pct < 0).length

    return (
        <div style={card}>
            {/* 헤더 */}
            <div style={header}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ color: "#fff", fontSize: 15, fontWeight: 700, fontFamily: font }}>
                        섹터 히트맵
                    </span>
                    <span style={{ color: "#22C55E", fontSize: 12, fontFamily: font }}>
                        상승 {hotCount}
                    </span>
                    <span style={{ color: "#EF4444", fontSize: 12, fontFamily: font }}>
                        하락 {coldCount}
                    </span>
                </div>
                <div style={{ display: "flex", gap: 4 }}>
                    {(["hot", "cold", "all", "rotation"] as const).map((v) => (
                        <button
                            key={v}
                            onClick={() => setView(v)}
                            style={{
                                padding: "4px 10px", borderRadius: 6, border: "none",
                                background: view === v ? "#B5FF19" : "#222",
                                color: view === v ? "#000" : "#888",
                                fontSize: 11, fontWeight: 600, fontFamily: font, cursor: "pointer",
                            }}
                        >
                            {v === "hot" ? "상승" : v === "cold" ? "하락" : v === "all" ? "전체" : "전략"}
                        </button>
                    ))}
                </div>
            </div>

            {/* 로테이션 전략 뷰 */}
            {view === "rotation" && rotation.cycle && (
                <div style={{ padding: "12px 16px" }}>
                    <div style={{ background: "#1A1A2E", borderRadius: 10, padding: "14px 16px", marginBottom: 12 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                            <span style={{ color: "#A78BFA", fontSize: 14, fontWeight: 800, fontFamily: font }}>
                                {rotation.cycle_label}
                            </span>
                        </div>
                        <div style={{ color: "#aaa", fontSize: 12, fontFamily: font, lineHeight: "1.6" }}>
                            {rotation.cycle_desc}
                        </div>
                    </div>

                    {rotation.recommended_sectors?.length > 0 && (
                        <div style={{ marginBottom: 12 }}>
                            <div style={{ color: "#22C55E", fontSize: 12, fontWeight: 700, fontFamily: font, marginBottom: 8 }}>
                                추천 섹터
                            </div>
                            {rotation.recommended_sectors.map((s: any, i: number) => (
                                <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid #1a1a1a" }}>
                                    <div>
                                        <span style={{ color: "#ddd", fontSize: 13, fontFamily: font }}>{s.name}</span>
                                        <div style={{ color: "#666", fontSize: 10, fontFamily: font, marginTop: 2 }}>{s.reason}</div>
                                    </div>
                                    <span style={{ color: chgColor(s.change_pct || 0), fontSize: 13, fontWeight: 600, fontFamily: font }}>
                                        {(s.change_pct || 0) >= 0 ? "+" : ""}{(s.change_pct || 0).toFixed(2)}%
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}

                    {rotation.avoid_sectors?.length > 0 && (
                        <div>
                            <div style={{ color: "#EF4444", fontSize: 12, fontWeight: 700, fontFamily: font, marginBottom: 8 }}>
                                회피 섹터
                            </div>
                            {rotation.avoid_sectors.map((s: any, i: number) => (
                                <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid #1a1a1a" }}>
                                    <div>
                                        <span style={{ color: "#888", fontSize: 13, fontFamily: font }}>{s.name}</span>
                                        <div style={{ color: "#555", fontSize: 10, fontFamily: font, marginTop: 2 }}>{s.reason}</div>
                                    </div>
                                    <span style={{ color: chgColor(s.change_pct || 0), fontSize: 13, fontWeight: 600, fontFamily: font }}>
                                        {(s.change_pct || 0) >= 0 ? "+" : ""}{(s.change_pct || 0).toFixed(2)}%
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* 섹터 리스트 */}
            {view !== "rotation" && <div style={{ maxHeight: 500, overflowY: "auto" }}>
                {filtered.map((s: any, i: number) => {
                    const isExpanded = expanded === s.name
                    return (
                        <div key={i}>
                            <div
                                onClick={() => setExpanded(isExpanded ? null : s.name)}
                                style={{
                                    ...sectorRow,
                                    background: isExpanded ? "#1A1A1A" : "transparent",
                                    cursor: "pointer",
                                }}
                            >
                                <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1 }}>
                                    <span style={{
                                        width: 6, height: 6, borderRadius: 3,
                                        background: heatColor(s.heat),
                                    }} />
                                    <span style={{ color: "#ddd", fontSize: 13, fontWeight: 500, fontFamily: font, minWidth: 100 }}>
                                        {s.name}
                                    </span>
                                    <div style={{ flex: 1, height: 4, background: "#1A1A1A", borderRadius: 2, position: "relative", overflow: "hidden" }}>
                                        <div style={{
                                            position: "absolute",
                                            [s.change_pct >= 0 ? "left" : "right"]: 0,
                                            top: 0, height: "100%",
                                            width: barWidth(s.change_pct),
                                            background: heatColor(s.heat),
                                            borderRadius: 2,
                                        }} />
                                    </div>
                                </div>
                                <span style={{ color: chgColor(s.change_pct), fontSize: 13, fontWeight: 700, fontFamily: font, minWidth: 60, textAlign: "right" }}>
                                    {s.change_pct >= 0 ? "+" : ""}{s.change_pct.toFixed(2)}%
                                </span>
                                <span style={{ color: "#444", fontSize: 12, marginLeft: 8, transition: "transform 0.2s", transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)" }}>›</span>
                            </div>

                            {/* 대표 종목 */}
                            {isExpanded && s.top_stocks && s.top_stocks.length > 0 && (
                                <div style={{ padding: "8px 16px 12px 32px", background: "#0D0D0D" }}>
                                    <div style={{ color: "#666", fontSize: 10, fontFamily: font, marginBottom: 6 }}>
                                        대표 종목
                                    </div>
                                    {s.top_stocks.map((st: any, j: number) => (
                                        <div key={j} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
                                            <span style={{ color: "#aaa", fontSize: 12, fontFamily: font }}>{st.name}</span>
                                            <div style={{ display: "flex", gap: 12 }}>
                                                <span style={{ color: "#888", fontSize: 12, fontFamily: font }}>
                                                    {st.price?.toLocaleString() || "—"}원
                                                </span>
                                                <span style={{ color: chgColor(st.change_pct || 0), fontSize: 12, fontWeight: 600, fontFamily: font }}>
                                                    {(st.change_pct || 0) >= 0 ? "+" : ""}{(st.change_pct || 0).toFixed(2)}%
                                                </span>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )
                })}
            </div>}
        </div>
    )
}

SectorHeat.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
}

addPropertyControls(SectorHeat, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    },
})

const card: React.CSSProperties = {
    width: "100%",
    background: "#111",
    borderRadius: 16,
    border: "1px solid #222",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    fontFamily: "'Pretendard', -apple-system, sans-serif",
}

const header: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "14px 16px",
    borderBottom: "1px solid #222",
}

const sectorRow: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    padding: "10px 16px",
    borderBottom: "1px solid #1a1a1a",
    transition: "background 0.15s",
}
