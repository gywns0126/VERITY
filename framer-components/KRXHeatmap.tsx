import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState, useCallback, useRef } from "react"

// ── 인라인 fetch 유틸 ────────────────────────────────────────────────────────
function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    return `${u}${u.includes("?") ? "&" : "?"}_=${Date.now()}`
}
function fetchJson(url: string): Promise<any> {
    return fetch(bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit" })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((txt) => JSON.parse(txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
}

// ── 헬퍼 ────────────────────────────────────────────────────────────────────
function isKRX(market: string): boolean {
    return /KOSPI|KOSDAQ|KRX|코스피|코스닥/i.test(market || "")
}
function isUS(market: string): boolean {
    return /NYSE|NASDAQ|AMEX|NMS|NGM|NCM/i.test(market || "")
}

function calcPct(sparkline: number[] | undefined): number | null {
    if (!sparkline || sparkline.length < 2) return null
    const last = sparkline[sparkline.length - 1]
    const prev = sparkline[sparkline.length - 2]
    if (!prev) return null
    return ((last - prev) / prev) * 100
}

function boxBg(pct: number | null): string {
    const v = pct ?? 0
    if (v >= 3)  return "#14532d"
    if (v >= 1)  return "#15803d"
    if (v >= 0)  return "#166534"
    if (v >= -1) return "#7f1d1d"
    if (v >= -3) return "#991b1b"
    return "#b91c1c"
}

function pctColor(pct: number | null): string {
    const v = pct ?? 0
    if (v > 0) return "#bbf7d0"
    if (v < 0) return "#fecaca"
    return "#d1d5db"
}

function naverStockUrl(ticker: string): string {
    return `https://finance.naver.com/item/main.naver?code=${ticker}`
}
function naverHeadlineUrl(headline: string): string {
    return `https://search.naver.com/search.naver?where=news&query=${encodeURIComponent(headline)}&sort=1`
}
function yahooStockUrl(ticker: string): string {
    return `https://finance.yahoo.com/quote/${ticker}/news`
}
function yahooHeadlineUrl(headline: string): string {
    return `https://finance.yahoo.com/search/?q=${encodeURIComponent(headline)}`
}

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"

// ── 시장별 설정 ──────────────────────────────────────────────────────────────
const MARKET_CONFIG = {
    kr: {
        filter: (m: string) => isKRX(m),
        badge: "국장",
        badgeColor: "#B5FF19",
        badgeBg: "rgba(181,255,25,0.12)",
        title: "KOSPI · KOSDAQ 히트맵",
        minCap: 1e11,
        stockUrl: naverStockUrl,
        headlineUrl: naverHeadlineUrl,
        linkLabel: "네이버 금융에서 보기 →",
        linkColor: "#03C75A",
        linkHover: "#05E066",
        priceFormatter: (p: number) => `${p?.toLocaleString()}원`,
        loadingText: "국장 히트맵 로딩 중...",
    },
    us: {
        filter: (m: string) => isUS(m),
        badge: "미장",
        badgeColor: "#60a5fa",
        badgeBg: "rgba(96,165,250,0.12)",
        title: "NYSE · NASDAQ 히트맵",
        minCap: 1e9,
        stockUrl: yahooStockUrl,
        headlineUrl: yahooHeadlineUrl,
        linkLabel: "Yahoo Finance에서 보기 →",
        linkColor: "#6c6cf7",
        linkHover: "#8e8ef9",
        priceFormatter: (p: number) =>
            p != null
                ? `$${Number(p).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                : "—",
        loadingText: "미장 히트맵 로딩 중...",
    },
}

// ── 컴포넌트 ─────────────────────────────────────────────────────────────────
interface Props {
    dataUrl: string
    market: "kr" | "us"
}

export default function KRXHeatmap({ dataUrl, market }: Props) {
    const [data, setData]       = useState<any>(null)
    const [hovered, setHovered] = useState<any>(null)
    const [tipPos, setTipPos]   = useState({ x: 0, y: 0 })
    const hideTimer             = useRef<ReturnType<typeof setTimeout> | null>(null)

    const cfg = MARKET_CONFIG[market] || MARKET_CONFIG.kr

    useEffect(() => {
        if (!dataUrl) return
        fetchJson(dataUrl).then(setData).catch(() => {})
    }, [dataUrl])

    const clearHide = useCallback(() => {
        if (hideTimer.current) clearTimeout(hideTimer.current)
    }, [])

    const startHide = useCallback(() => {
        clearHide()
        hideTimer.current = setTimeout(() => setHovered(null), 280)
    }, [clearHide])

    const showTooltip = useCallback((stock: any, x: number, y: number) => {
        clearHide()
        setHovered(stock)
        setTipPos({ x, y })
    }, [clearHide])

    const handleMouseMove = useCallback((e: React.MouseEvent) => {
        setTipPos({ x: e.clientX, y: e.clientY })
    }, [])

    const recs: any[] = data?.recommendations || []
    const stocks = recs.filter((s) => cfg.filter(s.market || ""))
    const totalCap = stocks.reduce((acc, s) => acc + Math.max(s.market_cap || 0, cfg.minCap), 0)

    if (!data) {
        return (
            <div style={{ ...card, alignItems: "center", justifyContent: "center", minHeight: 200 }}>
                <span style={{ color: "#555", fontSize: 13, fontFamily: font }}>{cfg.loadingText}</span>
            </div>
        )
    }

    const upCount   = stocks.filter((s) => (calcPct(s.sparkline) ?? 0) > 0).length
    const downCount = stocks.filter((s) => (calcPct(s.sparkline) ?? 0) < 0).length

    return (
        <div style={card}>
            {/* ── 헤더 ── */}
            <div style={headerStyle}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ color: cfg.badgeColor, fontSize: 11, fontWeight: 800, fontFamily: font,
                        background: cfg.badgeBg, padding: "2px 7px", borderRadius: 4 }}>
                        {cfg.badge}
                    </span>
                    <span style={{ color: "#fff", fontSize: 15, fontWeight: 700, fontFamily: font }}>
                        {cfg.title}
                    </span>
                    <span style={{ color: "#888", fontSize: 11, fontFamily: font }}>
                        {stocks.length}개 종목
                    </span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <span style={{ color: "#86efac", fontSize: 12, fontWeight: 600, fontFamily: font }}>▲ {upCount}</span>
                    <span style={{ color: "#fca5a5", fontSize: 12, fontWeight: 600, fontFamily: font }}>▼ {downCount}</span>
                </div>
            </div>

            {/* ── 히트맵 그리드 ── */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 3, padding: "10px 10px 6px" }}>
                {stocks.map((s) => {
                    const pct    = calcPct(s.sparkline)
                    const weight = Math.max((s.market_cap || cfg.minCap) / totalCap * 100, 3)
                    const isHov  = hovered?.ticker === s.ticker

                    return (
                        <div
                            key={s.ticker}
                            onMouseEnter={(e) => showTooltip(s, e.clientX, e.clientY)}
                            onMouseMove={handleMouseMove}
                            onMouseLeave={startHide}
                            style={{
                                flexBasis: `calc(${weight}% - 3px)`,
                                flexGrow: weight,
                                minWidth: 54,
                                height: 78,
                                background: boxBg(pct),
                                borderRadius: 5,
                                display: "flex",
                                flexDirection: "column",
                                alignItems: "center",
                                justifyContent: "center",
                                gap: 2,
                                cursor: "pointer",
                                border: isHov ? "1.5px solid rgba(255,255,255,0.6)" : "1.5px solid transparent",
                                transition: "border 0.1s, opacity 0.1s",
                                opacity: hovered && !isHov ? 0.65 : 1,
                                overflow: "hidden",
                                padding: "4px 3px",
                            }}
                        >
                            <span style={{
                                color: "#fff",
                                fontSize: Math.min(12, 7 + weight * 0.4),
                                fontWeight: 700,
                                fontFamily: font,
                                lineHeight: 1.2,
                                maxWidth: "95%",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                                textAlign: "center",
                            }}>
                                {s.name}
                            </span>
                            <span style={{
                                color: "rgba(255,255,255,0.5)",
                                fontSize: Math.min(9, 6 + weight * 0.2),
                                fontFamily: font,
                                lineHeight: 1,
                            }}>
                                {s.ticker}
                            </span>
                            {pct != null && (
                                <span style={{
                                    color: pctColor(pct),
                                    fontSize: Math.min(11, 7 + weight * 0.3),
                                    fontWeight: 600,
                                    fontFamily: font,
                                    marginTop: 1,
                                }}>
                                    {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
                                </span>
                            )}
                        </div>
                    )
                })}
            </div>

            {/* ── 범례 ── */}
            <div style={legendRow}>
                {[
                    { label: "+3% 이상", bg: "#14532d" },
                    { label: "+1~3%",   bg: "#15803d" },
                    { label: "0~+1%",   bg: "#166534" },
                    { label: "0~-1%",   bg: "#7f1d1d" },
                    { label: "-1~-3%",  bg: "#991b1b" },
                    { label: "-3% 이하", bg: "#b91c1c" },
                ].map((l) => (
                    <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <div style={{ width: 10, height: 10, borderRadius: 2, background: l.bg }} />
                        <span style={{ color: "#666", fontSize: 10, fontFamily: font }}>{l.label}</span>
                    </div>
                ))}
                <span style={{ color: "#444", fontSize: 10, fontFamily: font, marginLeft: "auto" }}>
                    sparkline 전일 대비
                </span>
            </div>

            {/* ── 호버 툴팁 ── */}
            {hovered && (
                <HeatmapTooltip
                    stock={hovered}
                    pos={tipPos}
                    cfg={cfg}
                    onMouseEnter={clearHide}
                    onMouseLeave={startHide}
                />
            )}
        </div>
    )
}

// ── 통합 툴팁 ────────────────────────────────────────────────────────────────
function HeatmapTooltip({
    stock,
    pos,
    cfg,
    onMouseEnter,
    onMouseLeave,
}: {
    stock: any
    pos: { x: number; y: number }
    cfg: typeof MARKET_CONFIG["kr"]
    onMouseEnter: () => void
    onMouseLeave: () => void
}) {
    const pct      = calcPct(stock.sparkline)
    const rec      = stock.recommendation || "WATCH"
    const recColor = rec === "BUY" ? "#B5FF19" : rec === "AVOID" ? "#FF4D4D" : "#888"
    const ms       = stock.multi_factor?.multi_score || stock.safety_score || 0

    const newsItems: Array<{ title: string; url: string }> =
        stock.sentiment?.top_headline_links?.length > 0
            ? stock.sentiment.top_headline_links
            : (stock.sentiment?.top_headlines || []).map((h: string) => ({
                title: h,
                url: cfg.headlineUrl(h),
            }))

    const tipW = 290
    const winW = typeof window !== "undefined" ? window.innerWidth : 1400
    const winH = typeof window !== "undefined" ? window.innerHeight : 900
    const left = pos.x + tipW + 20 > winW ? pos.x - tipW - 12 : pos.x + 14
    const top  = Math.min(pos.y - 10, winH - 340)

    return (
        <div
            onMouseEnter={onMouseEnter}
            onMouseLeave={onMouseLeave}
            style={{
                position: "fixed",
                left,
                top,
                width: tipW,
                background: "#181818",
                border: "1px solid #333",
                borderRadius: 10,
                padding: "12px 14px",
                zIndex: 9999,
                boxShadow: "0 8px 32px rgba(0,0,0,0.65)",
                cursor: "default",
            }}
        >
            <div style={{ display: "flex", alignItems: "flex-start", gap: 6, marginBottom: 6 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ color: "#fff", fontSize: 14, fontWeight: 800, fontFamily: font, lineHeight: 1.2 }}>
                        {stock.name}
                    </div>
                    <div style={{ color: "#666", fontSize: 11, fontFamily: font, marginTop: 2 }}>
                        {stock.ticker} · {stock.market}
                    </div>
                </div>
                <span style={{
                    background: recColor,
                    color: recColor === "#888" ? "#fff" : "#000",
                    fontSize: 9, fontWeight: 800,
                    padding: "2px 6px", borderRadius: 4,
                    fontFamily: font, flexShrink: 0, marginTop: 2,
                }}>
                    {rec}
                </span>
            </div>

            <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 8 }}>
                <span style={{ color: "#fff", fontSize: 13, fontWeight: 700, fontFamily: font }}>
                    {cfg.priceFormatter(stock.price)}
                </span>
                {pct != null && (
                    <span style={{ color: pctColor(pct), fontSize: 12, fontWeight: 600, fontFamily: font }}>
                        {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
                    </span>
                )}
                <span style={{ color: "#555", fontSize: 10, fontFamily: font, marginLeft: "auto" }}>
                    VERITY {ms}점
                </span>
            </div>

            <div style={{ borderTop: "1px solid #252525", marginBottom: 8 }} />

            {newsItems.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                    <span style={{ color: "#555", fontSize: 10, fontWeight: 600, fontFamily: font, marginBottom: 1 }}>
                        최신 뉴스
                    </span>
                    {newsItems.slice(0, 3).map((item, i) => (
                        <a
                            key={i}
                            href={item.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ display: "flex", gap: 6, alignItems: "flex-start", textDecoration: "none" }}
                        >
                            <span style={{ color: "#444", fontSize: 10, fontFamily: font, flexShrink: 0, marginTop: 2 }}>•</span>
                            <span
                                style={{ color: "#bbb", fontSize: 11, fontFamily: font, lineHeight: "1.45", transition: "color 0.1s" }}
                                onMouseEnter={(e) => (e.currentTarget.style.color = "#fff")}
                                onMouseLeave={(e) => (e.currentTarget.style.color = "#bbb")}
                            >
                                {item.title}
                            </span>
                        </a>
                    ))}
                </div>
            ) : (
                <span style={{ color: "#555", fontSize: 11, fontFamily: font }}>뉴스 없음</span>
            )}

            {stock.gold_insight && (
                <>
                    <div style={{ borderTop: "1px solid #252525", margin: "8px 0" }} />
                    <div style={{ display: "flex", gap: 6, alignItems: "flex-start" }}>
                        <span style={{ background: "#FFD600", color: "#000", fontSize: 8, fontWeight: 800,
                            padding: "1px 4px", borderRadius: 3, flexShrink: 0, marginTop: 2, fontFamily: font }}>G</span>
                        <span style={{ color: "#bbb", fontSize: 11, fontFamily: font, lineHeight: "1.45" }}>
                            {stock.gold_insight}
                        </span>
                    </div>
                </>
            )}

            <div style={{ borderTop: "1px solid #252525", marginTop: 8, paddingTop: 8 }}>
                <a
                    href={cfg.stockUrl(stock.ticker)}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ textDecoration: "none" }}
                >
                    <span
                        style={{ color: cfg.linkColor, fontSize: 11, fontWeight: 600, fontFamily: font }}
                        onMouseEnter={(e) => (e.currentTarget.style.color = cfg.linkHover)}
                        onMouseLeave={(e) => (e.currentTarget.style.color = cfg.linkColor)}
                    >
                        {cfg.linkLabel}
                    </span>
                </a>
            </div>
        </div>
    )
}

// ── 스타일 ───────────────────────────────────────────────────────────────────
const card: React.CSSProperties = {
    width: "100%",
    background: "#111",
    borderRadius: 16,
    border: "1px solid #222",
    overflow: "visible",
    display: "flex",
    flexDirection: "column",
    position: "relative",
    fontFamily: font,
}

const headerStyle: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "12px 14px",
    borderBottom: "1px solid #1e1e1e",
}

const legendRow: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 10,
    padding: "8px 14px 12px",
    borderTop: "1px solid #1a1a1a",
}

// ── Framer 설정 ──────────────────────────────────────────────────────────────
KRXHeatmap.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    market: "kr",
}

addPropertyControls(KRXHeatmap, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["국장 (KR)", "미장 (US)"],
        defaultValue: "kr",
    },
})
