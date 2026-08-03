"use client"
// /system — 구성 · 검증 페이지 (PM 2026-08-03 "데이터가 많으면 페이지 분할").
// 터미널(/)=실시간 운용(보유·호가·주문·추천·피드) / 여기=낮은 빈도·높은 밀도(중용 목표비중 ·
// 매매기준 제어판 · 검증 trail). 문서 스크롤 페이지.
import { useEffect, useState } from "react"
import { useDark, palette, FONT } from "@/lib/theme"
import { isAuthed } from "@/lib/auth"
import { captureOAuthHash, refreshIfNeeded } from "@/lib/supabase"
import TopBar from "../components/TopBar"
import ModerationPanel from "../components/ModerationPanel"
import ControlPanel from "../components/ControlPanel"
import VerificationPanel from "../components/VerificationPanel"

export default function SystemPage() {
    const dark = useDark()
    const c = palette(dark)
    const [authed, setAuthed] = useState<boolean | null>(null)

    useEffect(() => {
        captureOAuthHash()
        if (!isAuthed()) {
            window.location.replace("/login")
            return
        }
        setAuthed(true)
        refreshIfNeeded()
        const iv = setInterval(() => refreshIfNeeded(), 60_000)
        return () => clearInterval(iv)
    }, [])

    if (authed === null) {
        return <main style={{ minHeight: "100vh", background: c.bg }} />
    }

    return (
        <main style={{ minHeight: "100vh", background: c.bg, color: c.ink, fontFamily: FONT, WebkitFontSmoothing: "antialiased" }}>
            <TopBar active="system" />
            <div style={{ maxWidth: 1560, margin: "0 auto", padding: "14px 18px 28px" }}>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))", gap: 12, alignItems: "start" }}>
                    <ModerationPanel />
                    <ControlPanel />
                    <VerificationPanel />
                </div>
            </div>
        </main>
    )
}
