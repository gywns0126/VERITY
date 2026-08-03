"use client"
// MacroPanel — 거시(숲) 창 + 거시 경제 분석기 (PM 2026-08-03).
// ① 분석기 = 거시 3종 LLM 시나리오 (macro_synthesis, 평일 장전 07:50 생성, authed)
// ② 자기 산식 market_horizon (과열 판정·침체확률·CAPE·구간 분포 — 가설 라벨, RULE 7)
// ③ daily_report (일일 분석·전략·리스크·내일 관점) ④ 레짐 톤·사이클·지정학·속보.
// ②~④ = portfolio_full 기존 키 (추가 fetch 0) / ① 만 별도 authed fetch.
import { useEffect, useState } from "react"
import { useDark, palette, cardStyle, FONT, NUM, type Palette } from "@/lib/theme"
import { fetchOperator } from "@/lib/api"
import type { PortfolioFull } from "@/lib/types"

function toneColor(c: Palette, tone?: string): { fg: string; bg: string } {
    const t = String(tone || "")
    if (/위험|부정|risk_off|경계|하락/i.test(t)) return { fg: c.up, bg: c.upS }
    if (/긍정|호전|risk_on|상승/i.test(t)) return { fg: c.green, bg: c.greenS }
    return { fg: c.sub, bg: c.hi }
}

// 구 캐시 마크다운 방어 정리 (tri 패널 정합)
function plain(t?: string): string {
    return String(t || "")
        .replace(/\*\*/g, "")
        .replace(/^#{1,4}\s*/gm, "")
        .replace(/^\s*[*•]\s+/gm, "- ")
}

type SynSource = { content?: string; model?: string; citations?: string[] }
type MacroSyn = {
    generated_at?: string
    sources?: { claude?: SynSource; perplexity?: SynSource; gemini?: SynSource }
}

export default function MacroPanel({ data }: { data: PortfolioFull | null }) {
    const dark = useDark()
    const c = palette(dark)
    const [syn, setSyn] = useState<MacroSyn | null>(null)
    const [synStatus, setSynStatus] = useState<"loading" | "ok" | "none">("loading")

    useEffect(() => {
        let cancelled = false
        fetchOperator<MacroSyn>("macro_synthesis").then((r) => {
            if (cancelled) return
            if (r.ok && r.data?.sources?.claude?.content) {
                setSyn(r.data)
                setSynStatus("ok")
            } else {
                setSynStatus("none")
            }
        })
        return () => {
            cancelled = true
        }
    }, [])

    const briefing = data?.briefing
    const rot = data?.sector_rotation
    const mh = data?.market_horizon
    const dr = data?.daily_report
    const events = (data?.global_events || []).filter((e) => e && e.name)
    const highEvents = events.filter((e) => String(e.severity || "").toLowerCase() === "high")
    const shownEvents = (highEvents.length ? highEvents : events).slice(0, 3)
    const news = [
        ...(data?.bloomberg_google_headlines || []).slice(0, 3),
        ...(data?.headlines || []).slice(0, 3),
    ].filter((h) => h && h.title)

    const tone = toneColor(c, briefing?.tone)
    const secTitle = (t: string, extra?: string) => (
        <div style={{ fontSize: 10, fontWeight: 700, color: c.faint }}>
            {t} {extra ? <span style={{ fontWeight: 500 }}>{extra}</span> : null}
        </div>
    )
    const divider = { borderTop: `1px solid ${c.line}`, paddingTop: 8 }

    if (!data) {
        return <div style={{ ...cardStyle(c, "13px 15px"), fontFamily: FONT, fontSize: 12, color: c.faint }}>거시 데이터 불러오는 중…</div>
    }

    return (
        <div style={{ ...cardStyle(c, "13px 15px"), fontFamily: FONT, display: "flex", flexDirection: "column", gap: 10 }}>
            {/* 레짐 톤 + 브리핑 헤드라인 */}
            <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap" }}>
                {briefing?.tone ? (
                    <span style={{ fontSize: 10, fontWeight: 800, color: tone.fg, background: tone.bg, borderRadius: 6, padding: "3px 8px" }}>
                        {briefing.tone}
                    </span>
                ) : null}
                <span style={{ fontSize: 12.5, fontWeight: 700, color: c.ink, lineHeight: 1.4, flex: 1, minWidth: 0 }}>
                    {briefing?.headline || "브리핑 없음"}
                </span>
            </div>

            {/* ① 거시 분석기 — 3종 LLM 시나리오 (데스크 노트) */}
            <div style={{ display: "flex", flexDirection: "column", gap: 6, ...divider }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                    <span style={{ fontSize: 10.5, fontWeight: 800, color: c.vt }}>거시 분석기</span>
                    <span style={{ fontSize: 9.5, color: c.faint }}>
                        3종 LLM 시나리오 · 평일 장전 생성{syn?.generated_at ? ` · ${String(syn.generated_at).slice(5, 16).replace("T", " ")}` : ""}
                    </span>
                </div>
                {synStatus === "loading" ? (
                    <div style={{ fontSize: 11.5, color: c.faint }}>불러오는 중…</div>
                ) : synStatus === "none" ? (
                    <div style={{ fontSize: 11.5, color: c.sub, lineHeight: 1.5 }}>
                        아직 미적재 — 평일 07:50 장전 배치 후 자동 표시됩니다.
                    </div>
                ) : (
                    <div style={{ fontSize: 12, color: c.ink, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>
                        {plain(syn?.sources?.claude?.content)}
                    </div>
                )}
            </div>

            {/* ② 자기 산식 market_horizon — 가설 라벨 (RULE 7) */}
            {mh?.verdict ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 6, ...divider }}>
                    {secTitle("시장 지평", "자기 산식 · 가설 N<252")}
                    <div style={{ fontSize: 11.5, fontWeight: 700, color: c.ink, lineHeight: 1.45 }}>{mh.verdict}</div>
                    {mh.horizons ? (
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6 }}>
                            {(["1m", "3m", "6m", "12m"] as const).map((k) => {
                                const b = mh.horizons?.[k]
                                if (!b || typeof b.median !== "number") return null
                                const md = b.median * 100
                                const col = md > 0 ? c.up : md < 0 ? c.down : c.faint
                                return (
                                    <div key={k} style={{ background: c.hi, borderRadius: 8, padding: "5px 7px", display: "flex", flexDirection: "column", gap: 1 }}>
                                        <span style={{ fontSize: 9, fontWeight: 700, color: c.faint }}>{k.toUpperCase()} 중앙값</span>
                                        <span style={{ fontSize: 11.5, fontWeight: 800, color: col, ...NUM }}>{md > 0 ? "+" : ""}{md.toFixed(0)}%</span>
                                        {typeof b.p25 === "number" && typeof b.p75 === "number" ? (
                                            <span style={{ fontSize: 8.5, color: c.faint, ...NUM }}>{(b.p25 * 100).toFixed(0)}~{(b.p75 * 100) > 0 ? "+" : ""}{(b.p75 * 100).toFixed(0)}%</span>
                                        ) : null}
                                    </div>
                                )
                            })}
                        </div>
                    ) : null}
                </div>
            ) : null}

            {/* ③ 일일 리포트 (Gemini) */}
            {dr && (dr.market_analysis || dr.strategy) ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 5, ...divider }}>
                    {secTitle("일일 리포트")}
                    {([
                        ["분석", dr.market_analysis],
                        ["전략", dr.strategy],
                        ["리스크", dr.risk_watch],
                        ["내일", dr.tomorrow_outlook],
                    ] as Array<[string, string | undefined]>).map(([k, v]) =>
                        v ? (
                            <div key={k} style={{ fontSize: 11.5, color: c.sub, lineHeight: 1.45 }}>
                                <span style={{ fontWeight: 800, color: c.ink }}>{k}</span> {v}
                            </div>
                        ) : null
                    )}
                </div>
            ) : null}

            {/* 섹터 사이클 */}
            {rot?.cycle_label || rot?.cycle_desc ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 5, ...divider }}>
                    {secTitle("사이클")}
                    <div style={{ fontSize: 11.5, color: c.sub, lineHeight: 1.45 }}>
                        {rot?.cycle_label ? <span style={{ color: c.vt, fontWeight: 800 }}>{rot.cycle_label} </span> : null}
                        {rot?.cycle_desc || ""}
                    </div>
                    {rot?.recommended_sectors?.length ? (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                            {/* 🚨 객체 배열 — s.name 만 렌더 (문자열 취급 = 크래시, 2026-08-03 실사고) */}
                            {rot.recommended_sectors.slice(0, 4).map((s, i) => (
                                <span key={i} style={{ fontSize: 10, fontWeight: 700, color: c.vt, background: c.vtS, borderRadius: 6, padding: "2px 7px", ...NUM }}>
                                    {s?.name || "—"}{typeof s?.change_pct === "number" ? ` ${s.change_pct > 0 ? "+" : ""}${s.change_pct.toFixed(1)}%` : ""}
                                </span>
                            ))}
                        </div>
                    ) : null}
                </div>
            ) : null}

            {/* 지정학·글로벌 이벤트 */}
            {shownEvents.length ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 6, ...divider }}>
                    {secTitle("지정학 · 이벤트")}
                    {shownEvents.map((e, i) => (
                        <div key={i} style={{ display: "flex", flexDirection: "column", gap: 2 }} title={e.action || ""}>
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                {String(e.severity || "").toLowerCase() === "high" ? (
                                    <span style={{ fontSize: 9, fontWeight: 800, color: c.up, background: c.upS, borderRadius: 5, padding: "1px 5px", flexShrink: 0 }}>중요</span>
                                ) : null}
                                <span style={{ fontSize: 12, fontWeight: 700, color: c.ink }}>{e.name}</span>
                                {e.country ? <span style={{ fontSize: 10, color: c.faint }}>{e.country}</span> : null}
                            </div>
                            {e.impact ? (
                                <div style={{ fontSize: 11, color: c.sub, lineHeight: 1.4, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
                                    {e.impact}
                                </div>
                            ) : null}
                        </div>
                    ))}
                </div>
            ) : null}

            {/* 속보 */}
            {news.length ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 5, ...divider }}>
                    {secTitle("속보")}
                    {news.map((h, i) => (
                        <a
                            key={i}
                            href={h.link || "#"}
                            target="_blank"
                            rel="noreferrer"
                            style={{ fontSize: 11.5, color: c.sub, textDecoration: "none", lineHeight: 1.4, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                        >
                            {h.title}
                        </a>
                    ))}
                </div>
            ) : null}

            <a href="/macro" style={{ display: "block", textAlign: "center", background: c.hi, color: c.vt, borderRadius: 9, padding: "8px 0", fontSize: 11.5, fontWeight: 800, textDecoration: "none" }}>
                거시 전체 보기 — 섹터 · 이벤트 · 월가 · 고래
            </a>
            <div style={{ fontSize: 9.5, color: c.faint }}>LLM 의견=의견 · 자기 산식=가설 · 매수/매도 지시 아님</div>
        </div>
    )
}
