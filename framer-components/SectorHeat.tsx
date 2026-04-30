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

function _bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    return `${u}${u.includes("?") ? "&" : "?"}_=${Date.now()}`
}

function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    return fetch(_bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((t) => JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
}

interface Props {
    dataUrl: string
    market: "kr" | "us"
}

export default function SectorHeat(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [expanded, setExpanded] = useState<string | null>(null)
    const [view, setView] = useState<"hot" | "cold" | "all" | "rotation">("hot")

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchPortfolioJson(dataUrl, ac.signal).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    const font = FONT
    const isUS = props.market === "us"
    const allSectors: any[] = data?.sectors || []
    const sectors: any[] = allSectors.filter((s: any) => isUS ? s.market === "US" : s.market !== "US")
    const rotation: any = data?.sector_rotation || {}
    // §U-4 sector_rotation_check — quadrant 정합성 드리프트 (KOSPI 만 측정 — 한국 탭에서만 표시)
    const rotationCheck: any = !isUS ? (data?.sector_rotation_check || {}) : {}
    const rotationDrift = rotationCheck?.consistency?.drift === true ? rotationCheck.consistency : null

    const filtered = (() => {
        if (view === "hot") return sectors.filter((s) => s.change_pct > 0).slice(0, 10)
        if (view === "cold") return [...sectors].sort((a, b) => a.change_pct - b.change_pct).filter((s) => s.change_pct < 0).slice(0, 10)
        return sectors.slice(0, 20)
    })()

    const heatColor = (heat: string) => {
        if (heat === "hot") return "#22C55E"
        if (heat === "warm") return "#86EFAC"
        if (heat === "cool") return "#FCA5A5"
        if (heat === "cold") return "#EF4444"
        return "#888"
    }

    const heatBg = (heat: string) => {
        if (heat === "hot") return "rgba(34,197,94,0.12)"
        if (heat === "warm") return "rgba(134,239,172,0.08)"
        if (heat === "cool") return "rgba(252,165,165,0.08)"
        if (heat === "cold") return "rgba(239,68,68,0.12)"
        return "rgba(136,136,136,0.06)"
    }

    const maxSectorPct = useMemo(
        () => Math.max(...sectors.map((s) => Math.abs(s.change_pct ?? 0)), 3),
        [sectors]
    )

    const barWidth = (pct: number) => `${Math.min(Math.abs(pct) / maxSectorPct * 100, 100)}%`

    const chgColor = (v: number) => v > 0 ? "#22C55E" : v < 0 ? "#EF4444" : "#888"

    if (!data) {
        return (
            <div style={{ ...card, minHeight: 160, alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: C.textSecondary, fontSize: 14, fontFamily: font }}>섹터 로딩 중...</span>
            </div>
        )
    }

    const hotCount = sectors.filter((s) => s.change_pct > 0).length
    const coldCount = sectors.filter((s) => s.change_pct < 0).length

    return (
        <div style={card}>
            {/* 헤더 */}
            <div style={header}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ color: C.textPrimary, fontSize: 15, fontWeight: 700, fontFamily: font }}>
                        {isUS ? "US Sector Heatmap" : "섹터 히트맵"}
                    </span>
                    <span style={{ color: "#22C55E", fontSize: 12, fontFamily: font }}>
                        상승 {hotCount}
                    </span>
                    <span style={{ color: "#EF4444", fontSize: 12, fontFamily: font }}>
                        하락 {coldCount}
                    </span>
                </div>
                <div style={{ display: "flex", gap: 4 }}>
                    {(["hot", "cold", "all", "rotation"] as const).map((v) => (
                        <button
                            key={v}
                            onClick={() => setView(v)}
                            style={{
                                padding: "4px 10px", borderRadius: 6, border: "none",
                                background: view === v ? "#B5FF19" : "#222",
                                color: view === v ? "#000" : "#888",
                                fontSize: 12, fontWeight: 600, fontFamily: font, cursor: "pointer",
                            }}
                        >
                            {v === "hot" ? "상승" : v === "cold" ? "하락" : v === "all" ? "전체" : "전략"}
                        </button>
                    ))}
                </div>
            </div>

            {/* §U-4 sector_rotation_check drift 알림 — 모든 view 에서 상단 표시 */}
            {!isUS && rotationDrift && (
                <div style={{ padding: "8px 16px" }}>
                    <div style={{ background: "rgba(245,158,11,0.08)", border: "1px solid #F59E0B40", borderRadius: 10, padding: "10px 12px" }}>
                        <div style={{ color: "#F59E0B", fontSize: 12, fontWeight: 800, fontFamily: font, marginBottom: 4 }}>
                            ⚠ 섹터 로테이션 vs Quadrant 정합성 드리프트
                        </div>
                        <div style={{ color: C.textPrimary, fontSize: 12, fontFamily: font, lineHeight: 1.5 }}>
                            현재: <b>{rotationDrift.quadrant_label || rotationDrift.quadrant || "—"}</b>
                            {" · 드리프트 "}{rotationDrift.drift_count}건
                        </div>
                        {Array.isArray(rotationDrift.top_in_unfavored) && rotationDrift.top_in_unfavored.length > 0 && (
                            <div style={{ color: "#FCA5A5", fontSize: 12, fontFamily: font, marginTop: 2 }}>
                                상위인데 unfavored: {rotationDrift.top_in_unfavored.map((t: any) => t.sector).join(", ")}
                            </div>
                        )}
                        {Array.isArray(rotationDrift.bottom_in_favored) && rotationDrift.bottom_in_favored.length > 0 && (
                            <div style={{ color: "#86EFAC", fontSize: 12, fontFamily: font, marginTop: 2 }}>
                                하위인데 favored: {rotationDrift.bottom_in_favored.map((b: any) => b.sector).join(", ")}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* 로테이션 전략 뷰 */}
            {view === "rotation" && rotation.cycle && (
                <div style={{ padding: "12px 16px" }}>
                    <div style={{ background: "#1A1A2E", borderRadius: 10, padding: "14px 16px", marginBottom: 12 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                            <span style={{ color: "#A78BFA", fontSize: 14, fontWeight: 800, fontFamily: font }}>
                                {rotation.cycle_label}
                            </span>
                        </div>
                        <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: font, lineHeight: "1.6" }}>
                            {rotation.cycle_desc}
                        </div>
                    </div>

                    {rotation.recommended_sectors?.length > 0 && (
                        <div style={{ marginBottom: 12 }}>
                            <div style={{ color: "#22C55E", fontSize: 12, fontWeight: 700, fontFamily: font, marginBottom: 8 }}>
                                추천 섹터
                            </div>
                            {rotation.recommended_sectors.map((s: any, i: number) => (
                                <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid #1a1a1a" }}>
                                    <div>
                                        <span style={{ color: "#ddd", fontSize: 13, fontFamily: font }}>{s.name}</span>
                                        <div style={{ color: C.textTertiary, fontSize: 12, fontFamily: font, marginTop: 2 }}>{s.reason}</div>
                                    </div>
                                    <span style={{ color: chgColor(s.change_pct || 0), fontSize: 13, fontWeight: 600, fontFamily: font }}>
                                        {(s.change_pct || 0) >= 0 ? "+" : ""}{(s.change_pct || 0).toFixed(2)}%
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}

                    {rotation.avoid_sectors?.length > 0 && (
                        <div>
                            <div style={{ color: "#EF4444", fontSize: 12, fontWeight: 700, fontFamily: font, marginBottom: 8 }}>
                                회피 섹터
                            </div>
                            {rotation.avoid_sectors.map((s: any, i: number) => (
                                <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid #1a1a1a" }}>
                                    <div>
                                        <span style={{ color: C.textSecondary, fontSize: 13, fontFamily: font }}>{s.name}</span>
                                        <div style={{ color: C.textTertiary, fontSize: 12, fontFamily: font, marginTop: 2 }}>{s.reason}</div>
                                    </div>
                                    <span style={{ color: chgColor(s.change_pct || 0), fontSize: 13, fontWeight: 600, fontFamily: font }}>
                                        {(s.change_pct || 0) >= 0 ? "+" : ""}{(s.change_pct || 0).toFixed(2)}%
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* 섹터 리스트 */}
            {view !== "rotation" && <div style={{ maxHeight: 500, overflowY: "auto" }}>
                {filtered.map((s: any, i: number) => {
                    const isExpanded = expanded === s.name
                    return (
                        <div key={i}>
                            <div
                                onClick={() => setExpanded(isExpanded ? null : s.name)}
                                style={{
                                    ...sectorRow,
                                    background: isExpanded ? "#1A1A1A" : "transparent",
                                    cursor: "pointer",
                                }}
                            >
                                <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1 }}>
                                    <span style={{
                                        width: 6, height: 6, borderRadius: 3,
                                        background: heatColor(s.heat),
                                    }} />
                                    <span style={{ color: "#ddd", fontSize: 13, fontWeight: 500, fontFamily: font, minWidth: 100 }}>
                                        {s.name}
                                    </span>
                                    <div style={{ flex: 1, height: 4, background: C.bgElevated, borderRadius: 2, position: "relative", overflow: "hidden" }}>
                                        <div style={{
                                            position: "absolute",
                                            [s.change_pct >= 0 ? "left" : "right"]: 0,
                                            top: 0, height: "100%",
                                            width: barWidth(s.change_pct),
                                            background: heatColor(s.heat),
                                            borderRadius: 2,
                                        }} />
                                    </div>
                                </div>
                                <span style={{ color: chgColor(s.change_pct ?? 0), fontSize: 13, fontWeight: 700, fontFamily: font, minWidth: 60, textAlign: "right" }}>
                                    {typeof s.change_pct === "number" ? `${s.change_pct >= 0 ? "+" : ""}${s.change_pct.toFixed(2)}%` : "—"}
                                </span>
                                <span style={{ color: C.textTertiary, fontSize: 12, marginLeft: 8, transition: "transform 0.2s", transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)" }}>›</span>
                            </div>

                            {/* 대표 종목 */}
                            {isExpanded && s.top_stocks && s.top_stocks.length > 0 && (
                                <div style={{ padding: "8px 16px 12px 32px", background: "#0D0D0D" }}>
                                    <div style={{ color: C.textTertiary, fontSize: 12, fontFamily: font, marginBottom: 6 }}>
                                        대표 종목
                                    </div>
                                    {s.top_stocks.map((st: any, j: number) => (
                                        <div key={j} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
                                            <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: font }}>{st.name}</span>
                                            <div style={{ display: "flex", gap: 12 }}>
                                                <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: font }}>
                                                    {isUS ? `$${st.price?.toLocaleString("en-US", {minimumFractionDigits:2, maximumFractionDigits:2}) || "—"}` : `${st.price?.toLocaleString() || "—"}원`}
                                                </span>
                                                <span style={{ color: chgColor(st.change_pct || 0), fontSize: 12, fontWeight: 600, fontFamily: font }}>
                                                    {(st.change_pct || 0) >= 0 ? "+" : ""}{(st.change_pct || 0).toFixed(2)}%
                                                </span>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )
                })}
            </div>}
        </div>
    )
}

SectorHeat.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
    market: "kr",
}

addPropertyControls(SectorHeat, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
    },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["KR 국장", "US 미장"],
        defaultValue: "kr",
    },
})

const card: React.CSSProperties = {
    width: "100%",
    background: C.bgElevated,
    borderRadius: 16,
    border: `1px solid ${C.border}`,
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    fontFamily: FONT,
}

const header: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "14px 16px",
    borderBottom: "1px solid #222",
}

const sectorRow: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    padding: "10px 16px",
    borderBottom: "1px solid #1a1a1a",
    transition: "background 0.15s",
}
