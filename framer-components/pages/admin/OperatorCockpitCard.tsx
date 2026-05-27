// OperatorCockpitCard v2 — Phase 1 P1-b UI (TIDE 디자인 정합, 2026-05-27 재설계).
// Framer canvas mirror.
// source: plan §Phase 1-b + docs/design_system_tide.md
// PM=approved 2026-05-23.
//
// v2 변경 (2026-05-27):
//   - 좌측 초록 strip 제거 (borderLeft: 3px)
//   - sevBg tinted background 제거 (flat #0a0a0a)
//   - 이모지 제거
//   - horizontal border 박음 (TIDE 패턴)
//   - label UPPERCASE 11px / number Lora serif 박음
//   - block sub-card 박은 부분 단순 horizontal section 박음
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

export default function OperatorCockpitCard(props: Props) {
    const { cockpitStateUrl } = props
    const [state, setState] = React.useState<CockpitState | null>(null)
    const [error, setError] = React.useState<string | null>(null)

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
        return <div style={errorStyle}>cockpit error: {error.slice(0, 80)}</div>
    }
    if (!state) {
        return <div style={loadingStyle}>cockpit loading...</div>
    }

    const sevColor = SEV_COLOR[state.severity] || "#6b7280"
    const odm = state.operator_deadman || {}
    const alertVol = state.alert_volume_24h || {}
    const milestones = state.n_milestones || { to_50: 0, to_100: 0, to_252: 0, to_365: 0 }
    const pending = state.pre_registration_pending || []

    return (
        <div style={containerStyle}>
            {/* Header — severity + title */}
            <div style={headerStyle}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
                    <span style={{ ...labelStyle, color: sevColor, fontWeight: 600, fontSize: 13 }}>
                        {state.severity}
                    </span>
                    <span style={titleStyle}>Operator Cockpit</span>
                </div>
                <span style={timestampStyle}>{state.collected_at?.slice(0, 19) || "—"}</span>
            </div>

            {state.one_liner && (
                <div style={oneLinerStyle}>{state.one_liner}</div>
            )}

            {/* Severity reasons (RED/YELLOW 박음 시) */}
            {state.severity_reasons && state.severity_reasons.length > 0 && (
                <div style={section}>
                    <div style={{ ...labelStyle, marginBottom: 6 }}>SEVERITY REASONS</div>
                    {state.severity_reasons.map((r, i) => (
                        <div key={i} style={reasonRowStyle}>· {r}</div>
                    ))}
                </div>
            )}

            {/* Section 1 — N counter */}
            <div style={section}>
                <div style={{ ...labelStyle, marginBottom: 8 }}>N (verification days)</div>
                <div style={bigNumStyle}>{state.n_verification_days || 0}</div>
                <div style={miniStyle}>
                    50까지 {milestones.to_50}일 · 100까지 {milestones.to_100}일 · 252까지 {milestones.to_252}일 · 365까지 {milestones.to_365}일
                </div>
            </div>

            {/* Section 2 — Operator Deadman 3축 */}
            <div style={section}>
                <div style={{ ...labelStyle, marginBottom: 8 }}>Operator Deadman</div>
                <DaysRow label="git" days={odm.days_git} warn={odm.warn_days || 7} />
                <DaysRow label="telegram" days={odm.days_telegram} warn={odm.warn_days || 7} />
                <DaysRow label="uaq" days={odm.days_uaq} warn={odm.warn_days || 7} />
                <div style={{ ...miniStyle, marginTop: 6 }}>trigger: {odm.trigger || "—"}</div>
            </div>

            {/* Section 3 — Alert Volume 24h */}
            <div style={section}>
                <div style={{ ...labelStyle, marginBottom: 8 }}>Alert Volume (24h)</div>
                <KvRow label="sent" value={String(alertVol.sent ?? 0)} />
                <KvRow label="dedupe_skip" value={String(alertVol.dedupe_skip ?? 0)} />
                <KvRow label="quiet_skip" value={String(alertVol.quiet_skip ?? 0)} />
                <KvRow
                    label="fp_repeat_max"
                    value={String(alertVol.fp_repeat_max ?? 0)}
                    valueColor={(alertVol.fp_repeat_max || 0) > 10 ? "#FFD600" : "#A8ABB2"}
                />
            </div>

            {/* Section 4 — pre_registration_pending */}
            {pending.length > 0 && (
                <div style={sectionLast}>
                    <div style={{ ...labelStyle, marginBottom: 8, color: "#FFD600" }}>
                        Pre-registration Pending ({pending.length})
                    </div>
                    {pending.slice(0, 5).map((p, i) => (
                        <div key={i} style={pendingRowStyle}>
                            <div style={{ display: "flex", gap: 12, marginBottom: 2 }}>
                                <span style={pendingShaStyle}>{p.sha}</span>
                                <span style={pendingDateStyle}>{p.date}</span>
                                <span style={pendingSubjectStyle}>{p.subject.slice(0, 60)}</span>
                            </div>
                            <div style={pendingMissingStyle}>missing: {p.missing.join(", ")}</div>
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

function DaysRow(props: { label: string; days?: number; warn: number }) {
    const d = props.days ?? 0
    const color = d >= props.warn ? "#ff5a5a" : d >= props.warn * 0.7 ? "#FFD600" : "#7fffa0"
    return (
        <div style={{ ...rowStyle, padding: "3px 0" }}>
            <span style={{ ...miniStyle, color: "#A8ABB2" }}>{props.label}</span>
            <span style={{ ...miniStyle, color, fontWeight: 600 }}>{d.toFixed(1)}d</span>
        </div>
    )
}

function KvRow(props: { label: string; value: string; valueColor?: string }) {
    return (
        <div style={{ ...rowStyle, padding: "3px 0" }}>
            <span style={{ ...miniStyle, color: "#A8ABB2" }}>{props.label}</span>
            <span style={{ ...miniStyle, color: props.valueColor || "#ffffff", fontWeight: 600 }}>
                {props.value}
            </span>
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
const oneLinerStyle: React.CSSProperties = {
    fontSize: 14,
    color: "#ffffff",
    paddingTop: 16,
    paddingBottom: 16,
    borderBottom: "1px solid rgba(255,255,255,0.06)",
    letterSpacing: "0.01em",
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
    marginBottom: 8,
    fontVariantNumeric: "tabular-nums",
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
const reasonRowStyle: React.CSSProperties = {
    fontSize: 12,
    color: "#ffffff",
    marginBottom: 4,
    lineHeight: 1.5,
}
const pendingRowStyle: React.CSSProperties = {
    fontSize: 11,
    fontFamily: "'SF Mono', monospace",
    color: "#A8ABB2",
    padding: "8px 0",
    borderBottom: "1px solid rgba(255,255,255,0.04)",
    lineHeight: 1.5,
}
const pendingShaStyle: React.CSSProperties = {
    color: "#5BA9FF",
}
const pendingDateStyle: React.CSSProperties = {
    color: "#6b7280",
}
const pendingSubjectStyle: React.CSSProperties = {
    color: "#ffffff",
    flex: 1,
}
const pendingMissingStyle: React.CSSProperties = {
    color: "#FFD600",
    fontSize: 10,
}
const errorStyle: React.CSSProperties = {
    padding: 24,
    background: "#0a0a0a",
    color: "#ff5a5a",
    fontSize: 13,
}
const loadingStyle: React.CSSProperties = {
    padding: 24,
    background: "#0a0a0a",
    color: "#6b7280",
    fontSize: 13,
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
