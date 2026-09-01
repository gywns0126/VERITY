"use client"
// GateProgressPanel — 실자금 게이트 진척 (PM 2026-08-25 "진척을 알파콘솔에 보이게").
//
// 데이터 = 페이지 소유 슬림 페이로드(`portfolio_terminal`)의 vams 를 prop 으로 받는다
// (자체 fetch 금지 — /system 페이지 규율). 전부 **표시값**이며 집행값이 아니다.
//
// Active window, T/N, and detection floor come from validation_report. Do not
// restore a locally estimated completion date or a hardcoded sample gate.
import type { CSSProperties } from "react"
import { palette, cardStyle, CARD_TITLE, NUM, useDark } from "@/lib/theme"
import type { Vams } from "@/lib/types"

// 판정용 지표만 — pass=None(informational: sortino·calmar·alpha_beta·capture_ratios)은 제외.
const GATE_LABELS: Record<string, string> = {
    cumulative_return: "초과수익",
    mdd: "MDD비",
    win_rate: "승률",
    profit_loss_ratio: "손익비",
    expectancy: "기대값",
    sqn: "SQN",
    sharpe: "Sharpe",
    regime_coverage: "레짐",
    cost_efficiency: "비용효율",
}

export default function GateProgressPanel({ vams, status = "ok" }: { vams?: Vams; status?: "loading" | "ok" | "error" }) {
    const dark = useDark()
    const c = palette(dark)
    const vr = vams?.validation_report
    const seg = vams?.simulation_stats?.segments
    const after = seg?.after

    const metrics = vr?.metrics || {}
    const winMetric = metrics.win_rate as { trades?: number } | undefined
    const activeN = typeof winMetric?.trades === "number" ? winMetric.trades : after?.trades
    const activeT = vr?.window?.days
    const floor = vr?._meta?.min_detectable?.effect_r
    const evidence = vr?._meta?.evidence_status
    const evidenceLabel = evidence === "STATISTICALLY_UNINFORMATIVE"
        ? "통계 해석 불가"
        : evidence === "PRELIMINARY"
            ? "예비 결과"
            : evidence === "MATURE"
                ? "성숙 구간"
                : "근거 상태 미산출"
    const judged = Object.entries(GATE_LABELS)
        .filter(([k]) => metrics[k] && metrics[k].pass !== null && metrics[k].pass !== undefined)
        .map(([k, label]) => ({ label, pass: Boolean(metrics[k].pass) }))
    const passN = judged.filter((m) => m.pass).length
    const gateMeta = vr?._meta?.gate_metrics
    const requiredN = gateMeta?.required_count
    const measuredN = gateMeta?.measured_count ?? judged.length

    const sub: CSSProperties = { fontSize: 11.5, color: c.sub, lineHeight: 1.55 }

    if (status !== "ok") {
        return (
            <section style={cardStyle(c)}>
                <h2 style={{ ...CARD_TITLE, margin: 0 }}>실자금 게이트</h2>
                <div style={{ ...sub, marginTop: 10, color: status === "error" ? c.down : c.faint }}>
                    {status === "error" ? "게이트 원천을 불러오지 못했습니다." : "게이트 로딩…"}
                </div>
            </section>
        )
    }

    return (
        <section style={cardStyle(c)}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                <h2 style={{ ...CARD_TITLE, margin: 0 }}>실자금 게이트</h2>
                <span style={{ ...sub, ...NUM }}>
                    창 {vr?.window?.start || "—"}~ · 판정 {vr?.overall || "—"}
                </span>
            </div>

            {/* Active evidence window — no completion-date estimate or sample target. */}
            <div style={{ marginTop: 12 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
                    <span style={{ fontSize: 12.5, fontWeight: 700 }}>현행 창 (8/09 캡 복원 이후)</span>
                    <span style={{ ...NUM, fontSize: 13, fontWeight: 800 }}>
                        T={activeT ?? "—"}일 · N={activeN ?? "—"}거래
                    </span>
                </div>
                <div style={{ ...sub, marginTop: 6, display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                    <span>{evidenceLabel} · 일정 추정 없음</span>
                    {after?.expectancy_r != null && (
                        <span style={NUM}>
                            기대값 {after.expectancy_r > 0 ? "+" : ""}{after.expectancy_r}R
                        </span>
                    )}
                </div>
            </div>

            {/* 게이트 지표 — 판정용만, informational 제외 */}
            {judged.length > 0 && (
                <div style={{ marginTop: 12 }}>
                    <div style={{ ...sub, marginBottom: 6 }}>
                        {requiredN != null
                            ? `게이트 ${passN}/${requiredN} 통과 · 측정 ${measuredN}/${requiredN}`
                            : `게이트 측정 ${measuredN}개 · 분모 미산출`}
                        <span style={{ opacity: 0.7 }}> (8/09 이후 정본 창)</span>
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                        {judged.map((m) => (
                            <span
                                key={m.label}
                                style={{
                                    fontSize: 11, fontWeight: 700, padding: "3px 8px", borderRadius: 999,
                                    background: m.pass ? c.greenS : c.upS,
                                    color: m.pass ? c.green : c.up,
                                }}
                            >
                                {m.label} {m.pass ? "✓" : "✗"}
                            </span>
                        ))}
                    </div>
                </div>
            )}

            {/* Detection floor is computed from the active ledger window. */}
            <div style={{ ...sub, marginTop: 12, paddingTop: 10, borderTop: `1px solid ${c.line}` }}>
                검출하한: |t|=3 기준 <b style={NUM}>{floor != null ? `${floor}R` : "측정 불가"}</b> ·
                통과는 등록된 성과 문턱의 결과이며 알파 입증과 동일하지 않다.
            </div>
        </section>
    )
}
