// OperatorCockpitBar — Phase 1 P1-a UI (Cockpit dot + N counter + 한줄평).
// Framer canvas mirror (codeFileId 박힘 후 sync).
// source: plan §Phase 1-a, [[project_win_condition_decision]] option 2.
// PM=approved 2026-05-23.
//
// 데이터 source = cockpitStateUrl (raw URL, VERITY-data publish):
//   https://raw.githubusercontent.com/gywns0126/VERITY-data/main/metadata/cockpit_state.json
//
// 합성 0, 모든 표기 = cockpit_state.json 박은 부분 read-only.
// LLM 호출 0 (RULE 6 통과).
// 신규 컴포넌트 = SystemHealthBar 1719 라인 monster 회피 ([[feedback_simple_front_monster_back]]).
import * as React from "react"
import { addPropertyControls, ControlType } from "framer"

interface CockpitState {
    collected_at: string
    severity: "GREEN" | "YELLOW" | "RED"
    severity_reasons: string[]
    n_verification_days: number
    n_milestones: { to_50: number; to_100: number; to_252: number; to_365: number }
    n_trades?: number
    trade_milestones?: { to_50: number; to_100: number; to_252: number; to_365: number }
    n_validation_samples?: number
    sample_milestones?: { to_50: number; to_100: number; to_252: number; to_365: number }
    one_liner?: string
    days_clean: { kis: number | null; fred: number | null; telegram: number | null; vercel: number | null }
    operator_deadman: { trigger?: string; days_git?: number; days_telegram?: number; days_uaq?: number }
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

/**
 * OperatorCockpitBar — Phase 1 P1-a UI.
 *
 * 박음 부분:
 *  - 한줄평 (one_liner, P1-e 박음 — LLM 호출 0)
 *  - severity dot (hover 시 severity_reasons[] 노출)
 *  - N counter mini (N=30 → 50까지 20일)
 *  - days_clean 최약축 (KIS / FRED / Telegram)
 *  - alert_volume_24h fp_repeat_max (telegram 결함 시그널)
 */
export default function OperatorCockpitBar(props: Props) {
    const { cockpitStateUrl, showOneLiner, showDetail } = props
    const [state, setState] = React.useState<CockpitState | null>(null)
    const [error, setError] = React.useState<string | null>(null)
    const [hover, setHover] = React.useState<boolean>(false)

    React.useEffect(() => {
        const ctrl = new AbortController()
        fetch(cockpitStateUrl, { signal: ctrl.signal, cache: "no-store" })
            .then((r) => r.json())
            .then((d) => setState(d as CockpitState))
            .catch((e) => {
                if (e.name !== "AbortError") setError(String(e))
            })
        return () => ctrl.abort()
    }, [cockpitStateUrl])

    if (error) {
        return (
            <div style={errorStyle}>
                cockpit error: {error.slice(0, 60)}
            </div>
        )
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

    // days_clean 최약축 (1=clean, 0=결함, null=N/A)
    type CleanKey = "kis" | "fred" | "telegram"
    const cleanEntries: Array<[CleanKey, number | null]> = [
        ["kis", daysClean.kis],
        ["fred", daysClean.fred],
        ["telegram", daysClean.telegram],
    ]
    const weakest = cleanEntries
        .filter(([, v]) => v !== null && v !== undefined)
        .sort(([, a], [, b]) => (a || 0) - (b || 0))[0]
    const weakestLabel = weakest
        ? `${weakest[0].toUpperCase()} ${weakest[1] === 0 ? "결함" : "clean"}`
        : "—"

    return (
        <div style={containerStyle}>
            {/* 한줄평 (P1-e) */}
            {showOneLiner && state.one_liner && (
                <div style={oneLinerStyle}>{state.one_liner}</div>
            )}

            <div style={barStyle}>
                {/* severity dot (hover = reasons[]) */}
                <div
                    style={{ ...dotWrapStyle, position: "relative" }}
                    onMouseEnter={() => setHover(true)}
                    onMouseLeave={() => setHover(false)}
                >
                    <div style={{ ...dotStyle, background: sevColor }} />
                    <span style={sevLabelStyle}>{state.severity}</span>
                    {hover && state.severity_reasons.length > 0 && (
                        <div style={tooltipStyle}>
                            {state.severity_reasons.map((r, i) => (
                                <div key={i} style={{ marginBottom: 4 }}>· {r}</div>
                            ))}
                        </div>
                    )}
                </div>

                <Divider />

                {/* N counter mini */}
                <div style={textBlockStyle}>
                    <span style={labelStyle}>N=</span>
                    <span style={numberStyle}>{nDays}</span>
                    <span style={miniStyle}>
                        → 50까지 {milestones.to_50}일 / 365까지 {milestones.to_365}일
                    </span>
                </div>

                <Divider />

                {/* days_clean 최약축 */}
                <div style={textBlockStyle}>
                    <span style={labelStyle}>weakest:</span>
                    <span style={{ ...miniStyle, color: weakest && weakest[1] === 0 ? "#EF4444" : "#A8ABB2" }}>
                        {weakestLabel}
                    </span>
                </div>

                {showDetail && (
                    <>
                        <Divider />
                        {/* alert_volume fp_repeat_max */}
                        <div style={textBlockStyle}>
                            <span style={labelStyle}>alert fp_max:</span>
                            <span style={{ ...miniStyle, color: fpMax > 10 ? "#FFD600" : "#A8ABB2" }}>
                                {fpMax}
                            </span>
                        </div>

                        {/* pre_registration_pending */}
                        {state.pre_registration_pending && state.pre_registration_pending.length > 0 && (
                            <>
                                <Divider />
                                <div style={textBlockStyle}>
                                    <span style={labelStyle}>pre-reg pending:</span>
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

function Divider() {
    return <div style={dividerStyle} />
}

const containerStyle: React.CSSProperties = {
    width: "100%",
    background: "#0E0F11",
    color: "#F2F3F5",
    fontFamily: "'Pretendard', 'Inter', -apple-system, sans-serif",
    padding: "12px 16px",
    boxSizing: "border-box",
    borderBottom: "1px solid #23242C",
}
const oneLinerStyle: React.CSSProperties = {
    fontSize: 14,
    color: "#F2F3F5",
    paddingBottom: 8,
    marginBottom: 8,
    borderBottom: "1px solid rgba(255,255,255,0.04)",
    letterSpacing: "0.01em",
}
const barStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexWrap: "wrap",
    fontSize: 12,
    fontFamily: "'SF Mono', 'JetBrains Mono', monospace",
    fontVariantNumeric: "tabular-nums",
}
const dotWrapStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 6,
    cursor: "default",
}
const dotStyle: React.CSSProperties = {
    width: 8,
    height: 8,
    borderRadius: "50%",
}
const sevLabelStyle: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 600,
    color: "#F2F3F5",
    letterSpacing: "0.04em",
}
const dividerStyle: React.CSSProperties = {
    width: 1,
    height: 12,
    background: "#23242C",
}
const textBlockStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "baseline",
    gap: 4,
}
const labelStyle: React.CSSProperties = {
    fontSize: 11,
    color: "#6B6E76",
    textTransform: "uppercase",
    letterSpacing: "0.04em",
}
const numberStyle: React.CSSProperties = {
    fontSize: 13,
    fontWeight: 600,
    color: "#F2F3F5",
}
const miniStyle: React.CSSProperties = {
    fontSize: 11,
    color: "#A8ABB2",
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
    padding: 8,
    fontSize: 11,
    color: "#F2F3F5",
    zIndex: 10,
    boxShadow: "0 4px 12px rgba(0,0,0,0.5)",
}
const errorStyle: React.CSSProperties = {
    padding: 12,
    background: "#0E0F11",
    color: "#EF4444",
    fontSize: 12,
    fontFamily: "'Pretendard', sans-serif",
}
const loadingStyle: React.CSSProperties = {
    padding: 12,
    background: "#0E0F11",
    color: "#6B6E76",
    fontSize: 12,
    fontFamily: "'Pretendard', sans-serif",
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
