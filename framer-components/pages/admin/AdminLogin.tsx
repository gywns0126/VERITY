import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useCallback, useEffect, useState, type CSSProperties } from "react"

/**
 * AdminLogin — AlphaNest 관리자 로그인 (AlphaNest 스타일).
 * 이메일+비밀번호 → Supabase 로그인 → verity_supabase_session 저장 → 다른 관리자 카드가 토큰 사용.
 * 🔒 is_admin 게이트: 로그인 후 profiles.is_admin 확인. 관리자 아니면 세션 폐기 + 차단 안내.
 * 세션 변경 시 verity_auth_change dispatch (관리자 카드 새로고침). 다크모드 자동감지.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", grid: "#eef1f4", up: "#f04452", down: "#3182f6",
    green: "#15c47e", greenS: "#eafaf3", amber: "#ff9500", vt: "#6c5ce7", vtS: "#f0edff", onAccent: "#ffffff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", grid: "#1e242c", up: "#f04452", down: "#5b9bff",
    green: "#34e08a", greenS: "#0f241c", amber: "#ff9500", vt: "#a99bff", vtS: "#241f3a", onAccent: "#0f1318",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const SESSION_KEY = "verity_supabase_session"
const AUTH_EVENT = "verity_auth_change"
const DEFAULT_SUPABASE_URL = "https://lykqebdcurreppowulsl.supabase.co"

interface Sess { access_token: string; refresh_token: string; expires_at: number; user: { id: string; email: string } }

function readBodyDark(): boolean {
    try {
        const _lsPref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (_lsPref === "dark") return true
        if (_lsPref === "light") return false
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
function loadSession(): Sess | null {
    if (typeof window === "undefined") return null
    try {
        const raw = localStorage.getItem(SESSION_KEY)
        if (!raw) return null
        const s = JSON.parse(raw)
        if (s.expires_at && Date.now() / 1000 > s.expires_at) return null
        return s as Sess
    } catch (e) { return null }
}
function saveSession(s: Sess) { if (typeof window !== "undefined") localStorage.setItem(SESSION_KEY, JSON.stringify(s)) }
function clearSession() { if (typeof window !== "undefined") localStorage.removeItem(SESSION_KEY) }
function emitAuth() { if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(AUTH_EVENT)) }

interface Props { supabaseUrl: string; supabaseAnonKey: string; dark: boolean }

export default function AdminLogin(props: Props) {
    const url = (props.supabaseUrl || DEFAULT_SUPABASE_URL).replace(/\/+$/, "")
    const anon = props.supabaseAnonKey || ""
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() => (onCanvas ? !!props.dark : readBodyDark()))
    const C = (onCanvas ? !!props.dark : themeDark) ? DARK : LIGHT

    const [session, setSession] = useState<Sess | null>(null)
    const [isAdmin, setIsAdmin] = useState<boolean | null>(null)
    const [email, setEmail] = useState("")
    const [password, setPassword] = useState("")
    const [busy, setBusy] = useState(false)
    const [err, setErr] = useState("")

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || !document.body) return
        const o = new MutationObserver(read)
        o.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => o.disconnect()
    }, [onCanvas])

    const checkAdmin = useCallback(async (s: Sess) => {
        if (!anon) { setIsAdmin(null); return }
        try {
            const r = await fetch(`${url}/rest/v1/profiles?id=eq.${s.user.id}&select=is_admin`, {
                headers: { apikey: anon, Authorization: "Bearer " + s.access_token, Accept: "application/json" },
            })
            const rows = r.ok ? await r.json().catch(() => []) : []
            setIsAdmin(Array.isArray(rows) && rows[0] && rows[0].is_admin === true)
        } catch (e) { setIsAdmin(null) }
    }, [url, anon])

    useEffect(() => {
        if (onCanvas) return
        const s = loadSession()
        setSession(s)
        if (s) checkAdmin(s)
    }, [onCanvas, checkAdmin])

    const login = async () => {
        if (busy || onCanvas) return
        setErr("")
        if (!email.trim() || !password) { setErr("이메일과 비밀번호를 입력해주세요"); return }
        if (!anon) { setErr("Supabase Anon Key 미설정 (컴포넌트 속성)"); return }
        setBusy(true)
        try {
            const r = await fetch(`${url}/auth/v1/token?grant_type=password`, {
                method: "POST",
                headers: { "Content-Type": "application/json", apikey: anon, Authorization: "Bearer " + anon },
                body: JSON.stringify({ email: email.trim(), password }),
            })
            const b = await r.json().catch(() => ({}))
            if (!r.ok || !b.access_token) throw new Error(b.error_description || b.msg || "로그인 실패")
            const s: Sess = { access_token: b.access_token, refresh_token: b.refresh_token || "", expires_at: b.expires_at || (Date.now() / 1000 + 3600), user: b.user }
            saveSession(s); setSession(s); emitAuth()
            await checkAdmin(s)
            setPassword("")
        } catch (e: any) {
            setErr(e && e.message ? e.message : "로그인 실패")
        } finally { setBusy(false) }
    }

    const logout = () => {
        clearSession(); setSession(null); setIsAdmin(null); emitAuth()
    }

    const wrap: CSSProperties = { width: "100%", boxSizing: "border-box", background: C.bg, fontFamily: FONT, color: C.ink, padding: 16, display: "flex", justifyContent: "center" }
    const card: CSSProperties = { width: "100%", maxWidth: 380, background: C.card, borderRadius: 18, padding: "26px 24px", boxShadow: "0 2px 12px rgba(0,0,0,0.07)", boxSizing: "border-box" }
    const input: CSSProperties = { width: "100%", boxSizing: "border-box", border: "none", background: C.grid, color: C.ink, borderRadius: 11, padding: "12px 13px", fontSize: 13.5, fontFamily: FONT, outline: "none" }
    const btn = (bg: string, fg: string): CSSProperties => ({ width: "100%", border: "none", cursor: busy ? "default" : "pointer", fontFamily: FONT, fontSize: 14, fontWeight: 800, background: bg, color: fg, borderRadius: 12, padding: "13px 0", opacity: busy ? 0.6 : 1 })

    // 로그인 상태 — 관리자 확인/차단
    if (session && session.user) {
        const admin = isAdmin === true
        return (
            <div style={wrap}>
                <div style={card}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
                        <span style={{ width: 10, height: 10, borderRadius: "50%", background: admin ? C.green : C.amber }} />
                        <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: "-0.3px" }}>{admin ? "관리자 인증됨" : "관리자 권한 없음"}</span>
                    </div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: C.ink }}>{session.user.email}</div>
                    <div style={{ fontSize: 12, color: admin ? C.green : C.amber, fontWeight: 700, marginTop: 4, lineHeight: 1.5 }}>
                        {isAdmin === null ? "권한 확인 중… (Anon Key 필요)" : admin ? "아래 관리자 도구를 사용할 수 있어요." : "이 계정은 관리자 권한이 없습니다. 운영자 계정으로 로그인하세요."}
                    </div>
                    <button onClick={logout} style={{ ...btn(C.grid, C.sub), marginTop: 16 }}>로그아웃</button>
                </div>
            </div>
        )
    }

    return (
        <div style={wrap}>
            <div style={card}>
                <div style={{ textAlign: "center", marginBottom: 20 }}>
                    <div style={{ fontSize: 19, fontWeight: 800, letterSpacing: "-0.4px" }}>AlphaNest 관리자</div>
                    <div style={{ fontSize: 12, color: C.faint, fontWeight: 600, marginTop: 4 }}>운영자 계정으로 로그인</div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    <input type="email" autoComplete="email" placeholder="이메일" value={email} onChange={(e) => setEmail(e.target.value)} onKeyDown={(e) => e.key === "Enter" && login()} style={input} />
                    <input type="password" autoComplete="current-password" placeholder="비밀번호" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && login()} style={input} />
                </div>
                {err && <div style={{ fontSize: 12, color: C.up, fontWeight: 700, marginTop: 12, lineHeight: 1.5 }}>{err}</div>}
                <button onClick={login} disabled={busy} style={{ ...btn(C.vt, C.onAccent), marginTop: 16 }}>{busy ? "로그인 중…" : "로그인"}</button>
                <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 12, textAlign: "center", lineHeight: 1.5 }}>관리자 지정 = Supabase에서 profiles.is_admin=true</div>
            </div>
        </div>
    )
}

addPropertyControls(AdminLogin, {
    supabaseUrl: { type: ControlType.String, title: "Supabase URL", defaultValue: DEFAULT_SUPABASE_URL },
    supabaseAnonKey: { type: ControlType.String, title: "Supabase Anon Key", defaultValue: "" },
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
})
