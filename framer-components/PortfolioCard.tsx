import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

interface Props {
    dataUrl: string
}

export default function PortfolioCard(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)

    useEffect(() => {
        if (!dataUrl) return
        fetch(dataUrl)
            .then((r) => r.json())
            .then(setData)
            .catch(console.error)
    }, [dataUrl])

    const vams = data?.vams || {}
    const total = vams.total_asset || 0
    const cash = vams.cash || 0
    const ret = vams.total_return_pct || 0
    const holdings = vams.holdings || []
    const realizedPnl = vams.total_realized_pnl || 0

    const retColor = ret >= 0 ? "#B5FF19" : "#FF4D4D"

    return (
        <div style={card}>
            <span style={cardTitle}>가상 투자 현황</span>

            {/* 총 자산 */}
            <div style={heroSection}>
                <span style={totalLabel}>총 자산</span>
                <span style={totalValue}>
                    {total.toLocaleString()}
                    <span style={totalUnit}>원</span>
                </span>
                <span style={{ ...returnBadge, color: retColor }}>
                    {ret >= 0 ? "+" : ""}
                    {ret.toFixed(2)}%
                </span>
            </div>

            {/* 요약 메트릭 */}
            <div style={metricsRow}>
                <div style={metricBox}>
                    <span style={metricLabel}>현금</span>
                    <span style={metricVal}>
                        {cash.toLocaleString()}원
                    </span>
                </div>
                <div style={metricBox}>
                    <span style={metricLabel}>실현 손익</span>
                    <span
                        style={{
                            ...metricVal,
                            color: realizedPnl >= 0 ? "#B5FF19" : "#FF4D4D",
                        }}
                    >
                        {realizedPnl >= 0 ? "+" : ""}
                        {realizedPnl.toLocaleString()}원
                    </span>
                </div>
                <div style={metricBox}>
                    <span style={metricLabel}>보유 종목</span>
                    <span style={metricVal}>{holdings.length}개</span>
                </div>
            </div>

            {/* 보유 종목 리스트 */}
            {holdings.length > 0 && (
                <div style={holdingsList}>
                    {holdings.map((h: any, i: number) => {
                        const pct = h.return_pct || 0
                        const pctColor =
                            pct >= 0 ? "#B5FF19" : "#FF4D4D"
                        return (
                            <div key={i} style={holdingRow}>
                                <div style={holdingLeft}>
                                    <span style={holdingName}>
                                        {h.name}
                                    </span>
                                    <span style={holdingDetail}>
                                        {h.quantity}주 · 평단{" "}
                                        {h.buy_price?.toLocaleString()}원
                                    </span>
                                </div>
                                <div style={holdingRight}>
                                    <span
                                        style={{
                                            ...holdingReturn,
                                            color: pctColor,
                                        }}
                                    >
                                        {pct >= 0 ? "+" : ""}
                                        {pct.toFixed(1)}%
                                    </span>
                                    <span style={holdingPrice}>
                                        {h.current_price?.toLocaleString()}원
                                    </span>
                                </div>
                            </div>
                        )
                    })}
                </div>
            )}

            {holdings.length === 0 && (
                <div style={emptyHolder}>
                    <span style={emptyText}>
                        아직 매수한 종목이 없습니다
                    </span>
                </div>
            )}
        </div>
    )
}

PortfolioCard.defaultProps = {
    dataUrl: "",
}

addPropertyControls(PortfolioCard, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: "",
    },
})

const font = "'Pretendard', -apple-system, sans-serif"

const card: React.CSSProperties = {
    width: "100%",
    background: "#F8F7F2",
    borderRadius: 20,
    padding: "32px 28px",
    fontFamily: font,
    display: "flex",
    flexDirection: "column",
    gap: 20,
    border: "1px solid #E8E7E2",
}

const cardTitle: React.CSSProperties = {
    color: "#000",
    fontSize: 13,
    fontWeight: 600,
    letterSpacing: -0.3,
    textTransform: "uppercase",
}

const heroSection: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 4,
}

const totalLabel: React.CSSProperties = {
    color: "#888",
    fontSize: 12,
    fontWeight: 500,
}

const totalValue: React.CSSProperties = {
    color: "#000",
    fontSize: 36,
    fontWeight: 800,
    letterSpacing: -1.5,
}

const totalUnit: React.CSSProperties = {
    fontSize: 18,
    fontWeight: 500,
    color: "#666",
    marginLeft: 4,
}

const returnBadge: React.CSSProperties = {
    fontSize: 18,
    fontWeight: 700,
}

const metricsRow: React.CSSProperties = {
    display: "flex",
    gap: 16,
    padding: "16px 0",
    borderTop: "1px solid #E0DFD8",
    borderBottom: "1px solid #E0DFD8",
}

const metricBox: React.CSSProperties = {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 4,
}

const metricLabel: React.CSSProperties = {
    color: "#888",
    fontSize: 11,
    fontWeight: 500,
}

const metricVal: React.CSSProperties = {
    color: "#000",
    fontSize: 14,
    fontWeight: 700,
}

const holdingsList: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 12,
}

const holdingRow: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "12px 16px",
    background: "#fff",
    borderRadius: 12,
}

const holdingLeft: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 2,
}

const holdingName: React.CSSProperties = {
    color: "#000",
    fontSize: 15,
    fontWeight: 700,
}

const holdingDetail: React.CSSProperties = {
    color: "#888",
    fontSize: 12,
    fontWeight: 400,
}

const holdingRight: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    alignItems: "flex-end",
    gap: 2,
}

const holdingReturn: React.CSSProperties = {
    fontSize: 16,
    fontWeight: 800,
}

const holdingPrice: React.CSSProperties = {
    color: "#888",
    fontSize: 12,
    fontWeight: 400,
}

const emptyHolder: React.CSSProperties = {
    padding: "24px 0",
    textAlign: "center",
}

const emptyText: React.CSSProperties = {
    color: "#aaa",
    fontSize: 13,
}
