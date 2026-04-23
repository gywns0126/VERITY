import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useRef, useState, type ReactNode } from "react"

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆ (Neo Dark Terminal — _shared-patterns.ts 마스터)
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    strongBuy: "#22C55E", buy: "#B5FF19", watch: "#FFD600", caution: "#F59E0B", avoid: "#EF4444",
    up: "#F04452", down: "#3182F6",
    info: "#5BA9FF", success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const G = {
    accent: "0 0 8px rgba(181,255,25,0.35)",
    accentSoft: "0 0 4px rgba(181,255,25,0.20)",
    accentStrong: "0 0 12px rgba(181,255,25,0.50)",
    danger: "0 0 6px rgba(239,68,68,0.30)",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_tight: 1.3, lh_normal: 1.5, lh_loose: 1.7,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease", slow: "240ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


interface Props {
    apiUrl: string
    /** 패널 헤더 TG 링크용 (알림 봇) */
    botUsername: string
    dockBottom: number
    dockRight: number
    /** false면 JSON 일괄 응답 (구버전 API 호환) */
    useStream: boolean
}

interface Citation {
    url: string
    title?: string
}
interface Message {
    role: "user" | "assistant"
    text: string
    /** Chat Hybrid 메타데이터 — legacy 경로에서는 undefined */
    sources?: string[]        // ["Brain", "P(4)", "G(2)"]
    citations?: Citation[]    // 외부 출처 링크
    intentType?: string       // portfolio_only / external_only / hybrid / greeting
    totalMs?: number          // e2e 응답시간
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
                    <span style={{ color: C.textSecondary, fontSize: 12, fontWeight: 600, flexShrink: 0 }}>{k}</span>
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

/** Chat Hybrid status 이벤트의 stage 별 한국어 표시. orchestrator 가 방출. */
const HYBRID_STAGE_TEXT: Record<string, string> = {
    intent: "질문 의도 분류 중…",
    brain: "포트폴리오 데이터 조회 중…",
    external: "외부 뉴스·실시간 정보 검색 중…",
    synth: "답변 작성 중…",
    pre_synth: "답변 작성 중…",
}

export default function VerityChat(props: Props) {
    const { apiUrl, botUsername, dockBottom, dockRight, useStream } = props
    const [open, setOpen] = useState(false)
    const [messages, setMessages] = useState<Message[]>([])
    const [input, setInput] = useState("")
    const [loading, setLoading] = useState(false)
    const [streaming, setStreaming] = useState(false)
    const [statusIdx, setStatusIdx] = useState(0)
    const [stageText, setStageText] = useState<string | null>(null)
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
        setStageText(null)  // 새 질문 시작 — 이전 stage 표시 초기화

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
            let hybridSources: string[] | undefined
            let hybridCitations: Citation[] | undefined
            let hybridIntent: string | undefined
            let hybridTotalMs: number | undefined

            const attachHybridMeta = () => {
                if (!hybridSources && !hybridCitations) return
                setMessages((prev) => {
                    const n = [...prev]
                    const last = n[n.length - 1]
                    if (last?.role === "assistant") {
                        n[n.length - 1] = {
                            ...last,
                            sources: hybridSources,
                            citations: hybridCitations,
                            intentType: hybridIntent,
                            totalMs: hybridTotalMs,
                        }
                    }
                    return n
                })
            }

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
                    let ev: any
                    try {
                        ev = JSON.parse(trimmed)
                    } catch {
                        continue
                    }
                    if (ev.type === "delta" && ev.text) {
                        accumulated += ev.text
                        setLoading(false)
                        setStreaming(true)
                        setStageText(null)  // 토큰 도착 — stage 표시 종료
                        pushAssistant(accumulated)
                    } else if (ev.type === "error") {
                        applyError(ev.message || ev.error || "오류가 발생했습니다.")
                        return
                    } else if (ev.type === "end") {
                        if (Array.isArray(ev.sources)) hybridSources = ev.sources
                        if (Array.isArray(ev.citations)) hybridCitations = ev.citations
                        if (typeof ev.intent_type === "string") hybridIntent = ev.intent_type
                        if (typeof ev.total_ms === "number") hybridTotalMs = ev.total_ms
                        attachHybridMeta()
                        setStreaming(false)
                        setLoading(false)
                        setStageText(null)
                    } else if (ev.type === "meta") {
                        if (Array.isArray(ev.sources)) hybridSources = ev.sources
                    } else if (ev.type === "status") {
                        const stage = typeof ev.stage === "string" ? ev.stage : ""
                        const label = HYBRID_STAGE_TEXT[stage]
                        if (label) setStageText(label)
                    }
                }
            }

            if (buf.trim()) {
                try {
                    const ev = JSON.parse(buf.trim()) as any
                    if (ev.type === "delta" && ev.text) {
                        accumulated += ev.text
                        pushAssistant(accumulated)
                    } else if (ev.type === "error") {
                        applyError(ev.message || ev.error || "오류가 발생했습니다.")
                        return
                    } else if (ev.type === "end") {
                        if (Array.isArray(ev.sources)) hybridSources = ev.sources
                        if (Array.isArray(ev.citations)) hybridCitations = ev.citations
                        if (typeof ev.intent_type === "string") hybridIntent = ev.intent_type
                        if (typeof ev.total_ms === "number") hybridTotalMs = ev.total_ms
                        attachHybridMeta()
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
                        <span style={{ color: C.textSecondary, fontSize: 12 }}>무엇이든 물어보세요</span>
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
                {messages.map((m, i) => {
                    const isLastAssistant = i === messages.length - 1 && m.role === "assistant"
                    const showMeta = m.role === "assistant" && (m.sources?.length || m.citations?.length)
                    return (
                        <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: m.role === "user" ? "flex-end" : "flex-start", width: "100%", gap: 4 }}>
                            <div style={{
                                ...msgBubble,
                                background: m.role === "user" ? "#B5FF19" : "#1a1a1a",
                                color: m.role === "user" ? "#000" : "#ccc",
                                borderBottomRightRadius: m.role === "user" ? 4 : 12,
                                borderBottomLeftRadius: m.role === "assistant" ? 4 : 12,
                                maxWidth: m.role === "assistant" ? "92%" : msgBubble.maxWidth,
                            }}>
                                {m.role === "assistant" ? formatAssistantContent(m.text) : m.text}
                                {streaming && isLastAssistant ? (
                                    <span style={{ opacity: blink ? 1 : 0.2, color: "#B5FF19" }}>▌</span>
                                ) : null}
                            </div>
                            {showMeta ? (
                                <div style={metaRow}>
                                    {m.sources?.map((s, si) => (
                                        <span key={si} style={sourceBadge}>{s}</span>
                                    ))}
                                    {typeof m.totalMs === "number" ? (
                                        <span style={{ ...sourceBadge, background: "transparent", borderColor: C.border, color: C.textTertiary, ...MONO }}>
                                            {(m.totalMs / 1000).toFixed(1)}s
                                        </span>
                                    ) : null}
                                </div>
                            ) : null}
                            {m.citations && m.citations.length > 0 ? (
                                <div style={citationList}>
                                    {m.citations.slice(0, 5).map((c, ci) => (
                                        <a
                                            key={ci}
                                            href={c.url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            style={citationLink}
                                            title={c.url}
                                        >
                                            <span style={citationIdx}>[{ci + 1}]</span>
                                            <span style={citationTitle}>
                                                {c.title?.slice(0, 60) || c.url.replace(/^https?:\/\//, "").slice(0, 45)}
                                            </span>
                                        </a>
                                    ))}
                                </div>
                            ) : null}
                        </div>
                    )
                })}
                {loading && (
                    <div style={{ ...msgBubble, alignSelf: "flex-start", background: C.bgElevated, color: "#B5FF19", fontFamily: "ui-monospace, monospace" }}>
                        {stageText || TERMINAL_STATUSES[statusIdx % TERMINAL_STATUSES.length]}
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

const CHAT_API = "https://vercel-api-alpha-umber.vercel.app/api/chat"

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

const font = FONT

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
    background: C.bgElevated,
    border: `1px solid ${C.border}`,
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
    borderBottom: `1px solid ${C.border}`,
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
    color: C.textSecondary,
    fontSize: 12,
    padding: "5px 10px",
    border: `1px solid ${C.border}`,
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

const metaRow: React.CSSProperties = {
    display: "flex",
    flexWrap: "wrap",
    gap: 4,
    marginTop: 2,
    paddingLeft: 4,
    alignItems: "center",
}

const sourceBadge: React.CSSProperties = {
    fontSize: 10,
    fontFamily: FONT_MONO,
    fontWeight: 600,
    color: C.accent,
    background: C.accentSoft,
    border: `1px solid ${C.border}`,
    padding: "1px 6px",
    borderRadius: 4,
    lineHeight: 1.4,
    letterSpacing: 0.2,
}

const citationList: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 2,
    marginTop: 4,
    paddingLeft: 4,
    maxWidth: "92%",
}

const citationLink: React.CSSProperties = {
    display: "flex",
    alignItems: "baseline",
    gap: 6,
    fontSize: 10.5,
    color: C.textSecondary,
    textDecoration: "none",
    padding: "2px 0",
    transition: `color ${X.fast}`,
}

const citationIdx: React.CSSProperties = {
    color: C.textTertiary,
    fontFamily: FONT_MONO,
    flexShrink: 0,
}

const citationTitle: React.CSSProperties = {
    color: C.info,
    borderBottom: `1px dotted ${C.border}`,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    maxWidth: "100%",
}

const inputBar: React.CSSProperties = {
    display: "flex",
    gap: 10,
    padding: "14px 24px 18px",
    borderTop: `1px solid ${C.border}`,
    flexShrink: 0,
    boxSizing: "border-box",
}

const inputField: React.CSSProperties = {
    flex: 1,
    background: C.bgPage,
    border: `1px solid ${C.border}`,
    borderRadius: 8,
    padding: "8px 12px",
    color: C.textPrimary,
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
