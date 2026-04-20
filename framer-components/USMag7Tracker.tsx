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
const FONT = "'Inter', 'Pretendard', -apple-system, sans-serif"
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
const REC_URL  = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/recommendations.json"
const F = "'Inter', 'Pretendard', -apple-system, sans-serif"

const MAG7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]
const MAG7_ICONS: Record<string, string> = {
    AAPL: "🍎", MSFT: "🪟", GOOGL: "🔍", AMZN: "📦", NVDA: "🟢", META: "📘", TSLA: "⚡",
}

interface Props { dataUrl: string; recUrl?: string }

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
    const { dataUrl, recUrl } = props
    const [data, setData] = useState<any>(null)
    const [fullRecMap, setFullRecMap] = useState<Record<string, any>>({})

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    useEffect(() => {
        const ac = new AbortController()
        const url = recUrl || REC_URL
        fetchJson(url, ac.signal)
            .then((arr: any) => {
                if (ac.signal.aborted) return
                if (!Array.isArray(arr)) return
                const m: Record<string, any> = {}
                arr.forEach((r: any) => { if (r?.ticker) m[r.ticker.toUpperCase()] = r })
                setFullRecMap(m)
            })
            .catch(() => {})
        return () => ac.abort()
    }, [recUrl])

    const slimRecs: any[] = data?.recommendations || []
    const allRecs: any[] = slimRecs.map(r => ({ ...r, ...(fullRecMap[String(r.ticker || "").toUpperCase()] || {}) }))
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
                    <span style={{ color: avgChange >= 0 ? C.up : C.down, fontSize: 14, fontWeight: 800, fontFamily: F }}>
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
                    const color = changePct >= 0 ? C.up : C.down

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
                                            color={consensus.upside_pct > 0 ? C.up : C.down} />
                                    )}
                                    {earningsSurp && earningsSurp.surprise_pct != null && (
                                        <MetricChip label="Last EPS"
                                            value={`${earningsSurp.surprise_pct > 0 ? "+" : ""}${earningsSurp.surprise_pct}%`}
                                            color={earningsSurp.surprise_pct > 0 ? C.up : C.down} />
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

USMag7Tracker.defaultProps = { dataUrl: DATA_URL, recUrl: REC_URL }
addPropertyControls(USMag7Tracker, {
    dataUrl: { type: ControlType.String, title: "Portfolio URL", defaultValue: DATA_URL },
    recUrl:  { type: ControlType.String, title: "Recommendations URL", defaultValue: REC_URL },
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
