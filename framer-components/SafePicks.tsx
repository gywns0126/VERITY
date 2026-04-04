import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

const DATA_URL =
    "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"

interface Props {
    dataUrl: string
}

export default function SafePicks(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [activeTab, setActiveTab] = useState<"dividend" | "parking">("dividend")

    useEffect(() => {
        if (!dataUrl) return
        fetch(dataUrl)
            .then((r) => r.text())
            .then((txt) => JSON.parse(txt.replace(/\bNaN\b/g, "null")))
            .then(setData)
            .catch(console.error)
    }, [dataUrl])

    const safe = data?.safe_recommendations || {}
    const dividends: any[] = safe.dividend_stocks || []
    const parking: any = safe.parking_options || {}
    const options: any[] = parking.options || []

    if (!data) {
        return (
            <div style={wrap}>
                <span style={{ color: "#555", fontSize: 13 }}>로딩 중...</span>
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
                    <span style={{ color: "#555", fontSize: 11, marginLeft: 8 }}>보안 비서의 안전 자산 가이드</span>
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
                        <div style={{ color: "#555", fontSize: 12, textAlign: "center", padding: 20 }}>
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
                                        <span style={{ color: "#fff", fontSize: 13, fontWeight: 700 }}>{s.name}</span>
                                        <span style={{ color: "#555", fontSize: 10, marginLeft: 6 }}>{s.ticker}</span>
                                    </div>
                                </div>
                                <div style={{ textAlign: "right" }}>
                                    <span style={{ color: "#B5FF19", fontSize: 15, fontWeight: 800 }}>{s.div_yield}%</span>
                                    <span style={{ color: "#555", fontSize: 9, display: "block" }}>배당수익률</span>
                                </div>
                            </div>
                            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                                <MiniMetric label="현재가" value={`${s.price?.toLocaleString()}원`} />
                                <MiniMetric label="배당성향" value={`${s.payout_ratio}%`} color={s.payout_ratio < 40 ? "#22C55E" : "#FFD600"} />
                                <MiniMetric label="부채" value={`${s.debt_ratio}%`} color={s.debt_ratio < 50 ? "#22C55E" : "#FFD600"} />
                                <MiniMetric label="영업이익률" value={`${s.operating_margin}%`} />
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
                                <span style={{ color: "#fff", fontSize: 13, fontWeight: 700 }}>{opt.name}</span>
                                <span style={{ color: "#B5FF19", fontSize: 15, fontWeight: 800 }}>{opt.est_yield}%</span>
                            </div>
                            <div style={{ display: "flex", gap: 12, marginTop: 6 }}>
                                <span style={{ color: "#22C55E", fontSize: 11 }}>위험: {opt.risk}</span>
                                <span style={{ color: "#888", fontSize: 11 }}>유동성: {opt.liquidity}</span>
                            </div>
                            {opt.note && <div style={{ color: "#666", fontSize: 10, marginTop: 4 }}>{opt.note}</div>}
                            {!opt.suitable && <div style={{ color: "#FF4D4D", fontSize: 10, marginTop: 4 }}>현재 환율 조건 비적합</div>}
                        </div>
                    ))}

                    <div style={{ background: "#0A0A0A", borderRadius: 8, padding: "8px 12px", marginTop: 4 }}>
                        <span style={{ color: "#444", fontSize: 10 }}>
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
        <div style={{ flex: 1, background: "#0A0A0A", borderRadius: 6, padding: "5px 8px" }}>
            <span style={{ color: "#555", fontSize: 9, display: "block" }}>{label}</span>
            <span style={{ color, fontSize: 11, fontWeight: 700 }}>{value}</span>
        </div>
    )
}

SafePicks.defaultProps = { dataUrl: DATA_URL }
addPropertyControls(SafePicks, {
    dataUrl: { type: ControlType.String, title: "JSON URL", defaultValue: DATA_URL },
})

const font = "'Pretendard', -apple-system, sans-serif"
const wrap: React.CSSProperties = { width: "100%", background: "#0A0A0A", borderRadius: 16, fontFamily: font, padding: 20 }
const title: React.CSSProperties = { color: "#fff", fontSize: 18, fontWeight: 800 }
const tabRow: React.CSSProperties = { display: "flex", gap: 6, marginBottom: 12 }
const tabBtn: React.CSSProperties = { border: "none", borderRadius: 8, padding: "7px 14px", fontSize: 12, fontWeight: 700, fontFamily: font, cursor: "pointer" }
const card: React.CSSProperties = { background: "#111", borderRadius: 10, padding: "12px 14px", border: "1px solid #1A1A1A" }
const tierBadge: React.CSSProperties = { color: "#000", fontSize: 11, fontWeight: 900, width: 24, height: 24, borderRadius: 12, display: "flex", alignItems: "center", justifyContent: "center" }
