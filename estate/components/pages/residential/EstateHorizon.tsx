// EstateHorizon — 서울 종합 부동산 사이클 stage + horizon 분포 V0
// VERITY ESTATE residential 페이지급 컴포넌트.
//
// Backend: api/intelligence/estate_horizon.py (compute_estate_horizon)
// Builder: api/builders/estate_brain_builder.py (서울 25 gu lead_time 평균)
// Endpoint: /api/estate/horizon (vercel-api/api/estate_horizon.py)
//
// 5 섹션:
//   ① Header (verdict + cycle stage 배지 + dominant signal)
//   ② Cycle Stage 5단계 사다리 (recovery / expansion / peak / contraction / depression)
//   ③ Horizon Returns (3m / 6m / 12m / 24m × p25/median/p75)
//   ④ Nearest Analog (KB·한국부동산원 historical 1위)
//   ⑤ Source Attribution (feedback_master_rule_drift_audit + source_attribution_discipline)

import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useMemo, useState } from "react"

/* ◆ ESTATE 패밀리룩 v3 — feedback_estate_design_familylook 정합 ◆ */
const C = {
    bgPage: "#0A0908", bgCard: "#0F0D0A", bgElevated: "#16130E", bgInput: "#1F1B14",
    border: "transparent", borderStrong: "#3A3024",
    textPrimary: "#F2EFE9", textSecondary: "#A8A299", textTertiary: "#6B665E", textDisabled: "#4A453E",
    accent: "#B8864D", accentBright: "#D4A26B",
    accentSoft: "rgba(184,134,77,0.15)",
    statusPos: "#22C55E", statusNeut: "#A8A299", statusNeg: "#EF4444",
}
const T = { cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700 }
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24 }
const R = { sm: 6, md: 10, lg: 14 }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
const MOTION: React.CSSProperties = { transition: "all 200ms ease" }
/* ◆ DESIGN TOKENS END ◆ */


/* ◆ TYPES (estate_horizon V0 schema 정합) ◆ */
type Stage = "recovery" | "expansion" | "peak" | "contraction" | "depression"

interface HorizonRow {
    p25_pct: number
    median_pct: number
    p75_pct: number
}

interface ModelMeta {
    stage_classification?: { source?: string; version?: string; note?: string }
    horizon_returns?: { source?: string; version?: string; note?: string }
    lead_time_source?: string
    analog_source?: string
}

interface SnapshotMeta {
    generated_at?: string
    schema_version?: string
}

interface HorizonPayload {
    version?: string
    as_of?: string
    verdict?: string
    cycle_stage?: Stage
    cycle_stage_label_ko?: string
    horizons?: { "3m"?: HorizonRow; "6m"?: HorizonRow; "12m"?: HorizonRow; "24m"?: HorizonRow }
    dominant_signal?: string | null
    nearest_analog?: string | null
    model_meta?: ModelMeta
    snapshot_meta?: SnapshotMeta
    error?: string
}


const STAGE_ORDER: Stage[] = ["recovery", "expansion", "peak", "contraction", "depression"]
const STAGE_LABEL: Record<Stage, string> = {
    recovery: "회복",
    expansion: "확장",
    peak: "고점",
    contraction: "수축",
    depression: "침체",
}
const STAGE_COLOR: Record<Stage, string> = {
    recovery: C.statusPos,
    expansion: C.statusPos,
    peak: "#F59E0B",
    contraction: C.statusNeg,
    depression: C.statusNeg,
}


function pct(v?: number, plus = true): string {
    if (v == null) return "—"
    const sign = plus && v >= 0 ? "+" : ""
    return `${sign}${v.toFixed(1)}%`
}


/* ◆ MOCK ◆ */
const MOCK: HorizonPayload = {
    version: "v0",
    as_of: "2026-05-09T10:00:00+09:00",
    verdict: "확장 · 전세 강세 · 12M median +6.5% · ~ Rate-Shock Rebound",
    cycle_stage: "expansion",
    cycle_stage_label_ko: "확장",
    horizons: {
        "3m":  { p25_pct: 0.5, median_pct: 1.8, p75_pct: 3.2 },
        "6m":  { p25_pct: 1.2, median_pct: 3.5, p75_pct: 5.8 },
        "12m": { p25_pct: 2.5, median_pct: 6.5, p75_pct: 11.0 },
        "24m": { p25_pct: 4.0, median_pct: 10.0, p75_pct: 16.0 },
    },
    dominant_signal: "전세 강세",
    nearest_analog: "Rate-Shock Rebound (2022~)",
    model_meta: {
        stage_classification: {
            source: "자체 결정 (Perplexity 2026-05-08 Lead Time + KB 분포 근사)",
            version: "v0_hardcoded",
        },
        horizon_returns: {
            source: "한국 KB 매매가격지수 1986-2024 분기 lookup (V0 approximation)",
            version: "v0_hardcoded",
        },
        lead_time_source: "Perplexity 2026-05-08 (TVP-VAR / Granger / 패널)",
        analog_source: "KB부동산·한국부동산원 1997/2008/2022 (estate_brain)",
    },
    snapshot_meta: {
        generated_at: "2026-05-09T10:00:00+09:00",
        schema_version: "v0.2",
    },
}


interface Props {
    apiBase: string
    refreshSec: number
    useMock: boolean
}


export default function EstateHorizon(props: Props) {
    const { apiBase, refreshSec, useMock } = props
    const [data, setData] = useState<HorizonPayload | null>(useMock ? MOCK : null)
    const [error, setError] = useState<string | null>(null)
    const [loading, setLoading] = useState<boolean>(!useMock)

    useEffect(() => {
        if (useMock) {
            setData(MOCK)
            setError(null)
            setLoading(false)
            return
        }
        const ac = new AbortController()
        const base = (apiBase || "").replace(/\/$/, "")
        const load = async () => {
            setLoading(true)
            setError(null)
            try {
                const r = await fetch(`${base}/api/estate/horizon`, { signal: ac.signal })
                if (!r.ok) {
                    setError(`HTTP ${r.status}`)
                    setData(null)
                } else {
                    const j = await r.json()
                    if (j.error) {
                        setError(j.error)
                        setData(null)
                    } else {
                        setData(j as HorizonPayload)
                    }
                }
            } catch (e: any) {
                if (e?.name !== "AbortError") {
                    setError(e?.message || "fetch_failed")
                    setData(null)
                }
            } finally {
                setLoading(false)
            }
        }
        load()
        const id = setInterval(load, Math.max(60, refreshSec) * 1000)
        return () => { ac.abort(); clearInterval(id) }
    }, [apiBase, refreshSec, useMock])

    const stage: Stage | undefined = data?.cycle_stage
    const stageColor = stage ? STAGE_COLOR[stage] : C.textTertiary
    const horizons = data?.horizons || {}

    const hKeys = useMemo(() => ["3m", "6m", "12m", "24m"] as const, [])

    return (
        <div style={{
            background: C.bgCard,
            color: C.textPrimary,
            fontFamily: FONT,
            padding: S.xl,
            borderRadius: R.lg,
            display: "flex", flexDirection: "column", gap: S.lg,
            ...MOTION,
        }}>
            {/* ① Header */}
            <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                <div style={{
                    color: C.textTertiary, fontSize: T.cap, letterSpacing: 0.4,
                    textTransform: "uppercase",
                }}>
                    서울 종합 사이클 · V0
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: S.md, flexWrap: "wrap" }}>
                    <span style={{
                        color: stageColor, fontSize: T.cap, fontWeight: T.w_bold,
                        padding: `${S.xs}px ${S.sm}px`,
                        background: C.bgElevated,
                        border: `1px solid ${stageColor}55`,
                        borderRadius: R.sm,
                        letterSpacing: 0.3,
                    }}>
                        {data?.cycle_stage_label_ko || "—"}
                    </span>
                    {data?.dominant_signal && (
                        <span style={{
                            color: C.textSecondary, fontSize: T.cap, fontWeight: T.w_med,
                        }}>
                            {data.dominant_signal}
                        </span>
                    )}
                </div>
                <div style={{
                    color: C.textPrimary, fontSize: T.body, fontWeight: T.w_med, lineHeight: 1.5,
                }}>
                    {loading && !data ? "불러오는 중…"
                        : error ? <span style={{ color: C.statusNeg }}>오류: {error}</span>
                        : data?.verdict || "—"}
                </div>
            </div>

            {/* ② Cycle Stage 사다리 */}
            <div style={{ display: "flex", flexDirection: "column", gap: S.sm }}>
                <div style={{ color: C.textTertiary, fontSize: T.cap, letterSpacing: 0.4 }}>
                    Cycle Stage 5단계
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: S.xs }}>
                    {STAGE_ORDER.map((s) => {
                        const active = s === stage
                        return (
                            <div key={s} style={{
                                padding: `${S.sm}px ${S.xs}px`,
                                background: active ? C.bgElevated : "transparent",
                                border: `1px solid ${active ? STAGE_COLOR[s] : C.borderStrong}`,
                                borderRadius: R.sm,
                                color: active ? STAGE_COLOR[s] : C.textTertiary,
                                fontSize: T.cap, fontWeight: active ? T.w_bold : T.w_med,
                                textAlign: "center", letterSpacing: 0.3,
                                ...MOTION,
                            }}>
                                {STAGE_LABEL[s]}
                            </div>
                        )
                    })}
                </div>
            </div>

            {/* ③ Horizon Returns */}
            <div style={{ display: "flex", flexDirection: "column", gap: S.sm }}>
                <div style={{ color: C.textTertiary, fontSize: T.cap, letterSpacing: 0.4 }}>
                    Horizon Returns (KB lookup, V0)
                </div>
                <div style={{
                    background: C.bgElevated, padding: S.md, borderRadius: R.sm,
                    display: "grid", gridTemplateColumns: "60px 1fr 1fr 1fr", gap: S.sm,
                    ...MONO, fontSize: T.body,
                }}>
                    <span style={{ color: C.textTertiary, fontSize: T.cap }}>HORIZON</span>
                    <span style={{ color: C.textTertiary, fontSize: T.cap, textAlign: "right" }}>p25</span>
                    <span style={{ color: C.textTertiary, fontSize: T.cap, textAlign: "right" }}>median</span>
                    <span style={{ color: C.textTertiary, fontSize: T.cap, textAlign: "right" }}>p75</span>
                    {hKeys.map((k) => {
                        const row = horizons[k]
                        const med = row?.median_pct
                        const medColor = med == null ? C.textTertiary
                            : med >= 0 ? C.statusPos : C.statusNeg
                        return (
                            <React.Fragment key={k}>
                                <span style={{ color: C.textSecondary, fontWeight: T.w_semi }}>
                                    {k}
                                </span>
                                <span style={{ color: C.textSecondary, textAlign: "right" }}>
                                    {pct(row?.p25_pct)}
                                </span>
                                <span style={{ color: medColor, textAlign: "right", fontWeight: T.w_bold }}>
                                    {pct(row?.median_pct)}
                                </span>
                                <span style={{ color: C.textSecondary, textAlign: "right" }}>
                                    {pct(row?.p75_pct)}
                                </span>
                            </React.Fragment>
                        )
                    })}
                </div>
            </div>

            {/* ④ Nearest Analog */}
            {data?.nearest_analog && (
                <div style={{
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    padding: `${S.sm}px ${S.md}px`,
                    background: C.bgElevated, borderRadius: R.sm,
                    fontSize: T.cap,
                }}>
                    <span style={{ color: C.textTertiary, letterSpacing: 0.4 }}>
                        Nearest Historical Analog
                    </span>
                    <span style={{ color: C.accent, fontWeight: T.w_semi }}>
                        {data.nearest_analog}
                    </span>
                </div>
            )}

            {/* ⑤ Source Attribution */}
            <details style={{ fontSize: T.cap, color: C.textTertiary }}>
                <summary style={{ cursor: "pointer", letterSpacing: 0.3 }}>
                    출처 · 산식 (V0 hardcoded — V1 동적 calibration 큐잉)
                </summary>
                <ul style={{ margin: `${S.sm}px 0 0`, paddingLeft: S.lg, lineHeight: 1.6 }}>
                    <li>
                        Stage 분류: {data?.model_meta?.stage_classification?.source || "—"}
                    </li>
                    <li>
                        Horizon 분포: {data?.model_meta?.horizon_returns?.source || "—"}
                    </li>
                    <li>
                        Lead Time: {data?.model_meta?.lead_time_source || "—"}
                    </li>
                    <li>
                        Analog: {data?.model_meta?.analog_source || "—"}
                    </li>
                    {data?.snapshot_meta?.generated_at && (
                        <li>
                            Generated: {data.snapshot_meta.generated_at}
                        </li>
                    )}
                </ul>
            </details>
        </div>
    )
}


addPropertyControls(EstateHorizon, {
    apiBase: {
        type: ControlType.String,
        title: "API Base",
        defaultValue: "https://verity-estate.vercel.app",
        description: "vercel-api base. /api/estate/horizon 자동 부착.",
    },
    refreshSec: {
        type: ControlType.Number,
        title: "Refresh (sec)",
        defaultValue: 600,
        min: 60,
        step: 60,
    },
    useMock: {
        type: ControlType.Boolean,
        title: "Mock 데이터 사용",
        defaultValue: false,
        description: "true = 결정적 mock (개발용). 운영은 false.",
    },
})
