"use client"
// MacroPanel — 거시(숲) 창 (PM 플랜: "대표로서의 시각. 숲을 보는거지. 나무는 네가 봐주고").
// 레짐 톤 + 모닝 브리핑 헤드라인 + 섹터 사이클 + 지정학·글로벌 이벤트 + 속보.
// 소스 = portfolio_full 에 이미 실린 briefing/sector_rotation/global_events/headlines —
// 신규 빌더·추가 fetch 0. 거시 3종 LLM 시나리오 밴드는 후속(빌더 필요).
import { useDark, palette, cardStyle, FONT, type Palette } from "@/lib/theme"
import type { PortfolioFull } from "@/lib/types"

function toneColor(c: Palette, tone?: string): { fg: string; bg: string } {
    const t = String(tone || "")
    if (/위험|부정|risk_off|경계|하락/i.test(t)) return { fg: c.up, bg: c.upS }
    if (/긍정|호전|risk_on|상승/i.test(t)) return { fg: c.green, bg: c.greenS }
    return { fg: c.sub, bg: c.hi }
}

export default function MacroPanel({ data }: { data: PortfolioFull | null }) {
    const dark = useDark()
    const c = palette(dark)
    const briefing = data?.briefing
    const rot = data?.sector_rotation
    const events = (data?.global_events || []).filter((e) => e && e.name)
    const highEvents = events.filter((e) => String(e.severity || "").toLowerCase() === "high")
    const shownEvents = (highEvents.length ? highEvents : events).slice(0, 3)
    const news = [
        ...(data?.bloomberg_google_headlines || []).slice(0, 3),
        ...(data?.headlines || []).slice(0, 3),
    ].filter((h) => h && h.title)

    const tone = toneColor(c, briefing?.tone)

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

            {/* 섹터 사이클 */}
            {rot?.cycle_label || rot?.cycle_desc ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                    <div style={{ fontSize: 10, fontWeight: 700, color: c.faint }}>
                        사이클 {rot?.cycle_label ? <span style={{ color: c.vt }}>{rot.cycle_label}</span> : null}
                    </div>
                    {rot?.cycle_desc ? <div style={{ fontSize: 11.5, color: c.sub, lineHeight: 1.45 }}>{rot.cycle_desc}</div> : null}
                    {rot?.recommended_sectors?.length ? (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                            {rot.recommended_sectors.slice(0, 4).map((s, i) => (
                                <span key={i} style={{ fontSize: 10, fontWeight: 700, color: c.vt, background: c.vtS, borderRadius: 6, padding: "2px 7px" }}>{s}</span>
                            ))}
                        </div>
                    ) : null}
                </div>
            ) : null}

            {/* 지정학·글로벌 이벤트 */}
            {shownEvents.length ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 6, borderTop: `1px solid ${c.line}`, paddingTop: 8 }}>
                    <div style={{ fontSize: 10, fontWeight: 700, color: c.faint }}>지정학 · 이벤트</div>
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

            {/* 속보 (글로벌 + 국내) */}
            {news.length ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 5, borderTop: `1px solid ${c.line}`, paddingTop: 8 }}>
                    <div style={{ fontSize: 10, fontWeight: 700, color: c.faint }}>속보</div>
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

            <div style={{ fontSize: 9.5, color: c.faint }}>사실·수집 헤드라인 · 거시 3종 LLM 시나리오는 후속 · 매수/매도 지시 아님</div>
        </div>
    )
}
