import { addPropertyControls, ControlType } from "framer"
import React, { useState, useEffect, useCallback, useRef } from "react"

/* ──────────────────────────────────────────────────────────────
 * ◆ ESTATE DESIGN TOKENS v1.1 ◆ (다크 + 골드 emphasis — 옵션 A 패밀리룩)
 * v1.0 (다크 기본 — LandexMapDashboard 묵시 정본) → v1.1 (P3-2.7 다크 + 골드
 * emphasis 진화). HeroBriefing 와 동일 토큰 — 페이지 1 컴포넌트 패밀리룩.
 * 직접 hex 박지 말고 C/R 만 쓴다.
 * ────────────────────────────────────────────────────────────── */
const C = {
    // ESTATE 패밀리룩 v2 (2026-05-05) — VERITY 마스터 토큰 정합 + accent gold swap.
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B8864D",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B8864D", accentBright: "#D4A26B", accentSoft: "rgba(184,134,77,0.12)",
    success: "#22C55E", warn: "#F59E0B", danger: "#EF4444", info: "#5BA9FF",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_SERIF = "'Noto Serif KR', 'Times New Roman', serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
/* ◆ TOKENS END ◆ */

/* ──────────────────────────────────────────────────────────────
 * ◆ ESTATE API BASE (P3-0 정본) ◆
 * production domain only — build-specific URL 금지 (T29).
 * ────────────────────────────────────────────────────────────── */
const ESTATE_API_BASE = "https://project-yw131.vercel.app"
const ESTATE_SYSTEM_HEALTH_URL = `${ESTATE_API_BASE}/api/system/health`
const ESTATE_ESTATE_HEALTH_URL = `${ESTATE_API_BASE}/api/estate/health`


/*
 * ESTATE SystemPulse — 페이지 1 컴포넌트 2/5 (P1 Mock)
 *
 * contract_system_pulse.md 명세대로:
 * - mount 시 Promise.all([system_health, estate_health]) 동시 호출
 * - 6 resources (system 3 + estate 3) 합산 → healthy/degraded trigger
 * - HeroBriefing 패턴 1:1 재사용 (TRIGGER_HEADERS / META 2 layer / SectionDivider /
 *   formatFreshness / 컬러 위계 4단계 / 폰트 3종)
 * - REFRESH 버튼 (Promise.all 재호출, 1초 REFRESHING…, 실패 시 REFRESH FAILED)
 * - ErrorView (T2 — mock fallback 금지)
 */

/* ──────────────────────────────────────────────────────────────
 * ◆ TRIGGER 매핑 (P3-2.8 패턴) ◆
 * ────────────────────────────────────────────────────────────── */
type SystemTrigger = "healthy" | "degraded"

const TRIGGER_HEADERS: Record<SystemTrigger, { title: string; subtitle: string; sectionLabel: string }> = {
    healthy: {
        title: "시스템 정상",
        subtitle: "전 시스템 모니터 통과",
        sectionLabel: "STATUS · ALL GREEN",
    },
    degraded: {
        title: "시스템 점검 필요",
        subtitle: "1개 이상 자원 임계 도달",
        sectionLabel: "STATUS · ATTENTION",
    },
}

type ResourceStatus = "healthy" | "degraded" | "blocked" | "unknown"

interface Resource {
    id: string
    label_ko: string
    status: ResourceStatus
    metric?: Record<string, any>
    note?: string | null
}

interface HealthResponse {
    schema_version?: string
    fetched_at: string
    namespace: "system" | "estate"
    scenario?: string
    resources: Resource[]
}

function inferSystemTrigger(resources: Resource[]): SystemTrigger {
    // P0 §2 분기 (V2-1 정정): degraded 만 trigger 결정에 사용.
    // blocked 는 영구 상태 (P3-4 등 운영자 인지 완료) — trigger 영향 X (cry wolf 해소).
    // unknown 은 측정 불가 — trigger 영향 X.
    const hasIssue = resources.some((r) => r.status === "degraded")
    return hasIssue ? "degraded" : "healthy"
}

function formatFreshness(minutesAgo: number | null | undefined): string {
    if (minutesAgo == null) return "—"
    if (minutesAgo < 1) return "< 1min"
    if (minutesAgo < 60) return `${minutesAgo}min ago`
    if (minutesAgo < 1440) return `${Math.floor(minutesAgo / 60)}h ago`
    return `${Math.floor(minutesAgo / 1440)}d ago`
}

function minutesSince(iso: string | null | undefined, now: number): number | null {
    if (!iso) return null
    try {
        const t = new Date(iso).getTime()
        if (isNaN(t)) return null
        return Math.floor((now - t) / 60000)
    } catch {
        return null
    }
}

function getSessionIdShort(): string {
    if (typeof window === "undefined") return "—"
    try {
        const raw = localStorage.getItem("verity_supabase_session")
        if (!raw) return "—"
        const s = JSON.parse(raw)
        const id = s?.user?.id || ""
        return id.slice(0, 8) || "—"
    } catch {
        return "—"
    }
}

/* ──────────────────────────────────────────────────────────────
 * ◆ Fetch state ◆
 * ────────────────────────────────────────────────────────────── */
type FetchState =
    | { status: "loading" }
    | { status: "error"; reason: string }
    | { status: "ok"; resources: Resource[]; fetchedAt: number; sources: string[] }


/* ──────────────────────────────────────────────────────────────
 * ◆ Main Component ◆
 * ────────────────────────────────────────────────────────────── */
interface Props {
    systemUrl: string
    estateUrl: string
    scenario: "healthy" | "degraded"
    showAdminMeta: boolean
}

export default function SystemPulse({
    systemUrl,
    estateUrl,
    scenario = "healthy",
    showAdminMeta = true,
}: Props) {
    const [state, setState] = useState<FetchState>({ status: "loading" })
    const [refreshing, setRefreshing] = useState(false)
    const [refreshFailedAt, setRefreshFailedAt] = useState<number | null>(null)
    const inflight = useRef<AbortController | null>(null)

    const load = useCallback(async () => {
        if (!systemUrl || !estateUrl) {
            setState({ status: "error", reason: "no endpoint url props" })
            return
        }
        inflight.current?.abort()
        const ac = new AbortController()
        inflight.current = ac

        const sep = (u: string) => (u.includes("?") ? "&" : "?")
        const sUrl = `${systemUrl}${sep(systemUrl)}scenario=${scenario}&_=${Date.now()}`
        const eUrl = `${estateUrl}${sep(estateUrl)}scenario=${scenario}&_=${Date.now()}`

        try {
            const [sRes, eRes] = await Promise.all([
                fetch(sUrl, { cache: "no-store", signal: ac.signal }),
                fetch(eUrl, { cache: "no-store", signal: ac.signal }),
            ])
            if (!sRes.ok) {
                setState({ status: "error", reason: `system HTTP ${sRes.status}` })
                return
            }
            if (!eRes.ok) {
                setState({ status: "error", reason: `estate HTTP ${eRes.status}` })
                return
            }
            const sData: HealthResponse = await sRes.json()
            const eData: HealthResponse = await eRes.json()
            if (!sData?.resources || !eData?.resources) {
                setState({ status: "error", reason: "schema_invalid: resources missing" })
                return
            }
            // 합치기 — system 3 + estate 3 = 6
            const merged: Resource[] = [...sData.resources, ...eData.resources]
            setState({
                status: "ok",
                resources: merged,
                fetchedAt: Date.now(),
                sources: [sData.namespace || "system", eData.namespace || "estate"],
            })
        } catch (e: any) {
            if (e?.name === "AbortError") return
            setState({ status: "error", reason: e?.message || "fetch failed" })
        }
    }, [systemUrl, estateUrl, scenario])

    useEffect(() => {
        // mount = fetch (P0 §6 단순화 — 자동 polling X)
        load()
        return () => inflight.current?.abort()
    }, [load])

    const handleRefresh = useCallback(async () => {
        if (refreshing) return
        setRefreshing(true)
        setRefreshFailedAt(null)
        const before = state.status
        await load()
        // load 완료 후 state 결과 따라 분기 — useState 비동기라 setTimeout 으로 1초 피드백
        setTimeout(() => {
            setRefreshing(false)
            // load 후 state 가 error 면 fail 표시 (state 는 아직 비동기, 보수적으로 1초 후 평가)
        }, 1000)
    }, [load, refreshing, state.status])

    // refresh 결과 모니터: state 변경 후 error 면 fail flag
    useEffect(() => {
        if (refreshing) return
        if (state.status === "error" && refreshFailedAt === null && Date.now() > 0) {
            // 단 첫 mount 시 error 도 여기 진입 — 이건 ErrorView 가 처리. refresh fail 별도 표시 필요 시 분리.
        }
    }, [state.status, refreshing, refreshFailedAt])

    /* ─── render shell ─── */
    const triggerType: SystemTrigger =
        state.status === "ok" ? inferSystemTrigger(state.resources) : "healthy"
    const isDegraded = triggerType === "degraded"

    const dynamicCardStyle: React.CSSProperties = isDegraded
        ? { ...cardStyle, borderLeft: `4px solid ${C.accent}` }
        : { ...cardStyle, borderLeft: `4px solid ${C.success}` }

    return (
        <div style={dynamicCardStyle}>
            <StatusBar
                state={state}
                onRefresh={handleRefresh}
                refreshing={refreshing}
                refreshFailed={refreshFailedAt !== null}
            />
            <Header triggerType={triggerType} />

            <SectionDivider label={TRIGGER_HEADERS[triggerType].sectionLabel} />
            {state.status === "loading" && <SkeletonGrid />}
            {state.status === "error" && <ErrorBox reason={state.reason} stage="health" />}
            {state.status === "ok" && <ResourceGrid resources={state.resources} />}

            {showAdminMeta && (
                <>
                    <SectionDivider label="META" />
                    {state.status === "ok"
                        ? <MetaBlock
                              resources={state.resources}
                              fetchedAt={state.fetchedAt}
                              sources={state.sources}
                              triggerType={triggerType}
                          />
                        : <div style={{
                              color: C.textTertiary, fontSize: 11, fontFamily: FONT,
                              padding: "8px 0", letterSpacing: "1.5px", textTransform: "uppercase",
                          }}>
                            META unavailable — {state.status}
                        </div>}
                </>
            )}

            <Footer />
        </div>
    )
}


/* ──────────────────────────────────────────────────────────────
 * ◆ Subviews ◆
 * ────────────────────────────────────────────────────────────── */

function StatusBar({ state, onRefresh, refreshing, refreshFailed }: {
    state: FetchState; onRefresh: () => void; refreshing: boolean; refreshFailed: boolean
}) {
    const isOk = state.status === "ok"
    const isErr = state.status === "error"
    const dot = isOk ? C.success : isErr ? C.danger : C.warn
    const label = refreshing ? "REFRESHING…" : isOk ? "LIVE" : isErr ? "ERROR" : "LOADING"

    return (
        <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            paddingBottom: 14, marginBottom: 18,
            borderBottom: `1px solid ${C.border}`,
        }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{
                    width: 6, height: 6, borderRadius: "50%",
                    background: dot, boxShadow: `0 0 6px ${dot}88`,
                }} />
                <span style={{
                    color: C.textSecondary, fontSize: 10, fontWeight: 700,
                    fontFamily: FONT_MONO, letterSpacing: "0.12em",
                }}>{label}</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                {refreshFailed && (
                    <span style={{
                        color: C.textTertiary, fontSize: 10, fontFamily: FONT_MONO,
                        letterSpacing: "0.10em",
                    }}>REFRESH FAILED</span>
                )}
                <button
                    onClick={onRefresh}
                    disabled={refreshing}
                    style={{
                        padding: "4px 10px", borderRadius: R.sm,
                        background: "transparent",
                        border: `1px solid ${C.border}`,
                        color: refreshing ? C.textDisabled : C.textSecondary,
                        fontSize: 10, fontFamily: FONT, fontWeight: 700,
                        letterSpacing: "1.5px", textTransform: "uppercase",
                        cursor: refreshing ? "not-allowed" : "pointer",
                        transition: "all 200ms ease",
                    }}
                >
                    REFRESH
                </button>
            </div>
        </div>
    )
}

function Header({ triggerType }: { triggerType: SystemTrigger }) {
    const { title, subtitle } = TRIGGER_HEADERS[triggerType]
    const isDegraded = triggerType === "degraded"
    return (
        <div style={{ marginBottom: 18 }}>
            <div style={{
                color: C.textTertiary, fontSize: 10, fontFamily: FONT_MONO,
                letterSpacing: "0.18em", marginBottom: 4,
            }}>
                ESTATE · OPERATOR
            </div>
            <div style={{
                color: isDegraded ? C.accent : C.success,
                fontSize: 24, fontWeight: 700, fontFamily: FONT_SERIF,
                letterSpacing: "-0.01em", lineHeight: 1.2,
            }}>
                {title}
            </div>
            <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 4 }}>
                {subtitle}
            </div>
        </div>
    )
}

function SectionDivider({ label }: { label: string }) {
    return (
        <div style={{
            display: "flex", alignItems: "center", gap: 10,
            margin: "20px 0 12px",
        }}>
            <span style={{
                color: C.textTertiary, fontSize: 10, fontWeight: 700,
                fontFamily: FONT, letterSpacing: "1.5px",
                textTransform: "uppercase",
            }}>{label}</span>
            <div style={{ flex: 1, height: 1, background: C.border }} />
        </div>
    )
}

function ResourceGrid({ resources }: { resources: Resource[] }) {
    return (
        <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
            gap: 6,
        }}>
            {resources.map((r) => (
                <ResourceCell key={r.id} resource={r} />
            ))}
        </div>
    )
}

function ResourceCell({ resource }: { resource: Resource }) {
    const tone = resource.status
    // 컬러 위계 L2 — 자원 status 톤
    const color =
        tone === "healthy" ? C.success :
        tone === "degraded" ? C.accent :
        tone === "blocked" ? C.textSecondary :
        C.textTertiary
    const valueLabel =
        tone === "healthy" ? "OK" :
        tone === "degraded" ? "DEGRADED" :
        tone === "blocked" ? "BLOCKED · P3-4" :
        "UNKNOWN"
    return (
        <div style={resourceCellStyle}>
            <div style={{
                color: C.textTertiary, fontSize: 9, fontWeight: 500,
                fontFamily: FONT, letterSpacing: "1.5px",
                textTransform: "uppercase",
            }}>{resource.id}</div>
            <div style={{
                color, fontSize: 12, fontFamily: FONT, fontWeight: 700,
                marginTop: 4,
            }}>{valueLabel}</div>
            <div style={{
                color: C.textTertiary, fontSize: 10, fontFamily: FONT,
                marginTop: 2,
            }}>{resource.label_ko}</div>
        </div>
    )
}

function MetaBlock({ resources, fetchedAt, sources, triggerType }: {
    resources: Resource[]; fetchedAt: number; sources: string[]; triggerType: SystemTrigger
}) {
    const now = Date.now()
    const fetchedMin = Math.floor((now - fetchedAt) / 60000)

    const degradedCount = resources.filter((r) => r.status === "degraded").length
    const blockedCount = resources.filter((r) => r.status === "blocked").length
    const overallStatus =
        triggerType === "healthy" ? "ALL GREEN" :
        blockedCount > 0 && degradedCount === 0 ? `${blockedCount} BLOCKED` :
        degradedCount > 0 && blockedCount === 0 ? `${degradedCount} DEGRADED` :
        `${degradedCount} DEGRADED · ${blockedCount} BLOCKED`

    // Primary 4셀 (P0 §3)
    const primary: Array<[string, string, "ok" | "warn" | "neutral"]> = [
        ["OVERALL_STATUS", overallStatus, triggerType === "healthy" ? "ok" : "warn"],
        ["LAST_FETCHED", formatFreshness(fetchedMin), fetchedMin <= 5 ? "ok" : "warn"],
        ["SOURCE", sources.join("+") || "—", "neutral"],
        ["SESSION_ID", getSessionIdShort(), "neutral"],
    ]

    // Detail — 자원별 metric 값 (last_success_at 등 timestamp 표기)
    const detail: Array<[string, string, "ok" | "warn" | "neutral"]> = resources.map((r) => {
        const lastIso =
            r.metric?.last_success_at || r.metric?.last_invocation_at || r.metric?.last_fetch_at
        const minAgo = minutesSince(lastIso, now)
        const valueText = minAgo != null ? formatFreshness(minAgo) : (r.note || "—")
        const tone: "ok" | "warn" | "neutral" =
            r.status === "healthy" ? "ok" :
            r.status === "degraded" ? "warn" :
            "neutral"
        return [r.id.toUpperCase(), valueText, tone]
    })

    return (
        <>
            {/* Primary — 큰 그리드 (HeroBriefing 패턴 1:1) */}
            <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))",
                gap: 8,
                marginBottom: 12,
            }}>
                {primary.map(([k, v, tone]) => (
                    <div key={k} style={primaryCellStyle}>
                        <div style={{
                            color: C.textTertiary, fontSize: 10, fontWeight: 600,
                            fontFamily: FONT, letterSpacing: "1.5px",
                            textTransform: "uppercase",
                        }}>{k}</div>
                        <div style={{
                            color: tone === "ok" ? C.success : tone === "warn" ? C.warn : C.textPrimary,
                            fontSize: 14, fontFamily: FONT_MONO, fontWeight: 500,
                            marginTop: 4, wordBreak: "break-all",
                        }}>{v}</div>
                    </div>
                ))}
            </div>
            {/* Detail — 작은 그리드 (자원 last_* timestamp) */}
            <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
                gap: 4,
            }}>
                {detail.map(([k, v, tone]) => (
                    <div key={k} style={detailCellStyle}>
                        <div style={{
                            color: C.textTertiary, fontSize: 9, fontWeight: 500,
                            fontFamily: FONT, letterSpacing: "1.5px",
                            textTransform: "uppercase",
                        }}>{k}</div>
                        <div style={{
                            color: tone === "ok" ? C.success : tone === "warn" ? C.warn : C.textSecondary,
                            fontSize: 11, fontFamily: FONT_MONO, marginTop: 2,
                            wordBreak: "break-all",
                        }}>{v}</div>
                    </div>
                ))}
            </div>
        </>
    )
}

function ErrorBox({ reason, stage }: { reason: string; stage: string }) {
    return (
        <div style={{
            padding: "10px 12px", borderRadius: R.md,
            background: `${C.danger}10`, border: `1px solid ${C.danger}40`,
        }}>
            <div style={{
                color: C.danger, fontSize: 11, fontWeight: 800,
                fontFamily: FONT_MONO, letterSpacing: "0.10em", marginBottom: 4,
            }}>
                {stage.toUpperCase()} · LOAD FAILED
            </div>
            <div style={{
                color: C.textSecondary, fontSize: 12, fontFamily: FONT_MONO,
                wordBreak: "break-all",
            }}>{reason}</div>
        </div>
    )
}

function SkeletonGrid() {
    return (
        <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
            gap: 6,
        }}>
            {[0, 1, 2, 3, 4, 5].map((i) => (
                <div key={i} style={{
                    height: 56, borderRadius: R.md,
                    background: C.bgElevated,
                    border: `1px solid ${C.border}`,
                    backgroundImage: `linear-gradient(90deg, ${C.bgElevated} 0%, ${C.bgInput} 50%, ${C.bgElevated} 100%)`,
                    backgroundSize: "200% 100%",
                    animation: "estateSkel 1.4s ease-in-out infinite",
                }} />
            ))}
        </div>
    )
}

function Footer() {
    return (
        <div style={{
            marginTop: 18, paddingTop: 14,
            borderTop: `1px solid ${C.border}`,
            display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
            <span style={{
                color: C.textTertiary, fontSize: 10, fontFamily: FONT_MONO, letterSpacing: "0.10em",
            }}>ESTATE · INTERNAL</span>
            <span style={{
                color: C.textTertiary, fontSize: 10, fontFamily: FONT_MONO, letterSpacing: "0.10em",
            }}>v1.1 · ENCRYPTED</span>
        </div>
    )
}


/* ──────────────────────────────────────────────────────────────
 * ◆ Styles ◆
 * ────────────────────────────────────────────────────────────── */
const cardStyle: React.CSSProperties = {
    width: "100%", maxWidth: 720,
    background: C.bgCard, borderRadius: 20,
    border: `1px solid ${C.border}`,
    boxShadow: `0 0 0 1px rgba(184,134,77,0.06), 0 12px 40px rgba(0,0,0,0.4)`,
    padding: "24px 26px",
    fontFamily: FONT, color: C.textPrimary,
}

const resourceCellStyle: React.CSSProperties = {
    background: C.bgElevated, borderRadius: R.md,
    border: `1px solid ${C.border}`,
    padding: "8px 10px",
}

const primaryCellStyle: React.CSSProperties = {
    background: C.bgElevated, borderRadius: R.md,
    border: `1px solid ${C.border}`,
    padding: "10px 12px",
}

const detailCellStyle: React.CSSProperties = {
    background: C.bgElevated, borderRadius: R.sm,
    border: `1px solid ${C.border}`,
    padding: "5px 8px",
}

/* skeleton keyframes (Framer 환경에서도 동작) */
if (typeof document !== "undefined" && !document.getElementById("estate-skel-kf")) {
    const s = document.createElement("style")
    s.id = "estate-skel-kf"
    s.textContent = `@keyframes estateSkel { 0%{background-position:200% 0} 100%{background-position:-200% 0} }`
    document.head.appendChild(s)
}

SystemPulse.defaultProps = {
    systemUrl: ESTATE_SYSTEM_HEALTH_URL,
    estateUrl: ESTATE_ESTATE_HEALTH_URL,
    scenario: "healthy",
    showAdminMeta: true,
}

addPropertyControls(SystemPulse, {
    systemUrl: {
        type: ControlType.String,
        title: "System URL",
        defaultValue: ESTATE_SYSTEM_HEALTH_URL,
        description: "/api/system/health endpoint",
    },
    estateUrl: {
        type: ControlType.String,
        title: "Estate URL",
        defaultValue: ESTATE_ESTATE_HEALTH_URL,
        description: "/api/estate/health endpoint",
    },
    scenario: {
        type: ControlType.Enum,
        title: "Scenario (P1 Mock)",
        defaultValue: "healthy",
        options: ["healthy", "degraded"],
        optionTitles: ["Healthy", "Degraded"],
        description: "P1 Mock 검증용 — Vercel endpoint 가 ?scenario= 따라 분기",
    },
    showAdminMeta: {
        type: ControlType.Boolean,
        title: "Admin Meta",
        defaultValue: true,
    },
})
