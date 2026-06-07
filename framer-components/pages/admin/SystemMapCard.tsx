// SystemMapCard — VERITY "한눈에 보기" 구조 지도 (Admin 전용, 2026-06-07 신설).
// Framer canvas mirror.
//
// 목적: 운영자(PM)가 자기 시스템 규모/구조를 한눈에 이해. "이게 얼마나 크고
//       무엇으로 구성됐나" 에 답하는 유일한 surface.
// v2 (2026-06-07): 숫자 표 → 시각 다이어그램 (수집→두뇌→출력 spine + 자동화 엔진
//                  + 데이터/검증 + funnel 막대). 같은 JSON fetch 유지 (5분 자동 갱신).
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

    const cnt = (k: keyof SystemMap["subsystems"]) => {
        const node = sub[k]
        return node && node.count != null ? node.count : 0
    }
    const valN = sub.validation && sub.validation.n_trading_days != null ? sub.validation.n_trading_days : 0
    const valNext = (sub.validation && sub.validation.next_milestone) || {}
    const scheduled = sub.automation && sub.automation.scheduled != null ? sub.automation.scheduled : 0

    const stages = funnel.stages || []
    const labels = funnel.labels || []
    const maxStage = stages.length > 0 ? Math.max.apply(null, stages) : 1

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

            {/* Scale strip — compact 규모 */}
            <div style={scaleStripStyle}>
                <Stat value={fmt(s.code_lines_tsx_py)} label="코드 줄" />
                <Dot />
                <Stat value={fmt(s.python_modules)} label="Python" />
                <Dot />
                <Stat value={fmt(s.tsx_components)} label="컴포넌트" />
                <Dot />
                <Stat value={fmt(s.json_data_files)} label="발행 데이터" />
                <Dot />
                <Stat value={fmt(s.git_tracked_files)} label="추적 파일" />
            </div>

            {/* Pipeline diagram — 수집 → 두뇌 → 출력 spine */}
            <div style={section}>
                <div style={{ ...labelStyle, marginBottom: 14 }}>PIPELINE</div>
                <div style={spineStyle}>
                    <StageBox kr="수집" en="ingest" count={cnt("ingest")} sub="KIS · DART · FRED · sentiment" />
                    <Arrow />
                    <StageBox kr="두뇌" en="brain" count={cnt("brain")} sub="api/intelligence" accent />
                    <Arrow />
                    <StageBox kr="출력" en="surface" count={cnt("surface")} sub="Framer 컴포넌트" />
                </div>

                {/* 자동화 엔진 — 파이프라인 구동 */}
                <div style={engineBarStyle}>
                    <span style={engineLabelStyle}>⚙ 자동화 엔진</span>
                    <span style={engineValStyle}>
                        {fmt(cnt("automation"))} 워크플로
                        <span style={{ color: "#6b7280" }}> · {scheduled} 스케줄 / {fmt(s.cron_triggers)} cron</span>
                        <span style={{ color: "#6b7280" }}> — 위 파이프라인 구동</span>
                    </span>
                </div>

                {/* 데이터 / 검증 */}
                <div style={outRowStyle}>
                    <SideBox kr="데이터" en="data" value={fmt(cnt("data"))} sub="발행 JSON" />
                    <SideBox kr="검증" en="validation" value={`N=${valN}`} sub={valNext.label ? String(valNext.label).slice(0, 26) : "거래일"} accent />
                </div>
            </div>

            {/* Funnel — 5단계 깔때기 (막대 시각화, 가설 표기 의무 RULE 7) */}
            <div style={sectionLast}>
                <div style={{ ...labelStyle, marginBottom: 12 }}>UNIVERSE FUNNEL</div>
                {stages.map((st, i) => {
                    const w = Math.max(8, Math.round((Math.log(st + 1) / Math.log(maxStage + 1)) * 100))
                    return (
                        <div key={i} style={funnelRowStyle}>
                            <span style={funnelNumStyle}>{fmt(st)}</span>
                            <div style={funnelTrackStyle}>
                                <div style={{ ...funnelBarStyle, width: `${w}%` }} />
                            </div>
                            <span style={funnelLabelStyle}>{labels[i] || ""}</span>
                        </div>
                    )
                })}
                <div style={funnelStatusStyle}>{funnel.status}</div>
            </div>
        </div>
    )
}

function fmt(n?: number): string {
    if (n == null) return "—"
    return n.toLocaleString("en-US")
}

function Dot() {
    return <span style={{ color: "#2a2a30", fontSize: 12 }}>·</span>
}

function Stat(props: { value: string; label: string }) {
    return (
        <span style={{ display: "inline-flex", alignItems: "baseline", gap: 6 }}>
            <span style={statValStyle}>{props.value}</span>
            <span style={statLabelStyle}>{props.label}</span>
        </span>
    )
}

function Arrow() {
    return <span style={arrowStyle}>→</span>
}

function StageBox(props: { kr: string; en: string; count: number; sub: string; accent?: boolean }) {
    return (
        <div style={{ ...stageBoxStyle, borderColor: props.accent ? "rgba(127,255,160,0.4)" : "rgba(255,255,255,0.1)" }}>
            <div style={stageHeadStyle}>
                <span style={stageKrStyle}>{props.kr}</span>
                <span style={stageEnStyle}>{props.en}</span>
            </div>
            <div style={{ ...stageNumStyle, color: props.accent ? GREEN : "#ffffff" }}>{fmt(props.count)}</div>
            <div style={stageSubStyle}>{props.sub}</div>
        </div>
    )
}

function SideBox(props: { kr: string; en: string; value: string; sub: string; accent?: boolean }) {
    return (
        <div style={{ ...sideBoxStyle, borderColor: props.accent ? "rgba(127,255,160,0.4)" : "rgba(255,255,255,0.1)" }}>
            <div style={stageHeadStyle}>
                <span style={stageKrStyle}>{props.kr}</span>
                <span style={stageEnStyle}>{props.en}</span>
            </div>
            <div style={{ ...sideNumStyle, color: props.accent ? GREEN : "#ffffff" }}>{props.value}</div>
            <div style={stageSubStyle}>{props.sub}</div>
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
const scaleStripStyle: React.CSSProperties = {
    display: "flex",
    flexWrap: "wrap",
    alignItems: "baseline",
    gap: 10,
    marginTop: 16,
    paddingBottom: 16,
    borderBottom: "1px solid rgba(255,255,255,0.06)",
}
const statValStyle: React.CSSProperties = {
    fontSize: 16,
    fontFamily: "'Lora', serif",
    fontWeight: 600,
    color: "#ffffff",
    fontVariantNumeric: "tabular-nums",
}
const statLabelStyle: React.CSSProperties = {
    fontSize: 10,
    color: "#A8ABB2",
    textTransform: "uppercase",
    letterSpacing: "0.03em",
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
const spineStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "stretch",
    gap: 4,
}
const stageBoxStyle: React.CSSProperties = {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 6,
    background: "rgba(255,255,255,0.02)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 8,
    padding: "14px 12px",
}
const stageHeadStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "baseline",
    gap: 6,
}
const stageKrStyle: React.CSSProperties = {
    fontSize: 13,
    fontWeight: 600,
    color: "#ffffff",
}
const stageEnStyle: React.CSSProperties = {
    fontSize: 10,
    color: "#6b7280",
    fontFamily: "'SF Mono', monospace",
}
const stageNumStyle: React.CSSProperties = {
    fontSize: 34,
    fontFamily: "'Lora', serif",
    fontWeight: 600,
    lineHeight: 1.05,
    fontVariantNumeric: "tabular-nums",
}
const stageSubStyle: React.CSSProperties = {
    fontSize: 10,
    color: "#A8ABB2",
    fontFamily: "'SF Mono', monospace",
    lineHeight: 1.4,
}
const arrowStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    color: GREEN,
    fontSize: 18,
    fontWeight: 600,
    padding: "0 2px",
}
const engineBarStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "baseline",
    justifyContent: "space-between",
    gap: 12,
    marginTop: 12,
    background: "rgba(127,255,160,0.05)",
    border: "1px solid rgba(127,255,160,0.18)",
    borderRadius: 8,
    padding: "10px 14px",
}
const engineLabelStyle: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 600,
    color: GREEN,
}
const engineValStyle: React.CSSProperties = {
    fontSize: 12,
    color: "#ffffff",
    fontFamily: "'SF Mono', monospace",
    textAlign: "right",
}
const outRowStyle: React.CSSProperties = {
    display: "flex",
    gap: 12,
    marginTop: 12,
}
const sideBoxStyle: React.CSSProperties = {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 6,
    background: "rgba(255,255,255,0.02)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 8,
    padding: "12px 14px",
}
const sideNumStyle: React.CSSProperties = {
    fontSize: 24,
    fontFamily: "'Lora', serif",
    fontWeight: 600,
    lineHeight: 1.05,
    fontVariantNumeric: "tabular-nums",
}
const funnelRowStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 10,
    marginBottom: 6,
}
const funnelNumStyle: React.CSSProperties = {
    fontSize: 12,
    fontFamily: "'SF Mono', monospace",
    color: "#A8ABB2",
    fontVariantNumeric: "tabular-nums",
    width: 48,
    textAlign: "right",
}
const funnelTrackStyle: React.CSSProperties = {
    flex: 1,
    height: 14,
    background: "rgba(255,255,255,0.03)",
    borderRadius: 4,
    overflow: "hidden",
}
const funnelBarStyle: React.CSSProperties = {
    height: "100%",
    background: "linear-gradient(90deg, rgba(127,255,160,0.7), rgba(127,255,160,0.3))",
    borderRadius: 4,
}
const funnelLabelStyle: React.CSSProperties = {
    fontSize: 11,
    color: "#A8ABB2",
    width: 54,
}
const funnelStatusStyle: React.CSSProperties = {
    fontSize: 11,
    color: "#FFD600",
    marginTop: 10,
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
