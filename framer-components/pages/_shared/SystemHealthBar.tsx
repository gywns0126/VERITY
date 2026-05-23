import React, { useEffect, useState } from "react"
import { addPropertyControls, ControlType } from "framer"

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆ (Neo Dark Terminal — _shared-patterns.ts 마스터)
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11",
    bgCard: "#171820",
    bgElevated: "#22232B",
    bgInput: "#2A2B33",
    border: "#23242C",
    borderStrong: "#34353D",
    borderHover: "#B5FF19",
    textPrimary: "#F2F3F5",
    textSecondary: "#A8ABB2",
    textTertiary: "#6B6E76",
    textDisabled: "#4A4C52",
    accent: "#B5FF19",
    accentSoft: "rgba(181,255,25,0.12)",
    strongBuy: "#22C55E",
    buy: "#B5FF19",
    watch: "#FFD600",
    caution: "#F59E0B",
    avoid: "#EF4444",
    up: "#F04452",
    down: "#3182F6",
    info: "#5BA9FF",
    success: "#22C55E",
    warn: "#F59E0B",
    danger: "#EF4444",
}
const T = {
    cap: 12,
    body: 14,
    sub: 16,
    title: 18,
    h2: 22,
    h1: 28,
    w_reg: 400,
    w_med: 500,
    w_semi: 600,
    w_bold: 700,
    w_black: 800,
    lh_tight: 1.3,
    lh_normal: 1.5,
    lh_loose: 1.7,
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = {
    fontFamily: FONT_MONO,
    fontVariantNumeric: "tabular-nums",
}
/* ◆ DESIGN TOKENS END ◆ */

/** Framer 단일 파일용 fetch (fetchPortfolioJson.ts와 동일 로직) */
function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    const u = (url || "").trim()
    const sep = u.includes("?") ? "&" : "?"
    return fetch(`${u}${sep}_=${Date.now()}`, {
        cache: "no-store",
        mode: "cors",
        credentials: "omit",
        signal,
    })
        .then((r) => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            return r.text()
        })
        .then((txt) =>
            JSON.parse(
                txt
                    .replace(/\bNaN\b/g, "null")
                    .replace(/\bInfinity\b/g, "null")
                    .replace(/-null/g, "null")
            )
        )
}

interface Props {
    dataUrl: string
    pipelineUrl: string
    cronHealthUrl: string  // 2026-05-17 Phase 3 — cron_health.jsonl latest entry
    refreshInterval: number
    maxWidth: number
}

// 2026-05-17 Phase 3 — cron_health_monitor 결과 표시 (operator 한눈에 cron verdict)
interface CronHealthEntry {
    ts_kst?: string
    severity?: "PASS" | "WARNING" | "FAIL"
    findings?: string[]
    daily_summary?: { success?: number; total?: number; failure?: number }
    universe_scan_summary?: { success?: number; total?: number }
    macro_collect_summary?: { total?: number; fail_rate?: number }
    kis_lock_commits_24h?: number
    claude_final_verdict?: string
    claude_final_score?: number
    dispatch_chain_summary?: { total_24h?: number; success_24h?: number }
    macro_age_h?: number
}

// Phase 2-B 데이터 파이프라인 6 아티팩트 health (data_pipeline_health.json)
interface PipelineItem {
    key: string
    label: string
    status: "fresh" | "stale" | "missing"
    age_hours: number | null
    line_count?: number
    max_fresh_hours: number
    last_entry?: Record<string, unknown>
    diagnostics?: Record<string, unknown>
}

interface PipelineHealth {
    collected_at?: string
    overall_status: "ok" | "warn" | "error"
    summary: { fresh: number; stale: number; missing: number; total: number }
    items: PipelineItem[]
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
        files?: Record<
            string,
            { status: string; last_updated?: string; age_hours?: number }
        >
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

// API_LABELS: portfolio.json system_health.api_health 의 key 매핑.
// 2026-05-17 audit:
//   - 활성 (check_api_health 박힘, portfolio.json 14 + optional ecos): dart/fred/telegram/gemini/
//     anthropic/kipris/public_data/krx_open_api/perplexity/finnhub/polygon/sec_edgar/ecos/
//     reports_signed_url
//   - 잠재 dead 매핑 (UI label 만, 실제 source 0건): kis/newsapi/cftc_cot/cboe_pcr/fund_flows/
//     supabase/naver_news/google_news
//     · kis = [[project_kis_token_policy]] 1일 1토큰 ABSOLUTE → health check 의도적 회피 (별도
//       발급 시 사고). cache_only 모드 검증은 cron_health_monitor.yml 시간당 별도.
//     · newsapi/cftc_cot/cboe_pcr/fund_flows = macro/sentiment 모듈 잠재 활용 (Phase 2 큐).
//     · supabase = reports_signed_url 가 SUPABASE_SERVICE_ROLE_KEY 사용해 실측 wired (간접).
//     · naver_news/google_news = 뉴스 모듈 잠재 활용.
//   매핑은 운영자 가시성 위해 유지 (활성화 시 자동 표시).
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
    reports_signed_url: "Reports CDN",
}

const API_IMPACT: Record<string, string> = {
    dart: "StockDetailPanel · 종목 상세 (사업보고서·공시)",
    fred: "MacroPanel · 미국 매크로 (10Y·VIX·HY)",
    telegram: "자동 알림 수신 불가",
    gemini: "Gemini 종목 분석 · VerityReport",
    anthropic: "Claude 심층 분석 · dual_consensus",
    kipris: "특허 시그널",
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
    reports_signed_url: "리포트 PDF signed URL · 다운로드 차단",
}

const STATUS_CONFIG: Record<
    string,
    { color: string; label: string }
> = {
    ok: { color: C.accent, label: "ALL SYSTEMS OPERATIONAL" },
    warning: { color: C.warn, label: "경고 감지" },
    error: { color: C.danger, label: "시스템 오류" },
    unknown: { color: C.textTertiary, label: "진단 중..." },
    loading: { color: C.textTertiary, label: "로딩..." },
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

/**
 * 컴팩트 bar 의 API 상태 단일 카운터.
 * - 평상시: "● 16/16 정상"
 * - 장애 시: "● 14/16" + 문제 API 라벨 (DART · KRX)
 * 점 색상: 모두 ok=accent / 일부 error=danger / 일부 warning(unknown)=warn.
 */
function ApiSummary({ apis }: { apis: Record<string, ApiInfo> }) {
    const entries = Object.entries(apis) as [string, ApiInfo][]
    const total = entries.length
    if (total === 0) return null

    const errors = entries.filter(([, i]) => i.status === "error")
    const warns = entries.filter(
        ([, i]) => i.status !== "ok" && i.status !== "error"
    )
    const okCount = total - errors.length - warns.length
    const allOk = okCount === total

    const dotColor = errors.length
        ? C.danger
        : warns.length
          ? C.warn
          : C.accent
    const pulse = errors.length > 0

    const problemLabels = [...errors, ...warns]
        .slice(0, 4)
        .map(([k]) => API_LABELS[k] || k)
    const moreCount = errors.length + warns.length - problemLabels.length

    const tooltip = entries
        .map(([k, info]) => {
            const lab = API_LABELS[k] || k
            const lat =
                info.latency_ms != null && info.latency_ms > 0
                    ? ` ${info.latency_ms}ms`
                    : ""
            const stat = info.status === "ok" ? "✓" : "✗"
            return `${stat} ${lab}${lat}`
        })
        .join("\n")

    return (
        <div
            style={{ display: "flex", alignItems: "center", gap: 8 }}
            title={tooltip}
        >
            <span
                style={{
                    display: "inline-block",
                    width: 7,
                    height: 7,
                    borderRadius: "50%",
                    background: dotColor,
                    animation: pulse ? "pulse 1.5s infinite" : "none",
                    flexShrink: 0,
                }}
            />
            <span
                style={{
                    color: allOk ? C.textTertiary : dotColor,
                    fontSize: 11,
                    fontWeight: 700,
                    letterSpacing: 0.3,
                    ...MONO,
                }}
            >
                {okCount}/{total}
                {allOk ? " 정상" : ""}
            </span>
            {!allOk && problemLabels.length > 0 && (
                <span
                    style={{
                        color: dotColor,
                        fontSize: 11,
                        fontWeight: 600,
                        letterSpacing: 0.2,
                    }}
                >
                    ⚠ {problemLabels.join(" · ")}
                    {moreCount > 0 ? ` +${moreCount}` : ""}
                </span>
            )}
        </div>
    )
}

export default function SystemHealthBar(props: Props) {
    const { dataUrl, pipelineUrl, cronHealthUrl, refreshInterval, maxWidth } = props
    const [health, setHealth] = useState<HealthData | null>(null)
    const [pipelineHealth, setPipelineHealth] = useState<PipelineHealth | null>(null)
    const [cronHealth, setCronHealth] = useState<CronHealthEntry | null>(null)
    const [expanded, setExpanded] = useState(false)
    const [dismissed, setDismissed] = useState(false)
    const wrapperStyle: React.CSSProperties = {
        ...wrapper,
        maxWidth: maxWidth || undefined,
        margin: maxWidth ? "0 auto" : undefined,
    }

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
                        const ageH =
                            (Date.now() - new Date(updatedAt).getTime()) /
                            3600000
                        if (ageH > 24) {
                            warnings.push(
                                `데이터 ${Math.floor(ageH)}시간 경과 (24h 초과)`
                            )
                            overall = "warning"
                        }
                    }
                    setHealth({
                        status: overall,
                        checked_at: new Date().toISOString(),
                        version: "—",
                        data_recency: {
                            status: overall === "ok" ? "fresh" : "stale",
                            updated_at: updatedAt,
                        },
                        errors: [],
                        warnings,
                    })
                })
                .catch(() => {
                    if (!ac.signal.aborted)
                        setHealth({
                            status: "unknown",
                            errors: ["데이터 로드 실패"],
                        })
                })
        }
        doFetch()
        const id =
            refreshInterval > 0
                ? setInterval(doFetch, refreshInterval * 1000)
                : undefined
        return () => {
            ac.abort()
            if (id) clearInterval(id)
        }
    }, [dataUrl, refreshInterval])

    useEffect(() => {
        if (dismissed && isAlertMode) setDismissed(false)
    }, [isAlertMode])

    // Phase 2-B 데이터 파이프라인 health (data_pipeline_health.json)
    useEffect(() => {
        if (!pipelineUrl) return
        const ac = new AbortController()
        const doFetch = () => {
            fetchPortfolioJson(pipelineUrl, ac.signal)
                .then((data) => {
                    if (ac.signal.aborted) return
                    if (data && Array.isArray(data.items)) {
                        setPipelineHealth(data as PipelineHealth)
                    }
                })
                .catch(() => {
                    // silent — pipeline_health 결손이 SystemHealthBar 전체 망가뜨리지 않도록
                })
        }
        doFetch()
        const id =
            refreshInterval > 0
                ? setInterval(doFetch, refreshInterval * 1000)
                : undefined
        return () => {
            ac.abort()
            if (id) clearInterval(id)
        }
    }, [pipelineUrl, refreshInterval])

    // 2026-05-17 Phase 3 — cron_health.jsonl 마지막 entry fetch (시간당 갱신)
    useEffect(() => {
        if (!cronHealthUrl) return
        const ac = new AbortController()
        const doFetch = () => {
            const u = cronHealthUrl.trim()
            const sep = u.includes("?") ? "&" : "?"
            fetch(`${u}${sep}_=${Date.now()}`, {
                cache: "no-store", mode: "cors", credentials: "omit", signal: ac.signal,
            })
                .then((r) => {
                    if (!r.ok) throw new Error(`HTTP ${r.status}`)
                    return r.text()
                })
                .then((txt) => {
                    if (ac.signal.aborted) return
                    // jsonl 마지막 non-empty line parse
                    const lines = txt.split("\n").map((l) => l.trim()).filter(Boolean)
                    if (lines.length === 0) return
                    try {
                        const last = JSON.parse(lines[lines.length - 1])
                        setCronHealth(last as CronHealthEntry)
                    } catch {
                        // silent — jsonl parse 실패가 SystemHealthBar 전체 망가뜨리지 않도록
                    }
                })
                .catch(() => {
                    // silent — cron_health 결손이 SystemHealthBar 전체 망가뜨리지 않도록
                })
        }
        doFetch()
        const id =
            refreshInterval > 0
                ? setInterval(doFetch, refreshInterval * 1000)
                : undefined
        return () => {
            ac.abort()
            if (id) clearInterval(id)
        }
    }, [cronHealthUrl, refreshInterval])

    if (!health) {
        return (
            <div style={wrapperStyle}>
                <style>{`
                    @keyframes pulse {
                        0%, 100% { opacity: 1; }
                        50% { opacity: 0.4; }
                    }
                `}</style>
                <div style={{ ...bar, background: C.bgPage }}>
                    <div
                        style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                        }}
                    >
                        <span
                            style={{
                                width: 7,
                                height: 7,
                                borderRadius: "50%",
                                background: C.borderStrong,
                                animation: "pulse 1.5s infinite",
                            }}
                        />
                        <span
                            style={{
                                color: C.textTertiary,
                                fontSize: 11,
                                fontWeight: 700,
                                letterSpacing: 0.5,
                                textTransform: "uppercase",
                            }}
                        >
                            SYSTEM
                        </span>
                    </div>
                    <span
                        style={{
                            color: C.textDisabled,
                            fontSize: 11,
                            fontWeight: 500,
                        }}
                    >
                        연결 중...
                    </span>
                </div>
            </div>
        )
    }

    const cfg = STATUS_CONFIG[overall] || STATUS_CONFIG.unknown
    const hasIssues =
        (health.errors?.length || 0) + (health.warnings?.length || 0) > 0

    if (dismissed && !isAlertMode) {
        return null
    }

    const hasApiData =
        health.api_health && Object.keys(health.api_health).length > 0

    const workerColor =
        health.github_worker?.status === "ok"
            ? C.accent
            : health.github_worker?.status === "running"
              ? C.warn
              : health.github_worker?.status === "error"
                ? C.danger
                : C.textTertiary

    const recencyUpdatedAt = health.data_recency?.updated_at
    const dataAge = recencyUpdatedAt ? timeSince(recencyUpdatedAt) : "—"
    const dataAbsTime = recencyUpdatedAt
        ? new Date(recencyUpdatedAt).toLocaleString("ko-KR", {
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
          })
        : ""
    const recencyAgeH = recencyUpdatedAt
        ? (Date.now() - new Date(recencyUpdatedAt).getTime()) / 3600000
        : 0
    const isDataStale = recencyAgeH > 24

    const versionBadge = health.version_sync?.status === "update_available"

    return (
        <div style={wrapperStyle}>
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
                <div
                    style={{
                        ...alertBar,
                        background:
                            overall === "error"
                                ? "linear-gradient(90deg, rgba(239,68,68,0.18), rgba(239,68,68,0.04))"
                                : "linear-gradient(90deg, rgba(234,179,8,0.14), rgba(234,179,8,0.03))",
                    }}
                >
                    <div
                        style={{
                            display: "flex",
                            alignItems: "center",
                            gap: 10,
                            flex: 1,
                        }}
                    >
                        <span
                            style={{
                                width: 8,
                                height: 8,
                                borderRadius: "50%",
                                background: cfg.color,
                                animation: "pulse 2s infinite",
                                flexShrink: 0,
                            }}
                        />
                        <span
                            style={{
                                color: cfg.color,
                                fontSize: T.cap,
                                fontWeight: 700,
                                letterSpacing: 0.2,
                            }}
                        >
                            {health.errors?.[0] ||
                                health.warnings?.[0] ||
                                cfg.label}
                        </span>
                        {(health.errors?.length || 0) +
                            (health.warnings?.length || 0) >
                            1 && (
                            <span
                                style={{
                                    color: cfg.color,
                                    fontSize: 10,
                                    fontWeight: 700,
                                    ...MONO,
                                    letterSpacing: 0.3,
                                }}
                            >
                                +
                                {(health.errors?.length || 0) +
                                    (health.warnings?.length || 0) -
                                    1}
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
                style={{ ...bar, background: C.bgPage, cursor: "pointer" }}
                onClick={() => setExpanded(!expanded)}
            >
                {/* 상태 표시등 */}
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div
                        style={{
                            width: 7,
                            height: 7,
                            borderRadius: "50%",
                            background: cfg.color,
                            animation: isAlertMode
                                ? "pulse 1.5s infinite"
                                : "none",
                        }}
                    />
                    <span
                        style={{
                            color: cfg.color,
                            fontSize: 11,
                            fontWeight: 700,
                            letterSpacing: 0.5,
                            textTransform: "uppercase",
                        }}
                    >
                        SYSTEM
                    </span>
                </div>

                {/* 상태 정보 */}
                <div
                    style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 14,
                        flex: 1,
                        justifyContent: "center",
                        flexWrap: "wrap",
                    }}
                >
                    {hasApiData ? (
                        <>
                            <ApiSummary apis={health.api_health!} />
                            <span style={divider} />
                            <span
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 6,
                                }}
                                title="GitHub Actions"
                            >
                                <span
                                    style={{
                                        width: 6,
                                        height: 6,
                                        borderRadius: "50%",
                                        background: workerColor,
                                        flexShrink: 0,
                                    }}
                                />
                                <span
                                    style={{
                                        color: C.textTertiary,
                                        fontSize: 11,
                                        fontWeight: 600,
                                        letterSpacing: 0.2,
                                    }}
                                >
                                    Worker
                                </span>
                            </span>
                        </>
                    ) : (
                        <span
                            style={{
                                color: C.textTertiary,
                                fontSize: 11,
                                fontWeight: 500,
                            }}
                        >
                            {cfg.label}
                        </span>
                    )}

                    <span style={divider} />

                    <span
                        style={{
                            color: isDataStale ? C.danger : C.textTertiary,
                            fontSize: 11,
                            fontWeight: 600,
                            ...MONO,
                        }}
                        title={`데이터 갱신: ${dataAbsTime}`}
                    >
                        {dataAbsTime
                            ? `${dataAbsTime} · ${dataAge}`
                            : dataAge}
                    </span>

                    {versionBadge && (
                        <>
                            <span style={divider} />
                            <span
                                style={{
                                    color: C.accent,
                                    fontSize: 11,
                                    fontWeight: 800,
                                    letterSpacing: 0.5,
                                    textTransform: "uppercase",
                                }}
                            >
                                업데이트
                            </span>
                        </>
                    )}
                </div>

                {/* 버전 + 토글 */}
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span
                        style={{
                            color: C.textDisabled,
                            fontSize: 11,
                            fontWeight: 500,
                            ...MONO,
                        }}
                    >
                        {health.version || "—"}
                    </span>
                    <span
                        style={{
                            color: C.textTertiary,
                            fontSize: 11,
                            transform: expanded
                                ? "rotate(180deg)"
                                : "rotate(0deg)",
                            transition: "transform 180ms ease",
                        }}
                    >
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
                            <div
                                style={{
                                    display: "flex",
                                    flexWrap: "wrap",
                                    gap: 10,
                                }}
                            >
                                {(
                                    Object.entries(health.api_health!) as [
                                        string,
                                        ApiInfo,
                                    ][]
                                ).map(([key, info]) => {
                                    const color =
                                        info.status === "ok"
                                            ? C.accent
                                            : C.danger
                                    const isProblem = info.status !== "ok"
                                    const impact = isProblem
                                        ? API_IMPACT[key]
                                        : null
                                    return (
                                        <div
                                            key={key}
                                            style={{
                                                ...card,
                                                minWidth: impact
                                                    ? 220
                                                    : card.minWidth,
                                            }}
                                        >
                                            <div
                                                style={{
                                                    display: "flex",
                                                    alignItems: "center",
                                                    gap: 6,
                                                    marginBottom: 6,
                                                }}
                                            >
                                                <span
                                                    style={{
                                                        width: 6,
                                                        height: 6,
                                                        borderRadius: "50%",
                                                        background: color,
                                                        display: "inline-block",
                                                    }}
                                                />
                                                <span
                                                    style={{
                                                        color: C.textPrimary,
                                                        fontSize: 11,
                                                        fontWeight: 700,
                                                        letterSpacing: 0.2,
                                                    }}
                                                >
                                                    {API_LABELS[key] || key}
                                                </span>
                                            </div>
                                            <span
                                                style={{
                                                    color: C.textTertiary,
                                                    fontSize: 11,
                                                }}
                                            >
                                                {info.detail || info.status}
                                            </span>
                                            {info.latency_ms != null &&
                                                info.latency_ms > 0 && (
                                                    <span
                                                        style={{
                                                            color: C.textDisabled,
                                                            fontSize: 10,
                                                            marginTop: 4,
                                                            display: "block",
                                                            ...MONO,
                                                        }}
                                                    >
                                                        {info.latency_ms}ms
                                                    </span>
                                                )}
                                            {impact && (
                                                <div
                                                    style={{
                                                        marginTop: 8,
                                                        color: C.danger,
                                                        fontSize: 11,
                                                        lineHeight: 1.45,
                                                    }}
                                                >
                                                    <span
                                                        style={{
                                                            color: C.danger,
                                                            fontWeight: 700,
                                                            letterSpacing: 0.3,
                                                            textTransform:
                                                                "uppercase",
                                                            fontSize: 10,
                                                        }}
                                                    >
                                                        영향{" "}
                                                    </span>
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
                            <div style={card}>
                                <span
                                    style={{
                                        color: C.textTertiary,
                                        fontSize: 11,
                                    }}
                                >
                                    상세 진단 데이터는 다음 분석 실행 후
                                    표시됩니다.
                                </span>
                                <span
                                    style={{
                                        color: C.textDisabled,
                                        fontSize: 11,
                                        marginTop: 6,
                                        display: "block",
                                        lineHeight: 1.5,
                                    }}
                                >
                                    GitHub Actions가 main.py를 실행하면 API별
                                    상태, Worker 결과, 버전 정보가 자동으로
                                    수집됩니다.
                                </span>
                            </div>
                        </div>
                    )}

                    {/* GitHub Worker */}
                    {health.github_worker && (
                        <div style={section}>
                            <span style={sectionTitle}>GITHUB WORKER</span>
                            <div style={{ ...card, maxWidth: 360 }}>
                                <div
                                    style={{
                                        display: "flex",
                                        alignItems: "center",
                                        gap: 6,
                                        marginBottom: 6,
                                    }}
                                >
                                    <span
                                        style={{
                                            width: 6,
                                            height: 6,
                                            borderRadius: "50%",
                                            background: workerColor,
                                            flexShrink: 0,
                                        }}
                                    />
                                    <span
                                        style={{
                                            color: C.textPrimary,
                                            fontSize: 11,
                                            fontWeight: 700,
                                            letterSpacing: 0.2,
                                        }}
                                    >
                                        {health.github_worker.workflow || "—"}
                                    </span>
                                </div>
                                <span
                                    style={{
                                        color: C.textTertiary,
                                        fontSize: 11,
                                    }}
                                >
                                    {health.github_worker.conclusion ||
                                        "unknown"}
                                    {health.github_worker.started_at && (
                                        <>
                                            {" "}
                                            ·{" "}
                                            {timeSince(
                                                health.github_worker.started_at
                                            )}
                                        </>
                                    )}
                                </span>
                                {health.github_worker.url && (
                                    <a
                                        href={health.github_worker.url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        style={{
                                            color: C.accent,
                                            fontSize: 11,
                                            marginTop: 6,
                                            display: "block",
                                            textDecoration: "none",
                                            fontWeight: 700,
                                            letterSpacing: 0.3,
                                        }}
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
                        <div
                            style={{
                                display: "flex",
                                flexWrap: "wrap",
                                gap: 10,
                            }}
                        >
                            {health.data_recency?.files &&
                                (
                                    Object.entries(
                                        health.data_recency.files
                                    ) as [
                                        string,
                                        {
                                            status: string
                                            last_updated?: string
                                            age_hours?: number
                                        },
                                    ][]
                                ).map(([fname, info]) => {
                                    const isStale = info.status === "stale"
                                    const isMissing = info.status === "missing"
                                    const dotColor = isMissing
                                        ? C.danger
                                        : isStale
                                          ? C.warn
                                          : C.accent
                                    return (
                                        <div key={fname} style={card}>
                                            <div
                                                style={{
                                                    display: "flex",
                                                    alignItems: "center",
                                                    gap: 6,
                                                    marginBottom: 6,
                                                }}
                                            >
                                                <span
                                                    style={{
                                                        width: 6,
                                                        height: 6,
                                                        borderRadius: "50%",
                                                        background: dotColor,
                                                        display: "inline-block",
                                                    }}
                                                />
                                                <span
                                                    style={{
                                                        color: C.textPrimary,
                                                        fontSize: 11,
                                                        fontWeight: 700,
                                                        letterSpacing: 0.2,
                                                    }}
                                                >
                                                    {fname}
                                                </span>
                                            </div>
                                            <span
                                                style={{
                                                    color: C.textTertiary,
                                                    fontSize: 11,
                                                    ...MONO,
                                                }}
                                            >
                                                {isMissing
                                                    ? "파일 없음"
                                                    : `${info.last_updated || "?"} · ${info.age_hours?.toFixed(1) || "?"}h`}
                                            </span>
                                        </div>
                                    )
                                })}
                        </div>
                    </div>

                    {/* 2026-05-17 Phase 3 — Cron Health Monitor verdict */}
                    {cronHealth && cronHealth.severity && (
                        <div style={section}>
                            <span style={sectionTitle}>
                                CRON HEALTH ·{" "}
                                <span
                                    style={{
                                        color:
                                            cronHealth.severity === "PASS"
                                                ? C.accent
                                                : cronHealth.severity === "WARNING"
                                                  ? C.warn
                                                  : C.danger,
                                    }}
                                >
                                    {cronHealth.severity}
                                </span>
                                {cronHealth.ts_kst && (
                                    <span
                                        style={{
                                            color: C.textDisabled,
                                            fontSize: 10,
                                            fontWeight: 500,
                                            marginLeft: 10,
                                            ...MONO,
                                        }}
                                    >
                                        · {timeSince(cronHealth.ts_kst)}
                                    </span>
                                )}
                            </span>
                            <div
                                style={{
                                    display: "flex",
                                    flexWrap: "wrap",
                                    gap: 10,
                                }}
                            >
                                {cronHealth.universe_scan_summary && (
                                    <div style={card}>
                                        <div
                                            style={{
                                                color: C.textPrimary,
                                                fontSize: 11,
                                                fontWeight: 700,
                                                letterSpacing: 0.2,
                                                marginBottom: 6,
                                            }}
                                        >
                                            universe_scan
                                        </div>
                                        <span
                                            style={{
                                                color: C.textTertiary,
                                                fontSize: 11,
                                                ...MONO,
                                            }}
                                        >
                                            success{" "}
                                            {cronHealth.universe_scan_summary.success ?? "?"}/
                                            {cronHealth.universe_scan_summary.total ?? "?"}
                                        </span>
                                    </div>
                                )}
                                {cronHealth.macro_collect_summary && (
                                    <div style={card}>
                                        <div
                                            style={{
                                                color: C.textPrimary,
                                                fontSize: 11,
                                                fontWeight: 700,
                                                letterSpacing: 0.2,
                                                marginBottom: 6,
                                            }}
                                        >
                                            macro_collect
                                        </div>
                                        <span
                                            style={{
                                                color: C.textTertiary,
                                                fontSize: 11,
                                                ...MONO,
                                            }}
                                        >
                                            total {cronHealth.macro_collect_summary.total ?? "?"} · fail{" "}
                                            {((cronHealth.macro_collect_summary.fail_rate ?? 0) * 100).toFixed(0)}%
                                        </span>
                                    </div>
                                )}
                                {cronHealth.kis_lock_commits_24h != null && (
                                    <div style={card}>
                                        <div
                                            style={{
                                                color: C.textPrimary,
                                                fontSize: 11,
                                                fontWeight: 700,
                                                letterSpacing: 0.2,
                                                marginBottom: 6,
                                            }}
                                        >
                                            KIS lock 24h
                                        </div>
                                        <span
                                            style={{
                                                color:
                                                    cronHealth.kis_lock_commits_24h >= 3
                                                        ? C.danger
                                                        : cronHealth.kis_lock_commits_24h === 2
                                                          ? C.warn
                                                          : C.accent,
                                                fontSize: 11,
                                                fontWeight: 700,
                                                ...MONO,
                                            }}
                                            title="1일 1토큰 ABSOLUTE — 2회=WARNING, ≥3회=FAIL (계좌 제재)"
                                        >
                                            {cronHealth.kis_lock_commits_24h}회
                                            {cronHealth.kis_lock_commits_24h <= 1 ? " ✓" : ""}
                                        </span>
                                    </div>
                                )}
                                {cronHealth.dispatch_chain_summary && (
                                    <div style={card}>
                                        <div
                                            style={{
                                                color: C.textPrimary,
                                                fontSize: 11,
                                                fontWeight: 700,
                                                letterSpacing: 0.2,
                                                marginBottom: 6,
                                            }}
                                        >
                                            price_pulse 24h
                                        </div>
                                        <span
                                            style={{
                                                color: C.textTertiary,
                                                fontSize: 11,
                                                ...MONO,
                                            }}
                                        >
                                            success{" "}
                                            {cronHealth.dispatch_chain_summary.success_24h ?? 0}/
                                            {cronHealth.dispatch_chain_summary.total_24h ?? 0}
                                        </span>
                                    </div>
                                )}
                                {cronHealth.claude_final_verdict && (
                                    <div style={card}>
                                        <div
                                            style={{
                                                color: C.textPrimary,
                                                fontSize: 11,
                                                fontWeight: 700,
                                                letterSpacing: 0.2,
                                                marginBottom: 6,
                                            }}
                                        >
                                            Claude 검수
                                        </div>
                                        <span
                                            style={{
                                                color:
                                                    cronHealth.claude_final_verdict ===
                                                    "REVIEW_REQUIRED"
                                                        ? C.danger
                                                        : cronHealth.claude_final_verdict === "CAUTION"
                                                          ? C.warn
                                                          : C.accent,
                                                fontSize: 11,
                                                ...MONO,
                                            }}
                                        >
                                            {cronHealth.claude_final_verdict}
                                            {cronHealth.claude_final_score != null
                                                ? ` (${cronHealth.claude_final_score})`
                                                : ""}
                                        </span>
                                    </div>
                                )}
                            </div>
                            {cronHealth.findings && cronHealth.findings.length > 0 && (
                                <div
                                    style={{
                                        marginTop: 8,
                                        display: "flex",
                                        flexDirection: "column",
                                        gap: 4,
                                    }}
                                >
                                    {cronHealth.findings.slice(0, 5).map((f, i) => (
                                        <span
                                            key={i}
                                            style={{
                                                color:
                                                    cronHealth.severity === "FAIL"
                                                        ? C.danger
                                                        : C.warn,
                                                fontSize: 11,
                                                fontWeight: 500,
                                            }}
                                        >
                                            • {f}
                                        </span>
                                    ))}
                                    {cronHealth.findings.length > 5 && (
                                        <span
                                            style={{
                                                color: C.textTertiary,
                                                fontSize: 10,
                                                ...MONO,
                                            }}
                                        >
                                            +{cronHealth.findings.length - 5} more
                                        </span>
                                    )}
                                </div>
                            )}
                        </div>
                    )}

                    {/* Phase 2-B Data Pipeline (6 아티팩트) */}
                    {pipelineHealth && pipelineHealth.items.length > 0 && (
                        <div style={section}>
                            <span style={sectionTitle}>
                                DATA PIPELINE (Phase 2-B) ·{" "}
                                <span
                                    style={{
                                        color:
                                            pipelineHealth.overall_status === "ok"
                                                ? C.accent
                                                : pipelineHealth.overall_status === "warn"
                                                  ? C.warn
                                                  : C.danger,
                                    }}
                                >
                                    {pipelineHealth.summary.fresh}/
                                    {pipelineHealth.summary.total} fresh
                                </span>
                            </span>
                            <div
                                style={{
                                    display: "flex",
                                    flexWrap: "wrap",
                                    gap: 10,
                                }}
                            >
                                {pipelineHealth.items.map((item) => {
                                    const dotColor =
                                        item.status === "missing"
                                            ? C.danger
                                            : item.status === "stale"
                                              ? C.warn
                                              : C.accent
                                    const ageStr =
                                        item.age_hours != null
                                            ? item.age_hours < 1
                                                ? `${(item.age_hours * 60).toFixed(0)}m`
                                                : `${item.age_hours.toFixed(1)}h`
                                            : "—"
                                    const triggers =
                                        (item.last_entry?.fail_triggers as
                                            | string[]
                                            | undefined) ?? []
                                    return (
                                        <div key={item.key} style={card}>
                                            <div
                                                style={{
                                                    display: "flex",
                                                    alignItems: "center",
                                                    gap: 6,
                                                    marginBottom: 6,
                                                }}
                                            >
                                                <span
                                                    style={{
                                                        width: 6,
                                                        height: 6,
                                                        borderRadius: "50%",
                                                        background: dotColor,
                                                        display: "inline-block",
                                                    }}
                                                />
                                                <span
                                                    style={{
                                                        color: C.textPrimary,
                                                        fontSize: 11,
                                                        fontWeight: 700,
                                                        letterSpacing: 0.2,
                                                    }}
                                                >
                                                    {item.label}
                                                </span>
                                            </div>
                                            <div
                                                style={{
                                                    color: C.textTertiary,
                                                    fontSize: 11,
                                                    ...MONO,
                                                }}
                                            >
                                                {item.status === "missing"
                                                    ? "파일 없음"
                                                    : `age ${ageStr} · max ${item.max_fresh_hours}h`}
                                            </div>
                                            {item.line_count != null && (
                                                <div
                                                    style={{
                                                        color: C.textTertiary,
                                                        fontSize: 11,
                                                        ...MONO,
                                                    }}
                                                >
                                                    rows {item.line_count.toLocaleString()}
                                                </div>
                                            )}
                                            {triggers.length > 0 && (
                                                <div
                                                    style={{
                                                        color: C.warn,
                                                        fontSize: 10,
                                                        marginTop: 4,
                                                    }}
                                                >
                                                    ⚠ {triggers.join(", ")}
                                                </div>
                                            )}
                                        </div>
                                    )
                                })}
                            </div>
                        </div>
                    )}

                    {/* Version */}
                    <div style={section}>
                        <span style={sectionTitle}>VERSION</span>
                        <div style={{ ...card, maxWidth: 420 }}>
                            <div
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 10,
                                    flexWrap: "wrap",
                                }}
                            >
                                <span
                                    style={{
                                        color: C.textPrimary,
                                        fontSize: 13,
                                        fontWeight: 800,
                                        letterSpacing: -0.2,
                                    }}
                                >
                                    {health.version_sync?.local_version ||
                                        health.version ||
                                        "—"}
                                </span>
                                <span
                                    style={{
                                        color: C.textDisabled,
                                        fontSize: 11,
                                        ...MONO,
                                    }}
                                >
                                    {health.version_sync?.local_sha || "?"}
                                </span>
                                {versionBadge && (
                                    <span
                                        style={{
                                            color: C.accent,
                                            fontSize: 10,
                                            fontWeight: 800,
                                            letterSpacing: 0.5,
                                            textTransform: "uppercase",
                                        }}
                                    >
                                        새 업데이트 감지
                                    </span>
                                )}
                            </div>
                            {health.version_sync?.remote_message &&
                                versionBadge && (
                                    <span
                                        style={{
                                            color: C.textTertiary,
                                            fontSize: 11,
                                            marginTop: 6,
                                            display: "block",
                                        }}
                                    >
                                        최신:{" "}
                                        {health.version_sync.remote_message}
                                    </span>
                                )}
                        </div>
                    </div>

                    {/* 에러/경고 상세 */}
                    {hasIssues && (
                        <div style={section}>
                            <span style={sectionTitle}>ISSUES</span>
                            <div
                                style={{
                                    display: "flex",
                                    flexDirection: "column",
                                    gap: 6,
                                }}
                            >
                                {health.errors?.map((e, i) => (
                                    <div
                                        key={`e${i}`}
                                        style={{
                                            display: "flex",
                                            alignItems: "center",
                                            gap: 8,
                                        }}
                                    >
                                        <span
                                            style={{
                                                width: 6,
                                                height: 6,
                                                borderRadius: "50%",
                                                background: C.danger,
                                                flexShrink: 0,
                                            }}
                                        />
                                        <span
                                            style={{
                                                color: C.danger,
                                                fontSize: 11,
                                                fontWeight: 600,
                                            }}
                                        >
                                            {e}
                                        </span>
                                    </div>
                                ))}
                                {health.warnings?.map((w, i) => (
                                    <div
                                        key={`w${i}`}
                                        style={{
                                            display: "flex",
                                            alignItems: "center",
                                            gap: 8,
                                        }}
                                    >
                                        <span
                                            style={{
                                                width: 6,
                                                height: 6,
                                                borderRadius: "50%",
                                                background: C.warn,
                                                flexShrink: 0,
                                            }}
                                        />
                                        <span
                                            style={{
                                                color: C.warn,
                                                fontSize: 11,
                                                fontWeight: 600,
                                            }}
                                        >
                                            {w}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* 진단 시각 */}
                    <div style={{ textAlign: "center", paddingTop: 10 }}>
                        <span
                            style={{
                                color: C.textDisabled,
                                fontSize: 10,
                                ...MONO,
                                letterSpacing: 0.3,
                            }}
                        >
                            진단{" "}
                            {health.checked_at
                                ? new Date(health.checked_at).toLocaleString(
                                      "ko-KR"
                                  )
                                : "—"}
                            {health.elapsed_ms
                                ? ` · ${health.elapsed_ms}ms`
                                : ""}
                        </span>
                    </div>
                </div>
            )}
        </div>
    )
}

SystemHealthBar.defaultProps = {
    dataUrl:
        "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/system_health_snapshot.json",
    pipelineUrl:
        "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/metadata/data_pipeline_health.json",
    cronHealthUrl:
        "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/metadata/cron_health.jsonl",
    refreshInterval: 300,
    maxWidth: 1400,
}

addPropertyControls(SystemHealthBar, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue:
            "https://raw.githubusercontent.com/gywns0126/VERITY-data/main/system_health_snapshot.json",
    },
    pipelineUrl: {
        type: ControlType.String,
        title: "Pipeline Health URL",
        defaultValue:
            "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/metadata/data_pipeline_health.json",
        description: "Phase 2-B 데이터 파이프라인 6 아티팩트 health (data_pipeline_health.json)",
    },
    cronHealthUrl: {
        type: ControlType.String,
        title: "Cron Health URL",
        defaultValue:
            "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/metadata/cron_health.jsonl",
        description: "Phase 3 — cron_health_monitor 시간당 verdict jsonl (마지막 entry 노출)",
    },
    refreshInterval: {
        type: ControlType.Number,
        title: "새로고침(초)",
        defaultValue: 300,
        min: 30,
        max: 3600,
        step: 30,
    },
    maxWidth: {
        type: ControlType.Number,
        title: "최대 너비(px)",
        defaultValue: 1400,
        min: 0,
        max: 2400,
        step: 50,
        description: "0 = 무제한",
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
    padding: "10px 24px",
    gap: 8,
}

const dismissBtn: React.CSSProperties = {
    background: "transparent",
    border: "none",
    color: C.textTertiary,
    fontSize: 16,
    cursor: "pointer",
    padding: "2px 8px",
    lineHeight: 1,
    fontFamily: font,
}

const bar: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 16,
    padding: "10px 24px",
    transition: "background 180ms ease",
}

const divider: React.CSSProperties = {
    width: 1,
    height: 12,
    background: C.bgElevated,
    flexShrink: 0,
}

const panel: React.CSSProperties = {
    background: C.bgCard,
    padding: "18px 24px 14px",
    animation: "slideDown 240ms ease",
    overflow: "hidden",
}

const section: React.CSSProperties = {
    marginBottom: 18,
}

const sectionTitle: React.CSSProperties = {
    display: "block",
    color: C.textTertiary,
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 0.5,
    textTransform: "uppercase",
    marginBottom: 10,
}

const card: React.CSSProperties = {
    background: C.bgElevated,
    border: "none",
    borderRadius: 10,
    padding: "10px 14px",
    minWidth: 140,
}
