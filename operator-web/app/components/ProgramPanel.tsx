"use client"
// ProgramPanel — 프로그램매매 순매수 (태스크 #14-②, 2026-08-04 실측 shape 확정 후 구현).
// 소스 = Railway /program/{K|Q} (KIS comp-program-trade-today, 시간대별 누적 · 마지막 행 = 최신).
// 필드(실측): bsop_hour · arbt_*(차익) · nabt_*(비차익) 매도/매수 거래대금(tr_pbmn, 백만원 관례).
import { useEffect, useState } from "react"
import { useDark, palette, cardStyle, FONT, NUM, CARD_TITLE, type Palette } from "@/lib/theme"
import { fetchRailway } from "@/lib/api"

type Row = Record<string, string>
type Parsed = {
    hour: string
    arbNet: number   // 차익 순매수 (매수-매도, 백만원)
    nabNet: number   // 비차익 순매수
}

function parseLast(rows: Row[] | undefined): Parsed | null {
    if (!Array.isArray(rows) || rows.length === 0) return null
    const r = rows[rows.length - 1]
    const f = (k: string) => parseFloat(String(r[k] ?? "0").replace(/,/g, "")) || 0
    const hour = String(r.bsop_hour || "")
    return {
        hour: hour.length >= 4 ? `${hour.slice(0, 2)}:${hour.slice(2, 4)}` : hour,
        arbNet: f("arbt_smtn_shnu_tr_pbmn") - f("arbt_smtn_seln_tr_pbmn"),
        nabNet: f("nabt_smtn_shnu_tr_pbmn") - f("nabt_smtn_seln_tr_pbmn"),
    }
}

// 백만원 → 조/억 표기
function fmtMn(v: number): string {
    const eok = v / 100 // 백만원 → 억
    const sign = eok > 0 ? "+" : ""
    if (Math.abs(eok) >= 10000) return `${sign}${(eok / 10000).toFixed(2)}조`
    return `${sign}${Math.round(eok).toLocaleString()}억`
}

export default function ProgramPanel() {
    const dark = useDark()
    const c = palette(dark)
    const [k, setK] = useState<Parsed | null>(null)
    const [q, setQ] = useState<Parsed | null>(null)
    const [loaded, setLoaded] = useState(false)

    useEffect(() => {
        let stop = false
        async function pull() {
            const [rk, rq] = await Promise.all([
                fetchRailway<{ program?: { output?: Row[] } }>("program/K"),
                fetchRailway<{ program?: { output?: Row[] } }>("program/Q"),
            ])
            if (stop) return
            if (rk.ok) setK(parseLast(rk.data.program?.output))
            if (rq.ok) setQ(parseLast(rq.data.program?.output))
            setLoaded(true)
        }
        pull()
        const t = setInterval(pull, 60000)
        return () => {
            stop = true
            clearInterval(t)
        }
    }, [])

    const row = (label: string, p: Parsed | null) => {
        const total = p ? p.arbNet + p.nabNet : null
        const col = total == null ? c.faint : total > 0 ? c.up : total < 0 ? c.down : c.faint
        return (
            <div key={label} style={{ display: "flex", alignItems: "baseline", gap: 10, padding: "7px 0", borderTop: label === "코스피" ? "none" : `1px solid ${c.line}` }}>
                <span style={{ fontSize: 12.5, fontWeight: 700, color: c.ink, width: 52, flexShrink: 0 }}>{label}</span>
                <span style={{ fontSize: 14, fontWeight: 800, color: col, ...NUM }}>{total != null ? fmtMn(total) : "—"}</span>
                <span style={{ fontSize: 10.5, color: c.sub, ...NUM, marginLeft: "auto" }}>
                    차익 {p ? fmtMn(p.arbNet) : "—"} · 비차익 {p ? fmtMn(p.nabNet) : "—"}
                </span>
                {p?.hour ? <span style={{ fontSize: 9.5, color: c.faint, ...NUM, flexShrink: 0 }}>{p.hour}</span> : null}
            </div>
        )
    }

    return (
        <div style={{ ...cardStyle(c, "14px 16px"), fontFamily: FONT }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 7, marginBottom: 6 }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: c.down, alignSelf: "center", flexShrink: 0 }} />
                <span style={{ ...CARD_TITLE, color: c.ink }}>프로그램매매 순매수</span>
                <span style={{ fontSize: 10, color: c.faint }}>KIS 공식 · 60초 갱신 · 백만원 원계</span>
            </div>
            {!loaded ? (
                <div style={{ fontSize: 12, color: c.faint, padding: "4px 0" }}>불러오는 중…</div>
            ) : !k && !q ? (
                <div style={{ fontSize: 12, color: c.sub, padding: "4px 0" }}>데이터 없음 (장외에는 빈 값일 수 있음).</div>
            ) : (
                <>
                    {row("코스피", k)}
                    {row("코스닥", q)}
                    <div style={{ fontSize: 9.5, color: c.faint, paddingTop: 6 }}>양수 = 프로그램 순매수 · 사실 · 매수/매도 지시 아님</div>
                </>
            )}
        </div>
    )
}
