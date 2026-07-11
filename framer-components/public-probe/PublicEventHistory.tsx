import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 과거 공시 패턴 — VERITY 공개 터미널 (AlphaNest). 종목별 **자기 과거** 카탈리스트 공시(유상증자/자기주식취득·처분/
 * 전환사채/합병/감자/공급계약 등) 당시 종가 대비 +1d/+5d/+20d/+60d 거래일 forward return.
 *
 * 데이터 = data/event_study.json (event_study_builder.py 산출 — DART 공시이력 2015~ + kr_prices 레이크 19년 OHLCV).
 * 🚨 PM 결정 2026-06-25 / RULE 7: 종목별 자기 과거 사실만(종목 간 평균·집계·랭킹 0). 과거 사실 비교지 예측·신호 아님.
 *   종목 간 집계 없음 → 생존편향 비해당. count(N)·날짜 = 사실의 일부. raw 주가 변화(시장 포함).
 *   LLM·네이버 못 가지는 자기 데이터 자산(RULE 6 escape — 자기 trail, narrative 아님). 점수·등급·추천 0.
 * 종목 = prop ticker → URL ?q → verity_last_ticker. in-page 전환 추종 1s 폴링. 테마 = body[data-framer-theme] 추종.
 * 데이터 없으면 graceful 숨김(빈 카드 방지).
 */

interface Props {
    ticker: string
    dataUrl: string
    dark: boolean
}
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/event_study.json"

// up = 상승(한국 관습 빨강) · down = 하락(파랑). tone = 공시 의미축(PublicDisclosureFeed 동일).
const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#f0f1f3",
    up: "#f04452", down: "#3182f6", vt: "#6c5ce7", vtS: "#f0edff",
    amber: "#ff9500", amberS: "#fff6e9", green: "#15c47e", greenS: "#eafaf3", red: "#f04452", redS: "#fff0f1",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#222730",
    up: "#f04452", down: "#5b9bff", vt: "#a99bff", vtS: "#241f3a",
    amber: "#ff9500", amberS: "#2a2113", green: "#34e08a", greenS: "#0f241c", red: "#f04452", redS: "#2a1a1d",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

const WINDOWS: { key: string; label: string }[] = [
    { key: "ret_1d", label: "+1일" },
    { key: "ret_5d", label: "+5일" },
    { key: "ret_20d", label: "+20일" },
    { key: "ret_60d", label: "+60일" },
]

interface Occurrence { date: string; report_nm?: string; ret_1d: number | null; ret_5d: number | null; ret_20d: number | null; ret_60d: number | null }
interface Ev { type: string; tone: string; count: number; occurrences: Occurrence[]; truncated?: number }
interface Stock { name: string; events: Ev[] }

function readTickerFromUrl(): string {
    if (typeof window === "undefined") return ""
    try {
        const q = (new URLSearchParams(window.location.search).get("q") || "").trim()
        if (q) return q.toUpperCase()
        return (window.localStorage.getItem("verity_last_ticker") || "").trim().toUpperCase()
    } catch { return "" }
}

const SAMPLE: Record<string, Stock> = {
    SAMPLE: {
        name: "예시종목",
        events: [
            { type: "자기주식 취득", tone: "favor", count: 2, occurrences: [
                { date: "2023-08-14", ret_1d: 1.2, ret_5d: 3.1, ret_20d: 6.4, ret_60d: 11.0 },
                { date: "2021-05-03", ret_1d: 0.4, ret_5d: -1.8, ret_20d: 2.2, ret_60d: 5.5 },
            ] },
            { type: "유상증자", tone: "dilution", count: 1, occurrences: [
                { date: "2019-11-21", ret_1d: -4.8, ret_5d: -9.2, ret_20d: -12.4, ret_60d: -6.1 },
            ] },
        ],
    },
}

function readBodyDark(): boolean {
    // 첫 페인트 flash 방지 — body 속성 미설정(마운트 직후) 시 토글 저장 선호(localStorage) → OS 순 폴백.
    // PublicThemeToggle 이 verity_theme 로 저장 + body[data-framer-theme] 설정 = 동일 소스라 첫 페인트부터 정합.
    try {
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
        if (typeof window !== "undefined" && window.matchMedia) {
            return window.matchMedia("(prefers-color-scheme: dark)").matches
        }
    } catch (e) {}
    return false
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicEventHistory(props: Props) {
    // ETF/ETN 선택 시 자기 숨김 — StockReport 가 body[data-verity-asset-kind] 신호 발행 (2026-07-10)
    const [assetKind, setAssetKind] = useState<string>("stock")
    useEffect(() => {
        if (typeof document === "undefined" || !document.body) return
        const read = () => setAssetKind(document.body.dataset.verityAssetKind || "stock")
        read()
        if (typeof MutationObserver === "undefined") return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-verity-asset-kind"] })
        return () => obs.disconnect()
    }, [])
    const { ticker, dataUrl, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const [themeDark, setThemeDark] = useState<boolean>(() => (onCanvas ? !!dark : readBodyDark()))
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

    const isDark = onCanvas ? !!dark : themeDark
    const C = isDark ? DARK : LIGHT

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [tk, setTk] = useState<string>(() => String(ticker || "").trim().toUpperCase())
    const [data, setData] = useState<Record<string, Stock>>(onCanvas ? SAMPLE : {})

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    /* 종목 = prop 우선, 없으면 URL ?q. in-page 전환 추종 1s 폴링. */
    useEffect(() => {
        if (onCanvas) return
        const propTk = String(ticker || "").trim().toUpperCase()
        if (propTk) { setTk(propTk); return }
        const sync = () => { const u = readTickerFromUrl(); if (u) setTk((cur) => (cur === u ? cur : u)) }
        sync()
        window.addEventListener("popstate", sync)
        const iv = setInterval(sync, 1000)
        return () => { window.removeEventListener("popstate", sync); clearInterval(iv) }
    }, [ticker, onCanvas])

    /* event_study.json 로드 */
    useEffect(() => {
        if (onCanvas || !dataUrl) return
        let alive = true
        fetch(dataUrl)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { const m = d && d.stocks && typeof d.stocks === "object" ? d.stocks : null; if (alive && m) setData(m) })
            .catch(() => {})
        return () => { alive = false }
    }, [dataUrl, onCanvas])

    const stock: Stock | null = useMemo(() => {
        const key = onCanvas ? "SAMPLE" : String(tk).toUpperCase()
        const s = data[key]
        return s && Array.isArray(s.events) && s.events.length ? s : null
    }, [data, tk, onCanvas])

    const narrow = w > 0 && w < 460
    const toneC = (t: string) => t === "dilution" ? { fg: C.amber, bg: C.amberS } : t === "favor" ? { fg: C.green, bg: C.greenS } : t === "alert" ? { fg: C.red, bg: C.redS } : { fg: C.sub, bg: C.line }
    const retColor = (v: number | null) => v == null ? C.faint : v > 0 ? C.up : v < 0 ? C.down : C.sub
    const fmt = (v: number | null) => v == null ? "–" : (v > 0 ? "+" : "") + v.toFixed(1) + "%"

    const wrap: CSSProperties = { width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT, padding: narrow ? 14 : 18, boxSizing: "border-box", color: C.ink }

    // 데이터 없으면 숨김(빈 카드 방지)
    if (!stock) return <div ref={rootRef} style={{ width: "100%", height: 0, overflow: "hidden" }} />

    if (assetKind === "etf") return null  // ETF/ETN = 기업 전용 섹션 숨김

    return (
        <div ref={rootRef} style={wrap}>
            <div style={{ background: C.card, borderRadius: 16, padding: narrow ? 14 : 18, boxSizing: "border-box", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 7, marginBottom: 3, flexWrap: "wrap" }}>
                    <span style={{ fontSize: narrow ? 15 : 16, fontWeight: 800, letterSpacing: "-0.3px" }}>과거 공시 패턴</span>
                    <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>이 종목의 과거 같은 공시 당시 주가 변화</span>
                </div>
                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginBottom: 12 }}>발생일 종가 기준 이후 거래일별 주가 변화 · 과거 사실</div>

                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    {stock.events.map((ev, ei) => {
                        const tc = toneC(ev.tone)
                        return (
                            <div key={ei} style={{ borderTop: ei === 0 ? "none" : "1px solid " + C.line, paddingTop: ei === 0 ? 0 : 12 }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 8 }}>
                                    <span style={{ fontSize: 11, fontWeight: 800, color: tc.fg, background: tc.bg, padding: "3px 8px", borderRadius: 7, whiteSpace: "nowrap" }}>{ev.type}</span>
                                    <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 700 }}>과거 {ev.count}회</span>
                                </div>

                                {/* 윈도우 헤더 */}
                                <div style={{ display: "grid", gridTemplateColumns: `${narrow ? 78 : 96}px repeat(4, 1fr)`, gap: 4, alignItems: "center", padding: "0 2px 5px", borderBottom: "1px solid " + C.line }}>
                                    <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 700 }}>발생일</span>
                                    {WINDOWS.map((wd) => (
                                        <span key={wd.key} style={{ fontSize: 10.5, color: C.faint, fontWeight: 700, textAlign: "right" }}>{wd.label}</span>
                                    ))}
                                </div>

                                {/* 발생별 행 */}
                                {ev.occurrences.map((o, oi) => (
                                    <div key={oi} style={{ display: "grid", gridTemplateColumns: `${narrow ? 78 : 96}px repeat(4, 1fr)`, gap: 4, alignItems: "center", padding: "7px 2px", borderTop: oi === 0 ? "none" : "1px solid " + C.line }}>
                                        <span style={{ fontSize: narrow ? 11 : 12, color: C.sub, fontWeight: 700 }}>{o.date}</span>
                                        {WINDOWS.map((wd) => {
                                            const v = (o as any)[wd.key] as number | null
                                            return <span key={wd.key} style={{ fontSize: narrow ? 11.5 : 12.5, fontWeight: 800, textAlign: "right", color: retColor(v) }}>{fmt(v)}</span>
                                        })}
                                    </div>
                                ))}
                                {ev.truncated ? (
                                    <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, padding: "6px 2px 0", textAlign: "right" }}>최근 {ev.occurrences.length}건 표시 · 외 {ev.truncated}건 더</div>
                                ) : null}
                            </div>
                        )
                    })}
                </div>

                <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 500, marginTop: 13, lineHeight: 1.55 }}>
                    이 종목의 과거 공시 당시 주가 변화(거래일 기준, 시장 포함) — 과거 사실이며 미래를 보장하지 않아요. 출처 DART 공시이력 + 자체 가격 데이터.
                </div>
            </div>
        </div>
    )
}

addPropertyControls(PublicEventHistory, {
    ticker: { type: ControlType.String, title: "Ticker(빈값=URL ?q)", defaultValue: "" },
    dataUrl: { type: ControlType.String, title: "Event Study URL", defaultValue: DEFAULT_URL },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})
