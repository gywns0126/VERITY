import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState, type CSSProperties } from "react"

/**
 * AlphaNest 공개 — 종목 지분·설비 상세 (기관·국민연금 5%+ 대량보유 + DART 사업장). 사실만.
 * 🚨 RULE 7 — 점수·신호 0. net_flow_direction 등 해석 비노출. 데이터 = stock_report_public.json (Blob).
 * 다크모드 = body[data-framer-theme] 자가감지. 외곽선 없음(소프트 카드).
 * Framer codeFileId = Do9eiR9 (insertUrl framer.com/m/PublicHoldingsDetail-crn3L8.js).
 */

const LIGHT = { card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#f0f1f3", vt: "#6c5ce7", vtS: "#f0edff" }
const DARK = { card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#222730", vt: "#a99bff", vtS: "#241f3a" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_report_public.json"

const SAMPLE: any = {
    institutional: { total_pct: 5.18, n: 1, holders: [{ reporter: "국민연금공단", pct: 5.18, qty_change: 108230, date: "2026-04-01" }], note: "DART 5%+ 대량보유 보고(기관·국민연금) — 사실, 신호 아님" },
    facilities: { headquarters: { location: "경상남도 창원시 성산구", ownership: "소유" }, facilities: [{ name: "창원공장", location: "경상남도 창원시", use: "공장", segment: "디펜스솔루션" }], note: "DART 사업보고서 시설 현황 — 사실" },
}

function readDark(): boolean {
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}

export default function PublicHoldingsDetail(props: { ticker?: string; dataUrl?: string; dark?: boolean }) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT
    const [rec, setRec] = useState<any>(onCanvas ? SAMPLE : null)

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
            .then((d) => { if (alive) setRec(d && d.stocks ? d.stocks[String(props.ticker)] || null : null) })
            .catch(() => { if (alive) setRec(null) })
        return () => { alive = false }
    }, [props.ticker, props.dataUrl, onCanvas])

    const inst = rec && rec.institutional
    const fac = rec && rec.facilities
    const hasInst = inst && Array.isArray(inst.holders) && inst.holders.length > 0
    const hasFac = fac && (Array.isArray(fac.facilities) || fac.headquarters)
    if (!hasInst && !hasFac) return null

    const HEAD = "Pretendard, -apple-system, sans-serif"
    const wrap: CSSProperties = { width: "100%", boxSizing: "border-box", fontFamily: FONT, color: C.ink, display: "flex", flexDirection: "column", gap: 14 }
    const title = (t: string, sub: string) => (
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 2 }}>
            <span style={{ fontSize: 14, fontWeight: 800, letterSpacing: "-0.3px" }}>{t}</span>
            <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>{sub}</span>
        </div>
    )
    return (
        <div style={wrap}>
            {hasInst && (
                <div>
                    {title("기관·국민연금 대량보유", "DART 5%+ 보고 · 사실")}
                    <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        {inst.total_pct != null && (
                            <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 10 }}>
                                <span style={{ fontFamily: HEAD, fontSize: 22, fontWeight: 800, color: C.vt, letterSpacing: "-0.6px" }}>{inst.total_pct}%</span>
                                <span style={{ fontSize: 12.5, fontWeight: 700 }}>기관 합산 보유</span>
                                {inst.n != null && <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{inst.n}곳</span>}
                            </div>
                        )}
                        {inst.holders.map((h: any, i: number) => (
                            <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                                <span style={{ flex: 1, minWidth: 0, fontSize: 12.5, fontWeight: 700, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{h.reporter}</span>
                                {h.qty_change != null && <span style={{ flexShrink: 0, fontSize: 11, fontWeight: 600, color: C.faint }}>변동 {Number(h.qty_change) >= 0 ? "+" : ""}{Number(h.qty_change).toLocaleString("ko-KR")}</span>}
                                <span style={{ flexShrink: 0, fontSize: 12.5, fontWeight: 800, color: C.vt, minWidth: 46, textAlign: "right" }}>{h.pct}%</span>
                            </div>
                        ))}
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, lineHeight: 1.5, marginTop: 9 }}>{inst.note}</div>
                    </div>
                </div>
            )}
            {hasFac && (
                <div>
                    {title("사업장·설비", "DART 사업보고서 · 사실")}
                    <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        {fac.headquarters && fac.headquarters.location && (
                            <div style={{ fontSize: 12.5, fontWeight: 600, color: C.sub, marginBottom: 8 }}>본사 · {fac.headquarters.location}{fac.headquarters.ownership ? ` (${fac.headquarters.ownership})` : ""}</div>
                        )}
                        {Array.isArray(fac.facilities) && fac.facilities.map((f: any, i: number) => (
                            <div key={i} style={{ padding: "8px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                                <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                                    <span style={{ fontSize: 13, fontWeight: 700, color: C.ink }}>{f.name}</span>
                                    {f.use && <span style={{ fontSize: 11, fontWeight: 700, color: C.vt, background: C.vtS, borderRadius: 6, padding: "2px 7px" }}>{f.use}</span>}
                                </div>
                                {(f.location || f.segment) && <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3, lineHeight: 1.5 }}>{[f.location, f.segment].filter(Boolean).join(" · ")}</div>}
                            </div>
                        ))}
                        <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, lineHeight: 1.5, marginTop: 9 }}>{fac.note}</div>
                    </div>
                </div>
            )}
        </div>
    )
}

addPropertyControls(PublicHoldingsDetail, {
    ticker: { type: ControlType.String, title: "종목코드", defaultValue: "" },
    dataUrl: { type: ControlType.String, title: "Data URL", defaultValue: DEFAULT_URL },
    dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
})
