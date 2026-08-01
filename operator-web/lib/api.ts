"use client"
// 데이터 fetch 단일 소스 — 프레이머의 fetchJson 복붙(16파일) 제거.
// authed(/api/admin) = 오퍼레이터 데이터 · public(blob) = 사실만(사실은 공개 OK).
import { authHeaders } from "./auth"

export const API_BASE = "https://project-yw131.vercel.app"
export const BLOB = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"

export type FetchResult<T> = { ok: true; data: T } | { ok: false; status: number; error: string }

// 오퍼레이터 authed — /api/admin?type=<name>. 미로그인/401 → auth 상태로 구분.
export async function fetchOperator<T = unknown>(type: string): Promise<FetchResult<T>> {
    const headers = authHeaders()
    if (!headers.Authorization) return { ok: false, status: 401, error: "auth" }
    try {
        const r = await fetch(`${API_BASE}/api/admin?type=${encodeURIComponent(type)}`, { headers })
        if (r.status === 401 || r.status === 403) return { ok: false, status: r.status, error: "auth" }
        if (!r.ok) return { ok: false, status: r.status, error: "http" }
        return { ok: true, data: (await r.json()) as T }
    } catch (e) {
        return { ok: false, status: 0, error: String(e) }
    }
}

// 공개 사실 blob (사실만 — 크라운주얼 아님). 인증 불필요.
export async function fetchPublic<T = unknown>(file: string): Promise<FetchResult<T>> {
    try {
        const r = await fetch(`${BLOB}/${file}`)
        if (!r.ok) return { ok: false, status: r.status, error: "http" }
        return { ok: true, data: (await r.json()) as T }
    } catch (e) {
        return { ok: false, status: 0, error: String(e) }
    }
}
