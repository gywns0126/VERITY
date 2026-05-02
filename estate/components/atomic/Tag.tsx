// Tag — 카테고리·severity·status·grade·stage 통합 태그 (Badge + LabelPill 통합)
// SHARED (enum) — 5 variants (category|severity|status|grade|stage).

import React from "react"
import { addPropertyControls, ControlType } from "framer"

/* ◆ TOKENS START ◆ (tokens.ts 인라인 — 마스터는 /tokens.ts) */
const colors = {
  bg: {
    // TERMINAL 규격: 깊이별 배경 3단계 (푸른 기 미세, 검정에 가까움)
    primary: "#0E0F11",   // 페이지 배경 (TERMINAL bgPage)
    secondary: "#171820", // 기본 카드/패널 (TERMINAL bgCard)
    tertiary: "#22232B",  // 강조 카드/모달/hover (TERMINAL bgElevated)
  },
  border: {
    // TERMINAL 규격
    default: "#23242C",   // 평상시
    strong: "#34353D",    // 탭 active / 강조 구분선
  },
  text: {
    // TERMINAL 규격: 4단계 위계
    primary: "#F2F3F5",   // 본문/숫자 (흰색에 가까움)
    secondary: "#A8ABB2", // 보조/라벨
    tertiary: "#6B6E76",  // 캡션/메타/단위
    disabled: "#4A4C52",  // 비활성
  },
  accent: {
    // ESTATE 골드 — 부동산 섹터 식별 (TERMINAL 네온그린 #B5FF19 과 의도적 차별화)
    estate: "#B8864D",
    estateHover: "#D4A063",
    estateMuted: "rgba(184,134,77,0.12)",  // focus ring / 배경 강조
    // TERMINAL 참조 색 (교차 링크용)
    terminal: "#B5FF19",
  },
  grade: {
    // LANDEX 등급 — TERMINAL Tailwind 팔레트와 동톤
    HOT: "#EF4444",   // 강한 경고·뜨거움 (TERMINAL avoid 톤)
    WARM: "#F59E0B",  // 주의·주목 (TERMINAL caution 톤)
    NEUT: "#A8ABB2",  // 중립 (TERMINAL textSecondary 톤)
    COOL: "#5BA9FF",  // 관망 (TERMINAL info 톤)
    AVOID: "#6B6E76", // 회피 (TERMINAL textTertiary 톤)
  },
  stage: {
    // GEI Stage — 강도 단계 (투명→경고→위험→심각)
    0: "transparent",
    1: "#FFD600",  // TERMINAL watch
    2: "#F59E0B",  // TERMINAL caution
    3: "#EF4444",  // TERMINAL danger
    4: "#9B59B6",  // 자극 최대 (보라 유지 — 시각적 차별)
  },
  stageAlpha: {
    0: 0,
    1: 0.3,
    2: 0.5,
    3: 0.6,
    4: 0.7,
  },
  category: {
    // 알림 카테고리 — TERMINAL 팔레트 정렬
    gei: "#EF4444",        // danger
    catalyst: "#F59E0B",   // caution
    regulation: "#9B59B6", // 보라 (규제 식별)
    anomaly: "#5BA9FF",    // info
  },
  status: {
    // TERMINAL semantic 과 동일
    positive: "#22C55E",
    neutral: "#A8ABB2",
    negative: "#EF4444",
  },
} as const

const typography = {
  fontFamily: {
    // TERMINAL 규격
    display: "'Pretendard', 'Inter', -apple-system, sans-serif",
    body: "'Pretendard', 'Inter', -apple-system, sans-serif",
    mono: "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace",
  },
  size: {
    xs: 11,
    sm: 13,
    base: 14,
    md: 16,
    lg: 20,
    xl: 24,
    "2xl": 32,
    "3xl": 44,
  },
  lineHeight: {
    xs: 16,
    sm: 20,
    base: 22,
    md: 24,
    lg: 28,
    xl: 32,
    "2xl": 40,
    "3xl": 52,
  },
  weight: {
    regular: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
  },
} as const

const spacing = {
  s1: 4,
  s2: 8,
  s3: 12,
  s4: 16,
  s5: 24,
  s6: 32,
  s8: 48,
  s10: 64,
} as const

const radius = {
  sm: 6,
  md: 10,
  lg: 14,
  xl: 16,
  full: 9999,
} as const

const shadow = {
  // TERMINAL GLOW + 일반 shadow 혼합 — ESTATE 골드 글로우 포함
  sm: "0 1px 2px rgba(0,0,0,0.2)",
  md: "0 4px 8px rgba(0,0,0,0.3)",
  lg: "0 8px 24px rgba(0,0,0,0.4)",
  // 골드 글로우 — ESTATE CTA/hover 강조용
  glowEstate: "0 0 8px rgba(184,134,77,0.35)",
  glowEstateSoft: "0 0 4px rgba(184,134,77,0.20)",
  glowEstateStrong: "0 0 12px rgba(184,134,77,0.50)",
  glowDanger: "0 0 6px rgba(239,68,68,0.30)",
} as const

const motion = {
  easing: {
    // TERMINAL "ease" 보다 구체적인 cubic-bezier 유지 (ESTATE 기존 패턴)
    standard: "cubic-bezier(0.4, 0, 0.2, 1)",
    enter: "cubic-bezier(0.0, 0, 0.2, 1)",
    exit: "cubic-bezier(0.4, 0, 1, 1)",
  },
  duration: {
    fast: 120,
    base: 180,  // TERMINAL "base" 와 정렬 (기존 200 → 180)
    slow: 240,  // TERMINAL "slow" 와 정렬 (기존 320 → 240)
  },
} as const

// Type exports
type GradeLabel = "HOT" | "WARM" | "NEUT" | "COOL" | "AVOID"
type StageLevel = 0 | 1 | 2 | 3 | 4
type CategoryId = "gei" | "catalyst" | "regulation" | "anomaly"
type Severity = "high" | "mid" | "low"
type SensitivityLevel = "L0" | "L1" | "L2" | "L3"
type StatusKind = "positive" | "neutral" | "negative"

// Stage → public label mapping (from dilution-rules.md § 3.2)
const stagePublicLabel: Record<StageLevel, string | null> = {
  0: null, // Stage 0은 언급 안 함
  1: "관심 구간",
  2: "가속 신호",
  3: "과열 구간",
  4: "조정 신호",
}

// Grade → public comment tone (from scoring-landex.md § 5)
const gradePublicComment: Record<GradeLabel, string> = {
  HOT: "강한 진입 신호",
  WARM: "주목할 흐름",
  NEUT: "중립",
  COOL: "관망",
  AVOID: "주의 구간",
}
/* ◆ TOKENS END ◆ */
export type TagVariant =
  | "category"
  | "severity"
  | "status"
  | "grade"
  | "stage"

export type TagSize = "sm" | "md" | "lg"

export interface TagProps {
  /** 태그 종류 */
  variant: TagVariant
  /** variant 별 enum 값 (런타임 string)
   *  - category: gei | catalyst | regulation | anomaly
   *  - severity: high | mid | low
   *  - status:   positive | neutral | negative
   *  - grade:    HOT | WARM | NEUT | COOL | AVOID
   *  - stage:    0 | 1 | 2 | 3 | 4
   */
  value: string
  /** 라벨 override (없으면 variant 기본 라벨) */
  label?: string
  /** 아이콘 override (없으면 variant 기본 아이콘) */
  icon?: string
  size?: TagSize
}

/* ── variant 별 맵 ── */
const categoryIcon: Record<CategoryId, string> = {
  gei: "🔴",
  catalyst: "🟡",
  regulation: "🟣",
  anomaly: "🔵",
}
const categoryLabel: Record<CategoryId, string> = {
  gei: "GEI",
  catalyst: "Catalyst",
  regulation: "Regulation",
  anomaly: "Anomaly",
}
const severityLabel: Record<Severity, string> = {
  high: "높음",
  mid: "중간",
  low: "낮음",
}
const severityColor: Record<Severity, string> = {
  high: colors.status.negative,
  mid: colors.accent.estate,
  low: colors.text.secondary,
}
const statusColor: Record<StatusKind, string> = {
  positive: colors.status.positive,
  neutral: colors.status.neutral,
  negative: colors.status.negative,
}
const stageLabel: Record<StageLevel, string> = {
  0: "Stage 0",
  1: "Stage 1",
  2: "Stage 2",
  3: "Stage 3",
  4: "Stage 4",
}

const sizeStyles: Record<TagSize, { padY: number; padX: number; font: number }> = {
  sm: { padY: 2, padX: 6, font: typography.size.xs },
  md: { padY: 4, padX: 10, font: typography.size.sm },
  lg: { padY: 6, padX: 12, font: typography.size.base },
}

type Resolved = { bg: string; fg: string; text: string; pre?: string; weight: number }

function resolve(variant: TagVariant, value: string): Resolved {
  const w = typography.weight
  if (variant === "category") {
    const v = value as CategoryId
    const c = colors.category[v] ?? colors.text.secondary
    return { bg: `${c}1A`, fg: c, text: categoryLabel[v] ?? value, pre: categoryIcon[v], weight: w.medium }
  }
  if (variant === "severity") {
    const v = value as Severity
    const c = severityColor[v] ?? colors.text.secondary
    return { bg: `${c}1A`, fg: c, text: severityLabel[v] ?? value, weight: w.medium }
  }
  if (variant === "status") {
    const v = value as StatusKind
    const c = statusColor[v] ?? colors.text.secondary
    return { bg: `${c}1A`, fg: c, text: value, weight: w.medium }
  }
  if (variant === "grade") {
    const v = value as GradeLabel
    const c = colors.grade[v] ?? colors.text.secondary
    return { bg: `${c}1A`, fg: c, text: v, weight: w.semibold }
  }
  // stage
  const n = (typeof value === "number" ? value : parseInt(value as string, 10)) as StageLevel
  const c = colors.stage[n]
  const transparent = n === 0
  return {
    bg: transparent ? colors.bg.tertiary : `${c}26`,
    fg: transparent ? colors.text.secondary : c,
    text: stageLabel[n] ?? `Stage ${value}`,
    weight: w.semibold,
  }
}

function Tag({ variant, value, label, icon, size = "md" }: TagProps) {
  const r = resolve(variant, value)
  const sz = sizeStyles[size]

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: spacing.s1,
        backgroundColor: r.bg,
        color: r.fg,
        padding: `${sz.padY}px ${sz.padX}px`,
        borderRadius: radius.sm,
        fontSize: sz.font,
        fontWeight: r.weight,
        fontFamily: typography.fontFamily.body,
        lineHeight: 1,
        letterSpacing: variant === "grade" || variant === "stage" ? 0.2 : 0,
        whiteSpace: "nowrap",
      }}
    >
      {icon ?? r.pre}
      {label ?? r.text}
    </span>
  )
}

addPropertyControls(Tag, {
  variant: {
    type: ControlType.Enum,
    options: ["category", "severity", "status", "grade", "stage"],
    defaultValue: "category",
  },
  value: {
    type: ControlType.String,
    defaultValue: "gei",
    description:
      "category: gei/catalyst/regulation/anomaly · severity: high/mid/low · status: positive/neutral/negative · grade: HOT/WARM/NEUT/COOL/AVOID · stage: 0~4",
  },
  label: { type: ControlType.String, defaultValue: "" },
  icon: { type: ControlType.String, defaultValue: "" },
  size: {
    type: ControlType.Enum,
    options: ["sm", "md", "lg"],
    defaultValue: "md",
  },
})

export default Tag
