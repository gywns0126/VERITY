"use client"
// ProChart — 오퍼레이터 전용 프로 차트 (PM 2026-08-05 "트레이딩뷰급으로").
// 공개 알파네스트 PublicLiveChart 의 상호작용 문법(호버 크로스헤어·OHLC 카드·기간 탭·52주선·
// MA 전체구간 계산 후 슬라이스)을 계승하고, 오퍼레이터 전용으로 더 얹는다:
//   · 캔들 + 거래량 + MA5/20/60 + 52주 고저 점선 + 현재가 라벨
//   · 크로스헤어(수직·수평) + 호버 OHLC/등락/거래량 카드(경계에서 좌우 자동 반전)
//   · 기간 탭(1M/3M/6M/1Y/전체) — MA 는 전체 구간에서 계산 후 표시 구간만 슬라이스(경계 왜곡 방지)
//   · 로그/선형 축 토글 · 마지막 봉 강조 · 반응형(ResizeObserver)
// 외곽선 0 · 상승 빨강/하락 파랑(국내 관례).
import { useEffect, useMemo, useRef, useState } from "react"
import { useDark, palette, FONT, NUM, type Palette } from "@/lib/theme"

export type Candle = { t: string; o: number; h: number; l: number; c: number; v: number }

const RANGES: Array<{ k: string; label: string; n: number }> = [
    { k: "1m", label: "1개월", n: 22 },
    { k: "3m", label: "3개월", n: 66 },
    { k: "6m", label: "6개월", n: 132 },
    { k: "1y", label: "1년", n: 252 },
    { k: "all", label: "전체", n: 0 },
]

function sma(src: number[], p: number): Array<number | null> {
    const out: Array<number | null> = []
    let sum = 0
    for (let i = 0; i < src.length; i++) {
        sum += src[i]
        if (i >= p) sum -= src[i - p]
        out.push(i >= p - 1 ? sum / p : null)
    }
    return out
}

export default function ProChart({
    candles,
    dec = 0,
    height = 320,
    unit = "",
    showRanges = true,
}: {
    candles: Candle[]
    dec?: number
    height?: number
    unit?: string
    showRanges?: boolean
}) {
    const dark = useDark()
    const c = palette(dark)
    const wrapRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(920)
    const [range, setRange] = useState("6m")
    const [hoverIdx, setHoverIdx] = useState<number | null>(null)
    const [logScale, setLogScale] = useState(false)

    // 반응형 — 컨테이너 실폭 추적(고정 viewBox 확대 = 흐릿함 방지)
    useEffect(() => {
        const el = wrapRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => {
            const cw = entries[0]?.contentRect?.width
            if (cw && cw > 200) setW(Math.round(cw))
        })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    // MA 는 전체 구간에서 계산 → 표시 구간만 슬라이스 (구간 경계 왜곡 방지)
    const view = useMemo(() => {
        const all = candles.filter((x) => x && isFinite(x.h) && x.h > 0)
        if (all.length < 2) return null
        const closes = all.map((x) => x.c)
        const m5 = sma(closes, 5)
        const m20 = sma(closes, 20)
        const m60 = sma(closes, 60)
        const rn = RANGES.find((r) => r.k === range)?.n ?? 0
        const start = rn > 0 && all.length > rn ? all.length - rn : 0
        const cs = all.slice(start)
        return {
            cs,
            ma5: m5.slice(start),
            ma20: m20.slice(start),
            ma60: m60.slice(start),
            hi52: Math.max(...all.slice(-252).map((x) => x.h)),
            lo52: Math.min(...all.slice(-252).map((x) => x.l)),
            prevClose: start > 0 ? all[start - 1].c : all[0].o,
        }
    }, [candles, range])

    const geo = useMemo(() => {
        if (!view) return null
        const { cs } = view
        const W = w
        const PL = 4, PR = 78, PT = 8, PB = 22
        const volH = Math.max(38, Math.round(height * 0.17))
        const gap = 8
        const priceH = height - volH - gap - PT - PB
        const plotW = W - PL - PR
        const n = cs.length
        const xw = plotW / n
        const bw = Math.max(1.5, Math.min(12, xw * 0.66))

        let hi = Math.max(...cs.map((k) => k.h))
        let lo = Math.min(...cs.map((k) => k.l))
        // MA60 이 범위 밖이면 포함 (선이 잘리지 않게)
        for (const arr of [view.ma5, view.ma20, view.ma60]) {
            for (const v of arr) {
                if (v == null) continue
                hi = Math.max(hi, v)
                lo = Math.min(lo, v)
            }
        }
        if (view.hi52 <= hi * 1.15 && view.hi52 >= lo) hi = Math.max(hi, view.hi52)
        if (view.lo52 >= lo * 0.85 && view.lo52 <= hi) lo = Math.min(lo, view.lo52)
        const pad = (hi - lo) * 0.06 || 1
        hi += pad
        lo = Math.max(0, lo - pad)

        const lg = logScale && lo > 0
        const tf = (v: number) => (lg ? Math.log10(Math.max(v, 1e-9)) : v)
        const tHi = tf(hi), tLo = tf(lo)
        const rng = tHi - tLo || 1
        const yP = (v: number) => PT + ((tHi - tf(v)) / rng) * priceH
        const xAt = (i: number) => PL + i * xw + xw / 2

        const volMax = Math.max(1, ...cs.map((k) => k.v || 0))
        const volTop = PT + priceH + gap
        const yV = (v: number) => volTop + volH - ((v || 0) / volMax) * volH

        const path = (arr: Array<number | null>) => {
            let d = ""
            let started = false
            arr.forEach((v, i) => {
                if (v == null) return
                d += (started ? "L" : "M") + xAt(i).toFixed(1) + "," + yP(v).toFixed(1)
                started = true
            })
            return d
        }
        const gridVals = Array.from({ length: 5 }, (_, g) => {
            const t = tHi - (rng * g) / 4
            return lg ? Math.pow(10, t) : t
        })
        const tickIdx = [0, Math.floor(n / 3), Math.floor((2 * n) / 3), n - 1].filter(
            (v, i, a) => a.indexOf(v) === i && v >= 0 && v < n
        )
        return { W, PL, PR, PT, PB, priceH, volH, volTop, gap, n, xw, bw, hi, lo, yP, xAt, yV, path, gridVals, tickIdx, H: height }
    }, [view, w, height, logScale])

    if (!view || !geo) {
        return (
            <div ref={wrapRef} style={{ height, display: "flex", alignItems: "center", justifyContent: "center", background: c.hi, borderRadius: 12, fontSize: 12, color: c.faint, fontFamily: FONT }}>
                차트 데이터 없음
            </div>
        )
    }

    const { cs } = view
    const last = cs[cs.length - 1]
    const hov = hoverIdx != null && hoverIdx >= 0 && hoverIdx < cs.length ? cs[hoverIdx] : null
    const shown = hov || last
    const shownPrev = hov
        ? hoverIdx! > 0 ? cs[hoverIdx! - 1].c : view.prevClose
        : cs.length > 1 ? cs[cs.length - 2].c : view.prevClose
    const chg = shownPrev > 0 ? ((shown.c - shownPrev) / shownPrev) * 100 : null
    const fmt = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: dec }) + unit
    const fmtVol = (v: number) => (v >= 1e8 ? (v / 1e8).toFixed(1) + "억" : v >= 1e4 ? (v / 1e4).toFixed(1) + "만" : Math.round(v).toLocaleString())

    function onMove(e: React.MouseEvent<SVGSVGElement>) {
        const rect = e.currentTarget.getBoundingClientRect()
        if (rect.width <= 0) return
        const rel = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
        const px = rel * geo!.W
        const i = Math.round((px - geo!.PL - geo!.xw / 2) / geo!.xw)
        setHoverIdx(Math.max(0, Math.min(cs.length - 1, i)))
    }

    const upCol = c.up, dnCol = c.down
    const hovX = hoverIdx != null ? geo.xAt(hoverIdx) : 0
    const cardFlip = hoverIdx != null && hoverIdx > cs.length * 0.55

    return (
        <div ref={wrapRef} style={{ fontFamily: FONT, display: "flex", flexDirection: "column", gap: 7, minWidth: 0 }}>
            {/* 컨트롤 — 기간 · 축 */}
            {showRanges ? (
                <div style={{ display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap" }}>
                    {RANGES.map((r) => (
                        <button
                            key={r.k}
                            onClick={() => { setRange(r.k); setHoverIdx(null) }}
                            style={{ border: "none", borderRadius: 999, padding: "4px 11px", fontSize: 10.5, fontWeight: 800, cursor: "pointer", fontFamily: FONT, background: range === r.k ? c.vtS : c.hi, color: range === r.k ? c.vt : c.faint }}
                        >
                            {r.label}
                        </button>
                    ))}
                    <button
                        onClick={() => setLogScale((v) => !v)}
                        style={{ marginLeft: "auto", border: "none", borderRadius: 999, padding: "4px 11px", fontSize: 10.5, fontWeight: 800, cursor: "pointer", fontFamily: FONT, background: logScale ? c.vtS : c.hi, color: logScale ? c.vt : c.faint }}
                    >
                        {logScale ? "로그" : "선형"}
                    </button>
                </div>
            ) : null}

            {/* 상단 OHLC 리드아웃 — 호버 시 해당 봉, 아니면 최신 */}
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap", minHeight: 18 }}>
                <span style={{ fontSize: 11, fontWeight: 800, color: c.sub, ...NUM }}>{shown.t}</span>
                <span style={{ fontSize: 11, color: c.sub, ...NUM }}>
                    시 <b style={{ color: c.ink }}>{fmt(shown.o)}</b> 고 <b style={{ color: upCol }}>{fmt(shown.h)}</b> 저 <b style={{ color: dnCol }}>{fmt(shown.l)}</b> 종 <b style={{ color: c.ink }}>{fmt(shown.c)}</b>
                </span>
                {chg != null ? (
                    <span style={{ fontSize: 11, fontWeight: 800, color: chg > 0 ? upCol : chg < 0 ? dnCol : c.faint, ...NUM }}>
                        {chg > 0 ? "+" : ""}{chg.toFixed(2)}%
                    </span>
                ) : null}
                {shown.v > 0 ? <span style={{ fontSize: 10.5, color: c.faint, ...NUM }}>거래량 {fmtVol(shown.v)}</span> : null}
                <span style={{ marginLeft: "auto", display: "flex", gap: 8, fontSize: 9.5, ...NUM }}>
                    <span style={{ color: c.green }}>MA5</span>
                    <span style={{ color: c.amber }}>MA20</span>
                    <span style={{ color: c.vt }}>MA60</span>
                </span>
            </div>

            <div style={{ position: "relative", background: c.hi, borderRadius: 12, overflow: "hidden" }}>
                <svg
                    width="100%"
                    height={geo.H}
                    viewBox={`0 0 ${geo.W} ${geo.H}`}
                    preserveAspectRatio="none"
                    onMouseMove={onMove}
                    onMouseLeave={() => setHoverIdx(null)}
                    style={{ display: "block", cursor: "crosshair" }}
                >
                    {/* 가격 격자 + 우측 눈금 */}
                    {geo.gridVals.map((v, i) => (
                        <g key={"g" + i}>
                            <line x1={geo.PL} x2={geo.W - geo.PR + 3} y1={geo.yP(v)} y2={geo.yP(v)} stroke={c.line} strokeWidth={1} strokeDasharray="3 5" />
                            <text x={geo.W - geo.PR + 7} y={geo.yP(v) + 4} fontSize={10.5} fill={c.faint} style={{ fontVariantNumeric: "tabular-nums" }}>
                                {v.toLocaleString(undefined, { maximumFractionDigits: dec })}
                            </text>
                        </g>
                    ))}

                    {/* 52주 고저 */}
                    {view.hi52 <= geo.hi && view.hi52 >= geo.lo ? (
                        <g>
                            <line x1={geo.PL} x2={geo.W - geo.PR} y1={geo.yP(view.hi52)} y2={geo.yP(view.hi52)} stroke={upCol} strokeWidth={1} strokeDasharray="2 6" opacity={0.55} />
                            <text x={geo.PL + 4} y={geo.yP(view.hi52) - 3} fontSize={9} fill={upCol} opacity={0.8}>52주 고</text>
                        </g>
                    ) : null}
                    {view.lo52 >= geo.lo && view.lo52 <= geo.hi ? (
                        <g>
                            <line x1={geo.PL} x2={geo.W - geo.PR} y1={geo.yP(view.lo52)} y2={geo.yP(view.lo52)} stroke={dnCol} strokeWidth={1} strokeDasharray="2 6" opacity={0.55} />
                            <text x={geo.PL + 4} y={geo.yP(view.lo52) + 10} fontSize={9} fill={dnCol} opacity={0.8}>52주 저</text>
                        </g>
                    ) : null}

                    {/* 캔들 */}
                    {cs.map((k, i) => {
                        const up = k.c >= k.o
                        const col = up ? upCol : dnCol
                        const x = geo.xAt(i)
                        const top = geo.yP(Math.max(k.o, k.c))
                        const bot = geo.yP(Math.min(k.o, k.c))
                        const isLast = i === cs.length - 1
                        return (
                            <g key={i} opacity={hoverIdx == null || hoverIdx === i ? 1 : 0.82}>
                                <line x1={x} x2={x} y1={geo.yP(k.h)} y2={geo.yP(k.l)} stroke={col} strokeWidth={isLast ? 1.6 : 1} />
                                <rect x={x - geo.bw / 2} y={top} width={geo.bw} height={Math.max(1, bot - top)} fill={col} rx={0.8} />
                            </g>
                        )
                    })}

                    {/* 이동평균 */}
                    <path d={geo.path(view.ma5)} fill="none" stroke={c.green} strokeWidth={1.3} strokeLinejoin="round" />
                    <path d={geo.path(view.ma20)} fill="none" stroke={c.amber} strokeWidth={1.3} strokeLinejoin="round" />
                    <path d={geo.path(view.ma60)} fill="none" stroke={c.vt} strokeWidth={1.3} strokeLinejoin="round" opacity={0.85} />

                    {/* 현재가 라인 + 라벨 */}
                    <line x1={geo.PL} x2={geo.W - geo.PR + 3} y1={geo.yP(last.c)} y2={geo.yP(last.c)} stroke={c.vt} strokeWidth={1} strokeDasharray="5 4" />
                    <rect x={geo.W - geo.PR + 4} y={geo.yP(last.c) - 9} width={geo.PR - 7} height={18} rx={5} fill={c.vt} />
                    <text x={geo.W - geo.PR + 4 + (geo.PR - 7) / 2} y={geo.yP(last.c) + 4} fontSize={10.5} fontWeight={700} fill="#fff" textAnchor="middle" style={{ fontVariantNumeric: "tabular-nums" }}>
                        {last.c.toLocaleString(undefined, { maximumFractionDigits: dec })}
                    </text>

                    {/* 거래량 */}
                    {cs.map((k, i) => {
                        const up = k.c >= k.o
                        return (
                            <rect
                                key={"v" + i}
                                x={geo.xAt(i) - geo.bw / 2}
                                y={geo.yV(k.v)}
                                width={geo.bw}
                                height={Math.max(0.5, geo.volTop + geo.volH - geo.yV(k.v))}
                                fill={up ? upCol : dnCol}
                                opacity={hoverIdx === i ? 0.85 : 0.42}
                            />
                        )
                    })}

                    {/* 날짜축 */}
                    {geo.tickIdx.map((i, j) => (
                        <text
                            key={"t" + j}
                            x={geo.xAt(i)}
                            y={geo.H - 6}
                            fontSize={10}
                            fill={c.faint}
                            textAnchor={j === 0 ? "start" : j === geo.tickIdx.length - 1 ? "end" : "middle"}
                        >
                            {cs[i].t}
                        </text>
                    ))}

                    {/* 크로스헤어 */}
                    {hov && hoverIdx != null ? (
                        <g>
                            <line x1={hovX} x2={hovX} y1={geo.PT} y2={geo.volTop + geo.volH} stroke={c.sub} strokeWidth={0.8} strokeDasharray="3 3" opacity={0.7} />
                            <line x1={geo.PL} x2={geo.W - geo.PR + 3} y1={geo.yP(hov.c)} y2={geo.yP(hov.c)} stroke={c.sub} strokeWidth={0.8} strokeDasharray="3 3" opacity={0.7} />
                            <rect x={geo.W - geo.PR + 4} y={geo.yP(hov.c) - 9} width={geo.PR - 7} height={18} rx={5} fill={c.sub} />
                            <text x={geo.W - geo.PR + 4 + (geo.PR - 7) / 2} y={geo.yP(hov.c) + 4} fontSize={10.5} fontWeight={700} fill={c.card} textAnchor="middle" style={{ fontVariantNumeric: "tabular-nums" }}>
                                {hov.c.toLocaleString(undefined, { maximumFractionDigits: dec })}
                            </text>
                            <circle cx={hovX} cy={geo.yP(hov.c)} r={2.6} fill={c.vt} />
                        </g>
                    ) : null}
                </svg>

                {/* 호버 카드 — 경계에서 좌우 자동 반전 */}
                {hov && hoverIdx != null ? (
                    <div
                        style={{
                            position: "absolute",
                            top: 8,
                            left: cardFlip ? undefined : `${(hovX / geo.W) * 100}%`,
                            right: cardFlip ? `${100 - (hovX / geo.W) * 100}%` : undefined,
                            transform: cardFlip ? "translateX(-8px)" : "translateX(8px)",
                            background: c.card,
                            borderRadius: 10,
                            boxShadow: "0 4px 16px rgba(0,0,0,0.16)",
                            padding: "7px 10px",
                            pointerEvents: "none",
                            fontSize: 10.5,
                            lineHeight: 1.5,
                            color: c.sub,
                            whiteSpace: "nowrap",
                            ...NUM,
                        }}
                    >
                        <div style={{ fontWeight: 800, color: c.ink, fontSize: 11 }}>{hov.t}</div>
                        <div>시 {fmt(hov.o)} · 고 {fmt(hov.h)}</div>
                        <div>저 {fmt(hov.l)} · 종 <b style={{ color: c.ink }}>{fmt(hov.c)}</b></div>
                        {hov.v > 0 ? <div>거래량 {fmtVol(hov.v)}</div> : null}
                    </div>
                ) : null}
            </div>
        </div>
    )
}
