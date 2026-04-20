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
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


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

const font = FONT
const BG = C.bgPage
const CARD = C.bgCard
const BORDER = C.border
const MUTED = C.textSecondary
const UP = C.success
const DOWN = C.danger
const WARN = C.caution
const BLUE = "#3B82F6"

interface YieldPoint { tenor: string; yield: number }
interface Props { dataUrl: string }

const TENOR_ORDER = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]

function sortCurve(data: YieldPoint[]): YieldPoint[] {
    const last = TENOR_ORDER.length
    return [...data].sort((a, b) => {
        const ia = TENOR_ORDER.indexOf(a.tenor)
        const ib = TENOR_ORDER.indexOf(b.tenor)
        return (ia === -1 ? last : ia) - (ib === -1 ? last : ib)
    })
}

const SHAPE_MAP: Record<string, { color: string; label: string }> = {
    normal:   { color: UP, label: "정상 (우상향)" },
    steep:    { color: UP, label: "가파른 우상향" },
    flat:     { color: WARN, label: "플래트닝" },
    inverted: { color: DOWN, label: "역전" },
    humped:   { color: WARN, label: "험프" },
    unknown:  { color: MUTED, label: "데이터 없음" },
}

function CurveChart({ current, shape }: { current: YieldPoint[]; shape: string }) {
    const W = 420, H = 160
    const PAD = { top: 16, right: 16, bottom: 28, left: 40 }
    const chartW = W - PAD.left - PAD.right
    const chartH = H - PAD.top - PAD.bottom

    if (!current || current.length < 2) return (
        <div style={{ height: H, display: "flex", alignItems: "center", justifyContent: "center", color: MUTED, fontSize: 12, fontFamily: font }}>
            데이터 부족
        </div>
    )

    const sorted = sortCurve(current)
    const yields = sorted.map((d) => d.yield)
    const minY = Math.min(...yields) - 0.1
    const maxY = Math.max(...yields) + 0.1
    const rangeY = maxY - minY || 0.1

    const xScale = (i: number) => PAD.left + (i / (sorted.length - 1)) * chartW
    const yScale = (v: number) => PAD.top + chartH - ((v - minY) / rangeY) * chartH

    const lineColor = shape === "inverted" ? DOWN : shape === "flat" ? WARN : BLUE

    const pathD = sorted.map((d, i) => `${i === 0 ? "M" : "L"} ${xScale(i).toFixed(1)} ${yScale(d.yield).toFixed(1)}`).join(" ")
    const fillD = pathD + ` L ${xScale(sorted.length - 1).toFixed(1)} ${(PAD.top + chartH).toFixed(1)} L ${xScale(0).toFixed(1)} ${(PAD.top + chartH).toFixed(1)} Z`
    const gradId = `yc-grad-${shape}`

    return (
        <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ overflow: "visible", display: "block" }}>
            <defs>
                <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={lineColor} stopOpacity={0.25} />
                    <stop offset="100%" stopColor={lineColor} stopOpacity={0.02} />
                </linearGradient>
            </defs>
            {[0, 0.25, 0.5, 0.75, 1].map((t, i) => {
                const yv = minY + rangeY * (1 - t)
                const y = yScale(yv)
                return (
                    <g key={i}>
                        <line x1={PAD.left} x2={PAD.left + chartW} y1={y} y2={y} stroke={BORDER} strokeWidth={1} />
                        <text x={PAD.left - 4} y={y + 3} textAnchor="end" fill={MUTED} fontSize={9} fontFamily={font}>{yv.toFixed(2)}</text>
                    </g>
                )
            })}
            <path d={fillD} fill={`url(#${gradId})`} />
            <path d={pathD} fill="none" stroke={lineColor} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
            {sorted.map((d, i) => (
                <g key={i}>
                    <circle cx={xScale(i)} cy={yScale(d.yield)} r={3.5} fill={lineColor} stroke={BG} strokeWidth={1.5} />
                    <text x={xScale(i)} y={PAD.top + chartH + 16} textAnchor="middle" fill={MUTED} fontSize={9} fontFamily={font}>{d.tenor}</text>
                    <title>{d.tenor}: {d.yield.toFixed(3)}%</title>
                </g>
            ))}
        </svg>
    )
}

export default function YieldCurvePanel(props: Props) {
    const { dataUrl } = props
    const [bonds, setBonds] = useState<any>(null)
    const [tab, setTab] = useState<"US" | "KR">("US")
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal)
            .then((d) => { if (!ac.signal.aborted) { setBonds(d.bonds); setLoading(false) } })
            .catch(() => { if (!ac.signal.aborted) setLoading(false) })
        return () => ac.abort()
    }, [dataUrl])

    const curveData = bonds?.yield_curves?.[tab.toLowerCase()]
    const curve: YieldPoint[] = curveData?.curve ?? []
    const shape: string = curveData?.curve_shape ?? "unknown"
    const s2y10y = bonds?.yield_curves?.us?.spread_2y_10y
    const s3m10y = bonds?.yield_curves?.us?.spread_3m_10y
    const sm = SHAPE_MAP[shape] || SHAPE_MAP.unknown

    return (
        <div style={wrap}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <span style={{ fontSize: 13, fontWeight: 800, color: C.textPrimary, fontFamily: font }}>수익률 곡선</span>
                <div style={{ display: "flex", background: CARD, borderRadius: 7, padding: 2, gap: 2, border: `1px solid ${BORDER}` }}>
                    {(["US", "KR"] as const).map((t) => (
                        <button key={t} onClick={() => setTab(t)} style={{
                            padding: "3px 14px", borderRadius: 6, fontSize: 12, fontWeight: 700,
                            cursor: "pointer", border: "none", fontFamily: font,
                            background: tab === t ? BLUE : "transparent",
                            color: tab === t ? "#FFF" : MUTED,
                            transition: "all 0.15s ease",
                        }}>{t}</button>
                    ))}
                </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 12, color: MUTED, fontFamily: font }}>현재 형태</span>
                <span style={{
                    fontSize: 12, fontWeight: 700, color: sm.color,
                    background: sm.color + "22", border: `1px solid ${sm.color}44`,
                    borderRadius: 6, padding: "1px 8px", fontFamily: font,
                }}>{sm.label}</span>
            </div>

            {loading ? (
                <div style={{ flex: 1, minHeight: 120, display: "flex", alignItems: "center", justifyContent: "center", color: MUTED, fontSize: 12, fontFamily: font }}>로딩 중...</div>
            ) : (
                <div style={{ flex: 1, minHeight: 0 }}>
                    <CurveChart current={curve} shape={shape} />
                </div>
            )}

            {tab === "US" && (
                <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                    {[
                        { label: "2Y — 10Y", val: s2y10y },
                        { label: "3M — 10Y", val: s3m10y },
                    ].map(({ label, val }) => {
                        const bps = val != null ? val * 100 : null
                        return (
                            <div key={label} style={{ flex: 1, background: CARD, borderRadius: 8, padding: "7px 8px", textAlign: "center" as const, border: `1px solid ${BORDER}` }}>
                                <div style={{ fontSize: 12, color: MUTED, marginBottom: 2, fontFamily: font }}>{label}</div>
                                <div style={{
                                    fontSize: 14, fontWeight: 800, fontVariantNumeric: "tabular-nums", fontFamily: font,
                                    color: bps != null && bps < 0 ? DOWN : UP,
                                }}>
                                    {bps != null ? `${bps > 0 ? "+" : ""}${bps.toFixed(1)}bp` : "—"}
                                </div>
                            </div>
                        )
                    })}
                </div>
            )}
        </div>
    )
}

YieldCurvePanel.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
}

addPropertyControls(YieldCurvePanel, {
    dataUrl: { type: ControlType.String, title: "JSON URL", defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json" },
})

const wrap: React.CSSProperties = { width: "100%", height: "100%", boxSizing: "border-box" as const, background: BG, borderRadius: 12, padding: 14, fontFamily: font, color: "#E5E5E5", display: "flex", flexDirection: "column" as const, overflow: "hidden" }
