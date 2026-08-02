"use client"
// StockReport — 종목 심층 리포트 (오퍼레이터 authed, 본인전용). 공개 알파네스트 디자인.
// 되돌리지 말 것: fetchOperator("portfolio_full") 재사용(110키 풀 페이로드). 공개 blob 직독 금지.
//   🚨 RULE 7: brain=가설(N<252) 라벨 · backtest win_rate 는 표본수+평균수익 병기(단독 금지) ·
//     analyst_consensus/target_price = 발행 금지(PM 7/10, 라이선스) → 리포트에서도 제외.
//   🚨 외곽선 금지 — 카드 채움색만. 상승 빨강/하락 파랑. 숫자 tabular-nums(모노 금지).
import { useEffect, useState } from "react"
import { useDark, palette, cardStyle, FONT, NUM, type Palette } from "@/lib/theme"
import { fetchOperator } from "@/lib/api"

type Rec = Record<string, any>

function initialTicker(): string {
    try {
        const u = new URL(window.location.href)
        const q = u.searchParams.get("q")
        if (q) return q.toUpperCase()
        const last = localStorage.getItem("verity_last_ticker")
        if (last) return last.toUpperCase()
    } catch {}
    return ""
}

const n = (v: any): number | null => (typeof v === "number" && isFinite(v) ? v : null)
const won = (v: number) => (Math.abs(v) >= 1e12 ? (v / 1e12).toFixed(1) + "조" : Math.abs(v) >= 1e8 ? Math.round(v / 1e8).toLocaleString() + "억" : Math.round(v / 1e4).toLocaleString() + "만")

function recLabel(r?: string) {
    const s = String(r || "").toUpperCase()
    return s === "STRONG_BUY" ? "적극매수" : s === "BUY" ? "매수" : s === "AVOID" ? "회피" : s === "CAUTION" ? "주의" : "관망"
}

export default function StockReport() {
    const dark = useDark()
    const c = palette(dark)
    const [recs, setRecs] = useState<Rec[]>([])
    const [status, setStatus] = useState<"loading" | "ok" | "auth" | "error">("loading")
    const [ticker, setTicker] = useState("")

    useEffect(() => {
        setTicker(initialTicker())
        function onTicker(e: Event) {
            const t = (e as CustomEvent).detail?.ticker
            if (t) setTicker(String(t).toUpperCase())
        }
        window.addEventListener("verity-ticker", onTicker)
        return () => window.removeEventListener("verity-ticker", onTicker)
    }, [])

    useEffect(() => {
        let cancelled = false
        fetchOperator<{ recommendations?: Rec[] }>("portfolio_full").then((r) => {
            if (cancelled) return
            if (!r.ok) return setStatus(r.error === "auth" ? "auth" : "error")
            setRecs(r.data.recommendations || [])
            setStatus("ok")
        })
        return () => {
            cancelled = true
        }
    }, [])

    const title = (
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
            <span style={{ fontSize: 15, fontWeight: 800, color: c.ink, letterSpacing: "-0.02em" }}>종목 리포트</span>
            <span style={{ fontSize: 11, color: c.faint }}>본인전용 · Brain=가설 N&lt;252</span>
        </div>
    )
    const wrap = { fontFamily: FONT, display: "flex", flexDirection: "column" as const, gap: 12 }

    if (status === "auth" || status === "error")
        return (
            <div style={wrap}>
                {title}
                <div style={{ ...cardStyle(c), fontSize: 13, color: status === "auth" ? c.sub : c.down }}>
                    {status === "auth" ? "오퍼레이터 로그인이 필요합니다 (VERITY = 비공개)." : "리포트를 불러오지 못했습니다."}
                </div>
            </div>
        )

    const r = recs.find((x) => String(x.ticker).toUpperCase() === ticker)
    if (!r)
        return (
            <div style={wrap}>
                {title}
                <div style={{ ...cardStyle(c), fontSize: 13, color: c.sub, lineHeight: 1.55 }}>
                    {ticker ? `${ticker} 는 추천 유니버스(리포트 대상)에 없습니다.` : "종목을 검색해 선택하면 심층 리포트가 표시됩니다."}
                </div>
            </div>
        )

    const isUS = r.currency === "USD"
    const price = n(r.current_price) ?? n(r.price)
    const fin = r.kis_financial_ratio || {}
    const flow = r.flow || {}
    const lynch = r.lynch_kr || {}
    const bt = r.backtest || {}
    const dde = r.dart_disclosure_events || {}
    const brain = n(r.brain_score_pre_macro) ?? n(r.brain_score)
    const accent = String(r.recommendation).toUpperCase().includes("BUY") ? c.up : String(r.recommendation).toUpperCase().includes("AVOID") ? c.down : c.faint
    const fmtPrice = (v: number) => (isUS ? "$" + v.toFixed(2) : Math.round(v).toLocaleString())
    const netCol = (v: number | null) => (v == null ? c.faint : v > 0 ? c.up : v < 0 ? c.down : c.faint)

    return (
        <div style={wrap}>
            {title}

            {/* 헤더 */}
            <div style={{ ...cardStyle(c), display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 8, minWidth: 0 }}>
                        <span style={{ fontSize: 18, fontWeight: 800, color: c.ink, letterSpacing: "-0.02em" }}>{r.name || r.ticker}</span>
                        <span style={{ fontSize: 12, color: c.faint, ...NUM }}>{r.ticker}</span>
                    </div>
                    <span style={{ fontSize: 12, fontWeight: 800, color: "#fff", background: accent, borderRadius: 8, padding: "3px 10px" }}>{recLabel(r.recommendation)}</span>
                </div>
                {r.company_tagline || r.industry ? <div style={{ fontSize: 12, color: c.sub }}>{r.company_tagline || r.industry}</div> : null}
                <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                    {price != null ? <span style={{ fontSize: 20, fontWeight: 800, color: c.ink, ...NUM }}>{fmtPrice(price)}</span> : null}
                    {brain != null ? (
                        <span style={{ fontSize: 12, color: c.sub }}>
                            브레인 <b style={{ color: c.ink, ...NUM }}>{Math.round(brain)}</b> <span style={{ color: c.faint, fontSize: 10 }}>(가설)</span>
                        </span>
                    ) : null}
                    {n(r.market_cap) != null ? <span style={{ fontSize: 12, color: c.sub }}>시총 <b style={{ color: c.ink, ...NUM }}>{won(n(r.market_cap)!)}</b></span> : null}
                </div>
            </div>

            {/* 밸류에이션 */}
            <Card c={c} label="밸류에이션">
                <Metrics c={c} items={[
                    ["PER", n(r.per), (v) => v.toFixed(1)],
                    ["PBR", n(r.pbr), (v) => v.toFixed(1)],
                    ["ROE", n(fin.roe), (v) => v.toFixed(1) + "%"],
                    ["배당", n(r.div_yield), (v) => v.toFixed(2) + "%"],
                    ["고점대비", n(r.drop_from_high_pct), (v) => v.toFixed(1) + "%", true],
                    ["52W", null, null],
                ]} />
                {n(r.high_52w) != null && n(r.low_52w) != null ? (
                    <div style={{ fontSize: 11.5, color: c.faint, ...NUM }}>52주 {fmtPrice(n(r.low_52w)!)} ~ {fmtPrice(n(r.high_52w)!)}</div>
                ) : null}
            </Card>

            {/* 재무 건전성 */}
            <Card c={c} label="재무 건전성">
                <Metrics c={c} items={[
                    ["부채비율", n(fin.debt_ratio) ?? n(r.debt_ratio), (v) => v.toFixed(0) + "%"],
                    ["유동비율", n(fin.current_ratio) ?? n(r.current_ratio), (v) => v.toFixed(1)],
                    ["영업이익률", n(r.operating_margin), (v) => v.toFixed(1) + "%"],
                    ["잉여현금", n(r.free_cashflow), (v) => won(v)],
                    ["순이익", n(r.net_income), (v) => won(v)],
                ]} />
            </Card>

            {/* 수급 (외인·기관) */}
            {flow && (n(flow.foreign_net) != null || n(flow.institution_net) != null) ? (
                <Card c={c} label="수급 (순매매)">
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 14 }}>
                        {n(flow.foreign_net) != null ? <span style={{ fontSize: 12.5, color: c.sub }}>외국인 <b style={{ color: netCol(n(flow.foreign_net)), ...NUM }}>{won(n(flow.foreign_net)!)}</b></span> : null}
                        {n(flow.institution_net) != null ? <span style={{ fontSize: 12.5, color: c.sub }}>기관 <b style={{ color: netCol(n(flow.institution_net)), ...NUM }}>{won(n(flow.institution_net)!)}</b></span> : null}
                        {n(r.held_pct_institutions) != null ? <span style={{ fontSize: 12.5, color: c.sub }}>기관보유 <b style={{ color: c.ink, ...NUM }}>{n(r.held_pct_institutions)!.toFixed(1)}%</b></span> : null}
                    </div>
                </Card>
            ) : null}

            {/* Lynch */}
            {lynch && lynch.label ? (
                <Card c={c} label={`Lynch — ${lynch.label}`}>
                    {lynch.summary ? <div style={{ fontSize: 12.5, color: c.ink, lineHeight: 1.5 }}>{lynch.summary}</div> : null}
                </Card>
            ) : null}

            {/* DART 리스크 */}
            {dde && (dde.severity || dde.summary) ? (
                <Card c={c} label="DART 공시 리스크">
                    <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                        {dde.severity ? <span style={{ fontSize: 11, fontWeight: 700, color: dde.severity >= 3 ? c.up : c.amber, background: dde.severity >= 3 ? c.upS : c.amberS, borderRadius: 8, padding: "3px 9px" }}>심각도 {dde.severity}</span> : null}
                        {dde.summary ? <span style={{ fontSize: 12, color: c.sub, lineHeight: 1.5 }}>{dde.summary}</span> : null}
                    </div>
                    {Array.isArray(r.detected_risk_keywords) && r.detected_risk_keywords.length ? (
                        <div style={{ fontSize: 11.5, color: c.faint, marginTop: 4 }}>키워드: {r.detected_risk_keywords.slice(0, 8).join(" · ")}</div>
                    ) : null}
                </Card>
            ) : null}

            {/* backtest — 🚨 RULE 7: 승률+기대값+표본+CI 모두 병기(단독 금지) */}
            {n(bt.total_trades) != null && n(bt.total_trades)! > 0 ? (() => {
                const N = n(bt.total_trades)!
                const wr = n(bt.win_rate)
                const p = wr == null ? null : wr <= 1 ? wr : wr / 100
                const ciPp = p != null ? 1.96 * Math.sqrt(Math.max(p * (1 - p), 0) / N) * 100 : null // 95% 이항 CI(%p)
                return (
                    <Card c={c} label="백테스트 (가설)">
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 14 }}>
                            <span style={{ fontSize: 12.5, color: c.sub }}>표본 <b style={{ color: c.ink, ...NUM }}>N={N}</b></span>
                            {p != null ? (
                                <span style={{ fontSize: 12.5, color: c.sub }}>
                                    승률 <b style={{ color: c.ink, ...NUM }}>{(p * 100).toFixed(0)}%</b>
                                    {ciPp != null ? <span style={{ color: c.faint, ...NUM }}> ±{ciPp.toFixed(0)}%p</span> : null}
                                </span>
                            ) : null}
                            {n(bt.avg_return) != null ? <span style={{ fontSize: 12.5, color: c.sub }}>평균수익 <b style={{ color: netCol(n(bt.avg_return)), ...NUM }}>{n(bt.avg_return)!.toFixed(1)}%</b></span> : null}
                        </div>
                        <div style={{ fontSize: 11, color: c.amber, marginTop: 2 }}>
                            {N < 30 ? "⚠ N<30 = 통계 무의미. " : N < 100 ? "예비 결과 · N<100 = 95% CI 광범위. " : ""}승률+기대값+표본+CI 병기(RULE 7). 2027 게이트 전 예측력 주장 아님.
                        </div>
                    </Card>
                )
            })() : null}

            {/* 판단 (ai_verdict) */}
            {r.ai_verdict || r.gold_insight ? (
                <Card c={c} label="판단 (가설)">
                    <div style={{ fontSize: 12.5, color: c.ink, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{r.ai_verdict || r.gold_insight}</div>
                </Card>
            ) : null}

            <div style={{ fontSize: 10.5, color: c.faint, lineHeight: 1.5 }}>자기 산식·자기 trail(가설) · 컨센서스 목표가 = 라이선스상 미표기 · 매수/매도 지시 아님</div>
        </div>
    )
}

function Card({ c, label, children }: { c: Palette; label: string; children: React.ReactNode }) {
    return (
        <div style={{ ...cardStyle(c), display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: c.ink }}>{label}</div>
            {children}
        </div>
    )
}

function Metrics({ c, items }: { c: Palette; items: Array<[string, number | null, ((v: number) => string) | null, boolean?]> }) {
    return (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 14 }}>
            {items.map(([k, v, fmt, signed], i) =>
                v != null && fmt ? (
                    <span key={i} style={{ fontSize: 12.5, color: c.sub }}>
                        {k} <b style={{ color: signed ? (v > 0 ? c.up : v < 0 ? c.down : c.ink) : c.ink, ...NUM }}>{fmt(v)}</b>
                    </span>
                ) : null
            )}
        </div>
    )
}
