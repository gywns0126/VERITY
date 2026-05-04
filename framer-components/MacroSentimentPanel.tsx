/**
 * ⚠️ DEPRECATED (2026-05-05 Plan v0.1 §3 [Macro] 폐기 결정)
 *
 * MacroHub 가 market_fear_greed / cftc_cot / fund_flows 직접 fetch + sentiment 통합
 *
 * Framer 페이지에서 인스턴스 제거. 추후 일괄 cleanup commit 시 git rm.
 *
 * ────────────────────────────────────────────────────────────
 */
import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"

const DATA_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json"

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
/* ◆ DESIGN TOKENS END ◆ */

const font = FONT
// 시장 심리 지표 — 일반 신호 컨벤션 (양수=긍정 초록, 음수=부정 빨강).
// 한국 주식 등락률 (UP=빨강, DOWN=파랑) 과는 별개 컨텍스트.
const BG = C.bgPage
const CARD = C.bgElevated
const BORDER = C.border
const MUTED = C.textSecondary
const UP = C.success
const DOWN = C.danger
const WARN = C.warn
const ACCENT = C.accent
const BLUE = C.info
const PURPLE = "#A855F7"

const SIGNAL_COLOR: Record<string, string> = {
    EXTREME_GREED: DOWN,
    GREED: "#F97316",
    NEUTRAL: MUTED,
    FEAR: BLUE,
    EXTREME_FEAR: PURPLE,
    BULLISH: UP,
    STRONG_BULLISH: UP,
    BEARISH: DOWN,
    STRONG_BEARISH: DOWN,
    MIXED: MUTED,
    RISK_ON: UP,
    RISK_OFF: DOWN,
    DEFENSIVE: BLUE,
    CASH_FLIGHT: PURPLE,
    STRONG_INFLOW: UP,
    INFLOW: UP,
    STRONG_OUTFLOW: DOWN,
    OUTFLOW: DOWN,
}

function sigColor(s?: string | null): string {
    return SIGNAL_COLOR[(s || "").toUpperCase()] || MUTED
}

function sigLabel(s?: string | null): string {
    const map: Record<string, string> = {
        EXTREME_GREED: "극단적 탐욕", GREED: "탐욕", NEUTRAL: "중립",
        FEAR: "공포", EXTREME_FEAR: "극단적 공포",
        BULLISH: "강세", STRONG_BULLISH: "강한 강세",
        BEARISH: "약세", STRONG_BEARISH: "강한 약세",
        MIXED: "혼조",
        RISK_ON: "위험선호", RISK_OFF: "안전선호",
        DEFENSIVE: "방어적", CASH_FLIGHT: "현금선호",
        STRONG_INFLOW: "강한 유입", INFLOW: "유입",
        STRONG_OUTFLOW: "강한 유출", OUTFLOW: "유출",
    }
    return map[(s || "").toUpperCase()] || (s || "—")
}

interface Props { dataUrl: string }

function GaugeBar({ value, max = 100, color }: { value: number | null; max?: number; color: string }) {
    const pct = value != null ? Math.min(100, Math.max(0, (value / max) * 100)) : 0
    return (
        <div style={{ height: 6, background: BORDER, borderRadius: R.sm, overflow: "hidden", width: "100%" }}>
            <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: R.sm, transition: "width 0.6s ease" }} />
        </div>
    )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
    return (
        <div style={{ color: ACCENT, fontSize: T.cap, fontWeight: T.w_black, letterSpacing: "0.08em", textTransform: "uppercase" as const, marginBottom: S.md, fontFamily: FONT_MONO }}>
            {children}
        </div>
    )
}

function StatRow({ label, value, sub, color }: { label: string; value: React.ReactNode; sub?: string; color?: string }) {
    return (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: `${S.sm}px 0`, borderBottom: `1px solid ${BORDER}` }}>
            <span style={{ color: MUTED, fontSize: T.body }}>{label}</span>
            <span style={{ color: color || C.textPrimary, fontSize: T.body, fontWeight: T.w_bold, fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }}>
                {value}
                {sub && <span style={{ color: MUTED, fontSize: T.cap, fontWeight: T.w_reg, marginLeft: S.xs, fontFamily: FONT }}>{sub}</span>}
            </span>
        </div>
    )
}

function SignalBadge({ signal }: { signal?: string | null }) {
    const c = sigColor(signal)
    return (
        <span style={{
            background: `${c}22`, border: `1px solid ${c}55`, color: c,
            fontSize: T.cap, fontWeight: T.w_bold, padding: `2px ${S.sm}px`, borderRadius: R.sm,
        }}>
            {sigLabel(signal)}
        </span>
    )
}

export default function MacroSentimentPanel({ dataUrl }: Props) {
    const [data, setData] = useState<any>(null)
    const [loading, setLoading] = useState(true)
    const [fetchError, setFetchError] = useState(false)
    const [tab, setTab] = useState<"fng" | "cot" | "flow" | "pcr">("fng")

    const url = (dataUrl || "").trim() || DATA_URL
    useEffect(() => {
        const ac = new AbortController()
        setLoading(true)
        setFetchError(false)
        fetchJson(url, ac.signal)
            .then(d => { if (!ac.signal.aborted) { setData(d); setLoading(false) } })
            .catch(() => { if (!ac.signal.aborted) { setLoading(false); setFetchError(true) } })
        const iv = setInterval(() => {
            fetchJson(url).then(d => { if (!ac.signal.aborted) setData(d) }).catch(() => {})
        }, 10 * 60_000)
        return () => { ac.abort(); clearInterval(iv) }
    }, [url])

    const fng: any = data?.market_fear_greed || {}
    const cot: any = data?.cftc_cot || {}
    const flow: any = data?.fund_flows || {}
    const pcr: any = data?.cboe_pcr || {}
    // §U-4 sector_rotation_check — KOSPI quadrant 정합성 드리프트
    const rotationCheck: any = data?.sector_rotation_check || {}
    const rotationDrift = rotationCheck?.consistency?.drift === true ? rotationCheck.consistency : null

    const tabs = [
        { key: "fng" as const, label: "F&G 지수" },
        { key: "cot" as const, label: "COT 포지션" },
        { key: "flow" as const, label: "펀드 플로우" },
        { key: "pcr" as const, label: "CBOE PCR" },
    ]

    return (
        <div style={{ width: "100%", background: BG, borderRadius: R.lg, padding: S.xl, fontFamily: font, border: `1px solid ${BORDER}`, boxSizing: "border-box" as const }}>
            {/* 헤더 */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: S.lg }}>
                <span style={{ color: C.textPrimary, fontSize: T.title, fontWeight: T.w_black }}>시장 심리 지표</span>
                {loading && <span style={{ color: MUTED, fontSize: T.cap }}>로딩 중…</span>}
                {!loading && fetchError && (
                    <span style={{ color: DOWN, fontSize: T.cap }}>데이터 로드 실패 — 잠시 후 새로고침 하세요</span>
                )}
            </div>

            {/* §U-4 KOSPI 섹터 vs Quadrant 정합성 드리프트 */}
            {rotationDrift && (
                <div style={{
                    background: "rgba(245,158,11,0.08)", border: `1px solid ${WARN}40`,
                    borderRadius: R.sm, padding: `${S.md}px ${S.lg}px`, marginBottom: S.md,
                }}>
                    <div style={{ color: WARN, fontSize: T.body, fontWeight: T.w_black, fontFamily: font, marginBottom: S.xs }}>
                        ⚠ KOSPI 섹터 ↔ Quadrant 정합성 드리프트
                    </div>
                    <div style={{ color: C.textPrimary, fontSize: T.cap, fontFamily: font, lineHeight: T.lh_normal }}>
                        현 분면: <b>{rotationDrift.quadrant_label || rotationDrift.quadrant || "—"}</b>
                        {" · "}드리프트 <span style={{ fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }}>{rotationDrift.drift_count}</span>건
                    </div>
                    {Array.isArray(rotationDrift.top_in_unfavored) && rotationDrift.top_in_unfavored.length > 0 && (
                        <div style={{ color: "#FCA5A5", fontSize: T.cap, fontFamily: font, marginTop: 2 }}>
                            상위 (예상 약세): {rotationDrift.top_in_unfavored.map((t: any) => t.sector).join(", ")}
                        </div>
                    )}
                    {Array.isArray(rotationDrift.bottom_in_favored) && rotationDrift.bottom_in_favored.length > 0 && (
                        <div style={{ color: "#86EFAC", fontSize: T.cap, fontFamily: font, marginTop: 2 }}>
                            하위 (예상 강세): {rotationDrift.bottom_in_favored.map((b: any) => b.sector).join(", ")}
                        </div>
                    )}
                </div>
            )}

            {/* 탭 */}
            <div style={{ display: "flex", gap: S.xs, marginBottom: S.lg, flexWrap: "wrap" as const }}>
                {tabs.map(t => {
                    const active = tab === t.key
                    return (
                        <button key={t.key} onClick={() => setTab(t.key)} style={{
                            padding: `${S.sm}px ${S.md}px`, borderRadius: R.sm, fontSize: T.cap, fontWeight: T.w_bold,
                            cursor: "pointer", border: "none", fontFamily: font,
                            background: active ? ACCENT : CARD,
                            color: active ? "#000" : MUTED,
                            boxShadow: active ? G.accent : "none",
                            transition: X.fast,
                        }}>{t.label}</button>
                    )
                })}
            </div>

            {/* ── CNN Fear & Greed ── */}
            {tab === "fng" && (
                <div>
                    <SectionTitle>CNN Fear &amp; Greed Index</SectionTitle>
                    {fng.ok ? (
                        <>
                            <div style={{ display: "flex", alignItems: "center", gap: S.md, marginBottom: S.lg }}>
                                <div style={{
                                    width: 72, height: 72, borderRadius: "50%", background: CARD,
                                    border: `3px solid ${sigColor(fng.signal)}`,
                                    display: "flex", flexDirection: "column" as const, alignItems: "center", justifyContent: "center",
                                }}>
                                    <span style={{ color: C.textPrimary, fontSize: T.h2, fontWeight: T.w_black, lineHeight: 1, fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }}>{fng.value}</span>
                                    <span style={{ color: MUTED, fontSize: T.cap, fontFamily: FONT_MONO }}>/100</span>
                                </div>
                                <div>
                                    <SignalBadge signal={fng.signal} />
                                    <div style={{ color: MUTED, fontSize: T.cap, marginTop: S.xs }}>{fng.description_kr || fng.description || ""}</div>
                                    {fng.change_1d != null && (
                                        <div style={{ color: fng.change_1d >= 0 ? UP : DOWN, fontSize: T.cap, fontWeight: T.w_bold, marginTop: 2, fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }}>
                                            전일 대비 {fng.change_1d > 0 ? "+" : ""}{fng.change_1d?.toFixed(0)}
                                        </div>
                                    )}
                                </div>
                            </div>
                            <GaugeBar value={fng.value} color={sigColor(fng.signal)} />
                            {fng.sub_indicators && (
                                <div style={{ marginTop: S.lg }}>
                                    <SectionTitle>하위 지표</SectionTitle>
                                    {Object.entries(fng.sub_indicators).map(([k, v]: [string, any]) => (
                                        <StatRow key={k}
                                            label={k.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}
                                            value={v?.score != null ? v.score.toFixed(0) : "—"}
                                            sub={v?.signal ? sigLabel(v.signal) : undefined}
                                            color={v?.signal ? sigColor(v.signal) : undefined}
                                        />
                                    ))}
                                </div>
                            )}
                        </>
                    ) : (
                        <div style={{ color: MUTED, fontSize: T.body }}>데이터 없음</div>
                    )}
                </div>
            )}

            {/* ── CFTC COT ── */}
            {tab === "cot" && (
                <div>
                    <SectionTitle>CFTC COT — 기관 포지셔닝</SectionTitle>
                    {cot.ok ? (
                        <>
                            <div style={{ display: "flex", alignItems: "center", gap: S.md, marginBottom: S.md }}>
                                <SignalBadge signal={cot.summary?.overall_signal} />
                                <span style={{ color: MUTED, fontSize: T.cap }}>
                                    확신도 <strong style={{ color: C.textPrimary, fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }}>{cot.summary?.conviction_level ?? "—"}%</strong>
                                    {cot.report_date && <> &nbsp;·&nbsp; 기준 <span style={{ fontFamily: FONT_MONO }}>{cot.report_date}</span></>}
                                </span>
                            </div>
                            {(() => {
                                const allInst = cot.instruments ? Object.entries(cot.instruments) : []
                                const okInst = allInst.filter(([, inst]: [string, any]) => inst?.ok)
                                const failInst = allInst.filter(([, inst]: [string, any]) => !inst?.ok)
                                if (allInst.length > 0 && okInst.length === 0) {
                                    // §HOTFIX 모든 instrument fail — 빈 화면 방지 메시지
                                    return (
                                        <div style={{
                                            background: "rgba(239,68,68,0.08)", border: `1px solid ${DOWN}40`,
                                            borderRadius: R.sm, padding: `${S.md}px ${S.lg}px`, color: "#FCA5A5",
                                            fontSize: T.body, fontFamily: font,
                                        }}>
                                            ⚠ COT 모든 instrument 수집 실패 (CFTC API rate-limit 또는 응답 오류).
                                            다음 사이클에서 재시도됨.
                                            {failInst.length > 0 && (
                                                <div style={{ marginTop: S.xs, color: MUTED, fontSize: T.cap }}>
                                                    실패: {failInst.map(([s, i]: [string, any]) => `${s}(${i.error?.slice(0, 30) || "-"})`).join(", ")}
                                                </div>
                                            )}
                                        </div>
                                    )
                                }
                                return okInst.map(([sym, inst]: [string, any]) => {
                                    const net = inst.net_managed_money
                                    const chg = inst.change_1w
                                    const pct = inst.net_pct_of_oi
                                    return (
                                        <div key={sym} style={{ background: CARD, borderRadius: R.md, padding: `${S.md}px ${S.lg}px`, marginBottom: S.sm }}>
                                            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: S.sm }}>
                                                <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_bold, fontFamily: FONT_MONO }}>{sym}</span>
                                                <SignalBadge signal={inst.signal} />
                                            </div>
                                            <StatRow label="순포지션 (관리자금)" value={net != null ? `${(net / 1000).toFixed(0)}K` : "—"} color={net > 0 ? UP : DOWN} />
                                            {chg != null && <StatRow label="주간 변화" value={`${(chg / 1000).toFixed(0)}K`} color={chg > 0 ? UP : DOWN} />}
                                            {pct != null && <StatRow label="OI 대비 %" value={`${pct.toFixed(1)}%`} />}
                                        </div>
                                    )
                                })
                            })()}
                        </>
                    ) : (
                        <div style={{ color: MUTED, fontSize: T.body }}>데이터 없음 (full/quick 모드에서만 수집)</div>
                    )}
                </div>
            )}

            {/* ── Fund Flow ── */}
            {tab === "flow" && (
                <div>
                    <SectionTitle>ETF 기반 자금 유출입</SectionTitle>
                    {flow.ok ? (
                        <>
                            <div style={{ display: "flex", alignItems: "center", gap: S.md, marginBottom: S.md }}>
                                <SignalBadge signal={flow.rotation_signal} />
                                <span style={{ color: MUTED, fontSize: T.cap }}>{flow.rotation_detail?.detail || ""}</span>
                            </div>
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: S.sm, marginBottom: S.md }}>
                                {[
                                    { label: "주식 플로우", value: flow.equity_flow_score, color: flow.equity_flow_score > 0 ? UP : DOWN },
                                    { label: "채권 플로우", value: flow.bond_flow_score, color: flow.bond_flow_score > 0 ? UP : DOWN },
                                    { label: "안전자산", value: flow.safe_haven_flow_score, color: flow.safe_haven_flow_score > 0 ? UP : DOWN },
                                ].map(({ label, value, color }) => (
                                    <div key={label} style={{ background: CARD, borderRadius: R.md, padding: `${S.md}px ${S.lg}px`, textAlign: "center" as const }}>
                                        <div style={{ color: MUTED, fontSize: T.cap, marginBottom: S.xs }}>{label}</div>
                                        <div style={{ color, fontSize: T.title, fontWeight: T.w_black, fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }}>
                                            {value != null ? `${value > 0 ? "+" : ""}${value.toFixed(0)}` : "—"}
                                        </div>
                                    </div>
                                ))}
                            </div>
                            {(() => {
                                const etfList: any[] = Array.isArray(flow.etf_details)
                                    ? flow.etf_details
                                    : flow.etf_flows && typeof flow.etf_flows === "object" && !Array.isArray(flow.etf_flows)
                                        ? Object.entries(flow.etf_flows)
                                            .filter(([, v]: any) => v?.ok)
                                            .map(([ticker, v]: any) => ({
                                                ticker,
                                                category: v.category || "—",
                                                flow_score: v.flow_score ?? v.money_flow_1w ?? null,
                                                signal: v.signal || v.flow_signal || null,
                                            }))
                                        : []
                                return etfList.slice(0, 8).map((etf: any) => (
                                    <StatRow key={etf.ticker}
                                        label={`${etf.ticker} (${etf.category || "—"})`}
                                        value={etf.flow_score != null ? `${etf.flow_score > 0 ? "+" : ""}${Number(etf.flow_score).toFixed(0)}` : "—"}
                                        color={etf.flow_score > 0 ? UP : etf.flow_score < 0 ? DOWN : MUTED}
                                        sub={etf.signal ? sigLabel(etf.signal) : undefined}
                                    />
                                ))
                            })()}
                        </>
                    ) : (
                        <div style={{ color: MUTED, fontSize: T.body }}>데이터 없음 (full/quick 모드에서만 수집)</div>
                    )}
                </div>
            )}

            {/* ── CBOE PCR ── */}
            {tab === "pcr" && (
                <div>
                    <SectionTitle>CBOE 풋/콜 비율 (Put-Call Ratio)</SectionTitle>
                    {/* §HOTFIX history fallback 알림 — source==history_fallback 시 stale 표기 */}
                    {pcr.source === "history_fallback" && (
                        <div style={{
                            background: "rgba(245,158,11,0.10)", border: `1px solid ${WARN}40`,
                            borderRadius: R.sm, padding: `${S.sm}px ${S.md}px`, marginBottom: S.md,
                            color: WARN, fontSize: T.cap, fontFamily: font,
                        }}>
                            ⚠ 실시간 소스 실패 — <span style={{ fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }}>{pcr.stale_days ?? "?"}</span>일 전 값 사용 (panic 신호 비활성)
                        </div>
                    )}
                    {pcr.source === "fallback_no_data" && (
                        <div style={{
                            background: "rgba(239,68,68,0.08)", border: `1px solid ${DOWN}40`,
                            borderRadius: R.sm, padding: `${S.sm}px ${S.md}px`, marginBottom: S.md,
                            color: "#FCA5A5", fontSize: T.cap, fontFamily: font,
                        }}>
                            ⚠ PCR 데이터 수집 실패 — 다음 사이클 재시도
                        </div>
                    )}
                    {pcr.signal ? (
                        <>
                            <div style={{ display: "flex", alignItems: "center", gap: S.md, marginBottom: S.lg }}>
                                <div style={{
                                    background: CARD, borderRadius: R.md, padding: `${S.md}px ${S.lg}px`,
                                    border: `1px solid ${pcr.panic_trigger ? DOWN : BORDER}`,
                                    boxShadow: pcr.panic_trigger ? G.danger : "none",
                                }}>
                                    <div style={{ color: MUTED, fontSize: T.cap, marginBottom: 2, fontFamily: FONT_MONO, letterSpacing: "0.05em", textTransform: "uppercase" as const }}>Total PCR</div>
                                    <div style={{ color: C.textPrimary, fontSize: T.h1, fontWeight: T.w_black, fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }}>
                                        {pcr.total_pcr_latest?.toFixed(3) ?? "—"}
                                    </div>
                                </div>
                                <div>
                                    <SignalBadge signal={pcr.signal} />
                                    {pcr.panic_trigger && (
                                        <div style={{ color: DOWN, fontSize: T.body, fontWeight: T.w_bold, marginTop: S.sm }}>
                                            ⚠ PANIC 트리거
                                            {pcr.panic_reason && <span style={{ color: MUTED, fontWeight: T.w_reg }}> — {pcr.panic_reason}</span>}
                                        </div>
                                    )}
                                </div>
                            </div>

                            <StatRow label="20일 평균 PCR" value={pcr.total_pcr_avg_20d?.toFixed(3) ?? "—"} />
                            <StatRow label="Z-Score" value={pcr.pcr_z_score != null ? `${pcr.pcr_z_score > 0 ? "+" : ""}${pcr.pcr_z_score.toFixed(2)}` : "—"} color={pcr.pcr_z_score >= 2 ? DOWN : pcr.pcr_z_score <= -2 ? UP : C.textPrimary} />
                            <StatRow label="SPX 실시간 PCR" value={pcr.spx_realtime_pcr?.toFixed(3) ?? "—"} />
                            <StatRow label="Equity PCR (최신)" value={pcr.equity_pcr_latest?.toFixed(3) ?? "—"} />
                            <StatRow label="VCI 보정값" value={pcr.vci_adjustment != null ? `${pcr.vci_adjustment > 0 ? "+" : ""}${pcr.vci_adjustment}` : "—"} color={pcr.vci_adjustment > 0 ? UP : pcr.vci_adjustment < 0 ? DOWN : MUTED} />

                            {Array.isArray(pcr.history_20d) && pcr.history_20d.length > 0 && (
                                <div style={{ marginTop: S.md }}>
                                    <SectionTitle>20일 PCR 추이</SectionTitle>
                                    <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 48, width: "100%" }}>
                                        {(() => {
                                            const slice = pcr.history_20d.slice(-20)
                                            const maxPcr = Math.max(...slice.map((x: any) => x.pcr || 0))
                                            const minPcr = Math.min(...slice.map((x: any) => x.pcr || 0))
                                            const range = maxPcr - minPcr || 1
                                            return slice.map((h: any, i: number) => {
                                                const heightPct = ((h.pcr - minPcr) / range) * 80 + 20
                                                return (
                                                    <div key={i} style={{
                                                        flex: 1, height: `${heightPct}%`,
                                                        background: sigColor(h.pcr >= 1.3 ? "EXTREME_FEAR" : h.pcr >= 1.1 ? "FEAR" : h.pcr >= 0.9 ? "NEUTRAL" : h.pcr >= 0.7 ? "GREED" : "EXTREME_GREED"),
                                                        borderRadius: "2px 2px 0 0", opacity: 0.8,
                                                    }} />
                                                )
                                            })
                                        })()}
                                    </div>
                                    <div style={{ display: "flex", justifyContent: "space-between", marginTop: 2 }}>
                                        <span style={{ color: MUTED, fontSize: T.cap, fontFamily: FONT_MONO }}>{pcr.history_20d[0]?.date?.slice(5) || ""}</span>
                                        <span style={{ color: MUTED, fontSize: T.cap, fontFamily: FONT_MONO }}>{pcr.history_20d[pcr.history_20d.length - 1]?.date?.slice(5) || ""}</span>
                                    </div>
                                </div>
                            )}
                        </>
                    ) : (
                        <div style={{ color: MUTED, fontSize: T.body }}>데이터 없음 (다음 파이프라인 실행 후 수집)</div>
                    )}
                </div>
            )}

            {/* 업데이트 시각 */}
            {data?.updated_at && (
                <div style={{ marginTop: S.lg, color: MUTED, fontSize: T.cap, textAlign: "right" as const, fontFamily: FONT_MONO }}>
                    업데이트: {new Date(data.updated_at).toLocaleString("ko-KR")}
                </div>
            )}
        </div>
    )
}

addPropertyControls(MacroSentimentPanel, {
    dataUrl: {
        type: ControlType.String,
        title: "Portfolio JSON URL",
        defaultValue: DATA_URL,
    },
})
