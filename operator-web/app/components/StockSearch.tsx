"use client"
// StockSearch — 종목 검색 (오퍼레이터). 모든 흐름의 입구. 공개 알파네스트 디자인.
// universe_search.json(공개 사실 목록) 클라 필터. 선택 시 verity-ticker 이벤트 발신 →
//   TriSynthesisPanel/리포트가 수신. (기존 컨벤션 정합, RULE 11)
import { useEffect, useState } from "react"
import { useDark, palette, FONT, NUM } from "@/lib/theme"
import { fetchPublic } from "@/lib/api"

const RECENT_KEY = "verity_recent_tickers"
const LAST_KEY = "verity_last_ticker"

type Stock = { ticker: string; name?: string; name_ko?: string; kw?: string; market?: string }

function loadRecent(): Stock[] {
    try {
        const raw = localStorage.getItem(RECENT_KEY)
        if (!raw) return []
        const arr = JSON.parse(raw)
        return Array.isArray(arr) ? arr.slice(0, 8) : []
    } catch {
        return []
    }
}

export default function StockSearch({ placeholder = "종목명·티커 검색" }: { placeholder?: string }) {
    const dark = useDark()
    const c = palette(dark)
    const [universe, setUniverse] = useState<Stock[]>([])
    const [query, setQuery] = useState("")
    const [recent, setRecent] = useState<Stock[]>([])

    useEffect(() => {
        setRecent(loadRecent())
        let cancelled = false
        fetchPublic<{ stocks?: Stock[] }>("universe_search.json").then((r) => {
            if (cancelled) return
            setUniverse(r.ok && r.data.stocks ? r.data.stocks : [])
        })
        return () => {
            cancelled = true
        }
    }, [])

    function select(item: Stock) {
        try {
            localStorage.setItem(LAST_KEY, item.ticker)
            const next = [item, ...recent.filter((x) => x && x.ticker !== item.ticker)].slice(0, 8)
            localStorage.setItem(RECENT_KEY, JSON.stringify(next))
            setRecent(next)
        } catch {}
        try {
            const url = new URL(window.location.href)
            url.searchParams.set("q", item.ticker)
            window.history.replaceState({}, "", url.toString())
        } catch {}
        try {
            window.dispatchEvent(new CustomEvent("verity-ticker", { detail: { ticker: item.ticker, item } }))
        } catch {}
        setQuery("")
    }

    const norm = query.trim().toLowerCase()
    const results: Stock[] = []
    if (norm.length >= 1) {
        for (const it of universe) {
            if (!it) continue
            const hay = `${it.ticker || ""} ${it.name || ""} ${it.name_ko || ""} ${it.kw || ""}`.toLowerCase()
            if (hay.indexOf(norm) >= 0) {
                results.push(it)
                if (results.length >= 12) break
            }
        }
    }

    const inputBg = dark ? c.bg : c.track
    const hover = dark ? "rgba(169,155,255,0.14)" : "rgba(108,92,231,0.08)"

    function Row({ item, k }: { item: Stock; k: string }) {
        const isUS = item.market === "US"
        return (
            <div
                key={k}
                onClick={() => select(item)}
                style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "9px 11px", borderRadius: 10, cursor: "pointer", gap: 8 }}
                onMouseEnter={(e) => { e.currentTarget.style.background = hover }}
                onMouseLeave={(e) => { e.currentTarget.style.background = "transparent" }}
            >
                <div style={{ display: "flex", alignItems: "baseline", gap: 8, minWidth: 0 }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: c.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {item.name || item.ticker}
                    </span>
                    <span style={{ fontSize: 11, color: c.faint, ...NUM }}>{item.ticker}</span>
                </div>
                <span style={{ fontSize: 10, fontWeight: 700, color: isUS ? c.down : c.vt, background: isUS ? c.downS : c.vtS, borderRadius: 6, padding: "2px 6px" }}>
                    {isUS ? "US" : "KR"}
                </span>
            </div>
        )
    }

    return (
        <div style={{ fontFamily: FONT, width: "100%", boxSizing: "border-box" }}>
            <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={placeholder}
                style={{ width: "100%", boxSizing: "border-box", background: inputBg, color: c.ink, border: "none", borderRadius: 12, padding: "13px 15px", fontSize: 15, fontFamily: FONT, outline: "none" }}
            />
            {results.length > 0 ? (
                <div style={{ marginTop: 8, background: c.card, borderRadius: 14, boxShadow: "0 1px 3px rgba(0,0,0,0.05)", padding: 6, display: "flex", flexDirection: "column", gap: 2 }}>
                    {results.map((it, i) => <Row key={(it.ticker || "") + i} item={it} k={(it.ticker || "") + i} />)}
                </div>
            ) : null}
            {results.length === 0 && recent.length > 0 ? (
                <div style={{ marginTop: 10 }}>
                    <div style={{ fontSize: 11, color: c.faint, marginBottom: 7, paddingLeft: 2 }}>최근 검색</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {recent.map((it, i) =>
                            it ? (
                                <span key={(it.ticker || "") + i} onClick={() => select(it)} style={{ fontSize: 12, color: c.ink, background: inputBg, borderRadius: 999, padding: "6px 11px", cursor: "pointer" }}>
                                    {it.name || it.ticker}
                                </span>
                            ) : null
                        )}
                    </div>
                </div>
            ) : null}
        </div>
    )
}
