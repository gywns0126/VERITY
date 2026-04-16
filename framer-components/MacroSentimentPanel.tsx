import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"

const DATA_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"

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

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"
const BG = "#000"
const CARD = "#111"
const BORDER = "#222"
const MUTED = "#8B95A1"
const UP = "#22C55E"
const DOWN = "#EF4444"
const WARN = "#F59E0B"
const ACCENT = "#B5FF19"
const BLUE = "#3B82F6"
const PURPLE = "#A855F7"

const SIGNAL_COLOR: Record<string, string> = {
    EXTREME_GREED: DOWN,
    GREED: "#F97316",
    NEUTRAL: MUTED,
    FEAR: BLUE,
    EXTREME_FEAR: PURPLE,
    BULLISH: UP,
    BEARISH: DOWN,
    MIXED: MUTED,
    RISK_ON: UP,
    RISK_OFF: DOWN,
}

function sigColor(s?: string | null): string {
    return SIGNAL_COLOR[(s || "").toUpperCase()] || MUTED
}

function sigLabel(s?: string | null): string {
    const map: Record<string, string> = {
        EXTREME_GREED: "극단적 탐욕", GREED: "탐욕", NEUTRAL: "중립",
        FEAR: "공포", EXTREME_FEAR: "극단적 공포",
        BULLISH: "강세", BEARISH: "약세", MIXED: "혼조",
        RISK_ON: "위험선호", RISK_OFF: "안전선호",
    }
    return map[(s || "").toUpperCase()] || (s || "—")
}

interface Props { dataUrl: string }

function GaugeBar({ value, max = 100, color }: { value: number | null; max?: number; color: string }) {
    const pct = value != null ? Math.min(100, Math.max(0, (value / max) * 100)) : 0
    return (
        <div style={{ height: 6, background: BORDER, borderRadius: 3, overflow: "hidden", width: "100%" }}>
            <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: 3, transition: "width 0.6s ease" }} />
        </div>
    )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
    return (
        <div style={{ color: ACCENT, fontSize: 10, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase" as const, marginBottom: 10 }}>
            {children}
        </div>
    )
}

function StatRow({ label, value, sub, color }: { label: string; value: React.ReactNode; sub?: string; color?: string }) {
    return (
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "5px 0", borderBottom: `1px solid ${BORDER}` }}>
            <span style={{ color: MUTED, fontSize: 12 }}>{label}</span>
            <span style={{ color: color || "#fff", fontSize: 13, fontWeight: 700 }}>
                {value}
                {sub && <span style={{ color: MUTED, fontSize: 10, fontWeight: 400, marginLeft: 4 }}>{sub}</span>}
            </span>
        </div>
    )
}

function SignalBadge({ signal }: { signal?: string | null }) {
    const c = sigColor(signal)
    return (
        <span style={{
            background: `${c}22`, border: `1px solid ${c}55`, color: c,
            fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 5,
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

    const tabs = [
        { key: "fng" as const, label: "F&G 지수" },
        { key: "cot" as const, label: "COT 포지션" },
        { key: "flow" as const, label: "펀드 플로우" },
        { key: "pcr" as const, label: "CBOE PCR" },
    ]

    return (
        <div style={{ width: "100%", background: BG, borderRadius: 16, padding: 20, fontFamily: font, border: `1px solid ${BORDER}`, boxSizing: "border-box" as const }}>
            {/* 헤더 */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
                <span style={{ color: "#fff", fontSize: 16, fontWeight: 800 }}>시장 심리 지표</span>
                {loading && <span style={{ color: MUTED, fontSize: 11 }}>로딩 중…</span>}
                {!loading && fetchError && (
                    <span style={{ color: DOWN, fontSize: 11 }}>데이터 로드 실패 — 잠시 후 새로고침 하세요</span>
                )}
            </div>

            {/* 탭 */}
            <div style={{ display: "flex", gap: 4, marginBottom: 16, flexWrap: "wrap" as const }}>
                {tabs.map(t => (
                    <button key={t.key} onClick={() => setTab(t.key)} style={{
                        padding: "5px 12px", borderRadius: 6, fontSize: 11, fontWeight: 700,
                        cursor: "pointer", border: "none", fontFamily: font,
                        background: tab === t.key ? ACCENT : CARD,
                        color: tab === t.key ? "#000" : MUTED,
                        transition: "all 0.15s",
                    }}>{t.label}</button>
                ))}
            </div>

            {/* ── CNN Fear & Greed ── */}
            {tab === "fng" && (
                <div>
                    <SectionTitle>CNN Fear &amp; Greed Index</SectionTitle>
                    {fng.ok ? (
                        <>
                            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
                                <div style={{
                                    width: 72, height: 72, borderRadius: "50%", background: CARD,
                                    border: `3px solid ${sigColor(fng.signal)}`,
                                    display: "flex", flexDirection: "column" as const, alignItems: "center", justifyContent: "center",
                                }}>
                                    <span style={{ color: "#fff", fontSize: 22, fontWeight: 800, lineHeight: 1 }}>{fng.value}</span>
                                    <span style={{ color: MUTED, fontSize: 9 }}>/100</span>
                                </div>
                                <div>
                                    <SignalBadge signal={fng.signal} />
                                    <div style={{ color: MUTED, fontSize: 11, marginTop: 4 }}>{fng.description_kr || fng.description || ""}</div>
                                    {fng.change_1d != null && (
                                        <div style={{ color: fng.change_1d >= 0 ? UP : DOWN, fontSize: 11, fontWeight: 700, marginTop: 2 }}>
                                            전일 대비 {fng.change_1d > 0 ? "+" : ""}{fng.change_1d?.toFixed(0)}
                                        </div>
                                    )}
                                </div>
                            </div>
                            <GaugeBar value={fng.value} color={sigColor(fng.signal)} />
                            {fng.sub_indicators && (
                                <div style={{ marginTop: 14 }}>
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
                        <div style={{ color: MUTED, fontSize: 12 }}>데이터 없음</div>
                    )}
                </div>
            )}

            {/* ── CFTC COT ── */}
            {tab === "cot" && (
                <div>
                    <SectionTitle>CFTC COT — 기관 포지셔닝</SectionTitle>
                    {cot.ok ? (
                        <>
                            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                                <SignalBadge signal={cot.summary?.overall_signal} />
                                <span style={{ color: MUTED, fontSize: 11 }}>
                                    확신도 <strong style={{ color: "#fff" }}>{cot.summary?.conviction_level ?? "—"}%</strong>
                                    {cot.report_date && <> &nbsp;·&nbsp; 기준 {cot.report_date}</>}
                                </span>
                            </div>
                            {cot.instruments && Object.entries(cot.instruments).map(([sym, inst]: [string, any]) => {
                                if (!inst?.ok) return null
                                const net = inst.net_managed_money
                                const chg = inst.change_1w
                                const pct = inst.net_pct_of_oi
                                return (
                                    <div key={sym} style={{ background: CARD, borderRadius: 8, padding: "10px 12px", marginBottom: 8 }}>
                                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                                            <span style={{ color: "#fff", fontSize: 13, fontWeight: 700 }}>{sym}</span>
                                            <SignalBadge signal={inst.signal} />
                                        </div>
                                        <StatRow label="순포지션 (관리자금)" value={net != null ? `${(net / 1000).toFixed(0)}K` : "—"} color={net > 0 ? UP : DOWN} />
                                        {chg != null && <StatRow label="주간 변화" value={`${(chg / 1000).toFixed(0)}K`} color={chg > 0 ? UP : DOWN} />}
                                        {pct != null && <StatRow label="OI 대비 %" value={`${pct.toFixed(1)}%`} />}
                                    </div>
                                )
                            })}
                        </>
                    ) : (
                        <div style={{ color: MUTED, fontSize: 12 }}>데이터 없음 (full/quick 모드에서만 수집)</div>
                    )}
                </div>
            )}

            {/* ── Fund Flow ── */}
            {tab === "flow" && (
                <div>
                    <SectionTitle>ETF 기반 자금 유출입</SectionTitle>
                    {flow.ok ? (
                        <>
                            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
                                <SignalBadge signal={flow.rotation_signal} />
                                <span style={{ color: MUTED, fontSize: 11 }}>{flow.rotation_detail?.detail || ""}</span>
                            </div>
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 12 }}>
                                {[
                                    { label: "주식 플로우", value: flow.equity_flow_score, color: flow.equity_flow_score > 0 ? UP : DOWN },
                                    { label: "채권 플로우", value: flow.bond_flow_score, color: flow.bond_flow_score > 0 ? UP : DOWN },
                                    { label: "안전자산", value: flow.safe_haven_flow_score, color: flow.safe_haven_flow_score > 0 ? UP : DOWN },
                                ].map(({ label, value, color }) => (
                                    <div key={label} style={{ background: CARD, borderRadius: 8, padding: "10px 12px", textAlign: "center" as const }}>
                                        <div style={{ color: MUTED, fontSize: 10, marginBottom: 4 }}>{label}</div>
                                        <div style={{ color, fontSize: 18, fontWeight: 800 }}>
                                            {value != null ? `${value > 0 ? "+" : ""}${value.toFixed(0)}` : "—"}
                                        </div>
                                    </div>
                                ))}
                            </div>
                            {flow.etf_details && Array.isArray(flow.etf_details) && flow.etf_details.slice(0, 6).map((etf: any) => (
                                <StatRow key={etf.ticker}
                                    label={`${etf.ticker} (${etf.category || "—"})`}
                                    value={etf.flow_score != null ? `${etf.flow_score > 0 ? "+" : ""}${etf.flow_score.toFixed(0)}` : "—"}
                                    color={etf.flow_score > 0 ? UP : DOWN}
                                    sub={etf.signal || undefined}
                                />
                            ))}
                        </>
                    ) : (
                        <div style={{ color: MUTED, fontSize: 12 }}>데이터 없음 (full/quick 모드에서만 수집)</div>
                    )}
                </div>
            )}

            {/* ── CBOE PCR ── */}
            {tab === "pcr" && (
                <div>
                    <SectionTitle>CBOE 풋/콜 비율 (Put-Call Ratio)</SectionTitle>
                    {pcr.signal ? (
                        <>
                            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
                                <div style={{
                                    background: CARD, borderRadius: 10, padding: "10px 16px",
                                    border: `1px solid ${pcr.panic_trigger ? DOWN : BORDER}`,
                                }}>
                                    <div style={{ color: MUTED, fontSize: 10, marginBottom: 2 }}>Total PCR</div>
                                    <div style={{ color: "#fff", fontSize: 24, fontWeight: 800 }}>
                                        {pcr.total_pcr_latest?.toFixed(3) ?? "—"}
                                    </div>
                                </div>
                                <div>
                                    <SignalBadge signal={pcr.signal} />
                                    {pcr.panic_trigger && (
                                        <div style={{ color: DOWN, fontSize: 12, fontWeight: 700, marginTop: 6 }}>
                                            ⚠ PANIC 트리거
                                            {pcr.panic_reason && <span style={{ color: MUTED, fontWeight: 400 }}> — {pcr.panic_reason}</span>}
                                        </div>
                                    )}
                                </div>
                            </div>

                            <StatRow label="20일 평균 PCR" value={pcr.total_pcr_avg_20d?.toFixed(3) ?? "—"} />
                            <StatRow label="Z-Score" value={pcr.pcr_z_score != null ? `${pcr.pcr_z_score > 0 ? "+" : ""}${pcr.pcr_z_score.toFixed(2)}` : "—"} color={pcr.pcr_z_score >= 2 ? DOWN : pcr.pcr_z_score <= -2 ? UP : "#fff"} />
                            <StatRow label="SPX 실시간 PCR" value={pcr.spx_realtime_pcr?.toFixed(3) ?? "—"} />
                            <StatRow label="Equity PCR (최신)" value={pcr.equity_pcr_latest?.toFixed(3) ?? "—"} />
                            <StatRow label="VCI 보정값" value={pcr.vci_adjustment != null ? `${pcr.vci_adjustment > 0 ? "+" : ""}${pcr.vci_adjustment}` : "—"} color={pcr.vci_adjustment > 0 ? UP : pcr.vci_adjustment < 0 ? DOWN : MUTED} />

                            {Array.isArray(pcr.history_20d) && pcr.history_20d.length > 0 && (
                                <div style={{ marginTop: 12 }}>
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
                                        <span style={{ color: MUTED, fontSize: 9 }}>{pcr.history_20d[0]?.date?.slice(5) || ""}</span>
                                        <span style={{ color: MUTED, fontSize: 9 }}>{pcr.history_20d[pcr.history_20d.length - 1]?.date?.slice(5) || ""}</span>
                                    </div>
                                </div>
                            )}
                        </>
                    ) : (
                        <div style={{ color: MUTED, fontSize: 12 }}>데이터 없음 (다음 파이프라인 실행 후 수집)</div>
                    )}
                </div>
            )}

            {/* 업데이트 시각 */}
            {data?.updated_at && (
                <div style={{ marginTop: 16, color: MUTED, fontSize: 10, textAlign: "right" as const }}>
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
