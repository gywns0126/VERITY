"use client"
// 다크 감지 — 프레이머 재구축의 67파일 복붙(readBodyDark) 제거, 단일 소스.
import { useEffect, useState } from "react"

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

// 오퍼레이터 팔레트 (밀도 우선, 토스식 아님). 한국 관행: 매수/상승=빨강, 하락=파랑.
export function palette(dark: boolean) {
    return {
        bg: dark ? "#0f0f14" : "#f7f7f9",
        card: dark ? "#17171c" : "#ffffff",
        fg: dark ? "#f2f2f5" : "#1a1a1e",
        sub: dark ? "#9a9aa5" : "#8a8a94",
        border: dark ? "rgba(255,255,255,0.07)" : "rgba(0,0,0,0.06)",
        buy: "#f04452",
        sell: "#3182f6",
        purple: "#6c5ce7",
    }
}
