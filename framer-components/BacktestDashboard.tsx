import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState } from "react"

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


interface Props {
    dataUrl: string
}

function bustPortfolioUrl(url: string): string {
    const u = (url || "").trim()
    if (!u) return u
    const sep = u.includes("?") ? "&" : "?"
    return `${u}${sep}_=${Date.now()}`
}

function fetchPortfolioJson(url: string, signal?: AbortSignal): Promise<any> {
    return fetch(bustPortfolioUrl(url), {
        cache: "no-store",
        mode: "cors",
        credentials: "omit",
        signal,
    })
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

export default function BacktestDashboard(props: Props) {
    const { dataUrl } = props
    const [data, setData] = useState<any>(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [activePeriod, setActivePeriod] = useState("7d")

    useEffect(() => {
        if (!dataUrl) return
        const ac = new AbortController()
        setLoading(true)
        setError(null)
        fetchPortfolioJson(dataUrl, ac.signal)
            .then(d => { if (!ac.signal.aborted) setData(d) })
            .catch(() => { if (!ac.signal.aborted) setError("백테스트 데이터를 불러오지 못했습니다.") })
            .finally(() => { if (!ac.signal.aborted) setLoading(false) })
        return () => ac.abort()
    }, [dataUrl])

    const bt = data?.backtest_stats || {}
    const periods = bt.periods || {}
    const recs: any[] = bt.recommendations || []

    const periodKeys = Object.keys(periods)
    const selectedPeriod = periodKeys.includes(activePeriod) ? activePeriod : periodKeys[0] || ""

    useEffect(() => {
        if (!periodKeys.length) return
        if (!periodKeys.includes(activePeriod)) setActivePeriod(periodKeys[0])
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activePeriod, data?.backtest_stats])

    if (loading) {
        return (
            <div style={container}>
                <div style={headerRow}>
                    <span style={titleStyle}>추천 성과 백테스트</span>
                </div>
                <div style={{ color: C.textTertiary, fontSize: T.cap, textAlign: "center", padding: 40 }}>
                    백테스트 데이터를 불러오는 중...
                </div>
            </div>
        )
    }

    if (error) {
        return (
            <div style={container}>
                <div style={headerRow}>
                    <span style={titleStyle}>추천 성과 백테스트</span>
                </div>
                <div style={{ color: C.danger, fontSize: T.cap, textAlign: "center", padding: 40 }}>{error}</div>
            </div>
        )
    }

    if (!periodKeys.length) {
        return (
            <div style={container}>
                <div style={headerRow}>
                    <span style={titleStyle}>추천 성과 백테스트</span>
                </div>
                <div style={{ color: C.textTertiary, fontSize: T.cap, textAlign: "center", padding: 40 }}>
                    백테스트 데이터가 아직 없습니다. history 스냅샷이 2일 이상 쌓인 후 full 모드 실행 시 생성됩니다.
                </div>
            </div>
        )
    }

    const active = periods[selectedPeriod] || {}
    const filteredRecs = recs.filter((r: any) => r.period === selectedPeriod)

    return (
        <div style={container}>
            <div style={headerRow}>
                <span style={titleStyle}>추천 성과 백테스트</span>
                <span style={{ color: C.textTertiary, fontSize: T.cap }}>{bt.updated_at?.slice(0, 16) || ""}</span>
            </div>

            <div style={tabRow}>
                {periodKeys.map((pk) => (
                    <span
                        key={pk}
                        onClick={() => setActivePeriod(pk)}
                        style={{
                            ...tab,
                            color: activePeriod === pk ? C.accent : C.textTertiary,
                            borderBottom: activePeriod === pk ? "2px solid #B5FF19" : "2px solid transparent",
                        }}
                    >
                        {pk}
                    </span>
                ))}
            </div>

            <div style={metricsGrid}>
                <MetricBox
                    label="적중률"
                    value={active.hit_rate != null ? `${active.hit_rate}%` : "—"}
                    color={active.hit_rate >= 60 ? C.accent : active.hit_rate >= 40 ? C.watch : C.danger}
                />
                <MetricBox
                    label="평균 수익률"
                    value={active.avg_return != null ? `${active.avg_return >= 0 ? "+" : ""}${active.avg_return}%` : "—"}
                    color={active.avg_return >= 0 ? C.up : C.down}
                />
                <MetricBox label="종목 수" value={`${active.total_recs || 0}`} color={C.textTertiary} />
                <MetricBox
                    label="샤프 비율"
                    value={active.sharpe != null ? `${active.sharpe}` : "—"}
                    color={active.sharpe >= 1 ? C.accent : active.sharpe >= 0 ? C.textTertiary : C.danger}
                />
                <MetricBox
                    label="최대 수익"
                    value={active.max_return != null ? `+${active.max_return}%` : "—"}
                    color={C.success}
                />
                <MetricBox
                    label="최대 손실"
                    value={active.min_return != null ? `${active.min_return}%` : "—"}
                    color={C.danger}
                />
            </div>

            {active.hit_rate != null && (
                <div style={gaugeWrap}>
                    <div style={gaugeTrack}>
                        <div style={{ ...gaugeFill, width: `${Math.min(100, active.hit_rate)}%` }} />
                    </div>
                    <span style={{ color: C.textTertiary, fontSize: T.cap }}>
                        {active.hits || 0}적중 / {active.total_recs || 0}종목
                    </span>
                </div>
            )}

            {filteredRecs.length > 0 && (
                <div style={tableWrap}>
                    <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: 600, marginBottom: 6, display: "block" }}>
                        추천별 성과
                    </span>
                    {filteredRecs.slice(0, 10).map((r: any, i: number) => (
                        <div key={i} style={recRow}>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                <span style={{ color: C.textPrimary, fontSize: T.cap, fontWeight: 600 }}>{r.name}</span>
                                <span style={{ color: C.textTertiary, fontSize: T.cap }}>
                                    {r.rec_date} · {r.recommendation} · 브레인 {r.brain_score || "?"}
                                </span>
                            </div>
                            <div style={{ textAlign: "right" }}>
                                <div style={{
                                    color: r.return_pct >= 0 ? C.up : C.down,
                                    fontSize: T.body,
                                    fontWeight: 700,
                                }}>
                                    {typeof r.return_pct === "number" ? `${r.return_pct >= 0 ? "+" : ""}${r.return_pct.toFixed(1)}%` : "—"}
                                </div>
                                {/* rec_price/current_price 는 api/main.py 의 recommendations 출력부에서
                                    주입됨 (첫 추천 시 가격을 rec_price 로 고정, 현재가를 current_price 로). */}
                                <div style={{ color: C.textTertiary, fontSize: T.cap }}>
                                    {r.rec_price?.toLocaleString()} → {r.current_price?.toLocaleString()}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}

function MetricBox({ label, value, color }: { label: string; value: string; color: string }) {
    return (
        <div style={metricBox}>
            <span style={{ color: C.textTertiary, fontSize: T.cap, fontWeight: 600 }}>{label}</span>
            <span style={{ color, fontSize: T.title, fontWeight: 800, fontFamily: FONT }}>{value}</span>
        </div>
    )
}

const DATA_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/gh-pages/portfolio.json"

BacktestDashboard.defaultProps = {
    dataUrl: DATA_URL,
}

addPropertyControls(BacktestDashboard, {
    dataUrl: {
        type: ControlType.String,
        title: "데이터 URL",
        defaultValue: DATA_URL,
    },
})

const font = FONT

const container: React.CSSProperties = {
    width: "100%",
    background: C.bgElevated,
    border: `1px solid ${C.border}`,
    borderRadius: 16,
    padding: 16,
    fontFamily: font,
    boxSizing: "border-box",
    display: "flex",
    flexDirection: "column",
    gap: 14,
}

const headerRow: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
}

const titleStyle: React.CSSProperties = {
    color: C.textPrimary,
    fontSize: T.body,
    fontWeight: 700,
    fontFamily: font,
}

const tabRow: React.CSSProperties = {
    display: "flex",
    gap: 16,
}

const tab: React.CSSProperties = {
    fontSize: T.cap,
    fontWeight: 600,
    cursor: "pointer",
    paddingBottom: 4,
    fontFamily: font,
    transition: "color 0.15s",
}

const metricsGrid: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: 8,
}

const metricBox: React.CSSProperties = {
    background: C.bgPage,
    borderRadius: R.md,
    padding: "10px 12px",
    display: "flex",
    flexDirection: "column",
    gap: 4,
    alignItems: "center",
    textAlign: "center",
}

const gaugeWrap: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 8,
}

const gaugeTrack: React.CSSProperties = {
    flex: 1,
    height: 8,
    borderRadius: R.sm,
    background: C.bgElevated,
    overflow: "hidden",
}

const gaugeFill: React.CSSProperties = {
    height: "100%",
    borderRadius: R.sm,
    background: "linear-gradient(90deg, #FF4D4D, #FFD600, #B5FF19)",
    transition: "width 0.5s",
}

const tableWrap: React.CSSProperties = {
    borderTop: `1px solid ${C.border}`,
    paddingTop: 10,
}

const recRow: React.CSSProperties = {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "8px 0",
    borderBottom: `1px solid ${C.border}`,
}
