import { addPropertyControls, ControlType } from "framer"
import { useEffect, useMemo, useState, type CSSProperties } from "react"

/**
 * USFinancialsCard — US15 SEC EDGAR XBRL 표준화 재무 카드.
 *
 * 출처: /api/verity/us-financials (vercel-api/api/us_financials.py read-through).
 *      summary = 전체 15종목, ?ticker=X = per-ticker 8Q+5Y 시계열+파생.
 *      us_financials_builder 월 1회 cron. project_us_financials_sec_edgar.
 *
 * sector-aware (v0.3): 금융(SIC 6000-6499)은 op_margin 부재 → pretax_margin 표시,
 *      FCF=OCF-CapEx 무의미 → "N/A · 금융". 비금융은 op_margin + FCF.
 *
 * 디자인: USDetailHub 정합 — 모던 심플 6원칙 (No card-in-card / flat / mono / 토큰 색 / emoji 0).
 *      master-detail: 선택 종목 상세 + 클릭 가능 universe list. revenue SVG sparkline.
 *      feedback_no_hardcode_position / feedback_framer_hooks_top_level 적용.
 */

/* ◆ DESIGN TOKENS — VERITY 마스터 (USDetailHub 정합) ◆ */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
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
    // v0.4 자체 산식 calibration
    altman_z?: { z_score?: number | null; zone?: string; model_variant?: string } | null
    fscore?: { f_score?: number | null; grade?: string } | null
    lynch?: { lynch_class?: string | null; label?: string } | null
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
function fmtPct(n?: number | null, d = 1): string {
    if (n == null || !Number.isFinite(n as number)) return "—"
    const sign = (n as number) > 0 ? "+" : ""
    return `${sign}${(n as number).toFixed(d)}%`
}
function fmtPlain(n?: number | null, d = 1): string {
    if (n == null || !Number.isFinite(n as number)) return "—"
    return `${(n as number).toFixed(d)}%`
}
function pctColor(n?: number | null): string {
    if (n == null || !Number.isFinite(n as number)) return C.textTertiary
    return (n as number) >= 0 ? C.success : C.danger
}
function fmtFCF(n?: number | null, reason?: string | null): string {
    if (reason) return "N/A · 금융"
    if (n == null || !Number.isFinite(n as number)) return "—"
    return `$${((n as number) / 1e9).toFixed(1)}B`
}
function fmtRatio(n?: number | null): string {
    if (n == null || !Number.isFinite(n as number)) return "—"
    return (n as number).toFixed(2)
}
/** sector-aware 수익성: 금융/op 부재 → 세전이익률, 아니면 영업이익률 */
function profitability(d: Derived, isFin?: boolean): { label: string; val?: number | null } {
    if (isFin || d.operating_margin_pct == null) {
        return { label: "세전이익률", val: d.pretax_margin_pct }
    }
    return { label: "영업이익률", val: d.operating_margin_pct }
}
function zoneColor(zone?: string): string {
    if (zone === "safe") return C.success
    if (zone === "grey") return C.warn
    if (zone === "distress") return C.danger
    return C.textTertiary
}
function zoneLabel(zone?: string): string {
    if (zone === "safe") return "안전"
    if (zone === "grey") return "회색"
    if (zone === "distress") return "위험"
    return ""
}
function fGradeColor(grade?: string): string {
    if (grade === "strong") return C.success
    if (grade === "weak") return C.danger
    return C.warn
}

/* ◆ mini sparkline (USDetailHub 정합) ◆ */
function MiniSparkline({ data, color }: { data: number[]; color: string }) {
    if (!data || data.length < 2) return null
    const min = Math.min(...data)
    const max = Math.max(...data)
    const range = max - min || 1
    const w = 72, h = 22
    const step = w / (data.length - 1)
    const pts = data.map((v, i) => `${i * step},${h - ((v - min) / range) * h}`).join(" ")
    return (
        <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
            <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5"
                strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    )
}

/* ◆ MetricChip (USDetailHub 정합 — flat, no bg) ◆ */
function MetricChip({ label, value, color = C.textPrimary }: { label: string; value: string; color?: string }) {
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0,
            padding: `2px ${S.sm}px 2px 0` }}>
            <span style={{ color: C.textTertiary, fontSize: 9, fontWeight: T.w_med,
                letterSpacing: 0.5, fontFamily: FONT }}>{label}</span>
            <span style={{ ...MONO, color, fontSize: T.cap, fontWeight: T.w_semi }}>{value}</span>
        </div>
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

    useEffect(() => {
        const ac = new AbortController()
        fetch(`${base}/api/verity/us-financials`, { signal: ac.signal })
            .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
            .then((j: Summary) => setSummary(j))
            .catch((e) => { if (e.name !== "AbortError") setErr(e.message) })
        return () => ac.abort()
    }, [base])

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
    const revVals = (snap?.series_annual?.revenue || []).map((p) => p.val).filter((v) => Number.isFinite(v))
    const rows = summary?.rows || []

    return (
        <div style={shell}>
            {/* Header */}
            <div style={headerRow}>
                <div style={headerLeft}>
                    <span style={titleStyle}>US Financials</span>
                    <span style={metaStyle}>SEC EDGAR · 표준화 재무 · 월 1회</span>
                </div>
                <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap }}>
                    {rows.length || tickers.length} 종목
                </span>
            </div>

            <div style={hr} />

            {err && <span style={{ fontSize: T.cap, color: C.warn }}>source 연결 실패: {err}</span>}

            {/* Selected detail — headline */}
            <div style={{ display: "flex", alignItems: "baseline", gap: S.sm, flexWrap: "wrap" }}>
                <span style={{ ...MONO, fontSize: T.h2, fontWeight: T.w_bold, color: C.textPrimary }}>{ticker}</span>
                <span style={{ fontSize: T.cap, color: C.textSecondary }}>{name}</span>
                {isFin && (
                    <span style={{ fontSize: 10, color: C.info, background: "rgba(91,169,255,0.1)",
                        padding: `1px ${S.sm}px`, borderRadius: R.pill, fontWeight: T.w_semi }}>금융</span>
                )}
            </div>

            {/* headline metric + secondary summary */}
            <div style={summaryRow}>
                <div style={summaryItem}>
                    <span style={summaryCap}>매출 YoY</span>
                    <span style={{ ...MONO, color: pctColor(d.revenue_yoy_pct_annual), fontSize: T.h1, fontWeight: T.w_bold }}>
                        {fmtPct(d.revenue_yoy_pct_annual)}
                    </span>
                </div>
                {revVals.length > 1 && (
                    <div style={summaryItem}>
                        <span style={summaryCap}>매출 추이 5Y</span>
                        <MiniSparkline data={revVals.slice(-5)} color={C.accent} />
                    </div>
                )}
                <div style={summaryItem}>
                    <span style={summaryCap}>분기 YoY</span>
                    <span style={{ ...MONO, color: pctColor(d.revenue_yoy_pct_quarterly), fontSize: T.title, fontWeight: T.w_semi }}>
                        {fmtPct(d.revenue_yoy_pct_quarterly)}
                    </span>
                </div>
            </div>

            {/* metric chips (flat) */}
            <div style={{ display: "flex", gap: S.lg, flexWrap: "wrap" }}>
                {d.gross_margin_pct != null && (
                    <MetricChip label="매출총이익률" value={fmtPlain(d.gross_margin_pct)} />
                )}
                <MetricChip label={prof.label} value={fmtPlain(prof.val)} color={C.accent} />
                <MetricChip label="순이익률" value={fmtPlain(d.net_margin_pct)} color={C.success} />
                <MetricChip label="ROE" value={fmtPlain(d.roe_pct)} />
                <MetricChip label="부채/자본" value={fmtRatio(d.debt_to_equity)} />
                <MetricChip label="FCF" value={fmtFCF(d.fcf_usd, d.fcf_na_reason)}
                    color={d.fcf_na_reason ? C.textTertiary : C.textPrimary} />
            </div>

            {/* 자체 산식 calibration — Altman / F-Score / Lynch (v0.4) */}
            {(d.altman_z?.z_score != null || d.fscore?.f_score != null || d.lynch?.lynch_class) && (
                <>
                    <div style={hr} />
                    <span style={summaryCap}>자체 산식 · 가설 (검증 진행 중)</span>
                    <div style={{ display: "flex", gap: S.xxl, flexWrap: "wrap", alignItems: "flex-end" }}>
                        {d.altman_z?.z_score != null && (
                            <div style={summaryItem}>
                                <span style={summaryCap}>Altman Z</span>
                                <span style={{ ...MONO, fontSize: T.title, fontWeight: T.w_bold, color: zoneColor(d.altman_z.zone) }}>
                                    {d.altman_z.z_score}
                                    <span style={{ fontSize: T.cap, marginLeft: S.xs }}>{zoneLabel(d.altman_z.zone)}</span>
                                </span>
                            </div>
                        )}
                        {d.fscore?.f_score != null && (
                            <div style={summaryItem}>
                                <span style={summaryCap}>F-Score</span>
                                <span style={{ ...MONO, fontSize: T.title, fontWeight: T.w_bold, color: fGradeColor(d.fscore.grade) }}>
                                    {d.fscore.f_score}<span style={{ color: C.textTertiary, fontSize: T.cap }}> / 9</span>
                                </span>
                            </div>
                        )}
                        {d.lynch?.lynch_class && (
                            <div style={summaryItem}>
                                <span style={summaryCap}>Lynch</span>
                                <span style={{ fontSize: T.sub, fontWeight: T.w_semi, color: C.accent }}>
                                    {d.lynch.label || d.lynch.lynch_class}
                                </span>
                            </div>
                        )}
                    </div>
                </>
            )}

            <div style={hr} />

            {/* Universe list (master-detail selector) */}
            <span style={summaryCap}>Universe</span>
            <div style={listWrap}>
                {rows.map((row) => {
                    const rp = profitability(row, row.is_financial)
                    const sel = row.ticker === ticker
                    return (
                        <div key={row.ticker} onClick={() => setTicker(row.ticker)} style={listRow(sel)}>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0, flex: 1 }}>
                                <span style={{ color: sel ? C.accent : C.textPrimary, fontSize: T.body,
                                    fontWeight: T.w_semi, ...MONO }}>{row.ticker}</span>
                                <span style={{ color: C.textTertiary, fontSize: T.cap,
                                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                    {row.entity_name || ""}
                                </span>
                            </div>
                            <div style={{ display: "flex", gap: S.lg, alignItems: "center", flexShrink: 0 }}>
                                <span style={{ ...MONO, color: pctColor(row.revenue_yoy_pct_annual),
                                    fontSize: T.cap, fontWeight: T.w_bold, width: 56, textAlign: "right" }}>
                                    {fmtPct(row.revenue_yoy_pct_annual)}
                                </span>
                                <span style={{ ...MONO, color: C.textSecondary, fontSize: T.cap,
                                    width: 48, textAlign: "right" }}>{fmtPlain(rp.val)}</span>
                                <span style={{ ...MONO, color: C.textSecondary, fontSize: T.cap,
                                    width: 48, textAlign: "right" }}>{fmtPlain(row.roe_pct)}</span>
                            </div>
                        </div>
                    )
                })}
            </div>

            <span style={{ fontSize: 10, color: C.textTertiary }}>
                SEC EDGAR XBRL · Altman Z / Piotroski F / Lynch (자체 산식 가설) · 금융 = 세전이익률 (v0.4)
            </span>
        </div>
    )
}

/* ◆ STYLES (USDetailHub 정합) ◆ */
const shell: CSSProperties = {
    width: "100%", boxSizing: "border-box",
    fontFamily: FONT, color: C.textPrimary,
    background: C.bgPage, borderRadius: 16, padding: S.xxl,
    display: "flex", flexDirection: "column", gap: S.lg,
}
const headerRow: CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center",
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
const listWrap: CSSProperties = {
    display: "flex", flexDirection: "column", maxHeight: 360, overflowY: "auto",
}
function listRow(sel: boolean): CSSProperties {
    return {
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: `${S.md}px ${S.sm}px`, gap: S.md, cursor: "pointer",
        background: sel ? C.accentSoft : "transparent",
        borderRadius: R.sm, transition: "background 180ms ease",
    }
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
        description: "comma-separated. universe fallback (summary fetch 우선)",
    },
})

export default USFinancialsCard
