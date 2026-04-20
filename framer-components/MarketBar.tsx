import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

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


/** Framer 단일 코드 파일만 붙여 넣을 때를 위해 인라인 (fetchPortfolioJson.ts와 동일 로직 — 수정 시 맞춰 주세요) */
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
        fetch(bustPortfolioUrl(url), { ...PORTFOLIO_FETCH_INIT, signal: ac.signal })
            .then((r) => {
                if (!r.ok) throw new Error(`HTTP ${r.status}`)
                return r.text()
            })
            .then((txt) =>
                JSON.parse(
                    txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null"),
                ),
            ),
        PORTFOLIO_FETCH_TIMEOUT_MS,
        ac,
    )
}

type IndexFocus = "kr" | "us"

interface Props {
    dataUrl: string
    /** portfolio.json 재요청 간격(초). 최소 30. Framer에서 생략 시 defaultProps 사용 */
    refreshIntervalSec?: number
    /** 국장용: KOSPI·KOSDAQ 먼저 / 미장용: NDX·S&P500 먼저 */
    indexFocus?: IndexFocus
    market?: "kr" | "us"
}

const O2_LEVELS: { min: number; label: string; color: string; bg: string; msg: string }[] = [
    { min: 70, label: "HIGH", color: "#B5FF19", bg: "rgba(181,255,25,0.08)", msg: "시장 산소 충분 — 적극적 진입 가능" },
    { min: 55, label: "NORMAL", color: "#22C55E", bg: "rgba(34,197,94,0.06)", msg: "시장 안정권 — 기존 전략 유지" },
    { min: 40, label: "LOW", color: "#EAB308", bg: "rgba(234,179,8,0.06)", msg: "산소 부족 주의 — 신규 진입 보수적" },
    { min: 25, label: "HYPOXIA", color: "#F97316", bg: "rgba(249,115,22,0.06)", msg: "경고 — 현금 비중 확대 권고" },
    { min: 0, label: "CRITICAL", color: "#EF4444", bg: "rgba(239,68,68,0.08)", msg: "산소 고갈 — 신규 매수 금지" },
]

function getO2(score: number) {
    return O2_LEVELS.find((l) => score >= l.min) || O2_LEVELS[O2_LEVELS.length - 1]
}

function MiniChart({ data, width = 120, height = 40, color = "#B5FF19" }: { data: number[]; width?: number; height?: number; color?: string }) {
    if (!data || data.length < 2) return null
    const min = Math.min(...data)
    const max = Math.max(...data)
    const range = max - min || 1
    const points = data.map((v, i) => `${(i / (data.length - 1)) * width},${height - ((v - min) / range) * (height - 4) - 2}`).join(" ")
    const areaPoints = points + ` ${width},${height} 0,${height}`
    return (
        <svg width={width} height={height} style={{ display: "block" }}>
            <defs>
                <linearGradient id={`grad-${color.replace("#", "")}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={color} stopOpacity={0.2} />
                    <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
            </defs>
            <polygon points={areaPoints} fill={`url(#grad-${color.replace("#", "")})`} />
            <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
        </svg>
    )
}

export default function MarketBar(props: Props) {
    const { dataUrl, refreshIntervalSec = 180, indexFocus: _indexFocus, market = "kr" } = props
    const indexFocus = market || _indexFocus || "kr"
    const [data, setData] = useState<any>(null)
    const [expanded, setExpanded] = useState<"gold" | "silver" | null>(null)

    useEffect(() => {
        if (!dataUrl || typeof globalThis.setInterval !== "function") return
        const ac = new AbortController()
        const doLoad = () => fetchPortfolioJson(dataUrl, ac.signal).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        doLoad()
        const sec = Math.max(30, Number(refreshIntervalSec) || 180)
        const id = globalThis.setInterval(doLoad, sec * 1000)
        return () => { ac.abort(); globalThis.clearInterval(id) }
    }, [dataUrl, refreshIntervalSec])

    const marketSummary = data?.market_summary || {}
    const macro = data?.macro || {}
    const mood = macro.market_mood || {}
    const kospi = marketSummary.kospi || {}
    const kosdaq = marketSummary.kosdaq || {}
    const ndx = marketSummary.ndx || {}
    const sp500 = marketSummary.sp500 || {}
    const score = mood.score ?? 50
    const o2 = getO2(score)

    const gold = macro.gold || {}
    const silver = macro.silver || {}

    const updatedAt = data?.updated_at ? new Date(data.updated_at) : null
    const dataAgeH = updatedAt ? (Date.now() - updatedAt.getTime()) / 3600000 : 0
    const isStale = dataAgeH > 24
    const updatedLabel = updatedAt
        ? `${updatedAt.toLocaleString("ko-KR", {
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
          })} 기준`
        : "데이터 대기 중"

    const toggleExpand = (type: "gold" | "silver") => {
        setExpanded(expanded === type ? null : type)
    }

    const activeData = expanded === "gold" ? gold : expanded === "silver" ? silver : null
    const activeLabel = expanded === "gold" ? "금 (Gold)" : "은 (Silver)"
    const activeColor = expanded === "gold" ? "#FFD700" : "#C0C0C0"

    return (
        <div style={{ width: "100%", fontFamily: font }}>
            <div style={container}>
                <div style={leftSection}>
                    <div style={{ ...o2Badge, background: o2.bg, borderColor: o2.color }}>
                        <div style={o2Inner}>
                            <span style={{ ...o2Label, color: o2.color }}>O₂</span>
                            <div style={o2BarBg}>
                                <div style={{
                                    ...o2BarFill,
                                    width: `${score}%`,
                                    background: `linear-gradient(90deg, ${o2.color}88, ${o2.color})`,
                                    boxShadow: `0 0 8px ${o2.color}40`,
                                }} />
                            </div>
                            <span style={{ ...o2Score, color: o2.color }}>{score}</span>
                        </div>
                        <span style={{ ...o2Msg, color: o2.color }}>{o2.msg}</span>
                    </div>
                </div>

                {/* 지수 + 원자재 */}
                <div style={centerSection}>
                    {indexFocus === "us" ? (
                        <>
                            <IndexChip label="NDX" value={ndx.value} pct={ndx.change_pct} />
                            <IndexChip label="S&P500" value={sp500.value} pct={sp500.change_pct} />
                            <IndexChip label="KOSPI" value={kospi.value} pct={kospi.change_pct} />
                            <IndexChip label="KOSDAQ" value={kosdaq.value} pct={kosdaq.change_pct} />
                        </>
                    ) : (
                        <>
                            <IndexChip label="KOSPI" value={kospi.value} pct={kospi.change_pct} />
                            <IndexChip label="KOSDAQ" value={kosdaq.value} pct={kosdaq.change_pct} />
                            <IndexChip label="NDX" value={ndx.value} pct={ndx.change_pct} />
                            <IndexChip label="S&P500" value={sp500.value} pct={sp500.change_pct} />
                        </>
                    )}
                    <IndexChip label="USD/KRW" value={macro.usd_krw?.value} pct={null} />
                    <IndexChip label="VIX" value={macro.vix?.value}
                        pct={null}
                        color={(macro.vix?.value || 0) > 25 ? "#EF4444" : (macro.vix?.value || 0) < 18 ? "#22C55E" : "#EAB308"} />

                    <div style={dividerLine} />

                    {/* 금 */}
                    <div
                        onClick={() => toggleExpand("gold")}
                        style={{
                            ...commodityChip,
                            background: expanded === "gold" ? "rgba(255,215,0,0.08)" : "transparent",
                            borderColor: expanded === "gold" ? "#FFD700" : "transparent",
                        }}
                    >
                        <span style={{ ...chipLabel, color: "#FFD700" }}>GOLD</span>
                        <span style={chipValue}>${gold.value?.toLocaleString() || "—"}</span>
                        {gold.change_pct != null && (
                            <span style={{ ...chipPct, color: gold.change_pct >= 0 ? "#FFD700" : "#FF4D4D" }}>
                                {gold.change_pct >= 0 ? "+" : ""}{gold.change_pct?.toFixed(2)}%
                            </span>
                        )}
                    </div>

                    {/* 은 */}
                    <div
                        onClick={() => toggleExpand("silver")}
                        style={{
                            ...commodityChip,
                            background: expanded === "silver" ? "rgba(192,192,192,0.08)" : "transparent",
                            borderColor: expanded === "silver" ? "#C0C0C0" : "transparent",
                        }}
                    >
                        <span style={{ ...chipLabel, color: "#C0C0C0" }}>SILVER</span>
                        <span style={chipValue}>${silver.value?.toLocaleString() || "—"}</span>
                        {silver.change_pct != null && (
                            <span style={{ ...chipPct, color: silver.change_pct >= 0 ? "#C0C0C0" : "#FF4D4D" }}>
                                {silver.change_pct >= 0 ? "+" : ""}{silver.change_pct?.toFixed(2)}%
                            </span>
                        )}
                    </div>
                </div>

                <div style={rightMeta}>
                    <span style={{
                        ...updatedBadge,
                        background: isStale ? "rgba(239,68,68,0.10)" : "rgba(181,255,25,0.06)",
                        borderColor: isStale ? "#EF4444" : "#222",
                    }}>
                        <span style={{
                            width: 6, height: 6, borderRadius: "50%",
                            background: isStale ? "#EF4444" : "#B5FF19",
                            display: "inline-block",
                            flexShrink: 0,
                        }} />
                        <span style={{ color: isStale ? "#EF4444" : "#888", fontSize: 12, fontWeight: 600, whiteSpace: "nowrap" }}>
                            {updatedLabel}
                        </span>
                        {isStale && (
                            <span style={{ color: "#EF4444", fontSize: 12, fontWeight: 700, whiteSpace: "nowrap" }}>
                                ({Math.floor(dataAgeH)}h 경과)
                            </span>
                        )}
                    </span>
                </div>
            </div>

            {/* 확장 차트 패널 */}
            {expanded && activeData && (
                <div style={chartPanel}>
                    <div style={chartHeader}>
                        <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                            <span style={{ color: activeColor, fontSize: 14, fontWeight: 800 }}>{activeLabel}</span>
                            <span style={{ color: C.textPrimary, fontSize: 20, fontWeight: 900 }}>
                                ${activeData.value?.toLocaleString()}
                            </span>
                            {activeData.change_pct != null && (
                                <span style={{ color: activeData.change_pct >= 0 ? C.up : C.down, fontSize: 13, fontWeight: 700 }}>
                                    {activeData.change_pct >= 0 ? "▲" : "▼"} {Math.abs(activeData.change_pct)}%
                                </span>
                            )}
                        </div>
                        <div style={{ display: "flex", gap: 16 }}>
                            <div style={rangeItem}>
                                <span style={rangeLabel}>30일 최고</span>
                                <span style={{ ...rangeValue, color: "#22C55E" }}>${activeData.high_30d?.toLocaleString() || "—"}</span>
                            </div>
                            <div style={rangeItem}>
                                <span style={rangeLabel}>30일 최저</span>
                                <span style={{ ...rangeValue, color: "#EF4444" }}>${activeData.low_30d?.toLocaleString() || "—"}</span>
                            </div>
                        </div>
                    </div>
                    <div style={chartBody}>
                        {activeData.sparkline?.length > 2 ? (
                            <MiniChart data={activeData.sparkline} width={500} height={80} color={activeColor} />
                        ) : (
                            <span style={{ color: C.textTertiary, fontSize: 12 }}>차트 데이터 수집 중 (다음 전체 분석 후 표시)</span>
                        )}
                    </div>
                    <div style={chartFooter}>
                        <span style={{ color: C.textTertiary, fontSize: 12 }}>30일 추이 · 클릭하여 닫기</span>
                    </div>
                </div>
            )}
        </div>
    )
}

function IndexChip({ label, value, pct, color }: { label: string; value?: number; pct?: number | null; color?: string }) {
    const pctColor = color || ((pct || 0) >= 0 ? "#B5FF19" : "#FF4D4D")
    return (
        <div style={chipWrap}>
            <span style={chipLabel}>{label}</span>
            <span style={chipValue}>{value != null ? (value >= 100 ? value.toLocaleString(undefined, { maximumFractionDigits: 0 }) : value.toFixed(1)) : "—"}</span>
            {pct != null && (
                <span style={{ ...chipPct, color: pctColor }}>
                    {pct >= 0 ? "+" : ""}{pct?.toFixed(2)}%
                </span>
            )}
        </div>
    )
}

MarketBar.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    refreshIntervalSec: 180,
    indexFocus: "kr",
    market: "kr",
}

addPropertyControls(MarketBar, {
    dataUrl: { type: ControlType.String, title: "JSON URL", defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json" },
    market: {
        type: ControlType.Enum,
        title: "Market",
        options: ["kr", "us"],
        optionTitles: ["국장 (KR)", "미장 (US)"],
        defaultValue: "kr",
    },
    indexFocus: {
        type: ControlType.Enum,
        title: "지수 순서 (레거시)",
        options: ["kr", "us"],
        optionTitles: ["국장용 (KOSPI·KOSDAQ 먼저)", "미장용 (NDX·S&P500 먼저)"],
        defaultValue: "kr",
        hidden: () => true,
    },
    refreshIntervalSec: {
        type: ControlType.Number,
        title: "갱신 간격(초)",
        defaultValue: 180,
        min: 30,
        max: 3600,
        step: 30,
    },
})

const font = FONT

const container: React.CSSProperties = {
    width: "100%",
    display: "flex",
    alignItems: "center",
    gap: 16,
    padding: "10px 24px",
    background: C.bgPage,
    fontFamily: font,
    borderBottom: `1px solid ${C.border}`,
}

const leftSection: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 16,
    flexShrink: 0,
}

const o2Badge: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 2,
    padding: "6px 12px",
    borderRadius: 10,
    border: "1px solid",
    minWidth: 180,
}

const o2Inner: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 8,
}

const o2Label: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 800,
    letterSpacing: "0.03em",
}

const o2BarBg: React.CSSProperties = {
    flex: 1,
    height: 6,
    background: C.bgElevated,
    borderRadius: 3,
    overflow: "hidden",
}

const o2BarFill: React.CSSProperties = {
    height: "100%",
    borderRadius: 3,
    transition: "width 0.8s ease",
}

const o2Score: React.CSSProperties = {
    fontSize: 13,
    fontWeight: 900,
    minWidth: 24,
    textAlign: "right",
}

const o2Msg: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 500,
    opacity: 0.8,
    whiteSpace: "nowrap",
}

const centerSection: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 12,
    flex: 1,
    justifyContent: "center",
    flexWrap: "wrap",
}

const dividerLine: React.CSSProperties = {
    width: 1,
    height: 20,
    background: "#222",
    flexShrink: 0,
}

const chipWrap: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 6,
}

const commodityChip: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "4px 8px",
    borderRadius: 8,
    border: "1px solid",
    cursor: "pointer",
    transition: "all 0.2s",
}

const chipLabel: React.CSSProperties = {
    color: C.textTertiary,
    fontSize: 12,
    fontWeight: 600,
}

const chipValue: React.CSSProperties = {
    color: C.textPrimary,
    fontSize: 12,
    fontWeight: 700,
}

const chipPct: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 600,
}

const rightMeta: React.CSSProperties = {
    marginLeft: "auto",
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexShrink: 0,
}

const updatedBadge: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "4px 10px",
    borderRadius: 8,
    border: "1px solid",
}

const chartPanel: React.CSSProperties = {
    background: C.bgPage,
    borderBottom: `1px solid ${C.border}`,
    padding: "12px 24px",
}

const chartHeader: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
}

const rangeItem: React.CSSProperties = {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 2,
}

const rangeLabel: React.CSSProperties = {
    fontSize: 12,
    color: C.textTertiary,
    fontWeight: 600,
}

const rangeValue: React.CSSProperties = {
    fontSize: 12,
    fontWeight: 700,
}

const chartBody: React.CSSProperties = {
    display: "flex",
    justifyContent: "center",
    padding: "4px 0",
    overflow: "hidden",
}

const chartFooter: React.CSSProperties = {
    textAlign: "center",
    paddingTop: 4,
}
