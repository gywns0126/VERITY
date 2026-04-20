import { addPropertyControls, ControlType, RenderTarget } from "framer"
import React, { useState } from "react"

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
const FONT = "'Inter', 'Pretendard', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/*
 * VERITY Logout Button — Supabase 세션 즉시 파기 + 리다이렉트
 *
 * - localStorage("verity_supabase_session") 삭제
 * - Supabase GoTrue /logout 호출 (refresh_token 서버 측 무효화)
 * - 지정된 경로로 이동 (기본: "/")
 *
 * Framer 편집 캔버스에서는 클릭해도 아무 일 없이 작동하도록 막아둠.
 */

/* ─── Design tokens ─── */
const SESSION_KEY = "verity_supabase_session"

interface SupaSession {
    access_token: string
    refresh_token: string
    expires_at: number
}

function loadSessionRaw(): SupaSession | null {
    if (typeof window === "undefined") return null
    try {
        const raw = localStorage.getItem(SESSION_KEY)
        if (!raw) return null
        return JSON.parse(raw) as SupaSession
    } catch {
        return null
    }
}

function clearSession() {
    if (typeof window !== "undefined") localStorage.removeItem(SESSION_KEY)
}

async function serverLogout(supabaseUrl: string, anonKey: string, accessToken: string): Promise<void> {
    if (!supabaseUrl || !anonKey || !accessToken) return
    try {
        await fetch(`${supabaseUrl}/auth/v1/logout`, {
            method: "POST",
            headers: {
                apikey: anonKey,
                Authorization: `Bearer ${accessToken}`,
                "Content-Type": "application/json",
            },
        })
    } catch {
        /* 네트워크 실패해도 로컬 세션은 지우므로 무시 */
    }
}

type Variant = "solid" | "outline" | "ghost" | "danger"

interface Props {
    label: string
    variant: Variant
    supabaseUrl: string
    supabaseAnonKey: string
    redirectPath: string
    fullWidth: boolean
    size: "small" | "medium" | "large"
    showIcon: boolean
}

export default function LogoutButton(props: Props) {
    const {
        label,
        variant,
        supabaseUrl,
        supabaseAnonKey,
        redirectPath,
        fullWidth,
        size,
        showIcon,
    } = props

    const [loading, setLoading] = useState(false)
    const isCanvas = RenderTarget.current() === RenderTarget.canvas

    const handleLogout = async () => {
        if (isCanvas) return
        if (loading) return
        setLoading(true)

        const s = loadSessionRaw()
        if (s?.access_token && supabaseUrl && supabaseAnonKey) {
            await serverLogout(supabaseUrl, supabaseAnonKey, s.access_token)
        }
        clearSession()

        if (typeof window !== "undefined") {
            const dest = redirectPath && redirectPath.trim() ? redirectPath.trim() : "/"
            window.location.assign(dest)
        }
    }

    const sizes: Record<Props["size"], { padY: number; padX: number; font: number; iconSize: number }> = {
        small: { padY: 6, padX: 12, font: 12, iconSize: 14 },
        medium: { padY: 10, padX: 16, font: 13, iconSize: 16 },
        large: { padY: 14, padX: 22, font: 15, iconSize: 18 },
    }
    const sz = sizes[size] || sizes.medium

    const variantStyle: React.CSSProperties = (() => {
        switch (variant) {
            case "solid":
                return {
                    background: C.accent,
                    color: "#000",
                    border: `1px solid ${C.accent}`,
                }
            case "outline":
                return {
                    background: "transparent",
                    color: C.textPrimary,
                    border: `1px solid ${C.border}`,
                }
            case "ghost":
                return {
                    background: "transparent",
                    color: C.textSecondary,
                    border: "1px solid transparent",
                }
            case "danger":
                return {
                    background: "transparent",
                    color: C.danger,
                    border: `1px solid ${C.danger}55`,
                }
        }
    })()

    const buttonStyle: React.CSSProperties = {
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 8,
        padding: `${sz.padY}px ${sz.padX}px`,
        borderRadius: 8,
        fontFamily: FONT,
        fontSize: sz.font,
        fontWeight: 600,
        letterSpacing: "-0.01em",
        cursor: loading ? "wait" : "pointer",
        opacity: loading ? 0.6 : 1,
        userSelect: "none",
        width: fullWidth ? "100%" : "auto",
        transition: "transform 0.08s ease, opacity 0.15s ease",
        ...variantStyle,
    }

    if (isCanvas) {
        return (
            <div
                style={{
                    ...buttonStyle,
                    cursor: "default",
                    outline: `1px dashed ${C.border}`,
                    outlineOffset: 2,
                }}
                title="Framer 편집 캔버스 - 실제 사이트에서만 작동"
            >
                {showIcon && <LogoutIcon size={sz.iconSize} />}
                {label || "로그아웃"}
            </div>
        )
    }

    return (
        <button
            type="button"
            style={buttonStyle}
            onClick={handleLogout}
            disabled={loading}
            onMouseDown={(e) => {
                (e.currentTarget as HTMLButtonElement).style.transform = "scale(0.97)"
            }}
            onMouseUp={(e) => {
                (e.currentTarget as HTMLButtonElement).style.transform = "scale(1)"
            }}
            onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.transform = "scale(1)"
            }}
        >
            {showIcon && <LogoutIcon size={sz.iconSize} />}
            {loading ? "로그아웃 중..." : label || "로그아웃"}
        </button>
    )
}

function LogoutIcon({ size }: { size: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" y1="12" x2="9" y2="12" />
        </svg>
    )
}

LogoutButton.defaultProps = {
    label: "로그아웃",
    variant: "outline",
    supabaseUrl: "",
    supabaseAnonKey: "",
    redirectPath: "/",
    fullWidth: false,
    size: "medium",
    showIcon: true,
}

addPropertyControls(LogoutButton, {
    label: {
        type: ControlType.String,
        title: "버튼 텍스트",
        defaultValue: "로그아웃",
    },
    variant: {
        type: ControlType.Enum,
        title: "스타일",
        options: ["solid", "outline", "ghost", "danger"],
        optionTitles: ["네온 솔리드", "아웃라인", "고스트", "위험 (빨강)"],
        defaultValue: "outline",
    },
    size: {
        type: ControlType.Enum,
        title: "크기",
        options: ["small", "medium", "large"],
        optionTitles: ["Small", "Medium", "Large"],
        defaultValue: "medium",
    },
    showIcon: {
        type: ControlType.Boolean,
        title: "아이콘 표시",
        defaultValue: true,
    },
    fullWidth: {
        type: ControlType.Boolean,
        title: "가로 가득",
        defaultValue: false,
    },
    redirectPath: {
        type: ControlType.String,
        title: "로그아웃 후 이동",
        defaultValue: "/",
        description: "로그아웃 성공 후 이동할 경로 (예: /)",
    },
    supabaseUrl: {
        type: ControlType.String,
        title: "Supabase URL",
        defaultValue: "",
        description: "비우면 로컬 세션만 삭제 (서버 측 refresh_token 무효화는 생략)",
    },
    supabaseAnonKey: {
        type: ControlType.String,
        title: "Supabase Anon Key",
        defaultValue: "",
    },
})
