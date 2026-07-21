import * as React from "react"
import { addPropertyControls, ControlType, RenderTarget } from "framer"

/**
 * DataIntegrityMonitor — AlphaNest 데이터 무결 감시 (AlphaNest 스타일).
 * 소스: data/metadata/data_health.json (공개 Blob) — 발행 가드·배달 검증·커버리지·신선도 집계 SoT.
 * status green/amber/red. 규율(RULE 7): 사실만, 판정·점수 0. 결손 = "측정 불가".
 * 다크모드 = body[data-framer-theme] 자동감지. 접근차단 = 페이지 AuthGate.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", grid: "#eef1f4", up: "#f04452", upS: "#fff0f1", down: "#3182f6",
    green: "#15c47e", greenS: "#eafaf3", amber: "#ff9500", amberS: "#fff6e9", vt: "#6c5ce7", vtS: "#f0edff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", grid: "#1e242c", up: "#f04452", upS: "#2a1a1d", down: "#5b9bff",
    green: "#34e08a", greenS: "#0f241c", amber: "#ff9500", amberS: "#2a2113", vt: "#a99bff", vtS: "#241f3a",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/metadata/data_health.json"
const CDN_AGE_WARN_S = 120
const STATUS_LABEL: Record<string, string> = { green: "정상", amber: "주의", red: "위험" }

interface VerifyFile { file: string; ok?: boolean; pct?: { PER?: number; PBR?: number }; total?: number; cdn_age_s?: number | null; error?: string }
interface DataHealth {
    _meta?: { generated_at?: string }
    status?: "green" | "amber" | "red"
    reasons?: string[]
    publish_guard?: { held_24h?: number; recent?: Array<{ ts?: string; held?: string[] }> } | null
    publish_verify?: { ok?: boolean; failed?: number; max_cdn_age_s?: number; files?: VerifyFile[] } | null
    coverage?: { kr_total?: number; us_total?: number; core_fill_pct?: Record<string, number>; last_run_blocked?: boolean; last_run_fails?: number; last_run_warns?: number } | null
    freshness?: { summary?: any; stale_p0?: Array<{ id?: string; label?: string; age_min?: number }>; stale_other?: string[] } | null
}

const SAMPLE: DataHealth = {
    _meta: { generated_at: "2026-07-16T09:00:00+09:00" }, status: "green", reasons: [],
    publish_guard: { held_24h: 0, recent: [] },
    publish_verify: { ok: true, failed: 0, max_cdn_age_s: 0, files: [
        { file: "stock_report_public.json", ok: true, pct: { PER: 74.2, PBR: 97.7 }, total: 1599, cdn_age_s: 0 },
        { file: "us_stock_report_public.json", ok: true, pct: { PER: 86.2, PBR: 94.9 }, total: 1505, cdn_age_s: 0 },
    ] },
    coverage: { kr_total: 1599, us_total: 1505, core_fill_pct: { "KR PBR": 97.7, "KR PER": 74.2, "US PBR": 94.9, "US PER": 86.2 }, last_run_blocked: false, last_run_fails: 0, last_run_warns: 0 },
    freshness: { summary: { fresh: 19, stale: 0, paused: 10 }, stale_p0: [], stale_other: [] },
}

function readBodyDark(): boolean {
    try {
        const _lsPref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (_lsPref === "dark") return true
        if (_lsPref === "light") return false
        if (typeof document !== "undefined" && document.body) {
            const a = document.body.dataset.framerTheme
            if (a === "dark") return true
            if (a === "light") return false
        }
        if (typeof localStorage !== "undefined") {
            const s = localStorage.getItem("verity_theme")
            if (s === "dark") return true
            if (s === "light") return false
        }
        if (typeof window !== "undefined" && window.matchMedia) return window.matchMedia("(prefers-color-scheme: dark)").matches
    } catch (e) {}
    return false
}
function fmtAge(iso?: string): string {
    if (!iso) return "—"
    try {
        const mins = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000))
        if (mins < 60) return mins + "분 전"
        const hrs = Math.round(mins / 60)
        return hrs < 24 ? hrs + "시간 전" : Math.round(hrs / 24) + "일 전"
    } catch (e) { return "—" }
}
function pctColor(C: any, v?: number, floor = 5): string {
    if (v == null) return C.faint
    if (v < floor) return C.up
    if (v < 40) return C.amber
    return C.green
}

interface Props { dataUrl: string; refreshSec: number; dark: boolean }

export default function DataIntegrityMonitor(props: Props) {
    const dataUrl = props.dataUrl || DEFAULT_URL
    const refreshSec = props.refreshSec || 60
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = React.useState<boolean>(() => (onCanvas ? !!props.dark : readBodyDark()))
    const C = (onCanvas ? !!props.dark : themeDark) ? DARK : LIGHT
    const [doc, setDoc] = React.useState<DataHealth | null>(onCanvas ? SAMPLE : null)
    const [err, setErr] = React.useState<string | null>(null)

    React.useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || !document.body) return
        const o = new MutationObserver(read)
        o.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => o.disconnect()
    }, [onCanvas])

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

    const page: React.CSSProperties = { background: C.bg, fontFamily: FONT, color: C.ink, width: "100%", boxSizing: "border-box", padding: 16, display: "flex", flexDirection: "column", gap: 12 }
    const card: React.CSSProperties = { background: C.card, borderRadius: 16, padding: "15px 17px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }
    if (err && !doc) return <div style={page}><div style={{ ...card, color: C.up, fontSize: 13, fontWeight: 700 }}>data_health 로드 실패: {err.slice(0, 90)}</div></div>
    if (!doc) return <div style={page}><div style={{ ...card, color: C.faint, fontSize: 13, fontWeight: 600 }}>데이터 무결 로딩…</div></div>

    const status = doc.status || "green"
    const sC = status === "red" ? C.up : status === "amber" ? C.amber : C.green
    const sBg = status === "red" ? C.upS : status === "amber" ? C.amberS : C.greenS
    const reasons = doc.reasons || []
    const guard = doc.publish_guard || null
    const verify = doc.publish_verify || null
    const cov = doc.coverage || null
    const fr = doc.freshness || null
    const frSum = (fr && fr.summary) || {}
    const secTitle = (t: string, sub?: string) => (
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 10 }}>
            <span style={{ fontSize: 14, fontWeight: 800, letterSpacing: "-0.3px", color: C.ink }}>{t}</span>
            {sub ? <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>{sub}</span> : null}
        </div>
    )
    const naDiv = <div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600 }}>측정 불가</div>

    return (
        <div style={page}>
            {/* 상태 배지 */}
            <div style={{ ...card, background: sBg }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <span style={{ width: 10, height: 10, borderRadius: "50%", background: sC }} />
                    <span style={{ fontSize: 17, fontWeight: 800, letterSpacing: "-0.4px", color: C.ink }}>데이터 무결</span>
                    <span style={{ fontSize: 12, fontWeight: 800, color: sC, background: C.card, borderRadius: 8, padding: "3px 10px" }}>{STATUS_LABEL[status] || status}</span>
                    <span style={{ marginLeft: "auto", fontSize: 11, color: C.sub, fontWeight: 600 }}>{fmtAge(doc._meta && doc._meta.generated_at)}</span>
                </div>
                {reasons.length > 0 && (
                    <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 4 }}>
                        {reasons.map((r, i) => (<div key={i} style={{ fontSize: 12.5, color: sC, fontWeight: 700 }}>· {r}</div>))}
                    </div>
                )}
            </div>

            {/* 발행 가드 */}
            <div style={card}>
                {secTitle("발행 가드", "결함본 업로드 차단")}
                {guard == null ? naDiv : (
                    <>
                        <div style={{ fontSize: 13.5, fontWeight: 700, color: C.sub }}>
                            24h HOLD <span style={{ color: (guard.held_24h || 0) > 0 ? C.up : C.green, fontWeight: 800 }}>{guard.held_24h || 0}</span> 건 {(guard.held_24h || 0) === 0 ? "· 정상" : "· 결함 데이터 차단됨(직전 GOOD 서빙)"}
                        </div>
                        {(guard.recent || []).filter((r) => (r.held || []).length > 0).slice(-4).map((r, i) => (
                            <div key={i} style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 4 }}>{fmtAge(r.ts)} — {(r.held || []).join(", ")}</div>
                        ))}
                    </>
                )}
            </div>

            {/* 배달 검증 */}
            <div style={card}>
                {secTitle("배달 검증", "실 CDN 채움율 + age")}
                {verify == null ? naDiv : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
                        {(verify.files || []).map((f, i) => {
                            const stale = (f.cdn_age_s || 0) > CDN_AGE_WARN_S
                            return (
                                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", paddingTop: i === 0 ? 0 : 9, borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                                    <span style={{ fontSize: 12, color: C.sub, fontWeight: 600, flex: "1 1 170px", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.file}</span>
                                    <span style={{ fontSize: 12.5, fontWeight: 800, color: pctColor(C, f.pct && f.pct.PER) }}>PER {f.pct && f.pct.PER != null ? f.pct.PER + "%" : "—"}</span>
                                    <span style={{ fontSize: 12.5, fontWeight: 800, color: pctColor(C, f.pct && f.pct.PBR) }}>PBR {f.pct && f.pct.PBR != null ? f.pct.PBR + "%" : "—"}</span>
                                    <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>N={f.total != null ? f.total.toLocaleString() : "—"}</span>
                                    <span style={{ fontSize: 11, fontWeight: 700, color: stale ? C.amber : C.faint }}>age {f.cdn_age_s != null ? f.cdn_age_s + "s" : "—"}{stale ? " ⚠" : ""}</span>
                                </div>
                            )
                        })}
                        {(verify.max_cdn_age_s || 0) > CDN_AGE_WARN_S && (
                            <div style={{ fontSize: 11.5, color: C.amber, fontWeight: 700 }}>CDN 최대 age {verify.max_cdn_age_s}s — 스테일 서빙</div>
                        )}
                    </div>
                )}
            </div>

            {/* 커버리지 */}
            <div style={card}>
                {secTitle("커버리지", "핵심 필드 채움율")}
                {cov == null ? naDiv : (
                    <>
                        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            {Object.entries(cov.core_fill_pct || {}).map(([k, v]) => (
                                <div key={k} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                                    <span style={{ fontSize: 12, color: C.sub, fontWeight: 600, flex: "0 0 90px" }}>{k}</span>
                                    <div style={{ flex: 1, height: 7, borderRadius: 4, background: C.grid, overflow: "hidden" }}>
                                        <div style={{ width: Math.max(2, Math.min(100, v)) + "%", height: "100%", borderRadius: 4, background: pctColor(C, v) }} />
                                    </div>
                                    <span style={{ fontSize: 12, fontWeight: 800, color: pctColor(C, v), flex: "0 0 44px", textAlign: "right" }}>{v}%</span>
                                </div>
                            ))}
                        </div>
                        <div style={{ fontSize: 11.5, color: cov.last_run_blocked ? C.up : C.faint, fontWeight: 600, marginTop: 10 }}>
                            직전 run · {cov.last_run_blocked ? "차단됨" : "통과"} · 결함 {cov.last_run_fails || 0} · 경고 {cov.last_run_warns || 0} · KR {cov.kr_total != null ? cov.kr_total : "—"} / US {cov.us_total != null ? cov.us_total : "—"}
                        </div>
                    </>
                )}
            </div>

            {/* 신선도 */}
            <div style={card}>
                {secTitle("신선도", "SLA")}
                {fr == null ? naDiv : (
                    <>
                        <div style={{ display: "flex", gap: 10 }}>
                            <span style={{ flex: 1, textAlign: "center", background: C.greenS, color: C.green, borderRadius: 10, padding: "9px 0", fontSize: 13, fontWeight: 800 }}>fresh {frSum.fresh != null ? frSum.fresh : "—"}</span>
                            <span style={{ flex: 1, textAlign: "center", background: (frSum.stale || 0) > 0 ? C.upS : C.grid, color: (frSum.stale || 0) > 0 ? C.up : C.faint, borderRadius: 10, padding: "9px 0", fontSize: 13, fontWeight: 800 }}>stale {frSum.stale != null ? frSum.stale : "—"}</span>
                            <span style={{ flex: 1, textAlign: "center", background: C.grid, color: C.faint, borderRadius: 10, padding: "9px 0", fontSize: 13, fontWeight: 800 }}>paused {frSum.paused != null ? frSum.paused : "—"}</span>
                        </div>
                        {(fr.stale_p0 || []).length > 0 && (
                            <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 3 }}>
                                {(fr.stale_p0 || []).map((s, i) => (
                                    <div key={i} style={{ fontSize: 12, color: C.up, fontWeight: 700 }}>P0 stale · {s.label || s.id} {s.age_min != null ? `(${Math.round(s.age_min)}분)` : ""}</div>
                                ))}
                            </div>
                        )}
                        {(fr.stale_other || []).length > 0 && (
                            <div style={{ fontSize: 11.5, color: C.amber, fontWeight: 600, marginTop: 8 }}>비P0 stale: {(fr.stale_other || []).join(", ")}</div>
                        )}
                    </>
                )}
            </div>
            <div style={{ textAlign: "center", fontSize: 11, color: C.faint, fontWeight: 600 }}>data_health.json · 사실 집계 · 판정·점수 아님 (RULE 7)</div>
        </div>
    )
}

addPropertyControls(DataIntegrityMonitor, {
    dataUrl: { type: ControlType.String, title: "data_health URL", defaultValue: DEFAULT_URL },
    refreshSec: { type: ControlType.Number, title: "새로고침(초)", defaultValue: 60, min: 15, max: 600, step: 15 },
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
})
