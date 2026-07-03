import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState } from "react"

/**
 * AI 브리핑 (Stock Brief) — AlphaNest /stock. 무료 자판기 v0.
 * [AI 브리핑 생성] → /api/verity/stock-brief?ticker= (grounding=발행 JSON, Gemini, 24h 캐시+일일 캡)
 * → 인라인 섹션 렌더. data-noprint 없음 — 기존 PublicPrintButton(window.print)이 이 섹션까지 PDF 로 출력.
 *
 * 종목 추종 = URL ?q= + verity-ticker-change/popstate (PublicLiveChart 동일 패턴). 종목 바뀌면 상태 리셋.
 * 🚨 RULE 6 = 서버가 grounding 밖 생성 차단. RULE 7 = 출처 라벨 + disclaimer 고정 노출, 점수/추천 0.
 * 다크모드 자가감지(body[data-framer-theme]).
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", violet: "#6c5ce7", violetSoft: "#f0edff", red: "#f04452",
}
const DARK = {
    bg: "#16181d", card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684",
    line: "#2b2f37", violet: "#a98bff", violetSoft: "#2a2440", red: "#ff6b76",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif"
const DEFAULT_API = "https://project-yw131.vercel.app"

function readBodyDark(): boolean {
    if (typeof document === "undefined" || !document.body) return false
    return document.body.dataset.framerTheme === "dark"
}
function fmtAge(iso: any): string {
    if (!iso) return ""
    try {
        const mins = Math.max(0, Math.round((Date.now() - new Date(String(iso)).getTime()) / 60000))
        if (mins < 60) return mins + "분 전"
        const hrs = Math.round(mins / 60)
        if (hrs < 24) return hrs + "시간 전"
        return Math.round(hrs / 24) + "일 전"
    } catch (e) {
        return ""
    }
}
function resolveTicker(): string {
    if (typeof window === "undefined") return ""
    let t = (new URLSearchParams(window.location.search).get("q") || "").trim()
    if (!t) { try { t = (window.localStorage.getItem("verity_last_ticker") || "").trim() } catch (e) {} }
    t = t.toUpperCase()
    return /^\d{6}$/.test(t) || /^[A-Z][A-Z0-9.\-]{0,9}$/.test(t) ? t : ""
}

/* "## 제목" 구분 마크다운-라이트 → 섹션 배열 */
function parseBrief(text: string): { title: string; body: string }[] {
    const out: { title: string; body: string }[] = []
    let cur: { title: string; body: string } | null = null
    for (const raw of String(text || "").split("\n")) {
        const line = raw.trim()
        if (line.indexOf("## ") === 0) {
            if (cur) out.push(cur)
            cur = { title: line.slice(3).trim(), body: "" }
        } else if (line) {
            if (!cur) cur = { title: "", body: "" }
            cur.body += (cur.body ? " " : "") + line
        }
    }
    if (cur) out.push(cur)
    return out
}

export default function PublicStockBrief(props: {
    width?: number; dark?: boolean; apiBase?: string
}) {
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [themeDark, setThemeDark] = useState<boolean>(!!props.dark)
    const [tk, setTk] = useState<string>("")
    const [state, setState] = useState<string>("idle") // idle | loading | done | error
    const [data, setData] = useState<any>(null)
    const [errMsg, setErrMsg] = useState<string>("")

    useEffect(() => {
        if (onCanvas) return
        setThemeDark(readBodyDark())
        const obs = new MutationObserver(() => setThemeDark(readBodyDark()))
        if (document.body) obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    // 종목 추종 — 바뀌면 브리핑 상태 리셋 (다른 종목 브리핑 잔상 차단)
    useEffect(() => {
        if (onCanvas) return
        const reread = () => {
            const t = resolveTicker()
            setTk((prev) => {
                if (prev !== t) { setState("idle"); setData(null); setErrMsg("") }
                return t
            })
        }
        reread()
        window.addEventListener("verity-ticker-change", reread)
        window.addEventListener("popstate", reread)
        return () => { window.removeEventListener("verity-ticker-change", reread); window.removeEventListener("popstate", reread) }
    }, [onCanvas])

    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT
    const base = (props.apiBase || DEFAULT_API).replace(/\/+$/, "")

    const generate = () => {
        if (!tk || state === "loading") return
        setState("loading"); setErrMsg("")
        fetch(`${base}/api/verity/stock-brief?ticker=${encodeURIComponent(tk)}`, { cache: "no-store" })
            .then((r) => r.json().then((body) => ({ ok: r.ok, body })))
            .then(({ ok, body }) => {
                if (ok && body && body.brief) { setData(body); setState("done") }
                else {
                    setErrMsg((body && body.message) || "브리핑을 만들지 못했어요. 잠시 후 다시 시도해 주세요.")
                    setState("error")
                }
            })
            .catch(() => { setErrMsg("연결이 불안정해요. 잠시 후 다시 시도해 주세요."); setState("error") })
    }

    const wrap: any = { width: props.width || 380, fontFamily: FONT, background: C.bg, color: C.ink, padding: 14, boxSizing: "border-box" }
    const sections = data ? parseBrief(data.brief) : []

    return (
        <div style={wrap}>
            {/* 헤더 + 생성 버튼 */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <div>
                    <div style={{ fontSize: 16.5, fontWeight: 800, letterSpacing: "-0.4px" }}>AI 브리핑</div>
                    <div style={{ fontSize: 11, color: C.faint, fontWeight: 600, marginTop: 2 }}>
                        공개 데이터 사실만 조립해요 · 하루 1회 생성 후 캐시
                    </div>
                </div>
                {state !== "done" && (
                    <button data-noprint onClick={generate} disabled={!tk || state === "loading"} style={{
                        border: "none", cursor: tk && state !== "loading" ? "pointer" : "default", fontFamily: FONT,
                        padding: "9px 15px", borderRadius: 11, fontSize: 13, fontWeight: 800,
                        background: tk ? C.violet : C.line, color: tk ? "#fff" : C.faint,
                    }}>
                        {state === "loading" ? "생성 중…" : "브리핑 생성"}
                    </button>
                )}
            </div>

            {/* 상태별 본문 */}
            {!tk && (
                <div style={{ fontSize: 12.5, color: C.faint, fontWeight: 600, marginTop: 12 }}>종목을 먼저 선택해 주세요.</div>
            )}

            {tk && state === "idle" && (
                <div style={{ fontSize: 12.5, color: C.sub, fontWeight: 600, marginTop: 12, lineHeight: 1.6 }}>
                    {tk} 의 재무·수급·내부자·공시 사실을 한 편의 브리핑으로 조립해요. 생성 후 위 리포트와 함께 PDF 추출에 포함돼요.
                </div>
            )}

            {state === "loading" && (
                <div style={{ marginTop: 12 }}>
                    {[86, 100, 94].map((w, i) => (
                        <div key={i} style={{ height: 12, width: w + "%", background: C.line, borderRadius: 6, marginTop: i ? 8 : 0 }} />
                    ))}
                    <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 10 }}>공개 데이터 조립 중 — 보통 10초 안쪽이에요</div>
                </div>
            )}

            {state === "error" && (
                <div style={{ fontSize: 12.5, color: C.red, fontWeight: 600, marginTop: 12, lineHeight: 1.6 }}>{errMsg}</div>
            )}

            {state === "done" && data && (
                <div style={{ marginTop: 12 }}>
                    <div style={{ background: C.card, borderRadius: 14, padding: 15, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                            <span style={{ fontSize: 14.5, fontWeight: 800 }}>{data.name} <span style={{ color: C.faint, fontSize: 12, fontWeight: 700 }}>{data.ticker}</span></span>
                            <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 600 }}>
                                {data.cached ? "오늘 생성분 · " : ""}{fmtAge(data.generated_at)}
                            </span>
                        </div>
                        {sections.map((s, i) => (
                            <div key={i} style={{ marginTop: i === 0 ? 10 : 12 }}>
                                {s.title && <div style={{ fontSize: 12.5, fontWeight: 800, color: C.violet, marginBottom: 4 }}>{s.title}</div>}
                                <div style={{ fontSize: 13, color: C.sub, fontWeight: 500, lineHeight: 1.65 }}>{s.body}</div>
                            </div>
                        ))}
                        {Array.isArray(data.sources) && data.sources.length > 0 && (
                            <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 12 }}>
                                재료: {data.sources.join(" · ")}
                            </div>
                        )}
                    </div>
                    <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 8, lineHeight: 1.5 }}>
                        {data.disclaimer || "공개 데이터 사실 기반 자동 생성 · 점수·등급·종목 추천 아님"}
                    </div>
                </div>
            )}
        </div>
    )
}

addPropertyControls(PublicStockBrief, {
    width: { type: ControlType.Number, title: "Width", defaultValue: 380 },
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
})
