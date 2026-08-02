"use client"
// ChatConsult — 상담·추천 채팅 (오퍼레이터). 공개 알파네스트 디자인.
// 🚨 RULE 6: 기존 grounded 백엔드(/api/chat, Brain 컨텍스트+watchlist 그라운딩) 재사용 — 신규 LLM
//   narrative 컴포넌트 신설 아님. 자기 trail(Brain) 정합. 저가 모델(gemini flash-lite)+rate-limit+cache=비용 통제.
//   🚨 RULE 7: 답변=가설·매수/매도 지시 아님(백엔드 프롬프트+프론트 푸터 병기).
//   🚨 외곽선 금지 — 말풍선=채움색만.
import { useEffect, useRef, useState } from "react"
import { useDark, palette, FONT } from "@/lib/theme"
import { API_BASE } from "@/lib/api"

type Turn = { role: "user" | "assistant"; text: string }

function loadWatchlist(): unknown[] | null {
    try {
        const raw = localStorage.getItem("verity_watchlist")
        const arr = raw ? JSON.parse(raw) : null
        return Array.isArray(arr) ? arr : null
    } catch {
        return null
    }
}

export default function ChatConsult() {
    const dark = useDark()
    const c = palette(dark)
    const [turns, setTurns] = useState<Turn[]>([])
    const [input, setInput] = useState("")
    const [busy, setBusy] = useState(false)
    const scrollRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }, [turns, busy])

    function setLastAssistant(text: string) {
        setTurns((prev) => {
            const next = prev.slice()
            for (let i = next.length - 1; i >= 0; i--) {
                if (next[i].role === "assistant") {
                    next[i] = { ...next[i], text }
                    break
                }
            }
            return next
        })
    }

    async function send() {
        const q = input.trim()
        if (!q || busy) return
        setInput("")
        const history = turns.slice(-6).map((t) => ({ role: t.role, content: t.text }))
        setTurns((prev) => [...prev, { role: "user", text: q }, { role: "assistant", text: "" }])
        setBusy(true)
        try {
            const r = await fetch(`${API_BASE}/api/chat`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                // 🚨 RULE 6: stream=true → hybrid(Brain+Perplexity 통합) 그라운딩 경로. 미가용 시 백엔드가 legacy NDJSON 폴백.
                body: JSON.stringify({ question: q, stream: true, recent_turns: history, watchlist: loadWatchlist() }),
            })
            if (!r.ok || !r.body) throw new Error("http")
            const reader = r.body.getReader()
            const dec = new TextDecoder()
            let buf = "", acc = ""
            for (;;) {
                const { done, value } = await reader.read()
                if (done) break
                buf += dec.decode(value, { stream: true })
                const lines = buf.split("\n")
                buf = lines.pop() || ""
                for (const line of lines) {
                    const s = line.trim()
                    if (!s) continue
                    let ev: { type?: string; text?: string; message?: string }
                    try {
                        ev = JSON.parse(s)
                    } catch {
                        continue
                    }
                    if (ev.type === "delta" && ev.text) {
                        acc += ev.text
                        setLastAssistant(acc)
                    } else if (ev.type === "error") {
                        acc = String(ev.message || "오류가 발생했습니다.")
                        setLastAssistant(acc)
                    }
                }
            }
            if (!acc) setLastAssistant("답변을 받지 못했습니다.")
        } catch {
            setLastAssistant("상담 서버에 연결하지 못했습니다.")
        } finally {
            setBusy(false)
        }
    }

    return (
        <div style={{ fontFamily: FONT, display: "flex", flexDirection: "column", gap: 10 }}>
            <div
                ref={scrollRef}
                style={{ background: c.card, borderRadius: 16, boxShadow: "0 1px 3px rgba(0,0,0,0.05)", padding: 14, display: "flex", flexDirection: "column", gap: 10, maxHeight: 420, overflowY: "auto" }}
            >
                {turns.length === 0 ? (
                    <div style={{ fontSize: 13, color: c.sub, lineHeight: 1.6, padding: "8px 4px" }}>
                        종목·전략·시장에 대해 물어보세요. Brain 컨텍스트와 관심종목을 반영해 답합니다.
                        <div style={{ fontSize: 11.5, color: c.faint, marginTop: 8 }}>
                            예: “지금 반도체 비중 늘려도 될까?” · “NAVER 관망 이유는?” · “중용 관점에서 내 관심종목 균형은?”
                        </div>
                    </div>
                ) : (
                    turns.map((t, i) => {
                        const mine = t.role === "user"
                        const empty = !t.text
                        return (
                            <div key={i} style={{ display: "flex", justifyContent: mine ? "flex-end" : "flex-start" }}>
                                <div
                                    style={{
                                        maxWidth: "84%",
                                        background: mine ? c.vtS : c.hi,
                                        color: empty ? c.faint : c.ink,
                                        borderRadius: 14,
                                        padding: "10px 13px",
                                        fontSize: 13.5,
                                        lineHeight: 1.55,
                                        whiteSpace: "pre-wrap",
                                    }}
                                >
                                    {t.text || (t.role === "assistant" ? "답변 작성 중…" : "")}
                                </div>
                            </div>
                        )
                    })
                )}
            </div>

            <div style={{ display: "flex", gap: 8 }}>
                <input
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") send() }}
                    placeholder="상담 질문 (500자 이내)"
                    maxLength={500}
                    style={{ flex: 1, background: dark ? c.bg : c.track, color: c.ink, border: "none", borderRadius: 12, padding: "13px 15px", fontSize: 14, fontFamily: FONT, outline: "none" }}
                />
                <button
                    onClick={send}
                    disabled={busy || !input.trim()}
                    style={{ border: "none", borderRadius: 12, padding: "0 18px", fontSize: 14, fontWeight: 700, fontFamily: FONT, cursor: busy || !input.trim() ? "default" : "pointer", background: busy || !input.trim() ? c.hi : c.vt, color: busy || !input.trim() ? c.faint : "#fff" }}
                >
                    전송
                </button>
            </div>
            <div style={{ fontSize: 10.5, color: c.faint, lineHeight: 1.5 }}>
                Brain 컨텍스트·관심종목 그라운딩(가설) · 저가 모델+캐시로 비용 통제 · 정보 제공이며 매수/매도 지시 아님
            </div>
        </div>
    )
}
