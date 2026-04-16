/**
 * CryptoMacroSensor — 크립토 매크로 센서 (주식 분석 보조 지표)
 *
 * portfolio.json의 crypto_macro 데이터를 시각화합니다.
 * 5대 지표: Fear & Greed, 펀딩비, 김치프리미엄, BTC-NQ 상관계수, 스테이블코인 시총
 *
 * 코인 전용 컴포넌트 — 주식 분석의 보조 센서 역할
 */
import { addPropertyControls, ControlType } from "framer"
import { useEffect, useState } from "react"

function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

function fetchJson(url: string, signal?: AbortSignal): Promise<any> {
    return fetch(bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal })
        .then((r) => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            return r.text()
        })
        .then((txt) =>
            JSON.parse(txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")),
        )
}

interface Props {
    dataUrl: string
    refreshIntervalSec: number
    layout: "compact" | "full"
}

// ─── Fear & Greed 게이지 ─────────────────────────────────────

function FearGreedGauge({ value, label, change }: { value: number; label: string; change: number | null }) {
    const angle = -90 + (value / 100) * 180
    const color = value >= 75 ? "#EF4444" : value >= 55 ? "#F97316" : value >= 45 ? "#EAB308" : value >= 25 ? "#22C55E" : "#3B82F6"
    const labelKo = label === "Extreme Greed" ? "극단적 탐욕"
        : label === "Greed" ? "탐욕"
        : label === "Neutral" ? "중립"
        : label === "Fear" ? "공포"
        : label === "Extreme Fear" ? "극단적 공포"
        : label

    return (
        <div style={gaugeCard}>
            <div style={gaugeHeader}>
                <span style={gaugeTitle}>Fear & Greed</span>
                {change != null && (
                    <span style={{ ...changeBadge, color: change >= 0 ? "#EF4444" : "#22C55E" }}>
                        {change >= 0 ? "▲" : "▼"}{Math.abs(change)}
                    </span>
                )}
            </div>
            <div style={gaugeWrap}>
                <svg viewBox="0 0 120 70" width="120" height="70">
                    <defs>
                        <linearGradient id="fng-arc" x1="0" y1="0" x2="1" y2="0">
                            <stop offset="0%" stopColor="#3B82F6" />
                            <stop offset="25%" stopColor="#22C55E" />
                            <stop offset="50%" stopColor="#EAB308" />
                            <stop offset="75%" stopColor="#F97316" />
                            <stop offset="100%" stopColor="#EF4444" />
                        </linearGradient>
                    </defs>
                    <path d="M 10 65 A 50 50 0 0 1 110 65" fill="none" stroke="#1A1A1A" strokeWidth="8" strokeLinecap="round" />
                    <path d="M 10 65 A 50 50 0 0 1 110 65" fill="none" stroke="url(#fng-arc)" strokeWidth="8" strokeLinecap="round"
                        strokeDasharray={`${(value / 100) * 157} 157`} />
                    <line
                        x1="60" y1="65" x2="60" y2="22"
                        stroke={color} strokeWidth="2" strokeLinecap="round"
                        transform={`rotate(${angle}, 60, 65)`}
                    />
                    <circle cx="60" cy="65" r="4" fill={color} />
                </svg>
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 6, justifyContent: "center" }}>
                <span style={{ color, fontSize: 22, fontWeight: 900 }}>{value}</span>
                <span style={{ color: "#888", fontSize: 11, fontWeight: 600 }}>{labelKo}</span>
            </div>
        </div>
    )
}

// ─── 펀딩비 바 ────────────────────────────────────────────────

function FundingRateBar({ ratePct, signal }: { ratePct: number; signal: string }) {
    const isLong = ratePct >= 0
    const absWidth = Math.min(Math.abs(ratePct) / 0.1 * 100, 100)
    const barColor = signal === "long_overheat" ? "#EF4444" : signal === "short_overheat" ? "#3B82F6" : ratePct >= 0 ? "#F97316" : "#60A5FA"
    const signalLabel = signal === "long_overheat" ? "롱 과열" : signal === "short_overheat" ? "숏 과열" : "정상"

    return (
        <div style={metricCard}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={metricLabel}>펀딩비</span>
                <span style={{ ...signalBadge, color: barColor, borderColor: `${barColor}44` }}>{signalLabel}</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
                <div style={fundingBarBg}>
                    <div style={{ position: "absolute" as const, left: "50%", top: 0, bottom: 0, width: 1, background: "#333" }} />
                    <div style={{
                        position: "absolute" as const,
                        top: 1, bottom: 1,
                        borderRadius: 3,
                        background: barColor,
                        boxShadow: `0 0 8px ${barColor}60`,
                        ...(isLong
                            ? { left: "50%", width: `${absWidth / 2}%` }
                            : { right: "50%", width: `${absWidth / 2}%` }),
                    }} />
                </div>
                <span style={{ color: barColor, fontSize: 13, fontWeight: 800, minWidth: 64, textAlign: "right" as const }}>
                    {ratePct >= 0 ? "+" : ""}{ratePct.toFixed(4)}%
                </span>
            </div>
        </div>
    )
}

// ─── 김치 프리미엄 뱃지 ──────────────────────────────────────

function KimchiPremiumBadge({ premiumPct, signal }: { premiumPct: number; signal: string }) {
    const color = signal === "overheated" ? "#EF4444" : signal === "elevated" ? "#F97316" : signal === "discount" ? "#3B82F6" : "#22C55E"
    const isFlashing = signal === "overheated"
    const signalLabel = signal === "overheated" ? "과열" : signal === "elevated" ? "주의" : signal === "discount" ? "역프" : "정상"

    return (
        <div style={{ ...metricCard, borderColor: isFlashing ? `${color}66` : "#222" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={metricLabel}>김치 프리미엄</span>
                <span style={{ ...signalBadge, color, borderColor: `${color}44` }}>{signalLabel}</span>
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginTop: 8 }}>
                <span style={{
                    color,
                    fontSize: 24,
                    fontWeight: 900,
                    animation: isFlashing ? "pulse 1.5s ease-in-out infinite" : "none",
                }}>
                    {premiumPct >= 0 ? "+" : ""}{premiumPct.toFixed(2)}%
                </span>
                <span style={{ color: "#555", fontSize: 10 }}>업비트 vs 바이낸스</span>
            </div>
        </div>
    )
}

// ─── BTC-NQ 상관계수 ─────────────────────────────────────────

function CorrelationMeter({ correlation, signal }: { correlation: number; signal: string }) {
    const normalized = (correlation + 1) / 2
    const fillPct = normalized * 100
    const color = correlation >= 0.7 ? "#EF4444" : correlation >= 0.4 ? "#F97316" : correlation <= -0.3 ? "#3B82F6" : "#22C55E"
    const signalLabel = signal === "strongly_coupled" ? "강결합"
        : signal === "moderately_coupled" ? "연동"
        : signal === "inversely_correlated" ? "역상관"
        : "독립"

    return (
        <div style={metricCard}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={metricLabel}>BTC-나스닥 상관</span>
                <span style={{ ...signalBadge, color, borderColor: `${color}44` }}>{signalLabel}</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
                <div style={corrBarBg}>
                    <div style={{
                        position: "absolute" as const,
                        top: 1, bottom: 1, left: 1,
                        width: `${fillPct}%`,
                        borderRadius: 3,
                        background: `linear-gradient(90deg, #3B82F6, #22C55E, #F97316, #EF4444)`,
                        opacity: 0.8,
                    }} />
                    <div style={{
                        position: "absolute" as const,
                        top: -2, bottom: -2,
                        left: `${fillPct}%`,
                        width: 3,
                        background: "#fff",
                        borderRadius: 2,
                        boxShadow: "0 0 6px rgba(255,255,255,0.5)",
                        transform: "translateX(-50%)",
                    }} />
                </div>
                <span style={{ color, fontSize: 14, fontWeight: 800, minWidth: 44, textAlign: "right" as const }}>
                    {correlation >= 0 ? "+" : ""}{correlation.toFixed(2)}
                </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
                <span style={{ color: "#333", fontSize: 8 }}>-1.0</span>
                <span style={{ color: "#333", fontSize: 8 }}>0</span>
                <span style={{ color: "#333", fontSize: 8 }}>+1.0</span>
            </div>
        </div>
    )
}

// ─── 스테이블코인 시총 ───────────────────────────────────────

function StablecoinBar({ totalB, usdtB, usdcB }: { totalB: number; usdtB: number; usdcB: number }) {
    const usdtPct = totalB > 0 ? (usdtB / totalB) * 100 : 50
    return (
        <div style={metricCard}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={metricLabel}>스테이블코인 시총</span>
                <span style={{ color: "#B5FF19", fontSize: 14, fontWeight: 800 }}>${totalB.toFixed(0)}B</span>
            </div>
            <div style={{ ...stackedBar, marginTop: 8 }}>
                <div style={{ width: `${usdtPct}%`, background: "#22C55E", height: "100%", borderRadius: "3px 0 0 3px" }} />
                <div style={{ width: `${100 - usdtPct}%`, background: "#3B82F6", height: "100%", borderRadius: "0 3px 3px 0" }} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
                <span style={{ color: "#22C55E", fontSize: 9, fontWeight: 600 }}>USDT ${usdtB.toFixed(0)}B</span>
                <span style={{ color: "#3B82F6", fontSize: 9, fontWeight: 600 }}>USDC ${usdcB.toFixed(0)}B</span>
            </div>
        </div>
    )
}

// ─── 종합 온도계 ─────────────────────────────────────────────

function CompositeThermo({ score, label, signals }: { score: number; label: string; signals: string[] }) {
    const color = score >= 75 ? "#EF4444" : score >= 60 ? "#F97316" : score >= 40 ? "#B5FF19" : score >= 25 ? "#22C55E" : "#3B82F6"
    return (
        <div style={{ ...compositeCard, borderColor: `${color}33` }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{ position: "relative" as const, width: 40, height: 40 }}>
                    <svg viewBox="0 0 40 40" width="40" height="40">
                        <circle cx="20" cy="20" r="17" fill="none" stroke="#1A1A1A" strokeWidth="3" />
                        <circle cx="20" cy="20" r="17" fill="none" stroke={color} strokeWidth="3" strokeLinecap="round"
                            strokeDasharray={`${(score / 100) * 106.8} 106.8`}
                            transform="rotate(-90 20 20)" />
                    </svg>
                    <span style={{
                        position: "absolute" as const, top: "50%", left: "50%",
                        transform: "translate(-50%, -50%)",
                        color, fontSize: 11, fontWeight: 900,
                    }}>{score}</span>
                </div>
                <div>
                    <div style={{ color: "#aaa", fontSize: 10, fontWeight: 600, marginBottom: 2 }}>크립토 매크로 온도</div>
                    <div style={{ color, fontSize: 14, fontWeight: 800 }}>{label}</div>
                </div>
            </div>
            {signals.length > 0 && (
                <div style={{ marginTop: 8, display: "flex", flexDirection: "column" as const, gap: 3 }}>
                    {signals.map((s, i) => (
                        <span key={i} style={{ color: "#888", fontSize: 10, paddingLeft: 8, borderLeft: `2px solid ${color}33` }}>{s}</span>
                    ))}
                </div>
            )}
        </div>
    )
}

// ─── 메인 컴포넌트 ───────────────────────────────────────────

export default function CryptoMacroSensor(props: Props) {
    const { dataUrl, refreshIntervalSec = 180, layout = "full" } = props
    const [data, setData] = useState<any>(null)
    const [fetchErr, setFetchErr] = useState<string | null>(null)

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        setFetchErr(null)
        fetchJson(dataUrl, ac.signal)
            .then(d => { if (!ac.signal.aborted) setData(d) })
            .catch((e) => { if (!ac.signal.aborted) setFetchErr(e instanceof Error ? e.message : String(e)) })
        const sec = Math.max(30, refreshIntervalSec)
        const id = setInterval(() => {
            fetchJson(dataUrl).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        }, sec * 1000)
        return () => { ac.abort(); clearInterval(id) }
    }, [dataUrl, refreshIntervalSec])

    if (!dataUrl) {
        return (
            <div style={{ ...panel, padding: 20, textAlign: "center" as const }}>
                <span style={{ color: "#666", fontSize: 12 }}>dataUrl을 설정하세요.</span>
            </div>
        )
    }

    if (data === null && !fetchErr) {
        return (
            <div style={{ ...panel, padding: 20, textAlign: "center" as const }}>
                <span style={{ color: "#666", fontSize: 12 }}>portfolio.json 불러오는 중…</span>
            </div>
        )
    }

    if (fetchErr) {
        return (
            <div style={{ ...panel, padding: 20, textAlign: "center" as const }}>
                <span style={{ color: "#F97316", fontSize: 12 }}>JSON 로드 실패: {fetchErr}</span>
            </div>
        )
    }

    const crypto = data?.crypto_macro
    if (!crypto || typeof crypto !== "object") {
        return (
            <div style={{ ...panel, padding: 16, textAlign: "left" as const }}>
                <div style={{ color: "#888", fontSize: 11, lineHeight: 1.6 }}>
                    이 portfolio.json에는 아직 <span style={{ color: "#B5FF19" }}>crypto_macro</span> 블록이 없습니다.
                    <br /><br />
                    GitHub Actions로 <span style={{ color: "#ccc" }}>main.py</span>가 돌고 나온 최신{" "}
                    <span style={{ color: "#ccc" }}>data/portfolio.json</span>이 푸시됐는지 확인하세요.
                    (Framer는 코인 API를 직접 호출하지 않습니다.)
                </div>
            </div>
        )
    }

    const fng = crypto.fear_and_greed || {}
    const funding = crypto.funding_rate || {}
    const kimchi = crypto.kimchi_premium || {}
    const corr = crypto.btc_nasdaq_corr || {}
    const stable = crypto.stablecoin_mcap || {}
    const composite = crypto.composite || {}

    const hasAnyOk = !!(fng.ok || funding.ok || kimchi.ok || corr.ok || stable.ok)
    if (!hasAnyOk) {
        const hints = [
            fng.error && `F&G: ${fng.error}`,
            funding.error && `펀딩: ${funding.error}`,
            kimchi.error && `김프: ${kimchi.error}`,
            corr.error && `상관: ${corr.error}`,
            stable.error && `스테이블: ${stable.error}`,
        ].filter(Boolean) as string[]
        return (
            <div style={{ ...panel, padding: 16, textAlign: "left" as const }}>
                <div style={{ color: "#888", fontSize: 11, lineHeight: 1.6, marginBottom: 8 }}>
                    크립토 센서 5개 소스가 모두 실패했습니다. (백엔드 수집 시 일시 차단·타임아웃 가능)
                </div>
                {hints.slice(0, 3).map((h, i) => (
                    <div key={i} style={{ color: "#555", fontSize: 10, marginTop: 4 }}>{h}</div>
                ))}
            </div>
        )
    }

    if (layout === "compact") {
        return (
            <div style={panel}>
                <div style={compactHeader}>
                    <span style={{ color: "#555", fontSize: 10, fontWeight: 700, letterSpacing: "0.05em" }}>CRYPTO SENSOR</span>
                    <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                        {fng.ok && (
                            <div style={compactChip}>
                                <span style={compactLabel}>F&G</span>
                                <span style={{ color: fng.value >= 60 ? "#EF4444" : fng.value <= 40 ? "#3B82F6" : "#EAB308", fontSize: 12, fontWeight: 800 }}>{fng.value}</span>
                            </div>
                        )}
                        {funding.ok && (
                            <div style={compactChip}>
                                <span style={compactLabel}>펀딩비</span>
                                <span style={{ color: funding.signal === "long_overheat" ? "#EF4444" : funding.signal === "short_overheat" ? "#3B82F6" : "#888", fontSize: 12, fontWeight: 800 }}>
                                    {funding.rate_pct >= 0 ? "+" : ""}{funding.rate_pct.toFixed(3)}%
                                </span>
                            </div>
                        )}
                        {kimchi.ok && (
                            <div style={compactChip}>
                                <span style={compactLabel}>김프</span>
                                <span style={{ color: kimchi.premium_pct >= 5 ? "#EF4444" : kimchi.premium_pct >= 3 ? "#F97316" : "#22C55E", fontSize: 12, fontWeight: 800 }}>
                                    {kimchi.premium_pct >= 0 ? "+" : ""}{kimchi.premium_pct.toFixed(1)}%
                                </span>
                            </div>
                        )}
                        {corr.ok && (
                            <div style={compactChip}>
                                <span style={compactLabel}>BTC-NQ</span>
                                <span style={{ color: corr.correlation >= 0.7 ? "#EF4444" : "#888", fontSize: 12, fontWeight: 800 }}>
                                    {corr.correlation.toFixed(2)}
                                </span>
                            </div>
                        )}
                        {stable.ok && (
                            <div style={compactChip}>
                                <span style={compactLabel}>스테이블</span>
                                <span style={{ color: "#B5FF19", fontSize: 12, fontWeight: 800 }}>${stable.total_mcap_b?.toFixed(0)}B</span>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        )
    }

    return (
        <div style={panel}>
            <div style={headerRow}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={sectionIcon}>◈</span>
                    <span style={sectionTitle}>크립토 매크로 센서</span>
                    <span style={subtitleTag}>주식 보조 지표</span>
                </div>
                <span style={{ color: "#333", fontSize: 9 }}>{crypto.ok_count}/{crypto.total} 지표 활성</span>
            </div>

            <CompositeThermo score={composite.score ?? 50} label={composite.label || "중립"} signals={composite.signals || []} />

            <div style={gridRow}>
                {fng.ok && <FearGreedGauge value={fng.value} label={fng.label} change={fng.change} />}
                {funding.ok && <FundingRateBar ratePct={funding.rate_pct} signal={funding.signal} />}
            </div>

            <div style={gridRow}>
                {kimchi.ok && <KimchiPremiumBadge premiumPct={kimchi.premium_pct} signal={kimchi.signal} />}
                {corr.ok && <CorrelationMeter correlation={corr.correlation} signal={corr.signal} />}
            </div>

            {stable.ok && (
                <StablecoinBar totalB={stable.total_mcap_b} usdtB={stable.usdt_mcap_b} usdcB={stable.usdc_mcap_b} />
            )}
        </div>
    )
}

CryptoMacroSensor.defaultProps = {
    dataUrl: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json",
    refreshIntervalSec: 180,
    layout: "full",
}

addPropertyControls(CryptoMacroSensor, {
    dataUrl: { type: ControlType.String, title: "JSON URL", defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json" },
    refreshIntervalSec: { type: ControlType.Number, title: "갱신 간격(초)", defaultValue: 180, min: 30, max: 3600, step: 30 },
    layout: { type: ControlType.Enum, title: "레이아웃", options: ["compact", "full"], optionTitles: ["컴팩트 (바 형태)", "전체 (카드 형태)"], defaultValue: "full" },
})

// ─── 스타일 ──────────────────────────────────────────────────

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"

const panel: React.CSSProperties = {
    width: "100%",
    fontFamily: font,
    background: "#000",
    borderRadius: 16,
    border: "1px solid #1A1A1A",
    padding: 16,
}

const headerRow: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
}

const sectionIcon: React.CSSProperties = {
    color: "#F97316",
    fontSize: 14,
}

const sectionTitle: React.CSSProperties = {
    color: "#eee",
    fontSize: 14,
    fontWeight: 800,
}

const subtitleTag: React.CSSProperties = {
    color: "#555",
    fontSize: 9,
    fontWeight: 600,
    background: "#111",
    border: "1px solid #222",
    borderRadius: 4,
    padding: "2px 6px",
}

const gridRow: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 10,
    marginTop: 10,
}

const gaugeCard: React.CSSProperties = {
    background: "#0A0A0A",
    border: "1px solid #1A1A1A",
    borderRadius: 12,
    padding: 12,
}

const gaugeHeader: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 4,
}

const gaugeTitle: React.CSSProperties = {
    color: "#888",
    fontSize: 10,
    fontWeight: 700,
}

const gaugeWrap: React.CSSProperties = {
    display: "flex",
    justifyContent: "center",
    padding: "4px 0",
}

const changeBadge: React.CSSProperties = {
    fontSize: 10,
    fontWeight: 700,
}

const metricCard: React.CSSProperties = {
    background: "#0A0A0A",
    border: "1px solid #1A1A1A",
    borderRadius: 12,
    padding: 12,
}

const metricLabel: React.CSSProperties = {
    color: "#888",
    fontSize: 10,
    fontWeight: 700,
}

const signalBadge: React.CSSProperties = {
    fontSize: 9,
    fontWeight: 700,
    border: "1px solid",
    borderRadius: 4,
    padding: "1px 5px",
}

const fundingBarBg: React.CSSProperties = {
    position: "relative" as const,
    flex: 1,
    height: 10,
    background: "#111",
    borderRadius: 4,
    overflow: "hidden",
}

const corrBarBg: React.CSSProperties = {
    position: "relative" as const,
    flex: 1,
    height: 8,
    background: "#111",
    borderRadius: 4,
    overflow: "visible",
}

const compositeCard: React.CSSProperties = {
    background: "#0A0A0A",
    border: "1px solid #222",
    borderRadius: 12,
    padding: 12,
}

const stackedBar: React.CSSProperties = {
    display: "flex",
    height: 8,
    borderRadius: 4,
    overflow: "hidden",
}

const compactHeader: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 16,
}

const compactChip: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 5,
}

const compactLabel: React.CSSProperties = {
    color: "#555",
    fontSize: 9,
    fontWeight: 600,
}
