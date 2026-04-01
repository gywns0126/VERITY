import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

const DATA_URL =
    "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"

interface Props {
    dataUrl: string
}

export default function StockDashboard(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [selected, setSelected] = useState(0)
    const [tab, setTab] = useState<"all" | "buy" | "watch" | "avoid">("all")

    useEffect(() => {
        if (!dataUrl) return
        fetch(dataUrl)
            .then((r) => r.json())
            .then(setData)
            .catch(console.error)
    }, [dataUrl])

    const recs: any[] = data?.recommendations || []
    const filtered =
        tab === "all"
            ? recs
            : recs.filter(
                  (r) => r.recommendation === tab.toUpperCase()
              )
    const stock = recs[selected] || null
    const score = stock?.safety_score || 0
    const scoreColor =
        score >= 70 ? "#B5FF19" : score >= 40 ? "#FFD600" : "#FF4D4D"
    const grade =
        score >= 80
            ? "매우 안전"
            : score >= 60
              ? "안전"
              : score >= 40
                ? "보통"
                : score >= 20
                  ? "주의"
                  : "위험"
    const rec = stock?.recommendation || "WATCH"
    const recColor =
        rec === "BUY" ? "#B5FF19" : rec === "AVOID" ? "#FF4D4D" : "#888"

    const radius = 52
    const stroke = 8
    const circumference = 2 * Math.PI * radius
    const progress = (score / 100) * circumference

    const buyCount = recs.filter((r) => r.recommendation === "BUY").length
    const watchCount = recs.filter((r) => r.recommendation === "WATCH").length
    const avoidCount = recs.filter((r) => r.recommendation === "AVOID").length

    if (!data) {
        return (
            <div style={{ ...wrap, justifyContent: "center", alignItems: "center", minHeight: 400 }}>
                <span style={{ color: "#555", fontSize: 14 }}>데이터 로딩 중...</span>
            </div>
        )
    }

    return (
        <div style={wrap}>
            {/* 탭 필터 */}
            <div style={tabBar}>
                {([
                    ["all", `전체 ${recs.length}`],
                    ["buy", `매수 ${buyCount}`],
                    ["watch", `관망 ${watchCount}`],
                    ["avoid", `회피 ${avoidCount}`],
                ] as const).map(([key, label]) => (
                    <button
                        key={key}
                        onClick={() => setTab(key)}
                        style={{
                            ...tabBtn,
                            background: tab === key ? "#B5FF19" : "#1A1A1A",
                            color: tab === key ? "#000" : "#888",
                        }}
                    >
                        {label}
                    </button>
                ))}
            </div>

            <div style={body}>
                {/* 좌측: 종목 리스트 */}
                <div style={listPanel}>
                    {filtered.map((s: any) => {
                        const idx = recs.indexOf(s)
                        const isActive = idx === selected
                        const sColor =
                            s.safety_score >= 70
                                ? "#B5FF19"
                                : s.safety_score >= 40
                                  ? "#FFD600"
                                  : "#FF4D4D"
                        const rBadge =
                            s.recommendation === "BUY"
                                ? "#B5FF19"
                                : s.recommendation === "AVOID"
                                  ? "#FF4D4D"
                                  : "#555"
                        return (
                            <div
                                key={s.ticker}
                                onClick={() => setSelected(idx)}
                                style={{
                                    ...listItem,
                                    background: isActive ? "#1A1A1A" : "transparent",
                                    borderLeft: isActive
                                        ? "3px solid #B5FF19"
                                        : "3px solid transparent",
                                    cursor: "pointer",
                                }}
                            >
                                <div style={listLeft}>
                                    <span
                                        style={{
                                            ...listRecDot,
                                            background: rBadge,
                                        }}
                                    />
                                    <div style={listNameWrap}>
                                        <span style={listName}>{s.name}</span>
                                        <span style={listTicker}>
                                            {s.ticker} · {s.market}
                                        </span>
                                    </div>
                                </div>
                                <div style={listRight}>
                                    <span style={listPrice}>
                                        {s.price?.toLocaleString()}원
                                    </span>
                                    <span style={{ ...listScore, color: sColor }}>
                                        {s.safety_score}점
                                    </span>
                                </div>
                            </div>
                        )
                    })}
                    {filtered.length === 0 && (
                        <div style={{ padding: 24, textAlign: "center" }}>
                            <span style={{ color: "#555", fontSize: 13 }}>
                                해당 종목이 없습니다
                            </span>
                        </div>
                    )}
                </div>

                {/* 우측: 상세 패널 */}
                {stock && (
                    <div style={detailPanel}>
                        {/* 상단: 게이지 + 기본 정보 */}
                        <div style={detailTop}>
                            <div style={gaugeWrap}>
                                <svg
                                    width={132}
                                    height={132}
                                    viewBox={`0 0 ${(radius + stroke) * 2} ${(radius + stroke) * 2}`}
                                >
                                    <circle
                                        cx={radius + stroke}
                                        cy={radius + stroke}
                                        r={radius}
                                        fill="none"
                                        stroke="#222"
                                        strokeWidth={stroke}
                                    />
                                    <circle
                                        cx={radius + stroke}
                                        cy={radius + stroke}
                                        r={radius}
                                        fill="none"
                                        stroke={scoreColor}
                                        strokeWidth={stroke}
                                        strokeDasharray={circumference}
                                        strokeDashoffset={circumference - progress}
                                        strokeLinecap="round"
                                        transform={`rotate(-90 ${radius + stroke} ${radius + stroke})`}
                                        style={{ transition: "stroke-dashoffset 0.5s ease" }}
                                    />
                                </svg>
                                <div style={gaugeCenter}>
                                    <span style={{ ...gaugeNum, color: scoreColor }}>
                                        {score}
                                    </span>
                                    <span style={gaugeGrade}>{grade}</span>
                                </div>
                            </div>

                            <div style={detailInfo}>
                                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                    <span
                                        style={{
                                            ...badge,
                                            background: recColor,
                                        }}
                                    >
                                        {rec}
                                    </span>
                                    <span style={{ color: "#666", fontSize: 12 }}>
                                        {stock.market}
                                    </span>
                                </div>
                                <span style={detailName}>{stock.name}</span>
                                <span style={detailTicker}>{stock.ticker}</span>
                                <p style={detailVerdict}>
                                    {stock.ai_verdict || "분석 대기 중"}
                                </p>
                            </div>
                        </div>

                        {/* 인사이트 */}
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

                        {/* 수치 그리드 */}
                        <div style={metricsGrid}>
                            <div style={metricCard}>
                                <span style={mLabel}>현재가</span>
                                <span style={mValue}>
                                    {stock.price?.toLocaleString()}원
                                </span>
                            </div>
                            <div style={metricCard}>
                                <span style={mLabel}>PER</span>
                                <span style={mValue}>
                                    {stock.per?.toFixed(1) || "—"}
                                </span>
                            </div>
                            <div style={metricCard}>
                                <span style={mLabel}>고점대비</span>
                                <span
                                    style={{
                                        ...mValue,
                                        color:
                                            (stock.drop_from_high_pct || 0) <= -20
                                                ? "#B5FF19"
                                                : "#fff",
                                    }}
                                >
                                    {stock.drop_from_high_pct?.toFixed(1)}%
                                </span>
                            </div>
                            <div style={metricCard}>
                                <span style={mLabel}>배당수익률</span>
                                <span style={mValue}>
                                    {stock.div_yield?.toFixed(1) || "—"}%
                                </span>
                            </div>
                            <div style={metricCard}>
                                <span style={mLabel}>거래대금</span>
                                <span style={mValue}>
                                    {stock.trading_value
                                        ? (stock.trading_value / 100_000_000).toFixed(0) + "억"
                                        : "—"}
                                </span>
                            </div>
                            <div style={metricCard}>
                                <span style={mLabel}>시가총액</span>
                                <span style={mValue}>
                                    {stock.market_cap
                                        ? (stock.market_cap / 1_000_000_000_000).toFixed(1) + "조"
                                        : "—"}
                                </span>
                            </div>
                        </div>

                        {/* 리스크 */}
                        {stock.risk_flags?.length > 0 && (
                            <div style={riskSection}>
                                <span style={{ color: "#FF4D4D", fontSize: 12, fontWeight: 700 }}>
                                    리스크 플래그
                                </span>
                                {stock.risk_flags.map((f: string, i: number) => (
                                    <span key={i} style={riskTag}>{f}</span>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    )
}

StockDashboard.defaultProps = {
    dataUrl: DATA_URL,
}

addPropertyControls(StockDashboard, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: DATA_URL,
    },
})

/* ─── Styles ─── */
const font = "'Pretendard', -apple-system, sans-serif"

const wrap: React.CSSProperties = {
    width: "100%",
    background: "#0A0A0A",
    borderRadius: 20,
    fontFamily: font,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
}

const tabBar: React.CSSProperties = {
    display: "flex",
    gap: 6,
    padding: "16px 20px 0",
}

const tabBtn: React.CSSProperties = {
    border: "none",
    borderRadius: 8,
    padding: "7px 14px",
    fontSize: 12,
    fontWeight: 700,
    fontFamily: font,
    cursor: "pointer",
    transition: "all 0.2s",
}

const body: React.CSSProperties = {
    display: "flex",
    gap: 0,
    minHeight: 480,
}

const listPanel: React.CSSProperties = {
    width: 280,
    minWidth: 280,
    borderRight: "1px solid #1A1A1A",
    overflowY: "auto",
    padding: "12px 0",
    maxHeight: 520,
}

const listItem: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "12px 16px",
    transition: "all 0.15s",
}

const listLeft: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 10,
}

const listRecDot: React.CSSProperties = {
    width: 8,
    height: 8,
    borderRadius: 4,
    flexShrink: 0,
}

const listNameWrap: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 2,
}

const listName: React.CSSProperties = {
    color: "#fff",
    fontSize: 14,
    fontWeight: 600,
}

const listTicker: React.CSSProperties = {
    color: "#555",
    fontSize: 11,
    fontWeight: 400,
}

const listRight: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    alignItems: "flex-end",
    gap: 2,
}

const listPrice: React.CSSProperties = {
    color: "#ccc",
    fontSize: 13,
    fontWeight: 600,
}

const listScore: React.CSSProperties = {
    fontSize: 11,
    fontWeight: 700,
}

const detailPanel: React.CSSProperties = {
    flex: 1,
    padding: "20px 24px",
    display: "flex",
    flexDirection: "column",
    gap: 20,
    overflowY: "auto",
}

const detailTop: React.CSSProperties = {
    display: "flex",
    gap: 24,
    alignItems: "flex-start",
}

const gaugeWrap: React.CSSProperties = {
    position: "relative",
    width: 132,
    height: 132,
    flexShrink: 0,
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
}

const gaugeCenter: React.CSSProperties = {
    position: "absolute",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
}

const gaugeNum: React.CSSProperties = {
    fontSize: 36,
    fontWeight: 900,
    lineHeight: 1,
}

const gaugeGrade: React.CSSProperties = {
    color: "#888",
    fontSize: 11,
    fontWeight: 500,
    marginTop: 3,
}

const detailInfo: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 6,
    flex: 1,
    paddingTop: 8,
}

const badge: React.CSSProperties = {
    color: "#000",
    fontSize: 11,
    fontWeight: 800,
    padding: "3px 10px",
    borderRadius: 6,
}

const detailName: React.CSSProperties = {
    color: "#fff",
    fontSize: 28,
    fontWeight: 800,
    letterSpacing: -1,
    lineHeight: 1.1,
}

const detailTicker: React.CSSProperties = {
    color: "#555",
    fontSize: 13,
}

const detailVerdict: React.CSSProperties = {
    color: "#aaa",
    fontSize: 13,
    lineHeight: 1.5,
    margin: 0,
}

const insightSection: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 8,
    padding: "12px 0",
    borderTop: "1px solid #1A1A1A",
    borderBottom: "1px solid #1A1A1A",
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
}

const metricsGrid: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: "1fr 1fr 1fr",
    gap: 10,
}

const metricCard: React.CSSProperties = {
    background: "#111",
    borderRadius: 12,
    padding: "14px 16px",
    display: "flex",
    flexDirection: "column",
    gap: 6,
}

const mLabel: React.CSSProperties = {
    color: "#666",
    fontSize: 11,
    fontWeight: 500,
}

const mValue: React.CSSProperties = {
    color: "#fff",
    fontSize: 16,
    fontWeight: 700,
}

const riskSection: React.CSSProperties = {
    display: "flex",
    flexWrap: "wrap",
    gap: 6,
    alignItems: "center",
}

const riskTag: React.CSSProperties = {
    background: "#2A0000",
    color: "#FF4D4D",
    fontSize: 11,
    fontWeight: 600,
    padding: "4px 10px",
    borderRadius: 6,
}
