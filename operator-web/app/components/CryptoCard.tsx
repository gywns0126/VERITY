"use client"
// CryptoCard — 코인 시세 (PM 2026-08-03 "코인 시세는?"). TIDE 트랙 자산 = BTC/ETH.
// 소스 = Binance 공개 시세 API (마켓보드 법적 확정 소스와 동일, 무인증·브라우저 CORS 허용).
// 24/7 이라 장외에도 tick 이 살아있음. 5초 폴 + 플래시.
import { useEffect, useRef, useState } from "react"
import { useDark, palette, cardStyle, FONT, NUM } from "@/lib/theme"

const ENDPOINT =
    'https://data-api.binance.vision/api/v3/ticker/24hr?symbols=["BTCUSDT","ETHUSDT"]'
const POLL_MS = 5000
const NAMES: Record<string, string> = { BTCUSDT: "비트코인", ETHUSDT: "이더리움" }

type Row = { symbol: string; lastPrice?: string; priceChangePercent?: string }

export default function CryptoCard() {
    const dark = useDark()
    const c = palette(dark)
    const [rows, setRows] = useState<Row[]>([])
    const [err, setErr] = useState(false)
    const prev = useRef<Record<string, number>>({})

    useEffect(() => {
        let stop = false
        async function pull() {
            try {
                const r = await fetch(ENDPOINT, { cache: "no-store" })
                if (!r.ok) throw new Error(String(r.status))
                const d = await r.json()
                if (!stop && Array.isArray(d)) {
                    setRows(d)
                    setErr(false)
                }
            } catch {
                if (!stop) setErr(true)
            }
        }
        pull()
        const t = setInterval(pull, POLL_MS)
        return () => {
            stop = true
            clearInterval(t)
        }
    }, [])

    useEffect(() => {
        rows.forEach((r) => {
            const p = parseFloat(r.lastPrice || "")
            if (isFinite(p)) prev.current[r.symbol] = p
        })
    })

    return (
        <div style={{ ...cardStyle(c, "13px 15px"), fontFamily: FONT, display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 4 }}>
                <span style={{ fontSize: 13.5, fontWeight: 800, color: c.ink, letterSpacing: "-0.02em" }}>크립토</span>
                <span style={{ fontSize: 10, color: c.faint }}>TIDE 트랙 · 24/7</span>
                <span style={{ width: 5, height: 5, borderRadius: "50%", background: c.green, marginLeft: "auto" }} />
            </div>
            {err && rows.length === 0 ? (
                <div style={{ fontSize: 12, color: c.sub }}>시세 연결 실패 (Binance).</div>
            ) : rows.length === 0 ? (
                <div style={{ fontSize: 12, color: c.faint }}>불러오는 중…</div>
            ) : (
                rows.map((r, i) => {
                    const px = parseFloat(r.lastPrice || "")
                    const cp = parseFloat(r.priceChangePercent || "")
                    const was = prev.current[r.symbol]
                    const dir = isFinite(px) && typeof was === "number" && px !== was ? (px > was ? "up" : "dn") : ""
                    const col = !isFinite(cp) ? c.faint : cp > 0 ? c.up : cp < 0 ? c.down : c.faint
                    return (
                        <div key={r.symbol} style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 2px", borderTop: i === 0 ? "none" : `1px solid ${c.line}` }}>
                            <span style={{ fontSize: 12.5, fontWeight: 700, color: c.ink, flex: 1 }}>
                                {NAMES[r.symbol] || r.symbol}
                                <span style={{ fontSize: 10, color: c.faint, marginLeft: 5 }}>{r.symbol.replace("USDT", "")}</span>
                            </span>
                            <span key={`${r.symbol}-${r.lastPrice}`} className={dir ? `af-flash-${dir}` : undefined} style={{ fontSize: 12.5, fontWeight: 800, color: c.ink, ...NUM, padding: "0 3px" }}>
                                {isFinite(px) ? "$" + px.toLocaleString(undefined, { maximumFractionDigits: px >= 1000 ? 0 : 2 }) : "—"}
                            </span>
                            <span style={{ fontSize: 11, fontWeight: 700, color: col, ...NUM, minWidth: 52, textAlign: "right" }}>
                                {isFinite(cp) ? `${cp > 0 ? "+" : ""}${cp.toFixed(2)}%` : ""}
                            </span>
                        </div>
                    )
                })
            )}
            <div style={{ fontSize: 9.5, color: c.faint, paddingTop: 5 }}>Binance 24h 기준 · USDT · 매수/매도 지시 아님</div>
        </div>
    )
}
