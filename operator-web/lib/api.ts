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

// ── 온디맨드 종합 (오퍼레이터 전용) ──────────────────────────────────────────
// 🚨 배치(tri_synthesis, 추천 상위 × 주1회)의 제약을 푸는 경로 — 임의 종목 즉시 조회.
//   llm=false → 알파네스트 발행 사실 조인만 (LLM 0 · 비용 0 · ~10s)
//   llm=true  → Perplexity(신선 외부) + Gemini(구조화) + Claude opus-5(종합) ~90s
//   백엔드 = vercel-api/api/operator_ask.py (authed, is_admin). 공개 노출 금지.
export type AskSection = { label: string; source: string; as_of?: string; data: unknown }
export type AskResult = {
    ticker?: string
    name?: string
    sections?: AskSection[]
    missing?: string[]
    collected_at?: string
    facts_text?: string
    synthesis?: { text?: string; refused?: boolean; category?: string; usage?: { in?: number; out?: number } }
    external?: { text?: string; citations?: unknown[] }
    budget?: string
    budget_blocked?: string
    cached?: boolean
}

export async function fetchAsk(ticker: string, question = "", llm = false): Promise<FetchResult<AskResult>> {
    const headers = authHeaders()
    if (!headers.Authorization) return { ok: false, status: 401, error: "auth" }
    const p = new URLSearchParams({ ticker })
    if (question) p.set("q", question)
    if (llm) p.set("llm", "1")
    try {
        const r = await fetch(`${API_BASE}/api/operator_ask?${p.toString()}`, { headers, cache: "no-store" })
        if (r.status === 401 || r.status === 403) return { ok: false, status: r.status, error: "auth" }
        if (!r.ok) return { ok: false, status: r.status, error: "http" }
        return { ok: true, data: (await r.json()) as AskResult }
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
