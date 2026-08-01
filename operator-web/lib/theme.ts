"use client"
// 디자인 = 공개 알파네스트 전면 참고 (PM 2026-08-01). 토큰은 자체 신설 금지 —
// 공개 컴포넌트(PublicInvestorPortfolios/PublicNPSHoldings) 캐노니컬 세트 그대로 복사.
// 🚨 숫자 = Pretendard + tabular-nums (모노 스택 금지, AlphaNest 표준). 상승=빨강/하락=파랑.
// 프레이머 67파일 readBodyDark 복붙을 단일 소스로.
import { useEffect, useState, type CSSProperties } from "react"

export const FONT =
    "Pretendard, -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', sans-serif"
// 숫자 스타일 — 모노 금지, tabular-nums.
export const NUM: CSSProperties = { fontVariantNumeric: "tabular-nums" }

const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", track: "#eef0f3", hi: "#f6f7f9",
    vt: "#6c5ce7", vtS: "#f0edff",
    up: "#f04452", down: "#3182f6", upS: "#fdecee", downS: "#eaf1fe",
    green: "#15c47e", greenS: "#eafaf3",
}
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", track: "#222a33", hi: "#1e242c",
    vt: "#a99bff", vtS: "#241f3a",
    up: "#ff6b76", down: "#5a9cff", upS: "#2a1c20", downS: "#1b2740",
    green: "#34e08a", greenS: "#12241c",
}

export type Palette = typeof LIGHT

export function palette(dark: boolean): Palette {
    return dark ? DARK : LIGHT
}

// 토스식 부드러운 카드 (radius 16, 아주 옅은 그림자) — AlphaNest 표준.
export function cardStyle(c: Palette, pad = "18px 20px"): CSSProperties {
    return {
        background: c.card,
        borderRadius: 16,
        boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
        padding: pad,
    }
}

export function readDark(): boolean {
    if (typeof document === "undefined") return false
    try {
        const attr = document.documentElement.getAttribute("data-theme")
        if (attr === "dark") return true
        if (attr === "light") return false
        const t = localStorage.getItem("verity_theme")
        if (t === "dark") return true
        if (t === "light") return false
        if (window.matchMedia) return window.matchMedia("(prefers-color-scheme: dark)").matches
    } catch {
        return false
    }
    return false
}

export function useDark(): boolean {
    const [dark, setDark] = useState(false)
    useEffect(() => {
        setDark(readDark())
        function onChange() {
            setDark(readDark())
        }
        window.addEventListener("verity-theme-changed", onChange)
        const mq = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null
        if (mq) mq.addEventListener("change", onChange)
        return () => {
            window.removeEventListener("verity-theme-changed", onChange)
            if (mq) mq.removeEventListener("change", onChange)
        }
    }, [])
    return dark
}
