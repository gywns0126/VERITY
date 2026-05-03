import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState, useRef } from "react"

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
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */

const font = FONT

/** Framer 단일 파일 붙여넣기용 인라인 (fetchPortfolioJson.ts와 동일 로직 — 수정 시 맞춰 주세요) */
// §8 AVOID 라벨 의미 — 펀더멘털 결함 전용
const AVOID_TOOLTIP =
    "AVOID = 펀더멘털 결함 (감사거절·분식·상폐 위험 등 has_critical) 또는 매크로 위기 cap. 단순 저점수는 CAUTION."

// §11~§14 audit overrides
const OVERRIDE_LABELS: Record<string, string> = {
    contrarian_upgrade: "역발상↑", quadrant_unfavored: "분면불리↓",
    cape_bubble: "CAPE버블cap", panic_stage_3: "패닉3cap", panic_stage_4: "패닉4cap",
    vix_spread_panic: "VIX패닉cap", yield_defense: "수익률방어cap",
    sector_quadrant_drift: "섹터드리프트", ai_upside_relax: "AI호재완화",
}

function bustPortfolioUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

const PORTFOLIO_FETCH_INIT: RequestInit = {
    cache: "no-store",
    mode: "cors",
    credentials: "omit",
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
        fetch(bustPortfolioUrl(url), { ...PORTFOLIO_FETCH_INIT, signal: ac.signal })
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

const DATA_URL =
    "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json"

type Period = "daily" | "weekly" | "monthly" | "quarterly" | "semi" | "annual"
const PERIOD_LABELS: Record<Period, string> = {
    daily: "일일",
    weekly: "주간",
    monthly: "월간",
    quarterly: "분기",
    semi: "반기",
    annual: "연간",
}
const PERIOD_DESC: Record<Period, string> = {
    daily: "오늘의 시장과 종목 분석",
    weekly: "섹터의 흐름을 읽다 — 주간 전략",
    monthly: "복기와 예측 — 추천 성과 측정",
    quarterly: "거시적 안목 — 실적 시즌 총평",
    semi: "6개월 투자 전략 종합 리뷰",
    annual: "1년 투자 성과 종합 보고서",
}
const PERIOD_REPORT_KEY: Record<Period, string> = {
    daily: "",
    weekly: "weekly_report",
    monthly: "monthly_report",
    quarterly: "quarterly_report",
    semi: "semi_report",
    annual: "annual_report",
}

// PDF 다운로드: vercel-api `/api/reports?period=&type=` → Supabase Storage signed URL
// (구 raw.githubusercontent.com 직접 다운로드는 admin 정책 위반 + .gitignore 누락으로 항상 404 였음)
const DEFAULT_API_BASE = "https://project-yw131.vercel.app"
const SESSION_KEY = "verity_supabase_session"

function _getAccessToken(): string {
    if (typeof window === "undefined") return ""
    try {
        const raw = localStorage.getItem(SESSION_KEY)
        if (!raw) return ""
        const s = JSON.parse(raw)
        return s && typeof s.access_token === "string" ? s.access_token : ""
    } catch {
        return ""
    }
}

interface Props {
    dataUrl: string
    market: "kr" | "us"
    apiBase: string
}

const US_EVENT_KW = ["FOMC", "CPI", "GDP", "PCE", "NFP", "Fed", "고용", "비농업", "소비자물가", "금리결정", "PPI", "ISM", "PMI"]
const KR_EVENT_KW = ["한국", "코스피", "코스닥", "한국은행", "기준금리", "수출", "무역수지", "원달러"]
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

    if (["holding", "earnings", "opportunity", "price_target", "value_chain"].includes(cat)) {
        return false
    }
    return false
}

/* ─── Sub-components (defined outside VerityReport to prevent remount on re-render) ─── */
function SectionIcon({ icon, color }: { icon: string; color: string }) {
    return (
        <div style={{
            width: 28, height: 28, borderRadius: R.sm,
            background: `${color}20`, border: `1px solid ${color}40`,
            display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
        }}>
            <span style={{ color, fontSize: T.cap, fontWeight: T.w_black, fontFamily: font }}>{icon}</span>
        </div>
    )
}

function Section({ icon, iconColor, label, children }: { icon: string; iconColor: string; label: string; children?: any }) {
    return (
        <div style={{ padding: `${S.md}px ${S.lg}px`, background: C.bgElevated, borderRadius: R.md, border: `1px solid ${C.border}` }}>
            <div style={{ display: "flex", alignItems: "center", gap: S.md, marginBottom: S.md }}>
                <SectionIcon icon={icon} color={iconColor} />
                <span style={{ color: iconColor, fontSize: T.body, fontWeight: T.w_bold, fontFamily: font, letterSpacing: "0.02em" }}>{label}</span>
            </div>
            {children}
        </div>
    )
}

function MetricRow({ items }: { items: { label: string; value: string; color?: string }[] }) {
    return (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: S.sm, marginBottom: S.xs }}>
            {items.map((m, i) => (
                <div key={i} style={{ background: C.bgPage, borderRadius: R.md, padding: `${S.sm}px ${S.md}px`, display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med }}>{m.label}</span>
                    <span style={{ color: m.color || C.textPrimary, fontSize: T.body, fontWeight: T.w_bold, ...MONO }}>{m.value}</span>
                </div>
            ))}
        </div>
    )
}

function RingGauge({ value, label, size = 56, color }: { value: number; label: string; size?: number; color: string }) {
    const r = (size - 6) / 2
    const circ = 2 * Math.PI * r
    const offset = circ * (1 - Math.min(value, 100) / 100)
    return (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: S.xs }}>
            <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={C.bgElevated} strokeWidth={5} />
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={5}
                    strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round" />
            </svg>
            <span style={{ color, fontSize: T.sub, fontWeight: T.w_black, fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums", marginTop: -38 }}>{value}</span>
            <span style={{ color: C.textTertiary, fontSize: T.cap, fontFamily: FONT_MONO, letterSpacing: "0.05em", marginTop: 16 }}>{label}</span>
        </div>
    )
}

function BarChart({ items, maxValue }: { items: { label: string; value: number; color: string }[]; maxValue?: number }) {
    const mv = maxValue || Math.max(...items.map(i => Math.abs(i.value)), 1)
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.sm }}>
            {items.map((item, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: S.sm }}>
                    <span style={{ color: C.textSecondary, fontSize: T.cap, fontFamily: font, width: 70, textAlign: "right", flexShrink: 0 }}>{item.label}</span>
                    <div style={{ flex: 1, height: 14, background: C.bgElevated, borderRadius: R.sm, overflow: "hidden" }}>
                        <div style={{ width: `${Math.min(Math.abs(item.value) / mv * 100, 100)}%`, height: "100%", background: item.color, borderRadius: R.sm, transition: "width 0.5s" }} />
                    </div>
                    <span style={{ color: item.color, fontSize: T.cap, fontWeight: T.w_bold, width: 45, textAlign: "right", ...MONO }}>{item.value}%</span>
                </div>
            ))}
        </div>
    )
}

export default function VerityReport(props: Props) {
    const { dataUrl, market, apiBase } = props
    const [data, setData] = useState<any>(null)
    const [period, setPeriod] = useState<Period>("daily")
    const [pdfStatus, setPdfStatus] = useState<
        "idle" | "loading" | "not_found" | "unauthorized" | "forbidden" | "error"
    >("idle")
    const reportRef = useRef<any>(null)

    // 이전 리포트 모달 상태
    const [archiveOpen, setArchiveOpen] = useState(false)
    const [archiveStatus, setArchiveStatus] = useState<
        "idle" | "loading" | "loaded" | "unauthorized" | "forbidden" | "error"
    >("idle")
    const [archiveItems, setArchiveItems] = useState<{ date: string; filename: string }[]>([])
    const [archiveKind, setArchiveKind] = useState<"admin" | "public">("admin")
    const [archiveDownloadingKey, setArchiveDownloadingKey] = useState<string>("")

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchPortfolioJson(dataUrl, ac.signal).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    if (!data) {
        return (
            <div style={{ ...card, minHeight: 200, alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: C.textTertiary, fontSize: T.body, fontFamily: font }}>리포트 로딩 중...</span>
            </div>
        )
    }

    const _resetStatusLater = (ms = 5000) => {
        setTimeout(() => setPdfStatus("idle"), ms)
    }

    const _requestPdf = async (kind: "admin" | "public") => {
        const token = _getAccessToken()
        if (!token) {
            setPdfStatus("unauthorized")
            _resetStatusLater()
            return
        }
        const base = (apiBase || DEFAULT_API_BASE).replace(/\/+$/, "")
        const url = `${base}/api/reports?period=${encodeURIComponent(period)}&type=${kind}`
        // 새창은 사용자 클릭 직후에만 popup-allow 됨. 빈 탭 먼저 열고
        // 비동기 응답이 오면 탭의 location 을 교체.
        const tab = window.open("about:blank", "_blank")
        setPdfStatus("loading")
        try {
            const res = await fetch(url, {
                method: "GET",
                headers: { Authorization: `Bearer ${token}` },
                cache: "no-store",
                mode: "cors",
                credentials: "omit",
            })
            if (res.status === 401) {
                if (tab) tab.close()
                setPdfStatus("unauthorized")
                _resetStatusLater()
                return
            }
            if (res.status === 403) {
                if (tab) tab.close()
                setPdfStatus("forbidden")
                _resetStatusLater()
                return
            }
            if (res.status === 404) {
                if (tab) tab.close()
                setPdfStatus("not_found")
                _resetStatusLater()
                return
            }
            if (!res.ok) {
                if (tab) tab.close()
                setPdfStatus("error")
                _resetStatusLater()
                return
            }
            const body = await res.json()
            const signedUrl = body && typeof body.url === "string" ? body.url : ""
            if (!signedUrl) {
                if (tab) tab.close()
                setPdfStatus("error")
                _resetStatusLater()
                return
            }
            if (tab) {
                tab.location.href = signedUrl
            } else {
                // popup blocker 대응 — 동일 탭 fallback
                window.location.href = signedUrl
            }
            setPdfStatus("idle")
        } catch (e) {
            if (tab) tab.close()
            setPdfStatus("error")
            _resetStatusLater()
        }
    }

    const downloadAdminPdf = () => { _requestPdf("admin") }
    const downloadPublicPdf = () => { _requestPdf("public") }

    // ── 이전 리포트 모달 ──────────────────────────────────────
    const _openArchive = async (kind: "admin" | "public") => {
        const token = _getAccessToken()
        if (!token) {
            setArchiveStatus("unauthorized")
            setArchiveOpen(true)
            return
        }
        setArchiveKind(kind)
        setArchiveOpen(true)
        setArchiveStatus("loading")
        setArchiveItems([])
        const base = (apiBase || DEFAULT_API_BASE).replace(/\/+$/, "")
        const url = `${base}/api/reports?period=${encodeURIComponent(period)}&type=${kind}&action=list`
        try {
            const res = await fetch(url, {
                method: "GET",
                headers: { Authorization: `Bearer ${token}` },
                cache: "no-store",
                mode: "cors",
                credentials: "omit",
            })
            if (res.status === 401) { setArchiveStatus("unauthorized"); return }
            if (res.status === 403) { setArchiveStatus("forbidden"); return }
            if (!res.ok) { setArchiveStatus("error"); return }
            const body = await res.json()
            const items = Array.isArray(body?.items) ? body.items : []
            setArchiveItems(items)
            setArchiveStatus("loaded")
        } catch {
            setArchiveStatus("error")
        }
    }

    const _downloadArchive = async (date: string, kind: "admin" | "public") => {
        const token = _getAccessToken()
        if (!token) return
        const key = `${kind}_${date}`
        setArchiveDownloadingKey(key)
        const base = (apiBase || DEFAULT_API_BASE).replace(/\/+$/, "")
        const url = `${base}/api/reports?period=${encodeURIComponent(period)}&type=${kind}&date=${encodeURIComponent(date)}`
        const tab = window.open("about:blank", "_blank")
        try {
            const res = await fetch(url, {
                method: "GET",
                headers: { Authorization: `Bearer ${token}` },
                cache: "no-store",
                mode: "cors",
                credentials: "omit",
            })
            if (!res.ok) {
                if (tab) tab.close()
                setArchiveDownloadingKey("")
                return
            }
            const body = await res.json()
            const signedUrl = body && typeof body.url === "string" ? body.url : ""
            if (!signedUrl) {
                if (tab) tab.close()
                setArchiveDownloadingKey("")
                return
            }
            if (tab) tab.location.href = signedUrl
            else window.location.href = signedUrl
        } catch {
            if (tab) tab.close()
        } finally {
            setArchiveDownloadingKey("")
        }
    }

    const pdfUpdated = data?.updated_at
        ? new Date(data.updated_at).toLocaleDateString("ko-KR", { month: "numeric", day: "numeric" })
        : ""
    const dailyReportData = data?.daily_report || {}
    const hasDailyReport = Boolean(dailyReportData?.market_summary)
    const hasPdfHint = period === "daily" ? hasDailyReport : Boolean(data?.[PERIOD_REPORT_KEY[period]])

    const gradeLabels: Record<string, string> = { STRONG_BUY: "강력매수", BUY: "매수", WATCH: "관망", CAUTION: "주의", AVOID: "회피" }
    const gradeColors: Record<string, string> = { STRONG_BUY: "#22C55E", BUY: "#B5FF19", WATCH: "#FFD600", CAUTION: "#F59E0B", AVOID: "#EF4444" }

    const updated = data?.updated_at
        ? new Date(data.updated_at).toLocaleDateString("ko-KR", { year: "numeric", month: "long", day: "numeric", weekday: "long" })
        : "—"
    const dateShort = data?.updated_at
        ? new Date(data.updated_at).toLocaleDateString("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit" })
        : ""

    const periodicReport = period !== "daily" ? data[PERIOD_REPORT_KEY[period]] : null
    const isPeriodic = period !== "daily" && periodicReport

    return (
        <div style={card}>
            <style>{`
                @media print {
                    .verity-report-no-print { display: none !important; }
                    body * { visibility: hidden !important; }
                    #verity-report, #verity-report * { visibility: visible !important; }
                    #verity-report {
                        position: absolute !important;
                        left: 0 !important; top: 0 !important; width: 100% !important;
                        border: none !important;
                        -webkit-print-color-adjust: exact !important;
                        print-color-adjust: exact !important;
                    }
                }
            `}</style>

            {/* ===== 이전 리포트 모달 ===== */}
            {archiveOpen && (
                <div className="verity-report-no-print"
                     onClick={() => setArchiveOpen(false)}
                     style={{
                         position: "fixed", inset: 0, background: C.scrim,
                         zIndex: 9999, display: "flex", alignItems: "center",
                         justifyContent: "center", padding: S.lg,
                     }}>
                    <div onClick={(e) => e.stopPropagation()}
                         style={{
                             background: C.bgCard, border: `1px solid ${C.border}`,
                             borderRadius: R.lg, width: "100%", maxWidth: 520,
                             maxHeight: "85vh", display: "flex", flexDirection: "column",
                             overflow: "hidden",
                         }}>
                        {/* 헤더 */}
                        <div style={{
                            padding: `${S.md}px ${S.lg}px`,
                            borderBottom: `1px solid ${C.border}`,
                            display: "flex", justifyContent: "space-between", alignItems: "center",
                        }}>
                            <div>
                                <div style={{ color: C.accent, fontSize: T.cap, fontWeight: T.w_black, fontFamily: FONT_MONO, letterSpacing: "0.12em" }}>
                                    ARCHIVE
                                </div>
                                <div style={{ color: C.textPrimary, fontSize: T.sub, fontWeight: T.w_bold, fontFamily: font, marginTop: 2 }}>
                                    이전 {PERIOD_LABELS[period]} 리포트
                                </div>
                            </div>
                            <button type="button" onClick={() => setArchiveOpen(false)}
                                    style={{
                                        background: "transparent", border: "none",
                                        color: C.textSecondary, fontSize: T.h2, cursor: "pointer",
                                        padding: 0, lineHeight: 1, fontFamily: font,
                                    }}>×</button>
                        </div>

                        {/* admin/public 토글 */}
                        <div style={{
                            display: "flex", gap: 4, padding: `${S.sm}px ${S.lg}px`,
                            borderBottom: `1px solid ${C.border}`, background: C.bgPage,
                        }}>
                            {(["admin", "public"] as const).map((k) => {
                                const active = archiveKind === k
                                return (
                                    <button key={k} type="button" onClick={() => _openArchive(k)}
                                            style={{
                                                background: active ? C.accentSoft : "transparent",
                                                border: `1px solid ${active ? C.accent : C.border}`,
                                                color: active ? C.accent : C.textSecondary,
                                                fontSize: T.cap, fontWeight: T.w_bold, fontFamily: font,
                                                padding: `${S.xs}px ${S.md}px`,
                                                borderRadius: R.sm, cursor: "pointer",
                                            }}>
                                        {k === "admin" ? "관리자" : "일반인"}
                                    </button>
                                )
                            })}
                        </div>

                        {/* 본문 */}
                        <div style={{ overflow: "auto", padding: S.lg, flex: 1 }}>
                            {archiveStatus === "loading" && (
                                <div style={{ color: C.textSecondary, fontSize: T.body, fontFamily: font, textAlign: "center", padding: S.xl }}>
                                    목록 불러오는 중...
                                </div>
                            )}
                            {archiveStatus === "unauthorized" && (
                                <div style={{ color: C.caution, fontSize: T.body, fontFamily: font, textAlign: "center", padding: S.xl }}>
                                    로그인이 필요합니다
                                </div>
                            )}
                            {archiveStatus === "forbidden" && (
                                <div style={{ color: C.danger, fontSize: T.body, fontFamily: font, textAlign: "center", padding: S.xl }}>
                                    관리자 권한이 필요합니다
                                </div>
                            )}
                            {archiveStatus === "error" && (
                                <div style={{ color: C.danger, fontSize: T.body, fontFamily: font, textAlign: "center", padding: S.xl }}>
                                    목록을 불러오지 못했습니다
                                </div>
                            )}
                            {archiveStatus === "loaded" && archiveItems.length === 0 && (
                                <div style={{ color: C.textTertiary, fontSize: T.body, fontFamily: font, textAlign: "center", padding: S.xl }}>
                                    아직 보관된 리포트가 없습니다
                                </div>
                            )}
                            {archiveStatus === "loaded" && archiveItems.length > 0 && (
                                <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                                    {archiveItems.map((it) => {
                                        const key = `${archiveKind}_${it.date}`
                                        const downloading = archiveDownloadingKey === key
                                        return (
                                            <button key={it.date} type="button"
                                                    disabled={downloading}
                                                    onClick={() => _downloadArchive(it.date, archiveKind)}
                                                    style={{
                                                        display: "flex", justifyContent: "space-between", alignItems: "center",
                                                        background: C.bgElevated, border: `1px solid ${C.border}`,
                                                        borderRadius: R.sm, padding: `${S.sm}px ${S.md}px`,
                                                        cursor: downloading ? "wait" : "pointer",
                                                        fontFamily: font, color: C.textPrimary,
                                                        opacity: downloading ? 0.6 : 1,
                                                    }}>
                                                <span style={{ ...MONO, fontSize: T.body }}>{it.date}</span>
                                                <span style={{ color: C.accent, fontSize: T.cap, fontWeight: T.w_bold }}>
                                                    {downloading ? "준비 중..." : "다운로드"}
                                                </span>
                                            </button>
                                        )
                                    })}
                                </div>
                            )}
                        </div>

                        {/* 푸터 */}
                        <div style={{
                            padding: `${S.sm}px ${S.lg}px`, borderTop: `1px solid ${C.border}`,
                            color: C.textTertiary, fontSize: T.cap, fontFamily: font,
                        }}>
                            {archiveItems.length > 0 ? `총 ${archiveItems.length}개` : ""}
                        </div>
                    </div>
                </div>
            )}

            {/* 기간 선택 탭 */}
            <div className="verity-report-no-print" style={periodBar}>
                {(Object.keys(PERIOD_LABELS) as Period[]).map((p) => {
                    const active = period === p
                    return (
                        <button key={p} onClick={() => setPeriod(p)} style={{
                            ...periodBtn,
                            background: active ? C.accent : C.bgElevated,
                            color: active ? "#000" : C.textSecondary,
                            boxShadow: active ? G.accent : "none",
                        }}>
                            {PERIOD_LABELS[p]}
                        </button>
                    )
                })}
            </div>

            <div id="verity-report" ref={reportRef}>
                {/* 헤더 */}
                <div style={header}>
                    <div>
                        <div style={{ display: "flex", alignItems: "center", gap: S.md, marginBottom: S.xs }}>
                            <span style={{ color: C.accent, fontSize: T.cap, fontWeight: T.w_black, letterSpacing: "0.15em", fontFamily: FONT_MONO, textShadow: `0 0 8px rgba(181,255,25,0.35)` }}>VERITY TERMINAL</span>
                            <span style={{ color: C.textTertiary, fontSize: T.cap, fontFamily: FONT_MONO }}>v2.0</span>
                        </div>
                        <span style={{ color: C.textPrimary, fontSize: T.h2, fontWeight: T.w_black, fontFamily: font, display: "block" }}>
                            {isPeriodic ? (periodicReport.title || `${PERIOD_LABELS[period]} 종합 분석 리포트`) : `${PERIOD_LABELS[period]} 종합 분석 리포트`}
                        </span>
                        <span style={{ color: C.textTertiary, fontSize: T.cap, fontFamily: font }}>
                            {isPeriodic && periodicReport._date_range
                                ? `${periodicReport._date_range.start} ~ ${periodicReport._date_range.end} · ${PERIOD_DESC[period]}`
                                : `${updated} · ${PERIOD_DESC[period]}`}
                        </span>
                    </div>
                    <div style={{ display: "flex", alignItems: "flex-end", gap: S.sm, flexDirection: "column" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: S.sm }}>
                            {hasPdfHint ? (
                                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" }}>
                                    <button type="button" className="verity-report-no-print"
                                            title="관리자용 PDF — 점수/등급/VAMS 노골 표시 (본인용)"
                                            onClick={downloadAdminPdf} style={pdfBtn}>
                                        관리자 PDF
                                    </button>
                                    <button type="button" className="verity-report-no-print"
                                            title="일반인용 PDF — 점수/종목명 제거, 시장 해설 위주"
                                            onClick={downloadPublicPdf}
                                            style={{ ...pdfBtn, background: C.bgElevated, color: C.textSecondary }}>
                                        일반인 PDF
                                    </button>
                                    <button type="button" className="verity-report-no-print"
                                            title={`이전 ${PERIOD_LABELS[period]} 리포트 보기 — 일자별 다운로드`}
                                            onClick={() => _openArchive("admin")}
                                            style={{ ...pdfBtn, background: "transparent", color: C.textSecondary, borderColor: C.borderStrong, boxShadow: "none" }}>
                                        이전 리포트 보기
                                    </button>
                                </div>
                            ) : (
                                <span className="verity-report-no-print" style={{ color: C.textTertiary, fontSize: T.cap, fontFamily: font }}>
                                    PDF 준비 중
                                </span>
                            )}
                            <span style={aiBadge}>GEMINI + BRAIN</span>
                        </div>
                        {pdfStatus === "loading" && (
                            <span className="verity-report-no-print" style={{ color: C.textSecondary, fontSize: T.cap, fontFamily: font }}>
                                PDF 준비 중...
                            </span>
                        )}
                        {pdfStatus === "not_found" && (
                            <span className="verity-report-no-print" style={{ color: C.caution, fontSize: T.cap, fontFamily: font }}>
                                PDF 파일이 아직 없습니다 — 장 마감 full 분석 후 자동 생성됩니다
                            </span>
                        )}
                        {pdfStatus === "unauthorized" && (
                            <span className="verity-report-no-print" style={{ color: C.caution, fontSize: T.cap, fontFamily: font }}>
                                로그인이 필요합니다 — 다시 로그인 후 시도해 주세요
                            </span>
                        )}
                        {pdfStatus === "forbidden" && (
                            <span className="verity-report-no-print" style={{ color: C.danger, fontSize: T.cap, fontFamily: font }}>
                                관리자 권한이 필요한 리포트입니다
                            </span>
                        )}
                        {pdfStatus === "error" && (
                            <span className="verity-report-no-print" style={{ color: C.danger, fontSize: T.cap, fontFamily: font }}>
                                PDF 다운로드 실패 — 잠시 후 다시 시도해 주세요
                            </span>
                        )}
                    </div>
                </div>

                {/* ===== 정기 리포트 뷰 ===== */}
                {isPeriodic ? (
                    <div style={bodyWrap}>
                        {/* 핵심 요약 배너 */}
                        {periodicReport.executive_summary && (
                            <div style={{ padding: `${S.lg}px ${S.xl}px`, background: `linear-gradient(135deg, rgba(181,255,25,0.08), rgba(181,255,25,0.02))`, borderRadius: R.md, border: `1px solid rgba(181,255,25,0.25)` }}>
                                <span style={{ color: C.accent, fontSize: T.sub, fontWeight: T.w_black, fontFamily: font, lineHeight: T.lh_normal }}>
                                    {periodicReport.executive_summary}
                                </span>
                            </div>
                        )}

                        {/* 성과표: 지난 실현 + 이번 기대수익률 */}
                        {(() => {
                            const stats = periodicReport._raw_stats || {}
                            const expected = (periodicReport as any).expected_return || {}
                            const hasRealized = (stats.total_buy_recs || 0) > 0
                            const hasExpected = (expected.count || 0) > 0
                            if (!hasRealized && !hasExpected) return null
                            const retVal = stats.avg_return_pct ?? 0
                            const expVal = expected.avg_upside_pct ?? 0
                            const retCol = retVal >= 0 ? C.up : C.down
                            const expCol = expVal >= 0 ? C.accent : C.danger
                            const topPick = expected.top_picks?.[0]
                            return (
                                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: S.md }}>
                                    <div style={{ padding: `${S.lg}px ${S.xl}px`, background: C.bgElevated, borderRadius: R.md, border: `1px solid ${C.border}` }}>
                                        <div style={{ color: C.textSecondary, fontSize: T.cap, fontWeight: T.w_bold, letterSpacing: "0.05em", marginBottom: S.sm, fontFamily: font }}>
                                            지난 기간 실현 수익률
                                        </div>
                                        {hasRealized ? (
                                            <>
                                                <div style={{ color: retCol, fontSize: T.h1 + 4, fontWeight: T.w_black, letterSpacing: "-0.02em", lineHeight: T.lh_tight, ...MONO }}>
                                                    {retVal >= 0 ? "+" : ""}{Number(retVal).toFixed(1)}%
                                                </div>
                                                <div style={{ color: C.textSecondary, fontSize: T.cap, fontFamily: font, marginTop: S.sm, lineHeight: T.lh_normal }}>
                                                    <b style={{ color: C.textPrimary, ...MONO }}>{stats.total_buy_recs}</b>종목 매수 추천 · 적중률 <b style={{ color: (stats.hit_rate_pct ?? 0) >= 50 ? C.success : C.watch, ...MONO }}>{stats.hit_rate_pct ?? 0}%</b>
                                                </div>
                                            </>
                                        ) : (
                                            <div style={{ color: C.textTertiary, fontSize: T.body, fontFamily: font, padding: `${S.md}px 0` }}>데이터 누적 중</div>
                                        )}
                                    </div>
                                    <div style={{ padding: `${S.lg}px ${S.xl}px`, background: `linear-gradient(135deg, rgba(181,255,25,0.10), ${C.bgElevated})`, borderRadius: R.md, border: `1px solid rgba(181,255,25,0.25)`, boxShadow: G.accentSoft }}>
                                        <div style={{ color: C.accent, fontSize: T.cap, fontWeight: T.w_bold, letterSpacing: "0.05em", marginBottom: S.sm, fontFamily: font }}>
                                            이번 리포트 기대수익률
                                        </div>
                                        {hasExpected ? (
                                            <>
                                                <div style={{ color: expCol, fontSize: T.h1 + 4, fontWeight: T.w_black, letterSpacing: "-0.02em", lineHeight: T.lh_tight, ...MONO }}>
                                                    {expVal >= 0 ? "+" : ""}{Number(expVal).toFixed(1)}%
                                                </div>
                                                <div style={{ color: C.textSecondary, fontSize: T.cap, fontFamily: font, marginTop: S.sm, lineHeight: T.lh_normal }}>
                                                    <b style={{ color: C.textPrimary, ...MONO }}>{expected.count}</b>종목 · 최대 <b style={{ color: C.accent, ...MONO }}>+{Number(expected.max_upside_pct ?? 0).toFixed(1)}%</b>
                                                    {topPick && <> · TOP <b style={{ color: C.textPrimary }}>{topPick.name}</b> <span style={{ color: C.accent, fontWeight: T.w_bold, ...MONO }}>+{Number(topPick.upside_pct).toFixed(1)}%</span></>}
                                                </div>
                                            </>
                                        ) : (
                                            <div style={{ color: C.textTertiary, fontSize: T.body, fontFamily: font, padding: `${S.md}px 0` }}>현재 매수 추천 종목 없음</div>
                                        )}
                                        <div style={{ color: C.textTertiary, fontSize: T.cap, fontFamily: font, marginTop: S.md, lineHeight: T.lh_normal }}>
                                            ※ 목표가 대비 업사이드 (실현 보장 아님)
                                        </div>
                                    </div>
                                </div>
                            )
                        })()}

                        {/* 추천 성과 복기 */}
                        {periodicReport._raw_stats && (
                            <Section icon="📊" iconColor={C.success} label={`추천 성과 복기 — 적중률 ${periodicReport._raw_stats.hit_rate_pct || 0}%`}>
                                <MetricRow items={[
                                    { label: "BUY 추천", value: `${periodicReport._raw_stats.total_buy_recs || 0}건` },
                                    { label: "적중률", value: `${periodicReport._raw_stats.hit_rate_pct || 0}%`, color: (periodicReport._raw_stats.hit_rate_pct || 0) >= 50 ? C.up : C.down },
                                    { label: "평균 수익률", value: `${(periodicReport._raw_stats.avg_return_pct || 0) >= 0 ? "+" : ""}${periodicReport._raw_stats.avg_return_pct || 0}%`, color: (periodicReport._raw_stats.avg_return_pct || 0) >= 0 ? C.up : C.down },
                                    { label: "포트폴리오", value: `${(periodicReport._raw_stats.portfolio_return || 0) >= 0 ? "+" : ""}${periodicReport._raw_stats.portfolio_return || 0}%`, color: (periodicReport._raw_stats.portfolio_return || 0) >= 0 ? C.up : C.down },
                                ]} />
                                {periodicReport._raw_stats.best_picks?.length > 0 && (
                                    <div style={{ marginTop: S.md }}>
                                        <span style={{ color: C.success, fontSize: T.cap, fontWeight: T.w_bold, display: "block", marginBottom: S.sm }}>최고 수익 종목</span>
                                        {periodicReport._raw_stats.best_picks.slice(0, 5).map((s: any, i: number) => (
                                            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: `${S.sm}px 0`, borderBottom: `1px solid ${C.border}` }}>
                                                <span style={{ color: C.textPrimary, fontSize: T.body, fontFamily: font }}>{i + 1}. {s.name}</span>
                                                <div style={{ display: "flex", gap: S.md, alignItems: "center" }}>
                                                    <span style={{ color: C.textSecondary, fontSize: T.cap, ...MONO }}>브레인 {s.orig_brain_score}</span>
                                                    <span style={{ color: s.return_pct >= 0 ? C.up : C.down, fontSize: T.body, fontWeight: T.w_black, ...MONO }}>
                                                        {s.return_pct >= 0 ? "+" : ""}{s.return_pct}%
                                                    </span>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                                {periodicReport._raw_stats.worst_picks?.length > 0 && (
                                    <div style={{ marginTop: S.md }}>
                                        <span style={{ color: C.danger, fontSize: T.cap, fontWeight: T.w_bold, display: "block", marginBottom: S.sm }}>손실 종목</span>
                                        {periodicReport._raw_stats.worst_picks.map((s: any, i: number) => (
                                            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: `${S.sm}px 0`, borderBottom: `1px solid ${C.border}` }}>
                                                <span style={{ color: C.textSecondary, fontSize: T.body, fontFamily: font }}>{s.name}</span>
                                                <span style={{ color: C.danger, fontSize: T.body, fontWeight: T.w_black, ...MONO }}>{s.return_pct}%</span>
                                            </div>
                                        ))}
                                    </div>
                                )}
                                {periodicReport.performance_review && (
                                    <p style={{ ...sectionText, marginTop: S.md, paddingTop: S.md, borderTop: `1px solid ${C.border}` }}>{periodicReport.performance_review}</p>
                                )}
                            </Section>
                        )}

                        {/* 섹터 동향 분석 */}
                        {periodicReport._raw_stats?.top3_sectors?.length > 0 && (
                            <Section icon="📈" iconColor="#A78BFA" label="섹터 동향 — 돈의 흐름">
                                <BarChart items={periodicReport._raw_stats.top3_sectors.map((s: any) => ({
                                    label: s.name,
                                    value: s.avg_change_pct,
                                    color: s.avg_change_pct >= 0 ? C.up : C.down,
                                }))} />
                                {periodicReport.sector_analysis && (
                                    <p style={{ ...sectionText, marginTop: S.md }}>{periodicReport.sector_analysis}</p>
                                )}
                            </Section>
                        )}

                        {/* 메타 분석 — 데이터 소스 정확도 */}
                        {periodicReport._raw_stats?.meta_findings?.length > 0 && (
                            <Section icon="🔬" iconColor={C.info} label="메타 분석 — 어떤 지표가 맞았나?">
                                <BarChart items={periodicReport._raw_stats.meta_findings.map((f: any) => {
                                    const labels: Record<string, string> = {
                                        multi_factor: "멀티팩터", consensus: "내부모델합의", timing: "타이밍",
                                        prediction: "XGBoost", sentiment: "뉴스 감성", brain: "브레인",
                                    }
                                    return {
                                        label: labels[f.source] || f.source,
                                        value: f.accuracy_pct,
                                        color: f.accuracy_pct >= 60 ? C.success : f.accuracy_pct >= 50 ? C.watch : C.danger,
                                    }
                                })} maxValue={100} />
                                {periodicReport.meta_insight && (
                                    <p style={{ ...sectionText, marginTop: S.md, padding: `${S.md}px ${S.lg}px`, background: C.bgPage, borderRadius: R.md, border: `1px solid ${C.border}` }}>
                                        {periodicReport.meta_insight}
                                    </p>
                                )}
                            </Section>
                        )}

                        {/* 브레인 정확도 평가 */}
                        {periodicReport._raw_stats?.brain_grades && Object.keys(periodicReport._raw_stats.brain_grades).length > 0 && (
                            <Section icon="🧠" iconColor={C.accent} label="AI 브레인 등급별 실적">
                                <div style={{ display: "flex", flexWrap: "wrap", gap: S.sm, marginBottom: S.md }}>
                                    {Object.entries(periodicReport._raw_stats.brain_grades as Record<string, any>).map(([grade, stats]) => (
                                        <div key={grade} style={{
                                            padding: `${S.sm}px ${S.md}px`, borderRadius: R.md, background: C.bgPage, border: `1px solid ${gradeColors[grade] || C.border}30`,
                                            display: "flex", flexDirection: "column", gap: 2, minWidth: 80,
                                        }}>
                                            <span
                                                style={{ color: gradeColors[grade] || C.textSecondary, fontSize: T.cap, fontWeight: T.w_bold, fontFamily: font, cursor: grade === "AVOID" ? "help" : "default" }}
                                                title={grade === "AVOID" ? AVOID_TOOLTIP : undefined}
                                            >{gradeLabels[grade] || grade}</span>
                                            <span style={{ color: C.textPrimary, fontSize: T.sub, fontWeight: T.w_black, ...MONO }}>{stats.avg_return >= 0 ? "+" : ""}{stats.avg_return}%</span>
                                            <span style={{ color: C.textTertiary, fontSize: T.cap, ...MONO }}>적중 {stats.hit_rate}% · {stats.count}종목</span>
                                        </div>
                                    ))}
                                </div>
                                {periodicReport.brain_review && (
                                    <p style={sectionText}>{periodicReport.brain_review}</p>
                                )}
                            </Section>
                        )}

                        {/* 매크로 전망 */}
                        {periodicReport.macro_outlook && (
                            <Section icon="M" iconColor="#A78BFA" label="매크로 환경 변화">
                                <p style={sectionText}>{periodicReport.macro_outlook}</p>
                            </Section>
                        )}

                        {/* 전략 제안 */}
                        {periodicReport.strategy && (
                            <Section icon="T" iconColor={C.success} label={`다음 ${PERIOD_LABELS[period]} 전략`}>
                                <p style={sectionText}>{periodicReport.strategy}</p>
                            </Section>
                        )}

                        {/* 리스크 주의 */}
                        {periodicReport.risk_watch && (
                            <Section icon="!" iconColor={C.danger} label="리스크 주의">
                                <p style={sectionText}>{periodicReport.risk_watch}</p>
                            </Section>
                        )}
                    </div>
                ) : (
                    /* ===== 일일 리포트 뷰 (기존) ===== */
                    <DailyReportView data={data} market={market} Section={Section} MetricRow={MetricRow} RingGauge={RingGauge} gradeLabels={gradeLabels} gradeColors={gradeColors} />
                )}

                {/* 미생성 안내 (정기 리포트 데이터 없는 경우) */}
                {period !== "daily" && !periodicReport && (
                    <div style={{ padding: `${S.xxxl}px ${S.xl}px`, textAlign: "center" }}>
                        <div style={{ color: C.textTertiary, fontSize: 40, marginBottom: S.md }}>📋</div>
                        <span style={{ color: C.textTertiary, fontSize: T.sub, fontFamily: font, display: "block", marginBottom: S.sm }}>
                            {PERIOD_LABELS[period]} 리포트가 아직 생성되지 않았습니다
                        </span>
                        <span style={{ color: C.textTertiary, fontSize: T.body, fontFamily: font, display: "block" }}>
                            데이터가 충분히 누적되면 자동 생성됩니다
                        </span>
                    </div>
                )}

                {/* 푸터 */}
                <div style={footer}>
                    <span style={{ color: C.textTertiary, fontSize: T.cap, fontFamily: font, display: "block", lineHeight: T.lh_normal }}>
                        본 리포트는 VERITY AI가 자동 생성한 {PERIOD_LABELS[period]} 종합 분석이며, 투자 판단의 참고용입니다. <span style={MONO}>{dateShort}</span>
                    </span>
                    <span className="verity-report-no-print" style={{ color: C.textTertiary, fontSize: T.cap, fontFamily: font, display: "block", marginTop: S.xs }}>
                        PDF는 매일 장 마감 full 분석 완료 후 자동 생성됩니다
                    </span>
                </div>
            </div>
        </div>
    )
}

function _MiniSpark({ data, color = C.textSecondary, w = 80, h = 20 }: { data: number[]; color?: string; w?: number; h?: number }) {
    if (!data || data.length < 2) return null
    const mn = Math.min(...data), mx = Math.max(...data), rng = mx - mn || 1
    const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - mn) / rng) * h}`).join(" ")
    return (
        <svg width={w} height={h} style={{ display: "block" }}>
            <polyline points={pts} fill="none" stroke={color} strokeWidth={1.2} strokeLinejoin="round" strokeLinecap="round" />
        </svg>
    )
}

function MacroSparklines({ macro }: { macro: any }) {
    const fred = macro?.fred || {}
    const items: { label: string; spark: number[]; color: string }[] = []
    if (fred.dgs10?.sparkline?.length > 2) items.push({ label: "US 10Y", spark: fred.dgs10.sparkline, color: "#38BDF8" })
    if (fred.vix_close?.sparkline?.length > 2) items.push({ label: "VIX", spark: fred.vix_close.sparkline, color: C.danger })
    if (fred.hy_spread?.sparkline?.length > 2) items.push({ label: "HY Spread", spark: fred.hy_spread.sparkline, color: C.caution })
    if (macro.sp500?.sparkline_weekly?.length > 2) items.push({ label: "S&P 500", spark: macro.sp500.sparkline_weekly, color: C.success })
    if (macro.nasdaq?.sparkline_weekly?.length > 2) items.push({ label: "NASDAQ", spark: macro.nasdaq.sparkline_weekly, color: C.accent })
    if (macro.usd_krw?.sparkline_weekly?.length > 2) items.push({ label: "USD/KRW", spark: macro.usd_krw.sparkline_weekly, color: "#A78BFA" })
    if (items.length === 0) return null
    return (
        <div style={{ marginTop: S.sm, display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: S.sm }}>
            {items.map((it, i) => (
                <div key={i} style={{ background: C.bgPage, borderRadius: R.sm, padding: `${S.sm}px ${S.md}px` }}>
                    <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med, fontFamily: FONT_MONO }}>{it.label}</span>
                    <_MiniSpark data={it.spark.slice(-13)} color={it.color} w={70} h={18} />
                </div>
            ))}
        </div>
    )
}

function DailyReportView({ data, market, Section, MetricRow, RingGauge, gradeLabels, gradeColors }: any) {
    const report = data?.daily_report || {}
    const macro = data?.macro || {}
    const mood = macro.market_mood || {}
    const brain = data?.verity_brain || {}
    const marketBrain = brain.market_brain || {}
    const macroOv = brain.macro_override || {}
    const recs: any[] = data?.recommendations || []
    const vams = data?.vams || {}
    const sectors: any[] = data?.sectors || []
    const krHeadlines: any[] = data?.headlines || []
    const usHeadlines: any[] = data?.us_headlines || []
    const allHeadlines = [...krHeadlines, ...usHeadlines.filter((u: any) => !krHeadlines.some((k: any) => k.title === u.title))]
    const isUS = market === "us"
    const briefing = data?.briefing || {}
    const allEvents: any[] = data?.global_events || []
    const events: any[] = allEvents.filter((e) => (isUS ? _isUSEvent(e) : !_isUSEvent(e)))
    const allAlerts: any[] = briefing.alerts || []
    const usTokens = new Set<string>()
    const krTokens = new Set<string>()
    for (const r of recs) {
        const ticker = String(r?.ticker || "").trim().toLowerCase()
        const name = String(r?.name || "").trim().toLowerCase()
        const target = _isUSStock(r) ? usTokens : krTokens
        if (ticker.length >= 1) target.add(ticker)
        if (name.length >= 2) target.add(name)
    }
    const scopedAlerts: any[] = allAlerts.filter((a) => (isUS ? _isUSAlert(a, usTokens, krTokens) : !_isUSAlert(a, usTokens, krTokens)))
    const briefingHeadline = scopedAlerts[0]?.message || briefing.headline
    const briefingActions: string[] = scopedAlerts.map((a) => String(a?.action || "").trim()).filter(Boolean).slice(0, 3)
    const rotation = data?.sector_rotation || {}
    const holdings: any[] = vams.holdings || []
    const topPicks: any[] = marketBrain.top_picks || []

    const brainScore = marketBrain.avg_brain_score ?? null
    const factScore = marketBrain.avg_fact_score ?? null
    const sentScore = marketBrain.avg_sentiment_score ?? null
    const avgVci = marketBrain.avg_vci ?? 0
    const gradeDist: Record<string, number> = marketBrain.grade_distribution || {}

    const totalReturn = vams.total_return_pct || 0
    const totalAsset = vams.total_asset || 0
    const cash = vams.cash || 0

    const krRecs = recs.filter((r: any) => !_isUSStock(r))
    const usRecs = recs.filter(_isUSStock)
    const dualRows = recs.filter((r: any) => !!r.dual_consensus)
    const dualAgree = dualRows.filter((r: any) => r.dual_consensus?.agreement).length
    const dualManual = dualRows.filter((r: any) => r.dual_consensus?.manual_review_required).length
    const dualConflictHigh = dualRows.filter((r: any) => r.dual_consensus?.conflict_level === "high").length

    const _isUSSector = (s: any) => (s.market || "").toUpperCase() === "US"
    const krSectors = sectors.filter((s: any) => !_isUSSector(s))
    const usSectors = sectors.filter(_isUSSector)
    const topKrSectors = [...krSectors].sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0)).slice(0, 5)
    const bottomKrSectors = [...krSectors].sort((a, b) => (a.change_pct || 0) - (b.change_pct || 0)).slice(0, 3)
    const topUsSectors = [...usSectors].sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0)).slice(0, 5)
    const bottomUsSectors = [...usSectors].sort((a, b) => (a.change_pct || 0) - (b.change_pct || 0)).slice(0, 3)

    const posHeadlines = allHeadlines.filter((h) => h.sentiment === "positive").length
    const negHeadlines = allHeadlines.filter((h) => h.sentiment === "negative").length

    const hasReport = report.market_summary || report.market_analysis

    return (
        <>
            {/* 매크로 오버라이드 */}
            {macroOv.mode && (() => {
                const m = String(macroOv.mode).toLowerCase()
                const isPanic = m === "panic"
                const isYield = m === "yield_defense"
                const bg = isPanic ? "rgba(239,68,68,0.08)" : isYield ? "rgba(56,189,248,0.08)" : "rgba(234,179,8,0.08)"
                const bd = isPanic ? C.danger : isYield ? "#38BDF8" : "#EAB308"
                const fg = isPanic ? C.danger : isYield ? "#38BDF8" : "#EAB308"
                const title = isPanic ? "PANIC MODE" : isYield ? "YIELD DEFENSE" : "EUPHORIA MODE"
                const sub = macroOv.reason || macroOv.message || ""
                return (
                    <div style={{ padding: `${S.md}px ${S.xl}px`, background: bg, borderBottom: `2px solid ${bd}`, boxShadow: isPanic ? G.danger : "none" }}>
                        <span style={{ color: fg, fontSize: T.body, fontWeight: T.w_black, fontFamily: font, letterSpacing: "0.05em" }}>{title} — {sub}</span>
                    </div>
                )
            })()}

            {hasReport && (
                <div style={{ padding: `${S.lg}px ${S.xl}px`, background: `linear-gradient(135deg, rgba(181,255,25,0.08), rgba(181,255,25,0.02))`, borderBottom: `1px solid ${C.border}` }}>
                    <span style={{ color: C.accent, fontSize: T.title, fontWeight: T.w_black, fontFamily: font, lineHeight: T.lh_normal }}>{report.market_summary || "—"}</span>
                </div>
            )}

            <div style={bodyWrap}>
                {brainScore !== null && (
                    <Section icon="🧠" iconColor={C.accent} label="Verity Brain 종합">
                        <MetricRow items={[
                            { label: "종합 점수", value: `${brainScore}`, color: brainScore >= 65 ? C.accent : brainScore >= 45 ? C.watch : C.danger },
                            { label: "팩트", value: `${factScore ?? "—"}`, color: C.success },
                            { label: "심리", value: `${sentScore ?? "—"}`, color: C.info },
                            { label: "VCI", value: `${avgVci >= 0 ? "+" : ""}${avgVci?.toFixed(1)}`, color: avgVci > 15 ? C.accent : avgVci < -15 ? C.danger : C.textSecondary },
                        ]} />
                        <div style={{ display: "flex", gap: S.sm, flexWrap: "wrap", marginTop: S.sm }}>
                            {Object.entries(gradeDist).map(([g, count]) => count > 0 ? (
                                <span key={g} style={{
                                    fontSize: T.cap, fontWeight: T.w_bold, fontFamily: font, padding: `3px ${S.sm}px`, borderRadius: R.sm,
                                    background: `${gradeColors[g]}15`, color: gradeColors[g],
                                }}>{gradeLabels[g]} <span style={MONO}>{count}</span></span>
                            ) : null)}
                        </div>
                        {topPicks.length > 0 && (
                            <div style={{ marginTop: S.md, display: "flex", flexDirection: "column", gap: S.xs }}>
                                <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_semi }}>탑픽</span>
                                {topPicks.slice(0, 5).map((s: any, i: number) => (
                                    <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: `${S.sm}px 0`, borderBottom: `1px solid ${C.border}` }}>
                                        <span style={{ color: C.textPrimary, fontSize: T.body, fontFamily: font }}>{i + 1}. {s.name}</span>
                                        <span
                                            style={{ color: gradeColors[s.grade] || C.textSecondary, fontSize: T.body, fontWeight: T.w_black, fontFamily: font, cursor: s.grade === "AVOID" ? "help" : "default" }}
                                            title={s.grade === "AVOID" ? AVOID_TOOLTIP : undefined}
                                        ><span style={MONO}>{s.brain_score}</span> · {gradeLabels[s.grade] || s.grade}{Array.isArray(s.overrides_applied) && s.overrides_applied.length > 0 ? ` · ${(s.overrides_applied as string[]).map((o) => OVERRIDE_LABELS[o] || o).join("·")}` : ""}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </Section>
                )}

                {dualRows.length > 0 && (
                    <Section icon="H" iconColor="#38BDF8" label="듀얼 모델 합의 상태">
                        <MetricRow items={[
                            { label: "합의율", value: `${Math.round((dualAgree / Math.max(dualRows.length, 1)) * 100)}%`, color: dualAgree / Math.max(dualRows.length, 1) >= 0.7 ? C.success : C.watch },
                            { label: "수동검토", value: `${dualManual}종목`, color: dualManual > 0 ? C.danger : C.success },
                            { label: "High 충돌", value: `${dualConflictHigh}종목`, color: dualConflictHigh > 0 ? C.danger : C.textSecondary },
                            { label: "분석대상", value: `${dualRows.length}종목`, color: "#38BDF8" },
                        ]} />
                        {dualRows
                            .filter((r: any) => r.dual_consensus?.manual_review_required)
                            .slice(0, 5)
                            .map((s: any, i: number) => {
                                const dc = s.dual_consensus || {}
                                return (
                                    <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: `${S.sm}px 0`, borderBottom: `1px solid ${C.border}` }}>
                                        <div>
                                            <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi, fontFamily: font }}>{s.name}</span>
                                            <span style={{ color: C.textTertiary, fontSize: T.cap, marginLeft: S.sm, ...MONO }}>{s.ticker}</span>
                                        </div>
                                        <span style={{ color: C.danger, fontSize: T.cap, fontWeight: T.w_bold, fontFamily: font }}>
                                            G:{dc.gemini_recommendation} / C:{dc.claude_recommendation} ({dc.conflict_level})
                                        </span>
                                    </div>
                                )
                            })}
                    </Section>
                )}

                {report.market_analysis && (
                    <Section icon="A" iconColor={C.info} label="시장 분석">
                        <p style={sectionText}>{report.market_analysis}</p>
                    </Section>
                )}

                <Section icon="M" iconColor="#A78BFA" label="글로벌 매크로">
                    <MetricRow items={[
                        { label: "시장 분위기", value: mood.label || "—", color: (mood.score || 50) >= 60 ? C.success : (mood.score || 50) <= 40 ? C.danger : C.watch },
                        { label: "VIX", value: `${macro.vix?.value || "—"}`, color: (macro.vix?.value || 0) > 25 ? C.danger : C.success },
                        { label: "US 10Y", value: macro.fred?.dgs10?.value != null ? `${macro.fred.dgs10.value}%` : "—", color: "#38BDF8" },
                        { label: "USD/KRW", value: `${macro.usd_krw?.value?.toLocaleString() || "—"}원` },
                    ]} />
                    <MetricRow items={[
                        { label: "S&P 500", value: `${(macro.sp500?.change_pct || 0) >= 0 ? "+" : ""}${(macro.sp500?.change_pct || 0).toFixed(2)}%`, color: (macro.sp500?.change_pct || 0) >= 0 ? C.up : C.down },
                        { label: "NASDAQ", value: `${(macro.nasdaq?.change_pct || 0) >= 0 ? "+" : ""}${(macro.nasdaq?.change_pct || 0).toFixed(2)}%`, color: (macro.nasdaq?.change_pct || 0) >= 0 ? C.up : C.down },
                        { label: "Gold", value: `$${macro.gold?.value?.toLocaleString() || "—"}` },
                        { label: "WTI", value: `$${macro.wti_oil?.value || "—"}` },
                    ]} />
                    {/* 확장 FRED 지표 */}
                    {(macro.fred?.unemployment_rate || macro.fred?.consumer_sentiment || macro.fred?.hy_spread) && (
                        <MetricRow items={[
                            { label: "실업률", value: macro.fred?.unemployment_rate?.pct != null ? `${macro.fred.unemployment_rate.pct}%` : "—", color: (macro.fred?.unemployment_rate?.pct || 0) > 5 ? C.danger : C.success },
                            { label: "소비자 심리", value: macro.fred?.consumer_sentiment?.value != null ? `${macro.fred.consumer_sentiment.value}` : "—", color: (macro.fred?.consumer_sentiment?.value || 50) >= 70 ? C.success : (macro.fred?.consumer_sentiment?.value || 50) <= 50 ? C.danger : C.watch },
                            { label: "HY 스프레드", value: macro.fred?.hy_spread?.pct != null ? `${macro.fred.hy_spread.pct}%` : "—", color: (macro.fred?.hy_spread?.pct || 0) > 5 ? C.danger : C.success },
                            { label: "기대 인플레", value: macro.fred?.breakeven_inflation_10y?.pct != null ? `${macro.fred.breakeven_inflation_10y.pct}%` : "—" },
                        ]} />
                    )}
                    {macro.fred?.fed_balance_sheet?.trillions_usd != null && (
                        <MetricRow items={[
                            { label: "Fed B/S", value: `$${macro.fred.fed_balance_sheet.trillions_usd}T`, color: "#A78BFA" },
                            { label: "4주 변동", value: macro.fred.fed_balance_sheet.change_4w_pct != null ? `${macro.fred.fed_balance_sheet.change_4w_pct > 0 ? "+" : ""}${macro.fred.fed_balance_sheet.change_4w_pct}%` : "—", color: (macro.fred?.fed_balance_sheet?.change_4w_pct || 0) > 0 ? C.up : C.down },
                            { label: "리세션 확률", value: macro.fred?.us_recession_smoothed_prob?.pct != null ? `${macro.fred.us_recession_smoothed_prob.pct}%` : "—", color: (macro.fred?.us_recession_smoothed_prob?.pct || 0) > 20 ? C.danger : C.success },
                        ]} />
                    )}
                    <MacroSparklines macro={macro} />
                </Section>

                {report.strategy && (
                    <Section icon="T" iconColor={C.success} label="투자 전략">
                        <p style={sectionText}>{report.strategy}</p>
                    </Section>
                )}

                {holdings.length > 0 && (
                    <Section icon="P" iconColor={C.caution} label="포트폴리오 현황">
                        <MetricRow items={[
                            { label: "총 자산", value: totalAsset ? `${totalAsset.toLocaleString()}원` : "—" },
                            { label: "수익률", value: `${totalReturn >= 0 ? "+" : ""}${totalReturn.toFixed(2)}%`, color: totalReturn >= 0 ? C.up : C.down },
                            { label: "현금", value: cash ? `${cash.toLocaleString()}원` : "—" },
                            { label: "보유 종목", value: `${holdings.length}개` },
                        ]} />
                        {holdings.map((h: any, i: number) => {
                            const pct = h.return_pct || 0
                            return (
                                <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: `${S.sm}px 0`, borderBottom: `1px solid ${C.border}` }}>
                                    <span style={{ color: C.textPrimary, fontSize: T.body, fontFamily: font }}>{h.name} · <span style={MONO}>{h.quantity}주</span></span>
                                    <span style={{ color: pct >= 0 ? C.up : C.down, fontSize: T.body, fontWeight: T.w_bold, ...MONO }}>{pct >= 0 ? "+" : ""}{pct.toFixed(2)}%</span>
                                </div>
                            )
                        })}
                    </Section>
                )}

                <Section icon="R" iconColor={C.accent} label={`추천 종목 요약 (KR ${krRecs.length} · US ${usRecs.length})`}>
                    {krRecs.length > 0 && (
                        <>
                            <div style={{ display: "flex", alignItems: "center", gap: S.sm, marginBottom: S.sm }}>
                                <span style={{ padding: `2px ${S.sm}px`, borderRadius: R.sm, background: C.accentSoft, color: C.accent, fontSize: T.cap, fontWeight: T.w_bold, fontFamily: font }}>국장</span>
                                <span style={{ color: C.textSecondary, fontSize: T.cap, fontFamily: font }}>
                                    매수 <span style={MONO}>{krRecs.filter((r: any) => r.recommendation === "BUY").length}</span> · 회피 <span style={MONO}>{krRecs.filter((r: any) => r.recommendation === "AVOID").length}</span>
                                </span>
                            </div>
                            {krRecs.filter((r: any) => r.recommendation === "BUY").slice(0, 5).map((s: any, i: number) => (
                                <div key={`kr-${i}`} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: `${S.sm}px 0`, borderBottom: `1px solid ${C.border}` }}>
                                    <div>
                                        <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi, fontFamily: font }}>{s.name}</span>
                                        <span style={{ color: C.textTertiary, fontSize: T.cap, marginLeft: S.sm, ...MONO }}>{s.ticker}</span>
                                    </div>
                                    <div style={{ display: "flex", gap: S.sm, alignItems: "center" }}>
                                        <span style={{ color: C.textSecondary, fontSize: T.cap, ...MONO }}>{s.price?.toLocaleString()}원</span>
                                        <span style={{ color: C.accent, fontSize: T.body, fontWeight: T.w_bold, ...MONO }}>{s.multi_factor?.multi_score || s.safety_score || 0}점</span>
                                    </div>
                                </div>
                            ))}
                        </>
                    )}
                    {usRecs.length > 0 && (
                        <>
                            <div style={{ display: "flex", alignItems: "center", gap: S.sm, marginBottom: S.sm, marginTop: krRecs.length > 0 ? S.md : 0 }}>
                                <span style={{ padding: `2px ${S.sm}px`, borderRadius: R.sm, background: "rgba(91,169,255,0.12)", color: C.info, fontSize: T.cap, fontWeight: T.w_bold, fontFamily: font }}>미장</span>
                                <span style={{ color: C.textSecondary, fontSize: T.cap, fontFamily: font }}>
                                    매수 <span style={MONO}>{usRecs.filter((r: any) => r.recommendation === "BUY").length}</span> · 회피 <span style={MONO}>{usRecs.filter((r: any) => r.recommendation === "AVOID").length}</span>
                                </span>
                            </div>
                            {usRecs.filter((r: any) => r.recommendation === "BUY").slice(0, 5).map((s: any, i: number) => (
                                <div key={`us-${i}`} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: `${S.sm}px 0`, borderBottom: `1px solid ${C.border}` }}>
                                    <div>
                                        <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi, fontFamily: font }}>{s.name}</span>
                                        <span style={{ color: C.textTertiary, fontSize: T.cap, marginLeft: S.sm, ...MONO }}>{s.ticker}</span>
                                    </div>
                                    <div style={{ display: "flex", gap: S.sm, alignItems: "center" }}>
                                        <span style={{ color: C.textSecondary, fontSize: T.cap, ...MONO }}>${s.price?.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                                        <span style={{ color: C.info, fontSize: T.body, fontWeight: T.w_bold, ...MONO }}>{s.multi_factor?.multi_score || s.safety_score || 0}점</span>
                                    </div>
                                </div>
                            ))}
                        </>
                    )}
                    {krRecs.length === 0 && usRecs.length === 0 && (
                        <span style={{ color: C.textTertiary, fontSize: T.body, fontFamily: font }}>추천 종목 없음</span>
                    )}
                </Section>

                {sectors.length > 0 && (
                    <Section icon="S" iconColor="#A78BFA" label="섹터 동향">
                        {krSectors.length > 0 && (
                            <>
                                <div style={{ display: "flex", alignItems: "center", gap: S.sm, marginBottom: S.sm }}>
                                    <span style={{ padding: `2px ${S.sm}px`, borderRadius: R.sm, background: C.accentSoft, color: C.accent, fontSize: T.cap, fontWeight: T.w_bold, fontFamily: font }}>국장</span>
                                </div>
                                <div style={{ display: "flex", gap: S.sm }}>
                                    <div style={{ flex: 1 }}>
                                        <span style={{ color: C.success, fontSize: T.cap, fontWeight: T.w_bold, display: "block", marginBottom: S.sm }}>상승 TOP</span>
                                        {topKrSectors.map((s: any, i: number) => (
                                            <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: `${S.xs}px 0`, borderBottom: `1px solid ${C.border}` }}>
                                                <span style={{ color: C.textPrimary, fontSize: T.cap, fontFamily: font }}>{s.name}</span>
                                                <span style={{ color: C.success, fontSize: T.cap, fontWeight: T.w_bold, ...MONO }}>+{(s.change_pct || 0).toFixed(2)}%</span>
                                            </div>
                                        ))}
                                    </div>
                                    <div style={{ width: 1, background: C.border }} />
                                    <div style={{ flex: 1 }}>
                                        <span style={{ color: C.danger, fontSize: T.cap, fontWeight: T.w_bold, display: "block", marginBottom: S.sm }}>하락 TOP</span>
                                        {bottomKrSectors.map((s: any, i: number) => (
                                            <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: `${S.xs}px 0`, borderBottom: `1px solid ${C.border}` }}>
                                                <span style={{ color: C.textSecondary, fontSize: T.cap, fontFamily: font }}>{s.name}</span>
                                                <span style={{ color: C.danger, fontSize: T.cap, fontWeight: T.w_bold, ...MONO }}>{(s.change_pct || 0).toFixed(2)}%</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </>
                        )}
                        {usSectors.length > 0 && (
                            <>
                                <div style={{ display: "flex", alignItems: "center", gap: S.sm, marginBottom: S.sm, marginTop: krSectors.length > 0 ? S.md : 0 }}>
                                    <span style={{ padding: `2px ${S.sm}px`, borderRadius: R.sm, background: "rgba(91,169,255,0.12)", color: C.info, fontSize: T.cap, fontWeight: T.w_bold, fontFamily: font }}>미장</span>
                                </div>
                                <div style={{ display: "flex", gap: S.sm }}>
                                    <div style={{ flex: 1 }}>
                                        <span style={{ color: C.success, fontSize: T.cap, fontWeight: T.w_bold, display: "block", marginBottom: S.sm }}>상승 TOP</span>
                                        {topUsSectors.map((s: any, i: number) => (
                                            <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: `${S.xs}px 0`, borderBottom: `1px solid ${C.border}` }}>
                                                <span style={{ color: C.textPrimary, fontSize: T.cap, fontFamily: font }}>{s.name}</span>
                                                <span style={{ color: C.success, fontSize: T.cap, fontWeight: T.w_bold, ...MONO }}>+{(s.change_pct || 0).toFixed(2)}%</span>
                                            </div>
                                        ))}
                                    </div>
                                    <div style={{ width: 1, background: C.border }} />
                                    <div style={{ flex: 1 }}>
                                        <span style={{ color: C.danger, fontSize: T.cap, fontWeight: T.w_bold, display: "block", marginBottom: S.sm }}>하락 TOP</span>
                                        {bottomUsSectors.map((s: any, i: number) => (
                                            <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: `${S.xs}px 0`, borderBottom: `1px solid ${C.border}` }}>
                                                <span style={{ color: C.textSecondary, fontSize: T.cap, fontFamily: font }}>{s.name}</span>
                                                <span style={{ color: C.danger, fontSize: T.cap, fontWeight: T.w_bold, ...MONO }}>{(s.change_pct || 0).toFixed(2)}%</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </>
                        )}
                        {rotation.cycle_label && (
                            <div style={{ marginTop: S.sm, background: C.bgPage, borderRadius: R.md, padding: `${S.sm}px ${S.md}px`, border: `1px solid ${C.border}` }}>
                                <span style={{ color: "#A78BFA", fontSize: T.cap, fontWeight: T.w_bold, fontFamily: font }}>섹터 전략: {rotation.cycle_label}</span>
                                {rotation.cycle_desc && <p style={{ color: C.textSecondary, fontSize: T.cap, lineHeight: T.lh_normal, margin: `${S.xs}px 0 0`, fontFamily: font }}>{rotation.cycle_desc}</p>}
                            </div>
                        )}
                    </Section>
                )}

                {report.risk_watch && (
                    <Section icon="!" iconColor={C.danger} label="리스크 주의">
                        <p style={sectionText}>{report.risk_watch}</p>
                    </Section>
                )}

                {allHeadlines.length > 0 && (
                    <Section icon="N" iconColor={C.info} label={`뉴스 요약 (호재 ${posHeadlines} / 악재 ${negHeadlines})`}>
                        {krHeadlines.slice(0, 4).map((h: any, i: number) => {
                            const sc = h.sentiment === "positive" ? C.success : h.sentiment === "negative" ? C.danger : C.textSecondary
                            return (
                                <div key={`kr-${i}`} style={{ display: "flex", gap: S.sm, alignItems: "flex-start", padding: `${S.sm}px 0`, borderBottom: `1px solid ${C.border}` }}>
                                    <span style={{ width: 6, height: 6, borderRadius: 3, background: sc, marginTop: 5, flexShrink: 0 }} />
                                    <span style={{ color: C.textPrimary, fontSize: T.cap, lineHeight: T.lh_normal, fontFamily: font }}>{h.title}</span>
                                </div>
                            )
                        })}
                        {usHeadlines.length > 0 && (
                            <>
                                <div style={{ display: "flex", alignItems: "center", gap: S.sm, margin: `${S.sm}px 0 ${S.xs}px` }}>
                                    <span style={{ padding: `2px ${S.sm}px`, borderRadius: R.sm, background: "rgba(91,169,255,0.12)", color: C.info, fontSize: T.cap, fontWeight: T.w_bold, fontFamily: FONT_MONO, letterSpacing: "0.05em" }}>US</span>
                                </div>
                                {usHeadlines.slice(0, 4).map((h: any, i: number) => {
                                    const sc = h.sentiment === "positive" ? C.success : h.sentiment === "negative" ? C.danger : C.textSecondary
                                    return (
                                        <div key={`us-${i}`} style={{ display: "flex", gap: S.sm, alignItems: "flex-start", padding: `${S.sm}px 0`, borderBottom: `1px solid ${C.border}` }}>
                                            <span style={{ width: 6, height: 6, borderRadius: 3, background: sc, marginTop: 5, flexShrink: 0 }} />
                                            <span style={{ color: C.textPrimary, fontSize: T.cap, lineHeight: T.lh_normal, fontFamily: font }}>{h.title}</span>
                                        </div>
                                    )
                                })}
                            </>
                        )}
                    </Section>
                )}

                {report.hot_theme && (
                    <Section icon="H" iconColor={C.caution} label="주목 테마">
                        <p style={sectionText}>{report.hot_theme}</p>
                    </Section>
                )}

                {events.filter((e: any) => (e.d_day ?? 99) <= 14).length > 0 && (
                    <Section icon="E" iconColor="#A855F7" label="주요 이벤트">
                        {events.filter((e: any) => (e.d_day ?? 99) <= 14).slice(0, 5).map((e: any, i: number) => (
                            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: `${S.sm}px 0`, borderBottom: `1px solid ${C.border}` }}>
                                <div style={{ flex: 1 }}>
                                    <span style={{ color: C.textPrimary, fontSize: T.body, fontFamily: font }}>{e.name}</span>
                                    {e.impact && <div style={{ color: C.textTertiary, fontSize: T.cap, marginTop: 2 }}>{e.impact}</div>}
                                </div>
                                <span style={{ color: "#A855F7", fontSize: T.cap, fontWeight: T.w_bold, fontFamily: FONT_MONO, flexShrink: 0 }}>D-{e.d_day ?? "?"}</span>
                            </div>
                        ))}
                    </Section>
                )}

                {briefingHeadline && (
                    <Section icon="V" iconColor="#FFD700" label="비서의 한마디">
                        <p style={{ ...sectionText, color: "#FFD700", fontWeight: T.w_semi }}>{briefingHeadline}</p>
                        {briefingActions.length > 0 && (
                            <div style={{ marginTop: S.sm }}>
                                {briefingActions.map((a: string, i: number) => (
                                    <div key={i} style={{ color: C.textPrimary, fontSize: T.body, lineHeight: T.lh_loose, fontFamily: font }}>→ {a}</div>
                                ))}
                            </div>
                        )}
                    </Section>
                )}

                {report.tomorrow_outlook && (
                    <Section icon="→" iconColor="#A78BFA" label="향후 전망">
                        <p style={sectionText}>{report.tomorrow_outlook}</p>
                    </Section>
                )}

                {/* 저평가 발굴 (Value Hunter) */}
                {data?.value_hunt?.gate_open && Array.isArray(data.value_hunt.value_candidates) && data.value_hunt.value_candidates.length > 0 && (
                    <Section icon="V" iconColor="#22D3EE" label={`저평가 발굴 (${data.value_hunt.value_candidates.length}종목)`}>
                        <p style={{ color: "#22D3EE", fontSize: T.cap, fontWeight: T.w_semi, fontFamily: font, margin: `0 0 ${S.sm}px` }}>{data.value_hunt.gate_reason || ""}</p>
                        {data.value_hunt.value_candidates.slice(0, 5).map((vc: any, i: number) => (
                            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: `${S.sm}px 0`, borderBottom: `1px solid ${C.border}` }}>
                                <span style={{ color: C.textPrimary, fontSize: T.body, fontFamily: font }}>{vc.name || vc.ticker}</span>
                                <div style={{ display: "flex", gap: S.sm, alignItems: "center" }}>
                                    {typeof vc.value_score === "number" && <span style={{ color: "#22D3EE", fontSize: T.cap, fontWeight: T.w_bold, ...MONO }}>{vc.value_score}점</span>}
                                    {typeof vc.per === "number" && <span style={{ color: C.textSecondary, fontSize: T.cap, ...MONO }}>PER {vc.per.toFixed(1)}</span>}
                                </div>
                            </div>
                        ))}
                    </Section>
                )}

                {/* AI 포스트모텀 */}
                {data?.postmortem?.failures && data.postmortem.failures.length > 0 && (
                    <Section icon="X" iconColor="#F87171" label={`AI 오심 분석 (${data.postmortem.analyzed_count || data.postmortem.failures.length}건)`}>
                        {data.postmortem.lesson && <p style={{ ...sectionText, color: "#F87171" }}>{data.postmortem.lesson}</p>}
                        {data.postmortem.system_suggestion && <p style={{ ...sectionText, color: "#FBBF24", marginTop: S.sm }}>개선: {data.postmortem.system_suggestion}</p>}
                        {data.postmortem.failures.slice(0, 3).map((f: any, i: number) => (
                            <div key={i} style={{ padding: `${S.sm}px 0`, borderBottom: `1px solid ${C.border}` }}>
                                <div style={{ display: "flex", justifyContent: "space-between" }}>
                                    <span style={{ color: C.textPrimary, fontSize: T.body, fontFamily: font }}>{f.name || f.ticker || "?"}</span>
                                    <span style={{ color: "#F87171", fontSize: T.cap, fontWeight: T.w_bold, fontFamily: font }}>{f.recommendation || ""} → <span style={MONO}>{typeof f.actual_return_pct === "number" ? `${f.actual_return_pct.toFixed(1)}%` : "?"}</span></span>
                                </div>
                                {f.reason && <div style={{ color: C.textSecondary, fontSize: T.cap, marginTop: 2 }}>{f.reason}</div>}
                            </div>
                        ))}
                    </Section>
                )}

                {/* 팩터 IC 순위 */}
                {data?.factor_ic?.ranking?.length > 0 && (() => {
                    const ic = data.factor_ic
                    const ranking = ic.ranking || []
                    const monthly = ic.monthly_rollup || {}
                    const mFactors = monthly.by_factor || []
                    const thStyle: React.CSSProperties = { padding: `${S.xs}px ${S.sm}px`, textAlign: "left", fontSize: T.cap, fontWeight: T.w_bold, color: C.textTertiary, borderBottom: `1px solid ${C.border}` }
                    const tdStyle: React.CSSProperties = { padding: `${S.xs}px ${S.sm}px`, fontSize: T.cap, borderBottom: `1px solid ${C.bgElevated}` }
                    const sigFactors = ic.significant_factors || []
                    const decFactors = ic.decaying_factors || []

                    return (
                        <Section icon="Q" iconColor={C.info} label="팩터 예측력 순위">
                            <table style={{ width: "100%", borderCollapse: "collapse" }}>
                                <thead>
                                    <tr>
                                        <th style={thStyle}>#</th>
                                        <th style={thStyle}>팩터</th>
                                        <th style={{ ...thStyle, textAlign: "right" }}>ICIR</th>
                                        <th style={{ ...thStyle, textAlign: "center" }}>상태</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {ranking.slice(0, 8).map((r: any, i: number) => (
                                        <tr key={i}>
                                            <td style={{ ...tdStyle, color: C.textTertiary, ...MONO }}>{i + 1}</td>
                                            <td style={{ ...tdStyle, color: C.textPrimary }}>{r.factor}</td>
                                            <td style={{ ...tdStyle, textAlign: "right", color: Math.abs(r.icir) > 0.5 ? C.accent : C.textSecondary, fontWeight: T.w_bold, ...MONO }}>{r.icir?.toFixed(3)}</td>
                                            <td style={{ ...tdStyle, textAlign: "center", fontSize: T.cap }}>
                                                {decFactors.includes(r.factor) && <span style={{ color: C.danger, fontFamily: FONT_MONO, letterSpacing: "0.05em" }}>붕괴</span>}
                                                {sigFactors.includes(r.factor) && !decFactors.includes(r.factor) && <span style={{ color: C.accent, fontFamily: FONT_MONO, letterSpacing: "0.05em" }}>유의미</span>}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                            {mFactors.length > 0 && (
                                <div style={{ marginTop: S.md }}>
                                    <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_semi }}>{monthly.period_label || "월간"} 평균 (<span style={MONO}>{monthly.obs_entries || 0}</span>일)</span>
                                    <table style={{ width: "100%", borderCollapse: "collapse", marginTop: S.xs }}>
                                        <thead>
                                            <tr>
                                                <th style={thStyle}>#</th>
                                                <th style={thStyle}>팩터</th>
                                                <th style={{ ...thStyle, textAlign: "right" }}>평균 ICIR</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {mFactors.slice(0, 5).map((f: any, i: number) => (
                                                <tr key={i}>
                                                    <td style={{ ...tdStyle, color: C.textTertiary, ...MONO }}>{i + 1}</td>
                                                    <td style={{ ...tdStyle, color: C.textPrimary }}>{f.factor}</td>
                                                    <td style={{ ...tdStyle, textAlign: "right", color: Math.abs(f.avg_icir) > 0.5 ? C.accent : C.textSecondary, fontWeight: T.w_bold, ...MONO }}>{f.avg_icir?.toFixed(3)}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            )}
                        </Section>
                    )
                })()}

                {/* AI 소스별 리더보드 */}
                {data?.ai_leaderboard?.by_source?.length > 0 && (() => {
                    const lb = data.ai_leaderboard
                    const sources = lb.by_source || []
                    const thStyle: React.CSSProperties = { padding: `${S.xs}px ${S.sm}px`, textAlign: "left", fontSize: T.cap, fontWeight: T.w_bold, color: C.textTertiary, borderBottom: `1px solid ${C.border}` }
                    const tdStyle: React.CSSProperties = { padding: `${S.xs}px ${S.sm}px`, fontSize: T.cap, borderBottom: `1px solid ${C.bgElevated}` }
                    const sourceLabel: Record<string, string> = { gemini: "Gemini", claude: "Claude", gemini_disputed: "Gemini (이견)" }

                    return (
                        <Section icon="AI" iconColor={C.caution} label={`AI 소스별 성과 (${lb.window_days || 30}일)`}>
                            <table style={{ width: "100%", borderCollapse: "collapse" }}>
                                <thead>
                                    <tr>
                                        <th style={thStyle}>소스</th>
                                        <th style={{ ...thStyle, textAlign: "right" }}>추천 수</th>
                                        <th style={{ ...thStyle, textAlign: "right" }}>적중률</th>
                                        <th style={{ ...thStyle, textAlign: "right" }}>평균 수익</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {sources.map((s: any, i: number) => (
                                        <tr key={i}>
                                            <td style={{ ...tdStyle, color: C.textPrimary, fontWeight: T.w_semi }}>{sourceLabel[s.source] || s.source}</td>
                                            <td style={{ ...tdStyle, textAlign: "right", color: C.textSecondary, ...MONO }}>{s.n}건</td>
                                            <td style={{ ...tdStyle, textAlign: "right", color: s.hit_rate >= 60 ? C.accent : s.hit_rate >= 40 ? C.watch : C.danger, fontWeight: T.w_bold, ...MONO }}>{s.hit_rate}%</td>
                                            <td style={{ ...tdStyle, textAlign: "right", color: s.avg_return >= 0 ? C.accent : C.danger, fontWeight: T.w_bold, ...MONO }}>{s.avg_return > 0 ? "+" : ""}{s.avg_return}%</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                            {lb.suggested_note && (
                                <p style={{ color: C.textSecondary, fontSize: T.cap, marginTop: S.sm, lineHeight: T.lh_normal, fontFamily: font }}>
                                    {lb.suggested_note}
                                </p>
                            )}
                            <p style={{ color: C.textTertiary, fontSize: T.cap, marginTop: S.xs, fontFamily: font }}>
                                모델 전환은 수동으로 진행하세요 (.env GEMINI_MODEL / ANTHROPIC 설정)
                            </p>
                        </Section>
                    )
                })()}

                {/* 전략 진화 */}
                {data?.strategy_evolution && data.strategy_evolution.status && data.strategy_evolution.status !== "no_change" && (
                    <Section icon="⚙" iconColor="#A78BFA" label="전략 진화">
                        <div style={{ display: "flex", gap: S.sm, alignItems: "center", marginBottom: S.sm }}>
                            <span style={{ padding: `3px ${S.sm}px`, borderRadius: R.sm, fontSize: T.cap, fontWeight: T.w_bold, fontFamily: font, background: data.strategy_evolution.status === "auto_applied" ? "rgba(34,197,94,0.15)" : "rgba(234,179,8,0.12)", color: data.strategy_evolution.status === "auto_applied" ? C.success : "#EAB308" }}>
                                {data.strategy_evolution.status === "auto_applied" ? "자동 적용" : data.strategy_evolution.status === "pending_approval" ? "승인 대기" : data.strategy_evolution.status}
                            </span>
                            {data.strategy_evolution.new_version && <span style={{ color: C.textSecondary, fontSize: T.cap, fontFamily: FONT_MONO }}>v{data.strategy_evolution.new_version}</span>}
                        </div>
                        {data.strategy_evolution.reason && <p style={sectionText}>{data.strategy_evolution.reason}</p>}
                        {data.strategy_evolution.summary && <p style={sectionText}>{data.strategy_evolution.summary}</p>}
                    </Section>
                )}

                {/* 실적 캘린더 요약 */}
                {recs.some((r: any) => r.earnings?.next_earnings) && (
                    <Section icon="📅" iconColor={C.caution} label="실적 발표 예정">
                        {recs.filter((r: any) => r.earnings?.next_earnings).slice(0, 5).map((r: any, i: number) => (
                            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: `${S.sm}px 0`, borderBottom: `1px solid ${C.border}` }}>
                                <span style={{ color: C.textPrimary, fontSize: T.body, fontFamily: font }}>{r.name}</span>
                                <span style={{ color: C.caution, fontSize: T.cap, fontWeight: T.w_bold, ...MONO }}>{r.earnings.next_earnings}</span>
                            </div>
                        ))}
                    </Section>
                )}
            </div>
        </>
    )
}

VerityReport.defaultProps = { dataUrl: DATA_URL, market: "kr", apiBase: DEFAULT_API_BASE }
addPropertyControls(VerityReport, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: DATA_URL,
    },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["KR 국장", "US 미장"],
        defaultValue: "kr",
    },
    apiBase: {
        type: ControlType.String,
        title: "API Base URL",
        defaultValue: DEFAULT_API_BASE,
    },
})

const card: React.CSSProperties = {
    width: "100%",
    background: C.bgPage,
    borderRadius: R.lg,
    border: `1px solid ${C.border}`,
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    fontFamily: font,
    color: C.textPrimary,
}

const periodBar: React.CSSProperties = {
    display: "flex",
    gap: S.xs,
    padding: `${S.md}px ${S.lg}px`,
    borderBottom: `1px solid ${C.border}`,
    overflowX: "auto",
}

const periodBtn: React.CSSProperties = {
    border: "none",
    borderRadius: R.md,
    padding: `${S.sm}px ${S.lg}px`,
    fontSize: T.cap,
    fontWeight: T.w_bold,
    fontFamily: FONT,
    cursor: "pointer",
    transition: X.fast,
    whiteSpace: "nowrap",
    flexShrink: 0,
}

const header: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    padding: `${S.lg}px ${S.xl}px`,
    borderBottom: `1px solid ${C.border}`,
}

const pdfBtn: React.CSSProperties = {
    background: C.accentSoft,
    border: `1px solid ${C.accent}`,
    color: C.accent,
    fontSize: T.cap,
    fontWeight: T.w_bold,
    fontFamily: FONT,
    padding: `${S.sm}px ${S.md}px`,
    borderRadius: R.md,
    cursor: "pointer",
    whiteSpace: "nowrap",
    transition: X.fast,
    boxShadow: G.accentSoft,
}

const aiBadge: React.CSSProperties = {
    color: C.accent,
    fontSize: T.cap,
    fontWeight: T.w_bold,
    fontFamily: FONT_MONO,
    letterSpacing: "0.08em",
    background: C.accentSoft,
    border: `1px solid rgba(181,255,25,0.25)`,
    padding: `${S.xs}px ${S.sm}px`,
    borderRadius: R.sm,
    whiteSpace: "nowrap",
}

const bodyWrap: React.CSSProperties = {
    padding: `${S.md}px ${S.lg}px`,
    display: "flex",
    flexDirection: "column",
    gap: S.lg,
}

const sectionText: React.CSSProperties = {
    color: C.textPrimary,
    fontSize: T.body,
    lineHeight: T.lh_loose,
    margin: 0,
    fontFamily: FONT,
}

const footer: React.CSSProperties = {
    padding: `${S.md}px ${S.lg}px ${S.lg}px`,
    borderTop: `1px solid ${C.border}`,
}
