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
    const [detailTab, setDetailTab] = useState<"overview" | "technical" | "sentiment" | "macro">("overview")

    useEffect(() => {
        if (!dataUrl) return
        fetch(dataUrl)
            .then((r) => r.json())
            .then(setData)
            .catch(console.error)
    }, [dataUrl])

    const recs: any[] = data?.recommendations || []
    const macro: any = data?.macro || {}
    const filtered =
        tab === "all"
            ? recs
            : recs.filter((r) => r.recommendation === tab.toUpperCase())
    const stock = recs[selected] || null
    const mf = stock?.multi_factor || {}
    const tech = stock?.technical || {}
    const sent = stock?.sentiment || {}
    const flow = stock?.flow || {}
    const breakdown = mf.factor_breakdown || {}

    const multiScore = mf.multi_score || 0
    const multiColor =
        multiScore >= 65 ? "#B5FF19" : multiScore >= 45 ? "#FFD600" : "#FF4D4D"

    const radius = 48
    const stroke = 7
    const circumference = 2 * Math.PI * radius
    const progress = (multiScore / 100) * circumference

    const buyCount = recs.filter((r) => r.recommendation === "BUY").length
    const watchCount = recs.filter((r) => r.recommendation === "WATCH").length
    const avoidCount = recs.filter((r) => r.recommendation === "AVOID").length

    if (!data) {
        return (
            <div style={{ ...wrap, justifyContent: "center", alignItems: "center", minHeight: 500 }}>
                <span style={{ color: "#555", fontSize: 14 }}>데이터 로딩 중...</span>
            </div>
        )
    }

    const rec = stock?.recommendation || "WATCH"
    const recColor = rec === "BUY" ? "#B5FF19" : rec === "AVOID" ? "#FF4D4D" : "#888"

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
                        const ms = s.multi_factor?.multi_score || s.safety_score || 0
                        const msColor = ms >= 65 ? "#B5FF19" : ms >= 45 ? "#FFD600" : "#FF4D4D"
                        const rBadge = s.recommendation === "BUY" ? "#B5FF19" : s.recommendation === "AVOID" ? "#FF4D4D" : "#555"
                        return (
                            <div
                                key={s.ticker}
                                onClick={() => { setSelected(idx); setDetailTab("overview") }}
                                style={{
                                    ...listItem,
                                    background: isActive ? "#1A1A1A" : "transparent",
                                    borderLeft: isActive ? "3px solid #B5FF19" : "3px solid transparent",
                                    cursor: "pointer",
                                }}
                            >
                                <div style={listLeft}>
                                    <span style={{ ...listRecDot, background: rBadge }} />
                                    <div style={listNameWrap}>
                                        <span style={listName}>{s.name}</span>
                                        <span style={listTicker}>{s.ticker} · {s.market}</span>
                                    </div>
                                </div>
                                <div style={listRight}>
                                    <span style={listPrice}>{s.price?.toLocaleString()}원</span>
                                    <span style={{ ...listScore, color: msColor }}>{ms}점</span>
                                </div>
                            </div>
                        )
                    })}
                </div>

                {/* 우측: 상세 패널 */}
                {stock && (
                    <div style={detailPanel}>
                        {/* 헤더: 게이지 + 기본정보 */}
                        <div style={detailTop}>
                            <div style={gaugeWrap}>
                                <svg width={120} height={120} viewBox={`0 0 ${(radius + stroke) * 2} ${(radius + stroke) * 2}`}>
                                    <circle cx={radius + stroke} cy={radius + stroke} r={radius} fill="none" stroke="#222" strokeWidth={stroke} />
                                    <circle cx={radius + stroke} cy={radius + stroke} r={radius} fill="none" stroke={multiColor} strokeWidth={stroke}
                                        strokeDasharray={circumference} strokeDashoffset={circumference - progress}
                                        strokeLinecap="round" transform={`rotate(-90 ${radius + stroke} ${radius + stroke})`}
                                        style={{ transition: "stroke-dashoffset 0.5s ease" }} />
                                </svg>
                                <div style={gaugeCenter}>
                                    <span style={{ ...gaugeNum, color: multiColor }}>{multiScore}</span>
                                    <span style={gaugeGrade}>{mf.grade || "—"}</span>
                                </div>
                            </div>
                            <div style={detailInfo}>
                                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                    <span style={{ ...badge, background: recColor }}>{rec}</span>
                                    <span style={{ color: "#666", fontSize: 12 }}>{stock.market}</span>
                                </div>
                                <span style={detailName}>{stock.name}</span>
                                <span style={detailTicker}>{stock.ticker} · {stock.price?.toLocaleString()}원</span>
                                <p style={detailVerdict}>{stock.ai_verdict || "분석 대기 중"}</p>
                            </div>
                        </div>

                        {/* 5팩터 바 */}
                        <div style={factorBarSection}>
                            {(["fundamental", "technical", "sentiment", "flow", "macro"] as const).map((key) => {
                                const val = breakdown[key] || 0
                                const labels: Record<string, string> = { fundamental: "펀더멘털", technical: "기술적", sentiment: "뉴스", flow: "수급", macro: "매크로" }
                                const c = val >= 65 ? "#B5FF19" : val >= 45 ? "#FFD600" : "#FF4D4D"
                                return (
                                    <div key={key} style={factorItem}>
                                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                                            <span style={factorLabel}>{labels[key]}</span>
                                            <span style={{ ...factorVal, color: c }}>{val}</span>
                                        </div>
                                        <div style={factorBarBg}>
                                            <div style={{ ...factorBarFill, width: `${val}%`, background: c }} />
                                        </div>
                                    </div>
                                )
                            })}
                        </div>

                        {/* 상세 탭 */}
                        <div style={subTabBar}>
                            {([["overview", "개요"], ["technical", "기술적"], ["sentiment", "뉴스/수급"], ["macro", "매크로"]] as const).map(([k, l]) => (
                                <button key={k} onClick={() => setDetailTab(k)} style={{
                                    ...subTabBtn,
                                    borderBottom: detailTab === k ? "2px solid #B5FF19" : "2px solid transparent",
                                    color: detailTab === k ? "#fff" : "#666",
                                }}>
                                    {l}
                                </button>
                            ))}
                        </div>

                        <div style={tabContent}>
                            {detailTab === "overview" && (
                                <>
                                    <div style={insightSection}>
                                        <div style={insightRow}>
                                            <span style={goldBadge}>GOLD</span>
                                            <span style={insightText}>{stock.gold_insight || "데이터 수집 중"}</span>
                                        </div>
                                        <div style={insightRow}>
                                            <span style={silverBadge}>SILVER</span>
                                            <span style={insightText}>{stock.silver_insight || "데이터 수집 중"}</span>
                                        </div>
                                    </div>
                                    <div style={metricsGrid}>
                                        <MetricCard label="PER" value={stock.per?.toFixed(1) || "—"} />
                                        <MetricCard label="고점대비" value={`${stock.drop_from_high_pct?.toFixed(1)}%`}
                                            color={(stock.drop_from_high_pct || 0) <= -20 ? "#B5FF19" : "#fff"} />
                                        <MetricCard label="배당률" value={`${stock.div_yield?.toFixed(1)}%`} />
                                        <MetricCard label="거래대금" value={stock.trading_value ? `${(stock.trading_value / 1e8).toFixed(0)}억` : "—"} />
                                        <MetricCard label="시총" value={stock.market_cap ? `${(stock.market_cap / 1e12).toFixed(1)}조` : "—"} />
                                        <MetricCard label="안심점수" value={`${stock.safety_score || 0}`} />
                                    </div>
                                    {mf.all_signals?.length > 0 && (
                                        <div style={signalWrap}>
                                            {mf.all_signals.map((sig: string, i: number) => (
                                                <span key={i} style={signalTag}>{sig}</span>
                                            ))}
                                        </div>
                                    )}
                                </>
                            )}

                            {detailTab === "technical" && (
                                <>
                                    <div style={metricsGrid}>
                                        <MetricCard label="RSI(14)" value={tech.rsi?.toString() || "—"}
                                            color={tech.rsi <= 30 ? "#B5FF19" : tech.rsi >= 70 ? "#FF4D4D" : "#fff"} />
                                        <MetricCard label="MACD" value={tech.macd?.toString() || "—"}
                                            color={tech.macd_hist > 0 ? "#B5FF19" : "#FF4D4D"} />
                                        <MetricCard label="볼린저 위치" value={`${tech.bb_position}%`}
                                            color={tech.bb_position <= 20 ? "#B5FF19" : tech.bb_position >= 80 ? "#FF4D4D" : "#fff"} />
                                        <MetricCard label="거래량비" value={`${tech.vol_ratio}x`}
                                            color={tech.vol_ratio >= 2 ? "#FFD600" : "#fff"} />
                                        <MetricCard label="MA20" value={tech.ma20?.toLocaleString() || "—"} />
                                        <MetricCard label="MA60" value={tech.ma60?.toLocaleString() || "—"} />
                                    </div>
                                    <div style={{ marginTop: 12 }}>
                                        <span style={{ color: "#666", fontSize: 12 }}>이동평균선 배열</span>
                                        <div style={{ ...maBar, marginTop: 8 }}>
                                            {[["MA5", tech.ma5], ["MA20", tech.ma20], ["MA60", tech.ma60], ["MA120", tech.ma120]].map(([lbl, val]) => (
                                                <div key={lbl as string} style={maItem}>
                                                    <span style={{ color: "#888", fontSize: 10 }}>{lbl as string}</span>
                                                    <span style={{ color: Number(val) < (tech.price || 0) ? "#B5FF19" : "#FF4D4D", fontSize: 13, fontWeight: 700 }}>
                                                        {Number(val)?.toLocaleString()}
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                    {tech.signals?.length > 0 && (
                                        <div style={signalWrap}>
                                            {tech.signals.map((s: string, i: number) => (
                                                <span key={i} style={signalTag}>{s}</span>
                                            ))}
                                        </div>
                                    )}
                                </>
                            )}

                            {detailTab === "sentiment" && (
                                <>
                                    <div style={metricsGrid}>
                                        <MetricCard label="뉴스 감성" value={`${sent.score || 50}`}
                                            color={sent.score >= 60 ? "#B5FF19" : sent.score <= 40 ? "#FF4D4D" : "#FFD600"} />
                                        <MetricCard label="긍정 키워드" value={`${sent.positive || 0}건`} color="#B5FF19" />
                                        <MetricCard label="부정 키워드" value={`${sent.negative || 0}건`} color="#FF4D4D" />
                                        <MetricCard label="외국인" value={flow.foreign_net > 0 ? "순매수" : flow.foreign_net < 0 ? "순매도" : "중립"}
                                            color={flow.foreign_net > 0 ? "#B5FF19" : flow.foreign_net < 0 ? "#FF4D4D" : "#888"} />
                                        <MetricCard label="기관" value={flow.institution_net > 0 ? "순매수" : flow.institution_net < 0 ? "순매도" : "중립"}
                                            color={flow.institution_net > 0 ? "#B5FF19" : flow.institution_net < 0 ? "#FF4D4D" : "#888"} />
                                        <MetricCard label="수급 점수" value={`${flow.flow_score || 50}`} />
                                    </div>
                                    {sent.top_headlines?.length > 0 && (
                                        <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
                                            <span style={{ color: "#666", fontSize: 12, fontWeight: 600 }}>최근 뉴스</span>
                                            {sent.top_headlines.map((h: string, i: number) => (
                                                <div key={i} style={newsRow}>
                                                    <span style={{ color: "#aaa", fontSize: 12, lineHeight: 1.5 }}>{h}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </>
                            )}

                            {detailTab === "macro" && (
                                <>
                                    <div style={metricsGrid}>
                                        <MetricCard label="시장 분위기" value={macro.market_mood?.label || "—"}
                                            color={macro.market_mood?.score >= 60 ? "#B5FF19" : macro.market_mood?.score <= 40 ? "#FF4D4D" : "#FFD600"} />
                                        <MetricCard label="USD/KRW" value={`${macro.usd_krw?.value?.toLocaleString() || "—"}원`} />
                                        <MetricCard label="VIX" value={`${macro.vix?.value || "—"}`}
                                            color={macro.vix?.value > 25 ? "#FF4D4D" : macro.vix?.value < 18 ? "#B5FF19" : "#FFD600"} />
                                        <MetricCard label="WTI 원유" value={`$${macro.wti_oil?.value || "—"}`} />
                                        <MetricCard label="S&P500" value={`${macro.sp500?.change_pct >= 0 ? "+" : ""}${macro.sp500?.change_pct || 0}%`}
                                            color={macro.sp500?.change_pct >= 0 ? "#B5FF19" : "#FF4D4D"} />
                                        <MetricCard label="미국10년물" value={`${macro.us_10y?.value || "—"}%`} />
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}

function MetricCard({ label, value, color = "#fff" }: { label: string; value: string; color?: string }) {
    return (
        <div style={metricCard}>
            <span style={mLabel}>{label}</span>
            <span style={{ ...mValue, color }}>{value}</span>
        </div>
    )
}

StockDashboard.defaultProps = { dataUrl: DATA_URL }
addPropertyControls(StockDashboard, {
    dataUrl: { type: ControlType.String, title: "JSON URL", defaultValue: DATA_URL },
})

/* ─── Styles ─── */
const font = "'Pretendard', -apple-system, sans-serif"
const wrap: React.CSSProperties = { width: "100%", background: "#0A0A0A", borderRadius: 20, fontFamily: font, display: "flex", flexDirection: "column", overflow: "hidden" }
const tabBar: React.CSSProperties = { display: "flex", gap: 6, padding: "16px 20px 0" }
const tabBtn: React.CSSProperties = { border: "none", borderRadius: 8, padding: "7px 14px", fontSize: 12, fontWeight: 700, fontFamily: font, cursor: "pointer", transition: "all 0.2s" }
const body: React.CSSProperties = { display: "flex", gap: 0, minHeight: 560 }
const listPanel: React.CSSProperties = { width: 260, minWidth: 260, borderRight: "1px solid #1A1A1A", overflowY: "auto", padding: "12px 0", maxHeight: 600 }
const listItem: React.CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "11px 14px", transition: "all 0.15s" }
const listLeft: React.CSSProperties = { display: "flex", alignItems: "center", gap: 10 }
const listRecDot: React.CSSProperties = { width: 8, height: 8, borderRadius: 4, flexShrink: 0 }
const listNameWrap: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 2 }
const listName: React.CSSProperties = { color: "#fff", fontSize: 13, fontWeight: 600 }
const listTicker: React.CSSProperties = { color: "#555", fontSize: 10 }
const listRight: React.CSSProperties = { display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }
const listPrice: React.CSSProperties = { color: "#ccc", fontSize: 12, fontWeight: 600 }
const listScore: React.CSSProperties = { fontSize: 11, fontWeight: 700 }
const detailPanel: React.CSSProperties = { flex: 1, padding: "16px 20px", display: "flex", flexDirection: "column", gap: 16, overflowY: "auto" }
const detailTop: React.CSSProperties = { display: "flex", gap: 20, alignItems: "flex-start" }
const gaugeWrap: React.CSSProperties = { position: "relative", width: 120, height: 120, flexShrink: 0, display: "flex", justifyContent: "center", alignItems: "center" }
const gaugeCenter: React.CSSProperties = { position: "absolute", display: "flex", flexDirection: "column", alignItems: "center" }
const gaugeNum: React.CSSProperties = { fontSize: 28, fontWeight: 900, lineHeight: 1 }
const gaugeGrade: React.CSSProperties = { color: "#888", fontSize: 10, fontWeight: 500, marginTop: 2 }
const detailInfo: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 4, flex: 1, paddingTop: 4 }
const badge: React.CSSProperties = { color: "#000", fontSize: 11, fontWeight: 800, padding: "3px 10px", borderRadius: 6 }
const detailName: React.CSSProperties = { color: "#fff", fontSize: 24, fontWeight: 800, letterSpacing: -1, lineHeight: 1.1 }
const detailTicker: React.CSSProperties = { color: "#555", fontSize: 12 }
const detailVerdict: React.CSSProperties = { color: "#aaa", fontSize: 12, lineHeight: 1.5, margin: 0 }

const factorBarSection: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 8, padding: "12px 0", borderTop: "1px solid #1A1A1A", borderBottom: "1px solid #1A1A1A" }
const factorItem: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 4 }
const factorLabel: React.CSSProperties = { color: "#888", fontSize: 11, fontWeight: 500 }
const factorVal: React.CSSProperties = { fontSize: 11, fontWeight: 700 }
const factorBarBg: React.CSSProperties = { height: 4, background: "#222", borderRadius: 2, overflow: "hidden" }
const factorBarFill: React.CSSProperties = { height: "100%", borderRadius: 2, transition: "width 0.5s ease" }

const subTabBar: React.CSSProperties = { display: "flex", gap: 0 }
const subTabBtn: React.CSSProperties = { border: "none", background: "transparent", padding: "8px 16px", fontSize: 12, fontWeight: 600, fontFamily: font, cursor: "pointer", transition: "all 0.2s" }
const tabContent: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 12 }

const insightSection: React.CSSProperties = { display: "flex", flexDirection: "column", gap: 8 }
const insightRow: React.CSSProperties = { display: "flex", alignItems: "center", gap: 10 }
const goldBadge: React.CSSProperties = { background: "#FFD600", color: "#000", fontSize: 10, fontWeight: 800, padding: "3px 8px", borderRadius: 4, minWidth: 48, textAlign: "center" }
const silverBadge: React.CSSProperties = { background: "#999", color: "#000", fontSize: 10, fontWeight: 800, padding: "3px 8px", borderRadius: 4, minWidth: 48, textAlign: "center" }
const insightText: React.CSSProperties = { color: "#aaa", fontSize: 12 }

const metricsGrid: React.CSSProperties = { display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8 }
const metricCard: React.CSSProperties = { background: "#111", borderRadius: 10, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 4 }
const mLabel: React.CSSProperties = { color: "#666", fontSize: 10, fontWeight: 500 }
const mValue: React.CSSProperties = { color: "#fff", fontSize: 15, fontWeight: 700 }

const signalWrap: React.CSSProperties = { display: "flex", flexWrap: "wrap", gap: 6, marginTop: 4 }
const signalTag: React.CSSProperties = { background: "#0D1A00", border: "1px solid #1A2A00", color: "#B5FF19", fontSize: 11, fontWeight: 600, padding: "4px 10px", borderRadius: 6 }

const newsRow: React.CSSProperties = { background: "#111", borderRadius: 8, padding: "10px 12px" }
const maBar: React.CSSProperties = { display: "flex", gap: 8 }
const maItem: React.CSSProperties = { flex: 1, background: "#111", borderRadius: 8, padding: "10px 12px", display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }
