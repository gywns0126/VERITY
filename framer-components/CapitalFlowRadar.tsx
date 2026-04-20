import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

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


function _bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    return fetch(_bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((txt) => JSON.parse(txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
}

interface Props {
    dataUrl: string
}

const O2_LEVELS: { min: number; label: string; color: string; msg: string }[] = [
    { min: 70, label: "HIGH", color: "#B5FF19", msg: "시장 산소 충분 — 적극적 진입 가능" },
    { min: 55, label: "NORMAL", color: "#22C55E", msg: "시장 안정권 — 기존 전략 유지" },
    { min: 40, label: "LOW", color: "#EAB308", msg: "O₂ 부족 주의 — 신규 진입 보수적" },
    { min: 25, label: "HYPOXIA", color: "#F97316", msg: "경고 — 현금 비중 확대 권고" },
    { min: 0, label: "CRITICAL", color: "#EF4444", msg: "산소 고갈 — 신규 매수 금지" },
]

function getO2(score: number) {
    return O2_LEVELS.find((l) => score >= l.min) || O2_LEVELS[O2_LEVELS.length - 1]
}

const SECTOR_META: Record<string, { label: string; labelEn: string; icon: string }> = {
    equities: { label: "주식", labelEn: "Equities", icon: "📈" },
    commodities: { label: "원자재", labelEn: "Commodities", icon: "🥇" },
    bonds: { label: "채권/달러", labelEn: "Bonds", icon: "💵" },
}

const SECTOR_COLORS: Record<string, string> = {
    equities: "#B5FF19",
    commodities: "#FFD700",
    bonds: "#60A5FA",
}

function clamp(v: number, min: number, max: number) {
    return Math.max(min, Math.min(max, v))
}

function nodeRadius(score: number): number {
    return clamp(28 + (score - 50) * 0.6, 20, 50)
}

export default function CapitalFlowRadar(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchPortfolioJson(dataUrl, ac.signal).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    const macro = data?.macro || {}
    const flow = macro.capital_flow || {}
    const mood = macro.market_mood || {}
    const score = mood.score ?? 50
    const o2 = getO2(score)

    const eq = flow.equities || {}
    const cm = flow.commodities || {}
    const bd = flow.bonds || {}
    const interp = flow.interpretation || "데이터 수집 중..."
    const flowDir = flow.flow_direction || ""

    const W = 360
    const H = 320
    const CX = W / 2
    const CY = H / 2

    const nodes: { key: string; x: number; y: number; data: any }[] = [
        { key: "equities", x: CX, y: 52, data: eq },
        { key: "commodities", x: 60, y: H - 52, data: cm },
        { key: "bonds", x: W - 60, y: H - 52, data: bd },
    ]

    const edges: { from: string; to: string }[] = [
        { from: "equities", to: "commodities" },
        { from: "commodities", to: "bonds" },
        { from: "bonds", to: "equities" },
    ]

    const nodeMap: Record<string, { x: number; y: number }> = {}
    for (const n of nodes) nodeMap[n.key] = { x: n.x, y: n.y }

    const flowParts = flowDir.split("_to_")
    const flowFrom = flowParts[0] || ""
    const flowTo = flowParts[1] || ""

    function arrowPath(fromKey: string, toKey: string): string {
        const a = nodeMap[fromKey]
        const b = nodeMap[toKey]
        if (!a || !b) return ""
        const dx = b.x - a.x
        const dy = b.y - a.y
        const len = Math.sqrt(dx * dx + dy * dy)
        const nx = dx / len
        const ny = dy / len
        const rA = nodeRadius(getScore(fromKey))
        const rB = nodeRadius(getScore(toKey))
        const x1 = a.x + nx * (rA + 6)
        const y1 = a.y + ny * (rA + 6)
        const x2 = b.x - nx * (rB + 6)
        const y2 = b.y - ny * (rB + 6)
        return `M${x1},${y1} L${x2},${y2}`
    }

    function getScore(key: string): number {
        if (key === "equities") return eq.score ?? 50
        if (key === "commodities") return cm.score ?? 50
        if (key === "bonds") return bd.score ?? 50
        return 50
    }

    function isActiveEdge(from: string, to: string): boolean {
        return (from === flowFrom && to === flowTo) || (to === flowFrom && from === flowTo)
    }

    function edgeDirection(from: string, to: string): boolean {
        return from === flowFrom && to === flowTo
    }

    const chgColor = (v: number) => (v > 0 ? "#22C55E" : v < 0 ? "#EF4444" : "#888")
    const fmtChg = (v: any) => typeof v === "number" && Number.isFinite(v) ? `${v >= 0 ? "+" : ""}${v.toFixed(2)}%` : "—"

    if (!data) {
        return (
            <div style={{ ...card, minHeight: 300, alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: C.textSecondary, fontSize: 14, fontFamily: font }}>자금 흐름 데이터 로딩 중...</span>
            </div>
        )
    }

    return (
        <div style={card}>
            <div style={header}>
                <span style={titleText}>자금 흐름 레이더</span>
                <span style={{ ...o2Badge, color: o2.color, borderColor: o2.color + "40", background: o2.color + "12" }}>
                    O₂ {score}
                </span>
            </div>

            <div style={{ display: "flex", justifyContent: "center", padding: "4px 0" }}>
                <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
                    {/* Triangle edges */}
                    {edges.map(({ from, to }) => {
                        const active = isActiveEdge(from, to)
                        const reversed = edgeDirection(to, from)
                        const pathId = `edge-${from}-${to}`
                        const path = reversed ? arrowPath(to, from) : arrowPath(from, to)
                        return (
                            <g key={pathId}>
                                <path
                                    d={path}
                                    stroke={active ? "#fff" : "#333"}
                                    strokeWidth={active ? 2 : 1}
                                    fill="none"
                                    strokeDasharray={active ? "none" : "4,4"}
                                    opacity={active ? 0.9 : 0.4}
                                />
                                {active && (
                                    <path
                                        d={path}
                                        stroke="none"
                                        fill="none"
                                        markerEnd="url(#arrowHead)"
                                    />
                                )}
                            </g>
                        )
                    })}

                    {/* Active flow arrow marker */}
                    <defs>
                        <marker id="arrowHead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
                            <polygon points="0 0, 8 3, 0 6" fill="#fff" />
                        </marker>
                    </defs>

                    {/* Active flow animated arrow */}
                    {flowFrom && flowTo && nodeMap[flowFrom] && nodeMap[flowTo] && (
                        <path
                            d={arrowPath(flowFrom, flowTo)}
                            stroke={SECTOR_COLORS[flowTo] || "#fff"}
                            strokeWidth={2.5}
                            fill="none"
                            markerEnd="url(#arrowHead)"
                            opacity={0.8}
                        />
                    )}

                    {/* Sector nodes */}
                    {nodes.map(({ key, x, y, data: sData }) => {
                        const r = nodeRadius(sData.score ?? 50)
                        const meta = SECTOR_META[key]
                        const color = SECTOR_COLORS[key]
                        const chg = sData.change_pct ?? 0
                        const isStrongest = key === flowTo
                        return (
                            <g key={key}>
                                {isStrongest && (
                                    <circle cx={x} cy={y} r={r + 6} fill="none" stroke={color} strokeWidth={1} opacity={0.3}>
                                        <animate attributeName="r" from={r + 4} to={r + 12} dur="2s" repeatCount="indefinite" />
                                        <animate attributeName="opacity" from="0.4" to="0" dur="2s" repeatCount="indefinite" />
                                    </circle>
                                )}
                                <circle cx={x} cy={y} r={r} fill={color + "18"} stroke={color} strokeWidth={1.5} />
                                <text x={x} y={y - 6} textAnchor="middle" fill="#fff" fontSize="11" fontWeight="800" fontFamily={font}>
                                    {meta.label}
                                </text>
                                <text x={x} y={y + 10} textAnchor="middle" fill={chgColor(chg)} fontSize="12" fontWeight="700" fontFamily={font}>
                                    {fmtChg(chg)}
                                </text>
                            </g>
                        )
                    })}

                    {/* Center O2 display */}
                    <circle cx={CX} cy={CY} r={24} fill={o2.color + "12"} stroke={o2.color + "40"} strokeWidth={1} />
                    <text x={CX} y={CY - 4} textAnchor="middle" fill={o2.color} fontSize="9" fontWeight="700" fontFamily={font}>
                        O₂
                    </text>
                    <text x={CX} y={CY + 10} textAnchor="middle" fill={o2.color} fontSize="14" fontWeight="900" fontFamily={font}>
                        {score}
                    </text>
                </svg>
            </div>

            {/* Interpretation banner */}
            <div style={{ ...interpBanner, background: o2.color + "0A", borderColor: o2.color + "30" }}>
                <span style={{ ...interpText, color: o2.color }}>{o2.msg}</span>
                <span style={interpSub}>{interp}</span>
            </div>

            {/* Sector detail grid */}
            <div style={detailGrid}>
                {(["equities", "commodities", "bonds"] as const).map((key) => {
                    const sData = flow[key] || {}
                    const meta = SECTOR_META[key]
                    const color = SECTOR_COLORS[key]
                    const chg = sData.change_pct ?? 0
                    const dominant = sData.dominant || "—"
                    const dominantLabel: Record<string, string> = {
                        gold: "금", silver: "은", copper: "구리", wti_oil: "원유",
                        us_10y: "미10Y", us_2y: "미2Y",
                        sp500: "S&P500", nasdaq: "NASDAQ",
                    }
                    return (
                        <div key={key} style={{ ...detailCell, borderColor: color + "30" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                                <span style={{ ...detailIcon, color }}>{meta.icon}</span>
                                <span style={{ ...detailLabel, color }}>{meta.label}</span>
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                                <span style={{ ...detailScore }}>{sData.score ?? "—"}</span>
                                <span style={{ ...detailChg, color: chgColor(chg) }}>{fmtChg(chg)}</span>
                            </div>
                            <div style={detailDominant}>
                                주도: {dominantLabel[dominant] || dominant}
                                {key === "bonds" && sData.usd_change_pct != null && (
                                    <span style={{ marginLeft: 6, color: chgColor(sData.usd_change_pct) }}>
                                        USD/KRW {fmtChg(sData.usd_change_pct)}
                                    </span>
                                )}
                            </div>
                        </div>
                    )
                })}
            </div>
        </div>
    )
}

CapitalFlowRadar.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
}

addPropertyControls(CapitalFlowRadar, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    },
})

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"

const card: React.CSSProperties = {
    width: "100%",
    background: C.bgElevated,
    borderRadius: 16,
    border: `1px solid ${C.border}`,
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    fontFamily: font,
}

const header: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "14px 16px",
    borderBottom: `1px solid ${C.border}`,
}

const titleText: React.CSSProperties = {
    color: C.textPrimary,
    fontSize: 15,
    fontWeight: 700,
    fontFamily: font,
}

const o2Badge: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 800,
    padding: "3px 10px",
    borderRadius: 8,
    border: "1px solid",
    fontFamily: font,
}

const interpBanner: React.CSSProperties = {
    padding: "10px 16px",
    borderTop: "1px solid",
    borderBottom: `1px solid ${C.border}`,
    display: "flex",
    flexDirection: "column",
    gap: 2,
}

const interpText: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 700,
    fontFamily: font,
}

const interpSub: React.CSSProperties = {
    fontSize: 11,
    color: C.textSecondary,
    fontFamily: font,
}

const detailGrid: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: 8,
    padding: "12px 16px",
}

const detailCell: React.CSSProperties = {
    background: "#0D0D0D",
    borderRadius: 10,
    padding: "10px 12px",
    border: "1px solid",
}

const detailIcon: React.CSSProperties = {
    fontSize: 14,
}

const detailLabel: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 700,
    fontFamily: font,
}

const detailScore: React.CSSProperties = {
    color: C.textPrimary,
    fontSize: 20,
    fontWeight: 900,
    fontFamily: font,
}

const detailChg: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 700,
    fontFamily: font,
}

const detailDominant: React.CSSProperties = {
    fontSize: 10,
    color: C.textTertiary,
    marginTop: 4,
    fontFamily: font,
}
