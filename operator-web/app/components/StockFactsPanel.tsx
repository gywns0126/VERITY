"use client"
// StockFactsPanel — 종목별 자체 사실·출처·기준일을 보여 주는 오퍼레이터 전용 패널.
// 서버 생성형 종합은 2026-09-05 종료. 최종 해석은 Codex 세션이 같은 사실 번들을 읽고 수행한다.
import { useEffect, useState } from "react"
import { useDark, palette, cardStyle, FONT } from "@/lib/theme"
import { fetchAsk, alphanestStockUrl, type AskResult } from "@/lib/api"

export default function StockFactsPanel({ ticker }: { ticker: string }) {
    const dark = useDark()
    const c = palette(dark)
    const [facts, setFacts] = useState<AskResult | null>(null)
    const [status, setStatus] = useState<"loading" | "ok" | "auth" | "error">("loading")
    const [open, setOpen] = useState(true)

    useEffect(() => {
        setFacts(null)
        setStatus("loading")
        if (!ticker) return
        let cancelled = false
        fetchAsk(ticker).then((r) => {
            if (cancelled) return
            if (r.ok) {
                setFacts(r.data)
                setStatus("ok")
            } else {
                setStatus(r.error === "auth" ? "auth" : "error")
            }
        })
        return () => {
            cancelled = true
        }
    }, [ticker])

    const closeSec = (facts?.sections || []).find((s) => s.label === "종가")
    const n = facts?.sections?.length || 0

    return (
        <div style={{ fontFamily: FONT, display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                <div style={{ color: c.ink, fontSize: 15, fontWeight: 800, letterSpacing: "-0.02em" }}>종목 사실</div>
                <div style={{ color: c.faint, fontSize: 10.5 }}>출처 · 기준일 · 신선도</div>
            </div>

            <div style={{ ...cardStyle(c, "12px 14px"), display: "flex", flexDirection: "column", gap: 9 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 11, fontWeight: 800, color: c.vt }}>{ticker || "종목 미선택"}</span>
                    <span style={{ fontSize: 10, color: c.faint }}>
                        {status === "loading"
                            ? "사실 조인 중…"
                            : status === "auth"
                              ? "오퍼레이터 로그인이 필요합니다."
                              : status === "error"
                                ? "사실 조인 실패"
                                : `${n}개 섹션${closeSec?.as_of ? ` · 종가 ${closeSec.as_of} 기준` : ""} · 서버 LLM 호출 0`}
                    </span>
                    {ticker ? (
                        <a
                            href={alphanestStockUrl(ticker)}
                            target="_blank"
                            rel="noreferrer"
                            style={{ marginLeft: "auto", fontSize: 10, color: c.vt, textDecoration: "none", fontWeight: 700 }}
                        >
                            알파네스트 리포트 ↗
                        </a>
                    ) : null}
                </div>

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
                        {facts.missing?.length ? (
                            <div style={{ fontSize: 10, color: c.faint }}>미조회 {facts.missing.length}건 — 이름과 사유는 원본 사실에 표시</div>
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
