"use client"
// RealtimeQuotes — 실시간 시세 (오퍼레이터 본인 이용). 공개 알파네스트 디자인.
// 소스: Railway /quotes (fetch_price = KIS_SHARED_TOKEN 순수 소비자, 발급 X · RULE 1 안전).
// 대상 = 최근 검색 종목(verity_recent_tickers, 이름 포함) + verity-ticker 선택분. KR 6자리만(v1, US 후속).
// 자동(폴링 토글) + 수동(새로고침). 🚨 외곽선 금지 — 카드 채움색만. 상승=빨강/하락=파랑, tabular-nums.
import { useCallback, useEffect, useRef, useState } from "react"
import { useDark, palette, cardStyle, FONT, NUM } from "@/lib/theme"
import { fetchRailway } from "@/lib/api"

const RECENT_KEY = "verity_recent_tickers"
const POLL_MS = 10000

type Recent = { ticker: string; name?: string; market?: string }
type Quote = { price?: number; prev_close?: number; change?: number; change_pct?: number; volume?: number }

function loadTargets(): Recent[] {
    try {
        const raw = localStorage.getItem(RECENT_KEY)
        const arr = raw ? JSON.parse(raw) : []
        if (!Array.isArray(arr)) return []
        // KR 6자리만 (fetch_price = 국내). US 는 v1 미지원.
        return arr.filter((x) => x && /^\d{6}$/.test(String(x.ticker))).slice(0, 10)
    } catch {
        return []
    }
}

export default function RealtimeQuotes() {
    const dark = useDark()
    const c = palette(dark)
    const [targets, setTargets] = useState<Recent[]>([])
    const [quotes, setQuotes] = useState<Record<string, Quote>>({})
    const [auto, setAuto] = useState(true)
    const [asof, setAsof] = useState("")
    const [status, setStatus] = useState<"idle" | "loading" | "ok" | "error">("idle")
    const timer = useRef<ReturnType<typeof setInterval> | null>(null)

    const codes = targets.map((t) => t.ticker)
    const codesKey = codes.join(",")

    const refresh = useCallback(async () => {
        if (!codesKey) {
            setQuotes({})
            setStatus("idle")
            return
        }
        setStatus("loading")
        const r = await fetchRailway<{ quotes?: Record<string, Quote>; asof?: string }>(`quotes?tickers=${codesKey}`)
        if (r.ok) {
            setQuotes(r.data.quotes || {})
            setAsof(String(r.data.asof || "").slice(11, 19))
            setStatus("ok")
        } else {
            setStatus("error")
        }
    }, [codesKey])

    // 대상 로드 + 검색 선택 수신
    useEffect(() => {
        setTargets(loadTargets())
        function onTicker() {
            setTargets(loadTargets())
        }
        window.addEventListener("verity-ticker", onTicker)
        window.addEventListener("storage", onTicker)
        return () => {
            window.removeEventListener("verity-ticker", onTicker)
            window.removeEventListener("storage", onTicker)
        }
    }, [])

    // 초기 + 대상 변경 시 즉시 1회
    useEffect(() => {
        refresh()
    }, [refresh])

    // 자동 폴링
    useEffect(() => {
        if (timer.current) {
            clearInterval(timer.current)
            timer.current = null
        }
        if (auto && codesKey) {
            timer.current = setInterval(refresh, POLL_MS)
        }
        return () => {
            if (timer.current) clearInterval(timer.current)
        }
    }, [auto, codesKey, refresh])

    const btn = (active: boolean) => ({
        border: "none",
        borderRadius: 999,
        padding: "5px 11px",
        fontSize: 11,
        fontWeight: 700,
        cursor: "pointer",
        fontFamily: FONT,
        background: active ? c.vtS : c.hi,
        color: active ? c.vt : c.sub,
    })

    return (
        <div style={{ fontFamily: FONT, display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                    <span style={{ fontSize: 15, fontWeight: 800, color: c.ink, letterSpacing: "-0.02em" }}>실시간 시세</span>
                    <span style={{ fontSize: 11, color: c.faint }}>본인 이용 · KIS</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    {asof ? <span style={{ fontSize: 11, color: c.faint, ...NUM }}>{asof}</span> : null}
                    <button onClick={() => setAuto((v) => !v)} style={btn(auto)}>자동 {auto ? "ON" : "OFF"}</button>
                    <button onClick={refresh} style={btn(false)} aria-label="새로고침">↻ 수동</button>
                </div>
            </div>

            {targets.length === 0 ? (
                <div style={{ ...cardStyle(c), fontSize: 13, color: c.sub, lineHeight: 1.5 }}>
                    종목을 검색·선택하면 실시간 시세가 여기 표시됩니다. (국내 종목, 최근 검색 기준)
                </div>
            ) : status === "error" ? (
                <div style={{ ...cardStyle(c), fontSize: 13, color: c.down }}>시세 서버에 연결하지 못했습니다 (Railway).</div>
            ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {targets.map((t) => {
                        const q = quotes[t.ticker]
                        const cp = q && typeof q.change_pct === "number" ? q.change_pct : null
                        const col = cp == null ? c.faint : cp > 0 ? c.up : cp < 0 ? c.down : c.faint
                        const sign = cp != null && cp > 0 ? "+" : ""
                        return (
                            <div key={t.ticker} style={{ ...cardStyle(c, "12px 14px"), display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                                <div style={{ display: "flex", alignItems: "baseline", gap: 7, minWidth: 0 }}>
                                    <span style={{ fontSize: 14, fontWeight: 700, color: c.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{t.name || t.ticker}</span>
                                    <span style={{ fontSize: 11, color: c.faint, ...NUM }}>{t.ticker}</span>
                                </div>
                                {q && typeof q.price === "number" ? (
                                    <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexShrink: 0 }}>
                                        <span style={{ fontSize: 15, fontWeight: 800, color: c.ink, ...NUM }}>{Math.round(q.price).toLocaleString()}</span>
                                        <span style={{ fontSize: 12.5, fontWeight: 700, color: col, ...NUM, minWidth: 96, textAlign: "right" }}>
                                            {cp != null ? `${sign}${cp.toFixed(2)}%` : "—"}
                                            {typeof q.change === "number" && q.change !== 0 ? ` (${sign}${Math.abs(q.change).toLocaleString()})` : ""}
                                        </span>
                                    </div>
                                ) : (
                                    <span style={{ fontSize: 12, color: c.faint }}>{status === "loading" ? "불러오는 중…" : "—"}</span>
                                )}
                            </div>
                        )
                    })}
                    <div style={{ fontSize: 10.5, color: c.faint, lineHeight: 1.5 }}>
                        KIS 공유 토큰 소비(발급 안 함) · 국내 종목 · 장중 실시간/장외 최종가 · 매수/매도 지시 아님
                    </div>
                </div>
            )}
        </div>
    )
}
