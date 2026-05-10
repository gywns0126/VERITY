import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useMemo, useState } from "react"

/* ──────────────────────────────────────────────────────────────
 * ◆ ESTATE 패밀리룩 v3 — Cluster A warm gold (정합)
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0A0908", bgCard: "#0F0D0A", bgElevated: "#16130E",
    border: "transparent", borderStrong: "#3A3024",
    textPrimary: "#F2EFE9", textSecondary: "#A8A299", textTertiary: "#6B665E",
    accent: "#B8864D", accentSoft: "rgba(184,134,77,0.15)",
    success: "#22C55E", warn: "#F59E0B", danger: "#EF4444", info: "#5BA9FF",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }


/*
 * SupplyPipelineMonitor — 국토교통부 주택건설 4 단계 supply pipeline 시각화.
 *
 * Source: data/estate_brain_snapshots.json (estate_brain_builder commit 56b60e0 산출).
 *   payload.supply_pipeline = {
 *     construction_permits: {series, series_monthly_new, source, ...},
 *     construction_starts:  {series, source, ...},
 *     construction_completions: ...,
 *     subscription_apt: ...,
 *   }
 *
 * feedback_component_overlap_audit: LandexPulse / ScoreDetailPanel 은 *미분양 1종*
 *   chart 만 표시 — *4종 통합 supply pipeline view* 부재 → 신설 정당.
 * feedback_estate_density_first: 200줄 안쪽 (terminal 광범위 패턴 X).
 * feedback_no_hardcode_position: position:fixed 하드코드 X — Framer 직접 배치.
 */


interface SeriesRow {
    month: string
    value: number
    [k: string]: any
}

interface SourceBlock {
    series?: SeriesRow[]
    series_monthly_new?: SeriesRow[]  // permits 만 보유 (월별 누계 → 신규 변환)
    source?: string
    as_of?: string
    stat_id?: string
    n_points?: number
}

interface BrainSnapshots {
    generated_at?: string
    supply_pipeline?: {
        construction_permits?: SourceBlock | null
        construction_starts?: SourceBlock | null
        construction_completions?: SourceBlock | null
        subscription_apt?: SourceBlock | null
    }
    diagnostics?: { supply_pipeline_sources_available?: number }
}


function fetchJson(url: string, signal?: AbortSignal): Promise<BrainSnapshots> {
    const u = (url || "").trim()
    const sep = u.includes("?") ? "&" : "?"
    return fetch(`${u}${sep}_=${Date.now()}`, {
        cache: "no-store", mode: "cors", credentials: "omit", signal,
    }).then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
    })
}


function fmtMonth(m: string | undefined): string {
    if (!m || m.length < 6) return "—"
    return `${m.slice(0, 4)}.${m.slice(4)}`
}

function fmtNum(v: number | undefined): string {
    if (v == null) return "—"
    if (v >= 10000) return `${(v / 10000).toFixed(1)}만`
    if (v >= 1000) return `${(v / 1000).toFixed(1)}천`
    return Math.round(v).toLocaleString()
}


// 4 source 라벨 + lead 의미 (Plan v0.2 lead time table 정합).
const SOURCE_META: Array<{ key: string; label_ko: string; meaning: string; unit: string }> = [
    { key: "construction_permits",    label_ko: "인허가",   meaning: "공급 잠재 (1~3년 후 착공)",     unit: "호" },
    { key: "construction_starts",     label_ko: "착공",     meaning: "lead 28M (+ signal)",          unit: "호" },
    { key: "construction_completions", label_ko: "준공",     meaning: "준공 → 1~3M 후 입주 supply",   unit: "호" },
    { key: "subscription_apt",        label_ko: "분양",     meaning: "공동주택 신규 가구수",         unit: "가구" },
]


interface Props {
    dataUrl: string
    refreshIntervalSec: number
    usePermitsMonthlyNew: boolean
}

export default function SupplyPipelineMonitor({
    dataUrl, refreshIntervalSec, usePermitsMonthlyNew,
}: Props) {
    const [data, setData] = useState<BrainSnapshots | null>(null)
    const [err, setErr] = useState<string | null>(null)

    useEffect(() => {
        if (!dataUrl) return
        const ctl = new AbortController()
        const tick = () => {
            fetchJson(dataUrl, ctl.signal)
                .then((p) => { setData(p); setErr(null) })
                .catch((e) => { if (e?.name !== "AbortError") setErr(e?.message || "fetch failed") })
        }
        tick()
        const id = window.setInterval(tick, Math.max(60, refreshIntervalSec) * 1000)
        return () => { ctl.abort(); window.clearInterval(id) }
    }, [dataUrl, refreshIntervalSec])

    const sp = data?.supply_pipeline
    const rows = useMemo(() => {
        if (!sp) return []
        return SOURCE_META.map((meta) => {
            const block = (sp as any)[meta.key] as SourceBlock | null | undefined
            // permits 는 usePermitsMonthlyNew 옵션에 따라 series 또는 series_monthly_new 사용
            const useNew = meta.key === "construction_permits" && usePermitsMonthlyNew
            const series = useNew
                ? (block?.series_monthly_new || block?.series || [])
                : (block?.series || [])
            const last = series.length ? series[series.length - 1] : undefined
            return {
                ...meta,
                series, last, available: !!block,
                isMonthlyNew: useNew,
            }
        })
    }, [sp, usePermitsMonthlyNew])

    const sourcesAvailable = data?.diagnostics?.supply_pipeline_sources_available ?? 0

    return (
        <div style={{
            display: "flex", flexDirection: "column", gap: 12,
            padding: 16, borderRadius: 10,
            background: C.bgCard, border: `1px solid ${C.border}`,
            fontFamily: FONT, color: C.textPrimary, width: "100%", boxSizing: "border-box",
        }}>
            {/* 헤더 */}
            <div style={{ display: "flex", alignItems: "baseline",
                justifyContent: "space-between" }}>
                <div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: C.textPrimary }}>
                        Supply Pipeline 4단계
                    </div>
                    <div style={{ fontSize: 11, color: C.textTertiary, marginTop: 2 }}>
                        국토교통부 KOSIS · 전국 아파트 · 최근 3개월
                    </div>
                </div>
                <span style={{ ...MONO, fontSize: 10, color: C.textTertiary }}>
                    {sourcesAvailable}/4 source · {data?.generated_at?.slice(0, 10) || "—"}
                </span>
            </div>

            {err && (
                <div style={{
                    padding: "8px 10px", borderRadius: 6,
                    background: `${C.danger}15`, color: C.danger,
                    fontSize: 11, fontWeight: 600,
                }}>⚠ {err}</div>
            )}

            {/* 4 단계 행 */}
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {rows.map((r) => (
                    <div key={r.key} style={{
                        display: "grid",
                        gridTemplateColumns: "auto 1fr auto auto",
                        gap: 12,
                        alignItems: "center",
                        padding: "8px 10px", borderRadius: 6,
                        background: r.available ? C.bgElevated : "transparent",
                        opacity: r.available ? 1 : 0.5,
                    }}>
                        <div>
                            <div style={{ fontSize: 13, fontWeight: 600, color: C.textPrimary }}>
                                {r.label_ko}
                                {r.isMonthlyNew && (
                                    <span style={{ ...MONO, fontSize: 9, color: C.accent,
                                        marginLeft: 6, fontWeight: 700 }}>
                                        Δ월별
                                    </span>
                                )}
                            </div>
                            <div style={{ fontSize: 10, color: C.textTertiary, marginTop: 1 }}>
                                {r.meaning}
                            </div>
                        </div>

                        {/* 최근 3 month mini-bar */}
                        <div style={{ display: "flex", gap: 4, alignItems: "flex-end",
                            height: 28 }}>
                            {(() => {
                                const visible = r.series.slice(-3)
                                const maxVal = Math.max(...visible.map((s) => s.value), 1)
                                return visible.map((s, i) => (
                                    <div key={i} style={{ display: "flex", flexDirection: "column",
                                        alignItems: "center", gap: 2, flex: 1, maxWidth: 50 }}>
                                        <div style={{
                                            width: "100%",
                                            height: Math.max(2, (s.value / maxVal) * 24),
                                            background: C.accent, borderRadius: 2,
                                            opacity: 0.3 + (i + 1) / visible.length * 0.7,
                                        }} />
                                        <span style={{ ...MONO, fontSize: 9, color: C.textTertiary }}>
                                            {s.month?.slice(4)}
                                        </span>
                                    </div>
                                ))
                            })()}
                        </div>

                        {/* 최근 값 */}
                        <span style={{ ...MONO, fontSize: 13, fontWeight: 600,
                            color: C.textPrimary, textAlign: "right" }}>
                            {fmtNum(r.last?.value)}
                        </span>
                        <span style={{ fontSize: 10, color: C.textTertiary }}>
                            {r.unit}
                        </span>
                    </div>
                ))}
            </div>

            <div style={{
                fontSize: 10, color: C.textTertiary, lineHeight: 1.5,
                paddingTop: 8, borderTop: `1px solid ${C.borderStrong}`,
            }}>
                V0 — 3개월 raw window (KOSIS row limit). 권역별 / 주택유형별 확장 V1 큐.
                인허가는 *월별 누계* (yearly-to-date) — Δ월별 토글 시 신규 변환값.
            </div>
        </div>
    )
}


SupplyPipelineMonitor.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/estate_brain_snapshots.json",
    refreshIntervalSec: 3600,
    usePermitsMonthlyNew: true,
}

addPropertyControls(SupplyPipelineMonitor, {
    dataUrl: {
        type: ControlType.String,
        title: "Data URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/estate_brain_snapshots.json",
        description: "estate_brain_snapshots.json publish URL",
    },
    refreshIntervalSec: {
        type: ControlType.Number,
        title: "Refresh (sec)",
        defaultValue: 3600,
        min: 60, max: 86400, step: 60,
    },
    usePermitsMonthlyNew: {
        type: ControlType.Boolean,
        title: "인허가: 월별 신규",
        defaultValue: true,
        description: "true=Δ월별 (1월=그대로, 차분), false=raw 누계",
    },
})
