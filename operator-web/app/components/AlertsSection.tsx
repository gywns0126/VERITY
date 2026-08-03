"use client"
// AlertsSection — 긴급 공시·이벤트 전용 섹션 (PM 2026-08-03: 팝업 폐지, 상시 섹션으로).
// 공개 사실만(urgent_alerts.json) fetch — 크라운주얼/인증데이터 미접근(봉인 규율). 외곽선 0.
import { useEffect, useState } from "react"
import { useDark, palette, cardStyle, FONT, NUM } from "@/lib/theme"
import { fetchPublic } from "@/lib/api"

type Alert = {
    ticker: string
    name: string
    type: string
    headline: string
    date?: string
    krw?: number
    source_url?: string
}

function fmtKrw(v?: number): string | null {
    if (!v || v <= 0) return null
    const eok = v / 1e8
    if (eok >= 1) return `${eok.toFixed(eok >= 100 ? 0 : 1)}억`
    return `${Math.round(v / 1e4).toLocaleString()}만`
}

export default function AlertsSection({ maxItems = 8 }: { maxItems?: number }) {
    const dark = useDark()
    const c = palette(dark)
    const [alerts, setAlerts] = useState<Alert[]>([])
    const [loaded, setLoaded] = useState(false)

    useEffect(() => {
        let cancelled = false
        fetchPublic<{ alerts?: Alert[] }>("urgent_alerts.json").then((r) => {
            if (cancelled) return
            setAlerts(r.ok && r.data.alerts ? r.data.alerts : [])
            setLoaded(true)
        })
        return () => {
            cancelled = true
        }
    }, [])

    function accent(t: string) {
        if (t === "insider_buy") return c.up
        if (t === "insider_sell") return c.down
        return c.vt
    }
    function accentSoft(t: string) {
        if (t === "insider_buy") return c.upS
        if (t === "insider_sell") return c.downS
        return c.vtS
    }
    function tag(t: string) {
        if (t === "insider_buy") return "임원·대주주 매수"
        if (t === "insider_sell") return "임원·대주주 매도"
        return "긴급 공시"
    }

    const shown = alerts.slice(0, maxItems)

    if (loaded && shown.length === 0) {
        return <div style={{ ...cardStyle(c), fontFamily: FONT, fontSize: 13, color: c.sub }}>현재 고영향 이벤트 없음 — 조용한 장.</div>
    }

    return (
        <div style={{ ...cardStyle(c, "8px 16px 10px"), fontFamily: FONT }}>
            {shown.map((a, i) => {
                const ac = accent(a.type)
                const krw = fmtKrw(a.krw)
                return (
                    <div key={(a.source_url || "") + i} style={{ display: "flex", flexDirection: "column", gap: 5, padding: "11px 0", borderTop: i === 0 ? "none" : `1px solid ${c.line}` }}>
                        <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                            <span style={{ fontSize: 10.5, fontWeight: 800, color: ac, background: accentSoft(a.type), borderRadius: 8, padding: "3px 8px" }}>{tag(a.type)}</span>
                            <span style={{ fontSize: 14, fontWeight: 700, color: c.ink, letterSpacing: "-0.01em" }}>{a.name}</span>
                            {krw ? <span style={{ fontSize: 13, fontWeight: 800, color: ac, ...NUM }}>{krw}</span> : null}
                            <span style={{ fontSize: 10.5, color: c.faint, marginLeft: "auto", ...NUM }}>{a.date}</span>
                        </div>
                        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                            <span style={{ fontSize: 12.5, color: c.sub, lineHeight: 1.45 }}>{a.headline}</span>
                            {a.source_url ? (
                                <a href={a.source_url} target="_blank" rel="noreferrer" style={{ fontSize: 11, fontWeight: 700, color: ac, textDecoration: "none", whiteSpace: "nowrap" }}>
                                    DART 원문
                                </a>
                            ) : null}
                        </div>
                    </div>
                )
            })}
            {alerts.length > maxItems ? <div style={{ fontSize: 11, color: c.faint, padding: "8px 0 2px", ...NUM }}>외 {alerts.length - maxItems}건</div> : null}
            <div style={{ fontSize: 10, color: c.faint, paddingTop: 6 }}>공시 사실 · 매수/매도 지시 아님</div>
        </div>
    )
}
