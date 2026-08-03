"use client"
// Blotter — 주문 블로터 (기관 OMS 문법: 블로터 = primary interface). v1 = 이 브라우저에서
// 낸 주문의 접수/거부 기록 (localStorage af_blotter, OrderTicket 이 기록·이벤트 발신).
// 체결·정정·취소 동기화(KIS 체결통보)는 후속.
import { useEffect, useState } from "react"
import { useDark, palette, cardStyle, FONT, NUM, CARD_TITLE, MAIN_PAD } from "@/lib/theme"
import StockLogo from "./StockLogo"

type Entry = {
    ts: string
    ticker: string
    name?: string
    side: "BUY" | "SELL"
    order_type?: string
    qty: number
    price: number
    status: string
    msg?: string
}

function load(): Entry[] {
    try {
        const raw = localStorage.getItem("af_blotter")
        const arr = raw ? JSON.parse(raw) : []
        return Array.isArray(arr) ? arr.slice(0, 50) : []
    } catch {
        return []
    }
}

export default function Blotter() {
    const dark = useDark()
    const c = palette(dark)
    const [rows, setRows] = useState<Entry[]>([])

    useEffect(() => {
        setRows(load())
        function onChange() {
            setRows(load())
        }
        window.addEventListener("af-blotter", onChange)
        window.addEventListener("storage", onChange)
        return () => {
            window.removeEventListener("af-blotter", onChange)
            window.removeEventListener("storage", onChange)
        }
    }, [])

    function clear() {
        try {
            localStorage.removeItem("af_blotter")
        } catch {}
        setRows([])
    }

    if (rows.length === 0) return null

    return (
        <div style={{ ...cardStyle(c, MAIN_PAD), fontFamily: FONT, display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
                <span style={{ ...CARD_TITLE, color: c.ink }}>주문 블로터</span>
                <button onClick={clear} style={{ border: "none", background: "transparent", color: c.faint, fontSize: 10.5, cursor: "pointer", fontFamily: FONT, padding: 0 }}>
                    비우기
                </button>
            </div>
            {rows.slice(0, 8).map((r, i) => {
                const sideCol = r.side === "BUY" ? c.up : c.down
                const ok = r.status === "접수"
                return (
                    <div key={r.ts + i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0", borderTop: i === 0 ? "none" : `1px solid ${c.line}` }}>
                        <span style={{ fontSize: 10, color: c.faint, ...NUM, width: 40, flexShrink: 0 }}>{r.ts.slice(11, 16)}</span>
                        <StockLogo ticker={r.ticker} name={r.name} size={18} />
                        <span style={{ fontSize: 12, fontWeight: 700, color: c.ink, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.name || r.ticker}</span>
                        <span style={{ fontSize: 10.5, fontWeight: 800, color: sideCol }}>{r.side === "BUY" ? "매수" : "매도"}</span>
                        <span style={{ fontSize: 11, color: c.sub, ...NUM }}>
                            {r.qty.toLocaleString()}주{r.price ? ` @ ${r.price.toLocaleString()}` : " 시장가"}
                        </span>
                        <span style={{ marginLeft: "auto", fontSize: 10, fontWeight: 800, color: ok ? c.green : c.up, background: ok ? c.greenS : c.upS, borderRadius: 6, padding: "2px 7px", flexShrink: 0 }} title={r.msg || ""}>
                            {r.status}
                        </span>
                    </div>
                )
            })}
            <div style={{ fontSize: 9.5, color: c.faint }}>이 브라우저에서 낸 주문 기록 · 체결 동기화 후속</div>
        </div>
    )
}
