import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useMemo, useRef, useState } from "react"

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

function fetchPortfolioJson(url: string): Promise<any> {
    return fetch(bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit" })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((t) => JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
}

function buildWidgetHtml(): string {
    return `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>*{margin:0;padding:0}html,body,.tradingview-widget-container{width:100%;height:100%;overflow:hidden;background:#0a0a0a}</style>
</head><body>
<div class="tradingview-widget-container">
<div class="tradingview-widget-container__widget" style="width:100%;height:100%"></div>
<script src="https://s3.tradingview.com/external-embedding/embed-widget-stock-heatmap.js" async>
{"exchanges":[],"dataSource":"SPX500","grouping":"sector","blockSize":"market_cap_basic","blockColor":"change","locale":"ko","symbolUrl":"","colorTheme":"dark","hasTopBar":false,"isDataSetEnabled":false,"isZoomEnabled":true,"hasSymbolTooltip":true,"isMonoSize":false,"width":"100%","height":"100%"}
</script>
</div>
</body></html>`
}

interface Props {
    mapUrl: string
    dataUrl: string
    recUrl: string
    borderRadius: number
    showHeader: boolean
}

type Tab = "map" | "sectors" | "movers"

const GICS_ICONS: Record<string, string> = {
    "Technology": "💻", "기술": "💻",
    "Communication Services": "📡", "커뮤니케이션": "📡",
    "Consumer Cyclical": "🛍️", "Consumer Discretionary": "🛍️", "경기소비재": "🛍️",
    "Consumer Defensive": "🛒", "Consumer Staples": "🛒", "필수소비재": "🛒",
    "Financial Services": "🏦", "Financials": "🏦", "금융": "🏦",
    "Healthcare": "💊", "헬스케어": "💊",
    "Industrials": "🏭", "산업재": "🏭",
    "Energy": "⛽", "에너지": "⛽",
    "Basic Materials": "⚗️", "Materials": "⚗️", "소재": "⚗️",
    "Real Estate": "🏠", "부동산": "🏠",
    "Utilities": "⚡", "유틸리티": "⚡",
}

function heatColor(pct: number): string {
    if (pct > 2) return "#22C55E"
    if (pct > 1) return "#4ADE80"
    if (pct > 0.3) return "#86EFAC"
    if (pct > -0.3) return "#888"
    if (pct > -1) return "#FCA5A5"
    if (pct > -2) return "#F87171"
    return "#EF4444"
}

function heatBg(pct: number): string {
    if (pct > 0.3) return "rgba(34,197,94,0.08)"
    if (pct > -0.3) return "rgba(100,100,100,0.06)"
    return "rgba(239,68,68,0.08)"
}

export default function USMapEmbed(props: Props) {
    const { mapUrl, dataUrl, recUrl, borderRadius, showHeader } = props
    const [clientReady, setClientReady] = useState(false)
    const [loaded, setLoaded] = useState(false)
    const [timedOut, setTimedOut] = useState(false)
    const [tab, setTab] = useState<Tab>("map")
    const [dataMounted, setDataMounted] = useState(false)
    const [portfolio, setPortfolio] = useState<any>(null)
    const [fullRecMap, setFullRecMap] = useState<Record<string, any>>({})
    const widgetHtml = useRef(buildWidgetHtml())

    useEffect(() => setClientReady(true), [])

    useEffect(() => {
        if (!clientReady) return
        setLoaded(false)
        setTimedOut(false)
        const t = window.setTimeout(() => setTimedOut(true), 15_000)
        return () => window.clearTimeout(t)
    }, [clientReady])

    useEffect(() => {
        if (tab !== "map" && !dataMounted) setDataMounted(true)
    }, [tab, dataMounted])

    useEffect(() => {
        if (!dataMounted || !dataUrl) return
        fetchPortfolioJson(dataUrl).then(setPortfolio).catch(() => {})
    }, [dataMounted, dataUrl])

    useEffect(() => {
        const url = recUrl || DEFAULT_REC
        if (!url) return
        fetchPortfolioJson(url)
            .then((arr: any) => {
                if (!Array.isArray(arr)) return
                const m: Record<string, any> = {}
                arr.forEach((r: any) => { if (r?.ticker) m[r.ticker.toUpperCase()] = r })
                setFullRecMap(m)
            })
            .catch(() => {})
    }, [recUrl])

    return (
        <div style={{ ...box, borderRadius }}>
            {showHeader && (
                <div style={hdr}>
                    <span style={titleSt}>
                        {tab === "map" ? "US Market Map" : tab === "sectors" ? "섹터 퍼포먼스" : "Top Movers"}
                    </span>
                    <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                        <Pill label="히트맵" on={tab === "map"} onClick={() => setTab("map")} />
                        <Pill label="섹터" on={tab === "sectors"} onClick={() => setTab("sectors")} />
                        <Pill label="Movers" on={tab === "movers"} onClick={() => setTab("movers")} />
                        {tab === "map" && (
                            <a href={mapUrl} target="_blank" rel="noopener noreferrer" style={extLink}>
                                새 창 →
                            </a>
                        )}
                    </div>
                </div>
            )}

            <div style={{
                position: "relative", width: "100%", flex: 1, overflow: "hidden",
                borderRadius: showHeader ? `0 0 ${borderRadius}px ${borderRadius}px` : borderRadius,
                background: C.bgPage,
            }}>
                {/* Map tab */}
                <div style={{ position: "absolute", inset: 0, display: tab === "map" ? "block" : "none" }}>
                    {!clientReady ? (
                        <div style={absCenter}>
                            <span style={accentTxt}>불러오는 중…</span>
                            <a href={mapUrl} target="_blank" rel="noopener noreferrer" style={greenBtn}>새 창에서 열기</a>
                        </div>
                    ) : (
                        <>
                            <iframe
                                title="US Stock Heatmap"
                                srcDoc={widgetHtml.current}
                                sandbox="allow-scripts allow-same-origin allow-popups"
                                onLoad={() => setLoaded(true)}
                                style={{
                                    position: "absolute", top: 0, left: 0,
                                    width: "100%", height: "100%",
                                    border: "none", display: "block", zIndex: 1,
                                }}
                                loading="eager"
                            />
                            {!loaded && (
                                <div style={absOverlay}>
                                    <span style={accentTxt}>S&P 500 히트맵 로딩 중…</span>
                                    {timedOut && (
                                        <div style={{ display: "flex", flexDirection: "column" as const, alignItems: "center", gap: 10, maxWidth: 280, textAlign: "center" as const }}>
                                            <span style={grayTxt}>15초 이상 로딩 중입니다. 팝업 차단 또는 네트워크를 확인하세요.</span>
                                            <a href={mapUrl} target="_blank" rel="noopener noreferrer" style={greenBtn}>새 창에서 열기</a>
                                        </div>
                                    )}
                                </div>
                            )}
                        </>
                    )}
                </div>

                {/* Sectors tab */}
                {dataMounted && (
                    <div style={{
                        position: "absolute", inset: 0,
                        display: tab === "sectors" ? "flex" : "none",
                        flexDirection: "column", overflow: "hidden",
                    }}>
                        <SectorPanel portfolio={portfolio} fullRecMap={fullRecMap} />
                    </div>
                )}

                {/* Movers tab */}
                {dataMounted && (
                    <div style={{
                        position: "absolute", inset: 0,
                        display: tab === "movers" ? "flex" : "none",
                        flexDirection: "column", overflow: "hidden",
                    }}>
                        <MoversPanel portfolio={portfolio} fullRecMap={fullRecMap} />
                    </div>
                )}
            </div>
        </div>
    )
}

// ─── Sector Performance Panel ─────────────────────────────

function SectorPanel({ portfolio, fullRecMap = {} }: { portfolio: any; fullRecMap?: Record<string, any> }) {
    const [expanded, setExpanded] = useState<string | null>(null)

    const sectors: any[] = useMemo(() => {
        const direct = (portfolio?.sectors || []).filter((s: any) => {
            const m = String(s.market || "").toUpperCase()
            return m === "US" || m === "NYSE" || m === "NASDAQ" || m === "AMEX"
        })
        if (direct.length > 0) return direct

        // fallback: recommendations에서 섹터를 재집계
        const recs: any[] = (portfolio?.recommendations || []).filter((r: any) =>
            r?.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(r?.market || "")
        )
        const bySector: Record<string, any[]> = {}
        for (const r of recs) {
            const sec = String(r.sector || r.industry || "Unknown")
            bySector[sec] = bySector[sec] || []
            bySector[sec].push(r)
        }
        return Object.entries(bySector).map(([name, rows]) => {
            const topStocks = [...rows]
                .sort((a, b) => (b?.technical?.price_change_pct || b?.change_pct || 0) - (a?.technical?.price_change_pct || a?.change_pct || 0))
                .slice(0, 4)
                .map((x: any) => ({
                    name: x.name,
                    ticker: x.ticker,
                    change_pct: x?.technical?.price_change_pct || x?.change_pct || 0,
                }))
            const avg = rows.reduce((acc: number, x: any) => acc + (x?.technical?.price_change_pct || x?.change_pct || 0), 0) / Math.max(rows.length, 1)
            return { name, name_en: name, change_pct: avg, top_stocks: topStocks, market: "US" }
        }).sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0))
    }, [portfolio])

    if (!portfolio) {
        return <div style={flexCenter}><span style={accentTxt}>데이터 로딩 중…</span></div>
    }

    if (sectors.length === 0) {
        return (
            <div style={flexCenter}>
                <span style={grayTxt}>US 섹터 데이터가 없습니다</span>
                <span style={{ color: C.textTertiary, fontSize: 12, fontFamily: FONT }}>파이프라인에서 섹터 데이터를 수집하고 있는지 확인하세요</span>
            </div>
        )
    }

    const gainers = sectors.filter(s => (s.change_pct || 0) > 0.3).length
    const losers = sectors.filter(s => (s.change_pct || 0) < -0.3).length

    return (
        <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 16px", borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
                <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                    <span style={{ color: C.textPrimary, fontSize: 13, fontWeight: 700, fontFamily: FONT }}>GICS {sectors.length} 섹터</span>
                    <div style={{ display: "flex", gap: 6 }}>
                        <span style={{ color: "#22C55E", fontSize: 12, fontWeight: 700, fontFamily: FONT }}>▲{gainers}</span>
                        <span style={{ color: "#EF4444", fontSize: 12, fontWeight: 700, fontFamily: FONT }}>▼{losers}</span>
                    </div>
                </div>
                <span style={{ color: C.textTertiary, fontSize: 12, fontFamily: FONT }}>탭하여 상세</span>
            </div>

            <div style={{ flex: 1, overflowY: "auto", padding: "8px 12px 14px" }}>
                <div style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))",
                    gap: 6,
                }}>
                    {sectors.map((sec, i) => {
                        const pct = sec.change_pct || 0
                        const isOpen = expanded === sec.name
                        const topStocks: any[] = sec.top_stocks || []
                        return (
                            <div
                                key={i}
                                onClick={() => setExpanded(isOpen ? null : sec.name)}
                                style={{
                                    background: heatBg(pct), borderRadius: 10,
                                    border: isOpen ? "1px solid #444" : "1px solid #1a1a1a",
                                    padding: "10px 8px", cursor: "pointer",
                                    gridColumn: isOpen ? "1 / -1" : "auto",
                                    transition: "all 0.15s ease",
                                }}
                            >
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                                        <span style={{ fontSize: 14 }}>{GICS_ICONS[sec.name] || GICS_ICONS[sec.name_en] || "📊"}</span>
                                        <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>{sec.name}</span>
                                    </div>
                                    <span style={{ color: heatColor(pct), fontSize: 13, fontWeight: 800, fontFamily: FONT }}>
                                        {pct > 0 ? "+" : ""}{pct.toFixed(1)}%
                                    </span>
                                </div>
                                {sec.name_en && (
                                    <div style={{ color: C.textTertiary, fontSize: 8, fontFamily: FONT, marginTop: 2 }}>{sec.name_en}</div>
                                )}
                                <StrengthBar pct={pct} />

                                {isOpen && topStocks.length > 0 && (
                                    <div style={{ marginTop: 8, borderTop: "1px solid #333", paddingTop: 8, display: "flex", flexWrap: "wrap", gap: 6 }}>
                                        {topStocks.map((s: any, j: number) => {
                                            const sc = (s.change_pct || 0) >= 0 ? C.up : C.down
                                            return (
                                                <div key={j} style={{ background: C.bgElevated, borderRadius: 6, padding: "5px 8px", border: `1px solid ${C.border}` }}>
                                                    <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 600, fontFamily: FONT }}>{s.name || s.ticker}</span>
                                                    {s.ticker && <span style={{ color: C.textTertiary, fontSize: 8, marginLeft: 4, fontFamily: FONT }}>{s.ticker}</span>}
                                                    <span style={{ color: sc, fontSize: 12, fontWeight: 700, marginLeft: 6, fontFamily: FONT }}>
                                                        {(s.change_pct || 0) > 0 ? "+" : ""}{(s.change_pct || 0).toFixed(1)}%
                                                    </span>
                                                </div>
                                            )
                                        })}
                                    </div>
                                )}
                            </div>
                        )
                    })}
                </div>
            </div>
        </>
    )
}

function StrengthBar({ pct }: { pct: number }) {
    const norm = Math.min(Math.abs(pct) / 3 * 100, 100)
    const color = pct >= 0 ? C.up : C.down
    return (
        <div style={{ height: 3, background: C.bgElevated, borderRadius: 2, marginTop: 5 }}>
            <div style={{ height: "100%", width: `${norm}%`, background: color, borderRadius: 2 }} />
        </div>
    )
}

// ─── Top Movers Panel ─────────────────────────────────────

function MoversPanel({ portfolio, fullRecMap = {} }: { portfolio: any; fullRecMap?: Record<string, any> }) {
    const [view, setView] = useState<"gainers" | "losers">("gainers")

    const allStocks = useMemo(() => {
        const slimRecs: any[] = portfolio?.recommendations || []
        const recs: any[] = slimRecs.map((r: any) => ({ ...r, ...(fullRecMap[(r.ticker || "").toUpperCase()] || {}) }))
        const holds: any[] = portfolio?.vams?.holdings || portfolio?.holdings || []
        const combined = [...recs, ...holds]
        const seen = new Set<string>()
        return combined.filter((s) => {
            const t = (s.ticker || "").toUpperCase()
            if (!t || seen.has(t)) return false
            seen.add(t)
            const isUS = s.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(s.market || "")
            if (!isUS) return false
            return true
        })
    }, [portfolio])

    const sorted = useMemo(() => {
        return [...allStocks].sort((a, b) => {
            const ac = a.technical?.price_change_pct ?? a.change_pct ?? 0
            const bc = b.technical?.price_change_pct ?? b.change_pct ?? 0
            return view === "gainers" ? bc - ac : ac - bc
        }).slice(0, 15)
    }, [allStocks, view])

    if (!portfolio) {
        return <div style={flexCenter}><span style={accentTxt}>데이터 로딩 중…</span></div>
    }

    if (allStocks.length === 0) {
        return (
            <div style={flexCenter}>
                <span style={grayTxt}>종목 데이터가 없습니다</span>
            </div>
        )
    }

    return (
        <>
            <div style={{ display: "flex", gap: 4, padding: "10px 16px", borderBottom: `1px solid ${C.border}`, flexShrink: 0 }}>
                <MoverPill label="🔥 Top Gainers" on={view === "gainers"} onClick={() => setView("gainers")} />
                <MoverPill label="❄️ Top Losers" on={view === "losers"} onClick={() => setView("losers")} />
                <span style={{ marginLeft: "auto", color: C.textTertiary, fontSize: 12, fontFamily: FONT, alignSelf: "center" }}>
                    {allStocks.length}종목 중 Top 15
                </span>
            </div>

            <div style={{ flex: 1, overflowY: "auto" }}>
                {sorted.map((stock, i) => {
                    const ticker = (stock.ticker || "").toUpperCase()
                    const pct = stock.technical?.price_change_pct ?? stock.change_pct ?? 0
                    const price = stock.price || stock.current_price || 0
                    const vol = stock.volume || stock.avg_volume || 0
                    const color = pct >= 0 ? C.up : C.down
                    const sparkData: number[] = stock.sparkline_weekly || []

                    return (
                        <div key={ticker} style={{
                            display: "flex", alignItems: "center", padding: "10px 16px",
                            borderBottom: "1px solid #111", gap: 10,
                        }}>
                            <div style={{
                                width: 24, height: 24, borderRadius: 6,
                                background: heatBg(pct), display: "flex",
                                alignItems: "center", justifyContent: "center",
                                color: C.textTertiary, fontSize: 12, fontWeight: 800, fontFamily: FONT,
                                flexShrink: 0,
                            }}>
                                {i + 1}
                            </div>

                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                    <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>
                                        {stock.name || ticker}
                                    </span>
                                    <span style={{ color: C.textTertiary, fontSize: 12, fontFamily: FONT }}>{ticker}</span>
                                </div>
                                <div style={{ color: C.textTertiary, fontSize: 12, fontFamily: FONT, marginTop: 2 }}>
                                    {vol > 0 ? `Vol ${fmtVol(vol)}` : ""}
                                    {stock.sector ? ` · ${stock.sector}` : ""}
                                </div>
                            </div>

                            {sparkData.length > 1 && <MiniSparkline data={sparkData} color={color} />}

                            <div style={{ textAlign: "right", flexShrink: 0 }}>
                                <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>
                                    ${price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </div>
                                <div style={{ color, fontSize: 12, fontWeight: 800, fontFamily: FONT }}>
                                    {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
                                </div>
                            </div>
                        </div>
                    )
                })}
            </div>
        </>
    )
}

function MiniSparkline({ data, color }: { data: number[]; color: string }) {
    if (!data || data.length < 2) return null
    const min = Math.min(...data), max = Math.max(...data), range = max - min || 1
    const w = 50, h = 18
    const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * h}`).join(" ")
    return (
        <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block", flexShrink: 0 }}>
            <polyline points={pts} fill="none" stroke={color} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    )
}

function fmtVol(v: number): string {
    if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`
    if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`
    if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`
    return v.toLocaleString()
}

// ─── UI Primitives ────────────────────────────────────────

function Pill({ label, on, onClick }: { label: string; on: boolean; onClick: () => void }) {
    return (
        <button onClick={onClick} style={{
            background: on ? "#B5FF19" : "transparent", color: on ? "#000" : "#666",
            border: on ? "none" : "1px solid #333", borderRadius: 6,
            padding: "4px 10px", fontSize: 12, fontWeight: 600,
            cursor: "pointer", fontFamily: FONT,
        }}>{label}</button>
    )
}

function MoverPill({ label, on, onClick }: { label: string; on: boolean; onClick: () => void }) {
    return (
        <button onClick={onClick} style={{
            background: on ? "rgba(181,255,25,0.1)" : "transparent",
            color: on ? "#B5FF19" : "#555",
            border: on ? "1px solid #B5FF19" : "1px solid #222",
            borderRadius: 8, padding: "6px 12px", fontSize: 12,
            fontWeight: 700, cursor: "pointer", fontFamily: FONT,
        }}>{label}</button>
    )
}

// ─── Styles ───────────────────────────────────────────────

const box: React.CSSProperties = {
    width: "100%", height: "100%", background: C.bgElevated,
    border: `1px solid ${C.border}`, overflow: "hidden", fontFamily: FONT,
    boxSizing: "border-box", display: "flex", flexDirection: "column",
}

const hdr: React.CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "12px 16px", borderBottom: `1px solid ${C.border}`, flexShrink: 0,
}

const titleSt: React.CSSProperties = { color: C.textPrimary, fontSize: 14, fontWeight: 700, fontFamily: FONT }

const extLink: React.CSSProperties = {
    color: "#B5FF19", fontSize: 12, fontWeight: 600,
    textDecoration: "none", fontFamily: FONT, marginLeft: 8,
}

const absOverlay: React.CSSProperties = {
    position: "absolute", inset: 0, display: "flex", flexDirection: "column",
    alignItems: "center", justifyContent: "center", gap: 12,
    background: "rgba(10,10,10,0.92)", zIndex: 20, pointerEvents: "auto",
}

const absCenter: React.CSSProperties = {
    position: "absolute", inset: 0, display: "flex", flexDirection: "column",
    alignItems: "center", justifyContent: "center", gap: 14,
    padding: 20, zIndex: 5, textAlign: "center",
}

const flexCenter: React.CSSProperties = {
    flex: 1, display: "flex", flexDirection: "column",
    alignItems: "center", justifyContent: "center", gap: 12,
}

const accentTxt: React.CSSProperties = { color: "#B5FF19", fontSize: 13, fontWeight: 600, fontFamily: FONT }
const grayTxt: React.CSSProperties = { color: C.textSecondary, fontSize: 12, lineHeight: 1.5, fontFamily: FONT }

const greenBtn: React.CSSProperties = {
    color: "#000", background: "#B5FF19", fontSize: 12, fontWeight: 700,
    padding: "8px 14px", borderRadius: 8, textDecoration: "none", fontFamily: FONT,
}

// ─── Framer config ────────────────────────────────────────

const DEFAULT_MAP = "https://www.tradingview.com/heatmap/stock/?dataSource=SPX500&grouping=sector&blockSize=market_cap_basic&blockColor=change&locale=ko"
const DEFAULT_DATA = "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json"
const DEFAULT_REC  = "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/recommendations.json"

USMapEmbed.defaultProps = {
    mapUrl: DEFAULT_MAP,
    dataUrl: DEFAULT_DATA,
    recUrl: DEFAULT_REC,
    borderRadius: 16,
    showHeader: true,
}

addPropertyControls(USMapEmbed, {
    mapUrl:   { type: ControlType.String, title: "히트맵 URL", defaultValue: DEFAULT_MAP },
    dataUrl:  { type: ControlType.String, title: "Portfolio URL", defaultValue: DEFAULT_DATA },
    recUrl:   { type: ControlType.String, title: "Recommendations URL", defaultValue: DEFAULT_REC },
    borderRadius: { type: ControlType.Number, title: "모서리 곡률", defaultValue: 16, min: 0, max: 32, step: 2 },
    showHeader: { type: ControlType.Boolean, title: "헤더 표시", defaultValue: true },
})
