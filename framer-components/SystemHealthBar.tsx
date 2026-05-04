/**
 * ⚠️ DEPRECATED (2026-05-05 Plan v0.1 §3 [Admin/System] 폐기 결정)
 *
 * AdminDashboard 흡수 (CardSystemHealth removed Step 9 commit) — 1인 사용자 노출 X, admin 운영 영역
 *
 * Framer 페이지에서 인스턴스 제거. 추후 일괄 cleanup commit 시 git rm.
 *
 * ────────────────────────────────────────────────────────────
 */
import React, { useEffect, useState } from "react"
import { addPropertyControls, ControlType } from "framer"

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆ (Neo Dark Terminal — _shared-patterns.ts 마스터)
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    strongBuy: "#22C55E", buy: "#B5FF19", watch: "#FFD600", caution: "#F59E0B", avoid: "#EF4444",
    up: "#F04452", down: "#3182F6",
    info: "#5BA9FF", success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const G = {
    accent: "0 0 8px rgba(181,255,25,0.35)",
    accentSoft: "0 0 4px rgba(181,255,25,0.20)",
    accentStrong: "0 0 12px rgba(181,255,25,0.50)",
    danger: "0 0 6px rgba(239,68,68,0.30)",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_tight: 1.3, lh_normal: 1.5, lh_loose: 1.7,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease", slow: "240ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */

/** Framer 단일 파일용 fetch (fetchPortfolioJson.ts와 동일 로직) */
function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    const u = (url || "").trim()
    const sep = u.includes("?") ? "&" : "?"
    return fetch(`${u}${sep}_=${Date.now()}`, { cache: "no-store", mode: "cors", credentials: "omit", signal })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((txt) => JSON.parse(txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
}

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
    krx_open_api: "KRX",
    perplexity: "Perplexity",
    kis: "KIS",
    finnhub: "Finnhub",
    polygon: "Polygon",
    newsapi: "NewsAPI",
    sec_edgar: "SEC",
    ecos: "ECOS",
    cftc_cot: "CFTC",
    cboe_pcr: "CBOE",
    fund_flows: "Fund Flows",
    supabase: "Supabase",
    naver_news: "네이버뉴스",
    google_news: "구글뉴스",
}

// API 장애 → 영향 받는 컴포넌트/기능 매핑. status != ok 시 inline 표시.
// 사용자가 빈 컴포넌트 보고 "왜?" 물을 때 SystemHealthBar 한 번 보면 원인 파악.
const API_IMPACT: Record<string, string> = {
    dart: "StockDetailPanel · 종목 상세 (사업보고서·공시)",
    fred: "MacroPanel · 미국 매크로 (10Y·VIX·HY)",
    telegram: "자동 알림 수신 불가",
    gemini: "Gemini 종목 분석 · VerityReport",
    anthropic: "Claude 심층 분석 · dual_consensus",
    kipris: "NicheIntelPanel 특허 시그널",
    public_data: "수출입 신호 · CapitalFlowRadar",
    krx_open_api: "KRXHeatmap · 국내 섹터 데이터",
    perplexity: "분기 리서치 · 실시간 이벤트 요약",
    kis: "실시간 가격 · 주문 · TradingPanel",
    finnhub: "US 뉴스 · 실적 캘린더",
    polygon: "US 가격 · USMag7Tracker",
    newsapi: "뉴스 감성 · NewsHeadline",
    sec_edgar: "13F · 인사이더 · USInsiderFeed",
    ecos: "한국은행 금리 · 경제지표",
    cftc_cot: "MacroSentimentPanel COT 포지셔닝",
    cboe_pcr: "MacroSentimentPanel PCR · 패닉 감지",
    fund_flows: "MacroSentimentPanel ETF 자금 플로우",
    supabase: "LiveVisitors · AuthPage",
    naver_news: "국내 뉴스 · 센티먼트",
    google_news: "뉴스 보조 수집",
}

const STATUS_CONFIG: Record<string, { color: string; bg: string; label: string; icon: string }> = {
    ok: { color: C.accent, bg: "rgba(181,255,25,0.06)", label: "ALL SYSTEMS OPERATIONAL", icon: "●" },
    warning: { color: C.warn, bg: "rgba(234,179,8,0.08)", label: "경고 감지", icon: "+" },
    error: { color: C.danger, bg: "rgba(239,68,68,0.10)", label: "시스템 오류", icon: "■" },
    unknown: { color: C.textTertiary, bg: "rgba(102,102,102,0.06)", label: "진단 중...", icon: "○" },
    loading: { color: C.textTertiary, bg: "rgba(68,68,68,0.04)", label: "로딩...", icon: "○" },
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
    const color = info.status === "ok" ? C.accent : info.status === "error" ? C.danger : C.textTertiary
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
            <span style={{ color: info.status === "ok" ? C.textTertiary : color, fontSize: 10, fontWeight: 600 }}>
                {API_LABELS[name] || name}
            </span>
            {info.latency_ms != null && info.latency_ms > 0 && (
                <span style={{ color: C.textDisabled, fontSize: 9 }}>{info.latency_ms}ms</span>
            )}
        </div>
    )
}

export default function SystemHealthBar(props: Props) {
    const { dataUrl, refreshInterval } = props
    const [health, setHealth] = useState<HealthData | null>(null)
    const [expanded, setExpanded] = useState(false)
    const [dismissed, setDismissed] = useState(false)

    const overall = health?.status || "unknown"
    const isAlertMode = overall === "error" || overall === "warning"

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        const doFetch = () => {
            fetchPortfolioJson(dataUrl, ac.signal)
                .then((data) => {
                    if (ac.signal.aborted) return
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
                .catch(() => { if (!ac.signal.aborted) setHealth({ status: "unknown", errors: ["데이터 로드 실패"] }) })
        }
        doFetch()
        const id = refreshInterval > 0 ? setInterval(doFetch, refreshInterval * 1000) : undefined
        return () => { ac.abort(); if (id) clearInterval(id) }
    }, [dataUrl, refreshInterval])

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
                <div style={{ ...bar, background: C.bgPage, borderBottom: "1px solid #111" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{
                            width: 8, height: 8, borderRadius: "50%",
                            background: C.borderStrong, animation: "pulse 1.5s infinite",
                        }} />
                        <span style={{ color: C.textTertiary, fontSize: 10, fontWeight: 600, letterSpacing: "0.05em" }}>
                            SYSTEM
                        </span>
                    </div>
                    <span style={{ color: C.textDisabled, fontSize: 10, fontWeight: 500 }}>연결 중...</span>
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
        health.github_worker?.status === "ok" ? "" :
        health.github_worker?.status === "running" ? "⏳" :
        health.github_worker?.status === "error" ? "" : ""

    const recencyUpdatedAt = health.data_recency?.updated_at
    const dataAge = recencyUpdatedAt ? timeSince(recencyUpdatedAt) : "—"
    const dataAbsTime = recencyUpdatedAt
        ? new Date(recencyUpdatedAt).toLocaleString("ko-KR", {
              month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
          })
        : ""
    const recencyAgeH = recencyUpdatedAt
        ? (Date.now() - new Date(recencyUpdatedAt).getTime()) / 3600000
        : 0
    const isDataStale = recencyAgeH > 24

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
                        <span style={{ color: cfg.color, fontSize: T.cap, fontWeight: 800, animation: "pulse 2s infinite" }}>
                            {cfg.icon}
                        </span>
                        <span style={{ color: cfg.color, fontSize: T.cap, fontWeight: 700 }}>
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
                        ×
                    </button>
                </div>
            )}

            {/* 메인 상태 바 */}
            <div
                style={{ ...bar, background: expanded ? C.bgPage : C.bgPage, cursor: "pointer" }}
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
                            <span style={{ color: C.textTertiary, fontSize: 10, fontWeight: 600 }} title="GitHub Actions">
                                {workerIcon} Worker
                            </span>
                        </>
                    ) : (
                        <span style={{ color: C.textTertiary, fontSize: 10, fontWeight: 500 }}>
                            {cfg.label}
                        </span>
                    )}

                    <span style={divider} />

                    <span style={{
                        color: isDataStale ? C.danger : C.textTertiary,
                        fontSize: 10,
                        fontWeight: 600,
                        display: "flex",
                        alignItems: "center",
                        gap: 4,
                    }} title={`데이터 갱신: ${dataAbsTime}`}>
                        🕒 {dataAbsTime ? `${dataAbsTime} (${dataAge})` : dataAge}
                    </span>

                    {versionBadge && (
                        <>
                            <span style={divider} />
                            <span style={{
                                color: C.accent,
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
                    <span style={{ color: C.textDisabled, fontSize: 9, fontWeight: 500 }}>
                        {health.version || "—"}
                    </span>
                    <span style={{
                        color: C.textTertiary,
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
                                    const color = info.status === "ok" ? C.accent : C.danger
                                    const isProblem = info.status !== "ok"
                                    const impact = isProblem ? API_IMPACT[key] : null
                                    return (
                                        <div key={key} style={{
                                            ...card,
                                            borderColor: info.status === "error" ? `${C.danger}33` : C.bgElevated,
                                            minWidth: impact ? 200 : card.minWidth,
                                        }}>
                                            <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 4 }}>
                                                <span style={{
                                                    width: 6, height: 6, borderRadius: "50%",
                                                    background: color, display: "inline-block",
                                                }} />
                                                <span style={{ color: C.textSecondary, fontSize: 10, fontWeight: 700 }}>
                                                    {API_LABELS[key] || key}
                                                </span>
                                            </div>
                                            <span style={{ color: C.textTertiary, fontSize: 9 }}>
                                                {info.detail || info.status}
                                            </span>
                                            {info.latency_ms != null && info.latency_ms > 0 && (
                                                <span style={{ color: C.textDisabled, fontSize: 8, marginTop: 2, display: "block" }}>
                                                    {info.latency_ms}ms
                                                </span>
                                            )}
                                            {impact && (
                                                <div style={{
                                                    marginTop: 6,
                                                    paddingTop: 6,
                                                    borderTop: "1px solid rgba(239,68,68,0.2)",
                                                    color: C.danger,
                                                    fontSize: 9,
                                                    lineHeight: "1.4",
                                                }}>
                                                    <span style={{ color: C.danger, fontWeight: 700 }}>영향: </span>
                                                    {impact}
                                                </div>
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
                            <div style={{ ...card, borderColor: C.bgElevated }}>
                                <span style={{ color: C.textTertiary, fontSize: 10 }}>
                                    상세 진단 데이터는 다음 분석 실행 후 표시됩니다.
                                </span>
                                <span style={{ color: C.textDisabled, fontSize: 9, marginTop: 4, display: "block" }}>
                                    GitHub Actions가 main.py를 실행하면 API별 상태, Worker 결과, 버전 정보가 자동으로 수집됩니다.
                                </span>
                            </div>
                        </div>
                    )}

                    {/* GitHub Worker */}
                    {health.github_worker && (
                        <div style={section}>
                            <span style={sectionTitle}>GITHUB WORKER</span>
                            <div style={{ ...card, borderColor: C.bgElevated, maxWidth: 350 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                                    <span>{workerIcon}</span>
                                    <span style={{ color: C.textSecondary, fontSize: 10, fontWeight: 700 }}>
                                        {health.github_worker.workflow || "—"}
                                    </span>
                                </div>
                                <span style={{ color: C.textTertiary, fontSize: 9 }}>
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
                                        style={{ color: C.accent, fontSize: 9, marginTop: 4, display: "block", textDecoration: "none" }}
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
                                const dotColor = isMissing ? C.danger : isStale ? C.warn : C.accent
                                return (
                                    <div key={fname} style={{ ...card, borderColor: isStale ? `${C.warn}33` : C.bgElevated }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 4 }}>
                                            <span style={{
                                                width: 6, height: 6, borderRadius: "50%",
                                                background: dotColor, display: "inline-block",
                                            }} />
                                            <span style={{ color: C.textSecondary, fontSize: 10, fontWeight: 700 }}>
                                                {fname}
                                            </span>
                                        </div>
                                        <span style={{ color: C.textTertiary, fontSize: 9 }}>
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
                        <div style={{ ...card, borderColor: versionBadge ? `${C.accent}33` : C.bgElevated, maxWidth: 400 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                <span style={{ color: C.textSecondary, fontSize: T.cap, fontWeight: 800 }}>
                                    {health.version_sync?.local_version || health.version || "—"}
                                </span>
                                <span style={{ color: C.textDisabled, fontSize: 9 }}>
                                    ({health.version_sync?.local_sha || "?"})
                                </span>
                                {versionBadge && (
                                    <span style={{
                                        color: C.accent,
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
                                <span style={{ color: C.textTertiary, fontSize: 9, marginTop: 4, display: "block" }}>
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
                                        <span style={{ color: C.danger, fontSize: 10 }}>■</span>
                                        <span style={{ color: C.danger, fontSize: 10, fontWeight: 600 }}>{e}</span>
                                    </div>
                                ))}
                                {health.warnings?.map((w, i) => (
                                    <div key={`w${i}`} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                        <span style={{ color: C.warn, fontSize: 10 }}>+</span>
                                        <span style={{ color: C.warn, fontSize: 10, fontWeight: 600 }}>{w}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* 진단 시각 */}
                    <div style={{ textAlign: "center", paddingTop: 8 }}>
                        <span style={{ color: C.border, fontSize: 9 }}>
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
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
    refreshInterval: 300,
}

addPropertyControls(SystemHealthBar, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
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

const font = FONT

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
    color: C.textTertiary,
    fontSize: 9,
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
    background: C.bgElevated,
    flexShrink: 0,
}

const panel: React.CSSProperties = {
    background: C.bgPage,
    borderBottom: `1px solid ${C.border}`,
    padding: "16px 24px",
    animation: "slideDown 0.3s ease",
    overflow: "hidden",
}

const section: React.CSSProperties = {
    marginBottom: 14,
}

const sectionTitle: React.CSSProperties = {
    display: "block",
    color: C.textDisabled,
    fontSize: T.cap,
    fontWeight: 800,
    letterSpacing: "0.1em",
    marginBottom: 8,
}

const card: React.CSSProperties = {
    background: C.bgElevated,
    border: "1px solid",
    borderRadius: 8,
    padding: "8px 12px",
    minWidth: 120,
}
