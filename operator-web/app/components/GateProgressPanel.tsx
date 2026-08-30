"use client"
// GateProgressPanel — 실자금 게이트 진척 (PM 2026-08-25 "진척을 알파콘솔에 보이게").
//
// 데이터 = 페이지 소유 슬림 페이로드(`portfolio_terminal`)의 vams 를 prop 으로 받는다
// (자체 fetch 금지 — /system 페이지 규율). 전부 **표시값**이며 집행값이 아니다.
//
// 🚨 되돌리지 말 것 3가지:
//   ① "표본 미달 — 판정 아님" 라벨. after 5거래 +1.386R 이 좋아 보여도 판정 근거가 아니다
//      (PREREG_VAMS_GATE_WINDOW §4 — 20거래 전 조기 판정은 등록 위반).
//   ② 검출하한 고지. N20 에서 |t|=3 하한 0.929R — 통과해도 "검증됐다" 로 쓰면 등록 §3 위반.
//      쓸 수 있는 말은 "등록된 최소 문턱을 넘었다" 까지다.
//   ③ segments 부재 시 **부재를 말한다**. 경계 분해(8/25 배선)는 다음 run 부터 산출물에
//      실린다 — 빈 값을 전체 창 수치로 그럴듯하게 메우면 이미 고친 결함(캡 −5% 시절
//      22거래)이 현재 성적으로 오독된다. 그 오독이 이 패널을 만든 이유다.
import type { CSSProperties } from "react"
import { palette, cardStyle, CARD_TITLE, NUM, useDark } from "@/lib/theme"
import type { Vams } from "@/lib/types"

const REQUIRED_TRADES = 20
// PREREG_VAMS_GATE_WINDOW_2026_08_25 §4 등록 추정 (통과 예측 아님) — stale 화 방지를 위해
// 표본 충족 시(≥20) 이 문자열 대신 "표본 충족" 으로 전환된다.
const REG_ETA = "10/08–18 (등록 추정 8/25)"
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

    const afterN = after?.trades ?? null
    const pct = afterN != null ? Math.min(100, Math.round((afterN / REQUIRED_TRADES) * 100)) : null

    const metrics = vr?.metrics || {}
    const judged = Object.entries(GATE_LABELS)
        .filter(([k]) => metrics[k] && metrics[k].pass !== null && metrics[k].pass !== undefined)
        .map(([k, label]) => ({ label, pass: Boolean(metrics[k].pass) }))
    const passN = judged.filter((m) => m.pass).length

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

            {/* 표본 진척 — after 창(캡 −20% 이후)만이 현재 시스템이다 */}
            <div style={{ marginTop: 12 }}>
                {afterN != null ? (
                    <>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                            <span style={{ fontSize: 12.5, fontWeight: 700 }}>표본 (8/09 캡 복원 이후)</span>
                            <span style={{ ...NUM, fontSize: 13, fontWeight: 800 }}>
                                {afterN}/{REQUIRED_TRADES}거래
                            </span>
                        </div>
                        <div style={{ marginTop: 6, height: 8, borderRadius: 4, background: c.track, overflow: "hidden" }}>
                            <div style={{ width: `${pct}%`, height: "100%", borderRadius: 4, background: c.vt }} />
                        </div>
                        <div style={{ ...sub, marginTop: 6, display: "flex", justifyContent: "space-between", gap: 8 }}>
                            <span>
                                {afterN >= REQUIRED_TRADES
                                    ? "표본 충족 — 판정 실행 대기"
                                    : `판정 가능 ${REG_ETA}`}
                            </span>
                            {after?.expectancy_r != null && (
                                <span style={NUM}>
                                    기대값 {after.expectancy_r > 0 ? "+" : ""}{after.expectancy_r}R
                                    {afterN < REQUIRED_TRADES && " · 🚨 표본 미달 — 판정 아님"}
                                </span>
                            )}
                        </div>
                    </>
                ) : (
                    <div style={sub}>
                        🚨 경계 분해(segments) 미산출 — 8/25 배선분은 다음 검증 run 부터 실린다.
                        그 전의 전체 창 수치는 손절 캡 −5% 시절 22거래가 섞여 있어 현재 시스템
                        성적이 아니다 (전체 창으로 메워 보여주지 않는 것이 의도다).
                    </div>
                )}
            </div>

            {/* 게이트 지표 — 판정용만, informational 제외 */}
            {judged.length > 0 && (
                <div style={{ marginTop: 12 }}>
                    <div style={{ ...sub, marginBottom: 6 }}>
                        게이트 {passN}/{judged.length} 통과 <span style={{ opacity: 0.7 }}>(전체 창 기준 — 임계 9종 불변)</span>
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

            {/* 검출하한 고지 — 등록 §3. 지우면 "통과=검증" 오독이 돌아온다 */}
            <div style={{ ...sub, marginTop: 12, paddingTop: 10, borderTop: `1px solid ${c.line}` }}>
                검출하한: N=20 에서 |t|=3 하한 <b style={NUM}>0.929R</b> — 명목 임계 +0.25R 은
                통계적으로 0 과 구분되지 않는다. 통과 = "등록 문턱을 넘음"이지 "검증됨"이 아니다.
                실질 바인딩 = SQN 1.7 (N20 에서 0.526R 요구).
            </div>
        </section>
    )
}
