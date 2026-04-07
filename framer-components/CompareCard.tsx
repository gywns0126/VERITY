import { useState, useEffect } from "react"
import { addPropertyControls, ControlType } from "framer"
import { fetchPortfolioJson } from "./fetchPortfolioJson"

interface Props {
    dataUrl: string
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
    { key: "debt", label: "부채비율", path: "debt_ratio", higher: false, format: (v: number) => v ? `${v.toFixed(0)}%` : "—" },
    { key: "margin", label: "영업이익률", path: "operating_margin", higher: true, format: (v: number) => v ? `${(v * 100).toFixed(1)}%` : "—" },
    { key: "roe", label: "ROE", path: "roe", higher: true, format: (v: number) => v ? `${(v * 100).toFixed(1)}%` : "—" },
]

function getNestedValue(obj: any, path: string): any {
    return path.split(".").reduce((o, k) => o?.[k], obj)
}

export default function CompareCard(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [leftIdx, setLeftIdx] = useState<number>(-1)
    const [rightIdx, setRightIdx] = useState<number>(0)
    const [picking, setPicking] = useState<"left" | "right" | null>(null)

    useEffect(() => {
        if (!dataUrl) return
        fetchPortfolioJson(dataUrl)
            .then((d) => {
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
    }, [dataUrl])

    if (!data) {
        return (
            <div style={styles.container}>
                <div style={styles.loading}>비교 카드 준비 중...</div>
            </div>
        )
    }

    const recs: any[] = data.recommendations || []
    const holdings: any[] = data.vams?.holdings || []

    const holdingStocks = holdings.map((h: any, i: number) => {
        const matched = recs.find((r: any) => r.ticker === h.ticker)
        return {
            ...h,
            ...matched,
            _isHolding: true,
            _holdingIdx: i,
            safety_score: h.safety_score || matched?.safety_score || 0,
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

    const Sparkline = ({ data: d, w = 60, h = 20, color = "#888" }: { data?: number[]; w?: number; h?: number; color?: string }) => {
        if (!d || d.length < 2) return null
        const mn = Math.min(...d), mx = Math.max(...d), rng = mx - mn || 1
        const pts = d.map((v, i) => `${(i / (d.length - 1)) * w},${h - ((v - mn) / rng) * h}`).join(" ")
        return <svg width={w} height={h}><polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" /></svg>
    }

    return (
        <div style={styles.container}>
            <div style={styles.header}>
                <span style={styles.title}>안심 비교</span>
                <span style={styles.subtitle}>{hasHoldings ? "보유 vs 교체 후보" : "종목 간 비교"}</span>
            </div>

            {/* 종목 선택 바 */}
            <div style={styles.selectorRow}>
                <button style={styles.selectorBtn} onClick={() => setPicking(picking === "left" ? null : "left")}>
                    <span style={styles.selectorLabel}>{leftStock._isHolding ? "보유" : "종목 A"}</span>
                    <span style={styles.selectorName}>{leftStock.name}</span>
                </button>
                <span style={styles.vsText}>VS</span>
                <button style={styles.selectorBtn} onClick={() => setPicking(picking === "right" ? null : "right")}>
                    <span style={styles.selectorLabel}>{hasHoldings ? "후보" : "종목 B"}</span>
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
                                    <span style={{ color: "#ccc", fontSize: 12 }}>{s.name}</span>
                                    <span style={{ color: "#666", fontSize: 10 }}>
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
                            color={(leftStock.sparkline || [])[leftStock.sparkline?.length - 1] >= (leftStock.sparkline || [])[0] ? "#22C55E" : "#EF4444"} />
                    </div>
                    <div style={{ ...styles.rowLabel, fontSize: 10, color: "#444" }}>추이</div>
                    <div style={styles.sparkCell}>
                        <Sparkline data={rightStock.sparkline} w={80} h={28}
                            color={(rightStock.sparkline || [])[rightStock.sparkline?.length - 1] >= (rightStock.sparkline || [])[0] ? "#22C55E" : "#EF4444"} />
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
                <span style={styles.verdictLabel}>비서 판단</span>
                <span style={styles.verdictText}>{verdictText}</span>
            </div>
        </div>
    )
}

addPropertyControls(CompareCard, {
    dataUrl: {
        type: ControlType.String,
        title: "Data URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    },
})

const styles: Record<string, React.CSSProperties> = {
    container: {
        width: "100%",
        fontFamily: "'Inter', 'Pretendard', -apple-system, sans-serif",
        background: "#0A0A0A",
        borderRadius: 16,
        overflow: "hidden",
    },
    loading: {
        padding: 24,
        color: "#555",
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
        color: "#fff",
        fontSize: 16,
        fontWeight: 800,
    },
    subtitle: {
        color: "#555",
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
        background: "#111",
        border: "1px solid #222",
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
        color: "#555",
        fontWeight: 600,
        textTransform: "uppercase" as const,
    },
    selectorName: {
        fontSize: 14,
        color: "#fff",
        fontWeight: 700,
    },
    vsText: {
        color: "#333",
        fontSize: 12,
        fontWeight: 900,
        flexShrink: 0,
    },
    dropdown: {
        margin: "0 20px 12px",
        background: "#111",
        border: "1px solid #222",
        borderRadius: 10,
        overflow: "hidden",
    },
    dropdownTitle: {
        padding: "8px 12px",
        fontSize: 11,
        color: "#666",
        fontWeight: 600,
        borderBottom: "1px solid #1A1A1A",
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
        color: "#555",
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
        color: "#ccc",
        lineHeight: "1.6",
    },
}
