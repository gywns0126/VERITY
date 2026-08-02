"use client"
// MarketStrip — 상단 지수 스트립 (v2 터미널). 공개 사실(macro_snapshot, 전일종가/T+1)만. 외곽선 0.
import { useEffect, useState } from "react"
import { useDark, palette, FONT, NUM } from "@/lib/theme"
import { fetchPublic } from "@/lib/api"

const ITEMS: Array<{ key: string; name: string; unit?: string }> = [
    { key: "kospi", name: "코스피" },
    { key: "kosdaq", name: "코스닥" },
    { key: "nasdaq", name: "나스닥" },
    { key: "sp500", name: "S&P 500" },
    { key: "sox", name: "필라델피아 반도체" },
    { key: "vix", name: "VIX" },
    { key: "usd_krw", name: "달러 환율", unit: "원" },
    { key: "us_10y", name: "미 10년물", unit: "%" },
]

type Node = { value?: number; change_pct?: number; change_percent?: number; sparkline?: number[] }

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

    useEffect(() => {
        let cancelled = false
        fetchPublic<{ macro?: Record<string, Node> }>("macro_snapshot.json").then((r) => {
            if (cancelled) return
            setM((r.ok && (r.data.macro || (r.data as unknown as Record<string, Node>))) || {})
        })
        return () => {
            cancelled = true
        }
    }, [])

    return (
        <div className="af-mkt" style={{ fontFamily: FONT }}>
            {ITEMS.map(({ key, name, unit }) => {
                const n = m[key] || {}
                const v = typeof n.value === "number" ? n.value : null
                const cp = typeof n.change_pct === "number" ? n.change_pct : typeof n.change_percent === "number" ? n.change_percent : null
                const col = cp == null ? c.faint : cp > 0 ? c.up : cp < 0 ? c.down : c.faint
                const sign = cp != null && cp > 0 ? "+" : ""
                return (
                    <div key={key} style={{ background: c.card, borderRadius: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.05)", padding: "9px 11px", display: "flex", alignItems: "center", gap: 9, minWidth: 0 }}>
                        {n.sparkline && n.sparkline.length > 1 ? <Spark data={n.sparkline} color={col} /> : null}
                        <div style={{ minWidth: 0, flex: 1 }}>
                            <div style={{ fontSize: 10.5, fontWeight: 700, color: c.sub, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{name}</div>
                            <div style={{ fontSize: 14, fontWeight: 800, color: c.ink, letterSpacing: "-0.3px", ...NUM }}>
                                {v != null ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}{unit || ""}
                            </div>
                            <div style={{ fontSize: 10.5, fontWeight: 800, color: col, ...NUM }}>{cp != null ? `${sign}${cp.toFixed(2)}%` : ""}</div>
                        </div>
                    </div>
                )
            })}
        </div>
    )
}
