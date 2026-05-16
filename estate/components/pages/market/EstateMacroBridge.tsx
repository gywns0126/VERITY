import { addPropertyControls, ControlType } from "framer"
import React, { useState, useEffect } from "react"

/* ◆ ESTATE DESIGN TOKENS v1.1 (다크 + 골드 — 패밀리룩) ◆ */
const C = {
    bgPage: "#0A0908",
    bgCard: "#0F0D0A",
    bgElevated: "#16130E",
    bgInput: "#1F1B14",
    border: "transparent",
    borderStrong: "#3A3024",
    textPrimary: "#F2EFE9",
    textSecondary: "#A8A299",
    textTertiary: "#6B665E",
    textDisabled: "#4A453E",
    accent: "#B8864D",
    accentBright: "#D4A26B",
    accentSoft: "rgba(184,134,77,0.15)",
    success: "#22C55E",
    warn: "#F59E0B",
    danger: "#EF4444",
    info: "#5BA9FF",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
/* ◆ TOKENS END ◆ */

const ESTATE_API_BASE = "https://project-yw131.vercel.app"
const MACRO_BRIDGE_URL = `${ESTATE_API_BASE}/api/estate/macro-bridge`

/* ──────────────────────────────────────────────────────────────
 * EstateMacroBridge — ESTATE Tier 3 (Macro 페이지)
 *
 * 부동산 직결 매크로 4지표 + 룰 기반 LANDEX 방향성 해설.
 * VERITY 의 market_horizon (주식 트랙) 과 직교 — 부동산 valuation 관점.
 * ────────────────────────────────────────────────────────────── */

interface Indicator {
    label: string
    value: number | null
    unit: string
    as_of?: string | null
    narrative: string
    source?: string
    change_pct?: number | null
    yoy_pp?: number | null
    trend_1m_change?: number | null
}

interface BridgePayload {
    schema_version?: string
    fetched_at: string
    namespace: string
    scenario?: string
    collected_at?: string
    indicators: {
        korea_policy_rate: Indicator
        korea_gov_10y: Indicator
        usd_krw: Indicator
        vix: Indicator
    }
    overall_verdict: string
    pressure_count: number
    relief_count: number
}

const VERDICT_COLOR = (verdict: string): string => {
    if (verdict.startsWith("압박")) return C.danger
    if (verdict.startsWith("완화")) return C.success
    return C.warn
}

interface Props {
    apiUrlOverride?: string
}

const fmtValue = (v: number | null | undefined, decimals = 2): string =>
    v === null || v === undefined ? "—" : v.toLocaleString("ko-KR", { maximumFractionDigits: decimals })

export default function EstateMacroBridge(props: Props) {
    const url = (props.apiUrlOverride && props.apiUrlOverride.trim()) || MACRO_BRIDGE_URL

    const [payload, setPayload] = useState<BridgePayload | null>(null)
    const [loading, setLoading] = useState<boolean>(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        setError(null)
        fetch(url, { cache: "no-store" })
            .then(async (r) => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`)
                return (await r.json()) as BridgePayload
            })
            .then((d) => {
                if (cancelled) return
                setPayload(d)
                setLoading(false)
            })
            .catch((e) => {
                if (cancelled) return
                setError(String(e?.message || e))
                setPayload(null)
                setLoading(false)
            })
        return () => { cancelled = true }
    }, [url])

    return (
        <div
            style={{
                width: "100%",
                background: C.bgCard,
                borderRadius: R.lg,
                padding: 16,
                fontFamily: FONT,
                color: C.textPrimary,
                boxSizing: "border-box",
                border: `1px solid ${C.borderStrong}`,
            }}
        >
            {/* HEADER */}
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 4 }}>
                <span style={{ fontSize: 11, letterSpacing: 1.2, color: C.accent, fontFamily: FONT_MONO }}>
                    MACRO BRIDGE
                </span>
                <span style={{ fontSize: 11, color: C.textTertiary }}>
                    {payload?.fetched_at ? `갱신 ${payload.fetched_at.slice(5, 16).replace("T", " ")}` : ""}
                </span>
            </div>
            <div style={{ fontSize: 16, fontWeight: 600, color: C.textPrimary, marginBottom: 12 }}>
                매크로 → 부동산 영향
                <span style={{ fontSize: 12, fontWeight: 400, color: C.textSecondary, marginLeft: 8 }}>
                    4지표 · 룰 기반 v0
                </span>
            </div>

            {loading && <Skeleton height={220} />}

            {!loading && error && (
                <Placeholder text="매크로 다리 일시 불가" />
            )}

            {!loading && payload && (
                <>
                    {/* VERDICT */}
                    <div
                        style={{
                            background: C.bgElevated,
                            border: `1px solid ${VERDICT_COLOR(payload.overall_verdict)}`,
                            borderRadius: R.md,
                            padding: "10px 12px",
                            marginBottom: 12,
                        }}
                    >
                        <div style={{ fontSize: 10, color: C.textTertiary, fontFamily: FONT_MONO, marginBottom: 2 }}>
                            OVERALL VERDICT
                        </div>
                        <div style={{ fontSize: 13, color: VERDICT_COLOR(payload.overall_verdict), fontWeight: 600 }}>
                            {payload.overall_verdict}
                        </div>
                        <div style={{ fontSize: 10, color: C.textTertiary, marginTop: 4, fontFamily: FONT_MONO }}>
                            압박 {payload.pressure_count} · 완화 {payload.relief_count}
                        </div>
                    </div>

                    {/* 4 INDICATOR GRID */}
                    <div
                        style={{
                            display: "grid",
                            gridTemplateColumns: "1fr 1fr",
                            gap: 8,
                            marginBottom: 12,
                        }}
                    >
                        <IndicatorCard ind={payload.indicators.korea_policy_rate} />
                        <IndicatorCard ind={payload.indicators.korea_gov_10y} />
                        <IndicatorCard ind={payload.indicators.usd_krw} />
                        <IndicatorCard ind={payload.indicators.vix} />
                    </div>

                    {/* DISCLAIMER */}
                    <div
                        style={{
                            fontSize: 9,
                            color: C.textTertiary,
                            fontFamily: FONT,
                            lineHeight: 1.4,
                            paddingTop: 8,
                            borderTop: `1px dashed ${C.borderStrong}`,
                        }}
                    >
                        룰 기반 v0 자체 신호. LANDEX 시계열 cross-correlation 정량 = v1 후순위.
                        출처: ECOS (한국은행) / yfinance / FRED.
                    </div>
                </>
            )}
        </div>
    )
}

function IndicatorCard({ ind }: { ind: Indicator }) {
    const hasValue = ind.value !== null && ind.value !== undefined
    return (
        <div
            style={{
                background: C.bgElevated,
                border: `1px solid ${C.borderStrong}`,
                borderRadius: R.md,
                padding: "10px 12px",
                display: "flex",
                flexDirection: "column",
                gap: 4,
            }}
        >
            <div style={{ fontSize: 10, color: C.textTertiary, fontFamily: FONT_MONO }}>
                {ind.label}
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
                <span style={{ fontSize: 18, fontWeight: 600, color: C.accentBright, fontFamily: FONT_MONO }}>
                    {fmtValue(ind.value, ind.unit === "원" ? 0 : 2)}
                </span>
                <span style={{ fontSize: 11, color: C.textSecondary }}>{ind.unit}</span>
            </div>
            {hasValue && (
                <div style={{ fontSize: 9, color: C.textTertiary, fontFamily: FONT_MONO }}>
                    {ind.change_pct !== undefined && ind.change_pct !== null && (
                        <span style={{ color: ind.change_pct >= 0 ? C.success : C.danger }}>
                            {ind.change_pct >= 0 ? "+" : ""}
                            {ind.change_pct.toFixed(2)}%
                        </span>
                    )}
                    {ind.yoy_pp !== undefined && ind.yoy_pp !== null && (
                        <span style={{ color: ind.yoy_pp >= 0 ? C.danger : C.success, marginLeft: 6 }}>
                            YoY {ind.yoy_pp >= 0 ? "+" : ""}{ind.yoy_pp.toFixed(2)}pp
                        </span>
                    )}
                    {ind.trend_1m_change !== undefined && ind.trend_1m_change !== null && (
                        <span style={{ color: C.textTertiary, marginLeft: 6 }}>
                            1m {ind.trend_1m_change >= 0 ? "+" : ""}{ind.trend_1m_change.toFixed(2)}
                        </span>
                    )}
                </div>
            )}
            <div style={{ fontSize: 11, color: C.textPrimary, marginTop: 4, lineHeight: 1.4 }}>
                {ind.narrative}
            </div>
            <div style={{ fontSize: 9, color: C.textTertiary, fontFamily: FONT_MONO, marginTop: 2 }}>
                {ind.source ? `· ${ind.source}` : ""} {ind.as_of ? `· ${String(ind.as_of).slice(0, 10)}` : ""}
            </div>
        </div>
    )
}

function Skeleton({ height }: { height: number }) {
    return (
        <div
            style={{
                height,
                background: C.bgElevated,
                borderRadius: R.md,
                opacity: 0.5,
            }}
        />
    )
}

function Placeholder({ text }: { text: string }) {
    return (
        <div
            style={{
                padding: 24,
                textAlign: "center",
                color: C.textTertiary,
                fontSize: 11,
                background: C.bgElevated,
                borderRadius: R.md,
            }}
        >
            {text}
        </div>
    )
}

addPropertyControls(EstateMacroBridge, {
    apiUrlOverride: {
        type: ControlType.String,
        title: "API URL (override)",
        defaultValue: "",
        placeholder: MACRO_BRIDGE_URL,
    },
})
