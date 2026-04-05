import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

interface Props {
    historyUrl: string
    maxRows: number
}

export default function HistoryTable(props: Props) {
    const { historyUrl, maxRows } = props
    const [history, setHistory] = useState<any[]>([])

    useEffect(() => {
        if (!historyUrl) return
        fetch(historyUrl)
            .then((r) => r.text())
            .then((txt) => JSON.parse(txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
            .then((data) => {
                const sorted = [...data].reverse()
                setHistory(sorted)
            })
            .catch(console.error)
    }, [historyUrl])

    const visible = history.slice(0, maxRows)

    return (
        <div style={card}>
            <div style={headerRow}>
                <span style={cardTitle}>매매 이력</span>
                <span style={countBadge}>{history.length}건</span>
            </div>

            {visible.length === 0 && (
                <span style={emptyText}>매매 이력이 없습니다</span>
            )}

            {visible.map((item: any, i: number) => {
                const isBuy = item.type === "BUY"
                const pnl = item.pnl || 0
                return (
                    <div key={i} style={row}>
                        <span
                            style={{
                                ...typeBadge,
                                background: isBuy ? "#B5FF19" : "#FF4D4D",
                            }}
                        >
                            {isBuy ? "매수" : "매도"}
                        </span>
                        <div style={rowCenter}>
                            <span style={rowName}>{item.name}</span>
                            <span style={rowDate}>{item.date}</span>
                        </div>
                        <div style={rowRight}>
                            <span style={rowPrice}>
                                {item.quantity}주 ×{" "}
                                {item.price?.toLocaleString()}원
                            </span>
                            {!isBuy && (
                                <span
                                    style={{
                                        ...pnlText,
                                        color:
                                            pnl >= 0
                                                ? "#B5FF19"
                                                : "#FF4D4D",
                                    }}
                                >
                                    {pnl >= 0 ? "+" : ""}
                                    {pnl.toLocaleString()}원
                                </span>
                            )}
                        </div>
                    </div>
                )
            })}

            {history.length > maxRows && (
                <span style={moreText}>
                    + {history.length - maxRows}건 더 있음
                </span>
            )}

            {/* 매도 이력 사유 */}
            {visible
                .filter((item: any) => item.type === "SELL" && item.reason)
                .slice(0, 3)
                .map((item: any, i: number) => (
                    <div key={`reason-${i}`} style={reasonRow}>
                        <span style={reasonLabel}>
                            {item.name} 매도 사유:
                        </span>
                        <span style={reasonText}>{item.reason}</span>
                    </div>
                ))}
        </div>
    )
}

HistoryTable.defaultProps = {
    historyUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/history.json",
    maxRows: 10,
}

addPropertyControls(HistoryTable, {
    historyUrl: {
        type: ControlType.String,
        title: "History JSON URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/history.json",
    },
    maxRows: {
        type: ControlType.Number,
        title: "최대 표시 수",
        defaultValue: 10,
        min: 3,
        max: 50,
        step: 1,
    },
})

const font = "'Pretendard', -apple-system, sans-serif"

const card: React.CSSProperties = {
    width: "100%",
    background: "#111",
    borderRadius: 20,
    padding: "28px 24px",
    fontFamily: font,
    display: "flex",
    flexDirection: "column",
    gap: 10,
    border: "1px solid #222",
}

const headerRow: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
}

const cardTitle: React.CSSProperties = {
    color: "#fff",
    fontSize: 13,
    fontWeight: 600,
}

const countBadge: React.CSSProperties = {
    color: "#888",
    fontSize: 12,
    fontWeight: 500,
    background: "#1A1A1A",
    padding: "2px 10px",
    borderRadius: 8,
}

const emptyText: React.CSSProperties = {
    color: "#555",
    fontSize: 13,
    textAlign: "center",
    padding: 24,
}

const row: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "10px 14px",
    background: "#0A0A0A",
    borderRadius: 10,
}

const typeBadge: React.CSSProperties = {
    color: "#000",
    fontSize: 11,
    fontWeight: 800,
    padding: "4px 10px",
    borderRadius: 6,
    minWidth: 36,
    textAlign: "center",
}

const rowCenter: React.CSSProperties = {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: 2,
}

const rowName: React.CSSProperties = {
    color: "#fff",
    fontSize: 14,
    fontWeight: 700,
}

const rowDate: React.CSSProperties = {
    color: "#999",
    fontSize: 11,
}

const rowRight: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    alignItems: "flex-end",
    gap: 2,
}

const rowPrice: React.CSSProperties = {
    color: "#888",
    fontSize: 12,
}

const pnlText: React.CSSProperties = {
    fontSize: 14,
    fontWeight: 800,
}

const moreText: React.CSSProperties = {
    color: "#aaa",
    fontSize: 12,
    textAlign: "center",
    padding: 8,
}

const reasonRow: React.CSSProperties = {
    display: "flex",
    gap: 8,
    padding: "8px 14px",
    background: "#1A1200",
    border: "1px solid #332A00",
    borderRadius: 8,
    alignItems: "center",
}

const reasonLabel: React.CSSProperties = {
    color: "#F59E0B",
    fontSize: 11,
    fontWeight: 700,
    whiteSpace: "nowrap",
}

const reasonText: React.CSSProperties = {
    color: "#888",
    fontSize: 12,
    fontWeight: 400,
}
