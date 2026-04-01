import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

interface Props {
    dataUrl: string
    title: string
}

export default function MarketBar(props: Props) {
    const { dataUrl, title } = props
    const [data, setData] = useState<any>(null)

    useEffect(() => {
        if (!dataUrl) return
        fetch(dataUrl)
            .then((r) => r.json())
            .then(setData)
            .catch(console.error)
    }, [dataUrl])

    const market = data?.market_summary || {}
    const kospi = market.kospi || {}
    const kosdaq = market.kosdaq || {}
    const updated = data?.updated_at
        ? new Date(data.updated_at).toLocaleString("ko-KR", {
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
          })
        : "—"

    return (
        <div style={container}>
            <span style={logo}>{title}</span>
            <div style={indexGroup}>
                <span style={indexLabel}>KOSPI</span>
                <span style={indexValue}>
                    {kospi.value?.toLocaleString() || "—"}
                </span>
                <span
                    style={{
                        ...changeBadge,
                        color:
                            (kospi.change_pct || 0) >= 0
                                ? "#B5FF19"
                                : "#FF4D4D",
                    }}
                >
                    {(kospi.change_pct || 0) >= 0 ? "+" : ""}
                    {kospi.change_pct?.toFixed(2) || "0.00"}%
                </span>
            </div>
            <div style={indexGroup}>
                <span style={indexLabel}>KOSDAQ</span>
                <span style={indexValue}>
                    {kosdaq.value?.toLocaleString() || "—"}
                </span>
                <span
                    style={{
                        ...changeBadge,
                        color:
                            (kosdaq.change_pct || 0) >= 0
                                ? "#B5FF19"
                                : "#FF4D4D",
                    }}
                >
                    {(kosdaq.change_pct || 0) >= 0 ? "+" : ""}
                    {kosdaq.change_pct?.toFixed(2) || "0.00"}%
                </span>
            </div>
            <span style={updatedText}>{updated}</span>
        </div>
    )
}

MarketBar.defaultProps = {
    dataUrl: "",
    title: "안심 AI 비서",
}

addPropertyControls(MarketBar, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: "",
    },
    title: {
        type: ControlType.String,
        title: "서비스명",
        defaultValue: "안심 AI 비서",
    },
})

const container: React.CSSProperties = {
    width: "100%",
    display: "flex",
    alignItems: "center",
    gap: 24,
    padding: "14px 32px",
    background: "#000000",
    fontFamily: "'Pretendard', -apple-system, sans-serif",
    borderBottom: "1px solid #222",
}

const logo: React.CSSProperties = {
    color: "#B5FF19",
    fontSize: 16,
    fontWeight: 700,
    letterSpacing: -0.5,
    whiteSpace: "nowrap",
}

const indexGroup: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 8,
}

const indexLabel: React.CSSProperties = {
    color: "#888",
    fontSize: 12,
    fontWeight: 500,
}

const indexValue: React.CSSProperties = {
    color: "#fff",
    fontSize: 14,
    fontWeight: 600,
}

const changeBadge: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 600,
}

const updatedText: React.CSSProperties = {
    color: "#555",
    fontSize: 11,
    marginLeft: "auto",
    whiteSpace: "nowrap",
}
