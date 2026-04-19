/**
 * 관심종목(WatchGroups) 공통 API 유틸
 * StockSearch, StockDashboard, USAnalystView 등에서 공유.
 *
 * 인증: localStorage의 verity_supabase_session에서 access_token을 읽어
 *       Authorization: Bearer <token> 헤더로 전송. 서버는 이 JWT로 사용자를
 *       식별하므로 user_id는 더 이상 쿼리/바디에 포함하지 않는다.
 */

const FETCH_OPTS: RequestInit = { mode: "cors", credentials: "omit" }
const SESSION_KEY = "verity_supabase_session"

/** localStorage에서 Supabase 세션의 access_token 을 읽는다. 없으면 빈 문자열. */
export function getAccessToken(): string {
    if (typeof window === "undefined") return ""
    try {
        const raw = localStorage.getItem(SESSION_KEY)
        if (!raw) return ""
        const s = JSON.parse(raw)
        return (s && typeof s.access_token === "string") ? s.access_token : ""
    } catch {
        return ""
    }
}

/**
 * @deprecated 서버는 access_token(JWT)을 기반으로 user를 식별한다.
 * 기존 호출부 호환용으로만 유지. 새 코드는 getAccessToken() 사용.
 */
export function getVerityUserId(): string {
    if (typeof window === "undefined") return "anon"
    let uid = localStorage.getItem("verity_user_id")
    if (!uid) {
        uid = crypto.randomUUID?.() || `u-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
        localStorage.setItem("verity_user_id", uid)
    }
    return uid
}

function _authHeaders(extra: Record<string, string> = {}): Record<string, string> {
    const token = getAccessToken()
    const h: Record<string, string> = { ...extra }
    if (token) h["Authorization"] = `Bearer ${token}`
    return h
}

export interface WatchGroup {
    id: string
    name: string
    color: string
    icon: string
    sort_order: number
    items: { id: string; ticker: string; name: string; market: string }[]
}

export async function fetchWatchGroups(apiBase: string): Promise<WatchGroup[]> {
    if (!getAccessToken()) return []
    try {
        const res = await fetch(
            `${apiBase}/api/watchgroups`,
            { ...FETCH_OPTS, headers: _authHeaders() },
        )
        if (!res.ok) return []
        const data = await res.json()
        return Array.isArray(data) ? data : []
    } catch {
        return []
    }
}

export async function addWatchItem(
    apiBase: string,
    groupId: string,
    ticker: string,
    name: string,
    market: "kr" | "us",
): Promise<boolean> {
    if (!getAccessToken()) return false
    try {
        const res = await fetch(`${apiBase}/api/watchgroups`, {
            method: "POST",
            headers: _authHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({
                action: "add_item",
                group_id: groupId,
                ticker,
                name,
                market,
            }),
            ...FETCH_OPTS,
        })
        return res.ok
    } catch {
        return false
    }
}
