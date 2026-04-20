import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"

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
    accentStrong: "0 0 12px rgba(181,255,25,0.50)",
    danger: "0 0 6px rgba(239,68,68,0.30)",
}
const T = {
    cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700, w_black: 800,
    lh_tight: 1.3, lh_normal: 1.5, lh_loose: 1.7,
}
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24, xxxl: 32 }
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
const X = { fast: "120ms ease", base: "180ms ease", slow: "240ms ease" }
const FONT = "'Inter', 'Pretendard', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/** Framer 단일 코드 파일용 — 상대 경로 모듈 import 불가 → 인라인 (fetchPortfolioJson.ts와 동일 로직) */
function bustPortfolioUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

const PORTFOLIO_FETCH_INIT: RequestInit = {
    cache: "no-store",
    mode: "cors",
    credentials: "omit",
}

function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    return fetch(bustPortfolioUrl(url), { ...PORTFOLIO_FETCH_INIT, signal })
        .then((r) => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            return r.text()
        })
        .then((txt) =>
            JSON.parse(
                txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null"),
            ),
        )
}

interface Props {
    dataUrl: string
    maxNewsItems: number
    market: "kr" | "us"
}

function MiniSparkline({ data, color = "#888", width = 60, height = 18 }: { data: number[]; color?: string; width?: number; height?: number }) {
    if (!data || data.length < 2) return null
    const mn = Math.min(...data), mx = Math.max(...data), rng = mx - mn || 1
    const pts = data.map((v, i) => `${(i / (data.length - 1)) * width},${height - ((v - mn) / rng) * height}`).join(" ")
    return (
        <svg width={width} height={height} style={{ display: "block", marginTop: 4 }}>
            <polyline points={pts} fill="none" stroke={color} strokeWidth={1.2} strokeLinejoin="round" strokeLinecap="round" />
        </svg>
    )
}

export default function MacroPanel(props: Props) {
    const { dataUrl, maxNewsItems, market = "kr" } = props
    const isUS = market === "us"
    const [data, setData] = useState<any>(null)
    const [tab, setTab] = useState<"macro" | "micro" | "news">("macro")

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchPortfolioJson(dataUrl, ac.signal).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        return () => ac.abort()
    }, [dataUrl])

    const font = "'Pretendard', -apple-system, sans-serif"
    const macro = data?.macro || {}
    const mood = isUS ? (macro.market_mood_us || macro.market_mood || {}) : (macro.market_mood || {})
    const diags = isUS ? (macro.macro_diagnosis_us || macro.macro_diagnosis || []) : (macro.macro_diagnosis || [])

    // §11~§14 macro_override + secondary_signals
    const brain: any = data?.verity_brain || {}
    const macroOv: any = brain?.macro_override || data?.macro_override || {}
    const overrideMode = String(macroOv.mode || "")
    const secondarySignals: any[] = Array.isArray(macroOv.secondary_signals) ? macroOv.secondary_signals : []
    const overrideLabels: Record<string, string> = {
        panic_stage_1: "패닉 1단계", panic_stage_2: "패닉 2단계",
        panic_stage_3: "패닉 3단계 (기관 항복)", panic_stage_4: "패닉 4단계 (절망)",
        vix_spread_panic: "VIX·스프레드 패닉",
        cape_bubble: "CAPE 버블", yield_defense: "수익률 방어",
        euphoria: "유포리아", vi_cascade: "VI 연쇄",
        sector_quadrant_drift: "섹터 vs Quadrant 불일치",
        ai_upside_relax: "AI 상승 완화",
        cboe_panic: "CBOE 패닉",
    }
    const microsAll = macro.micro_signals || []
    const newsRows: any[] = (data?.bloomberg_google_headlines || []).slice(
        0,
        maxNewsItems,
    )
    const isUSItem = (x: any) =>
        x?.currency === "USD" ||
        /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(x?.market || "") ||
        /^[A-Z]{1,5}$/.test(String(x?.ticker || ""))
    const micros = microsAll
        .map((sig: any) => ({
            ...sig,
            data: Array.isArray(sig?.data)
                ? sig.data.filter((row: any) => (isUS ? isUSItem(row) : !isUSItem(row)))
                : sig?.data,
        }))
        .filter((sig: any) => !Array.isArray(sig?.data) || sig.data.length > 0)

    const chgColor = (v: number) =>
        v > 0 ? "#22C55E" : v < 0 ? "#EF4444" : "#888"
    const fmtChg = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`

    const moodGradient = (() => {
        const s = mood.score || 50
        if (s >= 70) return "linear-gradient(135deg, #064E3B, #10B981)"
        if (s >= 55) return "linear-gradient(135deg, #14532D, #22C55E)"
        if (s >= 45) return "linear-gradient(135deg, #1A1A2E, #555)"
        if (s >= 30) return "linear-gradient(135deg, #44090A, #EF4444)"
        return "linear-gradient(135deg, #7F1D1D, #DC2626)"
    })()

    const diagIcon = (type: string) => {
        if (type === "positive") return "+"
        if (type === "risk") return "!"
        if (type === "warning") return "~"
        return "·"
    }
    const diagColor = (type: string) => {
        if (type === "positive") return "#22C55E"
        if (type === "risk") return "#EF4444"
        if (type === "warning") return "#F59E0B"
        return "#888"
    }

    const globalIndices = [
        { key: "sp500", label: "S&P 500" },
        { key: "nasdaq", label: "NASDAQ" },
        { key: "dji", label: "DOW" },
        { key: "nikkei", label: "Nikkei" },
        { key: "sse", label: "Shanghai" },
        { key: "dax", label: "DAX" },
    ]

    const commodities = [
        { key: "wti_oil", label: "WTI 원유", unit: "$" },
        { key: "gold", label: "금", unit: "$" },
        { key: "copper", label: "구리", unit: "$" },
    ]

    const rates = [
        { key: "us_10y", label: "미 10Y", unit: "%" },
        { key: "us_2y", label: "미 2Y", unit: "%" },
    ]

    const currencies = isUS
        ? [
              { key: "usd_jpy", label: "USD/JPY", unit: "" },
              { key: "eur_usd", label: "EUR/USD", unit: "" },
              { key: "usd_krw", label: "USD/KRW", unit: "원" },
          ]
        : [
              { key: "usd_krw", label: "USD/KRW", unit: "원" },
              { key: "usd_jpy", label: "USD/JPY", unit: "" },
              { key: "eur_usd", label: "EUR/USD", unit: "" },
          ]

    if (!data) {
        return (
            <div style={{ ...card, minHeight: 200, alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: C.textSecondary, fontSize: 14, fontFamily: font }}>매크로 데이터 로딩 중...</span>
            </div>
        )
    }

    return (
        <div style={card}>
            {/* 시장 분위기 배너 */}
            <div style={{ ...moodBanner, background: moodGradient }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <span style={{ fontSize: 28, fontWeight: 800, color: C.textPrimary, fontFamily: font }}>
                        {mood.score || 50}
                    </span>
                    <div>
                        <div style={{ color: C.textPrimary, fontSize: 14, fontWeight: 700, fontFamily: font }}>
                            시장 분위기: {mood.label || "—"}
                        </div>
                        <div style={{ color: "rgba(255,255,255,0.7)", fontSize: 12, fontFamily: font }}>
                            {isUS
                                ? `VIX ${macro.vix?.value || "—"} | 미 10Y ${macro.us_10y?.value || "—"}% | USD/JPY ${macro.usd_jpy?.value || "—"}`
                                : `VIX ${macro.vix?.value || "—"} | 환율 ${macro.usd_krw?.value?.toLocaleString() || "—"}원`}
                            {macro.yield_spread ? ` | 금리차 ${macro.yield_spread.value}%p` : ""}
                        </div>
                    </div>
                </div>
            </div>

            {/* §11~§14 매크로 오버라이드 + secondary_signals */}
            {overrideMode && (
                <div style={{
                    padding: "10px 14px", borderBottom: `1px solid ${C.border}`,
                    background: "rgba(245,158,11,0.06)",
                    borderLeft: "3px solid #F59E0B",
                }}>
                    <div style={{ color: "#F59E0B", fontSize: 12, fontWeight: 800, fontFamily: font, marginBottom: 4 }}>
                        ⚠ 매크로 오버라이드: {overrideLabels[overrideMode] || overrideMode}
                        {macroOv.max_grade && (
                            <span style={{ color: "#FCA5A5", marginLeft: 6, fontWeight: 600 }}>
                                cap → {macroOv.max_grade}
                            </span>
                        )}
                    </div>
                    {macroOv.message && (
                        <div style={{ color: C.textPrimary, fontSize: 12, fontFamily: font, lineHeight: 1.5 }}>
                            {String(macroOv.message).slice(0, 160)}
                        </div>
                    )}
                    {secondarySignals.length > 0 && (
                        <div style={{ marginTop: 6, display: "flex", gap: 4, flexWrap: "wrap" }}>
                            <span style={{ color: C.textSecondary, fontSize: 12, fontFamily: font }}>보조:</span>
                            {secondarySignals.map((s: any, i: number) => (
                                <span key={i} style={{
                                    background: "rgba(125,211,252,0.10)", color: "#7DD3FC",
                                    fontSize: 12, fontWeight: 600, padding: "2px 6px", borderRadius: 6,
                                    border: "1px solid #7DD3FC40", fontFamily: font,
                                }} title={`${s.mode} (cap ${s.max_grade})`}>
                                    {overrideLabels[s.mode] || s.mode}
                                </span>
                            ))}
                        </div>
                    )}
                </div>
            )}

            {/* 진단 리스트 */}
            {diags.length > 0 && (
                <div style={{ padding: "12px 16px", borderBottom: `1px solid ${C.border}` }}>
                    {diags.map((d: any, i: number) => (
                        <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: i < diags.length - 1 ? 6 : 0 }}>
                            <span style={{ color: diagColor(d.type), fontWeight: 800, fontSize: 13, fontFamily: font, minWidth: 14, textAlign: "center" }}>
                                {diagIcon(d.type)}
                            </span>
                            <span style={{ color: C.textPrimary, fontSize: 12, fontFamily: font, lineHeight: "1.5" }}>
                                {d.text}
                            </span>
                        </div>
                    ))}
                </div>
            )}

            {/* 탭 */}
            <div style={{ display: "flex", gap: 0, borderBottom: `1px solid ${C.border}` }}>
                {(["macro", "micro", "news"] as const).map((t) => {
                    const labels = { macro: "거시 지표", micro: "미시 동향", news: "뉴스 피드" }
                    return (
                        <button
                            key={t}
                            onClick={() => setTab(t)}
                            style={{
                                flex: 1, padding: "10px 0", background: "none", border: "none",
                                color: tab === t ? "#B5FF19" : "#666",
                                borderBottom: tab === t ? "2px solid #B5FF19" : "2px solid transparent",
                                fontSize: 13, fontWeight: 600, fontFamily: font, cursor: "pointer",
                            }}
                        >
                            {labels[t]}
                        </button>
                    )
                })}
            </div>

            {/* 거시 탭 */}
            {tab === "macro" && (
                <div style={{ padding: "12px 16px" }}>
                    <div style={sectionTitle}>글로벌 지수</div>
                    <div style={gridRow}>
                        {globalIndices.map(({ key, label }) => {
                            const d = macro[key] || {}
                            const spark: number[] = d.sparkline_weekly || []
                            return (
                                <div key={key} style={gridCell}>
                                    <div style={cellLabel}>{label}</div>
                                    <div style={cellValue}>{d.value?.toLocaleString() || "—"}</div>
                                    <div style={{ ...cellChange, color: chgColor(d.change_pct || 0) }}>
                                        {fmtChg(d.change_pct || 0)}
                                    </div>
                                    {spark.length > 2 && <MiniSparkline data={spark.slice(-13)} color={chgColor(d.change_pct || 0)} />}
                                </div>
                            )
                        })}
                    </div>

                    <div style={sectionTitle}>원자재</div>
                    <div style={gridRow}>
                        {commodities.map(({ key, label, unit }) => {
                            const d = macro[key] || {}
                            return (
                                <div key={key} style={gridCell}>
                                    <div style={cellLabel}>{label}</div>
                                    <div style={cellValue}>{unit}{d.value?.toLocaleString() || "—"}</div>
                                    <div style={{ ...cellChange, color: chgColor(d.change_pct || 0) }}>
                                        {fmtChg(d.change_pct || 0)}
                                    </div>
                                </div>
                            )
                        })}
                    </div>

                    <div style={sectionTitle}>금리</div>
                    <div style={gridRow}>
                        {rates.map(({ key, label, unit }) => {
                            const d = macro[key] || {}
                            const fredKey = key === "us_10y" ? "dgs10" : null
                            const fredD = fredKey ? (macro.fred?.[fredKey] || {}) : {}
                            const spark: number[] = d.sparkline_weekly || fredD.sparkline || []
                            return (
                                <div key={key} style={gridCell}>
                                    <div style={cellLabel}>{label}</div>
                                    <div style={cellValue}>{d.value || "—"}{unit}</div>
                                    <div style={{ ...cellChange, color: chgColor(d.change_pct || 0) }}>
                                        {fmtChg(d.change_pct || 0)}
                                    </div>
                                    {spark.length > 2 && <MiniSparkline data={spark.slice(-13)} color="#38BDF8" />}
                                </div>
                            )
                        })}
                        {macro.yield_spread && (
                            <div style={gridCell}>
                                <div style={cellLabel}>10Y-2Y 스프레드</div>
                                <div style={cellValue}>{macro.yield_spread.value}%p</div>
                                <div style={{ ...cellChange, color: macro.yield_spread.value < 0 ? "#EF4444" : "#22C55E" }}>
                                    {macro.yield_spread.signal}
                                </div>
                            </div>
                        )}
                    </div>

                    <div style={sectionTitle}>환율</div>
                    <div style={gridRow}>
                        {currencies.map(({ key, label, unit }) => {
                            const d = macro[key] || {}
                            const spark: number[] = d.sparkline_weekly || []
                            return (
                                <div key={key} style={gridCell}>
                                    <div style={cellLabel}>{label}</div>
                                    <div style={cellValue}>{d.value?.toLocaleString() || "—"}{unit}</div>
                                    <div style={{ ...cellChange, color: chgColor(d.change_pct || 0) }}>
                                        {fmtChg(d.change_pct || 0)}
                                    </div>
                                    {spark.length > 2 && <MiniSparkline data={spark.slice(-13)} color={chgColor(d.change_pct || 0)} />}
                                </div>
                            )
                        })}
                    </div>
                </div>
            )}

            {/* 미시 탭 */}
            {tab === "micro" && (
                <div style={{ padding: "12px 16px" }}>
                    {micros.length === 0 && (
                        <div style={{ color: C.textTertiary, fontSize: 13, fontFamily: font, textAlign: "center", padding: 20 }}>
                            미시 데이터 없음
                        </div>
                    )}
                    {micros.map((sig: any, idx: number) => (
                        <div key={idx} style={{ marginBottom: 16 }}>
                            <div style={{ ...sectionTitle, color: sig.type === "hot_sector" ? C.up : C.down }}>
                                {sig.label}
                            </div>
                            {(sig.data || []).map((s: any, i: number) => (
                                <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: `1px solid ${C.border}` }}>
                                    <span style={{ color: C.textPrimary, fontSize: 13, fontFamily: font }}>{s.name}</span>
                                    <span style={{ color: chgColor(s.change_pct || 0), fontSize: 13, fontWeight: 600, fontFamily: font }}>
                                        {fmtChg(s.change_pct || 0)}
                                    </span>
                                </div>
                            ))}
                        </div>
                    ))}
                </div>
            )}

            {/* 뉴스 피드 탭 (Bloomberg / Google) */}
            {tab === "news" && (
                <div style={{ padding: "12px 16px" }}>
                    <div style={{ color: C.textTertiary, fontSize: 12, fontFamily: font, marginBottom: 10 }}>
                        Google News RSS · Bloomberg Market
                    </div>
                    {newsRows.length === 0 && (
                        <div style={{ padding: 20, textAlign: "center", color: C.textTertiary, fontSize: 13, fontFamily: font }}>
                            헤드라인 없음 (다음 파이프라인 실행 후 갱신)
                        </div>
                    )}
                    <div style={{ maxHeight: 360, overflowY: "auto" }}>
                        {newsRows.map((h: any, i: number) => (
                            <a
                                key={i}
                                href={h.link || "#"}
                                target="_blank"
                                rel="noopener noreferrer"
                                style={newsLink}
                            >
                                <span style={newsTitle}>{h.title}</span>
                                <span style={newsMeta}>
                                    {(h.source || "").slice(0, 40)}
                                    {h.time ? ` · ${h.time}` : ""}
                                </span>
                            </a>
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}

MacroPanel.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    maxNewsItems: 12,
    market: "kr",
}

addPropertyControls(MacroPanel, {
    dataUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    },
    maxNewsItems: {
        type: ControlType.Number,
        title: "최대 뉴스 수",
        defaultValue: 12,
        min: 3,
        max: 25,
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

const card: React.CSSProperties = {
    width: "100%",
    background: C.bgElevated,
    borderRadius: 16,
    border: `1px solid ${C.border}`,
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    fontFamily: "'Pretendard', -apple-system, sans-serif",
}

const moodBanner: React.CSSProperties = {
    padding: "16px 20px",
    borderBottom: `1px solid ${C.border}`,
}

const sectionTitle: React.CSSProperties = {
    color: C.textSecondary,
    fontSize: 12,
    fontWeight: 600,
    letterSpacing: 1,
    textTransform: "uppercase",
    marginBottom: 8,
    marginTop: 12,
    fontFamily: "'Pretendard', -apple-system, sans-serif",
}

const gridRow: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: 8,
}

const gridCell: React.CSSProperties = {
    background: C.bgElevated,
    borderRadius: 8,
    padding: "10px 12px",
}

const cellLabel: React.CSSProperties = {
    color: C.textSecondary,
    fontSize: 12,
    fontWeight: 500,
    marginBottom: 4,
    fontFamily: "'Pretendard', -apple-system, sans-serif",
}

const cellValue: React.CSSProperties = {
    color: C.textPrimary,
    fontSize: 14,
    fontWeight: 700,
    fontFamily: "'Pretendard', -apple-system, sans-serif",
}

const cellChange: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 600,
    marginTop: 2,
    fontFamily: "'Pretendard', -apple-system, sans-serif",
}

const newsLink: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 4,
    textDecoration: "none",
    borderBottom: `1px solid ${C.border}`,
    padding: "10px 0",
}

const newsTitle: React.CSSProperties = {
    color: "#e5e5e5",
    fontSize: 13,
    fontWeight: 600,
    lineHeight: 1.45,
    fontFamily: "'Pretendard', -apple-system, sans-serif",
}

const newsMeta: React.CSSProperties = {
    color: C.textTertiary,
    fontSize: 12,
    fontFamily: "'Pretendard', -apple-system, sans-serif",
}
