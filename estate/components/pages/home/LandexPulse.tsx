import { addPropertyControls, ControlType } from "framer"
import React, { useState, useEffect, useCallback, useRef } from "react"

/* ──────────────────────────────────────────────────────────────
 * ◆ ESTATE DESIGN TOKENS v1.1 ◆ (다크 + 골드 emphasis — 옵션 A 패밀리룩)
 * v1.0 (다크 기본 — LandexMapDashboard 묵시 정본) → v1.1 (P3-2.7 다크 + 골드
 * emphasis 진화). HeroBriefing/SystemPulse 와 동일 토큰.
 *
 * grade*/stage* hex 인라인 (LandexMapDashboard v1.0 정본 hex 그대로) — 옵션 A
 * 채택. v1.1 토큰 정의 무수정 ([C]6 미발동), 시각 일관성 보장.
 * ────────────────────────────────────────────────────────────── */
const C = {
    bgPage: "#0A0908",
    bgCard: "#0F0D0A",
    bgElevated: "#16130E",
    bgInput: "#1F1B14",
    border: "#26221C",
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
const FONT_SERIF = "'Noto Serif KR', 'Times New Roman', serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const R = { sm: 6, md: 10, lg: 14, pill: 999 }

// grade*/stage* hex 인라인 (LandexMapDashboard 정본)
const GRADE_COLORS: Record<string, string> = {
    HOT: "#EF4444",
    WARM: "#F59E0B",
    NEUT: "#A8ABB2",
    COOL: "#5BA9FF",
    AVOID: "#6B6E76",
}
const STAGE_COLORS: Record<number, string> = {
    0: "transparent",
    1: "#FFD600",
    2: "#F59E0B",
    3: "#EF4444",
    4: "#9B59B6",
}
/* ◆ TOKENS END ◆ */

const ESTATE_API_BASE = "https://project-yw131.vercel.app"
const ESTATE_LANDEX_PULSE_URL = `${ESTATE_API_BASE}/api/estate/landex-pulse`


/* ──────────────────────────────────────────────────────────────
 * ◆ TRIGGER 매핑 ◆
 * ────────────────────────────────────────────────────────────── */
type LandexTrigger = "normal" | "regime_shift"

const REGIME_SHIFT_THRESHOLD = 3

const TRIGGER_HEADERS: Record<LandexTrigger, {
    title: string; subtitle: (n: number) => string; sectionLabel: string
}> = {
    normal: {
        title: "시장 정상",
        subtitle: () => "regime 안정 — 25구 변화 임계 미만",
        sectionLabel: "REGIME · STABLE",
    },
    regime_shift: {
        title: "시장 regime 변동",
        subtitle: (n) => `${n}개 구 등급 변화 — 운영자 검토 필요`,
        sectionLabel: "REGIME · SHIFT DETECTED",
    },
}


/* ──────────────────────────────────────────────────────────────
 * ◆ TERMS 인라인 (estate/data/terms.json 정합) ◆
 * Framer self-contained 컨벤션 (T31) — 외부 import 0.
 * P4: terms.json 별도 fetch 또는 동적 import 검토.
 * ────────────────────────────────────────────────────────────── */
interface Term {
    label: string
    category?: string
    definition: string
    stages?: Record<string, string>
    values?: Record<string, string>
    l3?: boolean
}
const TERMS: Record<string, Term> = {
    LANDEX: { label: "LANDEX", category: "metric", definition: "ESTATE 자체 종합 점수 (0~100). V/D/S/C/R 5개 sub-score 의 가중 평균. 가중치는 preset 에 따라 동적." },
    V_SCORE: { label: "V Score (가치)", category: "metric", definition: "Value — 가치 점수 (0~100). 자산 가격 대비 내재 가치 평가." },
    D_SCORE: { label: "D Score (수요)", category: "metric", definition: "Demand — 수요 점수 (0~100). 거래량 + 매물 회전율 + 임차 수요." },
    S_SCORE: { label: "S Score (공급)", category: "metric", definition: "Supply — 공급 점수 (0~100). 신규 분양 + 미분양 호수 + 입주 물량." },
    C_SCORE: { label: "C Score (입지)", category: "metric", definition: "Convenience — 입지 점수 (0~100). 교통 접근성 + 학군 + 생활 인프라." },
    R_SCORE: { label: "R Score (위험)", category: "metric", definition: "Risk — 위험 점수 (0~100). 정책/금리/재건축 리스크 가중치." },
    CATALYST_SCORE: { label: "Catalyst Score", category: "metric", definition: "단기 변화 트리거 점수 (0~100). 정책 발표 + 개발 호재 + 공급 변화 가중." },
    GEI_STAGE: {
        label: "GEI Stage", category: "internal", l3: true,
        definition: "시장 과열 단계 지표 (S0~S4). 매물 회전율 + 임차료 상승 + 거래량 가속도 임계.",
        stages: { S0: "안정 (0~19)", S1: "주의 (20~39)", S2: "경계 (40~59)", S3: "과열 (60~79)", S4: "위험 (80~100)" },
    },
    GRADE_HOT: { label: "HOT 등급", category: "grade", definition: "최상위 등급 (LANDEX >= 80). 모든 5축이 평균 이상 + 강한 모멘텀." },
    GRADE_WARM: { label: "WARM 등급", category: "grade", definition: "상위 등급 (LANDEX 65~79). 안정적 우위, 일부 축 강점." },
    GRADE_NEUT: { label: "NEUT 등급", category: "grade", definition: "중립 등급 (LANDEX 50~64). 시장 평균권." },
    GRADE_COOL: { label: "COOL 등급", category: "grade", definition: "하위 등급 (LANDEX 35~49). 관망 권역, 1~2개 축 약점." },
    GRADE_AVOID: { label: "AVOID 등급", category: "grade", definition: "회피 등급 (LANDEX < 35). 다수 축 평균 이하." },
    REGIME: {
        label: "Regime", category: "metric",
        definition: "시장 regime — 25구 평균 LANDEX 추세 분류.",
        values: { bull: "강세 (avg >= 60)", bear: "약세 (avg <= 45)", neutral: "중립 (45 < avg < 60)" },
    },
    TIER10: { label: "Tier 10", category: "grade", definition: "10단계 세분 등급 (A+/A/.../D). LANDEX 점수 10분위." },
    FEATURE_CONTRIB: {
        label: "피처 기여도", category: "internal", l3: true,
        definition: "LANDEX 점수에 영향을 미친 요인별 가중치. 부호(+/-) + 절대값(weight). 외부 공유 금지 — 모델 내부 자산.",
    },
    WEEKLY_PRICE_INDEX: { label: "주간 매매가격지수", category: "data_source", definition: "R-ONE 주간 발표 매매가격지수 (목요일 발표). 자치구별 시계열." },
    MONTHLY_UNSOLD: { label: "월간 미분양", category: "data_source", definition: "R-ONE 월간 미분양현황. 자치구별 미분양 호수 누적 추이." },
    MoM: { label: "Month over Month", category: "time", definition: "전월 대비 변화율. % 단위." },
    WoW: { label: "Week over Week", category: "time", definition: "전주 대비 변화율. % 단위." },
}


/* ──────────────────────────────────────────────────────────────
 * ◆ Types ◆
 * ────────────────────────────────────────────────────────────── */
type GradeLabel = "HOT" | "WARM" | "NEUT" | "COOL" | "AVOID"

interface FeatureContrib { feature: string; weight: number; sign: "+" | "-" }
interface SeriesPoint { date: string; value: number }
interface GuDetail {
    radar: { v: number; d: number; s: number; c: number; r: number }
    feature_contributions: FeatureContrib[]
    timeseries: {
        weekly_price_index: SeriesPoint[]
        monthly_unsold: SeriesPoint[]
    }
    strengths: string[]
    weaknesses: string[]
}
interface Gu {
    gu_name: string
    landex: number
    grade: GradeLabel
    gei: number
    stage: 0 | 1 | 2 | 3 | 4
    v_score: number
    d_score: number
    s_score: number
    c_score: number
    r_score: number
    catalyst_score: number
    detail: GuDetail
}
interface PulseData {
    schema_version?: string
    generated_at: string
    scenario?: string
    trigger: { type: LandexTrigger }
    meta: {
        primary: {
            current_regime: "bull" | "bear" | "neutral"
            top_gainer: { gu_name: string; change_pct: number }
            top_loser: { gu_name: string; change_pct: number }
            last_shift_at: string | null
        }
        detail: {
            degraded_count: number
            gained_count: number
            gei_s4_count: number
            avg_landex: number
            data_freshness_min: number
        }
    }
    gus: Gu[]
}

type FetchState =
    | { status: "loading" }
    | { status: "error"; reason: string }
    | { status: "ok"; data: PulseData; fetchedAt: number }


/* ──────────────────────────────────────────────────────────────
 * ◆ Helpers ◆
 * ────────────────────────────────────────────────────────────── */
function formatFreshness(minutes: number | null | undefined): string {
    if (minutes == null) return "—"
    if (minutes < 1) return "< 1min"
    if (minutes < 60) return `${minutes}min ago`
    if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`
    return `${Math.floor(minutes / 1440)}d ago`
}

function minutesSince(iso: string | null | undefined, now: number): number | null {
    if (!iso) return null
    try {
        const t = new Date(iso).getTime()
        if (isNaN(t)) return null
        return Math.floor((now - t) / 60000)
    } catch { return null }
}

function inferTrigger(data: PulseData): LandexTrigger {
    const total = data.meta.detail.degraded_count + data.meta.detail.gained_count
    return total >= REGIME_SHIFT_THRESHOLD ? "regime_shift" : "normal"
}


/* ──────────────────────────────────────────────────────────────
 * ◆ Main Component ◆
 * ────────────────────────────────────────────────────────────── */
interface Props {
    jsonUrl: string
    scenario: "normal" | "regime_shift"
    showAdminMeta: boolean
}

export default function LandexPulse({
    jsonUrl,
    scenario = "normal",
    showAdminMeta = true,
}: Props) {
    const [state, setState] = useState<FetchState>({ status: "loading" })
    const [refreshing, setRefreshing] = useState(false)
    const [selectedGu, setSelectedGu] = useState<string | null>(null)
    const inflight = useRef<AbortController | null>(null)

    const load = useCallback(async () => {
        if (!jsonUrl) {
            setState({ status: "error", reason: "no jsonUrl prop" })
            return
        }
        inflight.current?.abort()
        const ac = new AbortController()
        inflight.current = ac
        const sep = jsonUrl.includes("?") ? "&" : "?"
        const url = `${jsonUrl}${sep}scenario=${scenario}&_=${Date.now()}`
        try {
            const r = await fetch(url, { cache: "no-store", signal: ac.signal })
            if (!r.ok) {
                setState({ status: "error", reason: `HTTP ${r.status}` })
                return
            }
            const data: PulseData = await r.json()
            if (!data?.gus || !data?.meta) {
                setState({ status: "error", reason: "schema_invalid" })
                return
            }
            setState({ status: "ok", data, fetchedAt: Date.now() })
        } catch (e: any) {
            if (e?.name === "AbortError") return
            setState({ status: "error", reason: e?.message || "fetch failed" })
        }
    }, [jsonUrl, scenario])

    useEffect(() => {
        load()
        return () => inflight.current?.abort()
    }, [load])

    const handleRefresh = useCallback(async () => {
        if (refreshing) return
        setRefreshing(true)
        await load()
        setTimeout(() => setRefreshing(false), 1000)
    }, [load, refreshing])

    const triggerType: LandexTrigger =
        state.status === "ok" ? inferTrigger(state.data) : "normal"
    const isShift = triggerType === "regime_shift"

    const dynamicCardStyle: React.CSSProperties = {
        ...cardStyle,
        borderLeft: `4px solid ${isShift ? C.accent : C.success}`,
    }

    return (
        <div style={dynamicCardStyle}>
            <StatusBar state={state} onRefresh={handleRefresh} refreshing={refreshing} />
            <Header triggerType={triggerType} state={state} />

            <SectionDivider label="META" />
            {state.status === "loading" && <SkeletonGrid n={4} h={56} />}
            {state.status === "error" && <ErrorBox reason={state.reason} stage="meta" />}
            {state.status === "ok" && (
                <MetaBlock
                    data={state.data}
                    fetchedAt={state.fetchedAt}
                    triggerType={triggerType}
                />
            )}

            <SectionDivider label="VISUALIZATION" />
            {state.status === "ok" && (
                <>
                    <GuGrid
                        gus={state.data.gus}
                        selectedGu={selectedGu}
                        onSelect={setSelectedGu}
                    />
                    {selectedGu && (
                        <GuDetailExpand
                            gu={state.data.gus.find((g) => g.gu_name === selectedGu)!}
                        />
                    )}
                </>
            )}

            <SectionDivider label="RANKING" />
            {state.status === "ok" && <RankingTable gus={state.data.gus} />}

            <Footer />
        </div>
    )
}


/* ──────────────────────────────────────────────────────────────
 * ◆ Subviews ◆
 * ────────────────────────────────────────────────────────────── */

function StatusBar({ state, onRefresh, refreshing }: {
    state: FetchState; onRefresh: () => void; refreshing: boolean
}) {
    const isOk = state.status === "ok"
    const isErr = state.status === "error"
    const dot = isOk ? C.success : isErr ? C.danger : C.warn
    const label = refreshing ? "REFRESHING…" : isOk ? "LIVE" : isErr ? "ERROR" : "LOADING"
    return (
        <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            paddingBottom: 14, marginBottom: 18,
            borderBottom: `1px solid ${C.border}`,
        }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{
                    width: 6, height: 6, borderRadius: "50%",
                    background: dot, boxShadow: `0 0 6px ${dot}88`,
                }} />
                <span style={{
                    color: C.textSecondary, fontSize: 10, fontWeight: 700,
                    fontFamily: FONT_MONO, letterSpacing: "0.12em",
                }}>{label}</span>
            </div>
            <button onClick={onRefresh} disabled={refreshing} style={{
                padding: "4px 10px", borderRadius: R.sm,
                background: "transparent",
                border: `1px solid ${C.border}`,
                color: refreshing ? C.textDisabled : C.textSecondary,
                fontSize: 10, fontFamily: FONT, fontWeight: 700,
                letterSpacing: "1.5px", textTransform: "uppercase",
                cursor: refreshing ? "not-allowed" : "pointer",
            }}>REFRESH</button>
        </div>
    )
}

function Header({ triggerType, state }: { triggerType: LandexTrigger; state: FetchState }) {
    const headers = TRIGGER_HEADERS[triggerType]
    const isShift = triggerType === "regime_shift"
    const totalChanged = state.status === "ok"
        ? state.data.meta.detail.degraded_count + state.data.meta.detail.gained_count
        : 0
    return (
        <div style={{ marginBottom: 18 }}>
            <div style={{
                color: C.textTertiary, fontSize: 10, fontFamily: FONT_MONO,
                letterSpacing: "0.18em", marginBottom: 4,
            }}>
                ESTATE · OPERATOR
            </div>
            <div style={{
                color: isShift ? C.accent : C.success,
                fontSize: 24, fontWeight: 700, fontFamily: FONT_SERIF,
                letterSpacing: "-0.01em", lineHeight: 1.2,
            }}>
                {headers.title}
            </div>
            <div style={{ color: C.textSecondary, fontSize: 12, fontFamily: FONT, marginTop: 4 }}>
                {headers.subtitle(totalChanged)}
            </div>
        </div>
    )
}

function SectionDivider({ label }: { label: string }) {
    return (
        <div style={{
            display: "flex", alignItems: "center", gap: 10,
            margin: "20px 0 12px",
        }}>
            <span style={{
                color: C.textTertiary, fontSize: 10, fontWeight: 700,
                fontFamily: FONT, letterSpacing: "1.5px",
                textTransform: "uppercase",
            }}>{label}</span>
            <div style={{ flex: 1, height: 1, background: C.border }} />
        </div>
    )
}

function MetaBlock({ data, fetchedAt, triggerType }: {
    data: PulseData; fetchedAt: number; triggerType: LandexTrigger
}) {
    const m = data.meta
    const now = Date.now()
    const fetchedMin = Math.floor((now - fetchedAt) / 60000)
    const lastShiftMin = minutesSince(m.primary.last_shift_at, now)

    const regimeMap: Record<string, string> = {
        bull: "BULL · 강세",
        bear: "BEAR · 약세",
        neutral: "NEUTRAL · 중립",
    }

    const primary: Array<[string, string, "ok" | "warn" | "neutral", string?]> = [
        ["CURRENT_REGIME", regimeMap[m.primary.current_regime] || "—",
            m.primary.current_regime === "bull" ? "ok" : m.primary.current_regime === "bear" ? "warn" : "neutral",
            "REGIME"],
        ["TOP_GAINER",
            `${m.primary.top_gainer.gu_name} +${m.primary.top_gainer.change_pct}%`,
            "ok", undefined],
        ["TOP_LOSER",
            `${m.primary.top_loser.gu_name} ${m.primary.top_loser.change_pct}%`,
            "warn", undefined],
        ["LAST_SHIFT", formatFreshness(lastShiftMin), "neutral", undefined],
    ]

    const detail: Array<[string, string, "ok" | "warn" | "neutral", string?]> = [
        ["DEGRADED_COUNT", String(m.detail.degraded_count),
            m.detail.degraded_count === 0 ? "ok" : "warn", undefined],
        ["GAINED_COUNT", String(m.detail.gained_count),
            m.detail.gained_count > 0 ? "ok" : "neutral", undefined],
        ["GEI_S4_COUNT", String(m.detail.gei_s4_count),
            m.detail.gei_s4_count === 0 ? "ok" : "warn", "GEI_STAGE"],
        ["AVG_LANDEX", String(m.detail.avg_landex), "neutral", "LANDEX"],
        ["DATA_FRESHNESS", formatFreshness(m.detail.data_freshness_min),
            m.detail.data_freshness_min <= 60 ? "ok" : "warn", undefined],
    ]

    return (
        <>
            {/* Primary 4셀 */}
            <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))",
                gap: 8, marginBottom: 12,
            }}>
                {primary.map(([k, v, tone, term]) => (
                    <div key={k} style={primaryCellStyle}>
                        <CellLabel text={k} termKey={term} />
                        <div style={{
                            color: tone === "ok" ? C.success : tone === "warn" ? C.warn : C.textPrimary,
                            fontSize: 14, fontFamily: FONT_MONO, fontWeight: 500,
                            marginTop: 4, wordBreak: "break-all",
                        }}>{v}</div>
                    </div>
                ))}
            </div>
            {/* Detail 5셀 */}
            <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
                gap: 4,
            }}>
                {detail.map(([k, v, tone, term]) => (
                    <div key={k} style={detailCellStyle}>
                        <CellLabel text={k} termKey={term} small />
                        <div style={{
                            color: tone === "ok" ? C.success : tone === "warn" ? C.warn : C.textSecondary,
                            fontSize: 11, fontFamily: FONT_MONO, marginTop: 2,
                        }}>{v}</div>
                    </div>
                ))}
            </div>
        </>
    )
}

function CellLabel({ text, termKey, small }: { text: string; termKey?: string; small?: boolean }) {
    const style: React.CSSProperties = {
        color: C.textTertiary,
        fontSize: small ? 9 : 10,
        fontWeight: small ? 500 : 600,
        fontFamily: FONT, letterSpacing: "1.5px",
        textTransform: "uppercase",
    }
    if (!termKey) return <div style={style}>{text}</div>
    return (
        <div style={style}>
            <TermTooltip termKey={termKey}><span>{text}</span></TermTooltip>
        </div>
    )
}

function GuGrid({ gus, selectedGu, onSelect }: {
    gus: Gu[]; selectedGu: string | null; onSelect: (gu: string | null) => void
}) {
    return (
        <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(110px, 1fr))",
            gap: 6,
        }}>
            {gus.map((g) => {
                const color = GRADE_COLORS[g.grade] || C.textTertiary
                const selected = selectedGu === g.gu_name
                return (
                    <button
                        key={g.gu_name}
                        onClick={() => onSelect(selected ? null : g.gu_name)}
                        style={{
                            padding: "10px 12px",
                            borderRadius: R.md,
                            border: `1px solid ${selected ? C.accent : C.border}`,
                            background: `${color}40`,  // alpha ~25% (다크 위 노출)
                            color: C.textPrimary,
                            fontFamily: FONT, cursor: "pointer",
                            textAlign: "left",
                            transition: "all 0.15s ease",
                        }}
                    >
                        <div style={{
                            fontSize: 12, fontWeight: 700,
                        }}>{g.gu_name}</div>
                        <div style={{
                            fontSize: 11, fontFamily: FONT_MONO,
                            marginTop: 2, color: C.textSecondary,
                        }}>{g.landex.toFixed(1)} · {g.grade}</div>
                    </button>
                )
            })}
        </div>
    )
}

function GuDetailExpand({ gu }: { gu: Gu }) {
    const isHotOrWarm = gu.grade === "HOT" || gu.grade === "WARM"
    const radar = gu.detail.radar
    const features = gu.detail.feature_contributions
    return (
        <div style={{
            marginTop: 14, padding: "16px 18px",
            background: C.bgElevated, borderRadius: R.lg,
            border: `1px solid ${GRADE_COLORS[gu.grade]}40`,
        }}>
            {/* Header — 구 명 + LANDEX 큰 점수 */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
                <div>
                    <div style={{ color: C.textTertiary, fontSize: 10, fontFamily: FONT_MONO, letterSpacing: "0.10em" }}>
                        SELECTED · GU
                    </div>
                    <div style={{ color: C.textPrimary, fontSize: 22, fontWeight: 700, fontFamily: FONT_SERIF, marginTop: 2 }}>
                        {gu.gu_name}
                    </div>
                </div>
                <div style={{ textAlign: "right" }}>
                    <div style={{ color: C.textTertiary, fontSize: 10, fontFamily: FONT, letterSpacing: "1.5px", textTransform: "uppercase" }}>
                        <TermTooltip termKey="LANDEX"><span>LANDEX</span></TermTooltip>
                    </div>
                    <div style={{
                        color: isHotOrWarm ? C.accent : C.textPrimary,
                        fontSize: 28, fontWeight: 800, fontFamily: FONT_MONO,
                    }}>{gu.landex.toFixed(1)}</div>
                </div>
            </div>

            {/* chips: 등급 + Stage */}
            <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                <span style={{
                    padding: "3px 10px", borderRadius: R.pill,
                    background: `${GRADE_COLORS[gu.grade]}25`,
                    border: `1px solid ${GRADE_COLORS[gu.grade]}60`,
                    color: GRADE_COLORS[gu.grade],
                    fontSize: 11, fontFamily: FONT, fontWeight: 700,
                }}>
                    <TermTooltip termKey={`GRADE_${gu.grade}`}><span>{gu.grade}</span></TermTooltip>
                </span>
                <span style={{
                    padding: "3px 10px", borderRadius: R.pill,
                    background: `${STAGE_COLORS[gu.stage]}25`,
                    border: `1px solid ${STAGE_COLORS[gu.stage] === "transparent" ? C.border : STAGE_COLORS[gu.stage]}60`,
                    color: STAGE_COLORS[gu.stage] === "transparent" ? C.textSecondary : STAGE_COLORS[gu.stage],
                    fontSize: 11, fontFamily: FONT, fontWeight: 700,
                }}>
                    <TermTooltip termKey="GEI_STAGE"><span>S{gu.stage}</span></TermTooltip>
                </span>
            </div>

            {/* Radar — 5축 simple ascii */}
            <div style={{ marginTop: 14 }}>
                <div style={{ color: C.textTertiary, fontSize: 10, fontFamily: FONT, letterSpacing: "1.5px", textTransform: "uppercase", marginBottom: 6 }}>
                    Score Radar
                </div>
                <ScoreRadar radar={radar} />
            </div>

            {/* Features — 피처 기여도 */}
            <div style={{ marginTop: 14 }}>
                <div style={{ color: C.textTertiary, fontSize: 10, fontFamily: FONT, letterSpacing: "1.5px", textTransform: "uppercase", marginBottom: 6 }}>
                    <TermTooltip termKey="FEATURE_CONTRIB"><span>Feature Contributions</span></TermTooltip>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    {features.map((f) => (
                        <FeatureBar key={f.feature} feat={f} />
                    ))}
                </div>
            </div>

            {/* Timeseries — mini sparkline */}
            <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <Sparkline
                    label={<TermTooltip termKey="WEEKLY_PRICE_INDEX"><span>주간 매매가격지수</span></TermTooltip>}
                    points={gu.detail.timeseries.weekly_price_index}
                />
                <Sparkline
                    label={<TermTooltip termKey="MONTHLY_UNSOLD"><span>월간 미분양</span></TermTooltip>}
                    points={gu.detail.timeseries.monthly_unsold}
                />
            </div>

            {/* 강점 / 약점 */}
            <div style={{ marginTop: 14, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                <StrengthsList strengths={gu.detail.strengths} />
                <WeaknessesList weaknesses={gu.detail.weaknesses} />
            </div>
        </div>
    )
}

function ScoreRadar({ radar }: { radar: { v: number; d: number; s: number; c: number; r: number } }) {
    const axes: Array<[string, number, string]> = [
        ["V", radar.v, "V_SCORE"],
        ["D", radar.d, "D_SCORE"],
        ["S", radar.s, "S_SCORE"],
        ["C", radar.c, "C_SCORE"],
        ["R", radar.r, "R_SCORE"],
    ]
    return (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8 }}>
            {axes.map(([axis, val, term]) => (
                <div key={axis} style={{
                    background: C.bgInput, borderRadius: R.sm,
                    border: `1px solid ${C.border}`, padding: "6px 8px",
                }}>
                    <div style={{ color: C.textTertiary, fontSize: 10, fontFamily: FONT, fontWeight: 600 }}>
                        <TermTooltip termKey={term}><span>{axis}</span></TermTooltip>
                    </div>
                    <div style={{
                        color: val >= 70 ? C.success : val >= 40 ? C.textPrimary : C.warn,
                        fontSize: 14, fontFamily: FONT_MONO, fontWeight: 600,
                        marginTop: 2,
                    }}>{val.toFixed(1)}</div>
                </div>
            ))}
        </div>
    )
}

function FeatureBar({ feat }: { feat: FeatureContrib }) {
    const isPositive = feat.sign === "+"
    const widthPct = Math.min(100, feat.weight * 100 * 3)  // 0.3 weight ≈ 90%
    return (
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{
                color: C.textSecondary, fontSize: 11, fontFamily: FONT_MONO,
                width: 180, flexShrink: 0,
            }}>{feat.feature}</div>
            <div style={{ flex: 1, height: 6, background: C.bgInput, borderRadius: 3, overflow: "hidden" }}>
                <div style={{
                    width: `${widthPct}%`, height: "100%",
                    background: isPositive ? C.success : C.danger,
                    transition: "width 0.2s",
                }} />
            </div>
            <div style={{
                color: isPositive ? C.success : C.danger,
                fontSize: 11, fontFamily: FONT_MONO, fontWeight: 700, width: 60, textAlign: "right",
            }}>{feat.sign}{feat.weight.toFixed(3)}</div>
        </div>
    )
}

function Sparkline({ label, points }: { label: React.ReactNode; points: SeriesPoint[] }) {
    if (!points || points.length < 2) {
        return <div style={{ color: C.textTertiary, fontSize: 11, fontFamily: FONT }}>{label}: —</div>
    }
    const values = points.map((p) => p.value)
    const min = Math.min(...values)
    const max = Math.max(...values)
    const range = max - min || 1
    const w = 200, h = 40
    const path = points.map((p, i) => {
        const x = (i / (points.length - 1)) * w
        const y = h - ((p.value - min) / range) * h
        return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`
    }).join(" ")
    const lastVal = values[values.length - 1]
    const firstVal = values[0]
    const trend = lastVal > firstVal ? C.success : lastVal < firstVal ? C.danger : C.textSecondary
    return (
        <div style={{
            background: C.bgInput, borderRadius: R.sm,
            border: `1px solid ${C.border}`, padding: "6px 8px",
        }}>
            <div style={{
                color: C.textTertiary, fontSize: 10, fontFamily: FONT, fontWeight: 600,
                letterSpacing: "1.5px", textTransform: "uppercase",
            }}>{label}</div>
            <svg width={w} height={h} style={{ marginTop: 4, display: "block" }}>
                <path d={path} fill="none" stroke={trend} strokeWidth={1.5} />
            </svg>
            <div style={{
                color: trend, fontSize: 11, fontFamily: FONT_MONO, marginTop: 2,
            }}>{firstVal.toFixed(1)} → {lastVal.toFixed(1)}</div>
        </div>
    )
}

function StrengthsList({ strengths }: { strengths: string[] }) {
    return (
        <div>
            <div style={{ color: C.success, fontSize: 10, fontFamily: FONT, letterSpacing: "1.5px", textTransform: "uppercase", fontWeight: 700, marginBottom: 4 }}>
                Strengths
            </div>
            <ul style={{ margin: 0, paddingLeft: 16, color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>
                {strengths.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
        </div>
    )
}

function WeaknessesList({ weaknesses }: { weaknesses: string[] }) {
    return (
        <div>
            <div style={{ color: C.warn, fontSize: 10, fontFamily: FONT, letterSpacing: "1.5px", textTransform: "uppercase", fontWeight: 700, marginBottom: 4 }}>
                Weaknesses
            </div>
            <ul style={{ margin: 0, paddingLeft: 16, color: C.textSecondary, fontSize: 12, fontFamily: FONT, lineHeight: 1.5 }}>
                {weaknesses.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
        </div>
    )
}

function RankingTable({ gus }: { gus: Gu[] }) {
    const sorted = [...gus].sort((a, b) => b.landex - a.landex)
    const headers: Array<[string, string?]> = [
        ["#", undefined],
        ["구", undefined],
        ["LANDEX↓", "LANDEX"],
        ["등급", undefined],
        ["GEI", undefined],
        ["Stage", "GEI_STAGE"],
        ["V", "V_SCORE"],
        ["D", "D_SCORE"],
        ["S", "S_SCORE"],
        ["C", "C_SCORE"],
    ]
    return (
        <div style={{
            background: C.bgElevated, borderRadius: R.md,
            border: `1px solid ${C.border}`, overflow: "hidden",
        }}>
            <div style={{
                display: "grid",
                gridTemplateColumns: "30px 1fr 70px 60px 50px 50px 45px 45px 45px 45px",
                gap: 6, padding: "8px 12px",
                borderBottom: `1px solid ${C.border}`,
                background: C.bgInput,
            }}>
                {headers.map(([h, term]) => (
                    <div key={h} style={{
                        color: C.textTertiary, fontSize: 10, fontFamily: FONT,
                        letterSpacing: "1.5px", textTransform: "uppercase", fontWeight: 700,
                    }}>
                        {term ? <TermTooltip termKey={term}><span>{h}</span></TermTooltip> : h}
                    </div>
                ))}
            </div>
            {sorted.map((g, i) => (
                <div key={g.gu_name} style={{
                    display: "grid",
                    gridTemplateColumns: "30px 1fr 70px 60px 50px 50px 45px 45px 45px 45px",
                    gap: 6, padding: "6px 12px",
                    borderBottom: i < sorted.length - 1 ? `1px solid ${C.border}` : "none",
                    fontFamily: FONT_MONO, fontSize: 11,
                }}>
                    <div style={{ color: C.textTertiary }}>{i + 1}</div>
                    <div style={{ color: C.textPrimary, fontFamily: FONT, fontWeight: 600 }}>{g.gu_name}</div>
                    <div style={{ color: g.grade === "HOT" || g.grade === "WARM" ? C.accent : C.textPrimary, fontWeight: 700 }}>
                        {g.landex.toFixed(1)}
                    </div>
                    <div style={{ color: GRADE_COLORS[g.grade] }}>{g.grade}</div>
                    <div style={{ color: C.textSecondary }}>{g.gei.toFixed(0)}</div>
                    <div style={{ color: STAGE_COLORS[g.stage] === "transparent" ? C.textTertiary : STAGE_COLORS[g.stage] }}>
                        S{g.stage}
                    </div>
                    <div style={{ color: C.textSecondary }}>{g.v_score.toFixed(0)}</div>
                    <div style={{ color: C.textSecondary }}>{g.d_score.toFixed(0)}</div>
                    <div style={{ color: C.textSecondary }}>{g.s_score.toFixed(0)}</div>
                    <div style={{ color: C.textSecondary }}>{g.c_score.toFixed(0)}</div>
                </div>
            ))}
        </div>
    )
}

function ErrorBox({ reason, stage }: { reason: string; stage: string }) {
    return (
        <div style={{
            padding: "10px 12px", borderRadius: R.md,
            background: `${C.danger}10`, border: `1px solid ${C.danger}40`,
        }}>
            <div style={{
                color: C.danger, fontSize: 11, fontWeight: 800,
                fontFamily: FONT_MONO, letterSpacing: "0.10em", marginBottom: 4,
            }}>
                {stage.toUpperCase()} · LOAD FAILED
            </div>
            <div style={{
                color: C.textSecondary, fontSize: 12, fontFamily: FONT_MONO,
                wordBreak: "break-all",
            }}>{reason}</div>
        </div>
    )
}

function SkeletonGrid({ n, h }: { n: number; h: number }) {
    return (
        <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))",
            gap: 8,
        }}>
            {Array.from({ length: n }).map((_, i) => (
                <div key={i} style={{
                    height: h, borderRadius: R.md,
                    background: C.bgElevated, border: `1px solid ${C.border}`,
                    backgroundImage: `linear-gradient(90deg, ${C.bgElevated} 0%, ${C.bgInput} 50%, ${C.bgElevated} 100%)`,
                    backgroundSize: "200% 100%",
                    animation: "estateSkel 1.4s ease-in-out infinite",
                }} />
            ))}
        </div>
    )
}

function Footer() {
    return (
        <div style={{
            marginTop: 18, paddingTop: 14,
            borderTop: `1px solid ${C.border}`,
            display: "flex", justifyContent: "space-between", alignItems: "center",
        }}>
            <span style={{ color: C.textTertiary, fontSize: 10, fontFamily: FONT_MONO, letterSpacing: "0.10em" }}>
                ESTATE · INTERNAL
            </span>
            <span style={{ color: C.textTertiary, fontSize: 10, fontFamily: FONT_MONO, letterSpacing: "0.10em" }}>
                v1.1 · ENCRYPTED
            </span>
        </div>
    )
}


/* ──────────────────────────────────────────────────────────────
 * ◆ TermTooltip — 인라인 컴포넌트 (T31 Framer self-contained) ◆
 * P4: ChangeFeed 등 다른 컴포넌트도 사용 시 estate/components/shared 분리 검토.
 * ────────────────────────────────────────────────────────────── */
function TermTooltip({ termKey, children }: { termKey: string; children: React.ReactNode }) {
    const [show, setShow] = useState(false)
    const term = TERMS[termKey]
    if (!term) return <>{children}</>
    return (
        <span
            onMouseEnter={() => setShow(true)}
            onMouseLeave={() => setShow(false)}
            onFocus={() => setShow(true)}
            onBlur={() => setShow(false)}
            tabIndex={0}
            style={{
                position: "relative", display: "inline-block",
                borderBottom: `1px dotted ${C.textTertiary}`,
                cursor: "help", outline: "none",
            }}
        >
            {children}
            {show && (
                <div style={{
                    position: "absolute", top: "calc(100% + 6px)", left: 0,
                    minWidth: 240, maxWidth: 360, zIndex: 100,
                    padding: "10px 12px", borderRadius: R.md,
                    background: C.bgElevated, border: `1px solid ${C.borderStrong}`,
                    boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                    fontFamily: FONT, fontSize: 12, lineHeight: 1.5,
                    whiteSpace: "normal",
                    pointerEvents: "none",
                }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                        <span style={{
                            color: C.textPrimary, fontFamily: FONT_SERIF, fontWeight: 700, fontSize: 13,
                        }}>{term.label}</span>
                        {term.l3 && (
                            <span style={{
                                color: C.accent, fontSize: 9, fontFamily: FONT,
                                letterSpacing: "1.5px", fontWeight: 800, textTransform: "uppercase",
                                padding: "1px 6px", borderRadius: R.pill,
                                border: `1px solid ${C.accent}60`,
                            }}>L3</span>
                        )}
                    </div>
                    <div style={{ color: C.textSecondary }}>{term.definition}</div>
                    {term.stages && (
                        <div style={{ marginTop: 6, paddingTop: 6, borderTop: `1px solid ${C.border}` }}>
                            {Object.entries(term.stages).map(([k, v]) => (
                                <div key={k} style={{ fontSize: 11, color: C.textTertiary }}>
                                    <span style={{ fontFamily: FONT_MONO, color: C.textSecondary }}>{k}</span>: {v}
                                </div>
                            ))}
                        </div>
                    )}
                    {term.values && (
                        <div style={{ marginTop: 6, paddingTop: 6, borderTop: `1px solid ${C.border}` }}>
                            {Object.entries(term.values).map(([k, v]) => (
                                <div key={k} style={{ fontSize: 11, color: C.textTertiary }}>
                                    <span style={{ fontFamily: FONT_MONO, color: C.textSecondary }}>{k}</span>: {v}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </span>
    )
}


/* ──────────────────────────────────────────────────────────────
 * ◆ Styles ◆
 * ────────────────────────────────────────────────────────────── */
const cardStyle: React.CSSProperties = {
    width: "100%", maxWidth: 1080,
    background: C.bgCard, borderRadius: 20,
    border: `1px solid ${C.border}`,
    boxShadow: `0 0 0 1px rgba(184,134,77,0.06), 0 12px 40px rgba(0,0,0,0.4)`,
    padding: "24px 26px",
    fontFamily: FONT, color: C.textPrimary,
}

const primaryCellStyle: React.CSSProperties = {
    background: C.bgElevated, borderRadius: R.md,
    border: `1px solid ${C.border}`,
    padding: "10px 12px",
}

const detailCellStyle: React.CSSProperties = {
    background: C.bgElevated, borderRadius: R.sm,
    border: `1px solid ${C.border}`,
    padding: "5px 8px",
}

/* skeleton keyframes */
if (typeof document !== "undefined" && !document.getElementById("estate-skel-kf")) {
    const s = document.createElement("style")
    s.id = "estate-skel-kf"
    s.textContent = `@keyframes estateSkel { 0%{background-position:200% 0} 100%{background-position:-200% 0} }`
    document.head.appendChild(s)
}

LandexPulse.defaultProps = {
    jsonUrl: ESTATE_LANDEX_PULSE_URL,
    scenario: "normal",
    showAdminMeta: true,
}

addPropertyControls(LandexPulse, {
    jsonUrl: {
        type: ControlType.String,
        title: "JSON URL",
        defaultValue: ESTATE_LANDEX_PULSE_URL,
        description: "/api/estate/landex-pulse endpoint",
    },
    scenario: {
        type: ControlType.Enum,
        title: "Scenario (P1 Mock)",
        defaultValue: "normal",
        options: ["normal", "regime_shift"],
        optionTitles: ["Normal", "Regime Shift"],
        description: "P1 Mock 검증 토글",
    },
    showAdminMeta: {
        type: ControlType.Boolean,
        title: "Admin Meta",
        defaultValue: true,
    },
})
