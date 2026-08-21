"use client"
// MultibaggerPanel — 멀티배거 워치(알파콘솔 전용). 소스 = authed /api/admin?type=multibagger.
//
// 🚨 관측 패널이지 매매 신호가 아니다. 생산자가 산출물에 `decision_use=false` +
//    "로깅 전용 — 결정 0 (active gate 2026-09)" 를 달고 있으므로 화면이 그대로 신고한다.
//    이 배지를 지우지 말 것 — 지우면 관측이 판단으로 둔갑한다.
// 🚨 커버리지도 표시한다. revenue_acceleration 의 연속가속 방어는 quarterly_revenue 를
//    요구하는데 DART 백필 미완이면 꺼진 채 발화한다(2026-08-21 실측 429/429 = 100%).
//    그 비율을 숨기면 화면이 "검증된 신호" 처럼 보인다.
import { useEffect, useState } from "react"
import { useDark, palette, cardStyle, FONT, NUM, CARD_TITLE, RAIL_PAD, hoverBg } from "@/lib/theme"
import { fetchOperator } from "@/lib/api"
import { selectTicker } from "@/lib/types"
import StockLogo from "./StockLogo"

type Fired = Record<string, { score?: number; reason?: string }>
type Item = {
    ticker?: string
    name?: string
    sector?: string
    lynch_class?: string
    alert_count?: number
    fired?: Fired
}
type Meta = {
    watch_date?: string
    universe_n?: number
    published_n?: number
    decision_use?: boolean
    producer_note?: string
    acceleration_uncovered_n?: number
    acceleration_uncovered_pct?: number
    fired_counts?: Record<string, number>
}
type Payload = { _meta?: Meta; items?: Item[] }

// 신호 키 → 짧은 한글 라벨. 없는 키는 원문 그대로 보여준다(조용한 누락 방지).
const LABEL: Record<string, string> = {
    revenue_acceleration: "매출가속",
    operating_leverage: "영업레버리지",
    category_leader: "카테고리 1위",
    hold_pnl_threshold: "보유손익",
}

export default function MultibaggerPanel() {
    const dark = useDark()
    const c = palette(dark)
    const [d, setD] = useState<Payload | null>(null)
    const [err, setErr] = useState<string>("")
    const [open, setOpen] = useState<string>("")

    useEffect(() => {
        let cancelled = false
        fetchOperator<Payload>("multibagger").then((r) => {
            if (cancelled) return
            if (r.ok) setD(r.data)
            else setErr(r.error === "auth" ? "로그인 필요" : `불러오기 실패 (${r.status})`)
        })
        return () => {
            cancelled = true
        }
    }, [])

    const m = d?._meta || {}
    const items = d?.items || []
    // 🚨 alert 2건 이상만 화면에 — 1건은 오늘 353/429 라 목록이 아니라 소음이 된다.
    const shown = items.filter((it) => (it.alert_count || 0) >= 2)

    if (err) {
        return (
            <div style={cardStyle(c, RAIL_PAD)}>
                <div style={{ ...CARD_TITLE, color: c.ink }}>멀티배거 워치</div>
                <div style={{ fontSize: 11, color: c.faint, marginTop: 6 }}>{err}</div>
            </div>
        )
    }
    if (!d) return null

    return (
        <div style={cardStyle(c, RAIL_PAD)}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <div style={{ ...CARD_TITLE, color: c.ink }}>멀티배거 워치</div>
                {/* 🚨 이 배지를 지우지 말 것 — 관측/판단 구분의 유일한 표시다 */}
                <span
                    title={m.producer_note || ""}
                    style={{
                        fontSize: 9, fontWeight: 800, color: c.amber, background: c.amberS,
                        borderRadius: 5, padding: "1px 6px", flexShrink: 0,
                    }}
                >
                    관측 전용
                </span>
                <span style={{ fontSize: 9.5, color: c.faint, marginLeft: "auto", ...NUM }}>
                    {m.watch_date || ""}
                </span>
            </div>

            {/* 분모 먼저 — 몇 개 중 몇 개인지 없이 목록만 보이면 전수처럼 읽힌다 */}
            <div style={{ fontSize: 10, color: c.faint, marginTop: 4, ...NUM }}>
                유니버스 {m.universe_n ?? "–"} · 발화 2건 이상 {shown.length}
            </div>

            {/* 🚨 커버리지 자기신고 — 꺼진 방어가 있으면 반드시 보인다 */}
            {(m.acceleration_uncovered_pct ?? 0) > 0 && (
                <div
                    style={{
                        fontSize: 10, lineHeight: 1.45, color: c.amber, background: c.amberS,
                        borderRadius: 6, padding: "6px 8px", marginTop: 7,
                    }}
                >
                    매출가속의 <b>연속성 방어가 꺼진</b> 종목 {m.acceleration_uncovered_n}/{m.universe_n}
                    {" "}({m.acceleration_uncovered_pct}%) — DART 분기매출 백필 미완
                </div>
            )}

            <div style={{ marginTop: 8, maxHeight: 320, overflowY: "auto" }}>
                {shown.length === 0 && (
                    <div style={{ fontSize: 11, color: c.faint, padding: "6px 2px" }}>
                        오늘 2건 이상 발화한 종목 없음
                    </div>
                )}
                {shown.map((it) => {
                    const keys = Object.keys(it.fired || {})
                    const isOpen = open === it.ticker
                    return (
                        <div key={it.ticker} style={{ borderBottom: `1px solid ${c.line}` }}>
                            <div
                                onClick={() => setOpen(isOpen ? "" : it.ticker || "")}
                                style={{
                                    display: "flex", alignItems: "center", gap: 7,
                                    padding: "6px 2px", cursor: "pointer",
                                }}
                                onMouseEnter={(e) => (e.currentTarget.style.background = hoverBg(dark))}
                                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                            >
                                <span
                                    style={{
                                        fontSize: 9.5, fontWeight: 800, color: c.vt, background: c.vtS,
                                        borderRadius: 5, padding: "1px 6px", flexShrink: 0, ...NUM,
                                    }}
                                >
                                    {it.alert_count}
                                </span>
                                <StockLogo ticker={it.ticker} name={it.name} size={17} />
                                <span
                                    onClick={(e) => {
                                        e.stopPropagation()
                                        if (it.ticker) selectTicker(it.ticker, it.name)
                                    }}
                                    style={{
                                        fontSize: 12, fontWeight: 700, color: c.ink, minWidth: 0,
                                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                                    }}
                                >
                                    {it.name || it.ticker}
                                </span>
                                <span style={{ fontSize: 9, color: c.faint, marginLeft: "auto", flexShrink: 0 }}>
                                    {it.lynch_class || ""}
                                </span>
                            </div>
                            {isOpen && (
                                <div style={{ padding: "2px 2px 8px 30px" }}>
                                    {keys.map((k) => (
                                        <div key={k} style={{ fontSize: 10, lineHeight: 1.5, color: c.sub, marginTop: 3 }}>
                                            <b style={{ color: c.ink }}>{LABEL[k] || k}</b>
                                            {(it.fired || {})[k]?.score != null && (
                                                <span style={{ ...NUM, color: c.faint }}> {(it.fired || {})[k].score}</span>
                                            )}
                                            <div style={{ color: c.faint }}>{(it.fired || {})[k]?.reason || ""}</div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )
                })}
            </div>
        </div>
    )
}
