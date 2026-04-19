import { addPropertyControls, ControlType } from "framer"
import React, { useState, useEffect, useCallback } from "react"

/*
 * VERITY Auth Page — Supabase GoTrue REST API 직접 호출
 *
 * Framer 단일 파일 컴포넌트로, 외부 패키지 없이 Supabase Auth를 구현합니다.
 * Supabase 프로젝트 URL + anon key만 Framer property로 전달하면 동작합니다.
 *
 * 기능: 이메일 회원가입, 이메일 로그인, Google OAuth, 로그아웃, 세션 유지
 * 세션은 localStorage에 저장되며, 다른 VERITY 컴포넌트에서 getVeritySession()으로 읽습니다.
 */

/* ─── Design tokens ─── */
const FONT = "'Inter', 'Pretendard', -apple-system, sans-serif"
const C = {
    bg: "#000", card: "#111", cardAlt: "#0A0A0A", border: "#1A1A1A",
    border2: "#222", accent: "#B5FF19", positive: "#22C55E", negative: "#EF4444",
    warning: "#F59E0B", muted: "#888", mutedLight: "#555", white: "#fff",
}

/* ─── Supabase GoTrue REST helpers ─── */
const SESSION_KEY = "verity_supabase_session"

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

async function supaFetch(url: string, supabaseUrl: string, anonKey: string, opts: RequestInit = {}): Promise<any> {
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

type ProfileStatus = "pending" | "approved" | "rejected" | "missing"

/**
 * profiles 테이블에서 status 조회.
 * RLS 정책상 본인 row만 조회 가능하므로 access_token 필요.
 */
async function fetchProfileStatus(supabaseUrl: string, anonKey: string, accessToken: string, userId: string): Promise<ProfileStatus> {
    try {
        const res = await fetch(`${supabaseUrl}/rest/v1/profiles?id=eq.${userId}&select=status`, {
            headers: {
                apikey: anonKey,
                Authorization: `Bearer ${accessToken}`,
                Accept: "application/json",
            },
        })
        if (!res.ok) return "missing"
        const rows = await res.json()
        if (!Array.isArray(rows) || rows.length === 0) return "missing"
        const st = rows[0]?.status
        if (st === "approved" || st === "pending" || st === "rejected") return st
        return "missing"
    } catch {
        return "missing"
    }
}

/**
 * profile이 없을 때 pending 상태로 생성 (trigger fallback).
 * 정상 설치된 프로젝트는 trigger가 자동 insert하므로 이 함수는 거의 no-op.
 */
async function ensureProfile(
    supabaseUrl: string, anonKey: string, accessToken: string,
    userId: string, email: string, displayName: string,
    extras?: { phone: string; consent: boolean }
): Promise<void> {
    try {
        const payload: Record<string, any> = {
            id: userId,
            email,
            display_name: displayName || email.split("@")[0],
            status: "pending",
        }
        if (extras) {
            if (extras.phone) payload.phone = extras.phone
            if (extras.consent) payload.consent_given_at = new Date().toISOString()
        }
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

interface SignUpExtras {
    phone: string
    consent: boolean
}

/**
 * 회원가입.
 * 성공 시 access_token이 있어도 profiles.status='pending'이므로 세션을 저장하지 않고
 * 'pending' 플래그를 던짐. UI에서 '승인 대기' 안내 후 강제 로그아웃 상태로 돌아감.
 */
async function signUp(supabaseUrl: string, anonKey: string, email: string, password: string, displayName: string, extras: SignUpExtras): Promise<{ result: "pending" | "email_confirm"; userId?: string }> {
    const body = await supaFetch(`${supabaseUrl}/auth/v1/signup`, supabaseUrl, anonKey, {
        method: "POST",
        body: JSON.stringify({
            email,
            password,
            data: {
                name: displayName || email.split("@")[0],
                phone: extras.phone,
                consent: extras.consent,
            },
        }),
    })

    const userId: string | undefined = body.user?.id || body.id
    const accessToken: string | undefined = body.access_token

    // Confirm email ON → access_token 없음. trigger는 이미 profile을 만들었을 것.
    if (!accessToken) {
        return { result: "email_confirm", userId }
    }

    // Confirm email OFF → 즉시 access_token 받음. trigger fallback으로 profile 확인/생성.
    if (userId) {
        await ensureProfile(supabaseUrl, anonKey, accessToken, userId, email, displayName, extras)
    }
    // 승인되지 않았으므로 세션은 절대 저장하지 않는다.
    clearSession()
    return { result: "pending", userId }
}

/**
 * 로그인.
 * auth 성공 후 profiles.status 체크. approved만 세션 저장, 그 외는 거부.
 */
async function signIn(supabaseUrl: string, anonKey: string, email: string, password: string): Promise<SupaSession> {
    const body = await supaFetch(`${supabaseUrl}/auth/v1/token?grant_type=password`, supabaseUrl, anonKey, {
        method: "POST",
        body: JSON.stringify({ email, password }),
    })
    const session: SupaSession = {
        access_token: body.access_token,
        refresh_token: body.refresh_token,
        expires_at: body.expires_at || (Date.now() / 1000 + 3600),
        user: body.user,
    }

    // 승인 상태 체크
    const status = await fetchProfileStatus(supabaseUrl, anonKey, session.access_token, session.user.id)

    if (status === "approved") {
        saveSession(session)
        return session
    }

    if (status === "missing") {
        // 레거시 계정이거나 trigger 실패. pending으로 프로필 생성하고 거부.
        await ensureProfile(supabaseUrl, anonKey, session.access_token, session.user.id, email, session.user.user_metadata?.name || "")
        clearSession()
        throw new Error("관리자 승인 대기 중입니다. 승인 후 다시 로그인해주세요.")
    }

    clearSession()
    if (status === "rejected") {
        throw new Error("가입이 거절되었습니다. 관리자에게 문의해주세요.")
    }
    throw new Error("관리자 승인 대기 중입니다. 승인 후 다시 로그인해주세요.")
}

async function signOut(supabaseUrl: string, anonKey: string, accessToken: string) {
    await fetch(`${supabaseUrl}/auth/v1/logout`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            apikey: anonKey,
            Authorization: `Bearer ${accessToken}`,
        },
    }).catch(() => {})
    clearSession()
}

async function refreshSession(supabaseUrl: string, anonKey: string, refreshToken: string): Promise<SupaSession | null> {
    try {
        const body = await supaFetch(`${supabaseUrl}/auth/v1/token?grant_type=refresh_token`, supabaseUrl, anonKey, {
            method: "POST",
            body: JSON.stringify({ refresh_token: refreshToken }),
        })
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

function getGoogleOAuthUrl(supabaseUrl: string, redirectTo: string): string {
    return `${supabaseUrl}/auth/v1/authorize?provider=google&redirect_to=${encodeURIComponent(redirectTo)}`
}

/* ─── Props ─── */
interface Props {
    supabaseUrl: string
    supabaseAnonKey: string
    redirectUrl: string
    defaultNextPath: string
    enableGoogle: boolean
    onAuthChange?: (session: SupaSession | null) => void
}

/** 로그인 성공 후 이동할 경로 결정 (?next= 파라미터 우선, 없으면 defaultNextPath). */
function resolveNextPath(defaultNextPath: string): string {
    if (typeof window === "undefined") return defaultNextPath || "/"
    try {
        const p = new URLSearchParams(window.location.search).get("next")
        if (p && p.startsWith("/")) return p
    } catch { /* ignore */ }
    return defaultNextPath || "/"
}

/* ─── Main Component ─── */
export default function AuthPage(props: Props) {
    const { supabaseUrl, supabaseAnonKey, redirectUrl, defaultNextPath = "/", enableGoogle = true, onAuthChange } = props
    const [mode, setMode] = useState<"login" | "signup">("login")
    const [session, setSession] = useState<SupaSession | null>(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState("")
    const [success, setSuccess] = useState("")

    const [email, setEmail] = useState("")
    const [password, setPassword] = useState("")
    const [displayName, setDisplayName] = useState("")
    const [phone, setPhone] = useState("")
    const [consent, setConsent] = useState(false)

    useEffect(() => {
        const s = loadSession()
        if (s) {
            if (s.expires_at && Date.now() / 1000 > s.expires_at - 300) {
                refreshSession(supabaseUrl, supabaseAnonKey, s.refresh_token).then((ns) => {
                    setSession(ns)
                    onAuthChange?.(ns)
                    // 이미 로그인 되어 있으면 next 경로로 자동 이동
                    if (ns && typeof window !== "undefined") {
                        const next = resolveNextPath(defaultNextPath)
                        if (next && next !== window.location.pathname) window.location.href = next
                    }
                })
            } else {
                setSession(s)
                onAuthChange?.(s)
                if (typeof window !== "undefined") {
                    const next = resolveNextPath(defaultNextPath)
                    if (next && next !== window.location.pathname) window.location.href = next
                }
            }
        }

        if (typeof window !== "undefined") {
            const hash = window.location.hash
            if (hash.includes("access_token=")) {
                const params = new URLSearchParams(hash.replace("#", ""))
                const at = params.get("access_token")
                const rt = params.get("refresh_token")
                const exp = params.get("expires_at") || params.get("expires_in")
                if (at) {
                    const oauthSession: SupaSession = {
                        access_token: at,
                        refresh_token: rt || "",
                        expires_at: Number(exp) > 1e9 ? Number(exp) : Date.now() / 1000 + Number(exp || 3600),
                        user: { id: "", email: "" },
                    }
                    window.history.replaceState(null, "", window.location.pathname)
                    fetch(`${supabaseUrl}/auth/v1/user`, {
                        headers: { apikey: supabaseAnonKey, Authorization: `Bearer ${at}` },
                    })
                        .then((r) => r.json())
                        .then(async (u) => {
                            oauthSession.user = u
                            // OAuth 후에도 profile status 체크
                            const status = await fetchProfileStatus(supabaseUrl, supabaseAnonKey, at, u.id)
                            if (status === "approved") {
                                saveSession(oauthSession)
                                setSession(oauthSession)
                                onAuthChange?.(oauthSession)
                                if (typeof window !== "undefined") {
                                    const next = resolveNextPath(defaultNextPath)
                                    window.location.href = next
                                }
                                return
                            }
                            if (status === "missing") {
                                await ensureProfile(supabaseUrl, supabaseAnonKey, at, u.id, u.email, u.user_metadata?.name || u.user_metadata?.full_name || "")
                            }
                            clearSession()
                            setSession(null)
                            onAuthChange?.(null)
                            setError(status === "rejected"
                                ? "가입이 거절되었습니다. 관리자에게 문의해주세요."
                                : "관리자 승인 대기 중입니다. 승인 후 다시 로그인해주세요.")
                        })
                        .catch(() => {})
                }
            }
        }
    }, [supabaseUrl, supabaseAnonKey])

    const handleSubmit = useCallback(async () => {
        if (!supabaseUrl || !supabaseAnonKey) {
            setError("Supabase URL과 Anon Key를 설정해주세요")
            return
        }
        if (password.length < 6) {
            setError("비밀번호는 6자 이상 입력해주세요")
            return
        }
        if (mode === "signup") {
            if (!phone.trim()) { setError("전화번호를 입력해주세요"); return }
            if (!consent) { setError("개인정보 수집·이용에 동의해주세요"); return }
        }
        setLoading(true)
        setError("")
        setSuccess("")
        try {
            if (mode === "signup") {
                const { result } = await signUp(supabaseUrl, supabaseAnonKey, email, password, displayName, {
                    phone: phone.trim(), consent,
                })
                if (result === "email_confirm") {
                    setSuccess("가입 요청이 접수되었습니다. 이메일 확인 후 관리자 승인을 기다려주세요.")
                } else {
                    setSuccess("가입 신청이 접수되었습니다. 관리자 승인 후 로그인 가능합니다.")
                }
                setPassword("")
                setPhone("")
                setConsent(false)
                setMode("login")
            } else {
                const s = await signIn(supabaseUrl, supabaseAnonKey, email, password)
                setSession(s)
                onAuthChange?.(s)
                if (typeof window !== "undefined") {
                    const next = resolveNextPath(defaultNextPath)
                    window.location.href = next
                }
            }
        } catch (e: any) {
            setError(e.message || "오류가 발생했습니다")
        } finally {
            setLoading(false)
        }
    }, [mode, email, password, displayName, phone, consent, supabaseUrl, supabaseAnonKey, onAuthChange])

    const handleLogout = useCallback(async () => {
        if (session) await signOut(supabaseUrl, supabaseAnonKey, session.access_token)
        setSession(null)
        onAuthChange?.(null)
    }, [session, supabaseUrl, supabaseAnonKey, onAuthChange])

    /* ─── Logged-in view ─── */
    if (session) {
        const user = session.user
        const name = user.user_metadata?.name || user.email?.split("@")[0] || "사용자"
        return (
            <div style={containerStyle}>
                <div style={cardStyle}>
                    {/* Avatar */}
                    <div style={{
                        width: 64, height: 64, borderRadius: "50%", background: `${C.accent}20`,
                        border: `2px solid ${C.accent}`, display: "flex", alignItems: "center",
                        justifyContent: "center", margin: "0 auto 16px",
                    }}>
                        <span style={{ color: C.accent, fontSize: 24, fontWeight: 800, fontFamily: FONT }}>
                            {name.charAt(0).toUpperCase()}
                        </span>
                    </div>
                    <div style={{ textAlign: "center", marginBottom: 20 }}>
                        <div style={{ color: C.white, fontSize: 18, fontWeight: 800, fontFamily: FONT }}>{name}</div>
                        <div style={{ color: C.muted, fontSize: 12, fontFamily: FONT, marginTop: 4 }}>{user.email}</div>
                    </div>

                    {/* Stats placeholder */}
                    <div style={{
                        display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20,
                    }}>
                        <div style={statBox}>
                            <div style={{ color: C.mutedLight, fontSize: 10, fontFamily: FONT }}>가입일</div>
                            <div style={{ color: C.white, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>
                                {user.user_metadata?.created_at
                                    ? new Date(user.user_metadata.created_at).toLocaleDateString("ko-KR")
                                    : "—"}
                            </div>
                        </div>
                        <div style={statBox}>
                            <div style={{ color: C.mutedLight, fontSize: 10, fontFamily: FONT }}>멤버십</div>
                            <div style={{ color: C.accent, fontSize: 12, fontWeight: 700, fontFamily: FONT }}>VERITY Free</div>
                        </div>
                    </div>

                    <button onClick={handleLogout} style={logoutBtnStyle}>로그아웃</button>
                </div>
            </div>
        )
    }

    /* ─── Auth form ─── */
    return (
        <div style={containerStyle}>
            <div style={cardStyle}>
                {/* Logo */}
                <div style={{ textAlign: "center", marginBottom: 28 }}>
                    <div style={{ color: C.accent, fontSize: 28, fontWeight: 900, fontFamily: FONT, letterSpacing: "-0.03em" }}>
                        VERITY
                    </div>
                    <div style={{ color: C.muted, fontSize: 12, fontFamily: FONT, marginTop: 4 }}>
                        AI 자산 보안 비서
                    </div>
                </div>

                {/* Tab toggle */}
                <div style={{ display: "flex", gap: 0, marginBottom: 16, borderRadius: 12, overflow: "hidden", border: `1px solid ${C.border2}` }}>
                    {(["login", "signup"] as const).map((m) => (
                        <button key={m} onClick={() => { setMode(m); setError(""); setSuccess("") }} style={{
                            flex: 1, border: "none", padding: "10px 0",
                            background: mode === m ? C.accent : C.cardAlt,
                            color: mode === m ? "#000" : C.muted,
                            fontSize: 13, fontWeight: 700, fontFamily: FONT, cursor: "pointer",
                            transition: "all 0.2s",
                        }}>
                            {m === "login" ? "로그인" : "가입 신청"}
                        </button>
                    ))}
                </div>

                {/* 승인제 안내 (signup 모드) */}
                {mode === "signup" && (
                    <div style={{
                        padding: "10px 12px", borderRadius: 10, marginBottom: 18,
                        background: `${C.accent}10`, border: `1px solid ${C.accent}25`,
                    }}>
                        <div style={{ color: C.accent, fontSize: 11, fontWeight: 700, fontFamily: FONT, marginBottom: 2 }}>
                            승인제 가입
                        </div>
                        <div style={{ color: C.muted, fontSize: 11, fontFamily: FONT, lineHeight: 1.5 }}>
                            가입 신청 후 관리자 승인이 완료되어야 로그인할 수 있습니다.
                        </div>
                    </div>
                )}

                {/* Fields */}
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    {mode === "signup" && (
                        <input
                            type="text"
                            placeholder="이름"
                            value={displayName}
                            onChange={(e) => setDisplayName(e.target.value)}
                            style={inputStyle}
                        />
                    )}
                    <input
                        type="email"
                        placeholder="이메일"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
                        style={inputStyle}
                    />
                    <input
                        type="password"
                        placeholder="비밀번호 (6자 이상)"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
                        style={inputStyle}
                    />
                    {mode === "signup" && (
                        <>
                            <input
                                type="tel"
                                placeholder="전화번호 (예: 010-1234-5678)"
                                value={phone}
                                onChange={(e) => setPhone(e.target.value)}
                                style={inputStyle}
                            />

                            {/* 개인정보 동의 */}
                            <label style={{
                                display: "flex", alignItems: "flex-start", gap: 10, cursor: "pointer",
                                padding: "10px 12px", borderRadius: 10,
                                background: C.cardAlt, border: `1px solid ${consent ? C.accent : C.border2}`,
                                transition: "border-color 0.2s",
                            }}>
                                <input
                                    type="checkbox"
                                    checked={consent}
                                    onChange={(e) => setConsent(e.target.checked)}
                                    style={{
                                        marginTop: 2, width: 16, height: 16, accentColor: C.accent as string,
                                        cursor: "pointer", flexShrink: 0,
                                    }}
                                />
                                <div style={{ flex: 1 }}>
                                    <div style={{ color: C.white, fontSize: 12, fontWeight: 700, fontFamily: FONT, marginBottom: 3 }}>
                                        개인정보 수집·이용 동의 (필수)
                                    </div>
                                    <div style={{ color: C.muted, fontSize: 10, fontFamily: FONT, lineHeight: 1.5 }}>
                                        수집 항목: 이메일, 이름, 전화번호<br />
                                        이용 목적: 회원 식별, 서비스 제공, 관리자 승인<br />
                                        보유 기간: 회원 탈퇴 시까지
                                    </div>
                                </div>
                            </label>
                        </>
                    )}
                </div>

                {/* Error / Success */}
                {error && (
                    <div style={{ marginTop: 10, padding: "8px 12px", borderRadius: 8, background: `${C.negative}15`, border: `1px solid ${C.negative}30` }}>
                        <span style={{ color: C.negative, fontSize: 12, fontFamily: FONT }}>{error}</span>
                    </div>
                )}
                {success && (
                    <div style={{ marginTop: 10, padding: "8px 12px", borderRadius: 8, background: `${C.positive}15`, border: `1px solid ${C.positive}30` }}>
                        <span style={{ color: C.positive, fontSize: 12, fontFamily: FONT }}>{success}</span>
                    </div>
                )}

                {/* Submit */}
                <button onClick={handleSubmit} disabled={loading || !email || !password} style={{
                    ...submitBtnStyle,
                    opacity: loading || !email || !password ? 0.5 : 1,
                    cursor: (loading || !email || !password) ? "not-allowed" : "pointer",
                }}>
                    {loading ? "처리 중..." : mode === "login" ? "로그인" : "가입 신청"}
                </button>

                {/* Divider */}
                {enableGoogle && (
                    <>
                        <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "16px 0" }}>
                            <div style={{ flex: 1, height: 1, background: C.border2 }} />
                            <span style={{ color: C.mutedLight, fontSize: 10, fontFamily: FONT }}>또는</span>
                            <div style={{ flex: 1, height: 1, background: C.border2 }} />
                        </div>

                        {/* Google OAuth */}
                        <button
                            onClick={() => {
                                const redirect = redirectUrl || (typeof window !== "undefined" ? window.location.origin : "")
                                window.location.href = getGoogleOAuthUrl(supabaseUrl, redirect)
                            }}
                            style={googleBtnStyle}
                        >
                            <svg width={16} height={16} viewBox="0 0 24 24" style={{ flexShrink: 0 }}>
                                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
                                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                            </svg>
                            <span>Google로 계속하기</span>
                        </button>
                    </>
                )}

                {/* Footer */}
                <div style={{ marginTop: 20, textAlign: "center" }}>
                    <span style={{ color: C.mutedLight, fontSize: 10, fontFamily: FONT, lineHeight: 1.5 }}>
                        {mode === "login"
                            ? "계정이 없으신가요? 위에서 '가입 신청' 탭을 선택해주세요."
                            : "이미 계정이 있으신가요? 위에서 '로그인' 탭을 선택해주세요."}
                    </span>
                </div>
            </div>
        </div>
    )
}

/* ─── Styles ─── */
const containerStyle: React.CSSProperties = {
    width: "100%", minHeight: "100vh", background: C.bg,
    display: "flex", alignItems: "center", justifyContent: "center",
    padding: 20, fontFamily: FONT,
}

const cardStyle: React.CSSProperties = {
    width: "100%", maxWidth: 400,
    background: C.card, borderRadius: 20, border: `1px solid ${C.border}`,
    padding: "32px 28px",
}

const inputStyle: React.CSSProperties = {
    width: "100%", padding: "12px 14px", borderRadius: 10,
    border: `1px solid ${C.border2}`, background: C.cardAlt,
    color: C.white, fontSize: 14, fontFamily: FONT,
    outline: "none", boxSizing: "border-box",
    transition: "border-color 0.2s",
}

const submitBtnStyle: React.CSSProperties = {
    width: "100%", padding: "13px 0", marginTop: 16,
    borderRadius: 12, border: "none", cursor: "pointer",
    background: C.accent, color: "#000",
    fontSize: 14, fontWeight: 800, fontFamily: FONT,
    transition: "all 0.2s",
}

const googleBtnStyle: React.CSSProperties = {
    width: "100%", padding: "11px 0",
    borderRadius: 12, border: `1px solid ${C.border2}`,
    background: C.cardAlt, color: C.white,
    fontSize: 13, fontWeight: 600, fontFamily: FONT, cursor: "pointer",
    display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
    transition: "all 0.2s",
}

const logoutBtnStyle: React.CSSProperties = {
    width: "100%", padding: "12px 0",
    borderRadius: 12, border: `1px solid ${C.negative}40`,
    background: `${C.negative}10`, color: C.negative,
    fontSize: 13, fontWeight: 700, fontFamily: FONT, cursor: "pointer",
}

const statBox: React.CSSProperties = {
    background: C.cardAlt, borderRadius: 10, padding: "10px 12px",
    display: "flex", flexDirection: "column", gap: 4,
}

AuthPage.defaultProps = {
    supabaseUrl: "",
    supabaseAnonKey: "",
    redirectUrl: "",
    defaultNextPath: "/",
    enableGoogle: true,
}

addPropertyControls(AuthPage, {
    supabaseUrl: {
        type: ControlType.String,
        title: "Supabase URL",
        defaultValue: "",
        description: "https://xxxxx.supabase.co",
    },
    supabaseAnonKey: {
        type: ControlType.String,
        title: "Supabase Anon Key",
        defaultValue: "",
        description: "Supabase → Settings → API → anon key",
    },
    redirectUrl: {
        type: ControlType.String,
        title: "OAuth Redirect URL",
        defaultValue: "",
        description: "Google OAuth 후 돌아올 URL (비우면 현재 도메인)",
    },
    defaultNextPath: {
        type: ControlType.String,
        title: "Default Next Path",
        defaultValue: "/",
        description: "로그인 성공 후 기본 이동 경로 (?next= 없을 때)",
    },
    enableGoogle: {
        type: ControlType.Boolean,
        title: "Google 로그인",
        defaultValue: true,
    },
})
