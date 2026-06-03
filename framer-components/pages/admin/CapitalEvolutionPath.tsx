import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState, type CSSProperties } from "react"

/**
 * CapitalEvolutionPath — VERITY 의 6 Tier 자본 진화 path 시각화 (2026-05-17).
 *
 * 빅브라더 정합 ([[feedback_no_new_llm_narrative_features]], CLAUDE.md RULE 6):
 *   LLM 위협 영역 = narrative. VERITY 의 LLM 못 가진 5 차별점 중 #1 = 자기 자본 진화 path.
 *   ChatGPT Pro / Claude for Small Business 가 못 만드는 unique view = 자기 1년 trail.
 *
 * 컴포넌트 가치:
 *   - 운영자가 한눈에 "지금 Tier 1 → 2 어디까지 왔는지" 확인
 *   - 다음 transition checklist 미리 보기 (Tier 진입 sprint 준비)
 *   - VAMS total_asset 변화 시계열 = 1년 trail 자산 (LLM 못 가짐)
 *
 * 데이터 source:
 *   - portfolio.json::vams (total_asset / cash / active_profile / total_return_pct / holdings)
 *
 * 메모리: [[project_capital_evolution_path]] (2026-05-02, 6 tier × 7축 진화 spec).
 *
 * feedback_no_hardcode_position 정합 — position:fixed 하드코드 X (Framer 사용자 배치).
 * feedback_estate_density_first 정합 — 밀도 우선 (펜타그램 4 원칙).
 */

/* ◆ DESIGN TOKENS — VERITY 마스터 ◆ */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B",
    border: "rgba(255,255,255,0.06)", borderStrong: "rgba(255,255,255,0.10)",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#7fffa0", accentSoft: "rgba(127, 255, 160,0.12)",
    success: "#22C55E", warn: "#F59E0B", danger: "#EF4444",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Menlo', monospace"
const MONO: CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }


/* ◆ 6 TIER SPEC (project_capital_evolution_path 메모리 정합) ◆ */
interface TierSpec {
    tier: number
    label: string
    min_krw: number   // 자본 범위 하한
    max_krw: number   // 자본 범위 상한 (다음 tier 진입 임계)
    max_holdings_aggressive: number
    system_form: string  // 핵심 시스템 형태
    universe: string     // 시장 universe
    transition_checklist: string[]  // 다음 tier 진입 checklist (top 2-3)
}

const TIERS: TierSpec[] = [
    {
        tier: 1, label: "Tier 1", min_krw: 1e7, max_krw: 1e8,
        max_holdings_aggressive: 7,
        system_form: "현재 시스템 그대로 적합 (1인 단독, moderate profile, VAMS 가상매매)",
        universe: "KR 코어 화이트리스트 85",
        transition_checklist: [
            "long_term 프로필 추가 (api/config.py:VAMS_PROFILES)",
            "multi_bagger_watch panel 활성 (Phase 2 신규)",
            "holdings 활용도 60%+ 안정 6주",
        ],
    },
    {
        tier: 2, label: "Tier 2", min_krw: 1e8, max_krw: 5e8,
        max_holdings_aggressive: 10,
        system_form: "long_term 프로필 + multi_bagger_watch 활성",
        universe: "KR 확장 (KOSPI 700 + KOSDAQ 1,300, Phase 2-A)",
        transition_checklist: [
            "US 시장 universe 추가 (S&P 500 일부, US 30%)",
            "종목 수 15~20 확대",
            "환율/환헷지 정책 신규",
        ],
    },
    {
        tier: 3, label: "Tier 3", min_krw: 5e8, max_krw: 20e8,
        max_holdings_aggressive: 15,
        system_form: "종목 수 ↑ + 미국 시장 30%",
        universe: "KR + US 30% (S&P 500 large cap 일부)",
        transition_checklist: [
            "미국 70% 비중 전환 + 페어 트레이딩",
            "FactSet 또는 Refinitiv 검토",
            "advisor 1명 search (회당 검토)",
        ],
    },
    {
        tier: 4, label: "Tier 4", min_krw: 20e8, max_krw: 50e8,
        max_holdings_aggressive: 25,
        system_form: "미국 70% + 페어 트레이딩",
        universe: "KR + US 70% (mid + small)",
        transition_checklist: [
            "Bloomberg Terminal 1대 도입 검토",
            "advisor 풀 1명 채용 (정량 검토)",
            "monthly risk report (VaR/CVaR/scenario)",
        ],
    },
    {
        tier: 5, label: "Tier 5", min_krw: 50e8, max_krw: 100e8,
        max_holdings_aggressive: 40,
        system_form: "미국 mid/large + advisor 1명",
        universe: "KR + US + Global 일부 (유럽 large cap)",
        transition_checklist: [
            "family office 거버넌스 검토",
            "PM + analyst 2명 + risk 1명 풀 팀",
            "monthly board + compliance 자체 audit",
        ],
    },
    {
        tier: 6, label: "Tier 6", min_krw: 100e8, max_krw: Infinity,
        max_holdings_aggressive: 60,
        system_form: "Bloomberg + family office governance",
        universe: "Global universe (Bloomberg)",
        transition_checklist: ["자본 cap 의사결정 (성장 vs 보존)"],
    },
]


/* ◆ HELPERS ◆ */
function fetchPortfolio(url: string, signal?: AbortSignal): Promise<any> {
    const u = (url || "").trim()
    const sep = u.includes("?") ? "&" : "?"
    return fetch(`${u}${sep}_=${Date.now()}`, {
        cache: "no-store", mode: "cors", credentials: "omit", signal,
    })
        .then((r) => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`)
            return r.text()
        })
        .then((txt) => JSON.parse(txt.replace(/\bNaN\b/g, "null").replace(/\bInfinity\b/g, "null")))
}

function fmtKRW(n?: number | null): string {
    if (n == null) return "—"
    if (n >= 1e8) return `${(n / 1e8).toFixed(1)}억`
    if (n >= 1e4) return `${(n / 1e4).toFixed(0)}만`
    return n.toLocaleString()
}

function currentTier(totalAsset?: number | null): TierSpec {
    if (totalAsset == null) return TIERS[0]
    for (const t of TIERS) {
        if (totalAsset >= t.min_krw && totalAsset < t.max_krw) return t
    }
    return TIERS[TIERS.length - 1]
}

function progressToNextTier(totalAsset?: number | null, tier?: TierSpec): number {
    if (totalAsset == null || !tier || tier.max_krw === Infinity) return 100
    const range = tier.max_krw - tier.min_krw
    const progress = (totalAsset - tier.min_krw) / range
    return Math.max(0, Math.min(100, progress * 100))
}


/* ◆ Props ◆ */
interface Props {
    portfolioUrl: string
    refreshIntervalSec: number
    maxWidth: number
}


/* ◆ Main Component ◆ */
function CapitalEvolutionPath({ portfolioUrl, refreshIntervalSec, maxWidth }: Props) {
    const [data, setData] = useState<any | null>(null)
    const [err, setErr] = useState<string | null>(null)
    const [expanded, setExpanded] = useState(false)

    useEffect(() => {
        if (!portfolioUrl) return
        const ac = new AbortController()
        const tick = () => {
            fetchPortfolio(portfolioUrl, ac.signal)
                .then((p) => { setData(p); setErr(null) })
                .catch((e) => { if (e?.name !== "AbortError") setErr(e?.message || "fetch failed") })
        }
        tick()
        const id = refreshIntervalSec > 0
            ? window.setInterval(tick, Math.max(60, refreshIntervalSec) * 1000)
            : undefined
        return () => { ac.abort(); if (id) window.clearInterval(id) }
    }, [portfolioUrl, refreshIntervalSec])

    const vams = (data?.vams || {}) as any
    const totalAsset = vams.total_asset as number | undefined
    const cash = vams.cash as number | undefined
    const totalReturnPct = vams.total_return_pct as number | undefined
    const activeProfile = vams.active_profile as string | undefined
    const holdings = (vams.holdings || []) as any[]
    const resetMeta = vams.reset_meta as any

    const tier = currentTier(totalAsset)
    const progress = progressToNextTier(totalAsset, tier)
    const cashPct = totalAsset ? Math.round((cash || 0) / totalAsset * 100) : null
    const utilizationPct = tier.max_holdings_aggressive > 0
        ? Math.round((holdings.length / tier.max_holdings_aggressive) * 100)
        : null
    const nextTier = TIERS.find((t) => t.tier === tier.tier + 1)

    return (
        <div style={{
            width: "100%", maxWidth: maxWidth || undefined,
            background: C.bgCard, borderRadius: 12,
            padding: "20px 24px",
            fontFamily: FONT, color: C.textPrimary,
            boxSizing: "border-box",
        }}>
            {/* Header */}
            <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 4, flexWrap: "wrap" }}>
                <span style={{
                    fontSize: 11, color: C.textTertiary,
                    textTransform: "uppercase", letterSpacing: 1.5, fontWeight: 700,
                }}>
                    Capital Evolution Path
                </span>
                <span style={{
                    fontSize: 22, fontWeight: 800,
                    color: C.accent, letterSpacing: -0.3,
                }}>
                    {tier.label}
                </span>
                <span style={{ fontSize: 14, color: C.textSecondary, ...MONO }}>
                    {fmtKRW(totalAsset)}
                </span>
                {totalReturnPct != null && (
                    <span style={{
                        fontSize: 12, fontWeight: 700, ...MONO,
                        color: totalReturnPct >= 0 ? C.success : C.danger,
                    }}>
                        {totalReturnPct >= 0 ? "+" : ""}{totalReturnPct.toFixed(2)}%
                    </span>
                )}
                <span style={{ flex: 1 }} />
                {err && (
                    <span style={{ fontSize: 10, color: C.danger, fontWeight: 600 }}>
                        ⚠ {err}
                    </span>
                )}
            </div>

            <div style={{ fontSize: 11, color: C.textTertiary, marginBottom: 4, fontStyle: "italic" }}>
                시스템 성숙도 함수 — 자본은 부산물이지 목표가 아님
            </div>
            <div style={{
                fontSize: 10, color: C.warn, marginBottom: 16,
                padding: "4px 8px", background: `${C.warn}10`,
                borderRadius: 4, border: `1px solid ${C.warn}30`,
                display: "inline-block",
            }}>
                ⚠ 베타 단계 (운영 N=14일, VAMS reset 5/17). 도달 시점 추정 X — 시스템 성숙도 × 시장 기회의 함수.
            </div>

            {/* 6 Tier path bar — 가로 6 segments */}
            <div style={{
                display: "flex", gap: 4, marginBottom: 14, alignItems: "stretch",
            }}>
                {TIERS.map((t) => {
                    const isCurrent = t.tier === tier.tier
                    const isPast = t.tier < tier.tier
                    const segColor = isCurrent ? C.accent : isPast ? C.accentSoft : C.bgElevated
                    return (
                        <div key={t.tier} style={{
                            flex: 1,
                            height: 36,
                            background: segColor,
                            border: isCurrent ? `1px solid ${C.accent}` : `1px solid transparent`,
                            borderRadius: 6,
                            display: "flex", flexDirection: "column",
                            alignItems: "center", justifyContent: "center",
                            position: "relative",
                            cursor: "default",
                        }} title={`${t.label}: ${fmtKRW(t.min_krw)} ~ ${t.max_krw === Infinity ? "∞" : fmtKRW(t.max_krw)} / ${t.system_form}`}>
                            <span style={{
                                fontSize: 10, fontWeight: 800,
                                color: isCurrent ? C.bgPage : isPast ? C.accent : C.textTertiary,
                                letterSpacing: 0.5,
                            }}>
                                T{t.tier}
                            </span>
                            <span style={{
                                fontSize: 9, ...MONO,
                                color: isCurrent ? C.bgPage : C.textTertiary,
                            }}>
                                {fmtKRW(t.min_krw)}
                            </span>
                            {isCurrent && (
                                <div style={{
                                    position: "absolute", top: -6, left: "50%",
                                    width: 0, height: 0,
                                    borderLeft: "5px solid transparent",
                                    borderRight: "5px solid transparent",
                                    borderTop: `5px solid ${C.accent}`,
                                    transform: "translateX(-50%) rotate(180deg)",
                                }} />
                            )}
                        </div>
                    )
                })}
            </div>

            {/* Tier 내 progress bar (현재 자본 → 다음 임계) */}
            {nextTier && (
                <div style={{ marginBottom: 18 }}>
                    <div style={{
                        display: "flex", justifyContent: "space-between",
                        fontSize: 10, color: C.textTertiary, marginBottom: 4, ...MONO,
                    }}>
                        <span>{fmtKRW(tier.min_krw)} (T{tier.tier})</span>
                        <span style={{ color: C.accent, fontWeight: 700 }}>
                            {progress.toFixed(1)}% → T{nextTier.tier}
                        </span>
                        <span>{fmtKRW(tier.max_krw)} (T{nextTier.tier})</span>
                    </div>
                    <div style={{
                        height: 6, background: C.bgElevated, borderRadius: 3, overflow: "hidden",
                    }}>
                        <div style={{
                            height: "100%", width: `${progress}%`,
                            background: `linear-gradient(90deg, ${C.accent}, ${C.success})`,
                            transition: "width 600ms ease",
                        }} />
                    </div>
                </div>
            )}

            {/* Current Tier sub-stats */}
            <div style={{
                display: "grid", gap: 8,
                gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
                marginBottom: 14,
            }}>
                <SubStat label="System Form" value={tier.system_form.split("(")[0].trim()} small />
                <SubStat label="Universe" value={tier.universe} small />
                <SubStat label="현재 활용도"
                    value={utilizationPct != null
                        ? `${holdings.length}/${tier.max_holdings_aggressive} (${utilizationPct}%)`
                        : "—"}
                    tone={utilizationPct != null && utilizationPct >= 90 ? "warn" : "neutral"} />
                <SubStat label="현금 비중"
                    value={cashPct != null ? `${cashPct}%` : "—"}
                    tone={cashPct != null && cashPct >= 90 ? "neutral" : "ok"} />
                <SubStat label="active profile"
                    value={activeProfile || "—"} />
                <SubStat label="reset since"
                    value={resetMeta?.reset_at?.slice(0, 10) || "—"} small />
            </div>

            {/* Expandable: 다음 Tier transition checklist */}
            {nextTier && (
                <div>
                    <button
                        onClick={() => setExpanded(!expanded)}
                        style={{
                            background: "transparent", border: `1px solid ${C.border}`,
                            color: C.textSecondary, padding: "6px 12px", borderRadius: 6,
                            fontSize: 11, fontFamily: FONT, fontWeight: 600,
                            cursor: "pointer", letterSpacing: 0.3,
                            transition: "all 200ms ease",
                        }}>
                        {expanded ? "▲" : "▼"} T{nextTier.tier} 전환 checklist ({nextTier.transition_checklist.length})
                    </button>
                    {expanded && (
                        <div style={{
                            marginTop: 10, padding: "12px 14px",
                            background: C.bgElevated, borderRadius: 8,
                            display: "flex", flexDirection: "column", gap: 6,
                        }}>
                            {nextTier.transition_checklist.map((item, i) => (
                                <div key={i} style={{
                                    display: "flex", gap: 8, alignItems: "flex-start",
                                    fontSize: 12, color: C.textSecondary, lineHeight: 1.5,
                                }}>
                                    <span style={{
                                        width: 14, height: 14, borderRadius: 3,
                                        border: `1px solid ${C.borderStrong}`,
                                        flexShrink: 0, marginTop: 2,
                                    }} />
                                    <span>{item}</span>
                                </div>
                            ))}
                            <div style={{
                                marginTop: 8, paddingTop: 8,
                                borderTop: `1px solid ${C.border}`,
                                fontSize: 10, color: C.textTertiary, ...MONO,
                            }}>
                                전환 임계: {fmtKRW(nextTier.min_krw)} 도달 시 sprint 진입
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Footer — 자기 trail 자산 + 정직성 명시 */}
            <div style={{
                marginTop: 14, paddingTop: 10,
                borderTop: `1px solid ${C.border}`,
                fontSize: 10, color: C.textTertiary, ...MONO, lineHeight: 1.5,
            }}>
                source: portfolio.json::vams · spec: project_capital_evolution_path
                <br />
                <span style={{ color: C.warn }}>
                    ⚠ 가설 상태 — Tier 1→6 시점 추정 X. 자본 도달 = 시스템 성숙도 × 시장 기회의 함수.
                </span>
                <br />
                CAGR baseline: 메달리온 펀드 66%/년 (역사 최고 헤지펀드). 1,000만→100억 = 1,000배 = 6년 215%/년 ≈ 불가능.
                <br />
                LLM 가입자 못 가지는 unique trail (자본 + PM 동시 진화)
            </div>
        </div>
    )
}


function SubStat({ label, value, tone, small }: {
    label: string; value: string; tone?: "ok" | "warn" | "neutral"; small?: boolean
}) {
    const valColor = tone === "ok" ? C.success
        : tone === "warn" ? C.warn
        : C.textPrimary
    return (
        <div style={{
            background: C.bgElevated, padding: "8px 10px", borderRadius: 6,
        }}>
            <div style={{
                fontSize: 9, color: C.textTertiary, fontWeight: 600,
                textTransform: "uppercase", letterSpacing: 1, marginBottom: 4,
            }}>
                {label}
            </div>
            <div style={{
                fontSize: small ? 11 : 13, color: valColor, fontWeight: 600,
                lineHeight: 1.3, wordBreak: "break-all",
            }}>
                {value}
            </div>
        </div>
    )
}


CapitalEvolutionPath.defaultProps = {
    portfolioUrl: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/portfolio.json",
    refreshIntervalSec: 300,  // 5분 (자본 변화 주기 = 시장 시간 매매)
    maxWidth: 1000,
}

addPropertyControls(CapitalEvolutionPath, {
    portfolioUrl: {
        type: ControlType.String,
        title: "Portfolio URL",
        defaultValue: "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/portfolio.json",
    },
    refreshIntervalSec: {
        type: ControlType.Number,
        title: "Refresh (sec)",
        defaultValue: 300,
        min: 60,
        max: 3600,
        step: 30,
    },
    maxWidth: {
        type: ControlType.Number,
        title: "Max Width (px)",
        defaultValue: 1000,
        min: 0, max: 2400, step: 50,
        description: "0 = 무제한",
    },
})

export default CapitalEvolutionPath
