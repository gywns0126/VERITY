// dilutionFilter — 공개 발행 전 6항목 자동 검증
// ESTATE-ONLY.
//
// dilution-rules.md § 5.2 발행 전 체크리스트 구현:
//   1. 원점수·수치 없음
//   2. combination guard (같은 구 LANDEX + GEI 동시 금지)
//   3. 지역 4주 간격
//   4. VAMS 참조 없음
//   5. 가중치 누출 없음
//   6. 임계치 누출 없음

export interface PublicDraft {
  channel: "instagram" | "newsletter" | "blog" | "youtube"
  body: string
  gus: string[] // 이 초안에서 언급되는 구 목록
  labels: {
    type: "landex-grade" | "gei-stage"
    gu: string
    value: string
  }[]
  mentionsVams?: boolean // 명시적 플래그 (초안 생성기가 세팅)
}

export interface PublicationHistory {
  gu: string
  channel: string
  publishedAt: Date
  type: "landex-grade" | "gei-stage"
}

export interface CheckResult {
  id: string
  label: string
  passed: boolean
  reason?: string
}

// --- 정규식 사전 ---

/** 원점수·수치 패턴 (소수점 포함 숫자) */
const RAW_NUMBER_PATTERN = /\b\d+\.\d+\b/

/** 백분율·점수 단위 단서 */
const SCORE_UNIT_PATTERN = /(\d+(?:\.\d+)?)\s*(?:점|score)/i

/** 가중치 누출 패턴 */
const WEIGHT_LEAK_PATTERNS = [
  /가중치/,
  /\b0\.\d+\s*·/,
  /×\s*0\.\d+/,
  /실려\s*서|실려\s*있/,
  /Value\s*\d+\s*%|Catalyst\s*\d+\s*%/i,
]

/** 임계치 누출 패턴 */
const THRESHOLD_LEAK_PATTERNS = [
  /임계치/,
  /경계값|경계치/,
  /GEI\s*40|GEI\s*65|GEI\s*85/,
  /Stage\s*\d+\s*→\s*Stage\s*\d+/,
]

/** VAMS 관련 키워드 */
const VAMS_LEAK_PATTERNS = [/VAMS/i, /가상\s*포지션/, /내\s*포지션/, /수익률/]

// --- Checks ---

export function checkRawNumbers(draft: PublicDraft): CheckResult {
  const m = RAW_NUMBER_PATTERN.exec(draft.body) || SCORE_UNIT_PATTERN.exec(draft.body)
  return {
    id: "raw-numbers",
    label: "원점수·수치 없음",
    passed: !m,
    reason: m ? `"${m[0]}" 발견` : undefined,
  }
}

export function checkCombinationGuard(draft: PublicDraft): CheckResult {
  // 같은 구에 대해 landex-grade와 gei-stage를 동시 언급 금지
  const byGu = new Map<string, Set<string>>()
  for (const lbl of draft.labels) {
    const set = byGu.get(lbl.gu) ?? new Set<string>()
    set.add(lbl.type)
    byGu.set(lbl.gu, set)
  }
  const violating: string[] = []
  byGu.forEach((types, gu) => {
    if (types.has("landex-grade") && types.has("gei-stage")) violating.push(gu)
  })
  return {
    id: "combination-guard",
    label: "Combination guard (LANDEX + GEI 동시 노출 없음)",
    passed: violating.length === 0,
    reason: violating.length > 0 ? `중복 노출: ${violating.join(", ")}` : undefined,
  }
}

export function checkGeographicGap(
  draft: PublicDraft,
  history: PublicationHistory[],
  now: Date = new Date(),
  gapDays: number = 28,
): CheckResult {
  const cutoff = now.getTime() - gapDays * 24 * 60 * 60 * 1000
  const violated: string[] = []
  for (const gu of draft.gus) {
    const recent = history.filter(
      (h) => h.gu === gu && h.publishedAt.getTime() >= cutoff,
    )
    if (recent.length > 0) violated.push(gu)
  }
  return {
    id: "geographic-gap",
    label: `지역 ${gapDays}일 간격`,
    passed: violated.length === 0,
    reason:
      violated.length > 0
        ? `${gapDays}일 내 재노출: ${violated.join(", ")}`
        : undefined,
  }
}

export function checkNoVams(draft: PublicDraft): CheckResult {
  if (draft.mentionsVams) {
    return {
      id: "no-vams",
      label: "VAMS 참조 없음",
      passed: false,
      reason: "VAMS 참조 플래그가 설정됨",
    }
  }
  for (const p of VAMS_LEAK_PATTERNS) {
    const m = p.exec(draft.body)
    if (m) {
      return {
        id: "no-vams",
        label: "VAMS 참조 없음",
        passed: false,
        reason: `"${m[0]}" 발견`,
      }
    }
  }
  return { id: "no-vams", label: "VAMS 참조 없음", passed: true }
}

export function checkNoWeightLeak(draft: PublicDraft): CheckResult {
  for (const p of WEIGHT_LEAK_PATTERNS) {
    const m = p.exec(draft.body)
    if (m) {
      return {
        id: "no-weight-leak",
        label: "가중치 누출 없음",
        passed: false,
        reason: `"${m[0]}" 발견`,
      }
    }
  }
  return { id: "no-weight-leak", label: "가중치 누출 없음", passed: true }
}

export function checkNoThresholdLeak(draft: PublicDraft): CheckResult {
  for (const p of THRESHOLD_LEAK_PATTERNS) {
    const m = p.exec(draft.body)
    if (m) {
      return {
        id: "no-threshold-leak",
        label: "임계치 누출 없음",
        passed: false,
        reason: `"${m[0]}" 발견`,
      }
    }
  }
  return { id: "no-threshold-leak", label: "임계치 누출 없음", passed: true }
}

// --- 집계 ---

export interface DilutionCheckOptions {
  history?: PublicationHistory[]
  now?: Date
  gapDays?: number
}

/**
 * 6개 체크를 모두 실행. Digest 페이지 DilutionCheckPanel에 그대로 주입 가능.
 */
export function runDilutionChecks(
  draft: PublicDraft,
  opts: DilutionCheckOptions = {},
): CheckResult[] {
  return [
    checkRawNumbers(draft),
    checkCombinationGuard(draft),
    checkGeographicGap(draft, opts.history ?? [], opts.now, opts.gapDays),
    checkNoVams(draft),
    checkNoWeightLeak(draft),
    checkNoThresholdLeak(draft),
  ]
}

export function isPublishable(results: CheckResult[]): boolean {
  return results.every((r) => r.passed)
}

// --- 로그 포맷 ---

export interface TransformationLog {
  postId: string
  channel: string
  publishedAt: string // ISO
  internalRefs: {
    landexSnapshotVersion?: string
    geiSnapshotVersion?: string
    sourceGus: string[]
    sourceScoresEncrypted?: string
  }
  publicContent: {
    labels: { gu: string; value: string; type: string }[]
    body: string
  }
  checks: {
    dilutionFilterPass: boolean
    combinationGuardPass: boolean
    failures?: string[]
  }
}

export function buildLog(
  postId: string,
  draft: PublicDraft,
  results: CheckResult[],
  internalRefs: Partial<TransformationLog["internalRefs"]> = {},
): TransformationLog {
  const failures = results.filter((r) => !r.passed).map((r) => r.id)
  return {
    postId,
    channel: draft.channel,
    publishedAt: new Date().toISOString(),
    internalRefs: {
      sourceGus: draft.gus,
      ...internalRefs,
    },
    publicContent: {
      labels: draft.labels.map((l) => ({ gu: l.gu, value: l.value, type: l.type })),
      body: draft.body,
    },
    checks: {
      dilutionFilterPass: results.every((r) => r.passed),
      combinationGuardPass:
        results.find((r) => r.id === "combination-guard")?.passed ?? false,
      failures: failures.length > 0 ? failures : undefined,
    },
  }
}
