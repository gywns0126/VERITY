/**
 * ⚠️ DEPRECATED (2026-05-05 Plan v0.1 §3 [Alert] 폐기 결정)
 *
 * AlertHub 단일 컴포넌트로 통합
 *
 * Framer 페이지에서 인스턴스 제거. 추후 일괄 cleanup commit 시 git rm.
 *
 * ────────────────────────────────────────────────────────────
 */
import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"
import type { CSSProperties } from "react"

/** Framer 단일 파일 붙여넣기용 — fetchPortfolioJson.ts와 동일 로직 */
function bustPortfolioUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

// WARN-24: 15초 timeout + AbortController — 네트워크 hang 방지
const PORTFOLIO_FETCH_TIMEOUT_MS = 15_000

function _withTimeout<T>(p: Promise<T>, ms: number, ac: AbortController): Promise<T> {
    const timer = setTimeout(() => ac.abort(), ms)
    return p.finally(() => clearTimeout(timer))
}

function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    const ac = new AbortController()
    if (signal) {
        if (signal.aborted) ac.abort()
        else signal.addEventListener("abort", () => ac.abort(), { once: true })
    }
    return _withTimeout(
        fetch(bustPortfolioUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal: ac.signal })
            .then((r) => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`)
                return r.text()
            })
            .then((txt) =>
                JSON.parse(
                    txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null"),
                ),
            ),
        PORTFOLIO_FETCH_TIMEOUT_MS,
        ac,
    )
}

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
    hoverOverlay: "rgba(255,255,255,0.04)", activeOverlay: "rgba(255,255,255,0.08)",
    focusRing: "rgba(181,255,25,0.35)", scrim: "rgba(0,0,0,0.5)",
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
/* ◆ DESIGN TOKENS END ◆ */

interface Props {
    dataUrl: string
    maxAlerts: number
    market: "kr" | "us"
}

type AlertLevel = "CRITICAL" | "WARNING" | "INFO"
type FilterType = "all" | AlertLevel

const LEVEL_META: Record<AlertLevel, { color: string; bg: string; icon: string; label: string }> = {
    CRITICAL: { color: C.danger, bg: "rgba(239,68,68,0.12)", icon: "🚨", label: "긴급" },
    WARNING: { color: C.watch, bg: "rgba(255,214,0,0.10)", icon: "⚠️", label: "주의" },
    INFO: { color: C.info, bg: "rgba(91,169,255,0.10)", icon: "ℹ️", label: "참고" },
}

const CAT_LABELS: Record<string, string> = {
    macro: "매크로",
    holding: "보유",
    earnings: "실적",
    opportunity: "기회",
    news: "뉴스",
    event: "이벤트",
    strategy: "전략",
    ai_consensus: "AI합의",
}

const US_ALERT_KW = ["미국", "연준", "Fed", "NASDAQ", "NYSE", "S&P", "다우", "국채", "VIX", "달러"]
const KR_ALERT_KW = ["한국", "국내", "코스피", "코스닥", "KRX", "원달러", "원화", "한국은행", "기준금리"]

function _isUSTicker(ticker: string): boolean {
    return /^[A-Z]{1,5}$/.test(String(ticker || "").trim())
}

function _isUSStock(s: any): boolean {
    return s?.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(s?.market || "") || _isUSTicker(s?.ticker || "")
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

function _isUSAlert(a: any, usTokens: Set<string>, krTokens: Set<string>): boolean {
    const cat = String(a?.category || "").toLowerCase()
    const ticker = String(a?.ticker || "").trim()
    const txt = `${_toText(a?.message)} ${_toText(a?.action)} ${_toText(a?.ticker)}`

    if (ticker) return _isUSTicker(ticker)
    if (_containsToken(txt, usTokens)) return true
    if (_containsToken(txt, krTokens)) return false
    if (_containsAny(txt, US_ALERT_KW)) return true
    if (_containsAny(txt, KR_ALERT_KW)) return false

    if (["holding", "earnings", "opportunity", "price_target", "value_chain"].includes(cat)) {
        return false
    }
    return false
}

export default function AlertDashboard(props: Props) {
    const { dataUrl, maxAlerts } = props
    const isUS = props.market === "us"
    const [data, setData] = useState<any>(null)
    const [filter, setFilter] = useState<FilterType>("all")

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchPortfolioJson(dataUrl, ac.signal).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    // 백엔드는 generate_briefing → portfolio["briefing"]["alerts"]에 저장함. 루트 data.alerts는 비어 있을 수 있음.
    const fromBriefing = data?.briefing?.alerts
    const fromRoot = data?.alerts
    const rawAlertsAll: any[] = Array.isArray(fromBriefing)
        ? fromBriefing
        : Array.isArray(fromRoot)
          ? fromRoot
          : []
    const recs: any[] = data?.recommendations || []
    const usTokens = new Set<string>()
    const krTokens = new Set<string>()
    for (const r of recs) {
        const ticker = String(r?.ticker || "").trim().toLowerCase()
        const name = String(r?.name || "").trim().toLowerCase()
        const target = _isUSStock(r) ? usTokens : krTokens
        if (ticker.length >= 1) target.add(ticker)
        if (name.length >= 2) target.add(name)
    }
    const rawAlerts = rawAlertsAll.filter((a: any) => (isUS ? _isUSAlert(a, usTokens, krTokens) : !_isUSAlert(a, usTokens, krTokens)))
    const cap = Math.min(30, Math.max(1, Number(maxAlerts) || 15))
    const alerts: any[] = rawAlerts.slice(0, cap)
    const filtered = filter === "all" ? alerts : alerts.filter((a: any) => a.level === filter)

    const counts = { CRITICAL: 0, WARNING: 0, INFO: 0 }
    alerts.forEach((a: any) => {
        if (a.level in counts) counts[a.level as AlertLevel]++
    })
    const aiConsensusCount = alerts.filter((a: any) => (a.category || "").toLowerCase() === "ai_consensus").length

    return (
        <div style={container}>
            <div style={headerRow}>
                <span style={titleStyle}>알림 센터</span>
                <div style={{ display: "flex", alignItems: "center", gap: S.sm }}>
                    {aiConsensusCount > 0 && (
                        <span style={{ ...categoryBadge, color: C.info, background: "rgba(91,169,255,0.12)", border: `1px solid rgba(91,169,255,0.25)` }}>
                            AI합의 <span style={{ fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }}>{aiConsensusCount}</span>
                        </span>
                    )}
                    <span style={{ color: C.textTertiary, fontSize: T.cap }}>
                        <span style={{ fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums", color: C.textSecondary }}>{alerts.length}</span>건
                    </span>
                </div>
            </div>

            <div style={filterRow}>
                <FilterChip label="전체" active={filter === "all"} count={alerts.length} onClick={() => setFilter("all")} color={C.textPrimary} />
                <FilterChip label="긴급" active={filter === "CRITICAL"} count={counts.CRITICAL} onClick={() => setFilter("CRITICAL")} color={C.danger} />
                <FilterChip label="주의" active={filter === "WARNING"} count={counts.WARNING} onClick={() => setFilter("WARNING")} color={C.watch} />
                <FilterChip label="참고" active={filter === "INFO"} count={counts.INFO} onClick={() => setFilter("INFO")} color={C.info} />
            </div>

            <div style={listWrap}>
                {filtered.length === 0 && (
                    <div style={{ color: C.textTertiary, fontSize: T.body, textAlign: "center", padding: S.xxl }}>
                        {alerts.length === 0 ? "알림이 없습니다." : "해당 레벨의 알림이 없습니다."}
                    </div>
                )}
                {filtered.map((a: any, i: number) => {
                    const meta = LEVEL_META[a.level as AlertLevel] || LEVEL_META.INFO
                    return (
                        <div key={i} style={{ ...alertCard, borderLeft: `3px solid ${meta.color}`, background: meta.bg }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <span style={{ fontSize: T.cap, fontWeight: T.w_bold, color: meta.color }}>
                                    {meta.icon} {meta.label}
                                </span>
                                {a.category && (
                                    <span style={categoryBadge}>{CAT_LABELS[String(a.category).toLowerCase()] || a.category}</span>
                                )}
                            </div>
                            <div style={{ color: C.textPrimary, fontSize: T.body, lineHeight: T.lh_normal, marginTop: S.xs }}>
                                {a.message}
                            </div>
                            {a.action && (
                                <div style={{ color: C.textSecondary, fontSize: T.cap, marginTop: S.xs, lineHeight: T.lh_normal }}>
                                    → {a.action}
                                </div>
                            )}
                        </div>
                    )
                })}
            </div>
        </div>
    )
}

function FilterChip({ label, active, count, onClick, color }: {
    label: string; active: boolean; count: number; onClick: () => void; color: string
}) {
    // active 시 동일 색상 알파 글로우 (네온 selective 적용)
    const glow = active && color === C.accent
        ? G.accentSoft
        : active
        ? `0 0 6px ${color}55`
        : "none"
    return (
        <span
            onClick={onClick}
            style={{
                padding: `${S.xs}px ${S.md}px`,
                borderRadius: R.pill,
                fontSize: T.cap,
                fontWeight: T.w_semi,
                cursor: "pointer",
                border: active ? `1px solid ${color}` : `1px solid ${C.border}`,
                background: active ? `${color}1F` : "transparent",
                color: active ? color : C.textTertiary,
                fontFamily: FONT,
                boxShadow: glow,
                transition: X.fast,
            }}
        >
            {label}{" "}
            {count > 0 && (
                <span style={{ fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }}>
                    {count}
                </span>
            )}
        </span>
    )
}

const DATA_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json"

AlertDashboard.defaultProps = {
    dataUrl: DATA_URL,
    maxAlerts: 15,
}

AlertDashboard.defaultProps = { ...AlertDashboard.defaultProps, market: "kr" }

addPropertyControls(AlertDashboard, {
    dataUrl: {
        type: ControlType.String,
        title: "데이터 URL",
        defaultValue: DATA_URL,
    },
    maxAlerts: {
        type: ControlType.Number,
        title: "최대 알림 수",
        defaultValue: 15,
        min: 5,
        max: 30,
        step: 1,
    },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["KR 국장", "US 미장"],
        defaultValue: "kr",
    },
})

const container: CSSProperties = {
    width: "100%",
    background: C.bgElevated,
    border: `1px solid ${C.border}`,
    borderRadius: R.lg,
    padding: S.xl,
    fontFamily: FONT,
    boxSizing: "border-box",
    display: "flex",
    flexDirection: "column",
    gap: S.md,
}

const headerRow: CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
}

const titleStyle: CSSProperties = {
    color: C.textPrimary,
    fontSize: T.sub,
    fontWeight: T.w_bold,
    fontFamily: FONT,
}

const filterRow: CSSProperties = {
    display: "flex",
    gap: S.sm,
    flexWrap: "wrap",
}

const listWrap: CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: S.sm,
}

const alertCard: CSSProperties = {
    padding: `${S.md}px ${S.lg}px`,
    borderRadius: R.md,
    display: "flex",
    flexDirection: "column",
    gap: S.xs,
}

const categoryBadge: CSSProperties = {
    fontSize: T.cap,
    color: C.textTertiary,
    background: C.bgInput,
    padding: `${S.xs / 2}px ${S.sm}px`,
    borderRadius: R.sm,
    fontFamily: FONT,
}
