import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * ETF 자금흐름 렌즈 — VERITY 공개 터미널 (AlphaNest). 국민연금(PublicNPSHoldings)처럼 독립 "렌즈".
 * 디자인 = 토스식 미니멀: 무채색 위주 + 방향값만 유입(빨강)/유출(파랑), 얇은 구분선, 색배경·외곽선·이모지 없음.
 *
 * 🚨 차별 각도: 토스/네이버 ETF 화면(보수율·수익률)과 달리 "패시브 자금이 어느 테마로".
 *   진짜 흐름 = Δ상장좌수(설정/환매) = 가격효과 제거. 1일 Δ는 노이즈 → 누적 순흐름(최근 N일)이 주신호.
 *   괴리율 = (시장가 − NAV) / NAV — ETF 프리미엄/디스카운트(수요 쏠림 보조 단서).
 * 🚨 RULE 7: 상장좌수·NAV·순자산·흐름 = KRX OpenAPI 1차 사실(etf_flow.py 누적). 점수·추천 0. 첫 신호 = 거래일 ≥2.
 * 데이터 = data/etf_flow.json (단일 writer, publish-data 발행). history(≤40거래일)에서 누적 산출. 테마 = body[data-framer-theme] 자가 추종.
 */

interface Props {
    reportPath: string
    dataUrl: string
    dark: boolean
}
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/etf_flow.json"
const WINDOW = 20 // 누적 흐름 산출 최대 거래일 창

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#f0f1f3", up: "#f04452", down: "#3182f6",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#222730", up: "#f04452", down: "#5b9bff",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

const CAT: Record<string, string> = {
    equity_domestic: "국내주식", equity_foreign: "해외주식", thematic: "테마",
    bond_kr: "한국채권", bond_us: "미국채권", commodity_gold: "금", commodity: "원자재",
    leverage: "레버리지", inverse: "인버스", sector_financial: "금융", sector_tech: "IT",
    sector: "섹터", dividend: "배당",
}

function fmtKRW(won: any, signed = false): string {
    const n = Number(won)
    if (!isFinite(n) || n === 0) return signed ? "0" : "—"
    const a = Math.abs(n)
    const sign = signed ? (n > 0 ? "+" : "−") : ""
    if (a >= 1e12) return sign + (a / 1e12).toFixed(2) + "조"
    if (a >= 1e8) return sign + Math.round(a / 1e8).toLocaleString("en-US") + "억"
    return sign + Math.round(a / 1e4).toLocaleString("en-US") + "만"
}
function fmtAge(iso: any): string {
    if (!iso) return ""
    try {
        const mins = Math.max(0, Math.round((Date.now() - new Date(String(iso)).getTime()) / 60000))
        if (mins < 60) return mins + "분 전"
        const hrs = Math.round(mins / 60)
        if (hrs < 24) return hrs + "시간 전"
        return Math.round(hrs / 24) + "일 전"
    } catch {
        return ""
    }
}

// 누적 순흐름 — history 창에서 Δ상장좌수 × 최근 NAV (가격효과 제거). 거래일 ≥2 필요.
function cumFlow(series: any[]): { flow: number; days: number; pct: number | null } | null {
    if (!Array.isArray(series) || series.length < 2) return null
    const win = series.slice(-WINDOW)
    const a = win[0], b = win[win.length - 1]
    const as = Number(a.list_shrs), bs = Number(b.list_shrs), nav = Number(b.nav)
    if (!isFinite(as) || !isFinite(bs) || !isFinite(nav)) return null
    const d = bs - as
    return { flow: d * nav, days: win.length, pct: as ? (d / as) * 100 : null }
}
// 괴리율 — (시장가 − NAV) / NAV.
function premium(close: any, nav: any): number | null {
    const c = Number(close), n = Number(nav)
    if (!isFinite(c) || !isFinite(n) || n <= 0) return null
    return ((c - n) / n) * 100
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
// 🎨 페이지 이동 다크 번쩍임 제거(2026-07-20): 첫 마운트만 라이트(SSG/첫방문 매칭·stuck 방지) → 이후 마운트는 실제 테마 즉시.
let __anHyd = false
function anReadDark(): boolean {
    if (typeof document === "undefined") return false
    if (!__anHyd) {
        __anHyd = true
        return false
    }
    const h = document.documentElement ? document.documentElement.dataset.anTheme : null
    if (h === "dark") return true
    if (h === "light") return false
    return !!(document.body && document.body.dataset.framerTheme === "dark")
}


// 마운트/토글 재판독 SoT — verity_theme(localStorage) 우선 → html[data-an-theme] → body[data-framer-theme].
// 791d29f7e 8개 fix 에서 누락됐던 body-only 재판독 버그 정정(다크에서 라이트 고정 방지, 2026-07-21 일괄).
function readBodyDark(): boolean {
    if (typeof document === "undefined") return false
    try {
        const pref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (pref === "dark") return true
        if (pref === "light") return false
        const h = document.documentElement ? document.documentElement.dataset.anTheme : null
        if (h === "dark") return true
        if (h === "light") return false
        if (document.body) {
            const a = document.body.dataset.framerTheme
            if (a === "dark") return true
            if (a === "light") return false
        }
        if (typeof window !== "undefined" && window.matchMedia) {
            return window.matchMedia("(prefers-color-scheme: dark)").matches
        }
    } catch (e) {}
    return false
}

export default function PublicETFFlow(props: Props) {
    const { dataUrl, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!dark : anReadDark()))
    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    const isDark = onCanvas ? !!dark : themeDark
    const C = isDark ? DARK : LIGHT

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [data, setData] = useState<any>(null)
    const [showAll, setShowAll] = useState(false)

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    useEffect(() => {
        if (!dataUrl) return
        let alive = true
        fetch(dataUrl, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (alive && d && Array.isArray(d.etfs)) setData(d) })
            .catch(() => {})
        return () => { alive = false }
    }, [dataUrl])

    const narrow = w > 0 && w < 560
    const loading = !data

    // ETF별 누적 흐름·괴리율 부착 + 누적 흐름 절댓값 정렬
    const rows = useMemo(() => {
        if (!data) return [] as any[]
        const hist = data.history || {}
        return (data.etfs || [])
            .map((e: any) => ({ e, cum: cumFlow(hist[e.ticker]), prem: premium(e.close, e.nav) }))
            .sort((a: any, b: any) => Math.abs((b.cum && b.cum.flow) || 0) - Math.abs((a.cum && a.cum.flow) || 0))
    }, [data])

    // 테마별 누적 순흐름 집계
    const cats = useMemo(() => {
        const m: Record<string, number> = {}
        for (const r of rows) {
            if (r.cum && r.cum.flow !== 0) m[r.e.category] = (m[r.e.category] || 0) + r.cum.flow
        }
        return Object.entries(m).map(([k, v]) => ({ cat: k, flow: v })).sort((a, b) => Math.abs(b.flow) - Math.abs(a.flow))
    }, [rows])

    const skBase = isDark ? "#1e242c" : "#edeff2"
    const skHi = isDark ? "#2a313b" : "#f5f6f8"
    const sk = (bw: any, bh: number, br = 7): CSSProperties => ({
        width: bw, height: bh, borderRadius: br, background: skBase,
        backgroundImage: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`,
        backgroundSize: "800px 100%", animation: "vefShimmer 1.4s ease-in-out infinite", flexShrink: 0,
    })

    const wrap: CSSProperties = {
        width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT,
        padding: narrow ? 16 : 22, boxSizing: "border-box", color: C.ink,
    }
    const card: CSSProperties = {
        background: C.card, borderRadius: 18, padding: narrow ? 16 : 20, boxSizing: "border-box",
    }

    if (loading) {
        return (
            <div ref={rootRef} style={wrap}>
                <style>{`@keyframes vefShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={{ ...sk(110, 12, 6), marginBottom: 12 }} />
                <div style={{ ...sk("64%", 24, 8), marginBottom: 22 }} />
                <div style={{ ...sk("100%", 64, 18), marginBottom: 12 }} />
                <div style={sk("100%", 240, 18)} />
            </div>
        )
    }

    const total = rows.length
    const hasFlow = rows.some((r: any) => r.cum && r.cum.flow !== 0)
    const maxCat = cats.length ? Math.max(...cats.map((c) => Math.abs(c.flow))) : 0
    const dirColor = (f: number) => (f > 0 ? C.up : C.down)
    const COLLAPSED = 8

    return (
        <div ref={rootRef} style={wrap}>
            {/* 헤더 */}
            <div style={{ fontSize: 12, fontWeight: 600, color: C.faint }}>ETF 자금흐름</div>
            <div style={{ fontSize: narrow ? 20 : 23, fontWeight: 700, color: C.ink, letterSpacing: "-0.5px", marginTop: 6 }}>패시브 자금이 어디로</div>
            <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 500, marginTop: 7 }}>
                누적 설정·환매(상장좌수 변화) · 가격효과 제거 · KRX{data.updated_at ? ` · ${fmtAge(data.updated_at)}` : ""}
            </div>

            {/* 집계 중 (거래일 1일차) */}
            {!hasFlow && (
                <div style={{ ...card, marginTop: 18 }}>
                    <div style={{ fontSize: 14.5, fontWeight: 700, color: C.ink }}>자금흐름 집계 중이에요</div>
                    <div style={{ fontSize: 12.5, color: C.sub, fontWeight: 500, marginTop: 6, lineHeight: 1.55 }}>
                        흐름은 매일 상장좌수 변화로 누적 계산해요. 거래일 둘째 날부터 순유입·유출이 표시돼요. 지금은 {total}개 ETF의 기준 스냅샷을 담았어요.
                    </div>
                </div>
            )}

            {/* 테마별 누적 순흐름 (흐름 있을 때) */}
            {hasFlow && cats.length > 0 && (
                <div style={{ ...card, marginTop: 18 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 700, color: C.ink, marginBottom: 14 }}>테마별 누적 순흐름</div>
                    {cats.slice(0, 8).map((c) => {
                        const pos = c.flow > 0
                        const col = dirColor(c.flow)
                        const pct = maxCat ? Math.max(5, (Math.abs(c.flow) / maxCat) * 100) : 0
                        return (
                            <div key={c.cat} style={{ display: "flex", alignItems: "center", gap: 12, padding: "7px 0" }}>
                                <div style={{ width: narrow ? 58 : 72, flexShrink: 0, fontSize: 12.5, fontWeight: 500, color: C.sub, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{CAT[c.cat] || c.cat}</div>
                                {/* 연회색 트랙(레인) + 컬러 막대 — 행 구분·기준선 확보. 양수=좌측/음수=우측 정렬 유지 */}
                                <div style={{ flex: 1, minWidth: 0, position: "relative", height: 8, borderRadius: 4, background: C.bg }}>
                                    <div style={{ position: "absolute", top: 0, ...(pos ? { left: 0 } : { right: 0 }), width: `${pct}%`, height: 8, borderRadius: 4, background: col, opacity: 0.9 }} />
                                </div>
                                <div style={{ width: narrow ? 70 : 86, flexShrink: 0, textAlign: "right", fontSize: 12.5, fontWeight: 600, color: col, fontVariantNumeric: "tabular-nums" }}>{fmtKRW(c.flow, true)}</div>
                            </div>
                        )
                    })}
                </div>
            )}

            {/* ETF 리스트 — 누적 흐름 순 상위 8개 + 더보기 */}
            <div style={{ ...card, marginTop: 12, paddingTop: 6, paddingBottom: showAll || total <= COLLAPSED ? 6 : 0 }}>
                {(showAll ? rows : rows.slice(0, COLLAPSED)).map((r: any, idx: number) => {
                    const e = r.e, cum = r.cum, prem = r.prem
                    const has = cum && cum.flow !== 0
                    const col = has ? dirColor(cum.flow) : C.faint
                    const premStr = prem != null && Math.abs(prem) >= 0.15 ? ` · 괴리 ${prem > 0 ? "+" : ""}${prem.toFixed(2)}%` : ""
                    return (
                        <div key={e.ticker} role="link" tabIndex={0}
                            onClick={() => { if (typeof window !== "undefined") window.location.href = `${(props.reportPath || "/stock").replace(/\/$/, "")}?q=${e.ticker}` }}
                            onKeyDown={(ev) => { if (ev.key === "Enter" && typeof window !== "undefined") window.location.href = `${(props.reportPath || "/stock").replace(/\/$/, "")}?q=${e.ticker}` }}
                            style={{ display: "flex", alignItems: "center", gap: 12, padding: "13px 0", borderTop: idx === 0 ? "none" : `1px solid ${C.line}`, cursor: "pointer" }}>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 14, fontWeight: 600, color: C.ink, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{e.name}</div>
                                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 500, marginTop: 2 }}>{CAT[e.category] || e.category} · 순자산 {fmtKRW(e.netasset)}원{premStr}</div>
                            </div>
                            <div style={{ flexShrink: 0, textAlign: "right" }}>
                                {has ? (
                                    <>
                                        <div style={{ fontSize: 14.5, fontWeight: 600, color: col, fontVariantNumeric: "tabular-nums" }}>{fmtKRW(cum.flow, true)}원</div>
                                        <div style={{ fontSize: 11, fontWeight: 500, color: col, marginTop: 2 }}>{cum.flow > 0 ? "유입" : "유출"} · {cum.days}일{cum.pct != null ? ` ${cum.pct > 0 ? "+" : ""}${cum.pct.toFixed(2)}%` : ""}</div>
                                    </>
                                ) : (
                                    <span style={{ fontSize: 12, fontWeight: 500, color: C.faint }}>집계 중</span>
                                )}
                            </div>
                        </div>
                    )
                })}
                {total > COLLAPSED && (
                    <button onClick={() => setShowAll((s) => !s)}
                        style={{ width: "100%", border: "none", cursor: "pointer", fontFamily: FONT, background: "transparent", padding: "13px 0", borderTop: `1px solid ${C.line}`, fontSize: 13, fontWeight: 600, color: C.sub }}>
                        {showAll ? "접기" : `더보기 (${total - COLLAPSED}개)`}
                    </button>
                )}
            </div>

            {/* 면책 */}
            <div style={{ fontSize: 11, color: C.faint, fontWeight: 500, marginTop: 18, lineHeight: 1.6 }}>
                상장좌수·NAV·순자산·괴리율은 KRX OpenAPI 사실이에요. 흐름은 상장좌수 변화 × NAV(설정/환매)를 최근 {WINDOW}거래일까지 누적한 값으로, 가격효과를 뺀 값이에요. 거래일 둘째 날부터 신호가 잡혀요. 자체 점수는 검증 후(2027) 공개해요.
            </div>
        </div>
    )
}

addPropertyControls(PublicETFFlow, {
    reportPath: { type: ControlType.String, title: "Report Path", defaultValue: "/stock" },
    dataUrl: { type: ControlType.String, title: "ETF Flow URL", defaultValue: DEFAULT_URL },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})
