import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"

function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

function fetchJson(url: string, signal?: AbortSignal): Promise<any> {
    return fetch(bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((txt) => JSON.parse(txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
}

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"
const BG = "#000"
const CARD = "#111"
const BORDER = "#222"
const ACCENT = "#B5FF19"
const MUTED = "#8B95A1"
const UP = "#22C55E"
const DOWN = "#EF4444"
const WARN = "#F59E0B"

interface YieldPoint { tenor: string; yield: number }

interface Props { dataUrl: string }

const SHAPE_STYLE: Record<string, { color: string; label: string }> = {
    normal:   { color: UP, label: "정상" },
    steep:    { color: UP, label: "가파름" },
    flat:     { color: WARN, label: "플랫" },
    inverted: { color: DOWN, label: "역전" },
    humped:   { color: WARN, label: "험프" },
    unknown:  { color: MUTED, label: "—" },
}

const RISK_COLOR: Record<string, string> = {
    LOW: UP, MODERATE: "#3B82F6", HIGH: WARN, EXTREME: DOWN,
}

function Badge({ text, color }: { text: string; color: string }) {
    return (
        <span style={{
            background: color + "22", color, border: `1px solid ${color}44`,
            borderRadius: 5, padding: "1px 7px", fontSize: 10, fontWeight: 700,
            letterSpacing: 0.3,
        }}>{text}</span>
    )
}

function MiniCurve({ data, label, shape }: { data: YieldPoint[]; label: string; shape: string }) {
    if (!data || data.length === 0) return null
    const vals = data.map((d) => d.yield)
    const mx = Math.max(...vals), mn = Math.min(...vals)
    const rng = mx - mn || 0.1
    const s = SHAPE_STYLE[shape] || SHAPE_STYLE.unknown

    return (
        <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: "#E5E5E5", fontFamily: font }}>{label}</span>
                <Badge text={s.label} color={s.color} />
            </div>
            <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 50 }}>
                {data.map((d, i) => {
                    const h = ((d.yield - mn) / rng) * 38 + 10
                    return (
                        <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 1 }}>
                            <div style={{
                                width: "100%", height: h, borderRadius: "2px 2px 0 0",
                                background: `linear-gradient(180deg, ${s.color}cc, ${s.color}33)`,
                                transition: "height 0.4s ease",
                            }} />
                            <span style={{ fontSize: 8, color: MUTED, whiteSpace: "nowrap", fontFamily: font }}>{d.tenor}</span>
                        </div>
                    )
                })}
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
                <span style={{ fontSize: 10, color: MUTED, fontFamily: font }}>{mn.toFixed(2)}%</span>
                <span style={{ fontSize: 10, color: MUTED, fontFamily: font }}>{mx.toFixed(2)}%</span>
            </div>
        </div>
    )
}

function SpreadRow({ label, value }: { label: string; value: number | null | undefined }) {
    if (value == null) return null
    const bps = value * 100
    const color = bps < -10 ? DOWN : bps < 25 ? WARN : UP
    return (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "5px 0", borderBottom: `1px solid ${BORDER}` }}>
            <span style={{ fontSize: 12, color: MUTED, fontFamily: font }}>{label}</span>
            <span style={{ fontSize: 13, fontWeight: 700, color, fontVariantNumeric: "tabular-nums", fontFamily: font }}>
                {bps > 0 ? "+" : ""}{bps.toFixed(1)}bp
            </span>
        </div>
    )
}

export default function BondDashboard(props: Props) {
    const { dataUrl } = props
    const [bonds, setBonds] = useState<any>(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal)
            .then((d) => { if (!ac.signal.aborted) { setBonds(d.bonds ?? null); setLoading(false) } })
            .catch(() => { if (!ac.signal.aborted) setLoading(false) })
        return () => ac.abort()
    }, [dataUrl])

    if (loading) return <div style={{ ...wrap, justifyContent: "center", alignItems: "center", textAlign: "center" as const, color: MUTED, fontSize: 13, fontFamily: font }}>채권 데이터 로딩 중...</div>
    if (!bonds) return <div style={{ ...wrap, justifyContent: "center", alignItems: "center", textAlign: "center" as const, color: DOWN, fontSize: 12, fontFamily: font }}>채권 데이터 없음</div>

    const yc = bonds.yield_curves || {}
    const credit = bonds.credit_spreads || {}
    const krCorp = bonds.kr_corp_spreads || {}
    const alerts = bonds.inversion_alerts || []
    const regime = bonds.bond_regime || {}
    const regimeCurve = regime.curve_shape || regime.us_curve_shape || null
    const regimeRecession = !!(regime.recession_signal ?? regime.is_recession_signal)

    return (
        <div style={wrap}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                <span style={{ fontSize: 14, fontWeight: 800, color: "#FFF", fontFamily: font }}>채권 시장</span>
                <span style={{ fontSize: 10, color: MUTED, fontFamily: font }}>
                    {bonds.updated_at ? new Date(bonds.updated_at).toLocaleString("ko-KR") : ""}
                </span>
            </div>

            {alerts.length > 0 && (
                <div style={{ background: DOWN + "18", border: `1px solid ${DOWN}44`, borderRadius: 8, padding: "7px 10px", marginBottom: 10 }}>
                    {alerts.map((a: any, i: number) => (
                        <div key={i} style={{ fontSize: 11, color: "#FCA5A5", lineHeight: 1.5, fontFamily: font }}>! {a.message}</div>
                    ))}
                </div>
            )}

            {(regimeCurve || regimeRecession) && (
                <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 10, flexWrap: "wrap" as const }}>
                    <span style={{ fontSize: 10, color: MUTED, fontFamily: font }}>채권 레짐</span>
                    {regimeCurve && (
                        <Badge
                            text={SHAPE_STYLE[regimeCurve]?.label || regimeCurve}
                            color={SHAPE_STYLE[regimeCurve]?.color || MUTED}
                        />
                    )}
                    {regimeRecession && <Badge text="경기침체 신호" color={DOWN} />}
                </div>
            )}

            <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
                <MiniCurve data={yc.kr?.curve ?? []} label="한국 국고채" shape={yc.kr?.curve_shape ?? "unknown"} />
                <MiniCurve data={yc.us?.curve ?? []} label="미국 국채" shape={yc.us?.curve_shape ?? "unknown"} />
            </div>

            <div style={card}>
                <div style={secTitle}>미국 수익률 스프레드</div>
                <SpreadRow label="2Y — 10Y" value={yc.us?.spread_2y_10y} />
                <SpreadRow label="3M — 10Y" value={yc.us?.spread_3m_10y} />
            </div>

            <div style={card}>
                <div style={secTitle}>미국 신용 스프레드 (OAS)</div>
                {[
                    { label: "IG (투자등급)", oas: credit.us_ig_oas, risk: credit.us_ig_risk },
                    { label: "HY (하이일드)", oas: credit.us_hy_oas, risk: credit.us_hy_risk },
                ].map((row) => (
                    <div key={row.label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "5px 0", borderBottom: `1px solid ${BORDER}` }}>
                        <span style={{ fontSize: 12, color: MUTED, fontFamily: font }}>{row.label}</span>
                        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                            <span style={{ fontSize: 13, fontWeight: 700, color: "#E5E5E5", fontVariantNumeric: "tabular-nums", fontFamily: font }}>
                                {row.oas != null ? `${(row.oas * 100).toFixed(0)}bp` : "—"}
                            </span>
                            {row.risk && <Badge text={row.risk} color={RISK_COLOR[row.risk] || MUTED} />}
                        </div>
                    </div>
                ))}
            </div>

            {krCorp?.grades && Object.keys(krCorp.grades).length > 0 && (
                <div style={card}>
                    <div style={secTitle}>한국 회사채 스프레드 <span style={{ fontSize: 9, color: "#555" }}>vs 국고채3Y</span></div>
                    {Object.entries(krCorp.grades).map(([grade, d]: [string, any]) => (
                        <div key={grade} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "4px 0", borderBottom: `1px solid ${BORDER}` }}>
                            <span style={{ fontSize: 12, fontWeight: 700, color: "#E5E5E5", width: 40, fontFamily: font }}>{grade}</span>
                            <span style={{ fontSize: 11, color: MUTED, fontVariantNumeric: "tabular-nums", fontFamily: font }}>
                                {d.yield != null ? `${d.yield.toFixed(2)}%` : "—"}
                            </span>
                            <span style={{
                                fontSize: 11, fontVariantNumeric: "tabular-nums", fontFamily: font,
                                color: d.spread_vs_3y != null && d.spread_vs_3y > 2 ? WARN : MUTED,
                            }}>
                                +{d.spread_vs_3y != null ? (d.spread_vs_3y * 100).toFixed(0) : "—"}bp
                            </span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}

BondDashboard.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
}

addPropertyControls(BondDashboard, {
    dataUrl: { type: ControlType.String, title: "JSON URL", defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json" },
})

const wrap: React.CSSProperties = { width: "100%", height: "100%", boxSizing: "border-box" as const, background: BG, borderRadius: 12, padding: 14, fontFamily: font, color: "#E5E5E5", display: "flex", flexDirection: "column" as const, overflow: "auto" as const }
const card: React.CSSProperties = { background: CARD, borderRadius: 8, padding: "9px 11px", marginBottom: 8, border: `1px solid ${BORDER}` }
const secTitle: React.CSSProperties = { fontSize: 10, fontWeight: 700, color: MUTED, textTransform: "uppercase" as const, letterSpacing: 0.8, marginBottom: 6, fontFamily: font }
