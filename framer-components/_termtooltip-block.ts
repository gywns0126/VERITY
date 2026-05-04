/**
 * VERITY Framer TermTooltip 인라인 블록 (마스터)
 *
 * Framer Code Components 는 단일 파일 제약으로 import 불가.
 * 각 컴포넌트는 본 파일의 ◆MARKER◆ 사이 블록을 그대로 인라인 복붙.
 * 본 파일 자체는 Framer 에 등록하지 않음 (참조용 마스터).
 *
 * 패턴 출처: estate/components/pages/home/LandexPulse.tsx 의 TermTooltip 검증된 구현
 * 용어 마스터: data/verity_terms.json (사전, l3 flag 등)
 *
 * 사용 시:
 *   1) 컴포넌트 상단 디자인 토큰 블록 직후에 ◆ TERMS START ◆ ~ ◆ TERMS END ◆ 복붙
 *   2) 각 컴포넌트는 자기가 쓰는 termKey subset 만 TERMS 객체에 포함
 *      (전체 사전 다 박을 필요 X — Framer bundle size 절감)
 *   3) JSX 안에서 <TermTooltip termKey="FACT_SCORE">Fact Score</TermTooltip> 형태로 감쌈
 *
 * 주의:
 *   - C / R / FONT / FONT_SERIF 은 디자인 토큰 블록의 변수 (이미 인라인되어 있어야 함)
 *   - useState, useRef 는 React 에서 import (이미 모든 Framer 컴포넌트에 있음)
 */

/* ──────────────────────────────────────────────────────────────
 * ◆ TERMS START ◆ (각 컴포넌트는 자기 termKey subset 만 박음)
 * 마스터 사전: data/verity_terms.json 에서 발췌
 * ────────────────────────────────────────────────────────────── */

interface Term {
    label: string
    category?: "metric" | "grade" | "signal" | "concept" | "data_source" | "internal" | "time"
    definition: string
    stages?: Record<string, string>
    values?: Record<string, string>
    l3?: boolean
}

const TERMS: Record<string, Term> = {
    /* 예시 — 각 컴포넌트는 자기가 쓰는 항목만 발췌 복붙 */
    FACT_SCORE: {
        label: "Fact Score", category: "metric",
        definition: "객관적 수치 기반 종합 점수 (0~100). 13 sub-score 가중 평균.",
    },
    GRADE_STRONG_BUY: {
        label: "강력매수", category: "grade",
        definition: "최상위 등급. fact_score ≥ 75 + multi-factor 일관 양성.",
    },
    /* ... data/verity_terms.json 의 필요 키만 발췌 ... */
}

/* ◆ TERMS END ◆ */


/* ──────────────────────────────────────────────────────────────
 * ◆ TERMTOOLTIP START ◆ (그대로 복붙)
 * 의존: React useState/useRef, 디자인 토큰 (C/R/FONT)
 * ────────────────────────────────────────────────────────────── */

function TermTooltip({ termKey, children }: { termKey: string; children: React.ReactNode }) {
    const [show, setShow] = useState(false)
    const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
    const anchorRef = useRef<HTMLSpanElement>(null)
    const term = TERMS[termKey]
    if (!term) return <>{children}</>

    const TIP_W = 320
    const TIP_H = 160

    const handleEnter = () => {
        const el = anchorRef.current
        if (!el || typeof window === "undefined") {
            setShow(true)
            return
        }
        const rect = el.getBoundingClientRect()
        const vw = window.innerWidth
        const vh = window.innerHeight
        const margin = 8

        // x: 좌측 정렬 default. 우측 공간 부족 시 우측 정렬 (좌로 확장)
        let left = rect.left
        if (left + TIP_W + margin > vw) {
            left = Math.max(margin, rect.right - TIP_W)
        }
        // y: 아래 default. 하단 공간 부족 시 위로
        let top = rect.bottom + 6
        if (top + TIP_H + margin > vh) {
            top = Math.max(margin, rect.top - TIP_H - 6)
        }
        setPos({ top, left })
        setShow(true)
    }
    const handleLeave = () => {
        setShow(false)
        setPos(null)
    }

    return (
        <span
            ref={anchorRef}
            onMouseEnter={handleEnter}
            onMouseLeave={handleLeave}
            onFocus={handleEnter}
            onBlur={handleLeave}
            tabIndex={0}
            style={{
                position: "relative",
                display: "inline-block",
                borderBottom: `1px dotted ${C.textTertiary}`,
                cursor: "help",
                outline: "none",
            }}
        >
            {children}
            {show && pos && (
                <div
                    style={{
                        position: "fixed",
                        top: pos.top,
                        left: pos.left,
                        width: TIP_W,
                        zIndex: 100,
                        padding: "10px 12px",
                        borderRadius: R.md,
                        background: C.bgElevated,
                        border: `1px solid ${C.borderStrong}`,
                        boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                        fontFamily: FONT,
                        fontSize: 12,
                        lineHeight: 1.5,
                        whiteSpace: "normal",
                        pointerEvents: "none",
                    }}
                >
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                        <span style={{ color: C.textPrimary, fontWeight: 700, fontSize: 13 }}>
                            {term.label}
                        </span>
                        {term.l3 && (
                            <span
                                style={{
                                    color: C.accent,
                                    fontSize: 9,
                                    letterSpacing: "1.5px",
                                    fontWeight: 800,
                                    textTransform: "uppercase",
                                    padding: "1px 6px",
                                    borderRadius: R.pill,
                                    border: `1px solid ${C.accent}60`,
                                }}
                            >
                                L3
                            </span>
                        )}
                    </div>
                    <div style={{ color: C.textSecondary }}>{term.definition}</div>
                    {term.stages && (
                        <div style={{ marginTop: 6, paddingTop: 6, borderTop: `1px solid ${C.border}` }}>
                            {Object.entries(term.stages).map(([k, v]) => (
                                <div key={k} style={{ fontSize: 11, color: C.textTertiary }}>
                                    <span style={{ fontWeight: 600, color: C.textSecondary }}>{k}</span>{" "}
                                    {v}
                                </div>
                            ))}
                        </div>
                    )}
                    {term.values && (
                        <div style={{ marginTop: 6, paddingTop: 6, borderTop: `1px solid ${C.border}` }}>
                            {Object.entries(term.values).map(([k, v]) => (
                                <div key={k} style={{ fontSize: 11, color: C.textTertiary }}>
                                    <span style={{ fontWeight: 600, color: C.textSecondary }}>{k}</span>{" "}
                                    {v}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </span>
    )
}

/* ◆ TERMTOOLTIP END ◆ */
