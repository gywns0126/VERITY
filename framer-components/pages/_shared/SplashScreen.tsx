import { addPropertyControls, ControlType, RenderTarget } from "framer"
import React, { useEffect, useState } from "react"

/**
 * SplashScreen — AlphaNest 첫 로딩 스플래시 (토스식: 로고 + 밑에 "알파네스트").
 * 모션: 로고·글자 아래서 살짝 떠오르며 페이드 인 → 로고 은은한 호흡(float) → 살짝 커지며 디졸브.
 * 트랜지션 기반(부드럽고 keyframe 충돌 없음). 세션 1회(oncePerSession). 다크감지. 캔버스=정적.
 * ⚠ 보수 구문(옵셔널체이닝/옵셔널catch/defaultProps 회피 — Framer esbuild panic).
 */

const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const SEEN_KEY = "alphanest_splash_seen"
const ENTER_MS = 640
const EASE = "cubic-bezier(.22,1,.36,1)"

function bodyDark(): boolean {
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

function AlphaLogo(props: { size: number }) {
    const size = props.size
    return (
        <svg width={(size * 870) / 830} height={size} viewBox="0 0 870 830" fill="none" aria-hidden="true" style={{ display: "block" }}>
            <path d="M74.9999 403.5C74.9999 617 249 754.5 434 754.5C619 754.5 794.5 617 794.5 403.5" stroke="#3A4268" strokeWidth="150" strokeLinecap="round" />
            <path d="M648.655 309.5C648.655 479 561.655 598 433.655 598C309.943 598 216.155 465 220.655 309.5C220.655 143.815 331.655 0 434.655 0C537.655 0 648.655 140 648.655 309.5Z" fill="#6B51EA" />
        </svg>
    )
}

interface Props {
    holdMs: number
    fadeMs: number
    oncePerSession: boolean
    logoSize: number
    label: string
    dark: boolean
}

type Phase = "show" | "fading" | "done"

export default function SplashScreen(props: Props) {
    const holdMs = props.holdMs > 0 ? props.holdMs : 900
    const fadeMs = props.fadeMs > 0 ? props.fadeMs : 500
    const oncePerSession = props.oncePerSession !== false
    const logoSize = props.logoSize > 0 ? props.logoSize : 84
    const label = props.label || "알파네스트"
    const isCanvas = RenderTarget.current() === RenderTarget.canvas
    const [phase, setPhase] = useState<Phase>("show")
    const [entered, setEntered] = useState<boolean>(isCanvas)

    useEffect(() => {
        if (isCanvas) return
        if (oncePerSession) {
            try {
                if (sessionStorage.getItem(SEEN_KEY) === "1") { setPhase("done"); return }
                sessionStorage.setItem(SEEN_KEY, "1")
            } catch (e) {}
        }
        const t0 = setTimeout(() => setEntered(true), 30)          // 진입 트랜지션 트리거
        const t1 = setTimeout(() => setPhase("fading"), holdMs)
        const t2 = setTimeout(() => setPhase("done"), holdMs + fadeMs)
        return () => { clearTimeout(t0); clearTimeout(t1); clearTimeout(t2) }
    }, [isCanvas, oncePerSession, holdMs, fadeMs])

    if (!isCanvas && phase === "done") return null

    const dark = isCanvas ? !!props.dark : bodyDark()
    const bg = dark ? "#0f1318" : "#f2f4f6"
    const ink = dark ? "#e3e7ec" : "#191f28"
    const fading = phase === "fading"

    // 콘텐츠(로고+글자) 진입/퇴장 트랜스폼
    let contentT = "translateY(0) scale(1)"
    let contentO = 1
    if (!entered) { contentT = "translateY(16px) scale(0.94)"; contentO = 0 }   // 진입 시작점
    if (fading) { contentT = "translateY(0) scale(1.06)"; contentO = 0 }        // 퇴장: 살짝 커지며 디졸브
    const dur = fading ? fadeMs : ENTER_MS

    return (
        <div style={{
            position: "fixed", top: 0, left: 0, right: 0, bottom: 0, zIndex: 100000,
            background: bg, display: "flex", alignItems: "center", justifyContent: "center",
            fontFamily: FONT, opacity: fading ? 0 : 1, transition: `opacity ${fadeMs}ms ease`,
            pointerEvents: fading ? "none" : "auto",
        }}>
            <style>{`@keyframes _an_float{0%,100%{transform:translateY(0)}50%{transform:translateY(-4px)}}`}</style>
            <div style={{
                display: "flex", flexDirection: "column", alignItems: "center", gap: 18,
                transform: contentT, opacity: contentO,
                transition: `transform ${dur}ms ${EASE}, opacity ${dur}ms ease`,
                willChange: "transform, opacity",
            }}>
                <div style={{ animation: (isCanvas || fading) ? "none" : "_an_float 3.2s ease-in-out infinite" }}>
                    <AlphaLogo size={logoSize} />
                </div>
                <div style={{ fontSize: Math.round(logoSize * 0.28), fontWeight: 700, letterSpacing: "-0.5px", color: ink }}>{label}</div>
            </div>
        </div>
    )
}

addPropertyControls(SplashScreen, {
    holdMs: { type: ControlType.Number, title: "유지(ms)", defaultValue: 900, min: 0, max: 4000, step: 100 },
    fadeMs: { type: ControlType.Number, title: "페이드(ms)", defaultValue: 500, min: 100, max: 1500, step: 50 },
    oncePerSession: { type: ControlType.Boolean, title: "세션 1회", defaultValue: true },
    logoSize: { type: ControlType.Number, title: "로고 크기", defaultValue: 84, min: 40, max: 200, step: 4 },
    label: { type: ControlType.String, title: "이름", defaultValue: "알파네스트" },
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
})
