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
            <div style={{ flex: 1, height: 3, background: C.bgElevated, borderRadius: 2, position: "relative" }}>
                <div style={{
                    height: "100%", width: `${barW}%`, background: color, borderRadius: 2,
                    position: "absolute", left: pct >= 0 ? "50%" : undefined, right: pct < 0 ? "50%" : undefined,
                }} />
                <div style={{ position: "absolute", left: "50%", top: -2, height: 8, width: 1, background: "#444" }} />
            </div>
            <span style={{ color, fontSize: 12, fontWeight: 800, fontFamily: F, minWidth: 38, textAlign: "right" }}>
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
                <span style={{ color: C.textTertiary, fontSize: 13, fontFamily: F }}>컨센서스 로딩 중...</span>
            </div>
        )
    }

    return (
        <div style={card}>
            <div style={header}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 16, fontWeight: 800, color: C.textPrimary, fontFamily: F }}>📊 Analyst Consensus</span>
                    {strongBuys > 0 && (
                        <span style={{ background: "#0D2A0D", color: "#22C55E", fontSize: 12, fontWeight: 700, padding: "3px 8px", borderRadius: 6, fontFamily: F }}>
                            Strong Buy {strongBuys}건
                        </span>
                    )}
                </div>
                <span style={{ color: C.textTertiary, fontSize: 12, fontFamily: F }}>{withConsensus.length}종목</span>
            </div>

            <div style={{ display: "flex", borderBottom: `1px solid ${C.border}`, padding: "0 14px" }}>
                {([
                    { id: "upside" as const, label: "업사이드순" },
                    { id: "buy_ratio" as const, label: "Buy비율순" },
                    { id: "name" as const, label: "이름순" },
                ]).map((t) => (
                    <button key={t.id} onClick={() => setSort(t.id)} style={{
                        padding: "8px 10px", background: "none", border: "none",
                        borderBottom: sort === t.id ? "2px solid #B5FF19" : "2px solid transparent",
                        color: sort === t.id ? "#B5FF19" : "#666", fontSize: 12, fontWeight: 600, fontFamily: F, cursor: "pointer",
                    }}>{t.label}</button>
                ))}
            </div>

            <div style={{ padding: "6px 14px 14px", maxHeight: 440, overflowY: "auto" }}>
                {sorted.length === 0 ? (
                    <div style={{ padding: 24, textAlign: "center", color: C.textTertiary, fontSize: 12, fontFamily: F }}>컨센서스 데이터 없음</div>
                ) : sorted.map((r, i) => {
                    const c = r.analyst_consensus
                    const total = c.buy + (c.hold || 0) + (c.sell || 0)
                    const buyRatio = total > 0 ? ((c.buy / total) * 100).toFixed(0) : "—"
                    const upside = c.upside_pct || 0
                    return (
                        <div key={i} style={row}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <div style={{ flex: 1 }}>
                                    <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: F }}>{r.name}</span>
                                    <span style={{ color: C.textTertiary, fontSize: 12, marginLeft: 6, fontFamily: F }}>{r.ticker}</span>
                                    <span style={{ color: C.textTertiary, fontSize: 12, marginLeft: 6, fontFamily: F }}>
                                        ${r.price?.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </span>
                                </div>
                            </div>
                            <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 6 }}>
                                <div>
                                    <div style={{ color: C.textTertiary, fontSize: 8, fontFamily: F, marginBottom: 2 }}>Rating</div>
                                    <RatingBar buy={c.buy} hold={c.hold || 0} sell={c.sell || 0} />
                                    <div style={{ display: "flex", gap: 6, marginTop: 2 }}>
                                        <span style={{ color: "#22C55E", fontSize: 8, fontWeight: 700, fontFamily: F }}>B:{c.buy}</span>
                                        <span style={{ color: "#F59E0B", fontSize: 8, fontWeight: 700, fontFamily: F }}>H:{c.hold || 0}</span>
                                        <span style={{ color: "#EF4444", fontSize: 8, fontWeight: 700, fontFamily: F }}>S:{c.sell || 0}</span>
                                        <span style={{ color: C.textSecondary, fontSize: 8, fontFamily: F }}>({buyRatio}% Buy)</span>
                                    </div>
                                </div>
                                <div style={{ textAlign: "center" }}>
                                    <div style={{ color: C.textTertiary, fontSize: 8, fontFamily: F, marginBottom: 2 }}>목표가</div>
                                    <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, fontFamily: F }}>
                                        ${c.target_mean?.toLocaleString("en-US", { maximumFractionDigits: 0 })}
                                    </div>
                                    <div style={{ color: C.textTertiary, fontSize: 8, fontFamily: F }}>
                                        {c.target_low ? `$${c.target_low.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : ""}
                                        {c.target_low || c.target_high ? " ~ " : ""}
                                        {c.target_high ? `$${c.target_high.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : ""}
                                    </div>
                                </div>
                                <div style={{ textAlign: "right" }}>
                                    <div style={{ color: C.textTertiary, fontSize: 8, fontFamily: F, marginBottom: 2 }}>Upside</div>
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
    width: "100%", background: C.bgPage, borderRadius: 16,
    border: `1px solid ${C.border}`, overflow: "hidden",
    display: "flex", flexDirection: "column", fontFamily: F,
}
const header: React.CSSProperties = {
    padding: "14px 16px", borderBottom: `1px solid ${C.border}`,
    display: "flex", justifyContent: "space-between", alignItems: "center",
}
const row: React.CSSProperties = {
    padding: "10px 0", borderBottom: `1px solid ${C.border}`,
}
