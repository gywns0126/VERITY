import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState } from "react"

/* 아이콘 = Phosphor 공식 path 인라인(fill=currentColor, 버튼 color 상속). npm import 는 Framer typecheck 실패. */
function PhPrinter({ size }: { size: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 256 256" fill="currentColor">
            <path d="M214.67,68H204V40a12,12,0,0,0-12-12H64A12,12,0,0,0,52,40V68H41.33C25.16,68,12,80.56,12,96v80a12,12,0,0,0,12,12H52v28a12,12,0,0,0,12,12H192a12,12,0,0,0,12-12V188h28a12,12,0,0,0,12-12V96C244,80.56,230.84,68,214.67,68ZM76,52H180V68H76ZM180,204H76V172H180Zm40-40H204v-4a12,12,0,0,0-12-12H64a12,12,0,0,0-12,12v4H36V96c0-2.17,2.44-4,5.33-4H214.67c2.89,0,5.33,1.83,5.33,4Zm-16-44a16,16,0,1,1-16-16A16,16,0,0,1,204,120Z" />
        </svg>
    )
}
function PhPencilLine({ size }: { size: number }) {
    return (
        <svg width={size} height={size} viewBox="0 0 256 256" fill="currentColor">
            <path d="M230.15,70.54,185.46,25.86a20,20,0,0,0-28.28,0L33.86,149.17A19.86,19.86,0,0,0,28,163.31V208a20,20,0,0,0,20,20H216a12,12,0,0,0,0-24H125L230.15,98.83A20,20,0,0,0,230.15,70.54ZM91,204H52V165l84-84,39,39ZM192,103,153,64l18.34-18.34,39,39Z" />
        </svg>
    )
}

/**
 * 리포트 추출 허브 — AlphaNest /stock. 팩트 PDF + AI 해석 PDF 버튼 + AI 브리핑 섹션.
 * 종목 추종 = URL ?q= + verity-ticker-change/popstate. RULE 6 = 서버 grounding. RULE 7 = 출처·disclaimer.
 *
 * 🚨 2026-07-24 테마 = 자체 내장 CSS 변수(--an-sbf-*) 구동. JS 다크 감지 전면 제거 + 헤드 CSS 의존 제거.
 *   <style>{AN_PALETTE} 정적 HTML 정합. vtBtn=순보라(AI PDF 버튼, 양모드 #6c5ce7+흰글자). 되돌리지 말 것.
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", violet: "#6c5ce7", violetSoft: "#f0edff", red: "#f04452", green: "#0ca678", vtBtn: "#6c5ce7",
}
const DARK = {
    bg: "#0f1318", card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684",
    line: "#2b2f37", violet: "#a98bff", violetSoft: "#2a2440", red: "#ff6b76", green: "#3ecf8e", vtBtn: "#6c5ce7",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif"
const DEFAULT_API = "https://project-yw131.vercel.app"

// 🎨 팔레트 자체 내장 — LIGHT/DARK 를 CSS 변수(--an-sbf-*)로 발행. 정적 HTML 정합. 되돌리지 말 것.
const _ANP = "sbf"
const AN_PALETTE =
    "body{" + Object.keys(LIGHT).map((k) => "--an-" + _ANP + "-" + k + ":" + (LIGHT as any)[k]).join(";") + "}" +
    'body[data-framer-theme="dark"]{' + Object.keys(DARK).map((k) => "--an-" + _ANP + "-" + k + ":" + (DARK as any)[k]).join(";") + "}"
const C: Record<string, string> = {}
for (const _k of Object.keys(LIGHT)) C[_k] = "var(--an-" + _ANP + "-" + _k + ")"

const PRINT_CSS_ID = "verity-print-facts-css"
const FACTS_CLASS = "verity-print-facts"
const PRINT_CSS =
    "@media screen { [data-aibrief] { display: none !important; } } " +
    "@media print { @page { size: A4 portrait; margin: 10mm; } [data-noprint] { display: none !important; } " +
    `body.${FACTS_CLASS} [data-aibrief] { display: none !important; } }`

function ensurePrintCss() {
    if (typeof document === "undefined") return
    if (document.getElementById(PRINT_CSS_ID)) return
    const el = document.createElement("style")
    el.id = PRINT_CSS_ID
    el.textContent = PRINT_CSS
    document.head.appendChild(el)
}
function doPrint(factsOnly: boolean) {
    if (typeof window === "undefined" || typeof document === "undefined") return
    ensurePrintCss()
    if (factsOnly) document.body.classList.add(FACTS_CLASS)
    else document.body.classList.remove(FACTS_CLASS)
    try {
        window.print()
    } finally {
        setTimeout(() => document.body.classList.remove(FACTS_CLASS), 800)
    }
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
    if (!t) {
        try {
            t = (window.localStorage.getItem("verity_last_ticker") || "").trim()
        } catch (e) {}
    }
    t = t.toUpperCase()
    return /^\d{6}$/.test(t) || /^[A-Z][A-Z0-9.\-]{0,9}$/.test(t) ? t : ""
}

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
    width?: number
    dark?: boolean
    apiBase?: string
}) {
    // ETF/ETN 선택 시 자기 숨김 — StockReport 가 body[data-verity-asset-kind] 신호 발행 (2026-07-10)
    const [assetKind, setAssetKind] = useState<string>("stock")
    useEffect(() => {
        if (typeof document === "undefined" || !document.body) return
        const read = () =>
            setAssetKind(document.body.dataset.verityAssetKind || "stock")
        read()
        if (typeof MutationObserver === "undefined") return
        const obs = new MutationObserver(read)
        obs.observe(document.body, {
            attributes: true,
            attributeFilter: ["data-verity-asset-kind"],
        })
        return () => obs.disconnect()
    }, [])
    const onCanvas = RenderTarget.current() === RenderTarget.canvas
    const [tk, setTk] = useState<string>("")
    const [state, setState] = useState<string>("idle") // idle | loading | done | error
    const [data, setData] = useState<any>(null)
    const [errMsg, setErrMsg] = useState<string>("")

    const base = (props.apiBase || DEFAULT_API).replace(/\/+$/, "")

    // 종목 추종 — 바뀌면 상태 리셋 + 오늘 캐시 자동 조회(생성 없음, 비용 0)
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        const reread = () => {
            const t = resolveTicker()
            setTk((prev) => {
                if (prev !== t) {
                    setState("idle")
                    setData(null)
                    setErrMsg("")
                    if (t) {
                        fetch(
                            `${base}/api/verity/stock-brief?ticker=${encodeURIComponent(t)}&mode=cached`,
                            { cache: "no-store" }
                        )
                            .then((r) => (r.ok ? r.json() : null))
                            .then((body) => {
                                if (
                                    alive &&
                                    body &&
                                    body.brief &&
                                    resolveTicker() === t
                                ) {
                                    setData(body)
                                    setState("done")
                                }
                            })
                            .catch(() => {})
                    }
                }
                return t
            })
        }
        reread()
        window.addEventListener("verity-ticker-change", reread)
        window.addEventListener("popstate", reread)
        return () => {
            alive = false
            window.removeEventListener("verity-ticker-change", reread)
            window.removeEventListener("popstate", reread)
        }
    }, [onCanvas, base])

    const generate = (printAfter: boolean) => {
        if (!tk || state === "loading") return
        setState("loading")
        setErrMsg("")
        fetch(
            `${base}/api/verity/stock-brief?ticker=${encodeURIComponent(tk)}`,
            { cache: "no-store" }
        )
            .then((r) => r.json().then((body) => ({ ok: r.ok, body })))
            .then(({ ok, body }) => {
                if (ok && body && body.brief) {
                    setData(body)
                    setState("done")
                    if (printAfter) setTimeout(() => doPrint(false), 400)
                } else {
                    setErrMsg(
                        (body && body.message) ||
                            "브리핑을 만들지 못했어요. 잠시 후 다시 시도해 주세요."
                    )
                    setState("error")
                }
            })
            .catch(() => {
                setErrMsg("연결이 불안정해요. 잠시 후 다시 시도해 주세요.")
                setState("error")
            })
    }

    const onAiPdf = () => {
        if (tk && typeof window !== "undefined")
            window.open(
                base + "/api/ai_report?ticker=" + encodeURIComponent(tk),
                "_blank",
                "noopener"
            )
    }

    const wrap: any = {
        width: props.width || 380,
        fontFamily: FONT,
        background: "transparent",
        color: C.ink,
        padding: 14,
        boxSizing: "border-box",
    }
    const sections = data ? parseBrief(data.brief) : []
    const btnBase: any = {
        border: "none",
        fontFamily: FONT,
        padding: "10px 15px",
        borderRadius: 11,
        fontSize: 13,
        fontWeight: 800,
        lineHeight: 1,
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
    }

    if (assetKind === "etf") return null // ETF/ETN = 기업 전용 섹션 숨김

    return (
        <div style={wrap}>
            <style>{AN_PALETTE}</style>
            <div
                data-noprint
                style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center" }}
            >
                <button
                    onClick={() => {
                        if (tk && typeof window !== "undefined")
                            window.open(
                                base + "/api/fact_report?ticker=" + encodeURIComponent(tk),
                                "_blank",
                                "noopener"
                            )
                    }}
                    disabled={!tk}
                    style={{
                        ...btnBase,
                        cursor: tk ? "pointer" : "default",
                        opacity: tk ? 1 : 0.5,
                        background: C.violetSoft,
                        color: C.violet,
                    }}
                >
                    <PhPrinter size={14} />
                    팩트 리포트 PDF
                </button>
                <button
                    onClick={onAiPdf}
                    disabled={!tk || state === "loading"}
                    style={{
                        ...btnBase,
                        cursor: tk && state !== "loading" ? "pointer" : "default",
                        background: tk ? C.vtBtn : C.line,
                        color: tk ? "#fff" : C.faint,
                    }}
                >
                    <PhPencilLine size={14} />
                    {state === "loading" ? "브리핑 생성 중…" : "AI 해석 리포트 PDF"}
                </button>
            </div>
            <div
                data-noprint
                style={{ fontSize: 10.5, color: C.faint, fontWeight: 600, marginTop: 7, lineHeight: 1.5, textAlign: "center" }}
            >
                팩트 = 100% 공개 데이터 · AI 해석 = 같은 데이터 위에 요약 서술이 붙어요
                {state !== "done" ? " (첫 생성 ~10초, 하루 1회 생성 후 캐시)" : ""}
            </div>

            {state === "loading" && (
                <div data-noprint style={{ marginTop: 12 }}>
                    {[86, 100, 94].map((wd, i) => (
                        <div key={i} style={{ height: 12, width: wd + "%", background: C.line, borderRadius: 6, marginTop: i ? 8 : 0 }} />
                    ))}
                    <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 10 }}>
                        공개 데이터 조립 중 — 완료되면 인쇄 창이 열려요
                    </div>
                </div>
            )}

            {state === "error" && (
                <div data-noprint style={{ fontSize: 12.5, color: C.red, fontWeight: 600, marginTop: 12, lineHeight: 1.6 }}>
                    {errMsg}
                </div>
            )}

            {state === "done" && data && (
                <div data-aibrief style={{ marginTop: 12 }}>
                    <div style={{ background: C.card, borderRadius: 14, padding: 15, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                            <span style={{ fontSize: 14.5, fontWeight: 800 }}>
                                AI 브리핑 · {data.name}{" "}
                                <span style={{ color: C.faint, fontSize: 12, fontWeight: 700 }}>{data.ticker}</span>
                            </span>
                            <span style={{ fontSize: 10.5, color: C.faint, fontWeight: 600 }}>
                                {data.cached ? "오늘 생성분 · " : ""}
                                {fmtAge(data.generated_at)}
                            </span>
                        </div>
                        {sections.map((s, i) => (
                            <div key={i} style={{ marginTop: i === 0 ? 10 : 12 }}>
                                {s.title && (
                                    <div style={{ fontSize: 12.5, fontWeight: 800, color: C.violet, marginBottom: 4 }}>{s.title}</div>
                                )}
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
                        {data.disclaimer || "공개 데이터 사실 기반 자동 생성"}
                    </div>
                </div>
            )}
        </div>
    )
}

addPropertyControls(PublicStockBrief, {
    width: { type: ControlType.Number, title: "Width", defaultValue: 380 },
    dark: { type: ControlType.Boolean, title: "Dark(미사용)", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
    apiBase: { type: ControlType.String, title: "API Base", defaultValue: DEFAULT_API },
})
