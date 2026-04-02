import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

interface Props {
    dataUrl: string
}

export default function DailyReport(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)

    useEffect(() => {
        if (!dataUrl) return
        fetch(dataUrl)
            .then((r) => r.text())
            .then((txt) => JSON.parse(txt.replace(/\bNaN\b/g, "null")))
            .then(setData)
            .catch(console.error)
    }, [dataUrl])

    const font = "'Pretendard', -apple-system, sans-serif"
    const report = data?.daily_report || {}
    const updated = data?.updated_at
        ? new Date(data.updated_at).toLocaleDateString("ko-KR", { month: "long", day: "numeric", weekday: "long" })
        : "—"

    const hasReport = report.market_summary || report.market_analysis

    if (!data) {
        return (
            <div style={{ ...card, minHeight: 200, alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: "#999", fontSize: 14, fontFamily: font }}>리포트 로딩 중...</span>
            </div>
        )
    }

    if (!hasReport) {
        return (
            <div style={{ ...card, minHeight: 120, alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: "#666", fontSize: 13, fontFamily: font }}>
                    AI 리포트는 장 마감 후(16시) 생성됩니다
                </span>
            </div>
        )
    }

    const sections = [
        { icon: "S", label: "시장 요약", text: report.market_summary, color: "#B5FF19" },
        { icon: "A", label: "시장 분석", text: report.market_analysis, color: "#60A5FA" },
        { icon: "T", label: "투자 전략", text: report.strategy, color: "#22C55E" },
        { icon: "!", label: "리스크 주의", text: report.risk_watch, color: "#EF4444" },
        { icon: "H", label: "주목 테마", text: report.hot_theme, color: "#F59E0B" },
        { icon: "→", label: "내일 전망", text: report.tomorrow_outlook, color: "#A78BFA" },
    ]

    return (
        <div style={card}>
            <div style={header}>
                <div>
                    <span style={{ color: "#fff", fontSize: 16, fontWeight: 800, fontFamily: font }}>
                        AI 일일 리포트
                    </span>
                    <span style={{ color: "#555", fontSize: 12, fontFamily: font, marginLeft: 10 }}>
                        {updated}
                    </span>
                </div>
                <span style={{ color: "#B5FF19", fontSize: 10, fontWeight: 600, fontFamily: font, background: "#1A2A00", padding: "3px 8px", borderRadius: 4 }}>
                    GEMINI AI
                </span>
            </div>

            {/* 시장 요약 배너 */}
            <div style={{ padding: "16px 20px", background: "linear-gradient(135deg, #0A1A00, #1A2A00)", borderBottom: "1px solid #222" }}>
                <span style={{ color: "#B5FF19", fontSize: 18, fontWeight: 800, fontFamily: font, lineHeight: "1.4" }}>
                    {report.market_summary || "—"}
                </span>
            </div>

            {/* 섹션들 */}
            <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 12 }}>
                {sections.slice(1).map((s, i) => (
                    s.text ? (
                        <div key={i} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
                            <div style={{
                                width: 28, height: 28, borderRadius: 6,
                                background: `${s.color}20`, border: `1px solid ${s.color}40`,
                                display: "flex", alignItems: "center", justifyContent: "center",
                                flexShrink: 0,
                            }}>
                                <span style={{ color: s.color, fontSize: 12, fontWeight: 800, fontFamily: font }}>
                                    {s.icon}
                                </span>
                            </div>
                            <div>
                                <div style={{ color: s.color, fontSize: 11, fontWeight: 700, fontFamily: font, marginBottom: 3 }}>
                                    {s.label}
                                </div>
                                <div style={{ color: "#ccc", fontSize: 13, fontFamily: font, lineHeight: "1.6" }}>
                                    {s.text}
                                </div>
                            </div>
                        </div>
                    ) : null
                ))}
            </div>

            <div style={{ padding: "8px 16px 12px", borderTop: "1px solid #1A1A1A" }}>
                <span style={{ color: "#444", fontSize: 10, fontFamily: font }}>
                    본 리포트는 AI가 자동 생성한 것으로, 투자 판단의 참고용입니다.
                </span>
            </div>
        </div>
    )
}

DailyReport.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
}

addPropertyControls(DailyReport, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    },
})

const card: React.CSSProperties = {
    width: "100%",
    background: "#111",
    borderRadius: 16,
    border: "1px solid #222",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    fontFamily: "'Pretendard', -apple-system, sans-serif",
}

const header: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "14px 20px",
    borderBottom: "1px solid #222",
}
