// DataIntegrityMonitor — 관리자 데이터 무결 감시 카드 (2026-07-12).
// 소스: data/metadata/data_health.json (공개 Blob, 페이지 AuthGate 로 접근 차단).
//   = 발행 fail-closed 게이트 + 단일 발행 가드 + 배달 검증 + 커버리지 + 신선도의 단일 SoT.
// 규율(RULE 7): 사실 표시만 — 판정·점수·추천 0. 필드 결손 = "측정 불가"(가짜 0 아님).
// 디자인: Neo Dark Terminal (AdminDashboard C 팔레트 정합).
import * as React from "react"
import { addPropertyControls, ControlType, RenderTarget } from "framer"

const C = {
    bgPage: "#0a0a0a", bgCard: "#141414", bgElevated: "#1a1a1a",
    border: "rgba(255,255,255,0.06)", borderStrong: "rgba(255,255,255,0.10)",
    textPrimary: "#ffffff", textSecondary: "#A8ABB2", textTertiary: "#6B6E76",
    accent: "#7fffa0", green: "#22C55E", amber: "#F59E0B", red: "#EF4444", info: "#5BA9FF",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const MONO: React.CSSProperties = { fontFamily: "ui-monospace, SF Mono, Menlo, monospace" }

const STATUS_COLOR: Record<string, string> = { green: C.green, amber: C.amber, red: C.red }
const STATUS_LABEL: Record<string, string> = { green: "정상", amber: "주의", red: "위험" }

interface VerifyFile { file: string; ok?: boolean; pct?: { PER?: number; PBR?: number }; total?: number; cdn_age_s?: number | null; error?: string }
interface DataHealth {
    _meta?: { generated_at?: string }
    status?: "green" | "amber" | "red"
    reasons?: string[]
    publish_guard?: { held_24h?: number; recent?: Array<{ ts?: string; held?: string[]; reasons?: string[] }> } | null
    publish_verify?: { ok?: boolean; failed?: number; max_cdn_age_s?: number; files?: VerifyFile[] } | null
    coverage?: { kr_total?: number; us_total?: number; core_fill_pct?: Record<string, number>; last_run_blocked?: boolean; last_run_fails?: number; last_run_warns?: number } | null
    freshness?: { summary?: any; stale_p0?: Array<{ id?: string; label?: string; age_min?: number }>; stale_other?: string[] } | null
}

const SAMPLE: DataHealth = {
    _meta: { generated_at: "2026-07-12T00:51:00+09:00" },
    status: "green", reasons: [],
    publish_guard: { held_24h: 0, recent: [] },
    publish_verify: {
        ok: true, failed: 0, max_cdn_age_s: 0, files: [
            { file: "stock_report_public.json", ok: true, pct: { PER: 74.2, PBR: 97.7 }, total: 1599, cdn_age_s: 0 },
            { file: "us_stock_report_public.json", ok: true, pct: { PER: 86.2, PBR: 94.9 }, total: 1505, cdn_age_s: 0 },
            { file: "us_stock_report_us_smallcap.json", ok: true, pct: { PER: 11.7, PBR: 14.2 }, total: 3964, cdn_age_s: 0 },
        ],
    },
    coverage: { kr_total: 1599, us_total: 1505, core_fill_pct: { "fields.facts.PBR": 97.7, "fields.facts.PER": 74.2, "us_fields.facts.PBR": 94.9, "us_fields.facts.PER": 86.2 }, last_run_blocked: false, last_run_fails: 0, last_run_warns: 0 },
    freshness: { summary: { fresh: 19, stale: 0, paused: 10 }, stale_p0: [], stale_other: [] },
}

const CDN_AGE_WARN_S = 120

function fmtAge(iso?: string): string {
    if (!iso) return "—"
    try {
        const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000))
        if (mins < 60) return mins + "분 전"
        const hrs = Math.round(mins / 60)
        return hrs < 24 ? hrs + "시간 전" : Math.round(hrs / 24) + "일 전"
    } catch { return "—" }
}
function pctColor(v?: number, floor = 5): string {
    if (v == null) return C.textTertiary
    if (v < floor) return C.red
    if (v < 40) return C.amber
    return C.green
}

interface Props { dataUrl: string; refreshSec: number }

export default function DataIntegrityMonitor(props: Props) {
    const { dataUrl, refreshSec } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [doc, setDoc] = React.useState<DataHealth | null>(onCanvas ? SAMPLE : null)
    const [err, setErr] = React.useState<string | null>(null)

    React.useEffect(() => {
        if (onCanvas) return
        let alive = true
        const load = () => {
            const url = `${dataUrl}${dataUrl.includes("?") ? "&" : "?"}t=${Date.now()}`
            fetch(url, { cache: "no-store" })
                .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
                .then((d) => { if (alive) { setDoc(d as DataHealth); setErr(null) } })
                .catch((e) => { if (alive && !doc) setErr(String(e && e.message ? e.message : e)) })
        }
        load()
        const iv = setInterval(load, Math.max(15, refreshSec || 60) * 1000)
        return () => { alive = false; clearInterval(iv) }
    }, [dataUrl, refreshSec, onCanvas])

    const wrap: React.CSSProperties = { background: C.bgPage, border: `1px solid ${C.border}`, borderRadius: 10, padding: 18, fontFamily: FONT, color: C.textPrimary, width: "100%", boxSizing: "border-box" }
    if (err && !doc) return <div style={{ ...wrap, color: C.red, fontSize: 13 }}>data_health 로드 실패: {err.slice(0, 90)}</div>
    if (!doc) return <div style={{ ...wrap, color: C.textTertiary, fontSize: 13 }}>data_health 로딩…</div>

    const status = doc.status || "green"
    const sColor = STATUS_COLOR[status] || C.textTertiary
    const reasons = doc.reasons || []
    const guard = doc.publish_guard || null
    const verify = doc.publish_verify || null
    const cov = doc.coverage || null
    const fr = doc.freshness || null
    const frSum = (fr && fr.summary) || {}

    const label = (t: string) => (<div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: C.textTertiary, marginBottom: 8 }}>{t}</div>)
    const section: React.CSSProperties = { borderTop: `1px solid ${C.border}`, paddingTop: 14, marginTop: 14 }

    return (
        <div style={wrap}>
            {/* 헤더 — 상태 배지 */}
            <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                <span style={{ width: 10, height: 10, borderRadius: "50%", background: sColor, boxShadow: `0 0 10px ${sColor}` }} />
                <span style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-0.01em" }}>데이터 무결</span>
                <span style={{ fontSize: 11, fontWeight: 800, color: sColor, background: sColor + "1f", border: `1px solid ${sColor}44`, borderRadius: 6, padding: "3px 9px", letterSpacing: "0.04em" }}>{STATUS_LABEL[status] || status}</span>
                <span style={{ marginLeft: "auto", fontSize: 11, color: C.textTertiary, ...MONO }}>{fmtAge(doc._meta && doc._meta.generated_at)}</span>
            </div>
            {reasons.length > 0 && (
                <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 4 }}>
                    {reasons.map((r, i) => (<div key={i} style={{ fontSize: 12, color: status === "red" ? C.red : C.amber, fontWeight: 600 }}>· {r}</div>))}
                </div>
            )}

            {/* 발행 가드 */}
            <div style={section}>
                {label("발행 가드 · 결함본 업로드 차단")}
                {guard == null ? (
                    <div style={{ fontSize: 12, color: C.textTertiary }}>측정 불가</div>
                ) : (
                    <>
                        <div style={{ fontSize: 13, fontWeight: 700, color: (guard.held_24h || 0) > 0 ? C.red : C.textSecondary }}>
                            24h HOLD <span style={{ ...MONO, color: (guard.held_24h || 0) > 0 ? C.red : C.green }}>{guard.held_24h || 0}</span> 건 {(guard.held_24h || 0) === 0 ? "· 정상" : "· 결함 데이터 차단됨(직전 GOOD 서빙)"}
                        </div>
                        {(guard.recent || []).filter((r) => (r.held || []).length > 0).slice(-4).map((r, i) => (
                            <div key={i} style={{ fontSize: 11, color: C.textTertiary, marginTop: 4, ...MONO }}>{fmtAge(r.ts)} — {(r.held || []).join(", ")}</div>
                        ))}
                    </>
                )}
            </div>

            {/* 배달 검증 */}
            <div style={section}>
                {label("배달 검증 · 실 CDN 채움율 + age")}
                {verify == null ? (
                    <div style={{ fontSize: 12, color: C.textTertiary }}>측정 불가</div>
                ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {(verify.files || []).map((f, i) => {
                            const stale = (f.cdn_age_s || 0) > CDN_AGE_WARN_S
                            return (
                                <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                                    <span style={{ fontSize: 11.5, color: C.textSecondary, flex: "1 1 180px", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.file}</span>
                                    <span style={{ fontSize: 12, ...MONO, color: pctColor(f.pct && f.pct.PER) }}>PER {f.pct && f.pct.PER != null ? f.pct.PER + "%" : "—"}</span>
                                    <span style={{ fontSize: 12, ...MONO, color: pctColor(f.pct && f.pct.PBR) }}>PBR {f.pct && f.pct.PBR != null ? f.pct.PBR + "%" : "—"}</span>
                                    <span style={{ fontSize: 11, ...MONO, color: C.textTertiary }}>N={f.total != null ? f.total.toLocaleString() : "—"}</span>
                                    <span style={{ fontSize: 11, ...MONO, color: stale ? C.amber : C.textTertiary }}>age {f.cdn_age_s != null ? f.cdn_age_s + "s" : "—"}{stale ? " ⚠" : ""}</span>
                                </div>
                            )
                        })}
                        {(verify.max_cdn_age_s || 0) > CDN_AGE_WARN_S && (
                            <div style={{ fontSize: 11, color: C.amber }}>CDN 최대 age {verify.max_cdn_age_s}s &gt; {CDN_AGE_WARN_S}s — 스테일 서빙</div>
                        )}
                    </div>
                )}
            </div>

            {/* 커버리지 */}
            <div style={section}>
                {label("커버리지 · 핵심 필드 채움율")}
                {cov == null ? (
                    <div style={{ fontSize: 12, color: C.textTertiary }}>측정 불가</div>
                ) : (
                    <>
                        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                            {Object.entries(cov.core_fill_pct || {}).map(([k, v]) => (
                                <div key={k} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                    <span style={{ fontSize: 11, color: C.textSecondary, flex: "0 0 150px", ...MONO }}>{k}</span>
                                    <div style={{ flex: 1, height: 6, borderRadius: 3, background: C.bgElevated, overflow: "hidden" }}>
                                        <div style={{ width: Math.max(2, Math.min(100, v)) + "%", height: "100%", background: pctColor(v) }} />
                                    </div>
                                    <span style={{ fontSize: 11.5, ...MONO, color: pctColor(v), flex: "0 0 46px", textAlign: "right" }}>{v}%</span>
                                </div>
                            ))}
                        </div>
                        <div style={{ fontSize: 11, color: cov.last_run_blocked ? C.red : C.textTertiary, marginTop: 8 }}>
                            직전 run · {cov.last_run_blocked ? "차단됨" : "통과"} · 결함 {cov.last_run_fails || 0} · 경고 {cov.last_run_warns || 0} · KR {cov.kr_total ?? "—"} / US {cov.us_total ?? "—"}
                        </div>
                    </>
                )}
            </div>

            {/* 신선도 */}
            <div style={section}>
                {label("신선도 SLA")}
                {fr == null ? (
                    <div style={{ fontSize: 12, color: C.textTertiary }}>측정 불가</div>
                ) : (
                    <>
                        <div style={{ display: "flex", gap: 16, fontSize: 12.5, ...MONO }}>
                            <span style={{ color: C.green }}>fresh {frSum.fresh ?? "—"}</span>
                            <span style={{ color: (frSum.stale || 0) > 0 ? C.red : C.textTertiary }}>stale {frSum.stale ?? "—"}</span>
                            <span style={{ color: C.textTertiary }}>paused {frSum.paused ?? "—"}</span>
                        </div>
                        {(fr.stale_p0 || []).length > 0 && (
                            <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 3 }}>
                                {(fr.stale_p0 || []).map((s, i) => (
                                    <div key={i} style={{ fontSize: 11.5, color: C.red }}>P0 stale · {s.label || s.id} {s.age_min != null ? `(${Math.round(s.age_min)}분)` : ""}</div>
                                ))}
                            </div>
                        )}
                        {(fr.stale_other || []).length > 0 && (
                            <div style={{ fontSize: 11, color: C.amber, marginTop: 6 }}>비P0 stale: {(fr.stale_other || []).join(", ")}</div>
                        )}
                    </>
                )}
            </div>
        </div>
    )
}

DataIntegrityMonitor.defaultProps = {
    dataUrl: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/metadata/data_health.json",
    refreshSec: 60,
}

addPropertyControls(DataIntegrityMonitor, {
    dataUrl: { type: ControlType.String, title: "data_health URL", defaultValue: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/metadata/data_health.json" },
    refreshSec: { type: ControlType.Number, title: "새로고침(초)", defaultValue: 60, min: 15, max: 600, step: 15 },
})
