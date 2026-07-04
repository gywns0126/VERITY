import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 코인 희석 포렌식 — 코인 AlphaNest 엣지 lead (주식 disclosure_forensics 의 코인판).
 *
 * 랭킹 = FDV/MC overhang(미유통 언락 대기 물량) + 유통비율. 토스·네이버 코인 화면엔 없는 view.
 * 공급 바 = 유통(초록) vs 미유통/언락대기(amber) — 한눈에 "앞으로 풀릴 물량" 사실.
 *
 * 데이터 = crypto_universe.json (CoinGecko 시총상위 50, 무인증). 탭 → CoinGecko 코인 페이지.
 *
 * 🚨 RULE 7: 자체 점수·등급·순위판정 0 — FDV/MC·유통비율·시총 사실만(랭킹=정렬, 평가 아님).
 * 🚨 RULE 6: LLM·서술 합성 0. 결정론 계산만.
 * 🚨 RULE 1 무관: KIS·국내증권 비참조. CoinGecko 링크만.
 * 다크모드 = body[data-framer-theme] 자가감지(AlphaNest 패턴). onCanvas = 데모.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", up: "#15c47e", down: "#f04452", warn: "#ff9500", accent: "#0ca678",
    track: "#eef1f4", lockedBg: "#fff4e3",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", up: "#3ddc97", down: "#ff6b76", warn: "#ffb454", accent: "#3ddc97",
    track: "#222a33", lockedBg: "#2a2113",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const MONO: CSSProperties = { fontFamily: "'SF Mono','JetBrains Mono','Menlo',monospace", fontVariantNumeric: "tabular-nums" }
const BLOB = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"
const CACHE_KEY = "verity_crypto_universe_cache"

function readBodyDark(): boolean {
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}
function fmtCap(v: any): string {
    const n = Number(v)
    if (!isFinite(n) || n <= 0) return "—"
    if (n >= 1e12) return "$" + (n / 1e12).toFixed(2) + "T"
    if (n >= 1e9) return "$" + (n / 1e9).toFixed(1) + "B"
    if (n >= 1e6) return "$" + (n / 1e6).toFixed(0) + "M"
    return "$" + n.toLocaleString()
}
function alpha(hex: string, a: number): string {
    const h = hex.replace("#", "")
    const r = parseInt(h.slice(0, 2), 16), g = parseInt(h.slice(2, 4), 16), b = parseInt(h.slice(4, 6), 16)
    return `rgba(${r},${g},${b},${a.toFixed(3)})`
}

type SortKey = "overhang" | "locked" | "mcap"

const DEMO = {
    collected_at: "demo",
    coins: [
        { id: "hyperliquid", symbol: "HYPE", name: "Hyperliquid", market_cap: 8.0e10, fdv: 3.44e11, fdv_mc_ratio: 4.3, circulating_ratio: 22.2 },
        { id: "worldcoin", symbol: "WLD", name: "Worldcoin", market_cap: 2.1e9, fdv: 2.0e10, fdv_mc_ratio: 9.5, circulating_ratio: 10.5 },
        { id: "ripple", symbol: "XRP", name: "XRP", market_cap: 3.1e10, fdv: 5.2e10, fdv_mc_ratio: 1.8, circulating_ratio: 56 },
        { id: "solana", symbol: "SOL", name: "Solana", market_cap: 6.5e10, fdv: 7.8e10, fdv_mc_ratio: 1.2, circulating_ratio: 78 },
        { id: "bitcoin", symbol: "BTC", name: "Bitcoin", market_cap: 1.29e12, fdv: 1.35e12, fdv_mc_ratio: 1.05, circulating_ratio: 95.5 },
        { id: "ethereum", symbol: "ETH", name: "Ethereum", market_cap: 2.1e11, fdv: 2.1e11, fdv_mc_ratio: 1.0, circulating_ratio: 100 },
    ],
}

function overhangColor(ratio: number, C: typeof LIGHT): string {
    // 단방향 amber — 1x(overhang 없음)=중립, ≥5x=폭탄. RULE7 사실 강도만.
    if (!isFinite(ratio) || ratio <= 1.05) return C.sub
    return C.warn
}

export default function CryptoDilutionForensics(props: { dataUrl?: string; dark?: boolean; sortBy?: SortKey; topN?: number }) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT

    const [data, setData] = useState<any>(onCanvas ? DEMO : null)
    const [sortBy, setSortBy] = useState<SortKey>(props.sortBy === "locked" || props.sortBy === "mcap" ? props.sortBy : "overhang")
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
        // cache-fallback: 직전 성공 응답 보존 → fetch 실패 시 stale 표시(빈 화면 회피, AlphaNest 패턴)
        if (typeof localStorage !== "undefined") {
            try { const c = localStorage.getItem(CACHE_KEY); if (c) setData(JSON.parse(c)) } catch {}
        }
        const url = props.dataUrl || BLOB + "/crypto_universe.json"
        fetch(url, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive || !d) return
                setData(d)
                if (typeof localStorage !== "undefined") { try { localStorage.setItem(CACHE_KEY, JSON.stringify(d)) } catch {} }
            })
            .catch(() => {})
        return () => { alive = false }
    }, [onCanvas, props.dataUrl])

    const rows = useMemo(() => {
        const coins = data && Array.isArray(data.coins) ? data.coins : []
        // fdv_mc_ratio 또는 circulating_ratio 둘 중 하나라도 있는 코인만(희석 사실 보유)
        const withDil = coins.filter((c: any) => c.fdv_mc_ratio != null || c.circulating_ratio != null)
        const sorted = [...withDil].sort((a: any, b: any) => {
            if (sortBy === "mcap") return (Number(b.market_cap) || 0) - (Number(a.market_cap) || 0)
            if (sortBy === "locked") {
                // 미유통(언락 대기) 큰 순 = 유통비율 낮은 순
                const ca = a.circulating_ratio == null ? 101 : Number(a.circulating_ratio)
                const cb = b.circulating_ratio == null ? 101 : Number(b.circulating_ratio)
                return ca - cb
            }
            // overhang = FDV/MC 큰 순
            const fa = a.fdv_mc_ratio == null ? 0 : Number(a.fdv_mc_ratio)
            const fb = b.fdv_mc_ratio == null ? 0 : Number(b.fdv_mc_ratio)
            return fb - fa
        })
        const n = Math.max(1, Math.min(props.topN || 30, sorted.length))
        return sorted.slice(0, n)
    }, [data, sortBy, props.topN])

    const overhangN = useMemo(() => {
        const coins = data && Array.isArray(data.coins) ? data.coins : []
        return coins.filter((c: any) => Number(c.fdv_mc_ratio) >= 2).length
    }, [data])

    const wrap: CSSProperties = { width: "100%", boxSizing: "border-box", fontFamily: FONT, color: C.ink, background: C.bg, borderRadius: 14, padding: 18, display: "flex", flexDirection: "column", gap: 12 }

    // 로딩 스켈레톤
    if (!data) {
        const skBase = isDark ? "#222a33" : "#e9edf1"
        const skHi = isDark ? "#2d3742" : "#f3f5f7"
        return (
            <div ref={rootRef} style={wrap}>
                <style>{`@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                {Array.from({ length: 8 }).map((_, i) => (
                    <div key={i} style={{ height: 52, borderRadius: 10, background: skBase, backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`, backgroundSize: "800px 100%", animation: "vsrShimmer 1.4s ease-in-out infinite" }} />
                ))}
            </div>
        )
    }

    const SORTS: { k: SortKey; label: string }[] = [
        { k: "overhang", label: "희석 압력" },
        { k: "locked", label: "미유통↑" },
        { k: "mcap", label: "시총" },
    ]

    return (
        <div ref={rootRef} style={wrap}>
            {/* 헤더 */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.4px" }}>코인 희석 포렌식</span>
                <span style={{ ...MONO, fontSize: 11.5, color: C.warn, fontWeight: 700 }}>희석≥2x {overhangN}개</span>
                <div style={{ marginLeft: "auto", display: "inline-flex", background: C.line, borderRadius: 9, padding: 2 }}>
                    {SORTS.map((s) => (
                        <button key={s.k} onClick={() => setSortBy(s.k)} style={{ border: "none", cursor: "pointer", fontFamily: FONT, fontSize: 12, fontWeight: 700, padding: "5px 11px", borderRadius: 7, background: sortBy === s.k ? C.card : "transparent", color: sortBy === s.k ? C.ink : C.sub }}>{s.label}</button>
                    ))}
                </div>
            </div>

            {/* 컬럼 라벨 */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 10.5, color: C.faint, fontWeight: 700, padding: "0 4px" }}>
                <span style={{ width: 22 }}>#</span>
                <span style={{ flex: "1 1 auto", minWidth: 0 }}>코인</span>
                <span style={{ width: 116, textAlign: "left" }}>유통 / 미유통(언락 대기)</span>
                <span style={{ width: 58, textAlign: "right" }}>FDV/MC</span>
            </div>

            {/* 랭킹 행 */}
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {rows.map((c: any, i: number) => {
                    const fdvMc = Number(c.fdv_mc_ratio)
                    const circ = c.circulating_ratio == null ? null : Math.max(0, Math.min(100, Number(c.circulating_ratio)))
                    const locked = circ == null ? null : Math.max(0, 100 - circ)
                    const ohCol = overhangColor(fdvMc, C)
                    const hot = isFinite(fdvMc) && fdvMc >= 2
                    return (
                        <div key={c.id || c.symbol}
                            onClick={() => { if (!onCanvas && typeof window !== "undefined" && c.id) window.open("https://www.coingecko.com/en/coins/" + encodeURIComponent(c.id), "_blank") }}
                            style={{ display: "flex", alignItems: "center", gap: 10, background: C.card, border: `1px solid ${hot ? alpha(C.warn, 0.35) : C.line}`, borderRadius: 10, padding: "9px 12px", cursor: "pointer" }}>
                            <span style={{ ...MONO, width: 22, fontSize: 12, fontWeight: 800, color: C.faint }}>{i + 1}</span>
                            <div style={{ flex: "1 1 auto", minWidth: 0 }}>
                                <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                                    <span style={{ ...MONO, fontSize: 13.5, fontWeight: 800, color: C.ink }}>{c.symbol}</span>
                                    <span style={{ fontSize: 11.5, color: C.sub, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</span>
                                </div>
                                <div style={{ ...MONO, fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 1 }}>시총 {fmtCap(c.market_cap)}{c.fdv ? " · FDV " + fmtCap(c.fdv) : ""}</div>
                            </div>
                            {/* 공급 바: 유통(초록) vs 미유통(amber) */}
                            <div style={{ width: 116, flexShrink: 0 }}>
                                <div style={{ display: "flex", height: 14, borderRadius: 4, overflow: "hidden", background: C.track }}>
                                    {circ == null ? (
                                        <div style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 9, color: C.faint, fontWeight: 700 }}>—</div>
                                    ) : (
                                        <>
                                            <div style={{ width: circ + "%", background: C.up }} />
                                            <div style={{ width: locked + "%", background: alpha(C.warn, 0.85) }} />
                                        </>
                                    )}
                                </div>
                                {circ != null && (
                                    <div style={{ ...MONO, display: "flex", justifyContent: "space-between", fontSize: 9.5, fontWeight: 700, marginTop: 2 }}>
                                        <span style={{ color: C.up }}>{circ.toFixed(0)}%</span>
                                        <span style={{ color: locked && locked >= 1 ? C.warn : C.faint }}>미유통 {locked!.toFixed(0)}%</span>
                                    </div>
                                )}
                            </div>
                            <span style={{ ...MONO, width: 58, textAlign: "right", fontSize: 13, fontWeight: 800, color: ohCol }}>{isFinite(fdvMc) && fdvMc > 0 ? fdvMc.toFixed(2) + "x" : "—"}</span>
                        </div>
                    )
                })}
            </div>

            {/* 푸터 — RULE 7 */}
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontSize: 10.5, color: C.faint, fontWeight: 600 }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 11, height: 11, borderRadius: 2, background: C.up }} /> 유통</span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 11, height: 11, borderRadius: 2, background: C.warn }} /> 미유통(언락 대기)</span>
                <span style={{ marginLeft: "auto" }}>FDV/MC = 완전희석가치÷시총(미유통 물량 배수) · CoinGecko 공급 사실</span>
            </div>
        </div>
    )
}

addPropertyControls(CryptoDilutionForensics, {
    dataUrl: { type: ControlType.String, title: "데이터 URL", defaultValue: BLOB + "/crypto_universe.json" },
    dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
    sortBy: { type: ControlType.Enum, title: "정렬", options: ["overhang", "locked", "mcap"], optionTitles: ["희석 압력", "미유통↑", "시총"], defaultValue: "overhang" },
    topN: { type: ControlType.Number, title: "표시 개수", defaultValue: 30, min: 5, max: 50, step: 5 },
})
