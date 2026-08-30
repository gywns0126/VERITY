"use client"
// CapitalPathCard — 6 Tier 자본 진화 path (구 프레이머 `pages/admin/CapitalEvolutionPath.tsx` 이관, PM 2026-08-12).
// Tier spec = [[project_capital_evolution_path]] (6 tier × 시스템 형태/universe/전환 checklist).
//
// 🚨 RULE 7 유지 — **Tier 도달 시점 추정 절대 금지.** 자본은 부산물이고 진화 trigger 는 시스템 성숙도다.
//    시점/기간/CAGR 목표를 이 컴포넌트에 다시 넣지 말 것.
//
// 이관 시 바뀐 것 (되돌리지 말 것):
//   · 데이터 = 페이지가 소유한 슬림 페이로드(`portfolio_terminal`)의 vams 를 **prop 으로** 받는다.
//     원본은 컴포넌트가 직접 `portfolio_full`(3.57MB)을 5분마다 당겨 Safari 메모리 킬 위험이 있었다.
//   · 하드코딩 면책 배너("⚠ 베타 단계 (운영 N=14일, VAMS reset 5/17)") 제거 — 5월 값으로 굳어 stale 이었고,
//     오퍼레이터는 본인 전용이라 면책 문구를 두지 않는다 ([[feedback_operator_is_private_no_disclaimers]]).
//     검증 N 은 실데이터로 CockpitCard 가 표시한다.
//   · TIDE 다크 토큰 → 오퍼레이터 팔레트.
import { useState } from "react"
import { useDark, palette, cardStyle, CARD_TITLE, RAIL_PAD, FONT, NUM } from "@/lib/theme"
import type { Vams } from "@/lib/types"

type TierSpec = {
    tier: number
    min_krw: number
    max_krw: number
    max_holdings_aggressive: number
    system_form: string
    universe: string
    transition_checklist: string[]
}

const TIERS: TierSpec[] = [
    {
        tier: 1, min_krw: 1e7, max_krw: 1e8, max_holdings_aggressive: 7,
        system_form: "현재 시스템 그대로 적합 (1인 단독, moderate profile, VAMS 가상매매)",
        universe: "KR 코어 화이트리스트 85",
        transition_checklist: [
            "long_term 프로필 추가 (api/config.py:VAMS_PROFILES)",
            "multi_bagger_watch panel 활성 (Phase 2 신규)",
            "holdings 활용도 60%+ 안정 6주",
        ],
    },
    {
        tier: 2, min_krw: 1e8, max_krw: 5e8, max_holdings_aggressive: 10,
        system_form: "long_term 프로필 + multi_bagger_watch 활성",
        universe: "KR 확장 (KOSPI 700 + KOSDAQ 1,300, Phase 2-A)",
        transition_checklist: ["US 시장 universe 추가 (S&P 500 일부, US 30%)", "종목 수 15~20 확대", "환율/환헷지 정책 신규"],
    },
    {
        tier: 3, min_krw: 5e8, max_krw: 20e8, max_holdings_aggressive: 15,
        system_form: "종목 수 ↑ + 미국 시장 30%",
        universe: "KR + US 30% (S&P 500 large cap 일부)",
        transition_checklist: ["미국 70% 비중 전환 + 페어 트레이딩", "FactSet 또는 Refinitiv 검토", "advisor 1명 search (회당 검토)"],
    },
    {
        tier: 4, min_krw: 20e8, max_krw: 50e8, max_holdings_aggressive: 25,
        system_form: "미국 70% + 페어 트레이딩",
        universe: "KR + US 70% (mid + small)",
        transition_checklist: ["Bloomberg Terminal 1대 도입 검토", "advisor 풀 1명 채용 (정량 검토)", "monthly risk report (VaR/CVaR/scenario)"],
    },
    {
        tier: 5, min_krw: 50e8, max_krw: 100e8, max_holdings_aggressive: 40,
        system_form: "미국 mid/large + advisor 1명",
        universe: "KR + US + Global 일부 (유럽 large cap)",
        transition_checklist: ["family office 거버넌스 검토", "PM + analyst 2명 + risk 1명 풀 팀", "monthly board + compliance 자체 audit"],
    },
    {
        tier: 6, min_krw: 100e8, max_krw: Infinity, max_holdings_aggressive: 60,
        system_form: "Bloomberg + family office governance",
        universe: "Global universe (Bloomberg)",
        transition_checklist: ["자본 cap 의사결정 (성장 vs 보존)"],
    },
]

function fmtKRW(n?: number | null): string {
    if (n == null || !isFinite(n)) return "—"
    if (n >= 1e8) return `${(n / 1e8).toFixed(1)}억`
    if (n >= 1e4) return `${(n / 1e4).toFixed(0)}만`
    return n.toLocaleString()
}

function currentTier(totalAsset?: number | null): TierSpec {
    if (totalAsset == null || totalAsset < TIERS[0].min_krw) return TIERS[0]
    for (const t of TIERS) if (totalAsset >= t.min_krw && totalAsset < t.max_krw) return t
    return TIERS[TIERS.length - 1]
}

export default function CapitalPathCard({ vams, status = "ok" }: { vams?: Vams; status?: "loading" | "ok" | "error" }) {
    const dark = useDark()
    const c = palette(dark)
    const [expanded, setExpanded] = useState(false)

    const totalAsset = vams?.total_asset
    const cash = vams?.cash
    const totalReturnPct = vams?.total_return_pct
    const holdings = vams?.holdings || []

    const tier = currentTier(totalAsset)
    const nextTier = TIERS.find((t) => t.tier === tier.tier + 1)
    const progress =
        totalAsset == null || tier.max_krw === Infinity
            ? 100
            : Math.max(0, Math.min(100, ((totalAsset - tier.min_krw) / (tier.max_krw - tier.min_krw)) * 100))
    const cashPct = totalAsset ? Math.round(((cash || 0) / totalAsset) * 100) : null
    const utilizationPct = tier.max_holdings_aggressive > 0 ? Math.round((holdings.length / tier.max_holdings_aggressive) * 100) : null

    const wrap = { ...cardStyle(c, RAIL_PAD), fontFamily: FONT, display: "flex", flexDirection: "column" as const, gap: 10 }
    if (status === "error") return <div style={wrap}><span style={{ fontSize: 12, color: c.down }}>자본 path 원천을 불러오지 못했습니다.</span></div>
    if (status === "loading" || !vams) return <div style={wrap}><span style={{ fontSize: 12, color: c.faint }}>자본 path 로딩…</span></div>

    const sub = (label: string, value: string, tone?: "ok" | "warn") => (
        <div key={label} style={{ background: c.hi, borderRadius: 10, padding: "7px 9px" }}>
            <div style={{ fontSize: 9.5, color: c.faint, fontWeight: 700, marginBottom: 2 }}>{label}</div>
            <div style={{ fontSize: 11.5, fontWeight: 700, lineHeight: 1.3, color: tone === "warn" ? c.amber : tone === "ok" ? c.green : c.ink, wordBreak: "break-all" }}>{value}</div>
        </div>
    )

    return (
        <div style={wrap}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
                <span style={{ ...CARD_TITLE, color: c.ink }}>자본 진화 path</span>
                <span style={{ fontSize: 13, fontWeight: 800, color: c.vt }}>Tier {tier.tier}</span>
                <span style={{ fontSize: 12.5, color: c.sub, ...NUM }}>{fmtKRW(totalAsset)}</span>
                {typeof totalReturnPct === "number" ? (
                    <span style={{ fontSize: 11.5, fontWeight: 800, ...NUM, color: totalReturnPct >= 0 ? c.up : c.down }}>
                        {totalReturnPct >= 0 ? "+" : ""}{totalReturnPct.toFixed(2)}%
                    </span>
                ) : null}
                <span style={{ marginLeft: "auto", fontSize: 10, color: c.faint }}>성숙도 함수 · 자본은 부산물</span>
            </div>

            <div style={{ display: "flex", gap: 4 }}>
                {TIERS.map((t) => {
                    const isCurrent = t.tier === tier.tier
                    const isPast = t.tier < tier.tier
                    return (
                        <div
                            key={t.tier}
                            title={`Tier ${t.tier}: ${fmtKRW(t.min_krw)} ~ ${t.max_krw === Infinity ? "∞" : fmtKRW(t.max_krw)} / ${t.system_form}`}
                            style={{
                                flex: 1, height: 34, borderRadius: 8, display: "flex", flexDirection: "column",
                                alignItems: "center", justifyContent: "center",
                                background: isCurrent ? c.vt : isPast ? c.vtS : c.track,
                            }}
                        >
                            <span style={{ fontSize: 9.5, fontWeight: 800, color: isCurrent ? "#fff" : isPast ? c.vt : c.faint }}>T{t.tier}</span>
                            <span style={{ fontSize: 9, ...NUM, color: isCurrent ? "rgba(255,255,255,0.85)" : c.faint }}>{fmtKRW(t.min_krw)}</span>
                        </div>
                    )
                })}
            </div>

            {nextTier ? (
                <div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9.5, color: c.faint, marginBottom: 3, ...NUM }}>
                        <span>{fmtKRW(tier.min_krw)} (T{tier.tier})</span>
                        <span style={{ color: c.vt, fontWeight: 800 }}>{progress.toFixed(1)}% → T{nextTier.tier}</span>
                        <span>{fmtKRW(tier.max_krw)} (T{nextTier.tier})</span>
                    </div>
                    <div style={{ height: 5, background: c.track, borderRadius: 999, overflow: "hidden" }}>
                        <div style={{ height: "100%", width: `${progress}%`, background: c.vt, borderRadius: 999 }} />
                    </div>
                </div>
            ) : null}

            <div style={{ display: "grid", gap: 6, gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))" }}>
                {sub("시스템 형태", tier.system_form.split("(")[0].trim())}
                {sub("universe", tier.universe)}
                {sub("현재 활용도", utilizationPct != null ? `${holdings.length}/${tier.max_holdings_aggressive} (${utilizationPct}%)` : "—", utilizationPct != null && utilizationPct >= 90 ? "warn" : undefined)}
                {sub("현금 비중", cashPct != null ? `${cashPct}%` : "—", cashPct != null && cashPct < 90 ? "ok" : undefined)}
            </div>

            {nextTier ? (
                <div>
                    <button
                        onClick={() => setExpanded(!expanded)}
                        style={{ border: "none", background: c.hi, color: c.sub, borderRadius: 999, padding: "5px 12px", fontSize: 10.5, fontWeight: 800, cursor: "pointer", fontFamily: FONT }}
                    >
                        {expanded ? "▲" : "▼"} T{nextTier.tier} 전환 checklist ({nextTier.transition_checklist.length})
                    </button>
                    {expanded ? (
                        <div style={{ marginTop: 8, padding: "10px 12px", background: c.hi, borderRadius: 12, display: "flex", flexDirection: "column", gap: 5 }}>
                            {nextTier.transition_checklist.map((item, i) => (
                                <div key={i} style={{ display: "flex", gap: 7, alignItems: "flex-start", fontSize: 11.5, color: c.sub, lineHeight: 1.5 }}>
                                    <span style={{ width: 12, height: 12, borderRadius: 3, background: c.track, flexShrink: 0, marginTop: 2 }} />
                                    <span>{item}</span>
                                </div>
                            ))}
                            <div style={{ marginTop: 5, paddingTop: 5, borderTop: `1px solid ${c.line}`, fontSize: 9.5, color: c.faint, ...NUM }}>
                                전환 임계 {fmtKRW(nextTier.min_krw)} 도달 시 sprint 진입 — 도달 시점은 추정하지 않는다
                            </div>
                        </div>
                    ) : null}
                </div>
            ) : null}
        </div>
    )
}
