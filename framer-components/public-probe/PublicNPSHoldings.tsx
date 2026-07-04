import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useState } from "react"

/**
 * 국민연금(NPS) 보유종목 + 운용현황 — 공개 probe.
 *
 * "국민연금이 어디에 투자하나 / 수익은 얼마나" 를 공시 사실로 한 화면에.
 * 🚨 점수·추천 없음. 지분율·수익률 = 공시 사실, 판단은 사용자 (RULE 7).
 *
 * 데이터 = data/nps_holdings.json (DART 5% 대량보유 공시 + data.go.kr 국민연금 대량보유).
 *   한계 = 5% 이상 보유 기준(전체 ~1,200종목 아님) · 분기 지연. 컴포넌트가 라벨로 명시.
 *
 * 다크모드 = body[data-framer-theme] 자가감지. 회사명 누르면 리포트(reportPath?q=ticker).
 */

const BLOB = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", up: "#f04452", down: "#3182f6", blue: "#3182f6", blueSoft: "#eef4ff",
    green: "#15c47e", greenSoft: "#eafaf3", accent: "#6c5ce7",
}
const DARK = {
    // 배경/카드/잉크 = 공시 피드·사이트 PageBg/NavBg 와 통일 (2026-06-22)
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", up: "#ff6b76", down: "#5a9cff", blue: "#5a9cff", blueSoft: "#1b2740",
    green: "#3ddc97", greenSoft: "#16322a", accent: "#a99bff",
}

function readBodyDark(): boolean {
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}

function fmtPct(v: any): string {
    const n = Number(v)
    if (!isFinite(n)) return "—"
    return n.toFixed(2) + "%"
}

const DEMO = {
    coverage: "operating_pool", count: 3, source: "DART 5% 대량보유 공시",
    note: "국민연금 5% 이상 대량보유 공시 기준 — 전체 보유종목 아님 · 분기 지연.",
    fund: { as_of: "2026-03-31", aum_krw_trillion: 1526.1, return_total_pct: 18.82, return_total_note: "2025년 전체(잠정)", return_cumulative_annualized_pct: 8.04, asset_returns_pct: { "국내주식": 8.24, "해외주식": 19.74, "국내채권": 0.84, "해외채권": 3.77, "대체투자": 8.03 }, source: "국민연금기금운용본부 운용현황 공시" },
    holdings: [
        { ticker: "017960", name: "한국카본", pct: 10.49, qty_change: 521052, date: "2026-04-01", src: "DART majorstock" },
        { ticker: "375500", name: "DL이앤씨", pct: 8.06, qty_change: -120000, date: "2026-03-20", src: "DART majorstock" },
        { ticker: "000270", name: "기아", pct: 6.61, qty_change: 0, date: "2026-02-14", src: "DART majorstock" },
    ],
}

export default function PublicNPSHoldings(props: { width?: number; dark?: boolean; dataUrl?: string; reportPath?: string }) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT

    const [data, setData] = useState<any>(onCanvas ? DEMO : null)
    const [loading, setLoading] = useState<boolean>(!onCanvas)
    const [query, setQuery] = useState<string>("")
    const [npsAll, setNpsAll] = useState<boolean>(false)   // 보유종목 더보기 토글

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas) return
        let alive = true
        const url = props.dataUrl || BLOB + "/nps_holdings.json"
        fetch(url, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (alive) { setData(d); setLoading(false) } })
            .catch(() => { if (alive) setLoading(false) })
        return () => { alive = false }
    }, [onCanvas, props.dataUrl])

    const holdings = useMemo(() => (data && Array.isArray(data.holdings) ? data.holdings : []), [data])
    // 검색 필터 — 종목명·코드
    const shownHoldings = useMemo(() => {
        const q = query.trim().toLowerCase()
        if (!q) return holdings
        return holdings.filter((h: any) =>
            String(h.name || "").toLowerCase().includes(q) ||
            String(h.ticker || "").toLowerCase().includes(q)
        )
    }, [holdings, query])
    // 더보기 — 검색 중이 아니고 미리보기 초과 시 접힘(너무 많은 종목 정리)
    const NPS_PREVIEW = 12
    const npsCollapsed = !npsAll && !query.trim() && shownHoldings.length > NPS_PREVIEW
    const displayHoldings = npsCollapsed ? shownHoldings.slice(0, NPS_PREVIEW) : shownHoldings
    const fund = data && data.fund ? data.fund : null
    const reportPath = props.reportPath || "/stock"

    const wrap: any = { width: "100%", background: C.bg, fontFamily: "Pretendard, -apple-system, sans-serif", padding: 16, boxSizing: "border-box", color: C.ink }

    if (loading) {
        const skBase = isDark ? "#222a33" : "#e9edf1"
        const skHi = isDark ? "#2d3742" : "#f3f5f7"
        const sk = (w: any, h: number, r = 8, mt = 0) => ({ width: w, height: h, borderRadius: r, marginTop: mt, background: skBase, backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`, backgroundSize: "800px 100%", animation: "vsrShimmer 1.4s ease-in-out infinite" })
        const skCard: any = { background: C.card, borderRadius: 16, padding: "14px 16px", marginTop: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }
        return (
            <div style={wrap}>
                <style>{`@keyframes vsrShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={sk(120, 18, 6)} />
                <div style={{ ...skCard, display: "flex", gap: 18, flexWrap: "wrap" }}>
                    {[0, 1, 2].map((i) => (<div key={i}><div style={sk(70, 11, 4)} /><div style={sk(90, 22, 6, 6)} /></div>))}
                </div>
                <div style={skCard}>
                    <div style={sk(150, 14, 6)} />
                    {[0, 1, 2, 3, 4].map((i) => (
                        <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                            <div style={{ flex: 1 }}><div style={sk(130, 14, 5)} /></div>
                            <div style={sk(56, 15, 5)} />
                        </div>
                    ))}
                </div>
            </div>
        )
    }
    if (!data) return <div style={{ ...wrap, textAlign: "center", color: C.faint, fontSize: 14, padding: 40 }}>데이터를 불러오지 못했어요.</div>

    return (
        <div style={wrap}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 12, flexWrap: "wrap" }}>
                <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.4px" }}>국민연금 투자</span>
                <span style={{ fontSize: 11.5, fontWeight: 600, color: C.faint }}>공시 사실</span>
            </div>

            {/* 운용현황 카드 */}
            {fund && (
                <div style={{ background: C.card, borderRadius: 16, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)", marginBottom: 12 }}>
                    <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
                        {fund.aum_krw_trillion != null && (
                            <div>
                                <div style={{ fontSize: 11, fontWeight: 700, color: C.faint }}>운용 규모(AUM)</div>
                                <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: "-0.5px" }}>{Number(fund.aum_krw_trillion).toLocaleString()}<span style={{ fontSize: 13, fontWeight: 700 }}>조원</span></div>
                            </div>
                        )}
                        {fund.return_total_pct != null && (
                            <div>
                                <div style={{ fontSize: 11, fontWeight: 700, color: C.faint }}>{fund.return_total_note || "수익률"}</div>
                                <div style={{ fontSize: 20, fontWeight: 800, color: Number(fund.return_total_pct) >= 0 ? C.up : C.down, letterSpacing: "-0.5px" }}>{Number(fund.return_total_pct) >= 0 ? "+" : ""}{fmtPct(fund.return_total_pct)}</div>
                            </div>
                        )}
                        {fund.return_cumulative_annualized_pct != null && (
                            <div>
                                <div style={{ fontSize: 11, fontWeight: 700, color: C.faint }}>누적 연환산</div>
                                <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: "-0.5px" }}>{fmtPct(fund.return_cumulative_annualized_pct)}</div>
                            </div>
                        )}
                    </div>
                    {fund.asset_returns_pct && (
                        <div style={{ display: "flex", gap: 7, flexWrap: "wrap", marginTop: 11 }}>
                            {Object.keys(fund.asset_returns_pct).map((k) => {
                                const v = fund.asset_returns_pct[k]
                                return (
                                    <span key={k} style={{ fontSize: 11, fontWeight: 700, color: C.sub, background: C.bg, borderRadius: 8, padding: "5px 9px" }}>
                                        {k} <b style={{ color: Number(v) >= 0 ? C.up : C.down }}>{Number(v) >= 0 ? "+" : ""}{fmtPct(v)}</b>
                                    </span>
                                )
                            })}
                        </div>
                    )}
                    <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 9, lineHeight: 1.5 }}>
                        {fund.as_of ? fund.as_of + " 기준 · " : ""}{fund.source || "국민연금 공시"}
                    </div>
                </div>
            )}

            {/* 보유종목 */}
            <div style={{ background: C.card, borderRadius: 16, padding: "8px 16px 12px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", padding: "8px 0 4px" }}>
                    <span style={{ fontSize: 13, fontWeight: 800 }}>보유종목 (5%+ 공시)</span>
                    <span style={{ fontSize: 11, fontWeight: 700, color: C.accent }}>
                        {query.trim() ? `${shownHoldings.length} / ${holdings.length}` : holdings.length}종목
                    </span>
                </div>
                {/* 검색 — 종목명·코드 */}
                <div style={{ position: "relative", margin: "2px 0 8px" }}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={C.faint} strokeWidth="2.4" strokeLinecap="round"
                        style={{ position: "absolute", left: 13, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}>
                        <circle cx="11" cy="11" r="7" />
                        <line x1="21" y1="21" x2="16.65" y2="16.65" />
                    </svg>
                    <input
                        type="text"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="종목명·코드 검색"
                        style={{
                            width: "100%", boxSizing: "border-box", border: "none",
                            background: C.bg, color: C.ink, borderRadius: 12,
                            padding: "11px 32px 11px 36px", fontSize: 13, fontFamily: "Pretendard, -apple-system, sans-serif", outline: "none",
                            WebkitAppearance: "none",
                        }}
                    />
                    {query && (
                        <span role="button" tabIndex={0} onClick={() => setQuery("")}
                            style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", color: C.faint, fontSize: 14, fontWeight: 700, cursor: "pointer", lineHeight: 1 }}>×</span>
                    )}
                </div>
                {shownHoldings.length === 0 ? (
                    <div style={{ padding: "20px 0", textAlign: "center", color: C.faint, fontSize: 13, fontWeight: 600 }}>
                        {query.trim() ? `"${query.trim()}" 검색 결과 없음` : "공시된 5%+ 보유종목 없음"}
                    </div>
                ) : (
                    displayHoldings.map((h: any, i: number) => {
                        const url = h.ticker ? reportPath + "?q=" + encodeURIComponent(h.ticker) : ""
                        const chg = h.qty_change
                        const chgCol = chg == null ? C.faint : Number(chg) > 0 ? C.up : Number(chg) < 0 ? C.down : C.faint
                        return (
                            <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    {url && !onCanvas ? (
                                        <a href={url} target="_blank" rel="noopener noreferrer" title={h.name + " 분석"} style={{ fontSize: 14, fontWeight: 700, color: C.blue, textDecoration: "none" }}>{h.name} ↗</a>
                                    ) : (
                                        <span style={{ fontSize: 14, fontWeight: 700, color: C.ink }}>{h.name}</span>
                                    )}
                                    <span style={{ fontSize: 11, fontWeight: 600, color: C.faint, marginLeft: 6 }}>{h.ticker}</span>
                                    {h.date && <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 1 }}>{h.date} · {h.src || "DART"}</div>}
                                </div>
                                {chg != null && Number(chg) !== 0 && (
                                    <span style={{ flexShrink: 0, fontSize: 11, fontWeight: 700, color: chgCol }}>{Number(chg) > 0 ? "▲" : "▼"}{Math.abs(Number(chg)).toLocaleString()}</span>
                                )}
                                <span style={{ flexShrink: 0, fontSize: 15, fontWeight: 800, color: C.ink, fontVariantNumeric: "tabular-nums", minWidth: 56, textAlign: "right" }}>{fmtPct(h.pct)}</span>
                            </div>
                        )
                    })
                )}
                {!query.trim() && shownHoldings.length > NPS_PREVIEW && (
                    <div role="button" tabIndex={0} onClick={() => setNpsAll((v) => !v)}
                        style={{ marginTop: 4, padding: "11px 0 5px", textAlign: "center", cursor: "pointer", fontSize: 12.5, fontWeight: 800, color: C.accent, borderTop: `1px solid ${C.line}` }}>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                            {npsAll ? "접기" : `더보기 (${shownHoldings.length - NPS_PREVIEW}개 더)`}
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={C.accent} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" style={{ transform: npsAll ? "rotate(180deg)" : "none", transition: "transform 150ms ease" }}>
                                <path d="M6 9l6 6 6-6" />
                            </svg>
                        </span>
                    </div>
                )}
            </div>

            {/* 한계 라벨 (RULE 7) */}
            <div style={{ marginTop: 12, padding: "11px 13px", background: C.card, borderRadius: 12, border: `1px solid ${C.line}` }}>
                <div style={{ fontSize: 11.5, fontWeight: 700, color: C.sub, lineHeight: 1.55 }}>
                    ⓘ {data.note || "국민연금 5% 이상 대량보유 공시 기준 — 전체 보유종목 아님 · 분기 지연."}
                </div>
                {data.coverage === "operating_pool" && (
                    <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 5, lineHeight: 1.5 }}>
                        현재 = 운영풀 종목 한정. 전체 5%+ 공시(약 111종목)는 data.go.kr 연동 시 확대.
                    </div>
                )}
            </div>

            <div style={{ textAlign: "center", fontSize: 10.5, color: C.faint, marginTop: 10, fontWeight: 600 }}>
                {data.source || "DART·data.go.kr"} · 공시 사실(지분율) · 판단은 직접
            </div>
        </div>
    )
}

addPropertyControls(PublicNPSHoldings, {
    width: { type: ControlType.Number, title: "Width", defaultValue: 420, min: 320, max: 760 },
    dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
    dataUrl: { type: ControlType.String, title: "데이터 URL", defaultValue: BLOB + "/nps_holdings.json" },
    reportPath: { type: ControlType.String, title: "리포트 경로", defaultValue: "/stock" },
})
