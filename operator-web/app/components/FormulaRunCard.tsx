"use client"

import { cardStyle, CARD_TITLE, NUM, palette, useDark } from "@/lib/theme"
import type { FormulaRun } from "@/lib/types"

function won(v?: number): string {
    return typeof v === "number" ? `${Math.round(v).toLocaleString()}원` : "—"
}

function pct(v?: number | null): string {
    if (typeof v !== "number") return "—"
    return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`
}

export default function FormulaRunCard({ run, status = "ok" }: { run?: FormulaRun; status?: "loading" | "ok" | "error" }) {
    const dark = useDark()
    const c = palette(dark)
    const positionsN = Object.keys(run?.positions || {}).length
    const targetN = run?.target_holdings ?? run?.target_capacity ?? 10
    const eligibleN = run?.denominator?.eligible_n
    const signalEligibleN = run?.denominator?.signal_eligible_n
    const poolN = run?.denominator?.kr_candidate_n
    const unaffordableN = run?.denominator?.rejected?.one_share_above_slot
    const floor = run?._meta?.min_detectable
    const floorEffect = typeof floor?.effect_pct === "number" ? floor.effect_pct : null
    const active = run?.status === "RUNNING"
    const targets = (run?.targets || []).slice(0, 10)

    if (status !== "ok") {
        return (
            <section style={cardStyle(c)}>
                <h2 style={{ ...CARD_TITLE, margin: 0 }}>현행식 전향 운용</h2>
                <div style={{ marginTop: 10, fontSize: 12, color: status === "error" ? c.down : c.faint }}>
                    {status === "error" ? "운용 원천을 불러오지 못했습니다." : "운용 상태 로딩…"}
                </div>
            </section>
        )
    }

    return (
        <section style={cardStyle(c)}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                <h2 style={{ ...CARD_TITLE, margin: 0 }}>현행식 전향 운용</h2>
                <span style={{ fontSize: 10.5, fontWeight: 800, color: active ? c.green : c.faint }}>
                    {active ? "RUNNING" : run?.status || "원천 대기"} · 가상 1,000만 · 실주문 0
                </span>
            </div>

            <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(92px, 1fr))", gap: 9 }}>
                <Metric label="평가액" value={won(run?.equity)} color={c.ink} labelColor={c.faint} />
                <Metric label="누적 수익" value={pct(run?.return_pct)} color={(run?.return_pct || 0) >= 0 ? c.up : c.down} labelColor={c.faint} />
                <Metric label="코스피 대비" value={pct(run?.benchmark?.excess_pct)} color={(run?.benchmark?.excess_pct || 0) >= 0 ? c.up : c.down} labelColor={c.faint} />
                <Metric label="누적 비용" value={won(run?.cost_paid)} color={c.sub} labelColor={c.faint} />
            </div>

            <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, color: c.sub }}>
                        <span>포지션 구성</span>
                        <b style={{ color: c.ink, ...NUM }}>{positionsN}/{targetN} · 대기 {run?.pending ?? 0}</b>
                    </div>
                    <div style={{ height: 7, borderRadius: 999, background: c.track, overflow: "hidden", marginTop: 6 }}>
                        <div style={{ height: "100%", width: `${Math.min(100, positionsN / Math.max(1, targetN) * 100)}%`, background: c.vt, borderRadius: 999 }} />
                    </div>
                </div>
                <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, color: c.sub }}>
                        <span>다음 재조정</span>
                        <b style={{ color: c.ink, ...NUM }}>{run?.rebalance?.sessions_remaining ?? "—"}세션 후</b>
                    </div>
                    <div style={{ height: 7, borderRadius: 999, background: c.track, overflow: "hidden", marginTop: 6 }}>
                        <div style={{ height: "100%", width: `${Math.min(100, (run?.rebalance?.sessions_since || 0) / Math.max(1, run?.rebalance?.interval_sessions || 20) * 100)}%`, background: c.down, borderRadius: 999 }} />
                    </div>
                </div>
            </div>

            <div style={{ marginTop: 11, display: "flex", gap: 6, flexWrap: "wrap" }}>
                {targets.map((t) => (
                    <span key={t.ticker} style={{ padding: "3px 7px", borderRadius: 999, background: c.hi, color: c.sub, fontSize: 10.5, ...NUM }}>
                        {t.rank ? `${t.rank}. ` : ""}{t.name || t.ticker} {typeof t.brain_score === "number" ? t.brain_score : ""}
                    </span>
                ))}
            </div>

            <div style={{ marginTop: 12, paddingTop: 10, borderTop: `1px solid ${c.line}`, fontSize: 11, lineHeight: 1.55, color: c.faint }}>
                실행/신호/KR <b style={{ color: c.sub, ...NUM }}>{eligibleN ?? "—"}/{signalEligibleN ?? "—"}/{poolN ?? "—"}</b> ·
                1주 초과 <b style={{ color: c.sub, ...NUM }}>{unaffordableN ?? 0}</b> ·
                시장 세션 <b style={{ color: c.sub, ...NUM }}>T={run?.market_sessions ?? 0}</b> ·
                체결 <b style={{ color: c.sub, ...NUM }}>N={run?.trades_total ?? 0}</b> ·
                검출하한 <b style={{ color: c.sub, ...NUM }}>{floor?.status === "computed" && floorEffect !== null ? `${floorEffect}%` : "측정 대기"}</b>
                <br />
                현재 분석 후보 안의 순위이며, 과거 포트폴리오 알파 통과를 뜻하지 않는다. 코스피 기준 {run?.benchmark?.as_of || "—"} · {run?.benchmark?.freshness || "기준 미산출"}.
                <br />
                가격 {run?.price_snapshot?.as_of || "—"} · {run?.price_snapshot?.market_clock_state || "상태 미산출"} · 정수 1주 기준.
            </div>
        </section>
    )
}

function Metric({ label, value, color, labelColor }: { label: string; value: string; color: string; labelColor: string }) {
    return (
        <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 10.5, color: labelColor }}>{label}</div>
            <div style={{ marginTop: 3, fontSize: 15, fontWeight: 850, color, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", ...NUM }}>{value}</div>
        </div>
    )
}
