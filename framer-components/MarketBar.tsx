import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

interface Props {
    dataUrl: string
    title: string
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

export default function MarketBar(props: Props) {
    const { dataUrl, title } = props
    const [data, setData] = useState<any>(null)

    useEffect(() => {
        if (!dataUrl) return
        fetch(dataUrl)
            .then((r) => r.text())
            .then((txt) => JSON.parse(txt.replace(/\bNaN\b/g, "null")))
            .then(setData)
            .catch(console.error)
    }, [dataUrl])

    const market = data?.market_summary || {}
    const macro = data?.macro || {}
    const mood = macro.market_mood || {}
    const kospi = market.kospi || {}
    const kosdaq = market.kosdaq || {}
    const score = mood.score ?? 50
    const o2 = getO2(score)

    const updated = data?.updated_at
        ? new Date(data.updated_at).toLocaleString("ko-KR", {
              month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
          })
        : "—"

    return (
        <div style={container}>
            {/* 로고 + 산소 게이지 */}
            <div style={leftSection}>
                <span style={logo}>{title}</span>
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

            {/* 지수 */}
            <div style={centerSection}>
                <IndexChip label="KOSPI" value={kospi.value} pct={kospi.change_pct} />
                <IndexChip label="KOSDAQ" value={kosdaq.value} pct={kosdaq.change_pct} />
                <IndexChip label="USD/KRW" value={macro.usd_krw?.value} pct={null} />
                <IndexChip label="VIX" value={macro.vix?.value}
                    pct={null}
                    color={(macro.vix?.value || 0) > 25 ? "#EF4444" : (macro.vix?.value || 0) < 18 ? "#22C55E" : "#EAB308"} />
            </div>

            <span style={updatedText}>{updated}</span>
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
    title: "VERITY",
}

addPropertyControls(MarketBar, {
    dataUrl: { type: ControlType.String, title: "JSON URL", defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json" },
    title: { type: ControlType.String, title: "서비스명", defaultValue: "VERITY" },
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

const logo: React.CSSProperties = {
    color: "#B5FF19",
    fontSize: 15,
    fontWeight: 800,
    letterSpacing: -0.5,
    whiteSpace: "nowrap",
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

const chipWrap: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 6,
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

const updatedText: React.CSSProperties = {
    color: "#444",
    fontSize: 10,
    marginLeft: "auto",
    whiteSpace: "nowrap",
    flexShrink: 0,
}
