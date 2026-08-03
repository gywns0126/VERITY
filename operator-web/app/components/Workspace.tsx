"use client"
// Workspace — 중앙 링크그룹 A (승인 목업 v3.1). 선택 종목 = 실시간 헤더 + 호가 10단 래더 +
// 체결강도 + 최근 체결 테이프 + 주문 티켓 + 3종 LLM 종합. 행 클릭(보유/관심/추천/검색) 시 전환.
// 호가 = Railway 구독형: POST /subscribe(최대 10, idle TTL 300s) → /snapshot/{t} 2.5s 폴링.
// 래더 가격 클릭 = 주문가 채움 (국내 HTS 스피드주문 문법).
import { useEffect, useRef, useState } from "react"
import { useDark, palette, cardStyle, FONT, NUM, MAIN_PAD, type Palette } from "@/lib/theme"
import { RAILWAY, fetchRailway } from "@/lib/api"
import { useQuotes } from "@/lib/quotes"
import StockLogo from "./StockLogo"
import { CandleChart, type Candle } from "./ChartModal"
import OrderTicket from "./OrderTicket"
import TriSynthesisPanel from "./TriSynthesisPanel"

type Level = { price?: number; volume?: number }
type Trade = { time?: string; price?: number; volume?: number; side?: string }
type Snap = {
    orderbook?: { asks?: Level[]; bids?: Level[]; total_ask_vol?: number; total_bid_vol?: number }
    trades?: Trade[]
    strength_pct?: number
}

function initialTicker(fallback: string): string {
    try {
        const u = new URL(window.location.href)
        const q = u.searchParams.get("q")
        if (q) return q.toUpperCase()
        const last = localStorage.getItem("verity_last_ticker")
        if (last) return last.toUpperCase()
    } catch {}
    return fallback
}

export default function Workspace({ defaultTicker, names }: { defaultTicker: string; names: Record<string, string> }) {
    const dark = useDark()
    const c = palette(dark)
    const [ticker, setTicker] = useState("")
    const [nameHint, setNameHint] = useState("")
    const [snap, setSnap] = useState<Snap | null>(null)
    const [chartType, setChartType] = useState<"minute" | "daily" | "weekly" | "monthly">("daily")
    const [candles, setCandles] = useState<Candle[]>([])
    const [ordPx, setOrdPx] = useState<number | null>(null)
    const isKR = /^\d{6}$/.test(ticker)
    const { q } = useQuotes(isKR ? [ticker] : [])
    const prevPx = useRef<number | null>(null)

    // 초기 + 링크그룹 수신
    useEffect(() => {
        setTicker(initialTicker(defaultTicker))
        function onTicker(e: Event) {
            const d = (e as CustomEvent).detail
            const t = d && d.ticker ? String(d.ticker).toUpperCase() : ""
            if (t) {
                setTicker(t)
                setNameHint(d.item && d.item.name ? String(d.item.name) : "")
            }
        }
        window.addEventListener("verity-ticker", onTicker)
        return () => window.removeEventListener("verity-ticker", onTicker)
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [defaultTicker])

    // 호가 구독 + 스냅샷 폴링 (KR 만)
    useEffect(() => {
        setSnap(null)
        setOrdPx(null)
        if (!isKR || !ticker) return
        let stop = false
        async function sub() {
            try {
                await fetch(`${RAILWAY}/subscribe`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ tickers: [ticker] }),
                })
            } catch {}
        }
        async function pull() {
            const r = await fetchRailway<Snap>(`snapshot/${ticker}`)
            if (!stop && r.ok) setSnap(r.data)
        }
        sub().then(pull)
        const t1 = setInterval(pull, 2500)
        const t2 = setInterval(sub, 240_000) // idle TTL 300s 유지
        return () => {
            stop = true
            clearInterval(t1)
            clearInterval(t2)
        }
    }, [ticker, isKR])

    // 종목 캔들 — Railway /chart (KIS 일/주/월/분봉, 토스 격차 해소 2단계). 분봉만 30초 폴.
    useEffect(() => {
        setCandles([])
        if (!isKR || !ticker) return
        let stop = false
        async function pull() {
            const r = await fetchRailway<Record<string, Array<{ date?: string; time?: string; open?: number; high?: number; low?: number; close?: number; volume?: number }>>>(
                `chart/${ticker}?type=${chartType}`
            )
            if (stop || !r.ok) return
            const rows = r.data[chartType]
            if (!Array.isArray(rows)) return
            const cs: Candle[] = rows
                .map((x) => ({
                    t: x.time
                        ? String(x.time)
                        : String(x.date || "").length === 8
                          ? `${String(x.date).slice(4, 6)}.${String(x.date).slice(6, 8)}`
                          : String(x.date || ""),
                    o: Number(x.open) || 0,
                    h: Number(x.high) || 0,
                    l: Number(x.low) || 0,
                    c: Number(x.close) || 0,
                    v: Number(x.volume) || 0,
                }))
                .filter((x) => x.h > 0)
            setCandles(cs)
        }
        pull()
        if (chartType === "minute") {
            const t = setInterval(pull, 30000)
            return () => {
                stop = true
                clearInterval(t)
            }
        }
        return () => {
            stop = true
        }
    }, [ticker, isKR, chartType])

    const live = isKR ? q[ticker]?.price : undefined
    const cp = isKR ? q[ticker]?.change_pct : undefined
    const dir = typeof live === "number" && prevPx.current !== null && live !== prevPx.current ? (live > prevPx.current ? "up" : "dn") : ""
    useEffect(() => {
        if (typeof live === "number") prevPx.current = live
    })
    const name = nameHint || names[ticker] || ""
    const cpCol = typeof cp !== "number" ? c.faint : cp > 0 ? c.up : cp < 0 ? c.down : c.faint

    const ob = snap?.orderbook || {}
    const asks = (ob.asks || []).filter((l) => typeof l.price === "number").slice(0, 10)
    const bids = (ob.bids || []).filter((l) => typeof l.price === "number").slice(0, 10)
    const maxVol = Math.max(1, ...asks.map((l) => l.volume || 0), ...bids.map((l) => l.volume || 0))
    const strength = typeof snap?.strength_pct === "number" ? snap.strength_pct : null
    const trades = (snap?.trades || []).filter((t) => typeof t.price === "number").slice(0, 8)

    if (!ticker) return null

    return (
        <div style={{ ...cardStyle(c, MAIN_PAD), fontFamily: FONT, display: "flex", flexDirection: "column", gap: 12 }}>
            {/* 헤더 — 선택 종목 실시간 */}
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <StockLogo ticker={ticker} name={name} size={28} />
                <div style={{ display: "flex", flexDirection: "column", gap: 0, minWidth: 0 }}>
                    <span style={{ fontSize: 16, fontWeight: 800, color: c.ink, letterSpacing: "-0.02em" }}>{name || ticker}</span>
                    <span style={{ fontSize: 10.5, color: c.faint, ...NUM }}>{ticker}</span>
                </div>
                {isKR ? (
                    <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginLeft: 6 }}>
                        <span key={`ws-${live}`} className={dir ? `af-flash-${dir}` : undefined} style={{ fontSize: 22, fontWeight: 800, color: c.ink, ...NUM, padding: "0 4px" }}>
                            {typeof live === "number" ? Math.round(live).toLocaleString() : "—"}
                        </span>
                        <span style={{ fontSize: 13, fontWeight: 700, color: cpCol, ...NUM }}>
                            {typeof cp === "number" ? `${cp > 0 ? "+" : ""}${cp.toFixed(2)}%` : ""}
                        </span>
                    </div>
                ) : (
                    <span style={{ fontSize: 11, color: c.faint }}>US 실시간 시세 미지원 (전일종가 체계)</span>
                )}
                {isKR && typeof q[ticker]?.low === "number" && typeof q[ticker]?.high === "number" && (q[ticker]!.high as number) > (q[ticker]!.low as number) ? (
                    <DayRange c={c} low={q[ticker]!.low as number} high={q[ticker]!.high as number} px={typeof live === "number" ? live : null} />
                ) : null}
                {strength !== null ? (
                    <span
                        style={{ marginLeft: "auto", fontSize: 11.5, fontWeight: 800, color: strength >= 100 ? c.up : c.down, background: strength >= 100 ? c.upS : c.downS, borderRadius: 8, padding: "4px 9px", ...NUM }}
                        title="체결강도 = 체결 매수/매도 비율 (100% 초과 = 매수 우위)"
                    >
                        체결강도 {strength.toFixed(1)}%
                    </span>
                ) : null}
            </div>

            {/* 종목 캔들 — 분/일/주/월 (KIS 실데이터) */}
            {isKR ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                    <div style={{ display: "flex", gap: 6 }}>
                        {([["minute", "분봉"], ["daily", "일봉"], ["weekly", "주봉"], ["monthly", "월봉"]] as Array<["minute" | "daily" | "weekly" | "monthly", string]>).map(([k, label]) => (
                            <button
                                key={k}
                                onClick={() => setChartType(k)}
                                style={{ border: "none", borderRadius: 999, padding: "4px 11px", fontSize: 10.5, fontWeight: 800, cursor: "pointer", fontFamily: FONT, background: chartType === k ? c.vtS : c.hi, color: chartType === k ? c.vt : c.faint }}
                            >
                                {label}
                            </button>
                        ))}
                        <span style={{ marginLeft: "auto", fontSize: 9.5, color: c.faint, alignSelf: "center" }}>
                            KIS · {chartType === "minute" ? "당일 분봉 · 30초 갱신" : "SMA5 · SMA20"}
                        </span>
                    </div>
                    {candles.length > 5 ? (
                        <CandleChart cs={candles} c={c} dec={0} />
                    ) : (
                        <div style={{ height: 120, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11.5, color: c.faint, background: c.hi, borderRadius: 12 }}>
                            차트 불러오는 중… (장외 분봉은 빈 값일 수 있음)
                        </div>
                    )}
                </div>
            ) : null}

            {/* 본문 — 호가 래더 + 티켓 */}
            {isKR ? (
                <div style={{ display: "grid", gridTemplateColumns: "minmax(240px, 320px) minmax(200px, 1fr)", gap: 14, alignItems: "start" }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, fontWeight: 700, color: c.faint, padding: "0 4px 4px" }}>
                            <span>잔량</span>
                            <span>호가 (클릭=주문가)</span>
                        </div>
                        {asks.length === 0 && bids.length === 0 ? (
                            <div style={{ fontSize: 11.5, color: c.faint, padding: "10px 4px", lineHeight: 1.5 }}>
                                호가 수신 대기 중… (구독 직후 수 초 소요, 장외에는 빈 값)
                            </div>
                        ) : (
                            <>
                                {[...asks].reverse().map((l, i) => (
                                    <LadderRow key={`a${i}`} c={c} price={l.price!} vol={l.volume || 0} maxVol={maxVol} side="ask" onPick={setOrdPx} />
                                ))}
                                <div style={{ display: "flex", justifyContent: "center", padding: "4px 0", background: c.hi, borderRadius: 8, margin: "3px 0" }}>
                                    <span style={{ fontSize: 12.5, fontWeight: 800, color: c.ink, ...NUM }}>
                                        {typeof live === "number" ? Math.round(live).toLocaleString() : "—"}
                                    </span>
                                </div>
                                {bids.map((l, i) => (
                                    <LadderRow key={`b${i}`} c={c} price={l.price!} vol={l.volume || 0} maxVol={maxVol} side="bid" onPick={setOrdPx} />
                                ))}
                                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: c.faint, padding: "5px 4px 0", ...NUM }}>
                                    <span>매도 {fmtVol(ob.total_ask_vol)}</span>
                                    <span>매수 {fmtVol(ob.total_bid_vol)}</span>
                                </div>
                            </>
                        )}
                        {trades.length ? (
                            <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 2 }}>
                                <span style={{ fontSize: 9.5, fontWeight: 700, color: c.faint, padding: "0 4px" }}>최근 체결</span>
                                {trades.map((t, i) => (
                                    <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: c.sub, padding: "1px 4px", ...NUM }}>
                                        <span style={{ color: c.faint }}>{String(t.time || "").slice(0, 8)}</span>
                                        <span style={{ fontWeight: 700, color: c.ink }}>{Math.round(t.price!).toLocaleString()}</span>
                                        <span>{fmtVol(t.volume)}</span>
                                    </div>
                                ))}
                            </div>
                        ) : null}
                    </div>

                    <OrderTicket ticker={ticker} name={name} presetPrice={ordPx} livePrice={typeof live === "number" ? live : null} />
                </div>
            ) : null}

            {/* 3종 LLM 종합 — 동일 링크그룹 (자체 verity-ticker 수신) */}
            <div style={{ borderTop: `1px solid ${c.line}`, paddingTop: 12 }}>
                <TriSynthesisPanel />
            </div>
        </div>
    )
}

// 1일 범위 바 — 토스 종목 헤더 문법 (저가~고가 트랙 + 현재가 위치 마커). /quotes 실데이터.
function DayRange({ c, low, high, px }: { c: Palette; low: number; high: number; px: number | null }) {
    const pos = px !== null && high > low ? Math.min(100, Math.max(0, ((px - low) / (high - low)) * 100)) : null
    return (
        <div style={{ display: "flex", alignItems: "center", gap: 7, minWidth: 170 }}>
            <span style={{ fontSize: 9.5, color: c.faint, ...NUM, flexShrink: 0 }}>{Math.round(low).toLocaleString()}</span>
            <div style={{ position: "relative", flex: 1, height: 4, borderRadius: 999, background: c.track, minWidth: 70 }}>
                {pos !== null ? (
                    <span style={{ position: "absolute", left: `${pos}%`, top: -2.5, width: 9, height: 9, borderRadius: "50%", background: c.vt, transform: "translateX(-50%)", boxShadow: "0 0 0 2px rgba(108,92,231,0.25)" }} />
                ) : null}
            </div>
            <span style={{ fontSize: 9.5, color: c.faint, ...NUM, flexShrink: 0 }}>{Math.round(high).toLocaleString()}</span>
            <span style={{ fontSize: 9, color: c.faint, flexShrink: 0 }}>1일</span>
        </div>
    )
}

function fmtVol(v?: number): string {
    if (typeof v !== "number" || !isFinite(v)) return "—"
    if (v >= 1e6) return (v / 1e6).toFixed(1) + "M"
    if (v >= 1e3) return (v / 1e3).toFixed(1) + "K"
    return String(Math.round(v))
}

function LadderRow({ c, price, vol, maxVol, side, onPick }: { c: Palette; price: number; vol: number; maxVol: number; side: "ask" | "bid"; onPick: (p: number) => void }) {
    // 매도호가=파랑 / 매수호가=빨강 (국내 HTS 관례). 잔량 막대 = 채움색만, 외곽선 0.
    const col = side === "ask" ? c.down : c.up
    const colS = side === "ask" ? c.downS : c.upS
    const w = Math.min(100, (vol / maxVol) * 100)
    return (
        <div
            onClick={() => onPick(price)}
            onMouseEnter={(e) => { e.currentTarget.style.background = c.hi }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent" }}
            style={{ display: "grid", gridTemplateColumns: "1fr 78px", gap: 6, alignItems: "center", padding: "2px 5px", cursor: "pointer", borderRadius: 6 }}
        >
            <div style={{ position: "relative", height: 16, display: "flex", alignItems: "center", justifyContent: "flex-end" }}>
                <div style={{ position: "absolute", right: 0, top: 1, bottom: 1, width: `${w}%`, background: colS, borderRadius: 3 }} />
                <span style={{ position: "relative", fontSize: 10.5, color: c.sub, ...NUM }}>{vol ? vol.toLocaleString() : ""}</span>
            </div>
            <span style={{ fontSize: 12.5, fontWeight: 800, color: col, textAlign: "right", ...NUM }}>{Math.round(price).toLocaleString()}</span>
        </div>
    )
}
