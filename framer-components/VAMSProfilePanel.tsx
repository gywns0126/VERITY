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
const FONT = "'Inter', 'Pretendard', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


const DATA_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/portfolio.json"
const HISTORY_URL = "https://raw.githubusercontent.com/gywns0126/VERITY/main/data/history.json"
const INITIAL_CASH = 10_000_000

const font = "'Inter', 'Pretendard', -apple-system, sans-serif"
const BG = C.bgPage
const CARD = C.bgCard
const BORDER = C.border
const MUTED = C.textSecondary
const WHITE = "#fff"
const ACCENT = C.accent
const UP = "#F04452"
const DOWN = "#3182F6"

function fetchJson(url: string): Promise<any> {
    const sep = url.includes("?") ? "&" : "?"
    return fetch(`${url}${sep}_=${Date.now()}`, { cache: "no-store", mode: "cors", credentials: "omit" })
        .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
        .then((t) => JSON.parse(t.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null").replace(/-null/g, "null")))
}

function fmtKRW(n: number): string {
    if (!Number.isFinite(n)) return "—"
    const abs = Math.abs(n)
    const sign = n < 0 ? "-" : ""
    if (abs >= 100_000_000) return `${sign}${(abs / 100_000_000).toFixed(1)}억`
    if (abs >= 10_000) return `${sign}${Math.round(abs / 10_000).toLocaleString("ko-KR")}만`
    return `${sign}${Math.round(abs).toLocaleString("ko-KR")}`
}

function fmtPct(n: number, digits = 2): string {
    if (!Number.isFinite(n)) return "—"
    const sign = n > 0 ? "+" : ""
    return `${sign}${n.toFixed(digits)}%`
}

function pctColor(n: number): string {
    if (n > 0) return UP
    if (n < 0) return DOWN
    return MUTED
}

function daysSince(dateStr: string): number {
    const d = new Date(dateStr)
    return Math.floor((Date.now() - d.getTime()) / 86_400_000)
}

// ── 상단 요약 수치 카드
function StatBox({ label, value, sub, valueColor }: { label: string; value: string; sub?: string; valueColor?: string }) {
    return (
        <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: "10px 14px", display: "flex", flexDirection: "column", gap: 2, flex: 1 }}>
            <span style={{ fontSize: 12, color: MUTED }}>{label}</span>
            <span style={{ fontSize: 18, fontWeight: 700, color: valueColor || WHITE, lineHeight: 1.2 }}>{value}</span>
            {sub && <span style={{ fontSize: 12, color: MUTED }}>{sub}</span>}
        </div>
    )
}

// ── 보유 종목 카드
function HoldingCard({ h }: { h: any }) {
    const ret: number = h.return_pct ?? 0
    const color = pctColor(ret)
    const days = daysSince(h.buy_date)
    const qty = typeof h.quantity === "number" ? h.quantity : 0
    const buyPrice = typeof h.buy_price === "number" ? h.buy_price : 0
    const curPrice = typeof h.current_price === "number" ? h.current_price : 0
    const investedKRW = typeof h.total_cost === "number" ? h.total_cost : buyPrice * qty
    const currentKRW = curPrice * qty
    const pnl = Number.isFinite(currentKRW) && Number.isFinite(investedKRW) ? currentKRW - investedKRW : 0

    return (
        <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: "10px 12px", display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: WHITE }}>{h.name}</div>
                    <div style={{ fontSize: 12, color: MUTED, marginTop: 1 }}>{h.ticker} · {days}일 보유</div>
                </div>
                <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color }}>{fmtPct(ret)}</div>
                    <div style={{ fontSize: 12, color }}>{fmtKRW(pnl)}원</div>
                </div>
            </div>

            {/* 수익률 바 */}
            <div style={{ position: "relative", height: 4, borderRadius: 2, background: "#2a2a2a", overflow: "hidden" }}>
                <div style={{
                    position: "absolute",
                    left: ret >= 0 ? "50%" : `${Math.max(0, 50 + ret * 2.5)}%`,
                    width: `${Math.min(50, Math.abs(ret) * 2.5)}%`,
                    height: "100%",
                    borderRadius: 2,
                    background: color,
                }} />
                <div style={{ position: "absolute", left: "50%", top: 0, width: 1, height: "100%", background: "#444" }} />
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: MUTED }}>
                <span>{h.quantity}주 · 매수 {fmtKRW(h.buy_price)}원</span>
                <span>현재 {fmtKRW(h.current_price)}원</span>
            </div>
        </div>
    )
}

// ── 매매 이력 행
function TradeRow({ t }: { t: any }) {
    const isBuy = t.type === "BUY"
    const color = isBuy ? ACCENT : MUTED
    const pnlColor = t.pnl != null ? pctColor(t.pnl) : MUTED
    const dateStr = (t.date || "").slice(5, 16)

    return (
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 0", borderBottom: `1px solid ${BORDER}` }}>
            <span style={{ fontSize: 12, fontWeight: 700, color, background: `${color}18`, padding: "2px 6px", borderRadius: 6, minWidth: 28, textAlign: "center" }}>
                {isBuy ? "매수" : "매도"}
            </span>
            <span style={{ fontSize: 12, fontWeight: 600, color: WHITE, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {t.name}
            </span>
            <span style={{ fontSize: 12, color: MUTED, flexShrink: 0 }}>{dateStr}</span>
            {t.pnl != null && (
                <span style={{ fontSize: 12, fontWeight: 600, color: pnlColor, flexShrink: 0 }}>
                    {fmtKRW(t.pnl)}원
                </span>
            )}
        </div>
    )
}

interface Props {
    dataUrl: string
    historyUrl: string
}

export default function VAMSProfilePanel(props: Props) {
    const { dataUrl, historyUrl } = props
    const [vams, setVams] = useState<any>(null)
    const [history, setHistory] = useState<any[]>([])
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState("")

    useEffect(() => {
        const pUrl = dataUrl || DATA_URL
        const hUrl = historyUrl || HISTORY_URL

        Promise.all([fetchJson(pUrl), fetchJson(hUrl).catch(() => [])])
            .then(([portfolio, hist]) => {
                const v = portfolio?.vams
                if (!v) { setError("vams 데이터 없음"); return }
                setVams(v)
                setHistory(Array.isArray(hist) ? hist.slice().reverse() : [])
            })
            .catch((e) => setError(e.message))
            .finally(() => setLoading(false))
    }, [dataUrl, historyUrl])

    if (loading) return (
        <div style={{ fontFamily: font, background: BG, color: MUTED, padding: 40, borderRadius: 12, textAlign: "center", fontSize: 13 }}>
            로딩 중…
        </div>
    )
    if (error) return (
        <div style={{ fontFamily: font, background: BG, color: UP, padding: 20, borderRadius: 12, textAlign: "center", fontSize: 13 }}>
            {error}
        </div>
    )

    const totalAsset: number = vams.total_asset ?? INITIAL_CASH
    const cash: number = vams.cash ?? 0
    const totalReturnPct: number = vams.total_return_pct ?? 0
    const realizedPnl: number = vams.total_realized_pnl ?? 0
    const holdings: any[] = vams.holdings ?? []
    const sim = vams.simulation_stats ?? {}

    const investedAmt = totalAsset - cash
    const cashPct = totalAsset > 0 ? (cash / totalAsset) * 100 : 0
    const unrealizedPnl = holdings.reduce((acc, h) => {
        const cur = h.current_price * h.quantity
        const cost = h.total_cost ?? (h.buy_price * h.quantity)
        return acc + (cur - cost)
    }, 0)

    const recentTrades = history.slice(0, 12)

    return (
        <div style={{ fontFamily: font, background: BG, padding: 16, borderRadius: 14, display: "flex", flexDirection: "column", gap: 14, width: "100%", boxSizing: "border-box" }}>

            {/* 헤더 */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div>
                    <span style={{ fontSize: 16, fontWeight: 700, color: WHITE }}>VAMS 가상 투자</span>
                    <span style={{ fontSize: 12, color: MUTED, marginLeft: 8 }}>Virtual Asset Management</span>
                </div>
                <span style={{ fontSize: 20, fontWeight: 800, color: pctColor(totalReturnPct) }}>
                    {fmtPct(totalReturnPct)}
                </span>
            </div>

            {/* 총 자산 + 현금 */}
            <div style={{ background: `${ACCENT}0d`, border: `1px solid ${ACCENT}30`, borderRadius: 12, padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                    <div style={{ fontSize: 12, color: MUTED, marginBottom: 2 }}>총 평가자산</div>
                    <div style={{ fontSize: 24, fontWeight: 800, color: WHITE }}>{fmtKRW(totalAsset)}원</div>
                    <div style={{ fontSize: 12, color: MUTED, marginTop: 2 }}>초기 {fmtKRW(INITIAL_CASH)}원 대비</div>
                </div>
                <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 12, color: MUTED, marginBottom: 2 }}>현금 잔고</div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: WHITE }}>{fmtKRW(cash)}원</div>
                    <div style={{ fontSize: 12, color: MUTED }}>{cashPct.toFixed(0)}% 현금화</div>
                </div>
            </div>

            {/* 요약 수치 4개 */}
            <div style={{ display: "flex", gap: 8 }}>
                <StatBox
                    label="미실현 손익"
                    value={`${fmtKRW(unrealizedPnl)}원`}
                    valueColor={pctColor(unrealizedPnl)}
                    sub={`보유 ${holdings.length}종목`}
                />
                <StatBox
                    label="확정 손익"
                    value={`${fmtKRW(sim.realized_pnl ?? realizedPnl)}원`}
                    valueColor={pctColor(sim.realized_pnl ?? realizedPnl)}
                    sub={`총 ${sim.total_trades ?? 0}회 매매`}
                />
                <StatBox
                    label="승률"
                    value={sim.win_rate != null ? `${sim.win_rate.toFixed(0)}%` : "—"}
                    sub={sim.win_count != null ? `${sim.win_count}승 ${sim.loss_count}패` : ""}
                    valueColor={sim.win_rate >= 50 ? ACCENT : MUTED}
                />
                <StatBox
                    label="최대 낙폭"
                    value={sim.max_drawdown_pct != null ? fmtPct(sim.max_drawdown_pct) : "—"}
                    valueColor={DOWN}
                    sub="MDD"
                />
            </div>

            {/* 현재 보유 종목 */}
            {holdings.length > 0 && (
                <div>
                    <div style={{ fontSize: 12, fontWeight: 600, color: MUTED, marginBottom: 8 }}>보유 종목</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        {holdings.map((h: any) => <HoldingCard key={h.ticker} h={h} />)}
                    </div>
                </div>
            )}

            {holdings.length === 0 && (
                <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: 16, textAlign: "center", color: MUTED, fontSize: 12 }}>
                    현재 보유 종목 없음 — 현금 {cashPct.toFixed(0)}% 대기 중
                </div>
            )}

            {/* 베스트 / 워스트 거래 */}
            {(sim.best_trade || sim.worst_trade) && (
                <div style={{ display: "flex", gap: 8 }}>
                    {sim.best_trade && (
                        <div style={{ flex: 1, background: `${UP}0d`, border: `1px solid ${UP}30`, borderRadius: 10, padding: "8px 12px" }}>
                            <div style={{ fontSize: 12, color: UP, fontWeight: 600, marginBottom: 3 }}>최고 거래</div>
                            <div style={{ fontSize: 12, fontWeight: 700, color: WHITE }}>{sim.best_trade.name}</div>
                            <div style={{ fontSize: 12, color: UP, fontWeight: 600 }}>+{fmtKRW(sim.best_trade.pnl)}원</div>
                        </div>
                    )}
                    {sim.worst_trade && (
                        <div style={{ flex: 1, background: `${DOWN}0d`, border: `1px solid ${DOWN}30`, borderRadius: 10, padding: "8px 12px" }}>
                            <div style={{ fontSize: 12, color: DOWN, fontWeight: 600, marginBottom: 3 }}>최악 거래</div>
                            <div style={{ fontSize: 12, fontWeight: 700, color: WHITE }}>{sim.worst_trade.name}</div>
                            <div style={{ fontSize: 12, color: DOWN, fontWeight: 600 }}>{fmtKRW(sim.worst_trade.pnl)}원</div>
                        </div>
                    )}
                </div>
            )}

            {/* 매매 이력 */}
            {recentTrades.length > 0 && (
                <div>
                    <div style={{ fontSize: 12, fontWeight: 600, color: MUTED, marginBottom: 4 }}>최근 매매 이력</div>
                    <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 10, padding: "4px 12px" }}>
                        {recentTrades.map((t: any, i: number) => <TradeRow key={i} t={t} />)}
                    </div>
                </div>
            )}
        </div>
    )
}

VAMSProfilePanel.defaultProps = {
    dataUrl: DATA_URL,
    historyUrl: HISTORY_URL,
}

addPropertyControls(VAMSProfilePanel, {
    dataUrl: {
        type: ControlType.String,
        title: "Portfolio URL",
        defaultValue: DATA_URL,
    },
    historyUrl: {
        type: ControlType.String,
        title: "History URL",
        defaultValue: HISTORY_URL,
    },
})
