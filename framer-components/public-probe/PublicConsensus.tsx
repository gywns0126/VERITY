import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * AlphaNest 공개 — 미장 투자의견 분포 + 목표가 범위. 외부 집계 사실.
 * 🚨 StockReport 컨센서스(의견/평균목표가/업사이드)와 중복 회피 — 여기는 분포막대 + 목표가 범위(high/low)만(StockReport에 없는 것).
 * RULE 7 — yfinance 외부 집계, 자체 의견·점수 아님. 데이터 = us_stock_report_public.json (Blob).
 * 다크모드 = body[data-framer-theme] 자가감지. 외곽선 없음. 루트 패딩 = /stock 컨벤션(narrow?14:18).
 * Framer codeFileId = YfnonVE (insertUrl framer.com/m/PublicConsensus-XYEH4x.js).
 */

const LIGHT = { card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#f0f1f3", vt: "#6c5ce7", vtS: "#f0edff", up: "#f04452", down: "#3182f6", bg: "#f2f4f6" }
const DARK = { card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#222730", vt: "#a99bff", vtS: "#241f3a", up: "#f04452", down: "#5b9bff", bg: "#0f1318" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/us_stock_report_public.json"

const CATS: { key: string; label: string }[] = [
    { key: "strongBuy", label: "적극매수" },
    { key: "buy", label: "매수" },
    { key: "hold", label: "중립" },
    { key: "sell", label: "매도" },
    { key: "strongSell", label: "적극매도" },
]

const SAMPLE: any = { target_high: "$370.00", target_low: "$207.00", num_analysts: 63, counts: { strongBuy: 15, buy: 48, hold: 4, sell: 0, strongSell: 0 }, note: "외부 애널리스트 집계 · yfinance" }

function readDark(): boolean {
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}

export default function PublicConsensus(props: { ticker?: string; dataUrl?: string; dark?: boolean }) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT
    const [c, setC] = useState<any>(onCanvas ? SAMPLE : null)
    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas || !props.ticker) return
        let alive = true
        fetch(props.dataUrl || DEFAULT_URL, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                const st = d && d.stocks
                const rec = Array.isArray(st) ? st.find((x: any) => String(x.ticker).toUpperCase() === String(props.ticker).toUpperCase()) : (st ? st[String(props.ticker)] : null)
                if (alive) setC(rec && rec.consensus ? rec.consensus : null)
            })
            .catch(() => { if (alive) setC(null) })
        return () => { alive = false }
    }, [props.ticker, props.dataUrl, onCanvas])

    const narrow = w > 0 && w < 420
    const counts = (c && c.counts) || {}
    const vals = CATS.map((x) => Number(counts[x.key] || 0))
    const maxV = Math.max(1, ...vals)
    const hasDist = vals.some((v) => v > 0)
    const hasRange = !!(c && c.target_low && c.target_high)
    if (!c || !c.num_analysts || (!hasDist && !hasRange)) return <div ref={rootRef} style={{ width: "100%", height: 0, overflow: "hidden" }} />

    const wrap: CSSProperties = { width: "100%", minHeight: "100%", boxSizing: "border-box", background: C.bg, fontFamily: FONT, color: C.ink, padding: narrow ? "0 14px" : "0 18px", display: "flex", flexDirection: "column", gap: 12 }
    return (
        <div ref={rootRef} style={wrap}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                <span style={{ fontSize: 14, fontWeight: 800, letterSpacing: "-0.3px" }}>투자의견 분포</span>
                <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>{c.num_analysts}명 · 외부 집계</span>
            </div>

            {/* 투자의견 분포 막대 (StockReport에 없는 시각화) */}
            {hasDist && (
                <div style={{ background: C.card, borderRadius: 16, padding: "16px 16px 12px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                    <div style={{ display: "flex", alignItems: "flex-end", gap: 6, height: 84 }}>
                        {CATS.map((cat, i) => {
                            const v = vals[i]
                            const h = Math.round((v / maxV) * 60)
                            const dominant = v === maxV && v > 0
                            return (
                                <div key={cat.key} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 5 }}>
                                    <span style={{ fontSize: 11, fontWeight: 800, color: dominant ? C.vt : C.faint }}>{v}</span>
                                    <div style={{ width: "100%", maxWidth: 34, height: Math.max(3, h), borderRadius: 6, background: dominant ? C.vt : v > 0 ? C.vtS : C.line }} />
                                    <span style={{ fontSize: 9.5, fontWeight: 600, color: C.faint, textAlign: "center", lineHeight: 1.2 }}>{cat.label}</span>
                                </div>
                            )
                        })}
                    </div>
                </div>
            )}

            {/* 목표가 범위 (최저~최고 — StockReport는 평균만 노출) */}
            {hasRange && (
                <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                    <div style={{ fontSize: 12.5, fontWeight: 700, color: C.sub, marginBottom: 8 }}>목표가 범위</div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12.5, fontWeight: 800, color: C.ink }}>
                        <span>{c.target_low}</span>
                        <span>{c.target_high}</span>
                    </div>
                    <div style={{ height: 6, borderRadius: 3, marginTop: 6, background: `linear-gradient(90deg, ${C.down}, ${C.vt}, ${C.up})` }} />
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, fontWeight: 600, color: C.faint, marginTop: 4 }}>
                        <span>최저</span>
                        <span>최고</span>
                    </div>
                </div>
            )}

            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, lineHeight: 1.5 }}>{c.note || "외부 애널리스트 집계 · yfinance"}</div>
        </div>
    )
}

addPropertyControls(PublicConsensus, {
    ticker: { type: ControlType.String, title: "Ticker", defaultValue: "" },
    dataUrl: { type: ControlType.String, title: "Data URL", defaultValue: DEFAULT_URL },
    dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
})
