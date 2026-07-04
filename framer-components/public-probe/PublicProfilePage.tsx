import { addPropertyControls, ControlType, RenderTarget } from "framer"
import React, { useCallback, useEffect, useState } from "react"

/**
 * AlphaNest 계정 페이지 (합본) — 미로그인 = 로그인/회원가입 폼, 로그인 = 내정보. 한 컴포넌트.
 *
 * 2026-07-04 PM 지시 "그냥 합쳐": AlphaNestAuth(폼) + PublicProfilePage(내정보) 2-컴포넌트
 * 자가숨김 조합 → 단일 컴포넌트 병합. 로그인 성공 = 이동 없이 제자리에서 내정보로 전환
 * (URL ?next=/path 가 있을 때만 그리로 이동). 로그아웃/탈퇴 = 제자리에서 폼으로 전환.
 *
 * 🚨 VERITY 운영 시스템과 겹치지 않음(해자):
 *   - VERITY 운영 콘솔(AuthPage)은 profiles.status="approved" 만 입장 허용.
 *   - AlphaNest 는 가입 시 status="pending"(공개 tier)로만 기록, 승인 상태 검사를 절대 안 함.
 *   - 같은 Supabase 프로젝트 + 같은 세션키(verity_supabase_session) = 관심종목 생태계 호환.
 *
 * 세션 변경 시 window 'verity_auth_change' dispatch — 다른 AlphaNest 컴포넌트(관심종목)가 구독.
 * 탈퇴: anon key 로는 auth user 물리 삭제 불가 → profiles.status="withdrawn" soft-delete.
 * 테마: body[data-framer-theme] 추종 (캔버스는 dark prop 정적). RULE7: 점수/등급 0.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    violet: "#6c5ce7", violetSoft: "#f0edff",
    line: "#e5e8eb", field: "#f7f8fa", red: "#f04452", redSoft: "#fff0f1",
    green: "#15c47e", greenSoft: "#eafaf3", blue: "#3182f6", blueSoft: "#eef4ff", ok: "#0ca678",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    violet: "#a98bff", violetSoft: "#241f3a",
    line: "#252b34", field: "#1e242c", red: "#f04452", redSoft: "#2a1a1d",
    green: "#34e08a", greenSoft: "#0f241c", blue: "#5b9bff", blueSoft: "#152031", ok: "#34e08a",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Menlo', monospace"
const SESSION_KEY = "verity_supabase_session"
const AUTH_EVENT = "verity_auth_change"
const DEFAULT_SUPABASE_URL = "https://lykqebdcurreppowulsl.supabase.co"
// 공개 anon key (클라이언트 배포 전제 설계 — service role 아님)
const DEFAULT_SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx5a3FlYmRjdXJyZXBwb3d1bHNsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUwMTcyMTUsImV4cCI6MjA5MDU5MzIxNX0.JhwsWgsrdDJ12BzZZjR7o6jdS-Mxny2eSJeWq59DhNs"

interface SupaSession {
    access_token: string
    refresh_token: string
    expires_at: number
    user: { id: string; email: string; created_at?: string; user_metadata?: any }
}

interface Profile {
    display_name: string
    email: string
    phone: string
    status: string
    created_at: string
}

const SAMPLE: Profile = {
    display_name: "홍길동",
    email: "user@example.com",
    phone: "010-1234-5678",
    status: "approved",
    created_at: "2026-04-01T00:00:00Z",
}

function loadSession(): SupaSession | null {
    if (typeof window === "undefined") return null
    try {
        const raw = localStorage.getItem(SESSION_KEY)
        if (!raw) return null
        const s: SupaSession = JSON.parse(raw)
        if (s.expires_at && Date.now() / 1000 > s.expires_at) return null
        return s
    } catch (e) {
        return null
    }
}
function saveSession(s: SupaSession) {
    if (typeof window !== "undefined") localStorage.setItem(SESSION_KEY, JSON.stringify(s))
}
function clearSession() {
    if (typeof window !== "undefined") localStorage.removeItem(SESSION_KEY)
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
    } catch (e) { /* no-op */ }
}

function getGoogleOAuthUrl(supabaseUrl: string, redirectTo: string, anonKey: string): string {
    return `${supabaseUrl}/auth/v1/authorize?provider=google&redirect_to=${encodeURIComponent(redirectTo)}&apikey=${encodeURIComponent(anonKey)}`
}

// 로그인 성공 후 이동 — URL 의 ?next=/path 가 있을 때만. 기본 = 이동 없이 제자리 전환(합본 설계).
function resolveNext(): string {
    if (typeof window !== "undefined") {
        try {
            const p = new URLSearchParams(window.location.search).get("next")
            if (p && p.startsWith("/")) return p
        } catch (e) { /* ignore */ }
    }
    return ""
}
function afterLoginNavigate() {
    const next = resolveNext()
    if (next && typeof window !== "undefined" && next !== window.location.pathname) window.location.href = next
}

// 이메일 회원가입(즉시 — 승인 없음). access_token 오면 즉시 로그인, 없으면 이메일 인증 안내.
// redirect_to = 현재 페이지 — 인증 메일 링크가 Site URL(VERITY 터미널)이 아닌 이 페이지로 복귀.
// 🚨 Supabase 대시보드 Redirect URLs 허용 목록에 이 도메인 와일드카드가 있어야 유효 (미등록 시 Site URL 폴백).
async function signUpEmail(supabaseUrl: string, anonKey: string, email: string, password: string, displayName: string, consent: boolean): Promise<{ session: SupaSession | null; needConfirm: boolean }> {
    const back = typeof window !== "undefined" ? window.location.origin + window.location.pathname : ""
    const q = back ? `?redirect_to=${encodeURIComponent(back)}` : ""
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

async function refreshSessionCall(supabaseUrl: string, anonKey: string, refreshToken: string): Promise<SupaSession | null> {
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
    } catch (e) {
        return null
    }
}

function humanError(msg: string): string {
    const m = (msg || "").toLowerCase()
    if (m.includes("already registered") || m.includes("already been registered")) return "이미 가입된 이메일입니다. 로그인해주세요."
    if (m.includes("invalid login") || m.includes("invalid credentials")) return "이메일 또는 비밀번호가 올바르지 않습니다."
    if (m.includes("email not confirmed")) return "이메일 인증이 필요합니다. 받은 메일의 링크를 눌러주세요."
    if (m.includes("password")) return "비밀번호는 6자 이상이어야 합니다."
    return msg || "오류가 발생했습니다. 다시 시도해주세요."
}

async function fetchProfile(
    url: string, anon: string, token: string, table: string, userId: string
): Promise<Partial<Profile> | null> {
    if (!url || !anon || !token || !userId) return null
    try {
        const sel = "display_name,email,phone,status"
        const res = await fetch(
            `${url}/rest/v1/${table}?id=eq.${userId}&select=${sel}`,
            { headers: { apikey: anon, Authorization: `Bearer ${token}`, Accept: "application/json" } }
        )
        if (!res.ok) return null
        const rows = await res.json()
        return Array.isArray(rows) && rows[0] ? rows[0] : null
    } catch (e) {
        return null
    }
}

async function markWithdrawn(
    url: string, anon: string, token: string, table: string, userId: string
): Promise<boolean> {
    if (!url || !anon || !token || !userId) return false
    try {
        const res = await fetch(`${url}/rest/v1/${table}?id=eq.${userId}`, {
            method: "PATCH",
            headers: {
                apikey: anon,
                Authorization: `Bearer ${token}`,
                "Content-Type": "application/json",
                Prefer: "return=minimal",
            },
            body: JSON.stringify({ status: "withdrawn" }),
        })
        return res.ok
    } catch (e) {
        return false
    }
}

async function serverLogout(url: string, anon: string, token: string) {
    if (!url || !anon || !token) return
    try {
        await fetch(`${url}/auth/v1/logout`, {
            method: "POST",
            headers: { apikey: anon, Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        })
    } catch (e) {
        /* 네트워크 실패해도 로컬 세션은 비움 */
    }
}

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

/* ─── 토스식 흉상 아바타 (머리 원 + 어깨 라운드) ─── */
function BustAvatar(props: { size: number; color: string }) {
    const size = props.size
    const color = props.color
    return (
        <svg width={size} height={size} viewBox="0 0 48 48" fill="none" aria-hidden="true">
            <circle cx="24" cy="17" r="8.5" fill={color} />
            <path
                d="M9 41c0-8.3 6.7-14 15-14s15 5.7 15 14a1.5 1.5 0 0 1-1.5 1.5h-27A1.5 1.5 0 0 1 9 41Z"
                fill={color}
            />
        </svg>
    )
}

function statusMeta(status: string, C: typeof LIGHT): { label: string; fg: string; bg: string } {
    if (status === "approved") return { label: "승인 완료", fg: C.green, bg: C.greenSoft }
    if (status === "withdrawn") return { label: "탈퇴 처리됨", fg: C.faint, bg: C.line }
    if (status === "pending") return { label: "AlphaNest 회원", fg: C.violet, bg: C.violetSoft }
    return { label: status || "—", fg: C.sub, bg: C.field }
}

function fmtDate(v: string): string {
    if (!v) return "—"
    try {
        const d = new Date(v)
        if (isNaN(d.getTime())) return "—"
        return d.toLocaleDateString("ko-KR", { year: "numeric", month: "long", day: "numeric" })
    } catch (e) {
        return "—"
    }
}

interface Props {
    supabaseUrl: string
    supabaseAnonKey: string
    profileTable: string
    redirectUrl: string
    logoutRedirect: string
    dark: boolean
    termsUrl?: string
    privacyUrl?: string
}

type Busy = "" | "logout" | "withdraw"

export default function PublicProfilePage(props: Props) {
    const supabaseUrl = (props.supabaseUrl || DEFAULT_SUPABASE_URL).replace(/\/+$/, "")
    const anonKey = props.supabaseAnonKey || DEFAULT_SUPABASE_ANON_KEY
    const profileTable = props.profileTable || "profiles"
    const logoutRedirect = (props.logoutRedirect || "").trim() // 비우면 제자리에서 로그인 폼으로 전환

    const isCanvas = RenderTarget.current() === RenderTarget.canvas

    const [dark, setDark] = useState<boolean>(!!props.dark)
    const [checked, setChecked] = useState<boolean>(isCanvas)
    const [session, setSession] = useState<SupaSession | null>(null)
    const [profile, setProfile] = useState<Profile | null>(isCanvas ? SAMPLE : null)
    const [confirming, setConfirming] = useState(false)
    const [busy, setBusy] = useState<Busy>("")

    // 로그인 폼 상태
    const [mode, setMode] = useState<"login" | "signup">("login")
    const [email, setEmail] = useState("")
    const [password, setPassword] = useState("")
    const [displayName, setDisplayName] = useState("")
    const [agreed, setAgreed] = useState(false)
    const [formBusy, setFormBusy] = useState(false)
    const [err, setErr] = useState("")
    const [ok, setOk] = useState("")

    const C = dark ? DARK : LIGHT

    /* 사이트 테마 추종: body[data-framer-theme] 읽기 + 변경 감지 (캔버스는 props.dark 정적 프리뷰) */
    useEffect(() => {
        if (isCanvas) return
        const read = () => {
            const t = (typeof document !== "undefined" && document.body) ? document.body.dataset.framerTheme : ""
            setDark(t === "dark")
        }
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [isCanvas])

    /* 마운트: OAuth #access_token 해시 소비 + 세션 로드 + 토큰 갱신 + 타 컴포넌트 이벤트 구독 */
    useEffect(() => {
        if (isCanvas || typeof window === "undefined") return
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
                const ures = await fetch(`${supabaseUrl}/auth/v1/user`, { headers: { apikey: anonKey, Authorization: `Bearer ${at}` } })
                const u = await ures.json().catch(() => null)
                if (!ures.ok || !u || !u.id) { if (alive) setErr("로그인 처리 실패 — 다시 시도해주세요"); return false }
                const s: SupaSession = { access_token: at, refresh_token: rt, expires_at, user: { id: u.id, email: u.email, created_at: u.created_at, user_metadata: u.user_metadata } }
                saveSession(s)
                await ensureProfile(supabaseUrl, anonKey, at, u.id, u.email || "", u.user_metadata?.name || u.user_metadata?.full_name || "", true)
                try { window.history.replaceState(null, "", window.location.pathname + window.location.search) } catch (e) { /* no-op */ }
                if (alive) { setSession(s); emitAuthChange() }
                afterLoginNavigate()
                return true
            } catch (e) {
                if (alive) setErr("로그인 처리 실패")
                return false
            }
        }

        const init = async () => {
            const consumed = await consumeHash()
            if (!consumed) {
                let s = loadSession()
                if (s && s.refresh_token && s.expires_at && Date.now() / 1000 > s.expires_at - 300) {
                    const refreshed = await refreshSessionCall(supabaseUrl, anonKey, s.refresh_token)
                    if (refreshed) s = refreshed
                }
                if (alive) setSession(s)
            }
            if (alive) setChecked(true)
        }
        init()

        const onAuth = () => { if (alive) setSession(loadSession()) }
        window.addEventListener(AUTH_EVENT, onAuth)
        window.addEventListener("storage", onAuth)

        const timer = setInterval(async () => {
            const cur = loadSession()
            if (cur && cur.refresh_token && cur.expires_at && Date.now() / 1000 > cur.expires_at - 300) {
                const r = await refreshSessionCall(supabaseUrl, anonKey, cur.refresh_token)
                if (alive && r) setSession(r)
            }
        }, 60000)

        return () => { alive = false; window.removeEventListener(AUTH_EVENT, onAuth); window.removeEventListener("storage", onAuth); clearInterval(timer) }
    }, [isCanvas, supabaseUrl, anonKey])

    /* 세션 확정 시 프로필 보강 */
    useEffect(() => {
        if (isCanvas) return
        if (!session || !session.user) { setProfile(null); return }
        const meta = (session.user.user_metadata) || {}
        const base: Profile = {
            display_name: meta.name || meta.full_name || (session.user.email || "").split("@")[0] || "사용자",
            email: session.user.email || meta.email || "",
            phone: meta.phone || "",
            status: "",
            created_at: session.user.created_at || meta.created_at || "",
        }
        setProfile(base)
        if (!session.access_token) return
        let alive = true
        fetchProfile(supabaseUrl, anonKey, session.access_token, profileTable, session.user.id).then((row) => {
            if (!alive || !row) return
            setProfile({
                display_name: row.display_name || base.display_name,
                email: row.email || base.email,
                phone: row.phone || base.phone,
                status: row.status || base.status,
                created_at: row.created_at || base.created_at,
            })
        })
        return () => { alive = false }
    }, [isCanvas, session, supabaseUrl, anonKey, profileTable])

    /* ─── 로그인 폼 액션 ─── */
    const submit = useCallback(async () => {
        if (formBusy) return
        setErr(""); setOk("")
        if (!email.trim() || !password) { setErr("이메일과 비밀번호를 입력해주세요"); return }
        if (password.length < 6) { setErr("비밀번호는 6자 이상 입력해주세요"); return }
        if (mode === "signup" && !agreed) { setErr("이용약관·개인정보처리방침(국외이전 포함) 동의가 필요합니다"); return }
        setFormBusy(true)
        try {
            if (mode === "signup") {
                const { session: s, needConfirm } = await signUpEmail(supabaseUrl, anonKey, email.trim(), password, displayName.trim(), agreed)
                if (needConfirm || !s) {
                    setOk("인증 메일을 보냈어요. 메일의 링크를 누른 뒤 로그인해주세요.")
                    setPassword("")
                    setMode("login")
                } else {
                    setSession(s); emitAuthChange(); setPassword("")
                    afterLoginNavigate() // ?next= 없으면 제자리에서 내정보 전환
                }
            } else {
                const s = await signInEmail(supabaseUrl, anonKey, email.trim(), password)
                setSession(s); emitAuthChange(); setPassword("")
                afterLoginNavigate()
            }
        } catch (e: any) {
            setErr(humanError(e?.message || ""))
        } finally {
            setFormBusy(false)
        }
    }, [formBusy, mode, email, password, displayName, agreed, supabaseUrl, anonKey])

    const googleLogin = () => {
        if (formBusy) return
        // 약관 동의는 회원가입 탭에서만 노출 → 구글도 회원가입 탭일 때만 동의 강제(로그인 탭=기존 회원 재방문)
        if (mode === "signup" && !agreed) { setErr("이용약관·개인정보처리방침(국외이전 포함) 동의가 필요합니다"); return }
        setErr("")
        setFormBusy(true)
        const back = (props.redirectUrl || "").trim() || (typeof window !== "undefined" ? window.location.origin + window.location.pathname : "")
        if (typeof window !== "undefined") window.location.href = getGoogleOAuthUrl(supabaseUrl, back, anonKey)
    }

    /* ─── 내정보 액션 ─── */
    const settle = () => {
        clearSession()
        setSession(null)
        setConfirming(false)
        setBusy("")
        setMode("login"); setPassword(""); setErr(""); setOk("")
        emitAuthChange()
        if (logoutRedirect && typeof window !== "undefined") window.location.assign(logoutRedirect)
    }

    const handleLogout = async () => {
        if (busy) return
        setBusy("logout")
        const s = loadSession()
        if (s && s.access_token) await serverLogout(supabaseUrl, anonKey, s.access_token)
        settle()
    }

    const handleWithdraw = async () => {
        if (busy) return
        setBusy("withdraw")
        const s = loadSession()
        if (s && s.access_token && s.user) {
            await markWithdrawn(supabaseUrl, anonKey, s.access_token, profileTable, s.user.id)
            await serverLogout(supabaseUrl, anonKey, s.access_token)
        }
        settle()
    }

    /* ─── 스타일 ─── */
    const wrap: React.CSSProperties = {
        width: "100%",
        minHeight: "100vh",
        background: C.bg,
        fontFamily: FONT,
        color: C.ink,
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        padding: "40px 20px 64px",
        boxSizing: "border-box",
    }
    const cardStyle: React.CSSProperties = {
        width: "100%",
        maxWidth: 460,
        background: C.card,
        border: `1px solid ${C.line}`,
        borderRadius: 22,
        boxShadow: "0 2px 16px rgba(0,0,0,0.06)",
        padding: 28,
        boxSizing: "border-box",
    }
    const inputStyle: React.CSSProperties = {
        width: "100%", padding: "11px 13px", borderRadius: 11, border: `1.5px solid ${C.line}`,
        background: C.field, color: C.ink, fontSize: 13.5, fontFamily: FONT, outline: "none", boxSizing: "border-box",
    }

    if (!checked) {
        return (
            <div style={wrap}>
                <div style={{ ...cardStyle, textAlign: "center", color: C.faint, fontSize: 13, fontWeight: 600 }}>
                    불러오는 중...
                </div>
            </div>
        )
    }

    /* ─── 미로그인 = 로그인/회원가입 폼 (제자리) ─── */
    if (!session || !session.user) {
        return (
            <div style={wrap}>
                <div style={{ ...cardStyle, maxWidth: 400 }}>
                    {/* 브랜드 lockup */}
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, marginBottom: 24 }}>
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
                                    style={{ flex: 1, border: "none", padding: "8px 0", borderRadius: 9, cursor: "pointer", fontFamily: FONT, fontSize: 13, fontWeight: 700, background: active ? C.card : "transparent", color: active ? C.violet : C.sub, boxShadow: active ? "0 1px 3px rgba(0,0,0,0.10)" : "none" }}>
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
                            <input type="checkbox" checked={agreed} onChange={(e) => { setAgreed(e.target.checked); if (e.target.checked) setErr("") }} style={{ marginTop: 1, accentColor: C.violet, cursor: "pointer", flexShrink: 0 }} />
                            <span>
                                {props.termsUrl ? <a href={props.termsUrl} target="_blank" rel="noopener noreferrer" style={{ color: C.violet, textDecoration: "underline" }}>이용약관</a> : "이용약관"}
                                {" · "}
                                {props.privacyUrl ? <a href={props.privacyUrl} target="_blank" rel="noopener noreferrer" style={{ color: C.violet, textDecoration: "underline" }}>개인정보처리방침</a> : "개인정보처리방침"}
                                {" 및 회원정보 국외 이전(미국)에 동의합니다 "}
                                <span style={{ color: C.faint }}>(필수)</span>
                            </span>
                        </label>
                    )}

                    {err && <div style={{ marginTop: 12, fontSize: 11.5, color: C.red, fontWeight: 700, lineHeight: 1.5 }}>{err}</div>}
                    {ok && <div style={{ marginTop: 12, fontSize: 11.5, color: C.ok, fontWeight: 700, lineHeight: 1.5 }}>{ok}</div>}

                    <button onClick={submit} disabled={formBusy}
                        style={{ width: "100%", marginTop: 16, padding: "13px 0", border: "none", borderRadius: 12, cursor: formBusy ? "default" : "pointer", fontFamily: FONT, fontSize: 14, fontWeight: 800, background: C.violet, color: "#ffffff", opacity: formBusy ? 0.6 : 1 }}>
                        {formBusy ? "처리 중…" : mode === "login" ? "로그인" : "회원가입"}
                    </button>

                    {/* 구분선 */}
                    <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "16px 0" }}>
                        <div style={{ flex: 1, height: 1, background: C.line }} />
                        <span style={{ fontSize: 11, color: C.faint, fontWeight: 600 }}>또는</span>
                        <div style={{ flex: 1, height: 1, background: C.line }} />
                    </div>

                    <button onClick={googleLogin} disabled={formBusy}
                        style={{ width: "100%", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 9, border: `1.5px solid ${C.line}`, background: C.card, color: C.ink, cursor: formBusy ? "default" : "pointer", fontFamily: FONT, fontSize: 13.5, fontWeight: 700, padding: "11px 16px", borderRadius: 12, opacity: formBusy ? 0.6 : 1 }}>
                        <GoogleG size={18} />
                        Google로 계속하기
                    </button>

                    <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 16, lineHeight: 1.5, textAlign: "center" }}>AlphaNest 계정은 공개 터미널 전용입니다</div>
                </div>
            </div>
        )
    }

    /* ─── 로그인 = 내정보 ─── */
    const name = profile ? profile.display_name : "사용자"
    const sm = statusMeta(profile ? profile.status : "", C)

    return (
        <div style={wrap}>
            <div style={cardStyle}>
                {/* 헤더: 큰 아바타 + 이름 + 이메일 + 상태 */}
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center" }}>
                    <div style={{ width: 80, height: 80, borderRadius: 26, background: C.field, display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 14 }}>
                        <BustAvatar size={50} color={C.sub} />
                    </div>
                    <div style={{ color: C.ink, fontSize: 20, fontWeight: 800, letterSpacing: -0.4 }}>{name}</div>
                    <div style={{ color: C.faint, fontSize: 12.5, fontFamily: FONT_MONO, marginTop: 4 }}>
                        {profile ? profile.email : ""}
                    </div>
                    <span style={{ marginTop: 12, display: "inline-flex", alignItems: "center", padding: "4px 12px", borderRadius: 999, background: sm.bg, color: sm.fg, fontSize: 11.5, fontWeight: 700 }}>
                        {sm.label}
                    </span>
                </div>

                {/* 가입 정보 */}
                <div style={{ marginTop: 22, borderTop: `1px solid ${C.line}`, paddingTop: 4 }}>
                    <InfoRow C={C} label="전화번호" value={profile && profile.phone ? profile.phone : "—"} mono />
                    <InfoRow C={C} label="가입일" value={fmtDate(profile ? profile.created_at : "")} />
                </div>

                {/* 액션 */}
                {!confirming ? (
                    <div style={{ marginTop: 22, display: "flex", flexDirection: "column", gap: 10 }}>
                        <button type="button" onClick={handleLogout} disabled={busy !== ""} style={btnSolid(C, busy === "logout")}>
                            {busy === "logout" ? "로그아웃 중..." : "로그아웃"}
                        </button>
                        <button type="button" onClick={() => setConfirming(true)} disabled={busy !== ""} style={btnGhostDanger(C)}>
                            회원 탈퇴
                        </button>
                    </div>
                ) : (
                    <div style={{ marginTop: 22, background: C.redSoft, border: `1px solid ${C.red}`, borderRadius: 16, padding: 16 }}>
                        <div style={{ color: C.ink, fontSize: 14, fontWeight: 800 }}>정말 탈퇴할까요?</div>
                        <div style={{ color: C.sub, fontSize: 12.5, lineHeight: 1.5, marginTop: 6 }}>
                            탈퇴 시 계정이 비활성화되고 다시 로그인할 수 없어요. 관리자 확인 후 정보가 삭제돼요.
                        </div>
                        <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
                            <button type="button" onClick={() => setConfirming(false)} disabled={busy !== ""} style={btnFlatHalf(C)}>
                                취소
                            </button>
                            <button type="button" onClick={handleWithdraw} disabled={busy !== ""} style={btnDangerHalf(C, busy === "withdraw")}>
                                {busy === "withdraw" ? "처리 중..." : "탈퇴하기"}
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    )
}

function InfoRow(props: { C: typeof LIGHT; label: string; value: string; mono?: boolean }) {
    const C = props.C
    return (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 0", borderBottom: `1px solid ${C.line}` }}>
            <span style={{ color: C.faint, fontSize: 12.5 }}>{props.label}</span>
            <span style={{ color: C.ink, fontSize: 13.5, fontWeight: 600, fontFamily: props.mono ? FONT_MONO : FONT, fontVariantNumeric: "tabular-nums" }}>
                {props.value}
            </span>
        </div>
    )
}

function btnSolid(C: typeof LIGHT, loading: boolean): React.CSSProperties {
    return {
        width: "100%", padding: "13px 0", marginTop: 14, border: "none", borderRadius: 14,
        background: C.violet, color: "#fff", fontSize: 14.5, fontWeight: 800, fontFamily: FONT, // 브랜드 보라 (PM 2026-07-04)
        cursor: loading ? "wait" : "pointer", opacity: loading ? 0.6 : 1,
    }
}

function btnGhostDanger(C: typeof LIGHT): React.CSSProperties {
    return {
        width: "100%", padding: "12px 0", border: "none", borderRadius: 14,
        background: "transparent", color: C.red, fontSize: 13.5, fontWeight: 700, fontFamily: FONT, cursor: "pointer",
    }
}

function btnFlatHalf(C: typeof LIGHT): React.CSSProperties {
    return {
        flex: 1, padding: "11px 0", border: `1px solid ${C.line}`, borderRadius: 12,
        background: C.card, color: C.sub, fontSize: 13.5, fontWeight: 700, fontFamily: FONT, cursor: "pointer",
    }
}

function btnDangerHalf(C: typeof LIGHT, loading: boolean): React.CSSProperties {
    return {
        flex: 1, padding: "11px 0", border: "none", borderRadius: 12,
        background: C.red, color: "#ffffff", fontSize: 13.5, fontWeight: 800, fontFamily: FONT,
        cursor: loading ? "wait" : "pointer", opacity: loading ? 0.6 : 1,
    }
}

addPropertyControls(PublicProfilePage, {
    supabaseUrl: { type: ControlType.String, title: "Supabase URL", defaultValue: DEFAULT_SUPABASE_URL },
    supabaseAnonKey: { type: ControlType.String, title: "Supabase Anon Key", defaultValue: "", placeholder: "비우면 내장 공개 anon key" },
    profileTable: { type: ControlType.String, title: "프로필 테이블", defaultValue: "profiles" },
    redirectUrl: { type: ControlType.String, title: "OAuth Redirect URL", defaultValue: "", placeholder: "구글 복귀 URL (비우면 현재 페이지)" },
    logoutRedirect: { type: ControlType.String, title: "로그아웃 후 이동", defaultValue: "", placeholder: "비우면 제자리에서 로그인 폼" },
    dark: { type: ControlType.Boolean, title: "Dark (정적)", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
    termsUrl: { type: ControlType.String, title: "이용약관 URL", defaultValue: "/policy" },
    privacyUrl: { type: ControlType.String, title: "개인정보처리방침 URL", defaultValue: "/policy" },
})
