"use client"
// NewsTicker — 주식·거시 관련 뉴스만 도는 회전 티커 (PM 2026-08-03 "임베드보다 골라 나오는 티커").
// 소스 = 이미 금융 필터로 수집되는 자기 헤드라인(국내 40 + 월가 15, portfolio_full) — 신규 수집 0.
// 7초 자동 회전 + 클릭 = 원문 새 탭. 정지/재생 없이 담백하게 한 줄.
import { useEffect, useState } from "react"
import { useDark, palette, FONT, NUM } from "@/lib/theme"

export type NewsItem = { tag: string; title: string; link?: string }

const ROTATE_MS = 7000

export default function NewsTicker({ items }: { items: NewsItem[] }) {
    const dark = useDark()
    const c = palette(dark)
    const [i, setI] = useState(0)
    const n = items.length

    useEffect(() => {
        if (n < 2) return
        const t = setInterval(() => setI((v) => (v + 1) % n), ROTATE_MS)
        return () => clearInterval(t)
    }, [n])

    if (n === 0) return null
    const it = items[i % n]
    const tagCol = it.tag === "월가" ? c.down : c.vt
    const tagBg = it.tag === "월가" ? c.downS : c.vtS

    return (
        <div
            onClick={() => {
                if (it.link) window.open(it.link, "_blank", "noopener")
            }}
            style={{ display: "flex", alignItems: "center", gap: 9, background: c.card, borderRadius: 12, boxShadow: "0 1px 3px rgba(0,0,0,0.05)", padding: "8px 14px", marginBottom: 12, cursor: it.link ? "pointer" : "default", fontFamily: FONT, minWidth: 0 }}
        >
            <span style={{ fontSize: 10, fontWeight: 800, color: c.up, flexShrink: 0 }}>뉴스</span>
            <span style={{ fontSize: 9.5, fontWeight: 800, color: tagCol, background: tagBg, borderRadius: 6, padding: "2px 7px", flexShrink: 0 }}>{it.tag}</span>
            <span key={i} className="af-newsfade" style={{ fontSize: 12.5, fontWeight: 600, color: c.ink, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flex: 1 }}>
                {it.title}
            </span>
            <span style={{ fontSize: 9.5, color: c.faint, flexShrink: 0, ...NUM }}>{(i % n) + 1}/{n}</span>
        </div>
    )
}
