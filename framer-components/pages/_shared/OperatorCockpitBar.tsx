// OperatorCockpitBar v2 — Phase 1 P1-a UI (TIDE 디자인 정합, 2026-05-27 재설계).
// Framer canvas mirror (codeFileId 박힘 후 sync).
// source: plan §Phase 1-a + docs/design_system_tide.md
// PM=approved 2026-05-23.
//
// v2 변경 (2026-05-27):
//   - 이모지 제거 (옛 🌗 박은 부분)
//   - 좌측 strip 제거
//   - horizontal border 박음 (TIDE 패턴 — BrainGradeBreakdown reference)
//   - label UPPERCASE 11px 0.04em letter-spacing
//   - number Lora serif
//
// 데이터 source = cockpitStateUrl (raw URL, VERITY-data publish).
import * as React from "react"
import { addPropertyControls, ControlType } from "framer"

interface CockpitState {
    collected_at: string
    severity: "GREEN" | "YELLOW" | "RED"
    severity_reasons: string[]
    n_verification_days: number
    n_milestones: { to_50: number; to_100: number; to_252: number; to_365: number }
    one_liner?: string
    days_clean: { kis: number | null; fred: number | null; telegram: number | null; vercel: number | null }
    alert_volume_24h: { sent?: number; dedupe_skip?: number; quiet_skip?: number; fp_repeat_max?: number }
    pre_registration_pending: any[]
}

interface Props {
    cockpitStateUrl: string
    showOneLiner: boolean
    showDetail: boolean
}

const SEV_COLOR: Record<string, string> = {
    GREEN: "#22C55E",
    YELLOW: "#FFD600",
    RED: "#EF4444",
}

export default function OperatorCockpitBar(props: Props) {
    const { cockpitStateUrl, showOneLiner, showDetail } = props
    const [state, setState] = React.useState<CockpitState | null>(null)
    const [error, setError] = React.useState<string | null>(null)
    const [hover, setHover] = React.useState<boolean>(false)

    React.useEffect(() => {
        const ctrl = new AbortController()
        // CDN 캐시 (raw.githubusercontent.com ~5분) 우회 — query param 박음
        const url = `${cockpitStateUrl}${cockpitStateUrl.includes("?") ? "&" : "?"}t=${Date.now()}`
        fetch(url, { signal: ctrl.signal, cache: "no-store" })
            .then((r) => r.json())
            .then((d) => setState(d as CockpitState))
            .catch((e) => {
                if (e.name !== "AbortError") setError(String(e))
            })
        return () => ctrl.abort()
    }, [cockpitStateUrl])

    if (error) {
        return <div style={errorStyle}>cockpit error: {error.slice(0, 60)}</div>
    }
    if (!state) {
        return <div style={loadingStyle}>cockpit loading...</div>
    }

    const sevColor = SEV_COLOR[state.severity] || "#6b7280"
    const nDays = state.n_verification_days || 0
    const milestones = state.n_milestones || { to_50: 0, to_100: 0, to_252: 0, to_365: 0 }
    const alertVol = state.alert_volume_24h || {}
    const fpMax = alertVol.fp_repeat_max || 0
    const daysClean = state.days_clean || { kis: null, fred: null, telegram: null, vercel: null }

    const cleanEntries: Array<[string, number | null]> = [
        ["kis", daysClean.kis],
        ["fred", daysClean.fred],
        ["telegram", daysClean.telegram],
    ]
    const weakest = cleanEntries
        .filter(([, v]) => v !== null && v !== undefined)
        .sort(([, a], [, b]) => (a || 0) - (b || 0))[0]
    const weakestLabel = weakest
        ? weakest[0].toUpperCase() + " " + (weakest[1] === 0 ? "결함" : "clean")
        : "—"

    return (
        <div style={containerStyle}>
            {showOneLiner && state.one_liner && (
                <div style={oneLinerStyle}>{state.one_liner}</div>
            )}
            <div style={barStyle}>
                <div
                    style={{ ...dotWrapStyle, position: "relative" }}
                    onMouseEnter={() => setHover(true)}
                    onMouseLeave={() => setHover(false)}
                >
                    <span style={{ ...labelStyle, color: sevColor, fontWeight: 600 }}>{state.severity}</span>
                    {hover && state.severity_reasons.length > 0 && (
                        <div style={tooltipStyle}>
                            {state.severity_reasons.map((r, i) => (
                                <div key={i} style={{ marginBottom: 4 }}>· {r}</div>
                            ))}
                        </div>
                    )}
                </div>

                <span style={separatorStyle}>·</span>

                <div style={textBlockStyle}>
                    <span style={labelStyle}>N</span>
                    <span style={numberStyle}>{nDays}</span>
                    <span style={miniStyle}>
                        50까지 {milestones.to_50}일 · 365까지 {milestones.to_365}일
                    </span>
                </div>

                <span style={separatorStyle}>·</span>

                <div style={textBlockStyle}>
                    <span style={labelStyle}>weakest</span>
                    <span style={{ ...miniStyle, color: weakest && weakest[1] === 0 ? "#ff5a5a" : "#A8ABB2" }}>
                        {weakestLabel}
                    </span>
                </div>

                {showDetail && (
                    <>
                        <span style={separatorStyle}>·</span>
                        <div style={textBlockStyle}>
                            <span style={labelStyle}>alert fp_max</span>
                            <span style={{ ...miniStyle, color: fpMax > 10 ? "#FFD600" : "#A8ABB2" }}>
                                {fpMax}
                            </span>
                        </div>
                        {state.pre_registration_pending && state.pre_registration_pending.length > 0 && (
                            <>
                                <span style={separatorStyle}>·</span>
                                <div style={textBlockStyle}>
                                    <span style={labelStyle}>pre-reg</span>
                                    <span style={{ ...miniStyle, color: "#FFD600" }}>
                                        {state.pre_registration_pending.length}건
                                    </span>
                                </div>
                            </>
                        )}
                    </>
                )}
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
    padding: "16px 24px",
    boxSizing: "border-box",
    borderRadius: 8,
    border: "1px solid rgba(255,255,255,0.06)",
}
const oneLinerStyle: React.CSSProperties = {
    fontSize: 14,
    color: "#ffffff",
    paddingBottom: 10,
    marginBottom: 10,
    borderBottom: "1px solid rgba(255,255,255,0.04)",
    letterSpacing: "0.01em",
}
const barStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 10,
    flexWrap: "wrap",
    fontSize: 12,
}
const dotWrapStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    cursor: "default",
}
const textBlockStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "baseline",
    gap: 6,
}
const labelStyle: React.CSSProperties = {
    fontSize: 11,
    color: "#6b7280",
    textTransform: "uppercase",
    letterSpacing: "0.04em",
}
const numberStyle: React.CSSProperties = {
    fontSize: 14,
    fontWeight: 600,
    color: "#ffffff",
    fontFamily: "'Lora', serif",
    fontVariantNumeric: "tabular-nums",
}
const miniStyle: React.CSSProperties = {
    fontSize: 11,
    color: "#A8ABB2",
    fontFamily: "'SF Mono', monospace",
    fontVariantNumeric: "tabular-nums",
}
const separatorStyle: React.CSSProperties = {
    color: "#6b7280",
    fontSize: 11,
}
const tooltipStyle: React.CSSProperties = {
    position: "absolute",
    top: "calc(100% + 6px)",
    left: 0,
    minWidth: 240,
    maxWidth: 360,
    background: "#141414",
    border: "1px solid #34353D",
    borderRadius: 4,
    padding: 10,
    fontSize: 11,
    color: "#ffffff",
    zIndex: 10,
    lineHeight: 1.5,
}
const errorStyle: React.CSSProperties = {
    padding: 16,
    background: "#0a0a0a",
    color: "#ff5a5a",
    fontSize: 13,
    fontFamily: "'Pretendard', sans-serif",
    borderRadius: 8,
    border: "1px solid rgba(255,255,255,0.06)",
}
const loadingStyle: React.CSSProperties = {
    padding: 16,
    background: "#0a0a0a",
    color: "#6b7280",
    fontSize: 13,
    fontFamily: "'Pretendard', sans-serif",
    borderRadius: 8,
    border: "1px solid rgba(255,255,255,0.06)",
}

OperatorCockpitBar.defaultProps = {
    cockpitStateUrl:
        "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/metadata/cockpit_state.json",
    showOneLiner: true,
    showDetail: true,
}

addPropertyControls(OperatorCockpitBar, {
    cockpitStateUrl: {
        type: ControlType.String,
        title: "Cockpit URL",
        defaultValue:
            "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/metadata/cockpit_state.json",
    },
    showOneLiner: {
        type: ControlType.Boolean,
        title: "한줄평 표시",
        defaultValue: true,
    },
    showDetail: {
        type: ControlType.Boolean,
        title: "Detail 표시",
        defaultValue: true,
    },
})
