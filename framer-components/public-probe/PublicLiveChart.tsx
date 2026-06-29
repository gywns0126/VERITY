import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 실시간 캔들 차트 — VERITY 공개 터미널. 외부 라이브러리 0 (순수 SVG → 무조건 렌더).
 *
 * 데이터 = /api/chart 일봉 OHLCV(KIS 증권사급, 토스와 동급 소스 · 실제 시세).
 * 라이브 = /api/stock 현재가 폴링으로 마지막 봉 갱신 — 🚨 정직: REST 폴링(웹소켓 틱 아님, 약간 지연) +
 *   장중(평일 09:00–15:30 KST)에만 움직임. 장외엔 종가 고정 → 배지를 "장중 시세 / 장 마감·종가"로 정직 표기.
 * 🚨 캔버스(에디터)에서도 봉이 보이게 = 데모 봉 즉시 세팅 + 실제 /api/chart 도 시도(성공 시 교체).
 * 🚨 높이 = 프레임 실제 높이를 측정해 그 안을 꽉 채움(반응형). 고정 H 강제 안 함 → 짧은 프레임서 잘림/압축 방지.
 * 🚨 로딩 = 토스식 캔들 shimmer 스켈레톤(빈 텍스트 대신). 게시 전/적재 전 빈 화면 방지.
 * hover/터치 = 토스풍 플로팅 카드(컴팩트, 300px서도). KR 색 = 상승 빨강 / 하락 파랑. 폰트 = 가볍게(헤비 회피).
 * 테마: Framer 네이티브 추종 — body[data-framer-theme] 읽어 dark 전환(캔버스는 dark prop 정적 프리뷰).
 */

interface Props {
    ticker: string
    apiBase: string
    dark: boolean
    livePollSec: number
    height: number
    showVolume: boolean
}
const DEFAULT_API = "https://project-yw131.vercel.app"
const LIGHT = { bg: "#ffffff", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#e5e8eb", grid: "#eef1f4", up: "#f04452", down: "#3182f6", live: "#15c47e", tipBd: "#e5e8eb" }
const DARK = { bg: "#171c23", card: "#1e242c", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#252b34", grid: "#1e242c", up: "#f04452", down: "#5b9bff", live: "#34e08a", tipBd: "#2d343d" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif"
const WK = ["일", "월", "화", "수", "목", "금", "토"]

function mmdd(s: any): string {
    const x = String(s || "")
    if (/^\d{8}$/.test(x)) return x.slice(4, 6) + "." + x.slice(6, 8)
    if (x.length >= 10) return x.slice(5).replace(/-/g, ".")
    return x
}
function dateDot(s: any): string {
    const x = String(s || "")
    if (!/^\d{8}$/.test(x)) return x
    const wd = WK[new Date(+x.slice(0, 4), +x.slice(4, 6) - 1, +x.slice(6, 8)).getDay()]
    return `${x.slice(0, 4)}.${x.slice(4, 6)}.${x.slice(6, 8)}(${wd})`
}
function won(v: any): string { const x = Number(v); return isFinite(x) ? Math.round(x).toLocaleString("en-US") + "원" : "—" }
function fmtVol(v: any): string {
    const x = Number(v)
    if (!isFinite(x) || x <= 0) return "—"
    if (x >= 1e8) return (x / 1e8).toFixed(2) + "억"
    if (x >= 1e4) return Math.round(x / 1e4).toLocaleString("en-US") + "만"
    return Math.round(x).toLocaleString("en-US")
}
function isKROpen(): boolean {
    const d = new Date()
    const k = new Date(d.getTime() + (d.getTimezoneOffset() + 540) * 60000)
    const day = k.getDay()
    if (day === 0 || day === 6) return false
    const m = k.getHours() * 60 + k.getMinutes()
    return m >= 540 && m <= 930
}
function demoCandles(): any[] {
    const demo: any[] = []
    let p = 70000
    for (let i = 0; i < 60; i++) {
        const o = p, c = p * (1 + (((i * 7) % 11) - 5) / 100)
        demo.push({ date: "202604" + String((i % 28) + 1).padStart(2, "0"), open: o, high: Math.max(o, c) * 1.01, low: Math.min(o, c) * 0.99, close: c, volume: 1000000 + i * 9000 })
        p = c
    }
    return demo
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicLiveChart(props: Props) {
    const { ticker, apiBase, dark, livePollSec, height, showVolume } = props
    const base = (apiBase || DEFAULT_API).replace(/\/+$/, "")
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const Hprop = height || 340

    const wrapRef = useRef<HTMLDivElement>(null)
    const svgRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [h, setH] = useState(0)
    const [candles, setCandles] = useState<any[]>(() => (RenderTarget.current() === RenderTarget.canvas ? demoCandles() : []))
    const [hoverIdx, setHoverIdx] = useState<number | null>(null)
    const [livePx, setLivePx] = useState<number | null>(null)
    const [pulse, setPulse] = useState(0)
    const [noData, setNoData] = useState(false)
    const [themeDark, setThemeDark] = useState<boolean>(!!dark)

    const isDark = onCanvas ? !!dark : themeDark
    const C = isDark ? DARK : LIGHT

    /* 테마 추종: body[data-framer-theme] 읽기 + 변경 감지 (캔버스는 dark prop 정적) */
    useEffect(() => {
        if (onCanvas) return
        const read = () => {
            const t = (typeof document !== "undefined" && document.body) ? document.body.dataset.framerTheme : ""
            setThemeDark(t === "dark")
        }
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    // 🚨 종목 미지정 시 삼성전자(005930) 등 기본 종목으로 떨어뜨리지 않음 —
    //    유효 6자리 코드가 없으면 빈 문자열 → '정보 없음' 빈 상태를 표시(엉뚱한 종목 그래프 방지).
    const tk = useMemo(() => {
        let t = String(ticker || "").trim()
        if (!t && typeof window !== "undefined") t = (new URLSearchParams(window.location.search).get("q") || "").trim()
        return /^\d{6}$/.test(t) ? t : ""
    }, [ticker])

    const marketOpen = !onCanvas && isKROpen()

    useEffect(() => {
        const el = wrapRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) { setW(e.contentRect.width); setH(e.contentRect.height) } })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    // 데이터 — 실제 /api/chart 시도. 캔버스엔 데모 봉 즉시 세팅(빈 화면 방지)→성공 시 실봉 교체.
    // 종목 없음/봉 없음/요청 실패 = noData=true → '정보 없음' 빈 상태(런타임). 캔버스는 항상 데모 유지.
    useEffect(() => {
        let alive = true
        if (onCanvas) setCandles(demoCandles())
        else { setCandles([]); setLivePx(null); setNoData(false) }
        if (!tk) { if (!onCanvas) setNoData(true); return () => { alive = false } }
        fetch(base + "/api/chart?ticker=" + tk + "&type=daily")
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive) return
                const arr = d && Array.isArray(d.daily) ? d.daily : (Array.isArray(d) ? d : null)
                if (Array.isArray(arr) && arr.length > 1) setCandles(arr)
                else if (!onCanvas) setNoData(true)
            })
            .catch(() => { if (alive && !onCanvas) setNoData(true) })
        return () => { alive = false }
    }, [tk, base, onCanvas])

    // 라이브 폴링 — 에디터(canvas)·종목없음 제외, 장중에만 interval.
    useEffect(() => {
        if (onCanvas || !tk) return
        const sec = Math.max(3, livePollSec || 6)
        let alive = true
        const tick = () => {
            fetch(base + "/api/stock?q=" + tk + "&market=kr")
                .then((r) => (r.ok ? r.json() : null))
                .then((d) => {
                    if (!alive || !d) return
                    const p = d.price ?? d.current_price ?? (d.stock && d.stock.price)
                    const px = Number(p)
                    if (!isFinite(px) || px <= 0) return
                    setLivePx(px)
                    setPulse((n) => n + 1)
                    setCandles((prev) => {
                        if (!prev.length) return prev
                        const next = prev.slice()
                        const last = { ...next[next.length - 1] }
                        last.close = px
                        last.high = Math.max(Number(last.high) || px, px)
                        last.low = Math.min(Number(last.low) || px, px)
                        next[next.length - 1] = last
                        return next
                    })
                })
                .catch(() => {})
        }
        tick()
        let timer: any = null
        if (isKROpen()) timer = setInterval(tick, sec * 1000)
        return () => { alive = false; if (timer) clearInterval(timer) }
    }, [tk, base, livePollSec, onCanvas])

    const cv = useMemo(() => {
        if (!candles || candles.length < 2) return null
        const closes = candles.map((c) => Number(c.close))
        const opens = candles.map((c) => Number(c.open != null ? c.open : c.close))
        const highs = candles.map((c) => Number(c.high != null ? c.high : c.close))
        const lows = candles.map((c) => Number(c.low != null ? c.low : c.close))
        const vols = candles.map((c) => Number(c.volume != null ? c.volume : 0))
        const pmin = Math.min(...lows.filter((x) => isFinite(x)))
        const pmax = Math.max(...highs.filter((x) => isFinite(x)))
        if (!isFinite(pmin) || !isFinite(pmax)) return null
        const prng = (pmax - pmin) || 1
        const W = Math.max(240, (w || 600) - 4)
        // 차트 svg 총높이 = 프레임 실측 높이 - 크롬(헤더/날짜축/푸터/패딩 ≈ 64). 미측정 시 prop fallback.
        const chartH = h > 140 ? Math.max(150, h - 64) : Hprop
        const Hv = showVolume ? Math.round(chartH * 0.18) : 0
        const gap = showVolume ? 8 : 0
        const padT = 8, padB = 4
        const Hp = chartH - Hv - gap
        const xAt = (i: number) => (candles.length === 1 ? W / 2 : (i / (candles.length - 1)) * W)
        const yP = (v: number) => padT + (Hp - padT - padB) - ((v - pmin) / prng) * (Hp - padT - padB)
        const up = closes[closes.length - 1] >= closes[0]
        const vmax = Math.max(1, ...vols.filter((x) => isFinite(x)))
        const cw = Math.max(1.5, (W / candles.length) * 0.66)
        const items = candles.map((c, i) => {
            const upDay = closes[i] >= opens[i]
            const bh = Hv ? (vols[i] / vmax) * Hv : 0
            return { x: xAt(i), oy: yP(opens[i]), cy: yP(closes[i]), hy: yP(highs[i]), ly: yP(lows[i]), upDay, volTop: Hp + gap + (Hv - bh), volH: Math.max(0.5, bh) }
        })
        const tickIdx = [0, Math.round((candles.length - 1) / 3), Math.round((2 * (candles.length - 1)) / 3), candles.length - 1]
        return { W, H: chartH, Hp, Hv, gap, pmin, pmax, xAt, yP, items, cw, up, n: candles.length, tickIdx }
    }, [candles, w, h, Hprop, showVolume])

    const setHoverFromX = (clientX: number) => {
        if (!cv || !svgRef.current) return
        const rect = svgRef.current.getBoundingClientRect()
        if (rect.width <= 0) return
        let rel = (clientX - rect.left) / rect.width
        rel = Math.max(0, Math.min(1, rel))
        setHoverIdx(Math.round(rel * (cv.n - 1)))
    }

    const hov = hoverIdx != null && cv && hoverIdx >= 0 && hoverIdx < cv.n ? candles[hoverIdx] : null
    const hovX = hov && cv ? cv.xAt(hoverIdx as number) : 0
    // 등락률 = 전일 종가 대비 (없으면 시가 대비)
    const hovChg = (() => {
        if (!hov || hoverIdx == null) return null
        const prevClose = hoverIdx > 0 ? Number(candles[hoverIdx - 1].close) : Number(hov.open)
        const c = Number(hov.close)
        if (!isFinite(prevClose) || prevClose <= 0 || !isFinite(c)) return null
        return ((c - prevClose) / prevClose) * 100
    })()
    const cardLeftPct = cv ? (hovX / cv.W) * 100 : 0
    const cardFlip = cv ? hoverIdx != null && (hoverIdx as number) > cv.n * 0.5 : false

    const wrap: CSSProperties = {
        width: "100%", height: "100%", minHeight: 180, position: "relative",
        background: C.bg, borderRadius: 16, overflow: "hidden", boxSizing: "border-box",
        fontFamily: FONT, padding: "6px 2px",
    }
    const tipRow = (label: string, value: any, color?: string) => (
        <div style={{ display: "flex", justifyContent: "space-between", gap: 10, padding: "2px 0" }}>
            <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 500 }}>{label}</span>
            <span style={{ fontSize: 11.5, color: color || C.ink, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>{value}</span>
        </div>
    )

    // 표시할 시세 데이터가 없을 때 — 엉뚱한 종목 그래프 대신 정직한 빈 상태.
    const renderEmpty = () => {
        const H = h > 140 ? Math.max(150, h - 64) : Hprop
        return (
            <div style={{ height: H, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 7, padding: "0 18px", textAlign: "center", boxSizing: "border-box" }}>
                <svg width="30" height="30" viewBox="0 0 24 24" fill="none" style={{ opacity: 0.45 }}>
                    <path d="M3 3v18h18" stroke={C.faint} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M7 14l3-3 3 3 4-5" stroke={C.faint} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="2.5 2.5" />
                </svg>
                <span style={{ fontSize: 13, fontWeight: 700, color: C.sub }}>표시할 시세 정보가 없습니다</span>
                <span style={{ fontSize: 11, fontWeight: 500, color: C.faint, lineHeight: 1.5 }}>이 종목은 차트로 표시할 일봉 데이터가 없어요</span>
            </div>
        )
    }

    // 로딩 스켈레톤 — 캔들 모양 shimmer 막대 + 날짜축 placeholder (토스식)
    const renderSkeleton = () => {
        const skBase = isDark ? "#222a33" : "#e9edf1"
        const skHi = isDark ? "#2d3742" : "#f3f5f7"
        const sh: CSSProperties = {
            background: skBase, backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`,
            backgroundSize: "800px 100%", animation: "plcShimmer 1.4s ease-in-out infinite",
        }
        const H = h > 140 ? Math.max(150, h - 64) : Hprop
        const n = 30
        return (
            <div style={{ padding: "8px 10px 0" }}>
                <style>{`@keyframes plcShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={{ height: H, display: "flex", alignItems: "flex-end", gap: 3 }}>
                    {Array.from({ length: n }).map((_, i) => {
                        const bh = 26 + ((i * 41 + 17) % 64) // 26~90% 결정론적 변동(캔들 느낌)
                        return <div key={i} style={{ flex: 1, height: bh + "%", borderRadius: 3, ...sh }} />
                    })}
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 10 }}>
                    {Array.from({ length: 4 }).map((_, i) => <div key={i} style={{ width: 38, height: 9, borderRadius: 4, ...sh }} />)}
                </div>
            </div>
        )
    }

    return (
        <div ref={wrapRef} style={wrap}>
            {/* 헤더 — 현재가 + 정직 장 상태 배지 */}
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, padding: "2px 10px 4px", minHeight: 18, flexWrap: "wrap" }}>
                {livePx != null && <span style={{ fontSize: 14, fontWeight: 700, color: C.ink }}>{won(livePx)}</span>}
                {!onCanvas && !noData && (
                    <span style={{ fontSize: 11, fontWeight: 700, color: marketOpen ? C.live : C.faint, display: "inline-flex", alignItems: "center", gap: 4 }}>
                        <span style={{ width: 7, height: 7, borderRadius: "50%", background: marketOpen ? C.live : C.faint, display: "inline-block", opacity: marketOpen ? (pulse % 2 ? 1 : 0.4) : 1, transition: "opacity 0.4s" }} />
                        {marketOpen ? "장중 시세" : "장 마감 · 종가"}
                    </span>
                )}
                {onCanvas && <span style={{ fontSize: 11, fontWeight: 600, color: C.faint }}>미리보기 봉(에디터) · 게시 시 실시세</span>}
            </div>

            {cv ? (
                <>
                    <div ref={svgRef} style={{ position: "relative", width: "100%", touchAction: "pan-y" }}
                        onMouseMove={(e) => setHoverFromX(e.clientX)}
                        onMouseLeave={() => setHoverIdx(null)}
                        onTouchStart={(e) => { if (e.touches[0]) setHoverFromX(e.touches[0].clientX) }}
                        onTouchMove={(e) => { if (e.touches[0]) setHoverFromX(e.touches[0].clientX) }}>
                        <svg viewBox={`0 0 ${cv.W} ${cv.H}`} width="100%" height={cv.H} preserveAspectRatio="none" style={{ display: "block" }}>
                            <line x1={0} y1={cv.yP(cv.pmax)} x2={cv.W} y2={cv.yP(cv.pmax)} stroke={C.grid} strokeWidth={1} />
                            <line x1={0} y1={cv.yP(cv.pmin)} x2={cv.W} y2={cv.yP(cv.pmin)} stroke={C.grid} strokeWidth={1} />
                            {cv.items.map((cd: any, i: number) => {
                                const col = cd.upDay ? C.up : C.down
                                const bodyTop = Math.min(cd.oy, cd.cy)
                                const bodyH = Math.max(0.8, Math.abs(cd.oy - cd.cy))
                                return (
                                    <g key={i}>
                                        {cv.Hv > 0 && <rect x={cd.x - cv.cw / 2} y={cd.volTop} width={cv.cw} height={cd.volH} fill={col} fillOpacity={0.4} />}
                                        <line x1={cd.x} y1={cd.hy} x2={cd.x} y2={cd.ly} stroke={col} strokeWidth={1} vectorEffect="non-scaling-stroke" />
                                        <rect x={cd.x - cv.cw / 2} y={bodyTop} width={Math.max(1, cv.cw)} height={bodyH} fill={col} />
                                    </g>
                                )
                            })}
                            {hov && (
                                <>
                                    <line x1={hovX} y1={0} x2={hovX} y2={cv.H} stroke={C.faint} strokeWidth={1} strokeOpacity={0.45} vectorEffect="non-scaling-stroke" />
                                    <circle cx={hovX} cy={cv.yP(Number(hov.close))} r={4} fill={cv.up ? C.up : C.down} stroke={C.bg} strokeWidth={1.5} />
                                </>
                            )}
                        </svg>
                        <span style={{ position: "absolute", top: 2, right: 4, fontSize: 10, fontWeight: 600, color: C.faint, background: C.bg, padding: "0 3px", borderRadius: 4 }}>{Number(cv.pmax).toLocaleString()}</span>
                        <span style={{ position: "absolute", top: (cv.Hp - 14) + "px", right: 4, fontSize: 10, fontWeight: 600, color: C.faint, background: C.bg, padding: "0 3px", borderRadius: 4 }}>{Number(cv.pmin).toLocaleString()}</span>

                        {/* 토스풍 플로팅 정보 카드 (컴팩트 — 300px서도 보이게, 폰트 가볍게) */}
                        {hov && (
                            <div style={{
                                position: "absolute", top: 2, left: cardLeftPct + "%",
                                transform: cardFlip ? "translateX(calc(-100% - 8px))" : "translateX(8px)",
                                background: C.card, border: `1px solid ${C.tipBd}`, borderRadius: 10,
                                boxShadow: "0 8px 24px rgba(0,0,0,0.14)", padding: "7px 9px", minWidth: 118,
                                zIndex: 30, pointerEvents: "none",
                            }}>
                                <div style={{ fontSize: 12, fontWeight: 600, color: C.ink, marginBottom: 4, letterSpacing: "-0.2px" }}>{dateDot(hov.date)}</div>
                                {tipRow("시작", won(hov.open))}
                                {tipRow("마지막", won(hov.close))}
                                {tipRow("최고", won(hov.high), C.up)}
                                {tipRow("최저", won(hov.low), C.down)}
                                {tipRow("거래량", fmtVol(hov.volume))}
                                {hovChg != null && tipRow("등락률", (hovChg > 0 ? "+" : "") + hovChg.toFixed(2) + "%", hovChg > 0 ? C.up : hovChg < 0 ? C.down : C.faint)}
                            </div>
                        )}
                    </div>
                    <div style={{ position: "relative", height: 14, margin: "2px 2px 0" }}>
                        {cv.tickIdx.map((ti: number, i: number) => {
                            const lp = (cv.xAt(ti) / cv.W) * 100
                            const tf = i === 0 ? "translateX(0)" : i === cv.tickIdx.length - 1 ? "translateX(-100%)" : "translateX(-50%)"
                            return <span key={i} style={{ position: "absolute", left: lp + "%", transform: tf, fontSize: 10, fontWeight: 500, color: C.faint, whiteSpace: "nowrap" }}>{mmdd(candles[ti] && candles[ti].date)}</span>
                        })}
                    </div>
                    <div style={{ fontSize: 10, color: C.faint, fontWeight: 500, padding: "3px 10px 0", lineHeight: 1.4 }}>
                        일봉 = KIS 실제 시세 · {marketOpen ? "장중 현재가 갱신(REST·지연 가능)" : "현재 장 마감 — 종가 고정"} · 등락률=전일 종가 대비
                    </div>
                </>
            ) : noData ? (
                renderEmpty()
            ) : (
                renderSkeleton()
            )}
        </div>
    )
}

addPropertyControls(PublicLiveChart, {
    ticker: { type: ControlType.String, title: "Ticker", defaultValue: "" },
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    livePollSec: { type: ControlType.Number, title: "Live Poll (s)", defaultValue: 6, min: 3, max: 60, step: 1 },
    height: { type: ControlType.Number, title: "Height(fallback)", defaultValue: 340, min: 160, max: 720, step: 10 },
    showVolume: { type: ControlType.Boolean, title: "Volume", defaultValue: true, enabledTitle: "On", disabledTitle: "Off" },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})
