// SystemMapCard — VERITY "한눈에 보기" 구조 지도 (Admin 전용, 2026-06-07 신설).
// Framer canvas mirror.
//
// 목적: 운영자(PM)가 자기 시스템 규모/구조를 한눈에 이해. "이게 얼마나 크고
//       무엇으로 구성됐나" 에 답하는 유일한 surface.
// 경계: OperatorCockpit = "지금 건강한가" / SystemMap = "이게 뭐고 얼마나 큰가".
//       헬스/알림/N 상세는 Cockpit 소유 → 여기선 중복 안 함 (구조/규모만).
// source: scripts/system_map.py → data/metadata/system_map.json → publish-data
//         → raw.githubusercontent.com/gywns0126/VERITY-data/main/metadata/system_map.json
// 값은 레포 실제 스캔 결과 (drift 불가). 손으로 그린 다이어그램 금지.
import * as React from "react"
import { addPropertyControls, ControlType } from "framer"

interface Scale {
    code_lines_tsx_py: number
    python_modules: number
    tsx_components: number
    json_data_files: number
    workflows: number
    scheduled_workflows: number
    cron_triggers: number
    git_tracked_files: number
}

interface Subsystem {
    label: string
    count?: number
    scheduled?: number
    n_trading_days?: number
    next_milestone?: { next_n?: number; days_remaining?: number; label?: string }
    by_group?: Record<string, number>
}

interface Funnel {
    stages: number[]
    labels: string[]
    status: string
}

interface SystemMap {
    generated_at: string
    scale: Scale
    subsystems: {
        ingest: Subsystem
        brain: Subsystem
        automation: Subsystem
        surface: Subsystem
        data: Subsystem
        validation: Subsystem
    }
    funnel: Funnel
}

interface Props {
    systemMapUrl: string
}

const GREEN = "#7fffa0"

export default function SystemMapCard(props: Props) {
    const { systemMapUrl } = props
    const [data, setData] = React.useState<SystemMap | null>(null)
    const [error, setError] = React.useState<string | null>(null)

    React.useEffect(() => {
        const ctrl = new AbortController()
        // CDN 캐시 (raw.githubusercontent.com ~5분) 우회 — query param 추가
        const url = `${systemMapUrl}${systemMapUrl.includes("?") ? "&" : "?"}t=${Date.now()}`
        fetch(url, { signal: ctrl.signal, cache: "no-store" })
            .then((r) => r.json())
            .then((d) => setData(d as SystemMap))
            .catch((e) => {
                if (e.name !== "AbortError") setError(String(e))
            })
        return () => ctrl.abort()
    }, [systemMapUrl])

    if (error) {
        return <div style={errorStyle}>system map error: {error.slice(0, 80)}</div>
    }
    if (!data) {
        return <div style={loadingStyle}>system map loading...</div>
    }

    const s = data.scale || ({} as Scale)
    const sub = data.subsystems || ({} as SystemMap["subsystems"])
    const funnel = data.funnel || ({ stages: [], labels: [], status: "" } as Funnel)
    const valN = sub.validation && sub.validation.n_trading_days != null ? sub.validation.n_trading_days : 0
    const valNext = (sub.validation && sub.validation.next_milestone) || {}
    const byGroup = (sub.surface && sub.surface.by_group) || {}
    const groupKeys = Object.keys(byGroup)

    return (
        <div style={containerStyle}>
            {/* Header */}
            <div style={headerStyle}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
                    <span style={{ ...labelStyle, color: GREEN, fontWeight: 600, fontSize: 13 }}>
                        STRUCTURE
                    </span>
                    <span style={titleStyle}>VERITY 한눈에 보기</span>
                </div>
                <span style={timestampStyle}>{(data.generated_at || "—").slice(0, 19)}</span>
            </div>

            {/* Scale headline — "얼마나 큰가" */}
            <div style={section}>
                <div style={{ ...labelStyle, marginBottom: 12 }}>SCALE</div>
                <div style={scaleGridStyle}>
                    <ScaleCell value={fmt(s.code_lines_tsx_py)} unit="줄" label="코드 (tsx+py)" big />
                    <ScaleCell value={fmt(s.python_modules)} unit="" label="Python 모듈" />
                    <ScaleCell value={fmt(s.tsx_components)} unit="" label="컴포넌트" />
                    <ScaleCell value={fmt(s.json_data_files)} unit="" label="발행 데이터" />
                    <ScaleCell value={fmt(s.workflows)} unit="" label="워크플로" />
                    <ScaleCell value={fmt(s.git_tracked_files)} unit="" label="추적 파일" />
                </div>
            </div>

            {/* 6 subsystems — "무엇으로 구성됐나" */}
            <div style={section}>
                <div style={{ ...labelStyle, marginBottom: 10 }}>SUBSYSTEMS</div>
                <SubRow label="수집" en="ingest" value={String(sub.ingest && sub.ingest.count != null ? sub.ingest.count : 0)} hint="모듈" />
                <SubRow label="두뇌" en="brain" value={String(sub.brain && sub.brain.count != null ? sub.brain.count : 0)} hint="api/intelligence" />
                <SubRow
                    label="자동화"
                    en="automation"
                    value={String(sub.automation && sub.automation.count != null ? sub.automation.count : 0)}
                    hint={`스케줄 ${sub.automation && sub.automation.scheduled != null ? sub.automation.scheduled : 0} / cron ${fmt(s.cron_triggers)}`}
                />
                <SubRow label="출력" en="surface" value={String(sub.surface && sub.surface.count != null ? sub.surface.count : 0)} hint="Framer 컴포넌트" />
                <SubRow label="데이터" en="data" value={String(sub.data && sub.data.count != null ? sub.data.count : 0)} hint="발행 JSON" />
                <SubRow label="검증" en="validation" value={`N=${valN}`} hint={valNext.label ? String(valNext.label).slice(0, 28) : "거래일"} valueColor={GREEN} />
            </div>

            {/* Surface 분포 — 페이지 그룹별 컴포넌트 */}
            {groupKeys.length > 0 && (
                <div style={section}>
                    <div style={{ ...labelStyle, marginBottom: 10 }}>출력 분포 (페이지 그룹별)</div>
                    <div style={chipWrapStyle}>
                        {groupKeys.map((g, i) => (
                            <span key={i} style={chipStyle}>
                                {g} <span style={{ color: GREEN, fontWeight: 600 }}>{byGroup[g]}</span>
                            </span>
                        ))}
                    </div>
                </div>
            )}

            {/* Funnel — 5단계 깔때기 (가설 표기 의무, RULE 7) */}
            <div style={sectionLast}>
                <div style={{ ...labelStyle, marginBottom: 10 }}>UNIVERSE FUNNEL</div>
                <div style={funnelWrapStyle}>
                    {(funnel.stages || []).map((st, i) => (
                        <React.Fragment key={i}>
                            <div style={funnelStageStyle}>
                                <div style={funnelNumStyle}>{fmt(st)}</div>
                                <div style={funnelLabelStyle}>{(funnel.labels || [])[i] || ""}</div>
                            </div>
                            {i < (funnel.stages || []).length - 1 && <span style={funnelArrowStyle}>→</span>}
                        </React.Fragment>
                    ))}
                </div>
                <div style={funnelStatusStyle}>{funnel.status}</div>
            </div>
        </div>
    )
}

function fmt(n?: number): string {
    if (n == null) return "—"
    return n.toLocaleString("en-US")
}

function ScaleCell(props: { value: string; unit: string; label: string; big?: boolean }) {
    return (
        <div style={scaleCellStyle}>
            <div style={props.big ? bigNumStyle : numStyle}>
                {props.value}
                {props.unit ? <span style={unitStyle}> {props.unit}</span> : null}
            </div>
            <div style={scaleLabelStyle}>{props.label}</div>
        </div>
    )
}

function SubRow(props: { label: string; en: string; value: string; hint: string; valueColor?: string }) {
    return (
        <div style={subRowStyle}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <span style={subLabelStyle}>{props.label}</span>
                <span style={subEnStyle}>{props.en}</span>
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <span style={subHintStyle}>{props.hint}</span>
                <span style={{ ...subValueStyle, color: props.valueColor || "#ffffff" }}>{props.value}</span>
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
const scaleGridStyle: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: 16,
}
const scaleCellStyle: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 4,
}
const bigNumStyle: React.CSSProperties = {
    fontSize: 32,
    fontFamily: "'Lora', serif",
    fontWeight: 600,
    lineHeight: 1.1,
    color: "#ffffff",
    fontVariantNumeric: "tabular-nums",
}
const numStyle: React.CSSProperties = {
    fontSize: 26,
    fontFamily: "'Lora', serif",
    fontWeight: 600,
    lineHeight: 1.1,
    color: "#ffffff",
    fontVariantNumeric: "tabular-nums",
}
const unitStyle: React.CSSProperties = {
    fontSize: 13,
    color: "#6b7280",
    fontFamily: "'Pretendard', sans-serif",
}
const scaleLabelStyle: React.CSSProperties = {
    fontSize: 11,
    color: "#A8ABB2",
    letterSpacing: "0.02em",
}
const subRowStyle: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "baseline",
    padding: "7px 0",
    borderBottom: "1px solid rgba(255,255,255,0.04)",
}
const subLabelStyle: React.CSSProperties = {
    fontSize: 14,
    fontWeight: 600,
    color: "#ffffff",
}
const subEnStyle: React.CSSProperties = {
    fontSize: 11,
    color: "#6b7280",
    fontFamily: "'SF Mono', monospace",
}
const subHintStyle: React.CSSProperties = {
    fontSize: 11,
    color: "#6b7280",
    fontFamily: "'SF Mono', monospace",
}
const subValueStyle: React.CSSProperties = {
    fontSize: 18,
    fontFamily: "'Lora', serif",
    fontWeight: 600,
    fontVariantNumeric: "tabular-nums",
}
const chipWrapStyle: React.CSSProperties = {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
}
const chipStyle: React.CSSProperties = {
    fontSize: 11,
    color: "#A8ABB2",
    fontFamily: "'SF Mono', monospace",
    background: "rgba(255,255,255,0.04)",
    padding: "4px 10px",
    borderRadius: 6,
    border: "1px solid rgba(255,255,255,0.06)",
}
const funnelWrapStyle: React.CSSProperties = {
    display: "flex",
    flexWrap: "wrap",
    alignItems: "center",
    gap: 8,
}
const funnelStageStyle: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 2,
    minWidth: 56,
}
const funnelNumStyle: React.CSSProperties = {
    fontSize: 18,
    fontFamily: "'Lora', serif",
    fontWeight: 600,
    color: GREEN,
    fontVariantNumeric: "tabular-nums",
}
const funnelLabelStyle: React.CSSProperties = {
    fontSize: 10,
    color: "#A8ABB2",
    textAlign: "center",
}
const funnelArrowStyle: React.CSSProperties = {
    fontSize: 14,
    color: "#6b7280",
}
const funnelStatusStyle: React.CSSProperties = {
    fontSize: 11,
    color: "#FFD600",
    marginTop: 12,
    lineHeight: 1.5,
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

SystemMapCard.defaultProps = {
    systemMapUrl:
        "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/metadata/system_map.json",
}

addPropertyControls(SystemMapCard, {
    systemMapUrl: {
        type: ControlType.String,
        title: "System Map URL",
        defaultValue:
            "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/metadata/system_map.json",
    },
})
