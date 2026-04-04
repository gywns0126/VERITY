import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

const DATA_URL =
    "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"
const API_BASE = "https://verity-api.vercel.app"

/** 끝 슬래시 제거, https 보정. 빈 문자열이면 "" */
function normalizeApiBase(raw: string): string {
    let s = (raw || "").trim().replace(/\/+$/, "")
    if (!s) return ""
    if (!/^https?:\/\//i.test(s)) s = `https://${s.replace(/^\/+/, "")}`
    return s.replace(/\/+$/, "")
}

/**
 * Preview 배포 호스트는 보통 `프로젝트-배포해시(7자↑)-팀...vercel.app` 형태.
 * Production은 `프로젝트-팀...vercel.app` 이라 두 번째 토큰이 짧음(예: api).
 */
function looksLikeVercelPreviewUrl(url: string): boolean {
    try {
        const host = new URL(url).hostname
        if (!host.toLowerCase().endsWith(".vercel.app")) return false
        const sub = host.slice(0, -".vercel.app".length)
        const parts = sub.split("-")
        if (parts.length < 3) return false
        const second = parts[1]
        return second.length >= 7 && /^[a-z0-9]+$/i.test(second)
    } catch {
        return false
    }
}

interface Props {
    dataUrl: string
    apiBase: string
}

export default function StockDashboard(props: Props) {
    const { dataUrl, apiBase } = props
    const api = normalizeApiBase(apiBase) || normalizeApiBase(API_BASE)
    const [data, setData] = useState<any>(null)
    const [selected, setSelected] = useState(0)
    const [tab, setTab] = useState<"all" | "buy" | "watch" | "avoid">("all")
    const [detailTab, setDetailTab] = useState<"overview" | "technical" | "sentiment" | "macro" | "predict" | "timing">("overview")
    const [searchQuery, setSearchQuery] = useState("")
    const [searchSuggestions, setSearchSuggestions] = useState<any[]>([])
    const [searchResult, setSearchResult] = useState<any>(null)
    const [searchLoading, setSearchLoading] = useState(false)
    const [searchFetchError, setSearchFetchError] = useState<string | null>(null)
    const [showSearchPopup, setShowSearchPopup] = useState(false)

    useEffect(() => {
        if (!dataUrl) return
        fetch(dataUrl)
            .then((r) => r.text())
            .then((txt) => JSON.parse(txt.replace(/\bNaN\b/g, "null")))
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

    const searchTimer = { current: null as any }

    const handleSearch = (query: string) => {
        setSearchQuery(query)
        if (!query.trim()) {
            setSearchSuggestions([])
            setSearchResult(null)
            setSearchFetchError(null)
            setShowSearchPopup(false)
            return
        }
        setShowSearchPopup(true)
        setSearchResult(null)
        setSearchFetchError(null)

        if (looksLikeVercelPreviewUrl(api)) {
            setSearchFetchError(
                "API Base가 Preview 주소입니다. Vercel → Deployments → Production 배포의 URL(예: 프로젝트명-팀.vercel.app)을 넣으세요."
            )
            setSearchSuggestions([])
            return
        }

        if (searchTimer.current) clearTimeout(searchTimer.current)
        searchTimer.current = setTimeout(() => {
            fetch(`${api}/api/search?q=${encodeURIComponent(query.trim())}&limit=8`)
                .then(async (r) => {
                    if (!r.ok) {
                        const hint =
                            r.status === 401 || r.status === 403
                                ? " Preview/보호된 배포일 수 있음 → Production URL 사용."
                                : ""
                        throw new Error(`HTTP ${r.status}${hint}`)
                    }
                    const ct = r.headers.get("content-type") || ""
                    if (!ct.includes("application/json")) {
                        throw new Error("API가 JSON이 아님. Production URL·경로(/api/search) 확인.")
                    }
                    return r.json()
                })
                .then((items) => {
                    if (Array.isArray(items)) {
                        setSearchSuggestions(items)
                        setSearchFetchError(null)
                    } else {
                        setSearchSuggestions([])
                        setSearchFetchError("검색 응답 형식 오류")
                    }
                })
                .catch((e) => {
                    setSearchSuggestions([])
                    setSearchFetchError(e?.message || "검색 API 연결 실패")
                })
        }, 200)
    }

    const analyzeStock = (ticker: string, name: string) => {
        setSearchLoading(true)
        setSearchSuggestions([])
        setSearchFetchError(null)
        setSearchQuery(name)
        if (looksLikeVercelPreviewUrl(api)) {
            setSearchResult({ error: "Preview URL은 Framer에서 막힐 수 있습니다. Production 도메인으로 API Base를 바꿔주세요." })
            setSearchLoading(false)
            return
        }
        fetch(`${api}/api/stock?q=${encodeURIComponent(ticker)}`)
            .then(async (r) => {
                if (!r.ok) {
                    throw new Error(`HTTP ${r.status}`)
                }
                const ct = r.headers.get("content-type") || ""
                if (!ct.includes("application/json")) {
                    throw new Error("JSON 아님")
                }
                return r.json()
            })
            .then((result) => {
                if (!result.error) {
                    setSearchResult(result)
                } else {
                    setSearchResult({ error: result.error })
                }
                setSearchLoading(false)
            })
            .catch(() => {
                setSearchResult({ error: "서버 연결 실패 (Production URL·CORS 확인)" })
                setSearchLoading(false)
            })
    }

    const jumpToStock = (ticker: string) => {
        const idx = recs.findIndex((r: any) => r.ticker === ticker)
        if (idx >= 0) {
            setSelected(idx)
            setTab("all")
            setDetailTab("overview")
        }
        setShowSearchPopup(false)
        setSearchQuery("")
        setSearchResult(null)
        setSearchSuggestions([])
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
            {/* 검색바 */}
            <div style={searchBarWrap}>
                <div style={searchInputWrap}>
                    <svg width={16} height={16} viewBox="0 0 24 24" fill="none" style={{ flexShrink: 0 }}>
                        <circle cx={11} cy={11} r={7} stroke="#555" strokeWidth={2} />
                        <path d="M16 16L20 20" stroke="#555" strokeWidth={2} strokeLinecap="round" />
                    </svg>
                    <input
                        type="text"
                        placeholder="종목명 또는 코드 검색..."
                        value={searchQuery}
                        onChange={(e) => handleSearch(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === "Escape") {
                                setShowSearchPopup(false)
                                setSearchQuery("")
                            }
                        }}
                        style={searchInput}
                    />
                    {searchQuery && (
                        <button onClick={() => { setSearchQuery(""); setShowSearchPopup(false) }}
                            style={{ background: "none", border: "none", color: "#555", cursor: "pointer", fontSize: 16, padding: 0 }}>
                            ✕
                        </button>
                    )}
                </div>

                {showSearchPopup && (
                    <div style={searchPopup}>
                        {searchLoading && (
                            <div style={{ textAlign: "center", padding: "24px 0" }}>
                                <div style={{ width: 28, height: 28, border: "3px solid #222", borderTopColor: "#B5FF19", borderRadius: "50%", margin: "0 auto 10px", animation: "spin 0.8s linear infinite" }} />
                                <span style={{ color: "#888", fontSize: 12 }}>실시간 분석 중...</span>
                                <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>
                            </div>
                        )}

                        {!searchLoading && searchResult && !searchResult.error && (() => {
                            const s = searchResult
                            const ms = s.multi_factor?.multi_score || s.safety_score || 0
                            const msColor = ms >= 65 ? "#B5FF19" : ms >= 45 ? "#FFD600" : "#FF4D4D"
                            const sRec = s.recommendation || "WATCH"
                            const sRecColor = sRec === "BUY" ? "#B5FF19" : sRec === "AVOID" ? "#FF4D4D" : "#888"
                            const inRecs = recs.some((r: any) => r.ticker === s.ticker)
                            return (
                                <div>
                                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                                        <div>
                                            <span style={{ color: "#fff", fontSize: 16, fontWeight: 800 }}>{s.name}</span>
                                            <span style={{ color: "#555", fontSize: 12, marginLeft: 8 }}>{s.ticker} · {s.market}</span>
                                        </div>
                                        <span style={{ background: sRecColor, color: "#000", fontSize: 11, fontWeight: 800, padding: "3px 10px", borderRadius: 6 }}>{sRec}</span>
                                    </div>
                                    <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
                                        <div style={{ width: 64, height: 64, borderRadius: 32, border: `3px solid ${msColor}`, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                                            <span style={{ color: msColor, fontSize: 20, fontWeight: 900 }}>{ms}</span>
                                            <span style={{ color: "#666", fontSize: 8 }}>종합점수</span>
                                        </div>
                                        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6 }}>
                                            <div style={popupMetric}><span style={popupMetricLabel}>현재가</span><span style={popupMetricVal}>{s.price?.toLocaleString()}원</span></div>
                                            <div style={popupMetric}><span style={popupMetricLabel}>PER</span><span style={popupMetricVal}>{s.per?.toFixed(1)}</span></div>
                                            <div style={popupMetric}><span style={popupMetricLabel}>배당</span><span style={popupMetricVal}>{s.div_yield?.toFixed(1)}%</span></div>
                                            <div style={popupMetric}><span style={popupMetricLabel}>RSI</span><span style={{ ...popupMetricVal, color: (s.technical?.rsi || 50) <= 30 ? "#B5FF19" : (s.technical?.rsi || 50) >= 70 ? "#FF4D4D" : "#fff" }}>{s.technical?.rsi || "—"}</span></div>
                                            <div style={popupMetric}><span style={popupMetricLabel}>수급</span><span style={popupMetricVal}>{s.flow?.flow_score || "—"}</span></div>
                                            <div style={popupMetric}><span style={popupMetricLabel}>고점대비</span><span style={popupMetricVal}>{s.drop_from_high_pct?.toFixed(0)}%</span></div>
                                        </div>
                                    </div>
                                    {s.technical?.signals?.length > 0 && (
                                        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 8 }}>
                                            {s.technical.signals.map((sig: string, i: number) => (
                                                <span key={i} style={{ background: "#0D1A00", border: "1px solid #1A2A00", color: "#B5FF19", fontSize: 10, fontWeight: 600, padding: "2px 8px", borderRadius: 4 }}>{sig}</span>
                                            ))}
                                        </div>
                                    )}
                                    {inRecs ? (
                                        <div style={{ cursor: "pointer", background: "#0D1A00", border: "1px solid #1A2A00", borderRadius: 8, padding: "8px 12px", textAlign: "center", marginTop: 4 }}
                                            onClick={() => jumpToStock(s.ticker)}>
                                            <span style={{ color: "#B5FF19", fontSize: 12, fontWeight: 700 }}>상세 분석 보기 →</span>
                                        </div>
                                    ) : (
                                        <div style={{ color: "#444", fontSize: 10, textAlign: "center", marginTop: 4 }}>이 종목은 추천 리스트 외 종목입니다 (실시간 분석 결과)</div>
                                    )}
                                </div>
                            )
                        })()}

                        {!searchLoading && searchResult?.error && (
                            <div style={{ textAlign: "center", padding: "16px 0" }}>
                                <span style={{ color: "#FF4D4D", fontSize: 13 }}>{searchResult.error}</span>
                            </div>
                        )}

                        {!searchLoading && !searchResult && searchSuggestions.length > 0 && (
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                <span style={{ color: "#444", fontSize: 10, marginBottom: 4 }}>종목을 선택하면 실시간 분석합니다</span>
                                {searchSuggestions.map((s: any) => (
                                    <div key={s.ticker} onClick={() => analyzeStock(s.ticker, s.name)}
                                        style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 10px", borderRadius: 8, cursor: "pointer", transition: "background 0.15s" }}
                                        onMouseEnter={(e) => (e.currentTarget.style.background = "#1A1A1A")}
                                        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                                        <div>
                                            <span style={{ color: "#fff", fontSize: 13, fontWeight: 600 }}>{s.name}</span>
                                            <span style={{ color: "#555", fontSize: 10, marginLeft: 6 }}>{s.ticker}</span>
                                        </div>
                                        <span style={{ color: "#444", fontSize: 10 }}>{s.market}</span>
                                    </div>
                                ))}
                            </div>
                        )}

                        {!searchLoading && searchFetchError && (
                            <div style={{ textAlign: "left", padding: "12px 0" }}>
                                <span style={{ color: "#FF9F40", fontSize: 11, lineHeight: 1.5 }}>{searchFetchError}</span>
                            </div>
                        )}

                        {!searchLoading && !searchResult && !searchFetchError && searchSuggestions.length === 0 && searchQuery.length >= 2 && (
                            <div style={{ textAlign: "center", padding: "16px 0" }}>
                                <span style={{ color: "#555", fontSize: 13 }}>"{searchQuery}" 검색 결과 없음</span>
                            </div>
                        )}
                    </div>
                )}
            </div>

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
                                                <span style={listTicker}>{s.ticker} · {s.market}</span>
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
                            {([["overview", "개요"], ["timing", "매매시점"], ["technical", "기술적"], ["sentiment", "뉴스/수급"], ["macro", "매크로"], ["predict", "예측"]] as const).map(([k, l]) => (
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
    apiBase: { type: ControlType.String, title: "API Base (Production URL)", defaultValue: API_BASE },
})

/* ─── Styles ─── */
const font = "'Pretendard', -apple-system, sans-serif"
const wrap: React.CSSProperties = { width: "100%", background: "#0A0A0A", borderRadius: 20, fontFamily: font, display: "flex", flexDirection: "column", overflow: "hidden" }
const searchBarWrap: React.CSSProperties = { position: "relative", padding: "16px 20px 0" }
const searchInputWrap: React.CSSProperties = { display: "flex", alignItems: "center", gap: 8, background: "#111", border: "1px solid #222", borderRadius: 10, padding: "8px 14px" }
const searchInput: React.CSSProperties = { flex: 1, background: "transparent", border: "none", outline: "none", color: "#fff", fontSize: 13, fontFamily: font }
const searchPopup: React.CSSProperties = { position: "absolute", top: "100%", left: 20, right: 20, background: "#111", border: "1px solid #222", borderRadius: 12, padding: 16, zIndex: 100, boxShadow: "0 8px 32px rgba(0,0,0,0.6)", marginTop: 4 }
const popupMetric: React.CSSProperties = { background: "#0A0A0A", borderRadius: 6, padding: "6px 8px", display: "flex", flexDirection: "column", gap: 2 }
const popupMetricLabel: React.CSSProperties = { color: "#555", fontSize: 9, fontWeight: 500 }
const popupMetricVal: React.CSSProperties = { color: "#fff", fontSize: 12, fontWeight: 700 }
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
