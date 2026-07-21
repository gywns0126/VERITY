import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useState, useEffect, useCallback } from "react"
import { SignOut, CaretRight, User, SignIn } from "@phosphor-icons/react"

/**
 * PublicMenuAccount — 메뉴 하단 계정 위젯 + 프로필 아바타 버튼 (2 variant, 상태 반영 + 호버).
 *
 * variant="account": 로그아웃=로그인/회원가입 버튼(솔리드 보라·흰 텍스트, 라이트·다크 동일 고정)
 *                    · 로그인=아바타+닉네임+(로그아웃) 카드.
 * variant="avatar" : 사용자 지정 프로필 사진(원형) 버튼 → 프로필 이동 (미로그인=로그인 이동).
 *
 * 호버 = 그림자·리프트 없이 색만 살짝 진해짐 (버튼/카드 배경 darken, 아바타 brightness).
 * 인증 = PublicAuth/PublicProfilePage 공유 스키마 재사용 (신규 인증 생성 아님):
 *   세션 = localStorage("verity_supabase_session") · profiles.nickname/avatar(128px JPEG base64 data-URL).
 * 🚨 2026-07-20 플래시 제거 — 세션 + 프로필(닉네임·avatar) 을 localStorage 캐시로 마운트 시 동기 로드.
 *   페이지 이동마다 재마운트해도 캐시 닉네임 즉시 표시 → 이메일 번쩍임 없음. fetch 는 백그라운드 갱신만.
 * 🎨 다크 자가감지 — fill/ink/sub 가 사이트 테마 추종(라이트=프롭 유지, 다크=사이트 표준). 보라 버튼·흰 텍스트=양모드 동일.
 */

const SESSION_KEY = "verity_supabase_session"
const PROFILE_CACHE_KEY = "verity_profile_cache"

interface SupaSession {
    access_token?: string
    user?: { id?: string; email?: string; user_metadata?: Record<string, string> }
}

interface ProfileRow {
    nickname?: string
    avatar?: string
    display_name?: string
}

function hexA(hex: string, a: number): string {
    const h = (hex || "").replace("#", "").trim()
    if (h.length !== 6) return `rgba(108, 92, 231, ${a})`
    const r = parseInt(h.slice(0, 2), 16)
    const g = parseInt(h.slice(2, 4), 16)
    const b = parseInt(h.slice(4, 6), 16)
    if ([r, g, b].some((n) => Number.isNaN(n))) return `rgba(108, 92, 231, ${a})`
    return `rgba(${r}, ${g}, ${b}, ${a})`
}

// hex 배경을 amt(0~1) 만큼 진하게 — 호버 시 색만 살짝 어둡게.
function darken(hex: string, amt: number): string {
    const h = (hex || "").replace("#", "").trim()
    if (h.length !== 6) return hex
    const r = parseInt(h.slice(0, 2), 16)
    const g = parseInt(h.slice(2, 4), 16)
    const b = parseInt(h.slice(4, 6), 16)
    if ([r, g, b].some((n) => Number.isNaN(n))) return hex
    const f = (n: number) => Math.max(0, Math.round(n * (1 - amt)))
    return `rgb(${f(r)}, ${f(g)}, ${f(b)})`
}

function loadSession(): SupaSession | null {
    if (typeof window === "undefined") return null
    try {
        const raw = window.localStorage.getItem(SESSION_KEY)
        return raw ? (JSON.parse(raw) as SupaSession) : null
    } catch (e) {
        return null
    }
}

// 프로필(닉네임·아바타) 캐시 — 재마운트 시 fetch 전에 즉시 표시(이메일 플래시 방지).
function loadCachedProfile(): ProfileRow | null {
    if (typeof window === "undefined") return null
    try {
        const raw = window.localStorage.getItem(PROFILE_CACHE_KEY)
        return raw ? (JSON.parse(raw) as ProfileRow) : null
    } catch (e) {
        return null
    }
}

function saveCachedProfile(row: ProfileRow) {
    try {
        window.localStorage.setItem(PROFILE_CACHE_KEY, JSON.stringify({
            nickname: row.nickname || "",
            avatar: row.avatar || "",
            display_name: row.display_name || "",
        }))
    } catch (e) {}
}

function clearSession() {
    try { window.localStorage.removeItem(SESSION_KEY) } catch (e) {}
    try { window.localStorage.removeItem(PROFILE_CACHE_KEY) } catch (e) {}
    try { window.sessionStorage.removeItem("verity_session_init") } catch (e) {}
}

async function fetchProfile(
    url: string, anon: string, token: string, table: string, userId: string
): Promise<ProfileRow | null> {
    if (!url || !anon || !token || !userId) return null
    try {
        const res = await fetch(
            `${url}/rest/v1/${table}?id=eq.${encodeURIComponent(userId)}&select=nickname,avatar,display_name`,
            { headers: { apikey: anon, Authorization: `Bearer ${token}`, Accept: "application/json" } }
        )
        if (!res.ok) return null
        const rows = await res.json()
        return Array.isArray(rows) && rows[0] ? (rows[0] as ProfileRow) : null
    } catch (e) {
        return null
    }
}

async function serverLogout(url: string, anon: string, token: string) {
    try {
        await fetch(`${url}/auth/v1/logout`, {
            method: "POST",
            headers: { apikey: anon, Authorization: `Bearer ${token}` },
        })
    } catch (e) {}
}

const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif"

function readBodyDark(): boolean {
    // 기본 라이트(SSG 매칭). html[data-an-theme](커스텀코드/토글) → body[data-framer-theme] → localStorage(verity_theme).
    try {
        if (typeof document !== "undefined") {
            const h = document.documentElement ? document.documentElement.dataset.anTheme : null
            if (h === "dark") return true
            if (h === "light") return false
            if (document.body) {
                const a = document.body.dataset.framerTheme
                if (a === "dark") return true
                if (a === "light") return false
            }
        }
        const s = typeof localStorage !== "undefined" ? localStorage.getItem("verity_theme") : null
        if (s === "dark") return true
    } catch (e) {}
    return false
}

export default function PublicMenuAccount(props: {
    variant?: string
    supabaseUrl?: string
    supabaseAnonKey?: string
    profileTable?: string
    loginRedirect?: string
    logoutRedirect?: string
    profileRedirect?: string
    avatarSize?: number
    showLogout?: boolean
    loginBg?: string
    loginText?: string
    accent?: string
    fill?: string
    ink?: string
    sub?: string
    style?: React.CSSProperties
}) {
    const {
        variant = "account",
        supabaseUrl = "",
        supabaseAnonKey = "",
        profileTable = "profiles",
        loginRedirect = "/login",
        logoutRedirect = "/login",
        profileRedirect = "/profile",
        avatarSize = 36,
        showLogout = true,
        loginBg = "#6C5CE7",
        loginText = "#FFFFFF",
        accent = "#6c5ce7",
        fill: fillProp = "#f5f6f8",
        ink: inkProp = "#191f28",
        sub: subProp = "#8b95a1",
        style,
    } = props

    const url = (supabaseUrl || "").replace(/\/+$/, "")
    const isCanvas = RenderTarget.current() === RenderTarget.canvas

    // 다크모드 자가감지 — nav 계정 위젯이 사이트 테마 추종(2026-07-20). 라이트=프롭 색 유지, 다크=사이트 표준.
    const [themeDark, setThemeDark] = useState<boolean>(false)
    useEffect(() => {
        if (isCanvas) return
        const readT = () => setThemeDark(readBodyDark())
        readT()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(readT)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [isCanvas])
    const fill = themeDark ? "#1e242c" : fillProp
    const ink = themeDark ? "#e3e7ec" : inkProp
    const sub = themeDark ? "#828d9b" : subProp

    // 세션·프로필을 마운트 시 localStorage 에서 동기 로드 → 재마운트 즉시 올바른 상태(플래시 없음).
    const [session, setSession] = useState<SupaSession | null>(() => (isCanvas ? null : loadSession()))
    const [profile, setProfile] = useState<ProfileRow | null>(() => (isCanvas ? null : loadCachedProfile()))
    const [busy, setBusy] = useState(false)
    const [btnHov, setBtnHov] = useState(false)
    const [cardHov, setCardHov] = useState(false)
    const [logoutHov, setLogoutHov] = useState(false)
    const [avatarHov, setAvatarHov] = useState(false)

    useEffect(() => {
        if (isCanvas) return
        const s = loadSession()
        setSession(s)
        if (s && s.access_token && s.user && s.user.id) {
            fetchProfile(url, supabaseAnonKey, s.access_token, profileTable, s.user.id).then((row) => {
                if (row) { setProfile(row); saveCachedProfile(row) }
            })
        } else {
            setProfile(null)
        }
    }, [isCanvas, url, supabaseAnonKey, profileTable])

    const go = useCallback((dest: string) => {
        if (typeof window !== "undefined" && dest) window.location.assign(dest)
    }, [])

    const doLogout = useCallback(async () => {
        if (busy) return
        setBusy(true)
        const s = loadSession()
        if (s && s.access_token) await serverLogout(url, supabaseAnonKey, s.access_token)
        clearSession()
        go(logoutRedirect || loginRedirect)
    }, [busy, url, supabaseAnonKey, logoutRedirect, loginRedirect, go])

    const loggedIn = isCanvas ? true : !!(session && session.access_token && session.user)
    // 이메일 fallback 제거 — 캐시 닉네임(없으면 '내 계정'). 세션 이메일이 잠깐 뜨는 플래시 원천 차단.
    const nickname =
        (profile && (profile.nickname || profile.display_name)) ||
        (isCanvas ? "길동무" : "내 계정")
    const avatar = (profile && profile.avatar) || ""
    const initial = (nickname || "?").trim().charAt(0).toUpperCase()

    const circle: React.CSSProperties = {
        width: avatarSize, height: avatarSize, borderRadius: "50%", overflow: "hidden",
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
    }
    const avatarNode = avatar ? (
        <div style={{ ...circle, background: fill }}>
            <img src={avatar} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        </div>
    ) : (
        <div style={{ ...circle, background: accent }}>
            <span style={{ color: "#fff", fontWeight: 800, fontSize: Math.round(avatarSize * 0.42), fontFamily: FONT }}>
                {initial}
            </span>
        </div>
    )

    // ── variant: avatar (프로필 링크 버튼용) — hover 살짝 어둡게(brightness) ──
    if (variant === "avatar") {
        return (
            <div
                onClick={() => go(loggedIn ? profileRedirect : loginRedirect)}
                onMouseEnter={() => setAvatarHov(true)}
                onMouseLeave={() => setAvatarHov(false)}
                style={{
                    display: "inline-flex", cursor: "pointer", borderRadius: "50%",
                    filter: avatarHov ? "brightness(0.93)" : "none",
                    transition: "filter 0.15s ease",
                    ...style,
                }}
            >
                {loggedIn ? avatarNode : (
                    <div style={{ ...circle, background: fill }}>
                        <User size={Math.round(avatarSize * 0.52)} color={sub} weight="fill" />
                    </div>
                )}
            </div>
        )
    }

    // ── 로그아웃 상태 — 솔리드 보라(#6C5CE7) + 흰 텍스트(라이트·다크 동일). hover 배경만 살짝 진하게 ──
    if (!loggedIn) {
        return (
            <div
                onClick={() => go(loginRedirect)}
                onMouseEnter={() => setBtnHov(true)}
                onMouseLeave={() => setBtnHov(false)}
                style={{
                    display: "flex", alignItems: "center", justifyContent: "center", gap: 7,
                    padding: "11px 14px", borderRadius: 13, cursor: "pointer", fontFamily: FONT,
                    background: btnHov ? darken(loginBg, 0.09) : loginBg,
                    transition: "background 0.15s ease",
                    ...style,
                }}
            >
                <SignIn size={17} color={loginText} weight="bold" />
                <span style={{ fontWeight: 800, fontSize: 13.5, color: loginText }}>로그인 / 회원가입</span>
            </div>
        )
    }

    // ── 로그인 상태 — 카드(현행 디자인) + hover 배경만 살짝 진하게 ──
    return (
        <div
            onMouseEnter={() => setCardHov(true)}
            onMouseLeave={() => { setCardHov(false); setLogoutHov(false) }}
            style={{
                display: "flex", alignItems: "center", gap: 9,
                padding: "8px 10px", borderRadius: 13, fontFamily: FONT,
                background: cardHov ? darken(fill, 0.06) : fill,
                transition: "background 0.15s ease",
                ...style,
            }}
        >
            <div
                onClick={() => go(profileRedirect)}
                style={{ display: "flex", alignItems: "center", gap: 9, flex: 1, minWidth: 0, cursor: "pointer" }}
            >
                {avatarNode}
                <div style={{ minWidth: 0 }}>
                    <div style={{
                        fontWeight: 800, fontSize: 13.5, color: ink,
                        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                    }}>
                        {nickname}
                    </div>
                    <div style={{ fontSize: 10.5, fontWeight: 600, marginTop: 1, color: sub }}>프로필 보기</div>
                </div>
                {!showLogout && <CaretRight size={15} color={sub} weight="bold" />}
            </div>
            {showLogout && (
                <div
                    onClick={doLogout}
                    onMouseEnter={() => setLogoutHov(true)}
                    onMouseLeave={() => setLogoutHov(false)}
                    title="로그아웃"
                    style={{
                        display: "flex", cursor: busy ? "default" : "pointer", padding: 6, borderRadius: 9,
                        background: logoutHov ? hexA(sub, 0.16) : "transparent",
                        opacity: busy ? 0.4 : 1, transition: "background 0.15s ease",
                    }}
                >
                    <SignOut size={17} color={logoutHov ? ink : sub} weight="bold" />
                </div>
            )}
        </div>
    )
}

addPropertyControls(PublicMenuAccount, {
    variant: {
        type: ControlType.Enum, title: "형태",
        options: ["account", "avatar"], optionTitles: ["계정 행", "아바타만"],
        defaultValue: "account",
    },
    supabaseUrl: { type: ControlType.String, title: "Supabase URL", defaultValue: "", placeholder: "https://xxxxx.supabase.co" },
    supabaseAnonKey: { type: ControlType.String, title: "Anon Key", defaultValue: "" },
    profileTable: { type: ControlType.String, title: "프로필 테이블", defaultValue: "profiles" },
    loginRedirect: { type: ControlType.String, title: "로그인 경로", defaultValue: "/login" },
    logoutRedirect: { type: ControlType.String, title: "로그아웃 후 경로", defaultValue: "/login" },
    profileRedirect: { type: ControlType.String, title: "프로필 경로", defaultValue: "/profile" },
    avatarSize: { type: ControlType.Number, title: "아바타 크기", defaultValue: 36, min: 24, max: 120, unit: "px" },
    showLogout: { type: ControlType.Boolean, title: "로그아웃 버튼", defaultValue: true, enabledTitle: "표시", disabledTitle: "숨김" },
    loginBg: { type: ControlType.Color, title: "로그인 버튼 배경", defaultValue: "#6C5CE7" },
    loginText: { type: ControlType.Color, title: "로그인 버튼 글자", defaultValue: "#FFFFFF" },
    accent: { type: ControlType.Color, title: "아바타 배경", defaultValue: "#6c5ce7" },
    fill: { type: ControlType.Color, title: "카드 채움색", defaultValue: "#f5f6f8" },
    ink: { type: ControlType.Color, title: "닉네임 색", defaultValue: "#191f28" },
    sub: { type: ControlType.Color, title: "보조색", defaultValue: "#8b95a1" },
})
