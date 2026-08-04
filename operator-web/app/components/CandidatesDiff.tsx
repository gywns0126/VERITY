"use client"
// CandidatesDiff — 후보 유니버스 편입/이탈 (태스크 #14-①). 깔때기가 오늘 바꾼 것만.
// 소스 = authed /api/admin?type=candidates_diff (universe_scan 후 산출, LLM 0).
// 변화 없으면 카드 자체를 숨김 — "없음"으로 화면 부동산 낭비 금지.
import { useEffect, useState } from "react"
import { useDark, palette, cardStyle, FONT, NUM, CARD_TITLE, RAIL_PAD } from "@/lib/theme"
import { fetchOperator } from "@/lib/api"
import { selectTicker } from "@/lib/types"
import StockLogo from "./StockLogo"

type Item = { ticker?: string; name?: string; market?: string }
type Diff = {
    generated_at?: string
    added?: Item[]
    removed?: Item[]
    kept_count?: number
    total?: number
}

export default function CandidatesDiff() {
    const dark = useDark()
    const c = palette(dark)
    const [d, setD] = useState<Diff | null>(null)

    useEffect(() => {
        let cancelled = false
        fetchOperator<Diff>("candidates_diff").then((r) => {
            if (!cancelled && r.ok) setD(r.data)
        })
        return () => {
            cancelled = true
        }
    }, [])

    const added = d?.added || []
    const removed = d?.removed || []
    if (!d || (added.length === 0 && removed.length === 0)) return null

    const row = (it: Item, kind: "in" | "out") => {
        const col = kind === "in" ? c.up : c.down
        const bg = kind === "in" ? c.upS : c.downS
        return (
            <div
                key={kind + it.ticker}
                onClick={() => it.ticker && selectTicker(it.ticker, it.name)}
                style={{ display: "flex", alignItems: "center", gap: 7, padding: "5px 2px", cursor: "pointer" }}
            >
                <span style={{ fontSize: 9, fontWeight: 800, color: col, background: bg, borderRadius: 5, padding: "1px 6px", flexShrink: 0 }}>
                    {kind === "in" ? "편입" : "이탈"}
                </span>
                <StockLogo ticker={it.ticker} name={it.name} size={17} />
                <span style={{ fontSize: 12, fontWeight: 700, color: c.ink, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {it.name || it.ticker}
                </span>
                <span style={{ fontSize: 9.5, color: c.faint, marginLeft: "auto", ...NUM, flexShrink: 0 }}>{it.market || ""}</span>
            </div>
        )
    }

    return (
        <div style={{ ...cardStyle(c, RAIL_PAD), fontFamily: FONT, display: "flex", flexDirection: "column", gap: 2 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 7, marginBottom: 4 }}>
                <span style={{ ...CARD_TITLE, color: c.ink }}>후보 변경</span>
                <span style={{ fontSize: 10, color: c.faint, ...NUM }}>
                    편입 {added.length} · 이탈 {removed.length} · 유지 {d.kept_count ?? "—"}/{d.total ?? "—"}
                </span>
            </div>
            {added.slice(0, 5).map((it) => row(it, "in"))}
            {removed.slice(0, 5).map((it) => row(it, "out"))}
            <div style={{ fontSize: 9.5, color: c.faint, paddingTop: 5 }}>깔때기 스캔 결과 변화 · 매수/매도 지시 아님</div>
        </div>
    )
}
