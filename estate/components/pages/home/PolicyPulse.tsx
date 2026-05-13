import { addPropertyControls, ControlType } from "framer"
import React, { useState, useEffect, useMemo, useCallback } from "react"

/* ◆ ESTATE DESIGN TOKENS v1.1 (다크 + 골드 — 패밀리룩) ◆ */
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
const HERO_URL = `${ESTATE_API_BASE}/api/estate/hero-briefing`
const SHOCK_URL = `${ESTATE_API_BASE}/api/estate/policy-shock`
const CHANGE_URL = `${ESTATE_API_BASE}/api/estate/change-feed`

/* ──────────────────────────────────────────────────────────────
 * PolicyPulse — ESTATE 정책 통합 카드
 *
 * 통합 대상 (2026-05-12 audit 결과):
 *   HeroBriefing       → highlight section (24h 1건 + AI 한줄평 + LANDEX fallback)
 *   PolicyShockTimeline → timeline section (30~90d strip + by_day + stats)
 *   ChangeFeed         → list section (72h N=5 압축, 카테고리 chip)
 *
 * 통합 사유 (feedback_component_overlap_audit):
 *   3 컴포넌트가 같은 정책 데이터(data.go.kr 1371000) + 같은 도메인. 시간 깊이만 다름.
 *   분리는 사용자가 동시 보고 싶은 정보를 화면 3장으로 흩뿌림 → 밀도 ↓
 *   ([[feedback_estate_density_first]] 위배).
 *
 * 통합 후 책임:
 *   "지금 정책 시장이 어떻게 움직이는가" 단일 화면에 highlight + 시간축 + 최근 리스트 모두.
 *
 * 시간 깊이 매트릭스 (한 컴포넌트 안에서 자연 분할):
 *   highlight  → 24h 1건 (지금)
 *   timeline   → 30~90d 누적 (과거 깊이, in-component window selector)
 *   list       → 72h N=5 (최근 변동)
 *
 * Backend 분리 보존 (feedback_simple_front_monster_back):
 *   3 endpoint / 3 builder / 3 cron 그대로 유지. front 만 단일 카드로 묶음.
 *   monster back / simple front.
 * ────────────────────────────────────────────────────────────── */

/* ─ Hero (highlight) types ─ */
interface PolicyAI {
    model?: string
    confidence?: number
    tokens?: number
    fallback_used?: boolean
    generated_at?: string
}
interface Briefing {
    schema_version?: string
    generated_at: string
    policy: {
        id: string
        title: string
        source: string
        source_url?: string
        published_at?: string
        category?: string
        affected_regions?: string[]
    }
    narrative?: {
        headline: string | null
        body?: string
        ai?: PolicyAI
        fallback_reason?: string
    }
    operator_meta?: {
        policy_24h?: number
        freshness_minutes?: number
    }
}

/* ─ Shock (timeline) types ─ */
type Direction = "negative" | "positive" | "neutral"
type ShockCategory =
    | "regulation" | "tax" | "loan" | "redev"
    | "supply" | "rental" | "catalyst" | "anomaly"
interface ShockItem {
    id: string
    title: string
    published_at: string
    category: ShockCategory
    stage: number
    affected_regions: string[]
    impact_score: number
    direction: Direction
    source_url: string
}
interface ByDay {
    count: number
    max_impact: number
    net_direction_score: number
}
interface ShockPayload {
    fetched_at: string
    lookback_days: number
    items: ShockItem[]
    by_day: Record<string, ByDay>
    stats: {
        by_category: Partial<Record<ShockCategory, number>>
        by_direction: Record<Direction, number>
        max_impact: number
        mean_impact: number
    }
    total: number
}

/* ─ ChangeFeed (list) types ─ */
type ChangeCategory = "regulation" | "catalyst"
type Severity = "high" | "mid" | "low"
interface FeedItem {
    id: string
    category: ChangeCategory
    severity: Severity
    region_label: string
    title: string
    summary: string
    occurred_at: string
    source_name: string
    source_url: string
}
interface FeedPayload {
    fetched_at: string
    lookback_hours: number
    items: FeedItem[]
    category_counts: Partial<Record<ChangeCategory, number>>
    total: number
}

/* ─ in-component selector options ─ */
const SHOCK_LOOKBACK_OPTIONS = [
    { value: 7, label: "7일" },
    { value: 14, label: "14일" },
    { value: 30, label: "30일" },
    { value: 60, label: "60일" },
    { value: 90, label: "90일" },
]

type DirectionFilter = "all" | Direction
const DIR_FILTER_OPTIONS: { value: DirectionFilter; label: string }[] = [
    { value: "all", label: "전체" },
    { value: "negative", label: "규제" },
    { value: "positive", label: "호재" },
    { value: "neutral", label: "중립" },
]

const DIR_COLOR: Record<Direction, string> = {
    negative: C.danger,
    positive: C.success,
    neutral: C.textTertiary,
}

const CHANGE_CATEGORY_META: Record<ChangeCategory, { label: string; color: string }> = {
    regulation: { label: "규제", color: C.accent },
    catalyst: { label: "호재", color: C.warn },
}

const SEVERITY_COLOR: Record<Severity, string> = {
    high: C.danger,
    mid: C.warn,
    low: C.textTertiary,
}

const CHANGE_LIST_CAP = 5  // 압축 (단일 ChangeFeed 의 cap=10 → PolicyPulse 안에서는 5)

interface Props {
    apiUrlOverride?: string
}

export default function PolicyPulse(props: Props) {
    const base = (props.apiUrlOverride && props.apiUrlOverride.trim()) || ESTATE_API_BASE

    /* fetch state */
    const [hero, setHero] = useState<Briefing | null>(null)
    const [shock, setShock] = useState<ShockPayload | null>(null)
    const [change, setChange] = useState<FeedPayload | null>(null)
    const [heroErr, setHeroErr] = useState<string | null>(null)
    const [shockErr, setShockErr] = useState<string | null>(null)
    const [changeErr, setChangeErr] = useState<string | null>(null)
    const [loading, setLoading] = useState<boolean>(true)

    /* in-component selectors */
    const [shockLookback, setShockLookback] = useState<number>(30)
    const [shockDirection, setShockDirection] = useState<DirectionFilter>("all")
    const [changeCategory, setChangeCategory] = useState<"" | ChangeCategory>("")
    const [hoveredShock, setHoveredShock] = useState<ShockItem | null>(null)

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        setHeroErr(null)
        setShockErr(null)
        setChangeErr(null)

        const heroUrl = `${base}/api/estate/hero-briefing`
        const shockUrl = new URL(`${base}/api/estate/policy-shock`)
        shockUrl.searchParams.set("lookback_days", String(shockLookback))
        if (shockDirection !== "all") shockUrl.searchParams.set("directions", shockDirection)
        const changeUrl = new URL(`${base}/api/estate/change-feed`)
        changeUrl.searchParams.set("hours", "72")
        if (changeCategory) changeUrl.searchParams.set("categories", changeCategory)

        const opts: RequestInit = { cache: "no-store" }

        Promise.all([
            fetch(heroUrl, opts).then((r) => r.ok ? r.json() : Promise.reject(`hero ${r.status}`)).catch((e) => {
                if (!cancelled) setHeroErr(String(e))
                return null
            }),
            fetch(shockUrl.toString(), opts).then((r) => r.ok ? r.json() : Promise.reject(`shock ${r.status}`)).catch((e) => {
                if (!cancelled) setShockErr(String(e))
                return null
            }),
            fetch(changeUrl.toString(), opts).then((r) => r.ok ? r.json() : Promise.reject(`change ${r.status}`)).catch((e) => {
                if (!cancelled) setChangeErr(String(e))
                return null
            }),
        ]).then(([h, s, c]) => {
            if (cancelled) return
            if (h && h.generated_at && h.policy) setHero(h as Briefing)
            if (s && Array.isArray(s.items)) setShock(s as ShockPayload)
            if (c && Array.isArray(c.items)) setChange(c as FeedPayload)
            setLoading(false)
        })

        return () => {
            cancelled = true
        }
    }, [base, shockLookback, shockDirection, changeCategory])

    /* shock strip position 계산 */
    const stripPositions = useMemo(() => {
        if (!shock) return []
        const now = Date.now()
        const start = now - shockLookback * 24 * 60 * 60 * 1000
        const span = now - start
        return shock.items.map((it) => {
            const t = Date.parse(it.published_at)
            const pct = span > 0 ? Math.max(0, Math.min(100, ((t - start) / span) * 100)) : 50
            return { item: it, pct }
        })
    }, [shock, shockLookback])

    const dayKeys = useMemo(() => Object.keys(shock?.by_day || {}).sort(), [shock])
    const maxDailyImpact = useMemo(() => {
        let m = 0
        for (const k of dayKeys) {
            const v = shock?.by_day[k]?.max_impact || 0
            if (v > m) m = v
        }
        return m || 1
    }, [shock, dayKeys])

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
            {/* TOP HEADER */}
            <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 4 }}>
                <span style={{ fontSize: 11, letterSpacing: 1.2, color: C.accent, fontFamily: FONT_MONO }}>
                    POLICY PULSE
                </span>
                <span style={{ fontSize: 11, color: C.textTertiary }}>
                    {hero?.generated_at ? `갱신 ${hero.generated_at.slice(5, 16).replace("T", " ")}` : ""}
                </span>
            </div>
            <div style={{ fontSize: 16, fontWeight: 600, color: C.textPrimary, marginBottom: 14 }}>
                정책 통합 모니터
                <span style={{ fontSize: 12, fontWeight: 400, color: C.textSecondary, marginLeft: 8 }}>
                    24h 1건 · {shockLookback}d 누적 · 72h 변동
                </span>
            </div>

            {/* ─ SECTION 1: HIGHLIGHT (Hero) ─────────────────────────── */}
            <SectionLabel text="HIGHLIGHT · 24H" />
            {loading && !hero ? (
                <Skeleton height={64} mb={14} />
            ) : heroErr || !hero ? (
                <Placeholder text="하이라이트 일시 불가" mb={14} />
            ) : (
                <a
                    href={hero.policy.source_url || "#"}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                        display: "block",
                        textDecoration: "none",
                        background: C.bgInput,
                        border: `1px solid ${C.borderStrong}`,
                        borderRadius: R.md,
                        padding: "10px 12px",
                        marginBottom: 14,
                        color: C.textPrimary,
                    }}
                >
                    <div style={{ display: "flex", gap: 6, marginBottom: 4 }}>
                        <span
                            style={{
                                fontSize: 10,
                                color: C.accentBright,
                                fontFamily: FONT_MONO,
                                fontWeight: 600,
                            }}
                        >
                            {hero.policy.source}
                        </span>
                        {hero.policy.published_at && (
                            <span style={{ fontSize: 10, color: C.textTertiary, fontFamily: FONT_MONO }}>
                                · {hero.policy.published_at.slice(5, 16).replace("T", " ")}
                            </span>
                        )}
                    </div>
                    <div style={{ fontSize: 14, fontWeight: 500, color: C.textPrimary, marginBottom: 4 }}>
                        {hero.policy.title}
                    </div>
                    {hero.narrative?.headline ? (
                        <div style={{ fontSize: 12, color: C.accentBright, fontStyle: "italic" }}>
                            “{hero.narrative.headline}”
                        </div>
                    ) : hero.narrative?.fallback_reason ? (
                        <div style={{ fontSize: 11, color: C.textTertiary }}>
                            AI 한줄평 생략: {hero.narrative.fallback_reason}
                        </div>
                    ) : null}
                </a>
            )}

            {/* ─ SECTION 2: SHOCK TIMELINE ─────────────────────────── */}
            <SectionLabel
                text={`SHOCK · ${shockLookback}D`}
                right={
                    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                        <SelectorPill
                            value={String(shockLookback)}
                            options={SHOCK_LOOKBACK_OPTIONS.map((o) => ({ value: String(o.value), label: o.label }))}
                            onChange={(v) => setShockLookback(parseInt(v, 10))}
                        />
                        <div style={{ display: "flex", gap: 3 }}>
                            {DIR_FILTER_OPTIONS.map((opt) => (
                                <button
                                    key={opt.value}
                                    onClick={() => setShockDirection(opt.value)}
                                    style={{
                                        background: shockDirection === opt.value ? C.accentSoft : "transparent",
                                        color: shockDirection === opt.value ? C.accentBright : C.textSecondary,
                                        border: `1px solid ${shockDirection === opt.value ? C.accent : C.borderStrong}`,
                                        borderRadius: R.pill,
                                        padding: "2px 8px",
                                        fontSize: 10,
                                        fontFamily: FONT,
                                        cursor: "pointer",
                                    }}
                                >
                                    {opt.label}
                                </button>
                            ))}
                        </div>
                    </div>
                }
            />
            {loading && !shock ? (
                <Skeleton height={56} mb={6} />
            ) : shockErr || !shock ? (
                <Placeholder text="충격 타임라인 일시 불가" mb={14} />
            ) : shock.items.length === 0 ? (
                <Placeholder text={`${shockLookback}일 누적 정책 없음`} mb={14} />
            ) : (
                <>
                    <div
                        style={{
                            position: "relative",
                            height: 48,
                            background: C.bgElevated,
                            borderRadius: R.md,
                            marginBottom: 8,
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
                            const size = Math.max(6, Math.min(16, 6 + item.impact_score * 10))
                            const color = DIR_COLOR[item.direction]
                            return (
                                <a
                                    key={item.id}
                                    href={item.source_url || "#"}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    onMouseEnter={() => setHoveredShock(item)}
                                    onMouseLeave={() =>
                                        setHoveredShock((h) => (h?.id === item.id ? null : h))
                                    }
                                    style={{
                                        position: "absolute",
                                        left: `calc(${pct}% - ${size / 2}px + 8px)`,
                                        top: `calc(50% - ${size / 2}px)`,
                                        width: size,
                                        height: size,
                                        borderRadius: "50%",
                                        background: color,
                                        boxShadow:
                                            hoveredShock?.id === item.id ? `0 0 0 2px ${C.accent}` : "none",
                                        cursor: "pointer",
                                        transition: "box-shadow 150ms ease",
                                    }}
                                />
                            )
                        })}
                        <div
                            style={{
                                position: "absolute",
                                left: 8,
                                bottom: 2,
                                fontSize: 9,
                                fontFamily: FONT_MONO,
                                color: C.textTertiary,
                            }}
                        >
                            -{shockLookback}d
                        </div>
                        <div
                            style={{
                                position: "absolute",
                                right: 8,
                                bottom: 2,
                                fontSize: 9,
                                fontFamily: FONT_MONO,
                                color: C.textTertiary,
                            }}
                        >
                            now
                        </div>
                    </div>

                    {hoveredShock && (
                        <div
                            style={{
                                background: C.bgInput,
                                border: `1px solid ${C.borderStrong}`,
                                borderRadius: R.md,
                                padding: "8px 12px",
                                marginBottom: 8,
                                fontSize: 12,
                            }}
                        >
                            <div style={{ display: "flex", gap: 6, marginBottom: 2 }}>
                                <span
                                    style={{
                                        fontSize: 10,
                                        color: DIR_COLOR[hoveredShock.direction],
                                        fontWeight: 600,
                                        fontFamily: FONT_MONO,
                                    }}
                                >
                                    {hoveredShock.category}
                                </span>
                                <span style={{ fontSize: 10, color: C.textTertiary, fontFamily: FONT_MONO }}>
                                    stage {hoveredShock.stage} · impact {hoveredShock.impact_score.toFixed(2)}
                                </span>
                            </div>
                            <div style={{ color: C.textPrimary }}>{hoveredShock.title}</div>
                        </div>
                    )}

                    {dayKeys.length > 0 && (
                        <div style={{ marginBottom: 8 }}>
                            <div style={{ fontSize: 9, color: C.textTertiary, marginBottom: 2, fontFamily: FONT_MONO }}>
                                DAILY · MAX IMPACT
                            </div>
                            <div
                                style={{
                                    display: "flex",
                                    gap: 2,
                                    alignItems: "flex-end",
                                    height: 28,
                                    background: C.bgElevated,
                                    borderRadius: R.sm,
                                    padding: "0 4px",
                                }}
                            >
                                {dayKeys.map((k) => {
                                    const cell = shock!.by_day[k]
                                    const h = Math.max(2, (cell.max_impact / maxDailyImpact) * 24)
                                    const dirSign = cell.net_direction_score
                                    const c =
                                        dirSign < -0.1 ? C.danger : dirSign > 0.1 ? C.success : C.textTertiary
                                    return (
                                        <div
                                            key={k}
                                            title={`${k}: ${cell.count}건 max=${cell.max_impact.toFixed(2)}`}
                                            style={{
                                                flex: 1,
                                                height: h,
                                                background: c,
                                                borderRadius: 2,
                                                opacity: 0.7,
                                            }}
                                        />
                                    )
                                })}
                            </div>
                        </div>
                    )}

                    <div
                        style={{
                            display: "flex",
                            flexWrap: "wrap",
                            gap: 6,
                            fontSize: 10,
                            color: C.textSecondary,
                            marginBottom: 14,
                        }}
                    >
                        <StatChip label="규제" value={shock.stats.by_direction.negative} color={C.danger} />
                        <StatChip label="호재" value={shock.stats.by_direction.positive} color={C.success} />
                        <StatChip label="중립" value={shock.stats.by_direction.neutral} color={C.textTertiary} />
                        <StatChip
                            label="max"
                            value={shock.stats.max_impact.toFixed(2)}
                            color={C.accent}
                            mono
                        />
                        <StatChip
                            label="mean"
                            value={shock.stats.mean_impact.toFixed(2)}
                            color={C.accent}
                            mono
                        />
                    </div>
                </>
            )}

            {/* ─ SECTION 3: RECENT CHANGES ─────────────────────────── */}
            <SectionLabel
                text="RECENT · 72H"
                right={
                    <div style={{ display: "flex", gap: 3 }}>
                        {([
                            { value: "", label: "전체" },
                            { value: "regulation", label: "규제" },
                            { value: "catalyst", label: "호재" },
                        ] as const).map((opt) => (
                            <button
                                key={opt.value}
                                onClick={() => setChangeCategory(opt.value as any)}
                                style={{
                                    background:
                                        changeCategory === opt.value ? C.accentSoft : "transparent",
                                    color:
                                        changeCategory === opt.value ? C.accentBright : C.textSecondary,
                                    border: `1px solid ${changeCategory === opt.value ? C.accent : C.borderStrong}`,
                                    borderRadius: R.pill,
                                    padding: "2px 8px",
                                    fontSize: 10,
                                    cursor: "pointer",
                                }}
                            >
                                {opt.label}
                            </button>
                        ))}
                    </div>
                }
            />
            {loading && !change ? (
                <Skeleton height={120} />
            ) : changeErr || !change ? (
                <Placeholder text="변동 리스트 일시 불가" />
            ) : change.items.length === 0 ? (
                <Placeholder text="72시간 변동 없음" />
            ) : (
                <div>
                    {change.items.slice(0, CHANGE_LIST_CAP).map((it) => {
                        const meta = CHANGE_CATEGORY_META[it.category]
                        return (
                            <a
                                key={it.id}
                                href={it.source_url || "#"}
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{
                                    display: "block",
                                    padding: "6px 0",
                                    borderBottom: `1px solid ${C.borderStrong}`,
                                    textDecoration: "none",
                                    color: C.textPrimary,
                                }}
                            >
                                <div style={{ display: "flex", alignItems: "baseline", gap: 6, fontSize: 12 }}>
                                    <span
                                        style={{
                                            width: 6,
                                            height: 6,
                                            borderRadius: "50%",
                                            background: SEVERITY_COLOR[it.severity],
                                            display: "inline-block",
                                        }}
                                    />
                                    <span style={{ color: meta.color, fontSize: 10, minWidth: 32, fontFamily: FONT_MONO }}>
                                        {meta.label}
                                    </span>
                                    <span style={{ flex: 1, color: C.textPrimary }}>{it.title}</span>
                                    <span style={{ fontSize: 10, color: C.textTertiary, fontFamily: FONT_MONO }}>
                                        {it.region_label}
                                    </span>
                                </div>
                            </a>
                        )
                    })}
                </div>
            )}
        </div>
    )
}

function SectionLabel({ text, right }: { text: string; right?: React.ReactNode }) {
    return (
        <div
            style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 4,
            }}
        >
            <span style={{ fontSize: 10, letterSpacing: 1, color: C.accent, fontFamily: FONT_MONO }}>
                {text}
            </span>
            {right}
        </div>
    )
}

function StatChip({
    label, value, color, mono,
}: {
    label: string; value: number | string; color: string; mono?: boolean
}) {
    return (
        <span
            style={{
                display: "inline-flex",
                gap: 3,
                alignItems: "center",
                background: C.bgElevated,
                padding: "3px 7px",
                borderRadius: R.sm,
                border: `1px solid ${C.borderStrong}`,
            }}
        >
            <span style={{ color: C.textTertiary, fontSize: 9 }}>{label}</span>
            <span style={{ color, fontWeight: 600, fontFamily: mono ? FONT_MONO : FONT }}>{value}</span>
        </span>
    )
}

function SelectorPill({
    value, options, onChange,
}: {
    value: string
    options: { value: string; label: string }[]
    onChange: (v: string) => void
}) {
    return (
        <select
            value={value}
            onChange={(e) => onChange(e.target.value)}
            style={{
                background: C.bgElevated,
                border: `1px solid ${C.borderStrong}`,
                borderRadius: R.pill,
                color: C.accentBright,
                fontFamily: FONT,
                fontSize: 10,
                padding: "2px 8px",
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
    )
}

function Skeleton({ height, mb }: { height: number; mb?: number }) {
    return (
        <div
            style={{
                height,
                background: C.bgElevated,
                borderRadius: R.md,
                opacity: 0.5,
                marginBottom: mb ?? 0,
            }}
        />
    )
}

function Placeholder({ text, mb }: { text: string; mb?: number }) {
    return (
        <div
            style={{
                padding: 16,
                textAlign: "center",
                color: C.textTertiary,
                fontSize: 11,
                background: C.bgElevated,
                borderRadius: R.md,
                marginBottom: mb ?? 0,
            }}
        >
            {text}
        </div>
    )
}

addPropertyControls(PolicyPulse, {
    apiUrlOverride: {
        type: ControlType.String,
        title: "API base (override)",
        defaultValue: "",
        placeholder: ESTATE_API_BASE,
    },
})
