import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useMemo, useState } from "react"
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


function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

function fetchPortfolioJson(url: string): Promise<any> {
    return fetch(bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit" })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((txt) => JSON.parse(txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
}

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"
const UP = "#22C55E"
const DOWN = "#EF4444"
const BG = "#000"
const CARD = "#111"
const BORDER = "#222"
const MUTED = "#8B95A1"
const ACCENT = "#B5FF19"

type MarketId = "KRX" | "NAS" | "NYS" | "HKS" | "TSE" | "SHS" | "SZS"
type MarketSession = "open" | "pre" | "closed"

const MARKET_IDS: MarketId[] = ["KRX", "NAS", "NYS", "HKS", "TSE", "SHS", "SZS"]

const MARKET_META: Record<MarketId, {
    name: string
    flag: string
    impact: string
    city: string
    timezone: string
    openHour: number
    closeHour: number
    lat: number
    lon: number
}> = {
    KRX: { name: "한국", flag: "🇰🇷", impact: "아시아 개장 선행", city: "서울", timezone: "Asia/Seoul", openHour: 9, closeHour: 15.5, lat: 37.56, lon: 126.97 },
    NAS: { name: "나스닥", flag: "🇺🇸", impact: "글로벌 기술주 선행", city: "뉴욕", timezone: "America/New_York", openHour: 9.5, closeHour: 16, lat: 40.71, lon: -74.0 },
    NYS: { name: "뉴욕", flag: "🇺🇸", impact: "대형주·산업재 벤치마크", city: "뉴욕", timezone: "America/New_York", openHour: 9.5, closeHour: 16, lat: 40.71, lon: -74.0 },
    HKS: { name: "홍콩", flag: "🇭🇰", impact: "중국 대리 지표", city: "홍콩", timezone: "Asia/Hong_Kong", openHour: 9.5, closeHour: 16, lat: 22.32, lon: 114.17 },
    TSE: { name: "도쿄", flag: "🇯🇵", impact: "아시아 선행·환율 연동", city: "도쿄", timezone: "Asia/Tokyo", openHour: 9, closeHour: 15, lat: 35.68, lon: 139.76 },
    SHS: { name: "상해", flag: "🇨🇳", impact: "중국 A주·원자재", city: "상하이", timezone: "Asia/Shanghai", openHour: 9.5, closeHour: 15, lat: 31.23, lon: 121.47 },
    SZS: { name: "심천", flag: "🇨🇳", impact: "중국 기술·성장주", city: "선전", timezone: "Asia/Shanghai", openHour: 9.5, closeHour: 15, lat: 22.54, lon: 114.06 },
}

type SubTab = "volume" | "updown" | "surge" | "cap"

const SUB_TABS: { id: SubTab; label: string }[] = [
    { id: "updown", label: "등락률" },
    { id: "volume", label: "거래량" },
    { id: "surge", label: "급증" },
    { id: "cap", label: "시총" },
]

function parseMarkets(raw: string): MarketId[] {
    const parsed = (raw || "")
        .split(",")
        .map((s) => s.trim().toUpperCase())
        .filter((s): s is MarketId => MARKET_IDS.includes(s as MarketId))
    return parsed.length > 0 ? parsed : ["KRX", "NAS", "NYS", "TSE", "HKS", "SHS", "SZS"]
}

function formatLocalTime(timezone: string, now: number): string {
    try {
        return new Intl.DateTimeFormat("ko-KR", {
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
            timeZone: timezone,
        }).format(new Date(now))
    } catch {
        return "—"
    }
}

function marketSession(timezone: string, openHour: number, closeHour: number, now: number): MarketSession {
    const local = new Date(new Date(now).toLocaleString("en-US", { timeZone: timezone }))
    const hour = local.getHours() + local.getMinutes() / 60
    if (hour >= openHour && hour <= closeHour) return "open"
    if (hour >= openHour - 1 && hour < openHour) return "pre"
    return "closed"
}

function sessionCountDownLabel(timezone: string, openHour: number, closeHour: number, now: number): string {
    const local = new Date(new Date(now).toLocaleString("en-US", { timeZone: timezone }))
    const minsNow = local.getHours() * 60 + local.getMinutes()
    const openMins = Math.round(openHour * 60)
    const closeMins = Math.round(closeHour * 60)

    const toLabel = (mins: number): string => {
        const h = Math.floor(mins / 60)
        const m = mins % 60
        return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`
    }

    if (minsNow >= openMins && minsNow <= closeMins) {
        return `마감 - ${toLabel(closeMins - minsNow)}`
    }
    if (minsNow < openMins) {
        return `개장 - ${toLabel(openMins - minsNow)}`
    }
    return `개장 - ${toLabel(24 * 60 - minsNow + openMins)}`
}

function sessionBadge(session: MarketSession): { icon: string; label: string; color: string } {
    if (session === "open") return { icon: "●", label: "개장", color: "#22C55E" }
    if (session === "pre") return { icon: "◐", label: "개장 전", color: "#F59E0B" }
    return { icon: "○", label: "마감", color: "#64748B" }
}

function fallbackMarketId(rec: any): MarketId {
    const tickerYf = String(rec?.ticker_yf || "").toUpperCase()
    const market = String(rec?.market || "").toUpperCase()
    const currency = String(rec?.currency || "").toUpperCase()
    if (currency === "KRW" || /KOSPI|KOSDAQ|KRX|코스피|코스닥/.test(market)) return "KRX"
    if (/\.HK$/.test(tickerYf) || /HKG|HONG KONG|HKEX/.test(market)) return "HKS"
    if (/\.T$/.test(tickerYf) || /TSE|TOKYO|JPX|JAPAN/.test(market)) return "TSE"
    if (/\.SZ$/.test(tickerYf) || /SZS|SHENZHEN/.test(market)) return "SZS"
    if (/\.SS$/.test(tickerYf) || /SHS|SSE|SHANGHAI/.test(market)) return "SHS"
    if (currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/.test(market)) return "NAS"
    return "NAS"
}

function fmtPct(v: any): string {
    const n = Number(v)
    if (!Number.isFinite(n)) return "—"
    return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`
}

function fmtVol(v: any): string {
    const n = Number(v)
    if (!Number.isFinite(n) || n === 0) return "—"
    if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`
    if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`
    if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`
    return n.toLocaleString()
}

function fmtPrice(v: any): string {
    const n = Number(v)
    if (!Number.isFinite(n)) return "—"
    return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function macroPoint(macro: any, keys: string[]): { key: string; value: number; pct: number } | null {
    for (const k of keys) {
        const d = macro?.[k]
        const value = Number(d?.value)
        if (Number.isFinite(value)) {
            return { key: k, value, pct: Number(d?.change_pct) }
        }
    }
    return null
}

function fmtIndexValue(v: number): string {
    if (!Number.isFinite(v)) return "—"
    if (Math.abs(v) >= 1000) return v.toLocaleString("en-US", { maximumFractionDigits: 2 })
    return v.toLocaleString("en-US", { maximumFractionDigits: 4 })
}

/* ── Mercator projection & TopoJSON decoder ── */

const MAP_W = 960
const MAP_H = 540
const MAP_DATA_URL = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json"
const _D2R = Math.PI / 180
const _MLAT = 85.05113

function _clamp(v: number, lo: number, hi: number) { return v < lo ? lo : v > hi ? hi : v }

function _merc(lng: number, lat: number, s: number, ox: number, oy: number): [number, number] {
    const p = _clamp(lat, -_MLAT, _MLAT) * _D2R
    return [s * lng * _D2R + ox, -s * Math.log(Math.tan(Math.PI / 4 + p / 2)) + oy]
}

function _getProj(w: number, h: number): [number, number, number] {
    const s = w / (2 * Math.PI)
    const yN = -s * Math.log(Math.tan(Math.PI / 4 + (72 * _D2R) / 2))
    const yS = -s * Math.log(Math.tan(Math.PI / 4 + (-56 * _D2R) / 2))
    return [s, w / 2, h / 2 - (yN + yS) / 2]
}

function _decArcs(t: any): number[][][] {
    const tf = t.transform
    if (!tf) return t.arcs
    const sx = tf.scale[0], sy = tf.scale[1], dx = tf.translate[0], dy = tf.translate[1]
    return t.arcs.map((a: number[][]) => {
        let x = 0, y = 0
        return a.map((p: number[]) => { x += p[0]; y += p[1]; return [x * sx + dx, y * sy + dy] })
    })
}

function _resolveRing(idx: number[], arcs: number[][][]): number[][] {
    const out: number[][] = []
    for (const i of idx) {
        const a = i >= 0 ? arcs[i] : arcs[~i].slice().reverse()
        for (let j = out.length > 0 ? 1 : 0; j < a.length; j++) out.push(a[j])
    }
    return out
}

function _extractFeatures(t: any): { id: string; type: string; coords: any }[] {
    const arcs = _decArcs(t)
    const gs = t.objects.countries?.geometries
    if (!gs) return []
    return gs.map((g: any) => {
        let c: any = null
        if (g.type === "Polygon") c = g.arcs.map((r: number[]) => _resolveRing(r, arcs))
        else if (g.type === "MultiPolygon") c = g.arcs.map((p: number[][]) => p.map((r: number[]) => _resolveRing(r, arcs)))
        return { id: String(g.id ?? ""), type: g.type, coords: c }
    })
}

function _ringToPath(ring: number[][], s: number, ox: number, oy: number, W: number): string {
    if (ring.length < 3) return ""
    const pts = ring.map(c => _merc(c[0], c[1], s, ox, oy))
    const thr = W / 3
    const segs: [number, number][][] = []
    let cur: [number, number][] = [pts[0]]
    for (let i = 1; i < pts.length; i++) {
        if (Math.abs(pts[i][0] - pts[i - 1][0]) > thr) {
            if (cur.length >= 2) segs.push(cur)
            cur = [pts[i]]
        } else cur.push(pts[i])
    }
    if (cur.length >= 2) segs.push(cur)
    if (segs.length === 0) return ""
    if (segs.length === 1 && segs[0].length === pts.length)
        return segs[0].map((p, i) => (i === 0 ? "M" : "L") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join("") + "Z"
    return segs.map(seg => seg.map((p, i) => (i === 0 ? "M" : "L") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join("")).join("")
}

function _buildPath(type: string, coords: any, s: number, ox: number, oy: number, W: number): string {
    if (!coords) return ""
    if (type === "Polygon") return coords.map((r: number[][]) => _ringToPath(r, s, ox, oy, W)).join("")
    if (type === "MultiPolygon") return coords.map((p: number[][][]) => p.map((r: number[][]) => _ringToPath(r, s, ox, oy, W)).join("")).join("")
    return ""
}

function _buildGraticule(s: number, ox: number, oy: number, w: number, h: number): string {
    const parts: string[] = []
    for (let lat = -60; lat <= 60; lat += 30) {
        const segs: string[] = []
        for (let lng = -180; lng <= 180; lng += 3) {
            const [x, y] = _merc(lng, lat, s, ox, oy)
            if (x >= 0 && x <= w && y >= 0 && y <= h)
                segs.push((segs.length === 0 ? "M" : "L") + x.toFixed(1) + "," + y.toFixed(1))
        }
        if (segs.length > 1) parts.push(segs.join(""))
    }
    for (let lng = -180; lng <= 180; lng += 30) {
        const segs: string[] = []
        for (let lat = -80; lat <= 80; lat += 2) {
            const [x, y] = _merc(lng, lat, s, ox, oy)
            if (x >= 0 && x <= w && y >= 0 && y <= h)
                segs.push((segs.length === 0 ? "M" : "L") + x.toFixed(1) + "," + y.toFixed(1))
        }
        if (segs.length > 1) parts.push(segs.join(""))
    }
    return parts.join(" ")
}

const MAP_PROJ = _getProj(MAP_W, MAP_H)

const MAP_MARKET_POS: Record<MarketId, { x: number; y: number }> = (() => {
    const [S, OX, OY] = MAP_PROJ
    const pos = {} as Record<MarketId, { x: number; y: number }>
    for (const id of MARKET_IDS) {
        const m = MARKET_META[id]
        const [x, y] = _merc(m.lon, m.lat, S, OX, OY)
        let fx = x, fy = y
        if (id === "NYS") { fx -= 14; fy += 16 }
        if (id === "SZS") { fx -= 24; fy += 16 }
        pos[id] = { x: fx, y: fy }
    }
    return pos
})()

export default function GlobalMarketsPanel({
    portfolioUrl = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    defaultMarkets = "KRX,NAS,NYS,TSE,HKS,SHS,SZS",
    refreshInterval = 300000,
}: {
    portfolioUrl?: string
    defaultMarkets?: string
    refreshInterval?: number
}) {
    const [portfolio, setPortfolio] = useState<any>(null)
    const [loading, setLoading] = useState(true)
    const [fetchError, setFetchError] = useState(false)
    const [retryKey, setRetryKey] = useState(0)
    const [activeMarket, setActiveMarket] = useState<MarketId>("KRX")
    const [subTab, setSubTab] = useState<SubTab>("updown")
    const [nowTick, setNowTick] = useState<number>(Date.now())
    const [ledOn, setLedOn] = useState(true)
    const [mapFeatures, setMapFeatures] = useState<any[] | null>(null)
    const [mapError, setMapError] = useState(false)

    const markets = useMemo<MarketId[]>(() => {
        return parseMarkets(defaultMarkets)
    }, [defaultMarkets])

    useEffect(() => {
        if (markets.includes(activeMarket)) return
        setActiveMarket(markets[0] || "KRX")
    }, [markets, activeMarket])

    useEffect(() => {
        const iv = setInterval(() => setNowTick(Date.now()), 30_000)
        return () => clearInterval(iv)
    }, [])

    useEffect(() => {
        const iv = setInterval(() => setLedOn((v) => !v), 700)
        return () => clearInterval(iv)
    }, [])

    useEffect(() => {
        let dead = false
        fetch(MAP_DATA_URL)
            .then((r) => { if (!r.ok) throw 0; return r.json() })
            .then((t) => { if (!dead) setMapFeatures(_extractFeatures(t)) })
            .catch(() => { if (!dead) setMapError(true) })
        return () => { dead = true }
    }, [])

    useEffect(() => {
        if (!portfolioUrl) return
        let cancelled = false
        setLoading(true)
        setFetchError(false)
        const load = () => {
            fetchPortfolioJson(portfolioUrl)
                .then((d) => { if (!cancelled) { setPortfolio(d); setLoading(false); setFetchError(false) } })
                .catch(() => { if (!cancelled) { setLoading(false); setFetchError(true) } })
        }
        load()
        const iv = refreshInterval > 0 ? setInterval(load, refreshInterval) : undefined
        return () => { cancelled = true; if (iv) clearInterval(iv) }
    }, [portfolioUrl, refreshInterval, retryKey])

    const countryPaths = useMemo(() => {
        if (!mapFeatures) return []
        const [S, OX, OY] = MAP_PROJ
        return mapFeatures
            .filter(f => f.id !== "010")
            .map(f => {
                const d = _buildPath(f.type, f.coords, S, OX, OY, MAP_W)
                return d ? { id: f.id, pathD: d } : null
            })
            .filter(Boolean) as { id: string; pathD: string }[]
    }, [mapFeatures])

    const mapGraticule = useMemo(() => {
        const [S, OX, OY] = MAP_PROJ
        return _buildGraticule(S, OX, OY, MAP_W, MAP_H)
    }, [])

    const kisOverseas = portfolio?.kis_overseas_market || {}
    const kisDomestic = portfolio?.kis_market || {}
    const macro = portfolio?.macro || {}
    const newsItems = kisOverseas.news || []
    const breakingItems = kisOverseas.breaking || []

    const groupedFallback = useMemo<Record<MarketId, any[]>>(() => {
        const recs: any[] = portfolio?.recommendations || []
        const bucket: Record<MarketId, any[]> = {
            KRX: [],
            NAS: [],
            NYS: [],
            HKS: [],
            TSE: [],
            SHS: [],
            SZS: [],
        }
        recs.forEach((r) => {
            const id = fallbackMarketId(r)
            bucket[id].push(r)
        })
        Object.keys(bucket).forEach((k) => {
            const id = k as MarketId
            bucket[id] = bucket[id]
                .sort((a, b) => (b?.technical?.price_change_pct || b?.change_pct || 0) - (a?.technical?.price_change_pct || a?.change_pct || 0))
                .slice(0, 20)
        })
        return bucket
    }, [portfolio])

    const mktData = activeMarket === "KRX" ? {} : (kisOverseas[activeMarket] || {})

    const listForTab = useMemo(() => {
        switch (subTab) {
            case "updown": return mktData.updown_rank || groupedFallback[activeMarket] || []
            case "volume": return mktData.volume_rank || groupedFallback[activeMarket] || []
            case "surge": return mktData.volume_surge || groupedFallback[activeMarket] || []
            case "cap": return mktData.market_cap || groupedFallback[activeMarket] || []
            default: return []
        }
    }, [subTab, mktData, groupedFallback, activeMarket])

    const getField = (item: any, tab: SubTab): { name: string; ticker: string; price: string; pct: string; vol: string } => {
        const name = item.hts_kor_isnm || item.name || item.symb || "—"
        const ticker = item.symb || item.mksc_shrn_iscd || ""
        const price = fmtPrice(item.last || item.stck_prpr || item.ovrs_nmix_prpr || item.price || 0)
        const pct = fmtPct(item.rate || item.prdy_ctrt || item.fluc_rt || 0)
        const vol = fmtVol(item.tvol || item.acml_vol || item.tamt || item.volume || 0)
        return { name, ticker, price, pct, vol }
    }
    const hasKisData = Object.keys(kisOverseas).length > 0
    const hasAnyRows = markets.some((id) => {
        if (id === "KRX") return groupedFallback.KRX.length > 0 || !!(kisDomestic.kospi || kisDomestic.kosdaq)
        const d = kisOverseas[id] || {}
        const rows = d.updown_rank || d.volume_rank || d.volume_surge || d.market_cap
        return (Array.isArray(rows) && rows.length > 0) || (groupedFallback[id] || []).length > 0
    })

    const marketCards = useMemo(() => {
        return markets.map((id) => {
            const meta = MARKET_META[id]
            const tzTime = formatLocalTime(meta.timezone, nowTick)
            const session = marketSession(meta.timezone, meta.openHour, meta.closeHour, nowTick)
            const rows =
                id === "KRX"
                    ? groupedFallback.KRX
                    : (kisOverseas[id]?.updown_rank || kisOverseas[id]?.volume_rank || groupedFallback[id] || [])
            const top = rows[0]
            const topPct = Number(top?.rate || top?.prdy_ctrt || top?.fluc_rt || top?.technical?.price_change_pct || top?.change_pct || 0)
            const countDown = sessionCountDownLabel(meta.timezone, meta.openHour, meta.closeHour, nowTick)
            return {
                id,
                meta,
                tzTime,
                session,
                countDown,
                topName: top ? (top.hts_kor_isnm || top.name || top.ticker || top.symb || "—") : "데이터 없음",
                topPct,
                count: rows.length,
            }
        })
    }, [markets, nowTick, kisOverseas, groupedFallback])

    const orderedMarketCards = useMemo(() => {
        const rank = (s: MarketSession) => (s === "open" ? 0 : s === "pre" ? 1 : 2)
        return [...marketCards].sort((a, b) => {
            const r = rank(a.session) - rank(b.session)
            if (r !== 0) return r
            return Math.abs(b.topPct) - Math.abs(a.topPct)
        })
    }, [marketCards])

    const orderedMarketIds = useMemo(() => orderedMarketCards.map((c) => c.id), [orderedMarketCards])
    const activeMapCard = useMemo(
        () => marketCards.find((c) => c.id === activeMarket) || orderedMarketCards[0] || null,
        [marketCards, orderedMarketCards, activeMarket],
    )

    const marketInfoBadges = useMemo(() => {
        return markets.map((id) => {
            const idxFromMacro =
                id === "KRX"
                    ? macroPoint(macro, ["kospi", "kosdaq"])
                    : id === "NAS"
                      ? macroPoint(macro, ["nasdaq", "sp500"])
                      : id === "NYS"
                        ? macroPoint(macro, ["dji", "sp500"])
                        : id === "TSE"
                          ? macroPoint(macro, ["nikkei"])
                          : id === "HKS"
                            ? macroPoint(macro, ["hsi", "sse"])
                            : macroPoint(macro, ["sse"])

            const idxFromKisDomestic =
                id === "KRX" && (kisDomestic.kospi || kisDomestic.kosdaq)
                    ? {
                        value: Number(kisDomestic.kospi?.bstp_nmix_prpr || kisDomestic.kosdaq?.bstp_nmix_prpr || NaN),
                        pct: Number(kisDomestic.kospi?.bstp_nmix_prdy_ctrt || kisDomestic.kosdaq?.bstp_nmix_prdy_ctrt || NaN),
                        label: kisDomestic.kospi ? "KOSPI" : "KOSDAQ",
                    }
                    : null

            const indexLabel =
                idxFromKisDomestic?.label ||
                (id === "KRX"
                    ? "KOSPI"
                    : id === "NAS"
                      ? "NASDAQ"
                      : id === "NYS"
                        ? "DOW"
                        : id === "TSE"
                          ? "NIKKEI"
                          : id === "HKS"
                            ? "HANG SENG"
                            : "SSE")

            const indexValue = idxFromKisDomestic?.value ?? idxFromMacro?.value ?? NaN
            const indexPct = idxFromKisDomestic?.pct ?? idxFromMacro?.pct ?? NaN

            const fxPoint =
                id === "KRX"
                    ? macroPoint(macro, ["usd_krw"])
                    : id === "TSE"
                      ? macroPoint(macro, ["usd_jpy"])
                      : id === "HKS"
                        ? macroPoint(macro, ["usd_hkd", "eur_usd"])
                        : id === "SHS" || id === "SZS"
                          ? macroPoint(macro, ["usd_cnh", "usd_cny", "eur_usd"])
                          : macroPoint(macro, ["eur_usd"])

            const fxLabel =
                id === "KRX"
                    ? "USD/KRW"
                    : id === "TSE"
                      ? "USD/JPY"
                      : id === "HKS"
                        ? "USD/HKD"
                        : id === "SHS" || id === "SZS"
                          ? "USD/CNH"
                          : "EUR/USD"

            return {
                id,
                indexLabel,
                indexValue,
                indexPct,
                fxLabel,
                fxValue: fxPoint?.value ?? NaN,
            }
        })
    }, [markets, macro, kisDomestic])

    if (loading) {
        return (
            <div style={wrapStyle}>
                <div style={{ ...flexCenter, padding: 30 }}>
                    <span style={{ color: ACCENT, fontSize: 13, fontWeight: 600, fontFamily: font }}>글로벌 마켓 데이터 로딩 중…</span>
                </div>
            </div>
        )
    }

    if (fetchError && !portfolio) {
        return (
            <div style={wrapStyle}>
                <div style={{ ...flexCenter, padding: 30 }}>
                    <span style={{ color: MUTED, fontSize: 13, fontFamily: font }}>데이터를 불러올 수 없습니다</span>
                    <span style={{ color: C.textTertiary, fontSize: 10, fontFamily: font, marginTop: 4 }}>네트워크 또는 CORS 설정을 확인하세요</span>
                    <button
                        type="button"
                        onClick={() => setRetryKey(k => k + 1)}
                        style={{
                            marginTop: 12, padding: "8px 18px", borderRadius: 8,
                            background: ACCENT, color: "#000", border: "none",
                            fontSize: 12, fontWeight: 700, cursor: "pointer", fontFamily: font,
                        }}
                    >
                        다시 시도
                    </button>
                </div>
            </div>
        )
    }

    if (!hasAnyRows) {
        return (
            <div style={wrapStyle}>
                <div style={{ ...flexCenter, padding: 30 }}>
                    <span style={{ color: MUTED, fontSize: 13, fontFamily: font }}>글로벌 마켓 데이터 준비 중</span>
                    <span style={{ color: C.textTertiary, fontSize: 10, fontFamily: font, marginTop: 4 }}>
                        KIS 파이프라인 또는 추천 데이터 확인 후 다시 시도해 주세요
                    </span>
                    <button
                        type="button"
                        onClick={() => setRetryKey((k) => k + 1)}
                        style={{
                            marginTop: 12, padding: "6px 14px", borderRadius: 8,
                            background: "transparent", color: ACCENT, border: `1px solid ${ACCENT}`,
                            fontSize: 11, fontWeight: 700, cursor: "pointer", fontFamily: font,
                        }}
                    >
                        새로고침
                    </button>
                </div>
            </div>
        )
    }

    return (
        <div style={wrapStyle}>
            {/* 헤더 */}
            <div style={{ padding: "14px 16px", borderBottom: `1px solid ${BORDER}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                    <div style={{ color: C.textPrimary, fontSize: 16, fontWeight: 800 }}>글로벌 마켓</div>
                    <div style={{ color: MUTED, fontSize: 10, marginTop: 2 }}>
                        {hasKisData ? "KIS Open API" : "추천 데이터 폴백"} · {kisOverseas.timestamp ? new Date(kisOverseas.timestamp).toLocaleTimeString("ko-KR") : "—"}
                    </div>
                </div>
                <div style={{ color: ACCENT, fontSize: 11, fontWeight: 700 }}>
                    {markets.length}개 시장
                </div>
            </div>

            {/* 지도형 글로벌 보드 */}
            <div style={{ padding: "12px 16px", borderBottom: `1px solid ${BORDER}` }}>
                <div style={{ position: "relative", width: "100%", paddingBottom: `${(MAP_H / MAP_W) * 100}%` }}>
                <div
                    style={{
                        position: "absolute",
                        inset: 0,
                        borderRadius: 14,
                        border: `1px solid ${BORDER}`,
                        background:
                            "radial-gradient(120% 90% at 50% 0%, rgba(181,255,25,0.2) 0%, rgba(181,255,25,0.07) 35%, #090909 100%)",
                        overflow: "hidden",
                    }}
                >
                    <div style={{ position: "absolute", top: 8, left: 10, color: "#A3A3A3", fontSize: 9, fontWeight: 700, letterSpacing: "0.04em", zIndex: 2 }}>
                        WORLD MARKET MAP
                    </div>
                    {!mapFeatures && !mapError && (
                        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1 }}>
                            <span style={{ color: C.textTertiary, fontSize: 9 }}>지도 로딩 중…</span>
                        </div>
                    )}
                    {mapError && (
                        <div style={{ position: "absolute", bottom: 8, right: 10, zIndex: 1 }}>
                            <span style={{ color: C.textTertiary, fontSize: 8 }}>지도 데이터 로드 실패</span>
                        </div>
                    )}
                    <svg
                        width="100%"
                        height="100%"
                        viewBox={`0 0 ${MAP_W} ${MAP_H}`}
                        preserveAspectRatio="xMidYMid meet"
                        style={{ display: "block", position: "absolute", inset: 0 }}
                    >
                        <rect width={MAP_W} height={MAP_H} fill="transparent" />
                        {mapGraticule && (
                            <path d={mapGraticule} fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="0.5" vectorEffect="non-scaling-stroke" />
                        )}
                        {countryPaths.map((c) => (
                            <path key={c.id} d={c.pathD} fill="#252525" stroke="#444" strokeWidth="0.5" vectorEffect="non-scaling-stroke" />
                        ))}
                        {orderedMarketCards.map((card) => {
                            const active = card.id === activeMarket
                            const sb = sessionBadge(card.session)
                            const pos = MAP_MARKET_POS[card.id]
                            return (
                                <g key={card.id} onClick={() => setActiveMarket(card.id)} style={{ cursor: "pointer" }}>
                                    {active && <circle cx={pos.x} cy={pos.y} r={22} fill="none" stroke={ACCENT} strokeWidth={1.5} opacity={0.25} />}
                                    <circle cx={pos.x} cy={pos.y} r={active ? 14 : 10} fill="rgba(10,10,10,0.92)" stroke={active ? ACCENT : "#3A3A3A"} strokeWidth={1} />
                                    <circle cx={pos.x} cy={pos.y} r={active ? 5.5 : 4} fill={sb.color} opacity={card.session === "open" ? (ledOn ? 1 : 0.35) : 0.9} />
                                    <circle cx={pos.x} cy={pos.y} r={22} fill="transparent" />
                                </g>
                            )
                        })}
                        {orderedMarketCards.map((card) => {
                            if (card.id !== activeMarket) return null
                            const pos = MAP_MARKET_POS[card.id]
                            const label = `${card.meta.flag} ${card.meta.city}`
                            return (
                                <g key={`lbl-${card.id}`} style={{ pointerEvents: "none" }}>
                                    <line x1={pos.x} y1={pos.y - 14} x2={pos.x} y2={pos.y - 28} stroke={ACCENT} strokeWidth={0.8} opacity={0.5} />
                                    <rect x={pos.x - 45} y={pos.y - 50} width={90} height={22} rx={6} fill="rgba(0,0,0,0.82)" stroke={ACCENT} strokeWidth={0.8} />
                                    <text x={pos.x} y={pos.y - 35} textAnchor="middle" fill="#fff" fontSize="11" fontWeight="700" fontFamily={font}>
                                        {label}
                                    </text>
                                </g>
                            )
                        })}
                    </svg>
                </div>
                </div>
                {activeMapCard && (
                    <div
                        style={{
                            marginTop: 8,
                            background: "rgba(17,17,17,0.88)",
                            border: `1px solid ${BORDER}`,
                            borderRadius: 10,
                            padding: "8px 10px",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: 10,
                        }}
                    >
                        <div style={{ minWidth: 0 }}>
                            <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 800 }}>
                                {activeMapCard.meta.flag} {activeMapCard.meta.city} · {activeMapCard.meta.name}
                            </div>
                            <div style={{ color: MUTED, fontSize: 10, marginTop: 2 }}>
                                {activeMapCard.tzTime} · {activeMapCard.count}종목 · {activeMapCard.countDown}
                            </div>
                        </div>
                        <div style={{ color: activeMapCard.topPct >= 0 ? UP : DOWN, fontSize: 12, fontWeight: 800, flexShrink: 0 }}>
                            {fmtPct(activeMapCard.topPct)}
                        </div>
                    </div>
                )}
                <div style={{ marginTop: 6, color: "#777", fontSize: 9 }}>
                    지도의 점을 클릭하거나 아래 시장 카드를 눌러 선택하세요.
                </div>
                <div style={{ marginTop: 10, overflowX: "auto" }}>
                    <div
                        style={{
                            display: "grid",
                            gridAutoFlow: "column",
                            gridTemplateRows: "repeat(3, minmax(0,1fr))",
                            gridAutoColumns: "minmax(150px, 1fr)",
                            gap: 8,
                            minWidth: `${Math.max(2, Math.ceil(marketInfoBadges.length / 3)) * 160}px`,
                            paddingBottom: 2,
                        }}
                    >
                    {orderedMarketIds.map((id) => {
                        const b = marketInfoBadges.find((x) => x.id === id)
                        if (!b) return null
                        const active = b.id === activeMarket
                        const card = marketCards.find((x) => x.id === b.id)
                        const sb = sessionBadge(card?.session || "closed")
                        return (
                            <button
                                key={`info-${b.id}`}
                                type="button"
                                onClick={() => setActiveMarket(b.id)}
                                style={{
                                    border: active ? `1px solid ${ACCENT}` : `1px solid ${BORDER}`,
                                    background: active ? "rgba(181,255,25,0.08)" : CARD,
                                    borderRadius: 10,
                                    padding: "8px 9px",
                                    textAlign: "left",
                                    cursor: "pointer",
                                    fontFamily: font,
                                }}
                            >
                                <div style={{ color: C.textPrimary, fontSize: 11, fontWeight: 800, marginBottom: 3 }}>
                                    {MARKET_META[b.id].flag} {MARKET_META[b.id].name}
                                </div>
                                <div style={{ color: MUTED, fontSize: 10, display: "flex", justifyContent: "space-between", gap: 8 }}>
                                    <span>{b.indexLabel}</span>
                                    <span style={{ color: C.textPrimary }}>{fmtIndexValue(b.indexValue)}</span>
                                </div>
                                <div style={{ color: MUTED, fontSize: 10, display: "flex", justifyContent: "space-between", gap: 8, marginTop: 2 }}>
                                    <span>{b.fxLabel}</span>
                                    <span style={{ color: C.textPrimary }}>
                                        {Number.isFinite(b.fxValue) ? fmtIndexValue(b.fxValue) : "—"}
                                    </span>
                                </div>
                                <div style={{ marginTop: 3, color: Number(b.indexPct) >= 0 ? UP : DOWN, fontSize: 10, fontWeight: 700 }}>
                                    {fmtPct(b.indexPct)}
                                </div>
                                <div style={{ marginTop: 2, color: sb.color, fontSize: 9, fontWeight: 700, display: "inline-flex", alignItems: "center", gap: 4 }}>
                                    <span
                                        style={{
                                            width: 7,
                                            height: 7,
                                            borderRadius: "50%",
                                            display: "inline-block",
                                            background: sb.color,
                                            boxShadow: `0 0 8px ${sb.color}`,
                                            opacity: card?.session === "open" ? (ledOn ? 1 : 0.35) : 0.9,
                                            transition: "opacity 140ms linear",
                                        }}
                                    />
                                    {sb.label}
                                </div>
                                <div style={{ marginTop: 1, color: "#777", fontSize: 9 }}>
                                    {card?.countDown || "—"}
                                </div>
                            </button>
                        )
                    })}
                    </div>
                </div>
            </div>

            {/* 국내 시장 요약 */}
            {(kisDomestic.kospi || kisDomestic.kosdaq) && (
                <div style={{ padding: "10px 16px", borderBottom: `1px solid ${BORDER}`, display: "flex", gap: 12 }}>
                    {kisDomestic.kospi && (() => {
                        const k = kisDomestic.kospi
                        const pct = Number(k.bstp_nmix_prdy_ctrt || 0)
                        return (
                            <div style={{ flex: 1, background: CARD, borderRadius: 10, padding: "10px 12px", border: `1px solid ${BORDER}` }}>
                                <div style={{ color: MUTED, fontSize: 10, marginBottom: 4 }}>코스피</div>
                                <div style={{ color: C.textPrimary, fontSize: 15, fontWeight: 800 }}>{Number(k.bstp_nmix_prpr || 0).toLocaleString()}</div>
                                <div style={{ color: pct >= 0 ? UP : DOWN, fontSize: 11, fontWeight: 700 }}>{fmtPct(pct)}</div>
                            </div>
                        )
                    })()}
                    {kisDomestic.kosdaq && (() => {
                        const k = kisDomestic.kosdaq
                        const pct = Number(k.bstp_nmix_prdy_ctrt || 0)
                        return (
                            <div style={{ flex: 1, background: CARD, borderRadius: 10, padding: "10px 12px", border: `1px solid ${BORDER}` }}>
                                <div style={{ color: MUTED, fontSize: 10, marginBottom: 4 }}>코스닥</div>
                                <div style={{ color: C.textPrimary, fontSize: 15, fontWeight: 800 }}>{Number(k.bstp_nmix_prpr || 0).toLocaleString()}</div>
                                <div style={{ color: pct >= 0 ? UP : DOWN, fontSize: 11, fontWeight: 700 }}>{fmtPct(pct)}</div>
                            </div>
                        )
                    })()}
                </div>
            )}

            {/* 시장 탭 */}
            <div style={{ display: "flex", overflowX: "auto", borderBottom: `1px solid ${BORDER}`, padding: "0 12px" }}>
                {orderedMarketIds.map((mId) => {
                    const meta = MARKET_META[mId]
                    if (!meta) return null
                    const active = mId === activeMarket
                    return (
                        <button
                            key={mId}
                            type="button"
                            onClick={() => setActiveMarket(mId)}
                            style={{
                                padding: "10px 14px",
                                background: "none",
                                border: "none",
                                borderBottom: active ? `2px solid ${ACCENT}` : "2px solid transparent",
                                cursor: "pointer",
                                fontFamily: font,
                                whiteSpace: "nowrap",
                            }}
                        >
                            <div style={{ fontSize: 12, fontWeight: active ? 800 : 600, color: active ? "#fff" : MUTED }}>
                                {meta.flag} {meta.name}
                            </div>
                        </button>
                    )
                })}
            </div>

            {/* 시장 설명 */}
            <div style={{ padding: "8px 16px", borderBottom: `1px solid ${BORDER}` }}>
                <div style={{ color: MUTED, fontSize: 10, lineHeight: 1.4 }}>
                    {MARKET_META[activeMarket]?.impact || ""} · {MARKET_META[activeMarket]?.city} {formatLocalTime(MARKET_META[activeMarket]?.timezone, nowTick)}
                </div>
            </div>

            {/* 서브 탭 */}
            <div style={{ display: "flex", gap: 6, padding: "8px 16px", borderBottom: `1px solid ${BORDER}` }}>
                {SUB_TABS.map((st) => (
                    <button
                        key={st.id}
                        type="button"
                        onClick={() => setSubTab(st.id)}
                        style={{
                            padding: "6px 12px",
                            borderRadius: 8,
                            border: `1px solid ${st.id === subTab ? ACCENT : BORDER}`,
                            background: st.id === subTab ? "rgba(181,255,25,0.1)" : "transparent",
                            color: st.id === subTab ? ACCENT : MUTED,
                            fontSize: 11,
                            fontWeight: 700,
                            cursor: "pointer",
                            fontFamily: font,
                        }}
                    >
                        {st.label}
                    </button>
                ))}
            </div>

            {/* 리스트 */}
            <div style={{ flex: 1, overflowY: "auto", padding: "8px 16px" }}>
                {listForTab.length === 0 ? (
                    <div style={{ color: MUTED, fontSize: 12, textAlign: "center", padding: 20 }}>
                        데이터 없음
                    </div>
                ) : (
                    listForTab.slice(0, 20).map((item: any, i: number) => {
                        const { name, ticker, price, pct, vol } = getField(item, subTab)
                        const pctVal = Number(item.rate || item.prdy_ctrt || item.fluc_rt || 0)
                        return (
                            <div
                                key={`${ticker}-${i}`}
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: 10,
                                    padding: "10px 0",
                                    borderBottom: i < listForTab.length - 1 ? `1px solid ${BORDER}` : "none",
                                }}
                            >
                                <div style={{ width: 24, color: MUTED, fontSize: 11, fontWeight: 700, textAlign: "right", flexShrink: 0 }}>
                                    {i + 1}
                                </div>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                        {name}
                                    </div>
                                    <div style={{ color: MUTED, fontSize: 10, marginTop: 2 }}>
                                        {ticker} · Vol {vol}
                                    </div>
                                </div>
                                <div style={{ textAlign: "right", flexShrink: 0 }}>
                                    <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 700 }}>{price}</div>
                                    <div style={{ color: pctVal >= 0 ? UP : DOWN, fontSize: 11, fontWeight: 700 }}>{pct}</div>
                                </div>
                            </div>
                        )
                    })
                )}
            </div>

            {/* 뉴스 */}
            {(newsItems.length > 0 || breakingItems.length > 0) && (
                <div style={{ borderTop: `1px solid ${BORDER}`, padding: "12px 16px", maxHeight: 200, overflowY: "auto" }}>
                    <div style={{ color: ACCENT, fontSize: 10, fontWeight: 800, marginBottom: 8 }}>해외 뉴스</div>
                    {breakingItems.slice(0, 3).map((n: any, i: number) => (
                        <div key={`brk-${i}`} style={{ marginBottom: 6, fontSize: 11, lineHeight: 1.4 }}>
                            <span style={{ color: "#EF4444", fontWeight: 700, marginRight: 4 }}>속보</span>
                            <span style={{ color: C.textPrimary }}>{n.hts_pbnt_titl_cntt || n.title || "—"}</span>
                            <span style={{ color: MUTED, marginLeft: 4 }}>{n.data_dt || ""}</span>
                        </div>
                    ))}
                    {newsItems.slice(0, 5).map((n: any, i: number) => (
                        <div key={`nws-${i}`} style={{ marginBottom: 6, fontSize: 11, lineHeight: 1.4 }}>
                            <span style={{ color: C.textPrimary }}>{n.hts_pbnt_titl_cntt || n.title || "—"}</span>
                            <span style={{ color: MUTED, marginLeft: 4 }}>{n.data_dt || ""}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}

GlobalMarketsPanel.defaultProps = {
    portfolioUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    defaultMarkets: "KRX,NAS,NYS,TSE,HKS,SHS,SZS",
    refreshInterval: 300000,
}

addPropertyControls(GlobalMarketsPanel, {
    portfolioUrl: { type: ControlType.String, title: "portfolio.json URL", defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json" },
    defaultMarkets: { type: ControlType.String, title: "시장 목록 (콤마 구분)", defaultValue: "KRX,NAS,NYS,TSE,HKS,SHS,SZS" },
    refreshInterval: { type: ControlType.Number, title: "갱신 주기(ms)", defaultValue: 300000, min: 0, step: 10000 },
})

const wrapStyle: CSSProperties = {
    width: "100%",
    height: "100%",
    minHeight: 400,
    background: BG,
    borderRadius: 20,
    border: `1px solid ${BORDER}`,
    overflow: "hidden",
    fontFamily: font,
    boxSizing: "border-box",
    display: "flex",
    flexDirection: "column",
}

const flexCenter: CSSProperties = {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    textAlign: "center",
}
