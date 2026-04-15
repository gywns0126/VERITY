import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"

const DATA_URL =
    "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"

function fetchJson(url: string): Promise<any> {
    const u = (url || "").trim()
    const sep = u.includes("?") ? "&" : "?"
    const busted = `${u}${sep}_=${Date.now()}`
    return fetch(busted, { cache: "no-store", mode: "cors", credentials: "omit" })
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

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"
const BG = "#000"
const CARD = "#111"
const BORDER = "#222"
const MUTED = "#8B95A1"
const WHITE = "#fff"

const PROFILE_META: Record<string, { color: string; icon: string; desc: string }> = {
    aggressive: { color: "#F04452", icon: "🔥", desc: "높은 수익, 높은 리스크" },
    moderate: { color: "#B5FF19", icon: "⚖️", desc: "균형 잡힌 포트폴리오" },
    safe: { color: "#3182F6", icon: "🛡️", desc: "안정 우선, 낮은 변동성" },
}

const PROFILE_ORDER = ["aggressive", "moderate", "safe"] as const

interface Pick {
    ticker: string
    name: string
    price: number | null
    safety_score: number
    recommendation: string
    ai_verdict: string
    detected_risk_keywords: string[]
}

interface ProfileData {
    label: string
    min_safety: number
    max_risk_keywords: number
    max_picks: number
    stop_loss_pct: number
    trailing_stop_pct: number
    max_hold_days: number
    max_per_stock: number
    picks: Pick[]
}

interface Props {
    dataUrl: string
}

function fmtKRW(n: number): string {
    if (!Number.isFinite(n)) return "—"
    if (n >= 1_000_000) return `${(n / 10_000).toLocaleString("ko-KR")}만`
    return n.toLocaleString("ko-KR")
}

function SafetyBar({ score }: { score: number }) {
    const pct = Math.max(0, Math.min(100, score))
    const barColor = pct >= 70 ? "#3182F6" : pct >= 50 ? "#B5FF19" : "#F04452"
    return (
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div
                style={{
                    flex: 1,
                    height: 4,
                    borderRadius: 2,
                    background: "#333",
                    overflow: "hidden",
                }}
            >
                <div
                    style={{
                        width: `${pct}%`,
                        height: "100%",
                        borderRadius: 2,
                        background: barColor,
                    }}
                />
            </div>
            <span style={{ fontSize: 11, color: barColor, fontWeight: 600, minWidth: 26, textAlign: "right" }}>
                {score}
            </span>
        </div>
    )
}

function PickCard({ pick, accentColor }: { pick: Pick; accentColor: string }) {
    const verdict =
        (pick.ai_verdict || "").length > 60
            ? pick.ai_verdict.slice(0, 58) + "…"
            : pick.ai_verdict || "—"

    return (
        <div
            style={{
                background: CARD,
                border: `1px solid ${BORDER}`,
                borderRadius: 10,
                padding: "10px 12px",
                display: "flex",
                flexDirection: "column",
                gap: 6,
            }}
        >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: WHITE }}>
                    {pick.name}
                </span>
                <span
                    style={{
                        fontSize: 10,
                        fontWeight: 600,
                        color: accentColor,
                        background: `${accentColor}18`,
                        padding: "2px 6px",
                        borderRadius: 4,
                    }}
                >
                    {pick.recommendation}
                </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 11, color: MUTED }}>{pick.ticker}</span>
                <span style={{ fontSize: 12, fontWeight: 600, color: WHITE }}>
                    {pick.price ? `${fmtKRW(pick.price)}원` : "—"}
                </span>
            </div>
            <SafetyBar score={pick.safety_score} />
            <p style={{ fontSize: 11, color: MUTED, margin: 0, lineHeight: 1.4 }}>{verdict}</p>
            {pick.detected_risk_keywords.length > 0 && (
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                    {pick.detected_risk_keywords.map((kw, i) => (
                        <span
                            key={i}
                            style={{
                                fontSize: 9,
                                color: "#F04452",
                                background: "#F0445218",
                                padding: "1px 5px",
                                borderRadius: 3,
                                fontWeight: 500,
                            }}
                        >
                            {kw}
                        </span>
                    ))}
                </div>
            )}
        </div>
    )
}

function ProfileColumn({
    profileKey,
    data,
}: {
    profileKey: string
    data: ProfileData
}) {
    const meta = PROFILE_META[profileKey] || PROFILE_META.moderate
    const picks = data.picks || []

    return (
        <div
            style={{
                flex: 1,
                minWidth: 0,
                display: "flex",
                flexDirection: "column",
                gap: 8,
            }}
        >
            {/* header */}
            <div
                style={{
                    background: `${meta.color}12`,
                    border: `1px solid ${meta.color}40`,
                    borderRadius: 10,
                    padding: "12px 14px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 4,
                }}
            >
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontSize: 18 }}>{meta.icon}</span>
                    <span style={{ fontSize: 15, fontWeight: 700, color: meta.color }}>
                        {data.label}
                    </span>
                    <span
                        style={{
                            fontSize: 11,
                            fontWeight: 600,
                            color: meta.color,
                            background: `${meta.color}20`,
                            padding: "1px 6px",
                            borderRadius: 8,
                            marginLeft: "auto",
                        }}
                    >
                        {picks.length}종목
                    </span>
                </div>
                <span style={{ fontSize: 11, color: MUTED }}>{meta.desc}</span>
                <div
                    style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr",
                        gap: "2px 12px",
                        marginTop: 4,
                        fontSize: 10,
                        color: MUTED,
                    }}
                >
                    <span>손절 {data.stop_loss_pct}%</span>
                    <span>트레일링 {data.trailing_stop_pct}%</span>
                    <span>보유 {data.max_hold_days}일</span>
                    <span>종목당 {fmtKRW(data.max_per_stock)}원</span>
                </div>
            </div>

            {/* picks */}
            {picks.length === 0 ? (
                <div
                    style={{
                        background: CARD,
                        border: `1px solid ${BORDER}`,
                        borderRadius: 10,
                        padding: 20,
                        textAlign: "center",
                        color: MUTED,
                        fontSize: 12,
                    }}
                >
                    조건에 맞는 종목 없음
                </div>
            ) : (
                picks.map((p) => (
                    <PickCard key={p.ticker} pick={p} accentColor={meta.color} />
                ))
            )}
        </div>
    )
}

export default function VAMSProfilePanel(props: Props) {
    const { dataUrl } = props
    const [profiles, setProfiles] = useState<Record<string, ProfileData> | null>(null)
    const [error, setError] = useState("")

    useEffect(() => {
        const url = dataUrl || DATA_URL
        fetchJson(url)
            .then((d) => {
                if (d?.vams_profiles) {
                    setProfiles(d.vams_profiles)
                } else {
                    setError("vams_profiles 데이터 없음")
                }
            })
            .catch((e) => setError(e.message))
    }, [dataUrl])

    if (error) {
        return (
            <div
                style={{
                    fontFamily: font,
                    background: BG,
                    color: "#F04452",
                    padding: 20,
                    borderRadius: 12,
                    fontSize: 13,
                    textAlign: "center",
                }}
            >
                {error}
            </div>
        )
    }

    if (!profiles) {
        return (
            <div
                style={{
                    fontFamily: font,
                    background: BG,
                    color: MUTED,
                    padding: 40,
                    borderRadius: 12,
                    fontSize: 13,
                    textAlign: "center",
                }}
            >
                로딩 중…
            </div>
        )
    }

    return (
        <div
            style={{
                fontFamily: font,
                background: BG,
                padding: 16,
                borderRadius: 14,
                display: "flex",
                flexDirection: "column",
                gap: 12,
                width: "100%",
                boxSizing: "border-box",
            }}
        >
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
                <span style={{ fontSize: 16, fontWeight: 700, color: WHITE }}>
                    투자 성향별 추천
                </span>
                <span style={{ fontSize: 11, color: MUTED }}>VAMS Profiles</span>
            </div>

            <div
                style={{
                    display: "flex",
                    gap: 12,
                    width: "100%",
                }}
            >
                {PROFILE_ORDER.map((key) =>
                    profiles[key] ? (
                        <ProfileColumn key={key} profileKey={key} data={profiles[key]} />
                    ) : null,
                )}
            </div>
        </div>
    )
}

VAMSProfilePanel.defaultProps = {
    dataUrl: DATA_URL,
}

addPropertyControls(VAMSProfilePanel, {
    dataUrl: {
        type: ControlType.String,
        title: "Portfolio URL",
        defaultValue: DATA_URL,
    },
})
