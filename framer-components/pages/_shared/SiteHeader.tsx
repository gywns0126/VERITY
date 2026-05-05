import { addPropertyControls, ControlType } from "framer"
import { useEffect, useRef, useState } from "react"

/**
 * SiteHeader — VERITY 통합 상단 헤더 (1줄 default + [더보기] expand)
 *
 * 통합 출처:
 *   - MarketBar.tsx (지수·O₂·원자재·freshness)
 *   - WorldClockRow.tsx (시계)
 *
 * 폐기:
 *   - ScrollingTicker.tsx (마퀴 스크롤 띠 — 초보 인지부하 + CNBC 톤)
 *
 * 디자인 원칙 (모던 심플 6원칙):
 *   1. No card-in-card — 외곽 1개, 내부 spacing 으로 섹션 분리
 *   2. Flat hierarchy — H1 1개 + cap(12) uppercase 라벨
 *   3. Mono numerics — 숫자/티커/시각 SF Mono + tabular-nums
 *   4. Expand on tap — 평소 1줄, 깊이는 [더보기]
 *   5. Color discipline — accent glow active/CTA only, 토큰만
 *   6. Hover tooltip — 전문 용어 dotted underline + TermTooltip
 *
 * 데이터: portfolio.json 의 market_summary + macro
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
    danger: "0 0 6px rgba(239,68,68,0.30)",
    success: "0 0 6px rgba(34,197,94,0.30)",
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


/* ──────────────────────────────────────────────────────────────
 * ◆ TERMS START ◆ (data/verity_terms.json 발췌 — 본 컴포넌트 사용 항목만)
 * ────────────────────────────────────────────────────────────── */
interface Term {
    label: string
    category?: "metric" | "grade" | "signal" | "concept" | "data_source" | "internal" | "time"
    definition: string
    stages?: Record<string, string>
    values?: Record<string, string>
    l3?: boolean
}
const TERMS: Record<string, Term> = {
    MARKET_MOOD: {
        label: "Market Mood (O₂ score)",
        category: "metric",
        definition:
            "VERITY 자체 산출 시장 분위기 점수 (0~100). macro 지표 종합. 진입 권고 강도 조정.",
        stages: {
            "HIGH (70+)": "산소 충분 — 적극 진입 가능",
            "NORMAL (55+)": "안정권 — 기존 전략 유지",
            "LOW (40+)": "산소 부족 — 보수적 진입",
            "HYPOXIA (25+)": "경고 — 현금 비중 확대",
            "CRITICAL (<25)": "고갈 — 신규 매수 금지",
        },
        l3: true,
    },
    VIX: {
        label: "VIX (변동성 지수)",
        category: "concept",
        definition:
            "S&P 500 옵션 implied volatility 지수. > 25 위험, < 18 안정. 미국 시장 공포 지수.",
    },
    REGIME: {
        label: "Regime (장세)",
        category: "metric",
        definition:
            "시장 국면 분류. bull/bear/range. regime별 fact_score 가중치 dynamic 조정.",
    },
}
/* ◆ TERMS END ◆ */


/* ──────────────────────────────────────────────────────────────
 * ◆ TERMTOOLTIP START ◆ (estate/components/pages/home/LandexPulse.tsx 검증된 패턴)
 * ────────────────────────────────────────────────────────────── */
function TermTooltip({ termKey, children }: { termKey: string; children: React.ReactNode }) {
    const [show, setShow] = useState(false)
    const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
    const anchorRef = useRef<HTMLSpanElement>(null)
    const term = TERMS[termKey]
    if (!term) return <>{children}</>

    const TIP_W = 320
    const TIP_H = 200

    const handleEnter = () => {
        const el = anchorRef.current
        if (!el || typeof window === "undefined") { setShow(true); return }
        const rect = el.getBoundingClientRect()
        const vw = window.innerWidth
        const vh = window.innerHeight
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
            onMouseEnter={handleEnter}
            onMouseLeave={handleLeave}
            onFocus={handleEnter}
            onBlur={handleLeave}
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
                    fontFamily: FONT, fontSize: 12, lineHeight: 1.5,
                    whiteSpace: "normal", pointerEvents: "none",
                }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                        <span style={{ color: C.textPrimary, fontWeight: T.w_bold, fontSize: 13 }}>{term.label}</span>
                        {term.l3 && (
                            <span style={{
                                color: C.accent, fontSize: 9,
                                letterSpacing: "1.5px", fontWeight: T.w_black, textTransform: "uppercase",
                                padding: "1px 6px", borderRadius: R.pill,
                                border: `1px solid ${C.accent}60`,
                            }}>L3</span>
                        )}
                    </div>
                    <div style={{ color: C.textSecondary }}>{term.definition}</div>
                    {term.stages && (
                        <div style={{ marginTop: 6, paddingTop: 6, borderTop: `1px solid ${C.border}` }}>
                            {Object.entries(term.stages).map(([k, v]) => (
                                <div key={k} style={{ fontSize: 11, color: C.textTertiary }}>
                                    <span style={{ fontWeight: T.w_semi, color: C.textSecondary }}>{k}</span> {v}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </span>
    )
}
/* ◆ TERMTOOLTIP END ◆ */


/* ─────────── Portfolio fetch (인라인) ─────────── */
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


/* ─────────── 시장 open/close 판정 (TZ 기반) ─────────── */
function isMarketOpen(tz: string, oH: number, oM: number, cH: number, cM: number): boolean {
    if (typeof window === "undefined") return false
    try {
        const parts = new Intl.DateTimeFormat("en-US", {
            timeZone: tz, weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false,
        }).formatToParts(new Date())
        const wd = parts.find((p) => p.type === "weekday")?.value
        if (wd === "Sat" || wd === "Sun") return false
        const h = parseInt(parts.find((p) => p.type === "hour")?.value ?? "0", 10)
        const m = parseInt(parts.find((p) => p.type === "minute")?.value ?? "0", 10)
        const cur = h * 60 + m
        return cur >= oH * 60 + oM && cur < cH * 60 + cM
    } catch {
        return false
    }
}

function formatClock(tz: string): string {
    if (typeof window === "undefined") return "--:--"
    try {
        return new Intl.DateTimeFormat("ko-KR", {
            timeZone: tz, hour: "2-digit", minute: "2-digit", hour12: false,
        }).format(new Date())
    } catch {
        return "--:--"
    }
}


/* ─────────── 포맷 유틸 ─────────── */
function fmtPct(n: number | null | undefined, digits = 2): string {
    if (n == null || !Number.isFinite(n)) return "—"
    const sign = n > 0 ? "+" : ""
    return `${sign}${n.toFixed(digits)}%`
}
function fmtIndex(v: number | null | undefined): string {
    if (v == null || !Number.isFinite(v)) return "—"
    return v >= 100 ? v.toLocaleString(undefined, { maximumFractionDigits: 0 }) : v.toFixed(1)
}
function signedColor(n: number | null | undefined): string {
    if (n == null || !Number.isFinite(n)) return C.textTertiary
    if (n > 0) return C.success
    if (n < 0) return C.danger
    return C.textTertiary
}


/* ─────────── O₂ score 단계 ─────────── */
const O2_LEVELS = [
    { min: 70, label: "HIGH", color: C.success },
    { min: 55, label: "NORMAL", color: C.success },
    { min: 40, label: "LOW", color: C.warn },
    { min: 25, label: "HYPOXIA", color: C.warn },
    { min: 0, label: "CRITICAL", color: C.danger },
] as const
function getO2(score: number) { return O2_LEVELS.find((l) => score >= l.min) ?? O2_LEVELS[O2_LEVELS.length - 1] }


/* ═══════════════════════════ 메인 ═══════════════════════════ */

interface Props {
    dataUrl: string
    refreshIntervalSec: number
}

export default function SiteHeader(props: Props) {
    const { dataUrl, refreshIntervalSec } = props
    const [data, setData] = useState<any>(null)
    const [expanded, setExpanded] = useState(false)
    const [, setTick] = useState(0)

    /* portfolio.json fetch */
    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        const load = () => fetchJson(dataUrl, ac.signal).then((d) => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        load()
        const sec = Math.max(30, Number(refreshIntervalSec) || 180)
        const id = window.setInterval(load, sec * 1000)
        return () => { ac.abort(); window.clearInterval(id) }
    }, [dataUrl, refreshIntervalSec])

    /* 시계 1초 tick */
    useEffect(() => {
        const id = window.setInterval(() => setTick((n) => n + 1), 1000)
        return () => window.clearInterval(id)
    }, [])

    const ms = data?.market_summary || {}
    const macro = data?.macro || {}
    const mood = macro.market_mood || {}
    const kospi = ms.kospi || {}
    const kosdaq = ms.kosdaq || {}
    const ndx = ms.ndx || {}
    const sp500 = ms.sp500 || {}
    const usd = macro.usd_krw || {}
    const vix = macro.vix || {}
    const gold = macro.gold || {}
    const silver = macro.silver || {}
    const score = mood.score ?? 50
    const o2 = getO2(score)

    const krxOpen = isMarketOpen("Asia/Seoul", 9, 0, 15, 30)
    const nyseOpen = isMarketOpen("America/New_York", 9, 30, 16, 0)
    const seoulNow = formatClock("Asia/Seoul")
    const nyNow = formatClock("America/New_York")

    const updatedAt = data?.updated_at ? new Date(data.updated_at) : null
    const ageH = updatedAt ? (Date.now() - updatedAt.getTime()) / 3_600_000 : null
    const isStale = ageH != null && ageH > 24
    const updatedLabel = updatedAt
        ? updatedAt.toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
        : "데이터 대기 중"

    return (
        <div style={shell}>
            {/* ── Default 1줄 ── */}
            <div style={defaultRow}>
                <div style={statusBlock}>
                    <StatusDot on={krxOpen} label="KRX" />
                    <StatusDot on={nyseOpen} label="NYSE" />
                </div>

                <div style={midBlock}>
                    <IndexChip label="KOSPI" value={kospi.value} pct={kospi.change_pct} />
                    <Sep />
                    <IndexChip label="S&P" value={sp500.value} pct={sp500.change_pct} />
                </div>

                <div style={rightBlock}>
                    <span style={{ ...timeStyle, color: C.textSecondary }}>서울 {seoulNow}</span>
                    <button
                        onClick={() => setExpanded((v) => !v)}
                        style={{
                            ...moreBtn,
                            color: expanded ? C.accent : C.textSecondary,
                            borderColor: expanded ? C.accent : C.border,
                        }}
                    >
                        {expanded ? "▾ 접기" : "▸ 더보기"}
                    </button>
                </div>
            </div>

            {/* ── Expand panel ── */}
            {expanded && (
                <div style={expandPanel}>
                    {/* Section: O₂ + freshness */}
                    <div style={sectionRow}>
                        <span style={sectionLabel}>
                            <TermTooltip termKey="MARKET_MOOD">시장 분위기</TermTooltip>
                        </span>
                        <div style={o2Row}>
                            <div style={{ ...o2Bar, background: C.bgElevated }}>
                                <div style={{
                                    width: `${score}%`, height: "100%",
                                    background: o2.color, transition: "width 0.6s ease",
                                }} />
                            </div>
                            <span style={{ ...MONO, color: o2.color, fontWeight: T.w_bold, fontSize: T.body }}>{score}</span>
                            <span style={{ color: o2.color, fontSize: T.cap, fontWeight: T.w_semi, letterSpacing: 0.5 }}>{o2.label}</span>
                        </div>
                        <span style={{
                            ...MONO,
                            color: isStale ? C.danger : C.textTertiary,
                            fontSize: T.cap,
                        }}>
                            {updatedLabel}
                            {isStale && ageH != null && ` (${Math.floor(ageH)}h)`}
                        </span>
                    </div>

                    <div style={hr} />

                    {/* Section: 6 indices */}
                    <div style={sectionRow}>
                        <span style={sectionLabel}>지수</span>
                        <div style={chipsRow}>
                            <IndexChip label="KOSPI" value={kospi.value} pct={kospi.change_pct} />
                            <IndexChip label="KOSDAQ" value={kosdaq.value} pct={kosdaq.change_pct} />
                            <IndexChip label="NDX" value={ndx.value} pct={ndx.change_pct} />
                            <IndexChip label="S&P" value={sp500.value} pct={sp500.change_pct} />
                            <IndexChip label="USD/KRW" value={usd.value} pct={null} />
                            <span>
                                <TermTooltip termKey="VIX">
                                    <IndexChipInline label="VIX" value={vix.value} pct={null} color={vixColor(vix.value)} />
                                </TermTooltip>
                            </span>
                        </div>
                    </div>

                    <div style={hr} />

                    {/* Section: 원자재 */}
                    <div style={sectionRow}>
                        <span style={sectionLabel}>원자재</span>
                        <div style={chipsRow}>
                            <CommodityChip label="GOLD" value={gold.value} pct={gold.change_pct} />
                            <CommodityChip label="SILVER" value={silver.value} pct={silver.change_pct} />
                        </div>
                    </div>

                    <div style={hr} />

                    {/* Section: 시계 */}
                    <div style={sectionRow}>
                        <span style={sectionLabel}>시각</span>
                        <div style={clocksRow}>
                            <ClockBlock label="서울" time={seoulNow} marketOpen={krxOpen} marketName="KRX" />
                            <ClockBlock label="뉴욕" time={nyNow} marketOpen={nyseOpen} marketName="NYSE" />
                        </div>
                    </div>

                    {/* Section: 시장 뉴스 (NewsHeadline 흡수, 2026-05-05) */}
                    {Array.isArray(data?.headlines) && data.headlines.length > 0 && (
                        <>
                            <div style={hr} />
                            <div style={sectionRow}>
                                <span style={sectionLabel}>시장 뉴스</span>
                                <div style={newsListStyle}>
                                    {data.headlines.slice(0, 5).map((h: any, i: number) => {
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
                                                <span style={newsTitleStyle}>{h.title}</span>
                                                {h.source && (
                                                    <span style={newsSourceStyle}>
                                                        {h.source}
                                                    </span>
                                                )}
                                                {h.time && (
                                                    <span style={newsTimeStyle}>
                                                        {String(h.time).slice(5, 16)}
                                                    </span>
                                                )}
                                                {href && (
                                                    <span style={newsArrowStyle}>↗</span>
                                                )}
                                            </>
                                        )
                                        return href ? (
                                            <a
                                                key={i}
                                                href={href}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                style={newsRowStyle}
                                            >
                                                {inner}
                                            </a>
                                        ) : (
                                            <div key={i} style={{ ...newsRowStyle, cursor: "default" }}>
                                                {inner}
                                            </div>
                                        )
                                    })}
                                </div>
                            </div>
                        </>
                    )}
                </div>
            )}
        </div>
    )
}


/* ─────────── 서브 컴포넌트 ─────────── */

function StatusDot({ on, label }: { on: boolean; label: string }) {
    return (
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <span style={{
                width: 8, height: 8, borderRadius: "50%",
                background: on ? C.success : C.textDisabled,
                boxShadow: "none",
                transition: X.base,
            }} />
            <span style={{ color: on ? C.textPrimary : C.textTertiary, fontSize: T.cap, fontWeight: T.w_semi, letterSpacing: 0.5 }}>
                {label}
            </span>
        </span>
    )
}

function Sep() { return <span style={{ width: 1, height: 16, background: C.border, flexShrink: 0 }} /> }

function IndexChip({ label, value, pct }: { label: string; value?: number | null; pct?: number | null }) {
    return (
        <div style={chipWrap}>
            <span style={chipLabel}>{label}</span>
            <span style={{ ...chipValue, ...MONO }}>{fmtIndex(value)}</span>
            {pct != null && Number.isFinite(pct) && (
                <span style={{ ...chipPct, ...MONO, color: signedColor(pct) }}>{fmtPct(pct)}</span>
            )}
        </div>
    )
}

function IndexChipInline({ label, value, pct, color }: { label: string; value?: number | null; pct?: number | null; color?: string }) {
    return (
        <span style={chipWrap}>
            <span style={chipLabel}>{label}</span>
            <span style={{ ...chipValue, ...MONO, color: color || C.textPrimary }}>{fmtIndex(value)}</span>
            {pct != null && Number.isFinite(pct) && (
                <span style={{ ...chipPct, ...MONO, color: signedColor(pct) }}>{fmtPct(pct)}</span>
            )}
        </span>
    )
}

function CommodityChip({ label, value, pct }: { label: string; value?: number | null; pct?: number | null }) {
    return (
        <div style={chipWrap}>
            <span style={{ ...chipLabel, color: C.textSecondary, fontWeight: T.w_semi, letterSpacing: 0.5 }}>{label}</span>
            <span style={{ ...chipValue, ...MONO }}>{value != null ? `$${value.toLocaleString()}` : "—"}</span>
            {pct != null && Number.isFinite(pct) && (
                <span style={{ ...chipPct, ...MONO, color: signedColor(pct) }}>{fmtPct(pct)}</span>
            )}
        </div>
    )
}

function ClockBlock({ label, time, marketOpen, marketName }: {
    label: string; time: string; marketOpen: boolean; marketName: string
}) {
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med, letterSpacing: 0.5, textTransform: "uppercase" }}>{label}</span>
            <span style={{ ...MONO, color: C.textPrimary, fontSize: T.sub, fontWeight: T.w_bold }}>{time}</span>
            <span style={{
                color: marketOpen ? C.success : C.textTertiary,
                fontSize: T.cap, fontWeight: T.w_semi, letterSpacing: 0.5,
            }}>
                {marketName} {marketOpen ? "OPEN" : "CLOSED"}
            </span>
        </div>
    )
}

function vixColor(v?: number | null): string {
    if (v == null || !Number.isFinite(v)) return C.textPrimary
    if (v > 25) return C.danger
    if (v < 18) return C.success
    return C.warn
}


/* ─────────── 스타일 ─────────── */

const shell: React.CSSProperties = {
    width: "100%", boxSizing: "border-box",
    fontFamily: FONT, color: C.textPrimary,
    background: C.bgPage, borderBottom: `1px solid ${C.border}`,
}

const defaultRow: React.CSSProperties = {
    display: "flex", alignItems: "center", gap: S.lg,
    padding: `${S.md}px ${S.xxl}px`, minHeight: 52,
}

const statusBlock: React.CSSProperties = {
    display: "flex", alignItems: "center", gap: S.md,
    flexShrink: 0,
}

const midBlock: React.CSSProperties = {
    display: "flex", alignItems: "center", gap: S.md,
    flex: 1, justifyContent: "center", flexWrap: "nowrap", minWidth: 0,
}

const rightBlock: React.CSSProperties = {
    display: "flex", alignItems: "center", gap: S.md,
    flexShrink: 0,
}

const timeStyle: React.CSSProperties = {
    ...MONO, fontSize: T.body, fontWeight: T.w_med,
}

const moreBtn: React.CSSProperties = {
    background: "transparent", border: `1px solid ${C.border}`,
    padding: `${S.xs}px ${S.md}px`, borderRadius: R.md,
    fontSize: T.cap, fontWeight: T.w_semi, letterSpacing: 0.5,
    fontFamily: FONT, cursor: "pointer", transition: X.base,
}

const expandPanel: React.CSSProperties = {
    display: "flex", flexDirection: "column", gap: S.lg,
    padding: `${S.lg}px ${S.xxl}px ${S.xl}px ${S.xxl}px`,
    borderTop: `1px solid ${C.border}`,
    background: C.bgPage,
}

const sectionRow: React.CSSProperties = {
    display: "flex", alignItems: "center", gap: S.lg,
    flexWrap: "wrap",
}

const sectionLabel: React.CSSProperties = {
    color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med,
    letterSpacing: 0.5, textTransform: "uppercase",
    minWidth: 80, flexShrink: 0,
}

const o2Row: React.CSSProperties = {
    display: "flex", alignItems: "center", gap: S.sm,
    flex: 1, minWidth: 200,
}

const o2Bar: React.CSSProperties = {
    flex: 1, height: 4, borderRadius: 2, overflow: "hidden", maxWidth: 240,
}

const chipsRow: React.CSSProperties = {
    display: "flex", alignItems: "center", gap: S.lg,
    flexWrap: "wrap", flex: 1,
}

/* News list style (NewsHeadline 흡수, 2026-05-05) */
const newsListStyle: React.CSSProperties = {
    display: "flex", flexDirection: "column", gap: S.xs,
    flex: 1, minWidth: 0,
}

const newsRowStyle: React.CSSProperties = {
    display: "flex", alignItems: "center", gap: S.sm,
    padding: `${S.xs}px ${S.sm}px`,
    borderRadius: R.sm,
    textDecoration: "none",
    transition: X.fast,
    cursor: "pointer",
}

const newsTitleStyle: React.CSSProperties = {
    color: C.textSecondary, fontSize: T.cap,
    lineHeight: 1.4, flex: 1,
    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
}

const newsSourceStyle: React.CSSProperties = {
    color: C.textTertiary, fontSize: T.cap, flexShrink: 0,
    letterSpacing: 0.5,
}

const newsTimeStyle: React.CSSProperties = {
    ...MONO,
    color: C.textDisabled, fontSize: T.cap, flexShrink: 0,
}

const newsArrowStyle: React.CSSProperties = {
    color: C.textTertiary, fontSize: T.cap, flexShrink: 0,
}

const clocksRow: React.CSSProperties = {
    display: "flex", alignItems: "flex-start", gap: S.xxl,
    flex: 1,
}

const chipWrap: React.CSSProperties = {
    display: "inline-flex", alignItems: "baseline", gap: 6,
}

const chipLabel: React.CSSProperties = {
    color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med,
    letterSpacing: 0.5,
}

const chipValue: React.CSSProperties = {
    color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi,
}

const chipPct: React.CSSProperties = {
    fontSize: T.cap, fontWeight: T.w_semi,
}

const hr: React.CSSProperties = {
    height: 1, background: C.border, margin: 0,
}


/* ─────────── Framer Property Controls ─────────── */

SiteHeader.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
    refreshIntervalSec: 180,
}

addPropertyControls(SiteHeader, {
    dataUrl: {
        type: ControlType.String,
        title: "Portfolio URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
    },
    refreshIntervalSec: {
        type: ControlType.Number,
        title: "갱신 간격(초)",
        defaultValue: 180,
        min: 30, max: 3600, step: 30,
    },
})
