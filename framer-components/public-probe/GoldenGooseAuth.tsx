import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState, type CSSProperties } from "react"

/**
 * 골든구스 로그인 위젯 — 공개 터미널(승인제 없음). 구글 원클릭 OAuth.
 *
 * 목적 = 접근 차단 X. 로그인하면 관심종목 등 '내 데이터'가 계정에 남음(미로그인=그냥 둘러보기 허용).
 * 메인 VERITY 와 같은 Supabase 프로젝트 + 같은 세션키(verity_supabase_session) — 단 status(승인) 검사 안 함.
 *   GG 가입은 profiles 에 pending 으로 들어가되 GG 는 무시 → 메인 VERITY(운영 시스템)엔 자동 접근 안 됨(해자 보호).
 * 세션 변경 시 window 'verity_auth_change' 이벤트 dispatch — 다른 GG 컴포넌트(관심종목 별표/내 종목)가 구독.
 *
 * 🚨 수동 선행(Supabase 대시보드): GG 도메인을 Auth → URL Configuration → Redirect URLs 에 추가 + Google provider enable.
 * 다크모드 = body[data-framer-theme] 추종(캔버스는 dark prop). nav 는 사용자가 직접 — 이건 nav 에 얹는 로그인 '버튼'.
 */

const SESSION_KEY = "verity_supabase_session"
const AUTH_EVENT = "verity_auth_change"

interface SupaSession {
    access_token: string
    refresh_token: string
    expires_at: number
    user: { id: string; email: string; user_metadata?: any }
}

function saveSession(s: SupaSession) {
    if (typeof window !== "undefined") localStorage.setItem(SESSION_KEY, JSON.stringify(s))
}
function clearSession() {
    if (typeof window !== "undefined") localStorage.removeItem(SESSION_KEY)
}
function loadSession(): SupaSession | null {
    if (typeof window === "undefined") return null
    try {
        const raw = localStorage.getItem(SESSION_KEY)
        if (!raw) return null
        const s: SupaSession = JSON.parse(raw)
        if (s.expires_at && Date.now() / 1000 > s.expires_at) return null
        return s
    } catch { return null }
}
export function getVeritySession(): SupaSession | null {
    return loadSession()
}
function emitAuthChange() {
    if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(AUTH_EVENT))
}

// GG 는 승인 검사 안 함 — profiles 행만 보장(없으면 생성, status pending 은 메인 게이트용이라 GG 무시).
async function ensureProfile(supabaseUrl: string, anonKey: string, accessToken: string, userId: string, email: string, displayName: string): Promise<void> {
    try {
        await fetch(`${supabaseUrl}/rest/v1/profiles`, {
            method: "POST",
            headers: {
                apikey: anonKey,
                Authorization: `Bearer ${accessToken}`,
                "Content-Type": "application/json",
                Prefer: "resolution=ignore-duplicates,return=minimal",
            },
            body: JSON.stringify({
                id: userId,
                email,
                display_name: displayName || (email ? email.split("@")[0] : "골든구스"),
                status: "pending",
            }),
        })
    } catch { /* no-op */ }
}

function getGoogleOAuthUrl(supabaseUrl: string, redirectTo: string, anonKey: string): string {
    return `${supabaseUrl}/auth/v1/authorize?provider=google&redirect_to=${encodeURIComponent(redirectTo)}&apikey=${encodeURIComponent(anonKey)}`
}

async function refreshSession(supabaseUrl: string, anonKey: string, refreshToken: string): Promise<SupaSession | null> {
    try {
        const res = await fetch(`${supabaseUrl}/auth/v1/token?grant_type=refresh_token`, {
            method: "POST",
            headers: { "Content-Type": "application/json", apikey: anonKey, Authorization: `Bearer ${anonKey}` },
            body: JSON.stringify({ refresh_token: refreshToken }),
        })
        const body = await res.json().catch(() => ({}))
        if (!res.ok || !body.access_token) return null
        const session: SupaSession = {
            access_token: body.access_token,
            refresh_token: body.refresh_token,
            expires_at: body.expires_at || (Date.now() / 1000 + 3600),
            user: body.user,
        }
        saveSession(session)
        return session
    } catch { return null }
}

const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const LIGHT = { ink: "#191f28", sub: "#4e5968", line: "#e5e8eb", card: "#ffffff", bg: "#f2f4f6", vg: "#0ca678", vgS: "#e7faf0" }
const DARK = { ink: "#e3e7ec", sub: "#9aa4b1", line: "#252b34", card: "#171c23", bg: "#0f1318", vg: "#7fffa0", vgS: "#11281d" }

function GoogleG({ size }: { size: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 48 48" style={{ display: "block" }}>
            <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3c-1.6 4.7-6.1 8-11.3 8-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.3-.4-3.5z" />
            <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 16 19 13 24 13c3.1 0 5.9 1.2 8 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
            <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.6 39.6 16.2 44 24 44z" />
            <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C39.9 36.3 44 30.8 44 24c0-1.3-.1-2.3-.4-3.5z" />
        </svg>
    )
}

interface Props {
    supabaseUrl: string
    supabaseAnonKey: string
    redirectUrl: string
    dark: boolean
}
const DEFAULT_SUPABASE_URL = "https://lykqebdcurreppowulsl.supabase.co"
const DEFAULT_SUPABASE_ANON_KEY = ""

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function GoldenGooseAuth(props: Props) {
    const { supabaseUrl, supabaseAnonKey, redirectUrl, dark } = props
    const url = (supabaseUrl || DEFAULT_SUPABASE_URL).replace(/\/+$/, "")
    const anonKey = supabaseAnonKey || DEFAULT_SUPABASE_ANON_KEY

    const [themeDark, setThemeDark] = useState<boolean>(!!dark)
    const C = (RenderTarget.current() === RenderTarget.canvas ? !!dark : themeDark) ? DARK : LIGHT
    useEffect(() => {
        if (RenderTarget.current() === RenderTarget.canvas) return
        const readTheme = () => {
            const t = (typeof document !== "undefined" && document.body) ? document.body.dataset.framerTheme : ""
            setThemeDark(t === "dark")
        }
        readTheme()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(readTheme)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [])

    const [session, setSession] = useState<SupaSession | null>(null)
    const [busy, setBusy] = useState(false)
    const [err, setErr] = useState("")

    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    // OAuth #access_token hash 소비(승인 검사 없음) + 기존 세션 로드 + 토큰 갱신.
    useEffect(() => {
        if (onCanvas || typeof window === "undefined") return
        let alive = true

        const consumeHash = async () => {
            const hash = window.location.hash || ""
            if (!hash.includes("access_token=")) return false
            try {
                const params = new URLSearchParams(hash.replace(/^#/, ""))
                const at = params.get("access_token")
                const rt = params.get("refresh_token") || ""
                const expRaw = params.get("expires_at") || params.get("expires_in") || ""
                if (!at) return false
                const expires_at = Number(expRaw) > 1e9 ? Number(expRaw) : Date.now() / 1000 + Number(expRaw || 3600)
                const ures = await fetch(`${url}/auth/v1/user`, {
                    headers: { apikey: anonKey, Authorization: `Bearer ${at}` },
                })
                const u = await ures.json().catch(() => null)
                if (!ures.ok || !u || !u.id) { setErr("로그인 처리 실패 — 다시 시도해주세요"); return false }
                const s: SupaSession = { access_token: at, refresh_token: rt, expires_at, user: { id: u.id, email: u.email, user_metadata: u.user_metadata } }
                saveSession(s)
                await ensureProfile(url, anonKey, at, u.id, u.email || "", u.user_metadata?.name || u.user_metadata?.full_name || "")
                // hash 제거(주소창 토큰 노출 회피)
                try { window.history.replaceState(null, "", window.location.pathname + window.location.search) } catch { /* no-op */ }
                if (alive) { setSession(s); emitAuthChange() }
                return true
            } catch {
                if (alive) setErr("로그인 처리 실패")
                return false
            }
        }

        const init = async () => {
            const consumed = await consumeHash()
            if (consumed) return
            let s = loadSession()
            // 만료 임박(5분 이내) 시 갱신
            if (s && s.refresh_token && s.expires_at && Date.now() / 1000 > s.expires_at - 300) {
                const refreshed = await refreshSession(url, anonKey, s.refresh_token)
                if (refreshed) s = refreshed
            }
            if (alive) setSession(s)
        }
        init()

        // 다른 GG 컴포넌트/탭의 로그인·로그아웃 반영
        const onAuth = () => { if (alive) setSession(loadSession()) }
        window.addEventListener(AUTH_EVENT, onAuth)
        window.addEventListener("storage", onAuth)

        // 주기적 토큰 갱신(만료 5분 전)
        const timer = setInterval(async () => {
            const cur = loadSession()
            if (cur && cur.refresh_token && cur.expires_at && Date.now() / 1000 > cur.expires_at - 300) {
                const r = await refreshSession(url, anonKey, cur.refresh_token)
                if (alive && r) setSession(r)
            }
        }, 60000)

        return () => { alive = false; window.removeEventListener(AUTH_EVENT, onAuth); window.removeEventListener("storage", onAuth); clearInterval(timer) }
    }, [url, anonKey, onCanvas])

    const login = () => {
        if (busy) return
        setErr("")
        setBusy(true)
        const back = (redirectUrl || "").trim() || (typeof window !== "undefined" ? window.location.origin + window.location.pathname : "")
        if (typeof window !== "undefined") window.location.href = getGoogleOAuthUrl(url, back, anonKey)
    }
    const logout = async () => {
        const s = loadSession()
        clearSession()
        setSession(null)
        emitAuthChange()
        if (s) {
            try {
                await fetch(`${url}/auth/v1/logout`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json", apikey: anonKey, Authorization: `Bearer ${s.access_token}` },
                })
            } catch { /* no-op */ }
        }
    }

    const wrap: CSSProperties = { fontFamily: FONT, display: "inline-flex", alignItems: "center", width: "100%", height: "100%" }

    if (session && session.user) {
        const meta = session.user.user_metadata || {}
        const avatar = meta.avatar_url || meta.picture
        const name = meta.name || meta.full_name || (session.user.email || "").split("@")[0]
        const ch = (String(name || "?").trim().charAt(0) || "?").toUpperCase()
        return (
            <div style={wrap}>
                <div style={{ display: "inline-flex", alignItems: "center", gap: 9 }}>
                    {avatar ? (
                        <img src={avatar} alt="" width={28} height={28} referrerPolicy="no-referrer" style={{ width: 28, height: 28, borderRadius: "50%", objectFit: "cover", display: "block" }} />
                    ) : (
                        <span style={{ width: 28, height: 28, borderRadius: "50%", background: C.vgS, color: C.vg, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 800 }}>{ch}</span>
                    )}
                    <span style={{ fontSize: 13, fontWeight: 700, color: C.ink, maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</span>
                    <button onClick={logout} style={{ border: "none", background: "transparent", cursor: "pointer", fontFamily: FONT, fontSize: 12, fontWeight: 700, color: C.sub, padding: "4px 6px" }}>로그아웃</button>
                </div>
            </div>
        )
    }

    return (
        <div style={wrap}>
            <div style={{ display: "inline-flex", flexDirection: "column", alignItems: "stretch", gap: 4 }}>
                <button onClick={login} disabled={busy}
                    style={{
                        display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 9,
                        border: `1px solid ${C.line}`, background: C.card, color: C.ink, cursor: busy ? "default" : "pointer",
                        fontFamily: FONT, fontSize: 13.5, fontWeight: 700, padding: "9px 16px", borderRadius: 12,
                        boxShadow: "0 1px 2px rgba(0,0,0,0.05)", opacity: busy ? 0.6 : 1, whiteSpace: "nowrap",
                    }}>
                    <GoogleG size={18} />
                    {busy ? "이동 중…" : "구글로 로그인"}
                </button>
                {err && <span style={{ fontSize: 11, color: "#f04452", fontWeight: 600 }}>{err}</span>}
            </div>
        </div>
    )
}

addPropertyControls(GoldenGooseAuth, {
    supabaseUrl: { type: ControlType.String, title: "Supabase URL", defaultValue: DEFAULT_SUPABASE_URL },
    supabaseAnonKey: { type: ControlType.String, title: "Supabase Anon Key", defaultValue: DEFAULT_SUPABASE_ANON_KEY },
    redirectUrl: { type: ControlType.String, title: "Redirect URL", defaultValue: "", placeholder: "비우면 현재 페이지로 복귀" },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})
