"use client"
// OperatorPicks — 오늘의 추천 종목 (오퍼레이터 전용, authed). 공개 알파네스트 디자인.
// 되돌리지 말 것: fetchOperator("portfolio_full") 만 읽음(Bearer). 공개 blob 직독 금지(봉인).
//   brain_score 노출은 authed 라 허용, 단 RULE 7 "가설 · 검증 N<252" 라벨 병기 의무.
import { useEffect, useState } from "react"
import { useDark, palette, cardStyle, FONT, NUM, type Palette } from "@/lib/theme"
import { fetchOperator } from "@/lib/api"

type Brain = { brain_score?: number; grade_label?: string; grade?: string }
type Rec = {
    name?: string
    ticker?: string
    currency?: string
    recommendation?: string
    verity_brain?: Brain
    brain_score?: number
    per?: number
    pbr?: number
    roe?: number
    rec_price?: number
    ai_verdict?: string
}

function num(v: unknown): number | null {
    return typeof v === "number" && isFinite(v) ? v : null
}

function brainOf(r: Rec): { score: number | null; grade: string } {
    const vb = r.verity_brain || null
    const score = vb && num(vb.brain_score) !== null ? (vb.brain_score as number) : num(r.brain_score)
    const grade = vb && vb.grade_label ? vb.grade_label : vb && vb.grade ? vb.grade : ""
    return { score, grade }
}

function recLabel(rec?: string): string {
    const r = String(rec || "").toUpperCase()
    if (r === "STRONG_BUY") return "적극매수"
    if (r === "BUY") return "매수"
    if (r === "AVOID") return "회피"
    if (r === "CAUTION") return "주의"
    return "관망"
}

function recColor(c: Palette, rec?: string): string {
    const r = String(rec || "").toUpperCase()
    if (r.indexOf("BUY") >= 0) return c.up
    if (r.indexOf("AVOID") >= 0) return c.down
    return c.faint
}

export default function OperatorPicks({ limit = 20 }: { limit?: number }) {
    const dark = useDark()
    const c = palette(dark)
    const [recs, setRecs] = useState<Rec[]>([])
    const [status, setStatus] = useState<"loading" | "ok" | "auth" | "error">("loading")

    useEffect(() => {
        let cancelled = false
        fetchOperator<{ recommendations?: Rec[] }>("portfolio_full").then((r) => {
            if (cancelled) return
            if (!r.ok) {
                setStatus(r.error === "auth" ? "auth" : "error")
                return
            }
            setRecs(r.data.recommendations || [])
            setStatus("ok")
        })
        return () => {
            cancelled = true
        }
    }, [])

    const head = (
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
            <div style={{ color: c.ink, fontSize: 15, fontWeight: 800, letterSpacing: "-0.02em" }}>오늘의 추천 종목</div>
            <div style={{ color: c.faint, fontSize: 11 }}>가설 · 검증 N&lt;252 (2027) · 예측 아님</div>
        </div>
    )

    if (status === "auth" || status === "error") {
        return (
            <div style={{ fontFamily: FONT, display: "flex", flexDirection: "column", gap: 10 }}>
                {head}
                <div style={{ color: status === "auth" ? c.sub : c.down, fontSize: 13, lineHeight: 1.5 }}>
                    {status === "auth" ? "오퍼레이터 로그인이 필요합니다 (VERITY = 비공개)." : "데이터를 불러오지 못했습니다."}
                </div>
            </div>
        )
    }

    const sorted = recs.slice().sort((a, b) => {
        const sa = brainOf(a).score
        const sb = brainOf(b).score
        return (sb === null ? -1 : sb) - (sa === null ? -1 : sa)
    })
    const shown = sorted.slice(0, limit)

    return (
        <div style={{ fontFamily: FONT, display: "flex", flexDirection: "column", gap: 10 }}>
            {head}
            {shown.map((r, i) => {
                const b = brainOf(r)
                const isUS = r.currency === "USD"
                const price = num(r.rec_price)
                const per = num(r.per)
                const pbr = num(r.pbr)
                const roe = num(r.roe)
                const accent = recColor(c, r.recommendation)
                return (
                    <div key={(r.ticker || "") + i} style={{ ...cardStyle(c, "12px 14px"), display: "flex", flexDirection: "column", gap: 8 }}>
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                            <div style={{ display: "flex", alignItems: "baseline", gap: 7, minWidth: 0 }}>
                                <span style={{ fontSize: 15, fontWeight: 700, color: c.ink, letterSpacing: "-0.02em", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                                    {r.name || r.ticker}
                                </span>
                                <span style={{ fontSize: 11, color: c.faint, ...NUM }}>{r.ticker}</span>
                            </div>
                            <span style={{ fontSize: 11, fontWeight: 800, color: "#fff", background: accent, borderRadius: 8, padding: "3px 8px", whiteSpace: "nowrap" }}>
                                {recLabel(r.recommendation)}
                            </span>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                            {b.score !== null ? (
                                <span style={{ fontSize: 12, color: c.sub }}>
                                    브레인 <span style={{ color: c.ink, fontWeight: 700, ...NUM }}>{Math.round(b.score)}</span>
                                    {b.grade ? <span style={{ color: c.sub }}> · {b.grade}</span> : null}
                                    <span style={{ color: c.faint, fontSize: 10 }}> (가설)</span>
                                </span>
                            ) : null}
                            {per !== null ? <Metric c={c} k="PER" v={per.toFixed(1)} /> : null}
                            {pbr !== null ? <Metric c={c} k="PBR" v={pbr.toFixed(1)} /> : null}
                            {roe !== null ? <Metric c={c} k="ROE" v={roe.toFixed(1) + "%"} /> : null}
                            {price !== null ? <Metric c={c} k="기준가" v={isUS ? "$" + price.toFixed(2) : Math.round(price).toLocaleString()} /> : null}
                        </div>
                        {r.ai_verdict ? (
                            <div style={{ fontSize: 12, color: c.sub, lineHeight: 1.45, borderTop: `1px solid ${c.line}`, paddingTop: 7 }}>{r.ai_verdict}</div>
                        ) : null}
                    </div>
                )
            })}
            {shown.length === 0 ? <div style={{ color: c.sub, fontSize: 13, padding: "8px 0" }}>추천 종목이 없습니다.</div> : null}
        </div>
    )
}

function Metric({ c, k, v }: { c: Palette; k: string; v: string }) {
    return (
        <span style={{ fontSize: 12, color: c.sub }}>
            {k} <span style={{ color: c.ink, ...NUM }}>{v}</span>
        </span>
    )
}
