import * as React from "react"
import { addPropertyControls, ControlType, RenderTarget } from "framer"

/**
 * BerserkerStatusCard — ARENA 버서커 검증 진행도 + 잠금 카운트다운 (AlphaNest 리스타일 2026-07-16).
 * 소스: berserker_status.json (공개 Blob). 공격성 = 검증 진행도의 함수. 레버리지·숏 = LOCKED.
 * 🚨 RULE 7: 자기 산식 = "(가설 / shadow only, 실자본 0)" 명시 의무 — 유지.
 * 옛 Neo Dark Terminal → AlphaNest 토스카드/보라/다크감지. 데이터 로직 동일.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", grid: "#eef1f4", up: "#f04452", down: "#3182f6",
    green: "#15c47e", greenS: "#eafaf3", amber: "#ff9500", amberS: "#fff6e9", vt: "#6c5ce7", vtS: "#f0edff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", grid: "#1e242c", up: "#f04452", down: "#5b9bff",
    green: "#34e08a", greenS: "#0f241c", amber: "#ff9500", amberS: "#2a2113", vt: "#a99bff", vtS: "#241f3a",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/arena/berserker_status.json"
const GATE_LABELS: Record<string, string> = { days: "거래일", trades: "완료 거래", expectancy: "기대값 (R)", sqn: "SQN" }

interface Gate { current: number | null; target: number; progress: number; remaining?: number | null; unit: string }
interface LockedFeature { name: string; label: string; status: "LOCKED" | "UNLOCKED"; unlock_condition: string; countdown: string; note?: string }
interface BerserkerStatus {
    as_of: string; validation_overall: string; validation_progress_pct: number
    gates: { days: Gate; trades: Gate; expectancy: Gate; sqn: Gate }
    aggression: { multiplier: number; mode: string; note?: string }
    locked_features: LockedFeature[]; fully_unlocked: boolean; _disclaimer?: string
}

const SAMPLE: BerserkerStatus = {
    as_of: "2026-07-16", validation_overall: "진행 중", validation_progress_pct: 28.2,
    gates: {
        days: { current: 12, target: 65, progress: 0.18, unit: "일" },
        trades: { current: 3, target: 10, progress: 0.3, unit: "건" },
        expectancy: { current: null, target: 0.2, progress: 0, unit: "R" },
        sqn: { current: null, target: 2.0, progress: 0, unit: "" },
    },
    aggression: { multiplier: 1.0, mode: "보수", note: "" },
    locked_features: [
        { name: "leverage", label: "레버리지", status: "LOCKED", unlock_condition: "N≥65 + SQN≥2", countdown: "거래일 53일 남음", note: "" },
        { name: "short", label: "숏 포지션", status: "LOCKED", unlock_condition: "N≥65", countdown: "거래일 53일 남음", note: "" },
    ],
    fully_unlocked: false,
}

function readBodyDark(): boolean {
    try {
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

interface Props { statusUrl: string; dark: boolean }

export default function BerserkerStatusCard(props: Props) {
    const url = props.statusUrl || DEFAULT_URL
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = React.useState<boolean>(() => (onCanvas ? !!props.dark : readBodyDark()))
    const C = (onCanvas ? !!props.dark : themeDark) ? DARK : LIGHT
    const [state, setState] = React.useState<BerserkerStatus | null>(onCanvas ? SAMPLE : null)
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
            .then((d) => { if (alive) { setState(d as BerserkerStatus); setError(null) } })
            .catch((e) => { if (alive && !state) setError(String(e && e.message ? e.message : e)) })
        return () => { alive = false }
    }, [url, onCanvas])

    const wrap: React.CSSProperties = { width: "100%", boxSizing: "border-box", background: C.bg, fontFamily: FONT, color: C.ink, padding: 16, display: "flex", flexDirection: "column", gap: 12 }
    const card: React.CSSProperties = { background: C.card, borderRadius: 16, padding: "15px 17px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }
    const label = (t: string) => (<div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.03em", color: C.faint, marginBottom: 8 }}>{t}</div>)
    const num: React.CSSProperties = { fontVariantNumeric: "tabular-nums" }

    if (error && !state) return <div style={wrap}><div style={{ ...card, color: C.up, fontSize: 13, fontWeight: 700 }}>버서커 로드 실패: {error.slice(0, 90)}</div></div>
    if (!state) return <div style={wrap}><div style={{ ...card, color: C.faint, fontSize: 13, fontWeight: 600 }}>버서커 상태 로딩…</div></div>

    const pct = Number(state.validation_progress_pct) || 0
    const unlocked = !!state.fully_unlocked
    const barColor = unlocked ? C.green : pct > 0 ? C.vt : C.faint
    const agg = state.aggression || { multiplier: 1, mode: "—" }
    const gates = state.gates || ({} as BerserkerStatus["gates"])
    const locked = state.locked_features || []
    const gateKeys = ["days", "trades", "expectancy", "sqn"] as const

    return (
        <div style={wrap}>
            {/* 헤더 */}
            <div style={card}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 17, fontWeight: 800, letterSpacing: "-0.4px" }}>ARENA 버서커</span>
                    <span style={{ fontSize: 12, fontWeight: 800, color: C.vt, background: C.vtS, borderRadius: 8, padding: "3px 10px" }}>{agg.mode || "—"}</span>
                    <span style={{ marginLeft: "auto", fontSize: 11, color: C.faint, fontWeight: 600, ...num }}>{state.as_of || "—"}</span>
                </div>
                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.5 }}>가설 · shadow only (실자본 0) · 공격성 = 검증 진행도의 함수</div>
            </div>

            {/* 검증 진행도 빅넘버 + 바 */}
            <div style={card}>
                {label("검증 진행도")}
                <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 10 }}>
                    <span style={{ fontSize: 40, fontWeight: 800, letterSpacing: "-1.4px", color: C.ink, ...num }}>{pct.toFixed(1)}%</span>
                    <span style={{ fontSize: 12.5, color: C.faint, fontWeight: 700 }}>{state.validation_overall || "—"}</span>
                </div>
                <div style={{ width: "100%", height: 8, borderRadius: 4, background: C.grid, overflow: "hidden" }}>
                    <div style={{ width: `${Math.max(0, Math.min(100, pct))}%`, height: "100%", borderRadius: 4, background: barColor }} />
                </div>
            </div>

            {/* 4 게이트 */}
            <div style={card}>
                {label("검증 게이트")}
                {gateKeys.map((k) => {
                    const g = gates[k]
                    if (!g) return null
                    const cur = g.current === null || g.current === undefined ? "—" : g.current
                    const done = Number(g.progress) >= 1
                    return (
                        <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", fontSize: 13 }}>
                            <span style={{ color: C.sub, fontWeight: 600 }}>{GATE_LABELS[k] || k}</span>
                            <span style={{ ...num, color: done ? C.green : C.ink, fontWeight: 800 }}>{cur} / {g.target} {g.unit}</span>
                        </div>
                    )
                })}
            </div>

            {/* 잠금 기능 */}
            <div style={card}>
                {label("잠금 기능 (검증량 카운트다운)")}
                {locked.map((f, i) => (
                    <div key={i} style={{ paddingTop: i === 0 ? 0 : 10, marginTop: i === 0 ? 0 : 10, borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span style={{ fontSize: 13.5, fontWeight: 700, color: C.ink }}>{f.label}</span>
                            <span style={{ fontSize: 11, fontWeight: 800, color: f.status === "UNLOCKED" ? C.green : C.amber, background: f.status === "UNLOCKED" ? C.greenS : C.amberS, borderRadius: 7, padding: "2px 8px" }}>
                                {f.status === "UNLOCKED" ? "해제됨" : "잠김"}
                            </span>
                        </div>
                        <div style={{ fontSize: 11.5, color: C.amber, fontWeight: 700, marginTop: 4 }}>잔여 · {f.countdown}</div>
                        {f.note && <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 2 }}>{f.note}</div>}
                    </div>
                ))}
            </div>
        </div>
    )
}

addPropertyControls(BerserkerStatusCard, {
    statusUrl: { type: ControlType.String, title: "Status URL", defaultValue: DEFAULT_URL },
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
})
