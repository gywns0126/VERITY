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

const MAG7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]
const MAG7_ICONS: Record<string, string> = {
    AAPL: "🍎", MSFT: "🪟", GOOGL: "🔍", AMZN: "📦", NVDA: "🟢", META: "📘", TSLA: "⚡",
}

interface Props { dataUrl: string }

function MiniSparkline({ data, color }: { data: number[]; color: string }) {
    if (!data || data.length < 2) return null
    const min = Math.min(...data)
    const max = Math.max(...data)
    const range = max - min || 1
    const w = 60, h = 20
    const step = w / (data.length - 1)
    const pts = data.map((v, i) => `${i * step},${h - ((v - min) / range) * h}`).join(" ")
    return (
        <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
            <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    )
}

export default function USMag7Tracker(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)

    useEffect(() => {
        if (!dataUrl) return
        fetchJson(dataUrl).then(setData).catch(() => {})
    }, [dataUrl])

    const allRecs: any[] = data?.recommendations || []
    const allHoldings: any[] = data?.holdings || []
    const combined = [...allRecs, ...allHoldings]

    const mag7Stocks = MAG7.map((ticker) =>
        combined.find((r) => (r.ticker || "").toUpperCase() === ticker)
    ).filter(Boolean)

    const totalMarketCap = mag7Stocks.reduce((s, r) => {
        const mc = r?.finnhub_metrics?.market_cap || r?.market_cap || 0
        return s + mc
    }, 0)

    const avgChange = mag7Stocks.length > 0
        ? mag7Stocks.reduce((s, r) => s + (r?.technical?.price_change_pct || r?.change_pct || 0), 0) / mag7Stocks.length
        : 0

    const gainers = mag7Stocks.filter((r) => (r?.technical?.price_change_pct || r?.change_pct || 0) > 0).length
    const losers = mag7Stocks.length - gainers

    if (!data) {
        return (
            <div style={{ ...card, minHeight: 140, alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: "#666", fontSize: 13, fontFamily: F }}>Mag 7 로딩 중...</span>
            </div>
        )
    }

    if (mag7Stocks.length === 0) {
        return (
            <div style={{ ...card, padding: 20, alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: "#555", fontSize: 13, fontFamily: F }}>포트폴리오에 Mag 7 종목 없음</span>
            </div>
        )
    }

    return (
        <div style={card}>
            <div style={header}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 16, fontWeight: 800, color: "#fff", fontFamily: F }}>✨ Magnificent 7</span>
                    <span style={{ color: "#555", fontSize: 10, fontFamily: F }}>{mag7Stocks.length}종목</span>
                </div>
                <div style={{ textAlign: "right" }}>
                    <span style={{ color: avgChange >= 0 ? "#22C55E" : "#EF4444", fontSize: 14, fontWeight: 800, fontFamily: F }}>
                        {avgChange >= 0 ? "+" : ""}{avgChange.toFixed(2)}%
                    </span>
                    <div style={{ display: "flex", gap: 6, marginTop: 2 }}>
                        <span style={{ color: "#22C55E", fontSize: 9, fontFamily: F }}>▲{gainers}</span>
                        <span style={{ color: "#EF4444", fontSize: 9, fontFamily: F }}>▼{losers}</span>
                    </div>
                </div>
            </div>

            <div style={{ padding: "6px 12px 14px" }}>
                {mag7Stocks.map((stock, i) => {
                    const ticker = (stock.ticker || "").toUpperCase()
                    const changePct = stock.technical?.price_change_pct ?? stock.change_pct ?? 0
                    const price = stock.price || stock.current_price || 0
                    const mc = stock.finnhub_metrics?.market_cap || stock.market_cap || 0
                    const sparkData = stock.sparkline_weekly || []
                    const consensus = stock.analyst_consensus || {}
                    const earningsSurp = (stock.earnings_surprises || [])[0]
                    const color = changePct >= 0 ? "#22C55E" : "#EF4444"

                    return (
                        <div key={i} style={{
                            padding: "12px 10px", borderBottom: "1px solid #1A1A1A",
                            display: "flex", flexDirection: "column", gap: 8,
                        }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                    <span style={{ fontSize: 20 }}>{MAG7_ICONS[ticker] || "📊"}</span>
                                    <div>
                                        <span style={{ color: "#fff", fontSize: 14, fontWeight: 800, fontFamily: F }}>{stock.name || ticker}</span>
                                        <span style={{ color: "#555", fontSize: 10, marginLeft: 6, fontFamily: F }}>{ticker}</span>
                                    </div>
                                </div>
                                <div style={{ textAlign: "right" }}>
                                    <div style={{ color: "#fff", fontSize: 14, fontWeight: 700, fontFamily: F }}>
                                        ${price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </div>
                                    <div style={{ color, fontSize: 12, fontWeight: 800, fontFamily: F }}>
                                        {changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%
                                    </div>
                                </div>
                            </div>

                            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                                {sparkData.length > 0 && (
                                    <MiniSparkline data={sparkData} color={color} />
                                )}
                                <div style={{ display: "flex", gap: 6, flex: 1, flexWrap: "wrap" }}>
                                    {mc > 0 && (
                                        <MetricChip label="Mkt Cap" value={mc > 1e6 ? `$${(mc / 1e6).toFixed(0)}T` : mc > 1e3 ? `$${(mc / 1e3).toFixed(0)}B` : `$${mc.toFixed(0)}M`} />
                                    )}
                                    {consensus.buy > 0 && (
                                        <MetricChip label="Buy/Hold/Sell" value={`${consensus.buy}/${consensus.hold || 0}/${consensus.sell || 0}`}
                                            color={consensus.buy > (consensus.hold || 0) + (consensus.sell || 0) ? "#22C55E" : "#F59E0B"} />
                                    )}
                                    {consensus.upside_pct != null && consensus.upside_pct !== 0 && (
                                        <MetricChip label="Upside" value={`${consensus.upside_pct > 0 ? "+" : ""}${consensus.upside_pct}%`}
                                            color={consensus.upside_pct > 0 ? "#22C55E" : "#EF4444"} />
                                    )}
                                    {earningsSurp && earningsSurp.surprise_pct != null && (
                                        <MetricChip label="Last EPS"
                                            value={`${earningsSurp.surprise_pct > 0 ? "+" : ""}${earningsSurp.surprise_pct}%`}
                                            color={earningsSurp.surprise_pct > 0 ? "#22C55E" : "#EF4444"} />
                                    )}
                                </div>
                            </div>
                        </div>
                    )
                })}
            </div>
        </div>
    )
}

function MetricChip({ label, value, color = "#ccc" }: { label: string; value: string; color?: string }) {
    return (
        <div style={{ background: "#111", borderRadius: 5, padding: "3px 6px", border: "1px solid #222" }}>
            <div style={{ color: "#555", fontSize: 7, fontWeight: 600, fontFamily: F }}>{label}</div>
            <div style={{ color, fontSize: 10, fontWeight: 700, fontFamily: F }}>{value}</div>
        </div>
    )
}

USMag7Tracker.defaultProps = { dataUrl: DATA_URL }
addPropertyControls(USMag7Tracker, {
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
