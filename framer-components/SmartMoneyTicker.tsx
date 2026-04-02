import { useState, useEffect, useRef } from "react"
import { addPropertyControls, ControlType } from "framer"

interface Props {
    dataUrl: string
    speed: number
}

interface FlowItem {
    name: string
    ticker: string
    signal: string
    score: number
    type: "foreign" | "institution" | "both"
}

export default function SmartMoneyTicker(props: Props) {
    const { dataUrl, speed } = props
    const [items, setItems] = useState<FlowItem[]>([])
    const [offset, setOffset] = useState(0)
    const containerRef = useRef<HTMLDivElement>(null)
    const contentRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        if (!dataUrl) return
        fetch(dataUrl)
            .then((r) => r.text())
            .then((txt) => JSON.parse(txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
            .then((data) => {
                const recs: any[] = data?.recommendations || []
                const flowItems: FlowItem[] = []

                for (const stock of recs) {
                    const flow = stock.flow || {}
                    const fs = flow.flow_score || 50
                    const signals: string[] = flow.flow_signals || []

                    if (fs >= 60 || signals.length > 0) {
                        const isForeign = signals.some((s: string) => s.includes("외국인"))
                        const isInst = signals.some((s: string) => s.includes("기관"))
                        const type = isForeign && isInst ? "both" : isForeign ? "foreign" : "institution"

                        const mainSignal = signals[0] || `수급 ${fs}점`

                        flowItems.push({
                            name: stock.name,
                            ticker: stock.ticker,
                            signal: mainSignal,
                            score: fs,
                            type,
                        })
                    }
                }

                flowItems.sort((a, b) => b.score - a.score)
                setItems(flowItems.slice(0, 15))
            })
            .catch(() => {})
    }, [dataUrl])

    useEffect(() => {
        if (items.length === 0) return
        const interval = setInterval(() => {
            setOffset((prev) => {
                const contentWidth = contentRef.current?.scrollWidth || 1000
                const next = prev - 1
                if (Math.abs(next) > contentWidth / 2) return 0
                return next
            })
        }, 50 / (speed || 1))
        return () => clearInterval(interval)
    }, [items, speed])

    if (items.length === 0) {
        return (
            <div style={styles.container}>
                <span style={styles.label}>SMART MONEY</span>
                <span style={{ color: "#444", fontSize: 11 }}>수급 데이터 대기 중...</span>
            </div>
        )
    }

    const doubled = [...items, ...items]

    return (
        <div style={styles.container} ref={containerRef}>
            <span style={styles.label}>SMART MONEY</span>
            <div style={styles.trackWrap}>
                <div
                    ref={contentRef}
                    style={{
                        ...styles.track,
                        transform: `translateX(${offset}px)`,
                    }}
                >
                    {doubled.map((item, i) => {
                        const typeIcon = item.type === "foreign" ? "🏦" : item.type === "institution" ? "🏢" : "⚡"
                        const typeLabel = item.type === "foreign" ? "외국인" : item.type === "institution" ? "기관" : "외국인+기관"
                        const scoreColor = item.score >= 70 ? "#B5FF19" : item.score >= 60 ? "#22C55E" : "#888"

                        return (
                            <div key={`${item.ticker}-${i}`} style={styles.item}>
                                <span style={{ fontSize: 12 }}>{typeIcon}</span>
                                <span style={styles.itemName}>{item.name}</span>
                                <span style={{ ...styles.itemSignal, color: scoreColor }}>
                                    {item.signal}
                                </span>
                                <span style={styles.divider}>·</span>
                            </div>
                        )
                    })}
                </div>
            </div>
        </div>
    )
}

SmartMoneyTicker.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    speed: 1,
}

addPropertyControls(SmartMoneyTicker, {
    dataUrl: {
        type: ControlType.String,
        title: "Data URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    },
    speed: {
        type: ControlType.Number,
        title: "속도",
        defaultValue: 1,
        min: 0.5,
        max: 3,
        step: 0.5,
    },
})

const styles: Record<string, React.CSSProperties> = {
    container: {
        width: "100%",
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "6px 20px",
        background: "#050505",
        fontFamily: "'Inter', 'Pretendard', -apple-system, sans-serif",
        borderBottom: "1px solid #111",
        overflow: "hidden",
    },
    label: {
        color: "#333",
        fontSize: 9,
        fontWeight: 800,
        letterSpacing: "0.08em",
        whiteSpace: "nowrap",
        flexShrink: 0,
    },
    trackWrap: {
        flex: 1,
        overflow: "hidden",
        position: "relative",
    },
    track: {
        display: "flex",
        alignItems: "center",
        gap: 0,
        whiteSpace: "nowrap",
        transition: "none",
    },
    item: {
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "0 6px",
        flexShrink: 0,
    },
    itemName: {
        color: "#999",
        fontSize: 11,
        fontWeight: 600,
    },
    itemSignal: {
        fontSize: 10,
        fontWeight: 500,
    },
    divider: {
        color: "#222",
        fontSize: 10,
        padding: "0 4px",
    },
}
