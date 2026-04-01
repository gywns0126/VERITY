import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

interface Props {
    dataUrl: string
}

export default function SignalBadge(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)

    useEffect(() => {
        if (!dataUrl) return
        fetch(dataUrl)
            .then((r) => r.json())
            .then(setData)
            .catch(console.error)
    }, [dataUrl])

    const alerts = data?.alerts || []
    const recs = data?.recommendations || []

    const buySignals = recs.filter(
        (r: any) => r.recommendation === "BUY"
    ).length
    const avoidSignals = recs.filter(
        (r: any) => r.recommendation === "AVOID"
    ).length
    const hasAlert = alerts.some(
        (a: any) => a.type === "STOP_LOSS"
    )

    return (
        <div style={container}>
            {/* 전체 시그널 요약 */}
            <div style={signalRow}>
                <div style={{ ...signalCard, background: "#0A1A00" }}>
                    <span style={{ ...signalNum, color: "#B5FF19" }}>
                        {buySignals}
                    </span>
                    <span style={signalLabel}>매수 신호</span>
                </div>
                <div style={{ ...signalCard, background: "#1A0000" }}>
                    <span style={{ ...signalNum, color: "#FF4D4D" }}>
                        {avoidSignals}
                    </span>
                    <span style={signalLabel}>회피 신호</span>
                </div>
                <div
                    style={{
                        ...signalCard,
                        background: hasAlert ? "#1A0A00" : "#111",
                    }}
                >
                    <span
                        style={{
                            ...signalNum,
                            color: hasAlert ? "#FF8C00" : "#555",
                        }}
                    >
                        {alerts.length}
                    </span>
                    <span style={signalLabel}>긴급 알림</span>
                </div>
            </div>

            {/* 알림 목록 */}
            {alerts.length > 0 && (
                <div style={alertList}>
                    {alerts.map((a: any, i: number) => (
                        <div key={i} style={alertRow}>
                            <span style={alertDot}>●</span>
                            <span style={alertText}>{a.message}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}

SignalBadge.defaultProps = {
    dataUrl: "",
}

addPropertyControls(SignalBadge, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: "",
    },
})

const font = "'Pretendard', -apple-system, sans-serif"

const container: React.CSSProperties = {
    width: "100%",
    fontFamily: font,
    display: "flex",
    flexDirection: "column",
    gap: 12,
}

const signalRow: React.CSSProperties = {
    display: "flex",
    gap: 12,
}

const signalCard: React.CSSProperties = {
    flex: 1,
    borderRadius: 16,
    padding: "24px 20px",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 6,
}

const signalNum: React.CSSProperties = {
    fontSize: 36,
    fontWeight: 900,
    lineHeight: 1,
}

const signalLabel: React.CSSProperties = {
    color: "#666",
    fontSize: 12,
    fontWeight: 500,
}

const alertList: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 8,
}

const alertRow: React.CSSProperties = {
    display: "flex",
    alignItems: "flex-start",
    gap: 8,
    padding: "12px 16px",
    background: "#1A0A00",
    borderRadius: 10,
    border: "1px solid #332200",
}

const alertDot: React.CSSProperties = {
    color: "#FF8C00",
    fontSize: 8,
    marginTop: 4,
}

const alertText: React.CSSProperties = {
    color: "#FFB84D",
    fontSize: 13,
    fontWeight: 500,
    lineHeight: 1.5,
}
