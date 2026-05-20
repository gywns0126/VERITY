// CommercialPulse — ESTATE commercial/ 페이지 v0.1
//
// 의도: office + 중대형 상가 2섹터 deep dive (commercial 트랙 분석).
//   SectorPulse (4섹터 cross) 와 차별 — 2섹터 깊이 + yoy_spread / yield_spread / 종합 verdict.
//
// Backend: api/builders/estate_sector_pulse_builder.py (R-ONE 4섹터 — commercial 만 추출)
// Endpoint: /api/estate/commercial-pulse (commit 506c050c — sector_pulse.json read-through)
// design memo: project_estate_commercial_v0_design (5/19 박힘)
//
// RULE 6 정합: LLM narrative 호출 X — metric/spread/verdict only.

import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"

/* ◆ ESTATE 패밀리룩 v3 ◆ */
const C = {
    bgCard: "#0F0D0A", bgElevated: "#16130E", bgInput: "#1F1B14",
    borderStrong: "#3A3024",
    textPrimary: "#F2EFE9", textSecondary: "#A8A299", textTertiary: "#6B665E",
    accent: "#B8864D", accentBright: "#D4A26B",
    success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Menlo', monospace"
const R = { sm: 6, md: 10, lg: 14, pill: 999 }

const ESTATE_API_BASE = "https://project-yw131.vercel.app"

type Verdict = "BULLISH" | "NEUTRAL" | "BEARISH" | "UNAVAILABLE"

interface Sector {
    key: string
    name: string
    verdict: Verdict
    rationale?: string
    region?: string
    latest_index?: number | null
    yoy_change_pct?: number | null
    yield_pct?: number | null
    // Fix A (builder transient resilience): 직전 good 값 carry-forward 시 stale 마킹
    stale?: boolean
    stale_reason?: string
    as_of?: string
}

interface Spread {
    office_yoy_pct?: number | null
    retail_yoy_pct?: number | null
    office_yield_pct?: number | null
    retail_yield_pct?: number | null
    spread_pct?: number | null
    reason?: string
}

interface CommercialPulsePayload {
    schema_version?: string
    generated_at?: string
    commercial_verdict: Verdict
    data_partial: boolean
    has_stale?: boolean
    sectors: Sector[]
    yoy_spread?: Spread | null
    yield_spread?: Spread | null
    source_pulse_overall_verdict?: Verdict
}

const VERDICT_META: Record<Verdict, { label: string; color: string }> = {
    BULLISH: { label: "강세", color: C.success },
    NEUTRAL: { label: "보합", color: C.textSecondary },
    BEARISH: { label: "약세", color: C.danger },
    UNAVAILABLE: { label: "데이터 부재", color: C.textTertiary },
}

interface Props {
    apiUrlOverride?: string
}

export default function CommercialPulse(props: Props) {
    const base = (props.apiUrlOverride && props.apiUrlOverride.trim()) || ESTATE_API_BASE
    const [data, setData] = useState<CommercialPulsePayload | null>(null)
    const [err, setErr] = useState<string | null>(null)
    const [loading, setLoading] = useState<boolean>(true)

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        setErr(null)
        fetch(`${base}/api/estate/commercial-pulse`)
            .then((r) => (r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`)))
            .then((d) => {
                if (cancelled) return
                if (d && Array.isArray(d.sectors)) {
                    setData(d as CommercialPulsePayload)
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
        return () => { cancelled = true }
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
                    COMMERCIAL PULSE
                </span>
                <span style={{ fontSize: 11, color: C.textTertiary }}>
                    {data?.generated_at ? `갱신 ${data.generated_at.slice(5, 10)}` : ""}
                </span>
                {data?.data_partial && (
                    <span
                        style={{
                            fontSize: 10,
                            fontFamily: FONT_MONO,
                            color: C.warn,
                            border: `1px solid ${C.warn}`,
                            borderRadius: R.pill,
                            padding: "1px 6px",
                            marginLeft: 4,
                        }}
                        title="일부 데이터 부재 (R-ONE 응답 결함, 별도 sprint 큐잉)"
                    >
                        PARTIAL
                    </span>
                )}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
                <div style={{ fontSize: 16, fontWeight: 600, color: C.textPrimary }}>
                    상업 부동산 동향
                </div>
                <span style={{ fontSize: 12, fontWeight: 400, color: C.textSecondary }}>
                    오피스 · 중대형 상가
                </span>
                {data && (
                    <span
                        style={{
                            marginLeft: "auto",
                            fontSize: 11,
                            fontFamily: FONT_MONO,
                            fontWeight: 600,
                            color: VERDICT_META[data.commercial_verdict].color,
                            border: `1px solid ${VERDICT_META[data.commercial_verdict].color}`,
                            borderRadius: R.pill,
                            padding: "2px 10px",
                        }}
                    >
                        종합 · {data.commercial_verdict}
                    </span>
                )}
            </div>

            {/* CONTENT */}
            {loading && !data ? (
                <SkeletonRows />
            ) : err || !data ? (
                <Placeholder text="상업 동향 일시 불가" />
            ) : (
                <>
                    {/* 2섹터 grid (1×2) */}
                    <div
                        style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(2, 1fr)",
                            gap: 10,
                            marginBottom: 12,
                        }}
                    >
                        {data.sectors.map((s) => (
                            <SectorTile key={s.key} sector={s} />
                        ))}
                    </div>

                    {/* spread block */}
                    <SpreadBlock yoy={data.yoy_spread} yield={data.yield_spread} />
                </>
            )}
        </div>
    )
}

function SectorTile({ sector }: { sector: Sector }) {
    const meta = VERDICT_META[sector.verdict] || VERDICT_META.UNAVAILABLE
    const yoy = sector.yoy_change_pct
    const yld = sector.yield_pct
    return (
        <div
            style={{
                background: C.bgElevated,
                border: `1px solid ${C.borderStrong}`,
                borderRadius: R.md,
                padding: 12,
                display: "flex",
                flexDirection: "column",
                gap: 6,
            }}
        >
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: C.textPrimary }}>{sector.name}</div>
                {sector.stale && (
                    <span
                        style={{
                            marginLeft: "auto",
                            fontSize: 9,
                            fontFamily: FONT_MONO,
                            color: C.textTertiary,
                            border: `1px solid ${C.textTertiary}`,
                            borderRadius: R.pill,
                            padding: "1px 6px",
                        }}
                        title={`${sector.stale_reason || "직전 값 유지"}${sector.as_of ? ` (${sector.as_of})` : ""}`}
                    >
                        STALE
                    </span>
                )}
                <span
                    style={{
                        marginLeft: sector.stale ? 0 : "auto",
                        fontSize: 10,
                        fontFamily: FONT_MONO,
                        color: meta.color,
                        border: `1px solid ${meta.color}`,
                        borderRadius: R.pill,
                        padding: "1px 8px",
                    }}
                >
                    {sector.verdict}
                </span>
            </div>
            <div style={{ display: "flex", gap: 12, fontSize: 11, fontFamily: FONT_MONO }}>
                <div>
                    <div style={{ color: C.textTertiary, fontSize: 9 }}>YoY</div>
                    <div style={{ color: yoy == null ? C.textTertiary : yoy >= 0 ? C.success : C.danger }}>
                        {yoy == null ? "—" : `${yoy >= 0 ? "+" : ""}${yoy.toFixed(2)}%`}
                    </div>
                </div>
                <div>
                    <div style={{ color: C.textTertiary, fontSize: 9 }}>수익률(분기)</div>
                    <div style={{ color: yld == null ? C.textTertiary : C.textSecondary }}>
                        {yld == null ? "—" : `${yld.toFixed(2)}%`}
                    </div>
                </div>
            </div>
            {sector.rationale && (
                <div style={{ fontSize: 10, color: C.textTertiary, lineHeight: 1.4 }}>
                    {sector.rationale}
                </div>
            )}
        </div>
    )
}

function SpreadBlock({ yoy, yield: yld }: { yoy?: Spread | null; yield?: Spread | null }) {
    return (
        <div
            style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 10,
                fontSize: 11,
            }}
        >
            <SpreadRow label="YoY 차이 (오피스 − 상가)" spread={yoy} unit="%p" />
            <SpreadRow label="수익률 차이 (오피스 − 상가)" spread={yld} unit="%p" />
        </div>
    )
}

function SpreadRow({ label, spread, unit }: { label: string; spread?: Spread | null; unit: string }) {
    const val = spread?.spread_pct
    return (
        <div
            style={{
                background: C.bgInput,
                border: `1px solid ${C.borderStrong}`,
                borderRadius: R.sm,
                padding: 8,
            }}
        >
            <div style={{ fontSize: 9, color: C.textTertiary, fontFamily: FONT_MONO, marginBottom: 4 }}>{label}</div>
            <div
                style={{
                    fontSize: 14,
                    fontFamily: FONT_MONO,
                    color: val == null ? C.textTertiary : val >= 0 ? C.success : C.danger,
                }}
            >
                {val == null ? "—" : `${val >= 0 ? "+" : ""}${val.toFixed(2)}${unit}`}
            </div>
            {spread?.reason && (
                <div style={{ fontSize: 9, color: C.warn, marginTop: 2 }}>{spread.reason}</div>
            )}
        </div>
    )
}

function SkeletonRows() {
    return (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <div style={{ height: 90, background: C.bgElevated, borderRadius: R.md, opacity: 0.4 }} />
            <div style={{ height: 90, background: C.bgElevated, borderRadius: R.md, opacity: 0.4 }} />
        </div>
    )
}

function Placeholder({ text }: { text: string }) {
    return (
        <div
            style={{
                padding: 24,
                textAlign: "center",
                color: C.textTertiary,
                fontSize: 13,
                background: C.bgElevated,
                borderRadius: R.md,
                border: `1px dashed ${C.borderStrong}`,
            }}
        >
            {text}
        </div>
    )
}

addPropertyControls(CommercialPulse, {
    apiUrlOverride: {
        type: ControlType.String,
        title: "API URL (선택)",
        placeholder: ESTATE_API_BASE,
    },
})
