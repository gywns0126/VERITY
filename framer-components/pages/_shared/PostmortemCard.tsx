import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useMemo, useState } from "react"

/**
 * VERITY PostmortemCard — AI 오심 복기 카드 (TIDE 정합 디자인)
 *
 * source: portfolio.json [postmortem] — daily_analysis_full cron 7일 trail
 * RULE 6 정합: 자기 trail = LLM 못 가진 차별 자산
 * TIDE design system: docs/design_system_tide.md (SoT: codeFile OUAKBZw)
 */

interface Props {
    portfolioUrl: string
    refreshIntervalSec: number
    compact: boolean
}

const C = {
    bgPage: "#0a0a0a",
    bgCard: "#141414",
    bgSection: "rgba(255,255,255,0.02)",
    border: "rgba(255,255,255,0.06)",
    borderSubtle: "rgba(255,255,255,0.04)",
    textPrimary: "#ffffff",
    textBody: "#F2F3F5",
    textSecondary: "#A8ABB2",
    textTertiary: "#6B6E76",
    buy: "#7fffa0",
    watch: "#5BA9FF",
    caution: "#FFA05A",
    avoid: "#FF5A5A",
    info: "#5BA9FF",
} as const

const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"

const labelStyle: React.CSSProperties = {
    fontSize: 11,
    color: C.textTertiary,
    textTransform: "uppercase",
    letterSpacing: "0.04em",
    fontWeight: 600,
}

interface Failure {
    type?: string
    ticker?: string
    name?: string
    original_rec?: string
    actual_return?: number
    ai_verdict?: string
    risk_flags?: string[]
    lesson?: string
    misleading_factor?: string
    brain_score?: number
    brain_grade?: string
}

interface Postmortem {
    status?: string
    failures?: Failure[]
    analyzed_count?: number
    period?: string
    summary?: string
    lesson?: string
    system_suggestion?: string
    quality_label?: string
    trail_sufficient?: boolean
    coverage_ratio?: number
    misleading_factors?: Record<string, number>
    generated_at?: string
}

function formatReturn(r?: number): { text: string; color: string } {
    if (r == null || isNaN(r)) return { text: "—", color: C.textTertiary }
    const sign = r >= 0 ? "+" : ""
    const color = r >= 0 ? C.buy : C.avoid
    return { text: `${sign}${r.toFixed(2)}%`, color }
}

function gradeColor(g?: string): string {
    if (!g) return C.textTertiary
    if (g === "STRONG_BUY" || g === "BUY") return C.buy
    if (g === "WATCH") return C.watch
    if (g === "CAUTION") return C.caution
    if (g === "AVOID") return C.avoid
    return C.textSecondary
}

function FailureRow({ f, compact }: { f: Failure; compact: boolean }) {
    const ret = formatReturn(f.actual_return)
    const flagsLimit = compact ? 2 : 3
    const flags = (f.risk_flags || []).slice(0, flagsLimit)
    return (
        <div style={{ padding: "10px 0", borderBottom: `1px solid ${C.borderSubtle}` }}>
            <div style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                gap: 12,
                flexWrap: "wrap",
                marginBottom: 6,
            }}>
                <div style={{ display: "flex", gap: 8, alignItems: "baseline", minWidth: 0 }}>
                    <span style={{
                        color: C.textPrimary,
                        fontSize: compact ? 13 : 14,
                        fontWeight: 600,
                        fontFamily: FONT,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                    }}>
                        {f.name || f.ticker || "—"}
                    </span>
                    {f.ticker && !compact && (
                        <span style={{
                            color: C.textTertiary,
                            fontSize: 11,
                            fontFamily: FONT_MONO,
                            fontVariantNumeric: "tabular-nums",
                        }}>
                            {f.ticker}
                        </span>
                    )}
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                    <span style={{
                        color: gradeColor(f.original_rec),
                        fontSize: 11,
                        fontWeight: 600,
                        textTransform: "uppercase",
                        letterSpacing: "0.04em",
                    }}>
                        {f.original_rec || "—"}
                    </span>
                    <span style={{ color: C.textTertiary, fontSize: 11 }}>→</span>
                    <span style={{
                        color: ret.color,
                        fontSize: 13,
                        fontWeight: 600,
                        fontFamily: FONT_MONO,
                        fontVariantNumeric: "tabular-nums",
                    }}>
                        {ret.text}
                    </span>
                </div>
            </div>

            {f.lesson && (
                <div style={{
                    color: C.textSecondary,
                    fontSize: compact ? 12 : 13,
                    lineHeight: 1.5,
                    fontFamily: FONT,
                }}>
                    {f.lesson}
                </div>
            )}

            {flags.length > 0 && !compact && (
                <div style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: 6,
                    marginTop: 6,
                }}>
                    {flags.map((flag, i) => (
                        <span key={i} style={{
                            fontSize: 11,
                            color: C.caution,
                            padding: "2px 8px",
                            border: `1px solid ${C.border}`,
                            borderRadius: 4,
                            fontFamily: FONT,
                        }}>
                            {flag.length > 40 ? flag.substring(0, 40) + "…" : flag}
                        </span>
                    ))}
                </div>
            )}
        </div>
    )
}

export default function PostmortemCard(props: Props) {
    const { portfolioUrl, refreshIntervalSec, compact } = props
    const [pm, setPm] = useState<Postmortem | null>(null)
    const [err, setErr] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        let cancelled = false
        const load = async () => {
            try {
                const r = await fetch(portfolioUrl, { cache: "no-store" })
                if (!r.ok) throw new Error(`HTTP ${r.status}`)
                const data = await r.json()
                if (cancelled) return
                setPm(data?.postmortem || null)
                setErr(null)
                setLoading(false)
            } catch (e) {
                if (cancelled) return
                setErr(String(e))
                setLoading(false)
            }
        }
        load()
        const iv = setInterval(load, Math.max(60, refreshIntervalSec) * 1000)
        return () => {
            cancelled = true
            clearInterval(iv)
        }
    }, [portfolioUrl, refreshIntervalSec])

    const failures = useMemo(() => pm?.failures || [], [pm])
    const hasFailures = failures.length > 0
    const genAt = useMemo(() => {
        if (!pm?.generated_at) return ""
        try {
            const d = new Date(pm.generated_at)
            return d.toLocaleString("ko-KR", {
                month: "2-digit",
                day: "2-digit",
                hour: "2-digit",
                minute: "2-digit",
            })
        } catch {
            return pm.generated_at
        }
    }, [pm])

    const pad = compact ? 16 : 20

    return (
        <div style={{
            width: "100%",
            background: C.bgCard,
            border: `1px solid ${C.border}`,
            borderRadius: 8,
            padding: pad,
            fontFamily: FONT,
            color: C.textBody,
            boxSizing: "border-box",
        }}>
            {/* Header */}
            <div style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
                flexWrap: "wrap",
                gap: 8,
                paddingBottom: 16,
                borderBottom: `1px solid ${C.border}`,
            }}>
                <div style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
                    <span style={labelStyle}>POSTMORTEM</span>
                    {pm?.period && (
                        <span style={{
                            color: C.textTertiary,
                            fontSize: 11,
                            fontFamily: FONT_MONO,
                            fontVariantNumeric: "tabular-nums",
                        }}>
                            {pm.period}
                        </span>
                    )}
                </div>
                {genAt && (
                    <span style={{
                        color: C.textTertiary,
                        fontSize: 11,
                        fontFamily: FONT_MONO,
                        fontVariantNumeric: "tabular-nums",
                    }}>
                        {genAt}
                    </span>
                )}
            </div>

            {loading && (
                <div style={{ color: C.textTertiary, fontSize: 13, padding: "16px 0" }}>
                    loading...
                </div>
            )}
            {err && !loading && (
                <div style={{ color: C.avoid, fontSize: 13, padding: "16px 0" }}>
                    error: {err}
                </div>
            )}

            {!loading && !err && !hasFailures && (
                <div style={{
                    color: C.textTertiary,
                    fontSize: 13,
                    padding: "24px 0",
                    textAlign: "center",
                }}>
                    최근 7일 유의미한 오심 없음
                </div>
            )}

            {!loading && !err && hasFailures && pm?.summary && (
                <div style={{
                    marginTop: 16,
                    color: C.textPrimary,
                    fontSize: 13,
                    fontWeight: 500,
                    fontFamily: FONT,
                    lineHeight: 1.5,
                }}>
                    {pm.summary}
                </div>
            )}

            {!loading && !err && hasFailures && (
                <div style={{ marginTop: 12 }}>
                    {failures.map((f, i) => (
                        <FailureRow key={`${f.ticker}-${i}`} f={f} compact={compact} />
                    ))}
                </div>
            )}

            {!loading && !err && hasFailures && pm?.lesson && !compact && (
                <div style={{
                    marginTop: 20,
                    paddingBottom: 16,
                    borderBottom: `1px solid ${C.border}`,
                }}>
                    <div style={{ ...labelStyle, marginBottom: 8 }}>오늘의 교훈</div>
                    <div style={{
                        color: C.textBody,
                        fontSize: 13,
                        lineHeight: 1.55,
                        fontFamily: FONT,
                    }}>
                        {pm.lesson}
                    </div>
                </div>
            )}

            {!loading && !err && hasFailures && pm?.system_suggestion && (
                <div style={{
                    marginTop: compact ? 16 : 20,
                    paddingBottom: 16,
                    borderBottom: `1px solid ${C.border}`,
                }}>
                    <div style={{
                        ...labelStyle,
                        color: C.avoid,
                        marginBottom: 8,
                    }}>
                        추천 시스템 조치
                    </div>
                    <div style={{
                        color: C.textBody,
                        fontSize: compact ? 12 : 13,
                        lineHeight: 1.55,
                        fontFamily: FONT,
                    }}>
                        {pm.system_suggestion}
                    </div>
                </div>
            )}

            {!loading && !err && (
                <div style={{
                    marginTop: 16,
                    paddingTop: 12,
                    borderTop: `1px solid ${C.borderSubtle}`,
                    display: "flex",
                    justifyContent: "space-between",
                    color: C.textTertiary,
                    fontSize: 11,
                    fontFamily: FONT_MONO,
                    fontVariantNumeric: "tabular-nums",
                }}>
                    <span>VERITY self-learning trail</span>
                    {pm && (
                        <span>
                            analyzed {pm.analyzed_count ?? 0}
                        </span>
                    )}
                </div>
            )}
        </div>
    )
}

PostmortemCard.defaultProps = {
    portfolioUrl:
        "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/portfolio.json",
    refreshIntervalSec: 300,
    compact: false,
}

addPropertyControls(PostmortemCard, {
    portfolioUrl: {
        type: ControlType.String,
        title: "Portfolio URL",
        defaultValue:
            "https://rte5guenhonw9fzn.public.blob.vercel-storage.com/portfolio.json",
    },
    refreshIntervalSec: {
        type: ControlType.Number,
        title: "Refresh (s)",
        defaultValue: 300,
        min: 60,
        max: 3600,
        step: 30,
    },
    compact: {
        type: ControlType.Boolean,
        title: "Compact (모바일)",
        defaultValue: false,
        enabledTitle: "Compact",
        disabledTitle: "Full",
    },
})
