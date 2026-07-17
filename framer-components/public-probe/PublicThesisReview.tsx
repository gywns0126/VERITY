import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useState, useEffect } from "react"

/**
 * 내 관점 복기 — AlphaNest 루프 결정 단계. 기록한 thesis 모음 + 기록 후 가격(종가) 변화.
 * dual: 로그인(verity_supabase_session) → /api/thesis · 익명 → localStorage verity_thesis_v1 (ThesisNote와 동일 키).
 * 🚨 시세 재배포 컴플라이언스(2026-07-03 Phase 1.5): /api/stock 실시간가 병렬 조회 제거(KIS 재배포 불가).
 *   가격 = stock_flow_5d.json 마지막 close(종가·발행 유지 판정) 1회 fetch · 종목명 = universe_search.json. 커버리지 밖 = graceful "—".
 * 행 클릭 → StockReport ?q=. 자가 다크감지.
 *
 * 🚨 RULE 7 = 사용자 자기 저널 복기 — VERITY 채점·정답·점수 0. "스스로 복기" 용도. RULE 6 = LLM 0.
 */

const LIGHT = { bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#e5e8eb", up: "#f04452", down: "#3182f6", upS: "#fdecee", downS: "#eaf1fe", vt: "#6c5ce7", chipBg: "#f2f4f6" }
const DARK = { bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#252b34", up: "#f04452", down: "#5b9bff", upS: "#2a1a1d", downS: "#17263c", vt: "#a99bff", chipBg: "#0f1318" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEFAULT_API = "https://project-yw131.vercel.app"
const STORE_KEY = "verity_thesis_v1"
const SESSION_KEY = "verity_supabase_session"
const STANCES: Record<string, { label: string; key: "up" | "down" | "faint" }> = {
    bull: { label: "강세", key: "up" }, watch: { label: "관망", key: "faint" }, bear: { label: "약세", key: "down" },
}

function readBodyDark(): boolean {
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}
function loadToken(): string {
    if (typeof window === "undefined") return ""
    try { const raw = localStorage.getItem(SESSION_KEY); if (!raw) return ""; const s = JSON.parse(raw); return typeof s.access_token === "string" ? s.access_token : "" } catch { return "" }
}
function loadLocal(): any[] {
    if (typeof window === "undefined") return []
    try {
        const o = JSON.parse(window.localStorage.getItem(STORE_KEY) || "{}") || {}
        return Object.keys(o).map((tk) => ({ ticker: tk, stance: o[tk].stance, note: o[tk].note, date: o[tk].date, entryPrice: o[tk].entryPrice }))
    } catch { return [] }
}
function todayKST(): string {
    const d = new Date(); const k = new Date(d.getTime() + (d.getTimezoneOffset() + 540) * 60000)
    return k.toISOString().slice(0, 10)
}
function daysSince(dateStr: string): number {
    try { const a = new Date(dateStr + "T00:00:00+09:00").getTime(); const b = new Date(todayKST() + "T00:00:00+09:00").getTime(); return Math.max(0, Math.round((b - a) / 86400000)) } catch { return 0 }
}
function won(v: any): string { const x = Number(v); if (!isFinite(x) || x === 0) return "—"; return Math.round(x).toLocaleString("en-US") + "원" }

const DEMO = [
    { ticker: "375500", name: "DL이앤씨", stance: "bull", note: "PER·PBR 업종 이하 + 내부자 순매수.", date: "2026-06-14", entryPrice: 71200, curPrice: 73900 },
    { ticker: "035420", name: "NAVER", stance: "watch", note: "실적발표 후 재검토.", date: "2026-06-20", entryPrice: 198000, curPrice: 191500 },
]

export default function PublicThesisReview(props: { width?: number; dark?: boolean; apiBase?: string; stockPath?: string }) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!props.dark : (typeof document !== "undefined" && !!document.body && document.body.dataset.framerTheme === "dark")))
    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT
    const base = (props.apiBase || DEFAULT_API).replace(/\/+$/, "")
    const stockPath = props.stockPath || "/stock"

    const [items, setItems] = useState<any[]>(onCanvas ? DEMO : [])
    const [loading, setLoading] = useState<boolean>(!onCanvas)

    useEffect(() => {
        if (onCanvas) return
        setThemeDark(readBodyDark())
        const obs = new MutationObserver(() => setThemeDark(readBodyDark()))
        if (document.body) obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    useEffect(() => {
        if (onCanvas) return
        let alive = true
        const token = loadToken()
        const build = (base_list: any[]) => {
            if (!alive) return
            if (!base_list.length) { setItems([]); setLoading(false); return }
            // 종가(flow_5d)·종목명(universe) 1회 fetch — 실시간가 조회 아님(컴플라이언스)
            Promise.all([
                fetch("https://rte5guenhonw9fzn.public.blob.vercel-storage.com/stock_flow_5d.json", { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).catch(() => null),
                fetch("https://rte5guenhonw9fzn.public.blob.vercel-storage.com/universe_search.json", { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).catch(() => null),
            ]).then(([fd, ud]) => {
                if (!alive) return
                const fm = (fd && (fd.flows || fd)) || {}
                const names: Record<string, string> = {}
                const uarr = ud && (Array.isArray(ud) ? ud : ud.stocks)
                if (Array.isArray(uarr)) for (const s of uarr) { if (s && s.ticker) names[String(s.ticker)] = String(s.name || "") }
                const rows = base_list.map((it) => {
                    const arr = fm[String(it.ticker)]
                    const last = Array.isArray(arr) && arr.length ? arr[arr.length - 1] : null
                    const c = last && Number(last.close)
                    return { ...it, curPrice: c && isFinite(c) ? c : null, name: it.name || names[String(it.ticker)] || it.ticker }
                })
                rows.sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")))
                setItems(rows); setLoading(false)
            })
        }
        if (token) {
            fetch(base + "/api/thesis", { headers: { Authorization: "Bearer " + token }, cache: "no-store" })
                .then((r) => (r.ok ? r.json() : null))
                .then((rows) => build(Array.isArray(rows) ? rows.map((r: any) => ({ ticker: r.ticker, stance: r.stance, note: r.note, date: (r.created_at || "").slice(0, 10), entryPrice: r.entry_price != null ? Number(r.entry_price) : null })) : []))
                .catch(() => build(loadLocal()))
        } else {
            build(loadLocal())
        }
        return () => { alive = false }
    }, [onCanvas, base])

    const wrap: any = { width: props.width || 380, fontFamily: FONT, background: C.bg, color: C.ink, padding: 14, boxSizing: "border-box" }
    const st = (id: string) => STANCES[id] || STANCES.watch
    const go = (tk: string) => { if (!onCanvas) try { window.location.href = stockPath + "?q=" + encodeURIComponent(tk) } catch (e) {} }

    return (
        <div style={wrap}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 7, marginBottom: 12 }}>
                <span style={{ fontSize: 15, fontWeight: 800, color: C.ink }}>내 관점 복기</span>
                <span style={{ fontSize: 11, fontWeight: 600, color: C.faint }}>· 기록 후 변화 (스스로 복기)</span>
            </div>

            {loading && <div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600, padding: "16px 0" }}>불러오는 중…</div>}
            {!loading && items.length === 0 && (
                <div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600, padding: "20px 4px", lineHeight: 1.6 }}>
                    아직 기록한 관점이 없어요. 종목 페이지에서 "내 관점"을 기록하면 여기 모여 기록 후 변화를 한눈에 복기할 수 있어요.
                </div>
            )}

            {!loading && items.map((it: any, i: number) => {
                const s = st(it.stance)
                const col = (C as any)[s.key]
                const diff = (it.entryPrice != null && it.curPrice != null && it.entryPrice > 0) ? ((it.curPrice - it.entryPrice) / it.entryPrice) * 100 : null
                const dCol = diff == null ? C.faint : diff > 0 ? C.up : diff < 0 ? C.down : C.faint
                return (
                    <div key={it.ticker + i} onClick={() => go(it.ticker)} style={{ background: C.card, borderRadius: 14, padding: 13, marginBottom: 9, boxShadow: "0 1px 3px rgba(0,0,0,0.04)", cursor: "pointer" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span style={{ fontSize: 11.5, fontWeight: 800, color: "#fff", background: col, borderRadius: 999, padding: "3px 10px" }}>{s.label}</span>
                            <span style={{ flex: 1, fontSize: 14, fontWeight: 800, color: C.ink, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.name || it.ticker}</span>
                            {diff != null && isFinite(diff) && <span style={{ fontSize: 13.5, fontWeight: 800, color: dCol }}>{(diff > 0 ? "+" : "") + diff.toFixed(1)}%</span>}
                        </div>
                        {it.note && <div style={{ fontSize: 12.5, color: C.sub, fontWeight: 500, lineHeight: 1.5, marginTop: 7, whiteSpace: "pre-wrap" }}>{it.note}</div>}
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginTop: 8, fontSize: 11, color: C.faint, fontWeight: 600 }}>
                            <span>{it.date || "—"} · {daysSince(it.date) === 0 ? "오늘" : daysSince(it.date) + "일 전"}</span>
                            {it.entryPrice != null ? <span>{won(it.entryPrice)} → {it.curPrice != null ? won(it.curPrice) : "—"}</span> : <span>기록가 미저장</span>}
                        </div>
                    </div>
                )
            })}

            {!loading && items.length > 0 && (
                <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 6, lineHeight: 1.5 }}>
                    내 thesis 가 맞았는지 *스스로* 복기하는 용도 · VERITY 의 점수·정답 아님 · 클릭 시 종목 리포트
                </div>
            )}
        </div>
    )
}

addPropertyControls(PublicThesisReview, {
    width: { type: ControlType.Number, title: "Width", defaultValue: 380 },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    stockPath: { type: ControlType.String, title: "Stock Path", defaultValue: "/stock" },
})
