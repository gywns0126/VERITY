"use client"
// VerificationPanel — ④ 검증 층 (오퍼레이터 전용, authed). 공개 알파네스트 디자인.
// 되돌리지 말 것: fetchOperator("verification")=verification_report.json(private bucket). 공개 blob 직독 금지.
//   🚨 RULE 7: performance 실값 없으면(미검증) 가짜 hit rate 금지 — "축적 중" 정직 표기.
//   🚨 2026-08-18 — 종전엔 "2027 게이트" 를 적었다. 그 게이트(N=252 IC, 2027-05)는 §7-1 로 폐기됐다.
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
    sample_7d?: number | null
    sample_14d?: number | null
    sample_30d?: number | null
    hit_rate_7d_ci95?: [number, number] | null
    hit_rate_14d_ci95?: [number, number] | null
    hit_rate_30d_ci95?: [number, number] | null
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
    return (
        typeof p.hit_rate_14d === "number" &&
        typeof p.avg_return_14d === "number" &&
        typeof p.sample_14d === "number" &&
        p.sample_14d > 0 &&
        Array.isArray(p.hit_rate_14d_ci95) &&
        p.hit_rate_14d_ci95.length === 2
    )
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
    const unclassified = Math.max(0, (fh.total_factors || 0) - (fh.healthy || []).length - (fh.weakening || []).length - (fh.decaying || []).length)
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
                            <span style={{ fontSize: 11, fontWeight: 700, color: c.vt, background: c.vtS, borderRadius: 8, padding: "3px 9px" }}>미검증</span>
                            <span style={{ fontSize: 11, fontWeight: 700, color: c.sub, background: c.hi, borderRadius: 8, padding: "3px 9px", ...NUM }}>검증 축적 중</span>
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
                        {unclassified > 0 ? <FactorChip c={c} label="미분류" n={unclassified} color={c.sub} soft={c.hi} /> : null}
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
                자기 검증 trail(가설)
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
    // 값은 생성기에서 이미 퍼센트 단위다. 적중률은 N·Wilson 95% CI와 함께만 표시한다.
    const hitCell = (k: string, v: number | null | undefined, n: number | null | undefined, ci: [number, number] | null | undefined) =>
        typeof v === "number" && isFinite(v) && typeof n === "number" && n > 0 && Array.isArray(ci) ? (
            <span style={{ fontSize: 12, color: c.sub }}>
                {k} <b style={{ color: c.ink, ...NUM }}>{v.toFixed(1)}%</b>
                <span style={{ color: c.faint, ...NUM }}> · N={n} · 95% CI {ci[0].toFixed(1)}~{ci[1].toFixed(1)}%</span>
            </span>
        ) : null
    return (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
                {hitCell("hit 7d", p.hit_rate_7d, p.sample_7d, p.hit_rate_7d_ci95)}
                {hitCell("hit 14d", p.hit_rate_14d, p.sample_14d, p.hit_rate_14d_ci95)}
                {hitCell("hit 30d", p.hit_rate_30d, p.sample_30d, p.hit_rate_30d_ci95)}
                {typeof p.avg_return_14d === "number" ? <span style={{ fontSize: 12, color: c.sub }}>기대수익(평균) 14d <b style={{ color: c.ink, ...NUM }}>{p.avg_return_14d.toFixed(2)}%</b></span> : null}
                {typeof p.sharpe_14d === "number" ? <span style={{ fontSize: 12, color: c.sub }}>Sharpe 14d <b style={{ color: c.ink, ...NUM }}>{p.sharpe_14d.toFixed(2)}</b></span> : null}
            </div>
            <div style={{ fontSize: 11, color: c.amber, lineHeight: 1.5 }}>
                예비 결과 — 표본수와 신뢰구간이 넓으면 판단을 유보합니다.
            </div>
        </div>
    )
}
