"use client"
// StockFactsPanel — 종목별 자체 사실·출처·기준일을 보여 주는 오퍼레이터 전용 패널.
// 서버 생성형 종합은 2026-09-05 종료. 최종 해석은 Codex 세션이 같은 사실 번들을 읽고 수행한다.
import { useEffect, useState } from "react"
import { useDark, palette, cardStyle, FONT } from "@/lib/theme"
import { fetchAsk, askResultState, alphanestStockUrl, type AskResult, type FetchResult } from "@/lib/api"

const SOURCE_STATUS = { hit: "확인", no_record: "자료 없음", unavailable: "조회 불가", skipped: "조회 제외" }
const FETCH_STATUS = { received: "수신", cache_hit: "캐시 사용", unavailable: "조회 불가" }

export default function StockFactsPanel({ ticker }: { ticker: string }) {
    const dark = useDark()
    const c = palette(dark)
    const [response, setResponse] = useState<{ generation: number; result: FetchResult<AskResult> } | null>(null)
    const [open, setOpen] = useState(true)
    const selected = ticker.trim()
    const [request, setRequest] = useState({ ticker: selected, generation: 0 })
    // A→B→A에서도 같은 ticker의 과거 결과가 다시 보이지 않도록 선택 세대를 구분한다.
    if (request.ticker !== selected) {
        setRequest({ ticker: selected, generation: request.generation + 1 })
    }

    useEffect(() => {
        if (!request.ticker) return
        let cancelled = false
        const controller = new AbortController()
        fetchAsk(request.ticker, "", controller.signal).then((result) => {
            if (cancelled) return
            setResponse({ generation: request.generation, result })
        })
        return () => {
            cancelled = true
            controller.abort()
        }
    }, [request.ticker, request.generation])

    const result = selected && request.ticker === selected && response?.generation === request.generation ? response.result : null
    const facts = result?.ok ? result.data : null
    const status = !selected ? "idle" : !result ? "loading" : result.ok
        ? askResultState(result.data) : result.error === "auth" ? "auth" : "error"
    const closeSec = (facts?.sections || []).find((s) => s.source === "kr_close_latest.json" || s.label?.startsWith("종가"))
    const usQuote = (facts?.sections || []).find((s) => s.source === "yahoo:chart")
    const quote = usQuote || closeSec
    const quoteLabel = usQuote ? "미국 시세" : closeSec ? "종가" : "시세"
    const quoteAsOf = quote?.as_of ? `${quoteLabel} ${quote.as_of} 기준` : `${quoteLabel} 자료 기준일 미상`
    const n = facts?.sections?.length || 0
    const coverage = facts?.coverage
    const diagnostics = facts?.fetch_diagnostics || []
    const statusText = {
        idle: "종목을 선택하세요.", loading: "사실 조인 중…", auth: "오퍼레이터 로그인이 필요합니다.",
        error: "사실 조인 요청 실패", unresolved: "종목을 확인하지 못했습니다.",
        empty: "조회된 자료 없음", degraded: "일부 소스 확인 불가 — 확보한 자료만 표시", ready: "사실 조회됨",
    }[status]

    return (
        <div style={{ fontFamily: FONT, display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                <div style={{ color: c.ink, fontSize: 15, fontWeight: 800, letterSpacing: "-0.02em" }}>종목 사실</div>
                <div style={{ color: c.faint, fontSize: 10.5 }}>출처 · 기준일 · 신선도</div>
            </div>

            <div style={{ ...cardStyle(c, "12px 14px"), display: "flex", flexDirection: "column", gap: 9 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 11, fontWeight: 800, color: c.vt }}>{selected || "종목 미선택"}</span>
                    <span role="status" style={{ fontSize: 10, color: c.faint }}>
                        {statusText}
                        {facts ? ` · ${n}개 섹션 · ${quoteAsOf}` : ""}
                    </span>
                    {selected ? (
                        <a
                            href={alphanestStockUrl(selected)}
                            target="_blank"
                            rel="noreferrer"
                            style={{ marginLeft: "auto", fontSize: 10, color: c.vt, textDecoration: "none", fontWeight: 700 }}
                        >
                            알파네스트 리포트 ↗
                        </a>
                    ) : null}
                </div>

                {coverage ? (
                    <details style={{ fontSize: 11, color: c.sub }}>
                        <summary style={{ cursor: "pointer", lineHeight: 1.6 }}>
                            소스 점검 {coverage.checked}/{coverage.applicable} · 전체 {coverage.total} · 확인 {coverage.hit} · 자료 없음 {coverage.no_record} · 조회 불가 {coverage.unavailable} · 제외 {coverage.skipped}
                        </summary>
                        <div style={{ display: "flex", flexDirection: "column", gap: 5, marginTop: 7 }}>
                            {coverage.sources.map((source, i) => (
                                <div key={`${source.source}-${i}`} style={{ overflowWrap: "anywhere" }}>
                                    {source.label} · {SOURCE_STATUS[source.status]} · {source.as_of || "자료 기준일 미상"}
                                    {source.reason ? ` · ${source.reason}` : ""}
                                </div>
                            ))}
                        </div>
                    </details>
                ) : facts ? <div style={{ fontSize: 11, color: c.faint }}>소스 점검 정보 미제공</div> : null}
                {diagnostics.length ? (
                    <details style={{ fontSize: 11, color: c.sub }}>
                        <summary style={{ cursor: "pointer" }}>수집 진단 {diagnostics.length}건</summary>
                        <div style={{ display: "flex", flexDirection: "column", gap: 5, marginTop: 7 }}>
                            {diagnostics.map((item, i) => (
                                <div key={`${item.source}-${i}`} style={{ overflowWrap: "anywhere" }}>
                                    {item.source} · {FETCH_STATUS[item.status]}{item.reason ? ` · ${item.reason}` : ""}
                                </div>
                            ))}
                        </div>
                    </details>
                ) : null}
                {facts?.missing?.length ? (
                    <details style={{ fontSize: 10, color: c.faint }}>
                        <summary style={{ cursor: "pointer" }}>미확인 항목 {facts.missing.length}건</summary>
                        {facts.missing.map((item, i) => <div key={i} style={{ marginTop: 4 }}>{item}</div>)}
                    </details>
                ) : null}
                {result && !result.ok && status === "error" ? (
                    <div style={{ fontSize: 10, color: c.faint }}>요청 오류: {result.error}</div>
                ) : null}
                {facts?.facts_text ? (
                    <>
                        <button
                            onClick={() => setOpen((v) => !v)}
                            style={{ alignSelf: "flex-start", border: "none", background: "transparent", padding: 0, fontSize: 10, fontWeight: 700, color: c.faint, cursor: "pointer", fontFamily: FONT }}
                        >
                            {open ? "원본 사실 접기" : "원본 사실 펼치기"}
                        </button>
                        {open ? (
                            <pre style={{ margin: 0, maxHeight: 320, overflow: "auto", background: c.hi, borderRadius: 10, padding: "10px 12px", fontSize: 11, lineHeight: 1.5, color: c.sub, whiteSpace: "pre-wrap", fontFamily: FONT }}>
                                {facts.facts_text}
                            </pre>
                        ) : null}
                    </>
                ) : null}
            </div>

            <div style={{ fontSize: 10, color: c.faint, lineHeight: 1.45 }}>
                판단이 필요한 질문은 Codex가 이 번들과 원문 직조회를 함께 사용합니다.
            </div>
        </div>
    )
}
