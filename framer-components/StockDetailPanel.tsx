import { addPropertyControls, ControlType } from "framer"
import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react"
import type { CSSProperties } from "react"

/** Framer 단일 파일용 fetch (fetchPortfolioJson.ts와 동일 로직) */
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
                txt
                    .replace(/\bNaN\b/g, "null")
                    .replace(/\bInfinity\b/g, "null")
                    .replace(/-null/g, "null"),
            ),
        )
}

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"
const UP = "#F04452"
const DOWN = "#3182F6"
const BG = "#000"
const CARD = "#111"
const BORDER = "#222"
const MUTED = "#8B95A1"
const ACCENT = "#B5FF19"

interface OrderRow {
    price: number
    ask_vol: number | null
    bid_vol: number | null
    pct_label: string
    highlight?: boolean
}

interface StockDetailModel {
    symbol: string
    name: string
    price: number
    change_amount: number
    change_pct: number
    compare_label: string
    chart: {
        timeframes: string[]
        active_timeframe: string
        line: number[]
        annotations?: { high?: { price: number; label: string }; low?: { price: number; label: string } }
        candles?: { o: number; h: number; l: number; c: number; up: boolean }[]
    }
    ranges: { id: string; label: string; low: number; high: number }[]
    session: { open: number; close: number; volume: number; trading_value_label: string }
    investors: { label: string; net_display: string; side: "buy" | "sell" }[]
    order_book: {
        current_price: number
        rows: OrderRow[]
        footer: {
            sell_wait_label: string
            buy_wait_label: string
            sell_wait: string
            buy_wait: string
            session_note: string
        }
    }
    execution: { strength_pct: number; trades: { price: number; qty: number; side: "buy" | "sell" }[] }
    limits: { upper: string; lower: string; vi: string }
    insights: { tag: string; text: string; ago: string }[]
}

const MOCK_DETAIL: StockDetailModel = {
    symbol: "000660",
    name: "SK하이닉스",
    price: 1043000,
    change_amount: 127000,
    change_pct: 13.8,
    compare_label: "전일대비",
    chart: {
        timeframes: ["1일", "1주", "3달", "1년", "5년", "전체"],
        active_timeframe: "1주",
        line: [920000, 935000, 910000, 948000, 990000, 1010000, 1025000, 998000, 1030000, 1043000],
        annotations: {
            high: { price: 1100000, label: "최고 1,100,000원" },
            low: { price: 818000, label: "최저 818,000원" },
        },
        candles: [
            { o: 1000000, h: 1020000, l: 995000, c: 1015000, up: true },
            { o: 1015000, h: 1040000, l: 1010000, c: 1038000, up: true },
            { o: 1038000, h: 1050000, l: 1025000, c: 1043000, up: true },
        ],
    },
    ranges: [
        { id: "1d", label: "1일", low: 948000, high: 1100000 },
        { id: "1y", label: "1년", low: 162700, high: 1117000 },
    ],
    session: { open: 1000000, close: 1043000, volume: 11906741, trading_value_label: "약 12조원" },
    investors: [
        { label: "개인", net_display: "-228만", side: "sell" },
        { label: "외국인", net_display: "+132만", side: "buy" },
        { label: "기관", net_display: "+108만", side: "buy" },
    ],
    order_book: {
        current_price: 1043000,
        rows: [
            { price: 1046000, ask_vol: 8420, bid_vol: null, pct_label: "+0.3%" },
            { price: 1045000, ask_vol: 12030, bid_vol: null, pct_label: "+0.2%" },
            { price: 1044000, ask_vol: 5600, bid_vol: null, pct_label: "+0.1%" },
            { price: 1043000, ask_vol: null, bid_vol: null, pct_label: "0.0%", highlight: true },
            { price: 1042000, ask_vol: null, bid_vol: 9100, pct_label: "-0.1%" },
            { price: 1041000, ask_vol: null, bid_vol: 15300, pct_label: "-0.2%" },
            { price: 1040000, ask_vol: null, bid_vol: 7200, pct_label: "-0.3%" },
        ],
        footer: {
            sell_wait_label: "판매 대기",
            buy_wait_label: "구매 대기",
            sell_wait: "약 1.2M주",
            buy_wait: "약 980K주",
            session_note: "애프터마켓",
        },
    },
    execution: {
        strength_pct: 146,
        trades: [
            { price: 1043000, qty: 120, side: "buy" },
            { price: 1042950, qty: 45, side: "sell" },
            { price: 1043000, qty: 200, side: "buy" },
            { price: 1042900, qty: 80, side: "sell" },
        ],
    },
    limits: { upper: "1,355,000", lower: "731,000", vi: "—" },
    insights: [
        { tag: "호재", text: "연간 주가 +463% 구간에서도 외국인·기관 순매수 지속", ago: "7시간 전" },
        { tag: "소식", text: "외국인 순매수 상위 10종목에 반도체 대형주 다수 포함", ago: "1일 전" },
        { tag: "호재", text: "HBM 수요 전망 상향 — 장비·소재 동반 강세", ago: "2일 전" },
    ],
}

function formatKRW(n: number): string {
    if (!Number.isFinite(n)) return "—"
    return `${Math.round(n).toLocaleString("ko-KR")}원`
}

function formatTradingValueKRW(n: number): string {
    if (!Number.isFinite(n)) return "—"
    const jo = n / 1e12
    if (jo >= 1) return `약 ${jo.toFixed(1)}조원`
    const eok = n / 1e8
    if (eok >= 1) return `약 ${eok.toFixed(0)}억원`
    const man = n / 1e4
    return `약 ${Math.round(man).toLocaleString("ko-KR")}만원`
}

function formatVolumeShares(n: number): string {
    if (!Number.isFinite(n)) return "—"
    return `${Math.round(n).toLocaleString("ko-KR")}주`
}

function normalizeIndex(v: unknown, max: number): number {
    const n = typeof v === "number" ? v : Number(v)
    if (!Number.isFinite(n) || n < 0) return 0
    return Math.min(Math.floor(n), Math.max(0, max))
}

/** 검색어·종목코드·이름으로 recommendations에서 한 건 찾기 (부분 폴백용) */
function findRecBySymbol(recs: any[], raw: string): any | null {
    const q = String(raw || "").trim()
    if (!q || !recs?.length) return null
    const qn = q.replace(/\s/g, "")
    const lower = qn.toLowerCase()
    for (const r of recs) {
        const t = String(r?.ticker ?? "").trim()
        const tyf = String(r?.ticker_yf ?? "").trim()
        const name = String(r?.name ?? "").trim()
        if (t === qn || name === q) return r
        if (tyf === qn) return r
        const base = tyf.split(".")[0]?.toLowerCase() ?? ""
        if (base && (base === lower || tyf.toLowerCase().startsWith(lower + "."))) return r
    }
    return null
}

function buildAnalysisUrl(template: string, symbol: string): string | null {
    const t = template.trim()
    if (!t) return null
    if (!/\{symbol\}|\{ticker\}|\{q\}/i.test(t)) return null
    const enc = encodeURIComponent(symbol.trim())
    return t.replace(/\{symbol\}/gi, enc).replace(/\{ticker\}/gi, enc).replace(/\{q\}/gi, enc)
}

function mergeFromRecommendation(base: StockDetailModel, rec: any): StockDetailModel {
    if (!rec || typeof rec !== "object") return base
    const tech = rec.technical || {}
    const pct = typeof tech.price_change_pct === "number" ? tech.price_change_pct : base.change_pct
    const price = typeof rec.price === "number" ? rec.price : base.price
    const prevClose = price / (1 + pct / 100)
    const changeAmt = price - prevClose
    const spark = Array.isArray(rec.sparkline) && rec.sparkline.length > 1 ? rec.sparkline.map((x: any) => Number(x)) : base.chart.line

    const flow = rec.flow || {}
    const investors = base.investors.map((row) => ({ ...row }))
    const fmtFlow = (v: number) => {
        const a = Math.abs(v)
        if (a >= 10000) return `${v >= 0 ? "+" : "-"}${Math.round(a / 10000)}만`
        return `${v >= 0 ? "+" : ""}${Math.round(v).toLocaleString("ko-KR")}`
    }
    if (typeof flow.foreign_net === "number" && flow.foreign_net !== 0) {
        const i = investors.findIndex((x) => x.label === "외국인")
        if (i >= 0) {
            investors[i] = {
                label: "외국인",
                net_display: fmtFlow(flow.foreign_net),
                side: flow.foreign_net >= 0 ? "buy" : "sell",
            }
        }
    }
    if (typeof flow.institution_net === "number" && flow.institution_net !== 0) {
        const i = investors.findIndex((x) => x.label === "기관")
        if (i >= 0) {
            investors[i] = {
                label: "기관",
                net_display: fmtFlow(flow.institution_net),
                side: flow.institution_net >= 0 ? "buy" : "sell",
            }
        }
    }

    const headlines: string[] = rec.sentiment?.top_headlines || []
    const insights =
        headlines.length > 0
            ? headlines.slice(0, 5).map((text: string, idx: number) => ({
                  tag: idx === 0 ? "호재" : "소식",
                  text,
                  ago: "portfolio.json",
              }))
            : base.insights

    const high52 = typeof rec.high_52w === "number" ? rec.high_52w : null
    const ranges = base.ranges.map((r) => {
        if (r.id === "1y" && high52 != null && Number.isFinite(high52)) {
            return { ...r, high: Math.max(r.high, high52) }
        }
        return { ...r }
    })

    return {
        ...base,
        name: rec.name || base.name,
        symbol: String(rec.ticker || base.symbol),
        price,
        change_amount: changeAmt,
        change_pct: pct,
        chart: { ...base.chart, line: spark },
        session: {
            ...base.session,
            close: price,
            volume: typeof rec.volume === "number" ? rec.volume : base.session.volume,
            trading_value_label:
                typeof rec.trading_value === "number" ? formatTradingValueKRW(rec.trading_value) : base.session.trading_value_label,
        },
        investors,
        insights,
        ranges,
        order_book: { ...base.order_book, current_price: price },
    }
}

function RangeGauge({ low, high, current, label }: { low: number; high: number; current: number; label: string }) {
    const span = high - low || 1
    const t = Math.min(1, Math.max(0, (current - low) / span))
    return (
        <div style={{ marginBottom: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <span style={{ color: MUTED, fontSize: 11, fontWeight: 600 }}>{label}</span>
            </div>
            <div style={{ position: "relative", height: 8, background: "#1A1A1A", borderRadius: 99 }}>
                <div
                    style={{
                        position: "absolute",
                        left: `${t * 100}%`,
                        top: "50%",
                        transform: "translate(-50%, -50%)",
                        width: 14,
                        height: 14,
                        borderRadius: "50%",
                        background: "#fff",
                        border: `2px solid ${UP}`,
                        boxSizing: "border-box",
                    }}
                />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
                <span style={{ color: MUTED, fontSize: 11 }}>{formatKRW(low)}</span>
                <span style={{ color: MUTED, fontSize: 11 }}>{formatKRW(high)}</span>
            </div>
        </div>
    )
}

function LineChart({ data, color, width, height }: { data: number[]; color: string; width: number; height: number }) {
    const w = Math.max(80, width)
    const h = Math.max(60, height)
    if (!data || data.length < 2)
        return (
            <div style={{ width: "100%", height: h, minHeight: 60, color: MUTED, fontSize: 12, display: "flex", alignItems: "center" }}>
                차트 데이터 없음
            </div>
        )
    const min = Math.min(...data)
    const max = Math.max(...data)
    const range = max - min || 1
    const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - 8 - ((v - min) / range) * (h - 16)}`).join(" ")
    return (
        <svg width="100%" height="100%" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: "block" }}>
            <polyline points={pts} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
        </svg>
    )
}

function CandlePreview({
    candles,
    upColor,
    downColor,
    width,
    height,
}: {
    candles: { o: number; h: number; l: number; c: number; up: boolean }[]
    upColor: string
    downColor: string
    width: number
    height: number
}) {
    const w = Math.max(80, width)
    const h = Math.max(60, height)
    if (!candles?.length) return null
    const lows = candles.map((c) => c.l)
    const highs = candles.map((c) => c.h)
    const min = Math.min(...lows)
    const max = Math.max(...highs)
    const range = max - min || 1
    const barW = w / candles.length - 6
    return (
        <svg width="100%" height="100%" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: "block" }}>
            {candles.map((c, i) => {
                const x = (i / candles.length) * w + 3
                const y1 = h - 8 - ((c.h - min) / range) * (h - 16)
                const y2 = h - 8 - ((c.l - min) / range) * (h - 16)
                const yO = h - 8 - ((c.o - min) / range) * (h - 16)
                const yC = h - 8 - ((c.c - min) / range) * (h - 16)
                const col = c.up ? upColor : downColor
                const top = Math.min(yO, yC)
                const bh = Math.max(2, Math.abs(yC - yO))
                return (
                    <g key={i}>
                        <line x1={x + barW / 2} y1={y1} x2={x + barW / 2} y2={y2} stroke={col} strokeWidth={1} vectorEffect="non-scaling-stroke" />
                        <rect x={x} y={top} width={barW} height={bh} fill={col} rx={1} />
                    </g>
                )
            })}
        </svg>
    )
}

type TabId = "chart" | "hoga" | "info" | "summary"

interface Props {
    /** 비우면 내장 목업 사용. 고정 단일 JSON (검색 미사용 시) */
    detailJsonUrl: string
    portfolioUrl: string
    stockIndex: number
    mergeFromPortfolio: boolean
    /** 사이트에서 종목 선택(셀렉트·이전·다음). 상세 JSON·검색 모드일 때 숨김 */
    showStockPicker: boolean
    /**
     * 검색창·다른 컴포넌트와 연동: 종목코드 또는 검색 확정 문자열.
     * 값이 있으면 포트폴리오 인덱스보다 우선합니다.
     */
    searchSymbol: string
    /**
     * 분석 결과 JSON URL 템플릿. `{symbol}` 또는 `{ticker}` 또는 `{q}` 자리에 검색어 삽입(인코딩).
     * 예: `https://example.com/api/stock/{symbol}.json`
     */
    analysisUrlTemplate: string
    /** 템플릿 미설정·요청 실패 시 recommendations에서만 매칭해 목업+병합 표시 */
    allowPortfolioFallbackForSearch: boolean
    /** 패널 내 검색 입력(엔터 시 조회). Framer에서 검색 컴포넌트만 쓸 경우 끄기 */
    showInlineSearch: boolean
    showBuyButton: boolean
}

export default function StockDetailPanel(props: Props) {
    const {
        detailJsonUrl,
        portfolioUrl,
        stockIndex,
        mergeFromPortfolio,
        showStockPicker,
        searchSymbol,
        analysisUrlTemplate,
        allowPortfolioFallbackForSearch,
        showInlineSearch,
        showBuyButton,
    } = props

    const [detailFromFile, setDetailFromFile] = useState<StockDetailModel | null>(null)
    const [detailFromSearch, setDetailFromSearch] = useState<StockDetailModel | null>(null)
    const [searchLoading, setSearchLoading] = useState(false)
    const [searchError, setSearchError] = useState<string | null>(null)
    const [searchBanner, setSearchBanner] = useState<string | null>(null)

    const [portfolio, setPortfolio] = useState<any>(null)
    const [activeStockIndex, setActiveStockIndex] = useState(() => normalizeIndex(stockIndex, 9999))
    const [inlineDraft, setInlineDraft] = useState("")
    const [inlineCommitted, setInlineCommitted] = useState("")

    const [tab, setTab] = useState<TabId>("chart")
    const [chartMode, setChartMode] = useState<"line" | "candle">("line")
    const [tfPick, setTfPick] = useState<string | null>(null)

    const chartBoxRef = useRef<HTMLDivElement | null>(null)
    const [chartBox, setChartBox] = useState({ w: 400, h: 220 })

    const propSymbol = (searchSymbol || "").trim()
    const effectiveSymbol = propSymbol || (inlineCommitted || "").trim()

    const needPortfolio = mergeFromPortfolio || allowPortfolioFallbackForSearch || showStockPicker

    const loadPortfolio = useCallback(() => {
        const u = (portfolioUrl || "").trim()
        if (!u || !needPortfolio) return
        fetchPortfolioJson(u).then(setPortfolio).catch(console.error)
    }, [portfolioUrl, needPortfolio])

    useEffect(() => {
        loadPortfolio()
    }, [loadPortfolio])

    useEffect(() => {
        if (effectiveSymbol) return
        const u = (detailJsonUrl || "").trim()
        if (!u) {
            setDetailFromFile(null)
            return
        }
        fetchPortfolioJson(u)
            .then((j) => setDetailFromFile(j as StockDetailModel))
            .catch(() => setDetailFromFile(null))
    }, [detailJsonUrl, effectiveSymbol])

    useEffect(() => {
        setActiveStockIndex(normalizeIndex(stockIndex, 9999))
    }, [stockIndex])

    const recs = portfolio?.recommendations || []
    const maxIdx = Math.max(0, recs.length - 1)

    useEffect(() => {
        setActiveStockIndex((i) => Math.min(Math.max(0, i), maxIdx))
    }, [maxIdx])

    const idx = normalizeIndex(activeStockIndex, maxIdx)
    const rec = recs.length ? recs[idx] : null

    useEffect(() => {
        const sym = effectiveSymbol
        if (!sym) {
            setDetailFromSearch(null)
            setSearchLoading(false)
            setSearchError(null)
            setSearchBanner(null)
            return
        }

        let cancelled = false
        setDetailFromSearch(null)
        setSearchLoading(true)
        setSearchError(null)
        setSearchBanner(null)

        const tryFallback = (): boolean => {
            const list = portfolio?.recommendations || []
            const hit = findRecBySymbol(list, sym)
            if (allowPortfolioFallbackForSearch && hit) {
                if (!cancelled) {
                    setDetailFromSearch(mergeFromRecommendation(MOCK_DETAIL, hit))
                    setSearchBanner(
                        "전용 분석 API가 없거나 요청에 실패했습니다. 추천 목록과 일치하는 종목만 요약·차트를 채웁니다.",
                    )
                    setSearchLoading(false)
                    setSearchError(null)
                }
                return true
            }
            return false
        }

        const url = buildAnalysisUrl(analysisUrlTemplate, sym)
        if (url) {
            fetchPortfolioJson(url)
                .then((j) => {
                    if (cancelled) return
                    setDetailFromSearch(j as StockDetailModel)
                    setSearchLoading(false)
                    setSearchError(null)
                    setSearchBanner(null)
                })
                .catch(() => {
                    if (cancelled) return
                    if (!tryFallback()) {
                        setDetailFromSearch(null)
                        setSearchError("분석 데이터를 불러오지 못했습니다. 종목코드·URL·CORS를 확인해 주세요.")
                        setSearchLoading(false)
                    }
                })
        } else {
            if (!tryFallback()) {
                setDetailFromSearch(null)
                setSearchError(
                    (analysisUrlTemplate || "").trim()
                        ? "analysisUrlTemplate에 {symbol}, {ticker}, {q} 중 하나를 넣어 주세요."
                        : "임의 종목 조회에는 analysisUrlTemplate(예: …/stock/{symbol}.json)을 설정하거나, 추천 일치 폴백을 켜 주세요.",
                )
                setSearchLoading(false)
            }
        }

        return () => {
            cancelled = true
        }
    }, [effectiveSymbol, analysisUrlTemplate, allowPortfolioFallbackForSearch, portfolio])

    const detail = useMemo(() => {
        if (effectiveSymbol) {
            if (detailFromSearch) return detailFromSearch
            return MOCK_DETAIL
        }
        const base = detailFromFile || MOCK_DETAIL
        if (!mergeFromPortfolio || !rec) return base
        if (detailFromFile) return base
        return mergeFromRecommendation(base, rec)
    }, [effectiveSymbol, detailFromSearch, detailFromFile, mergeFromPortfolio, rec])

    useLayoutEffect(() => {
        if (tab !== "chart") return
        const el = chartBoxRef.current
        if (!el) return
        const measure = () => {
            const r = el.getBoundingClientRect()
            setChartBox({
                w: Math.max(64, Math.floor(r.width)),
                h: Math.max(64, Math.floor(r.height)),
            })
        }
        measure()
        if (typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver(() => measure())
        ro.observe(el)
        return () => ro.disconnect()
    }, [tab, chartMode, detail.chart?.line?.length])

    const up = detail.change_pct >= 0
    const dirColor = up ? UP : DOWN
    const activeTf = tfPick || detail.chart.active_timeframe

    const tabs: { id: TabId; label: string }[] = [
        { id: "chart", label: "차트" },
        { id: "hoga", label: "호가" },
        { id: "info", label: "종목정보" },
        { id: "summary", label: "요약" },
    ]

    const pickerVisible =
        showStockPicker &&
        mergeFromPortfolio &&
        !effectiveSymbol &&
        !detailFromFile &&
        recs.length > 0

    const runInlineSearch = () => {
        const q = inlineDraft.trim()
        setInlineCommitted(q)
        if (!q) setDetailFromSearch(null)
    }

    return (
        <div style={wrap}>
            <div style={header}>
                <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={headName}>{detail.name}</div>
                    <div style={{ color: MUTED, fontSize: "clamp(10px, 2.4vw, 12px)", marginTop: 4 }}>
                        {detail.symbol}
                        {effectiveSymbol ? (
                            <span style={{ marginLeft: 8, color: ACCENT, fontWeight: 700 }}>검색: {effectiveSymbol}</span>
                        ) : null}
                    </div>
                </div>
                <div style={{ textAlign: "right", flexShrink: 0, minWidth: 0 }}>
                    <div style={headPrice}>{formatKRW(detail.price)}</div>
                    <div style={{ color: dirColor, fontSize: "clamp(11px, 2.8vw, 15px)", fontWeight: 700, marginTop: 4 }}>
                        {detail.compare_label}{" "}
                        {up ? "+" : ""}
                        {formatKRW(detail.change_amount).replace("원", "")}원 ({up ? "+" : ""}
                        {detail.change_pct.toFixed(1)}%)
                    </div>
                </div>
            </div>

            {showInlineSearch && (
                <div style={searchRow}>
                    <input
                        type="text"
                        value={inlineDraft}
                        onChange={(e) => setInlineDraft(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === "Enter") runInlineSearch()
                        }}
                        placeholder="종목코드 또는 이름 (엔터)"
                        style={searchInput}
                        aria-label="종목 검색"
                    />
                    <button type="button" style={searchSubmitBtn} onClick={runInlineSearch}>
                        조회
                    </button>
                    {inlineCommitted && !propSymbol ? (
                        <button
                            type="button"
                            style={searchClearBtn}
                            onClick={() => {
                                setInlineCommitted("")
                                setInlineDraft("")
                            }}
                        >
                            초기화
                        </button>
                    ) : null}
                </div>
            )}

            {(searchLoading || searchError || searchBanner) && (
                <div style={alertStrip}>
                    {searchLoading && (
                        <div style={{ color: ACCENT, fontSize: 12, fontWeight: 600 }}>분석 데이터 불러오는 중…</div>
                    )}
                    {searchError && (
                        <div style={{ color: "#F87171", fontSize: 12, fontWeight: 600, lineHeight: 1.45 }}>{searchError}</div>
                    )}
                    {searchBanner && (
                        <div style={{ color: "#CA8A04", fontSize: 11, fontWeight: 600, lineHeight: 1.45 }}>{searchBanner}</div>
                    )}
                </div>
            )}

            {pickerVisible && recs.length > 1 && (
                <div style={pickerRow}>
                    <button
                        type="button"
                        style={{
                            ...pickerNavBtn,
                            opacity: idx <= 0 ? 0.35 : 1,
                            cursor: idx <= 0 ? "not-allowed" : "pointer",
                        }}
                        onClick={() => setActiveStockIndex((i) => Math.max(0, i - 1))}
                        disabled={idx <= 0}
                        aria-label="이전 종목"
                    >
                        ‹
                    </button>
                    <select
                        style={pickerSelect}
                        value={String(idx)}
                        onChange={(e) => setActiveStockIndex(Number(e.target.value))}
                        aria-label="추천 목록에서 종목 선택"
                    >
                        {recs.map((r: any, i: number) => (
                            <option key={i} value={String(i)}>
                                {String(r?.name || r?.ticker || `#${i + 1}`)}
                            </option>
                        ))}
                    </select>
                    <span style={pickerHint}>
                        {idx + 1} / {recs.length}
                    </span>
                    <button
                        type="button"
                        style={{
                            ...pickerNavBtn,
                            opacity: idx >= maxIdx ? 0.35 : 1,
                            cursor: idx >= maxIdx ? "not-allowed" : "pointer",
                        }}
                        onClick={() => setActiveStockIndex((i) => Math.min(maxIdx, i + 1))}
                        disabled={idx >= maxIdx}
                        aria-label="다음 종목"
                    >
                        ›
                    </button>
                </div>
            )}

            <div style={tabRow}>
                {tabs.map((t) => (
                    <button
                        key={t.id}
                        type="button"
                        onClick={() => setTab(t.id)}
                        style={{
                            ...tabBtn,
                            color: tab === t.id ? "#fff" : MUTED,
                            borderBottom: tab === t.id ? "2px solid #fff" : "2px solid transparent",
                        }}
                    >
                        {t.label}
                    </button>
                ))}
            </div>

            <div style={body}>
                {tab === "chart" && (
                    <div style={tabPanelGrow}>
                        <div
                            style={{
                                display: "flex",
                                justifyContent: "space-between",
                                alignItems: "center",
                                marginBottom: 10,
                                flexShrink: 0,
                                gap: 8,
                                flexWrap: "wrap",
                            }}
                        >
                            <span style={{ color: ACCENT, fontSize: "clamp(10px, 2.5vw, 12px)", fontWeight: 700 }}>자세한 차트 (목업)</span>
                            <div style={{ display: "flex", gap: 6 }}>
                                <button
                                    type="button"
                                    onClick={() => setChartMode("line")}
                                    style={{
                                        ...pill,
                                        background: chartMode === "line" ? "#2A2A2A" : "transparent",
                                        color: "#fff",
                                    }}
                                >
                                    라인
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setChartMode("candle")}
                                    style={{
                                        ...pill,
                                        background: chartMode === "candle" ? "#2A2A2A" : "transparent",
                                        color: "#fff",
                                    }}
                                >
                                    캔들
                                </button>
                            </div>
                        </div>
                        <div ref={chartBoxRef} style={chartBoxShell}>
                            {chartMode === "line" ? (
                                <LineChart data={detail.chart.line} color={UP} width={chartBox.w} height={chartBox.h} />
                            ) : (
                                <CandlePreview
                                    candles={detail.chart.candles || []}
                                    upColor={UP}
                                    downColor={DOWN}
                                    width={chartBox.w}
                                    height={chartBox.h}
                                />
                            )}
                        </div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 12, flexShrink: 0 }}>
                            {detail.chart.timeframes.map((tf) => (
                                <button
                                    key={tf}
                                    type="button"
                                    onClick={() => setTfPick(tf)}
                                    style={{
                                        ...pill,
                                        background: activeTf === tf ? "#2A2A2A" : "transparent",
                                        color: activeTf === tf ? "#fff" : MUTED,
                                        fontSize: 11,
                                    }}
                                >
                                    {tf}
                                </button>
                            ))}
                        </div>
                        {(detail.chart.annotations?.high || detail.chart.annotations?.low) && (
                            <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 4, flexShrink: 0 }}>
                                {detail.chart.annotations?.high && (
                                    <span style={{ color: MUTED, fontSize: 11 }}>{detail.chart.annotations.high.label}</span>
                                )}
                                {detail.chart.annotations?.low && (
                                    <span style={{ color: MUTED, fontSize: 11 }}>{detail.chart.annotations.low.label}</span>
                                )}
                            </div>
                        )}
                    </div>
                )}

                {tab === "hoga" && (
                    <div style={tabPanelGrow}>
                        <div
                            style={{
                                display: "grid",
                                gridTemplateColumns: "minmax(0,1fr) minmax(72px,12%) minmax(0,1fr)",
                                gap: 4,
                                fontSize: "clamp(9px, 2vw, 11px)",
                                color: MUTED,
                                marginBottom: 8,
                                flexShrink: 0,
                            }}
                        >
                            <span>매도잔량</span>
                            <span style={{ textAlign: "center" }}>호가</span>
                            <span style={{ textAlign: "right" }}>매수잔량</span>
                        </div>
                        {detail.order_book.rows.map((row, i) => {
                            const maxAsk = Math.max(...detail.order_book.rows.map((r) => r.ask_vol || 0), 1)
                            const maxBid = Math.max(...detail.order_book.rows.map((r) => r.bid_vol || 0), 1)
                            const aw = row.ask_vol != null ? (row.ask_vol / maxAsk) * 100 : 0
                            const bw = row.bid_vol != null ? (row.bid_vol / maxBid) * 100 : 0
                            return (
                                <div
                                    key={i}
                                    style={{
                                        display: "grid",
                                        gridTemplateColumns: "minmax(0,1fr) minmax(72px,12%) minmax(0,1fr)",
                                        alignItems: "center",
                                        gap: 6,
                                        marginBottom: 4,
                                    }}
                                >
                                    <div style={{ position: "relative", height: 28, background: "#0A0A0A", borderRadius: 6, overflow: "hidden" }}>
                                        {row.ask_vol != null && (
                                            <div
                                                style={{
                                                    position: "absolute",
                                                    right: 0,
                                                    top: 0,
                                                    bottom: 0,
                                                    width: `${aw}%`,
                                                    background: "rgba(49,130,246,0.35)",
                                                    borderRadius: "6px 0 0 6px",
                                                }}
                                            />
                                        )}
                                        <span style={{ position: "relative", zIndex: 1, paddingLeft: 8, fontSize: 11, color: DOWN, lineHeight: "28px" }}>
                                            {row.ask_vol != null ? row.ask_vol.toLocaleString("ko-KR") : ""}
                                        </span>
                                    </div>
                                    <div
                                        style={{
                                            textAlign: "center",
                                            padding: "4px 0",
                                            borderRadius: 8,
                                            border: row.highlight ? "2px solid #fff" : "1px solid transparent",
                                            background: row.highlight ? "#1A1A1A" : "transparent",
                                        }}
                                    >
                                        <div style={{ color: "#fff", fontSize: 12, fontWeight: 800 }}>{formatKRW(row.price).replace("원", "")}</div>
                                        <div style={{ color: MUTED, fontSize: 9 }}>{row.pct_label}</div>
                                    </div>
                                    <div style={{ position: "relative", height: 28, background: "#0A0A0A", borderRadius: 6, overflow: "hidden" }}>
                                        {row.bid_vol != null && (
                                            <div
                                                style={{
                                                    position: "absolute",
                                                    left: 0,
                                                    top: 0,
                                                    bottom: 0,
                                                    width: `${bw}%`,
                                                    background: "rgba(240,68,82,0.35)",
                                                    borderRadius: "0 6px 6px 0",
                                                }}
                                            />
                                        )}
                                        <div
                                            style={{
                                                position: "relative",
                                                zIndex: 1,
                                                height: "100%",
                                                display: "flex",
                                                alignItems: "center",
                                                justifyContent: "flex-end",
                                                paddingRight: 8,
                                                fontSize: 11,
                                                color: UP,
                                                fontWeight: 600,
                                            }}
                                        >
                                            {row.bid_vol != null ? row.bid_vol.toLocaleString("ko-KR") : ""}
                                        </div>
                                    </div>
                                </div>
                            )
                        })}
                        <div
                            style={{
                                display: "flex",
                                justifyContent: "space-between",
                                marginTop: 14,
                                paddingTop: 12,
                                borderTop: `1px solid ${BORDER}`,
                                flexShrink: 0,
                                flexWrap: "wrap",
                                gap: 8,
                            }}
                        >
                            <div>
                                <div style={{ color: MUTED, fontSize: 10 }}>{detail.order_book.footer.sell_wait_label}</div>
                                <div style={{ color: DOWN, fontSize: 13, fontWeight: 700 }}>{detail.order_book.footer.sell_wait}</div>
                            </div>
                            <div style={{ color: MUTED, fontSize: 11, alignSelf: "center" }}>{detail.order_book.footer.session_note}</div>
                            <div style={{ textAlign: "right" }}>
                                <div style={{ color: MUTED, fontSize: 10 }}>{detail.order_book.footer.buy_wait_label}</div>
                                <div style={{ color: UP, fontSize: 13, fontWeight: 700 }}>{detail.order_book.footer.buy_wait}</div>
                            </div>
                        </div>
                        <div style={{ marginTop: 16, flex: 1, minHeight: 80, display: "flex", flexDirection: "column" }}>
                            <div style={{ color: MUTED, fontSize: 11, marginBottom: 8, flexShrink: 0 }}>
                                체결강도 <span style={{ color: "#fff", fontWeight: 800 }}>{detail.execution.strength_pct.toFixed(2)}%</span>
                            </div>
                            <div style={{ flex: 1, minHeight: 48, overflow: "auto" }}>
                                {detail.execution.trades.map((tr, j) => (
                                    <div key={j} style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
                                        <span style={{ color: tr.side === "buy" ? UP : DOWN, fontWeight: 700 }}>
                                            {formatKRW(tr.price)} · {tr.qty.toLocaleString("ko-KR")}주
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                )}

                {tab === "info" && (
                    <div style={{ width: "100%", minWidth: 0 }}>
                        <div style={{ color: "#fff", fontSize: 13, fontWeight: 800, marginBottom: 10 }}>시세</div>
                        {detail.ranges.map((r) => (
                            <RangeGauge key={r.id} label={r.label} low={r.low} high={r.high} current={detail.price} />
                        ))}
                        <div
                            style={{
                                display: "grid",
                                gridTemplateColumns: "1fr 1fr",
                                gap: 10,
                                marginTop: 8,
                            }}
                        >
                            <StatCell k="시작가" v={formatKRW(detail.session.open)} />
                            <StatCell k="종가" v={formatKRW(detail.session.close)} />
                            <StatCell k="거래량" v={formatVolumeShares(detail.session.volume)} />
                            <StatCell k="거래대금" v={detail.session.trading_value_label} />
                        </div>
                        <div style={{ color: "#fff", fontSize: 13, fontWeight: 800, margin: "18px 0 10px" }}>투자자 동향 (목업)</div>
                        {detail.investors.map((inv) => {
                            const buy = inv.side === "buy"
                            return (
                                <div key={inv.label} style={{ marginBottom: 10 }}>
                                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                                        <span style={{ color: MUTED, fontSize: 12 }}>{inv.label}</span>
                                        <span style={{ color: buy ? UP : DOWN, fontSize: 12, fontWeight: 800 }}>{inv.net_display}</span>
                                    </div>
                                    <div style={{ height: 8, background: "#1A1A1A", borderRadius: 99, overflow: "hidden" }}>
                                        <div
                                            style={{
                                                width: buy ? "72%" : "55%",
                                                height: "100%",
                                                borderRadius: 99,
                                                background: buy ? UP : DOWN,
                                                marginLeft: buy ? "28%" : 0,
                                            }}
                                        />
                                    </div>
                                </div>
                            )
                        })}
                        <div style={{ marginTop: 16, padding: 12, background: CARD, borderRadius: 12, border: `1px solid ${BORDER}` }}>
                            <div style={{ color: MUTED, fontSize: 11, marginBottom: 8 }}>가격 제한 (목업)</div>
                            <div style={{ fontSize: 12, color: "#fff", lineHeight: 1.6 }}>
                                상한 {detail.limits.upper} · 하한 {detail.limits.lower}
                                <br />
                                VI {detail.limits.vi}
                            </div>
                        </div>
                    </div>
                )}

                {tab === "summary" && (
                    <div style={{ width: "100%", minWidth: 0 }}>
                        <div style={{ color: ACCENT, fontSize: 11, fontWeight: 700, marginBottom: 6 }}>10초 요약 (목업 + 뉴스)</div>
                        <div style={{ color: "#fff", fontSize: 16, fontWeight: 800, marginBottom: 14 }}>지금 알아두면 좋은 요약</div>
                        {detail.insights.map((ins, k) => (
                            <div
                                key={k}
                                style={{
                                    background: CARD,
                                    border: `1px solid ${BORDER}`,
                                    borderRadius: 14,
                                    padding: "12px 14px",
                                    marginBottom: 10,
                                    display: "flex",
                                    gap: 12,
                                    alignItems: "flex-start",
                                }}
                            >
                                <span
                                    style={{
                                        flexShrink: 0,
                                        fontSize: 10,
                                        fontWeight: 800,
                                        padding: "4px 8px",
                                        borderRadius: 8,
                                        background: ins.tag === "호재" ? "rgba(240,68,82,0.2)" : "rgba(181,255,25,0.12)",
                                        color: ins.tag === "호재" ? UP : ACCENT,
                                    }}
                                >
                                    {ins.tag}
                                </span>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ color: "#fff", fontSize: 13, lineHeight: 1.45, fontWeight: 600 }}>{ins.text}</div>
                                    <div style={{ color: MUTED, fontSize: 11, marginTop: 6 }}>{ins.ago}</div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {showBuyButton && (
                <button type="button" style={buyBtn}>
                    구매하기 (데모)
                </button>
            )}
        </div>
    )
}

function StatCell({ k, v }: { k: string; v: string }) {
    return (
        <div style={{ background: "#0A0A0A", borderRadius: 12, padding: "12px 14px", border: `1px solid ${BORDER}` }}>
            <div style={{ color: MUTED, fontSize: 10, marginBottom: 6 }}>{k}</div>
            <div style={{ color: "#fff", fontSize: 14, fontWeight: 800 }}>{v}</div>
        </div>
    )
}

StockDetailPanel.defaultProps = {
    detailJsonUrl: "",
    portfolioUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    stockIndex: 0,
    mergeFromPortfolio: true,
    showStockPicker: true,
    searchSymbol: "",
    analysisUrlTemplate: "",
    allowPortfolioFallbackForSearch: true,
    showInlineSearch: false,
    showBuyButton: true,
}

addPropertyControls(StockDetailPanel, {
    detailJsonUrl: {
        type: ControlType.String,
        title: "상세 JSON URL",
        defaultValue: "",
        description: "비우면 목업. 배포 후 raw URL 예: .../stock_detail_mock.json",
    },
    portfolioUrl: {
        type: ControlType.String,
        title: "portfolio.json URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    },
    stockIndex: {
        type: ControlType.Number,
        title: "종목 인덱스",
        defaultValue: 0,
        min: 0,
        max: 50,
        step: 1,
    },
    mergeFromPortfolio: {
        type: ControlType.Boolean,
        title: "포트폴리오와 병합",
        defaultValue: true,
        enabledTitle: "켜기",
        disabledTitle: "끄기",
        description: "검색 미사용·고정 상세 JSON 없을 때 recommendations[인덱스]로 목업을 채웁니다.",
    },
    showStockPicker: {
        type: ControlType.Boolean,
        title: "사이트 종목 선택",
        defaultValue: true,
        enabledTitle: "표시",
        disabledTitle: "숨김",
        description: "검색·고정 JSON 미사용·병합 모드일 때만 셀렉트·이전·다음 표시",
    },
    searchSymbol: {
        type: ControlType.String,
        title: "검색 종목 (연동)",
        defaultValue: "",
        description: "검색 컴포넌트·변수와 연결. 비우면 인라인 검색 또는 추천 인덱스 사용",
    },
    analysisUrlTemplate: {
        type: ControlType.String,
        title: "분석 JSON URL 템플릿",
        defaultValue: "",
        description:
            "Vercel: https://<프로젝트>.vercel.app/api/stock_detail?q={symbol} — {symbol}{ticker}{q} 치환(쿼리·경로 모두 가능)",
    },
    allowPortfolioFallbackForSearch: {
        type: ControlType.Boolean,
        title: "검색 폴백(추천 일치)",
        defaultValue: true,
        enabledTitle: "허용",
        disabledTitle: "끔",
        description: "API 실패·템플릿 없을 때 recommendations에서만 종목 매칭",
    },
    showInlineSearch: {
        type: ControlType.Boolean,
        title: "패널 내 검색창",
        defaultValue: false,
        enabledTitle: "표시",
        disabledTitle: "숨김",
        description: "외부 검색만 쓰면 끄기",
    },
    showBuyButton: {
        type: ControlType.Boolean,
        title: "구매 버튼",
        defaultValue: true,
        enabledTitle: "표시",
        disabledTitle: "숨김",
    },
})

const wrap: CSSProperties = {
    width: "100%",
    height: "100%",
    minHeight: 240,
    alignSelf: "stretch",
    background: BG,
    borderRadius: 20,
    border: `1px solid ${BORDER}`,
    overflow: "hidden",
    fontFamily: font,
    boxSizing: "border-box",
    display: "flex",
    flexDirection: "column",
}

const header: CSSProperties = {
    padding: "clamp(12px, 3vw, 18px)",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 12,
    borderBottom: `1px solid ${BORDER}`,
    flexShrink: 0,
}

const headName: CSSProperties = {
    color: "#fff",
    fontSize: "clamp(15px, 3.8vw, 22px)",
    fontWeight: 800,
    lineHeight: 1.2,
    wordBreak: "break-word" as const,
}

const headPrice: CSSProperties = {
    color: "#fff",
    fontSize: "clamp(17px, 5.2vw, 32px)",
    fontWeight: 800,
    lineHeight: 1.15,
}

const tabPanelGrow: CSSProperties = {
    display: "flex",
    flexDirection: "column",
    flex: 1,
    minHeight: 0,
    width: "100%",
}

const chartBoxShell: CSSProperties = {
    flex: 1,
    minHeight: 160,
    width: "100%",
    position: "relative",
}

const searchRow: CSSProperties = {
    display: "flex",
    flexWrap: "wrap",
    alignItems: "center",
    gap: 8,
    padding: "10px 14px",
    borderBottom: `1px solid ${BORDER}`,
    background: "#0A0A0A",
}

const searchInput: CSSProperties = {
    flex: 1,
    minWidth: 140,
    padding: "10px 12px",
    borderRadius: 10,
    border: `1px solid ${BORDER}`,
    background: "#111",
    color: "#fff",
    fontSize: 14,
    fontWeight: 600,
    fontFamily: font,
    outline: "none",
    boxSizing: "border-box",
}

const searchSubmitBtn: CSSProperties = {
    padding: "10px 16px",
    borderRadius: 10,
    border: `1px solid ${ACCENT}`,
    background: "rgba(181,255,25,0.12)",
    color: ACCENT,
    fontSize: 13,
    fontWeight: 800,
    cursor: "pointer",
    fontFamily: font,
}

const searchClearBtn: CSSProperties = {
    padding: "10px 12px",
    borderRadius: 10,
    border: `1px solid ${BORDER}`,
    background: "transparent",
    color: MUTED,
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: font,
}

const alertStrip: CSSProperties = {
    padding: "10px 14px",
    borderBottom: `1px solid ${BORDER}`,
    background: "#0D0D0D",
    display: "flex",
    flexDirection: "column",
    gap: 6,
}

const pickerRow: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "10px 14px",
    borderBottom: `1px solid ${BORDER}`,
    background: "#0A0A0A",
    flexWrap: "wrap",
}

const pickerNavBtn: CSSProperties = {
    width: 36,
    height: 36,
    padding: 0,
    borderRadius: 10,
    border: `1px solid ${BORDER}`,
    background: "#111",
    color: ACCENT,
    fontSize: 20,
    fontWeight: 700,
    lineHeight: 1,
    cursor: "pointer",
    fontFamily: font,
    flexShrink: 0,
}

const pickerSelect: CSSProperties = {
    flex: 1,
    minWidth: 120,
    padding: "8px 10px",
    borderRadius: 10,
    border: `1px solid ${BORDER}`,
    background: "#111",
    color: "#fff",
    fontSize: 13,
    fontWeight: 600,
    fontFamily: font,
    cursor: "pointer",
    outline: "none",
}

const pickerHint: CSSProperties = {
    color: MUTED,
    fontSize: 11,
    fontWeight: 600,
    whiteSpace: "nowrap",
    flexShrink: 0,
}

const tabRow: CSSProperties = {
    display: "flex",
    gap: 4,
    padding: "0 8px",
    borderBottom: `1px solid ${BORDER}`,
    overflowX: "auto" as any,
    width: "100%",
    flexShrink: 0,
}

const tabBtn: CSSProperties = {
    flex: 1,
    minWidth: 0,
    padding: "12px 8px",
    background: "none",
    border: "none",
    cursor: "pointer",
    fontSize: "clamp(11px, 2.6vw, 14px)",
    fontWeight: 700,
    fontFamily: font,
    whiteSpace: "nowrap",
}

const body: CSSProperties = {
    padding: "clamp(12px, 3vw, 18px)",
    flex: 1,
    minHeight: 0,
    overflowY: "auto" as any,
    overflowX: "hidden" as any,
    display: "flex",
    flexDirection: "column",
}

const pill: CSSProperties = {
    border: "none",
    borderRadius: 8,
    padding: "6px 10px",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: font,
}

const buyBtn: CSSProperties = {
    width: "100%",
    padding: "16px 20px",
    background: UP,
    color: "#fff",
    border: "none",
    fontSize: "clamp(14px, 3.5vw, 17px)",
    fontWeight: 800,
    cursor: "pointer",
    fontFamily: font,
    borderRadius: "0",
    flexShrink: 0,
}
