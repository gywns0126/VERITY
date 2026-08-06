"use client"
// 종목 로고 = 토스 CDN + 국기 배지 (PM 2026-08-06 "미장 로고도 넣고, 국기도 알파네스트처럼").
//
// 실측(2026-08-06):
//   · 토스 CDN 은 **미국 티커도 지원** — AAPL·NVDA·PLTR·CAT·SOXL 등 16/16 = 200, BRK.B 도 200.
//     소문자는 403 → 반드시 대문자 정규화. KR = 6자리 코드 그대로.
//   · 국기 = 알파네스트 정본 문법 계승(PublicStockSearch: circle-flags CDN, 로고 우하단 원형
//     배지 + 카드색 테두리). 국적 판별 = flagFromTicker 동일 규칙(6자리 숫자 = kr).
// 실패·미지원 시 이니셜 폴백(결정적 색).
import { useState } from "react"

const PALETTE = ["#6c5ce7", "#3182f6", "#15c47e", "#f04452", "#ff9500", "#00b8d4", "#8e44ad"]
const CDN = "https://static.toss.im/png-icons/securities/icn-sec-fill-"
const FLAG_BASE = "https://hatscripts.github.io/circle-flags/flags/"   // 알파네스트와 동일 소스

/** CDN 키 — KR 6자리 숫자 그대로, US 는 대문자 티커(소문자 403). 그 외 null = 이니셜. */
function cdnKey(ticker?: string): string | null {
    const t = String(ticker || "").trim()
    if (!t) return null
    if (/^\d{6}$/.test(t)) return t                       // KR
    if (/^[A-Za-z][A-Za-z.\-]{0,6}$/.test(t)) return t.toUpperCase()  // US (BRK.B 형태 포함)
    return null
}

/** 국적 — 알파네스트 flagFromTicker 정합. */
function flagCode(ticker?: string): "kr" | "us" {
    return /^\d{6}$/.test(String(ticker || "")) ? "kr" : "us"
}

export default function StockLogo({
    ticker,
    name,
    size = 22,
    flag = true,
}: {
    ticker?: string
    name?: string
    size?: number
    flag?: boolean
}) {
    const [err, setErr] = useState(false)
    const key = cdnKey(ticker)
    const radius = Math.round(size * 0.32)

    const seed = name || String(ticker || "") || "?"
    let h = 0
    for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) | 0
    const bg = PALETTE[Math.abs(h) % PALETTE.length]
    const ch = seed.trim().charAt(0).toUpperCase() || "?"
    const fsize = Math.round(size * 0.46)

    const inner =
        key && !err ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
                src={`${CDN}${key}.png`}
                alt=""
                width={size}
                height={size}
                loading="lazy"
                decoding="async"
                onError={() => setErr(true)}
                style={{ width: size, height: size, borderRadius: radius, objectFit: "cover", display: "block", background: "rgba(128,128,128,0.08)" }}
            />
        ) : (
            <span
                style={{
                    width: size,
                    height: size,
                    borderRadius: radius,
                    background: bg,
                    color: "#fff",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: Math.round(size * 0.42),
                    fontWeight: 800,
                    lineHeight: 1,
                }}
            >
                {ch}
            </span>
        )

    // 아주 작은 아이콘(≤15px)은 국기가 뭉개지므로 생략
    if (!flag || size < 16) {
        return <span style={{ width: size, height: size, flexShrink: 0, display: "inline-block" }}>{inner}</span>
    }

    return (
        <span style={{ position: "relative", width: size, height: size, flexShrink: 0, display: "inline-block" }}>
            {inner}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
                src={`${FLAG_BASE}${flagCode(ticker)}.svg`}
                alt=""
                width={fsize}
                height={fsize}
                loading="lazy"
                decoding="async"
                style={{
                    position: "absolute",
                    right: -3,
                    bottom: -3,
                    width: fsize,
                    height: fsize,
                    borderRadius: "50%",
                    border: "1.5px solid var(--af-card, #fff)",
                    background: "var(--af-card, #fff)",
                    display: "block",
                    boxShadow: "0 1px 2px rgba(0,0,0,0.18)",
                }}
            />
        </span>
    )
}
