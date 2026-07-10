import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useCallback, useEffect, useState, type CSSProperties } from "react"

/**
 * AlphaNest 로그인/회원가입 — 공개 터미널(승인제 없음, 즉시 가입). 이메일 + 구글.
 *
 * 🚨 VERITY 운영 시스템과 겹치지 않음(해자):
 *   - VERITY 운영 콘솔(AuthPage)은 profiles.status="approved" 만 입장 허용.
 *   - AlphaNest 는 가입 시 status="pending"(공개 tier)로만 기록하고 **승인 상태 검사를 절대 안 함**
 *     → 사용자는 즉시 AlphaNest 사용 가능하지만, VERITY 운영 시스템엔 입장 불가(자동 접근 0).
 *   - 같은 Supabase 프로젝트 + 같은 세션키(verity_supabase_session)는 기존 관심종목 생태계
 *     (AlphaNestWatchlist /api/watchgroups)와의 호환 위해 유지. 접근 차단은 위 tier 로만 함.
 *
 * 목적 = 로그인하면 관심종목 등 '내 데이터'가 계정에 남음(미로그인=둘러보기 허용).
 * 회원가입(이메일) = Supabase signup. 이메일 인증이 켜져 있으면 인증 메일 안내, 꺼져 있으면 즉시 로그인.
 *   이메일 인증 링크는 signup ?redirect_to= 로 AlphaNest 로 복귀(미지정 시 Site URL=VERITY 폴백 방지).
 * 약관·개인정보·국외이전(미국) 동의 = 회원가입 시 필수(개인정보보호법 §28의8 국외이전 동의).
 * 로그인 성공 후 = afterLoginPath(또는 URL ?next=) 로 이동.
 * 세션 변경 시 window 'verity_auth_change' dispatch — 다른 AlphaNest 컴포넌트(관심종목)가 구독.
 *
 * 🚨 수동 선행(Supabase 대시보드): AlphaNest 도메인을 Auth → URL Configuration → Redirect URLs 추가 + Google provider enable.
 * 다크모드 = body[data-framer-theme] 추종(캔버스는 dark prop 정적).
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

async function supaFetch(url: string, anonKey: string, opts: RequestInit = {}): Promise<any> {
    const res = await fetch(url, {
        ...opts,
        headers: {
            "Content-Type": "application/json",
            apikey: anonKey,
            Authorization: `Bearer ${anonKey}`,
            ...((opts.headers as Record<string, string>) || {}),
        },
    })
    const body = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(body.error_description || body.msg || body.message || `HTTP ${res.status}`)
    return body
}

// AlphaNest = 공개 tier. profiles 행만 보장(없으면 생성). status="pending" = VERITY 승인 게이트 통과 불가(해자).
async function ensureProfile(supabaseUrl: string, anonKey: string, accessToken: string, userId: string, email: string, displayName: string, consent: boolean): Promise<void> {
    try {
        const payload: Record<string, any> = {
            id: userId,
            email,
            display_name: displayName || (email ? email.split("@")[0] : "AlphaNest"),
            status: "pending",
        }
        if (consent) payload.consent_given_at = new Date().toISOString()
        await fetch(`${supabaseUrl}/rest/v1/profiles`, {
            method: "POST",
            headers: {
                apikey: anonKey,
                Authorization: `Bearer ${accessToken}`,
                "Content-Type": "application/json",
                Prefer: "resolution=ignore-duplicates,return=minimal",
            },
            body: JSON.stringify(payload),
        })
    } catch { /* no-op */ }
}

function getGoogleOAuthUrl(supabaseUrl: string, redirectTo: string, anonKey: string): string {
    return `${supabaseUrl}/auth/v1/authorize?provider=google&redirect_to=${encodeURIComponent(redirectTo)}&apikey=${encodeURIComponent(anonKey)}`
}

// 로그인 성공 후 이동 경로 — URL 의 ?next=/path 우선, 없으면 afterLoginPath prop. (둘 다 없으면 빈 문자열=이동 안 함)
function resolveNext(afterLoginPath: string): string {
    if (typeof window !== "undefined") {
        try {
            const p = new URLSearchParams(window.location.search).get("next")
            if (p && p.startsWith("/")) return p
        } catch { /* ignore */ }
    }
    return (afterLoginPath || "").trim()
}

// 이메일 회원가입(즉시 — 승인 없음). access_token 오면 즉시 로그인, 없으면 이메일 인증 안내.
async function signUpEmail(supabaseUrl: string, anonKey: string, email: string, password: string, displayName: string, consent: boolean, redirectTo: string): Promise<{ session: SupaSession | null; needConfirm: boolean }> {
    // 인증 메일의 복귀 URL = redirect_to (미지정 시 Site URL=VERITY 로 폴백됨 → AlphaNest 로 명시).
    const q = redirectTo ? `?redirect_to=${encodeURIComponent(redirectTo)}` : ""
    const body = await supaFetch(`${supabaseUrl}/auth/v1/signup${q}`, anonKey, {
        method: "POST",
        body: JSON.stringify({ email, password, data: { name: displayName || email.split("@")[0], consent } }),
    })
    const userId: string | undefined = body.user?.id || body.id
    const accessToken: string | undefined = body.access_token
    if (!accessToken) return { session: null, needConfirm: true }
    const session: SupaSession = {
        access_token: accessToken,
        refresh_token: body.refresh_token || "",
        expires_at: body.expires_at || (Date.now() / 1000 + 3600),
        user: body.user || { id: userId || "", email },
    }
    if (userId) await ensureProfile(supabaseUrl, anonKey, accessToken, userId, email, displayName, consent)
    saveSession(session)
    return { session, needConfirm: false }
}

// 이메일 로그인(즉시 — 승인 상태 검사 안 함 = VERITY 게이트와 분리).
async function signInEmail(supabaseUrl: string, anonKey: string, email: string, password: string): Promise<SupaSession> {
    const body = await supaFetch(`${supabaseUrl}/auth/v1/token?grant_type=password`, anonKey, {
        method: "POST",
        body: JSON.stringify({ email, password }),
    })
    const session: SupaSession = {
        access_token: body.access_token,
        refresh_token: body.refresh_token,
        expires_at: body.expires_at || (Date.now() / 1000 + 3600),
        user: body.user,
    }
    if (session.user?.id) {
        await ensureProfile(supabaseUrl, anonKey, session.access_token, session.user.id, email, session.user.user_metadata?.name || "", false)
    }
    saveSession(session)
    return session
}

async function refreshSession(supabaseUrl: string, anonKey: string, refreshToken: string): Promise<SupaSession | null> {
    try {
        const body = await supaFetch(`${supabaseUrl}/auth/v1/token?grant_type=refresh_token`, anonKey, {
            method: "POST",
            body: JSON.stringify({ refresh_token: refreshToken }),
        })
        if (!body.access_token) return null
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

function humanError(msg: string): string {
    const m = (msg || "").toLowerCase()
    if (m.includes("already registered") || m.includes("already been registered")) return "이미 가입된 이메일입니다. 로그인해주세요."
    if (m.includes("invalid login") || m.includes("invalid credentials")) return "이메일 또는 비밀번호가 올바르지 않습니다."
    if (m.includes("email not confirmed")) return "이메일 인증이 필요합니다. 받은 메일의 링크를 눌러주세요."
    if (m.includes("password")) return "비밀번호는 6자 이상이어야 합니다."
    return msg || "오류가 발생했습니다. 다시 시도해주세요."
}

const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const LIGHT = { ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#e5e8eb", card: "#ffffff", bg: "#f2f4f6", field: "#f2f4f6", vg: "#6c5ce7", vgS: "#f0edff", danger: "#f04452", ok: "#0ca678" }
const DARK = { ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#252b34", card: "#171c23", bg: "#0f1318", field: "#1e242c", vg: "#a99bff", vgS: "#241f3a", danger: "#f04452", ok: "#34e08a" }

// ALPHANEST 브랜드 마크 — 보라 알(머리) + 네이비 둥지 아크. (Desktop/알파네스트 로고.svg 인라인)
function AlphaLogo({ size }: { size: number }) {
    return (
        <svg width={(size * 870) / 830} height={size} viewBox="0 0 870 830" fill="none" aria-hidden="true" style={{ display: "block" }}>
            <path d="M74.9999 403.5C74.9999 617 249 754.5 434 754.5C619 754.5 794.5 617 794.5 403.5" stroke="#3A4268" strokeWidth="150" strokeLinecap="round" />
            <path d="M648.655 309.5C648.655 479 561.655 598 433.655 598C309.943 598 216.155 465 220.655 309.5C220.655 143.815 331.655 0 434.655 0C537.655 0 648.655 140 648.655 309.5Z" fill="#6B51EA" />
        </svg>
    )
}

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
    afterLoginPath: string
    dark: boolean
    termsUrl?: string
    privacyUrl?: string
}
const DEFAULT_SUPABASE_URL = "https://lykqebdcurreppowulsl.supabase.co"
const DEFAULT_SUPABASE_ANON_KEY = ""

function readBodyDark(): boolean {
    // 첫 페인트 flash 방지 — body 속성 미설정(마운트 직후) 시 토글 저장 선호(localStorage) → OS 순 폴백.
    // PublicThemeToggle 이 verity_theme 로 저장 + body[data-framer-theme] 설정 = 동일 소스라 첫 페인트부터 정합.
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
        if (typeof window !== "undefined" && window.matchMedia) {
            return window.matchMedia("(prefers-color-scheme: dark)").matches
        }
    } catch (e) {}
    return false
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function AlphaNestAuth(props: Props) {
    const { supabaseUrl, supabaseAnonKey, redirectUrl, afterLoginPath, dark, termsUrl, privacyUrl } = props
    const url = (supabaseUrl || DEFAULT_SUPABASE_URL).replace(/\/+$/, "")
    const anonKey = supabaseAnonKey || DEFAULT_SUPABASE_ANON_KEY
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const [themeDark, setThemeDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!dark : readBodyDark()))
    const C = (onCanvas ? !!dark : themeDark) ? DARK : LIGHT
    useEffect(() => {
        if (onCanvas) return
        const readTheme = () => {
            const t = (typeof document !== "undefined" && document.body) ? document.body.dataset.framerTheme : ""
            setThemeDark(t === "dark")
        }
        readTheme()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(readTheme)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    const [session, setSession] = useState<SupaSession | null>(null)
    const [mode, setMode] = useState<"login" | "signup">("login")
    const [email, setEmail] = useState("")
    const [password, setPassword] = useState("")
    const [displayName, setDisplayName] = useState("")
    const [agreed, setAgreed] = useState(false)
    const [busy, setBusy] = useState(false)
    const [err, setErr] = useState("")
    const [ok, setOk] = useState("")

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
                const ures = await fetch(`${url}/auth/v1/user`, { headers: { apikey: anonKey, Authorization: `Bearer ${at}` } })
                const u = await ures.json().catch(() => null)
                if (!ures.ok || !u || !u.id) { setErr("로그인 처리 실패 — 다시 시도해주세요"); return false }
                const s: SupaSession = { access_token: at, refresh_token: rt, expires_at, user: { id: u.id, email: u.email, user_metadata: u.user_metadata } }
                saveSession(s)
                await ensureProfile(url, anonKey, at, u.id, u.email || "", u.user_metadata?.name || u.user_metadata?.full_name || "", true)
                try { window.history.replaceState(null, "", window.location.pathname + window.location.search) } catch { /* no-op */ }
                if (alive) { setSession(s); emitAuthChange() }
                const next = resolveNext(afterLoginPath)
                if (next && next !== window.location.pathname) window.location.href = next
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
            if (s && s.refresh_token && s.expires_at && Date.now() / 1000 > s.expires_at - 300) {
                const refreshed = await refreshSession(url, anonKey, s.refresh_token)
                if (refreshed) s = refreshed
            }
            if (alive) setSession(s)
        }
        init()

        const onAuth = () => { if (alive) setSession(loadSession()) }
        window.addEventListener(AUTH_EVENT, onAuth)
        window.addEventListener("storage", onAuth)

        const timer = setInterval(async () => {
            const cur = loadSession()
            if (cur && cur.refresh_token && cur.expires_at && Date.now() / 1000 > cur.expires_at - 300) {
                const r = await refreshSession(url, anonKey, cur.refresh_token)
                if (alive && r) setSession(r)
            }
        }, 60000)

        return () => { alive = false; window.removeEventListener(AUTH_EVENT, onAuth); window.removeEventListener("storage", onAuth); clearInterval(timer) }
    }, [url, anonKey, onCanvas])

    const submit = useCallback(async () => {
        if (busy) return
        setErr(""); setOk("")
        if (!email.trim() || !password) { setErr("이메일과 비밀번호를 입력해주세요"); return }
        if (password.length < 6) { setErr("비밀번호는 6자 이상 입력해주세요"); return }
        if (mode === "signup" && !agreed) { setErr("이용약관·개인정보처리방침(국외이전 포함) 동의가 필요합니다"); return }
        setBusy(true)
        try {
            if (mode === "signup") {
                const back = (redirectUrl || "").trim() || (typeof window !== "undefined" ? window.location.origin + window.location.pathname : "")
                const { session: s, needConfirm } = await signUpEmail(url, anonKey, email.trim(), password, displayName.trim(), agreed, back)
                if (needConfirm || !s) {
                    setOk("인증 메일을 보냈어요. 메일의 링크를 누른 뒤 로그인해주세요.")
                    setPassword("")
                    setMode("login")
                } else {
                    setSession(s); emitAuthChange()
                    const next = resolveNext(afterLoginPath)
                    if (next && typeof window !== "undefined" && next !== window.location.pathname) window.location.href = next
                }
            } else {
                const s = await signInEmail(url, anonKey, email.trim(), password)
                setSession(s); emitAuthChange()
                const next = resolveNext(afterLoginPath)
                if (next && typeof window !== "undefined" && next !== window.location.pathname) window.location.href = next
            }
        } catch (e: any) {
            setErr(humanError(e?.message || ""))
        } finally {
            setBusy(false)
        }
    }, [busy, mode, email, password, displayName, agreed, url, anonKey, afterLoginPath, redirectUrl])

    const googleLogin = () => {
        if (busy) return
        // 약관 동의는 회원가입 탭에서만 노출 → 구글도 회원가입 탭일 때만 동의 강제(로그인 탭=기존 회원 재방문)
        if (mode === "signup" && !agreed) { setErr("이용약관·개인정보처리방침(국외이전 포함) 동의가 필요합니다"); return }
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
                await fetch(`${url}/auth/v1/logout`, { method: "POST", headers: { "Content-Type": "application/json", apikey: anonKey, Authorization: `Bearer ${s.access_token}` } })
            } catch { /* no-op */ }
        }
    }

    const wrap: CSSProperties = { width: "100%", height: "100%", fontFamily: FONT, display: "flex", alignItems: "center", justifyContent: "center", boxSizing: "border-box", color: C.ink }
    const card: CSSProperties = { width: "100%", maxWidth: 360, background: C.card, borderRadius: 18, padding: "30px 24px", boxShadow: "0 2px 12px rgba(0,0,0,0.07)", boxSizing: "border-box" }
    const inputStyle: CSSProperties = { width: "100%", padding: "11px 13px", borderRadius: 11, border: `1.5px solid ${C.line}`, background: C.field, color: C.ink, fontSize: 13.5, fontFamily: FONT, outline: "none", boxSizing: "border-box" }

    // 로그인 상태 — 컴팩트 프로필
    if (session && session.user) {
        const meta = session.user.user_metadata || {}
        const avatar = meta.avatar_url || meta.picture
        const name = meta.name || meta.full_name || (session.user.email || "").split("@")[0]
        const ch = (String(name || "?").trim().charAt(0) || "?").toUpperCase()
        return (
            <div style={wrap}>
                <div style={{ ...card, display: "flex", alignItems: "center", gap: 12 }}>
                    {avatar ? (
                        <img src={avatar} alt="" width={40} height={40} referrerPolicy="no-referrer" style={{ width: 40, height: 40, borderRadius: "50%", objectFit: "cover", display: "block" }} />
                    ) : (
                        <span style={{ width: 40, height: 40, borderRadius: "50%", background: C.vgS, color: C.vg, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 17, fontWeight: 800 }}>{ch}</span>
                    )}
                    <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 14, fontWeight: 700, color: C.ink, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</div>
                        <div style={{ fontSize: 11.5, fontWeight: 600, color: C.faint, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{session.user.email}</div>
                    </div>
                    <button onClick={logout} style={{ border: `1px solid ${C.line}`, background: "transparent", cursor: "pointer", fontFamily: FONT, fontSize: 12.5, fontWeight: 700, color: C.sub, padding: "8px 12px", borderRadius: 10 }}>로그아웃</button>
                </div>
            </div>
        )
    }

    return (
        <div style={wrap}>
            <div style={card}>
                {/* 브랜드 lockup — 로고 + ALPHANEST (가운데 정렬, 여백 확대) */}
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, marginBottom: 26 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <AlphaLogo size={26} />
                        <span style={{ fontSize: 19, fontWeight: 800, color: C.ink, letterSpacing: "-0.4px" }}>ALPHANEST</span>
                    </div>
                </div>

                {/* 모드 탭 */}
                <div style={{ display: "flex", gap: 6, background: C.bg, padding: 4, borderRadius: 12, marginBottom: 16 }}>
                    {(["login", "signup"] as const).map((m) => {
                        const active = mode === m
                        return (
                            <button key={m} onClick={() => { setMode(m); setErr(""); setOk("") }}
                                style={{ flex: 1, border: "none", padding: "8px 0", borderRadius: 9, cursor: "pointer", fontFamily: FONT, fontSize: 13, fontWeight: 700, background: active ? C.card : "transparent", color: active ? C.vg : C.sub, boxShadow: active ? "0 1px 3px rgba(0,0,0,0.10)" : "none" }}>
                                {m === "login" ? "로그인" : "회원가입"}
                            </button>
                        )
                    })}
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {mode === "signup" && (
                        <input type="text" placeholder="이름 (선택)" value={displayName} onChange={(e) => setDisplayName(e.target.value)} style={inputStyle} />
                    )}
                    <input type="email" autoComplete="email" placeholder="이메일" value={email} onChange={(e) => setEmail(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} style={inputStyle} />
                    <input type="password" autoComplete={mode === "signup" ? "new-password" : "current-password"} placeholder="비밀번호 (6자 이상)" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && submit()} style={inputStyle} />
                </div>

                {/* 약관 동의 — 회원가입 탭에서만 노출, 필수 */}
                {mode === "signup" && (
                    <label style={{ display: "flex", alignItems: "flex-start", gap: 7, cursor: "pointer", fontSize: 11.5, color: C.sub, fontWeight: 600, lineHeight: 1.45, marginTop: 12 }}>
                        <input type="checkbox" checked={agreed} onChange={(e) => { setAgreed(e.target.checked); if (e.target.checked) setErr("") }} style={{ marginTop: 1, accentColor: C.vg, cursor: "pointer", flexShrink: 0 }} />
                        <span>
                            {termsUrl ? <a href={termsUrl} target="_blank" rel="noopener noreferrer" style={{ color: C.vg, textDecoration: "underline" }}>이용약관</a> : "이용약관"}
                            {" · "}
                            {privacyUrl ? <a href={privacyUrl} target="_blank" rel="noopener noreferrer" style={{ color: C.vg, textDecoration: "underline" }}>개인정보처리방침</a> : "개인정보처리방침"}
                            {" 및 회원정보 국외 이전(미국)에 동의합니다 "}
                            <span style={{ color: C.faint }}>(필수)</span>
                        </span>
                    </label>
                )}

                {err && <div style={{ marginTop: 12, fontSize: 11.5, color: C.danger, fontWeight: 700, lineHeight: 1.5 }}>{err}</div>}
                {ok && <div style={{ marginTop: 12, fontSize: 11.5, color: C.ok, fontWeight: 700, lineHeight: 1.5 }}>{ok}</div>}

                <button onClick={submit} disabled={busy}
                    style={{ width: "100%", marginTop: 16, padding: "13px 0", border: "none", borderRadius: 12, cursor: busy ? "default" : "pointer", fontFamily: FONT, fontSize: 14, fontWeight: 800, background: C.vg, color: "#ffffff", opacity: busy ? 0.6 : 1 }}>
                    {busy ? "처리 중…" : mode === "login" ? "로그인" : "회원가입"}
                </button>

                {/* 구분선 */}
                <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "16px 0" }}>
                    <div style={{ flex: 1, height: 1, background: C.line }} />
                    <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>또는</span>
                    <div style={{ flex: 1, height: 1, background: C.line }} />
                </div>

                <button onClick={googleLogin} disabled={busy}
                    style={{ width: "100%", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 9, border: `1.5px solid ${C.line}`, background: C.card, color: C.ink, cursor: busy ? "default" : "pointer", fontFamily: FONT, fontSize: 13.5, fontWeight: 700, padding: "11px 16px", borderRadius: 12, opacity: busy ? 0.6 : 1 }}>
                    <GoogleG size={18} />
                    Google로 계속하기
                </button>
            </div>
        </div>
    )
}

addPropertyControls(AlphaNestAuth, {
    supabaseUrl: { type: ControlType.String, title: "Supabase URL", defaultValue: DEFAULT_SUPABASE_URL },
    supabaseAnonKey: { type: ControlType.String, title: "Supabase Anon Key", defaultValue: DEFAULT_SUPABASE_ANON_KEY },
    redirectUrl: { type: ControlType.String, title: "OAuth Redirect URL", defaultValue: "", placeholder: "구글 복귀 URL (비우면 현재 페이지)" },
    afterLoginPath: { type: ControlType.String, title: "로그인 후 이동", defaultValue: "/", placeholder: "예: / (URL ?next= 가 우선, 비우면 그대로)" },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
    termsUrl: { type: ControlType.String, title: "이용약관 URL", defaultValue: "/policy" },
    privacyUrl: { type: ControlType.String, title: "개인정보처리방침 URL", defaultValue: "/policy" },
})
