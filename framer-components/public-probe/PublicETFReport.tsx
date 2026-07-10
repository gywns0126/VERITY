import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react"

/**
 * ETF 리포트 — VERITY 공개 터미널 (AlphaNest). PublicETFFlow(자금흐름 렌즈) 행 클릭 착지 페이지 (/etf?q=069500).
 *
 * 데이터 = etf_flow.json (KRX OpenAPI 1차 사실, 추적 유니버스 ~25종 + history ≤40거래일).
 *   흐름 = Δ상장좌수 × NAV (설정/환매 — 가격효과 제거). 괴리율 = (종가−NAV)/NAV.
 * 🚨 RULE 7 — 관측 사실만(점수·추천 0). 추적 밖 ETF = "관측 대상 아님" 안내(가짜 데이터 생성 금지).
 * 종목 연동 = ?q= + verity-ticker-change(발행). 다크 = body[data-framer-theme] 자가 추종.
 * 차트 = 자체 SVG 유선형(Catmull-Rom /4.5 — 사이트 공통 곡선 강도). 시세 재배포 아님(상장좌수·NAV = 공시성 사실).
 */

interface Props {
    dataUrl: string
    flowPath: string
    dark: boolean
}

const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/etf_flow.json"
const LIGHT = { bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#f0f1f3", grid: "#eef1f4", up: "#f04452", upS: "#fff0f1", down: "#3182f6", downS: "#eef4ff", vt: "#6c5ce7" }
const DARK = { bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#222730", grid: "#1e242c", up: "#f04452", upS: "#2a1a1d", down: "#5b9bff", downS: "#152031", vt: "#a99bff" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const CAT: Record<string, string> = {
    equity_domestic: "국내주식", equity_foreign: "해외주식", thematic: "테마", bond_kr: "한국채권",
    bond_us: "미국채권", commodity_gold: "금", commodity: "원자재", leverage: "레버리지",
    inverse: "인버스", sector_financial: "금융", sector_tech: "IT", sector: "섹터", dividend: "배당",
}

function fmtKRW(won: any, signed = false): string {
    const n = Number(won)
    if (!isFinite(n) || n === 0) return signed ? "0원" : "—"
    const a = Math.abs(n)
    const sign = signed ? (n > 0 ? "+" : "−") : ""
    if (a >= 1e12) return sign + (a / 1e12).toFixed(2) + "조원"
    if (a >= 1e8) return sign + Math.round(a / 1e8).toLocaleString() + "억원"
    return sign + Math.round(a / 1e4).toLocaleString() + "만원"
}
function fmtNum(v: any): string {
    const n = Number(v)
    return isFinite(n) ? n.toLocaleString() : "—"
}
function dstr(d: string): string {
    const s = String(d || "")
    return s.length === 8 ? `${s.slice(4, 6)}.${s.slice(6)}` : s
}

/* Catmull-Rom 유선형 path (사이트 공통 /4.5 강도) */
function smoothLine(pts: { x: number; y: number }[]): string {
    if (pts.length < 2) return ""
    let p = `M ${pts[0].x} ${pts[0].y}`
    for (let i = 0; i < pts.length - 1; i++) {
        const p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(pts.length - 1, i + 2)]
        const c1x = p1.x + (p2.x - p0.x) / 4.5, c1y = p1.y + (p2.y - p0.y) / 4.5
        const c2x = p2.x - (p3.x - p1.x) / 4.5, c2y = p2.y - (p3.y - p1.y) / 4.5
        p += ` C ${c1x} ${c1y}, ${c2x} ${c2y}, ${p2.x} ${p2.y}`
    }
    return p
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicETFReport(props: Props) {
    const { dataUrl, flowPath, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!dark)
    useEffect(() => {
        if (onCanvas) return
        const read = () => { const t = (typeof document !== "undefined" && document.body) ? document.body.dataset.framerTheme : ""; setThemeDark(t === "dark") }
        read()
        if (typeof MutationObserver === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])
    const isDark = onCanvas ? !!dark : themeDark
    const C = isDark ? DARK : LIGHT

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((es) => { for (const e of es) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    const [doc, setDoc] = useState<any>(null)
    const [tk, setTk] = useState<string>(() => {
        if (typeof window !== "undefined") {
            try { return (new URLSearchParams(window.location.search).get("q") || "").trim() } catch (e) {}
        }
        return ""
    })
    useEffect(() => {
        if (onCanvas) return
        const reread = () => { try { setTk((new URLSearchParams(window.location.search).get("q") || "").trim()) } catch (e) {} }
        window.addEventListener("popstate", reread)
        window.addEventListener("verity-ticker-change", reread)
        return () => { window.removeEventListener("popstate", reread); window.removeEventListener("verity-ticker-change", reread) }
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas) return
        let alive = true
        fetch(dataUrl || DEFAULT_URL, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (alive && d) setDoc(d) })
            .catch(() => {})
        return () => { alive = false }
    }, [dataUrl, onCanvas])

    const etf = useMemo(() => {
        const arr = (doc && doc.etfs) || []
        if (!arr.length) return null
        return arr.find((e: any) => String(e.ticker) === String(tk)) || arr[0]
    }, [doc, tk])
    const hist = useMemo(() => (doc && doc.history && etf && doc.history[etf.ticker]) || [], [doc, etf])

    /* 일별 흐름(Δ좌수×NAV) + 누적 시계열 */
    const series = useMemo(() => {
        const out: { date: string; flow: number; cum: number; prem: number | null }[] = []
        let cum = 0
        for (let i = 1; i < hist.length; i++) {
            const prev = hist[i - 1], cur = hist[i]
            const dSh = Number(cur.list_shrs) - Number(prev.list_shrs)
            const flow = isFinite(dSh) && isFinite(Number(cur.nav)) ? dSh * Number(cur.nav) : 0
            cum += flow
            const prem = (isFinite(Number(cur.close)) && isFinite(Number(cur.nav)) && Number(cur.nav) !== 0)
                ? ((Number(cur.close) - Number(cur.nav)) / Number(cur.nav)) * 100 : null
            out.push({ date: String(cur.date), flow, cum, prem })
        }
        return out
    }, [hist])

    const narrow = w > 0 && w < 560
    const pad = narrow ? 14 : 18
    const root: CSSProperties = { width: "100%", fontFamily: FONT, color: C.ink, padding: `0 ${pad}px`, boxSizing: "border-box" }
    const card: CSSProperties = { background: C.card, borderRadius: 16, padding: "16px 18px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }

    if (!onCanvas && (!doc || !etf)) {
        return <div ref={rootRef} style={root}><div style={{ ...card, color: C.faint, fontSize: 13, fontWeight: 600 }}>ETF 데이터 로딩 중…</div></div>
    }
    const e = etf || { ticker: "069500", name: "KODEX 200", category: "equity_domestic", close: 130125, nav: 130165.59, netasset: 2.766e13, list_shrs: 209850000, est_flow: 2.86e11, days_n: 7 }
    const tracked = !!(doc && doc.etfs && doc.etfs.some((x: any) => String(x.ticker) === String(tk))) || !tk

    const last = series.length ? series[series.length - 1] : null
    const cumFlow = last ? last.cum : Number(e.est_flow) || 0
    const flowColor = cumFlow > 0 ? C.up : cumFlow < 0 ? C.down : C.faint
    const prem = (isFinite(Number(e.close)) && isFinite(Number(e.nav)) && Number(e.nav) !== 0) ? ((Number(e.close) - Number(e.nav)) / Number(e.nav)) * 100 : null

    /* 누적 흐름 차트 */
    const CW = Math.max(280, Math.min(760, w - pad * 2 - 36)), CH = 120, PX = 6, PY = 12
    const pts = series.map((s, i) => {
        const vals = series.map((x) => x.cum)
        const mn = Math.min(0, ...vals), mx = Math.max(0, ...vals)
        const rng = mx - mn || 1
        return { x: PX + (i / Math.max(1, series.length - 1)) * (CW - PX * 2), y: PY + (1 - (s.cum - mn) / rng) * (CH - PY * 2) }
    })
    const zeroY = (() => {
        const vals = series.map((x) => x.cum)
        const mn = Math.min(0, ...vals), mx = Math.max(0, ...vals)
        const rng = mx - mn || 1
        return PY + (1 - (0 - mn) / rng) * (CH - PY * 2)
    })()

    const kv = (k: string, v: string, color?: string) => (
        <div style={{ flex: 1, minWidth: 96 }}>
            <div style={{ fontSize: 11, color: C.faint, fontWeight: 700 }}>{k}</div>
            <div style={{ fontSize: 15, fontWeight: 800, color: color || C.ink, marginTop: 2, letterSpacing: "-0.3px" }}>{v}</div>
        </div>
    )

    return (
        <div ref={rootRef} style={root}>
            {/* 헤더 */}
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
                <span style={{ fontSize: narrow ? 20 : 24, fontWeight: 800, letterSpacing: "-0.5px" }}>{e.name}</span>
                <span style={{ fontSize: 12.5, color: C.faint, fontWeight: 700 }}>{e.ticker}</span>
                <span style={{ fontSize: 11, fontWeight: 800, color: C.vt, background: isDark ? "#241f3a" : "#f0edff", borderRadius: 7, padding: "3px 9px" }}>{CAT[e.category] || e.category || "ETF"}</span>
                {flowPath !== "" && (
                    <a href={flowPath || "/market"} style={{ marginLeft: "auto", fontSize: 12, fontWeight: 700, color: C.faint, textDecoration: "none" }}>← 자금흐름 전체</a>
                )}
            </div>

            {!tracked && tk ? (
                <div style={{ ...card, marginBottom: 12 }}>
                    <div style={{ fontSize: 14, fontWeight: 800 }}>이 ETF({tk})는 아직 흐름 관측 대상이 아니에요</div>
                    <div style={{ fontSize: 12.5, color: C.sub, fontWeight: 600, marginTop: 6, lineHeight: 1.6 }}>
                        자금흐름 렌즈는 순자산 상위 ETF부터 순차 확대 중이에요. 아래는 현재 관측 중인 ETF 중 하나입니다.
                    </div>
                </div>
            ) : null}

            {/* 누적 순유입 헤드라인 + 차트 */}
            <div style={{ ...card, marginBottom: 12 }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 22, fontWeight: 800, color: flowColor, letterSpacing: "-0.6px" }}>{fmtKRW(cumFlow, true)}</span>
                    <span style={{ fontSize: 12.5, fontWeight: 700 }}>누적 순설정 (최근 {series.length || Number(e.days_n) || 0}거래일)</span>
                </div>
                {pts.length >= 2 && (
                    <svg width="100%" viewBox={`0 0 ${CW} ${CH}`} style={{ display: "block", marginTop: 10 }}>
                        <line x1={PX} x2={CW - PX} y1={zeroY} y2={zeroY} stroke={C.grid} strokeWidth={1} />
                        <path d={smoothLine(pts)} fill="none" stroke={flowColor} strokeWidth={2.2} strokeLinecap="round" />
                        <circle cx={pts[pts.length - 1].x} cy={pts[pts.length - 1].y} r={3.4} fill={flowColor} />
                    </svg>
                )}
                {series.length >= 2 && (
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 2 }}>
                        <span>{dstr(series[0].date)}</span><span>{dstr(series[series.length - 1].date)}</span>
                    </div>
                )}
                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 10, lineHeight: 1.5 }}>
                    순설정 = Δ상장좌수 × NAV (설정−환매, 가격효과 제거) · KRX 공시 사실 · 점수·추천 아님
                </div>
            </div>

            {/* 스탯 그리드 */}
            <div style={{ ...card, marginBottom: 12 }}>
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                    {kv("종가", fmtNum(e.close) + "원")}
                    {kv("NAV", fmtNum(Math.round(Number(e.nav))) + "원")}
                    {kv("괴리율", prem == null ? "—" : (prem >= 0 ? "+" : "") + prem.toFixed(2) + "%", prem == null ? undefined : prem >= 0 ? C.up : C.down)}
                </div>
                <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 12 }}>
                    {kv("순자산", fmtKRW(e.netasset))}
                    {kv("상장좌수", fmtNum(e.list_shrs) + "좌")}
                    {kv("오늘 순설정", fmtKRW(e.est_flow, true), Number(e.est_flow) > 0 ? C.up : Number(e.est_flow) < 0 ? C.down : undefined)}
                </div>
                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 12, lineHeight: 1.5 }}>
                    괴리율 = (종가 − NAV) ÷ NAV — 프리미엄(+)/디스카운트(−) · 기준일 {dstr(String((doc && doc.bas_dd) || ""))}
                </div>
            </div>

            {/* 일별 흐름 목록 */}
            {series.length > 0 && (
                <div style={{ ...card }}>
                    <div style={{ fontSize: 13.5, fontWeight: 800, marginBottom: 4 }}>일별 순설정</div>
                    {series.slice(-10).reverse().map((s, i) => (
                        <div key={s.date} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                            <span style={{ minWidth: 48, fontSize: 12.5, color: C.sub, fontWeight: 700 }}>{dstr(s.date)}</span>
                            <span style={{ flex: 1, fontSize: 13, fontWeight: 800, color: s.flow > 0 ? C.up : s.flow < 0 ? C.down : C.faint }}>{fmtKRW(s.flow, true)}</span>
                            {s.prem != null && <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>괴리 {(s.prem >= 0 ? "+" : "") + s.prem.toFixed(2)}%</span>}
                        </div>
                    ))}
                </div>
            )}

            <div style={{ textAlign: "center", fontSize: 11, color: C.faint, fontWeight: 600, margin: "14px 0 4px", lineHeight: 1.5 }}>
                KRX OpenAPI 공시 사실 · 자금흐름 = 설정/환매 관측 · AlphaNest 의견·추천 아님
            </div>
        </div>
    )
}

addPropertyControls(PublicETFReport, {
    dataUrl: { type: ControlType.String, title: "Data URL", defaultValue: DEFAULT_URL },
    flowPath: { type: ControlType.String, title: "Flow Path", defaultValue: "/market" },
    dark: { type: ControlType.Boolean, title: "Dark (canvas)", defaultValue: false },
})
