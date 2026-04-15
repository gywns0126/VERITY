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

export default function USInsiderFeed(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [tab, setTab] = useState<"insider" | "sec">("insider")

    useEffect(() => {
        if (!dataUrl) return
        fetchJson(dataUrl).then(setData).catch(() => {})
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
                <span style={{ color: "#666", fontSize: 13, fontFamily: F }}>내부자/SEC 로딩 중...</span>
            </div>
        )
    }

    return (
        <div style={card}>
            <div style={header}>
                <span style={{ fontSize: 16, fontWeight: 800, color: "#fff", fontFamily: F }}>🏛️ Insider & SEC</span>
                <div style={{ display: "flex", gap: 6 }}>
                    <span style={{ ...pill, background: "#0D2A0D", color: "#22C55E" }}>
                        Buy {insiderStocks.reduce((s, r) => s + (r.insider_sentiment?.positive_count || 0), 0)}건
                    </span>
                    <span style={{ ...pill, background: "#2A0D0D", color: "#EF4444" }}>
                        Sell {insiderStocks.reduce((s, r) => s + (r.insider_sentiment?.negative_count || 0), 0)}건
                    </span>
                </div>
            </div>

            <div style={{ display: "flex", borderBottom: "1px solid #222" }}>
                {([
                    { id: "insider" as const, label: `내부자 (${insiderStocks.length})` },
                    { id: "sec" as const, label: `SEC 공시 (${allFilings.length})` },
                ]).map((t) => (
                    <button key={t.id} onClick={() => setTab(t.id)} style={{
                        flex: 1, padding: "10px 0", background: "none", border: "none",
                        borderBottom: tab === t.id ? "2px solid #B5FF19" : "2px solid transparent",
                        color: tab === t.id ? "#B5FF19" : "#666", fontSize: 11, fontWeight: 600, fontFamily: F, cursor: "pointer",
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
                                                <span style={{ color: "#fff", fontSize: 12, fontWeight: 700, fontFamily: F }}>{r.name}</span>
                                                <span style={{ color: "#555", fontSize: 10, marginLeft: 6, fontFamily: F }}>{r.ticker}</span>
                                            </div>
                                            <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                                                <span style={{ color: "#22C55E", fontSize: 10, fontFamily: F }}>Buy {ins.positive_count || 0}</span>
                                                <span style={{ color: "#EF4444", fontSize: 10, fontFamily: F }}>Sell {ins.negative_count || 0}</span>
                                                <span style={{ color: "#888", fontSize: 10, fontFamily: F }}>
                                                    Net {net > 0 ? "+" : ""}{net.toLocaleString()}주
                                                </span>
                                            </div>
                                        </div>
                                        <div style={{ textAlign: "right" }}>
                                            <div style={{ color: sentColor, fontSize: 12, fontWeight: 800, fontFamily: F }}>{sentLabel}</div>
                                            <div style={{ color: "#555", fontSize: 9, fontFamily: F }}>MSPR {mspr > 0 ? "+" : ""}{mspr.toFixed(4)}</div>
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
                                            background: typeColor + "20", color: typeColor, fontSize: 9, fontWeight: 800,
                                            padding: "3px 6px", borderRadius: 4, fontFamily: F, whiteSpace: "nowrap",
                                        }}>{f.form_type || "Filing"}</span>
                                        <div style={{ minWidth: 0 }}>
                                            <div style={{ color: "#fff", fontSize: 11, fontWeight: 600, fontFamily: F, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                                {f.stock_name} <span style={{ color: "#555" }}>{f.ticker}</span>
                                            </div>
                                            {f.description && (
                                                <div style={{ color: "#666", fontSize: 9, fontFamily: F, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                                    {f.description}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                    <span style={{ color: "#555", fontSize: 9, fontFamily: F, whiteSpace: "nowrap", flexShrink: 0 }}>
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
    return <div style={{ padding: 24, textAlign: "center", color: "#555", fontSize: 12, fontFamily: F }}>{text}</div>
}

USInsiderFeed.defaultProps = { dataUrl: DATA_URL }
addPropertyControls(USInsiderFeed, {
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
const pill: React.CSSProperties = {
    fontSize: 9, fontWeight: 700, padding: "3px 8px", borderRadius: 4, fontFamily: F,
}
const row: React.CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "10px 0", borderBottom: "1px solid #1A1A1A", gap: 10,
}
