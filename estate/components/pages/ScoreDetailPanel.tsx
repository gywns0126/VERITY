// ScoreDetailPanel — 구별 LANDEX 상세 분석 패널
// VERITY ESTATE 페이지급 컴포넌트.
// 흡수: ScoreRadar (5축 레이더) + FeatureContribBar (피처 기여도).
//
// 헤더(구·LANDEX 점수) + ScoreRadar + FeatureContribBar + 강점/약점 코멘트.

import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState, useMemo } from "react"

/* ◆ DESIGN TOKENS START ◆ */
const C = {
    bgPage: "#0E0F11", bgCard: "#171820", bgElevated: "#22232B", bgInput: "#2A2B33",
    border: "#23242C", borderStrong: "#34353D",
    textPrimary: "#F2F3F5", textSecondary: "#A8ABB2", textTertiary: "#6B6E76", textDisabled: "#4A4C52",
    accent: "#B8864D", accentHover: "#D4A063", accentSoft: "rgba(184,134,77,0.12)",
    gradeHOT: "#EF4444", gradeWARM: "#F59E0B", gradeNEUT: "#A8ABB2", gradeCOOL: "#5BA9FF", gradeAVOID: "#6B6E76",
    statusPos: "#22C55E", statusNeut: "#A8ABB2", statusNeg: "#EF4444",
    info: "#5BA9FF",
}
const T = { cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28, h0: 36,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700 }
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24 }
const R = { sm: 6, md: 10, lg: 14 }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/* ◆ TYPES ◆ */
type GradeLabel = "HOT" | "WARM" | "NEUT" | "COOL" | "AVOID"
type SensitivityLevel = "L0" | "L1" | "L2" | "L3"

interface ScoreSet {
    V: number; D: number; S: number; C: number
    /** R은 감점 (음수 표시 가능) */
    R: number
}
interface FeatureContrib {
    label: string
    value: number  // 음수 가능
}
interface SeriesPoint { x: string; y: number; date: string | null }
interface TimeSeries {
    metric: "price_index" | "unsold"
    series: SeriesPoint[]
    asOf: string | null
    source: string | null
}
interface GuDetail {
    name: string
    landex: number
    grade: GradeLabel
    scores: ScoreSet
    features: FeatureContrib[]
    strengths: string[]
    weaknesses: string[]
}


/* ◆ PRIVACY HOOK ◆ */
function usePrivacyMode() {
    const [privacyMode, setPM] = useState(() =>
        typeof window !== "undefined" && (window as any).__VERITY_PRIVACY__ === true
    )
    useEffect(() => {
        if (typeof window === "undefined") return
        const onChange = () => setPM((window as any).__VERITY_PRIVACY__ === true)
        const onKey = (e: KeyboardEvent) => {
            if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "p") {
                e.preventDefault()
                ;(window as any).__VERITY_PRIVACY__ = !((window as any).__VERITY_PRIVACY__ === true)
                window.dispatchEvent(new Event("verity:privacy-change"))
            }
        }
        window.addEventListener("verity:privacy-change", onChange)
        window.addEventListener("keydown", onKey)
        return () => {
            window.removeEventListener("verity:privacy-change", onChange)
            window.removeEventListener("keydown", onKey)
        }
    }, [])
    const shouldMask = (s: SensitivityLevel) => s !== "L0" && privacyMode
    return { privacyMode, shouldMask }
}


/* ◆ MOCK DATA ◆ */
const MOCK_DETAIL: GuDetail = {
    name: "강남구",
    landex: 87,
    grade: "HOT",
    scores: { V: 82, D: 90, S: 78, C: 92, R: 18 },
    features: [
        { label: "교통 접근성", value: 28 },
        { label: "학군 수요", value: 22 },
        { label: "재건축 진행", value: 18 },
        { label: "신규 분양", value: 12 },
        { label: "공급 부족", value: -15 },
        { label: "금리 상승", value: -10 },
        { label: "정책 리스크", value: -8 },
    ],
    strengths: [
        "교통 인프라 최상위 — 9호선·신분당선 환승 거점",
        "학군 수요 안정적, 임대 회전율 낮음",
        "재건축 진행 단지 집중 분포",
    ],
    weaknesses: [
        "신규 공급 절벽 — 3년간 신규 분양 -42%",
        "고금리 환경 직접 노출, DSR 규제 영향 큼",
    ],
}


/* ◆ DATA FETCH ◆ */
async function fetchDetail(apiUrl: string, gu: string, month: string, signal?: AbortSignal): Promise<GuDetail> {
    if (!apiUrl) return { ...MOCK_DETAIL, name: gu || MOCK_DETAIL.name }
    const base = apiUrl.replace(/\/$/, "")
    try {
        // 3개 endpoint 병렬 호출 — scores (점수) + features (기여도) + narrative (강·약점)
        const [rScores, rFeatures, rNarrative] = await Promise.all([
            fetch(`${base}/api/landex/scores?gu=${encodeURIComponent(gu)}&month=${month}`, { signal }),
            fetch(`${base}/api/landex/features?gu=${encodeURIComponent(gu)}&month=${month}`, { signal }),
            fetch(`${base}/api/landex/narrative?gu=${encodeURIComponent(gu)}&month=${month}`, { signal }),
        ])
        if (!rScores.ok) throw new Error("scores fetch failed")

        const jScores = await rScores.json()
        const row = (jScores?.data ?? [])[0]
        if (!row) throw new Error("empty")

        // features / narrative 가 실패해도 scores 는 살림 — mock fallback
        let features = MOCK_DETAIL.features
        let strengths = MOCK_DETAIL.strengths
        let weaknesses = MOCK_DETAIL.weaknesses

        if (rFeatures.ok) {
            const jf = await rFeatures.json()
            if (Array.isArray(jf?.features) && jf.features.length > 0) features = jf.features
        }
        if (rNarrative.ok) {
            const jn = await rNarrative.json()
            if (Array.isArray(jn?.strengths))  strengths = jn.strengths
            if (Array.isArray(jn?.weaknesses)) weaknesses = jn.weaknesses
        }

        return {
            name: row.gu,
            landex: row.landex ?? 0,
            grade: (row.tier5 ?? "NEUT") as GradeLabel,
            scores: { V: row.v ?? 0, D: row.d ?? 0, S: row.s ?? 0, C: row.c ?? 0, R: row.r ?? 0 },
            features, strengths, weaknesses,
        }
    } catch {
        return { ...MOCK_DETAIL, name: gu || MOCK_DETAIL.name }
    }
}


/* ◆ UTIL ◆ */
function gradeColor(g: GradeLabel): string {
    return g === "HOT" ? C.gradeHOT : g === "WARM" ? C.gradeWARM : g === "NEUT" ? C.gradeNEUT : g === "COOL" ? C.gradeCOOL : C.gradeAVOID
}

function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number) {
    const rad = ((angleDeg - 90) * Math.PI) / 180
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) }
}


/* ◆ INTERNAL: Header (구명 + LANDEX 점수 + 등급) ◆ */
function DetailHeader({ detail, masked }: { detail: GuDetail; masked: boolean }) {
    const c = gradeColor(detail.grade)
    return (
        <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between", gap: S.md,
            padding: S.lg, backgroundColor: C.bgCard,
            border: `1px solid ${C.border}`, borderLeft: `3px solid ${c}`,
            borderRadius: R.md,
        }}>
            <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                <span style={{ fontSize: T.cap, color: C.textTertiary, textTransform: "uppercase", letterSpacing: 1 }}>
                    LANDEX 상세
                </span>
                <span style={{ fontSize: T.h1, fontWeight: T.w_bold, color: C.textPrimary }}>{detail.name}</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: S.xs }}>
                <span style={{ fontSize: T.cap, color: C.textTertiary }}>LANDEX</span>
                <div style={{ display: "flex", alignItems: "baseline", gap: S.sm }}>
                    <span style={{ fontSize: T.h0, fontWeight: T.w_bold, color: c, ...MONO }}>
                        {masked ? "—" : detail.landex}
                    </span>
                    <span style={{ fontSize: T.body, color: C.textTertiary }}>/ 100</span>
                </div>
                <span style={{
                    padding: "2px 10px", borderRadius: R.sm,
                    background: c + "1A", color: c,
                    fontSize: T.cap, fontWeight: T.w_semi, letterSpacing: 0.5,
                }}>{detail.grade}</span>
            </div>
        </div>
    )
}


/* ◆ INTERNAL: ScoreRadar (5축 V/D/S/C/R) ◆ */
function ScoreRadarCard({ scores, masked, size = 280 }: { scores: ScoreSet; masked: boolean; size?: number }) {
    const padding = 36
    const cx = size / 2
    const cy = size / 2
    const rMax = size / 2 - padding

    const axes = useMemo(() => ([
        { key: "V", label: "Value", value: scores.V },
        { key: "D", label: "Development", value: scores.D },
        { key: "S", label: "Supply", value: scores.S },
        { key: "C", label: "Convenience", value: scores.C },
        { key: "R", label: "Risk", value: Math.abs(scores.R) },
    ]), [scores])

    const gridSteps = [0.25, 0.5, 0.75, 1.0]

    const points = axes.map((a, i) => {
        const angle = (360 / axes.length) * i
        const r = (Math.max(0, Math.min(100, a.value)) / 100) * rMax
        return polarToCartesian(cx, cy, r, angle)
    })
    const polygonPath = points.map((p) => `${p.x},${p.y}`).join(" ")

    return (
        <div style={{
            padding: S.lg, backgroundColor: C.bgCard,
            border: `1px solid ${C.border}`, borderRadius: R.md,
            display: "flex", flexDirection: "column", gap: S.sm,
        }}>
            <span style={{ fontSize: T.sub, fontWeight: T.w_semi, color: C.textPrimary }}>Score Radar — V·D·S·C·R</span>

            <div style={{ display: "flex", justifyContent: "center" }}>
                <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
                    {gridSteps.map((step, idx) => {
                        const ringPoints = axes.map((_, i) => {
                            const angle = (360 / axes.length) * i
                            return polarToCartesian(cx, cy, rMax * step, angle)
                        })
                        return (
                            <polygon key={idx}
                                points={ringPoints.map((p) => `${p.x},${p.y}`).join(" ")}
                                fill="none" stroke={C.border} strokeWidth={1} opacity={0.5}
                            />
                        )
                    })}
                    {axes.map((_, i) => {
                        const angle = (360 / axes.length) * i
                        const end = polarToCartesian(cx, cy, rMax, angle)
                        return (
                            <line key={i} x1={cx} y1={cy} x2={end.x} y2={end.y}
                                stroke={C.border} strokeWidth={1} opacity={0.4} />
                        )
                    })}
                    {!masked && (
                        <>
                            <polygon points={polygonPath}
                                fill={C.accent} fillOpacity={0.25}
                                stroke={C.accent} strokeWidth={2} />
                            {points.map((p, i) => (
                                <circle key={i} cx={p.x} cy={p.y} r={3} fill={C.accent} />
                            ))}
                        </>
                    )}
                    {axes.map((a, i) => {
                        const angle = (360 / axes.length) * i
                        const labelPos = polarToCartesian(cx, cy, rMax + 18, angle)
                        return (
                            <g key={i}>
                                <text x={labelPos.x} y={labelPos.y - 6}
                                    textAnchor="middle" dominantBaseline="middle"
                                    fill={C.textSecondary} fontSize={T.cap}
                                    fontFamily={FONT} fontWeight={T.w_semi}
                                >{a.key}</text>
                                <text x={labelPos.x} y={labelPos.y + 8}
                                    textAnchor="middle" dominantBaseline="middle"
                                    fill={C.textTertiary} fontSize={11}
                                    fontFamily={FONT_MONO}
                                >{masked ? "—" : a.key === "R" && scores.R < 0 ? `−${a.value}` : a.value}</text>
                            </g>
                        )
                    })}
                </svg>
            </div>

            <div style={{ display: "flex", flexWrap: "wrap", gap: S.sm, justifyContent: "center" }}>
                {axes.map((a) => (
                    <span key={a.key} style={{ fontSize: T.cap, color: C.textTertiary }}>
                        <span style={{ color: C.accent, fontWeight: T.w_semi }}>{a.key}</span>{" "}
                        {a.label}
                    </span>
                ))}
            </div>
        </div>
    )
}


/* ◆ INTERNAL: FeatureContribCard (SHAP 막대) ◆ */
function FeatureContribCard({ features, masked }: { features: FeatureContrib[]; masked: boolean }) {
    if (masked) {
        return (
            <div style={{
                padding: S.lg, backgroundColor: C.bgCard,
                border: `1px dashed ${C.border}`, borderRadius: R.md,
                color: C.textTertiary, fontSize: T.body, textAlign: "center",
            }}>
                🔒 Feature Contribution — Privacy Mode 마스킹 (전면 L3)
            </div>
        )
    }
    const maxAbs = Math.max(1, ...features.map((f) => Math.abs(f.value)))
    return (
        <div style={{
            padding: S.lg, backgroundColor: C.bgCard,
            border: `1px solid ${C.border}`, borderRadius: R.md,
            display: "flex", flexDirection: "column", gap: S.sm,
        }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontSize: T.sub, fontWeight: T.w_semi, color: C.textPrimary }}>피처 기여도</span>
                <span style={{ fontSize: T.cap, color: C.gradeWARM }}>⚠️ L3 — 외부 공유 금지</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                {features.map((f, i) => {
                    const pct = (Math.abs(f.value) / maxAbs) * 100
                    const positive = f.value >= 0
                    const color = positive ? C.statusPos : C.statusNeg
                    return (
                        <div key={i} style={{ display: "flex", alignItems: "center", gap: S.sm }}>
                            <span style={{
                                width: 110, fontSize: T.cap, color: C.textSecondary, flexShrink: 0,
                                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                            }}>{f.label}</span>
                            <div style={{
                                flex: 1, height: 8, background: C.bgElevated,
                                borderRadius: R.sm, overflow: "hidden",
                            }}>
                                <div style={{
                                    width: `${pct}%`, height: "100%", background: color,
                                    borderRadius: R.sm, transition: "width 200ms",
                                }} />
                            </div>
                            <span style={{
                                width: 48, textAlign: "right",
                                fontSize: T.cap, color, ...MONO, flexShrink: 0,
                            }}>{positive ? "+" : ""}{f.value}</span>
                        </div>
                    )
                })}
            </div>
        </div>
    )
}


/* ◆ INTERNAL: TimeSeriesCard (sparkline) ◆ */
async function fetchTimeSeries(
    apiUrl: string, gu: string, metric: "price_index" | "unsold",
    signal?: AbortSignal,
): Promise<TimeSeries | null> {
    if (!apiUrl || !gu) return null
    const base = apiUrl.replace(/\/$/, "")
    const qs = metric === "price_index" ? "weeks=52" : "months=24"
    try {
        const r = await fetch(
            `${base}/api/landex/timeseries?gu=${encodeURIComponent(gu)}&metric=${metric}&${qs}`,
            { signal },
        )
        if (!r.ok) return null
        const j = await r.json()
        if (!Array.isArray(j?.series) || j.series.length === 0) return null
        return { metric, series: j.series, asOf: j.as_of ?? null, source: j.source ?? null }
    } catch {
        return null
    }
}

function Sparkline({
    points, color, width = 180, height = 44,
}: { points: SeriesPoint[]; color: string; width?: number; height?: number }) {
    if (points.length < 2) return null
    const ys = points.map((p) => p.y)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)
    const range = Math.max(1e-6, maxY - minY)
    const pad = 4
    const w = width - pad * 2
    const h = height - pad * 2
    const path = points.map((p, i) => {
        const x = pad + (i / (points.length - 1)) * w
        const y = pad + h - ((p.y - minY) / range) * h
        return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`
    }).join(" ")
    const last = points[points.length - 1]
    const lastX = pad + w
    const lastY = pad + h - ((last.y - minY) / range) * h
    return (
        <svg width={width} height={height} style={{ display: "block" }}>
            <path d={path} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" />
            <circle cx={lastX} cy={lastY} r={2.5} fill={color} />
        </svg>
    )
}

function TimeSeriesCard({ apiUrl, gu, masked }: { apiUrl: string; gu: string; masked: boolean }) {
    const [price, setPrice] = useState<TimeSeries | null>(null)
    const [unsold, setUnsold] = useState<TimeSeries | null>(null)
    const [loading, setLoading] = useState(false)

    useEffect(() => {
        const ac = new AbortController()
        setLoading(true)
        Promise.all([
            fetchTimeSeries(apiUrl, gu, "price_index", ac.signal),
            fetchTimeSeries(apiUrl, gu, "unsold", ac.signal),
        ]).then(([p, u]) => { setPrice(p); setUnsold(u) })
          .finally(() => setLoading(false))
        return () => ac.abort()
    }, [apiUrl, gu])

    const formatDelta = (s: SeriesPoint[]): { pct: number; sign: "+" | "−" | "" } => {
        if (s.length < 2) return { pct: 0, sign: "" }
        const first = s[0].y, last = s[s.length - 1].y
        if (first <= 0) return { pct: 0, sign: "" }
        const pct = ((last - first) / first) * 100
        return {
            pct: Math.abs(pct),
            sign: pct > 0.05 ? "+" : pct < -0.05 ? "−" : "",
        }
    }

    const renderRow = (
        label: string, sub: string, ts: TimeSeries | null, color: string,
        valueFmt: (v: number) => string,
    ) => {
        if (masked) {
            return (
                <div style={rowStyle}>
                    <div style={labelColStyle}>
                        <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi }}>{label}</span>
                        <span style={{ color: C.textTertiary, fontSize: T.cap }}>{sub}</span>
                    </div>
                    <span style={{ color: C.textTertiary, fontSize: T.cap, fontStyle: "italic" }}>🔒 마스킹</span>
                </div>
            )
        }
        if (!ts || ts.series.length < 2) {
            return (
                <div style={rowStyle}>
                    <div style={labelColStyle}>
                        <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi }}>{label}</span>
                        <span style={{ color: C.textTertiary, fontSize: T.cap }}>{sub}</span>
                    </div>
                    <span style={{ color: C.textTertiary, fontSize: T.cap, fontStyle: "italic" }}>
                        {loading ? "· 로딩 중" : "데이터 없음"}
                    </span>
                </div>
            )
        }
        const { pct, sign } = formatDelta(ts.series)
        const last = ts.series[ts.series.length - 1].y
        const deltaColor = sign === "+" ? C.statusPos : sign === "−" ? C.statusNeg : C.textSecondary
        // unsold 는 감소가 호재 → 색 반전
        const adjustedColor = ts.metric === "unsold"
            ? (sign === "+" ? C.statusNeg : sign === "−" ? C.statusPos : C.textSecondary)
            : deltaColor
        return (
            <div style={rowStyle}>
                <div style={labelColStyle}>
                    <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi }}>{label}</span>
                    <span style={{ color: C.textTertiary, fontSize: T.cap }}>
                        {sub}
                        {ts.asOf ? ` · ${ts.asOf}` : ""}
                    </span>
                </div>
                <Sparkline points={ts.series} color={color} />
                <div style={valueColStyle}>
                    <span style={{ color: C.textPrimary, fontSize: T.body, fontWeight: T.w_semi, ...MONO }}>
                        {valueFmt(last)}
                    </span>
                    <span style={{ color: adjustedColor, fontSize: T.cap, fontWeight: T.w_semi, ...MONO }}>
                        {sign}{pct.toFixed(1)}%
                    </span>
                </div>
            </div>
        )
    }

    return (
        <div style={{
            padding: S.lg, backgroundColor: C.bgCard,
            border: `1px solid ${C.border}`, borderRadius: R.md,
            display: "flex", flexDirection: "column", gap: S.sm,
        }}>
            <span style={{ fontSize: T.sub, fontWeight: T.w_semi, color: C.textPrimary }}>
                시계열 — R-ONE 한국부동산원
            </span>
            {renderRow(
                "주간 매매가격지수", "최근 52주", price, C.accent,
                (v) => v.toFixed(2),
            )}
            {renderRow(
                "월간 미분양 호수", "최근 24개월", unsold, C.info,
                (v) => `${Math.round(v).toLocaleString()}호`,
            )}
        </div>
    )
}

const rowStyle: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: "minmax(140px, 1fr) auto auto",
    gap: S.md, alignItems: "center",
    padding: `${S.xs}px 0`,
}
const labelColStyle: React.CSSProperties = {
    display: "flex", flexDirection: "column", gap: 2, minWidth: 0,
}
const valueColStyle: React.CSSProperties = {
    display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2, minWidth: 70,
}


/* ◆ INTERNAL: StrengthsWeaknesses ◆ */
function CommentList({ title, items, color }: { title: string; items: string[]; color: string }) {
    return (
        <div style={{
            padding: S.lg, backgroundColor: C.bgCard,
            border: `1px solid ${C.border}`, borderRadius: R.md,
            display: "flex", flexDirection: "column", gap: S.sm, flex: 1, minWidth: 0,
        }}>
            <span style={{ fontSize: T.sub, fontWeight: T.w_semi, color }}>{title}</span>
            <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: S.xs }}>
                {items.map((it, i) => (
                    <li key={i} style={{
                        fontSize: T.body, color: C.textPrimary, lineHeight: 1.5,
                        paddingLeft: S.md, position: "relative",
                    }}>
                        <span style={{
                            position: "absolute", left: 0, top: 8, width: 4, height: 4,
                            borderRadius: "50%", background: color,
                        }} />
                        {it}
                    </li>
                ))}
                {items.length === 0 && (
                    <li style={{ fontSize: T.cap, color: C.textTertiary }}>—</li>
                )}
            </ul>
        </div>
    )
}


/* ◆ MAIN ◆ */
interface Props {
    apiUrl: string
    /** 표시할 구명. 비우면 mock(강남구). */
    gu: string
    /** 표시할 월 (YYYY-MM) */
    month: string
    /** Privacy Mode sensitivity. ScoreRadar는 L1, FeatureContribBar는 항상 L3. */
    sensitivity: SensitivityLevel
}

function ScoreDetailPanel({ apiUrl = "", gu = "강남구", month = "2026-04", sensitivity = "L1" }: Props) {
    const [detail, setDetail] = useState<GuDetail>(() => ({ ...MOCK_DETAIL, name: gu || MOCK_DETAIL.name }))
    const [loading, setLoading] = useState(false)
    const { shouldMask } = usePrivacyMode()
    const radarMasked = shouldMask(sensitivity)
    const featureMasked = shouldMask("L3")  // FeatureContribBar는 항상 L3 마스킹 정책

    useEffect(() => {
        const ac = new AbortController()
        setLoading(true)
        fetchDetail(apiUrl, gu, month, ac.signal)
            .then((d) => { setDetail(d); setLoading(false) })
            .catch(() => setLoading(false))
        return () => ac.abort()
    }, [apiUrl, gu, month])

    return (
        <div style={{
            width: "100%", height: "100%", display: "flex", flexDirection: "column", gap: S.md, padding: S.md,
            backgroundColor: C.bgPage, fontFamily: FONT, color: C.textPrimary,
            boxSizing: "border-box", minWidth: 720, minHeight: 600, overflowY: "auto",
        }}>
            <DetailHeader detail={detail} masked={radarMasked} />

            {loading && <span style={{ fontSize: T.cap, color: C.info, ...MONO }}>· 로딩 중</span>}

            <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: S.md }}>
                <ScoreRadarCard scores={detail.scores} masked={radarMasked} />
                <FeatureContribCard features={detail.features} masked={featureMasked} />
            </div>

            <TimeSeriesCard apiUrl={apiUrl} gu={detail.name} masked={radarMasked} />

            <div style={{ display: "flex", gap: S.md, flexWrap: "wrap" }}>
                <CommentList title="✓ 강점" items={detail.strengths} color={C.statusPos} />
                <CommentList title="✕ 약점" items={detail.weaknesses} color={C.statusNeg} />
            </div>
        </div>
    )
}

addPropertyControls(ScoreDetailPanel, {
    apiUrl: { type: ControlType.String, defaultValue: "", description: "vercel-api base URL. 비우면 mock." },
    gu: { type: ControlType.String, defaultValue: "강남구", description: "표시할 구명" },
    month: { type: ControlType.String, defaultValue: "2026-04", description: "YYYY-MM" },
    sensitivity: { type: ControlType.Enum, options: ["L0", "L1", "L2", "L3"], defaultValue: "L1" },
})

export default ScoreDetailPanel
