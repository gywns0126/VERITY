import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useState } from "react"

/* 아이콘 = Phosphor 공식 path 원본 인라인 (printer-bold / pencil-simple-line-bold, MIT).
 * npm import 는 Framer typecheck 에서 모듈 해석 실패(2307) — publish 리스크라 원본 데이터 직접 사용. 자작 SVG 아님. */
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
 * 리포트 추출 허브 — AlphaNest /stock. 두 버튼 + AI 브리핑 섹션 = 단일 컴포넌트 (PM 결정 2026-07-03).
 *   [팩트 리포트 PDF]     = 즉시 window.print(), AI 브리핑 섹션은 제외(body.verity-print-facts) — 100% 데이터
 *   [AI 해석 리포트 PDF]  = 브리핑 있으면 포함 인쇄 / 없으면 생성(~10s) 후 자동 인쇄 — 명시적 의도라 대기 결합 OK
 * 종목 진입 시 mode=cached 자동 조회(생성 비용 0) — 오늘 생성분 있으면 브리핑이 미리 떠 있음.
 * 기존 PublicPrintButton 은 타 페이지용으로 존치 — /stock 인스턴스는 이 컴포넌트로 대체.
 *
 * 종목 추종 = URL ?q= + verity-ticker-change/popstate (PublicLiveChart 동일 패턴). 종목 바뀌면 상태 리셋.
 * 🚨 RULE 6 = 서버가 grounding 밖 생성 차단. RULE 7 = 출처 라벨 + disclaimer 고정 노출, 점수/추천 0.
 * 다크모드 자가감지(body[data-framer-theme]).
 */

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", violet: "#6c5ce7", violetSoft: "#f0edff", red: "#f04452", green: "#0ca678",
}
const DARK = {
    bg: "#16181d", card: "#1e2128", ink: "#f0f2f5", sub: "#b0b8c1", faint: "#6b7684",
    line: "#2b2f37", violet: "#a98bff", violetSoft: "#2a2440", red: "#ff6b76", green: "#3ecf8e",
}
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, sans-serif"
const DEFAULT_API = "https://project-yw131.vercel.app"

/* 인쇄 CSS — PublicPrintButton 과 별개 id (facts 모드 규칙 포함). @page 중복 주입은 무해. */
const PRINT_CSS_ID = "verity-print-facts-css"
const FACTS_CLASS = "verity-print-facts"
const PRINT_CSS =
    // 화면에선 인라인 AI 브리핑 숨김(2026-07-04, PM: 요약 브리핑 제거·버튼만 노출) — 인쇄엔 유지(AI PDF 내용용)
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
        // print 다이얼로그가 비동기인 브라우저 대비 — 닫힌 뒤 클래스 잔존 차단
        setTimeout(() => document.body.classList.remove(FACTS_CLASS), 800)
    }
}

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

    const base = (props.apiBase || DEFAULT_API).replace(/\/+$/, "")

    // 종목 추종 — 바뀌면 상태 리셋 + 오늘 캐시 자동 조회(생성 없음, 비용 0)
    useEffect(() => {
        if (onCanvas) return
        let alive = true
        const reread = () => {
            const t = resolveTicker()
            setTk((prev) => {
                if (prev !== t) {
                    setState("idle"); setData(null); setErrMsg("")
                    if (t) {
                        fetch(`${base}/api/verity/stock-brief?ticker=${encodeURIComponent(t)}&mode=cached`, { cache: "no-store" })
                            .then((r) => (r.ok ? r.json() : null))
                            .then((body) => {
                                if (alive && body && body.brief && resolveTicker() === t) { setData(body); setState("done") }
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
        return () => { alive = false; window.removeEventListener("verity-ticker-change", reread); window.removeEventListener("popstate", reread) }
    }, [onCanvas, base])

    const isDark = onCanvas ? !!props.dark : themeDark
    const C = isDark ? DARK : LIGHT

    const generate = (printAfter: boolean) => {
        if (!tk || state === "loading") return
        setState("loading"); setErrMsg("")
        fetch(`${base}/api/verity/stock-brief?ticker=${encodeURIComponent(tk)}`, { cache: "no-store" })
            .then((r) => r.json().then((body) => ({ ok: r.ok, body })))
            .then(({ ok, body }) => {
                if (ok && body && body.brief) {
                    setData(body); setState("done")
                    if (printAfter) setTimeout(() => doPrint(false), 400) // 섹션 렌더 후 인쇄
                } else {
                    setErrMsg((body && body.message) || "브리핑을 만들지 못했어요. 잠시 후 다시 시도해 주세요.")
                    setState("error")
                }
            })
            .catch(() => { setErrMsg("연결이 불안정해요. 잠시 후 다시 시도해 주세요."); setState("error") })
    }

    const onAiPdf = () => {
        if (state === "done" && data) doPrint(false)
        else generate(true)
    }

    const wrap: any = { width: props.width || 380, fontFamily: FONT, background: C.bg, color: C.ink, padding: 14, boxSizing: "border-box" }
    const sections = data ? parseBrief(data.brief) : []
    const greenSoft = isDark ? "rgba(62,207,142,0.16)" : "#e7f7ef"
    // 리포트 카드 공통 (토스식 소프트 카드) — 아이콘 사각 + 제목/설명 + › CTA
    const cardBase: any = {
        border: "none", fontFamily: FONT, textAlign: "left", width: "100%",
        background: C.card, borderRadius: 14, padding: 14, boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
        display: "flex", alignItems: "center", gap: 12,
    }
    const iconSq = (bg: string, fg: string): any => ({
        width: 42, height: 42, borderRadius: 12, background: bg, color: fg, flexShrink: 0,
        display: "flex", alignItems: "center", justifyContent: "center",
    })
    const chip = (bg: string, fg: string): any => ({ fontSize: 10, fontWeight: 800, color: fg, background: bg, borderRadius: 6, padding: "2px 7px", whiteSpace: "nowrap" })

    return (
        <div style={wrap}>
            {/* ── 리포트 카드 2종 (미리보기·설명 리치 카드) — 상품 구분: 100% 데이터 vs 데이터+AI 해석 ── */}
            <div data-noprint style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {/* 팩트 리포트 — 즉시·무료 */}
                <button onClick={() => doPrint(true)} style={{ ...cardBase, cursor: "pointer" }}>
                    <span style={iconSq(C.violetSoft, C.violet)}><PhPrinter size={21} /></span>
                    <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                            <span style={{ fontSize: 14, fontWeight: 800, color: C.ink }}>팩트 리포트 PDF</span>
                            <span style={chip(greenSoft, C.green)}>즉시 · 무료</span>
                        </div>
                        <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3, lineHeight: 1.45 }}>
                            100% 공개 데이터 — 시세·재무·수급·공시·내부자를 한 장으로
                        </div>
                    </div>
                    <span style={{ fontSize: 17, color: C.faint, flexShrink: 0, fontWeight: 700 }}>›</span>
                </button>

                {/* AI 해석 리포트 — 팩트 위 AI 요약 서술 */}
                <button onClick={onAiPdf} disabled={!tk || state === "loading"}
                    style={{ ...cardBase, cursor: tk && state !== "loading" ? "pointer" : "default", opacity: tk ? 1 : 0.6 }}>
                    <span style={iconSq(tk ? C.violet : C.line, tk ? "#fff" : C.faint)}><PhPencilLine size={21} /></span>
                    <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                            <span style={{ fontSize: 14, fontWeight: 800, color: C.ink }}>AI 해석 리포트 PDF</span>
                            <span style={chip(C.violetSoft, C.violet)}>{data && data.cached ? "오늘 생성분" : "첫 생성 ~10초"}</span>
                        </div>
                        <div style={{ fontSize: 11.5, color: C.faint, fontWeight: 600, marginTop: 3, lineHeight: 1.45 }}>
                            {state === "loading"
                                ? "브리핑 생성 중… 완료되면 인쇄 창이 열려요"
                                : !tk
                                    ? "종목을 먼저 선택하면 만들 수 있어요"
                                    : "같은 데이터 위에 AI가 요약 서술을 더한 리포트 (하루 1회 캐시)"}
                        </div>
                    </div>
                    <span style={{ fontSize: 17, color: C.faint, flexShrink: 0, fontWeight: 700 }}>{state === "loading" ? "…" : "›"}</span>
                </button>
            </div>

            {/* ── 상태별 본문 (에러만 화면 노출 · 로딩은 카드가 표시) ── */}
            {state === "error" && (
                <div data-noprint style={{ fontSize: 12.5, color: C.red, fontWeight: 600, marginTop: 12, lineHeight: 1.6 }}>{errMsg}</div>
            )}

            {/* ── AI 브리핑 섹션 — data-aibrief: 팩트 모드 인쇄에서 제외 ── */}
            {state === "done" && data && (
                <div data-aibrief style={{ marginTop: 12 }}>
                    <div style={{ background: C.card, borderRadius: 14, padding: 15, boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                            <span style={{ fontSize: 14.5, fontWeight: 800 }}>AI 브리핑 · {data.name} <span style={{ color: C.faint, fontSize: 12, fontWeight: 700 }}>{data.ticker}</span></span>
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
                        {data.disclaimer || "공개 데이터 사실 기반 자동 생성"}
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
