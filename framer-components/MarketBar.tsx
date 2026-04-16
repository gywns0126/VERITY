import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

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
                        <span style={{ color: isStale ? "#EF4444" : "#888", fontSize: 10, fontWeight: 600, whiteSpace: "nowrap" }}>
                            {updatedLabel}
                        </span>
                        {isStale && (
                            <span style={{ color: "#EF4444", fontSize: 9, fontWeight: 700, whiteSpace: "nowrap" }}>
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
                            <span style={{ color: "#fff", fontSize: 20, fontWeight: 900 }}>
                                ${activeData.value?.toLocaleString()}
                            </span>
                            {activeData.change_pct != null && (
                                <span style={{ color: activeData.change_pct >= 0 ? "#22C55E" : "#EF4444", fontSize: 13, fontWeight: 700 }}>
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
                            <span style={{ color: "#444", fontSize: 11 }}>차트 데이터 수집 중 (다음 전체 분석 후 표시)</span>
                        )}
                    </div>
                    <div style={chartFooter}>
                        <span style={{ color: "#444", fontSize: 10 }}>30일 추이 · 클릭하여 닫기</span>
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

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"

const container: React.CSSProperties = {
    width: "100%",
    display: "flex",
    alignItems: "center",
    gap: 16,
    padding: "10px 24px",
    background: "#000",
    fontFamily: font,
    borderBottom: "1px solid #1A1A1A",
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
    fontSize: 11,
    fontWeight: 800,
    letterSpacing: "0.03em",
}

const o2BarBg: React.CSSProperties = {
    flex: 1,
    height: 6,
    background: "#1A1A1A",
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
    fontSize: 10,
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
    color: "#555",
    fontSize: 10,
    fontWeight: 600,
}

const chipValue: React.CSSProperties = {
    color: "#ccc",
    fontSize: 12,
    fontWeight: 700,
}

const chipPct: React.CSSProperties = {
    fontSize: 11,
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
    background: "#0A0A0A",
    borderBottom: "1px solid #1A1A1A",
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
    fontSize: 9,
    color: "#555",
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
