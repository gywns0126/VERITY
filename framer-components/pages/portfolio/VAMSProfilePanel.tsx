import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useRef, useState } from "react"

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆ (Neo Dark Terminal — _shared-patterns.ts 마스터)
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "rgba(255,255,255,0.06)", borderStrong: "rgba(255,255,255,0.10)", borderHover: "#B5FF17",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B5FF17", accentSoft: "rgba(181,255,23,0.12)",
    strongBuy: "#22C55E", buy: "#B5FF17", watch: "#FFD600", caution: "#F59E0B", avoid: "#EF4444",
    up: "#F04452", down: "#3182F6",
    info: "#5BA9FF", success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const G = {
    accent: "0 0 8px rgba(181,255,23,0.35)",
    accentSoft: "0 0 4px rgba(181,255,23,0.20)",
    accentStrong: "0 0 12px rgba(181,255,23,0.50)",
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


const DATA_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/portfolio.json"
const HISTORY_URL = "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/history.json"
const RAILWAY_STREAM_BASE = "https://verity-production-1e44.up.railway.app/stream"
const INITIAL_CASH = 10_000_000
const KR_TICKER_RE = /^[0-9]{6}$/

const font = FONT
const BG = C.bgPage
const CARD = C.bgCard
const BORDER = C.border
const MUTED = C.textSecondary
const WHITE = C.textPrimary
const ACCENT = C.accent
const UP = C.up
const DOWN = C.down

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

/* ──────────────────────────────────────────────────────────────
 * 세금 산식 (backend api/vams/engine.py compute_adjusted_return 정합)
 * Perplexity 자문 2026-05-17 (메모리 [[after-tax-sharpe-kr-us]] 박힘)
 *
 * KR 0% (비대주주 비과세) / US 22% (250만 공제 후) / 배당 KR 15.4% / US 15.0%
 * 증권거래세 KR 0.18% (일반주) / KR ETF 0% / US 0% / FX 0.3%/년
 * ────────────────────────────────────────────────────────────── */
const TAX_RATES = {
    KR_SELL: 0.0018,       // KR 일반주 증권거래세
    KR_ETF_SELL: 0.0,      // KR ETF 면제
    US_SELL: 0.0,          // US 거래세 0
    US_CAPITAL_GAINS: 0.22, // US 양도세 (국세 20% + 지방세 2%)
    US_DEDUCTION: 2_500_000, // 양도소득 기본공제 (연 1회)
    DIV_KR: 0.154,         // 배당세 KR (소득세 14% + 지방세 1.4%)
    DIV_US: 0.150,         // 배당세 US (한미 조세조약, KR 추가 0%)
    US_FX_COST: 0.003,     // US 환전 0.3%/년 (왕복)
    SPREAD_BPS: 5,         // 호가 스프레드 5bp (왕복)
} as const

function isUSStock(h: any): boolean {
    const ac = h?.asset_class
    if (ac === "US_STOCK" || ac === "US_ETF") return true
    if (h?.currency === "USD") return true
    const ticker = String(h?.ticker || "").trim()
    return /[A-Z]/i.test(ticker) && !ticker.match(/^[0-9]+$/)
}

function isKREtf(h: any): boolean {
    return h?.asset_class === "KR_ETF"
}

/** 매도 시뮬 — 단일 종목 세금 분해 */
function simulateSell(h: any, sellQty: number, livePrice: number | undefined) {
    const qty = Math.min(sellQty, h.quantity ?? 0)
    const buyPx = h.buy_price ?? 0
    const curPx = livePrice && livePrice > 0 ? livePrice : (h.current_price ?? 0)
    const proceeds = curPx * qty
    const cost = buyPx * qty
    const grossPnl = proceeds - cost

    const isUS = isUSStock(h)
    const sellRate = isUS ? TAX_RATES.US_SELL
        : (isKREtf(h) ? TAX_RATES.KR_ETF_SELL : TAX_RATES.KR_SELL)

    const sellTax = proceeds * sellRate
    const spread = proceeds * (TAX_RATES.SPREAD_BPS / 10000)
    const fxCost = isUS ? proceeds * TAX_RATES.US_FX_COST : 0

    // US 양도세 (250만 공제 후 22%) — realized pnl 단일 종목 단순 가정
    // 정확히는 연간 통산, 여기는 "이 매도만 가정" 보수 추정
    let usCapGainsTax = 0
    if (isUS && grossPnl > 0) {
        const taxable = Math.max(0, grossPnl - TAX_RATES.US_DEDUCTION)
        usCapGainsTax = taxable * TAX_RATES.US_CAPITAL_GAINS
    }

    const totalTax = sellTax + spread + fxCost + usCapGainsTax
    const netPnl = grossPnl - totalTax
    const netReceived = proceeds - totalTax

    return {
        qty, proceeds, cost, grossPnl, netPnl, netReceived,
        sellTax, spread, fxCost, usCapGainsTax, totalTax,
        isUS,
    }
}

const NET_LABELS: Record<string, string> = {
    sell_tax_realized: "거래세 (실현)",
    sell_tax_unrealized_est: "거래세 (미실현)",
    spread_slippage_realized: "스프레드 (실현)",
    spread_slippage_unrealized_est: "스프레드 (미실현)",
    dividend_tax: "배당세",
    dividend_tax_kr: "배당세 KR",
    dividend_tax_us: "배당세 US",
    us_capital_gains_tax: "US 양도세 (실현)",
    us_capital_gains_tax_unrealized_est: "US 양도세 (미실현)",
    us_fx_cost_realized: "US 환전 (실현)",
    us_fx_cost_unrealized_est: "US 환전 (미실현)",
}

// ── 상단 요약 수치 카드
function StatBox({ label, value, sub, valueColor }: { label: string; value: string; sub?: string; valueColor?: string }) {
    return (
        <div style={{ background: CARD, borderRadius: 10, padding: "10px 14px", display: "flex", flexDirection: "column", gap: 2, flex: 1 }}>
            <span style={{ fontSize: 12, color: MUTED }}>{label}</span>
            <span style={{ fontSize: 18, fontWeight: 700, color: valueColor || WHITE, lineHeight: 1.2 }}>{value}</span>
            {sub && <span style={{ fontSize: 12, color: MUTED }}>{sub}</span>}
        </div>
    )
}

// ── 보유 종목 카드
// 2026-05-13: livePrice prop 추가 — Railway SSE 1초 단위 push 가격 우선. 폴백 = portfolio.json current_price.
function HoldingCard({ h, livePrice }: { h: any; livePrice?: number }) {
    const days = daysSince(h.buy_date)
    const qty = typeof h.quantity === "number" ? h.quantity : 0
    const buyPrice = typeof h.buy_price === "number" ? h.buy_price : 0
    const fallbackPrice = typeof h.current_price === "number" ? h.current_price : 0
    const curPrice = typeof livePrice === "number" && livePrice > 0 ? livePrice : fallbackPrice
    const isLive = typeof livePrice === "number" && livePrice > 0

    // live 가격으로 수익률 재계산 (SSE 가격이 매분 cron 보다 fresh).
    const ret: number = buyPrice > 0 ? ((curPrice - buyPrice) / buyPrice) * 100 : (h.return_pct ?? 0)
    const color = pctColor(ret)
    const investedKRW = typeof h.total_cost === "number" ? h.total_cost : buyPrice * qty
    const currentKRW = curPrice * qty
    const pnl = Number.isFinite(currentKRW) && Number.isFinite(investedKRW) ? currentKRW - investedKRW : 0

    return (
        <div style={{ background: CARD, borderRadius: 10, padding: "10px 12px", display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: WHITE, display: "flex", alignItems: "center", gap: 6 }}>
                        {h.name}
                        {isLive && (
                            <span title="실시간 (Railway SSE)" style={{
                                width: 6, height: 6, borderRadius: "50%",
                                background: ACCENT, boxShadow: G.accentSoft,
                            }} />
                        )}
                    </div>
                    <div style={{ fontSize: 12, color: MUTED, marginTop: 1 }}>{h.ticker} · {days}일 보유</div>
                </div>
                <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color }}>{fmtPct(ret)}</div>
                    <div style={{ fontSize: 12, color }}>{fmtKRW(pnl)}원</div>
                </div>
            </div>

            {/* 수익률 바 */}
            <div style={{ position: "relative", height: 4, borderRadius: 2, background: "transparent", overflow: "hidden" }}>
                <div style={{
                    position: "absolute",
                    left: ret >= 0 ? "50%" : `${Math.max(0, 50 + ret * 2.5)}%`,
                    width: `${Math.min(50, Math.abs(ret) * 2.5)}%`,
                    height: "100%",
                    borderRadius: 2,
                    background: color,
                }} />
                <div style={{ position: "absolute", left: "50%", top: 0, width: 1, height: "100%", background: C.borderStrong }} />
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: MUTED }}>
                <span>{h.quantity}주 · 매수 {fmtKRW(h.buy_price)}원</span>
                <span>현재 {fmtKRW(curPrice)}원</span>
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
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 0", }}>
            <span style={{ fontSize: 12, fontWeight: 700, color, background: "transparent", padding: "2px 6px", borderRadius: 6, minWidth: 28, textAlign: "center" }}>
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

/* ──────────────────────────────────────────────────────────────
 * 세후 PnL 분해 — backend api/vams/engine.py compute_adjusted_return 결과 소비
 * portfolio.json `vams.adjusted_performance.deductions` 박힘. 5/17 리셋 직후 = 빈 dict,
 * VAMS 매매 누적 시 자동 채워짐. RULE 7 정합 (가설 N=일수 명시).
 * ────────────────────────────────────────────────────────────── */
function DeductionBreakdown({ adj, daysObserved }: { adj: any; daysObserved: number }) {
    const raw = adj?.raw_return_pct ?? 0
    const adjusted = adj?.adjusted_return_pct ?? 0
    const gap = adj?.gap_pp ?? 0
    const ded = adj?.deductions || {}
    const total = ded.total ?? 0

    // 항목별 row (값 0 이면 hide)
    const rows: { key: string; value: number }[] = []
    for (const k of [
        "sell_tax_realized", "sell_tax_unrealized_est",
        "spread_slippage_realized", "spread_slippage_unrealized_est",
        "dividend_tax_kr", "dividend_tax_us",
        "us_capital_gains_tax", "us_capital_gains_tax_unrealized_est",
        "us_fx_cost_realized", "us_fx_cost_unrealized_est",
    ]) {
        const v = ded[k]
        if (typeof v === "number" && v > 0) {
            rows.push({ key: k, value: v })
        }
    }

    const hasData = rows.length > 0 || total > 0
    const labelN = daysObserved < 30 ? `시뮬, N=${daysObserved}일 (통계 무의미)`
        : daysObserved < 100 ? `시뮬, N=${daysObserved}일 (예비 결과)`
        : `시뮬, N=${daysObserved}일`

    return (
        <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: C.textTertiary, letterSpacing: 0.5, textTransform: "uppercase" }}>
                    세후 보정 (가설)
                </span>
                <span style={{ fontSize: 10, color: C.textDisabled, letterSpacing: 0.3 }}>
                    {labelN}
                </span>
            </div>

            {/* raw vs adjusted 비교 */}
            <div style={{ background: CARD, borderRadius: 10, padding: "12px 14px", marginBottom: 8 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                    <span style={{ fontSize: 12, color: MUTED }}>raw 수익률</span>
                    <span style={{ ...MONO, fontSize: 14, fontWeight: 700, color: pctColor(raw) }}>
                        {fmtPct(raw)}
                    </span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                    <span style={{ fontSize: 12, color: MUTED }}>세후 보정 수익률</span>
                    <span style={{ ...MONO, fontSize: 14, fontWeight: 700, color: pctColor(adjusted) }}>
                        {fmtPct(adjusted)}
                    </span>
                </div>
                {Math.abs(gap) > 0.001 && (
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginTop: 6, paddingTop: 6, borderTop: `1px solid ${BORDER}` }}>
                        <span style={{ fontSize: 11, color: C.textTertiary }}>비용 차감</span>
                        <span style={{ ...MONO, fontSize: 12, fontWeight: 600, color: DOWN }}>
                            -{gap.toFixed(2)}%p
                        </span>
                    </div>
                )}
            </div>

            {/* 항목별 분해 */}
            {hasData ? (
                <div style={{ background: CARD, borderRadius: 10, padding: "10px 14px" }}>
                    <div style={{ fontSize: 11, color: C.textTertiary, fontWeight: 600, letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 8 }}>
                        항목별 비용 분해
                    </div>
                    {rows.map((r) => (
                        <div key={r.key} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", fontSize: 12 }}>
                            <span style={{ color: MUTED }}>{NET_LABELS[r.key] || r.key}</span>
                            <span style={{ ...MONO, color: WHITE, fontWeight: 600 }}>
                                -{fmtKRW(r.value)}원
                            </span>
                        </div>
                    ))}
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0 2px", marginTop: 4, borderTop: `1px solid ${BORDER}`, fontSize: 13 }}>
                        <span style={{ color: WHITE, fontWeight: 700 }}>총 차감</span>
                        <span style={{ ...MONO, color: DOWN, fontWeight: 700 }}>
                            -{fmtKRW(total)}원
                        </span>
                    </div>
                </div>
            ) : (
                <div style={{ background: CARD, borderRadius: 10, padding: "12px 14px", textAlign: "center", color: C.textTertiary, fontSize: 12 }}>
                    매매 누적 시 자동 분해 — 현재 history 0건
                </div>
            )}
        </div>
    )
}

/* ──────────────────────────────────────────────────────────────
 * 매도 시뮬 — TaxGuide 계산기 흡수 (단일 진입점)
 * 보유 종목 선택 → 수량 입력 → 세금 분해 + 세후 수령액
 * KR/US 자동 분기 (asset_class). backend 산식 정합.
 * ────────────────────────────────────────────────────────────── */
function SellSimulator({ holdings, livePrices }: { holdings: any[]; livePrices: Record<string, number> }) {
    const [pickIdx, setPickIdx] = useState<number>(0)
    const [qtyRaw, setQtyRaw] = useState<string>("")

    if (holdings.length === 0) {
        return (
            <div style={{ background: CARD, borderRadius: 10, padding: "12px 14px", textAlign: "center", color: C.textTertiary, fontSize: 12 }}>
                보유 종목 없음 — 매도 시뮬 불가
            </div>
        )
    }

    const pick = holdings[Math.min(pickIdx, holdings.length - 1)]
    const live = livePrices[pick.ticker]
    const maxQty = pick.quantity ?? 0
    const sellQty = (() => {
        const n = Number(qtyRaw)
        if (!Number.isFinite(n) || n <= 0) return maxQty  // 빈 입력 = 전량
        return Math.min(Math.max(1, Math.floor(n)), maxQty)
    })()
    const sim = simulateSell(pick, sellQty, live)

    return (
        <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: C.textTertiary, letterSpacing: 0.5, textTransform: "uppercase" }}>
                    매도 시뮬
                </span>
                <span style={{ fontSize: 10, color: C.textDisabled, letterSpacing: 0.3 }}>
                    backend 산식 정합 (단일 매도, 연간 통산 미반영)
                </span>
            </div>

            {/* 보유 종목 picker */}
            <div style={{ background: CARD, borderRadius: 10, padding: "10px 14px", marginBottom: 8 }}>
                <div style={{ fontSize: 11, color: C.textTertiary, fontWeight: 600, marginBottom: 6 }}>종목 선택</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {holdings.map((h, i) => (
                        <button
                            key={h.ticker}
                            type="button"
                            onClick={() => { setPickIdx(i); setQtyRaw("") }}
                            style={{
                                border: "none",
                                padding: "5px 10px",
                                borderRadius: 6,
                                background: i === pickIdx ? ACCENT : C.bgElevated,
                                color: i === pickIdx ? C.bgPage : MUTED,
                                fontSize: 11, fontWeight: 700, letterSpacing: 0.3,
                                cursor: "pointer", fontFamily: font,
                                display: "inline-flex", alignItems: "center", gap: 4,
                            }}
                        >
                            {h.name}
                            {isUSStock(h) && (
                                <span style={{
                                    fontSize: 9, fontWeight: 800,
                                    padding: "1px 4px", borderRadius: 3,
                                    background: i === pickIdx ? "rgba(14,15,17,0.2)" : "rgba(91,169,255,0.15)",
                                    color: i === pickIdx ? C.bgPage : C.info,
                                }}>
                                    US
                                </span>
                            )}
                        </button>
                    ))}
                </div>

                {/* 수량 입력 */}
                <div style={{ marginTop: 10 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
                        <label style={{ fontSize: 11, color: C.textTertiary, fontWeight: 600 }}>매도 수량</label>
                        <span style={{ fontSize: 10, color: C.textTertiary }}>최대 {maxQty}주</span>
                    </div>
                    <div style={{ display: "flex", gap: 6 }}>
                        <input
                            type="text"
                            inputMode="decimal"
                            placeholder={`전량 (${maxQty}주)`}
                            value={qtyRaw}
                            onChange={(e) => setQtyRaw(e.target.value.replace(/[^0-9]/g, ""))}
                            style={{
                                flex: 1,
                                background: C.bgPage, border: `1px solid ${C.borderStrong}`,
                                borderRadius: 6, padding: "8px 10px",
                                color: WHITE, fontSize: 13, ...MONO,
                                outline: "none",
                            }}
                        />
                        {[25, 50, 100].map((pct) => (
                            <button
                                key={pct}
                                type="button"
                                onClick={() => setQtyRaw(String(Math.floor(maxQty * pct / 100)))}
                                style={{
                                    border: "none",
                                    padding: "6px 10px",
                                    borderRadius: 6,
                                    background: C.bgElevated,
                                    color: MUTED,
                                    fontSize: 11, fontWeight: 700,
                                    cursor: "pointer", fontFamily: font,
                                }}
                            >
                                {pct}%
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* 시뮬 결과 */}
            <div style={{ background: CARD, borderRadius: 10, padding: "12px 14px" }}>
                {/* 매도 금액 + 손익 헤더 */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
                    <div>
                        <div style={{ fontSize: 11, color: C.textTertiary }}>매도 금액 ({sim.qty}주)</div>
                        <div style={{ ...MONO, fontSize: 16, fontWeight: 700, color: WHITE }}>
                            {fmtKRW(sim.proceeds)}원
                        </div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: 11, color: C.textTertiary }}>매수 원가</div>
                        <div style={{ ...MONO, fontSize: 13, fontWeight: 600, color: MUTED }}>
                            {fmtKRW(sim.cost)}원
                        </div>
                    </div>
                </div>

                {/* 세금 분해 */}
                <div style={{ borderTop: `1px solid ${BORDER}`, paddingTop: 8, marginTop: 4 }}>
                    {sim.sellTax > 0 && (
                        <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontSize: 12 }}>
                            <span style={{ color: MUTED }}>거래세 ({sim.isUS ? "0%" : isKREtf(pick) ? "0% (ETF)" : "0.18%"})</span>
                            <span style={{ ...MONO, color: WHITE }}>-{fmtKRW(sim.sellTax)}원</span>
                        </div>
                    )}
                    {sim.spread > 0 && (
                        <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontSize: 12 }}>
                            <span style={{ color: MUTED }}>스프레드 (5bp)</span>
                            <span style={{ ...MONO, color: WHITE }}>-{fmtKRW(sim.spread)}원</span>
                        </div>
                    )}
                    {sim.fxCost > 0 && (
                        <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontSize: 12 }}>
                            <span style={{ color: MUTED }}>US 환전 (0.3%)</span>
                            <span style={{ ...MONO, color: WHITE }}>-{fmtKRW(sim.fxCost)}원</span>
                        </div>
                    )}
                    {sim.usCapGainsTax > 0 && (
                        <div style={{ display: "flex", justifyContent: "space-between", padding: "3px 0", fontSize: 12 }}>
                            <span style={{ color: MUTED }}>US 양도세 (250만 공제 후 22%)</span>
                            <span style={{ ...MONO, color: WHITE }}>-{fmtKRW(sim.usCapGainsTax)}원</span>
                        </div>
                    )}
                    {sim.totalTax === 0 && (
                        <div style={{ textAlign: "center", color: C.success, fontSize: 12, padding: "4px 0" }}>
                            과세/비용 없음 (KR 비대주주 비과세)
                        </div>
                    )}
                </div>

                {/* 결과 */}
                <div style={{ borderTop: `1px solid ${BORDER}`, paddingTop: 8, marginTop: 4 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", fontSize: 13 }}>
                        <span style={{ color: WHITE, fontWeight: 700 }}>세후 손익</span>
                        <span style={{ ...MONO, color: pctColor(sim.netPnl), fontWeight: 800 }}>
                            {sim.netPnl >= 0 ? "+" : ""}{fmtKRW(sim.netPnl)}원
                        </span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", fontSize: 13 }}>
                        <span style={{ color: WHITE, fontWeight: 700 }}>세후 수령액</span>
                        <span style={{ ...MONO, color: ACCENT, fontWeight: 800 }}>
                            {fmtKRW(sim.netReceived)}원
                        </span>
                    </div>
                </div>
            </div>
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
    // 2026-05-13: 실시간 가격 (Railway SSE push). 보유 KR 종목 ticker → 1초 단위 fresh 가격.
    const [livePrices, setLivePrices] = useState<Record<string, number>>({})
    const esRefs = useRef<Record<string, EventSource>>({})

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

    // 2026-05-13: Railway SSE 실시간 가격 구독 — KR 6자리 ticker 만.
    // /stream/{ticker} 별로 EventSource 1개. trade/snapshot event 에서 price 추출.
    // 사이트 닫으면 자동 close (cleanup). Railway idle TTL 가 구독 해제.
    useEffect(() => {
        const holdings: any[] = vams?.holdings ?? []
        const krTickers: string[] = holdings
            .map((h) => String(h.ticker || ""))
            .filter((t) => KR_TICKER_RE.test(t))

        // 새 종목 list — 기존 ref 중 list 에 없는 건 close
        const existing = Object.keys(esRefs.current)
        existing.forEach((t) => {
            if (!krTickers.includes(t)) {
                try { esRefs.current[t].close() } catch {}
                delete esRefs.current[t]
            }
        })

        // 신규 추가 종목만 EventSource 연결
        krTickers.forEach((ticker) => {
            if (esRefs.current[ticker]) return
            try {
                const es = new EventSource(`${RAILWAY_STREAM_BASE}/${ticker}`)

                es.addEventListener("snapshot", (e: MessageEvent) => {
                    try {
                        const snap = JSON.parse(e.data)
                        const trades = Array.isArray(snap?.trades) ? snap.trades : []
                        const p = trades[0]?.price
                        if (typeof p === "number" && p > 0) {
                            setLivePrices((prev) => (prev[ticker] === p ? prev : { ...prev, [ticker]: p }))
                        }
                    } catch {}
                })

                es.addEventListener("trade", (e: MessageEvent) => {
                    try {
                        const trade = JSON.parse(e.data)
                        const p = trade?.price
                        if (typeof p === "number" && p > 0) {
                            setLivePrices((prev) => (prev[ticker] === p ? prev : { ...prev, [ticker]: p }))
                        }
                    } catch {}
                })

                es.onerror = () => {
                    // EventSource 가 자동 재연결. 길게 fail 시 다음 useEffect cycle 에서 회수.
                }

                esRefs.current[ticker] = es
            } catch {
                // EventSource 미지원 환경 (구버전 브라우저 등) — 폴백 = h.current_price
            }
        })

        return () => {
            Object.values(esRefs.current).forEach((es) => {
                try { es.close() } catch {}
            })
            esRefs.current = {}
        }
    }, [vams?.holdings])

    if (loading) return (
        <div style={{ fontFamily: font, background: BG, color: MUTED, padding: 40, borderRadius: 16, textAlign: "center", fontSize: 13 }}>
            로딩 중…
        </div>
    )
    if (error) return (
        <div style={{ fontFamily: font, background: BG, color: UP, padding: 20, borderRadius: 16, textAlign: "center", fontSize: 13 }}>
            {error}
        </div>
    )

    const totalAsset: number = vams.total_asset ?? INITIAL_CASH
    const cash: number = vams.cash ?? 0
    const totalReturnPct: number = vams.total_return_pct ?? 0
    const realizedPnl: number = vams.total_realized_pnl ?? 0
    const holdings: any[] = vams.holdings ?? []
    const sim = vams.simulation_stats ?? {}
    // fx_hedge_reserve: β USD ETF (auto-sell 제외 별 필드, engine.py:442).
    // null = 미진입. 진입 시 ticker/name/krw_invested/current_krw/return_pct 등 표시.
    const fxHedge: any = vams.fx_hedge_reserve ?? null

    const investedAmt = totalAsset - cash
    const cashPct = totalAsset > 0 ? (cash / totalAsset) * 100 : 0
    const adj = vams?.adjusted_performance || null

    // 운영 N일 — VAMS reset 일자 기준 (assumptions.computed_at 또는 가장 오래된 history)
    const daysObserved: number = (() => {
        if (history.length > 0) {
            const oldest = history[history.length - 1]
            return daysSince(oldest?.date || oldest?.timestamp || "")
        }
        return 0
    })()
    // 2026-05-13: livePrices 우선 (SSE fresh). 폴백 = portfolio.json current_price.
    const unrealizedPnl = holdings.reduce((acc, h) => {
        const live = livePrices[h.ticker]
        const px = typeof live === "number" && live > 0 ? live : h.current_price
        const cur = px * h.quantity
        const cost = h.total_cost ?? (h.buy_price * h.quantity)
        return acc + (cur - cost)
    }, 0)

    const recentTrades = history.slice(0, 12)

    return (
        <div style={{ fontFamily: font, background: BG, padding: 16, borderRadius: 16, display: "flex", flexDirection: "column", gap: 14, width: "100%", boxSizing: "border-box" }}>

            {/* 헤더 — 펜타그램 톤: sub-label uppercase + 큰 숫자 */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: C.textTertiary, letterSpacing: 0.5, textTransform: "uppercase" }}>VAMS 가상 투자</span>
                    <span style={{ fontSize: 11, color: C.textDisabled, letterSpacing: 0.3 }}>Virtual Asset Management</span>
                </div>
                <span style={{ fontSize: 22, fontWeight: 800, letterSpacing: -0.3, color: pctColor(totalReturnPct), fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }}>
                    {fmtPct(totalReturnPct)}
                </span>
            </div>

            {/* 총 자산 + 현금 — 펜타그램: 박스 background 떼고 단순 row */}
            <div style={{ padding: "16px 4px", display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
                <div>
                    <div style={{ fontSize: 11, color: C.textTertiary, fontWeight: 600, letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 6 }}>총 평가자산</div>
                    <div style={{ fontSize: 26, fontWeight: 800, letterSpacing: -0.5, color: WHITE, fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }}>{fmtKRW(totalAsset)}원</div>
                    <div style={{ fontSize: 11, color: C.textTertiary, marginTop: 4, letterSpacing: 0.3 }}>초기 {fmtKRW(INITIAL_CASH)}원 대비</div>
                </div>
                <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: 11, color: C.textTertiary, fontWeight: 600, letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 6 }}>현금 잔고</div>
                    <div style={{ fontSize: 16, fontWeight: 700, color: WHITE, fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }}>{fmtKRW(cash)}원</div>
                    <div style={{ fontSize: 11, color: C.textTertiary, marginTop: 4 }}>{cashPct.toFixed(0)}% 현금화</div>
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
                    value={sim.max_drawdown_pct != null ? `${Math.abs(sim.max_drawdown_pct).toFixed(2)}%` : "—"}
                    valueColor={DOWN}
                    sub="MDD"
                />
            </div>

            {/* 달러 베타 포지션 (auto-sell 제외 별 필드, fx_hedge_reserve).
                의도 (2026-05-23 PM 결정): 달러 매크로 베타 노출 + 부분 환해지 경제 효과.
                합성 ETF (455030 KODEX 미국달러SOFR) = 달러 자산 + SOFR 이자 누적,
                환 hedge 효과 자체는 ≈ 0 (Perplexity 검증) but USD 노출 자체로 부분 보호. */}
            {fxHedge && (
                <div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: C.textTertiary, letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 10 }}>
                        달러 베타 포지션 (부분 환해지 효과)
                    </div>
                    <div style={{ background: CARD, borderRadius: 10, padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                <span style={{ fontSize: 13, fontWeight: 700, color: WHITE }}>{fxHedge.name || fxHedge.ticker}</span>
                                <span style={{ fontSize: 10, color: C.textTertiary, fontFamily: FONT_MONO }}>{fxHedge.ticker}</span>
                            </div>
                            <span style={{ fontSize: 15, fontWeight: 800, color: pctColor(fxHedge.return_pct ?? 0), fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }}>
                                {fmtPct(fxHedge.return_pct ?? 0)}
                            </span>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: MUTED }}>
                            <span>원금 {fmtKRW(fxHedge.krw_invested ?? 0)}원</span>
                            <span style={{ fontFamily: FONT_MONO }}>현재 {fmtKRW(fxHedge.current_krw ?? 0)}원</span>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: C.textTertiary }}>
                            <span>진입 USD/KRW {(fxHedge.entry_usdkrw ?? 0).toFixed(2)}</span>
                            <span style={{ color: pctColor(fxHedge.pnl_krw ?? 0), fontFamily: FONT_MONO }}>
                                PnL {fmtKRW(fxHedge.pnl_krw ?? 0)}원
                            </span>
                        </div>
                        {fxHedge.reason && (
                            <div style={{ fontSize: 10, color: C.textDisabled, letterSpacing: 0.2, marginTop: 2 }}>
                                {fxHedge.reason}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* 현재 보유 종목 */}
            {holdings.length > 0 && (
                <div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: C.textTertiary, letterSpacing: 0.5, textTransform: "uppercase", marginBottom: 10 }}>보유 종목</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        {holdings.map((h: any) => <HoldingCard key={h.ticker} h={h} livePrice={livePrices[h.ticker]} />)}
                    </div>
                </div>
            )}

            {holdings.length === 0 && (
                <div style={{ background: CARD, borderRadius: 10, padding: 16, textAlign: "center", color: MUTED, fontSize: 12 }}>
                    현재 보유 종목 없음 — 현금 {cashPct.toFixed(0)}% 대기 중
                </div>
            )}

            {/* 세후 PnL 분해 — backend deductions 소비 */}
            {adj && <DeductionBreakdown adj={adj} daysObserved={daysObserved} />}

            {/* 매도 시뮬 — TaxGuide 계산기 흡수 */}
            {holdings.length > 0 && <SellSimulator holdings={holdings} livePrices={livePrices} />}

            {/* 베스트 / 워스트 거래 */}
            {(sim.best_trade || sim.worst_trade) && (
                <div style={{ display: "flex", gap: 8 }}>
                    {sim.best_trade && (
                        <div style={{ flex: 1, background: "transparent", borderRadius: 10, padding: "8px 12px" }}>
                            <div style={{ fontSize: 12, color: UP, fontWeight: 600, marginBottom: 3 }}>최고 거래</div>
                            <div style={{ fontSize: 12, fontWeight: 700, color: WHITE }}>{sim.best_trade.name}</div>
                            <div style={{ fontSize: 12, color: UP, fontWeight: 600 }}>+{fmtKRW(sim.best_trade.pnl)}원</div>
                        </div>
                    )}
                    {sim.worst_trade && (
                        <div style={{ flex: 1, background: "transparent", borderRadius: 10, padding: "8px 12px" }}>
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
                    <div style={{ background: CARD, borderRadius: 10, padding: "4px 12px" }}>
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
