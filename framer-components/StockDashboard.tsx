import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState, useCallback } from "react"

/* ─── Shared constant (used by sub-components defined below) ─── */
const font = "'Pretendard', -apple-system, sans-serif"

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

function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    return fetch(bustPortfolioUrl(url), { ...PORTFOLIO_FETCH_INIT, signal })
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
const REC_URL =
    "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/recommendations.json"
const API_BASE = "https://vercel-api-alpha-umber.vercel.app"

function isKRX(market: string): boolean { return /KOSPI|KOSDAQ|KRX|코스피|코스닥/i.test(market || "") }
function isUSMarket(market: string, currency?: string): boolean {
    if (currency === "USD") return true
    return /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(market || "")
}

interface Props {
    dataUrl: string
    recUrl: string
    apiBase: string
    market: "kr" | "us"
}

/* ─── Sub-components outside StockDashboard to prevent state reset on re-render ─── */

function Sparkline({ data, width = 60, height = 24, color = "#888" }: { data: number[]; width?: number; height?: number; color?: string }) {
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

function TrendBlock({ stock: s, isUS: usd }: { stock: any; isUS: boolean }) {
    const trends = s?.trends
    const weeklyData: number[] = s?.sparkline_weekly || []
    const [tp, setTp] = useState<"1m" | "3m" | "6m" | "1y">("3m")
    if (!trends) return null
    const t = trends[tp]
    if (!t) return null
    const sliceMap = { "1m": 4, "3m": 13, "6m": 26, "1y": 52 }
    const chartData = weeklyData.slice(-sliceMap[tp])
    const pctColor = (t.change_pct ?? 0) >= 0 ? "#22C55E" : "#EF4444"
    return (
        <div style={{ marginTop: 8, padding: "8px 10px", background: "#0A0A0A", borderRadius: 8, border: "1px solid #1A1A1A" }}>
            <div style={{ display: "flex", gap: 4, marginBottom: 6 }}>
                {(["1m", "3m", "6m", "1y"] as const).map((p) => (
                    <button key={p} onClick={() => setTp(p)} style={{
                        border: "none", borderRadius: 4, padding: "3px 8px", fontSize: 10, fontWeight: 700, fontFamily: font,
                        cursor: "pointer", background: tp === p ? "#B5FF19" : "#1A1A1A", color: tp === p ? "#000" : "#666",
                    }}>{p.toUpperCase()}</button>
                ))}
            </div>
            {chartData.length > 1 && <Sparkline data={chartData} width={200} height={32} color={pctColor} />}
            <div style={{ display: "flex", gap: 8, marginTop: 4, flexWrap: "wrap" }}>
                <span style={{ color: pctColor, fontSize: 12, fontWeight: 800, fontFamily: font }}>{(t.change_pct ?? 0) >= 0 ? "+" : ""}{t.change_pct}%</span>
                <span style={{ color: "#666", fontSize: 10, fontFamily: font }}>H {usd ? `$${t.high}` : t.high?.toLocaleString()}</span>
                <span style={{ color: "#666", fontSize: 10, fontFamily: font }}>L {usd ? `$${t.low}` : t.low?.toLocaleString()}</span>
                <span style={{ color: "#555", fontSize: 10, fontFamily: font }}>Vol {t.avg_volume ? (t.avg_volume / 1e6).toFixed(1) + "M" : "—"}</span>
            </div>
        </div>
    )
}

function SectorTrendView({ sectorTrends }: { sectorTrends: any }) {
    const [sp, setSp] = useState<"1m" | "3m" | "6m" | "1y">("3m")
    if (!sectorTrends) return null
    const st = sectorTrends[sp]
    if (!st) return (
        <div style={{ marginTop: 12, padding: 10, background: "#0A0A0A", borderRadius: 8, border: "1px solid #1A1A1A" }}>
            <span style={{ color: "#555", fontSize: 11, fontFamily: font }}>{sp.toUpperCase()} 섹터 데이터 아직 없음 (스냅샷 축적 중)</span>
        </div>
    )
    return (
        <div style={{ marginTop: 12, padding: "10px 12px", background: "#0A0A0A", borderRadius: 8, border: "1px solid #1A1A1A" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <span style={{ color: "#A78BFA", fontSize: 11, fontWeight: 700, fontFamily: font }}>섹터 추이</span>
                <div style={{ display: "flex", gap: 3 }}>
                    {(["1m", "3m", "6m", "1y"] as const).map((p) => (
                        <button key={p} onClick={() => setSp(p)} style={{
                            border: "none", borderRadius: 4, padding: "2px 7px", fontSize: 9, fontWeight: 700, fontFamily: font,
                            cursor: "pointer", background: sp === p ? "#A78BFA" : "#1A1A1A", color: sp === p ? "#000" : "#666",
                        }}>{p.toUpperCase()}</button>
                    ))}
                </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
                <div style={{ flex: 1 }}>
                    <span style={{ color: "#22C55E", fontSize: 9, fontWeight: 700, display: "block", marginBottom: 4 }}>TOP</span>
                    {(st.top3_sectors || []).map((s: any, i: number) => (
                        <div key={s.name ?? i} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", borderBottom: "1px solid #1A1A1A" }}>
                            <span style={{ color: "#ccc", fontSize: 10, fontFamily: font }}>{s.name}</span>
                            <span style={{ color: "#22C55E", fontSize: 10, fontWeight: 700, fontFamily: font }}>{(s.avg_change_pct ?? 0) >= 0 ? "+" : ""}{s.avg_change_pct}%</span>
                        </div>
                    ))}
                </div>
                <div style={{ width: 1, background: "#222" }} />
                <div style={{ flex: 1 }}>
                    <span style={{ color: "#EF4444", fontSize: 9, fontWeight: 700, display: "block", marginBottom: 4 }}>BOTTOM</span>
                    {(st.bottom3_sectors || []).map((s: any, i: number) => (
                        <div key={s.name ?? i} style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", borderBottom: "1px solid #1A1A1A" }}>
                            <span style={{ color: "#888", fontSize: 10, fontFamily: font }}>{s.name}</span>
                            <span style={{ color: "#EF4444", fontSize: 10, fontWeight: 700, fontFamily: font }}>{s.avg_change_pct}%</span>
                        </div>
                    ))}
                </div>
            </div>
            {(st.rotation_in?.length > 0 || st.rotation_out?.length > 0) && (
                <div style={{ marginTop: 6, display: "flex", gap: 12, flexWrap: "wrap" }}>
                    {st.rotation_in?.length > 0 && (
                        <span style={{ color: "#22C55E", fontSize: 9, fontFamily: font }}>IN: {st.rotation_in.join(", ")}</span>
                    )}
                    {st.rotation_out?.length > 0 && (
                        <span style={{ color: "#EF4444", fontSize: 9, fontFamily: font }}>OUT: {st.rotation_out.join(", ")}</span>
                    )}
                </div>
            )}
        </div>
    )
}

function formatPrice(price: number, usd?: boolean): string {
    if (usd) return `$${Number(price).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    return `${price?.toLocaleString()}원`
}

function formatVolume(value: number, usd?: boolean): string {
    if (usd) return `$${(value / 1e6).toFixed(1)}M`
    return `${(value / 1e8).toFixed(0)}억`
}

function formatMarketCap(value: number, usd?: boolean): string {
    if (usd) return `$${(value / 1e9).toFixed(1)}B`
    return `${(value / 1e12).toFixed(2)}조`
}

function _normalizeApi(raw: string): string {
    let s = (raw || "").trim().replace(/\/+$/, "")
    if (!s) return ""
    if (!/^https?:\/\//i.test(s)) s = `https://${s.replace(/^\/+/, "")}`
    return s.replace(/\/+$/, "")
}

function _getVerityUserId(): string {
    if (typeof window === "undefined") return "anon"
    let uid = localStorage.getItem("verity_user_id")
    if (!uid) {
        uid = crypto.randomUUID?.() || `u-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
        localStorage.setItem("verity_user_id", uid)
    }
    return uid
}

const BUSINESS_NODE_LABELS: Record<string, string> = {
    "메모리·파운드리 리드": "메모리·파운드리 핵심",
    "장비/소재": "장비·소재",
}

function _cleanBusinessLabel(v: string): string {
    return String(v || "")
        .replace(/\s+/g, " ")
        .replace(/[|]/g, " ")
        .trim()
}

function getBusinessTagline(stock: any): string {
    const tagline = (stock?.company_tagline || "").trim()
    if (tagline) return tagline

    const roles = Array.isArray(stock?.value_chain?.roles) ? stock.value_chain.roles : []
    if (roles.length > 0) {
        const first = roles[0] || {}
        const sector = _cleanBusinessLabel(first?.sector_label_ko || "")
        const rawNode = _cleanBusinessLabel(first?.node_label_ko || "")
        const node = BUSINESS_NODE_LABELS[rawNode] || rawNode
        if (sector && node) return `${sector} ${node} 기업`
        if (sector) return `${sector} 관련 기업`
    }

    const nicheKeyword = _cleanBusinessLabel(stock?.niche_data?.trends?.keyword || "")
    if (nicheKeyword) return `${nicheKeyword} 관련 기업`

    const ctype = _cleanBusinessLabel(stock?.company_type || "")
    if (ctype) return ctype.includes("기업") ? ctype : `${ctype} 기업`

    return isUSMarket(stock?.market || "", stock?.currency) ? "미국 상장 기업" : "국내 상장 기업"
}

export default function StockDashboard(props: Props) {
    const { dataUrl, recUrl, market = "kr" } = props
    const api = _normalizeApi(props.apiBase) || _normalizeApi(API_BASE)
    const isUS = market === "us"
    const [data, setData] = useState<any>(null)
    const [fullRecMap, setFullRecMap] = useState<Record<string, any>>({})
    const [selected, setSelected] = useState(0)
    const [tab, setTab] = useState<"all" | "buy" | "watch" | "avoid">("all")
    const [detailTab, setDetailTab] = useState<
        "overview" | "brain" | "technical" | "sentiment" | "macro" | "predict" | "timing" | "niche" | "property" | "quant" | "group"
    >("overview")

    const [watchGroups, setWatchGroups] = useState<any[]>([])
    const [showGroupPicker, setShowGroupPicker] = useState(false)

    const loadWatchGroups = useCallback(() => {
        const uid = _getVerityUserId()
        fetch(`${api}/api/watchgroups?user_id=${encodeURIComponent(uid)}`, { mode: "cors", credentials: "omit" })
            .then(r => r.json())
            .then(d => { if (Array.isArray(d)) setWatchGroups(d) })
            .catch(() => {})
    }, [api])

    useEffect(() => { loadWatchGroups() }, [loadWatchGroups])

    const addToWatchGroup = useCallback((groupId: string, ticker: string, name: string) => {
        const uid = _getVerityUserId()
        fetch(`${api}/api/watchgroups`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                action: "add_item",
                user_id: uid,
                group_id: groupId,
                ticker,
                name,
                market: isUS ? "us" : "kr",
            }),
            mode: "cors", credentials: "omit",
        }).then(() => { setShowGroupPicker(false); loadWatchGroups() }).catch(() => {})
    }, [api, isUS, loadWatchGroups])

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchPortfolioJson(dataUrl, ac.signal).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    useEffect(() => {
        const url = recUrl || REC_URL
        if (!url) return
        const ac = new AbortController()
        fetchPortfolioJson(url, ac.signal)
            .then((arr: any) => {
                if (ac.signal.aborted || !Array.isArray(arr)) return
                const m: Record<string, any> = {}
                arr.forEach((r: any) => { if (r?.ticker) m[r.ticker] = r })
                setFullRecMap(m)
            })
            .catch(() => {})
        return () => ac.abort()
    }, [recUrl])

    const allRecs: any[] = data?.recommendations || []
    const recs = isUS
        ? allRecs.filter((r) => isUSMarket(r.market, r.currency))
        : allRecs.filter((r) => isKRX(r.market || ""))
    const macro: any = data?.macro || {}

    const filtered =
        tab === "all"
            ? recs
            : recs.filter((r) => r.recommendation === tab.toUpperCase())
    // slim rec에 fullRecMap의 상세 데이터 병합 (ticker 기준)
    const rawStock = recs[selected] || null
    const stock = rawStock ? { ...rawStock, ...(fullRecMap[rawStock.ticker] || {}) } : null
    const mf = stock?.multi_factor || {}
    const tech = stock?.technical || {}
    const sent = stock?.sentiment || {}
    const flow = stock?.flow || {}
    const breakdown = mf.factor_breakdown || {}

    const multiScore = mf.multi_score ?? 0
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
                        const ms = s.multi_factor?.multi_score ?? s.safety_score ?? 0
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
                                <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 0 }}>
                                    <span style={{ ...listRecDot, background: rBadge }} />
                                    <div style={{ display: "flex", flexDirection: "column", gap: 2, flex: 1, minWidth: 0 }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 4, minWidth: 0 }}>
                                            <span style={listName}>{s.name}</span>
                                            {s.company_type && (
                                                <span style={{ fontSize: 9, fontWeight: 700, color: "#B5FF19", background: "#0D1A00", border: "1px solid #1A2A00", borderRadius: 3, padding: "1px 5px", whiteSpace: "nowrap" as const, flexShrink: 0 }}>{s.company_type}</span>
                                            )}
                                        </div>
                                        <span style={listTicker}>{s.ticker} · {s.market} · {getBusinessTagline(s)}{hasClaude ? " · 🔬" : ""}</span>
                                        {whyText && (
                                            <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 1 }}>
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
                                    <div style={listRight}>
                                        {s.sparkline?.length > 1 && (
                                            <Sparkline data={s.sparkline} width={32} height={16}
                                                color={s.sparkline[s.sparkline.length - 1] >= s.sparkline[0] ? "#22C55E" : "#EF4444"} />
                                        )}
                                        <span style={listPrice}>{formatPrice(s.price, isUS)}</span>
                                        <span style={{ ...listScore, color: msColor }}>{ms}점</span>
                                    </div>
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
                                    {stock.company_type && (
                                        <span style={{ fontSize: 10, fontWeight: 700, color: "#B5FF19", background: "#0D1A00", border: "1px solid #1A2A00", borderRadius: 4, padding: "2px 8px" }}>{stock.company_type}</span>
                                    )}
                                </div>
                                <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
                                    <span style={detailName}>{stock.name}</span>
                                    <span style={detailBusiness}>{getBusinessTagline(stock)}</span>
                                    {watchGroups.length > 0 && (
                                        <div style={{ position: "relative" as const }}>
                                            <button
                                                onClick={() => setShowGroupPicker(!showGroupPicker)}
                                                style={{ background: "#1A1A1A", border: "1px solid #333", borderRadius: 8, padding: "4px 10px", color: "#B5FF19", fontSize: 11, fontWeight: 700, cursor: "pointer", fontFamily: font, whiteSpace: "nowrap" as const }}
                                            >
                                                {showGroupPicker ? "✕" : "⭐ 관심"}
                                            </button>
                                            {showGroupPicker && (
                                                <div style={{ position: "absolute" as const, top: 30, left: 0, zIndex: 20, background: "#111", border: "1px solid #333", borderRadius: 10, padding: 6, minWidth: 160 }}>
                                                    {watchGroups.map((g: any) => (
                                                        <div
                                                            key={g.id}
                                                            onClick={() => addToWatchGroup(g.id, stock.ticker, stock.name)}
                                                            style={{ padding: "6px 10px", borderRadius: 6, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}
                                                            onMouseEnter={e => (e.currentTarget.style.background = "#1A1A1A")}
                                                            onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                                                        >
                                                            <span style={{ fontSize: 14 }}>{g.icon}</span>
                                                            <span style={{ color: "#ccc", fontSize: 11, fontWeight: 600 }}>{g.name}</span>
                                                            <span style={{ color: "#555", fontSize: 9, marginLeft: "auto" }}>{g.items?.length || 0}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </div>
                                <span style={detailTicker}>{stock.ticker} · {formatPrice(stock.price, isUS)}</span>
                                {stock.sparkline?.length > 1 && (
                                    <div style={{ marginTop: 4 }}>
                                        <Sparkline data={stock.sparkline} width={180} height={36}
                                            color={stock.sparkline[stock.sparkline.length - 1] >= stock.sparkline[0] ? "#22C55E" : "#EF4444"} />
                                    </div>
                                )}
                                <p style={detailVerdict}>{stock.ai_verdict || "분석 대기 중"}</p>
                                <TrendBlock stock={stock} isUS={isUS} />
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
                            {([["overview", "개요"], ["brain", "브레인"], ["quant", "퀀트"], ["timing", "매매시점"], ["technical", "기술적"], ["sentiment", "뉴스/수급"], ["macro", "매크로"], ["property", "부동산"], ["group", "관계회사"], ["niche", "틈새"], ["predict", "예측"]] as const).map(([k, l]) => (
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
                                        {stock.dual_consensus && (
                                            <div style={{
                                                marginTop: 8,
                                                padding: "8px 10px",
                                                background: stock.dual_consensus.manual_review_required ? "#1A0A0A" : "#0A111A",
                                                border: `1px solid ${stock.dual_consensus.manual_review_required ? "#3A1A1A" : "#1A2F45"}`,
                                                borderRadius: 8,
                                            }}>
                                                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4, flexWrap: "wrap" }}>
                                                    <span style={{ background: "#0EA5E9", color: "#001018", fontSize: 9, fontWeight: 800, padding: "2px 6px", borderRadius: 4, fontFamily: font }}>
                                                        HYBRID
                                                    </span>
                                                    <span style={{ color: "#93C5FD", fontSize: 10, fontWeight: 700, fontFamily: font }}>
                                                        최종 {stock.dual_consensus.final_recommendation} · 신뢰 {stock.dual_consensus.final_confidence}
                                                    </span>
                                                    <span style={{ color: stock.dual_consensus.manual_review_required ? "#EF4444" : "#22C55E", fontSize: 10, fontWeight: 700, fontFamily: font }}>
                                                        {stock.dual_consensus.manual_review_required ? "수동검토 필요" : `합의 ${stock.dual_consensus.conflict_level}`}
                                                    </span>
                                                </div>
                                                <div style={{ color: "#888", fontSize: 10, lineHeight: "1.4", fontFamily: font }}>
                                                    Gemini {stock.dual_consensus.gemini_recommendation} ({stock.dual_consensus.gemini_confidence}) · Claude {stock.dual_consensus.claude_recommendation} ({stock.dual_consensus.claude_confidence})
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                    <div style={metricsGrid}>
                                        <MetricCard label="PER" value={stock.per?.toFixed(1) || "—"} />
                                        <MetricCard label="고점대비" value={`${stock.drop_from_high_pct?.toFixed(1)}%`}
                                            color={(stock.drop_from_high_pct || 0) <= -20 ? "#B5FF19" : "#fff"} />
                                        <MetricCard label="배당률" value={`${stock.div_yield?.toFixed(1)}%`} />
                                        <MetricCard label="거래대금" value={stock.trading_value ? formatVolume(stock.trading_value, isUS) : "—"} />
                                        <MetricCard label="시총" value={stock.market_cap ? formatMarketCap(stock.market_cap, isUS) : "—"} />
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

                                    {/* 종목 최신 뉴스 */}
                                    {(() => {
                                        const links: any[] = stock?.sentiment?.top_headline_links || []
                                        const details: any[] = stock?.sentiment?.detail || []
                                        const plain: string[] = stock?.sentiment?.top_headlines || []
                                        const richItems = links.length > 0
                                            ? links.slice(0, 5)
                                            : details.filter((d: any) => d.url).slice(0, 5)

                                        if (richItems.length === 0 && plain.length === 0) return null
                                        return (
                                            <div style={{ marginTop: 4 }}>
                                                <div style={{ color: "#666", fontSize: 11, fontWeight: 600, marginBottom: 6 }}>최신 뉴스</div>
                                                {richItems.length > 0
                                                    ? richItems.map((item: any, i: number) => {
                                                        const sentColor = item.label === "positive" ? "#22C55E" : item.label === "negative" ? "#EF4444" : "#555"
                                                        return (
                                                            <a key={i} href={item.url} target="_blank" rel="noopener noreferrer"
                                                                style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 10px", background: "#111", borderRadius: 8, marginBottom: 4, textDecoration: "none", transition: "background 0.15s", cursor: "pointer" }}
                                                                onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "#1A1A1A" }}
                                                                onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "#111" }}>
                                                                {item.label && <span style={{ width: 4, height: 4, borderRadius: 2, background: sentColor, flexShrink: 0 }} />}
                                                                <span style={{ color: "#bbb", fontSize: 11, lineHeight: 1.4, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.title}</span>
                                                                <span style={{ color: "#444", fontSize: 10, flexShrink: 0 }}>↗</span>
                                                            </a>
                                                        )
                                                    })
                                                    : plain.slice(0, 5).map((h: string, i: number) => (
                                                        <div key={i} style={{ ...newsRow, marginBottom: 4 }}>
                                                            <span style={{ color: "#aaa", fontSize: 11, lineHeight: 1.4 }}>{h}</span>
                                                        </div>
                                                    ))
                                                }
                                            </div>
                                        )
                                    })()}

                                    {/* 글로벌 시장 뉴스 */}
                                    {(() => {
                                        const globalNews: any[] = data?.headlines || []
                                        if (globalNews.length === 0) return null
                                        const rowBase: React.CSSProperties = { display: "flex", alignItems: "center", gap: 8, padding: "7px 10px", background: "#111", borderRadius: 8, marginBottom: 4, textDecoration: "none", transition: "background 0.15s" }
                                        return (
                                            <div style={{ marginTop: 4 }}>
                                                <div style={{ color: "#666", fontSize: 11, fontWeight: 600, marginBottom: 6 }}>시장 뉴스</div>
                                                {globalNews.slice(0, 6).map((h: any, i: number) => {
                                                    const sc = h.sentiment === "positive" ? "#22C55E" : h.sentiment === "negative" ? "#EF4444" : "#555"
                                                    const href = h.link || h.url || ""
                                                    const inner = (
                                                        <>
                                                            <span style={{ width: 4, height: 4, borderRadius: 2, background: sc, flexShrink: 0 }} />
                                                            <span style={{ color: "#bbb", fontSize: 11, lineHeight: 1.4, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{h.title}</span>
                                                            {h.source && <span style={{ color: "#444", fontSize: 9, flexShrink: 0 }}>{h.source}</span>}
                                                            {h.time && <span style={{ color: "#333", fontSize: 9, flexShrink: 0 }}>{h.time.slice(5, 16)}</span>}
                                                            {href && <span style={{ color: "#444", fontSize: 10, flexShrink: 0 }}>↗</span>}
                                                        </>
                                                    )
                                                    return href ? (
                                                        <a key={i} href={href} target="_blank" rel="noopener noreferrer" style={{ ...rowBase, cursor: "pointer" }}
                                                            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "#1A1A1A" }}
                                                            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "#111" }}>
                                                            {inner}
                                                        </a>
                                                    ) : (
                                                        <div key={i} style={rowBase}>{inner}</div>
                                                    )
                                                })}
                                            </div>
                                        )
                                    })()}

                                    {/* US 전용: 프리/애프터마켓, 애널리스트, 실적 서프라이즈 */}
                                    {isUS && stock.pre_after_market && (stock.pre_after_market.pre_price || stock.pre_after_market.after_price) && (
                                        <div style={{ marginTop: 4 }}>
                                            <div style={{ color: "#666", fontSize: 11, fontWeight: 600, marginBottom: 6 }}>프리/애프터마켓</div>
                                            <div style={metricsGrid}>
                                                {stock.pre_after_market.pre_price != null && <MetricCard label="프리마켓" value={formatPrice(stock.pre_after_market.pre_price, true)} color={stock.pre_after_market.pre_change_pct > 0 ? "#22C55E" : stock.pre_after_market.pre_change_pct < 0 ? "#FF4D4D" : "#fff"} />}
                                                {stock.pre_after_market.pre_change_pct != null && <MetricCard label="프리 변동" value={`${stock.pre_after_market.pre_change_pct > 0 ? "+" : ""}${stock.pre_after_market.pre_change_pct.toFixed(2)}%`} color={stock.pre_after_market.pre_change_pct > 0 ? "#22C55E" : "#FF4D4D"} />}
                                                {stock.pre_after_market.after_price != null && <MetricCard label="애프터마켓" value={formatPrice(stock.pre_after_market.after_price, true)} color={(stock.pre_after_market.after_change_pct || 0) > 0 ? "#22C55E" : (stock.pre_after_market.after_change_pct || 0) < 0 ? "#FF4D4D" : "#fff"} />}
                                            </div>
                                        </div>
                                    )}
                                    {isUS && stock.analyst_consensus && (stock.analyst_consensus.buy > 0 || stock.analyst_consensus.hold > 0 || stock.analyst_consensus.sell > 0) && (
                                        <div style={{ marginTop: 8 }}>
                                            <div style={{ color: "#666", fontSize: 11, fontWeight: 600, marginBottom: 6 }}>애널리스트 의견</div>
                                            <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 4 }}>
                                                <span style={{ background: "#22C55E", color: "#000", fontSize: 10, fontWeight: 800, padding: "2px 8px", borderRadius: 4 }}>매수 {stock.analyst_consensus.buy}</span>
                                                <span style={{ background: "#FFD600", color: "#000", fontSize: 10, fontWeight: 800, padding: "2px 8px", borderRadius: 4 }}>중립 {stock.analyst_consensus.hold}</span>
                                                <span style={{ background: "#FF4D4D", color: "#000", fontSize: 10, fontWeight: 800, padding: "2px 8px", borderRadius: 4 }}>매도 {stock.analyst_consensus.sell}</span>
                                            </div>
                                            {stock.analyst_consensus.target_mean > 0 && (
                                                <div style={{ display: "flex", gap: 6 }}>
                                                    <MetricCard label="목표가" value={formatPrice(stock.analyst_consensus.target_mean, true)} />
                                                    <MetricCard label="업사이드" value={`${stock.analyst_consensus.upside_pct > 0 ? "+" : ""}${stock.analyst_consensus.upside_pct}%`} color={stock.analyst_consensus.upside_pct > 0 ? "#22C55E" : "#FF4D4D"} />
                                                </div>
                                            )}
                                        </div>
                                    )}
                                    {isUS && Array.isArray(stock.earnings_surprises) && stock.earnings_surprises.length > 0 && (
                                        <div style={{ marginTop: 8 }}>
                                            <div style={{ color: "#666", fontSize: 11, fontWeight: 600, marginBottom: 6 }}>실적 서프라이즈</div>
                                            <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.min(stock.earnings_surprises.length, 4)}, 1fr)`, gap: 6 }}>
                                                {stock.earnings_surprises.slice(0, 4).map((es: any, i: number) => {
                                                    const sp = es.surprise_pct || 0
                                                    return <div key={i}><MetricCard label={es.period || `Q${4 - i}`} value={`${sp > 0 ? "+" : ""}${sp.toFixed(1)}%`} color={sp > 0 ? "#22C55E" : sp < 0 ? "#FF4D4D" : "#888"} /></div>
                                                })}
                                            </div>
                                        </div>
                                    )}
                                    {isUS && (
                                        <a href={`https://finance.yahoo.com/quote/${stock.ticker}`} target="_blank" rel="noopener noreferrer"
                                            style={{ display: "inline-flex", alignItems: "center", gap: 6, marginTop: 8, padding: "8px 14px", background: "#111", border: "1px solid #222", borderRadius: 8, color: "#60A5FA", fontSize: 12, fontWeight: 700, textDecoration: "none" }}>
                                            Yahoo Finance ↗
                                        </a>
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
                                        {(() => {
                                            const links: any[] = sent.top_headline_links || []
                                            const details: any[] = sent.detail || []
                                            const plain: string[] = sent.top_headlines || []
                                            const hasLinks = links.length > 0 || details.some((d: any) => d.url)

                                            if (!hasLinks && plain.length === 0) return null
                                            const newsItems = hasLinks
                                                ? (links.length > 0 ? links : details.filter((d: any) => d.url)).slice(0, 8)
                                                : []

                                            return (
                                                <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                                                    <span style={{ color: "#666", fontSize: 11, fontWeight: 600 }}>최근 뉴스</span>
                                                    {newsItems.length > 0
                                                        ? newsItems.map((item: any, i: number) => {
                                                            const sc = item.label === "positive" ? "#22C55E" : item.label === "negative" ? "#EF4444" : "#555"
                                                            return (
                                                                <a key={i} href={item.url} target="_blank" rel="noopener noreferrer"
                                                                    style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", background: "#111", borderRadius: 8, textDecoration: "none", transition: "background 0.15s", cursor: "pointer" }}
                                                                    onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "#1A1A1A" }}
                                                                    onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "#111" }}>
                                                                    {item.label && <span style={{ width: 5, height: 5, borderRadius: 3, background: sc, flexShrink: 0 }} />}
                                                                    <span style={{ color: "#aaa", fontSize: 12, lineHeight: 1.5, flex: 1 }}>{item.title}</span>
                                                                    <span style={{ color: "#444", fontSize: 11, flexShrink: 0 }}>↗</span>
                                                                </a>
                                                            )
                                                        })
                                                        : plain.map((h: string, i: number) => (
                                                            <div key={i} style={newsRow}>
                                                                <span style={{ color: "#aaa", fontSize: 12, lineHeight: 1.5 }}>{h}</span>
                                                            </div>
                                                        ))
                                                    }
                                                </div>
                                            )
                                        })()}
                                        {/* US: 내부자 심리 */}
                                        {isUS && stock.insider_sentiment && (stock.insider_sentiment.positive_count > 0 || stock.insider_sentiment.negative_count > 0) && (
                                            <div style={{ marginTop: 12 }}>
                                                <div style={{ color: "#666", fontSize: 11, fontWeight: 600, marginBottom: 6 }}>내부자 심리 (90일)</div>
                                                <div style={metricsGrid}>
                                                    <MetricCard label="MSPR" value={stock.insider_sentiment.mspr?.toFixed(4) || "0"} color={stock.insider_sentiment.mspr > 0 ? "#22C55E" : stock.insider_sentiment.mspr < 0 ? "#FF4D4D" : "#888"} />
                                                    <MetricCard label="순매수" value={String(stock.insider_sentiment.positive_count)} color="#22C55E" />
                                                    <MetricCard label="순매도" value={String(stock.insider_sentiment.negative_count)} color="#FF4D4D" />
                                                </div>
                                            </div>
                                        )}
                                        {/* US: 기관 보유 */}
                                        {isUS && stock.institutional_ownership && stock.institutional_ownership.total_holders > 0 && (
                                            <div style={{ marginTop: 12 }}>
                                                <div style={{ color: "#666", fontSize: 11, fontWeight: 600, marginBottom: 6 }}>기관 보유 현황</div>
                                                <div style={metricsGrid}>
                                                    <MetricCard label="기관수" value={String(stock.institutional_ownership.total_holders)} />
                                                    <MetricCard label="변동률" value={stock.institutional_ownership.change_pct ? `${stock.institutional_ownership.change_pct > 0 ? "+" : ""}${stock.institutional_ownership.change_pct}%` : "—"} color={(stock.institutional_ownership.change_pct || 0) > 0 ? "#22C55E" : (stock.institutional_ownership.change_pct || 0) < 0 ? "#FF4D4D" : "#888"} />
                                                </div>
                                            </div>
                                        )}
                                        {/* US: 공매도 현황 (yfinance 기반, NYSE/NASDAQ 공시) */}
                                        {isUS && stock.short_interest && (stock.short_interest.short_pct != null || stock.short_interest.days_to_cover != null) && (() => {
                                            const si = stock.short_interest
                                            const sp = Number(si.short_pct)
                                            const shortColor = sp >= 20 ? "#FF4D4D" : sp >= 10 ? "#FFD600" : "#B5FF19"
                                            const trendMap: Record<string, { label: string; color: string }> = {
                                                surge: { label: "급증", color: "#FF4D4D" },
                                                up: { label: "증가", color: "#FFD600" },
                                                flat: { label: "유지", color: "#888" },
                                                down: { label: "감소", color: "#60A5FA" },
                                                drop: { label: "급감", color: "#22C55E" },
                                            }
                                            const tr = si.trend ? trendMap[si.trend] : null
                                            return (
                                                <div style={{ marginTop: 12 }}>
                                                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                                                        <span style={{ color: "#666", fontSize: 11, fontWeight: 600 }}>공매도 현황</span>
                                                        {si.report_date && <span style={{ color: "#444", fontSize: 10 }}>기준 {si.report_date}</span>}
                                                    </div>
                                                    <div style={metricsGrid}>
                                                        {si.short_pct != null && (
                                                            <MetricCard label="Short % Float" value={`${si.short_pct}%`} color={shortColor} />
                                                        )}
                                                        {si.days_to_cover != null && (
                                                            <MetricCard label="Days to Cover" value={String(si.days_to_cover)} color={si.days_to_cover >= 5 ? "#FF4D4D" : si.days_to_cover >= 2 ? "#FFD600" : "#888"} />
                                                        )}
                                                        {tr && (
                                                            <MetricCard label="전월 대비" value={tr.label} color={tr.color} />
                                                        )}
                                                    </div>
                                                    {sp >= 20 && (
                                                        <div style={{ marginTop: 6, padding: "6px 10px", background: "#2A0000", border: "1px solid #5A0000", borderRadius: 6, color: "#FF9999", fontSize: 11 }}>
                                                            Short % 20% 초과 — 스퀴즈·하락 리스크 모두 주의
                                                        </div>
                                                    )}
                                                    {si.trend === "surge" && (
                                                        <div style={{ marginTop: 6, padding: "6px 10px", background: "#2A1800", border: "1px solid #5A3A00", borderRadius: 6, color: "#FFC266", fontSize: 11 }}>
                                                            공매도 전월比 +15% 이상 급증 — 기관 하락 베팅 확대
                                                        </div>
                                                    )}
                                                </div>
                                            )
                                        })()}
                                        {/* US: Finnhub 기업 뉴스 */}
                                        {isUS && Array.isArray(stock.company_news) && stock.company_news.length > 0 && (
                                            <div style={{ marginTop: 8 }}>
                                                <div style={{ color: "#60A5FA", fontSize: 11, fontWeight: 600, marginBottom: 6 }}>Finnhub 뉴스</div>
                                                {stock.company_news.slice(0, 5).map((n: any, i: number) => (
                                                    <a key={i} href={n.url || "#"} target="_blank" rel="noopener noreferrer"
                                                        style={{ display: "block", padding: "6px 10px", background: "#111", borderRadius: 6, marginBottom: 3, textDecoration: "none" }}>
                                                        <span style={{ color: "#bbb", fontSize: 11, lineHeight: 1.4 }}>{n.title}</span>
                                                        {n.source && <span style={{ color: "#444", fontSize: 9, marginLeft: 6 }}>{n.source}</span>}
                                                    </a>
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
                                    <SectorTrendView sectorTrends={data?.sector_trends} />
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

                                        {/* 13F 스마트머니 보너스 (US 종목 분기 데이터 존재 시) */}
                                        {typeof brain.inst_13f_bonus === "number" && brain.inst_13f_bonus > 0 && (
                                            <div style={{
                                                background: "rgba(96,165,250,0.06)",
                                                border: "1px solid #60A5FA40",
                                                borderRadius: 10, padding: "10px 14px",
                                            }}>
                                                <span style={{ color: "#60A5FA", fontSize: 12, fontWeight: 700 }}>
                                                    13F 스마트머니 +{brain.inst_13f_bonus}
                                                </span>
                                                <span style={{ color: "#666", fontSize: 11, marginLeft: 8 }}>
                                                    (기관 분기 포지션 보너스)
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
                                const mc = macro?.niche_credit || {}
                                const secFilings: any[] = stock?.sec_filings || []
                                const insiderSent = stock?.insider_sentiment || {}
                                const instOwn = stock?.institutional_ownership || {}
                                const finFacts = stock?.sec_financials || stock?.financial_facts || {}
                                const hasUSDeep = secFilings.length > 0 || insiderSent.mspr != null || instOwn.total_holders > 0 || finFacts.fcf != null
                                const hasAny =
                                    (n.trends && Object.keys(n.trends).length > 0) ||
                                    (n.legal && (n.legal.hits?.length > 0 || n.legal.risk_flag)) ||
                                    (n.credit && (n.credit.ig_spread_pp != null || n.credit.debt_ratio_pct != null || n.credit.note)) ||
                                    (mc.corporate_spread_vs_gov_pp != null || mc.alert) ||
                                    (isUS && hasUSDeep)

                                const nicheCardStyle: React.CSSProperties = { background: "#0A0A0A", border: "1px solid #1A1A1A", borderRadius: 10, padding: 12 }
                                const nicheChip: React.CSSProperties = { background: "#0D1A00", color: "#B5FF19", fontSize: 9, fontWeight: 800, padding: "2px 6px", borderRadius: 4, letterSpacing: 0.5 }
                                const nicheCardTitle: React.CSSProperties = { color: "#ccc", fontSize: 12, fontWeight: 700 }
                                const nicheRowStyle: React.CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }
                                const nicheMuted: React.CSSProperties = { color: "#555", fontSize: 11, lineHeight: 1.5 }
                                const nicheBidRow: React.CSSProperties = { background: "#111", borderRadius: 8, padding: "8px 10px", border: "1px solid #1A1A1A" }

                                return (
                                    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                                        <span style={{ color: "#fff", fontSize: 14, fontWeight: 700 }}>
                                            {isUS ? "Deep Intel" : "틈새 정보"} — {stock.name}
                                        </span>

                                        {!hasAny && (
                                            <div style={{ background: "#0A0A0A", borderRadius: 10, padding: 12, border: "1px dashed #333" }}>
                                                <span style={{ color: "#888", fontSize: 12, lineHeight: 1.5 }}>
                                                    틈새 데이터(트렌드·법 리스크·신용)는 백엔드 수집기 연동 후 표시됩니다.
                                                </span>
                                            </div>
                                        )}

                                        {/* Trends */}
                                        <div style={nicheCardStyle}>
                                            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                                                <span style={nicheChip}>Trends</span>
                                                <span style={nicheCardTitle}>검색·관심도</span>
                                            </div>
                                            {n.trends?.keyword || n.trends?.interest_index != null ? (
                                                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                                    <div style={nicheRowStyle}>
                                                        <span style={{ color: "#666", fontSize: 11 }}>키워드</span>
                                                        <span style={{ color: "#fff", fontSize: 12, fontWeight: 700 }}>{n.trends.keyword || "—"}</span>
                                                    </div>
                                                    <div style={nicheRowStyle}>
                                                        <span style={{ color: "#666", fontSize: 11 }}>관심 지수</span>
                                                        <span style={{ color: "#fff", fontSize: 12, fontWeight: 700 }}>{String(n.trends.interest_index ?? "—")}</span>
                                                    </div>
                                                    {n.trends.week_change_pct != null && (
                                                        <div style={nicheRowStyle}>
                                                            <span style={{ color: "#666", fontSize: 11 }}>주간 변화</span>
                                                            <span style={{ color: n.trends.week_change_pct >= 0 ? "#22C55E" : "#EF4444", fontSize: 12, fontWeight: 700 }}>
                                                                {n.trends.week_change_pct >= 0 ? "+" : ""}{n.trends.week_change_pct}%
                                                            </span>
                                                        </div>
                                                    )}
                                                    {n.trends.note && <p style={{ color: "#777", fontSize: 11, lineHeight: 1.45, margin: "6px 0 0" }}>{n.trends.note}</p>}
                                                </div>
                                            ) : (
                                                <span style={nicheMuted}>주 1회 수집 예정 (소비·게임·뷰티 등)</span>
                                            )}
                                        </div>

                                        {/* Risk */}
                                        <div style={nicheCardStyle}>
                                            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                                                <span style={nicheChip}>Risk</span>
                                                <span style={nicheCardTitle}>소송·리스크 키워드</span>
                                            </div>
                                            {n.legal?.risk_flag && (
                                                <div style={{ background: "#1A0A0A", border: "1px solid #3A1515", borderRadius: 8, padding: "8px 10px", marginBottom: 8 }}>
                                                    <span style={{ color: "#FF4D4D", fontSize: 12, fontWeight: 700 }}>리스크 플래그 ON</span>
                                                </div>
                                            )}
                                            {n.legal?.hits?.length > 0 ? (
                                                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                                    {n.legal.hits.slice(0, 6).map((h: any, i: number) => (
                                                        <div key={i} style={{ background: "#111", borderRadius: 8, padding: "8px 10px" }}>
                                                            <span style={{ color: "#aaa", fontSize: 11, lineHeight: 1.45 }}>
                                                                {typeof h === "string" ? h : h != null ? String(h) : "—"}
                                                            </span>
                                                        </div>
                                                    ))}
                                                </div>
                                            ) : (
                                                <span style={nicheMuted}>뉴스 RSS에서 소송·판결·가압류 등 매칭 시 표시</span>
                                            )}
                                        </div>

                                        {/* Credit */}
                                        <div style={nicheCardStyle}>
                                            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                                                <span style={nicheChip}>Credit</span>
                                                <span style={nicheCardTitle}>신용·유동성</span>
                                            </div>
                                            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                                {n.credit?.ig_spread_pp != null && (
                                                    <div style={nicheRowStyle}>
                                                        <span style={{ color: "#666", fontSize: 11 }}>IG 스프레드</span>
                                                        <span style={{ color: "#fff", fontSize: 12, fontWeight: 700 }}>{n.credit.ig_spread_pp}%p</span>
                                                    </div>
                                                )}
                                                {n.credit?.debt_ratio_pct != null && (
                                                    <div style={nicheRowStyle}>
                                                        <span style={{ color: "#666", fontSize: 11 }}>부채비율</span>
                                                        <span style={{ color: n.credit.debt_ratio_pct > 100 ? "#FF4D4D" : "#22C55E", fontSize: 12, fontWeight: 700 }}>{n.credit.debt_ratio_pct.toFixed(0)}%</span>
                                                    </div>
                                                )}
                                                {n.credit?.alert && (
                                                    <div style={{ color: "#FF9F40", fontSize: 11 }}>종목 단위 신용 알림</div>
                                                )}
                                                {n.credit?.note && <p style={{ color: "#777", fontSize: 11, lineHeight: 1.45, margin: "6px 0 0" }}>{n.credit.note}</p>}
                                                {(mc.corporate_spread_vs_gov_pp != null || mc.alert) && (
                                                    <div style={{ borderTop: "1px solid #222", marginTop: 4, paddingTop: 8 }}>
                                                        <span style={{ color: "#666", fontSize: 10, display: "block", marginBottom: 6 }}>시장 전체 (macro)</span>
                                                        {mc.corporate_spread_vs_gov_pp != null && (
                                                            <div style={nicheRowStyle}>
                                                                <span style={{ color: "#666", fontSize: 11 }}>회사채-국고 스프레드</span>
                                                                <span style={{ color: mc.alert || mc.corporate_spread_vs_gov_pp >= 2 ? "#FF4D4D" : "#22C55E", fontSize: 12, fontWeight: 700 }}>
                                                                    {mc.corporate_spread_vs_gov_pp}%p{mc.alert ? " · 경고" : ""}
                                                                </span>
                                                            </div>
                                                        )}
                                                        {mc.updated_at && <span style={{ color: "#444", fontSize: 10 }}>{mc.updated_at}</span>}
                                                    </div>
                                                )}
                                                {n.credit?.ig_spread_pp == null && n.credit?.debt_ratio_pct == null && mc.corporate_spread_vs_gov_pp == null && !mc.alert && (
                                                    <span style={nicheMuted}>중소형주는 개별 데이터가 없을 수 있음. 시장 전체 지표 위주.</span>
                                                )}
                                            </div>
                                        </div>

                                        {/* US: SEC Filings */}
                                        {isUS && (
                                            <div style={nicheCardStyle}>
                                                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                                                    <span style={nicheChip}>SEC</span>
                                                    <span style={nicheCardTitle}>Recent Filings</span>
                                                </div>
                                                {secFilings.length > 0 ? (
                                                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                                        {secFilings.slice(0, 5).map((f: any, i: number) => (
                                                            <div key={i} style={nicheBidRow}>
                                                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                                                    <span style={{ color: "#A78BFA", fontSize: 10, fontWeight: 700 }}>{f.form_type || "Filing"}</span>
                                                                    <span style={{ color: "#555", fontSize: 9 }}>{f.filed_date || ""}</span>
                                                                </div>
                                                                {f.description && <span style={{ color: "#aaa", fontSize: 10, lineHeight: 1.4 }}>{f.description}</span>}
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <span style={nicheMuted}>SEC 공시 데이터 없음</span>
                                                )}
                                            </div>
                                        )}

                                        {/* US: Insider Sentiment */}
                                        {isUS && (
                                            <div style={nicheCardStyle}>
                                                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                                                    <span style={nicheChip}>Insider</span>
                                                    <span style={nicheCardTitle}>Insider Activity</span>
                                                </div>
                                                {insiderSent.mspr != null ? (
                                                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                                        <div style={nicheRowStyle}>
                                                            <span style={{ color: "#666", fontSize: 11 }}>MSPR</span>
                                                            <span style={{ color: insiderSent.mspr > 0 ? "#22C55E" : insiderSent.mspr < 0 ? "#EF4444" : "#888", fontSize: 12, fontWeight: 700 }}>
                                                                {typeof insiderSent.mspr === "number" && Number.isFinite(insiderSent.mspr) ? `${insiderSent.mspr > 0 ? "+" : ""}${insiderSent.mspr.toFixed(4)}` : "—"}
                                                            </span>
                                                        </div>
                                                        <div style={nicheRowStyle}>
                                                            <span style={{ color: "#666", fontSize: 11 }}>Buy Count</span>
                                                            <span style={{ color: "#22C55E", fontSize: 12, fontWeight: 700 }}>{insiderSent.positive_count || 0}</span>
                                                        </div>
                                                        <div style={nicheRowStyle}>
                                                            <span style={{ color: "#666", fontSize: 11 }}>Sell Count</span>
                                                            <span style={{ color: "#EF4444", fontSize: 12, fontWeight: 700 }}>{insiderSent.negative_count || 0}</span>
                                                        </div>
                                                        {insiderSent.net_shares != null && (
                                                            <div style={nicheRowStyle}>
                                                                <span style={{ color: "#666", fontSize: 11 }}>Net Shares</span>
                                                                <span style={{ color: insiderSent.net_shares > 0 ? "#22C55E" : "#EF4444", fontSize: 12, fontWeight: 700 }}>
                                                                    {typeof insiderSent.net_shares === "number" ? insiderSent.net_shares.toLocaleString() : "—"}
                                                                </span>
                                                            </div>
                                                        )}
                                                    </div>
                                                ) : (
                                                    <span style={nicheMuted}>내부자 거래 데이터 없음</span>
                                                )}
                                            </div>
                                        )}

                                        {/* US: Institutional & Financials */}
                                        {isUS && (
                                            <div style={nicheCardStyle}>
                                                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                                                    <span style={nicheChip}>Inst</span>
                                                    <span style={nicheCardTitle}>Institutional & Financials</span>
                                                </div>
                                                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                                    {instOwn.total_holders > 0 && (
                                                        <>
                                                            <div style={nicheRowStyle}>
                                                                <span style={{ color: "#666", fontSize: 11 }}>Inst. Holders</span>
                                                                <span style={{ color: "#fff", fontSize: 12, fontWeight: 700 }}>{instOwn.total_holders}</span>
                                                            </div>
                                                            {instOwn.change_pct != null && (
                                                                <div style={nicheRowStyle}>
                                                                    <span style={{ color: "#666", fontSize: 11 }}>Holdings Chg</span>
                                                                    <span style={{ color: instOwn.change_pct > 0 ? "#22C55E" : "#EF4444", fontSize: 12, fontWeight: 700 }}>
                                                                        {instOwn.change_pct > 0 ? "+" : ""}{instOwn.change_pct}%
                                                                    </span>
                                                                </div>
                                                            )}
                                                        </>
                                                    )}
                                                    {finFacts.fcf != null && (
                                                        <div style={nicheRowStyle}>
                                                            <span style={{ color: "#666", fontSize: 11 }}>FCF</span>
                                                            <span style={{ color: finFacts.fcf >= 0 ? "#22C55E" : "#EF4444", fontSize: 12, fontWeight: 700 }}>${(finFacts.fcf / 1e9).toFixed(1)}B</span>
                                                        </div>
                                                    )}
                                                    {finFacts.revenue != null && (
                                                        <div style={nicheRowStyle}>
                                                            <span style={{ color: "#666", fontSize: 11 }}>Revenue</span>
                                                            <span style={{ color: "#fff", fontSize: 12, fontWeight: 700 }}>${(finFacts.revenue / 1e9).toFixed(1)}B</span>
                                                        </div>
                                                    )}
                                                    {finFacts.net_income != null && (
                                                        <div style={nicheRowStyle}>
                                                            <span style={{ color: "#666", fontSize: 11 }}>Net Income</span>
                                                            <span style={{ color: finFacts.net_income >= 0 ? "#22C55E" : "#EF4444", fontSize: 12, fontWeight: 700 }}>${(finFacts.net_income / 1e9).toFixed(1)}B</span>
                                                        </div>
                                                    )}
                                                    {finFacts.operating_income != null && (
                                                        <div style={nicheRowStyle}>
                                                            <span style={{ color: "#666", fontSize: 11 }}>Op. Income</span>
                                                            <span style={{ color: finFacts.operating_income >= 0 ? "#22C55E" : "#EF4444", fontSize: 12, fontWeight: 700 }}>${(finFacts.operating_income / 1e9).toFixed(1)}B</span>
                                                        </div>
                                                    )}
                                                    {finFacts.debt_ratio != null && (
                                                        <div style={nicheRowStyle}>
                                                            <span style={{ color: "#666", fontSize: 11 }}>Debt Ratio</span>
                                                            <span style={{ color: finFacts.debt_ratio > 100 ? "#EF4444" : "#22C55E", fontSize: 12, fontWeight: 700 }}>
                                                                {finFacts.debt_ratio.toFixed(0)}%
                                                            </span>
                                                        </div>
                                                    )}
                                                    {!instOwn.total_holders && finFacts.fcf == null && (
                                                        <span style={nicheMuted}>기관/재무 데이터 대기 중</span>
                                                    )}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                )
                            })()}

                            {detailTab === "property" && isUS && (() => {
                                const props10k = stock?.properties_10k || {}
                                const d = props10k.data || {}
                                const owned: any[] = Array.isArray(d.owned_properties) ? d.owned_properties : []
                                const leased: any[] = Array.isArray(d.leased_properties) ? d.leased_properties : []
                                const hq = d.headquarters || {}
                                const fc = d.facility_count || {}
                                const fmtSqft = (v: any) => {
                                    const n = Number(v)
                                    if (!n || !isFinite(n)) return "—"
                                    if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M sqft`
                                    if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K sqft`
                                    return `${n} sqft`
                                }
                                const useColor = (u: string) => {
                                    const m: Record<string, string> = {
                                        "본사": "#FFD700", "HQ": "#FFD700",
                                        "공장": "#FF9800", "manufacturing": "#FF9800",
                                        "데이터센터": "#60A5FA", "data center": "#60A5FA",
                                        "R&D": "#A78BFA", "연구": "#A78BFA",
                                        "물류센터": "#22C55E", "물류": "#22C55E",
                                        "매장": "#F472B6", "retail": "#F472B6",
                                        "오피스": "#94A3B8", "office": "#94A3B8",
                                    }
                                    for (const k in m) if (u && String(u).toLowerCase().includes(k.toLowerCase())) return m[k]
                                    return "#888"
                                }
                                const hasAny = owned.length > 0 || leased.length > 0 || d.total_owned_sqft || d.total_leased_sqft
                                return (
                                    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                                            <span style={{ color: "#fff", fontSize: 14, fontWeight: 700 }}>부동산 자산 — {stock.name}</span>
                                            {props10k.filed_date && (
                                                <span style={{ color: "#555", fontSize: 10 }}>10-K Item 2 · {props10k.filed_date}</span>
                                            )}
                                        </div>
                                        {hasAny ? (
                                            <>
                                                <div style={metricsGrid}>
                                                    <MetricCard label="소유 총면적" value={fmtSqft(d.total_owned_sqft)} color="#FFD700" />
                                                    <MetricCard label="임차 총면적" value={fmtSqft(d.total_leased_sqft)} color="#60A5FA" />
                                                    <MetricCard label="자산 수" value={`${fc.owned ?? owned.length}/${fc.leased ?? leased.length}`} />
                                                </div>
                                                {hq.location && (
                                                    <div style={{ padding: "10px 12px", background: "#111", border: "1px solid #1A1A1A", borderRadius: 8 }}>
                                                        <div style={{ color: "#666", fontSize: 11, fontWeight: 600, marginBottom: 4 }}>본사</div>
                                                        <div style={{ color: "#fff", fontSize: 13, fontWeight: 600 }}>{hq.location}</div>
                                                        <div style={{ color: "#888", fontSize: 11, marginTop: 2 }}>
                                                            {hq.size_sqft ? fmtSqft(hq.size_sqft) + " · " : ""}
                                                            {hq.status || ""}
                                                            {hq.description ? ` — ${hq.description}` : ""}
                                                        </div>
                                                    </div>
                                                )}
                                                {owned.length > 0 && (
                                                    <div>
                                                        <div style={{ color: "#FFD700", fontSize: 11, fontWeight: 600, marginBottom: 6 }}>소유 부동산 ({owned.length})</div>
                                                        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                                            {owned.slice(0, 30).map((p: any, i: number) => (
                                                                <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", padding: "8px 10px", background: "#0B0B0B", borderLeft: `2px solid ${useColor(p.use)}`, borderRadius: 4 }}>
                                                                    <div style={{ flex: 1, minWidth: 0 }}>
                                                                        <div style={{ color: "#ccc", fontSize: 12, fontWeight: 600 }}>{p.location || "—"}</div>
                                                                        <div style={{ color: "#666", fontSize: 10, marginTop: 2 }}>
                                                                            {p.use || "기타"}{p.segment ? ` · ${p.segment}` : ""}
                                                                            {p.notes ? ` · ${p.notes}` : ""}
                                                                        </div>
                                                                    </div>
                                                                    <div style={{ color: "#fff", fontSize: 12, fontWeight: 700, whiteSpace: "nowrap", marginLeft: 8 }}>
                                                                        {fmtSqft(p.size_sqft)}
                                                                    </div>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}
                                                {leased.length > 0 && (
                                                    <div>
                                                        <div style={{ color: "#60A5FA", fontSize: 11, fontWeight: 600, marginBottom: 6 }}>임차 부동산 ({leased.length})</div>
                                                        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                                            {leased.slice(0, 30).map((p: any, i: number) => (
                                                                <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", padding: "8px 10px", background: "#0B0B0B", borderLeft: `2px solid ${useColor(p.use)}`, borderRadius: 4 }}>
                                                                    <div style={{ flex: 1, minWidth: 0 }}>
                                                                        <div style={{ color: "#ccc", fontSize: 12, fontWeight: 600 }}>{p.location || "—"}</div>
                                                                        <div style={{ color: "#666", fontSize: 10, marginTop: 2 }}>
                                                                            {p.use || "기타"}{p.segment ? ` · ${p.segment}` : ""}
                                                                            {p.notes ? ` · ${p.notes}` : ""}
                                                                        </div>
                                                                    </div>
                                                                    <div style={{ color: "#fff", fontSize: 12, fontWeight: 700, whiteSpace: "nowrap", marginLeft: 8 }}>
                                                                        {fmtSqft(p.size_sqft)}
                                                                    </div>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}
                                                {d.key_insights && (
                                                    <div style={{ padding: "10px 12px", background: "#0A1A0F", border: "1px solid #1A3A1F", borderRadius: 8 }}>
                                                        <div style={{ color: "#B5FF19", fontSize: 11, fontWeight: 600, marginBottom: 4 }}>투자자 인사이트</div>
                                                        <div style={{ color: "#cce", fontSize: 12, lineHeight: 1.5 }}>{d.key_insights}</div>
                                                    </div>
                                                )}
                                                {d.summary_ko && (
                                                    <div style={{ color: "#888", fontSize: 12, lineHeight: 1.5, padding: "4px 0" }}>
                                                        {d.summary_ko}
                                                    </div>
                                                )}
                                                {props10k.source_url && (
                                                    <a href={props10k.source_url} target="_blank" rel="noopener noreferrer"
                                                        style={{ color: "#555", fontSize: 10, textDecoration: "none" }}>
                                                        원문 10-K ↗
                                                    </a>
                                                )}
                                                <div style={{ color: "#444", fontSize: 10, padding: "4px 0" }}>
                                                    SEC EDGAR 10-K Item 2 Properties 기준 (연 1회 공시). Gemini로 구조화 파싱.
                                                </div>
                                            </>
                                        ) : (
                                            <div style={{ color: "#555", fontSize: 12, textAlign: "center", padding: 20 }}>
                                                {props10k.accession
                                                    ? "최신 10-K에서 부동산 세부 정보를 찾지 못했습니다."
                                                    : "10-K Item 2 데이터가 아직 없습니다. full 모드 파이프라인 실행 후 표시됩니다."}
                                            </div>
                                        )}
                                    </div>
                                )
                            })()}

                            {detailTab === "property" && !isUS && (() => {
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

                            {detailTab === "quant" && (() => {
                                const qfScalar = stock?.multi_factor?.quant_factors || {}
                                const qfFull = stock?.quant_factors || {}

                                const toNum = (v: any, fallback = 50) => typeof v === "number" ? v : (typeof v === "object" && v != null ? (v.momentum_score ?? v.quality_score ?? v.volatility_score ?? v.mean_reversion_score ?? fallback) : fallback)
                                const mom = toNum(qfScalar.momentum ?? qfFull.momentum?.momentum_score)
                                const qual = toNum(qfScalar.quality ?? qfFull.quality?.quality_score)
                                const vol = toNum(qfScalar.volatility ?? qfFull.volatility?.volatility_score)
                                const mr = toNum(qfScalar.mean_reversion ?? qfFull.mean_reversion?.mean_reversion_score)

                                const momData = qfFull.momentum || {}
                                const qualData = qfFull.quality || {}
                                const volData = qfFull.volatility || {}
                                const mrData = qfFull.mean_reversion || {}

                                const qColor = (v: number) => v >= 70 ? "#B5FF19" : v >= 50 ? "#FFD600" : "#FF4D4D"

                                const QuantBar = ({ label, score, signals }: { label: string; score: number; signals?: string[] }) => (
                                    <div style={{ marginBottom: 14 }}>
                                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                                            <span style={{ color: "#aaa", fontSize: 12, fontWeight: 600 }}>{label}</span>
                                            <span style={{ color: qColor(score), fontSize: 14, fontWeight: 800 }}>{score}</span>
                                        </div>
                                        <div style={{ height: 6, background: "#1A1A1A", borderRadius: 3 }}>
                                            <div style={{ height: 6, borderRadius: 3, background: qColor(score), width: `${score}%`, transition: "width 0.3s" }} />
                                        </div>
                                        {signals && signals.length > 0 && (
                                            <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 5 }}>
                                                {signals.slice(0, 3).map((s: string, i: number) => (
                                                    <span key={i} style={{ ...signalTag, background: "#0A1A0D", border: "1px solid #1A2A1A", fontSize: 10 }}>{s}</span>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                )

                                const statArb = data?.stat_arb || {}
                                const pairs = statArb.actionable_pairs || []
                                const factorIc = data?.factor_ic || {}
                                const icRanking = factorIc.ranking || []

                                return (
                                    <>
                                        <div style={{ color: "#666", fontSize: 11, fontWeight: 600, marginBottom: 8 }}>학술 퀀트 팩터</div>
                                        <QuantBar label="모멘텀 (Jegadeesh & Titman)" score={mom} signals={momData.signals} />
                                        <QuantBar label="퀄리티 (Piotroski F-Score)" score={qual} signals={qualData.signals} />
                                        <QuantBar label="저변동성 (Ang et al.)" score={vol} signals={volData.signals} />
                                        <QuantBar label="평균회귀 (Hurst)" score={mr} signals={mrData.signals} />

                                        {qualData.piotroski_f !== undefined && (
                                            <div style={{ marginTop: 12, padding: "8px 10px", background: "#0A0A0A", borderRadius: 8, border: "1px solid #1A1A1A" }}>
                                                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                                                    <span style={{ color: "#888", fontSize: 11 }}>Piotroski F-Score</span>
                                                    <span style={{ color: qualData.piotroski_f >= 7 ? "#B5FF19" : qualData.piotroski_f >= 4 ? "#FFD600" : "#FF4D4D", fontSize: 13, fontWeight: 800 }}>{qualData.piotroski_f}/9</span>
                                                </div>
                                                {qualData.altman?.z_score != null && (
                                                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                                                        <span style={{ color: "#888", fontSize: 11 }}>Altman Z-Score</span>
                                                        <span style={{ color: qualData.altman.zone === "safe" ? "#B5FF19" : qualData.altman.zone === "grey" ? "#FFD600" : "#FF4D4D", fontSize: 13, fontWeight: 800 }}>{qualData.altman.z_score}</span>
                                                    </div>
                                                )}
                                            </div>
                                        )}

                                        {mrData.metrics?.hurst != null && (
                                            <div style={{ marginTop: 8, padding: "6px 10px", background: "#0A0A0A", borderRadius: 8, border: "1px solid #1A1A1A" }}>
                                                <div style={{ display: "flex", justifyContent: "space-between" }}>
                                                    <span style={{ color: "#888", fontSize: 11 }}>Hurst Exponent</span>
                                                    <span style={{ color: mrData.metrics.hurst < 0.5 ? "#B5FF19" : "#FF4D4D", fontSize: 13, fontWeight: 800 }}>{mrData.metrics.hurst.toFixed(3)}</span>
                                                </div>
                                                <span style={{ color: "#555", fontSize: 10 }}>{mrData.metrics.hurst < 0.5 ? "회귀형 — 평균회귀 전략 유리" : "추세형 — 모멘텀 전략 유리"}</span>
                                            </div>
                                        )}

                                        {pairs.length > 0 && (
                                            <div style={{ marginTop: 16, borderTop: "1px solid #1A1A1A", paddingTop: 12 }}>
                                                <span style={{ color: "#666", fontSize: 11, fontWeight: 600 }}>통계적 차익거래 페어</span>
                                                {pairs.slice(0, 5).map((p: any, i: number) => (
                                                    <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderBottom: "1px solid #111" }}>
                                                        <span style={{ color: "#ccc", fontSize: 12 }}>{p.name_a} ↔ {p.name_b}</span>
                                                        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                                                            <span style={{ color: Math.abs(p.spread_zscore) >= 2 ? "#B5FF19" : "#888", fontSize: 12, fontWeight: 700 }}>Z={p.spread_zscore?.toFixed(2)}</span>
                                                            <span style={{ fontSize: 9, color: "#555", background: "#111", padding: "2px 6px", borderRadius: 4 }}>{p.spread_signal}</span>
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        )}

                                        {icRanking.length > 0 && (() => {
                                            const thStyle: React.CSSProperties = { padding: "5px 6px", textAlign: "left", fontSize: 10, fontWeight: 700, color: "#555", borderBottom: "1px solid #1A1A1A" }
                                            const tdStyle: React.CSSProperties = { padding: "4px 6px", fontSize: 11, borderBottom: "1px solid #111" }
                                            const sigFactors = factorIc.significant_factors || factorIc.significant || []
                                            const decFactors = factorIc.decaying_factors || factorIc.decaying || []
                                            const monthly = factorIc.monthly_rollup || {}
                                            const mFactors = monthly.by_factor || []

                                            return (
                                                <div style={{ marginTop: 16, borderTop: "1px solid #1A1A1A", paddingTop: 12 }}>
                                                    <span style={{ color: "#666", fontSize: 11, fontWeight: 600 }}>팩터 예측력 순위 (ICIR)</span>
                                                    <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 8 }}>
                                                        <thead>
                                                            <tr>
                                                                <th style={thStyle}>#</th>
                                                                <th style={thStyle}>팩터</th>
                                                                <th style={{ ...thStyle, textAlign: "right" }}>ICIR</th>
                                                                <th style={{ ...thStyle, textAlign: "center" }}>상태</th>
                                                            </tr>
                                                        </thead>
                                                        <tbody>
                                                            {icRanking.slice(0, 10).map((r: any, i: number) => {
                                                                const isSig = sigFactors.includes(r.factor)
                                                                const isDec = decFactors.includes(r.factor)
                                                                return (
                                                                    <tr key={i}>
                                                                        <td style={{ ...tdStyle, color: "#555", fontSize: 10 }}>{i + 1}</td>
                                                                        <td style={{ ...tdStyle, color: "#ccc" }}>{r.factor}</td>
                                                                        <td style={{ ...tdStyle, textAlign: "right", color: Math.abs(r.icir) > 0.5 ? "#B5FF19" : "#888", fontWeight: 700 }}>{r.icir?.toFixed(3)}</td>
                                                                        <td style={{ ...tdStyle, textAlign: "center", fontSize: 9 }}>
                                                                            {isDec && <span style={{ color: "#FF4D4D" }}>붕괴</span>}
                                                                            {isSig && !isDec && <span style={{ color: "#B5FF19" }}>유의미</span>}
                                                                        </td>
                                                                    </tr>
                                                                )
                                                            })}
                                                        </tbody>
                                                    </table>

                                                    {mFactors.length > 0 && (
                                                        <div style={{ marginTop: 12 }}>
                                                            <span style={{ color: "#666", fontSize: 10, fontWeight: 600 }}>{monthly.period_label || "월간"} 평균 ICIR ({monthly.obs_entries || 0}일 기준)</span>
                                                            <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 6 }}>
                                                                <thead>
                                                                    <tr>
                                                                        <th style={thStyle}>#</th>
                                                                        <th style={thStyle}>팩터</th>
                                                                        <th style={{ ...thStyle, textAlign: "right" }}>평균 ICIR</th>
                                                                        <th style={{ ...thStyle, textAlign: "right" }}>관측</th>
                                                                    </tr>
                                                                </thead>
                                                                <tbody>
                                                                    {mFactors.slice(0, 10).map((f: any, i: number) => (
                                                                        <tr key={i}>
                                                                            <td style={{ ...tdStyle, color: "#555", fontSize: 10 }}>{i + 1}</td>
                                                                            <td style={{ ...tdStyle, color: "#ccc" }}>{f.factor}</td>
                                                                            <td style={{ ...tdStyle, textAlign: "right", color: Math.abs(f.avg_icir) > 0.5 ? "#B5FF19" : "#888", fontWeight: 700 }}>{f.avg_icir?.toFixed(3)}</td>
                                                                            <td style={{ ...tdStyle, textAlign: "right", color: "#555", fontSize: 10 }}>{f.obs_days}일</td>
                                                                        </tr>
                                                                    ))}
                                                                </tbody>
                                                            </table>
                                                        </div>
                                                    )}
                                                </div>
                                            )
                                        })()}
                                    </>
                                )
                            })()}

                            {detailTab === "group" && (() => {
                                const gs = stock?.group_structure
                                if (!gs || (!gs.parent && (!gs.subsidiaries || gs.subsidiaries.length === 0))) {
                                    return <div style={{ color: "#666", fontSize: 13, textAlign: "center" as const, padding: 32 }}>관계회사 데이터가 없습니다</div>
                                }
                                const nav = gs.nav_analysis || {}
                                const subs: any[] = gs.subsidiaries || []
                                const discountPct = nav.nav_discount_pct
                                const discountColor = discountPct == null ? "#666" : discountPct < -10 ? "#FF4D4D" : discountPct < 0 ? "#FFD600" : "#B5FF19"
                                const discountLabel = discountPct == null ? "-" : discountPct > 0 ? `+${discountPct}% 할증` : `${discountPct}% 할인`

                                const nodeStyle: React.CSSProperties = {
                                    background: "#1a1a1a", border: "1px solid #333", borderRadius: 10,
                                    padding: "10px 14px", textAlign: "center" as const, minWidth: 120,
                                }
                                const activeNodeStyle: React.CSSProperties = {
                                    ...nodeStyle, border: "1.5px solid #B5FF19", background: "#111",
                                }
                                const edgeLabel: React.CSSProperties = {
                                    color: "#B5FF19", fontSize: 11, fontWeight: 700, padding: "2px 6px",
                                    background: "#000", borderRadius: 4, position: "relative" as const,
                                }
                                const lineV: React.CSSProperties = {
                                    width: 1, height: 20, background: "#444", margin: "0 auto",
                                }

                                const shareholders: any[] = gs.major_shareholders || (gs.parent ? [gs.parent] : [])
                                const linkBtn: React.CSSProperties = {
                                    display: "inline-flex", alignItems: "center", gap: 3,
                                    background: "#1A1A1A", border: "1px solid #333", borderRadius: 4,
                                    padding: "2px 6px", color: "#B5FF19", fontSize: 9, fontWeight: 600,
                                    cursor: "pointer", textDecoration: "none",
                                }

                                return (
                                    <>
                                        {/* 구조도 — 상위 대주주 (최대 5명) */}
                                        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 0, marginBottom: 16 }}>
                                            {shareholders.length > 0 && (
                                                <>
                                                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" as const, justifyContent: "center", marginBottom: 0 }}>
                                                        {shareholders.slice(0, 5).map((sh: any, si: number) => {
                                                            const links = sh.links || {}
                                                            return (
                                                                <div key={si} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 0 }}>
                                                                    <div style={{ ...nodeStyle, minWidth: 110, maxWidth: 160 }}>
                                                                        <div style={{ color: "#fff", fontSize: 12, fontWeight: 700 }}>{sh.name}</div>
                                                                        {sh.ownership_pct > 0 && <div style={{ color: "#B5FF19", fontSize: 10, fontWeight: 700 }}>{sh.ownership_pct}%</div>}
                                                                        {sh.market_cap && <div style={{ color: "#888", fontSize: 9 }}>시총: {sh.market_cap.toLocaleString()}억</div>}
                                                                        {sh.relate && <div style={{ color: "#555", fontSize: 9 }}>{sh.relate}</div>}
                                                                        {(links.official || links.namuwiki || links.profile) && (
                                                                            <div style={{ display: "flex", gap: 3, marginTop: 4, flexWrap: "wrap" as const, justifyContent: "center" }}>
                                                                                {links.official && <a href={links.official} target="_blank" rel="noopener noreferrer" style={linkBtn}>공식</a>}
                                                                                {links.namuwiki && <a href={links.namuwiki} target="_blank" rel="noopener noreferrer" style={linkBtn}>나무위키</a>}
                                                                                {links.profile && <a href={links.profile} target="_blank" rel="noopener noreferrer" style={linkBtn}>회사소개</a>}
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                    <div style={lineV} />
                                                                </div>
                                                            )
                                                        })}
                                                    </div>
                                                    <div style={{ display: "flex", gap: 16, justifyContent: "center", marginBottom: 0 }}>
                                                        {shareholders.slice(0, 5).map((_: any, si: number) => (
                                                            <div key={si} style={{ width: 1, height: 12, background: "#444" }} />
                                                        ))}
                                                    </div>
                                                </>
                                            )}

                                            <div style={activeNodeStyle}>
                                                <div style={{ color: "#B5FF19", fontSize: 14, fontWeight: 800 }}>{stock.name}</div>
                                                {gs.market_cap_억 && <div style={{ color: "#aaa", fontSize: 10 }}>시총: {gs.market_cap_억.toLocaleString()}억</div>}
                                                {gs.group_name && <div style={{ color: "#666", fontSize: 9 }}>{gs.group_name} 그룹</div>}
                                            </div>

                                            {subs.length > 0 && (
                                                <>
                                                    <div style={lineV} />
                                                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" as const, justifyContent: "center", maxWidth: "100%" }}>
                                                        {subs.slice(0, 8).map((sub: any, si: number) => {
                                                            const subLinks = sub.links || {}
                                                            return (
                                                                <div key={si} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 0 }}>
                                                                    <div style={edgeLabel}>{sub.ownership_pct}%</div>
                                                                    <div style={lineV} />
                                                                    <div style={{ ...nodeStyle, minWidth: 100, maxWidth: 140 }}>
                                                                        <div style={{ color: sub.is_listed ? "#fff" : "#999", fontSize: 11, fontWeight: 600 }}>{sub.name}</div>
                                                                        {sub.is_listed && sub.market_cap_억 && <div style={{ color: "#888", fontSize: 9 }}>시총: {sub.market_cap_억.toLocaleString()}억</div>}
                                                                        {sub.stake_value_억 ? <div style={{ color: "#B5FF19", fontSize: 9 }}>지분가치: {sub.stake_value_억.toLocaleString()}억</div> : null}
                                                                        {!sub.is_listed && <div style={{ color: "#555", fontSize: 8 }}>비상장</div>}
                                                                        {(subLinks.official || subLinks.namuwiki || subLinks.profile) && (
                                                                            <div style={{ display: "flex", gap: 3, marginTop: 3, flexWrap: "wrap" as const, justifyContent: "center" }}>
                                                                                {subLinks.official && <a href={subLinks.official} target="_blank" rel="noopener noreferrer" style={linkBtn}>공식</a>}
                                                                                {subLinks.namuwiki && <a href={subLinks.namuwiki} target="_blank" rel="noopener noreferrer" style={linkBtn}>나무위키</a>}
                                                                                {subLinks.profile && <a href={subLinks.profile} target="_blank" rel="noopener noreferrer" style={linkBtn}>회사소개</a>}
                                                                            </div>
                                                                        )}
                                                                    </div>
                                                                </div>
                                                            )
                                                        })}
                                                    </div>
                                                </>
                                            )}
                                        </div>

                                        {/* NAV 분석 카드 */}
                                        {nav.sum_of_parts_억 > 0 && (
                                            <div style={{ background: "#1a1a1a", border: "1px solid #222", borderRadius: 10, padding: 14, marginTop: 8 }}>
                                                <div style={{ color: "#fff", fontSize: 13, fontWeight: 700, marginBottom: 10 }}>NAV 분석 (Sum-of-Parts)</div>
                                                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                                                    <div>
                                                        <div style={{ color: "#666", fontSize: 10 }}>상장 지분가치</div>
                                                        <div style={{ color: "#fff", fontSize: 14, fontWeight: 700 }}>{(nav.listed_stake_value_억 || 0).toLocaleString()}억</div>
                                                    </div>
                                                    <div>
                                                        <div style={{ color: "#666", fontSize: 10 }}>비상장 지분가치</div>
                                                        <div style={{ color: "#fff", fontSize: 14, fontWeight: 700 }}>{(nav.unlisted_stake_value_억 || 0).toLocaleString()}억</div>
                                                    </div>
                                                    <div>
                                                        <div style={{ color: "#666", fontSize: 10 }}>지분합산 NAV</div>
                                                        <div style={{ color: "#B5FF19", fontSize: 14, fontWeight: 700 }}>{nav.sum_of_parts_억.toLocaleString()}억</div>
                                                    </div>
                                                    <div>
                                                        <div style={{ color: "#666", fontSize: 10 }}>NAV 대비</div>
                                                        <div style={{ color: discountColor, fontSize: 14, fontWeight: 700 }}>{discountLabel}</div>
                                                    </div>
                                                </div>
                                            </div>
                                        )}

                                        {/* Sensitivity 테이블 */}
                                        {nav.sensitivity && nav.sensitivity.length > 0 && (
                                            <div style={{ marginTop: 12 }}>
                                                <div style={{ color: "#888", fontSize: 11, fontWeight: 600, marginBottom: 6 }}>자회사 변동 영향도</div>
                                                {nav.sensitivity.map((s: any, si: number) => (
                                                    <div key={si} style={{
                                                        display: "flex", justifyContent: "space-between", alignItems: "center",
                                                        padding: "6px 0", borderBottom: "1px solid #1a1a1a",
                                                    }}>
                                                        <div>
                                                            <span style={{ color: "#fff", fontSize: 12 }}>{s.subsidiary}</span>
                                                            {s.stake_value_억 && <span style={{ color: "#666", fontSize: 10, marginLeft: 6 }}>{s.stake_value_억.toLocaleString()}억</span>}
                                                        </div>
                                                        <div style={{ color: "#B5FF19", fontSize: 12, fontWeight: 600 }}>
                                                            1% → {(s.impact_per_1pct * 100).toFixed(2)}%
                                                        </div>
                                                    </div>
                                                ))}
                                                <div style={{ color: "#555", fontSize: 9, marginTop: 6, lineHeight: 1.4 }}>
                                                    자회사 주가 1% 변동 시 모회사 NAV에 미치는 영향(%)
                                                </div>
                                            </div>
                                        )}

                                        {/* 자회사 상세 리스트 */}
                                        {subs.length > 0 && (
                                            <div style={{ marginTop: 12 }}>
                                                <div style={{ color: "#888", fontSize: 11, fontWeight: 600, marginBottom: 6 }}>타법인 출자 현황 ({subs.length}건)</div>
                                                {subs.map((sub: any, si: number) => (
                                                    <div key={si} style={{
                                                        display: "flex", justifyContent: "space-between", alignItems: "center",
                                                        padding: "8px 0", borderBottom: "1px solid #1a1a1a",
                                                    }}>
                                                        <div style={{ flex: 1 }}>
                                                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                                                <span style={{ color: "#fff", fontSize: 12, fontWeight: 600 }}>{sub.name}</span>
                                                                {sub.is_listed && <span style={{ color: "#B5FF19", fontSize: 8, border: "1px solid #B5FF19", borderRadius: 3, padding: "1px 4px" }}>상장</span>}
                                                            </div>
                                                            <div style={{ color: "#666", fontSize: 10, marginTop: 2 }}>
                                                                지분 {sub.ownership_pct}% · 장부가 {sub.book_value_억}억
                                                                {sub.revenue_억 ? ` · 매출 ${sub.revenue_억}억` : ""}
                                                            </div>
                                                        </div>
                                                        <div style={{ textAlign: "right" as const }}>
                                                            {sub.stake_value_억 ? (
                                                                <div style={{ color: "#B5FF19", fontSize: 13, fontWeight: 700 }}>{sub.stake_value_억.toLocaleString()}억</div>
                                                            ) : (
                                                                <div style={{ color: "#555", fontSize: 11 }}>-</div>
                                                            )}
                                                            {sub.is_listed && sub.price && (
                                                                <div style={{ color: "#888", fontSize: 10 }}>{sub.price.toLocaleString()}원</div>
                                                            )}
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
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

StockDashboard.defaultProps = { dataUrl: DATA_URL, apiBase: API_BASE, market: "kr" }
addPropertyControls(StockDashboard, {
    dataUrl: { type: ControlType.String, title: "Portfolio URL", defaultValue: DATA_URL },
    recUrl:  { type: ControlType.String, title: "Recommendations URL", defaultValue: REC_URL },
    apiBase: { type: ControlType.String, title: "API Base URL", defaultValue: API_BASE },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["국장 (KR)", "미장 (US)"],
        defaultValue: "kr",
    },
})

/* ─── Styles ─── */
const wrap: React.CSSProperties = { width: "100%", background: "#0A0A0A", borderRadius: 20, fontFamily: font, display: "flex", flexDirection: "column", overflow: "hidden" }
const tabBar: React.CSSProperties = { display: "flex", gap: 6, padding: "16px 20px 0" }
const tabBtn: React.CSSProperties = { border: "none", borderRadius: 8, padding: "7px 14px", fontSize: 12, fontWeight: 700, fontFamily: font, cursor: "pointer", transition: "all 0.2s" }
const body: React.CSSProperties = { display: "flex", gap: 0, minHeight: 560 }
const listPanel: React.CSSProperties = {
    width: 280,
    minWidth: 280,
    borderRight: "1px solid #1A1A1A",
    padding: "24px 0",
    maxHeight: 720,
    alignSelf: "flex-start",
    overflowY: "auto",
    overscrollBehavior: "contain",
    WebkitOverflowScrolling: "touch",
    scrollbarWidth: "thin",
    WebkitMaskImage:
        "linear-gradient(to bottom, transparent 0, #000 28px, #000 calc(100% - 28px), transparent 100%)",
    maskImage:
        "linear-gradient(to bottom, transparent 0, #000 28px, #000 calc(100% - 28px), transparent 100%)",
}
const listItem: React.CSSProperties = { display: "flex", alignItems: "center", padding: "11px 16px 11px 12px", transition: "all 0.15s" }
const listRecDot: React.CSSProperties = { width: 8, height: 8, borderRadius: 4, flexShrink: 0 }
const listName: React.CSSProperties = { color: "#fff", fontSize: 13, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", minWidth: 0 }
const listTicker: React.CSSProperties = { color: "#555", fontSize: 10, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }
const listRight: React.CSSProperties = { display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2, flexShrink: 0, minWidth: 76 }
const listPrice: React.CSSProperties = { color: "#ccc", fontSize: 12, fontWeight: 600, whiteSpace: "nowrap" }
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
const detailBusiness: React.CSSProperties = {
    color: "#7A7A7A",
    fontSize: 11,
    fontWeight: 500,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    maxWidth: 260,
}
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

