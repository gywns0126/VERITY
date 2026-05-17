import { addPropertyControls, ControlType } from "framer"
import { useEffect, useMemo, useState, type CSSProperties } from "react"

/**
 * EquityBriefCard — Perplexity Sonar 기반 institutional equity research brief.
 *
 * 출처: data/equity_research/<TICKER>.json (gh-pages raw URL fetch).
 *      api/intelligence/equity_research_brief.py 가 주 1회 cron 생성 (월요일 KST 06:00).
 *
 * 분석가 consensus = yfinance (실측, hallucination 0).
 * thesis / catalysts / sec_filings / risks = Sonar pro (SEC + reputable media).
 *
 * VERITY 톤 정합 (USDetailHub 패턴) + 펜타그램 4 원칙 + mini viz 보존.
 *
 * In-component interactivity: ticker dropdown (feedback_in_component_interactivity).
 */

/* ◆ DESIGN TOKENS — VERITY 마스터 ◆ */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B",
    border: "#23242C", borderStrong: "#34353D",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    strongBuy: "#22C55E", buy: "#B5FF19", hold: "#FFD600", avoid: "#F59E0B", strongAvoid: "#EF4444",
    up: "#F04452", down: "#3182F6",
    info: "#5BA9FF", success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const T = { cap: 12, body: 14, sub: 16, title: 18, h2: 22,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700 }
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24 }
const R = { sm: 6, md: 10, lg: 14 }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Menlo', monospace"
const MONO: CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
const MOTION: CSSProperties = { transition: "all 200ms ease" }


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
// 2026-05-17 빅브라더 정합 — VERITY 자체 trail (Brain v5 + Lynch + VAMS). LLM 가입자 못 가짐.
// equity_research_brief.py::fetch_verity_trail() 산출. UI 의 "VERITY 관점" 섹션 source.
interface VerityTrail {
    _source?: string
    _error?: string
    brain_score?: number | null
    brain_score_raw?: number | null
    grade?: string | null            // STRONG_BUY / BUY / HOLD / WATCH / AVOID
    grade_label?: string | null      // 한글 라벨
    grade_confidence?: string | null // firm / weak
    fact_score?: number | null
    sentiment_score?: number | null
    vci_value?: number | null
    vci_signal?: string | null       // ALIGNED / DIVERGE
    vci_label?: string | null
    red_flags_auto_avoid?: string[]
    red_flags_downgrade?: string[]
    has_critical?: boolean
    lynch_class?: string | null      // STALWART / FAST_GROWER / SLOW_GROWER / ASSET_PLAY / TURNAROUND / CYCLICAL
    lynch_label?: string | null
    lynch_summary?: string | null
    recommended_position_pct?: number | null
    position_rationale?: string | null
    reasoning?: string | null
    vams_holding_status?: string     // holding / not_held
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
    verity_trail?: VerityTrail  // 2026-05-17 추가
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
function fmtPct(curr?: number | null, target?: number | null): string {
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


/* ◆ MINI VIZ — Price target gap bar ◆ */
function PriceTargetBar({ low, current, target, high }: {
    low?: number | null; current?: number | null; target?: number | null; high?: number | null
}) {
    if (low == null || high == null || current == null || target == null || high <= low) return null
    const range = high - low
    const currPct = Math.max(0, Math.min(100, ((current - low) / range) * 100))
    const targetPct = Math.max(0, Math.min(100, ((target - low) / range) * 100))
    return (
        <div style={{ position: "relative", height: 24, marginTop: S.xs }}>
            <div style={{
                position: "absolute", left: 0, right: 0, top: 10, height: 4,
                background: C.bgElevated, borderRadius: 2,
            }} />
            {/* Current price marker */}
            <div style={{
                position: "absolute", left: `${currPct}%`, top: 6,
                width: 12, height: 12, borderRadius: "50%",
                background: C.textPrimary, transform: "translateX(-50%)",
                border: `2px solid ${C.bgCard}`,
            }} title={`Current ${fmtUSD(current)}`} />
            {/* Target avg marker */}
            <div style={{
                position: "absolute", left: `${targetPct}%`, top: 4,
                width: 2, height: 16, background: C.accent,
                transform: "translateX(-50%)",
            }} title={`Target ${fmtUSD(target)}`} />
            <span style={{
                position: "absolute", left: 0, top: 18,
                fontSize: T.cap - 2, color: C.textTertiary, ...MONO,
            }}>{fmtUSD(low)}</span>
            <span style={{
                position: "absolute", right: 0, top: 18,
                fontSize: T.cap - 2, color: C.textTertiary, ...MONO,
            }}>{fmtUSD(high)}</span>
        </div>
    )
}


/* ◆ INTERNAL ◆ */
function VerdictBadge({ verdict }: { verdict?: string }) {
    const color = verdictColor(verdict)
    const label = (verdict || "—").replace("_", " ")
    return (
        <span style={{
            display: "inline-flex", alignItems: "center",
            padding: `${S.xs}px ${S.sm}px`,
            background: color + "1A", color,
            border: `1px solid ${color}`, borderRadius: R.sm,
            fontSize: T.cap, fontWeight: T.w_bold,
            fontFamily: FONT, letterSpacing: 0.5, lineHeight: 1,
        }}>{label}</span>
    )
}

function TickerSelector({ tickers, value, onChange }: {
    tickers: string[]; value: string; onChange: (t: string) => void
}) {
    return (
        <select
            value={value}
            onChange={e => onChange(e.target.value)}
            style={{
                background: C.bgInput || C.bgElevated, color: C.textPrimary,
                border: `1px solid ${C.borderStrong}`, borderRadius: R.sm,
                padding: `${S.xs}px ${S.sm}px`,
                fontSize: T.cap, fontWeight: T.w_med,
                fontFamily: FONT, outline: "none", cursor: "pointer", ...MONO,
            }}
        >
            {tickers.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
    )
}


/* ◆ MAIN ◆ */
interface Props {
    rawBaseUrl: string  // e.g. https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages
    defaultTicker: string
    tickerList: string  // comma-separated, e.g. "CRM,JPM,ADBE,..."
}

function EquityBriefCard({ rawBaseUrl, defaultTicker, tickerList }: Props) {
    const tickers = useMemo(() =>
        tickerList.split(",").map(t => t.trim().toUpperCase()).filter(Boolean),
        [tickerList]
    )
    const [ticker, setTicker] = useState(defaultTicker.toUpperCase() || (tickers[0] || "CRM"))
    const [brief, setBrief] = useState<Brief | null>(null)
    const [loading, setLoading] = useState(false)
    const [err, setErr] = useState<string | null>(null)

    useEffect(() => {
        if (!ticker) return
        const ac = new AbortController()
        setLoading(true); setErr(null); setBrief(null)
        const url = `${rawBaseUrl.replace(/\/$/, "")}/data/equity_research/${ticker}.json`
        fetch(url, { signal: ac.signal })
            .then(r => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`)
                return r.json()
            })
            .then((j: Brief) => { setBrief(j); setLoading(false) })
            .catch(e => { if (e.name !== "AbortError") { setErr(e.message); setLoading(false) } })
        return () => ac.abort()
    }, [ticker, rawBaseUrl])

    const ac = brief?.analyst_consensus || {}
    const gap = fmtPct(ac.current_price ?? undefined, ac.price_target_avg ?? undefined)
    const recMean = ac.recommendation_mean

    return (
        <div style={{
            width: "100%", height: "100%",
            display: "flex", flexDirection: "column", gap: S.md,
            padding: S.lg, background: C.bgCard,
            border: `1px solid ${C.border}`, borderLeft: `3px solid ${C.accent}`,
            borderRadius: R.md,
            fontFamily: FONT, color: C.textPrimary,
            boxSizing: "border-box", minWidth: 320, ...MOTION,
        }}>
            {/* Header */}
            <div style={{ display: "flex", alignItems: "center", gap: S.sm, flexWrap: "wrap" }}>
                <span style={{ fontSize: T.cap - 1, color: C.textTertiary,
                    textTransform: "uppercase", letterSpacing: 1 }}>Equity Brief</span>
                <span style={{ flex: 1 }} />
                <TickerSelector tickers={tickers.length ? tickers : [ticker]}
                    value={ticker} onChange={setTicker} />
            </div>

            <div style={{ display: "flex", alignItems: "baseline", gap: S.md, flexWrap: "wrap" }}>
                <span style={{ fontSize: T.h2, fontWeight: T.w_bold, color: C.textPrimary, ...MONO }}>
                    {ticker}
                </span>
                <VerdictBadge verdict={brief?.brief_verdict} />
                <span style={{ flex: 1 }} />
                <span style={{ fontSize: T.cap, color: C.textTertiary }}>
                    {relTime(brief?.generated_at)}
                </span>
            </div>

            {loading && (
                <span style={{ fontSize: T.cap, color: C.info, ...MONO }}>· 로딩 중</span>
            )}
            {err && (
                <span style={{ fontSize: T.cap, color: C.danger }}>
                    ⚠ brief 로딩 실패: {err} (주 1회 cron 가 아직 안 돈 ticker 일 수 있음)
                </span>
            )}

            {brief && (
                <>
                    {/* Analyst consensus block */}
                    <div style={{ display: "flex", flexDirection: "column", gap: S.xs,
                        padding: `${S.sm}px ${S.md}px`, background: C.bgElevated, borderRadius: R.sm }}>
                        <div style={{ display: "flex", alignItems: "baseline", gap: S.md, flexWrap: "wrap" }}>
                            <span style={{ fontSize: T.cap - 1, color: C.textTertiary,
                                textTransform: "uppercase", letterSpacing: 1 }}>Analyst</span>
                            {ac.current_price != null && (
                                <span style={{ fontSize: T.sub, fontWeight: T.w_bold, ...MONO }}>
                                    {fmtUSD(ac.current_price)}
                                </span>
                            )}
                            <span style={{ fontSize: T.cap, color: C.textSecondary, ...MONO }}>
                                → 목표 {fmtUSD(ac.price_target_avg)}
                            </span>
                            {gap && (
                                <span style={{
                                    fontSize: T.cap, color: gap.startsWith("+") ? C.success : C.danger,
                                    fontWeight: T.w_semi, ...MONO,
                                }}>{gap}</span>
                            )}
                            <span style={{ flex: 1 }} />
                            {recMean != null && (
                                <span style={{ fontSize: T.cap, color: C.textSecondary, ...MONO }}>
                                    rec {recMean.toFixed(2)} ({ac.recommendation_key || "—"}, n={ac.n_analysts ?? "—"})
                                </span>
                            )}
                        </div>
                        <PriceTargetBar
                            low={ac.price_target_low}
                            current={ac.current_price}
                            target={ac.price_target_avg}
                            high={ac.price_target_high}
                        />
                        {ac.eps_fy1_estimate != null && (
                            <div style={{ display: "flex", gap: S.md, marginTop: S.xs,
                                fontSize: T.cap, color: C.textSecondary }}>
                                <span>fwd EPS <strong style={{ color: C.textPrimary, ...MONO }}>
                                    {fmtUSD(ac.eps_fy1_estimate)}</strong></span>
                                {ac.pe_forward != null && (
                                    <span>fwd P/E <strong style={{ color: C.textPrimary, ...MONO }}>
                                        {ac.pe_forward.toFixed(1)}x</strong></span>
                                )}
                            </div>
                        )}
                    </div>

                    {/* 2026-05-17 빅브라더 정합 — VERITY 자체 관점 (LLM 가입자 못 가짐).
                        Brain v5 (가중치 7:3, 등급 75-60-45-30) + Lynch 6 카테고리 + VAMS holding.
                        thesis 보다 위에 노출 = 자기 차별점 우선 (사이트 사용자 unique view). */}
                    {brief.verity_trail && !brief.verity_trail._error &&
                     brief.verity_trail.brain_score != null && (
                        <div style={{
                            display: "flex", flexDirection: "column", gap: S.xs,
                            padding: `${S.sm}px ${S.md}px`,
                            background: C.accent + "0A",
                            border: `1px solid ${C.accent}33`,
                            borderRadius: R.sm,
                        }}>
                            <div style={{ display: "flex", alignItems: "baseline", gap: S.md, flexWrap: "wrap" }}>
                                <span style={{
                                    fontSize: T.cap - 1, color: C.accent,
                                    textTransform: "uppercase", letterSpacing: 1, fontWeight: T.w_bold,
                                }}>VERITY 관점 <span style={{
                                    color: C.warn, fontSize: T.cap - 2, marginLeft: 4,
                                    textTransform: "none", letterSpacing: 0, fontWeight: T.w_reg,
                                }}>· 가설 (N=14)</span></span>
                                {brief.verity_trail.grade && (
                                    <span style={{
                                        fontSize: T.body, fontWeight: T.w_bold,
                                        color: verdictColor(brief.verity_trail.grade),
                                        ...MONO, letterSpacing: 0.5,
                                    }}>
                                        {brief.verity_trail.grade.replace("_", " ")}
                                        {brief.verity_trail.grade_label && (
                                            <span style={{
                                                color: C.textSecondary,
                                                fontSize: T.cap, fontWeight: T.w_reg,
                                                marginLeft: S.xs,
                                            }}>({brief.verity_trail.grade_label})</span>
                                        )}
                                    </span>
                                )}
                                {brief.verity_trail.brain_score != null && (
                                    <span style={{
                                        fontSize: T.sub, fontWeight: T.w_bold,
                                        color: C.textPrimary, ...MONO,
                                    }} title="Brain v5 자체 산식 (가중치 7:3 + 등급 75-60-45-30)">
                                        {brief.verity_trail.brain_score}
                                    </span>
                                )}
                                {brief.verity_trail.grade_confidence && (
                                    <span style={{
                                        fontSize: T.cap - 1, color: C.textTertiary, ...MONO,
                                    }}>
                                        {brief.verity_trail.grade_confidence}
                                    </span>
                                )}
                                <span style={{ flex: 1 }} />
                                {brief.verity_trail.vams_holding_status === "holding" && (
                                    <span style={{
                                        padding: `${S.xs}px ${S.sm}px`,
                                        background: C.success + "1A",
                                        color: C.success,
                                        fontSize: T.cap, fontWeight: T.w_bold,
                                        borderRadius: R.sm, ...MONO,
                                    }} title={`VAMS 보유 — entry $${brief.verity_trail.vams_holding_entry_price}, ${brief.verity_trail.vams_holding_days}일`}>
                                        VAMS 보유
                                        {brief.verity_trail.vams_holding_pnl_pct != null && (
                                            <span style={{ marginLeft: S.xs }}>
                                                {brief.verity_trail.vams_holding_pnl_pct >= 0 ? "+" : ""}
                                                {brief.verity_trail.vams_holding_pnl_pct.toFixed(1)}%
                                            </span>
                                        )}
                                    </span>
                                )}
                            </div>

                            {/* Fact + Sentiment + VCI sub-scores */}
                            <div style={{ display: "flex", gap: S.md, flexWrap: "wrap",
                                fontSize: T.cap, color: C.textSecondary, ...MONO }}>
                                {brief.verity_trail.fact_score != null && (
                                    <span title="팩트 점수 (multi_factor + consensus + 12 지표)">
                                        팩트 <strong style={{ color: C.textPrimary }}>
                                            {brief.verity_trail.fact_score}</strong>
                                    </span>
                                )}
                                {brief.verity_trail.sentiment_score != null && (
                                    <span title="13-source hard-wire sentiment">
                                        심리 <strong style={{ color: C.textPrimary }}>
                                            {brief.verity_trail.sentiment_score}</strong>
                                    </span>
                                )}
                                {brief.verity_trail.vci_value != null && (
                                    <span title={brief.verity_trail.vci_label || "팩트-심리 정렬 지수"}
                                        style={{
                                            color: brief.verity_trail.vci_signal === "ALIGNED"
                                                ? C.success : C.warn,
                                        }}>
                                        VCI <strong>{brief.verity_trail.vci_value > 0 ? "+" : ""}
                                            {brief.verity_trail.vci_value}</strong>
                                        {brief.verity_trail.vci_signal && (
                                            <span style={{ marginLeft: 4, fontSize: T.cap - 2 }}>
                                                ({brief.verity_trail.vci_signal})
                                            </span>
                                        )}
                                    </span>
                                )}
                                {brief.verity_trail.lynch_class && (
                                    <span title={brief.verity_trail.lynch_summary || ""}>
                                        Lynch <strong style={{ color: C.accent }}>
                                            {brief.verity_trail.lynch_label || brief.verity_trail.lynch_class}</strong>
                                    </span>
                                )}
                                {brief.verity_trail.recommended_position_pct != null && (
                                    <span title={brief.verity_trail.position_rationale || ""}>
                                        포지션 <strong style={{
                                            color: brief.verity_trail.recommended_position_pct > 0
                                                ? C.accent : C.textTertiary,
                                        }}>
                                            {brief.verity_trail.recommended_position_pct.toFixed(1)}%
                                        </strong>
                                    </span>
                                )}
                            </div>

                            {/* Red flags (auto_avoid / downgrade) */}
                            {brief.verity_trail.red_flags_auto_avoid &&
                             brief.verity_trail.red_flags_auto_avoid.length > 0 && (
                                <div style={{
                                    display: "flex", flexDirection: "column", gap: 2,
                                    marginTop: S.xs,
                                }}>
                                    {brief.verity_trail.red_flags_auto_avoid.slice(0, 2).map((rf, i) => (
                                        <span key={`avoid-${i}`} style={{
                                            fontSize: T.cap, color: C.danger,
                                            fontWeight: T.w_semi,
                                        }}>
                                            🚨 {rf}
                                        </span>
                                    ))}
                                    {brief.verity_trail.red_flags_downgrade?.slice(0, 1).map((rf, i) => (
                                        <span key={`down-${i}`} style={{
                                            fontSize: T.cap, color: C.warn,
                                        }}>
                                            ⚠ {rf}
                                        </span>
                                    ))}
                                </div>
                            )}

                            {/* 자체 reasoning (1줄 룰 기반 합성) */}
                            {brief.verity_trail.reasoning && (
                                <p style={{
                                    margin: 0, marginTop: S.xs,
                                    fontSize: T.cap, color: C.textSecondary,
                                    lineHeight: 1.45, fontStyle: "italic",
                                }} title="VERITY Brain v5 룰 기반 합성 (LLM call 없음)">
                                    {brief.verity_trail.reasoning.slice(0, 280)}
                                    {brief.verity_trail.reasoning.length > 280 && "…"}
                                </p>
                            )}
                        </div>
                    )}

                    {/* Thesis top 2 */}
                    {brief.thesis && brief.thesis.length > 0 && (
                        <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                            <span style={{ fontSize: T.cap - 1, color: C.textTertiary,
                                textTransform: "uppercase", letterSpacing: 1 }}>Thesis</span>
                            {brief.thesis.slice(0, 2).map((t, i) => (
                                <p key={i} style={{ margin: 0, fontSize: T.body,
                                    color: C.textSecondary, lineHeight: 1.5 }}>
                                    · {t}
                                </p>
                            ))}
                        </div>
                    )}

                    {/* Recent catalyst (top 1) */}
                    {brief.recent_catalysts && brief.recent_catalysts[0] && (
                        <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                            <span style={{ fontSize: T.cap - 1, color: C.textTertiary,
                                textTransform: "uppercase", letterSpacing: 1 }}>최근 Catalyst</span>
                            <p style={{ margin: 0, fontSize: T.body,
                                color: C.textSecondary, lineHeight: 1.5 }}>
                                <span style={{ ...MONO, color: C.accent, marginRight: S.xs }}>
                                    {brief.recent_catalysts[0].date}
                                </span>
                                {brief.recent_catalysts[0].event}
                            </p>
                        </div>
                    )}

                    {/* Risk top 1 */}
                    {brief.risks && brief.risks[0] && (
                        <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                            <span style={{ fontSize: T.cap - 1, color: C.danger,
                                textTransform: "uppercase", letterSpacing: 1 }}>주요 Risk</span>
                            <p style={{ margin: 0, fontSize: T.body,
                                color: C.textSecondary, lineHeight: 1.5 }}>
                                · {brief.risks[0]}
                            </p>
                        </div>
                    )}

                    {/* Footer */}
                    <div style={{ display: "flex", gap: S.md, alignItems: "center",
                        fontSize: T.cap - 1, color: C.textTertiary, ...MONO,
                        paddingTop: S.xs, borderTop: `1px solid ${C.border}` }}>
                        <span>generated {brief.generated_at?.slice(0, 10) || "—"}</span>
                        {brief.cost_usd != null && <span>· ${brief.cost_usd?.toFixed(4)}</span>}
                        {brief.sec_filings_recent && (
                            <span>· {brief.sec_filings_recent.length} SEC filings</span>
                        )}
                    </div>
                </>
            )}
        </div>
    )
}

addPropertyControls(EquityBriefCard, {
    rawBaseUrl: {
        type: ControlType.String,
        title: "Raw Base URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages",
    },
    defaultTicker: {
        type: ControlType.String,
        title: "Default Ticker",
        defaultValue: "CRM",
    },
    tickerList: {
        type: ControlType.String,
        title: "Ticker List (CSV)",
        defaultValue: "CRM,JPM,ADBE,BAC,DIS,AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,V,MA,WMT",
        description: "comma-separated US15. component 내부 selector 로 변환",
    },
})

export default EquityBriefCard
