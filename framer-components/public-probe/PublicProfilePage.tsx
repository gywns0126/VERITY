import { addPropertyControls, ControlType, RenderTarget } from "framer"
import React, { useEffect, useRef, useState } from "react"

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
    nickname: string   // 커뮤니티 표시명 (019 마이그레이션, 유일)
    avatar: string     // 128px JPEG base64 data-URL (~10KB, 인라인 저장)
    bio: string        // 한 줄 소개 (021 마이그레이션, ≤40자)
    is_admin: boolean  // 008 컬럼 — 관리자 버튼 노출 게이트(실제 차단은 /admin AdminGate + 서버)
}

const SAMPLE: Profile = {
    display_name: "홍길동",
    email: "user@example.com",
    phone: "010-1234-5678",
    status: "approved",
    created_at: "2026-04-01T00:00:00Z",
    nickname: "길동무",
    avatar: "",
    bio: "저평가 가치주 장기 보유",
    is_admin: true,
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
    if (typeof window === "undefined") return
    localStorage.removeItem(SESSION_KEY)
    // 🚨 로그아웃 = 기기 초기화(다음 사용자 익명 누출 차단) — 로컬 스크래치 클리어. verity_theme(기기설정) 유지.
    for (const k of ["verity_watchlist", "verity_last_ticker", "verity_recent_tickers", "verity_thesis_v1", "verity_thesis_migrated_v1"]) {
        try { localStorage.removeItem(k) } catch (e) {}
    }
    try { sessionStorage.removeItem("verity_session_init") } catch (e) {}   // 세션 가드 재평가 허용
}

async function fetchProfile(
    url: string, anon: string, token: string, table: string, userId: string
): Promise<Partial<Profile> | null> {
    if (!url || !anon || !token || !userId) return null
    try {
        // nickname/avatar(019)·bio(021) = 마이그레이션 컬럼 — 미적용 DB 면 400 → 단계 폴백(기존 표시 유지)
        const get = async (sel: string) => {
            const res = await fetch(
                `${url}/rest/v1/${table}?id=eq.${userId}&select=${sel}`,
                { headers: { apikey: anon, Authorization: `Bearer ${token}`, Accept: "application/json" } }
            )
            if (!res.ok) return null
            const rows = await res.json()
            return Array.isArray(rows) && rows[0] ? rows[0] : null
        }
        // created_at 포함 — OAuth 세션은 user.created_at 를 저장하지 않아 가입일이 비므로 profiles 행에서 채움
        return (await get("display_name,email,phone,status,created_at,nickname,avatar,bio,is_admin"))
            || (await get("display_name,email,phone,status,created_at,nickname,avatar,is_admin"))
            || (await get("display_name,email,phone,status,created_at,is_admin"))
            || (await get("display_name,email,phone,status,created_at"))
    } catch (e) {
        return null
    }
}

/* 프로필 부분 수정(별명·사진) — profiles_update_own RLS(003). 409 = 별명 중복(019 unique index). */
async function patchProfile(
    url: string, anon: string, token: string, table: string, userId: string, body: Record<string, string>
): Promise<{ ok: boolean; status: number }> {
    if (!url || !anon || !token || !userId) return { ok: false, status: 0 }
    try {
        const res = await fetch(`${url}/rest/v1/${table}?id=eq.${userId}`, {
            method: "PATCH",
            headers: {
                apikey: anon,
                Authorization: `Bearer ${token}`,
                "Content-Type": "application/json",
                Prefer: "return=minimal",
            },
            body: JSON.stringify(body),
        })
        return { ok: res.ok, status: res.status }
    } catch (e) {
        return { ok: false, status: 0 }
    }
}

/* 이미지 파일 → 128×128 중앙 크롭 JPEG data-URL (~10KB) — Storage 없이 인라인 저장(019 설계). */
function fileToAvatar(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
        const fr = new FileReader()
        fr.onerror = () => reject(new Error("read"))
        fr.onload = () => {
            const img = new Image()
            img.onerror = () => reject(new Error("img"))
            img.onload = () => {
                try {
                    const S = 128
                    const cv = document.createElement("canvas")
                    cv.width = S; cv.height = S
                    const ctx = cv.getContext("2d")
                    if (!ctx) { reject(new Error("ctx")); return }
                    const side = Math.min(img.width, img.height)
                    const sx = (img.width - side) / 2, sy = (img.height - side) / 2
                    ctx.drawImage(img, sx, sy, side, side, 0, 0, S, S)
                    resolve(cv.toDataURL("image/jpeg", 0.82))
                } catch (e) { reject(e as Error) }
            }
            img.src = String(fr.result)
        }
        fr.readAsDataURL(file)
    })
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
    adminPath: string
    dark: boolean
}

type Busy = "" | "logout" | "withdraw"
type Phase = "loading" | "guest" | "member"

// 🎨 페이지 이동 다크 번쩍임 제거(2026-07-20): 첫 마운트만 라이트(SSG/첫방문 매칭·stuck 방지) → 이후 마운트는 실제 테마 즉시.
let __anHyd = false
function anReadDark(): boolean {
    if (typeof document === "undefined") return false
    if (!__anHyd) {
        __anHyd = true
        return false
    }
    const h = document.documentElement ? document.documentElement.dataset.anTheme : null
    if (h === "dark") return true
    if (h === "light") return false
    return !!(document.body && document.body.dataset.framerTheme === "dark")
}


export default function PublicProfilePage(props: Props) {
    const supabaseUrl = (props.supabaseUrl || "").replace(/\/+$/, "")
    const supabaseAnonKey = props.supabaseAnonKey || ""
    const profileTable = props.profileTable || "profiles"
    const loginRedirect = props.loginRedirect || "/login"
    const logoutRedirect = props.logoutRedirect || "/login"
    // 관리자 버튼 = profiles.is_admin 계정에만 노출(UI 편의). 실제 접근 차단은 /admin AdminGate + 서버(admin.py).
    // is_admin 기반 → 관리자 추가 = DB(is_admin=true)만, 코드/이메일 하드코딩 불필요.
    const adminPath = props.adminPath || "/admin"

    const isCanvas = RenderTarget.current() === RenderTarget.canvas

    const [dark, setDark] = useState<boolean>(() => (RenderTarget.current() === RenderTarget.canvas ? !!props.dark : anReadDark()))
    const [phase, setPhase] = useState<Phase>(isCanvas ? "member" : "loading")
    const [confirming, setConfirming] = useState(false)
    const [busy, setBusy] = useState<Busy>("")
    const [profile, setProfile] = useState<Profile | null>(isCanvas ? SAMPLE : null)
    // 프로필 편집 — 인스타식 보기/편집 분리 (2026-07-10 PM 선택). 편집 = 사진/별명/소개 필드 리스트.
    const fileRef = useRef<HTMLInputElement>(null)
    const [editMode, setEditMode] = useState(false)
    const [nickDraft, setNickDraft] = useState("")
    const [bioDraft, setBioDraft] = useState("")
    const [editMsg, setEditMsg] = useState("")
    const [avatarBusy, setAvatarBusy] = useState(false)

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
            nickname: "",
            avatar: "",
            bio: "",
            is_admin: false,
        }
        setProfile(base)   // 폴백 준비 — fetch 실패/지연 시 이거라도 표시
        if (!s.access_token) { setPhase("member"); return }   // 토큰 없으면 보강 불가 → 즉시 표시
        // 🚨 phase="member" 를 fetchProfile 완료까지 미룸 — 로딩 스켈레톤이 실제 느린 구간(profiles+is_admin fetch)
        //   동안 보이게(2026-07-18, "로딩이 오류처럼 보임"). 안전 타임아웃(6s)으로 무한 스켈레톤 방지.
        let alive = true
        const settle = () => { if (alive) setPhase("member") }
        const to = setTimeout(settle, 6000)
        fetchProfile(supabaseUrl, supabaseAnonKey, s.access_token, profileTable, s.user.id).then((row) => {
            if (!alive) return
            clearTimeout(to)
            if (row) {
                setProfile({
                    display_name: row.display_name || base.display_name,
                    email: row.email || base.email,
                    phone: row.phone || base.phone,
                    status: row.status || base.status,
                    created_at: row.created_at || base.created_at,
                    nickname: (row as any).nickname || "",
                    avatar: (row as any).avatar || "",
                    bio: (row as any).bio || "",
                    is_admin: (row as any).is_admin === true,
                })
            }
            setPhase("member")
        })
        return () => { alive = false; clearTimeout(to) }
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

    /* 프로필 저장(별명+소개) — 별명 2~16자 한글·영문·숫자(._- 허용). 409 = 유일 인덱스 충돌(이미 사용 중). */
    const NICK_RE = /^[가-힣A-Za-z0-9._-]{2,16}$/
    const saveProfile = async () => {
        const v = nickDraft.trim()
        const b = bioDraft.trim().slice(0, 40)
        if (v && !NICK_RE.test(v)) { setEditMsg("별명은 2~16자, 한글·영문·숫자(._- 허용) · 공백 불가예요"); return }
        const s = loadSession()
        if (!s || !s.access_token || !s.user) return
        setEditMsg("")
        const patch = (body: Record<string, string>) =>
            patchProfile(supabaseUrl, supabaseAnonKey, s.access_token, profileTable, s.user.id, body)
        let r = await patch({ nickname: v, bio: b })
        if (!r.ok && r.status === 400) r = await patch({ nickname: v })   // 021 미적용 DB(bio 컬럼 부재) 폴백
        if (r.ok) {
            setProfile((p) => (p ? { ...p, nickname: v, bio: b } : p))
            setEditMode(false)
            setEditMsg("")
        } else {
            setEditMsg(r.status === 409 ? "이미 사용 중인 별명이에요" : "저장에 실패했어요 — 잠시 후 다시 시도해 주세요")
        }
    }

    /* 프로필 사진 — 파일 선택 → 128px 크롭 JPEG → PATCH. 실패 시 기존 유지(조용히). */
    const pickAvatar = () => { if (!avatarBusy && fileRef.current) fileRef.current.click() }
    const onAvatarFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const f = e.target.files && e.target.files[0]
        e.target.value = ""
        if (!f) return
        const s = loadSession()
        if (!s || !s.access_token || !s.user) return
        setAvatarBusy(true)
        try {
            const dataUrl = await fileToAvatar(f)
            if (dataUrl.length > 120000) throw new Error("too_big")   // DB CHECK(150K) 전 클라이언트 상한
            const r = await patchProfile(supabaseUrl, supabaseAnonKey, s.access_token, profileTable, s.user.id, { avatar: dataUrl })
            if (r.ok) setProfile((p) => (p ? { ...p, avatar: dataUrl } : p))
        } catch (err) { /* 기존 아바타 유지 */ }
        setAvatarBusy(false)
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
        borderRadius: 22,
        boxShadow: "0 2px 16px rgba(0,0,0,0.06)",
        padding: 28,
        boxSizing: "border-box",
    }

    if (phase === "loading") {
        // 스켈레톤 — 최초 로딩(세션+profiles+is_admin fetch) 동안 카드 형태를 본떠 표시.
        //   빈 화면/텍스트 한 줄 = 오류처럼 보이던 문제 해소(2026-07-18). 관리자든 아니든 로딩 phase 공통.
        const skBase = dark ? "#232a33" : "#e7eaee"
        const skHi = dark ? "#2f3742" : "#f3f5f8"
        const skBar = (w: number | string, h: number, r: number = 8, mt: number = 0): React.CSSProperties => ({
            width: w, height: h, borderRadius: r, marginTop: mt, flexShrink: 0,
            background: `linear-gradient(90deg, ${skBase} 25%, ${skHi} 37%, ${skBase} 63%)`,
            backgroundSize: "800px 100%",
            animation: "ppShimmer 1.4s ease-in-out infinite",
        })
        return (
            <div style={wrap}>
                <style>{`@keyframes ppShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={cardStyle} aria-busy="true" aria-label="프로필 불러오는 중">
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                        <div style={{ ...skBar(80, 80, 26), marginBottom: 14 }} />
                        <div style={skBar(120, 20, 7)} />
                        <div style={skBar(172, 13, 6, 10)} />
                        <div style={skBar(76, 24, 20, 16)} />
                        <div style={skBar(96, 34, 18, 16)} />
                        <div style={skBar(72, 30, 16, 10)} />
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 26 }}>
                        <div style={skBar(48, 13, 6)} />
                        <div style={skBar(112, 15, 6)} />
                    </div>
                    <div style={skBar("100%", 52, 14, 24)} />
                    <div style={{ display: "flex", justifyContent: "center", marginTop: 14 }}>
                        <div style={skBar(64, 13, 6)} />
                    </div>
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
                {/* 헤더 — 인스타식 보기/편집 분리: 보기 = 표시 전용, 편집 = 사진/별명/소개 필드 리스트 */}
                <input ref={fileRef} type="file" accept="image/*" style={{ display: "none" }} onChange={onAvatarFile} />
                {!editMode ? (
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center" }}>
                        <div style={{ width: 80, height: 80, borderRadius: 26, background: C.field, display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 14, overflow: "hidden" }}>
                            {profile && profile.avatar ? (
                                <img src={profile.avatar} alt="" width={80} height={80}
                                    style={{ width: 80, height: 80, objectFit: "cover", display: "block" }} />
                            ) : (
                                <BustAvatar size={50} color={C.sub} />
                            )}
                        </div>
                        <div style={{ color: C.ink, fontSize: 20, fontWeight: 800, letterSpacing: -0.4 }}>
                            {profile && profile.nickname ? profile.nickname : name}
                        </div>
                        {profile && profile.bio ? (
                            <div style={{ color: C.sub, fontSize: 12.5, fontWeight: 500, marginTop: 5, lineHeight: 1.4 }}>{profile.bio}</div>
                        ) : null}
                        <div style={{ color: C.faint, fontSize: 12.5, fontFamily: FONT_MONO, marginTop: 5 }}>
                            {profile ? profile.email : ""}
                        </div>
                        <span style={{ marginTop: 12, display: "inline-flex", alignItems: "center", padding: "4px 12px", borderRadius: 999, background: sm.bg, color: sm.fg, fontSize: 11.5, fontWeight: 700 }}>
                            {sm.label}
                        </span>
                        <button type="button"
                            onClick={() => { setNickDraft((profile && profile.nickname) || ""); setBioDraft((profile && profile.bio) || ""); setEditMode(true); setEditMsg("") }}
                            style={{ marginTop: 16, border: "none", cursor: "pointer", background: C.field, color: C.ink, fontSize: 12.5, fontWeight: 700, fontFamily: FONT, padding: "8px 20px", borderRadius: 999 }}>
                            프로필 편집
                        </button>
                        {profile && profile.is_admin === true ? (
                            <button type="button"
                                onClick={() => go(adminPath)}
                                style={{ marginTop: 18, marginBottom: 10, border: "none", cursor: "pointer", background: "#ffffff", color: "#191f28", fontSize: 12.5, fontWeight: 700, fontFamily: FONT, padding: "8px 20px", borderRadius: 999 }}>
                            관리자
                        </button>
                        ) : null}
                    </div>
                ) : (
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
                        <button type="button" onClick={pickAvatar} title="프로필 사진 변경" aria-label="프로필 사진 변경"
                            style={{ position: "relative", width: 80, height: 80, borderRadius: 26, background: C.field, display: "flex", alignItems: "center", justifyContent: "center", border: "none", padding: 0, cursor: avatarBusy ? "wait" : "pointer", opacity: avatarBusy ? 0.55 : 1 }}>
                            {profile && profile.avatar ? (
                                <img src={profile.avatar} alt="" width={80} height={80}
                                    style={{ width: 80, height: 80, borderRadius: 26, objectFit: "cover", display: "block" }} />
                            ) : (
                                <BustAvatar size={50} color={C.sub} />
                            )}
                        </button>
                        <button type="button" onClick={pickAvatar}
                            style={{ marginTop: 10, border: "none", background: "transparent", cursor: "pointer", color: C.blue, fontSize: 12.5, fontWeight: 700, fontFamily: FONT, padding: 0 }}>
                            {avatarBusy ? "업로드 중…" : "사진 변경"}
                        </button>
                        {/* 필드 리스트 — 라벨 + 밑줄 입력 행 */}
                        <div style={{ width: "100%", marginTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "11px 14px", background: C.field, borderRadius: 12 }}>
                                <span style={{ width: 44, flexShrink: 0, color: C.faint, fontSize: 12.5, fontWeight: 600 }}>별명</span>
                                <input value={nickDraft} autoFocus maxLength={16} placeholder="2~16자"
                                    onChange={(e) => setNickDraft(e.target.value)}
                                    onKeyDown={(e) => { if (e.key === "Enter") saveProfile() }}
                                    style={{ flex: 1, border: "none", outline: "none", background: "transparent", fontSize: 14, fontWeight: 700, fontFamily: FONT, color: C.ink, padding: 0 }} />
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "11px 14px", background: C.field, borderRadius: 12 }}>
                                <span style={{ width: 44, flexShrink: 0, color: C.faint, fontSize: 12.5, fontWeight: 600 }}>소개</span>
                                <input value={bioDraft} maxLength={40} placeholder="한 줄 소개 (선택)"
                                    onChange={(e) => setBioDraft(e.target.value)}
                                    onKeyDown={(e) => { if (e.key === "Enter") saveProfile() }}
                                    style={{ flex: 1, border: "none", outline: "none", background: "transparent", fontSize: 14, fontWeight: 500, fontFamily: FONT, color: C.ink, padding: 0 }} />
                            </div>
                        </div>
                        {editMsg ? (
                            <div style={{ marginTop: 10, fontSize: 11.5, fontWeight: 700, color: C.red }}>{editMsg}</div>
                        ) : null}
                        <div style={{ display: "flex", gap: 4, justifyContent: "center", marginTop: 14 }}>
                            <button type="button" onClick={() => { setEditMode(false); setEditMsg("") }}
                                style={{ border: "none", background: "transparent", cursor: "pointer", padding: "7px 14px", borderRadius: 999, fontSize: 12.5, fontWeight: 700, fontFamily: FONT, color: C.faint }}>취소</button>
                            <button type="button" onClick={saveProfile}
                                style={{ border: "none", background: C.ink, color: C.card, cursor: "pointer", padding: "7px 18px", borderRadius: 999, fontSize: 12.5, fontWeight: 800, fontFamily: FONT }}>저장</button>
                        </div>
                    </div>
                )}

                {/* 가입 정보 — 빈 값 행은 숨김 (구글 OAuth = 전화번호 미수집) */}
                <div style={{ marginTop: 20 }}>
                    {profile && profile.phone ? <InfoRow C={C} label="전화번호" value={profile.phone} mono /> : null}
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
                    <div style={{ marginTop: 22, background: C.redSoft, borderRadius: 16, padding: 16 }}>
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

                {/* 이용약관(/policy) 링크 — 회원 탈퇴 아래, 카드 내부 */}
                <a href="/policy" style={{ display: "block", textAlign: "center", marginTop: 18, color: C.faint, fontSize: 12, fontWeight: 600, textDecoration: "none" }}>이용약관 · 개인정보처리방침</a>
            </div>
        </div>
    )
}

function InfoRow(props: { C: typeof LIGHT; label: string; value: string; mono?: boolean }) {
    const C = props.C
    return (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 0" }}>
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
        flex: 1, padding: "11px 0", border: "none", borderRadius: 12,
        background: C.field, color: C.sub, fontSize: 13.5, fontWeight: 700, fontFamily: FONT, cursor: "pointer",
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
    adminPath: { type: ControlType.String, title: "관리자 경로", defaultValue: "/admin" },
    dark: { type: ControlType.Boolean, title: "Dark (정적)", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})
