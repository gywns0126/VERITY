import React, { useState, useEffect } from "react"
import { addPropertyControls, ControlType } from "framer"

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
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_tight: 1.3, lh_normal: 1.5, lh_loose: 1.7,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease", slow: "240ms ease" }
const FONT = "'Inter', 'Pretendard', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/** Framer 단일 파일 붙여넣기용 (fetchPortfolioJson.ts와 동일 로직 — 수정 시 맞춰 주세요) */
function bustPortfolioUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

const PORTFOLIO_FETCH_INIT: RequestInit = {
    cache: "no-store",
    mode: "cors",
    credentials: "omit",
}

// WARN-24: 15초 timeout + AbortController — 네트워크 hang 방지
const PORTFOLIO_FETCH_TIMEOUT_MS = 15_000

function _withTimeout<T>(p: Promise<T>, ms: number, ac: AbortController): Promise<T> {
    const timer = setTimeout(() => ac.abort(), ms)
    return p.finally(() => clearTimeout(timer))
}

function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    const ac = new AbortController()
    if (signal) {
        if (signal.aborted) ac.abort()
        else signal.addEventListener("abort", () => ac.abort(), { once: true })
    }
    return _withTimeout(
        fetch(bustPortfolioUrl(url), { ...PORTFOLIO_FETCH_INIT, signal: ac.signal })
            .then((r) => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`)
                return r.text()
            })
            .then((txt) =>
                JSON.parse(
                    txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null"),
                ),
            ),
        PORTFOLIO_FETCH_TIMEOUT_MS,
        ac,
    )
}

function _isUS(r: any): boolean {
    return r?.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(r?.market || "")
}

function Sparkline({ data: d, w = 60, h = 20, color = "#888" }: { data?: number[]; w?: number; h?: number; color?: string }) {
    if (!d || d.length < 2) return null
    const mn = Math.min(...d), mx = Math.max(...d), rng = mx - mn || 1
    const pts = d.map((v, i) => `${(i / (d.length - 1)) * w},${h - ((v - mn) / rng) * h}`).join(" ")
    return <svg width={w} height={h}><polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" /></svg>
}

interface Props {
    dataUrl: string
    market: "kr" | "us"
}

interface StockProfile {
    name: string
    ticker: string
    safety_score: number
    multi_factor: { multi_score: number; grade: string; factor_breakdown: Record<string, number> }
    technical: { rsi: number }
    flow: { flow_score: number; flow_signals: string[] }
    timing: { timing_score: number; action: string; label: string }
    prediction: { up_probability: number }
    recommendation: string
    debt_ratio?: number
    operating_margin?: number
    roe?: number
    per?: number
    price?: number
    sparkline?: number[]
}

const COMPARE_KEYS: { key: string; label: string; path: string; higher: boolean; format?: (v: any) => string }[] = [
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
        fetchPortfolioJson(dataUrl, ac.signal)
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
            <div style={styles.container}>
                <div style={styles.loading}>비교 카드 준비 중...</div>
            </div>
        )
    }

    const allRecs: any[] = data.recommendations || []
    const recs: any[] = allRecs.filter((r: any) => isUS ? _isUS(r) : !_isUS(r))
    const allHoldings: any[] = data.vams?.holdings || []
    const holdings: any[] = allHoldings.filter((h: any) => {
        const matched = allRecs.find((r: any) => r.ticker === h.ticker)
        return isUS ? _isUS(matched || h) : !_isUS(matched || h)
    })

    const holdingStocks = holdings.map((h: any, i: number) => {
        const matched = recs.find((r: any) => r.ticker === h.ticker)
        return {
            ...h,
            ...matched,
            _isHolding: true,
            _holdingIdx: i,
            // holdings에 남은 예전 안심 점수보다 recommendations와 동일 스냅샷을 쓰면 같은 종목 비교 시 수치가 맞음
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
    let rightStock: any = null

    if (holdingStocks.length > 0) {
        leftStock = leftIdx >= 0 ? recs[leftIdx] : holdingStocks[0]
    } else {
        leftStock = leftIdx >= 0 ? recs[leftIdx] : recs[0]
    }

    rightStock = recs[rightIdx]
    if (!rightStock || rightStock === leftStock) {
        rightStock = recs.find((r: any) => r !== leftStock) || recs[1]
    }

    if (!leftStock || !rightStock || recs.length < 2) {
        return (
            <div style={styles.container}>
                <div style={styles.loading}>비교할 종목이 부족합니다 (최소 2개 필요)</div>
            </div>
        )
    }

    const leftTotal = (leftStock.multi_factor?.multi_score || 0) + (leftStock.timing?.timing_score || 0) + (leftStock.prediction?.up_probability || 0)
    const rightTotal = (rightStock.multi_factor?.multi_score || 0) + (rightStock.timing?.timing_score || 0) + (rightStock.prediction?.up_probability || 0)
    const diff = rightTotal - leftTotal
    const advantageRight = diff > 0

    const hasHoldings = holdings.length > 0
    let verdictText = ""
    if (Math.abs(diff) < 10) {
        verdictText = `두 종목의 종합 지표가 비슷합니다. ${hasHoldings ? "기존 보유를 유지하는 것이 수수료 절감 측면에서 유리합니다." : "추가 분석 후 진입을 결정하세요."}`
    } else if (advantageRight) {
        const pct = Math.round(Math.abs(diff / (leftTotal || 1)) * 100)
        verdictText = hasHoldings
            ? `${rightStock.name}이(가) 종합 지표에서 약 ${pct > 0 ? pct : 5}% 우위입니다. 교체를 검토해보세요.`
            : `${rightStock.name}이(가) ${leftStock.name}보다 종합 ${pct > 0 ? pct : 5}% 우위입니다.`
    } else {
        const pct = Math.round(Math.abs(diff / (rightTotal || 1)) * 100)
        verdictText = hasHoldings
            ? `현재 보유 중인 ${leftStock.name}이(가) ${pct > 0 ? pct : 5}% 우위입니다. 유지를 권합니다.`
            : `${leftStock.name}이(가) ${rightStock.name}보다 종합 ${pct > 0 ? pct : 5}% 우위입니다.`
    }

    return (
        <div style={styles.container}>
            <div style={styles.header}>
                <span style={styles.title}>{isUS ? "Stock Compare" : "안심 비교"}</span>
                <span style={styles.subtitle}>{hasHoldings ? (isUS ? "Holding vs Candidate" : "보유 vs 교체 후보") : (isUS ? "Side-by-Side" : "종목 간 비교")}</span>
            </div>

            {/* 종목 선택 바 */}
            <div style={styles.selectorRow}>
                <button style={styles.selectorBtn} onClick={() => setPicking(picking === "left" ? null : "left")}>
                    <span style={styles.selectorLabel}>{leftStock._isHolding ? (isUS ? "Holding" : "보유") : (isUS ? "Stock A" : "종목 A")}</span>
                    <span style={styles.selectorName}>{leftStock.name}</span>
                </button>
                <span style={styles.vsText}>VS</span>
                <button style={styles.selectorBtn} onClick={() => setPicking(picking === "right" ? null : "right")}>
                    <span style={styles.selectorLabel}>{hasHoldings ? (isUS ? "Candidate" : "후보") : (isUS ? "Stock B" : "종목 B")}</span>
                    <span style={styles.selectorName}>{rightStock.name}</span>
                </button>
            </div>

            {/* 종목 선택 드롭다운 */}
            {picking && (
                <div style={styles.dropdown}>
                    <div style={styles.dropdownTitle}>
                        {picking === "left" ? "보유 종목 선택" : "교체 후보 선택"}
                    </div>
                    <div style={styles.dropdownList}>
                        {(picking === "left" ? allPickable : [...recsOnly, ...holdingStocks]).map((s: any, i: number) => {
                            const recIdx = recs.indexOf(s) >= 0 ? recs.indexOf(s) : recs.findIndex((r: any) => r.ticker === s.ticker)
                            return (
                                <div
                                    key={`${s.ticker}-${i}`}
                                    style={styles.dropdownItem}
                                    onClick={() => {
                                        if (picking === "left") {
                                            setLeftIdx(s._isHolding ? -1 : recIdx)
                                        } else {
                                            setRightIdx(recIdx >= 0 ? recIdx : 0)
                                        }
                                        setPicking(null)
                                    }}
                                >
                                    <span style={{ color: C.textPrimary, fontSize: 12 }}>{s.name}</span>
                                    <span style={{ color: C.textTertiary, fontSize: 10 }}>
                                        {s._isHolding ? "보유" : s.recommendation}
                                        {" · "}
                                        {s.multi_factor?.multi_score || s.safety_score || 0}점
                                    </span>
                                </div>
                            )
                        })}
                    </div>
                </div>
            )}

            {/* 비교 테이블 */}
            <div style={styles.table}>
                {/* 스파크라인 행 */}
                <div style={styles.sparkRow}>
                    <div style={styles.sparkCell}>
                        <Sparkline data={leftStock.sparkline} w={80} h={28}
                            color={(leftStock.sparkline || [])[leftStock.sparkline?.length - 1] >= (leftStock.sparkline || [])[0] ? C.up : C.down} />
                    </div>
                    <div style={{ ...styles.rowLabel, fontSize: 10, color: C.textTertiary }}>추이</div>
                    <div style={styles.sparkCell}>
                        <Sparkline data={rightStock.sparkline} w={80} h={28}
                            color={(rightStock.sparkline || [])[rightStock.sparkline?.length - 1] >= (rightStock.sparkline || [])[0] ? C.up : C.down} />
                    </div>
                </div>

                {COMPARE_KEYS.map((ck) => {
                    const lv = getNestedValue(leftStock, ck.path)
                    const rv = getNestedValue(rightStock, ck.path)
                    const ln = typeof lv === "number" ? lv : 0
                    const rn = typeof rv === "number" ? rv : 0
                    const leftWins = ck.higher ? ln > rn : ln < rn
                    const rightWins = ck.higher ? rn > ln : rn < ln
                    const tie = ln === rn
                    const fmt = ck.format || ((v: number) => `${v}`)

                    return (
                        <div key={ck.key} style={styles.row}>
                            <div style={{ ...styles.cellValue, color: leftWins && !tie ? "#B5FF19" : "#999" }}>
                                {fmt(lv ?? 0)}
                                {leftWins && !tie && <span style={styles.winDot} />}
                            </div>
                            <div style={styles.rowLabel}>{ck.label}</div>
                            <div style={{ ...styles.cellValue, color: rightWins && !tie ? "#B5FF19" : "#999" }}>
                                {rightWins && !tie && <span style={styles.winDot} />}
                                {fmt(rv ?? 0)}
                            </div>
                        </div>
                    )
                })}
            </div>

            {/* 비서 멘트 */}
            <div style={{
                ...styles.verdict,
                borderLeft: `3px solid ${advantageRight ? "#B5FF19" : "#EAB308"}`,
            }}>
                <span style={styles.verdictLabel}>{isUS ? "AI Verdict" : "비서 판단"}</span>
                <span style={styles.verdictText}>{verdictText}</span>
            </div>
        </div>
    )
}

CompareCard.defaultProps = { ...CompareCard.defaultProps, market: "kr" }

addPropertyControls(CompareCard, {
    dataUrl: {
        type: ControlType.String,
        title: "Data URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["KR 국장", "US 미장"],
        defaultValue: "kr",
    },
})

const styles: Record<string, React.CSSProperties> = {
    container: {
        width: "100%",
        fontFamily: "'Inter', 'Pretendard', -apple-system, sans-serif",
        background: C.bgPage,
        borderRadius: 16,
        overflow: "hidden",
    },
    loading: {
        padding: 24,
        color: C.textTertiary,
        fontSize: 13,
        textAlign: "center",
    },
    header: {
        padding: "16px 20px 8px",
        display: "flex",
        alignItems: "baseline",
        gap: 8,
    },
    title: {
        color: C.textPrimary,
        fontSize: 16,
        fontWeight: 800,
    },
    subtitle: {
        color: C.textTertiary,
        fontSize: 11,
    },
    selectorRow: {
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "0 20px 12px",
    },
    selectorBtn: {
        flex: 1,
        background: C.bgCard,
        border: `1px solid ${C.border}`,
        borderRadius: 10,
        padding: "10px 14px",
        cursor: "pointer",
        display: "flex",
        flexDirection: "column",
        gap: 2,
        fontFamily: "'Inter', 'Pretendard', -apple-system, sans-serif",
    },
    selectorLabel: {
        fontSize: 9,
        color: C.textTertiary,
        fontWeight: 600,
        textTransform: "uppercase" as const,
    },
    selectorName: {
        fontSize: 14,
        color: C.textPrimary,
        fontWeight: 700,
    },
    vsText: {
        color: C.textDisabled,
        fontSize: 12,
        fontWeight: 900,
        flexShrink: 0,
    },
    dropdown: {
        margin: "0 20px 12px",
        background: C.bgCard,
        border: `1px solid ${C.border}`,
        borderRadius: 10,
        overflow: "hidden",
    },
    dropdownTitle: {
        padding: "8px 12px",
        fontSize: 11,
        color: C.textTertiary,
        fontWeight: 600,
        borderBottom: `1px solid ${C.border}`,
    },
    dropdownList: {
        maxHeight: 200,
        overflowY: "auto" as const,
    },
    dropdownItem: {
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "8px 12px",
        cursor: "pointer",
        borderBottom: "1px solid #0D0D0D",
    },
    table: {
        padding: "0 12px",
    },
    sparkRow: {
        display: "flex",
        alignItems: "center",
        padding: "8px 8px",
        borderBottom: "1px solid #111",
    },
    sparkCell: {
        flex: 1,
        display: "flex",
        justifyContent: "center",
    },
    row: {
        display: "flex",
        alignItems: "center",
        padding: "7px 8px",
        borderBottom: "1px solid #111",
    },
    rowLabel: {
        width: 80,
        textAlign: "center" as const,
        color: C.textTertiary,
        fontSize: 10,
        fontWeight: 600,
        flexShrink: 0,
    },
    cellValue: {
        flex: 1,
        textAlign: "center" as const,
        fontSize: 13,
        fontWeight: 700,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 4,
    },
    winDot: {
        width: 5,
        height: 5,
        borderRadius: 3,
        background: "#B5FF19",
        display: "inline-block",
    },
    verdict: {
        margin: "12px 20px 16px",
        padding: "12px 14px",
        background: "rgba(255,255,255,0.02)",
        borderRadius: 10,
    },
    verdictLabel: {
        display: "block",
        fontSize: 10,
        color: "#FFD700",
        fontWeight: 700,
        marginBottom: 4,
        letterSpacing: "0.03em",
    },
    verdictText: {
        fontSize: 13,
        color: C.textPrimary,
        lineHeight: "1.6",
    },
}
