import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useMemo, useState } from "react"

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
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


const DATA_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"
const INITIAL_CASH = 10_000_000
const UP = C.up
const DOWN = C.down

function fetchJson(url: string): Promise<any> {
    const sep = url.includes("?") ? "&" : "?"
    return fetch(`${url}${sep}_=${Date.now()}`, { cache: "no-store", mode: "cors", credentials: "omit" })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((t) => JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
}

function fmtPct(n: number | null | undefined, digits = 2, showSign = true): string {
    if (n == null || !Number.isFinite(n)) return "—"
    const sign = showSign && n > 0 ? "+" : ""
    return `${sign}${n.toFixed(digits)}%`
}
function fmtPp(n: number | null | undefined, digits = 2): string {
    if (n == null || !Number.isFinite(n)) return "—"
    const sign = n > 0 ? "+" : ""
    return `${sign}${n.toFixed(digits)}%p`
}
function fmtRatio(n: number | null | undefined, digits = 2): string {
    if (n == null || !Number.isFinite(n)) return "—"
    return n.toFixed(digits)
}
function signedColor(n: number): string {
    if (n > 0) return UP
    if (n < 0) return DOWN
    return C.textSecondary
}
function daysBetween(fromStr: string | null | undefined, toDate: Date): number {
    if (!fromStr) return 0
    const d = new Date(fromStr)
    if (isNaN(d.getTime())) return 0
    return Math.max(0, Math.floor((toDate.getTime() - d.getTime()) / 86_400_000))
}

/* ─────────── 판정 배지 ─────────── */
const VERDICT_META: Record<string, { label: string; color: string; bg: string; glow: string }> = {
    PASS: { label: "PASS", color: C.success, bg: "rgba(34,197,94,0.12)", glow: G.success },
    WATCH: { label: "WATCH", color: C.watch, bg: "rgba(255,214,0,0.12)", glow: "none" },
    FAIL: { label: "FAIL", color: C.danger, bg: "rgba(239,68,68,0.12)", glow: G.danger },
    INSUFFICIENT_DATA: { label: "샘플 부족", color: C.textSecondary, bg: "rgba(168,171,178,0.10)", glow: "none" },
}
function Badge({ verdict, size = 16 }: { verdict: string; size?: number }) {
    const m = VERDICT_META[verdict] || VERDICT_META.INSUFFICIENT_DATA
    return (
        <span style={{
            display: "inline-flex", alignItems: "center",
            fontSize: size, fontWeight: T.w_bold, color: m.color, background: m.bg,
            padding: size >= 16 ? "4px 10px" : "2px 7px", borderRadius: R.pill,
            boxShadow: m.glow, letterSpacing: 0.3,
            ...MONO,
        }}>
            {m.label}
        </span>
    )
}

/* ─────────── pass 표시 기호 ─────────── */
function PassMark({ pass }: { pass: boolean | null }) {
    if (pass == null) return <span style={{ color: C.textTertiary, fontSize: T.body }}>—</span>
    return <span style={{ color: pass ? C.success : C.danger, fontSize: T.body, fontWeight: T.w_bold }}>{pass ? "✓" : "✗"}</span>
}

/* ─────────── 비용 breakdown 한 줄 ─────────── */
function CostRow({ label, valuePp, note }: { label: string; valuePp: number | null; note?: string }) {
    return (
        <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "baseline",
            padding: `${S.xs}px 0`,
        }}>
            <span style={{ fontSize: T.body, color: C.textSecondary }}>
                {label}
                {note && <span style={{ color: C.textTertiary, fontSize: T.cap, marginLeft: S.sm }}>({note})</span>}
            </span>
            <span style={{ fontSize: T.body, color: valuePp != null && valuePp < 0 ? DOWN : C.textSecondary, ...MONO }}>
                {valuePp != null ? fmtPp(valuePp) : "—"}
            </span>
        </div>
    )
}
function CostTotalRow({ label, valuePct, accent }: { label: string; valuePct: number | null; accent?: boolean }) {
    const color = accent ? C.accent : (valuePct != null ? signedColor(valuePct) : C.textSecondary)
    return (
        <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "baseline",
            padding: `${S.sm}px 0`,
        }}>
            <span style={{ fontSize: T.sub, fontWeight: T.w_semi, color: C.textPrimary }}>{label}</span>
            <span style={{
                fontSize: T.title, fontWeight: T.w_bold, color, ...MONO,
                textShadow: accent ? G.accent : undefined,
            }}>
                {fmtPct(valuePct)}
            </span>
        </div>
    )
}

/* ─────────── 메트릭 카드 (6개 + cost_efficiency) ─────────── */
function MetricCard({
    title, pass, primary, secondary, threshold,
}: {
    title: string
    pass: boolean | null
    primary: string
    secondary?: string
    threshold?: string
}) {
    const borderColor = pass === true ? C.success : pass === false ? C.danger : C.border
    const glow = pass === true ? G.success : pass === false ? G.danger : "none"
    return (
        <div style={{
            background: C.bgCard, border: `1px solid ${borderColor}`, borderRadius: R.md,
            padding: `${S.md}px ${S.lg}px`, display: "flex", flexDirection: "column", gap: S.xs,
            boxShadow: glow,
        }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: T.cap, color: C.textSecondary, fontWeight: T.w_med, letterSpacing: 0.2 }}>{title}</span>
                <PassMark pass={pass} />
            </div>
            <span style={{ fontSize: T.title, fontWeight: T.w_bold, color: C.textPrimary, ...MONO, lineHeight: T.lh_tight }}>
                {primary}
            </span>
            {secondary && (
                <span style={{ fontSize: T.cap, color: C.textTertiary, ...MONO }}>{secondary}</span>
            )}
            {threshold && (
                <span style={{ fontSize: T.cap, color: C.textTertiary, marginTop: S.xs }}>{threshold}</span>
            )}
        </div>
    )
}

/* ─────────── 체크포인트 진행도 바 ─────────── */
function CheckpointBar({ daysPassed, labels }: { daysPassed: number; labels: { days: number; label: string }[] }) {
    const maxDays = labels[labels.length - 1].days
    const progressPct = Math.min(100, (daysPassed / maxDays) * 100)
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.sm }}>
            <div style={{ position: "relative", height: 6, background: C.bgInput, borderRadius: 3, overflow: "hidden" }}>
                <div style={{
                    position: "absolute", left: 0, top: 0, bottom: 0,
                    width: `${progressPct}%`, background: C.accent, boxShadow: G.accentSoft,
                }} />
                {labels.map((l) => {
                    const left = Math.min(100, (l.days / maxDays) * 100)
                    const reached = daysPassed >= l.days
                    return (
                        <div key={l.days} style={{
                            position: "absolute", left: `${left}%`, top: -2, width: 2, height: 10,
                            background: reached ? C.accent : C.borderStrong,
                        }} />
                    )
                })}
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: T.cap, color: C.textSecondary }}>
                {labels.map((l) => {
                    const reached = daysPassed >= l.days
                    return (
                        <span key={l.days} style={{ color: reached ? C.accent : C.textSecondary, fontWeight: reached ? T.w_semi : T.w_reg }}>
                            {l.label} <span style={{ color: C.textTertiary }}>D{Math.max(0, l.days - daysPassed)}</span>
                        </span>
                    )
                })}
            </div>
        </div>
    )
}

/* ═══════════════════════════ 메인 컴포넌트 ═══════════════════════════ */

interface Props {
    dataUrl: string
    initialCash: number
}

export default function ValidationPanel(props: Props) {
    const { dataUrl, initialCash } = props
    const [portfolio, setPortfolio] = useState<any>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState("")

    useEffect(() => {
        const url = dataUrl || DATA_URL
        fetchJson(url)
            .then((p) => setPortfolio(p))
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false))
    }, [dataUrl])

    const derived = useMemo(() => {
        if (!portfolio) return null
        const vams = portfolio.vams || {}
        const adj = vams.adjusted_performance || {}
        const val = vams.validation_report || {}
        const deductions = adj.deductions || {}
        const cash = initialCash || INITIAL_CASH

        // 항목별 %p 로 환산 (초기자본 대비)
        const toPp = (krw: number) => (Number.isFinite(krw) && cash > 0 ? -(krw / cash) * 100 : null)
        const taxRealized = toPp(deductions.sell_tax_realized || 0)
        const taxUnrealized = toPp(deductions.sell_tax_unrealized_est || 0)
        const spreadRealized = toPp(deductions.spread_slippage_realized || 0)
        const spreadUnrealized = toPp(deductions.spread_slippage_unrealized_est || 0)
        const dividendTax = toPp(deductions.dividend_tax || 0)

        const taxTotal = (taxRealized ?? 0) + (taxUnrealized ?? 0)
        const spreadTotal = (spreadRealized ?? 0) + (spreadUnrealized ?? 0)

        return {
            vams, adj, val, deductions,
            raw: adj.raw_return_pct ?? vams.total_return_pct ?? 0,
            adjusted: adj.adjusted_return_pct ?? vams.total_return_pct ?? 0,
            gap: adj.gap_pp ?? 0,
            taxTotal, spreadTotal, dividendTax,
            taxRealized, taxUnrealized, spreadRealized, spreadUnrealized,
        }
    }, [portfolio, initialCash])

    if (loading) return (
        <div style={{ fontFamily: FONT, background: C.bgPage, color: C.textSecondary, padding: 40, borderRadius: R.lg, textAlign: "center", fontSize: T.body }}>
            로딩 중…
        </div>
    )
    if (error) return (
        <div style={{ fontFamily: FONT, background: C.bgPage, color: C.danger, padding: S.xl, borderRadius: R.lg, textAlign: "center", fontSize: T.body }}>
            {error}
        </div>
    )
    if (!derived) return null

    const { vams, val, raw, adjusted, gap, taxTotal, spreadTotal, dividendTax, taxRealized, taxUnrealized, spreadRealized, spreadUnrealized } = derived
    const metrics = val.metrics || {}
    const window = val.window || {}
    const sampleChecks = val.sample_checks || {}
    const thresholds = val.thresholds || {}
    const overall = val.overall || "INSUFFICIENT_DATA"

    // KOSPI 누적수익률 & 알파
    const benchRet: number = metrics.cumulative_return?.benchmark_return_pct ?? 0
    const alpha = adjusted - benchRet

    // 체크포인트 진행도 (첫 스냅샷 날짜부터)
    const daysPassed = daysBetween(window.start, new Date())

    // 메트릭 카드 데이터
    const mRet = metrics.cumulative_return || {}
    const mMdd = metrics.mdd || {}
    const mWin = metrics.win_rate || {}
    const mPl = metrics.profit_loss_ratio || {}
    const mSharpe = metrics.sharpe || {}
    const mRegime = metrics.regime_coverage || {}
    const mCost = metrics.cost_efficiency || {}

    return (
        <div style={{
            fontFamily: FONT, background: C.bgPage, color: C.textPrimary,
            padding: S.xl, borderRadius: R.lg,
            display: "flex", flexDirection: "column", gap: S.lg,
            minWidth: 360,
        }}>
            {/* ── Header ── */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: S.md }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={{ fontSize: T.title, fontWeight: T.w_bold, color: C.textPrimary }}>VAMS 검증 대시보드</span>
                    <span style={{ fontSize: T.cap, color: C.textTertiary }}>
                        실거래 전환 전 운영 누적 판정 · 룰 진화 OK · {window.days ?? 0}일 / {window.snapshot_count ?? 0}스냅샷
                    </span>
                </div>
                <Badge verdict={overall} />
            </div>

            {/* ── Checkpoint bar ── */}
            <div style={{
                background: C.bgCard, border: `1px solid ${C.border}`, borderRadius: R.md,
                padding: S.lg, display: "flex", flexDirection: "column", gap: S.md,
            }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: T.cap, color: C.textSecondary, fontWeight: T.w_med, letterSpacing: 0.3 }}>검증 진행도</span>
                    <span style={{ fontSize: T.body, color: C.textPrimary, ...MONO }}>
                        <span style={{ color: C.accent, fontWeight: T.w_bold }}>D+{daysPassed}</span>
                        <span style={{ color: C.textTertiary }}>
                            {window.validation_start_configured
                                ? ` · 공식 ${window.validation_start_configured}`
                                : window.start ? ` · since ${window.start}` : ""}
                        </span>
                    </span>
                </div>
                <CheckpointBar
                    daysPassed={daysPassed}
                    labels={[
                        { days: 90, label: "3M 최초 판정" },
                        { days: 180, label: "6M 본판정" },
                        { days: 365, label: "12M 최대" },
                    ]}
                />
            </div>

            {/* ── Cost Breakdown ── */}
            <div style={{
                background: C.bgCard, border: `1px solid ${C.border}`, borderRadius: R.md,
                padding: S.lg, display: "flex", flexDirection: "column",
            }}>
                <span style={{ fontSize: T.cap, color: C.textSecondary, fontWeight: T.w_med, letterSpacing: 0.3, marginBottom: S.sm }}>
                    보정 전/후 수익률
                </span>

                <CostTotalRow label="VAMS 원 수익률" valuePct={raw} />

                <div style={{ height: 1, background: C.border, margin: `${S.xs}px 0` }} />

                <CostRow label="거래세" valuePp={taxTotal} note={`실현 ${fmtPp(taxRealized, 3)} / 평가 ${fmtPp(taxUnrealized, 3)}`} />
                <CostRow label="호가 스프레드" valuePp={spreadTotal} note={`실현 ${fmtPp(spreadRealized, 3)} / 평가 ${fmtPp(spreadUnrealized, 3)}`} />
                <CostRow label="배당세" valuePp={dividendTax} note={(dividendTax ?? 0) === 0 ? "수집기 미구현" : undefined} />

                <div style={{ height: 1, background: C.border, margin: `${S.xs}px 0` }} />

                <CostTotalRow label="VAMS 보정 수익률" valuePct={adjusted} accent />

                <div style={{ height: 1, background: C.border, margin: `${S.sm}px 0` }} />

                <div style={{ display: "flex", justifyContent: "space-between", padding: `${S.xs}px 0` }}>
                    <span style={{ fontSize: T.body, color: C.textSecondary }}>KOSPI (벤치)</span>
                    <span style={{ fontSize: T.body, color: signedColor(benchRet), ...MONO }}>{fmtPct(benchRet)}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", padding: `${S.xs}px 0`, alignItems: "baseline" }}>
                    <span style={{ fontSize: T.sub, fontWeight: T.w_semi, color: C.textPrimary }}>실질 알파</span>
                    <span style={{
                        fontSize: T.title, fontWeight: T.w_bold, ...MONO,
                        color: alpha > 0 ? C.success : alpha < 0 ? C.danger : C.textSecondary,
                        textShadow: alpha > 0 ? G.success : undefined,
                    }}>
                        {fmtPp(alpha)} {alpha > 0 ? "✓" : alpha < 0 ? "✗" : ""}
                    </span>
                </div>
            </div>

            {/* ── Sample Checks ── */}
            <div style={{
                background: C.bgCard, border: `1px solid ${C.border}`, borderRadius: R.md,
                padding: S.md, display: "grid", gridTemplateColumns: "1fr 1fr",
                gap: S.md, fontSize: T.cap,
            }}>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: C.textSecondary }}>최소 거래일</span>
                    <span style={{ ...MONO, color: sampleChecks.days_ok ? C.success : C.warn }}>
                        {window.days ?? 0} / {sampleChecks.days_required ?? 60}
                    </span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: C.textSecondary }}>최소 매매건</span>
                    <span style={{ ...MONO, color: sampleChecks.trades_ok ? C.success : C.warn }}>
                        {mWin.trades ?? 0} / {sampleChecks.trades_required ?? 20}
                    </span>
                </div>
            </div>

            {/* ── 지표 그리드 (7개) ── */}
            <div style={{
                display: "grid", gap: S.sm,
                gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
            }}>
                <MetricCard
                    title="누적 수익률 (보정)"
                    pass={mRet.pass ?? null}
                    primary={fmtPp(mRet.excess_pp)}
                    secondary={`VAMS ${fmtPct(mRet.vams_return_pct)} · 벤치 ${fmtPct(mRet.benchmark_return_pct)}`}
                    threshold={`통과선: 벤치 대비 ≥ ${thresholds.excess_return_pp_min ?? 0}%p`}
                />
                <MetricCard
                    title="MDD 비율"
                    pass={mMdd.pass ?? null}
                    primary={fmtRatio(mMdd.ratio)}
                    secondary={`VAMS ${fmtPct(mMdd.vams_mdd_pct)} · 벤치 ${fmtPct(mMdd.benchmark_mdd_pct)}`}
                    threshold={`통과선: ≤ ${thresholds.mdd_ratio_max ?? 1.0}`}
                />
                <MetricCard
                    title="승률"
                    pass={mWin.pass ?? null}
                    primary={mWin.win_rate != null ? `${(mWin.win_rate * 100).toFixed(1)}%` : "—"}
                    secondary={`${mWin.wins ?? 0}승 ${mWin.losses ?? 0}패 (${mWin.trades ?? 0}건)`}
                    threshold={`통과선: ≥ ${((thresholds.win_rate_min ?? 0.55) * 100).toFixed(0)}%`}
                />
                <MetricCard
                    title="손익비"
                    pass={mPl.pass ?? null}
                    primary={fmtRatio(mPl.pl_ratio)}
                    secondary={
                        mPl.avg_win != null && mPl.avg_loss != null
                            ? `+${Math.round(mPl.avg_win / 10000)}만 / ${Math.round(mPl.avg_loss / 10000)}만`
                            : "—"
                    }
                    threshold={`통과선: ≥ ${thresholds.profit_loss_ratio_min ?? 1.5}`}
                />
                <MetricCard
                    title="샤프 (연율)"
                    pass={mSharpe.pass ?? null}
                    primary={fmtRatio(mSharpe.annualized)}
                    secondary={mSharpe.verdict ? `verdict: ${mSharpe.verdict}` : undefined}
                    threshold={`≥ ${thresholds.sharpe_min ?? 1.0} 통과 · < ${thresholds.sharpe_redesign_below ?? 0.5} 재설계`}
                />
                <MetricCard
                    title="레짐 커버"
                    pass={mRegime.pass ?? null}
                    primary={mRegime.covered ? "covered" : "not yet"}
                    secondary={`벤치 MDD ${fmtPct(mRegime.peak_drawdown_pct)}`}
                    threshold={`조정 국면 ≥ ${thresholds.regime_drawdown_pct ?? 10}%`}
                />
                <MetricCard
                    title="비용 효율 (gap/α)"
                    pass={mCost.pass ?? null}
                    primary={fmtRatio(mCost.cost_to_alpha_ratio)}
                    secondary={`gap ${fmtPp(mCost.gap_pp_total, 2)} / α ${fmtPp(mCost.alpha_pp, 2)}`}
                    threshold="통과선: < 0.5 (비용이 알파 절반 미만)"
                />
            </div>

            {/* Footer */}
            <div style={{ fontSize: T.cap, color: C.textTertiary, textAlign: "center" }}>
                임계값 변경은 git 커밋으로 이력 · 결과 후 기준 조정 금지
            </div>
        </div>
    )
}

ValidationPanel.defaultProps = {
    dataUrl: DATA_URL,
    initialCash: INITIAL_CASH,
}

addPropertyControls(ValidationPanel, {
    dataUrl: {
        type: ControlType.String,
        title: "Portfolio URL",
        defaultValue: DATA_URL,
    },
    initialCash: {
        type: ControlType.Number,
        title: "Initial Cash",
        defaultValue: INITIAL_CASH,
        min: 1_000_000,
        max: 1_000_000_000,
        step: 1_000_000,
        displayStepper: true,
    },
})
