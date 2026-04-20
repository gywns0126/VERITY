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
const F = "'Inter', 'Pretendard', -apple-system, sans-serif"

interface Props { dataUrl: string }

export default function USInsiderFeed(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [tab, setTab] = useState<"insider" | "sec">("insider")

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    const allRecs: any[] = data?.recommendations || []
    const usRecs = allRecs.filter((r) => r.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(r.market || ""))

    const insiderStocks = usRecs.filter((r) => {
        const ins = r.insider_sentiment
        return ins && (ins.positive_count > 0 || ins.negative_count > 0 || ins.net_shares !== 0)
    })

    const secStocks = usRecs.filter((r) => Array.isArray(r.sec_filings) && r.sec_filings.length > 0)

    const allFilings = secStocks.flatMap((r) =>
        (r.sec_filings || []).map((f: any) => ({ ...f, stock_name: r.name, ticker: r.ticker }))
    ).sort((a, b) => (b.filed_date || "").localeCompare(a.filed_date || "")).slice(0, 30)

    if (!data) {
        return (
            <div style={{ ...card, minHeight: 140, alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: C.textTertiary, fontSize: 13, fontFamily: F }}>내부자/SEC 로딩 중...</span>
            </div>
        )
    }

    return (
        <div style={card}>
            <div style={header}>
                <span style={{ fontSize: 16, fontWeight: 800, color: C.textPrimary, fontFamily: F }}>🏛️ Insider & SEC</span>
                <div style={{ display: "flex", gap: 6 }}>
                    <span style={{ ...pill, background: "#0D2A0D", color: "#22C55E" }}>
                        Buy {insiderStocks.reduce((s, r) => s + (r.insider_sentiment?.positive_count || 0), 0)}건
                    </span>
                    <span style={{ ...pill, background: "#2A0D0D", color: "#EF4444" }}>
                        Sell {insiderStocks.reduce((s, r) => s + (r.insider_sentiment?.negative_count || 0), 0)}건
                    </span>
                </div>
            </div>

            <div style={{ display: "flex", borderBottom: `1px solid ${C.border}` }}>
                {([
                    { id: "insider" as const, label: `내부자 (${insiderStocks.length})` },
                    { id: "sec" as const, label: `SEC 공시 (${allFilings.length})` },
                ]).map((t) => (
                    <button key={t.id} onClick={() => setTab(t.id)} style={{
                        flex: 1, padding: "10px 0", background: "none", border: "none",
                        borderBottom: tab === t.id ? "2px solid #B5FF19" : "2px solid transparent",
                        color: tab === t.id ? "#B5FF19" : "#666", fontSize: 12, fontWeight: 600, fontFamily: F, cursor: "pointer",
                    }}>{t.label}</button>
                ))}
            </div>

            <div style={{ padding: "10px 14px", maxHeight: 420, overflowY: "auto" }}>
                {tab === "insider" && (
                    insiderStocks.length === 0
                        ? <Empty text="내부자 거래 데이터 없음" />
                        : insiderStocks
                            .sort((a, b) => Math.abs(b.insider_sentiment?.net_shares || 0) - Math.abs(a.insider_sentiment?.net_shares || 0))
                            .map((r, i) => {
                                const ins = r.insider_sentiment || {}
                                const mspr = ins.mspr || 0
                                const net = ins.net_shares || 0
                                const sentiment = mspr > 0 ? "bullish" : mspr < 0 ? "bearish" : "neutral"
                                const sentColor = sentiment === "bullish" ? "#22C55E" : sentiment === "bearish" ? "#EF4444" : "#888"
                                const sentLabel = sentiment === "bullish" ? "매수 우세" : sentiment === "bearish" ? "매도 우세" : "중립"
                                return (
                                    <div key={i} style={row}>
                                        <div style={{ flex: 1 }}>
                                            <div>
                                                <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: F }}>{r.name}</span>
                                                <span style={{ color: C.textTertiary, fontSize: 12, marginLeft: 6, fontFamily: F }}>{r.ticker}</span>
                                            </div>
                                            <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                                                <span style={{ color: "#22C55E", fontSize: 12, fontFamily: F }}>Buy {ins.positive_count || 0}</span>
                                                <span style={{ color: "#EF4444", fontSize: 12, fontFamily: F }}>Sell {ins.negative_count || 0}</span>
                                                <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: F }}>
                                                    Net {net > 0 ? "+" : ""}{net.toLocaleString()}주
                                                </span>
                                            </div>
                                        </div>
                                        <div style={{ textAlign: "right" }}>
                                            <div style={{ color: sentColor, fontSize: 12, fontWeight: 800, fontFamily: F }}>{sentLabel}</div>
                                            <div style={{ color: C.textTertiary, fontSize: 12, fontFamily: F }}>MSPR {mspr > 0 ? "+" : ""}{mspr.toFixed(4)}</div>
                                        </div>
                                    </div>
                                )
                            })
                )}

                {tab === "sec" && (
                    allFilings.length === 0
                        ? <Empty text="SEC 공시 데이터 없음" />
                        : allFilings.map((f, i) => {
                            const typeColor = f.form_type === "10-K" ? "#F59E0B" : f.form_type === "10-Q" ? "#60A5FA" : f.form_type === "8-K" ? "#A78BFA" : "#888"
                            return (
                                <div key={i} style={row}>
                                    <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 0 }}>
                                        <span style={{
                                            background: typeColor + "20", color: typeColor, fontSize: 12, fontWeight: 800,
                                            padding: "3px 6px", borderRadius: 6, fontFamily: F, whiteSpace: "nowrap",
                                        }}>{f.form_type || "Filing"}</span>
                                        <div style={{ minWidth: 0 }}>
                                            <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 600, fontFamily: F, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                                {f.stock_name} <span style={{ color: C.textTertiary }}>{f.ticker}</span>
                                            </div>
                                            {f.description && (
                                                <div style={{ color: C.textTertiary, fontSize: 12, fontFamily: F, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                                    {f.description}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                    <span style={{ color: C.textTertiary, fontSize: 12, fontFamily: F, whiteSpace: "nowrap", flexShrink: 0 }}>
                                        {f.filed_date || ""}
                                    </span>
                                </div>
                            )
                        })
                )}
            </div>
        </div>
    )
}

function Empty({ text }: { text: string }) {
    return <div style={{ padding: 24, textAlign: "center", color: C.textTertiary, fontSize: 12, fontFamily: F }}>{text}</div>
}

USInsiderFeed.defaultProps = { dataUrl: DATA_URL }
addPropertyControls(USInsiderFeed, {
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
const pill: React.CSSProperties = {
    fontSize: 12, fontWeight: 700, padding: "3px 8px", borderRadius: 6, fontFamily: F,
}
const row: React.CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "10px 0", borderBottom: `1px solid ${C.border}`, gap: 10,
}
