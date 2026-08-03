"use client"
// FeedPanel — 알림 3-tier (연구 정합: 무필터 알림 100+/일 = 충동거래 +22% → 보유/후보 연동만 승격).
// T1 보유 직결(붉은 배지, P0Line 에도 승격) / T2 후보 연동(앰버) / T3 참고(중립).
// 소스 = urgent_alerts.json(공개 사실). 구 AlertsSection 대체.
import { useDark, palette, cardStyle, FONT, NUM, type Palette } from "@/lib/theme"
import type { AlertItem } from "@/lib/types"
import StockLogo from "./StockLogo"
import { selectTicker } from "@/lib/types"

function fmtKrw(v?: number): string | null {
    if (!v || v <= 0) return null
    const eok = v / 1e8
    if (eok >= 1) return `${eok.toFixed(eok >= 100 ? 0 : 1)}억`
    return `${Math.round(v / 1e4).toLocaleString()}만`
}

function tierOf(a: AlertItem, hold: Set<string>, rec: Set<string>): 1 | 2 | 3 {
    if (hold.has(a.ticker)) return 1
    if (rec.has(a.ticker)) return 2
    return 3
}

/** R2 — P0 라인: 보유 직결(T1) 이벤트 있을 때만 노출되는 상시 얇은 라인. */
export function P0Line({ alerts, holdTickers }: { alerts: AlertItem[]; holdTickers: string[] }) {
    const dark = useDark()
    const c = palette(dark)
    const hold = new Set(holdTickers)
    const t1 = alerts.filter((a) => hold.has(a.ticker))
    if (t1.length === 0) return null
    const first = t1[0]
    return (
        <div
            onClick={() => selectTicker(first.ticker, first.name)}
            style={{ display: "flex", alignItems: "center", gap: 9, background: c.upS, borderRadius: 12, padding: "9px 14px", marginBottom: 12, cursor: "pointer", fontFamily: FONT }}
        >
            <span style={{ fontSize: 10, fontWeight: 800, color: "#fff", background: c.up, borderRadius: 6, padding: "2px 7px", flexShrink: 0 }}>P0 보유 직결</span>
            <span style={{ fontSize: 12.5, fontWeight: 700, color: c.ink, whiteSpace: "nowrap" }}>{first.name}</span>
            <span style={{ fontSize: 12, color: c.sub, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{first.headline}</span>
            {t1.length > 1 ? <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 700, color: c.up, flexShrink: 0, ...NUM }}>외 {t1.length - 1}건</span> : null}
        </div>
    )
}

export default function FeedPanel({ alerts, holdTickers, recTickers, loaded }: { alerts: AlertItem[]; holdTickers: string[]; recTickers: string[]; loaded: boolean }) {
    const dark = useDark()
    const c = palette(dark)
    const hold = new Set(holdTickers)
    const rec = new Set(recTickers)

    const sorted = alerts
        .map((a, i) => ({ a, i, tier: tierOf(a, hold, rec) }))
        .sort((x, y) => x.tier - y.tier || x.i - y.i)
    const shown = sorted.slice(0, 9)

    if (loaded && shown.length === 0) {
        return <div style={{ ...cardStyle(c), fontFamily: FONT, fontSize: 12.5, color: c.sub }}>현재 고영향 이벤트 없음 — 조용한 장.</div>
    }

    return (
        <div style={{ ...cardStyle(c, "8px 15px 10px"), fontFamily: FONT }}>
            {shown.map(({ a, tier }, i) => (
                <FeedRow key={(a.source_url || "") + i} c={c} a={a} tier={tier} first={i === 0} />
            ))}
            {alerts.length > shown.length ? <div style={{ fontSize: 10.5, color: c.faint, padding: "7px 0 2px", ...NUM }}>외 {alerts.length - shown.length}건</div> : null}
            <div style={{ fontSize: 9.5, color: c.faint, paddingTop: 5 }}>공시 사실 · T1=보유 직결 · T2=후보 연동 · 매수/매도 지시 아님</div>
        </div>
    )
}

function FeedRow({ c, a, tier, first }: { c: Palette; a: AlertItem; tier: 1 | 2 | 3; first: boolean }) {
    const tierCol = tier === 1 ? c.up : tier === 2 ? c.amber : c.faint
    const tierBg = tier === 1 ? c.upS : tier === 2 ? c.amberS : c.hi
    const tierLabel = tier === 1 ? "T1 보유" : tier === 2 ? "T2 후보" : "T3"
    const typeLabel = a.type === "insider_buy" ? "임원·대주주 매수" : a.type === "insider_sell" ? "임원·대주주 매도" : "긴급 공시"
    const krw = fmtKrw(a.krw)
    return (
        <div
            onClick={() => selectTicker(a.ticker, a.name)}
            style={{ display: "flex", flexDirection: "column", gap: 4, padding: "10px 0", borderTop: first ? "none" : `1px solid ${c.line}`, cursor: "pointer" }}
        >
            <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap" }}>
                <span style={{ fontSize: 9.5, fontWeight: 800, color: tierCol, background: tierBg, borderRadius: 6, padding: "2px 6px" }}>{tierLabel}</span>
                <StockLogo ticker={a.ticker} name={a.name} size={17} />
                <span style={{ fontSize: 12.5, fontWeight: 700, color: c.ink, letterSpacing: "-0.01em" }}>{a.name}</span>
                {krw ? <span style={{ fontSize: 11.5, fontWeight: 800, color: tier === 1 ? c.up : c.ink, ...NUM }}>{krw}</span> : null}
                <span style={{ fontSize: 9.5, color: c.faint, marginLeft: "auto", ...NUM }}>{a.date}</span>
            </div>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                <span style={{ fontSize: 11.5, color: c.sub, lineHeight: 1.45 }}>
                    <span style={{ color: c.faint, fontWeight: 700 }}>{typeLabel} · </span>
                    {a.headline}
                </span>
                {a.source_url ? (
                    <a href={a.source_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} style={{ fontSize: 10.5, fontWeight: 700, color: c.vt, textDecoration: "none", whiteSpace: "nowrap" }}>
                        원문
                    </a>
                ) : null}
            </div>
        </div>
    )
}
