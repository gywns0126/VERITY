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

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆ (Neo Dark Terminal — _shared-patterns.ts 마스터)
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D", borderHover: "#B5FF19",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF19", accentSoft: "rgba(181,255,25,0.12)",
    strongBuy: "#22C55E", buy: "#B5FF19", watch: "#FFD600", caution: "#F59E0B", avoid: "#EF4444",
    up: "#F04452", down: "#3182F6",
    info: "#5BA9FF", success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const G = {
    accent: "0 0 8px rgba(181,255,25,0.35)",
    accentSoft: "0 0 4px rgba(181,255,25,0.20)",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_tight: 1.3, lh_normal: 1.5, lh_loose: 1.7,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease", slow: "240ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */

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
                <div style={{ color: C.textTertiary, fontSize: T.body, textAlign: "center", padding: S.xxxl }}>
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
                <div style={{ color: C.textTertiary, fontSize: T.body, textAlign: "center", padding: S.xxxl }}>
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
                <span style={{ color: C.textTertiary, fontSize: T.cap }}>
                    <span style={MONO}>{recs.length}</span>{isUS ? " stocks" : "종목"}
                </span>
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
                                background: active ? C.bgElevated : "transparent",
                                borderLeft: active ? `3px solid ${C.accent}` : "3px solid transparent",
                                boxShadow: active ? G.accentSoft : "none",
                            }}
                        >
                            <div style={{ display: "flex", alignItems: "center", gap: S.sm }}>
                                <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi }}>{r.name}</span>
                                <span style={{
                                    fontSize: T.cap,
                                    fontWeight: T.w_bold,
                                    color: s.trend === "bullish" ? C.accent : s.trend === "bearish" ? C.danger : C.textSecondary,
                                }}>
                                    {s.trend === "bullish" ? "강세" : s.trend === "bearish" ? "약세" : "중립"}
                                </span>
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: S.sm }}>
                                <Bar value={s.score} />
                                <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_bold, minWidth: 28, textAlign: "right", ...MONO }}>
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
                        <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_bold }}>{sel.name} {isUS ? "Detail" : "상세"}</span>
                        <div style={{ display: "flex", gap: S.sm, marginTop: S.sm, flexWrap: "wrap" }}>
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
                            <div style={{ marginTop: S.sm }}>
                                <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_semi, fontFamily: FONT_MONO, letterSpacing: "0.05em" }}>StockTwits</span>
                                {st.top_messages.map((m: any, i: number) => (
                                    <div key={i} style={{ color: C.textSecondary, fontSize: T.cap, marginTop: 3, lineHeight: T.lh_normal }}>
                                        <span style={{ color: m.sentiment === "Bullish" ? C.accent : m.sentiment === "Bearish" ? C.danger : C.textTertiary, fontWeight: T.w_semi, fontSize: T.cap, fontFamily: FONT_MONO }}>
                                            {m.sentiment || "—"}
                                        </span>{" "}
                                        {m.text}
                                    </div>
                                ))}
                            </div>
                        )}
                        {Array.isArray(rd.top_posts) && rd.top_posts.length > 0 && (
                            <div style={{ marginTop: S.sm }}>
                                <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_semi, fontFamily: FONT_MONO, letterSpacing: "0.05em" }}>{isUS ? "Reddit Top" : "Reddit 인기글"}</span>
                                {rd.top_posts.map((p: any, i: number) => (
                                    <div key={i} style={{ color: C.textSecondary, fontSize: T.cap, marginTop: 3, lineHeight: T.lh_normal }}>
                                        r/{p.sub} · {p.title}
                                    </div>
                                ))}
                            </div>
                        )}
                        <div style={{ color: C.textTertiary, fontSize: T.cap, marginTop: S.sm, fontFamily: FONT }}>
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
    const color = pct >= 65 ? C.accent : pct <= 35 ? C.danger : C.watch
    return (
        <div style={{ width: 60, height: 6, borderRadius: R.sm, background: C.bgElevated, overflow: "hidden" }}>
            <div style={{ width: `${pct}%`, height: "100%", borderRadius: R.sm, background: color, transition: "width 0.5s ease" }} />
        </div>
    )
}

function Chip({ label, score, sub }: { label: string; score?: number; sub?: string }) {
    const v = score ?? 0
    const color = v >= 60 ? C.accent : v <= 40 ? C.danger : C.textSecondary
    return (
        <div style={{
            padding: `${S.xs}px ${S.md}px`,
            borderRadius: R.sm,
            background: C.bgElevated,
            border: `1px solid ${color}33`,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 2,
            minWidth: 60,
        }}>
            <span style={{ fontSize: T.cap, color: C.textTertiary }}>{label}</span>
            <span style={{ fontSize: T.sub, fontWeight: T.w_bold, color, ...MONO }}>{score ?? "—"}</span>
            {sub && <span style={{ fontSize: T.cap, color: C.textTertiary }}>{sub}</span>}
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

const container: CSSProperties = {
    width: "100%",
    background: C.bgElevated,
    border: `1px solid ${C.border}`,
    borderRadius: R.lg,
    padding: S.xl,
    fontFamily: FONT,
    boxSizing: "border-box",
    display: "flex",
    flexDirection: "column",
    gap: S.md,
}

const headerRow: CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
}

const titleStyle: CSSProperties = {
    color: C.textPrimary,
    fontSize: T.sub,
    fontWeight: T.w_bold,
    fontFamily: FONT,
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
    padding: `${S.sm}px ${S.md}px`,
    borderRadius: R.md,
    cursor: "pointer",
    transition: X.fast,
}

const detailWrap: CSSProperties = {
    marginTop: S.xs,
    padding: S.md,
    background: C.bgPage,
    borderRadius: R.md,
    border: `1px solid ${C.border}`,
}
