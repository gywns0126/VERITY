import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * 분기 재무 추이 — VERITY AlphaNest 종목 리포트 깊이 섹션. (독립 컴포넌트 — US는 quarterlyUrl=us_quarterly_public.json)
 *
 * 목적 = "재무 단년 스냅샷 1개" → "최근 N분기 흐름(개선/악화)". DART/SEC 분기 사실만(RULE 7).
 * 데이터 = quarterlyUrl {stocks:{ticker:{quarters:[...]}}}. KR=dart_quarterly_public.json / US=us_quarterly_public.json.
 *   quarters[] = {q(분기말 YYYY-MM-DD), debt_ratio, roa, current_ratio, gross_margin, asset_turnover,
 *                 operating_margin, net_margin, roe(US 2026-07 확장 — 없는 시장/종목은 행 자동 skip)}
 * 🚨 라이브: 실데이터(≥4분기) 없으면 **자동 숨김**(가짜 추이 금지, RULE 7). 캔버스만 SAMPLE 미리보기.
 * 테마: Framer 네이티브 추종(body[data-framer-theme]). 외곽선 없음(소프트 카드). 루트 패딩 = /stock 컨벤션(narrow?14:18).
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968",
    faint: "#8b95a1", line: "#e5e8eb", vt: "#6c5ce7", vtFill: "rgba(108,92,231,0.10)", vtS: "#f0edff",
    good: "#15c47e", goodS: "#e7faf0", warn: "#ff9500", warnS: "#fff6e9", grid: "#eef0f3",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1",
    faint: "#828d9b", line: "#252b34", vt: "#a99bff", vtFill: "rgba(169,155,255,0.13)", vtS: "#241f3a",
    good: "#34e08a", goodS: "#11281d", warn: "#ff9500", warnS: "#2a2113", grid: "#20262f",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

const METRICS: { key: string; label: string; unit: string; better: "up" | "down"; note?: string }[] = [
    { key: "debt_ratio", label: "부채비율", unit: "%", better: "down" },
    { key: "roa", label: "ROA", unit: "%", better: "up" },
    { key: "current_ratio", label: "유동비율", unit: "%", better: "up" },
    { key: "gross_margin", label: "매출총이익률", unit: "%", better: "up", note: "분기 누적" },
    { key: "operating_margin", label: "영업이익률", unit: "%", better: "up" },
    { key: "net_margin", label: "순이익률", unit: "%", better: "up" },
    { key: "roe", label: "ROE", unit: "%", better: "up" },
]

const SAMPLE_QUARTERS = (() => {
    const qs: any[] = []
    const ends = ["03-31", "06-30", "09-30", "12-31"]
    let i = 0
    for (let y = 2021; y <= 2025; y++) for (const e of ends) {
        const t = i / 19
        qs.push({
            q: `${y}-${e}`,
            debt_ratio: +(168 - 76 * t + Math.sin(i) * 4).toFixed(1),
            roa: +(1.2 + 5.6 * t + Math.cos(i * 1.3) * 0.35).toFixed(2),
            current_ratio: +(98 + 67 * t + Math.sin(i * 0.8) * 5).toFixed(1),
            gross_margin: +(31 + 11 * t + Math.cos(i) * 0.9).toFixed(1),
            operating_margin: +(12 + 6 * t + Math.sin(i * 1.1) * 0.8).toFixed(1),
            net_margin: +(8 + 5 * t + Math.cos(i * 0.9) * 0.7).toFixed(1),
            roe: +(6 + 9 * t + Math.sin(i * 0.7) * 1).toFixed(1),
        })
        i++
    }
    return qs
})()

interface Props {
    ticker: string
    quarterlyUrl: string
    maxQuarters: number
    showExtremes: boolean
    dark: boolean
}
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/dart_quarterly_public.json"

function qLabel(qEnd: string): string {
    const s = String(qEnd || "")
    if (s.length < 10) return s
    const y = s.slice(2, 4)
    const mm = s.slice(5, 7)
    const q = mm === "03" ? "1Q" : mm === "06" ? "2Q" : mm === "09" ? "3Q" : mm === "12" ? "4Q" : mm
    return `${y}.${q}`
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
export default function PublicQuarterlyTrend(props: Props) {
    const { ticker, quarterlyUrl, maxQuarters, showExtremes, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [quarters, setQuarters] = useState<any[]>(onCanvas ? SAMPLE_QUARTERS : [])
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!dark : readBodyDark()))
    const C = (onCanvas ? !!dark : themeDark) ? DARK : LIGHT

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

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    useEffect(() => {
        if (onCanvas || !quarterlyUrl || !ticker) return
        let alive = true
        fetch(quarterlyUrl)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const rec = d && d.stocks && d.stocks[ticker]
                const arr = rec && Array.isArray(rec.quarters) ? rec.quarters : null
                if (alive && arr && arr.length) setQuarters(arr)
            })
            .catch(() => {})
        return () => { alive = false }
    }, [quarterlyUrl, ticker, onCanvas])

    const cap = Math.max(4, Math.min(40, maxQuarters || 20))
    const series = useMemo(() => {
        const sorted = [...quarters].sort((a, b) => String(a.q).localeCompare(String(b.q)))
        return sorted.slice(-cap)
    }, [quarters, cap])

    const narrow = w > 0 && w < 420

    if (!onCanvas && series.length < 4) return <div ref={rootRef} style={{ width: "100%", height: 0, overflow: "hidden" }} />

    const CW = Math.max(80, (w || 360) - (narrow ? 28 : 36))
    const CH = 52
    const PX = 4
    const PY = 9

    const wrap: CSSProperties = {
        width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT, boxSizing: "border-box", color: C.ink,
        padding: narrow ? 14 : 18,
    }

    return (
        <div ref={rootRef} style={wrap}>
            <div style={{ background: C.card, borderRadius: 16, padding: narrow ? "15px 14px" : "17px 18px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-0.4px" }}>분기 재무 추이</span>
                    <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>최근 {series.length}분기 · 분기보고서 · 사실</span>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 0, marginTop: 10 }}>
                    {METRICS.map((m, mi) => {
                        const raw = series.map((q) => {
                            const v = q[m.key]
                            return typeof v === "number" && isFinite(v) ? v : null
                        })
                        const present = raw.filter((v): v is number => v != null)
                        if (present.length < 2) return null
                        const lo = Math.min(...present)
                        const hi = Math.max(...present)
                        const span = hi - lo || 1
                        const first = present[0]
                        const last = present[present.length - 1]
                        const delta = last - first
                        const improved = m.better === "down" ? delta < 0 : delta > 0
                        const flat = Math.abs(delta) < span * 0.04
                        const dirColor = flat ? C.faint : improved ? C.good : C.warn
                        const dirBg = flat ? C.line : improved ? C.goodS : C.warnS
                        const dirText = flat ? "보합" : improved ? "개선" : "악화"
                        const arrow = flat ? "→" : improved ? "▲" : "▼"
                        const dec = m.key === "roa" ? 2 : 1

                        const n = raw.length
                        const xAt = (i: number) => PX + (n <= 1 ? 0 : (i / (n - 1)) * (CW - PX * 2))
                        const yAt = (v: number) => PY + (1 - (v - lo) / span) * (CH - PY * 2)
                        const pts = raw.map((v, i) => (v == null ? null : { x: xAt(i), y: yAt(v), v, i }))
                            .filter((p): p is { x: number; y: number; v: number; i: number } => p != null)
                        const linePath = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")
                        const areaPath = `${linePath} L${pts[pts.length - 1].x.toFixed(1)},${CH - 1} L${pts[0].x.toFixed(1)},${CH - 1} Z`
                        const hiPt = pts.reduce((a, b) => (b.v > a.v ? b : a))
                        const loPt = pts.reduce((a, b) => (b.v < a.v ? b : a))
                        const lastPt = pts[pts.length - 1]
                        const gid = `qt-${m.key}-${mi}`
                        const clampX = (x: number) => Math.max(16, Math.min(CW - 16, x))

                        return (
                            <div key={m.key} style={{ padding: "12px 0", borderTop: mi === 0 ? "none" : `1px solid ${C.line}` }}>
                                <div style={{ display: "flex", alignItems: "baseline", gap: 7, marginBottom: 6, flexWrap: "wrap" }}>
                                    <span style={{ fontSize: 13, fontWeight: 700, color: C.ink }}>{m.label}</span>
                                    {m.note && <span style={{ fontSize: 10, color: C.faint, fontWeight: 600 }}>· {m.note}</span>}
                                    <span style={{ marginLeft: "auto", fontSize: 15, fontWeight: 800, letterSpacing: "-0.3px", color: C.ink, fontVariantNumeric: "tabular-nums" }}>
                                        {last.toFixed(dec)}{m.unit}
                                    </span>
                                    <span style={{ fontSize: 10.5, fontWeight: 800, color: dirColor, background: dirBg, borderRadius: 6, padding: "2px 7px" }}>
                                        {arrow} {dirText}
                                    </span>
                                </div>

                                <svg width={CW} height={CH} style={{ display: "block", width: "100%", overflow: "visible" }} viewBox={`0 0 ${CW} ${CH}`} preserveAspectRatio="none">
                                    <defs>
                                        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="0%" stopColor={C.vt} stopOpacity={C === DARK ? 0.28 : 0.18} />
                                            <stop offset="100%" stopColor={C.vt} stopOpacity={0} />
                                        </linearGradient>
                                    </defs>
                                    <path d={areaPath} fill={`url(#${gid})`} />
                                    <path d={linePath} fill="none" stroke={C.vt} strokeWidth={1.75}
                                        strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
                                    {showExtremes && (
                                        <>
                                            <circle cx={hiPt.x} cy={hiPt.y} r={2.6} fill={C.card} stroke={C.vt} strokeWidth={1.4} vectorEffect="non-scaling-stroke" />
                                            <circle cx={loPt.x} cy={loPt.y} r={2.6} fill={C.card} stroke={C.vt} strokeWidth={1.4} vectorEffect="non-scaling-stroke" />
                                            <text x={clampX(hiPt.x)} y={Math.max(7, hiPt.y - 4)} textAnchor="middle" fontSize={8.5} fontWeight={700} fill={C.faint} fontFamily={FONT}>
                                                최고 {hiPt.v.toFixed(dec)}
                                            </text>
                                            <text x={clampX(loPt.x)} y={Math.min(CH - 1, loPt.y + 9)} textAnchor="middle" fontSize={8.5} fontWeight={700} fill={C.faint} fontFamily={FONT}>
                                                최저 {loPt.v.toFixed(dec)}
                                            </text>
                                        </>
                                    )}
                                    <circle cx={lastPt.x} cy={lastPt.y} r={3.4} fill={C.vt} stroke={C.card} strokeWidth={1.6} vectorEffect="non-scaling-stroke" />
                                </svg>

                                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 3 }}>
                                    <span style={{ fontSize: 10, color: C.faint, fontWeight: 600 }}>{qLabel(series[0].q)}</span>
                                    <span style={{ fontSize: 10, color: dirColor, fontWeight: 700 }}>
                                        {(delta > 0 ? "+" : "") + delta.toFixed(dec)}{m.unit} ({series.length}분기)
                                    </span>
                                    <span style={{ fontSize: 10, color: C.faint, fontWeight: 600 }}>{qLabel(series[series.length - 1].q)}</span>
                                </div>
                            </div>
                        )
                    })}
                </div>

                <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.5 }}>
                    출처 분기·반기·사업보고서 · 비율 자체계산(사실){showExtremes ? " · ○ 최고·최저점" : ""}
                    {onCanvas && <span style={{ color: C.warn }}> · ⚠ SAMPLE 미리보기(실데이터는 backfill 누적 후)</span>}
                </div>
            </div>
        </div>
    )
}

addPropertyControls(PublicQuarterlyTrend, {
    ticker: { type: ControlType.String, title: "Ticker", defaultValue: "005930" },
    quarterlyUrl: { type: ControlType.String, title: "Quarterly URL", defaultValue: DEFAULT_URL },
    maxQuarters: { type: ControlType.Number, title: "Max Quarters", defaultValue: 20, min: 4, max: 40, step: 1 },
    showExtremes: { type: ControlType.Boolean, title: "최고·최저점", defaultValue: true, enabledTitle: "On", disabledTitle: "Off" },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})
