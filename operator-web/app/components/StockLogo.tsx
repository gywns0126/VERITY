"use client"
// 종목 로고 = 토스 CDN (PM 확정 "로고는 토스 사용" · project_logo_toss_lane 정합).
// KR 6자리만 CDN 제공 — US/로드 실패 = 이니셜 폴백(결정적 색). 전 종목 행 부착 (PM 결함 #1).
import { useState } from "react"

const PALETTE = ["#6c5ce7", "#3182f6", "#15c47e", "#f04452", "#ff9500", "#00b8d4", "#8e44ad"]

export default function StockLogo({ ticker, name, size = 22 }: { ticker?: string; name?: string; size?: number }) {
    const [err, setErr] = useState(false)
    const t = String(ticker || "").trim()
    const isKR = /^\d{6}$/.test(t)

    if (isKR && !err) {
        return (
            // eslint-disable-next-line @next/next/no-img-element
            <img
                src={`https://static.toss.im/png-icons/securities/icn-sec-fill-${t}.png`}
                alt=""
                width={size}
                height={size}
                loading="lazy"
                onError={() => setErr(true)}
                style={{ width: size, height: size, borderRadius: "36%", flexShrink: 0, display: "block", background: "rgba(128,128,128,0.08)" }}
            />
        )
    }

    const seed = name || t || "?"
    let h = 0
    for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) | 0
    const bg = PALETTE[Math.abs(h) % PALETTE.length]
    const ch = seed.trim().charAt(0).toUpperCase() || "?"
    return (
        <span
            style={{
                width: size,
                height: size,
                borderRadius: "36%",
                flexShrink: 0,
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                background: bg,
                color: "#fff",
                fontSize: Math.round(size * 0.5),
                fontWeight: 800,
                lineHeight: 1,
            }}
        >
            {ch}
        </span>
    )
}
