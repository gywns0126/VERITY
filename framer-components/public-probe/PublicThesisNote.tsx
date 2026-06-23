import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState, type CSSProperties } from "react"

/**
 * 내 관점(thesis) 노트 — VERITY 공개 터미널. 종목 페이지에서 *사용자 본인*의 매매 결정 thesis 를 기록·재방문.
 *
 * 🚨 RULE 7 = 이건 **사용자 자기 저널**(관점/메모/날짜)이지 VERITY 의 추천·점수가 아님. 우리는 채점/판단 0.
 * 🚨 RULE 6 = LLM 0. 전부 사용자 입력 + 결정론적 가격 diff.
 * 저장 = localStorage `verity_thesis_v1` + "verity-thesis-changed" 이벤트 → PublicWatchlist 즉시 관점 배지 갱신.
 * 가격 = /api/stock(기록 시점 entryPrice 동결 → 재방문 diff).
 * ticker = prop → URL ?q= → localStorage `verity_last_ticker` 폴백(페이지 토글 시 종목 유지).
 *   + "verity-ticker-change" 이벤트 수신 → 같은 페이지 PublicDecisionPanel(검색 통합)이 종목 바꾸면 리로드 없이 따라옴(2026-06-23).
 */

const LIGHT = { bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#e5e8eb", up: "#f04452", down: "#3182f6", upS: "#fdecee", downS: "#eaf1fe", vg: "#0ca678", vgS: "#e7faf0", vt: "#6c5ce7", vtS: "#f0edff", chipBg: "#f2f4f6" }
const DARK = { bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#252b34", up: "#f04452", down: "#5b9bff", upS: "#2a1a1d", downS: "#17263c", vg: "#34e08a", vgS: "#11281d", vt: "#a99bff", vtS: "#241f3a", chipBg: "#0f1318" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEFAULT_API = "https://project-yw131.vercel.app"
const STORE_KEY = "verity_thesis_v1"
const LAST_TK_KEY = "verity_last_ticker"
const TK_EVENT = "verity-ticker-change"

const STANCES: { id: string; label: string; key: "up" | "down" | "faint" }[] = [
    { id: "bull", label: "강세", key: "up" },
    { id: "watch", label: "관망", key: "faint" },
    { id: "bear", label: "약세", key: "down" },
]

interface Props {
    ticker: string
    apiBase: string
    dark: boolean
}

function loadAll(): Record<string, any> {
    if (typeof window === "undefined") return {}
    try { return JSON.parse(window.localStorage.getItem(STORE_KEY) || "{}") || {} } catch { return {} }
}
function saveAll(o: Record<string, any>) {
    if (typeof window === "undefined") return
    try { window.localStorage.setItem(STORE_KEY, JSON.stringify(o)); window.dispatchEvent(new Event("verity-thesis-changed")) } catch { /* quota/private */ }
}
function todayStr(): string {
    const d = new Date()
    const k = new Date(d.getTime() + (d.getTimezoneOffset() + 540) * 60000) // KST
    return k.toISOString().slice(0, 10)
}
function daysSince(dateStr: string): number {
    try {
        const a = new Date(dateStr + "T00:00:00+09:00").getTime()
        const b = new Date(todayStr() + "T00:00:00+09:00").getTime()
        return Math.max(0, Math.round((b - a) / 86400000))
    } catch { return 0 }
}
function won(v: any): string {
    const x = Number(v)
    if (!isFinite(x) || x === 0) return "—"
    return Math.round(x).toLocaleString("en-US") + "원"
}

const DEMO_THESIS = { stance: "bull", note: "PER·PBR 업종 이하 + 내부자 순매수. 부채 낮음. 실적발표 후 재검토.", date: "2026-06-14", entryPrice: 71200, name: "DL이앤씨" }

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicThesisNote(props: Props) {
    const { ticker, apiBase, dark } = props
    const C = dark ? DARK : LIGHT
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const base = (apiBase || DEFAULT_API).replace(/\/+$/, "")

    const resolveTk = (): string => {
        if (ticker && ticker.trim()) return ticker.trim()
        if (typeof window !== "undefined") {
            try {
                const q = (new URLSearchParams(window.location.search).get("q") || "").trim()
                if (q) { try { window.localStorage.setItem(LAST_TK_KEY, q) } catch { /* */ } ; return q }
                return (window.localStorage.getItem(LAST_TK_KEY) || "").trim()
            } catch { return "" }
        }
        return ""
    }
    const [tk, setTk] = useState<string>(resolveTk)

    // 통합 DecisionPanel 이 종목 바꾸면(이벤트) / 뒤로가기(popstate) 시 리로드 없이 추종
    useEffect(() => {
        if (onCanvas) return
        const reread = () => setTk(resolveTk())
        reread()
        window.addEventListener(TK_EVENT, reread)
        window.addEventListener("popstate", reread)
        return () => { window.removeEventListener(TK_EVENT, reread); window.removeEventListener("popstate", reread) }
    }, [ticker, onCanvas])

    const [thesis, setThesis] = useState<any>(null)   // 저장된 기록
    const [editing, setEditing] = useState(false)
    const [stance, setStance] = useState("watch")
    const [note, setNote] = useState("")
    const [curPrice, setCurPrice] = useState<number | null>(null)

    // 기록 로드
    useEffect(() => {
        if (onCanvas) { setThesis(DEMO_THESIS); return }
        if (!tk) { setThesis(null); setEditing(false); return }
        const all = loadAll()
        const t = all[tk] || null
        setThesis(t)
        setEditing(!t)
        if (t) { setStance(t.stance); setNote(t.note || "") } else { setStance("watch"); setNote("") }
    }, [tk, onCanvas])

    // 현재가 (재방문 diff용 + 기록 시 entryPrice 동결)
    useEffect(() => {
        setCurPrice(null)
        if (onCanvas) { setCurPrice(73900); return }
        if (!tk || !base) return
        let alive = true
        fetch(base + "/api/stock?q=" + encodeURIComponent(tk) + "&market=kr")
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
                if (!alive || !d) return
                const p = d.price ?? d.current_price ?? (d.stock && d.stock.price)
                if (p != null) setCurPrice(Number(p))
            })
            .catch(() => {})
        return () => { alive = false }
    }, [tk, base, onCanvas])

    const save = () => {
        if (onCanvas || !tk) return
        const all = loadAll()
        const rec = {
            stance, note: note.trim(),
            date: (thesis && thesis.date) || todayStr(),
            entryPrice: (thesis && thesis.entryPrice != null) ? thesis.entryPrice : (curPrice != null ? curPrice : null),
            updated: todayStr(),
        }
        all[tk] = rec
        saveAll(all)
        setThesis(rec)
        setEditing(false)
    }
    const remove = () => {
        if (onCanvas || !tk) return
        const all = loadAll()
        delete all[tk]
        saveAll(all)
        setThesis(null); setEditing(true); setStance("watch"); setNote("")
    }

    const wrap: CSSProperties = { width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT, padding: 16, boxSizing: "border-box", color: C.ink }
    const stanceColor = (id: string) => { const s = STANCES.find((x) => x.id === id); return s ? (C as any)[s.key] : C.faint }
    const stanceLabel = (id: string) => { const s = STANCES.find((x) => x.id === id); return s ? s.label : "관망" }

    if (!tk && !onCanvas) {
        return <div style={{ ...wrap, textAlign: "center", color: C.faint, fontSize: 12.5, fontWeight: 600, padding: "22px 16px" }}>종목을 선택하면 내 관점을 기록할 수 있어요.</div>
    }

    const card: CSSProperties = { background: C.card, borderRadius: 14, padding: "14px 16px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }
    const title = (
        <div style={{ display: "flex", alignItems: "baseline", gap: 7, marginBottom: 10 }}>
            <span style={{ fontSize: 14, fontWeight: 800, color: C.ink }}>내 관점</span>
            <span style={{ fontSize: 11, fontWeight: 600, color: C.faint }}>· 본인 결정 저널 (VERITY 추천 아님)</span>
        </div>
    )

    // 기록 표시 (재방문) ─ "그 후 변화"
    if (thesis && !editing) {
        const since = daysSince(thesis.date)
        const ep = thesis.entryPrice
        const diffPct = (ep != null && curPrice != null && ep > 0) ? ((curPrice - ep) / ep) * 100 : null
        const dCol = diffPct == null ? C.faint : diffPct > 0 ? C.up : diffPct < 0 ? C.down : C.faint
        return (
            <div style={wrap}>
                <div style={card}>
                    {title}
                    <div style={{ display: "flex", alignItems: "center", gap: 9, flexWrap: "wrap" }}>
                        <span style={{ fontSize: 12.5, fontWeight: 800, color: "#fff", background: stanceColor(thesis.stance), borderRadius: 999, padding: "4px 12px" }}>{stanceLabel(thesis.stance)}</span>
                        <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>{thesis.date} · {since === 0 ? "오늘" : since + "일 전"} 기록</span>
                    </div>
                    {thesis.note && <div style={{ fontSize: 13, color: C.ink, fontWeight: 500, lineHeight: 1.5, marginTop: 9, background: C.bg, borderRadius: 10, padding: "10px 12px", whiteSpace: "pre-wrap" }}>{thesis.note}</div>}

                    {/* 그 후 변화 */}
                    <div style={{ marginTop: 11, paddingTop: 11, borderTop: `1px solid ${C.line}` }}>
                        <div style={{ fontSize: 11, fontWeight: 800, color: C.faint, marginBottom: 5 }}>기록 후 변화</div>
                        {ep != null ? (
                            <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                                <span style={{ fontSize: 12.5, color: C.sub, fontWeight: 600 }}>기록 시 {won(ep)} →</span>
                                <span style={{ fontSize: 14.5, fontWeight: 800, color: C.ink }}>{curPrice != null ? won(curPrice) : "—"}</span>
                                {diffPct != null && isFinite(diffPct) && (
                                    <span style={{ fontSize: 13, fontWeight: 800, color: dCol }}>{(diffPct > 0 ? "+" : "") + diffPct.toFixed(1)}%</span>
                                )}
                            </div>
                        ) : (
                            <div style={{ fontSize: 12, color: C.faint, fontWeight: 600 }}>기록 시 가격 미저장 (다음 기록부터 추적)</div>
                        )}
                        <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 6, lineHeight: 1.5 }}>내 thesis 가 맞았는지 *스스로* 복기하는 용도 · 점수·정답 제공 아님 · 사실(공시·수급·내부자) 변화는 아래 리포트에서</div>
                    </div>

                    <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                        <button onClick={() => setEditing(true)} style={{ flex: 1, cursor: "pointer", fontFamily: FONT, padding: "9px 0", borderRadius: 10, fontSize: 12.5, fontWeight: 700, background: C.chipBg, color: C.ink, border: `1px solid ${C.line}` }}>수정</button>
                        <button onClick={remove} style={{ flexShrink: 0, cursor: "pointer", fontFamily: FONT, padding: "9px 16px", borderRadius: 10, fontSize: 12.5, fontWeight: 700, background: "transparent", color: C.faint, border: `1px solid ${C.line}` }}>삭제</button>
                    </div>
                </div>
            </div>
        )
    }

    // 입력 폼 (신규/수정)
    return (
        <div style={wrap}>
            <div style={card}>
                {title}
                <div style={{ fontSize: 11.5, fontWeight: 700, color: C.sub, marginBottom: 6 }}>내 관점</div>
                <div style={{ display: "flex", gap: 7, marginBottom: 12 }}>
                    {STANCES.map((st) => {
                        const on = stance === st.id
                        const col = (C as any)[st.key]
                        // 선택 시 외곽선 없음 + 연한 파스텔 칩(강세=연빨강 / 약세=연파랑 / 관망=중립)
                        const softBg = st.key === "up" ? C.upS : st.key === "down" ? C.downS : C.chipBg
                        return (
                            <button key={st.id} onClick={() => setStance(st.id)}
                                style={{ flex: 1, border: "none", cursor: "pointer", fontFamily: FONT, padding: "10px 0", borderRadius: 10, fontSize: 13, fontWeight: on ? 800 : 700, background: on ? softBg : C.bg, color: on ? col : C.sub }}>
                                {st.label}
                            </button>
                        )
                    })}
                </div>
                <div style={{ fontSize: 11.5, fontWeight: 700, color: C.sub, marginBottom: 6 }}>왜 이렇게 보는지 (근거·재검토 시점)</div>
                <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3}
                    placeholder="예: PER·PBR 업종 이하 + 내부자 순매수. 부채 낮음. 다음 실적발표 후 재검토."
                    style={{ width: "100%", boxSizing: "border-box", border: `1px solid ${C.line}`, borderRadius: 10, padding: "10px 12px", fontSize: 12.5, fontFamily: FONT, fontWeight: 500, background: C.bg, color: C.ink, outline: "none", resize: "vertical", lineHeight: 1.5 }} />
                <div style={{ display: "flex", gap: 8, marginTop: 11, alignItems: "center" }}>
                    <button onClick={save} style={{ flex: 1, border: "none", cursor: "pointer", fontFamily: FONT, padding: "11px 0", borderRadius: 11, fontSize: 13, fontWeight: 800, background: C.vt, color: "#fff" }}>기록</button>
                    {thesis && <button onClick={() => { setEditing(false); setStance(thesis.stance); setNote(thesis.note || "") }} style={{ flexShrink: 0, cursor: "pointer", fontFamily: FONT, padding: "11px 16px", borderRadius: 11, fontSize: 13, fontWeight: 700, background: "transparent", color: C.faint, border: `1px solid ${C.line}` }}>취소</button>}
                </div>
                <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 9, lineHeight: 1.5 }}>이 기기에만 저장(localStorage) · 기록 시점 가격이 동결돼 재방문 시 변화를 보여줘요 · VERITY 의 판단·추천 아님</div>
            </div>
        </div>
    )
}

addPropertyControls(PublicThesisNote, {
    ticker: { type: ControlType.String, title: "Ticker (빈칸=URL ?q=)", defaultValue: "" },
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})
