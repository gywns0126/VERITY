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

function Gauge({ value, max, label, color, suffix = "" }: { value: number; max: number; label: string; color: string; suffix?: string }) {
    const pct = Math.min(Math.abs(value) / (max || 1) * 100, 100)
    return (
        <div style={{ flex: 1, minWidth: 80 }}>
            <div style={{ color: "#666", fontSize: 9, fontWeight: 600, fontFamily: F, marginBottom: 3 }}>{label}</div>
            <div style={{ color, fontSize: 15, fontWeight: 800, fontFamily: F }}>{value != null ? `${value}${suffix}` : "—"}</div>
            <div style={{ height: 3, background: "#1A1A1A", borderRadius: 2, marginTop: 3 }}>
                <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: 2 }} />
            </div>
        </div>
    )
}

export default function USFlowPanel(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [tab, setTab] = useState<"options" | "short" | "preafter">("options")

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    const allRecs: any[] = data?.recommendations || []
    const usRecs = allRecs.filter((r) => r.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(r.market || ""))

    const optionsStocks = usRecs.filter((r) => r.options_flow?.put_call_ratio != null)
    const shortStocks = usRecs.filter((r) => r.short_interest?.short_pct != null || r.finnhub_metrics?.short_pct_float != null)
    const preAfterStocks = usRecs.filter((r) => r.pre_after_market?.pre_price != null || r.pre_after_market?.after_price != null)

    const avgPCR = optionsStocks.length > 0
        ? optionsStocks.reduce((s, r) => s + (r.options_flow.put_call_ratio || 0), 0) / optionsStocks.length
        : null

    if (!data) {
        return (
            <div style={{ ...card, height: "100%", minHeight: 180, alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: "#666", fontSize: 13, fontFamily: F }}>US 플로우 로딩 중...</span>
            </div>
        )
    }

    return (
        <div style={card}>
            <div style={header}>
                <span style={{ fontSize: 16, fontWeight: 800, color: "#fff", fontFamily: F }}>🔀 US Flow Panel</span>
                {avgPCR != null && (
                    <span style={{ color: avgPCR > 1 ? "#EF4444" : "#22C55E", fontSize: 11, fontWeight: 700, fontFamily: F }}>
                        Avg P/C {avgPCR.toFixed(2)}
                    </span>
                )}
            </div>

            <div style={{ display: "flex", borderBottom: "1px solid #222" }}>
                {([
                    { id: "options" as const, label: `옵션 (${optionsStocks.length})` },
                    { id: "short" as const, label: `공매도 (${shortStocks.length})` },
                    { id: "preafter" as const, label: `Pre/After (${preAfterStocks.length})` },
                ]).map((t) => (
                    <button key={t.id} onClick={() => setTab(t.id)} style={{
                        flex: 1, padding: "10px 0", background: "none", border: "none",
                        borderBottom: tab === t.id ? "2px solid #B5FF19" : "2px solid transparent",
                        color: tab === t.id ? "#B5FF19" : "#666", fontSize: 11, fontWeight: 600, fontFamily: F, cursor: "pointer",
                    }}>{t.label}</button>
                ))}
            </div>

            <div style={{ padding: "10px 14px", flex: 1, minHeight: 0, overflowY: "auto" }}>
                {tab === "options" && (
                    optionsStocks.length === 0
                        ? <Empty text="옵션 데이터 없음" />
                        : [...optionsStocks].sort((a, b) => (b.options_flow?.put_call_ratio || 0) - (a.options_flow?.put_call_ratio || 0)).map((r, i) => {
                            const o = r.options_flow || {}
                            const pcr = o.put_call_ratio || 0
                            const pcrColor = pcr > 1.5 ? "#EF4444" : pcr > 1 ? "#F59E0B" : pcr > 0.7 ? "#888" : "#22C55E"
                            return (
                                <div key={i} style={row}>
                                    <div style={{ flex: 1 }}>
                                        <span style={{ color: "#fff", fontSize: 12, fontWeight: 700, fontFamily: F }}>{r.name}</span>
                                        <span style={{ color: "#555", fontSize: 10, marginLeft: 6 }}>{r.ticker}</span>
                                    </div>
                                    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                                        <Gauge value={pcr} max={3} label="P/C" color={pcrColor} />
                                        <Gauge value={o.avg_iv || 0} max={100} label="IV" color="#A78BFA" suffix="%" />
                                        <Gauge value={o.total_oi ? Math.round(o.total_oi / 1000) : 0} max={500} label="OI(K)" color="#60A5FA" />
                                    </div>
                                </div>
                            )
                        })
                )}

                {tab === "short" && (
                    shortStocks.length === 0
                        ? <Empty text="공매도 데이터 없음" />
                        : [...shortStocks].sort((a, b) => {
                            const sa = a.short_interest?.short_pct ?? a.finnhub_metrics?.short_pct_float ?? 0
                            const sb = b.short_interest?.short_pct ?? b.finnhub_metrics?.short_pct_float ?? 0
                            return sb - sa
                        }).map((r, i) => {
                            const si = r.short_interest || {}
                            const fm = r.finnhub_metrics || {}
                            const shortPct = si.short_pct ?? fm.short_pct_float ?? fm.short_pct_outstanding
                            const dtc = si.days_to_cover ?? si.short_ratio
                            const shortColor = (shortPct || 0) > 20 ? "#EF4444" : (shortPct || 0) > 10 ? "#F59E0B" : "#22C55E"
                            return (
                                <div key={i} style={row}>
                                    <div style={{ flex: 1 }}>
                                        <span style={{ color: "#fff", fontSize: 12, fontWeight: 700, fontFamily: F }}>{r.name}</span>
                                        <span style={{ color: "#555", fontSize: 10, marginLeft: 6 }}>{r.ticker}</span>
                                    </div>
                                    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                                        {shortPct != null && <Gauge value={Number(shortPct.toFixed(1))} max={40} label="Short%" color={shortColor} suffix="%" />}
                                        {dtc != null && <Gauge value={Number(Number(dtc).toFixed(1))} max={10} label="Days" color="#60A5FA" />}
                                    </div>
                                </div>
                            )
                        })
                )}

                {tab === "preafter" && (
                    preAfterStocks.length === 0
                        ? <Empty text="장전·장후 데이터 없음 (장중에만 표시)" />
                        : preAfterStocks.map((r, i) => {
                            const pa = r.pre_after_market || {}
                            const preC = pa.pre_change_pct ?? 0
                            const afterC = pa.after_change_pct ?? 0
                            return (
                                <div key={i} style={row}>
                                    <div style={{ flex: 1 }}>
                                        <span style={{ color: "#fff", fontSize: 12, fontWeight: 700, fontFamily: F }}>{r.name}</span>
                                        <span style={{ color: "#555", fontSize: 10, marginLeft: 6 }}>{r.ticker}</span>
                                    </div>
                                    <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                                        {pa.pre_price != null && (
                                            <div style={{ textAlign: "center" }}>
                                                <div style={{ color: "#888", fontSize: 8, fontFamily: F }}>Pre</div>
                                                <div style={{ color: preC >= 0 ? "#22C55E" : "#EF4444", fontSize: 13, fontWeight: 800, fontFamily: F }}>
                                                    {preC >= 0 ? "+" : ""}{preC.toFixed(2)}%
                                                </div>
                                                <div style={{ color: "#555", fontSize: 9, fontFamily: F }}>${pa.pre_price.toFixed(2)}</div>
                                            </div>
                                        )}
                                        {pa.after_price != null && (
                                            <div style={{ textAlign: "center" }}>
                                                <div style={{ color: "#888", fontSize: 8, fontFamily: F }}>After</div>
                                                <div style={{ color: afterC >= 0 ? "#22C55E" : "#EF4444", fontSize: 13, fontWeight: 800, fontFamily: F }}>
                                                    {afterC >= 0 ? "+" : ""}{afterC.toFixed(2)}%
                                                </div>
                                                <div style={{ color: "#555", fontSize: 9, fontFamily: F }}>${pa.after_price.toFixed(2)}</div>
                                            </div>
                                        )}
                                    </div>
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

USFlowPanel.defaultProps = { dataUrl: DATA_URL }
addPropertyControls(USFlowPanel, {
    dataUrl: { type: ControlType.String, title: "JSON URL", defaultValue: DATA_URL },
})

const card: React.CSSProperties = {
    width: "100%", height: "100%", minHeight: 320, background: "#0A0A0A", borderRadius: 16,
    border: "1px solid #222", overflow: "hidden",
    display: "flex", flexDirection: "column", fontFamily: F,
}
const header: React.CSSProperties = {
    padding: "14px 16px", borderBottom: "1px solid #222",
    display: "flex", justifyContent: "space-between", alignItems: "center",
}
const row: React.CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "10px 0", borderBottom: "1px solid #1A1A1A", gap: 12,
}
