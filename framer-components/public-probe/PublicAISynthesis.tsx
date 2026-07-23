import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * AI 사실 종합 — VERITY 공개 터미널 (AlphaNest). 검증된 공개 사실(DART/KRX/공정위)을 LLM이 자연스럽게 종합.
 *
 * 🚨 RULE 6 escape: 자기 trail 위 종합. 🚨 RULE 7 / held-2027 / 유사투자자문 법: 사실 종합·연결만(평가·의견·추천·등급 0).
 * 종목 = prop ticker → URL ?q → verity_last_ticker. in-page replaceState 추종 1s 폴링. 데이터 없으면 graceful 숨김.
 *
 * 🚨 2026-07-24 테마 = 자체 내장 CSS 변수(--an-as-*) 구동. JS 다크 감지 전면 제거 + 헤드 CSS 의존 제거.
 *   <style>{AN_PALETTE} 로 정적 HTML 정합(하이드레이션 무관). 되돌리지 말 것.
 */

interface Props {
    ticker: string
    dataUrl: string
    dark: boolean
}
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/ai_synthesis.json"

const LIGHT = { bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#f0f1f3", vt: "#6c5ce7", vtS: "#f0edff", skBase: "#e9edf1", skHi: "#f3f5f7" }
const DARK = { bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#222730", vt: "#a99bff", vtS: "#241f3a", skBase: "#222a33", skHi: "#2d3742" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

// 🎨 팔레트 자체 내장 — LIGHT/DARK 를 CSS 변수(--an-as-*)로 발행. 정적 HTML 정합. 되돌리지 말 것.
const _ANP = "as"
const AN_PALETTE =
    "body{" + Object.keys(LIGHT).map((k) => "--an-" + _ANP + "-" + k + ":" + (LIGHT as any)[k]).join(";") + "}" +
    'body[data-framer-theme="dark"]{' + Object.keys(DARK).map((k) => "--an-" + _ANP + "-" + k + ":" + (DARK as any)[k]).join(";") + "}"
const C: Record<string, string> = {}
for (const _k of Object.keys(LIGHT)) C[_k] = "var(--an-" + _ANP + "-" + _k + ")"

function readTickerFromUrl(): string {
    if (typeof window === "undefined") return ""
    try {
        const q = (new URLSearchParams(window.location.search).get("q") || "").trim()
        if (q) return q.toUpperCase()
        return (window.localStorage.getItem("verity_last_ticker") || "").trim().toUpperCase()
    } catch { return "" }
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
export default function PublicAISynthesis(props: Props) {
    const { ticker, dataUrl } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [tk, setTk] = useState<string>(() => String(ticker || "").trim().toUpperCase())
    const [synth, setSynth] = useState<Record<string, string>>({})
    const [loaded, setLoaded] = useState<boolean>(onCanvas)

    useEffect(() => {
        const el = rootRef.current
        if (!el || typeof ResizeObserver === "undefined") return
        const ro = new ResizeObserver((entries) => { for (const e of entries) setW(e.contentRect.width) })
        ro.observe(el)
        return () => ro.disconnect()
    }, [])

    /* 종목 = prop 우선, 없으면 URL ?q. in-page 전환 추종 1s 폴링. */
    useEffect(() => {
        if (onCanvas) return
        const propTk = String(ticker || "").trim().toUpperCase()
        if (propTk) { setTk(propTk); return }
        const sync = () => { const u = readTickerFromUrl(); if (u) setTk((cur) => (cur === u ? cur : u)) }
        sync()
        window.addEventListener("popstate", sync)
        window.addEventListener("verity-ticker-change", sync)
        const iv = setInterval(sync, 1000)
        return () => { window.removeEventListener("popstate", sync); window.removeEventListener("verity-ticker-change", sync); clearInterval(iv) }
    }, [ticker, onCanvas])

    /* ai_synthesis.json 로드 */
    useEffect(() => {
        if (onCanvas || !dataUrl) return
        let alive = true
        fetch(dataUrl)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { const m = d && d.synth && typeof d.synth === "object" ? d.synth : null; if (alive) { if (m) setSynth(m); setLoaded(true) } })
            .catch(() => { if (alive) setLoaded(true) })
        return () => { alive = false }
    }, [dataUrl, onCanvas])

    const text = onCanvas
        ? "삼성전자는 메모리·파운드리 반도체 회사로, PER 17.5(업종 대비 낮음)·ROE 9.1%·부채비율 38% 수준이다. 최근 공시 8건, 내부자 순매수가 있었고 총수일가 지분은 21.2%다."
        : (synth[String(tk).toUpperCase()] || "")
    const narrow = w > 0 && w < 420

    const wrap: CSSProperties = {
        width: "100%", minHeight: "100%", background: C.bg, fontFamily: FONT,
        padding: 0, boxSizing: "border-box", color: C.ink,
    }

    // 텍스트 없음: (1) 로드 중 + 종목 있음 → 스켈레톤, (2) 로드 완료 후 없음/종목 없음 → 숨김
    if (!text) {
        if (loaded || !tk) return <div ref={rootRef} style={{ width: "100%", height: 0, overflow: "hidden" }} />
        const bar = (wd: any, h: number, mt: number): CSSProperties => ({
            width: wd, height: h, marginTop: mt, borderRadius: 6, background: C.skBase,
            backgroundImage: `linear-gradient(90deg, ${C.skBase} 25%, ${C.skHi} 37%, ${C.skBase} 63%)`,
            backgroundSize: "800px 100%", animation: "vasShimmer 1.4s ease-in-out infinite",
        })
        return (
            <div ref={rootRef} style={wrap}>
                <style>{AN_PALETTE}</style>
                <style>{`@keyframes vasShimmer{0%{background-position:-400px 0}100%{background-position:400px 0}}`}</style>
                <div style={{ background: C.card, borderRadius: 16, padding: narrow ? 14 : 18, boxSizing: "border-box", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                    <div style={bar(64, 18, 0)} />
                    <div style={bar("100%", 13, 12)} />
                    <div style={bar("96%", 13, 7)} />
                    <div style={bar("86%", 13, 7)} />
                    <div style={bar("42%", 11, 14)} />
                </div>
            </div>
        )
    }

    return (
        <div ref={rootRef} style={wrap}>
            <style>{AN_PALETTE}</style>
            <div style={{ background: C.card, borderRadius: 16, padding: narrow ? 14 : 18, boxSizing: "border-box", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 8 }}>
                    <span style={{ fontSize: 10.5, fontWeight: 800, color: C.vt, background: C.vtS, borderRadius: 7, padding: "3px 8px", letterSpacing: "-0.2px" }}>AI 종합</span>
                    <span style={{ fontSize: 11, fontWeight: 600, color: C.faint }}>검증 사실 기반</span>
                </div>
                <div style={{ fontSize: narrow ? 13.5 : 14.5, fontWeight: 600, color: C.ink, lineHeight: 1.62, letterSpacing: "-0.2px" }}>{text}</div>
                <div style={{ fontSize: 10.5, color: C.faint, fontWeight: 500, marginTop: 12, lineHeight: 1.55 }}>
                    DART·KRX·공정위 검증 사실을 AI가 종합 (다듬기만, 새 숫자·전망·매수의견 0)
                </div>
            </div>
        </div>
    )
}

addPropertyControls(PublicAISynthesis, {
    ticker: { type: ControlType.String, title: "Ticker(빈값=URL ?q)", defaultValue: "" },
    dataUrl: { type: ControlType.String, title: "Synthesis URL", defaultValue: DEFAULT_URL },
    dark: { type: ControlType.Boolean, title: "Dark(미사용)", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})
