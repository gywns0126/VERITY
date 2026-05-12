// EstateBrainPanel — 단지 단위 ESTATE Brain V0.2 상세 분석 패널
// VERITY ESTATE 페이지급 컴포넌트 (단지 drill-down).
// 흡수 X — ScoreDetailPanel(구 단위 LANDEX) 와 도메인 분리 (단지 vs 구).
//
// Plan: docs/ESTATE_BRAIN_V0_PLAN.md (commit b6a2732)
// Endpoint: /api/estate/brain?complex_id=... (commit 6e10d19, P2 read-through)
// Core 산식: api/intelligence/estate_brain.py (commit 94ce0d0)
//
// 5 섹션:
//   ① Header (complex 이름 + weighted_score + 4중 신호 카운터 + 데이터 source 배지)
//   ② Valuation 4 Layer (PIR / 전세가율 / Cap Rate / 인근 실거래) — 각 score bar + verdict chip
//   ③ 고평가 4중 신호 chip strip
//   ④ Cycle Analog (현재 phase + 3 nearest + lead time mini)
//   ⑤ Redevelopment Stage (있을 때만 — 6 stage 사다리 + 가격 phase)

import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState, useMemo } from "react"

/* ◆ ESTATE 패밀리룩 v3 — feedback_estate_design_familylook 정합 (VERITY 마스터 + accent gold) ◆ */
const C = {
    bgPage: "#0A0908", bgCard: "#0F0D0A", bgElevated: "#16130E", bgInput: "#1F1B14",
    border: "transparent", borderStrong: "#3A3024",
    textPrimary: "#F2EFE9", textSecondary: "#A8A299", textTertiary: "#6B665E", textDisabled: "#4A453E",
    accent: "#B8864D", accentBright: "#D4A26B", accentHover: "#D4A063",
    accentSoft: "rgba(184,134,77,0.15)",
    verdictHigh: "#EF4444", verdictBubble: "#EF4444", verdictCompressed: "#EF4444",
    verdictBalanced: "#A8A299", verdictLow: "#F59E0B",
    verdictAttractive: "#22C55E", verdictVeryHigh: "#22C55E", verdictAligned: "#A8A299",
    statusPos: "#22C55E", statusNeut: "#A8A299", statusNeg: "#EF4444",
    info: "#5BA9FF",
}
const T = { cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28, h0: 36,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700 }
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24 }
const R = { sm: 6, md: 10, lg: 14 }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
const MOTION: React.CSSProperties = { transition: "all 200ms ease" }
/* ◆ DESIGN TOKENS END ◆ */


/* ◆ TYPES (estate_brain V0.2 schema 정합) ◆ */
type LayerKey = "L1_pir" | "L2_jeonse" | "L3_cap_rate" | "L4_neighbor"
type ProjectType = "reconstruction" | "redevelopment"

interface Layer {
    score?: number | null
    verdict?: string
    value?: number
    z_score?: number | null
    "10yr_ma"?: number | null
    treasury_10y?: number
    spread_pp?: number
    kb_price?: number
    actual?: number
    gap_pct?: number
}
interface Valuation {
    primary_anchor_pct: number | null
    layers: Record<LayerKey, Layer | null>
    weighted_score: number | null
    extreme_signals: string[]
    extreme_signals_count: number
}
interface LeadTimeSignal {
    value_pct?: number
    value_yoy_pct?: number
    rate_change_pp?: number
    lead_months: number
    verdict: string
    non_linear_warning?: string
}
interface CycleAnalog {
    current_phase: string
    nearest_historical: Array<{ name: string; year_label: string; shape: string; distance: number }>
    lead_time_signals: Record<string, LeadTimeSignal>
    forward_return_horizon_weeks: number
}
interface RedevelopmentStage {
    stage: string
    stage_label_ko: string
    project_type: ProjectType
    months_in_stage: number
    months_to_next_stage_estimated: number
    price_phase: string
    monitoring: { valuation_announcement_pending: boolean; general_subscription_announced: boolean }
}
interface ModelMeta {
    version: string
    source: string
    factor_weights?: string
    price_source?: string
}
interface SnapshotMeta {
    generated_at?: string
    schema_version?: string
    diagnostics?: Record<string, any>
}
interface BrainPayload {
    version: string
    as_of: string
    complex_id: string
    valuation: Valuation
    cycle_analog: CycleAnalog
    redevelopment_stage: RedevelopmentStage | null
    regional_split: { core: string; non_core: string }
    model_meta: ModelMeta
    snapshot_meta?: SnapshotMeta
    error?: string
}


/* ◆ MOCK ◆ */
const MOCK_BRAIN: BrainPayload = {
    version: "v0.2",
    as_of: "2026-05-08T10:00:00+09:00",
    complex_id: "강남구_대치동_은마_1979",
    valuation: {
        primary_anchor_pct: 35,
        layers: {
            L1_pir:      { score: 0, verdict: "high", value: 40.0, z_score: 11.0, "10yr_ma": 18 },
            L2_jeonse:   { score: 0, verdict: "bubble", value: 25.0 },
            L3_cap_rate: { score: 0, verdict: "compressed", value: 1.05, treasury_10y: 3.2, spread_pp: -2.15 },
            L4_neighbor: { score: 35, verdict: "aligned", kb_price: 27e8, actual: 25.5e8, gap_pct: -5.6 },
        },
        weighted_score: 15.8,
        extreme_signals: ["pir_z_extreme", "jeonse_ratio_below_50", "cap_treasury_inverted"],
        extreme_signals_count: 3,
    },
    cycle_analog: {
        current_phase: "Rate-Shock Rebound",
        nearest_historical: [
            { name: "Rate-Shock Rebound", year_label: "2022~", shape: "W", distance: 0.18 },
            { name: "Shock-Recovery", year_label: "1997 IMF", shape: "V", distance: 0.62 },
            { name: "Debt-Deflation Drag", year_label: "2008 GFC", shape: "U", distance: 1.05 },
        ],
        lead_time_signals: {
            jeonse_3m_lead:         { value_pct: 1.2, lead_months: 2, verdict: "moderate_up" },
            jeonse_ratio_24m:       { value_pct: 58.0, lead_months: 24, verdict: "balanced" },
            construction_starts_lead: { value_yoy_pct: -12.0, lead_months: 28, verdict: "supply_tight_in_2y" },
            unsold_units_lead:      { value_yoy_pct: 18.0, lead_months: 4, verdict: "negative_pressure" },
            rate_lead:              { rate_change_pp: -0.25, lead_months: 6, verdict: "neutral" },
        },
        forward_return_horizon_weeks: 26,
    },
    redevelopment_stage: {
        stage: "management_plan", stage_label_ko: "관리처분 인가",
        project_type: "redevelopment", months_in_stage: 4,
        months_to_next_stage_estimated: 5, price_phase: "max_uplift",
        monitoring: { valuation_announcement_pending: true, general_subscription_announced: false },
    },
    regional_split: { core: "강남3구·마용성", non_core: "수도권 외곽" },
    model_meta: { version: "v0_hardcoded", source: "v0_mock", price_source: "v0_mock" },
}


/* ◆ DATA FETCH ◆ */
async function fetchBrain(
    apiUrl: string, complexId: string, gu: string, scenario: string,
    signal?: AbortSignal
): Promise<BrainPayload> {
    if (!apiUrl) return MOCK_BRAIN
    const base = apiUrl.replace(/\/$/, "")
    const params = new URLSearchParams()
    if (complexId) params.set("complex_id", complexId)
    else if (gu) params.set("gu", gu)
    if (scenario) params.set("scenario", scenario)
    try {
        const r = await fetch(`${base}/api/estate/brain?${params.toString()}`, { signal })
        if (!r.ok) {
            const j = await r.json().catch(() => ({}))
            return { ...MOCK_BRAIN, complex_id: complexId || gu || "unknown",
                error: j?.error || `HTTP ${r.status}` }
        }
        return await r.json()
    } catch (e: any) {
        if (e?.name === "AbortError") throw e
        return { ...MOCK_BRAIN, complex_id: complexId || gu || "unknown",
            error: "fetch_failed" }
    }
}


/* ◆ UTIL ◆ */
function verdictColor(v?: string): string {
    if (!v) return C.verdictBalanced
    if (v === "high" || v === "bubble" || v === "compressed" || v === "kb_lagging_bubble"
        || v === "negative_pressure" || v === "negative_pressure_strong"
        || v === "tightening_pressure" || v === "ambivalent_overheated"
        || v === "reverse_lease_risk" || v === "supply_overhang_in_2y") return C.verdictHigh
    if (v === "low" || v === "moderate_up") return C.verdictLow
    if (v === "very_high" || v === "attractive" || v === "supply_tight_in_2y"
        || v === "supportive" || v === "absorption" || v === "strong_up") return C.verdictAttractive
    return C.verdictBalanced
}

function formatWon(won?: number): string {
    if (!won && won !== 0) return "—"
    if (won >= 1e8) return `${(won / 1e8).toFixed(1)}억`
    if (won >= 1e4) return `${(won / 1e4).toFixed(0)}만`
    return won.toLocaleString()
}

const SIGNAL_LABELS: Record<string, string> = {
    pir_z_extreme: "PIR z+1σ 초과",
    jeonse_ratio_below_50: "전세가율 50% 미만",
    cap_treasury_inverted: "Cap-국고채 역전",
    kb_actual_gap_extreme: "KB-실거래 ±10%",
}
const ALL_SIGNALS = Object.keys(SIGNAL_LABELS)

const STAGE_ORDER = [
    "district_designation", "union_setup", "business_plan",
    "management_plan", "relocation", "completion",
] as const
const STAGE_LABELS: Record<string, string> = {
    district_designation: "정비구역", union_setup: "조합설립",
    business_plan: "사업시행", management_plan: "관리처분",
    relocation: "이주·철거", completion: "준공·입주",
}
const PRICE_PHASE_LABELS: Record<string, string> = {
    pre_signal: "초기 기대",
    max_uplift: "최대 상승",
    moderate_uplift: "완만 상승",
    mid_uplift: "중반 상승",
    post_peak_consolidation: "정점 후 조정",
    rental_market_spillover: "주변 전세 급등",
    new_build_premium: "신축 프리미엄",
}


/* ◆ Header ◆ */
function BrainHeader({ payload }: { payload: BrainPayload }) {
    const ws = payload.valuation.weighted_score ?? null
    const sigCount = payload.valuation.extreme_signals_count
    const sigColor = sigCount >= 3 ? C.verdictHigh : sigCount >= 2 ? C.verdictLow : C.verdictBalanced
    const wsColor = ws == null ? C.textTertiary
        : ws >= 70 ? C.verdictAttractive
        : ws >= 40 ? C.verdictBalanced : C.verdictHigh
    const isLive = payload.model_meta.source !== "v0_mock"

    return (
        <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between", gap: S.md,
            padding: S.lg, backgroundColor: C.bgCard,
            border: `1px solid ${C.border}`, borderLeft: `3px solid ${C.accent}`,
            borderRadius: R.md, ...MOTION,
        }}>
            <div style={{ display: "flex", flexDirection: "column", gap: S.xs, minWidth: 0 }}>
                <span style={{ fontSize: T.cap, color: C.textTertiary, textTransform: "uppercase", letterSpacing: 1 }}>
                    ESTATE BRAIN · v{payload.version}
                </span>
                <span style={{ fontSize: T.h2, fontWeight: T.w_bold, color: C.textPrimary,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {payload.complex_id}
                </span>
                <span style={{ fontSize: T.cap, color: C.textTertiary, ...MONO }}>
                    {payload.as_of?.slice(0, 19)}
                </span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: S.xs }}>
                <span style={{ fontSize: T.cap, color: C.textTertiary }}>weighted score</span>
                <div style={{ display: "flex", alignItems: "baseline", gap: S.sm }}>
                    <span style={{ fontSize: T.h0, fontWeight: T.w_bold, color: wsColor, ...MONO }}>
                        {ws == null ? "—" : ws.toFixed(1)}
                    </span>
                    <span style={{ fontSize: T.body, color: C.textTertiary }}>/ 100</span>
                </div>
                <div style={{ display: "flex", gap: S.xs }}>
                    <span style={{
                        padding: "2px 10px", borderRadius: R.sm,
                        background: sigColor + "1A", color: sigColor,
                        fontSize: T.cap, fontWeight: T.w_semi,
                    }}>
                        {sigCount}/4 신호
                    </span>
                    <span style={{
                        padding: "2px 10px", borderRadius: R.sm,
                        background: isLive ? C.verdictAttractive + "1A" : C.verdictBalanced + "1A",
                        color: isLive ? C.verdictAttractive : C.verdictBalanced,
                        fontSize: T.cap, fontWeight: T.w_semi,
                    }}>
                        {isLive ? "LIVE" : "MOCK"}
                    </span>
                </div>
            </div>
        </div>
    )
}


/* ◆ Section: Valuation 4 Layer ◆ */
function LayerCard({ title, layer, valueLabel }: {
    title: string; layer: Layer | null; valueLabel?: string
}) {
    const score = layer?.score
    const color = verdictColor(layer?.verdict)
    const w = score == null ? 0 : Math.max(0, Math.min(100, score))

    return (
        <div style={{
            display: "flex", flexDirection: "column", gap: S.sm,
            padding: S.md, backgroundColor: C.bgCard,
            border: `1px solid ${C.border}`, borderRadius: R.md, ...MOTION,
        }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span style={{ fontSize: T.cap, color: C.textTertiary, textTransform: "uppercase",
                    letterSpacing: 0.5 }}>{title}</span>
                {layer?.verdict && (
                    <span style={{
                        padding: "1px 8px", borderRadius: R.sm,
                        background: color + "1A", color, fontSize: T.cap - 1, fontWeight: T.w_semi,
                    }}>{layer.verdict}</span>
                )}
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: S.sm }}>
                <span style={{ fontSize: T.h2, fontWeight: T.w_bold, color: C.textPrimary, ...MONO }}>
                    {layer == null ? "—" : valueLabel ?? layer.value?.toFixed(2) ?? "—"}
                </span>
                {score != null && (
                    <span style={{ fontSize: T.cap, color: C.textTertiary, ...MONO }}>
                        score {score.toFixed(0)}
                    </span>
                )}
            </div>
            {/* score bar — picture book mini viz */}
            <div style={{ height: 4, background: C.bgInput, borderRadius: R.sm, overflow: "hidden" }}>
                <div style={{ width: `${w}%`, height: "100%", background: color, ...MOTION }} />
            </div>
        </div>
    )
}

function ValuationGrid({ valuation }: { valuation: Valuation }) {
    const l1 = valuation.layers.L1_pir
    const l2 = valuation.layers.L2_jeonse
    const l3 = valuation.layers.L3_cap_rate
    const l4 = valuation.layers.L4_neighbor

    return (
        <div style={{
            display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
            gap: S.md,
        }}>
            <LayerCard title="L4 인근 실거래 (45%)" layer={l4}
                valueLabel={l4?.gap_pct != null ? `${l4.gap_pct > 0 ? "+" : ""}${l4.gap_pct.toFixed(1)}%` : undefined} />
            <LayerCard title="L2 전세가율 (27.5%)" layer={l2}
                valueLabel={l2?.value != null ? `${l2.value.toFixed(1)}%` : undefined} />
            <LayerCard title="L3 Cap Rate (17.5%)" layer={l3}
                valueLabel={l3?.value != null ? `${l3.value.toFixed(2)}%` : undefined} />
            <LayerCard title="L1 PIR (10%)" layer={l1}
                valueLabel={l1?.value != null ? `${l1.value.toFixed(1)}x` : undefined} />
        </div>
    )
}


/* ◆ Section: Extreme Signals 4 chip ◆ */
function ExtremeSignalsStrip({ signals }: { signals: string[] }) {
    return (
        <div style={{
            display: "flex", flexDirection: "column", gap: S.sm,
            padding: S.lg, backgroundColor: C.bgCard,
            border: `1px solid ${C.border}`, borderRadius: R.md,
        }}>
            <span style={{ fontSize: T.cap, color: C.textTertiary, textTransform: "uppercase", letterSpacing: 1 }}>
                고평가 4중 신호
            </span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: S.sm }}>
                {ALL_SIGNALS.map(sig => {
                    const active = signals.includes(sig)
                    return (
                        <span key={sig} style={{
                            padding: "6px 12px", borderRadius: R.sm,
                            background: active ? C.verdictHigh + "1A" : C.bgInput,
                            color: active ? C.verdictHigh : C.textTertiary,
                            fontSize: T.cap, fontWeight: active ? T.w_bold : T.w_med,
                            border: `1px solid ${active ? C.verdictHigh + "40" : "transparent"}`,
                            ...MOTION,
                        }}>
                            {active ? "● " : "○ "}{SIGNAL_LABELS[sig]}
                        </span>
                    )
                })}
            </div>
        </div>
    )
}


/* ◆ Section: Cycle Analog + Lead Time mini ◆ */
function CycleAnalogCard({ cycle }: { cycle: CycleAnalog }) {
    return (
        <div style={{
            display: "flex", flexDirection: "column", gap: S.md,
            padding: S.lg, backgroundColor: C.bgCard,
            border: `1px solid ${C.border}`, borderRadius: R.md,
        }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span style={{ fontSize: T.cap, color: C.textTertiary, textTransform: "uppercase", letterSpacing: 1 }}>
                    Cycle Analog
                </span>
                <span style={{ fontSize: T.cap, color: C.accent, ...MONO }}>
                    forward {cycle.forward_return_horizon_weeks}w
                </span>
            </div>
            <span style={{ fontSize: T.title, fontWeight: T.w_bold, color: C.textPrimary }}>
                {cycle.current_phase}
            </span>
            {/* nearest 3 — picture book mini viz */}
            <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                {cycle.nearest_historical.slice(0, 3).map((h, i) => {
                    const w = Math.max(0, Math.min(100, (1 - h.distance) * 100))
                    return (
                        <div key={i} style={{ display: "flex", alignItems: "center", gap: S.sm }}>
                            <span style={{ fontSize: T.cap, color: C.textSecondary, minWidth: 200 }}>
                                {h.name} <span style={{ color: C.textTertiary }}>({h.year_label} · {h.shape})</span>
                            </span>
                            <div style={{ flex: 1, height: 3, background: C.bgInput, borderRadius: R.sm,
                                overflow: "hidden" }}>
                                <div style={{ width: `${w}%`, height: "100%", background: C.accent, ...MOTION }} />
                            </div>
                            <span style={{ fontSize: T.cap, color: C.textTertiary, ...MONO, minWidth: 50,
                                textAlign: "right" }}>
                                d={h.distance.toFixed(2)}
                            </span>
                        </div>
                    )
                })}
            </div>
            {/* lead time signals 5 mini */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                gap: S.sm, marginTop: S.xs }}>
                {Object.entries(cycle.lead_time_signals).map(([key, sig]) => {
                    const color = verdictColor(sig.verdict)
                    const v = sig.value_pct ?? sig.value_yoy_pct ?? sig.rate_change_pp
                    return (
                        <div key={key} style={{
                            padding: S.sm, background: C.bgElevated, borderRadius: R.sm,
                        }}>
                            <div style={{ fontSize: T.cap - 1, color: C.textTertiary,
                                marginBottom: 2 }}>
                                {key} <span style={{ color: C.accent }}>+{sig.lead_months}M</span>
                            </div>
                            <div style={{ display: "flex", alignItems: "baseline",
                                justifyContent: "space-between" }}>
                                <span style={{ fontSize: T.body, fontWeight: T.w_semi,
                                    color: C.textPrimary, ...MONO }}>
                                    {v != null ? (v > 0 ? "+" : "") + v.toFixed(1) : "—"}
                                </span>
                                <span style={{ fontSize: T.cap - 2, color, fontWeight: T.w_semi }}>
                                    {sig.verdict}
                                </span>
                            </div>
                        </div>
                    )
                })}
            </div>
        </div>
    )
}


/* ◆ Section: Redevelopment Stage (있을 때만) ◆ */
function RedevStageCard({ redev }: { redev: RedevelopmentStage }) {
    const idx = STAGE_ORDER.indexOf(redev.stage as any)
    const phaseLabel = PRICE_PHASE_LABELS[redev.price_phase] ?? redev.price_phase
    const phaseColor = redev.price_phase === "max_uplift" ? C.verdictAttractive
        : redev.price_phase === "rental_market_spillover" ? C.accent
        : redev.price_phase === "post_peak_consolidation" ? C.verdictLow
        : C.verdictBalanced

    return (
        <div style={{
            display: "flex", flexDirection: "column", gap: S.md,
            padding: S.lg, backgroundColor: C.bgCard,
            border: `1px solid ${C.border}`, borderLeft: `3px solid ${phaseColor}`,
            borderRadius: R.md,
        }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span style={{ fontSize: T.cap, color: C.textTertiary, textTransform: "uppercase", letterSpacing: 1 }}>
                    재{redev.project_type === "reconstruction" ? "건축" : "개발"} · 6 단계
                </span>
                <span style={{
                    padding: "2px 10px", borderRadius: R.sm,
                    background: phaseColor + "1A", color: phaseColor,
                    fontSize: T.cap, fontWeight: T.w_semi,
                }}>{phaseLabel}</span>
            </div>
            <span style={{ fontSize: T.title, fontWeight: T.w_bold, color: C.textPrimary }}>
                {redev.stage_label_ko}
            </span>
            {/* 6 stage 사다리 — picture book mini viz */}
            <div style={{ display: "flex", gap: 2 }}>
                {STAGE_ORDER.map((s, i) => {
                    const past = i < idx
                    const current = i === idx
                    return (
                        <div key={s} style={{
                            flex: 1, padding: `${S.xs}px ${S.sm}px`,
                            background: current ? phaseColor + "33"
                                : past ? C.bgElevated : C.bgInput,
                            color: current ? phaseColor : past ? C.textSecondary : C.textTertiary,
                            border: current ? `1px solid ${phaseColor}` : "1px solid transparent",
                            borderRadius: R.sm,
                            textAlign: "center", fontSize: T.cap - 1,
                            fontWeight: current ? T.w_bold : T.w_med,
                            ...MOTION,
                        }}>
                            {STAGE_LABELS[s]}
                        </div>
                    )
                })}
            </div>
            <div style={{ display: "flex", gap: S.lg, fontSize: T.cap, color: C.textSecondary }}>
                <span>현 단계 진행: <strong style={{ color: C.textPrimary, ...MONO }}>{redev.months_in_stage}M</strong></span>
                <span>다음 단계까지: <strong style={{ color: C.textPrimary, ...MONO }}>{redev.months_to_next_stage_estimated}M</strong></span>
            </div>
            {(redev.monitoring.valuation_announcement_pending ||
              redev.monitoring.general_subscription_announced) && (
                <div style={{ display: "flex", gap: S.sm, flexWrap: "wrap" }}>
                    {redev.monitoring.valuation_announcement_pending && (
                        <span style={{ padding: "4px 10px", borderRadius: R.sm,
                            background: C.accent + "1A", color: C.accent,
                            fontSize: T.cap, fontWeight: T.w_semi }}>
                            ⚠ 종전자산평가 발표 대기
                        </span>
                    )}
                    {redev.monitoring.general_subscription_announced && (
                        <span style={{ padding: "4px 10px", borderRadius: R.sm,
                            background: C.info + "1A", color: C.info,
                            fontSize: T.cap, fontWeight: T.w_semi }}>
                            ◉ 일반분양 공고
                        </span>
                    )}
                </div>
            )}
        </div>
    )
}


/* ◆ Source / Diagnostics footer ◆ */
function MetaFooter({ payload }: { payload: BrainPayload }) {
    const meta = payload.snapshot_meta
    if (!meta) return null
    const diag = meta.diagnostics ?? {}
    const sources = [
        ["ECOS",   diag.ecos_available],
        ["KOSIS",  diag.kosis_available],
        ["R-ONE 전세", diag.rone_jeonse_available],
        ["R-ONE 미분양", diag.rone_unsold_available],
    ] as Array<[string, boolean | undefined]>

    return (
        <div style={{
            display: "flex", flexWrap: "wrap", alignItems: "center", gap: S.sm,
            padding: `${S.sm}px ${S.md}px`,
            fontSize: T.cap, color: C.textTertiary, ...MONO,
        }}>
            <span>snapshot {meta.generated_at?.slice(0, 19) ?? "—"}</span>
            <span style={{ color: C.textDisabled }}>·</span>
            {sources.map(([label, ok]) => (
                <span key={label} style={{
                    color: ok ? C.verdictAttractive : C.textTertiary,
                }}>
                    {ok ? "●" : "○"} {label}
                </span>
            ))}
        </div>
    )
}


/* ◆ URL param 우선 — drill-down wiring (WatchComplexesDashboard 카드 클릭 진입) ◆ */
type ScenarioKey = "live" | "mock_balanced" | "mock_high_pir" | "mock_redev_uplift"

function readUrlContext(): { complexId?: string; gu?: string; scenario?: ScenarioKey } {
    if (typeof window === "undefined") return {}
    try {
        const search = new URLSearchParams(window.location.search)
        const ctx: { complexId?: string; gu?: string; scenario?: ScenarioKey } = {}
        if (search.get("complex_id")) ctx.complexId = search.get("complex_id")!
        else if (search.get("gu")) ctx.gu = search.get("gu")!
        const sc = search.get("scenario")
        if (sc && ["live", "mock_balanced", "mock_high_pir", "mock_redev_uplift"].includes(sc)) {
            ctx.scenario = sc as ScenarioKey
        }
        if (ctx.complexId || ctx.gu || ctx.scenario) return ctx
        // hash 경로: #complex_id=... 또는 #gu=... 또는 #scenario=...
        const hash = (window.location.hash || "").replace(/^#/, "")
        if (hash) {
            const hashParams = new URLSearchParams(hash)
            if (hashParams.get("complex_id")) ctx.complexId = hashParams.get("complex_id")!
            else if (hashParams.get("gu")) ctx.gu = hashParams.get("gu")!
            const hsc = hashParams.get("scenario")
            if (hsc && ["live", "mock_balanced", "mock_high_pir", "mock_redev_uplift"].includes(hsc)) {
                ctx.scenario = hsc as ScenarioKey
            }
        }
    } catch {}
    return {}
}

/* ◆ Gu push — feedback_in_component_interactivity 정합 (사이트 내 셀렉터 → URL sync) ◆ */
function pushGuToUrl(gu: string): void {
    if (typeof window === "undefined") return
    try {
        const url = new URL(window.location.href)
        url.searchParams.delete("complex_id")
        url.searchParams.set("gu", gu)
        window.history.pushState({ gu }, "", url.toString())
    } catch {}
}

/* ◆ Scenario push — 2026-05-12 audit fix (HIGH #9): props 전용 → URL sync 사이트 내 셀렉터.
   feedback_in_component_interactivity 정합 — Framer 편집창 의존 폐기 ◆ */
function pushScenarioToUrl(scenario: ScenarioKey): void {
    if (typeof window === "undefined") return
    try {
        const url = new URL(window.location.href)
        url.searchParams.set("scenario", scenario)
        window.history.pushState({ scenario }, "", url.toString())
    } catch {}
}

const SEOUL_25_GU = [
    "강남구", "서초구", "송파구", "강동구", "마포구",
    "용산구", "성동구", "광진구", "중구", "종로구",
    "서대문구", "은평구", "강서구", "양천구", "영등포구",
    "구로구", "금천구", "관악구", "동작구", "성북구",
    "동대문구", "중랑구", "노원구", "도봉구", "강북구",
]

/* ◆ GuSelector — 누르면 펼쳐지는 dropdown (사이트 내 토글, Framer 편집창 의존 폐기) ◆ */
function GuSelector({ value, onChange }: { value: string | null; onChange: (gu: string) => void }) {
    const [open, setOpen] = useState(false)
    const wrapRef = React.useRef<HTMLDivElement>(null)

    useEffect(() => {
        if (!open) return
        const onDocClick = (e: MouseEvent) => {
            if (!wrapRef.current?.contains(e.target as Node)) setOpen(false)
        }
        const onEsc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false) }
        document.addEventListener("mousedown", onDocClick)
        document.addEventListener("keydown", onEsc)
        return () => {
            document.removeEventListener("mousedown", onDocClick)
            document.removeEventListener("keydown", onEsc)
        }
    }, [open])

    return (
        <div ref={wrapRef} style={{ position: "relative", alignSelf: "flex-start" }}>
            <button
                onClick={() => setOpen(o => !o)}
                style={{
                    ...MOTION,
                    display: "inline-flex", alignItems: "center", gap: S.sm,
                    padding: `${S.sm}px ${S.md}px`,
                    background: C.bgCard,
                    border: `1px solid ${value ? C.accent : C.borderStrong}`,
                    borderRadius: R.md,
                    color: value ? C.accentBright : C.textSecondary,
                    fontSize: T.body, fontWeight: T.w_semi,
                    fontFamily: FONT, cursor: "pointer", minWidth: 140,
                }}
            >
                <span style={{ fontSize: T.cap, color: C.textTertiary, fontWeight: T.w_med }}>구</span>
                <span style={{ flex: 1, textAlign: "left" }}>{value ?? "선택"}</span>
                <span style={{ ...MOTION, transform: open ? "rotate(180deg)" : "rotate(0deg)" }}>▾</span>
            </button>
            {open && (
                <div style={{
                    position: "absolute", top: "calc(100% + 4px)", left: 0, zIndex: 10,
                    minWidth: 160, maxHeight: 280, overflowY: "auto",
                    background: C.bgElevated,
                    border: `1px solid ${C.borderStrong}`,
                    borderRadius: R.md,
                    padding: S.xs,
                    boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                }}>
                    {SEOUL_25_GU.map(name => {
                        const active = value === name
                        return (
                            <button
                                key={name}
                                onClick={() => { onChange(name); setOpen(false) }}
                                style={{
                                    ...MOTION,
                                    display: "block", width: "100%", textAlign: "left",
                                    padding: `${S.sm}px ${S.md}px`,
                                    background: active ? C.accentSoft : "transparent",
                                    border: "none", borderRadius: R.sm,
                                    color: active ? C.accentBright : C.textPrimary,
                                    fontSize: T.body, fontWeight: active ? T.w_semi : T.w_med,
                                    fontFamily: FONT, cursor: "pointer",
                                }}
                                onMouseEnter={(e) => {
                                    if (!active) (e.currentTarget as HTMLButtonElement).style.background = C.bgInput
                                }}
                                onMouseLeave={(e) => {
                                    if (!active) (e.currentTarget as HTMLButtonElement).style.background = "transparent"
                                }}
                            >{name}</button>
                        )
                    })}
                </div>
            )}
        </div>
    )
}


/* ◆ ScenarioSelector — 2026-05-12 audit fix (HIGH #9). GuSelector 패턴 차용.
   feedback_in_component_interactivity 정합 — props 전용 폐기, 사이트 내 셀렉터 + URL sync ◆ */
const SCENARIO_OPTIONS: { key: ScenarioKey; label: string }[] = [
    { key: "live", label: "LIVE" },
    { key: "mock_balanced", label: "Mock 균형" },
    { key: "mock_high_pir", label: "Mock 고PIR" },
    { key: "mock_redev_uplift", label: "Mock 재건축" },
]

function ScenarioSelector({ value, onChange }: { value: ScenarioKey; onChange: (s: ScenarioKey) => void }) {
    const [open, setOpen] = useState(false)
    const wrapRef = React.useRef<HTMLDivElement>(null)

    useEffect(() => {
        if (!open) return
        const onDocClick = (e: MouseEvent) => {
            if (!wrapRef.current?.contains(e.target as Node)) setOpen(false)
        }
        const onEsc = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false) }
        document.addEventListener("mousedown", onDocClick)
        document.addEventListener("keydown", onEsc)
        return () => {
            document.removeEventListener("mousedown", onDocClick)
            document.removeEventListener("keydown", onEsc)
        }
    }, [open])

    const current = SCENARIO_OPTIONS.find(o => o.key === value) ?? SCENARIO_OPTIONS[0]

    return (
        <div ref={wrapRef} style={{ position: "relative", alignSelf: "flex-start" }}>
            <button
                onClick={() => setOpen(o => !o)}
                style={{
                    ...MOTION,
                    display: "inline-flex", alignItems: "center", gap: S.sm,
                    padding: `${S.sm}px ${S.md}px`,
                    background: C.bgCard,
                    border: `1px solid ${value !== "live" ? C.accent : C.borderStrong}`,
                    borderRadius: R.md,
                    color: value !== "live" ? C.accentBright : C.textSecondary,
                    fontSize: T.body, fontWeight: T.w_semi,
                    fontFamily: FONT, cursor: "pointer", minWidth: 160,
                }}
            >
                <span style={{ fontSize: T.cap, color: C.textTertiary, fontWeight: T.w_med }}>시나리오</span>
                <span style={{ flex: 1, textAlign: "left" }}>{current.label}</span>
                <span style={{ ...MOTION, transform: open ? "rotate(180deg)" : "rotate(0deg)" }}>▾</span>
            </button>
            {open && (
                <div style={{
                    position: "absolute", top: "calc(100% + 4px)", left: 0, zIndex: 10,
                    minWidth: 180,
                    background: C.bgElevated,
                    border: `1px solid ${C.borderStrong}`,
                    borderRadius: R.md,
                    padding: S.xs,
                    boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                }}>
                    {SCENARIO_OPTIONS.map(opt => {
                        const active = value === opt.key
                        return (
                            <button
                                key={opt.key}
                                onClick={() => { onChange(opt.key); setOpen(false) }}
                                style={{
                                    ...MOTION,
                                    display: "block", width: "100%", textAlign: "left",
                                    padding: `${S.sm}px ${S.md}px`,
                                    background: active ? C.accentSoft : "transparent",
                                    border: "none", borderRadius: R.sm,
                                    color: active ? C.accentBright : C.textPrimary,
                                    fontSize: T.body, fontWeight: active ? T.w_semi : T.w_med,
                                    fontFamily: FONT, cursor: "pointer",
                                }}
                                onMouseEnter={(e) => {
                                    if (!active) (e.currentTarget as HTMLButtonElement).style.background = C.bgInput
                                }}
                                onMouseLeave={(e) => {
                                    if (!active) (e.currentTarget as HTMLButtonElement).style.background = "transparent"
                                }}
                            >{opt.label}</button>
                        )
                    })}
                </div>
            )}
        </div>
    )
}


/* ◆ MAIN ◆ */
interface Props {
    apiUrl: string
    complexId: string
    gu: string
    scenario: ScenarioKey
}

export default function EstateBrainPanel(props: Props) {
    const { apiUrl } = props
    // URL param 우선 — Framer 페이지 wiring (Map/Watchlist → Brain drill-down) + scenario 사이트 내 셀렉터.
    const [urlCtx, setUrlCtx] = useState<{ complexId?: string; gu?: string; scenario?: ScenarioKey }>(() => readUrlContext())
    const effectiveComplexId = urlCtx.complexId ?? props.complexId
    const effectiveGu = urlCtx.gu ?? props.gu
    const effectiveScenario: ScenarioKey = urlCtx.scenario ?? props.scenario ?? "live"

    const [payload, setPayload] = useState<BrainPayload | null>(null)
    const [loading, setLoading] = useState(false)
    const [err, setErr] = useState<string | null>(null)

    // popstate / hashchange 감지 — 사용자 뒤로가기 / 새 단지 클릭 시 즉시 갱신
    useEffect(() => {
        if (typeof window === "undefined") return
        const onChange = () => setUrlCtx(readUrlContext())
        window.addEventListener("popstate", onChange)
        window.addEventListener("hashchange", onChange)
        return () => {
            window.removeEventListener("popstate", onChange)
            window.removeEventListener("hashchange", onChange)
        }
    }, [])

    useEffect(() => {
        const ctl = new AbortController()
        let cancelled = false
        setLoading(true); setErr(null)
        fetchBrain(apiUrl, effectiveComplexId, effectiveGu, effectiveScenario, ctl.signal)
            .then(p => { if (!cancelled) { setPayload(p); setErr(p.error ?? null) } })
            .catch(e => { if (!cancelled && e?.name !== "AbortError") setErr("fetch_failed") })
            .finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true; ctl.abort() }
    }, [apiUrl, effectiveComplexId, effectiveGu, effectiveScenario])

    const view = payload ?? MOCK_BRAIN

    return (
        <div style={{
            display: "flex", flexDirection: "column", gap: S.md,
            padding: S.lg, backgroundColor: C.bgPage,
            fontFamily: FONT, color: C.textPrimary,
            width: "100%", boxSizing: "border-box",
        }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: S.sm }}>
                <GuSelector
                    value={effectiveGu || null}
                    onChange={(gu) => {
                        pushGuToUrl(gu)
                        setUrlCtx(prev => ({ ...prev, complexId: undefined, gu }))
                    }}
                />
                <ScenarioSelector
                    value={effectiveScenario}
                    onChange={(scenario) => {
                        pushScenarioToUrl(scenario)
                        setUrlCtx(prev => ({ ...prev, scenario }))
                    }}
                />
            </div>
            <BrainHeader payload={view} />
            {err && (
                <div style={{
                    padding: `${S.sm}px ${S.md}px`, borderRadius: R.sm,
                    background: C.verdictHigh + "1A", color: C.verdictHigh,
                    fontSize: T.cap, fontWeight: T.w_semi,
                }}>⚠ {err}</div>
            )}
            <ValuationGrid valuation={view.valuation} />
            <ExtremeSignalsStrip signals={view.valuation.extreme_signals} />
            <CycleAnalogCard cycle={view.cycle_analog} />
            {view.redevelopment_stage && (
                <RedevStageCard redev={view.redevelopment_stage} />
            )}
            <MetaFooter payload={view} />
        </div>
    )
}


/* ◆ FRAMER PROPERTY CONTROLS ◆ */
addPropertyControls(EstateBrainPanel, {
    apiUrl: {
        type: ControlType.String,
        title: "API URL",
        defaultValue: "https://project-yw131.vercel.app",
        description: "vercel-api base. /api/estate/brain 자동 부착.",
    },
    complexId: {
        type: ControlType.String,
        title: "Complex ID",
        defaultValue: "강남구_대치동_은마_1979",
        description: "단지 ID (clustering make_complex_id 산출).",
    },
    gu: {
        type: ControlType.String,
        title: "Gu (fallback)",
        defaultValue: "",
        description: "complex_id 비어있을 때 구 단위 aggregate.",
    },
    scenario: {
        type: ControlType.Enum,
        title: "Scenario",
        defaultValue: "live",
        options: ["live", "mock_balanced", "mock_high_pir", "mock_redev_uplift"],
        optionTitles: ["LIVE", "Mock balanced", "Mock high_pir", "Mock redev_uplift"],
    },
})
