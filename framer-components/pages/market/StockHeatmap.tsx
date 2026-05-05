import { addPropertyControls, ControlType } from "framer"
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * StockHeatmap — VERITY 종목 히트맵 (Step 4, KRXHeatmap 모던 심플)
 *
 * 출처: KRXHeatmap.tsx (516줄) modernize.
 *
 * 설계:
 *   - KR/US toggle (badge + 외부 링크 분기 — Naver / Yahoo)
 *   - 시가총액 가중 grid (flexbox, 큰 종목 큰 박스)
 *   - 호버 툴팁 (종목 detail + 뉴스 + gold insight + 외부 링크)
 *   - 범례 (변화율 7단계)
 *
 * 모던 심플 6원칙:
 *   1. No card-in-card — 외곽 1개 + grid 직접
 *   2. Flat hierarchy — title + 그리드 + 범례
 *   3. Mono numerics — 변화율, 가격, 점수
 *   4. Hover tooltip — 종목 정보 (320px viewport-aware)
 *   5. Color discipline — heat = success/danger 토큰 alpha (7→3 단계 압축)
 *   6. Emoji ▲▼ → 텍스트 / 토큰 dot
 *
 * feedback_no_hardcode_position 적용: inline 렌더링.
 *
 * NOTE: 호버 툴팁은 viewport-fixed (마우스 따라가는 본질) — 예외적 fixed 허용.
 */

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    strongBuy: "#22C55E", buy: "#B5FF19", watch: "#FFD600", caution: "#F59E0B", avoid: "#EF4444",
    success: "#22C55E", warn: "#F59E0B", danger: "#EF4444", info: "#5BA9FF",
}
const G = {
    accent: "0 0 8px rgba(181,255,25,0.35)",
    success: "0 0 6px rgba(34,197,94,0.30)",
    danger: "0 0 6px rgba(239,68,68,0.30)",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_normal: 1.5,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/* ─────────── Portfolio fetch ─────────── */
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


/* ─────────── 헬퍼 ─────────── */
function isKRX(market: string): boolean {
    return /KOSPI|KOSDAQ|KRX|코스피|코스닥/i.test(market || "")
}
function isUSMarket(market: string): boolean {
    return /NYSE|NASDAQ|AMEX|NMS|NGM|NCM/i.test(market || "")
}

function calcPct(sparkline: number[] | undefined): number | null {
    if (!sparkline || sparkline.length < 2) return null
    const last = sparkline[sparkline.length - 1]
    const prev = sparkline[sparkline.length - 2]
    if (!prev) return null
    return ((last - prev) / prev) * 100
}

function naverStockUrl(ticker: string): string { return `https://finance.naver.com/item/main.naver?code=${ticker}` }
function naverHeadlineUrl(headline: string): string { return `https://search.naver.com/search.naver?where=news&query=${encodeURIComponent(headline)}&sort=1` }
function yahooStockUrl(ticker: string): string { return `https://finance.yahoo.com/quote/${ticker}/news` }
function yahooHeadlineUrl(headline: string): string { return `https://finance.yahoo.com/search/?q=${encodeURIComponent(headline)}` }


/* ─────────── 색 매핑 (3 단계 압축, 토큰 alpha) ─────────── */
function boxBg(pct: number | null): string {
    const v = pct ?? 0
    if (v >= 1)  return `${C.success}40`  // strong up (alpha 25%)
    if (v >= 0)  return `${C.success}1F`  // mild up (alpha 12%)
    if (v >= -1) return `${C.danger}1F`   // mild down
    return `${C.danger}40`                // strong down
}

function pctTextColor(pct: number | null): string {
    const v = pct ?? 0
    if (v > 0) return C.success
    if (v < 0) return C.danger
    return C.textTertiary
}

function fmtPct(n: number | null | undefined, digits = 2): string {
    if (n == null || !Number.isFinite(n)) return "—"
    const sign = n > 0 ? "+" : ""
    return `${sign}${n.toFixed(digits)}%`
}


/* ─────────── 시장별 설정 ─────────── */
type MarketKey = "kr" | "us"

interface MarketConfig {
    filter: (m: string) => boolean
    badge: string
    title: string
    minCap: number
    stockUrl: (ticker: string) => string
    headlineUrl: (headline: string) => string
    linkLabel: string
    priceFormatter: (p: number) => string
    loadingText: string
}

const MARKET_CONFIG: Record<MarketKey, MarketConfig> = {
    kr: {
        filter: (m) => isKRX(m),
        badge: "국장",
        title: "KOSPI · KOSDAQ 히트맵",
        minCap: 1e11,
        stockUrl: naverStockUrl,
        headlineUrl: naverHeadlineUrl,
        linkLabel: "네이버 금융에서 보기 →",
        priceFormatter: (p) => `${(p ?? 0).toLocaleString()}원`,
        loadingText: "국장 히트맵 로딩 중…",
    },
    us: {
        filter: (m) => isUSMarket(m),
        badge: "미장",
        title: "NYSE · NASDAQ 히트맵",
        minCap: 1e9,
        stockUrl: yahooStockUrl,
        headlineUrl: yahooHeadlineUrl,
        linkLabel: "Yahoo Finance 보기 →",
        priceFormatter: (p) =>
            p != null ? `$${Number(p).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—",
        loadingText: "미장 히트맵 로딩 중…",
    },
}


/* ═══════════════════════════ 메인 ═══════════════════════════ */

interface Props {
    dataUrl: string
    market: MarketKey
}

export default function StockHeatmap({ dataUrl, market }: Props) {
    const [data, setData] = useState<any>(null)
    const [hovered, setHovered] = useState<any>(null)
    const [tipPos, setTipPos] = useState({ x: 0, y: 0 })
    const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

    const cfg = MARKET_CONFIG[market] || MARKET_CONFIG.kr

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal).then((d) => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    const clearHide = useCallback(() => {
        if (hideTimer.current) clearTimeout(hideTimer.current)
    }, [])
    const startHide = useCallback(() => {
        clearHide()
        hideTimer.current = setTimeout(() => setHovered(null), 280)
    }, [clearHide])
    const showTooltip = useCallback((stock: any, x: number, y: number) => {
        clearHide()
        setHovered(stock)
        setTipPos({ x, y })
    }, [clearHide])
    const handleMouseMove = useCallback((e: React.MouseEvent) => {
        setTipPos({ x: e.clientX, y: e.clientY })
    }, [])

    const recs: any[] = data?.recommendations || []
    const stocks = recs.filter((s: any) => cfg.filter(s.market || ""))
    const totalCap = stocks.reduce((acc: number, s: any) => acc + Math.max(s.market_cap || 0, cfg.minCap), 0)

    if (!data) {
        return (
            <div style={shell}>
                <div style={loadingBox}>
                    <span style={{ color: C.textTertiary, fontSize: T.body }}>{cfg.loadingText}</span>
                </div>
            </div>
        )
    }

    const upCount = stocks.filter((s: any) => (calcPct(s.sparkline) ?? 0) > 0).length
    const downCount = stocks.filter((s: any) => (calcPct(s.sparkline) ?? 0) < 0).length

    return (
        <div style={shell}>
            {/* Header */}
            <div style={headerRow}>
                <div style={headerLeft}>
                    <div style={{ display: "flex", alignItems: "center", gap: S.md }}>
                        <span style={badgeStyle}>{cfg.badge}</span>
                        <span style={titleStyle}>{cfg.title}</span>
                    </div>
                    <div style={metaRow}>
                        <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap }}>
                            {stocks.length}개
                        </span>
                        <span style={{ color: C.textDisabled, fontSize: T.cap }}>·</span>
                        <span style={{ ...MONO, color: C.success, fontSize: T.cap, fontWeight: T.w_semi }}>
                            상승 {upCount}
                        </span>
                        <span style={{ color: C.textDisabled, fontSize: T.cap }}>·</span>
                        <span style={{ ...MONO, color: C.danger, fontSize: T.cap, fontWeight: T.w_semi }}>
                            하락 {downCount}
                        </span>
                    </div>
                </div>
            </div>

            <div style={hr} />

            {/* Heatmap grid */}
            <div style={gridWrap}>
                {stocks.map((s: any) => {
                    const pct = calcPct(s.sparkline)
                    const weight = Math.max(((s.market_cap || cfg.minCap) / totalCap) * 100, 3)
                    const isHov = hovered?.ticker === s.ticker
                    const fontSizeName = Math.min(13, 8 + weight * 0.4)
                    const fontSizeTicker = Math.min(10, 7 + weight * 0.2)
                    const fontSizePct = Math.min(12, 7 + weight * 0.3)

                    return (
                        <div
                            key={s.ticker}
                            onMouseEnter={(e) => showTooltip(s, e.clientX, e.clientY)}
                            onMouseMove={handleMouseMove}
                            onMouseLeave={startHide}
                            style={{
                                flexBasis: `calc(${weight}% - 3px)`,
                                flexGrow: weight,
                                minWidth: 56,
                                height: 80,
                                background: boxBg(pct),
                                borderRadius: R.sm,
                                display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
                                gap: 2,
                                cursor: "pointer",
                                border: isHov ? `1.5px solid ${C.borderHover}` : `1.5px solid transparent`,
                                transition: "border 0.12s, opacity 0.12s",
                                opacity: hovered && !isHov ? 0.6 : 1,
                                overflow: "hidden",
                                padding: "4px 4px",
                                boxShadow: "none",
                            }}
                        >
                            <span
                                style={{
                                    color: C.textPrimary,
                                    fontSize: fontSizeName,
                                    fontWeight: T.w_bold,
                                    lineHeight: 1.2,
                                    maxWidth: "95%",
                                    overflow: "hidden",
                                    textOverflow: "ellipsis",
                                    whiteSpace: "nowrap",
                                    textAlign: "center",
                                }}
                            >
                                {s.name}
                            </span>
                            <span
                                style={{
                                    ...MONO,
                                    color: C.textTertiary,
                                    fontSize: fontSizeTicker,
                                    lineHeight: 1,
                                }}
                            >
                                {s.ticker}
                            </span>
                            {pct != null && (
                                <span
                                    style={{
                                        ...MONO,
                                        color: pctTextColor(pct),
                                        fontSize: fontSizePct,
                                        fontWeight: T.w_semi,
                                        marginTop: 1,
                                    }}
                                >
                                    {fmtPct(pct)}
                                </span>
                            )}
                        </div>
                    )
                })}
            </div>

            <div style={hr} />

            {/* Legend */}
            <div style={legendRow}>
                <LegendCell label="+1% 이상" bg={`${C.success}40`} />
                <LegendCell label="0~+1%" bg={`${C.success}1F`} />
                <LegendCell label="0~-1%" bg={`${C.danger}1F`} />
                <LegendCell label="-1% 이하" bg={`${C.danger}40`} />
                <span style={{ color: C.textTertiary, fontSize: T.cap, marginLeft: "auto" }}>
                    sparkline 전일 대비
                </span>
            </div>

            {/* Hover tooltip (viewport-fixed, 마우스 추적 본질) */}
            {hovered && (
                <HeatmapTooltip
                    stock={hovered}
                    pos={tipPos}
                    cfg={cfg}
                    onMouseEnter={clearHide}
                    onMouseLeave={startHide}
                />
            )}
        </div>
    )
}


/* ─────────── 서브 컴포넌트 ─────────── */

function LegendCell({ label, bg }: { label: string; bg: string }) {
    return (
        <div style={{ display: "inline-flex", alignItems: "center", gap: S.xs }}>
            <span style={{ width: 12, height: 12, borderRadius: 2, background: bg }} />
            <span style={{ color: C.textTertiary, fontSize: T.cap, fontFamily: FONT }}>{label}</span>
        </div>
    )
}

function HeatmapTooltip({
    stock, pos, cfg, onMouseEnter, onMouseLeave,
}: {
    stock: any
    pos: { x: number; y: number }
    cfg: MarketConfig
    onMouseEnter: () => void
    onMouseLeave: () => void
}) {
    const pct = calcPct(stock.sparkline)
    const rec = stock.recommendation || "WATCH"
    const recColor =
        rec === "STRONG_BUY" ? C.strongBuy
        : rec === "BUY" ? C.buy
        : rec === "WATCH" ? C.watch
        : rec === "CAUTION" ? C.caution
        : rec === "AVOID" ? C.avoid
        : C.textTertiary
    const ms = stock.multi_factor?.multi_score ?? stock.safety_score ?? 0

    const newsItems: Array<{ title: string; url: string }> =
        (stock.sentiment?.top_headline_links || []).length > 0
            ? stock.sentiment.top_headline_links
            : (stock.sentiment?.top_headlines || []).map((h: string) => ({ title: h, url: cfg.headlineUrl(h) }))

    const TIP_W = 300
    const winW = typeof window !== "undefined" ? window.innerWidth : 1400
    const winH = typeof window !== "undefined" ? window.innerHeight : 900
    const left = pos.x + TIP_W + 24 > winW ? pos.x - TIP_W - 16 : pos.x + 16
    const top = Math.min(pos.y - 10, winH - 360)

    return (
        <div
            onMouseEnter={onMouseEnter}
            onMouseLeave={onMouseLeave}
            style={{
                position: "fixed",
                left, top,
                width: TIP_W, zIndex: 9999,
                background: C.bgElevated,
                border: `1px solid ${C.borderStrong}`,
                borderRadius: R.md,
                padding: `${S.md}px ${S.lg}px`,
                boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
                fontFamily: FONT,
                cursor: "default",
                display: "flex", flexDirection: "column", gap: S.sm,
            }}
        >
            {/* 종목 + 등급 */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: S.sm }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_bold }}>
                        {stock.name}
                    </div>
                    <div style={{ ...MONO, color: C.textTertiary, fontSize: T.cap, marginTop: 2 }}>
                        {stock.ticker} · {stock.market}
                    </div>
                </div>
                <span
                    style={{
                        background: recColor,
                        color: rec === "WATCH" ? C.bgPage : recColor === C.buy || recColor === C.watch || recColor === C.strongBuy ? C.bgPage : C.textPrimary,
                        fontSize: T.cap,
                        fontWeight: T.w_bold,
                        letterSpacing: 0.5,
                        padding: "2px 6px",
                        borderRadius: R.sm,
                        fontFamily: FONT,
                        flexShrink: 0,
                    }}
                    title={rec === "AVOID" ? "AVOID = 펀더멘털 결함 (감사거절·분식·상폐 위험 등). 단순 저점수는 CAUTION." : undefined}
                >
                    {rec}
                </span>
            </div>

            {/* 가격 + 변화율 + 점수 */}
            <div style={{ display: "flex", alignItems: "baseline", gap: S.md }}>
                <span style={{ ...MONO, color: C.textPrimary, fontSize: T.body, fontWeight: T.w_bold }}>
                    {cfg.priceFormatter(stock.price)}
                </span>
                {pct != null && (
                    <span style={{ ...MONO, color: pctTextColor(pct), fontSize: T.cap, fontWeight: T.w_semi }}>
                        {fmtPct(pct)}
                    </span>
                )}
                <span style={{ color: C.textTertiary, fontSize: T.cap, marginLeft: "auto" }}>
                    VERITY <span style={{ ...MONO, color: C.textSecondary, fontWeight: T.w_semi }}>{ms}</span>점
                </span>
            </div>

            <div style={{ height: 1, background: C.border }} />

            {/* 뉴스 */}
            {newsItems.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                    <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med, letterSpacing: 0.5, textTransform: "uppercase" }}>
                        최신 뉴스
                    </span>
                    {newsItems.slice(0, 3).map((item, i) => (
                        <a
                            key={i}
                            href={item.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ display: "flex", gap: S.xs, alignItems: "flex-start", textDecoration: "none" }}
                        >
                            <span style={{ color: C.textTertiary, fontSize: T.cap, flexShrink: 0, marginTop: 2 }}>·</span>
                            <span style={{ color: C.textSecondary, fontSize: T.cap, lineHeight: T.lh_normal }}>
                                {item.title}
                            </span>
                        </a>
                    ))}
                </div>
            ) : (
                <span style={{ color: C.textTertiary, fontSize: T.cap }}>뉴스 없음</span>
            )}

            {/* gold insight */}
            {stock.gold_insight && (
                <>
                    <div style={{ height: 1, background: C.border }} />
                    <div style={{ display: "flex", gap: S.xs, alignItems: "flex-start" }}>
                        <span
                            style={{
                                background: C.watch, color: C.bgPage,
                                fontSize: 9, fontWeight: T.w_black,
                                padding: "1px 5px", borderRadius: R.sm,
                                flexShrink: 0, marginTop: 2,
                                letterSpacing: 0.5,
                            }}
                        >
                            G
                        </span>
                        <span style={{ color: C.textSecondary, fontSize: T.cap, lineHeight: T.lh_normal }}>
                            {stock.gold_insight}
                        </span>
                    </div>
                </>
            )}

            <div style={{ height: 1, background: C.border }} />

            {/* 외부 링크 */}
            <a
                href={cfg.stockUrl(stock.ticker)}
                target="_blank"
                rel="noopener noreferrer"
                style={{ textDecoration: "none" }}
            >
                <span style={{ color: C.info, fontSize: T.cap, fontWeight: T.w_semi }}>
                    {cfg.linkLabel}
                </span>
            </a>
        </div>
    )
}


/* ─────────── 스타일 ─────────── */

const shell: CSSProperties = {
    width: "100%", boxSizing: "border-box",
    fontFamily: FONT, color: C.textPrimary,
    background: C.bgPage,
    border: `1px solid ${C.border}`,
    borderRadius: 16,
    padding: S.xxl,
    display: "flex", flexDirection: "column",
    gap: S.lg,
    position: "relative",  // 호버 툴팁 anchor 가능 (실제론 fixed 사용)
}

const headerRow: CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    gap: S.md, flexWrap: "wrap",
}

const headerLeft: CSSProperties = {
    display: "flex", flexDirection: "column", gap: S.xs,
}

const titleStyle: CSSProperties = {
    fontSize: T.h2, fontWeight: T.w_bold, color: C.textPrimary,
    letterSpacing: "-0.5px",
}

const badgeStyle: CSSProperties = {
    color: C.accent,
    background: C.accentSoft,
    fontSize: T.cap, fontWeight: T.w_bold,
    letterSpacing: 0.5,
    padding: `2px ${S.sm}px`,
    borderRadius: R.sm,
    fontFamily: FONT,
}

const metaRow: CSSProperties = {
    display: "flex", alignItems: "center", gap: S.sm,
}

const hr: CSSProperties = {
    height: 1, background: C.border, margin: 0,
}

const gridWrap: CSSProperties = {
    display: "flex", flexWrap: "wrap", gap: 3,
}

const legendRow: CSSProperties = {
    display: "flex", alignItems: "center", flexWrap: "wrap",
    gap: S.md,
}

const loadingBox: CSSProperties = {
    minHeight: 200,
    display: "flex", alignItems: "center", justifyContent: "center",
}


/* ─────────── Framer Property Controls ─────────── */

StockHeatmap.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
    market: "kr",
}

addPropertyControls(StockHeatmap, {
    dataUrl: {
        type: ControlType.String,
        title: "Portfolio URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
    },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["KR 국장", "US 미장"],
        defaultValue: "kr",
    },
})
