import { addPropertyControls, ControlType, RenderTarget } from "framer"
import React, { useEffect, useState } from "react"

/**
 * AdminNavLink — is_admin 계정에게만 "관리자" 링크를 뿅 노출.
 * 네브바(또는 아무 데)에 배치. 로그인 세션(verity_supabase_session) + profiles.is_admin 확인.
 *   · 관리자 → /admin 링크 렌더. · 아니면 → null(안 보임).
 * verity_auth_change / storage 이벤트 구독 → 로그인·로그아웃 순간 새로고침 없이 나타남/사라짐.
 * 🚨 이건 노출 편의일 뿐 — 실제 접근 차단은 /admin 의 AdminGate + 서버(admin.py). 다크감지.
 * ⚠ 보수 구문(옵셔널체이닝/옵셔널catch/defaultProps 회피 — Framer esbuild panic).
 */

const SESSION_KEY = "verity_supabase_session"
const AUTH_EVENT = "verity_auth_change"
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

interface Session { access_token: string; expires_at: number; user: { id: string } }

function loadSession(): Session | null {
    if (typeof window === "undefined") return null
    try {
        const raw = localStorage.getItem(SESSION_KEY)
        if (!raw) return null
        const s = JSON.parse(raw)
        if (s.expires_at && Date.now() / 1000 > s.expires_at) return null
        return s as Session
    } catch (e) {
        return null
    }
}
function bodyDark(): boolean {
    try {
        if (typeof document !== "undefined" && document.body) {
            const a = document.body.dataset.framerTheme
            if (a === "dark") return true
            if (a === "light") return false
        }
        if (typeof localStorage !== "undefined") {
            const s = localStorage.getItem("verity_theme")
            if (s === "dark") return true
        }
    } catch (e) {}
    return false
}

interface Props {
    supabaseUrl: string
    supabaseAnonKey: string
    adminPath: string
    label: string
    dark: boolean
}

export default function AdminNavLink(props: Props) {
    const supabaseUrl = (props.supabaseUrl || "").replace(/\/+$/, "")
    const anon = props.supabaseAnonKey || ""
    const adminPath = props.adminPath || "/admin"
    const label = props.label || "관리자"
    const isCanvas = RenderTarget.current() === RenderTarget.canvas
    const [show, setShow] = useState<boolean>(isCanvas)
    const [themeDark, setThemeDark] = useState<boolean>(isCanvas ? !!props.dark : bodyDark())

    useEffect(() => {
        if (isCanvas) return
        let alive = true

        const check = async () => {
            const s = loadSession()
            if (!s || !supabaseUrl || !anon) { if (alive) setShow(false); return }
            try {
                const r = await fetch(`${supabaseUrl}/rest/v1/profiles?id=eq.${s.user.id}&select=is_admin`, {
                    headers: { apikey: anon, Authorization: "Bearer " + s.access_token, Accept: "application/json" },
                })
                let rows: any[] = []
                if (r.ok) {
                    try { rows = await r.json() } catch (e) { rows = [] }
                }
                if (alive) setShow(Array.isArray(rows) && rows[0] && rows[0].is_admin === true)
            } catch (e) {
                if (alive) setShow(false)
            }
        }
        check()

        const onAuth = () => check()
        const readTheme = () => setThemeDark(bodyDark())
        window.addEventListener(AUTH_EVENT, onAuth)
        window.addEventListener("storage", onAuth)
        let obs: MutationObserver | null = null
        if (typeof MutationObserver !== "undefined" && document.body) {
            obs = new MutationObserver(readTheme)
            obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        }
        return () => {
            alive = false
            window.removeEventListener(AUTH_EVENT, onAuth)
            window.removeEventListener("storage", onAuth)
            if (obs) obs.disconnect()
        }
    }, [supabaseUrl, anon, isCanvas])

    if (!show) return null

    const vt = themeDark ? "#a99bff" : "#6c5ce7"
    const vtS = themeDark ? "#241f3a" : "#f0edff"

    const go = () => {
        if (isCanvas) return
        if (typeof window !== "undefined") window.location.href = adminPath
    }

    return (
        <div
            role="button"
            tabIndex={0}
            onClick={go}
            style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                fontFamily: FONT, fontSize: 13, fontWeight: 800, color: vt,
                background: vtS, borderRadius: 10, padding: "7px 13px", cursor: "pointer",
                whiteSpace: "nowrap", userSelect: "none",
            }}
        >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={vt} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 2l7 4v6c0 4.4-3 8-7 10-4-2-7-5.6-7-10V6z" />
            </svg>
            {label}
        </div>
    )
}

addPropertyControls(AdminNavLink, {
    supabaseUrl: { type: ControlType.String, title: "Supabase URL", defaultValue: "https://lykqebdcurreppowulsl.supabase.co" },
    supabaseAnonKey: { type: ControlType.String, title: "Supabase Anon Key", defaultValue: "" },
    adminPath: { type: ControlType.String, title: "Admin Path", defaultValue: "/admin" },
    label: { type: ControlType.String, title: "Label", defaultValue: "관리자" },
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
})
