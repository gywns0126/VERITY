import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useMemo, useState } from "react"

/* ──────────────────────────────────────────────────────────────
 * ◆ ESTATE 패밀리룩 v3 — Cluster A warm gold tone (정합)
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0A0908", bgCard: "#0F0D0A", bgElevated: "#16130E",
    border: "transparent", borderStrong: "#3A3024",
    textPrimary: "#F2EFE9", textSecondary: "#A8A299", textTertiary: "#6B665E",
    accent: "#B8864D", accentSoft: "rgba(184,134,77,0.15)",
    success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }


/*
 * RegionalCycleTimingPanel — KOSIS REB 9 권역 cycle timing 비교 시각화.
 *
 * Source: data/estate_brain_backtest_50y.json (estate_brain_backtest_50y_builder
 * commit fff1728 산출). publish-data action 으로 gh-pages publish.
 *
 * Plan v0.2 "핵심지 선행" 가설 직접 검증 view — 권역별 peak / trough / drop /
 * duration. leader (가장 빠른 시점 권역) 강조.
 *
 * feedback_component_overlap_audit: EstateBrainPanel = 단지 detail / SystemPulse =
 * home 단편 → 권역별 cycle timing 시각화 부재 → 신설 정당.
 * feedback_estate_density_first: 200줄 안쪽 (terminal 광범위 패턴 이식 X).
 * feedback_no_hardcode_position: position:fixed 하드코드 X — Framer 사용자 배치.
 */


interface RegionTiming {
    peak_label: string | null
    trough_label: string | null
    drop_pct: number | null
    duration_months: number | null
}

interface RegionalTiming {
    per_region: Record<string, RegionTiming>
    n_regions_with_cycle: number
    leader_peak: string | null
    leader_trough: string | null
}

interface BacktestPayload {
    schema_version?: string
    generated_at?: string
    regional_timing?: RegionalTiming
}


function fetchJson(url: string, signal?: AbortSignal): Promise<BacktestPayload> {
    const u = (url || "").trim()
    const sep = u.includes("?") ? "&" : "?"
    return fetch(`${u}${sep}_=${Date.now()}`, {
        cache: "no-store", mode: "cors", credentials: "omit", signal,
    }).then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
    })
}


function fmtDate(label: string | null): string {
    // YYYYMM → YYYY.MM, YYYYQN 그대로, 그 외 그대로
    if (!label) return "—"
    if (/^\d{6}$/.test(label)) return `${label.slice(0, 4)}.${label.slice(4)}`
    return label
}

function fmtDrop(pct: number | null): string {
    if (pct == null) return "—"
    return `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%`
}


interface Props {
    dataUrl: string
    refreshIntervalSec: number
}

export default function RegionalCycleTimingPanel({ dataUrl, refreshIntervalSec }: Props) {
    const [payload, setPayload] = useState<BacktestPayload | null>(null)
    const [err, setErr] = useState<string | null>(null)

    useEffect(() => {
        if (!dataUrl) return
        const ctl = new AbortController()
        const tick = () => {
            fetchJson(dataUrl, ctl.signal)
                .then((p) => { setPayload(p); setErr(null) })
                .catch((e) => { if (e?.name !== "AbortError") setErr(e?.message || "fetch failed") })
        }
        tick()
        const id = window.setInterval(tick, Math.max(60, refreshIntervalSec) * 1000)
        return () => { ctl.abort(); window.clearInterval(id) }
    }, [dataUrl, refreshIntervalSec])

    const rt = payload?.regional_timing
    const regions = useMemo(() => {
        if (!rt?.per_region) return [] as Array<{ name: string } & RegionTiming>
        return Object.entries(rt.per_region).map(([name, t]) => ({ name, ...t }))
            .sort((a, b) => {
                // peak 빠른 순 정렬 (leader 우선)
                if (!a.peak_label) return 1
                if (!b.peak_label) return -1
                return a.peak_label.localeCompare(b.peak_label)
            })
    }, [rt])

    return (
        <div style={{
            display: "flex", flexDirection: "column", gap: 12,
            padding: 16, borderRadius: 10,
            background: C.bgCard, border: `1px solid ${C.border}`,
            fontFamily: FONT, color: C.textPrimary, width: "100%", boxSizing: "border-box",
        }}>
            {/* 헤더 */}
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
                <div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: C.textPrimary }}>
                        9 권역 Cycle Timing
                    </div>
                    <div style={{ fontSize: 11, color: C.textTertiary, marginTop: 2 }}>
                        KOSIS REB 공동주택 매매 실거래가격지수 · 2006~ 월간
                    </div>
                </div>
                {payload?.generated_at && (
                    <span style={{ ...MONO, fontSize: 10, color: C.textTertiary }}>
                        {payload.generated_at.slice(0, 10)}
                    </span>
                )}
            </div>

            {err && (
                <div style={{
                    padding: "8px 10px", borderRadius: 6,
                    background: `${C.danger}15`, color: C.danger,
                    fontSize: 11, fontWeight: 600,
                }}>⚠ {err}</div>
            )}

            {/* leader 라인 */}
            {rt && (rt.leader_peak || rt.leader_trough) && (
                <div style={{ display: "flex", gap: 14, flexWrap: "wrap",
                    fontSize: 12, color: C.textSecondary }}>
                    {rt.leader_peak && (
                        <span>
                            먼저 peak: <strong style={{ color: C.accent, ...MONO }}>{rt.leader_peak}</strong>
                        </span>
                    )}
                    {rt.leader_trough && (
                        <span>
                            먼저 trough: <strong style={{ color: C.accent, ...MONO }}>{rt.leader_trough}</strong>
                        </span>
                    )}
                </div>
            )}

            {/* 권역 표 */}
            <div style={{
                display: "grid",
                gridTemplateColumns: "1fr auto auto auto auto",
                gap: "6px 14px",
                fontSize: 12, alignItems: "center",
            }}>
                <span style={{ fontSize: 10, color: C.textTertiary, fontWeight: 600,
                    letterSpacing: "0.05em" }}>권역</span>
                <span style={{ fontSize: 10, color: C.textTertiary, fontWeight: 600,
                    textAlign: "right" }}>peak</span>
                <span style={{ fontSize: 10, color: C.textTertiary, fontWeight: 600,
                    textAlign: "right" }}>trough</span>
                <span style={{ fontSize: 10, color: C.textTertiary, fontWeight: 600,
                    textAlign: "right" }}>drop</span>
                <span style={{ fontSize: 10, color: C.textTertiary, fontWeight: 600,
                    textAlign: "right" }}>dur</span>

                {regions.map((r) => {
                    const isLeaderPeak = rt?.leader_peak === r.name
                    const isLeaderTrough = rt?.leader_trough === r.name
                    const drop = r.drop_pct
                    const dropColor = drop != null && drop <= -20 ? C.danger
                        : drop != null && drop <= -10 ? C.warn
                        : C.textPrimary
                    return (
                        <React.Fragment key={r.name}>
                            <span style={{ color: C.textPrimary, fontWeight: 500 }}>
                                {r.name}
                                {isLeaderPeak && (
                                    <span style={{ ...MONO, fontSize: 9, color: C.accent,
                                        marginLeft: 6, fontWeight: 700 }}>
                                        ▲peak
                                    </span>
                                )}
                                {isLeaderTrough && (
                                    <span style={{ ...MONO, fontSize: 9, color: C.accent,
                                        marginLeft: 6, fontWeight: 700 }}>
                                        ▲trough
                                    </span>
                                )}
                            </span>
                            <span style={{ ...MONO, color: C.textSecondary, textAlign: "right" }}>
                                {fmtDate(r.peak_label)}
                            </span>
                            <span style={{ ...MONO, color: C.textSecondary, textAlign: "right" }}>
                                {fmtDate(r.trough_label)}
                            </span>
                            <span style={{ ...MONO, color: dropColor, textAlign: "right",
                                fontWeight: 600 }}>
                                {fmtDrop(drop)}
                            </span>
                            <span style={{ ...MONO, color: C.textSecondary, textAlign: "right" }}>
                                {r.duration_months != null ? `${r.duration_months}m` : "—"}
                            </span>
                        </React.Fragment>
                    )
                })}
            </div>

            {/* footnote */}
            <div style={{
                fontSize: 10, color: C.textTertiary, lineHeight: 1.5,
                paddingTop: 8, borderTop: `1px solid ${C.borderStrong}`,
            }}>
                각 권역의 *가장 큰 drop* cycle 만 표시. 1990~2005 이전 cycle 은 인천 등 일부
                권역만 cover. plan v0.2 "핵심지 선행" 가설 검증 input.
            </div>
        </div>
    )
}


RegionalCycleTimingPanel.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/estate_brain_backtest_50y.json",
    refreshIntervalSec: 3600,
}

addPropertyControls(RegionalCycleTimingPanel, {
    dataUrl: {
        type: ControlType.String,
        title: "Data URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/estate_brain_backtest_50y.json",
        description: "estate_brain_backtest_50y.json publish URL (gh-pages)",
    },
    refreshIntervalSec: {
        type: ControlType.Number,
        title: "Refresh (sec)",
        defaultValue: 3600,
        min: 60,
        max: 86400,
        step: 60,
        description: "데이터는 월 1회 cron 갱신 — 1시간 default 충분",
    },
})
