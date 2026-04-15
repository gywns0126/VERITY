import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"

interface Props {
    dataUrl: string
}

function bustPortfolioUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

function fetchPortfolioJson(url: string): Promise<any> {
    return fetch(bustPortfolioUrl(url), {
        cache: "no-store",
        mode: "cors",
        credentials: "omit",
    })
        .then((r) => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            return r.text()
        })
        .then((txt) =>
            JSON.parse(
                txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null"),
            ),
        )
}

export default function BacktestDashboard(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [activePeriod, setActivePeriod] = useState("7d")

    useEffect(() => {
        if (!dataUrl) return
        setLoading(true)
        setError(null)
        fetchPortfolioJson(dataUrl)
            .then(setData)
            .catch((e) => {
                setError("백테스트 데이터를 불러오지 못했습니다.")
            })
            .finally(() => setLoading(false))
    }, [dataUrl])

    const bt = data?.backtest_stats || {}
    const periods = bt.periods || {}
    const recs: any[] = bt.recommendations || []

    const periodKeys = Object.keys(periods)
    const selectedPeriod = periodKeys.includes(activePeriod) ? activePeriod : periodKeys[0] || ""

    useEffect(() => {
        if (!periodKeys.length) return
        if (!periodKeys.includes(activePeriod)) setActivePeriod(periodKeys[0])
    }, [activePeriod, periodKeys])

    if (loading) {
        return (
            <div style={container}>
                <div style={headerRow}>
                    <span style={titleStyle}>추천 성과 백테스트</span>
                </div>
                <div style={{ color: "#666", fontSize: 12, textAlign: "center", padding: 40 }}>
                    백테스트 데이터를 불러오는 중...
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div style={container}>
                <div style={headerRow}>
                    <span style={titleStyle}>추천 성과 백테스트</span>
                </div>
                <div style={{ color: "#FF6B6B", fontSize: 12, textAlign: "center", padding: 40 }}>{error}</div>
            </div>
        )
    }

    if (!periodKeys.length) {
        return (
            <div style={container}>
                <div style={headerRow}>
                    <span style={titleStyle}>추천 성과 백테스트</span>
                </div>
                <div style={{ color: "#555", fontSize: 12, textAlign: "center", padding: 40 }}>
                    백테스트 데이터가 아직 없습니다. history 스냅샷이 2일 이상 쌓인 후 full 모드 실행 시 생성됩니다.
                </div>
            </div>
        )
    }

    const active = periods[selectedPeriod] || {}
    const filteredRecs = recs.filter((r: any) => r.period === selectedPeriod)

    return (
        <div style={container}>
            <div style={headerRow}>
                <span style={titleStyle}>추천 성과 백테스트</span>
                <span style={{ color: "#444", fontSize: 9 }}>{bt.updated_at?.slice(0, 16) || ""}</span>
            </div>

            <div style={tabRow}>
                {periodKeys.map((pk) => (
                    <span
                        key={pk}
                        onClick={() => setActivePeriod(pk)}
                        style={{
                            ...tab,
                            color: activePeriod === pk ? "#B5FF19" : "#666",
                            borderBottom: activePeriod === pk ? "2px solid #B5FF19" : "2px solid transparent",
                        }}
                    >
                        {pk}
                    </span>
                ))}
            </div>

            <div style={metricsGrid}>
                <MetricBox
                    label="적중률"
                    value={active.hit_rate != null ? `${active.hit_rate}%` : "—"}
                    color={active.hit_rate >= 60 ? "#B5FF19" : active.hit_rate >= 40 ? "#FFD600" : "#FF4D4D"}
                />
                <MetricBox
                    label="평균 수익률"
                    value={active.avg_return != null ? `${active.avg_return >= 0 ? "+" : ""}${active.avg_return}%` : "—"}
                    color={active.avg_return >= 0 ? "#22C55E" : "#FF4D4D"}
                />
                <MetricBox label="종목 수" value={`${active.total_recs || 0}`} color="#888" />
                <MetricBox
                    label="샤프 비율"
                    value={active.sharpe != null ? `${active.sharpe}` : "—"}
                    color={active.sharpe >= 1 ? "#B5FF19" : active.sharpe >= 0 ? "#888" : "#FF4D4D"}
                />
                <MetricBox
                    label="최대 수익"
                    value={active.max_return != null ? `+${active.max_return}%` : "—"}
                    color="#22C55E"
                />
                <MetricBox
                    label="최대 손실"
                    value={active.min_return != null ? `${active.min_return}%` : "—"}
                    color="#FF4D4D"
                />
            </div>

            {active.hit_rate != null && (
                <div style={gaugeWrap}>
                    <div style={gaugeTrack}>
                        <div style={{ ...gaugeFill, width: `${Math.min(100, active.hit_rate)}%` }} />
                    </div>
                    <span style={{ color: "#555", fontSize: 9 }}>
                        {active.hits || 0}적중 / {active.total_recs || 0}종목
                    </span>
                </div>
            )}

            {filteredRecs.length > 0 && (
                <div style={tableWrap}>
                    <span style={{ color: "#666", fontSize: 11, fontWeight: 600, marginBottom: 6, display: "block" }}>
                        추천별 성과
                    </span>
                    {filteredRecs.slice(0, 10).map((r: any, i: number) => (
                        <div key={i} style={recRow}>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                <span style={{ color: "#fff", fontSize: 12, fontWeight: 600 }}>{r.name}</span>
                                <span style={{ color: "#555", fontSize: 9 }}>
                                    {r.rec_date} · {r.recommendation} · 브레인 {r.brain_score || "?"}
                                </span>
                            </div>
                            <div style={{ textAlign: "right" }}>
                                <div style={{
                                    color: r.return_pct >= 0 ? "#22C55E" : "#FF4D4D",
                                    fontSize: 14,
                                    fontWeight: 700,
                                }}>
                                    {r.return_pct >= 0 ? "+" : ""}{r.return_pct}%
                                </div>
                                <div style={{ color: "#555", fontSize: 9 }}>
                                    {r.rec_price?.toLocaleString()} → {r.current_price?.toLocaleString()}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}

function MetricBox({ label, value, color }: { label: string; value: string; color: string }) {
    return (
        <div style={metricBox}>
            <span style={{ color: "#666", fontSize: 9, fontWeight: 600 }}>{label}</span>
            <span style={{ color, fontSize: 18, fontWeight: 800, fontFamily: "'Inter', sans-serif" }}>{value}</span>
        </div>
    )
}

const DATA_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"

BacktestDashboard.defaultProps = {
    dataUrl: DATA_URL,
}

addPropertyControls(BacktestDashboard, {
    dataUrl: {
        type: ControlType.String,
        title: "데이터 URL",
        defaultValue: DATA_URL,
    },
})

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"

const container: React.CSSProperties = {
    width: "100%",
    background: "#111",
    border: "1px solid #222",
    borderRadius: 16,
    padding: 16,
    fontFamily: font,
    boxSizing: "border-box",
    display: "flex",
    flexDirection: "column",
    gap: 14,
}

const headerRow: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
}

const titleStyle: React.CSSProperties = {
    color: "#fff",
    fontSize: 14,
    fontWeight: 700,
    fontFamily: font,
}

const tabRow: React.CSSProperties = {
    display: "flex",
    gap: 16,
}

const tab: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
    paddingBottom: 4,
    fontFamily: font,
    transition: "color 0.15s",
}

const metricsGrid: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: 8,
}

const metricBox: React.CSSProperties = {
    background: "#0a0a0a",
    borderRadius: 10,
    padding: "10px 12px",
    display: "flex",
    flexDirection: "column",
    gap: 4,
    alignItems: "center",
    textAlign: "center",
}

const gaugeWrap: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 8,
}

const gaugeTrack: React.CSSProperties = {
    flex: 1,
    height: 8,
    borderRadius: 4,
    background: "#1a1a1a",
    overflow: "hidden",
}

const gaugeFill: React.CSSProperties = {
    height: "100%",
    borderRadius: 4,
    background: "linear-gradient(90deg, #FF4D4D, #FFD600, #B5FF19)",
    transition: "width 0.5s",
}

const tableWrap: React.CSSProperties = {
    borderTop: "1px solid #1a1a1a",
    paddingTop: 10,
}

const recRow: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "8px 0",
    borderBottom: "1px solid #1a1a1a",
}
