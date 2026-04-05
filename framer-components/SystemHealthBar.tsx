import React, { useEffect, useState, useCallback } from "react"
import { addPropertyControls, ControlType } from "framer"

interface Props {
    dataUrl: string
    refreshInterval: number
}

type ApiStatus = "ok" | "error" | "unknown"
type OverallStatus = "ok" | "warning" | "error" | "unknown" | "loading"

interface ApiInfo {
    status: ApiStatus
    latency_ms?: number
    detail?: string
}

interface HealthData {
    status: OverallStatus
    checked_at?: string
    version?: string
    elapsed_ms?: number
    api_health?: Record<string, ApiInfo>
    github_worker?: {
        status: string
        conclusion?: string
        workflow?: string
        started_at?: string
        url?: string
        detail?: string
    }
    data_recency?: {
        status: string
        updated_at?: string
        files?: Record<string, { status: string; last_updated?: string; age_hours?: number }>
    }
    version_sync?: {
        local_version?: string
        local_sha?: string
        remote_sha?: string
        remote_message?: string
        status?: string
    }
    errors?: string[]
    warnings?: string[]
}

const API_LABELS: Record<string, string> = {
    dart: "DART",
    fred: "FRED",
    telegram: "Telegram",
    gemini: "Gemini",
    anthropic: "Claude",
    kipris: "KIPRIS",
    public_data: "관세청",
}

const STATUS_CONFIG: Record<string, { color: string; bg: string; label: string; icon: string }> = {
    ok: { color: "#B5FF19", bg: "rgba(181,255,25,0.06)", label: "ALL SYSTEMS OPERATIONAL", icon: "●" },
    warning: { color: "#EAB308", bg: "rgba(234,179,8,0.08)", label: "경고 감지", icon: "▲" },
    error: { color: "#EF4444", bg: "rgba(239,68,68,0.10)", label: "시스템 오류", icon: "■" },
    unknown: { color: "#666", bg: "rgba(102,102,102,0.06)", label: "진단 중...", icon: "○" },
    loading: { color: "#444", bg: "rgba(68,68,68,0.04)", label: "로딩...", icon: "○" },
}

function timeSince(dateStr: string): string {
    if (!dateStr) return "—"
    const diff = Date.now() - new Date(dateStr).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return "방금 전"
    if (mins < 60) return `${mins}분 전`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours}시간 전`
    const days = Math.floor(hours / 24)
    return `${days}일 전`
}

function ApiDot({ name, info }: { name: string; info: ApiInfo }) {
    const color = info.status === "ok" ? "#B5FF19" : info.status === "error" ? "#EF4444" : "#555"
    const pulse = info.status === "error"
    return (
        <div style={{ display: "flex", alignItems: "center", gap: 5 }} title={info.detail || ""}>
            <span style={{
                display: "inline-block",
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: color,
                boxShadow: pulse ? `0 0 6px ${color}` : "none",
                animation: pulse ? "pulse 1.5s infinite" : "none",
                flexShrink: 0,
            }} />
            <span style={{ color: info.status === "ok" ? "#888" : color, fontSize: 10, fontWeight: 600 }}>
                {API_LABELS[name] || name}
            </span>
            {info.latency_ms != null && info.latency_ms > 0 && (
                <span style={{ color: "#333", fontSize: 9 }}>{info.latency_ms}ms</span>
            )}
        </div>
    )
}

export default function SystemHealthBar(props: Props) {
    const { dataUrl, refreshInterval } = props
    const [health, setHealth] = useState<HealthData | null>(null)
    const [expanded, setExpanded] = useState(false)
    const [dismissed, setDismissed] = useState(false)

    const fetchHealth = useCallback(() => {
        if (!dataUrl) return
        fetch(dataUrl)
            .then((r) => r.text())
            .then((txt) => {
                const data = JSON.parse(txt.replace(/\bNaN\b/g, "null"))
                if (data?.system_health) {
                    setHealth(data.system_health)
                    return
                }
                const updatedAt = data?.updated_at
                const warnings: string[] = []
                let overall: OverallStatus = "ok"
                if (updatedAt) {
                    const ageH = (Date.now() - new Date(updatedAt).getTime()) / 3600000
                    if (ageH > 24) {
                        warnings.push(`데이터 ${Math.floor(ageH)}시간 경과 (24h 초과)`)
                        overall = "warning"
                    }
                }
                setHealth({
                    status: overall,
                    checked_at: new Date().toISOString(),
                    version: "—",
                    data_recency: { status: overall === "ok" ? "fresh" : "stale", updated_at: updatedAt },
                    errors: [],
                    warnings,
                })
            })
            .catch(() => setHealth({ status: "unknown", errors: ["데이터 로드 실패"] }))
    }, [dataUrl])

    const overall = health?.status || "unknown"
    const isAlertMode = overall === "error" || overall === "warning"

    useEffect(() => {
        fetchHealth()
        if (refreshInterval > 0) {
            const id = setInterval(fetchHealth, refreshInterval * 1000)
            return () => clearInterval(id)
        }
    }, [fetchHealth, refreshInterval])

    useEffect(() => {
        if (dismissed && isAlertMode) setDismissed(false)
    }, [isAlertMode])

    if (!health) {
        return (
            <div style={wrapper}>
                <style>{`
                    @keyframes pulse {
                        0%, 100% { opacity: 1; }
                        50% { opacity: 0.4; }
                    }
                `}</style>
                <div style={{ ...bar, background: "#0A0A0A", borderBottom: "1px solid #111" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{
                            width: 8, height: 8, borderRadius: "50%",
                            background: "#333", animation: "pulse 1.5s infinite",
                        }} />
                        <span style={{ color: "#444", fontSize: 10, fontWeight: 600, letterSpacing: "0.05em" }}>
                            SYSTEM
                        </span>
                    </div>
                    <span style={{ color: "#333", fontSize: 10, fontWeight: 500 }}>연결 중...</span>
                </div>
            </div>
        )
    }

    const cfg = STATUS_CONFIG[overall] || STATUS_CONFIG.unknown
    const hasIssues = (health.errors?.length || 0) + (health.warnings?.length || 0) > 0

    if (dismissed && !isAlertMode) {
        return null
    }

    const hasApiData = health.api_health && Object.keys(health.api_health).length > 0

    const workerIcon =
        health.github_worker?.status === "ok" ? "🟢" :
        health.github_worker?.status === "running" ? "⏳" :
        health.github_worker?.status === "error" ? "🔴" : "⚪"

    const dataAge = health.data_recency?.updated_at
        ? timeSince(health.data_recency.updated_at)
        : "—"

    const versionBadge = health.version_sync?.status === "update_available"

    return (
        <div style={wrapper}>
            <style>{`
                @keyframes pulse {
                    0%, 100% { opacity: 1; }
                    50% { opacity: 0.4; }
                }
                @keyframes slideDown {
                    from { max-height: 0; opacity: 0; }
                    to { max-height: 400px; opacity: 1; }
                }
            `}</style>

            {/* 경고 바 — 에러/경고 시 표시 */}
            {isAlertMode && !dismissed && (
                <div style={{
                    ...alertBar,
                    background: overall === "error"
                        ? "linear-gradient(90deg, rgba(239,68,68,0.15), rgba(239,68,68,0.05))"
                        : "linear-gradient(90deg, rgba(234,179,8,0.12), rgba(234,179,8,0.04))",
                    borderBottom: `1px solid ${cfg.color}33`,
                }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1 }}>
                        <span style={{ color: cfg.color, fontSize: 12, fontWeight: 800, animation: "pulse 2s infinite" }}>
                            {cfg.icon}
                        </span>
                        <span style={{ color: cfg.color, fontSize: 11, fontWeight: 700 }}>
                            {health.errors?.[0] || health.warnings?.[0] || cfg.label}
                        </span>
                        {(health.errors?.length || 0) + (health.warnings?.length || 0) > 1 && (
                            <span style={{
                                color: cfg.color,
                                fontSize: 9,
                                fontWeight: 600,
                                background: `${cfg.color}15`,
                                padding: "2px 6px",
                                borderRadius: 4,
                            }}>
                                +{(health.errors?.length || 0) + (health.warnings?.length || 0) - 1}건
                            </span>
                        )}
                    </div>
                    <button
                        onClick={() => setDismissed(true)}
                        style={dismissBtn}
                        title="경고 닫기"
                    >
                        ✕
                    </button>
                </div>
            )}

            {/* 메인 상태 바 */}
            <div
                style={{ ...bar, background: expanded ? "#0A0A0A" : "#000", cursor: "pointer" }}
                onClick={() => setExpanded(!expanded)}
            >
                {/* 상태 표시등 */}
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div style={{
                        width: 8,
                        height: 8,
                        borderRadius: "50%",
                        background: cfg.color,
                        boxShadow: `0 0 8px ${cfg.color}60`,
                        animation: isAlertMode ? "pulse 1.5s infinite" : "none",
                    }} />
                    <span style={{ color: cfg.color, fontSize: 10, fontWeight: 700, letterSpacing: "0.05em" }}>
                        SYSTEM
                    </span>
                </div>

                {/* 상태 정보 */}
                <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, justifyContent: "center" }}>
                    {hasApiData ? (
                        <>
                            {(Object.entries(health.api_health!) as [string, ApiInfo][]).map(([k, info]) => (
                                <ApiDot key={k} name={k} info={info} />
                            ))}
                            <span style={divider} />
                            <span style={{ color: "#555", fontSize: 10, fontWeight: 600 }} title="GitHub Actions">
                                {workerIcon} Worker
                            </span>
                        </>
                    ) : (
                        <span style={{ color: "#444", fontSize: 10, fontWeight: 500 }}>
                            {cfg.label}
                        </span>
                    )}

                    <span style={divider} />

                    <span style={{ color: "#555", fontSize: 10, fontWeight: 600 }} title="데이터 갱신 시각">
                        🕒 {dataAge}
                    </span>

                    {versionBadge && (
                        <>
                            <span style={divider} />
                            <span style={{
                                color: "#B5FF19",
                                fontSize: 9,
                                fontWeight: 700,
                                background: "rgba(181,255,25,0.1)",
                                padding: "2px 6px",
                                borderRadius: 4,
                            }}>
                                🔄 업데이트
                            </span>
                        </>
                    )}
                </div>

                {/* 버전 + 토글 */}
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ color: "#333", fontSize: 9, fontWeight: 500 }}>
                        {health.version || "—"}
                    </span>
                    <span style={{
                        color: "#444",
                        fontSize: 10,
                        transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
                        transition: "transform 0.2s",
                    }}>
                        ▾
                    </span>
                </div>
            </div>

            {/* 확장 패널 */}
            {expanded && (
                <div style={panel}>
                    {/* API Health 상세 */}
                    {hasApiData && (
                        <div style={section}>
                            <span style={sectionTitle}>API HEARTBEAT</span>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                                {(Object.entries(health.api_health!) as [string, ApiInfo][]).map(([key, info]) => {
                                    const color = info.status === "ok" ? "#B5FF19" : "#EF4444"
                                    return (
                                        <div key={key} style={{
                                            ...card,
                                            borderColor: info.status === "error" ? "#EF444433" : "#1A1A1A",
                                        }}>
                                            <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 4 }}>
                                                <span style={{
                                                    width: 6, height: 6, borderRadius: "50%",
                                                    background: color, display: "inline-block",
                                                }} />
                                                <span style={{ color: "#aaa", fontSize: 10, fontWeight: 700 }}>
                                                    {API_LABELS[key] || key}
                                                </span>
                                            </div>
                                            <span style={{ color: "#555", fontSize: 9 }}>
                                                {info.detail || info.status}
                                            </span>
                                            {info.latency_ms != null && info.latency_ms > 0 && (
                                                <span style={{ color: "#333", fontSize: 8, marginTop: 2, display: "block" }}>
                                                    {info.latency_ms}ms
                                                </span>
                                            )}
                                        </div>
                                    )
                                })}
                            </div>
                        </div>
                    )}

                    {!hasApiData && (
                        <div style={section}>
                            <span style={sectionTitle}>SYSTEM HEALTH</span>
                            <div style={{ ...card, borderColor: "#1A1A1A" }}>
                                <span style={{ color: "#555", fontSize: 10 }}>
                                    상세 진단 데이터는 다음 분석 실행 후 표시됩니다.
                                </span>
                                <span style={{ color: "#333", fontSize: 9, marginTop: 4, display: "block" }}>
                                    GitHub Actions가 main.py를 실행하면 API별 상태, Worker 결과, 버전 정보가 자동으로 수집됩니다.
                                </span>
                            </div>
                        </div>
                    )}

                    {/* GitHub Worker */}
                    {health.github_worker && (
                        <div style={section}>
                            <span style={sectionTitle}>GITHUB WORKER</span>
                            <div style={{ ...card, borderColor: "#1A1A1A", maxWidth: 350 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                                    <span>{workerIcon}</span>
                                    <span style={{ color: "#aaa", fontSize: 10, fontWeight: 700 }}>
                                        {health.github_worker.workflow || "—"}
                                    </span>
                                </div>
                                <span style={{ color: "#555", fontSize: 9 }}>
                                    {health.github_worker.conclusion || "unknown"}
                                    {health.github_worker.started_at && (
                                        <> · {timeSince(health.github_worker.started_at)}</>
                                    )}
                                </span>
                                {health.github_worker.url && (
                                    <a
                                        href={health.github_worker.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        style={{ color: "#B5FF19", fontSize: 9, marginTop: 4, display: "block", textDecoration: "none" }}
                                    >
                                        GitHub에서 보기 →
                                    </a>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Data Recency */}
                    <div style={section}>
                        <span style={sectionTitle}>DATA FRESHNESS</span>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                            {health.data_recency?.files && (Object.entries(health.data_recency.files) as [string, { status: string; last_updated?: string; age_hours?: number }][]).map(([fname, info]) => {
                                const isStale = info.status === "stale"
                                const isMissing = info.status === "missing"
                                const dotColor = isMissing ? "#EF4444" : isStale ? "#EAB308" : "#B5FF19"
                                return (
                                    <div key={fname} style={{ ...card, borderColor: isStale ? "#EAB30833" : "#1A1A1A" }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 4 }}>
                                            <span style={{
                                                width: 6, height: 6, borderRadius: "50%",
                                                background: dotColor, display: "inline-block",
                                            }} />
                                            <span style={{ color: "#aaa", fontSize: 10, fontWeight: 700 }}>
                                                {fname}
                                            </span>
                                        </div>
                                        <span style={{ color: "#555", fontSize: 9 }}>
                                            {isMissing
                                                ? "파일 없음"
                                                : `${info.last_updated || "?"} (${info.age_hours?.toFixed(1) || "?"}h)`}
                                        </span>
                                    </div>
                                )
                            })}
                        </div>
                    </div>

                    {/* Version */}
                    <div style={section}>
                        <span style={sectionTitle}>VERSION</span>
                        <div style={{ ...card, borderColor: versionBadge ? "#B5FF1933" : "#1A1A1A", maxWidth: 400 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                <span style={{ color: "#aaa", fontSize: 11, fontWeight: 800 }}>
                                    {health.version_sync?.local_version || health.version || "—"}
                                </span>
                                <span style={{ color: "#333", fontSize: 9 }}>
                                    ({health.version_sync?.local_sha || "?"})
                                </span>
                                {versionBadge && (
                                    <span style={{
                                        color: "#B5FF19",
                                        fontSize: 9,
                                        fontWeight: 700,
                                        background: "rgba(181,255,25,0.1)",
                                        padding: "2px 8px",
                                        borderRadius: 4,
                                    }}>
                                        새 업데이트 감지
                                    </span>
                                )}
                            </div>
                            {health.version_sync?.remote_message && versionBadge && (
                                <span style={{ color: "#555", fontSize: 9, marginTop: 4, display: "block" }}>
                                    최신: {health.version_sync.remote_message}
                                </span>
                            )}
                        </div>
                    </div>

                    {/* 에러/경고 상세 */}
                    {hasIssues && (
                        <div style={section}>
                            <span style={sectionTitle}>ISSUES</span>
                            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                                {health.errors?.map((e, i) => (
                                    <div key={`e${i}`} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                        <span style={{ color: "#EF4444", fontSize: 10 }}>■</span>
                                        <span style={{ color: "#EF4444", fontSize: 10, fontWeight: 600 }}>{e}</span>
                                    </div>
                                ))}
                                {health.warnings?.map((w, i) => (
                                    <div key={`w${i}`} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                        <span style={{ color: "#EAB308", fontSize: 10 }}>▲</span>
                                        <span style={{ color: "#EAB308", fontSize: 10, fontWeight: 600 }}>{w}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* 진단 시각 */}
                    <div style={{ textAlign: "center", paddingTop: 8 }}>
                        <span style={{ color: "#222", fontSize: 9 }}>
                            진단 시각: {health.checked_at ? new Date(health.checked_at).toLocaleString("ko-KR") : "—"}
                            {health.elapsed_ms ? ` (${health.elapsed_ms}ms)` : ""}
                        </span>
                    </div>
                </div>
            )}
        </div>
    )
}

SystemHealthBar.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    refreshInterval: 300,
}

addPropertyControls(SystemHealthBar, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    },
    refreshInterval: {
        type: ControlType.Number,
        title: "새로고침(초)",
        defaultValue: 300,
        min: 30,
        max: 3600,
        step: 30,
    },
})

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"

const wrapper: React.CSSProperties = {
    width: "100%",
    fontFamily: font,
    position: "relative",
    zIndex: 100,
}

const alertBar: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    padding: "6px 24px",
    gap: 8,
}

const dismissBtn: React.CSSProperties = {
    background: "none",
    border: "none",
    color: "#555",
    fontSize: 12,
    cursor: "pointer",
    padding: "2px 6px",
    borderRadius: 4,
    lineHeight: 1,
}

const bar: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 16,
    padding: "6px 24px",
    borderBottom: "1px solid #111",
    transition: "background 0.2s",
}

const divider: React.CSSProperties = {
    width: 1,
    height: 14,
    background: "#1A1A1A",
    flexShrink: 0,
}

const panel: React.CSSProperties = {
    background: "#0A0A0A",
    borderBottom: "1px solid #1A1A1A",
    padding: "16px 24px",
    animation: "slideDown 0.3s ease",
    overflow: "hidden",
}

const section: React.CSSProperties = {
    marginBottom: 14,
}

const sectionTitle: React.CSSProperties = {
    display: "block",
    color: "#333",
    fontSize: 9,
    fontWeight: 800,
    letterSpacing: "0.1em",
    marginBottom: 8,
}

const card: React.CSSProperties = {
    background: "#111",
    border: "1px solid",
    borderRadius: 8,
    padding: "8px 12px",
    minWidth: 120,
}
