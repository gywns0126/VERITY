import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"

function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    return `${u}${u.includes("?") ? "&" : "?"}_=${Date.now()}`
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

const GICS_ICONS: Record<string, string> = {
    "기술": "💻", "커뮤니케이션": "📡", "경기소비재": "🛍️", "필수소비재": "🛒",
    "금융": "🏦", "헬스케어": "💊", "산업재": "🏭", "에너지": "⛽",
    "소재": "⚗️", "부동산": "🏠", "유틸리티": "⚡",
}

function heatColor(pct: number): string {
    if (pct > 2) return "#22C55E"
    if (pct > 1) return "#4ADE80"
    if (pct > 0.3) return "#86EFAC"
    if (pct > -0.3) return "#666"
    if (pct > -1) return "#FCA5A5"
    if (pct > -2) return "#F87171"
    return "#EF4444"
}

function heatBg(pct: number): string {
    if (pct > 2) return "rgba(34,197,94,0.15)"
    if (pct > 1) return "rgba(34,197,94,0.10)"
    if (pct > 0.3) return "rgba(34,197,94,0.05)"
    if (pct > -0.3) return "rgba(100,100,100,0.1)"
    if (pct > -1) return "rgba(239,68,68,0.05)"
    if (pct > -2) return "rgba(239,68,68,0.10)"
    return "rgba(239,68,68,0.15)"
}

export default function USSectorMap(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [expanded, setExpanded] = useState<string | null>(null)

    useEffect(() => {
        if (!dataUrl) return
        fetchJson(dataUrl).then(setData).catch(console.error)
    }, [dataUrl])

    const allSectors: any[] = (data?.sectors || []).filter((s: any) => (s.market || "").toUpperCase() === "US")
    const sectorTrends = data?.sector_trends || {}

    const hotCount = allSectors.filter((s) => s.change_pct > 0.3).length
    const coldCount = allSectors.filter((s) => s.change_pct < -0.3).length

    if (!data) {
        return (
            <div style={{ ...card, minHeight: 140, alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: "#666", fontSize: 13, fontFamily: F }}>섹터맵 로딩 중...</span>
            </div>
        )
    }

    return (
        <div style={card}>
            <div style={header}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 16, fontWeight: 800, color: "#fff", fontFamily: F }}>🗺️ S&P Sector Map</span>
                    <span style={{ fontSize: 10, color: "#555", fontFamily: F }}>GICS 11 Sectors</span>
                </div>
                <div style={{ display: "flex", gap: 6 }}>
                    <span style={{ fontSize: 10, fontWeight: 700, fontFamily: F, color: "#22C55E" }}>🔥 {hotCount}</span>
                    <span style={{ fontSize: 10, fontWeight: 700, fontFamily: F, color: "#EF4444" }}>❄️ {coldCount}</span>
                </div>
            </div>

            <div style={{ padding: "6px 12px 14px" }}>
                <div style={{
                    display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(110px, 1fr))",
                    gap: 6,
                }}>
                    {allSectors.map((sec, i) => {
                        const pct = sec.change_pct || 0
                        const isExpanded = expanded === sec.name
                        const topStocks: any[] = sec.top_stocks || []
                        return (
                            <div key={i} onClick={() => setExpanded(isExpanded ? null : sec.name)} style={{
                                background: heatBg(pct), borderRadius: 10,
                                border: isExpanded ? "1px solid #444" : "1px solid #1A1A1A",
                                padding: "10px 8px", cursor: "pointer",
                                gridColumn: isExpanded ? "1 / -1" : "auto",
                                transition: "all 0.2s",
                            }}>
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                                        <span style={{ fontSize: 14 }}>{GICS_ICONS[sec.name] || "📊"}</span>
                                        <span style={{ color: "#ccc", fontSize: 11, fontWeight: 700, fontFamily: F }}>{sec.name}</span>
                                    </div>
                                    <span style={{ color: heatColor(pct), fontSize: 13, fontWeight: 800, fontFamily: F }}>
                                        {pct > 0 ? "+" : ""}{pct.toFixed(1)}%
                                    </span>
                                </div>
                                {sec.name_en && (
                                    <div style={{ color: "#555", fontSize: 8, fontFamily: F, marginTop: 2 }}>{sec.name_en}</div>
                                )}
                                <StrengthBar pct={pct} />

                                {isExpanded && topStocks.length > 0 && (
                                    <div style={{ marginTop: 8, borderTop: "1px solid #333", paddingTop: 8 }}>
                                        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                                            {topStocks.map((s: any, j: number) => {
                                                const sc = (s.change_pct || 0) >= 0 ? "#22C55E" : "#EF4444"
                                                return (
                                                    <div key={j} style={{
                                                        background: "#111", borderRadius: 6, padding: "5px 8px",
                                                        border: "1px solid #222",
                                                    }}>
                                                        <span style={{ color: "#fff", fontSize: 10, fontWeight: 600, fontFamily: F }}>{s.name}</span>
                                                        <span style={{ color: "#555", fontSize: 8, marginLeft: 4, fontFamily: F }}>{s.ticker}</span>
                                                        <span style={{ color: sc, fontSize: 10, fontWeight: 700, marginLeft: 6, fontFamily: F }}>
                                                            {(s.change_pct || 0) > 0 ? "+" : ""}{(s.change_pct || 0).toFixed(1)}%
                                                        </span>
                                                    </div>
                                                )
                                            })}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )
                    })}
                </div>

                {Object.keys(sectorTrends).length > 0 && (
                    <TrendSummary trends={sectorTrends} />
                )}
            </div>
        </div>
    )
}

function StrengthBar({ pct }: { pct: number }) {
    const norm = Math.min(Math.abs(pct) / 3 * 100, 100)
    const color = pct >= 0 ? "#22C55E" : "#EF4444"
    return (
        <div style={{ height: 3, background: "#1A1A1A", borderRadius: 2, marginTop: 5 }}>
            <div style={{ height: "100%", width: `${norm}%`, background: color, borderRadius: 2 }} />
        </div>
    )
}

function TrendSummary({ trends }: { trends: any }) {
    const [period, setPeriod] = useState<"1m" | "3m" | "6m" | "1y">("1m")
    const current = trends[period]
    if (!current) return null

    return (
        <div style={{ marginTop: 12, borderTop: "1px solid #222", paddingTop: 10 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                <span style={{ color: "#888", fontSize: 10, fontWeight: 600, fontFamily: F }}>섹터 로테이션 추이</span>
                <div style={{ display: "flex", gap: 3 }}>
                    {(["1m", "3m", "6m", "1y"] as const).map((p) => (
                        <button key={p} onClick={() => setPeriod(p)} style={{
                            background: period === p ? "#B5FF19" : "#1A1A1A", color: period === p ? "#000" : "#666",
                            border: "none", padding: "3px 8px", borderRadius: 4, fontSize: 9, fontWeight: 700,
                            fontFamily: F, cursor: "pointer",
                        }}>{p}</button>
                    ))}
                </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
                {current.top && current.top.length > 0 && (
                    <div style={{ flex: 1 }}>
                        <div style={{ color: "#22C55E", fontSize: 9, fontWeight: 700, fontFamily: F, marginBottom: 4 }}>🔥 TOP</div>
                        {current.top.slice(0, 3).map((s: any, i: number) => (
                            <div key={i} style={{ color: "#ccc", fontSize: 10, fontFamily: F, lineHeight: 1.6 }}>
                                {s.name} <span style={{ color: "#22C55E" }}>{s.change_pct > 0 ? "+" : ""}{s.change_pct?.toFixed(1)}%</span>
                            </div>
                        ))}
                    </div>
                )}
                {current.bottom && current.bottom.length > 0 && (
                    <div style={{ flex: 1 }}>
                        <div style={{ color: "#EF4444", fontSize: 9, fontWeight: 700, fontFamily: F, marginBottom: 4 }}>❄️ BOTTOM</div>
                        {current.bottom.slice(0, 3).map((s: any, i: number) => (
                            <div key={i} style={{ color: "#ccc", fontSize: 10, fontFamily: F, lineHeight: 1.6 }}>
                                {s.name} <span style={{ color: "#EF4444" }}>{s.change_pct > 0 ? "+" : ""}{s.change_pct?.toFixed(1)}%</span>
                            </div>
                        ))}
                    </div>
                )}
                {(current.rotation_in?.length > 0 || current.rotation_out?.length > 0) && (
                    <div style={{ flex: 1 }}>
                        <div style={{ color: "#A78BFA", fontSize: 9, fontWeight: 700, fontFamily: F, marginBottom: 4 }}>🔄 ROTATION</div>
                        {(current.rotation_in || []).slice(0, 2).map((s: string, i: number) => (
                            <div key={`in-${i}`} style={{ color: "#22C55E", fontSize: 10, fontFamily: F, lineHeight: 1.6 }}>IN → {s}</div>
                        ))}
                        {(current.rotation_out || []).slice(0, 2).map((s: string, i: number) => (
                            <div key={`out-${i}`} style={{ color: "#EF4444", fontSize: 10, fontFamily: F, lineHeight: 1.6 }}>OUT ← {s}</div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    )
}

USSectorMap.defaultProps = { dataUrl: DATA_URL }
addPropertyControls(USSectorMap, {
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
