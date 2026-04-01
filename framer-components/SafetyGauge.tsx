import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

interface Props {
    dataUrl: string
    stockIndex: number
}

export default function SafetyGauge(props: Props) {
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
    const score = stock?.safety_score || 0

    const radius = 70
    const stroke = 10
    const circumference = 2 * Math.PI * radius
    const progress = (score / 100) * circumference
    const color =
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

    return (
        <div style={card}>
            <span style={cardTitle}>안심 점수</span>

            <div style={gaugeWrap}>
                <svg
                    width={180}
                    height={180}
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
                        stroke={color}
                        strokeWidth={stroke}
                        strokeDasharray={circumference}
                        strokeDashoffset={circumference - progress}
                        strokeLinecap="round"
                        transform={`rotate(-90 ${radius + stroke} ${radius + stroke})`}
                        style={{ transition: "stroke-dashoffset 0.8s ease" }}
                    />
                </svg>
                <div style={scoreCenterText}>
                    <span style={{ ...scoreNumber, color }}>{score}</span>
                    <span style={gradeText}>{grade}</span>
                </div>
            </div>

            {stock && (
                <span style={stockNameText}>
                    {stock.name} ({stock.ticker})
                </span>
            )}
        </div>
    )
}

SafetyGauge.defaultProps = {
    dataUrl: "",
    stockIndex: 0,
}

addPropertyControls(SafetyGauge, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: "",
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
    padding: "32px 28px",
    fontFamily: font,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 16,
}

const cardTitle: React.CSSProperties = {
    color: "#888",
    fontSize: 13,
    fontWeight: 600,
    alignSelf: "flex-start",
    letterSpacing: -0.3,
}

const gaugeWrap: React.CSSProperties = {
    position: "relative",
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
}

const scoreCenterText: React.CSSProperties = {
    position: "absolute",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
}

const scoreNumber: React.CSSProperties = {
    fontSize: 48,
    fontWeight: 900,
    lineHeight: 1,
}

const gradeText: React.CSSProperties = {
    color: "#888",
    fontSize: 13,
    fontWeight: 500,
    marginTop: 4,
}

const stockNameText: React.CSSProperties = {
    color: "#666",
    fontSize: 13,
    fontWeight: 400,
}
