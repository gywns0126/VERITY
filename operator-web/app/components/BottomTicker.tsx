"use client"
// BottomTicker — 하단 고정 매크로 티커 (v2 터미널). 공개 사실만.
import { useEffect, useState } from "react"
import { useDark, palette, FONT, NUM } from "@/lib/theme"
import { fetchPublic } from "@/lib/api"

const KEYS: Array<[string, string, string?]> = [
    ["usd_krw", "달러환율", "원"], ["nasdaq", "나스닥"], ["sp500", "S&P 500"],
    ["sox", "필라델피아 반도체"], ["kospi", "코스피"], ["kosdaq", "코스닥"], ["vix", "VIX"],
]

type Node = { value?: number; change_pct?: number; change_percent?: number }

export default function BottomTicker() {
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
        <div className="af-bticker" style={{ position: "sticky", bottom: 0, zIndex: 30, display: "flex", alignItems: "center", gap: 22, padding: "9px 18px", background: c.card, boxShadow: "0 -1px 3px rgba(0,0,0,0.05)", overflowX: "auto", whiteSpace: "nowrap", fontFamily: FONT, flexShrink: 0 }}>
            {KEYS.map(([key, name, unit]) => {
                const n = m[key] || {}
                const v = typeof n.value === "number" ? n.value : null
                const cp = typeof n.change_pct === "number" ? n.change_pct : typeof n.change_percent === "number" ? n.change_percent : null
                const col = cp == null ? c.faint : cp > 0 ? c.up : cp < 0 ? c.down : c.faint
                const sign = cp != null && cp > 0 ? "+" : ""
                return (
                    <span key={key} style={{ fontSize: 11.5, color: c.sub }}>
                        {name} <b style={{ color: c.ink, fontWeight: 700, ...NUM }}>{v != null ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}{unit || ""}</b>{" "}
                        <span style={{ color: col, ...NUM }}>{cp != null ? `${sign}${cp.toFixed(2)}%` : ""}</span>
                    </span>
                )
            })}
            <span style={{ fontSize: 10, color: c.faint }}>전일 종가(T+1) · 사실</span>
        </div>
    )
}
