import { addPropertyControls, ControlType, RenderTarget } from "framer"
import React, { useEffect, useState } from "react"

/**
 * AlphaNest 내정보 페이지 — 페이지 전체용 컴포넌트 (네브바 버튼 없음, 페이지에 바로 렌더).
 *
 * 가입 시 입력 정보(이름/이메일/전화/가입일/상태) + 로그아웃 + 회원 탈퇴.
 * 데이터: localStorage("verity_supabase_session") 세션 + Supabase REST `profiles` (PublicAuth 공유 스키마).
 *   가입일 = auth user.created_at. profiles select 는 확정 컬럼만(컬럼 부재 시 400 회피).
 * 탈퇴: anon key 로는 auth user 물리 삭제 불가(service role 필요) → 승인제(status) 모델 정합:
 *       profiles.status = "withdrawn" soft-delete + 세션 파기 + 리다이렉트. 실제 삭제는 관리자.
 *
 * 테마: Framer 네이티브 추종 — body[data-framer-theme]("light"|"dark") 를 읽어 dark 전환.
 *   PublicThemeToggle(네이티브) 이 그 속성을 바꾸면 이 컴포넌트 + Color Styles 가 함께 전환.
 *   dark prop = 캔버스 정적 프리뷰 fallback. 실제 사이트는 body 속성을 따름.
 * RULE7: 점수/등급/verdict 0. 캔버스에서는 샘플 카드 렌더(부작용 없음).
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", field: "#f7f8fa", red: "#f04452", redSoft: "#fff0f1",
    green: "#15c47e", greenSoft: "#eafaf3", blue: "#3182f6", blueSoft: "#eef4ff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", field: "#0f1318", red: "#f04452", redSoft: "#2a1a1d",
    green: "#34e08a", greenSoft: "#0f241c", blue: "#5b9bff", blueSoft: "#152031",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Menlo', monospace"
const SESSION_KEY = "verity_supabase_session"

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
        return raw ? (JSON.parse(raw) as SupaSession) : null
    } catch (e) {
        return null
    }
}

function clearSession() {
    if (typeof window !== "undefined") localStorage.removeItem(SESSION_KEY)
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
    if (status === "pending") return { label: "승인 대기", fg: C.blue, bg: C.blueSoft }
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
    loginRedirect: string
    logoutRedirect: string
    dark: boolean
}

type Busy = "" | "logout" | "withdraw"
type Phase = "loading" | "guest" | "member"

export default function PublicProfilePage(props: Props) {
    const supabaseUrl = (props.supabaseUrl || "").replace(/\/+$/, "")
    const supabaseAnonKey = props.supabaseAnonKey || ""
    const profileTable = props.profileTable || "profiles"
    const loginRedirect = props.loginRedirect || "/login"
    const logoutRedirect = props.logoutRedirect || "/login"

    const isCanvas = RenderTarget.current() === RenderTarget.canvas

    const [dark, setDark] = useState<boolean>(!!props.dark)
    const [phase, setPhase] = useState<Phase>(isCanvas ? "member" : "loading")
    const [confirming, setConfirming] = useState(false)
    const [busy, setBusy] = useState<Busy>("")
    const [profile, setProfile] = useState<Profile | null>(isCanvas ? SAMPLE : null)

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

    /* 마운트: 세션 로드 + 프로필 보강 */
    useEffect(() => {
        if (isCanvas) return
        const s = loadSession()
        if (!s || !s.user) {
            setPhase("guest")
            return
        }
        const meta = (s.user.user_metadata) || {}
        const base: Profile = {
            display_name: meta.name || meta.full_name || (s.user.email || "").split("@")[0] || "사용자",
            email: s.user.email || meta.email || "",
            phone: meta.phone || "",
            status: "",
            created_at: s.user.created_at || meta.created_at || "",
        }
        setProfile(base)
        setPhase("member")
        if (!s.access_token) return
        let alive = true
        fetchProfile(supabaseUrl, supabaseAnonKey, s.access_token, profileTable, s.user.id).then((row) => {
            if (!alive || !row) return
            setProfile({
                display_name: row.display_name || base.display_name,
                email: row.email || base.email,
                phone: row.phone || base.phone,
                status: row.status || base.status,
                created_at: row.created_at || base.created_at,
            })
        })
        return () => {
            alive = false
        }
    }, [isCanvas, supabaseUrl, supabaseAnonKey, profileTable])

    const go = (path: string) => {
        if (typeof window !== "undefined") {
            const dest = path && path.trim() ? path.trim() : "/login"
            window.location.assign(dest)
        }
    }

    const handleLogout = async () => {
        if (busy) return
        setBusy("logout")
        const s = loadSession()
        if (s && s.access_token) await serverLogout(supabaseUrl, supabaseAnonKey, s.access_token)
        clearSession()
        go(logoutRedirect)
    }

    const handleWithdraw = async () => {
        if (busy) return
        setBusy("withdraw")
        const s = loadSession()
        if (s && s.access_token && s.user) {
            await markWithdrawn(supabaseUrl, supabaseAnonKey, s.access_token, profileTable, s.user.id)
            await serverLogout(supabaseUrl, supabaseAnonKey, s.access_token)
        }
        clearSession()
        go(logoutRedirect)
    }

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

    if (phase === "loading") {
        return (
            <div style={wrap}>
                <div style={{ ...cardStyle, textAlign: "center", color: C.faint, fontSize: 13, fontWeight: 600 }}>
                    불러오는 중...
                </div>
            </div>
        )
    }

    if (phase === "guest") {
        return (
            <div style={wrap}>
                <div style={{ ...cardStyle, textAlign: "center" }}>
                    <div style={{ display: "flex", justifyContent: "center", marginBottom: 14 }}>
                        <div style={{ width: 64, height: 64, borderRadius: 20, background: C.field, display: "flex", alignItems: "center", justifyContent: "center" }}>
                            <BustAvatar size={40} color={C.faint} />
                        </div>
                    </div>
                    <div style={{ fontSize: 16, fontWeight: 800, letterSpacing: -0.3 }}>로그인이 필요해요</div>
                    <div style={{ fontSize: 12.5, color: C.sub, fontWeight: 600, marginTop: 6, lineHeight: 1.5 }}>
                        내 정보를 보려면 먼저 로그인해 주세요.
                    </div>
                    <button type="button" onClick={() => go(loginRedirect)} style={btnSolid(C, false)}>
                        로그인하러 가기
                    </button>
                </div>
            </div>
        )
    }

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
            {/* 이용약관(/policy) 링크 — 내부 이동 */}
            <a href="/policy" style={{ display: "block", textAlign: "center", marginTop: 16, color: C.faint, fontSize: 12, fontWeight: 600, textDecoration: "none" }}>이용약관 · 개인정보처리방침</a>
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
        background: C.ink, color: C.card, fontSize: 14.5, fontWeight: 800, fontFamily: FONT,
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
    supabaseUrl: { type: ControlType.String, title: "Supabase URL", defaultValue: "", description: "https://xxxxx.supabase.co" },
    supabaseAnonKey: { type: ControlType.String, title: "Supabase Anon Key", defaultValue: "" },
    profileTable: { type: ControlType.String, title: "프로필 테이블", defaultValue: "profiles" },
    loginRedirect: { type: ControlType.String, title: "로그인 경로", defaultValue: "/login" },
    logoutRedirect: { type: ControlType.String, title: "로그아웃/탈퇴 후 이동", defaultValue: "/login" },
    dark: { type: ControlType.Boolean, title: "Dark (정적)", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})
