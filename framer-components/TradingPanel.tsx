import { addPropertyControls, ControlType } from "framer"
import React, { useCallback, useEffect, useMemo, useState } from "react"
import type { CSSProperties } from "react"

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆ (Neo Dark Terminal — _shared-patterns.ts 마스터)
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    strongBuy: "#22C55E", buy: "#B5FF19", watch: "#FFD600", caution: "#F59E0B", avoid: "#EF4444",
    up: "#F04452", down: "#3182F6",
    info: "#5BA9FF", success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const G = {
    accent: "0 0 8px rgba(181,255,25,0.35)",
    accentSoft: "0 0 4px rgba(181,255,25,0.20)",
    accentStrong: "0 0 12px rgba(181,255,25,0.50)",
    danger: "0 0 6px rgba(239,68,68,0.30)",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_tight: 1.3, lh_normal: 1.5, lh_loose: 1.7,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease", slow: "240ms ease" }
const FONT = "'Inter', 'Pretendard', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/* ── 순수익 계산기 인라인 (netPnlCalc.ts와 동일 로직) ── */
const KR_BROKER_FEE = 0.00015
const KR_TX_TAX = 0.0018
const KR_AGRI_TAX = 0.0015
const US_BROKER_FEE = 0.00025
const US_SEC_FEE = 0.0000278
const US_FX_SPREAD = 0.002

function calcOrderCostInline(
    market: "kr" | "us", side: "buy" | "sell", qty: number, price: number,
): { fee: number; tax: number; fxCost: number; totalCost: number } {
    const amount = price * qty
    const brokeFee = market === "us" ? US_BROKER_FEE : KR_BROKER_FEE
    const fee = amount * brokeFee
    let tax = 0
    if (side === "sell") {
        tax = market === "kr"
            ? amount * (KR_TX_TAX + KR_AGRI_TAX)
            : amount * US_SEC_FEE
    }
    const fxCost = market === "us" ? amount * US_FX_SPREAD : 0
    return { fee: Math.round(fee), tax: Math.round(tax), fxCost: Math.round(fxCost), totalCost: Math.round(fee + tax + fxCost) }
}

function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

function fetchJson(url: string, signal?: AbortSignal): Promise<any> {
    return fetch(bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((t) => JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
}

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"
const UP = "#F04452"
const DOWN = "#3182F6"
const BG = C.bgPage
const CARD = C.bgCard
const BORDER = C.border
const MUTED = C.textSecondary
const ACCENT = C.accent
function fmtKRW(n: number): string {
    if (!Number.isFinite(n)) return "—"
    return `${Math.round(n).toLocaleString("ko-KR")}`
}

type Side = "buy" | "sell"
type OrderMode = "market" | "limit"
type TradeMode = "long" | "short"

const INVERSE_PRESETS_KR = [
    { ticker: "252670", name: "KODEX 200선물인버스2X", leverage: "2x", desc: "코스피200 하락 2배" },
    { ticker: "114800", name: "KODEX 인버스", leverage: "1x", desc: "코스피200 하락 1배" },
    { ticker: "251340", name: "KODEX 코스닥150선물인버스", leverage: "1x", desc: "코스닥150 하락" },
    { ticker: "233740", name: "KODEX 코스닥150레버리지", leverage: "2x↑", desc: "코스닥 하락 베팅(인버스)" },
    { ticker: "145670", name: "KINDEX 인버스", leverage: "1x", desc: "코스피200 하락 1배" },
]

const INVERSE_PRESETS_US = [
    { ticker: "SQQQ", name: "ProShares UltraPro Short QQQ", leverage: "3x", desc: "나스닥100 하락 3배" },
    { ticker: "SPXS", name: "Direxion Daily S&P500 Bear 3X", leverage: "3x", desc: "S&P500 하락 3배" },
    { ticker: "SH", name: "ProShares Short S&P500", leverage: "1x", desc: "S&P500 하락 1배" },
    { ticker: "QID", name: "ProShares UltraShort QQQ", leverage: "2x", desc: "나스닥100 하락 2배" },
    { ticker: "SDOW", name: "ProShares UltraPro Short Dow30", leverage: "3x", desc: "다우30 하락 3배" },
]

interface Props {
    portfolioUrl: string
    stockIndex: number
    searchSymbol: string
    market: "kr" | "us"
}

function fmtUSD(n: number): string {
    if (!Number.isFinite(n)) return "—"
    return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export default function TradingPanel(props: Props) {
    const { portfolioUrl, stockIndex, searchSymbol, market = "kr" } = props
    const isUS = market === "us"

    const [portfolio, setPortfolio] = useState<any>(null)
    const [side, setSide] = useState<Side>("buy")
    const [mode, setMode] = useState<OrderMode>("limit")
    const [qty, setQty] = useState("")
    const [price, setPrice] = useState("")
    const [submitted, setSubmitted] = useState(false)
    const [tradeMode, setTradeMode] = useState<TradeMode>("long")
    const [selectedInverse, setSelectedInverse] = useState<string | null>(null)
    const priceStep = isUS ? 1 : 1000

    const parsePriceValue = useCallback((v: string): number => {
        const n = Number(String(v || "").replace(/,/g, ""))
        return Number.isFinite(n) ? n : 0
    }, [])

    const formatEditablePrice = useCallback((n: number): string => {
        if (!Number.isFinite(n) || n <= 0) return "0"
        if (isUS) return n.toFixed(2).replace(/\.00$/, "")
        return String(Math.round(n))
    }, [isUS])

    useEffect(() => {
        const u = (portfolioUrl || "").trim()
        if (!u) return
        const ac = new AbortController()
        fetchJson(u, ac.signal).then(d => { if (!ac.signal.aborted) setPortfolio(d) }).catch(() => {})
        return () => ac.abort()
    }, [portfolioUrl])

    const stock = useMemo(() => {
        if (!portfolio) return null
        const allRecs = portfolio.recommendations || []
        const recs = isUS
            ? allRecs.filter((r: any) => r.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM/i.test(r.market || ""))
            : allRecs
        const sym = (searchSymbol || "").trim()
        if (sym) {
            const hit = recs.find((r: any) => {
                const t = String(r?.ticker ?? "").trim()
                return t === sym || String(r?.name ?? "").trim() === sym
            })
            if (hit) return hit
        }
        return recs[stockIndex] || recs[0] || null
    // isUS도 포함해야 market 변경 시 즉시 갱신됨
    }, [portfolio, stockIndex, searchSymbol, isUS])

    const kisSnap = useMemo(() => {
        if (!portfolio || !stock) return null
        const snaps = portfolio.kis_snapshots
        if (!snaps) return null
        const t6 = String(stock.ticker || "").replace(/\D/g, "").padStart(6, "0")
        return snaps[t6] || null
    }, [portfolio, stock])

    const currentPrice = kisSnap?.price?.price || stock?.price || 0
    const changeAmt = kisSnap?.price?.change_amount || 0
    const changePct = kisSnap?.price?.change_pct || 0
    const isUp = changePct >= 0

    useEffect(() => {
        if (currentPrice > 0 && !price) setPrice(formatEditablePrice(currentPrice))
    }, [currentPrice, price, formatEditablePrice])

    const orderbook = useMemo(() => {
        const ob = kisSnap?.orderbook
        if (!ob?.rows?.length) return null
        return ob
    }, [kisSnap])

    const limitPrice = mode === "market" ? currentPrice : parsePriceValue(price)
    const qtyNum = parseInt(qty) || 0
    const totalAmount = limitPrice * qtyNum

    const handleSubmit = useCallback(() => {
        if (qtyNum <= 0) return
        setSubmitted(true)
        setTimeout(() => setSubmitted(false), 3000)
    }, [qtyNum, side, mode, limitPrice])

    const sideColor = side === "buy" ? UP : DOWN

    if (!stock) {
        return (
            <div style={wrap}>
                <div style={{ padding: 40, textAlign: "center" as const, color: MUTED, fontSize: 14, fontFamily: font }}>
                    종목을 선택해주세요
                </div>
            </div>
        )
    }

    return (
        <div style={wrap}>
            {/* Header */}
            <div style={header}>
                <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ color: C.textPrimary, fontSize: 18, fontWeight: 800 }}>{stock.name || "—"}</div>
                    <div style={{ color: MUTED, fontSize: 12, marginTop: 2 }}>{stock.ticker || ""}</div>
                </div>
                <div style={{ textAlign: "right" as const }}>
                    <div style={{ color: C.textPrimary, fontSize: 22, fontWeight: 800 }}>{fmtKRW(currentPrice)}</div>
                    <div style={{ color: isUp ? UP : DOWN, fontSize: 13, fontWeight: 700, marginTop: 2 }}>
                        {isUp ? "+" : ""}{fmtKRW(changeAmt)} ({isUp ? "+" : ""}{changePct.toFixed(2)}%)
                    </div>
                </div>
            </div>

            {/* Long/Short Mode Toggle */}
            <div style={{ display: "flex", gap: 0, padding: "8px 18px 0", flexShrink: 0 }}>
                <button
                    type="button"
                    onClick={() => { setTradeMode("long"); setSelectedInverse(null) }}
                    style={{
                        flex: 1, padding: "8px 0", borderRadius: "10px 0 0 10px", fontSize: 12, fontWeight: 700,
                        cursor: "pointer", fontFamily: font, border: "none",
                        background: tradeMode === "long" ? "#1A2A00" : "transparent",
                        color: tradeMode === "long" ? ACCENT : MUTED,
                        borderBottom: tradeMode === "long" ? `2px solid ${ACCENT}` : "2px solid transparent",
                    }}
                >
                    롱 모드
                </button>
                <button
                    type="button"
                    onClick={() => setTradeMode("short")}
                    style={{
                        flex: 1, padding: "8px 0", borderRadius: "0 10px 10px 0", fontSize: 12, fontWeight: 700,
                        cursor: "pointer", fontFamily: font, border: "none",
                        background: tradeMode === "short" ? "rgba(240,68,82,0.1)" : "transparent",
                        color: tradeMode === "short" ? UP : MUTED,
                        borderBottom: tradeMode === "short" ? `2px solid ${UP}` : "2px solid transparent",
                    }}
                >
                    숏 모드
                </button>
            </div>

            {/* Short Mode: Inverse ETF Presets */}
            {tradeMode === "short" && (
                <div style={{ padding: "8px 18px", flexShrink: 0 }}>
                    <div style={{ background: "rgba(240,68,82,0.08)", border: "1px solid rgba(240,68,82,0.2)", borderRadius: 10, padding: "8px 12px", marginBottom: 8 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                            <span style={{ color: UP, fontSize: 11, fontWeight: 700 }}>⚠ 숏 모드 — 인버스 ETF 매수</span>
                        </div>
                        <span style={{ color: MUTED, fontSize: 9, lineHeight: 1.4 }}>
                            레버리지 상품은 장기 보유 시 괴리율·복리 효과로 원금 손실 위험이 큽니다. 단기 헤지 용도로만 활용하세요.
                        </span>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column" as const, gap: 4 }}>
                        {(isUS ? INVERSE_PRESETS_US : INVERSE_PRESETS_KR).map(inv => (
                            <div
                                key={inv.ticker}
                                onClick={() => setSelectedInverse(selectedInverse === inv.ticker ? null : inv.ticker)}
                                style={{
                                    display: "flex", justifyContent: "space-between", alignItems: "center",
                                    padding: "8px 10px", borderRadius: 8, cursor: "pointer",
                                    background: selectedInverse === inv.ticker ? "#1A1A1A" : "transparent",
                                    border: selectedInverse === inv.ticker ? `1px solid ${UP}` : "1px solid transparent",
                                }}
                            >
                                <div style={{ display: "flex", flexDirection: "column" as const, gap: 2 }}>
                                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                        <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700 }}>{inv.name}</span>
                                        <span style={{ background: "rgba(240,68,82,0.2)", color: UP, fontSize: 9, fontWeight: 700, padding: "1px 5px", borderRadius: 4 }}>{inv.leverage}</span>
                                    </div>
                                    <span style={{ color: MUTED, fontSize: 9 }}>{inv.desc}</span>
                                </div>
                                <span style={{ color: C.textTertiary, fontSize: 10, fontFamily: font }}>{inv.ticker}</span>
                            </div>
                        ))}
                    </div>
                    {selectedInverse && (
                        <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                            {["25%", "50%", "100%"].map(pct => (
                                <button
                                    key={pct}
                                    type="button"
                                    onClick={() => {
                                        const ratio = parseInt(pct) / 100
                                        const maxQty = limitPrice > 0 ? Math.floor(10_000_000 * ratio / limitPrice) : 0
                                        setQty(String(Math.max(1, maxQty)))
                                        setSide("buy")
                                    }}
                                    style={{
                                        flex: 1, padding: "10px 0", borderRadius: 8,
                                        border: `1px solid rgba(240,68,82,0.3)`, background: "rgba(240,68,82,0.05)",
                                        color: UP, fontSize: 12, fontWeight: 700, cursor: "pointer", fontFamily: font,
                                    }}
                                >
                                    {pct}
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* Buy/Sell Toggle */}
            <div style={toggleRow}>
                <button
                    type="button"
                    onClick={() => setSide("buy")}
                    style={{
                        ...toggleBtn,
                        background: side === "buy" ? UP : "transparent",
                        color: side === "buy" ? "#fff" : MUTED,
                        border: side === "buy" ? "none" : `1px solid ${BORDER}`,
                    }}
                >
                    {tradeMode === "short" ? "인버스 매수" : "매수"}
                </button>
                <button
                    type="button"
                    onClick={() => setSide("sell")}
                    style={{
                        ...toggleBtn,
                        background: side === "sell" ? DOWN : "transparent",
                        color: side === "sell" ? "#fff" : MUTED,
                        border: side === "sell" ? "none" : `1px solid ${BORDER}`,
                    }}
                >
                    {tradeMode === "short" ? "인버스 매도" : "매도"}
                </button>
            </div>

            {/* Order Type */}
            <div style={modeRow}>
                <button
                    type="button"
                    onClick={() => setMode("limit")}
                    style={{ ...modePill, background: mode === "limit" ? "#2A2A2A" : "transparent", color: mode === "limit" ? "#fff" : MUTED }}
                >
                    지정가
                </button>
                <button
                    type="button"
                    onClick={() => setMode("market")}
                    style={{ ...modePill, background: mode === "market" ? "#2A2A2A" : "transparent", color: mode === "market" ? "#fff" : MUTED }}
                >
                    시장가
                </button>
            </div>

            <div style={formBody}>
                {/* Mini Orderbook */}
                {orderbook && (
                    <div style={miniObWrap}>
                        {orderbook.rows
                            .filter((r: any) => r.side === "ask")
                            .slice(-3)
                            .map((r: any, i: number) => (
                                <div key={`a${i}`} style={miniObRow} onClick={() => { setPrice(String(r.price)); setMode("limit") }}>
                                    <span style={{ color: DOWN, fontSize: 11, fontWeight: 600 }}>{fmtKRW(r.price)}</span>
                                    <span style={{ color: MUTED, fontSize: 10 }}>{r.ask_vol?.toLocaleString("ko-KR") || ""}</span>
                                </div>
                            ))}
                        <div style={{ ...miniObRow, background: "rgba(255,255,255,0.05)", borderRadius: 6 }}>
                            <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 800 }}>{fmtKRW(orderbook.current_price)}</span>
                            <span style={{ color: ACCENT, fontSize: 10, fontWeight: 700 }}>현재가</span>
                        </div>
                        {orderbook.rows
                            .filter((r: any) => r.side === "bid")
                            .slice(0, 3)
                            .map((r: any, i: number) => (
                                <div key={`b${i}`} style={miniObRow} onClick={() => { setPrice(String(r.price)); setMode("limit") }}>
                                    <span style={{ color: UP, fontSize: 11, fontWeight: 600 }}>{fmtKRW(r.price)}</span>
                                    <span style={{ color: MUTED, fontSize: 10 }}>{r.bid_vol?.toLocaleString("ko-KR") || ""}</span>
                                </div>
                            ))}
                    </div>
                )}

                {/* Price Input */}
                {mode === "limit" && (
                    <div style={inputGroup}>
                        <label style={inputLabel}>가격</label>
                        <div style={inputRow}>
                            <button
                                type="button"
                                style={stepBtn}
                                onClick={() => {
                                    const next = Math.max(0, parsePriceValue(price) - priceStep)
                                    setPrice(formatEditablePrice(next))
                                }}
                            >
                                -
                            </button>
                            <input
                                type="text"
                                inputMode="numeric"
                                value={price}
                                onChange={(e) => {
                                    const raw = e.target.value
                                    if (isUS) {
                                        const cleaned = raw
                                            .replace(/[^0-9.]/g, "")
                                            .replace(/(\..*)\./g, "$1")
                                        setPrice(cleaned)
                                    } else {
                                        setPrice(raw.replace(/\D/g, ""))
                                    }
                                }}
                                style={inputField}
                                aria-label="주문 가격"
                            />
                            <button
                                type="button"
                                style={stepBtn}
                                onClick={() => {
                                    const next = Math.max(0, parsePriceValue(price) + priceStep)
                                    setPrice(formatEditablePrice(next))
                                }}
                            >
                                +
                            </button>
                        </div>
                    </div>
                )}
                {mode === "market" && (
                    <div style={inputGroup}>
                        <label style={inputLabel}>가격</label>
                        <div style={{ ...inputField, display: "flex", alignItems: "center", color: MUTED, cursor: "default" }}>
                            시장가 (최유리)
                        </div>
                    </div>
                )}

                {/* Qty Input */}
                <div style={inputGroup}>
                    <label style={inputLabel}>수량</label>
                    <div style={inputRow}>
                        <button type="button" style={stepBtn} onClick={() => setQty(String(Math.max(0, (parseInt(qty) || 0) - 1)))}>-</button>
                        <input
                            type="text"
                            inputMode="numeric"
                            value={qty}
                            onChange={(e) => setQty(e.target.value.replace(/\D/g, ""))}
                            placeholder="0"
                            style={inputField}
                            aria-label="주문 수량"
                        />
                        <button type="button" style={stepBtn} onClick={() => setQty(String((parseInt(qty) || 0) + 1))}>+</button>
                    </div>
                    <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                        {["10%", "25%", "50%", "100%"].map((pct) => (
                            <button
                                key={pct}
                                type="button"
                                style={pctBtn}
                                onClick={() => {
                                    if (limitPrice <= 0) return
                                    const ratio = parseInt(pct) / 100
                                    const maxQty = Math.floor(10_000_000 * ratio / limitPrice)
                                    setQty(String(Math.max(1, maxQty)))
                                }}
                            >
                                {pct}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Summary with net cost */}
                {(() => {
                    const cost = totalAmount > 0
                        ? calcOrderCostInline(isUS ? "us" : "kr", side, qtyNum, limitPrice)
                        : { fee: 0, tax: 0, fxCost: 0, totalCost: 0 }
                    const netTotal = side === "buy"
                        ? totalAmount + cost.totalCost
                        : totalAmount - cost.totalCost
                    const fmtAmt = isUS ? fmtUSD : fmtKRW
                    const unit = isUS ? "" : "원"
                    return (
                        <div style={summaryBox}>
                            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                                <span style={{ color: MUTED, fontSize: 12 }}>주문 총액</span>
                                <span style={{ color: C.textPrimary, fontSize: 16, fontWeight: 800 }}>
                                    {totalAmount > 0 ? `${fmtAmt(totalAmount)}${unit}` : "—"}
                                </span>
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                                <span style={{ color: MUTED, fontSize: 11 }}>{mode === "market" ? "시장가" : `${fmtAmt(limitPrice)}${unit}`} × {qtyNum}주</span>
                            </div>
                            {totalAmount > 0 && (
                                <>
                                    <div style={{ borderTop: `1px solid ${BORDER}`, paddingTop: 8, marginTop: 4, display: "flex", flexDirection: "column" as const, gap: 3 }}>
                                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                                            <span style={{ color: MUTED, fontSize: 10 }}>수수료</span>
                                            <span style={{ color: C.textPrimary, fontSize: 10 }}>{fmtAmt(cost.fee)}{unit}</span>
                                        </div>
                                        {cost.tax > 0 && (
                                            <div style={{ display: "flex", justifyContent: "space-between" }}>
                                                <span style={{ color: MUTED, fontSize: 10 }}>{isUS ? "SEC Fee" : "거래세+농특세"}</span>
                                                <span style={{ color: C.textPrimary, fontSize: 10 }}>{fmtAmt(cost.tax)}{unit}</span>
                                            </div>
                                        )}
                                        {cost.fxCost > 0 && (
                                            <div style={{ display: "flex", justifyContent: "space-between" }}>
                                                <span style={{ color: MUTED, fontSize: 10 }}>환전비용</span>
                                                <span style={{ color: C.textPrimary, fontSize: 10 }}>{fmtAmt(cost.fxCost)}{unit}</span>
                                            </div>
                                        )}
                                        <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, paddingTop: 4, borderTop: `1px dashed #333` }}>
                                            <span style={{ color: ACCENT, fontSize: 11, fontWeight: 700 }}>
                                                {side === "buy" ? "실제 지불액" : "실제 수령액"}
                                            </span>
                                            <span style={{ color: ACCENT, fontSize: 13, fontWeight: 800 }}>
                                                {fmtAmt(netTotal)}{unit}
                                            </span>
                                        </div>
                                    </div>
                                </>
                            )}
                        </div>
                    )
                })()}
            </div>

            {/* Submit */}
            <button
                type="button"
                onClick={handleSubmit}
                disabled={qtyNum <= 0}
                style={{
                    ...submitBtn,
                    background: qtyNum > 0 ? sideColor : "#333",
                    cursor: qtyNum > 0 ? "pointer" : "not-allowed",
                    opacity: qtyNum > 0 ? 1 : 0.5,
                }}
            >
                {submitted
                    ? "주문 접수 완료"
                    : tradeMode === "short" && selectedInverse
                        ? `${selectedInverse} ${side === "buy" ? "매수" : "매도"}${totalAmount > 0 ? ` · ${isUS ? fmtUSD(totalAmount) : `${fmtKRW(totalAmount)}원`}` : ""}`
                        : `${side === "buy" ? "매수" : "매도"} 주문${totalAmount > 0 ? ` · ${isUS ? fmtUSD(totalAmount) : `${fmtKRW(totalAmount)}원`}` : ""}`}
            </button>
        </div>
    )
}

TradingPanel.defaultProps = {
    portfolioUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    stockIndex: 0,
    searchSymbol: "",
    market: "kr",
}

addPropertyControls(TradingPanel, {
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
    searchSymbol: {
        type: ControlType.String,
        title: "종목 (연동)",
        defaultValue: "",
    },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["국장 (KR)", "미장 (US)"],
        defaultValue: "kr",
    },
})

const wrap: CSSProperties = {
    width: "100%",
    height: "100%",
    minHeight: 480,
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
    padding: "16px 18px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 12,
    borderBottom: `1px solid ${BORDER}`,
    flexShrink: 0,
}

const toggleRow: CSSProperties = {
    display: "flex",
    gap: 0,
    padding: "12px 18px",
    flexShrink: 0,
}

const toggleBtn: CSSProperties = {
    flex: 1,
    padding: "12px 0",
    borderRadius: 12,
    fontSize: 15,
    fontWeight: 800,
    cursor: "pointer",
    fontFamily: font,
    textAlign: "center" as const,
}

const modeRow: CSSProperties = {
    display: "flex",
    gap: 6,
    padding: "0 18px 12px",
    flexShrink: 0,
}

const modePill: CSSProperties = {
    border: "none",
    borderRadius: 8,
    padding: "8px 14px",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: font,
}

const formBody: CSSProperties = {
    flex: 1,
    padding: "0 18px",
    overflowY: "auto" as any,
    display: "flex",
    flexDirection: "column",
    gap: 14,
}

const miniObWrap: CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 2,
    padding: "8px 0",
}

const miniObRow: CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "6px 10px",
    cursor: "pointer",
    borderRadius: 4,
}

const inputGroup: CSSProperties = { display: "flex", flexDirection: "column", gap: 6 }

const inputLabel: CSSProperties = { color: MUTED, fontSize: 12, fontWeight: 600 }

const inputRow: CSSProperties = { display: "flex", gap: 6, alignItems: "center" }

const inputField: CSSProperties = {
    flex: 1,
    padding: "12px 14px",
    borderRadius: 12,
    border: `1px solid ${BORDER}`,
    background: CARD,
    color: C.textPrimary,
    fontSize: 16,
    fontWeight: 700,
    fontFamily: font,
    outline: "none",
    textAlign: "right" as const,
    boxSizing: "border-box",
}

const stepBtn: CSSProperties = {
    width: 40,
    height: 44,
    borderRadius: 12,
    border: `1px solid ${BORDER}`,
    background: CARD,
    color: C.textPrimary,
    fontSize: 18,
    fontWeight: 700,
    cursor: "pointer",
    fontFamily: font,
    flexShrink: 0,
}

const pctBtn: CSSProperties = {
    flex: 1,
    padding: "8px 0",
    borderRadius: 8,
    border: `1px solid ${BORDER}`,
    background: "transparent",
    color: MUTED,
    fontSize: 11,
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: font,
}

const summaryBox: CSSProperties = {
    background: CARD,
    borderRadius: 14,
    padding: "14px 16px",
    border: `1px solid ${BORDER}`,
}

const submitBtn: CSSProperties = {
    width: "100%",
    padding: "18px 20px",
    color: C.textPrimary,
    border: "none",
    fontSize: 16,
    fontWeight: 800,
    fontFamily: font,
    borderRadius: 0,
    flexShrink: 0,
}
