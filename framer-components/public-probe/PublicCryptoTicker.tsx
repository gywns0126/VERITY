import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * 실시간 코인 — AlphaNest 공개. 마켓보드 카드 디자인 그대로 + Binance 무인증 실시간 연동.
 *
 * 🚨 시세 재배포 컴플라이언스 (2026-07-15):
 *   · 데이터 = Binance 무인증 "Market Data Only" 공개 엔드포인트 (REST 시드 + WebSocket 실시간 + klines 스파크).
 *     "API key 불필요, 공개 시장데이터만". 브라우저가 Binance 직접 연결 = 우리 서버 릴레이 아님.
 *   · ⚠️ OKX·업비트·빗썸은 재배포/표시 명시 금지 → 미사용. Binance = 비상업·무광고 전제. 어트리뷰션 유지.
 *   · 값·등락 = 실시간(WS). 스파크 = 30일 일봉(klines, 마운트 1회) — 보드 30일 추세선과 동일 문법.
 * 🚨 RULE 7 — 사실(가격·등락)만. KR 색 관례(상승 빨강/하락 파랑) = 마켓보드 통일. 다크모드 자가감지.
 */

// 마켓보드(PublicMarketBoard)와 동일 팔레트.
const LIGHT = { bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#6b7684", faint: "#8b95a1", line: "#eef1f4", up: "#f04452", down: "#3182f6", flat: "#8b95a1", live: "#0ca678" }
const DARK = { bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#252b34", up: "#f04452", down: "#5b9bff", flat: "#828d9b", live: "#34e08a" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const REST_BASE = "https://data-api.binance.vision/api/v3/ticker/24hr"
const KLINE_BASE = "https://data-api.binance.vision/api/v3/klines"
const WS_BASE = "wss://data-stream.binance.vision/stream?streams="

const COINS = [
    { sym: "BTCUSDT", name: "비트코인" },
    { sym: "ETHUSDT", name: "이더리움" },
    { sym: "XRPUSDT", name: "리플" },
    { sym: "SOLUSDT", name: "솔라나" },
    { sym: "DOGEUSDT", name: "도지코인" },
]

type Row = { price: number; chg: number }

function readBodyDark(): boolean {
    try {
        const _lsPref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (_lsPref === "dark") return true
        if (_lsPref === "light") return false
        if (typeof document !== "undefined" && document.body) {
            const a = document.body.dataset.framerTheme
            if (a === "dark") return true
            if (a === "light") return false
        }
        if (typeof localStorage !== "undefined") {
            const s = localStorage.getItem("verity_theme")
            if (s === "dark") return true
            if (s === "light") return false
        }
        if (typeof window !== "undefined" && window.matchMedia) return window.matchMedia("(prefers-color-scheme: dark)").matches
    } catch (e) {}
    return false
}
function fmtPrice(v: number): string {
    if (!isFinite(v) || v <= 0) return "—"
    if (v >= 1000) return v.toLocaleString("en-US", { maximumFractionDigits: 0 })
    if (v >= 1) return v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    return v.toLocaleString("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 4 })
}

// 마켓보드 Spark 컴포넌트 동일 replicate (40×24, 라인 + 하단 그라데이션).
function Spark({ data, color, w, h }: { data: number[]; color: string; w: number; h: number }) {
    if (!data || data.length < 2) return null
    const min = Math.min(...data), max = Math.max(...data), rng = (max - min) || 1
    const pad = 2
    const pts = data.map((v, i) => `${((i / (data.length - 1)) * w).toFixed(1)},${(h - pad - ((v - min) / rng) * (h - pad * 2)).toFixed(1)}`)
    const line = pts.join(" ")
    const area = `${line} ${w.toFixed(1)},${h} 0,${h}`
    const gid = "vct-" + color.replace(/[^a-z0-9]/gi, "")
    return (
        <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: "block", flexShrink: 0 }}>
            <defs>
                <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={color} stopOpacity={0.22} />
                    <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
            </defs>
            <polygon points={area} fill={`url(#${gid})`} />
            <polyline points={line} fill="none" stroke={color} strokeWidth={1.4} vectorEffect="non-scaling-stroke" />
        </svg>
    )
}

const SAMPLE: Record<string, Row> = {
    BTCUSDT: { price: 64286, chg: 2.32 }, ETHUSDT: { price: 1878, chg: 5.55 },
    XRPUSDT: { price: 2.41, chg: 0.58 }, SOLUSDT: { price: 77.36, chg: 1.6 }, DOGEUSDT: { price: 0.3821, chg: -1.04 },
}
const SAMPLE_SPARK: Record<string, number[]> = {}
COINS.forEach((c) => { const b = SAMPLE[c.sym].price; SAMPLE_SPARK[c.sym] = Array.from({ length: 30 }, (_, i) => b * (1 + Math.sin(i / 4) * 0.03 + (i / 30) * (SAMPLE[c.sym].chg / 100))) })

// 🎨 페이지 이동 다크 번쩍임 제거(2026-07-20): 첫 마운트만 라이트(SSG/첫방문 매칭·stuck 방지) → 이후 마운트는 실제 테마 즉시.
let __anHyd = false
function anReadDark(): boolean {
    if (typeof document === "undefined") return false
    if (!__anHyd) {
        __anHyd = true
        return false
    }
    const h = document.documentElement ? document.documentElement.dataset.anTheme : null
    if (h === "dark") return true
    if (h === "light") return false
    return !!(document.body && document.body.dataset.framerTheme === "dark")
}


export default function PublicCryptoTicker(props: { width?: number; dark?: boolean; minCard?: number }) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (onCanvas ? !!props.dark : anReadDark()))
    const [rows, setRows] = useState<Record<string, Row>>(onCanvas ? SAMPLE : {})
    const [spark, setSpark] = useState<Record<string, number[]>>(onCanvas ? SAMPLE_SPARK : {})
    const [live, setLive] = useState(false)
    const [flash, setFlash] = useState<Record<string, 1 | -1>>({})
    const flashTimers = useRef<Record<string, any>>({})

    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT
    const minCard = props.minCard || 160

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    // REST 시드 (값·등락)
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        const syms = encodeURIComponent(JSON.stringify(COINS.map((c) => c.sym)))
        fetch(`${REST_BASE}?symbols=${syms}`, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((arr) => {
                if (!alive || !Array.isArray(arr)) return
                const next: Record<string, Row> = {}
                arr.forEach((t: any) => { next[t.symbol] = { price: Number(t.lastPrice), chg: Number(t.priceChangePercent) } })
                setRows((prev) => ({ ...prev, ...next }))
            })
            .catch(() => {})
        return () => { alive = false }
    }, [onCanvas])

    // 스파크 (30일 일봉 klines, 코인별 1회)
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        COINS.forEach((c) => {
            fetch(`${KLINE_BASE}?symbol=${c.sym}&interval=1d&limit=30`, { cache: "no-store" })
                .then((r) => (r.ok ? r.json() : null))
                .then((k) => {
                    if (!alive || !Array.isArray(k)) return
                    const closes = k.map((row: any) => Number(row[4])).filter((x: number) => isFinite(x))
                    if (closes.length >= 2) setSpark((prev) => ({ ...prev, [c.sym]: closes }))
                })
                .catch(() => {})
        })
        return () => { alive = false }
    }, [onCanvas])

    // WebSocket 실시간 (값·등락)
    useEffect(() => {
        if (onCanvas || typeof WebSocket === "undefined") return
        let ws: WebSocket | null = null
        let retry: any = null
        let tries = 0
        let disposed = false

        const bump = (sym: string, dir: 1 | -1) => {
            setFlash((f) => ({ ...f, [sym]: dir }))
            clearTimeout(flashTimers.current[sym])
            flashTimers.current[sym] = setTimeout(() => setFlash((f) => { const n = { ...f }; delete n[sym]; return n }), 450)
        }
        const connect = () => {
            if (disposed) return
            const streams = COINS.map((c) => c.sym.toLowerCase() + "@ticker").join("/")
            try {
                ws = new WebSocket(WS_BASE + streams)
                ws.onopen = () => { setLive(true); tries = 0 }
                ws.onclose = () => { setLive(false); if (!disposed) schedule() }
                ws.onerror = () => { try { ws && ws.close() } catch (e) {} }
                ws.onmessage = (ev) => {
                    try {
                        const m = JSON.parse(ev.data)
                        const d = m && m.data
                        if (!d || !d.s) return
                        const price = Number(d.c), chg = Number(d.P)
                        setRows((prev) => {
                            const old = prev[d.s]
                            if (old && price !== old.price) bump(d.s, price > old.price ? 1 : -1)
                            return { ...prev, [d.s]: { price, chg } }
                        })
                    } catch (e) {}
                }
            } catch (e) { schedule() }
        }
        const schedule = () => { if (disposed || tries >= 8) return; const delay = Math.min(15000, 1000 * Math.pow(2, tries)); tries++; retry = setTimeout(connect, delay) }
        connect()
        return () => {
            disposed = true
            clearTimeout(retry)
            Object.values(flashTimers.current).forEach((t) => clearTimeout(t))
            if (ws) { try { ws.onclose = null; ws.close() } catch (e) {} }
        }
    }, [onCanvas])

    const wrap: CSSProperties = { width: "100%", maxWidth: props.width || 720, margin: "0 auto", fontFamily: FONT, color: C.ink, padding: "0 14px", boxSizing: "border-box" }

    return (
        <div style={wrap}>
            <style>{`@keyframes vctUp{0%{background:${C.up}1f}100%{background:${C.card}}}@keyframes vctDn{0%{background:${C.down}1f}100%{background:${C.card}}}@keyframes vctPulse{0%,100%{opacity:1}50%{opacity:.35}}`}</style>

            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                <div style={{ fontSize: 17, fontWeight: 800, letterSpacing: "-0.4px" }}>실시간 코인</div>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 5, marginLeft: "auto", fontSize: 10.5, fontWeight: 700, color: live ? C.live : C.faint }}>
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: live ? C.live : C.faint, animation: live ? "vctPulse 1.4s ease-in-out infinite" : "none" }} />
                    {live ? "실시간 · Binance" : "연결 중"}
                </span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: `repeat(auto-fill, minmax(${minCard}px, 1fr))`, gap: 8 }}>
                {COINS.map((coin) => {
                    const r = rows[coin.sym]
                    const cp = r ? r.chg : NaN
                    const col = !isFinite(cp) ? C.flat : cp > 0 ? C.up : cp < 0 ? C.down : C.flat
                    const sign = isFinite(cp) && cp > 0 ? "+" : ""
                    const sp = spark[coin.sym]
                    const fl = flash[coin.sym]
                    return (
                        <div key={coin.sym}
                            style={{ background: C.card, borderRadius: 11, padding: "8px 10px", boxShadow: "0 1px 2px rgba(0,0,0,0.04)", display: "flex", alignItems: "center", gap: 9, minWidth: 0, animation: fl === 1 ? "vctUp .45s ease-out" : fl === -1 ? "vctDn .45s ease-out" : "none" }}>
                            {sp && sp.length >= 2 ? <Spark data={sp} color={col} w={40} h={24} /> : <span style={{ width: 40, height: 24, flexShrink: 0 }} />}
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 11, fontWeight: 700, color: C.sub, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{coin.name}</div>
                                <div style={{ fontSize: 15, fontWeight: 800, color: C.ink, letterSpacing: "-0.3px", marginTop: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontVariantNumeric: "tabular-nums" }}>{r ? "$" + fmtPrice(r.price) : "—"}</div>
                                <div style={{ fontSize: 11, fontWeight: 800, color: col, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontVariantNumeric: "tabular-nums" }}>{isFinite(cp) ? `${sign}${cp.toFixed(2)}%` : "—"}</div>
                            </div>
                        </div>
                    )
                })}
            </div>

            <div style={{ fontSize: 10, color: C.faint, fontWeight: 600, marginTop: 9, lineHeight: 1.5 }}>
                가격 USDT · 24h 등락 · 실시간 · 스파크 30일 · 데이터{" "}
                <a href="https://www.binance.com" target="_blank" rel="noopener noreferrer" style={{ color: C.faint, fontWeight: 700, textDecoration: "underline" }}>Binance</a>
            </div>
        </div>
    )
}

addPropertyControls(PublicCryptoTicker, {
    width: { type: ControlType.Number, title: "Max Width", defaultValue: 720 },
    minCard: { type: ControlType.Number, title: "카드 최소폭", defaultValue: 160, min: 120, max: 280, step: 10, unit: "px" },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})
