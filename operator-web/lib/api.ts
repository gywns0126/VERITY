"use client"
// 데이터 fetch 단일 소스 — 프레이머의 fetchJson 복붙(16파일) 제거.
// authed(/api/admin) = 오퍼레이터 데이터 · public(blob) = 사실만(사실은 공개 OK).
import { authHeaders } from "./auth"

export const API_BASE = "https://project-yw131.vercel.app"
export const BLOB = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com"
// Railway 실시간 KIS 서버(FastAPI) — 시세/호가/캔들. KIS_SHARED_TOKEN 순수 소비자(발급 X, RULE 1).
// 🚨 배포 시 operator 오리진을 Railway ALLOWED_ORIGINS(server/config.py)에 추가해야 CORS 통과.
export const RAILWAY = "https://verity-production-1e44.up.railway.app"
// 공개 알파네스트 — 오퍼레이터에서 종목 리포트로 넘어가는 딥링크 대상(별트랙, 손대지 않음).
export const ALPHANEST = "https://www.alphanest.kr"

/** 공개 알파네스트 종목 리포트 딥링크. 오퍼레이터는 판단, 공개는 사실 리포트 — 역할 분리. */
export function alphanestStockUrl(ticker: string): string {
    return `${ALPHANEST}/stock?q=${encodeURIComponent(ticker)}`
}

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

/** 터미널 포트폴리오 — 슬림 라우트 우선(full 3.57MB = Safari 메모리 킬), 미배포 전환기만 full 폴백. */
export async function fetchPortfolioSlim<T = unknown>(): Promise<FetchResult<T>> {
    const r = await fetchOperator<T>("portfolio_terminal")
    if (r.ok || r.error === "auth") return r
    return fetchOperator<T>("portfolio_full")
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

// ── 온디맨드 사실 번들 (오퍼레이터 전용) ────────────────────────────────────
// 생성형 종합은 종료. 백엔드는 자체 사실·출처·기준일·결손 질문만 반환한다.
export type AskSection = {
    label: string
    source: string
    as_of?: string
    observed_at?: string
    source_periods?: Record<string, unknown>
    data: unknown
}
export type AskCoverage = {
    total: number
    applicable: number
    checked: number
    hit: number
    unavailable: number
    no_record: number
    skipped: number
    sources: Array<{
        source: string
        label: string
        status: "hit" | "no_record" | "unavailable" | "skipped"
        reason?: string | null
        as_of?: string | null
    }>
}
export type FetchDiagnostic = {
    source: string
    status: "received" | "cache_hit" | "unavailable"
    reason?: string | null
}
export type AskResult = {
    status?: "unresolved" | "empty" | "partial" | "ready"
    ticker?: string | null
    name?: string
    sections?: AskSection[]
    missing?: string[]
    collected_at?: string
    coverage?: AskCoverage | null
    fetch_diagnostics?: FetchDiagnostic[]
    facts_text?: string
    research_questions?: Array<{ key?: string; label?: string; query?: string; recency?: string }>
    contract?: { contract?: string; llm_calls?: number; final_reasoner?: string; legacy_chain_retired?: boolean }
    legacy_llm_retired?: boolean
}

export function askResultState(result: AskResult): "unresolved" | "empty" | "degraded" | "ready" {
    if (!result.ticker || result.status === "unresolved") return "unresolved"
    if (result.status === "empty") return "empty"
    if (result.status === "ready") return "ready"
    return "degraded"
}

export async function fetchAsk(ticker: string, question = "", signal?: AbortSignal): Promise<FetchResult<AskResult>> {
    const headers = authHeaders()
    if (!headers.Authorization) return { ok: false, status: 401, error: "auth" }
    const p = new URLSearchParams({ ticker })
    if (question) p.set("q", question)
    const url = `${API_BASE}/api/operator_ask?${p.toString()}`
    const options: RequestInit = { headers, cache: "no-store", signal }
    try {
        const r = await fetch(url, options).catch((e: unknown) => {
            // Retry one rejected transport request only; name also works across browser/VM realms.
            const transportFailure = typeof e === "object" && e !== null && "name" in e && e.name === "TypeError"
            if (signal?.aborted || !transportFailure) throw e
            return fetch(url, options)
        })
        if (r.status === 401 || r.status === 403) return { ok: false, status: r.status, error: "auth" }
        const data = await r.json().catch(() => null)
        if (!r.ok) return { ok: false, status: r.status, error: typeof data?.error === "string" ? data.error : "http" }
        if (!data || !Array.isArray(data.sections)) return { ok: false, status: r.status, error: "invalid_response" }
        return { ok: true, data: data as AskResult }
    } catch (e) {
        return { ok: false, status: 0, error: String(e) }
    }
}

// Railway 실시간 서버 (KIS 본인 이용, 발급 X 소비자). path 예: "quotes?tickers=005930,000660".
export async function fetchRailway<T = unknown>(path: string): Promise<FetchResult<T>> {
    try {
        const r = await fetch(`${RAILWAY}/${path}`, { cache: "no-store" })
        if (!r.ok) return { ok: false, status: r.status, error: "http" }
        return { ok: true, data: (await r.json()) as T }
    } catch (e) {
        return { ok: false, status: 0, error: String(e) }
    }
}
