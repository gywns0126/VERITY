/**
 * 관심종목(WatchGroups) 공통 API 유틸
 * StockSearch, StockDashboard, USAnalystView 등에서 공유.
 */

const FETCH_OPTS: RequestInit = { mode: "cors", credentials: "omit" }

export function getVerityUserId(): string {
    if (typeof window === "undefined") return "anon"
    let uid = localStorage.getItem("verity_user_id")
    if (!uid) {
        uid = crypto.randomUUID?.() || `u-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
        localStorage.setItem("verity_user_id", uid)
    }
    return uid
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
    const uid = getVerityUserId()
    try {
        const res = await fetch(
            `${apiBase}/api/watchgroups?user_id=${encodeURIComponent(uid)}`,
            FETCH_OPTS,
        )
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
    const uid = getVerityUserId()
    try {
        await fetch(`${apiBase}/api/watchgroups`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                action: "add_item",
                user_id: uid,
                group_id: groupId,
                ticker,
                name,
                market,
            }),
            ...FETCH_OPTS,
        })
        return true
    } catch {
        return false
    }
}
