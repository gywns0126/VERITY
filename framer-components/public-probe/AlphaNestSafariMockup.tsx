import { addPropertyControls, ControlType, RenderTarget } from "framer"
import { useState, useEffect } from "react"

/**
 * AlphaNestSafariMockup — 사파리(macOS) 브라우저 창 목업 + 라이브 임베드.
 *
 * 트래픽 라이트 + 중앙 주소창(자물쇠+호스트) + LIVE 태그 → 아래 실사이트 iframe.
 * 스크린 = 포스터→탭하면 라이브(LCP 보호). 프레임 색 = 사이트 테마 따라감(라이트/다크).
 *
 * ⚠ 보수 구문(옵셔널체이닝 ?. / 널병합 ?? / 옵셔널 catch{} / defaultProps 회피 — Framer esbuild panic).
 *
 * @framerSupportedLayoutWidth auto
 * @framerSupportedLayoutHeight auto
 */

const FONT = '"Apple SD Gothic Neo", -apple-system, "Segoe UI", Pretendard, sans-serif'

function readBodyDark() {
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
        if (typeof window !== "undefined" && window.matchMedia) return window.matchMedia("(prefers-color-scheme: dark)").matches
    } catch (e) {}
    return false
}

function prettyHost(u: any) {
    try {
        return String(u).replace(/^https?:\/\//, "").replace(/\/.*$/, "")
    } catch (e) {
        return u
    }
}

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


export default function AlphaNestSafariMockup(props: any) {
    const url = props.url || "https://www.alphanest.kr/"
    const width = props.width > 0 ? props.width : 900
    const ratio = props.ratio > 0 ? props.ratio : 0.62
    const mode = props.mode || "eager"
    const showToolbar = props.showToolbar !== false
    const showLive = props.showLive !== false
    const accent = props.accent || "#6c5ce7"
    const posterBg = props.posterBg || "linear-gradient(135deg,#6c5ce7 0%,#4a3aa8 100%)"
    const ctaLabel = props.ctaLabel || "직접 해보기"
    const caption = props.caption || "실제 사이트가 이 안에서 구동됩니다"

    const isCanvas = RenderTarget.current() === RenderTarget.canvas
    const [dark, setDark] = useState(isCanvas ? !!props.dark : anReadDark())
    const [active, setActive] = useState(mode === "eager")
    const [loaded, setLoaded] = useState(false)

    useEffect(() => {
        setActive(mode === "eager")
        setLoaded(false)
    }, [mode, url])

    useEffect(() => {
        if (isCanvas) {
            setDark(!!props.dark)
            return
        }
        const read = () => setDark(readBodyDark())
        read()
        if (typeof MutationObserver === "undefined" || !document.body) return
        const o = new MutationObserver(read)
        o.observe(document.body, { attributes: true, attributeFilter: ["data-framer-theme"] })
        return () => o.disconnect()
    }, [isCanvas, props.dark])

    // 치수
    const W = Math.round(width)
    const barH = Math.max(38, Math.round(W * 0.052))
    const screenH = Math.round(W * ratio)
    const rad = Math.max(8, Math.round(W * 0.014))
    const dotSize = Math.max(10, Math.round(barH * 0.26))
    const pillW = Math.round(W * 0.46)
    const iconC = dark ? "#8a8f98" : "#9aa0a8"

    // 사파리 팔레트
    const barBg = dark ? "#2b2c31" : "#f3f3f5"
    const barLine = dark ? "#1b1c20" : "#e2e3e8"
    const pillBg = dark ? "#3a3b41" : "#ffffff"
    const pillText = dark ? "#c3c6cd" : "#6b7280"
    const winShadow = dark ? "0 30px 70px -24px rgba(0,0,0,0.6)" : "0 30px 70px -22px rgba(17,24,39,0.24)"
    const winBorder = dark ? "1px solid #23242a" : "1px solid rgba(17,24,39,0.08)"

    const dot = (c: any) => ({ width: dotSize, height: dotSize, borderRadius: "50%", background: c })

    // ── 스크린(임베드) 노드 ──
    const screenNode = (
        <div style={{ position: "relative", width: "100%", height: screenH, background: "#ffffff" }}>
            <style>{"@keyframes asm_spin{to{transform:rotate(360deg)}}@keyframes asm_blink{0%,100%{opacity:1}50%{opacity:.35}}"}</style>
            {active ? (
                <>
                    {!loaded ? (
                        <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 14, background: "#ffffff" }}>
                            <div style={{ width: 34, height: 34, borderRadius: "50%", border: "3px solid #eeeeee", borderTopColor: accent, animation: "asm_spin 0.8s linear infinite" }} />
                            <div style={{ color: "#9a95b5", fontSize: 14 }}>실시간 사이트 불러오는 중…</div>
                        </div>
                    ) : null}
                    <iframe
                        src={url}
                        title="AlphaNest live"
                        style={{ width: "100%", height: "100%", border: "0", display: "block" }}
                        onLoad={() => setLoaded(true)}
                        referrerPolicy="no-referrer-when-downgrade"
                        loading="eager"
                    />
                </>
            ) : (
                <button
                    type="button"
                    onClick={() => setActive(true)}
                    style={{ position: "absolute", inset: 0, border: "0", cursor: "pointer", background: posterBg, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 14, color: "#ffffff", fontFamily: FONT }}
                >
                    <div style={{ width: 64, height: 64, borderRadius: "50%", background: "rgba(255,255,255,0.16)", border: "1px solid rgba(255,255,255,0.4)", display: "flex", alignItems: "center", justifyContent: "center" }}>
                        <div style={{ width: 0, height: 0, borderTop: "11px solid transparent", borderBottom: "11px solid transparent", borderLeft: "18px solid #ffffff", marginLeft: 5 }} />
                    </div>
                    <div style={{ fontSize: 16, fontWeight: 600, letterSpacing: -0.2 }}>{ctaLabel}</div>
                    {caption ? <div style={{ fontSize: 12, opacity: 0.72 }}>{caption}</div> : null}
                </button>
            )}
        </div>
    )

    return (
        <div style={{ width: W, borderRadius: rad, overflow: "hidden", background: "#fff", boxShadow: winShadow, border: winBorder, fontFamily: FONT }}>
            {showToolbar ? (
                <div style={{ position: "relative", width: "100%", height: barH, background: barBg, borderBottom: "1px solid " + barLine, display: "flex", alignItems: "center" }}>
                    {/* 트래픽 라이트 */}
                    <div style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", display: "flex", gap: 8 }}>
                        <span style={dot("#ff5f57")} />
                        <span style={dot("#febc2e")} />
                        <span style={dot("#28c840")} />
                    </div>
                    {/* 중앙 주소창 */}
                    <div style={{ position: "absolute", left: "50%", top: "50%", transform: "translate(-50%,-50%)", width: pillW, height: Math.round(barH * 0.56), maxWidth: "62%", background: pillBg, borderRadius: 7, display: "flex", alignItems: "center", justifyContent: "center", gap: 6, boxShadow: dark ? "none" : "inset 0 0 0 1px rgba(17,24,39,0.05)" }}>
                        <svg width={Math.round(barH * 0.26)} height={Math.round(barH * 0.26)} viewBox="0 0 24 24" fill="none">
                            <rect x="5" y="11" width="14" height="9" rx="2" fill={iconC} />
                            <path d="M8 11V8a4 4 0 0 1 8 0v3" stroke={iconC} strokeWidth="2" fill="none" />
                        </svg>
                        <span style={{ fontSize: Math.max(11, Math.round(barH * 0.29)), color: pillText, fontWeight: 500, letterSpacing: 0.1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{prettyHost(url)}</span>
                    </div>
                    {/* LIVE 태그 */}
                    {showLive ? (
                        <div style={{ position: "absolute", right: 14, top: "50%", transform: "translateY(-50%)", display: "flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 700, color: "#1aa860", letterSpacing: 0.3 }}>
                            <span style={{ width: 7, height: 7, borderRadius: "50%", background: "#28c840", boxShadow: "0 0 8px #28c840", animation: "asm_blink 1.6s infinite" }} />
                            LIVE
                        </div>
                    ) : null}
                </div>
            ) : null}
            {screenNode}
        </div>
    )
}

addPropertyControls(AlphaNestSafariMockup, {
    url: { type: ControlType.String, title: "URL", defaultValue: "https://www.alphanest.kr/" },
    width: { type: ControlType.Number, title: "너비", min: 320, max: 1600, step: 10, defaultValue: 900, displayStepper: true },
    ratio: { type: ControlType.Number, title: "화면 비율(H/W)", min: 0.4, max: 1.2, step: 0.02, defaultValue: 0.62 },
    mode: { type: ControlType.Enum, title: "모드", options: ["eager", "lazy"], optionTitles: ["즉시 로드", "탭하면 라이브"], defaultValue: "eager", displaySegmentedControl: true },
    showToolbar: { type: ControlType.Boolean, title: "툴바", defaultValue: true },
    showLive: { type: ControlType.Boolean, title: "LIVE 태그", defaultValue: true },
    accent: { type: ControlType.Color, title: "액센트", defaultValue: "#6c5ce7" },
    posterBg: { type: ControlType.String, title: "포스터 배경", defaultValue: "linear-gradient(135deg,#6c5ce7 0%,#4a3aa8 100%)" },
    ctaLabel: { type: ControlType.String, title: "버튼 문구", defaultValue: "직접 해보기" },
    caption: { type: ControlType.String, title: "포스터 캡션", defaultValue: "실제 사이트가 이 안에서 구동됩니다" },
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
})
