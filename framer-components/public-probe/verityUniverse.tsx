// VERITY 종목 universe 단일 출처 — 4 검색창(nav / report / decision / watchlist) 공유 모듈.
// 목적: universe URL·매칭·최근목록을 한 곳에 모아 "각자 따로 노는" 4 검색창을 연동.
// universe 교체(예: 풀 6000)는 여기 STOCK_UNIVERSE_URL 한 줄만 바꾸면 4개 전부 반영.
import { useEffect, useState } from "react"

// 단일 출처 URL (Blob). 풀 universe 발행 후 여기만 교체.
export const STOCK_UNIVERSE_URL =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_report_public.json"
export const US_UNIVERSE_URL =
    "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_stock_report_public.json"

export const RECENTS_KEY = "verity_recent_tickers"
export const LAST_TICKER_KEY = "verity_last_ticker"
const CACHE_KEY = "verity_universe_cache_v2"

// 종목 매칭 (코드·영문명·한글명 부분일치). 4 검색창 동일 동작.
export function matchStocks(universe: any[], query: string, limit: number = 12): any[] {
    const s = (query || "").trim().toLowerCase()
    const raw = (query || "").trim()
    if (!s || !Array.isArray(universe)) return []
    return universe
        .filter(
            (x) =>
                String(x.ticker || "").toLowerCase().includes(s) ||
                String(x.name || "").toLowerCase().includes(s) ||
                String((x as any).name_ko || "").includes(raw)
        )
        .slice(0, limit)
}

// 최근 본 종목 — 단일 키 공유 (한 검색창에서 고르면 다른 창 최근목록에도 반영).
export function readRecents(): any[] {
    if (typeof window === "undefined") return []
    try {
        const a = JSON.parse(window.localStorage.getItem(RECENTS_KEY) || "[]")
        return Array.isArray(a) ? a.filter((x) => x && x.t) : []
    } catch {
        return []
    }
}

export function pushRecent(ticker: string, name?: string, cap: number = 12): void {
    if (typeof window === "undefined" || !ticker) return
    try {
        window.localStorage.setItem(LAST_TICKER_KEY, ticker)
        const cur = readRecents().filter((x) => String(x.t) !== String(ticker))
        cur.unshift({ t: ticker, n: name || ticker })
        window.localStorage.setItem(RECENTS_KEY, JSON.stringify(cur.slice(0, cap)))
    } catch {
        /* private mode / quota */
    }
}

// universe 1회 fetch + sessionStorage 캐시 (4 검색창이 각자 4번 fetch → 1번 공유).
// urls 지정 시 그 목록을, 아니면 [krUrl, usUrl]. 머지 후 ticker dedup(먼저 등장 우선). onCanvas=true 면 fetch 안 함.
export function useStockUniverse(opts?: {
    onCanvas?: boolean
    krUrl?: string
    usUrl?: string
    urls?: string[]
}): any[] {
    const onCanvas = !!(opts && opts.onCanvas)
    const krUrl = (opts && opts.krUrl) || STOCK_UNIVERSE_URL
    const usUrl = opts && "usUrl" in opts ? opts.usUrl : US_UNIVERSE_URL
    const list = opts && opts.urls ? opts.urls : [krUrl, usUrl]
    const key = list.filter(Boolean).join("|")
    const [universe, setUniverse] = useState<any[]>([])

    useEffect(() => {
        if (onCanvas) return
        let alive = true

        try {
            const c = window.sessionStorage.getItem(CACHE_KEY + ":" + key)
            if (c) {
                const arr = JSON.parse(c)
                if (Array.isArray(arr) && arr.length) setUniverse(arr)
            }
        } catch {
            /* ignore */
        }

        const urls = key.split("|").filter(Boolean)
        Promise.all(
            urls.map((u) =>
                fetch(u, { cache: "no-store" })
                    .then((r) => (r.ok ? r.json() : null))
                    .catch(() => null)
            )
        ).then((docs) => {
            if (!alive) return
            const merged: any[] = []
            for (const d of docs) {
                const a = d && (Array.isArray(d) ? d : d.stocks)
                if (Array.isArray(a)) merged.push(...a)
            }
            // ticker dedup (트랙 간 중복 — 먼저 등장 우선)
            const seen: Record<string, boolean> = {}
            const deduped = merged.filter((x) => {
                const tk = String((x && x.ticker) || "")
                if (!tk || seen[tk]) return false
                seen[tk] = true
                return true
            })
            if (deduped.length) {
                setUniverse(deduped)
                try {
                    window.sessionStorage.setItem(CACHE_KEY + ":" + key, JSON.stringify(deduped))
                } catch {
                    /* quota */
                }
            }
        })
        return () => {
            alive = false
        }
    }, [key, onCanvas])

    return universe
}
