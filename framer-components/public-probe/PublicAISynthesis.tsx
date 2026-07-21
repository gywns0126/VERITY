import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useEffect, useRef, useState, type CSSProperties } from "react"

/**
 * AI 사실 종합 — VERITY 공개 터미널 (AlphaNest). 검증된 공개 사실(DART/KRX/공정위)을 LLM이 자연스럽게 종합.
 *
 * 🚨 RULE 6 escape hatch: ungrounded LLM narrative 금지지만 **자기 trail 위 종합 = 권장 방향**. ChatGPT 못 보는 우리 데이터 위.
 * 🚨 RULE 7 / held-2027 / 유사투자자문 법: **사실 종합·연결만**. 평가·의견·추천·등급 0(빌더 post-filter + 결정론 fallback).
 *   = "사세요/저평가/유망" 절대 없음. 이 컴포넌트는 ai_synthesis.json(빌더 산출) 텍스트를 표시만.
 * 종목 = prop ticker → URL ?q → verity_last_ticker. in-page replaceState 추종 1s 폴링.
 * 데이터 = data/ai_synthesis.json (단일 writer, publish 발행). 없으면 graceful 숨김. 테마 = body[data-framer-theme] 추종.
 */

interface Props {
    ticker: string
    dataUrl: string
    dark: boolean
}
const DEFAULT_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/ai_synthesis.json"

const LIGHT = { bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1", line: "#f0f1f3", vt: "#6c5ce7", vtS: "#f0edff" }
const DARK = { bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b", line: "#222730", vt: "#a99bff", vtS: "#241f3a" }
const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"

function readTickerFromUrl(): string {
    if (typeof window === "undefined") return ""
    try {
        const q = (new URLSearchParams(window.location.search).get("q") || "").trim()
        if (q) return q.toUpperCase()
        return (window.localStorage.getItem("verity_last_ticker") || "").trim().toUpperCase()
    } catch { return "" }
}

function readBodyDark(): boolean {
    // 첫 페인트 flash 방지 — body 속성 미설정(마운트 직후) 시 토글 저장 선호(localStorage) → OS 순 폴백.
    // PublicThemeToggle 이 verity_theme 로 저장 + body[data-framer-theme] 설정 = 동일 소스라 첫 페인트부터 정합.
    try {
        const _lsPref = (typeof localStorage !== "undefined") ? localStorage.getItem("verity_theme") : null
        if (_lsPref === "dark") return true
        if (_lsPref === "light") return false
        if (typeof document !== "undefined" && document.body) {
            const a = document.body.dataset.framerTheme
            if (a === "dark") return true
            if (a === "light") return false
        }
        if (typeof localStorage !== "undefined") {
            const s = localStorage.getItem("verity_theme")
            if (s === "dark") return true
            if (s === "light") return false
        }
        if (typeof window !== "undefined" && window.matchMedia) {
            return window.matchMedia("(prefers-color-scheme: dark)").matches
        }
    } catch (e) {}
    return false
}

/**
 * @framerSupportedLayoutWidth any
 * @framerSupportedLayoutHeight any
 */
// 🎨 페이지 이동 다크 번쩍임 제거(2026-07-20): 첫 마운트만 라이트(SSG/첫방문 매칭·stuck 방지) → 이후 마운트는 실제 테마 즉시.
let __anHyd = false
function anReadDark(): boolean {
    if (typeof document === "undefined") return false
    if (!__anHyd) {
        __anHyd = true
        return false
    }
    const h = document.documentElement ? document.documentElement.dataset.anTheme : null
    if (h === "dark") return true
    if (h === "light") return false
    return !!(document.body && document.body.dataset.framerTheme === "dark")
}


export default function PublicAISynthesis(props: Props) {
    const { ticker, dataUrl, dark } = props
    const onCanvas = RenderTarget.current() === RenderTarget.canvas

    const [themeDark, setThemeDark] = useState<boolean>(() => (onCanvas ? !!dark : anReadDark()))
    useEffect(() => {
        if (onCanvas) return
        const read = () => setThemeDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || typeof document === "undefined" || !document.body) return
        const obs = new MutationObserver(read)
        obs.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => obs.disconnect()
    }, [onCanvas])

    const isDark = onCanvas ? !!dark : themeDark
    const C = isDark ? DARK : LIGHT

    const rootRef = useRef<HTMLDivElement>(null)
    const [w, setW] = useState(0)
    const [tk, setTk] = useState<string>(() => String(ticker || "").trim().toUpperCase())
    const [synth, setSynth] = useState<Record<string, string>>({})
    const [loaded, setLoaded] = useState<boolean>(onCanvas)   // ai_synthesis.json 로드 완료 여부 (스켈레톤 게이트)

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
        window.addEventListener("verity-ticker-change", sync)   // 리포트/결정 컴포넌트의 in-page 종목 전환(콜드 기본값 포함) 즉시 추종
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

    // 텍스트 없음: (1) 로드 중 + 종목 있음 → 스켈레톤, (2) 로드 완료 후 해당 종목 종합 없음/종목 없음 → 숨김
    if (!text) {
        if (loaded || !tk) return <div ref={rootRef} style={{ width: "100%", height: 0, overflow: "hidden" }} />
        const base = isDark ? "#222a33" : "#e9edf1"
        const hiC = isDark ? "#2d3742" : "#f3f5f7"
        const bar = (wd: any, h: number, mt: number): CSSProperties => ({
            width: wd, height: h, marginTop: mt, borderRadius: 6, background: base,
            backgroundImage: `linear-gradient(90deg, ${base} 25%, ${hiC} 37%, ${base} 63%)`,
            backgroundSize: "800px 100%", animation: "vasShimmer 1.4s ease-in-out infinite",
        })
        return (
            <div ref={rootRef} style={wrap}>
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
    dark: { type: ControlType.Boolean, title: "Dark", defaultValue: false, enabledTitle: "On", disabledTitle: "Off" },
})
