"use client"
// AlertPopup — 고영향 이벤트 긴급 팝업. 프레이머판 포팅(React, Framer 종속 제거).
// 공개 사실만(urgent_alerts.json) fetch — 크라운주얼/인증데이터 미접근(봉인 규율).
import { useEffect, useState } from "react"
import { useDark, palette } from "@/lib/theme"
import { fetchPublic } from "@/lib/api"

const SEEN_KEY = "verity_urgent_seen"

type Alert = {
    ticker: string
    name: string
    type: string
    headline: string
    date?: string
    source_url?: string
}

function alertKey(a: Alert) {
    return String(a.source_url || "") + "|" + String(a.headline || "")
}

export default function AlertPopup({ maxVisible = 3 }: { maxVisible?: number }) {
    const dark = useDark()
    const c = palette(dark)
    const [alerts, setAlerts] = useState<Alert[]>([])
    const [dismissed, setDismissed] = useState<Record<string, number>>({})

    useEffect(() => {
        try {
            const raw = localStorage.getItem(SEEN_KEY)
            if (raw) setDismissed(JSON.parse(raw) || {})
        } catch {}
        let cancelled = false
        fetchPublic<{ alerts?: Alert[] }>("urgent_alerts.json").then((r) => {
            if (cancelled) return
            setAlerts(r.ok && r.data.alerts ? r.data.alerts : [])
        })
        return () => {
            cancelled = true
        }
    }, [])

    function dismiss(a: Alert) {
        const next = { ...dismissed, [alertKey(a)]: 1 }
        setDismissed(next)
        try {
            localStorage.setItem(SEEN_KEY, JSON.stringify(next))
        } catch {}
    }

    const visible = alerts.filter((a) => !dismissed[alertKey(a)])
    const shown = visible.slice(0, maxVisible)
    const extra = visible.length - shown.length
    if (shown.length === 0) return null

    function accent(t: string) {
        if (t === "insider_buy") return c.buy
        if (t === "insider_sell") return c.sell
        return c.purple
    }
    function tag(t: string) {
        if (t === "insider_buy") return "임원·대주주 매수"
        if (t === "insider_sell") return "임원·대주주 매도"
        return "긴급 공시"
    }

    return (
        <div
            style={{
                position: "fixed",
                bottom: 20,
                right: 20,
                zIndex: 99999,
                display: "flex",
                flexDirection: "column",
                gap: 10,
                width: "100%",
                maxWidth: 380,
            }}
        >
            {shown.map((a, i) => (
                <div
                    key={alertKey(a) + i}
                    style={{
                        background: c.card,
                        borderRadius: 16,
                        border: `1px solid ${c.border}`,
                        borderLeft: `3px solid ${accent(a.type)}`,
                        boxShadow: dark ? "0 8px 30px rgba(0,0,0,0.5)" : "0 8px 30px rgba(0,0,0,0.14)",
                        padding: "14px 15px",
                        display: "flex",
                        flexDirection: "column",
                        gap: 7,
                    }}
                >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color: accent(a.type) }}>{tag(a.type)}</span>
                        <button
                            onClick={() => dismiss(a)}
                            aria-label="닫기"
                            style={{ border: "none", background: "transparent", color: c.sub, fontSize: 16, cursor: "pointer", padding: 2 }}
                        >
                            ×
                        </button>
                    </div>
                    <div style={{ fontSize: 15, fontWeight: 700, color: c.fg, letterSpacing: "-0.02em" }}>{a.name}</div>
                    <div style={{ fontSize: 13, color: c.fg, lineHeight: 1.45 }}>{a.headline}</div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 2 }}>
                        <span style={{ fontSize: 11, color: c.sub }}>{a.date} · 공시 사실</span>
                        {a.source_url ? (
                            <a href={a.source_url} target="_blank" rel="noreferrer" style={{ fontSize: 11, fontWeight: 600, color: accent(a.type), textDecoration: "none" }}>
                                DART 원문 →
                            </a>
                        ) : null}
                    </div>
                </div>
            ))}
            {extra > 0 ? <div style={{ fontSize: 11, color: c.sub, textAlign: "center" }}>외 {extra}건 더</div> : null}
        </div>
    )
}
