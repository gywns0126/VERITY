// OperatorCockpitCard — Phase 1 P1-b UI (admin dashboard 상단 박음).
// Framer canvas mirror (codeFileId 박힘 후 sync).
// source: plan §Phase 1-b, [[project_win_condition_decision]] option 2.
// PM=approved 2026-05-23.
//
// 데이터 source = cockpitStateUrl (raw URL, VERITY-data publish):
//   https://raw.githubusercontent.com/gywns0126/VERITY-data/main/metadata/cockpit_state.json
//
// 박음 부분:
//  - severity badge (큰 dot + label + reasons 리스트)
//  - operator_deadman 3축 (git / telegram / uaq days)
//  - pre_registration_pending list (RULE 7 audit)
//  - alert_volume_24h (sent / dedupe / quiet / fp_max)
//  - N counter (days + trades + samples)
//
// 신규 컴포넌트 = AdminDashboard 1347 라인 monster 회피 ([[feedback_simple_front_monster_back]]).
import * as React from "react"
import { addPropertyControls, ControlType } from "framer"

interface PendingItem {
    sha: string
    date: string
    subject: string
    missing: string[]
}

interface CockpitState {
    collected_at: string
    severity: "GREEN" | "YELLOW" | "RED"
    severity_reasons: string[]
    n_verification_days: number
    n_milestones: { to_50: number; to_100: number; to_252: number; to_365: number }
    n_trades?: number
    n_validation_samples?: number
    one_liner?: string
    days_clean: { kis: number | null; fred: number | null; telegram: number | null; vercel: number | null }
    operator_deadman: { trigger?: string; days_git?: number; days_telegram?: number; days_uaq?: number; warn_days?: number }
    alert_volume_24h: { sent?: number; dedupe_skip?: number; quiet_skip?: number; fp_repeat_max?: number }
    pre_registration_pending: PendingItem[]
}

interface Props {
    cockpitStateUrl: string
}

const SEV_COLOR: Record<string, string> = {
    GREEN: "#22C55E",
    YELLOW: "#FFD600",
    RED: "#EF4444",
}

const SEV_BG: Record<string, string> = {
    GREEN: "rgba(34, 197, 94, 0.08)",
    YELLOW: "rgba(255, 214, 0, 0.08)",
    RED: "rgba(239, 68, 68, 0.10)",
}

export default function OperatorCockpitCard(props: Props) {
    const { cockpitStateUrl } = props
    const [state, setState] = React.useState<CockpitState | null>(null)
    const [error, setError] = React.useState<string | null>(null)

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
        return <div style={errorStyle}>cockpit error: {error.slice(0, 80)}</div>
    }
    if (!state) {
        return <div style={loadingStyle}>cockpit loading...</div>
    }

    const sevColor = SEV_COLOR[state.severity] || "#6b7280"
    const sevBg = SEV_BG[state.severity] || "rgba(107, 114, 128, 0.08)"
    const odm = state.operator_deadman || {}
    const alertVol = state.alert_volume_24h || {}
    const milestones = state.n_milestones || { to_50: 0, to_100: 0, to_252: 0, to_365: 0 }
    const pending = state.pre_registration_pending || []

    return (
        <div style={{ ...containerStyle, background: sevBg, borderLeft: `3px solid ${sevColor}` }}>
            {/* Header — severity + 한줄평 */}
            <div style={headerStyle}>
                <div style={severityBlockStyle}>
                    <div style={{ ...sevDotStyle, background: sevColor }} />
                    <span style={{ ...sevLabelStyle, color: sevColor }}>{state.severity}</span>
                    <span style={titleStyle}>Operator Cockpit</span>
                </div>
                <span style={timestampStyle}>{state.collected_at?.slice(0, 19) || "—"}</span>
            </div>

            {state.one_liner && (
                <div style={oneLinerStyle}>{state.one_liner}</div>
            )}

            {/* Severity reasons */}
            {state.severity_reasons && state.severity_reasons.length > 0 && (
                <div style={reasonsStyle}>
                    {state.severity_reasons.map((r, i) => (
                        <div key={i} style={reasonRowStyle}>· {r}</div>
                    ))}
                </div>
            )}

            {/* 3 col grid — N counter / deadman / alert */}
            <div style={gridStyle}>
                <Block label="N (verification days)">
                    <div style={bigNumStyle}>{state.n_verification_days || 0}</div>
                    <div style={miniStyle}>
                        50→{milestones.to_50}d / 100→{milestones.to_100}d
                    </div>
                    <div style={miniStyle}>
                        252→{milestones.to_252}d / 365→{milestones.to_365}d
                    </div>
                </Block>

                <Block label="Operator Deadman">
                    <DaysBar label="git" days={odm.days_git} warn={odm.warn_days || 7} />
                    <DaysBar label="telegram" days={odm.days_telegram} warn={odm.warn_days || 7} />
                    <DaysBar label="uaq" days={odm.days_uaq} warn={odm.warn_days || 7} />
                    <div style={{ ...miniStyle, marginTop: 4 }}>
                        trigger: {odm.trigger || "—"}
                    </div>
                </Block>

                <Block label="Alert Volume (24h)">
                    <div style={miniStyle}>sent: {alertVol.sent ?? 0}</div>
                    <div style={miniStyle}>dedupe: {alertVol.dedupe_skip ?? 0}</div>
                    <div style={miniStyle}>quiet: {alertVol.quiet_skip ?? 0}</div>
                    <div style={{ ...miniStyle, color: (alertVol.fp_repeat_max || 0) > 10 ? "#FFD600" : "#A8ABB2" }}>
                        fp_max: {alertVol.fp_repeat_max ?? 0}
                    </div>
                </Block>
            </div>

            {/* pre_registration_pending list */}
            {pending.length > 0 && (
                <div style={pendingSectionStyle}>
                    <div style={pendingTitleStyle}>
                        Pre-registration Pending ({pending.length})
                    </div>
                    {pending.slice(0, 5).map((p, i) => (
                        <div key={i} style={pendingRowStyle}>
                            <span style={pendingShaStyle}>{p.sha}</span>
                            <span style={pendingDateStyle}>{p.date}</span>
                            <span style={pendingSubjectStyle}>{p.subject.slice(0, 60)}</span>
                            <span style={pendingMissingStyle}>missing: {p.missing.join(", ")}</span>
                        </div>
                    ))}
                    {pending.length > 5 && (
                        <div style={{ ...miniStyle, marginTop: 4 }}>
                            +{pending.length - 5}건 더
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}

function Block(props: { label: string; children: React.ReactNode }) {
    return (
        <div style={blockStyle}>
            <div style={labelStyle}>{props.label}</div>
            {props.children}
        </div>
    )
}

function DaysBar(props: { label: string; days?: number; warn: number }) {
    const d = props.days ?? 0
    const color = d >= props.warn ? "#EF4444" : d >= props.warn * 0.7 ? "#FFD600" : "#22C55E"
    return (
        <div style={daysRowStyle}>
            <span style={{ ...labelStyle, width: 60 }}>{props.label}</span>
            <span style={{ ...miniStyle, color, fontWeight: 600 }}>{d.toFixed(1)}d</span>
        </div>
    )
}

const containerStyle: React.CSSProperties = {
    width: "100%",
    color: "#F2F3F5",
    fontFamily: "'Pretendard', 'Inter', -apple-system, sans-serif",
    padding: 16,
    boxSizing: "border-box",
    borderRadius: 6,
    border: "1px solid #23242C",
    marginBottom: 16,
}
const headerStyle: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
}
const severityBlockStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 10,
}
const sevDotStyle: React.CSSProperties = {
    width: 10,
    height: 10,
    borderRadius: "50%",
}
const sevLabelStyle: React.CSSProperties = {
    fontSize: 13,
    fontWeight: 700,
    letterSpacing: "0.04em",
}
const titleStyle: React.CSSProperties = {
    fontSize: 14,
    fontWeight: 600,
    color: "#F2F3F5",
}
const timestampStyle: React.CSSProperties = {
    fontSize: 11,
    color: "#6B6E76",
    fontFamily: "'SF Mono', monospace",
    fontVariantNumeric: "tabular-nums",
}
const oneLinerStyle: React.CSSProperties = {
    fontSize: 13,
    color: "#F2F3F5",
    paddingBottom: 8,
    marginBottom: 12,
    borderBottom: "1px solid rgba(255,255,255,0.04)",
    letterSpacing: "0.01em",
}
const reasonsStyle: React.CSSProperties = {
    marginBottom: 12,
    padding: 8,
    background: "rgba(0,0,0,0.2)",
    borderRadius: 4,
    fontSize: 11,
}
const reasonRowStyle: React.CSSProperties = {
    color: "#F2F3F5",
    marginBottom: 2,
}
const gridStyle: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: 12,
    marginBottom: 12,
}
const blockStyle: React.CSSProperties = {
    padding: 10,
    background: "rgba(255,255,255,0.02)",
    borderRadius: 4,
    border: "1px solid #23242C",
}
const labelStyle: React.CSSProperties = {
    fontSize: 11,
    color: "#6B6E76",
    textTransform: "uppercase",
    letterSpacing: "0.04em",
    marginBottom: 4,
    display: "inline-block",
}
const bigNumStyle: React.CSSProperties = {
    fontSize: 32,
    fontWeight: 700,
    fontFamily: "'Lora', serif",
    color: "#F2F3F5",
    lineHeight: 1.1,
    marginBottom: 4,
}
const miniStyle: React.CSSProperties = {
    fontSize: 11,
    color: "#A8ABB2",
    fontFamily: "'SF Mono', monospace",
    fontVariantNumeric: "tabular-nums",
    lineHeight: 1.5,
}
const daysRowStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 8,
    marginBottom: 2,
}
const pendingSectionStyle: React.CSSProperties = {
    marginTop: 8,
    paddingTop: 12,
    borderTop: "1px solid #23242C",
}
const pendingTitleStyle: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 600,
    color: "#FFD600",
    marginBottom: 8,
    letterSpacing: "0.02em",
}
const pendingRowStyle: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: "70px 80px 1fr",
    gap: 8,
    fontSize: 11,
    fontFamily: "'SF Mono', monospace",
    color: "#A8ABB2",
    padding: "4px 0",
    borderBottom: "1px solid rgba(255,255,255,0.02)",
}
const pendingShaStyle: React.CSSProperties = {
    color: "#5BA9FF",
}
const pendingDateStyle: React.CSSProperties = {
    color: "#6B6E76",
}
const pendingSubjectStyle: React.CSSProperties = {
    color: "#F2F3F5",
}
const pendingMissingStyle: React.CSSProperties = {
    gridColumn: "1 / -1",
    color: "#FFD600",
    fontSize: 10,
    paddingLeft: 78,
}
const errorStyle: React.CSSProperties = {
    padding: 16,
    background: "#0E0F11",
    color: "#EF4444",
    fontSize: 12,
    borderRadius: 4,
}
const loadingStyle: React.CSSProperties = {
    padding: 16,
    background: "#0E0F11",
    color: "#6B6E76",
    fontSize: 12,
    borderRadius: 4,
}

OperatorCockpitCard.defaultProps = {
    cockpitStateUrl:
        "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/metadata/cockpit_state.json",
}

addPropertyControls(OperatorCockpitCard, {
    cockpitStateUrl: {
        type: ControlType.String,
        title: "Cockpit URL",
        defaultValue:
            "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/metadata/cockpit_state.json",
    },
})
