/**
 * VERITY Framer 공통 패턴 + 디자인 토큰 마스터 (Toss Dark v2)
 *
 * Framer Code Components 는 단일 파일 제약으로 import 가 불가하므로,
 * 각 컴포넌트는 이 파일의 토큰 블록을 ◆MARKER◆ 사이로 인라인 복사한다.
 * 이 파일 자체는 Framer 에 등록하지 않는다 (참조용 마스터).
 *
 * 토큰 변경 시: 이 파일에서 먼저 확정 → 49개 컴포넌트로 일괄 복붙.
 */

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS START ◆ (이 블록 전체를 각 컴포넌트 상단에 복붙)
 * ────────────────────────────────────────────────────────────── */

/* 색상 — Neo Dark Terminal (트레이딩 터미널 톤, 네온 액센트 보호)
 * 배경 더 어둡게 잡아 차트·숫자가 도드라지고 네온그린 글로우 효과 강화. */
export const C = {
    /* surface — 깊이별 배경 4단계 (푸른 기 미세, 검정에 가까움) */
    bgPage: "#0E0F11",        // 최외곽 페이지 배경 (트레이딩 터미널 톤)
    bgCard: "#171820",        // 기본 카드/패널
    bgElevated: "#22232B",    // 강조 카드/모달/hover
    bgInput: "#2A2B33",       // 입력/필터/칩 배경

    /* border — 옅게, hover 시 accent 로 전환되는 패턴 권장 */
    border: "#23242C",        // 평상시 (배경과 미세 차이만)
    borderStrong: "#34353D",  // 탭 active / 강조 구분선
    borderHover: "#B5FF19",   // hover/focus 시 (accent 동일)

    /* text — 3단계 위계 */
    textPrimary: "#F2F3F5",   // 본문/숫자 (흰색에 가까움)
    textSecondary: "#A8ABB2", // 보조/라벨
    textTertiary: "#6B6E76",  // 캡션/메타/단위
    textDisabled: "#4A4C52",  // 비활성

    /* brand — 명령서 고정 (변경 금지) */
    accent: "#B5FF19",        // VERITY 네온그린 (CTA·하이라이트)
    accentSoft: "rgba(181,255,25,0.12)",  // accent 알파 — focus ring/배경 강조

    /* signal — 매매 등급 (gradeColors, 명령서 고정) */
    strongBuy: "#22C55E",
    buy: "#B5FF19",
    watch: "#FFD600",
    caution: "#F59E0B",
    avoid: "#EF4444",

    /* market — 한국 관행 (명령서 고정) */
    up: "#F04452",            // 상승 빨강
    down: "#3182F6",          // 하락 파랑

    /* semantic — 정보/경고 (시그널과 분리) */
    info: "#5BA9FF",
    success: "#22C55E",
    warn: "#F59E0B",
    danger: "#EF4444",

    /* interaction — hover/active/focus 상태 */
    hoverOverlay: "rgba(255,255,255,0.04)",  // surface 위 hover 오버레이
    activeOverlay: "rgba(255,255,255,0.08)", // press 상태
    focusRing: "rgba(181,255,25,0.35)",      // focus 외곽선 (accent 35% alpha)
    scrim: "rgba(0,0,0,0.5)",                // 모달 backdrop
}

/* GLOW — 네온 액센트 글로우 (selective 사용: active 탭, hover 카드, 핵심 숫자) */
export const G = {
    accent: "0 0 8px rgba(181,255,25,0.35)",         // 표준 accent glow
    accentSoft: "0 0 4px rgba(181,255,25,0.20)",     // 약한 글로우 (idle 강조)
    accentStrong: "0 0 12px rgba(181,255,25,0.50)",  // 강한 글로우 (active CTA)
    danger: "0 0 6px rgba(239,68,68,0.30)",          // 위험 알림
    success: "0 0 6px rgba(34,197,94,0.30)",         // 성공 신호
    none: "none",
}

/* 폰트 사이즈 — 한국어 다크 UI 본문 14px 표준 (기존 9-10px 대비 +40% 가독성) */
export const T = {
    cap: 12,    // 캡션/메타 (단위, freshness 태그)
    body: 14,   // 본문 표준
    sub: 16,    // 서브타이틀/카드 헤더
    title: 18,  // 섹션 타이틀
    h2: 22,     // 페이지 H2
    h1: 28,     // 메인 헤딩/큰 숫자
    /* 굵기 — 600 semibold 추가 */
    w_reg: 400,
    w_med: 500,
    w_semi: 600,
    w_bold: 700,
    w_black: 800,
    /* line-height (배수) — 가독성 표준 1.5 */
    lh_tight: 1.3,   // 큰 숫자/헤딩
    lh_normal: 1.5,  // 본문 (한국어 표준)
    lh_loose: 1.7,   // 다단락 설명문
}

/* 간격 — 8pt grid + 20 (카드 padding 표준) */
export const S = {
    xs: 4,
    sm: 8,
    md: 12,
    lg: 16,
    xl: 20,    // 카드 padding 표준 (토스 관행)
    xxl: 24,
    xxxl: 32,
}

/* radius — 한 단계 작게 (각진 느낌, 트레이딩 터미널 정밀감) */
export const R = {
    sm: 6,    // 칩/배지/태그
    md: 10,   // 기본 카드/입력
    lg: 14,   // 큰 패널/모달
    pill: 999, // 둥근 칩
}

/* elevation 정책 — 다크 모드는 일반 그림자 대신 배경 단계로 depth 표현.
 * 단, 네온 액센트 GLOW (G.accent 등) 는 selective 강조 시 사용 (active 탭/CTA).
 */

/* transition — 인터랙션 속도 표준 */
export const X = {
    fast: "120ms ease",     // 칩/링크 hover
    base: "180ms ease",     // 카드 hover/탭 전환
    slow: "240ms ease",     // 모달/패널 진입
}

/* 폰트 패밀리 — 본문 sans / 숫자·티커·단위는 mono (Bloomberg 단말기 정밀감) */
export const FONT = "'Inter', 'Pretendard', -apple-system, sans-serif"
export const FONT_MONO = "'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace"

/* MONO 사용 가이드 (적용 권장 영역):
 *   - 가격, 거래량, 시가총액, 등락률, 점수 (숫자)
 *   - 티커 (AAPL, 005930)
 *   - 시각 (HH:MM, HH:MM:SS)
 *   - 비율/단위 (%, 원, $, M, B)
 *   - microcopy 메타 태그 (FRESH / STALE / EXPIRED) — uppercase + cap
 */

/* 등급 라벨/색상 (명령서 고정 — 변경 금지) */
export const gradeLabels: Record<string, string> = {
    STRONG_BUY: "강력매수", BUY: "매수", WATCH: "관망", CAUTION: "주의", AVOID: "회피",
}
export const gradeColors: Record<string, string> = {
    STRONG_BUY: "#22C55E", BUY: "#B5FF19", WATCH: "#FFD600", CAUTION: "#F59E0B", AVOID: "#EF4444",
}

/* ──────────────────────────────────────────────────────────────
 * ◆ DESIGN TOKENS END ◆
 * ────────────────────────────────────────────────────────────── */


/* ── 카드 베이스 스타일 (참조용 — 인라인 복사 시 const card = {...}) ── */
export const cardStyle: React.CSSProperties = {
    background: C.bgCard,
    border: `1px solid ${C.border}`,
    borderRadius: R.md,
    padding: S.xl,             // 20 (숨통)
    fontFamily: FONT,
    color: C.textPrimary,
    fontSize: T.body,          // 14
    lineHeight: T.lh_normal,   // 1.5
    transition: X.base,        // hover 시 boxShadow/border 자연 전환
}

/* hover 시 적용 권장 (인라인 추가):
 *   borderColor: C.borderHover, boxShadow: G.accentSoft
 */
export const elevatedCardStyle: React.CSSProperties = {
    background: C.bgElevated,
    border: `1px solid ${C.border}`,
    borderRadius: R.md,
    padding: S.xl,
    fontFamily: FONT,
    color: C.textPrimary,
    fontSize: T.body,
    lineHeight: T.lh_normal,
}

/* ── 모노 숫자 스타일 (참조용 — 가격/점수 표시) ── */
export const monoNumStyle: React.CSSProperties = {
    fontFamily: FONT_MONO,
    fontVariantNumeric: "tabular-nums",  // 숫자 폭 일정 (정렬 정밀)
    letterSpacing: "-0.01em",
}

/* ── microcopy 메타 태그 (FRESH/STALE/EXPIRED) ── */
export const metaTagStyle: React.CSSProperties = {
    fontFamily: FONT_MONO,
    fontSize: T.cap,
    fontWeight: T.w_semi,
    letterSpacing: "0.05em",
    textTransform: "uppercase",
    padding: `2px ${S.sm}px`,
    borderRadius: R.sm,
}


/* ── NaN/Infinity Sanitize (표준) ── */
export function sanitizeJson(txt: string): any {
    return JSON.parse(
        txt
            .replace(/\bNaN\b/g, "null")
            .replace(/\bInfinity\b/g, "null")
            .replace(/-null/g, "null"),
    )
}

/* ── Sparkline SVG (표준) ── */
export function Sparkline({
    data,
    width = 60,
    height = 24,
    color = C.textTertiary,
}: {
    data: number[]
    width?: number
    height?: number
    color?: string
}) {
    if (!data || data.length < 2) return null
    const min = Math.min(...data)
    const max = Math.max(...data)
    const range = max - min || 1
    const points = data
        .map(
            (v, i) =>
                `${(i / (data.length - 1)) * width},${height - ((v - min) / range) * height}`,
        )
        .join(" ")
    return (
        <svg width={width} height={height} style={{ display: "block" }}>
            <polyline
                points={points}
                fill="none"
                stroke={color}
                strokeWidth={1.5}
                strokeLinejoin="round"
                strokeLinecap="round"
            />
        </svg>
    )
}

/* ── RingGauge SVG (표준) ── */
export function RingGauge({
    value,
    label,
    size = 56,
    color,
}: {
    value: number
    label: string
    size?: number
    color: string
}) {
    const r = (size - 6) / 2
    const circ = 2 * Math.PI * r
    const offset = circ * (1 - Math.min(value, 100) / 100)
    return (
        <div
            style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: S.xs,
            }}
        >
            <svg
                width={size}
                height={size}
                style={{ transform: "rotate(-90deg)" }}
            >
                <circle
                    cx={size / 2}
                    cy={size / 2}
                    r={r}
                    fill="none"
                    stroke={C.bgElevated}
                    strokeWidth={5}
                />
                <circle
                    cx={size / 2}
                    cy={size / 2}
                    r={r}
                    fill="none"
                    stroke={color}
                    strokeWidth={5}
                    strokeDasharray={circ}
                    strokeDashoffset={offset}
                    strokeLinecap="round"
                />
            </svg>
            <span
                style={{
                    color,
                    fontSize: T.sub,
                    fontWeight: T.w_black,
                    marginTop: -38,
                }}
            >
                {value}
            </span>
            <span style={{ color: C.textTertiary, fontSize: T.cap, marginTop: 16 }}>
                {label}
            </span>
        </div>
    )
}


/* ── 레거시 호환 (점진적 deprecation) ──
 * 기존 컴포넌트가 COLORS 를 import 하지 않지만, 코드 내 인라인 값 치환 시
 * 매핑 참조용으로 남겨둠. Phase 4 완료 후 제거 예정.
 */
export const COLORS = {
    bg: C.bgPage,
    card: C.bgCard,
    border: C.border,
    accent: C.accent,
    positive: C.success,
    negative: C.danger,
    warning: C.warn,
    muted: C.textTertiary,
}
