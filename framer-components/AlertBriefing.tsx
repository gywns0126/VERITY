/**
 * ⚠️ DEPRECATED (2026-05-05 Plan v0.1 §3 [Alert] 폐기 결정)
 *
 * AlertHub 의 briefing view 로 흡수 (탭하면 expand)
 *
 * Framer 페이지에서 인스턴스 제거. 추후 일괄 cleanup commit 시 git rm.
 *
 * ────────────────────────────────────────────────────────────
 */
import React, { useState, useEffect } from "react"
import type { CSSProperties } from "react"
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


function _bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    return `${u}${u.includes("?") ? "&" : "?"}_=${Date.now()}`
}

function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    return fetch(_bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((t) => JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
}

interface Props {
    dataUrl: string
    market: "kr" | "us"
}

const TONE_STYLES: Record<string, { bg: string; border: string; icon: string; label: string }> = {
    urgent: { bg: "rgba(239,68,68,0.08)", border: "#EF4444", icon: "🔴", label: "긴급" },
    cautious: { bg: "rgba(234,179,8,0.08)", border: "#EAB308", icon: "🟡", label: "주의" },
    defensive: { bg: "rgba(234,179,8,0.06)", border: "#F59E0B", icon: "🛡️", label: "방어" },
    positive: { bg: "rgba(34,197,94,0.06)", border: "#22C55E", icon: "🟢", label: "양호" },
    neutral: { bg: "rgba(136,136,136,0.06)", border: "#555", icon: "⚪", label: "중립" },
}

const LEVEL_STYLES: Record<string, { bg: string; color: string; label: string }> = {
    CRITICAL: { bg: "rgba(239,68,68,0.15)", color: "#EF4444", label: "긴급" },
    WARNING: { bg: "rgba(234,179,8,0.15)", color: "#EAB308", label: "주의" },
    INFO: { bg: "rgba(96,165,250,0.12)", color: "#60A5FA", label: "참고" },
}

const CAT_LABELS: Record<string, string> = {
    macro: "매크로",
    holding: "보유종목",
    earnings: "실적",
    opportunity: "기회",
    news: "뉴스",
    event: "이벤트",
    strategy: "전략",
    ai_consensus: "AI합의",
}

const US_EVENT_KW = ["FOMC", "CPI", "GDP", "PCE", "NFP", "Fed", "고용", "비농업", "소비자물가", "금리결정", "PPI", "ISM", "PMI"]
const KR_EVENT_KW = ["한국", "코스피", "코스닥", "한국은행", "기준금리", "수출", "무역수지", "원달러"]
const US_ALERT_KW = ["미국", "연준", "Fed", "NASDAQ", "NYSE", "S&P", "다우", "국채", "VIX", "달러"]
const KR_ALERT_KW = ["한국", "국내", "코스피", "코스닥", "KRX", "원달러", "원화", "한국은행", "기준금리"]

function _isUSTicker(ticker: string): boolean {
    return /^[A-Z]{1,5}$/.test(String(ticker || "").trim())
}

function _isUSRecommendation(r: any): boolean {
    const m = String(r?.market || "")
    return r?.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(m) || _isUSTicker(r?.ticker || "")
}

function _toText(v: any): string {
    if (v == null) return ""
    if (Array.isArray(v)) return v.map(_toText).join(" ")
    return String(v)
}

function _containsAny(text: string, kws: string[]): boolean {
    const t = String(text || "").toLowerCase()
    return kws.some((kw) => t.includes(kw.toLowerCase()))
}

function _containsToken(text: string, tokens: Set<string>): boolean {
    const t = String(text || "").toLowerCase()
    for (const token of tokens) {
        if (token && t.includes(token)) return true
    }
    return false
}

function _isUSEvent(e: any): boolean {
    const txt = `${_toText(e?.name)} ${_toText(e?.impact)} ${_toText(e?.country)}`
    if (_containsAny(txt, US_EVENT_KW)) return true
    if ((e?.country || "").toLowerCase().includes("미국")) return true
    if (_containsAny(txt, KR_EVENT_KW)) return false
    return false
}

function _isUSAlert(a: any, usTokens: Set<string>, krTokens: Set<string>): boolean {
    const cat = String(a?.category || "").toLowerCase()
    const ticker = String(a?.ticker || "").trim()
    const txt = `${_toText(a?.message)} ${_toText(a?.action)} ${_toText(a?.ticker)}`

    if (ticker) return _isUSTicker(ticker)
    if (_containsToken(txt, usTokens)) return true
    if (_containsToken(txt, krTokens)) return false
    if (_containsAny(txt, US_ALERT_KW)) return true
    if (_containsAny(txt, KR_ALERT_KW)) return false

    // 종목 중심 카테고리는 티커/텍스트에 시장 단서가 없으면 KR 기본값으로 처리
    if (["holding", "earnings", "opportunity", "price_target", "value_chain"].includes(cat)) {
        return false
    }
    return false
}

export default function AlertBriefing(props: Props) {
    const { dataUrl } = props
    const isUS = props.market === "us"
    const [data, setData] = useState<any>(null)
    const [expanded, setExpanded] = useState(false)
    // alerts 탭 제거 (AlertDashboard 가 담당) — 이 컴포넌트는 이벤트 브리핑 전용

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchPortfolioJson(dataUrl, ac.signal).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    if (!data) {
        return (
            <div style={styles.container}>
                <div style={styles.loading}>VERITY 브리핑 준비 중...</div>
            </div>
        )
    }

    const briefing = data.briefing || {}
    const allRecs: any[] = data.recommendations || []
    const usTokens = new Set<string>()
    const krTokens = new Set<string>()
    for (const r of allRecs) {
        const ticker = String(r?.ticker || "").trim().toLowerCase()
        const name = String(r?.name || "").trim().toLowerCase()
        const target = _isUSRecommendation(r) ? usTokens : krTokens
        if (ticker.length >= 1) target.add(ticker)
        if (name.length >= 2) target.add(name)
    }
    const allEvents: any[] = data.global_events || []
    const events: any[] = allEvents.filter((e) => (isUS ? _isUSEvent(e) : !_isUSEvent(e)))
    const allAlerts: any[] = briefing.alerts || []
    const alerts: any[] = allAlerts.filter((a) => (isUS ? _isUSAlert(a, usTokens, krTokens) : !_isUSAlert(a, usTokens, krTokens)))
    const counts = {
        critical: alerts.filter((a) => a?.level === "CRITICAL").length,
        warning: alerts.filter((a) => a?.level === "WARNING").length,
        info: alerts.filter((a) => a?.level === "INFO").length,
    }
    const actions: string[] = alerts
        .map((a) => String(a?.action || "").trim())
        .filter(Boolean)
        .slice(0, 3)
    const toneKey =
        counts.critical > 0 ? "urgent"
            : counts.warning > 0 ? "cautious"
                : counts.info > 0 ? "neutral"
                    : (briefing.tone || "neutral")
    const tone = TONE_STYLES[toneKey] || TONE_STYLES.neutral
    const marketHeadline = alerts[0]?.message || briefing.headline || "분석 대기 중"
    const updatedAt = data.updated_at || ""

    const upcomingEvents = events.filter((e: any) => (e.d_day ?? 99) <= 7)

    return (
        <div style={styles.container}>
            {/* 비서의 한마디 — 최상단 헤드라인 */}
            <div
                style={{
                    ...styles.headlineBanner,
                    background: tone.bg,
                    borderLeft: `3px solid ${tone.border}`,
                }}
                onClick={() => setExpanded(!expanded)}
            >
                <div style={styles.headlineRow}>
                    <span style={{ fontSize: 18 }}>{tone.icon}</span>
                    <div style={styles.headlineText}>
                        <div style={styles.headlineLabel}>
                            VERITY · {tone.label}
                        </div>
                        <div style={styles.headlineMessage}>
                            {marketHeadline}
                        </div>
                    </div>
                    <div style={styles.expandArrow}>{expanded ? "▲" : "▼"}</div>
                </div>

                {/* 요약 배지 */}
                <div style={styles.badgeRow}>
                    {counts.critical > 0 && (
                        <span style={{ ...styles.badge, background: LEVEL_STYLES.CRITICAL.bg, color: LEVEL_STYLES.CRITICAL.color }}>
                            긴급 {counts.critical}
                        </span>
                    )}
                    {counts.warning > 0 && (
                        <span style={{ ...styles.badge, background: LEVEL_STYLES.WARNING.bg, color: LEVEL_STYLES.WARNING.color }}>
                            주의 {counts.warning}
                        </span>
                    )}
                    {counts.info > 0 && (
                        <span style={{ ...styles.badge, background: LEVEL_STYLES.INFO.bg, color: LEVEL_STYLES.INFO.color }}>
                            참고 {counts.info}
                        </span>
                    )}
                    {upcomingEvents.length > 0 && (
                        <span style={{ ...styles.badge, background: "rgba(168,85,247,0.12)", color: "#A855F7" }}>
                            이벤트 {upcomingEvents.length}
                        </span>
                    )}
                    <span style={styles.time}>
                        {updatedAt ? new Date(updatedAt).toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : ""}
                    </span>
                </div>

                {/* 지금 해야 할 것 */}
                {actions.length > 0 && (
                    <div style={styles.actionBox}>
                        <div style={styles.actionTitle}>지금 해야 할 것</div>
                        {actions.map((a, i) => (
                            <div key={i} style={styles.actionItem}>→ {a}</div>
                        ))}
                    </div>
                )}
            </div>

            {/* 펼침 영역: 다가오는 이벤트 (알림 상세는 AlertDashboard 참조) */}
            {expanded && (
                <div style={styles.expandedArea}>
                    {/* 이벤트 헤더 */}
                    <div style={styles.sectionHeader}>
                        <span style={styles.sectionTitle}>다가오는 이벤트 ({upcomingEvents.length})</span>
                        {alerts.length > 0 && (
                            <span style={styles.hintText}>
                                경고 {alerts.length}건 — 알림 센터에서 확인
                            </span>
                        )}
                    </div>

                    <div style={styles.alertList}>
                        {upcomingEvents.length === 0 && (
                            <div style={styles.emptyText}>7일 내 주요 이벤트 없음</div>
                        )}
                        {upcomingEvents.map((e: any, i: number) => {
                            const sev = e.severity === "high" ? LEVEL_STYLES.CRITICAL : e.severity === "medium" ? LEVEL_STYLES.WARNING : LEVEL_STYLES.INFO
                            return (
                                <div key={i} style={{ ...styles.alertCard, borderLeft: `3px solid ${sev.color}` }}>
                                    <div style={styles.alertHeader}>
                                        <span style={{ ...styles.alertBadge, background: sev.bg, color: sev.color }}>
                                            D-{e.d_day ?? "?"}
                                        </span>
                                        <span style={styles.alertCat}>
                                            {e.date ? new Date(e.date).toLocaleDateString("ko-KR", { month: "short", day: "numeric" }) : ""}
                                        </span>
                                    </div>
                                    <div style={styles.alertMsg}>{e.name}</div>
                                    <div style={styles.eventImpact}>{e.impact}</div>
                                    {e.action && (
                                        <div style={styles.alertAction}>→ {e.action}</div>
                                    )}
                                    {Array.isArray(e.impact_area) && e.impact_area.length > 0 && (
                                        <div style={styles.impactTags}>
                                            {e.impact_area.map((tag: string, j: number) => (
                                                <span key={j} style={styles.impactTag}>{tag}</span>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            )
                        })}
                    </div>

                    {/* 포트폴리오 상태 한줄 */}
                    {briefing.portfolio_status && (
                        <div style={styles.portfolioStatus}>{briefing.portfolio_status}</div>
                    )}
                </div>
            )}
        </div>
    )
}

AlertBriefing.defaultProps = { ...AlertBriefing.defaultProps, market: "kr" }

addPropertyControls(AlertBriefing, {
    dataUrl: {
        type: ControlType.String,
        title: "Data URL",
        defaultValue:
            "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
    },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["KR 국장", "US 미장"],
        defaultValue: "kr",
    },
})

const styles: Record<string, CSSProperties> = {
    container: {
        width: "100%",
        fontFamily: FONT,
    },
    loading: {
        padding: "16px 20px",
        color: C.textTertiary,
        fontSize: 13,
        background: "rgba(255,255,255,0.02)",
        borderRadius: 12,
        border: "1px solid rgba(255,255,255,0.06)",
    },
    headlineBanner: {
        padding: "16px 20px",
        borderRadius: 12,
        cursor: "pointer",
        transition: "all 0.2s",
    },
    headlineRow: {
        display: "flex",
        alignItems: "flex-start",
        gap: 12,
    },
    headlineText: {
        flex: 1,
    },
    headlineLabel: {
        fontSize: 12,
        color: C.textSecondary,
        fontWeight: 600,
        letterSpacing: "0.05em",
        textTransform: "uppercase" as const,
        marginBottom: 4,
    },
    headlineMessage: {
        fontSize: 15,
        fontWeight: 600,
        color: C.textPrimary,
        lineHeight: "1.5",
    },
    expandArrow: {
        color: C.textTertiary,
        fontSize: 12,
        marginTop: 4,
    },
    badgeRow: {
        display: "flex",
        gap: 6,
        marginTop: 10,
        flexWrap: "wrap" as const,
        alignItems: "center",
    },
    badge: {
        padding: "3px 8px",
        borderRadius: 6,
        fontSize: 12,
        fontWeight: 600,
    },
    time: {
        fontSize: 12,
        color: C.textTertiary,
        marginLeft: "auto",
    },
    actionBox: {
        marginTop: 12,
        padding: "10px 12px",
        background: "rgba(255,255,255,0.03)",
        borderRadius: 8,
        border: "1px solid rgba(255,255,255,0.06)",
    },
    actionTitle: {
        fontSize: 12,
        fontWeight: 700,
        color: "#FFD700",
        marginBottom: 6,
        letterSpacing: "0.03em",
    },
    actionItem: {
        fontSize: 13,
        color: C.textPrimary,
        lineHeight: "1.6",
    },
    expandedArea: {
        marginTop: 8,
        borderRadius: 12,
        background: "rgba(255,255,255,0.02)",
        border: "1px solid rgba(255,255,255,0.06)",
        overflow: "hidden",
    },
    sectionHeader: {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "10px 12px",
        borderBottom: "1px solid rgba(255,255,255,0.06)",
    },
    sectionTitle: {
        color: C.textPrimary,
        fontSize: 12,
        fontWeight: 700,
    },
    hintText: {
        color: C.textSecondary,
        fontSize: 12,
        fontStyle: "italic" as const,
    },
    alertList: {
        padding: "8px 12px",
        display: "flex",
        flexDirection: "column" as const,
        gap: 8,
    },
    emptyText: {
        textAlign: "center" as const,
        color: C.textTertiary,
        fontSize: 13,
        padding: "20px 0",
    },
    alertCard: {
        padding: "10px 12px",
        borderRadius: 8,
        background: "rgba(255,255,255,0.02)",
    },
    alertHeader: {
        display: "flex",
        alignItems: "center",
        gap: 8,
        marginBottom: 4,
    },
    alertBadge: {
        padding: "2px 6px",
        borderRadius: 6,
        fontSize: 12,
        fontWeight: 700,
    },
    alertCat: {
        fontSize: 12,
        color: C.textTertiary,
    },
    alertMsg: {
        fontSize: 13,
        color: C.textPrimary,
        lineHeight: "1.5",
    },
    alertAction: {
        fontSize: 12,
        color: "#FFD700",
        marginTop: 4,
    },
    eventImpact: {
        fontSize: 12,
        color: C.textSecondary,
        marginTop: 4,
        lineHeight: "1.4",
    },
    impactTags: {
        display: "flex",
        gap: 4,
        marginTop: 6,
    },
    impactTag: {
        padding: "2px 6px",
        borderRadius: 6,
        background: "rgba(168,85,247,0.1)",
        color: "#A855F7",
        fontSize: 12,
        fontWeight: 600,
    },
    portfolioStatus: {
        padding: "8px 12px",
        borderTop: "1px solid rgba(255,255,255,0.06)",
        fontSize: 12,
        color: C.textTertiary,
        textAlign: "center" as const,
    },
}
