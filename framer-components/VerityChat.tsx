import { addPropertyControls, ControlType } from "framer"
import { useEffect, useRef, useState } from "react"

interface Props {
    apiUrl: string
    botUsername: string
}

interface Message {
    role: "user" | "assistant"
    text: string
}

const LS_KEY = "verity_chat_history"

export default function VerityChat(props: Props) {
    const { apiUrl, botUsername } = props
    const [open, setOpen] = useState(false)
    const [messages, setMessages] = useState<Message[]>([])
    const [input, setInput] = useState("")
    const [loading, setLoading] = useState(false)
    const bottomRef = useRef<HTMLDivElement>(null)

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
    }, [messages, open])

    const send = async () => {
        const q = input.trim()
        if (!q || loading) return
        setInput("")
        const userMsg: Message = { role: "user", text: q }
        setMessages((prev) => [...prev, userMsg])
        setLoading(true)

        try {
            const resp = await fetch(apiUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ question: q }),
            })
            const data = await resp.json()
            const answer = data.ok ? data.answer : (data.error || "오류가 발생했습니다.")
            setMessages((prev) => [...prev, { role: "assistant", text: answer }])
        } catch (e: any) {
            setMessages((prev) => [...prev, { role: "assistant", text: `연결 오류: ${e.message}` }])
        } finally {
            setLoading(false)
        }
    }

    if (!open) {
        return (
            <div style={fabWrap}>
                <div
                    onClick={() => setOpen(true)}
                    style={fab}
                    onMouseEnter={(e) => (e.currentTarget.style.transform = "scale(1.1)")}
                    onMouseLeave={(e) => (e.currentTarget.style.transform = "scale(1)")}
                >
                    <span style={{ fontSize: 22 }}>V</span>
                </div>
                <div style={fabLabel}>비서에게 물어보기</div>
            </div>
        )
    }

    return (
        <div style={panelWrap}>
            <div style={panelHeader}>
                <span style={panelTitle}>VERITY 비서</span>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <a
                        href={`https://t.me/${botUsername}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={tgLink}
                    >
                        TG
                    </a>
                    <span onClick={() => setOpen(false)} style={closeBtn}>×</span>
                </div>
            </div>

            <div style={msgArea}>
                {messages.length === 0 && (
                    <div style={emptyState}>
                        <span style={{ fontSize: 24 }}>V</span>
                        <span style={{ color: "#888", fontSize: 11 }}>무엇이든 물어보세요</span>
                        <div style={suggestWrap}>
                            {["지금 시장 어때?", "추천 종목 알려줘", "포트폴리오 현황"].map((s) => (
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
                    }}>
                        {m.text}
                    </div>
                ))}
                {loading && (
                    <div style={{ ...msgBubble, alignSelf: "flex-start", background: "#1a1a1a", color: "#B5FF19" }}>
                        분석 중…
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
                    disabled={loading}
                />
                <div onClick={send} style={{ ...sendBtn, opacity: loading || !input.trim() ? 0.4 : 1 }}>
                    →
                </div>
            </div>
        </div>
    )
}

const CHAT_API = "https://verity-vercel-api.vercel.app/api/chat"

VerityChat.defaultProps = {
    apiUrl: CHAT_API,
    botUsername: "verity_stock_bot",
}

addPropertyControls(VerityChat, {
    apiUrl: {
        type: ControlType.String,
        title: "Chat API URL",
        defaultValue: CHAT_API,
    },
    botUsername: {
        type: ControlType.String,
        title: "Telegram Bot",
        defaultValue: "verity_stock_bot",
    },
})

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"

const fabWrap: React.CSSProperties = {
    position: "fixed",
    bottom: 24,
    right: 24,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 6,
    zIndex: 9999,
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

const fabLabel: React.CSSProperties = {
    color: "#888",
    fontSize: 10,
    fontFamily: font,
    whiteSpace: "nowrap",
}

const panelWrap: React.CSSProperties = {
    position: "fixed",
    bottom: 24,
    right: 24,
    width: 360,
    height: 520,
    background: "#111",
    border: "1px solid #222",
    borderRadius: 16,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    fontFamily: font,
    zIndex: 9999,
    boxShadow: "0 8px 40px rgba(0,0,0,0.6)",
}

const panelHeader: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "12px 16px",
    borderBottom: "1px solid #222",
    flexShrink: 0,
}

const panelTitle: React.CSSProperties = {
    color: "#B5FF19",
    fontSize: 14,
    fontWeight: 800,
    fontFamily: font,
}

const tgLink: React.CSSProperties = {
    color: "#555",
    fontSize: 10,
    textDecoration: "none",
    border: "1px solid #333",
    padding: "2px 6px",
    borderRadius: 4,
}

const closeBtn: React.CSSProperties = {
    color: "#666",
    fontSize: 20,
    cursor: "pointer",
    lineHeight: 1,
}

const msgArea: React.CSSProperties = {
    flex: 1,
    overflowY: "auto",
    padding: "12px 14px",
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
    gap: 8,
    padding: "10px 12px",
    borderTop: "1px solid #222",
    flexShrink: 0,
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
