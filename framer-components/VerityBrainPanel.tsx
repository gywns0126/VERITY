import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState, useCallback } from "react"

function _bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    return `${u}${u.includes("?") ? "&" : "?"}_=${Date.now()}`
}

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
        fetch(_bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal: ac.signal })
            .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
            .then((t) => JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null"))),
        PORTFOLIO_FETCH_TIMEOUT_MS,
        ac,
    )
}

// WARN-23: updated_at 기준 stale 경고 정보
function stalenessInfo(updatedAt: any): { label: string; color: string; stale: boolean } {
    if (!updatedAt) return { label: "", color: "#666", stale: false }
    const t = new Date(String(updatedAt)).getTime()
    if (!Number.isFinite(t)) return { label: "", color: "#666", stale: false }
    const hours = (Date.now() - t) / 3_600_000
    if (hours < 1) return { label: `방금 갱신 (${Math.round(hours * 60)}분 전)`, color: "#22C55E", stale: false }
    if (hours < 3) return { label: `${Math.round(hours)}시간 전`, color: "#B5FF19", stale: false }
    if (hours < 12) return { label: `${Math.round(hours)}시간 전`, color: "#FFD600", stale: false }
    if (hours < 24) return { label: `${Math.round(hours)}시간 전 (⚠️ stale 경계)`, color: "#F59E0B", stale: true }
    const days = hours / 24
    return { label: `${days.toFixed(1)}일 전 (⚠️ stale)`, color: "#FF4D4D", stale: true }
}

const DATA_URL =
    "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"

function _isUS(r: any): boolean {
    return r?.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(r?.market || "")
}

interface Props {
    dataUrl: string
    market: "kr" | "us"
}

/** 멀티팩터 한글 등급 → Brain 등급 코드 */
function gradeFromMultiFactorLabel(label: string): string {
    const g = String(label || "").trim()
    if (g.includes("강력") || g.includes("강매")) return "STRONG_BUY"
    if (g.includes("회피")) return "AVOID"
    if (g.includes("매도")) return "AVOID"
    if (g.includes("주의")) return "CAUTION"
    if (g === "매수" || g.startsWith("매수")) return "BUY"
    return "WATCH"
}

/** verity_brain 없을 때 multi_factor + sentiment 로 시장 집계 (구버전 JSON 호환) */
function synthesizeMarketBrainFromMultiFactor(recs: any[]) {
    const rows = recs
        .map((s) => {
            const mf = s.multi_factor || {}
            const raw = mf.multi_score
            if (raw == null || Number.isNaN(Number(raw))) return null
            const brain = Number(raw)
            const fund = Number(mf.factor_breakdown?.fundamental ?? mf.multi_score ?? brain)
            const sen = Number(s.sentiment?.score ?? 50)
            const gradeLabel = String(mf.grade || "관망")
            return { s, brain, fund, sen, gradeLabel }
        })
        .filter(Boolean) as Array<{ s: any; brain: number; fund: number; sen: number; gradeLabel: string }>
    if (rows.length === 0) return null
    const roundAvg = (xs: number[]) => Math.round(xs.reduce((a, b) => a + b, 0) / xs.length)
    const avg_fact = roundAvg(rows.map((r) => r.fund))
    const avg_sent = roundAvg(rows.map((r) => r.sen))
    const gradeDist: Record<string, number> = { STRONG_BUY: 0, BUY: 0, WATCH: 0, CAUTION: 0, AVOID: 0 }
    for (const r of rows) {
        const g = gradeFromMultiFactorLabel(r.gradeLabel)
        gradeDist[g] = (gradeDist[g] || 0) + 1
    }
    const sorted = [...rows].sort((a, b) => b.brain - a.brain)
    const topPicks = sorted
        .filter((r) => ["STRONG_BUY", "BUY"].includes(gradeFromMultiFactorLabel(r.gradeLabel)))
        .slice(0, 5)
        .map((r) => {
            const g = gradeFromMultiFactorLabel(r.gradeLabel)
            const vci = Math.round(r.fund - r.sen)
            return {
                ticker: r.s.ticker,
                name: r.s.name,
                score: r.brain,
                brain_score: r.brain,
                grade: g,
                vci,
            }
        })
    const redFlagStocks = rows
        .filter((r) => Array.isArray(r.s.risk_flags) && r.s.risk_flags.length > 0)
        .map((r) => ({
            ticker: r.s.ticker,
            name: r.s.name,
            grade: gradeFromMultiFactorLabel(r.gradeLabel),
            flags: r.s.risk_flags.map((x: any) => String(x)),
        }))
    return {
        avg_brain_score: roundAvg(rows.map((r) => r.brain)),
        avg_fact_score: avg_fact,
        avg_sentiment_score: avg_sent,
        avg_vci: avg_fact - avg_sent,
        grade_distribution: gradeDist,
        top_picks: topPicks,
        red_flag_stocks: redFlagStocks,
    }
}

/** 종목 탭용: Brain 없으면 멀티팩터로 synthetic verity_brain 부착 */
function enrichStockWithSyntheticBrain(s: any): any {
    if (s?.verity_brain != null && s.verity_brain.brain_score != null) return s
    const mf = s?.multi_factor || {}
    const raw = mf.multi_score
    if (raw == null || Number.isNaN(Number(raw))) return s
    const brain = Number(raw)
    const fund = Number(mf.factor_breakdown?.fundamental ?? mf.multi_score ?? brain)
    const sen = Number(s.sentiment?.score ?? 50)
    const vci = Math.round(fund - sen)
    const grade = gradeFromMultiFactorLabel(mf.grade)
    return {
        ...s,
        verity_brain: {
            brain_score: brain,
            grade,
            fact_score: { score: Math.round(fund) },
            sentiment_score: { score: Math.round(sen) },
            vci: { vci },
            red_flags: { has_critical: false, downgrade_count: 0, auto_avoid: [], downgrade: [] },
        },
    }
}

/** market_brain 누락 시 recommendations[].verity_brain 으로 집계 복원 */
function synthesizeMarketBrainFromRecommendations(recs: any[]) {
    const withBrain = recs.filter((s) => s?.verity_brain != null && s.verity_brain.brain_score != null)
    if (withBrain.length === 0) return null
    const scores = withBrain.map((s) => Number(s.verity_brain.brain_score))
    const facts = withBrain.map((s) => Number(s.verity_brain.fact_score?.score ?? 0))
    const sents = withBrain.map((s) => Number(s.verity_brain.sentiment_score?.score ?? 0))
    const roundAvg = (xs: number[]) => Math.round(xs.reduce((a, b) => a + b, 0) / xs.length)
    const avg_fact = roundAvg(facts)
    const avg_sent = roundAvg(sents)
    const gradeDist: Record<string, number> = { STRONG_BUY: 0, BUY: 0, WATCH: 0, CAUTION: 0, AVOID: 0 }
    for (const s of withBrain) {
        const g = String(s.verity_brain.grade || "WATCH")
        gradeDist[g] = (gradeDist[g] || 0) + 1
    }
    const sorted = [...withBrain].sort((a, b) => b.verity_brain.brain_score - a.verity_brain.brain_score)
    const topPicks = sorted
        .filter((s) => ["STRONG_BUY", "BUY"].includes(s.verity_brain.grade))
        .slice(0, 5)
        .map((s) => ({
            ticker: s.ticker,
            name: s.name,
            score: s.verity_brain.brain_score,
            brain_score: s.verity_brain.brain_score,
            grade: s.verity_brain.grade,
            vci: Number(s.verity_brain.vci?.vci ?? 0),
        }))
    const redFlagStocks = withBrain
        .filter((s) => {
            const rf = s.verity_brain.red_flags || {}
            return rf.has_critical || (Number(rf.downgrade_count) || 0) >= 2
        })
        .map((s) => {
            const rf = s.verity_brain.red_flags || {}
            const flags = [...(rf.auto_avoid || []), ...(rf.downgrade || [])]
            return { ticker: s.ticker, name: s.name, grade: s.verity_brain.grade, flags }
        })
    return {
        avg_brain_score: roundAvg(scores),
        avg_fact_score: avg_fact,
        avg_sentiment_score: avg_sent,
        avg_vci: avg_fact - avg_sent,
        grade_distribution: gradeDist,
        top_picks: topPicks,
        red_flag_stocks: redFlagStocks,
    }
}

export default function VerityBrainPanel(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [error, setError] = useState<string | null>(null)
    const [tab, setTab] = useState<"overview" | "stocks" | "redflags">("overview")

    const loadData = useCallback((signal?: AbortSignal) => {
        if (!dataUrl) return
        setError(null)
        fetchPortfolioJson(dataUrl, signal)
            .then(setData)
            .catch((e) => {
                if (e?.name === "AbortError") return
                setError(e?.message || "데이터 로드 실패")
            })
    }, [dataUrl])

    useEffect(() => {
        const ac = new AbortController()
        loadData(ac.signal)
        return () => ac.abort()
    }, [loadData])

    if (error) {
        return (
            <div style={{ ...card, minHeight: 200, alignItems: "center", justifyContent: "center", gap: 12 }}>
                <span style={{ color: "#EF4444", fontSize: 13, fontFamily: font }}>데이터 로드 실패: {error}</span>
                <button
                    onClick={() => loadData()}
                    style={{
                        background: "none", border: "1px solid #333", borderRadius: 8,
                        color: "#B5FF19", fontSize: 12, fontFamily: font, padding: "6px 16px",
                        cursor: "pointer",
                    }}
                >
                    재시도
                </button>
            </div>
        )
    }

    if (!data) {
        return (
            <div style={{ ...card, minHeight: 200, alignItems: "center", justifyContent: "center" }}>
                <span style={{ color: "#555", fontSize: 14, fontFamily: font }}>Brain 데이터 로딩 중...</span>
            </div>
        )
    }

    const isUS = props.market === "us"
    const brain = data?.verity_brain || {}
    const macroOv = brain.macro_override || {}
    const allRecs: any[] = data?.recommendations || []
    const recs: any[] = allRecs.filter((r) => isUS ? _isUS(r) : !_isUS(r))
    let market = brain.market_brain || {}
    let usedMultifactorProxy = false

    // 포트폴리오가 KR/US를 함께 담는 경우가 있어, 화면 시장 기준으로 집계를 재구성한다.
    if (recs.length > 0) {
        const synV = synthesizeMarketBrainFromRecommendations(recs)
        if (synV) market = { ...market, ...synV }
        else {
            const synM = synthesizeMarketBrainFromMultiFactor(recs)
            if (synM) {
                market = { ...market, ...synM }
                usedMultifactorProxy = true
            }
        }
    }

    const recsDisplay = usedMultifactorProxy ? recs.map(enrichStockWithSyntheticBrain) : recs

    const avgBrain = market.avg_brain_score ?? null
    const _rawFact = market.avg_fact_score
    const _rawSent = market.avg_sentiment_score
    const _rawVci = market.avg_vci
    const avgFact = (_rawFact != null && !Number.isNaN(Number(_rawFact))) ? Number(_rawFact) : 0
    const avgSent = (_rawSent != null && !Number.isNaN(Number(_rawSent))) ? Number(_rawSent) : 0
    const avgVci = (_rawVci != null && !Number.isNaN(Number(_rawVci))) ? Number(_rawVci) : 0
    const gradeDist: Record<string, number> = market.grade_distribution || {}
    const topPicks: any[] = market.top_picks || []
    const redFlagStocks: any[] = market.red_flag_stocks || []

    if (avgBrain === null) {
        return (
            <div style={{ ...card, minHeight: 160, alignItems: "center", justifyContent: "center", padding: "0 20px" }}>
                <span style={{ color: "#555", fontSize: 13, fontFamily: font, textAlign: "center", lineHeight: 1.5 }}>
                    Verity Brain 집계가 없습니다. 파이프라인 실행 후 배포된 portfolio.json에 시장 집계
                    (verity_brain.market_brain)가 들어 있는지, Framer의 JSON URL이 그 파일을 가리키는지 확인하세요.
                </span>
            </div>
        )
    }

    const brainColor = avgBrain >= 65 ? "#B5FF19" : avgBrain >= 45 ? "#FFD600" : "#FF4D4D"
    const factColor = _rawFact == null ? "#555" : avgFact >= 65 ? "#22C55E" : avgFact >= 45 ? "#FFD600" : "#FF4D4D"
    const sentColor = _rawSent == null ? "#555" : avgSent >= 65 ? "#60A5FA" : avgSent >= 45 ? "#FFD600" : "#FF4D4D"
    const vciColor = avgVci > 15 ? "#B5FF19" : avgVci < -15 ? "#FF4D4D" : "#888"

    const gradeOrder = ["STRONG_BUY", "BUY", "WATCH", "CAUTION", "AVOID"]
    const gradeLabels: Record<string, string> = { STRONG_BUY: "강력매수", BUY: "매수", WATCH: "관망", CAUTION: "주의", AVOID: "회피" }
    const gradeColors: Record<string, string> = { STRONG_BUY: "#22C55E", BUY: "#B5FF19", WATCH: "#FFD600", CAUTION: "#F59E0B", AVOID: "#EF4444" }

    const totalGraded = Object.values(gradeDist).reduce((a, b) => a + b, 0) || 1
    const ovMode = String(macroOv.mode || "").toLowerCase()
    const panicActive = ovMode.startsWith("panic")
    const yieldDefActive = ovMode === "yield_defense"
    const euphoriaActive = ovMode === "euphoria"

    const expiry = market.expiry || data?.expiry_status || {}
    const expiryWatch = String(expiry.watch_level || "NORMAL")
    const expiryReason = expiry.reason || ""
    const prog = market.program_trading || data?.program_trading || {}
    const progSignal = String(prog.signal || "NEUTRAL")
    const progOk = !!prog.ok || prog.signal != null
    const sellBomb = !!prog.sell_bomb
    const hasExpiry = expiry.watch_level != null
    const hasStructureData = hasExpiry || progOk

    const cboePcr = market.cboe_pcr || data?.cboe_pcr || {}
    const pcrPanic = !!cboePcr.panic_trigger
    const pcrSignal = String(cboePcr.signal || "NEUTRAL")

    return (
        <div style={card}>
            {/* 매크로 오버라이드 배너 */}
            {(panicActive || yieldDefActive || euphoriaActive) && (
                <div style={{
                    padding: "12px 20px",
                    background: panicActive ? "rgba(239,68,68,0.1)" : yieldDefActive ? "rgba(56,189,248,0.1)" : "rgba(234,179,8,0.1)",
                    borderBottom: `2px solid ${panicActive ? "#EF4444" : yieldDefActive ? "#38BDF8" : "#EAB308"}`,
                    display: "flex", alignItems: "center", gap: 10,
                }}>
                    <span style={{ fontSize: 20 }}>{panicActive ? "🚨" : yieldDefActive ? "🛡️" : "⚠️"}</span>
                    <div>
                        <span style={{
                            color: panicActive ? "#EF4444" : yieldDefActive ? "#38BDF8" : "#EAB308",
                            fontSize: 13, fontWeight: 800,
                        }}>
                            {panicActive ? "PANIC MODE — 신규 매수 제한" : yieldDefActive ? "YIELD DEFENSE — 금리 방패 (관망 상한)" : "EUPHORIA MODE — 과열 경계"}
                        </span>
                        <div style={{ color: "#888", fontSize: 11, marginTop: 2 }}>
                            {macroOv.reason || macroOv.message || "매크로 오버라이드 활성"}
                        </div>
                    </div>
                </div>
            )}

            {/* 만기일 관망 배너 */}
            {expiryWatch !== "NORMAL" && (
                <div style={{
                    padding: "10px 20px",
                    background: expiryWatch === "FULL_WATCH" ? "rgba(239,68,68,0.08)" : "rgba(245,158,11,0.08)",
                    borderBottom: `2px solid ${expiryWatch === "FULL_WATCH" ? "#EF4444" : "#F59E0B"}`,
                    display: "flex", alignItems: "center", gap: 10,
                }}>
                    <span style={{ fontSize: 18 }}>{expiryWatch === "FULL_WATCH" ? "\u26A0\uFE0F" : "\u23F3"}</span>
                    <div style={{ flex: 1 }}>
                        <span style={{
                            color: expiryWatch === "FULL_WATCH" ? "#EF4444" : "#F59E0B",
                            fontSize: 12, fontWeight: 800, fontFamily: font,
                        }}>
                            {expiryWatch === "FULL_WATCH" ? "FULL WATCH" : "CAUTION"} — {expiryReason}
                        </span>
                        <div style={{ color: "#666", fontSize: 10, marginTop: 2, fontFamily: font }}>
                            {expiryWatch === "FULL_WATCH"
                                ? "추격매수 완전 차단 / BUY → WATCH 강등"
                                : "신규 진입 자제 / 포지션 한도 50%"}
                            {expiry.days_to_kr_option != null && (
                                <span style={{ marginLeft: 8, color: "#555" }}>
                                    KR옵션 D-{expiry.days_to_kr_option}
                                    {expiry.days_to_kr_futures != null && expiry.days_to_kr_futures <= 10
                                        ? ` / KR선물 D-${expiry.days_to_kr_futures}` : ""}
                                </span>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {/* CBOE 풋/콜 패닉 배너 */}
            {pcrPanic && (
                <div style={{
                    padding: "10px 20px",
                    background: "rgba(239,68,68,0.1)",
                    borderBottom: "2px solid #EF4444",
                    display: "flex", alignItems: "center", gap: 10,
                }}>
                    <span style={{ fontSize: 18 }}>{"\uD83D\uDEA8"}</span>
                    <div style={{ flex: 1 }}>
                        <span style={{ color: "#EF4444", fontSize: 12, fontWeight: 800, fontFamily: font }}>
                            CBOE PCR PANIC — 풋/콜 비율 극단
                        </span>
                        <div style={{ color: "#888", fontSize: 10, marginTop: 2, fontFamily: font }}>
                            전체 등급 WATCH 상한
                            {cboePcr.pcr_latest != null && <span style={{ marginLeft: 6 }}>PCR {Number(cboePcr.pcr_latest).toFixed(2)}</span>}
                            {cboePcr.panic_reason && <span style={{ marginLeft: 6 }}>({cboePcr.panic_reason})</span>}
                        </div>
                    </div>
                </div>
            )}

            {/* 프로그램 매도 폭탄 배너 */}
            {sellBomb && (
                <div style={{
                    padding: "10px 20px",
                    background: "rgba(239,68,68,0.12)",
                    borderBottom: "2px solid #EF4444",
                    display: "flex", alignItems: "center", gap: 10,
                }}>
                    <span style={{ fontSize: 18 }}>{"\uD83D\uDEA8"}</span>
                    <div style={{ flex: 1 }}>
                        <span style={{ color: "#EF4444", fontSize: 12, fontWeight: 800, fontFamily: font }}>
                            SELL BOMB — 프로그램 매도 폭탄
                        </span>
                        <div style={{ color: "#888", fontSize: 10, marginTop: 2, fontFamily: font }}>
                            비차익 {(prog.non_arb_net_bn || 0).toLocaleString()}억 / 총 {(prog.total_net_bn || 0).toLocaleString()}억
                            {prog.sell_bomb_reason && <span style={{ marginLeft: 6 }}>({prog.sell_bomb_reason})</span>}
                        </div>
                    </div>
                </div>
            )}

            {/* 헤더 */}
            <div style={{ padding: "16px 20px 8px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ color: "#fff", fontSize: 16, fontWeight: 800, fontFamily: font }}>Verity Brain {isUS ? "US" : ""}</span>
                    <span style={{ color: "#333", fontSize: 10, background: "#0D1A00", border: "1px solid #1A2A00", borderRadius: 4, padding: "2px 6px", fontWeight: 700 }}>
                        AI CORE
                    </span>
                </div>
                <div style={{ display: "flex", flexDirection: "column" as const, alignItems: "flex-end", gap: 2 }}>
                    <span style={{ color: "#444", fontSize: 10, fontFamily: font }}>
                        {data.updated_at ? new Date(data.updated_at).toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : ""}
                    </span>
                    {(() => {
                        const s = stalenessInfo(data?.updated_at)
                        if (!s.label) return null
                        return (
                            <span style={{ color: s.color, fontSize: 9, fontWeight: s.stale ? 800 : 500, fontFamily: font }}>
                                {s.label}
                            </span>
                        )
                    })()}
                </div>
            </div>
            {usedMultifactorProxy && (
                <div style={{ padding: "0 20px 10px" }}>
                    <span style={{ color: "#887010", fontSize: 10, fontFamily: font, lineHeight: 1.45 }}>
                        JSON에 verity_brain 블록이 없어 멀티팩터 점수로 대체 표시 중입니다. 파이프라인 산출물을 푸시하면 본래 Brain 집계로 바뀝니다.
                    </span>
                </div>
            )}

            {/* 핵심 게이지 */}
            <div style={{ padding: "8px 20px 16px", display: "flex", alignItems: "center", gap: 16, justifyContent: "center" }}>
                <RingGauge value={avgBrain} color={brainColor} size={110} label="종합" />
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    <div style={{ display: "flex", gap: 16 }}>
                        <RingGauge value={avgFact} color={factColor} size={72} label="팩트" />
                        <RingGauge value={avgSent} color={sentColor} size={72} label="심리" />
                    </div>
                    <div style={{
                        display: "flex", alignItems: "center", gap: 8,
                        background: avgVci > 15 ? "rgba(181,255,25,0.06)" : avgVci < -15 ? "rgba(255,77,77,0.06)" : "#111",
                        borderRadius: 8, padding: "8px 12px",
                        border: `1px solid ${vciColor}30`,
                    }}>
                        <span style={{ color: "#666", fontSize: 10, fontWeight: 600 }}>VCI</span>
                        <span style={{ color: vciColor, fontSize: 18, fontWeight: 900 }}>
                            {avgVci >= 0 ? "+" : ""}{avgVci.toFixed(1)}
                        </span>
                        <span style={{ color: "#666", fontSize: 10 }}>
                            {avgVci > 15 ? "역발상 매수" : avgVci < -15 ? "역발상 매도" : "균형"}
                        </span>
                    </div>
                </div>
            </div>

            {/* 시장 구조 상태줄 — KR 모드에서 항상 표시 */}
            {!isUS && (
                <div style={{
                    margin: "0 16px 12px",
                    background: "#0D0D0D",
                    border: "1px solid #1A1A1A",
                    borderRadius: 10,
                    padding: "10px 14px",
                    display: "flex", alignItems: "center", gap: 10,
                }}>
                    {/* 만기일 */}
                    <div style={{ display: "flex", alignItems: "center", gap: 6, flex: 1 }}>
                        {(() => {
                            const watchColors: Record<string, string> = { FULL_WATCH: "#EF4444", CAUTION: "#F59E0B", NORMAL: "#22C55E" }
                            const watchLabels: Record<string, string> = { FULL_WATCH: "관망", CAUTION: "주의", NORMAL: "정상" }
                            const wc = watchColors[expiryWatch] || "#555"
                            return (
                                <>
                                    <span style={{ width: 7, height: 7, borderRadius: 4, background: wc, flexShrink: 0 }} />
                                    <span style={{ color: "#888", fontSize: 10, fontWeight: 600, fontFamily: font }}>만기</span>
                                    <span style={{ color: wc, fontSize: 11, fontWeight: 800, fontFamily: font }}>
                                        {hasExpiry ? (watchLabels[expiryWatch] || expiryWatch) : "대기"}
                                    </span>
                                    {hasExpiry && expiry.days_to_kr_option != null && (
                                        <span style={{ color: "#444", fontSize: 9, fontFamily: font }}>
                                            D-{expiry.days_to_kr_option}
                                            {expiry.next_kr_option ? ` (${expiry.next_kr_option.slice(5)})` : ""}
                                        </span>
                                    )}
                                    {hasExpiry && expiryWatch !== "NORMAL" && expiryReason && (
                                        <span style={{ color: wc, fontSize: 9, fontFamily: font, opacity: 0.7 }}>
                                            {expiryReason}
                                        </span>
                                    )}
                                </>
                            )
                        })()}
                    </div>

                    <div style={{ width: 1, height: 20, background: "#222", flexShrink: 0 }} />

                    {/* 프로그램 매매 */}
                    <div style={{ display: "flex", alignItems: "center", gap: 6, flex: 1 }}>
                        {(() => {
                            const progColors: Record<string, string> = {
                                SELL_BOMB: "#EF4444", STRONG_SELL_PRESSURE: "#EF4444",
                                SELL_PRESSURE: "#F59E0B", NEUTRAL: "#555",
                                BUY_PRESSURE: "#22C55E", STRONG_BUY_PRESSURE: "#B5FF19",
                            }
                            const progLabels: Record<string, string> = {
                                SELL_BOMB: "매도폭탄", STRONG_SELL_PRESSURE: "강매도",
                                SELL_PRESSURE: "매도우세", NEUTRAL: "중립",
                                BUY_PRESSURE: "매수우세", STRONG_BUY_PRESSURE: "강매수",
                            }
                            const pc = progColors[progSignal] || "#555"
                            return (
                                <>
                                    <span style={{ width: 7, height: 7, borderRadius: 4, background: pc, flexShrink: 0 }} />
                                    <span style={{ color: "#888", fontSize: 10, fontWeight: 600, fontFamily: font }}>수급</span>
                                    <span style={{ color: pc, fontSize: 11, fontWeight: 800, fontFamily: font }}>
                                        {progOk ? (progLabels[progSignal] || progSignal) : "대기"}
                                    </span>
                                    {progOk && prog.total_net_bn != null && (
                                        <span style={{ color: "#444", fontSize: 9, fontFamily: font }}>
                                            {prog.total_net_bn >= 0 ? "+" : ""}{Number(prog.total_net_bn).toLocaleString()}억
                                        </span>
                                    )}
                                </>
                            )
                        })()}
                    </div>
                </div>
            )}

            {/* 등급 분포 바 */}
            <div style={{ padding: "0 20px 12px" }}>
                <div style={{ display: "flex", height: 10, borderRadius: 5, overflow: "hidden", background: "#1A1A1A" }}>
                    {gradeOrder
                        .filter((g) => (gradeDist[g] || 0) > 0)
                        .map((g) => {
                            const pct = ((gradeDist[g] || 0) / totalGraded) * 100
                            return (
                                <div key={g} style={{
                                    width: `${pct}%`, background: gradeColors[g] || "#555",
                                    transition: "width 0.5s ease",
                                }} />
                            )
                        })}
                </div>
                <div style={{ display: "flex", justifyContent: "center", gap: 12, marginTop: 8 }}>
                    {gradeOrder
                        .filter((g) => (gradeDist[g] || 0) > 0)
                        .map((g) => (
                            <div key={g} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                                <span style={{ width: 8, height: 8, borderRadius: 4, background: gradeColors[g] || "#555", display: "inline-block" }} />
                                <span style={{ color: "#888", fontSize: 10, fontFamily: font }}>
                                    {gradeLabels[g] || g} {gradeDist[g]}
                                </span>
                            </div>
                        ))}
                </div>
            </div>

            {/* 탭 */}
            <div style={{ display: "flex", borderTop: "1px solid #222", borderBottom: "1px solid #222" }}>
                {(["overview", "stocks", "redflags"] as const).map((t) => {
                    const labels: Record<string, string> = { overview: "탑픽", stocks: `전체 ${recs.length}`, redflags: `위험 ${redFlagStocks.length}` }
                    return (
                        <button key={t} onClick={() => setTab(t)} style={{
                            flex: 1, padding: "10px 0", background: "none", border: "none",
                            borderBottom: tab === t ? "2px solid #B5FF19" : "2px solid transparent",
                            color: tab === t ? "#B5FF19" : "#666",
                            fontSize: 12, fontWeight: 600, fontFamily: font, cursor: "pointer",
                        }}>
                            {labels[t]}
                        </button>
                    )
                })}
            </div>

            {/* 탑픽 */}
            {tab === "overview" && (
                <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
                    {topPicks.length === 0 && (
                        <div style={{ color: "#555", fontSize: 12, textAlign: "center", padding: 16 }}>
                            탑픽 종목이 없습니다
                        </div>
                    )}
                    {topPicks.map((s: any, i: number) => {
                        const gc = gradeColors[s.grade] || "#888"
                        const pickBrain = s.brain_score ?? s.score ?? 0
                        const pickVci = Number(s.vci ?? 0)
                        return (
                            <div key={s.ticker || i} style={stockRow}>
                                <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1 }}>
                                    <span style={{ ...gradeBadge, background: gc }}>{i + 1}</span>
                                    <div>
                                        <span style={{ color: "#fff", fontSize: 13, fontWeight: 700 }}>{s.name}</span>
                                        <span style={{ color: "#555", fontSize: 10, marginLeft: 6 }}>{s.ticker}</span>
                                    </div>
                                </div>
                                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 1 }}>
                                        <span style={{ color: gc, fontSize: 16, fontWeight: 900 }}>{pickBrain}</span>
                                        <span style={{ color: "#555", fontSize: 8 }}>
                                            {gradeLabels[s.grade] || s.grade}
                                            {s.grade_confidence === "borderline" && <span style={{ color: "#F59E0B", marginLeft: 2 }}>~</span>}
                                        </span>
                                    </div>
                                    {typeof s.data_coverage === "number" && s.data_coverage < 0.4 && (
                                        <span style={{ color: "#F59E0B", fontSize: 8, fontWeight: 600 }}>⚠ 데이터 부족</span>
                                    )}
                                    <div style={{ width: 1, height: 24, background: "#222" }} />
                                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 1 }}>
                                        <span style={{ color: pickVci >= 0 ? "#B5FF19" : "#FF4D4D", fontSize: 12, fontWeight: 700 }}>
                                            {pickVci >= 0 ? "+" : ""}{pickVci}
                                        </span>
                                        <span style={{ color: "#555", fontSize: 8 }}>VCI</span>
                                    </div>
                                </div>
                            </div>
                        )
                    })}
                </div>
            )}

            {/* 전체 종목 */}
            {tab === "stocks" && (
                <div style={{ padding: "8px 16px", maxHeight: 400, overflowY: "auto" }}>
                    {recsDisplay
                        .filter((s: any) => s?.verity_brain?.brain_score != null)
                        .map((s: any) => {
                        const b = s.verity_brain || {}
                        const bs = b.brain_score
                        const gc = gradeColors[b.grade] || "#888"
                        return (
                            <div key={s.ticker || s.name} style={{ ...stockRow, padding: "8px 10px" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 6, flex: 1, minWidth: 0 }}>
                                    <span style={{ width: 6, height: 6, borderRadius: 3, background: gc, flexShrink: 0 }} />
                                    <span style={{ color: "#ccc", fontSize: 12, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.name}</span>
                                </div>
                                <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
                                    <span style={{ color: gc, fontSize: 13, fontWeight: 800, minWidth: 28, textAlign: "right" }}>{bs}</span>
                                    <span style={{ color: "#555", fontSize: 9, minWidth: 32 }}>
                                        {gradeLabels[b.grade] || b.grade}
                                        {b.grade_confidence === "borderline" && <span style={{ color: "#F59E0B" }}>~</span>}
                                    </span>
                                    <span style={{
                                        color: (b.vci?.vci ?? 0) >= 0 ? "#B5FF19" : "#FF4D4D",
                                        fontSize: 10, fontWeight: 600, minWidth: 32, textAlign: "right",
                                    }}>
                                        {(b.vci?.vci ?? 0) >= 0 ? "+" : ""}{b.vci?.vci ?? 0}
                                    </span>
                                </div>
                            </div>
                        )
                    })}
                </div>
            )}

            {/* 레드플래그 */}
            {tab === "redflags" && (
                <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
                    {redFlagStocks.length === 0 && (
                        <div style={{ color: "#22C55E", fontSize: 12, textAlign: "center", padding: 16 }}>
                            레드플래그 종목 없음 ✅
                        </div>
                    )}
                    {redFlagStocks.map((s: any, i: number) => (
                        <div key={s.ticker || i} style={{ background: "rgba(239,68,68,0.04)", border: "1px solid #2A1515", borderRadius: 10, padding: "10px 12px" }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                                <span style={{ color: "#fff", fontSize: 13, fontWeight: 700 }}>{s.name}</span>
                                <span style={{ color: "#EF4444", fontSize: 12, fontWeight: 800 }}>{gradeLabels[s.grade] || s.grade}</span>
                            </div>
                            {s.flags?.map((f: string, j: number) => (
                                <div key={j} style={{ color: "#FF6B6B", fontSize: 11, lineHeight: "1.5" }}>⛔ {f}</div>
                            ))}
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}

VerityBrainPanel.defaultProps = { dataUrl: DATA_URL, market: "kr" }
addPropertyControls(VerityBrainPanel, {
    dataUrl: { type: ControlType.String, title: "JSON URL", defaultValue: DATA_URL },
    market: { type: ControlType.Enum, title: "Market", options: ["kr", "us"], optionTitles: ["KR 국장", "US 미장"], defaultValue: "kr" },
})

function RingGauge({ value, color, size = 100, label }: { value: number; color: string; size?: number; label: string }) {
    const safeVal = (value != null && !Number.isNaN(Number(value))) ? Math.max(0, Math.min(100, Number(value))) : 0
    const r = (size - 16) / 2
    const s = 7
    const c = 2 * Math.PI * r
    const p = (safeVal / 100) * c
    return (
        <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
            <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1A1A1A" strokeWidth={s} />
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={s}
                    strokeDasharray={c} strokeDashoffset={c - p} strokeLinecap="round"
                    transform={`rotate(-90 ${size / 2} ${size / 2})`}
                    style={{ transition: "stroke-dashoffset 0.6s ease" }} />
            </svg>
            <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                <span style={{ color, fontSize: size > 80 ? 22 : 16, fontWeight: 900 }}>{safeVal}</span>
                <span style={{ color: "#666", fontSize: 9 }}>{label}</span>
            </div>
        </div>
    )
}

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"

const card: React.CSSProperties = {
    width: "100%",
    background: "#0A0A0A",
    borderRadius: 16,
    border: "1px solid #222",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    fontFamily: font,
}

const stockRow: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "10px 12px",
    background: "#111",
    borderRadius: 10,
}

const gradeBadge: React.CSSProperties = {
    width: 24,
    height: 24,
    borderRadius: 6,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#000",
    fontSize: 12,
    fontWeight: 900,
    flexShrink: 0,
}
