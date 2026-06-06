import { addPropertyControls, ControlType, RenderTarget } from "framer"
import React, { useEffect, useState } from "react"

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆ (Neo Dark Terminal — _shared-patterns.ts 마스터)
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0a0a0a", bgCard: "#141414", bgElevated: "#1a1a1a", bgInput: "transparent",
    border: "rgba(255,255,255,0.06)", borderStrong: "rgba(255,255,255,0.10)", borderHover: "#7fffa0",
    textPrimary: "#ffffff", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#7fffa0", accentSoft: "rgba(127, 255, 160,0.12)",
    strongBuy: "#22C55E", buy: "#2DD4BF", watch: "#FFD600", caution: "#F59E0B", avoid: "#EF4444",
    up: "#F04452", down: "#3182F6",
    info: "#5BA9FF", success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_tight: 1.3, lh_normal: 1.5, lh_loose: 1.7,
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"

/*
 * VERITY AuthGate — 사이트 전체 접근 제한 문지기 컴포넌트
 * 보호하고 싶은 모든 Framer 페이지에 하나씩 드래그해서 배치 (로그인 페이지 제외).
 *
 * ⚠ 2026-05-21: optional chaining(?.) / optional catch(catch{}) / 즉시실행 async IIFE /
 *   defaultProps 등 모던 구문이 Framer esbuild 를 "RuntimeError: unreachable" 로 panic
 *   시키는 회귀가 있어, 보수적 구문으로 재작성함. 이 스타일 유지할 것.
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
    } catch (e) {
        return null
    }
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
        if (!body || !body.access_token) return null
        const s: AuthSession = {
            access_token: body.access_token,
            refresh_token: body.refresh_token,
            expires_at: body.expires_at || Date.now() / 1000 + 3600,
            user: body.user,
        }
        saveSession(s)
        return s
    } catch (e) {
        return null
    }
}

async function tryConsumeOAuthHash(supabaseUrl: string, anonKey: string): Promise<AuthSession | null> {
    if (typeof window === "undefined") return null
    const hash = window.location.hash || ""
    if (hash.indexOf("access_token=") === -1) return null
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
        let rows: any[] = []
        if (pres.ok) {
            try { rows = await pres.json() } catch (e) { rows = [] }
        }
        const status = Array.isArray(rows) && rows[0] ? rows[0].status : null
        if (status !== "approved") return null
        const session: AuthSession = {
            access_token: at,
            refresh_token: rt,
            expires_at: Number(expRaw) > 1e9 ? Number(expRaw) : Date.now() / 1000 + Number(expRaw || 3600),
            user: u,
        }
        saveSession(session)
        return session
    } catch (e) {
        return null
    }
}

interface Props {
    supabaseUrl: string
    supabaseAnonKey: string
    loginPath: string
    showOverlay: boolean
}

type GateState = "checking" | "authorized" | "redirecting"

export default function AuthGate(props: Props) {
    const supabaseUrl = props.supabaseUrl || ""
    const supabaseAnonKey = props.supabaseAnonKey || ""
    const loginPath = props.loginPath || "/login"
    const showOverlay = props.showOverlay !== false
    const [state, setState] = useState<GateState>("checking")

    const isCanvas = RenderTarget.current() === RenderTarget.canvas

    const normalizedLoginPath = loginPath
        ? (loginPath.charAt(0) === "/" ? loginPath : "/" + loginPath)
        : "/login"

    useEffect(() => {
        if (isCanvas) {
            setState("authorized")
            return
        }

        const loginPathOnly = normalizedLoginPath.split("?")[0]
        const isOnLoginPage =
            typeof window !== "undefined" && window.location.pathname === loginPathOnly

        if (isOnLoginPage) {
            setState("authorized")
            return
        }

        const goLogin = () => {
            setState("redirecting")
            if (typeof window !== "undefined") {
                if (window.location.pathname === loginPathOnly) {
                    setState("authorized")
                    return
                }
                const next = encodeURIComponent(window.location.pathname + window.location.search)
                const sep = normalizedLoginPath.indexOf("?") !== -1 ? "&" : "?"
                window.location.href = normalizedLoginPath + sep + "next=" + next
            }
        }

        let cancelled = false

        const run = async () => {
            if (typeof window !== "undefined" && window.location.hash.indexOf("access_token=") !== -1) {
                const oauth = await tryConsumeOAuthHash(supabaseUrl, supabaseAnonKey)
                if (cancelled) return
                if (oauth) {
                    setState("authorized")
                    return
                }
                goLogin()
                return
            }

            const s = loadSessionRaw()
            if (!s) {
                goLogin()
                return
            }

            const now = Date.now() / 1000
            const nearExpiry = s.expires_at && now > s.expires_at - 300
            if (!nearExpiry) {
                setState("authorized")
                return
            }

            if (!supabaseUrl || !supabaseAnonKey || !s.refresh_token) {
                clearSession()
                goLogin()
                return
            }
            const ns = await refreshSession(supabaseUrl, supabaseAnonKey, s.refresh_token)
            if (cancelled) return
            if (ns) {
                setState("authorized")
            } else {
                clearSession()
                goLogin()
            }
        }
        run()

        return () => {
            cancelled = true
        }
    }, [supabaseUrl, supabaseAnonKey, normalizedLoginPath, isCanvas])

    useEffect(() => {
        if (state !== "authorized") return
        if (!supabaseUrl || !supabaseAnonKey) return
        const id = setInterval(() => {
            const cur = loadSessionRaw()
            if (!cur || !cur.refresh_token) return
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
                padding: "8px 12px", borderRadius: 8,
                background: "transparent", border: `1px dashed ${C.accent}`,
                fontFamily: FONT,
            }}>
                <div>
                    <div style={{ color: C.textTertiary, fontSize: 11, fontWeight: 700, fontFamily: FONT, letterSpacing: 0.5, textTransform: "uppercase", lineHeight: 1.2 }}>
                        AuthGate
                    </div>
                    <div style={{ color: C.textSecondary, fontSize: 11, fontFamily: FONT_MONO, marginTop: 4, lineHeight: 1.3, letterSpacing: 0.3 }}>
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
            <style>{`@keyframes _vg_spin { to { transform: rotate(360deg) } }`}</style>
            <div style={{ textAlign: "center" }}>
                <div style={{ color: C.accent, fontSize: 24, fontWeight: 900, fontFamily: FONT, letterSpacing: -0.5, marginBottom: 14 }}>
                    VERITY
                </div>
                <div style={{
                    width: 28, height: 28,
                    border: `3px solid ${C.border}`, borderTopColor: C.accent,
                    borderRadius: "50%", margin: "0 auto 10px",
                    animation: "_vg_spin 0.8s linear infinite",
                }} />
                <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT }}>
                    {state === "checking" ? "인증 확인 중..." : "로그인 페이지로 이동..."}
                </div>
            </div>
        </div>
    )
}

addPropertyControls(AuthGate, {
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
        defaultValue: "/login",
        description: "로그인 페이지 경로",
    },
    showOverlay: {
        type: ControlType.Boolean,
        title: "Loading Overlay",
        defaultValue: true,
        description: "인증 확인 중 전체화면 오버레이 표시",
    },
})
