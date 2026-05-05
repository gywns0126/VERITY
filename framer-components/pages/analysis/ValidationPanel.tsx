import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useMemo, useRef, useState } from "react"

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


/* ──────────────────────────────────────────────────────────────
 * ◆ TERMS START ◆ (data/verity_terms.json 발췌 — VAMS 검증 패널 사용 항목)
 * ────────────────────────────────────────────────────────────── */
interface Term {
    label: string
    category?: "metric" | "grade" | "signal" | "concept" | "data_source" | "internal" | "time"
    definition: string
    l3?: boolean
}
const TERMS: Record<string, Term> = {
    VAMS: {
        label: "VAMS",
        category: "metric",
        definition:
            "Verity Account Management System — 가상 운영 누적 계좌. 시그널-결과 페어로 검증. raw_return / adjusted_return (거래세·스프레드·배당세 보정) 둘 다 트래킹.",
    },
    ALPHA: {
        label: "Alpha (초과수익)",
        category: "metric",
        definition:
            "벤치마크 대비 초과수익률 (% 또는 %p). 실질 alpha = VAMS 보정수익률 - KOSPI(또는 S&P) 누적수익률.",
    },
    MDD: {
        label: "MDD (Max Drawdown)",
        category: "metric",
        definition:
            "최대 낙폭 — 고점 대비 최저점 누적 손실률. VERITY UI 는 양수 magnitude 로 표시 (음수 부호 제거).",
    },
    WIN_RATE: {
        label: "Win Rate (승률)",
        category: "metric",
        definition:
            "수익 매매 / 전체 매매. VAMS 통과 임계 ≥ 55%.",
    },
    PROFIT_LOSS_RATIO: {
        label: "손익비",
        category: "metric",
        definition:
            "평균 수익 / 평균 손실. 통과 임계 ≥ 1.5 (수익이 손실의 1.5배 이상).",
    },
    SHARPE: {
        label: "Sharpe Ratio",
        category: "metric",
        definition:
            "위험조정 수익률. (수익률 - 무위험금리) / 표준편차. 연환산. ≥ 1.0 통과, < 0.5 재설계.",
    },
    REGIME: {
        label: "Regime (장세)",
        category: "metric",
        definition:
            "시장 국면 분류. bull (강세) / bear (약세) / range (횡보). regime별 fact_score 가중치 dynamic 조정 (bull→canslim_growth↑ / bear→graham_value↑).",
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
    const TIP_H = 160
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
                </div>
            )}
        </span>
    )
}
/* ◆ TERMTOOLTIP END ◆ */


const DATA_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json"
const INITIAL_CASH = 10_000_000

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
/** MDD/drawdown 등 항상 음수 magnitude 인 값 — 부호 제거하고 절댓값만 표시 */
function fmtPctAbs(n: number | null | undefined, digits = 2): string {
    if (n == null || !Number.isFinite(n)) return "—"
    return `${Math.abs(n).toFixed(digits)}%`
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
            display: "inline-flex", alignItems: "center", gap: 8,
            fontSize: size, fontWeight: T.w_bold, color: m.color,
            letterSpacing: 0.5, textTransform: "uppercase",
            ...MONO,
        }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: m.color, display: "inline-block" }} />
            {m.label}
        </span>
    )
}

/* ─────────── 비용 breakdown 한 줄 (펜타그램 톤) ─────────── */
function CostRow({ label, valuePp, note }: { label: string; valuePp: number | null; note?: string }) {
    return (
        <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "baseline",
            padding: `${S.xs}px 0`,
        }}>
            <span style={{ fontSize: T.cap, color: C.textTertiary, letterSpacing: 0.4, textTransform: "uppercase", fontWeight: T.w_med }}>
                {label}
                {note && <span style={{ color: C.textDisabled, fontSize: T.cap, marginLeft: S.sm, textTransform: "none", letterSpacing: 0 }}>{note}</span>}
            </span>
            <span style={{ fontSize: T.body, color: C.textSecondary, ...MONO }}>
                {valuePp != null ? fmtPp(valuePp) : "—"}
            </span>
        </div>
    )
}
function CostTotalRow({ label, valuePct, accent }: { label: string; valuePct: number | null; accent?: boolean }) {
    const color = accent ? C.textPrimary : (valuePct != null ? C.textSecondary : C.textTertiary)
    return (
        <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "baseline",
            padding: `${S.sm}px 0`,
        }}>
            <span style={{
                fontSize: T.cap, color: accent ? C.textPrimary : C.textTertiary,
                letterSpacing: 0.5, textTransform: "uppercase",
                fontWeight: accent ? T.w_bold : T.w_semi,
            }}>
                {label}
            </span>
            <span style={{
                fontSize: accent ? T.h2 : T.sub,
                fontWeight: accent ? T.w_bold : T.w_semi, color, ...MONO,
                letterSpacing: accent ? -0.3 : 0,
            }}>
                {fmtPct(valuePct)}
            </span>
        </div>
    )
}

/* ─────────── 메트릭 카드 — 펜타그램 톤 (dot indicator + 미니멀 column) ─────────── */
function MetricCard({
    title, pass, primary, secondary, threshold,
}: {
    title: React.ReactNode
    pass: boolean | null
    primary: string
    secondary?: string
    threshold?: string
}) {
    const [open, setOpen] = useState(false)
    // pass 도 accent green X — 한 화면 1색 강조 룰. pass 표시는 dot color 만.
    const dotColor = pass === true ? C.success : pass === false ? C.danger : C.textTertiary
    const primaryColor = pass === false ? C.textSecondary : C.textPrimary
    return (
        <div
            onClick={() => threshold && setOpen(!open)}
            style={{
                padding: `${S.sm}px 0`, display: "flex", flexDirection: "column", gap: S.xs,
                cursor: threshold ? "pointer" : "default",
                transition: "opacity 120ms ease",
            }}
        >
            <span style={{ display: "flex", alignItems: "center", gap: S.xs, fontSize: T.cap, color: C.textTertiary, fontWeight: T.w_med, letterSpacing: 0.5, textTransform: "uppercase" }}>
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: dotColor, display: "inline-block", flexShrink: 0 }} />
                {title}
            </span>
            <span style={{ fontSize: T.h2, fontWeight: T.w_bold, color: primaryColor, ...MONO, lineHeight: 1.1, letterSpacing: -0.3 }}>
                {primary}
            </span>
            {secondary && (
                <span style={{ fontSize: T.cap, color: C.textTertiary, ...MONO, letterSpacing: 0.3 }}>{secondary}</span>
            )}
            {open && threshold && (
                <span style={{ fontSize: T.cap, color: C.textTertiary, marginTop: S.xs, ...MONO, letterSpacing: 0.3, opacity: 0.8 }}>
                    {threshold}
                </span>
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
                    width: `${progressPct}%`, background: C.accent, boxShadow: "none",
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

/* ALPHA 비교 — 3-bar mini chart (펜타그램 #4 PROVIDE ORIENTATION + #5 ANNOTATIONS) */
function AlphaCompare({ vams, kospi, alpha }: { vams: number; kospi: number; alpha: number }) {
    const rows = [
        { label: "VAMS",  value: vams,  accent: false },
        { label: "KOSPI", value: kospi, accent: false },
        { label: "ALPHA", value: alpha, accent: true  },
    ]
    const max = Math.max(...rows.map(r => Math.abs(r.value)), 1)
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
            {rows.map((r) => {
                const pct = (Math.abs(r.value) / max) * 100
                const positive = r.value >= 0
                const color = r.accent ? C.accent : positive ? C.textPrimary : C.textSecondary
                return (
                    <div key={r.label} style={{ display: "flex", alignItems: "center", gap: S.md, height: 18 }}>
                        <span style={{ width: 52, fontSize: T.cap, color: C.textTertiary, letterSpacing: 0.4, textTransform: "uppercase", fontWeight: r.accent ? T.w_bold : T.w_med }}>
                            {r.label}
                        </span>
                        <div style={{ flex: 1, height: 2, position: "relative", background: C.border }}>
                            <div style={{
                                position: "absolute", left: 0, top: 0, height: "100%",
                                width: `${pct}%`, background: color,
                            }} />
                        </div>
                        <span style={{ minWidth: 64, textAlign: "right", fontSize: T.body, color, ...MONO, fontWeight: r.accent ? T.w_bold : T.w_med }}>
                            {fmtPp(r.value)}
                        </span>
                    </div>
                )
            })}
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
        <div style={{ fontFamily: FONT, background: C.bgPage, color: C.textSecondary, padding: 40, borderRadius: 16, textAlign: "center", fontSize: T.body }}>
            로딩 중…
        </div>
    )
    if (error) return (
        <div style={{ fontFamily: FONT, background: C.bgPage, color: C.danger, padding: S.xl, borderRadius: 16, textAlign: "center", fontSize: T.body }}>
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
            padding: S.xxl, borderRadius: 16,
            display: "flex", flexDirection: "column", gap: S.xxl,
            minWidth: 360,
        }}>
            {/* ── Header ── */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: S.md }}>
                <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                    <span style={{ fontSize: T.h1, fontWeight: T.w_bold, color: C.textPrimary, letterSpacing: -0.5 }}>
                        <TermTooltip termKey="VAMS">VAMS</TermTooltip> 검증
                    </span>
                    <span style={{ fontSize: T.cap, color: C.textTertiary }}>
                        {window.days ?? 0}일 · {window.snapshot_count ?? 0}스냅샷
                    </span>
                </div>
                <Badge verdict={overall} />
            </div>

            {/* ── Checkpoint bar (no card) ── */}
            <div style={{ display: "flex", flexDirection: "column", gap: S.md }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                    <span style={{ fontSize: T.cap, color: C.textTertiary, fontWeight: T.w_med, letterSpacing: 0.5, textTransform: "uppercase" }}>검증 진행도</span>
                    <span style={{ fontSize: T.body, color: C.textSecondary, ...MONO, letterSpacing: 0.3 }}>
                        <span style={{ color: C.textPrimary, fontWeight: T.w_bold }}>D+{daysPassed}</span>
                        {window.start && (
                            <span style={{ color: C.textTertiary }}> · since {window.start}</span>
                        )}
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

            {/* ── Cost Breakdown (no card) ── */}
            <div style={{ display: "flex", flexDirection: "column" }}>
                <span style={{ fontSize: T.cap, color: C.textTertiary, fontWeight: T.w_med, letterSpacing: 0.5, marginBottom: S.md, textTransform: "uppercase" }}>
                    보정 전/후 수익률
                </span>

                <CostTotalRow label="VAMS 원 수익률" valuePct={raw} />
                <CostRow label="거래세" valuePp={taxTotal} note={`실현 ${fmtPp(taxRealized, 3)} / 평가 ${fmtPp(taxUnrealized, 3)}`} />
                <CostRow label="호가 스프레드" valuePp={spreadTotal} note={`실현 ${fmtPp(spreadRealized, 3)} / 평가 ${fmtPp(spreadUnrealized, 3)}`} />
                <CostRow label="배당세" valuePp={dividendTax} note={(dividendTax ?? 0) === 0 ? "수집기 미구현" : undefined} />

                <div style={{ height: 1, background: C.border, margin: `${S.sm}px 0` }} />

                <CostTotalRow label="VAMS 보정 수익률" valuePct={adjusted} accent />
            </div>

            {/* ── ALPHA Spotlight (펜타그램 시안) ── */}
            <div style={{ display: "flex", flexDirection: "column", gap: S.lg }}>
                {/* 헤더: 작은 라벨 + 큰 숫자 (1색 강조) */}
                <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                    <span style={{ fontSize: T.cap, color: C.textTertiary, letterSpacing: 0.5, textTransform: "uppercase", fontWeight: T.w_semi }}>
                        <TermTooltip termKey="ALPHA">ALPHA</TermTooltip> · 실질 초과수익률
                    </span>
                    <span style={{
                        fontSize: 44, fontWeight: T.w_bold, ...MONO, lineHeight: 1, letterSpacing: -1,
                        color: alpha > 0 ? C.accent : alpha < 0 ? C.danger : C.textTertiary,
                    }}>
                        {fmtPp(alpha)}
                    </span>
                </div>

                {/* 3-bar 비교 — VAMS / KOSPI / ALPHA, ALPHA 만 accent */}
                <AlphaCompare vams={adjusted} kospi={benchRet} alpha={alpha} />

                {/* Annotation (Claude 톤, 사실 진술) */}
                <span style={{ fontSize: T.cap, color: C.textTertiary, ...MONO, letterSpacing: 0.3 }}>
                    N = {window.days ?? 0} / 365 days observed
                    {(window.days ?? 0) >= 90
                        ? " · 본판정 가능"
                        : ` · 본판정 D+${Math.max(0, 90 - (window.days ?? 0))} 후`}
                </span>
            </div>

            {/* ── Sample Checks (펜타그램 톤 — dot indicator + 미니멀) ── */}
            <div style={{ display: "flex", gap: S.xxl, fontSize: T.body }}>
                {[
                    { label: "최소 거래일", current: window.days ?? 0, required: sampleChecks.days_required ?? 60, ok: !!sampleChecks.days_ok },
                    { label: "최소 매매건", current: mWin.trades ?? 0, required: sampleChecks.trades_required ?? 20, ok: !!sampleChecks.trades_ok },
                ].map((s) => {
                    const dotColor = s.ok ? C.success : C.textTertiary
                    return (
                        <div key={s.label} style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                            <span style={{ display: "flex", alignItems: "center", gap: S.xs, fontSize: T.cap, color: C.textTertiary, fontWeight: T.w_med, letterSpacing: 0.5, textTransform: "uppercase" }}>
                                <span style={{ width: 6, height: 6, borderRadius: "50%", background: dotColor, display: "inline-block" }} />
                                {s.label}
                            </span>
                            <span style={{ ...MONO, color: C.textPrimary, fontWeight: T.w_bold, fontSize: T.sub, letterSpacing: -0.2 }}>
                                {s.current} <span style={{ color: C.textTertiary, fontWeight: T.w_reg, fontSize: T.cap }}>/ {s.required}</span>
                            </span>
                        </div>
                    )
                })}
            </div>

            {/* ── 지표 그리드 (7개) — 카드 탭하면 통과선 표시 ── */}
            <div style={{ display: "flex", flexDirection: "column", gap: S.md }}>
                <span style={{ fontSize: T.cap, color: C.textTertiary, fontWeight: T.w_med, letterSpacing: 0.5, textTransform: "uppercase" }}>
                    지표 <span style={{ color: C.textDisabled, letterSpacing: 0.3 }}>· 탭하면 통과선</span>
                </span>
                <div style={{
                    display: "grid", gap: S.md,
                    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                }}>
                <MetricCard
                    title="누적 수익률 (보정)"
                    pass={mRet.pass ?? null}
                    primary={fmtPp(mRet.excess_pp)}
                    secondary={`VAMS ${fmtPct(mRet.vams_return_pct)} · 벤치 ${fmtPct(mRet.benchmark_return_pct)}`}
                    threshold={`통과선: 벤치 대비 ≥ ${thresholds.excess_return_pp_min ?? 0}%p`}
                />
                <MetricCard
                    title={<><TermTooltip termKey="MDD">MDD</TermTooltip> 비율</>}
                    pass={mMdd.pass ?? null}
                    primary={fmtRatio(mMdd.ratio)}
                    secondary={`VAMS ${fmtPctAbs(mMdd.vams_mdd_pct)} · 벤치 ${fmtPctAbs(mMdd.benchmark_mdd_pct)}`}
                    threshold={`통과선: ≤ ${thresholds.mdd_ratio_max ?? 1.0}`}
                />
                <MetricCard
                    title={<TermTooltip termKey="WIN_RATE">승률</TermTooltip>}
                    pass={mWin.pass ?? null}
                    primary={mWin.win_rate != null ? `${(mWin.win_rate * 100).toFixed(1)}%` : "—"}
                    secondary={`${mWin.wins ?? 0}승 ${mWin.losses ?? 0}패 (${mWin.trades ?? 0}건)`}
                    threshold={`통과선: ≥ ${((thresholds.win_rate_min ?? 0.55) * 100).toFixed(0)}%`}
                />
                <MetricCard
                    title={<TermTooltip termKey="PROFIT_LOSS_RATIO">손익비</TermTooltip>}
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
                    title={<><TermTooltip termKey="SHARPE">샤프</TermTooltip> (연율)</>}
                    pass={mSharpe.pass ?? null}
                    primary={fmtRatio(mSharpe.annualized)}
                    secondary={mSharpe.verdict ? `verdict: ${mSharpe.verdict}` : undefined}
                    threshold={`≥ ${thresholds.sharpe_min ?? 1.0} 통과 · < ${thresholds.sharpe_redesign_below ?? 0.5} 재설계`}
                />
                <MetricCard
                    title={<><TermTooltip termKey="REGIME">레짐</TermTooltip> 커버</>}
                    pass={mRegime.pass ?? null}
                    primary={mRegime.covered ? "covered" : "not yet"}
                    secondary={`벤치 MDD ${fmtPctAbs(mRegime.peak_drawdown_pct)}`}
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
