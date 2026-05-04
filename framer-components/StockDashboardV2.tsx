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

export default function StockDashboardV2(props: Props) {
    const { dataUrl, recUrl, market = "kr" } = props
    const isUS = market === "us"

    const [data, setData] = useState<any>(null)
    const [loadState, setLoadState] = useState<"loading" | "ok" | "error">("loading")

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        setLoadState("loading")
        fetchJson(dataUrl, ac.signal)
            .then((d) => { if (!ac.signal.aborted) { setData(d); setLoadState("ok") } })
            .catch(() => { if (!ac.signal.aborted) setLoadState("error") })
        return () => ac.abort()
    }, [dataUrl])

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

    const recs: any[] = data?.recommendations || []
    const stale = stalenessInfo(data?.updated_at)

    return (
        <div style={shell}>
            {/* 헤더 + stale 배지 */}
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

            <div style={hr} />

            {/* Placeholder: A.3~A.15 turn 들에서 listPanel + detailPanel + 11 detail tab 박음 */}
            <div style={{
                background: C.bgCard, border: `1px solid ${C.border}`,
                borderRadius: R.md, padding: `${S.lg}px ${S.xl}px`,
                display: "flex", flexDirection: "column", gap: S.sm,
            }}>
                <span style={{ color: C.accent, fontSize: T.cap, fontWeight: T.w_bold, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                    풀 재작성 진행 중
                </span>
                <span style={{ color: C.textPrimary, fontSize: T.body, lineHeight: T.lh_normal }}>
                    StockDashboardV2 — A.2 골격 박힘 (토큰 + TermTooltip + 7 sub-component + 메인 shell).
                </span>
                <span style={{ color: C.textTertiary, fontSize: T.cap, lineHeight: T.lh_normal }}>
                    다음 단계: A.3 listPanel · A.4 detailPanel header · A.5~ 11 detail tab 점진 박음.
                </span>
                <span style={{ color: C.textTertiary, fontSize: T.cap, lineHeight: T.lh_normal }}>
                    현재는 기존 StockDashboard 사용 권장. V2 swap 은 A.16 검증 완료 후.
                </span>
            </div>
        </div>
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
