import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState, type CSSProperties } from "react"

/**
 * ⚠️ DEPRECATED (2026-05-04 폐기 결정)
 *
 * Brain v5 등급(STRONG_BUY/BUY/WATCH/CAUTION/AVOID)이 이미 종목 간 비교
 * 결과를 등급으로 표현 + AlertHub 가 "교체 권고" alert 자동 surface.
 * 9 metrics 직접 비교는 Brain 영역을 사용자에게 떠넘기는 형태 →
 * 이건희-반도체 원칙(feedback_simple_front_monster_back) 위반.
 *
 * Framer 페이지에서 인스턴스 제거. 추후 일괄 cleanup commit 시 git rm.
 *
 * 대안:
 *   - 보유 vs 후보 교체 결정 → AlertHub 자동 alert
 *   - 종목 detail 비교 → StockDetailPanel 두 인스턴스
 *
 * ────────────────────────────────────────────────────────────
 * (이하 원본 docstring — 모던 심플 정정은 commit 남아있음)
 *
 * CompareCard — 종목 비교 (Step 6.1 모던 심플, 별도 유지)
 *
 * 출처: CompareCard.tsx (521줄) 통째 재작성.
 *
 * 분류 정정 (2026-05-04):
 *   Plan v0.1 §3 "CompareCard → DetailPanel 흡수"는 잘못된 분류.
 *   StockDetailPanel(1,390) + CompareCard(521) 흡수 시 1,911줄 →
 *   single-responsibility 위반. DetailPanel = 단일 종목 drill-down,
 *   CompareCard = 멀티 종목 비교 본질이 다름. 별도 유지가 정합.
 *
 * 설계:
 *   - KR/US toggle (시장별 종목 universe)
 *   - 좌/우 종목 선택 (보유 우선 → 추천 후보)
 *   - 9 metrics 비교 (safety / multi / timing / prediction / RSI /
 *     flow / debt / margin / ROE)
 *   - 스파크라인 추이 row
 *   - winning dot (각 metric 우위)
 *   - AI Verdict 자동 산출 (multi+timing+prediction 합 비교)
 *
 * 모던 심플 6원칙:
 *   1. No card-in-card — 외곽 1개 + 섹션 spacing
 *   2. Flat hierarchy — title + selector + table + verdict
 *   3. Mono numerics — 점수 / 비율 / RSI
 *   4. Color discipline — winning = accent / verdict 색 = success/warn
 *   5. Emoji 0
 *   6. 자체 색 (#B5FF19 / #999 / #FFD700 / #EAB308 / #0D0D0D / #111)
 *      모두 토큰
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


/* ─────────── 시장 분류 ─────────── */
function isUSMarket(r: any): boolean {
    return r?.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(r?.market || "")
}


/* ─────────── Sparkline (인라인) ─────────── */
function Sparkline({ data, w = 80, h = 28, color = C.textTertiary }: { data?: number[]; w?: number; h?: number; color?: string }) {
    if (!data || data.length < 2) return null
    const mn = Math.min(...data)
    const mx = Math.max(...data)
    const rng = mx - mn || 1
    const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - mn) / rng) * h}`).join(" ")
    return (
        <svg width={w} height={h} style={{ display: "block" }}>
            <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
        </svg>
    )
}


/* ─────────── 비교 metrics 정의 ─────────── */
const COMPARE_KEYS: {
    key: string
    label: string
    path: string
    higher: boolean   // true = 높을수록 우위, false = 낮을수록 우위
    format?: (v: any) => string
}[] = [
    { key: "safety", label: "안심 점수", path: "safety_score", higher: true },
    { key: "multi", label: "종합 점수", path: "multi_factor.multi_score", higher: true },
    { key: "timing", label: "타이밍", path: "timing.timing_score", higher: true },
    { key: "prediction", label: "AI 상승확률", path: "prediction.up_probability", higher: true, format: (v: number) => `${v}%` },
    { key: "rsi", label: "RSI", path: "technical.rsi", higher: false },
    { key: "flow", label: "수급 점수", path: "flow.flow_score", higher: true },
    { key: "debt", label: "부채비율", path: "debt_ratio", higher: false, format: (v: number) => v != null && Number.isFinite(v) ? `${v.toFixed(0)}%` : "—" },
    { key: "margin", label: "영업이익률", path: "operating_margin", higher: true, format: (v: number) => v != null && Number.isFinite(v) ? `${(v * 100).toFixed(1)}%` : "—" },
    { key: "roe", label: "ROE", path: "roe", higher: true, format: (v: number) => v != null && Number.isFinite(v) ? `${(v * 100).toFixed(1)}%` : "—" },
]

function getNestedValue(obj: any, path: string): any {
    return path.split(".").reduce((o, k) => o?.[k], obj)
}


/* ═══════════════════════════ 메인 ═══════════════════════════ */

interface Props {
    dataUrl: string
    market: "kr" | "us"
}

export default function CompareCard(props: Props) {
    const { dataUrl } = props
    const isUS = props.market === "us"
    const [data, setData] = useState<any>(null)
    const [leftIdx, setLeftIdx] = useState<number>(-1)
    const [rightIdx, setRightIdx] = useState<number>(0)
    const [picking, setPicking] = useState<"left" | "right" | null>(null)

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal)
            .then((d) => {
                if (ac.signal.aborted) return
                setData(d)
                const holdings = d?.vams?.holdings || []
                const recs = d?.recommendations || []
                if (holdings.length > 0) {
                    setLeftIdx(-1)
                } else if (recs.length > 0) {
                    setLeftIdx(0)
                }
                const buys = recs.filter((r: any) => r.recommendation === "BUY")
                if (buys.length > 0) {
                    const buyIdx = recs.indexOf(buys[0])
                    setRightIdx(buyIdx > 0 ? buyIdx : 1)
                } else if (recs.length > 1) {
                    setRightIdx(1)
                }
            })
            .catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    if (!data) {
        return (
            <div style={shell}>
                <div style={loadingBox}>
                    <span style={{ color: C.textTertiary, fontSize: T.body }}>비교 카드 준비 중…</span>
                </div>
            </div>
        )
    }

    const allRecs: any[] = data.recommendations || []
    const recs: any[] = allRecs.filter((r: any) => isUS ? isUSMarket(r) : !isUSMarket(r))
    const allHoldings: any[] = data.vams?.holdings || []
    const holdings: any[] = allHoldings.filter((h: any) => {
        const matched = allRecs.find((r: any) => r.ticker === h.ticker)
        return isUS ? isUSMarket(matched || h) : !isUSMarket(matched || h)
    })

    const holdingStocks = holdings.map((h: any, i: number) => {
        const matched = recs.find((r: any) => r.ticker === h.ticker)
        return {
            ...h,
            ...matched,
            _isHolding: true,
            _holdingIdx: i,
            safety_score: matched?.safety_score ?? h.safety_score ?? 0,
            multi_factor: matched?.multi_factor || { multi_score: 0, grade: "—", factor_breakdown: {} },
            technical: matched?.technical || { rsi: 50 },
            flow: matched?.flow || { flow_score: 50, flow_signals: [] },
            timing: matched?.timing || { timing_score: 50, action: "HOLD", label: "관망" },
            prediction: matched?.prediction || { up_probability: 50 },
        }
    })
    const recsOnly = recs.filter((r: any) => !holdings.some((h: any) => h.ticker === r.ticker))
    const allPickable = [...holdingStocks, ...recsOnly]

    let leftStock: any = null
    if (holdingStocks.length > 0) {
        leftStock = leftIdx >= 0 ? recs[leftIdx] : holdingStocks[0]
    } else {
        leftStock = leftIdx >= 0 ? recs[leftIdx] : recs[0]
    }

    let rightStock: any = recs[rightIdx]
    if (!rightStock || rightStock === leftStock) {
        rightStock = recs.find((r: any) => r !== leftStock) || recs[1]
    }

    if (!leftStock || !rightStock || recs.length < 2) {
        return (
            <div style={shell}>
                <div style={loadingBox}>
                    <span style={{ color: C.textTertiary, fontSize: T.body }}>
                        비교할 종목이 부족합니다 (최소 2개 필요)
                    </span>
                </div>
            </div>
        )
    }

    const leftTotal = (leftStock.multi_factor?.multi_score || 0) + (leftStock.timing?.timing_score || 0) + (leftStock.prediction?.up_probability || 0)
    const rightTotal = (rightStock.multi_factor?.multi_score || 0) + (rightStock.timing?.timing_score || 0) + (rightStock.prediction?.up_probability || 0)
    const diff = rightTotal - leftTotal
    const advantageRight = diff > 0
    const hasHoldings = holdings.length > 0

    let verdictText = ""
    let verdictColor = C.warn
    if (Math.abs(diff) < 10) {
        verdictText = `두 종목 종합 지표가 비슷합니다. ${hasHoldings ? "기존 보유 유지가 수수료 절감 측면 유리." : "추가 분석 후 진입 결정."}`
        verdictColor = C.warn
    } else if (advantageRight) {
        const pct = Math.round(Math.abs(diff / (leftTotal || 1)) * 100)
        verdictText = hasHoldings
            ? `${rightStock.name}이(가) 종합 지표 약 ${pct > 0 ? pct : 5}% 우위. 교체 검토.`
            : `${rightStock.name}이(가) ${leftStock.name}보다 종합 ${pct > 0 ? pct : 5}% 우위.`
        verdictColor = C.success
    } else {
        const pct = Math.round(Math.abs(diff / (rightTotal || 1)) * 100)
        verdictText = hasHoldings
            ? `현재 보유 ${leftStock.name}이(가) ${pct > 0 ? pct : 5}% 우위. 유지 권고.`
            : `${leftStock.name}이(가) ${rightStock.name}보다 종합 ${pct > 0 ? pct : 5}% 우위.`
        verdictColor = C.success
    }

    return (
        <div style={shell}>
            {/* Header */}
            <div style={headerRow}>
                <div style={headerLeft}>
                    <span style={titleStyle}>{isUS ? "Stock Compare" : "안심 비교"}</span>
                    <span style={metaStyle}>
                        {hasHoldings ? (isUS ? "Holding vs Candidate" : "보유 vs 교체 후보") : (isUS ? "Side-by-Side" : "종목 간 비교")}
                    </span>
                </div>
            </div>

            {/* Selector row */}
            <div style={selectorRow}>
                <SelectorButton
                    badge={leftStock._isHolding ? (isUS ? "HOLDING" : "보유") : (isUS ? "STOCK A" : "종목 A")}
                    name={leftStock.name}
                    active={picking === "left"}
                    onClick={() => setPicking(picking === "left" ? null : "left")}
                />
                <span style={vsText}>VS</span>
                <SelectorButton
                    badge={hasHoldings ? (isUS ? "CANDIDATE" : "후보") : (isUS ? "STOCK B" : "종목 B")}
                    name={rightStock.name}
                    active={picking === "right"}
                    onClick={() => setPicking(picking === "right" ? null : "right")}
                />
            </div>

            {/* Dropdown */}
            {picking && (
                <div style={dropdownWrap}>
                    <span style={dropdownTitle}>
                        {picking === "left" ? "종목 선택 (좌)" : "종목 선택 (우)"}
                    </span>
                    <div style={dropdownList}>
                        {(picking === "left" ? allPickable : [...recsOnly, ...holdingStocks]).map((s: any, i: number) => {
                            const recIdx = recs.indexOf(s) >= 0 ? recs.indexOf(s) : recs.findIndex((r: any) => r.ticker === s.ticker)
                            const recScore = s.multi_factor?.multi_score || s.safety_score || 0
                            return (
                                <div
                                    key={`${s.ticker}-${i}`}
                                    style={dropdownItem}
                                    onClick={() => {
                                        if (picking === "left") {
                                            setLeftIdx(s._isHolding ? -1 : recIdx)
                                        } else {
                                            setRightIdx(recIdx >= 0 ? recIdx : 0)
                                        }
                                        setPicking(null)
                                    }}
                                >
                                    <span style={{ color: C.textPrimary, fontSize: T.cap, fontWeight: T.w_semi }}>
                                        {s.name}
                                    </span>
                                    <span style={{ color: C.textTertiary, fontSize: T.cap, display: "flex", gap: S.sm }}>
                                        <span>{s._isHolding ? "보유" : s.recommendation}</span>
                                        <span style={{ color: C.textDisabled }}>·</span>
                                        <span style={{ ...MONO, color: C.textSecondary }}>{recScore}점</span>
                                    </span>
                                </div>
                            )
                        })}
                    </div>
                </div>
            )}

            <div style={hr} />

            {/* Comparison table */}
            <div style={tableWrap}>
                {/* Sparkline row */}
                <div style={sparkRow}>
                    <div style={sparkCell}>
                        <Sparkline
                            data={leftStock.sparkline}
                            w={80} h={28}
                            color={(leftStock.sparkline || [])[leftStock.sparkline?.length - 1] >= (leftStock.sparkline || [])[0] ? C.up : C.down}
                        />
                    </div>
                    <div style={metricLabel}>추이</div>
                    <div style={sparkCell}>
                        <Sparkline
                            data={rightStock.sparkline}
                            w={80} h={28}
                            color={(rightStock.sparkline || [])[rightStock.sparkline?.length - 1] >= (rightStock.sparkline || [])[0] ? C.up : C.down}
                        />
                    </div>
                </div>

                {/* Metric rows */}
                {COMPARE_KEYS.map((ck) => {
                    const lv = getNestedValue(leftStock, ck.path)
                    const rv = getNestedValue(rightStock, ck.path)
                    const ln = typeof lv === "number" ? lv : 0
                    const rn = typeof rv === "number" ? rv : 0
                    const leftWins = ck.higher ? ln > rn : ln < rn
                    const rightWins = ck.higher ? rn > ln : rn < ln
                    const tie = ln === rn
                    const fmt = ck.format || ((v: number) => String(v))

                    return (
                        <div key={ck.key} style={metricRow}>
                            <MetricCell
                                value={fmt(lv ?? 0)}
                                isWinner={leftWins && !tie}
                                side="left"
                            />
                            <div style={metricLabel}>{ck.label}</div>
                            <MetricCell
                                value={fmt(rv ?? 0)}
                                isWinner={rightWins && !tie}
                                side="right"
                            />
                        </div>
                    )
                })}
            </div>

            <div style={hr} />

            {/* Verdict */}
            <div
                style={{
                    background: `${verdictColor}1A`,
                    border: `1px solid ${verdictColor}33`,
                    borderRadius: R.md,
                    borderLeft: `3px solid ${verdictColor}`,
                    padding: `${S.md}px ${S.lg}px`,
                    display: "flex", flexDirection: "column", gap: S.xs,
                }}
            >
                <span
                    style={{
                        color: verdictColor,
                        fontSize: T.cap,
                        fontWeight: T.w_bold,
                        letterSpacing: "0.08em",
                        textTransform: "uppercase",
                    }}
                >
                    {isUS ? "AI Verdict" : "비서 판단"}
                </span>
                <span style={{ color: C.textPrimary, fontSize: T.body, lineHeight: T.lh_loose }}>
                    {verdictText}
                </span>
            </div>
        </div>
    )
}


/* ─────────── 서브 컴포넌트 ─────────── */

function SelectorButton({
    badge, name, active, onClick,
}: {
    badge: string
    name: string
    active: boolean
    onClick: () => void
}) {
    return (
        <button
            onClick={onClick}
            style={{
                flex: 1,
                background: active ? C.bgElevated : C.bgCard,
                border: `1px solid ${active ? C.accent : C.border}`,
                borderRadius: R.md,
                padding: `${S.sm}px ${S.md}px`,
                cursor: "pointer",
                display: "flex", flexDirection: "column",
                gap: 2, fontFamily: FONT,
                transition: X.base,
                textAlign: "left",
                minWidth: 0,
            }}
        >
            <span
                style={{
                    color: active ? C.accent : C.textTertiary,
                    fontSize: T.cap,
                    fontWeight: T.w_med,
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                }}
            >
                {badge}
            </span>
            <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi }}>
                {name}
            </span>
        </button>
    )
}

function MetricCell({ value, isWinner, side }: { value: string; isWinner: boolean; side: "left" | "right" }) {
    return (
        <div
            style={{
                flex: 1,
                display: "flex", alignItems: "center", justifyContent: "center",
                gap: S.xs,
                fontSize: T.body,
                fontWeight: T.w_bold,
                ...MONO,
                color: isWinner ? C.accent : C.textSecondary,
                flexDirection: side === "left" ? "row" : "row-reverse",
            }}
        >
            <span>{value}</span>
            {isWinner && (
                <span
                    style={{
                        width: 5, height: 5, borderRadius: "50%",
                        background: C.accent, boxShadow: G.accent,
                    }}
                />
            )}
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

const selectorRow: CSSProperties = {
    display: "flex", alignItems: "center", gap: S.md,
}

const vsText: CSSProperties = {
    color: C.textDisabled,
    fontSize: T.cap,
    fontWeight: T.w_black,
    letterSpacing: "0.1em",
    flexShrink: 0,
    fontFamily: FONT,
}

const dropdownWrap: CSSProperties = {
    background: C.bgCard,
    border: `1px solid ${C.borderStrong}`,
    borderRadius: R.md,
    overflow: "hidden",
    display: "flex", flexDirection: "column",
}

const dropdownTitle: CSSProperties = {
    padding: `${S.sm}px ${S.md}px`,
    color: C.textTertiary,
    fontSize: T.cap,
    fontWeight: T.w_med,
    letterSpacing: "0.05em",
    textTransform: "uppercase",
    borderBottom: `1px solid ${C.border}`,
}

const dropdownList: CSSProperties = {
    maxHeight: 200,
    overflowY: "auto",
}

const dropdownItem: CSSProperties = {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: `${S.sm}px ${S.md}px`,
    cursor: "pointer",
    borderBottom: `1px solid ${C.border}`,
    transition: X.fast,
}

const hr: CSSProperties = {
    height: 1, background: C.border, margin: 0,
}

const tableWrap: CSSProperties = {
    display: "flex", flexDirection: "column",
}

const sparkRow: CSSProperties = {
    display: "flex", alignItems: "center",
    padding: `${S.sm}px 0`,
    borderBottom: `1px solid ${C.border}`,
}

const sparkCell: CSSProperties = {
    flex: 1, display: "flex", justifyContent: "center",
}

const metricRow: CSSProperties = {
    display: "flex", alignItems: "center",
    padding: `${S.xs}px 0`,
    borderBottom: `1px solid ${C.border}`,
}

const metricLabel: CSSProperties = {
    width: 96, textAlign: "center",
    color: C.textTertiary,
    fontSize: T.cap,
    fontWeight: T.w_med,
    letterSpacing: "0.03em",
    flexShrink: 0,
}

const loadingBox: CSSProperties = {
    minHeight: 200,
    display: "flex", alignItems: "center", justifyContent: "center",
}


/* ─────────── Framer Property Controls ─────────── */

CompareCard.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
    market: "kr",
}

addPropertyControls(CompareCard, {
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
