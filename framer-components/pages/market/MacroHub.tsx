import { addPropertyControls, ControlType } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * MacroHub — 매크로 통합 (Step 8, Macro 8→1, 가장 위험 cluster)
 *
 * 통합 출처 (4 → 1):
 *   - MacroPanel (550) — Brain mood + diagnosis + macro_override
 *   - MacroSentimentPanel (498) — F&G + COT + P/C + 펀드플로우
 *   - YieldCurvePanel (229) — 채권 수익률 곡선
 *   - CapitalFlowRadar (428) — 섹터 자본 흐름 + 원자재
 *
 * 폐기 (DEPRECATED, 같은 step):
 *   - SentimentPanel (330) — 종목별 X sentiment, StockDetailPanel 흡수
 *   - GlobalMarketsPanel (1,001) — 다른 컴포넌트와 중복
 *   - USCapitalFlowRadar (379) — Brain flow_score 에 이미 반영
 *
 * 별도 유지:
 *   - CryptoMacroSensor (619) — 자산군 분리 (코인 거래 시)
 *
 * 구조: 외곽 1개 + 메인 탭 4개 (Mood / Sentiment / Yield / Flow) + KR/US toggle
 * 데이터: portfolio.json (macro / market_fear_greed / cftc_cot / fund_flows /
 *         cboe_pcr / sectors / sector_rotation)
 *
 * 모던 심플 6원칙 + feedback_no_hardcode_position 적용.
 *
 * NOTE: 통합 분량 큰 cluster — 각 view 는 hero 영역만 박음. 세부 그래프
 * 일부 단순화 (drift drilldown 등은 v2 cycle 에서 보강).
 */

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "rgba(255,255,255,0.06)", borderStrong: "rgba(255,255,255,0.10)", borderHover: "#7fffa0",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#7fffa0", accentSoft: "rgba(127, 255, 160,0.12)",
    strongBuy: "#22C55E", buy: "#2DD4BF", watch: "#FFD600", caution: "#F59E0B", avoid: "#EF4444",
    up: "#F04452", down: "#3182F6",
    info: "#5BA9FF", success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const G = {
    accent: "0 0 8px rgba(127, 255, 160,0.35)",
    success: "0 0 6px rgba(34,197,94,0.30)",
    warn: "0 0 6px rgba(245,158,11,0.30)",
    danger: "0 0 6px rgba(239,68,68,0.30)",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_normal: 1.5, lh_loose: 1.7,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/* ──────────────────────────────────────────────────────────────
 * ◆ TERMS START ◆
 * ────────────────────────────────────────────────────────────── */
interface Term { label: string; definition: string; l3?: boolean }
const TERMS: Record<string, Term> = {
    MARKET_MOOD: {
        label: "Market Mood (O₂ score)",
        definition: "VERITY 자체 산출 시장 분위기 (0~100). HIGH/NORMAL/LOW/HYPOXIA/CRITICAL 5단계.",
        l3: true,
    },
    VIX: {
        label: "VIX (변동성 지수)",
        definition: "S&P 500 옵션 implied volatility. > 25 위험, < 18 안정.",
    },
    REGIME: {
        label: "Regime (장세)",
        definition: "시장 국면 분류. bull / bear / range. fact_score 가중치 dynamic 조정.",
    },
    FNG: {
        label: "Fear & Greed Index",
        definition: "CNN F&G 0~100. 0 극도공포, 100 극도탐욕. 시장 sentiment 종합.",
    },
    COT: {
        label: "CFTC COT (선물 포지션)",
        definition: "Commitments of Traders. 비상업 longs 비율로 선물 시장 sentiment 측정.",
    },
    PCR: {
        label: "Put/Call Ratio (P/C)",
        definition: "CBOE P/C ratio. > 1.0 풋 우세 (공포), < 0.7 콜 우세 (탐욕).",
    },
    YIELD_SPREAD: {
        label: "Yield Spread (금리차)",
        definition: "10Y - 2Y 또는 10Y - 3M 스프레드. 음수 = inverted = 침체 선행 신호.",
    },
    REAL_YIELD: {
        label: "Real Yield (실질금리)",
        definition: "미 10Y 명목금리 − 10Y 기대인플레이션(BEI). 금/은의 가장 강한 매크로 드라이버. 하락 = 금 친화.",
    },
    GOLD_SILVER_RATIO: {
        label: "Gold/Silver Ratio",
        definition: "금 가격 ÷ 은 가격. 역사적 평균 ~70. 90+ 은 상대 저평가, 60- 은 상대 고평가 통상 해석.",
    },
}
/* ◆ TERMS END ◆ */


/* ──────────────────────────────────────────────────────────────
 * ◆ TERMTOOLTIP START ◆
 * ────────────────────────────────────────────────────────────── */
function TermTooltip({ termKey, children }: { termKey: string; children: React.ReactNode }) {
    const [show, setShow] = useState(false)
    const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
    const anchorRef = useRef<HTMLSpanElement>(null)
    const term = TERMS[termKey]
    if (!term) return <>{children}</>
    const TIP_W = 320, TIP_H = 160
    const handleEnter = () => {
        const el = anchorRef.current
        if (!el || typeof window === "undefined") { setShow(true); return }
        const rect = el.getBoundingClientRect()
        const vw = window.innerWidth, vh = window.innerHeight
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
            onMouseEnter={handleEnter} onMouseLeave={handleLeave}
            onFocus={handleEnter} onBlur={handleLeave}
            tabIndex={0}
            style={{
                position: "relative", display: "inline-block",
                
                cursor: "help", outline: "none",
            }}
        >
            {children}
            {show && pos && (
                <div style={{
                    position: "fixed", top: pos.top, left: pos.left,
                    width: TIP_W, zIndex: 100,
                    padding: "10px 12px", borderRadius: R.md,
                    background: C.bgElevated, 
                    boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                    fontFamily: FONT, fontSize: 12, lineHeight: 1.5,
                    whiteSpace: "normal", pointerEvents: "none",
                }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                        <span style={{ color: C.textPrimary, fontWeight: T.w_bold, fontSize: 13 }}>{term.label}</span>
                        {term.l3 && (
                            <span style={{
                                color: C.accent, fontSize: 9, letterSpacing: 1.5, fontWeight: T.w_black,
                                textTransform: "uppercase", padding: "1px 6px", borderRadius: R.pill,
                                
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


/* ─────────── 색 매핑 ─────────── */
function moodColor(score: number): string {
    if (score >= 70) return C.success
    if (score >= 55) return C.success
    if (score >= 40) return C.warn
    if (score >= 25) return C.warn
    return C.danger
}

function moodLabel(score: number): string {
    if (score >= 70) return "HIGH"
    if (score >= 55) return "NORMAL"
    if (score >= 40) return "LOW"
    if (score >= 25) return "HYPOXIA"
    return "CRITICAL"
}

function fngColor(value: number, signal?: string): string {
    if (signal === "extreme_fear") return C.danger
    if (signal === "fear") return C.warn
    if (signal === "greed") return C.warn
    if (signal === "extreme_greed") return C.danger
    return C.success
}

function pctColor(n: number | null | undefined): string {
    if (n == null || !Number.isFinite(n)) return C.textTertiary
    if (n > 0) return C.success
    if (n < 0) return C.danger
    return C.textTertiary
}

function fmtPct(n: number | null | undefined, digits = 2): string {
    if (n == null || !Number.isFinite(n)) return "—"
    const sign = n > 0 ? "+" : ""
    return `${sign}${n.toFixed(digits)}%`
}

function fmtNum(n: number | null | undefined): string {
    if (n == null || !Number.isFinite(n)) return "—"
    return n.toLocaleString()
}


/* ═══════════════════════════ 메인 ═══════════════════════════ */

type Tab = "mood" | "sentiment" | "yield" | "flow" | "commodities"

interface Props {
    dataUrl: string
    market: "kr" | "us"
}

export default function MacroHub(props: Props) {
    const { dataUrl } = props
    const isUS = props.market === "us"
    const [data, setData] = useState<any>(null)
    const [tab, setTab] = useState<Tab>("mood")

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal).then((d) => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    if (!data) {
        return (
            <div style={shell}>
                <div style={loadingBox}>
                    <span style={{ color: C.textTertiary, fontSize: T.body }}>매크로 로딩 중…</span>
                </div>
            </div>
        )
    }

    return (
        <div style={shell}>
            {/* Header */}
            <div style={headerRow}>
                <div style={headerLeft}>
                    <span style={titleStyle}>매크로</span>
                    <span style={metaStyle}>
                        {isUS ? "US 시장" : "KR 시장"} · Mood · Sentiment · Yield · Flow · Commodities
                    </span>
                </div>
            </div>

            {/* Main tab */}
            <div style={tabRow}>
                <TabButton label="Mood" active={tab === "mood"} onClick={() => setTab("mood")} />
                <TabButton label="Sentiment" active={tab === "sentiment"} onClick={() => setTab("sentiment")} />
                <TabButton label="Yield" active={tab === "yield"} onClick={() => setTab("yield")} />
                <TabButton label="Flow" active={tab === "flow"} onClick={() => setTab("flow")} />
                <TabButton label="Commodities" active={tab === "commodities"} onClick={() => setTab("commodities")} />
            </div>

            <div style={hr} />

            {tab === "mood" && <MoodView data={data} isUS={isUS} />}
            {tab === "sentiment" && <SentimentView data={data} />}
            {tab === "yield" && <YieldView data={data} />}
            {tab === "flow" && <FlowView data={data} isUS={isUS} />}
            {tab === "commodities" && <CommoditiesView data={data} />}
        </div>
    )
}


/* ─────────── Mood view (MacroPanel 핵심) ─────────── */
function MoodView({ data, isUS }: { data: any; isUS: boolean }) {
    const macro = data?.macro || {}
    const mood = isUS
        ? (macro.market_mood_us || macro.market_mood || {})
        : (macro.market_mood || {})
    const diags = isUS
        ? (macro.macro_diagnosis_us || macro.macro_diagnosis || [])
        : (macro.macro_diagnosis || [])
    const brain: any = data?.verity_brain || {}
    const macroOv: any = brain?.macro_override || data?.macro_override || {}
    const overrideMode = macroOv?.mode

    const score = mood.score ?? 50
    const mC = moodColor(score)
    const mLabel = moodLabel(score)

    const vix = macro.vix?.value
    const us10y = macro.us_10y?.value
    const usdKrw = macro.usd_krw?.value

    return (
        <>
            {/* Hero: O₂ score */}
            <div style={heroBlock}>
                <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                    <span style={sectionCap}>
                        <TermTooltip termKey="MARKET_MOOD">시장 분위기</TermTooltip>
                    </span>
                    <div style={{ display: "flex", alignItems: "baseline", gap: S.md }}>
                        <span style={{ ...MONO, color: mC, fontSize: T.h1, fontWeight: T.w_black, lineHeight: 1 }}>
                            {score}
                        </span>
                        <span style={{ color: mC, fontSize: T.body, fontWeight: T.w_bold, letterSpacing: 0.5 }}>
                            {mLabel}
                        </span>
                        {mood.label && (
                            <span style={{ color: C.textSecondary, fontSize: T.body }}>
                                {mood.label}
                            </span>
                        )}
                    </div>
                    {/* progress bar */}
                    <div style={{ width: "100%", height: 4, background: C.bgElevated, borderRadius: 2, overflow: "hidden" }}>
                        <div style={{
                            width: `${score}%`, height: "100%",
                            background: mC, transition: "width 0.6s ease",
                        }} />
                    </div>
                </div>

                {/* macro chips */}
                <div style={{ display: "flex", gap: S.md, flexWrap: "wrap", marginTop: S.md }}>
                    {vix != null && (
                        <ChipMetric
                            label={<TermTooltip termKey="VIX">VIX</TermTooltip>}
                            value={fmtNum(vix)}
                            color={vix > 25 ? C.danger : vix < 18 ? C.success : C.warn}
                        />
                    )}
                    {us10y != null && (
                        <ChipMetric label="미 10Y" value={`${us10y.toFixed(2)}%`} />
                    )}
                    {!isUS && usdKrw != null && (
                        <ChipMetric label="USD/KRW" value={fmtNum(usdKrw)} />
                    )}
                    {macro.yield_spread?.value != null && (
                        <ChipMetric
                            label={<TermTooltip termKey="YIELD_SPREAD">금리차</TermTooltip>}
                            value={`${macro.yield_spread.value.toFixed(2)}%p`}
                            color={pctColor(macro.yield_spread.value)}
                        />
                    )}
                </div>
            </div>

            {/* Macro override warning */}
            {overrideMode && (
                <>
                    <div style={hr} />
                    <div style={overrideBox}>
                        <div style={{ display: "flex", alignItems: "center", gap: S.sm }}>
                            <span style={{
                                width: 6, height: 6, borderRadius: "50%",
                                background: C.warn, boxShadow: "none",
                            }} />
                            <span style={{
                                color: C.warn, fontSize: T.cap, fontWeight: T.w_bold,
                                letterSpacing: 1, textTransform: "uppercase",
                            }}>
                                매크로 오버라이드 — {overrideMode}
                            </span>
                            {macroOv.max_grade && (
                                <span style={{ color: C.danger, fontSize: T.cap, fontWeight: T.w_semi }}>
                                    cap → {macroOv.max_grade}
                                </span>
                            )}
                        </div>
                        {macroOv.message && (
                            <div style={{ color: C.textPrimary, fontSize: T.body, lineHeight: T.lh_normal, marginTop: S.xs }}>
                                {String(macroOv.message).slice(0, 200)}
                            </div>
                        )}
                        {Array.isArray(macroOv.secondary_signals) && macroOv.secondary_signals.length > 0 && (
                            <div style={{ display: "flex", flexWrap: "wrap", gap: S.xs, marginTop: S.sm }}>
                                {macroOv.secondary_signals.map((sig: any, i: number) => (
                                    <span key={i} style={{
                                        background: C.bgElevated,
                                        color: C.textSecondary,
                                        fontSize: T.cap, fontWeight: T.w_med,
                                        padding: `${S.xs}px ${S.sm}px`,
                                        borderRadius: R.sm,
                                        display: "inline-flex", alignItems: "center", gap: S.xs,
                                    }}>
                                        <span style={{ color: C.warn, fontSize: T.cap, fontWeight: T.w_bold }}>+</span>
                                        {sig.label || sig.mode}
                                        {sig.max_grade && (
                                            <span style={{ color: C.textTertiary, fontSize: T.cap }}>
                                                ({sig.max_grade})
                                            </span>
                                        )}
                                    </span>
                                ))}
                            </div>
                        )}
                    </div>
                </>
            )}

            {/* Market Horizon — 자체 산식 V2.1 (가설 검증 진행 중) */}
            {(() => {
                const mh: any = data?.market_horizon || {}
                if (!mh.cycle_stage) return null
                const cycleLabel = mh.cycle_stage_label_ko || mh.cycle_stage
                const capeV = mh.cape_value
                const capeP = mh.cape_percentile
                const recProb = mh.recession_prob_12m
                const h12 = mh.horizons?.["12m"]?.median
                const stageColor =
                    mh.cycle_stage === "euphoria" || mh.cycle_stage === "late_cycle" ? C.warn
                  : mh.cycle_stage === "panic" || mh.cycle_stage === "capitulation" ? C.danger
                  : mh.cycle_stage === "recovery" || mh.cycle_stage === "expansion" ? C.success
                  : C.textSecondary
                return (
                    <>
                        <div style={hr} />
                        <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                            <span style={sectionCap}>
                                시장 사이클 — 자체 산식 V2.1 (가설 검증 진행 중)
                            </span>
                            <div style={{ display: "flex", alignItems: "baseline", gap: S.md, flexWrap: "wrap" }}>
                                <span style={{ ...MONO, color: stageColor, fontSize: T.h2, fontWeight: T.w_black }}>
                                    {cycleLabel}
                                </span>
                            </div>
                            <div style={{ display: "flex", gap: S.md, flexWrap: "wrap", marginTop: S.xs }}>
                                {capeP != null && (
                                    <ChipMetric
                                        label="CAPE %ile"
                                        value={`${capeP}%`}
                                        color={capeP > 90 ? C.warn : capeP < 20 ? C.success : C.textSecondary}
                                    />
                                )}
                                {capeV != null && (
                                    <ChipMetric label="CAPE" value={Number(capeV).toFixed(1)} />
                                )}
                                {recProb != null && (
                                    <ChipMetric
                                        label="12M 침체확률"
                                        value={`${(Number(recProb) * 100).toFixed(0)}%`}
                                        color={Number(recProb) >= 0.3 ? C.danger : Number(recProb) >= 0.15 ? C.warn : C.success}
                                    />
                                )}
                                {h12 != null && (
                                    <ChipMetric
                                        label="12M 예상 (median)"
                                        value={`${(Number(h12) * 100).toFixed(0)}%`}
                                        color={Number(h12) < 0 ? C.danger : C.success}
                                    />
                                )}
                            </div>
                        </div>
                    </>
                )
            })()}

            {/* Diagnosis list */}
            {diags.length > 0 && (
                <>
                    <div style={hr} />
                    <div style={{ display: "flex", flexDirection: "column", gap: S.sm }}>
                        <span style={sectionCap}>진단</span>
                        {diags.slice(0, 6).map((d: any, i: number) => {
                            const dKind = (d.kind || d.type || "info").toLowerCase()
                            const dColor = dKind.includes("danger") || dKind.includes("crit") ? C.danger
                                : dKind.includes("warn") ? C.warn
                                : dKind.includes("success") ? C.success
                                : C.textSecondary
                            return (
                                <div key={i} style={{ display: "flex", gap: S.sm, alignItems: "flex-start" }}>
                                    <span style={{
                                        width: 4, height: 4, borderRadius: "50%",
                                        background: dColor, marginTop: 7, flexShrink: 0,
                                    }} />
                                    <span style={{ color: C.textPrimary, fontSize: T.cap, lineHeight: T.lh_normal }}>
                                        {d.message || d.text || JSON.stringify(d).slice(0, 120)}
                                    </span>
                                </div>
                            )
                        })}
                    </div>
                </>
            )}
        </>
    )
}


/* ─────────── Sentiment view (MacroSentimentPanel 핵심) ─────────── */
function SentimentView({ data }: { data: any }) {
    const fng = data?.market_fear_greed || {}
    const cot = data?.cftc_cot || {}
    const flow = data?.fund_flows || {}
    const pcr = data?.cboe_pcr || {}

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.lg }}>
            {/* F&G */}
            {fng.ok && fng.value != null && (
                <div style={blockStyle}>
                    <div style={{ display: "flex", alignItems: "center", gap: S.lg }}>
                        <div style={{
                            width: 64, height: 64, borderRadius: "50%",
                            border: `3px solid ${fngColor(fng.value, fng.signal)}`,
                            display: "flex", flexDirection: "column",
                            alignItems: "center", justifyContent: "center",
                            flexShrink: 0,
                        }}>
                            <span style={{ ...MONO, color: C.textPrimary, fontSize: T.title, fontWeight: T.w_black, lineHeight: 1 }}>
                                {fng.value}
                            </span>
                            <span style={{ ...MONO, color: C.textTertiary, fontSize: 9 }}>
                                /100
                            </span>
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: S.xs, flex: 1, minWidth: 0 }}>
                            <span style={sectionCap}>
                                <TermTooltip termKey="FNG">CNN Fear &amp; Greed</TermTooltip>
                            </span>
                            <span style={{ color: fngColor(fng.value, fng.signal), fontSize: T.body, fontWeight: T.w_bold }}>
                                {(fng.signal || "").toUpperCase().replace(/_/g, " ") || "—"}
                            </span>
                            {fng.description_kr && (
                                <span style={{ color: C.textSecondary, fontSize: T.cap, lineHeight: T.lh_normal }}>
                                    {fng.description_kr}
                                </span>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* COT */}
            {cot.ok && (
                <div style={blockStyle}>
                    <span style={sectionCap}>
                        <TermTooltip termKey="COT">CFTC COT</TermTooltip>
                    </span>
                    <div style={{ display: "flex", gap: S.md, marginTop: S.sm, flexWrap: "wrap" }}>
                        {cot.assets && Object.entries(cot.assets).slice(0, 4).map(([asset, info]: [string, any]) => (
                            <ChipMetric
                                key={asset}
                                label={asset}
                                value={info.noncomm_long_pct != null ? `${info.noncomm_long_pct.toFixed(0)}%` : "—"}
                                color={info.noncomm_long_pct > 60 ? C.success : info.noncomm_long_pct < 40 ? C.danger : C.warn}
                            />
                        ))}
                    </div>
                </div>
            )}

            {/* P/C */}
            {pcr.ok && pcr.value != null && (
                <div style={blockStyle}>
                    <span style={sectionCap}>
                        <TermTooltip termKey="PCR">Put / Call Ratio</TermTooltip>
                    </span>
                    <div style={{ display: "flex", alignItems: "baseline", gap: S.sm, marginTop: S.xs }}>
                        <span style={{ ...MONO, color: C.textPrimary, fontSize: T.title, fontWeight: T.w_bold }}>
                            {pcr.value.toFixed(2)}
                        </span>
                        <span style={{ color: pcr.value > 1.0 ? C.danger : pcr.value < 0.7 ? C.warn : C.success, fontSize: T.cap, fontWeight: T.w_semi }}>
                            {pcr.value > 1.0 ? "공포 우세" : pcr.value < 0.7 ? "탐욕 우세" : "중립"}
                        </span>
                    </div>
                </div>
            )}

            {/* Fund flows */}
            {flow.ok && (flow.equity_flow_pct != null || flow.bond_flow_pct != null) && (
                <div style={blockStyle}>
                    <span style={sectionCap}>펀드 플로우</span>
                    <div style={{ display: "flex", gap: S.md, marginTop: S.sm, flexWrap: "wrap" }}>
                        {flow.equity_flow_pct != null && (
                            <ChipMetric
                                label="주식형"
                                value={fmtPct(flow.equity_flow_pct)}
                                color={pctColor(flow.equity_flow_pct)}
                            />
                        )}
                        {flow.bond_flow_pct != null && (
                            <ChipMetric
                                label="채권형"
                                value={fmtPct(flow.bond_flow_pct)}
                                color={pctColor(flow.bond_flow_pct)}
                            />
                        )}
                    </div>
                </div>
            )}

            {!fng.ok && !cot.ok && !pcr.ok && !flow.ok && (
                <div style={emptyBox}>
                    <span style={{ color: C.textTertiary, fontSize: T.body }}>
                        sentiment 데이터 없음
                    </span>
                </div>
            )}
        </div>
    )
}


/* ─────────── Yield view (YieldCurvePanel 핵심) ─────────── */
function YieldView({ data }: { data: any }) {
    const macro = data?.macro || {}
    const us10y = macro.us_10y?.value
    const us2y = macro.us_2y?.value
    const us3m = macro.us_3m?.value
    const spread2y10y = us10y != null && us2y != null ? us10y - us2y : null
    const spread3m10y = us10y != null && us3m != null ? us10y - us3m : null
    const isInverted = spread2y10y != null && spread2y10y < 0

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.lg }}>
            {/* Yields */}
            <div style={{ display: "flex", gap: S.md, flexWrap: "wrap" }}>
                {us3m != null && <YieldChip label="3M" value={us3m} />}
                {us2y != null && <YieldChip label="2Y" value={us2y} />}
                {us10y != null && <YieldChip label="10Y" value={us10y} />}
            </div>

            <div style={hr} />

            {/* Spreads */}
            <div style={{ display: "flex", flexDirection: "column", gap: S.sm }}>
                <span style={sectionCap}>
                    <TermTooltip termKey="YIELD_SPREAD">금리차 (Spread)</TermTooltip>
                </span>
                <div style={{ display: "flex", gap: S.md, flexWrap: "wrap" }}>
                    {spread2y10y != null && (
                        <SpreadChip label="2Y → 10Y" bps={spread2y10y * 100} />
                    )}
                    {spread3m10y != null && (
                        <SpreadChip label="3M → 10Y" bps={spread3m10y * 100} />
                    )}
                </div>
            </div>

            {/* Inversion warning */}
            {isInverted && (
                <div style={{
                    background: "transparent",
                    borderRadius: R.md,
                    padding: `${S.md}px ${S.lg}px`,
                    display: "flex", flexDirection: "column", gap: S.xs,
                }}>
                    <div style={{ display: "flex", alignItems: "center", gap: S.sm }}>
                        <span style={{
                            width: 6, height: 6, borderRadius: "50%",
                            background: C.danger, boxShadow: "none",
                        }} />
                        <span style={{ color: C.danger, fontSize: T.cap, fontWeight: T.w_bold, letterSpacing: 1, textTransform: "uppercase" }}>
                            Yield Curve Inverted
                        </span>
                    </div>
                    <span style={{ color: C.textPrimary, fontSize: T.body, lineHeight: T.lh_normal }}>
                        2Y &gt; 10Y — 침체 선행 신호. Brain 보수 진입 권고 가능.
                    </span>
                </div>
            )}

            {us10y == null && us2y == null && us3m == null && (
                <div style={emptyBox}>
                    <span style={{ color: C.textTertiary, fontSize: T.body }}>yield 데이터 없음</span>
                </div>
            )}
        </div>
    )
}


/* ─────────── Flow view (CapitalFlowRadar 핵심) ─────────── */
function FlowView({ data, isUS }: { data: any; isUS: boolean }) {
    const macro = data?.macro || {}
    const flow = macro.capital_flow || {}
    const sectors: any[] = data?.sectors || []
    const filtered = sectors.filter((s: any) =>
        isUS ? (s.market || "").toUpperCase() === "US" : (s.market || "").toUpperCase() !== "US"
    )

    /* 섹터 변화율 정렬 */
    const sorted = [...filtered].sort((a, b) => (b.change_pct ?? 0) - (a.change_pct ?? 0))
    const top3 = sorted.slice(0, 3)
    const bottom3 = sorted.slice(-3).reverse()

    /* 원자재 + 국채 */
    const commodities = ["gold", "silver", "copper", "wti_oil"] as const
    const bonds = ["us_10y", "us_2y"] as const

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.lg }}>
            {/* 섹터 자본 흐름 (Top3 / Bottom3) */}
            {filtered.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: S.md }}>
                    <span style={sectionCap}>섹터 자본 흐름</span>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: S.lg }}>
                        <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                            <span style={{ color: C.success, fontSize: T.cap, fontWeight: T.w_semi }}>유입</span>
                            {top3.map((s: any, i: number) => (
                                <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                                    <span style={{ color: C.textPrimary, fontSize: T.cap }}>{s.name}</span>
                                    <span style={{ ...MONO, color: pctColor(s.change_pct), fontSize: T.cap, fontWeight: T.w_semi }}>
                                        {fmtPct(s.change_pct ?? 0)}
                                    </span>
                                </div>
                            ))}
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                            <span style={{ color: C.danger, fontSize: T.cap, fontWeight: T.w_semi }}>유출</span>
                            {bottom3.map((s: any, i: number) => (
                                <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                                    <span style={{ color: C.textPrimary, fontSize: T.cap }}>{s.name}</span>
                                    <span style={{ ...MONO, color: pctColor(s.change_pct), fontSize: T.cap, fontWeight: T.w_semi }}>
                                        {fmtPct(s.change_pct ?? 0)}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            )}

            <div style={hr} />

            {/* 원자재 */}
            <div style={{ display: "flex", flexDirection: "column", gap: S.sm }}>
                <span style={sectionCap}>원자재</span>
                <div style={{ display: "flex", gap: S.md, flexWrap: "wrap" }}>
                    {commodities.map((key) => {
                        const v = (macro as any)[key]
                        if (!v?.value) return null
                        const labels: Record<string, string> = {
                            gold: "금", silver: "은", copper: "구리", wti_oil: "원유",
                        }
                        return (
                            <ChipMetric
                                key={key}
                                label={labels[key]}
                                value={`$${v.value.toLocaleString()}`}
                                color={pctColor(v.change_pct)}
                            />
                        )
                    })}
                </div>
            </div>

            {/* 채권 */}
            <div style={{ display: "flex", flexDirection: "column", gap: S.sm }}>
                <span style={sectionCap}>채권 수익률</span>
                <div style={{ display: "flex", gap: S.md, flexWrap: "wrap" }}>
                    {bonds.map((key) => {
                        const v = (macro as any)[key]
                        if (!v?.value) return null
                        const labels: Record<string, string> = {
                            us_10y: "미 10Y", us_2y: "미 2Y",
                        }
                        return (
                            <ChipMetric
                                key={key}
                                label={labels[key]}
                                value={`${v.value.toFixed(2)}%`}
                            />
                        )
                    })}
                </div>
            </div>

            {/* Capital flow narrative (있으면) */}
            {flow.narrative && (
                <>
                    <div style={hr} />
                    <div style={{ color: C.textSecondary, fontSize: T.cap, lineHeight: T.lh_loose }}>
                        {flow.narrative}
                    </div>
                </>
            )}
        </div>
    )
}


/* ─────────── Commodities view (금·은 정밀) ─────────── */
function CommoditiesView({ data }: { data: any }) {
    const macro = data?.macro || {}
    const gold = macro.gold || {}
    const silver = macro.silver || {}
    const copper = macro.copper || {}
    const wti = macro.wti_oil || {}
    const us10y = macro.us_10y?.value
    const bei = macro.breakeven_inflation_10y?.value
    const usdKrw = macro.usd_krw

    const realYield = (us10y != null && bei != null) ? us10y - bei : null
    const gsRatio = (gold.value != null && silver.value != null && silver.value > 0)
        ? gold.value / silver.value
        : null

    /* 금 친화 narrative — 실질금리 ↓ + 달러 ↓ → bullish 금. 둘 다 ↑ → bearish. */
    let narrative: string | null = null
    if (realYield != null && usdKrw?.change_pct != null && gold?.change_pct != null) {
        const realFalling = realYield < 1.5
        const dollarFalling = usdKrw.change_pct < 0
        if (realFalling && dollarFalling) {
            narrative = "실질금리 둔화 + 달러 약세 — 금 매크로 동조. 강세 지속 가능성."
        } else if (!realFalling && !dollarFalling) {
            narrative = "실질금리 부담 + 달러 강세 — 금에 역풍. 단기 조정 가능."
        } else {
            narrative = "매크로 신호 혼재 — 단일 방향 베팅 자제, 금/은 비중 조절."
        }
    }

    if (gold.value == null && silver.value == null) {
        return (
            <div style={emptyBox}>
                <span style={{ color: C.textTertiary, fontSize: T.body }}>commodities 데이터 없음</span>
            </div>
        )
    }

    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.lg }}>
            {/* Hero — 금 */}
            {gold.value != null && (
                <CommodityHero
                    label="금 (Gold)"
                    unit="$"
                    value={gold.value}
                    changePct={gold.change_pct}
                    sparkline={gold.sparkline}
                    high30d={gold.high_30d}
                    low30d={gold.low_30d}
                />
            )}

            {/* Hero — 은 */}
            {silver.value != null && (
                <CommodityHero
                    label="은 (Silver)"
                    unit="$"
                    value={silver.value}
                    changePct={silver.change_pct}
                    sparkline={silver.sparkline}
                    high30d={silver.high_30d}
                    low30d={silver.low_30d}
                />
            )}

            <div style={hr} />

            {/* Macro drivers */}
            <div style={{ display: "flex", flexDirection: "column", gap: S.sm }}>
                <span style={sectionCap}>매크로 드라이버</span>
                <div style={{ display: "flex", gap: S.lg, flexWrap: "wrap" }}>
                    {realYield != null && (
                        <ChipMetric
                            label={<TermTooltip termKey="REAL_YIELD">실질금리(10Y)</TermTooltip>}
                            value={`${realYield.toFixed(2)}%`}
                            color={realYield < 1 ? C.success : realYield > 2 ? C.danger : C.textPrimary}
                        />
                    )}
                    {usdKrw?.value != null && (
                        <ChipMetric
                            label="USD/KRW"
                            value={`${usdKrw.value.toLocaleString()} (${fmtPct(usdKrw.change_pct ?? 0)})`}
                            color={pctColor(usdKrw.change_pct != null ? -usdKrw.change_pct : 0)}
                        />
                    )}
                    {copper.value != null && (
                        <ChipMetric
                            label="구리"
                            value={`$${copper.value.toLocaleString()} (${fmtPct(copper.change_pct ?? 0)})`}
                            color={pctColor(copper.change_pct)}
                        />
                    )}
                    {wti.value != null && (
                        <ChipMetric
                            label="원유 (WTI)"
                            value={`$${wti.value.toLocaleString()} (${fmtPct(wti.change_pct ?? 0)})`}
                            color={pctColor(wti.change_pct)}
                        />
                    )}
                </div>
            </div>

            {/* Gold/Silver Ratio */}
            {gsRatio != null && (
                <div style={{ display: "flex", flexDirection: "column", gap: S.sm }}>
                    <span style={sectionCap}>
                        <TermTooltip termKey="GOLD_SILVER_RATIO">금/은 비율</TermTooltip>
                    </span>
                    <div style={{ display: "flex", alignItems: "baseline", gap: S.md }}>
                        <span style={{ ...MONO, color: C.textPrimary, fontSize: T.h2, fontWeight: T.w_bold }}>
                            {gsRatio.toFixed(1)}
                        </span>
                        <span style={{
                            color: gsRatio >= 90 ? C.success : gsRatio <= 60 ? C.danger : C.textSecondary,
                            fontSize: T.cap, fontWeight: T.w_semi,
                        }}>
                            {gsRatio >= 90 ? "은 상대 저평가 (금 강세 지나침)"
                                : gsRatio <= 60 ? "은 상대 고평가 (금 약세 지나침)"
                                    : "통상 범위 (60~90)"}
                        </span>
                    </div>
                </div>
            )}

            {/* Narrative */}
            {narrative && (
                <>
                    <div style={hr} />
                    <div style={{ color: C.textSecondary, fontSize: T.cap, lineHeight: T.lh_loose }}>
                        {narrative}
                    </div>
                </>
            )}
        </div>
    )
}

function CommodityHero({ label, unit, value, changePct, sparkline, high30d, low30d }: {
    label: string
    unit: string
    value: number
    changePct?: number | null
    sparkline?: number[] | null
    high30d?: number | null
    low30d?: number | null
}) {
    const c = pctColor(changePct ?? 0)
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: S.sm }}>
            <span style={sectionCap}>{label}</span>
            <div style={{ display: "flex", alignItems: "flex-end", gap: S.lg, flexWrap: "wrap" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={{ ...MONO, color: C.textPrimary, fontSize: T.h1, fontWeight: T.w_black, lineHeight: 1 }}>
                        {unit}{value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                    </span>
                    {changePct != null && Number.isFinite(changePct) && (
                        <span style={{ ...MONO, color: c, fontSize: T.cap, fontWeight: T.w_semi }}>
                            {fmtPct(changePct)} (1D)
                        </span>
                    )}
                </div>
                {Array.isArray(sparkline) && sparkline.length > 1 && (
                    <Sparkline values={sparkline} color={c} width={140} height={36} />
                )}
            </div>
            {(high30d != null || low30d != null) && (
                <div style={{ display: "flex", gap: S.lg, flexWrap: "wrap" }}>
                    {high30d != null && (
                        <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap }}>
                            30D 고가 <span style={{ color: C.textSecondary, fontWeight: T.w_semi }}>{unit}{high30d.toLocaleString()}</span>
                        </span>
                    )}
                    {low30d != null && (
                        <span style={{ ...MONO, color: C.textTertiary, fontSize: T.cap }}>
                            30D 저가 <span style={{ color: C.textSecondary, fontWeight: T.w_semi }}>{unit}{low30d.toLocaleString()}</span>
                        </span>
                    )}
                </div>
            )}
        </div>
    )
}

function Sparkline({ values, color, width = 100, height = 32 }: {
    values: number[]
    color: string
    width?: number
    height?: number
}) {
    if (!values || values.length < 2) return null
    const min = Math.min(...values)
    const max = Math.max(...values)
    const range = max - min || 1
    const stepX = width / (values.length - 1)
    const points = values
        .map((v, i) => `${(i * stepX).toFixed(2)},${(height - ((v - min) / range) * height).toFixed(2)}`)
        .join(" ")
    return (
        <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden>
            <polyline
                points={points}
                fill="none"
                stroke={color}
                strokeWidth={1.5}
                strokeLinejoin="round"
                strokeLinecap="round"
            />
        </svg>
    )
}


/* ─────────── 서브 컴포넌트 ─────────── */

function TabButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
    return (
        <button
            onClick={onClick}
            style={{
                background: "transparent",
                border: "none",
                color: active ? C.textPrimary : C.textTertiary,
                padding: `${S.sm}px ${S.lg}px`,
                borderRadius: R.pill,
                fontSize: T.cap,
                fontWeight: active ? T.w_bold : T.w_semi,
                fontFamily: FONT,
                letterSpacing: 0.5,
                textTransform: "uppercase",
                cursor: "pointer",
                transition: "color 180ms ease, border-color 180ms ease",
            }}
        >
            {label}
        </button>
    )
}

function ChipMetric({ label, value, color = C.textPrimary }: { label: React.ReactNode; value: string; color?: string }) {
    return (
        <div style={{
            display: "inline-flex", flexDirection: "column", gap: 1,
            padding: 0,
            background: "transparent",
            minWidth: 0,
        }}>
            <span style={{ color: C.textTertiary, fontSize: 10, fontWeight: T.w_med, letterSpacing: 0.5 }}>
                {label}
            </span>
            <span style={{ ...MONO, color, fontSize: T.cap, fontWeight: T.w_semi }}>
                {value}
            </span>
        </div>
    )
}

function YieldChip({ label, value }: { label: string; value: number }) {
    return (
        <div style={{
            background: C.bgCard, borderRadius: R.md,
            padding: `${S.md}px ${S.lg}px`,
            display: "flex", flexDirection: "column", gap: S.xs,
            flex: 1, minWidth: 80,
        }}>
            <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med, letterSpacing: 0.5 }}>
                {label}
            </span>
            <span style={{ ...MONO, color: C.textPrimary, fontSize: T.title, fontWeight: T.w_bold }}>
                {value.toFixed(2)}%
            </span>
        </div>
    )
}

function SpreadChip({ label, bps }: { label: string; bps: number }) {
    const c = bps < 0 ? C.danger : C.success
    return (
        <div style={{
            background: C.bgCard, borderRadius: R.md,
            padding: `${S.md}px ${S.lg}px`,
            display: "flex", flexDirection: "column", gap: S.xs,
            flex: 1, minWidth: 100,
        }}>
            <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_med }}>{label}</span>
            <span style={{ ...MONO, color: c, fontSize: T.title, fontWeight: T.w_bold }}>
                {bps > 0 ? "+" : ""}{bps.toFixed(1)}bp
            </span>
        </div>
    )
}


/* ─────────── 스타일 ─────────── */

const shell: CSSProperties = {
    width: "100%", boxSizing: "border-box",
    fontFamily: FONT, color: C.textPrimary,
    background: C.bgPage,

    borderRadius: 16,
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
    letterSpacing: -0.5,
}

const metaStyle: CSSProperties = {
    fontSize: T.cap, color: C.textTertiary, fontWeight: T.w_med,
}

const tabRow: CSSProperties = {
    display: "flex", gap: S.sm, flexWrap: "wrap",
}

const hr: CSSProperties = {
    height: 1, background: C.border, margin: 0,
}

const sectionCap: CSSProperties = {
    color: C.textTertiary,
    fontSize: T.cap, fontWeight: T.w_med,
    letterSpacing: 1, textTransform: "uppercase",
}

const heroBlock: CSSProperties = {
    display: "flex", flexDirection: "column", gap: S.md,
}

const overrideBox: CSSProperties = {
    background: "transparent",
    borderRadius: R.md,
    padding: `${S.md}px ${S.lg}px`,
    display: "flex", flexDirection: "column", gap: S.xs,
}

const blockStyle: CSSProperties = {
    background: C.bgCard,
    
    borderRadius: R.md,
    padding: `${S.md}px ${S.lg}px`,
    display: "flex", flexDirection: "column", gap: S.xs,
}

const emptyBox: CSSProperties = {
    padding: `${S.xxl}px 0`, textAlign: "center",
}

const loadingBox: CSSProperties = {
    minHeight: 200,
    display: "flex", alignItems: "center", justifyContent: "center",
}


/* ─────────── Framer Property Controls ─────────── */

MacroHub.defaultProps = {
    dataUrl: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/portfolio.json",
    market: "kr",
}

addPropertyControls(MacroHub, {
    dataUrl: {
        type: ControlType.String,
        title: "Portfolio URL",
        defaultValue: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/portfolio.json",
    },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["KR 국장", "US 미장"],
        defaultValue: "kr",
    },
})
