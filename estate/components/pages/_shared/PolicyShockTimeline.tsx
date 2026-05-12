import { addPropertyControls, ControlType } from "framer"
import React, { useState, useEffect, useMemo, useCallback } from "react"

/* ──────────────────────────────────────────────────────────────
 * ◆ ESTATE DESIGN TOKENS v1.1 ◆ (다크 + 골드 — 패밀리룩 정합)
 * HeroBriefing/ChangeFeed/SystemPulse 와 동일 토큰. 직접 hex 박지 말고 C/R 만.
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0A0908",
    bgCard: "#0F0D0A",
    bgElevated: "#16130E",
    bgInput: "#1F1B14",
    border: "transparent",
    borderStrong: "#3A3024",
    textPrimary: "#F2EFE9",
    textSecondary: "#A8A299",
    textTertiary: "#6B665E",
    textDisabled: "#4A453E",
    accent: "#B8864D",
    accentBright: "#D4A26B",
    accentSoft: "rgba(184,134,77,0.15)",
    success: "#22C55E",
    warn: "#F59E0B",
    danger: "#EF4444",
    info: "#5BA9FF",
}
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const R = { sm: 6, md: 10, lg: 14, pill: 999 }
/* ◆ TOKENS END ◆ */

const ESTATE_API_BASE = "https://project-yw131.vercel.app"
const ESTATE_POLICY_SHOCK_URL = `${ESTATE_API_BASE}/api/estate/policy-shock`

/* ──────────────────────────────────────────────────────────────
 * PolicyShockTimeline — ESTATE Tier 2 / E
 *
 * ChangeFeed (72h N=10 리스트) 와 직교: 30/90일 누적 시간축 + 충격 magnitude.
 * 데이터: estate_policy_archive_builder (jsonl) + estate_policy_shock_builder
 *        → /api/estate/policy-shock read-through.
 * 산식: impact_score = stage×0.5 + category_weight×0.3 + region_breadth×0.2
 *      direction = negative(regulation/tax/loan) | positive(catalyst/...) | neutral
 * ────────────────────────────────────────────────────────────── */

type Direction = "negative" | "positive" | "neutral"
type Category =
    | "regulation" | "tax" | "loan" | "redev"
    | "supply" | "rental" | "catalyst" | "anomaly"

interface ShockItem {
    id: string
    title: string
    source_name: string
    source_url: string
    published_at: string
    category: Category
    stage: number
    affected_regions: string[]
    impact_score: number  // 0~1
    direction: Direction
}

interface ByDay {
    count: number
    max_impact: number
    net_direction_score: number
}

interface ShockPayload {
    schema_version?: string
    fetched_at: string
    namespace: string
    scenario?: "live" | "empty" | "error"
    lookback_days: number
    items: ShockItem[]
    by_day: Record<string, ByDay>
    stats: {
        by_category: Partial<Record<Category, number>>
        by_direction: Record<Direction, number>
        max_impact: number
        mean_impact: number
    }
    total: number
    error?: string
}

const CATEGORY_LABEL: Record<Category, string> = {
    regulation: "규제",
    tax: "세제",
    loan: "대출",
    redev: "재건축",
    supply: "공급",
    rental: "임대",
    catalyst: "호재",
    anomaly: "이슈",
}

const DIRECTION_COLOR: Record<Direction, string> = {
    negative: C.danger,
    positive: C.success,
    neutral: C.textTertiary,
}

const LOOKBACK_OPTIONS: { value: number; label: string }[] = [
    { value: 7, label: "7일" },
    { value: 14, label: "14일" },
    { value: 30, label: "30일" },
    { value: 60, label: "60일" },
    { value: 90, label: "90일" },
]

type DirectionFilter = "all" | Direction

const DIRECTION_FILTER_OPTIONS: { value: DirectionFilter; label: string }[] = [
    { value: "all", label: "전체" },
    { value: "negative", label: "규제" },
    { value: "positive", label: "호재" },
    { value: "neutral", label: "중립" },
]

interface Props {
    /** Framer publish 환경에서 source URL 오버라이드 (테스트). 평소 빈 문자열. */
    apiUrlOverride?: string
}

export default function PolicyShockTimeline(props: Props) {
    const sourceBase = (props.apiUrlOverride && props.apiUrlOverride.trim()) || ESTATE_POLICY_SHOCK_URL

    const [lookback, setLookback] = useState<number>(30)
    const [direction, setDirection] = useState<DirectionFilter>("all")
    const [payload, setPayload] = useState<ShockPayload | null>(null)
    const [loading, setLoading] = useState<boolean>(true)
    const [error, setError] = useState<string | null>(null)
    const [hovered, setHovered] = useState<ShockItem | null>(null)

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        setError(null)
        const url = new URL(sourceBase)
        url.searchParams.set("lookback_days", String(lookback))
        if (direction !== "all") url.searchParams.set("directions", direction)

        fetch(url.toString(), { cache: "no-store" })
            .then(async (r) => {
                if (!r.ok) throw new Error(`upstream ${r.status}`)
                return (await r.json()) as ShockPayload
            })
            .then((data) => {
                if (cancelled) return
                setPayload(data)
                setLoading(false)
            })
            .catch((e) => {
                if (cancelled) return
                setError(String(e?.message || e))
                setPayload(null)
                setLoading(false)
            })

        return () => {
            cancelled = true
        }
    }, [sourceBase, lookback, direction])

    const items = payload?.items || []
    const byDay = payload?.by_day || {}
    const stats = payload?.stats

    /* 시간축 strip 위치 산출 (lookback 윈도우 내 백분율) */
    const stripPositions = useMemo(() => {
        const now = Date.now()
        const start = now - lookback * 24 * 60 * 60 * 1000
        const span = now - start
        return items.map((it) => {
            const t = Date.parse(it.published_at)
            const pct = span > 0 ? Math.max(0, Math.min(100, ((t - start) / span) * 100)) : 50
            return { item: it, pct }
        })
    }, [items, lookback])

    const dayKeys = useMemo(() => Object.keys(byDay).sort(), [byDay])
    const maxDailyImpact = useMemo(() => {
        let m = 0
        for (const k of dayKeys) {
            const v = byDay[k]?.max_impact || 0
            if (v > m) m = v
        }
        return m || 1
    }, [byDay, dayKeys])

    return (
        <div
            style={{
                width: "100%",
                background: C.bgCard,
                borderRadius: R.lg,
                padding: 16,
                fontFamily: FONT,
                color: C.textPrimary,
                boxSizing: "border-box",
                border: `1px solid ${C.borderStrong}`,
            }}
        >
            {/* HEADER */}
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 4 }}>
                <span style={{ fontSize: 11, letterSpacing: 1.2, color: C.accent, fontFamily: FONT_MONO }}>
                    POLICY · {lookback}D
                </span>
                <span style={{ fontSize: 11, color: C.textTertiary }}>
                    {payload?.fetched_at ? `갱신 ${payload.fetched_at.slice(5, 16).replace("T", " ")}` : ""}
                </span>
            </div>
            <div style={{ fontSize: 16, fontWeight: 600, color: C.textPrimary, marginBottom: 12 }}>
                정책 충격 타임라인
                <span style={{ fontSize: 12, fontWeight: 400, color: C.textSecondary, marginLeft: 8 }}>
                    {loading ? "—" : `${items.length}건`}
                </span>
            </div>

            {/* FILTERS (in-component selector — feedback_in_component_interactivity) */}
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
                <SelectorPill
                    label="기간"
                    value={String(lookback)}
                    options={LOOKBACK_OPTIONS.map((o) => ({ value: String(o.value), label: o.label }))}
                    onChange={(v) => setLookback(parseInt(v, 10))}
                />
                <div style={{ display: "flex", gap: 4 }}>
                    {DIRECTION_FILTER_OPTIONS.map((opt) => (
                        <button
                            key={opt.value}
                            onClick={() => setDirection(opt.value)}
                            style={{
                                background: direction === opt.value ? C.accentSoft : "transparent",
                                color: direction === opt.value ? C.accentBright : C.textSecondary,
                                border: `1px solid ${direction === opt.value ? C.accent : C.borderStrong}`,
                                borderRadius: R.pill,
                                padding: "4px 10px",
                                fontSize: 11,
                                fontFamily: FONT,
                                cursor: "pointer",
                                transition: "all 200ms ease",
                            }}
                        >
                            {opt.label}
                        </button>
                    ))}
                </div>
            </div>

            {/* STATE */}
            {loading && <SkeletonStrip />}
            {!loading && error && (
                <div style={{ padding: 24, textAlign: "center", color: C.textTertiary, fontSize: 12 }}>
                    충격 타임라인 일시 불가
                </div>
            )}
            {!loading && !error && items.length === 0 && (
                <div style={{ padding: 24, textAlign: "center", color: C.textTertiary, fontSize: 12 }}>
                    {lookback}일간 적재된 정책 없음
                </div>
            )}

            {!loading && !error && items.length > 0 && (
                <>
                    {/* STRIP — 시간축 + dot */}
                    <div
                        style={{
                            position: "relative",
                            height: 56,
                            background: C.bgElevated,
                            borderRadius: R.md,
                            marginBottom: 12,
                            padding: "0 8px",
                        }}
                    >
                        <div
                            style={{
                                position: "absolute",
                                left: 8,
                                right: 8,
                                top: "50%",
                                height: 1,
                                background: C.borderStrong,
                            }}
                        />
                        {stripPositions.map(({ item, pct }) => {
                            const size = Math.max(6, Math.min(18, 6 + item.impact_score * 12))
                            const color = DIRECTION_COLOR[item.direction]
                            return (
                                <a
                                    key={item.id}
                                    href={item.source_url || "#"}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    onMouseEnter={() => setHovered(item)}
                                    onMouseLeave={() => setHovered((h) => (h?.id === item.id ? null : h))}
                                    style={{
                                        position: "absolute",
                                        left: `calc(${pct}% - ${size / 2}px + 8px)`,
                                        top: `calc(50% - ${size / 2}px)`,
                                        width: size,
                                        height: size,
                                        borderRadius: "50%",
                                        background: color,
                                        boxShadow: hovered?.id === item.id ? `0 0 0 2px ${C.accent}` : "none",
                                        cursor: "pointer",
                                        transition: "box-shadow 150ms ease",
                                    }}
                                />
                            )
                        })}
                        {/* x축 라벨 (양 끝) */}
                        <div
                            style={{
                                position: "absolute",
                                left: 8,
                                bottom: 4,
                                fontSize: 9,
                                fontFamily: FONT_MONO,
                                color: C.textTertiary,
                            }}
                        >
                            -{lookback}d
                        </div>
                        <div
                            style={{
                                position: "absolute",
                                right: 8,
                                bottom: 4,
                                fontSize: 9,
                                fontFamily: FONT_MONO,
                                color: C.textTertiary,
                            }}
                        >
                            now
                        </div>
                    </div>

                    {/* HOVER DETAIL */}
                    {hovered && <HoverDetail item={hovered} />}

                    {/* BY_DAY 막대 */}
                    {dayKeys.length > 0 && (
                        <div style={{ marginBottom: 12 }}>
                            <div style={{ fontSize: 10, color: C.textTertiary, marginBottom: 4, fontFamily: FONT_MONO }}>
                                DAILY · MAX IMPACT
                            </div>
                            <div
                                style={{
                                    display: "flex",
                                    gap: 2,
                                    alignItems: "flex-end",
                                    height: 36,
                                    background: C.bgElevated,
                                    borderRadius: R.sm,
                                    padding: "0 4px",
                                }}
                            >
                                {dayKeys.map((k) => {
                                    const cell = byDay[k]
                                    const h = Math.max(2, (cell.max_impact / maxDailyImpact) * 32)
                                    const dirSign = cell.net_direction_score
                                    const c =
                                        dirSign < -0.1 ? C.danger : dirSign > 0.1 ? C.success : C.textTertiary
                                    return (
                                        <div
                                            key={k}
                                            title={`${k}: ${cell.count}건 max=${cell.max_impact.toFixed(2)}`}
                                            style={{ flex: 1, height: h, background: c, borderRadius: 2, opacity: 0.7 }}
                                        />
                                    )
                                })}
                            </div>
                        </div>
                    )}

                    {/* STATS */}
                    {stats && (
                        <div
                            style={{
                                display: "flex",
                                flexWrap: "wrap",
                                gap: 8,
                                fontSize: 11,
                                color: C.textSecondary,
                            }}
                        >
                            <StatChip
                                label="규제"
                                value={stats.by_direction.negative}
                                color={C.danger}
                            />
                            <StatChip
                                label="호재"
                                value={stats.by_direction.positive}
                                color={C.success}
                            />
                            <StatChip
                                label="중립"
                                value={stats.by_direction.neutral}
                                color={C.textTertiary}
                            />
                            <StatChip
                                label="최대 충격"
                                value={stats.max_impact.toFixed(2)}
                                color={C.accent}
                                mono
                            />
                            <StatChip
                                label="평균"
                                value={stats.mean_impact.toFixed(2)}
                                color={C.accent}
                                mono
                            />
                        </div>
                    )}
                </>
            )}
        </div>
    )
}

function HoverDetail({ item }: { item: ShockItem }) {
    return (
        <div
            style={{
                background: C.bgInput,
                border: `1px solid ${C.borderStrong}`,
                borderRadius: R.md,
                padding: "10px 12px",
                marginBottom: 12,
                fontSize: 12,
                lineHeight: 1.5,
            }}
        >
            <div style={{ display: "flex", gap: 6, marginBottom: 4 }}>
                <span
                    style={{
                        fontSize: 10,
                        color: DIRECTION_COLOR[item.direction],
                        fontFamily: FONT_MONO,
                        fontWeight: 600,
                    }}
                >
                    {CATEGORY_LABEL[item.category]}
                </span>
                <span style={{ fontSize: 10, color: C.textTertiary, fontFamily: FONT_MONO }}>
                    stage {item.stage} · impact {item.impact_score.toFixed(2)}
                </span>
            </div>
            <div style={{ color: C.textPrimary, fontWeight: 500 }}>{item.title}</div>
            <div style={{ color: C.textTertiary, fontSize: 10, marginTop: 4 }}>
                {item.source_name} · {item.published_at.slice(0, 10)}
                {item.affected_regions.length > 0 && ` · ${item.affected_regions.slice(0, 3).join(", ")}`}
            </div>
        </div>
    )
}

function StatChip({ label, value, color, mono }: { label: string; value: number | string; color: string; mono?: boolean }) {
    return (
        <span
            style={{
                display: "inline-flex",
                gap: 4,
                alignItems: "center",
                background: C.bgElevated,
                padding: "4px 8px",
                borderRadius: R.sm,
                border: `1px solid ${C.borderStrong}`,
            }}
        >
            <span style={{ color: C.textTertiary, fontSize: 10 }}>{label}</span>
            <span style={{ color, fontWeight: 600, fontFamily: mono ? FONT_MONO : FONT }}>{value}</span>
        </span>
    )
}

function SelectorPill({
    label,
    value,
    options,
    onChange,
}: {
    label: string
    value: string
    options: { value: string; label: string }[]
    onChange: (v: string) => void
}) {
    return (
        <label
            style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                background: C.bgElevated,
                border: `1px solid ${C.borderStrong}`,
                borderRadius: R.pill,
                padding: "3px 10px",
                fontSize: 11,
                color: C.textSecondary,
            }}
        >
            <span style={{ color: C.textTertiary }}>{label}</span>
            <select
                value={value}
                onChange={(e) => onChange(e.target.value)}
                style={{
                    background: "transparent",
                    border: "none",
                    color: C.accentBright,
                    fontFamily: FONT,
                    fontSize: 11,
                    cursor: "pointer",
                    outline: "none",
                }}
            >
                {options.map((o) => (
                    <option key={o.value} value={o.value} style={{ background: C.bgCard, color: C.textPrimary }}>
                        {o.label}
                    </option>
                ))}
            </select>
        </label>
    )
}

function SkeletonStrip() {
    return (
        <div
            style={{
                height: 56,
                background: C.bgElevated,
                borderRadius: R.md,
                marginBottom: 12,
                opacity: 0.5,
                animation: "estatePolicyShockPulse 1.4s ease-in-out infinite",
            }}
        />
    )
}

addPropertyControls(PolicyShockTimeline, {
    apiUrlOverride: {
        type: ControlType.String,
        title: "API URL (override)",
        defaultValue: "",
        placeholder: ESTATE_POLICY_SHOCK_URL,
    },
})
