import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"

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

function RatingBar({ buy, hold, sell }: { buy: number; hold: number; sell: number }) {
    const total = buy + hold + sell || 1
    const bPct = (buy / total) * 100
    const hPct = (hold / total) * 100
    return (
        <div style={{ display: "flex", height: 4, borderRadius: 2, overflow: "hidden", width: 80 }}>
            <div style={{ width: `${bPct}%`, background: "#22C55E" }} />
            <div style={{ width: `${hPct}%`, background: "#F59E0B" }} />
            <div style={{ flex: 1, background: "#EF4444" }} />
        </div>
    )
}

function UpsideArrow({ pct }: { pct: number }) {
    const abs = Math.abs(pct)
    const barW = Math.min(abs / 60 * 100, 100)
    const color = pct > 20 ? "#22C55E" : pct > 0 ? "#4ADE80" : pct > -10 ? "#F59E0B" : "#EF4444"
    return (
        <div style={{ display: "flex", alignItems: "center", gap: 4, width: 100 }}>
            <div style={{ flex: 1, height: 3, background: "#1A1A1A", borderRadius: 2, position: "relative" }}>
                <div style={{
                    height: "100%", width: `${barW}%`, background: color, borderRadius: 2,
                    position: "absolute", left: pct >= 0 ? "50%" : undefined, right: pct < 0 ? "50%" : undefined,
                }} />
                <div style={{ position: "absolute", left: "50%", top: -2, height: 8, width: 1, background: "#444" }} />
            </div>
            <span style={{ color, fontSize: 11, fontWeight: 800, fontFamily: F, minWidth: 38, textAlign: "right" }}>
                {pct > 0 ? "+" : ""}{pct.toFixed(0)}%
            </span>
        </div>
    )
}

export default function USAnalystView(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [sort, setSort] = useState<"upside" | "buy_ratio" | "name">("upside")

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    const allRecs: any[] = data?.recommendations || []
    const usRecs = allRecs.filter((r) => r.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(r.market || ""))

    const withConsensus = usRecs.filter((r) => {
        const c = r.analyst_consensus
        return c && (c.buy > 0 || c.hold > 0 || c.sell > 0)
    })

    const sorted = [...withConsensus].sort((a, b) => {
        if (sort === "upside") return (b.analyst_consensus?.upside_pct || 0) - (a.analyst_consensus?.upside_pct || 0)
        if (sort === "buy_ratio") {
            const ratioA = a.analyst_consensus.buy / ((a.analyst_consensus.buy + a.analyst_consensus.hold + a.analyst_consensus.sell) || 1)
            const ratioB = b.analyst_consensus.buy / ((b.analyst_consensus.buy + b.analyst_consensus.hold + b.analyst_consensus.sell) || 1)
            return ratioB - ratioA
        }
        return (a.name || "").localeCompare(b.name || "")
    })

    const strongBuys = withConsensus.filter((r) => {
        const c = r.analyst_consensus
        return c.buy > (c.hold || 0) + (c.sell || 0) && (c.upside_pct || 0) > 10
    }).length

    if (!data) {
        return (
            <div style={{ ...card, minHeight: 140, alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: "#666", fontSize: 13, fontFamily: F }}>컨센서스 로딩 중...</span>
            </div>
        )
    }

    return (
        <div style={card}>
            <div style={header}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 16, fontWeight: 800, color: "#fff", fontFamily: F }}>📊 Analyst Consensus</span>
                    {strongBuys > 0 && (
                        <span style={{ background: "#0D2A0D", color: "#22C55E", fontSize: 9, fontWeight: 700, padding: "3px 8px", borderRadius: 4, fontFamily: F }}>
                            Strong Buy {strongBuys}건
                        </span>
                    )}
                </div>
                <span style={{ color: "#555", fontSize: 10, fontFamily: F }}>{withConsensus.length}종목</span>
            </div>

            <div style={{ display: "flex", borderBottom: "1px solid #222", padding: "0 14px" }}>
                {([
                    { id: "upside" as const, label: "업사이드순" },
                    { id: "buy_ratio" as const, label: "Buy비율순" },
                    { id: "name" as const, label: "이름순" },
                ]).map((t) => (
                    <button key={t.id} onClick={() => setSort(t.id)} style={{
                        padding: "8px 10px", background: "none", border: "none",
                        borderBottom: sort === t.id ? "2px solid #B5FF19" : "2px solid transparent",
                        color: sort === t.id ? "#B5FF19" : "#666", fontSize: 10, fontWeight: 600, fontFamily: F, cursor: "pointer",
                    }}>{t.label}</button>
                ))}
            </div>

            <div style={{ padding: "6px 14px 14px", maxHeight: 440, overflowY: "auto" }}>
                {sorted.length === 0 ? (
                    <div style={{ padding: 24, textAlign: "center", color: "#555", fontSize: 12, fontFamily: F }}>컨센서스 데이터 없음</div>
                ) : sorted.map((r, i) => {
                    const c = r.analyst_consensus
                    const total = c.buy + (c.hold || 0) + (c.sell || 0)
                    const buyRatio = total > 0 ? ((c.buy / total) * 100).toFixed(0) : "—"
                    const upside = c.upside_pct || 0
                    return (
                        <div key={i} style={row}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <div style={{ flex: 1 }}>
                                    <span style={{ color: "#fff", fontSize: 12, fontWeight: 700, fontFamily: F }}>{r.name}</span>
                                    <span style={{ color: "#555", fontSize: 9, marginLeft: 6, fontFamily: F }}>{r.ticker}</span>
                                    <span style={{ color: "#444", fontSize: 9, marginLeft: 6, fontFamily: F }}>
                                        ${r.price?.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </span>
                                </div>
                            </div>
                            <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 6 }}>
                                <div>
                                    <div style={{ color: "#555", fontSize: 8, fontFamily: F, marginBottom: 2 }}>Rating</div>
                                    <RatingBar buy={c.buy} hold={c.hold || 0} sell={c.sell || 0} />
                                    <div style={{ display: "flex", gap: 6, marginTop: 2 }}>
                                        <span style={{ color: "#22C55E", fontSize: 8, fontWeight: 700, fontFamily: F }}>B:{c.buy}</span>
                                        <span style={{ color: "#F59E0B", fontSize: 8, fontWeight: 700, fontFamily: F }}>H:{c.hold || 0}</span>
                                        <span style={{ color: "#EF4444", fontSize: 8, fontWeight: 700, fontFamily: F }}>S:{c.sell || 0}</span>
                                        <span style={{ color: "#888", fontSize: 8, fontFamily: F }}>({buyRatio}% Buy)</span>
                                    </div>
                                </div>
                                <div style={{ textAlign: "center" }}>
                                    <div style={{ color: "#555", fontSize: 8, fontFamily: F, marginBottom: 2 }}>목표가</div>
                                    <div style={{ color: "#ccc", fontSize: 11, fontWeight: 700, fontFamily: F }}>
                                        ${c.target_mean?.toLocaleString("en-US", { maximumFractionDigits: 0 })}
                                    </div>
                                    <div style={{ color: "#444", fontSize: 8, fontFamily: F }}>
                                        {c.target_low ? `$${c.target_low.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : ""}
                                        {c.target_low || c.target_high ? " ~ " : ""}
                                        {c.target_high ? `$${c.target_high.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : ""}
                                    </div>
                                </div>
                                <div style={{ textAlign: "right" }}>
                                    <div style={{ color: "#555", fontSize: 8, fontFamily: F, marginBottom: 2 }}>Upside</div>
                                    <UpsideArrow pct={upside} />
                                </div>
                            </div>
                        </div>
                    )
                })}
            </div>
        </div>
    )
}

USAnalystView.defaultProps = { dataUrl: DATA_URL }
addPropertyControls(USAnalystView, {
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
const row: React.CSSProperties = {
    padding: "10px 0", borderBottom: "1px solid #1A1A1A",
}
