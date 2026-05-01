import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"

/**
 * VERITY — Today Actions Card (Sprint 11 결함 7)
 *
 * 베테랑 due diligence 평가:
 *   "49 컴포넌트 정보 분산이 decision fatigue 의 가장 큰 이유.
 *    아침에 '오늘의 액션 3개 (매수 1, 매도 1, 관찰 1)' 가 첫 화면이어야."
 *
 * portfolio.daily_actions 를 fetch 해서 BUY/SELL/WATCH 단일 액션 게이트 표시.
 * backend: api/intelligence/daily_actions.py (commit 10379c6).
 *
 * 매수: STRONG_BUY/BUY 등급 + 보유 X + brain_score 최고
 * 매도: 보유 중 return_pct < -3% (정상 노이즈는 hold 유지 — 액션 없음)
 * 관찰: brain_score 55-69 + 보유 X (BUY 직전 영역)
 */

const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgHover: "#1F2028",
    border: "#23242C", borderStrong: "#34353D",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76",
    accent: "#B5FF19",
    buy: "#22C55E", buySoft: "rgba(34,197,94,0.12)",
    sell: "#EF4444", sellSoft: "rgba(239,68,68,0.12)",
    watch: "#FFD600", watchSoft: "rgba(255,214,0,0.12)",
    ok: "#22C55E", warning: "#FFD600", critical: "#EF4444",
    none: "#6B6E76",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"

type Action = {
    action: "buy" | "sell" | "watch"
    ticker?: string
    name?: string
    price?: number
    grade?: string
    brain_score?: number
    verdict?: string
    reason?: string
    sector?: string
    currency?: string
    return_pct?: number
    quantity?: number
    buy_price?: number
    current_price?: number
    buy_date?: string
    confidence_days?: number
    ic_ir?: number
    hit_rate?: number
} | null

type DailyActions = {
    buy: Action
    sell: Action
    watch: Action
    _meta?: any
}

function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    const u = (url || "").trim()
    const sep = u.includes("?") ? "&" : "?"
    const busted = `${u}${sep}_=${Date.now()}`
    return fetch(busted, { cache: "no-store", mode: "cors", credentials: "omit", signal })
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

// Framer ControlType.Link 슬롯 — href 있으면 <a>, 없으면 <div>
function LinkBox(props: {
    href?: string
    children: React.ReactNode
    style?: React.CSSProperties
    title?: string
}) {
    const { href, children, style, title } = props
    const [hover, setHover] = useState(false)
    const isLinked = !!(href && href.trim())
    const baseStyle: React.CSSProperties = {
        display: "block",
        textDecoration: "none",
        color: "inherit",
        cursor: isLinked ? "pointer" : "default",
        transition: "background 120ms, border-color 120ms",
        ...style,
    }
    if (isLinked && hover) {
        baseStyle.background = C.bgHover
        baseStyle.borderColor = C.borderStrong
    }
    if (isLinked) {
        return (
            <a href={href} title={title} style={baseStyle}
                onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
                {children}
            </a>
        )
    }
    return <div title={title} style={baseStyle}>{children}</div>
}

function fmtPct(v: number | null | undefined): string {
    if (v === null || v === undefined || Number.isNaN(v)) return "—"
    const sign = v > 0 ? "+" : ""
    return `${sign}${v.toFixed(2)}%`
}
function pnlColor(v: number | null | undefined): string {
    if (v === null || v === undefined || Number.isNaN(v)) return C.textTertiary
    if (v > 0) return C.buy
    if (v < 0) return C.sell
    return C.textSecondary
}
function statusColor(s: string): string {
    if (s === "ok") return C.ok
    if (s === "warning") return C.warning
    if (s === "critical") return C.critical
    return C.none
}

const ACTION_META: Record<string, { label: string; color: string; soft: string; emoji: string }> = {
    buy: { label: "매수", color: C.buy, soft: C.buySoft, emoji: "📈" },
    sell: { label: "매도", color: C.sell, soft: C.sellSoft, emoji: "📉" },
    watch: { label: "관찰", color: C.watch, soft: C.watchSoft, emoji: "👀" },
}

function ActionCard({ kind, data }: { kind: "buy" | "sell" | "watch"; data: Action }) {
    const meta = ACTION_META[kind]
    const card: React.CSSProperties = {
        background: C.bgCard,
        border: `1px solid ${data ? meta.color : C.border}`,
        borderLeft: `4px solid ${data ? meta.color : C.none}`,
        borderRadius: 12,
        padding: 14,
        flex: 1,
        minWidth: 0,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        boxShadow: data ? `0 0 12px ${meta.soft}` : "none",
    }
    const headerRow: React.CSSProperties = {
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 8,
    }
    const labelStyle: React.CSSProperties = {
        color: data ? meta.color : C.none,
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: 1,
        textTransform: "uppercase",
    }

    if (!data) {
        return (
            <div style={card}>
                <div style={headerRow}>
                    <span style={labelStyle}>{meta.emoji} {meta.label}</span>
                </div>
                <div style={{ color: C.textTertiary, fontSize: 13, padding: "8px 0" }}>
                    이번 사이클 액션 없음
                </div>
                <div style={{ color: C.textTertiary, fontSize: 11 }}>
                    {kind === "buy" && "BUY 후보 추천 0건"}
                    {kind === "sell" && "보유 종목 손절 임계 -3% 이내"}
                    {kind === "watch" && "관찰 후보 추천 0건"}
                </div>
            </div>
        )
    }

    const isFromHolding = kind === "sell"
    const ticker = data.ticker || "—"
    const name = data.name || ticker
    const isUS = data.currency === "USD"

    const priceVal = isFromHolding
        ? data.current_price
        : (data.price || data.current_price)
    const priceStr = typeof priceVal === "number"
        ? (isUS ? `$${priceVal.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                : `${Math.round(priceVal).toLocaleString()}원`)
        : "—"

    return (
        <div style={card}>
            <div style={headerRow}>
                <span style={labelStyle}>{meta.emoji} {meta.label}</span>
                {data.grade && (
                    <span style={{ color: meta.color, fontSize: 10, fontWeight: 700, letterSpacing: 0.5 }}>
                        {data.grade}
                    </span>
                )}
                {isFromHolding && typeof data.return_pct === "number" && (
                    <span style={{ color: C.sell, fontSize: 12, fontWeight: 700, ...{ fontFamily: FONT_MONO } }}>
                        {data.return_pct.toFixed(1)}%
                    </span>
                )}
            </div>

            <div>
                <div style={{ color: C.textPrimary, fontSize: 16, fontWeight: 700, marginBottom: 2 }}>
                    {name}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ color: C.textTertiary, fontSize: 11, fontFamily: FONT_MONO }}>
                        {ticker}
                    </span>
                    {data.sector && (
                        <span style={{ color: C.textTertiary, fontSize: 11 }}>
                            · {data.sector}
                        </span>
                    )}
                </div>
            </div>

            <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <span style={{ color: meta.color, fontSize: 18, fontWeight: 800, fontFamily: FONT_MONO }}>
                    {priceStr}
                </span>
                {typeof data.brain_score === "number" && !isFromHolding && (
                    <span style={{ color: C.textSecondary, fontSize: 11 }}>
                        Brain {Math.round(data.brain_score)}
                    </span>
                )}
                {isFromHolding && data.quantity != null && (
                    <span style={{ color: C.textSecondary, fontSize: 11 }}>
                        {data.quantity}주
                    </span>
                )}
            </div>

            {data.reason && (
                <div style={{
                    color: C.textSecondary,
                    fontSize: 12,
                    lineHeight: 1.5,
                    paddingTop: 4,
                    borderTop: `1px solid ${C.border}`,
                    marginTop: 2,
                }}>
                    {data.reason}
                </div>
            )}

            {(data.confidence_days != null || data.ic_ir != null || data.hit_rate != null) && (
                <div
                    title="검증 누적일수 / IC IR / 적중률 — 이 신호 얼마나 믿어도 되나"
                    style={{
                        display: "flex",
                        gap: 8,
                        fontFamily: FONT_MONO,
                        fontSize: 10,
                        color: C.textTertiary,
                        paddingTop: 4,
                        borderTop: `1px dashed ${C.border}`,
                        marginTop: 2,
                    }}
                >
                    <span>📊 {data.confidence_days != null ? `${data.confidence_days}d` : "—"}</span>
                    <span>· IC·IR {data.ic_ir != null ? data.ic_ir.toFixed(2) : "—"}</span>
                    <span>· 적중 {data.hit_rate != null ? `${(data.hit_rate * 100).toFixed(0)}%` : "—"}</span>
                </div>
            )}
        </div>
    )
}

export default function TodayActionsCard(props: any) {
    const apiUrl = props.apiUrl || "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json"
    const layout = props.layout || "row"
    const showHeader = props.showHeader !== false
    const showTopStrip = props.showTopStrip !== false
    const showBottomStrip = props.showBottomStrip !== false

    const [actions, setActions] = useState<DailyActions | null>(null)
    const [payload, setPayload] = useState<any>(null)
    const [error, setError] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)
    const [updatedAt, setUpdatedAt] = useState<string | null>(null)

    useEffect(() => {
        const ctrl = new AbortController()
        let alive = true

        const load = async () => {
            try {
                setLoading(true)
                setError(null)
                const json = await fetchPortfolioJson(apiUrl, ctrl.signal)
                if (!alive) return
                setPayload(json)
                const da = json?.daily_actions
                if (!da) {
                    setError("daily_actions 필드 없음 (cron 갱신 대기)")
                } else {
                    setActions(da)
                }
                setUpdatedAt(json?.updated_at || null)
            } catch (e: any) {
                if (!alive) return
                setError(e?.message || "fetch 실패")
            } finally {
                if (alive) setLoading(false)
            }
        }
        load()
        const id = setInterval(load, 5 * 60 * 1000)  // 5분 마다 재fetch
        return () => {
            alive = false
            ctrl.abort()
            clearInterval(id)
        }
    }, [apiUrl])

    // ─── TOP/BOTTOM strip 데이터 추출 (다중 경로 fallback, 누락 시 — 표시) ───
    const pnlToday: number | null =
        payload?.portfolio_summary?.today_pct ?? payload?.portfolio?.today_pct ?? payload?.pnl?.today ?? null
    const pnlCum: number | null =
        payload?.portfolio_summary?.cumulative_pct ?? payload?.portfolio?.cumulative_pct ?? payload?.pnl?.cumulative ?? null
    const isPaper: boolean =
        payload?.portfolio_summary?.is_paper ?? payload?.portfolio?.is_paper ?? true
    const systemStatus: string =
        payload?.system_health?.overall_status ?? payload?.health?.overall_status ?? "unknown"
    const decisionQueue: any[] = payload?.decision_queue ?? payload?.queue ?? payload?.followups ?? []
    const decisionCount = Array.isArray(decisionQueue) ? decisionQueue.length : 0
    const validationDays: number | null =
        payload?.validation?.cumulative_days ?? payload?.vams?.cumulative_days ?? null
    const validationTarget: number | null =
        payload?.validation?.target_days ?? payload?.vams?.target_days ?? null
    const evolutionDiff: any[] =
        payload?.evolution?.brain_weights_diff ?? payload?.brain_weights_diff ?? []
    const evolutionCount = Array.isArray(evolutionDiff) ? evolutionDiff.length : 0
    const evolutionLabel: string =
        payload?.evolution?.label ?? (evolutionCount > 0 ? `${evolutionCount}개 변경` : "변경 없음")

    const container: React.CSSProperties = {
        background: C.bgPage,
        padding: 16,
        fontFamily: FONT,
        color: C.textPrimary,
        minHeight: 200,
    }

    const stack: React.CSSProperties = {
        display: "flex",
        flexDirection: layout === "column" ? "column" : "row",
        flexWrap: layout === "row" ? "wrap" : "nowrap",
        gap: 12,
    }

    // ─── strip 공통 스타일 ───
    const kpiBox: React.CSSProperties = {
        flex: 1,
        background: C.bgCard,
        border: `1px solid ${C.border}`,
        borderRadius: 10,
        padding: "12px 14px",
        minWidth: 0,
    }
    const kpiLabel: React.CSSProperties = {
        fontSize: 10,
        color: C.textTertiary,
        textTransform: "uppercase",
        letterSpacing: 1,
        marginBottom: 4,
    }
    const kpiValue: React.CSSProperties = {
        fontSize: 18,
        fontWeight: 700,
        fontFamily: FONT_MONO,
    }
    const stripRow: React.CSSProperties = {
        display: "flex",
        gap: 10,
        flexWrap: "wrap",
        marginBottom: 12,
    }

    const TopStrip = () => (
        <div style={stripRow}>
            <LinkBox href={props.portfolioLink} style={kpiBox} title="포트폴리오 상세">
                <div style={kpiLabel}>포트폴리오 {isPaper ? "(가상)" : "(실계좌)"}</div>
                <div style={{ display: "flex", gap: 12, alignItems: "baseline" }}>
                    <span style={{ ...kpiValue, color: pnlColor(pnlToday) }}>{fmtPct(pnlToday)}</span>
                    <span style={{ fontSize: 10, color: C.textTertiary }}>오늘</span>
                    <span style={{ ...kpiValue, fontSize: 14, color: pnlColor(pnlCum) }}>{fmtPct(pnlCum)}</span>
                    <span style={{ fontSize: 10, color: C.textTertiary }}>누적</span>
                </div>
            </LinkBox>
            <LinkBox href={props.systemHealthLink} style={kpiBox} title="시스템 상태">
                <div style={kpiLabel}>시스템 신호등</div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{
                        width: 10, height: 10, borderRadius: "50%",
                        background: statusColor(systemStatus), display: "inline-block",
                    }} />
                    <span style={{ ...kpiValue, color: statusColor(systemStatus), textTransform: "uppercase" }}>
                        {systemStatus}
                    </span>
                </div>
            </LinkBox>
            <LinkBox href={props.decisionQueueLink} style={kpiBox} title="결정 큐">
                <div style={kpiLabel}>결정 큐</div>
                <div style={{ ...kpiValue, color: decisionCount > 0 ? C.accent : C.textSecondary }}>
                    {decisionCount}
                    <span style={{ fontSize: 11, color: C.textTertiary, marginLeft: 4, fontFamily: FONT }}>개</span>
                </div>
            </LinkBox>
        </div>
    )

    const BottomStrip = () => (
        <div style={{ ...stripRow, marginBottom: 0, marginTop: 12 }}>
            <LinkBox href={props.validationLink} style={kpiBox} title="검증 추이">
                <div style={kpiLabel}>누적 검증일수</div>
                <div style={kpiValue}>
                    {validationDays ?? "—"}
                    {validationTarget ? (
                        <span style={{ fontSize: 11, color: C.textTertiary, marginLeft: 6, fontFamily: FONT }}>
                            / {validationTarget}일
                        </span>
                    ) : null}
                </div>
            </LinkBox>
            <LinkBox href={props.evolutionLink} style={kpiBox} title="brain_weights 디프">
                <div style={kpiLabel}>진화 (어제 대비)</div>
                <div style={{ ...kpiValue, fontSize: 14, color: evolutionCount > 0 ? C.accent : C.textSecondary }}>
                    {evolutionLabel}
                </div>
            </LinkBox>
        </div>
    )

    if (loading && !actions) {
        return (
            <div style={container}>
                {showTopStrip && <TopStrip />}
                <div style={{ color: C.textTertiary, fontSize: 13, textAlign: "center", padding: 40 }}>
                    로딩 중…
                </div>
                {showBottomStrip && <BottomStrip />}
            </div>
        )
    }

    if (error && !actions) {
        return (
            <div style={container}>
                {showTopStrip && <TopStrip />}
                <div style={{ color: C.sell, fontSize: 13, textAlign: "center", padding: 20 }}>
                    ⚠️ {error}
                </div>
                {showBottomStrip && <BottomStrip />}
            </div>
        )
    }

    return (
        <div style={container}>
            {showTopStrip && <TopStrip />}
            {showHeader && (
                <div style={{
                    display: "flex",
                    alignItems: "baseline",
                    justifyContent: "space-between",
                    marginBottom: 12,
                }}>
                    <h2 style={{
                        margin: 0,
                        fontSize: 18,
                        fontWeight: 800,
                        color: C.accent,
                        letterSpacing: -0.3,
                    }}>
                        🎯 오늘의 액션
                    </h2>
                    {updatedAt && (
                        <span style={{ color: C.textTertiary, fontSize: 11, fontFamily: FONT_MONO }}>
                            {String(updatedAt).slice(0, 16).replace("T", " ")}
                        </span>
                    )}
                </div>
            )}

            <div style={stack}>
                <ActionCard kind="buy" data={actions?.buy || null} />
                <ActionCard kind="sell" data={actions?.sell || null} />
                <ActionCard kind="watch" data={actions?.watch || null} />
            </div>

            <div style={{
                marginTop: 12,
                color: C.textTertiary,
                fontSize: 10,
                lineHeight: 1.5,
                textAlign: "center",
            }}>
                매수 = STRONG_BUY/BUY 중 brain_score 최고 · 매도 = 보유 손실 -3%↑ ·
                관찰 = brain_score 55-69 BUY 직전 영역
            </div>
            {showBottomStrip && <BottomStrip />}
        </div>
    )
}

addPropertyControls(TodayActionsCard, {
    apiUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json",
        description: "VERITY portfolio.json (gh-pages 권장)",
    },
    layout: {
        type: ControlType.Enum,
        title: "Layout",
        options: ["row", "column"],
        optionTitles: ["가로 (3열)", "세로 (모바일)"],
        defaultValue: "row",
    },
    showHeader: {
        type: ControlType.Boolean,
        title: "Header",
        defaultValue: true,
    },
    showTopStrip: {
        type: ControlType.Boolean,
        title: "위 KPI strip",
        defaultValue: true,
        description: "포트폴리오·시스템·결정 큐",
    },
    showBottomStrip: {
        type: ControlType.Boolean,
        title: "아래 KPI strip",
        defaultValue: true,
        description: "검증 일수·진화 디프",
    },
    portfolioLink: {
        type: ControlType.Link,
        title: "→ 포트폴리오",
    },
    systemHealthLink: {
        type: ControlType.Link,
        title: "→ 시스템 상태",
    },
    decisionQueueLink: {
        type: ControlType.Link,
        title: "→ 결정 큐",
    },
    validationLink: {
        type: ControlType.Link,
        title: "→ 검증 추이",
    },
    evolutionLink: {
        type: ControlType.Link,
        title: "→ 진화 디프",
    },
})
