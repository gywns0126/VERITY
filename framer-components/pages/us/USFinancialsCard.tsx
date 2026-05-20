import { addPropertyControls, ControlType } from "framer"
import { useEffect, useMemo, useState, type CSSProperties } from "react"

/**
 * USFinancialsCard — US15 SEC EDGAR XBRL 표준화 재무 카드.
 *
 * 출처: /api/verity/us-financials (vercel-api/api/us_financials.py read-through).
 *      summary = 전체 15종목, ?ticker=X = per-ticker 8Q+5Y 시계열+파생.
 *      us_financials_builder 월 1회 cron (분기 보고서 발표 후). project_us_financials_sec_edgar.
 *
 * sector-aware (v0.3): 금융(SIC 6000-6499)은 op_margin 부재 → pretax_margin 표시,
 *      FCF=OCF-CapEx 무의미 → "N/A · 금융". 비금융은 op_margin + FCF.
 *
 * VERITY 톤 정합 (EquityBriefCard 패턴) + 펜타그램 4 원칙 + margin mini viz (picture_book).
 * In-component interactivity: ticker dropdown (feedback_in_component_interactivity).
 */

/* ◆ DESIGN TOKENS — VERITY 마스터 ◆ */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B",
    border: "#23242C", borderStrong: "#34353D",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    up: "#22C55E", down: "#EF4444", info: "#5BA9FF", warn: "#F59E0B",
}
const T = { cap: 12, body: 14, sub: 16, title: 18, h2: 22,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700 }
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24 }
const R = { sm: 6, md: 10, lg: 14 }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Menlo', monospace"
const MONO: CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
const MOTION: CSSProperties = { transition: "all 200ms ease" }

/* ◆ TYPES ◆ */
interface Derived {
    revenue_yoy_pct_annual?: number | null
    revenue_yoy_pct_quarterly?: number | null
    gross_margin_pct?: number | null
    operating_margin_pct?: number | null
    pretax_margin_pct?: number | null
    net_margin_pct?: number | null
    fcf_usd?: number | null
    fcf_na_reason?: string | null
    debt_to_equity?: number | null
    roe_pct?: number | null
}
interface SummaryRow extends Derived {
    ticker: string
    entity_name?: string
    sic?: number | null
    is_financial?: boolean
}
interface Summary { schema_version?: string; generated_at?: string; rows: SummaryRow[] }
interface Snapshot {
    ticker: string
    meta?: { entity_name?: string; sic?: number | null; is_financial?: boolean }
    derived?: Derived
    series_annual?: Record<string, Array<{ end: string; val: number }>>
}

/* ◆ HELPERS ◆ */
function pct(n?: number | null, d = 1): string {
    if (n == null || isNaN(n as number)) return "—"
    return `${(n as number) >= 0 ? "" : ""}${(n as number).toFixed(d)}%`
}
function signColor(n?: number | null): string {
    if (n == null || isNaN(n as number)) return C.textTertiary
    return (n as number) >= 0 ? C.up : C.down
}
function fmtFCF(n?: number | null, reason?: string | null): string {
    if (reason) return "N/A · 금융"
    if (n == null || isNaN(n as number)) return "—"
    const b = (n as number) / 1e9
    return `$${b.toFixed(1)}B`
}
/** sector-aware 수익성: 금융/op 부재 → 세전이익률, 아니면 영업이익률 */
function profitability(d: Derived, isFin?: boolean): { label: string; val?: number | null } {
    if (isFin || d.operating_margin_pct == null) {
        return { label: "세전이익률", val: d.pretax_margin_pct }
    }
    return { label: "영업이익률", val: d.operating_margin_pct }
}

/* ◆ mini viz — margin bar (picture_book) ◆ */
function MarginBar({ label, value, color }: { label: string; value?: number | null; color: string }) {
    const v = value == null || isNaN(value) ? 0 : value
    const w = Math.max(0, Math.min(100, Math.abs(v)))  // 0~100% 클램프
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ fontSize: T.cap, color: C.textSecondary }}>{label}</span>
                <span style={{ fontSize: T.cap, color: value == null ? C.textTertiary : color, ...MONO }}>
                    {pct(value)}
                </span>
            </div>
            <div style={{ height: 4, background: C.bgElevated, borderRadius: 2, overflow: "hidden" }}>
                <div style={{ width: `${w}%`, height: "100%", background: color, ...MOTION }} />
            </div>
        </div>
    )
}

/* ◆ ticker selector (in-component) ◆ */
function TickerSelector({ tickers, value, onChange }: {
    tickers: string[]; value: string; onChange: (t: string) => void
}) {
    return (
        <select
            value={value}
            onChange={(e) => onChange(e.target.value)}
            style={{
                background: C.bgElevated, color: C.textPrimary,
                border: `1px solid ${C.borderStrong}`, borderRadius: R.sm,
                padding: `${S.xs}px ${S.sm}px`, fontSize: T.cap, fontFamily: FONT,
                cursor: "pointer", outline: "none", ...MONO,
            }}
        >
            {tickers.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
    )
}

/* ◆ MAIN ◆ */
interface Props {
    apiBase: string
    defaultTicker: string
    tickerList: string
}

function USFinancialsCard({ apiBase, defaultTicker, tickerList }: Props) {
    const tickers = useMemo(
        () => tickerList.split(",").map((t) => t.trim().toUpperCase()).filter(Boolean),
        [tickerList]
    )
    const [ticker, setTicker] = useState(defaultTicker.toUpperCase() || (tickers[0] || "MSFT"))
    const [summary, setSummary] = useState<Summary | null>(null)
    const [snap, setSnap] = useState<Snapshot | null>(null)
    const [err, setErr] = useState<string | null>(null)

    const base = useMemo(() => apiBase.replace(/\/$/, ""), [apiBase])

    // summary (mount)
    useEffect(() => {
        const ac = new AbortController()
        fetch(`${base}/api/verity/us-financials`, { signal: ac.signal })
            .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
            .then((j: Summary) => setSummary(j))
            .catch((e) => { if (e.name !== "AbortError") setErr(e.message) })
        return () => ac.abort()
    }, [base])

    // per-ticker detail
    useEffect(() => {
        if (!ticker) return
        const ac = new AbortController()
        setSnap(null)
        fetch(`${base}/api/verity/us-financials?ticker=${encodeURIComponent(ticker)}`, { signal: ac.signal })
            .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
            .then((j: Snapshot) => setSnap(j))
            .catch((e) => { if (e.name !== "AbortError") setSnap(null) })
        return () => ac.abort()
    }, [ticker, base])

    const d = snap?.derived || {}
    const isFin = snap?.meta?.is_financial
    const prof = profitability(d, isFin)
    const name = snap?.meta?.entity_name || ticker
    const revSeries = snap?.series_annual?.revenue || []

    return (
        <div style={{
            width: "100%", height: "100%",
            display: "flex", flexDirection: "column", gap: S.md,
            padding: S.lg, background: C.bgCard,
            border: `1px solid ${C.border}`, borderLeft: `3px solid ${C.accent}`,
            borderRadius: R.md, fontFamily: FONT, color: C.textPrimary,
            boxSizing: "border-box", minWidth: 320, overflow: "auto", ...MOTION,
        }}>
            {/* Header */}
            <div style={{ display: "flex", alignItems: "center", gap: S.sm, flexWrap: "wrap" }}>
                <span style={{ fontSize: T.cap - 1, color: C.textTertiary,
                    textTransform: "uppercase", letterSpacing: 1 }}>US Financials · SEC EDGAR</span>
                <span style={{ flex: 1 }} />
                <TickerSelector tickers={tickers.length ? tickers : [ticker]}
                    value={ticker} onChange={setTicker} />
            </div>

            {err && (
                <div style={{ fontSize: T.cap, color: C.warn }}>source 연결 실패: {err}</div>
            )}

            {/* Selected ticker detail */}
            <div style={{ display: "flex", alignItems: "baseline", gap: S.md, flexWrap: "wrap" }}>
                <span style={{ fontSize: T.h2, fontWeight: T.w_bold, ...MONO }}>{ticker}</span>
                <span style={{ fontSize: T.cap, color: C.textSecondary }}>{name}</span>
                {isFin && (
                    <span style={{ fontSize: T.cap - 1, color: C.info, background: "rgba(91,169,255,0.1)",
                        padding: `1px ${S.xs}px`, borderRadius: R.sm }}>금융</span>
                )}
            </div>

            {/* revenue YoY */}
            <div style={{ display: "flex", gap: S.lg, flexWrap: "wrap" }}>
                <div style={{ display: "flex", flexDirection: "column" }}>
                    <span style={{ fontSize: T.cap, color: C.textTertiary }}>매출 YoY (연간)</span>
                    <span style={{ fontSize: T.title, fontWeight: T.w_semi, color: signColor(d.revenue_yoy_pct_annual), ...MONO }}>
                        {pct(d.revenue_yoy_pct_annual)}
                    </span>
                </div>
                <div style={{ display: "flex", flexDirection: "column" }}>
                    <span style={{ fontSize: T.cap, color: C.textTertiary }}>매출 YoY (분기)</span>
                    <span style={{ fontSize: T.title, fontWeight: T.w_semi, color: signColor(d.revenue_yoy_pct_quarterly), ...MONO }}>
                        {pct(d.revenue_yoy_pct_quarterly)}
                    </span>
                </div>
                <div style={{ display: "flex", flexDirection: "column" }}>
                    <span style={{ fontSize: T.cap, color: C.textTertiary }}>ROE</span>
                    <span style={{ fontSize: T.title, fontWeight: T.w_semi, color: C.textPrimary, ...MONO }}>
                        {pct(d.roe_pct)}
                    </span>
                </div>
                <div style={{ display: "flex", flexDirection: "column" }}>
                    <span style={{ fontSize: T.cap, color: C.textTertiary }}>FCF</span>
                    <span style={{ fontSize: T.title, fontWeight: T.w_semi,
                        color: d.fcf_na_reason ? C.textTertiary : C.textPrimary, ...MONO }}>
                        {fmtFCF(d.fcf_usd, d.fcf_na_reason)}
                    </span>
                </div>
            </div>

            {/* margins mini viz */}
            <div style={{ display: "flex", flexDirection: "column", gap: S.sm,
                padding: S.md, background: C.bgElevated, borderRadius: R.sm }}>
                {d.gross_margin_pct != null && (
                    <MarginBar label="매출총이익률" value={d.gross_margin_pct} color={C.info} />
                )}
                <MarginBar label={prof.label} value={prof.val} color={C.accent} />
                <MarginBar label="순이익률" value={d.net_margin_pct} color={C.up} />
            </div>

            {/* revenue trend (mini, 최근 5Y) */}
            {revSeries.length > 1 && (
                <div style={{ display: "flex", alignItems: "flex-end", gap: S.xs, height: 36 }}>
                    {revSeries.slice(-5).map((p, i, arr) => {
                        const max = Math.max(...arr.map((x) => x.val || 0)) || 1
                        const h = Math.max(2, ((p.val || 0) / max) * 32)
                        return (
                            <div key={p.end} style={{ flex: 1, display: "flex", flexDirection: "column",
                                alignItems: "center", gap: 2 }}>
                                <div style={{ width: "100%", height: h, background: C.accentSoft,
                                    borderTop: `2px solid ${C.accent}`, borderRadius: 1, ...MOTION }} />
                                <span style={{ fontSize: 9, color: C.textTertiary, ...MONO }}>
                                    {p.end.slice(2, 4)}
                                </span>
                            </div>
                        )
                    })}
                </div>
            )}

            {/* universe table (compact) */}
            <div style={{ borderTop: `1px solid ${C.border}`, paddingTop: S.sm }}>
                <span style={{ fontSize: T.cap - 1, color: C.textTertiary,
                    textTransform: "uppercase", letterSpacing: 1 }}>Universe</span>
                <div style={{ display: "flex", flexDirection: "column", gap: 2, marginTop: S.xs }}>
                    {(summary?.rows || []).map((row) => {
                        const rp = profitability(row, row.is_financial)
                        const sel = row.ticker === ticker
                        return (
                            <div key={row.ticker}
                                onClick={() => setTicker(row.ticker)}
                                style={{
                                    display: "grid", gridTemplateColumns: "64px 1fr 1fr 1fr",
                                    gap: S.sm, padding: `${S.xs}px ${S.sm}px`, cursor: "pointer",
                                    background: sel ? C.accentSoft : "transparent",
                                    borderRadius: R.sm, fontSize: T.cap, ...MOTION,
                                }}>
                                <span style={{ fontWeight: sel ? T.w_semi : T.w_reg, color: sel ? C.accent : C.textPrimary, ...MONO }}>
                                    {row.ticker}
                                </span>
                                <span style={{ color: signColor(row.revenue_yoy_pct_annual), textAlign: "right", ...MONO }}>
                                    {pct(row.revenue_yoy_pct_annual)}
                                </span>
                                <span style={{ color: C.textSecondary, textAlign: "right", ...MONO }}>
                                    {pct(rp.val)}
                                </span>
                                <span style={{ color: C.textSecondary, textAlign: "right", ...MONO }}>
                                    {pct(row.roe_pct)}
                                </span>
                            </div>
                        )
                    })}
                </div>
            </div>

            {/* footer */}
            <span style={{ fontSize: 10, color: C.textTertiary, marginTop: "auto" }}>
                SEC EDGAR XBRL · 매출 YoY / 마진 / FCF · 금융 = 세전이익률 + FCF N/A (v0.3)
            </span>
        </div>
    )
}

addPropertyControls(USFinancialsCard, {
    apiBase: {
        type: ControlType.String,
        title: "API Base",
        defaultValue: "https://project-yw131.vercel.app",
    },
    defaultTicker: {
        type: ControlType.String,
        title: "Default Ticker",
        defaultValue: "MSFT",
    },
    tickerList: {
        type: ControlType.String,
        title: "US15 Tickers",
        defaultValue: "MSFT,JNJ,BAC,ADBE,CRM,JPM,DIS,SOFI,QCOM,META,BRK-B,TMO,PG,XOM,CSCO",
        description: "comma-separated. component 내부 selector + universe table",
    },
})

export default USFinancialsCard
