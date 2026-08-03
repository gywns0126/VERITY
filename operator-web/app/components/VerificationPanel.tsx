"use client"
// VerificationPanel — ④ 검증 층 (오퍼레이터 전용, authed). 공개 알파네스트 디자인.
// 되돌리지 말 것: fetchOperator("verification")=verification_report.json(private bucket). 공개 blob 직독 금지.
//   🚨 RULE 7: performance 실값 없으면(N<252) 가짜 hit rate 금지 — "축적 중 · 2027 게이트" 정직 표기.
//   hit rate 표시 시엔 sample+CI 병기 의무(단독 게재 금지). 이게 LLM 못 가지는 자기 검증 trail 차별점.
import { useEffect, useState } from "react"
import { useDark, palette, cardStyle, FONT, NUM, type Palette } from "@/lib/theme"
import { fetchOperator } from "@/lib/api"

type Perf = {
    hit_rate_7d?: number | null
    hit_rate_14d?: number | null
    hit_rate_30d?: number | null
    avg_return_14d?: number | null
    sharpe_14d?: number | null
    delisted_count_30d?: number | null
}
type FactorHealth = { healthy?: string[]; weakening?: string[]; decaying?: string[]; total_factors?: number }
type IcAdj = { factor?: string; ic_recent?: number; multiplier?: number; status?: string }
type Report = {
    generated_at?: string
    feedback_loop_status?: string
    performance?: Perf
    factor_health?: FactorHealth
    ic_adjustments_active?: IcAdj[]
    _corrections_meta?: { tx_cost_pct_round_trip?: number; slippage_model?: string; delisted_return_pct?: number }
}

function hasPerf(p?: Perf): boolean {
    if (!p) return false
    return [p.hit_rate_7d, p.hit_rate_14d, p.hit_rate_30d, p.avg_return_14d, p.sharpe_14d].some((v) => typeof v === "number" && isFinite(v as number))
}

export default function VerificationPanel() {
    const dark = useDark()
    const c = palette(dark)
    const [rep, setRep] = useState<Report | null>(null)
    const [status, setStatus] = useState<"loading" | "ok" | "auth" | "error">("loading")

    useEffect(() => {
        let cancelled = false
        fetchOperator<Report>("verification").then((r) => {
            if (cancelled) return
            if (!r.ok) {
                setStatus(r.error === "auth" ? "auth" : "error")
                return
            }
            setRep(r.data)
            setStatus("ok")
        })
        return () => {
            cancelled = true
        }
    }, [])

    if (status === "auth" || status === "error") {
        return (
            <div style={{ ...cardStyle(c), fontFamily: FONT, fontSize: 13, color: status === "auth" ? c.sub : c.down }}>
                {status === "auth" ? "오퍼레이터 로그인이 필요합니다 (비공개)." : "검증 데이터를 불러오지 못했습니다."}
            </div>
        )
    }
    if (status === "loading" || !rep) {
        return <div style={{ ...cardStyle(c), fontFamily: FONT, fontSize: 13, color: c.faint }}>불러오는 중…</div>
    }

    const fh = rep.factor_health || {}
    const ic = (rep.ic_adjustments_active || []).slice(0, 6)
    const perfLive = hasPerf(rep.performance)
    const genAt = String(rep.generated_at || "").slice(0, 16).replace("T", " ").replace(/\.\d+/, "")

    return (
        <div style={{ fontFamily: FONT, display: "flex", flexDirection: "column", gap: 12 }}>
            {/* 상태 줄 */}
            <div style={{ ...cardStyle(c), display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 13, fontWeight: 700, color: c.ink }}>학습 루프</span>
                    <span style={{ fontSize: 11, fontWeight: 700, color: rep.feedback_loop_status === "closed" ? c.green : c.amber, background: rep.feedback_loop_status === "closed" ? c.greenS : c.amberS, borderRadius: 8, padding: "3px 9px" }}>
                        {rep.feedback_loop_status === "closed" ? "닫힘(가동)" : rep.feedback_loop_status || "—"}
                    </span>
                </div>
                <span style={{ fontSize: 11, color: c.faint, ...NUM }}>{genAt}</span>
            </div>

            {/* 성과 — RULE 7 정직 표기 */}
            <div style={{ ...cardStyle(c), display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: c.ink }}>성과 검증</div>
                {perfLive ? (
                    <PerfLive c={c} p={rep.performance!} />
                ) : (
                    <div style={{ fontSize: 12.5, color: c.sub, lineHeight: 1.55 }}>
                        <b style={{ color: c.ink }}>검증 데이터 축적 중</b> — 통계적으로 무의미한 구간입니다.
                        <div style={{ marginTop: 6, display: "flex", flexWrap: "wrap", gap: 8 }}>
                            <span style={{ fontSize: 11, fontWeight: 700, color: c.vt, background: c.vtS, borderRadius: 8, padding: "3px 9px" }}>N&lt;252</span>
                            <span style={{ fontSize: 11, fontWeight: 700, color: c.sub, background: c.hi, borderRadius: 8, padding: "3px 9px", ...NUM }}>IC 게이트 2027-05</span>
                            <span style={{ fontSize: 11, fontWeight: 700, color: c.sub, background: c.hi, borderRadius: 8, padding: "3px 9px" }}>hit rate 미표기(표본 부족)</span>
                        </div>
                        <div style={{ fontSize: 11, color: c.faint, marginTop: 6, lineHeight: 1.5 }}>
                            표본이 쌓이면 hit rate·기대값·표본수·신뢰구간을 함께 노출합니다(단독 게재 금지).
                        </div>
                    </div>
                )}
            </div>

            {/* 팩터 건강도 */}
            {fh.total_factors ? (
                <div style={{ ...cardStyle(c), display: "flex", flexDirection: "column", gap: 8 }}>
                    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
                        <span style={{ fontSize: 13, fontWeight: 700, color: c.ink }}>팩터 건강도</span>
                        <span style={{ fontSize: 11, color: c.faint, ...NUM }}>총 {fh.total_factors}개</span>
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                        <FactorChip c={c} label="건강" n={(fh.healthy || []).length} color={c.green} soft={c.greenS} />
                        <FactorChip c={c} label="약화" n={(fh.weakening || []).length} color={c.amber} soft={c.amberS} />
                        <FactorChip c={c} label="쇠퇴" n={(fh.decaying || []).length} color={c.faint} soft={c.hi} />
                    </div>
                </div>
            ) : null}

            {/* IC 조정 활성 */}
            {ic.length ? (
                <div style={{ ...cardStyle(c), display: "flex", flexDirection: "column", gap: 8 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: c.ink }}>IC 기반 가중 조정 <span style={{ fontSize: 11, fontWeight: 500, color: c.faint }}>(피드백 루프 실작동)</span></div>
                    {ic.map((a, i) => {
                        const m = typeof a.multiplier === "number" ? a.multiplier : null
                        const mCol = m == null ? c.sub : m > 1 ? c.up : m < 1 ? c.down : c.sub
                        return (
                            <div key={(a.factor || "") + i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, paddingTop: i === 0 ? 0 : 7, borderTop: i === 0 ? "none" : `1px solid ${c.line}` }}>
                                <span style={{ fontSize: 12.5, color: c.ink, fontWeight: 600 }}>{a.factor}</span>
                                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                                    {typeof a.ic_recent === "number" ? <span style={{ fontSize: 11.5, color: c.sub }}>IC <span style={{ ...NUM, color: c.ink }}>{a.ic_recent.toFixed(3)}</span></span> : null}
                                    {m != null ? <span style={{ fontSize: 12, fontWeight: 700, color: mCol, ...NUM }}>×{m.toFixed(2)}</span> : null}
                                </div>
                            </div>
                        )
                    })}
                </div>
            ) : null}

            <div style={{ fontSize: 10.5, color: c.faint, lineHeight: 1.5 }}>
                {rep._corrections_meta ? (
                    <>비용 반영: 왕복 {((rep._corrections_meta.tx_cost_pct_round_trip ?? 0) * 100).toFixed(2)}% · {rep._corrections_meta.slippage_model || "슬리피지 모델"} · 상폐 {(rep._corrections_meta.delisted_return_pct ?? 0)}% · </>
                ) : null}
                자기 검증 trail(가설) · 매수/매도 지시 아님
            </div>
        </div>
    )
}

function FactorChip({ c, label, n, color, soft }: { c: Palette; label: string; n: number; color: string; soft: string }) {
    return (
        <span style={{ display: "inline-flex", alignItems: "baseline", gap: 5, fontSize: 12, fontWeight: 700, color, background: soft, borderRadius: 8, padding: "5px 10px" }}>
            {label} <span style={{ ...NUM }}>{n}</span>
        </span>
    )
}

function PerfLive({ c, p }: { c: Palette; p: Perf }) {
    // 🚨 RULE 7: hit rate 단독 금지 — 표본수 캐비엇 항상 병기.
    const cell = (k: string, v: number | null | undefined, pct = true) =>
        typeof v === "number" && isFinite(v) ? (
            <span style={{ fontSize: 12, color: c.sub }}>
                {k} <b style={{ color: c.ink, ...NUM }}>{pct ? (v * 100).toFixed(1) + "%" : v.toFixed(2)}</b>
            </span>
        ) : null
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
                {cell("hit 7d", p.hit_rate_7d)}
                {cell("hit 14d", p.hit_rate_14d)}
                {cell("hit 30d", p.hit_rate_30d)}
                {cell("평균수익 14d", p.avg_return_14d)}
                {cell("Sharpe 14d", p.sharpe_14d, false)}
            </div>
            <div style={{ fontSize: 11, color: c.amber, lineHeight: 1.5 }}>
                예비 결과 — 표본수·신뢰구간 확인 전 판단 유보(N&lt;252, 2027 게이트 전).
            </div>
        </div>
    )
}
