import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"

/** Framer 단일 파일 붙여넣기용 인라인 (fetchPortfolioJson.ts와 동일 로직 — 수정 시 맞춰 주세요) */
function bustPortfolioUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

const PORTFOLIO_FETCH_INIT: RequestInit = {
    cache: "no-store",
    mode: "cors",
    credentials: "omit",
}

function fetchPortfolioJson(url: string): Promise<any> {
    return fetch(bustPortfolioUrl(url), PORTFOLIO_FETCH_INIT)
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

const DATA_URL =
    "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"
const API_BASE = "https://verity-api.vercel.app"

interface Props {
    dataUrl: string
}

export default function StockDashboard(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [selected, setSelected] = useState(0)
    const [tab, setTab] = useState<"all" | "buy" | "watch" | "avoid">("all")
    const [detailTab, setDetailTab] = useState<
        "overview" | "brain" | "technical" | "sentiment" | "macro" | "predict" | "timing" | "niche" | "property"
    >("overview")

    useEffect(() => {
        if (!dataUrl) return
        fetchPortfolioJson(dataUrl).then(setData).catch(console.error)
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

    const Sparkline = ({ data, width = 60, height = 24, color = "#888" }: { data: number[]; width?: number; height?: number; color?: string }) => {
        if (!data || data.length < 2) return null
        const min = Math.min(...data)
        const max = Math.max(...data)
        const range = max - min || 1
        const points = data.map((v, i) => `${(i / (data.length - 1)) * width},${height - ((v - min) / range) * height}`).join(" ")
        return (
            <svg width={width} height={height} style={{ display: "block" }}>
                <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
            </svg>
        )
    }

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
                        const whyText = s.gold_insight || s.silver_insight || ""
                        const whyIsGold = !!s.gold_insight
                        const hasClaude = !!s.claude_analysis
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
                                <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1, minWidth: 0 }}>
                                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                        <div style={listLeft}>
                                            <span style={{ ...listRecDot, background: rBadge }} />
                                            <div style={listNameWrap}>
                                                <span style={listName}>{s.name}</span>
                                                <span style={listTicker}>{s.ticker} · {s.market}{hasClaude ? " · 🔬" : ""}</span>
                                            </div>
                                        </div>
                                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                            {s.sparkline?.length > 1 && (
                                                <Sparkline data={s.sparkline} width={48} height={20}
                                                    color={s.sparkline[s.sparkline.length - 1] >= s.sparkline[0] ? "#22C55E" : "#EF4444"} />
                                            )}
                                            <div style={listRight}>
                                                <span style={listPrice}>{s.price?.toLocaleString()}원</span>
                                                <span style={{ ...listScore, color: msColor }}>{ms}점</span>
                                            </div>
                                        </div>
                                    </div>
                                    {whyText && (
                                        <div style={{
                                            display: "flex", alignItems: "center", gap: 4,
                                            paddingLeft: 18,
                                        }}>
                                            <span style={{
                                                fontSize: 8, fontWeight: 800, padding: "1px 4px", borderRadius: 3,
                                                background: whyIsGold ? "#FFD600" : "#666",
                                                color: "#000", lineHeight: 1.2, flexShrink: 0,
                                            }}>
                                                {whyIsGold ? "G" : "S"}
                                            </span>
                                            <span style={{
                                                fontSize: 10, color: "#777", lineHeight: 1.2,
                                                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                                            }}>
                                                {whyText}
                                            </span>
                                        </div>
                                    )}
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
                                {stock.sparkline?.length > 1 && (
                                    <div style={{ marginTop: 4 }}>
                                        <Sparkline data={stock.sparkline} width={180} height={36}
                                            color={stock.sparkline[stock.sparkline.length - 1] >= stock.sparkline[0] ? "#22C55E" : "#EF4444"} />
                                    </div>
                                )}
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
                            {([["overview", "개요"], ["brain", "브레인"], ["timing", "매매시점"], ["technical", "기술적"], ["sentiment", "뉴스/수급"], ["macro", "매크로"], ["property", "부동산"], ["niche", "틈새"], ["predict", "예측"]] as const).map(([k, l]) => (
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
                                        {stock.claude_analysis && (
                                            <div style={{ marginTop: 8, padding: "8px 10px", background: stock.claude_analysis.agrees ? "#0A1A0A" : "#1A0A0A", border: `1px solid ${stock.claude_analysis.agrees ? "#1A3A1A" : "#3A1A1A"}`, borderRadius: 8 }}>
                                                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                                                    <span style={{ background: "#6B21A8", color: "#E9D5FF", fontSize: 9, fontWeight: 800, padding: "2px 6px", borderRadius: 4, fontFamily: font }}>CLAUDE</span>
                                                    <span style={{ color: stock.claude_analysis.agrees ? "#22C55E" : "#F59E0B", fontSize: 10, fontWeight: 700, fontFamily: font }}>
                                                        {stock.claude_analysis.agrees ? "Gemini 동의" : "Gemini 반론"}
                                                    </span>
                                                    {stock.claude_analysis.override && (
                                                        <span style={{ color: "#EF4444", fontSize: 10, fontWeight: 800, fontFamily: font }}>
                                                            → {stock.claude_analysis.override}
                                                        </span>
                                                    )}
                                                </div>
                                                <span style={{ color: "#ccc", fontSize: 11, lineHeight: "1.5", fontFamily: font }}>{stock.claude_analysis.verdict}</span>
                                                {stock.claude_analysis.conviction_note && (
                                                    <div style={{ color: "#888", fontSize: 10, marginTop: 4, fontFamily: font }}>{stock.claude_analysis.conviction_note}</div>
                                                )}
                                                {stock.claude_analysis.hidden_risks?.length > 0 && (
                                                    <div style={{ color: "#EF4444", fontSize: 10, marginTop: 4, fontFamily: font }}>숨겨진 리스크: {stock.claude_analysis.hidden_risks.join(" · ")}</div>
                                                )}
                                                {stock.claude_analysis.hidden_opportunities?.length > 0 && (
                                                    <div style={{ color: "#22C55E", fontSize: 10, marginTop: 2, fontFamily: font }}>숨겨진 기회: {stock.claude_analysis.hidden_opportunities.join(" · ")}</div>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                    <div style={metricsGrid}>
                                        <MetricCard label="PER" value={stock.per?.toFixed(1) || "—"} />
                                        <MetricCard label="고점대비" value={`${stock.drop_from_high_pct?.toFixed(1)}%`}
                                            color={(stock.drop_from_high_pct || 0) <= -20 ? "#B5FF19" : "#fff"} />
                                        <MetricCard label="배당률" value={`${stock.div_yield?.toFixed(1)}%`} />
                                        <MetricCard label="거래대금" value={stock.trading_value ? `${(stock.trading_value / 1e8).toFixed(0)}억` : "—"} />
                                        <MetricCard label="시총" value={stock.market_cap ? `${(stock.market_cap / 1e12).toFixed(1)}조` : "—"} />
                                        <MetricCard label="안심점수" value={`${stock.safety_score || 0}`} />
                                        <MetricCard label="부채비율" value={stock.debt_ratio ? `${stock.debt_ratio.toFixed(0)}%` : "—"}
                                            color={(stock.debt_ratio || 0) > 100 ? "#FF4D4D" : "#22C55E"} />
                                        <MetricCard label="영업이익률" value={stock.operating_margin ? `${(stock.operating_margin * 100).toFixed(1)}%` : "—"}
                                            color={(stock.operating_margin || 0) > 0.1 ? "#22C55E" : (stock.operating_margin || 0) < 0 ? "#FF4D4D" : "#FFD600"} />
                                        <MetricCard label="ROE" value={stock.roe ? `${(stock.roe * 100).toFixed(1)}%` : "—"}
                                            color={(stock.roe || 0) > 0.15 ? "#22C55E" : (stock.roe || 0) < 0 ? "#FF4D4D" : "#fff"} />
                                    </div>

                                    {/* 실적발표일 */}
                                    {stock.earnings?.next_earnings && (
                                        <div style={{ display: "flex", alignItems: "center", gap: 8, background: "#1A1200", border: "1px solid #332A00", borderRadius: 8, padding: "8px 12px", marginTop: 4 }}>
                                            <span style={{ color: "#FFD600", fontSize: 13, fontWeight: 700 }}>실적발표</span>
                                            <span style={{ color: "#ccc", fontSize: 12 }}>{stock.earnings.next_earnings}</span>
                                        </div>
                                    )}

                                    {/* 타이밍 요약 */}
                                    {stock.timing && (
                                        <div style={{ display: "flex", alignItems: "center", gap: 12, background: "#111", borderRadius: 10, padding: "10px 14px", marginTop: 4 }}>
                                            <div style={{ width: 36, height: 36, borderRadius: 18, background: stock.timing.color || "#888", display: "flex", alignItems: "center", justifyContent: "center" }}>
                                                <span style={{ color: "#000", fontSize: 14, fontWeight: 900 }}>{stock.timing.timing_score}</span>
                                            </div>
                                            <div style={{ flex: 1 }}>
                                                <span style={{ color: stock.timing.color || "#888", fontSize: 13, fontWeight: 700 }}>
                                                    {stock.timing.label || "—"}
                                                </span>
                                                <span style={{ color: "#666", fontSize: 11, marginLeft: 8 }}>
                                                    {stock.timing.reasons?.[0] || ""}
                                                </span>
                                            </div>
                                        </div>
                                    )}
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

                            {detailTab === "sentiment" && (() => {
                                const social = stock?.social_sentiment || {}
                                const hasSSocial = social.score != null
                                const newsS = social.news || {}
                                const commS = social.community || {}
                                const redditS = social.reddit || {}
                                return (
                                    <>
                                        <div style={metricsGrid}>
                                            {hasSSocial ? (
                                                <>
                                                    <MetricCard label="종합 감성" value={`${social.score}`}
                                                        color={social.score >= 60 ? "#B5FF19" : social.score <= 40 ? "#FF4D4D" : "#FFD600"} />
                                                    <MetricCard label="추세" value={social.trend === "bullish" ? "강세" : social.trend === "bearish" ? "약세" : "중립"}
                                                        color={social.trend === "bullish" ? "#B5FF19" : social.trend === "bearish" ? "#FF4D4D" : "#888"} />
                                                    <MetricCard label="뉴스" value={`${newsS.score || sent.score || 50}`}
                                                        color={((newsS.score || sent.score || 50)) >= 60 ? "#B5FF19" : ((newsS.score || sent.score || 50)) <= 40 ? "#FF4D4D" : "#FFD600"} />
                                                    <MetricCard label="커뮤니티" value={`${commS.score || "—"}`}
                                                        color={commS.score >= 60 ? "#B5FF19" : commS.score <= 40 ? "#FF4D4D" : "#888"} />
                                                    <MetricCard label="Reddit" value={`${redditS.score || "—"}`}
                                                        color={redditS.score >= 60 ? "#B5FF19" : redditS.score <= 40 ? "#FF4D4D" : "#888"} />
                                                    <MetricCard label="수급 점수" value={`${flow.flow_score || 50}`} />
                                                </>
                                            ) : (
                                                <>
                                                    <MetricCard label="뉴스 감성" value={`${sent.score || 50}`}
                                                        color={sent.score >= 60 ? "#B5FF19" : sent.score <= 40 ? "#FF4D4D" : "#FFD600"} />
                                                    <MetricCard label="긍정 키워드" value={`${sent.positive || 0}건`} color="#B5FF19" />
                                                    <MetricCard label="부정 키워드" value={`${sent.negative || 0}건`} color="#FF4D4D" />
                                                    <MetricCard label="외국인" value={flow.foreign_net > 0 ? "순매수" : flow.foreign_net < 0 ? "순매도" : "중립"}
                                                        color={flow.foreign_net > 0 ? "#B5FF19" : flow.foreign_net < 0 ? "#FF4D4D" : "#888"} />
                                                    <MetricCard label="기관" value={flow.institution_net > 0 ? "순매수" : flow.institution_net < 0 ? "순매도" : "중립"}
                                                        color={flow.institution_net > 0 ? "#B5FF19" : flow.institution_net < 0 ? "#FF4D4D" : "#888"} />
                                                    <MetricCard label="수급 점수" value={`${flow.flow_score || 50}`} />
                                                </>
                                            )}
                                        </div>
                                        {hasSSocial && (commS.volume > 0 || redditS.volume > 0) && (
                                            <div style={{ marginTop: 10, display: "flex", gap: 16, fontSize: 11, color: "#555" }}>
                                                {commS.volume > 0 && <span>커뮤니티 {commS.volume}건 (긍정 {commS.positive} / 부정 {commS.negative})</span>}
                                                {redditS.volume > 0 && <span>Reddit {redditS.volume}건 (긍정 {redditS.positive} / 부정 {redditS.negative})</span>}
                                            </div>
                                        )}
                                        {redditS.top_posts?.length > 0 && (
                                            <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                                                <span style={{ color: "#666", fontSize: 11, fontWeight: 600 }}>Reddit 인기글</span>
                                                {redditS.top_posts.map((p: any, i: number) => (
                                                    <div key={i} style={{ ...newsRow, padding: "4px 0" }}>
                                                        <span style={{ color: "#aaa", fontSize: 11 }}>r/{p.sub} · {p.title}</span>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                        {sent.top_headlines?.length > 0 && (
                                            <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                                                <span style={{ color: "#666", fontSize: 11, fontWeight: 600 }}>최근 뉴스</span>
                                                {sent.top_headlines.map((h: string, i: number) => (
                                                    <div key={i} style={newsRow}>
                                                        <span style={{ color: "#aaa", fontSize: 12, lineHeight: 1.5 }}>{h}</span>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </>
                                )
                            })()}

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
                                        <MetricCard label="미10년(DGS10·표시)" value={`${macro.us_10y?.value || "—"}%`} />
                                        <MetricCard label="10년 출처" value={`${macro.us_10y?.source || "—"}`} />
                                        <MetricCard label="근원 CPI YoY" value={macro.fred?.core_cpi?.yoy_pct != null ? `${macro.fred.core_cpi.yoy_pct}%` : "—"}
                                            color="#A78BFA" />
                                        <MetricCard label="M2 YoY" value={macro.fred?.m2?.yoy_pct != null ? `${macro.fred.m2.yoy_pct}%` : "—"}
                                            color="#94A3B8" />
                                        <MetricCard label="VIXCLS(FRED)" value={macro.fred?.vix_close?.value != null ? `${macro.fred.vix_close.value}` : "—"}
                                            color="#F472B6" />
                                        <MetricCard label="한국10Y OECD" value={macro.fred?.korea_gov_10y?.value != null ? `${macro.fred.korea_gov_10y.value}%` : "—"}
                                            color="#22D3EE" />
                                        <MetricCard label="IMF할인율 KR" value={macro.fred?.korea_discount_rate?.value != null ? `${macro.fred.korea_discount_rate.value}%` : "—"}
                                            color="#94A3B8" />
                                        <MetricCard label="미 리세션확률" value={macro.fred?.us_recession_smoothed_prob?.pct != null ? `${macro.fred.us_recession_smoothed_prob.pct}%` : "—"}
                                            color={(macro.fred?.us_recession_smoothed_prob?.pct || 0) >= 25 ? "#EF4444" : "#888"} />
                                        <MetricCard label="나스닥" value={`${macro.nasdaq?.change_pct >= 0 ? "+" : ""}${macro.nasdaq?.change_pct || 0}%`}
                                            color={(macro.nasdaq?.change_pct || 0) >= 0 ? "#B5FF19" : "#FF4D4D"} />
                                        <MetricCard label="금" value={`$${macro.gold?.value?.toLocaleString() || "—"}`} />
                                        <MetricCard label="금리 스프레드" value={macro.yield_spread ? `${macro.yield_spread.value}%p` : "—"}
                                            color={(macro.yield_spread?.value || 0) < 0 ? "#FF4D4D" : "#22C55E"} />
                                    </div>
                                    {macro.macro_diagnosis?.length > 0 && (
                                        <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
                                            <span style={{ color: "#666", fontSize: 12, fontWeight: 600 }}>매크로 진단</span>
                                            {macro.macro_diagnosis.map((d: any, i: number) => (
                                                <div key={i} style={{ ...newsRow, borderLeft: `3px solid ${d.type === "positive" ? "#22C55E" : d.type === "risk" ? "#EF4444" : d.type === "warning" ? "#F59E0B" : "#555"}` }}>
                                                    <span style={{ color: "#bbb", fontSize: 12, lineHeight: "1.5" }}>{d.text}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </>
                            )}

                            {detailTab === "timing" && (() => {
                                const timing = stock?.timing || {}
                                const ts = timing.timing_score || 50
                                const actionColors: Record<string, string> = {
                                    STRONG_BUY: "#22C55E", BUY: "#86EFAC", HOLD: "#888",
                                    SELL: "#FCA5A5", STRONG_SELL: "#EF4444",
                                }
                                const ac = actionColors[timing.action] || "#888"
                                const gaugeR = 50, gaugeS = 8, gaugeC = 2 * Math.PI * gaugeR, gaugeP = (ts / 100) * gaugeC
                                return (
                                    <>
                                        <div style={{ display: "flex", alignItems: "center", gap: 20, padding: "8px 0" }}>
                                            <div style={{ position: "relative", width: 116, height: 116, flexShrink: 0 }}>
                                                <svg width={116} height={116} viewBox={`0 0 ${(gaugeR + gaugeS) * 2} ${(gaugeR + gaugeS) * 2}`}>
                                                    <circle cx={gaugeR + gaugeS} cy={gaugeR + gaugeS} r={gaugeR} fill="none" stroke="#222" strokeWidth={gaugeS} />
                                                    <circle cx={gaugeR + gaugeS} cy={gaugeR + gaugeS} r={gaugeR} fill="none" stroke={ac} strokeWidth={gaugeS}
                                                        strokeDasharray={gaugeC} strokeDashoffset={gaugeC - gaugeP} strokeLinecap="round"
                                                        transform={`rotate(-90 ${gaugeR + gaugeS} ${gaugeR + gaugeS})`}
                                                        style={{ transition: "stroke-dashoffset 0.5s ease" }} />
                                                </svg>
                                                <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                                                    <span style={{ color: ac, fontSize: 26, fontWeight: 900 }}>{ts}</span>
                                                    <span style={{ color: ac, fontSize: 11, fontWeight: 700 }}>{timing.label || "—"}</span>
                                                </div>
                                            </div>
                                            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                                                <span style={{ color: "#fff", fontSize: 16, fontWeight: 800 }}>
                                                    {timing.label || "데이터 대기"}
                                                </span>
                                                <span style={{ color: "#888", fontSize: 12 }}>
                                                    {timing.action === "STRONG_BUY" ? "강한 매수 신호 — 적극적 진입 고려" :
                                                     timing.action === "BUY" ? "매수 우위 — 분할 매수 고려" :
                                                     timing.action === "HOLD" ? "방향성 불명확 — 관망 권고" :
                                                     timing.action === "SELL" ? "매도 우위 — 비중 축소 고려" :
                                                     timing.action === "STRONG_SELL" ? "강한 매도 신호 — 손절/청산 고려" :
                                                     "분석 데이터 수집 중"}
                                                </span>
                                            </div>
                                        </div>

                                        {/* 스코어 바 */}
                                        <div style={{ padding: "8px 0" }}>
                                            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                                                <span style={{ color: "#EF4444", fontSize: 10, fontWeight: 600 }}>매도</span>
                                                <span style={{ color: "#888", fontSize: 10 }}>관망</span>
                                                <span style={{ color: "#22C55E", fontSize: 10, fontWeight: 600 }}>매수</span>
                                            </div>
                                            <div style={{ height: 8, background: "linear-gradient(to right, #EF4444, #F59E0B, #888, #86EFAC, #22C55E)", borderRadius: 4, position: "relative" }}>
                                                <div style={{
                                                    position: "absolute", top: -3, left: `${ts}%`, width: 14, height: 14,
                                                    borderRadius: 7, background: "#fff", border: `2px solid ${ac}`,
                                                    transform: "translateX(-50%)", transition: "left 0.5s ease",
                                                }} />
                                            </div>
                                        </div>

                                        {/* 판단 근거 */}
                                        {timing.reasons?.length > 0 && (
                                            <div style={{ marginTop: 8 }}>
                                                <span style={{ color: "#666", fontSize: 11, fontWeight: 600 }}>판단 근거</span>
                                                <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
                                                    {timing.reasons.map((r: string, i: number) => (
                                                        <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
                                                            <span style={{ color: "#444", fontSize: 12, marginTop: 1 }}>•</span>
                                                            <span style={{ color: "#bbb", fontSize: 12, lineHeight: "1.5" }}>{r}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

                                        <div style={{ ...newsRow, marginTop: 8 }}>
                                            <span style={{ color: "#555", fontSize: 11 }}>
                                                타이밍 스코어는 RSI, MACD, 볼린저밴드, 이동평균, 거래량, AI 상승확률, 수급을 종합한 점수입니다. 투자 판단의 참고용으로만 사용하세요.
                                            </span>
                                        </div>
                                    </>
                                )
                            })()}

                            {detailTab === "brain" && (() => {
                                const brain = stock?.verity_brain || {}
                                const bs = brain.brain_score ?? null
                                const fs = brain.fact_score || {}
                                const ss = brain.sentiment_score || {}
                                const vci = brain.vci || {}
                                const rf = brain.red_flags || {}
                                const gradeLabel = brain.grade_label || "—"
                                const grade = brain.grade || "WATCH"
                                const gradeColors: Record<string, string> = { STRONG_BUY: "#22C55E", BUY: "#B5FF19", WATCH: "#FFD600", CAUTION: "#F59E0B", AVOID: "#EF4444" }
                                const gc = gradeColors[grade] || "#888"
                                const vciVal = vci.vci ?? 0
                                const vciColor = vciVal > 15 ? "#B5FF19" : vciVal < -15 ? "#FF4D4D" : "#888"

                                if (bs === null) {
                                    return (
                                        <div style={{ color: "#555", fontSize: 12, textAlign: "center", padding: 20 }}>
                                            Verity Brain 데이터는 파이프라인 실행 후 표시됩니다
                                        </div>
                                    )
                                }

                                const brainR = 50, brainS = 8, brainC = 2 * Math.PI * brainR, brainP = (bs / 100) * brainC
                                return (
                                    <>
                                        <div style={{ display: "flex", alignItems: "center", gap: 20, padding: "8px 0" }}>
                                            <div style={{ position: "relative", width: 116, height: 116, flexShrink: 0 }}>
                                                <svg width={116} height={116} viewBox={`0 0 ${(brainR + brainS) * 2} ${(brainR + brainS) * 2}`}>
                                                    <circle cx={brainR + brainS} cy={brainR + brainS} r={brainR} fill="none" stroke="#222" strokeWidth={brainS} />
                                                    <circle cx={brainR + brainS} cy={brainR + brainS} r={brainR} fill="none" stroke={gc} strokeWidth={brainS}
                                                        strokeDasharray={brainC} strokeDashoffset={brainC - brainP} strokeLinecap="round"
                                                        transform={`rotate(-90 ${brainR + brainS} ${brainR + brainS})`}
                                                        style={{ transition: "stroke-dashoffset 0.5s ease" }} />
                                                </svg>
                                                <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                                                    <span style={{ color: gc, fontSize: 26, fontWeight: 900 }}>{bs}</span>
                                                    <span style={{ color: gc, fontSize: 11, fontWeight: 700 }}>{gradeLabel}</span>
                                                </div>
                                            </div>
                                            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                                <span style={{ color: "#fff", fontSize: 16, fontWeight: 800 }}>Verity Brain</span>
                                                <div style={{ display: "flex", gap: 12 }}>
                                                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                                        <span style={{ color: "#666", fontSize: 10 }}>팩트</span>
                                                        <span style={{ color: "#22C55E", fontSize: 18, fontWeight: 800 }}>{fs.score ?? "—"}</span>
                                                    </div>
                                                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                                        <span style={{ color: "#666", fontSize: 10 }}>심리</span>
                                                        <span style={{ color: "#60A5FA", fontSize: 18, fontWeight: 800 }}>{ss.score ?? "—"}</span>
                                                    </div>
                                                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                                        <span style={{ color: "#666", fontSize: 10 }}>VCI</span>
                                                        <span style={{ color: vciColor, fontSize: 18, fontWeight: 800 }}>{vciVal >= 0 ? "+" : ""}{vciVal}</span>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>

                                        {/* VCI 시그널 */}
                                        {vci.signal && vci.signal !== "ALIGNED" && (
                                            <div style={{
                                                background: vciVal > 15 ? "rgba(181,255,25,0.06)" : "rgba(255,77,77,0.06)",
                                                border: `1px solid ${vciColor}40`,
                                                borderRadius: 10, padding: "10px 14px",
                                            }}>
                                                <span style={{ color: vciColor, fontSize: 12, fontWeight: 700 }}>
                                                    VCI {vciVal >= 0 ? "+" : ""}{vciVal}: {vci.label}
                                                </span>
                                            </div>
                                        )}

                                        {/* 팩트 컴포넌트 분해 */}
                                        {fs.components && (
                                            <div style={{ marginTop: 4 }}>
                                                <span style={{ color: "#666", fontSize: 11, fontWeight: 600 }}>팩트 스코어 구성</span>
                                                <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
                                                    {Object.entries(fs.components as Record<string, number>).map(([key, val]) => {
                                                        const labels: Record<string, string> = { multi_factor: "멀티팩터", consensus: "컨센서스", prediction: "AI예측", backtest: "백테스트", timing: "타이밍", commodity_margin: "원자재", export_trade: "수출입" }
                                                        const c = val >= 65 ? "#B5FF19" : val >= 45 ? "#FFD600" : "#FF4D4D"
                                                        return (
                                                            <div key={key} style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                                                                <div style={{ display: "flex", justifyContent: "space-between" }}>
                                                                    <span style={{ color: "#888", fontSize: 11 }}>{labels[key] || key}</span>
                                                                    <span style={{ color: c, fontSize: 11, fontWeight: 700 }}>{val}</span>
                                                                </div>
                                                                <div style={{ height: 3, background: "#222", borderRadius: 2, overflow: "hidden" }}>
                                                                    <div style={{ height: "100%", width: `${val}%`, background: c, borderRadius: 2, transition: "width 0.5s ease" }} />
                                                                </div>
                                                            </div>
                                                        )
                                                    })}
                                                </div>
                                            </div>
                                        )}

                                        {/* 레드플래그 */}
                                        {(rf.auto_avoid?.length > 0 || rf.downgrade?.length > 0) && (
                                            <div style={{ marginTop: 4 }}>
                                                <span style={{ color: "#EF4444", fontSize: 11, fontWeight: 700 }}>레드플래그</span>
                                                <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
                                                    {(rf.auto_avoid || []).map((f: string, i: number) => (
                                                        <div key={`a${i}`} style={{ background: "rgba(239,68,68,0.08)", borderRadius: 6, padding: "6px 10px", borderLeft: "3px solid #EF4444" }}>
                                                            <span style={{ color: "#FF6B6B", fontSize: 11 }}>⛔ {f}</span>
                                                        </div>
                                                    ))}
                                                    {(rf.downgrade || []).map((f: string, i: number) => (
                                                        <div key={`d${i}`} style={{ background: "rgba(234,179,8,0.06)", borderRadius: 6, padding: "6px 10px", borderLeft: "3px solid #EAB308" }}>
                                                            <span style={{ color: "#EAB308", fontSize: 11 }}>⚠️ {f}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

                                        {/* 판단 근거 */}
                                        {brain.reasoning && (
                                            <div style={{ ...newsRow, marginTop: 4 }}>
                                                <span style={{ color: "#888", fontSize: 11, lineHeight: "1.5" }}>{brain.reasoning}</span>
                                            </div>
                                        )}
                                    </>
                                )
                            })()}

                            {detailTab === "niche" && (() => {
                                const n = stock?.niche_data || {}
                                const hasNiche = n.trends || n.g2b?.items?.length || n.legal?.hits?.length || n.credit
                                return (
                                    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                                        <span style={{ color: "#fff", fontSize: 14, fontWeight: 700 }}>틈새 정보 — {stock.name}</span>
                                        {hasNiche ? (
                                            <>
                                                {n.trends?.keyword && <div style={newsRow}><span style={{ color: "#888", fontSize: 11 }}>검색 키워드: {n.trends.keyword} (관심 {n.trends.interest_index ?? "—"})</span></div>}
                                                {n.g2b?.items?.length > 0 && <div style={newsRow}><span style={{ color: "#888", fontSize: 11 }}>공공 수주: {n.g2b.items.length}건</span></div>}
                                                {n.legal?.risk_flag && <div style={{ ...newsRow, borderLeft: "3px solid #EF4444" }}><span style={{ color: "#FF4D4D", fontSize: 11 }}>리스크 플래그 ON</span></div>}
                                                {n.credit?.ig_spread_pp != null && <div style={newsRow}><span style={{ color: "#888", fontSize: 11 }}>IG 스프레드: {n.credit.ig_spread_pp}%p</span></div>}
                                            </>
                                        ) : (
                                            <div style={{ color: "#555", fontSize: 12, textAlign: "center", padding: 20 }}>
                                                틈새 데이터는 NicheIntelPanel 컴포넌트에서 상세 확인 가능합니다
                                            </div>
                                        )}
                                    </div>
                                )
                            })()}

                            {detailTab === "property" && (() => {
                                const prop =
                                    stock?.dart_financials?.property_assets ||
                                    stock?.dart_data?.property_assets ||
                                    stock?.property_assets ||
                                    {}
                                const items: any[] = prop.items || []
                                const totalCurr = prop.total_current || 0
                                const totalPrev = prop.total_previous || 0
                                const propRatio = prop.property_to_asset_pct
                                const totalChgPct = prop.total_change_pct
                                const fmtBillion = (v: number) => {
                                    if (v === 0) return "—"
                                    const billion = v / 1e8
                                    if (billion >= 10000) return `${(billion / 10000).toFixed(1)}조`
                                    return `${billion.toFixed(0)}억`
                                }
                                return (
                                    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                                        <span style={{ color: "#fff", fontSize: 14, fontWeight: 700 }}>부동산 자산 — {stock.name}</span>
                                        {items.length > 0 ? (
                                            <>
                                                <div style={metricsGrid}>
                                                    <MetricCard label="부동산 총계" value={fmtBillion(totalCurr)} color="#FFD700" />
                                                    <MetricCard label="전년 대비" value={totalChgPct != null ? `${totalChgPct >= 0 ? "+" : ""}${totalChgPct}%` : "—"}
                                                        color={totalChgPct > 0 ? "#22C55E" : totalChgPct < 0 ? "#EF4444" : "#888"} />
                                                    <MetricCard label="자산 대비 비중" value={propRatio != null ? `${propRatio}%` : "—"} color="#60A5FA" />
                                                </div>
                                                <div style={{ borderTop: "1px solid #1A1A1A", paddingTop: 10 }}>
                                                    <span style={{ color: "#666", fontSize: 11, fontWeight: 600 }}>계정과목별 상세</span>
                                                    {items.map((item: any, idx: number) => (
                                                        <div key={idx} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid #1a1a1a" }}>
                                                            <div>
                                                                <span style={{ color: "#ccc", fontSize: 12, fontWeight: 600 }}>{item.account}</span>
                                                                <div style={{ color: "#555", fontSize: 10, marginTop: 2 }}>
                                                                    전기: {fmtBillion(item.previous)}
                                                                </div>
                                                            </div>
                                                            <div style={{ textAlign: "right" }}>
                                                                <span style={{ color: "#fff", fontSize: 13, fontWeight: 700 }}>{fmtBillion(item.current)}</span>
                                                                {item.change_pct != null && (
                                                                    <div style={{ color: item.change_pct >= 0 ? "#22C55E" : "#EF4444", fontSize: 11, fontWeight: 600 }}>
                                                                        {item.change_pct >= 0 ? "+" : ""}{item.change_pct}%
                                                                    </div>
                                                                )}
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                                <div style={{ color: "#555", fontSize: 10, padding: "8px 0" }}>
                                                    OpenDART 재무상태표 기준. 투자부동산·토지·건물·사용권자산 합산.
                                                </div>
                                            </>
                                        ) : (
                                            <div style={{ color: "#555", fontSize: 12, textAlign: "center", padding: 20 }}>
                                                {stock?.dart_financials
                                                    ? "OpenDART 재무제표에 투자부동산·토지·건물·사용권자산 등 해당 계정이 없거나 금액이 0입니다."
                                                    : "DART 데이터가 아직 없습니다. GitHub Actions 또는 로컬에서 full 모드로 파이프라인을 실행하면 표시됩니다."}
                                                <br />
                                                <span style={{ fontSize: 10, color: "#444" }}>
                                                    국내 상장사(KRX)만 OpenDART 연동이 가능합니다.
                                                </span>
                                            </div>
                                        )}
                                    </div>
                                )
                            })()}

                            {detailTab === "predict" && (() => {
                                const pred = stock?.prediction || {}
                                const bt = stock?.backtest || {}
                                const upProb = pred.up_probability || 50
                                const probColor = upProb >= 65 ? "#B5FF19" : upProb >= 45 ? "#FFD600" : "#FF4D4D"
                                return (
                                    <>
                                        <div style={{ display: "flex", alignItems: "center", gap: 16, padding: "8px 0" }}>
                                            <div style={{ width: 80, height: 80, borderRadius: 40, border: `3px solid ${probColor}`, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                                                <span style={{ color: probColor, fontSize: 22, fontWeight: 900 }}>{upProb}%</span>
                                                <span style={{ color: "#666", fontSize: 9 }}>상승확률</span>
                                            </div>
                                            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                                                <span style={{ color: "#fff", fontSize: 14, fontWeight: 700 }}>1주 후 상승 확률</span>
                                                <span style={{ color: "#888", fontSize: 11 }}>
                                                    {pred.method === "xgboost" ? `XGBoost (정확도 ${pred.model_accuracy}%)` : "규칙 기반 추정"}
                                                </span>
                                                <span style={{ color: "#555", fontSize: 10 }}>
                                                    {pred.train_samples ? `학습: ${pred.train_samples}건 / 테스트: ${pred.test_samples}건` : ""}
                                                </span>
                                            </div>
                                        </div>

                                        {pred.top_features && Object.keys(pred.top_features).length > 0 && (
                                            <div style={{ marginTop: 8 }}>
                                                <span style={{ color: "#666", fontSize: 11, fontWeight: 600 }}>주요 예측 피처</span>
                                                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                                                    {Object.entries(pred.top_features).map(([k, v]: [string, any]) => (
                                                        <span key={k} style={{ ...signalTag, background: "#001A0D", border: "1px solid #0A2A1A" }}>
                                                            {k}: {(v * 100).toFixed(0)}%
                                                        </span>
                                                    ))}
                                                </div>
                                            </div>
                                        )}

                                        {bt.total_trades > 0 && (
                                            <div style={{ marginTop: 16, borderTop: "1px solid #1A1A1A", paddingTop: 12 }}>
                                                <span style={{ color: "#666", fontSize: 12, fontWeight: 600 }}>백테스트 (1년)</span>
                                                <div style={{ ...metricsGrid, marginTop: 8 }}>
                                                    <MetricCard label="승률" value={`${bt.win_rate}%`}
                                                        color={bt.win_rate >= 55 ? "#B5FF19" : bt.win_rate >= 45 ? "#FFD600" : "#FF4D4D"} />
                                                    <MetricCard label="총 매매" value={`${bt.total_trades}회`} />
                                                    <MetricCard label="평균수익" value={`${bt.avg_return >= 0 ? "+" : ""}${bt.avg_return}%`}
                                                        color={bt.avg_return >= 0 ? "#B5FF19" : "#FF4D4D"} />
                                                    <MetricCard label="최대낙폭" value={`-${bt.max_drawdown}%`} color="#FF4D4D" />
                                                    <MetricCard label="샤프비율" value={`${bt.sharpe_ratio}`}
                                                        color={bt.sharpe_ratio >= 1 ? "#B5FF19" : bt.sharpe_ratio >= 0.5 ? "#FFD600" : "#FF4D4D"} />
                                                    <MetricCard label="누적수익" value={`${bt.total_return >= 0 ? "+" : ""}${bt.total_return}%`}
                                                        color={bt.total_return >= 0 ? "#B5FF19" : "#FF4D4D"} />
                                                </div>
                                                {bt.recent_trades?.length > 0 && (
                                                    <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                                                        <span style={{ color: "#555", fontSize: 10 }}>최근 매매</span>
                                                        {bt.recent_trades.map((tr: any, i: number) => (
                                                            <div key={i} style={{ ...newsRow, display: "flex", justifyContent: "space-between" }}>
                                                                <span style={{ color: "#888", fontSize: 11 }}>{tr.entry_date} → {tr.exit_date}</span>
                                                                <span style={{ color: tr.return_pct >= 0 ? "#B5FF19" : "#FF4D4D", fontSize: 12, fontWeight: 700 }}>
                                                                    {tr.return_pct >= 0 ? "+" : ""}{tr.return_pct}%
                                                                </span>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                        )}

                                        {(!bt.total_trades || bt.total_trades === 0) && (
                                            <div style={{ color: "#555", fontSize: 12, padding: "16px 0", textAlign: "center" }}>
                                                백테스트 데이터는 장 마감 후(16시) 전체 분석 시 생성됩니다
                                            </div>
                                        )}
                                    </>
                                )
                            })()}
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

StockDashboard.defaultProps = { dataUrl: DATA_URL, apiBase: API_BASE }
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

const subTabBar: React.CSSProperties = { display: "flex", gap: 0, flexWrap: "wrap", rowGap: 4 }
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

