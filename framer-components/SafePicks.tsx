/**
 * ⚠️ DEPRECATED (2026-05-05 Plan v0.1 §3 [Stock] 폐기 결정)
 *
 * Brain v5 5등급 + Lynch 분류 + Graham value sub-score 가 안전 종목 자동 surface. 별도 컴포넌트 X
 *
 * Framer 페이지에서 인스턴스 제거. 추후 일괄 cleanup commit 시 git rm.
 *
 * ────────────────────────────────────────────────────────────
 */
import { addPropertyControls, ControlType } from "framer"
import { useEffect, useMemo, useState, type CSSProperties } from "react"

/**
 * SafePicks — 안정 추천 (Step 6.2 모던 심플)
 *
 * 출처: SafePicks.tsx (329줄) 통째 재작성.
 *
 * 설계:
 *   - KR/US toggle (시장별 배당주 + 현금 파킹)
 *   - tab 2개: 배당주 / 현금 파킹
 *   - 배당주 tier (S/A/B) + payout/debt/operating margin
 *   - 현금 파킹 옵션 (KR 단기국채 / US T-Bill / MMF)
 *   - macro mood 기반 권고 메시지 (defensive/cautious/balanced)
 *
 * 모던 심플 6원칙:
 *   1. No card-in-card — 외곽 1개 + 카드 grid
 *   2. Flat hierarchy — title + tab + list
 *   3. Mono numerics — 배당%, 가격, 비율
 *   4. Color discipline — tier S/A/B = accent/success/watch 토큰
 *   5. Emoji 0
 *   6. 자체 색 (#FF4D4D, #1A0000, #777, #fff, #1A1A1A 등) 폐기
 *
 * feedback_no_hardcode_position 적용: inline 렌더링.
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
    warn: "0 0 6px rgba(245,158,11,0.30)",
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

const DATA_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json"


/* ─────────── 배당주 도출 (자체 필터) ─────────── */
function deriveDividendPicks(recommendations: any[], macro: any): any[] {
    const us10y = macro?.us_10y?.value ?? 3.5
    const threshold = Math.max(us10y * 0.8, 2.0)

    const picks: any[] = []
    for (const s of recommendations) {
        const divYield = s.div_yield ?? 0
        const debtRatio = s.debt_ratio ?? 0
        const opMargin = s.operating_margin ?? 0
        const eps = s.eps ?? 0
        const price = s.price ?? 0

        if (divYield <= threshold || divYield > 20 || debtRatio > 80 || opMargin < 5) continue
        if (eps <= 0) continue

        let payoutRatio = 0
        if (price > 0 && divYield > 0) {
            payoutRatio = ((price * divYield / 100) / eps) * 100
        }
        if (payoutRatio <= 0 || payoutRatio > 60) continue

        let tier = "A"
        if (divYield >= 4 && debtRatio < 50 && opMargin > 10) tier = "S"
        else if (divYield < 3 || debtRatio > 60) tier = "B"

        picks.push({
            ticker: s.ticker,
            name: s.name,
            currency: s.currency,
            price: s.price,
            div_yield: +divYield.toFixed(2),
            payout_ratio: +payoutRatio.toFixed(1),
            debt_ratio: +debtRatio.toFixed(1),
            operating_margin: +opMargin.toFixed(1),
            safety_tier: tier,
            reason: `배당 ${divYield.toFixed(1)}% (기준 ${threshold.toFixed(1)}% 초과)${debtRatio < 40 ? " · 저부채" : ""}${opMargin > 15 ? " · 고수익" : ""}`,
        })
    }

    picks.sort((a, b) => {
        const tierOrder: Record<string, number> = { S: 0, A: 1, B: 2 }
        return (tierOrder[a.safety_tier] ?? 2) * 100 - a.div_yield * 10
            - ((tierOrder[b.safety_tier] ?? 2) * 100 - b.div_yield * 10)
    })
    return picks.slice(0, 10)
}


/* ─────────── 현금 파킹 옵션 도출 ─────────── */
function deriveParkingOptions(macro: any): any {
    const usdKrw = macro?.usd_krw?.value ?? 0
    const us10y = macro?.us_10y?.value ?? 0
    const us2y = macro?.us_2y?.value ?? 0
    const vix = macro?.vix?.value ?? 0
    const moodScore = macro?.market_mood?.score ?? 50
    const krRate = Math.max(us10y - 0.5, 2.5)

    const options: any[] = [
        { type: "kr_bond", name: "한국 단기국채 (1-3년)", est_yield: +krRate.toFixed(2), risk: "매우 낮음", liquidity: "높음", suitable: true },
    ]
    if (us2y > 3.5) {
        options.push({
            type: "us_tbill", name: "미국 단기국채 (T-Bill)", est_yield: +us2y.toFixed(2),
            risk: "매우 낮음 (환위험 존재)", liquidity: "높음", suitable: usdKrw < 1400,
            note: `환율 ${usdKrw.toLocaleString()}원${usdKrw < 1300 ? " — 원화 강세 시 유리" : " — 환헤지 고려"}`,
        })
    }
    options.push({ type: "mmf", name: "MMF/CMA (수시입출금)", est_yield: +Math.max(krRate - 0.5, 2.0).toFixed(2), risk: "매우 낮음", liquidity: "최고", suitable: true })

    let recommendation: "defensive" | "cautious" | "balanced" = "balanced"
    let message = "시장 안정 — 안전자산 10~20% 유지로 충분"
    if (vix > 25 || moodScore < 35) {
        recommendation = "defensive"
        message = `VIX ${vix}, 시장 불안 — 현금/국채 비중 확대 강력 권고`
    } else if (moodScore < 45) {
        recommendation = "cautious"
        message = "시장 관망 구간 — 안전자산 30~40% 유지 권장"
    }

    return { options, recommendation, message }
}


/* ─────────── 색 매핑 ─────────── */
function tierColor(tier: string): string {
    if (tier === "S") return C.accent
    if (tier === "A") return C.success
    if (tier === "B") return C.watch
    return C.textTertiary
}

function recColors(rec: string): { color: string; glow: string } {
    if (rec === "defensive") return { color: C.danger, glow: G.danger }
    if (rec === "cautious") return { color: C.warn, glow: G.warn }
    return { color: C.success, glow: G.success }
}

function fmtPct(n: number | null | undefined, digits = 2): string {
    if (n == null || !Number.isFinite(n)) return "—"
    return `${n.toFixed(digits)}%`
}


/* ═══════════════════════════ 메인 ═══════════════════════════ */

interface Props {
    dataUrl: string
    market: "kr" | "us"
}

export default function SafePicks(props: Props) {
    const { dataUrl, market = "kr" } = props
    const isUS = market === "us"
    const [data, setData] = useState<any>(null)
    const [error, setError] = useState(false)
    const [tab, setTab] = useState<"dividend" | "parking">("dividend")

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal)
            .then((d) => { if (!ac.signal.aborted) setData(d) })
            .catch(() => { if (!ac.signal.aborted) setError(true) })
        return () => ac.abort()
    }, [dataUrl])

    const { dividends, parking, options } = useMemo(() => {
        if (!data) return { dividends: [] as any[], parking: {} as any, options: [] as any[] }

        const safe = data.safe_recommendations
        if (safe && (safe.dividend_stocks?.length || safe.parking_options?.options?.length)) {
            return {
                dividends: (safe.dividend_stocks || []).filter((s: any) =>
                    (s.div_yield ?? 0) <= 20 && (s.payout_ratio ?? 0) > 0
                ),
                parking: safe.parking_options || {},
                options: safe.parking_options?.options || [],
            }
        }

        const allRecs = data.recommendations || []
        const recs = isUS
            ? allRecs.filter((r: any) => r.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM/i.test(r.market || ""))
            : allRecs.filter((r: any) => /KOSPI|KOSDAQ|KRX/i.test(r.market || ""))
        const macro = data.macro || {}
        return {
            dividends: deriveDividendPicks(recs, macro),
            parking: deriveParkingOptions(macro),
            options: deriveParkingOptions(macro).options,
        }
    }, [data, isUS])

    if (error) {
        return (
            <div style={shell}>
                <div style={loadingBox}>
                    <span style={{ color: C.danger, fontSize: T.body }}>데이터를 불러올 수 없습니다</span>
                </div>
            </div>
        )
    }

    if (!data) {
        return (
            <div style={shell}>
                <div style={loadingBox}>
                    <span style={{ color: C.textTertiary, fontSize: T.body }}>로딩 중…</span>
                </div>
            </div>
        )
    }

    const recC = parking.message ? recColors(parking.recommendation) : null

    return (
        <div style={shell}>
            {/* Header */}
            <div style={headerRow}>
                <div style={headerLeft}>
                    <span style={titleStyle}>안정 추천</span>
                    <span style={metaStyle}>
                        {isUS ? "US 시장" : "KR 시장"} · 배당주 + 현금 파킹
                    </span>
                </div>
            </div>

            {/* Recommendation banner */}
            {parking.message && recC && (
                <div
                    style={{
                        background: `${recC.color}1A`,
                        border: `1px solid ${recC.color}33`,
                        borderRadius: R.md,
                        padding: `${S.md}px ${S.lg}px`,
                        display: "flex", alignItems: "center", gap: S.sm,
                    }}
                >
                    <span
                        style={{
                            width: 6, height: 6, borderRadius: "50%",
                            background: recC.color, boxShadow: recC.glow, flexShrink: 0,
                        }}
                    />
                    <span style={{ color: recC.color, fontSize: T.body, fontWeight: T.w_semi }}>
                        {parking.message}
                    </span>
                </div>
            )}

            {/* Tab row */}
            <div style={tabRow}>
                <TabButton label={`배당주 ${dividends.length}`} active={tab === "dividend"} onClick={() => setTab("dividend")} />
                <TabButton label={`현금 파킹 ${options.length}`} active={tab === "parking"} onClick={() => setTab("parking")} />
            </div>

            {/* Dividend tab */}
            {tab === "dividend" && (
                <div style={listWrap}>
                    {dividends.length === 0 ? (
                        <div style={emptyBox}>
                            <span style={{ color: C.textTertiary, fontSize: T.body }}>
                                조건 충족 배당주 없음
                            </span>
                        </div>
                    ) : (
                        dividends.map((s: any) => <DividendCard key={s.ticker} stock={s} />)
                    )}
                </div>
            )}

            {/* Parking tab */}
            {tab === "parking" && (
                <div style={listWrap}>
                    {options.map((opt: any, i: number) => <ParkingCard key={i} opt={opt} />)}
                    <div style={footnote}>
                        예상 수익률은 현재 금리 환경 기반 추정치. 실제 상품별 금리는 증권사 확인.
                    </div>
                </div>
            )}
        </div>
    )
}


/* ─────────── 서브 컴포넌트 ─────────── */

function TabButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
    return (
        <button
            onClick={onClick}
            style={{
                background: active ? C.accentSoft : "transparent",
                border: `1px solid ${active ? C.accent : C.border}`,
                color: active ? C.accent : C.textSecondary,
                padding: `${S.sm}px ${S.lg}px`,
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

function DividendCard({ stock }: { stock: any }) {
    const tC = tierColor(stock.safety_tier)
    const isUSD = stock.currency === "USD"
    const priceText = isUSD
        ? `$${(stock.price ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
        : `${(stock.price ?? 0).toLocaleString()}원`

    return (
        <div style={cardStyle}>
            {/* Top row: tier + name + 배당% */}
            <div style={cardTopRow}>
                <div style={{ display: "flex", alignItems: "center", gap: S.sm, flex: 1, minWidth: 0 }}>
                    <span
                        style={{
                            background: tC,
                            color: "#0E0F11",
                            fontSize: T.cap,
                            fontWeight: T.w_black,
                            width: 22, height: 22, borderRadius: "50%",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            flexShrink: 0,
                        }}
                    >
                        {stock.safety_tier}
                    </span>
                    <div style={{ minWidth: 0, flex: 1 }}>
                        <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_bold }}>
                            {stock.name}
                        </span>
                        <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap, marginLeft: S.sm }}>
                            {stock.ticker}
                        </span>
                    </div>
                </div>
                <div style={{ textAlign: "right", flexShrink: 0 }}>
                    <div style={{ ...MONO, color: C.accent, fontSize: T.title, fontWeight: T.w_bold, lineHeight: 1.1 }}>
                        {fmtPct(stock.div_yield)}
                    </div>
                    <div style={{ color: C.textTertiary, fontSize: T.cap, marginTop: 2 }}>
                        배당수익률
                    </div>
                </div>
            </div>

            {/* Metrics row */}
            <div style={metricsRow}>
                <MiniMetric label="현재가" value={priceText} />
                <MiniMetric
                    label="배당성향"
                    value={stock.payout_ratio != null ? `${stock.payout_ratio}%` : "—"}
                    color={(stock.payout_ratio ?? 100) < 40 ? C.success : C.warn}
                />
                <MiniMetric
                    label="부채"
                    value={stock.debt_ratio != null ? `${stock.debt_ratio}%` : "—"}
                    color={(stock.debt_ratio ?? 100) < 50 ? C.success : C.warn}
                />
                <MiniMetric
                    label="영업이익률"
                    value={stock.operating_margin != null ? `${stock.operating_margin}%` : "—"}
                />
            </div>

            {stock.reason && (
                <div style={{ color: C.textTertiary, fontSize: T.cap, lineHeight: T.lh_normal }}>
                    {stock.reason}
                </div>
            )}
        </div>
    )
}

function ParkingCard({ opt }: { opt: any }) {
    return (
        <div style={cardStyle}>
            <div style={cardTopRow}>
                <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_bold }}>
                    {opt.name}
                </span>
                <span style={{ ...MONO, color: C.accent, fontSize: T.title, fontWeight: T.w_bold }}>
                    {opt.est_yield}%
                </span>
            </div>
            <div style={{ display: "flex", gap: S.lg, alignItems: "center" }}>
                <span style={{ color: C.success, fontSize: T.cap }}>
                    위험 <span style={{ color: C.textSecondary }}>{opt.risk}</span>
                </span>
                <span style={{ color: C.info, fontSize: T.cap }}>
                    유동성 <span style={{ color: C.textSecondary }}>{opt.liquidity}</span>
                </span>
            </div>
            {opt.note && (
                <div style={{ color: C.textTertiary, fontSize: T.cap, lineHeight: T.lh_normal }}>
                    {opt.note}
                </div>
            )}
            {!opt.suitable && (
                <div style={{ color: C.danger, fontSize: T.cap, fontWeight: T.w_semi }}>
                    현재 환율 조건 비적합
                </div>
            )}
        </div>
    )
}

function MiniMetric({ label, value, color = C.textPrimary }: { label: string; value: string; color?: string }) {
    return (
        <div style={miniMetric}>
            <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med, letterSpacing: "0.03em" }}>
                {label}
            </span>
            <span style={{ ...MONO, color, fontSize: T.cap, fontWeight: T.w_semi }}>
                {value}
            </span>
        </div>
    )
}


/* ─────────── 스타일 ─────────── */

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
}

const headerLeft: CSSProperties = {
    display: "flex", flexDirection: "column", gap: 2,
}

const titleStyle: CSSProperties = {
    fontSize: T.h2, fontWeight: T.w_bold, color: C.textPrimary,
    letterSpacing: "-0.5px",
}

const metaStyle: CSSProperties = {
    fontSize: T.cap, color: C.textTertiary, fontWeight: T.w_med,
}

const tabRow: CSSProperties = {
    display: "flex", gap: S.sm,
}

const listWrap: CSSProperties = {
    display: "flex", flexDirection: "column", gap: S.md,
}

const cardStyle: CSSProperties = {
    background: C.bgCard,
    border: `1px solid ${C.border}`,
    borderRadius: R.md,
    padding: `${S.md}px ${S.lg}px`,
    display: "flex", flexDirection: "column", gap: S.sm,
}

const cardTopRow: CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    gap: S.md,
}

const metricsRow: CSSProperties = {
    display: "flex", gap: S.sm,
}

const miniMetric: CSSProperties = {
    flex: 1,
    background: C.bgPage,
    borderRadius: R.sm,
    padding: `${S.xs}px ${S.sm}px`,
    display: "flex", flexDirection: "column", gap: 2,
    minWidth: 0,
}

const emptyBox: CSSProperties = {
    padding: `${S.xxl}px 0`, textAlign: "center",
}

const loadingBox: CSSProperties = {
    minHeight: 160,
    display: "flex", alignItems: "center", justifyContent: "center",
}

const footnote: CSSProperties = {
    color: C.textTertiary,
    fontSize: T.cap,
    lineHeight: T.lh_normal,
    padding: `${S.sm}px ${S.md}px`,
    background: C.bgElevated,
    borderRadius: R.sm,
    marginTop: S.xs,
}


/* ─────────── Framer Property Controls ─────────── */

SafePicks.defaultProps = {
    dataUrl: DATA_URL,
    market: "kr",
}

addPropertyControls(SafePicks, {
    dataUrl: {
        type: ControlType.String,
        title: "Portfolio URL",
        defaultValue: DATA_URL,
    },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["KR 국장", "US 미장"],
        defaultValue: "kr",
    },
})
