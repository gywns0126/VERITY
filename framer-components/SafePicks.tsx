import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState, useMemo } from "react"

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


/** Framer 단일 파일용 fetch (fetchPortfolioJson.ts와 동일 로직) */
function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    const u = (url || "").trim()
    const sep = u.includes("?") ? "&" : "?"
    const busted = `${u}${sep}_=${Date.now()}`
    return fetch(busted, { cache: "no-store", mode: "cors", credentials: "omit", signal })
        .then((r) => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            return r.text()
        })
        .then((txt) =>
            JSON.parse(
                txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null"),
            ),
        )
}

const DATA_URL =
    "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"

interface Props {
    dataUrl: string
    market: "kr" | "us"
}

function deriveDividendPicks(recommendations: any[], macro: any): any[] {
    const us10y = macro?.us_10y?.value ?? 3.5
    const threshold = Math.max(us10y * 0.8, 2.0)

    const picks: any[] = []
    for (const s of recommendations) {
        const divYield = s.div_yield ?? 0
        const debtRatio = s.debt_ratio ?? 0
        const opMargin = s.operating_margin ?? 0
        const eps = s.eps ?? 0
        const price = s.price ?? 0

        if (divYield <= threshold || divYield > 20 || debtRatio > 80 || opMargin < 5) continue
        if (eps <= 0) continue

        let payoutRatio = 0
        if (price > 0 && divYield > 0) {
            payoutRatio = ((price * divYield / 100) / eps) * 100
        }
        if (payoutRatio <= 0 || payoutRatio > 60) continue

        let tier = "A"
        if (divYield >= 4 && debtRatio < 50 && opMargin > 10) tier = "S"
        else if (divYield < 3 || debtRatio > 60) tier = "B"

        picks.push({
            ticker: s.ticker,
            name: s.name,
            price: s.price,
            div_yield: +divYield.toFixed(2),
            payout_ratio: +payoutRatio.toFixed(1),
            debt_ratio: +debtRatio.toFixed(1),
            operating_margin: +opMargin.toFixed(1),
            safety_tier: tier,
            reason: `배당 ${divYield.toFixed(1)}%(기준 ${threshold.toFixed(1)}% 초과)${debtRatio < 40 ? " · 저부채" : ""}${opMargin > 15 ? " · 고수익" : ""}`,
        })
    }

    picks.sort((a, b) => {
        const tierOrder = { S: 0, A: 1, B: 2 } as Record<string, number>
        return (tierOrder[a.safety_tier] ?? 2) * 100 - a.div_yield * 10
             - ((tierOrder[b.safety_tier] ?? 2) * 100 - b.div_yield * 10)
    })
    return picks.slice(0, 10)
}

function deriveParkingOptions(macro: any): any {
    const usdKrw = macro?.usd_krw?.value ?? 0
    const us10y = macro?.us_10y?.value ?? 0
    const us2y = macro?.us_2y?.value ?? 0
    const vix = macro?.vix?.value ?? 0
    const moodScore = macro?.market_mood?.score ?? 50
    const krRate = Math.max(us10y - 0.5, 2.5)

    const options: any[] = [
        { type: "kr_bond", name: "한국 단기국채 (1-3년)", est_yield: +krRate.toFixed(2), risk: "매우 낮음", liquidity: "높음", suitable: true },
    ]
    if (us2y > 3.5) {
        options.push({
            type: "us_tbill", name: "미국 단기국채 (T-Bill)", est_yield: +us2y.toFixed(2),
            risk: "매우 낮음 (환위험 존재)", liquidity: "높음", suitable: usdKrw < 1400,
            note: `환율 ${usdKrw.toLocaleString()}원${usdKrw < 1300 ? " — 원화 강세 시 유리" : " — 환헤지 고려"}`,
        })
    }
    options.push({ type: "mmf", name: "MMF/CMA (수시입출금)", est_yield: +Math.max(krRate - 0.5, 2.0).toFixed(2), risk: "매우 낮음", liquidity: "최고", suitable: true })

    let recommendation = "balanced"
    let message = "시장 안정 — 안전자산 10~20% 유지로 충분"
    if (vix > 25 || moodScore < 35) {
        recommendation = "defensive"
        message = `VIX ${vix}, 시장 불안 — 현금/국채 비중 확대 강력 권고`
    } else if (moodScore < 45) {
        recommendation = "cautious"
        message = "시장 관망 구간 — 안전자산 30~40% 유지 권장"
    }

    return { options, recommendation, message }
}

export default function SafePicks(props: Props) {
    const { dataUrl, market = "kr" } = props
    const isUS = market === "us"
    const [data, setData] = useState<any>(null)
    const [error, setError] = useState(false)
    const [activeTab, setActiveTab] = useState<"dividend" | "parking">("dividend")

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchPortfolioJson(dataUrl, ac.signal).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => { if (!ac.signal.aborted) setError(true) })
        return () => ac.abort()
    }, [dataUrl])

    const { dividends, parking, options } = useMemo(() => {
        if (!data) return { dividends: [], parking: {} as any, options: [] }

        const safe = data.safe_recommendations
        if (safe && (safe.dividend_stocks?.length || safe.parking_options?.options?.length)) {
            return {
                dividends: (safe.dividend_stocks || []).filter((s: any) =>
                    (s.div_yield ?? 0) <= 20 && (s.payout_ratio ?? 0) > 0
                ),
                parking: safe.parking_options || {},
                options: safe.parking_options?.options || [],
            }
        }

        const allRecs = data.recommendations || []
        const recs = isUS
            ? allRecs.filter((r: any) => r.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM/i.test(r.market || ""))
            : allRecs.filter((r: any) => /KOSPI|KOSDAQ|KRX/i.test(r.market || ""))
        const macro = data.macro || {}
        const derivedDividends = deriveDividendPicks(recs, macro)
        const derivedParking = deriveParkingOptions(macro)
        return { dividends: derivedDividends, parking: derivedParking, options: derivedParking.options }
    // isUS도 deps에 포함해야 market 변경 시 즉시 갱신됨
    }, [data, isUS])

    if (error) {
        return (
            <div style={wrap}>
                <span style={{ color: "#FF4D4D", fontSize: 13 }}>데이터를 불러올 수 없습니다</span>
            </div>
        )
    }

    if (!data) {
        return (
            <div style={wrap}>
                <span style={{ color: C.textTertiary, fontSize: 13 }}>로딩 중...</span>
            </div>
        )
    }

    const tierColor: Record<string, string> = { S: "#B5FF19", A: "#22C55E", B: "#FFD600" }
    const recBg: Record<string, string> = {
        defensive: "#1A0000",
        cautious: "#1A1200",
        balanced: "#001A0D",
    }
    const recBorder: Record<string, string> = {
        defensive: "#FF4D4D",
        cautious: "#FFD600",
        balanced: "#B5FF19",
    }

    return (
        <div style={wrap}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
                <div>
                    <span style={title}>안정 추천</span>
                    <span style={{ color: C.textTertiary, fontSize: 11, marginLeft: 8 }}>보안 비서의 안전 자산 가이드</span>
                </div>
            </div>

            {parking.message && (
                <div style={{
                    background: recBg[parking.recommendation] || "#111",
                    border: `1px solid ${recBorder[parking.recommendation] || "#222"}`,
                    borderRadius: 10, padding: "10px 14px", marginBottom: 16,
                }}>
                    <span style={{ color: recBorder[parking.recommendation] || "#888", fontSize: 12, fontWeight: 700 }}>
                        {parking.message}
                    </span>
                </div>
            )}

            <div style={tabRow}>
                <button onClick={() => setActiveTab("dividend")}
                    style={{ ...tabBtn, background: activeTab === "dividend" ? "#B5FF19" : "#1A1A1A", color: activeTab === "dividend" ? "#000" : "#888" }}>
                    배당주 {dividends.length}
                </button>
                <button onClick={() => setActiveTab("parking")}
                    style={{ ...tabBtn, background: activeTab === "parking" ? "#B5FF19" : "#1A1A1A", color: activeTab === "parking" ? "#000" : "#888" }}>
                    현금 파킹 {options.length}
                </button>
            </div>

            {activeTab === "dividend" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {dividends.length === 0 ? (
                        <div style={{ color: C.textTertiary, fontSize: 12, textAlign: "center", padding: 20 }}>
                            조건을 충족하는 배당주가 없습니다
                        </div>
                    ) : dividends.map((s: any) => (
                        <div key={s.ticker} style={card}>
                            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                    <span style={{ ...tierBadge, background: tierColor[s.safety_tier] || "#888" }}>
                                        {s.safety_tier}
                                    </span>
                                    <div>
                                        <span style={{ color: C.textPrimary, fontSize: 13, fontWeight: 700 }}>{s.name}</span>
                                        <span style={{ color: C.textTertiary, fontSize: 10, marginLeft: 6 }}>{s.ticker}</span>
                                    </div>
                                </div>
                                <div style={{ textAlign: "right" }}>
                                    <span style={{ color: "#B5FF19", fontSize: 15, fontWeight: 800 }}>{typeof s.div_yield === "number" && Number.isFinite(s.div_yield) ? `${s.div_yield.toFixed(2)}%` : "—"}</span>
                                    <span style={{ color: C.textTertiary, fontSize: 9, display: "block" }}>배당수익률</span>
                                </div>
                            </div>
                            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                                <MiniMetric label="현재가" value={s.currency === "USD" ? `$${s.price?.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : `${s.price?.toLocaleString()}원`} />
                                <MiniMetric label="배당성향" value={s.payout_ratio != null ? `${s.payout_ratio}%` : "—"} color={(s.payout_ratio ?? 100) < 40 ? "#22C55E" : "#FFD600"} />
                                <MiniMetric label="부채" value={s.debt_ratio != null ? `${s.debt_ratio}%` : "—"} color={(s.debt_ratio ?? 100) < 50 ? "#22C55E" : "#FFD600"} />
                                <MiniMetric label="영업이익률" value={s.operating_margin != null ? `${s.operating_margin}%` : "—"} />
                            </div>
                            <div style={{ color: "#777", fontSize: 10, marginTop: 6 }}>{s.reason}</div>
                        </div>
                    ))}
                </div>
            )}

            {activeTab === "parking" && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {options.map((opt: any, i: number) => (
                        <div key={i} style={card}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <span style={{ color: C.textPrimary, fontSize: 13, fontWeight: 700 }}>{opt.name}</span>
                                <span style={{ color: "#B5FF19", fontSize: 15, fontWeight: 800 }}>{opt.est_yield}%</span>
                            </div>
                            <div style={{ display: "flex", gap: 12, marginTop: 6 }}>
                                <span style={{ color: "#22C55E", fontSize: 11 }}>위험: {opt.risk}</span>
                                <span style={{ color: C.textSecondary, fontSize: 11 }}>유동성: {opt.liquidity}</span>
                            </div>
                            {opt.note && <div style={{ color: C.textTertiary, fontSize: 10, marginTop: 4 }}>{opt.note}</div>}
                            {!opt.suitable && <div style={{ color: "#FF4D4D", fontSize: 10, marginTop: 4 }}>현재 환율 조건 비적합</div>}
                        </div>
                    ))}

                    <div style={{ background: C.bgPage, borderRadius: 8, padding: "8px 12px", marginTop: 4 }}>
                        <span style={{ color: C.textTertiary, fontSize: 10 }}>
                            * 예상 수익률은 현재 금리 환경 기반 추정치입니다. 실제 상품별 금리는 증권사에서 확인하세요.
                        </span>
                    </div>
                </div>
            )}
        </div>
    )
}

function MiniMetric({ label, value, color = "#fff" }: { label: string; value: string; color?: string }) {
    return (
        <div style={{ flex: 1, background: C.bgPage, borderRadius: 6, padding: "5px 8px" }}>
            <span style={{ color: C.textTertiary, fontSize: 9, display: "block" }}>{label}</span>
            <span style={{ color, fontSize: 11, fontWeight: 700 }}>{value}</span>
        </div>
    )
}

SafePicks.defaultProps = { dataUrl: DATA_URL, market: "kr" }
addPropertyControls(SafePicks, {
    dataUrl: { type: ControlType.String, title: "JSON URL", defaultValue: DATA_URL },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["국장 (KR)", "미장 (US)"],
        defaultValue: "kr",
    },
})

const font = "'Pretendard', -apple-system, sans-serif"
const wrap: React.CSSProperties = { width: "100%", background: C.bgPage, borderRadius: 16, fontFamily: font, padding: 20 }
const title: React.CSSProperties = { color: C.textPrimary, fontSize: 18, fontWeight: 800 }
const tabRow: React.CSSProperties = { display: "flex", gap: 6, marginBottom: 12 }
const tabBtn: React.CSSProperties = { border: "none", borderRadius: 8, padding: "7px 14px", fontSize: 12, fontWeight: 700, fontFamily: font, cursor: "pointer" }
const card: React.CSSProperties = { background: C.bgElevated, borderRadius: 10, padding: "12px 14px", border: `1px solid ${C.border}` }
const tierBadge: React.CSSProperties = { color: "#000", fontSize: 11, fontWeight: 900, width: 24, height: 24, borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "center" }
