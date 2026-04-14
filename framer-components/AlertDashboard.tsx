import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"
import type { CSSProperties } from "react"

/** Framer 단일 파일 붙여넣기용 — fetchPortfolioJson.ts와 동일 로직 */
function bustPortfolioUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

function fetchPortfolioJson(url: string): Promise<any> {
    return fetch(bustPortfolioUrl(url), { cache: "no-store", mode: "cors", credentials: "omit" })
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
    maxAlerts: number
    market: "kr" | "us"
}

type AlertLevel = "CRITICAL" | "WARNING" | "INFO"
type FilterType = "all" | AlertLevel

const LEVEL_META: Record<AlertLevel, { color: string; bg: string; icon: string; label: string }> = {
    CRITICAL: { color: "#FF4D4D", bg: "#FF4D4D15", icon: "🚨", label: "긴급" },
    WARNING: { color: "#FFD600", bg: "#FFD60015", icon: "⚠️", label: "주의" },
    INFO: { color: "#60A5FA", bg: "#60A5FA15", icon: "ℹ️", label: "참고" },
}

const CAT_LABELS: Record<string, string> = {
    macro: "매크로",
    holding: "보유",
    earnings: "실적",
    opportunity: "기회",
    news: "뉴스",
    event: "이벤트",
    strategy: "전략",
    ai_consensus: "AI합의",
}

const US_ALERT_KW = ["미국", "연준", "Fed", "NASDAQ", "NYSE", "S&P", "다우", "국채", "VIX", "달러"]
const KR_ALERT_KW = ["한국", "국내", "코스피", "코스닥", "KRX", "원달러", "원화", "한국은행", "기준금리"]

function _isUSTicker(ticker: string): boolean {
    return /^[A-Z]{1,5}$/.test(String(ticker || "").trim())
}

function _isUSStock(s: any): boolean {
    return s?.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(s?.market || "") || _isUSTicker(s?.ticker || "")
}

function _toText(v: any): string {
    if (v == null) return ""
    if (Array.isArray(v)) return v.map(_toText).join(" ")
    return String(v)
}

function _containsAny(text: string, kws: string[]): boolean {
    const t = String(text || "").toLowerCase()
    return kws.some((kw) => t.includes(kw.toLowerCase()))
}

function _containsToken(text: string, tokens: Set<string>): boolean {
    const t = String(text || "").toLowerCase()
    for (const token of tokens) {
        if (token && t.includes(token)) return true
    }
    return false
}

function _isUSAlert(a: any, usTokens: Set<string>, krTokens: Set<string>): boolean {
    const cat = String(a?.category || "").toLowerCase()
    const ticker = String(a?.ticker || "").trim()
    const txt = `${_toText(a?.message)} ${_toText(a?.action)} ${_toText(a?.ticker)}`

    if (ticker) return _isUSTicker(ticker)
    if (_containsToken(txt, usTokens)) return true
    if (_containsToken(txt, krTokens)) return false
    if (_containsAny(txt, US_ALERT_KW)) return true
    if (_containsAny(txt, KR_ALERT_KW)) return false

    if (["holding", "earnings", "opportunity", "price_target", "value_chain"].includes(cat)) {
        return false
    }
    return false
}

export default function AlertDashboard(props: Props) {
    const { dataUrl, maxAlerts } = props
    const isUS = props.market === "us"
    const [data, setData] = useState<any>(null)
    const [filter, setFilter] = useState<FilterType>("all")

    useEffect(() => {
        if (!dataUrl) return
        fetchPortfolioJson(dataUrl).then(setData).catch(console.error)
    }, [dataUrl])

    // 백엔드는 generate_briefing → portfolio["briefing"]["alerts"]에 저장함. 루트 data.alerts는 비어 있을 수 있음.
    const fromBriefing = data?.briefing?.alerts
    const fromRoot = data?.alerts
    const rawAlertsAll: any[] = Array.isArray(fromBriefing)
        ? fromBriefing
        : Array.isArray(fromRoot)
          ? fromRoot
          : []
    const recs: any[] = data?.recommendations || []
    const usTokens = new Set<string>()
    const krTokens = new Set<string>()
    for (const r of recs) {
        const ticker = String(r?.ticker || "").trim().toLowerCase()
        const name = String(r?.name || "").trim().toLowerCase()
        const target = _isUSStock(r) ? usTokens : krTokens
        if (ticker.length >= 1) target.add(ticker)
        if (name.length >= 2) target.add(name)
    }
    const rawAlerts = rawAlertsAll.filter((a: any) => (isUS ? _isUSAlert(a, usTokens, krTokens) : !_isUSAlert(a, usTokens, krTokens)))
    const cap = Math.min(30, Math.max(1, Number(maxAlerts) || 15))
    const alerts: any[] = rawAlerts.slice(0, cap)
    const filtered = filter === "all" ? alerts : alerts.filter((a: any) => a.level === filter)

    const counts = { CRITICAL: 0, WARNING: 0, INFO: 0 }
    alerts.forEach((a: any) => {
        if (a.level in counts) counts[a.level as AlertLevel]++
    })
    const aiConsensusCount = alerts.filter((a: any) => (a.category || "").toLowerCase() === "ai_consensus").length

    return (
        <div style={container}>
            <div style={headerRow}>
                <span style={titleStyle}>알림 센터</span>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    {aiConsensusCount > 0 && (
                        <span style={{ ...categoryBadge, color: "#38BDF8", background: "#38BDF815", border: "1px solid #38BDF830" }}>
                            AI합의 {aiConsensusCount}
                        </span>
                    )}
                    <span style={{ color: "#555", fontSize: 10 }}>{alerts.length}건</span>
                </div>
            </div>

            <div style={filterRow}>
                <FilterChip label="전체" active={filter === "all"} count={alerts.length} onClick={() => setFilter("all")} color="#fff" />
                <FilterChip label="긴급" active={filter === "CRITICAL"} count={counts.CRITICAL} onClick={() => setFilter("CRITICAL")} color="#FF4D4D" />
                <FilterChip label="주의" active={filter === "WARNING"} count={counts.WARNING} onClick={() => setFilter("WARNING")} color="#FFD600" />
                <FilterChip label="참고" active={filter === "INFO"} count={counts.INFO} onClick={() => setFilter("INFO")} color="#60A5FA" />
            </div>

            <div style={listWrap}>
                {filtered.length === 0 && (
                    <div style={{ color: "#555", fontSize: 12, textAlign: "center", padding: 30 }}>
                        {alerts.length === 0 ? "알림이 없습니다." : "해당 레벨의 알림이 없습니다."}
                    </div>
                )}
                {filtered.map((a: any, i: number) => {
                    const meta = LEVEL_META[a.level as AlertLevel] || LEVEL_META.INFO
                    return (
                        <div key={i} style={{ ...alertCard, borderLeft: `3px solid ${meta.color}`, background: meta.bg }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <span style={{ fontSize: 11, fontWeight: 700, color: meta.color }}>
                                    {meta.icon} {meta.label}
                                </span>
                                {a.category && (
                                    <span style={categoryBadge}>{CAT_LABELS[String(a.category).toLowerCase()] || a.category}</span>
                                )}
                            </div>
                            <div style={{ color: "#ddd", fontSize: 12, lineHeight: 1.5, marginTop: 4 }}>
                                {a.message}
                            </div>
                            {a.action && (
                                <div style={{ color: "#888", fontSize: 10, marginTop: 4, lineHeight: 1.4 }}>
                                    → {a.action}
                                </div>
                            )}
                        </div>
                    )
                })}
            </div>
        </div>
    )
}

function FilterChip({ label, active, count, onClick, color }: {
    label: string; active: boolean; count: number; onClick: () => void; color: string
}) {
    return (
        <span
            onClick={onClick}
            style={{
                padding: "4px 10px",
                borderRadius: 20,
                fontSize: 11,
                fontWeight: 600,
                cursor: "pointer",
                border: active ? `1px solid ${color}` : "1px solid #333",
                background: active ? `${color}15` : "transparent",
                color: active ? color : "#666",
                fontFamily: "'Inter', 'Pretendard', sans-serif",
            }}
        >
            {label} {count > 0 ? count : ""}
        </span>
    )
}

const DATA_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"

AlertDashboard.defaultProps = {
    dataUrl: DATA_URL,
    maxAlerts: 15,
}

AlertDashboard.defaultProps = { ...AlertDashboard.defaultProps, market: "kr" }

addPropertyControls(AlertDashboard, {
    dataUrl: {
        type: ControlType.String,
        title: "데이터 URL",
        defaultValue: DATA_URL,
    },
    maxAlerts: {
        type: ControlType.Number,
        title: "최대 알림 수",
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

const filterRow: CSSProperties = {
    display: "flex",
    gap: 6,
    flexWrap: "wrap",
}

const listWrap: CSSProperties = {
    display: "flex",
    flexDirection: "column",
    gap: 8,
}

const alertCard: CSSProperties = {
    padding: "10px 12px",
    borderRadius: 10,
    display: "flex",
    flexDirection: "column",
    gap: 2,
}

const categoryBadge: CSSProperties = {
    fontSize: 9,
    color: "#555",
    background: "#1a1a1a",
    padding: "2px 6px",
    borderRadius: 4,
    fontFamily: font,
}
