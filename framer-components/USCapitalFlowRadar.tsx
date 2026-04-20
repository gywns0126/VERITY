import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useMemo, useState } from "react"

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


const F = "'Inter', 'Pretendard', -apple-system, sans-serif"
const DATA_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"

function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    return `${u}${u.includes("?") ? "&" : "?"}_=${Date.now()}`
}

function fetchJson(url: string, signal?: AbortSignal): Promise<any> {
    return fetch(bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((t) => JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
}

interface Props { dataUrl: string }

interface Axis {
    key: string
    label: string
    icon: string
    value: number
    raw: string
    color: string
    signal: string
}

const FLOW_LEVELS: { min: number; label: string; color: string; msg: string }[] = [
    { min: 75, label: "STRONG BUY", color: "#B5FF19", msg: "강한 매수 수급 — 적극 진입 가능" },
    { min: 60, label: "BUY LEAN", color: "#22C55E", msg: "매수 우위 수급 — 전략적 진입" },
    { min: 45, label: "NEUTRAL", color: "#F59E0B", msg: "중립 수급 — 방향 관찰 필요" },
    { min: 30, label: "SELL LEAN", color: "#F97316", msg: "매도 우위 수급 — 신규 진입 보수적" },
    { min: 0, label: "STRONG SELL", color: "#EF4444", msg: "강한 매도 수급 — 현금 비중 확대" },
]

function getFlowLevel(score: number) {
    return FLOW_LEVELS.find((l) => score >= l.min) || FLOW_LEVELS[FLOW_LEVELS.length - 1]
}

function clamp(v: number, lo: number, hi: number) { return Math.max(lo, Math.min(hi, v)) }

export default function USCapitalFlowRadar(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    const allRecs: any[] = data?.recommendations || []
    const allHolds: any[] = data?.vams?.holdings || data?.holdings || []

    const usStocks = useMemo(() => {
        const combined = [...allRecs, ...allHolds]
        const seen = new Set<string>()
        return combined.filter((s) => {
            const t = (s.ticker || "").toUpperCase()
            if (!t || seen.has(t)) return false
            seen.add(t)
            const isUS = s.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(s.market || "")
            return isUS
        })
    }, [allRecs, allHolds])

    const agg = useMemo(() => {
        if (usStocks.length === 0) return null

        let insiderSum = 0, insiderN = 0
        let instSum = 0, instN = 0
        let buyTotal = 0, holdTotal = 0, sellTotal = 0, analystN = 0
        let pcrSum = 0, pcrN = 0
        let shortSum = 0, shortN = 0
        let surpriseSum = 0, surpriseN = 0
        const signals: string[] = []

        for (const s of usStocks) {
            const insider = s.insider_sentiment || {}
            if (insider.mspr != null) { insiderSum += insider.mspr; insiderN++ }

            const inst = s.institutional_ownership || {}
            if (inst.change_pct != null) { instSum += inst.change_pct; instN++ }

            const con = s.analyst_consensus || {}
            if (con.buy != null) { buyTotal += con.buy; holdTotal += (con.hold || 0); sellTotal += (con.sell || 0); analystN++ }

            const opts = s.options_flow || {}
            if (opts.put_call_ratio != null) { pcrSum += opts.put_call_ratio; pcrN++ }

            const si = s.short_interest || {}
            const fm = s.finnhub_metrics || {}
            const sp = si.short_pct ?? fm.short_pct_float ?? fm.short_pct_outstanding
            if (sp != null) { shortSum += sp; shortN++ }

            const earn = (s.earnings_surprises || [])[0]
            if (earn?.surprise_pct != null) { surpriseSum += earn.surprise_pct; surpriseN++ }
        }

        const avgMspr = insiderN > 0 ? insiderSum / insiderN : 0
        const avgInstChg = instN > 0 ? instSum / instN : 0
        const totalAnalysts = buyTotal + holdTotal + sellTotal
        const buyRatio = totalAnalysts > 0 ? buyTotal / totalAnalysts : 0
        const avgPcr = pcrN > 0 ? pcrSum / pcrN : 0
        const avgShort = shortN > 0 ? shortSum / shortN : 0
        const avgSurprise = surpriseN > 0 ? surpriseSum / surpriseN : 0

        const dataSourceCount = [insiderN, instN, analystN, pcrN, shortN, surpriseN].filter((n) => n > 0).length

        const insiderScore = insiderN > 0 ? clamp(50 + avgMspr * 5, 0, 100) : 50
        const instScore = instN > 0 ? clamp(50 + avgInstChg * 3, 0, 100) : 50
        const analystScore = analystN > 0 ? clamp(buyRatio * 100, 0, 100) : 50
        const optionsScore = pcrN > 0 ? clamp(100 - avgPcr * 50, 0, 100) : 50
        const shortScore = shortN > 0 ? clamp(100 - avgShort * 2, 0, 100) : 50
        const earningsScore = surpriseN > 0 ? clamp(50 + avgSurprise * 2, 0, 100) : 50

        const overall = dataSourceCount > 0
            ? Math.round(
                insiderScore * 0.15 + instScore * 0.15 + analystScore * 0.25 +
                optionsScore * 0.20 + shortScore * 0.10 + earningsScore * 0.15
            )
            : null

        if (avgMspr > 2) signals.push(`내부자 순매수 강세 (MSPR ${avgMspr.toFixed(1)})`)
        else if (avgMspr < -2) signals.push(`내부자 순매도 주의 (MSPR ${avgMspr.toFixed(1)})`)
        if (buyRatio > 0.7 && analystN > 0) signals.push(`애널리스트 ${Math.round(buyRatio * 100)}% 매수`)
        if (avgPcr > 1.2 && pcrN > 0) signals.push(`풋 우세 (P/C ${avgPcr.toFixed(2)}) — 약세 심리`)
        else if (avgPcr < 0.6 && pcrN > 0) signals.push(`콜 우세 (P/C ${avgPcr.toFixed(2)}) — 강세 심리`)
        if (avgShort > 15 && shortN > 0) signals.push(`공매도 과다 (${avgShort.toFixed(1)}%)`)
        if (avgSurprise > 5 && surpriseN > 0) signals.push(`실적 서프라이즈 +${avgSurprise.toFixed(1)}%`)

        return {
            overall,
            signals,
            counts: { insider: insiderN, inst: instN, analyst: analystN, options: pcrN, short: shortN, earnings: surpriseN },
            axes: [
                { key: "insider", label: "내부자", icon: "👤", value: insiderScore, raw: insiderN > 0 ? `MSPR ${avgMspr.toFixed(1)}` : "N/A", color: "#B5FF19", signal: avgMspr > 0 ? "매수" : avgMspr < 0 ? "매도" : "중립" },
                { key: "inst", label: "기관", icon: "🏛", value: instScore, raw: instN > 0 ? `${avgInstChg >= 0 ? "+" : ""}${avgInstChg.toFixed(1)}%` : "N/A", color: "#60A5FA", signal: avgInstChg > 1 ? "증가" : avgInstChg < -1 ? "감소" : "유지" },
                { key: "analyst", label: "애널리스트", icon: "📊", value: analystScore, raw: analystN > 0 ? `Buy ${Math.round(buyRatio * 100)}%` : "N/A", color: "#22C55E", signal: buyRatio > 0.6 ? "매수 우위" : buyRatio < 0.4 ? "매도 우위" : "혼조" },
                { key: "options", label: "옵션", icon: "🎯", value: optionsScore, raw: pcrN > 0 ? `P/C ${avgPcr.toFixed(2)}` : "N/A", color: "#A78BFA", signal: avgPcr < 0.7 ? "콜 우세" : avgPcr > 1.2 ? "풋 우세" : "균형" },
                { key: "short", label: "공매도", icon: "🐻", value: shortScore, raw: shortN > 0 ? `${avgShort.toFixed(1)}%` : "N/A", color: "#F97316", signal: avgShort > 15 ? "과다" : avgShort < 5 ? "적음" : "보통" },
                { key: "earnings", label: "실적", icon: "💰", value: earningsScore, raw: surpriseN > 0 ? `${avgSurprise >= 0 ? "+" : ""}${avgSurprise.toFixed(1)}%` : "N/A", color: "#FFD700", signal: avgSurprise > 5 ? "서프라이즈" : avgSurprise < -5 ? "쇼크" : "인라인" },
            ] as Axis[],
        }
    }, [usStocks])

    if (!data) {
        return (
            <div style={{ ...card, minHeight: 340, alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: C.textTertiary, fontSize: 13, fontFamily: F }}>US 자금 흐름 로딩 중...</span>
            </div>
        )
    }

    if (!agg || usStocks.length === 0) {
        return (
            <div style={{ ...card, minHeight: 200, alignItems: "center", justifyContent: "center", padding: 24 }}>
                <span style={{ color: C.textTertiary, fontSize: 13, fontFamily: F }}>US 종목 데이터 없음</span>
                <span style={{ color: C.textTertiary, fontSize: 10, fontFamily: F, marginTop: 4 }}>파이프라인에서 US 종목을 수집해야 합니다</span>
            </div>
        )
    }

    const hasScore = agg.overall != null
    const level = getFlowLevel(agg.overall ?? 50)

    return (
        <div style={card}>
            {/* Header */}
            <div style={header}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 16, fontWeight: 800, color: C.textPrimary, fontFamily: F }}>🇺🇸 US Flow Radar</span>
                    <span style={{ color: C.textTertiary, fontSize: 10, fontFamily: F }}>{usStocks.length}종목</span>
                </div>
                <span style={{
                    fontSize: 11, fontWeight: 800, padding: "3px 10px", borderRadius: 8,
                    border: `1px solid ${hasScore ? level.color : "#555"}40`, color: hasScore ? level.color : "#555", background: hasScore ? `${level.color}12` : "#111",
                    fontFamily: F,
                }}>
                    {hasScore ? `${level.label} ${agg.overall}` : "데이터 미수집"}
                </span>
            </div>

            {/* Radar chart */}
            <div style={{ display: "flex", justifyContent: "center", padding: "8px 0 4px" }}>
                <RadarChart axes={agg.axes} overall={agg.overall ?? 50} levelColor={hasScore ? level.color : "#555"} />
            </div>

            {/* Interpretation */}
            <div style={{
                padding: "10px 16px", borderTop: `1px solid ${hasScore ? level.color : "#333"}30`, borderBottom: `1px solid ${C.border}`,
                background: hasScore ? `${level.color}08` : "#0A0A0A",
            }}>
                {hasScore ? (
                    <>
                        <div style={{ color: level.color, fontSize: 12, fontWeight: 700, fontFamily: F }}>{level.msg}</div>
                        {agg.signals.length > 0 && (
                            <div style={{ color: C.textSecondary, fontSize: 11, fontFamily: F, marginTop: 3, lineHeight: 1.5 }}>
                                {agg.signals.join(" · ")}
                            </div>
                        )}
                    </>
                ) : (
                    <div style={{ color: C.textTertiary, fontSize: 12, fontWeight: 600, fontFamily: F }}>
                        Finnhub/Polygon 데이터 미수집 — full_us 실행 후 표시됩니다
                    </div>
                )}
            </div>

            {/* Axis detail grid */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6, padding: "10px 14px" }}>
                {agg.axes.map((ax) => (
                    <div key={ax.key} style={{
                        background: "#0D0D0D", borderRadius: 10, padding: "10px 10px",
                        border: `1px solid ${ax.color}25`,
                    }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 4 }}>
                            <span style={{ fontSize: 13 }}>{ax.icon}</span>
                            <span style={{ color: ax.color, fontSize: 10, fontWeight: 700, fontFamily: F }}>{ax.label}</span>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                            <span style={{ color: C.textPrimary, fontSize: 18, fontWeight: 900, fontFamily: F }}>{Math.round(ax.value)}</span>
                            <span style={{ color: C.textSecondary, fontSize: 9, fontFamily: F }}>{ax.raw}</span>
                        </div>
                        <div style={{ height: 3, background: C.bgElevated, borderRadius: 2, marginTop: 5 }}>
                            <div style={{ height: "100%", width: `${ax.value}%`, background: ax.color, borderRadius: 2 }} />
                        </div>
                        <div style={{ color: C.textTertiary, fontSize: 9, fontFamily: F, marginTop: 3 }}>{ax.signal}</div>
                    </div>
                ))}
            </div>
        </div>
    )
}

// ─── Hexagonal Radar SVG ──────────────────────────────────

function RadarChart({ axes, overall, levelColor }: { axes: Axis[]; overall: number; levelColor: string }) {
    const N = axes.length
    const W = 320, H = 280
    const CX = W / 2, CY = H / 2
    const R = 100

    const angleOf = (i: number) => (Math.PI * 2 * i) / N - Math.PI / 2

    const gridLevels = [0.25, 0.5, 0.75, 1.0]

    const polyPoints = (radius: number) =>
        Array.from({ length: N }, (_, i) => {
            const a = angleOf(i)
            return `${CX + Math.cos(a) * radius},${CY + Math.sin(a) * radius}`
        }).join(" ")

    const dataPoints = axes.map((ax, i) => {
        const a = angleOf(i)
        const r = (ax.value / 100) * R
        return { x: CX + Math.cos(a) * r, y: CY + Math.sin(a) * r }
    })

    const dataPath = dataPoints.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ") + " Z"

    const labelPoints = axes.map((_, i) => {
        const a = angleOf(i)
        return { x: CX + Math.cos(a) * (R + 28), y: CY + Math.sin(a) * (R + 28) }
    })

    return (
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
            {/* Grid polygons */}
            {gridLevels.map((l) => (
                <polygon key={l} points={polyPoints(R * l)} fill="none" stroke="#222" strokeWidth={l === 1 ? 1 : 0.5} />
            ))}

            {/* Axis lines */}
            {axes.map((_, i) => {
                const a = angleOf(i)
                return (
                    <line key={i}
                        x1={CX} y1={CY}
                        x2={CX + Math.cos(a) * R} y2={CY + Math.sin(a) * R}
                        stroke="#1A1A1A" strokeWidth={0.5}
                    />
                )
            })}

            {/* Data polygon fill + stroke */}
            <defs>
                <linearGradient id="usflow_grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={levelColor} stopOpacity={0.2} />
                    <stop offset="100%" stopColor={levelColor} stopOpacity={0.03} />
                </linearGradient>
            </defs>
            <path d={dataPath} fill="url(#usflow_grad)" stroke={levelColor} strokeWidth={1.8} strokeLinejoin="round" />

            {/* Data points */}
            {dataPoints.map((p, i) => (
                <circle key={i} cx={p.x} cy={p.y} r={3.5} fill={axes[i].color} stroke="#000" strokeWidth={1} />
            ))}

            {/* Axis labels */}
            {axes.map((ax, i) => {
                const lp = labelPoints[i]
                return (
                    <g key={ax.key}>
                        <text x={lp.x} y={lp.y - 5} textAnchor="middle" fill={ax.color} fontSize="10" fontWeight="700" fontFamily={F}>
                            {ax.icon} {ax.label}
                        </text>
                        <text x={lp.x} y={lp.y + 8} textAnchor="middle" fill="#888" fontSize="9" fontFamily={F}>
                            {Math.round(ax.value)}
                        </text>
                    </g>
                )
            })}

            {/* Center score */}
            <circle cx={CX} cy={CY} r={26} fill={`${levelColor}12`} stroke={`${levelColor}40`} strokeWidth={1} />
            <text x={CX} y={CY - 5} textAnchor="middle" fill={levelColor} fontSize="9" fontWeight="700" fontFamily={F}>
                FLOW
            </text>
            <text x={CX} y={CY + 12} textAnchor="middle" fill={levelColor} fontSize="16" fontWeight="900" fontFamily={F}>
                {overall}
            </text>
        </svg>
    )
}

// ─── Framer config ────────────────────────────────────────

USCapitalFlowRadar.defaultProps = { dataUrl: DATA_URL }

addPropertyControls(USCapitalFlowRadar, {
    dataUrl: { type: ControlType.String, title: "JSON URL", defaultValue: DATA_URL },
})

const card: React.CSSProperties = {
    width: "100%", background: C.bgElevated, borderRadius: 16,
    border: `1px solid ${C.border}`, overflow: "hidden",
    display: "flex", flexDirection: "column", fontFamily: F,
}
const header: React.CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "14px 16px", borderBottom: `1px solid ${C.border}`,
}
