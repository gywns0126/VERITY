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

// 라이트 = 라이브 4컴포넌트 전건 일치(검증 2026-08-01, MCP 대조). vt = 라이브 "vg"(퍼플) 동의어.
const LIGHT = {
    bg: "#f2f4f6", card: "#ffffff", ink: "#191f28", sub: "#4e5968", faint: "#8b95a1",
    line: "#e5e8eb", track: "#eef1f4", hi: "#f6f7f9",
    vt: "#6c5ce7", vtS: "#f0edff",
    up: "#f04452", down: "#3182f6", upS: "#fff0f1", downS: "#eef4ff",
    green: "#15c47e", greenS: "#eafaf3", amber: "#ff9500", amberS: "#fff6e9",
}
// 다크 up/down = 라이브 최신 PublicInvestorPortfolios 정합(2026-07-12 접근성 검증값).
//   🚨 옛 #ff6b76/#5a9cff 로 되돌리지 말 것 — down #4a90f0 은 OKLCH 다크밴드 준수 + 색약 ΔE 79.8 PASS,
//   #5b9bff/#5a9cff 는 dataviz validator FAIL. NPSHoldings/MarketBoard 는 아직 구형(라이브도 마이그레이션 중).
const DARK = {
    bg: "#0f1318", card: "#171c23", ink: "#e3e7ec", sub: "#9aa4b1", faint: "#828d9b",
    line: "#252b34", track: "#222a33", hi: "#1e242c",
    vt: "#a99bff", vtS: "#241f3a",
    up: "#f04452", down: "#4a90f0", upS: "#2a1a1d", downS: "#1b2740",
    green: "#34e08a", greenS: "#12241c", amber: "#f0a020", amberS: "#2a2013",
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
