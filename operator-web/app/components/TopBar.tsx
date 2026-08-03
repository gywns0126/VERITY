"use client"
// TopBar — R0 커맨드 바 공용 (터미널 / 구성·검증 페이지). 브랜드 · 페이지 탭 · 전역검색(터미널만) ·
// 인증칩 · 테마. 페이지 분할 문법(PM 2026-08-03: 데이터 많으면 페이지 분할).
import { useEffect, useState } from "react"
import { useDark, palette, FONT, type Palette } from "@/lib/theme"
import { clearSession, loadSession } from "@/lib/supabase"
import StockSearch from "./StockSearch"

export default function TopBar({ active }: { active: "terminal" | "macro" | "system" }) {
    const dark = useDark()
    const c = palette(dark)
    const [who, setWho] = useState("")
    useEffect(() => {
        setWho(loadSession()?.user_email || "")
    }, [])

    function toggleTheme() {
        const root = document.documentElement
        const cur = root.getAttribute("data-theme")
        const isDark = cur ? cur === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches
        const next = isDark ? "light" : "dark"
        root.setAttribute("data-theme", next)
        try {
            localStorage.setItem("verity_theme", next)
        } catch {}
        window.dispatchEvent(new Event("verity-theme-changed"))
    }

    function logout() {
        clearSession()
        window.location.replace("/login")
    }

    const tab = (isActive: boolean) => ({
        border: "none",
        textDecoration: "none",
        background: isActive ? c.vtS : "transparent",
        color: isActive ? c.vt : c.faint,
        borderRadius: 999,
        padding: "6px 12px",
        fontSize: 11.5,
        fontWeight: 800 as const,
        fontFamily: FONT,
        whiteSpace: "nowrap" as const,
    })

    return (
        <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "9px 18px", background: c.card, boxShadow: "0 1px 3px rgba(0,0,0,0.05)", flexShrink: 0, position: "relative", zIndex: 40 }}>
            <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: "-0.02em", color: c.ink, flexShrink: 0, fontFamily: FONT }}>
                알파<span style={{ color: c.vt }}>파운더</span>
            </span>
            <nav style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                <a href="/" style={tab(active === "terminal")}>터미널</a>
                <a href="/macro" style={tab(active === "macro")}>거시</a>
                <a href="/system" style={tab(active === "system")}>구성 · 검증</a>
            </nav>
            {active === "terminal" ? (
                <div style={{ flex: 1, maxWidth: 460, minWidth: 160 }}>
                    <StockSearch floating placeholder="종목 검색 — 이름·티커 ( / )" />
                </div>
            ) : null}
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: "auto", flexShrink: 0 }}>
                <span style={{ fontSize: 11, color: c.sub, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontFamily: FONT }}>{who}</span>
                <button onClick={logout} style={chip(c)}>로그아웃</button>
                <button onClick={toggleTheme} style={chip(c)}>테마</button>
            </div>
        </div>
    )
}

function chip(c: Palette) {
    return {
        border: "none",
        background: c.hi,
        color: c.sub,
        borderRadius: 999,
        padding: "6px 12px",
        fontSize: 11,
        fontWeight: 700 as const,
        cursor: "pointer",
        fontFamily: FONT,
    }
}
