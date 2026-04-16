import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useRef, useState, type ReactNode } from "react"

interface Props {
    apiUrl: string
    /** 패널 헤더 TG 링크용 (알림 봇) */
    botUsername: string
    dockBottom: number
    dockRight: number
    /** false면 JSON 일괄 응답 (구버전 API 호환) */
    useStream: boolean
}

interface Message {
    role: "user" | "assistant"
    text: string
}

const LS_KEY = "verity_chat_history"

/** 어시스턴트 응답이 "라벨: 값" 형태면 한눈에 보이게 줄 단위로 렌더 */
function formatAssistantContent(text: string): ReactNode {
    const raw = text.trim()
    if (!raw) return null
    const lines = raw.split("\n")
    const kv: Array<[string, string]> = []
    const loose: string[] = []
    const lineRe = /^([^:\n]{1,32})[:：]\s*(.+)$/
    for (const line of lines) {
        const t = line.trim()
        if (!t) continue
        const m = t.match(lineRe)
        if (m && !m[1].includes("/")) {
            kv.push([m[1].trim(), m[2].trim()])
            continue
        }
        loose.push(t)
    }
    const structured = kv.length >= 3 || (kv.length >= 2 && loose.length === 0)
    if (!structured) return raw
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {kv.map(([k, v], i) => (
                <div
                    key={i}
                    style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: "4px 8px",
                        alignItems: "baseline",
                    }}
                >
                    <span style={{ color: "#888", fontSize: 11, fontWeight: 600, flexShrink: 0 }}>{k}</span>
                    <span style={{ color: "#e8e8e8", fontSize: 12, wordBreak: "break-word", flex: "1 1 120px", minWidth: 0 }}>
                        {v}
                    </span>
                </div>
            ))}
            {loose.length > 0 ? (
                <div style={{ marginTop: 4, fontSize: 12, color: "#bbb", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                    {loose.join("\n")}
                </div>
            ) : null}
        </div>
    )
}

const TERMINAL_STATUSES = [
    "portfolio.json 대조 중…",
    "시장 무드·자금흐름 스캔 중…",
    "브리핑·추천 데이터 연동 중…",
    "모델 추론 연결 중…",
]

export default function VerityChat(props: Props) {
    const { apiUrl, botUsername, dockBottom, dockRight, useStream } = props
    const [open, setOpen] = useState(false)
    const [messages, setMessages] = useState<Message[]>([])
    const [input, setInput] = useState("")
    const [loading, setLoading] = useState(false)
    const [streaming, setStreaming] = useState(false)
    const [statusIdx, setStatusIdx] = useState(0)
    const [blink, setBlink] = useState(true)
    const bottomRef = useRef<HTMLDivElement>(null)
    const sendAc = useRef<AbortController | null>(null)

    useEffect(() => {
        try {
            const saved = localStorage.getItem(LS_KEY)
            if (saved) setMessages(JSON.parse(saved).slice(-10))
        } catch {}
    }, [])

    useEffect(() => {
        try {
            localStorage.setItem(LS_KEY, JSON.stringify(messages.slice(-10)))
        } catch {}
    }, [messages])

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" })
    }, [messages, open, loading, streaming])

    useEffect(() => {
        if (!loading) return
        setStatusIdx(0)
        const id = window.setInterval(() => {
            setStatusIdx((i) => (i + 1) % TERMINAL_STATUSES.length)
        }, 1600)
        return () => window.clearInterval(id)
    }, [loading])

    useEffect(() => {
        if (!loading && !streaming) return
        const id = window.setInterval(() => setBlink((b) => !b), 420)
        return () => window.clearInterval(id)
    }, [loading, streaming])

    const send = async () => {
        const q = input.trim()
        if (!q || loading || streaming) return
        setInput("")
        const userMsg: Message = { role: "user", text: q }
        setMessages((prev) => [...prev, userMsg])
        setLoading(true)
        setStreaming(false)

        const pushAssistant = (text: string) => {
            setMessages((prev) => {
                const next = [...prev]
                const last = next[next.length - 1]
                if (last?.role === "assistant") {
                    next[next.length - 1] = { role: "assistant", text }
                } else {
                    next.push({ role: "assistant", text })
                }
                return next
            })
        }

        try {
            if (sendAc.current) sendAc.current.abort()
            const ac = new AbortController()
            sendAc.current = ac
            const resp = await fetch(apiUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(useStream ? { question: q, stream: true } : { question: q }),
                signal: ac.signal,
            })

            if (!resp.ok) {
                const errBody = await resp.json().catch(() => ({} as { error?: string }))
                const msg = errBody.error || `요청 실패 (${resp.status})`
                setMessages((prev) => [...prev, { role: "assistant", text: msg }])
                return
            }

            const ct = resp.headers.get("content-type") || ""

            if (!useStream || (!ct.includes("ndjson") && ct.includes("json"))) {
                const data = await resp.json()
                const answer = data.ok ? data.answer : (data.error || "오류가 발생했습니다.")
                setMessages((prev) => [...prev, { role: "assistant", text: answer }])
                return
            }

            const reader = resp.body?.getReader()
            if (!reader) {
                setMessages((prev) => [...prev, { role: "assistant", text: "스트림을 읽을 수 없습니다." }])
                return
            }

            const dec = new TextDecoder()
            let buf = ""
            let accumulated = ""

            const applyError = (msg: string) => {
                setLoading(false)
                setStreaming(false)
                setMessages((prev) => {
                    const n = [...prev]
                    const last = n[n.length - 1]
                    if (last?.role === "assistant" && last.text === "") {
                        n[n.length - 1] = { role: "assistant", text: msg }
                        return n
                    }
                    if (last?.role === "assistant" && accumulated) {
                        n.push({ role: "assistant", text: msg })
                        return n
                    }
                    n.push({ role: "assistant", text: msg })
                    return n
                })
            }

            while (true) {
                const { done, value } = await reader.read()
                if (done) break
                buf += dec.decode(value, { stream: true })
                const lines = buf.split("\n")
                buf = lines.pop() || ""
                for (const line of lines) {
                    const trimmed = line.trim()
                    if (!trimmed) continue
                    let ev: { type?: string; text?: string; message?: string }
                    try {
                        ev = JSON.parse(trimmed)
                    } catch {
                        continue
                    }
                    if (ev.type === "delta" && ev.text) {
                        accumulated += ev.text
                        setLoading(false)
                        setStreaming(true)
                        pushAssistant(accumulated)
                    } else if (ev.type === "error") {
                        applyError(ev.message || "오류가 발생했습니다.")
                        return
                    } else if (ev.type === "end") {
                        setStreaming(false)
                        setLoading(false)
                    }
                }
            }

            if (buf.trim()) {
                try {
                    const ev = JSON.parse(buf.trim()) as { type?: string; text?: string; message?: string }
                    if (ev.type === "delta" && ev.text) {
                        accumulated += ev.text
                        pushAssistant(accumulated)
                    } else if (ev.type === "error") {
                        applyError(ev.message || "오류가 발생했습니다.")
                        return
                    } else if (ev.type === "end") {
                        setStreaming(false)
                    }
                } catch {
                    /* ignore trailing garbage */
                }
            }

            setLoading(false)
            setStreaming(false)
            if (accumulated === "") {
                setMessages((prev) => {
                    if (prev.length && prev[prev.length - 1].role === "assistant" && prev[prev.length - 1].text === "") {
                        const n = [...prev]
                        n[n.length - 1] = { role: "assistant", text: "응답이 비어 있습니다." }
                        return n
                    }
                    return [...prev, { role: "assistant", text: "응답이 비어 있습니다." }]
                })
            }
        } catch (e: any) {
            setMessages((prev) => [...prev, { role: "assistant", text: `연결 오류: ${e.message}` }])
        } finally {
            setLoading(false)
            setStreaming(false)
        }
    }

    const dock: React.CSSProperties = {
        position: "absolute",
        bottom: dockBottom,
        right: dockRight,
        zIndex: 2,
        pointerEvents: "auto",
    }

    if (!open) {
        return (
            <div style={rootWrap}>
                <div style={dock}>
                    <div
                        onClick={() => setOpen(true)}
                        style={fab}
                        onMouseEnter={(e) => (e.currentTarget.style.transform = "scale(1.1)")}
                        onMouseLeave={(e) => (e.currentTarget.style.transform = "scale(1)")}
                    >
                        <span style={{ fontSize: 22 }}>V</span>
                    </div>
                </div>
            </div>
        )
    }

    return (
        <div style={rootWrap}>
        <div style={{ ...panelWrap, bottom: dockBottom, right: dockRight }}>
            <div style={panelHeader}>
                <div style={panelHeaderTitleCol}>
                    <span style={panelTitle}>VERITY</span>
                </div>
                <div style={panelHeaderActions}>
                    <a
                        href={`https://t.me/${botUsername}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={tgLink}
                        aria-label="Telegram에서 열기"
                    >
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
                            <path
                                d="M20.665 3.717l-17.73 6.837c-1.21.486-1.203 1.161-.222 1.462l4.552 1.42 10.532-6.645c.498-.303.953-.14.579.192l-8.533 7.701h-.002l.002.001-.314 4.692c.46 0 .663-.211.921-.46l2.211-2.15 4.599 3.397c.848.467 1.457.227 1.668-.785l3.019-14.228c.309-1.239-.473-1.8-1.282-1.434z"
                                fill="#B5FF19"
                            />
                        </svg>
                    </a>
                    <span
                        onClick={() => setOpen(false)}
                        style={closeBtn}
                        role="button"
                        aria-label="닫기"
                    >
                        ×
                    </span>
                </div>
            </div>

            <div style={msgArea}>
                {messages.length === 0 && (
                    <div style={emptyState}>
                        <span style={{ fontSize: 24 }}>V</span>
                        <span style={{ color: "#888", fontSize: 11 }}>무엇이든 물어보세요</span>
                        <div style={suggestWrap}>
                            {["지금 시장 어때?", "삼성전자 어때?", "포트폴리오 현황"].map((s) => (
                                <span
                                    key={s}
                                    style={suggestChip}
                                    onClick={() => { setInput(s); }}
                                >
                                    {s}
                                </span>
                            ))}
                        </div>
                    </div>
                )}
                {messages.map((m, i) => (
                    <div key={i} style={{
                        ...msgBubble,
                        alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                        background: m.role === "user" ? "#B5FF19" : "#1a1a1a",
                        color: m.role === "user" ? "#000" : "#ccc",
                        borderBottomRightRadius: m.role === "user" ? 4 : 12,
                        borderBottomLeftRadius: m.role === "assistant" ? 4 : 12,
                        maxWidth: m.role === "assistant" ? "92%" : msgBubble.maxWidth,
                    }}>
                        {m.role === "assistant" ? formatAssistantContent(m.text) : m.text}
                        {streaming && i === messages.length - 1 && m.role === "assistant" ? (
                            <span style={{ opacity: blink ? 1 : 0.2, color: "#B5FF19" }}>▌</span>
                        ) : null}
                    </div>
                ))}
                {loading && (
                    <div style={{ ...msgBubble, alignSelf: "flex-start", background: "#1a1a1a", color: "#B5FF19", fontFamily: "ui-monospace, monospace" }}>
                        {TERMINAL_STATUSES[statusIdx % TERMINAL_STATUSES.length]}
                        <span style={{ opacity: blink ? 1 : 0.15, marginLeft: 2 }}>▌</span>
                    </div>
                )}
                <div ref={bottomRef} />
            </div>

            <div style={inputBar}>
                <input
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && send()}
                    placeholder="질문을 입력하세요…"
                    style={inputField}
                    disabled={loading || streaming}
                />
                <div onClick={send} style={{ ...sendBtn, opacity: loading || streaming || !input.trim() ? 0.4 : 1 }}>
                    →
                </div>
            </div>
        </div>
        </div>
    )
}

const CHAT_API = "https://project-yw131.vercel.app/api/chat"

VerityChat.defaultProps = {
    apiUrl: CHAT_API,
    botUsername: "verity_stock_bot",
    dockBottom: 0,
    dockRight: 0,
    useStream: true,
}

addPropertyControls(VerityChat, {
    apiUrl: {
        type: ControlType.String,
        title: "Chat API URL",
        defaultValue: CHAT_API,
    },
    botUsername: {
        type: ControlType.String,
        title: "TG 봇 (헤더 링크)",
        defaultValue: "verity_stock_bot",
    },
    dockBottom: {
        type: ControlType.Number,
        title: "하단 여백",
        defaultValue: 0,
        min: 0,
        max: 120,
        step: 4,
        displayStepper: true,
    },
    dockRight: {
        type: ControlType.Number,
        title: "우측 여백",
        defaultValue: 0,
        min: 0,
        max: 120,
        step: 4,
        displayStepper: true,
    },
    useStream: {
        type: ControlType.Boolean,
        title: "스트리밍 응답",
        defaultValue: true,
        enabledTitle: "켜기",
        disabledTitle: "끄기",
    },
})

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"

const rootWrap: React.CSSProperties = {
    position: "relative",
    width: "100%",
    height: "100%",
    minWidth: 56,
    minHeight: 56,
    overflow: "visible",
    pointerEvents: "none",
    fontFamily: font,
}

const fab: React.CSSProperties = {
    width: 52,
    height: 52,
    borderRadius: "50%",
    background: "#B5FF19",
    color: "#000",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontWeight: 900,
    fontFamily: font,
    cursor: "pointer",
    boxShadow: "0 4px 20px rgba(181,255,25,0.3)",
    transition: "transform 0.2s",
}

const panelWrap: React.CSSProperties = {
    position: "absolute",
    width: 360,
    maxWidth: "calc(100vw - 48px)",
    height: 520,
    maxHeight: "min(520px, 100vh - 48px)",
    minHeight: 0,
    background: "#111",
    border: "1px solid #222",
    borderRadius: 16,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    fontFamily: font,
    zIndex: 3,
    boxShadow: "0 8px 40px rgba(0,0,0,0.6)",
    pointerEvents: "auto",
}

const panelHeader: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 16,
    padding: "16px 24px",
    borderBottom: "1px solid #222",
    flexShrink: 0,
    minHeight: 56,
    boxSizing: "border-box",
}

const panelHeaderTitleCol: React.CSSProperties = {
    flex: 1,
    minWidth: 0,
    paddingRight: 4,
}

const panelHeaderActions: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 4,
    flexShrink: 0,
}

const panelTitle: React.CSSProperties = {
    color: "#B5FF19",
    fontSize: 15,
    fontWeight: 800,
    fontFamily: font,
    letterSpacing: "-0.02em",
    lineHeight: 1.3,
    display: "block",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
}

const tgLink: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    textDecoration: "none",
    padding: "6px",
    borderRadius: "50%",
    flexShrink: 0,
    lineHeight: 0,
    boxSizing: "border-box",
    background: "transparent",
    border: "none",
}

const closeBtn: React.CSSProperties = {
    color: "#777",
    fontSize: 26,
    fontWeight: 200,
    cursor: "pointer",
    lineHeight: 1,
    margin: 0,
    padding: "6px 10px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    boxSizing: "border-box",
    border: "none",
    background: "transparent",
    userSelect: "none",
}

const msgArea: React.CSSProperties = {
    flex: 1,
    minHeight: 0,
    overflowY: "auto",
    overflowX: "hidden",
    WebkitOverflowScrolling: "touch",
    padding: "14px 24px 18px",
    display: "flex",
    flexDirection: "column",
    gap: 8,
}

const emptyState: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    height: "100%",
    color: "#B5FF19",
    fontWeight: 900,
    fontFamily: font,
}

const suggestWrap: React.CSSProperties = {
    display: "flex",
    flexWrap: "wrap",
    gap: 6,
    justifyContent: "center",
    marginTop: 8,
}

const suggestChip: React.CSSProperties = {
    color: "#aaa",
    fontSize: 11,
    padding: "5px 10px",
    border: "1px solid #333",
    borderRadius: 20,
    cursor: "pointer",
    fontFamily: font,
}

const msgBubble: React.CSSProperties = {
    maxWidth: "80%",
    padding: "8px 12px",
    borderRadius: 12,
    fontSize: 12,
    lineHeight: 1.6,
    fontFamily: font,
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
}

const inputBar: React.CSSProperties = {
    display: "flex",
    gap: 10,
    padding: "14px 24px 18px",
    borderTop: "1px solid #222",
    flexShrink: 0,
    boxSizing: "border-box",
}

const inputField: React.CSSProperties = {
    flex: 1,
    background: "#0a0a0a",
    border: "1px solid #333",
    borderRadius: 8,
    padding: "8px 12px",
    color: "#fff",
    fontSize: 12,
    fontFamily: font,
    outline: "none",
}

const sendBtn: React.CSSProperties = {
    width: 36,
    height: 36,
    borderRadius: 8,
    background: "#B5FF19",
    color: "#000",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 16,
    fontWeight: 700,
    cursor: "pointer",
    flexShrink: 0,
}
