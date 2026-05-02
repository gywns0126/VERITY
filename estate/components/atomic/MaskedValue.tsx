// MaskedValue — 민감 수치·문자열 자동 마스킹
// SHARED — TERMINAL과 완전 공유. 1급 시설 (dilution-rules.md 구현 핵심).
//
// sensitivity prop이 L1 이상이고 전역 Privacy Mode가 ON이면 자동 마스킹.
// defaultMasked=true 면 처음부터 가려진 상태로 시작, 클릭 시 n초 한시 해제 후 재마스킹.

import React, { useCallback, useEffect, useState } from "react"
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

/* ◆ PRIVACY HOOK START ◆ (Context 대신 window 이벤트 브리지 — Framer 단일 파일 제약) */
function usePrivacyMode() {
    const [privacyMode, _setPM] = useState(() =>
        typeof window !== "undefined" && (window as any).__VERITY_PRIVACY__ === true
    )
    useEffect(() => {
        if (typeof window === "undefined") return
        const onChange = () => _setPM((window as any).__VERITY_PRIVACY__ === true)
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
    const togglePrivacy = () => {
        if (typeof window === "undefined") return
        ;(window as any).__VERITY_PRIVACY__ = !((window as any).__VERITY_PRIVACY__ === true)
        window.dispatchEvent(new Event("verity:privacy-change"))
    }
    const setPrivacy = (v: boolean) => {
        if (typeof window === "undefined") return
        ;(window as any).__VERITY_PRIVACY__ = v
        window.dispatchEvent(new Event("verity:privacy-change"))
    }
    const shouldMask = (s: SensitivityLevel) => s !== "L0" && privacyMode
    return { privacyMode, togglePrivacy, setPrivacy, shouldMask }
}
/* ◆ PRIVACY HOOK END ◆ */
type MaskedFormat = "text" | "number" | "percent" | "currency"

export interface MaskedValueProps {
  value: string | number
  sensitivity: SensitivityLevel
  format?: MaskedFormat
  /** 초기 마스킹 상태 (Privacy Mode와 별개, 컴포넌트 로컬 기본값) */
  defaultMasked?: boolean
  /** 클릭으로 한시 해제 가능 여부 */
  unmaskOnClick?: boolean
  /** 해제 지속 시간(ms). 0 = 영구 해제 */
  unmaskDuration?: number
  /** 자리수 고정 (숫자 마스킹 시 실제 길이 추론 방지) */
  fixedWidth?: number
  /** 폰트 variant */
  font?: "mono" | "body"
  style?: React.CSSProperties
}

function formatValue(value: string | number, format: MaskedFormat): string {
  if (typeof value === "string") return value
  switch (format) {
    case "percent":
      return `${value.toFixed(1)}%`
    case "currency":
      return `₩${value.toLocaleString()}`
    case "number":
      return value.toLocaleString()
    default:
      return String(value)
  }
}

function maskText(text: string, fixedWidth?: number): string {
  if (fixedWidth && fixedWidth > 0) {
    return "●".repeat(fixedWidth)
  }
  return text.replace(/\S/g, "●")
}

function MaskedValue({
  value,
  sensitivity,
  format = "text",
  defaultMasked = false,
  unmaskOnClick = true,
  unmaskDuration = 30000,
  fixedWidth,
  font = "mono",
  style,
}: MaskedValueProps) {
  const { shouldMask } = usePrivacyMode()
  const [locallyUnmasked, setLocallyUnmasked] = useState<boolean>(!defaultMasked)

  const globalForceMask = shouldMask(sensitivity)
  const masked = globalForceMask || !locallyUnmasked

  useEffect(() => {
    if (!defaultMasked) return
    if (!locallyUnmasked) return
    if (unmaskDuration <= 0) return
    const t = setTimeout(() => setLocallyUnmasked(false), unmaskDuration)
    return () => clearTimeout(t)
  }, [locallyUnmasked, unmaskDuration, defaultMasked])

  const handleClick = useCallback(() => {
    if (!unmaskOnClick) return
    if (globalForceMask) return // 전역 Privacy Mode가 ON이면 로컬 해제 무시
    setLocallyUnmasked((v) => !v)
  }, [unmaskOnClick, globalForceMask])

  const formatted = formatValue(value, format)
  const display = masked ? maskText(formatted, fixedWidth) : formatted
  const canInteract = unmaskOnClick && !globalForceMask

  return (
    <span
      role={canInteract ? "button" : undefined}
      tabIndex={canInteract ? 0 : undefined}
      aria-label={masked ? "masked value" : undefined}
      onClick={handleClick}
      onKeyDown={(e) => {
        if (!canInteract) return
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          handleClick()
        }
      }}
      style={{
        fontFamily:
          font === "mono" ? typography.fontFamily.mono : typography.fontFamily.body,
        color: masked ? colors.text.tertiary : colors.text.primary,
        cursor: canInteract ? "pointer" : "default",
        userSelect: masked ? "none" : "text",
        transition: "color 200ms",
        letterSpacing: masked ? 1 : 0,
        display: "inline",
        ...style,
      }}
    >
      {display}
    </span>
  )
}

addPropertyControls(MaskedValue, {
  value: { type: ControlType.String, defaultValue: "87.3" },
  sensitivity: {
    type: ControlType.Enum,
    options: ["L0", "L1", "L2", "L3"],
    defaultValue: "L2",
  },
  format: {
    type: ControlType.Enum,
    options: ["text", "number", "percent", "currency"],
    defaultValue: "text",
  },
  defaultMasked: { type: ControlType.Boolean, defaultValue: false },
  unmaskOnClick: { type: ControlType.Boolean, defaultValue: true },
  unmaskDuration: { type: ControlType.Number, defaultValue: 30000, min: 0, max: 600000 },
  fixedWidth: { type: ControlType.Number, defaultValue: 0, min: 0, max: 40 },
  font: {
    type: ControlType.Enum,
    options: ["mono", "body"],
    defaultValue: "mono",
  },
})

export default MaskedValue
