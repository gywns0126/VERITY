"use client"
// 시스템 작용 — 매크로·게이트가 "지금 시스템에 뭘 하고 있는가" (PM 2026-08-03 /macro 1번 패널).
// 데이터 = pf.system_action (VERITY #267 · 오퍼레이터 전용, 공개 blob strip).
// 지표 나열(측정)과 구분되는 이 페이지의 판단 연결 고리: 방패 발동 → 등급 상한,
// 레짐 비선호 → NEM 류 모순 식별, 배지 게이트 → BUY·정렬·강등 현황.
import type { CSSProperties } from "react"
import { cardStyle, MAIN_PAD, NUM, type Palette } from "@/lib/theme"
import type { SystemAction } from "@/lib/types"

function chip(bg: string, fg: string): CSSProperties {
    return { display: "inline-block", padding: "1px 8px", borderRadius: 999, fontSize: 11, fontWeight: 700, background: bg, color: fg }
}

export default function SystemActionPanel({ c, sa }: { c: Palette; sa?: SystemAction }) {
    const k: CSSProperties = { fontSize: 12, color: c.faint, marginRight: 6 }
    const v: CSSProperties = { fontSize: 12.5, color: c.ink, ...NUM }
    const sh = sa?.rate_shield
    const q = sa?.quadrant
    const vg = sa?.verdict_gate

    return (
        <div style={{ ...cardStyle(c, MAIN_PAD) }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 7, marginBottom: 10 }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: c.amber, alignSelf: "center", flexShrink: 0 }} />
                <span style={{ fontSize: 14, fontWeight: 800, color: c.ink, letterSpacing: "-0.02em" }}>시스템 작용</span>
                <span style={{ fontSize: 10, color: c.faint }}>
                    매크로·게이트의 실작용{sa?.as_of ? ` · 기준 ${String(sa.as_of).slice(5, 16).replace("T", " ")}` : ""}
                </span>
            </div>

            {!sa ? (
                <div style={{ fontSize: 12.5, color: c.sub }}>미적재 — 다음 분석 run(16:07) 후 자동 표시.</div>
            ) : (
                <div style={{ display: "flex", flexWrap: "wrap", gap: "8px 22px", alignItems: "center" }}>
                    <span>
                        <span style={k}>금리 방패</span>
                        <span style={chip(sh?.on ? c.upS : c.track, sh?.on ? c.up : c.sub)}>{sh?.on ? "발동" : "미발동"}</span>
                        <span style={{ ...v, marginLeft: 6 }}>
                            10Y {sh?.us_10y ?? "—"}% / {sh?.threshold ?? 4.5}%{sh?.on && sh?.grade_cap ? ` · 등급 상한 ${sh.grade_cap}` : ""}
                        </span>
                    </span>
                    <span>
                        <span style={k}>레짐</span>
                        <span style={v}>{q?.label ?? "—"}</span>
                        {(q?.unfavored?.length ?? 0) > 0 &&
                            q!.unfavored!.map((u) => (
                                <span key={u} style={{ ...chip(c.upS, c.up), marginLeft: 4 }}>비선호 {u}</span>
                            ))}
                    </span>
                    <span>
                        <span style={k}>매크로 배율</span>
                        <span style={v}>{sa.macro_multiplier_median ?? "—"}</span>
                        <span style={{ fontSize: 10, color: c.faint, marginLeft: 3 }}>중앙값</span>
                    </span>
                    <span>
                        <span style={k}>배지 게이트</span>
                        <span style={v}>BUY {vg?.buy_count ?? 0}</span>
                        {(vg?.aligned?.length ?? 0) > 0 ? (
                            vg!.aligned!.map((t) => (
                                <span key={t} style={{ ...chip(c.greenS, c.green), marginLeft: 4 }}>정렬 {t}</span>
                            ))
                        ) : (
                            <span style={{ fontSize: 11, color: c.faint, marginLeft: 4 }}>· 정렬 0</span>
                        )}
                        <span style={{ ...v, marginLeft: 6 }}>· 강등 {vg?.gated_count ?? 0}건</span>
                    </span>
                    <span style={{ fontSize: 10, color: c.faint, flexBasis: "100%" }}>
                        배지 소유 = Brain(강등 전용 게이트) · {sa.validation ?? "가설 — 자체 산식 N<252 미검증"}
                    </span>
                </div>
            )}
        </div>
    )
}
