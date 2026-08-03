"use client"
// HoldingsTable — 보유 포트폴리오 (좌 레일 최상단 = 가장 잘 보이는 위치, PM 결함 #7).
// 행 = 로고 + 수량·평단 + 실시간 현재가(tick 플래시) + 손익. 클릭 = 링크그룹 전환(verity-ticker).
// KR = Railway 실시간(3s 공유 폴러) / US = 서버 스냅샷 가격 (전일종가 체계, 차트 이원화 결정 정합).
import { useEffect, useRef } from "react"
import { useDark, palette, cardStyle, FONT, NUM, CARD_TITLE, RAIL_PAD, hoverBg } from "@/lib/theme"
import { useQuotes } from "@/lib/quotes"
import { selectTicker, type Holding } from "@/lib/types"
import StockLogo from "./StockLogo"

export default function HoldingsTable({ holdings, status }: { holdings: Holding[]; status: "loading" | "ok" | "error" }) {
    const dark = useDark()
    const c = palette(dark)
    const krTickers = holdings.filter((h) => /^\d{6}$/.test(h.ticker)).map((h) => h.ticker)
    const { q } = useQuotes(krTickers)
    const prev = useRef<Record<string, number>>({})

    useEffect(() => {
        krTickers.forEach((t) => {
            const p = q[t]?.price
            if (typeof p === "number") prev.current[t] = p
        })
    })

    let evalKr = 0
    holdings.forEach((h) => {
        if (/^\d{6}$/.test(h.ticker)) {
            const px = q[h.ticker]?.price ?? h.current_price ?? 0
            evalKr += (h.quantity || 0) * px
        }
    })

    return (
        <div style={{ ...cardStyle(c, RAIL_PAD), fontFamily: FONT, display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 4 }}>
                <span style={{ ...CARD_TITLE, color: c.ink }}>보유 포트폴리오</span>
                <span style={{ fontSize: 10.5, color: c.faint, ...NUM }}>{holdings.length}종목</span>
            </div>

            {status === "loading" ? (
                <div style={{ fontSize: 12.5, color: c.faint, padding: "6px 0" }}>불러오는 중…</div>
            ) : holdings.length === 0 ? (
                <div style={{ fontSize: 12.5, color: c.sub, padding: "6px 0" }}>보유 종목 없음.</div>
            ) : (
                holdings.map((h, i) => {
                    const isKR = /^\d{6}$/.test(h.ticker)
                    const live = isKR ? q[h.ticker]?.price : undefined
                    const px = typeof live === "number" ? live : h.current_price || 0
                    const was = prev.current[h.ticker]
                    const dir = typeof live === "number" && typeof was === "number" && live !== was ? (live > was ? "up" : "dn") : ""
                    const buy = h.buy_price || 0
                    const pnlPct = buy > 0 && px > 0 ? ((px - buy) / buy) * 100 : null
                    const evalAmt = (h.quantity || 0) * px
                    const isUS = h.currency === "USD"
                    const col = pnlPct === null ? c.faint : pnlPct > 0 ? c.up : pnlPct < 0 ? c.down : c.faint
                    const fmtPx = isUS ? `$${px.toFixed(2)}` : Math.round(px).toLocaleString()
                    const fmtEval = isUS ? `$${evalAmt.toFixed(0)}` : Math.round(evalAmt).toLocaleString()
                    const fmtBuy = isUS ? `$${buy.toFixed(2)}` : Math.round(buy).toLocaleString()
                    return (
                        <div
                            key={h.ticker}
                            onClick={() => selectTicker(h.ticker, h.name)}
                            onMouseEnter={(e) => { e.currentTarget.style.background = hoverBg(dark) }}
                            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent" }}
                            style={{ display: "flex", alignItems: "center", gap: 9, padding: "8px 4px", borderTop: i === 0 ? "none" : `1px solid ${c.line}`, cursor: "pointer", borderRadius: 8 }}
                        >
                            <StockLogo ticker={h.ticker} name={h.name} size={24} />
                            <div style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0, flex: 1 }}>
                                <span style={{ fontSize: 13, fontWeight: 700, color: c.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                    {h.name || h.ticker}
                                </span>
                                <span style={{ fontSize: 10.5, color: c.faint, ...NUM }}>
                                    {(h.quantity || 0).toLocaleString()}주 · 평단 {fmtBuy}
                                </span>
                            </div>
                            <div style={{ display: "flex", flexDirection: "column", gap: 1, alignItems: "flex-end", flexShrink: 0 }}>
                                <span key={`${h.ticker}-${px}`} className={dir ? `af-flash-${dir}` : undefined} style={{ fontSize: 13.5, fontWeight: 800, color: c.ink, ...NUM, padding: "0 3px" }}>
                                    {fmtPx}
                                </span>
                                <span style={{ fontSize: 10.5, fontWeight: 700, color: col, ...NUM }}>
                                    {pnlPct !== null ? `${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(1)}%` : "—"} · {fmtEval}
                                </span>
                            </div>
                        </div>
                    )
                })
            )}

            {holdings.length > 0 ? (
                <div style={{ display: "flex", justifyContent: "space-between", paddingTop: 7, borderTop: `1px solid ${c.line}`, fontSize: 11, color: c.sub }}>
                    <span>KR 평가액 (실시간)</span>
                    <span style={{ fontWeight: 800, color: c.ink, ...NUM }}>{Math.round(evalKr).toLocaleString()}원</span>
                </div>
            ) : null}
        </div>
    )
}
