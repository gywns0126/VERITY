import { addPropertyControls, ControlType, RenderTarget } from "framer"
import React, { useEffect, useState } from "react"

/**
 * AdminGate — AlphaNest 관리자(is_admin) 전용 페이지 문지기.
 * /admin 페이지에 하나 배치. 로그인 세션(verity_supabase_session) + profiles.is_admin 확인.
 *   · 세션 없음 → 로그인 페이지로.
 *   · 세션 있으나 is_admin 아님 → 홈으로 (일반 유저 차단).
 *   · is_admin → null 렌더 (페이지의 관리자 카드들 그대로 노출).
 * 🚨 실제 권한은 서버(admin.py is_admin 재검증)에 있음 — 이건 화면 노출 게이트.
 * ⚠ AuthGate 와 동일 보수 구문(옵셔널체이닝/옵셔널catch/async IIFE/defaultProps 회피 — Framer esbuild panic).
 */

const C = {
    bg: "#f2f4f6", ink: "#191f28", sub: "#4e5968", vt: "#6c5ce7",
    bgDark: "#0f1318", inkDark: "#e3e7ec", subDark: "#9aa4b1", vtDark: "#a99bff",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const SESSION_KEY = "verity_supabase_session"

interface Session { access_token: string; expires_at: number; user: { id: string; email: string } }

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
        }
    } catch (e) {}
    return false
}

interface Props {
    supabaseUrl: string
    supabaseAnonKey: string
    loginPath: string
    homePath: string
    showOverlay: boolean
}

type GateState = "checking" | "authorized" | "redirecting"

export default function AdminGate(props: Props) {
    const supabaseUrl = (props.supabaseUrl || "").replace(/\/+$/, "")
    const anon = props.supabaseAnonKey || ""
    const loginPath = props.loginPath || "/login"
    const homePath = props.homePath || "/"
    const showOverlay = props.showOverlay !== false
    const isCanvas = RenderTarget.current() === RenderTarget.canvas
    const [state, setState] = useState<GateState>("checking")

    useEffect(() => {
        if (isCanvas) { setState("authorized"); return }
        let cancelled = false

        const go = (path: string) => {
            setState("redirecting")
            if (typeof window !== "undefined" && window.location.pathname !== path) {
                window.location.href = path
            } else {
                setState("authorized")
            }
        }

        const run = async () => {
            const s = loadSession()
            if (!s) { go(loginPath); return }
            if (!supabaseUrl || !anon) {
                // 키 미설정 — 서버 게이트가 실권한이므로 화면은 통과 (경고는 콘솔)
                if (!cancelled) setState("authorized")
                return
            }
            try {
                const r = await fetch(`${supabaseUrl}/rest/v1/profiles?id=eq.${s.user.id}&select=is_admin`, {
                    headers: { apikey: anon, Authorization: "Bearer " + s.access_token, Accept: "application/json" },
                })
                let rows: any[] = []
                if (r.ok) {
                    try { rows = await r.json() } catch (e) { rows = [] }
                }
                const admin = Array.isArray(rows) && rows[0] && rows[0].is_admin === true
                if (cancelled) return
                if (admin) { setState("authorized") } else { go(homePath) }
            } catch (e) {
                if (!cancelled) go(homePath)
            }
        }
        run()

        return () => { cancelled = true }
    }, [supabaseUrl, anon, loginPath, homePath, isCanvas])

    const dark = bodyDark()
    const bg = dark ? C.bgDark : C.bg
    const ink = dark ? C.inkDark : C.ink
    const sub = dark ? C.subDark : C.sub
    const vt = dark ? C.vtDark : C.vt

    if (isCanvas) {
        return (
            <div style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "8px 12px", borderRadius: 10, border: `1px dashed ${vt}`, fontFamily: FONT }}>
                <div style={{ color: sub, fontSize: 11, fontWeight: 700 }}>AdminGate</div>
                <div style={{ color: sub, fontSize: 11, fontWeight: 600 }}>실제 사이트에서만 동작 · is_admin 전용</div>
            </div>
        )
    }

    if (state === "authorized") return null
    if (!showOverlay) return null

    return (
        <div style={{ position: "fixed", top: 0, left: 0, right: 0, bottom: 0, zIndex: 99999, background: bg, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: FONT }}>
            <style>{`@keyframes _ag_spin { to { transform: rotate(360deg) } }`}</style>
            <div style={{ textAlign: "center" }}>
                <div style={{ color: vt, fontSize: 22, fontWeight: 900, letterSpacing: "-0.5px", marginBottom: 14 }}>AlphaNest 관리자</div>
                <div style={{ width: 26, height: 26, border: `3px solid ${dark ? "#252b34" : "#e5e8eb"}`, borderTopColor: vt, borderRadius: "50%", margin: "0 auto 10px", animation: "_ag_spin 0.8s linear infinite" }} />
                <div style={{ color: sub, fontSize: 12, fontWeight: 600 }}>{state === "checking" ? "권한 확인 중…" : "이동 중…"}</div>
            </div>
        </div>
    )
}

addPropertyControls(AdminGate, {
    supabaseUrl: { type: ControlType.String, title: "Supabase URL", defaultValue: "https://lykqebdcurreppowulsl.supabase.co" },
    supabaseAnonKey: { type: ControlType.String, title: "Supabase Anon Key", defaultValue: "" },
    loginPath: { type: ControlType.String, title: "Login Path", defaultValue: "/login" },
    homePath: { type: ControlType.String, title: "Home Path", defaultValue: "/" },
    showOverlay: { type: ControlType.Boolean, title: "Loading Overlay", defaultValue: true },
})
