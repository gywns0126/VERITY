"use client"
// ChatDock — 상담 플로팅(FAB + 창). v2 터미널: 상담은 섹션이 아니라 우하단 도크. Esc 로 닫힘.
import { useEffect, useState } from "react"
import { useDark, palette, FONT } from "@/lib/theme"
import ChatConsult from "./ChatConsult"

export default function ChatDock() {
    const dark = useDark()
    const c = palette(dark)
    const [open, setOpen] = useState(false)

    useEffect(() => {
        function onKey(e: KeyboardEvent) {
            if (e.key === "Escape") setOpen(false)
        }
        window.addEventListener("keydown", onKey)
        return () => window.removeEventListener("keydown", onKey)
    }, [])

    return (
        <>
            <button
                onClick={() => setOpen((v) => !v)}
                style={{ position: "fixed", bottom: 54, right: 20, zIndex: 60, background: c.vt, color: "#fff", border: "none", borderRadius: 999, padding: "12px 18px", fontSize: 13, fontWeight: 800, cursor: "pointer", fontFamily: FONT, boxShadow: "0 8px 24px rgba(108,92,231,0.38)" }}
            >
                상담
            </button>
            {open ? (
                <div style={{ position: "fixed", bottom: 104, right: 20, zIndex: 60, width: 380, maxWidth: "calc(100vw - 40px)", background: c.card, borderRadius: 18, boxShadow: "0 16px 48px rgba(0,0,0,0.24)", padding: 14, fontFamily: FONT }}>
                    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 8 }}>
                        <span style={{ fontSize: 13, fontWeight: 800, color: c.ink }}>상담 <span style={{ fontSize: 10, color: c.faint, fontWeight: 500 }}>Brain 그라운딩</span></span>
                        <button onClick={() => setOpen(false)} style={{ border: "none", background: c.hi, color: c.sub, borderRadius: 999, padding: "4px 10px", fontSize: 11, fontWeight: 700, cursor: "pointer", fontFamily: FONT }}>닫기</button>
                    </div>
                    <ChatConsult />
                </div>
            ) : null}
        </>
    )
}
