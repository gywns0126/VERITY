import { addPropertyControls, ControlType, RenderTarget } from "framer"
import React, { useEffect, useState } from "react"

/* ──────────────────────────────────────────────────────────────
 * ◆ ESTATE 패밀리룩 v3 — Cluster A warm gold tone (마스터 정합)
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0A0908", bgCard: "#0F0D0A", bgElevated: "#16130E", bgInput: "#1F1B14",
    border: "transparent", borderStrong: "#3A3024",
    textPrimary: "#F2EFE9", textSecondary: "#A8A299", textTertiary: "#6B665E",
    accent: "#B8864D",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
/* ◆ TOKENS END ◆ */


/*
 * VERITY ESTATE — AuthGate (보호 페이지 문지기)
 *
 * AuthGate.tsx (terminal) 의 로직 100% 정합. ESTATE 골드 톤만 swap.
 * 같은 SESSION_KEY (verity_supabase_session) 공유 → estate ↔ terminal 세션 호환.
 *
 * 동작:
 *  1. URL hash 에 OAuth #access_token 발견 → 우선 소비·검증·저장 (Supabase Site URL
 *     이 estate /home 등을 가리킬 때 결정적 — terminal AuthGate 와 동일)
 *  2. localStorage 세션 확인
 *  3. 없음 → loginPath 로 redirect
 *  4. 만료 임박 → refresh_token 으로 자동 갱신
 *  5. 유효 → 투명 (페이지 컨텐츠 노출)
 *
 * 배치: 보호하고 싶은 모든 estate 페이지에 하나씩. 로그인 페이지("/") 에는 배치 X.
 */

const SESSION_KEY = "verity_supabase_session"

interface AuthSession {
    access_token: string
    refresh_token: string
    expires_at: number
    user: { id: string; email: string; user_metadata?: any }
}

function loadSessionRaw(): AuthSession | null {
    if (typeof window === "undefined") return null
    try {
        const raw = localStorage.getItem(SESSION_KEY)
        return raw ? JSON.parse(raw) : null
    } catch { return null }
}

function saveSession(s: AuthSession) {
    if (typeof window !== "undefined") localStorage.setItem(SESSION_KEY, JSON.stringify(s))
}

function clearSession() {
    if (typeof window !== "undefined") localStorage.removeItem(SESSION_KEY)
}

async function refreshSession(supabaseUrl: string, anonKey: string, refreshToken: string): Promise<AuthSession | null> {
    try {
        const res = await fetch(`${supabaseUrl}/auth/v1/token?grant_type=refresh_token`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                apikey: anonKey,
                Authorization: `Bearer ${anonKey}`,
            },
            body: JSON.stringify({ refresh_token: refreshToken }),
        })
        if (!res.ok) return null
        const body = await res.json()
        if (!body?.access_token) return null
        const s: AuthSession = {
            access_token: body.access_token,
            refresh_token: body.refresh_token,
            expires_at: body.expires_at || (Date.now() / 1000 + 3600),
            user: body.user,
        }
        saveSession(s)
        return s
    } catch { return null }
}

async function tryConsumeOAuthHash(supabaseUrl: string, anonKey: string): Promise<AuthSession | null> {
    if (typeof window === "undefined") return null
    const hash = window.location.hash || ""
    if (!hash.includes("access_token=")) return null
    const params = new URLSearchParams(hash.replace(/^#/, ""))
    const at = params.get("access_token")
    const rt = params.get("refresh_token") || ""
    const expRaw = params.get("expires_at") || params.get("expires_in")
    if (!at) return null
    const cleanUrl = window.location.pathname + window.location.search
    window.history.replaceState(null, "", cleanUrl)
    if (!supabaseUrl || !anonKey) return null
    try {
        const ures = await fetch(`${supabaseUrl}/auth/v1/user`, {
            headers: { apikey: anonKey, Authorization: `Bearer ${at}` },
        })
        if (!ures.ok) return null
        const u = await ures.json()
        const pres = await fetch(
            `${supabaseUrl}/rest/v1/profiles?id=eq.${u.id}&select=status`,
            { headers: { apikey: anonKey, Authorization: `Bearer ${at}`, Accept: "application/json" } }
        )
        const rows = pres.ok ? await pres.json().catch(() => []) : []
        const status = Array.isArray(rows) && rows[0]?.status
        if (status !== "approved") return null
        const session: AuthSession = {
            access_token: at,
            refresh_token: rt,
            expires_at: Number(expRaw) > 1e9
                ? Number(expRaw)
                : Date.now() / 1000 + Number(expRaw || 3600),
            user: u,
        }
        saveSession(session)
        return session
    } catch { return null }
}

interface Props {
    supabaseUrl: string
    supabaseAnonKey: string
    loginPath: string
    showOverlay: boolean
}

type GateState = "checking" | "authorized" | "redirecting"

export default function EstateAuthGate(props: Props) {
    const {
        supabaseUrl = "",
        supabaseAnonKey = "",
        loginPath = "/",
        showOverlay = true,
    } = props
    const [state, setState] = useState<GateState>("checking")

    const isCanvas = RenderTarget.current() === RenderTarget.canvas

    const normalizedLoginPath = loginPath
        ? (loginPath.startsWith("/") ? loginPath : "/" + loginPath)
        : "/"

    useEffect(() => {
        if (isCanvas) { setState("authorized"); return }

        const loginPathOnly = normalizedLoginPath.split("?")[0]
        const isOnLoginPage =
            typeof window !== "undefined" && window.location.pathname === loginPathOnly
        if (isOnLoginPage) { setState("authorized"); return }

        const goLogin = () => {
            setState("redirecting")
            if (typeof window !== "undefined") {
                if (window.location.pathname === loginPathOnly) {
                    setState("authorized")
                    return
                }
                const next = encodeURIComponent(window.location.pathname + window.location.search)
                const url = normalizedLoginPath +
                    (normalizedLoginPath.includes("?") ? "&" : "?") + "next=" + next
                window.location.href = url
            }
        }

        let cancelled = false
        ;(async () => {
            if (typeof window !== "undefined" &&
                window.location.hash.includes("access_token=")) {
                const oauth = await tryConsumeOAuthHash(supabaseUrl, supabaseAnonKey)
                if (cancelled) return
                if (oauth) { setState("authorized"); return }
                goLogin()
                return
            }

            const s = loadSessionRaw()
            if (!s) { goLogin(); return }

            const now = Date.now() / 1000
            const nearExpiry = s.expires_at && now > s.expires_at - 300
            if (!nearExpiry) { setState("authorized"); return }

            if (!supabaseUrl || !supabaseAnonKey || !s.refresh_token) {
                clearSession(); goLogin(); return
            }
            const ns = await refreshSession(supabaseUrl, supabaseAnonKey, s.refresh_token)
            if (cancelled) return
            if (ns) setState("authorized")
            else { clearSession(); goLogin() }
        })()
        return () => { cancelled = true }
    }, [supabaseUrl, supabaseAnonKey, normalizedLoginPath, isCanvas])

    useEffect(() => {
        if (state !== "authorized") return
        if (!supabaseUrl || !supabaseAnonKey) return
        const id = setInterval(() => {
            const cur = loadSessionRaw()
            if (!cur?.refresh_token) return
            const now = Date.now() / 1000
            if (cur.expires_at && now > cur.expires_at - 300) {
                refreshSession(supabaseUrl, supabaseAnonKey, cur.refresh_token).catch(() => {})
            }
        }, 60 * 1000)
        return () => clearInterval(id)
    }, [state, supabaseUrl, supabaseAnonKey])

    if (isCanvas) {
        return (
            <div style={{
                display: "inline-flex", alignItems: "center", gap: 8,
                padding: "8px 12px", borderRadius: 16,
                background: "transparent", border: `1px dashed ${C.accent}`,
                fontFamily: FONT,
            }}>
                <div>
                    <div style={{
                        color: C.textTertiary, fontSize: 11, fontWeight: 700,
                        fontFamily: FONT, letterSpacing: 0.5, textTransform: "uppercase",
                        lineHeight: 1.2,
                    }}>
                        EstateAuthGate
                    </div>
                    <div style={{
                        color: C.textSecondary, fontSize: 11, fontFamily: FONT_MONO,
                        marginTop: 4, lineHeight: 1.3, letterSpacing: 0.3,
                    }}>
                        실제 사이트에서만 동작 · → {normalizedLoginPath}
                    </div>
                </div>
            </div>
        )
    }

    if (state === "authorized") return null
    if (!showOverlay) return null

    return (
        <div style={{
            position: "fixed", top: 0, left: 0, right: 0, bottom: 0, zIndex: 99999,
            background: C.bgPage, display: "flex", alignItems: "center", justifyContent: "center",
            fontFamily: FONT,
        }}>
            <style>{`@keyframes _eg_spin { to { transform: rotate(360deg) } }`}</style>
            <div style={{ textAlign: "center" }}>
                <div style={{
                    color: C.accent, fontSize: 24, fontWeight: 900, fontFamily: FONT,
                    letterSpacing: -0.5, marginBottom: 14,
                }}>VERITY ESTATE</div>
                <div style={{
                    width: 28, height: 28,
                    border: `3px solid ${C.borderStrong}`, borderTopColor: C.accent,
                    borderRadius: "50%", margin: "0 auto 10px",
                    animation: "_eg_spin 0.8s linear infinite",
                }} />
                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>
                    {state === "checking" ? "인증 확인 중..." : "로그인 페이지로 이동..."}
                </div>
            </div>
        </div>
    )
}

EstateAuthGate.defaultProps = {
    supabaseUrl: "",
    supabaseAnonKey: "",
    loginPath: "/",
    showOverlay: true,
}

addPropertyControls(EstateAuthGate, {
    supabaseUrl: {
        type: ControlType.String,
        title: "Supabase URL",
        description: "https://xxxxx.supabase.co",
        defaultValue: "",
    },
    supabaseAnonKey: {
        type: ControlType.String,
        title: "Supabase Anon Key",
        defaultValue: "",
    },
    loginPath: {
        type: ControlType.String,
        title: "Login Path",
        defaultValue: "/",
        description: "estate 로그인 페이지 경로 (보통 root /)",
    },
    showOverlay: {
        type: ControlType.Boolean,
        title: "Loading Overlay",
        defaultValue: true,
        description: "인증 확인 중 전체화면 오버레이 표시",
    },
})
