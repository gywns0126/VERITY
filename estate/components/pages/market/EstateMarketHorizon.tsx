// EstateMarketHorizon — ESTATE 5축 종합 verdict synthesizer (market/ 폴더)
//
// VERITY MarketHorizon V2.1 의 ESTATE 짝. brain synthesizer 역할.
// 5축 (거시 / 사이클 / 정책 / 지역 / 섹터) 가중평균 → 단일 verdict + narrative.
//
// Backend: api/builders/estate_market_horizon_builder.py
// Endpoint: /api/estate/market-horizon (vercel-api/api/estate_market_horizon.py)
// Cron: .github/workflows/estate_market_horizon.yml (월요일 KST 08:00)
//
// 의도 ([[feedback_brain_synthesizer_role]] 정합): 5 aux 분해 명시 + 1 brain verdict 우선.
// 사용자가 머릿속 종합 X — 시스템이 가중평균으로 단일 verdict 산출. raw 분해도 같이 노출.

import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"

/* ◆ ESTATE 패밀리룩 v3 — feedback_estate_design_familylook 정합 ◆ */
const C = {
    bgCard: "#0F0D0A", bgElevated: "#16130E", bgInput: "#1F1B14",
    borderStrong: "#3A3024",
    textPrimary: "#F2EFE9", textSecondary: "#A8A299", textTertiary: "#6B665E",
    accent: "#B8864D", accentBright: "#D4A26B", accentSoft: "rgba(184,134,77,0.15)",
    success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Menlo', monospace"
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
/* ◆ TOKENS END ◆ */

const ESTATE_API_BASE = "https://project-yw131.vercel.app"

type Verdict = "BULLISH" | "NEUTRAL" | "BEARISH" | "MIXED" | "UNAVAILABLE"

interface Axis {
    key?: string
    name: string
    weight: number
    verdict: Verdict
    as_of?: string
    stage?: string
    mean_landex?: number
    stdev_landex?: number
    n_gu?: number
    overview?: string
    sectors_breakdown?: { name: string; verdict: string }[]
    raw_indicators?: { name?: string; value?: any }[]
    _error?: string
    _fallback_reason?: string
}

interface MarketHorizonPayload {
    schema_version?: string
    generated_at: string
    verdict: Verdict
    weighted_score: number
    rationale: string
    narrative: string
    axes: Record<string, Axis>
    thresholds: {
        bullish: number
        bearish: number
        weights: Record<string, number>
    }
}

const VERDICT_META: Record<Verdict, { label: string; color: string }> = {
    BULLISH: { label: "강세", color: C.success },
    NEUTRAL: { label: "보합", color: C.textSecondary },
    BEARISH: { label: "약세", color: C.danger },
    MIXED: { label: "혼조", color: C.warn },
    UNAVAILABLE: { label: "부재", color: C.textTertiary },
}

const AXIS_ORDER = ["macro", "cycle", "policy", "region", "sector"] as const

interface Props {
    apiUrlOverride?: string
}

export default function EstateMarketHorizon(props: Props) {
    const base = (props.apiUrlOverride && props.apiUrlOverride.trim()) || ESTATE_API_BASE
    const [data, setData] = useState<MarketHorizonPayload | null>(null)
    const [err, setErr] = useState<string | null>(null)
    const [loading, setLoading] = useState<boolean>(true)
    const [expandedAxis, setExpandedAxis] = useState<string | null>(null)

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        setErr(null)
        fetch(`${base}/api/estate/market-horizon`)
            .then((r) => (r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`)))
            .then((d) => {
                if (cancelled) return
                if (d && d.generated_at && d.verdict && d.axes) {
                    setData(d as MarketHorizonPayload)
                } else {
                    setErr("invalid schema")
                }
                setLoading(false)
            })
            .catch((e) => {
                if (cancelled) return
                setErr(String(e))
                setLoading(false)
            })
        return () => {
            cancelled = true
        }
    }, [base])

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
                    MARKET HORIZON
                </span>
                <span style={{ fontSize: 11, color: C.textTertiary }}>
                    {data?.generated_at ? `갱신 ${data.generated_at.slice(5, 10)}` : ""}
                </span>
                <span style={{ marginLeft: "auto", fontSize: 10, color: C.textTertiary, fontFamily: FONT_MONO }}>
                    5축 가중 synthesizer
                </span>
            </div>
            <div style={{ fontSize: 16, fontWeight: 600, color: C.textPrimary, marginBottom: 14 }}>
                ESTATE 시장 종합 verdict
            </div>

            {/* CONTENT */}
            {loading && !data ? (
                <Skeleton height={260} />
            ) : err || !data ? (
                <Placeholder text="종합 verdict 일시 불가 (월요일 08:00 KST 첫 cron 후 활성)" />
            ) : (
                <>
                    {/* HERO — 메인 verdict + gauge + narrative */}
                    <HeroVerdict data={data} />

                    {/* 5축 분해 — horizontal cards */}
                    <div style={{ marginTop: 14, marginBottom: 10 }}>
                        <div style={{ fontSize: 9, color: C.textTertiary, fontFamily: FONT_MONO, marginBottom: 6, letterSpacing: 1 }}>
                            5축 분해 · 클릭 시 detail
                        </div>
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 6 }}>
                            {AXIS_ORDER.map((key) => {
                                const ax = data.axes[key]
                                if (!ax) return null
                                return (
                                    <AxisCard
                                        key={key}
                                        axisKey={key}
                                        axis={ax}
                                        selected={expandedAxis === key}
                                        onClick={() => setExpandedAxis((v) => (v === key ? null : key))}
                                    />
                                )
                            })}
                        </div>
                    </div>

                    {/* selected axis detail */}
                    {expandedAxis && data.axes[expandedAxis] && (
                        <AxisDetail axisKey={expandedAxis} axis={data.axes[expandedAxis]} />
                    )}

                    {/* rationale */}
                    <div
                        style={{
                            marginTop: 10,
                            background: C.bgElevated,
                            border: `1px solid ${C.borderStrong}`,
                            borderRadius: R.md,
                            padding: "8px 12px",
                            fontSize: 11,
                            color: C.textSecondary,
                            lineHeight: 1.5,
                        }}
                    >
                        <span style={{ color: C.accent, fontFamily: FONT_MONO, fontSize: 9, marginRight: 6 }}>
                            산식
                        </span>
                        {data.rationale}
                    </div>

                    {/* footer — 임계 + 가중치 메타 */}
                    <div
                        style={{
                            marginTop: 8,
                            fontSize: 9,
                            color: C.textTertiary,
                            fontFamily: FONT_MONO,
                            display: "flex",
                            gap: 8,
                            flexWrap: "wrap",
                        }}
                    >
                        <span>임계 BULLISH ≥ {data.thresholds.bullish}</span>
                        <span>· BEARISH ≤ {data.thresholds.bearish}</span>
                        <span>· {data.generated_at.slice(0, 10)}</span>
                    </div>
                </>
            )}
        </div>
    )
}

/* ─ HeroVerdict — 메인 verdict + gauge + narrative ─ */
function HeroVerdict({ data }: { data: MarketHorizonPayload }) {
    const meta = VERDICT_META[data.verdict]
    // gauge: -1 ~ +1 위치
    const pct = Math.max(0, Math.min(100, ((data.weighted_score + 1) / 2) * 100))

    return (
        <div
            style={{
                background: C.bgInput,
                border: `1px solid ${meta.color}`,
                borderRadius: R.md,
                padding: 14,
            }}
        >
            <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 10 }}>
                <span
                    style={{
                        fontSize: 22,
                        fontWeight: 700,
                        color: meta.color,
                        fontFamily: FONT_MONO,
                    }}
                >
                    {data.verdict}
                </span>
                <span style={{ fontSize: 12, color: C.textSecondary }}>
                    {meta.label}
                </span>
                <span
                    style={{
                        marginLeft: "auto",
                        fontSize: 16,
                        fontWeight: 600,
                        color: meta.color,
                        fontFamily: FONT_MONO,
                    }}
                >
                    {data.weighted_score >= 0 ? "+" : ""}{data.weighted_score.toFixed(2)}
                </span>
            </div>

            {/* gauge */}
            <div style={{ marginBottom: 10 }}>
                <div
                    style={{
                        position: "relative",
                        height: 14,
                        background: C.bgElevated,
                        borderRadius: R.pill,
                        border: `1px solid ${C.borderStrong}`,
                        overflow: "hidden",
                    }}
                >
                    {/* zone backgrounds */}
                    <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: "30%", background: "rgba(239,68,68,0.08)" }} />
                    <div style={{ position: "absolute", left: "30%", top: 0, bottom: 0, width: "40%", background: "rgba(168,162,153,0.05)" }} />
                    <div style={{ position: "absolute", left: "70%", top: 0, bottom: 0, width: "30%", background: "rgba(34,197,94,0.08)" }} />
                    {/* center marker */}
                    <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: C.borderStrong }} />
                    {/* threshold markers */}
                    <div style={{ position: "absolute", left: `${((data.thresholds.bearish + 1) / 2) * 100}%`, top: 0, bottom: 0, width: 1, background: C.danger, opacity: 0.4 }} />
                    <div style={{ position: "absolute", left: `${((data.thresholds.bullish + 1) / 2) * 100}%`, top: 0, bottom: 0, width: 1, background: C.success, opacity: 0.4 }} />
                    {/* needle */}
                    <div
                        style={{
                            position: "absolute",
                            left: `calc(${pct}% - 6px)`,
                            top: -3,
                            width: 12,
                            height: 20,
                            background: meta.color,
                            borderRadius: R.sm,
                            boxShadow: `0 0 6px ${meta.color}`,
                        }}
                    />
                </div>
                <div
                    style={{
                        display: "flex",
                        justifyContent: "space-between",
                        fontSize: 9,
                        fontFamily: FONT_MONO,
                        color: C.textTertiary,
                        marginTop: 4,
                    }}
                >
                    <span>−1 약세</span>
                    <span>0 중립</span>
                    <span>+1 강세</span>
                </div>
            </div>

            {/* narrative */}
            <div style={{ fontSize: 12, color: C.textPrimary, lineHeight: 1.5, fontStyle: "italic" }}>
                "{data.narrative}"
            </div>
        </div>
    )
}

/* ─ AxisCard — 1축 카드 (grid 안) ─ */
function AxisCard({
    axisKey, axis, selected, onClick,
}: {
    axisKey: string
    axis: Axis
    selected: boolean
    onClick: () => void
}) {
    const meta = VERDICT_META[axis.verdict]
    return (
        <button
            onClick={onClick}
            style={{
                background: selected ? C.accentSoft : C.bgElevated,
                border: `1px solid ${selected ? C.accent : C.borderStrong}`,
                borderRadius: R.md,
                padding: 8,
                cursor: "pointer",
                textAlign: "center",
                color: C.textPrimary,
                fontFamily: FONT,
                transition: "all 150ms ease",
                display: "flex",
                flexDirection: "column",
                gap: 4,
            }}
        >
            <div style={{ fontSize: 10, color: C.textSecondary }}>{axis.name}</div>
            <div
                style={{
                    fontSize: 11,
                    fontFamily: FONT_MONO,
                    fontWeight: 600,
                    color: meta.color,
                }}
            >
                {axis.verdict}
            </div>
            <div style={{ fontSize: 9, color: C.textTertiary, fontFamily: FONT_MONO }}>
                w {(axis.weight * 100).toFixed(0)}%
            </div>
        </button>
    )
}

/* ─ AxisDetail — 선택된 axis 의 raw 분해 ─ */
function AxisDetail({ axisKey, axis }: { axisKey: string; axis: Axis }) {
    return (
        <div
            style={{
                marginTop: 10,
                background: C.bgInput,
                border: `1px solid ${C.accent}`,
                borderRadius: R.md,
                padding: 12,
            }}
        >
            <div style={{ fontSize: 10, color: C.accentBright, fontFamily: FONT_MONO, marginBottom: 6 }}>
                DETAIL · {axis.name} ({axisKey})
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, fontSize: 11, color: C.textSecondary, marginBottom: 6 }}>
                <span>verdict <span style={{ color: VERDICT_META[axis.verdict].color, fontWeight: 600, fontFamily: FONT_MONO }}>{axis.verdict}</span></span>
                <span>weight <span style={{ fontFamily: FONT_MONO }}>{(axis.weight * 100).toFixed(0)}%</span></span>
                {axis.as_of && <span>as_of <span style={{ fontFamily: FONT_MONO }}>{axis.as_of.slice(0, 10)}</span></span>}
            </div>

            {/* axis-specific raw */}
            {axis.stage && (
                <Row label="cycle stage" value={axis.stage} />
            )}
            {axis.mean_landex != null && (
                <Row label="LANDEX 평균" value={`${axis.mean_landex} (${axis.n_gu}구, σ${axis.stdev_landex})`} />
            )}
            {axis.overview && (
                <Row label="overview" value={axis.overview} />
            )}
            {axis.sectors_breakdown && axis.sectors_breakdown.length > 0 && (
                <div style={{ marginTop: 6 }}>
                    <div style={{ fontSize: 9, color: C.textTertiary, fontFamily: FONT_MONO, marginBottom: 2 }}>섹터별</div>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {axis.sectors_breakdown.map((s, i) => {
                            const m = VERDICT_META[s.verdict as Verdict] || VERDICT_META.NEUTRAL
                            return (
                                <span key={i} style={{ fontSize: 10, color: m.color, fontFamily: FONT_MONO, border: `1px solid ${m.color}`, borderRadius: R.pill, padding: "1px 6px" }}>
                                    {s.name} {s.verdict}
                                </span>
                            )
                        })}
                    </div>
                </div>
            )}
            {axis.raw_indicators && axis.raw_indicators.length > 0 && (
                <div style={{ marginTop: 6 }}>
                    <div style={{ fontSize: 9, color: C.textTertiary, fontFamily: FONT_MONO, marginBottom: 2 }}>지표</div>
                    {axis.raw_indicators.map((ind, i) => (
                        <Row key={i} label={ind.name || `idx${i}`} value={String(ind.value)} />
                    ))}
                </div>
            )}
            {axis._fallback_reason && (
                <div style={{ marginTop: 6, fontSize: 10, color: C.warn, fontStyle: "italic" }}>
                    fallback: {axis._fallback_reason}
                </div>
            )}
            {axis._error && (
                <div style={{ marginTop: 6, fontSize: 10, color: C.danger, fontStyle: "italic" }}>
                    error: {axis._error}
                </div>
            )}
        </div>
    )
}

function Row({ label, value }: { label: string; value: string }) {
    return (
        <div style={{ display: "flex", gap: 8, fontSize: 11, lineHeight: 1.5, marginBottom: 2 }}>
            <span style={{ color: C.textTertiary, fontFamily: FONT_MONO, minWidth: 76, fontSize: 10 }}>{label}</span>
            <span style={{ color: C.textPrimary, flex: 1 }}>{value}</span>
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
                padding: 16,
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

addPropertyControls(EstateMarketHorizon, {
    apiUrlOverride: {
        type: ControlType.String,
        title: "API base (override)",
        defaultValue: "",
        placeholder: ESTATE_API_BASE,
    },
})
