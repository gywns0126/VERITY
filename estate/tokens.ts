// VERITY ESTATE Design Tokens
// TERMINAL(Neo Dark Terminal) 디자인 규격 + ESTATE 골드 액센트 차별화(B안).
// 배경/텍스트/보더/폰트/모션은 TERMINAL과 동일한 시각 언어.
// accent.estate(골드)만 부동산 섹터 식별용으로 별도.
// 모든 컴포넌트는 이 파일의 값만 참조한다. 직접 hex 값 사용 금지.

export const colors = {
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

export const typography = {
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

export const spacing = {
  s1: 4,
  s2: 8,
  s3: 12,
  s4: 16,
  s5: 24,
  s6: 32,
  s8: 48,
  s10: 64,
} as const

export const radius = {
  sm: 6,
  md: 10,
  lg: 14,
  xl: 16,
  full: 9999,
} as const

export const shadow = {
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

export const motion = {
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
export type GradeLabel = "HOT" | "WARM" | "NEUT" | "COOL" | "AVOID"
export type StageLevel = 0 | 1 | 2 | 3 | 4
export type CategoryId = "gei" | "catalyst" | "regulation" | "anomaly"
export type Severity = "high" | "mid" | "low"
export type SensitivityLevel = "L0" | "L1" | "L2" | "L3"
export type StatusKind = "positive" | "neutral" | "negative"

// Stage → public label mapping (from dilution-rules.md § 3.2)
export const stagePublicLabel: Record<StageLevel, string | null> = {
  0: null, // Stage 0은 언급 안 함
  1: "관심 구간",
  2: "가속 신호",
  3: "과열 구간",
  4: "조정 신호",
}

// Grade → public comment tone (from scoring-landex.md § 5)
export const gradePublicComment: Record<GradeLabel, string> = {
  HOT: "강한 진입 신호",
  WARM: "주목할 흐름",
  NEUT: "중립",
  COOL: "관망",
  AVOID: "주의 구간",
}
