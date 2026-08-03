"use client"
// WatchTable — 관심(최근 검색) 실시간. 구 RealtimeQuotes 대체: 개별 10s 폴링 → 공유 3s 폴러
// (Railway /quotes 30req/60s 제한 대응, tick 플래시 = PM 결함 #4). 클릭 = 링크그룹 전환.
import { useEffect, useRef, useState } from "react"
import { useDark, palette, cardStyle, FONT, NUM } from "@/lib/theme"
import { useQuotes } from "@/lib/quotes"
import { selectTicker } from "@/lib/types"
import StockLogo from "./StockLogo"

const RECENT_KEY = "verity_recent_tickers"

type Recent = { ticker: string; name?: string; market?: string }

function loadTargets(): Recent[] {
    try {
        const raw = localStorage.getItem(RECENT_KEY)
        const arr = raw ? JSON.parse(raw) : []
        if (!Array.isArray(arr)) return []
        return arr.filter((x) => x && /^\d{6}$/.test(String(x.ticker))).slice(0, 10)
    } catch {
        return []
    }
}

export default function WatchTable() {
    const dark = useDark()
    const c = palette(dark)
    const [targets, setTargets] = useState<Recent[]>([])
    const { q, asof } = useQuotes(targets.map((t) => t.ticker))
    const prev = useRef<Record<string, number>>({})

    useEffect(() => {
        setTargets(loadTargets())
        function onChange() {
            setTargets(loadTargets())
        }
        window.addEventListener("verity-ticker", onChange)
        window.addEventListener("storage", onChange)
        return () => {
            window.removeEventListener("verity-ticker", onChange)
            window.removeEventListener("storage", onChange)
        }
    }, [])

    useEffect(() => {
        targets.forEach((t) => {
            const p = q[t.ticker]?.price
            if (typeof p === "number") prev.current[t.ticker] = p
        })
    })

    return (
        <div style={{ ...cardStyle(c, "13px 15px"), fontFamily: FONT, display: "flex", flexDirection: "column", gap: 4 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                    <span style={{ fontSize: 13.5, fontWeight: 800, color: c.ink, letterSpacing: "-0.02em" }}>관심 · 최근 검색</span>
                    <span style={{ width: 5, height: 5, borderRadius: "50%", background: c.green }} />
                </div>
                {asof ? <span style={{ fontSize: 10, color: c.faint, ...NUM }}>{asof}</span> : null}
            </div>

            {targets.length === 0 ? (
                <div style={{ fontSize: 12, color: c.sub, lineHeight: 1.5, padding: "4px 0" }}>
                    종목을 검색하면 실시간 시세가 쌓입니다. (KR · 3초 갱신)
                </div>
            ) : (
                targets.map((t, i) => {
                    const live = q[t.ticker]?.price
                    const cp = q[t.ticker]?.change_pct
                    const was = prev.current[t.ticker]
                    const dir = typeof live === "number" && typeof was === "number" && live !== was ? (live > was ? "up" : "dn") : ""
                    const col = typeof cp !== "number" ? c.faint : cp > 0 ? c.up : cp < 0 ? c.down : c.faint
                    return (
                        <div
                            key={t.ticker}
                            onClick={() => selectTicker(t.ticker, t.name)}
                            style={{ display: "flex", alignItems: "center", gap: 9, padding: "7px 2px", borderTop: i === 0 ? "none" : `1px solid ${c.line}`, cursor: "pointer" }}
                        >
                            <StockLogo ticker={t.ticker} name={t.name} size={22} />
                            <span style={{ fontSize: 12.5, fontWeight: 700, color: c.ink, flex: 1, minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                {t.name || t.ticker}
                            </span>
                            <span key={`${t.ticker}-${live}`} className={dir ? `af-flash-${dir}` : undefined} style={{ fontSize: 12.5, fontWeight: 800, color: c.ink, ...NUM, padding: "0 3px" }}>
                                {typeof live === "number" ? Math.round(live).toLocaleString() : "—"}
                            </span>
                            <span style={{ fontSize: 11, fontWeight: 700, color: col, ...NUM, minWidth: 52, textAlign: "right" }}>
                                {typeof cp === "number" ? `${cp > 0 ? "+" : ""}${cp.toFixed(2)}%` : ""}
                            </span>
                        </div>
                    )
                })
            )}
            <div style={{ fontSize: 9.5, color: c.faint, paddingTop: 5 }}>KIS 공유 토큰 소비(발급 없음) · 매수/매도 지시 아님</div>
        </div>
    )
}
