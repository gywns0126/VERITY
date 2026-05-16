// SectorPulse — ESTATE 4섹터 dynamics 카드 (market/ 폴더)
// 아파트(주거) / 오피스 / 중대형 상가 / 오피스텔
//
// Backend: api/builders/estate_sector_pulse_builder.py (R-ONE 실측 4섹터 × 2 통계)
// Endpoint: /api/estate/sector-pulse (vercel-api/api/estate_sector_pulse.py read-through)
// Cron: .github/workflows/estate_sector_pulse.yml (월요일 KST 07:00)
//
// 의도 (사용자 요구 2026-05-17 "에스테이트도 터미널처럼 거시/미시/지역/섹터 시장 흐름 읽어야"):
//   ESTATE 가 비어있던 "섹터 dynamics" 갭 채움. 향후 EstateMarketHorizon(synthesizer) 의 5번째 입력 신호.
//   commercial/ 폴더는 오피스/리테일 단독 컴포넌트 용 — 4섹터 통합은 market/ 가 정합.

import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState, useMemo } from "react"

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

/* ◆ TYPES ◆ */
type Verdict = "BULLISH" | "NEUTRAL" | "BEARISH" | "MIXED" | "UNAVAILABLE"

interface SparkPoint {
    t: string
    v: number | null
}

interface Sector {
    key: string
    name: string
    cycle: string
    verdict: Verdict
    rationale: string
    region?: string
    latest_index?: number | null
    yoy_change_pct?: number | null
    short_change_pct?: number | null
    short_change_unit?: string
    as_of?: string
    yield_pct?: number | null
    yield_is_quarterly?: boolean
    index_source?: string
    yield_source?: string
    spark?: SparkPoint[]
    _error_index?: string
}

interface SectorPulsePayload {
    schema_version?: string
    generated_at: string
    overall_verdict: Verdict
    overall_rationale: string
    sectors: Sector[]
}

const VERDICT_META: Record<Verdict, { label: string; color: string }> = {
    BULLISH: { label: "강세", color: C.success },
    NEUTRAL: { label: "보합", color: C.textSecondary },
    BEARISH: { label: "약세", color: C.danger },
    MIXED: { label: "혼조", color: C.warn },
    UNAVAILABLE: { label: "데이터 부재", color: C.textTertiary },
}

interface Props {
    apiUrlOverride?: string
}

export default function SectorPulse(props: Props) {
    const base = (props.apiUrlOverride && props.apiUrlOverride.trim()) || ESTATE_API_BASE
    const [data, setData] = useState<SectorPulsePayload | null>(null)
    const [err, setErr] = useState<string | null>(null)
    const [loading, setLoading] = useState<boolean>(true)
    const [selectedKey, setSelectedKey] = useState<string | null>(null)

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        setErr(null)
        fetch(`${base}/api/estate/sector-pulse`)
            .then((r) => (r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`)))
            .then((d) => {
                if (cancelled) return
                if (d && d.generated_at && Array.isArray(d.sectors)) {
                    setData(d as SectorPulsePayload)
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
                    SECTOR PULSE
                </span>
                <span style={{ fontSize: 11, color: C.textTertiary }}>
                    {data?.generated_at ? `갱신 ${data.generated_at.slice(5, 10)}` : ""}
                </span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
                <div style={{ fontSize: 16, fontWeight: 600, color: C.textPrimary }}>
                    4섹터 동향
                </div>
                <span style={{ fontSize: 12, fontWeight: 400, color: C.textSecondary }}>
                    아파트 · 오피스 · 상가 · 오피스텔
                </span>
                {data && (
                    <span
                        style={{
                            marginLeft: "auto",
                            fontSize: 11,
                            fontFamily: FONT_MONO,
                            fontWeight: 600,
                            color: VERDICT_META[data.overall_verdict].color,
                            border: `1px solid ${VERDICT_META[data.overall_verdict].color}`,
                            borderRadius: R.pill,
                            padding: "2px 10px",
                        }}
                    >
                        종합 · {data.overall_verdict}
                    </span>
                )}
            </div>

            {/* CONTENT */}
            {loading && !data ? (
                <Skeleton height={220} />
            ) : err || !data ? (
                <Placeholder text="섹터 동향 일시 불가" />
            ) : (
                <>
                    {/* 4섹터 grid (2×2) */}
                    <div
                        style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(2, 1fr)",
                            gap: 10,
                            marginBottom: 12,
                        }}
                    >
                        {data.sectors.map((s) => (
                            <SectorCard
                                key={s.key}
                                sector={s}
                                selected={selectedKey === s.key}
                                onClick={() => setSelectedKey((k) => (k === s.key ? null : s.key))}
                            />
                        ))}
                    </div>

                    {/* selected detail */}
                    {selectedKey &&
                        (() => {
                            const s = data.sectors.find((x) => x.key === selectedKey)
                            if (!s) return null
                            return (
                                <div
                                    style={{
                                        background: C.bgInput,
                                        border: `1px solid ${C.accent}`,
                                        borderRadius: R.md,
                                        padding: 12,
                                        marginBottom: 10,
                                    }}
                                >
                                    <div style={{ fontSize: 11, color: C.accentBright, fontFamily: FONT_MONO, marginBottom: 6 }}>
                                        DETAIL · {s.name}
                                    </div>
                                    <div style={{ fontSize: 12, color: C.textPrimary, marginBottom: 6 }}>
                                        {s.rationale}
                                    </div>
                                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, fontSize: 10, fontFamily: FONT_MONO, color: C.textSecondary }}>
                                        {s.region && <span>지역 {s.region}</span>}
                                        {s.as_of && <span>· 기준 {s.as_of}</span>}
                                        {s.cycle && <span>· cycle {s.cycle}</span>}
                                    </div>
                                    {(s.index_source || s.yield_source) && (
                                        <div style={{ marginTop: 6, fontSize: 9, color: C.textTertiary, fontFamily: FONT_MONO, lineHeight: 1.5 }}>
                                            {s.index_source && <div>지수: {s.index_source}</div>}
                                            {s.yield_source && <div>수익률: {s.yield_source}</div>}
                                        </div>
                                    )}
                                </div>
                            )
                        })()}

                    {/* overall rationale */}
                    <div
                        style={{
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
                            종합
                        </span>
                        {data.overall_rationale}
                    </div>

                    {/* footer */}
                    <div
                        style={{
                            marginTop: 8,
                            fontSize: 9,
                            color: C.textTertiary,
                            fontFamily: FONT_MONO,
                            display: "flex",
                            gap: 8,
                        }}
                    >
                        <span>R-ONE 실측</span>
                        <span>· {data.generated_at.slice(0, 10)}</span>
                    </div>
                </>
            )}
        </div>
    )
}

/* ─ SectorCard — 1개 섹터 카드 ─ */
function SectorCard({
    sector, selected, onClick,
}: {
    sector: Sector
    selected: boolean
    onClick: () => void
}) {
    const meta = VERDICT_META[sector.verdict]
    const yoyColor = (() => {
        const y = sector.yoy_change_pct
        if (y == null) return C.textTertiary
        if (y >= 2) return C.success
        if (y <= -2) return C.danger
        return C.textSecondary
    })()

    return (
        <button
            onClick={onClick}
            style={{
                background: selected ? C.accentSoft : C.bgElevated,
                border: `1px solid ${selected ? C.accent : C.borderStrong}`,
                borderRadius: R.md,
                padding: 10,
                cursor: "pointer",
                textAlign: "left",
                color: C.textPrimary,
                fontFamily: FONT,
                transition: "all 150ms ease",
                display: "flex",
                flexDirection: "column",
                gap: 6,
            }}
        >
            {/* row 1: 이름 + verdict pill */}
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: C.textPrimary, flex: 1 }}>
                    {sector.name}
                </span>
                <span
                    style={{
                        fontSize: 9,
                        fontFamily: FONT_MONO,
                        fontWeight: 600,
                        color: meta.color,
                        border: `1px solid ${meta.color}`,
                        borderRadius: R.pill,
                        padding: "1px 6px",
                    }}
                >
                    {sector.verdict}
                </span>
            </div>

            {/* row 2: index + YoY + short */}
            {sector.latest_index != null ? (
                <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                    <span style={{ fontSize: 18, fontWeight: 600, color: C.textPrimary, fontFamily: FONT_MONO }}>
                        {sector.latest_index.toFixed(2)}
                    </span>
                    {sector.yoy_change_pct != null && (
                        <span style={{ fontSize: 11, color: yoyColor, fontFamily: FONT_MONO }}>
                            YoY {sector.yoy_change_pct >= 0 ? "+" : ""}{sector.yoy_change_pct.toFixed(2)}%
                        </span>
                    )}
                    {sector.short_change_pct != null && sector.short_change_unit && (
                        <span style={{ fontSize: 10, color: C.textTertiary, fontFamily: FONT_MONO }}>
                            {sector.short_change_unit} {sector.short_change_pct >= 0 ? "+" : ""}{sector.short_change_pct.toFixed(2)}%
                        </span>
                    )}
                </div>
            ) : (
                <div style={{ fontSize: 11, color: C.textTertiary }}>{sector._error_index || "데이터 부재"}</div>
            )}

            {/* row 3: sparkline + 수익률 */}
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Sparkline points={sector.spark || []} color={meta.color} />
                {sector.yield_pct != null && (
                    <span style={{ fontSize: 10, color: C.accentBright, fontFamily: FONT_MONO }}>
                        수익률 {sector.yield_pct}%{sector.yield_is_quarterly ? "/Q" : ""}
                    </span>
                )}
            </div>
        </button>
    )
}

/* ─ Sparkline mini ([feedback_picture_book_principle]) ─ */
function Sparkline({ points, color }: { points: SparkPoint[]; color: string }) {
    const valid = useMemo(() => points.filter((p): p is { t: string; v: number } => p.v != null), [points])
    if (valid.length < 2) {
        return <div style={{ flex: 1, height: 22 }} />
    }
    const vals = valid.map((p) => p.v)
    const min = Math.min(...vals)
    const max = Math.max(...vals)
    const range = max - min || 1
    const W = 100
    const H = 22
    const stepX = valid.length > 1 ? W / (valid.length - 1) : W
    const path = valid
        .map((p, i) => {
            const x = i * stepX
            const y = H - ((p.v - min) / range) * (H - 2) - 1
            return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`
        })
        .join(" ")
    return (
        <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ flex: 1 }}>
            <path d={path} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
        </svg>
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

addPropertyControls(SectorPulse, {
    apiUrlOverride: {
        type: ControlType.String,
        title: "API base (override)",
        defaultValue: "",
        placeholder: ESTATE_API_BASE,
    },
})
