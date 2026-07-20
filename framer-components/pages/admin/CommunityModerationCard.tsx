import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useCallback, useEffect, useState, type CSSProperties } from "react"

/**
 * CommunityModerationCard — 관리자 커뮤니티 모더레이션 (AlphaNest 스타일).
 * 소스: /api/admin?type=community_moderation (본인 JWT · is_admin 서버 재검증 · service_role 실행).
 *   GET view=reports(신고 큐)|posts(전체 글) · POST hide|unhide · DELETE(글 삭제).
 *   작성자 제재 = member_management ban 재사용.
 * 다크모드 = body[data-framer-theme] 자동감지. 접근차단 = 페이지 AuthGate(is_admin).
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", grid: "#eef1f4", up: "#f04452", upS: "#fff0f1", down: "#3182f6",
    green: "#15c47e", greenS: "#eafaf3", amber: "#ff9500", amberS: "#fff6e9", vt: "#6c5ce7", vtS: "#f0edff", onAccent: "#ffffff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", grid: "#1e242c", up: "#f04452", upS: "#2a1a1d", down: "#5b9bff",
    green: "#34e08a", greenS: "#0f241c", amber: "#ff9500", amberS: "#2a2113", vt: "#a99bff", vtS: "#241f3a", onAccent: "#0f1318",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEFAULT_API = "https://project-yw131.vercel.app"
const SESSION_KEY = "verity_supabase_session"
const STANCE: Record<string, { t: string; c: (x: any) => string }> = {
    bull: { t: "강세", c: (C) => C.up }, bear: { t: "약세", c: (C) => C.down }, watch: { t: "관망", c: (C) => C.faint },
}

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

interface Thesis { id: string; user_id?: string; ticker?: string; market?: string; stance?: string; note?: string; is_public?: boolean; hidden?: boolean; created_at?: string }
interface Report { id: string; reason?: string; created_at?: string; reporter_id?: string; thesis?: Thesis }

const SAMPLE_REPORTS: Report[] = [
    { id: "r1", reason: "욕설·비방", created_at: "2026-07-14", reporter_id: "x", thesis: { id: "t1", user_id: "u3", ticker: "005930", stance: "bear", note: "이건 사기다 다 팔아라 ㅁㅊ", is_public: true, hidden: false, created_at: "2026-07-13" } },
    { id: "r2", reason: "홍보·스팸", created_at: "2026-07-14", reporter_id: "y", thesis: { id: "t2", user_id: "u5", ticker: "AAPL", stance: "bull", note: "지금 이 리딩방 들어오면 수익 보장 링크→", is_public: true, hidden: false, created_at: "2026-07-12" } },
]
const SAMPLE_POSTS: Thesis[] = [
    { id: "t1", user_id: "u3", ticker: "005930", stance: "bear", note: "메모리 다운사이클 우려", is_public: true, hidden: false, created_at: "2026-07-13" },
    { id: "t3", user_id: "u4", ticker: "247540", stance: "bull", note: "2차전지 저점 매수 관점", is_public: true, hidden: true, created_at: "2026-07-11" },
]

interface Props { apiBase: string; dark: boolean }

export default function CommunityModerationCard(props: Props) {
    const apiBase = (props.apiBase || DEFAULT_API).replace(/\/+$/, "")
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (onCanvas ? !!props.dark : readBodyDark()))
    const C = (onCanvas ? !!props.dark : themeDark) ? DARK : LIGHT

    const [tab, setTab] = useState<"reports" | "posts">("reports")
    const [reports, setReports] = useState<Report[]>(onCanvas ? SAMPLE_REPORTS : [])
    const [posts, setPosts] = useState<Thesis[]>(onCanvas ? SAMPLE_POSTS : [])
    const [loading, setLoading] = useState(false)
    const [err, setErr] = useState("")
    const [msg, setMsg] = useState("")
    const [busy, setBusy] = useState("")

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || !document.body) return
        const o = new MutationObserver(read)
        o.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => o.disconnect()
    }, [onCanvas])

    const load = useCallback((view: "reports" | "posts") => {
        if (onCanvas) return
        const token = loadToken()
        if (!token) { setErr("관리자 로그인이 필요해요"); return }
        setLoading(true); setErr("")
        fetch(`${apiBase}/api/admin?type=community_moderation&view=${view}&limit=100`, { headers: { Authorization: "Bearer " + token }, cache: "no-store" })
            .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
            .then((d) => {
                const items = Array.isArray(d.items) ? d.items : []
                if (view === "reports") setReports(items); else setPosts(items)
            })
            .catch((e) => setErr("불러오기 실패: " + (e && e.message ? e.message : e)))
            .finally(() => setLoading(false))
    }, [apiBase, onCanvas])

    useEffect(() => { load(tab) }, [tab, load])

    const mod = async (key: string, opts: { method?: string; body: any; ok: string }) => {
        if (onCanvas) return
        const token = loadToken()
        if (!token) { setErr("관리자 로그인이 필요해요"); return }
        setBusy(key); setErr(""); setMsg("")
        try {
            const r = await fetch(`${apiBase}/api/admin?type=community_moderation`, {
                method: opts.method || "POST",
                headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
                body: JSON.stringify(opts.body),
            })
            const d = await r.json().catch(() => ({}))
            if (!r.ok) throw new Error(d.error || ("HTTP " + r.status))
            setMsg(opts.ok); load(tab)
        } catch (e: any) {
            setErr("실패: " + (e && e.message ? e.message : e))
        } finally { setBusy("") }
    }

    const banAuthor = async (userId: string, key: string) => {
        if (onCanvas || !userId) return
        const token = loadToken()
        if (!token) { setErr("관리자 로그인이 필요해요"); return }
        setBusy(key); setErr(""); setMsg("")
        try {
            const r = await fetch(`${apiBase}/api/admin?type=member_management`, {
                method: "POST",
                headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
                body: JSON.stringify({ action: "ban", user_id: userId, reason: "커뮤니티 신고 처리" }),
            })
            const d = await r.json().catch(() => ({}))
            if (!r.ok) throw new Error(d.error || ("HTTP " + r.status))
            setMsg("작성자를 제재했어요 (쓰기 차단)")
        } catch (e: any) {
            setErr("실패: " + (e && e.message ? e.message : e))
        } finally { setBusy("") }
    }

    const wrap: CSSProperties = { width: "100%", boxSizing: "border-box", background: C.bg, fontFamily: FONT, color: C.ink, padding: 16, display: "flex", flexDirection: "column", gap: 12 }
    const card: CSSProperties = { background: C.card, borderRadius: 16, padding: "15px 17px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }
    const btn = (bg: string, fg: string): CSSProperties => ({ border: "none", cursor: "pointer", fontFamily: FONT, fontSize: 12, fontWeight: 800, background: bg, color: fg, borderRadius: 9, padding: "7px 12px" })
    const stanceChip = (st?: string) => {
        const m = STANCE[st || "watch"] || STANCE.watch
        return <span style={{ fontSize: 11, fontWeight: 800, color: m.c(C) }}>{m.t}</span>
    }

    const postBlock = (t: Thesis, keyPrefix: string) => (
        <div style={{ background: C.grid, borderRadius: 10, padding: 11, marginTop: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <span style={{ fontSize: 13, fontWeight: 800, color: C.vt }}>{t.ticker}</span>
                {stanceChip(t.stance)}
                {t.hidden && <span style={{ fontSize: 11, fontWeight: 800, color: C.amber, background: C.amberS, borderRadius: 6, padding: "2px 7px" }}>숨김</span>}
                <span style={{ marginLeft: "auto", fontSize: 11, color: C.faint, fontWeight: 600 }}>{fmtDate(t.created_at)}</span>
            </div>
            <div style={{ fontSize: 12.5, color: C.ink, fontWeight: 600, marginTop: 6, lineHeight: 1.5, wordBreak: "break-word" }}>{t.note || "(내용 없음)"}</div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
                {t.hidden
                    ? <button disabled={busy === keyPrefix} onClick={() => mod(keyPrefix, { body: { action: "unhide", thesis_id: t.id }, ok: "숨김을 해제했어요" })} style={btn(C.card, C.sub)}>숨김 해제</button>
                    : <button disabled={busy === keyPrefix} onClick={() => mod(keyPrefix, { body: { action: "hide", thesis_id: t.id }, ok: "글을 숨겼어요" })} style={btn(C.amberS, C.amber)}>숨김</button>}
                <button disabled={busy === keyPrefix} onClick={() => mod(keyPrefix, { method: "DELETE", body: { thesis_id: t.id }, ok: "글을 삭제했어요" })} style={btn(C.upS, C.up)}>글 삭제</button>
                {t.user_id && <button disabled={busy === keyPrefix} onClick={() => banAuthor(t.user_id as string, keyPrefix)} style={btn(C.card, C.up)}>작성자 제재</button>}
            </div>
        </div>
    )

    // 스켈레톤 — 최초 로딩 동안 신고/글 행 형태를 본떠 표시(빈 카드=오류처럼 보임 회피).
    const dk = onCanvas ? !!props.dark : themeDark
    const skBase = dk ? "#232a33" : "#e7eaee", skHi = dk ? "#2f3742" : "#f3f5f8"
    const shim: CSSProperties = { background: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`, backgroundSize: "800px 100%", animation: "cmcShimmer 1.4s ease-in-out infinite" }
    const skRows = (
        <>
            <style>{`@keyframes cmcShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
            {[0, 1, 2].map((i) => (
                <div key={i} style={{ paddingTop: i === 0 ? 0 : 12, marginTop: i === 0 ? 0 : 12, borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <div style={{ ...shim, width: 36, height: 16, borderRadius: 7 }} />
                        <div style={{ ...shim, width: 120, height: 13, borderRadius: 6 }} />
                        <div style={{ ...shim, width: 44, height: 12, borderRadius: 6, marginLeft: "auto" }} />
                    </div>
                    <div style={{ ...shim, width: "100%", height: 44, borderRadius: 10, marginTop: 8 }} />
                </div>
            ))}
        </>
    )

    return (
        <div style={wrap}>
            {/* 탭 */}
            <div style={card}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 12 }}>
                    <span style={{ fontSize: 17, fontWeight: 800, letterSpacing: "-0.4px" }}>커뮤니티 모더레이션</span>
                    <span style={{ marginLeft: "auto", fontSize: 11, color: C.faint, fontWeight: 600 }}>{loading ? "불러오는 중…" : ""}</span>
                </div>
                <div style={{ display: "flex", gap: 6, background: C.bg, padding: 4, borderRadius: 12 }}>
                    {([["reports", "신고 큐"], ["posts", "전체 글"]] as const).map(([k, label]) => {
                        const active = tab === k
                        return (
                            <button key={k} onClick={() => setTab(k as any)}
                                style={{ flex: 1, border: "none", padding: "8px 0", borderRadius: 9, cursor: "pointer", fontFamily: FONT, fontSize: 13, fontWeight: 800, background: active ? C.card : "transparent", color: active ? C.vt : C.sub, boxShadow: active ? "0 1px 3px rgba(0,0,0,0.10)" : "none" }}>
                                {label}{k === "reports" && reports.length > 0 ? ` ${reports.length}` : ""}
                            </button>
                        )
                    })}
                </div>
                {err && <div style={{ fontSize: 12, color: C.up, fontWeight: 700, marginTop: 10 }}>{err}</div>}
                {msg && <div style={{ fontSize: 12, color: C.green, fontWeight: 700, marginTop: 10 }}>{msg}</div>}
            </div>

            {/* 콘텐츠 */}
            <div style={card}>
                {tab === "reports" ? (
                    reports.length === 0 && loading ? skRows
                    : reports.length === 0 && !loading ? (
                        <div style={{ fontSize: 13, color: C.faint, fontWeight: 600 }}>처리할 신고가 없어요</div>
                    ) : reports.map((rp, i) => (
                        <div key={rp.id} style={{ paddingTop: i === 0 ? 0 : 12, marginTop: i === 0 ? 0 : 12, borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                                <span style={{ fontSize: 11.5, fontWeight: 800, color: C.up, background: C.upS, borderRadius: 7, padding: "2px 8px" }}>신고</span>
                                <span style={{ fontSize: 12.5, fontWeight: 700, color: C.ink }}>{rp.reason || "사유 없음"}</span>
                                <span style={{ marginLeft: "auto", fontSize: 11, color: C.faint, fontWeight: 600 }}>{fmtDate(rp.created_at)}</span>
                            </div>
                            {rp.thesis ? postBlock(rp.thesis, "r:" + rp.id) : <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, marginTop: 8 }}>대상 글이 이미 삭제됨</div>}
                        </div>
                    ))
                ) : (
                    posts.length === 0 && loading ? skRows
                    : posts.length === 0 && !loading ? (
                        <div style={{ fontSize: 13, color: C.faint, fontWeight: 600 }}>공개 글이 없어요</div>
                    ) : posts.map((t, i) => (
                        <div key={t.id} style={{ paddingTop: i === 0 ? 0 : 4, marginTop: i === 0 ? 0 : 4 }}>
                            {postBlock(t, "p:" + t.id)}
                        </div>
                    ))
                )}
            </div>
            <div style={{ textAlign: "center", fontSize: 11, color: C.faint, fontWeight: 600 }}>글 삭제=영구 · 숨김=피드에서만 제외 · 모든 조치 감사 로그 기록</div>
        </div>
    )
}

addPropertyControls(CommunityModerationCard, {
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
})
