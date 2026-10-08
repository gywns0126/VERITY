"use client"
// Saved private reviews only: no collection, model execution, or automatic orders.
import { useEffect, useState } from "react"
import { API_BASE } from "@/lib/api"
import { authHeaders, refreshAuth } from "@/lib/auth"
import { selectTicker } from "@/lib/types"
import { useDark, palette, cardStyle, CARD_TITLE, RAIL_PAD, FONT } from "@/lib/theme"

type Item = {
    ticker: string; name: string; state: "awaiting_review" | "review_expired" | "reviewed"
    prepared_at: string; reviewed_at: string | null; valid_until: string | null
    verdict: string | null; confidence: string | null
}
type Queue = { schema: string; generated_at: string | null; total: number; items: Item[] }
const date = (value: string) => new Date(value).toLocaleDateString("ko-KR")

export default function ReviewQueue() {
    const c = palette(useDark())
    const [data, setData] = useState<Queue | null>(null)
    const [error, setError] = useState("")
    const [epoch, setEpoch] = useState(0)
    const [now, setNow] = useState(Date.now)
    useEffect(() => {
        const abort = new AbortController()
        let active = true
        setData(null); setError("")
        const onSession = (event: StorageEvent) => {
            if (event.key !== null && event.key !== "verity_supabase_session") return
            abort.abort(); setData(null); setEpoch(x => x + 1)
        }
        window.addEventListener("storage", onSession)
        const deadline = setTimeout(() => {
            if (active) setError("목록 조회 시간이 초과되었습니다. 다시 시도해 주세요.")
            abort.abort()
        }, 30000)
        void (async () => {
            try {
                await refreshAuth()
                if (!active || abort.signal.aborted) return
                const headers = authHeaders()
                if (!headers.Authorization) throw new Error("관리자 로그인이 필요합니다.")
                const response = await fetch(`${API_BASE}/api/analysis_review?view=queue`, { headers, cache: "no-store", credentials: "omit", redirect: "error", signal: abort.signal })
                if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? "관리자 권한을 확인해 주세요." : "재검토 목록을 불러오지 못했습니다.")
                const result = await response.json() as Queue
                if (headers.Authorization !== authHeaders().Authorization) throw new Error("로그인 상태가 변경되었습니다. 새로고침해 주세요.")
                if (result.schema !== "analysis-review-queue-v1" || !Array.isArray(result.items) || result.total !== result.items.length
                    || result.items.some(item => !item || !/^[A-Z0-9.^-]{1,20}$/.test(item.ticker) || !["awaiting_review", "review_expired", "reviewed"].includes(item.state)
                        || (item.state !== "awaiting_review" && !Number.isFinite(Date.parse(item.valid_until || ""))))) {
                    throw new Error("재검토 목록 형식이 일치하지 않습니다.")
                }
                if (active && !abort.signal.aborted) { setData(result); setNow(Date.now()) }
            } catch (e) {
                if (active && !abort.signal.aborted) setError(e instanceof Error ? e.message : "목록 조회 실패")
            } finally { clearTimeout(deadline) }
        })()
        return () => { active = false; abort.abort(); clearTimeout(deadline); window.removeEventListener("storage", onSession) }
    }, [epoch])

    // Expiry changes labels locally, not the stored verdict and not the network state.
    useEffect(() => {
        const next = Math.min(...(data?.items || []).map(item => Date.parse(item.valid_until || "")).filter(t => t > now))
        if (!Number.isFinite(next)) return
        const timer = setTimeout(() => setNow(Date.now()), Math.max(0, Math.min(next - Date.now() + 1, 2147483647)))
        return () => clearTimeout(timer)
    }, [data, now])
    const expired = (item: Item) => item.state === "review_expired" || (item.state === "reviewed" && Date.parse(item.valid_until || "") <= now)
    const pending = (data?.items || []).filter(item => item.state === "awaiting_review" || expired(item)).sort((a, b) => Number(expired(b)) - Number(expired(a)))
    const current = (data?.items || []).filter(item => item.state === "reviewed" && !expired(item))
    const row = (item: Item) => <button type="button" key={item.ticker} className="af-review-row" onClick={() => {
        selectTicker(item.ticker, item.name || item.ticker)
        document.getElementById("console-analysis")?.scrollIntoView({ behavior: "smooth", block: "start" })
    }} style={{ color: c.ink, borderColor: c.line }}>
        <span style={{ fontWeight: 800 }}>{item.name || item.ticker}{item.name && item.name !== item.ticker ? ` · ${item.ticker}` : ""}</span>
        <span style={{ fontSize: 12, color: expired(item) ? c.amber : c.sub }}>
            {expired(item) ? "기한 경과 · 재검토 필요" : item.state === "awaiting_review" ? "자료 준비됨 · 판단 대기" : `저장된 판단 · ${item.verdict}`}
        </span>
        {item.valid_until && <span style={{ fontSize: 10, color: c.faint }}>재검토 기한 {date(item.valid_until)}{expired(item) && item.verdict ? ` · 이전 판단 ${item.verdict}` : ""}</span>}
    </button>
    return <section data-review-queue="v1" style={{ ...cardStyle(c, RAIL_PAD), fontFamily: FONT }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
            <h2 style={{ ...CARD_TITLE, margin: 0 }}>재검토 목록{data ? ` · ${pending.length}` : ""}</h2>
            <button type="button" onClick={() => setEpoch(x => x + 1)} style={{ border: 0, borderRadius: 8, padding: "6px 8px", background: c.hi, color: c.sub, cursor: "pointer", fontFamily: FONT }}>새로고침</button>
        </div>
        <p style={{ fontSize: 11, color: c.faint, lineHeight: 1.5 }}>게시된 분석 기록 범위 · 관심 기업 전체를 자동 감시하는 목록은 아닙니다.</p>
        {error ? <p role="alert" style={{ color: c.down, fontSize: 12 }}>{error}</p> : !data ? <p role="status" style={{ color: c.sub, fontSize: 12 }}>목록 확인 중…</p> : <>
            {pending.map(row)}
            {!pending.length && <p style={{ color: c.sub, fontSize: 12 }}>{data.total ? "기한이 지난 기록이나 판단 대기 자료가 없습니다." : "아직 게시된 분석 기록이 없습니다."}</p>}
            {current.length > 0 && <details className="af-console-disclosure"><summary style={{ fontSize: 12 }}>기한 내 검토 기록 · {current.length}</summary>{current.map(row)}</details>}
            <p style={{ fontSize: 10, color: c.faint, marginBottom: 0 }}>전체 {data.total}건{data.generated_at ? ` · 게시 ${date(data.generated_at)}` : ""} · 종목 선택 시 근거 확인</p>
        </>}
    </section>
}
