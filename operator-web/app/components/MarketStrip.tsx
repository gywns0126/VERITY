"use client"
// MarketStrip — 상단 지수 스트립 (v2 터미널). 공개 사실(macro_snapshot, 전일종가/T+1)만. 외곽선 0.
// v3.3 (PM 2026-08-03 "코인 시세 위로 — 코스피 코스닥 있는 곳까지"): BTC/ETH 를 코스닥 옆에 상주
//   (Binance 공개 API = 마켓보드 법적 확정 소스, TIDE 트랙, 24/7 · 5초 tick 플래시).
import { useEffect, useRef, useState } from "react"
import { useDark, palette, FONT, NUM } from "@/lib/theme"
import { fetchPublic } from "@/lib/api"

const LEAD: Array<{ key: string; name: string; unit?: string }> = [
    { key: "kospi", name: "코스피" },
    { key: "kosdaq", name: "코스닥" },
]
const REST: Array<{ key: string; name: string; unit?: string }> = [
    { key: "nasdaq", name: "나스닥" },
    { key: "sp500", name: "S&P 500" },
    { key: "sox", name: "필라델피아 반도체" },
    { key: "vix", name: "VIX" },
    { key: "usd_krw", name: "달러 환율", unit: "원" },
    { key: "us_10y", name: "미 10년물", unit: "%" },
]

const CRYPTO_ENDPOINT =
    'https://data-api.binance.vision/api/v3/ticker/24hr?symbols=["BTCUSDT","ETHUSDT"]'
const CRYPTO_POLL_MS = 5000
const CRYPTO_NAMES: Record<string, string> = { BTCUSDT: "비트코인", ETHUSDT: "이더리움" }

type Node = { value?: number; change_pct?: number; change_percent?: number; sparkline?: number[] }
type CryptoRow = { symbol: string; lastPrice?: string; priceChangePercent?: string }

function Spark({ data, color }: { data: number[]; color: string }) {
    if (!data || data.length < 2) return null
    const w = 42, h = 26, pad = 2
    const mn = Math.min(...data), mx = Math.max(...data), rng = mx - mn || 1
    const pts = data.map((v, i) => `${((i / (data.length - 1)) * w).toFixed(1)},${(h - pad - ((v - mn) / rng) * (h - pad * 2)).toFixed(1)}`)
    return (
        <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: "block", flexShrink: 0 }}>
            <polyline points={pts.join(" ")} fill="none" strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" style={{ stroke: color }} />
        </svg>
    )
}

export default function MarketStrip() {
    const dark = useDark()
    const c = palette(dark)
    const [m, setM] = useState<Record<string, Node>>({})
    const [crypto, setCrypto] = useState<CryptoRow[]>([])
    const prevPx = useRef<Record<string, number>>({})

    useEffect(() => {
        let cancelled = false
        fetchPublic<{ macro?: Record<string, Node> }>("macro_snapshot.json").then((r) => {
            if (cancelled) return
            setM((r.ok && (r.data.macro || (r.data as unknown as Record<string, Node>))) || {})
        })
        // 크립토 24/7 tick
        async function pull() {
            try {
                const r = await fetch(CRYPTO_ENDPOINT, { cache: "no-store" })
                if (!r.ok) return
                const d = await r.json()
                if (!cancelled && Array.isArray(d)) setCrypto(d)
            } catch {}
        }
        pull()
        const t = setInterval(pull, CRYPTO_POLL_MS)
        return () => {
            cancelled = true
            clearInterval(t)
        }
    }, [])

    useEffect(() => {
        crypto.forEach((r) => {
            const p = parseFloat(r.lastPrice || "")
            if (isFinite(p)) prevPx.current[r.symbol] = p
        })
    })

    function IndexCard({ k, name, unit }: { k: string; name: string; unit?: string }) {
        const n = m[k] || {}
        const v = typeof n.value === "number" ? n.value : null
        const cp = typeof n.change_pct === "number" ? n.change_pct : typeof n.change_percent === "number" ? n.change_percent : null
        const col = cp == null ? c.faint : cp > 0 ? c.up : cp < 0 ? c.down : c.faint
        const sign = cp != null && cp > 0 ? "+" : ""
        return (
            <div style={{ background: c.card, borderRadius: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.05)", padding: "9px 11px", display: "flex", alignItems: "center", gap: 9, minWidth: 0 }}>
                {n.sparkline && n.sparkline.length > 1 ? <Spark data={n.sparkline} color={col} /> : null}
                <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: 10.5, fontWeight: 700, color: c.sub, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{name}</div>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                        <span style={{ fontSize: 13.5, fontWeight: 800, color: c.ink, ...NUM }}>{v != null ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}{unit || ""}</span>
                        <span style={{ fontSize: 10.5, fontWeight: 700, color: col, ...NUM }}>{cp != null ? `${sign}${cp.toFixed(2)}%` : ""}</span>
                    </div>
                </div>
            </div>
        )
    }

    function CryptoCard({ row }: { row: CryptoRow }) {
        const px = parseFloat(row.lastPrice || "")
        const cp = parseFloat(row.priceChangePercent || "")
        const was = prevPx.current[row.symbol]
        const dir = isFinite(px) && typeof was === "number" && px !== was ? (px > was ? "up" : "dn") : ""
        const col = !isFinite(cp) ? c.faint : cp > 0 ? c.up : cp < 0 ? c.down : c.faint
        const sign = isFinite(cp) && cp > 0 ? "+" : ""
        return (
            <div style={{ background: c.card, borderRadius: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.05)", padding: "9px 11px", display: "flex", alignItems: "center", gap: 9, minWidth: 0 }}>
                <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: 10.5, fontWeight: 700, color: c.sub, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {CRYPTO_NAMES[row.symbol] || row.symbol} <span style={{ color: c.faint, fontWeight: 500 }}>24/7</span>
                    </div>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                        <span key={`${row.symbol}-${row.lastPrice}`} className={dir ? `af-flash-${dir}` : undefined} style={{ fontSize: 13.5, fontWeight: 800, color: c.ink, ...NUM, padding: "0 2px" }}>
                            {isFinite(px) ? "$" + px.toLocaleString(undefined, { maximumFractionDigits: px >= 1000 ? 0 : 2 }) : "—"}
                        </span>
                        <span style={{ fontSize: 10.5, fontWeight: 700, color: col, ...NUM }}>{isFinite(cp) ? `${sign}${cp.toFixed(2)}%` : ""}</span>
                    </div>
                </div>
            </div>
        )
    }

    return (
        <div className="af-mkt" style={{ fontFamily: FONT }}>
            {LEAD.map(({ key, name, unit }) => <IndexCard key={key} k={key} name={name} unit={unit} />)}
            {crypto.map((row) => <CryptoCard key={row.symbol} row={row} />)}
            {REST.map(({ key, name, unit }) => <IndexCard key={key} k={key} name={name} unit={unit} />)}
        </div>
    )
}
