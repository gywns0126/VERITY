"use client"
// PicksTable — 오늘의 추천 (dense 테이블, 구 OperatorPicks 카드 리스트 대체 — Bloomberg 밀도).
// 행 클릭 = 링크그룹 전환. 추천 이유 = 사실 드라이버 칩(취사선택 결정: 리포트 삭제 → 추천이유 직접 실음).
// RULE 7: brain = 가설(N<252) 라벨 상시.
import { useState } from "react"
import { useDark, palette, cardStyle, FONT, NUM, CARD_TITLE, MAIN_PAD, hoverBg, type Palette } from "@/lib/theme"
import { selectTicker, type Rec } from "@/lib/types"
import StockLogo from "./StockLogo"

function num(v: unknown): number | null {
    return typeof v === "number" && isFinite(v) ? v : null
}

function driversOf(r: Rec): string[] {
    const out: string[] = []
    const per = num(r.per)
    const pbr = num(r.pbr)
    if (pbr !== null && pbr > 0 && pbr <= 1) out.push(`PBR ${pbr.toFixed(1)} 저평가`)
    else if (per !== null && per > 0 && per <= 10) out.push(`PER ${per.toFixed(1)} 저평가`)
    const drop = num(r.drop_from_high_pct)
    if (drop !== null && drop <= -30) out.push(`고점대비 ${drop.toFixed(0)}%`)
    const fn = r.flow ? num(r.flow.foreign_net) : null
    if (fn !== null && fn > 0) out.push("외인 순매수")
    else if (fn !== null && fn < 0) out.push("외인 순매도")
    if (r.lynch_kr && r.lynch_kr.label) out.push(`Lynch ${r.lynch_kr.label}`)
    const sev = r.dart_disclosure_events ? num(r.dart_disclosure_events.severity) : null
    if (sev !== null && sev >= 3) out.push("공시 리스크")
    return out.slice(0, 2)
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

export default function PicksTable({ recs, status }: { recs: Rec[]; status: "loading" | "ok" | "error" }) {
    const dark = useDark()
    const c = palette(dark)
    const [all, setAll] = useState(false)

    const sorted = recs.slice().sort((a, b) => {
        const sa = brainOf(a).score
        const sb = brainOf(b).score
        return (sb === null ? -1 : sb) - (sa === null ? -1 : sa)
    })
    const shown = all ? sorted : sorted.slice(0, 12)

    const th = { fontSize: 10, fontWeight: 700 as const, color: c.faint, textAlign: "right" as const, padding: "4px 8px", whiteSpace: "nowrap" as const }
    const td = { fontSize: 12, color: c.sub, textAlign: "right" as const, padding: "6px 8px", whiteSpace: "nowrap" as const, ...NUM }

    return (
        <div style={{ ...cardStyle(c, MAIN_PAD), fontFamily: FONT, display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 9 }}>
                    <span style={{ ...CARD_TITLE, color: c.ink }}>오늘의 추천</span>
                    <span style={{ fontSize: 10, color: c.faint }}>스캔 5,000 → 후보 25 → 추천 {recs.length} → 중용 사이징</span>
                </div>
                <span style={{ fontSize: 10, color: c.faint }}>가설 · 검증 N&lt;252 (2027)</span>
            </div>

            {status === "loading" ? (
                <div style={{ fontSize: 12.5, color: c.faint, padding: "4px 0" }}>불러오는 중…</div>
            ) : shown.length === 0 ? (
                <div style={{ fontSize: 12.5, color: c.sub, padding: "4px 0" }}>추천 종목이 없습니다.</div>
            ) : (
                <div style={{ overflowX: "auto" }}>
                    {/* 🚨 tableLayout fixed + colgroup 명시 폭 — auto layout 은 렌더된 행 내용 폭으로
                        열을 재계산해 접기/펼치기 때 열 위치가 움직임 (PM 2026-08-03 지적). */}
                    <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 720, tableLayout: "fixed" }}>
                        <colgroup>
                            <col style={{ width: 220 }} />
                            <col style={{ width: 70 }} />
                            <col style={{ width: 86 }} />
                            <col style={{ width: 56 }} />
                            <col style={{ width: 52 }} />
                            <col style={{ width: 62 }} />
                            <col style={{ width: 96 }} />
                            <col />
                        </colgroup>
                        <thead>
                            <tr>
                                <th style={{ ...th, textAlign: "left" }}>종목</th>
                                <th style={th}>판단</th>
                                <th style={th}>브레인</th>
                                <th style={th}>PER</th>
                                <th style={th}>PBR</th>
                                <th style={th}>ROE</th>
                                <th style={th}>기준가</th>
                                <th style={{ ...th, textAlign: "left" }}>이유</th>
                            </tr>
                        </thead>
                        <tbody>
                            {shown.map((r, i) => {
                                const b = brainOf(r)
                                const isUS = r.currency === "USD"
                                const price = num(r.rec_price)
                                const per = num(r.per)
                                const pbr = num(r.pbr)
                                const roe = num(r.roe)
                                const accent = recColor(c, r.recommendation)
                                const drivers = driversOf(r)
                                return (
                                    <tr
                                        key={(r.ticker || "") + i}
                                        onClick={() => selectTicker(String(r.ticker || ""), r.name)}
                                        onMouseEnter={(e) => { e.currentTarget.style.background = hoverBg(dark) }}
                                        onMouseLeave={(e) => { e.currentTarget.style.background = "transparent" }}
                                        style={{ cursor: "pointer", borderTop: i === 0 ? "none" : `1px solid ${c.line}` }}
                                    >
                                        <td style={{ ...td, textAlign: "left", overflow: "hidden" }}>
                                            <span style={{ display: "flex", alignItems: "center", gap: 7, minWidth: 0 }}>
                                                <StockLogo ticker={r.ticker} name={r.name} size={20} />
                                                <span style={{ fontSize: 12.5, fontWeight: 700, color: c.ink, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{r.name || r.ticker}</span>
                                                <span style={{ fontSize: 10, color: c.faint, ...NUM, flexShrink: 0 }}>{r.ticker}</span>
                                            </span>
                                        </td>
                                        <td style={td}>
                                            <span style={{ fontSize: 10, fontWeight: 800, color: "#fff", background: accent, borderRadius: 6, padding: "2px 7px" }}>{recLabel(r.recommendation)}</span>
                                        </td>
                                        <td style={{ ...td, fontWeight: 700, color: c.ink }}>
                                            {b.score !== null ? Math.round(b.score) : "—"}
                                            {b.grade ? <span style={{ fontWeight: 500, color: c.faint }}> {b.grade}</span> : null}
                                        </td>
                                        <td style={td}>{per !== null ? per.toFixed(1) : "—"}</td>
                                        <td style={td}>{pbr !== null ? pbr.toFixed(1) : "—"}</td>
                                        <td style={td}>{roe !== null ? roe.toFixed(1) + "%" : "—"}</td>
                                        <td style={{ ...td, fontWeight: 700, color: c.ink }}>
                                            {price !== null ? (isUS ? "$" + price.toFixed(2) : Math.round(price).toLocaleString()) : "—"}
                                        </td>
                                        <td style={{ ...td, textAlign: "left", overflow: "hidden" }}>
                                            {drivers.map((d, j) => (
                                                <span key={j} style={{ fontSize: 10, fontWeight: 600, color: c.vt, background: c.vtS, borderRadius: 6, padding: "2px 6px", marginRight: 4, whiteSpace: "nowrap", display: "inline-block" }}>{d}</span>
                                            ))}
                                        </td>
                                    </tr>
                                )
                            })}
                        </tbody>
                    </table>
                </div>
            )}

            {sorted.length > 12 ? (
                <button onClick={() => setAll((v) => !v)} style={{ border: "none", background: c.hi, color: c.sub, borderRadius: 9, padding: "7px 0", fontSize: 11.5, fontWeight: 700, cursor: "pointer", fontFamily: FONT }}>
                    {all ? "접기" : `전체 ${sorted.length}종목 보기`}
                </button>
            ) : null}
        </div>
    )
}
