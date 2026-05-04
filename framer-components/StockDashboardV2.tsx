import { addPropertyControls, ControlType } from "framer"
import {
    useCallback,
    useEffect,
    useMemo,
    useRef,
    useState,
    type CSSProperties,
} from "react"

/**
 * StockDashboardV2 — 풀 재작성 (Step A 정공법, 2026-05-05~)
 *
 * 출처: StockDashboard.tsx (3,095줄) 통째 재작성.
 *
 * 진행 단계 (총 13~14 turn 예상):
 *   - A.1 ✅ 본체 chapter 분석
 *   - A.2 ✅ 골격 (이 파일) — 토큰 + TermTooltip + 7 sub-component
 *          + 메인 shell (placeholder render)
 *   - A.3 listPanel — 종목 list
 *   - A.4 detailPanel header + tab bar
 *   - A.5~A.15 11 detail tab 각 재작성 (overview / brain / technical
 *              / sentiment / macro / predict / timing / niche / property
 *              / quant / group)
 *   - A.16 통합 검증 + 기능 매핑
 *
 * 모던 심플 6원칙 풀 적용:
 *   1. No card-in-card — 외곽 1개 + 섹션 spacing
 *   2. Flat hierarchy — H1 + cap 라벨 + content
 *   3. Mono numerics 일관 (가격·점수·티커·시각·% 모두)
 *   4. Expand on tap (탭 + 카드 expand)
 *   5. Color discipline — 토큰만
 *   6. Hover tooltip — 전문 용어 dotted underline
 *
 * feedback_no_hardcode_position 적용: inline 렌더링.
 *
 * NOTE (A.2): main render 는 placeholder. listPanel / detailPanel /
 * 11 detail tab 은 다음 turn 들에서 점진 박음. 현재는 "준비 중" 카드.
 */

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
    success: "0 0 6px rgba(34,197,94,0.30)",
    warn: "0 0 6px rgba(245,158,11,0.30)",
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
const MONO: CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/* ──────────────────────────────────────────────────────────────
 * ◆ TERMS START ◆ (data/verity_terms.json 발췌)
 * ────────────────────────────────────────────────────────────── */
interface Term {
    label: string
    category?: "metric" | "grade" | "signal" | "concept" | "data_source" | "internal" | "time"
    definition: string
    l3?: boolean
}
const TERMS: Record<string, Term> = {
    FACT_SCORE: {
        label: "Fact Score",
        category: "metric",
        definition: "객관적 수치 종합 점수 (0~100). 13 sub-score 가중 평균.",
    },
    BRAIN_SCORE: {
        label: "Brain Score",
        category: "metric",
        definition: "Brain v5 종합 판정 (0~100). fact_score + sentiment + regime 가중.",
    },
    MULTI_FACTOR: {
        label: "Multi-Factor (다요인)",
        category: "metric",
        definition: "fact_score 13 sub-score 중 최대 가중 (0.1876). 가치·성장·모멘텀·품질 통합.",
    },
    TIMING_SCORE: {
        label: "Timing Score",
        category: "metric",
        definition: "진입 타이밍 점수 (0~100). sentiment 70% + technical 30%.",
    },
    GRADE_BUY: { label: "매수", category: "grade", definition: "fact_score 60~74. 진입 권고." },
    GRADE_AVOID: { label: "회피", category: "grade", definition: "다수 sub-score 평균 이하. 펀더멘털 결함 가능." },
    R_MULTIPLE: {
        label: "R-Multiple",
        category: "concept",
        definition: "1R = 진입가-손절가. 1R 50% / 2R 30% / 트레일링 20% 3단계 부분 익절.",
    },
}
/* ◆ TERMS END ◆ */


/* ──────────────────────────────────────────────────────────────
 * ◆ TERMTOOLTIP START ◆
 * ────────────────────────────────────────────────────────────── */
function TermTooltip({ termKey, children }: { termKey: string; children: React.ReactNode }) {
    const [show, setShow] = useState(false)
    const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
    const anchorRef = useRef<HTMLSpanElement>(null)
    const term = TERMS[termKey]
    if (!term) return <>{children}</>
    const TIP_W = 320, TIP_H = 160
    const handleEnter = () => {
        const el = anchorRef.current
        if (!el || typeof window === "undefined") { setShow(true); return }
        const rect = el.getBoundingClientRect()
        const vw = window.innerWidth, vh = window.innerHeight
        const margin = 8
        let left = rect.left
        if (left + TIP_W + margin > vw) left = Math.max(margin, rect.right - TIP_W)
        let top = rect.bottom + 6
        if (top + TIP_H + margin > vh) top = Math.max(margin, rect.top - TIP_H - 6)
        setPos({ top, left })
        setShow(true)
    }
    const handleLeave = () => { setShow(false); setPos(null) }
    return (
        <span
            ref={anchorRef}
            onMouseEnter={handleEnter} onMouseLeave={handleLeave}
            onFocus={handleEnter} onBlur={handleLeave}
            tabIndex={0}
            style={{
                position: "relative", display: "inline-block",
                borderBottom: `1px dotted ${C.textTertiary}`,
                cursor: "help", outline: "none",
            }}
        >
            {children}
            {show && pos && (
                <div style={{
                    position: "fixed", top: pos.top, left: pos.left,
                    width: TIP_W, zIndex: 100,
                    padding: "10px 12px", borderRadius: R.md,
                    background: C.bgElevated, border: `1px solid ${C.borderStrong}`,
                    boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                    fontFamily: FONT, fontSize: T.cap, lineHeight: T.lh_normal,
                    whiteSpace: "normal", pointerEvents: "none",
                }}>
                    <div style={{ color: C.textPrimary, fontWeight: T.w_bold, fontSize: 13, marginBottom: 4 }}>
                        {term.label}
                    </div>
                    <div style={{ color: C.textSecondary }}>{term.definition}</div>
                </div>
            )}
        </span>
    )
}
/* ◆ TERMTOOLTIP END ◆ */


/* ──────────────────────────────────────────────────────────────
 * ◆ HELPERS START ◆
 * ────────────────────────────────────────────────────────────── */

/* fetch (인라인) */
const PORTFOLIO_FETCH_TIMEOUT_MS = 15_000
function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}
function fetchJson(url: string, signal?: AbortSignal): Promise<any> {
    const ac = new AbortController()
    if (signal) {
        if (signal.aborted) ac.abort()
        else signal.addEventListener("abort", () => ac.abort(), { once: true })
    }
    const timer = setTimeout(() => ac.abort(), PORTFOLIO_FETCH_TIMEOUT_MS)
    return fetch(bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal: ac.signal })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((t) => JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
        .finally(() => clearTimeout(timer))
}

/* 시장 분류 */
function isUSMarket(market: string, currency?: string): boolean {
    if (currency === "USD") return true
    return /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(market || "")
}
function isKRX(market: string): boolean {
    return /KOSPI|KOSDAQ|KRX|코스피|코스닥/i.test(market || "")
}

/* 포맷 */
function fmtFixed(n: any, digits: number = 1, suffix: string = ""): string {
    const x = typeof n === "number" ? n : Number(n)
    if (!Number.isFinite(x)) return "—"
    return `${x.toFixed(digits)}${suffix}`
}
function fmtLocale(n: any, suffix: string = ""): string {
    const x = typeof n === "number" ? n : Number(n)
    if (!Number.isFinite(x)) return "—"
    return `${x.toLocaleString()}${suffix}`
}
function fmtPct(n: number | null | undefined, digits = 2, showSign = true): string {
    if (n == null || !Number.isFinite(n)) return "—"
    const sign = showSign && n > 0 ? "+" : ""
    return `${sign}${n.toFixed(digits)}%`
}
function formatPrice(price: number, usd?: boolean): string {
    if (usd) return `$${Number(price).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    return `${price?.toLocaleString()}원`
}
function formatVolume(value: number, usd?: boolean): string {
    if (usd) return `$${(value / 1e6).toFixed(1)}M`
    return `${(value / 1e8).toFixed(0)}억`
}
function formatMarketCap(value: number, usd?: boolean): string {
    if (usd) return `$${(value / 1e9).toFixed(1)}B`
    return `${(value / 1e12).toFixed(2)}조`
}

/* 색 */
function pctColor(n: number | null | undefined): string {
    if (n == null || !Number.isFinite(n)) return C.textTertiary
    if (n > 0) return C.up
    if (n < 0) return C.down
    return C.textTertiary
}
function scoreColor(score: number): string {
    if (score >= 65) return C.accent
    if (score >= 45) return C.watch
    return C.danger
}
function recColor(rec: string): string {
    if (rec === "STRONG_BUY") return C.strongBuy
    if (rec === "BUY") return C.buy
    if (rec === "WATCH") return C.watch
    if (rec === "CAUTION") return C.caution
    if (rec === "AVOID") return C.avoid
    return C.textTertiary
}

/* Stale 정보 */
function stalenessInfo(updatedAt: any): { label: string; color: string; stale: boolean } {
    if (!updatedAt) return { label: "", color: C.textTertiary, stale: false }
    const t = new Date(String(updatedAt)).getTime()
    if (!Number.isFinite(t)) return { label: "", color: C.textTertiary, stale: false }
    const hours = (Date.now() - t) / 3_600_000
    if (hours < 1) return { label: `방금 (${Math.round(hours * 60)}분 전)`, color: C.success, stale: false }
    if (hours < 3) return { label: `${Math.round(hours)}시간 전`, color: C.success, stale: false }
    if (hours < 12) return { label: `${Math.round(hours)}시간 전`, color: C.warn, stale: false }
    if (hours < 24) return { label: `${Math.round(hours)}시간 전 (stale 경계)`, color: C.warn, stale: true }
    const days = hours / 24
    return { label: `${days.toFixed(1)}일 전 (stale)`, color: C.danger, stale: true }
}

/* API normalize */
function _normalizeApi(raw: string): string {
    let s = (raw || "").trim().replace(/\/+$/, "")
    if (!s) return ""
    if (!/^https?:\/\//i.test(s)) s = `https://${s.replace(/^\/+/, "")}`
    return s.replace(/\/+$/, "")
}

/* JWT auth */
const SUPABASE_SESSION_KEY = "verity_supabase_session"
const AUTH_LOGIN_PATH = "/login"

function getAccessToken(): string {
    if (typeof window === "undefined") return ""
    try {
        const raw = localStorage.getItem(SUPABASE_SESSION_KEY)
        if (!raw) return ""
        const s = JSON.parse(raw)
        return s && typeof s.access_token === "string" ? s.access_token : ""
    } catch { return "" }
}
function authHeaders(extra: Record<string, string> = {}): Record<string, string> {
    const token = getAccessToken()
    const h: Record<string, string> = { ...extra }
    if (token) h["Authorization"] = `Bearer ${token}`
    return h
}
function redirectToAuth(): void {
    if (typeof window === "undefined") return
    const next = encodeURIComponent(window.location.pathname + window.location.search)
    const url = AUTH_LOGIN_PATH + (AUTH_LOGIN_PATH.includes("?") ? "&" : "?") + "next=" + next
    window.location.href = url
}

/* Business tagline */
const BUSINESS_NODE_LABELS: Record<string, string> = {
    "메모리·파운드리 리드": "메모리·파운드리 핵심",
    "장비/소재": "장비·소재",
}
function _cleanBusinessLabel(v: string): string {
    return String(v || "").replace(/\s+/g, " ").replace(/[|]/g, " ").trim()
}
function getBusinessTagline(stock: any): string {
    const tagline = (stock?.company_tagline || "").trim()
    if (tagline) return tagline
    const roles = Array.isArray(stock?.value_chain?.roles) ? stock.value_chain.roles : []
    if (roles.length > 0) {
        const first = roles[0] || {}
        const sector = _cleanBusinessLabel(first?.sector_label_ko || "")
        const rawNode = _cleanBusinessLabel(first?.node_label_ko || "")
        const node = BUSINESS_NODE_LABELS[rawNode] || rawNode
        if (sector && node) return `${sector} ${node} 기업`
        if (sector) return `${sector} 관련 기업`
    }
    const nicheKeyword = _cleanBusinessLabel(stock?.niche_data?.trends?.keyword || "")
    if (nicheKeyword) return `${nicheKeyword} 관련 기업`
    const ctype = _cleanBusinessLabel(stock?.company_type || "")
    if (ctype) return ctype.includes("기업") ? ctype : `${ctype} 기업`
    return isUSMarket(stock?.market || "", stock?.currency) ? "미국 상장 기업" : "국내 상장 기업"
}

/* ◆ HELPERS END ◆ */


/* ──────────────────────────────────────────────────────────────
 * ◆ SUB COMPONENTS START ◆
 * ────────────────────────────────────────────────────────────── */

/* Sparkline (간단 SVG polyline) */
function Sparkline({
    data, width = 60, height = 24, color = C.textTertiary,
}: { data: number[]; width?: number; height?: number; color?: string }) {
    if (!data || data.length < 2) return null
    const min = Math.min(...data)
    const max = Math.max(...data)
    const range = max - min || 1
    const points = data
        .map((v, i) => `${(i / (data.length - 1)) * width},${height - ((v - min) / range) * height}`)
        .join(" ")
    return (
        <svg width={width} height={height} style={{ display: "block" }}>
            <polyline
                points={points} fill="none" stroke={color}
                strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round"
            />
        </svg>
    )
}

/* TrendBlock — 1m/3m/6m/1y 차트 + H/L/Vol */
function TrendBlock({ stock: s, isUS: usd }: { stock: any; isUS: boolean }) {
    const trends = s?.trends
    const weeklyData: number[] = s?.sparkline_weekly || []
    const [tp, setTp] = useState<"1m" | "3m" | "6m" | "1y">("3m")
    if (!trends) return null
    const t = trends[tp]
    if (!t) return null
    const sliceMap: Record<string, number> = { "1m": 4, "3m": 13, "6m": 26, "1y": 52 }
    const chartData = weeklyData.slice(-sliceMap[tp])
    const c = pctColor(t.change_pct ?? 0)

    return (
        <div style={trendBlock}>
            <div style={{ display: "flex", gap: S.xs, marginBottom: S.sm }}>
                {(["1m", "3m", "6m", "1y"] as const).map((p) => (
                    <button
                        key={p}
                        onClick={() => setTp(p)}
                        style={{
                            border: "none", borderRadius: R.sm,
                            padding: `${S.xs / 2}px ${S.sm}px`,
                            fontSize: T.cap, fontWeight: T.w_semi, fontFamily: FONT,
                            cursor: "pointer",
                            background: tp === p ? C.accent : C.bgElevated,
                            color: tp === p ? C.bgPage : C.textTertiary,
                            transition: X.fast,
                            letterSpacing: "0.05em",
                        }}
                    >
                        {p.toUpperCase()}
                    </button>
                ))}
            </div>
            {chartData.length > 1 && (
                <Sparkline data={chartData} width={220} height={32} color={c} />
            )}
            <div style={{ display: "flex", gap: S.md, marginTop: S.xs, flexWrap: "wrap" }}>
                <span style={{ ...MONO, color: c, fontSize: T.cap, fontWeight: T.w_bold }}>
                    {fmtPct(t.change_pct ?? 0)}
                </span>
                <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap }}>
                    H {usd ? `$${fmtFixed(t.high, 2)}` : fmtLocale(t.high)}
                </span>
                <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap }}>
                    L {usd ? `$${fmtFixed(t.low, 2)}` : fmtLocale(t.low)}
                </span>
                <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap }}>
                    Vol {Number.isFinite(Number(t.avg_volume)) && Number(t.avg_volume) > 0
                        ? (Number(t.avg_volume) / 1e6).toFixed(1) + "M"
                        : "—"}
                </span>
            </div>
        </div>
    )
}

/* TimingSignal type */
type TimingSignal = {
    score?: number
    signal?: string
    sentiment_component?: number
    technical_component?: number
    weights?: { sentiment: number; technical: number }
    version?: string
    note?: string
}

/* TimingSignalCard — sentiment + technical 분리 */
function TimingSignalCard({ ts }: { ts: TimingSignal | null | undefined }) {
    if (!ts || ts.score == null) return null
    const sigColor = (s?: string) =>
        s === "STRONG_BUY" ? C.strongBuy
        : s === "BUY" ? C.buy
        : s === "NEUTRAL" ? C.textSecondary
        : s === "WEAK" ? C.warn
        : C.danger
    const sigLabel = (s?: string) =>
        s === "STRONG_BUY" ? "강한 진입"
        : s === "BUY" ? "진입 우위"
        : s === "NEUTRAL" ? "중립"
        : s === "WEAK" ? "약세"
        : "대기"
    const sc = sigColor(ts.signal)
    const sentPct = (ts.weights?.sentiment ?? 0.7) * 100
    const techPct = (ts.weights?.technical ?? 0.3) * 100

    return (
        <div style={subCard}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: S.sm }}>
                <div style={{ display: "flex", alignItems: "center", gap: S.sm }}>
                    <span style={subCardCap}>
                        <TermTooltip termKey="TIMING_SCORE">타이밍 시그널</TermTooltip>
                    </span>
                    <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap }}>
                        sentiment {sentPct.toFixed(0)}% + technical {techPct.toFixed(0)}%
                    </span>
                </div>
                <span style={{
                    background: sc, color: C.bgPage,
                    padding: `2px ${S.sm}px`, borderRadius: R.sm,
                    fontSize: T.cap, fontWeight: T.w_bold,
                    fontFamily: FONT, letterSpacing: "0.03em",
                }}>
                    {sigLabel(ts.signal)} · {ts.score}
                </span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: S.sm, marginTop: S.sm }}>
                <div style={miniMetric}>
                    <span style={miniLabel}>심리</span>
                    <span style={miniValue}>{ts.sentiment_component ?? "—"}</span>
                </div>
                <div style={miniMetric}>
                    <span style={miniLabel}>기술적</span>
                    <span style={miniValue}>{ts.technical_component ?? "—"}</span>
                </div>
            </div>
            <div style={{ marginTop: S.xs, color: C.textTertiary, fontSize: T.cap, lineHeight: T.lh_normal }}>
                <TermTooltip termKey="BRAIN_SCORE">brain_score</TermTooltip>
                {" "}(펀더멘털) 와 분리. 동시 confirm 시 강한 신호.
            </div>
        </div>
    )
}

/* TradePlan type */
type TradePlan = {
    rec?: string
    entry_zone?: { low: number; high: number; trigger?: string; active?: boolean } | null
    position_pct?: number | null
    position_pct_range?: { min: number; max: number; note?: string } | null
    exit_target?: { price: number; condition?: string } | null
    stop_loss?: { price: number; condition?: string } | null
    transition_triggers?: { current_verdict?: string; current_action?: string; rules?: string[] } | null
    expected_return?: { median?: number; p25?: number; p75?: number; hit_rate?: number; horizon_days?: number } | null
    version?: string
    note?: string
}

/* TradePlanSection — 진입/포지션/익절/손절/예상수익 */
function TradePlanSection({ plan, isUS }: { plan: TradePlan | null | undefined; isUS: boolean }) {
    if (!plan) return null
    const rec = plan.rec || "WATCH"
    const rc = recColor(rec)
    const isSkeleton = (plan.version || "").startsWith("v0_skeleton")
    const fmt = (v: any) => formatPrice(Number(v || 0), isUS)
    const entryActive = plan.entry_zone?.active === true
    const range = plan.position_pct_range

    return (
        <div style={subCard}>
            {/* 헤더 */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: S.sm }}>
                <div style={{ display: "flex", alignItems: "center", gap: S.sm, flexWrap: "wrap" }}>
                    <span style={{ ...subCardCap, color: rc }}>매매 플랜</span>
                    <span style={{ color: C.textTertiary, fontSize: T.cap }}>
                        {plan.version || "v0"} · 본인 운영 참고용 (검증 전)
                    </span>
                </div>
                {isSkeleton ? (
                    <span style={{ color: C.warn, fontSize: T.cap, fontWeight: T.w_bold }}>산출 중</span>
                ) : rec === "BUY" ? (
                    <span style={{
                        color: entryActive ? C.bgPage : C.warn,
                        background: entryActive ? C.buy : "transparent",
                        border: entryActive ? "none" : `1px solid ${C.warn}`,
                        padding: `2px ${S.sm}px`, borderRadius: R.sm,
                        fontSize: T.cap, fontWeight: T.w_bold,
                        fontFamily: FONT, letterSpacing: "0.03em",
                    }}>
                        {entryActive ? "진입 가능" : "진입 대기"}
                    </span>
                ) : null}
            </div>

            {/* 현재 액션 */}
            {plan.transition_triggers?.current_action && (
                <div style={{
                    background: rec === "AVOID" ? `${C.danger}1A` : rec === "BUY" ? C.accentSoft : `${C.watch}1A`,
                    border: `1px solid ${rec === "AVOID" ? `${C.danger}33` : rec === "BUY" ? `${C.accent}33` : `${C.watch}33`}`,
                    borderRadius: R.sm,
                    padding: `${S.xs}px ${S.md}px`,
                    marginTop: S.sm,
                }}>
                    <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_semi, marginRight: S.sm }}>현재 액션</span>
                    <span style={{ color: rc, fontSize: T.cap, fontWeight: T.w_bold }}>
                        {plan.transition_triggers.current_action}
                    </span>
                </div>
            )}

            {/* 4 셀 grid */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: S.sm, marginTop: S.sm }}>
                <div style={planCell}>
                    <span style={planLabel}>진입 구간</span>
                    <span style={planValue}>
                        {plan.entry_zone ? `${fmt(plan.entry_zone.low)} ~ ${fmt(plan.entry_zone.high)}` : "—"}
                    </span>
                    {plan.entry_zone?.trigger && <span style={planHint}>{plan.entry_zone.trigger}</span>}
                </div>
                <div style={planCell}>
                    <span style={planLabel}>포지션 비중 (권고)</span>
                    <span style={planValue}>
                        {range ? (range.min === range.max ? `${range.max}%` : `${range.min} ~ ${range.max}%`) : "—"}
                    </span>
                    <span style={planHint}>{range?.note || "단일 종목 한도 — 본인 portfolio 수동 결정"}</span>
                </div>
                <div style={planCell}>
                    <span style={planLabel}>익절 목표 (참고)</span>
                    <span style={{ ...planValue, color: C.up }}>
                        {plan.exit_target ? fmt(plan.exit_target.price) : "—"}
                    </span>
                    {plan.exit_target?.condition && <span style={planHint}>{plan.exit_target.condition}</span>}
                </div>
                <div style={planCell}>
                    <span style={planLabel}>손절 라인 (참고)</span>
                    <span style={{ ...planValue, color: C.down }}>
                        {plan.stop_loss ? fmt(plan.stop_loss.price) : "—"}
                    </span>
                    {plan.stop_loss?.condition && <span style={planHint}>{plan.stop_loss.condition}</span>}
                </div>
            </div>

            {/* verdict 전이 룰 */}
            {plan.transition_triggers?.rules && plan.transition_triggers.rules.length > 0 && (
                <div style={{
                    marginTop: S.sm,
                    background: C.bgCard, borderRadius: R.sm,
                    border: `1px solid ${C.border}`,
                    padding: `${S.xs}px ${S.md}px`,
                }}>
                    <span style={{ color: C.textSecondary, fontSize: T.cap, fontWeight: T.w_bold }}>
                        자동 액션 트리거 (verdict 전이)
                    </span>
                    <ul style={{ margin: `${S.xs}px 0 0 0`, padding: `0 0 0 ${S.lg}px` }}>
                        {plan.transition_triggers.rules.map((r, i) => (
                            <li key={i} style={{ color: C.textSecondary, fontSize: T.cap, lineHeight: T.lh_normal }}>{r}</li>
                        ))}
                    </ul>
                </div>
            )}

            {/* 예상 수익 분포 */}
            <div style={{
                marginTop: S.sm,
                background: C.bgCard, borderRadius: R.sm,
                border: `1px solid ${C.border}`,
                padding: `${S.xs}px ${S.md}px`,
            }}>
                <span style={{ color: C.textSecondary, fontSize: T.cap, fontWeight: T.w_bold }}>
                    예상 수익 (백테스트 분포)
                </span>
                {plan.expected_return ? (
                    <div style={{ display: "flex", gap: S.lg, marginTop: S.xs, flexWrap: "wrap" }}>
                        <span style={{ ...MONO, color: C.textSecondary, fontSize: T.cap }}>
                            중앙값 <b style={{ color: C.up }}>{fmtFixed(plan.expected_return.median, 1, "%")}</b>
                        </span>
                        <span style={{ ...MONO, color: C.textSecondary, fontSize: T.cap }}>
                            P25/75 {fmtFixed(plan.expected_return.p25, 1, "%")} / {fmtFixed(plan.expected_return.p75, 1, "%")}
                        </span>
                        <span style={{ ...MONO, color: C.textSecondary, fontSize: T.cap }}>
                            적중률 {fmtFixed((plan.expected_return.hit_rate ?? 0) * 100, 0, "%")}
                        </span>
                        <span style={{ ...MONO, color: C.textSecondary, fontSize: T.cap }}>
                            보유기간 {plan.expected_return.horizon_days ?? "—"}일
                        </span>
                    </div>
                ) : (
                    <div style={{ marginTop: S.xs, color: C.textTertiary, fontSize: T.cap }}>
                        백테스트 quintile 결과 연결 후 채워짐 (단일 숫자 X — 분포로 표시)
                    </div>
                )}
            </div>

            {plan.note && (
                <div style={{ marginTop: S.xs, color: C.textTertiary, fontSize: T.cap }}>
                    {plan.note}
                </div>
            )}
        </div>
    )
}

/* SectorTrendView — 섹터 top3 / bottom3 / rotation */
function SectorTrendView({ sectorTrends }: { sectorTrends: any }) {
    const [sp, setSp] = useState<"1m" | "3m" | "6m" | "1y">("3m")
    if (!sectorTrends) return null
    const st = sectorTrends[sp]
    if (!st) {
        return (
            <div style={subCard}>
                <span style={{ color: C.textTertiary, fontSize: T.cap }}>
                    {sp.toUpperCase()} 섹터 데이터 아직 없음 (스냅샷 축적 중)
                </span>
            </div>
        )
    }
    return (
        <div style={subCard}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: S.sm }}>
                <span style={{ ...subCardCap, color: C.info }}>섹터 추이</span>
                <div style={{ display: "flex", gap: S.xs / 2 }}>
                    {(["1m", "3m", "6m", "1y"] as const).map((p) => (
                        <button
                            key={p}
                            onClick={() => setSp(p)}
                            style={{
                                border: "none", borderRadius: R.sm,
                                padding: `2px ${S.sm}px`,
                                fontSize: T.cap, fontWeight: T.w_semi, fontFamily: FONT,
                                cursor: "pointer",
                                background: sp === p ? C.info : C.bgElevated,
                                color: sp === p ? C.bgPage : C.textTertiary,
                                transition: X.fast,
                                letterSpacing: "0.03em",
                            }}
                        >
                            {p.toUpperCase()}
                        </button>
                    ))}
                </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: S.md }}>
                <div>
                    <span style={{ color: C.success, fontSize: T.cap, fontWeight: T.w_bold, display: "block", marginBottom: S.xs }}>TOP</span>
                    {(st.top3_sectors || []).map((s: any, i: number) => (
                        <div
                            key={s.name ?? i}
                            style={{
                                display: "flex", justifyContent: "space-between",
                                padding: `2px 0`,
                                borderBottom: `1px solid ${C.border}`,
                            }}
                        >
                            <span style={{ color: C.textPrimary, fontSize: T.cap }}>{s.name}</span>
                            <span style={{ ...MONO, color: C.success, fontSize: T.cap, fontWeight: T.w_semi }}>
                                {fmtPct(s.avg_change_pct ?? 0)}
                            </span>
                        </div>
                    ))}
                </div>
                <div>
                    <span style={{ color: C.danger, fontSize: T.cap, fontWeight: T.w_bold, display: "block", marginBottom: S.xs }}>BOTTOM</span>
                    {(st.bottom3_sectors || []).map((s: any, i: number) => (
                        <div
                            key={s.name ?? i}
                            style={{
                                display: "flex", justifyContent: "space-between",
                                padding: `2px 0`,
                                borderBottom: `1px solid ${C.border}`,
                            }}
                        >
                            <span style={{ color: C.textSecondary, fontSize: T.cap }}>{s.name}</span>
                            <span style={{ ...MONO, color: C.danger, fontSize: T.cap, fontWeight: T.w_semi }}>
                                {fmtPct(s.avg_change_pct ?? 0)}
                            </span>
                        </div>
                    ))}
                </div>
            </div>
            {(st.rotation_in?.length > 0 || st.rotation_out?.length > 0) && (
                <div style={{ marginTop: S.xs, display: "flex", gap: S.md, flexWrap: "wrap" }}>
                    {st.rotation_in?.length > 0 && (
                        <span style={{ color: C.success, fontSize: T.cap }}>IN: {st.rotation_in.join(", ")}</span>
                    )}
                    {st.rotation_out?.length > 0 && (
                        <span style={{ color: C.danger, fontSize: T.cap }}>OUT: {st.rotation_out.join(", ")}</span>
                    )}
                </div>
            )}
        </div>
    )
}

/* MetricCard — 단순 라벨 + 값 */
function MetricCard({ label, value, color = C.textPrimary }: { label: string; value: string; color?: string }) {
    return (
        <div style={miniMetric}>
            <span style={miniLabel}>{label}</span>
            <span style={{ ...miniValue, color }}>{value}</span>
        </div>
    )
}

/* EstateLandexCard — 부동산 자산 (별도 API) */
type EstateFacResp = {
    landex_score?: number
    grade?: string
    region?: string
    valuation?: number
    occupancy?: number
    [k: string]: any
}

function EstateLandexCard({ ticker, apiBase }: { ticker: string; apiBase: string }) {
    const [data, setData] = useState<EstateFacResp | null>(null)
    const [loading, setLoading] = useState(false)
    const [err, setErr] = useState<string | null>(null)

    useEffect(() => {
        const api = _normalizeApi(apiBase)
        if (!api || !ticker) return
        const ac = new AbortController()
        setLoading(true)
        fetch(`${api}/api/estate/landex?ticker=${encodeURIComponent(ticker)}`, { signal: ac.signal })
            .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
            .then((d) => { if (!ac.signal.aborted) { setData(d); setErr(null) } })
            .catch((e) => { if (!ac.signal.aborted) setErr(e.message) })
            .finally(() => { if (!ac.signal.aborted) setLoading(false) })
        return () => ac.abort()
    }, [ticker, apiBase])

    if (loading) return (
        <div style={subCard}>
            <span style={{ color: C.textTertiary, fontSize: T.cap }}>부동산 데이터 로딩 중…</span>
        </div>
    )
    if (err) return (
        <div style={subCard}>
            <span style={{ color: C.danger, fontSize: T.cap }}>부동산 데이터 실패: {err}</span>
        </div>
    )
    if (!data) return null

    return (
        <div style={subCard}>
            <span style={subCardCap}>부동산 자산 (LANDEX)</span>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: S.sm, marginTop: S.sm }}>
                {data.landex_score != null && (
                    <MetricCard label="LANDEX 점수" value={String(data.landex_score)} color={scoreColor(data.landex_score)} />
                )}
                {data.grade && <MetricCard label="등급" value={data.grade} />}
                {data.region && <MetricCard label="지역" value={data.region} />}
                {data.valuation != null && <MetricCard label="평가액" value={fmtLocale(data.valuation)} />}
                {data.occupancy != null && <MetricCard label="공실률" value={fmtPct(data.occupancy * 100, 1)} />}
            </div>
        </div>
    )
}

/* ◆ SUB COMPONENTS END ◆ */


/* ──────────────────────────────────────────────────────────────
 * ◆ MAIN COMPONENT (skeleton) — A.3 후속 turn 들에서 채움
 * ────────────────────────────────────────────────────────────── */

interface Props {
    dataUrl: string
    recUrl: string
    apiBase: string
    market: "kr" | "us"
    supabaseUrl?: string
    supabaseAnonKey?: string
}

const DATA_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json"
const REC_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/recommendations.json"
const API_BASE = "https://project-yw131.vercel.app"

type FilterTab = "all" | "buy" | "watch" | "avoid"
type DetailTab =
    | "overview" | "brain" | "sentiment" | "macro"
    | "predict" | "timing" | "niche" | "property" | "quant" | "group"

/* technical tab retract (2026-05-05): brain v5 의 technical_mean_reversion
 * 등 sub-score 가 흡수. 이건희 원칙 (사용자=결정자, 결과만 노출). */
const DETAIL_TABS: { key: DetailTab; label: string }[] = [
    { key: "overview", label: "개요" },
    { key: "brain", label: "브레인" },
    { key: "quant", label: "퀀트" },
    { key: "timing", label: "매매시점" },
    { key: "sentiment", label: "뉴스/수급" },
    { key: "macro", label: "매크로" },
    { key: "property", label: "부동산" },
    { key: "group", label: "관계회사" },
    { key: "niche", label: "틈새" },
    { key: "predict", label: "예측" },
]

export default function StockDashboardV2(props: Props) {
    const { dataUrl, recUrl, market = "kr" } = props
    const isUS = market === "us"

    const [data, setData] = useState<any>(null)
    const [fullRecMap, setFullRecMap] = useState<Record<string, any>>({})
    const [loadState, setLoadState] = useState<"loading" | "ok" | "error">("loading")
    const [filterTab, setFilterTab] = useState<FilterTab>("all")
    const [selected, setSelected] = useState<number>(0)
    const [detailTab, setDetailTab] = useState<DetailTab>("overview")

    /* portfolio.json fetch */
    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        setLoadState("loading")
        fetchJson(dataUrl, ac.signal)
            .then((d) => { if (!ac.signal.aborted) { setData(d); setLoadState("ok") } })
            .catch(() => { if (!ac.signal.aborted) setLoadState("error") })
        return () => ac.abort()
    }, [dataUrl])

    /* recommendations.json (full data) fetch — Mag7/depth 보강용 */
    useEffect(() => {
        const url = recUrl || REC_URL
        if (!url) return
        const ac = new AbortController()
        fetchJson(url, ac.signal)
            .then((arr: any) => {
                if (ac.signal.aborted || !Array.isArray(arr)) return
                const m: Record<string, any> = {}
                arr.forEach((r: any) => { if (r?.ticker) m[r.ticker] = r })
                setFullRecMap(m)
            })
            .catch(() => {})
        return () => ac.abort()
    }, [recUrl])

    if (loadState === "loading") {
        return (
            <div style={shell}>
                <div style={loadingBox}>
                    <span style={{ color: C.textTertiary, fontSize: T.body }}>데이터 로딩 중…</span>
                </div>
            </div>
        )
    }

    if (loadState === "error") {
        return (
            <div style={shell}>
                <div style={loadingBox}>
                    <span style={{ color: C.danger, fontSize: T.body }}>데이터 로드 실패</span>
                </div>
            </div>
        )
    }

    const allRecs: any[] = data?.recommendations || []
    const recs = allRecs.filter((r: any) =>
        isUS ? isUSMarket(r.market || "", r.currency) : !isUSMarket(r.market || "", r.currency)
    )
    const stale = stalenessInfo(data?.updated_at)

    /* filter counts */
    const buyCount = recs.filter((r) => r.recommendation === "BUY").length
    const watchCount = recs.filter((r) => r.recommendation === "WATCH").length
    const avoidCount = recs.filter((r) => r.recommendation === "AVOID").length

    const filtered = recs.filter((r: any) => {
        if (filterTab === "all") return true
        return (r.recommendation || "").toLowerCase() === filterTab
    })

    /* selected stock + fullRecMap merge */
    const rawStock = recs[selected] || null
    const stock = rawStock ? { ...rawStock, ...(fullRecMap[rawStock.ticker] || {}) } : null
    const mf = stock?.multi_factor || {}
    const breakdown = mf.factor_breakdown || {}
    const multiScore = mf.multi_score ?? stock?.safety_score ?? 0
    const multiC = scoreColor(multiScore)
    const rec = stock?.recommendation || "WATCH"
    const recC = recColor(rec)

    return (
        <div style={shell}>
            {/* 헤더 */}
            <div style={headerRow}>
                <div style={headerLeft}>
                    <span style={titleStyle}>종목 대시보드</span>
                    <span style={metaStyle}>
                        {isUS ? "US 시장" : "KR 시장"} · {recs.length}개 종목
                    </span>
                </div>
                {stale.label && (
                    <span style={{ ...MONO, color: stale.color, fontSize: T.cap, fontWeight: T.w_semi }}>
                        {stale.label}
                    </span>
                )}
            </div>

            {/* Filter tab row */}
            <div style={filterTabRow}>
                <FilterChip label={`전체 ${recs.length}`} active={filterTab === "all"} onClick={() => setFilterTab("all")} />
                <FilterChip label={`매수 ${buyCount}`} active={filterTab === "buy"} onClick={() => setFilterTab("buy")} color={C.accent} />
                <FilterChip label={`관망 ${watchCount}`} active={filterTab === "watch"} onClick={() => setFilterTab("watch")} color={C.watch} />
                <FilterChip label={`회피 ${avoidCount}`} active={filterTab === "avoid"} onClick={() => setFilterTab("avoid")} color={C.danger} />
            </div>

            <div style={hr} />

            {/* Body: list + detail (좌우 split) */}
            <div style={bodyRow}>
                {/* 좌측: 종목 list */}
                <div style={listPanel}>
                    {filtered.length === 0 ? (
                        <div style={emptyBox}>
                            <span style={{ color: C.textTertiary, fontSize: T.body }}>해당 등급 종목 없음</span>
                        </div>
                    ) : (
                        filtered.map((s: any) => {
                            const idx = recs.indexOf(s)
                            const isActive = idx === selected
                            return (
                                <StockListItem
                                    key={s.ticker}
                                    stock={s}
                                    isActive={isActive}
                                    isUS={isUS}
                                    onClick={() => setSelected(idx)}
                                />
                            )
                        })
                    )}
                </div>

                {/* 우측: detail panel */}
                {stock ? (
                    <div style={detailPanel}>
                        {/* Header: 게이지 + 정보 */}
                        <div style={detailHeader}>
                            <DetailGauge score={multiScore} grade={mf.grade || "—"} color={multiC} />
                            <div style={detailInfoBlock}>
                                {/* rec + market + company_type */}
                                <div style={{ display: "flex", alignItems: "center", gap: S.sm, flexWrap: "wrap" }}>
                                    <span style={{
                                        background: recC,
                                        color: rec === "WATCH" || rec === "BUY" || rec === "STRONG_BUY" ? C.bgPage : C.textPrimary,
                                        padding: `2px ${S.sm}px`,
                                        borderRadius: R.sm,
                                        fontSize: T.cap, fontWeight: T.w_bold,
                                        letterSpacing: "0.05em",
                                    }}>
                                        {rec}
                                    </span>
                                    <span style={{ color: C.textTertiary, fontSize: T.cap }}>{stock.market}</span>
                                    {stock.company_type && (
                                        <span style={{
                                            fontSize: T.cap, fontWeight: T.w_bold,
                                            color: C.accent, background: C.accentSoft,
                                            border: `1px solid ${C.accent}33`,
                                            borderRadius: R.sm,
                                            padding: `2px ${S.sm}px`,
                                            letterSpacing: "0.03em",
                                        }}>
                                            {stock.company_type}
                                        </span>
                                    )}
                                </div>
                                {/* 종목명 + business tagline */}
                                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                    <span style={{
                                        color: C.textPrimary, fontSize: T.h2, fontWeight: T.w_bold,
                                        letterSpacing: "-0.5px",
                                    }}>
                                        {stock.name}
                                    </span>
                                    <span style={{ color: C.textSecondary, fontSize: T.cap }}>
                                        {getBusinessTagline(stock)}
                                    </span>
                                </div>
                                {/* ticker · price + sparkline */}
                                <div style={{ display: "flex", alignItems: "center", gap: S.md, flexWrap: "wrap" }}>
                                    <span style={{ ...MONO, color: C.textSecondary, fontSize: T.body, fontWeight: T.w_semi }}>
                                        {stock.ticker} · {formatPrice(stock.price, isUS)}
                                    </span>
                                    {(stock.sparkline || []).length > 1 && (
                                        <Sparkline
                                            data={stock.sparkline}
                                            width={140}
                                            height={28}
                                            color={stock.sparkline[stock.sparkline.length - 1] >= stock.sparkline[0] ? C.up : C.down}
                                        />
                                    )}
                                </div>
                                {/* AI verdict */}
                                {stock.ai_verdict && (
                                    <div style={{
                                        color: C.textSecondary, fontSize: T.cap,
                                        lineHeight: T.lh_loose,
                                        background: C.bgPage,
                                        border: `1px solid ${C.border}`,
                                        borderRadius: R.sm,
                                        padding: `${S.xs}px ${S.md}px`,
                                    }}>
                                        {stock.ai_verdict}
                                    </div>
                                )}
                                {/* Trend block */}
                                <TrendBlock stock={stock} isUS={isUS} />
                            </div>
                        </div>

                        <div style={hr} />

                        {/* 5팩터 바 */}
                        <FactorBars breakdown={breakdown} />

                        <div style={hr} />

                        {/* TimingSignal + TradePlan */}
                        <TimingSignalCard ts={stock.timing_signal} />
                        <TradePlanSection plan={stock.trade_plan} isUS={isUS} />

                        <div style={hr} />

                        {/* Detail tab bar */}
                        <DetailTabBar current={detailTab} onChange={setDetailTab} />

                        {/* Tab content */}
                        <div style={{ marginTop: S.md }}>
                            {detailTab === "overview" && (
                                <OverviewTab stock={stock} data={data} mf={mf} isUS={isUS} />
                            )}
                            {detailTab === "brain" && (
                                <BrainTab stock={stock} />
                            )}
                            {detailTab === "sentiment" && (
                                <SentimentTab stock={stock} isUS={isUS} />
                            )}
                            {detailTab !== "overview" && detailTab !== "brain" &&
                                detailTab !== "sentiment" && (
                                <div style={{
                                    background: C.bgCard, border: `1px solid ${C.border}`,
                                    borderRadius: R.md, padding: `${S.lg}px ${S.xl}px`,
                                    display: "flex", flexDirection: "column", gap: S.sm,
                                }}>
                                    <span style={{
                                        color: C.accent, fontSize: T.cap, fontWeight: T.w_bold,
                                        letterSpacing: "0.08em", textTransform: "uppercase",
                                    }}>
                                        {DETAIL_TABS.find((t) => t.key === detailTab)?.label || detailTab}
                                    </span>
                                    <span style={{ color: C.textSecondary, fontSize: T.cap, lineHeight: T.lh_normal }}>
                                        상세 내용은 다음 turn 들에서 박힙니다.
                                    </span>
                                </div>
                            )}
                        </div>
                    </div>
                ) : (
                    <div style={detailPanelPlaceholder}>
                        <span style={{ color: C.textTertiary, fontSize: T.body }}>종목 선택</span>
                    </div>
                )}
            </div>
        </div>
    )
}


/* ─────────── DetailGauge — 원형 게이지 (multi_score) ─────────── */
function DetailGauge({ score, grade, color }: { score: number; grade: string; color: string }) {
    const radius = 48
    const stroke = 6
    const size = (radius + stroke) * 2
    const circumference = 2 * Math.PI * radius
    const progress = (score / 100) * circumference

    return (
        <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
            <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
                <circle
                    cx={radius + stroke} cy={radius + stroke} r={radius}
                    fill="none" stroke={C.bgElevated} strokeWidth={stroke}
                />
                <circle
                    cx={radius + stroke} cy={radius + stroke} r={radius}
                    fill="none" stroke={color} strokeWidth={stroke}
                    strokeDasharray={circumference} strokeDashoffset={circumference - progress}
                    strokeLinecap="round"
                    transform={`rotate(-90 ${radius + stroke} ${radius + stroke})`}
                    style={{ transition: "stroke-dashoffset 0.6s ease" }}
                />
            </svg>
            <div style={{
                position: "absolute", top: "50%", left: "50%",
                transform: "translate(-50%, -50%)",
                display: "flex", flexDirection: "column", alignItems: "center", gap: 2,
            }}>
                <span style={{ ...MONO, color, fontSize: T.h2, fontWeight: T.w_black, lineHeight: 1 }}>
                    {score}
                </span>
                <span style={{
                    color: C.textTertiary, fontSize: 9, fontWeight: T.w_semi,
                    letterSpacing: "0.05em",
                }}>
                    {grade}
                </span>
            </div>
        </div>
    )
}


/* ─────────── FactorBars — 5 팩터 (fundamental/technical/sentiment/flow/macro) ─────────── */
function FactorBars({ breakdown }: { breakdown: Record<string, number> }) {
    const factors: { key: string; label: string }[] = [
        { key: "fundamental", label: "펀더멘털" },
        { key: "technical", label: "기술적" },
        { key: "sentiment", label: "뉴스" },
        { key: "flow", label: "수급" },
        { key: "macro", label: "매크로" },
    ]

    return (
        <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))",
            gap: S.sm,
        }}>
            {factors.map(({ key, label }) => {
                const val = breakdown[key] || 0
                const c = scoreColor(val)
                return (
                    <div
                        key={key}
                        style={{
                            background: C.bgCard,
                            border: `1px solid ${C.border}`,
                            borderRadius: R.sm,
                            padding: `${S.sm}px ${S.md}px`,
                            display: "flex", flexDirection: "column", gap: S.xs,
                        }}
                    >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                            <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med }}>
                                {label}
                            </span>
                            <span style={{ ...MONO, color: c, fontSize: T.body, fontWeight: T.w_bold }}>
                                {val}
                            </span>
                        </div>
                        <div style={{
                            width: "100%", height: 3,
                            background: C.bgElevated,
                            borderRadius: 2, overflow: "hidden",
                        }}>
                            <div style={{
                                width: `${val}%`, height: "100%",
                                background: c, transition: "width 0.6s ease",
                            }} />
                        </div>
                    </div>
                )
            })}
        </div>
    )
}


/* ─────────── OverviewTab — 개요 (AI 분석 + 메트릭 + 이벤트 + 뉴스) ─────────── */
function OverviewTab({
    stock, data, mf, isUS,
}: { stock: any; data: any; mf: any; isUS: boolean }) {
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.md }}>
            {/* AI 분석 카드들 */}
            <InsightSection stock={stock} />

            {/* 메트릭 grid */}
            <MetricsGridSection stock={stock} isUS={isUS} />

            {/* 이벤트 (실적발표 / 타이밍 / signals) */}
            <EventsSection stock={stock} mf={mf} />

            {/* 뉴스 */}
            <NewsSection stock={stock} data={data} />

            {/* US 전용 */}
            {isUS && <USOnlySection stock={stock} />}
        </div>
    )
}


/* ─────────── 1. AI 분석 카드 (gold / silver / claude / dual_consensus) ─────────── */
function InsightSection({ stock }: { stock: any }) {
    return (
        <div style={{
            background: C.bgCard, border: `1px solid ${C.border}`,
            borderRadius: R.md, padding: `${S.md}px ${S.lg}px`,
            display: "flex", flexDirection: "column", gap: S.sm,
        }}>
            <span style={subCardCap}>AI 분석</span>

            {/* Gold insight */}
            <div style={{ display: "flex", alignItems: "flex-start", gap: S.sm }}>
                <span style={{
                    background: C.watch, color: C.bgPage,
                    fontSize: 9, fontWeight: T.w_black,
                    padding: `2px ${S.xs}px`, borderRadius: R.sm,
                    letterSpacing: "0.05em", flexShrink: 0,
                }}>
                    GOLD
                </span>
                <span style={{ color: C.textPrimary, fontSize: T.cap, lineHeight: T.lh_normal, flex: 1 }}>
                    {stock.gold_insight || "데이터 수집 중"}
                </span>
            </div>

            {/* Silver insight */}
            <div style={{ display: "flex", alignItems: "flex-start", gap: S.sm }}>
                <span style={{
                    background: C.textTertiary, color: C.bgPage,
                    fontSize: 9, fontWeight: T.w_black,
                    padding: `2px ${S.xs}px`, borderRadius: R.sm,
                    letterSpacing: "0.05em", flexShrink: 0,
                }}>
                    SILVER
                </span>
                <span style={{ color: C.textSecondary, fontSize: T.cap, lineHeight: T.lh_normal, flex: 1 }}>
                    {stock.silver_insight || "데이터 수집 중"}
                </span>
            </div>

            {/* Claude analysis */}
            {stock.claude_analysis && (
                <ClaudeAnalysisCard ca={stock.claude_analysis} />
            )}

            {/* Dual consensus */}
            {stock.dual_consensus && (
                <DualConsensusCard dc={stock.dual_consensus} />
            )}
        </div>
    )
}

function ClaudeAnalysisCard({ ca }: { ca: any }) {
    const agrees = !!ca.agrees
    const c = agrees ? C.success : C.caution
    const [open, setOpen] = useState(false)
    const hasDetail = !!ca.conviction_note ||
        (ca.hidden_risks?.length > 0) ||
        (ca.hidden_opportunities?.length > 0)
    return (
        <div style={{
            background: agrees ? `${C.success}1A` : C.bgPage,
            border: `1px solid ${agrees ? `${C.success}33` : C.border}`,
            borderRadius: R.sm,
            padding: `${S.sm}px ${S.md}px`,
            display: "flex", flexDirection: "column", gap: S.xs,
        }}>
            <div style={{ display: "flex", alignItems: "center", gap: S.xs, flexWrap: "wrap" }}>
                <span style={{
                    background: `${C.info}33`, color: C.info,
                    fontSize: T.cap, fontWeight: T.w_bold,
                    padding: `2px ${S.xs}px`, borderRadius: R.sm,
                    letterSpacing: "0.05em",
                }}>
                    CLAUDE
                </span>
                <span style={{ color: c, fontSize: T.cap, fontWeight: T.w_semi }}>
                    {agrees ? "Gemini 동의" : "Gemini 반론"}
                </span>
                {ca.override && (
                    <span style={{ color: C.danger, fontSize: T.cap, fontWeight: T.w_bold }}>
                        → {ca.override}
                    </span>
                )}
            </div>
            <span style={{ color: C.textPrimary, fontSize: T.cap, lineHeight: T.lh_normal }}>
                {ca.verdict}
            </span>
            {hasDetail && (
                <button
                    onClick={() => setOpen(!open)}
                    style={{
                        background: "transparent", border: "none",
                        color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_semi,
                        cursor: "pointer", padding: 0, textAlign: "left",
                        fontFamily: FONT, letterSpacing: "0.02em",
                    }}
                >
                    {open ? "▼ 상세 접기" : "▶ 상세 펼치기"}
                </button>
            )}
            {open && hasDetail && (
                <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                    {ca.conviction_note && (
                        <span style={{ color: C.textSecondary, fontSize: T.cap, lineHeight: T.lh_normal }}>
                            {ca.conviction_note}
                        </span>
                    )}
                    {ca.hidden_risks?.length > 0 && (
                        <span style={{ color: C.danger, fontSize: T.cap, lineHeight: T.lh_normal }}>
                            숨겨진 리스크: {ca.hidden_risks.join(" · ")}
                        </span>
                    )}
                    {ca.hidden_opportunities?.length > 0 && (
                        <span style={{ color: C.success, fontSize: T.cap, lineHeight: T.lh_normal }}>
                            숨겨진 기회: {ca.hidden_opportunities.join(" · ")}
                        </span>
                    )}
                </div>
            )}
        </div>
    )
}

function DualConsensusCard({ dc }: { dc: any }) {
    const review = !!dc.manual_review_required
    return (
        <div style={{
            background: C.bgPage,
            border: `1px solid ${review ? C.border : `${C.info}33`}`,
            borderRadius: R.sm,
            padding: `${S.sm}px ${S.md}px`,
            display: "flex", flexDirection: "column", gap: S.xs,
        }}>
            <div style={{ display: "flex", alignItems: "center", gap: S.xs, flexWrap: "wrap" }}>
                <span style={{
                    background: C.info, color: C.bgPage,
                    fontSize: T.cap, fontWeight: T.w_bold,
                    padding: `2px ${S.xs}px`, borderRadius: R.sm,
                    letterSpacing: "0.05em",
                }}>
                    HYBRID
                </span>
                <span style={{ color: C.info, fontSize: T.cap, fontWeight: T.w_semi }}>
                    최종 {dc.final_recommendation} · 신뢰 {dc.final_confidence}
                </span>
                <span style={{
                    color: review ? C.danger : C.success,
                    fontSize: T.cap, fontWeight: T.w_semi,
                }}>
                    {review ? "수동검토 필요" : `합의 ${dc.conflict_level}`}
                </span>
            </div>
            <span style={{ color: C.textSecondary, fontSize: T.cap, lineHeight: T.lh_normal }}>
                Gemini {dc.gemini_recommendation} ({dc.gemini_confidence})
                {" · "}
                Claude {dc.claude_recommendation} ({dc.claude_confidence})
            </span>
        </div>
    )
}


/* ─────────── 2. 메트릭 grid ─────────── */
function MetricsGridSection({ stock, isUS }: { stock: any; isUS: boolean }) {
    const debtNum = Number(stock.debt_ratio) || 0
    const opNum = Number(stock.operating_margin) || 0
    const roeNum = Number(stock.roe) || 0
    const dropNum = Number(stock.drop_from_high_pct) || 0

    return (
        <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))",
            gap: S.sm,
        }}>
            <MetricCard label="PER" value={fmtFixed(stock.per, 1)} />
            <MetricCard
                label="고점대비"
                value={fmtFixed(stock.drop_from_high_pct, 1, "%")}
                color={dropNum <= -20 ? C.accent : C.textPrimary}
            />
            <MetricCard label="배당률" value={fmtFixed(stock.div_yield, 1, "%")} />
            <MetricCard
                label="거래대금"
                value={stock.trading_value ? formatVolume(stock.trading_value, isUS) : "—"}
            />
            <MetricCard
                label="시총"
                value={stock.market_cap ? formatMarketCap(stock.market_cap, isUS) : "—"}
            />
            <MetricCard label="안심점수" value={String(stock.safety_score || 0)} />
            <MetricCard
                label="부채비율"
                value={fmtFixed(stock.debt_ratio, 0, "%")}
                color={debtNum > 100 ? C.danger : C.success}
            />
            <MetricCard
                label="영업이익률"
                value={fmtFixed(Number.isFinite(opNum) ? opNum * 100 : NaN, 1, "%")}
                color={opNum > 0.1 ? C.success : opNum < 0 ? C.danger : C.watch}
            />
            <MetricCard
                label="ROE"
                value={fmtFixed(Number.isFinite(roeNum) ? roeNum * 100 : NaN, 1, "%")}
                color={roeNum > 0.15 ? C.success : roeNum < 0 ? C.danger : C.textPrimary}
            />
        </div>
    )
}


/* ─────────── 3. 이벤트 (실적발표 / 타이밍 / signals) ─────────── */
function EventsSection({ stock, mf }: { stock: any; mf: any }) {
    const hasEarnings = !!stock.earnings?.next_earnings
    const hasTiming = !!stock.timing
    const hasSignals = mf.all_signals?.length > 0
    if (!hasEarnings && !hasTiming && !hasSignals) return null

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.sm }}>
            {/* 실적발표 */}
            {hasEarnings && (
                <div style={{
                    display: "flex", alignItems: "center", gap: S.sm,
                    background: `${C.watch}1A`,
                    border: `1px solid ${C.watch}33`,
                    borderRadius: R.sm,
                    padding: `${S.xs}px ${S.md}px`,
                }}>
                    <span style={{ color: C.watch, fontSize: T.cap, fontWeight: T.w_bold, letterSpacing: "0.05em" }}>
                        실적발표
                    </span>
                    <span style={{ ...MONO, color: C.textPrimary, fontSize: T.cap }}>
                        {stock.earnings.next_earnings}
                    </span>
                </div>
            )}

            {/* 타이밍 요약 */}
            {hasTiming && (
                <div style={{
                    display: "flex", alignItems: "center", gap: S.md,
                    background: C.bgElevated,
                    borderRadius: R.sm,
                    padding: `${S.sm}px ${S.md}px`,
                }}>
                    <div style={{
                        width: 32, height: 32, borderRadius: "50%",
                        background: stock.timing.color || C.textTertiary,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        flexShrink: 0,
                    }}>
                        <span style={{ ...MONO, color: C.bgPage, fontSize: T.cap, fontWeight: T.w_black }}>
                            {stock.timing.timing_score}
                        </span>
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                        <span style={{ color: stock.timing.color || C.textTertiary, fontSize: T.cap, fontWeight: T.w_bold }}>
                            {stock.timing.label || "—"}
                        </span>
                        <span style={{ color: C.textTertiary, fontSize: T.cap, marginLeft: S.sm }}>
                            {stock.timing.reasons?.[0] || ""}
                        </span>
                    </div>
                </div>
            )}

            {/* All signals */}
            {hasSignals && (
                <div style={{ display: "flex", gap: S.xs, flexWrap: "wrap" }}>
                    {mf.all_signals.map((sig: string, i: number) => (
                        <span
                            key={i}
                            style={{
                                background: C.accentSoft,
                                border: `1px solid ${C.accent}33`,
                                color: C.accent,
                                fontSize: T.cap, fontWeight: T.w_semi,
                                padding: `2px ${S.sm}px`,
                                borderRadius: R.sm,
                                letterSpacing: "0.02em",
                            }}
                        >
                            {sig}
                        </span>
                    ))}
                </div>
            )}
        </div>
    )
}


/* ─────────── 4. 뉴스 (종목 + 글로벌) ─────────── */
function NewsSection({ stock, data }: { stock: any; data: any }) {
    const links: any[] = stock?.sentiment?.top_headline_links || []
    const details: any[] = stock?.sentiment?.detail || []
    const plain: string[] = stock?.sentiment?.top_headlines || []
    const richItems = links.length > 0 ? links.slice(0, 5) : details.filter((d: any) => d.url).slice(0, 5)
    const stockHasNews = richItems.length > 0 || plain.length > 0
    const globalNews: any[] = data?.headlines || []

    if (!stockHasNews && globalNews.length === 0) return null

    /* 종목+시장 단일 박스 통합 (2026-05-05 retrospective).
     * 종목 row 5 + 시장 row 6 inline. 시장 row 는 source/time 으로 자동 구분. */
    return (
        <div style={{
            background: C.bgCard, border: `1px solid ${C.border}`,
            borderRadius: R.md, padding: `${S.md}px ${S.lg}px`,
            display: "flex", flexDirection: "column", gap: S.xs,
        }}>
            <span style={subCardCap}>최신 뉴스</span>

            {/* 종목 뉴스 (분석 라벨 우선, plain fallback) */}
            {richItems.length > 0
                ? richItems.map((item: any, i: number) => {
                    const sentColor = item.label === "positive" ? C.success
                        : item.label === "negative" ? C.danger
                        : C.textTertiary
                    return (
                        <a
                            key={`s${i}`}
                            href={item.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={newsLink}
                        >
                            {item.label && (
                                <span style={{
                                    width: 4, height: 4, borderRadius: "50%",
                                    background: sentColor, flexShrink: 0,
                                }} />
                            )}
                            <span style={newsTitle}>{item.title}</span>
                            <span style={{ color: C.textTertiary, fontSize: T.cap, flexShrink: 0 }}>↗</span>
                        </a>
                    )
                })
                : plain.slice(0, 5).map((h: string, i: number) => (
                    <div key={`p${i}`} style={{ ...newsLink, cursor: "default" }}>
                        <span style={newsTitle}>{h}</span>
                    </div>
                ))
            }

            {/* 시장 뉴스 row (source/time 표시로 자동 구분) */}
            {globalNews.slice(0, 6).map((h: any, i: number) => {
                const sc = h.sentiment === "positive" ? C.success
                    : h.sentiment === "negative" ? C.danger
                    : C.textTertiary
                const href = h.link || h.url || ""
                const inner = (
                    <>
                        <span style={{
                            width: 4, height: 4, borderRadius: "50%",
                            background: sc, flexShrink: 0,
                        }} />
                        <span style={newsTitle}>{h.title}</span>
                        {h.source && (
                            <span style={{ color: C.textTertiary, fontSize: T.cap, flexShrink: 0 }}>
                                {h.source}
                            </span>
                        )}
                        {h.time && (
                            <span style={{ ...MONO, color: C.textDisabled, fontSize: T.cap, flexShrink: 0 }}>
                                {h.time.slice(5, 16)}
                            </span>
                        )}
                        {href && (
                            <span style={{ color: C.textTertiary, fontSize: T.cap, flexShrink: 0 }}>↗</span>
                        )}
                    </>
                )
                return href ? (
                    <a key={`g${i}`} href={href} target="_blank" rel="noopener noreferrer" style={newsLink}>
                        {inner}
                    </a>
                ) : (
                    <div key={`g${i}`} style={{ ...newsLink, cursor: "default" }}>{inner}</div>
                )
            })}
        </div>
    )
}


/* ─────────── 5. US 전용 (프리/애프터, 애널리스트, 실적surprise, Yahoo) ─────────── */
function USOnlySection({ stock }: { stock: any }) {
    const pa = stock.pre_after_market
    const ac = stock.analyst_consensus
    const es: any[] = stock.earnings_surprises || []
    const hasPreAfter = pa && (pa.pre_price || pa.after_price)
    const hasAnalyst = ac && (ac.buy > 0 || ac.hold > 0 || ac.sell > 0)
    const hasSurprise = Array.isArray(es) && es.length > 0

    if (!hasPreAfter && !hasAnalyst && !hasSurprise) return (
        <a
            href={`https://finance.yahoo.com/quote/${stock.ticker}`}
            target="_blank"
            rel="noopener noreferrer"
            style={{
                display: "inline-flex", alignItems: "center", gap: S.xs,
                padding: `${S.xs}px ${S.md}px`,
                background: C.bgElevated,
                border: `1px solid ${C.border}`,
                borderRadius: R.sm,
                color: C.info, fontSize: T.cap, fontWeight: T.w_semi,
                textDecoration: "none",
                width: "fit-content",
            }}
        >
            Yahoo Finance ↗
        </a>
    )

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.md }}>
            {/* 프리/애프터마켓 */}
            {hasPreAfter && (
                <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                    <span style={subCardCap}>프리 / 애프터마켓</span>
                    <div style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fit, minmax(100px, 1fr))",
                        gap: S.sm,
                    }}>
                        {pa.pre_price != null && (
                            <MetricCard
                                label="프리마켓"
                                value={formatPrice(pa.pre_price, true)}
                                color={pa.pre_change_pct > 0 ? C.success : pa.pre_change_pct < 0 ? C.danger : C.textPrimary}
                            />
                        )}
                        {pa.pre_change_pct != null && (
                            <MetricCard
                                label="프리 변동"
                                value={fmtPct(pa.pre_change_pct)}
                                color={pa.pre_change_pct > 0 ? C.up : C.down}
                            />
                        )}
                        {pa.after_price != null && (
                            <MetricCard
                                label="애프터마켓"
                                value={formatPrice(pa.after_price, true)}
                                color={(pa.after_change_pct || 0) > 0 ? C.success : (pa.after_change_pct || 0) < 0 ? C.danger : C.textPrimary}
                            />
                        )}
                    </div>
                </div>
            )}

            {/* 애널리스트 */}
            {hasAnalyst && (
                <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                    <span style={subCardCap}>애널리스트 의견</span>
                    <div style={{ display: "flex", gap: S.xs, flexWrap: "wrap" }}>
                        <ConsensusBadge label="매수" count={ac.buy} color={C.success} />
                        <ConsensusBadge label="중립" count={ac.hold} color={C.watch} />
                        <ConsensusBadge label="매도" count={ac.sell} color={C.danger} />
                    </div>
                    {ac.target_mean > 0 && (
                        <div style={{
                            display: "grid",
                            gridTemplateColumns: "repeat(auto-fit, minmax(100px, 1fr))",
                            gap: S.sm,
                        }}>
                            <MetricCard label="목표가" value={formatPrice(ac.target_mean, true)} />
                            <MetricCard
                                label="업사이드"
                                value={fmtPct(ac.upside_pct)}
                                color={ac.upside_pct > 0 ? C.up : C.down}
                            />
                        </div>
                    )}
                </div>
            )}

            {/* 실적 서프라이즈 */}
            {hasSurprise && (
                <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                    <span style={subCardCap}>실적 서프라이즈</span>
                    <div style={{
                        display: "grid",
                        gridTemplateColumns: `repeat(${Math.min(es.length, 4)}, 1fr)`,
                        gap: S.xs,
                    }}>
                        {es.slice(0, 4).map((e: any, i: number) => {
                            const sp = e.surprise_pct || 0
                            return (
                                <MetricCard
                                    key={i}
                                    label={e.period || `Q${4 - i}`}
                                    value={fmtPct(sp, 1)}
                                    color={sp > 0 ? C.success : sp < 0 ? C.danger : C.textTertiary}
                                />
                            )
                        })}
                    </div>
                </div>
            )}

            {/* Yahoo 링크 */}
            <a
                href={`https://finance.yahoo.com/quote/${stock.ticker}`}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                    display: "inline-flex", alignItems: "center", gap: S.xs,
                    padding: `${S.xs}px ${S.md}px`,
                    background: C.bgElevated,
                    border: `1px solid ${C.border}`,
                    borderRadius: R.sm,
                    color: C.info, fontSize: T.cap, fontWeight: T.w_semi,
                    textDecoration: "none",
                    width: "fit-content",
                }}
            >
                Yahoo Finance ↗
            </a>
        </div>
    )
}

function ConsensusBadge({ label, count, color }: { label: string; count: number; color: string }) {
    return (
        <span style={{
            background: color, color: C.bgPage,
            fontSize: T.cap, fontWeight: T.w_bold,
            padding: `2px ${S.sm}px`,
            borderRadius: R.sm,
            letterSpacing: "0.05em",
            fontFamily: FONT,
        }}>
            {label} {count}
        </span>
    )
}


/* ─────────── BrainTab — Brain v5 분해 (점수/팩트/레드플래그/오버라이드/XAI/리포트/DART) ─────────── */
const GRADE_COLOR_MAP: Record<string, string> = {
    STRONG_BUY: C.strongBuy,
    BUY: C.buy,
    WATCH: C.watch,
    CAUTION: C.caution,
    AVOID: C.avoid,
}

const FACT_COMPONENT_LABELS: Record<string, string> = {
    multi_factor: "멀티팩터",
    consensus: "내부모델합의",
    prediction: "AI예측",
    backtest: "백테스트",
    timing: "타이밍",
    commodity_margin: "원자재",
    export_trade: "수출입",
    moat_quality: "모트(해자)",
    graham_value: "그레이엄가치",
    canslim_growth: "CANSLIM성장",
    kis_analysis: "KIS분석",
    alpha_combined: "퀀트알파",
    technical_mean_reversion: "기술MR(IC)",
    kr_fundamental_mean_reversion: "KR펀더멘털MR(DART)",
    analyst_report: "증권사리포트",
    dart_health: "DART건전성",
}

const OVERRIDE_LABELS: Record<string, string> = {
    contrarian_upgrade: "역발상↑",
    quadrant_unfavored: "분면불리↓",
    cape_bubble: "CAPE버블cap",
    panic_stage_3: "패닉3cap",
    panic_stage_4: "패닉4cap",
    vix_spread_panic: "VIX패닉cap",
    yield_defense: "수익률방어cap",
    sector_quadrant_drift: "섹터드리프트",
    ai_upside_relax: "AI호재완화",
}

const AVOID_TOOLTIP =
    "AVOID 부여 조건: 펀더멘털 결함 (감사거절·분식·상폐 위험 등 has_critical) 또는 매크로 위기 cap. 단순 저점수는 CAUTION."

function formatRedFlagDetail(d: any): string {
    if (!d || typeof d !== "object") return String(d || "")
    const text = d.text || String(d)
    const fresh = d.freshness
    if (!fresh || fresh === "FRESH") return text
    const days = d.days_since_event != null ? `${d.days_since_event}d` : ""
    return `${text} [${fresh === "EXPIRED" ? "EXPIRED" : "STALE"}${days ? " " + days : ""}]`
}

function BrainTab({ stock }: { stock: any }) {
    const brain = stock?.verity_brain || {}
    const bs = brain.brain_score ?? null

    if (bs === null) {
        return (
            <div style={{
                background: C.bgCard, border: `1px solid ${C.border}`,
                borderRadius: R.md, padding: `${S.xl}px ${S.lg}px`,
                color: C.textTertiary, fontSize: T.cap, textAlign: "center",
            }}>
                Verity Brain 데이터는 파이프라인 실행 후 표시됩니다
            </div>
        )
    }

    const fs = brain.fact_score || {}
    const ss = brain.sentiment_score || {}
    const vci = brain.vci || {}
    const rf = brain.red_flags || {}
    const grade = brain.grade || "WATCH"
    const gradeLabel = brain.grade_label || "—"
    const gc = GRADE_COLOR_MAP[grade] || C.textTertiary
    const sb = stock?.score_breakdown || null
    const vciVal = vci.vci ?? 0
    const vciColor = vciVal > 15 ? C.accent : vciVal < -15 ? C.danger : C.textTertiary

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.md }}>
            {/* 1. Hero — Brain score circle + 팩트/심리/VCI */}
            <BrainHeroSection
                bs={bs}
                gc={gc}
                grade={grade}
                gradeLabel={gradeLabel}
                fs={fs}
                ss={ss}
                vciVal={vciVal}
                vciColor={vciColor}
            />

            {/* 2. Signals — VCI 시그널 / 13F 스마트머니 */}
            {((vci.signal && vci.signal !== "ALIGNED") ||
                (typeof brain.inst_13f_bonus === "number" && brain.inst_13f_bonus > 0)) && (
                <BrainSignalsSection brain={brain} vci={vci} vciVal={vciVal} vciColor={vciColor} />
            )}

            {/* 3. 팩트 컴포넌트 분해 */}
            {fs.components && Object.keys(fs.components).length > 0 && (
                <FactComponentsSection components={fs.components} />
            )}

            {/* 4. 레드플래그 */}
            {(rf.auto_avoid?.length > 0 || rf.downgrade?.length > 0 ||
              rf.auto_avoid_detail?.length > 0 || rf.downgrade_detail?.length > 0) && (
                <RedFlagsSection rf={rf} />
            )}

            {/* 5. XAI 점수 분해 (override 배지는 retract 2026-05-05) */}
            {sb && <ScoreBreakdownSection sb={sb} gc={gc} />}

            {/* 7. 증권사 리포트 AI 요약 */}
            {stock?.analyst_report_summary?.report_count > 0 && (
                <AnalystReportSection ar={stock.analyst_report_summary} />
            )}

            {/* 8. DART 사업 건전성 */}
            {stock?.dart_business_analysis?.business_health_score != null && (
                <BusinessHealthSection da={stock.dart_business_analysis} />
            )}

            {/* 9. 판단 근거 */}
            {brain.reasoning && (
                <div style={{
                    background: C.bgCard, border: `1px solid ${C.border}`,
                    borderRadius: R.md, padding: `${S.md}px ${S.lg}px`,
                }}>
                    <span style={subCardCap}>판단 근거</span>
                    <span style={{
                        color: C.textSecondary, fontSize: T.cap,
                        lineHeight: T.lh_normal, marginTop: S.xs, display: "block",
                    }}>
                        {brain.reasoning}
                    </span>
                </div>
            )}
        </div>
    )
}

function BrainHeroSection({
    bs, gc, grade, gradeLabel, fs, ss, vciVal, vciColor,
}: {
    bs: number; gc: string; grade: string; gradeLabel: string;
    fs: any; ss: any; vciVal: number; vciColor: string;
}) {
    const radius = 50, stroke = 8
    const size = (radius + stroke) * 2
    const circumference = 2 * Math.PI * radius
    const progress = (bs / 100) * circumference

    return (
        <div style={{
            background: C.bgCard, border: `1px solid ${C.border}`,
            borderRadius: R.md, padding: `${S.md}px ${S.lg}px`,
            display: "flex", alignItems: "center", gap: S.xl,
        }}>
            {/* Brain score circle */}
            <div style={{ position: "relative", width: 116, height: 116, flexShrink: 0 }}>
                <svg width={116} height={116} viewBox={`0 0 ${size} ${size}`}>
                    <circle
                        cx={radius + stroke} cy={radius + stroke} r={radius}
                        fill="none" stroke={C.bgElevated} strokeWidth={stroke}
                    />
                    <circle
                        cx={radius + stroke} cy={radius + stroke} r={radius}
                        fill="none" stroke={gc} strokeWidth={stroke}
                        strokeDasharray={circumference} strokeDashoffset={circumference - progress}
                        strokeLinecap="round"
                        transform={`rotate(-90 ${radius + stroke} ${radius + stroke})`}
                        style={{ transition: "stroke-dashoffset 0.6s ease" }}
                    />
                </svg>
                <div style={{
                    position: "absolute", inset: 0,
                    display: "flex", flexDirection: "column",
                    alignItems: "center", justifyContent: "center",
                }}>
                    <span style={{ ...MONO, color: gc, fontSize: 26, fontWeight: T.w_black, lineHeight: 1 }}>
                        {bs}
                    </span>
                    <span
                        style={{
                            color: gc, fontSize: T.cap, fontWeight: T.w_bold,
                            cursor: grade === "AVOID" ? "help" : "default",
                            marginTop: 2,
                        }}
                        title={grade === "AVOID" ? AVOID_TOOLTIP : undefined}
                    >
                        {gradeLabel}
                    </span>
                </div>
            </div>

            {/* 팩트 / 심리 / VCI */}
            <div style={{ display: "flex", flexDirection: "column", gap: S.sm, flex: 1, minWidth: 0 }}>
                <span style={{
                    color: C.textPrimary, fontSize: T.sub, fontWeight: T.w_black,
                    letterSpacing: "0.02em",
                }}>
                    Verity Brain
                </span>
                <div style={{ display: "flex", gap: S.lg, flexWrap: "wrap" }}>
                    <BrainHeroMetric label="팩트" value={fs.score ?? "—"} color={C.success} termKey="FACT_SCORE" />
                    <BrainHeroMetric label="심리" value={ss.score ?? "—"} color={C.info} />
                    <BrainHeroMetric
                        label="VCI"
                        value={vciVal === 0 ? 0 : `${vciVal >= 0 ? "+" : ""}${vciVal}`}
                        color={vciColor}
                    />
                </div>
            </div>
        </div>
    )
}

function BrainHeroMetric({
    label, value, color, termKey,
}: { label: string; value: any; color: string; termKey?: string }) {
    const labelEl = (
        <span style={{
            color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med,
            letterSpacing: "0.03em",
        }}>
            {label}
        </span>
    )
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            {termKey ? <TermTooltip termKey={termKey}>{labelEl}</TermTooltip> : labelEl}
            <span style={{ ...MONO, color, fontSize: T.title, fontWeight: T.w_black, lineHeight: 1.1 }}>
                {value}
            </span>
        </div>
    )
}

function BrainSignalsSection({
    brain, vci, vciVal, vciColor,
}: { brain: any; vci: any; vciVal: number; vciColor: string }) {
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
            {vci.signal && vci.signal !== "ALIGNED" && (
                <div style={{
                    background: vciVal > 15 ? `${C.accent}10` : `${C.danger}10`,
                    border: `1px solid ${vciColor}40`,
                    borderRadius: R.sm,
                    padding: `${S.sm}px ${S.md}px`,
                    display: "flex", alignItems: "center", gap: S.sm,
                }}>
                    <span style={{
                        ...MONO, color: vciColor, fontSize: T.cap, fontWeight: T.w_bold,
                    }}>
                        VCI {vciVal >= 0 ? "+" : ""}{vciVal}
                    </span>
                    <span style={{ color: C.textSecondary, fontSize: T.cap }}>
                        {vci.label}
                    </span>
                </div>
            )}
            {typeof brain.inst_13f_bonus === "number" && brain.inst_13f_bonus > 0 && (
                <div style={{
                    background: `${C.info}10`,
                    border: `1px solid ${C.info}40`,
                    borderRadius: R.sm,
                    padding: `${S.sm}px ${S.md}px`,
                    display: "flex", alignItems: "center", gap: S.sm,
                }}>
                    <span style={{
                        ...MONO, color: C.info, fontSize: T.cap, fontWeight: T.w_bold,
                    }}>
                        13F +{brain.inst_13f_bonus}
                    </span>
                    <span style={{ color: C.textSecondary, fontSize: T.cap }}>
                        스마트머니 (기관 분기 포지션 보너스)
                    </span>
                </div>
            )}
        </div>
    )
}

function FactComponentsSection({ components }: { components: Record<string, number> }) {
    const entries = Object.entries(components)
    const [open, setOpen] = useState(false)
    return (
        <div style={{
            background: C.bgCard, border: `1px solid ${C.border}`,
            borderRadius: R.md, padding: `${S.md}px ${S.lg}px`,
            display: "flex", flexDirection: "column", gap: S.sm,
        }}>
            <button
                onClick={() => setOpen(!open)}
                style={{
                    background: "transparent", border: "none", padding: 0,
                    display: "flex", alignItems: "center", gap: S.xs,
                    cursor: "pointer", textAlign: "left", fontFamily: FONT,
                }}
            >
                <span style={subCardCap}>팩트 스코어 구성</span>
                <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_semi }}>
                    {entries.length}건 {open ? "▼" : "▶"}
                </span>
            </button>
            {open && (
                <div style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                    gap: S.sm,
                }}>
                    {entries.map(([key, val]) => {
                        const c = scoreColor(val)
                        return (
                            <div key={key} style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                                    <span style={{
                                        color: C.textSecondary, fontSize: T.cap, fontWeight: T.w_med,
                                    }}>
                                        {FACT_COMPONENT_LABELS[key] || key}
                                    </span>
                                    <span style={{ ...MONO, color: c, fontSize: T.cap, fontWeight: T.w_bold }}>
                                        {val}
                                    </span>
                                </div>
                                <div style={{
                                    height: 3, background: C.bgElevated,
                                    borderRadius: 2, overflow: "hidden",
                                }}>
                                    <div style={{
                                        height: "100%", width: `${Math.max(0, Math.min(100, val))}%`,
                                        background: c, borderRadius: 2, transition: "width 0.6s ease",
                                    }} />
                                </div>
                            </div>
                        )
                    })}
                </div>
            )}
        </div>
    )
}

function RedFlagsSection({ rf }: { rf: any }) {
    const autoAvoid = Array.isArray(rf.auto_avoid_detail) && rf.auto_avoid_detail.length > 0
        ? rf.auto_avoid_detail
        : (rf.auto_avoid || [])
    const downgrade = Array.isArray(rf.downgrade_detail) && rf.downgrade_detail.length > 0
        ? rf.downgrade_detail
        : (rf.downgrade || [])
    return (
        <div style={{
            background: C.bgCard, border: `1px solid ${C.border}`,
            borderRadius: R.md, padding: `${S.md}px ${S.lg}px`,
            display: "flex", flexDirection: "column", gap: S.sm,
        }}>
            <span style={{ ...subCardCap, color: C.danger }}>레드플래그</span>
            <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                {autoAvoid.map((f: any, i: number) => (
                    <div
                        key={`a${i}`}
                        style={{
                            background: `${C.danger}14`,
                            borderLeft: `3px solid ${C.danger}`,
                            borderRadius: R.sm,
                            padding: `${S.xs}px ${S.md}px`,
                            color: C.danger, fontSize: T.cap, fontWeight: T.w_semi,
                            lineHeight: T.lh_normal,
                        }}
                    >
                        ⛔ {formatRedFlagDetail(f)}
                    </div>
                ))}
                {downgrade.map((f: any, i: number) => (
                    <div
                        key={`d${i}`}
                        style={{
                            background: `${C.warn}10`,
                            borderLeft: `3px solid ${C.warn}`,
                            borderRadius: R.sm,
                            padding: `${S.xs}px ${S.md}px`,
                            color: C.warn, fontSize: T.cap,
                            lineHeight: T.lh_normal,
                        }}
                    >
                        {formatRedFlagDetail(f)}
                    </div>
                ))}
            </div>
        </div>
    )
}

function ScoreBreakdownSection({ sb, gc }: { sb: any; gc: string }) {
    const [open, setOpen] = useState(false)
    const cells: { label: string; value: any; color?: string; sign?: boolean }[] = [
        { label: "팩트 기여", value: sb.fact_contribution, color: C.success },
        { label: "심리 기여", value: sb.sentiment_contribution, color: C.info },
        { label: "VCI 보너스", value: sb.vci_bonus, sign: true },
        { label: "캔들 보너스", value: sb.candle_bonus, sign: true },
        { label: "그룹 보너스", value: sb.gs_bonus, sign: true },
        { label: "기관 보너스", value: sb.inst_bonus, sign: true },
    ]
    return (
        <div style={{
            background: C.bgCard, border: `1px solid ${C.border}`,
            borderRadius: R.md, padding: `${S.md}px ${S.lg}px`,
            display: "flex", flexDirection: "column", gap: S.sm,
        }}>
            <button
                onClick={() => setOpen(!open)}
                style={{
                    background: "transparent", border: "none", padding: 0,
                    display: "flex", alignItems: "center", gap: S.xs,
                    cursor: "pointer", textAlign: "left", fontFamily: FONT,
                }}
            >
                <span style={subCardCap}>점수 분해 (XAI)</span>
                <span style={{
                    ...MONO, color: gc, fontSize: T.cap, fontWeight: T.w_black,
                }}>
                    {sb.final_score}
                </span>
                <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_semi }}>
                    {open ? "▼" : "▶"}
                </span>
            </button>
            {open && (
                <>
                    <div style={{
                        display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                        gap: S.sm,
                    }}>
                        {cells.map((cell) => {
                            const v = cell.value ?? 0
                            const display = cell.sign && v > 0 ? `+${v}` : `${v}`
                            return (
                                <div key={cell.label} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                    <span style={{
                                        color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med,
                                        letterSpacing: "0.02em",
                                    }}>
                                        {cell.label}
                                    </span>
                                    <span style={{
                                        ...MONO, color: cell.color || C.textPrimary,
                                        fontSize: T.body, fontWeight: T.w_bold,
                                    }}>
                                        {display}
                                    </span>
                                </div>
                            )
                        })}
                    </div>
                    <div style={{
                        display: "flex", flexWrap: "wrap", gap: S.md,
                        color: C.textSecondary, fontSize: T.cap, marginTop: S.xs,
                    }}>
                        <span>
                            합계 (페널티 전)
                            {" "}
                            <span style={{ ...MONO, color: C.textPrimary, fontWeight: T.w_bold }}>
                                {sb.raw_before_penalty}
                            </span>
                        </span>
                        <span>
                            red_flag
                            {" "}
                            <span style={{ ...MONO, color: C.danger, fontWeight: T.w_bold }}>
                                {sb.penalties?.red_flag ?? 0}
                            </span>
                        </span>
                        {sb.penalties?.quadrant_unfavored !== 0 && (
                            <span>
                                분면불리
                                {" "}
                                <span style={{ ...MONO, color: C.danger, fontWeight: T.w_bold }}>
                                    {sb.penalties?.quadrant_unfavored}
                                </span>
                            </span>
                        )}
                    </div>
                    <div style={{
                        color: C.textSecondary, fontSize: T.cap, marginTop: 2,
                    }}>
                        raw{" "}
                        <span style={{ ...MONO, color: C.textPrimary, fontWeight: T.w_bold }}>
                            {sb.raw_brain_score}
                        </span>
                        {" "}→ 최종 (clip 0~100){" "}
                        <span style={{ ...MONO, color: gc, fontWeight: T.w_black }}>
                            {sb.final_score}
                        </span>
                    </div>
                    {Array.isArray(sb.grade_caps_applied) && sb.grade_caps_applied.length > 0 && (
                        <div style={{ color: C.caution, fontSize: T.cap, marginTop: 2 }}>
                            등급 cap: {sb.grade_caps_applied
                                .map((c: string) => OVERRIDE_LABELS[c] || c)
                                .join(" · ")}
                        </div>
                    )}
                </>
            )}
        </div>
    )
}

function AnalystReportSection({ ar }: { ar: any }) {
    const dirColor = ar.signal_direction === "bullish" ? C.success
        : ar.signal_direction === "bearish" ? C.danger : C.textTertiary
    const dirLabel = ar.signal_direction === "bullish" ? "강세 우세"
        : ar.signal_direction === "bearish" ? "약세 우세" : "혼조"
    const recent = Array.isArray(ar.recent_reports) && ar.recent_reports.length > 0
        ? ar.recent_reports[0] : null
    return (
        <div style={{
            background: C.bgCard, border: `1px solid ${C.border}`,
            borderRadius: R.md, padding: `${S.md}px ${S.lg}px`,
            display: "flex", flexDirection: "column", gap: S.sm,
        }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: S.sm, flexWrap: "wrap" }}>
                <span style={{ ...subCardCap, color: C.info }}>증권사 리포트 AI 요약</span>
                <span style={{ color: C.textTertiary, fontSize: T.cap }}>
                    최근 7일 {ar.report_count}건
                </span>
            </div>
            <div style={{
                display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
                gap: S.sm,
            }}>
                <BrainKVCell
                    label="센티먼트"
                    value={`${ar.analyst_sentiment_score}/100`}
                    color={C.textPrimary}
                />
                <BrainKVCell
                    label="평균 목표가"
                    value={ar.avg_target_price != null
                        ? `${Number(ar.avg_target_price).toLocaleString()}원`
                        : "—"}
                    color={C.textPrimary}
                />
                <BrainKVCell
                    label="의견 강도"
                    value={`${ar.consensus_strength_index ?? "—"} · ${dirLabel}`}
                    color={dirColor}
                />
                <BrainKVCell
                    label="실적 추정"
                    value={ar.revision_ratio != null
                        ? (ar.revision_ratio > 0.5 ? "상향 우세" : "하향/혼조")
                        : "—"}
                    color={C.textPrimary}
                />
            </div>
            {recent?.summary && (
                <div style={{
                    color: C.textSecondary, fontSize: T.cap, lineHeight: T.lh_normal,
                    marginTop: 2,
                }}>
                    <span style={{ color: C.info, fontWeight: T.w_bold }}>{recent.firm}</span>
                    {" — "}
                    {`"${String(recent.summary).slice(0, 100)}"`}
                </div>
            )}
        </div>
    )
}

function BusinessHealthSection({ da }: { da: any }) {
    const moats = Array.isArray(da.moat_indicators) ? da.moat_indicators.slice(0, 3) : []
    return (
        <div style={{
            background: C.bgCard, border: `1px solid ${C.border}`,
            borderRadius: R.md, padding: `${S.md}px ${S.lg}px`,
            display: "flex", flexDirection: "column", gap: S.sm,
        }}>
            <span style={{ ...subCardCap, color: C.accent }}>사업 건전성 (DART AI)</span>
            <div style={{ display: "flex", gap: S.lg, flexWrap: "wrap" }}>
                <BrainKVCell
                    label="점수"
                    value={`${da.business_health_score}/100`}
                    color={C.accent}
                />
                <BrainKVCell
                    label="설비투자"
                    value={da.capex_direction || "—"}
                    color={C.textPrimary}
                />
            </div>
            {moats.length > 0 && (
                <div style={{
                    color: C.textSecondary, fontSize: T.cap, lineHeight: T.lh_normal,
                }}>
                    해자 · {moats.join(" · ")}
                </div>
            )}
            {da.one_line_summary && (
                <div style={{
                    color: C.textSecondary, fontSize: T.cap,
                    fontStyle: "italic", lineHeight: T.lh_normal,
                }}>
                    {da.one_line_summary}
                </div>
            )}
        </div>
    )
}

function BrainKVCell({ label, value, color }: { label: string; value: string; color: string }) {
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
            <span style={{
                color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med,
                letterSpacing: "0.02em",
            }}>
                {label}
            </span>
            <span style={{ ...MONO, color, fontSize: T.body, fontWeight: T.w_bold }}>
                {value}
            </span>
        </div>
    )
}

/* ─────────── SentimentTab — 뉴스/수급/커뮤니티/내부자/기관/공매도 ─────────── */
function SentimentTab({ stock, isUS }: { stock: any; isUS: boolean }) {
    const sent = stock?.sentiment || {}
    const flow = stock?.flow || {}
    const social = stock?.social_sentiment || {}
    const hasSocial = social.score != null
    const newsS = social.news || {}
    const commS = social.community || {}
    const redditS = social.reddit || {}
    const sentScore = newsS.score ?? sent.score ?? 50

    const colorBy = (val: number, hi = 60, lo = 40) =>
        val >= hi ? C.accent : val <= lo ? C.danger : C.watch
    const trendColor = (t: string) =>
        t === "bullish" ? C.accent : t === "bearish" ? C.danger : C.textTertiary
    const flowColor = (n: number) =>
        n > 0 ? C.accent : n < 0 ? C.danger : C.textTertiary

    const topCells: { label: string; value: string; color: string }[] = hasSocial
        ? [
            { label: "종합 감성", value: `${social.score}`, color: colorBy(social.score) },
            {
                label: "추세",
                value: social.trend === "bullish" ? "강세" : social.trend === "bearish" ? "약세" : "중립",
                color: trendColor(social.trend),
            },
            { label: "뉴스", value: `${sentScore}`, color: colorBy(sentScore) },
            {
                label: "커뮤니티",
                value: commS.score != null ? `${commS.score}` : "—",
                color: commS.score != null ? colorBy(commS.score) : C.textTertiary,
            },
            {
                label: "Reddit",
                value: redditS.score != null ? `${redditS.score}` : "—",
                color: redditS.score != null ? colorBy(redditS.score) : C.textTertiary,
            },
            { label: "수급 점수", value: `${flow.flow_score ?? 50}`, color: C.textPrimary },
        ]
        : [
            { label: "뉴스 감성", value: `${sent.score ?? 50}`, color: colorBy(sent.score ?? 50) },
            { label: "긍정 키워드", value: `${sent.positive ?? 0}건`, color: C.accent },
            { label: "부정 키워드", value: `${sent.negative ?? 0}건`, color: C.danger },
            {
                label: "외국인",
                value: flow.foreign_net > 0 ? "순매수" : flow.foreign_net < 0 ? "순매도" : "중립",
                color: flowColor(flow.foreign_net ?? 0),
            },
            {
                label: "기관",
                value: flow.institution_net > 0 ? "순매수" : flow.institution_net < 0 ? "순매도" : "중립",
                color: flowColor(flow.institution_net ?? 0),
            },
            { label: "수급 점수", value: `${flow.flow_score ?? 50}`, color: C.textPrimary },
        ]

    /* 최근 뉴스 통합 (sent + company_news, 2026-05-05):
     *   1) sent.top_headline_links 또는 detail.url (label 있는 분석 뉴스 우선)
     *   2) 없으면 sent.top_headlines (plain)
     *   3) US 한정 stock.company_news 가 비중복으로 추가 */
    const newsLinks: any[] = sent.top_headline_links || []
    const newsDetails: any[] = sent.detail || []
    const newsPlain: string[] = sent.top_headlines || []
    const sentNewsRaw = newsLinks.length > 0
        ? newsLinks
        : newsDetails.filter((d: any) => d.url)
    type NewsItem = { title: string; url?: string; label?: string; source?: string }
    const allNewsItems: NewsItem[] = []
    if (sentNewsRaw.length > 0) {
        for (const n of sentNewsRaw.slice(0, 8)) {
            allNewsItems.push({ title: n.title, url: n.url, label: n.label })
        }
    } else if (newsPlain.length > 0) {
        for (const h of newsPlain.slice(0, 8)) {
            allNewsItems.push({ title: h })
        }
    }
    if (isUS && Array.isArray(stock?.company_news)) {
        const seen = new Set(allNewsItems.map((n) => n.title))
        for (const n of stock.company_news.slice(0, 5)) {
            if (n?.title && !seen.has(n.title)) {
                allNewsItems.push({ title: n.title, url: n.url, source: n.source })
                seen.add(n.title)
            }
        }
    }
    const showNews = allNewsItems.length > 0

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.md }}>
            {/* 1. 감성/수급 metrics */}
            <div style={{
                background: C.bgCard, border: `1px solid ${C.border}`,
                borderRadius: R.md, padding: `${S.md}px ${S.lg}px`,
                display: "flex", flexDirection: "column", gap: S.sm,
            }}>
                <span style={subCardCap}>{hasSocial ? "감성·수급 종합" : "뉴스·수급"}</span>
                <div style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))",
                    gap: S.sm,
                }}>
                    {topCells.map((cell) => (
                        <div key={cell.label} style={{
                            display: "flex", flexDirection: "column", gap: 2, minWidth: 0,
                        }}>
                            <span style={{
                                color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med,
                                letterSpacing: "0.02em",
                            }}>
                                {cell.label}
                            </span>
                            <span style={{
                                ...MONO, color: cell.color, fontSize: T.sub, fontWeight: T.w_black,
                                lineHeight: 1.1,
                            }}>
                                {cell.value}
                            </span>
                        </div>
                    ))}
                </div>
                {hasSocial && (commS.volume > 0 || redditS.volume > 0) && (
                    <div style={{
                        display: "flex", flexWrap: "wrap", gap: S.lg,
                        color: C.textTertiary, fontSize: T.cap, marginTop: 2,
                    }}>
                        {commS.volume > 0 && (
                            <span>
                                커뮤니티{" "}
                                <span style={{ ...MONO, color: C.textPrimary, fontWeight: T.w_bold }}>
                                    {commS.volume}건
                                </span>
                                {" · 긍정 "}
                                <span style={{ ...MONO, color: C.success }}>{commS.positive}</span>
                                {" / 부정 "}
                                <span style={{ ...MONO, color: C.danger }}>{commS.negative}</span>
                            </span>
                        )}
                        {redditS.volume > 0 && (
                            <span>
                                Reddit{" "}
                                <span style={{ ...MONO, color: C.textPrimary, fontWeight: T.w_bold }}>
                                    {redditS.volume}건
                                </span>
                                {" · 긍정 "}
                                <span style={{ ...MONO, color: C.success }}>{redditS.positive}</span>
                                {" / 부정 "}
                                <span style={{ ...MONO, color: C.danger }}>{redditS.negative}</span>
                            </span>
                        )}
                    </div>
                )}
            </div>

            {/* 2. Reddit 인기글 */}
            {Array.isArray(redditS.top_posts) && redditS.top_posts.length > 0 && (
                <div style={{
                    background: C.bgCard, border: `1px solid ${C.border}`,
                    borderRadius: R.md, padding: `${S.md}px ${S.lg}px`,
                    display: "flex", flexDirection: "column", gap: S.xs,
                }}>
                    <span style={subCardCap}>Reddit 인기글</span>
                    {redditS.top_posts.map((p: any, i: number) => (
                        <span key={i} style={{
                            color: C.textSecondary, fontSize: T.cap, lineHeight: T.lh_normal,
                        }}>
                            <span style={{ color: C.info, fontWeight: T.w_semi }}>r/{p.sub}</span>
                            {" · "}
                            {p.title}
                        </span>
                    ))}
                </div>
            )}

            {/* 3. 최근 뉴스 (sent + Finnhub 통합 2026-05-05) */}
            {showNews && (
                <div style={{
                    background: C.bgCard, border: `1px solid ${C.border}`,
                    borderRadius: R.md, padding: `${S.md}px ${S.lg}px`,
                    display: "flex", flexDirection: "column", gap: S.xs,
                }}>
                    <span style={subCardCap}>최근 뉴스</span>
                    {allNewsItems.map((item, i) => {
                        const sc = item.label === "positive" ? C.success
                            : item.label === "negative" ? C.danger : C.textTertiary
                        const Tag = item.url ? "a" : "div"
                        const aProps = item.url ? {
                            href: item.url, target: "_blank", rel: "noopener noreferrer",
                        } : {}
                        return (
                            <Tag
                                key={i}
                                {...aProps}
                                style={{
                                    display: "flex", alignItems: "center", gap: S.sm,
                                    padding: `${S.xs}px ${S.sm}px`,
                                    borderRadius: R.sm,
                                    textDecoration: "none",
                                    transition: X.fast,
                                }}
                                onMouseEnter={(e: any) => {
                                    if (item.url) (e.currentTarget as HTMLElement).style.background = C.bgPage
                                }}
                                onMouseLeave={(e: any) => {
                                    (e.currentTarget as HTMLElement).style.background = "transparent"
                                }}
                            >
                                {item.label && (
                                    <span style={{
                                        width: 5, height: 5, borderRadius: 3,
                                        background: sc, flexShrink: 0,
                                    }} />
                                )}
                                <span style={{
                                    color: C.textSecondary, fontSize: T.cap,
                                    lineHeight: T.lh_normal, flex: 1,
                                }}>
                                    {item.title}
                                </span>
                                {item.source && (
                                    <span style={{
                                        color: C.textTertiary, fontSize: T.cap,
                                        flexShrink: 0, letterSpacing: "0.02em",
                                    }}>
                                        {item.source}
                                    </span>
                                )}
                                {item.url && (
                                    <span style={{
                                        color: C.textTertiary, fontSize: T.cap, flexShrink: 0,
                                    }}>
                                        ↗
                                    </span>
                                )}
                            </Tag>
                        )
                    })}
                </div>
            )}

            {/* US 전용 섹션들 (Insider MSPR / Finnhub 별도 박스 retract 2026-05-05) */}
            {isUS && stock?.institutional_ownership && stock.institutional_ownership.total_holders > 0 && (
                <InstitutionalSection inst={stock.institutional_ownership} />
            )}

            {isUS && stock?.short_interest &&
                (stock.short_interest.short_pct != null || stock.short_interest.days_to_cover != null) && (
                <ShortInterestSection si={stock.short_interest} />
            )}
        </div>
    )
}

function InstitutionalSection({ inst }: { inst: any }) {
    const cp = inst.change_pct ?? 0
    const cpColor = cp > 0 ? C.success : cp < 0 ? C.danger : C.textTertiary
    const cpDisplay = inst.change_pct != null
        ? `${cp > 0 ? "+" : ""}${cp}%`
        : "—"
    return (
        <div style={{
            background: C.bgCard, border: `1px solid ${C.border}`,
            borderRadius: R.md, padding: `${S.md}px ${S.lg}px`,
            display: "flex", flexDirection: "column", gap: S.sm,
        }}>
            <span style={subCardCap}>기관 보유 현황</span>
            <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))",
                gap: S.sm,
            }}>
                <BrainKVCell label="기관수" value={String(inst.total_holders)} color={C.textPrimary} />
                <BrainKVCell label="변동률" value={cpDisplay} color={cpColor} />
            </div>
        </div>
    )
}

function ShortInterestSection({ si }: { si: any }) {
    const sp = Number(si.short_pct)
    const shortColor = sp >= 20 ? C.danger : sp >= 10 ? C.watch : C.accent
    const trendMap: Record<string, { label: string; color: string }> = {
        surge: { label: "급증", color: C.danger },
        up: { label: "증가", color: C.watch },
        flat: { label: "유지", color: C.textSecondary },
        down: { label: "감소", color: C.info },
        drop: { label: "급감", color: C.success },
    }
    const tr = si.trend ? trendMap[si.trend] : null

    return (
        <div style={{
            background: C.bgCard, border: `1px solid ${C.border}`,
            borderRadius: R.md, padding: `${S.md}px ${S.lg}px`,
            display: "flex", flexDirection: "column", gap: S.sm,
        }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: S.sm }}>
                <span style={subCardCap}>공매도 현황</span>
                {si.report_date && (
                    <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap }}>
                        기준 {si.report_date}
                    </span>
                )}
            </div>
            <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))",
                gap: S.sm,
            }}>
                {si.short_pct != null && (
                    <BrainKVCell label="Short % Float" value={`${si.short_pct}%`} color={shortColor} />
                )}
                {si.days_to_cover != null && (
                    <BrainKVCell
                        label="Days to Cover"
                        value={String(si.days_to_cover)}
                        color={si.days_to_cover >= 5 ? C.danger : si.days_to_cover >= 2 ? C.watch : C.textTertiary}
                    />
                )}
                {tr && (
                    <BrainKVCell label="전월 대비" value={tr.label} color={tr.color} />
                )}
            </div>
            {sp >= 20 && (
                <div style={{
                    background: `${C.danger}14`,
                    border: `1px solid ${C.danger}40`,
                    borderRadius: R.sm,
                    padding: `${S.xs}px ${S.md}px`,
                    color: C.danger, fontSize: T.cap, fontWeight: T.w_semi,
                    lineHeight: T.lh_normal,
                }}>
                    Short % 20% 초과 — 스퀴즈·하락 리스크 모두 주의
                </div>
            )}
            {si.trend === "surge" && (
                <div style={{
                    background: `${C.warn}10`,
                    border: `1px solid ${C.warn}40`,
                    borderRadius: R.sm,
                    padding: `${S.xs}px ${S.md}px`,
                    color: C.warn, fontSize: T.cap, lineHeight: T.lh_normal,
                }}>
                    공매도 전월比 +15% 이상 급증 — 기관 하락 베팅 확대
                </div>
            )}
        </div>
    )
}

/* ─────────── DetailTabBar — 10 tab 토글 ─────────── */
function DetailTabBar({
    current, onChange,
}: { current: DetailTab; onChange: (t: DetailTab) => void }) {
    return (
        <div style={{
            display: "flex", gap: S.xs, flexWrap: "wrap",
            borderBottom: `1px solid ${C.border}`,
            paddingBottom: 0,
        }}>
            {DETAIL_TABS.map((t) => {
                const active = current === t.key
                return (
                    <button
                        key={t.key}
                        onClick={() => onChange(t.key)}
                        style={{
                            background: "transparent",
                            border: "none",
                            borderBottom: `2px solid ${active ? C.accent : "transparent"}`,
                            color: active ? C.accent : C.textTertiary,
                            padding: `${S.sm}px ${S.md}px`,
                            fontSize: T.cap, fontWeight: active ? T.w_bold : T.w_semi,
                            fontFamily: FONT,
                            cursor: "pointer",
                            transition: X.fast,
                            letterSpacing: "0.03em",
                        }}
                    >
                        {t.label}
                    </button>
                )
            })}
        </div>
    )
}


/* ─────────── 좌측 list 카드 ─────────── */
function StockListItem({
    stock: s, isActive, isUS, onClick,
}: {
    stock: any; isActive: boolean; isUS: boolean; onClick: () => void
}) {
    const ms = s.multi_factor?.multi_score ?? s.safety_score ?? 0
    const msC = scoreColor(ms)
    const recC = recColor(s.recommendation || "WATCH")
    const whyGold = !!s.gold_insight
    const whyText = s.gold_insight || s.silver_insight || ""
    const hasClaude = !!s.claude_analysis
    const sparkColor = (s.sparkline || []).length > 1
        && s.sparkline[s.sparkline.length - 1] >= s.sparkline[0]
        ? C.up : C.down

    return (
        <div
            onClick={onClick}
            style={{
                ...listItem,
                background: isActive ? C.bgElevated : "transparent",
                borderLeft: `3px solid ${isActive ? C.accent : "transparent"}`,
                boxShadow: isActive ? G.accentSoft : "none",
            }}
            onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = `${C.bgElevated}80` }}
            onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.background = "transparent" }}
        >
            {/* 좌: rec dot + 본문 */}
            <div style={{ display: "flex", alignItems: "flex-start", gap: S.sm, flex: 1, minWidth: 0 }}>
                <span
                    style={{
                        width: 8, height: 8, borderRadius: "50%",
                        background: recC, flexShrink: 0, marginTop: 6,
                    }}
                />
                <div style={{ display: "flex", flexDirection: "column", gap: 2, flex: 1, minWidth: 0 }}>
                    {/* 종목명 + company_type */}
                    <div style={{ display: "flex", alignItems: "center", gap: S.xs, minWidth: 0 }}>
                        <span style={{
                            color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi,
                            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                        }}>
                            {s.name}
                        </span>
                        {s.company_type && (
                            <span style={{
                                fontSize: T.cap, fontWeight: T.w_bold,
                                color: C.accent, background: C.accentSoft,
                                border: `1px solid ${C.accent}33`,
                                borderRadius: R.sm,
                                padding: `1px ${S.xs}px`,
                                whiteSpace: "nowrap",
                                flexShrink: 0,
                                letterSpacing: "0.03em",
                            }}>
                                {s.company_type}
                            </span>
                        )}
                    </div>

                    {/* ticker · market · tagline */}
                    <span style={{
                        ...MONO,
                        color: C.textTertiary, fontSize: T.cap,
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                    }}>
                        {s.ticker} · {s.market} · {getBusinessTagline(s)}
                        {hasClaude && <span style={{ color: C.info, marginLeft: S.xs }}>· AI</span>}
                    </span>

                    {/* gold/silver insight */}
                    {whyText && (
                        <div style={{ display: "flex", alignItems: "center", gap: S.xs, marginTop: 2 }}>
                            <span style={{
                                fontSize: 9, fontWeight: T.w_black,
                                padding: `1px ${S.xs}px`, borderRadius: R.sm,
                                background: whyGold ? C.watch : C.textTertiary,
                                color: C.bgPage,
                                lineHeight: 1.2, flexShrink: 0,
                                letterSpacing: "0.03em",
                            }}>
                                {whyGold ? "G" : "S"}
                            </span>
                            <span style={{
                                fontSize: T.cap, color: C.textSecondary, lineHeight: 1.3,
                                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                                flex: 1, minWidth: 0,
                            }}>
                                {whyText}
                            </span>
                        </div>
                    )}
                </div>

                {/* 우: sparkline + price + score */}
                <div style={{
                    display: "flex", flexDirection: "column", alignItems: "flex-end",
                    gap: 2, flexShrink: 0,
                }}>
                    {(s.sparkline || []).length > 1 && (
                        <Sparkline data={s.sparkline} width={40} height={16} color={sparkColor} />
                    )}
                    <span style={{ ...MONO, color: C.textPrimary, fontSize: T.cap, fontWeight: T.w_semi }}>
                        {formatPrice(s.price, isUS)}
                    </span>
                    <span style={{ ...MONO, color: msC, fontSize: T.cap, fontWeight: T.w_bold }}>
                        {ms}점
                    </span>
                </div>
            </div>
        </div>
    )
}


/* ─────────── Filter chip ─────────── */
function FilterChip({
    label, active, onClick, color,
}: {
    label: string; active: boolean; onClick: () => void; color?: string
}) {
    const c = color || C.accent
    return (
        <button
            onClick={onClick}
            style={{
                background: active ? `${c}1A` : "transparent",
                border: `1px solid ${active ? c : C.border}`,
                color: active ? c : C.textSecondary,
                padding: `${S.xs}px ${S.md}px`,
                borderRadius: R.pill,
                fontSize: T.cap,
                fontWeight: T.w_semi,
                fontFamily: FONT,
                letterSpacing: "0.05em",
                cursor: "pointer",
                transition: X.base,
            }}
        >
            {label}
        </button>
    )
}


/* ──────────────────────────────────────────────────────────────
 * ◆ STYLES START ◆
 * ────────────────────────────────────────────────────────────── */

const shell: CSSProperties = {
    width: "100%", boxSizing: "border-box",
    fontFamily: FONT, color: C.textPrimary,
    background: C.bgPage,
    border: `1px solid ${C.border}`,
    borderRadius: R.lg,
    padding: S.xxl,
    display: "flex", flexDirection: "column",
    gap: S.lg,
}

const headerRow: CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    gap: S.md, flexWrap: "wrap",
}

const headerLeft: CSSProperties = {
    display: "flex", flexDirection: "column", gap: 2,
}

const titleStyle: CSSProperties = {
    fontSize: T.h1, fontWeight: T.w_bold, color: C.textPrimary,
    letterSpacing: "-0.5px",
}

const metaStyle: CSSProperties = {
    fontSize: T.cap, color: C.textTertiary, fontWeight: T.w_med,
}

const hr: CSSProperties = {
    height: 1, background: C.border, margin: 0,
}

const loadingBox: CSSProperties = {
    minHeight: 240,
    display: "flex", alignItems: "center", justifyContent: "center",
}

const filterTabRow: CSSProperties = {
    display: "flex", gap: S.sm, flexWrap: "wrap",
}

const bodyRow: CSSProperties = {
    display: "grid",
    gridTemplateColumns: "minmax(280px, 360px) 1fr",
    gap: S.lg,
    minHeight: 480,
}

const listPanel: CSSProperties = {
    display: "flex", flexDirection: "column",
    background: C.bgCard,
    border: `1px solid ${C.border}`,
    borderRadius: R.md,
    overflowY: "auto",
    maxHeight: 720,
}

const listItem: CSSProperties = {
    padding: `${S.md}px ${S.md}px`,
    borderBottom: `1px solid ${C.border}`,
    cursor: "pointer",
    transition: X.fast,
    display: "flex",
    minWidth: 0,
}

const detailPanelPlaceholder: CSSProperties = {
    background: C.bgCard,
    border: `1px solid ${C.border}`,
    borderRadius: R.md,
    padding: `${S.lg}px ${S.xl}px`,
    display: "flex", alignItems: "center", justifyContent: "center",
    minHeight: 480,
}

const detailPanel: CSSProperties = {
    display: "flex", flexDirection: "column",
    gap: S.lg,
    background: C.bgPage,
    minHeight: 480,
}

const detailHeader: CSSProperties = {
    display: "flex", gap: S.lg,
    background: C.bgCard,
    border: `1px solid ${C.border}`,
    borderRadius: R.md,
    padding: S.xl,
    flexWrap: "wrap",
}

const detailInfoBlock: CSSProperties = {
    flex: 1, minWidth: 240,
    display: "flex", flexDirection: "column",
    gap: S.sm,
}

const emptyBox: CSSProperties = {
    padding: `${S.xxl}px 0`, textAlign: "center",
}

const newsLink: CSSProperties = {
    display: "flex", alignItems: "center", gap: S.xs,
    padding: `${S.xs}px ${S.md}px`,
    background: C.bgElevated,
    borderRadius: R.sm,
    textDecoration: "none",
    transition: X.fast,
    cursor: "pointer",
}

const newsTitle: CSSProperties = {
    color: C.textSecondary,
    fontSize: T.cap,
    lineHeight: T.lh_normal,
    flex: 1, minWidth: 0,
    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
}

/* sub-component 공용 */
const subCard: CSSProperties = {
    background: C.bgCard,
    border: `1px solid ${C.border}`,
    borderRadius: R.md,
    padding: `${S.md}px ${S.lg}px`,
    display: "flex", flexDirection: "column",
}

const subCardCap: CSSProperties = {
    color: C.textSecondary,
    fontSize: T.cap,
    fontWeight: T.w_bold,
    letterSpacing: "0.08em",
    textTransform: "uppercase",
}

const trendBlock: CSSProperties = {
    background: C.bgPage,
    border: `1px solid ${C.border}`,
    borderRadius: R.sm,
    padding: `${S.sm}px ${S.md}px`,
    marginTop: S.xs,
}

const miniMetric: CSSProperties = {
    background: C.bgPage,
    border: `1px solid ${C.border}`,
    borderRadius: R.sm,
    padding: `${S.xs}px ${S.md}px`,
    display: "flex", flexDirection: "column", gap: 2,
    minWidth: 0,
}

const miniLabel: CSSProperties = {
    color: C.textTertiary,
    fontSize: T.cap,
    fontWeight: T.w_med,
    letterSpacing: "0.03em",
}

const miniValue: CSSProperties = {
    ...MONO,
    color: C.textPrimary,
    fontSize: T.body,
    fontWeight: T.w_bold,
}

const planCell: CSSProperties = {
    background: C.bgCard,
    border: `1px solid ${C.border}`,
    borderRadius: R.sm,
    padding: `${S.sm}px ${S.md}px`,
    display: "flex", flexDirection: "column", gap: 2,
    minWidth: 0,
}

const planLabel: CSSProperties = {
    color: C.textTertiary,
    fontSize: T.cap,
    fontWeight: T.w_semi,
    letterSpacing: "0.03em",
}

const planValue: CSSProperties = {
    ...MONO,
    color: C.textPrimary,
    fontSize: T.sub,
    fontWeight: T.w_bold,
}

const planHint: CSSProperties = {
    color: C.textSecondary,
    fontSize: T.cap,
    lineHeight: T.lh_normal,
}

/* ◆ STYLES END ◆ */


/* ──────────────────────────────────────────────────────────────
 * ◆ FRAMER PROPERTY CONTROLS
 * ────────────────────────────────────────────────────────────── */

StockDashboardV2.defaultProps = {
    dataUrl: DATA_URL,
    recUrl: REC_URL,
    apiBase: API_BASE,
    market: "kr",
    supabaseUrl: "",
    supabaseAnonKey: "",
}

addPropertyControls(StockDashboardV2, {
    dataUrl: {
        type: ControlType.String,
        title: "Portfolio URL",
        defaultValue: DATA_URL,
    },
    recUrl: {
        type: ControlType.String,
        title: "Recommendations URL",
        defaultValue: REC_URL,
    },
    apiBase: {
        type: ControlType.String,
        title: "API Base",
        defaultValue: API_BASE,
    },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["KR 국장", "US 미장"],
        defaultValue: "kr",
    },
    supabaseUrl: {
        type: ControlType.String,
        title: "Supabase URL (선택)",
        defaultValue: "",
        description: "watchGroups API 용",
    },
    supabaseAnonKey: {
        type: ControlType.String,
        title: "Supabase Anon Key (선택)",
        defaultValue: "",
    },
})
