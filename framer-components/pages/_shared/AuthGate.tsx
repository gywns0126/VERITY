import { addPropertyControls, ControlType, RenderTarget } from "framer"
import React, { useEffect, useState } from "react"

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆ (Neo Dark Terminal — _shared-patterns.ts 마스터)
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    strongBuy: "#22C55E", buy: "#B5FF19", watch: "#FFD600", caution: "#F59E0B", avoid: "#EF4444",
    up: "#F04452", down: "#3182F6",
    info: "#5BA9FF", success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const G = {
    accent: "0 0 8px rgba(181,255,25,0.35)",
    accentSoft: "0 0 4px rgba(181,255,25,0.20)",
    accentStrong: "0 0 12px rgba(181,255,25,0.50)",
    danger: "0 0 6px rgba(239,68,68,0.30)",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_tight: 1.3, lh_normal: 1.5, lh_loose: 1.7,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease", slow: "240ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/*
 * VERITY AuthGate — 사이트 전체 접근 제한 문지기 컴포넌트
 *
 * 보호하고 싶은 모든 Framer 페이지에 하나씩 드래그해서 배치하면 됩니다.
 * (로그인 페이지 `/login` 에는 배치하지 마세요)
 *
 * 동작:
 *  1. 페이지 로드 시 localStorage 의 Supabase 세션 확인
 *  2. 세션 없음 → `loginPath` 로 리다이렉트
 *  3. 세션 만료 임박 → refresh_token 으로 자동 갱신 (자동 로그인)
 *  4. 세션 유효 → 투명하게 숨음 (페이지 컨텐츠 그대로 노출)
 *  5. 1분마다 주기적으로 토큰 갱신 체크
 *
 * 확인 중에는 전체 화면 검정 오버레이로 컨텐츠를 가려
 * 미인증 컨텐츠가 깜빡이며 노출되는 것을 방지합니다.
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

interface Props {
    supabaseUrl: string
    supabaseAnonKey: string
    loginPath: string
    showOverlay: boolean
}

type GateState = "checking" | "authorized" | "redirecting"

export default function AuthGate(props: Props) {
    const {
        supabaseUrl = "",
        supabaseAnonKey = "",
        loginPath = "/login",
        showOverlay = true,
    } = props
    const [state, setState] = useState<GateState>("checking")

    // Framer 에디터 캔버스에서는 실제 게이트 동작을 스킵하고 플레이스홀더만 표시
    const isCanvas = RenderTarget.current() === RenderTarget.canvas

    // Framer 인스턴스에서 leading slash 빠진 값("home")이 들어와도
    // pathname("/home") 비교가 깨져 자기 자신으로 redirect → 무한 루프 발생.
    // → 항상 "/" 로 시작하도록 정규화.
    const normalizedLoginPath = loginPath
        ? (loginPath.startsWith("/") ? loginPath : "/" + loginPath)
        : "/login"

    useEffect(() => {
        if (isCanvas) { setState("authorized"); return }

        // 로그인 페이지 path 만 비교 (query string 제거)
        const loginPathOnly = normalizedLoginPath.split("?")[0]
        const isOnLoginPage =
            typeof window !== "undefined" && window.location.pathname === loginPathOnly

        // 로그인 페이지에 실수로 배치된 경우 통과 (무한 리다이렉트 방지)
        if (isOnLoginPage) {
            setState("authorized")
            return
        }

        const goLogin = () => {
            setState("redirecting")
            if (typeof window !== "undefined") {
                // 자기 자신으로 redirect 방지 가드 (loginPath 오설정 안전망)
                if (window.location.pathname === loginPathOnly) {
                    setState("authorized")
                    return
                }
                // 원래 경로를 query로 넘겨서 로그인 후 복귀 가능하게
                const next = encodeURIComponent(window.location.pathname + window.location.search)
                const url = normalizedLoginPath + (normalizedLoginPath.includes("?") ? "&" : "?") + "next=" + next
                window.location.href = url
            }
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

        // 만료 임박 → 자동 refresh 시도
        if (!supabaseUrl || !supabaseAnonKey || !s.refresh_token) {
            clearSession()
            goLogin()
            return
        }

        refreshSession(supabaseUrl, supabaseAnonKey, s.refresh_token).then((ns) => {
            if (ns) setState("authorized")
            else { clearSession(); goLogin() }
        })
    }, [supabaseUrl, supabaseAnonKey, normalizedLoginPath, isCanvas])

    // 주기적 refresh: 만료 5분 이내면 미리 갱신
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

    // Framer 에디터 캔버스에서만 보이는 플레이스홀더 (실제 사이트에서는 렌더되지 않음)
    if (isCanvas) {
        return (
            <div style={{
                display: "inline-flex", alignItems: "center", gap: 8,
                padding: "8px 12px", borderRadius: 16,
                background: C.bgElevated, border: `1px dashed ${C.accent}`,
                fontFamily: FONT,
            }}>
                <span style={{ fontSize: 14 }}>🔒</span>
                <div>
                    <div style={{ color: C.accent, fontSize: 12, fontWeight: 800, fontFamily: FONT, lineHeight: 1.2 }}>
                        AuthGate
                    </div>
                    <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 2, lineHeight: 1.3 }}>
                        실제 사이트에서만 동작 · → {normalizedLoginPath}
                    </div>
                </div>
            </div>
        )
    }

    // 인증됨 → 투명하게 숨음 (페이지 컨텐츠 노출)
    if (state === "authorized") return null

    // 확인/리다이렉트 중 → 오버레이로 컨텐츠 가림
    if (!showOverlay) return null

    return (
        <div style={{
            position: "fixed", top: 0, left: 0, right: 0, bottom: 0, zIndex: 99999,
            background: C.bgPage, display: "flex", alignItems: "center", justifyContent: "center",
            fontFamily: FONT,
        }}>
            <style>{`@keyframes _vg_spin { to { transform: rotate(360deg) } }`}</style>
            <div style={{ textAlign: "center" }}>
                <div style={{
                    color: C.accent, fontSize: 24, fontWeight: 900, fontFamily: FONT,
                    letterSpacing: "-0.03em", marginBottom: 14,
                }}>VERITY</div>
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

AuthGate.defaultProps = {
    supabaseUrl: "",
    supabaseAnonKey: "",
    loginPath: "/login",
    showOverlay: true,
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
