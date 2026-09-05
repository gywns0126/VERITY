"use client"
// StockSearch — 종목 검색 (오퍼레이터). 모든 흐름의 입구. 공개 알파네스트 디자인.
// universe_search.json(공개 사실 목록) 클라 필터. 선택 시 verity-ticker 이벤트 발신 →
//   StockFactsPanel/리포트가 수신. (기존 컨벤션 정합, RULE 11)
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

export default function StockSearch({ placeholder = "종목명·티커 검색", floating = false }: { placeholder?: string; floating?: boolean }) {
    const dark = useDark()
    const c = palette(dark)
    const [universe, setUniverse] = useState<Stock[]>([])
    const [query, setQuery] = useState("")
    const [idx, setIdx] = useState(-1)   // 키보드 탐색 (토스 검색 문법: 상하 이동·Enter 선택·ESC 지우기)
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
        setIdx(-1)
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

    function Row({ item, k, active }: { item: Stock; k: string; active?: boolean }) {
        const isUS = item.market === "US"
        return (
            <button
                type="button"
                key={k}
                id={`af-search-option-${k}`}
                role="option"
                aria-selected={Boolean(active)}
                onClick={() => select(item)}
                style={{ display: "flex", width: "100%", border: "none", fontFamily: FONT, textAlign: "left", alignItems: "center", justifyContent: "space-between", padding: "9px 11px", borderRadius: 10, cursor: "pointer", gap: 8, background: active ? hover : "transparent" }}
                onMouseEnter={(e) => { e.currentTarget.style.background = hover }}
                onMouseLeave={(e) => { e.currentTarget.style.background = active ? hover : "transparent" }}
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
            </button>
        )
    }

    // floating = 커맨드바 모드: 결과를 입력창 아래 절대배치 드롭다운으로 (레이아웃 밀림 0).
    const resultsBox = results.length > 0 ? (
        <div
            id="af-search-results"
            role="listbox"
            aria-label="종목 검색 결과"
            style={{
                background: c.card,
                borderRadius: 14,
                boxShadow: floating ? "0 8px 28px rgba(0,0,0,0.16)" : "0 1px 3px rgba(0,0,0,0.05)",
                padding: 6,
                display: "flex",
                flexDirection: "column",
                gap: 2,
                ...(floating
                    ? { position: "absolute" as const, top: "calc(100% + 6px)", left: 0, right: 0, zIndex: 60, maxHeight: 420, overflowY: "auto" as const }
                    : { marginTop: 8 }),
            }}
        >
            {results.map((it, i) => <Row key={(it.ticker || "") + i} item={it} k={(it.ticker || "") + i} active={i === idx} />)}
            <div style={{ display: "flex", gap: 12, padding: "7px 11px 3px", borderTop: `1px solid ${c.line}`, marginTop: 4 }}>
                {([["Enter", "선택"], ["상하", "탐색"], ["ESC", "지우기"]] as Array<[string, string]>).map(([k, v]) => (
                    <span key={k} style={{ fontSize: 9.5, color: c.faint }}>
                        <span style={{ background: c.hi, borderRadius: 4, padding: "1px 5px", fontWeight: 700, color: c.sub }}>{k}</span> {v}
                    </span>
                ))}
            </div>
        </div>
    ) : null

    return (
        <div style={{ fontFamily: FONT, width: "100%", boxSizing: "border-box", position: floating ? "relative" : "static" }}>
            <input
                id="af-search"
                role="combobox"
                aria-label="종목 검색"
                aria-autocomplete="list"
                aria-expanded={results.length > 0}
                aria-controls="af-search-results"
                aria-activedescendant={idx >= 0 && results[idx] ? `af-search-option-${results[idx].ticker}${idx}` : undefined}
                value={query}
                onChange={(e) => { setQuery(e.target.value); setIdx(-1) }}
                onKeyDown={(e) => {
                    if (e.key === "ArrowDown") { e.preventDefault(); setIdx((v) => Math.min(results.length - 1, v + 1)) }
                    else if (e.key === "ArrowUp") { e.preventDefault(); setIdx((v) => Math.max(-1, v - 1)) }
                    else if (e.key === "Enter") { const pick = idx >= 0 ? results[idx] : results[0]; if (pick) select(pick) }
                    else if (e.key === "Escape") { setQuery(""); setIdx(-1); (e.target as HTMLInputElement).blur() }
                }}
                placeholder={placeholder}
                style={{ width: "100%", boxSizing: "border-box", background: inputBg, color: c.ink, border: "none", borderRadius: floating ? 10 : 12, padding: floating ? "9px 13px" : "13px 15px", fontSize: floating ? 13.5 : 15, fontFamily: FONT, outline: "none" }}
            />
            {resultsBox}
            {!floating && results.length === 0 && recent.length > 0 ? (
                <div style={{ marginTop: 10 }}>
                    <div style={{ fontSize: 11, color: c.faint, marginBottom: 7, paddingLeft: 2 }}>최근 검색</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {recent.map((it, i) =>
                            it ? (
                                <button type="button" key={(it.ticker || "") + i} onClick={() => select(it)} style={{ border: "none", fontFamily: FONT, fontSize: 12, color: c.ink, background: inputBg, borderRadius: 999, padding: "6px 11px", cursor: "pointer" }}>
                                    {it.name || it.ticker}
                                </button>
                            ) : null
                        )}
                    </div>
                </div>
            ) : null}
        </div>
    )
}
