"use client"
// AccountHud — R1 계좌 헤드업 (총평가 大 · 손익 · 현금 · 노출). 기관 터미널 문법:
// "지금 내 계좌가 어디 서 있나"가 최상단 (PM 결함 #7 — 포트폴리오 최상위 노출).
// 총자산 = 서버 SoT(vams.total_asset, FX 반영) + KR 보유 실시간 델타만 가산 (혼합통화 합산 오류 방지).
import { useDark, palette, cardStyle, FONT, NUM, type Palette } from "@/lib/theme"
import { useQuotes } from "@/lib/quotes"
import type { Vams } from "@/lib/types"

function won(v: number): string {
    return Math.round(v).toLocaleString() + "원"
}

export default function AccountHud({ vams, status }: { vams?: Vams; status: "loading" | "ok" | "error" }) {
    const dark = useDark()
    const c = palette(dark)
    const holds = vams?.holdings || []
    const krTickers = holds.filter((h) => /^\d{6}$/.test(h.ticker)).map((h) => h.ticker)
    const { q, asof } = useQuotes(krTickers)

    const totalAsset = typeof vams?.total_asset === "number" ? vams.total_asset : null
    const cash = typeof vams?.cash === "number" ? vams.cash : null

    // KR 실시간 델타 (live − 서버 스냅샷). US 는 서버 값 유지.
    let liveDelta = 0
    let krPnl = 0
    let krCost = 0
    holds.forEach((h) => {
        const qty = h.quantity || 0
        if (/^\d{6}$/.test(h.ticker)) {
            const live = q[h.ticker]?.price
            const snap = h.current_price || 0
            const px = typeof live === "number" ? live : snap
            if (typeof live === "number" && snap > 0) liveDelta += qty * (live - snap)
            if (h.buy_price) {
                krPnl += qty * (px - h.buy_price)
                krCost += qty * h.buy_price
            }
        }
    })
    const liveTotal = totalAsset !== null ? totalAsset + liveDelta : null
    const exposure = liveTotal && cash !== null && liveTotal > 0 ? ((liveTotal - cash) / liveTotal) * 100 : null
    const cum = typeof vams?.total_return_pct === "number" ? vams.total_return_pct : null
    const krPnlPct = krCost > 0 ? (krPnl / krCost) * 100 : null

    return (
        <div style={{ ...cardStyle(c, "16px 20px"), fontFamily: FONT, display: "flex", alignItems: "center", gap: 22, flexWrap: "wrap", marginBottom: 12 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 190 }}>
                <span style={{ fontSize: 11, color: c.faint, fontWeight: 700 }}>
                    총평가 자산 <span style={{ fontWeight: 500 }}>· VAMS 모의 1,000만 · 가설 N&lt;252</span>
                </span>
                {status === "loading" ? (
                    <span style={{ fontSize: 24, fontWeight: 800, color: c.faint }}>불러오는 중…</span>
                ) : liveTotal !== null ? (
                    <span style={{ fontSize: 26, fontWeight: 800, letterSpacing: "-0.02em", color: c.ink, ...NUM }}>{won(liveTotal)}</span>
                ) : (
                    <span style={{ fontSize: 20, fontWeight: 800, color: c.faint }}>—</span>
                )}
            </div>

            <Stat c={c} k="누적 수익률" v={cum !== null ? `${cum >= 0 ? "+" : ""}${cum.toFixed(2)}%` : "—"} col={cum === null ? c.faint : cum > 0 ? c.up : cum < 0 ? c.down : c.faint} />
            <Stat c={c} k="KR 보유손익 (실시간)" v={krCost > 0 ? `${krPnl >= 0 ? "+" : ""}${Math.round(krPnl).toLocaleString()}원${krPnlPct !== null ? ` (${krPnlPct >= 0 ? "+" : ""}${krPnlPct.toFixed(2)}%)` : ""}` : "—"} col={krCost === 0 ? c.faint : krPnl > 0 ? c.up : krPnl < 0 ? c.down : c.faint} />
            <Stat c={c} k="현금" v={cash !== null ? won(cash) : "—"} col={c.ink} />

            {/* 노출 게이지 — 중용 사이징 결과의 실측 (E=quarter-Kelly binding 시 현금 우위 정상) */}
            <div style={{ display: "flex", flexDirection: "column", gap: 5, minWidth: 150, flex: "0 1 190px" }}>
                <span style={{ fontSize: 11, color: c.faint, fontWeight: 700 }}>
                    주식 노출 {exposure !== null ? <span style={{ color: c.ink, ...NUM }}>{exposure.toFixed(1)}%</span> : "—"}
                </span>
                <div style={{ height: 8, borderRadius: 999, background: c.track, overflow: "hidden" }}>
                    <div style={{ width: `${Math.min(100, Math.max(0, exposure || 0))}%`, height: "100%", borderRadius: 999, background: c.vt }} />
                </div>
            </div>

            <span style={{ marginLeft: "auto", fontSize: 10.5, color: c.faint, ...NUM }}>
                {asof ? `시세 ${asof} · ` : ""}보유 {holds.length}종목
            </span>
        </div>
    )
}

function Stat({ c, k, v, col }: { c: Palette; k: string; v: string; col: string }) {
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <span style={{ fontSize: 11, color: c.faint, fontWeight: 700 }}>{k}</span>
            <span style={{ fontSize: 15, fontWeight: 800, color: col, ...NUM }}>{v}</span>
        </div>
    )
}
