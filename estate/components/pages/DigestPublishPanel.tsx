// DigestPublishPanel — Digest 공개 발행 워크플로우 패널
// VERITY ESTATE 페이지급 컴포넌트.
// 흡수: DilutionCheckPanel + 발행 미리보기 + 예약/즉시 발행.
//
// 좌: 미리보기(공개 카드) | 우: 희석 체크리스트 + 발행 버튼.

import { addPropertyControls, ControlType } from "framer"
import React, { useEffect, useState, useMemo } from "react"

/* ◆ ESTATE 패밀리룩 v3 (2026-05-05) — Cluster A warm gold tone 통일. ◆ */
const C = {
    bgPage: "#0A0908", bgCard: "#0F0D0A", bgElevated: "#16130E", bgInput: "#1F1B14",
    border: "transparent", borderStrong: "#3A3024",
    textPrimary: "#F2EFE9", textSecondary: "#A8A299", textTertiary: "#6B665E", textDisabled: "#4A453E",
    accent: "#B8864D", accentBright: "#D4A26B", accentHover: "#D4A063",
    accentSoft: "rgba(184,134,77,0.15)",
    statusPos: "#22C55E", statusNeut: "#A8A299", statusNeg: "#EF4444",
    info: "#5BA9FF", warn: "#F59E0B",
}
const T = { cap: 12, body: 14, sub: 16, title: 18, h2: 22, h1: 28,
    w_reg: 400, w_med: 500, w_semi: 600, w_bold: 700 }
const S = { xs: 4, sm: 8, md: 12, lg: 16, xl: 20, xxl: 24 }
const R = { sm: 6, md: 10, lg: 14 }
const X = { fast: "120ms ease", base: "180ms ease" }
const FONT = "'Pretendard', 'Inter', -apple-system, sans-serif"
const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"
const MONO: React.CSSProperties = { fontFamily: FONT_MONO, fontVariantNumeric: "tabular-nums" }
/* ◆ DESIGN TOKENS END ◆ */


/* ◆ TYPES (백엔드 /api/digest/publish-readiness 와 정합) ◆ */
type CheckCategory = "data" | "logic" | "ux"

interface DilutionCheckItem {
    id: string
    category: CheckCategory
    label: string
    description?: string
    passed: boolean
    reason?: string
}

interface DivergenceWarning {
    kind: string
    severity: "high" | "mid" | "low"
    message: string
}

interface DigestPreview {
    title: string
    period: string  // "2026-04 4주차"
    summary: string
    sections: { heading: string; body: string }[]
    publicNotes: string[]  // 공개 시 주의 문구
}


/* ◆ MOCK DATA — 백엔드 9 체크리스트와 정합 ◆ */
const MOCK_CHECKS: DilutionCheckItem[] = [
    { id: "recency",    category: "data",  label: "Recency Check",     description: "실거래가·매물 데이터가 최근 72시간 이내", passed: true },
    { id: "outlier",    category: "data",  label: "Outlier Filter",    description: "평균가 대비 ±30% 이상 이상치 제거", passed: true },
    { id: "source",     category: "data",  label: "Source Validation", description: "V/D/S/C/R 결측치 2개 이상 미발생", passed: false, reason: "R 결측 — 한국은행 ECOS 응답 누락" },
    { id: "divergence", category: "logic", label: "Bull/Bear Cross-check", description: "LANDEX↑ + 거래량↓ 또는 GEI Stage 4 다이버전스 경고 포함", passed: false, reason: "LANDEX 상승 + GEI 4 발생했으나 요약문에 경고 미포함" },
    { id: "weight",     category: "logic", label: "Weighted Alignment", description: "특정 가중치가 60% 이상 지배하지 않음", passed: true },
    { id: "sentiment",  category: "logic", label: "Sentiment Sync",    description: "정량 점수와 뉴스 감성 방향성 일치", passed: true },
    { id: "actionable", category: "ux",    label: "Actionable Insight", description: "매수/보유/관망 결론 명확", passed: true },
    { id: "disclosure", category: "ux",    label: "Risk Disclosure",   description: "투자 참고용 + 본인 책임 면책 문구", passed: true },
    { id: "comparison", category: "ux",    label: "Comparison Context", description: "인근 단지·구 평균 비교 차트 포함", passed: false, reason: "구 평균 비교 차트 미생성" },
]

const MOCK_WARNINGS: DivergenceWarning[] = [
    { kind: "landex_up_gei_overheat", severity: "high", message: "LANDEX 상승하나 GEI Stage 4 — 과열 후 조정 위험" },
]

const MOCK_PREVIEW: DigestPreview = {
    title: "서울 부동산 주간 인사이트",
    period: "2026-04 4주차",
    summary: "GEI Stage 3 이상 구가 2주 연속 5개 유지. 강남권 과열 신호 지속, 서북부 안정세.",
    sections: [
        { heading: "이번주 핵심", body: "강남권 LANDEX 상위 5구가 평균 +4점 상승. 거래량은 보합." },
        { heading: "주목 흐름", body: "용산구 신분당선 연장 확정 — 카탈리스트 점수 +12. 6개월 모니터링 추천." },
        { heading: "주의 구간", body: "도봉·강북구 AVOID 등급 유지. 임차 매물 누적 증가." },
    ],
    publicNotes: [
        "본 리포트는 VERITY ESTATE 내부 모델의 희석된 공개판입니다.",
        "개별 구의 정확한 점수·매수 추천은 포함하지 않습니다.",
        "투자 판단의 책임은 본인에게 있습니다.",
    ],
}


/* ◆ DATA FETCH (vercel-api/api/digest/publish-readiness 와 정합) ◆ */
interface PublishReadiness {
    checks: DilutionCheckItem[]
    warnings: DivergenceWarning[]
    confidenceScore: number
    publishThreshold: number
    readyToPublish: boolean
    preview: DigestPreview
}

async function fetchPublishData(apiUrl: string, signal?: AbortSignal): Promise<PublishReadiness> {
    const fallback: PublishReadiness = {
        checks: MOCK_CHECKS, warnings: MOCK_WARNINGS,
        confidenceScore: 67, publishThreshold: 80, readyToPublish: false,
        preview: MOCK_PREVIEW,
    }
    if (!apiUrl) return fallback
    try {
        const res = await fetch(`${apiUrl.replace(/\/$/, "")}/api/digest/publish-readiness`, { signal })
        if (!res.ok) throw new Error()
        const j = await res.json()
        // 백엔드 키 → 프론트 키 매핑
        const previewRaw = j?.preview ?? {}
        return {
            checks: Array.isArray(j?.checklist) && j.checklist.length ? j.checklist : MOCK_CHECKS,
            warnings: Array.isArray(j?.divergence_warnings) ? j.divergence_warnings : [],
            confidenceScore: typeof j?.confidence_score === "number" ? j.confidence_score : 0,
            publishThreshold: typeof j?.publish_threshold === "number" ? j.publish_threshold : 80,
            readyToPublish: !!j?.ready_to_publish,
            preview: {
                title: previewRaw.title ?? MOCK_PREVIEW.title,
                period: previewRaw.period ?? MOCK_PREVIEW.period,
                summary: previewRaw.summary ?? "",
                sections: Array.isArray(previewRaw.sections) ? previewRaw.sections : [],
                publicNotes: Array.isArray(previewRaw.public_notes) ? previewRaw.public_notes : [],
            },
        }
    } catch {
        return fallback
    }
}


/* ◆ INTERNAL: ConfidenceGauge (0-100 게이지 + 발행 임계선) ◆ */
function ConfidenceGauge({ score, threshold }: { score: number; threshold: number }) {
    const pct = Math.max(0, Math.min(100, score))
    const ready = pct >= threshold
    const barColor = ready ? C.statusPos : pct >= threshold - 15 ? C.warn : C.statusNeg
    return (
        <div style={{
            padding: S.md, backgroundColor: C.bgElevated, borderRadius: R.sm,
            display: "flex", flexDirection: "column", gap: S.xs,
        }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
                <span style={{ fontSize: T.cap, color: C.textTertiary, textTransform: "uppercase", letterSpacing: 1 }}>
                    Confidence Score
                </span>
                <span style={{ fontSize: T.h2, fontWeight: T.w_bold, color: barColor, ...MONO }}>
                    {pct.toFixed(0)}
                </span>
            </div>
            <div style={{ position: "relative", height: 8, background: C.bgPage, borderRadius: 4, overflow: "hidden" }}>
                <div style={{ width: `${pct}%`, height: "100%", background: barColor, borderRadius: 4, transition: "width 200ms" }} />
                {/* 임계선 표시 */}
                <div style={{
                    position: "absolute", left: `${threshold}%`, top: -2, bottom: -2,
                    width: 2, background: C.textPrimary, opacity: 0.6,
                }} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: T.cap, color: C.textTertiary, ...MONO }}>
                <span>0</span>
                <span>발행 임계 {threshold}</span>
                <span>100</span>
            </div>
        </div>
    )
}


/* ◆ INTERNAL: DivergenceWarnings (LANDEX-GEI-거래량 다이버전스 경고) ◆ */
function DivergenceWarnings({ warnings }: { warnings: DivergenceWarning[] }) {
    if (warnings.length === 0) return null
    return (
        <div style={{
            padding: S.md, backgroundColor: C.warn + "1A",
            border: `1px solid ${C.warn}`, borderRadius: R.sm,
            display: "flex", flexDirection: "column", gap: S.xs,
        }}>
            <span style={{ fontSize: T.cap, color: C.warn, fontWeight: T.w_semi, textTransform: "uppercase", letterSpacing: 1 }}>
                ⚠️ 다이버전스 경고 ({warnings.length})
            </span>
            {warnings.map((w, i) => (
                <span key={i} style={{ fontSize: T.cap, color: C.textSecondary, lineHeight: 1.5 }}>
                    · {w.message}
                </span>
            ))}
        </div>
    )
}


/* ◆ INTERNAL: ChecklistCard (9개 — Data/Logic/UX 카테고리별 그룹) ◆ */
const CATEGORY_LABEL: Record<CheckCategory, string> = {
    data: "Data Integrity",
    logic: "Logical Consistency",
    ux: "UX & Legal",
}

function ChecklistCard({ checks, hideReasons, onRetryCheck }: {
    checks: DilutionCheckItem[]
    hideReasons: boolean
    onRetryCheck?: () => void
}) {
    const passed = checks.filter((c) => c.passed).length
    const total = checks.length
    const allPass = passed === total
    const grouped: Record<CheckCategory, DilutionCheckItem[]> = { data: [], logic: [], ux: [] }
    checks.forEach((c) => { grouped[c.category]?.push(c) })

    return (
        <section style={{
            padding: S.lg, backgroundColor: C.bgCard,
            border: `1px solid ${C.border}`, borderRadius: R.md,
            display: "flex", flexDirection: "column", gap: S.md,
        }}>
            <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontSize: T.sub, fontWeight: T.w_semi, color: C.textPrimary }}>
                    ✅ Publish Readiness
                </span>
                <span style={{
                    fontSize: T.cap, color: allPass ? C.statusPos : C.warn,
                    fontWeight: T.w_semi, ...MONO,
                }}>{passed} / {total}</span>
            </header>

            {(["data", "logic", "ux"] as CheckCategory[]).map((cat) => {
                const items = grouped[cat]
                if (items.length === 0) return null
                return (
                    <div key={cat} style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                        <span style={{
                            fontSize: T.cap, color: C.textTertiary, fontWeight: T.w_semi,
                            textTransform: "uppercase", letterSpacing: 1,
                        }}>{CATEGORY_LABEL[cat]}</span>
                        <ul style={{
                            listStyle: "none", margin: 0, padding: 0,
                            display: "flex", flexDirection: "column", gap: S.xs,
                        }}>
                            {items.map((c) => (
                                <li key={c.id} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                                    <div style={{ display: "flex", alignItems: "center", gap: S.sm }}>
                                        <span aria-hidden style={{
                                            display: "inline-flex", alignItems: "center", justifyContent: "center",
                                            width: 18, height: 18, borderRadius: "50%",
                                            background: c.passed ? C.statusPos : C.statusNeg,
                                            color: C.bgPage,
                                            fontSize: 11, fontWeight: T.w_bold, flexShrink: 0,
                                        }}>{c.passed ? "✓" : "✕"}</span>
                                        <span style={{
                                            fontSize: T.body,
                                            color: c.passed ? C.textPrimary : C.statusNeg,
                                            fontWeight: c.passed ? T.w_med : T.w_semi,
                                        }}>{c.label}</span>
                                    </div>
                                    {!c.passed && c.reason && !hideReasons && (
                                        <span style={{
                                            marginLeft: 26, fontSize: T.cap, color: C.textSecondary,
                                            fontFamily: FONT_MONO, lineHeight: 1.5,
                                        }}>{c.reason}</span>
                                    )}
                                </li>
                            ))}
                        </ul>
                    </div>
                )
            })}

            <div style={{
                padding: `${S.sm}px ${S.md}px`, borderRadius: R.sm,
                background: allPass ? C.statusPos + "22" : C.statusNeg + "22",
                color: allPass ? C.statusPos : C.statusNeg,
                fontSize: T.body, fontWeight: T.w_semi, textAlign: "center",
            }}>
                {allPass ? "✓ 발행 가능" : `${total - passed}개 항목 미통과`}
            </div>

            {!allPass && onRetryCheck && (
                <button
                    onClick={onRetryCheck}
                    style={{
                        padding: `${S.sm}px ${S.md}px`,
                        background: "transparent", color: C.textSecondary,
                        border: `1px solid ${C.border}`, borderRadius: R.sm,
                        fontSize: T.cap, fontFamily: FONT, cursor: "pointer",
                    }}
                >재검사</button>
            )}
        </section>
    )
}


/* ◆ INTERNAL: PublishActions ◆ */
function PublishActions({ enabled, status, onSchedule, onPublish }: {
    enabled: boolean
    status: PublishStatus
    onSchedule: () => void
    onPublish: () => void
}) {
    return (
        <section style={{
            padding: S.lg, backgroundColor: C.bgCard,
            border: `1px solid ${C.border}`, borderRadius: R.md,
            display: "flex", flexDirection: "column", gap: S.md,
        }}>
            <span style={{ fontSize: T.sub, fontWeight: T.w_semi, color: C.textPrimary }}>발행</span>
            {status !== "idle" && (
                <div style={{
                    padding: S.sm, borderRadius: R.sm,
                    background: status === "published" ? C.statusPos + "22"
                              : status === "scheduled" ? C.info + "22"
                              : C.statusNeg + "22",
                    color: status === "published" ? C.statusPos
                         : status === "scheduled" ? C.info
                         : C.statusNeg,
                    fontSize: T.cap, fontWeight: T.w_med,
                }}>
                    {status === "published" && "✓ 즉시 발행됨"}
                    {status === "scheduled" && "✓ 발행 예약 완료"}
                    {status === "error" && "× 발행 실패 — 재시도"}
                </div>
            )}
            <div style={{ display: "flex", gap: S.sm }}>
                <button
                    disabled={!enabled} onClick={onSchedule}
                    style={btnStyle(enabled, "secondary")}
                >발행 예약</button>
                <button
                    disabled={!enabled} onClick={onPublish}
                    style={btnStyle(enabled, "primary")}
                >즉시 발행</button>
            </div>
            {!enabled && (
                <span style={{ fontSize: T.cap, color: C.textTertiary, textAlign: "center" }}>
                    체크리스트 통과 후 활성화
                </span>
            )}
        </section>
    )
}

function btnStyle(enabled: boolean, variant: "primary" | "secondary"): React.CSSProperties {
    const base: React.CSSProperties = {
        flex: 1, padding: `${S.sm}px ${S.md}px`,
        borderRadius: R.sm,
        fontSize: T.body, fontWeight: T.w_semi, fontFamily: FONT,
        cursor: enabled ? "pointer" : "not-allowed",
        opacity: enabled ? 1 : 0.4,
        border: `1px solid ${C.border}`,
        transition: X.base,
    }
    if (variant === "primary") {
        return {
            ...base,
            background: enabled ? C.accent : C.bgElevated,
            color: enabled ? C.bgPage : C.textTertiary,
            borderColor: enabled ? C.accent : C.border,
        }
    }
    return { ...base, background: "transparent", color: C.textPrimary }
}


/* ◆ INTERNAL: PreviewCard (공개 카드 미리보기) ◆ */
function PreviewCard({ preview }: { preview: DigestPreview }) {
    return (
        <article style={{
            padding: S.xl, backgroundColor: C.bgCard,
            border: `1px solid ${C.border}`, borderRadius: R.md,
            display: "flex", flexDirection: "column", gap: S.md,
        }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: S.md }}>
                <div style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                    <span style={{ fontSize: T.cap, color: C.textTertiary, textTransform: "uppercase", letterSpacing: 1 }}>
                        Public Digest 미리보기
                    </span>
                    <h2 style={{ margin: 0, fontSize: T.h2, fontWeight: T.w_bold, color: C.textPrimary }}>{preview.title}</h2>
                </div>
                <span style={{ fontSize: T.cap, color: C.textSecondary, ...MONO }}>{preview.period}</span>
            </div>

            <p style={{
                margin: 0, padding: S.md,
                background: C.bgElevated, borderRadius: R.sm,
                fontSize: T.body, color: C.textPrimary, lineHeight: 1.6,
                borderLeft: `3px solid ${C.accent}`,
            }}>{preview.summary}</p>

            <div style={{ display: "flex", flexDirection: "column", gap: S.md }}>
                {preview.sections.map((sec, i) => (
                    <div key={i} style={{ display: "flex", flexDirection: "column", gap: S.xs }}>
                        <h3 style={{
                            margin: 0, fontSize: T.sub, fontWeight: T.w_semi,
                            color: C.accent,
                        }}>{sec.heading}</h3>
                        <p style={{
                            margin: 0, fontSize: T.body, color: C.textSecondary,
                            lineHeight: 1.6,
                        }}>{sec.body}</p>
                    </div>
                ))}
            </div>

            <div style={{
                padding: S.md, marginTop: S.sm,
                background: C.bgElevated, borderRadius: R.sm,
                borderLeft: `3px solid ${C.warn}`,
            }}>
                <span style={{
                    display: "block", fontSize: T.cap, color: C.warn,
                    fontWeight: T.w_semi, marginBottom: S.xs, textTransform: "uppercase", letterSpacing: 1,
                }}>주의 문구</span>
                <ul style={{ margin: 0, padding: 0, paddingLeft: S.lg, listStyle: "disc", display: "flex", flexDirection: "column", gap: S.xs }}>
                    {preview.publicNotes.map((n, i) => (
                        <li key={i} style={{ fontSize: T.cap, color: C.textTertiary, lineHeight: 1.5 }}>{n}</li>
                    ))}
                </ul>
            </div>
        </article>
    )
}


/* ◆ MAIN ◆ */
type PublishStatus = "idle" | "scheduled" | "published" | "error"

interface Props {
    apiUrl: string
    /** 미통과 사유 숨김 (외부 데모용) */
    hideReasons: boolean
}

function DigestPublishPanel({ apiUrl = "", hideReasons = false }: Props) {
    const [readiness, setReadiness] = useState<PublishReadiness>({
        checks: MOCK_CHECKS, warnings: MOCK_WARNINGS,
        confidenceScore: 67, publishThreshold: 80, readyToPublish: false,
        preview: MOCK_PREVIEW,
    })
    const [loading, setLoading] = useState(false)
    const [status, setStatus] = useState<PublishStatus>("idle")

    useEffect(() => {
        const ac = new AbortController()
        setLoading(true)
        fetchPublishData(apiUrl, ac.signal)
            .then((r) => { setReadiness(r); setLoading(false) })
            .catch(() => setLoading(false))
        return () => ac.abort()
    }, [apiUrl])

    const { checks, warnings, confidenceScore, publishThreshold, readyToPublish, preview } = readiness

    const handleSchedule = () => {
        if (!readyToPublish) return
        setStatus("scheduled")
    }
    const handlePublish = () => {
        if (!readyToPublish) return
        setStatus("published")
    }
    const handleRetryCheck = () => {
        // 시연용: 첫 번째 미통과 항목을 통과로 + Confidence 재계산
        setReadiness((cur) => {
            const idx = cur.checks.findIndex((c) => !c.passed)
            if (idx < 0) return cur
            const nextChecks = [...cur.checks]
            nextChecks[idx] = { ...nextChecks[idx], passed: true, reason: undefined }
            const passedCount = nextChecks.filter((c) => c.passed).length
            const base = (passedCount / nextChecks.length) * 100
            const penalty = cur.warnings.length * 15
            const score = Math.max(0, base - penalty)
            return {
                ...cur,
                checks: nextChecks,
                confidenceScore: Math.round(score * 100) / 100,
                readyToPublish: score >= cur.publishThreshold,
            }
        })
    }

    return (
        <div style={{
            width: "100%", height: "100%", display: "flex", flexDirection: "column", gap: S.md, padding: S.md,
            backgroundColor: C.bgPage, fontFamily: FONT, color: C.textPrimary,
            boxSizing: "border-box", minWidth: 960, minHeight: 600, overflowY: "auto",
        }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: S.md }}>
                    <span style={{ fontSize: T.h2, fontWeight: T.w_bold, color: C.textPrimary }}>Digest 발행</span>
                    <span style={{ fontSize: T.body, color: C.textSecondary }}>· {preview.period}</span>
                </div>
                {loading && <span style={{ fontSize: T.cap, color: C.info, ...MONO }}>· 로딩 중</span>}
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: S.md, flex: 1, minHeight: 0 }}>
                <PreviewCard preview={preview} />
                <div style={{ display: "flex", flexDirection: "column", gap: S.md }}>
                    <ConfidenceGauge score={confidenceScore} threshold={publishThreshold} />
                    <DivergenceWarnings warnings={warnings} />
                    <ChecklistCard checks={checks} hideReasons={hideReasons} onRetryCheck={handleRetryCheck} />
                    <PublishActions
                        enabled={readyToPublish} status={status}
                        onSchedule={handleSchedule} onPublish={handlePublish}
                    />
                </div>
            </div>
        </div>
    )
}

addPropertyControls(DigestPublishPanel, {
    apiUrl: { type: ControlType.String, defaultValue: "", description: "Publish API base URL. 비우면 mock." },
    hideReasons: {
        type: ControlType.Boolean, defaultValue: false,
        description: "체크 미통과 사유 숨김 (외부 데모용)",
    },
})

export default DigestPublishPanel
