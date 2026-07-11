import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 코인 히트맵 — TIDE 크립토 공개 표면.
 *
 * 박스 크기 = 시가총액. 색 = 24h(또는 7d) 변동률(사실) — 글로벌 관례 green=상승/red=하락.
 * 데이터 = crypto_universe.json (CoinGecko 시총상위 50, 무인증). 탭하면 CoinGecko 코인 페이지.
 *
 * 🚨 RULE 7: 자체 점수·등급 0 — 시총/변동%/sparkline 사실만 (StockHeatmap의 Brain grade dot 제거).
 * 🚨 RULE 1 무관: KIS·국내증권 비참조. CoinGecko 링크만.
 * 다크모드 = body[data-framer-theme] 자가감지(AlphaNest 패턴). 로딩 = shimmer 스켈레톤. onCanvas = 데모.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", up: "#15c47e", down: "#f04452", warn: "#ff9500", accent: "#0ca678", tileInk: "#191f28",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", up: "#3ddc97", down: "#ff6b76", warn: "#ffb454", accent: "#3ddc97", tileInk: "#ffffff",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const MONO: CSSProperties = { fontFamily: "'SF Mono','JetBrains Mono','Menlo',monospace", fontVariantNumeric: "tabular-nums" }
const BLOB = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"

function readBodyDark(): boolean {
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}
function fmtPct(n: any): string {
    if (n == null || !isFinite(Number(n))) return "—"
    const v = Number(n)
    return (v > 0 ? "+" : "") + v.toFixed(2) + "%"
}
function fmtCap(v: any): string {
    const n = Number(v)
    if (!isFinite(n) || n <= 0) return "—"
    if (n >= 1e12) return "$" + (n / 1e12).toFixed(2) + "T"
    if (n >= 1e9) return "$" + (n / 1e9).toFixed(1) + "B"
    if (n >= 1e6) return "$" + (n / 1e6).toFixed(0) + "M"
    return "$" + n.toLocaleString()
}
function fmtPrice(v: any): string {
    const n = Number(v)
    if (!isFinite(n)) return "—"
    if (n >= 1) return "$" + n.toLocaleString("en-US", { maximumFractionDigits: 2 })
    return "$" + n.toLocaleString("en-US", { maximumFractionDigits: 6 })
}

const DEMO = {
    coins: [
        { id: "bitcoin", symbol: "BTC", name: "Bitcoin", market_cap: 1.29e12, current_price: 64663, change_pct: 0.72, change_pct_7d: -3.8, sparkline: [], fdv_mc_ratio: 1.0, circulating_ratio: 95.5 },
        { id: "ethereum", symbol: "ETH", name: "Ethereum", market_cap: 2.1e11, current_price: 2630, change_pct: 0.67, change_pct_7d: -5.1, sparkline: [], fdv_mc_ratio: 1.0, circulating_ratio: 100 },
        { id: "tether", symbol: "USDT", name: "Tether", market_cap: 1.86e11, current_price: 1, change_pct: 0.0, change_pct_7d: 0.01, sparkline: [], fdv_mc_ratio: 1.0, circulating_ratio: 100 },
        { id: "hyperliquid", symbol: "HYPE", name: "Hyperliquid", market_cap: 8.0e10, current_price: 24, change_pct: 0.8, change_pct_7d: 2.1, sparkline: [], fdv_mc_ratio: 4.3, circulating_ratio: 22.2 },
        { id: "solana", symbol: "SOL", name: "Solana", market_cap: 6.5e10, current_price: 140, change_pct: -1.2, change_pct_7d: 4.3, sparkline: [], fdv_mc_ratio: 1.2, circulating_ratio: 78 },
        { id: "ripple", symbol: "XRP", name: "XRP", market_cap: 3.1e10, current_price: 0.52, change_pct: 1.9, change_pct_7d: -2.0, sparkline: [], fdv_mc_ratio: 1.8, circulating_ratio: 56 },
    ],
}

type Metric = "24h" | "7d" | "dilution"

function alpha(hex: string, a: number): string {
    const h = hex.replace("#", "")
    const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16)
    return `rgba(${r},${g},${b},${a.toFixed(3)})`
}
function boxBg(pct: number | null, up: string, down: string): { bg: string; strong: boolean } {
    if (pct == null || !isFinite(pct)) return { bg: "transparent", strong: false }
    const inten = Math.max(0, Math.min(1, Math.abs(pct) / 8))
    const a = 0.1 + inten * 0.72
    return { bg: alpha(pct >= 0 ? up : down, a), strong: a >= 0.45 }
}
// 희석 색 — FDV/MC overhang(1x=없음, ≥4x=폭탄). 단방향 amber. 높을수록 진함.
function dilutionBg(fdvMc: number | null, warn: string): { bg: string; strong: boolean } {
    if (fdvMc == null || !isFinite(fdvMc) || fdvMc <= 1) return { bg: "transparent", strong: false }
    const inten = Math.max(0, Math.min(1, (fdvMc - 1) / 3))
    const a = 0.12 + inten * 0.7
    return { bg: alpha(warn, a), strong: a >= 0.45 }
}

export default function CryptoHeatmap(props: { dataUrl?: string; dark?: boolean; metric?: Metric }) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT

    const [data, setData] = useState<any>(onCanvas ? DEMO : null)
    const [metric, setMetric] = useState<Metric>(props.metric === "7d" || props.metric === "dilution" ? props.metric : "24h")
    const [hover, setHover] = useState<any>(null)
    const [tip, setTip] = useState({ x: 0, y: 0 })
    const rootRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas) return
        let alive = true
        const url = props.dataUrl || BLOB + "/crypto_universe.json"
        fetch(url)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (alive && d) setData(d) })
            .catch(() => {})
        return () => { alive = false }
    }, [onCanvas, props.dataUrl])

    const coins = useMemo(() => (data && Array.isArray(data.coins) ? data.coins : []), [data])
    const totalCap = useMemo(() => coins.reduce((a: number, c: any) => a + Math.max(Number(c.market_cap) || 0, 1), 0), [coins])
    const colorOf = (c: any) => (metric === "7d" ? c.change_pct_7d : c.change_pct)

    const wrap: CSSProperties = { width: "100%", boxSizing: "border-box", fontFamily: FONT, color: C.ink, background: C.bg, borderRadius: 14, padding: 18, display: "flex", flexDirection: "column", gap: 12, position: "relative" }

    // 로딩 스켈레톤 (시총가중 회색 블록 + shimmer)
    if (!data) {
        const skBase = isDark ? "#222a33" : "#e9edf1"
        const skHi = isDark ? "#2d3742" : "#f3f5f7"
        const W = [30, 18, 16, 12, 14, 10, 12, 8, 10, 8, 9, 7, 8, 6, 9, 7, 6, 8, 6, 7]
        return (
            <div ref={rootRef} style={wrap}>
                <style>{`@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                    {W.map((w, i) => (
                        <div key={i} style={{ flexBasis: `calc(${w}% - 3px)`, flexGrow: w, minWidth: 56, height: 80, borderRadius: 6, background: skBase, backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`, backgroundSize: "800px 100%", animation: "vsrShimmer 1.4s ease-in-out infinite" }} />
                    ))}
                </div>
            </div>
        )
    }

    const upN = coins.filter((c: any) => Number(colorOf(c)) > 0).length
    const downN = coins.filter((c: any) => Number(colorOf(c)) < 0).length

    return (
        <div ref={rootRef} style={wrap} onMouseLeave={() => setHover(null)}>
            {/* 헤더 */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.4px" }}>코인 히트맵</span>
                <span style={{ ...MONO, fontSize: 11.5, color: C.faint, fontWeight: 700 }}>{coins.length}개 · 박스=시총 · {metric === "dilution" ? "색=희석 overhang(FDV/MC)" : "색=" + metric + " 변동"}</span>
                {metric === "dilution" ? (
                    <span style={{ ...MONO, fontSize: 11.5, color: C.warn, fontWeight: 700 }}>희석≥2x {coins.filter((c: any) => Number(c.fdv_mc_ratio) >= 2).length}개</span>
                ) : (
                    <>
                        <span style={{ ...MONO, fontSize: 11.5, color: C.up, fontWeight: 700 }}>▲{upN}</span>
                        <span style={{ ...MONO, fontSize: 11.5, color: C.down, fontWeight: 700 }}>▼{downN}</span>
                    </>
                )}
                <div style={{ marginLeft: "auto", display: "inline-flex", background: C.line, borderRadius: 9, padding: 2 }}>
                    {(["24h", "7d", "dilution"] as Metric[]).map((m) => (
                        <button key={m} onClick={() => setMetric(m)} style={{ border: "none", cursor: "pointer", fontFamily: FONT, fontSize: 12, fontWeight: 700, padding: "5px 11px", borderRadius: 7, background: metric === m ? C.card : "transparent", color: metric === m ? C.ink : C.sub }}>{m === "dilution" ? "희석" : m}</button>
                    ))}
                </div>
            </div>

            {/* 히트맵 그리드 */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                {coins.map((c: any) => {
                    const dil = metric === "dilution"
                    const pct = Number(colorOf(c))
                    const fdvMc = Number(c.fdv_mc_ratio)
                    const weight = Math.max((Math.max(Number(c.market_cap) || 1, 1) / totalCap) * 100, 3)
                    const col = dil ? dilutionBg(isFinite(fdvMc) ? fdvMc : null, C.warn) : boxBg(isFinite(pct) ? pct : null, C.up, C.down)
                    const isHov = hover && hover.id === c.id
                    const txt = col.strong ? C.tileInk : C.ink
                    const fName = Math.min(14, 8 + weight * 0.4)
                    return (
                        <div key={c.id || c.symbol}
                            onMouseEnter={(e) => { setHover(c); setTip({ x: e.clientX, y: e.clientY }) }}
                            onMouseMove={(e) => setTip({ x: e.clientX, y: e.clientY })}
                            onClick={() => { if (!onCanvas && typeof window !== "undefined" && c.id) window.open("https://www.coingecko.com/en/coins/" + encodeURIComponent(c.id), "_blank") }}
                            style={{ flexBasis: `calc(${weight}% - 3px)`, flexGrow: weight, minWidth: 56, height: 80, background: col.bg, borderRadius: 6, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 2, cursor: "pointer", border: isHov ? `1.5px solid ${C.accent}` : "1.5px solid transparent", opacity: hover && !isHov ? 0.6 : 1, overflow: "hidden", padding: 4, boxSizing: "border-box", transition: "border 0.12s, opacity 0.12s" }}>
                            <span style={{ fontSize: fName, fontWeight: 800, color: txt, lineHeight: 1.1, maxWidth: "96%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.symbol}</span>
                            {dil
                                ? (isFinite(fdvMc) && fdvMc > 0 && <span style={{ ...MONO, fontSize: Math.min(12, 7 + weight * 0.3), fontWeight: 700, color: txt }}>{fdvMc.toFixed(1)}x</span>)
                                : (isFinite(pct) && <span style={{ ...MONO, fontSize: Math.min(12, 7 + weight * 0.3), fontWeight: 700, color: txt }}>{fmtPct(pct)}</span>)}
                        </div>
                    )
                })}
            </div>

            {/* 범례 */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", fontSize: 10.5, color: C.faint, fontWeight: 600 }}>
                {metric === "dilution" ? (
                    <>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 12, height: 12, borderRadius: 2, background: C.warn }} /> 미유통 overhang(희석 압력↑)</span>
                        <span style={{ marginLeft: "auto" }}>FDV/MC·유통비율 = 공급 희석 사실(미유통=언락 대기 물량)</span>
                    </>
                ) : (
                    <>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 12, height: 12, borderRadius: 2, background: C.up }} /> 상승</span>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 12, height: 12, borderRadius: 2, background: C.down }} /> 하락</span>
                        <span style={{ marginLeft: "auto" }}>CoinGecko · {metric} 변동률 사실</span>
                    </>
                )}
            </div>

            {/* 호버 툴팁 (viewport-fixed) */}
            {hover && (() => {
                const W = 220
                const winW = typeof window !== "undefined" ? window.innerWidth : 1400
                const left = tip.x + W + 24 > winW ? tip.x - W - 16 : tip.x + 16
                const top = Math.max(8, tip.y - 10)
                return (
                    <div style={{ position: "fixed", left, top, width: W, zIndex: 9999, background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, padding: "11px 13px", boxShadow: "0 8px 26px rgba(0,0,0,0.22)", pointerEvents: "none", fontFamily: FONT }}>
                        <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                            <span style={{ fontSize: 14, fontWeight: 800, color: C.ink }}>{hover.name}</span>
                            <span style={{ ...MONO, fontSize: 11, color: C.faint, fontWeight: 700 }}>{hover.symbol}</span>
                        </div>
                        <div style={{ ...MONO, fontSize: 16, fontWeight: 800, color: C.ink, marginTop: 5 }}>{fmtPrice(hover.current_price)}</div>
                        <div style={{ display: "flex", gap: 12, marginTop: 5 }}>
                            <span style={{ ...MONO, fontSize: 12, fontWeight: 700, color: Number(hover.change_pct) >= 0 ? C.up : C.down }}>24h {fmtPct(hover.change_pct)}</span>
                            <span style={{ ...MONO, fontSize: 12, fontWeight: 700, color: Number(hover.change_pct_7d) >= 0 ? C.up : C.down }}>7d {fmtPct(hover.change_pct_7d)}</span>
                        </div>
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 5 }}>시총 {fmtCap(hover.market_cap)}</div>
                        {(hover.fdv_mc_ratio != null || hover.circulating_ratio != null) && (
                            <div style={{ fontSize: 11, fontWeight: 700, color: Number(hover.fdv_mc_ratio) >= 2 ? C.warn : C.sub, marginTop: 3 }}>
                                {hover.circulating_ratio != null ? "유통 " + hover.circulating_ratio + "%" : ""}{hover.fdv_mc_ratio != null ? " · FDV/MC " + Number(hover.fdv_mc_ratio).toFixed(2) + "x" : ""}
                            </div>
                        )}
                        <div style={{ fontSize: 10, color: C.accent, fontWeight: 800, marginTop: 6 }}>탭 → CoinGecko ›</div>
                    </div>
                )
            })()}
        </div>
    )
}

addPropertyControls(CryptoHeatmap, {
    dataUrl: { type: ControlType.String, title: "데이터 URL", defaultValue: BLOB + "/crypto_universe.json" },
    dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
    metric: { type: ControlType.Enum, title: "색 지표", options: ["24h", "7d", "dilution"], optionTitles: ["24시간", "7일", "희석(FDV/MC)"], defaultValue: "24h" },
})
