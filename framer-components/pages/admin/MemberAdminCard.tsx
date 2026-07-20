import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useCallback, useEffect, useState, type CSSProperties } from "react"

/**
 * MemberAdminCard — 관리자 회원 관리 (AlphaNest 스타일).
 * 소스: /api/admin?type=member_management (본인 JWT · is_admin 서버 재검증 · service_role 실행).
 *   GET 목록/검색 · POST ban|unban|update · DELETE(계정 삭제, 2단계 confirm).
 * 규율: 제재=쓰기 차단(읽기·로그인 허용). 삭제=되돌릴 수 없음 → 이메일 재입력 확인.
 * 다크모드 = body[data-framer-theme] 자동감지. 접근차단 = 페이지 AuthGate(is_admin 계정만).
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
        return `${d.getFullYear()}.${String(d.getMonth() + 1).padStart(2, "0")}.${String(d.getDate()).padStart(2, "0")}`
    } catch (e) { return "—" }
}

interface Member {
    id: string; email?: string; display_name?: string; nickname?: string
    status?: string; is_admin?: boolean; is_banned?: boolean; ban_reason?: string
    banned_at?: string; created_at?: string
}

const SAMPLE: Member[] = [
    { id: "u1", email: "user1@example.com", nickname: "가치투자자", status: "pending", is_admin: false, is_banned: false, created_at: "2026-06-01" },
    { id: "u2", email: "admin@example.com", nickname: "운영자", status: "approved", is_admin: true, is_banned: false, created_at: "2026-04-01" },
    { id: "u3", email: "spam@example.com", nickname: "홍보봇", status: "pending", is_admin: false, is_banned: true, ban_reason: "반복 홍보글", banned_at: "2026-07-10", created_at: "2026-07-08" },
]

interface Props { apiBase: string; dark: boolean }

export default function MemberAdminCard(props: Props) {
    const apiBase = (props.apiBase || DEFAULT_API).replace(/\/+$/, "")
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (onCanvas ? !!props.dark : readBodyDark()))
    const C = (onCanvas ? !!props.dark : themeDark) ? DARK : LIGHT

    const [members, setMembers] = useState<Member[]>(onCanvas ? SAMPLE : [])
    const [total, setTotal] = useState<number | null>(onCanvas ? SAMPLE.length : null)
    const [q, setQ] = useState("")
    const [loading, setLoading] = useState(false)
    const [err, setErr] = useState("")
    const [msg, setMsg] = useState("")
    const [openId, setOpenId] = useState("")           // 행 액션 펼침
    const [banId, setBanId] = useState("")             // 제재 사유 입력 중
    const [banReason, setBanReason] = useState("")
    const [delId, setDelId] = useState("")             // 삭제 확인 중
    const [delEmail, setDelEmail] = useState("")
    const [busy, setBusy] = useState("")               // 처리 중 user_id

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || !document.body) return
        const o = new MutationObserver(read)
        o.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => o.disconnect()
    }, [onCanvas])

    const load = useCallback((query: string) => {
        if (onCanvas) return
        const token = loadToken()
        if (!token) { setErr("관리자 로그인이 필요해요"); return }
        setLoading(true); setErr("")
        const url = `${apiBase}/api/admin?type=member_management&limit=100${query ? "&q=" + encodeURIComponent(query) : ""}`
        fetch(url, { headers: { Authorization: "Bearer " + token }, cache: "no-store" })
            .then((r) => (r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status))))
            .then((d) => { setMembers(Array.isArray(d.members) ? d.members : []); setTotal(d.total != null ? d.total : null) })
            .catch((e) => setErr("불러오기 실패: " + (e && e.message ? e.message : e)))
            .finally(() => setLoading(false))
    }, [apiBase, onCanvas])

    useEffect(() => { load("") }, [load])

    const act = async (m: Member, opts: { method?: string; body: any; ok: string }) => {
        if (onCanvas) return
        const token = loadToken()
        if (!token) { setErr("관리자 로그인이 필요해요"); return }
        setBusy(m.id); setErr(""); setMsg("")
        try {
            const r = await fetch(`${apiBase}/api/admin?type=member_management`, {
                method: opts.method || "POST",
                headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
                body: JSON.stringify(opts.body),
            })
            const d = await r.json().catch(() => ({}))
            if (!r.ok) throw new Error(d.error || ("HTTP " + r.status))
            setMsg(opts.ok)
            setOpenId(""); setBanId(""); setBanReason(""); setDelId(""); setDelEmail("")
            load(q)
        } catch (e: any) {
            setErr("실패: " + (e && e.message ? e.message : e))
        } finally {
            setBusy("")
        }
    }

    const wrap: CSSProperties = { width: "100%", boxSizing: "border-box", background: C.bg, fontFamily: FONT, color: C.ink, padding: 16, display: "flex", flexDirection: "column", gap: 12 }
    const card: CSSProperties = { background: C.card, borderRadius: 16, padding: "15px 17px", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }
    const chip = (bg: string, fg: string): CSSProperties => ({ fontSize: 11, fontWeight: 800, color: fg, background: bg, borderRadius: 7, padding: "2px 8px" })
    const btn = (bg: string, fg: string): CSSProperties => ({ border: "none", cursor: "pointer", fontFamily: FONT, fontSize: 12, fontWeight: 800, background: bg, color: fg, borderRadius: 9, padding: "7px 12px" })

    return (
        <div style={wrap}>
            {/* 헤더 + 검색 */}
            <div style={card}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap", marginBottom: 12 }}>
                    <span style={{ fontSize: 17, fontWeight: 800, letterSpacing: "-0.4px" }}>회원 관리</span>
                    <span style={{ fontSize: 12, color: C.faint, fontWeight: 600 }}>{total != null ? total.toLocaleString() + "명" : ""}</span>
                    <span style={{ marginLeft: "auto", fontSize: 11, color: C.faint, fontWeight: 600 }}>{loading ? "불러오는 중…" : ""}</span>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                    <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load(q)}
                        placeholder="이메일·별명·이름 검색"
                        style={{ flex: 1, border: "none", background: C.grid, color: C.ink, borderRadius: 11, padding: "11px 13px", fontSize: 13.5, fontFamily: FONT, outline: "none", boxSizing: "border-box" }} />
                    <button onClick={() => load(q)} style={btn(C.vt, C.onAccent)}>검색</button>
                </div>
                {err && <div style={{ fontSize: 12, color: C.up, fontWeight: 700, marginTop: 10 }}>{err}</div>}
                {msg && <div style={{ fontSize: 12, color: C.green, fontWeight: 700, marginTop: 10 }}>{msg}</div>}
            </div>

            {/* 회원 리스트 */}
            <div style={card}>
                {members.length === 0 && !loading ? (
                    <div style={{ fontSize: 13, color: C.faint, fontWeight: 600 }}>회원이 없어요</div>
                ) : members.map((m, i) => {
                    const opened = openId === m.id
                    const st = m.status === "approved" ? { bg: C.greenS, fg: C.green, t: "승인" } : m.status === "rejected" ? { bg: C.upS, fg: C.up, t: "거절" } : { bg: C.grid, fg: C.sub, t: "대기" }
                    return (
                        <div key={m.id} style={{ paddingTop: i === 0 ? 0 : 12, marginTop: i === 0 ? 0 : 12, borderTop: i === 0 ? "none" : `1px solid ${C.line}` }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", cursor: "pointer" }} onClick={() => { setOpenId(opened ? "" : m.id); setBanId(""); setDelId("") }}>
                                <span style={{ fontSize: 14, fontWeight: 800 }}>{m.nickname || m.display_name || "(별명 없음)"}</span>
                                {m.is_admin && <span style={chip(C.vtS, C.vt)}>관리자</span>}
                                {m.is_banned && <span style={chip(C.upS, C.up)}>제재됨</span>}
                                <span style={{ ...chip(st.bg, st.fg) }}>{st.t}</span>
                                <span style={{ marginLeft: "auto", fontSize: 11, color: C.faint, fontWeight: 700, transform: opened ? "rotate(90deg)" : "none", transition: "transform 0.12s" }}>›</span>
                            </div>
                            <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3 }}>{m.email} · 가입 {fmtDate(m.created_at)}{m.is_banned && m.ban_reason ? ` · 사유: ${m.ban_reason}` : ""}</div>

                            {opened && (
                                <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
                                    {/* 액션 버튼 행 */}
                                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                                        {m.status !== "approved" && <button disabled={busy === m.id} onClick={() => act(m, { body: { action: "update", user_id: m.id, status: "approved" }, ok: "승인했어요" })} style={btn(C.greenS, C.green)}>승인</button>}
                                        {m.is_banned
                                            ? <button disabled={busy === m.id} onClick={() => act(m, { body: { action: "unban", user_id: m.id }, ok: "제재를 해제했어요" })} style={btn(C.grid, C.sub)}>제재 해제</button>
                                            : <button disabled={busy === m.id} onClick={() => { setBanId(m.id); setBanReason("") }} style={btn(C.amberS, C.amber)}>제재</button>}
                                        <button disabled={busy === m.id} onClick={() => { setDelId(m.id); setDelEmail("") }} style={btn(C.upS, C.up)}>삭제</button>
                                    </div>

                                    {/* 제재 사유 입력 */}
                                    {banId === m.id && (
                                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", background: C.grid, borderRadius: 10, padding: 10 }}>
                                            <input value={banReason} onChange={(e) => setBanReason(e.target.value)} placeholder="제재 사유 (선택)"
                                                style={{ flex: 1, minWidth: 140, border: "none", background: C.card, color: C.ink, borderRadius: 8, padding: "8px 10px", fontSize: 12.5, fontFamily: FONT, outline: "none" }} />
                                            <button disabled={busy === m.id} onClick={() => act(m, { body: { action: "ban", user_id: m.id, reason: banReason }, ok: "제재했어요 (쓰기 차단)" })} style={btn(C.amber, "#fff")}>제재 확정</button>
                                            <button onClick={() => setBanId("")} style={btn(C.card, C.sub)}>취소</button>
                                        </div>
                                    )}

                                    {/* 삭제 2단계 확인 */}
                                    {delId === m.id && (
                                        <div style={{ background: C.upS, borderRadius: 10, padding: 10 }}>
                                            <div style={{ fontSize: 12, color: C.up, fontWeight: 700, marginBottom: 8, lineHeight: 1.5 }}>계정·글 전부 영구 삭제돼요 (되돌릴 수 없음). 확인하려면 이메일 <b>{m.email}</b> 입력:</div>
                                            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                                                <input value={delEmail} onChange={(e) => setDelEmail(e.target.value)} placeholder={m.email || ""}
                                                    style={{ flex: 1, minWidth: 160, border: "none", background: C.card, color: C.ink, borderRadius: 8, padding: "8px 10px", fontSize: 12.5, fontFamily: FONT, outline: "none" }} />
                                                <button disabled={busy === m.id || delEmail.trim() !== (m.email || "")} onClick={() => act(m, { method: "DELETE", body: { user_id: m.id, email: m.email, confirm: true }, ok: "삭제했어요" })}
                                                    style={{ ...btn(C.up, "#fff"), opacity: delEmail.trim() === (m.email || "") ? 1 : 0.5 }}>영구 삭제</button>
                                                <button onClick={() => setDelId("")} style={btn(C.card, C.sub)}>취소</button>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    )
                })}
            </div>
            <div style={{ textAlign: "center", fontSize: 11, color: C.faint, fontWeight: 600 }}>제재=쓰기 차단(읽기 허용) · 모든 변경 감사 로그 기록 · is_admin 계정만</div>
        </div>
    )
}

addPropertyControls(MemberAdminCard, {
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
})
