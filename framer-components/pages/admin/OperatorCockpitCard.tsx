import * as React from "react"
import { addPropertyControls, ControlType, RenderTarget } from "framer"

/**
 * OperatorCockpitCard — 관리자 종합 운영 상태 (AlphaNest 리스타일 2026-07-16).
 * 소스: cockpit_state.json (공개 Blob) — severity·검증 N일·오퍼레이터 데드맨·24h 알림량·사전등록 대기.
 * 옛 Neo Dark Terminal → AlphaNest 토스카드/보라/다크감지. 데이터 로직 동일.
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
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/metadata/cockpit_state.json"

interface PendingItem { sha: string; date: string; subject: string; missing: string[] }
interface CockpitState {
    collected_at: string
    severity: "GREEN" | "YELLOW" | "RED"
    severity_reasons: string[]
    n_verification_days: number
    n_milestones: { to_50: number; to_100: number; to_252: number; to_365: number }
    one_liner?: string
    days_clean: { kis: number | null; fred: number | null; telegram: number | null; vercel: number | null }
    operator_deadman: { trigger?: string; days_git?: number; days_telegram?: number; days_uaq?: number; warn_days?: number }
    alert_volume_24h: { sent?: number; dedupe_skip?: number; quiet_skip?: number; fp_repeat_max?: number }
    pre_registration_pending: PendingItem[]
}

const SAMPLE: CockpitState = {
    collected_at: "2026-07-16T09:20:00", severity: "GREEN", severity_reasons: [],
    n_verification_days: 71, n_milestones: { to_50: 0, to_100: 29, to_252: 181, to_365: 294 },
    one_liner: "전 채널 정상 · 검증 71일 누적 · 알림 0건",
    days_clean: { kis: 0, fred: 0, telegram: 0, vercel: 0 },
    operator_deadman: { trigger: "none", days_git: 0.2, days_telegram: 0.1, days_uaq: 0.4, warn_days: 7 },
    alert_volume_24h: { sent: 0, dedupe_skip: 3, quiet_skip: 1, fp_repeat_max: 0 },
    pre_registration_pending: [],
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
function n0(v: any): number { const x = Number(v); return isFinite(x) ? x : 0 }

interface Props { cockpitStateUrl: string; dark: boolean }

export default function OperatorCockpitCard(props: Props) {
    const url = props.cockpitStateUrl || DEFAULT_URL
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = React.useState<boolean>(() => (onCanvas ? !!props.dark : readBodyDark()))
    const C = (onCanvas ? !!props.dark : themeDark) ? DARK : LIGHT
    const [state, setState] = React.useState<CockpitState | null>(onCanvas ? SAMPLE : null)
    const [error, setError] = React.useState<string | null>(null)

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
        const u = `${url}${url.includes("?") ? "&" : "?"}t=${Date.now()}`
        fetch(u, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
            .then((d) => { if (alive) { setState(d as CockpitState); setError(null) } })
            .catch((e) => { if (alive && !state) setError(String(e && e.message ? e.message : e)) })
        return () => { alive = false }
    }, [url, onCanvas])

    const wrap: React.CSSProperties = { width: "100%", boxSizing: "border-box", background: C.bg, fontFamily: FONT, color: C.ink, padding: 16, display: "flex", flexDirection: "column", gap: 12 }
    const card: React.CSSProperties = { background: C.card, borderRadius: 16, padding: "15px 17px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }
    const label = (t: string) => (<div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.03em", color: C.faint, marginBottom: 8 }}>{t}</div>)
    const num: React.CSSProperties = { fontVariantNumeric: "tabular-nums" }

    if (error && !state) return <div style={wrap}><div style={{ ...card, color: C.up, fontSize: 13, fontWeight: 700 }}>콕핏 로드 실패: {error.slice(0, 90)}</div></div>
    if (!state) return <div style={wrap}><div style={{ ...card, color: C.faint, fontSize: 13, fontWeight: 600 }}>운영 콕핏 로딩…</div></div>

    const sev = state.severity
    const sC = sev === "RED" ? C.up : sev === "YELLOW" ? C.amber : C.green
    const sBg = sev === "RED" ? C.upS : sev === "YELLOW" ? C.amberS : C.greenS
    const sLabel = sev === "RED" ? "위험" : sev === "YELLOW" ? "주의" : "정상"
    const odm = state.operator_deadman || {}
    const av = state.alert_volume_24h || {}
    const ms = state.n_milestones || { to_50: 0, to_100: 0, to_252: 0, to_365: 0 }
    const pending = state.pre_registration_pending || []
    const warn = n0(odm.warn_days) || 7

    const dayRow = (name: string, d: any) => {
        const v = n0(d)
        const col = v >= warn ? C.up : v >= warn * 0.7 ? C.amber : C.green
        return (
            <div style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", fontSize: 13 }}>
                <span style={{ color: C.sub, fontWeight: 600 }}>{name}</span>
                <span style={{ ...num, color: col, fontWeight: 800 }}>{v.toFixed(1)}일</span>
            </div>
        )
    }
    const kv = (name: string, v: any, danger?: boolean) => (
        <div style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", fontSize: 13 }}>
            <span style={{ color: C.sub, fontWeight: 600 }}>{name}</span>
            <span style={{ ...num, color: danger ? C.amber : C.ink, fontWeight: 800 }}>{String(n0(v))}</span>
        </div>
    )

    return (
        <div style={wrap}>
            {/* 헤더 — severity 틴트 박스 */}
            <div style={{ ...card, background: sBg }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <span style={{ width: 10, height: 10, borderRadius: "50%", background: sC }} />
                    <span style={{ fontSize: 17, fontWeight: 800, letterSpacing: "-0.4px", color: C.ink }}>운영 콕핏</span>
                    <span style={{ fontSize: 12, fontWeight: 800, color: sC, background: C.card, borderRadius: 8, padding: "3px 10px" }}>{sLabel}</span>
                    <span style={{ marginLeft: "auto", fontSize: 11, color: C.sub, fontWeight: 600, ...num }}>{(state.collected_at || "").slice(0, 16).replace("T", " ")}</span>
                </div>
                {state.one_liner && <div style={{ fontSize: 13.5, color: C.ink, fontWeight: 600, marginTop: 10, lineHeight: 1.5 }}>{state.one_liner}</div>}
                {state.severity_reasons && state.severity_reasons.length > 0 && (
                    <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 3 }}>
                        {state.severity_reasons.map((r, i) => (<div key={i} style={{ fontSize: 12.5, color: sC, fontWeight: 700 }}>· {r}</div>))}
                    </div>
                )}
            </div>

            {/* N 검증일 */}
            <div style={card}>
                {label("검증 N일 (누적)")}
                <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                    <span style={{ fontSize: 44, fontWeight: 800, letterSpacing: "-1.5px", color: C.ink, ...num }}>{n0(state.n_verification_days)}</span>
                    <span style={{ fontSize: 12.5, color: C.faint, fontWeight: 700 }}>일</span>
                </div>
                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 6, ...num }}>
                    50까지 {n0(ms.to_50)} · 100까지 {n0(ms.to_100)} · 252까지 {n0(ms.to_252)} · 365까지 {n0(ms.to_365)}
                </div>
            </div>

            {/* 데드맨 + 알림량 (2열) */}
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                <div style={{ ...card, flex: "1 1 200px" }}>
                    {label("오퍼레이터 데드맨")}
                    {dayRow("git", odm.days_git)}
                    {dayRow("telegram", odm.days_telegram)}
                    {dayRow("uaq", odm.days_uaq)}
                    <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 6 }}>trigger · {odm.trigger || "none"}</div>
                </div>
                <div style={{ ...card, flex: "1 1 200px" }}>
                    {label("24시간 알림량")}
                    {kv("전송(sent)", av.sent)}
                    {kv("중복 스킵", av.dedupe_skip)}
                    {kv("조용시간 스킵", av.quiet_skip)}
                    {kv("반복 최대", av.fp_repeat_max, n0(av.fp_repeat_max) > 10)}
                </div>
            </div>

            {/* 사전등록 대기 */}
            {pending.length > 0 && (
                <div style={card}>
                    {label(`사전등록 대기 (${pending.length})`)}
                    {pending.slice(0, 5).map((p, i) => (
                        <div key={i} style={{ paddingTop: i === 0 ? 0 : 8, marginTop: i === 0 ? 0 : 8, borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                            <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
                                <span style={{ fontSize: 11.5, fontWeight: 800, color: C.vt, ...num }}>{p.sha}</span>
                                <span style={{ fontSize: 11, color: C.faint, fontWeight: 600, ...num }}>{p.date}</span>
                                <span style={{ fontSize: 12.5, color: C.ink, fontWeight: 600, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.subject}</span>
                            </div>
                            <div style={{ fontSize: 10.5, color: C.amber, fontWeight: 700, marginTop: 2 }}>missing: {(p.missing || []).join(", ")}</div>
                        </div>
                    ))}
                    {pending.length > 5 && <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 6 }}>+{pending.length - 5}건 더</div>}
                </div>
            )}
        </div>
    )
}

addPropertyControls(OperatorCockpitCard, {
    cockpitStateUrl: { type: ControlType.String, title: "Cockpit URL", defaultValue: DEFAULT_URL },
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
})
