"use client"
// TriSynthesisPanel — 3종 LLM 종합 분석 (② 판단 층 센터피스, 오퍼레이터 전용). 공개 알파네스트 디자인.
// StockSearch 가 쏜 verity-ticker / ?q= / verity_last_ticker 수신해 해당 종목 종합 표시.
// 되돌리지 말 것: fetchOperator("tri_synthesis") 만 읽음(Brain grounding=오퍼레이터 전용). 공개 blob 직독 금지.
//   RULE 7: LLM 의견=의견(provenance 분리 표기), Brain=가설(N<252) 라벨 필수.
import { useEffect, useState } from "react"
import { useDark, palette, cardStyle, FONT, type Palette } from "@/lib/theme"
import { fetchOperator, fetchAsk, alphanestStockUrl, type AskResult } from "@/lib/api"

const PPLX = "#20808d" // Perplexity teal
const GEM = "#4285f4" // Gemini blue

type Source = { content?: string; model?: string; citations?: string[] }
type Syn = {
    ticker?: string
    name?: string
    generated_at?: string
    sources?: { claude?: Source; perplexity?: Source; gemini?: Source }
    verity_trail?: { summary?: string; has_trail?: boolean }
}
type Data = { syntheses?: Record<string, Syn> }

function initialTicker(): string {
    try {
        const u = new URL(window.location.href)
        const q = u.searchParams.get("q")
        if (q) return q.toUpperCase()
        const last = localStorage.getItem("verity_last_ticker")
        if (last) return last.toUpperCase()
    } catch {}
    return ""
}

export default function TriSynthesisPanel() {
    const dark = useDark()
    const c = palette(dark)
    const [data, setData] = useState<Data | null>(null)
    const [status, setStatus] = useState<"loading" | "ok" | "auth" | "error">("loading")
    const [ticker, setTicker] = useState("")
    // 온디맨드 — 알파네스트 발행 사실 조인 + 요청 시 3종 LLM
    const [ask, setAsk] = useState<AskResult | null>(null)
    const [factsLoading, setFactsLoading] = useState(false)
    const [llmBusy, setLlmBusy] = useState(false)
    const [question, setQuestion] = useState("")
    const [askErr, setAskErr] = useState("")
    const [openFacts, setOpenFacts] = useState(false)

    useEffect(() => {
        setTicker(initialTicker())
        function onTicker(e: Event) {
            const d = (e as CustomEvent).detail
            const t = d && d.ticker ? String(d.ticker).toUpperCase() : ""
            if (t) setTicker(t)
        }
        window.addEventListener("verity-ticker", onTicker)
        return () => window.removeEventListener("verity-ticker", onTicker)
    }, [])

    useEffect(() => {
        let cancelled = false
        fetchOperator<Data>("tri_synthesis").then((r) => {
            if (cancelled) return
            if (!r.ok) {
                setStatus(r.error === "auth" ? "auth" : "error")
                return
            }
            setData(r.data)
            setStatus("ok")
        })
        return () => {
            cancelled = true
        }
    }, [])

    /* 알파네스트 발행 사실 조인 — 종목이 바뀌면 자동 조회(LLM 0 · 비용 0).
       배치 종합 대상이 아닌 종목도 여기서는 항상 사실을 볼 수 있다. */
    useEffect(() => {
        setAsk(null)
        setAskErr("")
        if (!ticker) return
        let cancelled = false
        setFactsLoading(true)
        fetchAsk(ticker).then((r) => {
            if (cancelled) return
            setFactsLoading(false)
            if (r.ok) setAsk(r.data)
            else if (r.error !== "auth") setAskErr("사실 조인 실패")
        })
        return () => {
            cancelled = true
        }
    }, [ticker])

    /* 온디맨드 3종 LLM — 버튼을 눌러야만 호출된다(질문당 과금·일 상한). */
    function runSynthesis() {
        if (!ticker || llmBusy) return
        setLlmBusy(true)
        setAskErr("")
        fetchAsk(ticker, question.trim(), true).then((r) => {
            setLlmBusy(false)
            if (r.ok) setAsk(r.data)
            else setAskErr(r.error === "auth" ? "로그인 필요" : "분석 실패 (시간 초과일 수 있음)")
        })
    }

    const title = (
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
            <div style={{ color: c.ink, fontSize: 15, fontWeight: 800, letterSpacing: "-0.02em" }}>3종 LLM 종합</div>
            <div style={{ color: c.faint, fontSize: 11 }}>Brain=가설 N&lt;252 · LLM 의견=의견</div>
        </div>
    )

    const wrapStyle = { fontFamily: FONT, display: "flex", flexDirection: "column" as const, gap: 12 }

    /* ── 온디맨드 블록 — 배치 대상 여부와 무관하게 항상 노출 ──
       🚨 되돌리지 말 것: 배치(주1회·추천 상위)만으로는 임의 종목을 볼 수 없다(PM 2026-08-03).
       사실 조인은 자동(무료), 3종 LLM 은 버튼(과금·일 상한)으로 분리한다. */
    const closeSec = (ask?.sections || []).find((s) => s.label === "종가")
    const onDemand = !ticker ? null : (
        <div style={{ ...cardStyle(c, "12px 14px"), display: "flex", flexDirection: "column", gap: 9 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <span style={{ fontSize: 11, fontWeight: 800, color: c.vt }}>온디맨드</span>
                <span style={{ fontSize: 10, color: c.faint }}>
                    {factsLoading
                        ? "알파네스트 사실 조인 중…"
                        : ask && ask.sections
                          ? `발행 사실 ${ask.sections.length}섹션${closeSec?.as_of ? ` · 종가 ${closeSec.as_of} 기준` : ""}`
                          : "사실 없음"}
                </span>
                <a
                    href={alphanestStockUrl(ticker)}
                    target="_blank"
                    rel="noreferrer"
                    style={{ marginLeft: "auto", fontSize: 10, color: c.vt, textDecoration: "none", fontWeight: 700 }}
                >
                    알파네스트 리포트 ↗
                </a>
            </div>

            <div style={{ display: "flex", gap: 6 }}>
                <input
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === "Enter") runSynthesis()
                    }}
                    placeholder="질문 (비우면 사실 종합)"
                    style={{
                        flex: 1,
                        minWidth: 0,
                        background: c.hi,
                        color: c.ink,
                        border: "none",
                        borderRadius: 10,
                        padding: "8px 10px",
                        fontSize: 12,
                        fontFamily: FONT,
                        outline: "none",
                    }}
                />
                <button
                    onClick={runSynthesis}
                    disabled={llmBusy}
                    style={{
                        border: "none",
                        borderRadius: 10,
                        padding: "8px 12px",
                        fontSize: 12,
                        fontWeight: 800,
                        fontFamily: FONT,
                        cursor: llmBusy ? "default" : "pointer",
                        background: llmBusy ? c.line : c.vt,
                        color: llmBusy ? c.faint : "#fff",
                        flexShrink: 0,
                    }}
                >
                    {llmBusy ? "분석 중…" : "지금 분석"}
                </button>
            </div>
            {llmBusy ? (
                <div style={{ fontSize: 10, color: c.faint }}>3종 LLM 종합 — 60~120초 걸립니다. 창을 닫지 마세요.</div>
            ) : null}
            {askErr ? <div style={{ fontSize: 11, color: c.down }}>{askErr}</div> : null}

            {ask?.budget_blocked ? (
                <div style={{ fontSize: 11, color: c.down }}>{ask.budget_blocked}</div>
            ) : null}

            {ask?.synthesis?.text ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ fontSize: 11, fontWeight: 800, color: c.vt }}>종합 (온디맨드)</span>
                        <span style={{ fontSize: 10, color: c.faint }}>
                            판단(의견) · Brain=가설 N&lt;252{ask.cached ? " · 캐시" : ""}
                            {ask.budget ? ` · ${ask.budget}` : ""}
                        </span>
                    </div>
                    <div style={{ fontSize: 13, color: c.ink, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>
                        {ask.synthesis.text}
                    </div>
                </div>
            ) : ask?.synthesis?.refused ? (
                <div style={{ fontSize: 12, color: c.down }}>모델이 응답을 거절했습니다 ({ask.synthesis.category || "—"}).</div>
            ) : null}

            {ask?.external?.text ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                    <div style={{ fontSize: 11, fontWeight: 800, color: PPLX }}>
                        신선 사실 <span style={{ color: c.faint, fontWeight: 500 }}>· 외부 사실 (자체 데이터 아님)</span>
                    </div>
                    <div style={{ fontSize: 12, color: c.ink, lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
                        {ask.external.text}
                    </div>
                </div>
            ) : null}

            {ask?.facts_text ? (
                <>
                    <button
                        onClick={() => setOpenFacts((v) => !v)}
                        style={{
                            alignSelf: "flex-start",
                            border: "none",
                            background: "transparent",
                            padding: 0,
                            fontSize: 10,
                            fontWeight: 700,
                            color: c.faint,
                            cursor: "pointer",
                            fontFamily: FONT,
                        }}
                    >
                        {openFacts ? "원본 사실 접기" : `원본 사실 펼치기 (출처·기준일 포함)`}
                    </button>
                    {openFacts ? (
                        <pre
                            style={{
                                margin: 0,
                                maxHeight: 320,
                                overflow: "auto",
                                background: c.hi,
                                borderRadius: 10,
                                padding: "10px 12px",
                                fontSize: 11,
                                lineHeight: 1.5,
                                color: c.sub,
                                whiteSpace: "pre-wrap",
                                fontFamily: FONT,
                            }}
                        >
                            {ask.facts_text}
                        </pre>
                    ) : null}
                    {ask.missing && ask.missing.length ? (
                        <div style={{ fontSize: 10, color: c.faint }}>없는 것 {ask.missing.length}건 — 지어내지 않음</div>
                    ) : null}
                </>
            ) : null}
        </div>
    )

    if (status === "auth" || status === "error") {
        return (
            <div style={wrapStyle}>
                {title}
                <div style={{ color: status === "auth" ? c.sub : c.down, fontSize: 13, lineHeight: 1.5 }}>
                    {status === "auth" ? "오퍼레이터 로그인이 필요합니다 (비공개)." : "데이터를 불러오지 못했습니다."}
                </div>
            </div>
        )
    }

    const syn = data && data.syntheses ? data.syntheses[ticker] : null
    if (!syn) {
        return (
            <div style={wrapStyle}>
                {title}
                <div style={{ color: c.sub, fontSize: 13, lineHeight: 1.55 }}>
                    {ticker ? `${ticker} 는 사전 종합 대상이 아닙니다.` : "종목을 검색해 선택하세요."}
                    <br />
                    사전 종합은 추천 상위 종목만 주 1회입니다 — 아래에서 <b>지금 분석</b>하면 이 종목도 즉시 종합됩니다.
                </div>
                {onDemand}
            </div>
        )
    }

    const s = syn.sources || {}
    const cl = s.claude || {}
    const px = s.perplexity || {}
    const gm = s.gemini || {}

    return (
        <div style={wrapStyle}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                <div style={{ color: c.ink, fontSize: 16, fontWeight: 800, letterSpacing: "-0.02em" }}>
                    {syn.name || ticker} <span style={{ fontSize: 12, color: c.faint, fontWeight: 500 }}>{ticker}</span>
                </div>
                <div style={{ color: c.faint, fontSize: 10 }}>3종 LLM · Brain=가설</div>
            </div>

            {onDemand}

            <Block c={c} tag="종합" tagColor={c.vt} model={cl.model} kind="판단(의견)" text={cl.content} />
            <Block c={c} tag="신선 사실" tagColor={PPLX} model={px.model} kind="외부 사실" text={px.content} citations={px.citations} />
            <Block c={c} tag="구조화" tagColor={GEM} model={gm.model} kind="정리(의견)" text={gm.content} />

            {syn.verity_trail && syn.verity_trail.summary ? (
                <div style={{ background: c.vtS, borderRadius: 14, padding: "11px 13px" }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: c.sub, marginBottom: 5 }}>자체 관점 (가설, 검증 전)</div>
                    <div style={{ fontSize: 12, color: c.ink, lineHeight: 1.5, whiteSpace: "pre-wrap" }}>{syn.verity_trail.summary}</div>
                </div>
            ) : null}

            <div style={{ fontSize: 10, color: c.faint, textAlign: "right" }}>
                생성 {String(syn.generated_at || "").slice(0, 16).replace("T", " ")} · 매수/매도 지시 아님
            </div>
        </div>
    )
}

function Block({ c, tag, tagColor, model, kind, text, citations }: { c: Palette; tag: string; tagColor: string; model?: string; kind: string; text?: string; citations?: string[] }) {
    // 🚨 외곽선 금지 — 좌측 accent 바 제거. 소스 구분은 태그 텍스트 색으로만.
    return (
        <div style={{ ...cardStyle(c, "12px 14px"), display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ fontSize: 11, fontWeight: 800, color: tagColor }}>{tag}</span>
                <span style={{ fontSize: 10, color: c.faint }}>{model || ""}</span>
                <span style={{ fontSize: 10, color: c.faint }}>· {kind}</span>
            </div>
            <div style={{ fontSize: 13, color: c.ink, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{text || "(없음)"}</div>
            {citations && citations.length ? (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 2 }}>
                    {citations.slice(0, 5).map((u, i) => (
                        <a key={i} href={u} target="_blank" rel="noreferrer" style={{ fontSize: 10, color: tagColor, textDecoration: "none" }}>
                            출처 {i + 1} →
                        </a>
                    ))}
                </div>
            ) : null}
        </div>
    )
}
