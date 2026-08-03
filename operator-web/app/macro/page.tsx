"use client"
// /macro — 거시 전용 페이지 (PM 2026-08-03 "거시 패널이 작은데... 섹터·호재·월가·고래 모든 정보,
// 페이지 하나 새로 파야할듯"). 우레일 거시 창 = 요약, 여기 = 전체.
// 구성: 분석기 노트 + 신선사실 / 매크로 지표 8종 / 섹터 보드(86, 핫·부진) / 로테이션 /
//   시장 지평(가설, 유사국면) / 이벤트 캘린더(D-day) / 월가·국내 헤드라인 / 고래 13F(공개 blob).
// 소스 = portfolio_full(authed) + macro_synthesis(authed) + us_investor_portfolios.json(공개 사실).
import { useEffect, useState } from "react"
import { useDark, palette, cardStyle, FONT, NUM, MAIN_PAD, type Palette } from "@/lib/theme"
import { fetchOperator, fetchPortfolioSlim, fetchPublic } from "@/lib/api"
import { isAuthed } from "@/lib/auth"
import { captureOAuthHash, refreshIfNeeded } from "@/lib/supabase"
import type { PortfolioFull, SectorRow } from "@/lib/types"
import TopBar from "../components/TopBar"
import PanelBoundary from "../components/PanelBoundary"
import StockLogo from "../components/StockLogo"
import SystemActionPanel from "../components/SystemActionPanel"

const MACRO_LABELS: Record<string, string> = {
    usd_krw: "달러 환율", usd_jpy: "엔/달러", eur_usd: "유로/달러", wti_oil: "WTI 유가",
    gold: "금", silver: "은", copper: "구리", vix: "VIX",
}

type GmCite = { title?: string; uri?: string }
type SynSource = { content?: string; model?: string; citations?: string[]; gm_citations?: GmCite[] }
type MacroSyn = { generated_at?: string; sources?: { claude?: SynSource; perplexity?: SynSource; gemini?: SynSource } }
type Holding13F = { ticker?: string; weight_pct?: number; change_type?: string }
type Investor = {
    institution?: string
    person?: string
    disclosed_style?: string
    holdings?: Holding13F[]
    holdings_capped?: Holding13F[]
    trailing_4q_replication_pct?: number
    report_date?: string
}

function plain(t?: string): string {
    return String(t || "").replace(/\*\*/g, "").replace(/^#{1,4}\s*/gm, "").replace(/^\s*[*•]\s+/gm, "- ")
}

export default function MacroPage() {
    const dark = useDark()
    const c = palette(dark)
    const [authed, setAuthed] = useState<boolean | null>(null)
    const [pf, setPf] = useState<PortfolioFull | null>(null)
    const [syn, setSyn] = useState<MacroSyn | null>(null)
    const [whales, setWhales] = useState<Investor[]>([])
    const [allSectors, setAllSectors] = useState(false)

    useEffect(() => {
        captureOAuthHash()
        if (!isAuthed()) {
            window.location.replace("/login")
            return
        }
        setAuthed(true)
        refreshIfNeeded()
        const iv = setInterval(() => refreshIfNeeded(), 60_000)
        return () => clearInterval(iv)
    }, [])

    useEffect(() => {
        if (!authed) return
        let cancelled = false
        fetchPortfolioSlim<PortfolioFull>().then((r) => {
            if (!cancelled && r.ok) setPf(r.data)
        })
        fetchOperator<MacroSyn>("macro_synthesis").then((r) => {
            if (!cancelled && r.ok) setSyn(r.data)
        })
        fetchPublic<{ investors?: Investor[] }>("us_investor_portfolios.json").then((r) => {
            if (!cancelled && r.ok && Array.isArray(r.data.investors)) {
                // 슬림 보관 — 화면이 쓰는 필드·상위 5보유만 state 로 (메모리 규율)
                setWhales(
                    r.data.investors.map((w) => ({
                        institution: w.institution,
                        person: w.person,
                        trailing_4q_replication_pct: w.trailing_4q_replication_pct,
                        report_date: w.report_date,
                        holdings_capped: (w.holdings_capped || w.holdings || [])
                            .slice()
                            .sort((a, b) => (b.weight_pct || 0) - (a.weight_pct || 0))
                            .slice(0, 5)
                            .map((h) => ({ ticker: h.ticker, weight_pct: h.weight_pct, change_type: h.change_type })),
                    }))
                )
            }
        })
        return () => {
            cancelled = true
        }
    }, [authed])

    if (authed === null) return <main style={{ minHeight: "100vh", background: c.bg }} />

    const sectors = (pf?.sectors || []).filter((s) => s && s.name && typeof s.change_pct === "number")
    const sorted = sectors.slice().sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0))
    const hot = sorted.slice(0, 8)
    const cold = sorted.slice(-8).reverse()
    const rot = pf?.sector_rotation
    const mh = pf?.market_horizon
    const events = (pf?.global_events || []).filter((e) => e && e.name)
    const macro = pf?.macro || {}
    const cl = syn?.sources?.claude
    const px = syn?.sources?.perplexity

    // 알파네스트 섹션 문법 — 컬러 닷 아이브로 + 타이틀 + 메타 (좌측 바 아님, 닷만)
    const secTitle = (t: string, n?: string, dot?: string) => (
        <div style={{ display: "flex", alignItems: "baseline", gap: 7, marginBottom: 10 }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: dot || c.vt, alignSelf: "center", flexShrink: 0 }} />
            <span style={{ fontSize: 14, fontWeight: 800, color: c.ink, letterSpacing: "-0.02em" }}>{t}</span>
            {n ? <span style={{ fontSize: 10, color: c.faint }}>{n}</span> : null}
        </div>
    )

    return (
        <main style={{ minHeight: "100vh", background: c.bg, color: c.ink, fontFamily: FONT, WebkitFontSmoothing: "antialiased" }}>
            <TopBar active="macro" />
            <div style={{ maxWidth: 1560, margin: "0 auto", padding: "14px 18px 30px", display: "flex", flexDirection: "column", gap: 12 }}>

                {/* 분석기 노트 + 신선 사실 */}
                <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 2fr) minmax(0, 1fr)", gap: 12, alignItems: "start" }}>
                    <PanelBoundary name="분석기">
                        <div style={{ ...cardStyle(c, MAIN_PAD) }}>
                            {secTitle("거시 분석기 — 오늘의 데스크 노트", `3종 LLM · 평일 07:50${syn?.generated_at ? ` · 생성 ${String(syn.generated_at).slice(5, 16).replace("T", " ")}` : ""}`)}
                            {cl?.content ? (
                                <div style={{ fontSize: 13, color: c.ink, lineHeight: 1.6, whiteSpace: "pre-wrap" }}>{plain(cl.content)}</div>
                            ) : (
                                <div style={{ fontSize: 12.5, color: c.sub }}>미적재 — 평일 장전 배치 후 자동 표시.</div>
                            )}
                        </div>
                    </PanelBoundary>
                    <PanelBoundary name="신선사실">
                        <div style={{ ...cardStyle(c, MAIN_PAD) }}>
                            {secTitle("신선 사실", "Perplexity · 72h")}
                            {px?.content ? (
                                <>
                                    <div style={{ fontSize: 12, color: c.sub, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{plain(px.content)}</div>
                                    {px.citations?.length ? (
                                        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
                                            {px.citations.slice(0, 5).map((u, i) => (
                                                <a key={i} href={u} target="_blank" rel="noreferrer" style={{ fontSize: 10, color: c.vt, textDecoration: "none" }}>글로벌 {i + 1}</a>
                                            ))}
                                        </div>
                                    ) : null}
                                    {/* 국내 근거 — Gemini 구글 그라운딩(T1/T2 필터 통과분만, source_tiers) */}
                                    {(syn?.sources?.gemini as SynSource | undefined)?.gm_citations?.length ? (
                                        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 6 }}>
                                            {(syn!.sources!.gemini!.gm_citations || []).slice(0, 6).map((g, i) => (
                                                <a key={i} href={g.uri || "#"} target="_blank" rel="noreferrer" style={{ fontSize: 10, color: c.green, textDecoration: "none" }}>
                                                    국내 {g.title || i + 1}
                                                </a>
                                            ))}
                                        </div>
                                    ) : null}
                                </>
                            ) : (
                                <div style={{ fontSize: 12.5, color: c.sub }}>미적재.</div>
                            )}
                        </div>
                    </PanelBoundary>
                </div>

                {/* 시스템 작용 — 매크로·게이트의 실작용 (PM 2026-08-03 1번 패널, VERITY #267) */}
                <PanelBoundary name="시스템 작용">
                    <SystemActionPanel c={c} sa={pf?.system_action} />
                </PanelBoundary>

                {/* 매크로 지표 8종 */}
                <PanelBoundary name="지표">
                    <div style={{ ...cardStyle(c, MAIN_PAD) }}>
                        {secTitle("매크로 지표", "환율 · 원자재 · 변동성 · 약 30분 주기", c.green)}
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 8 }}>
                            {Object.keys(MACRO_LABELS).map((k) => {
                                const n = macro[k]
                                if (!n || typeof n.value !== "number") return null
                                const cp = typeof n.change_pct === "number" ? n.change_pct : null
                                const col = cp == null ? c.faint : cp > 0 ? c.up : cp < 0 ? c.down : c.faint
                                return (
                                    <div key={k} style={{ background: c.hi, borderRadius: 10, padding: "8px 10px", display: "flex", flexDirection: "column", gap: 2 }}>
                                        <span style={{ fontSize: 10, fontWeight: 700, color: c.sub }}>{MACRO_LABELS[k]}</span>
                                        <span style={{ fontSize: 14, fontWeight: 800, color: c.ink, ...NUM, whiteSpace: "nowrap" }}>
                                            {n.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                                        </span>
                                        <span style={{ fontSize: 10, fontWeight: 700, color: col, ...NUM }}>
                                            {cp != null ? `${cp > 0 ? "+" : ""}${cp.toFixed(2)}%` : ""}
                                            {typeof n.week_low === "number" && typeof n.week_high === "number" ? (
                                                <span style={{ color: c.faint, fontWeight: 500 }}> · 주 {n.week_low.toLocaleString(undefined, { maximumFractionDigits: 1 })}~{n.week_high.toLocaleString(undefined, { maximumFractionDigits: 1 })}</span>
                                            ) : null}
                                        </span>
                                    </div>
                                )
                            })}
                        </div>
                    </div>
                </PanelBoundary>

                {/* 섹터 보드 */}
                <PanelBoundary name="섹터">
                    <div style={{ ...cardStyle(c, MAIN_PAD) }}>
                        {secTitle("섹터 보드", `${sectors.length}개 업종 · 등락률순`, c.up)}
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(330px, 1fr))", gap: 14 }}>
                            <SectorList c={c} title="핫 섹터" rows={hot} accent={c.up} />
                            <SectorList c={c} title="부진 섹터" rows={cold} accent={c.down} />
                        </div>
                        {sorted.length > 16 ? (
                            <button onClick={() => setAllSectors((v) => !v)} style={{ marginTop: 10, width: "100%", border: "none", background: c.hi, color: c.sub, borderRadius: 9, padding: "8px 0", fontSize: 11.5, fontWeight: 700, cursor: "pointer", fontFamily: FONT }}>
                                {allSectors ? "접기" : `전체 ${sorted.length}개 업종 보기`}
                            </button>
                        ) : null}
                        {allSectors ? (
                            <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 6 }}>
                                {sorted.map((s, i) => {
                                    const cp = s.change_pct || 0
                                    const col = cp > 0 ? c.up : cp < 0 ? c.down : c.faint
                                    return (
                                        <span key={i} style={{ fontSize: 10.5, fontWeight: 700, color: col, background: c.hi, borderRadius: 7, padding: "3px 8px", ...NUM }}>
                                            {s.name} {cp > 0 ? "+" : ""}{cp.toFixed(1)}%
                                        </span>
                                    )
                                })}
                            </div>
                        ) : null}
                    </div>
                </PanelBoundary>

                {/* 로테이션 + 시장 지평 */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))", gap: 12, alignItems: "start" }}>
                    <PanelBoundary name="로테이션">
                        <div style={{ ...cardStyle(c, MAIN_PAD) }}>
                            {secTitle("섹터 로테이션", rot?.cycle_label || "")}
                            {rot?.cycle_desc ? <div style={{ fontSize: 12, color: c.sub, lineHeight: 1.5, marginBottom: 8 }}>{rot.cycle_desc}</div> : null}
                            {(rot?.recommended_sectors || []).slice(0, 4).map((s, i) => (
                                <RotRow key={`r${i}`} c={c} name={s?.name} cp={s?.change_pct} reason={s?.reason} col={c.up} />
                            ))}
                            {(rot?.avoid_sectors || []).slice(0, 3).map((s, i) => (
                                <RotRow key={`a${i}`} c={c} name={s?.name} cp={s?.change_pct} reason={s?.reason} col={c.down} />
                            ))}
                        </div>
                    </PanelBoundary>

                    <PanelBoundary name="지평">
                        <div style={{ ...cardStyle(c, MAIN_PAD) }}>
                            {secTitle("시장 지평", "자기 산식 · 가설 N<252")}
                            {mh?.verdict ? <div style={{ fontSize: 12.5, fontWeight: 700, color: c.ink, lineHeight: 1.5, marginBottom: 8 }}>{mh.verdict}</div> : null}
                            {mh?.horizons ? (
                                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6, marginBottom: 10 }}>
                                    {(["1m", "3m", "6m", "12m"] as const).map((k) => {
                                        const b = mh.horizons?.[k]
                                        if (!b || typeof b.median !== "number") return null
                                        const md = b.median * 100
                                        const col = md > 0 ? c.up : md < 0 ? c.down : c.faint
                                        return (
                                            <div key={k} style={{ background: c.hi, borderRadius: 8, padding: "6px 8px", display: "flex", flexDirection: "column", gap: 1 }}>
                                                <span style={{ fontSize: 9, fontWeight: 700, color: c.faint }}>{k.toUpperCase()}</span>
                                                <span style={{ fontSize: 12.5, fontWeight: 800, color: col, ...NUM }}>{md > 0 ? "+" : ""}{md.toFixed(0)}%</span>
                                                {typeof b.p25 === "number" && typeof b.p75 === "number" ? (
                                                    <span style={{ fontSize: 8.5, color: c.faint, ...NUM }}>{(b.p25 * 100).toFixed(0)}~{(b.p75 * 100) > 0 ? "+" : ""}{(b.p75 * 100).toFixed(0)}%</span>
                                                ) : null}
                                            </div>
                                        )
                                    })}
                                </div>
                            ) : null}
                            {mh?.analogs?.length ? (
                                <>
                                    <div style={{ fontSize: 10, fontWeight: 700, color: c.faint, marginBottom: 5 }}>유사 국면 (거리순)</div>
                                    {mh.analogs.slice(0, 4).map((a, i) => (
                                        <div key={i} style={{ display: "flex", alignItems: "baseline", gap: 8, padding: "4px 0", borderTop: i === 0 ? "none" : `1px solid ${c.line}` }}>
                                            <span style={{ fontSize: 11.5, fontWeight: 700, color: c.ink, flex: 1, minWidth: 0 }}>{a.name}</span>
                                            <span style={{ fontSize: 9.5, color: c.faint, ...NUM, flexShrink: 0 }}>
                                                CAPE {a.cape ?? "—"} · VIX {a.vix ?? "—"} · d={typeof a.distance === "number" ? a.distance.toFixed(2) : "—"}
                                            </span>
                                        </div>
                                    ))}
                                </>
                            ) : null}
                        </div>
                    </PanelBoundary>
                </div>

                {/* 이벤트 캘린더 */}
                <PanelBoundary name="이벤트">
                    <div style={{ ...cardStyle(c, MAIN_PAD) }}>
                        {secTitle("이벤트 캘린더", `지정학 · 정책 · ${events.length}건`, c.amber)}
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(330px, 1fr))", gap: 10 }}>
                            {events.map((e, i) => {
                                const high = String(e.severity || "").toLowerCase() === "high"
                                const dd = (e as { d_day?: string | number }).d_day
                                return (
                                    <div key={i} style={{ background: c.hi, borderRadius: 10, padding: "9px 11px", display: "flex", flexDirection: "column", gap: 4 }}>
                                        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                                            {dd !== undefined && dd !== null && String(dd) !== "" ? (
                                                <span style={{ fontSize: 9.5, fontWeight: 800, color: c.vt, background: c.vtS, borderRadius: 5, padding: "1px 6px", ...NUM }}>{String(dd)}</span>
                                            ) : null}
                                            {high ? <span style={{ fontSize: 9, fontWeight: 800, color: c.up, background: c.upS, borderRadius: 5, padding: "1px 5px" }}>중요</span> : null}
                                            <span style={{ fontSize: 12, fontWeight: 700, color: c.ink }}>{e.name}</span>
                                            <span style={{ fontSize: 9.5, color: c.faint, marginLeft: "auto" }}>{e.country || ""}</span>
                                        </div>
                                        {e.impact ? <div style={{ fontSize: 11, color: c.sub, lineHeight: 1.45 }}>{e.impact}</div> : null}
                                        {e.action ? <div style={{ fontSize: 10.5, color: c.vt, lineHeight: 1.4 }}>대응 — {e.action}</div> : null}
                                    </div>
                                )
                            })}
                        </div>
                    </div>
                </PanelBoundary>

                {/* 고래 13F */}
                <PanelBoundary name="고래">
                    <div style={{ ...cardStyle(c, "14px 16px") }}>
                        {secTitle("고래 포지션", "13F 분기 공시 사실 · 지연 데이터 · 복제수익률=참고", c.down)}
                        {whales.length === 0 ? (
                            <div style={{ fontSize: 12, color: c.sub }}>불러오는 중이거나 미발행.</div>
                        ) : (
                            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 10 }}>
                                {whales.slice(0, 8).map((w, i) => {
                                    const holds = (w.holdings_capped || w.holdings || []).slice().sort((a, b) => (b.weight_pct || 0) - (a.weight_pct || 0)).slice(0, 3)
                                    const rep = w.trailing_4q_replication_pct
                                    return (
                                        <div key={i} style={{ background: c.hi, borderRadius: 10, padding: "9px 11px", display: "flex", flexDirection: "column", gap: 5 }}>
                                            <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                                                <span style={{ fontSize: 12, fontWeight: 800, color: c.ink, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                                    {w.person || w.institution || "—"}
                                                </span>
                                                {typeof rep === "number" ? (
                                                    <span style={{ fontSize: 9.5, fontWeight: 700, color: rep > 0 ? c.up : c.down, ...NUM, flexShrink: 0 }}>
                                                        4Q 복제 {rep > 0 ? "+" : ""}{rep.toFixed(1)}%
                                                    </span>
                                                ) : null}
                                            </div>
                                            {holds.map((h, j) => (
                                                <div key={j} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                                    <StockLogo ticker={h.ticker} name={h.ticker} size={15} />
                                                    <span style={{ fontSize: 11, fontWeight: 700, color: c.ink, ...NUM }}>{h.ticker}</span>
                                                    <span style={{ fontSize: 10, color: c.sub, ...NUM }}>{typeof h.weight_pct === "number" ? h.weight_pct.toFixed(1) + "%" : ""}</span>
                                                    <ChangeTag c={c} t={h.change_type} />
                                                </div>
                                            ))}
                                            <span style={{ fontSize: 9, color: c.faint, ...NUM }}>기준 {w.report_date || "—"}</span>
                                        </div>
                                    )
                                })}
                            </div>
                        )}
                    </div>
                </PanelBoundary>

                {/* 헤드라인 2열 — 전체 아우름 (기본 12, 전체 토글) */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))", gap: 12, alignItems: "start" }}>
                    <PanelBoundary name="월가">
                        <HeadlineCard c={c} title="월가 · 글로벌" items={pf?.bloomberg_google_headlines || []} />
                    </PanelBoundary>
                    <PanelBoundary name="국내">
                        <HeadlineCard c={c} title="국내" items={pf?.headlines || []} />
                    </PanelBoundary>
                </div>

                <div style={{ fontSize: 10, color: c.faint }}>
                    사실·수집 데이터 + LLM 의견(의견) + 자기 산식(가설 N&lt;252) · 13F=분기 지연 공시 · 매수/매도 지시 아님
                </div>
            </div>
        </main>
    )
}

function SectorList({ c, title, rows, accent }: { c: Palette; title: string; rows: SectorRow[]; accent: string }) {
    return (
        <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 800, color: accent, marginBottom: 5 }}>{title}</div>
            {rows.map((s, i) => {
                const cp = s.change_pct || 0
                const col = cp > 0 ? c.up : cp < 0 ? c.down : c.faint
                const top = (s.top_stocks || [])[0]
                return (
                    <div key={i} style={{ display: "flex", alignItems: "baseline", gap: 8, padding: "5px 0", borderTop: i === 0 ? "none" : `1px solid ${c.line}` }}>
                        <span style={{ fontSize: 12, fontWeight: 700, color: c.ink, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {s.name} <span style={{ fontSize: 9.5, color: c.faint, fontWeight: 500 }}>{s.market || ""}</span>
                        </span>
                        {top && top.name ? (
                            <span style={{ fontSize: 10, color: c.sub, whiteSpace: "nowrap", ...NUM }}>
                                {top.name} {typeof top.change_pct === "number" ? `${top.change_pct > 0 ? "+" : ""}${top.change_pct.toFixed(1)}%` : ""}
                            </span>
                        ) : null}
                        <span style={{ fontSize: 12, fontWeight: 800, color: col, ...NUM, flexShrink: 0, minWidth: 56, textAlign: "right" }}>
                            {cp > 0 ? "+" : ""}{cp.toFixed(2)}%
                        </span>
                    </div>
                )
            })}
        </div>
    )
}

function RotRow({ c, name, cp, reason, col }: { c: Palette; name?: string; cp?: number; reason?: string; col: string }) {
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 1, padding: "5px 0", borderTop: `1px solid ${c.line}` }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
                <span style={{ fontSize: 12, fontWeight: 700, color: c.ink }}>{name || "—"}</span>
                {typeof cp === "number" ? (
                    <span style={{ fontSize: 10.5, fontWeight: 700, color: col, ...NUM }}>{cp > 0 ? "+" : ""}{cp.toFixed(1)}%</span>
                ) : null}
            </div>
            {reason ? <span style={{ fontSize: 10.5, color: c.faint, lineHeight: 1.4 }}>{reason}</span> : null}
        </div>
    )
}

function ChangeTag({ c, t }: { c: Palette; t?: string }) {
    const v = String(t || "").toUpperCase()
    if (!v) return null
    const label = v === "NEW" ? "신규" : v === "INCREASED" ? "확대" : v === "REDUCED" || v === "DECREASED" ? "축소" : v === "SOLD_OUT" || v === "EXITED" ? "청산" : ""
    if (!label) return null
    const col = label === "신규" || label === "확대" ? c.up : c.down
    const bg = label === "신규" || label === "확대" ? c.upS : c.downS
    return <span style={{ fontSize: 9, fontWeight: 800, color: col, background: bg, borderRadius: 5, padding: "1px 5px" }}>{label}</span>
}

function HeadlineCard({ c, title, items }: { c: Palette; title: string; items: Array<{ title?: string; link?: string }> }) {
    const [all, setAll] = useState(false)
    const clean = items.filter((h) => h && h.title)
    const shown = all ? clean : clean.slice(0, 12)
    return (
        <div style={{ ...cardStyle(c, "14px 16px") }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 13.5, fontWeight: 800, color: c.ink, letterSpacing: "-0.02em" }}>{title}</span>
                <span style={{ fontSize: 10, color: c.faint }}>{clean.length}건</span>
                {clean.length > 12 ? (
                    <button onClick={() => setAll((v) => !v)} style={{ marginLeft: "auto", border: "none", background: c.hi, color: c.sub, borderRadius: 999, padding: "3px 10px", fontSize: 10, fontWeight: 700, cursor: "pointer", fontFamily: FONT }}>
                        {all ? "접기" : "전체"}
                    </button>
                ) : null}
            </div>
            {shown.map((h, i) => (
                <a
                    key={i}
                    href={h.link || "#"}
                    target="_blank"
                    rel="noreferrer"
                    style={{ display: "block", fontSize: 12, color: c.sub, textDecoration: "none", lineHeight: 1.45, padding: "5px 0", borderTop: i === 0 ? "none" : `1px solid ${c.line}`, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                >
                    {h.title}
                </a>
            ))}
        </div>
    )
}

