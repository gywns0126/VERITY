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
    hoverOverlay: "rgba(255,255,255,0.04)", activeOverlay: "rgba(255,255,255,0.08)",
    focusRing: "rgba(181,255,25,0.35)", scrim: "rgba(0,0,0,0.5)",
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

// WARN-23: updated_at 기준 stale 경고 정보
function stalenessInfo(updatedAt: any): { label: string; color: string; stale: boolean } {
    if (!updatedAt) return { label: "", color: C.textTertiary, stale: false }
    const t = new Date(String(updatedAt)).getTime()
    if (!Number.isFinite(t)) return { label: "", color: C.textTertiary, stale: false }
    const hours = (Date.now() - t) / 3_600_000
    if (hours < 1) return { label: `방금 갱신 (${Math.round(hours * 60)}분 전)`, color: C.success, stale: false }
    if (hours < 3) return { label: `${Math.round(hours)}시간 전`, color: C.accent, stale: false }
    if (hours < 12) return { label: `${Math.round(hours)}시간 전`, color: C.watch, stale: false }
    if (hours < 24) return { label: `${Math.round(hours)}시간 전 (⚠️ stale 경계)`, color: C.caution, stale: true }
    const days = hours / 24
    return { label: `${days.toFixed(1)}일 전 (⚠️ stale)`, color: C.danger, stale: true }
}

const DATA_URL =
    "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"

function _isUS(r: any): boolean {
    return r?.currency === "USD" || /NYSE|NASDAQ|AMEX|NMS|NGM|NCM|ARCA/i.test(r?.market || "")
}

// Brain Audit §8: AVOID 라벨 의미 재정의 — 펀더멘털 결함 전용
const AVOID_TOOLTIP =
    "AVOID 부여 조건: 펀더멘털 결함 (감사거절·분식회계·상폐 위험 등 has_critical) 또는 매크로 위기 cap. " +
    "단순 저점수는 CAUTION으로 표시됨."

// §11~§14 audit overrides 라벨 매핑
const OVERRIDE_LABELS: Record<string, string> = {
    contrarian_upgrade: "역발상↑",
    quadrant_unfavored: "분면불리↓",
    cape_bubble: "CAPE버블cap",
    panic_stage_3: "패닉3cap",
    panic_stage_4: "패닉4cap",
    vix_spread_panic: "VIX패닉cap",
    yield_defense: "수익률방어cap",
    sector_quadrant_drift: "섹터드리프트",
    ai_upside_relax: "AI호재완화",
}

function formatOverrides(overrides: any): string[] {
    if (!Array.isArray(overrides)) return []
    return overrides.map((o) => OVERRIDE_LABELS[o] || o)
}

// red_flags.{auto_avoid,downgrade}_detail freshness 표기
function formatRedFlagDetail(d: any): string {
    if (!d || typeof d !== "object") return String(d || "")
    const text = d.text || d.toString()
    const fresh = d.freshness
    if (!fresh || fresh === "FRESH") return text
    const days = d.days_since_event != null ? `${d.days_since_event}d` : ""
    const tag = fresh === "EXPIRED" ? "EXPIRED" : "STALE"
    return `${text} [${tag}${days ? " " + days : ""}]`
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
            overrides_applied: Array.isArray(s.overrides_applied) ? s.overrides_applied : [],
            score_breakdown: s.score_breakdown || null,
        }))
    const redFlagStocks = withBrain
        .filter((s) => {
            const rf = s.verity_brain.red_flags || {}
            return rf.has_critical || (Number(rf.downgrade_count) || 0) >= 2
        })
        .map((s) => {
            const rf = s.verity_brain.red_flags || {}
            // §U-3 freshness — *_detail 우선, 없으면 plain string fallback
            const aaDetail = Array.isArray(rf.auto_avoid_detail) ? rf.auto_avoid_detail : null
            const dgDetail = Array.isArray(rf.downgrade_detail) ? rf.downgrade_detail : null
            const flags = aaDetail || dgDetail
                ? [...(aaDetail || []), ...(dgDetail || [])].map(formatRedFlagDetail)
                : [...(rf.auto_avoid || []), ...(rf.downgrade || [])]
            return {
                ticker: s.ticker,
                name: s.name,
                grade: s.verity_brain.grade,
                flags,
                overrides_applied: Array.isArray(s.overrides_applied) ? s.overrides_applied : [],
            }
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
            <div style={{ ...card, minHeight: 200, alignItems: "center", justifyContent: "center", gap: S.md }}>
                <span style={{ color: C.danger, fontSize: T.body, fontFamily: FONT }}>데이터 로드 실패: {error}</span>
                <button
                    onClick={() => loadData()}
                    style={{
                        background: "none", border: `1px solid ${C.border}`, borderRadius: R.md,
                        color: C.accent, fontSize: T.cap, fontFamily: FONT, padding: `${S.sm}px ${S.lg}px`,
                        cursor: "pointer", transition: X.fast,
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
                <span style={{ color: C.textTertiary, fontSize: T.body, fontFamily: FONT }}>Brain 데이터 로딩 중...</span>
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
            <div style={{ ...card, minHeight: 160, alignItems: "center", justifyContent: "center", padding: `0 ${S.xl}px` }}>
                <span style={{ color: C.textTertiary, fontSize: T.body, fontFamily: FONT, textAlign: "center", lineHeight: T.lh_normal }}>
                    Verity Brain 집계가 없습니다. 파이프라인 실행 후 배포된 portfolio.json에 시장 집계
                    (verity_brain.market_brain)가 들어 있는지, Framer의 JSON URL이 그 파일을 가리키는지 확인하세요.
                </span>
            </div>
        )
    }

    const brainColor = avgBrain >= 65 ? C.accent : avgBrain >= 45 ? C.watch : C.danger
    const factColor = _rawFact == null ? C.textTertiary : avgFact >= 65 ? C.success : avgFact >= 45 ? C.watch : C.danger
    const sentColor = _rawSent == null ? C.textTertiary : avgSent >= 65 ? C.info : avgSent >= 45 ? C.watch : C.danger
    const vciColor = avgVci > 15 ? C.accent : avgVci < -15 ? C.danger : C.textSecondary

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
                    padding: `${S.md}px ${S.xl}px`,
                    background: panicActive ? "rgba(239,68,68,0.1)" : yieldDefActive ? "rgba(56,189,248,0.1)" : "rgba(234,179,8,0.1)",
                    borderBottom: `2px solid ${panicActive ? C.danger : yieldDefActive ? "#38BDF8" : "#EAB308"}`,
                    boxShadow: panicActive ? G.danger : "none",
                    display: "flex", alignItems: "center", gap: S.md,
                }}>
                    <span style={{ fontSize: 20 }}>{panicActive ? "🚨" : yieldDefActive ? "🛡️" : "⚠️"}</span>
                    <div>
                        <span style={{
                            color: panicActive ? C.danger : yieldDefActive ? "#38BDF8" : "#EAB308",
                            fontSize: T.body, fontWeight: T.w_black,
                        }}>
                            {panicActive ? "PANIC MODE — 신규 매수 제한" : yieldDefActive ? "YIELD DEFENSE — 금리 방패 (관망 상한)" : "EUPHORIA MODE — 과열 경계"}
                        </span>
                        <div style={{ color: C.textSecondary, fontSize: T.cap, marginTop: 2 }}>
                            {macroOv.reason || macroOv.message || "매크로 오버라이드 활성"}
                        </div>
                    </div>
                </div>
            )}

            {/* 만기일 관망 배너 */}
            {expiryWatch !== "NORMAL" && (
                <div style={{
                    padding: `${S.md}px ${S.xl}px`,
                    background: expiryWatch === "FULL_WATCH" ? "rgba(239,68,68,0.08)" : "rgba(245,158,11,0.08)",
                    borderBottom: `2px solid ${expiryWatch === "FULL_WATCH" ? C.danger : C.caution}`,
                    display: "flex", alignItems: "center", gap: S.md,
                }}>
                    <span style={{ fontSize: 18 }}>{expiryWatch === "FULL_WATCH" ? "\u26A0\uFE0F" : "\u23F3"}</span>
                    <div style={{ flex: 1 }}>
                        <span style={{
                            color: expiryWatch === "FULL_WATCH" ? C.danger : C.caution,
                            fontSize: T.body, fontWeight: T.w_black, fontFamily: FONT,
                        }}>
                            {expiryWatch === "FULL_WATCH" ? "FULL WATCH" : "CAUTION"} — {expiryReason}
                        </span>
                        <div style={{ color: C.textTertiary, fontSize: T.cap, marginTop: 2, fontFamily: FONT }}>
                            {expiryWatch === "FULL_WATCH"
                                ? "추격매수 완전 차단 / BUY → WATCH 강등"
                                : "신규 진입 자제 / 포지션 한도 50%"}
                            {expiry.days_to_kr_option != null && (
                                <span style={{ marginLeft: S.sm, color: C.textTertiary, ...MONO }}>
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
                    padding: `${S.md}px ${S.xl}px`,
                    background: "rgba(239,68,68,0.1)",
                    borderBottom: `2px solid ${C.danger}`,
                    boxShadow: G.danger,
                    display: "flex", alignItems: "center", gap: S.md,
                }}>
                    <span style={{ fontSize: 18 }}>{"\uD83D\uDEA8"}</span>
                    <div style={{ flex: 1 }}>
                        <span style={{ color: C.danger, fontSize: T.body, fontWeight: T.w_black, fontFamily: FONT }}>
                            CBOE PCR PANIC — 풋/콜 비율 극단
                        </span>
                        <div style={{ color: C.textSecondary, fontSize: T.cap, marginTop: 2, fontFamily: FONT }}>
                            전체 등급 WATCH 상한
                            {cboePcr.pcr_latest != null && <span style={{ marginLeft: S.xs, ...MONO }}>PCR {Number(cboePcr.pcr_latest).toFixed(2)}</span>}
                            {cboePcr.panic_reason && <span style={{ marginLeft: S.xs }}>({cboePcr.panic_reason})</span>}
                        </div>
                    </div>
                </div>
            )}

            {/* 프로그램 매도 폭탄 배너 */}
            {sellBomb && (
                <div style={{
                    padding: `${S.md}px ${S.xl}px`,
                    background: "rgba(239,68,68,0.12)",
                    borderBottom: `2px solid ${C.danger}`,
                    boxShadow: G.danger,
                    display: "flex", alignItems: "center", gap: S.md,
                }}>
                    <span style={{ fontSize: 18 }}>{"\uD83D\uDEA8"}</span>
                    <div style={{ flex: 1 }}>
                        <span style={{ color: C.danger, fontSize: T.body, fontWeight: T.w_black, fontFamily: FONT }}>
                            SELL BOMB — 프로그램 매도 폭탄
                        </span>
                        <div style={{ color: C.textSecondary, fontSize: T.cap, marginTop: 2, fontFamily: FONT }}>
                            비차익 <span style={MONO}>{(prog.non_arb_net_bn || 0).toLocaleString()}</span>억 / 총 <span style={MONO}>{(prog.total_net_bn || 0).toLocaleString()}</span>억
                            {prog.sell_bomb_reason && <span style={{ marginLeft: S.xs }}>({prog.sell_bomb_reason})</span>}
                        </div>
                    </div>
                </div>
            )}

            {/* 헤더 */}
            <div style={{ padding: `${S.lg}px ${S.xl}px ${S.sm}px`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ display: "flex", alignItems: "center", gap: S.md }}>
                    <span style={{ color: C.textPrimary, fontSize: T.sub, fontWeight: T.w_black, fontFamily: FONT }}>Verity Brain {isUS ? "US" : ""}</span>
                    <span style={{ color: C.accent, fontSize: T.cap, background: C.accentSoft, border: `1px solid ${C.accent}40`, borderRadius: R.sm, padding: `2px ${S.sm}px`, fontWeight: T.w_bold, fontFamily: FONT_MONO, letterSpacing: "0.05em" }}>
                        AI CORE
                    </span>
                </div>
                <div style={{ display: "flex", flexDirection: "column" as const, alignItems: "flex-end", gap: 2 }}>
                    <span style={{ color: C.textTertiary, fontSize: T.cap, fontFamily: FONT_MONO }}>
                        {data.updated_at ? new Date(data.updated_at).toLocaleString("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : ""}
                    </span>
                    {(() => {
                        const s = stalenessInfo(data?.updated_at)
                        if (!s.label) return null
                        return (
                            <span style={{ color: s.color, fontSize: T.cap, fontWeight: s.stale ? T.w_black : T.w_med, fontFamily: FONT }}>
                                {s.label}
                            </span>
                        )
                    })()}
                </div>
            </div>
            {usedMultifactorProxy && (
                <div style={{ padding: `0 ${S.xl}px ${S.md}px` }}>
                    <span style={{ color: C.watch, fontSize: T.cap, fontFamily: FONT, lineHeight: T.lh_normal }}>
                        JSON에 verity_brain 블록이 없어 멀티팩터 점수로 대체 표시 중입니다. 파이프라인 산출물을 푸시하면 본래 Brain 집계로 바뀝니다.
                    </span>
                </div>
            )}

            {/* 핵심 게이지 */}
            <div style={{ padding: `${S.sm}px ${S.xl}px ${S.lg}px`, display: "flex", alignItems: "center", gap: S.lg, justifyContent: "center" }}>
                <RingGauge value={avgBrain} color={brainColor} size={110} label="종합" />
                <div style={{ display: "flex", flexDirection: "column", gap: S.md }}>
                    <div style={{ display: "flex", gap: S.lg }}>
                        <RingGauge value={avgFact} color={factColor} size={72} label="팩트" />
                        <RingGauge value={avgSent} color={sentColor} size={72} label="심리" />
                    </div>
                    <div style={{
                        display: "flex", alignItems: "center", gap: S.sm,
                        background: avgVci > 15 ? C.accentSoft : avgVci < -15 ? "rgba(239,68,68,0.08)" : C.bgElevated,
                        borderRadius: R.md, padding: `${S.sm}px ${S.md}px`,
                        border: `1px solid ${vciColor}30`,
                    }}>
                        <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: T.w_semi, fontFamily: FONT_MONO, letterSpacing: "0.05em" }}>VCI</span>
                        <span style={{ color: vciColor, fontSize: T.title, fontWeight: T.w_black, ...MONO }}>
                            {avgVci >= 0 ? "+" : ""}{avgVci.toFixed(1)}
                        </span>
                        <span style={{ color: C.textTertiary, fontSize: T.cap }}>
                            {avgVci > 15 ? "역발상 매수" : avgVci < -15 ? "역발상 매도" : "균형"}
                        </span>
                    </div>
                </div>
            </div>

            {/* 시장 구조 상태줄 — KR 모드에서 항상 표시 */}
            {!isUS && (
                <div style={{
                    margin: `0 ${S.lg}px ${S.md}px`,
                    background: C.bgElevated,
                    border: `1px solid ${C.border}`,
                    borderRadius: R.md,
                    padding: `${S.sm}px ${S.md}px`,
                    display: "flex", alignItems: "center", gap: S.md,
                }}>
                    {/* 만기일 */}
                    <div style={{ display: "flex", alignItems: "center", gap: S.sm, flex: 1 }}>
                        {(() => {
                            const watchColors: Record<string, string> = { FULL_WATCH: C.danger, CAUTION: C.caution, NORMAL: C.success }
                            const watchLabels: Record<string, string> = { FULL_WATCH: "관망", CAUTION: "주의", NORMAL: "정상" }
                            const wc = watchColors[expiryWatch] || C.textTertiary
                            return (
                                <>
                                    <span style={{ width: 7, height: 7, borderRadius: 6, background: wc, flexShrink: 0 }} />
                                    <span style={{ color: C.textSecondary, fontSize: T.cap, fontWeight: T.w_semi, fontFamily: FONT }}>만기</span>
                                    <span style={{ color: wc, fontSize: T.cap, fontWeight: T.w_black, fontFamily: FONT }}>
                                        {hasExpiry ? (watchLabels[expiryWatch] || expiryWatch) : "대기"}
                                    </span>
                                    {hasExpiry && expiry.days_to_kr_option != null && (
                                        <span style={{ color: C.textTertiary, fontSize: T.cap, fontFamily: FONT_MONO }}>
                                            D-{expiry.days_to_kr_option}
                                            {expiry.next_kr_option ? ` (${expiry.next_kr_option.slice(5)})` : ""}
                                        </span>
                                    )}
                                    {hasExpiry && expiryWatch !== "NORMAL" && expiryReason && (
                                        <span style={{ color: wc, fontSize: T.cap, fontFamily: FONT, opacity: 0.7 }}>
                                            {expiryReason}
                                        </span>
                                    )}
                                </>
                            )
                        })()}
                    </div>

                    <div style={{ width: 1, height: 20, background: C.border, flexShrink: 0 }} />

                    {/* 프로그램 매매 */}
                    <div style={{ display: "flex", alignItems: "center", gap: S.sm, flex: 1 }}>
                        {(() => {
                            const progColors: Record<string, string> = {
                                SELL_BOMB: C.danger, STRONG_SELL_PRESSURE: C.danger,
                                SELL_PRESSURE: C.caution, NEUTRAL: C.textTertiary,
                                BUY_PRESSURE: C.success, STRONG_BUY_PRESSURE: C.accent,
                            }
                            const progLabels: Record<string, string> = {
                                SELL_BOMB: "매도폭탄", STRONG_SELL_PRESSURE: "강매도",
                                SELL_PRESSURE: "매도우세", NEUTRAL: "중립",
                                BUY_PRESSURE: "매수우세", STRONG_BUY_PRESSURE: "강매수",
                            }
                            const pc = progColors[progSignal] || C.textTertiary
                            return (
                                <>
                                    <span style={{ width: 7, height: 7, borderRadius: 6, background: pc, flexShrink: 0 }} />
                                    <span style={{ color: C.textSecondary, fontSize: T.cap, fontWeight: T.w_semi, fontFamily: FONT }}>수급</span>
                                    <span style={{ color: pc, fontSize: T.cap, fontWeight: T.w_black, fontFamily: FONT }}>
                                        {progOk ? (progLabels[progSignal] || progSignal) : "대기"}
                                    </span>
                                    {progOk && prog.total_net_bn != null && (
                                        <span style={{ color: C.textTertiary, fontSize: T.cap, fontFamily: FONT_MONO }}>
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
            <div style={{ padding: `0 ${S.xl}px ${S.md}px` }}>
                <div style={{ display: "flex", height: 10, borderRadius: R.sm, overflow: "hidden", background: C.bgElevated }}>
                    {gradeOrder
                        .filter((g) => (gradeDist[g] || 0) > 0)
                        .map((g) => {
                            const pct = ((gradeDist[g] || 0) / totalGraded) * 100
                            return (
                                <div key={g} style={{
                                    width: `${pct}%`, background: gradeColors[g] || C.textTertiary,
                                    transition: "width 0.5s ease",
                                }} />
                            )
                        })}
                </div>
                <div style={{ display: "flex", justifyContent: "center", gap: S.md, marginTop: S.sm }}>
                    {gradeOrder
                        .filter((g) => (gradeDist[g] || 0) > 0)
                        .map((g) => (
                            <div key={g} style={{ display: "flex", alignItems: "center", gap: S.xs }}>
                                <span style={{ width: 8, height: 8, borderRadius: 6, background: gradeColors[g] || C.textTertiary, display: "inline-block" }} />
                                <span style={{ color: C.textSecondary, fontSize: T.cap, fontFamily: FONT }}>
                                    {gradeLabels[g] || g} <span style={MONO}>{gradeDist[g]}</span>
                                </span>
                            </div>
                        ))}
                </div>
            </div>

            {/* 탭 */}
            <div style={{ display: "flex", borderTop: `1px solid ${C.border}`, borderBottom: `1px solid ${C.border}` }}>
                {(["overview", "stocks", "redflags"] as const).map((t) => {
                    const labels: Record<string, string> = { overview: "탑픽", stocks: `전체 ${recs.length}`, redflags: `위험 ${redFlagStocks.length}` }
                    const active = tab === t
                    return (
                        <button key={t} onClick={() => setTab(t)} style={{
                            flex: 1, padding: `${S.md}px 0`, background: "none", border: "none",
                            borderBottom: active ? `2px solid ${C.accent}` : "2px solid transparent",
                            color: active ? C.accent : C.textTertiary,
                            fontSize: T.body, fontWeight: T.w_semi, fontFamily: FONT, cursor: "pointer",
                            textShadow: active ? `0 0 8px rgba(181,255,25,0.4)` : "none",
                            transition: X.fast,
                        }}>
                            {labels[t]}
                        </button>
                    )
                })}
            </div>

            {/* 탑픽 */}
            {tab === "overview" && (
                <div style={{ padding: `${S.md}px ${S.lg}px`, display: "flex", flexDirection: "column", gap: S.sm }}>
                    {topPicks.length === 0 && (
                        <div style={{ color: C.textTertiary, fontSize: T.body, textAlign: "center", padding: S.lg }}>
                            탑픽 종목이 없습니다
                        </div>
                    )}
                    {topPicks.map((s: any, i: number) => {
                        const gc = gradeColors[s.grade] || C.textSecondary
                        const pickBrain = s.brain_score ?? s.score ?? 0
                        const pickVci = Number(s.vci ?? 0)
                        return (
                            <div key={s.ticker || i} style={stockRow}>
                                <div style={{ display: "flex", alignItems: "center", gap: S.sm, flex: 1 }}>
                                    <span style={{ ...gradeBadge, background: gc }}>{i + 1}</span>
                                    <div>
                                        <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_bold }}>{s.name}</span>
                                        <span style={{ color: C.textTertiary, fontSize: T.cap, marginLeft: S.sm, fontFamily: FONT_MONO }}>{s.ticker}</span>
                                    </div>
                                </div>
                                <div style={{ display: "flex", alignItems: "center", gap: S.md }}>
                                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 1 }}>
                                        <span style={{ color: gc, fontSize: T.sub, fontWeight: T.w_black, ...MONO }}>{pickBrain}</span>
                                        <span
                                            style={{ color: C.textTertiary, fontSize: T.cap, cursor: s.grade === "AVOID" ? "help" : "default" }}
                                            title={s.grade === "AVOID" ? AVOID_TOOLTIP : undefined}
                                        >
                                            {gradeLabels[s.grade] || s.grade}
                                            {s.grade_confidence === "borderline" && <span style={{ color: C.caution, marginLeft: 2 }}>~</span>}
                                        </span>
                                        {Array.isArray(s.overrides_applied) && s.overrides_applied.length > 0 && (
                                            <span style={{ color: "#7DD3FC", fontSize: T.cap, fontWeight: T.w_semi }} title="overrides_applied (audit)">
                                                {formatOverrides(s.overrides_applied).slice(0, 2).join(" · ")}
                                            </span>
                                        )}
                                    </div>
                                    {typeof s.data_coverage === "number" && s.data_coverage < 0.4 && (
                                        <span style={{ color: C.caution, fontSize: T.cap, fontWeight: T.w_semi }}>⚠ 데이터 부족</span>
                                    )}
                                    <div style={{ width: 1, height: 24, background: C.border }} />
                                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 1 }}>
                                        <span style={{ color: pickVci >= 0 ? C.accent : C.danger, fontSize: T.body, fontWeight: T.w_bold, ...MONO }}>
                                            {pickVci >= 0 ? "+" : ""}{pickVci}
                                        </span>
                                        <span style={{ color: C.textTertiary, fontSize: T.cap, fontFamily: FONT_MONO, letterSpacing: "0.05em" }}>VCI</span>
                                    </div>
                                </div>
                            </div>
                        )
                    })}
                </div>
            )}

            {/* 전체 종목 */}
            {tab === "stocks" && (
                <div style={{ padding: `${S.sm}px ${S.lg}px`, maxHeight: 400, overflowY: "auto" }}>
                    {recsDisplay
                        .filter((s: any) => s?.verity_brain?.brain_score != null)
                        .map((s: any) => {
                        const b = s.verity_brain || {}
                        const bs = b.brain_score
                        const gc = gradeColors[b.grade] || C.textSecondary
                        return (
                            <div key={s.ticker || s.name} style={{ ...stockRow, padding: `${S.sm}px ${S.md}px` }}>
                                <div style={{ display: "flex", alignItems: "center", gap: S.sm, flex: 1, minWidth: 0 }}>
                                    <span style={{ width: 6, height: 6, borderRadius: 3, background: gc, flexShrink: 0 }} />
                                    <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.name}</span>
                                </div>
                                <div style={{ display: "flex", gap: S.sm, alignItems: "center", flexShrink: 0 }}>
                                    <span style={{ color: gc, fontSize: T.body, fontWeight: T.w_black, minWidth: 28, textAlign: "right", ...MONO }}>{bs}</span>
                                    <span
                                        style={{ color: C.textTertiary, fontSize: T.cap, minWidth: 32, cursor: b.grade === "AVOID" ? "help" : "default" }}
                                        title={b.grade === "AVOID" ? AVOID_TOOLTIP : undefined}
                                    >
                                        {gradeLabels[b.grade] || b.grade}
                                        {b.grade_confidence === "borderline" && <span style={{ color: C.caution }}>~</span>}
                                    </span>
                                    <span style={{
                                        color: (b.vci?.vci ?? 0) >= 0 ? C.accent : C.danger,
                                        fontSize: T.cap, fontWeight: T.w_semi, minWidth: 32, textAlign: "right",
                                        ...MONO,
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
                <div style={{ padding: `${S.md}px ${S.lg}px`, display: "flex", flexDirection: "column", gap: S.sm }}>
                    {redFlagStocks.length === 0 && (
                        <div style={{ color: C.success, fontSize: T.body, textAlign: "center", padding: S.lg }}>
                            레드플래그 종목 없음 ✅
                        </div>
                    )}
                    {redFlagStocks.map((s: any, i: number) => (
                        <div key={s.ticker || i} style={{ background: "rgba(239,68,68,0.04)", border: `1px solid rgba(239,68,68,0.20)`, borderRadius: R.md, padding: `${S.md}px ${S.lg}px` }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: S.sm }}>
                                <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_bold }}>{s.name}</span>
                                <span
                                    style={{ color: C.danger, fontSize: T.body, fontWeight: T.w_black, cursor: s.grade === "AVOID" ? "help" : "default" }}
                                    title={s.grade === "AVOID" ? AVOID_TOOLTIP : undefined}
                                >
                                    {gradeLabels[s.grade] || s.grade}
                                </span>
                            </div>
                            {s.flags?.map((f: string, j: number) => (
                                <div key={j} style={{ color: "#FF6B6B", fontSize: T.cap, lineHeight: T.lh_normal }}>⛔ {f}</div>
                            ))}
                            {Array.isArray(s.overrides_applied) && s.overrides_applied.length > 0 && (
                                <div style={{ marginTop: S.xs, color: "#7DD3FC", fontSize: T.cap, fontWeight: T.w_semi }}>
                                    overrides: {formatOverrides(s.overrides_applied).join(" · ")}
                                </div>
                            )}
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
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={C.bgElevated} strokeWidth={s} />
                <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={s}
                    strokeDasharray={c} strokeDashoffset={c - p} strokeLinecap="round"
                    transform={`rotate(-90 ${size / 2} ${size / 2})`}
                    style={{ transition: "stroke-dashoffset 0.6s ease" }} />
            </svg>
            <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                <span style={{ color, fontSize: size > 80 ? T.h2 : T.sub, fontWeight: T.w_black, ...MONO }}>{safeVal}</span>
                <span style={{ color: C.textTertiary, fontSize: T.cap, fontFamily: FONT_MONO, letterSpacing: "0.05em" }}>{label}</span>
            </div>
        </div>
    )
}

const card: React.CSSProperties = {
    width: "100%",
    background: C.bgPage,
    borderRadius: R.lg,
    border: `1px solid ${C.border}`,
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    fontFamily: FONT,
    color: C.textPrimary,
}

const stockRow: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: `${S.md}px ${S.lg}px`,
    background: C.bgElevated,
    borderRadius: R.md,
}

const gradeBadge: React.CSSProperties = {
    width: 24,
    height: 24,
    borderRadius: R.sm,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#000",
    fontSize: T.body,
    fontWeight: T.w_black,
    flexShrink: 0,
    fontFamily: FONT_MONO,
}
