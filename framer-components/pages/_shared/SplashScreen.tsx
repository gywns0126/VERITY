import { addPropertyControls, ControlType, RenderTarget } from "framer"
import React, { useEffect, useState } from "react"

/**
 * SplashScreen — AlphaNest 첫 로딩 스플래시 (토스식: 로고 + 밑에 "알파네스트").
 * 전체화면 오버레이 → 로고 페이드+스케일 인 → 잠깐 유지 → 전체 페이드아웃 → 제거.
 * 세션 1회만(oncePerSession) — 페이지 이동마다 반복 X. 다크감지. 캔버스=정적 미리보기.
 * ⚠ 보수 구문(옵셔널체이닝/옵셔널catch/defaultProps 회피 — Framer esbuild panic).
 */

const FONT = "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
const SEEN_KEY = "alphanest_splash_seen"

function bodyDark(): boolean {
    try {
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
    const holdMs = props.holdMs > 0 ? props.holdMs : 800
    const fadeMs = props.fadeMs > 0 ? props.fadeMs : 400
    const oncePerSession = props.oncePerSession !== false
    const logoSize = props.logoSize > 0 ? props.logoSize : 84
    const label = props.label || "알파네스트"
    const isCanvas = RenderTarget.current() === RenderTarget.canvas
    const [phase, setPhase] = useState<Phase>("show")

    useEffect(() => {
        if (isCanvas) return
        // 세션 1회 — 이미 봤으면 즉시 제거
        if (oncePerSession) {
            try {
                if (sessionStorage.getItem(SEEN_KEY) === "1") { setPhase("done"); return }
                sessionStorage.setItem(SEEN_KEY, "1")
            } catch (e) {}
        }
        const t1 = setTimeout(() => setPhase("fading"), holdMs)
        const t2 = setTimeout(() => setPhase("done"), holdMs + fadeMs)
        return () => { clearTimeout(t1); clearTimeout(t2) }
    }, [isCanvas, oncePerSession, holdMs, fadeMs])

    if (!isCanvas && phase === "done") return null

    const dark = isCanvas ? !!props.dark : bodyDark()
    const bg = dark ? "#0f1318" : "#f2f4f6"
    const ink = dark ? "#e3e7ec" : "#191f28"
    const opacity = phase === "fading" ? 0 : 1

    return (
        <div style={{
            position: "fixed", top: 0, left: 0, right: 0, bottom: 0, zIndex: 100000,
            background: bg, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
            gap: 18, fontFamily: FONT, opacity, transition: `opacity ${fadeMs}ms ease`,
            pointerEvents: phase === "fading" ? "none" : "auto",
        }}>
            <style>{`@keyframes _an_splash_in{0%{opacity:0;transform:scale(0.82)}55%{opacity:1}100%{opacity:1;transform:scale(1)}}`}</style>
            <div style={{ animation: isCanvas ? "none" : "_an_splash_in 0.62s cubic-bezier(.34,1.4,.5,1) both" }}>
                <AlphaLogo size={logoSize} />
            </div>
            <div style={{
                fontSize: Math.round(logoSize * 0.28), fontWeight: 800, letterSpacing: "-0.5px", color: ink,
                animation: isCanvas ? "none" : "_an_splash_in 0.62s cubic-bezier(.34,1.4,.5,1) 0.08s both",
            }}>{label}</div>
        </div>
    )
}

addPropertyControls(SplashScreen, {
    holdMs: { type: ControlType.Number, title: "유지(ms)", defaultValue: 800, min: 0, max: 4000, step: 100 },
    fadeMs: { type: ControlType.Number, title: "페이드(ms)", defaultValue: 400, min: 100, max: 1500, step: 50 },
    oncePerSession: { type: ControlType.Boolean, title: "세션 1회", defaultValue: true },
    logoSize: { type: ControlType.Number, title: "로고 크기", defaultValue: 84, min: 40, max: 200, step: 4 },
    label: { type: ControlType.String, title: "이름", defaultValue: "알파네스트" },
    dark: { type: ControlType.Boolean, title: "다크(캔버스)", defaultValue: false },
})
