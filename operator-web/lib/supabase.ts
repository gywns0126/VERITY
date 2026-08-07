"use client"
// 오퍼레이터 오리진 Supabase 인증 — 공개사이트(PublicAuth/PublicSessionKeeper)와 동일 프로젝트·
// 동일 세션키(verity_supabase_session)·동일 shape({access_token, refresh_token, expires_at}).
// 🚨 비밀번호 로그인 = 이 오리진의 "독립 세션 패밀리" 발급 → 공개사이트 세션과 refresh 회전 충돌 없음(정석).
//   세션 붙여넣기 폴백 = 같은 패밀리 공유라 회전 충돌 가능(붙여넣은 뒤 공개사이트 쪽이 로그아웃될 수 있음) — UI 에 경고 병기.
// anon key = 공개 클라이언트 키(브라우저 임베드 표준, PublicSessionKeeper 와 동일 값).
const SUPABASE_URL = "https://lykqebdcurreppowulsl.supabase.co"
const ANON_KEY =
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx5a3FlYmRjdXJyZXBwb3d1bHNsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzUwMTcyMTUsImV4cCI6MjA5MDU5MzIxNX0.JhwsWgsrdDJ12BzZZjR7o6jdS-Mxny2eSJeWq59DhNs"

const SESSION_KEY = "verity_supabase_session"
const LOCK_KEY = "verity_session_refresh_lock"
const LOCK_MS = 20000          // 다중 탭 동시 refresh 디바운스 (SessionKeeper 정합)
const REFRESH_MARGIN_S = 300   // 만료 5분 전 선제 갱신

export type Session = { access_token: string; refresh_token: string; expires_at: number; user_email?: string }

export function loadSession(): Session | null {
    try {
        const raw = localStorage.getItem(SESSION_KEY)
        if (!raw) return null
        const s = JSON.parse(raw)
        return s && s.access_token ? (s as Session) : null
    } catch {
        return null
    }
}

export function saveSession(s: Session): void {
    try {
        localStorage.setItem(SESSION_KEY, JSON.stringify(s))
    } catch {}
}

export function clearSession(): void {
    try {
        localStorage.removeItem(SESSION_KEY)
    } catch {}
}

async function tokenRequest(grant: string, body: Record<string, string>): Promise<Session> {
    const r = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=${grant}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", apikey: ANON_KEY },
        body: JSON.stringify(body),
    })
    const d = await r.json().catch(() => ({}))
    if (!r.ok || !d.access_token) {
        throw new Error(String(d.error_description || d.msg || d.error || `로그인 실패 (${r.status})`))
    }
    return {
        access_token: d.access_token,
        refresh_token: d.refresh_token || "",
        expires_at: d.expires_at || Math.floor(Date.now() / 1000) + (d.expires_in || 3600),
        user_email: d.user?.email,
    }
}

export async function signInPassword(email: string, password: string): Promise<Session> {
    const s = await tokenRequest("password", { email, password })
    saveSession(s)
    return s
}

/** 구글 OAuth 진입 URL — PublicAuth.getGoogleOAuthUrl 동일 패턴.
 * 🚨 redirect_to 는 Supabase Auth "Redirect URLs" 허용목록에 있어야 함(없으면 Site URL 로 폴백
 *   = 공개사이트로 튕겨 세션이 엉뚱한 오리진에 저장됨). 오퍼레이터 도메인 등록 = 대시보드 1회. */
export function googleAuthUrl(redirectTo: string): string {
    return `${SUPABASE_URL}/auth/v1/authorize?provider=google&redirect_to=${encodeURIComponent(redirectTo)}&apikey=${encodeURIComponent(ANON_KEY)}`
}

/** OAuth 복귀 해시(#access_token=...) 캡처 → 세션 저장 + URL 정리. 캡처 시 true. */
export function captureOAuthHash(): boolean {
    if (typeof window === "undefined") return false
    const h = window.location.hash
    if (!h || h.indexOf("access_token=") < 0) return false
    const p = new URLSearchParams(h.replace(/^#/, ""))
    const at = p.get("access_token")
    if (!at) return false
    const expiresAt = Number(p.get("expires_at")) ||
        Math.floor(Date.now() / 1000) + (Number(p.get("expires_in")) || 3600)
    saveSession({ access_token: at, refresh_token: p.get("refresh_token") || "", expires_at: expiresAt })
    try {
        window.history.replaceState({}, "", window.location.pathname + window.location.search)
    } catch {}
    return true
}

/** 세션 JSON 붙여넣기 폴백 — 공개사이트 콘솔의 verity_supabase_session 값 그대로. */
export function importSessionJson(raw: string): Session {
    const s = JSON.parse(raw.trim())
    if (!s || typeof s.access_token !== "string" || !s.access_token) throw new Error("access_token 없는 JSON")
    const sess: Session = {
        access_token: s.access_token,
        refresh_token: s.refresh_token || "",
        expires_at: Number(s.expires_at) || Math.floor(Date.now() / 1000) + 3600,
        user_email: s.user_email || s.email,
    }
    saveSession(sess)
    return sess
}

/** 만료 임박 시 refresh — 성공 true. 다중 탭 락(SessionKeeper 패턴, 회전 충돌 방지). */
export async function refreshIfNeeded(): Promise<boolean> {
    const s = loadSession()
    if (!s || !s.refresh_token) return false
    const now = Math.floor(Date.now() / 1000)
    if (s.expires_at && now < s.expires_at - REFRESH_MARGIN_S) return false
    try {
        const lock = Number(localStorage.getItem(LOCK_KEY) || 0)
        if (Date.now() - lock < LOCK_MS) return false
        localStorage.setItem(LOCK_KEY, String(Date.now()))
    } catch {}
    try {
        const next = await tokenRequest("refresh_token", { refresh_token: s.refresh_token })
        saveSession({ ...next, user_email: next.user_email || s.user_email })
        return true
    } catch {
        return false
    }
}

// ── 내 프로필 (계좌 라우팅·시드) — PM 2026-08-07 다계좌 ──────────────
// 회원 = 오퍼레이터 + 지인 1명. A안(각자 자기 계좌에서 자기가 승인)이라 화면은 항상
// **본인 것만** 보여준다. RLS 가 본인 행만 내주므로 여기서 별도 필터를 두지 않는다.
export type MyProfile = { broker_slug: string | null; seed_krw: number | null }

/** 본인 profiles 행 조회. 실패·미로그인 시 null (호출부는 실계좌 총액으로 폴백). */
export async function fetchMyProfile(): Promise<MyProfile | null> {
    const s = loadSession()
    if (!s?.access_token) return null
    try {
        const r = await fetch(
            `${SUPABASE_URL}/rest/v1/profiles?select=broker_slug,seed_krw&limit=1`,
            {
                headers: {
                    apikey: ANON_KEY,
                    Authorization: `Bearer ${s.access_token}`,
                    Accept: "application/json",
                },
            }
        )
        if (!r.ok) return null
        const rows = (await r.json()) as Array<Record<string, unknown>>
        if (!Array.isArray(rows) || !rows.length) return null
        const seed = Number(rows[0].seed_krw)
        return {
            broker_slug: (rows[0].broker_slug as string) || null,
            // 0·음수·NaN 은 배분 분모로 쓸 수 없다(0 나눗셈·부호 반전). null 로 떨어뜨려 폴백.
            seed_krw: isFinite(seed) && seed > 0 ? seed : null,
        }
    } catch {
        return null
    }
}
