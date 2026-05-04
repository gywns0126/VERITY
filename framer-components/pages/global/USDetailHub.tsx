import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState, type CSSProperties } from "react"

/**
 * USDetailHub — 미장 detail 통합 (Step 7, US 3→1)
 *
 * 출처:
 *   - USMag7Tracker.tsx (246줄) — Magnificent 7 가격·컨센서스
 *   - USInsiderFeed.tsx (212줄) — 내부자 거래 + SEC 공시
 *   - USAnalystView.tsx (229줄) — 분석가 컨센서스 (Buy/Hold/Sell + 목표가)
 *
 * 통합:
 *   - 외곽 1개 카드 + 메인 탭 3개 (Mag7 / Insider / Analyst)
 *   - portfolio.json recommendations US 필터 공유
 *   - 모던 심플 6원칙 적용
 *
 * 모던 심플:
 *   1. No card-in-card — 외곽 1개 + 탭 + 섹션 spacing
 *   2. Flat hierarchy — title + tab + list
 *   3. Mono numerics — 가격, 변화율, 카운트
 *   4. Color discipline — 토큰만 (success/warn/danger/info)
 *   5. Emoji 0 (✨🍎🪟🔍📦🟢📘⚡▲▼📊🏛️ 폐기)
 *   6. 자체 색 (#22C55E #EF4444 #B5FF19 #ccc #666 #4ADE80 #444 #A78BFA
 *      #60A5FA #0D2A0D #2A0D0D 등) 모두 토큰
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
    up: "#F04452", down: "#3182F6",
    info: "#5BA9FF", success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
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


/* ─────────── 헬퍼 ─────────── */
function isUSStock(r: any): boolean {
    return r?.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(r?.market || "")
}

function fmtPct(n: number | null | undefined, digits = 2): string {
    if (n == null || !Number.isFinite(n)) return "—"
    const sign = n > 0 ? "+" : ""
    return `${sign}${n.toFixed(digits)}%`
}

function fmtUSD(n: number | null | undefined): string {
    if (n == null || !Number.isFinite(n)) return "—"
    return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function fmtMarketCap(mc: number): string {
    if (!Number.isFinite(mc) || mc <= 0) return "—"
    if (mc > 1e6) return `$${(mc / 1e6).toFixed(1)}T`
    if (mc > 1e3) return `$${(mc / 1e3).toFixed(0)}B`
    return `$${mc.toFixed(0)}M`
}

function pctColor(n: number | null | undefined): string {
    if (n == null || !Number.isFinite(n)) return C.textTertiary
    if (n > 0) return C.up
    if (n < 0) return C.down
    return C.textTertiary
}

function pctColorSemantic(n: number | null | undefined): string {
    if (n == null || !Number.isFinite(n)) return C.textTertiary
    if (n > 0) return C.success
    if (n < 0) return C.danger
    return C.textTertiary
}


/* ─────────── Mag 7 ─────────── */
const MAG7_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]


/* ─────────── 미니 sparkline ─────────── */
function MiniSparkline({ data, color }: { data: number[]; color: string }) {
    if (!data || data.length < 2) return null
    const min = Math.min(...data)
    const max = Math.max(...data)
    const range = max - min || 1
    const w = 60, h = 20
    const step = w / (data.length - 1)
    const pts = data.map((v, i) => `${i * step},${h - ((v - min) / range) * h}`).join(" ")
    return (
        <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
            <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    )
}


/* ─────────── SEC form type 색 매핑 ─────────── */
function secFormColor(formType: string): string {
    if (formType === "10-K") return C.warn
    if (formType === "10-Q") return C.info
    if (formType === "8-K") return C.accent
    return C.textTertiary
}


/* ═══════════════════════════ 메인 ═══════════════════════════ */

type Tab = "mag7" | "insider" | "analyst"
type AnalystSort = "upside" | "buy_ratio" | "name"

interface Props {
    dataUrl: string
    recUrl: string
}

export default function USDetailHub(props: Props) {
    const { dataUrl, recUrl } = props
    const [data, setData] = useState<any>(null)
    const [fullRecMap, setFullRecMap] = useState<Record<string, any>>({})
    const [tab, setTab] = useState<Tab>("mag7")
    const [insiderSubTab, setInsiderSubTab] = useState<"insider" | "sec">("insider")
    const [analystSort, setAnalystSort] = useState<AnalystSort>("upside")

    /* portfolio fetch */
    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal)
            .then((d) => { if (!ac.signal.aborted) setData(d) })
            .catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    /* 풀 recommendations fetch (Mag7 시가총액 보강용) */
    useEffect(() => {
        if (!recUrl) return
        const ac = new AbortController()
        fetchJson(recUrl, ac.signal)
            .then((arr: any) => {
                if (ac.signal.aborted) return
                if (!Array.isArray(arr)) return
                const m: Record<string, any> = {}
                arr.forEach((r: any) => { if (r?.ticker) m[r.ticker.toUpperCase()] = r })
                setFullRecMap(m)
            })
            .catch(() => {})
        return () => ac.abort()
    }, [recUrl])

    if (!data) {
        return (
            <div style={shell}>
                <div style={loadingBox}>
                    <span style={{ color: C.textTertiary, fontSize: T.body }}>US 데이터 로딩 중…</span>
                </div>
            </div>
        )
    }

    const slimRecs: any[] = data?.recommendations || []
    const allRecs: any[] = slimRecs.map((r) => ({
        ...r,
        ...(fullRecMap[String(r.ticker || "").toUpperCase()] || {}),
    }))
    const usRecs = allRecs.filter(isUSStock)

    return (
        <div style={shell}>
            {/* Header */}
            <div style={headerRow}>
                <div style={headerLeft}>
                    <span style={titleStyle}>US Detail</span>
                    <span style={metaStyle}>Mag 7 · 내부자/SEC · 분석가 컨센서스</span>
                </div>
                <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap }}>
                    {usRecs.length} 종목
                </span>
            </div>

            {/* Tab row */}
            <div style={tabRow}>
                <TabButton label="Mag 7" active={tab === "mag7"} onClick={() => setTab("mag7")} />
                <TabButton label="Insider · SEC" active={tab === "insider"} onClick={() => setTab("insider")} />
                <TabButton label="Analyst" active={tab === "analyst"} onClick={() => setTab("analyst")} />
            </div>

            <div style={hr} />

            {/* Mag 7 tab */}
            {tab === "mag7" && <Mag7View recs={usRecs} allHoldings={data?.holdings || []} />}

            {/* Insider tab */}
            {tab === "insider" && (
                <InsiderView
                    usRecs={usRecs}
                    subTab={insiderSubTab}
                    setSubTab={setInsiderSubTab}
                />
            )}

            {/* Analyst tab */}
            {tab === "analyst" && (
                <AnalystView
                    usRecs={usRecs}
                    sort={analystSort}
                    setSort={setAnalystSort}
                />
            )}
        </div>
    )
}


/* ─────────── Mag 7 view ─────────── */
function Mag7View({ recs, allHoldings }: { recs: any[]; allHoldings: any[] }) {
    const combined = [...recs, ...allHoldings]
    const mag7 = MAG7_TICKERS
        .map((ticker) => combined.find((r) => (r.ticker || "").toUpperCase() === ticker))
        .filter(Boolean)

    if (mag7.length === 0) {
        return (
            <div style={emptyBox}>
                <span style={{ color: C.textTertiary, fontSize: T.body }}>포트폴리오에 Mag 7 종목 없음</span>
            </div>
        )
    }

    const avgChange = mag7.reduce((s, r) => s + (r?.technical?.price_change_pct || r?.change_pct || 0), 0) / mag7.length
    const gainers = mag7.filter((r) => (r?.technical?.price_change_pct || r?.change_pct || 0) > 0).length
    const losers = mag7.length - gainers

    return (
        <>
            {/* Summary */}
            <div style={summaryRow}>
                <div style={summaryItem}>
                    <span style={summaryCap}>평균 변화</span>
                    <span style={{ ...MONO, color: pctColor(avgChange), fontSize: T.title, fontWeight: T.w_bold }}>
                        {fmtPct(avgChange)}
                    </span>
                </div>
                <div style={summaryItem}>
                    <span style={summaryCap}>상승 / 하락</span>
                    <span style={{ ...MONO, fontSize: T.body, fontWeight: T.w_semi }}>
                        <span style={{ color: C.success }}>{gainers}</span>
                        <span style={{ color: C.textDisabled, margin: "0 4px" }}>/</span>
                        <span style={{ color: C.danger }}>{losers}</span>
                    </span>
                </div>
            </div>

            <div style={hr} />

            {/* Mag 7 list */}
            <div style={listWrap}>
                {mag7.map((stock, i) => {
                    const ticker = (stock.ticker || "").toUpperCase()
                    const changePct = stock.technical?.price_change_pct ?? stock.change_pct ?? 0
                    const price = stock.price || stock.current_price || 0
                    const mc = stock.finnhub_metrics?.market_cap || stock.market_cap || 0
                    const sparkData = stock.sparkline_weekly || []
                    const consensus = stock.analyst_consensus || {}
                    const earningsSurp = (stock.earnings_surprises || [])[0]
                    const c = pctColor(changePct)

                    return (
                        <div key={i} style={mag7Row}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: S.sm }}>
                                <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0, flex: 1 }}>
                                    <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_bold }}>
                                        {stock.name || ticker}
                                    </span>
                                    <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap }}>
                                        {ticker}
                                    </span>
                                </div>
                                <div style={{ textAlign: "right", flexShrink: 0 }}>
                                    <div style={{ ...MONO, color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi }}>
                                        {fmtUSD(price)}
                                    </div>
                                    <div style={{ ...MONO, color: c, fontSize: T.cap, fontWeight: T.w_bold }}>
                                        {fmtPct(changePct)}
                                    </div>
                                </div>
                            </div>

                            <div style={{ display: "flex", gap: S.sm, alignItems: "center", flexWrap: "wrap" }}>
                                {sparkData.length > 0 && <MiniSparkline data={sparkData} color={c} />}
                                {mc > 0 && <MetricChip label="시총" value={fmtMarketCap(mc)} />}
                                {consensus.buy > 0 && (
                                    <MetricChip
                                        label="B/H/S"
                                        value={`${consensus.buy}/${consensus.hold || 0}/${consensus.sell || 0}`}
                                        color={consensus.buy > (consensus.hold || 0) + (consensus.sell || 0) ? C.success : C.warn}
                                    />
                                )}
                                {consensus.upside_pct != null && consensus.upside_pct !== 0 && (
                                    <MetricChip
                                        label="Upside"
                                        value={fmtPct(consensus.upside_pct)}
                                        color={pctColor(consensus.upside_pct)}
                                    />
                                )}
                                {earningsSurp?.surprise_pct != null && (
                                    <MetricChip
                                        label="Last EPS"
                                        value={fmtPct(earningsSurp.surprise_pct)}
                                        color={pctColor(earningsSurp.surprise_pct)}
                                    />
                                )}
                            </div>
                        </div>
                    )
                })}
            </div>
        </>
    )
}


/* ─────────── Insider · SEC view ─────────── */
function InsiderView({
    usRecs, subTab, setSubTab,
}: {
    usRecs: any[]
    subTab: "insider" | "sec"
    setSubTab: (t: "insider" | "sec") => void
}) {
    const insiderStocks = usRecs.filter((r) => {
        const ins = r.insider_sentiment
        return ins && (ins.positive_count > 0 || ins.negative_count > 0 || ins.net_shares !== 0)
    })
    const secStocks = usRecs.filter((r) => Array.isArray(r.sec_filings) && r.sec_filings.length > 0)
    const allFilings = secStocks
        .flatMap((r) => (r.sec_filings || []).map((f: any) => ({ ...f, stock_name: r.name, ticker: r.ticker })))
        .sort((a, b) => (b.filed_date || "").localeCompare(a.filed_date || ""))
        .slice(0, 30)

    const buyTotal = insiderStocks.reduce((s, r) => s + (r.insider_sentiment?.positive_count || 0), 0)
    const sellTotal = insiderStocks.reduce((s, r) => s + (r.insider_sentiment?.negative_count || 0), 0)

    return (
        <>
            {/* Summary */}
            <div style={summaryRow}>
                <CountBadge label="Buy" count={buyTotal} color={C.success} />
                <CountBadge label="Sell" count={sellTotal} color={C.danger} />
            </div>

            {/* Sub tab */}
            <div style={subTabRow}>
                <SubTabButton
                    label={`내부자 (${insiderStocks.length})`}
                    active={subTab === "insider"}
                    onClick={() => setSubTab("insider")}
                />
                <SubTabButton
                    label={`SEC 공시 (${allFilings.length})`}
                    active={subTab === "sec"}
                    onClick={() => setSubTab("sec")}
                />
            </div>

            <div style={hr} />

            {/* Insider list */}
            {subTab === "insider" && (
                <div style={listWrap}>
                    {insiderStocks.length === 0 ? (
                        <div style={emptyBox}>
                            <span style={{ color: C.textTertiary, fontSize: T.body }}>내부자 거래 데이터 없음</span>
                        </div>
                    ) : (
                        insiderStocks
                            .sort((a, b) => Math.abs(b.insider_sentiment?.net_shares || 0) - Math.abs(a.insider_sentiment?.net_shares || 0))
                            .map((r, i) => {
                                const ins = r.insider_sentiment || {}
                                const mspr = ins.mspr || 0
                                const net = ins.net_shares || 0
                                const sentColor = mspr > 0 ? C.success : mspr < 0 ? C.danger : C.textTertiary
                                const sentLabel = mspr > 0 ? "매수 우세" : mspr < 0 ? "매도 우세" : "중립"

                                return (
                                    <div key={i} style={listRow}>
                                        <div style={{ flex: 1, minWidth: 0 }}>
                                            <div>
                                                <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi }}>
                                                    {r.name}
                                                </span>
                                                <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap, marginLeft: S.xs }}>
                                                    {r.ticker}
                                                </span>
                                            </div>
                                            <div style={{ display: "flex", gap: S.sm, marginTop: 4 }}>
                                                <span style={{ ...MONO, color: C.success, fontSize: T.cap }}>
                                                    Buy {ins.positive_count || 0}
                                                </span>
                                                <span style={{ ...MONO, color: C.danger, fontSize: T.cap }}>
                                                    Sell {ins.negative_count || 0}
                                                </span>
                                                <span style={{ ...MONO, color: C.textSecondary, fontSize: T.cap }}>
                                                    Net {net > 0 ? "+" : ""}{net.toLocaleString()}주
                                                </span>
                                            </div>
                                        </div>
                                        <div style={{ textAlign: "right", flexShrink: 0 }}>
                                            <div style={{ color: sentColor, fontSize: T.cap, fontWeight: T.w_bold }}>
                                                {sentLabel}
                                            </div>
                                            <div style={{ ...MONO, color: C.textTertiary, fontSize: T.cap, marginTop: 2 }}>
                                                MSPR {mspr > 0 ? "+" : ""}{mspr.toFixed(4)}
                                            </div>
                                        </div>
                                    </div>
                                )
                            })
                    )}
                </div>
            )}

            {/* SEC list */}
            {subTab === "sec" && (
                <div style={listWrap}>
                    {allFilings.length === 0 ? (
                        <div style={emptyBox}>
                            <span style={{ color: C.textTertiary, fontSize: T.body }}>SEC 공시 데이터 없음</span>
                        </div>
                    ) : (
                        allFilings.map((f, i) => {
                            const formColor = secFormColor(f.form_type || "")
                            return (
                                <div key={i} style={listRow}>
                                    <div style={{ display: "flex", alignItems: "center", gap: S.md, flex: 1, minWidth: 0 }}>
                                        <span
                                            style={{
                                                background: `${formColor}1F`,
                                                color: formColor,
                                                fontSize: T.cap,
                                                fontWeight: T.w_bold,
                                                letterSpacing: "0.05em",
                                                padding: `2px ${S.sm}px`,
                                                borderRadius: R.sm,
                                                fontFamily: FONT,
                                                whiteSpace: "nowrap",
                                            }}
                                        >
                                            {f.form_type || "Filing"}
                                        </span>
                                        <div style={{ minWidth: 0, flex: 1 }}>
                                            <div
                                                style={{
                                                    color: C.textPrimary, fontSize: T.cap, fontWeight: T.w_semi,
                                                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                                                }}
                                            >
                                                {f.stock_name}{" "}
                                                <span style={{ ...MONO, color: C.textTertiary }}>{f.ticker}</span>
                                            </div>
                                            {f.description && (
                                                <div
                                                    style={{
                                                        color: C.textTertiary, fontSize: T.cap,
                                                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                                                    }}
                                                >
                                                    {f.description}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                    <span
                                        style={{
                                            ...MONO, color: C.textTertiary, fontSize: T.cap,
                                            whiteSpace: "nowrap", flexShrink: 0,
                                        }}
                                    >
                                        {f.filed_date || ""}
                                    </span>
                                </div>
                            )
                        })
                    )}
                </div>
            )}
        </>
    )
}


/* ─────────── Analyst Consensus view ─────────── */
function AnalystView({
    usRecs, sort, setSort,
}: {
    usRecs: any[]
    sort: AnalystSort
    setSort: (s: AnalystSort) => void
}) {
    const withConsensus = usRecs.filter((r) => {
        const c = r.analyst_consensus
        return c && (c.buy > 0 || c.hold > 0 || c.sell > 0)
    })

    const sorted = [...withConsensus].sort((a, b) => {
        if (sort === "upside") return (b.analyst_consensus?.upside_pct || 0) - (a.analyst_consensus?.upside_pct || 0)
        if (sort === "buy_ratio") {
            const ratioA = a.analyst_consensus.buy / ((a.analyst_consensus.buy + a.analyst_consensus.hold + a.analyst_consensus.sell) || 1)
            const ratioB = b.analyst_consensus.buy / ((b.analyst_consensus.buy + b.analyst_consensus.hold + b.analyst_consensus.sell) || 1)
            return ratioB - ratioA
        }
        return (a.name || "").localeCompare(b.name || "")
    })

    const strongBuys = withConsensus.filter((r) => {
        const c = r.analyst_consensus
        return c.buy > (c.hold || 0) + (c.sell || 0) && (c.upside_pct || 0) > 10
    }).length

    return (
        <>
            {/* Summary */}
            {strongBuys > 0 && (
                <div style={summaryRow}>
                    <CountBadge label="Strong Buy" count={strongBuys} color={C.success} />
                </div>
            )}

            {/* Sort row */}
            <div style={subTabRow}>
                <SubTabButton label="업사이드순" active={sort === "upside"} onClick={() => setSort("upside")} />
                <SubTabButton label="Buy비율순" active={sort === "buy_ratio"} onClick={() => setSort("buy_ratio")} />
                <SubTabButton label="이름순" active={sort === "name"} onClick={() => setSort("name")} />
            </div>

            <div style={hr} />

            {/* List */}
            <div style={listWrap}>
                {sorted.length === 0 ? (
                    <div style={emptyBox}>
                        <span style={{ color: C.textTertiary, fontSize: T.body }}>컨센서스 데이터 없음</span>
                    </div>
                ) : (
                    sorted.map((r, i) => {
                        const c = r.analyst_consensus
                        const total = c.buy + (c.hold || 0) + (c.sell || 0)
                        const buyRatio = total > 0 ? ((c.buy / total) * 100).toFixed(0) : "—"
                        const upside = c.upside_pct || 0
                        return (
                            <div key={i} style={listRow}>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ display: "flex", alignItems: "baseline", gap: S.xs, marginBottom: S.xs }}>
                                        <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi }}>
                                            {r.name}
                                        </span>
                                        <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap }}>
                                            {r.ticker}
                                        </span>
                                        <span style={{ ...MONO, color: C.textSecondary, fontSize: T.cap }}>
                                            {fmtUSD(r.price)}
                                        </span>
                                    </div>

                                    <div style={{ display: "flex", gap: S.lg, alignItems: "center", flexWrap: "wrap" }}>
                                        {/* Rating bar */}
                                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                            <span style={{ color: C.textTertiary, fontSize: 9, fontWeight: T.w_med }}>RATING</span>
                                            <RatingBar buy={c.buy} hold={c.hold || 0} sell={c.sell || 0} />
                                            <div style={{ display: "flex", gap: S.xs, marginTop: 2 }}>
                                                <span style={{ ...MONO, color: C.success, fontSize: 10, fontWeight: T.w_semi }}>B {c.buy}</span>
                                                <span style={{ ...MONO, color: C.warn, fontSize: 10, fontWeight: T.w_semi }}>H {c.hold || 0}</span>
                                                <span style={{ ...MONO, color: C.danger, fontSize: 10, fontWeight: T.w_semi }}>S {c.sell || 0}</span>
                                                <span style={{ ...MONO, color: C.textSecondary, fontSize: 10 }}>({buyRatio}%)</span>
                                            </div>
                                        </div>

                                        {/* Target */}
                                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                            <span style={{ color: C.textTertiary, fontSize: 9, fontWeight: T.w_med }}>목표가</span>
                                            <span style={{ ...MONO, color: C.textPrimary, fontSize: T.cap, fontWeight: T.w_semi }}>
                                                ${c.target_mean?.toLocaleString("en-US", { maximumFractionDigits: 0 }) || "—"}
                                            </span>
                                            {(c.target_low || c.target_high) && (
                                                <span style={{ ...MONO, color: C.textTertiary, fontSize: 10 }}>
                                                    {c.target_low ? `$${c.target_low.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : ""}
                                                    {c.target_low && c.target_high ? " ~ " : ""}
                                                    {c.target_high ? `$${c.target_high.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : ""}
                                                </span>
                                            )}
                                        </div>

                                        {/* Upside */}
                                        <div style={{ display: "flex", flexDirection: "column", gap: 2, marginLeft: "auto" }}>
                                            <span style={{ color: C.textTertiary, fontSize: 9, fontWeight: T.w_med }}>UPSIDE</span>
                                            <UpsideArrow pct={upside} />
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )
                    })
                )}
            </div>
        </>
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

function SubTabButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
    return (
        <button
            onClick={onClick}
            style={{
                background: "transparent",
                border: "none",
                borderBottom: `2px solid ${active ? C.accent : "transparent"}`,
                color: active ? C.accent : C.textTertiary,
                padding: `${S.sm}px ${S.md}px`,
                fontSize: T.cap,
                fontWeight: T.w_semi,
                fontFamily: FONT,
                cursor: "pointer",
                transition: X.fast,
            }}
        >
            {label}
        </button>
    )
}

function MetricChip({ label, value, color = C.textPrimary }: { label: string; value: string; color?: string }) {
    return (
        <div
            style={{
                background: C.bgElevated,
                border: `1px solid ${C.border}`,
                borderRadius: R.sm,
                padding: `2px ${S.sm}px`,
                display: "flex", flexDirection: "column", gap: 1,
                minWidth: 0,
            }}
        >
            <span
                style={{
                    color: C.textTertiary,
                    fontSize: 9,
                    fontWeight: T.w_med,
                    letterSpacing: "0.03em",
                    fontFamily: FONT,
                }}
            >
                {label}
            </span>
            <span style={{ ...MONO, color, fontSize: T.cap, fontWeight: T.w_semi }}>
                {value}
            </span>
        </div>
    )
}

function CountBadge({ label, count, color }: { label: string; count: number; color: string }) {
    return (
        <span
            style={{
                display: "inline-flex", alignItems: "center", gap: S.xs,
                padding: `${S.xs}px ${S.md}px`,
                background: `${color}1A`,
                border: `1px solid ${color}33`,
                borderRadius: R.sm,
                fontSize: T.cap, fontWeight: T.w_semi,
                color, fontFamily: FONT,
            }}
        >
            <span>{label}</span>
            <span style={{ ...MONO, fontWeight: T.w_bold }}>{count}건</span>
        </span>
    )
}

function RatingBar({ buy, hold, sell }: { buy: number; hold: number; sell: number }) {
    const total = buy + hold + sell || 1
    const bPct = (buy / total) * 100
    const hPct = (hold / total) * 100
    return (
        <div style={{ display: "flex", height: 4, borderRadius: 2, overflow: "hidden", width: 80 }}>
            <div style={{ width: `${bPct}%`, background: C.success }} />
            <div style={{ width: `${hPct}%`, background: C.warn }} />
            <div style={{ flex: 1, background: C.danger }} />
        </div>
    )
}

function UpsideArrow({ pct }: { pct: number }) {
    const abs = Math.abs(pct)
    const barW = Math.min(abs / 60 * 100, 100)
    const color = pct > 20 ? C.success : pct > 0 ? C.success : pct > -10 ? C.warn : C.danger
    return (
        <div style={{ display: "flex", alignItems: "center", gap: S.xs, width: 100 }}>
            <div style={{ flex: 1, height: 3, background: C.bgElevated, borderRadius: 2, position: "relative" }}>
                <div
                    style={{
                        height: "100%", width: `${barW}%`, background: color, borderRadius: 2,
                        position: "absolute",
                        left: pct >= 0 ? "50%" : undefined,
                        right: pct < 0 ? "50%" : undefined,
                    }}
                />
                <div
                    style={{
                        position: "absolute", left: "50%", top: -2,
                        height: 8, width: 1, background: C.textDisabled,
                    }}
                />
            </div>
            <span style={{ ...MONO, color, fontSize: T.cap, fontWeight: T.w_bold, minWidth: 38, textAlign: "right" }}>
                {pct > 0 ? "+" : ""}{pct.toFixed(0)}%
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
    display: "flex", gap: S.sm, flexWrap: "wrap",
}

const subTabRow: CSSProperties = {
    display: "flex", gap: 0, borderBottom: `1px solid ${C.border}`,
}

const summaryRow: CSSProperties = {
    display: "flex", gap: S.lg, flexWrap: "wrap", alignItems: "center",
}

const summaryItem: CSSProperties = {
    display: "flex", flexDirection: "column", gap: 2,
}

const summaryCap: CSSProperties = {
    color: C.textTertiary,
    fontSize: T.cap, fontWeight: T.w_med,
    letterSpacing: "0.05em", textTransform: "uppercase",
}

const hr: CSSProperties = {
    height: 1, background: C.border, margin: 0,
}

const listWrap: CSSProperties = {
    display: "flex", flexDirection: "column",
    maxHeight: 480, overflowY: "auto",
}

const mag7Row: CSSProperties = {
    padding: `${S.md}px 0`,
    borderBottom: `1px solid ${C.border}`,
    display: "flex", flexDirection: "column", gap: S.sm,
}

const listRow: CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "flex-start",
    padding: `${S.md}px 0`,
    borderBottom: `1px solid ${C.border}`,
    gap: S.md,
}

const emptyBox: CSSProperties = {
    padding: `${S.xxl}px 0`, textAlign: "center",
}

const loadingBox: CSSProperties = {
    minHeight: 200,
    display: "flex", alignItems: "center", justifyContent: "center",
}


/* ─────────── Framer Property Controls ─────────── */

USDetailHub.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
    recUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/recommendations.json",
}

addPropertyControls(USDetailHub, {
    dataUrl: {
        type: ControlType.String,
        title: "Portfolio URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
    },
    recUrl: {
        type: ControlType.String,
        title: "Recommendations URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/recommendations.json",
    },
})
