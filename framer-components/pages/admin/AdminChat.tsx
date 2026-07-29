import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * AdminChat — 관리자 전용 챗 (AlphaNest 스타일).
 *
 * 🚨 왜 /admin 안에만 두나 (PM 2026-07-30 "나 혼자 볼거고 배포 안할거니까"):
 *   이 챗은 미발행 자산(추천 원본·VAMS 실적·컨센서스 목표가·팩터 IC)을 컨텍스트로 쓴다.
 *   공개 화면에 두면 그 순간 재배포가 된다. 서버가 JWT + profiles.is_admin 을 검증하는
 *   /api/chat_admin 만 호출하며, 공개 /api/chat 은 이 컴포넌트와 무관하다.
 *
 * 소스 = POST /api/chat_admin → NDJSON 스트림
 *   {"type":"status","stage":"brain|internal|..."} · {"type":"meta"} ·
 *   {"type":"delta","text"} · {"type":"end","text","sources"} · {"type":"error"}
 *
 * 🚨 RULE 7 — 자기 산식(등급·IC·시뮬 통계)은 가설이다. 서버가 컨텍스트에 그 표기를 실어 보내며,
 *   화면 하단에도 상시 고지를 둔다. 지우지 말 것.
 * 🚨 fast-moving 수치(현재가·환율·지수)는 답변 prose 에 박제되면 stale 이 된다 —
 *   서버 프롬프트 가드가 1차, 여기서는 답변 시각을 함께 표시해 언제 기준인지 남긴다.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", grid: "#eef1f4", vt: "#6c5ce7", vtS: "#f0edff", up: "#f04452",
    mine: "#6c5ce7", mineInk: "#ffffff",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", grid: "#1e242c", vt: "#a99bff", vtS: "#241f3a", up: "#f04452",
    mine: "#6c5ce7", mineInk: "#ffffff",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const DEFAULT_API = "https://project-yw131.vercel.app"
const SESSION_KEY = "verity_supabase_session"

const STAGE_LABEL: Record<string, string> = {
    classify: "질문 분류",
    brain: "내부 종목 데이터",
    internal: "미발행 자산 결합",
    perplexity: "웹 검색",
    grounding: "실시간 확인",
    synthesize: "답변 작성",
}

function readBodyDark(): boolean {
    try {
        if (typeof document !== "undefined" && document.body) {
            const a = document.body.dataset.framerTheme
            if (a === "dark") return true
            if (a === "light") return false
        }
        if (typeof window !== "undefined" && window.matchMedia)
            return window.matchMedia("(prefers-color-scheme: dark)").matches
    } catch (e) {}
    return false
}
function loadToken(): string {
    if (typeof window === "undefined") return ""
    try {
        const raw = localStorage.getItem(SESSION_KEY)
        if (!raw) return ""
        const s = JSON.parse(raw)
        if (s.expires_at && Date.now() / 1000 > s.expires_at) return ""
        return typeof s.access_token === "string" ? s.access_token : ""
    } catch (e) {
        return ""
    }
}
function hhmm(): string {
    const d = new Date()
    return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
}

interface Msg {
    role: "me" | "bot"
    text: string
    at: string
    stages?: string[]
    err?: boolean
}

const SAMPLE: Msg[] = [
    { role: "me", text: "지금 보유 종목 중 가장 약한 고리는?", at: "09:14" },
    {
        role: "bot",
        at: "09:14",
        stages: ["내부 종목 데이터", "미발행 자산 결합", "답변 작성"],
        text: "보유 6종 가운데 실현손익 기여가 가장 나쁜 쪽은 …\n(미리보기 — 실제 답변은 내부 자산을 읽어 작성됩니다)",
    },
]

const PROMPTS = [
    "지금 보유 종목 중 가장 약한 고리는?",
    "이번 주 실적 발표 예정 중 내 유니버스와 겹치는 건?",
    "VAMS 검증이 FAIL 인 이유를 데이터로 짚어줘",
    "외인·기관이 동시에 사들인 종목과 내 보유의 교집합",
]

interface Props {
    apiBase: string
    dark: boolean
    height: number
}

export default function AdminChat(props: Props) {
    const apiBase = (props.apiBase || DEFAULT_API).replace(/\/+$/, "")
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(() =>
        onCanvas ? !!props.dark : readBodyDark()
    )
    const C = (onCanvas ? !!props.dark : themeDark) ? DARK : LIGHT

    const [msgs, setMsgs] = useState<Msg[]>(onCanvas ? SAMPLE : [])
    const [q, setQ] = useState("")
    const [busy, setBusy] = useState(false)
    const [stage, setStage] = useState("")
    const [gate, setGate] = useState<"?" | "ok" | "no">("?")
    const scrollRef = useRef<HTMLDivElement>(null)
    const abortRef = useRef<any>(null)

    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || !document.body) return
        const o = new MutationObserver(read)
        o.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => o.disconnect()
    }, [onCanvas])

    // 게이트 상태 — 서버가 관리자 인증을 인정하는지 먼저 확인(질문 전에 알려준다)
    useEffect(() => {
        if (onCanvas) return
        const token = loadToken()
        if (!token) {
            setGate("no")
            return
        }
        fetch(`${apiBase}/api/chat_admin`, {
            headers: { Authorization: "Bearer " + token },
            cache: "no-store",
        })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => setGate(d && d.authorized ? "ok" : "no"))
            .catch(() => setGate("no"))
    }, [apiBase, onCanvas])

    useEffect(() => {
        const el = scrollRef.current
        if (el) el.scrollTop = el.scrollHeight
    }, [msgs, stage])

    const send = useCallback(
        (text: string) => {
            const question = (text || "").trim()
            if (!question || busy || onCanvas) return
            const token = loadToken()
            if (!token) {
                setGate("no")
                return
            }
            setQ("")
            setBusy(true)
            setStage("")
            const stages: string[] = []
            setMsgs((m) => [...m, { role: "me", text: question, at: hhmm() }])

            const recent = msgs.slice(-6).map((m) => ({
                role: m.role === "me" ? "user" : "assistant",
                content: m.text,
            }))

            const ctrl = typeof AbortController !== "undefined" ? new AbortController() : null
            abortRef.current = ctrl

            fetch(`${apiBase}/api/chat_admin`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Authorization: "Bearer " + token,
                },
                body: JSON.stringify({ question, session_id: "admin", recent_turns: recent }),
                signal: ctrl ? ctrl.signal : undefined,
            })
                .then(async (r) => {
                    if (!r.ok || !r.body) {
                        const t = await r.text().catch(() => "")
                        throw new Error(
                            r.status === 403
                                ? "관리자 인증이 필요합니다"
                                : `HTTP ${r.status}${t ? " · " + t.slice(0, 120) : ""}`
                        )
                    }
                    const reader = r.body.getReader()
                    const dec = new TextDecoder()
                    let buf = ""
                    let acc = ""
                    let started = false

                    // NDJSON — 줄 단위로 끊어 처리. 마지막 조각은 버퍼에 남긴다.
                    for (;;) {
                        const { done, value } = await reader.read()
                        if (done) break
                        buf += dec.decode(value, { stream: true })
                        const lines = buf.split("\n")
                        buf = lines.pop() || ""
                        for (const ln of lines) {
                            const s = ln.trim()
                            if (!s) continue
                            let ev: any
                            try {
                                ev = JSON.parse(s)
                            } catch (e) {
                                continue
                            }
                            if (ev.type === "status") {
                                const lb = STAGE_LABEL[ev.stage] || ev.stage
                                if (lb && stages.indexOf(lb) < 0) stages.push(lb)
                                setStage(lb || "")
                            } else if (ev.type === "delta") {
                                acc += ev.text || ""
                                if (!started) {
                                    started = true
                                    setMsgs((m) => [
                                        ...m,
                                        { role: "bot", text: acc, at: hhmm(), stages: [...stages] },
                                    ])
                                } else {
                                    setMsgs((m) => {
                                        const c = m.slice()
                                        c[c.length - 1] = {
                                            ...c[c.length - 1],
                                            text: acc,
                                            stages: [...stages],
                                        }
                                        return c
                                    })
                                }
                            } else if (ev.type === "end") {
                                const full = ev.text || acc
                                setMsgs((m) => {
                                    const c = m.slice()
                                    if (started) {
                                        c[c.length - 1] = {
                                            ...c[c.length - 1],
                                            text: full,
                                            stages: [...stages],
                                        }
                                    } else {
                                        c.push({
                                            role: "bot",
                                            text: full,
                                            at: hhmm(),
                                            stages: [...stages],
                                        })
                                    }
                                    return c
                                })
                            } else if (ev.type === "error") {
                                throw new Error(ev.message || ev.error || "오류")
                            }
                        }
                    }
                })
                .catch((e) => {
                    if (e && e.name === "AbortError") return
                    setMsgs((m) => [
                        ...m,
                        {
                            role: "bot",
                            text: "답변에 실패했어요 — " + (e && e.message ? e.message : String(e)),
                            at: hhmm(),
                            err: true,
                        },
                    ])
                })
                .finally(() => {
                    setBusy(false)
                    setStage("")
                    abortRef.current = null
                })
        },
        [apiBase, busy, msgs, onCanvas]
    )

    const H = props.height || 620
    const wrap: CSSProperties = {
        width: "100%",
        height: "100%",
        minHeight: H,
        boxSizing: "border-box",
        background: C.bg,
        fontFamily: FONT,
        color: C.ink,
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 12,
    }
    const card: CSSProperties = {
        background: C.card,
        borderRadius: 16,
        padding: "15px 17px",
        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
    }

    const bubble = (m: Msg, i: number) => {
        const mine = m.role === "me"
        return (
            <div
                key={i}
                style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: mine ? "flex-end" : "flex-start",
                    gap: 4,
                }}
            >
                {!mine && m.stages && m.stages.length > 0 && (
                    <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                        {m.stages.map((s) => (
                            <span
                                key={s}
                                style={{
                                    fontSize: 10.5,
                                    fontWeight: 700,
                                    color: C.vt,
                                    background: C.vtS,
                                    borderRadius: 6,
                                    padding: "2px 7px",
                                }}
                            >
                                {s}
                            </span>
                        ))}
                    </div>
                )}
                <div
                    style={{
                        maxWidth: "86%",
                        background: mine ? C.mine : C.card,
                        color: mine ? C.mineInk : m.err ? C.up : C.ink,
                        borderRadius: 14,
                        padding: "10px 13px",
                        fontSize: 13.5,
                        fontWeight: mine ? 700 : 500,
                        lineHeight: 1.65,
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                        boxShadow: mine ? "none" : "0 1px 3px rgba(0,0,0,0.04)",
                    }}
                >
                    {m.text}
                </div>
                <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 600 }}>{m.at}</span>
            </div>
        )
    }

    return (
        <div style={wrap}>
            <style>{`@keyframes acDot{0%,80%,100%{opacity:.25}40%{opacity:1}}`}</style>

            <div style={{ ...card, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <span style={{ fontSize: 17, fontWeight: 800, letterSpacing: "-0.4px" }}>
                    배리티 챗
                </span>
                <span
                    style={{
                        fontSize: 10.5,
                        fontWeight: 800,
                        color: C.vt,
                        background: C.vtS,
                        borderRadius: 6,
                        padding: "3px 8px",
                    }}
                >
                    관리자 전용 · 미발행 자산 결합
                </span>
                <span
                    style={{
                        marginLeft: "auto",
                        fontSize: 11,
                        fontWeight: 700,
                        color: gate === "ok" ? C.vt : gate === "no" ? C.up : C.faint,
                    }}
                >
                    {gate === "ok" ? "인증됨" : gate === "no" ? "관리자 로그인 필요" : "확인 중…"}
                </span>
            </div>

            <div
                ref={scrollRef}
                style={{
                    flex: 1,
                    minHeight: 0,
                    overflowY: "auto",
                    display: "flex",
                    flexDirection: "column",
                    gap: 12,
                    padding: "2px 2px 6px",
                }}
            >
                {msgs.length === 0 && (
                    <div style={{ ...card }}>
                        <div style={{ fontSize: 13.5, fontWeight: 800, marginBottom: 8 }}>
                            무엇이든 물어보세요
                        </div>
                        <div
                            style={{
                                fontSize: 12.5,
                                color: C.sub,
                                fontWeight: 600,
                                lineHeight: 1.6,
                                marginBottom: 12,
                            }}
                        >
                            공개 화면에 싣지 못하는 데이터까지 읽고 답합니다 — 추천 유니버스 원본,
                            VAMS 운용 실적, 미장 컨센서스, 팩터 IC.
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                            {PROMPTS.map((p) => (
                                <div
                                    key={p}
                                    onClick={() => send(p)}
                                    style={{
                                        cursor: "pointer",
                                        fontSize: 12.5,
                                        fontWeight: 700,
                                        color: C.vt,
                                        background: C.vtS,
                                        borderRadius: 10,
                                        padding: "9px 12px",
                                    }}
                                >
                                    {p}
                                </div>
                            ))}
                        </div>
                    </div>
                )}
                {msgs.map(bubble)}
                {busy && (
                    <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                        {[0, 1, 2].map((i) => (
                            <span
                                key={i}
                                style={{
                                    width: 6,
                                    height: 6,
                                    borderRadius: "50%",
                                    background: C.vt,
                                    animation: `acDot 1.2s ${i * 0.16}s infinite`,
                                }}
                            />
                        ))}
                        <span style={{ fontSize: 11.5, color: C.faint, fontWeight: 700 }}>
                            {stage || "생각 중…"}
                        </span>
                    </div>
                )}
            </div>

            <div style={{ ...card, display: "flex", gap: 8, alignItems: "flex-end", padding: "10px 12px" }}>
                <textarea
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault()
                            send(q)
                        }
                    }}
                    placeholder={gate === "no" ? "관리자 로그인이 필요해요" : "질문을 적어주세요 (Enter 전송 · Shift+Enter 줄바꿈)"}
                    rows={1}
                    disabled={gate === "no"}
                    style={{
                        flex: 1,
                        minHeight: 22,
                        maxHeight: 120,
                        resize: "none",
                        border: "none",
                        outline: "none",
                        background: "transparent",
                        color: C.ink,
                        fontFamily: FONT,
                        fontSize: 13.5,
                        fontWeight: 500,
                        lineHeight: 1.6,
                        padding: "6px 2px",
                    }}
                />
                <div
                    onClick={() => send(q)}
                    style={{
                        flexShrink: 0,
                        cursor: busy || !q.trim() ? "default" : "pointer",
                        opacity: busy || !q.trim() ? 0.4 : 1,
                        fontSize: 12.5,
                        fontWeight: 800,
                        color: "#ffffff",
                        background: C.vt,
                        borderRadius: 10,
                        padding: "8px 14px",
                    }}
                >
                    보내기
                </div>
            </div>

            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, lineHeight: 1.55, textAlign: "center" }}>
                자기 산식(등급·IC·시뮬 통계)은 가설이며 N 과 함께 읽어야 해요 · 컨센서스 목표가는
                외부 견해이고 발행 금지 자산이에요 · 이 화면은 관리자 전용으로 외부에 공유되지 않아요
            </div>
        </div>
    )
}

addPropertyControls(AdminChat, {
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
    height: { type: ControlType.Number, title: "높이", defaultValue: 620, min: 320, max: 1200, step: 20 },
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
})
