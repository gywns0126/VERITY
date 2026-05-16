import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"

/* ──────────────────────────────────────────────────────────────
 * ◆ ESTATE 패밀리룩 v3 — Cluster A warm gold tone (SystemPulse / EstateAuthGate 정합)
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
 * ESTATE System Health Bar — sticky bar (페이지 하단/헤더 배치)
 *
 * /api/estate/health 응답 (contract_system_pulse.md §1) 의 자원 status 띠 노출.
 *
 * ── 직교 관계 (2026-05-17 audit 명시) ──
 * 1. terminal SystemHealthBar 와 직교 (terminal 자원 X — estate 전용)
 * 2. SystemPulse.tsx (홈 페이지 1 카드) 와 같은 endpoint 사용하지만 다른 UX:
 *    - EstateSystemHealthBar = sticky bar (모든 페이지 상시 표시, 컴팩트 띠)
 *    - SystemPulse            = 홈 카드 (페이지 1 fold, 큰 카드 + admin meta)
 *    같은 source 다른 view 정공법 — feedback_component_overlap_audit 검토 후 보존 결정.
 *
 * feedback_estate_density_first 정합 — 200줄 안쪽 (terminal 1416줄 sub).
 * feedback_no_hardcode_position 정합 — position:fixed 하드코드 X. 사용자가
 * Framer 에서 페이지 하단 sticky / 헤더 등 직접 배치.
 *
 * 자원 schema (P2 wire — 2026-05-17 estate_health.py):
 *   {id, label_ko, status: "healthy"|"degraded"|"down"|"unknown", metric{...}, note}
 * 5 자원: r_one_weekly / r_one_unsold / landex_meta_validation / policy_archive / estate_api_keys
 */

const STATUS_COLOR: Record<string, string> = {
    healthy: C.success,
    degraded: C.warn,
    down: C.danger,
    unknown: C.textTertiary,
}

const STATUS_LABEL: Record<string, string> = {
    healthy: "정상",
    degraded: "지연",
    down: "중단",
    unknown: "—",
}

interface Resource {
    id: string
    label_ko: string
    status: string
    metric?: Record<string, any>
    note?: string | null
}

interface HealthPayload {
    resources?: Resource[]
    fetched_at?: string
    scenario?: string
}

function fetchHealth(url: string, signal?: AbortSignal): Promise<HealthPayload> {
    const u = (url || "").trim().replace(/\/$/, "")
    const sep = u.includes("?") ? "&" : "?"
    return fetch(`${u}${sep}_=${Date.now()}`, {
        cache: "no-store", mode: "cors", credentials: "omit", signal,
    }).then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
    })
}

function summarize(resources: Resource[]): { tone: string; label: string; n_total: number; n_ok: number } {
    const n_total = resources.length
    const n_ok = resources.filter((r) => r.status === "healthy").length
    const n_degraded = resources.filter((r) => r.status === "degraded").length
    const n_down = resources.filter((r) => r.status === "down").length
    if (n_down > 0) return { tone: "down", label: "ESTATE 중단 자원 발견", n_total, n_ok }
    if (n_degraded > 0) return { tone: "degraded", label: "ESTATE 일부 지연", n_total, n_ok }
    if (n_total > 0) return { tone: "healthy", label: "ESTATE 정상", n_total, n_ok }
    return { tone: "unknown", label: "데이터 없음", n_total, n_ok }
}

function fmtRelative(iso?: string): string {
    if (!iso) return "—"
    const t = Date.parse(iso)
    if (Number.isNaN(t)) return "—"
    const diff_ms = Date.now() - t
    const m = Math.floor(diff_ms / 60_000)
    if (m < 60) return `${m}m`
    const h = Math.floor(m / 60)
    if (h < 24) return `${h}h`
    const d = Math.floor(h / 24)
    return `${d}d`
}


interface Props {
    apiUrl: string
    refreshIntervalSec: number
}

export default function EstateSystemHealthBar({ apiUrl, refreshIntervalSec }: Props) {
    const [data, setData] = useState<HealthPayload | null>(null)
    const [err, setErr] = useState<string | null>(null)

    useEffect(() => {
        if (!apiUrl) return
        const ctl = new AbortController()
        const tick = () => {
            fetchHealth(`${apiUrl.replace(/\/$/, "")}/api/estate/health`, ctl.signal)
                .then((p) => { setData(p); setErr(null) })
                .catch((e) => { if (e?.name !== "AbortError") setErr(e?.message || "fetch failed") })
        }
        tick()
        // 2026-05-17 C5 polling 정합 — estate_health.py P2 wire 후 source 갱신 주기 = R-ONE 일/주,
        // 정책 cron 평일 일 1회, env 거의 변화 X. 30s 미만 polling 은 무의미한 Vercel 호출 증가.
        // min 30초 강제. 또한 endpoint Cache-Control: max-age=300 (5분) 라 30초 polling 도 대부분 CDN hit.
        const id = window.setInterval(tick, Math.max(30, refreshIntervalSec) * 1000)
        return () => { ctl.abort(); window.clearInterval(id) }
    }, [apiUrl, refreshIntervalSec])

    const resources = data?.resources || []
    const sum = summarize(resources)

    return (
        <div style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "5px 12px", borderRadius: 6,
            background: C.bgCard, border: `1px solid ${C.border}`,
            fontFamily: FONT, color: C.textPrimary, width: "100%", boxSizing: "border-box",
        }}>
            {/* 좌: 종합 verdict */}
            <div style={{ display: "flex", alignItems: "center", gap: 6,
                flexShrink: 0 }}>
                <span style={{
                    width: 6, height: 6, borderRadius: "50%",
                    background: STATUS_COLOR[sum.tone] || C.textTertiary,
                }} />
                <span style={{ fontSize: 11, fontWeight: 700, color: C.textPrimary,
                    whiteSpace: "nowrap" }}>
                    {sum.label}
                </span>
                {sum.n_total > 0 && (
                    <span style={{ ...MONO, fontSize: 10, color: C.textTertiary,
                        whiteSpace: "nowrap" }}>
                        {sum.n_ok}/{sum.n_total}
                    </span>
                )}
            </div>

            {/* 가운데: 자원 칩 — flex:1 + justifyContent:center 로 가운데 정렬 (terminal 패턴) */}
            <div style={{
                display: "flex", gap: 10, flexWrap: "wrap",
                flex: 1, justifyContent: "center", alignItems: "center",
                minWidth: 0,
            }}>
                {resources.map((r) => (
                    <span key={r.id} title={r.note || STATUS_LABEL[r.status] || ""}
                        style={{
                            display: "inline-flex", alignItems: "center", gap: 5,
                            fontSize: 11, fontWeight: 500, color: C.textSecondary,
                            whiteSpace: "nowrap",
                        }}>
                        <span style={{
                            width: 6, height: 6, borderRadius: "50%",
                            background: STATUS_COLOR[r.status] || C.textTertiary,
                        }} />
                        {r.label_ko || r.id}
                        {r.metric?.last_success_at && (
                            <span style={{ ...MONO, fontSize: 10, color: C.textTertiary,
                                marginLeft: 2 }}>
                                {fmtRelative(r.metric.last_success_at as string)}
                            </span>
                        )}
                    </span>
                ))}
            </div>

            {/* 우: 메타 (갱신 시점 / err) */}
            <div style={{ display: "flex", alignItems: "center", gap: 6, flexShrink: 0 }}>
                {err && (
                    <span style={{ fontSize: 10, color: C.danger, fontWeight: 600 }}>
                        ⚠ {err}
                    </span>
                )}
                {data?.fetched_at && (
                    <span style={{ ...MONO, fontSize: 10, color: C.textTertiary }}>
                        as_of {fmtRelative(data.fetched_at)}
                    </span>
                )}
            </div>
        </div>
    )
}


EstateSystemHealthBar.defaultProps = {
    apiUrl: "https://project-yw131.vercel.app",
    refreshIntervalSec: 300,  // 2026-05-17 C5 — 60s → 300s (5분, R-ONE 일/주 갱신 정합)
}

addPropertyControls(EstateSystemHealthBar, {
    apiUrl: {
        type: ControlType.String,
        title: "API URL",
        defaultValue: "https://project-yw131.vercel.app",
    },
    refreshIntervalSec: {
        type: ControlType.Number,
        title: "Refresh (sec)",
        defaultValue: 300,  // 2026-05-17 C5 — 60 → 300 (P2 wire 후 source 갱신 일/주)
        min: 30,            // 2026-05-17 C5 — 15 → 30 (Vercel CDN cache 5분 정합)
        max: 600,
        step: 30,
    },
})
