// BerserkerStatusCard — ARENA 버서커 모드 검증 진행도 + 잠금 카운트다운 (PM 6/8 부활).
// Framer canvas mirror. source: api/arena/berserker_status.py 산출 berserker_status.json.
// 공격성 = 검증 N의 함수(validation_progress). 레버리지·숏 = LOCKED + 검증량 카운트다운.
// OperatorCockpitCard 패턴 미러링 (TIDE 디자인 토큰, esbuild-safe).
// 🚨 RULE 7: 자기 산식 = "(가설 / shadow only)" 명시 의무.
import * as React from "react"
import { addPropertyControls, ControlType } from "framer"

interface Gate {
    current: number | null
    target: number
    progress: number
    remaining?: number | null
    unit: string
}

interface LockedFeature {
    name: string
    label: string
    status: "LOCKED" | "UNLOCKED"
    unlock_condition: string
    countdown: string
    note?: string
}

interface BerserkerStatus {
    as_of: string
    validation_overall: string
    validation_progress_pct: number
    gates: { days: Gate; trades: Gate; expectancy: Gate; sqn: Gate }
    aggression: { multiplier: number; mode: string; note?: string }
    locked_features: LockedFeature[]
    fully_unlocked: boolean
    _disclaimer?: string
}

interface Props {
    statusUrl: string
}

const GATE_LABELS: Record<string, string> = {
    days: "거래일",
    trades: "완료 거래",
    expectancy: "기대값 (R)",
    sqn: "SQN",
}

export default function BerserkerStatusCard(props: Props) {
    const { statusUrl } = props
    const [state, setState] = React.useState<BerserkerStatus | null>(null)
    const [error, setError] = React.useState<string | null>(null)

    React.useEffect(() => {
        const ctrl = new AbortController()
        // CDN 캐시 (raw.githubusercontent.com ~5분) 우회
        const url = `${statusUrl}${statusUrl.includes("?") ? "&" : "?"}t=${Date.now()}`
        fetch(url, { signal: ctrl.signal, cache: "no-store" })
            .then((r) => r.json())
            .then((d) => setState(d as BerserkerStatus))
            .catch((e) => {
                if (e.name !== "AbortError") setError(String(e))
            })
        return () => ctrl.abort()
    }, [statusUrl])

    if (error) {
        return <div style={errorStyle}>berserker error: {error.slice(0, 80)}</div>
    }
    if (!state) {
        return <div style={loadingStyle}>berserker loading...</div>
    }

    const pct = state.validation_progress_pct || 0
    const unlocked = !!state.fully_unlocked
    const modeColor = unlocked ? "#7fffa0" : pct > 0 ? "#FFD600" : "#6b7280"
    const gates = state.gates || ({} as BerserkerStatus["gates"])
    const locked = state.locked_features || []
    const gateKeys = ["days", "trades", "expectancy", "sqn"] as const

    return (
        <div style={containerStyle}>
            {/* Header */}
            <div style={headerStyle}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
                    <span style={{ ...labelStyle, color: modeColor, fontWeight: 600, fontSize: 13 }}>
                        {state.aggression?.mode || "—"}
                    </span>
                    <span style={titleStyle}>ARENA Berserker</span>
                </div>
                <span style={timestampStyle}>{state.as_of || "—"}</span>
            </div>

            {/* 가설 / shadow only 명시 (RULE 7) */}
            <div style={disclaimerStyle}>
                가설 · shadow only (실자본 0) · 공격성 = 검증 진행도의 함수
            </div>

            {/* validation_progress 빅넘버 + 바 */}
            <div style={section}>
                <div style={{ ...labelStyle, marginBottom: 8 }}>VALIDATION PROGRESS</div>
                <div style={bigNumStyle}>{pct.toFixed(1)}%</div>
                <div style={barTrackStyle}>
                    <div style={{ ...barFillStyle, width: `${Math.max(0, Math.min(100, pct))}%`, background: modeColor }} />
                </div>
                <div style={{ ...miniStyle, marginTop: 6 }}>
                    overall: {state.validation_overall || "—"}
                </div>
            </div>

            {/* 4 게이트 */}
            <div style={section}>
                <div style={{ ...labelStyle, marginBottom: 8 }}>검증 게이트</div>
                {gateKeys.map((k) => {
                    const g = gates[k]
                    if (!g) return null
                    const cur = g.current === null || g.current === undefined ? "—" : g.current
                    return (
                        <div key={k} style={{ ...rowStyle, padding: "4px 0" }}>
                            <span style={{ ...miniStyle, color: "#A8ABB2" }}>{GATE_LABELS[k] || k}</span>
                            <span style={{ ...miniStyle, color: g.progress >= 1 ? "#7fffa0" : "#ffffff", fontWeight: 600 }}>
                                {cur} / {g.target} {g.unit}
                            </span>
                        </div>
                    )
                })}
            </div>

            {/* 잠금 기능 + 카운트다운 */}
            <div style={sectionLast}>
                <div style={{ ...labelStyle, marginBottom: 8 }}>잠금 기능 (검증량 카운트다운)</div>
                {locked.map((f, i) => (
                    <div key={i} style={lockRowStyle}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 2 }}>
                            <span style={{ fontSize: 13, color: "#ffffff" }}>{f.label}</span>
                            <span style={f.status === "UNLOCKED" ? badgeUnlockStyle : badgeLockStyle}>
                                {f.status === "UNLOCKED" ? "UNLOCKED" : "🔒 LOCKED"}
                            </span>
                        </div>
                        <div style={{ ...miniStyle, color: "#FFD600" }}>잔여: {f.countdown}</div>
                        {f.note && <div style={{ ...miniStyle, color: "#6b7280", fontSize: 10 }}>{f.note}</div>}
                    </div>
                ))}
            </div>
        </div>
    )
}

// ─── TIDE design tokens (docs/design_system_tide.md 정합) ──────────
const containerStyle: React.CSSProperties = {
    width: "100%",
    background: "#0a0a0a",
    color: "#ffffff",
    fontFamily: "'Pretendard', 'Inter', -apple-system, sans-serif",
    padding: 24,
    boxSizing: "border-box",
    borderRadius: 8,
    border: "1px solid rgba(255,255,255,0.06)",
}
const headerStyle: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "baseline",
    paddingBottom: 12,
    borderBottom: "1px solid rgba(255,255,255,0.06)",
}
const titleStyle: React.CSSProperties = {
    fontSize: 14,
    fontWeight: 600,
    color: "#ffffff",
    letterSpacing: "0.01em",
}
const timestampStyle: React.CSSProperties = {
    fontSize: 11,
    color: "#6b7280",
    fontFamily: "'SF Mono', monospace",
    fontVariantNumeric: "tabular-nums",
}
const disclaimerStyle: React.CSSProperties = {
    fontSize: 11,
    color: "#6b7280",
    paddingTop: 12,
    fontStyle: "italic",
    lineHeight: 1.5,
}
const section: React.CSSProperties = {
    marginTop: 20,
    paddingBottom: 16,
    borderBottom: "1px solid rgba(255,255,255,0.06)",
}
const sectionLast: React.CSSProperties = {
    marginTop: 20,
    paddingBottom: 0,
}
const labelStyle: React.CSSProperties = {
    fontSize: 11,
    color: "#6b7280",
    textTransform: "uppercase",
    letterSpacing: "0.04em",
}
const bigNumStyle: React.CSSProperties = {
    fontSize: 56,
    fontFamily: "'Lora', serif",
    fontWeight: 600,
    lineHeight: 1.1,
    color: "#ffffff",
    marginBottom: 12,
    fontVariantNumeric: "tabular-nums",
}
const barTrackStyle: React.CSSProperties = {
    width: "100%",
    height: 6,
    background: "rgba(255,255,255,0.08)",
    borderRadius: 3,
    overflow: "hidden",
}
const barFillStyle: React.CSSProperties = {
    height: "100%",
    borderRadius: 3,
}
const rowStyle: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    fontSize: 13,
}
const miniStyle: React.CSSProperties = {
    fontSize: 12,
    color: "#A8ABB2",
    fontFamily: "'SF Mono', monospace",
    fontVariantNumeric: "tabular-nums",
    lineHeight: 1.5,
}
const lockRowStyle: React.CSSProperties = {
    padding: "8px 0",
    borderBottom: "1px solid rgba(255,255,255,0.04)",
}
const badgeLockStyle: React.CSSProperties = {
    fontSize: 10,
    color: "#FFD600",
    fontWeight: 600,
    letterSpacing: "0.04em",
}
const badgeUnlockStyle: React.CSSProperties = {
    fontSize: 10,
    color: "#7fffa0",
    fontWeight: 600,
    letterSpacing: "0.04em",
}
const errorStyle: React.CSSProperties = {
    padding: 24,
    background: "#0a0a0a",
    color: "#ff5a5a",
    fontSize: 13,
    borderRadius: 8,
    border: "1px solid rgba(255,255,255,0.06)",
}
const loadingStyle: React.CSSProperties = {
    padding: 24,
    background: "#0a0a0a",
    color: "#6b7280",
    fontSize: 13,
    borderRadius: 8,
    border: "1px solid rgba(255,255,255,0.06)",
}

BerserkerStatusCard.defaultProps = {
    statusUrl:
        "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/arena/berserker_status.json",
}

addPropertyControls(BerserkerStatusCard, {
    statusUrl: {
        type: ControlType.String,
        title: "Status URL",
        defaultValue:
            "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/arena/berserker_status.json",
    },
})
