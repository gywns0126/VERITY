import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useMemo, useState } from "react"

/**
 * VERITY PostmortemCard — AI 오심 복기 카드 (자기 trail 자산)
 *
 * source: portfolio.json [postmortem] — daily_analysis_full cron 7일 trail
 * sink: MobileApp 임베드 (모바일 사용자 폰 알람 → 사이트 확인 정합)
 *       /admin 페이지는 BrainMonitor 의 postmortem 탭이 데스크탑 채널
 * RULE 6 정합: 자기 trail = LLM 못 가진 차별 자산
 */

interface Props {
    portfolioUrl: string
    refreshIntervalSec: number
    compact: boolean
}

const C = {
    bgCard: "#171820",
    bgElevated: "#22232B",
    border: "rgba(255,255,255,0.06)",
    borderStrong: "rgba(255,255,255,0.10)",
    textPrimary: "#F2F3F5",
    textSecondary: "#A8ABB2",
    textTertiary: "#6B6E76",
    accent: "#B5FF17",
    accentSoft: "rgba(181,255,23,0.12)",
    info: "#5BA9FF",
    success: "#22C55E",
    warn: "#F59E0B",
    danger: "#EF4444",
    dangerSoft: "rgba(239,68,68,0.12)",
} as const

const FONT = `-apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", "Pretendard", sans-serif`

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
    const color = r >= 0 ? C.success : C.danger
    return { text: `${sign}${r.toFixed(2)}%`, color }
}

function gradeColor(g?: string): string {
    if (!g) return C.textTertiary
    if (g === "STRONG_BUY" || g === "BUY") return C.success
    if (g === "WATCH") return C.info
    if (g === "CAUTION") return C.warn
    if (g === "AVOID") return C.danger
    return C.textSecondary
}

function FailureRow({ f, compact }: { f: Failure; compact: boolean }) {
    const ret = formatReturn(f.actual_return)
    const flagsLimit = compact ? 2 : 3
    const flags = (f.risk_flags || []).slice(0, flagsLimit)
    return (
        <div
            style={{
                background: C.bgElevated,
                border: `1px solid ${C.border}`,
                borderRadius: 8,
                padding: compact ? "10px 12px" : "14px 16px",
                display: "flex",
                flexDirection: "column",
                gap: compact ? 6 : 8,
            }}
        >
            <div
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "baseline",
                    gap: 12,
                    flexWrap: "wrap",
                }}
            >
                <div style={{ display: "flex", gap: 8, alignItems: "baseline", minWidth: 0 }}>
                    <span
                        style={{
                            color: C.textPrimary,
                            fontSize: compact ? 14 : 15,
                            fontWeight: 600,
                            letterSpacing: "-0.01em",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                        }}
                    >
                        {f.name || f.ticker || "—"}
                    </span>
                    {f.ticker && !compact && (
                        <span style={{ color: C.textTertiary, fontSize: 12 }}>
                            {f.ticker}
                        </span>
                    )}
                </div>
                <div style={{ display: "flex", gap: 6, alignItems: "baseline" }}>
                    <span
                        style={{
                            color: gradeColor(f.original_rec),
                            fontSize: 11,
                            fontWeight: 600,
                            textTransform: "uppercase",
                            letterSpacing: "0.04em",
                        }}
                    >
                        {f.original_rec || "—"}
                    </span>
                    <span style={{ color: C.textTertiary, fontSize: 11 }}>→</span>
                    <span style={{ color: ret.color, fontSize: 13, fontWeight: 600 }}>
                        {ret.text}
                    </span>
                </div>
            </div>

            {f.lesson && (
                <div
                    style={{
                        color: C.textSecondary,
                        fontSize: compact ? 12 : 13,
                        lineHeight: 1.5,
                    }}
                >
                    💬 {f.lesson}
                </div>
            )}

            {flags.length > 0 && !compact && (
                <div
                    style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: 6,
                        marginTop: 2,
                    }}
                >
                    {flags.map((flag, i) => (
                        <span
                            key={i}
                            style={{
                                fontSize: 11,
                                color: C.warn,
                                background: "rgba(245,158,11,0.10)",
                                border: `1px solid rgba(245,158,11,0.25)`,
                                padding: "2px 8px",
                                borderRadius: 4,
                            }}
                        >
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

    const pad = compact ? 14 : 20
    const radius = compact ? 10 : 12
    const gap = compact ? 12 : 16

    return (
        <div
            style={{
                width: "100%",
                background: C.bgCard,
                border: `1px solid ${C.borderStrong}`,
                borderRadius: radius,
                padding: pad,
                fontFamily: FONT,
                color: C.textPrimary,
                display: "flex",
                flexDirection: "column",
                gap,
                boxSizing: "border-box",
            }}
        >
            <div
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "baseline",
                    flexWrap: "wrap",
                    gap: 8,
                }}
            >
                <div style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
                    <span
                        style={{
                            color: C.accent,
                            fontSize: 11,
                            fontWeight: 600,
                            letterSpacing: "0.08em",
                            textTransform: "uppercase",
                        }}
                    >
                        🔍 AI 오심 복기
                    </span>
                    {pm?.period && (
                        <span style={{ color: C.textTertiary, fontSize: 11 }}>
                            {pm.period}
                        </span>
                    )}
                </div>
                {genAt && (
                    <span style={{ color: C.textTertiary, fontSize: 11 }}>
                        {genAt}
                    </span>
                )}
            </div>

            {loading && (
                <div style={{ color: C.textTertiary, fontSize: 13 }}>로딩 중…</div>
            )}
            {err && !loading && (
                <div style={{ color: C.danger, fontSize: 13 }}>오류: {err}</div>
            )}

            {!loading && !err && !hasFailures && (
                <div
                    style={{
                        color: C.textSecondary,
                        fontSize: 13,
                        padding: "20px 0",
                        textAlign: "center",
                    }}
                >
                    최근 7일 유의미한 오심 없음
                </div>
            )}

            {!loading && !err && hasFailures && pm?.summary && (
                <div
                    style={{
                        color: C.textPrimary,
                        fontSize: 13,
                        fontWeight: 500,
                        padding: "10px 12px",
                        background: C.accentSoft,
                        borderRadius: 6,
                        borderLeft: `3px solid ${C.accent}`,
                    }}
                >
                    {pm.summary}
                </div>
            )}

            {!loading && !err && hasFailures && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {failures.map((f, i) => (
                        <FailureRow key={`${f.ticker}-${i}`} f={f} compact={compact} />
                    ))}
                </div>
            )}

            {!loading && !err && hasFailures && pm?.lesson && !compact && (
                <div
                    style={{
                        color: C.textPrimary,
                        fontSize: 13,
                        lineHeight: 1.55,
                        padding: "12px 14px",
                        background: C.bgElevated,
                        borderRadius: 6,
                        border: `1px solid ${C.border}`,
                    }}
                >
                    <div
                        style={{
                            color: C.textTertiary,
                            fontSize: 10,
                            fontWeight: 600,
                            letterSpacing: "0.08em",
                            textTransform: "uppercase",
                            marginBottom: 6,
                        }}
                    >
                        오늘의 교훈
                    </div>
                    {pm.lesson}
                </div>
            )}

            {!loading && !err && hasFailures && pm?.system_suggestion && (
                <div
                    style={{
                        color: C.textPrimary,
                        fontSize: compact ? 12 : 13,
                        lineHeight: 1.55,
                        padding: compact ? "10px 12px" : "12px 14px",
                        background: C.dangerSoft,
                        borderRadius: 6,
                        border: `1px solid rgba(239,68,68,0.25)`,
                        borderLeft: `3px solid ${C.danger}`,
                    }}
                >
                    <div
                        style={{
                            color: C.danger,
                            fontSize: 10,
                            fontWeight: 700,
                            letterSpacing: "0.08em",
                            textTransform: "uppercase",
                            marginBottom: 6,
                        }}
                    >
                        ⚙ 추천 시스템 조치
                    </div>
                    {pm.system_suggestion}
                </div>
            )}

            <div
                style={{
                    display: "flex",
                    justifyContent: "space-between",
                    color: C.textTertiary,
                    fontSize: 10,
                    paddingTop: 6,
                    borderTop: `1px solid ${C.border}`,
                }}
            >
                <span>VERITY 자기 학습 trail</span>
                {pm && (
                    <span>
                        analyzed {pm.analyzed_count ?? 0}
                    </span>
                )}
            </div>
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
