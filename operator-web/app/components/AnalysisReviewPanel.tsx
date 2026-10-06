"use client"
// Private read-only harness projection. Never fetch a public fallback or run a model.
import { useEffect, useState } from "react"
import { API_BASE } from "@/lib/api"
import { authHeaders, refreshAuth } from "@/lib/auth"
import { useDark, palette, FONT } from "@/lib/theme"
import StockFactsPanel from "./StockFactsPanel"

type Review = {
    verdict: string; confidence: string; reviewed_at: string; valid_until: string
    reasoning_brief: string; counterevidence: string; limitations: string
    change_conditions: string[]; unresolved: string[]
    coverage: { reviewed: number; section_total: number; not_used: number; primary_supported_basis: number; basis_total: number }
    evidence: { claim: string; value: string; url: string; source_as_of: string; status: string }[]
}
type Result = {
    ticker: string; state: "not_reviewed" | "awaiting_review" | "reviewed" | "review_expired"
    facts_at?: string; packet_id?: string; section_total?: number
    sources?: { total: number; counts: Record<string, number>; entries: {source: string; state: string}[] }
    review?: Review | null
}
const date = (value?: string) => value ? new Date(value).toLocaleString("ko-KR") : "—"
function safeUrl(value: string): string | undefined {
    try { const u = new URL(value); return ["https:", "http:"].includes(u.protocol) && !u.username && !u.password ? u.href : undefined } catch { return undefined }
}

export default function AnalysisReviewPanel({ ticker }: { ticker: string }) {
    const c = palette(useDark())
    const [result, setResult] = useState<Result | null>(null)
    const [error, setError] = useState("")
    const [epoch, setEpoch] = useState(0)
    const [factsTicker, setFactsTicker] = useState<string | null>(null)
    const [, setExpiryTick] = useState(0)
    // One summary read on selection/manual refresh. No interval or automatic facts collection.
    useEffect(() => {
        const abort = new AbortController()
        let cancelled = false
        setResult(null); setError("")
        // The deadline covers shared auth refresh, GET and response parsing.
        const deadline = setTimeout(() => {
            if (!cancelled) setError("검토 기록 조회 시간이 초과되었습니다. 다시 시도해 주세요.")
            abort.abort()
        }, 30000)
        void (async () => {
            try {
                await refreshAuth()
                if (cancelled || abort.signal.aborted) return
                const headers = authHeaders()
                if (!headers.Authorization) throw new Error("관리자 로그인이 필요합니다.")
                const r = await fetch(`${API_BASE}/api/analysis_review?ticker=${encodeURIComponent(ticker)}`, {
                    method: "GET", headers, cache: "no-store", signal: abort.signal,
                })
                if (!r.ok) throw new Error(r.status === 401 || r.status === 403 ? "관리자 권한을 확인해 주세요." : "검토 기록을 불러오지 못했습니다.")
                const body = await r.json() as Result
                if (body.ticker !== ticker || !["not_reviewed", "awaiting_review", "reviewed", "review_expired"].includes(body.state)) throw new Error("검토 기록 형식이 일치하지 않습니다.")
                if (!cancelled && !abort.signal.aborted) setResult(body)
            } catch (e) {
                if (!cancelled && !abort.signal.aborted) setError(e instanceof Error ? e.message : "조회 실패")
            } finally {
                clearTimeout(deadline)
            }
        })()
        return () => { cancelled = true; clearTimeout(deadline); abort.abort() }
    }, [ticker, epoch])

    // A keyed child below resets any in-flight fact request when the ticker changes.
    const current = result?.ticker === ticker ? result : null
    const review = current?.review
    useEffect(() => {
        const expiresAt = Date.parse(review?.valid_until || "")
        if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) return
        let timer: ReturnType<typeof setTimeout>
        // One logical deadline; long waits are split only for the browser timer limit.
        const schedule = () => {
            const remaining = expiresAt - Date.now()
            if (remaining <= 0) { setExpiryTick(x => x + 1); return }
            timer = setTimeout(schedule, Math.min(remaining, 2147483647))
        }
        schedule()
        return () => clearTimeout(timer)
    }, [review?.valid_until])
    const expired = current?.state === "review_expired" || Boolean(review && Date.parse(review.valid_until) <= Date.now())
    const button = { border: "none", borderRadius: 8, background: c.hi, color: c.sub, padding: "6px 10px", cursor: "pointer", fontFamily: FONT, fontWeight: 700 }
    return <section data-analysis-harness="v1" style={{ fontFamily: FONT, display: "flex", flexDirection: "column", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
            <h3 style={{ margin: 0, fontSize: 15, fontWeight: 800, color: c.ink }}>분석 검토 · {ticker}</h3>
            <button style={button} onClick={() => setEpoch(x => x + 1)}>기록 새로고침</button>
        </div>
        {error ? <div role="alert" style={{ color: c.down }}>{error}</div> : !current ? <div role="status" style={{ color: c.faint }}>검토 기록 확인 중…</div> : <>
            <div style={{ color: expired ? c.amber : c.vt, fontWeight: 800 }}>
                {expired ? "재검토 필요 · 이전 판단" : current.state === "reviewed" ? "검토 기록" : current.state === "awaiting_review" ? "자료 준비됨 · 검토 대기" : "저장된 분석 없음"}
                {review ? ` — ${review.verdict} · 근거 확신 ${review.confidence}` : ""}
            </div>
            {!review ? <div style={{ fontSize: 12, color: c.sub }}>Codex에서 종목 분석과 근거 검토를 마친 뒤 저장·반영하면 여기에 표시됩니다.</div> : <>
                <p style={{ margin: 0, fontSize: 14, lineHeight: 1.65, color: c.ink, whiteSpace: "pre-wrap" }}>{review.reasoning_brief}</p>
                <div style={{ background: c.hi, borderRadius: 12, padding: 12, fontSize: 12, lineHeight: 1.65, color: c.sub }}>
                    <b>판단을 바꾸는 조건</b>
                    <ul style={{ margin: "5px 0 0", paddingLeft: 18 }}>{review.change_conditions.map((s, i) => <li key={i}>{s}</li>)}</ul>
                </div>
                <details style={{ fontSize: 12, color: c.sub }}><summary style={{ cursor: "pointer", fontWeight: 700 }}>근거·반대 근거·검토 범위</summary>
                    <p>반대 근거: {review.counterevidence}</p>
                    <p>한계: {review.limitations}</p>
                    {review.unresolved.length > 0 && <p>미해결: {review.unresolved.join(" · ")}</p>}
                    <p>섹션 검토 {review.coverage.reviewed}/{review.coverage.section_total} · 미사용 {review.coverage.not_used} · 원문 확인 근거축 {review.coverage.primary_supported_basis}/{review.coverage.basis_total}</p>
                    {review.evidence.map((e, i) => <p key={i}><a href={safeUrl(e.url)} target="_blank" rel="noreferrer" style={{ color: c.vt }}>{e.claim}: {e.value}</a> · {e.source_as_of} · {e.status}</p>)}
                </details>
                <div style={{ fontSize: 10, color: c.faint }}>검토 {date(review.reviewed_at)} · 재검토 기한 {date(review.valid_until)}</div>
            </>}
            {current.sources && <details style={{ fontSize: 11, color: c.faint }}><summary style={{ cursor: "pointer" }}>자료 포함 {current.sources.counts.in_bundle || 0}/{current.sources.total} · 원천 조회 성공률과는 다릅니다</summary>
                <p>미포함: {current.sources.entries.filter(x => x.state === "not_in_bundle").map(x => x.source).join(" · ") || "없음"}</p>
                <p>시장 제외: {current.sources.counts.excluded_market || 0} · 미포함은 부재·실패·표본 제한을 구별하지 않습니다.</p>
            </details>}
            {current.facts_at && <div style={{ fontSize: 10, color: c.faint }}>검토 자료 수집 {date(current.facts_at)} · 원천별 기준일은 다를 수 있습니다.</div>}
        </>}
        <button style={{ ...button, alignSelf: "flex-start" }} aria-expanded={factsTicker === ticker}
            onClick={() => setFactsTicker(selected => selected === ticker ? null : ticker)}>
            {factsTicker === ticker ? "현재 사실 닫기" : "현재 사실 별도 조회"}
        </button>
        {factsTicker === ticker && <div>
            <div style={{ fontSize: 11, color: c.faint, marginBottom: 8 }}>현재 조회 자료 · 저장된 판단과 별개</div>
            <StockFactsPanel key={ticker} ticker={ticker} />
        </div>}
        <div style={{ fontSize: 10, color: c.faint }}>저장된 검토 표시 · 자동 감시·자동 주문 없음</div>
    </section>
}
