"use client"
// ChartModal — 시세 카드 클릭 상세 차트. v2 (PM 2026-08-03 "토스와 차이 보여?"):
// 라인 확대본 → 진짜 캔들차트(OHLC 캔들 + 거래량 서브차트 + SMA 5/20 + 가격 눈금 + 날짜축 +
// 현재가 점선 라벨). 전부 실데이터 — KR 지수 = Railway /index_daily(KIS 일봉 90일),
// 크립토 = Binance klines OHLCV(1분/15분/일봉, 5초 폴). 환율·미장 = 수집 시계열 라인(정직 라벨).
// 외곽선 0 · Esc/배경 닫기.
import { useEffect, useState } from "react"
import { useDark, palette, FONT, NUM, type Palette } from "@/lib/theme"
import { fetchRailway } from "@/lib/api"
import type { MarketExplain } from "@/lib/types"

export type ChartTarget = {
    kind: "macro" | "crypto" | "krindex"
    name: string
    symbol?: string          // crypto: BTCUSDT
    indexCd?: string         // krindex: 0001 코스피 / 1001 코스닥
    unit?: string
    series?: number[]        // macro: 수집 시계열
    value?: number | null
    changePct?: number | null
    explain?: MarketExplain  // krindex: daily_report 발췌 (요인·전략·리스크·내일 관점)
}

export type Candle = { t: string; o: number; h: number; l: number; c: number; v: number }

const INTERVALS: Array<{ k: string; label: string; limit: number }> = [
    { k: "1m", label: "1분", limit: 120 },
    { k: "15m", label: "15분", limit: 120 },
    { k: "1d", label: "일봉", limit: 120 },
]

function fmtT(ms: number, interval: string): string {
    const d = new Date(ms)
    if (interval === "1d") return `${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
}

export default function ChartModal({ target, onClose }: { target: ChartTarget; onClose: () => void }) {
    const dark = useDark()
    const c = palette(dark)
    const [interval_, setInterval_] = useState("1m")
    const [candles, setCandles] = useState<Candle[]>([])

    useEffect(() => {
        function onKey(e: KeyboardEvent) {
            if (e.key === "Escape") onClose()
        }
        window.addEventListener("keydown", onKey)
        const prev = document.body.style.overflow
        document.body.style.overflow = "hidden"
        return () => {
            window.removeEventListener("keydown", onKey)
            document.body.style.overflow = prev
        }
    }, [onClose])

    // 데이터 — 크립토(klines OHLCV 5초 폴) / KR지수(KIS 일봉 30초 폴) / macro(시계열 → 의사 캔들 없음, 라인)
    useEffect(() => {
        let stop = false
        setCandles([])
        async function pullCrypto() {
            if (!target.symbol) return
            const iv = INTERVALS.find((x) => x.k === interval_) || INTERVALS[0]
            try {
                const r = await fetch(
                    `https://data-api.binance.vision/api/v3/klines?symbol=${target.symbol}&interval=${iv.k}&limit=${iv.limit}`,
                    { cache: "no-store" }
                )
                if (!r.ok) return
                const d = await r.json()
                if (stop || !Array.isArray(d)) return
                const cs: Candle[] = d
                    .map((row: unknown[]) => ({
                        t: fmtT(Number(row[0]), iv.k),
                        o: parseFloat(String(row[1])),
                        h: parseFloat(String(row[2])),
                        l: parseFloat(String(row[3])),
                        c: parseFloat(String(row[4])),
                        v: parseFloat(String(row[5])),
                    }))
                    .filter((x: Candle) => isFinite(x.h) && x.h > 0)
                setCandles(cs)
            } catch {}
        }
        async function pullIndex() {
            if (!target.indexCd) return
            const r = await fetchRailway<{ candles?: Array<{ date?: string; open?: number; high?: number; low?: number; close?: number; volume?: number }> }>(
                `index_daily/${target.indexCd}`
            )
            if (stop || !r.ok || !Array.isArray(r.data.candles)) return
            const cs: Candle[] = r.data.candles
                .map((x) => ({
                    t: String(x.date || "").length === 8 ? `${String(x.date).slice(4, 6)}.${String(x.date).slice(6, 8)}` : String(x.date || ""),
                    o: Number(x.open) || 0,
                    h: Number(x.high) || 0,
                    l: Number(x.low) || 0,
                    c: Number(x.close) || 0,
                    v: Number(x.volume) || 0,
                }))
                .filter((x) => x.h > 0)
            setCandles(cs)
        }
        if (target.kind === "crypto") {
            pullCrypto()
            const t = setInterval(pullCrypto, 5000)
            return () => {
                stop = true
                clearInterval(t)
            }
        }
        if (target.kind === "krindex") {
            pullIndex()
            const t = setInterval(pullIndex, 30000)
            return () => {
                stop = true
                clearInterval(t)
            }
        }
        return () => {
            stop = true
        }
    }, [target, interval_])

    const isCrypto = target.kind === "crypto"
    const isIndex = target.kind === "krindex"
    const last = candles.length ? candles[candles.length - 1] : null
    const first = candles.length ? candles[0] : null
    const rangeCp = last && first && first.o > 0 ? ((last.c - first.o) / first.o) * 100 : null
    const headPx = last ? last.c : target.value ?? null
    const headCp = isCrypto ? rangeCp : target.changePct ?? null
    const col = headCp == null ? c.faint : headCp > 0 ? c.up : headCp < 0 ? c.down : c.faint
    const dec = isCrypto && (headPx || 0) < 1000 ? 2 : isIndex ? 2 : 0
    const fmt = (v: number) => (isCrypto ? "$" : "") + v.toLocaleString(undefined, { maximumFractionDigits: dec }) + (target.unit || "")
    const macroSeries = (target.series || []).filter((v) => typeof v === "number" && isFinite(v))

    return (
        <div
            onClick={onClose}
            style={{ position: "fixed", inset: 0, zIndex: 90, background: "rgba(10,12,16,0.55)", display: "flex", alignItems: "center", justifyContent: "center", padding: 20, fontFamily: FONT }}
        >
            <div
                onClick={(e) => e.stopPropagation()}
                style={{ background: c.card, borderRadius: 18, boxShadow: "0 18px 60px rgba(0,0,0,0.35)", width: "min(920px, 96vw)", padding: "18px 20px 14px", display: "flex", flexDirection: "column", gap: 10 }}
            >
                {/* 헤더 — 이름·현재가·등락 + OHLC 요약 + 신선도 */}
                <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 16, fontWeight: 800, color: c.ink, letterSpacing: "-0.02em" }}>{target.name}</span>
                    <span style={{ fontSize: 21, fontWeight: 800, color: c.ink, ...NUM }}>{headPx != null ? fmt(headPx) : "—"}</span>
                    <span style={{ fontSize: 13, fontWeight: 700, color: col, ...NUM }}>
                        {headCp != null ? `${headCp > 0 ? "+" : ""}${headCp.toFixed(2)}%` : ""}
                        {isCrypto ? <span style={{ color: c.faint, fontWeight: 500 }}> 구간</span> : null}
                    </span>
                    {last ? (
                        <span style={{ fontSize: 10.5, color: c.sub, ...NUM }}>
                            시 {fmt(last.o)} · 고 <span style={{ color: c.up }}>{fmt(last.h)}</span> · 저 <span style={{ color: c.down }}>{fmt(last.l)}</span> · 종 {fmt(last.c)}
                        </span>
                    ) : null}
                    <span style={{ marginLeft: "auto", fontSize: 10, color: c.faint }}>
                        {isCrypto ? "실시간 · Binance · 5초" : isIndex ? "KIS 일봉 · 90일 · 30초 갱신" : "수집 시계열 · 약 30분 주기"}
                    </span>
                    <button onClick={onClose} style={{ border: "none", background: c.hi, color: c.sub, borderRadius: 999, padding: "5px 12px", fontSize: 11, fontWeight: 800, cursor: "pointer", fontFamily: FONT }}>
                        닫기 (Esc)
                    </button>
                </div>

                {isCrypto ? (
                    <div style={{ display: "flex", gap: 6 }}>
                        {INTERVALS.map((iv) => (
                            <button
                                key={iv.k}
                                onClick={() => setInterval_(iv.k)}
                                style={{ border: "none", borderRadius: 999, padding: "5px 12px", fontSize: 11, fontWeight: 800, cursor: "pointer", fontFamily: FONT, background: interval_ === iv.k ? c.vtS : c.hi, color: interval_ === iv.k ? c.vt : c.faint }}
                            >
                                {iv.label}
                            </button>
                        ))}
                    </div>
                ) : null}

                {candles.length > 5 ? (
                    <CandleChart cs={candles} c={c} dec={dec} />
                ) : macroSeries.length > 1 ? (
                    <LineChart c={c} data={macroSeries} color={col} />
                ) : (
                    <div style={{ height: 320, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12.5, color: c.faint }}>
                        차트 불러오는 중…
                    </div>
                )}

                {/* 왜 움직였나 · 향후 관점 — 자기 리포트(daily_report) 발췌. RULE 7: 가설·예측 아님 라벨 */}
                {isIndex && target.explain && (target.explain.analysis || target.explain.outlook) ? (
                    <div style={{ background: c.hi, borderRadius: 12, padding: "11px 14px", display: "flex", flexDirection: "column", gap: 6 }}>
                        <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
                            <span style={{ fontSize: 11, fontWeight: 800, color: c.vt }}>오늘 시장 설명</span>
                            <span style={{ fontSize: 9.5, color: c.faint }}>자기 리포트 · 매일 생성 · 가설 — 예측 아님</span>
                        </div>
                        {([
                            ["분석", target.explain.analysis],
                            ["전략", target.explain.strategy],
                            ["리스크", target.explain.risk],
                            ["내일 관점", target.explain.outlook],
                        ] as Array<[string, string | undefined]>).map(([k, v]) =>
                            v ? (
                                <div key={k} style={{ fontSize: 12, color: c.sub, lineHeight: 1.5 }}>
                                    <span style={{ fontWeight: 800, color: c.ink }}>{k}</span> {v}
                                </div>
                            ) : null
                        )}
                    </div>
                ) : null}

                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, color: c.faint }}>
                    <span>{candles.length ? `SMA5 · SMA20 · ${candles.length}봉` : ""}</span>
                    <span>사실 시세 · 매수/매도 지시 아님</span>
                </div>
            </div>
        </div>
    )
}

// ── 캔들차트 (SVG 자체 렌더 — 캔들 + 거래량 + SMA + 눈금/축 + 현재가 라벨) ──
function sma(cs: Candle[], p: number): Array<number | null> {
    const out: Array<number | null> = []
    let sum = 0
    for (let i = 0; i < cs.length; i++) {
        sum += cs[i].c
        if (i >= p) sum -= cs[i - p].c
        out.push(i >= p - 1 ? sum / p : null)
    }
    return out
}

export function CandleChart({ cs, c, dec }: { cs: Candle[]; c: Palette; dec: number }) {
    const W = 920, PT = 8, PL = 6, PR = 74, PB = 20
    const priceH = 268, gapH = 10, volH = 56
    const H = PT + priceH + gapH + volH + PB
    const n = cs.length
    const plotW = W - PL - PR
    const xw = plotW / n
    const bw = Math.max(2, Math.min(11, xw * 0.62))
    const hi = Math.max(...cs.map((k) => k.h))
    const lo = Math.min(...cs.map((k) => k.l))
    const rng = hi - lo || 1
    const y = (v: number) => PT + ((hi - v) / rng) * priceH
    const x = (i: number) => PL + i * xw + xw / 2
    const volMax = Math.max(1, ...cs.map((k) => k.v))
    const volTop = PT + priceH + gapH
    const vy = (v: number) => volTop + volH - (v / volMax) * volH
    const s5 = sma(cs, 5)
    const s20 = sma(cs, 20)
    const line = (arr: Array<number | null>) =>
        arr.map((v, i) => (v === null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`)).filter(Boolean).join(" ")
    const gridN = 4
    const lastC = cs[n - 1].c
    const xTickIdx = [0, Math.floor(n / 3), Math.floor((2 * n) / 3), n - 1]
    const fmtY = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: dec })

    return (
        <div style={{ background: c.hi, borderRadius: 12, padding: "8px 4px 2px" }}>
            <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
                {/* 가격 눈금 + 우측 라벨 */}
                {Array.from({ length: gridN + 1 }, (_, g) => {
                    const v = hi - (rng * g) / gridN
                    const yy = y(v)
                    return (
                        <g key={g}>
                            <line x1={PL} x2={W - PR + 4} y1={yy} y2={yy} stroke={c.line} strokeWidth={1} strokeDasharray="3 4" />
                            <text x={W - PR + 8} y={yy + 4} fontSize={11} fill={c.faint} style={{ fontVariantNumeric: "tabular-nums" }}>{fmtY(v)}</text>
                        </g>
                    )
                })}
                {/* 캔들 */}
                {cs.map((k, i) => {
                    const up = k.c >= k.o
                    const col = up ? c.up : c.down
                    const cx = x(i)
                    const top = y(Math.max(k.o, k.c))
                    const bot = y(Math.min(k.o, k.c))
                    return (
                        <g key={i}>
                            <line x1={cx} x2={cx} y1={y(k.h)} y2={y(k.l)} stroke={col} strokeWidth={1} />
                            <rect x={cx - bw / 2} y={top} width={bw} height={Math.max(1, bot - top)} fill={col} rx={1} />
                        </g>
                    )
                })}
                {/* SMA 5/20 */}
                <polyline points={line(s5)} fill="none" stroke={c.green} strokeWidth={1.3} strokeLinejoin="round" />
                <polyline points={line(s20)} fill="none" stroke={c.amber} strokeWidth={1.3} strokeLinejoin="round" />
                {/* 현재가 점선 + 라벨 */}
                <line x1={PL} x2={W - PR + 4} y1={y(lastC)} y2={y(lastC)} stroke={c.vt} strokeWidth={1} strokeDasharray="5 4" />
                <rect x={W - PR + 5} y={y(lastC) - 9} width={PR - 8} height={18} rx={5} fill={c.vt} />
                <text x={W - PR + 5 + (PR - 8) / 2} y={y(lastC) + 4} fontSize={11} fontWeight={700} fill="#fff" textAnchor="middle" style={{ fontVariantNumeric: "tabular-nums" }}>{fmtY(lastC)}</text>
                {/* 거래량 */}
                {cs.map((k, i) => {
                    const up = k.c >= k.o
                    return <rect key={`v${i}`} x={x(i) - bw / 2} y={vy(k.v)} width={bw} height={Math.max(1, volTop + volH - vy(k.v))} fill={up ? c.upS : c.downS} stroke={up ? c.up : c.down} strokeWidth={0.4} />
                })}
                {/* 날짜축 */}
                {xTickIdx.map((i, j) => (
                    <text key={j} x={x(i)} y={H - 6} fontSize={10.5} fill={c.faint} textAnchor={j === 0 ? "start" : j === xTickIdx.length - 1 ? "end" : "middle"}>{cs[i].t}</text>
                ))}
            </svg>
        </div>
    )
}

// 수집 시계열 라인 (환율·미장 등 — 캔들 소스 없는 자산, 정직 라벨과 세트)
function LineChart({ c, data, color }: { c: Palette; data: number[]; color: string }) {
    const W = 100, H = 34, PAD = 1.5
    const mn = Math.min(...data), mx = Math.max(...data), rng = mx - mn || 1
    const pts = data.map((v, i) => `${((i / (data.length - 1)) * W).toFixed(2)},${(H - PAD - ((v - mn) / rng) * (H - PAD * 2)).toFixed(2)}`)
    return (
        <div style={{ background: c.hi, borderRadius: 12, padding: "10px 8px 6px" }}>
            <svg width="100%" height={300} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ display: "block" }}>
                <polyline points={`${PAD},${H - PAD} ${pts.join(" ")} ${W},${H - PAD}`} fill={color} opacity={0.08} stroke="none" />
                <polyline points={pts.join(" ")} fill="none" strokeWidth={1.4} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" style={{ stroke: color }} />
            </svg>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: c.faint, padding: "4px 4px 2px" }}>
                <span style={{ fontVariantNumeric: "tabular-nums" }}>저 {mn.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
                <span>{data.length}pt</span>
                <span style={{ fontVariantNumeric: "tabular-nums" }}>고 {mx.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
            </div>
        </div>
    )
}
