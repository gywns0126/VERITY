import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"

/** Framer 단일 코드 파일 — 상대 경로 모듈 import 불가 → 인라인 (fetchPortfolioJson.ts와 동일 로직) */
function bustPortfolioUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

// WARN-24: 15초 timeout + AbortController — 네트워크 hang 방지
const PORTFOLIO_FETCH_TIMEOUT_MS = 15_000

function _withTimeout<T>(p: Promise<T>, ms: number, ac: AbortController): Promise<T> {
    const timer = setTimeout(() => ac.abort(), ms)
    return p.finally(() => clearTimeout(timer))
}

function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    const ac = new AbortController()
    if (signal) {
        if (signal.aborted) ac.abort()
        else signal.addEventListener("abort", () => ac.abort(), { once: true })
    }
    return _withTimeout(
        fetch(bustPortfolioUrl(url), {
            cache: "no-store",
            mode: "cors",
            credentials: "omit",
            signal: ac.signal,
        })
            .then((r) => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`)
                return r.text()
            })
            .then((txt) =>
                JSON.parse(
                    txt
                        .replace(/\bNaN\b/g, "null")
                        .replace(/\bInfinity\b/g, "null")
                        .replace(/-null/g, "null"),
                ),
            ),
        PORTFOLIO_FETCH_TIMEOUT_MS,
        ac,
    )
}

// WARN-23: 뉴스 수집 시각(updated_at) 기준 stale 경고 정보 (Framer 단일 파일 인라인)
function stalenessInfo(updatedAt: any): { label: string; color: string; stale: boolean } {
    if (!updatedAt) return { label: "", color: "#666", stale: false }
    const t = new Date(String(updatedAt)).getTime()
    if (!Number.isFinite(t)) return { label: "", color: "#666", stale: false }
    const hours = (Date.now() - t) / 3_600_000
    if (hours < 1) return { label: `방금 갱신 (${Math.round(hours * 60)}분 전)`, color: "#22C55E", stale: false }
    if (hours < 3) return { label: `${Math.round(hours)}시간 전`, color: "#B5FF19", stale: false }
    if (hours < 12) return { label: `${Math.round(hours)}시간 전`, color: "#FFD600", stale: false }
    if (hours < 24) return { label: `${Math.round(hours)}시간 전 (⚠️ stale 경계)`, color: "#F59E0B", stale: true }
    const days = hours / 24
    return { label: `${days.toFixed(1)}일 전 (⚠️ stale)`, color: "#FF4D4D", stale: true }
}

interface Props {
    dataUrl: string
    maxItems: number
    market: "kr" | "us"
}

export default function NewsHeadline(props: Props) {
    const { dataUrl, maxItems, market = "kr" } = props
    const [data, setData] = useState<any>(null)
    const [filter, setFilter] = useState<"all" | "positive" | "negative">("all")

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchPortfolioJson(dataUrl, ac.signal).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    const font = "'Pretendard', -apple-system, sans-serif"
    const allHeadlines: any[] = data?.headlines || []
    const usHeadlines: any[] = data?.us_headlines || []
    const headlines = market === "us"
        ? (usHeadlines.length > 0
            ? usHeadlines
            : allHeadlines.filter((h: any) => /us|global|미국|미장|나스닥|nasdaq|nyse|s&p|월가|연준|fed|테슬라|엔비디아|서학개미/i.test(
                (h.title || "") + (h.category || "") + (h.region || "")
            )))
        : allHeadlines

    const filtered = headlines.filter((h) => {
        if (filter === "all") return true
        return h.sentiment === filter
    }).slice(0, maxItems)

    const sentimentBadge = (s: string) => {
        if (s === "positive") return { text: "호재", bg: "rgba(34,197,94,0.15)", color: "#22C55E" }
        if (s === "negative") return { text: "악재", bg: "rgba(239,68,68,0.15)", color: "#EF4444" }
        return { text: "중립", bg: "rgba(136,136,136,0.12)", color: "#888" }
    }

    const posCount = headlines.filter((h) => h.sentiment === "positive").length
    const negCount = headlines.filter((h) => h.sentiment === "negative").length

    if (!data) {
        return (
            <div style={{ ...card, minHeight: 160, alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: "#999", fontSize: 14, fontFamily: font }}>뉴스 로딩 중...</span>
            </div>
        )
    }

    return (
        <div style={card}>
            {/* 헤더 */}
            <div style={header}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" as const }}>
                    <span style={{ color: "#fff", fontSize: 15, fontWeight: 700, fontFamily: font }}>
                        시장 헤드라인
                    </span>
                    <span style={{ color: "#22C55E", fontSize: 12, fontWeight: 600, fontFamily: font }}>
                        호재 {posCount}
                    </span>
                    <span style={{ color: "#EF4444", fontSize: 12, fontWeight: 600, fontFamily: font }}>
                        악재 {negCount}
                    </span>
                    {(() => {
                        // WARN-23: 뉴스 수집 시각 freshness 배지
                        const s = stalenessInfo(data?.updated_at)
                        if (!s.label) return null
                        return (
                            <span style={{ color: s.color, fontSize: 10, fontWeight: s.stale ? 800 : 500, fontFamily: font, padding: "2px 7px", borderRadius: 999, background: s.stale ? "rgba(255,77,77,0.10)" : "transparent" }}>
                                수집 {s.label}
                            </span>
                        )
                    })()}
                </div>
                <div style={{ display: "flex", gap: 4 }}>
                    {(["all", "positive", "negative"] as const).map((f) => (
                        <button
                            key={f}
                            onClick={() => setFilter(f)}
                            style={{
                                padding: "4px 10px",
                                borderRadius: 6,
                                border: "none",
                                background: filter === f ? "#B5FF19" : "#222",
                                color: filter === f ? "#000" : "#888",
                                fontSize: 11,
                                fontWeight: 600,
                                fontFamily: font,
                                cursor: "pointer",
                            }}
                        >
                            {f === "all" ? "전체" : f === "positive" ? "호재" : "악재"}
                        </button>
                    ))}
                </div>
            </div>

            {/* 뉴스 목록 */}
            <div style={{ maxHeight: 400, overflowY: "auto" }}>
                {filtered.length === 0 && (
                    <div style={{ padding: 20, textAlign: "center", color: "#666", fontSize: 13, fontFamily: font }}>
                        해당 뉴스 없음
                    </div>
                )}
                {filtered.map((h: any, i: number) => {
                    const badge = sentimentBadge(h.sentiment)
                    return (
                        <a
                            key={i}
                            href={h.link || "#"}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ ...newsRow, textDecoration: "none" }}
                        >
                            <div style={{ display: "flex", alignItems: "flex-start", gap: 10, flex: 1 }}>
                                <span
                                    style={{
                                        padding: "2px 7px",
                                        borderRadius: 4,
                                        background: badge.bg,
                                        color: badge.color,
                                        fontSize: 10,
                                        fontWeight: 700,
                                        fontFamily: font,
                                        whiteSpace: "nowrap",
                                        marginTop: 2,
                                    }}
                                >
                                    {badge.text}
                                </span>
                                <div style={{ flex: 1 }}>
                                    <div style={{ color: "#ddd", fontSize: 13, fontWeight: 500, fontFamily: font, lineHeight: "1.5" }}>
                                        {h.title}
                                    </div>
                                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 3, flexWrap: "wrap" as const }}>
                                        <span style={{ color: "#666", fontSize: 10, fontFamily: font }}>
                                            {h.source}{h.time ? ` · ${h.time}` : ""}
                                        </span>
                                        {h.category && (
                                            <span style={{ padding: "1px 5px", borderRadius: 3, background: "rgba(181,255,25,0.08)", color: "#B5FF19", fontSize: 9, fontWeight: 600, fontFamily: font }}>{h.category}</span>
                                        )}
                                        {typeof h.urgency === "number" && h.urgency >= 4 && (
                                            <span style={{ padding: "1px 5px", borderRadius: 3, background: "rgba(239,68,68,0.12)", color: "#F87171", fontSize: 9, fontWeight: 700, fontFamily: font }}>긴급</span>
                                        )}
                                        {typeof h.credibility === "number" && h.credibility >= 80 && (
                                            <span style={{ padding: "1px 5px", borderRadius: 3, background: "rgba(96,165,250,0.1)", color: "#60A5FA", fontSize: 9, fontWeight: 600, fontFamily: font }}>신뢰↑</span>
                                        )}
                                    </div>
                                </div>
                            </div>
                            <span style={{ color: "#444", fontSize: 14, marginLeft: 8 }}>›</span>
                        </a>
                    )
                })}
            </div>
        </div>
    )
}

NewsHeadline.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    maxItems: 15,
    market: "kr",
}

addPropertyControls(NewsHeadline, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    },
    maxItems: {
        type: ControlType.Number,
        title: "표시 개수",
        defaultValue: 15,
        min: 5,
        max: 30,
    },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["국장 (KR)", "미장 (US)"],
        defaultValue: "kr",
    },
})

const card: React.CSSProperties = {
    width: "100%",
    background: "#111",
    borderRadius: 16,
    border: "1px solid #222",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    fontFamily: "'Pretendard', -apple-system, sans-serif",
}

const header: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "14px 16px",
    borderBottom: "1px solid #222",
}

const newsRow: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "12px 16px",
    borderBottom: "1px solid #1a1a1a",
    transition: "background 0.15s",
    cursor: "pointer",
}
