import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useCallback, useEffect, useState, type CSSProperties } from "react"

/**
 * NoticeAdminCard — 공지·이벤트 발행 (AlphaNest 관리자).
 * 소스: /api/admin?type=notices (본인 JWT · is_admin 서버 재검증 · service_role 실행 · 감사 로그).
 *   GET 전량 목록 · POST 신규/수정(id 동봉 시) · DELETE. 공개 읽기는 /api/notices (027 RLS).
 * 노출 기간(시작/종료) 비우면 무기한. 종료 시각이 지나면 공개에서 자동으로 빠짐 = is_active 손댈 필요 없음.
 * 다크모드 자동감지. 접근차단 = 페이지 AdminGate(is_admin).
 *
 * 🚨 RULE 6 — 여기 쓰는 문구가 사이트에 그대로 나갑니다. LLM 생성 0, 관리자 작성 원문만.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", field: "#f7f8fa", up: "#f04452", upS: "#fff0f1",
    green: "#15c47e", greenS: "#eafaf3", vt: "#6c5ce7", vtS: "#f0edff", onAccent: "#ffffff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", field: "#1e242c", up: "#f04452", upS: "#2a1a1d",
    green: "#34e08a", greenS: "#0f241c", vt: "#a99bff", vtS: "#241f3a", onAccent: "#0f1318",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEFAULT_API = "https://project-yw131.vercel.app"
const SESSION_KEY = "verity_supabase_session"

function readBodyDark(): boolean {
    try {
        if (typeof document !== "undefined" && document.body) {
            const a = document.body.dataset.framerTheme
            if (a === "dark") return true
            if (a === "light") return false
        }
        if (typeof localStorage !== "undefined") {
            const s = localStorage.getItem("verity_theme")
            if (s === "dark") return true
            if (s === "light") return false
        }
        if (typeof window !== "undefined" && window.matchMedia) return window.matchMedia("(prefers-color-scheme: dark)").matches
    } catch (e) {}
    return false
}
function loadToken(): string {
    if (typeof window === "undefined") return ""
    try {
        const raw = localStorage.getItem(SESSION_KEY)
        if (!raw) return ""
        const s = JSON.parse(raw)
        if (s.expires_at && Date.now() / 1000 > s.expires_at) return ""
        return typeof s.access_token === "string" ? s.access_token : ""
    } catch (e) { return "" }
}
function fmtDate(iso: any): string {
    if (!iso) return "—"
    try {
        const d = new Date(String(iso))
        return `${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`
    } catch (e) { return "—" }
}

interface Notice {
    id: string; kind?: string; title?: string; body?: string; link?: string
    pinned?: boolean; starts_at?: string; ends_at?: string; is_active?: boolean; created_at?: string
}

const SAMPLE: Notice[] = [
    { id: "n1", kind: "event", title: "첫 관점 남기기 이벤트", body: "이번 주 안에 관점을 남기면 커뮤니티 첫 기록으로 남아요.", pinned: true, is_active: true, created_at: "2026-07-26" },
    { id: "n2", kind: "notice", title: "커뮤니티 이용 안내", body: "모든 글은 이용자 개인 의견이며 투자 권유가 아닙니다.", pinned: false, is_active: true, created_at: "2026-07-20" },
]

interface Props { apiBase: string; dark: boolean }

export default function NoticeAdminCard(props: Props) {
    const apiBase = (props.apiBase || DEFAULT_API).replace(/\/+$/, "")
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (onCanvas ? !!props.dark : readBodyDark()))
    const C = (onCanvas ? !!props.dark : themeDark) ? DARK : LIGHT

    const [items, setItems] = useState<Notice[]>(onCanvas ? SAMPLE : [])
    const [loading, setLoading] = useState(false)
    const [err, setErr] = useState("")
    const [msg, setMsg] = useState("")
    const [busy, setBusy] = useState("")

    // 작성 폼
    const [kind, setKind] = useState<"notice" | "event">("notice")
    const [title, setTitle] = useState("")
    const [body, setBody] = useState("")
    const [link, setLink] = useState("")
    const [pinned, setPinned] = useState(false)
    const [endsAt, setEndsAt] = useState("") // 이벤트 종료(YYYY-MM-DD). 비우면 무기한

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || !document.body) return
        const o = new MutationObserver(read)
        o.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => o.disconnect()
    }, [onCanvas])

    const load = useCallback(() => {
        if (onCanvas) return
        const token = loadToken()
        if (!token) { setErr("관리자 로그인이 필요해요"); return }
        setLoading(true); setErr("")
        fetch(`${apiBase}/api/admin?type=notices&limit=100`, { headers: { Authorization: "Bearer " + token }, cache: "no-store" })
            .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
            .then((d) => setItems(Array.isArray(d.items) ? d.items : []))
            .catch((e) => setErr("불러오기 실패: " + (e && e.message ? e.message : e)))
            .finally(() => setLoading(false))
    }, [apiBase, onCanvas])

    useEffect(() => { load() }, [load])

    const call = async (key: string, method: string, payload: any, okMsg: string) => {
        if (onCanvas) return
        const token = loadToken()
        if (!token) { setErr("관리자 로그인이 필요해요"); return }
        setBusy(key); setErr(""); setMsg("")
        try {
            const r = await fetch(`${apiBase}/api/admin?type=notices`, {
                method,
                headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            })
            const d = await r.json().catch(() => ({}))
            if (!r.ok) throw new Error(d.error || ("HTTP " + r.status))
            setMsg(okMsg); load()
        } catch (e: any) {
            setErr("실패: " + (e && e.message ? e.message : e))
        } finally {
            setBusy("")
        }
    }

    const publish = () => {
        const t = title.trim()
        if (!t) { setErr("제목을 입력해 주세요"); return }
        const payload: any = { kind, title: t, body: body.trim(), link: link.trim(), pinned, is_active: true }
        if (endsAt.trim()) payload.ends_at = endsAt.trim() + "T23:59:59+09:00" // 한국 기준 그날 끝까지
        call("new", "POST", payload, "발행했어요")
        setTitle(""); setBody(""); setLink(""); setPinned(false); setEndsAt("")
    }

    const wrap: CSSProperties = {
        background: C.card, borderRadius: 16, padding: "18px 18px 14px", fontFamily: FONT,
        color: C.ink, boxSizing: "border-box", width: "100%",
    }
    const label: CSSProperties = { fontSize: 11.5, fontWeight: 700, color: C.faint, marginBottom: 5 }
    const input: CSSProperties = {
        width: "100%", boxSizing: "border-box", border: "none", outline: "none", background: C.field,
        color: C.ink, fontFamily: FONT, fontSize: 13, fontWeight: 600, borderRadius: 10, padding: "10px 12px",
    }
    const btn = (bg: string, fg: string): CSSProperties => ({
        border: "none", cursor: "pointer", fontFamily: FONT, fontSize: 12.5, fontWeight: 800,
        borderRadius: 10, padding: "10px 16px", background: bg, color: fg,
    })

    return (
        <div style={wrap}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <span style={{ fontSize: 15.5, fontWeight: 800, letterSpacing: "-0.3px" }}>공지 · 이벤트</span>
                <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 600 }}>커뮤니티 상단 배너에 노출</span>
                <button onClick={load} disabled={loading} style={{ ...btn("transparent", C.vt), marginLeft: "auto", padding: "4px 8px" }}>
                    {loading ? "불러오는 중" : "새로고침"}
                </button>
            </div>

            {/* 작성 */}
            <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ display: "flex", gap: 8 }}>
                    {([["notice", "공지"], ["event", "이벤트"]] as const).map(([k, lb]) => (
                        <button
                            key={k}
                            onClick={() => setKind(k)}
                            style={btn(kind === k ? C.vt : C.field, kind === k ? C.onAccent : C.sub)}
                        >
                            {lb}
                        </button>
                    ))}
                    <label style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, fontWeight: 700, color: C.sub, cursor: "pointer" }}>
                        <input type="checkbox" checked={pinned} onChange={(e) => setPinned(e.target.checked)} />
                        상단 고정
                    </label>
                </div>
                <div>
                    <div style={label}>제목 (최대 120자)</div>
                    <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} placeholder="예: 커뮤니티 이용 안내" style={input} />
                </div>
                <div>
                    <div style={label}>본문 (선택 · 최대 2000자)</div>
                    <textarea value={body} onChange={(e) => setBody(e.target.value)} maxLength={2000} rows={3} placeholder="배너에 그대로 노출됩니다" style={{ ...input, resize: "vertical", lineHeight: 1.55 }} />
                </div>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                    <div style={{ flex: "1 1 200px", minWidth: 0 }}>
                        <div style={label}>링크 (선택)</div>
                        <input value={link} onChange={(e) => setLink(e.target.value)} placeholder="https://" style={input} />
                    </div>
                    <div style={{ flex: "0 1 170px" }}>
                        <div style={label}>종료일 (선택 · 비우면 무기한)</div>
                        <input value={endsAt} onChange={(e) => setEndsAt(e.target.value)} placeholder="2026-08-31" style={input} />
                    </div>
                </div>
                <button onClick={publish} disabled={busy === "new"} style={btn(C.vt, C.onAccent)}>
                    {busy === "new" ? "발행 중" : "발행"}
                </button>
            </div>

            {err ? <div style={{ marginTop: 10, fontSize: 12, fontWeight: 700, color: C.up, background: C.upS, borderRadius: 8, padding: "8px 10px" }}>{err}</div> : null}
            {msg ? <div style={{ marginTop: 10, fontSize: 12, fontWeight: 700, color: C.green, background: C.greenS, borderRadius: 8, padding: "8px 10px" }}>{msg}</div> : null}

            {/* 목록 */}
            <div style={{ marginTop: 16, borderTop: `1px solid ${C.line}`, paddingTop: 6 }}>
                {items.length === 0 ? (
                    <div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600, padding: "14px 2px" }}>
                        발행한 공지가 없어요
                    </div>
                ) : (
                    items.map((n) => (
                        <div key={n.id} style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "11px 2px", borderBottom: `1px solid ${C.line}` }}>
                            <span style={{ flexShrink: 0, marginTop: 2, fontSize: 10.5, fontWeight: 800, color: n.kind === "event" ? C.onAccent : C.vt, background: n.kind === "event" ? C.vt : C.vtS, borderRadius: 6, padding: "3px 7px" }}>
                                {n.kind === "event" ? "이벤트" : "공지"}
                            </span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 13, fontWeight: 800, color: n.is_active ? C.ink : C.faint }}>
                                    {n.title}
                                    {n.pinned ? <span style={{ marginLeft: 6, fontSize: 11, color: C.vt }}>고정</span> : null}
                                </div>
                                <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3 }}>
                                    {fmtDate(n.created_at)}
                                    {n.ends_at ? ` · ${fmtDate(n.ends_at)} 종료` : " · 무기한"}
                                    {n.is_active ? "" : " · 숨김"}
                                </div>
                            </div>
                            <button
                                onClick={() => call("t" + n.id, "POST", { id: n.id, is_active: !n.is_active }, n.is_active ? "숨겼어요" : "다시 노출해요")}
                                disabled={busy === "t" + n.id}
                                style={{ ...btn(C.field, C.sub), padding: "6px 10px", flexShrink: 0 }}
                            >
                                {n.is_active ? "숨김" : "노출"}
                            </button>
                            <button
                                onClick={() => {
                                    if (typeof window !== "undefined" && !window.confirm("삭제할까요? 되돌릴 수 없어요.")) return
                                    call("d" + n.id, "DELETE", { id: n.id }, "삭제했어요")
                                }}
                                disabled={busy === "d" + n.id}
                                style={{ ...btn(C.upS, C.up), padding: "6px 10px", flexShrink: 0 }}
                            >
                                삭제
                            </button>
                        </div>
                    ))
                )}
            </div>
        </div>
    )
}

addPropertyControls(NoticeAdminCard, {
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
})
