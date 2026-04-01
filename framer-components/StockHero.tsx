import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

interface Props {
    dataUrl: string
    stockIndex: number
}

export default function StockHero(props: Props) {
    const { dataUrl, stockIndex } = props
    const [data, setData] = useState<any>(null)

    useEffect(() => {
        if (!dataUrl) return
        fetch(dataUrl)
            .then((r) => r.json())
            .then(setData)
            .catch(console.error)
    }, [dataUrl])

    const recs = data?.recommendations || []
    const stock = recs[stockIndex] || null

    if (!stock) {
        return (
            <div style={card}>
                <span style={emptyText}>
                    JSON URL을 연결하면 종목 분석이 표시됩니다
                </span>
            </div>
        )
    }

    const score = stock.safety_score || 0
    const scoreColor =
        score >= 70 ? "#B5FF19" : score >= 40 ? "#FFD600" : "#FF4D4D"
    const rec = stock.recommendation || "WATCH"
    const recColor =
        rec === "BUY"
            ? "#B5FF19"
            : rec === "AVOID"
              ? "#FF4D4D"
              : "#888"

    return (
        <div style={card}>
            {/* 상단: 추천 배지 + 시장 */}
            <div style={topRow}>
                <span style={{ ...recBadge, background: recColor }}>
                    {rec}
                </span>
                <span style={marketLabel}>{stock.market}</span>
            </div>

            {/* 종목명 + 코드 */}
            <div style={nameRow}>
                <span style={stockName}>{stock.name}</span>
                <span style={stockCode}>{stock.ticker}</span>
            </div>

            {/* 안심 점수 */}
            <div style={scoreSection}>
                <span style={scoreLabel}>안심 점수</span>
                <div style={scoreBarBg}>
                    <div
                        style={{
                            ...scoreBarFill,
                            width: `${score}%`,
                            background: scoreColor,
                        }}
                    />
                </div>
                <span style={{ ...scoreNum, color: scoreColor }}>
                    {score}
                </span>
            </div>

            {/* AI 한줄평 */}
            <p style={verdict}>{stock.ai_verdict || "분석 대기 중"}</p>

            {/* Gold / Silver 데이터 */}
            <div style={insightSection}>
                <div style={insightRow}>
                    <span style={goldBadge}>GOLD</span>
                    <span style={insightText}>
                        {stock.gold_insight || "공시 데이터 수집 중"}
                    </span>
                </div>
                <div style={insightRow}>
                    <span style={silverBadge}>SILVER</span>
                    <span style={insightText}>
                        {stock.silver_insight || "시장 데이터 수집 중"}
                    </span>
                </div>
            </div>

            {/* 하단 수치 */}
            <div style={metricsRow}>
                <div style={metricBox}>
                    <span style={metricLabel}>현재가</span>
                    <span style={metricValue}>
                        {stock.price?.toLocaleString() || "—"}원
                    </span>
                </div>
                <div style={metricBox}>
                    <span style={metricLabel}>PER</span>
                    <span style={metricValue}>
                        {stock.per?.toFixed(1) || "—"}
                    </span>
                </div>
                <div style={metricBox}>
                    <span style={metricLabel}>PBR</span>
                    <span style={metricValue}>
                        {stock.pbr?.toFixed(2) || "—"}
                    </span>
                </div>
                <div style={metricBox}>
                    <span style={metricLabel}>고점대비</span>
                    <span
                        style={{
                            ...metricValue,
                            color:
                                (stock.drop_from_high_pct || 0) <= -20
                                    ? "#B5FF19"
                                    : "#fff",
                        }}
                    >
                        {stock.drop_from_high_pct?.toFixed(1) || "—"}%
                    </span>
                </div>
            </div>
        </div>
    )
}

StockHero.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    stockIndex: 0,
}

addPropertyControls(StockHero, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    },
    stockIndex: {
        type: ControlType.Number,
        title: "종목 순번",
        defaultValue: 0,
        min: 0,
        max: 9,
        step: 1,
    },
})

const font = "'Pretendard', -apple-system, sans-serif"

const card: React.CSSProperties = {
    width: "100%",
    background: "#000",
    borderRadius: 20,
    padding: "36px 32px",
    fontFamily: font,
    display: "flex",
    flexDirection: "column",
    gap: 20,
}

const emptyText: React.CSSProperties = {
    color: "#555",
    fontSize: 14,
    textAlign: "center",
    padding: 40,
}

const topRow: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 10,
}

const recBadge: React.CSSProperties = {
    color: "#000",
    fontSize: 11,
    fontWeight: 800,
    padding: "4px 10px",
    borderRadius: 6,
    letterSpacing: 0.5,
}

const marketLabel: React.CSSProperties = {
    color: "#666",
    fontSize: 12,
    fontWeight: 500,
}

const nameRow: React.CSSProperties = {
    display: "flex",
    alignItems: "baseline",
    gap: 12,
}

const stockName: React.CSSProperties = {
    color: "#fff",
    fontSize: 32,
    fontWeight: 800,
    letterSpacing: -1,
}

const stockCode: React.CSSProperties = {
    color: "#555",
    fontSize: 14,
    fontWeight: 400,
}

const scoreSection: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 12,
}

const scoreLabel: React.CSSProperties = {
    color: "#888",
    fontSize: 12,
    fontWeight: 500,
    whiteSpace: "nowrap",
}

const scoreBarBg: React.CSSProperties = {
    flex: 1,
    height: 6,
    background: "#222",
    borderRadius: 3,
    overflow: "hidden",
}

const scoreBarFill: React.CSSProperties = {
    height: "100%",
    borderRadius: 3,
    transition: "width 0.6s ease",
}

const scoreNum: React.CSSProperties = {
    fontSize: 24,
    fontWeight: 800,
    minWidth: 36,
    textAlign: "right",
}

const verdict: React.CSSProperties = {
    color: "#ccc",
    fontSize: 15,
    fontWeight: 400,
    lineHeight: 1.6,
    margin: 0,
}

const insightSection: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 8,
}

const insightRow: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 10,
}

const goldBadge: React.CSSProperties = {
    background: "#FFD600",
    color: "#000",
    fontSize: 10,
    fontWeight: 800,
    padding: "3px 8px",
    borderRadius: 4,
    minWidth: 48,
    textAlign: "center",
}

const silverBadge: React.CSSProperties = {
    background: "#999",
    color: "#000",
    fontSize: 10,
    fontWeight: 800,
    padding: "3px 8px",
    borderRadius: 4,
    minWidth: 48,
    textAlign: "center",
}

const insightText: React.CSSProperties = {
    color: "#aaa",
    fontSize: 13,
    fontWeight: 400,
}

const metricsRow: React.CSSProperties = {
    display: "flex",
    gap: 16,
    paddingTop: 12,
    borderTop: "1px solid #222",
}

const metricBox: React.CSSProperties = {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 4,
}

const metricLabel: React.CSSProperties = {
    color: "#666",
    fontSize: 11,
    fontWeight: 500,
}

const metricValue: React.CSSProperties = {
    color: "#fff",
    fontSize: 16,
    fontWeight: 700,
}
