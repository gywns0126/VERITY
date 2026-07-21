import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * 종목 뉴스 (정보 밀도형) — VERITY 공개 터미널 (골든구스).
 *
 * 데이터 = /api/stock_news?code=종목코드 (네이버 금융 종목뉴스 라이브, 건당 밀도 enrichment).
 * 밀도: 카테고리 칩 · 출처 신뢰티어(✓) · 매체 클러스터 수 · 상대시각 · 관련 공시(뉴스×DART 연결, 우리 차별점).
 * RULE 6: LLM 해설 0. RULE 7: 호재악재·랭킹 0(사실만).
 * 종목 = prop ticker → URL ?q → verity_last_ticker. in-page 전환 추종 1s 폴링. 테마 = body[data-framer-theme] 추종.
 * 데이터 없으면 graceful 숨김.
 * 🚨 외곽 padding·narrow 브레이크포인트 = PublicStockReport 와 동일(w<560, 12/18) — /stock 좌측 열 카드 인셋 정렬(2026-07-04).
 */

interface Props {
    ticker: string
    apiBase: string
    dark: boolean
}
const DEFAULT_API = "https://project-yw131.vercel.app"

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#f0f1f3",
    vt: "#6c5ce7", vtS: "#f0edff", green: "#15c47e", chip: "#f2f4f6",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#222730",
    vt: "#a99bff", vtS: "#241f3a", green: "#34e08a", chip: "#222933",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

interface RelDisc { title: string; url: string; date: string }
interface NewsItem {
    title: string; url: string; source: string; category: string
    credibility: number; credible: boolean; outlets: number; datetime: string; rel_time: string
    related_disclosure?: RelDisc | null
}

function readTickerFromUrl(): string {
    if (typeof window === "undefined") return ""
    try {
        const q = (new URLSearchParams(window.location.search).get("q") || "").trim()
        if (q) return q.toUpperCase()
        return (window.localStorage.getItem("verity_last_ticker") || "").trim().toUpperCase()
    } catch { return "" }
}

const SAMPLE: NewsItem[] = [
    { title: "삼성전자, 2분기 영업이익 10조 돌파…반도체 회복", url: "#", source: "한국경제", category: "실적", credibility: 5, credible: true, outlets: 8, datetime: "", rel_time: "2시간 전" },
    { title: "삼성전자, 자기주식 3조원 취득 결정", url: "#", source: "연합뉴스", category: "공시", credibility: 5, credible: true, outlets: 5, datetime: "", rel_time: "5시간 전", related_disclosure: { title: "주요사항보고서(자기주식취득결정)", url: "#", date: "2026-06-25" } },
    { title: "삼성전자, HBM4 양산 계획 발표", url: "#", source: "전자신문", category: "신사업·투자", credibility: 3, credible: false, outlets: 2, datetime: "", rel_time: "1일 전" },
]

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

export default function PublicStockNews(props: Props) {
    const { ticker, apiBase, dark } = props
    const api = (apiBase || DEFAULT_API).replace(/\/+$/, "")
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
    const [tk, setTk] = useState<string>(() => String(ticker || "").trim().toUpperCase())
    const [items, setItems] = useState<NewsItem[]>(onCanvas ? SAMPLE : [])
    const [loading, setLoading] = useState(false)

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    /* 종목 = prop 우선, 없으면 URL ?q. in-page 전환 추종 1s 폴링. */
    useEffect(() => {
        if (onCanvas) return
        const propTk = String(ticker || "").trim().toUpperCase()
        if (propTk) { setTk(propTk); return }
        const sync = () => { const u = readTickerFromUrl(); if (u) setTk((cur) => (cur === u ? cur : u)) }
        sync()
        window.addEventListener("popstate", sync)
        const iv = setInterval(sync, 1000)
        return () => { window.removeEventListener("popstate", sync); clearInterval(iv) }
    }, [ticker, onCanvas])

    /* 뉴스 로드 — 종목코드 변경 시 (KR 6자리만) */
    useEffect(() => {
        if (onCanvas) return
        const code = String(tk).trim()
        if (!/^\d{6}$/.test(code)) { setItems([]); return }  // KR 종목코드만 (US는 별도)
        let alive = true
        setLoading(true)
        fetch(`${api}/api/stock_news?code=${encodeURIComponent(code)}`, { cache: "no-store" })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (alive) setItems(d && Array.isArray(d.items) ? d.items : []) })
            .catch(() => { if (alive) setItems([]) })
            .finally(() => { if (alive) setLoading(false) })
        return () => { alive = false }
    }, [tk, api, onCanvas])

    const narrow = w > 0 && w < 560   // PublicStockReport 와 동일 브레이크포인트 (좌측 인셋 정렬)
    const catColor = (cat: string) =>
        cat === "실적" || cat === "공시" ? C.vt
            : cat === "계약·수주" || cat === "M&A·지분" ? C.green
                : C.faint

    const wrap: CSSProperties = { width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT, padding: narrow ? "0 12px" : "0 18px", boxSizing: "border-box", color: C.ink }   // 외곽 pad = PublicStockReport 동일(12/18)

    // 로딩 중 빈 화면 방지: 아무것도 없고 로딩도 끝났으면 숨김
    if (!items.length && !loading) return <div ref={rootRef} style={{ width: "100%", height: 0, overflow: "hidden" }} />

    return (
        <div ref={rootRef} style={wrap}>
            <div style={{ background: C.card, borderRadius: 16, padding: narrow ? 14 : 18, boxSizing: "border-box", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 7, marginBottom: 12, flexWrap: "wrap" }}>
                    <span style={{ fontSize: narrow ? 15 : 16, fontWeight: 800, letterSpacing: "-0.3px" }}>종목 뉴스</span>
                    {items.length > 0 && <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{items.length}건</span>}
                </div>

                {loading && !items.length ? (
                    <div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600, padding: "16px 0", textAlign: "center" }}>불러오는 중…</div>
                ) : (
                    <div style={{ display: "flex", flexDirection: "column" }}>
                        {items.map((n, i) => (
                            <div key={i} style={{ padding: "11px 0", borderTop: i === 0 ? "none" : "1px solid " + C.line }}>
                                <a href={n.url || "#"} target="_blank" rel="noopener" style={{ display: "block", textDecoration: "none", color: "inherit" }}>
                                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4, flexWrap: "wrap" }}>
                                        <span style={{ fontSize: 10.5, fontWeight: 800, color: catColor(n.category), background: C.chip, padding: "2px 7px", borderRadius: 6, whiteSpace: "nowrap" }}>{n.category}</span>
                                        {n.outlets > 1 && <span style={{ fontSize: 10.5, fontWeight: 700, color: C.vt, background: C.vtS, padding: "2px 7px", borderRadius: 6, whiteSpace: "nowrap" }}>{n.outlets}개 매체</span>}
                                    </div>
                                    <div style={{ fontSize: narrow ? 13 : 13.5, fontWeight: 600, color: C.ink, lineHeight: 1.45, wordBreak: "break-word" }}>{n.title}</div>
                                    <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 4, display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap" }}>
                                        <span style={{ fontWeight: 700, color: n.credible ? C.sub : C.faint }}>{n.source}{n.credible ? " ✓" : ""}</span>
                                        {n.rel_time && <span>· {n.rel_time}</span>}
                                    </div>
                                </a>
                                {n.related_disclosure ? (
                                    <a href={n.related_disclosure.url} target="_blank" rel="noopener" title={n.related_disclosure.title}
                                        style={{ display: "inline-flex", alignItems: "center", gap: 4, marginTop: 6, maxWidth: "100%", fontSize: 10.5, fontWeight: 800, color: C.vt, background: C.vtS, padding: "3px 8px", borderRadius: 7, textDecoration: "none", boxSizing: "border-box" }}>
                                        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>관련 공시 · {n.related_disclosure.title}</span>
                                        <span style={{ flexShrink: 0 }}>›</span>
                                    </a>
                                ) : null}
                            </div>
                        ))}
                    </div>
                )}

                <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 500, marginTop: 13, lineHeight: 1.55 }}>
                    네이버 금융 종목 뉴스 · 매체·시각·출처는 사실, ✓=신뢰 출처 · 관련 공시는 ±2일 DART 매칭
                </div>
            </div>
        </div>
    )
}

addPropertyControls(PublicStockNews, {
    ticker: { type: ControlType.String, title: "Ticker(빈값=URL ?q)", defaultValue: "" },
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})
