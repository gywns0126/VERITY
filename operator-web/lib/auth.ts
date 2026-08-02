"use client"
// 오퍼레이터 인증 — Supabase 세션(verity_supabase_session) 기반 Bearer JWT.
// 프레이머 컴포넌트의 _operatorAuthHeaders 복붙을 단일 소스로.
// 🚨 오퍼레이터 데이터(Brain grounding)는 authed /api/admin?type= 로만. 공개 blob 직독 금지.
// TODO(보안 상향, v2): @supabase/ssr httpOnly 쿠키 + 서버사이드 service_role fetch 로 이전
//   (localStorage JWT = XSS 노출면). 현 v1 = 기존 백엔드(/api/admin Bearer) 즉시 호환 우선.
const SESSION_KEY = "verity_supabase_session"

export function getJwt(): string | null {
    try {
        const raw = typeof localStorage !== "undefined" ? localStorage.getItem(SESSION_KEY) : null
        if (!raw) return null
        const s = JSON.parse(raw)
        const ok = !s.expires_at || Date.now() / 1000 <= s.expires_at
        return ok ? s.access_token || null : null
    } catch {
        return null
    }
}

export function authHeaders(): Record<string, string> {
    const jwt = getJwt()
    return jwt ? { Authorization: `Bearer ${jwt}` } : {}
}

export function isAuthed(): boolean {
    return getJwt() !== null
}
