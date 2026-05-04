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
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

function fetchJson(url: string, signal?: AbortSignal): Promise<any> {
    return fetch(bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((txt) => JSON.parse(txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
}

const font = FONT
const BG = C.bgPage
const CARD = C.bgCard
const BORDER = C.border
const MUTED = C.textSecondary
const UP = C.success
const DOWN = C.danger
const WARN = C.caution
const BLUE = "#3B82F6"
const ACCENT = C.accent
interface ETFItem {
    ticker: string
    name: string
    category: string
    close: number | null
    change_pct: number | null
    volume: number | null
    aum: number | null
    expense_ratio: number | null
    dividend_yield: number | null
    verity_etf_score: number | null
    signal: string | null
    returns: Record<string, number | null>
}

interface Props { dataUrl: string }

const SIG: Record<string, { color: string; label: string }> = {
    STRONG_BUY: { color: UP, label: "강매수" },
    BUY:        { color: BLUE, label: "매수" },
    WATCH:      { color: WARN, label: "관망" },
    CAUTION:    { color: "#F97316", label: "주의" },
    AVOID:      { color: DOWN, label: "회피" },
    UNKNOWN:    { color: MUTED, label: "—" },
}

const CAT_LABEL: Record<string, string> = {
    equity_domestic: "국내주식", equity_foreign: "해외주식",
    equity_us_large: "미대형", equity_us_tech: "미기술",
    equity_us_small: "미소형", equity_us_total: "미전체",
    equity_intl: "선진국", equity_em: "이머징",
    bond_kr: "국내채권", bond_us: "미국채권",
    bond_us_long: "미장기채", bond_us_mid: "미중기채",
    bond_us_short: "미단기채", bond_us_agg: "미종합채권",
    bond_us_total: "미전체채권", bond_us_ig: "미IG", bond_us_hy: "미HY",
    bond_us_tips: "TIPS", bond_em: "이머징채권",
    sector: "섹터", sector_financial: "금융섹터", sector_tech: "기술섹터", sector_energy: "에너지섹터",
    commodity: "원자재", commodity_gold: "금", commodity_silver: "은", commodity_oil: "원유",
    thematic: "테마", thematic_innovation: "혁신",
    dividend: "배당", leverage: "레버리지", inverse: "인버스",
}

type TabKey = "all" | "kr" | "us" | "bond"
type SortKey = "score" | "return_1y" | "change"

function ETFRow({ etf }: { etf: ETFItem }) {
    const sig = SIG[etf.signal ?? "UNKNOWN"] || SIG.UNKNOWN
    const catLabel = CAT_LABEL[etf.category] ?? etf.category
    const score = etf.verity_etf_score
    const scoreColor = score != null && score >= 60 ? UP : score != null && score >= 45 ? WARN : DOWN

    return (
        <div style={{
            display: "grid", gridTemplateColumns: "52px 1fr 50px 48px 56px",
            alignItems: "center", padding: "7px 4px", borderBottom: `1px solid ${BORDER}`, gap: 6,
        }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: "#93C5FD", fontVariantNumeric: "tabular-nums", fontFamily: font }}>{etf.ticker}</span>
            <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 12, color: "#E5E5E5", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontFamily: font }}>{etf.name}</div>
                <div style={{ fontSize: 12, color: C.textTertiary, fontFamily: font }}>{catLabel}</div>
            </div>
            <div style={{ textAlign: "center" as const }}>
                <div style={{ fontSize: 13, fontWeight: 800, fontVariantNumeric: "tabular-nums", color: scoreColor, fontFamily: font }}>
                    {score != null ? score.toFixed(0) : "—"}
                </div>
            </div>
            <span
                style={{
                    background: sig.color + "22", color: sig.color, border: `1px solid ${sig.color}44`,
                    borderRadius: 6, padding: "1px 5px", fontSize: 12, fontWeight: 700, textAlign: "center" as const, fontFamily: font,
                    cursor: etf.signal === "AVOID" ? "help" : "default",
                }}
                title={etf.signal === "AVOID" ? "AVOID = 펀더멘털/구조적 결함 — 단순 저점수 ETF 는 CAUTION 으로 표시." : undefined}
            >{sig.label}</span>
            <div style={{ textAlign: "right" as const }}>
                <span style={{
                    fontSize: 12, fontWeight: 600, fontVariantNumeric: "tabular-nums", fontFamily: font,
                    color: (etf.change_pct ?? 0) >= 0 ? UP : DOWN,
                }}>
                    {etf.change_pct != null ? `${etf.change_pct > 0 ? "+" : ""}${etf.change_pct.toFixed(2)}%` : "—"}
                </span>
            </div>
        </div>
    )
}

export default function ETFDashboard(props: Props) {
    const { dataUrl } = props
    const [etfs, setEtfs] = useState<ETFItem[]>([])
    const [loading, setLoading] = useState(true)
    const [tab, setTab] = useState<TabKey>("all")
    const [sortKey, setSortKey] = useState<SortKey>("score")

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        fetchJson(dataUrl, ac.signal).then((data) => {
            if (ac.signal.aborted) return
            const kr = data.etfs?.kr_top ?? []
            const us = data.etfs?.us_top ?? []
            const bond = data.etfs?.us_bond ?? []
            const screened = data.etfs?.overall_top20 ?? [...kr, ...us, ...bond]
            setEtfs(screened)
            setLoading(false)
        }).catch(() => { if (!ac.signal.aborted) setLoading(false) })
        return () => ac.abort()
    }, [dataUrl])

    const filtered = etfs.filter((e) => {
        if (tab === "all") return true
        if (tab === "kr") return (e.category || "").includes("domestic") || (e.category || "").includes("kr")
        if (tab === "us") return (e.category || "").includes("us") || (e.category || "").includes("foreign")
        if (tab === "bond") return (e.category || "").includes("bond")
        return true
    })

    const sorted = [...filtered].sort((a, b) => {
        if (sortKey === "score") return (b.verity_etf_score ?? 0) - (a.verity_etf_score ?? 0)
        if (sortKey === "return_1y") return (b.returns?.["1Y"] ?? -999) - (a.returns?.["1Y"] ?? -999)
        if (sortKey === "change") return (b.change_pct ?? -999) - (a.change_pct ?? -999)
        return 0
    })

    const TABS: { key: TabKey; label: string }[] = [
        { key: "all", label: "전체" }, { key: "kr", label: "국내" },
        { key: "us", label: "미국" }, { key: "bond", label: "채권형" },
    ]

    return (
        <div style={wrap}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <span style={{ fontSize: 14, fontWeight: 800, color: C.textPrimary, fontFamily: font }}>ETF 스크리닝</span>
                <span style={{ fontSize: 12, color: MUTED, fontFamily: font }}>{sorted.length}개</span>
            </div>

            <div style={{ display: "flex", gap: 3, marginBottom: 8, flexWrap: "wrap" as const }}>
                {TABS.map((t) => (
                    <button key={t.key} onClick={() => setTab(t.key)} style={{
                        padding: "3px 10px", borderRadius: 6, fontSize: 12, fontWeight: 700,
                        cursor: "pointer", border: "none", fontFamily: font,
                        background: tab === t.key ? BLUE : CARD,
                        color: tab === t.key ? "#FFF" : MUTED,
                        transition: "all 0.15s ease",
                    }}>{t.label}</button>
                ))}
                <select value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)} style={{
                    marginLeft: "auto", background: CARD, color: MUTED, border: `1px solid ${BORDER}`,
                    borderRadius: 6, padding: "2px 6px", fontSize: 12, cursor: "pointer", fontFamily: font,
                }}>
                    <option value="score">스코어순</option>
                    <option value="return_1y">1Y수익률</option>
                    <option value="change">등락률순</option>
                </select>
            </div>

            <div style={{
                display: "grid", gridTemplateColumns: "52px 1fr 50px 48px 56px",
                gap: 6, padding: "3px 4px", marginBottom: 2,
            }}>
                {["티커", "종목명", "스코어", "시그널", "등락"].map((h) => (
                    <span key={h} style={{ fontSize: 12, color: C.textTertiary, fontWeight: 700, textTransform: "uppercase" as const, fontFamily: font }}>{h}</span>
                ))}
            </div>

            {loading ? (
                <div style={{ textAlign: "center" as const, color: MUTED, padding: 28, fontSize: 12, fontFamily: font }}>로딩 중...</div>
            ) : sorted.length === 0 ? (
                <div style={{ textAlign: "center" as const, color: MUTED, padding: 28, fontSize: 12, fontFamily: font }}>해당 카테고리 데이터 없음</div>
            ) : (
                <div style={{ flex: 1, minHeight: 0, overflowY: "auto" as const }}>
                    {sorted.map((etf) => <ETFRow key={etf.ticker} etf={etf} />)}
                </div>
            )}
        </div>
    )
}

ETFDashboard.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
}

addPropertyControls(ETFDashboard, {
    dataUrl: { type: ControlType.String, title: "JSON URL", defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json" },
})

const wrap: React.CSSProperties = { width: "100%", height: "100%", boxSizing: "border-box" as const, background: BG, borderRadius: 12, padding: 14, fontFamily: font, color: "#E5E5E5", display: "flex", flexDirection: "column" as const, overflow: "hidden" }
