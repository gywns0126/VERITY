import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"
import type { CSSProperties } from "react"

/** Framer 단일 파일 업로드용 — fetchPortfolioJson.ts 의존 제거 */
function bustPortfolioUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    return fetch(bustPortfolioUrl(url), {
        cache: "no-store",
        mode: "cors",
        credentials: "omit",
        signal,
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
        )
}

function _isUS(r: any): boolean {
    return r?.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(r?.market || "")
}

interface Props {
    dataUrl: string
    maxStocks: number
    market: "kr" | "us"
}

export default function SentimentPanel(props: Props) {
    const { dataUrl, maxStocks } = props
    const isUS = props.market === "us"
    const [data, setData] = useState<any>(null)
    const [selected, setSelected] = useState<string | null>(null)

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchPortfolioJson(dataUrl, ac.signal)
            .then(d => { if (!ac.signal.aborted) setData(d) })
            .catch(() => { if (!ac.signal.aborted) setData({ recommendations: [] }) })
        return () => ac.abort()
    }, [dataUrl])

    if (data === null) {
        return (
            <div style={container}>
                <div style={headerRow}>
                    <span style={titleStyle}>{isUS ? "Social Sentiment Radar" : "소셜 감성 레이더"}</span>
                </div>
                <div style={{ color: "#555", fontSize: 12, textAlign: "center", padding: 40 }}>
                    {isUS ? "Loading..." : "데이터 로딩 중..."}
                </div>
            </div>
        )
    }

    const recs: any[] = (data?.recommendations || []).filter(
        (r: any) => r.social_sentiment?.score != null && (isUS ? _isUS(r) : !_isUS(r))
    ).slice(0, maxStocks)

    if (!recs.length) {
        return (
            <div style={container}>
                <div style={headerRow}>
                    <span style={titleStyle}>{isUS ? "Social Sentiment Radar" : "소셜 감성 레이더"}</span>
                </div>
                <div style={{ color: "#555", fontSize: 12, textAlign: "center", padding: 40 }}>
                    {isUS ? "No social sentiment data. Run pipeline in full mode." : "소셜 감성 데이터가 아직 없습니다. full 모드 파이프라인 실행 후 표시됩니다."}
                </div>
            </div>
        )
    }

    const sel = selected ? recs.find((r: any) => r.ticker === selected) : null

    return (
        <div style={container}>
            <div style={headerRow}>
                <span style={titleStyle}>{isUS ? "Social Sentiment Radar" : "소셜 감성 레이더"}</span>
                <span style={{ color: "#555", fontSize: 10 }}>{recs.length}{isUS ? " stocks" : "종목"}</span>
            </div>

            <div style={listWrap}>
                {recs.map((r: any) => {
                    const s = r.social_sentiment
                    const active = selected === r.ticker
                    return (
                        <div
                            key={r.ticker}
                            onClick={() => setSelected(active ? null : r.ticker)}
                            style={{
                                ...stockRow,
                                background: active ? "#1a1a1a" : "transparent",
                                borderLeft: active ? "3px solid #B5FF19" : "3px solid transparent",
                            }}
                        >
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                <span style={{ color: "#fff", fontSize: 12, fontWeight: 600 }}>{r.name}</span>
                                <span style={{
                                    fontSize: 10,
                                    fontWeight: 700,
                                    color: s.trend === "bullish" ? "#B5FF19" : s.trend === "bearish" ? "#FF4D4D" : "#888",
                                }}>
                                    {s.trend === "bullish" ? "강세" : s.trend === "bearish" ? "약세" : "중립"}
                                </span>
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                <Bar value={s.score} />
                                <span style={{ color: "#fff", fontSize: 13, fontWeight: 700, minWidth: 28, textAlign: "right" }}>
                                    {s.score}
                                </span>
                            </div>
                        </div>
                    )
                })}
            </div>

            {sel && (() => {
                const s = sel.social_sentiment
                const n = s.news || {}
                const c = s.community || {}
                const rd = s.reddit || {}
                const st = s.stocktwits || {}
                return (
                    <div style={detailWrap}>
                        <span style={{ color: "#fff", fontSize: 13, fontWeight: 700 }}>{sel.name} {isUS ? "Detail" : "상세"}</span>
                        <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                            <Chip label={isUS ? "News" : "뉴스"} score={n.score} />
                            {!isUS && <Chip label="커뮤니티" score={c.score} sub={c.volume ? `${c.volume}건` : undefined} />}
                            <Chip label="Reddit" score={rd.score} sub={rd.volume ? `${rd.volume}건` : undefined} />
                            {isUS && st.score != null && (
                                <Chip
                                    label="StockTwits"
                                    score={st.score}
                                    sub={st.volume ? `${st.volume}msg` : undefined}
                                />
                            )}
                        </div>
                        {isUS && Array.isArray(st.top_messages) && st.top_messages.length > 0 && (
                            <div style={{ marginTop: 8 }}>
                                <span style={{ color: "#555", fontSize: 10, fontWeight: 600 }}>StockTwits</span>
                                {st.top_messages.map((m: any, i: number) => (
                                    <div key={i} style={{ color: "#888", fontSize: 10, marginTop: 3, lineHeight: 1.4 }}>
                                        <span style={{ color: m.sentiment === "Bullish" ? "#B5FF19" : m.sentiment === "Bearish" ? "#FF4D4D" : "#666", fontWeight: 600, fontSize: 9 }}>
                                            {m.sentiment || "—"}
                                        </span>{" "}
                                        {m.text}
                                    </div>
                                ))}
                            </div>
                        )}
                        {Array.isArray(rd.top_posts) && rd.top_posts.length > 0 && (
                            <div style={{ marginTop: 8 }}>
                                <span style={{ color: "#555", fontSize: 10, fontWeight: 600 }}>{isUS ? "Reddit Top" : "Reddit 인기글"}</span>
                                {rd.top_posts.map((p: any, i: number) => (
                                    <div key={i} style={{ color: "#888", fontSize: 10, marginTop: 3, lineHeight: 1.4 }}>
                                        r/{p.sub} · {p.title}
                                    </div>
                                ))}
                            </div>
                        )}
                        <div style={{ color: "#444", fontSize: 9, marginTop: 8 }}>
                            {isUS ? "Sources" : "소스"}: {(s.sources_used || []).join(", ")}
                        </div>
                    </div>
                )
            })()}
        </div>
    )
}

function Bar({ value }: { value: number }) {
    const pct = Math.max(0, Math.min(100, value))
    const color = pct >= 65 ? "#B5FF19" : pct <= 35 ? "#FF4D4D" : "#FFD600"
    return (
        <div style={{ width: 60, height: 6, borderRadius: 3, background: "#222", overflow: "hidden" }}>
            <div style={{ width: `${pct}%`, height: "100%", borderRadius: 3, background: color }} />
        </div>
    )
}

function Chip({ label, score, sub }: { label: string; score?: number; sub?: string }) {
    const v = score ?? 0
    const color = v >= 60 ? "#B5FF19" : v <= 40 ? "#FF4D4D" : "#888"
    return (
        <div style={{
            padding: "4px 10px",
            borderRadius: 6,
            background: "#1a1a1a",
            border: `1px solid ${color}33`,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 2,
            minWidth: 60,
        }}>
            <span style={{ fontSize: 9, color: "#666" }}>{label}</span>
            <span style={{ fontSize: 14, fontWeight: 700, color }}>{score ?? "—"}</span>
            {sub && <span style={{ fontSize: 8, color: "#555" }}>{sub}</span>}
        </div>
    )
}

const DATA_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"

SentimentPanel.defaultProps = {
    dataUrl: DATA_URL,
    maxStocks: 15,
    market: "kr",
}

addPropertyControls(SentimentPanel, {
    dataUrl: {
        type: ControlType.String,
        title: "데이터 URL",
        defaultValue: DATA_URL,
    },
    maxStocks: {
        type: ControlType.Number,
        title: "최대 종목 수",
        defaultValue: 15,
        min: 5,
        max: 30,
        step: 1,
    },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["KR 국장", "US 미장"],
        defaultValue: "kr",
    },
})

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"

const container: CSSProperties = {
    width: "100%",
    background: "#111",
    border: "1px solid #222",
    borderRadius: 16,
    padding: 16,
    fontFamily: font,
    boxSizing: "border-box",
    display: "flex",
    flexDirection: "column",
    gap: 12,
}

const headerRow: CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
}

const titleStyle: CSSProperties = {
    color: "#fff",
    fontSize: 14,
    fontWeight: 700,
    fontFamily: font,
}

const listWrap: CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 2,
}

const stockRow: CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "8px 10px",
    borderRadius: 8,
    cursor: "pointer",
    transition: "background 0.15s",
}

const detailWrap: CSSProperties = {
    marginTop: 4,
    padding: 12,
    background: "#0a0a0a",
    borderRadius: 10,
    border: "1px solid #222",
}
