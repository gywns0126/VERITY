"use client"
// ChartModal — 시세 카드 클릭 시 상세 차트 (PM 2026-08-03 "각 시세 누르면 상세 그래프").
// 크립토 = Binance 분봉 실시간(1분/15분/1일, 5초 폴 — 공개 알파네스트 차트는 종가지만 여기선 실시간).
// 지수·환율·금리 = 보유 수집 시계열 확대(약 30분 주기 — 실시간 아님을 라벨로 명시, 정직 표기).
// 외곽선 0 — 카드 채움 + 그림자. Esc/배경 클릭 닫기.
import { useCallback, useEffect, useState } from "react"
import { useDark, palette, FONT, NUM, type Palette } from "@/lib/theme"

export type ChartTarget = {
    kind: "macro" | "crypto"
    name: string
    symbol?: string          // crypto: BTCUSDT
    unit?: string            // macro: 원, %
    series?: number[]        // macro: sparkline
    value?: number | null
    changePct?: number | null
}

const INTERVALS: Array<{ k: string; label: string; limit: number }> = [
    { k: "1m", label: "1분", limit: 180 },
    { k: "15m", label: "15분", limit: 192 },
    { k: "1d", label: "일봉", limit: 180 },
]

export default function ChartModal({ target, onClose }: { target: ChartTarget; onClose: () => void }) {
    const dark = useDark()
    const c = palette(dark)
    const [interval_, setInterval_] = useState("1m")
    const [closes, setCloses] = useState<number[]>([])
    const [live, setLive] = useState<{ px: number | null; cp: number | null }>({ px: target.value ?? null, cp: target.changePct ?? null })

    // Esc 닫기 + 배경 스크롤 잠금
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

    // 크립토 = klines 폴링 (검증 2026-08-03: [openTime,o,h,l,c,...] close=idx4)
    const pull = useCallback(async () => {
        if (target.kind !== "crypto" || !target.symbol) return
        const iv = INTERVALS.find((x) => x.k === interval_) || INTERVALS[0]
        try {
            const r = await fetch(
                `https://data-api.binance.vision/api/v3/klines?symbol=${target.symbol}&interval=${iv.k}&limit=${iv.limit}`,
                { cache: "no-store" }
            )
            if (!r.ok) return
            const d = await r.json()
            if (Array.isArray(d) && d.length) {
                const cs = d.map((row: unknown[]) => parseFloat(String(row[4]))).filter((v: number) => isFinite(v))
                setCloses(cs)
                const last = cs[cs.length - 1]
                const first = cs[0]
                setLive({ px: last, cp: first > 0 ? ((last - first) / first) * 100 : null })
            }
        } catch {}
    }, [target.kind, target.symbol, interval_])

    useEffect(() => {
        if (target.kind !== "crypto") {
            setCloses((target.series || []).filter((v) => typeof v === "number" && isFinite(v)))
            return
        }
        setCloses([])
        pull()
        const t = setInterval(pull, 5000)
        return () => clearInterval(t)
    }, [target, pull])

    const isCrypto = target.kind === "crypto"
    const cp = isCrypto ? live.cp : target.changePct ?? null
    const col = cp == null ? c.faint : cp > 0 ? c.up : cp < 0 ? c.down : c.faint
    const px = isCrypto ? live.px : target.value ?? null
    const mn = closes.length ? Math.min(...closes) : null
    const mx = closes.length ? Math.max(...closes) : null
    const fmt = (v: number) =>
        (isCrypto ? "$" : "") + v.toLocaleString(undefined, { maximumFractionDigits: v >= 1000 ? 0 : 2 }) + (target.unit || "")

    return (
        <div
            onClick={onClose}
            style={{ position: "fixed", inset: 0, zIndex: 90, background: "rgba(10,12,16,0.55)", display: "flex", alignItems: "center", justifyContent: "center", padding: 20, fontFamily: FONT }}
        >
            <div
                onClick={(e) => e.stopPropagation()}
                style={{ background: c.card, borderRadius: 18, boxShadow: "0 18px 60px rgba(0,0,0,0.35)", width: "min(860px, 96vw)", padding: "18px 20px 16px", display: "flex", flexDirection: "column", gap: 12 }}
            >
                <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 16, fontWeight: 800, color: c.ink, letterSpacing: "-0.02em" }}>{target.name}</span>
                    <span style={{ fontSize: 20, fontWeight: 800, color: c.ink, ...NUM }}>{px != null ? fmt(px) : "—"}</span>
                    <span style={{ fontSize: 13, fontWeight: 700, color: col, ...NUM }}>
                        {cp != null ? `${cp > 0 ? "+" : ""}${cp.toFixed(2)}%` : ""}
                        {isCrypto ? <span style={{ color: c.faint, fontWeight: 500 }}> · 구간 기준</span> : null}
                    </span>
                    <span style={{ marginLeft: "auto", fontSize: 10.5, color: c.faint }}>
                        {isCrypto ? "실시간 · Binance · 5초 갱신" : "수집 시계열 · 약 30분 주기 · 실시간 아님"}
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

                {closes.length > 1 ? (
                    <>
                        <BigChart c={c} data={closes} color={col} />
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: c.faint, ...NUM }}>
                            <span>저 {mn != null ? fmt(mn) : "—"}</span>
                            <span>{closes.length}pt</span>
                            <span>고 {mx != null ? fmt(mx) : "—"}</span>
                        </div>
                    </>
                ) : (
                    <div style={{ height: 280, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12.5, color: c.faint }}>
                        {isCrypto ? "차트 불러오는 중…" : "시계열 없음"}
                    </div>
                )}

                <div style={{ fontSize: 9.5, color: c.faint }}>사실 시세 · 매수/매도 지시 아님</div>
            </div>
        </div>
    )
}

function BigChart({ c, data, color }: { c: Palette; data: number[]; color: string }) {
    const W = 100, H = 34, PAD = 1.5
    const mn = Math.min(...data), mx = Math.max(...data), rng = mx - mn || 1
    const pts = data.map((v, i) => {
        const x = (i / (data.length - 1)) * W
        const y = H - PAD - ((v - mn) / rng) * (H - PAD * 2)
        return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    const lastX = W, lastY = H - PAD - ((data[data.length - 1] - mn) / rng) * (H - PAD * 2)
    return (
        <div style={{ background: c.hi, borderRadius: 12, padding: "10px 8px 6px" }}>
            <svg width="100%" height={280} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ display: "block" }}>
                <polyline
                    points={`${PAD},${H - PAD} ${pts.join(" ")} ${W},${H - PAD}`}
                    fill={color}
                    opacity={0.08}
                    stroke="none"
                />
                <polyline points={pts.join(" ")} fill="none" strokeWidth={1.4} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" style={{ stroke: color }} />
                <circle cx={lastX} cy={lastY} r={0.9} style={{ fill: color }} />
            </svg>
        </div>
    )
}
