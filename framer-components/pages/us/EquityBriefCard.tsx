import { addPropertyControls, ControlType } from "framer"
import { useEffect, useMemo, useState, type CSSProperties } from "react"

/**
 * EquityBriefCard — Perplexity Sonar 기반 institutional equity research brief.
 *
 * 출처: data/equity_research/<TICKER>.json (gh-pages raw URL fetch).
 *      api/intelligence/equity_research_brief.py 가 주 1회 cron 생성 (월요일 KST 06:00).
 *
 * 분석가 consensus = yfinance (실측). thesis / catalysts / sec_filings / risks = Sonar pro.
 * VERITY 관점 = 자체 trail (Brain v5 + Lynch + VAMS) — LLM 가입자 못 가짐 (RULE 6 보강).
 *
 * 디자인: USDetailHub 정합 — 모던 심플 6원칙 (No card-in-card / flat / mono / 토큰 색 / emoji 0).
 *      VERITY 관점만 RULE 6 차별점 prominence 위해 미세 accent borderLeft.
 *      feedback_no_hardcode_position / feedback_framer_hooks_top_level / in_component_interactivity.
 */

/* ◆ DESIGN TOKENS — VERITY 마스터 (USDetailHub 정합) ◆ */
const C = {
    bgPage: "#0a0a0a", bgCard: "#141414", bgElevated: "#1a1a1a", bgInput: "transparent",
    border: "rgba(255,255,255,0.06)", borderStrong: "rgba(255,255,255,0.10)", borderHover: "#7fffa0",
    textPrimary: "#ffffff", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#7fffa0", accentSoft: "rgba(127, 255, 160,0.12)",
    strongBuy: "#22C55E", buy: "#2DD4BF", hold: "#FFD600", avoid: "#F59E0B", strongAvoid: "#EF4444",
    up: "#22C55E", down: "#EF4444",
    info: "#5BA9FF", success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }

/* ◆ TYPES (brief json schema) ◆ */
interface AnalystConsensus {
    price_target_avg?: number | null
    price_target_high?: number | null
    price_target_low?: number | null
    price_target_median?: number | null
    current_price?: number | null
    n_analysts?: number | null
    recommendation_key?: string | null
    recommendation_mean?: number | null
    eps_fy1_estimate?: number | null
    pe_forward?: number | null
    _source?: string
}
interface Catalyst { date: string; event: string }
interface SecFiling { date: string; form: string; topic: string }
interface VerityTrail {
    _source?: string
    _error?: string
    brain_score?: number | null
    brain_score_raw?: number | null
    grade?: string | null
    grade_label?: string | null
    grade_confidence?: string | null
    fact_score?: number | null
    sentiment_score?: number | null
    vci_value?: number | null
    vci_signal?: string | null
    vci_label?: string | null
    red_flags_auto_avoid?: string[]
    red_flags_downgrade?: string[]
    has_critical?: boolean
    lynch_class?: string | null
    lynch_label?: string | null
    lynch_summary?: string | null
    recommended_position_pct?: number | null
    position_rationale?: string | null
    reasoning?: string | null
    vams_holding_status?: string
    vams_holding_qty?: number | null
    vams_holding_entry_price?: number | null
    vams_holding_pnl_pct?: number | null
    vams_holding_days?: number | null
    universe_stage?: string
    trail_collected_at?: string
}
interface Brief {
    ticker: string
    company_summary?: string
    thesis?: string[]
    recent_catalysts?: Catalyst[]
    earnings_highlights?: any
    sec_filings_recent?: SecFiling[]
    analyst_consensus?: AnalystConsensus
    risks?: string[]
    brief_verdict?: string
    verity_trail?: VerityTrail
    generated_at?: string
    cost_usd?: number
}

/* ◆ HELPERS ◆ */
function verdictColor(v?: string): string {
    switch ((v || "").toUpperCase()) {
        case "STRONG_BUY": return C.strongBuy
        case "BUY": return C.buy
        case "HOLD": return C.hold
        case "AVOID": return C.avoid
        case "STRONG_AVOID": return C.strongAvoid
        default: return C.textTertiary
    }
}
function fmtUSD(n?: number | null, digits = 2): string {
    if (n == null || isNaN(n as number)) return "—"
    return `$${(n as number).toFixed(digits)}`
}
function gapPct(curr?: number | null, target?: number | null): string {
    if (curr == null || target == null || curr === 0) return ""
    const pct = ((target - curr) / curr) * 100
    return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`
}
function relTime(iso?: string): string {
    if (!iso) return ""
    try {
        const t = new Date(iso).getTime()
        const days = Math.floor((Date.now() - t) / 86400000)
        if (days === 0) return "오늘"
        if (days === 1) return "어제"
        if (days < 7) return `${days}일 전`
        if (days < 30) return `${Math.floor(days / 7)}주 전`
        return `${Math.floor(days / 30)}개월 전`
    } catch { return iso.slice(0, 10) }
}

/* ◆ MetricChip (USDetailHub 정합 — flat, no bg) ◆ */
function MetricChip({ label, value, color = C.textPrimary, title }: {
    label: string; value: string; color?: string; title?: string
}) {
    return (
        <div title={title} style={{ display: "flex", flexDirection: "column", gap: 1,
            minWidth: 0, padding: `2px ${S.sm}px 2px 0` }}>
            <span style={{ color: C.textTertiary, fontSize: 9, fontWeight: T.w_med,
                letterSpacing: 0.5, fontFamily: FONT }}>{label}</span>
            <span style={{ ...MONO, color, fontSize: T.cap, fontWeight: T.w_semi }}>{value}</span>
        </div>
    )
}

/* ◆ Price target gap bar ◆ */
function PriceTargetBar({ low, current, target, high }: {
    low?: number | null; current?: number | null; target?: number | null; high?: number | null
}) {
    if (low == null || high == null || current == null || target == null || high <= low) return null
    const range = high - low
    const currPct = Math.max(0, Math.min(100, ((current - low) / range) * 100))
    const targetPct = Math.max(0, Math.min(100, ((target - low) / range) * 100))
    return (
        <div style={{ position: "relative", height: 24, marginTop: S.xs, maxWidth: 280 }}>
            <div style={{ position: "absolute", left: 0, right: 0, top: 10, height: 4,
                background: C.bgElevated, borderRadius: 2 }} />
            <div style={{ position: "absolute", left: `${currPct}%`, top: 6,
                width: 12, height: 12, borderRadius: "50%", background: C.textPrimary,
                transform: "translateX(-50%)", border: `2px solid ${C.bgPage}` }}
                title={`현재가 ${fmtUSD(current)}`} />
            <div style={{ position: "absolute", left: `${targetPct}%`, top: 4,
                width: 2, height: 16, background: C.accent, transform: "translateX(-50%)" }}
                title={`목표가 ${fmtUSD(target)}`} />
            <span style={{ position: "absolute", left: 0, top: 18, fontSize: T.cap - 2,
                color: C.textTertiary, ...MONO }}>{fmtUSD(low)}</span>
            <span style={{ position: "absolute", right: 0, top: 18, fontSize: T.cap - 2,
                color: C.textTertiary, ...MONO }}>{fmtUSD(high)}</span>
        </div>
    )
}

/* ◆ Verdict badge ◆ */
function VerdictBadge({ verdict }: { verdict?: string }) {
    const color = verdictColor(verdict)
    const label = (verdict || "—").replace("_", " ")
    return (
        <span style={{ display: "inline-flex", alignItems: "center",
            padding: `2px ${S.sm}px`, background: color + "1A", color,
            borderRadius: R.sm, fontSize: T.cap, fontWeight: T.w_bold,
            fontFamily: FONT, letterSpacing: 0.5, lineHeight: 1.4 }}>{label}</span>
    )
}

/* ◆ ticker selector (in-component) ◆ */
function TickerSelector({ tickers, value, onChange }: {
    tickers: string[]; value: string; onChange: (t: string) => void
}) {
    return (
        <select value={value} onChange={(e) => onChange(e.target.value)}
            style={{ background: C.bgInput, color: C.textPrimary,
                border: `1px solid ${C.borderStrong}`, borderRadius: R.sm,
                padding: `${S.xs}px ${S.sm}px`, fontSize: T.cap, fontWeight: T.w_med,
                fontFamily: FONT, outline: "none", cursor: "pointer", ...MONO }}>
            {tickers.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
    )
}

/* ◆ MAIN ◆ */
interface Props {
    rawBaseUrl: string
    defaultTicker: string
    tickerList: string
}

function EquityBriefCard({ rawBaseUrl, defaultTicker, tickerList }: Props) {
    const tickers = useMemo(
        () => tickerList.split(",").map((t) => t.trim().toUpperCase()).filter(Boolean),
        [tickerList]
    )
    const [ticker, setTicker] = useState(defaultTicker.toUpperCase() || (tickers[0] || "CRM"))
    const [brief, setBrief] = useState<Brief | null>(null)
    const [loading, setLoading] = useState(false)
    const [err, setErr] = useState<string | null>(null)

    useEffect(() => {
        if (!ticker) return
        const ctrl = new AbortController()
        setLoading(true); setErr(null); setBrief(null)
        const url = `${rawBaseUrl.replace(/\/$/, "")}/equity_research/${ticker}.json`
        fetch(url, { signal: ctrl.signal })
            .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
            .then((j: Brief) => { setBrief(j); setLoading(false) })
            .catch((e) => { if (e.name !== "AbortError") { setErr(e.message); setLoading(false) } })
        return () => ctrl.abort()
    }, [ticker, rawBaseUrl])

    const ac = brief?.analyst_consensus || {}
    const gap = gapPct(ac.current_price ?? undefined, ac.price_target_avg ?? undefined)
    const recMean = ac.recommendation_mean
    const vt = brief?.verity_trail
    const showTrail = vt && !vt._error && vt.brain_score != null

    return (
        <div style={shell}>
            {/* Header */}
            <div style={headerRow}>
                <div style={headerLeft}>
                    <span style={titleStyle}>종목 분석 브리프</span>
                    <span style={metaStyle}>Perplexity Sonar · 기관 리서치</span>
                </div>
                <TickerSelector tickers={tickers.length ? tickers : [ticker]}
                    value={ticker} onChange={setTicker} />
            </div>

            <div style={hr} />

            {/* Ticker headline */}
            <div style={{ display: "flex", alignItems: "center", gap: S.md, flexWrap: "wrap" }}>
                <span style={{ ...MONO, fontSize: T.h2, fontWeight: T.w_bold, color: C.textPrimary }}>{ticker}</span>
                <VerdictBadge verdict={brief?.brief_verdict} />
                <span style={{ flex: 1 }} />
                {loading && <span style={{ fontSize: T.cap, color: C.info, ...MONO }}>로딩 중</span>}
                <span style={{ fontSize: T.cap, color: C.textTertiary }}>{relTime(brief?.generated_at)}</span>
            </div>

            {err && (
                <span style={{ fontSize: T.cap, color: C.danger }}>
                    브리프 로딩 실패: {err} (주 1회 cron 미실행 ticker 가능)
                </span>
            )}

            {brief && (
                <>
                    {/* Analyst consensus — flat */}
                    <div style={{ display: "flex", flexDirection: "column", gap: S.sm }}>
                        <span style={summaryCap}>애널리스트 컨센서스</span>
                        <div style={summaryRow}>
                            <div style={summaryItem}>
                                <span style={summaryCap}>현재가</span>
                                <span style={{ ...MONO, fontSize: T.title, fontWeight: T.w_bold }}>
                                    {fmtUSD(ac.current_price)}
                                </span>
                            </div>
                            <div style={summaryItem}>
                                <span style={summaryCap}>목표가</span>
                                <span style={{ ...MONO, fontSize: T.title, fontWeight: T.w_semi, color: C.textSecondary }}>
                                    {fmtUSD(ac.price_target_avg)}
                                    {gap && (
                                        <span style={{ marginLeft: S.sm, fontSize: T.cap,
                                            color: gap.startsWith("+") ? C.success : C.danger }}>{gap}</span>
                                    )}
                                </span>
                            </div>
                            {recMean != null && (
                                <div style={summaryItem}>
                                    <span style={summaryCap}>의견</span>
                                    <span style={{ ...MONO, fontSize: T.body, color: C.textSecondary }}>
                                        {recMean.toFixed(2)} ({ac.recommendation_key || "—"}, n={ac.n_analysts ?? "—"})
                                    </span>
                                </div>
                            )}
                        </div>
                        <PriceTargetBar low={ac.price_target_low} current={ac.current_price}
                            target={ac.price_target_avg} high={ac.price_target_high} />
                        {(ac.eps_fy1_estimate != null || ac.pe_forward != null) && (
                            <div style={{ display: "flex", gap: S.lg, flexWrap: "wrap" }}>
                                {ac.eps_fy1_estimate != null && (
                                    <MetricChip label="선행 EPS" value={fmtUSD(ac.eps_fy1_estimate)} />
                                )}
                                {ac.pe_forward != null && (
                                    <MetricChip label="선행 P/E" value={`${ac.pe_forward.toFixed(1)}x`} />
                                )}
                            </div>
                        )}
                    </div>

                    {/* VERITY 관점 — RULE 6 차별점 (Brain v5 + Lynch + VAMS). 미세 accent 강조. */}
                    {showTrail && (
                        <>
                            <div style={hr} />
                            <div style={{ display: "flex", flexDirection: "column", gap: S.sm }}>
                                <div style={{ display: "flex", alignItems: "baseline", gap: S.md, flexWrap: "wrap" }}>
                                    <span style={{ fontSize: T.cap, color: C.accent, textTransform: "uppercase",
                                        letterSpacing: 0.5, fontWeight: T.w_bold }}>
                                        VERITY 관점
                                        <span style={{ color: C.warn, fontSize: T.cap - 2, marginLeft: 4,
                                            textTransform: "none", letterSpacing: 0, fontWeight: T.w_reg }}>· 가설 (N=14)</span>
                                    </span>
                                    {vt!.grade && (
                                        <span style={{ ...MONO, fontSize: T.body, fontWeight: T.w_bold,
                                            color: verdictColor(vt!.grade), letterSpacing: 0.5 }}>
                                            {vt!.grade.replace("_", " ")}
                                            {vt!.grade_label && (
                                                <span style={{ color: C.textSecondary, fontSize: T.cap,
                                                    fontWeight: T.w_reg, marginLeft: S.xs }}>({vt!.grade_label})</span>
                                            )}
                                        </span>
                                    )}
                                    {vt!.brain_score != null && (
                                        <span style={{ ...MONO, fontSize: T.sub, fontWeight: T.w_bold, color: C.textPrimary }}
                                            title="Brain v5 자체 산식 (가중치 7:3 + 등급 75-60-45-30)">{vt!.brain_score}</span>
                                    )}
                                    {vt!.grade_confidence && (
                                        <span style={{ ...MONO, fontSize: T.cap - 1, color: C.textTertiary }}>{vt!.grade_confidence}</span>
                                    )}
                                    <span style={{ flex: 1 }} />
                                    {vt!.vams_holding_status === "holding" && (
                                        <span style={{ ...MONO, padding: `2px ${S.sm}px`, background: C.success + "1A",
                                            color: C.success, fontSize: T.cap, fontWeight: T.w_bold, borderRadius: R.pill }}
                                            title={`VAMS 보유 — entry $${vt!.vams_holding_entry_price}, ${vt!.vams_holding_days}일`}>
                                            VAMS 보유
                                            {vt!.vams_holding_pnl_pct != null && (
                                                <span style={{ marginLeft: S.xs }}>
                                                    {vt!.vams_holding_pnl_pct >= 0 ? "+" : ""}{vt!.vams_holding_pnl_pct.toFixed(1)}%
                                                </span>
                                            )}
                                        </span>
                                    )}
                                </div>

                                {/* sub-scores — flat chips */}
                                <div style={{ display: "flex", gap: S.lg, flexWrap: "wrap" }}>
                                    {vt!.fact_score != null && (
                                        <MetricChip label="팩트" value={`${vt!.fact_score}`}
                                            title="multi_factor + consensus + 12 지표" />
                                    )}
                                    {vt!.sentiment_score != null && (
                                        <MetricChip label="심리" value={`${vt!.sentiment_score}`}
                                            title="13-source hard-wire sentiment" />
                                    )}
                                    {vt!.vci_value != null && (
                                        <MetricChip label="VCI" value={`${vt!.vci_value > 0 ? "+" : ""}${vt!.vci_value} ${vt!.vci_signal || ""}`}
                                            color={vt!.vci_signal === "ALIGNED" ? C.success : C.warn}
                                            title={vt!.vci_label || "팩트-심리 정렬 지수"} />
                                    )}
                                    {vt!.lynch_class && (
                                        <MetricChip label="Lynch" value={vt!.lynch_label || vt!.lynch_class}
                                            color={C.accent} title={vt!.lynch_summary || ""} />
                                    )}
                                    {vt!.recommended_position_pct != null && (
                                        <MetricChip label="포지션" value={`${vt!.recommended_position_pct.toFixed(1)}%`}
                                            color={vt!.recommended_position_pct > 0 ? C.accent : C.textTertiary}
                                            title={vt!.position_rationale || ""} />
                                    )}
                                </div>

                                {/* Red flags (emoji 0 — 색 마커) */}
                                {vt!.red_flags_auto_avoid && vt!.red_flags_auto_avoid.length > 0 && (
                                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                        {vt!.red_flags_auto_avoid.slice(0, 2).map((rf, i) => (
                                            <span key={`avoid-${i}`} style={{ fontSize: T.cap, color: C.danger, fontWeight: T.w_semi }}>
                                                ● {rf}
                                            </span>
                                        ))}
                                        {vt!.red_flags_downgrade?.slice(0, 1).map((rf, i) => (
                                            <span key={`down-${i}`} style={{ fontSize: T.cap, color: C.warn }}>· {rf}</span>
                                        ))}
                                    </div>
                                )}

                                {vt!.reasoning && (
                                    <p style={{ margin: 0, fontSize: T.cap, color: C.textSecondary,
                                        lineHeight: 1.45, fontStyle: "italic" }}
                                        title="VERITY Brain v5 룰 기반 합성 (LLM call 없음)">
                                        {vt!.reasoning.slice(0, 280)}{vt!.reasoning.length > 280 && "…"}
                                    </p>
                                )}
                            </div>
                        </>
                    )}

                    <div style={hr} />

                    {/* Thesis */}
                    {brief.thesis && brief.thesis.length > 0 && (
                        <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                            <span style={summaryCap}>투자 포인트</span>
                            {brief.thesis.slice(0, 2).map((t, i) => (
                                <p key={i} style={{ margin: 0, fontSize: T.body, color: C.textSecondary, lineHeight: 1.5 }}>· {t}</p>
                            ))}
                        </div>
                    )}

                    {/* Catalyst */}
                    {brief.recent_catalysts && brief.recent_catalysts[0] && (
                        <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                            <span style={summaryCap}>최근 Catalyst</span>
                            <p style={{ margin: 0, fontSize: T.body, color: C.textSecondary, lineHeight: 1.5 }}>
                                <span style={{ ...MONO, color: C.accent, marginRight: S.xs }}>{brief.recent_catalysts[0].date}</span>
                                {brief.recent_catalysts[0].event}
                            </p>
                        </div>
                    )}

                    {/* Risk */}
                    {brief.risks && brief.risks[0] && (
                        <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                            <span style={{ ...summaryCap, color: C.danger }}>주요 Risk</span>
                            <p style={{ margin: 0, fontSize: T.body, color: C.textSecondary, lineHeight: 1.5 }}>· {brief.risks[0]}</p>
                        </div>
                    )}

                    {/* Footer */}
                    <div style={{ display: "flex", gap: S.md, alignItems: "center", flexWrap: "wrap",
                        fontSize: T.cap - 1, color: C.textTertiary, ...MONO,
                        paddingTop: S.sm, borderTop: `1px solid ${C.border}` }}>
                        <span>생성 {brief.generated_at?.slice(0, 10) || "—"}</span>
                        {brief.cost_usd != null && <span>· ${brief.cost_usd?.toFixed(4)}</span>}
                        {brief.sec_filings_recent && <span>· SEC 공시 {brief.sec_filings_recent.length}건</span>}
                    </div>
                </>
            )}
        </div>
    )
}

/* ◆ STYLES (USDetailHub 정합) ◆ */
const shell: CSSProperties = {
    width: "100%", boxSizing: "border-box",
    fontFamily: FONT, color: C.textPrimary,
    background: C.bgPage, borderRadius: 8, padding: S.xxl,
    display: "flex", flexDirection: "column", gap: S.lg, minWidth: 320,
}
const headerRow: CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center", gap: S.sm,
}
const headerLeft: CSSProperties = { display: "flex", flexDirection: "column", gap: 2 }
const titleStyle: CSSProperties = {
    fontSize: T.h2, fontWeight: T.w_bold, color: C.textPrimary, letterSpacing: -0.5,
}
const metaStyle: CSSProperties = { fontSize: T.cap, color: C.textTertiary, fontWeight: T.w_med }
const hr: CSSProperties = { height: 1, background: C.border, margin: 0 }
const summaryRow: CSSProperties = {
    display: "flex", gap: S.xxl, flexWrap: "wrap", alignItems: "center",
}
const summaryItem: CSSProperties = { display: "flex", flexDirection: "column", gap: S.xs }
const summaryCap: CSSProperties = {
    color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med,
    letterSpacing: 0.5, textTransform: "uppercase",
}

addPropertyControls(EquityBriefCard, {
    rawBaseUrl: {
        type: ControlType.String,
        title: "Raw Base URL",
        defaultValue: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com",
    },
    defaultTicker: {
        type: ControlType.String,
        title: "Default Ticker",
        defaultValue: "CRM",
    },
    tickerList: {
        type: ControlType.String,
        title: "US Tickers",
        defaultValue: "CRM,JPM,ADBE,MSFT,JNJ,BAC,DIS,SOFI,QCOM,META,BRK-B,TMO,PG,XOM,CSCO",
        description: "comma-separated US15. component 내부 selector",
    },
})

export default EquityBriefCard
