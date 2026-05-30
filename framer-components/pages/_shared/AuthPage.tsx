import { addPropertyControls, ControlType } from "framer"
import React, { useState, useEffect, useCallback } from "react"

/* ──────────────────────────────────────────────────────────────
 * Design tokens — 3색 strict (흑/백/TIDE 초록) + TIDE design 정합
 * Brand: TIDE 초록 #7fffa0 (5/30 PM 결단, 라임 #B5FF17 폐기)
 * SoT: docs/design_system_tide.md
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPrimary: "#0a0a0a",
    bgElevated: "#141414",
    bgSubtle: "rgba(255,255,255,0.02)",
    textPrimary: "#ffffff",
    textSecondary: "#A8ABB2",
    textTertiary: "#6B6E76",
    textDisabled: "#4A4C52",
    accent: "#7fffa0",
    divider: "rgba(255,255,255,0.06)",
    border: "rgba(255,255,255,0.06)",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"

const labelStyle: React.CSSProperties = {
    fontSize: 11,
    color: C.textTertiary,
    textTransform: "uppercase",
    letterSpacing: "0.04em",
    fontFamily: FONT,
    fontWeight: 600,
}

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

    if (!accessToken) {
        return { result: "email_confirm", userId }
    }

    if (userId) {
        await ensureProfile(supabaseUrl, anonKey, accessToken, userId, email, displayName, extras)
    }
    clearSession()
    return { result: "pending", userId }
}

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

    const status = await fetchProfileStatus(supabaseUrl, anonKey, session.access_token, session.user.id)

    if (status === "approved") {
        saveSession(session)
        return session
    }

    if (status === "missing") {
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

interface Props {
    supabaseUrl: string
    supabaseAnonKey: string
    redirectUrl: string
    defaultNextPath: string
    enableGoogle: boolean
    onAuthChange?: (session: SupaSession | null) => void
}

function resolveNextPath(defaultNextPath: string): string {
    if (typeof window === "undefined") return defaultNextPath || "/"
    try {
        const p = new URLSearchParams(window.location.search).get("next")
        if (p && p.startsWith("/")) return p
    } catch { /* ignore */ }
    return defaultNextPath || "/"
}

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
                    setSuccess("요청 접수됨. 이메일 인증 후 승인 대기.")
                } else {
                    setSuccess("요청 접수됨. 승인 후 접근 가능.")
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

    if (session) {
        const user = session.user
        const name = user.user_metadata?.name || user.email?.split("@")[0] || "사용자"
        return (
            <div style={containerStyle}>
                <div style={cardStyle}>
                    <div style={{
                        width: 56, height: 56, borderRadius: "50%", background: "transparent",
                        border: `1px solid ${C.border}`, display: "flex", alignItems: "center",
                        justifyContent: "center", margin: "0 auto 16px",
                    }}>
                        <span style={{ color: C.textPrimary, fontSize: 22, fontWeight: 600, fontFamily: FONT }}>
                            {name.charAt(0).toUpperCase()}
                        </span>
                    </div>
                    <div style={{ textAlign: "center", marginBottom: 24 }}>
                        <div style={{ color: C.textPrimary, fontSize: 14, fontWeight: 600, fontFamily: FONT }}>{name}</div>
                        <div style={{ color: C.textTertiary, fontSize: 11, fontFamily: FONT_MONO, marginTop: 4, fontVariantNumeric: "tabular-nums" }}>{user.email}</div>
                    </div>

                    <div style={{
                        display: "flex", flexDirection: "column", gap: 0,
                        paddingTop: 16, paddingBottom: 16,
                        borderTop: `1px solid ${C.divider}`,
                        borderBottom: `1px solid ${C.divider}`,
                        marginBottom: 20,
                    }}>
                        <Row label="가입일" value={user.user_metadata?.created_at ? new Date(user.user_metadata.created_at).toLocaleDateString("ko-KR") : "—"} />
                        <Row label="권한" value="OPERATOR" valueColor={C.accent} />
                    </div>

                    <button onClick={handleLogout} style={logoutBtnStyle}>로그아웃</button>
                </div>
            </div>
        )
    }

    return (
        <div style={containerStyle}>
            <div style={cardStyle}>
                <div style={{
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                    paddingBottom: 16,
                    borderBottom: `1px solid ${C.divider}`,
                }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{
                            width: 6, height: 6, borderRadius: "50%",
                            background: C.accent,
                        }} />
                        <span style={{ ...labelStyle, color: C.textSecondary }}>SECURE</span>
                    </div>
                    <span style={{ ...labelStyle, color: C.textTertiary, fontFamily: FONT_MONO }}>TLS · KR</span>
                </div>

                <div style={{ textAlign: "center", marginTop: 24, marginBottom: 24 }}>
                    <div style={{ color: C.accent, fontSize: 28, fontWeight: 700, fontFamily: FONT, letterSpacing: -0.5 }}>
                        VERITY
                    </div>
                    <div style={{ ...labelStyle, marginTop: 4 }}>
                        OPERATOR CONSOLE
                    </div>
                    <div style={{
                        display: "inline-block",
                        marginTop: 12,
                    }}>
                        <span style={{
                            ...labelStyle,
                            color: C.textTertiary,
                            fontFamily: FONT_MONO,
                            letterSpacing: "0.08em",
                        }}>
                            ADMIN ONLY
                        </span>
                    </div>
                </div>

                <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
                    {(["login", "signup"] as const).map((m) => {
                        const active = mode === m
                        return (
                            <button key={m} onClick={() => { setMode(m); setError(""); setSuccess("") }} style={{
                                flex: 1, border: "none", padding: "8px 0",
                                background: active ? C.textPrimary : C.bgElevated,
                                color: active ? C.bgPrimary : C.textPrimary,
                                fontSize: 12, fontWeight: 600, fontFamily: FONT, cursor: "pointer",
                                borderRadius: 4,
                            }}>
                                {m === "login" ? "로그인" : "등록 신청"}
                            </button>
                        )
                    })}
                </div>

                {mode === "signup" && (
                    <div style={{
                        padding: "10px 12px", borderRadius: 4, marginBottom: 16,
                        border: `1px solid ${C.border}`,
                    }}>
                        <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>
                            총책임자 승인 후에만 접근 가능합니다.
                        </div>
                    </div>
                )}

                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
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

                            <label style={{
                                display: "flex", alignItems: "flex-start", gap: 10, cursor: "pointer",
                                padding: "10px 12px", borderRadius: 4,
                                border: `1px solid ${consent ? C.accent : C.border}`,
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
                                    <div style={{ color: C.textPrimary, fontSize: 12, fontWeight: 600, fontFamily: FONT, marginBottom: 4 }}>
                                        개인정보 수집·이용 동의 (필수)
                                    </div>
                                    <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>
                                        수집: 이메일, 이름, 전화번호 · 목적: 회원 식별 / 관리자 승인 · 보유: 회원 탈퇴 시까지
                                    </div>
                                </div>
                            </label>
                        </>
                    )}
                </div>

                {error && (
                    <div style={{ marginTop: 12, padding: "8px 12px", borderRadius: 4, border: `1px solid ${C.accent}` }}>
                        <span style={{ color: C.textPrimary, fontSize: 12, fontFamily: FONT }}>
                            <span style={{ ...labelStyle, marginRight: 6, color: C.accent }}>오류</span>
                            {error}
                        </span>
                    </div>
                )}
                {success && (
                    <div style={{ marginTop: 12, padding: "8px 12px", borderRadius: 4, border: `1px solid ${C.accent}` }}>
                        <span style={{ color: C.textPrimary, fontSize: 12, fontFamily: FONT }}>
                            <span style={{ ...labelStyle, marginRight: 6, color: C.accent }}>완료</span>
                            {success}
                        </span>
                    </div>
                )}

                <button onClick={handleSubmit} disabled={loading || !email || !password} style={{
                    ...submitBtnStyle,
                    opacity: loading || !email || !password ? 0.5 : 1,
                    cursor: (loading || !email || !password) ? "not-allowed" : "pointer",
                }}>
                    {loading ? "처리 중..." : mode === "login" ? "로그인" : "등록 신청"}
                </button>

                {enableGoogle && (
                    <>
                        <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "20px 0" }}>
                            <div style={{ flex: 1, height: 1, background: C.divider }} />
                            <span style={{ color: C.textTertiary, fontSize: 11, fontFamily: FONT }}>또는</span>
                            <div style={{ flex: 1, height: 1, background: C.divider }} />
                        </div>

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

                <div style={{
                    marginTop: 20, paddingTop: 16,
                    borderTop: `1px solid ${C.divider}`,
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                }}>
                    <span style={{ ...labelStyle, color: C.textTertiary }}>VERITY · INTERNAL</span>
                    <span style={{ ...labelStyle, color: C.textTertiary, fontFamily: FONT_MONO }}>v1.0</span>
                </div>
            </div>
        </div>
    )
}

interface RowProps {
    label: string
    value: string
    valueColor?: string
}
function Row(props: RowProps) {
    return (
        <div style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "6px 0",
            fontSize: 13,
        }}>
            <span style={{ color: C.textSecondary, fontFamily: FONT }}>{props.label}</span>
            <span style={{
                color: props.valueColor || C.textPrimary,
                fontWeight: 600,
                fontFamily: FONT_MONO,
                fontVariantNumeric: "tabular-nums",
            }}>
                {props.value}
            </span>
        </div>
    )
}

const containerStyle: React.CSSProperties = {
    border: "none",
    width: "100%", minHeight: "100vh", background: "transparent",
    display: "flex", alignItems: "center", justifyContent: "center",
    padding: 20, fontFamily: FONT,
}

const cardStyle: React.CSSProperties = {
    width: "100%", maxWidth: 400,
    background: C.bgPrimary, borderRadius: 8, border: `1px solid ${C.border}`,
    padding: "24px 24px",
}

const inputStyle: React.CSSProperties = {
    width: "100%", padding: "10px 12px", borderRadius: 4,
    border: `1px solid ${C.border}`, background: "transparent",
    color: C.textPrimary, fontSize: 13, fontFamily: FONT,
    outline: "none", boxSizing: "border-box",
}

const submitBtnStyle: React.CSSProperties = {
    width: "100%", padding: "12px 0", marginTop: 16,
    borderRadius: 4, border: "none",
    background: C.accent, color: C.bgPrimary,
    fontSize: 13, fontWeight: 700, fontFamily: FONT,
    letterSpacing: "0.04em",
    textTransform: "uppercase",
}

const googleBtnStyle: React.CSSProperties = {
    width: "100%", padding: "10px 0",
    borderRadius: 4, border: `1px solid ${C.border}`,
    background: "transparent", color: C.textPrimary,
    fontSize: 13, fontWeight: 600, fontFamily: FONT, cursor: "pointer",
    display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
}

const logoutBtnStyle: React.CSSProperties = {
    width: "100%", padding: "10px 0",
    borderRadius: 4, border: `1px solid ${C.border}`,
    background: "transparent", color: C.textSecondary,
    fontSize: 13, fontWeight: 600, fontFamily: FONT, cursor: "pointer",
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
