import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState, type CSSProperties } from "react"

/**
 * MarketHorizon V0 — "시장 어디까지 가나" 답하는 컴포넌트.
 *
 * 4축: probit 침체확률 / CAPE percentile / cycle stage / horizon 분포.
 * 정직 패턴: 분포 + 가정 노출. 단정 X. self-attribution 명시.
 *
 * 평소 = 1 row dense verdict. tap 시 expand → 4 horizon grid + signal stack.
 */

/* ◆ DESIGN TOKENS ◆ */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B",
    border: "rgba(255,255,255,0.06)", borderStrong: "rgba(255,255,255,0.10)",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#7fffa0",
    success: "#22C55E", warn: "#F59E0B", danger: "#EF4444", info: "#5BA9FF",
}
const T = { cap: 12, body: 14, sub: 16, title: 18, h2: 22 }
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24 }
const R = { sm: 6, md: 10, lg: 14 }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Menlo', monospace"
const MONO: CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }


interface Props {
    dataUrl: string
    refreshInterval: number
    defaultExpanded: boolean
}

interface HorizonRow {
    median: number
    p25: number
    p75: number
    p5: number
    p95: number
}

interface AnalogRow {
    name: string
    date: string
    distance: number
    cape?: number
    after_pct?: { "1m"?: number; "3m"?: number; "6m"?: number; "12m"?: number; "24m"?: number }
}

interface SwanEvent {
    ts_kst?: string
    severity?: number
    category?: string
    summary_ko?: string
    primary_title?: string
    link?: string
    portfolio_angle?: string
}

interface MarketHorizonData {
    verdict?: string
    recession_prob_12m?: number
    cape_percentile?: number
    cape_value?: number
    cycle_stage?: string
    cycle_stage_label_ko?: string
    horizons?: { "1m"?: HorizonRow; "3m"?: HorizonRow; "6m"?: HorizonRow; "12m"?: HorizonRow }
    analogs?: AnalogRow[]
    analog_horizons?: Record<string, { n_samples: number; median_pct: number; p25_pct: number; p75_pct: number; min_pct: number; max_pct: number }>
    recent_black_swan_events?: SwanEvent[]
    signals?: Array<{
        name: string
        value?: number
        percentile?: number
        direction?: "ok" | "neutral" | "warn"
        note?: string
        lead_months?: number[]
    }>
    model_meta?: any
    as_of?: string
    _error?: string
}


function bustUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}


function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    return fetch(bustUrl(url), { cache: "no-store", mode: "cors", credentials: "omit", signal })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((txt) => JSON.parse(txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null")))
}


const STAGE_COLOR: Record<string, string> = {
    early_bull: C.success,
    mid_bull: C.accent,
    late_bull: C.warn,
    euphoria: C.danger,
    bear: C.danger,
    unknown: C.textTertiary,
}


const STAGE_ORDER = ["early_bull", "mid_bull", "late_bull", "euphoria", "bear"]
const STAGE_LABEL_SHORT: Record<string, string> = {
    early_bull: "초기",
    mid_bull: "중기",
    late_bull: "후기",
    euphoria: "과열",
    bear: "약세",
    unknown: "—",
}


const SIG_NAME_KO: Record<string, string> = {
    yield_spread_3m_10y: "수익률곡선 (3M-10Y)",
    fred_recession_now: "FRED 침체확률 (현재)",
    cape: "CAPE (Shiller PE)",
    pmi: "PMI",
    unemployment: "실업률",
    hy_oas: "HY OAS (신용 스프레드)",
    consumer_sentiment: "소비자심리",
    vix: "VIX",
    cnn_fear_greed: "CNN F&G (탐욕/공포)",
    cboe_pcr: "CBOE P/C Ratio",
    fund_flow_rotation: "ETF 자금흐름",
    cot_overall: "CFTC COT 포지셔닝",
    new_listing_quality: "신규 딜 품질 (Marks)",
}


const DIR_COLOR: Record<string, string> = {
    ok: C.success,
    neutral: C.textSecondary,
    warn: C.danger,
}


const SWAN_CAT_KO: Record<string, string> = {
    war: "전쟁/충돌",
    disaster: "재난",
    market_shock: "시장 쇼크",
    geopolitics: "지정학",
    irrelevant: "기타",
}


function swanColor(sev?: number): string {
    if (sev == null) return C.textTertiary
    if (sev >= 8) return C.danger
    if (sev >= 5) return C.warn
    return C.textTertiary
}


function pctFmt(v?: number, plus = true): string {
    if (v == null) return "—"
    const sign = plus && v >= 0 ? "+" : ""
    return `${sign}${(v * 100).toFixed(1)}%`
}


function HorizonBar({ row }: { row: HorizonRow }) {
    // 분포 시각화: -50% ~ +50% 범위로 정규화. p5/p95 = 가는 선, p25/p75 = 박스, median = 점.
    const RANGE = 0.5
    const map = (v: number) => Math.max(0, Math.min(1, (v + RANGE) / (2 * RANGE))) * 100
    const p5 = map(row.p5)
    const p95 = map(row.p95)
    const p25 = map(row.p25)
    const p75 = map(row.p75)
    const med = map(row.median)
    const medColor = row.median >= 0 ? C.success : C.danger

    return (
        <div style={{ position: "relative", width: "100%", height: 22 }}>
            {/* 0% 기준선 */}
            <div style={{
                position: "absolute", left: "50%", top: 0, bottom: 0,
                width: 1, background: C.border, transform: "translateX(-0.5px)",
            }} />
            {/* p5 ~ p95 thin line */}
            <div style={{
                position: "absolute", top: "50%", height: 1, background: C.borderStrong,
                left: `${p5}%`, width: `${p95 - p5}%`,
                transform: "translateY(-0.5px)",
            }} />
            {/* p25 ~ p75 box */}
            <div style={{
                position: "absolute", top: "30%", bottom: "30%", background: C.bgElevated,
                left: `${p25}%`, width: `${p75 - p25}%`,
                borderRadius: 2,
            }} />
            {/* median dot */}
            <div style={{
                position: "absolute", top: "50%", left: `${med}%`,
                width: 8, height: 8, borderRadius: "50%",
                background: medColor,
                transform: "translate(-50%, -50%)",
            }} />
        </div>
    )
}


function CycleDots({ stage }: { stage?: string }) {
    return (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {STAGE_ORDER.map((s) => {
                const active = s === stage
                return (
                    <div key={s} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                        <span style={{
                            width: active ? 10 : 6, height: active ? 10 : 6,
                            borderRadius: "50%",
                            background: active ? STAGE_COLOR[s] : C.borderStrong,
                            transition: "all 180ms ease",
                        }} />
                        <span style={{
                            fontSize: 10, color: active ? C.textPrimary : C.textTertiary,
                            fontWeight: active ? 700 : 500, letterSpacing: 0.2,
                        }}>
                            {STAGE_LABEL_SHORT[s]}
                        </span>
                    </div>
                )
            })}
        </div>
    )
}


export default function MarketHorizon(props: Props) {
    const { dataUrl, refreshInterval, defaultExpanded } = props
    const [data, setData] = useState<MarketHorizonData | null>(null)
    const [expanded, setExpanded] = useState(defaultExpanded)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        const load = () => {
            fetchPortfolioJson(dataUrl, ac.signal)
                .then((d) => {
                    if (ac.signal.aborted) return
                    setData(d?.market_horizon ?? null)
                    setLoading(false)
                })
                .catch(() => { if (!ac.signal.aborted) setLoading(false) })
        }
        load()
        const id = refreshInterval > 0 ? setInterval(load, refreshInterval * 1000) : undefined
        return () => { ac.abort(); if (id) clearInterval(id) }
    }, [dataUrl, refreshInterval])

    if (loading) {
        return (
            <div style={shell}>
                <span style={{ color: C.textTertiary, fontSize: T.cap }}>시장 사이클 로딩 중...</span>
            </div>
        )
    }
    if (!data || data._error) {
        return (
            <div style={shell}>
                <span style={{ color: C.textTertiary, fontSize: T.cap }}>
                    {data?._error || "데이터 없음"}
                </span>
            </div>
        )
    }

    const stage = data.cycle_stage || "unknown"
    const stageColor = STAGE_COLOR[stage] || C.textTertiary
    const horizons = data.horizons || {}
    const horizonOrder: Array<keyof typeof horizons> = ["1m", "3m", "6m", "12m"]
    const horizonLabel: Record<string, string> = { "1m": "1개월", "3m": "3개월", "6m": "6개월", "12m": "12개월" }

    return (
        <div style={shell}>
            {/* 헤더 + verdict */}
            <div
                onClick={() => setExpanded((v) => !v)}
                style={{
                    display: "flex", alignItems: "center", gap: S.md,
                    cursor: "pointer",
                }}
            >
                <span style={{
                    width: 8, height: 8, borderRadius: "50%", background: stageColor, flexShrink: 0,
                }} />
                <span style={{
                    color: C.textTertiary, fontSize: 11, fontWeight: 700,
                    letterSpacing: 0.5, textTransform: "uppercase", flexShrink: 0,
                }}>
                    Market Horizon
                </span>
                <span style={{
                    color: C.textPrimary, fontSize: T.body, fontWeight: 600,
                    flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                }}>
                    {data.verdict || "—"}
                </span>
                <span style={{
                    color: C.textTertiary, fontSize: 12,
                    transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
                    transition: "transform 180ms ease",
                }}>
                    ▾
                </span>
            </div>

            {expanded && (
                <>
                    {/* Cycle dots */}
                    <div style={{ paddingTop: S.md }}>
                        <div style={subLabelStyle}>사이클 단계</div>
                        <CycleDots stage={stage} />
                    </div>

                    {/* Horizon grid */}
                    <div style={{ paddingTop: S.lg }}>
                        <div style={subLabelStyle}>Horizon 분포 (S&P 500 기대수익)</div>
                        <div style={{ display: "flex", flexDirection: "column", gap: S.sm }}>
                            {horizonOrder.map((h) => {
                                const row = horizons[h]
                                if (!row) return null
                                return (
                                    <div key={h} style={{
                                        display: "grid",
                                        gridTemplateColumns: "60px 1fr 80px",
                                        alignItems: "center", gap: S.md,
                                    }}>
                                        <span style={{ color: C.textSecondary, fontSize: 12, fontWeight: 600 }}>
                                            {horizonLabel[h]}
                                        </span>
                                        <HorizonBar row={row} />
                                        <span style={{
                                            ...MONO,
                                            color: row.median >= 0 ? C.success : C.danger,
                                            fontSize: 13, fontWeight: 700, textAlign: "right",
                                        }}>
                                            {pctFmt(row.median)}
                                        </span>
                                    </div>
                                )
                            })}
                            <div style={{
                                display: "flex", justifyContent: "space-between",
                                color: C.textDisabled, fontSize: 10, ...MONO, paddingTop: S.xs,
                            }}>
                                <span>−50%</span>
                                <span>0%</span>
                                <span>+50%</span>
                            </div>
                            <div style={{
                                color: C.textTertiary, fontSize: 10, paddingTop: S.xs,
                            }}>
                                점 = median · 박스 = 25-75 percentile · 선 = 5-95 percentile
                            </div>
                        </div>
                    </div>

                    {/* Historical analogs (V2) */}
                    {(data.analogs?.length || 0) > 0 && (
                        <div style={{ paddingTop: S.lg }}>
                            <div style={subLabelStyle}>과거 유사 시점 (nearest 5)</div>
                            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                {data.analogs!.map((a) => (
                                    <div key={a.date} style={{
                                        display: "grid",
                                        gridTemplateColumns: "70px 1fr 50px 80px",
                                        alignItems: "center", gap: S.sm,
                                        padding: `4px 0`,
                                    }}>
                                        <span style={{ ...MONO, color: C.textTertiary, fontSize: 11 }}>
                                            {a.date}
                                        </span>
                                        <span style={{ color: C.textPrimary, fontSize: 11, fontWeight: 600,
                                            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                            {a.name}
                                        </span>
                                        <span style={{ ...MONO, color: C.textDisabled, fontSize: 10, textAlign: "right" }}>
                                            d={a.distance.toFixed(2)}
                                        </span>
                                        <span style={{
                                            ...MONO, fontSize: 11, fontWeight: 700, textAlign: "right",
                                            color: (a.after_pct?.["12m"] ?? 0) >= 0 ? C.success : C.danger,
                                        }}>
                                            {a.after_pct?.["12m"] != null
                                                ? `12M ${a.after_pct["12m"] > 0 ? "+" : ""}${a.after_pct["12m"]}%`
                                                : "12M —"}
                                        </span>
                                    </div>
                                ))}
                                {data.analog_horizons?.["12m"] && (
                                    <div style={{
                                        marginTop: 6, paddingTop: 6,
                                        color: C.textTertiary, fontSize: 11, lineHeight: 1.5,
                                    }}>
                                        <span style={{ color: C.textSecondary, fontWeight: 700 }}>
                                            12M 집계
                                        </span>
                                        {" — "}
                                        median <span style={{ ...MONO, color: C.textPrimary }}>
                                            {data.analog_horizons["12m"].median_pct >= 0 ? "+" : ""}
                                            {data.analog_horizons["12m"].median_pct}%
                                        </span>
                                        {", p25/p75 "}
                                        <span style={{ ...MONO, color: C.textPrimary }}>
                                            {data.analog_horizons["12m"].p25_pct >= 0 ? "+" : ""}
                                            {data.analog_horizons["12m"].p25_pct}% / {data.analog_horizons["12m"].p75_pct >= 0 ? "+" : ""}
                                            {data.analog_horizons["12m"].p75_pct}%
                                        </span>
                                        {", range "}
                                        <span style={{ ...MONO, color: C.textPrimary }}>
                                            {data.analog_horizons["12m"].min_pct}% / +{data.analog_horizons["12m"].max_pct}%
                                        </span>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Black Swan events (V2.2) — 직전 24h ledger top 3 */}
                    <div style={{ paddingTop: S.lg }}>
                        <div style={{
                            ...subLabelStyle,
                            display: "flex", alignItems: "center", gap: S.sm,
                        }}>
                            <span>Black Swan · 직전 24h</span>
                            {(data.recent_black_swan_events?.length || 0) === 0 && (
                                <span style={{
                                    color: C.textDisabled, fontSize: 9, fontWeight: 600,
                                    letterSpacing: 0.4, textTransform: "uppercase",
                                    padding: "2px 6px", borderRadius: 4,
                                    border: `1px solid ${C.borderStrong}`,
                                }}>
                                    목업 · 데이터 누적 중
                                </span>
                            )}
                        </div>
                        {(data.recent_black_swan_events?.length || 0) === 0 ? (
                            <div style={{
                                color: C.textTertiary, fontSize: 11, lineHeight: 1.5,
                            }}>
                                아직 적재된 이벤트가 없습니다. tail_risk_digest 가 매 cycle 헤드라인을
                                Gemini 로 판별하여 severity 5+ 이벤트를 자동으로 누적합니다.
                            </div>
                        ) : (
                            <div style={{ display: "flex", flexDirection: "column", gap: S.sm }}>
                                {data.recent_black_swan_events!.map((e, i) => {
                                    const color = swanColor(e.severity)
                                    const cat = SWAN_CAT_KO[e.category || ""] || (e.category || "—")
                                    return (
                                        <div key={i} style={{
                                            display: "grid",
                                            gridTemplateColumns: "32px 70px 1fr",
                                            alignItems: "start", gap: S.sm,
                                            padding: `${S.xs}px 0`,
                                        }}>
                                            <span style={{
                                                ...MONO,
                                                color, fontSize: 13, fontWeight: 700,
                                                textAlign: "center",
                                            }}>
                                                {e.severity ?? "—"}
                                            </span>
                                            <span style={{
                                                color: C.textSecondary, fontSize: 11, fontWeight: 600,
                                                letterSpacing: 0.2,
                                            }}>
                                                {cat}
                                            </span>
                                            <div style={{
                                                display: "flex", flexDirection: "column", gap: 2,
                                                minWidth: 0,
                                            }}>
                                                <span style={{
                                                    color: C.textPrimary, fontSize: 12, fontWeight: 600,
                                                    lineHeight: 1.4,
                                                }}>
                                                    {e.summary_ko || e.primary_title || "—"}
                                                </span>
                                                {e.portfolio_angle && (
                                                    <span style={{
                                                        color: C.textTertiary, fontSize: 10,
                                                        lineHeight: 1.4,
                                                    }}>
                                                        포트 연결 · {e.portfolio_angle}
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    )
                                })}
                            </div>
                        )}
                    </div>

                    {/* Signal stack */}
                    {(data.signals?.length || 0) > 0 && (
                        <div style={{ paddingTop: S.lg }}>
                            <div style={subLabelStyle}>매크로 시그널</div>
                            <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                                {data.signals!.map((s) => {
                                    const isNumeric = typeof s.value === "number"
                                    return (
                                        <div key={s.name} style={{
                                            display: "grid",
                                            gridTemplateColumns: "180px 100px 1fr",
                                            alignItems: "start", gap: S.md,
                                            padding: `${S.xs}px 0`,
                                        }}>
                                            <span style={{ color: C.textPrimary, fontSize: 12, fontWeight: 600 }}>
                                                {SIG_NAME_KO[s.name] || s.name}
                                            </span>
                                            <span style={{
                                                ...(isNumeric ? MONO : {}),
                                                color: DIR_COLOR[s.direction || "neutral"],
                                                fontSize: 12, fontWeight: 700,
                                                textAlign: isNumeric ? "right" : "left",
                                                letterSpacing: isNumeric ? 0 : 0.2,
                                                textTransform: isNumeric ? undefined : "uppercase",
                                            }}>
                                                {s.value != null ? s.value : "—"}
                                                {s.percentile != null ? ` (${s.percentile}%ile)` : ""}
                                            </span>
                                            <span style={{
                                                color: C.textTertiary, fontSize: 11,
                                                lineHeight: 1.4,
                                            }}>
                                                {s.note || ""}
                                            </span>
                                        </div>
                                    )
                                })}
                            </div>
                        </div>
                    )}

                    {/* Self-attribution */}
                    {data.model_meta && (
                        <div style={{ paddingTop: S.lg }}>
                            <div style={subLabelStyle}>모델 출처</div>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                {data.model_meta.probit && (
                                    <span style={{ color: C.textTertiary, fontSize: 11 }}>
                                        침체 probit · {data.model_meta.probit.source}
                                        {data.model_meta.probit.hit_rate ? ` · ${data.model_meta.probit.hit_rate}` : ""}
                                    </span>
                                )}
                                {data.model_meta.horizon_returns && (
                                    <span style={{ color: C.textTertiary, fontSize: 11 }}>
                                        Horizon 분포 · {data.model_meta.horizon_returns.source}
                                    </span>
                                )}
                                {data.as_of && (
                                    <span style={{ color: C.textDisabled, fontSize: 10, ...MONO, paddingTop: 4 }}>
                                        as_of {new Date(data.as_of).toLocaleString("ko-KR")}
                                    </span>
                                )}
                            </div>
                        </div>
                    )}
                </>
            )}
        </div>
    )
}


/* 스타일 */
const shell: CSSProperties = {
    width: "100%", boxSizing: "border-box",
    background: C.bgPage, borderRadius: 14,
    padding: `${S.md}px ${S.lg}px`,
    fontFamily: FONT, color: C.textPrimary,
    display: "flex", flexDirection: "column",
}

const subLabelStyle: CSSProperties = {
    color: C.textTertiary, fontSize: 10, fontWeight: 700,
    letterSpacing: 0.5, textTransform: "uppercase",
    paddingBottom: S.sm,
}


MarketHorizon.defaultProps = {
    dataUrl: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/portfolio.json",
    refreshInterval: 600,
    defaultExpanded: false,
}

addPropertyControls(MarketHorizon, {
    dataUrl: { type: ControlType.String, title: "JSON URL", defaultValue: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/portfolio.json" },
    refreshInterval: { type: ControlType.Number, title: "새로고침(초)", defaultValue: 600, min: 60, max: 3600, step: 60 },
    defaultExpanded: { type: ControlType.Boolean, title: "처음부터 펼침", defaultValue: false },
})
